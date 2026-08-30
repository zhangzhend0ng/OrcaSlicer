#!/usr/bin/env python3
# m4j_mixing_samecolor.py — same-colour mixing is ALLOWED (表1 #9), the
# 5-distinct-filament Cycle advisory warns WITHOUT blocking (表1 #16), and
# the batch dialog's Manual match renders a mapping list on a same-colour
# fixture (表2 #7/#9 partial).
#
# White-box refs:
#   - MixedFilamentDialog.cpp:2173-2237 — the compat gate keys on
#     filament TYPE (is_filament_compatible, MixedColorMatchHelpers.cpp:
#     1169-1210 + filament_compatibility.json); identical COLORS carry no
#     gate, so a pair of same-colour PLA filaments passes with no banner
#     and OK enabled (record #9's intent: identical colours no longer
#     block).
#   - MixedFilamentDialog.cpp:2226/:2229 — the >4 DISTINCT filaments Cycle
#     advisory 'Excessive filaments in the mix may affect the result.
#     Please use with caution.' is orange and does NOT disable OK
#     (advisory, not blocking); the seeded fixture only has 4 compatible
#     filaments, so per FEISHU_MAPPING this assert lives here on an
#     all-PLA 5-filament fixture.
#   - MixedFilamentBatchDialog — Manual mode start_batch_match (:2273) is
#     palette-agnostic; completion renders the color-mapping list
#     (swatches; chromatic fraction 0 -> ~0.12, m3k measurement) and
#     Cancel then pops 'Discard Matching' (:1826).
#
# Scope / partial notes (FEISHU_MAPPING.md):
#   - 表2 #7/#9: the mapping LIST rendering is asserted; the ΔE<1
#     map-to-first-same-colour DETAIL is out of black-box reach (needs
#     per-swatch ΔE values — left MANUAL like m3l's tooltip sub-item).
#   - Popup rows share one preset label on this all-PLA fixture ('Generic
#     PLA @U1 0.8 nozzle'), so the same-colour PAIR (F3+F4, both
#     #00C1AE) is driven by popup row index and self-verified through the
#     registered sidebar label 'F3 50%+F4 50%' (parse the ids); wrong
#     pairs are deleted via the entry Options menu and retried.
#
# Black-box path: craft a 5-filament all-PLA fixture with F3/F4 the SAME
# colour, no seeded scheme -> boot (dismiss 'Customized Preset') ->
# #9: Add Mix opens with default F1+F2 (same type) -> NO blocking banner,
# OK enabled -> drive row 1/row 2 popups to the same-colour pair -> still
# no banner -> OK -> the sidebar gains a 'F3 50%+F4 50%' entry ->
# #16: new Add Mix, Cycle tab, type '12345' -> the excessive-filaments
# advisory shows AND OK stays ENABLED -> Cancel -> 表2: open 'Color Mixing
# Match', Manual, Start Matching -> the mapping list renders -> Cancel ->
# Discard -> app alive.

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import fixture_util  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import (add_common_args, boot_session, ensure_gl_ready,  # noqa: E402
                       verdict)
from m3u_mixing_ratio_flow import compat_blocked  # noqa: E402

LOG = "[m4j]"
COLOURS = ["#D9A63A", "#ECED17", "#00C1AE", "#00C1AE", "#F4E2C1"]
TYPES = ["PLA"] * 5
IDS = ["Generic PLA @U1 0.8 nozzle"] * 5
ADVISORY = "excessive filaments"


def entries(session):
    out = [(t, r) for t, r, _h in mdu.mix_entry_labels(session)]
    out.sort(key=lambda x: x[1][1])
    return out


def label_ids(text):
    return set(re.findall(r"F(\d+)", text))


def register_same_colour_pair(session, max_picks=((0, 1), (1, 1), (2, 1),
                                                  (1, 2))):
    """Open Add Mix (the all-PLA defaults are already compatible), drive
    row 1/row 2 popups by index toward the same-colour F3+F4 pair, OK, and
    verify through the registered label; wrong pairs are deleted via the
    entry Options menu and the next index pair is tried. Returns
    (hit, pair_label, last_blocked_all_ok) where hit means the registered
    label cites exactly filaments 3 and 4."""
    hit = False
    pair_label = None
    ever_blocked = False
    base = entries(session)
    for i, j in max_picks:
        dlg = mdu.open_add_mix_dialog(session)
        if not dlg:
            break
        time.sleep(1.0)
        blocked0 = compat_blocked(dlg)
        ever_blocked = ever_blocked or blocked0
        if blocked0:
            mdu.click_button(session, dlg, "Cancel")
            time.sleep(1.0)
            continue
        ok1 = mdu.pick_popup_index(session, dlg, 0, i)
        ok2 = mdu.pick_popup_index(session, dlg, 1, j)
        combos = mdu.filament_combos(dlg)
        sel = tuple(c[0] for c in combos[:2])
        blocked = compat_blocked(dlg)
        ok_en = mdu.ok_enabled(dlg)
        print(f"{LOG} pair attempt ({i},{j}): picked={ok1}/{ok2} "
              f"rows={sel} blocked={blocked} ok={ok_en} "
              f"legends={mdu.legend_pcts(dlg)}")
        if not (ok1 and ok2) or blocked or not ok_en:
            ever_blocked = ever_blocked or blocked
            mdu.click_button(session, dlg, "Cancel")
            time.sleep(1.0)
            continue
        mdu.click_button(session, dlg, "OK")
        time.sleep(2.0)
        if mdu.find_mix_dialog(session.pid, timeout_s=2.0) is not None:
            mdu.click_button(session, dlg, "Cancel")
            time.sleep(1.0)
            continue
        ents = entries(session)
        if len(ents) != len(base) + 1:
            print(f"{LOG} registration did not add an entry: "
                  f"{[e[0] for e in ents]}")
            continue
        fresh = [e for e in ents if e[0] not in [b[0] for b in base]]
        text, rect = fresh[0] if fresh else ents[-1]
        ids = label_ids(text)
        print(f"{LOG} registered {text!r} ids={sorted(ids)} (want 3+4)")
        if ids == {"3", "4"}:
            return True, text, ever_blocked
        mdu.menu_delete_entry(session, rect)
        time.sleep(1.5)
    return hit, pair_label, ever_blocked


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap)
    args = ap.parse_args()
    if not args.model:
        args.model = fixture_util.craft_filaments_fixture(
            fixture_util.ART_FIXTURES / "samecolor_5_pla.3mf",
            COLOURS, TYPES, IDS, strip_mixed=True)
        print(f"{LOG} fixture: {args.model}")

    results = {}
    session = boot_session(args, model=args.model)
    try:
        dismissed = fixture_util.dismiss_custom_preset_dialog(
            session, timeout_s=30)
        if dismissed:
            ensure_gl_ready(session)
        print(f"{LOG} customized-preset dialog dismissed: {dismissed}")
        ok_model, frac = wait_model_loaded(session, timeout_s=60)
        print(f"{LOG} model loaded: {ok_model}")
        results["same-colour fixture loads"] = (
            "PASS" if ok_model else "FAIL")
        if not ok_model:
            return verdict(results)
        time.sleep(2.0)
        results["no seeded scheme"] = (
            "PASS" if not entries(session) else "FAIL")

        # --- #9: same-type default pair unblocked + same-colour pair ---
        hit, pair_label, ever_blocked = register_same_colour_pair(session)
        ents = entries(session)
        print(f"{LOG} #9: hit={hit} label={pair_label!r} "
              f"ever_blocked={ever_blocked} entries={[e[0] for e in ents]}")
        results["#9 same-type pair: no blocking banner"] = (
            "PASS" if not ever_blocked else "FAIL")
        results["#9 identical-colour pair registers (F3+F4)"] = (
            "PASS" if (hit and pair_label and len(ents) == 1) else "FAIL")

        # --- #16: Cycle '12345' -> excessive-filaments advisory, OK on ---
        advised = ok_stayed = False
        dlg2 = mdu.open_add_mix_dialog(session)
        if dlg2:
            time.sleep(1.0)
            if mdu.click_tab(session, dlg2, "Cycle") \
                    and mdu.active_tab(dlg2) == "Cycle":
                got = mdu.real_edit_text(session, dlg2, "12345")
                banners = mdu.banner_texts(dlg2)
                advised = any(ADVISORY in b.lower() for b in banners)
                ok_stayed = mdu.ok_enabled(dlg2)
                print(f"{LOG} #16 pattern={got!r} banners={banners} "
                      f"ok={ok_stayed}")
            else:
                print(f"{LOG} #16 cycle tab did not activate")
            mdu.click_button(session, dlg2, "Cancel")
            time.sleep(1.5)
        results["#16 5-distinct advisory warns, OK enabled"] = (
            "PASS" if (advised and ok_stayed) else "FAIL")

        # --- 表2 #7/#9 (partial): Manual match renders the mapping list ---
        b_open = b_manual = b_started = b_done = b_closed = False
        bdlg = mixing_util.open_mixing_dialog(session)
        print(f"{LOG} batch dialog: {hex(bdlg) if bdlg else None}")
        b_open = bool(bdlg)
        if b_open:
            b_manual = mixing_util.switch_match_mode(session, bdlg,
                                                     "Manual")
            time.sleep(1.0)
            b_started = mixing_util.click_button(bdlg, "Start Matching")
            b_done = mixing_util.wait_match_done(session, bdlg,
                                                 timeout_s=420.0)
            rows = mixing_util.swatch_rows(bdlg)
            if rows and b_started:
                b_done = True
            print(f"{LOG} batch: manual={b_manual} started={b_started} "
                  f"done={b_done} swatch_rows={len(rows)}")
            b_closed = mixing_util.close_batch_dialog(session, bdlg)
            print(f"{LOG} batch closed (Discard confirmed): {b_closed}")
        results["t2 #7/#9 manual match renders mapping list"] = (
            "PASS" if (b_open and b_manual and b_started and b_done
                       and b_closed) else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
