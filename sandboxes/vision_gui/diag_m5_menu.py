#!/usr/bin/env python3
# diag_m5_menu.py — v3: open the empty-plate context menu (message-level
# right-click; REAL right-clicks are swallowed by the remote layer —
# measured 09-01), hover 'Add Primitive', capture the shapes submenu, click
# a shape and confirm a model lands on the plate.
# Run: hv_go.ps1 -Cases diag_m5_menu

import ctypes
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import (VP_X0, VP_Y0, has_colored_content,  # noqa: E402
                            wait_model_loaded)
from m3_common import add_common_args, boot_session, verdict  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[diag]"
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205


def msg_rclick_screen(session, x, y):
    hwnd = winutil.deepest_child_at(session.hwnd, x, y)
    lp = winutil._lparam_from_screen(hwnd, x, y)
    winutil._send_msg(hwnd, WM_RBUTTONDOWN, 0x0002, lp)
    winutil._send_msg(hwnd, WM_RBUTTONUP, 0, lp)
    return hwnd


def menus_of(pid):
    """All visible #32768 windows of pid as [(rect, hwnd)]."""
    return [(r, h) for cls, txt, r, h in mixing_util.toplevel(pid)
            if cls == "#32768"]


def dump_menu(tag, menu):
    r, h = menu
    w, hgt, bgra = winutil.capture_window(h)
    img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
    cv2.imwrite(str(HERE / "artifacts" / f"m5_menu_{tag}.png"),
                img[:, :, ::-1])
    words = mdu.ocr_words_img(img, scale=3)
    print(f"{LOG} menu[{tag}] rect={r} ocr: "
          f"{' | '.join(t for t, *_ in words)!r}")
    return words


def row_point(menu_rect, words, substr):
    """Screen point of the menu row whose OCR text contains `substr`."""
    mr = menu_rect
    for t, x, y, w_w, w_h in words:
        if substr.lower() in t.lower():
            return (mr[0] + x + w_w // 2, mr[1] + y + w_h // 2)
    return None


def real_move(x, y):
    winutil.user32.SetCursorPos(x, y)
    sw = user32.GetSystemMetrics(0)
    sh = user32.GetSystemMetrics(1)
    ev = winutil._INPUT()
    ev.type = 0
    ev.value.dx = int(x * 65535 / sw)
    ev.value.dy = int(y * 65535 / sh)
    ev.value.dwFlags = winutil.MOUSEEVENTF_MOVE | winutil.MOUSEEVENTF_ABSOLUTE
    user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(winutil._INPUT))


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=None)
    try:
        time.sleep(3.0)
        img = capture_bgr(session)
        hh, ww = img.shape[:2]
        cx, cy = VP_X0 + (ww - VP_X0) // 2, (VP_Y0 + hh) // 2
        frac0 = has_colored_content(img)
        print(f"{LOG} empty-plate chroma baseline {frac0:.3%}")

        sx, sy = winutil.client_to_screen(session.hwnd, cx, cy)
        msg_rclick_screen(session, cx, cy)
        time.sleep(1.2)
        menus = menus_of(session.pid)
        if not menus:
            print(f"{LOG} no context menu")
            results["context menu opens"] = "FAIL"
            return verdict(results)
        menu = menus[0]
        words = dump_menu("top", menu)

        # hover 'Add Primitive' to expand the shapes submenu
        pt = row_point(menu[0], words, "Primitive")
        print(f"{LOG} Add Primitive row at {pt}")
        results["Add Primitive row located"] = "PASS" if pt else "FAIL"
        if not pt:
            return verdict(results)
        real_move(*pt)
        time.sleep(1.5)
        menus2 = menus_of(session.pid)
        sub = next((m for m in menus2 if m[1] != menu[1]), None)
        print(f"{LOG} menus after hover: {len(menus2)}")
        results["shapes submenu opens"] = "PASS" if sub else "FAIL"
        if not sub:
            cv2.imwrite(str(HERE / "artifacts" / "m5_main_hover.png"),
                        capture_bgr(session)[:, :, ::-1])
            return verdict(results)
        swords = dump_menu("sub", sub)

        # click the 'Cube' row (fall back to the first submenu word)
        spt = row_point(sub[0], swords, "cube") or \
            row_point(sub[0], swords, swords[0][0])
        print(f"{LOG} cube row at {spt}")
        winutil.real_click_screen(*spt)
        time.sleep(3.0)

        # confirm: a model now renders on the plate
        ok_model, frac = wait_model_loaded(session, timeout_s=20)
        img2 = capture_bgr(session)
        cv2.imwrite(str(HERE / "artifacts" / "m5_after_add.png"),
                    img2[:, :, ::-1])
        print(f"{LOG} model loaded: {ok_model} (chroma {frac0:.3%} -> "
              f"{frac:.3%})")
        results["primitive lands on plate"] = (
            "PASS" if ok_model else "FAIL")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
