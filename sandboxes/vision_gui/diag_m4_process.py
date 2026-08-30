#!/usr/bin/env python3
# diag_m4_process.py — one-boot dump of the sidebar PROCESS panel (bottom of
# the left sidebar): preset combos (printer / process), the self-drawn tab
# row (OCR), visible option controls (Statics / Edits / checkbox Buttons)
# and a full-sidebar capture for pixel work. Also probes the Multimaterial
# tab by OCR word clicks and dumps the checkbox state after activation.

import ctypes
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, ocr_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[diag]"
SB_W = 424


def client(session, x, y):
    return winutil.client_to_screen(session.hwnd, x, y)


def dump_children(session, x_max=SB_W, y_min=560, tag="process"):
    rows = []
    for t, c, r, h in mixing_util.children(session.hwnd):
        lx0, ly0 = r[0] - winutil.window_rect(session.hwnd)[0], \
            r[1] - winutil.window_rect(session.hwnd)[1]
        if r[0] - winutil.window_rect(session.hwnd)[0] > x_max:
            continue
        if r[1] - winutil.window_rect(session.hwnd)[1] < y_min:
            continue
        vis = bool(user32.IsWindowVisible(h))
        rows.append((ly0, lx0, t[:48], c, r, h, vis))
    rows.sort()
    print(f"{LOG} --- children ({tag}, local x<={x_max} y>={y_min}) ---")
    for ly0, lx0, t, c, r, h, vis in rows:
        if not t and c not in ("Edit", "Button", "ComboBox"):
            continue
        print(f"  y{ly0:<4} x{lx0:<4} {c:<12} vis={vis} {t!r} rect={r}")
    return rows


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = wait_model_loaded(session, timeout_s=40)
        print(f"{LOG} model loaded: {ok}")
        time.sleep(2.0)

        img = capture_bgr(session)
        cv2.imwrite(str(HERE / "artifacts" / "diag_m4_process_full.png"), img)

        # --- all '@' texts (preset combos) in the whole window ---
        frect = winutil.window_rect(session.hwnd)
        print(f"{LOG} frame rect: {frect}")
        for t, c, r, h in mixing_util.children(session.hwnd):
            if "@" in t and user32.IsWindowVisible(h):
                print(f"{LOG} preset combo: {c} {t!r} rect={r}")

        # --- printer combo candidates: text 'Snapmaker U1' without @ ---
        for t, c, r, h in mixing_util.children(session.hwnd):
            if t.strip() in ("Snapmaker U1", "Snapmaker U1 (0.8 nozzle)") \
                    and user32.IsWindowVisible(h):
                print(f"{LOG} printer combo cand: {c} {t!r} rect={r}")

        dump_children(session, y_min=560, tag="process-area")

        # --- OCR the process area ---
        sub = img[560:800, 0:SB_W]
        words = mdu.ocr_words_img(sub, scale=3)
        print(f"{LOG} OCR process area (offsets +560y):")
        for w, x, y, ww, hh in words:
            print(f"    {w!r} @ ({x},{y}) {ww}x{hh}")

        # --- click the Multimaterial tab word (real click) ---
        target = None
        for w, x, y, ww, hh in words:
            if "material" in w.lower():
                target = (x, y, ww, hh)
                break
        print(f"{LOG} multimaterial word: {target}")
        if target:
            x, y, ww, hh = target
            sx, sy = client(session, x + ww // 2, 560 + y + hh // 2)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            winutil.real_click_screen(sx, sy)
            time.sleep(1.5)
            img2 = capture_bgr(session)
            cv2.imwrite(str(HERE / "artifacts" / "diag_m4_process_mm.png"), img2)
            dump_children(session, y_min=560, tag="multimaterial-page")
            sub2 = img2[560:800, 0:SB_W]
            for w, x2, y2, ww2, hh2 in mdu.ocr_words_img(sub2, scale=3):
                print(f"    MM-OCR {w!r} @ ({x2},{y2})")

        # --- checkbox probe anywhere in the frame ---
        for t, c, r, h in mixing_util.children(session.hwnd):
            if "Subdivide" in t or "dithering" in t.lower():
                chk = user32.SendMessageW(h, 0x00F0, 0, 0)
                print(f"{LOG} checkbox cand: {c} {t!r} rect={r} "
                      f"BM_GETCHECK={chk} vis={user32.IsWindowVisible(h)}")

        # --- Quality tab: layer height edit ---
        print(f"{LOG} --- all Edit children (visible) ---")
        for t, c, r, h in mixing_util.children(session.hwnd):
            if c == "Edit" and user32.IsWindowVisible(h):
                ln = user32.SendMessageW(h, 0x000E, 0, 0)
                buf = ctypes.create_unicode_buffer(ln + 2)
                user32.SendMessageW(h, 0x000D, ln + 1,
                                    ctypes.c_void_p(ctypes.addressof(buf)))
                print(f"    rect={r} text={buf.value!r}")

        print(f"{LOG} alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
