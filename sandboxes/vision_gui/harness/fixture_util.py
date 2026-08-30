#!/usr/bin/env python3
# fixture_util.py — craft 3mf fixture variants for the mixing cases.
#
# The mixed_filament_test.3mf embeds 5 filaments (F1 Generic PETG +
# F2..F5 Snapmaker PLA Silk). The compatibility matrix cases need MORE
# filament TYPES (ABS/ASA/TPU/PA/PC/PVA/BVOH) and m4f needs 64 slots.
# This helper clones the fixture and rewrites Metadata/
# project_settings.config: every per-filament list (length == the source
# filament count) is extended to the new count, then filament_colour /
# filament_type / filament_settings_id are replaced.
#
# The compatibility gate maps filament_type -> category via a hardcoded
# table (MixedColorMatchHelpers.cpp:1120-1143) and the pair matrix from
# resources/profiles/Snapmaker/filament/filament_compatibility.json, so
# the TYPE carries the semantics; the preset id is only the display hint
# (Generic @U1 0.8 variants exist for PLA/PETG/TPU, base names for the
# rest).

import json
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
FIXTURES = HERE.parent.parent / "tests" / "data" / "test_3mf"
MIXED_3MF = FIXTURES / "mixed_filament_test.3mf"

ART_FIXTURES = HERE / "artifacts" / "fixtures"


def craft_filaments_fixture(dest, colours, types, settings_ids=None,
                            src=MIXED_3MF, strip_mixed=False):
    """Clone `src` into `dest` with the given filament table.

    strip_mixed=True also removes the project's
    'mixed_filament_definitions' key (both load sites guard on
    !empty, Plater.cpp:2690/:7406, so absence is safe) — used by the
    batch-gate cases that need filaments WITHOUT a seeded scheme."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    n0 = len(json.loads(zipfile.ZipFile(src).read(
        "Metadata/project_settings.config").decode("utf-8"))
        ["filament_colour"])
    n1 = len(colours)
    zin = zipfile.ZipFile(src)
    cfg = json.loads(zin.read("Metadata/project_settings.config")
                     .decode("utf-8"))
    for key, value in cfg.items():
        if isinstance(value, list) and len(value) == n0 and n1 > n0:
            value.extend([value[-1]] * (n1 - n0))
    cfg["filament_colour"] = list(colours)
    cfg["filament_type"] = list(types)
    if settings_ids:
        cfg["filament_settings_id"] = list(settings_ids)
    if strip_mixed:
        cfg.pop("mixed_filament_definitions", None)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "Metadata/project_settings.config":
                zout.writestr(item, json.dumps(cfg, indent=4))
            else:
                zout.writestr(item, zin.read(item.filename))
    zin.close()
    return dest


def dismiss_custom_preset_dialog(session, timeout_s: float = 20.0) -> bool:
    """A crafted fixture (modified filament table) pops the 'Customized
    Preset' RichDialog on load; OK accepts the customizations and the
    load proceeds. Poll-and-click from the case right after boot."""
    import time as _t
    from . import mixing_util
    deadline = _t.monotonic() + timeout_s
    while _t.monotonic() < deadline:
        for cls, txt, rect, hwnd in mixing_util.toplevel(session.pid):
            if cls == "#32770" and "Customized Preset" in txt:
                mixing_util.click_button(hwnd, "OK")
                _t.sleep(1.0)
                return True
        _t.sleep(0.5)
    return False
