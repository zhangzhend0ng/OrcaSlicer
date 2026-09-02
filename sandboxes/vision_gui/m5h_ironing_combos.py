#!/usr/bin/env python3
# m5h_ironing_combos.py — Ironing + advanced-page COMBO GROUP main flow:
# switch TWO options-panel combos on the Quality page (Ironing Type, Seam
# Position) via the popup-row mechanic, slice once, prove both enum values
# reached the slicer via the gcode echo.
#
# White-box refs:
#   - PrintConfig.cpp:3560 — 'ironing_type' enum (no ironing / top /
#     topmost / solid; labels 'No ironing' / 'Top surfaces' / 'Topmost
#     surface' / 'All solid layer'), default NoIroning, comAdvanced.
#   - 'seam_position' enum (aligned / nearest / back / random), default
#     'aligned' — m5b's planned-but-dropped second combo.
#   - Tab.cpp:2331 — the 'Ironing' group lives on the Quality page, below
#     Seam/Precision.
#   - the gcode header echoes enum CONFIG VALUES ('; ironing_type =
#     topmost', '; seam_position = random').
#
# MEASURED 09-02 (attempts 1-14):
#   - the Ironing group sits deep on the page: scroll it in first, and do
#     NOT wheel during the post-commit rebuild (killed the app twice);
#   - the Ironing Type value locates by OCR word SEQUENCE ('no','ironing')
#     — a single 'no' would also match 'nozzle';
#   - the Ironing PATTERN row's painted value resists OCR (psm 3 AND 6)
#     and its control resists WindowFromPoint/option_combo_at — replaced
#     by Seam Position, whose 'Aligned' value OCRs reliably.
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> Advanced ON ->
# Quality page -> Ironing Type 'No ironing' -> Topmost (popup) -> long
# settle -> tab round-trip reset -> Seam position Aligned -> Random
# (popup) -> slice + export -> '; ironing_type = topmost' +
# '; seam_position = random' -> app alive.
# Stale-table notes: none.

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import gcode_check  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from harness import winutil  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (add_common_args, export_and_check,  # noqa: E402
                       slice_and_wait, verdict)

LOG = "[m5h]"


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
        tab_ok = pp.click_tab(session, "Quality", "height")
        print(f"{LOG} quality page opens: {tab_ok}")
        results["quality page opens"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- combo 1/2: Ironing Type 'No ironing' -> Topmost ---
        # MEASURED 09-02: the Ironing group sits BELOW Seam/Precision —
        # scroll it in first (m5c mechanic). NO post-commit verify wheels:
        # scrolling during the options rebuild KILLED the app twice
        # (PrintWindow DC-gone after the commit); long settle instead and
        # the gcode echo is the only judge.
        hit = pp.scroll_group_into_view(session, "Ironing")
        print(f"{LOG} ironing group scrolled in: {bool(hit)}")
        results["ironing group located"] = "PASS" if hit else "FAIL"
        if not hit:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)
        _located, info_type = pp.set_combo_by_popup(
            session, ("no", "ironing"), "topmost", log=LOG, psm=6)
        print(f"{LOG} ironing type click reported: {info_type} "
              f"alive={session.alive()}")
        pp.neutralize_focus(session)
        time.sleep(12.0)  # LONG settle: rebuild + wheel do not mix here

        # --- combo 2/2: Seam position 'Aligned' -> Random. The tab
        #     round-trip resets the viewport after the Ironing commit
        #     (m5e mechanic); the 'Aligned' painted value OCRs reliably.
        pp.click_tab(session, "Strength", "loops")
        pp.click_tab(session, "Quality", "height")
        pp.scroll_group_into_view(session, "Seam")
        _located, info_seam = pp.set_combo_by_popup(
            session, "Aligned", "random", log=LOG, psm=6)
        print(f"{LOG} seam position click reported: {info_seam} "
              f"alive={session.alive()}")
        pp.neutralize_focus(session)
        time.sleep(12.0)

        sliced = slice_and_wait(session, timeout_s=900)
        out_path = Path(args.datadir).parent / "m5h_ironing.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        it = gcode_check.config_value(data, "ironing_type") if ok_exp else None
        sp = gcode_check.config_value(data, "seam_position") if ok_exp else None
        print(f"{LOG} slice={sliced} export={ok_exp} ironing_type={it!r} "
              f"seam_position={sp!r}")
        results["slice + export"] = "PASS" if (sliced and ok_exp) else "FAIL"
        results["gcode ironing_type = topmost"] = (
            "PASS" if it is not None and "topmost" in it.lower() else "FAIL")
        results["gcode seam_position = random"] = (
            "PASS" if sp is not None and "random" in sp.lower() else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
