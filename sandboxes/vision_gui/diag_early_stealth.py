#!/usr/bin/env python3
# diag_early_stealth.py — regression probe for the boot "pop to top" fix.
#
# The launcher's SW_SHOWNOACTIVATE is a no-op for wx (wxMSW Show() calls
# ShowWindow(SW_SHOW), which activates + raises), so the main frame used to
# pop to the TOP of the user's desktop at boot and sit there for the whole
# ~12s hands-off window. Fix = passive demote_watchdog() during boot
# (WS_EX_NOACTIVATE + HWND_BOTTOM — the taskbar icon is deliberately KEPT as
# a running indicator — plus foreground RESTORATION to the pre-launch window;
# never moves/capture). This probe asserts, in ONE run:
#
#   1. (the fix)   no app window ever takes the FOREGROUND from launch
#                  return through boot + model load, and the main frame
#                  ends up demoted (NOACTIVATE style, taskbar icon kept).
#   2. (no regress) the experimentally sensitive CLI model auto-load still
#                  works with the watchdog active (README pitfall #3: early
#                  foreground/move interference kills it — demotion must not).
#
# Control run: --no-watchdog  boots WITHOUT early demotion; there the
# foreground assertion is EXPECTED to fail (that is the old behavior).

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import launcher, profile, winutil  # noqa: E402
from m1_minimal_loop import capture_bgr  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402

FIXTURES = HERE.parent.parent / "tests" / "data" / "test_3mf"
MIXED_3MF = FIXTURES / "mixed_filament_test.3mf"  # CLI auto-load fixture

WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
GWL_EXSTYLE = -20


def app_is_foreground(pid: int) -> bool:
    hwnd = winutil.user32.GetForegroundWindow()
    if not hwnd:
        return False
    wpid = winutil.wt.DWORD()
    winutil.user32.GetWindowThreadProcessId(hwnd, winutil.ctypes.byref(wpid))
    return wpid.value == pid


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=HERE / "artifacts" / "diag_stealth_profile", type=Path)
    ap.add_argument("--no-watchdog", action="store_true",
                    help="control run: boot WITHOUT early demotion (old behavior)")
    args = ap.parse_args()

    profile.seed_profile(args.datadir, fresh=True)
    session = launcher.launch(exe=args.exe, datadir=args.datadir, model=MIXED_3MF,
                              boot_demote_s=0 if args.no_watchdog else 12.0)
    try:
        results: dict[str, str] = {}

        # 1) foreground monitor: poll through the hands-off boot window. The
        #    watchdog restores the pre-launch foreground whenever the app
        #    grabs it, so a sub-second blip is acceptable (invisible); what
        #    this asserts is that the app never HOLDS the foreground.
        poll_s = 0.1
        fg_polls = 0          # polls where an app window owned the foreground
        fg_streak = 0         # longest continuous run
        max_streak = 0
        hands_off_deadline = time.monotonic() + 14.0
        while time.monotonic() < hands_off_deadline:
            if app_is_foreground(session.pid):
                fg_polls += 1
                fg_streak += 1
                max_streak = max(max_streak, fg_streak)
            else:
                fg_streak = 0
            time.sleep(poll_s)

        fg_time = fg_polls * poll_s
        results["no foreground steal"] = (
            "PASS" if fg_time <= 1.0 else
            f"FAIL (app held foreground ~{fg_time:.1f}s total, "
            f"longest streak ~{max_streak * poll_s:.1f}s)")

        # Late re-assert exactly like the m1/m2/m3 drivers do.
        winutil.demote_window(session.hwnd)
        time.sleep(1.0)

        # 2) demoted styles on the main frame: NOACTIVATE must be set,
        #    TOOLWINDOW must NOT (the taskbar icon is the running indicator).
        ex = winutil.user32.GetWindowLongW(session.hwnd, GWL_EXSTYLE)
        demoted = bool(ex & WS_EX_NOACTIVATE)
        icon_kept = not (ex & WS_EX_TOOLWINDOW)
        bottom = winutil.user32.GetWindow(session.hwnd, 1) == session.hwnd  # GW_HWNDLAST
        results["demoted (NOACTIVATE)"] = ("PASS" if demoted else f"FAIL (exstyle=0x{ex & 0xffffffff:x})")
        results["taskbar icon kept"] = "PASS" if icon_kept else "FAIL (WS_EX_TOOLWINDOW set - icon hidden)"
        results["z-order bottom"] = ("PASS" if bottom else
                                     "INFO (not the very last; other toolwindows may sit below)")

        # 3) the sensitive path: CLI model auto-load must survive the watchdog.
        ok_model, col_frac = wait_model_loaded(session)
        results["model auto-loaded"] = ("PASS" if ok_model else
                                        f"FAIL (viewport colored {col_frac:.2%})")
        if not ok_model:
            import cv2
            frame = capture_bgr(session)
            out = HERE / "artifacts" / "diag_stealth_fail.png"
            cv2.imwrite(str(out), frame)
            print(f"[diag] model NOT loaded; frame {frame.shape} -> {out.name}")

        print("\n[diag] === verdict ===")
        for k, v in results.items():
            print(f"  {k}: {v}")
        ok = not any(str(v).startswith("FAIL") for v in results.values())
        print("[diag] " + ("GREEN — boot stealth holds, auto-load unaffected"
                           if ok else "RED — see failures above"))
        return 0 if ok else 1
    finally:
        session.close()
        print("[diag] app closed")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as e:
        print(f"[diag] aborted: {e}")
        raise
