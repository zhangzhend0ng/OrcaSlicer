# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Local slicing example"
# version = "1.0.0"
# ///
"""Select Local slice inspector in the process preset's Slicing plugins picker.

Reports actual layer counts without changing geometry. Borrowed slicing graph
objects are used only inside execute(); only ordinary Python values are saved.
"""
import json
import pathlib
import orca


class Inspector(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Local slice inspector"

    def execute(self, ctx):
        # The final-file stage has a different context: inspect live geometry
        # only in object stages (see local_gcode.py for final-file handling).
        if ctx.step == orca.slicing.Step.psGCodePostProcess:
            return orca.ExecutionResult.skipped()
        if ctx.step != orca.slicing.Step.posSlice:
            return orca.ExecutionResult.skipped()
        if ctx.cancelled():
            return orca.ExecutionResult.skipped("Slice cancelled")
        result = {
            "step": ctx.step.name,
            "layers": len(ctx.object.layers()),
            "wall_loops": ctx.config_value("wall_loops"),
            "host_version": ctx.orca_version,
        }
        output = pathlib.Path(orca.host.plugin.storage()) / "last_slice.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return orca.ExecutionResult.success("Layer report written to plugin storage")


@orca.plugin
class Package(orca.base):
    def register_capabilities(self):
        orca.register_capability(Inspector)
