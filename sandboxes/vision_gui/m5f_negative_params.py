#!/usr/bin/env python3
# m5f_negative_params.py — parameter-entry NEGATIVE paths on the Quality
# page, proving the app validates, stays alive, and recovers.
#
# White-box refs (measured + read 09-02):
#   - Tab.cpp:1778-1812 — on committing `layer_height` the bounds come from
#     the machine preset's min/max_layer_height; for the fixture's
#     Snapmaker U1 (0.8 nozzle) the RUNTIME bounds are 0.16 / 0.56
#     (proven from the m5b gcode echo '; min_layer_height = 0.16,...' /
#     '; max_layer_height = 0.56,...' — the 0.08/0.32 in older notes are
#     the fdm_U1 BASE values, stale for this fixture).
#   - in range: no dialog. below floor (>EPSILON) or above ceil:
#     MessageDialog 'Layer height exceeds the limit ...' with
#     Adjust (YES) / Ignore (NO) — Adjust clamps to the bound, Ignore
#     keeps the typed value. == 0 (<EPSILON): OK-only dialog 'Layer height
#     is too small...' then auto-set to the floor.
#   - Print.cpp:1878 — layer_height > nozzle diameter fails Print::validate
#     -> the Slice gate stays closed (m5d measured: gray button + red
#     config-error toast), so an Ignored 1.0 must REJECT slicing.
#   - Field.cpp:~300 — non-numeric text on commit raises the 'Invalid
#     numeric.' error dialog, rewrites the field to the parse result (0),
#     which then cascades into the too-small dialog and lands on the floor
#     (measured 09-02: 'abc' -> 'Invalid numeric.' -> '0' -> 'Layer height
#     is too small.' OK dialog -> field 0.16).
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> Quality page ->
#   A. commit 0.4 (in range)          -> NO dialog (control)
#   B. commit 0.04 (below 0.16)       -> dialog -> Adjust -> field 0.16
#   C. commit 0 (<EPSILON)            -> OK dialog -> field auto 0.16
#   D. commit 1.0 (above 0.56)        -> dialog -> Ignore -> field keeps 1
#      -> Slice click swallowed (no slice result in 60s), app alive
#   E. commit 0.4 again               -> no dialog -> slice + export ->
#      '; layer_height = 0.4' (recoverable)
#   F. commit 'abc'                   -> app survives, field ends numeric
#      (error dialog family handled generically), then app alive.
# Stale-table notes: the '0.32/0.08 limits' on the task table are the
# fdm_U1 base values; this fixture's runtime limits are 0.56/0.16 (see
# white-box refs).

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import gcode_check  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m2_slice_chain import click_slice_start, wait_slicing_done  # noqa: E402
from m3_common import (add_common_args, export_and_check,  # noqa: E402
                       slice_and_wait, verdict)

LOG = "[m5f]"


def pop_dialog(session, known, timeout_s=8.0):
    """(found, body) of a NEW small #32770 within the timeout."""
    dlg = pp.find_conflict_dialog(session, known, timeout_s=timeout_s)
    body = pp.dialog_body(session.pid, dlg) if dlg else ""
    if dlg:
        print(f"{LOG} dialog popped: {body[:160]!r}")
    return dlg, body


def click_dialog_button(session, dlg, label):
    """Real-click the dialog Button whose text contains `label`."""
    hit = mixing_util.child_by_text(dlg, label)
    if not hit:
        return False
    r = hit[2]
    winutil_real_click_center(r)
    time.sleep(1.2)
    return True


def winutil_real_click_center(rect):
    from harness import winutil
    winutil.real_click_screen((rect[0] + rect[2]) // 2,
                              (rect[1] + rect[3]) // 2)


def commit_and_read(session, text, settle_s=6.0):
    """Type `text` into the topmost Quality float Edit (Layer height) and
    commit. Returns (edit_value_after_typing, known_dialog_set). The CALLER
    owns dialog handling: a commit may pop the Adjust/Ignore MessageDialog
    right at Enter."""
    hit = pp.wait_float_edit(session)
    if not hit:
        return None, None
    r, h, old = hit
    known = pp.top_dialog_set(session)
    new = pp.real_edit_set(session, r, h, text)
    return new, known


def read_layer_height(session, tries=6):
    """Value of the topmost Quality float Edit, retried — a commit REBUILDS
    the options page and a mid-rebuild read returns nothing (measured
    09-01)."""
    for _ in range(tries):
        eds = pp.float_edits_in_view(session)
        if eds:
            return eds[0][2]
        time.sleep(1.0)
    return None


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
        results["quality page opens"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- A. in-range control: 0.4 commits WITHOUT any dialog ---
        val_a, known = commit_and_read(session, "0.4")
        dlg, _body = pop_dialog(session, known, timeout_s=3.0)
        ok_a = bool(val_a and val_a.startswith("0.4")) and dlg is None
        print(f"{LOG} A in-range 0.4: val={val_a!r} dialog={dlg}")
        results["in-range 0.4: no dialog"] = "PASS" if ok_a else "FAIL"
        if dlg:
            pp.dismiss_conflict(session, dlg)
        time.sleep(6.0)

        # --- B. below floor (0.04 < 0.16): dialog -> Adjust clamps 0.16 ---
        val_b, known = commit_and_read(session, "0.04")
        dlg_b, body_b = pop_dialog(session, known, timeout_s=8.0)
        ok_dlg = dlg_b is not None
        if dlg_b:
            ok_dlg = ("exceeds the limit" in body_b) or ("Adjust" in body_b)
            clicked = click_dialog_button(session, dlg_b, "Adjust")
            print(f"{LOG} B clicked Adjust: {clicked}")
            time.sleep(1.5)
        val_b2 = read_layer_height(session)
        ok_b = ok_dlg and bool(val_b2 and val_b2.startswith("0.16"))
        print(f"{LOG} B below-floor 0.04: dialog_ok={ok_dlg} "
              f"val_after={val_b2!r}")
        results["0.04 below floor: dialog + Adjust -> 0.16"] = (
            "PASS" if ok_b else "FAIL")
        if dlg_b is None:
            # leave a numeric field for the next step
            commit_and_read(session, "0.16")
        time.sleep(6.0)

        # --- C. zero: OK-only dialog, auto-set to the floor ---
        val_c, known = commit_and_read(session, "0")
        dlg_c, _body = pop_dialog(session, known, timeout_s=8.0)
        if dlg_c:
            pp.dismiss_conflict(session, dlg_c)  # its OK
            time.sleep(1.5)
        val_c2 = read_layer_height(session)
        ok_c = dlg_c is not None and bool(val_c2
                                          and val_c2.startswith("0.16"))
        print(f"{LOG} C zero: dialog={dlg_c} val_after={val_c2!r}")
        results["0: OK dialog + auto min"] = "PASS" if ok_c else "FAIL"
        if dlg_c is None:
            commit_and_read(session, "0.16")
        time.sleep(6.0)

        # --- D. above ceil (1.0 > 0.56): dialog -> Ignore KEEPS 1.0;
        #        1.0 > 0.8 nozzle -> Print::validate fails -> slice gate
        #        closed (click swallowed, no result in 60s) ---
        val_d, known = commit_and_read(session, "1.0")
        dlg_d, _body = pop_dialog(session, known, timeout_s=8.0)
        kept = False
        if dlg_d:
            clicked = click_dialog_button(session, dlg_d, "Ignore")
            print(f"{LOG} D clicked Ignore: {clicked}")
            time.sleep(1.5)
            val_d2 = read_layer_height(session)
            kept = bool(val_d2 and val_d2.startswith("1"))
        else:
            # a rejected commit would leave 0.16 -> detect
            val_d2 = read_layer_height(session)
            kept = bool(val_d2 and val_d2.startswith("1"))
        print(f"{LOG} D above-ceil 1.0: dialog={bool(dlg_d)} "
              f"kept={val_d2!r}")
        results["1.0 above ceil: dialog + Ignore keeps value"] = (
            "PASS" if (dlg_d is not None and kept) else "FAIL")
        # NOTE: NO neutralize_focus here — its ESC reverts the Just-Kept
        # 1.0 when the field still holds focus after the modal dialog
        # (measured 09-02 run 3: slice went VALID and completed), and this
        # step must slice against the STILL-INVALID config. Dead-focus
        # recovery for the next commit happens after the slice attempt.
        time.sleep(6.0)

        started = click_slice_start(session)
        done, _score = (False, 0.0)
        if started:
            done, _score = wait_slicing_done(session, timeout_s=60)
        ok_d2 = (not done) and session.alive()
        print(f"{LOG} D slice attempt: started={started} done={done} "
              f"(expected swallowed)")
        results["1.0 invalid config: slice rejected, app alive"] = (
            "PASS" if ok_d2 else "FAIL")

        # --- E. recovery: back to 0.4, slice + export, echo 0.4 ---
        # DIAG: after the Ignore step the field shows 1.0 marked INVALID
        # (red) + a red error toast + gray Slice (frame-proven 09-02); the
        # first run's real typing went dead here. Dump focus state before
        # retrying, and dismiss the toast first.
        from harness import winutil
        fh = pp.focus_hwnd(session.hwnd)
        print(f"{LOG} E pre: focus_hwnd={fh:#x} alive={session.alive()}")
        for cls, txt, rc, hh in mixing_util.toplevel(session.pid):
            print(f"{LOG} E pre toplevel: {cls} {txt[:40]!r} {rc}")
        pp.neutralize_focus(session)
        time.sleep(1.0)
        val_e, known = commit_and_read(session, "0.4")
        if val_e is None:
            # focus forensics: what sits at the click point?
            hit = pp.wait_float_edit(session, timeout_s=20.0)
            if hit:
                r2, h2, _v = hit
                x2, y2 = (r2[0] + r2[2]) // 2, (r2[1] + r2[3]) // 2
                f = winutil.window_rect(session.hwnd)
                sx, sy = f[0] + x2, f[1] + y2
                at = winutil.window_from_screen_point(sx, sy)
                cls = ctypes.create_unicode_buffer(64)
                winutil.user32.GetClassNameW(at, cls, 64)
                print(f"{LOG} E forensics: click at ({sx},{sy}) -> "
                      f"hwnd={at:#x} class={cls.value!r} "
                      f"focus={pp.focus_hwnd(session.hwnd):#x}")
                # retry: click via neutralize first, then real_edit_set
                pp.neutralize_focus(session)
                val_e = pp.real_edit_set(session, r2, h2, "0.4")
                print(f"{LOG} E retry typed: {val_e!r}")
        dlg_e, _body = pop_dialog(session, known, timeout_s=3.0)
        if dlg_e:
            pp.dismiss_conflict(session, dlg_e)
        pp.neutralize_focus(session)
        time.sleep(6.0)
        ok_set = bool(val_e and val_e.startswith("0.4"))
        sliced = slice_and_wait(session, timeout_s=900) if ok_set else False
        out_path = Path(args.datadir).parent / "m5f_recovered.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = (True, b"")
        lh = None
        if sliced:
            ok_exp, data = export_and_check(session, out_path)
            lh = gcode_check.config_value(data, "layer_height") if ok_exp \
                else None
        print(f"{LOG} E recover: set={val_e!r} slice={sliced} "
              f"export={ok_exp} layer_height={lh!r}")
        results["recover at 0.4: slice + export + echo"] = (
            "PASS" if (ok_set and sliced and ok_exp
                       and lh is not None and lh.startswith("0.4"))
            else "FAIL")

        # --- F. invalid characters: the app must not keep 'abc' ---
        pp.neutralize_focus(session)
        val_f, known = commit_and_read(session, "abc")
        # the Field error path may raise an error dialog family member;
        # dismiss whatever appears (up to two), then read the field
        for _ in range(2):
            dlg_f, _b = pop_dialog(session, known, timeout_s=4.0)
            if not dlg_f:
                break
            pp.dismiss_conflict(session, dlg_f)
            time.sleep(1.0)
        val_f2 = read_layer_height(session)
        numeric = False
        if val_f2:
            try:
                float(val_f2)
                numeric = True
            except ValueError:
                numeric = False
        ok_f = session.alive() and (val_f2 is not None) \
            and ("abc" not in (val_f2 or "").lower()) and numeric
        print(f"{LOG} F invalid 'abc': typed={val_f!r} field_now={val_f2!r} "
              f"numeric={numeric}")
        results["'abc' rejected: field ends numeric, app alive"] = (
            "PASS" if ok_f else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
