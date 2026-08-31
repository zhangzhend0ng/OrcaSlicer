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
from m2_slice_chain import (VP_X0, VP_Y0, wait_model_loaded)  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

user32 = ctypes.WinDLL("user32")
LOG = "[m4e]"
# Recalibrated 08-31 on the MAXIMIZED window (1920x1032 client): all three
# fixed 1200x800-era bands were stale. The gizmo toolbar row is top-anchored
# (BAR_Y holds), but it is centered over the 3D view and once the window is
# wider than 1200 it REACHES PAST x=1160 — the Color Painting slot sits in
# the never-scanned right half. The palette band and the model-centroid band
# are viewport-relative now (m2_slice_chain._vp calibration).
BAR_Y = 88           # gizmo toolbar row (client y)
PITCH = 35
SCAN_X0 = VP_X0 + 60            # hover-scan from the viewport left edge...
PAL_Y0, PAL_Y1 = 55, 470        # palette band y (top-anchored chrome)...
PAL_LEFT_OFF = 250              # ...x from viewport-left+offset to window edge


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
    component, or None. Band = the whole 3D viewport, size-adaptive: the
    fixed 100:520 x 440:1180 band clipped the model on the maximized window
    and the biased centroid clicked empty bed (model never selected)."""
    img = viewport_img(session)
    h, w = img.shape[:2]
    x0, y0, x1, y1 = VP_X0 + 10, VP_Y0 + 30, w - 10, h - 60
    band = img[y0:y1, x0:x1].astype(int)
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
    return int(cx) + x0, int(cy) + y0


def find_slot(session, pred):
    """First gizmo-toolbar slot whose in-canvas tooltip satisfies `pred`
    (on the lowercased text). Band spans the viewport top strip (see the
    recalibration note above); returns (client_x, tooltip) or (None, '')."""
    img = viewport_img(session)
    x0, x1 = SCAN_X0, img.shape[1] - 60
    n = (x1 - x0) // PITCH + 1
    for i in range(min(n, 40)):
        cx = x0 + i * PITCH
        text = hover_tooltip_text(session, cx, BAR_Y)
        if text:
            print(f"{LOG} tooltip @x{cx}: {text!r}")
            if pred(text.lower()):
                return cx, text
    return None, ""


def select_model(session):
    """Click the model's chromatic centroid until the ROTATE slot's tooltip
    stops demanding a selection. The Rotate slot is located by tooltip scan
    (size-adaptive): the fixed x=760 hover was the windowed-era position and
    silently read a neighboring tooltip after the maximize, so the 'selected'
    observable flipped on garbage text."""
    rot_x, _ = find_slot(session, lambda t: "rotate" in t)
    if rot_x is None:
        print(f"{LOG} rotate slot not found by tooltip scan")
        return False
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
        tip = hover_tooltip_text(session, rot_x, BAR_Y)
        print(f"{LOG} rotate tooltip after click: {tip!r}")
        if tip and "select" not in tip.lower():
            return True
    return False


def palette_state(session):
    """(heading_found, tile_count) of the palette band: OCR 'Filaments'
    heading + chromatic connected blobs of tile size. Band = the viewport's
    top strip right of x=VP_X0+PAL_LEFT_OFF to the window edge: the ImGui
    gizmo panel renders inside the 3D canvas, which widens with the window
    (the fixed 700..1185 band searched empty space once maximized)."""
    img = viewport_img(session)
    w = img.shape[1]
    band = img[PAL_Y0:PAL_Y1, VP_X0 + PAL_LEFT_OFF:w - 12]
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
        target, tip_text = find_slot(
            session, lambda t: "paint" in t and "color" in t)
        if target is None:
            # looser retry before falling back to nothing
            target, tip_text = find_slot(session, lambda t: "paint" in t)
        if target is None:
            print(f"{LOG} color-painting slot NOT found by tooltip scan")
        results["Color Painting toolbar tooltip found"] = (
            "PASS" if "paint" in tip_text.lower() else "FAIL")
        if target is None:
            results["Color Painting gizmo activates"] = "FAIL"
            results["palette renders >=5 filament tiles"] = "FAIL"
            results["app alive"] = "PASS" if session.alive() else "FAIL"
            return verdict(results)

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
