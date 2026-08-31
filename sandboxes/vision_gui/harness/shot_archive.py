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
        import cv2
        seq = 0
        vid = None
        vpath = str(root / f"{name}_run.mp4")
        while not stop.is_set() and winutil.user32.IsWindow(session.hwnd):
            seq += 1
            ts = time.strftime("%H%M%S")
            frame = None
            if seq % 6 == 1:  # ~every 3s at 0.5s cadence: keep the PNG archive
                _save(session.hwnd, root / f"{seq:04d}_{ts}_main.png")
                for h, tag in visible_big_dialogs():
                    _save(h, root / f"{seq:04d}_{ts}_{tag}.png")
            try:  # every tick (~0.5s): main window + current dialog, stacked
                import numpy as _np
                w, h, bgra = winutil.capture_window(session.hwnd)
                main = _np.frombuffer(bgra, _np.uint8).reshape(h, w, 4)[:, :, :3].copy()
                VW = 960
                main = cv2.resize(main, (VW, int(h * VW / w)))
                dlg_slot_h = 480
                dlg_area = _np.zeros((dlg_slot_h, VW, 3), _np.uint8)
                for dh, _tag in visible_big_dialogs():
                    dw, dh2, dbgra = winutil.capture_window(dh)
                    dimg = _np.frombuffer(dbgra, _np.uint8).reshape(dh2, dw, 4)[:, :, :3]
                    dimg = cv2.resize(dimg, (VW, min(dlg_slot_h, int(dh2 * VW / dw))))
                    dlg_area[:dimg.shape[0], :VW] = dimg
                    break
                if vid is None:
                    vid = cv2.VideoWriter(vpath, cv2.VideoWriter_fourcc(*"mp4v"), 2.0,
                                          (VW, main.shape[0] + dlg_slot_h))
                vid.write(_np.vstack([main, dlg_area]))
            except Exception:
                pass
            stop.wait(min(interval, 0.5))
        if vid is not None:
            vid.release()
        _save(session.hwnd, root / "final.png")

    t = threading.Thread(target=run, name=f"shots-{name}")  # non-daemon: the
    # mp4 moov atom is written in release(); a daemon thread killed at process
    # exit leaves an unplayable file (measured: 9/27 files lost their index).
    t.start()
    import atexit
    atexit.register(lambda: (stop.set(), t.join(timeout=10)))

    # labeled capture: called from the stdout tee on every step print, so each
    # assertion/step log line gets its own screenshot named after the line —
    # this is what makes per-Feishu-record evidence lookup exact.
    state = {"n": 0, "last": 0.0}

    def capture_labeled(label: str):
        now = time.monotonic()
        if now - state["last"] < 1.0:   # rate limit: live prints can burst
            return
        state["last"] = now
        state["n"] += 1
        slug = "".join(ch if ch.isalnum() else "-" for ch in label.strip())[:60].strip("-")
        _save(session.hwnd, root / f"L{state['n']:03d}_{slug}_main.png")
        for h, tag in visible_big_dialogs():
            _save(h, root / f"L{state['n']:03d}_{slug}_{tag}.png")

    stop.capture_labeled = capture_labeled   # attach for the stdout hook
    return stop


def hook_stdout_tee(archive):
    """Tee case stdout: every printed line also triggers a labeled capture.
    Idempotent; call once per process after start_archiver."""
    import sys
    if getattr(sys.stdout, "_shot_hooked", False):
        return
    orig = sys.stdout

    class Tee:
        _shot_hooked = True

        def __init__(self, orig):
            self._orig = orig

        def write(self, s):
            try:
                self._orig.write(s)
            except Exception:
                pass
            for line in s.splitlines():
                line = line.strip()
                # step/verdict lines only: harness prints are prefixed [mX] or start
                # with an assertion name in the verdict block
                if line and (line.startswith("[") or ":" in line or "PASS" in line or "FAIL" in line):
                    try:
                        archive.capture_labeled(line)
                    except Exception:
                        pass
            return len(s)

        def flush(self):
            try:
                self._orig.flush()
            except Exception:
                pass

        def __getattr__(self, a):
            return getattr(self._orig, a)

    sys.stdout = Tee(orig)
