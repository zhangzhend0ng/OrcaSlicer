#!/usr/bin/env python3
# m3e_preset_switch.py — P0-2: print-preset switch -> gcode header follows.
#
# White-box ref: wx_gui_business_tests.cpp:304 — switching the print preset
# (combo path) and reslicing moves "; layer_height" with the new preset
# (0.40 Standard <-> 0.24 Standard @Snapmaker U1 (0.8 nozzle)).
#
# Black-box path: slice + export A -> click the print-preset selector (the
# '0.40 Standard @Snapmaker U1 (0.8 nozzle)' wxWindowNR, screen y~765) ->
# its SidePopup lists the U1 print presets -> click the '0.24 ...' row
# (popup rows are a SEPARATE top-level: click WITHOUT root piercing) ->
# reslice (button returns to idle on preset change, or the app auto-slices)
# -> export B -> assert "; layer_height" moved to 0.24.
#
# This is also the black-box cover for the "parameter change -> reslice ->
# different artifact" assertion family (P0-1's field-edit path needs real
# keyboard focus, which SendMessage injection cannot transfer).

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import export_util, winutil  # noqa: E402
from m1_minimal_loop import match, capture_bgr  # noqa: E402
from m3_common import (MIXED_3MF, RESOURCE, add_common_args,  # noqa: E402
                       boot_session, export_and_check, verdict)


def find_preset_combo(hwnd: int):
    """The print-preset selector: the wxWindowNR whose text contains
    'Standard @Snapmaker U1' in the settings panel (screen y 740-800)."""
    for text, rect, ch in export_util._children_texts(hwnd):
        if "Standard @Snapmaker U1" in text and 740 <= rect[1] <= 810:
            return rect, ch
    return None, None


def switch_preset(session, target: str) -> bool:
    """Open the preset combo, click the row containing `target`.

    The preset list rows are SELF-DRAWN (no child HWNDs — enumeration
    yields nothing), so rows are probed by coordinate: the popup lists U1
    print presets at a measured 28px pitch starting popup_top+14, and every
    click selects and closes the popup. After each click the combo text is
    read back; the loop reopens the popup until the target row is hit."""
    import ctypes
    user32 = ctypes.WinDLL("user32")
    rect, ch = find_preset_combo(session.hwnd)
    if not rect:
        return False
    txt = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(ch, txt, 256)
    if target in txt.value:
        return True  # already selected
    combo_cx = (rect[0] + rect[2]) // 2
    combo_cy = (rect[1] + rect[3]) // 2
    for attempt in range(6):
        winutil.msg_click_screen(combo_cx, combo_cy, session.hwnd)
        popup = export_util.wait_popup(session.pid, timeout_s=4.0)
        if not popup:
            return False
        pr = popup[2]
        px = (pr[0] + pr[2]) // 2
        py = pr[1] + 14 + attempt * 28
        winutil.msg_click_screen(px, py)  # popup is top-level: no root
        time.sleep(0.8)
        user32.GetWindowTextW(ch, txt, 256)
        if target in txt.value:
            return True
        # popup closed by the selection; retry the next row
    return False


def gcode_layer_height(data: bytes):
    m = re.search(rb"; layer_height = ([0-9.]+)", data)
    return m.group(1).decode() if m else None


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out_a = Path(args.datadir).parent / "m3e_a.gcode"
    out_b = Path(args.datadir).parent / "m3e_b.gcode"
    for p in (out_a, out_b):
        if p.exists():
            p.unlink()

    session = boot_session(args, model=args.model)
    try:
        # --- slice once, export baseline A ---
        from m3_common import slice_and_wait
        ok_slice = slice_and_wait(session, timeout_s=1500)
        ok_a, data_a = export_and_check(session, out_a)
        lh_a = gcode_layer_height(data_a)
        print(f"[m3e] slice={ok_slice} exportA={ok_a} layer_height={lh_a}")
        results["baseline slice + export"] = "PASS" if (ok_slice and ok_a) else "FAIL"

        # --- switch print preset 0.40 -> 0.24 ---
        target = ("0.24 Standard @Snapmaker U1 (0.8 nozzle)"
                  if lh_a and "0.24" not in lh_a
                  else "0.40 Standard @Snapmaker U1 (0.8 nozzle)")
        switched = switch_preset(session, target)
        print(f"[m3e] preset switch to '{target}': {switched}")
        results["preset combo switch"] = "PASS" if switched else "FAIL"
        time.sleep(2.0)

        # --- reslice (button returns idle on preset change / auto-slice) ---
        from m3_common import slice_and_wait
        ok_slice2 = slice_and_wait(session, timeout_s=1500)
        ok_b, data_b = export_and_check(session, out_b)
        lh_b = gcode_layer_height(data_b)
        print(f"[m3e] reslice={ok_slice2} exportB={ok_b} layer_height={lh_b}")
        results["reslice after preset switch"] = (
            "PASS" if ok_slice2 and ok_b else "FAIL")

        same = (data_a == data_b)
        print(f"[m3e] gcode identical: {same}")
        results["gcode differs after preset switch"] = (
            "PASS" if not same else "FAIL")
        target_short = target.split(" Standard")[0]  # e.g. '0.24'
        results["header follows new preset"] = (
            "PASS" if (lh_b and target_short in lh_b) else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3e] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
