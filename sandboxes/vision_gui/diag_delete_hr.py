#!/usr/bin/env python3
# diag_delete_hr.py — reproduce "add Height range Modifier, then Delete key"
# scenario. Steps: load model -> right-click object -> context menu
# 'Height range Modifier' -> verify layers editing overlay -> select object ->
# press Delete (VK_DELETE / VK_BACK) -> check whether the object survives.

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import launcher, mixing_util, profile, winutil  # noqa: E402
from harness.add_shape import (  # noqa: E402
    _dismiss_menus, _menus_of, _menu_words, _real_move, _row_point,
    msg_rclick_screen)
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import VP_X0, VP_Y0, has_colored_content, wait_model_loaded  # noqa: E402
from m3_common import add_common_args, boot_session, verdict  # noqa: E402

VK_DELETE = 0x2E
VK_BACK = 0x08


def viewport_center(session):
    img = capture_bgr(session)
    hh, ww = img.shape[:2]
    return VP_X0 + (ww - VP_X0) // 2, (VP_Y0 + hh) // 2


def open_object_menu(session, timeout_s=12.0):
    cx, cy = viewport_center(session)
    msg_rclick_screen(session, cx, cy)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        menus = _menus_of(session.pid)
        if menus:
            return menus[0]
        time.sleep(0.3)
    return None


def click_menu_row(menu, substr, timeout_s=12.0):
    r, h = menu
    words = _menu_words(menu)[1]
    for t, x, y, w_w, w_h in words:
        print(f"[diag] menu word: {t!r} at ({x},{y})")
    pt = _row_point(r, words, substr)
    if not pt:
        return False
    _real_move(*pt)
    time.sleep(1.0)
    winutil.real_click_screen(*pt)
    time.sleep(0.5)
    return True


def send_key(session, vk, hold_s=0.08):
    mdu._send_keys([(vk, False)])
    time.sleep(hold_s)
    mdu._send_keys([(vk, True)])
    time.sleep(0.3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=r"C:\coil\Projects\SnapmakerOrca\tests\data\20mm_cube.obj")
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[diag] model arrived: {ok_model} (colored {frac:.2%})")
        results["model arrived"] = "PASS" if ok_model else "FAIL"
        if not ok_model:
            return verdict(results)

        frac_before = frac

        # ---- step 1: right-click object -> 'Height range Modifier' ----
        menu = open_object_menu(session)
        results["object context menu opens"] = "PASS" if menu else "FAIL"
        if not menu:
            return verdict(results)

        clicked = click_menu_row(menu, "Height range")
        results["clicked Height range Modifier"] = "PASS" if clicked else "FAIL"
        _dismiss_menus(session)
        time.sleep(3.0)

        # layers editing overlay check: OCR the canvas for 'Variable layer height'
        from harness import ocr_util
        img = capture_bgr(session)
        text = ""
        try:
            text = ocr_util.ocr_text(img) if hasattr(ocr_util, "ocr_text") else ""
        except Exception:
            pass
        layers_on = ("Variable layer" in text) or ("Adaptive" in text)
        print(f"[diag] canvas OCR after menu: {text[:120]!r}")
        results["layers editing overlay on"] = "PASS" if layers_on else "FAIL"

        # ---- step 2: select the object in the 3D view ----
        cx, cy = viewport_center(session)
        winutil.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        winutil.real_click_screen(cx, cy)
        time.sleep(1.0)
        frac_selected = has_colored_content(capture_bgr(session))
        print(f"[diag] after click: colored {frac_selected:.2%}")

        # ---- step 3: press Delete (macOS 'Delete' = backspace; Windows = DEL) ----
        for name, vk in (("VK_DELETE", VK_DELETE), ("VK_BACK", VK_BACK)):
            send_key(session, vk)
            time.sleep(1.0)
            frac_now = has_colored_content(capture_bgr(session))
            print(f"[diag] after {name}: colored {frac_now:.2%}")
            gone = frac_now < max(0.004, frac_selected * 0.5)
            results[f"object deleted by {name}"] = "PASS" if gone else "FAIL"
            if gone:
                break

        return verdict(results)
    finally:
        session.close()
        print("[diag] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
