#!/usr/bin/env python3
# diag_m6d_speed.py — recon for the m6d SPEED-page parameter flow
# (m5c float-edit mechanic on a different page). Proves with log+frame:
#   1. the Speed page opens via click_tab('Speed', expect_word) — the
#      first screen shows the 'Initial layer speed' group ('initial');
#   2. the 'Other layers speed' group scrolls into view and the
#      'Outer wall speed' row resolves to a real Edit
#      (Tab.cpp:2449-2450: group 'Other layers speed', first row
#      outer_wall_speed);
#   3. committing 60 lands in the gcode: '; outer_wall_speed = 60'
#      (default echo is 120 on the 0.40 Standard fixture preset).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import gcode_check  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (add_common_args, export_and_check,  # noqa: E402
                       slice_and_wait)

LOG = "[diag_m6d]"


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    session, ok_cube = boot_cube_session(args)
    try:
        print(f"{LOG} cube: {ok_cube} alive={session.alive()}")
        if not ok_cube:
            return 1
        pp.ensure_advanced(session, want=True)
        tab_ok = pp.click_tab(session, "Speed", "initial")
        print(f"{LOG} speed page opens: {tab_ok}")
        if not tab_ok:
            return 1

        hit = pp.scroll_group_into_view(session, "Other layers")
        print(f"{LOG} 'Other layers' group in view: {bool(hit)}")
        # MEASURED (round 1): the group-title acceptance may rest the title
        # at the band's bottom edge — the first row then sits half-cut and
        # its Edit is out of reach. Wheel the row fully into the band.
        vp = pp.options_viewport(session)
        if vp:
            pp.wheel_viewport(session, vp, 2, delta=-120)
            time.sleep(0.6)
        # MEASURED (round 4): the SPEED-page option Edits sit at client
        # x=208 (Quality/Strength pages use >=224) — option_edit_at's
        # default x_lo=220 misses them; widen to 200.
        word, y_row = pp.find_option_row(session, "outer")
        hit = pp.option_edit_at(session, y_row, x_lo=200) if word else None
        print(f"{LOG} outer row y={y_row} edit: "
              f"{pp.to_local(session, hit[0]) if hit else None}")
        if not hit:
            return 1
        r, h = hit
        new = pp.real_edit_set(session, r, h, "60")
        pp.neutralize_focus(session)
        time.sleep(6.0)
        print(f"{LOG} commit: {new!r}")

        sliced = slice_and_wait(session, timeout_s=900)
        out_path = HERE / "artifacts" / "diag_m6d.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        ows = gcode_check.config_value(data, "outer_wall_speed") if ok_exp else None
        iws = gcode_check.config_value(data, "inner_wall_speed") if ok_exp else None
        print(f"{LOG} slice={sliced} export={ok_exp} "
              f"outer_wall_speed={ows!r} inner_wall_speed={iws!r}")
        print(f"{LOG} alive={session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
