# winutil.py — pure-ctypes Win32 helpers for the black-box vision driver.
#
# Everything here targets a DIFFERENT process (the app under test); we never
# touch app internals — this is the "hands and eyes" layer of the driver:
#   eyes: window discovery (by PID), window capture (PrintWindow w/ FULLCONTENT)
#   hands: WindowFromPoint + SendMessage click / WM_CHAR text (remote-control
#          proof, works without focus/foreground — same mechanism as the
#          in-process Win32MessageSimulator tier, see tests/wx_gui)
#
# Windows-only by design (this sandbox experiment is wxMSW targeted).

import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --- constants ---------------------------------------------------------------
PW_RENDERFULLCONTENT = 0x00000002  # PrintWindow flag: render GL/DWM content
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
WM_CHAR = 0x0102
WM_CLOSE = 0x0010
SMTO_NORMAL = 0x0000
SMTO_ABORTIFHUNG = 0x0002
SEND_TIMEOUT_MS = 3000
DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def _send_msg(hwnd: int, msg: int, wparam: int, lparam: int, timeout_ms: int = SEND_TIMEOUT_MS) -> None:
    """SendMessageW with a timeout so a hung/busy target can't wedge the driver."""
    result = ctypes.c_ulong()
    ok = user32.SendMessageTimeoutW(hwnd, msg, wparam, lparam,
                                    SMTO_NORMAL | SMTO_ABORTIFHUNG, timeout_ms, ctypes.byref(result))
    if not ok:
        # Timeout/aborted: not fatal for input injection (the app may be busy);
        # capture/assert layers will surface any real malfunction.
        print(f"[winutil] SendMessageTimeoutW(msg=0x{msg:x}) to hwnd 0x{hwnd:x} did not complete")

# Make OUR process per-monitor-v2 DPI aware so all rects/coordinates are in
# PHYSICAL pixels (matching what we capture and what we template-match against).
_process_dpi_aware = False


def make_dpi_aware() -> bool:
    """Set per-monitor-v2 DPI awareness for this process (idempotent)."""
    global _process_dpi_aware
    if _process_dpi_aware:
        return True
    try:
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
    except Exception:
        pass
    _process_dpi_aware = True
    return True


# --- window discovery --------------------------------------------------------

def _check_bool(result, func, args):
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
    return args


WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def enum_windows() -> list[tuple[int, int]]:
    """All top-level windows as (hwnd, pid), visible only."""
    results: list[tuple[int, int]] = []

    @WNDENUMPROC
    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        # Filter out zero-size windows (splash leftovers, hidden shells).
        rc = wt.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rc)):
            if rc.right - rc.left > 50 and rc.bottom - rc.top > 50:
                results.append((hwnd, pid.value))
        return True

    user32.EnumWindows(callback, 0)
    return results


def find_main_window(pid: int, timeout_s: float = 60.0, stable_s: float = 1.0) -> int:
    """Wait for the app's main window (top-level, visible, owned by `pid`).

    The main frame has an EMPTY title (custom BBLTopbar draws its own), so the
    only robust keying is pid + visible + non-trivial size. `stable_s` requires
    the window rect to stop changing before we accept it (startup resizing).
    """
    deadline = time.monotonic() + timeout_s
    last_rect = None
    stable_since = None
    while time.monotonic() < deadline:
        cands = [h for (h, p) in enum_windows() if p == pid]
        if cands:
            def area(h):
                l, t, r, b = _window_rect(h)
                return (r - l) * (b - t)

            # Largest window = the main frame (splash/tray windows are smaller).
            hwnd = max(cands, key=area)
            rc = _window_rect(hwnd)
            if rc == last_rect and (time.monotonic() - (stable_since or time.monotonic())) >= stable_s:
                return hwnd
            if rc != last_rect:
                last_rect = rc
                stable_since = time.monotonic()
        time.sleep(0.5)
    raise TimeoutError(f"no stable main window for pid {pid} within {timeout_s}s")


def _window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rc = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    return (rc.left, rc.top, rc.right, rc.bottom)


def window_rect(hwnd: int) -> tuple[int, int, int, int]:
    """(left, top, right, bottom) of the window in physical screen px."""
    return _window_rect(hwnd)


def get_dpi_for_window(hwnd: int) -> int:
    try:
        return user32.GetDpiForWindow(hwnd) or 96
    except Exception:
        return 96


# --- capture -----------------------------------------------------------------

class CaptureError(RuntimeError):
    pass


def capture_window(hwnd: int) -> "tuple[int, int, bytes]":
    """Capture a window with PrintWindow(PW_RENDERFULLCONTENT).

    Returns (width, height, bgra_pixels). PW_RENDERFULLCONTENT asks DWM to
    render the CURRENT visual tree — required for the OpenGL 3D canvas (plain
    BitBlt from a window DC returns black for GL areas) and correct for the
    WebView2 children. Works while the window is partially occluded.
    """
    rc = wt.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        raise CaptureError(f"GetClientRect failed: {ctypes.WinError(ctypes.get_last_error())}")
    w, h = rc.right - rc.left, rc.bottom - rc.top
    if w <= 0 or h <= 0:
        raise CaptureError(f"empty client area {w}x{h}")

    hdc_window = user32.GetWindowDC(hwnd)
    if not hdc_window:
        raise CaptureError("GetWindowDC failed")
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
        hbmp = gdi32.CreateCompatibleBitmap(hdc_window, w, h)
        old = gdi32.SelectObject(hdc_mem, hbmp)
        try:
            # PW_RENDERFULLCONTENT sends WM_PRINTCLIENT-equivalent through DWM;
            # result lands in our compatible bitmap as top-down BGRA.
            ok = user32.PrintWindow(hwnd, hdc_mem, PW_CLIENTONLY | PW_RENDERFULLCONTENT)
            if not ok:
                raise CaptureError(f"PrintWindow failed: {ctypes.WinError(ctypes.get_last_error())}")
            buf = ctypes.create_string_buffer(w * h * 4)
            # NOTE: GetDIBits must not use a DC with `hbmp` still selected —
            # pass the window DC instead.
            got = gdi32.GetDIBits(hdc_window, hbmp, 0, h, buf, ctypes.byref(_bitmapinfo(w, h)), 0)  # DIB_RGB_COLORS
            if not got:
                raise CaptureError("GetDIBits failed")
            return (w, h, buf.raw)
        finally:
            gdi32.SelectObject(hdc_mem, old)
            gdi32.DeleteObject(hbmp)
            gdi32.DeleteDC(hdc_mem)
    finally:
        user32.ReleaseDC(hwnd, hdc_window)


PW_CLIENTONLY = 0x00000001


def _bitmapinfo(w: int, h: int):
    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
            ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
            ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
            ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
        ]

    class BITMAPINFO(ctypes.Structure):
        _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]

    bi = BITMAPINFO()
    bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bi.bmiHeader.biWidth = w
    bi.bmiHeader.biHeight = -h  # top-down
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    bi.bmiHeader.biCompression = 0  # BI_RGB
    return bi


def save_capture_bmp(path: str, capture: tuple[int, int, bytes]) -> None:
    """Minimal BMP writer for raw captures (opencv/PIL may not be available)."""
    w, h, bgra = capture
    row = w * 4
    file_size = 54 + row * h
    with open(path, "wb") as f:
        f.write(b"BM" + file_size.to_bytes(4, "little") + b"\0\0\0\0" + (54).to_bytes(4, "little"))
        f.write((40).to_bytes(4, "little") + w.to_bytes(4, "little") + h.to_bytes(4, "little")
                + (1).to_bytes(2, "little") + (32).to_bytes(2, "little") + (0).to_bytes(4, "little")
                + (row * h).to_bytes(4, "little") + (2835).to_bytes(4, "little") * 2 + b"\0" * 8)
        f.write(bgra)


# --- input (message-level: remote-control proof, no focus needed) ------------

def client_to_screen(hwnd: int, x: int, y: int) -> tuple[int, int]:
    pt = wt.POINT(x, y)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return (pt.x, pt.y)


def window_from_screen_point(x: int, y: int) -> int:
    """The HWND (possibly a CHILD control) under the screen point.

    This is the key trick for a composite wx UI: the top-level frame hosts
    native child controls (buttons) and WebView2 children; sending
    WM_LBUTTONDOWN to the frame does NOT route to them — resolve the real
    target HWND first, then SendMessage it directly.
    """
    pt = wt.POINT(x, y)
    return user32.WindowFromPoint(pt)


def msg_click_screen(x: int, y: int) -> int:
    """Left-click at screen (x, y) via WindowFromPoint + SendMessage.

    Synchronous send through the native window procedure: the low-level
    keyboard/mouse hooks (NetEase GameViewer et al.) never see sent messages,
    so this works even when SendInput-style injection is suppressed. Needs no
    foreground window and no focus. Returns the HWND that received it.
    """
    hwnd = window_from_screen_point(x, y)
    lp = _lparam_from_screen(hwnd, x, y)
    _send_msg(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lp)
    _send_msg(hwnd, WM_LBUTTONUP, 0, lp)
    return hwnd


def _lparam_from_screen(hwnd: int, x: int, y: int) -> int:
    # Convert screen -> client coords of hwnd and pack into LPARAM.
    rc = wt.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rc))
    cx, cy = x - rc.left, y - rc.top
    return (cy << 16) | (cx & 0xFFFF)


def msg_click_client(hwnd: int, cx: int, cy: int) -> int:
    """Left-click client coords (cx, cy) of `hwnd` via SendMessage."""
    sx, sy = client_to_screen(hwnd, cx, cy)
    return msg_click_screen(sx, sy)


def msg_text(hwnd: int, text: str) -> None:
    """Type `text` into a control by sending WM_CHAR per character."""
    for ch in text:
        _send_msg(hwnd, WM_CHAR, ord(ch), 0)


def close_window(hwnd: int) -> None:
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def move_to_primary_and_foreground(hwnd: int) -> bool:
    """Move the window onto the primary monitor and make it foreground.

    WHY: the app restores its last window position, which on this machine can
    be the GameViewer VIRTUAL display; a window that lives on a non-interactive
    display is DWM-throttled — its wx timers barely fire and the slicing
    pipeline (timer-driven progress polling) FREEZES at ~30% forever. A vision
    driver needs the app in a real "user is using it" state: visible, on the
    interactive monitor, foreground.
    """
    l, t, r, b = _window_rect(hwnd)
    w, h = r - l, b - t
    if l >= 1900 or t < 0:  # on the virtual display / off-screen
        user32.SetWindowPos(hwnd, 0, 40, 40, 0, 0, 0x0001 | 0x0002)  # NOSIZE | NOZORDER
        print(f"[winutil] moved window from ({l},{t}) to (40,40)")
    user32.ShowWindow(hwnd, 5)  # SW_SHOW
    # Foreground acquisition via AttachThreadInput (plain SetForegroundWindow
    # is a no-op under the foreground lock — same lesson as wx_gui's journal).
    hFg = user32.GetForegroundWindow()
    fgTid = user32.GetWindowThreadProcessId(hFg, None)
    ourTid = kernel32.GetCurrentThreadId()
    attached = user32.AttachThreadInput(ourTid, fgTid, True)
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(hwnd)
    if attached:
        user32.AttachThreadInput(ourTid, fgTid, False)
    ok = user32.GetForegroundWindow() == hwnd
    print(f"[winutil] foreground = our window: {ok}")
    return ok
