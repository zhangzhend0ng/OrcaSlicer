#!/usr/bin/env python3
# m3l_mixing_delta.py — hover the mapping swatches: the Delta-E grade
# tooltip (#24) and its Good/Fair/Poor band (#22).
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entries MixedFilamentBatchDialog — mapping rows get SetToolTip after a
# match (MixedFilamentBatchDialog.cpp:1118), the tooltip text is
# "Color Difference: <grade> (AE=<value>)" and the grade bands are
# kDeltaEGoodMax=4.0 / kDeltaEFairMax=8.0 (:72).
# Source facts: the tooltip is a wx system tooltip (tooltips_class32) which
# tracks REAL mouse input only (SetCursorPos / WM_MOUSEMOVE injection do
# not arm it — measured); the swatch rows are created after the match in
# the dialog's lower band; OCR (Tesseract eng) reads the tooltip verbatim
# ('Color Difference: Good (AE=0.0)' measured).
#
# Black-box path: open dialog -> Manual -> Start -> match renders -> hover
# a swatch row (real mouse move) -> the tooltip window appears -> OCR it ->
# assert 'Color Difference' + a grade keyword (Good/Fair/Poor) + 'AE='.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util, ocr_util  # noqa: E402
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
        print(f"[m3l] model arrived: {ok_model} (colored {frac:.2%})")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        dlg = mixing_util.open_mixing_dialog(session)
        results["mixing dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)

        switched = mixing_util.switch_match_mode(session, dlg, "Manual")
        results["mode switch to Manual"] = "PASS" if switched else "FAIL"

        done = False
        if switched:
            mixing_util.click_button(dlg, "Start Matching")
            done = mixing_util.wait_match_done(session, dlg, timeout_s=420.0)
        print(f"[m3l] match rendered: {done}")
        results["manual match completes"] = "PASS" if done else "FAIL"

        # --- hover a swatch row -> the Delta-E tooltip appears ---
        tooltip_text = None
        if done:
            time.sleep(1.5)
            rows = mixing_util.swatch_rows(dlg)
            print(f"[m3l] swatch rows: {rows}")
            for row in rows[:4]:
                tt = mixing_util.hover_swatch_row(session, dlg, row)
                if tt:
                    rect, hwnd = tt
                    tooltip_text = ocr_util.ocr_hwnd(hwnd)
                    print(f"[m3l] tooltip rect={rect}: {tooltip_text!r}")
                    break
                time.sleep(0.5)
        results["hover shows tooltip"] = (
            "PASS" if tooltip_text is not None else "FAIL")

        # --- OCR assertions on the tooltip content ---
        if tooltip_text:
            results["tooltip has grade header"] = (
                "PASS" if ocr_util.assert_keywords(
                    tooltip_text, ["color difference"]) else "FAIL")
            grade = any(ocr_util.assert_keywords(tooltip_text, [g])
                        for g in ("good", "fair", "poor"))
            print(f"[m3l] grade keyword: {grade}")
            results["grade keyword present"] = "PASS" if grade else "FAIL"
            has_de = ocr_util.assert_keywords(tooltip_text, ["ae="]) or \
                ocr_util.assert_keywords(tooltip_text, ["ae"])
            print(f"[m3l] Delta-E value present: {has_de}")
            results["delta-e value present"] = "PASS" if has_de else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3l] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
