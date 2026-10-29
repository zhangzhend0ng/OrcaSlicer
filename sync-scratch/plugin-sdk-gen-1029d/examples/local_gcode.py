# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Local G-code footer"
# version = "1.0.0"
# ///
from pathlib import Path
import orca


class Footer(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Local G-code footer"

    def execute(self, ctx):
        if ctx.step != orca.slicing.Step.psGCodePostProcess:
            return orca.ExecutionResult.skipped()
        # This is a working copy. Each export/upload receives its own callback;
        # do not keep this path, ctx, or Print graph references after returning.
        with Path(ctx.gcode_path).open("a", encoding="utf-8") as stream:
            stream.write("\n; Local plugin footer — host " + ctx.orca_version + "\n")
        return orca.ExecutionResult.success("Footer added")


@orca.plugin
class Package(orca.base):
    def register_capabilities(self):
        orca.register_capability(Footer)
