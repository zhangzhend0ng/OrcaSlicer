#!/usr/bin/env python3
# diag_m5_wizard.py — v3: add the 'Snapmaker U1 (0.8 nozzle)' printer via
# the printer popup's 'Select/Remove printers (system presets)' dialog.
#   boot -> close wizard -> printer combo -> popup row index 2 (blind 28px
#   pitch, visual-confirmed layout) -> dump the select-printers dialog ->
#   click the '0.8' item -> OK -> dump sidebar (diameter expected 0.8mm).
# Run: hv_go.ps1 -Cases diag_m5_wizard

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
from m3_common import add_common_args, boot_session, verdict  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[diag]"


def close_wizard(session):
    for cls, txt, r, h in mixing_util.toplevel(session.pid):
        if cls == "#32770" and "wizard" in txt.lower():
            winutil.close_window(h)
            time.sleep(1.5)
            return True
    return False


def popup_panels(pid):
    return [(r, h) for cls, txt, r, h in mixing_util.toplevel(pid)
            if cls == "wxWindowNR" and txt == "panel"]


def ocr_dump(tag, hwnd):
    w, hgt, bgra = winutil.capture_window(hwnd)
    img = np.frombuffer(bgra, np.uint8).reshape(hgt, w, 4)[:, :, :3]
    cv2.imwrite(str(HERE / "artifacts" / f"m5_diag_{tag}.png"),
                img[:, :, ::-1])
    words = mdu.ocr_words_img(img, scale=3)
    print(f"{LOG} [{tag}] ocr: {' | '.join(t for t, *_ in words)[:250]!r}")
    return words


def sidebar_probe(session, tag):
    f = winutil.window_rect(session.hwnd)
    hits = []
    for t, c, r, h in mixing_util.children(session.hwnd):
        lx0, ly0 = r[0] - f[0], r[1] - f[1]
        if lx0 <= 440 and 130 <= ly0 <= 340 and t.strip():
            hits.append((t.strip()[:30], c, lx0, ly0))
    print(f"{LOG} sidebar[{tag}] y130-340: {hits}")
    return hits


def big_dialog(pid):
    """The biggest visible #32770 (the select-printers dialog)."""
    best = None
    for cls, txt, r, h in mixing_util.toplevel(pid):
        if cls == "#32770":
            area = (r[2] - r[0]) * (r[3] - r[1])
            if best is None or area > best[0]:
                best = (area, r, h, txt)
    return (best[1], best[2], best[3]) if best else None


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=None)
    try:
        print(f"{LOG} wizard closed: {close_wizard(session)}")

        # open the printer preset popup, click row index 2
        f = winutil.window_rect(session.hwnd)
        combo = None
        for t, c, r, h in mixing_util.children(session.hwnd):
            lx0, ly0 = r[0] - f[0], r[1] - f[1]
            if lx0 <= 440 and 130 <= ly0 <= 175 \
                    and t.strip() == "Snapmaker U1":
                combo = (r, h)
        if not combo:
            print(f"{LOG} printer combo not found")
            results["printer combo"] = "FAIL"
            return verdict(results)
        r, h = combo
        winutil.msg_click_screen((r[0] + r[2]) // 2, (r[1] + r[3]) // 2,
                                 session.hwnd)
        time.sleep(1.2)
        pops = popup_panels(session.pid)
        if not pops:
            print(f"{LOG} no popup")
            results["popup"] = "FAIL"
            return verdict(results)
        pr = pops[0][0]
        # rows: 0 header / 1 Snapmaker U1 / 2 Select-Remove / 3 Create
        sel_y = pr[1] + 14 + 2 * 28
        print(f"{LOG} clicking Select/Remove row at "
              f"({(pr[0] + pr[2]) // 2}, {sel_y})")
        winutil.msg_click_screen((pr[0] + pr[2]) // 2, sel_y)
        time.sleep(2.0)

        dlg = big_dialog(session.pid)
        print(f"{LOG} select-printers dialog: {dlg}")
        results["select dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            cv2.imwrite(str(HERE / "artifacts" / "m5_no_select_dlg.png"),
                        capture_bgr(session)[:, :, ::-1])
            return verdict(results)
        dr, dh, _txt = dlg
        words = ocr_dump("select_dlg", dh)
        btns = [(t.strip(), c) for t, c, rr, hh in mixing_util.children(dh)
                if t.strip()]
        print(f"{LOG} dialog children with text: {btns[:20]}")

        # click the '0.8' list item (OCR position within the dialog)
        target = None
        for t, x, y, w_w, w_h in words:
            if "0.8" in t:
                target = (dr[0] + x + w_w // 2, dr[1] + y + w_h // 2)
                break
        results["0.8 item visible"] = "PASS" if target else "FAIL"
        if target:
            print(f"{LOG} 0.8 item at {target} -> click")
            winutil.user32.SetCursorPos(*target)
            time.sleep(0.2)
            winutil.real_click_screen(*target)
            time.sleep(1.0)
            words = ocr_dump("select_dlg_after", dh)

        # confirm via the dialog's OK/confirm button (bottom-right Button)
        btns2 = [(rr, hh) for t, c, rr, hh in mixing_util.children(dh)
                 if c == "Button" and user32.IsWindowVisible(hh)
                 and (rr[2] - rr[0]) > 40]
        if btns2:
            btns2.sort(key=lambda rh: (rh[0][0] + rh[0][2], rh[0][1]))
            br, bh = btns2[-1]
            label = [t for t, c, rr, hh in mixing_util.children(dh)
                     if hh == bh]
            print(f"{LOG} clicking dialog confirm {label}")
            winutil.real_click_screen((br[0] + br[2]) // 2,
                                      (br[1] + br[3]) // 2)
            time.sleep(2.0)

        sidebar_probe(session, "after-add")
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
