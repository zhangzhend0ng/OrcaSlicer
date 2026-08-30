#!/usr/bin/env python3
# m3q_mixing_view.py — original-model view default (#14), view switching
# (#17), plate display (#19) and the single-plate arrow boundary (#18).
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entry MixedFilamentBatchDialog view/plate strip (View combo + plate
# arrows, add_common_view_menu_items view list for the popup order).
# Source facts: the strip shows 'Isometric' (the default original-model
# view) and the current plate ('01'); the View combo's popup lists the
# standard views (Default View, Top, ... — same order as the View menu);
# with a single plate the left/right arrows must not change the plate.
#
# Black-box path: Manual match -> the strip shows 'Isometric' and '01' ->
# clicking the plate arrows leaves '01' unchanged (single plate) -> the
# View combo switches to 'Top' and the view panels change (pixel diff) ->
# switch back to 'Isometric' (view still switchable).

import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402


def text_of(hwnd: int) -> str:
    import ctypes
    buf = ctypes.create_unicode_buffer(128)
    ctypes.WinDLL("user32").GetWindowTextW(hwnd, buf, 128)
    return buf.value


def plate_arrows(dlg: int):
    """(left, right) arrow buttons of the plate strip (x < 1000)."""
    btns = [r for t, c, r, h in mixing_util.children(dlg)
            if c == "Button" and 690 <= r[1] <= 730 and r[2] > r[0]]
    btns.sort(key=lambda r: r[0])
    return (btns[0], btns[1]) if len(btns) >= 2 else (None, None)


def view_panels_sig(session, dlg):
    """(original, result) view panels: chromatic fractions."""
    dlg_rect = None
    for cls, txt, r, h in mixing_util.toplevel(session.pid):
        if h == dlg:
            dlg_rect = r
    img = mixing_util.dialog_bgr(dlg)
    orig = mixing_util.map_region_colored(img, dlg_rect, (738, 451, 918, 631))
    res = mixing_util.map_region_colored(img, dlg_rect, (938, 451, 1165, 678))
    return orig, res


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3q] model arrived: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        dlg = mixing_util.open_mixing_dialog(session)
        results["mixing dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)
        mixing_util.switch_match_mode(session, dlg, "Manual")
        ok_start = mixing_util.click_button(dlg, "Start Matching")
        done = mixing_util.wait_match_done(session, dlg, timeout_s=420.0)
        print(f"[m3q] match: {ok_start}/{done}")
        results["match completes"] = "PASS" if done else "FAIL"
        if not done:
            return verdict(results)
        time.sleep(1.5)

        # --- strip texts: view 'Isometric' + plate '01' (#14/#19) ---
        view_txt, plate_txt = None, None
        for t, c, r, h in mixing_util.children(dlg):
            if c == "wxWindowNR" and 690 <= r[1] <= 730 and r[2] - r[0] > 40:
                txt = text_of(h)
                if txt in ("Isometric", "Top", "Front", "Bottom"):
                    view_txt = txt
                if txt.isdigit():
                    plate_txt = txt
        print(f"[m3q] view={view_txt!r} plate={plate_txt!r}")
        results["default view is Isometric"] = (
            "PASS" if view_txt == "Isometric" else "FAIL")
        results["plate shows current plate"] = (
            "PASS" if plate_txt == "01" else "FAIL")

        # --- single plate: arrows must not change the plate (#18) ---
        left, right = plate_arrows(dlg)
        print(f"[m3q] arrows: left={left} right={right}")
        unchanged = False
        if left and right:
            dlg_rect = None
            for cls, txt, r, h in mixing_util.toplevel(session.pid):
                if h == dlg:
                    dlg_rect = r
            strip0 = mixing_util.dialog_bgr(dlg)[545:580, 20:500]
            for rect in (left, right):
                winutil.real_click_screen((rect[0] + rect[2]) // 2,
                                          (rect[1] + rect[3]) // 2)
                time.sleep(1.0)
            strip1 = mixing_util.dialog_bgr(dlg)[545:580, 20:500]
            diff = float(np.abs(strip0.astype(int) - strip1.astype(int)).mean())
            print(f"[m3q] strip diff after both arrows: {diff:.2f}")
            unchanged = diff < 1.0
        results["single plate arrows no-op"] = (
            "PASS" if unchanged else "FAIL")

        # --- View switch to Top -> view panels change (#17) ---
        sig0 = view_panels_sig(session, dlg)
        switched = mixing_util.switch_combo(
            session, dlg, ("Isometric", "Top", "Front", "Top-Front"),
            "Top", row_guess=1)
        time.sleep(1.5)
        sig1 = view_panels_sig(session, dlg)
        print(f"[m3q] view switch to Top: {switched} "
              f"sig {sig0} -> {sig1}")
        changed = abs(sig1[0] - sig0[0]) + abs(sig1[1] - sig0[1]) > 0.02
        results["view switch changes panels"] = (
            "PASS" if (switched and changed) else "FAIL")

        # --- switch to Front too: views switch repeatedly ---
        back = mixing_util.switch_combo(
            session, dlg, ("Isometric", "Top", "Front", "Top-Front",
                           "Bottom"), "Front", row_guess=3)
        results["view switch again"] = "PASS" if back else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print("[m3q] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
