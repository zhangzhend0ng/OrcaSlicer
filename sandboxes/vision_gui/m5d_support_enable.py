#!/usr/bin/env python3
# m5d_support_enable.py — Support-page parameter MAIN FLOW: on a standard
# right-click model, enable support material, slice, and prove the flag
# reached the slicer (gcode echo) with the app healthy.
#
# White-box refs:
#   - PrintConfig 'enable_support' ('Enable support' checkbox, 'Support'
#     group, Support page); the echo lands as '; enable_support = ...'.
#   - OptionsGroup.cpp:248 activate_line — painted labels; the checkbox is
#     an ~18px empty-text wxBitmapToggleButton on the row.
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> Support page ->
# 'Enable support' checkbox ON (frame-capture teal state) -> slice ->
# export -> '; enable_support = true' -> app alive.
# Scope note: a flat-bottom cube needs no actual support towers — the
# assertion is the CONFIG echo + a completed slice (m4g convention: option
# applying + slice completing; geometry-dependent towers out of scope).
# Stale-table notes: none.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import (gcode_check, mix_dialog_util as mdu,  # noqa: E402
                     winutil)
import numpy as np  # noqa: E402
from harness import process_panel as pp  # noqa: E402
import m5_common
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (add_common_args, export_and_check,  # noqa: E402
                       slice_and_wait, verdict)

LOG = "[m5d]"


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    results = {}
    session, ok_cube = boot_cube_session(args)
    try:
        results["fixture deleted + standard model added"] = "PASS" if ok_cube else "FAIL"
        if results["fixture deleted + standard model added"] != "PASS":
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        pp.ensure_advanced(session, want=True)
        tab_ok = pp.click_tab(session, "Support", "support")
        print(f"{LOG} support page opens: {tab_ok}")
        results["support page opens"] = "PASS" if tab_ok else "FAIL"
        if not tab_ok:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        st, rect = pp.set_option_checkbox(session, "Enable", True,
                                          group_substr="Support")
        print(f"{LOG} enable support: state={st} rect={rect}")
        results["enable support checks on"] = "PASS" if st is True \
            else "FAIL"
        if st is not True:
            results["slice with support on"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # the default Tree (auto) type leaves the U1 0.8 preset INVALID
        # (organic tip diameter < support extrusion width -> Slice disabled
        # with a red config-error toast; measured 09-01): switch Type ->
        # Normal so the config validates
        pp.relocate_wizard(session)
        # the Support Type dropdown: click the combo, then click the
        # 'Normal (auto)' row inside its popup (self-drawn 'panel')
        _r, _h, cur = pp.find_option_combo(session, "Tree")
        ok_t = False
        if _h:
            cx, cy = (_r[0] + _r[2]) // 2, (_r[1] + _r[3]) // 2
            winutil.msg_click_screen(cx, cy, session.hwnd)
            from harness import export_util
            popup = None
            for _ in range(20):
                popup = export_util.wait_popup(session.pid, timeout_s=0.5)
                if popup:
                    break
            print(f"{LOG} type popup: {popup}")
            if popup:
                pr, ph = popup[2], popup[3]
                time.sleep(0.8)  # self-drawn rows lag the popup creation
                words = []
                for attempt in range(3):
                    w, hgt, bgra = winutil.capture_window(ph)
                    import numpy as np
                    img = np.frombuffer(bgra, np.uint8).reshape(
                        hgt, w, 4)[:, :, :3]
                    words = mdu.ocr_words_img(img, scale=3)
                    if words:
                        break
                    time.sleep(0.6)
                print(f"{LOG} popup rows: "
                      f"{' | '.join(t for t, *_ in words)[:140]!r}")
                clicked = False
                for t, x, y, w_w, w_h in words:
                    if "normal" in t.lower():
                        winutil.msg_click_screen(pr[0] + x + w_w // 2,
                                                 pr[1] + y + w_h // 2)
                        clicked = True
                        break
                if not clicked:
                    # blind fallback: 28px row pitch, rows 0..n, verify by
                    # re-locating the combo by its new value after each
                    import time as _t
                    for row in range(5):
                        winutil.msg_click_screen(
                            (pr[0] + pr[2]) // 2, pr[1] + 14 + row * 28)
                        _t.sleep(1.0)
                        if pp.find_option_combo(session, "Normal")[1]:
                            clicked = True
                            print(f"{LOG} blind row {row} hit Normal")
                            break
                        # reopen the popup for the next row
                        winutil.msg_click_screen(cx, cy, session.hwnd)
                        _t.sleep(1.0)
                        popup2 = None
                        for _ in range(10):
                            popup2 = export_util.wait_popup(
                                session.pid, timeout_s=0.5)
                            if popup2:
                                break
                            _t.sleep(0.2)
                        if not popup2:
                            break
                        pr = popup2[2]
                time.sleep(1.5)
            _r2, _h2, cur2 = pp.find_option_combo(session, "Normal")
            ok_t = _h2 is not None
            print(f"{LOG} support type now: {cur2!r} ok={ok_t}")

        sliced = slice_and_wait(session, timeout_s=900)
        out_path = Path(args.datadir).parent / "m5d_support.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        es = gcode_check.config_value(data, "enable_support") if ok_exp \
            else None
        print(f"{LOG} slice={sliced} export={ok_exp} enable_support={es!r}")
        results["slice + export"] = "PASS" if (sliced and ok_exp) else "FAIL"
        # the echo is boolean-encoded: this build writes '1' (measured
        # 09-01), other builds may write 'true'
        results["gcode enable_support = true"] = (
            "PASS" if es is not None and es.lower().startswith(("true", "1"))
            else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
