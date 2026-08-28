# launcher.py — start the REAL app as a black-box child process and locate its
# main window. Deliberately environment-clean:
#   - ORCA_GUI_TEST_MODE is REMOVED from the child env (it hides the window —
#     GUI_App.cpp skips mainframe->Show(true) in test mode; a vision driver
#     needs the window visible).
#   - isolation comes from --datadir pointing at a seeded sandbox profile
#     (see profile.py), never from the user's real datadir.
#   - a 3mf/stl passed as `model` is auto-loaded by the app's own startup
#     file-loading path (GUI_App::post_init -> plater()->load_files).

import os
import subprocess
import time
from pathlib import Path

from . import winutil

DEFAULT_EXE = Path(r"C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe")


class AppSession:
    def __init__(self, popen: subprocess.Popen, hwnd: int):
        self.popen = popen
        self.hwnd = hwnd

    @property
    def pid(self) -> int:
        return self.popen.pid

    def rect(self) -> tuple[int, int, int, int]:
        return winutil.window_rect(self.hwnd)

    def alive(self) -> bool:
        return self.popen.poll() is None

    def close(self, timeout_s: float = 10.0) -> None:
        """Graceful WM_CLOSE, then wait, then hard kill."""
        if not self.alive():
            return
        winutil.close_window(self.hwnd)
        deadline = time.monotonic() + timeout_s
        while self.alive() and time.monotonic() < deadline:
            time.sleep(0.5)
        if self.alive():
            self.popen.kill()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def launch(exe: Path | str | None = None,
           datadir: Path | str | None = None,
           model: Path | str | None = None,
           wait_window_s: float = 90.0) -> AppSession:
    """Launch the app; wait for its main window; return the session."""
    exe = Path(exe) if exe else DEFAULT_EXE
    if not exe.exists():
        raise FileNotFoundError(f"app exe not found: {exe} (pass --exe)")
    if datadir is None:
        raise ValueError("datadir is required (isolation!) — seed one via profile.seed_profile()")

    args = [str(exe), "--datadir", str(datadir)]
    if model:
        model = Path(model)
        if not model.exists():
            raise FileNotFoundError(f"model not found: {model}")
        args.append(str(model))

    env = {k: v for (k, v) in os.environ.items() if k.upper() != "ORCA_GUI_TEST_MODE"}
    print(f"[launcher] {args[0]} --datadir {args[2]}" + (f" {args[3]}" if model else ""))

    winutil.make_dpi_aware()
    # SW_SHOWNOACTIVATE: show the window WITHOUT activating/raising it, so
    # the app never steals focus from whatever the user is doing. wx may or
    # may not honor it; the late background_tool_window() call in the
    # drivers is the authoritative enforcement.
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 4  # SW_SHOWNOACTIVATE
    popen = subprocess.Popen(args, env=env, cwd=str(exe.parent), startupinfo=si)
    try:
        hwnd = winutil.find_main_window(popen.pid, timeout_s=wait_window_s)
    except BaseException:
        # Never leak a launched app when window discovery fails.
        popen.kill()
        raise
    # NOTE: do NOT touch window position/foreground here. Early interference
    # (before post_init's first-idle input_files load) BREAKS the CLI model
    # auto-load — proven experimentally: hands-off boots load the model,
    # foreground-grabbing boots do not. Late, conditional repositioning is
    # the caller's job (see m2_slice_chain after boot settles).
    dpi = winutil.get_dpi_for_window(hwnd)
    print(f"[launcher] pid={popen.pid} hwnd=0x{hwnd:x} rect={winutil.window_rect(hwnd)} dpi={dpi}")
    return AppSession(popen, hwnd)
