#!/usr/bin/env python3
# diag_m4g_quality.py — in Advanced mode, dump the Quality page: visible
# Edits anywhere in the sidebar band, OCR of the viewport, and the effect of
# scrolling up first. Reuses m4g helpers.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import m4g_mixing_sublayer as g  # noqa: E402
from harness import winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402

LOG = "[diagq]"


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, _ = wait_model_loaded(session, timeout_s=40)
        print(f"{LOG} model loaded: {ok}")
        time.sleep(2.0)

        sw = g.advanced_switch(session)
        g.real_click(sw[0])
        time.sleep(2.0)
        print(f"{LOG} advanced flipped")

        # Quality tab BEFORE ever touching Multimaterial
        print(f"{LOG} tab click: {g.click_tab(session, 'Quality')}")
        time.sleep(1.5)
        vp = g.options_viewport(session)
        print(f"{LOG} viewport: {vp and g.to_local(session, vp[0])}")
        # dump ALL visible edits in the sidebar
        for t, c, r, h, lx, ly in g.kids(session):
            if c == "Edit" and winutil and __import__("ctypes").WinDLL("user32").IsWindowVisible(h):
                if lx < 430 and 640 <= ly <= 820:
                    print(f"{LOG} edit local=({lx},{ly}) rect={r} "
                          f"value={__import__('harness.mix_dialog_util', fromlist=['edit_value']).edit_value(h)!r}")
        words = g.ocr_band(session, y0=640, y1=820)
        print(f"{LOG} OCR 640-820:")
        for w, x, y, ww, hh in words:
            print(f"    {w!r} @ ({x},{y})")

        # scroll to top, retry
        vp = g.options_viewport(session)
        if vp:
            g.wheel_viewport(session, vp, 20, delta=120)
        for t, c, r, h, lx, ly in g.kids(session):
            if c == "Edit" and __import__("ctypes").WinDLL("user32").IsWindowVisible(h):
                if lx < 430 and 640 <= ly <= 820:
                    print(f"{LOG} after-up edit local=({lx},{ly}) rect={r}")
        words = g.ocr_band(session, y0=640, y1=820)
        print(f"{LOG} OCR after scroll-up:")
        for w, x, y, ww, hh in words:
            print(f"    {w!r} @ ({x},{y})")
        print(f"{LOG} alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
