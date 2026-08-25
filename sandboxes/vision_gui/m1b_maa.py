#!/usr/bin/env python3
# m1b_maa.py — M1b: the SAME minimal loop, expressed as MaaFramework pipeline.
#
# Decisive comparison for the engine choice (README conclusion matrix):
#   variant A: pipeline node action "Click" — MaaFw's Win32Controller built-in
#              SendMessage click, sent to the CONTROLLER's target hwnd (the
#              top-level frame). Composite wx UI: tabs are child controls, so
#              this is expected to MISS (routing a WM_LBUTTONDOWN to the frame
#              does not reach the child button).
#   variant B: pipeline node action "Custom" -> Python MsgClick, which resolves
#              the real child HWND via WindowFromPoint and SendMessage's it —
#              the proven m1 mechanism.
#
# Verification is done with OUR OWN eyes (winutil capture + template match +
# teal pixel), independent of MaaFw's reporting, so a "task succeeded" from
# MaaFw cannot mask a click that never landed.

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import launcher, profile, winutil  # noqa: E402
from m1_minimal_loop import MATCH_THRESHOLD, capture_bgr, is_tab_teal, wait_for  # noqa: E402
RESOURCE = HERE / "resource"


def preview_selected(session) -> bool:
    img = capture_bgr(session)
    return is_tab_teal(img, 244, 49)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=HERE / "artifacts" / "profile", type=Path)
    args = ap.parse_args()

    from maa.controller import Win32Controller
    from maa.custom_action import CustomAction
    from maa.define import MaaWin32InputMethodEnum as IM
    from maa.define import MaaWin32ScreencapMethodEnum as SM
    from maa.resource import Resource
    from maa.tasker import Tasker

    _MAIN = []  # populated after launch: [session]

    class MsgClickAction(CustomAction):
        """Custom action: WindowFromPoint + SendMessage click at the hit box."""

        def run(self, context, argv: CustomAction.RunArg) -> CustomAction.RunResult:
            x, y, w, h = argv.box
            ox, oy = winutil.client_to_screen(_MAIN[0].hwnd, 0, 0)
            hwnd = winutil.msg_click_screen(x + w // 2 + ox, y + h // 2 + oy)
            print(f"[m1b] custom MsgClick at box {argv.box} -> hwnd 0x{hwnd:x}")
            return CustomAction.RunResult(success=True)

    results = {}

    profile.seed_profile(args.datadir)
    session = launcher.launch(exe=args.exe, datadir=args.datadir)
    _MAIN.append(session)
    try:
        # wait for the boot to settle on Prepare (same rationale as m1)
        score, _, _ = wait_for(session, RESOURCE / "image" / "tab_prepare_active.png", timeout_s=45.0)
        print(f"[m1b] boot settled on Prepare: {score:.3f}")
        if score < MATCH_THRESHOLD:
            return 2
        time.sleep(1.0)

        # ---- MaaFw setup ----
        res = Resource()
        job = res.post_bundle(RESOURCE)
        if not job.wait().succeeded:
            print("[m1b] resource bundle load failed"); return 2
        res.register_custom_action("MsgClick", MsgClickAction())

        ctrl = Win32Controller(ctypes_hwnd(session.hwnd),
                               screencap_method=SM.PrintWindow,
                               mouse_method=IM.SendMessage,
                               keyboard_method=IM.SendMessage)
        # MaaFw downsamples captures to ~720p by default; templates are cut at
        # native resolution — force RAW size so the two scales agree.
        ctrl.set_screenshot_use_raw_size(True)
        if not ctrl.post_connection().wait().succeeded:
            print("[m1b] controller connection failed"); return 2

        tasker = Tasker()
        if not tasker.bind(res, ctrl):
            print("[m1b] tasker bind failed"); return 2

        # sanity: MaaFw screencap sees the same thing we do
        shot = ctrl.post_screencap().wait().get()
        if shot is not None:
            img = np.array(shot)
            print(f"[m1b] MaaFw screencap: {img.shape}")
            teal_seen = is_tab_teal(img[:, :, ::-1], 244, 49) if img.ndim == 3 else None
            print(f"[m1b] MaaFw screencap prepare-tab-teal: {teal_seen}")

        # ---- variant A: built-in Click ----
        for attempt in range(3):
            task = tasker.post_task("click_preview_builtin")
            task.wait()
            # diagnostics: did recognition hit, what box, did the node complete
            td = tasker.get_task_detail(task.job_id)
            for nd in (td.nodes if hasattr(td, "nodes") else []):
                rd = nd.recognition
                print(f"[m1b] A attempt {attempt+1}: node '{nd.name}' completed={nd.completed} "
                      f"reco hit={rd.hit} box={rd.box}")
            time.sleep(1.5)
            if preview_selected(session):
                results["A built-in Click"] = "PASS (tab switched)"
                # switch back before variant B
                wait_for(session, RESOURCE / "image" / "tab_prepare_inactive.png", timeout_s=5.0)
                sx = 108; sy = 49
                ox, oy = winutil.client_to_screen(session.hwnd, 0, 0)
                for _ in range(3):
                    winutil.msg_click_screen(sx + ox, sy + oy)
                    time.sleep(1.0)
                    s2, _, _ = wait_for(session, RESOURCE / "image" / "tab_prepare_active.png", timeout_s=4.0)
                    if s2 >= MATCH_THRESHOLD and is_tab_teal(capture_bgr(session), 108, 49):
                        break
                break
        else:
            results["A built-in Click"] = "FAIL (tab never switched)"

        # ---- variant B: custom action MsgClick ----
        for attempt in range(3):
            task = tasker.post_task("click_preview_custom")
            task.wait()
            time.sleep(1.0)
            if preview_selected(session):
                time.sleep(1.0)
                if preview_selected(session):  # stable, not bounced
                    results["B custom MsgClick"] = "PASS (tab switched, stable)"
                    break
        else:
            results["B custom MsgClick"] = "FAIL"

        print("\n[m1b] === verdict ===")
        for k, v in results.items():
            print(f"  {k}: {v}")
        return 0
    finally:
        session.close()
        print("[m1b] app closed")


def ctypes_hwnd(h: int):
    import ctypes
    return ctypes.c_void_p(h)


if __name__ == "__main__":
    raise SystemExit(main())
