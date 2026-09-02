#!/usr/bin/env python3
# m5g_preset_manage.py — process-preset MANAGEMENT main flow: save the
# modified config as a USER preset, survive an app RESTART with the same
# datadir, select it again, DELETE it, and prove the app fell back cleanly.
#
# White-box refs (measured 09-02 diag_m5g_preset):
#   - Tab.cpp:299-313 — the preset row carries 'save' (m_btn_save_preset,
#     tooltip 'Save current Process') and 'cross' (m_btn_delete_preset,
#     tooltip 'Delete this preset', SHOWN only when the edited preset is a
#     user preset — update_btns_enabling). MEASURED: the buttons sit on the
#     PRESET row (anchor py+20..py+70), NOT on the Process-title row (that
#     row carries the Advanced switch + view/compare icons).
#   - Tab.cpp:6156 — SavePresetDialog (#32770 'Save preset'): name Edit
#     (prefilled, LIVE text — no Enter needed), 'User Preset' /
#     'Preset Inside Project' radio rows, 'OK'/'Cancel' — all painted
#     wxWindowNR, NOT class Button (a class-filtered search finds nothing).
#   - user presets land in <datadir>/user/default/process/<name>.json
#     (+ .info) — NOT <datadir>/process (measured).
#   - Tab.cpp:6281 delete_preset — MessageDialog 'Delete Preset' /
#     'Are you sure to delete the selected preset?' wxYES_NO.
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> Quality: layer
# height 0.3 (dirty) -> save-icon click -> 'Save preset' dialog -> name
# 'm5g_flow_preset' + User Preset + OK -> json exists + combo shows it ->
# RESTART same datadir (no reseed) -> combo/popup still offers it + json
# still there -> select it -> delete-cross -> confirm Yes -> json GONE +
# combo falls back -> app alive.
# Stale-table notes: the preset save/delete buttons were previously
# untested (m5a covered switching only).

import ctypes
import cv2
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import launcher, mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util  # noqa: E402
from harness import ocr_util  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from harness import winutil  # noqa: E402
import m5_common  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (MIXED_3MF, add_common_args, boot_session,  # noqa: E402
                       verdict)
from m2_slice_chain import wait_model_loaded  # noqa: E402
from harness import profile  # noqa: E402

LOG = "[m5g]"
PRESET_NAME = "m5g_flow_preset"


def preset_row_buttons(session):
    """Small empty-text Buttons on the PRESET row (anchor py+8..py+70,
    right half). MEASURED: the Process-title row's icons are the Advanced
    switch / view / compare — a band that includes them mis-hits."""
    py = pp.process_row_y(session)
    out = []
    for t, c, r, h, lx, ly in pp.kids(session):
        if c != "Button" or t.strip() or not pp.user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (10 <= w <= 40 and 8 <= hh <= 32):
            continue
        if py + 8 <= ly <= py + 70 and lx > 250:
            out.append((r, h))
    out.sort(key=lambda rh: rh[0][0])
    return out


def hover_tooltip(session, rect, dwell_s=4.0):
    """Tooltip text for a button rect; parks the cursor on a NEUTRAL spot
    first so a stale tooltip from the previous hover is not re-read
    (measured: the old window lingers and wait_tooltip returns it)."""
    winutil.user32.SetCursorPos(rect[0] - 150, rect[1] - 60)
    time.sleep(1.2)
    tt = mixing_util.hover_swatch_row(
        session, session.hwnd, (rect[0] - 4, rect[1] - 4,
                                rect[2] + 4, rect[3] + 4),
        x_frac=0.5, dwell_s=dwell_s)
    return ocr_util.ocr_hwnd(tt[1]) if tt else ""


def find_button_by_tooltip(session, substr, tries=4):
    """(rect, hwnd, tooltip) of the preset-row button whose tooltip
    contains `substr`; falls back to (leftmost, 'save')."""
    btns = preset_row_buttons(session)
    print(f"{LOG} preset-row buttons: {[r for r, _h in btns]}")
    for _attempt in range(tries):
        for r, h in btns:
            tip = hover_tooltip(session, r)
            print(f"{LOG} btn {r} tooltip={tip!r}")
            if substr.lower() in tip.lower():
                return r, h, tip
    return None, None, None


def preset_row_text(session):
    """Text of the preset selector on the preset row (a wxWindowNR with
    REAL text; after a save it shows the new preset name)."""
    py = pp.process_row_y(session)
    for t, c, r, h, lx, ly in pp.kids(session):
        if c == "wxWindowNR" and t.strip() and pp.user32.IsWindowVisible(h) \
                and py + 8 <= ly <= py + 70 and 20 <= lx <= 340 \
                and (r[2] - r[0]) > 80:
            return t.strip()
    return None


def dialog_child_exact(dlg, text):
    for t, c, r, h in mixing_util.children(dlg):
        if t.strip() == text and pp.user32.IsWindowVisible(h):
            return r, h
    return None, None


def dialog_edit(dlg):
    for t, c, r, h in mixing_util.children(dlg):
        if c == "Edit" and pp.user32.IsWindowVisible(h):
            return r, h
    return None, None


def wait_new_dialog(session, known, timeout_s=8.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "#32770" and h not in known:
                return h, txt
        time.sleep(0.3)
    return None, None


def real_click(rect_or_point):
    if len(rect_or_point) == 4:
        x = (rect_or_point[0] + rect_or_point[2]) // 2
        y = (rect_or_point[1] + rect_or_point[3]) // 2
    else:
        x, y = rect_or_point
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.2)
    winutil.real_click_screen(x, y)
    time.sleep(1.0)


def save_user_preset(session):
    """Dirty-config -> Save preset dialog -> 'm5g_flow_preset'. Returns
    (ok, detail)."""
    r, h, tip = find_button_by_tooltip(session, "save")
    if not h:
        print(f"{LOG} save button NOT located")
        return False, "no save button"
    known = pp.top_dialog_set(session)
    real_click(r)
    dlg, title = wait_new_dialog(session, known)
    print(f"{LOG} save dialog: {title!r}")
    if not dlg:
        return False, "no save dialog"
    er, eh = dialog_edit(dlg)
    if not eh:
        return False, "no name edit"
    # focus + select-all + type; NO Enter — the TextInput lives on wxEVT_TEXT
    ok_focus = False
    for _ in range(4):
        winutil.force_set_foreground(session.hwnd)
        time.sleep(0.3)
        real_click(er)
        time.sleep(0.4)
        if pp.focus_hwnd(eh) == eh:
            ok_focus = True
            break
    if not ok_focus:
        return False, "name edit focus failed"
    mdu._send_keys([(0x11, False), (0x41, False), (0x41, True),
                    (0x11, True)])
    time.sleep(0.15)
    mdu._send_keys([(0x2E, False), (0x2E, True)])
    time.sleep(0.2)
    mdu._send_chars(PRESET_NAME)
    time.sleep(0.4)
    rr, _rh = dialog_child_exact(dlg, "User Preset")
    if rr:
        real_click(rr)
        time.sleep(0.5)
        print(f"{LOG} 'User Preset' radio clicked")
    okr, _okh = dialog_child_exact(dlg, "OK")
    if not okr:
        return False, "no OK button"
    real_click(okr)
    time.sleep(3.0)
    return True, "saved"


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()
    datadir = Path(args.datadir)
    pjson = datadir / "user" / "default" / "process" / f"{PRESET_NAME}.json"

    results = {}
    session, ok_cube = boot_cube_session(args)
    try:
        results["fixture deleted + standard model added"] = "PASS" if ok_cube else "FAIL"
        if results["fixture deleted + standard model added"] != "PASS":
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # dirty the config (m5b's proven positional path)
        pp.ensure_advanced(session, want=True)
        tab_ok = pp.click_tab(session, "Quality", "height")
        hit = pp.wait_float_edit(session)
        ok_dirty = False
        if tab_ok and hit:
            r, h, old = hit
            new = pp.real_edit_set(session, r, h, "0.3")
            pp.neutralize_focus(session)
            ok_dirty = bool(new and new.startswith("0.3"))
        time.sleep(6.0)
        print(f"{LOG} dirty layer height 0.3: {ok_dirty}")
        results["config dirtied (layer height 0.3)"] = (
            "PASS" if ok_dirty else "FAIL")

        ok_save, detail = save_user_preset(session)
        print(f"{LOG} save: {ok_save} ({detail})")
        results["save as user preset"] = "PASS" if ok_save else "FAIL"
        file_saved = pjson.exists()
        print(f"{LOG} preset json exists: {file_saved} ({pjson.name})")
        results["preset json in datadir"] = "PASS" if file_saved else "FAIL"
        row_txt = preset_row_text(session)
        print(f"{LOG} preset row text: {row_txt!r}")
        results["combo shows new preset"] = (
            "PASS" if row_txt and PRESET_NAME in row_txt else "FAIL")
        if not (ok_save and file_saved):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- RESTART on the SAME datadir (no reseed): persistence.
        # MEASURED 09-02 run 1: a MODEL-LESS restart boots with no printer
        # selected and the process list filtered down to 'Default Setting'
        # (PITFALLS #2 state) — the user preset is invisible. Reloading the
        # fixture 3mf re-establishes the U1 (0.8 nozzle) context. ---
        session.close()
        print(f"{LOG} closed for restart")
        time.sleep(3.0)
        session = boot_session(args, model=MIXED_3MF, fresh=False)
        pp.relocate_wizard(session, log=LOG)
        ok_model, _frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} restart fixture loaded: {ok_model}")
        row_txt = preset_row_text(session)
        print(f"{LOG} after restart, preset row: {row_txt!r}")
        persisted = bool(row_txt and PRESET_NAME in row_txt)
        if not persisted:
            # the 3mf restores ITS embedded preset — open the popup and
            # pick the user preset row
            combo = None
            py = pp.process_row_y(session)
            for t, c, r, h, lx, ly in pp.kids(session):
                if c == "wxWindowNR" and t.strip() \
                        and pp.user32.IsWindowVisible(h) \
                        and py + 8 <= ly <= py + 70 and 20 <= lx <= 340 \
                        and (r[2] - r[0]) > 80:
                    combo = r
                    break
            if combo:
                cx, cy = (combo[0] + combo[2]) // 2, (combo[1] + combo[3]) // 2
                winutil.msg_click_screen(cx, cy, session.hwnd)
                time.sleep(1.2)
            popup, pr = None, None
            for _ in range(10):
                for t2, ptxt, pr2, h2 in mixing_util.toplevel(session.pid):
                    if t2 == "wxWindowNR" and ptxt == "panel":
                        popup, pr = h2, pr2
                        break
                if popup:
                    break
                time.sleep(0.4)
            if popup:
                # MEASURED 09-02 runs 3-4: the popup opens scrolled AT the
                # selected system preset; wheel-DOWN is a no-op there (list
                # already at bottom) and TYPE-AHEAD closes the popup
                # without selecting. The user preset sits in the rows ABOVE
                # (Default Setting / user section precede the system rows)
                # — wheel-UP first, verified by OCR after each nudge.
                import numpy as np

                def popup_words():
                    w, hgt, bgra = winutil.capture_window(popup)
                    img = np.frombuffer(bgra, np.uint8).reshape(
                        hgt, w, 4)[:, :, :3]
                    try:
                        cv2.imwrite(str(HERE / "artifacts" /
                                        f"m5g_popup_{tag}.png"), img[:, :, ::-1])
                    except Exception:
                        pass
                    # psm 6: the section-header '-----' art makes the
                    # default psm 3 DROP the user-preset rows (measured
                    # 09-02; the capture shows them, OCR skipped them)
                    return mdu.ocr_words_img(img, scale=3, psm=6)

                def wheel_popup(notches_down):
                    px, py2 = (pr[0] + pr[2]) // 2, (pr[1] + pr[3]) // 2
                    winutil.user32.SetCursorPos(px, py2)
                    time.sleep(0.2)
                    for _n in range(abs(notches_down)):
                        ev = winutil._INPUT()
                        ev.type = 0
                        ev.value.dx = 0
                        ev.value.dy = 0
                        ev.value.mouseData = ((-120 if notches_down > 0
                                               else 120) & 0xFFFFFFFF)
                        ev.value.dwFlags = 0x0800  # MOUSEEVENTF_WHEEL
                        winutil.user32.SendInput(
                            1, ctypes.byref(ev),
                            ctypes.sizeof(winutil._INPUT))
                        time.sleep(0.15)
                    time.sleep(0.8)

                clicked = False
                for tag, act in (("r0", None), ("r1up", 3), ("r2up", 3),
                                 ("r3down", -4)):
                    words = popup_words()
                    print(f"{LOG} popup rows [{tag}]: "
                          f"{' | '.join(t for t, *_ in words)[:200]!r}")
                    for t_w, x, y, w_w, w_h in words:
                        if "flow" in t_w.lower():
                            winutil.msg_click_screen(pr[0] + x + w_w // 2,
                                                     pr[1] + y + w_h // 2)
                            clicked = True
                            break
                    if clicked:
                        break
                    if act is None:
                        continue  # baseline capture, then try the wheels
                    wheel_popup(act)
                time.sleep(2.0)
            row_txt = preset_row_text(session)
            print(f"{LOG} preset row after pick: {row_txt!r}")
            # fresh determination for this branch: the pre-pick row showed
            # the project-embedded preset, so `persisted` starts False and
            # ANDing it would erase the pick's success (measured 09-02)
            persisted = bool(row_txt and PRESET_NAME in row_txt)
        results["preset survives restart"] = "PASS" if persisted else "FAIL"
        results["preset json survives restart"] = (
            "PASS" if pjson.exists() else "FAIL")

        # --- DELETE: the cross appears for a selected user preset ---
        r, h, tip = find_button_by_tooltip(session, "delete")
        deleted = False
        if h:
            known = pp.top_dialog_set(session)
            real_click(r)
            dlg, title = wait_new_dialog(session, known)
            print(f"{LOG} delete confirm dialog: {title!r}")
            if dlg:
                body = pp.dialog_body(session.pid, dlg)
                print(f"{LOG} confirm body: {body[:120]!r}")
                yesr, _yh = dialog_child_exact(dlg, "Yes")
                if not yesr:
                    from harness import mix_dialog_util as _mdu2
                    hit_y = mixing_util.child_by_text(dlg, "Yes")
                    yesr = hit_y[2] if hit_y else None
                if yesr:
                    real_click(yesr)
                    time.sleep(3.0)
                    deleted = True
        print(f"{LOG} deleted flow done: {deleted}")
        results["delete confirm drives"] = "PASS" if deleted else "FAIL"
        time.sleep(4.0)
        results["preset json removed"] = (
            "PASS" if not pjson.exists() else "FAIL")
        row_txt = preset_row_text(session)
        print(f"{LOG} preset row after delete: {row_txt!r}")
        results["combo falls back from deleted"] = (
            "PASS" if row_txt is not None
            and PRESET_NAME not in row_txt else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
