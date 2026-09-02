#!/usr/bin/env python3
# diag_m5i_objects.py — empirical recon for the m5i OBJECTS-MODE flow.
# Answers, with log + frame evidence:
#   1. where the Global|Objects SwitchButton paints on the Process title
#      row (self-drawn, OCR is the only handle);
#   2. what the sidebar shows after flipping to Objects (object list? which
#      HWND classes? does the preset row / tab row survive?);
#   3. how the Cube row is located/selected in the object list and whether
#      the per-object tab (Frequent page) activates;
#   4. whether layer_height edits land on the object (Edit text + commit);
#   5. what the exported gcode shows for a per-object override: the header
#      '; layer_height' echo (global config) vs the actual LAYER_CHANGE
#      count (object config reaching the slicer).

import ctypes
import sys
import time
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import gcode_check  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import (add_common_args, export_and_check,  # noqa: E402
                       slice_and_wait)

LOG = "[diag_m5i]"
ART = HERE / "artifacts"
user32 = ctypes.WinDLL("user32")


def frame(session, name):
    img = capture_bgr(session)
    cv2.imwrite(str(ART / f"diag_m5i_{name}.png"), img)
    return img


def ocr_region(session, x0, y0, x1, y1, psm=6, scale=3):
    img = capture_bgr(session)
    words = mdu.ocr_words_img(img[y0:y1, x0:x1], scale=scale, psm=psm)
    return [(w, x + x0, y + y0, ww, wh) for w, x, y, ww, wh in words]


def click_word(session, words, seq):
    n = len(seq)
    for i in range(len(words) - n + 1):
        got = [w.lower() for w, *_ in words[i:i + n]]
        if got == [s.lower() for s in seq]:
            w0, x0, y0, _, wh = words[i]
            wn, xn, yn, x1n, _ = words[i + n - 1]
            x = (x0 + xn + x1n) // 2
            y = y0 + wh // 2
            return pp.client(session, x, y)
    return None


def teal_frac(session, rect):
    """Fraction of strongly-chromatic (teal highlight) pixels in a client
    rect — the switch paints the ACTIVE label as a teal pill (frame
    diag_m5i_t1: Global teal, Objects grey)."""
    img = capture_bgr(session)
    x0, y0, x1, y1 = rect
    sub = img[y0:y1, x0:x1].astype(int)
    if sub.size == 0:
        return -1.0
    spread = sub.max(axis=2) - sub.min(axis=2)
    return float((spread > 40).mean())


def mode_pill_words(session, py):
    """OCR the Global|Objects pill area. MEASURED on the frame: no single
    OCR config reads both tiny pills — scale=4/psm3 reads 'Global',
    scale=5/psm3 reads 'Objects' (crop x80..260, y py-12..py+20). Falls
    back to the frame-anchored geometry (pills begin ~15px right of the
    'Process' label, same row) when OCR misses."""
    words = ocr_region(session, 80, max(0, py - 12), 260, py + 20,
                       psm=3, scale=4)
    words += ocr_region(session, 80, max(0, py - 12), 260, py + 20,
                        psm=3, scale=5)
    for name, x0, x1 in (("global", 15, 62), ("objects", 66, 122)):
        if not any(w.lower() == name for w, *_ in words):
            # frame-measured fallback: client x106..139 / x150..191 at
            # py-2..py+16 (anchor row), i.e. label_right+24..+57 / +68..+109
            words.append((name, x0, py - 2, x1 - x0, 18))
    print(f"{LOG} mode pills: {' | '.join(f'{w}@{x},{y}' for w, x, y, *_ in words)}")
    return words


def dump_kids(session, tag, y_lo=None, y_hi=None):
    py = pp.process_row_y(session)
    rows = []
    for t, c, r, h, lx, ly in pp.kids(session):
        if not pp.user32.IsWindowVisible(h):
            continue
        if y_lo is not None and not (y_lo <= ly <= y_hi):
            continue
        rows.append((c, t.strip()[:40], lx, ly, r[2] - r[0], r[3] - r[1]))
    print(f"{LOG} kids[{tag}] anchor_py={py}: {rows[:26]}")


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    session, ok_cube = boot_cube_session(args)
    try:
        print(f"{LOG} cube: {ok_cube} alive={session.alive()}")
        if not ok_cube:
            return 1

        py = pp.process_row_y(session)
        print(f"{LOG} process anchor py={py}")

        # --- step 1+2: locate the Global|Objects pills and flip to
        # Objects via a REAL click on the 'objects' pill; judge the flip
        # by the teal highlight migrating to the Objects pill ---
        words = mode_pill_words(session, py)
        frame(session, "t1_global_row")
        pt = click_word(session, words, ("objects",))
        print(f"{LOG} 'objects' word point: {pt}")
        if not pt:
            print(f"{LOG} FAIL: no objects word on title row")
            return 1
        obj_rect = None
        for w, x, y, ww, wh in words:
            if w.lower() == "objects":
                obj_rect = (x - 6, y - 6, x + ww + 6, y + wh + 6)
        teal_before = teal_frac(session, obj_rect) if obj_rect else -1
        winutil.user32.SetCursorPos(*pt)
        time.sleep(0.2)
        winutil.real_click_screen(*pt)
        time.sleep(2.5)
        teal_after = teal_frac(session, obj_rect) if obj_rect else -1
        print(f"{LOG} objects pill teal {teal_before:.3f} -> {teal_after:.3f}")

        frame(session, "t2_objects_row")
        dump_kids(session, "after_objects_flip")

        tops = [(c, t.strip()[:30]) for c, t, r, h in
                mixing_util.toplevel(session.pid)]
        print(f"{LOG} toplevels after flip: {tops}")

        # --- step 3: Objects-mode sidebar. MEASURED (frame t3): the
        # preset combo row is REPLACED by a search box + object list
        # (Plate 1 / Cube [selected, teal] / Outside), the per-object
        # tab row sits ~188px below the anchor (Frequent active), and
        # the Frequent page shows Layer height 0.4 / Sparse infill 15%
        # / Wall loops 2 / Enable support. pp.options_viewport is None
        # in this mode — OCR a custom band below the tab row. ---
        img = capture_bgr(session)
        h_img = img.shape[0]
        freq = None
        for t, c, r, h, lx, ly in pp.kids(session):
            if c == "wxWindowNR" and t.strip() == "Frequent" \
                    and pp.user32.IsWindowVisible(h):
                freq = (lx, ly, r[2] - r[0], r[3] - r[1])
        print(f"{LOG} Frequent tab kid: {freq}")
        if not freq:
            print(f"{LOG} FAIL: per-object tab row not present")
            return 1
        band = ocr_region(session, 0, freq[1] + 25, pp.SB_W,
                          min(h_img, freq[1] + 190))
        print(f"{LOG} frequent page band: "
              f"{' | '.join(f'{w}@{x},{y}' for w, x, y, *_ in band)}")
        frame(session, "t3_objects_sidebar")

        # --- step 5: the per-object layer_height row: OCR 'height' ->
        # Edit at the row -> set 0.2 ---
        y_row = None
        for w, x, y, ww, wh in band:
            if w.lower() == "height":
                y_row = y + wh // 2
                break
        print(f"{LOG} layer row y_row={y_row}")
        if y_row is None:
            print(f"{LOG} FAIL: no Layer height row visible in Objects mode")
            return 1
        hit = pp.option_edit_at(session, y_row)
        print(f"{LOG} edit at row: {hit[0] if hit else None}")
        if not hit:
            return 1
        r, h = hit
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(h, buf, 256)
        print(f"{LOG} edit current text: {buf.value!r}")
        new = pp.real_edit_set(session, r, h, "0.2")
        pp.neutralize_focus(session)
        time.sleep(6.0)
        print(f"{LOG} edit set -> {new!r}")
        frame(session, "t6_committed")

        # --- step 6: slice + export; judge the override by the gcode:
        # the header echo keeps the GLOBAL 0.4 while the layer count
        # matches the OBJECT 0.2 (27mm cube: ~68 vs ~134 layers) ---
        sliced = slice_and_wait(session, timeout_s=900)
        out_path = ART / "diag_m5i.gcode"
        if out_path.exists():
            out_path.unlink()
        ok_exp, data = export_and_check(session, out_path)
        lh = gcode_check.config_value(data, "layer_height") if ok_exp else None
        n_change = data.count(b"LAYER_CHANGE") if ok_exp else -1
        print(f"{LOG} slice={sliced} export={ok_exp} "
              f"header layer_height={lh!r} LAYER_CHANGE x{n_change}")

        # --- step 7: flip back to Global; the preset combo row returns ---
        words3 = mode_pill_words(session, py)
        pt = click_word(session, words3, ("global",))
        print(f"{LOG} 'global' pill point: {pt}")
        if pt:
            winutil.user32.SetCursorPos(*pt)
            time.sleep(0.2)
            winutil.real_click_screen(*pt)
            time.sleep(2.5)
        _r, _h2, txt = pp.find_process_preset_combo(session)
        teal_after = teal_frac(session, obj_rect) if obj_rect else -1
        print(f"{LOG} back in global: preset combo={txt!r} "
              f"objects pill teal={teal_after:.3f}")
        frame(session, "t7_back_global")
        print(f"{LOG} alive={session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
