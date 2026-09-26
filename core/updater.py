"""
Self-update from the GLauncher GitHub repository.

There are no GitHub Releases yet (see README - the installer/portable-zip
release flow is still planned), so this tracks the tip of `main` directly:
it compares the latest commit SHA on the branch against the SHA we last
updated to, and - when the two differ - downloads the branch as a zipball,
and overwrites just the source files (main.py, api.py, core/, web/, ...)
in place, leaving the data/ directory (accounts, instances, settings)
completely untouched.

This only makes sense for a "run from source" checkout. When frozen (e.g. a
future PyInstaller .exe build), the running executable is a compiled binary
that new .py files wouldn't affect, so update checks there are skipped -
frozen builds should get their own installer/release-based update path
later instead.
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

from .instances import _launcher_root

REPO = "lazvom/GLauncher"
BRANCH = "main"
API_COMMIT_URL = f"https://api.github.com/repos/{REPO}/commits/{BRANCH}"
ZIPBALL_URL = f"https://codeload.github.com/{REPO}/zip/refs/heads/{BRANCH}"
USER_AGENT = "GLauncher-updater"

# Top-level entries that make up the app's source; everything else in the
# launcher root (data/, settings.json, __pycache__, this version file, any
# user-added files) is left alone.
TRACKED_PATHS = ["main.py", "api.py", "requirements.txt", "README.md", "core", "web"]

VERSION_FILENAME = ".glauncher_version"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _version_file() -> str:
    return os.path.join(_launcher_root(), VERSION_FILENAME)


def get_local_commit() -> Optional[str]:
    try:
        with open(_version_file(), "r", encoding="utf-8") as f:
            return json.load(f).get("sha")
    except Exception:
        return None


def _set_local_commit(sha: str) -> None:
    try:
        with open(_version_file(), "w", encoding="utf-8") as f:
            json.dump({"sha": sha}, f)
    except OSError:
        pass


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_remote_commit() -> dict:
    """Latest commit on the tracked branch: {"sha", "message", "date"}.
    Raises on network/API failure - callers should catch and surface it."""
    data = _get_json(API_COMMIT_URL)
    commit = data.get("commit", {})
    message = (commit.get("message") or "").split("\n", 1)[0]  # first line only
    date = (commit.get("committer") or commit.get("author") or {}).get("date", "")
    return {"sha": data["sha"], "message": message, "date": date}


def check_for_update() -> dict:
    """Returns a dict describing update status, or {"error": ...}. Never
    raises. If this is the very first check (no local commit recorded yet),
    the current remote tip is adopted as the baseline silently, rather than
    reporting an "update" for a version that may already be what's on disk."""
    if is_frozen():
        return {"update_available": False, "frozen": True}
    try:
        remote = get_remote_commit()
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
        return {"error": str(e)}

    local = get_local_commit()
    if local is None:
        _set_local_commit(remote["sha"])
        return {"update_available": False, "current": remote["sha"][:7]}

    return {
        "update_available": local != remote["sha"],
        "current": local[:7],
        "latest": remote["sha"][:7],
        "latest_full": remote["sha"],
        "message": remote["message"],
        "date": remote["date"],
    }


def apply_update(update: Callable[[Optional[float], str], None]) -> dict:
    """Downloads the branch zipball and replaces TRACKED_PATHS in the
    launcher root with their contents. `update(progress, detail)` is called
    as work proceeds, matching the TaskManager work_fn convention (progress
    is 0..1, or None while indeterminate). Returns {"sha": ...} on success;
    raises on failure so the caller's task ends up in the "error" state."""
    if is_frozen():
        raise RuntimeError("Auto-update isn't available for this build yet.")

    remote = get_remote_commit()

    update(0, "Downloading update...")
    req = urllib.request.Request(ZIPBALL_URL, headers={"User-Agent": USER_AGENT})
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
                update(min(0.7, 0.7 * read / total), "Downloading update...")
            else:
                update(None, "Downloading update...")
        archive_bytes = b"".join(chunks)

    update(0.75, "Extracting...")
    root = _launcher_root()
    with tempfile.TemporaryDirectory(prefix="glauncher_update_") as tmp:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            zf.extractall(tmp)

        # GitHub zipballs contain one top-level folder, e.g. "GLauncher-main".
        entries = os.listdir(tmp)
        if len(entries) != 1:
            raise RuntimeError("Unexpected archive layout from GitHub.")
        extracted_root = os.path.join(tmp, entries[0])

        update(0.85, "Applying update...")
        for name in TRACKED_PATHS:
            src = os.path.join(extracted_root, name)
            if not os.path.exists(src):
                continue
            dest = os.path.join(root, name)
            if os.path.isdir(src):
                if os.path.exists(dest):
                    shutil.rmtree(dest, ignore_errors=True)
                shutil.copytree(src, dest)
            else:
                os.makedirs(os.path.dirname(dest) or root, exist_ok=True)
                shutil.copy2(src, dest)

    _set_local_commit(remote["sha"])
    update(1.0, "Update installed")
    return {"sha": remote["sha"]}


def restart_app() -> None:
    """Relaunches the same executable/script with the same arguments and
    ends this process. Call after apply_update() succeeds so the freshly
    copied files actually take effect."""
    python = sys.executable
    args = [python] + sys.argv
    os.execv(python, args)
