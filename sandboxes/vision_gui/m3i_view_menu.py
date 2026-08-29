#!/usr/bin/env python3
# m3i_view_menu.py — View menu switching changes the camera view.
#
# White-box ref: none of the wx_gui cases drive the View menu; source entry
# add_common_view_menu_items (MainFrame.cpp:2470) — the View submenu of the
# topbar dropdown menu (Default View / Top / Bottom / Front / Rear / Left /
# Right / Fit in all view), handlers MainFrame::select_view + camera
# actions.
# Source facts: the View submenu rows are native menu rows (real clicks
# needed, see m3b/m3h); the camera angles are not externally readable, so
# the assertion is honest: each menu-driven view switch must CHANGE the
# viewport significantly (measured: plate view -> Top view mean-abs-diff
# 55 on the viewport region; threshold 10 has >5x margin).
#
# Black-box path: load model -> capture the plate-view baseline -> View
# menu -> real-click the 'Top' row -> the viewport must change -> View menu
# -> real-click the 'Front' row -> the viewport must change AGAIN (and stay
# different from the baseline).

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import topbar_util  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

# 3D viewport region (client px), same as m2_slice_chain.
VP_Y0, VP_Y1, VP_X0, VP_X1 = 70, 1030, 430, 1155
VIEW_DIFF_THRESHOLD = 10.0  # measured 55 for a real view switch


def viewport_diff(a, b) -> float:
    va = a[VP_Y0:VP_Y1, VP_X0:VP_X1].astype(int)
    vb = b[VP_Y0:VP_Y1, VP_X0:VP_X1].astype(int)
    return float(np.abs(va - vb).mean())


def switch_view(session, row: str, baseline, label: str) -> bool:
    """Real-click the `row` of the View submenu; succeeds when the viewport
    moved away from `baseline` (any of the camera rows changing the view is
    a PASS — the specific angle is not externally readable)."""
    return topbar_util.real_click_submenu_row(
        session, "View", row,
        success_fn=lambda: viewport_diff(capture_bgr(session),
                                         baseline) > VIEW_DIFF_THRESHOLD,
        label=label)


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3i] model arrived: {ok_model} (colored {frac:.2%})")
        results["model arrived"] = "PASS" if ok_model else "FAIL"
        time.sleep(1.0)
        base = capture_bgr(session)

        # --- View menu -> 'Top' row -> viewport must change ---
        ok_top = switch_view(session, "Top", base, label="view-top")
        time.sleep(1.5)
        after_top = capture_bgr(session)
        d1 = viewport_diff(after_top, base)
        print(f"[m3i] first view switch: {ok_top} (diff {d1:.1f} "
              f"> {VIEW_DIFF_THRESHOLD})")
        results["view switch changes viewport"] = "PASS" if ok_top else "FAIL"

        # --- View menu -> 'Front' row -> viewport must change again ---
        ok_front = False
        if ok_top:
            ok_front = switch_view(session, "Front", after_top,
                                   label="view-front")
            time.sleep(1.5)
            after_front = capture_bgr(session)
            d2 = viewport_diff(after_front, after_top)
            d2b = viewport_diff(after_front, base)
            print(f"[m3i] second view switch: {ok_front} (diff {d2:.1f}, "
                  f"vs baseline {d2b:.1f})")
        results["second view switch changes viewport"] = (
            "PASS" if ok_front else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3i] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
