#!/usr/bin/env python3
# m6c_discard.py — DIRTY-PRESET switch confirm main flow: dirty the layer
# height, switch the process preset, drive the 'Transfer or discard
# changes' dialog both ways (Discard commits the switch and reloads the
# preset values; closing the dialog aborts and keeps the dirty value).
#
# White-box refs:
#   - Tab.cpp:5511 / :5796 — switching a preset while the current one is
#     dirty calls may_discard_current_dirty_preset -> UnsavedChangesDialog.
#   - UnsavedChangesDialog.cpp:804-811 — the dialog title is 'Transfer or
#     discard changes'; :1002-1007 the buttons are PAINTED ('Transfer' /
#     'Discard' / 'Save' — find by TEXT, m5g precedent: class-filtered
#     searches find nothing); :1425 the action line reads 'You have
#     changed some settings of preset "X".'; the diff table lists
#     Settings / Old value / New Value rows.
#   - closing the dialog (WM_CLOSE -> wxID_CANCEL) aborts the switch
#     (ShowModal returns wxID_CANCEL -> return false).
#
# MEASURED 09-02 (diag_m6c_discard):
#   - the dialog is a #32770 titled 'Transfer or discard changes'; its
#     child Statics carry the action line + diff rows ('Layer height',
#     '0.4') as REAL text (no OCR needed);
#   - 'Discard' click -> preset combo '0.24 Standard @Snapmaker U1
#     (0.8 nozzle)', Quality field reloads to 0.24;
#   - WM_CLOSE on the dialog -> combo '* 0.24 Standard ...' (the '*'
#     dirty marker prefixes the combo text) and the field KEEPS the
#     dirty 0.3;
#   - a msg-click timeout warning during switch_process_preset
#     (SendMessageTimeoutW 0x202) is benign — the switch proceeds.
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> Quality layer
# height 0.3 (dirty) -> switch preset to 0.24 -> dialog appears (title +
# action-line Static + 'Layer height' diff row) -> 'Discard' -> combo +
# field 0.24 -> dirty 0.3 again -> switch to 0.32 -> dialog -> WM_CLOSE ->
# combo stays 0.24 (dirty-starred) + field stays 0.3 -> app alive.
# Stale-table notes: none (the discard confirm was previously untested).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util  # noqa: E402
from harness import winutil  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import add_common_args, verdict  # noqa: E402

LOG = "[m6c]"


def top_dialog(session, known, title_substr, timeout_s=8.0):
    """First NEW #32770 whose title contains `title_substr`."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "#32770" and h not in known \
                    and title_substr.lower() in txt.lower():
                return h, txt
        time.sleep(0.3)
    return None, None


def dialog_static(session, dlg, substr):
    """First visible child Static whose text contains `substr`."""
    for t, c, r, h in mixing_util.children(dlg):
        if c == "Static" and substr.lower() in t.lower() \
                and pp.user32.IsWindowVisible(h):
            return t.strip()
    return None


def click_dialog_text(session, dlg, text):
    """m5g mechanic: painted dialog buttons — find by EXACT text."""
    for t, c, r, h in mixing_util.children(dlg):
        if t.strip() == text and pp.user32.IsWindowVisible(h):
            x, y = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(x, y)
            time.sleep(0.2)
            winutil.real_click_screen(x, y)
            time.sleep(1.5)
            return True
    return False


def dirty_layer_height(session, text="0.3"):
    """Quality page topmost float Edit -> type `text`. Returns readback."""
    pp.ensure_advanced(session, want=True)
    if not pp.click_tab(session, "Quality", "height"):
        return None
    hit = pp.wait_float_edit(session)
    if not hit:
        return None
    new = pp.real_edit_set(session, hit[0], hit[1], text)
    pp.neutralize_focus(session)
    time.sleep(4.0)
    return new


def read_layer_height(session, tries=6):
    for _ in range(tries):
        eds = pp.float_edits_in_view(session)
        if eds:
            return eds[0][2]
        time.sleep(1.0)
    return None


def preset_combo_text(session):
    return pp.find_process_preset_combo(session)[2]


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    results = {}
    session, ok_cube = boot_cube_session(args)
    try:
        results["fixture deleted + standard model added"] = (
            "PASS" if ok_cube else "FAIL")
        if not ok_cube:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- dirty 0.3 on the 0.40 preset, then switch to 0.24 ---
        new = dirty_layer_height(session, "0.3")
        print(f"{LOG} dirty 0.3: {new!r} field={read_layer_height(session)!r}")
        results["config dirtied (layer height 0.3)"] = (
            "PASS" if new and new.startswith("0.3") else "FAIL")

        known = pp.top_dialog_set(session)
        pp.switch_process_preset(session, "0.24", tries=2)
        dlg, title = top_dialog(session, known, "discard changes")
        print(f"{LOG} confirm dialog: {title!r}")
        results["dirty switch pops confirm dialog"] = (
            "PASS" if dlg else "FAIL")
        if not dlg:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        action = dialog_static(session, dlg, "changed some settings")
        diffrow = dialog_static(session, dlg, "Layer height")
        print(f"{LOG} action line: {action!r}")
        print(f"{LOG} diff row present: {bool(diffrow)}")
        results["dialog lists preset + changed option"] = (
            "PASS" if action and diffrow else "FAIL")

        clicked = click_dialog_text(session, dlg, "Discard")
        if not clicked:
            clicked = click_dialog_text(session, dlg, "Don't save")
        print(f"{LOG} discard clicked: {clicked}")
        time.sleep(4.0)
        combo = preset_combo_text(session)
        field = read_layer_height(session)
        print(f"{LOG} after discard: combo={combo!r} field={field!r}")
        results["discard switches preset"] = (
            "PASS" if clicked and combo and "0.24" in combo else "FAIL")
        results["discard reloads preset value 0.24"] = (
            "PASS" if field and field.startswith("0.24") else "FAIL")

        # --- dirty again, switch to 0.32, CANCEL via WM_CLOSE ---
        new = dirty_layer_height(session, "0.3")
        print(f"{LOG} re-dirty 0.3: {new!r}")
        known = pp.top_dialog_set(session)
        pp.switch_process_preset(session, "0.32", tries=2)
        dlg2, title2 = top_dialog(session, known, "discard changes")
        print(f"{LOG} second confirm dialog: {title2!r}")
        results["second dirty switch pops dialog"] = (
            "PASS" if dlg2 else "FAIL")
        if not dlg2:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)
        # WM_CLOSE == wxID_CANCEL == abort (UnsavedChangesDialog.ShowModal)
        winutil.close_window(dlg2)
        time.sleep(3.0)
        combo = preset_combo_text(session)
        field = read_layer_height(session)
        print(f"{LOG} after cancel: combo={combo!r} field={field!r}")
        results["cancel aborts the switch"] = (
            "PASS" if combo and "0.24" in combo and "0.32" not in combo
            else "FAIL")
        results["cancel keeps the dirty 0.3"] = (
            "PASS" if field and field.startswith("0.3") else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
