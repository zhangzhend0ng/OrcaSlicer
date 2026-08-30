#!/usr/bin/env python3
# harness/shot_archive.py — background screenshot archiver for the m3/m4 cases.
#
# start_archiver() spawns a daemon thread that PrintWindow-captures the app's
# main window plus any large visible dialogs of the same pid every `interval`
# seconds, writing PNGs to artifacts/shots/<name>/. A final shot is taken when
# the main window goes away. Purely observational (no input injection), so it
# never interferes with the case's own vision checks — the captures use the
# same PrintWindow(PW_RENDERFULLCONTENT) path the harness already uses.
#
# Hooked from m3_common.boot_session, so every case archives automatically.

import threading
import time
from pathlib import Path

import cv2
import numpy as np

from harness import winutil  # noqa: E402

HERE = Path(__file__).resolve().parent.parent


def _save(hwnd: int, path: Path) -> bool:
    try:
        w, h, bgra = winutil.capture_window(hwnd)
        img = np.frombuffer(bgra, np.uint8).reshape(h, w, 4)
        return cv2.imwrite(str(path), img[:, :, :3])
    except Exception:
        return False


def start_archiver(session, name: str, interval: float = 3.0, out_root=None):
    """Archive screenshots for this session; returns the stop Event."""
    root = (Path(out_root) if out_root else HERE / "artifacts" / "shots" / name)
    root.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()

    def visible_big_dialogs():
        out = []
        try:
            from harness import mixing_util
            for cls, _txt, r, h in mixing_util.toplevel(session.pid):
                if h == session.hwnd or not winutil.user32.IsWindowVisible(h):
                    continue
                if (r[2] - r[0]) > 200 and (r[3] - r[1]) > 200:
                    out.append((h, "".join(ch for ch in cls if ch.isalnum())[:12]))
        except Exception:
            pass
        return out

    def run():
        seq = 0
        while not stop.is_set() and winutil.user32.IsWindow(session.hwnd):
            seq += 1
            ts = time.strftime("%H%M%S")
            _save(session.hwnd, root / f"{seq:04d}_{ts}_main.png")
            for h, tag in visible_big_dialogs():
                _save(h, root / f"{seq:04d}_{ts}_{tag}.png")
            stop.wait(interval)
        _save(session.hwnd, root / "final.png")

    threading.Thread(target=run, daemon=True, name=f"shots-{name}").start()
    return stop
