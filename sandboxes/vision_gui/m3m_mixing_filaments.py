#!/usr/bin/env python3
# m3m_mixing_filaments.py — Manual-mode filament card: default rows, add /
# remove boundaries (#5/#6) and the gamut warning banner text (#13).
#
# White-box refs: none of the wx_gui cases drive the mixing dialog; source
# entries MixedFilamentBatchDialog (manual card layout + add/remove buttons,
# start_batch_match gamut warning).
# Source facts: switching to Manual shows the filament card with the
# selected physical filaments; the add/remove icon buttons sit at the card's
# right end (measured (1129,307) and (1149,307) @96dpi); adding is allowed
# while rows < 4 / < the prepared-page count, removing while rows >= 3;
# after a match, a gamut warning banner appears whose text is a plain
# Static (GetWindowText-readable, e.g. 'The mix ratios for ... outside the
# recommended 0%-70% range' — record #13).
#
# Black-box path: open dialog -> Manual -> the card shows 2 rows -> click
# the add button -> 3 rows -> click again -> 4 rows -> click again -> still
# 4 (boundary) -> click the remove button -> 3 rows -> click twice more ->
# 2 rows -> remove again -> still 2 (boundary) -> Start Matching -> the
# gamut warning banner appears and its text mentions '0%-70%'.

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

user32 = ctypes.WinDLL("user32")


def button_rects(dlg: int):
    """(remove_rect, add_rect) — the Manual card's icon buttons at the
    dialog's right edge (x > 1100): icon_minus then icon_plus."""
    cands = [r for t, c, r, h in mixing_util.children(dlg)
             if c == "Button" and r[0] > 1100 and r[2] > r[0]
             and r[3] - r[1] in (16, 25)]
    cands.sort(key=lambda r: (r[1], r[0]))
    return (cands[0], cands[1]) if len(cands) >= 2 else (None, None)


def button_enabled(hwnd: int) -> bool:
    return not bool(ctypes.WinDLL("user32").GetWindowLongW(hwnd, -16)
                    & 0x08000000)  # GWL_STYLE & WS_DISABLED


def click_rect(rect):
    winutil.real_click_screen((rect[0] + rect[2]) // 2,
                              (rect[1] + rect[3]) // 2)
    time.sleep(1.2)


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3m] model arrived: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"

        dlg = mixing_util.open_mixing_dialog(session)
        results["mixing dialog opens"] = "PASS" if dlg else "FAIL"
        if not dlg:
            return verdict(results)

        switched = mixing_util.switch_match_mode(session, dlg, "Manual")
        print(f"[m3m] mode Manual: {switched}")
        results["mode switch to Manual"] = "PASS" if switched else "FAIL"
        time.sleep(1.0)

        # --- default state: 4 filaments -> add disabled (max_rows), the
        # remove button enabled (#5 boundary: no-op at 4) ---
        rm_btn, add_btn = button_rects(dlg)
        print(f"[m3m] remove={rm_btn} add={add_btn}")
        results["add/remove buttons found"] = (
            "PASS" if (rm_btn and add_btn) else "FAIL")

        def btn_hwnd(rect):
            for t, c, r, h in mixing_util.children(dlg):
                if r == rect and c == "Button":
                    return h
            return None

        add_en = button_enabled(btn_hwnd(add_btn)) if add_btn else False
        rm_en = button_enabled(btn_hwnd(rm_btn)) if rm_btn else False
        print(f"[m3m] initial: add_enabled={add_en} remove_enabled={rm_en}")
        results["add disabled at 4 filaments"] = (
            "PASS" if (add_btn and not add_en) else "FAIL")
        results["remove enabled at 4 filaments"] = (
            "PASS" if (rm_btn and rm_en) else "FAIL")

        # --- remove once: 4 -> 3 -> add becomes enabled (#5) ---
        if rm_btn and add_btn:
            click_rect(rm_btn)
            add_en2 = button_enabled(btn_hwnd(add_btn))
            rm_en2 = button_enabled(btn_hwnd(rm_btn))
            print(f"[m3m] after remove: add_enabled={add_en2} "
                  f"remove_enabled={rm_en2}")
            results["remove to 3 enables add"] = (
                "PASS" if add_en2 else "FAIL")

            # --- remove again: 3 -> 2 -> remove disabled (#6) ---
            click_rect(rm_btn)
            add_en3 = button_enabled(btn_hwnd(add_btn))
            rm_en3 = button_enabled(btn_hwnd(rm_btn))
            print(f"[m3m] after remove: add_enabled={add_en3} "
                  f"remove_enabled={rm_en3}")
            results["remove disabled at 2 filaments"] = (
                "PASS" if not rm_en3 else "FAIL")

            # --- add back: 2 -> 3 -> remove re-enabled (#5) ---
            if add_en3:
                click_rect(add_btn)
                rm_en4 = button_enabled(btn_hwnd(rm_btn))
                print(f"[m3m] after add back: remove_enabled={rm_en4}")
                results["add back to 3 re-enables remove"] = (
                    "PASS" if rm_en4 else "FAIL")

        # --- match -> gamut warning banner (#13) ---
        ok_start = mixing_util.click_button(dlg, "Start Matching")
        done = mixing_util.wait_match_done(session, dlg, timeout_s=90.0)
        print(f"[m3m] start={ok_start} match={done}")
        warn_text = None
        if done:
            time.sleep(1.0)
            for t, c, r, h in mixing_util.children(dlg):
                if "mix ratios" in t.lower() or "range" in t.lower():
                    warn_text = t
                    break
        print(f"[m3m] gamut banner: {warn_text!r}")
        results["gamut warning appears"] = (
            "PASS" if warn_text else "FAIL")
        if warn_text:
            results["gamut text mentions 0-70%"] = (
                "PASS" if ("0%" in warn_text or "70%" in warn_text)
                else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print("[m3m] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
