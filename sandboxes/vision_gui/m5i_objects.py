#!/usr/bin/env python3
# m5i_objects.py — OBJECTS-MODE single-object parameter main flow: flip the
# sidebar Process row Global|Objects switch to Objects, override the
# object's layer height on the per-object Frequent page, slice once, and
# prove the override reached the slicer WITHOUT touching the global config.
#
# White-box refs:
#   - ParamsPanel.cpp:221-223 — the Global|Objects SwitchButton on the
#     Process title row; OnToggled -> set_active_tab(nullptr) ->
#     sidebar().show_object_list(true) (line 570).
#   - Tab.cpp:3418 — TabPrintObject = PrintObjectConfig+PrintRegionConfig
#     keys; Tab.cpp:2942 build() prepends a 'Frequent' page whose first
#     row is layer_height. Edits land in ModelObject::config (Tab.cpp:3131
#     apply_only per object config) — per-object, not the preset.
#   - GCode.cpp:6638 append_full_config echoes print.full_print_config()
#     — the GLOBAL config only: the header '; layer_height' stays 0.4.
#   - GCode.cpp:4730 m_config.apply(layer.object()->config(), true) — the
#     object override IS applied during slicing: a 27mm cube slices to 134
#     layers at 0.2 vs 68 at 0.4 (measured: '; total layer number: 134').
#
# MEASURED 09-02 (diag_m5i_objects, rounds 1-4):
#   - the switch pills are TINY painted text; no single OCR config reads
#     both — scale=4/psm3 reads 'Global', scale=5/psm3 reads 'Objects'
#     (crop anchor row x80..260); a frame-anchored fallback covers misses;
#   - the pill ACTIVE state judges by teal fraction (grey ~0.11-0.19,
#     active ~0.71);
#   - Objects mode REPLACES the preset combo row with a search box +
#     object list (Plate 1 / Cube selected by default after the add /
#     Outside); the per-object tab row (Frequent active) sits ~188px below
#     the Process anchor; pp.options_viewport is None in this mode — the
#     Frequent page is OCR'd in a custom band below the tab row;
#   - the layer-height Edit reports EMPTY window text until committed
#     (painted value); real_edit_set + readback works;
#   - the raw gcode contains 3 'LAYER_CHANGE' tokens per layer — count
#     the LINE-ANCHORED '\n;LAYER_CHANGE' (or the post-processor
#     '; total layer number: N' summary) instead.
#
# Black-box path: boot EMPTY -> Add Primitive > Cube -> flip Objects (teal)
# -> Frequent tab present -> layer height 0.2 (object-level) -> slice +
# export -> header '; layer_height = 0.4' (global intact) AND total layers
# >= 95 (the 0.2 override reached the slicer) -> flip back Global (preset
# combo returns '0.40 Standard ...', Objects pill grey) -> app alive.
# Stale-table notes: none (Objects mode was previously untested).

import ctypes
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import gcode_check  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from harness import winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (add_common_args, export_and_check,  # noqa: E402
                       slice_and_wait, verdict)

LOG = "[m5i]"
user32 = ctypes.WinDLL("user32")


def ocr_region(session, x0, y0, x1, y1, psm=6, scale=3):
    img = capture_bgr(session)
    words = mdu.ocr_words_img(img[y0:y1, x0:x1], scale=scale, psm=psm)
    return [(w, x + x0, y + y0, ww, wh) for w, x, y, ww, wh in words]


def click_word(session, words, seq):
    """SCREEN point of the first consecutive word SEQUENCE match."""
    n = len(seq)
    for i in range(len(words) - n + 1):
        got = [w.lower() for w, *_ in words[i:i + n]]
        if got == [s.lower() for s in seq]:
            x0, y0, _, wh = words[i][1], words[i][2], words[i][3], words[i][4]
            x1 = words[i + n - 1][1] + words[i + n - 1][3]
            return pp.client(session, (x0 + x1) // 2, y0 + wh // 2)
    return None


def teal_frac(session, rect):
    """Fraction of strongly-chromatic pixels in a client rect — the switch
    paints the ACTIVE label as a teal pill (grey 0.11-0.19 / active 0.71,
    measured 09-02)."""
    img = capture_bgr(session)
    x0, y0, x1, y1 = rect
    sub = img[y0:y1, x0:x1].astype(int)
    if sub.size == 0:
        return -1.0
    spread = sub.max(axis=2) - sub.min(axis=2)
    return float((spread > 40).mean())


def mode_pill_words(session, py):
    """Locate the Global|Objects pills on the Process anchor row.
    MEASURED: scale=4/psm3 OCRs 'Global', scale=5/psm3 OCRs 'Objects',
    never both — union both passes; frame-anchored fallback rectangles
    (x106..139 / x150..191, py-2..py+16) when OCR misses."""
    words = ocr_region(session, 80, max(0, py - 12), 260, py + 20,
                       psm=3, scale=4)
    words += ocr_region(session, 80, max(0, py - 12), 260, py + 20,
                        psm=3, scale=5)
    for name, x0, x1 in (("global", 15, 62), ("objects", 66, 122)):
        if not any(w.lower() == name for w, *_ in words):
            words.append((name, x0, py - 2, x1 - x0, 18))
    print(f"{LOG} mode pills: "
          f"{' | '.join(f'{w}@{x},{y}' for w, x, y, *_ in words)}")
    return words


def pill_rect(words, name):
    for w, x, y, ww, wh in words:
        if w.lower() == name:
            return (x - 6, y - 6, x + ww + 6, y + wh + 6)
    return None


def frequent_tab(session):
    """(rect, hwnd) of the per-object 'Frequent' tab kid, or None."""
    for t, c, r, h, lx, ly in pp.kids(session):
        if c == "wxWindowNR" and t.strip() == "Frequent" \
                and pp.user32.IsWindowVisible(h):
            return r, h
    return None


def set_object_layer_height(session, tab_y, text):
    """OCR the Frequent page band below the tab row, find the Layer height
    row, type `text` into its Edit. Returns (ok, readback). MEASURED: the
    Edit reports empty window text until committed — the readback after
    the set is the judge."""
    img = capture_bgr(session)
    band = ocr_region(session, 0, tab_y + 25, pp.SB_W,
                      min(img.shape[0], tab_y + 190))
    print(f"{LOG} frequent band: "
          f"{' | '.join(f'{w}@{x},{y}' for w, x, y, *_ in band)}")
    y_row = None
    for w, x, y, ww, wh in band:
        if w.lower() == "height":
            y_row = y + wh // 2
            break
    if y_row is None:
        return False, None
    hit = pp.option_edit_at(session, y_row)
    print(f"{LOG} layer row y={y_row} edit={hit[0] if hit else None}")
    if not hit:
        return False, None
    r, h = hit
    new = pp.real_edit_set(session, r, h, text)
    pp.neutralize_focus(session)
    time.sleep(6.0)  # settle the page rebuild (m5b mechanic)
    return bool(new and new.startswith(text)), new


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

        py = pp.process_row_y(session)
        words = mode_pill_words(session, py)
        obj_rect = pill_rect(words, "objects")
        g_rect = pill_rect(words, "global")

        # --- flip to Objects; judge by the teal highlight migrating ---
        teal_before = teal_frac(session, obj_rect) if obj_rect else -1
        pt = click_word(session, words, ("objects",))
        print(f"{LOG} objects pill point: {pt} teal_before={teal_before:.3f}")
        flipped = False
        if pt:
            winutil.user32.SetCursorPos(*pt)
            time.sleep(0.2)
            winutil.real_click_screen(*pt)
            time.sleep(2.5)
        teal_after = teal_frac(session, obj_rect) if obj_rect else -1
        print(f"{LOG} objects pill teal {teal_before:.3f} -> {teal_after:.3f}")
        flipped = 0 <= teal_before < 0.45 and teal_after > 0.45
        results["global->objects switch flips"] = (
            "PASS" if flipped else "FAIL")

        # --- per-object tab row present (Frequent active) ---
        tab = frequent_tab(session)
        print(f"{LOG} frequent tab: {tab[0] if tab else None}")
        results["per-object Frequent tab appears"] = (
            "PASS" if tab else "FAIL")
        if not (flipped and tab):
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # best-effort: click the Cube row (selected by default after the
        # add; the click is a no-op safety) — row sits ~108px above the
        # tab row, mid-sidebar (frame-measured 09-02)
        cx, _cy = pp.client(session, 150, tab[0][1] - 108)
        winutil.user32.SetCursorPos(cx, _cy)
        time.sleep(0.2)
        winutil.real_click_screen(cx, _cy)
        time.sleep(1.5)

        ok_set, new = set_object_layer_height(session, tab[0][1], "0.2")
        print(f"{LOG} object layer height set: {ok_set} readback={new!r}")
        results["object layer height 0.2 committed"] = (
            "PASS" if ok_set else "FAIL")
        cv2.imwrite(str(HERE / "artifacts" / "m5i_committed.png"),
                    capture_bgr(session))
        if not ok_set:
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- slice + export; the override shows in the layer COUNT, not
        # the header echo (which stays global 0.4) ---
        sliced = slice_and_wait(session, timeout_s=900)
        out_path = Path(args.datadir).parent / "m5i_objects.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        lh = gcode_check.config_value(data, "layer_height") if ok_exp else None
        n_layers = -1
        if ok_exp:
            m = gcode_check.config_value(data, "total layer number")
            if m and m.isdigit():
                n_layers = int(m)
            else:
                n_layers = data.count(b"\n;LAYER_CHANGE")
        print(f"{LOG} slice={sliced} export={ok_exp} header={lh!r} "
              f"layers={n_layers}")
        results["slice + export"] = (
            "PASS" if (sliced and ok_exp) else "FAIL")
        results["gcode header keeps global 0.4"] = (
            "PASS" if lh is not None and lh.startswith("0.4") else "FAIL")
        # 27mm cube: 134 layers at 0.2 vs 68 at 0.4 (measured)
        results["object override reached slicer (>=95 layers)"] = (
            "PASS" if n_layers >= 95 else "FAIL")

        # --- flip back to Global: the preset combo row returns ---
        words2 = mode_pill_words(session, py)
        pt = click_word(session, words2, ("global",))
        back = False
        if pt:
            winutil.user32.SetCursorPos(*pt)
            time.sleep(0.2)
            winutil.real_click_screen(*pt)
            time.sleep(2.5)
        _r, _h, txt = pp.find_process_preset_combo(session)
        teal_end = teal_frac(session, obj_rect) if obj_rect else -1
        print(f"{LOG} back to global: combo={txt!r} objects teal={teal_end:.3f}")
        back = bool(txt and "0.40" in txt) and 0 <= teal_end < 0.45
        results["objects->global restores preset row"] = (
            "PASS" if back else "FAIL")

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
