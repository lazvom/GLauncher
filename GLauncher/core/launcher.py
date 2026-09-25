"""
Thin wrapper around minecraft_launcher_lib that gives us:
- version listing (release / snapshot / old versions)
- installing vanilla / fabric / forge / neoforge / quilt
- building launch options + launching the game
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
import uuid
from typing import Callable, Optional

import minecraft_launcher_lib as mll

LOADERS = ["vanilla", "fabric", "quilt", "forge", "neoforge"]
LOADER_LABELS = {
    "vanilla": "Vanilla",
    "fabric": "Fabric",
    "quilt": "Quilt",
    "forge": "Forge",
    "neoforge": "NeoForge",
}


def offline_uuid(username: str) -> str:
    """Reproduces Minecraft's offline-mode UUID algorithm
    (MD5 of 'OfflinePlayer:<name>', version/variant bits patched to v3)."""
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{username}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


def get_version_list(include_snapshots: bool = True, include_old: bool = False):
    """Returns vanilla version dicts: {id, type, releaseTime}."""
    versions = mll.utils.get_version_list()
    out = []
    for v in versions:
        t = v["type"]
        if t == "release":
            out.append(v)
        elif t == "snapshot" and include_snapshots:
            out.append(v)
        elif t in ("old_beta", "old_alpha") and include_old:
            out.append(v)
    return out


def get_loader_minecraft_versions(loader_id: str, stable_only: bool = False):
    """Minecraft versions compatible with a given loader."""
    if loader_id == "vanilla":
        return [v["id"] for v in get_version_list(include_snapshots=True, include_old=True)]
    loader = mll.mod_loader.get_mod_loader(loader_id)
    return loader.get_minecraft_versions(stable_only)


def get_loader_versions(loader_id: str, mc_version: str, stable_only: bool = False):
    """Loader-specific build versions (e.g. Fabric loader 0.16.x) for a given MC version."""
    if loader_id == "vanilla":
        return []
    loader = mll.mod_loader.get_mod_loader(loader_id)
    try:
        return loader.get_loader_versions(mc_version, stable_only)
    except Exception:
        return []


def get_minecraft_directory() -> str:
    return mll.utils.get_minecraft_directory()


def is_version_installed(version_id: str, minecraft_directory: str) -> bool:
    return mll.utils.is_version_valid(version_id, minecraft_directory)


def install_version(
    minecraft_directory: str,
    mc_version: str,
    loader_id: str = "vanilla",
    loader_version: Optional[str] = None,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
    java: Optional[str] = None,
) -> str:
    """
    Installs vanilla or a modloader into `minecraft_directory`.
    progress_cb(status_text, current, maximum) is called throughout the install.
    Returns the version id that should be passed to get_minecraft_command / launch().
    """
    state = {"status": "", "progress": 0, "max": 0}
    last_fired = {"t": 0.0}

    def _fire(force: bool = False):
        if not progress_cb:
            return
        now = time.monotonic()
        is_done = state["max"] and state["progress"] >= state["max"]
        # setProgress fires once per file - libraries/assets alone can be 1000-3000+ calls.
        # Forwarding every single one floods the UI update queue and makes the app stutter
        # or appear to hang, so only forward at most ~10x/second (always forward on
        # status changes and on completion, so nothing important gets dropped).
        if force or is_done or now - last_fired["t"] >= 0.1:
            progress_cb(state["status"], state["progress"], state["max"])
            last_fired["t"] = now

    def set_status(s):
        state["status"] = s
        _fire(force=True)

    def set_progress(p):
        state["progress"] = p
        _fire()

    def set_max(m):
        state["max"] = m
        _fire(force=True)

    callback = {"setStatus": set_status, "setProgress": set_progress, "setMax": set_max}

    os.makedirs(minecraft_directory, exist_ok=True)

    if loader_id == "vanilla":
        mll.install.install_minecraft_version(mc_version, minecraft_directory, callback=callback)
        return mc_version

    loader = mll.mod_loader.get_mod_loader(loader_id)
    installed_version = loader.install(
        mc_version,
        minecraft_directory,
        loader_version=loader_version,
        callback=callback,
        java=java,
    )
    return installed_version


def detect_mrpack_loader(mrpack_path: str):
    """Reads modrinth.index.json inside a .mrpack file and returns (loader_id, loader_version)
    for whichever mod loader the pack depends on (or ("vanilla", None) if none)."""
    import json
    import zipfile

    with zipfile.ZipFile(mrpack_path, "r") as zf:
        with zf.open("modrinth.index.json", "r") as f:
            index = json.load(f)
    deps = index.get("dependencies", {})
    if "forge" in deps:
        return "forge", deps["forge"]
    if "neoforge" in deps:
        return "neoforge", deps["neoforge"]
    if "fabric-loader" in deps:
        return "fabric", deps["fabric-loader"]
    if "quilt-loader" in deps:
        return "quilt", deps["quilt-loader"]
    return "vanilla", None


def install_modpack(
    mrpack_path: str,
    minecraft_directory: str,
    modpack_directory: Optional[str] = None,
    progress_cb: Optional[Callable[[str, int, int], None]] = None,
):
    """Installs a Modrinth .mrpack modpack (downloads its overrides + required mod files)."""
    state = {"status": "", "progress": 0, "max": 0}
    last_fired = {"t": 0.0}

    def _fire(force: bool = False):
        if not progress_cb:
            return
        now = time.monotonic()
        is_done = state["max"] and state["progress"] >= state["max"]
        if force or is_done or now - last_fired["t"] >= 0.1:
            progress_cb(state["status"], state["progress"], state["max"])
            last_fired["t"] = now

    callback = {
        "setStatus": lambda s: (state.update(status=s), _fire(force=True)),
        "setProgress": lambda p: (state.update(progress=p), _fire()),
        "setMax": lambda m: (state.update(max=m), _fire(force=True)),
    }
    mll.mrpack.install_mrpack(mrpack_path, minecraft_directory, modpack_directory, callback=callback)
    return mll.mrpack.get_mrpack_launch_version(mrpack_path)


def build_options(
    username: str,
    uuid_: str,
    token: str = "",
    ram_min_mb: int = 1024,
    ram_max_mb: int = 4096,
    extra_jvm_args: Optional[list] = None,
    game_directory: Optional[str] = None,
    demo: bool = False,
) -> dict:
    options: dict = {
        "username": username,
        "uuid": uuid_,
        "token": token or "",
        "launcherName": "GlassLauncher",
        "launcherVersion": "1.0",
    }
    jvm_args = [f"-Xms{ram_min_mb}M", f"-Xmx{ram_max_mb}M"]
    if extra_jvm_args:
        jvm_args.extend(extra_jvm_args)
    options["jvmArguments"] = jvm_args
    if game_directory:
        options["gameDirectory"] = game_directory
    if demo:
        options["demo"] = True
    return options


def get_launch_command(version_id: str, minecraft_directory: str, options: dict) -> list:
    return mll.command.get_minecraft_command(version_id, minecraft_directory, options)


def launch(version_id: str, minecraft_directory: str, options: dict, cwd: Optional[str] = None) -> subprocess.Popen:
    command = get_launch_command(version_id, minecraft_directory, options)
    popen_kwargs = {}
    if sys.platform.startswith("win"):
        # Without this, launching the JVM pops up a visible console/cmd window
        # alongside the game on Windows - this suppresses that while still
        # letting us capture stdout/stderr normally for the console panel.
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    return subprocess.Popen(
        command,
        cwd=cwd or options.get("gameDirectory") or minecraft_directory,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        **popen_kwargs,
    )
