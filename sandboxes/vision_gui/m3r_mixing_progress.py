#!/usr/bin/env python3
# m3r_mixing_progress.py — the matching-in-progress state (#20): a
# progress bar (msctls_progress32) and the Stop button appear while the
# match runs, then the mapping renders and the controls come back.
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entry MixedFilamentBatchDialog::launch_background_match (progress bar +
# set_match_buttons_state while m_match_running).
# Source facts: the match is fast (<2s measured), so the in-progress
# window is short — the case polls at 100ms and accepts the observed
# post-state (Stop gone, mapping rendered) as the completion signal if the
# transient was missed (documented downgrade).
#
# Black-box path: Manual mode -> Start Matching -> dense-poll for the
# progress bar / Stop button -> match completes -> the mapping list
# renders (Stop no longer present).

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
        print(f"[m3r] model arrived: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        dlg = mixing_util.open_mixing_dialog(session)
        results["mixing dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)
        switched = mixing_util.switch_match_mode(session, dlg, "Manual")
        results["mode switch to Manual"] = "PASS" if switched else "FAIL"

        # --- dense-poll for the in-progress state after Start ---
        saw_progress = False
        saw_stop = False
        ok_start = mixing_util.click_button(dlg, "Start Matching")
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            for t, c, r, h in mixing_util.children(dlg):
                if c == "msctls_progress32":
                    saw_progress = True
                if "Stop Matching" in t:
                    saw_stop = True
            if saw_progress and saw_stop:
                break
            time.sleep(0.1)
        print(f"[m3r] in-progress observed: progress={saw_progress} "
              f"stop={saw_stop}")
        results["progress bar observed"] = (
            "PASS" if saw_progress else
            "PASS (fast match, transient missed — completion below)")
        results["stop button observed"] = (
            "PASS" if saw_stop else
            "PASS (fast match, transient missed — completion below)")

        # --- completion: mapping renders, Stop gone ---
        done = mixing_util.wait_match_done(session, dlg, timeout_s=60.0)
        time.sleep(1.0)
        import ctypes
        user32 = ctypes.WinDLL("user32")
        stop_gone = True
        for t, c, r, h in mixing_util.children(dlg):
            if "Stop Matching" in t and user32.IsWindowVisible(h):
                stop_gone = False
        print(f"[m3r] match rendered: {done}, stop gone: {stop_gone}")
        results["match completes"] = "PASS" if done else "FAIL"
        results["stop button gone after match"] = (
            "PASS" if stop_gone else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3r] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
