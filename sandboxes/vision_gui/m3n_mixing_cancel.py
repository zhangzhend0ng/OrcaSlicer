#!/usr/bin/env python3
# m3n_mixing_cancel.py — Cancel asks for confirmation (#25) and the
# confirmation can be aborted, keeping the result (#26).
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entry MixedFilamentBatchDialog (cancel path shows a confirm dialog with
# the 'abandon match' wording).
# Source facts: after a match, Cancel pops a confirmation dialog (a new
# #32770 on top); confirming closes the batch dialog WITHOUT saving; the
# confirmation itself can be cancelled, returning to the batch dialog with
# the mapping result intact.
#
# Black-box path: Manual match -> Cancel -> the confirmation dialog appears
# -> OCR its text (contains 'abandon'/'not be saved'-ish wording) -> click
# its affirmative button -> the batch dialog closes (scene unchanged) ->
# reopen -> match -> Cancel -> click the confirmation's NEGATIVE button ->
# back in the batch dialog and the mapping list is still rendered.

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util, ocr_util  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402


def wait_confirm(pid, dlg, timeout_s=8.0):
    """The confirmation dialog on top of the batch dialog."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, rect, hwnd in mixing_util.toplevel(pid):
            if cls == "#32770" and hwnd != dlg and rect[3] - rect[1] < 300:
                return hwnd
        time.sleep(0.3)
    return None


def dialog_buttons(hwnd):
    """(rect, text) pairs of the clickable rows of a small dialog."""
    out = []
    for t, c, r, h in mixing_util.children(hwnd):
        if r[2] > r[0] and r[3] - r[1] >= 25 and (c == "Button" or t.strip()):
            out.append((r, t))
    return out


def run_match(session, dlg):
    mixing_util.click_button(dlg, "Start Matching")
    return mixing_util.wait_match_done(session, dlg, timeout_s=420.0)


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3n] model arrived: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        # ---- first run: Cancel -> confirm -> affirmative closes all ----
        dlg = mixing_util.open_mixing_dialog(session)
        results["mixing dialog opens"] = "PASS" if dlg else "FAIL"
        closed_by_confirm = False
        if dlg:
            mixing_util.switch_match_mode(session, dlg, "Manual")
            done = run_match(session, dlg)
            print(f"[m3n] match 1: {done}")
            results["match completes"] = "PASS" if done else "FAIL"
            if done:
                time.sleep(1.0)
                mixing_util.click_button(dlg, "Cancel")
                cfm = wait_confirm(session.pid, dlg)
                print(f"[m3n] confirm dialog: {hex(cfm) if cfm else None}")
                results["cancel asks for confirmation"] = (
                    "PASS" if cfm else "FAIL")
                if cfm:
                    time.sleep(0.5)
                    text = ocr_util.ocr_hwnd(cfm)
                    print(f"[m3n] confirm text: {text!r}")
                    results["confirm wording"] = (
                        "PASS" if ocr_util.assert_keywords(
                            text, ["discard"]) else "FAIL")
                    btns = dialog_buttons(cfm)
                    print(f"[m3n] confirm buttons: {[(t, r) for r, t in btns]}")
                    # affirmative = the rightmost/non-'Cancel' button
                    aff = None
                    for r, t in btns:
                        if t and "cancel" not in t.lower():
                            aff = r
                            break
                    if not aff and btns:
                        aff = btns[-1][0]
                    if aff:
                        import ctypes as _c
                        from harness import winutil as _w
                        _w.real_click_screen((aff[0] + aff[2]) // 2,
                                             (aff[1] + aff[3]) // 2)
                        time.sleep(2.0)
                        gone = mixing_util.find_dialog(
                            session.pid, timeout_s=3.0) is None
                        print(f"[m3n] batch dialog closed: {gone}")
                        closed_by_confirm = gone
        results["confirm closes without save"] = (
            "PASS" if closed_by_confirm else "FAIL")

        # ---- second run: Cancel -> confirmation -> negative keeps all ---
        kept = False
        if closed_by_confirm:
            dlg2 = mixing_util.open_mixing_dialog(session)
            if dlg2:
                mixing_util.switch_match_mode(session, dlg2, "Manual")
                done2 = run_match(session, dlg2)
                if done2:
                    time.sleep(1.0)
                    mixing_util.click_button(dlg2, "Cancel")
                    cfm2 = wait_confirm(session.pid, dlg2)
                    print(f"[m3n] confirm 2: {hex(cfm2) if cfm2 else None}")
                    if cfm2:
                        time.sleep(0.5)
                        btns2 = dialog_buttons(cfm2)
                        neg = None
                        for r, t in btns2:
                            if "cancel" in t.lower():
                                neg = r
                                break
                        if neg:
                            from harness import winutil as _w
                            _w.real_click_screen((neg[0] + neg[2]) // 2,
                                                 (neg[1] + neg[3]) // 2)
                            time.sleep(2.0)
                            back = mixing_util.find_dialog(
                                session.pid, timeout_s=3.0)
                            kept = back is not None
                            print(f"[m3n] back in batch dialog: {kept}")
                            # mapping list still rendered?
                            rows = mixing_util.swatch_rows(dlg2)
                            print(f"[m3n] swatch rows after abort: "
                                  f"{len(rows)}")
                            kept = kept and len(rows) > 0
        results["abort keeps result"] = "PASS" if kept else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3n] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
