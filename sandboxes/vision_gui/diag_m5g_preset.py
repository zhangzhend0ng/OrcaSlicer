#!/usr/bin/env python3
# diag_m5g_preset.py — empirical recon for the preset SAVE flow (m5g).
# Dumps: Process-row icon buttons + their hover tooltips, the save dialog
# children, then drives the save end-to-end and lists the datadir/process
# output + combo text. Evidence goes to the log + artifacts shots.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mixing_util  # noqa: E402
from harness import ocr_util  # noqa: E402
from harness import process_panel as pp  # noqa: E402
from m5_common import boot_cube_session  # noqa: E402
from m3_common import add_common_args, boot_session, verdict  # noqa: E402

LOG = "[diag_m5g]"


def row_buttons(session):
    """Small empty-text Buttons on the preset row: the band BELOW the
    'Process' anchor row. MEASURED 09-02: the anchor row itself carries the
    Advanced switch + view/compare icons (py-24..py+8); the preset combo
    row with the save floppy + search sits py+20..py+60 — the first diag
    missed the floppy because its band stopped at py+24."""
    py = pp.process_row_y(session)
    out = []
    for t, c, r, h, lx, ly in pp.kids(session):
        if c != "Button" or t.strip() or not pp.user32.IsWindowVisible(h):
            continue
        w, hh = r[2] - r[0], r[3] - r[1]
        if not (10 <= w <= 40 and 8 <= hh <= 32):
            continue
        if py + 8 <= ly <= py + 70 and lx > 250:
            out.append((lx, r, h))
    out.sort(key=lambda x: x[0])
    return [(r, h) for _lx, r, h in out]


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    args = ap.parse_args()

    session, ok_cube = boot_cube_session(args)
    try:
        print(f"{LOG} cube: {ok_cube} alive={session.alive()}")
        pp.ensure_advanced(session, want=True)
        pp.click_tab(session, "Quality", "height")
        hit = pp.wait_float_edit(session)
        if hit:
            r, h, old = hit
            new = pp.real_edit_set(session, r, h, "0.3")
            pp.neutralize_focus(session)
            print(f"{LOG} dirty layer height: {old!r} -> {new!r}")
        time.sleep(6.0)

        btns = row_buttons(session)
        print(f"{LOG} preset-row button candidates: {len(btns)}")
        # tooltip probe first (armed by real-mouse hover), then click
        from harness import winutil
        save_btn = None
        for i, (r, h) in enumerate(btns):
            tt = mixing_util.hover_swatch_row(
                session, session.hwnd, (r[0] - 4, r[1] - 4, r[2] + 4, r[3] + 4),
                x_frac=0.5, dwell_s=3.0)
            tip = ocr_util.ocr_hwnd(tt[1]) if tt else ""
            print(f"{LOG} btn{i} rect={r} tooltip={tip!r}")
            if "save" in tip.lower() and save_btn is None:
                save_btn = ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
        print(f"{LOG} save (tooltip) click point: {save_btn}")
        if save_btn is None and btns:
            # fallback: LEFTMOST preset-row icon = the save floppy
            # (icon order in the crop: floppy then search; measured 09-02)
            r, h = btns[0]
            save_btn = ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            print(f"{LOG} fallback to leftmost: {save_btn}")

        known = pp.top_dialog_set(session)
        if save_btn:
            cx, cy = save_btn
            winutil.user32.SetCursorPos(cx, cy)
            time.sleep(0.2)
            winutil.real_click_screen(cx, cy)
            time.sleep(2.5)
            new_tl = [(cls, txt, rc, hh)
                      for cls, txt, rc, hh in mixing_util.toplevel(session.pid)
                      if hh not in known]
            print(f"{LOG} click btn -> new toplevels: "
                  f"{[(c, t[:30], rc2[2] - rc2[0], rc2[3] - rc2[1]) for c, t, rc2, hh in new_tl]}")
            dlg = next((hh for cls, txt, rc, hh in new_tl
                        if cls == "#32770"), None)
            popup = next((hh for cls, txt, rc, hh in new_tl
                          if cls == "wxWindowNR"), None)
            if popup and not dlg:
                mdu._send_keys([(0x1B, False), (0x1B, True)])
                time.sleep(1.0)
        else:
            dlg = None
        new_tl = [(cls, txt, rc, hh) for cls, txt, rc, hh
                  in mixing_util.toplevel(session.pid)
                  if hh not in known]
        print(f"{LOG} new toplevels now: "
              f"{[(c, t, rc2[2] - rc2[0], rc2[3] - rc2[1]) for c, t, rc2, hh in new_tl]}")
        if dlg:
            for t, c, rc, hh in mixing_util.children(dlg):
                if t.strip() or c in ("Edit", "ComboBox", "Button"):
                    print(f"{LOG}   dlg child: {c} {t[:44]!r} {rc}")
            print(f"{LOG} dialog ocr: {ocr_util.ocr_hwnd(dlg)[:200]!r}")
            # drive: real-type the name into the Edit, click OK
            edits = [(rc, hh) for t, c, rc, hh in mixing_util.children(dlg)
                     if c == "Edit" and pp.user32.IsWindowVisible(hh)]
            print(f"{LOG} dialog edits: {len(edits)}")
            if edits:
                rc, hh = edits[0]
                new = pp.real_edit_set(session, rc, hh, "m5g_diag_preset")
                print(f"{LOG} name typed: {new!r}")
            oks = [(t, rc, hh) for t, c, rc, hh in mixing_util.children(dlg)
                   if "ok" in t.lower() and t.strip() == "OK"
                   and pp.user32.IsWindowVisible(hh)]
            print(f"{LOG} ok buttons (any class): {[(t) for t, _r, _h in oks]}")
            if edits:
                # ensure 'User Preset' (selection 0) so the preset lands as
                # a datadir file, not only inside the project
                radios = [(t, rc, hh) for t, c, rc, hh
                          in mixing_util.children(dlg)
                          if t.strip() == "User Preset"]
                if radios:
                    from harness import winutil as _wu
                    _t, rr, _hh = radios[0]
                    _wu.user32.SetCursorPos((rr[0] + rr[2]) // 2,
                                            (rr[1] + rr[3]) // 2)
                    time.sleep(0.2)
                    _wu.real_click_screen((rr[0] + rr[2]) // 2,
                                          (rr[1] + rr[3]) // 2)
                    time.sleep(0.8)
                    print(f"{LOG} clicked 'User Preset' radio")
            if oks:
                from harness import winutil
                _t, rc, _hh = oks[0]
                winutil.real_click_screen((rc[0] + rc[2]) // 2,
                                          (rc[1] + rc[3]) // 2)
                time.sleep(3.0)
        # post-save evidence: datadir/process + combo text
        pdir = Path(args.datadir) / "process"
        files = sorted(p.name for p in pdir.glob("*.json")) \
            if pdir.exists() else "NO DIR"
        print(f"{LOG} datadir/process: {files}")
        _r, _h, txt = pp.find_process_preset_combo(session)
        print(f"{LOG} combo text: {txt!r}")
        print(f"{LOG} alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
