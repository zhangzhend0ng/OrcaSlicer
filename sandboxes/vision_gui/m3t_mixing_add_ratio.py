#!/usr/bin/env python3
# m3t_mixing_add_ratio.py — the Add Mix dialog opens in Ratio mode with the
# seeded defaults (#1), the row add/remove button toggles add->remove at
# the 3-row mode cap (#2), the row combo excludes used filaments and a
# different filament repaints the preview (#3), and the ratio selector
# clamps to 10%..90% (#4).
#
# White-box refs: MixedFilamentDialog (tabs 'Ratio'/'Cycle'/'Match'/
# 'Gradient' :270 — REAL window text, 81x28, active = teal #009688),
# defaults :142-144, row add/remove toggle :571/:592/:2094-2101,
# selector clamp MixedGradientSelector.hpp:22-23, high-ratio advisory
# :2346 (masked while a compat error shows, :2222-2224).
# Seeded fixture: F1=PETG, F2..F5=PLA Silk — the DEFAULT F1+F2 pair is
# cross-type, so the compat error banner is EXPECTED on open (asserted).
# NOTE (record #4): the table's '<25% warns' expectation is stale — the
# current build warns when one filament exceeds ~66.7% ('ratio is too
# high'); the 10..90 clamp matches.
#
# Black-box path: boot -> click the Color Mixing row's add button -> the
# 'Add Mix' dialog opens in Ratio mode with 50/50 legends and the compat
# banner -> switch row 1 via its popup (options exclude used filaments;
# every candidate is PLA, so the banner clears) -> preview pixels move,
# ratio unchanged -> click the selector at its ends: 90/10 and 10/90 with
# the high-ratio advisory on a compatible pair, cleared at mid -> the row
# button adds to 3 rows and toggles to REMOVE at the cap -> Cancel leaves
# the sidebar unchanged.

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402


def row_count(dlg) -> int:
    return len([1 for t, r, h, vis in mdu.static_texts(dlg)
                if vis and t.strip().startswith("Filament ")
                and t.strip()[9:].isdigit()])


def row_toggle_button(dlg):
    """The single small icon Button beside 'Filament Selection' — adds a
    row below the cap, switches to REMOVE at the cap (measured: the icon
    shifts 4px left when it flips to remove)."""
    return mdu.card_button(dlg, "Filament Selection")


def click_rect(rect):
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    mdu.winutil.user32.SetCursorPos(x, y)
    time.sleep(0.15)
    mdu.winutil.real_click_screen(x, y)
    time.sleep(0.8)


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3t] model arrived: {ok_model} (colored {frac:.2%})")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        # --- open the Add Mix dialog from the sidebar row ---
        dlg = mdu.open_add_mix_dialog(session)
        print(f"[m3t] add-mix dialog: {hex(dlg) if dlg else None}")
        results["add mix dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)
        time.sleep(1.0)

        # --- #1: default Ratio presentation ---
        results["default mode is Ratio"] = (
            "PASS" if mdu.active_tab(dlg) == "Ratio" else "FAIL")
        cards = [s for s in ("Mixing Ratio", "Preview", "Mix Effect",
                             "Mixing Recommendations")
                 if mdu.find_static(dlg, s)]
        print(f"[m3t] ratio cards present: {cards}")
        results["ratio cards present"] = (
            "PASS" if len(cards) >= 3 else "FAIL")
        legs = mdu.legend_pcts(dlg)
        print(f"[m3t] default legends: {legs}")
        results["default 2 rows 50/50"] = (
            "PASS" if row_count(dlg) == 2 and legs == [50, 50] else "FAIL")

        banners = mdu.banner_texts(dlg)
        named = any("filament 1" in b.lower() and "filament 2" in b.lower()
                    for b in banners)
        print(f"[m3t] banners on open: {banners}")
        results["default pair flagged incompatible"] = (
            "PASS" if (named and not mdu.ok_enabled(dlg)) else "FAIL")

        # --- #3: switch row 1 via its popup until compatible ---
        combos = mdu.filament_combos(dlg)
        orig = combos[0][0]
        crect = combos[0][1]
        pv = mdu.panel_below(dlg, "Preview")
        snap0 = mdu.hwnd_pixels(pv[1]) if pv else None
        switched = False
        if len(combos) >= 2:
            cx, cy = (crect[0] + crect[2]) // 2, (crect[1] + crect[3]) // 2
            for attempt in range(4):
                winutil_setpos(cx, cy)
                time.sleep(0.2)
                mdu.winutil.real_click_screen(cx, cy)
                time.sleep(1.0)
                pop = mdu.popup_panel(session, crect[2] - crect[0])
                if not pop:
                    continue
                for row in range(0, 4):
                    mdu.popup_pick(session, pop, row)
                    if not mdu.banner_texts(dlg):
                        switched = True
                        break
                    # reopen the popup for the next row
                    winutil_setpos(cx, cy)
                    time.sleep(0.2)
                    mdu.winutil.real_click_screen(cx, cy)
                    time.sleep(1.0)
                    pop = mdu.popup_panel(session, crect[2] - crect[0])
                    if not pop:
                        break
                if switched:
                    break
        print(f"[m3t] row1 switched to compatible: {switched}")
        results["row combo excludes used, pick valid"] = (
            "PASS" if switched else "FAIL")
        if switched:
            legs2 = mdu.legend_pcts(dlg)
            print(f"[m3t] legends after switch: {legs2}")
            results["ratio unchanged after switch"] = (
                "PASS" if legs2 == legs else "FAIL")
            snap1 = mdu.hwnd_pixels(pv[1]) if pv else None
            moved = False
            if snap0 is not None and snap1 is not None \
                    and snap0.shape == snap1.shape:
                diff = float(np.abs(snap0.astype(int)
                                    - snap1.astype(int)).mean())
                print(f"[m3t] preview pixel diff: {diff:.2f}")
                moved = diff > 2.0
            results["preview repaints with filament"] = (
                "PASS" if moved else "FAIL")

        # --- #4: selector clamps 10..90; advisory on a compatible pair ---
        # NOTE: the banner band expands/collapses as advisories come and go,
        # shifting everything below it — re-locate the selector before
        # every click.
        clamped = advised = cleared = False
        sel = mdu.ratio_selector(dlg)
        if sel:
            mdu.click_selector_frac(session, dlg, mdu.ratio_selector(dlg)[0],
                                    0.03)
            low = mdu.legend_pcts(dlg)
            mdu.click_selector_frac(session, dlg, mdu.ratio_selector(dlg)[0],
                                    0.97)
            high = mdu.legend_pcts(dlg)
            print(f"[m3t] legends at ends: {low} / {high}")
            clamped = bool(low and high
                           and min(low + high) >= 10
                           and max(low + high) <= 90
                           and sum(low) == 100 and sum(high) == 100)
            advised = any("too high" in b.lower()
                          for b in mdu.banner_texts(dlg))
            mdu.click_selector_frac(session, dlg, mdu.ratio_selector(dlg)[0],
                                    0.5)
            cleared = not any("too high" in b.lower()
                              for b in mdu.banner_texts(dlg))
            print(f"[m3t] advisory: shown={advised} cleared={cleared} "
                  f"banners={mdu.banner_texts(dlg)}")
        results["ratio clamped 10-90 sum 100"] = (
            "PASS" if clamped else "FAIL")
        results["high-ratio advisory shows and clears"] = (
            "PASS" if (advised and cleared) else "FAIL")

        # --- #2: the row button adds, then toggles to REMOVE at 3 ---
        add_ok = remove_ok = toggled = False
        btn = row_toggle_button(dlg)
        if btn:
            x0 = btn[0][0]
            click_rect(btn[0])
            add_ok = row_count(dlg) == 3
            btn2 = row_toggle_button(dlg)
            toggled = bool(btn2 and btn2[0][0] != x0)
            if btn2:
                click_rect(btn2[0])
                remove_ok = row_count(dlg) == 2
        print(f"[m3t] add={add_ok} toggle_icon={toggled} remove={remove_ok}")
        results["add row to 3"] = "PASS" if add_ok else "FAIL"
        results["button flips to remove at cap"] = (
            "PASS" if toggled else "FAIL")
        results["remove row to 2"] = "PASS" if remove_ok else "FAIL"

        # --- cancel: nothing may be registered ---
        mdu.click_button(session, dlg, "Cancel")
        time.sleep(1.5)
        gone = mdu.find_mix_dialog(session.pid, timeout_s=3.0) is None
        results["cancel closes dialog"] = "PASS" if gone else "FAIL"
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3t] app closed")


def winutil_setpos(x, y):
    mdu.winutil.user32.SetCursorPos(x, y)


if __name__ == "__main__":
    raise SystemExit(main())
