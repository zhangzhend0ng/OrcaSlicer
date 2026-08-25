#!/usr/bin/env python3
# m0_boot_check.py — Phase 0 milestone: prove the black-box bootstrap.
#
#   seed profile -> launch the real exe (visible, no test-mode env) ->
#   find the main window -> preflight env -> capture screenshots over time ->
#   close gracefully.
#
# Artifacts under artifacts/m0/: startup captures (BMP) + report. These
# captures are ALSO the raw material for cutting template images
# (resource/image/) — run with --grab to dump a steady-state shot for that.

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import env_check, launcher, profile, winutil  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None, help="app exe (default: main checkout Release build)")
    ap.add_argument("--datadir", default=HERE / "artifacts" / "profile", type=Path)
    ap.add_argument("--model", default=None, help="optional 3mf/stl to auto-load")
    ap.add_argument("--fresh", action="store_true", help="re-seed the datadir from scratch")
    ap.add_argument("--grab", action="store_true", help="steady-state capture for template cutting")
    ap.add_argument("--keep", action="store_true", help="leave the app running (manual inspection)")
    args = ap.parse_args()

    out_dir = HERE / "artifacts" / "m0"
    out_dir.mkdir(parents=True, exist_ok=True)

    profile.seed_profile(args.datadir, fresh=args.fresh)
    session = launcher.launch(exe=args.exe, datadir=args.datadir, model=args.model)
    try:
        report = env_check.print_preflight(session.hwnd)

        # Capture a few startup phases; PrintWindow(PW_RENDERFULLCONTENT)
        # should include the GL canvas — a black 3D area would mean the
        # (c) experiment failed (see README hazard matrix).
        stamps = [0.5, 2.0, 5.0]
        if args.grab:
            time.sleep(3.0)  # let first paint / preset load settle
            stamps = [0.2]
        for i, wait in enumerate(stamps):
            time.sleep(wait)
            try:
                cap = winutil.capture_window(session.hwnd)
                path = out_dir / ("grab.png" if args.grab else f"startup_{i}.bmp")
                winutil.save_capture_bmp(str(path), cap)
                print(f"[m0] capture {i}: {cap[0]}x{cap[1]} -> {path.name}")
            except winutil.CaptureError as e:
                print(f"[m0] capture {i} FAILED: {e}")
                return 2

        if args.keep:
            print(f"[m0] --keep: app running (pid {session.pid}); press Ctrl+C to exit")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        print("[m0] OK" if not report.get("remote_control") else
              "[m0] OK (remote-control layer active: message-injection path required)")
        return 0
    finally:
        session.close()
        print("[m0] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
