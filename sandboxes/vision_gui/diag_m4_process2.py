#!/usr/bin/env python3
# diag_m4_process2.py — focused probe: does the Multimaterial page expose a
# 'Subdivide Mix Layer' label Static / checkbox Button after tab activation,
# and where is the Quality page's Layer height Edit. Full output to a file.

import ctypes
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[diag2]"


def client(session, x, y):
    return winutil.client_to_screen(session.hwnd, x, y)


def kids(session):
    frect = winutil.window_rect(session.hwnd)
    out = []
    for t, c, r, h in mixing_util.children(session.hwnd):
        lx, ly = r[0] - frect[0], r[1] - frect[1]
        out.append((t, c, r, h, lx, ly))
    return out


def dump_region(session, x_max=440, y_min=560, tag=""):
    print(f"{LOG} --- region dump {tag} ---")
    rows = [(ly, lx, t, c, r, h) for t, c, r, h, lx, ly in kids(session)
            if lx <= x_max and ly >= y_min and t.strip()]
    rows.sort()
    for ly, lx, t, c, r, h in rows:
        vis = bool(user32.IsWindowVisible(h))
        print(f"  y{ly:<4} x{lx:<4} {c:<12} vis={int(vis)} {t[:44]!r} {r}")


def find_sub(session, tag):
    hits = [(t, c, r, h, lx, ly) for t, c, r, h, lx, ly in kids(session)
            if "subdivide" in t.lower()]
    print(f"{LOG} subdivide hits ({tag}): {len(hits)}")
    for t, c, r, h, lx, ly in hits:
        print(f"    {c} vis={int(user32.IsWindowVisible(h))} {t!r} "
              f"local=({lx},{ly}) {r} hwnd=0x{h:x}")
    return hits


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = wait_model_loaded(session, timeout_s=40)
        print(f"{LOG} model loaded: {ok}")
        time.sleep(2.0)
        print(f"{LOG} total frame children: {len(kids(session))}")

        img = capture_bgr(session)
        sub = img[560:800, 0:424]
        print(f"{LOG} initial OCR (y+560):")
        for w, x, y, ww, hh in mdu.ocr_words_img(sub, scale=3):
            print(f"    {w!r} @ ({x},{y})")

        find_sub(session, "before tab click")
        dump_region(session, tag="before")

        # real-click the Multimaterial tab word
        words = mdu.ocr_words_img(img[560:800, 0:424], scale=3)
        tgt = next(((x, y, ww, hh) for w, x, y, ww, hh in words
                    if "material" in w.lower()), None)
        print(f"{LOG} tab word: {tgt}")
        if tgt:
            x, y, ww, hh = tgt
            sx, sy = client(session, x + ww // 2, 560 + y + hh // 2)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            winutil.real_click_screen(sx, sy)
            time.sleep(3.0)
        find_sub(session, "after tab click +3s")

        img2 = capture_bgr(session)
        cv2.imwrite(str(HERE / "artifacts" / "diag_m4_process2_mm.png"), img2)
        dump_region(session, tag="after-mm")

        # click Quality, dump its page + find Layer height Edit
        words2 = mdu.ocr_words_img(img2[560:800, 0:424], scale=3)
        qtgt = next(((x, y, ww, hh) for w, x, y, ww, hh in words2
                     if w.lower().startswith("qual")), None)
        print(f"{LOG} quality word: {qtgt}")
        if qtgt:
            x, y, ww, hh = qtgt
            sx, sy = client(session, x + ww // 2, 560 + y + hh // 2)
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            winutil.real_click_screen(sx, sy)
            time.sleep(3.0)
        img3 = capture_bgr(session)
        cv2.imwrite(str(HERE / "artifacts" / "diag_m4_process2_q.png"), img3)
        dump_region(session, tag="after-quality")
        print(f"{LOG} --- visible Edits ---")
        for t, c, r, h, lx, ly in kids(session):
            if c == "Edit" and user32.IsWindowVisible(h):
                val = mdu.edit_value(h)
                print(f"    local=({lx},{ly}) {r} value={val!r}")
        print(f"{LOG} alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
