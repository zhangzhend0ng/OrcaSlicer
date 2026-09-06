import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snapmaker_orca_mcp.errors import BridgeError
from snapmaker_orca_mcp.knowledge import mesh_tools

REPO_ROOT = Path(__file__).resolve().parents[3]
BENCHY = REPO_ROOT / "resources" / "handy_models" / "3DBenchy.3mf"


def _box(tmp_path: Path, name="box.stl", extents=(20.0, 30.0, 40.0)):
    import trimesh

    mesh = trimesh.creation.box(extents=extents)
    p = tmp_path / name
    mesh.export(p, file_type="stl")
    return p


def test_analyze_box(tmp_path):
    p = _box(tmp_path)
    out = mesh_tools.analyze_mesh(str(p))
    assert out["objects"] == 1
    assert out["dimensions_mm"] == [20.0, 30.0, 40.0]
    assert abs(out["volume_mm3"] - 20 * 30 * 40) < 1.0
    assert out["is_watertight"] is True
    assert out["triangles"] == 12


def test_analyze_real_3mf_fixture():
    if not BENCHY.is_file():
        pytest.skip("repo 3mf fixture not available")
    out = mesh_tools.analyze_mesh(str(BENCHY))
    assert out["format"] == "3mf"
    assert out["objects"] >= 1
    assert out["volume_mm3"] > 0
    assert out["triangles"] > 100


def test_missing_and_unsupported_paths(tmp_path):
    with pytest.raises(BridgeError) as ei:
        mesh_tools.analyze_mesh(str(tmp_path / "nope.stl"))
    assert ei.value.code == "mesh_missing"
    p = tmp_path / "model.exe"
    p.write_bytes(b"")
    with pytest.raises(BridgeError) as ei2:
        mesh_tools.analyze_mesh(str(p))
    assert ei2.value.code == "unsupported_mesh"


def test_check_printability_size_fail(tmp_path):
    p = _box(tmp_path, extents=(500.0, 30.0, 40.0))
    out = mesh_tools.check_printability(str(p), build_volume_mm=[400, 350, 350])
    assert out["printable"] is False
    assert any("exceeds build volume" in f for f in out["findings"])


def test_check_printability_ok(tmp_path):
    p = _box(tmp_path)
    out = mesh_tools.check_printability(str(p), build_volume_mm=[400, 350, 350])
    assert out["printable"] is True
    assert out["overhangs"]["overhang_area_ratio"] < 0.01  # box has vertical walls


def test_suggest_orientation_flat_best(tmp_path):
    import trimesh

    # A thin plate: standing on edge is worse than lying flat.
    mesh = trimesh.creation.box(extents=(100.0, 100.0, 2.0))
    p = tmp_path / "plate.stl"
    mesh.export(p, file_type="stl")
    out = mesh_tools.suggest_orientation(str(p))
    assert out["recommended"] in ("as_loaded", "rot_180_deg_x", "rot_180_deg_y")
    best = out["candidates"][0]
    assert best["overhang_ratio"] <= out["candidates"][-1]["overhang_ratio"]


def test_estimate_cost_sanity(tmp_path):
    p = _box(tmp_path, extents=(50.0, 50.0, 20.0))
    out = mesh_tools.estimate_cost(
        str(p),
        infill_density_pct=20.0,
        filament_density_g_cm3=1.24,
        filament_price_per_kg=20.0,
    )
    assert 0 < out["extruded_volume_mm3"] <= 50 * 50 * 20
    assert 0 < out["filament_weight_g"] < 200
    assert out["material_cost"] == pytest.approx(
        out["filament_weight_g"] / 1000 * 20.0, abs=1e-2
    )
    assert out["estimated_time_s"] > 0


def test_estimate_cost_nonpositive_volume(tmp_path):
    import trimesh

    p = tmp_path / "open.stl"
    trimesh.Trimesh(
        vertices=[[0, 0, 0], [1, 0, 0], [0, 1, 0]],
        faces=[[0, 1, 2]],
        process=False,
    ).export(p, file_type="stl")
    with pytest.raises(BridgeError) as ei:
        mesh_tools.estimate_cost(str(p))
    assert ei.value.code == "bad_volume"
