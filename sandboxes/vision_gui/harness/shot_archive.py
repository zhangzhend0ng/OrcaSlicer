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



def _screen_bgr():
    """Full virtual-screen GDI capture (BGR numpy array) or None."""
    import numpy
    u = winutil.user32; g = winutil.gdi32
    SW, SH = 1920, 1080  # fixed VM video mode; GetSystemMetrics below as fallback
    try:
        SW = u.GetSystemMetrics(0) or SW
        SH = u.GetSystemMetrics(1) or SH
    except Exception:
        pass
    hdc = u.GetDC(None)
    if not hdc:
        return None
    try:
        mem = g.CreateCompatibleDC(hdc)
        bmp = g.CreateCompatibleBitmap(hdc, SW, SH)
        g.SelectObject(mem, bmp)
        g.BitBlt(mem, 0, 0, SW, SH, hdc, 0, 0, 0x00CC0020)  # SRCCOPY
        import ctypes
        class BMI(ctypes.Structure):
            _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                        ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                        ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                        ("biClrImportant", ctypes.c_uint32)]
        bmi = BMI(); bmi.biSize = ctypes.sizeof(BMI); bmi.biWidth = SW; bmi.biHeight = -SH
        bmi.biPlanes = 1; bmi.biBitCount = 24; bmi.biCompression = 0
        buf = ctypes.create_string_buffer(SW * SH * 3)
        g.GetDIBits(mem, bmp, 0, SH, buf, ctypes.byref(bmi), 0)
        return numpy.frombuffer(buf.raw, numpy.uint8).reshape(SH, SW, 3)
    finally:
        u.ReleaseDC(None, hdc)


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
            try:  # full-screen capture at ~5fps — app is maximized at boot, so
                  # dialogs, menus and tooltips all appear naturally in frame.
                frame = _screen_bgr()
                if frame is not None:
                    if vid is None:
                        vid = cv2.VideoWriter(vpath, cv2.VideoWriter_fourcc(*"mp4v"), 5.0,
                                              (frame.shape[1], frame.shape[0]))
                    vid.write(frame)
            except Exception:
                pass
            stop.wait(min(interval, 0.2))
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
