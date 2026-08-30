#!/usr/bin/env python3
# m3s_mixing_hover.py — dialog controls show hover tooltips (#8, downgraded
# smoke): hovering known controls raises a tooltips_class32 window whose
# text is OCR-readable.
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entry MixedFilamentBatchDialog (SetToolTip on the add/remove buttons,
# swatch rows, mode combo).
# Source facts: wx system tooltips only track REAL mouse input (measured);
# the tooltip text is readable via Tesseract (ocr_util).
#
# Black-box path: Manual mode -> hover the add-filament button and a swatch
# row -> a tooltip window appears and OCR reads non-empty text.

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
        print(f"[m3s] model arrived: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        dlg = mixing_util.open_mixing_dialog(session)
        results["mixing dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)
        mixing_util.switch_match_mode(session, dlg, "Manual")
        time.sleep(1.0)

        # --- hover the add/remove filament buttons ---
        from m3m_mixing_filaments import button_rects
        rm_btn, add_btn = button_rects(dlg)
        targets = [r for r in (add_btn, rm_btn) if r]
        texts = []
        for rect in targets:
            tt = mixing_util.hover_swatch_row(
                session, dlg, (rect[0] - 20, rect[1], rect[2] + 20,
                               rect[3]), dwell_s=3.0)
            if tt:
                texts.append(ocr_util.ocr_hwnd(tt[1]))
                print(f"[m3s] tooltip on button {rect}: {texts[-1]!r}")
        print(f"[m3s] button tooltips: {len(texts)}")
        results["filament buttons show tooltips"] = (
            "PASS" if texts and all(t.strip() for t in texts) else "FAIL")

        # --- after a match, hover a swatch row -> the Delta-E tooltip ---
        ok_start = mixing_util.click_button(dlg, "Start Matching")
        done = mixing_util.wait_match_done(session, dlg, timeout_s=420.0)
        print(f"[m3s] match: {ok_start}/{done}")
        swatch_tip = None
        if done:
            time.sleep(1.5)
            rows = mixing_util.swatch_rows(dlg)
            for row in rows[:3]:
                tt = mixing_util.hover_swatch_row(session, dlg, row)
                if tt:
                    swatch_tip = ocr_util.ocr_hwnd(tt[1])
                    print(f"[m3s] swatch tooltip: {swatch_tip!r}")
                    break
        results["swatch hover shows tooltip"] = (
            "PASS" if swatch_tip else "FAIL")
        if swatch_tip:
            results["swatch tooltip readable"] = (
                "PASS" if ocr_util.assert_keywords(
                    swatch_tip, ["color difference"]) else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3s] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
