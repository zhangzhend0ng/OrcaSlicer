"""Path and environment discovery for the bridge.

Resolution order for every setting: explicit constructor argument, then
environment variable, then platform default. Nothing here talks to Orca.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

from .errors import BridgeError

# Discovery file written by the Orca in-process listener (M1+). Contains
# {"port": <int>, "token": <hex>} so the bridge never hardcodes the port
# (the legacy HttpServer drifts +1000 when the port is taken - see
# HttpServer.cpp:491-494 - so discovery by file is mandatory).
DISCOVERY_FILE_ENV = "SNAPMAKER_ORCA_MCP_DISCOVERY"
DEFAULT_DISCOVERY_NAME = "mcp_session.json"


def _default_exe_candidates() -> list[Path]:
    """Common install locations for snapmaker-orca.exe / Snapmaker_Orca."""
    system = platform.system()
    out: list[Path] = []
    if system == "Windows":
        exe_names = ["snapmaker-orca.exe", "Snapmaker_Orca.exe"]
        bases = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Snapmaker Orca",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Snapmaker Orca",
        ]
        for base in bases:
            for name in exe_names:
                out.append(base / name)
    elif system == "Darwin":
        out.append(Path("/Applications/OrcaSlicer.app/Contents/MacOS/Snapmaker_Orca"))
    else:
        out.append(Path("/usr/local/bin/snapmaker-orca"))
        out.append(Path("/usr/bin/snapmaker-orca"))
    return out


class BridgeConfig:
    """Resolved locations the bridge needs."""

    def __init__(
        self,
        *,
        exe_path: str | os.PathLike[str] | None = None,
        resources_dir: str | os.PathLike[str] | None = None,
        data_dir: str | os.PathLike[str] | None = None,
        discovery_file: str | os.PathLike[str] | None = None,
        default_timeout_s: float = 1800.0,
    ) -> None:
        self._exe_override = Path(exe_path) if exe_path else None
        env_exe = os.environ.get("SNAPMAKER_ORCA_EXE")
        if self._exe_override is None and env_exe:
            self._exe_override = Path(env_exe)
        self._resources_override = (
            Path(resources_dir) if resources_dir else None
        )
        env_res = os.environ.get("SNAPMAKER_ORCA_RESOURCES")
        if self._resources_override is None and env_res:
            self._resources_override = Path(env_res)
        self._data_override = Path(data_dir) if data_dir else None
        env_data = os.environ.get("SNAPMAKER_ORCA_DATA_DIR")
        if self._data_override is None and env_data:
            self._data_override = Path(env_data)
        self._discovery_override = (
            Path(discovery_file) if discovery_file else None
        )
        env_disc = os.environ.get(DISCOVERY_FILE_ENV)
        if self._discovery_override is None and env_disc:
            self._discovery_override = Path(env_disc)
        self.default_timeout_s = default_timeout_s

    # ---- executable -----------------------------------------------------

    def find_exe(self) -> Path:
        """Locate the Orca executable, raising BridgeError if absent.

        On Windows prefer the GUI shim snapmaker-orca.exe (loads
        Snapmaker_Orca.dll and forwards CLI args); both spellings work for
        headless CLI runs.
        """
        if self._exe_override is not None:
            if self._exe_override.is_file():
                return self._exe_override
            raise BridgeError(
                f"SNAPMAKER_ORCA_EXE does not exist: {self._exe_override}",
                code="exe_not_found",
            )
        for cand in _default_exe_candidates():
            if cand.is_file():
                return cand
        raise BridgeError(
            "Snapmaker Orca executable not found. Set SNAPMAKER_ORCA_EXE.",
            code="exe_not_found",
        )

    # ---- resources ------------------------------------------------------

    def find_resources_dir(self) -> Path | None:
        """Locate the Orca resources/ directory (may be absent)."""
        if self._resources_override is not None:
            return self._resources_override if self._resources_override.is_dir() else None
        try:
            exe = self.find_exe()
        except BridgeError:
            return None
        for cand in (exe.parent / "resources", exe.parent.parent / "resources"):
            if cand.is_dir():
                return cand
        return None

    # ---- data dir -------------------------------------------------------

    def data_dir(self) -> Path | None:
        return self._data_override

    # ---- session discovery (M1+) ----------------------------------------

    def discovery_file(self) -> Path:
        if self._discovery_override is not None:
            return self._discovery_override
        data = self._data_override
        if data is None:
            env_data = os.environ.get("SNAPMAKER_ORCA_DATA_DIR")
            if env_data:
                data = Path(env_data)
        name = DEFAULT_DISCOVERY_NAME
        if data is not None:
            return data / name
        # Fall back next to the bridge package for tests.
        return Path(os.environ.get("TEMP", "/tmp")) / name
