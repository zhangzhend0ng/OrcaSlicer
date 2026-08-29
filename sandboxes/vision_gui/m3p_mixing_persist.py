#!/usr/bin/env python3
# m3p_mixing_persist.py — the matched scheme persists into the project
# .3mf and reloads (#48).
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entry MixedFilamentBatchDialog apply-on-Confirm (palette rewrite +
# mixed-filament creation) and Plater::save_project (project-level config
# in the .3mf).
# Source facts: Confirm applies the scheme and closes; 'Save Project as'
# (File menu) writes the project config into the .3mf; a fresh launch of
# that file must restore the scheme (the Color Mixing panel shows the
# mixed filament entries).
#
# Black-box path: Manual match -> Confirm -> Save Project as -> close ->
# relaunch the saved file -> the Color Mixing panel shows mixed-filament
# content (chromatic swatches in the panel region) and the mixing dialog
# opens normally.

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util, topbar_util, export_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import has_colored_content, wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402
from m3g_export_3mf import save_project_as  # noqa: E402


def color_mixing_panel_sig(session):
    """Chromatic fraction of the 'Color Mixing' panel region in the main
    frame (the panel sits left of the mixing-match bar at screen y~460)."""
    img = capture_bgr(session)
    frect = winutil.window_rect(session.hwnd)
    # client region of the Color Mixing panel (~x 40-190, y 320-380)
    x0, y0 = 40, 320
    x1, y1 = 190, 400
    sub = img[y0:y1, x0:x1].astype(int)
    spread = sub.max(axis=2) - sub.min(axis=2)
    return float((spread > 40).mean())


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out_path = Path(args.datadir).parent / "m3p_persist.3mf"
    if out_path.exists():
        out_path.unlink()

    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3p] model arrived: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        dlg = mixing_util.open_mixing_dialog(session)
        results["mixing dialog opens"] = "PASS" if dlg else "FAIL"
        matched = False
        if dlg:
            mixing_util.switch_match_mode(session, dlg, "Manual")
            mixing_util.click_button(dlg, "Start Matching")
            matched = mixing_util.wait_match_done(session, dlg,
                                                  timeout_s=90.0)
            print(f"[m3p] match: {matched}")
            results["manual match completes"] = "PASS" if matched else "FAIL"
            if matched:
                time.sleep(1.0)
                ok_c = mixing_util.click_button(dlg, "Confirm")
                time.sleep(2.0)
                gone = mixing_util.find_dialog(session.pid,
                                               timeout_s=3.0) is None
                print(f"[m3p] confirm={ok_c} dialog closed={gone}")
                results["confirm applies scheme"] = (
                    "PASS" if (ok_c and gone) else "FAIL")
        # the panel now shows the mixed filament entries
        sig = color_mixing_panel_sig(session)
        print(f"[m3p] color mixing panel colored: {sig:.3f}")
        results["panel shows scheme"] = (
            "PASS" if matched and sig > 0.01 else "FAIL")

        # --- save the project and relaunch it ---
        ok_save = False
        if matched:
            ok_save = save_project_as(session, out_path)
            print(f"[m3p] saved: {ok_save} "
                  f"({out_path.stat().st_size if out_path.exists() else 0}B)")
        results["project saved"] = "PASS" if ok_save else "FAIL"
    finally:
        session.close()
        print("[m3p] app closed")

    if ok_save:
        args.datadir = Path(args.datadir).parent / "m3p_profile_b"
        session2 = boot_session(args, model=out_path)
        try:
            ok_re, frac2 = wait_model_loaded(session2, timeout_s=45)
            print(f"[m3p] reloaded model: {ok_re} ({frac2:.2%})")
            sig2 = color_mixing_panel_sig(session2)
            print(f"[m3p] panel colored after reload: {sig2:.3f}")
            results["scheme survives reload"] = (
                "PASS" if (ok_re and sig2 > 0.01) else "FAIL")
            dlg2 = mixing_util.open_mixing_dialog(session2)
            print(f"[m3p] dialog reopens: {hex(dlg2) if dlg2 else None}")
            results["dialog reopens after reload"] = (
                "PASS" if dlg2 else "FAIL")
        finally:
            session2.close()
            print("[m3p] app closed")
    return verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
