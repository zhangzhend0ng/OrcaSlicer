#!/usr/bin/env python3
# m5e_combo_params.py — cross-page parameter COMBINATION main flow: on a
# standard right-click model, change THREE parameters on THREE different
# process pages (Quality layer height, Strength infill density, Support
# enable + type), slice ONCE, and prove every value reached the slicer
# together (multiple gcode echoes) with the app healthy.
#
# White-box refs:
#   - OptionsGroup.cpp:248 activate_line — painted labels; native
#     Edit/ComboBox/checkbox row values (m5b/m5c/m5d mechanics).
#   - PrintConfig echo in the gcode header ('; layer_height',
#     '; sparse_infill_density', '; enable_support') — m5a-m5d precedent.
#   - layer-height limits for the U1 (0.8 nozzle) machine preset:
#     min 0.16 / max 0.56 (machine json), so 0.3 is in range and no
#     Tab.cpp:1786 Adjust/Ignore dialog fires (negative path is m5f).
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> Advanced ON ->
# Quality: 'Layer height' 0.3 -> Strength: 'density' 30 -> Support:
# 'Enable support' ON + Type combo Tree -> Normal (m5d popup mechanic,
# factored as process_panel.set_combo_by_popup) -> slice + export ->
# '; layer_height = 0.3' + '; sparse_infill_density' carries 30 +
# '; enable_support = 1/true' -> app alive.
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

LOG = "[m5e]"


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

        # --- param 1/3: Quality page, Layer height 0.3 (m5b positional
        # path: the page opens AT TOP, topmost float Edit = Layer height)
        tab_ok = pp.click_tab(session, "Quality", "height")
        print(f"{LOG} quality page opens: {tab_ok}")
        results["quality page opens"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)
        hit = pp.wait_float_edit(session)
        ok_lh = False
        old_lh = new_lh = None
        if hit:
            r, h, old_lh = hit
            new_lh = pp.real_edit_set(session, r, h, "0.3")
            pp.neutralize_focus(session)
            ok_lh = bool(new_lh and new_lh.startswith("0.3"))
        print(f"{LOG} layer height: {old_lh!r} -> {new_lh!r} ok={ok_lh}")
        results["quality: layer height 0.3"] = "PASS" if ok_lh else "FAIL"
        time.sleep(6.0)  # config-change rebuild: a real click mid-rebuild
        # crashed the app (measured 09-01); settle between pages
        if not ok_lh:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- param 2/3: Strength page, sparse infill density 30 (m5c)
        tab_ok = pp.click_tab(session, "Strength", "loops")
        print(f"{LOG} strength page opens: {tab_ok}")
        results["strength page opens"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)
        ok_d, old_d, new_d = pp.set_option_float(
            session, "density", "30", group_substr="Infill")
        print(f"{LOG} infill density: {old_d!r} -> {new_d!r} ok={ok_d}")
        results["strength: infill density 30%"] = (
            "PASS" if ok_d else "FAIL")
        time.sleep(6.0)
        if not ok_d:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- param 3/3: Support page, enable + Type Tree -> Normal (m5d;
        # the default Tree (auto) type leaves the U1 0.8 preset INVALID:
        # organic tip diameter < support extrusion width -> Slice grayed)
        tab_ok = pp.click_tab(session, "Support", "support")
        print(f"{LOG} support page opens: {tab_ok}")
        results["support page opens"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        st, rect = pp.set_option_checkbox(session, "Enable", True,
                                          group_substr="Support")
        print(f"{LOG} enable support: state={st} rect={rect}")
        results["support: enable checks on"] = "PASS" if st is True \
            else "FAIL"
        time.sleep(6.0)  # checkbox commit also rebuilds the page
        _located, ok_type = pp.set_combo_by_popup(
            session, "Tree", "Normal", log=LOG)
        print(f"{LOG} support type -> normal: {ok_type}")
        results["support: type switches to Normal"] = (
            "PASS" if ok_type else "FAIL")

        # --- ONE slice for the whole combination
        sliced = slice_and_wait(session, timeout_s=900)
        out_path = Path(args.datadir).parent / "m5e_combo.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        lh = gcode_check.config_value(data, "layer_height") if ok_exp else None
        dens = gcode_check.config_value(data, "sparse_infill_density") \
            if ok_exp else None
        es = gcode_check.config_value(data, "enable_support") if ok_exp \
            else None
        print(f"{LOG} slice={sliced} export={ok_exp} layer_height={lh!r} "
              f"density={dens!r} enable_support={es!r}")
        results["slice + export (one pass)"] = (
            "PASS" if (sliced and ok_exp) else "FAIL")
        results["gcode layer_height = 0.3"] = (
            "PASS" if lh is not None and lh.startswith("0.3") else "FAIL")
        results["gcode density follows (30)"] = (
            "PASS" if dens is not None and "30" in dens else "FAIL")
        # boolean echo is build-encoded: '1' here (measured 09-01), some
        # builds write 'true' — accept both
        results["gcode enable_support = true"] = (
            "PASS" if es is not None and es.lower().startswith(("true", "1"))
            else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
