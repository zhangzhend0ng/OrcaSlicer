#!/usr/bin/env python3
# m3y_mixing_gradient.py — the Gradient mode: forced 2 rows + Mix Effect
# + swap control (#31), the row combo repaints the gradient (#32), the
# default direction registers as F3->F2 and the swap flips it to F2->F3
# (#33), a re-open stays in Gradient (#34), and a recommendation fill +
# Cancel registers nothing (#35).
#
# White-box refs: MixedFilamentDialog — gradient forces exactly 2 rows
# :1687-1688; swap button 'reverse_arrow' tooltip 'Swap filaments'
# :553-566 resets m_gradient_direction; direction 0 = A->B with
# 80/20 start-end (k_default_gradient_dominant, MixedFilament.hpp:75-81);
# sidebar gradient labels 'F%u->F%u' Plater.cpp:6703.
# The seeded F1(PETG)+F2(PLA) pair is cross-type -> re-pick row 1 to a
# PLA filament first (make_compatible), so rows are F3+F2.
#
# Black-box path: boot -> Gradient tab: 2 rows + Mix Effect + small icon
# button -> switch row 2 -> preview repaints -> OK: entry 'F3->F2' ->
# re-open: Gradient still active -> click the swap button: preview flips
# -> OK: label 'F2->F3' -> open Add Mix, Gradient, click a recommendation
# badge, Cancel: no new entry.

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
from m3u_mixing_ratio_flow import (make_compatible, sidebar_entries,  # noqa: E402
                                   compat_blocked)


def preview_pixels(dlg):
    hit = mdu.panel_below(dlg, "Mix Effect")
    return mdu.hwnd_pixels(hit[1]) if hit else None


def small_buttons(dlg):
    out = []
    for t, c, r, h in mixing_util.children(dlg):
        if c == "Button" and not t.strip() and mdu.user32.IsWindowVisible(h):
            w, hh = r[2] - r[0], r[3] - r[1]
            if 10 <= w <= 34 and 14 <= hh <= 34:
                out.append((r, h))
    out.sort(key=lambda rh: (rh[0][1], rh[0][0]))
    return out


def click_rect(rect):
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    mdu.winutil.user32.SetCursorPos(x, y)
    time.sleep(0.15)
    mdu.winutil.real_click_screen(x, y)
    time.sleep(0.8)


def ok_and_close(session, dlg):
    for _ in range(3):
        mdu.click_button(session, dlg, "OK")
        if mdu.find_mix_dialog(session.pid, timeout_s=4.0) is None:
            return True
        time.sleep(1.0)
    return False


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

        dlg = mdu.open_add_mix_dialog(session)
        results["add mix dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)
        time.sleep(1.0)

        # --- #31: gradient presentation ---
        mdu.click_tab(session, dlg, "Gradient")
        results["gradient tab switches"] = (
            "PASS" if mdu.active_tab(dlg) == "Gradient" else "FAIL")
        time.sleep(1.0)
        combos = mdu.filament_combos(dlg)
        has_effect = bool(mdu.find_static(dlg, "Mix Effect"))
        btns = small_buttons(dlg)
        print(f"[m3y] rows={len(combos)} mixEffect={has_effect} "
              f"iconButtons={len(btns)}")
        results["gradient forces 2 rows"] = (
            "PASS" if len(combos) == 2 else "FAIL")
        results["mix effect card present"] = (
            "PASS" if has_effect else "FAIL")

        # --- #32: switching a row repaints the gradient ---
        compat = make_compatible(session, dlg)
        results["compatible rows selectable"] = (
            "PASS" if compat else "FAIL")
        snap0 = preview_pixels(dlg)
        repaints = False
        if compat:
            combos = mdu.filament_combos(dlg)
            crect = combos[1][1]
            cx, cy = (crect[0] + crect[2]) // 2, (crect[1] + crect[3]) // 2
            mdu.winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.2)
            mdu.winutil.real_click_screen(cx, cy)
            time.sleep(1.0)
            pop = mdu.popup_panel(session, crect[2] - crect[0])
            if pop:
                mdu.popup_pick(session, pop, 2)
                time.sleep(0.8)
            snap1 = preview_pixels(dlg)
            if snap0 is not None and snap1 is not None \
                    and snap0.shape == snap1.shape:
                diff = float(np.abs(snap0.astype(int)
                                    - snap1.astype(int)).mean())
                print(f"[m3y] preview diff after row switch: {diff:.2f}")
                repaints = diff > 2.0
                # restore the previous selection for a stable direction
                if repaints:
                    mdu.winutil.user32.SetCursorPos(cx, cy)
                    time.sleep(0.2)
                    mdu.winutil.real_click_screen(cx, cy)
                    time.sleep(1.0)
                    pop = mdu.popup_panel(session, crect[2] - crect[0])
                    if pop:
                        mdu.popup_pick(session, pop, 1)
        results["row switch repaints gradient"] = (
            "PASS" if repaints else "FAIL")

        # --- #33a: default direction registers F3->F2 ---
        registered = False
        label0 = None
        if compat:
            if not ok_and_close(session, dlg):
                return verdict(results)
            after = sidebar_entries(session)
            registered = len(after) == len(base) + 1
            label0 = after[-1][0] if registered else None
            print(f"[m3y] entries after OK: {[e[0] for e in after]}")
            results["gradient registers"] = (
                "PASS" if registered else "FAIL")
            results["default label F3->F2"] = (
                "PASS" if label0 == "F3->F2" else "FAIL")

        # --- #34/#33b: re-open in gradient, swap direction ---
        swapped = False
        if registered:
            r = sidebar_entries(session)[-1][1]
            x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            mdu.winutil.user32.SetCursorPos(x, y)
            time.sleep(0.15)
            mdu.winutil.real_click_screen(x, y)
            edlg = mdu.find_mix_dialog(session.pid, timeout_s=6.0)
            title = mdu.dialog_title(session.pid, edlg) if edlg else None
            mode = mdu.active_tab(edlg) if edlg else None
            print(f"[m3y] re-open: {title!r} mode={mode}")
            results["edit stays in gradient"] = (
                "PASS" if (edlg and "Edit Mix" in title and mode == "Gradient")
                else "FAIL")
            if edlg:
                snap0 = preview_pixels(edlg)
                for rect, h in small_buttons(edlg):
                    click_rect(rect)
                    snap1 = preview_pixels(edlg)
                    if snap0 is not None and snap1 is not None \
                            and snap0.shape == snap1.shape:
                        diff = float(np.abs(snap0.astype(int)
                                            - snap1.astype(int)).mean())
                        if diff > 8.0:
                            swapped = True
                            print(f"[m3y] swap candidate {rect} flips "
                                  f"preview (diff {diff:.2f})")
                            break
                if swapped:
                    if not ok_and_close(session, edlg):
                        swapped = False
        after2 = sidebar_entries(session)
        label1 = after2[-1][0] if after2 else None
        print(f"[m3y] entries after swap: {[e[0] for e in after2]}")
        results["swap flips direction"] = (
            "PASS" if (swapped and label1 == "F2->F3") else "FAIL")

        # --- #35: recommendation fill + Cancel registers nothing ---
        cancel_ok = False
        if swapped:
            dlg2 = mdu.open_add_mix_dialog(session)
            if dlg2:
                mdu.click_tab(session, dlg2, "Gradient")
                time.sleep(0.8)
                make_compatible(session, dlg2)
                mdu.scroll_content_to(session, dlg2,
                                      "Mixing Recommendations")
                recs = [r for r, h in []]
                hit = mdu.find_static(dlg2, "Mixing Recommendations")
                if hit:
                    ft = mdu.footer_top(dlg2)
                    ty1 = hit[1][3]
                    recs = [r for t, c, r, h in
                            mixing_util.children(dlg2)
                            if c == "wxWindowNR"
                            and 22 <= r[2] - r[0] <= 26
                            and 22 <= r[3] - r[1] <= 26
                            and ty1 - 4 <= r[1] <= ty1 + 150
                            and (ft is None or r[3] < ft - 4)
                            and mdu.user32.IsWindowVisible(h)]
                if recs:
                    click_rect(recs[0])
                mdu.click_button(session, dlg2, "Cancel")
                time.sleep(1.5)
                after3 = sidebar_entries(session)
                cancel_ok = len(after3) == len(after2)
                print(f"[m3y] entries after cancel: "
                      f"{[e[0] for e in after3]} (recs={len(recs)})")
        results["cancel registers nothing"] = (
            "PASS" if cancel_ok else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3y] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
