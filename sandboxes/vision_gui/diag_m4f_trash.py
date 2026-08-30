#!/usr/bin/env python3
# diag_m4f_trash.py — why does the Filaments-row trash click not delete at
# 64 slots? Dump the title-row buttons, try real + message clicks, dump
# again, save a screenshot.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import fixture_util  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
import m4f_mixing_cap64 as m4f  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402

LOG = "[diag]"


def dump(session, tag):
    frect = winutil.window_rect(session.hwnd)
    print(f"{LOG} {tag}: frame={frect}")
    for title in ("Filaments", "Color Mixing"):
        row = mdu._sidebar_title_row(session, title)
        if not row:
            print(f"{LOG} {tag}: {title} row NOT FOUND")
            continue
        label, btns = row
        print(f"{LOG} {tag}: {title} label={label}")
        for i, (r, h) in enumerate(btns):
            t, c, rr, hh = None, None, r, h
            for tt, cc, r2, h2 in mixing_util.children(session.hwnd):
                if h2 == h:
                    t, c = tt, cc
                    break
            print(f"  band btn[{i}] text={t!r} class={c} rect={r} "
                  f"enabled={m4f.enabled(h)}")
        # exact children of the title PANEL (parent of the label Static)
        label_h = None
        for t, c, r, h in mixing_util.children(session.hwnd):
            if c == "Static" and t == title:
                label_h = h
                break
        if label_h:
            panel = winutil.user32.GetParent(label_h)
            kids = []
            for t, c, r, h in mixing_util.children(panel):
                vis = winutil.user32.IsWindowVisible(h)
                kids.append((c, t, r, h, vis, m4f.enabled(h)))
            for i, (c, t, r, h, vis, en) in enumerate(kids):
                print(f"  panel[{i}] class={c} text={t!r} rect={r} "
                      f"visible={vis} enabled={en}")
    print(f"{LOG} {tag}: chips={m4f.visible_chips(session)} "
          f"combos={len(mdu.filament_material_combos(session))}")


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap)
    args = ap.parse_args()
    if not args.model:
        args.model = m4f.COLOURS and fixture_util.craft_filaments_fixture(
            fixture_util.ART_FIXTURES / "cap64_pla.3mf",
            m4f.COLOURS, m4f.TYPES, m4f.IDS, strip_mixed=True)
    session = boot_session(args, model=args.model)
    try:
        fixture_util.dismiss_custom_preset_dialog(session, timeout_s=20)
        ensure_gl_ready(session)
        wait_model_loaded(session, timeout_s=60)
        time.sleep(2.5)
        dump(session, "before")

        fbtns = mdu.filament_row_buttons(session)
        # panel-scoped buttons: siblings of the 'Filaments' label
        label_h = None
        for t, c, r, h in mixing_util.children(session.hwnd):
            if c == "Static" and t == "Filaments":
                label_h = h
                break
        panel = winutil.user32.GetParent(label_h)
        pbtns = [(r, h) for t, c, r, h in mixing_util.children(panel)
                 if c == "Button" and winutil.user32.IsWindowVisible(h)]
        pbtns.sort(key=lambda bh: bh[0][0])
        print(f"{LOG} panel buttons: {[(r, hex(h)) for r, h in pbtns]}")
        if len(pbtns) >= 2:
            rect, hwnd = pbtns[-2]
            x, y = (rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2
            print(f"{LOG} real-click panel[-2] (del) at ({x},{y})")
            winutil.user32.SetCursorPos(x, y)
            time.sleep(0.3)
            winutil.real_click_screen(x, y)
            time.sleep(6.0)
            dump(session, "after-panel-del-click")

        # --- try to open Add Mix like m4f does, with full diagnostics ---
        time.sleep(3.0)
        mbtns = mdu.title_panel_buttons(session, "Color Mixing")
        print(f"{LOG} color-mixing panel buttons: "
              f"{[(r, hex(h), m4f.enabled(h)) for r, h in mbtns]}")
        if mbtns:
            r, h = mbtns[-1]
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            top = winutil.window_from_screen_point(cx, cy)
            deep = winutil.deepest_child_at(top, cx, cy) \
                if hasattr(winutil, "deepest_child_at") else None
            print(f"{LOG} click pt ({cx},{cy}): window_from_point="
                  f"{hex(top)} deepest={hex(deep) if deep else None} "
                  f"(frame {hex(session.hwnd)})")
            real_click_r = r
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.3)
            t0 = time.monotonic()
            winutil.real_click_screen(cx, cy)
            dlg = None
            while time.monotonic() - t0 < 120.0:
                dlg = mdu.find_mix_dialog(session.pid, timeout_s=1.0)
                if dlg:
                    break
            dt = time.monotonic() - t0
            print(f"{LOG} add-mix dialog after {dt:.1f}s: {hex(dlg) if dlg else None}")
            dlgs = [(hex(h), t, (r2[2] - r2[0], r2[3] - r2[1]))
                    for c, t, r2, h in mixing_util.toplevel(session.pid)
                    if c == "#32770"]
            print(f"{LOG} #32770 toplevels: {dlgs}")
            if dlg:
                mdu.click_button(session, dlg, "Cancel")
    finally:
        session.close()
        print(f"{LOG} closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
