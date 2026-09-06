"""Resolve Orca system preset JSONs including their ``inherits`` chain.

The Orca CLI (``--load-settings`` / ``--load-filaments``) loads exactly one
file per category and does **not** follow the ``inherits`` chain. System
profiles ship as thin variant overlays (e.g. ``Snapmaker Artisan (0.4
nozzle).json`` -> ``fdm_a400.json`` -> ... -> ``fdm_common.json``), so the
bridge merges each chain into a single temp file: base first, child keys
override, ``inherits`` removed from the result.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .errors import BridgeError

CATEGORY_DIRS = {
    "machine": "machine",
    "process": "process",
    "filament": "filament",
}


def find_preset_file(
    resources_dir: Path,
    category: str,
    name_or_path: str,
) -> Path:
    """Resolve a preset by absolute path or by preset name within its dir."""
    if category not in CATEGORY_DIRS:
        raise BridgeError(
            f"unknown preset category: {category}", code="bad_preset_category"
        )
    direct = Path(name_or_path)
    if direct.suffix.lower() == ".json" and direct.is_file():
        return direct
    base = resources_dir / "profiles" / "Snapmaker" / CATEGORY_DIRS[category]
    stem = direct.stem if direct.suffix.lower() == ".json" else str(direct)
    candidate = base / f"{stem}.json"
    if candidate.is_file():
        return candidate
    # Preset file names may embed printer suffixes; fall back to a scan.
    lowered = stem.lower()
    if base.is_dir():
        for entry in sorted(base.glob("*.json")):
            if entry.stem.lower() == lowered:
                return entry
    raise BridgeError(
        f"preset not found: {name_or_path} (category={category}, "
        f"searched {base})",
        code="preset_not_found",
    )


def merge_inherit_chain(preset_path: Path) -> dict:
    """Flatten one preset JSON (following ``inherits`` within its directory)."""
    chain: list[tuple[Path, dict]] = []
    seen: set[str] = set()
    current: Path | None = Path(preset_path)
    while current is not None:
        key = str(current).lower()
        if key in seen:
            raise BridgeError(
                f"inherit cycle detected at {current}", code="preset_cycle"
            )
        seen.add(key)
        if not current.is_file():
            raise BridgeError(
                f"preset parent not found: {current}", code="preset_not_found"
            )
        with current.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        chain.append((current, data))
        parent = data.get("inherits")
        if parent:
            current = current.parent / f"{parent}.json"
            if not current.is_file():
                # Parent presets may live one level up for some vendors.
                alt = current.parent.parent / f"{parent}.json"
                current = alt if alt.is_file() else None
                if current is None:
                    raise BridgeError(
                        f"missing preset parent '{parent}.json' for "
                        f"{chain[-1][0].name}",
                        code="preset_not_found",
                    )
        else:
            current = None
    merged: dict = {}
    for _, data in reversed(chain):
        merged.update(data)
    merged.pop("inherits", None)
    # Keep the descriptor fields of the requested (child, chain[0]) preset.
    for field in ("name", "type", "from", "version"):
        if field in chain[0][1]:
            merged[field] = chain[0][1][field]
    return merged


def write_merged_preset(preset_path: Path, work_dir: Path) -> Path:
    """Write the flattened preset to work_dir and return its path."""
    merged = merge_inherit_chain(preset_path)
    out_name = f"_mcp_merged_{preset_path.stem}.json"
    out_path = work_dir / out_name
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=1)
    return out_path


def prepare_preset_files(
    resources_dir: Path,
    machine: str | None,
    process: str | None,
    filaments: list[str] | None,
    work_dir: Path | None = None,
) -> dict:
    """Resolve all requested presets to merged temp files.

    Returns {"machine": path|None, "process": path|None, "filaments": [paths]}
    """
    work_dir = work_dir or Path(tempfile.mkdtemp(prefix="orca_mcp_presets_"))
    work_dir.mkdir(parents=True, exist_ok=True)
    out: dict = {"machine": None, "process": None, "filaments": []}
    if machine:
        out["machine"] = str(
            write_merged_preset(find_preset_file(resources_dir, "machine", machine), work_dir)
        )
    if process:
        out["process"] = str(
            write_merged_preset(find_preset_file(resources_dir, "process", process), work_dir)
        )
    for fila in filaments or []:
        out["filaments"].append(
            str(
                write_merged_preset(find_preset_file(resources_dir, "filament", fila), work_dir)
            )
        )
    return out
