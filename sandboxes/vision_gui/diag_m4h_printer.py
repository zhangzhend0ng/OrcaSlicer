#!/usr/bin/env python3
# diag_m4h_printer.py — explore how the 0.4-nozzle printer variant is
# selected: printer combo popup content, what the 'Snapmaker U1' row click
# does, the 'Select/Remove printers' dialog, and the sidebar-top children.

import ctypes
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[diagp]"


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, _ = wait_model_loaded(session, timeout_s=40)
        print(f"{LOG} model loaded: {ok}")
        time.sleep(2.0)
        f = winutil.window_rect(session.hwnd)

        # sidebar top children dump
        print(f"{LOG} --- sidebar top children (ly<300) with text ---")
        rows = []
        for t, c, r, h in mixing_util.children(session.hwnd):
            lx, ly = r[0] - f[0], r[1] - f[1]
            if lx < 440 and ly < 300 and t.strip() and user32.IsWindowVisible(h):
                rows.append((ly, lx, t[:40], c, r, h))
        rows.sort()
        for ly, lx, t, c, r, h in rows:
            print(f"  y{ly:<4} x{lx:<4} {c:<12} {t!r} {r}")

        # open printer popup
        pr = next(((t, r, h) for t, c, r, h, lx, ly in
                   [(a, b, cc, d, e, f2) for a, b, cc, d, e, f2 in []]), None)
        combo = None
        for t, c, r, h in mixing_util.children(session.hwnd):
            if c == "wxWindowNR" and t.strip() == "Snapmaker U1" \
                    and user32.IsWindowVisible(h):
                combo = (t, r, h)
                break
        print(f"{LOG} combo: {combo and combo[1]}")
        crect = combo[1]
        known = set(h for _c, _t, _r, h in mixing_util.toplevel(session.pid))
        cx, cy = (crect[0] + crect[2]) // 2, (crect[1] + crect[3]) // 2
        winutil.msg_click_screen(cx, cy, session.hwnd)
        time.sleep(1.2)
        pop = None
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "wxWindowNR" and txt == "panel" and h not in known:
                pop = (r, h)
        print(f"{LOG} popup: {pop and pop[0]}")

        def grab(tag):
            if not pop:
                return
            w, h, bgra = winutil.capture_window(pop[1])
            img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
            cv2.imwrite(str(HERE / f"artifacts/m4h_pop_{tag}.png"),
                        img[:, :, ::-1].copy())
            print(f"{LOG} saved m4h_pop_{tag}.png {img.shape}")

        grab("open")
        # click the 'Snapmaker U1' row (row index 1, 28px pitch)
        if pop:
            pr2 = pop[0]
            winutil.user32.SetCursorPos((pr2[0] + pr2[2]) // 2, pr2[1] + 14 + 1 * 28)
            time.sleep(0.3)
            winutil.real_click_screen((pr2[0] + pr2[2]) // 2, pr2[1] + 14 + 1 * 28)
            time.sleep(1.5)
            # popup may have expanded in place — capture new state
            pops = [(r, h) for cls, txt, r, h in mixing_util.toplevel(session.pid)
                    if cls == "wxWindowNR" and txt == "panel"]
            print(f"{LOG} panels after row click: {[p[0] for p in pops]}")
            if pops:
                pop = pops[0]
                grab("afterclick")
                # OCR rows via psm6 per 28px band
                w, h, bgra = winutil.capture_window(pop[1])
                img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
                for i in range((h - 10) // 28):
                    band = img[4 + i * 28: 32 + i * 28, :]
                    big = cv2.resize(band, None, fx=3, fy=3,
                                     interpolation=cv2.INTER_CUBIC)
                    from harness import ocr_util
                    txt = ocr_util.ocr_image(big).replace("\n", " ")
                    print(f"    row{i}: {txt!r}")

        # dump any new top-level dialogs
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if h not in known and cls != "wxWindowNR":
                print(f"{LOG} new toplevel: {cls} {txt!r} {r}")
        mdu.popup_cancel(session)
        print(f"{LOG} alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
