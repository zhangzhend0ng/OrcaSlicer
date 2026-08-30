#!/usr/bin/env python3
# m4f_mixing_cap64.py — the color/filament ADD CAP (表1 #41): a 64-filament
# project silently disables BOTH add buttons (the Color Mixing panel's '+'
# and the Filaments row's '+'); deleting one physical filament (63 total)
# re-enables both; below the cap the Add Mix dialog opens with a clean,
# unblocked same-type PLA pair.
#
# White-box refs:
#   - libslic3r.h:68 — MAXIMUM_FILAMENT_NUMBER = 64 (mixed-color cap);
#     MAXIMUM_EXTRUDER_NUMBER = 64 as well (add-filament gate).
#   - Plater.cpp:4148-4156 / :7016-7023 — at the cap the add buttons get
#     Enable(false) SILENTLY (no dialog, no banner); the buttons are the
#     icon Buttons at the right end of the 'Color Mixing' title row
#     (m_btn_add_color_mix, Plater.cpp:6470) and of the 'Filaments' title
#     row (add_filament, Plater.cpp:3104-3110).
#   - Plater.cpp:3083-3110 — the Filaments-row trash ('Remove last
#     filament', the MIDDLE button) deletes the LAST filament; with no
#     dependent mixed scheme the delete pops NO confirm.
#   - MixedFilamentDialog defaults (:142-144) — Add Mix opens in Ratio mode
#     with 2 rows; with an all-PLA table the default F1+F2 pair is
#     same-type -> no compat banner, OK enabled.
#
# Stale-table note (FEISHU_MAPPING.md):
#   - 表1 #41 says the mix cap is 32; the current build caps at 64
#     (libslic3r.h:68). The record's INTENT — at the cap the add button is
#     greyed out, deleting one recovers it — is asserted against 64.
#
# Observability note: with 64 slots the sidebar rows band (~120px) shows
# only ~4 slots at a time (the list scrolls), so the physical count cannot
# be read as '64' from the window tree. The cap state is instead observed
# EXACTLY through the designed signal: WS_DISABLED on the add buttons
# (GWL_STYLE & 0x08000000). Both gates are at 64, so 'both adds enabled
# again' after one trash click is sound evidence the count dropped to 63.
#
# Black-box path: craft a 64-filament all-PLA fixture (strip_mixed) ->
# boot (dismiss 'Customized Preset' if it pops, re-force GL) -> 'Color
# Mixing' row visible with add DISABLED + 'Filaments' add DISABLED (trash
# ENABLED) -> trash once -> BOTH adds re-enabled -> Add Mix opens (its
# ctor needs ~30s at 63 filaments: recommendations over all colour pairs),
# default PLA pair unblocked, OK enabled -> Cancel -> app alive.

import colorsys
import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import fixture_util  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import (add_common_args, boot_session, ensure_gl_ready,  # noqa: E402
                       verdict)
from m3u_mixing_ratio_flow import compat_blocked  # noqa: E402

LOG = "[m4f]"
GWL_STYLE = -16
WS_DISABLED = 0x08000000
N_FIL = 64
IDS = ["Generic PLA @U1 0.8 nozzle"] * N_FIL
TYPES = ["PLA"] * N_FIL
COLOURS = ["#%02X%02X%02X" % tuple(
    round(c * 255) for c in colorsys.hsv_to_rgb(i / N_FIL, 0.75, 0.9))
    for i in range(N_FIL)]


def enabled(hwnd):
    return not bool(ctypes.WinDLL("user32").GetWindowLongW(hwnd, GWL_STYLE)
                    & WS_DISABLED)


def real_click(rect):
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.2)
    winutil.real_click_screen(x, y)
    time.sleep(0.8)


def add_buttons(session):
    """((rect, hwnd) mixing-add or None, (rect, hwnd) filament-add or None,
    (rect, hwnd) filament-trash or None) — re-enumerated fresh. Uses the
    title PANEL's direct Button children: at 64 slots the rows list scrolls
    and the band-scan (filament_row_buttons) picks up slot chips plus an
    unrelated overlapping button, so btns[-2] is NOT the trash there."""
    mbtns = mdu.title_panel_buttons(session, "Color Mixing")
    fbtns = mdu.title_panel_buttons(session, "Filaments")
    mix = mbtns[-1] if mbtns else None
    fil = fbtns[-1] if fbtns else None
    trash = fbtns[-2] if len(fbtns) >= 2 else None
    return mix, fil, trash


def visible_chips(session):
    """Numbered slot chips currently VISIBLE in the rows band (info only —
    the band scrolls, so this is NOT the physical count at 64 slots)."""
    band = mdu.sidebar_rows_band(session)
    if not band:
        return []
    top, bottom, x0 = band
    nums = set()
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c == "Button" and t.strip().isdigit() \
                and mdu.user32.IsWindowVisible(h) \
                and top <= r[1] <= bottom and x0 <= r[0] <= x0 + 400:
            nums.add(int(t.strip()))
    return sorted(nums)


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap)
    args = ap.parse_args()
    if not args.model:
        args.model = fixture_util.craft_filaments_fixture(
            fixture_util.ART_FIXTURES / "cap64_pla.3mf",
            COLOURS, TYPES, IDS, strip_mixed=True)
        print(f"{LOG} fixture: {args.model}")

    results = {}
    session = boot_session(args, model=args.model)
    try:
        # a crafted filament table pops the 'Customized Preset' dialog
        dismissed = fixture_util.dismiss_custom_preset_dialog(
            session, timeout_s=30)
        if dismissed:
            ensure_gl_ready(session)
        print(f"{LOG} customized-preset dialog dismissed: {dismissed}")
        ok_model, frac = wait_model_loaded(session, timeout_s=420)
        print(f"{LOG} model loaded: {ok_model}")
        results["64-filament fixture loads"] = "PASS" if ok_model else "FAIL"
        if not ok_model:
            results["cap: mixing add disabled"] = "FAIL"
            results["cap: filament add disabled"] = "FAIL"
            results["delete recovers both add buttons"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)
        time.sleep(2.5)  # let the sidebar finish building 64 slots

        # --- cap state: both add buttons DISABLED (silently) ---
        bar = mdu.color_mix_bar(session)
        mix, fil, trash = add_buttons(session)
        mix_dis = bool(mix) and not enabled(mix[1])
        fil_dis = bool(fil) and not enabled(fil[1])
        trash_en = bool(trash) and enabled(trash[1])
        print(f"{LOG} cap state: mixing_row={bar is not None} "
              f"mix_add_disabled={mix_dis} fil_add_disabled={fil_dis} "
              f"trash_enabled={trash_en} visible_chips={visible_chips(session)} "
              f"visible_combos={len(mdu.filament_material_combos(session))}")
        results["cap: mixing add disabled"] = (
            "PASS" if (bar and mix_dis) else "FAIL")
        results["cap: filament add disabled"] = (
            "PASS" if fil_dis else "FAIL")

        # --- delete one physical filament -> both adds recover ---
        recovered = False
        if trash_en:
            real_click(trash[0])
            deadline = time.monotonic() + 25.0
            while time.monotonic() < deadline:
                mix2, fil2, _tr = add_buttons(session)
                if mix2 and fil2 and enabled(mix2[1]) and enabled(fil2[1]):
                    recovered = True
                    break
                time.sleep(0.6)
            warn = mixing_util.wait_warning_dialog(session.pid, 0,
                                                   timeout_s=1.5)
            if warn:  # no scheme references anything on this fixture
                mixing_util.dismiss_dialog(session.pid, warn)
            print(f"{LOG} after trash: recovered={recovered} "
                  f"visible_chips={visible_chips(session)}")
        results["delete recovers both add buttons"] = (
            "PASS" if recovered else "FAIL")

        # --- below the cap: Add Mix opens with an unblocked PLA pair ---
        opened = unblocked = False
        if recovered:
            time.sleep(3.0)  # let the 63-slot sidebar rebuild settle
            dlg = None
            mbtns = mdu.title_panel_buttons(session, "Color Mixing")
            if mbtns and enabled(mbtns[-1][1]):
                real_click(mbtns[-1][0])
                # the dialog ctor computes its recommendation grid over all
                # colour pairs — ~30s at 63 filaments (measured 08-30);
                # ONE click only: retries would queue on the modal loop
                dlg = mdu.find_mix_dialog(session.pid, timeout_s=120.0)
            if dlg:
                time.sleep(1.0)
                opened = True
                unblocked = (not compat_blocked(dlg)
                             and mdu.ok_enabled(dlg))
                print(f"{LOG} add mix below cap: opened={opened} "
                      f"blocked={compat_blocked(dlg)} "
                      f"ok={mdu.ok_enabled(dlg)} "
                      f"legends={mdu.legend_pcts(dlg)}")
                mdu.click_button(session, dlg, "Cancel")
                time.sleep(2.0)
                if mdu.find_mix_dialog(session.pid, timeout_s=3.0) \
                        is not None:
                    mdu.click_button(session, dlg, "Cancel")
                    time.sleep(2.0)
        results["below cap: add-mix PLA pair unblocked"] = (
            "PASS" if (opened and unblocked) else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
