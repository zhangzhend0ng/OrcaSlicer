#!/usr/bin/env python3
# m3_common.py — shared scaffolding for the m3 black-box business-path cases.
#
# Every m3 case follows the same skeleton (fresh profile + hands-off boot +
# background presentation + graceful close) and reuses:
#   - template-located slicing      (m2_slice_chain)
#   - the export-gcode primitive    (harness/export_util)
#   - deterministic control lookup  (export_util.topbar_buttons)
# No app API, no runtime hooks: observation is screenshots / window
# messages / filesystem only (see BLACKBOX_CASES.md).

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import launcher, profile, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import (MODEL_COLORED_THRESHOLD,  # noqa: E402
                            click_slice_start, has_colored_content,
                            wait_model_loaded, wait_slicing_done)

RESOURCE = HERE / "resource" / "image"
FIXTURES = HERE.parent.parent / "tests" / "data" / "test_3mf"
MIXED_3MF = FIXTURES / "mixed_filament_test.3mf"   # embeds Snapmaker U1 0.8
MULTI_PLATE_3MF = FIXTURES / "snapmates_nonmixed.3mf"  # 7 plates
PRUSA_STL = FIXTURES / "Prusa.stl"


def viewport_rendered(session, min_frac=0.5) -> bool:
    """True once the 3D viewport paints non-background pixels. An
    uninitialized canvas is PURE white (255/255/255, measured); a rendered
    one shows the bed gradient / model."""
    img = capture_bgr(session)
    h, w = img.shape[:2]
    sub = img[h // 8: h * 7 // 8, w * 3 // 8: w * 15 // 16].astype(int)
    nonwhite = float((sub.min(axis=2) < 245).mean())
    return nonwhite > min_frac


def force_canvas_paint(session):
    """Real clicks across the Preview/Prepare tab band. The GL canvas only
    initializes on REAL paint/mouse events; when the boot window is fully
    occluded (a fullscreen console window above it), no WM_PAINT arrives
    and the canvas stays white forever (measured 08-30, GLCanvas3D render
    gate / GUI_App init path). The frame is a fixed 1200x800 rect, so the
    tab offsets are stable."""
    rect = winutil.window_rect(session.hwnd)
    for dx, dy in ((240, 48), (120, 48)):
        x, y = rect[0] + dx, rect[1] + dy
        winutil.user32.SetCursorPos(x, y)
        time.sleep(0.2)
        winutil.real_click_screen(x, y)
        time.sleep(1.2)


def ensure_gl_ready(session, tries: int = 4) -> bool:
    """Force-paint the GL canvas until the viewport stops being blank."""
    ok = viewport_rendered(session)
    for _ in range(tries):
        if ok:
            break
        force_canvas_paint(session)
        ok = viewport_rendered(session)
    print(f"[m3] gl canvas ready: {ok}")
    return ok


def boot_session(args, model=None, fresh=True):
    """Seed a fresh datadir, launch with optional model, hands-off boot."""
    datadir = Path(args.datadir)
    profile.seed_profile(datadir, fresh=fresh)
    session = launcher.launch(exe=args.exe, datadir=datadir, model=model)
    # archive screenshots for later manual spot-check (all cases, zero edits)
    from harness import shot_archive
    _arch = shot_archive.start_archiver(session, Path(sys.argv[0]).stem)
    shot_archive.hook_stdout_tee(_arch)   # labeled capture per step/verdict print
    time.sleep(12.0)  # hands-off: early interference kills CLI auto-load
    ensure_gl_ready(session)
    winutil.demote_window(session.hwnd)
    return session


def slice_and_wait(session, model_arrived=True, timeout_s=1500):
    """Click Slice (template-located) and wait for the done rendering."""
    started = click_slice_start(session)
    if not started:
        return False
    cap = 60 if not model_arrived else timeout_s
    done, score = wait_slicing_done(session, timeout_s=cap)
    return done


def export_and_check(session, out_path: Path, timeout_s=45.0):
    """Export the current slice result; returns (ok, bytes) or (False, b'')."""
    from harness import export_util
    if not export_util.export_gcode(session, out_path, timeout_s=timeout_s):
        return False, b""
    return True, out_path.read_bytes()


def verdict(results: dict) -> int:
    print("\n[m3] === verdict ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    ok = all(str(v).startswith("PASS") for v in results.values())
    print("[m3] " + ("GREEN" if ok else "RED"))
    return 0 if ok else 1


def add_common_args(ap: argparse.ArgumentParser, default_model=None):
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=HERE / "artifacts" / "m3_profile", type=Path)
    ap.add_argument("--model", default=default_model, type=Path)
    return ap
