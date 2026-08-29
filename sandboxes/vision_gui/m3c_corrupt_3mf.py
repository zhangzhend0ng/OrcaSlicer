#!/usr/bin/env python3
# m3c_corrupt_3mf.py — P3-12: a corrupted 3mf fails the load gracefully.
#
# White-box ref: wx_gui_business_tests.cpp:666 — no crash, no model
# mutation, plater stays functional for the next project.
#
# Black-box path: launch with a corrupt file -> an error dialog appears
# (wxMessageBox, #32770) -> dismiss it -> the app is still alive -> a
# second launch with a good project loads the model (model arrival by
# viewport chromatic fraction).

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import export_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402


def make_corrupt_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"this is not a 3mf archive")
    return path


def dismiss_dialog(pid, timeout_s=15.0):
    """Find the visible #32770 of the process, click its OK button (or
    press ESC), wait for it to close."""
    dlg = export_util.wait_toplevel(pid, lambda c, t, r: c == "#32770",
                                    timeout_s=timeout_s)
    if not dlg:
        return False
    print(f"[m3c] error dialog: '{dlg[1]}' rect={dlg[2]}")
    # click OK / Cancel / close button (Button class, usually first)
    import ctypes
    user32 = ctypes.WinDLL("user32")
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p,
                                     ctypes.c_void_p)
    buttons = []
    def cb(h, _lp):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(h, cls, 64)
        if cls.value == "Button":
            txt = ctypes.create_unicode_buffer(128)
            user32.GetWindowTextW(h, txt, 128)
            rc = ctypes.wintypes.RECT()
            user32.GetWindowRect(h, ctypes.byref(rc))
            buttons.append((txt.value, (rc.left, rc.top, rc.right, rc.bottom)))
        return True
    user32.EnumChildWindows(ctypes.c_void_p(dlg[3]), WNDENUMPROC(cb), 0)
    print(f"[m3c] dialog buttons: {[(t, r) for t, r in buttons]}")
    if buttons:
        rc = buttons[0][1]  # OK is typically the first button
        winutil.msg_click_screen((rc[0] + rc[2]) // 2, (rc[1] + rc[3]) // 2,
                                 dlg[3])
    else:
        winutil.msg_key(dlg[3], winutil.VK_ESCAPE if hasattr(winutil, "VK_ESCAPE") else 0x1B)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if export_util.wait_toplevel(pid, lambda c, t, r: c == "#32770",
                                     timeout_s=1.0) is None:
            return True
        time.sleep(0.5)
    return True  # dialog gone or closed anyway


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    results = {}
    corrupt = make_corrupt_file(Path(args.datadir).parent / "corrupt_probe.3mf")

    # --- first launch: corrupt file ---
    session = boot_session(args, model=corrupt)
    try:
        time.sleep(5.0)  # allow the load failure path to surface
        dlg = export_util.wait_toplevel(
            session.pid, lambda c, t, r: c == "#32770", timeout_s=20.0)
        print(f"[m3c] error dialog appeared: {bool(dlg)}")
        results["corrupt load surfaces error"] = (
            "PASS" if dlg else "FAIL (no dialog — check app behavior)")
        if dlg:
            dismiss_dialog(session.pid)
        time.sleep(2.0)
        results["app survives corrupt load"] = (
            "PASS" if session.alive() else "FAIL (app crashed)")
    finally:
        session.close()
        print("[m3c] first launch closed")

    # --- second launch: good project still loads ---
    session2 = boot_session(args, model=MIXED_3MF)
    try:
        ok, frac = wait_model_loaded(session2, timeout_s=30)
        print(f"[m3c] good project model arrival: {ok} ({frac:.2%})")
        results["plater usable after corrupt load"] = (
            "PASS" if ok else "FAIL")
        return verdict(results)
    finally:
        session2.close()
        print("[m3c] second launch closed")


if __name__ == "__main__":
    raise SystemExit(main())
