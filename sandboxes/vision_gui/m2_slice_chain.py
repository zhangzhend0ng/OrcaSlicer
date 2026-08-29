#!/usr/bin/env python3
# m2_slice_chain.py — M2: the black-box SLICING business chain.
#
#   launch(with model) -> vision-confirm model loaded -> click "Slice plate"
#   -> wait for slicing to finish (green-check done badge on the button) ->
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

# Fraction of viewport pixels that must be clearly chromatic for the model
# to count as loaded: empty bed measures ~0.15%, a loaded (multicolor) model
# ~2.1% — 1% sits with >5x margin on both sides (measured 2026-08-28).
MODEL_COLORED_THRESHOLD = 0.010

# Absolute floor for the toolpath assertion: the pre-slice model baseline
# is 0.7-2.1% depending on the model (default Prusa.stl 0.69%, multicolor
# 1.9-2.1%) — 1% keeps the gate model-agnostic while far above empty-bed
# noise (~0.15%). The >=2x ratio gate does the real discrimination; this
# floor only excludes sub-1% jitter.
TOOLPATH_COLORED_FLOOR = 0.010


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


def wait_model_loaded(session, timeout_s=30):
    """Model-arrival detector: a loaded model renders saturated colors into
    the 3D viewport while the empty bed/grid is essentially monochrome
    (measured: empty ~0.15% chromatic pixels, multicolor model ~2.1% — a 14x
    separation; the 1% threshold has >5x margin on both sides).

    The earlier diff-vs-reference detector was structurally blind: the model
    loads DURING the hands-off boot (the t=12s boot frame already carries
    it), so any reference captured after the hands-off sleep already contains
    the model and a change never fires. An absolute chromatic threshold needs
    no reference at all. Stability across two polls rules out theme/UI
    animation transients (they would only trip a single poll).
    Returns (ok, colored_fraction)."""
    last_frac = 0.0
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        frac = has_colored_content(capture_bgr(session))
        if frac >= MODEL_COLORED_THRESHOLD:
            time.sleep(1.0)
            frac2 = has_colored_content(capture_bgr(session))
            if frac2 >= MODEL_COLORED_THRESHOLD:
                return True, max(frac, frac2)
        last_frac = frac
        time.sleep(1.0)
    return False, last_frac


def wait_slicing_done(session, timeout_s=1500):
    """Slicing finished = the 'Slice plate' button shows its DONE rendering
    (green checkmark badge; template slice_button_done.png). The plain idle
    template is NOT a valid completion signal: the done state scores only
    ~0.67 against it (the checkmark shifts the normalized correlation), which
    masqueraded as 'still slicing' in earlier runs while slicing had in fact
    COMPLETED.

    Anti-false-positive: the done template also scores ~0.90 against the
    PRINT button area on an EMPTY scene (the 180x42 template spans both
    buttons), so completion additionally requires the idle template to have
    LEFT its 1.0 match (idle < 0.9) — a real completion shows done ~1.0 +
    idle ~0.67, an empty scene shows done ~0.90 + idle ~1.0."""
    tpl = cv2.imread(str(RESOURCE / "slice_button_done.png"))
    tpl_idle = cv2.imread(str(RESOURCE / "slice_plate_button.png"))
    deadline = time.monotonic() + timeout_s
    n_polls = 0
    last = 0.0
    while time.monotonic() < deadline:
        img = capture_bgr(session)
        if n_polls in (2, 10, 60, 150):  # diag snapshots: 1s/5s/30s/75s at 0.5s poll
            cv2.imwrite(str(HERE / "artifacts" / f"m2_diag_wait{n_polls}.png"), img)
        n_polls += 1
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, _ = cv2.minMaxLoc(res)
        res_idle = cv2.matchTemplate(img, tpl_idle, cv2.TM_CCOEFF_NORMED)
        _, score_idle, _, _ = cv2.minMaxLoc(res_idle)
        last = float(score)
        if score >= 0.85 and score_idle < 0.9:
            return True, last
        time.sleep(0.5)
    return False, last


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
        winutil.msg_click_screen(sx, sy, session.hwnd)
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
    ap.add_argument("--model", default=HERE.parent.parent / "tests" / "data" / "test_3mf" / "mixed_filament_test.3mf", type=Path,
                    help="U1-embedded fixture: Prusa.stl (no embedded preset) falls back to a seed preset "
                         "that leaves Slice disabled — see BLACKBOX_CASES.md '关键源码事实'")
    ap.add_argument("--reuse", action="store_true",
                    help="reuse the datadir (default: FRESH — a used datadir "
                         "carries saved state that blocks CLI auto-load)")
    args = ap.parse_args()

    results = {}
    profile.seed_profile(args.datadir, fresh=not args.reuse)
    session = launcher.launch(exe=args.exe, datadir=args.datadir, model=args.model)
    try:
        env_check.print_preflight(session.hwnd)

        # 1) HANDS-OFF boot: any early interference with the window (capture
        # polling, foreground grabbing) races post_init's first-idle
        # input_files load and SILENTLY KILLS the CLI model auto-load —
        # proven by the m3mf hands-off experiment. Sleep through it.
        time.sleep(12.0)
        # Late, non-interfering presentation: no taskbar button and bottom
        # of the z-order (the UI shell owns the taskbar). Rendering and
        # hit-testing are untouched, so capture/injection still work.
        winutil.background_tool_window(session.hwnd)
        img_boot = capture_bgr(session)
        cv2.imwrite(str(HERE / "artifacts" / "m2_boot.png"), img_boot)
        from m1_minimal_loop import match as tpl_match
        score, _, _, _, _ = tpl_match(img_boot, RESOURCE / "tab_prepare_active.png")
        print(f"[m2] boot state: Prepare tab score {score:.3f} "
              f"(rect {session.rect()})")
        ok_model, col_frac = wait_model_loaded(session)
        print(f"[m2] model arrival observed: {ok_model} (viewport colored {col_frac:.2%})")
        # Slicing an empty plate produces nothing, so a successful slice also
        # proves the model loaded — the detector verdict is upgraded below
        # for models whose colors are too muted for the chromatic threshold.
        results["model loaded"] = "PASS" if ok_model else "FAIL (no chromatic model content)"
        time.sleep(1.0)

        # 2) click "Slice plate" and wait for the button to come back idle
        empty_frac0 = has_colored_content(capture_bgr(session))
        started = click_slice_start(session)
        done, done_score = (False, 0.0)
        if started:
            # Model-arrival FAIL means slicing probably has nothing to work
            # on; cap the wait so a dead run fails in ~1min with a clear
            # diagnosis instead of spinning out the full 1500s. A muted-color
            # model that slipped past the detector can still finish a real
            # slice inside the cap and get upgraded below.
            timeout_s = 1500 if ok_model else 60
            done, done_score = wait_slicing_done(session, timeout_s=timeout_s)
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
        # toolpath = colored fraction well above the noise floor AND >=2x
        # the pre-slice colored-model baseline (a colored MODEL alone used
        # to false-positive the old fixed threshold; the ratio gate already
        # excludes that — the floor only excludes sub-1% empty-bed jitter)
        results["preview toolpath"] = (
            "PASS" if (ok_pv and colored > TOOLPATH_COLORED_FLOOR
                       and colored >= 2 * max(empty_frac0, 1e-4)) else "FAIL")

        print("\n[m2] === verdict ===")
        # A successful end-to-end slice is itself proof the model loaded
        # (slicing an empty plate produces nothing); upgrade a detector FAIL
        # for models whose colors are too muted to trip the chromatic gate.
        if results.get("slice + completion") == "PASS" and not results["model loaded"].startswith("PASS"):
            results["model loaded"] = "PASS (proven by successful slicing)"
        for k, v in results.items():
            print(f"  {k}: {v}")
        ok = all(v.startswith("PASS") for v in results.values())
        print("[m2] " + ("GREEN" if ok else "RED"))
        return 0 if ok else 1
    finally:
        session.close()
        print("[m2] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
