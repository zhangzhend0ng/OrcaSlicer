#!/usr/bin/env python3
# inspect_window.py — launch the app, dump its child-HWND control tree
# (class/text/rect) + a fresh capture, then close. Development aid: maps the
# visual layout to concrete controls so template regions can be chosen
# deliberately (and so message-injection targets are known).

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import launcher, profile, winutil  # noqa: E402

user32 = ctypes.WinDLL("user32")
WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def dump_children(root: int) -> list[dict]:
    out: list[dict] = []

    def cb(hwnd, _lp):
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        txt = ctypes.create_unicode_buffer(128)
        user32.GetWindowTextW(hwnd, txt, 128)
        rc = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rc))
        out.append({
            "hwnd": f"0x{hwnd:x}",
            "class": cls.value,
            "text": txt.value,
            "rect": [rc.left, rc.top, rc.right, rc.bottom],
            "size": [rc.right - rc.left, rc.bottom - rc.top],
        })
        return True

    user32.EnumChildWindows(ctypes.c_void_p(root), WNDENUMPROC(cb), 0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=HERE / "artifacts" / "profile", type=Path)
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default=HERE / "artifacts" / "inspect", type=Path)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    profile.seed_profile(args.datadir)
    session = launcher.launch(exe=args.exe, datadir=args.datadir, model=args.model)
    try:
        time.sleep(3.0)  # first paint + preset load
        cap = winutil.capture_window(session.hwnd)
        winutil.save_capture_bmp(str(args.out / "capture.bmp"), cap)
        print(f"[inspect] capture {cap[0]}x{cap[1]}")

        children = dump_children(session.hwnd)
        (args.out / "children.json").write_text(json.dumps(children, indent=1))
        print(f"[inspect] {len(children)} child hwnds -> children.json")

        # Console summary: interesting controls (has text or decent size)
        main_l, main_t, main_r, main_b = session.rect()
        for c in children:
            l, t, r, b = c["rect"]
            cl, ct = l - main_l, t - main_t  # client-ish coords
            if c["text"] or (c["size"][0] > 30 and c["size"][1] > 15):
                print(f"[inspect] {c['class']:26s} {c['size'][0]:5d}x{c['size'][1]:<4d} "
                      f"@client({cl},{ct}) text={c['text']!r}")

        if args.keep:
            print("[inspect] --keep: running; Ctrl+C to exit")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
        return 0
    finally:
        session.close()
        print("[inspect] closed")


if __name__ == "__main__":
    raise SystemExit(main())
