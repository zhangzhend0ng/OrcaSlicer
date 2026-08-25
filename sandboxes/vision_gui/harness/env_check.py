# env_check.py — runtime environment preflight for the vision driver.
#
# Python port of the runtime gates from tests/wx_gui/wx_gui_tests_main.cpp
# (windows_sim_env_problem): the OS-level injection hazards discovered during
# the wxUIActionSimulator investigation (ADVERSARIAL_LOOP_JOURNAL.md):
#   1. Remote-control / mirroring layers (NetEase GameViewer etc.) suppress
#      SendInput-style synthetic input -> use MESSAGE-level injection instead.
#   2. zh-CN IME composes synthesized keystrokes into CJK -> irrelevant for
#      message-level WM_CHAR (it carries literal characters), only relevant
#      if the OS-level (SendInput) path is used.
# Plus vision-specific checks: DPI scale (template matching assumes one scale).

import ctypes
import ctypes.wintypes as wt
import subprocess

user32 = ctypes.WinDLL("user32", use_last_error=True)

# Display-adapter markers that indicate a remote-control/mirroring layer.
KNOWN_ADAPTER_MARKERS = [
    "gameviewer", "teamviewer", "anydesk", "sunlogin",
    "todesk", "awesun", "parsec", "vnc",
]

# Services installed by the known remote-control tools (queried via `sc query`,
# which needs no admin rights).
KNOWN_SERVICES = [
    "GameViewerService", "GameViewerServer", "TeamViewer", "AnyDesk",
    "ToDesk_Service", "SunloginClient", "AweSunService", "uvnc_service",
    "Parsec",
]


def detect_remote_control() -> str | None:
    """Return a human-readable finding if a remote-control layer is active."""
    # --- display adapters (same EnumDisplayDevicesW walk as the C++ gate) ---
    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [
            ("cb", wt.DWORD),
            ("DeviceName", wt.WCHAR * 32),
            ("DeviceString", wt.WCHAR * 128),
            ("StateFlags", wt.DWORD),
            ("DeviceID", wt.WCHAR * 128),
            ("DeviceKey", wt.WCHAR * 128),
        ]

    dd = DISPLAY_DEVICEW()
    i = 0
    while True:
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dd), 0):
            break
        name = dd.DeviceString.lower()
        for marker in KNOWN_ADAPTER_MARKERS:
            if marker in name:
                return (f"remote-control display adapter '{dd.DeviceString}' present -> "
                        f"SendInput-style injection is SUPPRESSED; the message-level "
                        f"(SendMessage) injection path is unaffected")
        i += 1

    # --- services ---
    for svc in KNOWN_SERVICES:
        r = subprocess.run(["sc", "query", svc], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and "RUNNING" in r.stdout:
            return (f"remote-control service '{svc}' is RUNNING -> SendInput-style "
                    f"injection is SUPPRESSED; message-level injection is unaffected. "
                    f"Recovery: net stop {svc}")
    return None


def dpi_scale(hwnd: int) -> float:
    """Scale factor of the window's monitor (1.0 = 100%)."""
    try:
        return user32.GetDpiForWindow(hwnd) / 96.0
    except Exception:
        return 1.0


def preflight(hwnd: int | None = None) -> dict:
    """Run all checks; returns a report dict. Non-fatal — callers decide.

    remote_control: finding string or None (affects which injection path is
    usable, NOT whether we can run: message injection + PrintWindow capture
    both work in that environment).
    dpi_scale: float; != 1.0 means templates must be captured at this scale
    (or the display pinned to 100%).
    """
    report = {
        "remote_control": detect_remote_control(),
        "dpi_scale": dpi_scale(hwnd) if hwnd else None,
    }
    if hwnd and abs(report["dpi_scale"] - 1.0) > 0.01:
        report["dpi_warning"] = (
            f"monitor scale is {report['dpi_scale']:.0%} — templates are "
            f"scale-sensitive: capture them at THIS scale, or pin the display to 100%"
        )
    return report


def print_preflight(hwnd: int | None = None) -> dict:
    report = preflight(hwnd)
    print("[env_check] --- preflight ---")
    print(f"[env_check] remote-control layer : {report['remote_control'] or 'none detected'}")
    if hwnd:
        print(f"[env_check] dpi scale            : {report['dpi_scale']:.0%}")
        if "dpi_warning" in report:
            print(f"[env_check] WARNING: {report['dpi_warning']}")
    if report["remote_control"]:
        print("[env_check] => using MESSAGE-level injection (immune); "
              "avoid the SendInput/OS-level path")
    return report


if __name__ == "__main__":
    print_preflight()
