#!/usr/bin/env python3
"""
GLauncher - a custom Minecraft launcher.

The UI is a real HTML/CSS/JS frontend (web/) running in a native window via
pywebview, built around Apple's fluid-interface design principles: genuine
glass materials (backdrop-filter), critically-damped spring motion, 1:1
gesture tracking on the draggable sheets, and size-aware typography. None of
that is possible in a native Tk toolkit, which is why the UI lives here
instead - but the actual engine (core/: installing vanilla/Fabric/Forge/
Quilt/NeoForge, Modrinth content, accounts, background tasks) is completely
unchanged from before.

Run with:  python main.py
"""
import os

import webview

from api import Api
from core import winchrome

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def main():
    api = Api()
    window = webview.create_window(
        "GLauncher",
        os.path.join(WEB_DIR, "index.html"),
        js_api=api,
        width=1180,
        height=760,
        min_size=(980, 640),
        background_color="#0a0c12",
        text_select=True,
        # Keep a normal WinForms window so Windows retains its native window
        # manager integration. core/winchrome.py moves the client area into
        # the native frame and suppresses the visible caption/buttons.
        frameless=False,
        easy_drag=False,
    )
    api._window = window
    # pywebview 5.x routes .pywebview-drag-region through Window.move(),
    # whose WinForms backend passes None for SetWindowPos dimensions. Replace
    # only this window's move() with a real native caption drag.
    # Install the custom non-client frame before WinForms calls Show().
    # pywebview's before_show Event is raised immediately after the Form is
    # constructed; the callback is marshalled back to the Form's UI thread
    # inside core/winchrome.py so WM_NCCALCSIZE/WM_NCHITTEST are active before
    # the first frame is painted.
    window.events.before_show += lambda: winchrome.install_native_chrome_on_ui_thread(window)
    webview.start()


if __name__ == "__main__":
    main()
