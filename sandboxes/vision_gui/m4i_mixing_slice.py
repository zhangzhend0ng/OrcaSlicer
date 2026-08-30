#!/usr/bin/env python3
# m4i_mixing_slice.py — mixed-slice + export chain (表1 #50 partial): two
# schemes of DIFFERENT modes are registered (Ratio 50/50 + Gradient), the
# mixed project slices to completion, and the gcode exports to a non-empty
# file whose text carries multiple distinct tool-change commands.
#
# White-box refs:
#   - MixedFilamentDialog — Ratio registers 'F%u %d%%+F%u %d%%' labels
#     (Plater.cpp:6707); Gradient forces 2 rows and registers 'F%u->F%u'
#     (Plater.cpp:6703, direction 0 = A->B, MixedFilament.hpp:75-81).
#   - MainFrame::can_export_gcode -> is_slice_result_ready_for_print gates
#     the export on a COMPLETED slice (MainFrame.cpp:1600, export_util).
#
# Stale-table / scope notes (表1 #50):
#   - '上传并打印' (upload & print on a physical device) is OUT of black-box
#     scope (needs a physical printer; not automatable here).
#   - The mixing-marker parse is kept LOOSE on purpose: the U1 gcode speaks
#     plain tool-change commands (measured on prior exports of this exact
#     fixture: T0 x2 / T1 x57 / T2 x59 / T3 x3 / T4 x2, plus EXTRUDER and
#     mixed_filament_definitions config echoes; no M163/M163-style mixing
#     commands in the current format). The assertion is >=2 DISTINCT ^T<n>
#     tool-change commands in the exported text.
#
# Black-box path: boot standard fixture (5 filaments + seeded scheme) ->
# Add Mix: make the pair compatible (row-1 popup), OK -> sidebar +1 ratio
# entry -> Add Mix: Gradient tab, make compatible, OK -> sidebar +1
# 'F<n>->F<m>' entry -> Slice plate -> done badge -> export gcode ->
# file non-empty + >=2 distinct tool-change markers -> app alive.

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import (MIXED_3MF, add_common_args, boot_session,  # noqa: E402
                       export_and_check, slice_and_wait, verdict)
from m3u_mixing_ratio_flow import (compat_blocked, make_compatible,  # noqa: E402
                                   sidebar_entries)

LOG = "[m4i]"
LABEL_RATIO = re.compile(r"^F\d+ \d+%(\+F\d+ \d+%)+$")
LABEL_GRADIENT = re.compile(r"^F\d+->F\d+$")


def register_scheme(session, mode, n_before):
    """Open Add Mix, switch to `mode`, make the pair compatible, OK.
    Returns (registered, label). The label can be IDENTICAL to a seeded
    entry's text (make_compatible re-picks row 1 to F3 — the seeded pair),
    so registration is detected by COUNT and the label read positionally
    (new entries append at the end)."""
    dlg = mdu.open_add_mix_dialog(session)
    if not dlg:
        return False, None
    time.sleep(1.0)
    if mode == "Gradient":
        mdu.click_tab(session, dlg, "Gradient")
        time.sleep(0.8)
    switched = make_compatible(session, dlg)
    blocked = compat_blocked(dlg)
    ok_en = mdu.ok_enabled(dlg)
    print(f"{LOG} add {mode}: switched={switched} blocked={blocked} "
          f"ok={ok_en} legends={mdu.legend_pcts(dlg)}")
    if not (switched and ok_en):
        mdu.click_button(session, dlg, "Cancel")
        time.sleep(1.2)
        return False, None
    mdu.click_button(session, dlg, "OK")
    time.sleep(2.5)
    if mdu.find_mix_dialog(session.pid, timeout_s=3.0) is not None:
        mdu.click_button(session, dlg, "Cancel")
        time.sleep(1.0)
        return False, None
    ents = sidebar_entries(session)
    print(f"{LOG} entries after {mode}: {[e[0] for e in ents]}")
    if len(ents) != n_before + 1:
        return False, None
    return True, ents[-1][0]


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out_path = Path(args.datadir).parent / "m4i_mix.gcode"
    if out_path.exists():
        out_path.unlink()

    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model loaded: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"
        if not ok_model:
            return verdict(results)
        time.sleep(2.0)

        base = sidebar_entries(session)
        base_labels = [e[0] for e in base]
        print(f"{LOG} base entries: {base_labels}")
        results["seeded scheme present"] = (
            "PASS" if len(base_labels) >= 1 else "FAIL")

        # --- scheme A: Ratio 50/50 on a compatible pair ---
        ok_a, label_a = register_scheme(session, "Ratio", len(base_labels))
        print(f"{LOG} ratio scheme: ok={ok_a} label={label_a!r}")
        results["ratio scheme registers"] = (
            "PASS" if ok_a and label_a
            and LABEL_RATIO.match(label_a) else "FAIL")

        # --- scheme B: Gradient (compatible pair) ---
        ok_b, label_b = register_scheme(
            session, "Gradient", len(sidebar_entries(session)))
        print(f"{LOG} gradient scheme: ok={ok_b} label={label_b!r}")
        results["gradient scheme registers"] = (
            "PASS" if ok_b and label_b
            and LABEL_GRADIENT.match(label_b) else "FAIL")

        ents = [e[0] for e in sidebar_entries(session)]
        n_ratio = sum(1 for e in ents if LABEL_RATIO.match(e))
        results["both sidebar entries present"] = (
            "PASS" if (ok_a and ok_b and len(ents) == len(base_labels) + 2
                       and n_ratio >= 2
                       and any(LABEL_GRADIENT.match(e) for e in ents))
            else "FAIL")

        # --- slice the mixed project ---
        done = slice_and_wait(session, timeout_s=1500)
        print(f"{LOG} slicing done: {done}")
        results["mixed project slices"] = "PASS" if done else "FAIL"
        if not done:
            results["gcode exports non-empty"] = "FAIL"
            results["gcode mixing/tool-change markers"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- export + parse ---
        ok_exp, data = export_and_check(session, out_path)
        print(f"{LOG} export ok={ok_exp} bytes={len(data)}")
        results["gcode exports non-empty"] = (
            "PASS" if (ok_exp and len(data) > 0) else "FAIL")

        markers = {}
        for m in re.finditer(rb"^T(\d+)", data, re.M):
            markers[b"T" + m.group(1)] = markers.get(b"T" + m.group(1), 0) + 1
        distinct = len(markers)
        print(f"{LOG} tool-change markers: {sorted(markers.items())} "
              f"(distinct {distinct})")
        results["gcode >=2 distinct tool-change markers"] = (
            "PASS" if distinct >= 2 else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
