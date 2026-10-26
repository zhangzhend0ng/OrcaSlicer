# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Plugin workflow fixture"
# version = "1.0.0"
# ///
"""Only for ORCA_LOCAL_PLUGIN_SMOKE_MODE=workflow in an isolated profile."""
import json
import pathlib
import orca


class WorkflowContour(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self):
        return "Workflow contour"

    def on_lifecycle_event(self, event, ctx):
        output = pathlib.Path(orca.host.plugin.storage()) / "workflow-events.jsonl"
        record = {"event": event.name, "code": ctx.code.name, "id": ctx.id,
                  "name": ctx.name, "source": ctx.source, "index": ctx.index, "dirty": ctx.dirty}
        with output.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def execute(self, ctx):
        if ctx.step != orca.slicing.Step.posSlice:
            return orca.ExecutionResult.skipped()
        factor = json.loads(self.get_config()).get("factor", 0.5)
        widths = []
        for layer_index, layer in enumerate(ctx.object.layers()):
            for region in layer.regions():
                for surface in region.slices.surfaces:
                    xs = [point.x for point in surface.expolygon.contour.points]
                    widths.append({"layer": layer_index, "before": (max(xs) - min(xs)) / 1e6})
                    for point in surface.expolygon.contour.points:
                        point.x = round(point.x * factor)
            layer.make_slices()
        output = pathlib.Path(orca.host.plugin.storage()) / "workflow-slice.json"
        output.write_text(json.dumps({"factor": factor, "layers": len(ctx.object.layers()), "widths": widths,
                                     "elefant_foot_compensation": ctx.config_value("elefant_foot_compensation")}), encoding="utf-8")
        return orca.ExecutionResult.success()


@orca.plugin
class WorkflowPackage(orca.base):
    def register_capabilities(self):
        orca.register_capability(WorkflowContour)
