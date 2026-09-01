#!/usr/bin/env python3
# m5_common.py — shared boot for the m5 "process-parameter main flow" cases.
#
# WHY the fixture-context boot: the EMPTY boot selects no printer (Slice
# stays disabled, the process preset dropdown lists no system presets, and
# the first-run Setup Wizard [HTML] blocks the flow — all measured 09-01).
# The mixed-filament fixture brings the Snapmaker U1 (0.8 nozzle) printer
# preset + process preset context; the m5 cases then DELETE the loaded
# model and slice a RIGHT-CLICK standard primitive instead (user
# requirement: the sliced model is the context-menu standard model).
#
# Menu facts (measured): the plate context menu is a native #32768 opened
# by message-level right-click (real right-clicks are swallowed by the
# remote layer); rows are located by OCR word SEQUENCES ('Delete All' vs
# 'Select All' both contain 'all').

import ctypes
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import add_shape, mix_dialog_util as mdu  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import (VP_X0, VP_Y0, has_colored_content,  # noqa: E402
                            wait_model_loaded)
from m3_common import MIXED_3MF, boot_session  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[m5]"


def _menu_words(menu):
    r, h = menu
    w, hgt, bgra = winutil.capture_window(h)
    img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
    return r, mdu.ocr_words_img(img, scale=3)


def _menus_of(pid):
    return [(r, h) for cls, txt, r, h in mixing_util.toplevel(pid)
            if cls == "#32768"]


def _seq_point(mr, words, seq):
    """SCREEN point of the row whose OCR words contain the SEQUENCE
    (consecutive, case-insensitive). `mr` = menu screen rect; the words'
    coords are capture-relative. 'Delete All' vs 'Select All' need
    sequence matching, not substring."""
    n = len(seq)
    for i in range(len(words) - n + 1):
        got = [w.lower() for w, *_ in words[i:i + n]]
        if got == [s.lower() for s in seq]:
            xs = [mr[0] + words[i + k][1] for k in range(n)]
            ys = [mr[1] + words[i + k][2] + words[i + k][4] // 2
                  for k in range(n)]
            return (min(xs), sum(ys) // n)
    return None


def open_plate_menu(session):
    """Message-level right-click at the viewport center; returns
    (menu_rect, ocr_words) or (None, None)."""
    img = capture_bgr(session)
    hh, ww = img.shape[:2]
    cx, cy = VP_X0 + (ww - VP_X0) // 2, (VP_Y0 + hh) // 2
    hwnd = winutil.deepest_child_at(session.hwnd, cx, cy)
    lp = winutil._lparam_from_screen(hwnd, cx, cy)
    winutil._send_msg(hwnd, 0x0204, 0x0002, lp)  # WM_RBUTTONDOWN
    winutil._send_msg(hwnd, 0x0205, 0, lp)       # WM_RBUTTONUP
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        time.sleep(0.3)
        menus = _menus_of(session.pid)
        if menus:
            return _menu_words(menus[0])
    return None, None


def menu_click(session, seq, dismiss=True):
    """Click the context-menu row matching `seq`; True when clicked."""
    menu = open_plate_menu(session)
    if not menu:
        return False
    mr, words = menu
    pt = _seq_point(mr, words, seq)
    if not pt:
        if dismiss:
            for _ in range(2):
                mdu._send_keys([(0x1B, False), (0x1B, True)])
                time.sleep(0.3)
        return False
    winutil.user32.SetCursorPos(*pt)
    time.sleep(0.2)
    winutil.real_click_screen(*pt)
    time.sleep(2.0)
    return True


def _delete_row_point(mr, words):
    """SCREEN point of the Delete row: prefer the 'Delete All' pair, then a
    bare 'Delete' that is NOT the 'Delete Plate' row (clicking that removes
    the plate and can close the app — measured 09-01)."""
    pt = _seq_point(mr, words, ("Delete", "All"))
    if pt:
        return pt
    for i, w in enumerate(words):
        if w[0].lower() == "delete":
            if i + 1 < len(words) and words[i + 1][0].lower() == "plate":
                continue
            return (mr[0] + w[1], mr[1] + w[2] + w[4] // 2)
    return None


def delete_all_models(session, timeout_s=20.0):
    """Right-click Delete until the plate loses its chromatic content.
    The on-model menu row is 'Delete' (Del); the blank-plate menu row is
    'Delete All' — try both sequences, per attempt (measured 09-01)."""
    for attempt in range(3):
        menu = open_plate_menu(session)
        if not menu:
            time.sleep(1.0)
            continue
        mr, words = menu
        print(f"{LOG} delete menu ocr: "
              f"{' | '.join(w for w, *_ in words)[:200]!r}")
        pt = _delete_row_point(mr, words)
        if not pt:
            for _ in range(2):
                mdu._send_keys([(0x1B, False), (0x1B, True)])
                time.sleep(0.3)
            time.sleep(1.0)
            continue
        winutil.user32.SetCursorPos(*pt)
        time.sleep(0.2)
        winutil.real_click_screen(*pt)
        time.sleep(2.0)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            frac = has_colored_content(capture_bgr(session))
            if frac < 0.006:
                print(f"{LOG} plate empty after delete (attempt {attempt})")
                return True
            time.sleep(1.0)
        print(f"{LOG} chroma still high after attempt {attempt}")
    frac = has_colored_content(capture_bgr(session))
    print(f"{LOG} delete gave up, chroma {frac:.3%}")
    return frac < 0.006


def close_setup_wizard(session, attempts=4):
    """Delegate to the generic process_panel implementation."""
    from harness import process_panel as pp
    return pp.close_setup_wizard(session, attempts, log="[m5]")


def boot_cube_session(args, shape="Cube"):
    """Fixture-context boot -> delete the loaded model -> add the
    right-click standard primitive. Returns (session, ok).

    RE-MAXIMIZE at the end: the app spontaneously RESTORES the window
    (to ~1366x751) around the first user input after the delete/add
    dance — measured 09-01 — which breaks every maximized-window
    calibration downstream. Re-assert and verify."""
    session = boot_session(args, model=MIXED_3MF)
    print(f"{LOG} wizard relocated: "
          f"{pp.relocate_wizard(session, log='[m5]')}")
    ok_model, _frac = wait_model_loaded(session, timeout_s=240)
    print(f"{LOG} fixture model loaded: {ok_model}")
    ok_del = delete_all_models(session) if ok_model else False
    print(f"{LOG} fixture model deleted: {ok_del}")
    if not ok_del:
        session.close()
        return session, False
    ok_add = add_shape.add_primitive(session, shape)
    print(f"{LOG} standard {shape} added: {ok_add}")
    l, t, r, b = winutil.window_rect(session.hwnd)
    if (r - l) < 1900:
        winutil.user32.ShowWindow(session.hwnd, 3)  # SW_MAXIMIZE
        time.sleep(1.5)
        l, t, r, b = winutil.window_rect(session.hwnd)
        print(f"{LOG} re-maximized: rect=({l},{t},{r},{b})")
    return session, ok_add
