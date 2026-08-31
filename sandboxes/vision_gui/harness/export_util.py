#!/usr/bin/env python3
# export_util.py — Tier 0: the EXPORT-GCODE black-box primitive.
#
# "Export G-code becomes available" is the deterministic slicing-completion
# signal (MainFrame::can_export_gcode -> is_slice_result_ready_for_print,
# MainFrame.cpp:1600) and exporting produces the STRONGEST black-box
# assertion artifact: the real gcode file, parsed on disk.
#
# UI path (measured on the 08-24 dev build, Snapmaker U1 layout):
#   1. topbar right side has: [slice-opt][Slice][print-opt][Print/Export]
#      — ALL SideButtons are wxWindowNR with NO native HWND children, so
#      locate them by EnumChildWindows + GetWindowText + screen rect
#      (deterministic, no templates).
#   2. clicking the PRINT dropdown (empty-text button left of the main
#      print button) opens a SidePopup (a top-level wxWindowNR 'panel')
#      whose rows are 'Print' / 'Export G-code file' (order varies!).
#   3. clicking the row sets m_print_select=eExportGcode and the main
#      button label becomes 'Export G-code file'.
#   4. clicking the main button then posts EVT_GLTOOLBAR_EXPORT_GCODE and
#      the native 'Save G-code file as:' dialog (#32770) opens.
#   5. type the full path into the filename Edit, press Enter, wait for the
#      file to land on disk.
#
# CRITICAL details learned the hard way:
#   - the popup row click must NOT pass root_hwnd: the popup is a SEPARATE
#     top-level window, deepest_child_at(root) resolves inside the app tree
#     and would dismiss the popup instead of selecting the row.
#   - button rects MOVE when the print label changes length (Slice shifts
#     left), so re-enumerate after every step; never cache coordinates.
#   - EnumChildWindows order is not layout order — sort by rect.

import ctypes
import ctypes.wintypes as wt
import time
from pathlib import Path

from . import winutil

user32 = ctypes.WinDLL("user32")
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

# Topbar row filter, WINDOW-RELATIVE (recalibrated 08-31 for the maximized
# window): the SideButton cluster sits at client y ~25-70 and hugs the RIGHT
# edge of the topbar. Absolute screen bands (the old y 140-170 / x > 1150)
# were calibrated against one windowed position and broke the moment the
# window maximizes (buttons land at screen y ~50-90, x ~1800).
_TOPBAR_CLIENT_Y0, _TOPBAR_CLIENT_Y1 = 18, 100
_MAIN_RIGHT_SPAN = 600  # buttons live within the rightmost N client px


def _client_frame(hwnd: int) -> tuple[int, int, int]:
    """(client-origin screen x, client-origin screen y, client width)."""
    rc = wt.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rc))
    w = rc.right - rc.left
    ox, oy = winutil.client_to_screen(hwnd, 0, 0)
    return ox, oy, w


def _children_texts(parent: int) -> list[tuple[str, tuple[int, int, int, int], int]]:
    """(text, screen-rect, hwnd) for every child of `parent`."""
    out: list[tuple[str, tuple[int, int, int, int], int]] = []

    def cb(hwnd, _lp):
        txt = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(hwnd, txt, 128)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append((txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd))
        return True

    user32.EnumChildWindows(ctypes.c_void_p(parent), WNDENUMPROC(cb), 0)
    return out


def topbar_buttons(hwnd: int) -> list[tuple[str, tuple[int, int, int, int], int]]:
    """SideButton cluster in the topbar right area: named main buttons
    ('Slice plate' / 'Print' / 'Export G-code file') and empty-text dropdown
    buttons. Returned sorted left-to-right. Band is window-relative, so it
    holds at any window position AND maximized."""
    ox, oy, w_client = _client_frame(hwnd)
    y0, y1 = oy + _TOPBAR_CLIENT_Y0, oy + _TOPBAR_CLIENT_Y1
    x_min = ox + max(0, w_client - _MAIN_RIGHT_SPAN)
    out = []
    for text, rect, ch in _children_texts(hwnd):
        if y0 <= rect[1] <= y1 and rect[0] > x_min:
            out.append((text, rect, ch))
    out.sort(key=lambda b: b[1][0])
    return out


def find_slice_buttons(hwnd: int):
    """(slice_opt, slice_main) from the topbar button cluster."""
    btns = topbar_buttons(hwnd)
    named = [b for b in btns if b[0]]
    empties = [b for b in btns if not b[0]]
    slice_main = None
    for i, b in enumerate(named):
        if "Slice" in b[0]:
            slice_main = b
    slice_opt = None
    if slice_main:
        left_neighbors = [e for e in empties if e[1][2] <= slice_main[1][0]]
        if left_neighbors:
            slice_opt = max(left_neighbors, key=lambda e: e[1][2])
    return slice_opt, slice_main


def find_print_buttons(hwnd: int):
    """(print_opt, print_main) — main is the rightmost named button
    ('Print' initially; 'Export G-code file' after mode selection)."""
    btns = topbar_buttons(hwnd)
    named = [b for b in btns if b[0]]
    empties = [b for b in btns if not b[0]]
    if not named:
        return None, None
    main = named[-1]  # rightmost named = the print/export main button
    opt = None
    left_neighbors = [e for e in empties if e[1][2] <= main[1][0]]
    if left_neighbors:
        opt = max(left_neighbors, key=lambda e: e[1][2])
    return opt, main


def _click_center(session, rect: tuple[int, int, int, int], root: bool = True) -> int:
    cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    return winutil.msg_click_screen(cx, cy, session.hwnd if root else None)


def wait_toplevel(pid: int, predicate, timeout_s: float = 10.0, poll_s: float = 0.25):
    """Poll EnumWindows for a visible top-level window of `pid` matching
    `predicate(cls, text, rect)`. Returns the window tuple or None."""
    deadline = time.monotonic() + timeout_s
    found: list = []

    def cb(hwnd, _lp):
        tid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(tid))
        if tid.value != pid or not user32.IsWindowVisible(hwnd):
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(hwnd, txt, 128)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        tup = (cls.value, txt.value, (rc.left, rc.top, rc.right, rc.bottom), hwnd)
        if predicate(*tup[:3]):
            found.append(tup)
        return True

    while time.monotonic() < deadline:
        found.clear()
        user32.EnumWindows(WNDENUMPROC(cb), 0)
        if found:
            return found[0]
        time.sleep(poll_s)
    return None


def wait_popup(pid: int, timeout_s: float = 5.0):
    """The SidePopup options menu: a visible top-level wxWindowNR 'panel'."""
    return wait_toplevel(pid, lambda c, t, r: c == "wxWindowNR" and t == "panel",
                         timeout_s)


def wait_save_dialog(pid: int, timeout_s: float = 15.0):
    """The native 'Save G-code file as:' dialog — a visible #32770."""
    return wait_toplevel(pid, lambda c, t, r: c == "#32770", timeout_s)


def find_edit(dialog_hwnd: int) -> int | None:
    """The filename Edit of a native save dialog (class 'Edit')."""
    for text, rect, ch in _children_texts(dialog_hwnd):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(ch, cls, 64)
        if cls.value == "Edit":
            return ch
    return None


def wait_file(path: Path, timeout_s: float = 30.0, poll_s: float = 0.5) -> bool:
    """Poll until `path` exists and is non-empty (export finished writing)."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if path.exists() and path.stat().st_size > 0:
                return True
        except OSError:
            pass  # file may be momentarily locked by the writer
        time.sleep(poll_s)
    return False


def switch_to_export_mode(session, timeout_s: float = 10.0) -> bool:
    """Ensure the topbar print button is in eExportGcode mode.

    Steps: click the print dropdown -> popup -> click the 'Export G-code
    file' row. Returns True when the main button label confirms the mode.
    """
    opt, main = find_print_buttons(session.hwnd)
    if main and "Export" in main[0]:
        return True  # already in export mode
    if not opt:
        return False
    _click_center(session, opt[1])
    popup = wait_popup(session.pid, timeout_s=5.0)
    if not popup:
        return False
    rows = [r for r in _children_texts(popup[3]) if "Export" in r[0]]
    if not rows:
        return False
    # popup is a SEPARATE top-level window: click WITHOUT root piercing
    rect = rows[0][1]
    winutil.msg_click_screen((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        _, main2 = find_print_buttons(session.hwnd)
        if main2 and "Export" in main2[0]:
            return True
        time.sleep(0.3)
    return False


def export_gcode(session, out_path: Path, timeout_s: float = 60.0) -> bool:
    """Export the current slice result to `out_path` and wait for the file.

    Precondition: a slice has COMPLETED (export is gated on
    is_slice_result_ready_for_print). The call is the completion probe
    itself — a dialog appearing proves the gate was open.
    Returns True when the gcode file exists and is non-empty.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not switch_to_export_mode(session):
        return False
    _, main = find_print_buttons(session.hwnd)
    if not main:
        return False
    _click_center(session, main[1])  # posts EVT_GLTOOLBAR_EXPORT_GCODE
    dlg = wait_save_dialog(session.pid, timeout_s=15.0)
    if not dlg:
        return False
    edit = find_edit(dlg[3])
    if edit is None:
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(out_path))
    # Enter-on-Edit does NOT trigger the save (native dialog routes it
    # nowhere useful); the deterministic trigger is WM_COMMAND IDOK on the
    # dialog itself (measured: file lands reliably).
    user32.SendMessageW(dlg[3], 0x0111, 1, 0)  # WM_COMMAND, IDOK = 1
    return wait_file(out_path, timeout_s=timeout_s)
