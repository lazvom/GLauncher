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
requirements.txt is also re-installed after syncing, so a release that
adds a new dependency gets it pulled in automatically too, not just the
new .py files that import it.

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
import subprocess
import sys
import tempfile
import urllib.request
import urllib.error
import zipfile
from typing import Callable, Optional

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
        raise
    return {
        "tag": data["tag_name"],
        "name": data.get("name") or data["tag_name"],
        "body": data.get("body") or "",
        "date": data.get("published_at", ""),
        "zip_url": data["zipball_url"],
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
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
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


def apply_update(update: Callable[[Optional[float], str], None]) -> dict:
    """Downloads the latest release's source zip and syncs it into the
    launcher root (see EXCLUDED_FROM_SYNC for what's left alone), then
    installs requirements.txt again so any new dependency the update
    needs is pulled in too - not just new/changed source files.
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
        total = resp.length or 0
        chunks = []
        read = 0
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            chunks.append(chunk)
            read += len(chunk)
            if total:
                update(min(0.55, 0.55 * read / total), "Downloading update...")
            else:
                update(None, "Downloading update...")
        archive_bytes = b"".join(chunks)

    update(0.6, "Extracting...")
    root = _launcher_root()
    with tempfile.TemporaryDirectory(prefix="glauncher_update_") as tmp:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            zf.extractall(tmp)

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
            if os.path.isdir(src):
                if os.path.exists(dest):
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(src, dest)
            else:
                os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
                shutil.copy2(src, dest)

    _install_requirements(root, update)

    _set_local_release(remote["tag"], remote["name"])
    update(1.0, "Update installed")
    return {"tag": remote["tag"], "name": remote["name"]}


def _install_requirements(root: str, update: Callable[[Optional[float], str], None]) -> None:
    """Runs `pip install -r requirements.txt` with the *current*
    interpreter (sys.executable) after syncing files, so a release that
    adds a new dependency doesn't just get skipped until someone thinks
    to reinstall it by hand. sys.executable is correct whether that's a
    system Python (dev/source runs) or python-embed's python.exe (when
    this process was spawned by the launcher.py stub) - either way it's
    the interpreter main.py is actually running under right now."""
    req_file = os.path.join(root, "requirements.txt")
    if not os.path.isfile(req_file):
        return
    update(0.85, "Installing dependencies...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", req_file, "--no-warn-script-location"],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError as e:
        raise RuntimeError(f"Couldn't run pip to install dependencies: {e}") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Installing dependencies timed out.") from e
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or e.stdout or "").strip().splitlines()[-1:] or [str(e)]
        raise RuntimeError(f"Installing dependencies failed: {detail[0]}") from e


def restart_app() -> None:
    """Relaunches the same executable/script with the same arguments and
    ends this process. Call after apply_update() succeeds so the freshly
    copied files actually take effect."""
    python = sys.executable
    args = [python] + sys.argv
    os.execv(python, args)
