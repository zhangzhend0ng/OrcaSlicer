#!/usr/bin/env python3
# m5a_preset_cycle.py — the preset-level MAIN FLOW: on a standard model
# added via the plate right-click menu, cycle the PROCESS preset and prove
# the slicer follows. The gcode artifacts are kept for the evidence chain.
#
# White-box refs:
#   - m3e precedent: the preset selector is a wxWindowNR whose window text
#     carries the preset name; its popup rows are self-drawn 'panel' rows.
#   - the gcode header echoes the active PrintConfig ('; layer_height =
#     0.4') — the strongest black-box proof a preset REACHED the slicer.
#
# Black-box path: boot EMPTY -> right-click Add Primitive > Cube -> slice +
# export A (baseline 0.40) -> switch preset '0.24 Standard' -> slice +
# export B -> switch '0.32 Standard' -> slice + export C -> switch back
# '0.40' -> slice + export D -> assert '; layer_height' == 0.4/0.24/0.32/0.4
# -> app alive.
# Stale-table notes: none.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import gcode_check  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (add_common_args, export_and_check,  # noqa: E402
                       slice_and_wait, verdict)

LOG = "[m5a]"
STEPS = [("baseline 0.40", "0.40 Standard", "0.4"),
         ("switch 0.24", "0.24 Standard", "0.24"),
         ("switch 0.32", "0.32 Standard", "0.32"),
         ("switch back 0.40", "0.40 Standard", "0.4")]


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    results = {}
    session, ok_cube = boot_cube_session(args)
    try:
        results["fixture deleted + standard model added"] = "PASS" if ok_cube else "FAIL"
        if results["fixture deleted + standard model added"] != "PASS":
            results["preset cycle"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        combo_ok = pp.find_process_preset_combo(session)[1] is not None
        results["preset selector located"] = "PASS" if combo_ok else "FAIL"
        if not combo_ok:
            return verdict(results)

        for step_name, preset_sub, want_lh in STEPS:
            switched = pp.switch_process_preset(session, preset_sub)
            print(f"{LOG} {step_name}: switched={switched}")
            results[f"preset: {step_name}"] = "PASS" if switched else "FAIL"
            if not switched:
                results["app alive"] = "PASS" if session.alive() else "FAIL"
                return verdict(results)
            time.sleep(1.0)
            sliced = slice_and_wait(session, timeout_s=900)
            out_path = Path(args.datadir).parent / \
                f"m5a_{want_lh.replace('.', '_')}.gcode"
            if out_path.exists():
                out_path.unlink()
            ok_exp, data = export_and_check(session, out_path)
            lh = gcode_check.config_value(data, "layer_height") if ok_exp \
                else None
            print(f"{LOG} {step_name}: slice={sliced} export={ok_exp} "
                  f"layer_height={lh!r} ({out_path.name})")
            results[f"{step_name}: slice+export"] = (
                "PASS" if (sliced and ok_exp) else "FAIL")
            results[f"{step_name}: gcode follows ({want_lh})"] = (
                "PASS" if lh is not None and lh.startswith(want_lh)
                else "FAIL")
            if not (sliced and ok_exp):
                break

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
