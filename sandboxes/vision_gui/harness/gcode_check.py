#!/usr/bin/env python3
# gcode_check.py — assertions over the EXPORTED gcode text.
#
# Orca echoes the active PrintConfig into the gcode header as '; key = value'
# lines (measured: '; layer_height = 0.4', '; wall_loops = ...', the
# mixed_filament_definitions block, etc.) — the strongest black-box evidence
# that a parameter change REACHED the slicer (m3e/m4i precedent).

import re


def config_value(data: bytes, key: str):
    """Value of the '; key = value' config echo, or None when absent.
    `data` is the raw gcode (bytes); both are matched ASCII-loose."""
    pat = re.compile(rb";\s*" + re.escape(key.encode()) + rb"\s*=\s*([^\r\n]*)",
                     re.IGNORECASE)
    m = pat.search(data)
    if not m:
        return None
    return m.group(1).decode("ascii", errors="replace").strip()


def config_value_all(data: bytes, key: str):
    """Every '; key = value' echo (extruder-keyed configs repeat)."""
    pat = re.compile(rb";\s*" + re.escape(key.encode()) + rb"\s*=\s*([^\r\n]*)",
                     re.IGNORECASE)
    return [m.group(1).decode("ascii", errors="replace").strip()
            for m in pat.finditer(data)]


def distinct_tool_changes(data: bytes) -> dict:
    """{b'T<n>': count} of plain tool-change commands (m4i convention)."""
    markers = {}
    for m in re.finditer(rb"^T(\d+)", data, re.M):
        markers[b"T" + m.group(1)] = markers.get(b"T" + m.group(1), 0) + 1
    return markers
