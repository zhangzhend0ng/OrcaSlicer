#!/usr/bin/env python3
# m4e_mixing_paint.py — the Color Painting gizmo palette (表1 #39, PARTIAL
# by design): the gizmo activates from the 3D view toolbar and renders the
# ImGui 'Filaments' palette with a color tile per physical AND mixed
# filament. The per-tile painting sub-steps are documented OUT of scope
# (ImGui pixel interaction).
#
# White-box refs:
#   - Gizmos/GLGizmosManager.cpp:206-221 — gizmo registration order; the
#     Color Painting gizmo is GLGizmoMmuSegmentation (10th registered).
#   - Gizmos/GLGizmoMmuSegmentation.cpp:429-520 — on_render_input_window
#     draws an ImGui window (NoTitleBar) whose FIRST line is the
#     m_desc['filaments'] heading ('Filaments', :216) followed by one color
#     tile button per displayed filament id; m_display_filament_ids include
#     MIXED filament ids (mixed_filament_from_id lookup, :495-505), so the
#     palette carries physical + mixed entries.
#   - GLGizmoMmuSegmentation.cpp:431 — requires a selected model object
#     (selection_info()->model_object()), hence the model click first.
#
# Stale-table / scope notes (表1 #39):
#   - '逐块涂色' (paint via each palette tile) is out of black-box scope —
#     the palette is ImGui pixels, not windowed controls.
#   - 'model selected' is not directly observable black-box (no selection
#     window text); it is implied by the palette appearing — the gizmo
#     renders nothing without a selected object.
#   - The 3D-view gizmo toolbar is HORIZONTAL in this build (top of the
#     3D view, not a left column) — buttons are located by a hover scan
#     reading the in-canvas tooltip ('Color Painting'), then clicked.
#
# Black-box path: boot standard fixture (5 filaments + seeded mixed scheme,
# >1 filament as the gizmo requires) -> real-click the model -> hover-scan
# the gizmo toolbar positions (bounded 20) until the tooltip OCRs 'Color
# Painting' -> click it -> OCR the 3D view right side for the 'Filaments'
# heading + count chromatic palette tiles (connected blobs, expect >=5) ->
# toggle the gizmo off, app alive.

import ctypes
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import (VP_X0, wait_model_loaded)  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[m4e]"
BAR_Y = 88           # gizmo toolbar row (client y)
BAR_X0, BAR_X1 = 480, 1160
PITCH = 35
PAL_X0, PAL_Y0, PAL_X1, PAL_Y1 = 700, 55, 1185, 470  # palette search band


def client(session, x, y):
    return winutil.client_to_screen(session.hwnd, x, y)


def viewport_img(session):
    return capture_bgr(session)


def hover_tooltip_text(session, cx, cy, dwell_s=1.4):
    """Park the cursor on a toolbar position and OCR the in-canvas tooltip
    band below the cursor (GLToolbar draws tooltips inside the canvas)."""
    sx, sy = client(session, cx, cy)
    winutil.user32.SetCursorPos(sx, sy)
    time.sleep(0.2)
    deadline = time.monotonic() + dwell_s
    while time.monotonic() < deadline:
        img = viewport_img(session)
        crop = img[cy + 12:cy + 96, max(0, cx - 110):cx + 130]
        if crop.size:
            words = mdu.ocr_words_img(crop, scale=3)
            text = " ".join(w for w, *_ in words)
            if len(text) >= 6:
                return text
        time.sleep(0.35)
    return ""


def find_model_centroid(session):
    """The model is the only chromatic blob in the upper canvas (bed grid
    and plate are gray). Returns the local centroid of the largest chromatic
    component, or None."""
    img = viewport_img(session)
    band = img[100:520, 440:1180].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 45).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    best, best_area = None, 0
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        if area > best_area:
            best, best_area = i, area
    if best is None or best_area < 400:
        return None
    cx, cy = centroids[best]
    return int(cx) + 440, int(cy) + 100


def rotate_tooltip(session):
    """Toolbar tooltip at the Rotate slot: with no selection it reads
    'Rotate: Please select at least one object'; with a selection just
    'Rotate...'."""
    return hover_tooltip_text(session, 760, BAR_Y)


def select_model(session):
    """Click the model's chromatic centroid until the Rotate tooltip stops
    demanding a selection. Returns True once selected."""
    for _ in range(4):
        pos = find_model_centroid(session)
        print(f"{LOG} model centroid: {pos}")
        if not pos:
            time.sleep(1.0)
            continue
        sx, sy = client(session, pos[0], pos[1])
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.2)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.2)
        tip = rotate_tooltip(session)
        print(f"{LOG} rotate tooltip after click: {tip!r}")
        if tip and "select" not in tip.lower():
            return True
    return False


def palette_state(session):
    """(heading_found, tile_count) of the palette band: OCR 'Filaments'
    heading + chromatic connected blobs of tile size."""
    img = viewport_img(session)
    band = img[PAL_Y0:PAL_Y1, PAL_X0:PAL_X1]
    words = mdu.ocr_words_img(band, scale=3)
    text = " ".join(w for w, *_ in words)
    heading = "filament" in text.lower()
    sub = band.astype(int)
    spread = sub.max(axis=2) - sub.min(axis=2)
    mask = (spread > 50).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            np.ones((3, 3), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    tiles = 0
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        w_px, h_px = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if area >= 120 and w_px >= 10 and h_px >= 8 and w_px < 220 \
                and h_px < 160:
            tiles += 1
    return heading, tiles, text


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

        # --- select the model (click its chromatic centroid; the Rotate
        #     tooltip observable flips from 'Please select at least...' to
        #     a plain 'Rotate' hint once an object is selected) ---
        selected = select_model(session)
        print(f"{LOG} model selected (rotate-tooltip observable): "
              f"{selected}")
        results["model selected"] = "PASS" if selected else "FAIL"
        if not selected:
            results["Color Painting toolbar tooltip found"] = "FAIL"
            results["Color Painting gizmo activates"] = "FAIL"
            results["palette renders >=5 filament tiles"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

        # --- hover-scan the gizmo toolbar for 'Color Painting' ---
        n_pos = (BAR_X1 - BAR_X0) // PITCH + 1
        target = None
        tip_text = ""
        for i in range(min(n_pos, 20)):
            cx = BAR_X0 + i * PITCH
            text = hover_tooltip_text(session, cx, BAR_Y)
            if text:
                print(f"{LOG} tooltip @x{cx}: {text!r}")
            low = text.lower()
            if "paint" in low and "color" in low:
                target = cx
                tip_text = text
                break
        if target is None:
            # fall back to the registration order (10th gizmo)
            target = BAR_X0 + 9 * PITCH
            print(f"{LOG} tooltip scan missed; using order-based x={target}")
        results["Color Painting toolbar tooltip found"] = (
            "PASS" if "paint" in tip_text.lower() else "FAIL")

        # --- activate the gizmo (poll: the selector build can take a
        #     moment and the palette renders after it) ---
        sx, sy = client(session, target, BAR_Y)
        heading = tiles = 0
        text = ""
        for poll in range(5):
            winutil.user32.SetCursorPos(sx, sy)
            time.sleep(0.15)
            winutil.real_click_screen(sx, sy)
            time.sleep(2.0)
            heading, tiles, text = palette_state(session)
            print(f"{LOG} palette poll{poll}: heading={heading} "
                  f"tiles={tiles} ocr={text[:60]!r}")
            if heading and tiles >= 5:
                break
            cv2.imwrite(str(HERE / "artifacts" / f"m4e_poll{poll}.png"),
                        viewport_img(session))
        results["Color Painting gizmo activates"] = (
            "PASS" if heading else "FAIL")
        results["palette renders >=5 filament tiles"] = (
            "PASS" if heading and tiles >= 5 else "FAIL")

        # --- toggle the gizmo back off ---
        winutil.user32.SetCursorPos(sx, sy)
        time.sleep(0.2)
        winutil.real_click_screen(sx, sy)
        time.sleep(1.0)

        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
