"""
Minimal Modrinth API client used for the Content browser tab.
No API key is required for Modrinth's public API.

project_type: "mod" | "modpack" | "resourcepack" | "shader"
"""
from __future__ import annotations

import json
import os
import time
from typing import Optional

import requests

API_BASE = "https://api.modrinth.com/v2"
USER_AGENT = "GlassLauncher/1.0 (custom minecraft launcher)"

FOLDER_FOR_TYPE = {
    "mod": "mods",
    "resourcepack": "resourcepacks",
    "shader": "shaderpacks",
}

# Loader ids that are meaningful as a Modrinth "categories" facet for a given project type.
LOADER_FACET_APPLICABLE = {"mod": True, "modpack": True, "resourcepack": False, "shader": False}


def _headers():
    return {"User-Agent": USER_AGENT}


def search(
    query: str,
    project_type: str,
    loader: Optional[str] = None,
    game_version: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    # Shaders, resource packs, and modpacks aren't tied to a specific instance's mod loader
    # or Minecraft version the way individual mods are - browse everything for those.
    if project_type in ("shader", "resourcepack", "modpack"):
        loader = None
        game_version = None

    facets = [[f"project_type:{project_type}"]]
    if loader and loader != "vanilla" and LOADER_FACET_APPLICABLE.get(project_type):
        facets.append([f"categories:{loader}"])
    if game_version:
        facets.append([f"versions:{game_version}"])

    params = {
        "query": query,
        "limit": limit,
        "offset": offset,
        "facets": json.dumps(facets),
        "index": "relevance",
    }
    resp = requests.get(f"{API_BASE}/search", params=params, headers=_headers(), timeout=20)
    resp.raise_for_status()
    return resp.json()


def get_project_versions(
    project_id: str,
    loader: Optional[str] = None,
    game_version: Optional[str] = None,
    project_type: Optional[str] = None,
) -> list:
    if project_type in ("shader", "resourcepack", "modpack"):
        loader = None
        game_version = None

    params = {}
    if loader and loader != "vanilla":
        params["loaders"] = json.dumps([loader])
    if game_version:
        params["game_versions"] = json.dumps([game_version])
    resp = requests.get(f"{API_BASE}/project/{project_id}/version", params=params, headers=_headers(), timeout=20)
    resp.raise_for_status()
    return resp.json()


def filter_compatible_versions(
    versions: list,
    loader: Optional[str] = None,
    game_version: Optional[str] = None,
) -> list:
    """Defensive client-side filter on top of the API's own loader/game_version params -
    only keeps versions that actually declare support for the given loader and/or MC version.
    Versions are returned newest-first (Modrinth already sorts them that way)."""
    out = []
    for v in versions:
        if loader and loader not in ("vanilla",):
            if v.get("loaders") and loader not in v["loaders"]:
                continue
        if game_version:
            if v.get("game_versions") and game_version not in v["game_versions"]:
                continue
        out.append(v)
    return out


def download_file(url: str, dest_path: str, progress_cb=None) -> str:
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    with requests.get(url, headers=_headers(), stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        written = 0
        last_report = 0.0
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                if not chunk:
                    continue
                f.write(chunk)
                written += len(chunk)
                if progress_cb and total:
                    now = time.monotonic()
                    # Report at most ~10x/second - a 300MB file at 64KB/chunk is thousands
                    # of chunks; firing a UI update for every single one floods the queue
                    # and makes the whole app stutter instead of just showing smooth progress.
                    if now - last_report >= 0.1 or written >= total:
                        progress_cb(written, total)
                        last_report = now
    return dest_path


def install_content(
    instance_dir: str,
    project_type: str,
    version: dict,
    progress_cb=None,
) -> str:
    """Downloads the primary file of a Modrinth version into the right instance subfolder.
    For project_type == 'modpack', downloads the .mrpack to a temp path and returns that
    path instead (caller should then run launcher.install_modpack on it)."""
    files = version.get("files", [])
    primary = next((f for f in files if f.get("primary")), files[0] if files else None)
    if primary is None:
        raise ValueError("This version has no downloadable files.")

    filename = primary["filename"]
    url = primary["url"]

    if project_type == "modpack":
        dest = os.path.join(instance_dir, ".modrinth_cache", filename)
    else:
        subfolder = FOLDER_FOR_TYPE.get(project_type, "mods")
        dest = os.path.join(instance_dir, subfolder, filename)

    return download_file(url, dest, progress_cb=progress_cb)


def get_version(version_id: str) -> dict:
    resp = requests.get(f"{API_BASE}/version/{version_id}", headers=_headers(), timeout=20)
    resp.raise_for_status()
    return resp.json()


def resolve_dependencies(
    version: dict,
    loader: Optional[str] = None,
    game_version: Optional[str] = None,
    already_installed: Optional[set] = None,
    _seen: Optional[set] = None,
) -> list:
    """Recursively resolves a version's 'required' dependencies into a flat list of
    version dicts to also install. Skips optional/incompatible/embedded dependencies,
    anything already embedded in the jar, and anything whose project_id is in
    already_installed (a set of Modrinth project ids already present in the target
    instance - so a mod that several others depend on only gets downloaded once, and
    not re-downloaded on every subsequent install)."""
    if _seen is None:
        _seen = set()
    if already_installed is None:
        already_installed = set()

    resolved = []
    for dep in version.get("dependencies", []) or []:
        if dep.get("dependency_type") != "required":
            continue
        project_id = dep.get("project_id")
        if not project_id or project_id in _seen:
            continue
        _seen.add(project_id)
        if project_id in already_installed:
            continue  # already there - nothing to download, and assume its own deps are too

        dep_version = None
        try:
            version_id = dep.get("version_id")
            if version_id:
                dep_version = get_version(version_id)
            else:
                candidates = get_project_versions(project_id, loader=loader, game_version=game_version)
                candidates = filter_compatible_versions(candidates, loader=loader, game_version=game_version)
                if candidates:
                    dep_version = candidates[0]
        except Exception:
            dep_version = None

        if dep_version:
            resolved.append(dep_version)
            resolved.extend(resolve_dependencies(dep_version, loader, game_version, already_installed, _seen))

    return resolved


_CONTENT_FOLDER_TO_TYPE = {"mods": "mod", "resourcepacks": "resourcepack", "shaderpacks": "shader"}


def identify_installed_files(instance_dir: str) -> list:
    """Scans the instance's mods/resourcepacks/shaderpacks folders and identifies
    every file that matches something on Modrinth by content hash (via Modrinth's
    bulk hash-lookup endpoint). This is what actually landed on disk, so unlike
    parsing a modpack's index.json, it catches mods a pack bundled as raw files
    (in its `overrides/` folder) just as reliably as ones it listed as a tracked
    CDN download - a modpack shipping e.g. Sodium either way still gets picked up.
    Returns a list of {project_id, version_id, filename, project_type} dicts for
    every file Modrinth recognized; anything it doesn't recognize (private mods,
    hand-written configs, non-Modrinth content) is silently skipped."""
    import hashlib

    hash_to_file = {}  # sha1 hex -> (filename, project_type)
    for folder, project_type in _CONTENT_FOLDER_TO_TYPE.items():
        dir_path = os.path.join(instance_dir, folder)
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            fpath = os.path.join(dir_path, fname)
            if not os.path.isfile(fpath):
                continue
            try:
                digest = hashlib.sha1()
                with open(fpath, "rb") as f:
                    for chunk in iter(lambda: f.read(1 << 16), b""):
                        digest.update(chunk)
                hash_to_file[digest.hexdigest()] = (fname, project_type)
            except Exception:
                continue

    if not hash_to_file:
        return []

    try:
        resp = requests.post(
            f"{API_BASE}/version_files",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"hashes": list(hash_to_file.keys()), "algorithm": "sha1"},
            timeout=30,
        )
        resp.raise_for_status()
        matches = resp.json()
    except Exception:
        return []

    results = []
    for sha1, version in matches.items():
        entry = hash_to_file.get(sha1)
        if not entry or not version.get("project_id"):
            continue
        filename, project_type = entry
        results.append({
            "project_id": version["project_id"],
            "version_id": version.get("id"),
            "filename": filename,
            "project_type": project_type,
        })
    return results


def get_project(project_id: str) -> dict:
    resp = requests.get(f"{API_BASE}/project/{project_id}", headers=_headers(), timeout=20)
    resp.raise_for_status()
    return resp.json()


def get_projects(project_ids: list) -> list:
    """Batch project lookup (title + icon_url, among other fields) for the
    Manage tab, so filling in display names for a whole list of installed
    mods/shaders/resource packs costs one request instead of one per item."""
    ids = [pid for pid in dict.fromkeys(project_ids) if pid]
    if not ids:
        return []
    resp = requests.get(
        f"{API_BASE}/projects", params={"ids": json.dumps(ids)}, headers=_headers(), timeout=20,
    )
    resp.raise_for_status()
    return resp.json()
