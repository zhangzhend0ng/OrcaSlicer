#!/usr/bin/env python3
# m4g_mixing_sublayer.py — 'Subdivide Mix Layer' (config dithering_local_z_mode):
# the sidebar Process panel exposes the checkbox on the Multimaterial page in
# Advanced mode; toggling it at layer height 0.4 (>0.1) pops NO warning, at
# layer height 0.1 (<=0.1) pops the 'Configuration Conflict' advisory while
# still applying the check, and slicing completes with the option enabled
# (表1 #36/#37, 表2 #40/#41).
#
# White-box refs:
#   - PrintConfig.cpp:4343-4348 — 'dithering_local_z_mode' label 'Subdivide
#     Mix Layer', def->mode = comAdvanced (hidden until the Process panel's
#     'Advanced' switch flips the app mode).
#   - Tab.cpp:2625-2629 — the option lives in the 'Color Mixing
#     (Experimental)' group, LAST group of the Multimaterial page
#     (TabPrint::build, Multimaterial page starts with 'Prime tower').
#   - Tab.cpp:1566-1575 — enabling with layer_height <= 0.1+EPSILON pops a
#     RichMessageDialog titled 'Configuration Conflict' ('The current layer
#     height is 0.1 mm or below. Enabling Subdivide Mixing Layers may
#     cause...', wxOK) AFTER the config change is applied.
#   - Tab.cpp:1815-1826 — the mirrored advisory when SETTING a layer height
#     <= 0.1 while the option is enabled (not hit here: we go 0.4 -> 0.1
#     while OFF, then 0.1 -> 0.4 while ON, both advisories silent for the
#     value that lands).
#   - Tab.cpp:1781-1813 — ANY layer-height commit is range-checked against
#     the nozzle limits (fdm_U1.json: min 0.08 / max 0.32): typing 0.1 is in
#     range (silent), typing 0.4 back pops the 'Layer height exceeds the
#     limit...' Adjust/Ignore dialog — 'Ignore' keeps the preset value.
#   - OptionsGroup.cpp:248 activate_line — labels are PAINTED by OG_CustomCtrl
#     (no label windows); a checkbox option renders as an ~18px empty-text
#     wxBitmapToggleButton (Widgets/CheckBox.hpp) at the row's value column.
#
# The generic Process-panel machinery (advanced switch, tab switching,
# viewport scrolling, float/checkbox editing, conflict dialogs) lives in
# harness/process_panel.py — this case keeps only the Subdivide-specific
# row/toggle logic and the business flow.
#
# Black-box path: boot standard fixture -> real-click the 'Advanced'
# SwitchButton on the Process title row -> real-click the 'Multimaterial' tab
# (self-drawn ButtonsListCtrl item, located by its window text) -> wheel the
# options viewport until OCR shows 'Subdivide' -> real-click the 18px checkbox
# Button on that row, state read from the frame capture (teal fraction):
#   #41a at lh 0.4: check ON -> no new #32770 within 3s + checked; uncheck.
#   #37/#41b set lh 0.1 (Quality page topmost Edit, real typing) -> check ON ->
#   'Configuration Conflict' #32770 ('0.1 mm or below') -> OK -> stays checked.
#   #36 lh back to 0.4 (no warning) -> slice completes (done badge) -> uncheck,
#   app alive.
#
# Scope note (表1 #36 numeric half): the subdivided sub-layer height itself is
# solver-dependent; the gcode local-Z parse is documented OUT of black-box
# scope — the automated assertion is the option applying + a completed slice.
# Stale-table notes: none — #37/#40/#41 match the current build dialogs.

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util, process_panel as pp, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded, wait_slicing_done  # noqa: E402
from m3_common import (MIXED_3MF, add_common_args, boot_session,  # noqa: E402
                       click_slice_start, verdict)

user32 = ctypes.WinDLL("user32")
LOG = "[m4g]"
CHECKED_FRACTION = 0.13  # checked reads ~0.21 teal fraction on this build/
                         # layout, an unchecked box ~0.00-0.06 (measured
                         # 08-31 on the maximized window; the windowed-era
                         # 0.25 threshold misclassified every checked state
                         # and made the toggle rounds flail).


def find_subdivide_row(session):
    """Scroll the 'Color Mixing (Experimental)' group into view and locate
    the Subdivide Mix Layer row: OCR confirm + the 18px checkbox candidate
    on the first option row under the group title. If the row is still cut
    off, wheel one more notch and retry."""
    for _ in range(6):
        hit = pp.scroll_group_into_view(session, "Color Mixing")
        if not hit:
            return None, []
        tr = hit[0]
        ty1 = tr[3] - pp.frect(session)[1]
        word = None
        for w, x, y, ww, hh in pp.ocr_band(session):
            if "subdivi" in w.lower() \
                    and abs((y + hh // 2) - (ty1 + 14)) <= 40:
                word = (x, y, x + ww, y + hh)
                break
        y_row = (word[1] + word[3]) // 2 if word else ty1 + 16
        cands = pp.row_checkboxes(session, y_row, y_tol=14)
        if word and cands:
            return word, cands
        vp = pp.options_viewport(session)
        if vp:
            pp.wheel_viewport(session, vp, 1, delta=-120)
        time.sleep(0.4)
    return None, []


def toggle_subdivide(session, want_checked, tries=4):
    """Click the Subdivide checkbox until the frame-capture state reads
    `want_checked`. Rotates real -> message-level click on retries. Returns
    (final_state, clicked_btn_rect) or (None, None)."""
    for attempt in range(tries):
        word, cands = find_subdivide_row(session)
        if not word or not cands:
            return None, None
        for rect, h in cands[:3]:
            before = pp.checked_state(session, rect)
            if attempt < 2:
                pp.real_click(rect)
            else:
                cx, cy = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
                winutil.user32.SetCursorPos(cx, cy)
                time.sleep(0.15)
                winutil.msg_click_screen(cx, cy, session.hwnd)
                time.sleep(1.0)
            time.sleep(0.8)
            after = pp.checked_state(session, rect)
            print(f"{LOG} subdivide click(att{attempt}): before={before:.2f} "
                  f"after={after:.2f}")
            now_on = after > CHECKED_FRACTION
            if now_on == want_checked and abs(after - before) > 0.05:
                return now_on, rect
            if now_on == want_checked:
                return now_on, rect
        time.sleep(0.8)
    word, cands = find_subdivide_row(session)
    if word and cands:
        st = pp.checked_state(session, cands[0][0])
        if (st > CHECKED_FRACTION) == want_checked:
            return st > CHECKED_FRACTION, cands[0][0]
    return None, None


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model loaded: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"
        if not ok_model:
            return verdict(results)
        time.sleep(2.0)

        # --- flip the Process panel 'Advanced' switch (comSimple hides the
        #     comAdvanced option, PrintConfig.cpp:4347) ---
        sw = pp.advanced_switch(session)
        print(f"{LOG} advanced switch: {sw}")
        results["advanced switch located"] = "PASS" if sw else "FAIL"
        if not sw:
            return verdict(results)
        st0 = pp.advanced_on(session)
        pp.real_click(sw[0])
        time.sleep(2.0)
        st1 = pp.advanced_on(session)
        print(f"{LOG} advanced knob chroma L/R: before={st0} after={st1}")
        flipped = (st0 is not None and st1 is not None
                   and abs(st0[0] - st1[0]) + abs(st0[1] - st1[1]) > 0.05)
        results["advanced mode toggles"] = "PASS" if flipped else "FAIL"

        # --- Multimaterial tab (ButtonsListCtrl item with window text) ---
        tab_ok = pp.click_tab(session, "Multimaterial", "tower")
        print(f"{LOG} multimaterial tab switched: {tab_ok}")
        results["multimaterial tab switches"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            return verdict(results)

        # --- scroll until 'Subdivide' paints, locate its checkbox ---
        word, cands = find_subdivide_row(session)
        print(f"{LOG} subdivide word: {word} candidates: "
              f"{[pp.to_local(session, r) for r, _h in cands]}")
        located = bool(word and cands)
        results["Subdivide Mix Layer reachable in Advanced mode"] = (
            "PASS" if located else "FAIL")
        if not located:
            return verdict(results)

        # --- #41a: toggle ON at lh 0.4 -> NO warning ---
        known = pp.top_dialog_set(session)
        st, rect = toggle_subdivide(session, want_checked=True)
        print(f"{LOG} #41a toggle on: state={st} rect={rect}")
        late = pp.find_conflict_dialog(session, known, timeout_s=3.0)
        popped_txt = pp.dialog_body(session.pid, late) if late else ""
        if late:
            print(f"{LOG} UNEXPECTED dialog: {popped_txt[:120]!r}")
            pp.dismiss_conflict(session, late)
        results["#41a at 0.4mm: no warning + checks on"] = (
            "PASS" if (st is True and late is None) else "FAIL")

        # --- uncheck (still no warning) ---
        known = pp.top_dialog_set(session)
        st_off, _r = toggle_subdivide(session, want_checked=False)
        late2 = pp.find_conflict_dialog(session, known, timeout_s=2.0)
        if late2:
            pp.dismiss_conflict(session, late2)
        results["#41a uncheck silent at 0.4mm"] = (
            "PASS" if (st_off is False and late2 is None) else "FAIL")

        # --- Quality tab: set layer height to 0.1 (real typing) ---
        qtab = pp.click_tab(session, "Quality", "height")
        print(f"{LOG} quality tab switched: {qtab}")
        hit = pp.wait_float_edit(session) if qtab else None
        lh_ok = False
        lh_rect = None
        if hit:
            lh_rect, lh_h, lh_val = hit
            new_val = pp.real_edit_set(session, lh_rect, lh_h, "0.1")
            print(f"{LOG} layer height edit: {lh_val!r} -> {new_val!r}")
            pp.neutralize_focus(session)  # wheel/clicks die while the Edit holds focus
            lh_ok = bool(new_val and new_val.startswith("0.1"))
        results["layer height sets to 0.1"] = "PASS" if lh_ok else "FAIL"
        if not lh_ok:
            results["#37/#41b conflict dialog at 0.1mm"] = "FAIL"
            results["#36 slice with Subdivide enabled"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- Multimaterial again: toggle ON at 0.1 -> 'Configuration
        #     Conflict' advisory, then the checkbox STAYS checked ---
        pp.click_tab(session, "Multimaterial", "tower")
        word, cands = find_subdivide_row(session)
        if not (word and cands):
            results["#37/#41b conflict dialog at 0.1mm"] = "FAIL"
            results["#36 slice with Subdivide enabled"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)
        known = pp.top_dialog_set(session)
        st_on, rect = toggle_subdivide(session, want_checked=True)
        warn = pp.find_conflict_dialog(session, known, timeout_s=6.0)
        wtitle = wbody = ""
        if warn:
            for cls, txt, r, h in mixing_util.toplevel(session.pid):
                if h == warn:
                    wtitle = txt
            wbody = pp.dialog_body(session.pid, warn)
            print(f"{LOG} conflict dialog: title={wtitle!r} "
                  f"body={wbody[:140]!r}")
        dismissed = pp.dismiss_conflict(session, warn) if warn else False
        time.sleep(1.0)
        st_after = pp.checked_state(session, rect) if rect else 0.0
        print(f"{LOG} #41b state after dismiss: {st_after:.2f} "
              f"st_on={st_on}")
        results["#37/#41b conflict dialog at 0.1mm"] = (
            "PASS" if (warn is not None and dismissed
                       and "0.1 mm or below" in wbody) else "FAIL")

        # --- back to 0.4 for slicing. NOTE: the U1 0.8 nozzle caps
        #     max_layer_height at 0.32 (fdm_U1.json), so committing 0.4 pops
        #     the 'Layer height exceeds the limit...' Adjust/Ignore dialog
        #     (Tab.cpp:1794-1812) — 'Ignore' keeps the preset value. ---
        pp.click_tab(session, "Quality", "height")
        hit2 = pp.wait_float_edit(session)
        lh_ok2 = False
        if hit2:
            r2, h2, v2 = hit2
            known = pp.top_dialog_set(session)
            new2 = pp.real_edit_set(session, r2, h2, "0.4")
            print(f"{LOG} layer height back: {v2!r} -> {new2!r}")
            pp.neutralize_focus(session)
            lh_ok2 = bool(new2 and new2.startswith("0.4"))
            rng = pp.find_conflict_dialog(session, known, timeout_s=6.0)
            if rng:
                hit_ign = mixing_util.child_by_text(rng, "Ignore")
                btn = "Ignore" if hit_ign else "No"
                print(f"{LOG} range dialog popped -> click {btn!r}")
                mixing_util.click_button(rng, btn)
                time.sleep(1.2)
        results["layer height back to 0.4"] = "PASS" if lh_ok2 else "FAIL"

        # --- #36: slice with Subdivide enabled ---
        if not lh_ok2:
            results["#36 slice with Subdivide enabled"] = "FAIL"
            results["state restored + app alive"] = "FAIL"
            return verdict(results)
        started = click_slice_start(session)
        done, done_score = (False, 0.0)
        if started:
            done, done_score = wait_slicing_done(session, timeout_s=1500)
        print(f"{LOG} #36 slice started={started} done={done} "
              f"(score {done_score:.3f})")
        results["#36 slice with Subdivide enabled"] = (
            "PASS" if (started and done) else "FAIL")

        # --- restore: uncheck, confirm ---
        pp.click_tab(session, "Multimaterial", "tower")
        st_end, _r = toggle_subdivide(session, want_checked=False)
        print(f"{LOG} final uncheck: {st_end}")
        results["subdivide off after slice + app alive"] = (
            "PASS" if (st_end is False and session.alive()) else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
