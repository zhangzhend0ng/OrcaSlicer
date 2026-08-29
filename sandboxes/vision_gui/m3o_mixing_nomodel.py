#!/usr/bin/env python3
# m3o_mixing_nomodel.py — the entry gates on a multicolor model (#28).
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entry Plater.cpp:2557 — with no model the Color Mixing Match button pops
# a RichMessageDialog ('No model detected. Import a multi-color model to
# continue.') and does NOT open the batch dialog.
#
# Black-box path: load the fixture -> delete all objects (Edit menu) ->
# click the Color Mixing Match entry -> the no-model prompt appears (OCR:
# 'no model detected') with a dismissable 'Got it' -> the batch dialog does
# NOT open -> the app stays alive.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util, ocr_util, topbar_util  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import has_colored_content, wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

EMPTY_FLOOR = 0.004


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3o] model arrived: {ok_model} (colored {frac:.2%})")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        # --- clear the scene (Edit menu Delete All) ---
        deleted = topbar_util.real_click_submenu_row(
            session, "Edit", "Delete All",
            success_fn=lambda: has_colored_content(
                capture_bgr(session)) < EMPTY_FLOOR,
            label="delete-all")
        print(f"[m3o] scene cleared: {deleted}")
        results["scene cleared"] = "PASS" if deleted else "FAIL"

        # --- entry -> the no-model prompt, not the batch dialog ---
        dlg = mixing_util.open_mixing_dialog(session, timeout_s=6.0)
        print(f"[m3o] batch dialog opened: {hex(dlg) if dlg else None}")
        results["batch dialog NOT opened"] = (
            "PASS" if dlg is None else "FAIL")
        prompt = None
        for cls, txt, rect, hwnd in mixing_util.toplevel(session.pid):
            if cls == "#32770" and rect[3] - rect[1] < 300:
                prompt = hwnd
                break
        print(f"[m3o] prompt dialog: {hex(prompt) if prompt else None}")
        results["no-model prompt appears"] = (
            "PASS" if prompt else "FAIL")
        if prompt:
            time.sleep(0.5)
            text = ocr_util.ocr_hwnd(prompt)
            print(f"[m3o] prompt text: {text!r}")
            results["prompt mentions no model"] = (
                "PASS" if ocr_util.assert_keywords(
                    text, ["no model detected"]) else "FAIL")
            ok_dismiss = mixing_util.dismiss_dialog(session.pid, prompt)
            print(f"[m3o] prompt dismissed: {ok_dismiss}")
            results["prompt dismissable"] = (
                "PASS" if ok_dismiss else "FAIL")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3o] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
