#!/usr/bin/env python3
# m6d_speed.py — SPEED-page parameter main flow (P1 mainflow backlog):
# Advanced mode -> Speed page -> 'Other layers speed' group -> Outer wall
# speed 120 -> 60 -> slice once -> prove it via the gcode echo
# ('; outer_wall_speed = 60').
#
# White-box refs:
#   - Tab.cpp:2443-2451 — the Speed page: group 'Initial layer speed',
#     then 'Other layers speed' whose FIRST row is outer_wall_speed
#     ('Outer wall speed'), second inner_wall_speed.
#   - GCode.cpp:6638 append_full_config — the header echoes
#     '; outer_wall_speed = 120' on the 0.40 Standard fixture preset.
#
# MEASURED 09-02 (diag_m6d_speed, rounds 1-5):
#   - click_tab('Speed', 'initial'): the page's first screen shows the
#     'Initial layer speed' group ('initial' is the stable expect_word);
#   - the group-title acceptance can rest the title at the band's bottom
#     edge with the first row half-cut — wheel 2 notches down before
#     locating the row;
#   - the SPEED-page option Edits sit at client x=208 (Quality/Strength
#     pages use >=224) — option_edit_at's default x_lo=220 misses them;
#     widen to 200;
#   - commit 60 -> echo '60' (inner_wall_speed stays 150 — a second,
#     untouched-row control).

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

LOG = "[m6d]"


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    results = {}
    session, ok_cube = boot_cube_session(args)
    try:
        results["fixture deleted + standard model added"] = (
            "PASS" if ok_cube else "FAIL")
        if not ok_cube:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        pp.ensure_advanced(session, want=True)
        tab_ok = pp.click_tab(session, "Speed", "initial")
        print(f"{LOG} speed page opens: {tab_ok}")
        results["speed page opens"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        hit = pp.scroll_group_into_view(session, "Other layers")
        print(f"{LOG} 'Other layers' group in view: {bool(hit)}")
        results["other-layers group located"] = (
            "PASS" if hit else "FAIL")
        if not hit:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # the title acceptance may rest the row half-cut at the band's
        # bottom edge — wheel it fully into view (measured 09-02)
        vp = pp.options_viewport(session)
        if vp:
            pp.wheel_viewport(session, vp, 2, delta=-120)
            time.sleep(0.6)

        # Speed-page Edits sit at client x=208 (Quality/Strength >=224,
        # measured) — widen option_edit_at's x_lo
        word, y_row = pp.find_option_row(session, "outer")
        edit = pp.option_edit_at(session, y_row, x_lo=200) if word else None
        print(f"{LOG} outer row y={y_row} edit: "
              f"{pp.to_local(session, edit[0]) if edit else None}")
        results["outer wall speed row resolves"] = (
            "PASS" if edit else "FAIL")
        if not edit:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        new = pp.real_edit_set(session, edit[0], edit[1], "60")
        pp.neutralize_focus(session)
        time.sleep(6.0)  # settle the page rebuild (m5b mechanic)
        ok_set = bool(new and new.startswith("60"))
        print(f"{LOG} commit: {new!r} ok={ok_set}")
        results["outer wall speed commits 60"] = (
            "PASS" if ok_set else "FAIL")

        sliced = slice_and_wait(session, timeout_s=900)
        out_path = Path(args.datadir).parent / "m6d_speed.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        ows = gcode_check.config_value(data, "outer_wall_speed") \
            if ok_exp else None
        iws = gcode_check.config_value(data, "inner_wall_speed") \
            if ok_exp else None
        print(f"{LOG} slice={sliced} export={ok_exp} "
              f"outer_wall_speed={ows!r} inner_wall_speed={iws!r}")
        results["slice + export"] = (
            "PASS" if (sliced and ok_exp) else "FAIL")
        results["gcode outer_wall_speed = 60"] = (
            "PASS" if ows is not None and ows.startswith("60") else "FAIL")
        results["untouched inner_wall_speed stays 150"] = (
            "PASS" if iws is not None and iws.startswith("150") else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
