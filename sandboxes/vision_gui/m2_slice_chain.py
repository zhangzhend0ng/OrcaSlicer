#!/usr/bin/env python3
# m2_slice_chain.py — M2: the black-box SLICING business chain.
#
#   launch(with model) -> vision-confirm model loaded -> click "Slice plate"
#   -> wait for slicing to finish (button region returns to idle) ->
#   switch to Preview -> assert toolpath rendering (colored travel/extrusion
#   lines raise viewport color variance).
#
# Everything is observed from OUTSIDE the process: captures, template
# matches, pixel statistics. No app API, no HWND introspection for state.

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import env_check, launcher, profile, winutil  # noqa: E402
from m1_minimal_loop import (MATCH_THRESHOLD, capture_bgr,  # noqa: E402
                             click_and_verify, wait_for)

RESOURCE = HERE / "resource" / "image"

# 3D viewport region (client px): right of the settings panel, below topbar.
VP_X0, VP_Y0, VP_X1, VP_Y1 = 430, 70, 1155, 1030


def viewport_stats(img):
    vp = img[VP_Y0:VP_Y1, VP_X0:VP_X1].astype(int)
    return vp.std(), vp.mean()


def has_colored_content(img) -> float:
    """Fraction of viewport pixels that are clearly CHROMATIC (toolpath lines).

    The empty bed/grid and UI chrome are near-gray (low channel spread);
    extruded toolpath is rendered in saturated filament colors.
    """
    vp = img[VP_Y0:VP_Y1, VP_X0:VP_X1].astype(int)
    spread = vp.max(axis=2) - vp.min(axis=2)
    return float((spread > 40).mean())


def wait_model_loaded(session, timeout_s=45):
    """Best-effort model-arrival detector: after a short settle, any large
    viewport CHANGE means the loaded model rendered (absolute levels are too
    boot-dependent to threshold — camera angle and bed fade-in vary)."""
    time.sleep(4.0)  # let boot animations settle; the model loads in parallel
    ref = capture_bgr(session)[VP_Y0:VP_Y1, VP_X0:VP_X1].astype(int)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        img = capture_bgr(session)
        vp = img[VP_Y0:VP_Y1, VP_X0:VP_X1].astype(int)
        diff = float(np.abs(vp - ref).mean())
        if diff > 6.0:
            # require stability: next capture close to this one
            time.sleep(1.5)
            vp2 = capture_bgr(session)[VP_Y0:VP_Y1, VP_X0:VP_X1].astype(int)
            if float(np.abs(vp2 - vp).mean()) < 2.0:
                return True, diff
        time.sleep(1.0)
    return False, 0.0


def wait_slicing_done(session, timeout_s=600):
    """Slicing finished = the Slice button returns to its idle rendering.

    While slicing, the button region morphs into a progress display; polling
    for the idle template coming BACK is the black-box completion signal.
    NOTE: on this GameViewer-hosted machine slicing is SLOW (Prusa.stl can
    take minutes on first run) — the timeout must be generous.
    """
    tpl = cv2.imread(str(RESOURCE / "slice_plate_button.png"))
    deadline = time.monotonic() + timeout_s
    saw_busy = False
    n_polls = 0
    last_score = 0.0
    while time.monotonic() < deadline:
        img = capture_bgr(session)
        if n_polls in (2, 10, 60, 150):  # diagnostic snapshots during the wait
            cv2.imwrite(str(HERE / "artifacts" / f"m2_diag_wait{n_polls}.png"), img)
        n_polls += 1
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(res)
        last_score = float(score)
        if score < 0.7:
            saw_busy = True  # button changed shape -> slicing in progress
        elif saw_busy and score >= MATCH_THRESHOLD:
            return True, last_score
        time.sleep(2.0)
    return False, last_score


def click_slice_start(session, attempts=3):
    """Click 'Slice plate' ONCE-accepted: a click only counts when the button
    leaves its idle rendering (slicing started). NO blind re-clicking after
    that — clicking again mid-slice could cancel the job."""
    tpl = cv2.imread(str(RESOURCE / "slice_plate_button.png"))
    for i in range(attempts):
        score, sx, sy = wait_for(session, RESOURCE / "slice_plate_button.png", timeout_s=5.0)
        if score < MATCH_THRESHOLD:
            print(f"[m2] slice button not found ({score:.3f})")
            continue
        winutil.msg_click_screen(sx, sy)
        time.sleep(3.0)
        img = capture_bgr(session)
        cv2.imwrite(str(HERE / "artifacts" / f"m2_diag_click{i}.png"), img)
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, s2, _, _ = cv2.minMaxLoc(res)
        if s2 < 0.7:
            print(f"[m2] slicing started (button left idle, score {s2:.3f})")
            return True
        print(f"[m2] attempt {i+1}: click didn't take (still {s2:.3f}), retry")
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=HERE / "artifacts" / "profile", type=Path)
    ap.add_argument("--model", default=HERE.parent.parent / "tests" / "data" / "test_3mf" / "Prusa.stl", type=Path)
    ap.add_argument("--reuse", action="store_true",
                    help="reuse the datadir (default: FRESH — a used datadir "
                         "carries saved state that blocks CLI auto-load)")
    args = ap.parse_args()

    results = {}
    profile.seed_profile(args.datadir, fresh=not args.reuse)
    session = launcher.launch(exe=args.exe, datadir=args.datadir, model=args.model)
    try:
        env_check.print_preflight(session.hwnd)

        # 1) boot settles on Prepare with the model loaded (auto via CLI arg)
        score, _, _ = wait_for(session, RESOURCE / "tab_prepare_active.png", timeout_s=60.0)
        print(f"[m2] Prepare settled: {score:.3f}")
        # Re-assert position AFTER startup: window_pos_restore runs late in
        # on_init_inner and can drag the window back to the GameViewer virtual
        # display, where DWM throttling freezes the slicing pipeline.
        winutil.move_to_primary_and_foreground(session.hwnd)
        print(f"[m2] window rect now: {winutil.window_rect(session.hwnd)}")
        ok_model, mdiff = wait_model_loaded(session)
        print(f"[m2] model arrival observed: {ok_model} (viewport diff {mdiff:.1f})")
        # best-effort: a fast load can precede our reference capture; the
        # preview-toolpath assertion below is the authoritative gate.
        results["model loaded"] = "PASS" if ok_model else "UNVERIFIED (best-effort)"
        time.sleep(1.0)

        # 2) click "Slice plate" and wait for the button to come back idle
        empty_frac0 = has_colored_content(capture_bgr(session))
        started = click_slice_start(session)
        done, done_score = (False, 0.0)
        if started:
            done, done_score = wait_slicing_done(session, timeout_s=1500)
        print(f"[m2] slicing started={started} done={done} (idle score {done_score:.3f})")
        results["slice + completion"] = "PASS" if done else "FAIL"

        # 3) switch to Preview and assert the toolpath rendering
        ok_pv, _ = click_and_verify(session, RESOURCE / "tab_preview_inactive.png",
                                    RESOURCE / "tab_preview_active.png")
        time.sleep(2.0)  # toolpath load
        img = capture_bgr(session)
        cv2.imwrite(str(HERE / "artifacts" / "m2_preview.png"), img)
        colored = has_colored_content(img)
        print(f"[m2] Preview switched={ok_pv}, colored-viewport fraction: "
              f"{colored:.3%} (was {empty_frac0:.3%} before slicing)")
        results["preview toolpath"] = "PASS" if (ok_pv and colored > 0.02) else "FAIL"

        print("\n[m2] === verdict ===")
        for k, v in results.items():
            print(f"  {k}: {v}")
        ok = all(v.startswith("PASS") or v.startswith("UNVERIFIED") for v in results.values())
        print("[m2] " + ("GREEN" if ok else "RED"))
        return 0 if ok else 1
    finally:
        session.close()
        print("[m2] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
