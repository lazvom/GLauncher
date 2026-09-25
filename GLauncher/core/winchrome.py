"""
Native Windows window-chrome control for the frameless window.

pywebview's frameless=True makes the window a plain WS_POPUP: no caption, no
border, no system menu. That's *too* frameless - Windows only gives a window
its native minimize/maximize/restore animations, Aero Snap (drag to the top
of the screen to maximize, drag to a side to half-snap, Win+arrow, shake to
minimize others), a live taskbar thumbnail, and maximize that respects the
taskbar automatically when the window is a "real" framed window under the
hood. A WS_POPUP window gets none of that for free.

The technique real apps with a custom title bar use (this is what Chromium,
VS Code, WPF's WindowChrome, and - going by the request that led here -
Modrinth's own launcher all do) is the opposite of what frameless=True does:
keep the window as a genuine WS_CAPTION | WS_THICKFRAME window so Windows
treats it as completely normal, and only hide the *visible* caption/border by
intercepting WM_NCCALCSIZE. Combined with a WM_NCHITTEST override so the
custom HTML title bar reports itself as the caption (HTCAPTION) and its
edges report as resize handles, this gets every native behavior "for real"
instead of reimplemented: the actual DWM animations, the actual Aero Snap,
the actual taskbar integration - because the OS is doing it, not us.

WM_GETMINMAXINFO is still handled too, belt-and-suspenders: it's not strictly
needed once the window has a real frame, but costs nothing to keep and
guards against an OS/DPI edge case that can otherwise crop a maximized
borderless-look window by a pixel or two at the work-area edge.

Everything here is a no-op off Windows.
"""
from __future__ import annotations

import sys

IS_WINDOWS = sys.platform == "win32"

SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
WM_CLOSE = 0x0010
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
WM_GETMINMAXINFO = 0x0024
WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
GWL_STYLE = -16
GWLP_WNDPROC = -4
MONITOR_DEFAULTTONEAREST = 2

# DWM non-client rendering control. Disabling DWM NC rendering prevents the
# real caption from being painted while WS_CAPTION/WS_THICKFRAME remain on
# the window, so Windows still treats it as a normal framed window.
DWMWA_NCRENDERING_POLICY = 2
DWMNCRP_DISABLED = 1

WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_THICKFRAME = 0x00040000
WS_CAPTION = 0x00C00000
WS_SYSMENU = 0x00080000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

HTCLIENT = 1
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17

RESIZE_BORDER = 8   # px - how close to an edge still counts as a resize handle
TITLEBAR_HEIGHT = 34  # px - must match .titlebar's height in style.css
TITLEBAR_CONTROLS_WIDTH = 3 * 46  # px - the 3 buttons' width in style.css, excluded from dragging

_wndproc_refs = []  # ctypes callbacks must be kept alive for the window's lifetime
_user32 = None  # lazily-configured ctypes.windll.user32, argtypes set exactly once
_mouse_operation_lock = None
_mouse_operation_active = False
VK_LBUTTON = 0x01
SWP_NOACTIVATE = 0x0010


def _get_user32():
    """ctypes.windll.user32 with argtypes/restype set on every function this
    module calls. Every one of these takes a window handle or pointer that
    can be a large 64-bit value, and leaving ctypes to guess the argument
    type from a bare Python int treats it as a 32-bit C int - which either
    overflows outright (as an unconfigured CallWindowProcW once did, breaking
    every message the hook forwarded and leaving the window stuck) or
    silently truncates the value. Configured once here rather than ad hoc
    at each call site, so nothing that calls into user32 can skip it."""
    global _user32
    if _user32 is not None:
        return _user32
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.ReleaseCapture.argtypes = []
    user32.ReleaseCapture.restype = wintypes.BOOL
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_void_p
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    user32.SetWindowLongPtrW.restype = ctypes.c_void_p
    user32.CallWindowProcW.argtypes = [
        ctypes.c_void_p, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM
    ]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t  # LRESULT: pointer-sized, not c_long
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.ScreenToClient.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ScreenToClient.restype = wintypes.BOOL
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    _user32 = user32
    return user32


def _hwnd(window):
    """The real native window handle behind a pywebview Window, or None if
    that isn't available yet (too early) or we're not on Windows.
    ToInt64(), not ToInt32() - a 64-bit process's window handle can be
    outside the 32-bit range, and truncating it silently corrupts it rather
    than raising anything, which is a much worse failure mode."""
    if not IS_WINDOWS or window is None:
        return None
    try:
        return window.native.Handle.ToInt64()
    except Exception:
        return None


def _disable_dwm_nc_rendering(hwnd_):
    """Disable DWM painting of the native non-client caption/frame.

    We keep the native window styles for Windows window-manager behavior, but
    the visible caption and border must be rendered by our HTML client area.
    DWM's non-client rendering can otherwise remain visible even when
    WM_NCCALCSIZE makes the client area cover the full window.
    """
    if not IS_WINDOWS or not hwnd_:
        return

    import ctypes
    from ctypes import wintypes

    dwmapi = ctypes.WinDLL('dwmapi', use_last_error=True)
    fn = dwmapi.DwmSetWindowAttribute
    fn.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    fn.restype = ctypes.c_long

    policy = ctypes.c_int(DWMNCRP_DISABLED)
    hr = fn(hwnd_, DWMWA_NCRENDERING_POLICY, ctypes.byref(policy), ctypes.sizeof(policy))
    if hr < 0:
        raise OSError(f'DwmSetWindowAttribute(DWMWA_NCRENDERING_POLICY) failed: HRESULT 0x{hr & 0xffffffff:08X}')


def _hit_test(user32, hwnd_, lparam):
    """WM_NCHITTEST: reports the titlebar's drag strip as HTCAPTION (so
    Windows drags/Aero-Snaps it as a real caption) and the outer edges as
    resize handles, since removing the visible frame in WM_NCCALCSIZE below
    also removes the OS's own hit-testing for both. None means "let the
    default window proc decide" (ordinary client-area content)."""
    import ctypes
    from ctypes import wintypes

    x = ctypes.c_short(lparam & 0xFFFF).value
    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
    pt = wintypes.POINT(x, y)
    user32.ScreenToClient(hwnd_, ctypes.byref(pt))
    rect = wintypes.RECT()
    if not user32.GetClientRect(hwnd_, ctypes.byref(rect)):
        return None
    w, h = rect.right, rect.bottom
    cx, cy = pt.x, pt.y

    left, right = cx < RESIZE_BORDER, cx > w - RESIZE_BORDER
    top, bottom = cy < RESIZE_BORDER, cy > h - RESIZE_BORDER
    if top and left:
        return HTTOPLEFT
    if top and right:
        return HTTOPRIGHT
    if bottom and left:
        return HTBOTTOMLEFT
    if bottom and right:
        return HTBOTTOMRIGHT
    if left:
        return HTLEFT
    if right:
        return HTRIGHT
    if top:
        return HTTOP
    if bottom:
        return HTBOTTOM
    if cy < TITLEBAR_HEIGHT and cx < w - TITLEBAR_CONTROLS_WIDTH:
        return HTCAPTION
    return None


def install_native_chrome(window):
    """Call once, right after the window is shown. Restores the window's
    real caption/frame styles (for native animations, Aero Snap, and correct
    taskbar behavior) while keeping it visually borderless, and wires up
    hit-testing so the HTML title bar drags/resizes/snaps exactly like a
    real one. Safe to call on non-Windows, or if anything here fails - it
    just won't do anything."""
    hwnd = _hwnd(window)
    if not hwnd:
        return
    import ctypes
    from ctypes import wintypes
    import traceback

    user32 = _get_user32()
    original_style = user32.GetWindowLongPtrW(hwnd, GWL_STYLE) or 0

    try:
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MINMAXINFO(ctypes.Structure):
            _fields_ = [
                ("ptReserved", POINT),
                ("ptMaxSize", POINT),
                ("ptMaxPosition", POINT),
                ("ptMinTrackSize", POINT),
                ("ptMaxTrackSize", POINT),
            ]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM
        )

        old_proc = user32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
        if not old_proc:
            raise RuntimeError("GetWindowLongPtrW(GWLP_WNDPROC) returned NULL")

        def wndproc(hwnd_, msg, wparam, lparam):
            if msg == WM_NCCALCSIZE:
                if wparam:
                    return 0  # client area = the whole window: no visible caption/border
            elif msg == WM_NCHITTEST:
                try:
                    hit = _hit_test(user32, hwnd_, lparam)
                    if hit is not None:
                        return hit
                except Exception:
                    traceback.print_exc()
            elif msg == WM_GETMINMAXINFO:
                try:
                    info = ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents
                    hmon = user32.MonitorFromWindow(hwnd_, MONITOR_DEFAULTTONEAREST)
                    mi = MONITORINFO()
                    mi.cbSize = ctypes.sizeof(MONITORINFO)
                    if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                        work, mon = mi.rcWork, mi.rcMonitor
                        info.ptMaxPosition.x = work.left - mon.left
                        info.ptMaxPosition.y = work.top - mon.top
                        info.ptMaxSize.x = work.right - work.left
                        info.ptMaxSize.y = work.bottom - work.top
                        info.ptMaxTrackSize.x = work.right - work.left
                        info.ptMaxTrackSize.y = work.bottom - work.top
                except Exception:
                    traceback.print_exc()
            try:
                return user32.CallWindowProcW(old_proc, hwnd_, msg, wparam, lparam)
            except Exception:
                traceback.print_exc()
                return 0

        # Install the message hook FIRST, before touching GWL_STYLE below.
        # SWP_FRAMECHANGED (needed to make the style change take effect)
        # triggers an immediate WM_NCCALCSIZE - if that happens before this
        # hook exists, the *original* window proc handles it and computes a
        # normal caption+border inset, so the real native title bar actually
        # flashes in (and stays, since nothing later ever recalculates it).
        callback = WNDPROC(wndproc)
        _wndproc_refs.append(callback)  # prevent garbage collection
        if not user32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(callback, ctypes.c_void_p)):
            raise RuntimeError("SetWindowLongPtrW(GWLP_WNDPROC) failed")

        # Keep the real framed-window styles for native Windows behavior,
        # but tell DWM not to paint its visible non-client caption/frame.
        # The HTML titlebar is then the visible frame while Windows still
        # owns moving, snapping, resizing, minimize/maximize, and taskbar
        # integration.
        style = original_style | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
        user32.SetWindowLongPtrW(hwnd, GWL_STYLE, style)
        _disable_dwm_nc_rendering(hwnd)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    except Exception:
        # Don't leave the window with WS_CAPTION added but no hook to hide
        # it (a real native title bar with no working custom drag, worse
        # than either state alone) - put the style back exactly as it was
        # and fall back to pywebview's own frameless/drag-region handling.
        traceback.print_exc()
        try:
            user32.SetWindowLongPtrW(hwnd, GWL_STYLE, original_style)
            user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        except Exception:
            traceback.print_exc()


def install_native_chrome_on_ui_thread(window):
    """Install the custom frame on the WinForms UI thread.

    pywebview's Event callbacks normally run on a worker thread. WinForms
    controls must be manipulated from the thread that created them, so route
    the native-frame setup through Control.Invoke when possible.
    """
    if not IS_WINDOWS or window is None:
        return

    form = getattr(window, 'native', None)
    if form is None:
        return

    try:
        from System import Func, Type

        def _install():
            install_native_chrome(window)
            return None

        # before_show is raised from pywebview's create thread, which is the
        # same STA thread that owns the Form. In case pywebview changes that
        # ordering, Invoke marshals safely to the owning UI thread.
        if getattr(form, 'InvokeRequired', False):
            form.Invoke(Func[Type](_install))
        else:
            _install()
    except Exception:
        # ctypes/Win32 operations can still be used as a last resort if the
        # pythonnet delegate layer isn't available in a particular runtime.
        install_native_chrome(window)


def install_pywebview_drag_compat(window):
    """Deprecated compatibility hook.

    GLauncher no longer uses pywebview's ``pywebview-drag-region`` because
    that path calls ``Window.move``/``SetWindowPos`` from the WebView bridge.
    The HTML titlebar now calls ``window_start_drag`` explicitly, which starts
    a genuine Win32 caption drag. Kept as a no-op so older callers do not fail.
    """
    return None


def _start_mouse_operation(window, mode, edge=None):
    """Start a small background Win32 mouse tracker for move/resize.

    WebView2 owns the visible client area, so sending WM_NCHITTEST/WM_NCLBUTTONDOWN
    to the top-level window is unreliable when the original mouse message began in
    the WebView child.  Instead we take a snapshot of the cursor and window rectangle
    and let Win32 SetWindowPos follow the mouse until the left button is released.
    This keeps the operation limited to the explicit titlebar/resize handles and,
    importantly, never calls pywebview Window.move().
    """
    global _mouse_operation_lock, _mouse_operation_active
    hwnd = _hwnd(window)
    if not hwnd:
        return False

    import ctypes
    import threading
    import time
    from ctypes import wintypes

    if _mouse_operation_lock is None:
        _mouse_operation_lock = threading.Lock()
    if not _mouse_operation_lock.acquire(blocking=False):
        return False

    try:
        if _mouse_operation_active:
            return False
        _mouse_operation_active = True

        user32 = _get_user32()
        cursor = wintypes.POINT()
        rect = wintypes.RECT()
        if not user32.GetCursorPos(ctypes.byref(cursor)) or not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            _mouse_operation_active = False
            return False

        start_x, start_y = int(cursor.x), int(cursor.y)
        start_left, start_top = int(rect.left), int(rect.top)
        start_right, start_bottom = int(rect.right), int(rect.bottom)
        start_width = max(1, start_right - start_left)
        start_height = max(1, start_bottom - start_top)

        if mode == 'resize':
            edge = str(edge or '').lower()
            if edge not in {
                'left', 'right', 'top', 'bottom',
                'top-left', 'top-right', 'bottom-left', 'bottom-right'
            }:
                _mouse_operation_active = False
                return False

            # Resize handles are only meaningful while restored.  A maximized
            # window is restored first, matching normal Windows frame behavior.
            if user32.IsZoomed(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
                # The restored rectangle may differ from the maximized one.
                user32.GetWindowRect(hwnd, ctypes.byref(rect))
                start_left, start_top = int(rect.left), int(rect.top)
                start_right, start_bottom = int(rect.right), int(rect.bottom)
                start_width = max(1, start_right - start_left)
                start_height = max(1, start_bottom - start_top)
                user32.GetCursorPos(ctypes.byref(cursor))
                start_x, start_y = int(cursor.x), int(cursor.y)

        # Match the create_window(min_size=...) constraint without relying on
        # WinForms' non-client hit-testing.
        min_w, min_h = 980, 640

        def track():
            global _mouse_operation_active
            try:
                # Give the mousedown handler time to return to WebView2 before
                # the first SetWindowPos call.
                time.sleep(0.01)
                while user32.GetAsyncKeyState(VK_LBUTTON) & 0x8000:
                    pt = wintypes.POINT()
                    if not user32.GetCursorPos(ctypes.byref(pt)):
                        break
                    x, y = int(pt.x), int(pt.y)
                    dx, dy = x - start_x, y - start_y

                    if mode == 'move':
                        new_left = start_left + dx
                        new_top = start_top + dy
                        user32.SetWindowPos(
                            hwnd, 0, new_left, new_top,
                            start_width, start_height,
                            SWP_NOZORDER | SWP_NOACTIVATE,
                        )
                    else:
                        left, top = start_left, start_top
                        right, bottom = start_right, start_bottom

                        if 'left' in edge:
                            left = start_left + dx
                        if 'right' in edge:
                            right = start_right + dx
                        if 'top' in edge:
                            top = start_top + dy
                        if 'bottom' in edge:
                            bottom = start_bottom + dy

                        width = right - left
                        height = bottom - top
                        if width < min_w:
                            if 'left' in edge and 'right' not in edge:
                                left = right - min_w
                            else:
                                right = left + min_w
                        if height < min_h:
                            if 'top' in edge and 'bottom' not in edge:
                                top = bottom - min_h
                            else:
                                bottom = top + min_h

                        user32.SetWindowPos(
                            hwnd, 0,
                            int(left), int(top),
                            int(right - left), int(bottom - top),
                            SWP_NOZORDER | SWP_NOACTIVATE,
                        )

                    time.sleep(1 / 120)
            finally:
                _mouse_operation_active = False
                try:
                    _mouse_operation_lock.release()
                except Exception:
                    pass

        threading.Thread(target=track, name='glauncher-window-operation', daemon=True).start()
        return True
    except Exception:
        _mouse_operation_active = False
        try:
            _mouse_operation_lock.release()
        except Exception:
            pass
        return False


def start_resize(window, edge):
    """Resize only when one of the explicit HTML resize handles is pressed."""
    return _start_mouse_operation(window, 'resize', edge)


def minimize(window):
    hwnd = _hwnd(window)
    if hwnd:
        _get_user32().ShowWindow(hwnd, SW_MINIMIZE)
    elif window:
        window.minimize()


def start_drag(window):
    """Move only from the explicit custom HTML titlebar strip.

    The move is implemented with SetWindowPos tracking rather than pywebview's
    Window.move(), so the WebView never turns normal client-area clicks into a drag.
    """
    return _start_mouse_operation(window, 'move')


def toggle_maximize(window) -> bool:
    """Maximizes or restores via the real Win32 state (queried live with
    IsZoomed, not a flag we track ourselves) so it stays correct even if the
    window was maximized some other way, like Aero Snap or a Windows
    shortcut. Returns the new maximized state."""
    hwnd = _hwnd(window)
    if hwnd:
        user32 = _get_user32()
        was_maximized = bool(user32.IsZoomed(hwnd))
        user32.ShowWindow(hwnd, SW_RESTORE if was_maximized else SW_MAXIMIZE)
        return not was_maximized
    elif window:
        if window.maximized:
            window.restore()
            return False
        window.maximize()
        return True
    return False


def is_maximized(window) -> bool:
    hwnd = _hwnd(window)
    if hwnd:
        return bool(_get_user32().IsZoomed(hwnd))
    return bool(window and window.maximized)


def close(window):
    hwnd = _hwnd(window)
    if hwnd:
        _get_user32().PostMessageW(hwnd, WM_CLOSE, 0, 0)
    elif window:
        window.destroy()
