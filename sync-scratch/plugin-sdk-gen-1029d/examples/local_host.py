# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Local Host Contract"
# version = "1.0.0"
# ///
"""Reads live presets/model and exports a copy. Run after importing a model."""
import json
from pathlib import Path
from zipfile import ZipFile
import orca


class HostContract(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "Host Contract"

    def execute(self):
        plater = orca.host.plater()
        model = orca.host.model()
        assert model.object_count() > 0
        assert plater.model() is model
        bundle = orca.host.preset_bundle()
        preset = bundle.current_process_preset()
        assert "layer_height" in preset.config_keys()
        assert float(preset.config_value("layer_height")) > 0
        assert preset.config_value("missing_contract_option") is None
        assert bundle.current_printer_preset().type == orca.host.PresetType.Printer
        assert orca.host.gl_info()["vendor"]
        before = (plater.project_path(), plater.is_project_dirty(), plater.is_presets_dirty())
        target = Path(orca.host.plugin.storage()) / "工程副本.3mf"
        plater.export_3mf_copy(str(target))
        assert target.is_file() and target.stat().st_size > 0
        with ZipFile(target) as archive:
            assert archive.testzip() is None
            assert any(name.endswith(".model") for name in archive.namelist())
        assert before == (plater.project_path(), plater.is_project_dirty(), plater.is_presets_dirty())
        try:
            plater.export_3mf_copy(str(target.with_suffix(".zip")))
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid export extension accepted")
        try:
            plater.export_3mf_copy(str(target.parent / "missing-directory" / "copy.3mf"))
        except RuntimeError:
            pass
        else:
            raise AssertionError("Invalid export location accepted")
        assert before == (plater.project_path(), plater.is_project_dirty(), plater.is_presets_dirty())
        return orca.ExecutionResult.success("Host contract passed", json.dumps({
            "object_count": model.object_count(), "export_path": str(target),
            "project_state_preserved": True, "failed_export_state_preserved": True,
            "presets": True, "gl_info": orca.host.gl_info(),
        }))


@orca.plugin
class Package(orca.base):
    def register_capabilities(self):
        orca.register_capability(HostContract)
