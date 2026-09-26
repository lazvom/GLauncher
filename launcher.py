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

Where it looks for Python, in order:
  1. <this exe's folder>/python-embed/  - a Python "embeddable" distribution
     you place next to the exe (see scripts/setup_python_embed.ps1, or the
     Packaging section in README.md, for how to set that up once).
  2. A system Python already on PATH (mainly useful when running this file
     directly during development, unfrozen).

If neither is found, it shows a plain message box (no console window is
assumed, since this is normally built with auto-py-to-exe in
"window based" mode) and exits instead of silently doing nothing.
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


def _find_python(base: str) -> str | None:
    embed_dir = os.path.join(base, "python-embed")
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
    main_py = os.path.join(base, "main.py")

    if not os.path.isfile(main_py):
        _show_error(
            "main.py wasn't found next to GLauncher.exe.\n\n"
            "This launcher expects to sit alongside main.py, api.py, core/ "
            "and web/ - the actual app source - not to contain it."
        )
        return 1

    python = _find_python(base)
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
    proc = subprocess.Popen([python, main_py, *sys.argv[1:]], cwd=base, creationflags=creationflags)
    return proc.wait()


if __name__ == "__main__":
    sys.exit(main())
