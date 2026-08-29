#!/usr/bin/env python3
# mixing_util.py — primitives for the Color Mixing Match dialog
# (MixedFilamentBatchDialog) black-box cases.
#
# UI facts (measured on the 08-24 dev build, source-verified):
#   - entry: the 'Color Mixing Match' title bar in the right-side mixing
#     panel (Plater.cpp:2578 gate: model colors + >=2 filaments); the add
#     button is the icon-only ScalableButton at the bar's right end —
#     clicked by probing offsets (SetCursorPos + message click, like the
#     topbar tools).
#   - the dialog is a NATIVE modal #32770 'Color Mixing Match'; its controls
#     are reached WITHOUT root piercing (it is a separate top-level — root
#     resolves inside the frame tree and the click would miss).
#   - 'Auto' (recommended) mode on the seeded U1 0.8 nozzle has NO Full
#     Spectrum preset -> start_batch_match() gates with a RichMessageDialog
#     ('Automatic color mixing matching is not supported for the current
#     nozzle diameter...', MixedFilamentBatchDialog.cpp:2290) — a
#     deterministic, case-worthy behavior (record #49).
#   - the match-mode selector is a readonly ComboBox ('Auto'/'Manual'); its
#     popup is a top-level 'panel' with self-drawn rows (28px pitch,
#     popup_top+14 = first row): click row 2 (popup_top+42) for Manual,
#     confirm via GetWindowText on the combo.
#   - Manual mode matching runs in a background thread and finishes in
#     seconds; completion is observable as the color-mapping list region
#     rendering saturated swatches (chromatic fraction jumps from ~0 to
#     ~0.1+) and the view panels rendering the model + result.

import ctypes
import ctypes.wintypes as wt
import time

import numpy as np

from . import winutil

user32 = ctypes.WinDLL("user32")
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


# --- window helpers ---------------------------------------------------------

def children(parent: int):
    """(text, class, screen-rect, hwnd) for every child of `parent`."""
    out = []

    def cb(hwnd, _lp):
        txt = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, txt, 512)
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((txt.value, cls.value,
                    (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumChildWindows(ctypes.c_void_p(parent), WNDENUMPROC(cb), 0)
    return out


def toplevel(pid: int):
    """Visible top-level windows of the app as (class, text, rect, hwnd)."""
    out = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, txt, 256)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((cls.value, txt.value,
                    (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


def find_dialog(pid: int, timeout_s: float = 10.0):
    """The Color Mixing Match batch dialog: the big (#32770) top-level."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, rect, hwnd in toplevel(pid):
            if cls == "#32770" and "Color Mixing Match" in txt \
                    and rect[3] - rect[1] > 300:
                return hwnd
        time.sleep(0.3)
    return None


def _msg_click(x: int, y: int, root=None) -> int:
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.2)
    return winutil.msg_click_screen(x, y, root)


def dialog_children(dlg: int):
    return children(dlg)


def child_by_text(dlg: int, substr: str):
    for t, c, r, h in children(dlg):
        if substr in t:
            return t, c, r, h
    return None


def dialog_bgr(dlg: int):
    """The dialog's own pixels (PrintWindow), BGR numpy array."""
    w, h, bgra = winutil.capture_window(dlg)
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
    return img[:, :, ::-1].copy()


# --- entry -------------------------------------------------------------------

def open_mixing_dialog(session, timeout_s: float = 12.0):
    """Click the add button at the right end of the 'Color Mixing Match'
    title bar; returns the dialog hwnd or None."""
    frect = winutil.window_rect(session.hwnd)
    for t, c, r, h in children(session.hwnd):
        if t == "Color Mixing Match" and r[3] - r[1] < 40 \
                and r[3] > frect[1] and r[3] < frect[3] \
                and user32.IsWindowVisible(h):
            cy = (r[1] + r[3]) // 2
            for dx in (16, 26, 36):
                _msg_click(r[2] - dx, cy, session.hwnd)
                dlg = find_dialog(session.pid, timeout_s=3.0)
                if dlg:
                    return dlg
            break
    return None


# --- match mode combo --------------------------------------------------------

def combo_text(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(128)
    user32.GetWindowTextW(hwnd, buf, 128)
    return buf.value


def switch_match_mode(session, dlg: int, target: str) -> bool:
    """Switch the Auto/Manual combo to `target` (popup row 2 = Manual)."""
    return switch_combo(session, dlg, ("Auto", "Manual"), target)


def switch_combo(session, dlg: int, current_labels: tuple, target: str,
                 row_guess: int = 1) -> bool:
    """Switch a readonly combo (identified by one of `current_labels`)
    to `target` by opening its popup (NO root — the dialog is a separate
    top-level) and clicking rows from `row_guess` onward until the combo
    text confirms. Popup rows: 28px pitch, first row at popup_top+14."""
    combo = None
    for t, c, r, h in children(dlg):
        if t in current_labels:
            combo = (r, h)
            break
    if not combo:
        return False
    rect, ch = combo
    if target in combo_text(ch):
        return True
    _msg_click((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
    deadline = time.monotonic() + 4.0
    pr = None
    while time.monotonic() < deadline:
        for cls, txt, r, h in toplevel(session.pid):
            if cls == "wxWindowNR" and txt == "panel":
                pr = r
                break
        if pr:
            break
        time.sleep(0.2)
    if not pr:
        return False
    px = (pr[0] + pr[2]) // 2
    for row in range(max(0, row_guess), 12):
        _msg_click(px, pr[1] + 14 + row * 28)
        time.sleep(0.8)
        if target in combo_text(ch):
            return True
        # reopen the popup for the next row
        _msg_click((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
        time.sleep(1.0)
    return False


# --- matching -----------------------------------------------------------------

def click_button(dlg: int, substr: str) -> bool:
    """Click a dialog button by its text label (real input: the dialog's
    self-drawn buttons are in a modal context that message clicks miss)."""
    hit = child_by_text(dlg, substr)
    if not hit:
        return False
    rect = hit[2]
    winutil.real_click_screen((rect[0] + rect[2]) // 2,
                              (rect[1] + rect[3]) // 2)
    return True


def wait_warning_dialog(pid: int, dlg: int, timeout_s: float = 8.0):
    """A NEW #32770 dialog (the gated RichMessageDialog) on top of the
    batch dialog; returns its hwnd or None."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, rect, hwnd in toplevel(pid):
            if cls == "#32770" and hwnd != dlg and rect[3] - rect[1] < 300:
                return hwnd
        time.sleep(0.3)
    return None


def dismiss_dialog(pid: int, dlg: int) -> bool:
    """Click the 'Got it' / OK button of a modal warning dialog."""
    hit = child_by_text(dlg, "Got")
    if not hit:
        hit = child_by_text(dlg, "OK")
    if not hit:
        return False
    rect = hit[2]
    winutil.real_click_screen((rect[0] + rect[2]) // 2,
                              (rect[1] + rect[3]) // 2)
    time.sleep(1.0)
    return True


def map_region_colored(img, dlg_rect: tuple, region) -> float:
    """Chromatic fraction of a screen region inside the dialog capture."""
    x0, y0 = region[0] - dlg_rect[0], region[1] - dlg_rect[1]
    x1, y1 = region[2] - dlg_rect[0], region[3] - dlg_rect[1]
    sub = img[y0:y1, x0:x1].astype(int)
    spread = sub.max(axis=2) - sub.min(axis=2)
    return float((spread > 40).mean())


def wait_match_done(session, dlg: int, timeout_s: float = 60.0) -> bool:
    """Manual matching completes when the color-mapping list renders
    saturated swatches (measured: chromatic fraction 0 -> ~0.12) and the
    result view panel shows content. Returns True on completion."""
    dlg_rect = None
    for cls, txt, r, h in toplevel(session.pid):
        if h == dlg:
            dlg_rect = r
    if not dlg_rect:
        return False
    map_region = (746, 749, 1173, 780)
    deadline = time.monotonic() + timeout_s
    last = 0.0
    while time.monotonic() < deadline:
        img = dialog_bgr(dlg)
        frac = map_region_colored(img, dlg_rect, map_region)
        last = frac
        if frac > 0.02:
            time.sleep(1.0)
            frac2 = map_region_colored(dialog_bgr(dlg), dlg_rect, map_region)
            if frac2 > 0.02:
                return True
        time.sleep(0.5)
    return False


# --- swatch hover (Delta-E tooltip) ------------------------------------------

def swatch_rows(dlg: int):
    """The mapping-list swatch rows created AFTER a match: small panels in
    the dialog's lower band (measured rects ~93x36 at y 797-885)."""
    rows = []
    for t, c, r, h in children(dlg):
        if c == "wxWindowNR" and 780 < r[1] < 900 \
                and r[3] - r[1] in (32, 36) and r[2] - r[0] in (83, 93):
            rows.append(r)
    return rows


def wait_tooltip(pid: int, timeout_s: float = 5.0):
    """A visible tooltip window (tooltips_class32) with real height."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, rect, hwnd in toplevel(pid):
            if cls == "tooltips_class32" and rect[3] - rect[1] > 10:
                return rect, hwnd
        time.sleep(0.2)
    return None


def _real_move(x: int, y: int) -> int:
    """A REAL mouse move via SendInput (absolute screen coords)."""
    sw = winutil.user32.GetSystemMetrics(0)
    sh = winutil.user32.GetSystemMetrics(1)
    ev = winutil._INPUT()
    ev.type = 0  # INPUT_MOUSE
    ev.value.dx = int(x * 65535 / sw)
    ev.value.dy = int(y * 65535 / sh)
    ev.value.dwFlags = (winutil.MOUSEEVENTF_MOVE |
                        winutil.MOUSEEVENTF_ABSOLUTE)
    return winutil.user32.SendInput(1, ctypes.byref(ev),
                                    ctypes.sizeof(winutil._INPUT))


def hover_swatch_row(session, dlg: int, row_rect: tuple, x_frac: float = 0.2,
                     dwell_s: float = 6.0):
    """Park the REAL cursor on a swatch row (the wx system tooltip tracks
    real mouse input only — SetCursorPos / WM_MOUSEMOVE injection do NOT
    arm it, measured). Consecutive-run experience: the cursor can be stolen
    by other processes (remote layers), so the position is held and nudged
    with repeated real moves until the tooltip appears. Returns the tooltip
    window (rect, hwnd) or None."""
    x = int(row_rect[0] + (row_rect[2] - row_rect[0]) * x_frac)
    y = (row_rect[1] + row_rect[3]) // 2
    deadline = time.monotonic() + dwell_s
    while time.monotonic() < deadline:
        winutil.user32.SetCursorPos(x, y)
        _real_move(x, y)
        tt = wait_tooltip(session.pid, timeout_s=1.0)
        if tt:
            return tt
        time.sleep(0.4)
    return None
