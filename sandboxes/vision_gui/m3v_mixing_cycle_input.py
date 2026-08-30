#!/usr/bin/env python3
# m3v_mixing_cycle_input.py — the Cycle-mode pattern input (#10/#11/#12):
# default '12', quick-badge append, legal formats, and every validation
# branch (#13 single-filament advisory + empty-normalize, #14 unknown
# filament, #15 invalid characters + leading/trailing commas, 512 cap).
#
# White-box refs: MixedFilamentDialog — pattern ctrl default '12' :1030,
# SetMaxLength(512) :1041, validate on ENTER/KILL_FOCUS/OK :1043-1047/
# :1282, validate_cycle_pattern :3155-3227 (exact strings :3179/:3184/
# :3198), advisory :2226 (1 filament), quick badges append :999-1008.
# NOTE (records #11/#15): the table's '/' separator + live-filter
# expectations are stale — the current grammar uses [nn] brackets and
# validates on Enter/kill-focus, not per keystroke.
# NOTE (#16 >4-distinct advisory): the seeded fixture only has 4
# compatible filaments (F1 is the lone PETG), so a 5-distinct pattern
# trips the compat banner first — asserted in m4j on the all-PLA fixture.
#
# Driving facts (measured 08-30): GetWindowText is STALE for other-process
# Edit controls — WM_GETTEXT reads live; validation fires on REAL Enter
# only (SendInput), not on message-injected key events; the banner band
# expands/collapses and shifts the layout, so the Edit is re-located
# before every interaction.
#
# Black-box path: boot -> open Add Mix -> Cycle tab -> default '12' ->
# click quick badge 3: '123' -> '23,32': clean + OK enabled -> '623':
# Filament 6 not recognized + OK disabled -> '2a3': invalid characters ->
# ',123': leading comma -> '2': same-color advisory, not blocked ->
# empty + Enter: falls back to '12' -> 520 '2's: capped at 512 -> Cancel.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402


def quick_badges(dlg):
    """The 20x20 filament quick-badges under the Cycle card's 'Filaments'
    title (EXACT text match — the compat banner's prose also contains the
    word 'filaments')."""
    hits = [(t, r, h) for t, r, h, v in mdu.static_texts(dlg)
            if t.strip() == "Filaments" and v]
    if not hits:
        return []
    ty1 = hits[0][1][3]
    out = [(r, h) for t, c, r, h in mixing_util.children(dlg)
           if c == "wxWindowNR" and 16 <= r[2] - r[0] <= 26
           and 16 <= r[3] - r[1] <= 26 and ty1 - 4 <= r[1] <= ty1 + 80
           and mdu.user32.IsWindowVisible(h)]
    out.sort(key=lambda rh: rh[0][0])
    return out


def click_rect(rect):
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    mdu.winutil.user32.SetCursorPos(x, y)
    time.sleep(0.15)
    mdu.winutil.real_click_screen(x, y)
    time.sleep(0.7)


def type_pattern(session, dlg, text, enter=True):
    return mdu.real_edit_text(session, dlg, text, clear=True, enter=enter)


def has_banner(dlg, substr):
    return any(substr.lower() in b.lower() for b in mdu.banner_texts(dlg))


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        dlg = mdu.open_add_mix_dialog(session)
        results["add mix dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)
        time.sleep(1.0)

        tab_ok = mdu.click_tab(session, dlg, "Cycle")
        print(f"[m3v] active tab: {mdu.active_tab(dlg)}")
        results["cycle tab switches"] = (
            "PASS" if (tab_ok and mdu.active_tab(dlg) == "Cycle")
            else "FAIL")
        time.sleep(0.5)

        edits = mdu.edit_boxes(dlg)
        results["pattern input found"] = (
            "PASS" if len(edits) == 1 else "FAIL")
        if not edits:
            return verdict(results)
        edit_hwnd = edits[0][1]

        # --- #10: default '12' ---
        val = mdu.edit_value(edit_hwnd)
        print(f"[m3v] default pattern: {val!r}")
        results["default pattern is 12"] = (
            "PASS" if val == "12" else "FAIL")

        # --- #12: quick badge appends its id ---
        badges = quick_badges(dlg)
        print(f"[m3v] quick badges: {len(badges)}")
        results["quick badges rendered"] = (
            "PASS" if len(badges) >= 3 else "FAIL")
        appended = False
        if len(badges) >= 3:
            click_rect(badges[2][0])  # third filament badge -> '3'
            val2 = mdu.edit_value(edits[0][1])
            print(f"[m3v] pattern after badge click: {val2!r}")
            appended = val2 == "123"
        results["badge click appends id"] = (
            "PASS" if appended else "FAIL")

        # --- #11: legal compatible patterns validate clean ---
        legal = True
        for text in ("23", "23,32"):
            got = type_pattern(session, dlg, text)
            bad = has_banner(dlg, "not allowed") or \
                has_banner(dlg, "Invalid characters") or \
                has_banner(dlg, "not recognized")
            print(f"[m3v] {text!r}: stored={got!r} error={bad} "
                  f"ok={mdu.ok_enabled(dlg)}")
            legal = legal and not bad and mdu.ok_enabled(dlg)
        results["legal patterns validate"] = (
            "PASS" if legal else "FAIL")

        # --- #14: unrecognized filament id ---
        got = type_pattern(session, dlg, "623")
        unk = has_banner(dlg, "Filament 6 not recognized")
        print(f"[m3v] 623: banner={unk} ok={mdu.ok_enabled(dlg)}")
        results["unknown id blocked"] = (
            "PASS" if unk and not mdu.ok_enabled(dlg) else "FAIL")

        # --- #15: invalid characters / leading comma ---
        type_pattern(session, dlg, "2a3")
        invalid = has_banner(dlg, "Invalid characters")
        results["invalid chars blocked"] = (
            "PASS" if invalid and not mdu.ok_enabled(dlg) else "FAIL")
        type_pattern(session, dlg, ",123")
        lead = has_banner(dlg, "Leading or trailing commas")
        print(f"[m3v] invalid={invalid} lead={lead}")
        results["leading comma blocked"] = (
            "PASS" if lead and not mdu.ok_enabled(dlg) else "FAIL")

        # --- #13b: single filament -> advisory, not blocked ---
        type_pattern(session, dlg, "2")
        single = has_banner(dlg, "same filament colors")
        print(f"[m3v] single advisory={single} ok={mdu.ok_enabled(dlg)}")
        results["single filament warns, not blocked"] = (
            "PASS" if single and mdu.ok_enabled(dlg) else "FAIL")

        # --- #13a: empty normalizes back to '12' ---
        got = type_pattern(session, dlg, "")
        print(f"[m3v] empty normalizes to: {got!r}")
        results["empty falls back to 12"] = (
            "PASS" if got == "12" else "FAIL")

        # --- 512-char cap: 520 typed chars truncate ---
        got = mdu.real_edit_text(session, dlg, "2" * 520, enter=False)
        time.sleep(0.5)
        eds = mdu.edit_boxes(dlg)
        if eds:
            got = mdu.edit_value(eds[0][1])
        print(f"[m3v] typed 520, stored {len(got)}")
        results["input capped at 512"] = (
            "PASS" if len(got) == 512 else "FAIL")

        mdu.click_button(session, dlg, "Cancel")
        time.sleep(1.5)
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3v] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
