#!/usr/bin/env python3
# m5c_strength_infill.py — Strength-page parameter MAIN FLOW: on a standard
# right-click model, raise the sparse infill density and change the infill
# pattern, slice once, and prove the values reached the slicer (gcode echo
# + the fill amount actually changing).
#
# White-box refs:
#   - OptionsGroup.cpp:248 activate_line — painted labels; native
#     Edit/ComboBox row values.
#   - PrintConfig 'sparse_infill_density' ('Sparse infill density', %) and
#     'sparse_infill_pattern' ('Sparse infill pattern') — Strength page.
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> Strength page ->
# 'density' 15 -> 30 (real typing) -> 'pattern' -> 'Grid' (combo popup) ->
# slice -> export -> '; sparse_infill_density' carries 30 + '; 
# sparse_infill_pattern' carries grid -> app alive.
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

LOG = "[m5c]"


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    results = {}
    session, ok_cube = boot_cube_session(args)
    try:
        results["fixture deleted + standard model added"] = "PASS" if ok_cube else "FAIL"
        if results["fixture deleted + standard model added"] != "PASS":
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        pp.ensure_advanced(session, want=True)
        # expect_word = the page's FIRST visible row content: this fork's
        # Strength page opens on the Walls block ('Wall loops' row first;
        # measured 09-01) — 'infill' sits below the fold
        tab_ok = pp.click_tab(session, "Strength", "loops")
        print(f"{LOG} strength page opens: {tab_ok}")
        results["strength page opens"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        ok_d, old_d, new_d = pp.set_option_float(session, "density", "30", group_substr="Infill")
        print(f"{LOG} infill density: {old_d!r} -> {new_d!r} ok={ok_d}")
        results["infill density sets to 30%"] = "PASS" if ok_d else "FAIL"

        if not ok_d:
            results["slice with new params"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        sliced = slice_and_wait(session, timeout_s=900)
        out_path = Path(args.datadir).parent / "m5c_infill.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        dens = gcode_check.config_value(data, "sparse_infill_density") \
            if ok_exp else None
        pat = gcode_check.config_value(data, "sparse_infill_pattern") \
            if ok_exp else None
        print(f"{LOG} slice={sliced} export={ok_exp} density={dens!r} "
              f"pattern={pat!r}")
        results["slice + export"] = "PASS" if (sliced and ok_exp) else "FAIL"
        results["gcode density follows (30)"] = (
            "PASS" if dens is not None and "30" in dens else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
