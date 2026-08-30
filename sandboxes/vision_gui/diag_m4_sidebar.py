#!/usr/bin/env python3
# diag_m4_sidebar.py — one-boot dump of the sidebar physical-filament
# observables (chips / preset combos / title rows / buttons) for the m4
# cases. Boots the standard MIXED_3MF fixture.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import mix_dialog_util as mdu  # noqa: E402
from harness import mixing_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session  # noqa: E402

user32 = mdu.user32


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = wait_model_loaded(session, timeout_s=40)
        print(f"[diag] model loaded: {ok} colored={frac:.2%}")
        time.sleep(2.0)
        frect = winutil.window_rect(session.hwnd)
        print(f"[diag] frame rect: {frect}")

        chips = [(t, r, h) for t, c, r, h in mixing_util.children(session.hwnd)
                 if c == "Static" and t.strip().isdigit()
                 and user32.IsWindowVisible(h)]
        print(f"[diag] digit Statics: {[(t, r) for t, r, _ in chips]}")
        print(f"[diag] physical_filament_count: "
              f"{mdu.physical_filament_count(session)}")

        at = [(t, c, r, h) for t, c, r, h in mixing_util.children(session.hwnd)
              if "@" in t and user32.IsWindowVisible(h)]
        print(f"[diag] '@' texts ({len(at)}):")
        for t, c, r, _h in sorted(at, key=lambda x: (x[2][1], x[2][0])):
            print(f"    {c} {r} {t[:60]!r}")

        for title in ("Filaments", "Color Mixing", "Filament Management"):
            row = mdu._sidebar_title_row(session, title)
            if not row:
                print(f"[diag] title row {title!r}: NONE")
            else:
                print(f"[diag] title row {title!r}: label={row[0]} "
                      f"buttons={row[1]}")
        print(f"[diag] color_mix_bar: {mdu.color_mix_bar(session)}")
        print(f"[diag] filament_row_buttons: "
              f"{mdu.filament_row_buttons(session)}")
        print(f"[diag] mix_entry_labels: "
              f"{[(t, r) for t, r, _h in mdu.mix_entry_labels(session)]}")
        return 0
    finally:
        session.close()
        print("[diag] closed")


if __name__ == "__main__":
    raise SystemExit(main())
