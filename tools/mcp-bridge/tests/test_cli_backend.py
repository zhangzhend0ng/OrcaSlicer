import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snapmaker_orca_mcp.cli_backend import CliBackend
from snapmaker_orca_mcp.config import BridgeConfig
from snapmaker_orca_mcp.errors import BridgeError


class _NoCatalog:
    def has_option(self, key: str) -> bool:
        return False


@pytest.fixture
def backend(tmp_path):
    cfg = BridgeConfig(
        exe_path=tmp_path / "fake-orca.exe",
        resources_dir=tmp_path / "res",
        data_dir=tmp_path / "data",
    )
    (tmp_path / "fake-orca.exe").write_text("")
    return CliBackend(cfg)


def _make_model(tmp_path, name="model.stl"):
    p = tmp_path / name
    p.write_bytes(b"solid x\nendsolid x\n")
    return p


def test_build_slice_command_shape(backend, tmp_path):
    model = _make_model(tmp_path)
    presets = {
        "machine": str(tmp_path / "m.json"),
        "process": str(tmp_path / "p.json"),
        "filaments": [str(tmp_path / "f.json")],
    }
    cmd = backend.build_slice_command(
        model,
        tmp_path / "out",
        plate=2,
        overrides={"layer_height": 0.16, "sparse_infill_density": "25%"},
        presets=presets,
        allow_newer_file=True,
    )
    assert "--allow-newer-file" in cmd
    assert f"--datadir={tmp_path / 'data'}" in cmd
    assert f"--load-settings={tmp_path / 'm.json'};{tmp_path / 'p.json'}" in cmd
    assert f"--load-filaments={tmp_path / 'f.json'}" in cmd
    # without a catalog, keys fall back to dash form (read_cli convention)
    assert "--layer-height=0.16" in cmd
    assert "--sparse-infill-density=25%" in cmd
    assert "--slice=2" in cmd
    assert cmd[-1] == str(model)


def test_cli_token_uses_catalog_alias(backend, tmp_path):
    class _AliasCatalog:
        def has_option(self, key):
            return key == "layer_height"

        options = {"layer_height": {"cli": "layer-height|lh"}}

    backend._catalog = _AliasCatalog()
    assert backend._cli_token_for("layer_height") == "layer-height"


def test_managed_keys_cannot_be_overridden(backend):
    for key in ("slice", "outputdir", "export_3mf", "load_settings"):
        with pytest.raises(BridgeError) as ei:
            backend._validate_override_key(key)
        assert ei.value.code == "forbidden_override"


def test_unknown_key_rejected_with_catalog(backend, tmp_path):
    backend._catalog = _NoCatalog()  # strict catalog: nothing is "known"
    model = _make_model(tmp_path)
    with pytest.raises(BridgeError) as ei:
        backend.build_slice_command(
            model,
            tmp_path / "out",
            1,
            overrides={"definitely_not_a_param": 1},
            presets={"machine": None, "process": None, "filaments": []},
            allow_newer_file=False,
        )
    assert ei.value.code == "unknown_param"


def test_interpret_exit_mapping():
    class P:
        def __init__(self, code):
            self.returncode = code
            self.stdout = ""
            self.stderr = ""

    assert CliBackend._interpret_exit(P(0))["status"] == "ok"
    assert CliBackend._interpret_exit(P(1))["status"] == "cli_error"
    assert CliBackend._interpret_exit(P(-1073741819))["status"] == "crashed"
    assert CliBackend._interpret_exit(P(139))["status"] == "crashed"


def test_set_and_slice_validations(backend, tmp_path):
    with pytest.raises(BridgeError) as ei:
        backend.set_and_slice(str(tmp_path / "nothere.stl"))
    assert ei.value.code == "model_missing"

    weird = tmp_path / "model.exe"
    weird.write_bytes(b"x")
    with pytest.raises(BridgeError) as ei2:
        backend.set_and_slice(str(weird))
    assert ei2.value.code == "unsupported_model"

    mesh_no_presets = _make_model(tmp_path)
    with pytest.raises(BridgeError) as ei3:
        backend.set_and_slice(str(mesh_no_presets))
    assert ei3.value.code == "presets_required"


def test_export_3mf_passthrough_and_wrap(tmp_path):
    cfg = BridgeConfig(exe_path=tmp_path / "f.exe")
    (tmp_path / "f.exe").write_text("")
    backend = CliBackend(cfg)

    import trimesh

    src_mesh = tmp_path / "cube.stl"
    trimesh.creation.box(extents=(5, 5, 5)).export(src_mesh, file_type="stl")
    out = backend.export_3mf(str(src_mesh), str(tmp_path / "cube_out.3mf"))
    assert Path(out["output_file"]).is_file()
    assert out["method"] == "minimal_3mf_wrap"
    assert out["bytes"] > 0
    # The wrapped 3mf must survive a round-trip through trimesh's reader.
    import trimesh as tm

    loaded = tm.load(out["output_file"], force="mesh")
    assert abs(loaded.volume - 125.0) < 0.1

    src_3mf = tmp_path / "proj.3mf"
    src_3mf.write_bytes(b"PK\x03\x04 fake zip")
    out2 = backend.export_3mf(str(src_3mf), str(tmp_path / "proj_copy.3mf"))
    assert out2["method"] == "copy"
    assert Path(out2["output_file"]).read_bytes() == src_3mf.read_bytes()

    with pytest.raises(BridgeError) as ei:
        backend.export_3mf(str(src_3mf), str(src_3mf))
    assert ei.value.code == "bad_output"
