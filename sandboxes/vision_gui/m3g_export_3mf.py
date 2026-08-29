#!/usr/bin/env python3
# m3g_export_3mf.py — P0-4: export 3mf writes a real artifact that reloads
# as a project.
#
# White-box ref: wx_gui_business_tests.cpp:421 — export_3mf produces a
# non-empty artifact that reloads with the same scene and the U1 printer
# preset intact.
# Source facts: the topbar File tool (ID_TOP_FILE_MENU, BBLTopbar.cpp:213)
# opens the File menu whose 'Save Project as' item (MainFrame.cpp:2562,
# handler Plater::save_project(true), gate can_save_as) shows the FT_3MF
# wxFileDialog ('Save file as:', Plater.cpp get_export_file) and exports via
# export_3mf(SplitModel|ShareMesh|FullPathSources).
#
# Black-box path: load mixed_filament_test.3mf -> open the File menu
# (SetCursorPos + message click) -> dispatch WM_COMMAND for 'Save Project
# as' (the same message a real selection produces; wx dispatches it through
# the current popup menu) -> the native save dialog appears -> type a unique
# path -> IDOK -> the file lands. Then relaunch the app with the exported
# file and assert the model arrives (viewport chromaticity >= 1%) and that
# the embedded U1 preset survived the round trip (zip content).

import re
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from harness import export_util, topbar_util, winutil  # noqa: E402
from m2_slice_chain import wait_model_loaded  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, verdict  # noqa: E402

U1_PRESET = "Snapmaker U1 (0.8 nozzle)"


def save_project_as(session, out_path: Path, timeout_s: float = 30.0) -> bool:
    """File menu -> 'Save Project as' -> native dialog -> type -> IDOK."""
    menu = topbar_util.open_file_menu(session)
    if not menu:
        print("[m3g] file menu did not open")
        return False
    _rect, _hwnd, hmenu = menu
    idx = topbar_util.find_item(hmenu, "Save Project as")
    if idx is None:
        print("[m3g] 'Save Project as' not in the file menu")
        topbar_util.close_menu_windows(session.pid)
        return False
    print(f"[m3g] 'Save Project as' at index {idx}, dispatching WM_COMMAND")
    topbar_util.activate_menu_item(session, hmenu, idx)
    # the send may time out while the app opens the modal save dialog
    dlg = export_util.wait_save_dialog(session.pid, timeout_s=10.0)
    topbar_util.close_menu_windows(session.pid)
    if not dlg:
        print("[m3g] save dialog did not appear")
        return False
    print(f"[m3g] save dialog '{dlg[1]}'")
    edit = export_util.find_edit(dlg[3])
    if edit is None:
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(out_path))
    import ctypes
    user32 = ctypes.WinDLL("user32")
    user32.SendMessageW(dlg[3], 0x0111, 1, 0)  # WM_COMMAND, IDOK = 1
    return export_util.wait_file(out_path, timeout_s=timeout_s)


def inspect_3mf(path: Path):
    """(is_zip, has_model, preset_line) — pure filesystem observation."""
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        return False, False, None
    names = z.namelist()
    has_model = "3D/3dmodel.model" in names
    preset = None
    if "Metadata/project_settings.config" in names:
        data = z.read("Metadata/project_settings.config").decode("utf-8",
                                                                 "replace")
        m = re.search(r'"printer_settings_id"\s*:\s*"([^"]+)"', data)
        if m:
            preset = m.group(1)
    return True, has_model, preset


def main() -> int:
    ap = __import__("argparse").ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    out_path = Path(args.datadir).parent / "m3g_export.3mf"
    if out_path.exists():
        out_path.unlink()

    session = boot_session(args, model=args.model)
    try:
        ok_model, frac = wait_model_loaded(session, timeout_s=30)
        print(f"[m3g] model arrived: {ok_model} (colored {frac:.2%})")
        results["project loads"] = "PASS" if ok_model else "FAIL"

        # --- File menu -> Save Project as -> file lands ---
        ok_save = save_project_as(session, out_path)
        print(f"[m3g] save-as produced file: {ok_save} "
              f"({out_path.stat().st_size if out_path.exists() else 0}B)")
        results["export 3mf via File menu"] = "PASS" if ok_save else "FAIL"

        # --- the artifact must be a real project: zip + model + U1 preset ---
        is_zip, has_model, preset = inspect_3mf(out_path)
        print(f"[m3g] artifact: zip={is_zip} model={has_model} "
              f"printer={preset!r}")
        results["artifact is a 3mf project"] = (
            "PASS" if (is_zip and has_model) else "FAIL")
        results["U1 preset survives round trip"] = (
            "PASS" if preset == U1_PRESET else "FAIL")
    finally:
        session.close()
        print("[m3g] app closed")

    # --- reload the artifact in a FRESH session (fresh datadir) ---
    args.datadir = Path(args.datadir).parent / "m3g_profile_b"
    session2 = boot_session(args, model=out_path)
    try:
        ok_re, frac2 = wait_model_loaded(session2, timeout_s=45)
        print(f"[m3g] reloaded model arrives: {ok_re} (colored {frac2:.2%})")
        results["exported 3mf reloads as project"] = (
            "PASS" if ok_re else "FAIL")
    finally:
        session2.close()
        print("[m3g] app closed")

    return verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
