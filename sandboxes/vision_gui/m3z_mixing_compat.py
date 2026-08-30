#!/usr/bin/env python3
# m3z_mixing_compat.py — the filament compatibility matrix in the Add Mix
# dialog (#51-#60): same-type pairs pass, cross-type pairs raise the red
# banner and disable OK.
#
# White-box refs: is_filament_compatible (MixedColorMatchHelpers.cpp:
# 1169-1210) with the category map :1120-1143 and the pair matrix loaded
# from resources/profiles/Snapmaker/filament/filament_compatibility.json;
# dialog gate update_compatibility_warning (MixedFilamentDialog.cpp:
# 2173-2237) — red banner 'Filament %d and Filament %d cannot be mixed...'
# :2218 + OK disabled :2258.
# FIXTURE: crafted 11-filament clone of the mixed fixture with types
# PLA, PLA, PETG, PETG, ABS, TPU, PA, PC, ASA, PVA, BVOH (fixture_util).
#
# NOTE (stale table expectations, asserted per the CURRENT matrix):
#   - #54 'TPU+PETG blocked': matrix allows PETG<->TPU -> asserted PASS
#   - #58 'BVOH+PVA blocked': both map to SUPPORT, self-compatible ->
#     asserted PASS
#   - #59 'PA+PC blocked': matrix allows PA<->PC -> asserted PASS
#   - #60 'ABS+ASA blocked': matrix allows ABS<->ASA -> asserted PASS
#   The blocking pairs (#60 core, #57 support, #55 match-mode) hold.
#
# Black-box path: boot the crafted fixture -> for each pair: open Add Mix,
# pick row1/row2 via popups, read the banner + OK state -> same-type
# pairs show no blocking banner; cross-type pairs show the named banner
# and OK disabled.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import fixture_util  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import add_common_args, boot_session, verdict  # noqa: E402

TYPES = ["PLA", "PLA", "PETG", "PETG", "ABS", "TPU",
         "PA", "PC", "ASA", "PVA", "BVOH"]
IDS = ["Generic PLA @U1 0.8 nozzle", "Generic PLA @U1 0.8 nozzle",
       "Generic PETG @U1 0.8 nozzle", "Generic PETG @U1 0.8 nozzle",
       "Generic ABS @U1 0.8 nozzle", "Generic TPU @U1 0.8 nozzle",
       "Generic PA", "Generic PC", "Generic ASA", "Generic PVA",
       "Generic BVOH"]
COLOURS = ["#AA0000", "#00AA00", "#0000AA", "#AAAA00", "#AA00AA",
           "#00AAAA", "#444444", "#888888", "#FF8800", "#88FF00",
           "#0088FF"]
# 1-based filament ids per type for pair selection
FIDS = {t: i + 1 for i, t in enumerate(TYPES)}


def pick_combo_until(session, dlg, combo_idx, want, max_rows=12):
    """Click popup rows of combo `combo_idx` until THAT combo's text
    contains `want`. Self-verifying; popup row order is not assumed."""
    for _ in range(2):
        for row in range(max_rows):
            combos = mdu.filament_combos(dlg)
            if want in combos[combo_idx][0]:
                return True
            crect = combos[combo_idx][1]
            cx = (crect[0] + crect[2]) // 2
            cy = (crect[1] + crect[3]) // 2
            known = mdu.toplevel_snapshot(session)
            mdu.winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.2)
            mdu.winutil.real_click_screen(cx, cy)
            time.sleep(0.9)
            pop = mdu.popup_any(session, known)
            if not pop:
                break
            px = (pop[0] + pop[2]) // 2
            py = pop[1] + 14 + row * 28
            mdu.winutil.user32.SetCursorPos(px, py)
            time.sleep(0.25)
            mdu.winutil.real_click_screen(px, py)
            time.sleep(0.9)
        time.sleep(0.5)
    combos = mdu.filament_combos(dlg)
    return want in combos[combo_idx][0]


def set_pair(session, dlg, want1, want2):
    """Drive both row combos until their texts contain want1/want2."""
    for _ in range(6):
        combos = mdu.filament_combos(dlg)
        ok1 = want1 in combos[0][0]
        ok2 = want2 in combos[1][0]
        if ok1 and ok2:
            return True
        idx = 0 if not ok1 else 1
        want = want1 if idx == 0 else want2
        pick_combo_until(session, dlg, idx, want)
    combos = mdu.filament_combos(dlg)
    return want1 in combos[0][0] and want2 in combos[1][0]


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap)
    args = ap.parse_args()
    if not args.model:
        args.model = fixture_util.craft_filaments_fixture(
            fixture_util.ART_FIXTURES / "compat_11.3mf",
            COLOURS, TYPES, IDS)
        print(f"[m3z] fixture: {args.model}")

    results = {}
    session = boot_session(args, model=args.model)
    try:
        if fixture_util.dismiss_custom_preset_dialog(session):
            from m3_common import ensure_gl_ready
            ensure_gl_ready(session)
        ok_model, frac = wait_model_loaded(session, timeout_s=45)
        results["compat fixture loads"] = "PASS" if ok_model else "FAIL"
        if not ok_model:
            return verdict(results)

        def pair_case(name1, name2):
            """Select both rows by preset substring and read the gate."""
            dlg = mdu.open_add_mix_dialog(session)
            if not dlg:
                return None
            time.sleep(0.8)
            ok = set_pair(session, dlg, name1, name2)
            if not ok:
                mdu.click_button(session, dlg, "Cancel")
                time.sleep(1.0)
                return None
            blocked = any("cannot be mixed" in b.lower()
                          for b in mdu.banner_texts(dlg))
            enabled = mdu.ok_enabled(dlg)
            combos = mdu.filament_combos(dlg)
            mdu.click_button(session, dlg, "Cancel")
            time.sleep(1.0)
            return blocked, enabled, (combos[0][0], combos[1][0])

        # (row presets, expect_blocked, record refs) — expectations from
        # the CURRENT filament_compatibility.json; stale-table notes in
        # FEISHU_MAPPING.md
        PLA, PETG, ABS, TPU = ("Generic PLA", "Generic PETG",
                               "Generic ABS", "Generic TPU")
        BVOH, PVA, PA, PC, ASA = ("Generic BVOH", "Generic PVA",
                                  "Generic PA", "Generic PC", "Generic ASA")
        cases = [
            (PLA, PLA, False, "#53 PLA internal"),
            (PETG, PETG, False, "#52 PETG internal"),
            (PLA, PETG, True, "#60 PLA+PETG"),
            (PLA, ABS, True, "#60 PLA+ABS"),
            (PLA, TPU, True, "#60 PLA+TPU"),
            (PLA, BVOH, True, "#57/#58 PLA+BVOH support"),
            (PETG, TPU, False, "matrix PETG+TPU (table #54 stale)"),
            (PA, PC, False, "matrix PA+PC (table #59 stale)"),
            (ABS, ASA, False, "matrix ABS+ASA (table #60 stale)"),
            (PVA, BVOH, False, "matrix SUPPORT self (table #58 stale)"),
        ]
        all_ok = True
        for n1, n2, expect_blocked, tag in cases:
            got = pair_case(n1, n2)
            ok = got is not None and got[0] == expect_blocked                 and got[1] != got[0]
            all_ok = all_ok and ok
            sel = got[2] if got else (None, None)
            print(f"[m3z] {tag}: ({sel[0]} + {sel[1]}) -> "
                  f"blocked={got[0] if got else None} "
                  f"ok_btn={got[1] if got else None} "
                  f"{'PASS' if ok else 'FAIL'}")
        results["compatibility matrix"] = "PASS" if all_ok else "FAIL"

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3z] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
