#!/usr/bin/env python3
# diag_m6c_discard.py — recon for the m6c DIRTY-PRESET switch confirm.
# Source facts (Tab.cpp:5511/5796, UnsavedChangesDialog.cpp): switching a
# preset while the current one is dirty pops the 'Transfer or discard
# changes' DPIDialog; buttons painted (m5g precedent: find by TEXT):
# 'Transfer' / 'Discard' / 'Save'; the action line reads 'Preset "X"
# contains the following unsaved changes:'. Cancel (close box) aborts the
# switch.
# Answers, with log + frame evidence:
#   1. does the dialog appear on switching 0.40 -> 0.24 after dirtying
#      layer height 0.3? (title + child texts + OCR body)
#   2. does 'Discard' commit the switch (combo text 0.24, field reloads
#      to the preset value)?
#   3. does closing the dialog (WM_CLOSE = cancel) abort (combo still the
#      old preset, dirty value retained)?

import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util  # noqa: E402
from harness import winutil  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import add_common_args  # noqa: E402

LOG = "[diag_m6c]"
ART = HERE / "artifacts"


def frame(session, name):
    img = __import__("m1_minimal_loop", fromlist=["capture_bgr"]) \
        .capture_bgr(session)
    cv2.imwrite(str(ART / f"diag_m6c_{name}.png"), img)
    return img


def top_dialogs(session, known):
    return [(h, txt) for cls, txt, r, h in mixing_util.toplevel(session.pid)
            if cls == "#32770" and h not in known]


def dialog_dump(session, dlg, tag):
    f = winutil.window_rect(session.hwnd)
    r = winutil.window_rect(dlg)
    print(f"{LOG} dialog rect: {r}")
    rows = []
    for t, c, hr, h in mixing_util.children(dlg):
        if t.strip() and user32_visible(h):
            rows.append((c, t.strip()[:60]))
    print(f"{LOG} children with text: {rows[:24]}")
    # OCR the dialog body for the painted action line
    w, hgt, bgra = winutil.capture_window(dlg)
    import numpy as np
    img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
    cv2.imwrite(str(ART / f"diag_m6c_{tag}.png"), img[:, :, ::-1])
    words = mdu.ocr_words_img(img, scale=3, psm=6)
    print(f"{LOG} body ocr: {' '.join(t for t, *_ in words)[:400]!r}")


def user32_visible(h):
    import ctypes
    return ctypes.WinDLL("user32").IsWindowVisible(h)


def click_dialog_text(session, dlg, text):
    """m5g mechanic: the dialog buttons are PAINTED wxWindowNR — find by
    exact text and real-click."""
    for t, c, r, h in mixing_util.children(dlg):
        if t.strip() == text and user32_visible(h):
            x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(x, y)
            time.sleep(0.2)
            winutil.real_click_screen(x, y)
            time.sleep(1.5)
            return True
    return False


def read_layer_height(session, tries=6):
    for _ in range(tries):
        eds = pp.float_edits_in_view(session)
        if eds:
            return eds[0][2]
        time.sleep(1.0)
    return None


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    session, ok_cube = boot_cube_session(args)
    try:
        print(f"{LOG} cube: {ok_cube} alive={session.alive()}")
        if not ok_cube:
            return 1

        # dirty the layer height (m5b mechanic)
        pp.ensure_advanced(session, want=True)
        tab_ok = pp.click_tab(session, "Quality", "height")
        hit = pp.wait_float_edit(session)
        ok_dirty = False
        if tab_ok and hit:
            r, h = hit[0], hit[1]
            new = pp.real_edit_set(session, r, h, "0.3")
            pp.neutralize_focus(session)
            ok_dirty = bool(new and new.startswith("0.3"))
        time.sleep(4.0)
        print(f"{LOG} dirty 0.3: {ok_dirty} field={read_layer_height(session)!r}")

        # switch to the 0.24 preset: dialog expected
        known = pp.top_dialog_set(session)
        ok_click = pp.switch_process_preset(session, "0.24", tries=2)
        time.sleep(2.0)
        dlgs = top_dialogs(session, known)
        print(f"{LOG} dialogs after switch attempt: {dlgs}")
        if not dlgs:
            print(f"{LOG} FAIL: no confirm dialog; preset click={ok_click}")
            return 1
        dlg, title = dlgs[0]
        print(f"{LOG} dialog title: {title!r}")
        dialog_dump(session, dlg, "dlg")

        # click 'Discard'
        clicked = click_dialog_text(session, dlg, "Discard")
        if not clicked:
            clicked = click_dialog_text(session, dlg, "Don't save")
        print(f"{LOG} discard clicked: {clicked}")
        time.sleep(4.0)
        _r, _ch, ptxt = pp.find_process_preset_combo(session)
        print(f"{LOG} preset combo after discard: {ptxt!r}")
        print(f"{LOG} field after discard: {read_layer_height(session)!r}")
        frame(session, "after_discard")

        # second round: dirty again, then CANCEL via WM_CLOSE
        hit = pp.wait_float_edit(session)
        ok_dirty2 = False
        if hit:
            r, h = hit[0], hit[1]
            new = pp.real_edit_set(session, r, h, "0.3")
            pp.neutralize_focus(session)
            ok_dirty2 = bool(new and new.startswith("0.3"))
        time.sleep(4.0)
        known = pp.top_dialog_set(session)
        pp.switch_process_preset(session, "0.32", tries=2)
        time.sleep(2.0)
        dlgs2 = top_dialogs(session, known)
        print(f"{LOG} dialogs on second switch: {dlgs2}")
        if dlgs2:
            winutil.close_window(dlgs2[0][0])  # WM_CLOSE == cancel
            time.sleep(3.0)
        _r, _ch, ptxt2 = pp.find_process_preset_combo(session)
        print(f"{LOG} preset combo after cancel: {ptxt2!r}")
        print(f"{LOG} field after cancel: {read_layer_height(session)!r}")
        frame(session, "after_cancel")
        print(f"{LOG} alive={session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
