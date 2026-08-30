#!/usr/bin/env python3
# m3w_mixing_cycle_flow.py — the Cycle round trip: register a pattern
# (#18), edit it in place (#19), cancel an edit (#20), and switch the
# scheme's mode inside Edit Mix (#44).
#
# White-box refs: MixedFilamentDialog OK -> collect_result :3246-3414;
# sidebar labels Plater.cpp:6673-6711 (cycle summaries vs 'F%u %d%%'
# ratio forms) ; single-click opens Edit Mix :6769-6777; on_mode_changed
# :2920-3034 saves per-mode state (:146-157) so switching tabs and back
# preserves the pattern.
# Uses the COMPATIBLE pattern '23' (F3+F2, both PLA) — pattern '12' would
# trip the fixture's cross-type compat banner and block OK.
#
# Black-box path: boot -> open Add Mix -> Cycle tab -> '23' + OK: a new
# sidebar entry appears (cycle form, no '%' ratio text) -> click it:
# 'Edit Mix' with Cycle active and '23' preserved -> '232' + OK: the
# label changes in place -> edit again, '2323', Cancel: label unchanged
# -> edit, switch to Match (Match becomes active), back to Cycle ('232'
# intact), then to Ratio + OK: the label becomes a ratio form.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402
from m3u_mixing_ratio_flow import (sidebar_entries,  # noqa: E402
                                   make_compatible)


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"
        base = sidebar_entries(session)
        print(f"[m3w] base entries: {[e[0] for e in base]}")

        # --- #18: register a cycle scheme ---
        dlg = mdu.open_add_mix_dialog(session)
        results["add mix dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)
        time.sleep(1.0)
        mdu.click_tab(session, dlg, "Cycle")
        got = mdu.real_edit_text(session, dlg, "23")
        ok_enabled = mdu.ok_enabled(dlg)
        print(f"[m3w] pattern '23' stored={got!r} ok={ok_enabled}")
        results["compatible pattern accepted"] = (
            "PASS" if (got == "23" and ok_enabled) else "FAIL")
        mdu.click_button(session, dlg, "OK")
        time.sleep(2.0)
        after = sidebar_entries(session)
        print(f"[m3w] entries after OK: {[e[0] for e in after]}")
        registered = len(after) == len(base) + 1
        new_label = after[-1][0] if registered else None
        results["cycle scheme registered"] = (
            "PASS" if registered else "FAIL")
        # equal-count cycle '23' summarizes as the 50/50 ratio form
        results["cycle summary 50/50"] = (
            "PASS" if new_label == "F2 50%+F3 50%" else "FAIL")

        # --- #19: edit in place ---
        edited = False
        label_after_edit = None
        if registered:
            mixing_util_winutil_click(session, after[-1][1])
            edlg = mdu.find_mix_dialog(session.pid, timeout_s=6.0)
            title = mdu.dialog_title(session.pid, edlg) if edlg else None
            mode = mdu.active_tab(edlg) if edlg else None
            eds = mdu.edit_boxes(edlg) if edlg else []
            pat = mdu.edit_value(eds[0][1]) if eds else None
            print(f"[m3w] edit: title={title!r} mode={mode} pattern={pat!r}")
            results["edit opens in cycle mode"] = (
                "PASS" if (edlg and "Edit Mix" in title and mode == "Cycle")
                else "FAIL")
            results["edit preserves pattern"] = (
                "PASS" if pat == "23" else "FAIL")
            if edlg:
                got2 = mdu.real_edit_text(session, edlg, "232")
                edited = mdu.ok_enabled(edlg)
                print(f"[m3w] edited pattern: {got2!r} ok={edited}")
                mdu.click_button(session, edlg, "OK")
                time.sleep(2.0)
        after2 = sidebar_entries(session)
        label_after_edit = after2[-1][0] if after2 else None
        updated = (edited and registered
                   and label_after_edit != new_label)
        print(f"[m3w] label after edit: {label_after_edit!r}")
        results["edit confirm updates label"] = (
            "PASS" if updated else "FAIL")

        # --- #20: cancel an edit ---
        kept = False
        if updated:
            mixing_util_winutil_click(session, after2[-1][1])
            edlg2 = mdu.find_mix_dialog(session.pid, timeout_s=6.0)
            if edlg2:
                mdu.real_edit_text(session, edlg2, "2323")
                mdu.click_button(session, edlg2, "Cancel")
                time.sleep(2.0)
                after3 = sidebar_entries(session)
                kept = (len(after3) == len(after2)
                        and after3[-1][0] == label_after_edit)
                print(f"[m3w] entries after cancel: {[e[0] for e in after3]}")
        results["cancel keeps label"] = "PASS" if kept else "FAIL"

        # --- #44: switch the scheme's mode to Ratio ---
        switched = False
        if kept:
            mixing_util_winutil_click(session, after2[-1][1])
            edlg3 = mdu.find_mix_dialog(session.pid, timeout_s=6.0)
            if edlg3:
                to_match = mdu.click_tab(session, edlg3, "Match")
                back = mdu.click_tab(session, edlg3, "Cycle")
                eds = mdu.edit_boxes(edlg3)
                pat = mdu.edit_value(eds[0][1]) if eds else None
                print(f"[m3w] match switch={to_match} back={back} "
                      f"pattern preserved={pat!r}")
                results["mode switch preserves pattern"] = (
                    "PASS" if (to_match and back and pat == "232") else "FAIL")
                to_ratio = mdu.click_tab(session, edlg3, "Ratio")
                time.sleep(0.5)
                # NOTE: entering Ratio resets the rows to the fixture
                # defaults F1(PETG)+F2(PLA) — the compat gate then blocks
                # OK (by design, record #60). Re-pick a compatible pair.
                compat = make_compatible(session, edlg3)
                print(f"[m3w] ratio={to_ratio} compat={compat} "
                      f"ok={mdu.ok_enabled(edlg3)} "
                      f"banners={mdu.banner_texts(edlg3)}")
                switched = (to_ratio and compat
                            and mdu.ok_enabled(edlg3))
                if switched:
                    # clicking OK applies + closes; retry once on a race
                    gone = False
                    for _ in range(3):
                        mdu.click_button(session, edlg3, "OK")
                        gone = mdu.find_mix_dialog(
                            session.pid, timeout_s=4.0) is None
                        if gone:
                            break
                        time.sleep(1.0)
                    switched = gone
        after4 = sidebar_entries(session)
        final = after4[-1][0] if after4 else None
        print(f"[m3w] final entries: {[e[0] for e in after4]}")
        results["mode switch re-types scheme"] = (
            "PASS" if (switched and final and final != "F2 67%+F3 33%"
                       and "%" in final) else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3w] app closed")


def mixing_util_winutil_click(session, rect):
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    mdu.winutil.user32.SetCursorPos(x, y)
    time.sleep(0.15)
    mdu.winutil.real_click_screen(x, y)
    time.sleep(1.2)


if __name__ == "__main__":
    raise SystemExit(main())
