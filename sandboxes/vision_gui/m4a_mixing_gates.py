#!/usr/bin/env python3
# m4a_mixing_gates.py — batch-dialog ('Color Mixing Match') entry gates by
# PHYSICAL FILAMENT COUNT (表2 records #31, #32, #33, #34, #35).
#
# White-box refs:
#   - Plater.cpp:2557-2576 — the m_btn_batch_match handler gates on
#     project 'filament_colour' size: <2 -> RichMessageDialog 'Color Mixing
#     Match is unavailable when only one filament is added to Filament
#     Management.' (caption 'Color Mixing Match', 'Got it' OK) and NO
#     batch dialog. (The no-model half of the same gate is m3o, #28.)
#   - Plater.cpp:3083-3110 — the 'Filaments' title row hosts THREE icon
#     buttons left->right: sync_filament, delete_filament ('Remove last
#     filament', HIDDEN at <=1 filament), add_filament ('Add one
#     filament', right-most). del -> Sidebar::delete_filament(size_t(-1))
#     (Plater.cpp:8408): a Warning confirm pops ONLY when dependent mixed
#     filaments exist (:8432-8471) — this case's fixture has NONE.
#   - Plater.cpp:6583-6591 — Sidebar::update_color_mix_panel hides the
#     'Color Mixing' row when n_physical < 2.
#   - MixedFilamentBatchDialog.cpp:309-313 — the Manual-mode filament
#     count defaults to min(4, n_physical), floored at 2.
#   - MixedFilamentBatchDialog.cpp:1826-1849 — Cancel pops the 'Discard
#     Matching' confirm ONLY when a completed match exists; with no match
#     Cancel closes directly (this case never runs a match).
#
# Stale-table notes:
#   - #33 ('>4 耗材弹冲突确认弹窗'): the current build has NO conflict
#     popup — the Manual rows simply CLAMP to 4 (source line above); the
#     dialog opens normally. Asserted as clamping (FEISHU_MAPPING stale
#     row '表2 #34/35').
#   - #35 ('>4 耗材有混色'): shares the same entry gate as #34 with a
#     scheme present. Scope: asserted with the standard 5-filament+scheme
#     fixture. The 6-filament Phase-A state has no scheme (crafted
#     fixture strips mixed_filament_definitions) and re-adding 3
#     filaments + re-crafting a 6-filament-with-scheme fixture is not
#     combinable in one boot, so the literal '>4 AND scheme' matrix cell
#     is covered by the 5-filament+scheme gate (same code path: the gate
#     only counts filament_colour, the scheme plays no part in it —
#     Plater.cpp:2565-2576).
#
# Black-box path (TWO phases, two boots):
#   Phase A — crafted 5-filament fixture with mixed_filament_definitions
#   STRIPPED (fixture_util strip_mixed=True):
#     #31 delete filaments down to 1 via the title-row trash button
#         (observable: numbered chips drop) -> 'Color Mixing' row hidden
#         AND the batch entry pops the 1-filament prompt ('Got it'
#         dismissable) AND the batch dialog does NOT open.
#     #32 add back to 3 -> the entry OPENS the batch dialog -> Manual ->
#         the manual filament card shows 3 rows -> Cancel closes.
#     #33 add to 6 -> entry opens -> Manual rows clamp to 4 -> Cancel.
#   Phase B — standard MIXED_3MF (5 filaments WITH the seeded scheme):
#     #34/#35 the entry opens normally; Cancel closes.

import ctypes
import json
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import fixture_util  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from harness import ocr_util  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import (MIXED_3MF, add_common_args, boot_session,  # noqa: E402
                       ensure_gl_ready, verdict)

user32 = ctypes.WinDLL("user32")

LOG = "[m4a]"


def real_click(rect):
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.2)
    winutil.real_click_screen(x, y)
    time.sleep(0.8)


def _rows_band(session):
    """(top, bottom, x0) of the sidebar physical-filament rows band:
    between the 'Filaments' title bar and the 'Color Mixing' title bar
    (or +180px when that row is hidden at 1 filament — Plater.cpp:6585)."""
    frow = mdu._sidebar_title_row(session, "Filaments")
    if not frow:
        return None
    top = frow[0][3] + 2
    x0 = frow[0][0] - 20
    crow = mdu._sidebar_title_row(session, "Color Mixing")
    bottom = (crow[0][1] - 2) if crow else top + 180
    return top, bottom, x0


def count_chips(session):
    """Numbered slot chips: 'Button' children with DIGIT text inside the
    rows band (measured: each 2-column slot = digit Button + material
    combo; distinct digit values = physical count)."""
    band = _rows_band(session)
    if not band:
        return 0
    top, bottom, x0 = band
    nums = set()
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c == "Button" and t.strip().isdigit() \
                and user32.IsWindowVisible(h) \
                and top <= r[1] <= bottom and x0 <= r[0] <= x0 + 400:
            nums.add(int(t.strip()))
    return len(nums)


def count_combos(session):
    """Material-name combos: wxWindowNR children with preset text
    ('Snapmaker PLA Silk' / 'Generic PETG' — no '@', measured) inside
    the rows band."""
    band = _rows_band(session)
    if not band:
        return 0
    top, bottom, x0 = band
    seen = set()
    for t, c, r, h in mixing_util.children(session.hwnd):
        if c == "wxWindowNR" and t.strip() and "@" not in t \
                and user32.IsWindowVisible(h) \
                and top <= r[1] <= bottom and x0 <= r[0] <= x0 + 400 \
                and 100 <= r[2] - r[0] <= 200:
            seen.add((r[0], r[1]))
    return len(seen)


COUNT_FN = None


def calibrate_counter(session, expect):
    """Pick the physical-count observable that reads the known fixture
    count at boot."""
    global COUNT_FN
    chips = count_chips(session)
    combos = count_combos(session)
    print(f"{LOG} counter calibration: chips={chips} combos={combos} "
          f"(expect {expect})")
    COUNT_FN = count_chips if chips == expect else count_combos
    return COUNT_FN(session)


def count_physical(session):
    """Primary calibrated counter; on a 0 reading fall back to the other
    counter, then to the del-button state (the trash is HIDDEN at <= 1
    filament — Plater.cpp:4102-4108 — which pins the 1-filament state
    when the combo rebuild blurs the band)."""
    n = COUNT_FN(session) if COUNT_FN else count_chips(session)
    if n == 0:
        alt = count_combos(session) if COUNT_FN is count_chips \
            else count_chips(session)
        if alt:
            return alt
        if len(mdu.filament_row_buttons(session)) == 2:
            return 1
    return n


def wait_count(session, want, timeout_s=10.0):
    """Poll until the physical count reaches `want`; returns last count."""
    deadline = time.monotonic() + timeout_s
    last = -1
    while time.monotonic() < deadline:
        last = count_physical(session)
        if last == want:
            return last
        time.sleep(0.5)
    return last


def trash_click(session):
    """Click the 'Remove last filament' trash — the MIDDLE of the three
    Filaments-row buttons (sync, del, add left->right, Plater.cpp:3104-
    3110; add is the right-most). Re-enumerates every call."""
    btns = mdu.filament_row_buttons(session)
    if len(btns) < 2:
        return False
    real_click(btns[-2][0])
    return True


def add_click(session):
    """Click the right-most Filaments-row button ('Add one filament')."""
    btns = mdu.filament_row_buttons(session)
    if not btns:
        return False
    real_click(btns[-1][0])
    return True


def dismiss_warning(session, timeout_s=2.0):
    """Dismiss a popped Warning/RichMessageDialog (OK / 'Got it')."""
    warn = mixing_util.wait_warning_dialog(session.pid, 0,
                                           timeout_s=timeout_s)
    if warn:
        mixing_util.dismiss_dialog(session.pid, warn)
        time.sleep(1.0)
    return warn


def delete_to(session, want, steps):
    """Click the trash until the count reaches `want` (max `steps`)."""
    for i in range(steps):
        cur = count_physical(session)
        if cur <= want:
            return True
        trash_click(session)
        got = wait_count(session, cur - 1, timeout_s=8.0)
        if got != cur - 1:
            dismiss_warning(session)
            got = wait_count(session, cur - 1, timeout_s=4.0)
        print(f"{LOG} delete step {i + 1}: {cur} -> {got}")
        if got != cur - 1:
            return False
    return count_physical(session) == want


def add_to(session, want, steps):
    for i in range(steps):
        cur = count_physical(session)
        if cur >= want:
            return True
        add_click(session)
        got = wait_count(session, cur + 1, timeout_s=8.0)
        print(f"{LOG} add step {i + 1}: {cur} -> {got}")
        if got != cur + 1:
            return False
    return count_physical(session) == want


def entry_click_once(session):
    """ONE message-click on the batch entry (the button at the right end
    of the 'Color Mixing Match' bar, Plater.cpp:2546/:2967). A single
    click: when the gate pops a modal prompt the owner frame is disabled
    and further probe clicks would be swallowed anyway."""
    frect = winutil.window_rect(session.hwnd)
    for t, c, r, h in mixing_util.children(session.hwnd):
        if t == "Color Mixing Match" and 0 < r[3] - r[1] < 40 \
                and frect[1] < r[3] < frect[3] \
                and user32.IsWindowVisible(h):
            x, y = r[2] - 16, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(x, y)
            time.sleep(0.2)
            winutil.msg_click_screen(x, y, session.hwnd)
            time.sleep(1.0)
            return True
    return False


def wait_batch_outcome(session, timeout_s=8.0):
    """('dialog', hwnd) for the batch dialog, ('prompt', hwnd) for a
    gated RichMessageDialog, (None, None) on timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, rect, hwnd in mixing_util.toplevel(session.pid):
            if cls != "#32770":
                continue
            h = rect[3] - rect[1]
            if "Color Mixing Match" in txt and h > 300:
                return "dialog", hwnd
            if h < 300:
                return "prompt", hwnd
        time.sleep(0.3)
    return None, None


def dismiss_all_prompts(session, timeout_s=3.0):
    n = 0
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        warn = mixing_util.wait_warning_dialog(session.pid, 0,
                                               timeout_s=1.0)
        if not warn:
            break
        mixing_util.dismiss_dialog(session.pid, warn)
        n += 1
        time.sleep(1.0)
    return n


def open_batch_dialog(session, timeout_s=10.0):
    """Entry click -> the batch dialog (not a gate prompt)."""
    if not entry_click_once(session):
        return None
    kind, hwnd = wait_batch_outcome(session, timeout_s=timeout_s)
    if kind == "prompt":
        print(f"{LOG} gate prompt popped (unexpected here)")
        dismiss_all_prompts(session)
        return None
    return hwnd if kind == "dialog" else None


def close_batch_dialog(session, dlg):
    """Cancel closes; with no completed match no 'Discard Matching'
    confirm appears (MixedFilamentBatchDialog.cpp:1826) — tolerate one
    anyway."""
    if not mixing_util.click_button(dlg, "Cancel"):
        print(f"{LOG} cancel button not found")
    time.sleep(1.5)
    cfm = mixing_util.wait_warning_dialog(session.pid, dlg,
                                          timeout_s=3.0)
    if cfm:
        print(f"{LOG} cancel confirm popped; clicking Discard")
        hit = mixing_util.child_by_text(cfm, "Discard")
        if hit:
            r = hit[2]
            winutil.real_click_screen((r[0] + r[2]) // 2,
                                      (r[1] + r[3]) // 2)
        time.sleep(2.0)
    for _ in range(6):
        if mixing_util.find_dialog(session.pid, timeout_s=1.0) is None:
            return True
        mixing_util.click_button(dlg, "Cancel")
        time.sleep(1.5)
    return False


def manual_rows(dlg):
    """The Manual card's filament-selector combos: readonly combobox
    widgets (preset-label text) between the visible 'Filament Setup'
    card title and ~220px below it. Each row = an outer container
    (text 'panel') + an inner text child — dedupe by rect and keep the
    real label. The mode combo ('Auto'/'Manual') is excluded by text;
    the plate/view combos live in the preview card further down.
    Returns -1 when the card title is not found."""
    hit = mdu.find_static(dlg, "Filament Setup")
    if not hit:
        return -1
    ty1 = hit[1][3]
    rows = {}
    for t, c, r, h in mixing_util.children(dlg):
        if c not in ("ComboBox", "wxWindowNR") or not t.strip():
            continue
        if not user32.IsWindowVisible(h):
            continue
        txt = t.strip()
        if txt == "panel" or txt in ("Auto", "Manual"):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (140 <= w <= 300 and 22 <= hh <= 40):
            continue
        if ty1 - 8 <= r[1] <= ty1 + 220:
            rows.setdefault((r[0], r[1]), txt)
    print(f"{LOG} manual rows: {list(rows.values())}")
    return len(rows)


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap)
    args = ap.parse_args()
    if not args.model:
        cfg = json.loads(zipfile.ZipFile(MIXED_3MF).read(
            "Metadata/project_settings.config").decode("utf-8"))
        args.model = fixture_util.craft_filaments_fixture(
            fixture_util.ART_FIXTURES / "gates_5_noscheme.3mf",
            cfg["filament_colour"], cfg["filament_type"],
            cfg.get("filament_settings_id"), strip_mixed=True)
        print(f"{LOG} fixture (no scheme): {args.model}")

    results = {}

    # ============================== PHASE A ==============================
    session = boot_session(args, model=args.model)
    try:
        if fixture_util.dismiss_custom_preset_dialog(session, timeout_s=4):
            ensure_gl_ready(session)
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} phase A model loaded: {ok_model}")
        calibrate_counter(session, 5)
        n0 = wait_count(session, 5, timeout_s=15.0)
        print(f"{LOG} phase A physical count: {n0}")
        results["#31 delete to 1: row hidden + one-filament gate"] = "FAIL"
        results["#32 3 filaments: dialog opens, 3 manual rows"] = "FAIL"
        results["#33 6 filaments: dialog opens, rows clamp to 4"] = "FAIL"

        # --- #31: trash-delete 5 -> 1 ---
        ok_del = delete_to(session, 1, steps=4)
        n1 = count_physical(session)
        print(f"{LOG} after deletes: {n1} (del ok={ok_del})")

        hidden = mdu.color_mix_bar(session) is None
        print(f"{LOG} color mixing row hidden at {n1}: {hidden}")

        gated = False
        prompt_text = ""
        dismissed = False
        no_dialog = False
        if entry_click_once(session):
            kind, hwnd = wait_batch_outcome(session)
            print(f"{LOG} entry at 1 filament -> {kind}")
            if kind == "prompt":
                time.sleep(0.5)
                prompt_text = ocr_util.ocr_hwnd(hwnd)
                print(f"{LOG} prompt text: {prompt_text!r}")
                gated = "only one filament" in prompt_text
                dismissed = mixing_util.dismiss_dialog(session.pid, hwnd)
                time.sleep(1.0)
                dismiss_all_prompts(session, timeout_s=2.0)
                no_dialog = mixing_util.find_dialog(
                    session.pid, timeout_s=2.0) is None
        print(f"{LOG} gated={gated} dismissed={dismissed} "
              f"no_dialog={no_dialog}")
        if ok_del and n1 == 1:
            results["#31 delete to 1: row hidden + one-filament gate"] = (
                "PASS" if (hidden and gated and dismissed and no_dialog)
                else "FAIL")

        # --- #32: add back to 3, the dialog opens, Manual rows == 3 ---
        ok_add = add_to(session, 3, steps=2)
        n3 = count_physical(session)
        print(f"{LOG} back to: {n3} (add ok={ok_add})")
        rec32 = False
        if ok_add and n3 == 3:
            dlg = open_batch_dialog(session)
            if dlg:
                switched = mixing_util.switch_match_mode(session, dlg,
                                                         "Manual")
                time.sleep(1.0)
                rows = manual_rows(dlg)
                print(f"{LOG} #32 manual switched={switched} rows={rows}")
                closed = close_batch_dialog(session, dlg)
                rec32 = bool(switched and rows == 3 and closed)
        results["#32 3 filaments: dialog opens, 3 manual rows"] = (
            "PASS" if rec32 else "FAIL")

        # --- #33: add to 6, rows clamp to 4 (STALE: no conflict popup) ---
        ok_add6 = add_to(session, 6, steps=3)
        n6 = count_physical(session)
        print(f"{LOG} grown to: {n6} (add ok={ok_add6})")
        rec33 = False
        if ok_add6 and n6 == 6:
            dlg = open_batch_dialog(session)
            if dlg:
                switched = mixing_util.switch_match_mode(session, dlg,
                                                         "Manual")
                time.sleep(1.0)
                rows = manual_rows(dlg)
                print(f"{LOG} #33 manual switched={switched} rows={rows}")
                closed = close_batch_dialog(session, dlg)
                rec33 = bool(switched and rows == 4 and closed)
        results["#33 6 filaments: dialog opens, rows clamp to 4"] = (
            "PASS" if rec33 else "FAIL")
    finally:
        alive_a = session.alive()
        session.close()
        print(f"{LOG} phase A app closed (was alive: {alive_a})")
        time.sleep(4.0)  # let the OS release the profile log lock

    # ============================== PHASE B ==============================
    args.model = MIXED_3MF
    session = None
    for attempt in range(3):
        try:
            session = boot_session(args, model=args.model)
            break
        except PermissionError as e:
            print(f"{LOG} phase B boot retry {attempt + 1}: {e}")
            time.sleep(6.0)
    if session is None:
        results["app alive"] = "FAIL"
        return verdict(results)
    try:
        results["#34 5 filaments + scheme: entry opens"] = "FAIL"
        results["#35 scheme present: gate does not block"] = "FAIL"
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} phase B model loaded: {ok_model}")
        calibrate_counter(session, 5)
        n = wait_count(session, 5, timeout_s=15.0)
        entries = [(t, r) for t, r, _h in mdu.mix_entry_labels(session)]
        print(f"{LOG} phase B count={n} scheme entries="
              f"{[e[0] for e in entries]}")

        rec34 = False
        dlg = open_batch_dialog(session)
        print(f"{LOG} #34 dialog: {hex(dlg) if dlg else None}")
        rec34 = bool(dlg)
        if dlg:
            rec34 = close_batch_dialog(session, dlg)

        rec35 = False
        if rec34:
            dlg = open_batch_dialog(session)
            print(f"{LOG} #35 dialog reopen: {hex(dlg) if dlg else None}")
            rec35 = bool(dlg)
            if dlg:
                rec35 = close_batch_dialog(session, dlg)
        results["#34 5 filaments + scheme: entry opens"] = (
            "PASS" if rec34 else "FAIL")
        results["#35 scheme present: gate does not block"] = (
            "PASS" if rec35 else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} phase B app closed")


if __name__ == "__main__":
    raise SystemExit(main())
