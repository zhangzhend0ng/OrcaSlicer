#!/usr/bin/env python3
# m3d_param_reslice.py — P0-1: parameter change -> reslice -> different gcode.
#
# White-box ref: wx_gui_business_tests.cpp:238 (infill density change ->
# different gcode). Black-box uses the LAYER HEIGHT field instead — it is
# the first visible settings field (no panel scrolling needed) and a layer
# height change ripples through the whole gcode, giving a strong file diff.
# The assertion is the same shape: exported gcode A != exported gcode B and
# the "; layer_height" header actually moved.
#
# Black-box path: slice -> export A -> click the Layer height Edit ->
# overwrite with a different value -> reslice -> export B -> compare.
# "Export becomes available" is the deterministic completion signal
# (can_export_gcode) — no completion templates needed here.

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import export_util, winutil  # noqa: E402
from m2_slice_chain import click_slice_start, wait_slicing_done  # noqa: E402
from m3_common import (MIXED_3MF, RESOURCE, add_common_args,  # noqa: E402
                       boot_session, export_and_check, slice_and_wait, verdict)


def find_layer_height_edit(hwnd: int):
    """The native Edit holding the layer-height VALUE.

    Layout: the 'Layer height' label (screen y~844) is followed by a unit
    row 'mm' (y~872) whose inner Edit carries the value ('0.4' here). The
    label row itself also hosts empty placeholder Edits — match the Edit
    INTERSECTING the 'mm' unit control, not the label."""
    import ctypes
    user32 = ctypes.WinDLL("user32")
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.c_void_p)
    mm_rect = None
    for text, rect, ch in export_util._children_texts(hwnd):
        if text.strip() == "mm" and 800 <= rect[1] <= 950:
            mm_rect = rect
            break
    if mm_rect is None:
        return None
    for text, rect, ch in export_util._children_texts(hwnd):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(ch, cls, 64)
        if cls.value != "Edit":
            continue
        # rects overlap?
        if (rect[0] < mm_rect[2] and rect[2] > mm_rect[0]
                and rect[1] < mm_rect[3] and rect[3] > mm_rect[1]):
            return ch
    return None


def gcode_layer_height(data: bytes):
    m = re.search(rb"; layer_height = ([0-9.]+)", data)
    return m.group(1).decode() if m else None


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out_a = Path(args.datadir).parent / "m3d_a.gcode"
    out_b = Path(args.datadir).parent / "m3d_b.gcode"
    for p in (out_a, out_b):
        if p.exists():
            p.unlink()

    session = boot_session(args, model=args.model)
    try:
        # --- slice once, export baseline A ---
        ok_slice = slice_and_wait(session, timeout_s=1500)
        ok_a, data_a = export_and_check(session, out_a)
        lh_a = gcode_layer_height(data_a)
        print(f"[m3d] slice={ok_slice} exportA={ok_a} size={len(data_a)} "
              f"layer_height={lh_a}")
        results["baseline slice + export"] = "PASS" if (ok_slice and ok_a) else "FAIL"

        # --- edit the layer height field ---
        edit = find_layer_height_edit(session.hwnd)
        print(f"[m3d] layer height Edit: {hex(edit) if edit else None}")
        if not edit:
            results["layer height edit"] = "FAIL (Edit not found)"
            return verdict(results)
        # pick a different value: 0.2 <-> 0.3
        new_lh = "0.3" if (lh_a and float(lh_a) < 0.25) else "0.2"
        # WM_SETTEXT sets the value directly — Ctrl+A + WM_CHAR depends on
        # the Edit holding Windows focus, which SendMessage clicks do not
        # transfer after a modal export dialog; WM_SETTEXT fires EN_CHANGE
        # and commits through the same wx path.
        import ctypes
        user32 = ctypes.WinDLL("user32")
        user32.SendMessageW(edit, 0x000C, 0, new_lh)  # WM_SETTEXT
        winutil.press_enter(edit)  # commit
        time.sleep(2.0)
        # read back the Edit content to prove the value actually landed
        n = user32.SendMessageW(edit, 0x000E, 0, 0)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.SendMessageW(edit, 0x000D, n + 1, buf)
        print(f"[m3d] layer height Edit now: {buf.value!r} (wanted {new_lh!r})")
        results["layer height edit"] = (
            "PASS" if buf.value.strip() == new_lh else "FAIL")

        # --- reslice: parameter change invalidates the slice result, so the
        # button returns to idle (manual reslice) OR the app auto-resliced
        # (button already done). Poll for whichever settles. ---
        from m1_minimal_loop import match, capture_bgr
        import cv2
        tpl_idle = str(RESOURCE / "slice_plate_button.png")
        idle_score, done_score = 0.0, 0.0
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            img = capture_bgr(session)
            idle_score, *_ = match(img, tpl_idle)
            done_score, *_ = match(img, str(RESOURCE / "slice_button_done.png"))
            if idle_score >= 0.9 or done_score >= 0.9:
                break
            time.sleep(1.0)
        print(f"[m3d] after edit: idle={idle_score:.3f} done={done_score:.3f}")
        ok_slice2 = False
        if idle_score >= 0.9:
            ok_slice2 = slice_and_wait(session, timeout_s=1500)
        elif done_score >= 0.9:
            ok_slice2 = True  # auto-resliced by the app
        ok_b, data_b = export_and_check(session, out_b)
        lh_b = gcode_layer_height(data_b)
        print(f"[m3d] reslice={ok_slice2} exportB={ok_b} size={len(data_b)} "
              f"layer_height={lh_b}")
        results["reslice after param change"] = (
            "PASS" if ok_slice2 and ok_b else "FAIL")

        same = (data_a == data_b)
        print(f"[m3d] gcode identical: {same} "
              f"(A {len(data_a)}B / B {len(data_b)}B)")
        results["gcode differs after param change"] = (
            "PASS" if not same else "FAIL")
        results["layer height header moved"] = (
            "PASS" if (lh_a and lh_b and lh_a != lh_b) else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3d] app closed")


def _edit_center(session, edit_hwnd: int):
    import ctypes
    user32 = ctypes.WinDLL("user32")
    rc = ctypes.wintypes.RECT()
    user32.GetWindowRect(edit_hwnd, ctypes.byref(rc))
    return (rc.left + rc.right) // 2, (rc.top + rc.bottom) // 2


if __name__ == "__main__":
    raise SystemExit(main())
