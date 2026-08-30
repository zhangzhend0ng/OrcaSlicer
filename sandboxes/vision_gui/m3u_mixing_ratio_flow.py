#!/usr/bin/env python3
# m3u_mixing_ratio_flow.py — the Ratio-mode round trip: a recommendation
# preset fills 50:50 and CONFIRM registers the scheme (#5/#6), single-
# clicking a sidebar entry opens Edit Mix with the stored params (#7/#43),
# confirming an edit updates the label in place, and CANCEL abandons both
# adds and edits (#8).
#
# White-box refs: MixedFilamentDialog (recommendation badges + tooltips
# :2613-2695, click sets selector :2838-2857, OK/Cancel :1172/:1180,
# collect_result :3246); sidebar entries Plater.cpp:6577-7025 (label
# 'F%u %d%%+F%u %d%%' :6707, single-click opens Edit Mix :6769-6777,
# persisted to mixed_filament_definitions :6544).
# Seeded fixture already contains ONE ratio entry ('F3 50%+F2 50%'), so
# counts are relative: 1 -> 2 after the add.
#
# Black-box path: boot -> open Add Mix -> switch row 1 to a PLA (banner
# clears) -> drag the selector to an extreme -> click a recommendation
# badge: legends snap back to 50/50 and the preview repaints -> OK: the
# dialog closes and a NEW 'F<n> 50%+F<m> 50%' entry appears -> click it:
# 'Edit Mix' opens with Ratio active and 50/50 preserved -> selector to
# 75/25 -> OK: the label updates in place -> edit again, Cancel: label
# unchanged -> Add Mix again, change, Cancel: no new entry.

import re
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

LABEL_RE = re.compile(r"^F\d+ \d+%(\+F\d+ \d+%)+$")


def sidebar_entries(session):
    """Sidebar mixing labels as (text, rect) sorted top->bottom."""
    out = [(t.strip(), r) for t, r, h in mdu.mix_entry_labels(session)]
    out.sort(key=lambda x: x[1][1])
    return out


def compat_blocked(dlg):
    """True while the CROSS-TYPE error banner shows (advisories such as
    'ratio is too high' do NOT block OK and must not count)."""
    low = [b.lower() for b in mdu.banner_texts(dlg)]
    return any(("cannot be mixed" in b) or ("different filament types" in b)
               for b in low)


def make_compatible(session, dlg):
    """Switch row 1 via its popup until the cross-type banner clears."""
    combos = mdu.filament_combos(dlg)
    crect = combos[0][1]
    cx, cy = (crect[0] + crect[2]) // 2, (crect[1] + crect[3]) // 2
    for _attempt in range(3):
        for _round in range(4):
            mdu.winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.2)
            mdu.winutil.real_click_screen(cx, cy)
            time.sleep(1.0)
            pop = mdu.popup_panel(session, crect[2] - crect[0])
            if not pop:
                continue
            for row in range(0, 4):
                mdu.popup_pick(session, pop, row)
                if not compat_blocked(dlg):
                    return True
                mdu.winutil.user32.SetCursorPos(cx, cy)
                time.sleep(0.2)
                mdu.winutil.real_click_screen(cx, cy)
                time.sleep(1.0)
                pop = mdu.popup_panel(session, crect[2] - crect[0])
                if not pop:
                    break
    return False


def rec_badges(dlg):
    """24x24 swatch panels below the 'Mixing Recommendations' title that
    sit ABOVE the footer band (the grid lives in the scrolled content and
    is covered by the OK/Cancel footer until the content is scrolled)."""
    hit = mdu.find_static(dlg, "Mixing Recommendations")
    if not hit:
        return []
    ft = mdu.footer_top(dlg)
    ty1 = hit[1][3]
    out = [(r, h) for t, c, r, h in mixing_util.children(dlg)
           if c == "wxWindowNR" and 22 <= r[2] - r[0] <= 26
           and 22 <= r[3] - r[1] <= 26 and ty1 - 4 <= r[1] <= ty1 + 150
           and (ft is None or r[3] < ft - 4)
           and mdu.user32.IsWindowVisible(h)]
    out.sort(key=lambda rh: (rh[0][1], rh[0][0]))
    return [r for r, _h in out]


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
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"
        base_entries = sidebar_entries(session)
        print(f"[m3u] base sidebar entries: {[e[0] for e in base_entries]}")
        results["seeded entry present"] = (
            "PASS" if len(base_entries) >= 1 else "FAIL")

        dlg = mdu.open_add_mix_dialog(session)
        results["add mix dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)
        time.sleep(1.0)

        # --- make the pair compatible, then #5: a rec preset fills 50/50 ---
        switched = make_compatible(session, dlg)
        results["compatible pair selectable"] = (
            "PASS" if switched else "FAIL")

        rec_ok = False
        filled = False
        if switched:
            sel = mdu.ratio_selector(dlg)
            if sel:
                mdu.click_selector_frac(session, dlg, sel[0], 0.97)
                print(f"[m3u] pre-rec legends: {mdu.legend_pcts(dlg)}")
            pv = mdu.panel_below(dlg, "Preview")
            snap0 = mdu.hwnd_pixels(pv[1]) if pv else None
            mdu.scroll_content_to(session, dlg, "Mixing Recommendations")
            badges = rec_badges(dlg)
            print(f"[m3u] rec badges: {len(badges)}")
            if badges:
                click_rect(badges[0])
                legs = mdu.legend_pcts(dlg)
                print(f"[m3u] legends after rec click: {legs}")
                filled = legs == [50, 50]
                snap1 = mdu.hwnd_pixels(pv[1]) if pv else None
                moved = False
                if snap0 is not None and snap1 is not None \
                        and snap0.shape == snap1.shape:
                    diff = float(np.abs(snap0.astype(int)
                                        - snap1.astype(int)).mean())
                    print(f"[m3u] preview diff after rec: {diff:.2f}")
                    moved = diff > 1.0
                rec_ok = filled and moved
        results["rec preset fills 50/50"] = (
            "PASS" if filled else "FAIL")

        # --- #6: OK registers the scheme ---
        registered = False
        new_label = None
        if switched and filled:
            mdu.click_button(session, dlg, "OK")
            time.sleep(2.0)
            gone = mdu.find_mix_dialog(session.pid, timeout_s=3.0) is None
            entries = sidebar_entries(session)
            print(f"[m3u] entries after OK: {[e[0] for e in entries]}")
            registered = gone and len(entries) == len(base_entries) + 1
            if registered:
                new_label = entries[-1][0]
                results["new entry is 50/50 label"] = (
                    "PASS" if LABEL_RE.match(new_label)
                    and "50%+F" in new_label else "FAIL")
        results["confirm registers scheme"] = (
            "PASS" if registered else "FAIL")

        # --- #7/#43: click the new entry -> Edit Mix with stored params ---
        edited = False
        if registered:
            click_rect(entries[-1][1])
            edlg = mdu.find_mix_dialog(session.pid, timeout_s=6.0)
            title = mdu.dialog_title(session.pid, edlg) if edlg else None
            print(f"[m3u] edit dialog: {hex(edlg) if edlg else None} "
                  f"title={title!r}")
            results["click entry opens Edit Mix"] = (
                "PASS" if edlg and "Edit Mix" in title else "FAIL")
            results["edit preserves mode"] = (
                "PASS" if edlg and mdu.active_tab(edlg) == "Ratio"
                else "FAIL")
            results["edit preserves params"] = (
                "PASS" if edlg and mdu.legend_pcts(edlg) == [50, 50]
                else "FAIL")
            if edlg:
                sel = mdu.ratio_selector(edlg)
                if sel:
                    mdu.click_selector_frac(session, edlg, sel[0], 0.75)
                    time.sleep(0.5)
                    legs = mdu.legend_pcts(edlg)
                    print(f"[m3u] edited legends: {legs}")
                    edited = mdu.ok_enabled(edlg)
                    mdu.click_button(session, edlg, "OK")
                    time.sleep(2.0)
        results["edit confirm enabled"] = "PASS" if edited else "FAIL"

        entries2 = sidebar_entries(session)
        updated = any(" 25%+" in e[0] for e in entries2) if edited else False
        print(f"[m3u] entries after edit: {[e[0] for e in entries2]}")
        results["edit updates label in place"] = (
            "PASS" if updated else "FAIL")

        # --- #8b: edit again, Cancel keeps the label ---
        kept = False
        if updated:
            target = [e for e in entries2 if " 25%+" in e[0]][0]
            click_rect(target[1])
            edlg2 = mdu.find_mix_dialog(session.pid, timeout_s=6.0)
            if edlg2:
                sel = mdu.ratio_selector(edlg2)
                if sel:
                    mdu.click_selector_frac(session, edlg2, sel[0], 0.03)
                mdu.click_button(session, edlg2, "Cancel")
                time.sleep(1.5)
                entries3 = sidebar_entries(session)
                kept = (len(entries3) == len(entries2)
                        and any(" 25%+" in e[0] for e in entries3))
                print(f"[m3u] entries after cancel-edit: "
                      f"{[e[0] for e in entries3]}")
        results["cancel edit keeps label"] = "PASS" if kept else "FAIL"

        # --- #8a: add flow, Cancel adds nothing ---
        no_add = False
        if kept:
            dlg2 = mdu.open_add_mix_dialog(session)
            if dlg2:
                sel = mdu.ratio_selector(dlg2)
                if sel:
                    mdu.click_selector_frac(session, dlg2, sel[0], 0.97)
                mdu.click_button(session, dlg2, "Cancel")
                time.sleep(1.5)
                entries4 = sidebar_entries(session)
                no_add = len(entries4) == len(entries2)
                print(f"[m3u] entries after cancel-add: "
                      f"{[e[0] for e in entries4]}")
        results["cancel add registers nothing"] = (
            "PASS" if no_add else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3u] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
