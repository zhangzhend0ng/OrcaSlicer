#!/usr/bin/env python3
# diag_m6a_filament.py — recon for the m6a FILAMENT-PRESET switch flow.
# Answers, with log + frame evidence:
#   1. what the sidebar filament material combos report (texts/rects) and
#      whether slot 1 = 'Generic PETG' / slots 2-5 = 'Snapmaker PLA Silk';
#   2. what the combo POPUP lists for the U1 (0.8) context and whether
#      WHEEL-SCANNING it (alphabetical, Snapmaker rows far down) reaches
#      'Snapmaker PLA Silk' / 'Generic PETG' rows and a real click commits
#      (combo text updates);
#   3. whether the Color Mixing entries survive the switch (count);
#   4. what the gcode '; filament_type' / '; filament_settings_id' echoes
#      look like after switching slot 1 -> PLA silk and slot 2 -> PETG.
#
# MEASURED round 1: the popup OCRs with psm 6; rows list ALL vendors
# alphabetically (AliZ ... Bambu ... Generic ... Snapmaker) — 'Snapmaker
# PLA Silk' is NOT in the initial viewport; picking a visible row by word
# works ('AliZ PETG' committed and the combo text updated); the gcode
# echoes '; filament_type = PETG;PETG;PLA;PLA;PLA' (semicolon list,
# per-physical-slot) and '; filament_settings_id = "...";...' with the
# FULL preset names; mixing entries survive.

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
                       slice_and_wait)

LOG = "[diag_m6a]"
ART = HERE / "artifacts"
user32 = ctypes.WinDLL("user32")
notch_tag = [0]


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


def popup_rows(session, popup_hwnd, popup_rect, tag=""):
    """OCR the popup (psm 6) and group words into ROWS (y +-5px).
    Returns [(joined_text, y_center_screen, x_left_screen)]."""
    import numpy as np
    w, hgt, bgra = winutil.capture_window(popup_hwnd)
    img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
    try:
        cv2.imwrite(str(ART / f"diag_m6a_popup_{tag}.png"), img[:, :, ::-1])
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
    """Wheel-scan the popup (down first, then up) for a row whose joined
    text contains ALL of want_words; real-click it. Returns True on a
    click."""
    seen = set()
    for direction in (1, 1, -1):
        for _burst in range(6):
            rows = popup_rows(session, ph, pr, tag=str(notch_tag[0]))
            notch_tag[0] += 1
            print(f"{LOG} popup rows: {' | '.join(t for t, *_ in rows)[:300]!r}")
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
    row matching want_words, click it, verify the combo text reads
    `want_text`. Returns (ok, text)."""
    combos = mdu.filament_material_combos(session)
    if len(combos) <= combo_idx:
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
    notch_tag[0] = 0
    clicked = pick_named_row(session, ph, pop, want_words)
    time.sleep(1.5)
    txt = combo_text(h)
    print(f"{LOG} slot {combo_idx} -> {txt!r} (clicked={clicked})")
    return clicked and want_text.lower() in txt.lower(), txt


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    session, ok_cube = boot_cube_session(args)
    try:
        print(f"{LOG} cube: {ok_cube} alive={session.alive()}")
        if not ok_cube:
            return 1

        combos = mdu.filament_material_combos(session)
        print(f"{LOG} initial combos: {[(t, r[0], r[1]) for t, r, _h in combos]}")
        mixing_before = [t for t, _r, _h in mdu.mix_entry_labels(session)]
        print(f"{LOG} mixing entries before: {mixing_before}")

        ok1, txt1 = switch_slot(session, 0, ("pla", "silk"),
                                "Snapmaker PLA Silk")
        time.sleep(3.0)
        ok2, txt2 = switch_slot(session, 1, ("generic", "petg"),
                                "Generic PETG")
        time.sleep(3.0)

        mixing_after = [t for t, _r, _h in mdu.mix_entry_labels(session)]
        print(f"{LOG} mixing entries after: {mixing_after}")
        print(f"{LOG} switches: slot0={ok1} ({txt1!r}) slot1={ok2} ({txt2!r})")

        sliced = slice_and_wait(session, timeout_s=900)
        out_path = ART / "diag_m6a.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        ft = gcode_check.config_value_all(data, "filament_type") if ok_exp else []
        fid = gcode_check.config_value(data, "filament_settings_id") if ok_exp else None
        print(f"{LOG} slice={sliced} export={ok_exp} "
              f"filament_type echoes={ft} settings_id={fid!r}")
        print(f"{LOG} alive={session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
