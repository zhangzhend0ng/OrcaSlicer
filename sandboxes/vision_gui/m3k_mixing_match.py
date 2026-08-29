#!/usr/bin/env python3
# m3k_mixing_match.py — Manual-mode matching: mode switch, match, result
# rendering and Confirm.
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entries MixedFilamentBatchDialog (start_batch_match :2273 — Manual mode
# is palette-agnostic and unaffected by the Full Spectrum gate) and
# on_method_changed (:2009 sel==1 -> MANUAL).
# Source facts: the Auto/Manual combo's popup rows are self-drawn (28px
# pitch, popup_top+14 first row); Manual matching runs in a background
# thread; completion renders the color-mapping list (saturated swatches,
# chromatic fraction 0 -> ~0.12 measured) and the result view panel.
# Records: #10 mode switch, #15 matched view renders, #27 Confirm.
#
# Black-box path: open the dialog -> switch the combo to Manual (popup row
# 2, text-confirmed) -> Start Matching -> the color-mapping list renders
# (double-poll chromaticity) -> Confirm becomes clickable -> clicking it
# closes the batch dialog and the app stays alive.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3k] model arrived: {ok_model} (colored {frac:.2%})")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        dlg = mixing_util.open_mixing_dialog(session)
        print(f"[m3k] mixing dialog: {hex(dlg) if dlg else None}")
        results["mixing dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)

        # --- switch match mode Auto -> Manual (popup row 2) ---
        switched = mixing_util.switch_match_mode(session, dlg, "Manual")
        print(f"[m3k] mode switched to Manual: {switched}")
        results["mode switch to Manual"] = "PASS" if switched else "FAIL"

        # --- Start Matching -> result renders (color-mapping list) ---
        ok_start = False
        done = False
        if switched:
            ok_start = mixing_util.click_button(dlg, "Start Matching")
            done = mixing_util.wait_match_done(session, dlg, timeout_s=90.0)
        print(f"[m3k] start={ok_start} match rendered={done}")
        results["manual match completes"] = (
            "PASS" if (ok_start and done) else "FAIL")

        # --- Confirm becomes available; clicking closes the dialog ---
        confirmed = False
        if done:
            time.sleep(1.0)
            # the click may race with background UI churn on consecutive
            # runs: poll for the dialog to close and retry the click once
            import time as _t
            for attempt in range(3):
                ok_confirm = mixing_util.click_button(dlg, "Confirm")
                deadline = _t.monotonic() + 10.0
                gone = False
                while _t.monotonic() < deadline:
                    if mixing_util.find_dialog(session.pid,
                                               timeout_s=1.0) is None:
                        gone = True
                        break
                    _t.sleep(0.5)
                print(f"[m3k] confirm attempt {attempt + 1}: clicked="
                      f"{ok_confirm} dialog_closed={gone}")
                if gone:
                    confirmed = True
                    break
                _t.sleep(1.0)
        results["confirm closes dialog"] = "PASS" if confirmed else "FAIL"

        # --- the app must still be alive and the model present ---
        alive = session.alive()
        frac2 = None
        if alive:
            from m1_minimal_loop import capture_bgr
            from m2_slice_chain import has_colored_content
            frac2 = has_colored_content(capture_bgr(session))
        print(f"[m3k] app alive: {alive}, model colored: {frac2}")
        results["app survives confirm"] = (
            "PASS" if (alive and frac2 and frac2 >= 0.004) else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3k] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
