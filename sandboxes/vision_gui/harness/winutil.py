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
import threading
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


# ChildWindowFromPointEx skip flags.
CWP_SKIPINVISIBLE = 0x0001
CWP_SKIPDISABLED = 0x0002
CWP_SKIPTRANSPARENT = 0x0004


def deepest_child_at(root_hwnd: int, x: int, y: int) -> int:
    """Deepest descendant of `root_hwnd` containing screen point (x, y).

    WHY: the WCP home keeps a FULLSCREEN transparent render host
    (Chrome_RenderWidgetHostHWND, WS_EX_TRANSPARENT) that WindowFromPoint
    hit-tests above everything while drawing nothing — clicks routed to it
    are silently swallowed (observed ~30% flaky 'click didn't take' in m2,
    both tabs and buttons). WS_EX_TRANSPARENT affects paint order only, NOT
    hit testing, so WindowFromPoint cannot be fixed from outside; instead we
    resolve the target inside the app's OWN window tree, where the WebView2
    host does not exist. ChildWindowFromPointEx with CWP_SKIPTRANSPARENT
    skips transparent layers; recursion walks to the deepest window.
    """
    hwnd = root_hwnd
    while True:
        ox, oy = client_to_screen(hwnd, 0, 0)
        pt = wt.POINT(x - ox, y - oy)
        child = user32.ChildWindowFromPointEx(
            hwnd, pt, CWP_SKIPINVISIBLE | CWP_SKIPDISABLED | CWP_SKIPTRANSPARENT)
        if not child or child == hwnd:
            return hwnd
        hwnd = child


def msg_click_screen(x: int, y: int, root_hwnd: int | None = None) -> int:
    """Left-click at screen (x, y) via SendMessage.

    Synchronous send through the native window procedure: the low-level
    keyboard/mouse hooks (NetEase GameViewer et al.) never see sent messages,
    so this works even when SendInput-style injection is suppressed. Needs no
    foreground window and no focus. Returns the HWND that received it.

    `root_hwnd` (the app's main window) makes the target resolution
    WebView2-proof via `deepest_child_at` — pass it from the drivers.
    """
    hwnd = (deepest_child_at(root_hwnd, x, y) if root_hwnd
            else window_from_screen_point(x, y))
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


def msg_click_client(hwnd: int, cx: int, cy: int, root_hwnd: int | None = None) -> int:
    """Left-click client coords (cx, cy) of `hwnd` via SendMessage."""
    sx, sy = client_to_screen(hwnd, cx, cy)
    return msg_click_screen(sx, sy, root_hwnd)


def msg_text(hwnd: int, text: str) -> None:
    """Type `text` into a control by sending WM_CHAR per character."""
    for ch in text:
        _send_msg(hwnd, WM_CHAR, ord(ch), 0)


WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
VK_CONTROL = 0x11
VK_RETURN = 0x0D


def msg_key(hwnd: int, vk: int, modifiers: int = 0) -> None:
    """Send a key press (WM_KEYDOWN + WM_KEYUP) to `hwnd`.

    Used for Enter in modal dialogs and Ctrl+A select-all in Edit controls.
    `modifiers` (e.g. VK_CONTROL) is held down for the press and released
    after. Message-level injection — immune to remote-control hooks, no
    focus required.
    """
    # A zero lParam is ignored by some native controls (Edit's Ctrl+A,
    # dialog default-button Enter): pack the scan code + repeat count.
    scan = user32.MapVirtualKeyW(vk, 0)  # MAPVK_VK_TO_VSC
    lp = 1 | (scan << 16)
    if modifiers:
        _send_msg(hwnd, WM_KEYDOWN, modifiers, 1 | (user32.MapVirtualKeyW(modifiers, 0) << 16))
    _send_msg(hwnd, WM_KEYDOWN, vk, lp)
    _send_msg(hwnd, WM_KEYUP, vk, lp | (1 << 30) | (1 << 31))
    if modifiers:
        _send_msg(hwnd, WM_KEYUP, modifiers, 1 | (user32.MapVirtualKeyW(modifiers, 0) << 16) | (1 << 30) | (1 << 31))


def select_all(hwnd: int) -> None:
    """Ctrl+A inside an Edit control (prepares it for overwrite typing)."""
    msg_key(hwnd, ord("A"), VK_CONTROL)


def press_enter(hwnd: int) -> None:
    """Press Enter on `hwnd` (activates a modal dialog's default button)."""
    msg_key(hwnd, VK_RETURN)


def close_window(hwnd: int) -> None:
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


# --- real input (SendInput) -------------------------------------------------
# NOTE: the README env matrix used to record SendInput as swallowed by the
# remote-control layer, but it delivers 2/2 on this machine (2026-08-29).
# It is needed ONLY where the app's modal loops ignore message-level input:
# native popup-menu rows (#32768) hit-test in their modal loop, which
# message clicks cannot drive (see topbar_util). The WCP WebView2 transparent
# host swallows real clicks over the APP window, so SendInput is used ONLY
# on topmost menu windows, never on the app frame itself.

MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


class _INPUT(ctypes.Structure):
    class _INPUTMOUSE(ctypes.Structure):
        _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD),
                    ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wt.ULONG))]
    _fields_ = [("type", wt.DWORD), ("value", _INPUTMOUSE)]


def real_click_screen(x: int, y: int) -> int:
    """A REAL left click at screen (x, y) via SendInput (moves the cursor).

    Unlike msg_click_screen this goes through the OS input queue, so modal
    loops (native menus, dialogs) see it as genuine user input. Returns the
    number of events delivered."""
    sw = user32.GetSystemMetrics(0)   # SM_CXSCREEN
    sh = user32.GetSystemMetrics(1)   # SM_CYSCREEN
    absx = int(x * 65535 / sw)
    absy = int(y * 65535 / sh)
    events = []
    for flags in (MOUSEEVENTF_MOVE | MOUSEEVENTF_LEFTDOWN,
                  MOUSEEVENTF_LEFTUP):
        ev = _INPUT()
        ev.type = 0  # INPUT_MOUSE
        ev.value.dx = absx
        ev.value.dy = absy
        ev.value.dwFlags = flags | MOUSEEVENTF_ABSOLUTE
        events.append(ev)
    arr = (_INPUT * 2)(*events)
    return user32.SendInput(2, arr, ctypes.sizeof(_INPUT))


WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
HWND_BOTTOM = 1                  # SetWindowPos insert-after
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
GWL_EXSTYLE = -20


def demote_window(hwnd: int) -> bool:
    """One PASSIVE demotion pass on `hwnd`: bottom of the z-order, and — the
    load-bearing bit — WS_EX_NOACTIVATE, which forbids the window from ever
    taking the foreground again (Show/Raise/click included). Touches ONLY the
    ex-style and the z-order: no move, no size, no focus, no foreground grab,
    so it can be repeated freely (the boot watchdog calls it every tick).
    Rendering and hit-testing are untouched, so capture and message injection
    keep working (regression-verified, see diag_early_stealth.py).

    The taskbar button is deliberately KEPT (2026-08-30, user request): with
    WS_EX_TOOLWINDOW the app was completely invisible — an orphaned/stuck
    run gave the user no indicator at all. The icon is a running indicator;
    NOACTIVATE still keeps a taskbar click from popping the window to the
    top. History: the FIRST version set only WS_EX_TOOLWINDOW plus a one-shot
    HWND_BOTTOM, so any later Show/Raise/dialog re-popped the app over the
    user's desktop — the very thing the stealth design exists to prevent.
    """
    ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)
    user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    return bool(style & WS_EX_NOACTIVATE)


# Backwards-compat alias (m3x case scripts may call the old name directly).
background_tool_window = demote_window


def _window_pid(hwnd: int) -> int:
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def force_set_foreground(hwnd: int) -> bool:
    """SetForegroundWindow that works under the foreground lock, and works on
    a window we do NOT own: attach our thread to the current foreground
    thread first (same trick move_to_primary_and_foreground uses). Used to
    RESTORE focus to the window the user was actually using when the app
    under test grabs the foreground at boot.
    """
    fg = user32.GetForegroundWindow()
    our_tid = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = user32.AttachThreadInput(our_tid, fg_tid, True) if fg_tid else False
    user32.SetForegroundWindow(hwnd)
    user32.SetFocus(hwnd)
    if attached:
        user32.AttachThreadInput(our_tid, fg_tid, False)
    return user32.GetForegroundWindow() == hwnd


def demote_watchdog(pid: int, duration_s: float, interval_s: float = 0.2,
                    fg_restore_to: int | None = None) -> threading.Thread:
    """Keep every visible top-level window of `pid` demoted for `duration_s`.

    WHY: the launcher's SW_SHOWNOACTIVATE is a no-op for wx — wxMSW Show()
    calls ShowWindow(SW_SHOW), which activates + raises regardless of the
    STARTUPINFO wShowWindow (Windows honors that only for SW_SHOWDEFAULT).
    The main frame therefore popped to the TOP of the user's desktop at boot
    and, under the drivers' hands-off rule, sat there for ~12s until the
    late background_tool_window() call ran.

    Two mechanisms, because demotion alone is racy:
      1. demote_window() every tick (ex-style + HWND_BOTTOM, NOMOVE|NOSIZE|
         NOACTIVATE) — prevents any LATER activation, self-heals Raises.
      2. fg_restore_to: the watchdog cannot PREVENT the first activation
         (Show races our first tick — verified: two runs of the same code
         gave 0 vs 139 foreground steals) and z-order demotion does not
         strip an already-held foreground. So when the app owns the
         foreground, we hand it back to `fg_restore_to` (the window that
         was foreground before launch — i.e. whatever the user was using).
         This is focus RESTORATION, the inverse of the experimentally
         forbidden foreground-grabbing (README pitfall #3).

    Returns the started daemon thread.
    """
    stop_at = time.monotonic() + duration_s
    restore_count = 0

    def _run() -> None:
        nonlocal restore_count
        while time.monotonic() < stop_at:
            try:
                for hwnd, wpid in enum_windows():
                    if wpid == pid:
                        demote_window(hwnd)
                if fg_restore_to is not None:
                    fg = user32.GetForegroundWindow()
                    if fg and fg != fg_restore_to and _window_pid(fg) == pid:
                        restore_count += 1
                        if force_set_foreground(fg_restore_to):
                            print(f"[winutil] demote_watchdog: foreground restored "
                                  f"to pre-launch window (#{restore_count})")
            except Exception as e:  # never let the watchdog kill a run
                print(f"[winutil] demote_watchdog: {e}")
            time.sleep(interval_s)

    t = threading.Thread(target=_run, daemon=True, name="demote-watchdog")
    t.start()
    return t


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
