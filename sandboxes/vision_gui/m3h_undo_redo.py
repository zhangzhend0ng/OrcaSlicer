#!/usr/bin/env python3
# m3h_undo_redo.py — P1-6 (menu half): undo/redo restore the scene through
# the topbar Edit menu.
#
# White-box ref: wx_gui_business_tests.cpp:505 — undo and redo restore the
# instance transform through the real UndoRedo stack (Plater::undo/redo).
# This case exercises the same stack over the DELETE-ALL business path
# (P1-7/P2-8): delete_all_objects_from_model takes an undo snapshot
# (Plater.cpp:12921 "Delete All Objects"), so Undo must bring the model
# back and Redo must remove it again.
# Source facts: Undo/Redo are rows of the topbar dropdown menu's Edit
# submenu (MainFrame.cpp:2660/2666, handlers m_plater->undo()/redo(), gates
# can_undo/can_redo); native menu rows need REAL clicks (see m3b).
#
# Black-box path: load model -> delete all (Edit menu, real click) -> the
# scene is empty -> Undo (Edit menu, real click) -> the model ARRIVES again
# (viewport chromaticity >= 1%, double-poll) -> Redo (Edit menu, real
# click) -> the scene is empty again (< 0.4%).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import topbar_util  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import (MODEL_COLORED_THRESHOLD, has_colored_content,  # noqa: E402
                            wait_model_loaded)
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

EMPTY_BED_FLOOR = 0.004


def colored(session) -> float:
    return has_colored_content(capture_bgr(session))


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3h] model arrived: {ok_model} (colored {frac:.2%})")
        results["model arrived"] = "PASS" if ok_model else "FAIL"

        # --- delete all (Edit menu) -> empty ---
        deleted = topbar_util.real_click_submenu_row(
            session, "Edit", "Delete All",
            success_fn=lambda: colored(session) < EMPTY_BED_FLOOR,
            label="delete-all")
        print(f"[m3h] delete-all: {deleted}")
        results["delete-all empties scene"] = "PASS" if deleted else "FAIL"

        # --- Undo (Edit menu) -> the model comes back ---
        undone = False
        if deleted:
            undone = topbar_util.real_click_submenu_row(
                session, "Edit", "Undo",
                success_fn=lambda: colored(session) >=
                MODEL_COLORED_THRESHOLD,
                label="undo")
        print(f"[m3h] undo restores model: {undone}")
        results["undo restores scene"] = "PASS" if undone else "FAIL"

        # --- Redo (Edit menu) -> empty again ---
        redone = False
        if undone:
            redone = topbar_util.real_click_submenu_row(
                session, "Edit", "Redo",
                success_fn=lambda: colored(session) < EMPTY_BED_FLOOR,
                label="redo")
        print(f"[m3h] redo empties scene: {redone}")
        results["redo empties scene again"] = "PASS" if redone else "FAIL"

        return verdict(results)
    finally:
        session.close()
        print("[m3h] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
