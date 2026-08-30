#!/usr/bin/env python3
# m4c_mixing_panel.py — the sidebar Color Mixing panel (表1 #45, #48, #42,
# #38): physical rows show material names, the seeded mixing entry renders
# its rule label with an Options menu whose Delete empties the list (empty
# state keeps the add button), a freshly added scheme survives a physical
# filament insertion, the Add Mix dialog reopens with clean defaults, and
# the whole panel HIDES at 1 physical filament.
#
# White-box refs:
#   - Plater.cpp:6577-7025 — update_color_mix_panel renders one Static
#     label per mixed entry ('F%u %d%%+F%u %d%%', :6707) + a 'menu_filament'
#     Options button (:6809) opening a NATIVE wxMenu (#32768) with
#     Edit / Merge with / Delete; the panel title bar hosts the add button
#     (m_btn_add_color_mix, :6470).
#   - Plater.cpp:6583-6591 — panel visibility gate: the 'Color Mixing'
#     title + scrolled content Show(n_physical >= 2).
#   - Plater.cpp:3083-3110 — 'Filaments' title row buttons sync / del
#     ('Remove last filament') / add ('Add one filament'); del hides at
#     <= 1 filament (:4102-4108). Sidebar::delete_filament (:8408) pops a
#     Warning ONLY when dependent mixed filaments exist — #38's
#     delete-to-1 may hit that (the #42 scheme is alive) and the warning
#     is confirmed with OK.
#   - MixedFilamentDialog defaults (:142-144): Add Mix reopens in Ratio
#     mode with 2 rows at 50/50 (m3t asserted the same on first open).
#
# Stale-table / scope notes:
#   - #42 (耗材序号自动更新): the record's core is badge NUMBER renumbering
#     after a physical insertion — the badge numbers are SELF-DRAWN pixels
#     (MixedFilamentBadge), not window text, so renumbering is only
#     partially observable black-box. Asserted instead: the pre-existing
#     entry labels survive unchanged + stay well-formed (regex ^F\d) and
#     the panel keeps rendering them after the insertion.
#   - #45's hover-tooltip sub-item is out of reach (wx GetToolTipText is
#     not exposed cross-process); the label + Options-button row presence
#     is asserted instead.
#
# Black-box path: boot standard fixture -> #45 material rows + seeded
# 'F3 50%+F2 50%' label + Options button on its row -> #48 Options menu
# Delete (real-click row probing, observable = label disappears); empty
# panel still shows the row + enabled add button -> #42 add a scheme
# (compatible pair via popup, OK) then add a physical filament; the entry
# persists -> #38 reopen Add Mix (2 rows, 50/50, Ratio active) -> Cancel;
# trash-delete filaments down to 1 -> the 'Color Mixing' row hides.

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, topbar_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402
from m3u_mixing_ratio_flow import compat_blocked, make_compatible  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[m4c]"
GWL_STYLE = -16
WS_DISABLED = 0x08000000


def real_click(rect):
    x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.2)
    winutil.real_click_screen(x, y)
    time.sleep(0.8)


def entries(session):
    """Sidebar mixing labels (text, rect) sorted top->bottom."""
    out = [(t, r) for t, r, _h in mdu.mix_entry_labels(session)]
    out.sort(key=lambda x: x[1][1])
    return out


def wait_entries_gone(session, timeout_s=6.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not entries(session):
            return True
        time.sleep(0.4)
    return False


def enabled(hwnd):
    return not bool(user32.GetWindowLongW(hwnd, GWL_STYLE) & WS_DISABLED)


def delete_entry_via_menu(session, label_rect, max_attempts=5):
    """Open the entry's Options menu and real-click its 'Delete' row
    (top-level menu row — the modal loop tracks the REAL cursor, so the
    y is probed around the computed position with the label disappearing
    as the observable, like topbar_util.real_click_submenu_row)."""
    btn = mdu.entry_menu_button(session, label_rect)
    if not btn:
        return False
    pid = session.pid

    def open_menu():
        real_click(btn[0])
        menus = topbar_util.wait_menu_popup(pid, timeout_s=4.0)
        if not menus:
            return None
        m = menus[0]
        return (m[:4], m[4], topbar_util.menu_hmenu(m[4]))

    for _attempt in range(max_attempts):
        menu = open_menu()
        if not menu:
            continue
        rect, _hwnd, hmenu = menu
        items = topbar_util.menu_items(hmenu)
        idx = topbar_util.find_item(hmenu, "Delete")
        if idx is None:
            print(f"{LOG} options menu items: {[i[1] for i in items]}")
            topbar_util.close_menu_windows(pid)
            return False
        left, top, right, bottom = rect
        pitch = (bottom - top - 4) / max(len(items), 1)
        base = top + 2 + int((idx + 0.5) * pitch)
        cands = [base + k * 6 for k in range(0, 6)] + \
                [base - k * 6 for k in (1, 2, 3)]
        cx = (left + right) // 2
        for y in cands:
            winutil.user32.SetCursorPos(cx, y)
            time.sleep(0.15)
            winutil.real_click_screen(cx, y)
            deadline = time.monotonic() + 2.5
            while time.monotonic() < deadline:
                if wait_entries_gone(session, timeout_s=0.3):
                    topbar_util.close_menu_windows(pid)
                    return True
                # a probe click may have landed on 'Edit' -> an Edit Mix
                # dialog opened; back out and retry
                edlg = mdu.find_mix_dialog(pid, timeout_s=0.3)
                if edlg:
                    mdu.click_button(session, edlg, "Cancel")
                    time.sleep(1.2)
                    break
            if wait_entries_gone(session, timeout_s=0.3):
                topbar_util.close_menu_windows(pid)
                return True
            topbar_util.close_menu_windows(pid)
            time.sleep(0.8)
            break  # reopen the menu for the next attempt
    return wait_entries_gone(session, timeout_s=1.0)


def count_physical(session):
    return mdu.physical_filament_count_ex(session)


def wait_count(session, want, timeout_s=10.0):
    deadline = time.monotonic() + timeout_s
    last = -1
    while time.monotonic() < deadline:
        last = count_physical(session)
        if last == want:
            return last
        time.sleep(0.5)
    return last


def trash_click(session):
    """The 'Remove last filament' trash: the MIDDLE of the three
    Filaments-row buttons (sync, del, add — Plater.cpp:3104-3110)."""
    btns = mdu.filament_row_buttons(session)
    if len(btns) < 2:
        return False
    real_click(btns[-2][0])
    return True


def add_click(session):
    btns = mdu.filament_row_buttons(session)
    if not btns:
        return False
    real_click(btns[-1][0])
    return True


def dismiss_warning(session, timeout_s=2.0):
    warn = mixing_util.wait_warning_dialog(session.pid, 0,
                                           timeout_s=timeout_s)
    if warn:
        mixing_util.dismiss_dialog(session.pid, warn)
        time.sleep(1.0)
    return warn


def delete_to(session, want, steps):
    for i in range(steps):
        cur = count_physical(session)
        if cur <= want:
            return True
        trash_click(session)
        got = wait_count(session, cur - 1, timeout_s=8.0)
        if got != cur - 1:
            dismiss_warning(session)  # dependent-scheme Warning (OK)
            got = wait_count(session, cur - 1, timeout_s=4.0)
        print(f"{LOG} delete step {i + 1}: {cur} -> {got}")
        if got != cur - 1:
            return False
    return count_physical(session) == want


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model loaded: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"
        if not ok_model:
            return verdict(results)
        time.sleep(2.0)

        # --- #45: material rows + seeded entry label + Options button ---
        mats = [(t, r) for t, r, _h in mdu.filament_material_combos(session)]
        n_phys = len(mats)
        print(f"{LOG} material rows: {mats}")
        named = n_phys >= 1 and any(
            ("PLA" in t or "PETG" in t) for t, _r in mats)
        ents = entries(session)
        print(f"{LOG} mixing entries: {ents}")
        seeded = [e for e in ents if e[0] == "F3 50%+F2 50%"]
        opts = mdu.entry_menu_button(session, seeded[0][1]) if seeded else None
        print(f"{LOG} options button on entry row: {opts}")
        results["#45 material rows + entry label + options button"] = (
            "PASS" if (named and seeded and opts) else "FAIL")

        # --- #48: Options menu Delete -> empty state keeps add usable ---
        deleted = False
        if seeded:
            deleted = delete_entry_via_menu(session, seeded[0][1])
        time.sleep(1.0)
        empty = not entries(session)
        bar = mdu.color_mix_bar(session)
        row_btns = mdu._sidebar_title_row(session, "Color Mixing")
        add_btn = row_btns[1][-1] if row_btns and row_btns[1] else None
        add_ok = bool(add_btn and enabled(add_btn[1]))
        print(f"{LOG} deleted={deleted} empty={empty} bar={bar} "
              f"add_enabled={add_ok} (physical={count_physical(session)})")
        results["#48 menu delete empties list, add stays usable"] = (
            "PASS" if (deleted and empty and bar and add_ok) else "FAIL")

        # --- #42: add a scheme, then a physical filament; entry persists ---
        rec42 = False
        dlg = mdu.open_add_mix_dialog(session)
        if dlg:
            time.sleep(1.0)
            switched = make_compatible(session, dlg)
            ok_en = mdu.ok_enabled(dlg)
            mdu.click_button(session, dlg, "OK")
            time.sleep(2.0)
            gone = mdu.find_mix_dialog(session.pid, timeout_s=3.0) is None
            ents2 = entries(session)
            import re
            wellformed = bool(ents2) and all(
                re.match(r"^F\d[\dF %,+>\-\[\]]*$", e[0]) for e in ents2)
            print(f"{LOG} scheme added: switched={switched} ok={ok_en} "
                  f"gone={gone} entries={[e[0] for e in ents2]}")
            if switched and gone and wellformed and len(ents2) == 1:
                before = [e[0] for e in ents2]
                cur = count_physical(session)
                add_click(session)
                got = wait_count(session, cur + 1, timeout_s=8.0)
                if got != cur + 1:
                    dismiss_warning(session)
                    got = wait_count(session, cur + 1, timeout_s=4.0)
                ents3 = entries(session)
                print(f"{LOG} after physical add: count {cur} -> {got}, "
                      f"entries={[e[0] for e in ents3]}")
                survived = (got == cur + 1
                            and [e[0] for e in ents3] == before)
                rec42 = bool(survived and wellformed)
        results["#42 entry labels persist after filament insertion"] = (
            "PASS" if rec42 else "FAIL")

        # --- #38a: Add Mix reopens with clean defaults ---
        clean = False
        dlg2 = mdu.open_add_mix_dialog(session)
        if dlg2:
            time.sleep(1.0)
            rows = len([1 for t, r, h, vis in mdu.static_texts(dlg2)
                        if vis and t.strip().startswith("Filament ")
                        and t.strip()[9:].isdigit()])
            legs = mdu.legend_pcts(dlg2)
            mode = mdu.active_tab(dlg2)
            print(f"{LOG} reopen defaults: rows={rows} legends={legs} "
                  f"tab={mode}")
            clean = rows == 2 and legs == [50, 50] and mode == "Ratio"
            mdu.click_button(session, dlg2, "Cancel")
            time.sleep(1.5)
            clean = clean and (mdu.find_mix_dialog(
                session.pid, timeout_s=2.0) is None)

        # --- #38b: delete physical filaments to 1 -> panel hides ---
        ok_del = delete_to(session, 1, steps=6)
        n1 = count_physical(session)
        hidden = mdu.color_mix_bar(session) is None
        print(f"{LOG} #38b physical={n1} (del ok={ok_del}) "
              f"color mixing row hidden={hidden}")
        results["#38 clean defaults + panel hides at 1 filament"] = (
            "PASS" if (clean and ok_del and n1 == 1 and hidden) else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
