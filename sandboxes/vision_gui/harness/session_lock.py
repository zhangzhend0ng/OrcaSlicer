# session_lock.py — single-driver mutual exclusion for the vision sandbox.
#
# The unified human/AI entry (README "人机统一入口") allows exactly ONE
# driver at a time: the CustomTkinter UI runner and the MCP server (AI
# agents) both take this lock around any app-driving activity. Lock file:
#   %LOCALAPPDATA%\vision_gui\mcp_session.lock  (content = holder pid)
# Stale locks (dead holder) are detected via process liveness and broken.

import ctypes
import os
from pathlib import Path

LOCK = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "vision_gui" / "mcp_session.lock"


def _kernel32():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    return k


def pid_alive(pid: int) -> bool:
    k = _kernel32()
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    k.CloseHandle(h)
    return True


def holder() -> int | None:
    """Live holder pid, or None when free/stale (a stale file is not held)."""
    try:
        pid = int(LOCK.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    if pid == os.getpid() or pid_alive(pid):
        return pid
    return None


def acquire() -> tuple[bool, str]:
    """Take the lock; (True, '') on success, (False, reason) when held."""
    try:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        current = holder()
        if current is not None and current != os.getpid():
            return False, f"held by live pid {current} (UI runner or another agent)"
        LOCK.write_text(str(os.getpid()))
        return True, ""
    except OSError as e:
        return False, str(e)


def release() -> None:
    """Release only OUR own lock file (never break someone else's)."""
    try:
        if LOCK.exists() and LOCK.read_text().strip() == str(os.getpid()):
            LOCK.unlink()
    except OSError:
        pass
