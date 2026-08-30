#!/usr/bin/env python3
# m4h_mixing_templates.py — the 0.1mm Color Mixing process TEMPLATE and the
# nozzle-compat counterpart (表2 #37 / #38 / #39 / #44).
#
# White-box refs:
#   - resources/profiles/Snapmaker/process/'0.10mm Color Mixing @Snapmaker
#     U1 (0.4 Nozzle).json' — the 0.1mm mixing process template EXISTS only
#     for the 0.4 nozzle (no 0.8 variant is installed; verified by ls).
#   - resources/profiles/Snapmaker/machine/'Snapmaker U1 (0.4 nozzle).json'
#     vs base 'Snapmaker U1' — printer variants carry fixed nozzle_diameter
#     lists; the seeded fixture embeds the base U1 (0.8-nozzle config).
#   - MixedFilamentBatchDialog.cpp:2287-2292 — Auto-mode Start Matching
#     gates on full_spectrum_preset_exists_for_current_nozzle()
#     (MixedColorMatchHelpers.cpp:624 'Snapmaker PLA Full Spectrum @U1 ',
#     installed for 0.2/0.4/0.6 nozzles only): on the 0.8 nozzle it pops
#     'Automatic color mixing matching is not supported for the current
#     nozzle diameter...' (#49, m3j), on 0.4 it must NOT.
#   - DEVIATION notes:
#     * #37/#38/#39: the batch dialog has NO process-template combo
#       (source-verified: its only combos are the mode combo, 4 manual
#       filament rows, plate and view — grep 08-30). The process template
#       picker is the sidebar Process panel preset combo (the
#       m3e_preset_switch widget). #37/#39 are asserted there; #38's 'info
#       icon' is covered by the bounded hover probe on the preset-row icons
#       + combo (tooltips are the only hover text this row offers).
#     * printer switching: the sidebar printer combo popup offers ONLY the
#       base machine + wizard entries ('Select/Remove printers', 'Create
#       printer' — PresetComboBoxes.cpp:1325-1329 hides printer presets
#       that are not visible/compatible; the U1 nozzle variants are not
#       listed). The 0.4-nozzle state is therefore produced the same way a
#       user project would: a crafted copy of the fixture whose embedded
#       project carries printer_settings_id 'Snapmaker U1 (0.4 nozzle)',
#       printer_variant 0.4 and nozzle_diameter 0.4x4 (the
#       fixture_util crafting pattern used by m4a). Phase B boots the
#       standard 0.8 fixture.
#
# Black-box path (TWO phases):
#   Phase A — boot the crafted 0.4-nozzle variant of the standard fixture
#   (printer combo text confirms '(0.4 nozzle)') -> #37 open the Process
#   preset combo popup, OCR rows: a '0.10mm Color Mixing' row exists;
#   real-click it; combo text confirms -> #38 bounded hover probe on the
#   preset-row icons/combo -> tooltip OCR -> #44 open the batch dialog,
#   Start Matching in Auto: NO gate dialog, matching completes (swatch band
#   renders) -> #39 switch the template to a different preset: no confirm
#   dialog in the current build (stale table); assert the switch applied
#   via the combo text.
#   Phase B — fresh boot on the standard 0.8 fixture: the process dropdown
#   offers NO 0.10 mixing template and batch-dialog Auto -> Start Matching
#   gates with the nozzle warning (the 0.8 counterpart of #44).

import ctypes
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pytesseract

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import fixture_util  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, ocr_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[m4h]"

ART_FIXTURES = HERE / "artifacts" / "fixtures"


def craft_04_fixture(dest):
    """Copy MIXED_3MF with the embedded project switched to the 0.4-nozzle
    U1 variant (printer preset / variant / nozzle_diameter / process
    preset / compatible printers). Filament preset ids keep their 0.8
    names — exact-name lookups that exist in the shipped library."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    zin = zipfile.ZipFile(MIXED_3MF)
    cfg = json.loads(zin.read("Metadata/project_settings.config")
                     .decode("utf-8"))
    cfg["printer_settings_id"] = "Snapmaker U1 (0.4 nozzle)"
    cfg["printer_variant"] = "0.4"
    cfg["nozzle_diameter"] = ["0.4", "0.4", "0.4", "0.4"]
    cfg["print_settings_id"] = "0.20 Standard @Snapmaker U1 (0.4 nozzle)"
    cfg["print_compatible_printers"] = ["Snapmaker U1 (0.4 nozzle)"]
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "Metadata/project_settings.config":
                zout.writestr(item, json.dumps(cfg, indent=4))
            else:
                zout.writestr(item, zin.read(item.filename))
    zin.close()
    return dest


def frect(session):
    return winutil.window_rect(session.hwnd)


def kids(session):
    out = []
    for t, c, r, h in mixing_util.children(session.hwnd):
        lx = r[0] - frect(session)[0]
        ly = r[1] - frect(session)[1]
        out.append((t, c, r, h, lx, ly))
    return out


def find_printer_combo(session):
    """The sidebar printer preset combo: wxWindowNR whose text is the
    printer preset name (no '@' suffix, no process template prefix)."""
    cands = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "wxWindowNR" or not t.strip():
            continue
        txt = t.strip()
        if "@" in txt or txt == "panel":
            continue
        if not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (120 <= w <= 340 and 18 <= hh <= 40):
            continue
        if ly > 320:  # printer section is at the sidebar top
            continue
        if "Snapmaker U1" in txt or "Snapmaker" in txt:
            cands.append((txt, r, h))
    cands.sort(key=lambda x: x[1][1])
    return cands[0] if cands else None


def combo_text(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def open_combo_popup(session, crect, timeout_s=5.0):
    """Open a sidebar combo (message-level click like m3e) and return
    (popup_rect, popup_hwnd) ('panel', combo-width) or None."""
    known = set(h for _c, _t, _r, h in mixing_util.toplevel(session.pid))
    cx, cy = (crect[0] + crect[2]) // 2, (crect[1] + crect[3]) // 2
    winutil.msg_click_screen(cx, cy, session.hwnd)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "wxWindowNR" and txt == "panel" and h not in known:
                return r, h
        time.sleep(0.2)
    return None


def ocr_words_psm6(img, scale=3):
    """ocr_words_img with psm 6 — the SectionedCombo popups render thin
    separator rows that defeat the default page segmentation."""
    big = mdu.cv2_resize(img, scale)
    data = pytesseract.image_to_data(big, config="-l eng --psm 6",
                                     output_type=pytesseract.Output.DICT)
    words = []
    for i, txt in enumerate(data["text"]):
        t = txt.strip()
        if not t or int(data["conf"][i]) < 40:
            continue
        words.append((t, data["left"][i] // scale, data["top"][i] // scale,
                      data["width"][i] // scale, data["height"][i] // scale))
    return words


def popup_rows(popup_rect, popup_hwnd):
    """OCR the self-drawn popup; returns [(text, y_center_screen)] rows
    (words grouped into lines by y). Falls back to psm 6."""
    w, h, bgra = winutil.capture_window(popup_hwnd)
    img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)[:, :, :3]
    words = mdu.ocr_words_img(img[:, :, ::-1].copy(), scale=3)
    if not words:
        words = ocr_words_psm6(img[:, :, ::-1].copy(), scale=3)
    lines = {}
    for t, x, y, ww, hh in words:
        key = (y + hh // 2) // 14
        lines.setdefault(key, []).append((t, x, y, ww, hh))
    rows = []
    for key in sorted(lines):
        ws = sorted(lines[key], key=lambda z: z[1])
        text = " ".join(z[0] for z in ws)
        ymid = sum(z[2] + z[3] // 2 for z in ws) // len(ws)
        rows.append((text, popup_rect[1] + ymid))
    return rows


def real_click_xy(x, y):
    winutil.user32.SetCursorPos(x, y)
    time.sleep(0.2)
    winutil.real_click_screen(x, y)
    time.sleep(0.8)


def find_process_combo(session):
    """The Process panel preset combo (m3e's widget): '@Snapmaker U1' text
    in the process band."""
    for t, c, r, h, lx, ly in kids(session):
        if c == "wxWindowNR" and "@Snapmaker U1" in t \
                and user32.IsWindowVisible(h) \
                and 615 <= ly <= 700 and lx < 430:
            return t.strip(), r, h
    return None


def drain_dialogs(session, timeout_s=4.0):
    n = 0
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        hit = None
        for cls, txt, r, h in mixing_util.toplevel(session.pid):
            if cls == "#32770" and (r[3] - r[1]) < 300:
                hit = h
                break
        if not hit:
            break
        body = " ".join(t for t, c, r, h in mixing_util.children(hit)
                        if t.strip() and c == "Static")
        print(f"{LOG} dialog drained: {body[:90]!r}")
        mixing_util.dismiss_dialog(session.pid, hit)
        n += 1
        time.sleep(1.0)
    return n


def hover_probe(session, rects, dwell_s=3.0):
    """Hover each rect (real moves) and return the first OCR-readable
    tooltip text."""
    for rect in rects:
        x = (rect[0] + rect[2]) // 2
        y = (rect[1] + rect[3]) // 2
        deadline = time.monotonic() + dwell_s
        while time.monotonic() < deadline:
            winutil.user32.SetCursorPos(x, y)
            time.sleep(0.4)
            tt = mixing_util.wait_tooltip(session.pid, timeout_s=1.0)
            if tt:
                time.sleep(0.8)
                text = ocr_util.ocr_hwnd(tt[1])
                if text.strip():
                    return text.strip()
        time.sleep(0.5)
    return None


def preset_row_icons(session):
    """Small icon buttons right of the Process preset combo (save, search)
    as screen rects."""
    hit = find_process_combo(session)
    if not hit:
        return []
    _t, crect, _h = hit
    y0, y1 = crect[1], crect[3]
    out = []
    for t, c, r, h, lx, ly in kids(session):
        if c != "Button" or not user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (12 <= w <= 34 and 12 <= hh <= 34):
            continue
        if y0 - 6 <= r[1] <= y1 + 6 and lx >= crect[2] - frect(session)[0]:
            out.append(r)
    out.sort(key=lambda r: r[0])
    return out


def batch_auto_match(session, expect_gate):
    """Open the batch dialog, Start Matching in Auto. expect_gate=True:
    assert the nozzle gate pops and dismiss it. expect_gate=False: assert
    NO gate and wait for the match to complete. Returns (ok, note)."""
    dlg = mixing_util.open_mixing_dialog(session)
    if not dlg:
        return False, "batch dialog did not open"
    time.sleep(1.0)
    ok_start = mixing_util.click_button(dlg, "Start Matching")
    warn = mixing_util.wait_warning_dialog(session.pid, dlg, timeout_s=8.0)
    if expect_gate:
        if not (ok_start and warn):
            return False, "expected gate did not pop"
        body = " ".join(t for t, c, r, h in mixing_util.children(warn)
                        if t.strip() and c == "Static")
        if not body:
            body = ocr_util.ocr_hwnd(warn)
        print(f"{LOG} gate text: {body[:120]!r}")
        mixing_util.dismiss_dialog(session.pid, warn)
        time.sleep(1.0)
        mixing_util.close_batch_dialog(session, dlg)
        return ("not supported for the current nozzle diameter" in body), body
    if warn:
        body = " ".join(t for t, c, r, h in mixing_util.children(warn)
                        if t.strip() and c == "Static")
        print(f"{LOG} UNEXPECTED gate: {body[:120]!r}")
        mixing_util.dismiss_dialog(session.pid, warn)
        time.sleep(1.0)
        mixing_util.close_batch_dialog(session, dlg)
        return False, "gate popped on 0.4"
    done = mixing_util.wait_match_done(session, dlg, timeout_s=150.0)
    print(f"{LOG} auto matching done: {done}")
    closed = mixing_util.close_batch_dialog(session, dlg)
    return bool(done and closed), f"done={done} closed={closed}"


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()
    if not args.model or str(args.model) == str(MIXED_3MF):
        args.model = craft_04_fixture(ART_FIXTURES / "m4h_04variant.3mf")
        print(f"{LOG} phase A fixture (0.4 variant): {args.model}")

    results = {}
    session = boot_session(args, model=args.model)
    try:
        fixture_util.dismiss_custom_preset_dialog(session, timeout_s=6)
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} model loaded: {ok_model}")
        results["multicolor project loads"] = "PASS" if ok_model else "FAIL"
        if not ok_model:
            return verdict(results)
        time.sleep(2.0)
        drain_dialogs(session, timeout_s=3.0)

        # --- the project boots as the 0.4-nozzle U1 variant. NOTE: the
        #     sidebar printer combo displays the BASE machine name
        #     ('Snapmaker U1') even for a variant project; the PROCESS
        #     preset carries the nozzle suffix and is the observable. ---
        pr = find_printer_combo(session)
        print(f"{LOG} printer combo: {pr and (pr[0], pr[1])}")
        pc = find_process_combo(session)
        print(f"{LOG} process combo: {pc and (pc[0], pc[1])}")
        is04 = bool(pc and "(0.4 nozzle)" in pc[0])
        results["project loads as 0.4-nozzle U1 variant"] = (
            "PASS" if is04 else "FAIL")
        if not is04:
            return verdict(results)

        # --- #37: the process template combo offers the 0.10mm mixing
        #     template on the 0.4 nozzle ---
        pc = find_process_combo(session)
        print(f"{LOG} process combo: {pc and (pc[0], pc[1])}")
        rec37 = False
        row_text = ""
        if pc:
            ptxt, crect, ch = pc
            pop = open_combo_popup(session, crect)
            if pop:
                prect, phwnd = pop
                time.sleep(0.6)
                rows = popup_rows(prect, phwnd)
                print(f"{LOG} process popup rows({ptxt!r}): "
                      f"{[r[0] for r in rows]}")
                # long entries WRAP across two OCR line groups ('0.10mm
                # Color' / 'Mixing @Snapmaker...'), so presence is checked
                # on the joined text and the click targets the '0.10' line
                joined = " ".join(r[0] for r in rows)
                target = next((r for r in rows if "0.10" in r[0]), None)
                if target and "mix" in joined.lower() \
                        and "0.10" in joined:
                    row_text = target[0]
                    real_click_xy((prect[0] + prect[2]) // 2, target[1])
                    time.sleep(2.0)
                    newtxt = combo_text(ch)
                    print(f"{LOG} template selected -> {newtxt!r}")
                    rec37 = "0.10" in newtxt
                else:
                    mdu.popup_cancel(session)
            drain_dialogs(session, timeout_s=2.0)
        results["#37 0.10mm Color Mixing template in 0.4 dropdown"] = (
            "PASS" if rec37 else "FAIL")

        # --- #38: bounded hover probe on the preset-row icons + combo ---
        tip = hover_probe(session, preset_row_icons(session)
                          + ([pc[1]] if pc else []))
        print(f"{LOG} preset row tooltip: {tip!r}")
        results["#38 template row hover tooltip"] = (
            "PASS" if tip and len(tip) >= 3 else "FAIL")

        # --- #44 (0.4): Auto Start Matching must NOT gate ---
        ok44, note44 = batch_auto_match(session, expect_gate=False)
        print(f"{LOG} #44 0.4 auto: {ok44} ({note44})")
        results["#44 0.4 nozzle: Auto match runs (no gate)"] = (
            "PASS" if ok44 else "FAIL")

        # --- #39: switching the template pops no confirm dialog in the
        #     current build; assert the switch applied via the combo text ---
        rec39 = False
        pc2 = find_process_combo(session)
        if pc2:
            ptxt, crect, ch = pc2
            pop = open_combo_popup(session, crect)
            if pop:
                prect, phwnd = pop
                time.sleep(0.6)
                rows = popup_rows(prect, phwnd)
                other = next((r for r in rows if "0.10" not in r[0]
                              and "Standard" in r[0]), None)
                if other:
                    known = set(h for _c, _t, _r, h
                                in mixing_util.toplevel(session.pid))
                    real_click_xy((prect[0] + prect[2]) // 2, other[1])
                    time.sleep(2.0)
                    confirm = None
                    for cls, txt, r, h in mixing_util.toplevel(session.pid):
                        if cls == "#32770" and h not in known \
                                and (r[3] - r[1]) < 300:
                            confirm = h
                            break
                    if confirm:
                        print(f"{LOG} confirm dialog popped (unexpected)")
                        drain_dialogs(session, timeout_s=2.0)
                    newtxt = combo_text(ch)
                    switched = "0.10" not in newtxt
                    print(f"{LOG} #39 switched to {newtxt!r} "
                          f"confirm={confirm is not None}")
                    rec39 = switched and confirm is None
                else:
                    mdu.popup_cancel(session)
        results["#39 template switch applies (no confirm dialog)"] = (
            "PASS" if rec39 else "FAIL")

        results["app alive (phase A)"] = "PASS" if session.alive() else "FAIL"
    finally:
        alive_a = session.alive()
        session.close()
        print(f"{LOG} phase A app closed (was alive: {alive_a})")
        time.sleep(4.0)  # release the profile log lock

    # ==================== PHASE B: the 0.8 nozzle gate ====================
    session = None
    for attempt in range(3):
        try:
            session = boot_session(args, model=MIXED_3MF)
            break
        except PermissionError as e:
            print(f"{LOG} phase B boot retry {attempt + 1}: {e}")
            time.sleep(6.0)
    if session is None:
        results["#44 0.8 nozzle: Auto gates (no 0.4 template)"] = "FAIL"
        return verdict(results)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=240)
        print(f"{LOG} phase B model loaded: {ok_model}")
        time.sleep(2.0)
        pc = find_process_combo(session)
        has_template = False
        if pc:
            ptxt, crect, _ch = pc
            print(f"{LOG} phase B process combo: {ptxt!r}")
            pop = open_combo_popup(session, crect)
            if pop:
                prect, phwnd = pop
                time.sleep(0.6)
                rows = popup_rows(prect, phwnd)
                print(f"{LOG} phase B popup rows: {[r[0] for r in rows]}")
                has_template = ("0.10" in " ".join(r[0] for r in rows)
                                and "mix" in " ".join(
                                    r[0] for r in rows).lower())
                mdu.popup_cancel(session)
        print(f"{LOG} phase B 0.8 dropdown has 0.10 mixing template: "
              f"{has_template}")
        results["#44 0.8 process dropdown: no 0.10 mixing template"] = (
            "PASS" if not has_template else "FAIL")

        ok_gate, note = batch_auto_match(session, expect_gate=True)
        print(f"{LOG} #44 0.8 gate: {ok_gate} ({note[:80]})")
        results["#44 0.8 nozzle: Auto gates (no 0.4 template)"] = (
            "PASS" if ok_gate else "FAIL")
        results["app alive (phase B)"] = (
            "PASS" if session.alive() else "FAIL")
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} phase B app closed")


if __name__ == "__main__":
    raise SystemExit(main())
