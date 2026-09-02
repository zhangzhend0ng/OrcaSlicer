#!/usr/bin/env python3
# diag_m6b_printer.py — recon for the m6b PRINTER-variant cascade flow.
# The U1 nozzle variants are NOT selectable in the printer combo popup
# (m4h measured: only the base machine + wizard entries) — the 0.4-nozzle
# context is produced the m4h way: a crafted copy of the standard fixture
# whose embedded project carries printer_settings_id 'Snapmaker U1
# (0.4 nozzle)' + printer_variant 0.4.
# Answers, with log + frame evidence:
#   1. printer combo + process preset combo texts after the crafted boot
#      (delete model + add Cube first, matching the m5/m6 case context);
#   2. the process preset POPUP rows under the 0.4 context: are the
#      'U1 (0.8 nozzle)' rows GONE (compatible_printers filter, PITFALLS
#      #2 positive) and 'U1 (0.4 nozzle)' rows present?
#   3. the gcode echoes: nozzle_diameter 0.4 + min/max_layer_height
#      0.08/0.32 (vs 0.16/0.56 on the standard fixture);

import ctypes
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import gcode_check  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import winutil  # noqa: E402
from harness import process_panel as pp  # noqa: E402
import numpy as np  # noqa: E402

from m5_common import boot_cube_session  # noqa: E402
from m3_common import (MIXED_3MF, add_common_args, boot_session,  # noqa: E402
                       export_and_check, slice_and_wait, verdict)
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m4h_mixing_templates import craft_04_fixture, find_printer_combo  # noqa: E402

LOG = "[diag_m6b]"
ART = HERE / "artifacts"
user32 = ctypes.WinDLL("user32")


def combo_text(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    return buf.value


def preset_popup_rows(session, log=LOG):
    """Open the process preset combo, OCR the popup rows (psm 6). Returns
    the joined row list or [] (popup did not open)."""
    r, ch, txt = pp.find_process_preset_combo(session)
    if not ch:
        print(f"{log} no process preset combo")
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
        print(f"{log} preset popup did not open")
        return []
    time.sleep(0.8)
    w, hgt, bgra = winutil.capture_window(ph)
    img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
    try:
        cv2.imwrite(str(ART / "diag_m6b_popup.png"), img[:, :, ::-1])
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
    return [" ".join(ws) for ws, _yc in rows]


def slice_echoes(session, tag, datadir):
    sliced = slice_and_wait(session, timeout_s=900)
    out_path = ART / f"diag_m6b_{tag}.gcode"
    if out_path.exists():
        out_path.unlink()
    ok_exp, data = export_and_check(session, out_path)
    nozzle = gcode_check.config_value(data, "nozzle_diameter") if ok_exp else None
    mn = gcode_check.config_value(data, "min_layer_height") if ok_exp else None
    mx = gcode_check.config_value(data, "max_layer_height") if ok_exp else None
    lh = gcode_check.config_value(data, "layer_height") if ok_exp else None
    print(f"{LOG} [{tag}] slice={sliced} export={ok_exp} nozzle={nozzle!r} "
          f"min={mn!r} max={mx!r} layer_height={lh!r}")
    return ok_exp and sliced


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    crafted = ART / "m6b_fixture_04.3mf"
    craft_04_fixture(crafted)

    # --- Phase A: crafted 0.4-nozzle context ---
    session = boot_session(args, model=crafted)
    try:
        pp.relocate_wizard(session, log=LOG)
        ok_model, _frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} crafted fixture loaded: {ok_model}")
        if not ok_model:
            return 1
        ok_del = __import__("m5_common").delete_all_models(session)
        from harness import add_shape
        ok_add = add_shape.add_primitive(session, "Cube")
        print(f"{LOG} delete={ok_del} cube={ok_add}")
        if not (ok_del and ok_add):
            return 1

        pr = find_printer_combo(session)
        print(f"{LOG} printer combo: {pr and (pr[0], combo_text(pr[2]))}")
        _r, _ch, ptxt = pp.find_process_preset_combo(session)
        print(f"{LOG} process preset combo: {ptxt!r}")

        rows = preset_popup_rows(session)
        hits_08 = [t for t in rows if "0.8" in t]
        hits_04 = [t for t in rows if "0.4" in t]
        print(f"{LOG} popup rows with 0.8: {hits_08[:6]}")
        print(f"{LOG} popup rows with 0.4: {hits_04[:6]}")
        print(f"{LOG} all rows ({len(rows)}): {rows[:24]}")

        slice_echoes(session, "a04", args.datadir)
        print(f"{LOG} alive={session.alive()}")
    finally:
        session.close()
        time.sleep(3.0)
        print(f"{LOG} phase A closed")

    # --- Phase B: standard 0.8-nozzle context (contrast) ---
    session, ok_cube = boot_cube_session(args)
    try:
        print(f"{LOG} phase B cube: {ok_cube}")
        if not ok_cube:
            return 1
        pr = find_printer_combo(session)
        print(f"{LOG} printer combo: {pr and (pr[0], combo_text(pr[2]))}")
        _r, _ch, ptxt = pp.find_process_preset_combo(session)
        print(f"{LOG} process preset combo: {ptxt!r}")
        slice_echoes(session, "b08", args.datadir)
        print(f"{LOG} alive={session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
