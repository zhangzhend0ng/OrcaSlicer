"""Parse the statistics footer Orca writes into exported G-code.

Snapmaker/Orca (non-BBL printer) footers contain lines like::

    ; filament used [cm3] = 3.38
    ; total filament used [g] = 4.19
    ; total filament cost = 0.08
    ; total layers count = 125
    ; estimated printing time (normal mode) = 34m 54s

The parser is deliberately tolerant: it only reads ``;`` comment lines and
never trusts anything outside the footer format.
"""

from __future__ import annotations

import re
from pathlib import Path

from .errors import BridgeError

_TIME_PART = re.compile(r"(\d+)\s*(d|h|m|s)")


def _parse_duration(text: str) -> int | None:
    """'1h 2m 3s' -> seconds; returns None when nothing parses."""
    total = 0
    matched = False
    for value, unit in _TIME_PART.findall(text):
        total += int(value) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[unit]
        matched = True
    return total if matched else None


def parse_gcode_stats(gcode_path: str | Path) -> dict:
    """Extract the statistics footer from a G-code file.

    Reads only the tail of the file (the footer is the last ~64 KiB) so huge
    G-code files stay cheap to analyse.
    """
    path = Path(gcode_path)
    if not path.is_file():
        raise BridgeError(f"gcode file not found: {path}", code="gcode_missing")

    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        fh.seek(max(0, size - 65536))
        tail = fh.read().decode("utf-8", errors="replace")

    stats: dict = {
        "gcode_file": str(path),
        "file_size_bytes": size,
    }
    filament_cm3: list[float] = []
    filament_mm: list[float] = []
    for raw in tail.splitlines():
        line = raw.strip()
        if not line.startswith(";"):
            continue
        body = line[1:].strip()
        key, sep, value = body.partition("=")
        if not sep:
            key, sep, value = body.partition(":")
            if not sep:
                continue
        key = key.strip().lower()
        value = value.strip()
        try:
            if key == "filament used [cm3]":
                filament_cm3.extend(float(v) for v in value.split(","))
            elif key == "filament used [mm]":
                filament_mm.extend(float(v) for v in value.split(","))
            elif key == "total filament used [g]":
                stats["filament_used_g"] = round(float(value), 3)
            elif key == "total filament cost":
                stats["filament_cost"] = round(float(value), 3)
            elif key == "total filament change":
                stats["filament_changes"] = int(value)
            elif key == "total layers count":
                stats["layers"] = int(value)
            elif key.startswith("estimated printing time"):
                seconds = _parse_duration(value)
                if seconds is not None:
                    stats["estimated_time_s"] = seconds
        except ValueError:
            # Malformed footer line: skip rather than fail the whole parse.
            continue
    if filament_cm3:
        stats["filament_used_cm3"] = filament_cm3
    if filament_mm:
        stats["filament_used_mm"] = filament_mm
    if "estimated_time_s" in stats:
        stats.setdefault("estimated_time_human", _human_time(stats["estimated_time_s"]))
    return stats


def _human_time(seconds: int) -> str:
    out = []
    for unit, div in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= div or (unit == "s" and not out):
            value, seconds = divmod(seconds, div)
            out.append(f"{value}{unit}")
    return " ".join(out)
