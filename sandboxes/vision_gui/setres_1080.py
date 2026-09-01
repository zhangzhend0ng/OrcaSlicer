#!/usr/bin/env python3
# setres_1080.py — pin the guest display to 1920x1080 from INSIDE the
# interactive session (the Hyper-V console auto-degrades the mode to
# 1024x768 when no console is attached, which breaks every maximized-window
# calibration; measured 09-01). Run via hv_go so it lands in the
# INTERACTIVE session.
import ctypes
import sys


def main() -> int:
    user32 = ctypes.WinDLL("user32")


    class DEVMODE(ctypes.Structure):
        _fields_ = [("dmDeviceName", ctypes.c_wchar * 32),
                    ("dmSpecVersion", ctypes.c_ushort),
                    ("dmDriverVersion", ctypes.c_ushort),
                    ("dmSize", ctypes.c_ushort),
                    ("dmDriverExtra", ctypes.c_ushort),
                    ("dmFields", ctypes.c_ulong),
                    ("dmPosition", ctypes.c_long * 2),
                    ("dmDisplayOrientation", ctypes.c_ulong),
                    ("dmDisplayFixedOutput", ctypes.c_ulong),
                    ("dmColor", ctypes.c_short),
                    ("dmDuplex", ctypes.c_short),
                    ("dmYResolution", ctypes.c_short),
                    ("dmTTOption", ctypes.c_short),
                    ("dmCollate", ctypes.c_short),
                    ("dmFormName", ctypes.c_wchar * 32),
                    ("dmLogPixels", ctypes.c_ushort),
                    ("dmBitsPerPel", ctypes.c_ulong),
                    ("dmPelsWidth", ctypes.c_ulong),
                    ("dmPelsHeight", ctypes.c_ulong),
                    ("dmDisplayFlags", ctypes.c_ulong),
                    ("dmDisplayFrequency", ctypes.c_ulong),
                    ("dmICMMethod", ctypes.c_ulong),
                    ("dmICMIntent", ctypes.c_ulong),
                    ("dmMediaType", ctypes.c_ulong),
                    ("dmDitherType", ctypes.c_ulong),
                    ("dmReserved1", ctypes.c_ulong),
                    ("dmReserved2", ctypes.c_ulong),
                    ("dmPanningWidth", ctypes.c_ulong),
                    ("dmPanningHeight", ctypes.c_ulong)]


    dm = DEVMODE()
    dm.dmSize = ctypes.sizeof(DEVMODE)
    dm.dmFields = 0x180000  # DM_PELSWIDTH | DM_PELSHEIGHT
    dm.dmPelsWidth = 1920
    dm.dmPelsHeight = 1080
    CDS_UPDATEREGISTRY = 0x00000001
    r = user32.ChangeDisplaySettingsW(ctypes.byref(dm), CDS_UPDATEREGISTRY)
    print(f"[setres] ChangeDisplaySettings rc={r} (0 = OK)")
    print(f"[setres] interactive screen now: "
          f"{user32.GetSystemMetrics(0)}x{user32.GetSystemMetrics(1)}")
    print(f"[setres] GREEN" if r == 0 else f"[setres] RED")
    return 0 if r == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
