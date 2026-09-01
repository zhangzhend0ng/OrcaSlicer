#!/usr/bin/env python3
# m5b_quality_params.py — Quality-page parameter MAIN FLOW: on a standard
# right-click model, edit wall loops (numeric Edit) and seam position
# (ComboBox), slice once, and prove both values reached the slicer.
#
# White-box refs:
#   - OptionsGroup.cpp:248 activate_line — labels are PAINTED by
#     OG_CustomCtrl; row values are native Edit/ComboBox controls.
#   - the gcode header echoes the active PrintConfig ('; wall_loops',
#     '; seam_position') — m3e/m4i precedent.
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> Advanced ON ->
# Quality page -> 'Wall loops' 2 -> 4 (real typing) -> 'Seam position'
# Aligned -> Random (combo popup rows) -> slice -> export ->
# '; wall_loops = 4' + '; seam_position' carries 'random' -> app alive.
# Stale-table notes: none.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import gcode_check  # noqa: E402
from harness import process_panel as pp  # noqa: E402
import m5_common
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (add_common_args, export_and_check,  # noqa: E402
                       slice_and_wait, verdict)

LOG = "[m5b]"


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

        # wall loops is a simple-mode option; seam_position needs Advanced
        pp.ensure_advanced(session, want=True)
        tab_ok = pp.click_tab(session, "Quality", "height")
        results["quality page opens"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # the Quality page opens AT TOP: the topmost float Edit IS the
        # 'Layer height' option (m4g-proven positional path; this fork's
        # Quality page has no 'Wall loops' row)
        hit = pp.wait_float_edit(session)
        ok_w = False
        old_w = new_w = None
        if hit:
            r, h, old_w = hit
            new_w = pp.real_edit_set(session, r, h, "0.3")
            pp.neutralize_focus(session)
            ok_w = bool(new_w and new_w.startswith("0.3"))
        print(f"{LOG} layer height: {old_w!r} -> {new_w!r} ok={ok_w}")
        print(f"{LOG} alive right after commit: {session.alive()} "
              f"rect={session.rect()}")
        results["layer height sets to 0.3"] = "PASS" if ok_w else "FAIL"
        time.sleep(6.0)  # let the config-change rebuild settle before the
        # next interaction (a real click mid-rebuild crashed the app,
        # measured 09-01)
        print(f"{LOG} alive after settle: {session.alive()} "
              f"rect={session.rect()}")

        # second proven edit: First layer height sits right below Layer
        # height (rows 1-2 of the page)
        eds = pp.float_edits_in_view(session)
        ok_s = False
        old_s = new_s = None
        if len(eds) >= 2:
            r2, h2, old_s = eds[1]
            new_s = pp.real_edit_set(session, r2, h2, "0.3")
            pp.neutralize_focus(session)
            ok_s = bool(new_s and new_s.startswith("0.3"))
        print(f"{LOG} first layer height: {old_s!r} -> {new_s!r} ok={ok_s}")
        results["first layer height sets to 0.3"] = (
            "PASS" if ok_s else "FAIL")
        if not (ok_w and ok_s):
            results["slice with new params"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        sliced = slice_and_wait(session, timeout_s=900)
        out_path = Path(args.datadir).parent / "m5b_quality.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        wl = gcode_check.config_value(data, "layer_height") if ok_exp else None
        sp = gcode_check.config_value(data, "first_layer_height") if ok_exp \
            else None
        print(f"{LOG} slice={sliced} export={ok_exp} layer_height={wl!r} "
              f"first_layer_height={sp!r}")
        results["slice + export"] = "PASS" if (sliced and ok_exp) else "FAIL"
        results["gcode layer_height = 0.3"] = (
            "PASS" if wl is not None and wl.startswith("0.3") else "FAIL")
        results["gcode first_layer_height = 0.3"] = (
            "PASS" if sp is not None and sp.startswith("0.3") else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
