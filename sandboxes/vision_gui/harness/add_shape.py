#!/usr/bin/env python3
# add_shape.py — add a STANDARD MODEL to the empty plate via the right-click
# context menu (the m5 main-flow entry point: no 3mf fixture).
#
# Measured 09-01 on the maximized window (diag_m5_menu):
#   - the plate context menu is a NATIVE #32768 that message-level
#     WM_RBUTTONDOWN/UP opens reliably; REAL right-clicks are swallowed by
#     the remote-control layer (3/3 no-ops) — use msg_rclick.
#   - 'Add Primitive' row opens a submenu (Cube | Cylinder | Sphere | Cone |
#     Disc | Text | SVG); rows are located by OCR of the menu capture, then
#     clicked with REAL input (native menus run a modal loop).
#   - a real-hover (~1.5s) on the 'Add Primitive' row expands the submenu.
#
# Menu geometry is read per-open (OCR word offsets + menu rect) — nothing
# here depends on the window size.

import ctypes
import time

from . import mix_dialog_util as mdu
from . import mixing_util, winutil
from m1_minimal_loop import capture_bgr
from m2_slice_chain import VP_X0, VP_Y0, has_colored_content

user32 = ctypes.WinDLL("user32")
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205


def msg_rclick_screen(session, x, y):
    hwnd = winutil.deepest_child_at(session.hwnd, x, y)
    lp = winutil._lparam_from_screen(hwnd, x, y)
    winutil._send_msg(hwnd, WM_RBUTTONDOWN, 0x0002, lp)
    winutil._send_msg(hwnd, WM_RBUTTONUP, 0, lp)
    return hwnd


def _menus_of(pid):
    return [(r, h) for cls, txt, r, h in mixing_util.toplevel(pid)
            if cls == "#32768"]


def _menu_words(menu):
    r, h = menu
    w, hgt, bgra = winutil.capture_window(h)
    import numpy as np
    img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
    return r, mdu.ocr_words_img(img, scale=3)


def _row_point(menu_rect, words, substr):
    mr = menu_rect
    for t, x, y, w_w, w_h in words:
        if substr.lower() in t.lower():
            return (mr[0] + x + w_w // 2, mr[1] + y + w_h // 2)
    return None


def _real_move(x, y):
    winutil.user32.SetCursorPos(x, y)
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    ev = winutil._INPUT()
    ev.type = 0
    ev.value.dx = int(x * 65535 / sw)
    ev.value.dy = int(y * 65535 / sh)
    ev.value.dwFlags = winutil.MOUSEEVENTF_MOVE | winutil.MOUSEEVENTF_ABSOLUTE
    user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(winutil._INPUT))


def _dismiss_menus(session):
    for _ in range(3):
        if not _menus_of(session.pid):
            return
        mdu._send_keys([(0x1B, False), (0x1B, True)])
        time.sleep(0.3)


def add_primitive(session, shape: str = "Cube", timeout_s: float = 30.0) -> bool:
    """Add a standard primitive via the plate context menu; returns True
    once a model renders (chromatic content over the empty-plate floor)."""
    img = capture_bgr(session)
    hh, ww = img.shape[:2]
    cx, cy = VP_X0 + (ww - VP_X0) // 2, (VP_Y0 + hh) // 2
    baseline = has_colored_content(img)

    msg_rclick_screen(session, cx, cy)
    deadline = time.monotonic() + timeout_s
    menu = None
    while time.monotonic() < deadline and not menu:
        time.sleep(0.3)
        menus = _menus_of(session.pid)
        menu = menus[0] if menus else None
    if not menu:
        return False
    words = _menu_words(menu)[1]
    pt = _row_point(menu[0], words, "Primitive")
    print("[add_shape] menu words: "
          + " | ".join(t for t, *_ in words)[:150])
    if not pt:
        print("[add_shape] FAIL: Primitive row not found")
        _dismiss_menus(session)
        return False
    _real_move(*pt)
    time.sleep(1.5)

    sub = None
    while time.monotonic() < deadline and not sub:
        time.sleep(0.3)
        subs = [m for m in _menus_of(session.pid) if m[1] != menu[1]]
        sub = subs[0] if subs else None
    if not sub:
        print("[add_shape] FAIL: shapes submenu did not open")
        _dismiss_menus(session)
        return False
    swords = _menu_words(sub)[1]
    print("[add_shape] submenu words: "
          + " | ".join(t for t, *_ in swords)[:150])
    spt = _row_point(sub[0], swords, shape)
    if not spt:
        # tolerate case/spacing variants: first word as a fallback probe
        spt = _row_point(sub[0], swords, shape.capitalize())
    if not spt:
        print(f"[add_shape] FAIL: {shape} row not found")
        _dismiss_menus(session)
        return False
    winutil.user32.SetCursorPos(*spt)
    time.sleep(0.2)
    winutil.real_click_screen(*spt)
    time.sleep(3.0)
    _dismiss_menus(session)

    # model arrival: chromatic fraction clears the m2 model-loaded floor
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        frac = has_colored_content(capture_bgr(session))
        if frac >= 0.003 and frac > baseline * 3:
            print(f"[add_shape] model landed (chroma {frac:.3%})")
            return True
        time.sleep(1.0)
    print(f"[add_shape] FAIL: model never landed (chroma {frac:.3%})")
    return False
