"""
Tiny stub meant to be frozen with auto-py-to-exe / PyInstaller instead of
main.py itself.

The problem this solves: a frozen main.py can't self-update, because
core/updater.py overwrites .py source files on disk, and a compiled exe
doesn't re-read those - it already has everything baked in. So instead of
freezing the actual app, we freeze this tiny launcher, which does nothing
but find a real Python interpreter and run main.py *as a normal script*.
Inside that process, sys.frozen is False, so the updater behaves exactly
like a source checkout: it can check GitHub, download a new release, and
overwrite main.py/core/web in place - the next time this stub runs it, it
picks up the new code automatically. Nothing about core/updater.py needs
to know this stub exists.

Where it looks for main.py (and python-embed/), in order:
  1. Directly next to the exe - the recommended layout (see the
     Packaging section in README.md): build with auto-py-to-exe pointed
     at *only* this file, with no "Add Files"/"Add Folder" entries, then
     copy main.py, api.py, core/, web/, requirements.txt and python-embed/
     into the output folder next to the exe yourself, afterwards.
  2. Inside an _internal/ folder next to the exe. This is a fallback for
     when main.py (and friends) were instead added to auto-py-to-exe as
     "Additional Files" - PyInstaller 6+'s --onedir builds put anything
     bundled that way inside _internal/ rather than leaving it beside the
     exe, which is an easy layout to end up with by accident. It still
     works from there, but see the README note above: it means every
     update also lands inside _internal/ instead of next to the exe,
     which is a bit unusual to browse to by hand later.

Python itself (python-embed/) is looked for next to the exe first, then
inside whichever of the two locations above main.py was actually found in,
then finally a system Python on PATH.

If neither main.py nor a Python interpreter is found, this shows a plain
message box (no console window is assumed, since this is normally built
with auto-py-to-exe in "window based" mode) and exits instead of silently
doing nothing.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def _base_dir() -> str:
    """Folder the stub itself lives in - next to the frozen .exe, or next
    to this .py file when run unfrozen during development."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _find_app_root(base: str) -> str | None:
    """Where main.py actually lives: directly in `base`, or inside a
    PyInstaller-generated `base/_internal/` (see the module docstring for
    why that happens). Returns None if it isn't in either place."""
    if os.path.isfile(os.path.join(base, "main.py")):
        return base
    internal = os.path.join(base, "_internal")
    if os.path.isfile(os.path.join(internal, "main.py")):
        return internal
    return None


def _find_python(*search_dirs: str) -> str | None:
    for d in search_dirs:
        embed_dir = os.path.join(d, "python-embed")
        if os.name == "nt":
            candidates = [
                os.path.join(embed_dir, "pythonw.exe"),  # no console flash
                os.path.join(embed_dir, "python.exe"),
            ]
        else:
            candidates = [
                os.path.join(embed_dir, "bin", "python3"),
                os.path.join(embed_dir, "bin", "python"),
            ]
        for c in candidates:
            if os.path.isfile(c):
                return c

    # Fall back to whatever Python is already on PATH (dev runs, or a
    # user who'd rather rely on a system install than an embedded one).
    for name in ("python3", "python", "py"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _show_error(message: str) -> None:
    print(message, file=sys.stderr)
    try:
        import tkinter
        from tkinter import messagebox

        root = tkinter.Tk()
        root.withdraw()
        messagebox.showerror("GLauncher", message)
        root.destroy()
    except Exception:
        pass  # tkinter unavailable - stderr above is the best we can do


def main() -> int:
    base = _base_dir()
    root = _find_app_root(base)

    if root is None:
        _show_error(
            "main.py wasn't found next to GLauncher.exe (or in an "
            "_internal/ folder next to it).\n\n"
            "This launcher expects to sit alongside main.py, api.py, core/ "
            "and web/ - the actual app source - not to contain it. If you "
            "added those as \"Additional Files\" in auto-py-to-exe, try "
            "building with just this file instead, and copy the source "
            "files next to the built exe by hand afterwards."
        )
        return 1
    main_py = os.path.join(root, "main.py")

    # python-embed/ is expected next to the exe; if main.py ended up inside
    # _internal/, also check there, since anything bundled alongside it
    # would've landed in the same place.
    python = _find_python(base, root)
    if not python:
        _show_error(
            "No Python interpreter was found.\n\n"
            "Expected an embedded Python at python-embed/ next to "
            "GLauncher.exe (see scripts/setup_python_embed.ps1), or a "
            "Python install on PATH."
        )
        return 1

    # Run main.py as a normal, unfrozen script. This process, not the
    # stub, is what the in-app updater checks/replaces/restarts - the
    # stub's only job is finding an interpreter and getting out of the way.
    creationflags = 0
    if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        creationflags = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen([python, main_py, *sys.argv[1:]], cwd=root, creationflags=creationflags)
    return proc.wait()


if __name__ == "__main__":
    sys.exit(main())
