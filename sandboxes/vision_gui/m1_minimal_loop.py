#!/usr/bin/env python3
# m1_minimal_loop.py — M1: the minimal closed loop, raw-Python version.
#
#   launch -> capture -> template-match the Preview tab -> message-click it ->
#   assert the view switched (tab state + left panel content changed) ->
#   switch back -> assert.
#
# Decisive experiments recorded (see README hazard/conclusion matrix):
#   (a) can a message-level click drive the CUSTOM-DRAWN topbar tabs?
#   (b) can message-level input reach NATIVE child controls (Edit fields)?
#   (c) PrintWindow(PW_RENDERFULLCONTENT) GL capture — proven in m0.
#
# Exit code 0 = loop green.

import argparse
import ctypes
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import env_check, launcher, profile, winutil  # noqa: E402

RESOURCE = HERE / "resource" / "image"
user32 = ctypes.WinDLL("user32")

MATCH_THRESHOLD = 0.80


def match(screen_bgr: np.ndarray, template_path: Path):
    """Best match of template in a BGR capture; returns (score, x, y) top-left."""
    tpl = cv2.imread(str(template_path))
    if tpl is None:
        raise FileNotFoundError(template_path)
    res = cv2.matchTemplate(screen_bgr, tpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(res)
    return score, loc[0], loc[1], tpl.shape[1], tpl.shape[0]


def capture_bgr(session):
    cap = winutil.capture_window(session.hwnd)
    return cv2.cvtColor(np.frombuffer(cap[2], np.uint8).reshape(cap[1], cap[0], 4),
                        cv2.COLOR_BGRA2BGR)


def wait_for(session, template_path: Path, timeout_s: float = 30.0, poll_s: float = 0.5):
    """Poll until `template_path` matches the live capture (score >= threshold).

    Startup page selection is racy (the final select_tab runs in a CallAfter
    after GL init — see GUI_App.cpp load_gl_resources), so the driver must
    WAIT for the expected visual state, never assume a fixed delay.
    Returns (score, screen_x, screen_y) of the best match.
    """
    tpl = cv2.imread(str(template_path))
    deadline = time.monotonic() + timeout_s
    best = (0.0, 0, 0)
    while time.monotonic() < deadline:
        cap = winutil.capture_window(session.hwnd)
        img = cv2.cvtColor(np.frombuffer(cap[2], np.uint8).reshape(cap[1], cap[0], 4),
                           cv2.COLOR_BGRA2BGR)
        res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(res)
        cx, cy = loc[0] + tpl.shape[1] // 2, loc[1] + tpl.shape[0] // 2
        ox, oy = winutil.client_to_screen(session.hwnd, 0, 0)
        best = (float(score), cx + ox, cy + oy)
        if score >= MATCH_THRESHOLD:
            return best
        time.sleep(poll_s)
    return best


def click_and_verify(session, click_tpl: Path, expect_tpl: Path, attempts: int = 4):
    """Click the control matching `click_tpl`, retry until `expect_tpl` shows
    AND STAYS for the bounce window.

    Retrying is essential for two reasons:
      - page switches posted early after boot can be undone by late startup
        events (EVT_GLVIEWTOOLBAR_3D / restore-project CallAfters bounce the
        selection back to Prepare — see GUI_App::load_gl_resources);
      - a click landing mid-repaint can be lost.
    A single positive sighting is not enough: the app may bounce back within
    ~1s, so the expected state must be RE-confirmed after a settle delay.
    Vision drivers retry; they never assume.
    Returns (ok, last_expect_score).
    """
    last = 0.0
    for i in range(attempts):
        score, sx, sy = wait_for(session, click_tpl, timeout_s=5.0)
        if score < MATCH_THRESHOLD:
            print(f"[m1] attempt {i+1}: click target not found ({score:.3f})")
            continue
        hwnd = winutil.msg_click_screen(sx, sy, session.hwnd)
        print(f"[m1] attempt {i+1}: clicked {click_tpl.name} at ({sx},{sy}) -> hwnd 0x{hwnd:x}")
        score2, _, _ = wait_for(session, expect_tpl, timeout_s=6.0)
        last = score2
        if score2 >= MATCH_THRESHOLD:
            time.sleep(1.0)  # bounce window
            img = capture_bgr(session)
            tpl = cv2.imread(str(expect_tpl))
            res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
            _, score3, _, _ = cv2.minMaxLoc(res)
            last = float(score3)
            if score3 >= MATCH_THRESHOLD:
                print(f"[m1] attempt {i+1}: state stable ({score3:.3f})")
                return True, score3
            print(f"[m1] attempt {i+1}: state BOUNCED back ({score2:.3f} -> {score3:.3f}), retrying")
        else:
            print(f"[m1] attempt {i+1}: expected state not reached ({score2:.3f}), retrying")
    return False, last


def is_tab_teal(img, x: int, y: int) -> bool:
    px = img[y, x]
    return abs(int(px[0]) - 136) + abs(int(px[1]) - 150) + abs(int(px[2])) < 60


def get_edit_text(hwnd) -> str:
    n = user32.SendMessageW(hwnd, 0x000E, 0, 0)  # WM_GETTEXTLENGTH
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(hwnd, 0x000D, n + 1, buf)  # WM_GETTEXT
    return buf.value


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=HERE / "artifacts" / "profile", type=Path)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    verdict = {}

    profile.seed_profile(args.datadir)
    session = launcher.launch(exe=args.exe, datadir=args.datadir, model=args.model)
    try:
        report = env_check.print_preflight(session.hwnd)

        # Boot page selection is racy (deferred CallAfter after GL init):
        # WAIT for the Prepare tab's active state instead of a fixed sleep.
        score, px, py = wait_for(session, RESOURCE / "tab_prepare_active.png", timeout_s=45.0)
        print(f"[m1] boot settled on Prepare: score={score:.3f} tab center=({px},{py})")
        if score < MATCH_THRESHOLD:
            cv2.imwrite(str(HERE / "artifacts" / "m1_debug_timeout.png"), capture_bgr(session))
            print("[m1] FAIL: app never reached the Prepare page"); return 2
        time.sleep(1.0)  # let the settings panel finish laying out

        # ---------- click Preview (custom-drawn tab), with retry ----------
        (HERE / "artifacts").mkdir(exist_ok=True)
        cv2.imwrite(str(HERE / "artifacts" / "m1_debug_cap0.png"), capture_bgr(session))
        print(f"[m1] client origin screen: {winutil.client_to_screen(session.hwnd, 0, 0)}")

        active_tpl = RESOURCE / "tab_preview_active.png"
        bootstrap = not active_tpl.exists()
        if bootstrap:
            # First run: no active-state template yet. Click, settle, verify by
            # the teal pixel (ButtonsListCtrl selected color) STABLY, then cut.
            score, sx, sy = wait_for(session, RESOURCE / "tab_preview_inactive.png", timeout_s=5.0)
            if score < MATCH_THRESHOLD:
                print("[m1] FAIL: preview tab not found"); return 2
            img1 = None
            for i in range(4):
                winutil.msg_click_screen(sx, sy, session.hwnd)
                time.sleep(1.0)
                probe = capture_bgr(session)
                if is_tab_teal(probe, 244, 49):
                    time.sleep(1.0)  # bounce window
                    probe2 = capture_bgr(session)
                    if is_tab_teal(probe2, 244, 49):
                        img1 = probe2
                        break
            if img1 is None:
                print("[m1] FAIL: Preview never became stably selected (teal)"); return 2
        else:
            ok, score2 = click_and_verify(session, RESOURCE / "tab_preview_inactive.png", active_tpl)
            if not ok:
                img1 = capture_bgr(session)
                print("[m1] FAIL: switch to Preview not verifiable "
                      f"(score {score2:.3f})"); return 2
            img1 = capture_bgr(session)

        # ---------- assert switched ----------
        # Dark theme evidence, per ButtonsListCtrl source (Notebook.cpp):
        # selected tab bg = teal (0,150,136); unselected = (59,68,70).
        # (Template matching alone is a weak state discriminator here — the
        # glyphs are identical between states and TM_CCOEFF_NORMED normalizes
        # the uniform background away — so assert on the button COLORS.)
        tab_px = img1[49, 244]  # Preview tab center (capture coords)
        preview_now_selected = is_tab_teal(img1, 244, 49)
        prep_px = img1[49, 108]
        prep_now_unselected = abs(int(prep_px[0]) - 70) + abs(int(prep_px[1]) - 68) + abs(int(prep_px[2]) - 59) < 60
        print(f"[m1] after click: Preview tab BGR={tab_px} selected={preview_now_selected}; "
              f"Prepare tab BGR={prep_px} unselected={prep_now_unselected}")
        verdict["(a) custom tab click"] = "PASS" if (preview_now_selected and prep_now_unselected) else "FAIL"

        # cut templates from the VERIFIED switched state only (never blind)
        cv2.imwrite(str(RESOURCE / "tab_preview_active.png"), img1[31:67, 176:312])
        cv2.imwrite(str(RESOURCE / "tab_prepare_inactive.png"), img1[31:67, 40:176])

        # ---------- click back to Prepare ----------
        ok_back, score_back = click_and_verify(session, RESOURCE / "tab_prepare_inactive.png",
                                               RESOURCE / "tab_prepare_active.png")
        img2 = capture_bgr(session)
        print(f"[m1] back on Prepare: template score={score_back:.3f}, "
              f"tab BGR={img2[49, 108]} teal={is_tab_teal(img2, 108, 49)}")
        verdict["(a2) switch back to Prepare"] = (
            "PASS" if (ok_back and is_tab_teal(img2, 108, 49)) else "FAIL")

        # ---------- (b) native Edit control reachable? ----------
        # 'Layer height' Edit was at screen (258,708)-ish; re-discover children
        edit = None
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        def cb(h, _):
            nonlocal edit
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, cls, 64)
            if cls.value == "Edit" and edit is None:
                edit = h
            return True
        user32.EnumChildWindows(ctypes.c_void_p(session.hwnd), WNDENUMPROC(cb), 0)
        if edit is not None:
            before = get_edit_text(edit)
            winutil.msg_text(edit, "0.16")
            time.sleep(0.5)
            after = get_edit_text(edit)
            print(f"[m1] native Edit text: {before!r} -> {after!r}")
            verdict["(b) native Edit WM_CHAR"] = "PASS" if "0.16" in after else "FAIL"
        else:
            verdict["(b) native Edit WM_CHAR"] = "SKIP (no Edit found)"

        print("\n[m1] === verdict ===")
        for k, v in verdict.items():
            print(f"  {k}: {v}")
        ok = all(v == "PASS" for v in verdict.values())
        print("[m1] " + ("GREEN" if ok else "RED"))
        return 0 if ok else 1
    finally:
        session.close()
        print("[m1] app closed")


if __name__ == "__main__":
    raise SystemExit(main())
