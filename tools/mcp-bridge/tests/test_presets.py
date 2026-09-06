import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snapmaker_orca_mcp.errors import BridgeError
from snapmaker_orca_mcp.presets import (
    find_preset_file,
    merge_inherit_chain,
    prepare_preset_files,
    write_merged_preset,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILES = REPO_ROOT / "resources" / "profiles" / "Snapmaker"


def _have_profiles() -> bool:
    return (PROFILES / "machine" / "fdm_common.json").is_file()


VARIANT = "Snapmaker Artisan (0.4 nozzle).json"


@pytest.mark.skipif(not _have_profiles(), reason="Snapmaker profiles missing")
def test_chain_has_expected_depth():
    chain_file = find_preset_file(PROFILES.parent.parent, "machine", VARIANT)
    merged = merge_inherit_chain(chain_file)
    # base layer keys must survive and child overrides must win
    assert "inherits" not in merged
    assert merged["name"] == VARIANT.replace(".json", "")
    for base_key in ("type", "from"):
        assert base_key in merged


@pytest.mark.skipif(not _have_profiles(), reason="Snapmaker profiles missing")
def test_merged_file_is_valid_json_with_no_inherits(tmp_path):
    src = find_preset_file(PROFILES.parent.parent, "machine", VARIANT)
    out = write_merged_preset(src, tmp_path)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "inherits" not in data


@pytest.mark.skipif(not _have_profiles(), reason="Snapmaker profiles missing")
def test_prepare_all_categories(tmp_path):
    out = prepare_preset_files(
        PROFILES.parent.parent,
        machine=VARIANT,
        process="0.16 Optimal @Snapmaker Artisan (0.4 nozzle)",
        filaments=["Generic PLA"],
        work_dir=tmp_path,
    )
    assert Path(out["machine"]).is_file()
    assert Path(out["process"]).is_file()
    assert len(out["filaments"]) == 1


def test_missing_preset_errors(tmp_path):
    with pytest.raises(BridgeError) as ei:
        merge_inherit_chain(tmp_path / "ghost.json")
    assert ei.value.code == "preset_not_found"
    with pytest.raises(BridgeError):
        find_preset_file(tmp_path, "machine", "No Such Printer")


def test_cycle_detection(tmp_path):
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"inherits": "b", "name": "a"}), encoding="utf-8")
    b.write_text(json.dumps({"inherits": "a", "name": "b"}), encoding="utf-8")
    with pytest.raises(BridgeError) as ei:
        merge_inherit_chain(a)
    assert ei.value.code == "preset_cycle"
