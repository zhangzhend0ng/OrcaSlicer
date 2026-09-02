#!/usr/bin/env python3
# m6a_filaments.py — FILAMENT-PRESET switch main flow: switch the sidebar
# material combo of physical slot 1 ('Generic PETG') to 'Snapmaker PLA
# Silk' and slot 2 ('Snapmaker PLA Silk') to 'Generic PETG', slice once,
# and prove both presets reached the slicer via the gcode echoes.
#
# White-box refs:
#   - Plater.cpp:705-721 — the sidebar material combos read
#     preset_bundle->filament_presets per slot (base names, no '@').
#   - resources/profiles/Snapmaker/Filament/ — 'Snapmaker PLA Silk' has
#     filament_type ["PLA"], 'Generic PETG' ["PETG"].
#   - GCode.cpp:2270-2275 — the header echoes '; filament_type' as a
#     ';'-joined per-extruder list; append_full_config also echoes
#     '; filament_settings_id' with the FULL preset names — the strongest
#     per-slot evidence (measured: '"Generic PETG @U1 0.8 nozzle";
#     "AliZ PETG @System";...').
#
# MEASURED 09-02 (diag_m6a_filament, rounds 1-3):
#   - the combos are wxWindowNR children with REAL text, sorted
#     row-major: slot1 @ (38,410), slot2 @ (236,410) on the maximized
#     window (mdu.filament_material_combos);
#   - the combo popup is a wxWindowNR 'panel' top-level listing ALL
#     vendors alphabetically (AliZ, Bambu, ..., FDplast, Fiberon,
#     Generic, ..., Snapmaker) — 'Snapmaker PLA Silk' needs WHEEL-DOWN
#     scans (m5g mechanic; popup row OCR with psm 6, rows grouped by
#     y +-5px, 28px pitch);
#   - row matching MUST key the vendor ('snapmaker'+'pla'+'silk'):
#     ('pla','silk') alone clicks 'Bambu PLA Silk' (measured round 3 —
#     and its gcode chain still proved the echo mechanics);
#   - the Color Mixing entries survive a material switch ('F3 50%+F2
#     50%' before == after);
#   - the '; filament_type' echo is semicolon-joined per physical slot:
#     baseline PETG;PETG;PLA;PLA;PLA -> PLA;PETG;PLA;PLA;PLA after the
#     two switches.
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> slot1 -> Snapmaker
# PLA Silk (popup scan) + slot2 -> Generic PETG -> combo texts read back ->
# mixing entry preserved -> slice + export -> '; filament_type = PLA;PETG;
# PLA;PLA;PLA' and filament_settings_id[0] starts 'Snapmaker PLA Silk' /
# [1] starts 'Generic PETG' -> app alive.
# Stale-table notes: none (filament preset switching was previously
# untested; m3a's preset switch covered the PROCESS preset only).

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
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (add_common_args, export_and_check,  # noqa: E402
                       slice_and_wait, verdict)

LOG = "[m6a]"
ART = HERE / "artifacts"
user32 = ctypes.WinDLL("user32")


def popup_panel_hw(session, known):
    """(rect, hwnd) of the first NEW 'panel' top-level after `known`."""
    from harness import mixing_util
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "wxWindowNR" and txt == "panel" and h not in known:
                return r, h
        time.sleep(0.15)
    return None, None


def popup_rows(session, popup_hwnd, popup_rect):
    """OCR the popup (psm 6 — the '-----' section art kills psm 3) and
    group words into rows (y +-5px). Returns [(joined_text, y_center,
    x_left)] in SCREEN coords."""
    import numpy as np
    w, hgt, bgra = winutil.capture_window(popup_hwnd)
    img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
    try:
        cv2.imwrite(str(ART / "m6a_popup.png"), img[:, :, ::-1])
    except Exception:
        pass
    words = mdu.ocr_words_img(img, scale=3, psm=6)
    rows = []
    for t, x, y, ww, wh in sorted(words, key=lambda wi: (wi[2], wi[1])):
        yc = popup_rect[1] + y + wh // 2
        for row in rows:
            if abs(row[1] - yc) <= 5:
                row[0].append(t)
                row[1] = (row[1] + yc) // 2
                break
        else:
            rows.append([[t], yc, popup_rect[0] + x])
    return [(" ".join(ws), yc, xl) for ws, yc, xl in rows]


def wheel_popup(session, popup_rect, notches_down):
    px = (popup_rect[0] + popup_rect[2]) // 2
    py = (popup_rect[1] + popup_rect[3]) // 2
    winutil.user32.SetCursorPos(px, py)
    time.sleep(0.2)
    ev = winutil._INPUT()
    ev.type = 0
    ev.value.mouseData = ((-120 if notches_down > 0 else 120) & 0xFFFFFFFF)
    ev.value.dwFlags = 0x0800  # MOUSEEVENTF_WHEEL
    for _ in range(abs(notches_down)):
        user32.SendInput(1, ctypes.byref(ev), ctypes.sizeof(winutil._INPUT))
        time.sleep(0.12)
    time.sleep(0.8)


def pick_named_row(session, ph, pr, want_words):
    """Wheel-scan the popup (down first, then back up) for a row whose
    joined text contains ALL of want_words; real-click it. Returns True
    on a click."""
    seen = set()
    for direction in (1, 1, -1):
        for _burst in range(6):
            rows = popup_rows(session, ph, pr)
            print(f"{LOG} popup rows: "
                  f"{' | '.join(t for t, *_ in rows)[:300]!r}")
            for text, yc, xl in rows:
                low = text.lower()
                if all(wd in low for wd in want_words) and low not in seen:
                    print(f"{LOG} picking row {text!r} at y={yc}")
                    winutil.user32.SetCursorPos(xl + 12, yc)
                    time.sleep(0.2)
                    winutil.real_click_screen(xl + 12, yc)
                    time.sleep(1.2)
                    return True
            seen |= {t.lower() for t, _y, _x in rows}
            wheel_popup(session, pr, 5 * direction)
    return False


def combo_text(h):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    return buf.value


def switch_slot(session, combo_idx, want_words, want_text):
    """Open the material combo `combo_idx`, wheel-scan the popup for the
    named row, click it, verify the combo text. Returns (ok, text)."""
    combos = mdu.filament_material_combos(session)
    if len(combos) <= combo_idx:
        print(f"{LOG} slot {combo_idx}: no combo (have {len(combos)})")
        return False, None
    _t, r, h = combos[combo_idx]
    known = mdu.toplevel_snapshot(session)
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    winutil.user32.SetCursorPos(cx, cy)
    time.sleep(0.2)
    winutil.real_click_screen(cx, cy)
    pop, ph = popup_panel_hw(session, known)
    print(f"{LOG} popup: {pop}")
    if not pop:
        mdu.popup_cancel(session)
        return False, None
    time.sleep(0.8)
    clicked = pick_named_row(session, ph, pop, want_words)
    time.sleep(1.5)
    txt = combo_text(h)
    print(f"{LOG} slot {combo_idx + 1} -> {txt!r} (clicked={clicked})")
    return clicked and want_text.lower() in txt.lower(), txt


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    results = {}
    session, ok_cube = boot_cube_session(args)
    try:
        results["fixture deleted + standard model added"] = (
            "PASS" if ok_cube else "FAIL")
        if not ok_cube:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        combos = mdu.filament_material_combos(session)
        print(f"{LOG} initial combos: "
              f"{[t for t, _r, _h in combos]}")
        mixing_before = [t for t, _r, _h in mdu.mix_entry_labels(session)]
        results["five material combos visible"] = (
            "PASS" if len(combos) == 5 else "FAIL")

        # slot 1: Generic PETG -> Snapmaker PLA Silk
        ok1, txt1 = switch_slot(session, 0, ("snapmaker", "pla", "silk"),
                                "Snapmaker PLA Silk")
        time.sleep(3.0)
        results["slot 1 -> Snapmaker PLA Silk"] = (
            "PASS" if ok1 else "FAIL")
        # slot 2: Snapmaker PLA Silk -> Generic PETG
        ok2, txt2 = switch_slot(session, 1, ("generic", "petg"),
                                "Generic PETG")
        time.sleep(3.0)
        results["slot 2 -> Generic PETG"] = (
            "PASS" if ok2 else "FAIL")

        mixing_after = [t for t, _r, _h in mdu.mix_entry_labels(session)]
        print(f"{LOG} mixing entries {mixing_before} -> {mixing_after}")
        results["mixing entries survive"] = (
            "PASS" if mixing_after == mixing_before and mixing_before
            else "FAIL")
        if not (ok1 and ok2):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- slice once; the echoes carry the per-slot evidence ---
        sliced = slice_and_wait(session, timeout_s=900)
        out_path = Path(args.datadir).parent / "m6a_filaments.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        ft = gcode_check.config_value(data, "filament_type") if ok_exp else None
        fid = gcode_check.config_value(data, "filament_settings_id") \
            if ok_exp else None
        print(f"{LOG} slice={sliced} export={ok_exp} "
              f"filament_type={ft!r} settings_id={fid!r}")
        results["slice + export"] = (
            "PASS" if (sliced and ok_exp) else "FAIL")
        results["gcode filament_type PLA;PETG;PLA;PLA;PLA"] = (
            "PASS" if ft and ft.replace(" ", "").lower()
            == "pla;petg;pla;pla;pla" else "FAIL")
        id0 = fid.split(";")[0] if fid else ""
        id1 = fid.split(";")[1] if fid and ";" in fid else ""
        results["settings_id[0] is Snapmaker PLA Silk"] = (
            "PASS" if id0.strip().strip('"').startswith(
                "Snapmaker PLA Silk") else "FAIL")
        results["settings_id[1] is Generic PETG"] = (
            "PASS" if id1.strip().strip('"').startswith(
                "Generic PETG") else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
