"""
Self-update from GitHub Releases on the GLauncher repo.

This tracks the repo's *latest published release* (tag name, release name,
and changelog body) rather than raw commits, so the update prompt can show
a real version name and changelog instead of a commit hash. That means
updates only show up once a release is actually published on GitHub - a
push to `main` alone won't trigger anything. When it's time to ship an
update, publish a GitHub Release (Releases > Draft a new release) and this
picks it up on its own.

The release's own source zip is what gets applied: everything in it is
synced into the launcher root except a short exclusion list (see
EXCLUDED_FROM_SYNC below) - so a release that adds a brand new file or
folder just installs it, no code change needed here to recognise it. The
data/ directory (accounts, instances, settings) is always left untouched.
The updater deliberately does not execute pip after downloading release
source; dependency changes must be installed by the trusted build/install
process rather than by network-delivered requirements.txt.

This only takes effect for a source checkout - i.e. `python main.py`
directly, or `launcher.py` (see that file) spawning main.py as a real,
unfrozen Python process. If main.py itself were ever frozen directly with
PyInstaller, the running executable would be a compiled binary that new
.py files wouldn't affect, so the check is skipped in that case (see
is_frozen()) - `launcher.py` exists specifically so that doesn't happen.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import urllib.error
import zipfile
from typing import Callable, Optional
from pathlib import PurePosixPath

from .security import is_https_host
from .instances import _launcher_root

REPO = "lazvom/GLauncher"
API_LATEST_RELEASE_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
USER_AGENT = "GLauncher-updater"

VERSION_FILENAME = ".glauncher_version"

# Everything in the launcher root is synced from a release EXCEPT these -
# so a release that adds a brand new file or folder just shows up after
# updating, with nothing to configure here. data/ is the user's accounts,
# instances and settings; python-embed/ is the runtime a packaged .exe
# runs on (see scripts/setup_python_embed.ps1); the rest is either
# bookkeeping that doesn't belong in a running install, or metadata that
# only makes sense inside a git checkout, not something GitHub's own
# release zipball can strip out on its own.
EXCLUDED_FROM_SYNC = {
    "data", "python-embed", "__pycache__", VERSION_FILENAME,
    ".git", ".github", ".gitignore", ".gitattributes", "LICENSE",
}

MAX_UPDATE_ARCHIVE_BYTES = 250 * 1024 * 1024

# Two distinct stages, two distinct expected hosts - conflating them is what
# made every real update report "unexpected update host":
#  1. The release JSON's own "zipball_url" field is an api.github.com URL
#     (e.g. https://api.github.com/repos/<repo>/zipball/<tag>) - that's the
#     host GitHub documents for this field, so it's what gets checked before
#     we ever follow it.
#  2. Actually requesting that URL 302s to a signed, short-lived download on
#     codeload.github.com - that's the host that must serve the real bytes,
#     checked against resp.geturl() in apply_update() after redirects.
ALLOWED_API_ZIP_HOSTS = {"api.github.com"}
ALLOWED_ZIP_HOSTS = {"codeload.github.com", "github.com"}


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _version_file() -> str:
    return os.path.join(_launcher_root(), VERSION_FILENAME)


def get_local_release() -> Optional[dict]:
    """The release we last updated to: {"tag", "name"}, or None if this
    install has never recorded one (fresh checkout, or updater just added)."""
    try:
        with open(_version_file(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("tag"):
            return None
        return data
    except Exception:
        return None


def _set_local_release(tag: str, name: str) -> None:
    try:
        with open(_version_file(), "w", encoding="utf-8") as f:
            json.dump({"tag": tag, "name": name}, f)
    except OSError:
        pass


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_remote_release() -> Optional[dict]:
    """The latest published release: {"tag", "name", "body", "date",
    "zip_url"}, or None if the repo has no releases published yet. Raises
    on any other network/API failure - callers should catch and surface it."""
    try:
        data = _get_json(API_LATEST_RELEASE_URL)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 403 and e.headers and e.headers.get("X-RateLimit-Remaining") == "0":
            # GitHub's unauthenticated API limit is 60 requests/hour, shared
            # by everyone behind the same IP (offices, CGNAT, VPNs...) - easy
            # to hit without it meaning anything is actually wrong.
            raise RuntimeError("GitHub API rate limit exceeded for your network - try again later.") from e
        raise
    zip_url = data["zipball_url"]
    if not is_https_host(zip_url, ALLOWED_API_ZIP_HOSTS):
        raise ValueError("GitHub returned an unexpected update host.")
    if data.get("draft") or data.get("prerelease"):
        return None
    return {
        "tag": data["tag_name"],
        "name": data.get("name") or data["tag_name"],
        "body": data.get("body") or "",
        "date": data.get("published_at", ""),
        "zip_url": zip_url,
    }


def check_for_update() -> dict:
    """Returns a dict describing update status, or {"error": ...}. Never
    raises. If this is the very first check (no local release recorded
    yet), the current latest release is adopted as the baseline silently,
    rather than reporting an "update" for a version that may already be
    what's on disk."""
    if is_frozen():
        return {"update_available": False, "frozen": True}
    try:
        remote = get_remote_release()
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, RuntimeError) as e:
        return {"error": str(e)}

    if remote is None:
        local = get_local_release()
        return {"update_available": False, "current": local["name"] if local else None, "no_releases": True}

    local = get_local_release()
    if local is None:
        _set_local_release(remote["tag"], remote["name"])
        return {"update_available": False, "current": remote["name"]}

    return {
        "update_available": local["tag"] != remote["tag"],
        "current": local["name"],
        "latest": remote["name"],
        "latest_tag": remote["tag"],
        "body": remote["body"],
        "date": remote["date"],
    }


def _safe_extract_zip(archive_bytes: bytes, destination: str) -> None:
    """Extract only normal relative files/directories and reject Zip Slip paths."""
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
        root = os.path.abspath(destination)
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.startswith("/"):
                raise RuntimeError("Unsafe path in update archive.")
            path = PurePosixPath(name)
            if any(part in {"", ".", ".."} for part in path.parts):
                raise RuntimeError("Unsafe path in update archive.")
            if any(":" in part for part in path.parts):
                raise RuntimeError("Unsafe drive-qualified path in update archive.")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise RuntimeError("Symlinks are not allowed in update archives.")
            target = os.path.abspath(os.path.join(root, *path.parts))
            if target != root and not target.startswith(root + os.sep):
                raise RuntimeError("Unsafe path in update archive.")
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info, "r") as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1 << 16)

def apply_update(update: Callable[[Optional[float], str], None]) -> dict:
    """Downloads the latest release's source zip and syncs it into the
    launcher root (see EXCLUDED_FROM_SYNC for what's left alone). Dependency
    installation is intentionally not performed by the self-updater.
    `update(progress, detail)` is called as work proceeds, matching the
    TaskManager work_fn convention (progress is 0..1, or None while
    indeterminate). Returns {"tag", "name"} on success; raises on failure
    so the caller's task ends up in the "error" state."""
    if is_frozen():
        raise RuntimeError("Auto-update isn't available for this build yet.")

    remote = get_remote_release()
    if remote is None:
        raise RuntimeError("No published release found.")

    update(0, "Downloading update...")
    req = urllib.request.Request(remote["zip_url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        final_url = resp.geturl()
        if not is_https_host(final_url, ALLOWED_ZIP_HOSTS):
            raise RuntimeError("GitHub redirected the update to an unexpected host.")
        total = resp.length or 0
        if total and total > MAX_UPDATE_ARCHIVE_BYTES:
            raise RuntimeError("Update archive is unexpectedly large.")
        chunks = []
        read = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            read += len(chunk)
            if read > MAX_UPDATE_ARCHIVE_BYTES:
                raise RuntimeError("Update archive exceeds the safety limit.")
            chunks.append(chunk)
            if total:
                update(min(0.55, 0.55 * read / total), "Downloading update...")
            else:
                update(None, "Downloading update...")
        archive_bytes = b"".join(chunks)

    update(0.6, "Extracting...")
    root = _launcher_root()
    with tempfile.TemporaryDirectory(prefix="glauncher_update_") as tmp:
        _safe_extract_zip(archive_bytes, tmp)

        # GitHub's release/zipball archives contain one top-level folder,
        # e.g. "lazvom-GLauncher-abc1234".
        entries = os.listdir(tmp)
        if len(entries) != 1:
            raise RuntimeError("Unexpected archive layout from GitHub.")
        extracted_root = os.path.join(tmp, entries[0])

        update(0.65, "Applying update...")
        # Sync every top-level entry the release ships, not a fixed list -
        # so a release that adds a brand new file/folder installs it here
        # automatically, with no code change needed to recognise it.
        for name in os.listdir(extracted_root):
            if name in EXCLUDED_FROM_SYNC:
                continue
            src = os.path.join(extracted_root, name)
            dest = os.path.join(root, name)
            from .security import ensure_within_directory
            ensure_within_directory(root, dest)
            if os.path.isdir(src):
                if os.path.exists(dest):
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(src, dest)
            else:
                os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
                shutil.copy2(src, dest)

    # Do not run pip against files that just arrived over the network.
    # Dependencies must be installed separately from the trusted build process.
    _set_local_release(remote["tag"], remote["name"])
    update(1.0, "Update installed")
    return {"tag": remote["tag"], "name": remote["name"]}


def restart_app() -> None:
    """Relaunches the same executable/script with the same arguments and
    ends this process. Call after apply_update() succeeds so the freshly
    copied files actually take effect."""
    python = sys.executable
    args = [python] + sys.argv
    os.execv(python, args)
