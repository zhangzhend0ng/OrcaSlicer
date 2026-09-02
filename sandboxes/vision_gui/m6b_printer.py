#!/usr/bin/env python3
# m6b_printer.py — PRINTER-VARIANT cascade main flow: boot the crafted
# 0.4-nozzle variant of the standard fixture (m4h's crafting: nozzle
# variants are NOT selectable in the printer combo popup — PresetComboBoxes
# hides them), slice, then contrast against the standard 0.8-nozzle
# fixture. Proves the compatible_printers filter and that the nozzle +
# layer-height bounds follow the MACHINE preset.
#
# White-box refs:
#   - PresetComboBoxes.cpp:1325-1329 — printer presets that are not
#     visible/compatible are dropped from the combo popup (m4h measured:
#     only the base machine + wizard entries).
#   - Pitfalls #2 positive use: process presets are filtered by
#     compatible_printers — under the 0.4-nozzle context the popup lists
#     ONLY 'U1 (0.4 nozzle)' rows (measured 09-02: zero '0.8' rows).
#   - resources/profiles/Snapmaker/Machine/ — 'Snapmaker U1 (0.8 nozzle)'
#     carries min/max_layer_height 0.16/0.56, 'U1 (0.4 nozzle)'
#     0.08/0.32; GCode.cpp:6638 append_full_config echoes
#     '; min_layer_height' / '; nozzle_diameter' from the full config.
#
# MEASURED 09-02 (diag_m6b_printer):
#   - crafted boot: process combo auto-selects the embedded
#     '0.20 Standard @Snapmaker U1 (0.4 nozzle)'; the printer combo reads
#     the BASE name 'Snapmaker U1' (no variant suffix);
#   - the process popup OCR scrambles word order per row (row grouping)
#     — filter checks must be SUBSTRING over the joined rows;
#   - echoes A04: nozzle 0.4 / min 0.08 / max 0.32 / layer_height 0.2;
#     B08: nozzle 0.8 / min 0.16 / max 0.56 / layer_height 0.4.
#
# Black-box path: craft 0.4 fixture -> boot -> delete + Cube -> process
# combo contains '(0.4 nozzle)' -> preset popup: no '0.8' rows, '>=3'
# '0.4' rows -> slice + export (nozzle 0.4, min 0.08) -> RESTART standard
# fixture -> delete + Cube -> process combo contains '(0.8 nozzle)' ->
# slice + export (nozzle 0.8, min 0.16) -> app alive.
# Stale-table notes: none (printer-variant context was previously
# produced only inside m4h's mixing flow, without echo asserts).

import ctypes
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import add_shape  # noqa: E402
from harness import gcode_check  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from harness import winutil  # noqa: E402
import numpy as np  # noqa: E402

import m5_common  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (MIXED_3MF, add_common_args, boot_session,  # noqa: E402
                       export_and_check, slice_and_wait, verdict)
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m4h_mixing_templates import craft_04_fixture, find_printer_combo  # noqa: E402

LOG = "[m6b]"
user32 = ctypes.WinDLL("user32")


def combo_text(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    return buf.value


def preset_popup_rows(session):
    """Open the process preset combo, OCR the popup rows (psm 6; the
    '-----' art kills psm 3), close it. Returns the joined row texts —
    word order within a row may be scrambled (measured)."""
    r, ch, _txt = pp.find_process_preset_combo(session)
    if not ch:
        return []
    known = mdu.toplevel_snapshot(session)
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    winutil.msg_click_screen(cx, cy, session.hwnd)
    pop, ph = None, None
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline and not pop:
        time.sleep(0.2)
        for cls, ptxt, pr, h in mdu.mixing_util.toplevel(session.pid):
            if cls == "wxWindowNR" and ptxt == "panel" and h not in known:
                pop, ph = pr, h
    if not pop:
        print(f"{LOG} preset popup did not open")
        mdu.popup_cancel(session)
        return []
    time.sleep(0.8)
    w, hgt, bgra = winutil.capture_window(ph)
    img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
    try:
        cv2.imwrite(str(HERE / "artifacts" / "m6b_popup.png"), img[:, :, ::-1])
    except Exception:
        pass
    words = mdu.ocr_words_img(img, scale=3, psm=6)
    rows = []
    for t, x, y, ww, wh in sorted(words, key=lambda wi: (wi[2], wi[1])):
        yc = pop[1] + y + wh // 2
        for row in rows:
            if abs(row[1] - yc) <= 5:
                row[0].append(t)
                break
        else:
            rows.append([[t], yc])
    mdu.popup_cancel(session)
    time.sleep(1.0)
    return [" ".join(ws) for ws, _yc in rows]


def boot_prepare_cube(args, model):
    """Boot `model`, delete the loaded fixture model, add the standard
    Cube. Returns session or None."""
    session = boot_session(args, model=model)
    pp.relocate_wizard(session, log=LOG)
    ok_model, _frac = wait_model_loaded(session, timeout_s=240)
    ok_del = m5_common.delete_all_models(session) if ok_model else False
    ok_add = add_shape.add_primitive(session, "Cube") if ok_del else False
    print(f"{LOG} boot {Path(model).name}: loaded={ok_model} "
          f"deleted={ok_del} cube={ok_add}")
    if not (ok_model and ok_del and ok_add):
        session.close()
        return None
    return session


def slice_export_echoes(session, tag, datadir):
    """Slice once, export, pull the machine-dependent echoes."""
    sliced = slice_and_wait(session, timeout_s=900)
    out_path = Path(datadir).parent / f"m6b_{tag}.gcode"
    if out_path.exists():
        out_path.unlink()
    ok_exp, data = export_and_check(session, out_path)
    vals = {k: gcode_check.config_value(data, k) if ok_exp else None
            for k in ("nozzle_diameter", "min_layer_height",
                      "max_layer_height", "layer_height")}
    print(f"{LOG} [{tag}] slice={sliced} export={ok_exp} {vals}")
    return sliced and ok_exp, vals


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()
    results = {}

    crafted = HERE / "artifacts" / "m6b_fixture_04.3mf"
    craft_04_fixture(crafted)

    # --- Phase A: 0.4-nozzle variant context ---
    session = boot_prepare_cube(args, crafted)
    try:
        if not session:
            results["A: crafted fixture boot + cube"] = "FAIL"
            return verdict(results)
        results["A: crafted fixture boot + cube"] = "PASS"
        pr = find_printer_combo(session)
        ptxt = combo_text(pr[2]) if pr else ""
        print(f"{LOG} printer combo: {ptxt!r}")
        results["A: printer combo is base Snapmaker U1"] = (
            "PASS" if "Snapmaker U1" in ptxt else "FAIL")
        _r, _ch, combo = pp.find_process_preset_combo(session)
        print(f"{LOG} A process preset combo: {combo!r}")
        results["A: process preset is a 0.4-nozzle one"] = (
            "PASS" if combo and "0.4" in combo else "FAIL")

        rows = preset_popup_rows(session)
        n08 = sum(1 for t in rows if "0.8" in t)
        n04 = sum(1 for t in rows if "0.4" in t)
        print(f"{LOG} popup rows: {len(rows)} with'0.8'={n08} "
              f"with'0.4'={n04}")
        results["A: preset popup filters 0.8 rows out"] = (
            "PASS" if rows and n08 == 0 and n04 >= 3 else "FAIL")

        ok_a, vals = slice_export_echoes(session, "a04", args.datadir)
        results["A: slice + export"] = "PASS" if ok_a else "FAIL"
        results["A: nozzle echo 0.4"] = (
            "PASS" if vals["nozzle_diameter"] and
            vals["nozzle_diameter"].startswith("0.4") else "FAIL")
        results["A: min layer height echo 0.08"] = (
            "PASS" if vals["min_layer_height"] and
            vals["min_layer_height"].startswith("0.08") else "FAIL")
        results["A: max layer height echo 0.32"] = (
            "PASS" if vals["max_layer_height"] and
            vals["max_layer_height"].startswith("0.32") else "FAIL")
    finally:
        if session:
            session.close()
            print(f"{LOG} phase A closed")
    time.sleep(3.0)

    # --- Phase B: standard 0.8-nozzle context (contrast / restore) ---
    session = boot_prepare_cube(args, MIXED_3MF)
    try:
        if not session:
            results["B: standard fixture boot + cube"] = "FAIL"
            return verdict(results)
        results["B: standard fixture boot + cube"] = "PASS"
        _r, _ch, combo = pp.find_process_preset_combo(session)
        print(f"{LOG} B process preset combo: {combo!r}")
        results["B: process preset is the 0.8-nozzle one"] = (
            "PASS" if combo and "0.8" in combo else "FAIL")
        ok_b, vals = slice_export_echoes(session, "b08", args.datadir)
        results["B: slice + export"] = "PASS" if ok_b else "FAIL"
        results["B: nozzle echo 0.8"] = (
            "PASS" if vals["nozzle_diameter"] and
            vals["nozzle_diameter"].startswith("0.8") else "FAIL")
        results["B: min layer height echo 0.16"] = (
            "PASS" if vals["min_layer_height"] and
            vals["min_layer_height"].startswith("0.16") else "FAIL")
        results["B: max layer height echo 0.56"] = (
            "PASS" if vals["max_layer_height"] and
            vals["max_layer_height"].startswith("0.56") else "FAIL")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        if session:
            session.close()
            print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
