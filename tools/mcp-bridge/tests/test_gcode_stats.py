import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snapmaker_orca_mcp.errors import BridgeError
from snapmaker_orca_mcp.gcode_stats import _parse_duration, parse_gcode_stats

FOOTER = """; estimated printing time (normal mode) = 34m 54s
; total filament used [g] = 4.19
; total filament cost = 0.08
; total filament change = 2
; total layers count = 125
; filament used [cm3] = 3.38
; filament used [mm] = 1340.5
; CONFIG_BLOCK_START
; layer_height = 0.2
"""


def test_duration_parsing():
    assert _parse_duration("34m 54s") == 34 * 60 + 54
    assert _parse_duration("1h 2m 3s") == 3723
    assert _parse_duration("2d 4h") == 2 * 86400 + 4 * 3600
    assert _parse_duration("nonsense") is None


def test_parse_footer_stats(tmp_path: Path):
    gcode = tmp_path / "plate_1.gcode"
    gcode.write_text("; header\nG1 X0\n" + FOOTER, encoding="utf-8")
    stats = parse_gcode_stats(gcode)
    assert stats["filament_used_g"] == 4.19
    assert stats["filament_cost"] == 0.08
    assert stats["filament_changes"] == 2
    assert stats["layers"] == 125
    assert stats["filament_used_cm3"] == [3.38]
    assert stats["filament_used_mm"] == [1340.5]
    assert stats["estimated_time_s"] == 34 * 60 + 54
    assert stats["estimated_time_human"] == "34m 54s"


def test_missing_gcode_raises():
    with pytest.raises(BridgeError) as ei:
        parse_gcode_stats("Z:/definitely/missing.gcode")
    assert ei.value.code == "gcode_missing"


def test_malformed_lines_are_tolerated(tmp_path: Path):
    gcode = tmp_path / "plate_1.gcode"
    gcode.write_text(
        "; total filament used [g] = oops\n; total layers count = 7\n",
        encoding="utf-8",
    )
    stats = parse_gcode_stats(gcode)
    assert "filament_used_g" not in stats
    assert stats["layers"] == 7


def test_only_tail_is_read(tmp_path: Path):
    gcode = tmp_path / "big.gcode"
    gcode.write_text("; total layers count = 1\n" + ("G1 X1 Y1\n" * 100_000), encoding="utf-8")
    gcode.with_name("big.gcode").write_bytes(
        gcode.read_bytes() + FOOTER.encode("utf-8")
    )
    stats = parse_gcode_stats(gcode)
    assert stats["layers"] == 125  # footer value wins; header ignored


def test_footer_json_shape(tmp_path: Path):
    gcode = tmp_path / "plate_1.gcode"
    gcode.write_text(FOOTER, encoding="utf-8")
    stats = parse_gcode_stats(gcode)
    json.dumps(stats)  # must be serializable for MCP payloads
