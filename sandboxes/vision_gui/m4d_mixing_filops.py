#!/usr/bin/env python3
# m4d_mixing_filops.py — physical-filament operations against mixing state
# (表1 #47 delete boundaries + #46 merge): the Filaments-row trash deletes
# the LAST filament; a delete with NO dependent scheme is SILENT while the
# seeded scheme survives; a scheme registered on the current last filament
# arms the 'Warning' confirm — Cancel keeps everything, OK cascades the
# dependent scheme away; deleting down to 1 filament hides the Color Mixing
# panel AND the trash; and a mixing entry's Options menu offers Edit /
# Merge with / Delete, where merging the entry into a PHYSICAL filament
# removes the entry and leaves the physical set untouched.
#
# White-box refs:
#   - Plater.cpp:3083-3110 — 'Filaments' title row buttons sync / del
#     ('Remove last filament' = trash) / add ('Add one filament'); the
#     trash deletes the LAST filament (Sidebar::delete_filament(size_t(-1)),
#     Plater.cpp:8408) and is HIDDEN at <= 1 filament (:3122, :4102-4108).
#   - Plater.cpp:8443-8473 — deleting a filament referenced by mixing
#     schemes pops a MessageDialog titled 'Warning' ('This filament is used
#     in the following mixed filament configurations: ... Continue?')
#     OK/Cancel; Cancel aborts, OK cascades (PresetBundle
#     update_num_filaments removes dependent mixed entries).
#   - Plater.cpp:6583-6591 — the 'Color Mixing' panel hides at
#     n_physical < 2.
#   - Plater.cpp:6809/:6817-6942 — a mixing entry renders an Options
#     button opening a native wxMenu (#32768) with Edit / Merge with /
#     Delete; the 'Merge with' submenu lists other physical filaments by
#     preset label and mixed targets as 'Mixed Filament %d'.
#   - Plater.cpp:8335-8413 — merging a MIXED entry into a PHYSICAL target
#     marks the source deleted and remaps painted objects.
#
# Scope / stale-table notes:
#   - 表1 #47/#46 match the current build (no stale rows in
#     FEISHU_MAPPING.md for these records).
#   - #47b registers the scheme on the CURRENT last filament (id derived
#     from the live count after #47a, i.e. F4, not a literal table id); the
#     row-2 popup is driven by index and self-verified through the
#     registered sidebar label (popup rows share the preset label text).
#   - #46 asserts the mixed->physical merge (the deterministic path); the
#     physical->physical variant shares the same change_filament machinery
#     and is noted out of scope; the physical->mixed guard dialog is NOT
#     exercised.
#
# Black-box path: boot standard fixture (5 filaments + seeded
# 'F3 50%+F2 50%') -> #47a trash: 5->4, NO dialog, seeded label survives ->
# #47b Add Mix: row 1 popup to a PLA, row 2 popup toward the last id, OK ->
# new entry whose label cites the last id -> trash: 'Warning' names the
# mixed configs -> Cancel: count 4 and both schemes intact -> trash again,
# OK: count 3, new scheme cascaded away, seeded survives -> #47c trash
# (warning, OK) to 2 (seeded cascades), trash to 1: 'Color Mixing' row
# hidden + trash hidden -> PHASE 2 (fresh boot): register a second scheme,
# Options menu item asserts, hover 'Merge with', submenu lists physicals +
# 'Mixed Filament %d', merge into a physical: entry gone, physical count
# unchanged, app alive.

import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import fixture_util  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, topbar_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import (MIXED_3MF, add_common_args, boot_session,  # noqa: E402
                       verdict)
from m3u_mixing_ratio_flow import compat_blocked, make_compatible  # noqa: E402

LOG = "[m4d]"
WARN_KEY = "used in the following mixed filament configurations"


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
    Filaments-row buttons (sync, del, add — Plater.cpp:3104-3110); the
    right-most is '+'. Re-enumerated fresh every call."""
    btns = mdu.filament_row_buttons(session)
    if len(btns) < 2:
        return False
    real_click(btns[-2][0])
    return True


def wait_warning(pid, timeout_s=8.0):
    return mixing_util.wait_warning_dialog(pid, 0, timeout_s=timeout_s)


def drain_warnings(session, timeout_s=2.0):
    n = 0
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        warn = wait_warning(session.pid, timeout_s=0.8)
        if not warn:
            break
        mixing_util.dismiss_dialog(session.pid, warn)
        n += 1
        time.sleep(0.8)
    return n


def warning_info(pid, warn):
    """(title, body) of a popped MessageDialog: top-level title + Static
    children; OCR fallback for the body (native dialogs may paint text)."""
    title = ""
    for cls, txt, rect, hwnd in mixing_util.toplevel(pid):
        if hwnd == warn:
            title = txt
    body = " ".join(t for t, c, r, h in mixing_util.children(warn)
                    if t.strip() and c == "Static")
    if WARN_KEY not in body:
        from harness import ocr_util
        try:
            body += " " + ocr_util.ocr_hwnd(warn)
        except Exception:
            pass
    return title, body


def register_scheme_on_last(session, n_last, max_picks=(2, 1, 0)):
    """Open Add Mix, make the pair PLA (make_compatible), drive row 2's
    popup toward the LAST filament id, OK, and verify through the
    registered sidebar label (popup rows cannot be told apart by text —
    all PLAs share the preset label). Wrong picks are deleted again via
    the entry Options menu. Returns (True, new_text, new_rect) or
    (False, None, None)."""
    base = entries(session)
    base_labels = [e[0] for e in base]
    for pop_idx in max_picks:
        dlg = mdu.open_add_mix_dialog(session)
        if not dlg:
            break
        time.sleep(1.0)
        if not make_compatible(session, dlg):
            mdu.click_button(session, dlg, "Cancel")
            time.sleep(1.0)
            continue
        picked = mdu.pick_popup_index(session, dlg, 1, pop_idx)
        combos = mdu.filament_combos(dlg)
        row2 = combos[1][0] if len(combos) > 1 else ""
        blocked = compat_blocked(dlg)
        ok_en = mdu.ok_enabled(dlg)
        print(f"{LOG} add-mix pop_idx={pop_idx}: picked={picked} "
              f"row2={row2!r} blocked={blocked} ok={ok_en} "
              f"legends={mdu.legend_pcts(dlg)}")
        if not picked or blocked or not ok_en:
            mdu.click_button(session, dlg, "Cancel")
            time.sleep(1.0)
            continue
        mdu.click_button(session, dlg, "OK")
        time.sleep(2.0)
        if mdu.find_mix_dialog(session.pid, timeout_s=2.0) is not None:
            mdu.click_button(session, dlg, "Cancel")
            time.sleep(1.0)
            continue
        ents = entries(session)
        if len(ents) != len(base) + 1:
            print(f"{LOG} registration did not add an entry: "
                  f"{[e[0] for e in ents]}")
            continue
        fresh = [e for e in ents if e[0] not in base_labels]
        new_text, new_rect = fresh[0] if fresh else ents[-1]
        ids = set(re.findall(r"F(\d+)", new_text))
        print(f"{LOG} registered {new_text!r} ids={sorted(ids)} "
              f"(want F{n_last})")
        if str(n_last) in ids:
            return True, new_text, new_rect
        mdu.menu_delete_entry(session, new_rect)
        time.sleep(1.5)
    return False, None, None


def merge_entry_into_physical(session, label_rect, max_attempts=3):
    """Options menu -> hover 'Merge with' -> real-click the first PHYSICAL
    target of the submenu (observable = the entry at label_rect is gone).
    A probe landing on a mixed target pops the component-use guard dialog;
    it is read, dismissed and the merge retried."""
    pid = session.pid

    def gone():
        return not any(abs(r[1] - label_rect[1]) < 6
                       for _t, r, _h in mdu.mix_entry_labels(session))

    for attempt in range(max_attempts):
        # real ESC: dismiss any menu a previous attempt left hovering
        # (WM_CANCELMODE alone is not enough once a submenu was open)
        mdu._send_keys([(0x1B, False), (0x1B, True)])
        time.sleep(0.5)
        menu = mdu.entry_options_menu(session, label_rect)
        if not menu:
            print(f"{LOG} merge: options menu did not open "
                  f"(attempt {attempt + 1})")
            continue
        rect, mhwnd, hmenu, items = menu
        sub_idx = topbar_util.find_item(hmenu, "Merge with")
        if sub_idx is None:
            print(f"{LOG} merge: no 'Merge with' in "
                  f"{[i[1] for i in items]}")
            mdu.close_entry_menu(session)
            return False
        topbar_util.hover_row(rect, len(items), sub_idx)
        sub = topbar_util.wait_submenu(pid, {mhwnd}, timeout_s=5.0)
        if not sub:
            mdu.close_entry_menu(session)
            continue
        srect, _shwnd, shmenu = sub
        sub_items = topbar_util.menu_items(shmenu)
        print(f"{LOG} merge submenu: {[i[1] for i in sub_items]}")
        phys = [i for i in sub_items
                if "mixed filament" not in i[1].lower()]
        if not phys:
            mdu.close_entry_menu(session)
            return False
        row_idx = topbar_util.find_item(shmenu, phys[0][1])
        left, top, right, _b = srect
        cx = (left + right) // 2
        guard = None
        for yy in topbar_util.submenu_row_candidates(srect, len(sub_items),
                                                     row_idx):
            winutil.user32.SetCursorPos(cx, yy)
            time.sleep(0.15)
            winutil.real_click_screen(cx, yy)
            deadline = time.monotonic() + 6.0
            while time.monotonic() < deadline:
                if gone():
                    mdu.close_entry_menu(session)
                    return True
                g = wait_warning(pid, timeout_s=0.3)
                if g:
                    guard = g
                    break
                time.sleep(0.4)
            if guard or gone():
                break
        mdu.close_entry_menu(session)
        if guard:
            gtitle, gbody = warning_info(pid, guard)
            print(f"{LOG} merge guard dialog: {gtitle!r} {gbody[:120]!r}")
            mixing_util.click_button(guard, "OK")
            time.sleep(1.5)
        time.sleep(1.0)
    return gone()


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} phase 1 model loaded: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"
        if not ok_model:
            return verdict(results)
        time.sleep(2.0)

        seeded_label = "F3 50%+F2 50%"
        n0 = wait_count(session, 5, timeout_s=15.0)
        ents0 = entries(session)
        print(f"{LOG} boot: physical={n0} entries={[e[0] for e in ents0]}")
        results["seeded state (5 filaments, 1 scheme)"] = (
            "PASS" if (n0 == 5 and ents0
                       and ents0[0][0] == seeded_label) else "FAIL")

        # --- #47a: trash the LAST filament (unreferenced) -> no confirm ---
        clicked = trash_click(session)
        n4 = wait_count(session, 4, timeout_s=8.0)
        late = wait_warning(session.pid, timeout_s=2.0)
        drain_warnings(session, timeout_s=1.0)
        ents1 = entries(session)
        survived = ents1 and any(e[0] == seeded_label for e in ents1)
        print(f"{LOG} #47a clicked={clicked} count={n4} "
              f"late_warning={late is not None} entries="
              f"{[e[0] for e in ents1]}")
        results["#47a trash last: silent, scheme survives"] = (
            "PASS" if (clicked and n4 == 4 and late is None and survived)
            else "FAIL")
        if n4 != 4:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- #47b: register a scheme on the CURRENT last filament (F4) ---
        n_last = count_physical(session)
        reg, new_text, new_rect = register_scheme_on_last(session, n_last)
        print(f"{LOG} #47b registered={reg} label={new_text!r}")
        results["#47b scheme on last filament registers"] = (
            "PASS" if reg else "FAIL")
        if not reg:
            results["#47b cancel keeps count and schemes"] = "FAIL"
            results["#47b confirm cascades scheme"] = "FAIL"
            results["#47c at 1: panel hidden, trash hidden"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- #47b: trash -> Warning names the mixed configs -> Cancel ---
        trash_click(session)
        warn = wait_warning(session.pid, timeout_s=8.0)
        still = count_physical(session)
        wtitle, wbody = warning_info(session.pid, warn) if warn \
            else ("", "")
        print(f"{LOG} #47b warning: {wtitle!r} count_still={still} "
              f"body={wbody[:160]!r}")
        results["#47b trash arms 'Warning' confirm"] = (
            "PASS" if (warn is not None and still == 4
                       and "warning" in wtitle.lower()
                       and WARN_KEY in wbody) else "FAIL")

        cancel_ok = mixing_util.click_button(warn, "Cancel") if warn \
            else False
        time.sleep(1.5)
        drain_warnings(session, timeout_s=1.0)
        cnt = wait_count(session, 4, timeout_s=6.0)
        ents2 = entries(session)
        labels2 = [e[0] for e in ents2]
        kept = (cnt == 4 and len(ents2) == 2
                and seeded_label in labels2 and new_text in labels2)
        print(f"{LOG} #47b after Cancel: clicked={cancel_ok} count={cnt} "
              f"entries={labels2}")
        results["#47b cancel keeps count and schemes"] = (
            "PASS" if (cancel_ok and kept) else "FAIL")

        # --- #47b: trash again -> OK -> cascade removes the new scheme ---
        trash_click(session)
        warn2 = wait_warning(session.pid, timeout_s=8.0)
        ok_ok = mixing_util.click_button(warn2, "OK") if warn2 else False
        n3 = wait_count(session, 3, timeout_s=8.0)
        ents3 = entries(session)
        labels3 = [e[0] for e in ents3]
        cascaded = (warn2 is not None and ok_ok and n3 == 3
                    and seeded_label in labels3 and new_text not in labels3
                    and len(ents3) == 1)
        print(f"{LOG} #47b after OK: clicked={ok_ok} count={n3} "
              f"entries={labels3}")
        results["#47b confirm cascades scheme, seeded survives"] = (
            "PASS" if cascaded else "FAIL")

        # --- #47c: delete down to 1 -> panel hidden + trash hidden ---
        trash_click(session)
        warn3 = wait_warning(session.pid, timeout_s=6.0)  # F3 referenced
        if warn3:
            mixing_util.click_button(warn3, "OK")
        n2 = wait_count(session, 2, timeout_s=8.0)
        ents_empty = not entries(session)
        print(f"{LOG} #47c to 2: warning={warn3 is not None} count={n2} "
              f"entries empty={ents_empty}")

        trash_click(session)
        n1 = wait_count(session, 1, timeout_s=8.0)
        late2 = wait_warning(session.pid, timeout_s=2.0)
        drain_warnings(session, timeout_s=1.0)
        panel_hidden = mdu.color_mix_bar(session) is None
        btns = mdu.filament_row_buttons(session)
        trash_hidden = len(btns) == 2  # sync + add only
        print(f"{LOG} #47c to 1: count={n1} late_warning="
              f"{late2 is not None} panel_hidden={panel_hidden} "
              f"row_buttons={len(btns)} trash_hidden={trash_hidden}")
        results["#47c at 1: panel hidden, trash hidden"] = (
            "PASS" if (n1 == 1 and late2 is None and panel_hidden
                       and trash_hidden) else "FAIL")
    finally:
        alive1 = session.alive()
        session.close()
        print(f"{LOG} phase 1 app closed (was alive: {alive1})")
        time.sleep(4.0)  # let the OS release the profile log lock

    # ==================== PHASE 2: #46 merge (fresh boot) ================
    session = None
    for attempt in range(3):
        try:
            session = boot_session(args, model=MIXED_3MF)
            break
        except PermissionError as e:
            print(f"{LOG} phase 2 boot retry {attempt + 1}: {e}")
            time.sleep(6.0)
    if session is None:
        results["#46 options menu (Edit/Merge with/Delete + targets)"] = \
            "FAIL"
        results["#46 merge mixed->physical"] = "FAIL"
        results["app alive"] = "FAIL"
        return verdict(results)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} phase 2 model loaded: {ok_model}")
        time.sleep(2.0)
        n5 = wait_count(session, 5, timeout_s=15.0)
        base = entries(session)
        print(f"{LOG} phase 2 boot: count={n5} "
              f"entries={[e[0] for e in base]}")

        # register a second scheme (distinct label: row2 popup -> last PLA)
        reg2 = False
        if ok_model and n5 == 5 and base:
            dlg = mdu.open_add_mix_dialog(session)
            if dlg:
                time.sleep(1.0)
                switched = make_compatible(session, dlg)
                mdu.pick_popup_index(session, dlg, 1, 2)  # row2 -> last PLA
                blocked = compat_blocked(dlg)
                ok_en = mdu.ok_enabled(dlg)
                print(f"{LOG} #46 second scheme: switched={switched} "
                      f"blocked={blocked} ok={ok_en} "
                      f"legends={mdu.legend_pcts(dlg)}")
                if switched and not blocked and ok_en:
                    mdu.click_button(session, dlg, "OK")
                    time.sleep(2.0)
                    reg2 = (mdu.find_mix_dialog(
                        session.pid, timeout_s=2.0) is None)
        ents = entries(session)
        labels = [e[0] for e in ents]
        distinct = len(set(labels)) == len(labels)
        print(f"{LOG} #46 entries now: {labels} registered={reg2}")

        menu_ok = sub_ok = False
        merged = False
        if ents:
            target_text, target_rect = ents[-1]
            n_phys_before = count_physical(session)
            menu = mdu.entry_options_menu(session, target_rect)
            if menu:
                rect, mhwnd, hmenu, items = menu
                names = [i[1] for i in items]
                print(f"{LOG} #46 options menu items: {names}")
                menu_ok = all(
                    topbar_util.find_item(hmenu, k) is not None
                    for k in ("Edit", "Merge with", "Delete"))
                sub_idx = topbar_util.find_item(hmenu, "Merge with")
                if menu_ok and sub_idx is not None:
                    topbar_util.hover_row(rect, len(items), sub_idx)
                    sub = topbar_util.wait_submenu(session.pid, {mhwnd},
                                                   timeout_s=5.0)
                    if sub:
                        srect, _sh, shmenu = sub
                        sub_items = topbar_util.menu_items(shmenu)
                        has_mixed = any("mixed filament" in i[1].lower()
                                        for i in sub_items)
                        has_phys = any("mixed filament" not in i[1].lower()
                                       for i in sub_items)
                        sub_ok = bool(has_mixed and has_phys)
                        print(f"{LOG} #46 submenu targets: "
                              f"{[i[1] for i in sub_items]} "
                              f"mixed={has_mixed} physical={has_phys}")
                # MEASURED 09-02: WM_CANCELMODE cannot dismiss a menu whose
                # SUBMENU was hovered open — the menu stayed up and every
                # merge re-open click landed on the floating menu (RED x2
                # in the 35-case regression). The menu modal loop only
                # obeys REAL input (m3b precedent): real ESC x2 closes the
                # submenu and the main menu.
                mdu._send_keys([(0x1B, False), (0x1B, True)])
                time.sleep(0.4)
                mdu._send_keys([(0x1B, False), (0x1B, True)])
                time.sleep(0.6)
                mdu.close_entry_menu(session)
                time.sleep(0.8)
            if menu_ok and sub_ok:
                merged = merge_entry_into_physical(session, target_rect)
                time.sleep(1.5)
                ents_after = entries(session)
                labels_after = [e[0] for e in ents_after]
                n_phys_after = count_physical(session)
                merged = bool(
                    merged and len(ents_after) == len(ents) - 1
                    and n_phys_after == n_phys_before
                    and target_text not in labels_after
                    and (not distinct or labels_after == [seeded_label]))
                print(f"{LOG} #46 after merge: entries={labels_after} "
                      f"physical {n_phys_before} -> {n_phys_after}")
        results["#46 options menu (Edit/Merge with/Delete + targets)"] = (
            "PASS" if (menu_ok and sub_ok) else "FAIL")
        results["#46 merge mixed->physical"] = (
            "PASS" if merged else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} phase 2 app closed")


if __name__ == "__main__":
    raise SystemExit(main())
