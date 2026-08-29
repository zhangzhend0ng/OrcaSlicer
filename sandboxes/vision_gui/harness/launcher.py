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
import sys
import time
from pathlib import Path

from . import winutil

# App-under-test resolution order (see default_exe):
#   1. ORCA_VISION_APP_EXE env var (any layout, CI/packaged)
#   2. <runner>/orca/snapmaker-orca.exe (packaged layout — app shipped next
#      to the UI shell)
#   3. the dev build (this checkout)
_DEV_EXE = Path(r"C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe")


def default_exe() -> Path:
    env = os.environ.get("ORCA_VISION_APP_EXE")
    if env:
        return Path(env)
    runner_dir = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                  else Path(__file__).resolve().parents[2])
    # PyInstaller 6.x onedir ships add-data under _internal/
    data_dir = runner_dir / "_internal" if (runner_dir / "_internal").exists() else runner_dir
    for bundled in (data_dir / "orca" / "snapmaker-orca.exe",
                    runner_dir / "orca" / "snapmaker-orca.exe"):
        if bundled.exists():
            return bundled
    return _DEV_EXE


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
           wait_window_s: float = 90.0,
           boot_demote_s: float = 12.0) -> AppSession:
    """Launch the app; wait for its main window; return the session.

    `boot_demote_s` runs a passive z-order/style demotion watchdog for that
    many seconds after window discovery (0 disables; the m1/m2/m3 drivers'
    late demote_window() call still re-asserts afterwards).
    """
    exe = Path(exe) if exe else default_exe()
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
    # Remember what the USER was using before we launch: the watchdog hands
    # the foreground back to this window whenever the app grabs it (see the
    # demote_watchdog comment — z-order demotion alone cannot strip an
    # already-held foreground, and the first Show() activation is a race).
    prev_fg = winutil.user32.GetForegroundWindow()
    # NOTE: SW_SHOWNOACTIVATE does NOT actually work for wx — wxMSW Show()
    # calls ShowWindow(SW_SHOW), which activates + raises regardless of the
    # STARTUPINFO wShowWindow (Windows only honors that for SW_SHOWDEFAULT).
    # Left in place because it is free and covers any non-wx helper window;
    # the authoritative no-pop mechanism is the demote_watchdog() below.
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 4  # SW_SHOWNOACTIVATE (ineffective for wx, kept anyway)
    popen = subprocess.Popen(args, env=env, cwd=str(exe.parent), startupinfo=si)
    try:
        hwnd = winutil.find_main_window(popen.pid, timeout_s=wait_window_s)
    except BaseException:
        # Never leak a launched app when window discovery fails.
        popen.kill()
        raise
    # Without early demotion the main frame pops to the TOP of the user's
    # desktop at boot (see the SW_SHOWNOACTIVATE note) and — under the
    # drivers' hands-off rule — sits there ~12s until demote_window()
    # runs. The watchdog closes that hole PASSIVELY: ex-style + HWND_BOTTOM
    # demotion every tick, plus foreground RESTORATION to prev_fg when the
    # app holds it (never foreground-GRABBING or window moves — README
    # pitfall #3). diag_early_stealth.py verifies the CLI model auto-load
    # survives it. Set boot_demote_s=0 for control runs.
    if boot_demote_s > 0:
        winutil.demote_watchdog(pid=popen.pid, duration_s=boot_demote_s,
                                fg_restore_to=prev_fg)
    # NOTE: still do NOT touch window position/foreground here. Early
    # interference (before post_init's first-idle input_files load) BREAKS
    # the CLI model auto-load — proven experimentally: hands-off boots load
    # the model, foreground-grabbing boots do not. Late, conditional
    # repositioning is the caller's job (see m2_slice_chain after boot
    # settles).
    dpi = winutil.get_dpi_for_window(hwnd)
    print(f"[launcher] pid={popen.pid} hwnd=0x{hwnd:x} rect={winutil.window_rect(hwnd)} dpi={dpi}")
    return AppSession(popen, hwnd)
