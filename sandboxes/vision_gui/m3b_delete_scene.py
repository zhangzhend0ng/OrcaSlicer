#!/usr/bin/env python3
# m3b_delete_scene.py — P1-7 + P2-8: delete all / clear the scene.
#
# White-box refs: wx_gui_business_tests.cpp:546 (delete object and clear
# scene update model count) and :574 (topbar edit menu delete-all).
# Source facts: 'Delete all' is Ctrl+D, bound under the topbar's top menu
# (wx_gui_business_tests.cpp:588 find_menu_item_by_accel '\tCtrl+D').
#
# Black-box path: load a model -> verify arrival -> send Ctrl+D to the main
# window -> assert the viewport chromatic fraction falls back to the empty
# bed floor (~0.15%, README pitfall #8) — the model disappearing is the
# externally observable state flip.
#
# Fallback if keyboard accelerators don't route: click the topbar Edit menu
# and its 'Delete all' row (popup-row click without root piercing).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import has_colored_content  # noqa: E402
from m3_common import (MIXED_3MF, add_common_args, boot_session,  # noqa: E402
                       verdict)
from m2_slice_chain import wait_model_loaded  # noqa: E402

EMPTY_BED_FLOOR = 0.004  # measured ~0.15%; 0.4% sits with margin below model


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
        time.sleep(1.0)

        # --- try Ctrl+D keyboard accelerator on the main window ---
        winutil.msg_key(session.hwnd, ord("D"), winutil.VK_CONTROL)
        time.sleep(2.0)
        frac_after = has_colored_content(capture_bgr(session))
        print(f"[m3b] after Ctrl+D colored fraction: {frac_after:.3%}")
        ctrl_d_worked = frac_after < EMPTY_BED_FLOOR

        if not ctrl_d_worked:
            # Fallback: topbar Edit menu -> Delete all row.
            # Locate the topbar menu buttons by text (File/Edit/...).
            from harness import export_util
            btns = export_util.topbar_buttons(session.hwnd)
            print("[m3b] Ctrl+D had no effect; trying topbar Edit menu")
            # topbar menus live left of the button cluster; enumerate the
            # whole topbar for a text button 'Edit'
            edit_btn = None
            for text, rect, ch in export_util._children_texts(session.hwnd):
                if 100 <= rect[1] <= 140 and text.strip() in ("Edit", "编辑"):
                    edit_btn = (rect, ch)
                    break
            if edit_btn:
                rect, _ = edit_btn
                winutil.msg_click_screen((rect[0] + rect[2]) // 2,
                                         (rect[1] + rect[3]) // 2, session.hwnd)
                time.sleep(1.0)
                # the menu popup is a top-level panel; find a row 'Delete all'
                popup = export_util.wait_popup(session.pid, timeout_s=5.0)
                if popup:
                    rows = export_util._children_texts(popup[3])
                    print("[m3b] menu rows:", [(t, r) for t, r, h in rows])
                    del_row = [r for r in rows if "Delete all" in r[0]]
                    if del_row:
                        rc = del_row[0][1]
                        winutil.msg_click_screen((rc[0] + rc[2]) // 2,
                                                 (rc[1] + rc[3]) // 2)
                        time.sleep(2.0)
                        frac_after = has_colored_content(capture_bgr(session))
                        ctrl_d_worked = frac_after < EMPTY_BED_FLOOR
        print(f"[m3b] final colored fraction: {frac_after:.3%} "
              f"(floor {EMPTY_BED_FLOOR:.3%})")
        results["clear scene empties viewport"] = (
            "PASS" if ctrl_d_worked else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3b] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
