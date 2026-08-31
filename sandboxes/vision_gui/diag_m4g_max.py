#!/usr/bin/env python3
# diag_m4g_max.py — why does m4g fail on the MAXIMIZED window? Dumps the
# live child tree around the options panel + tests the real-wheel scroll,
# so the fix is calibrated against the actual maximize layout (not guesses).
#
# Run: hv_go.ps1 -Cases diag_m4g_max  (logs to artifacts\regress_diag_m4g_max.log)

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402
import m4g_mixing_sublayer as g  # noqa: E402

LOG = "[diag]"
SB_X1 = 440  # sidebar right edge (client x)


def dump_candidates(session, f):
    print(f"{LOG} --- sidebar wxWindowNR with text (local y 600..1100) ---")
    for t, c, r, h in mixing_util.children(session.hwnd):
        if not t.strip() or not user32_visible(h):
            continue
        lx, ly = r[0] - f[0], r[1] - f[1]
        if lx > SB_X1 or not (600 <= ly <= 1100):
            continue
        print(f"{LOG}   {t.strip()!r} | {c} | local=({lx},{ly},"
              f"{r[2] - f[0]},{r[3] - f[1]})")


def user32_visible(h):
    return winutil.user32.IsWindowVisible(h)


def dump_color_texts(session, f):
    print(f"{LOG} --- ALL children with 'color'/'subdiv'/'mix' in text ---")
    for t, c, r, h in mixing_util.children(session.hwnd):
        tl = t.lower()
        if "color" in tl or "subdiv" in tl or "mix" in tl:
            vis = user32_visible(h)
            lx, ly = r[0] - f[0], r[1] - f[1]
            print(f"{LOG}   {t.strip()[:60]!r} | {c} | local=({lx},{ly},"
                  f"{r[2] - f[0]},{r[3] - f[1]}) | vis={vis}")


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    session = boot_session(args, model=args.model)
    try:
        ok, _frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model loaded: {ok}")
        time.sleep(2.0)
        f = g.frect(session)
        print(f"{LOG} window rect: {f}")

        sw = g.advanced_switch(session)
        print(f"{LOG} advanced switch: {sw}")
        if sw:
            g.real_click(sw[0])
            time.sleep(2.0)
        tab_ok = g.click_tab(session, "Multimaterial", "tower")
        print(f"{LOG} multimaterial tab: {tab_ok}")
        time.sleep(1.0)

        vp = g.options_viewport(session)
        print(f"{LOG} options_viewport: "
              f"{None if not vp else (vp[0], hex(vp[1]))}")
        for kw in ("Prime tower", "Color Mixing", "Subdivide"):
            gt = g.group_title(session, kw)
            print(f"{LOG} group_title({kw!r}): "
                  f"{None if not gt else (gt[0], hex(gt[1]))}")

        dump_candidates(session, f)
        dump_color_texts(session, f)

        if vp:
            before = " ".join(w for w, *_ in g.ocr_band(session))
            print(f"{LOG} band before wheel: {before[:110]!r}")
            g.wheel_viewport(session, vp, 10, delta=-120)
            time.sleep(1.2)
            mid = " ".join(w for w, *_ in g.ocr_band(session))
            print(f"{LOG} band after 10 down:  {mid[:110]!r}")
            g.wheel_viewport(session, vp, 40, delta=-120)
            time.sleep(1.2)
            after = " ".join(w for w, *_ in g.ocr_band(session))
            print(f"{LOG} band after 50 down:  {after[:110]!r}")
            for kw in ("Color Mixing", "Subdivide"):
                gt = g.group_title(session, kw)
                print(f"{LOG} group_title({kw!r}) after scroll: "
                      f"{None if not gt else (gt[0], hex(gt[1]))}")

        print("[m3] === verdict ===")
        print("  diag: PASS")
        print("[m3] GREEN")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
