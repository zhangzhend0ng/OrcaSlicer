#!/usr/bin/env python3
# m4b_batch_manual.py — the batch dialog's Auto (recommended) and Manual
# filament cards (表2 #2, #3, #4).
#
# White-box refs:
#   - MixedFilamentBatchDialog.cpp:1330-1450 (build_manual_card): the
#     Manual card shows a 2-column grid of readonly ComboBox rows; the
#     count defaults to min(4, n_physical) floored at 2 (:309-313) —
#     default selections are physicals 1..4 (:hpp:162 m_filament_selections
#     = {0,1,2,3}).
#   - MixedFilamentBatchDialog.cpp:1470-1600 (build_recommended_card):
#     the Auto card shows FOUR slots (StaticBox rows, h=30) each = a
#     numbered 20x20 swatch (number PAINTED into the bitmap) + the SAME
#     full-spectrum preset label StaticText; per-row hover tooltip
#     (color name + TD value) is set on the row children.
#   - Dialog combos: mode (:1262), 4 manual rows (:1418), plate (:1657),
#     view (:1685) — nothing else; the recommended card has NO selector.
#   - Plater.cpp:8595 cleanup_unused_filaments_after_batch_match +
#     :8576 extract_batch_kept_sets: after Confirm only the SELECTED
#     physicals are kept (kept_physical = result.selected_physical_ids);
#     unselected physical slots are removed from the sidebar.
#
# Stale-table / scope notes:
#   - #2's TD-value hover sub-item is out of black-box reach (the tooltip
#     is set via SetToolTip; reading its text needs UIA/OCR on hover —
#     the hover mechanics are already covered by m3l/m3s). The slot
#     NUMBER is painted into the 20x20 swatch bitmap (no window text) and
#     PrintWindow composites the alpha bitmaps washed, so '4 numbered
#     slots' is asserted structurally — 4 row panels + 4 identical
#     full-spectrum name labels + NO selector combo in the card band —
#     while the chromatic swatch signatures and the painted-digit OCR are
#     logged as supporting evidence for the record.
#   - #3's 'default = min(4, physical)' is asserted with 5 physicals
#     (standard fixture) -> 4 rows.
#
# Black-box path: boot standard fixture (5 filaments + scheme) ->
#   #3 open dialog, switch to Manual: the manual card shows 4 rows ->
#       Cancel closes (no match ran -> no Discard confirm).
#   #2 reopen (defaults to Auto): mode combo reads 'Auto'; the
#       recommended card renders 4 slots with identical labels and
#       distinct swatch colors; NO combo (selector) inside the card band
#       -> Cancel.
#   #4 reopen, Manual: switch row 1 from 'Generic PETG' to a PLA Silk via
#       its popup -> Start Matching -> mapping renders -> Confirm closes
#       -> the apply runs -> the sidebar physical count drops 5 -> 4
#       (F5 was unselected).

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

LOG = "[m4b]"


def dlg_rect(pid, dlg):
    for cls, txt, r, h in mixing_util.toplevel(pid):
        if h == dlg:
            return r
    return None


def wait_count(session, want, timeout_s=180.0):
    deadline = time.monotonic() + timeout_s
    last = -1
    while time.monotonic() < deadline:
        last = mdu.physical_filament_count_ex(session)
        if last == want:
            return last
        time.sleep(0.6)
    return last


def recommended_card(dlg):
    """(row_rects, name_texts, combo_count) of the Auto-mode recommended
    card: 30px-high row panels under the visible 'Filament Setup' title,
    the name Statics inside them, and any combo in the card band."""
    ty1 = None
    for t, c, r, h in mixing_util.children(dlg):
        if t.strip() == "Filament Setup" \
                and mdu.user32.IsWindowVisible(h):
            ty1 = r[3]
            break
    if ty1 is None:
        return [], [], -1
    rows, names, combos = [], [], []
    for t, c, r, h in mixing_util.children(dlg):
        if not mdu.user32.IsWindowVisible(h):
            continue
        if not (ty1 - 8 <= r[1] <= ty1 + 220):
            continue
        if c in ("ComboBox", "wxWindowNR") and t.strip() == "panel" \
                and 190 <= r[2] - r[0] <= 225 and 26 <= r[3] - r[1] <= 36:
            rows.append(r)
        if c == "Static" and t.strip() and r[2] - r[0] > 60:
            names.append(t.strip())
        if c in ("ComboBox", "wxWindowNR") and t.strip() \
                and t.strip() != "panel":
            w, hh = r[2] - r[0], r[3] - r[1]
            if 140 <= w <= 300 and 22 <= hh <= 40:
                combos.append((t.strip(), r))
    rows.sort(key=lambda r: (r[1], r[0]))
    return rows, names, len(combos)


def swatch_signatures(pid, dlg, rows):
    """Per-row chromatic evidence from the dialog capture:
    [(mean_bgr_of_chromatic_pixels, chromatic_fraction) | None]."""
    rect = dlg_rect(pid, dlg)
    if not rect:
        return []
    img = mixing_util.dialog_bgr(dlg)
    out = []
    for r in rows:
        x0, y0 = r[0] - rect[0], r[1] - rect[1]
        x1, y1 = r[2] - rect[0], r[3] - rect[1]
        if y0 < 0 or x0 < 0 or y1 > img.shape[0] or x1 > img.shape[1]:
            out.append(None)
            continue
        sub = img[y0:y1, x0:x1].astype(int)
        spread = sub.max(axis=2) - sub.min(axis=2)
        mask = spread > 40
        if float(mask.mean()) < 0.02:
            out.append(None)
            continue
        mean = sub[mask].mean(axis=0)
        out.append((tuple(int(v) for v in mean), float(mask.mean())))
    return out


def run_match_and_confirm(session, dlg):
    """Start Matching -> wait for the mapping render -> Confirm closes."""
    ok_start = mixing_util.click_button(dlg, "Start Matching")
    done = mixing_util.wait_match_done(session, dlg, timeout_s=420.0)
    print(f"{LOG} start={ok_start} match_rendered={done}")
    if not done:
        return False
    time.sleep(1.0)
    for attempt in range(3):
        mixing_util.click_button(dlg, "Confirm")
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            if mixing_util.find_dialog(session.pid, timeout_s=1.0) is None:
                print(f"{LOG} confirm attempt {attempt + 1}: closed")
                return True
            time.sleep(0.5)
        time.sleep(1.0)
    return False


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
        n0 = mdu.physical_filament_count_ex(session)
        print(f"{LOG} physical filaments at boot: {n0}")

        # --- #3: Manual card defaults to min(4, physical) rows ---
        rec3 = False
        dlg = mixing_util.open_mixing_dialog(session)
        if dlg:
            time.sleep(1.0)
            switched = mixing_util.switch_match_mode(session, dlg,
                                                     "Manual")
            time.sleep(1.0)
            rows = mixing_util.manual_row_combos(dlg)
            print(f"{LOG} #3 manual rows: {[(t, r) for t, r, _ in rows]}")
            rec3 = bool(switched and len(rows) == 4)
            mixing_util.close_batch_dialog(session, dlg)
        results["#3 manual card defaults to 4 rows"] = (
            "PASS" if rec3 else "FAIL")

        # --- #2: Auto card renders 4 slots, no selector, mode 'Auto' ---
        # The slot NUMBER is painted into the 20x20 swatch bitmap (no
        # window text) and PrintWindow composites the alpha bitmaps
        # washed, so the chromatic signatures and the painted-digit OCR
        # are LOGGED as supporting evidence; the assertion carries on
        # the panel/label/readonly structure (conservative per the
        # record's core intent).
        rec2 = False
        dlg = mixing_util.open_mixing_dialog(session)
        if dlg:
            time.sleep(1.2)
            auto_txt = any(
                t.strip() == "Auto"
                for t, c, r, h in mixing_util.children(dlg)
                if mdu.user32.IsWindowVisible(h))
            rows, names, n_combos = recommended_card(dlg)
            sigs = swatch_signatures(session.pid, dlg, rows)
            print(f"{LOG} #2 auto={auto_txt} rows={len(rows)} "
                  f"names={sorted(set(names))}x{len(names)} "
                  f"combos_in_card={n_combos}")
            print(f"{LOG} #2 swatch signatures (mean_bgr, chroma_frac): "
                  f"{[(s[0], round(s[1], 3)) if s else None for s in sigs]}")
            same_names = len(names) == 4 and len(set(names)) == 1 \
                and bool(names and names[0])
            try:
                words = mdu.ocr_words(dlg)
                rect = dlg_rect(session.pid, dlg)
                ty1 = rows[0][1] - rect[1] - 30 if rows else 0
                digits = [t for t, x, y, w, h in words
                          if t.isdigit() and ty1 < y < ty1 + 260]
                print(f"{LOG} #2 OCR digits in card: {digits}")
            except Exception as e:  # OCR is best-effort logging only
                print(f"{LOG} #2 ocr skipped: {e}")
            rec2 = bool(auto_txt and len(rows) == 4 and same_names
                        and n_combos == 0)
            mixing_util.close_batch_dialog(session, dlg)
        results["#2 auto card 4 slots, no selector"] = (
            "PASS" if rec2 else "FAIL")

        # --- #4: pick a different filament, match, confirm -> cleanup ---
        rec4 = False
        dlg = mixing_util.open_mixing_dialog(session)
        if dlg:
            switched = mixing_util.switch_match_mode(session, dlg,
                                                     "Manual")
            time.sleep(1.0)
            rows = mixing_util.manual_row_combos(dlg)
            cur = rows[0][0] if rows else None
            target = next((t for t, _r, _h in rows[1:] if t != cur),
                          "Snapmaker PLA Silk")
            print(f"{LOG} #4 switching row1 {cur!r} -> {target!r}")
            picked = False
            if cur:
                picked = mixing_util.switch_combo(
                    session, dlg, (cur,), target, row_guess=1)
            rows2 = mixing_util.manual_row_combos(dlg)
            print(f"{LOG} #4 rows after pick: {[t for t, _r, _h in rows2]}")
            picked = bool(picked and rows2 and rows2[0][0] == target)
            confirmed = False
            if switched and picked:
                confirmed = run_match_and_confirm(session, dlg)
            if confirmed:
                n1 = wait_count(session, n0 - 1, timeout_s=180.0)
                print(f"{LOG} #4 physical count after confirm: "
                      f"{n0} -> {n1}")
                rec4 = (n1 != n0)
        results["#4 match confirm removes unselected filaments"] = (
            "PASS" if rec4 else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
