#!/usr/bin/env python3
# m3j_mixing_entry.py — color-mixing match entry, default mode and the
# Auto-mode nozzle gate.
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entries MixedFilamentBatchDialog (Plater.cpp:2578 open + gate: model
# colors + >=2 filaments) and start_batch_match()
# (MixedFilamentBatchDialog.cpp:2273).
# Source facts: the entry is the add button at the right end of the
# 'Color Mixing Match' title bar; the match-mode combo defaults to 'Auto'
# (MixedFilamentBatchDialog.cpp:1269); on the seeded U1 0.8 nozzle there is
# no Full Spectrum preset, so Auto-mode Start Matching gates with a
# RichMessageDialog ('Automatic color mixing matching is not supported for
# the current nozzle diameter...', :2290) — record #49.
#
# Black-box path: load the multicolor fixture -> open the dialog -> the
# dialog appears and the mode combo shows 'Auto' -> click Start Matching ->
# a warning dialog appears with a dismissable 'Got it' button -> dismiss ->
# the batch dialog is still alive.

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
        print(f"[m3j] model arrived: {ok_model} (colored {frac:.2%})")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        # --- entry: add button -> the batch dialog appears ---
        dlg = mixing_util.open_mixing_dialog(session)
        print(f"[m3j] mixing dialog: {hex(dlg) if dlg else None}")
        results["mixing dialog opens"] = "PASS" if dlg else "FAIL"

        if dlg:
            # --- default match mode is Auto ---
            combo = mixing_util.child_by_text(dlg, "Auto")
            if not combo:
                combo = mixing_util.child_by_text(dlg, "Manual")
            mode = mixing_util.combo_text(combo[3]) if combo else "?"
            print(f"[m3j] default match mode: {mode!r}")
            results["default mode is Auto"] = (
                "PASS" if mode == "Auto" else "FAIL")

            # --- Auto-mode Start Matching -> nozzle warning dialog ---
            ok_start = mixing_util.click_button(dlg, "Start Matching")
            warn = mixing_util.wait_warning_dialog(session.pid, dlg,
                                                   timeout_s=8.0)
            print(f"[m3j] start clicked: {ok_start}, warning: "
                  f"{hex(warn) if warn else None}")
            results["Auto mode gates on nozzle"] = (
                "PASS" if (ok_start and warn) else "FAIL")
            if warn:
                time.sleep(1.0)
                ok_dismiss = mixing_util.dismiss_dialog(session.pid, warn)
                print(f"[m3j] warning dismissed: {ok_dismiss}")
                results["warning dismissable"] = (
                    "PASS" if ok_dismiss else "FAIL")
                # the batch dialog must still be alive
                alive = mixing_util.find_dialog(session.pid, timeout_s=3.0)
                print(f"[m3j] batch dialog alive after dismiss: "
                      f"{hex(alive) if alive else None}")
                results["dialog survives warning"] = (
                    "PASS" if alive else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3j] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
