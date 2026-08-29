#!/usr/bin/env python3
# m3b_delete_scene.py — P1-7 + P2-8: delete all / clear the scene.
#
# White-box refs: wx_gui_business_tests.cpp:546 (delete object and clear
# scene update model count) and :574 (topbar edit menu delete-all dispatched
# through the frame handler chain; 'Delete all' = Ctrl+D).
# Source facts: 'Delete all' lives in the Edit submenu of the topbar's
# dropdown menu (MainFrame.cpp:2690/2778, handler
# Plater::delete_all_objects_from_model, gate can_delete_all). The dropdown
# tool is a self-drawn wxAuiToolBar tool (no per-tool HWND) and the menu is
# a NATIVE popup (#32768): its rows hit-test in the menu's own modal loop,
# which ignores message-level clicks — selection needs REAL input
# (SendInput; the topmost menu sits above the WebView2 host, so real clicks
# there are not swallowed — measured 2026-08-29).
#
# Black-box path: load a model -> verify arrival -> open the topbar dropdown
# menu (SetCursorPos + message click) -> hover the Edit row to open the
# submenu -> real-click the 'Delete All' row (probed y — the row geometry
# measured ~12px lower than the naive formula) -> assert the viewport
# chromatic fraction falls back to the empty-bed floor (~0.15%, README
# pitfall #8) and that a Slice click on the emptied scene starts nothing
# (the empty-scene rejection of m3a as a second external signal that the
# scene really is empty).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import topbar_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import (click_slice_start, has_colored_content,  # noqa: E402
                            wait_model_loaded)
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

EMPTY_BED_FLOOR = 0.004  # measured ~0.15%; 0.4% sits with margin below model


def open_edit_submenu(session):
    """Dropdown menu -> hover the Edit row -> the Edit submenu opens.
    Returns (srect, n_items, del_idx) or (None, None, None)."""
    menu = topbar_util.open_dropdown_menu(session)
    if not menu:
        return None, None, None
    rect, hwnd, hmenu = menu
    items = topbar_util.menu_items(hmenu)
    edit_idx = topbar_util.find_item(hmenu, "Edit")
    if edit_idx is None:
        topbar_util.close_menu_windows(session.pid)
        return None, None, None
    topbar_util.hover_row(rect, len(items), edit_idx)
    sub = topbar_util.wait_submenu(session.pid, {hwnd}, timeout_s=5.0)
    if not sub:
        topbar_util.close_menu_windows(session.pid)
        return None, None, None
    srect, _shwnd, shmenu = sub
    sub_items = topbar_util.menu_items(shmenu)
    del_idx = topbar_util.find_item(shmenu, "Delete All")
    if del_idx is None:
        topbar_util.close_menu_windows(session.pid)
        return None, None, None
    return srect, len(sub_items), del_idx


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3b] model arrived: {ok_model} (colored {frac:.2%})")
        results["model arrived"] = "PASS" if ok_model else "FAIL"

        # --- dropdown menu -> Edit submenu -> real-click 'Delete All' ---
        srect, n_items, del_idx = open_edit_submenu(session)
        print(f"[m3b] edit submenu: rect={srect} items={n_items} "
              f"del_idx={del_idx}")
        deleted = False
        if srect:
            cands = topbar_util.submenu_row_candidates(srect, n_items, del_idx)
            left, top, right, _b = srect
            cx = (left + right) // 2
            for k, y in enumerate(cands):
                print(f"[m3b] real-click Delete All candidate y={y} "
                      f"({k + 1}/{len(cands)})")
                winutil.real_click_screen(cx, y)
                time.sleep(2.5)
                frac_after = has_colored_content(capture_bgr(session))
                menus = topbar_util._enum_menu_windows(session.pid)
                print(f"[m3b]   after click: menus={len(menus)} "
                      f"colored={frac_after:.3%}")
                if frac_after < EMPTY_BED_FLOOR:
                    deleted = True
                    break
                if menus:
                    topbar_util.close_menu_windows(session.pid)
                    time.sleep(1.0)
                srect, n_items, del_idx = open_edit_submenu(session)
                if not srect:
                    break
                left, top, right, _b = srect
                cx = (left + right) // 2
        topbar_util.close_menu_windows(session.pid)
        print(f"[m3b] delete-all via menu: {deleted}")
        results["delete-all via Edit menu"] = "PASS" if deleted else "FAIL"

        # --- the model must be gone: chromatic fraction back to empty bed ---
        frac_after = has_colored_content(capture_bgr(session))
        print(f"[m3b] colored fraction after delete-all: {frac_after:.3%} "
              f"(floor {EMPTY_BED_FLOOR:.3%})")
        emptied = frac_after < EMPTY_BED_FLOOR
        results["viewport empty after delete"] = (
            "PASS" if emptied else "FAIL")

        # --- second signal: an emptied scene rejects slicing ---
        if emptied:
            started = click_slice_start(session)
            print(f"[m3b] slice click on empty scene started a job: {started}")
            results["empty scene rejects slice"] = (
                "PASS" if not started else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3b] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
