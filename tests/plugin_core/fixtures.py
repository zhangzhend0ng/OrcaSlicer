"""Deterministic local packages; no network, account or system site-packages."""
import base64
import csv
import hashlib
import io
from pathlib import Path
import zipfile

HEADER = '''# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Core Contract"
# version = "1.0.0"
# ///
'''
SCRIPT = '''import orca, json, pathlib
class Counter(orca.script.ScriptPluginCapabilityBase):
    def get_name(self): return "Counter"
    def get_default_config(self): return {"count": 0}
    def execute(self):
        config = json.loads(self.get_config())
        config["count"] = config.get("count", 0) + 1
        if not self.save_config(json.dumps(config)): raise RuntimeError("save failed")
        return orca.ExecutionResult.success("executed", json.dumps(config))
    def on_lifecycle_event(self, event, ctx):
        self.save_config(json.dumps({"event": ctx.name, "id": ctx.id}))
@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(Counter)
'''
AUDIT = '''import orca, pathlib
class Audit(orca.script.ScriptPluginCapabilityBase):
    def get_name(self): return "Audit"
    def execute(self):
        root = pathlib.Path(orca.host.plugin.storage())
        (root / "result.txt").write_text("allowed", encoding="utf-8")
        (root / "Snapmaker_Orca.conf").read_text()
        return orca.ExecutionResult.success("SHOULD NOT REACH")
@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(Audit)
'''
MULTI = '''import orca, pathlib
class Page(orca.pages.PagesPluginCapabilityBase):
    def get_name(self): return "Contract Page"
    def get_ui(self): return "<h1>Local page</h1>"
    def on_message(self, data): self.post_message({"reply": data})
class Texture(orca.resource_texture.ResourceTexturePluginCapabilityBase):
    def get_name(self): return "Contract Texture"
    def get_texture_dir(self): return str(pathlib.Path(__file__).parent / "textures")
@orca.plugin
class Package(orca.base):
    def register_capabilities(self):
        orca.register_capability(Page)
        orca.register_capability(Texture)
'''

SLICING = '''import orca, json, pathlib, time
class Contour(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self): return "Contour contract"
    def execute(self, ctx):
        assert ctx.print is not None and not ctx.cancelled()
        assert ctx.gcode_path == "" and ctx.host == "" and ctx.output_name == ""
        assert ctx.config_value("wall_loops") is not None
        config = json.loads(self.get_config())
        root = pathlib.Path(orca.host.plugin.storage())
        if ctx.step == orca.slicing.Step.posSlice:
            assert ctx.object is not None
            self.steps, self.factors = [], []
            if config.get("wait"):
                (root / "entered").write_text("entered")
                deadline = time.monotonic() + 20
                while not (root / "release").exists():
                    if time.monotonic() > deadline: raise RuntimeError("slice gate timeout")
                    time.sleep(.01)
            for layer in ctx.object.layers():
                for region in layer.regions():
                    for surface in region.slices.surfaces:
                        for point in surface.expolygon.contour.points:
                            point.x = round(point.x * config.get("factor", .5))
                layer.make_slices()
            if config.get("mode") == "fatal": return orca.ExecutionResult.failure(orca.PluginResult.FatalError, "contract failure")
            if config.get("mode") == "raise": raise RuntimeError("contract failure")
            if config.get("mode") == "ui": orca.host.ui.message("must not reach UI")
        assert (ctx.object is None) == (ctx.step in (orca.slicing.Step.psWipeTower, orca.slicing.Step.psSkirtBrim))
        self.steps.append(ctx.step.name)
        self.factors.append(config.get("factor", .5))
        (root / "report.json").write_text(json.dumps({"steps": self.steps, "factors": self.factors}))
        return orca.ExecutionResult.success()
@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(Contour)
'''

GCODE = '''import orca, json, pathlib, time, os
class First(orca.slicing.SlicingPipelineCapabilityBase):
    def get_name(self): return "G-code first"
    def on_lifecycle_event(self, event, ctx):
        if self.get_name() != "G-code first": return
        root = pathlib.Path(orca.host.plugin.storage())
        path = root / "events.json"
        events = json.loads(path.read_text()) if path.exists() else []
        events.append({"event": event.name, "name": ctx.name, "id": ctx.id, "code": ctx.code.name, "msg": ctx.msg})
        path.write_text(json.dumps(events))
        config = json.loads(self.get_config())
        if config.get("event_ui"):
            try: orca.host.ui.message("must not block native worker")
            except RuntimeError as error:
                assert "Blocking UI calls" in str(error)
                (root / "event_ui_rejected").write_text("rejected")
            else: raise RuntimeError("background UI was allowed")
        if config.get("event_raise"): raise RuntimeError("lifecycle observer failure")
        if config.get("event_wait"):
            (root / "entered").write_text("entered")
            deadline = time.monotonic() + 20
            while not (root / "release").exists():
                if time.monotonic() > deadline: raise RuntimeError("event gate timeout")
                time.sleep(.01)
    def execute(self, ctx):
        if ctx.step != orca.slicing.Step.psGCodePostProcess: return orca.ExecutionResult.skipped()
        assert ctx.print is None and ctx.object is None and not ctx.cancelled()
        assert ctx.config_value("wall_loops") == "3"
        assert ctx.config_value("missing_option") is None
        config = json.loads(self.get_config())
        root = pathlib.Path(orca.host.plugin.storage())
        path = pathlib.Path(ctx.gcode_path)
        prior = path.read_text()
        (root / (self.get_name() + ".json")).write_text(json.dumps({"prior": prior, "host": ctx.host, "output_name": ctx.output_name, "config": config}))
        if config.get("wait"):
            (root / "entered").write_text("entered")
            deadline = time.monotonic() + 20
            while not (root / "release").exists():
                if time.monotonic() > deadline: raise RuntimeError("G-code gate timeout")
                time.sleep(.01)
        mode = config.get("mode")
        if mode == "skip": return orca.ExecutionResult.skipped()
        path.write_text(prior + "; " + self.get_name() + ":" + str(config.get("value", 1)) + "\\n")
        if mode == "delete": path.unlink()
        if mode == "raise": raise RuntimeError("G-code contract failure")
        if mode == "ui": orca.host.ui.message("must not block export")
        if mode in ("fatal", "recoverable"):
            status = orca.PluginResult.FatalError if mode == "fatal" else orca.PluginResult.RecoverableError
            return orca.ExecutionResult.failure(status, "G-code contract failure")
        return orca.ExecutionResult.success()
class Second(First):
    def get_name(self): return "G-code second"
@orca.plugin
class Package(orca.base):
    def register_capabilities(self):
        orca.register_capability(First)
        orca.register_capability(Second)
'''

def wheel(path, name, code, version="1.0.0", extra=None):
    info = f"{name}-{version}.dist-info"
    files = {f"{name}/__init__.py": code.encode(),
             f"{info}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\nRequires-Python: >=3.12\n\n".encode(),
             f"{info}/WHEEL": b"Wheel-Version: 1.0\nGenerator: Snapmaker-contract-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
             f"{info}/top_level.txt": (name + "\n").encode()}
    files.update(extra or {})
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for key, data in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow([key, "sha256=" + digest, len(data)])
    writer.writerow([f"{info}/RECORD", "", ""])
    files[f"{info}/RECORD"] = record.getvalue().encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for key, data in files.items(): archive.writestr(key, data)

def prepare(root):
    root.mkdir()
    (root / "counter.py").write_text(HEADER + SCRIPT)
    (root / "slicing.py").write_text(HEADER + SLICING)
    (root / "gcode.py").write_text(HEADER + GCODE)
    (root / "classic_postprocess.py").write_text("import pathlib, sys\np = pathlib.Path(sys.argv[1])\np.write_text(p.read_text() + '; classic\\n')\npathlib.Path(str(p) + '.output_name').write_text('renamed.gcode\\n')\n")
    (root / "audit.py").write_text(HEADER + AUDIT)
    (root / "invalid.py").write_text("raise RuntimeError('metadata scan executed package')\n")
    (root / "duplicate.py").write_text(HEADER + SCRIPT.replace("orca.register_capability(Counter)", "orca.register_capability(Counter); orca.register_capability(Counter)"))
    (root / "failure.py").write_text(HEADER + SCRIPT.replace('    def execute(self):', '    def on_load(self): raise RuntimeError("contract on_load failure")\n    def execute(self):'))
    (root / "metadata_only.py").write_text(HEADER + "raise RuntimeError('metadata scan executed package')\n")
    wheel(root / "wheelcounter-1.0.0-py3-none-any.whl", "wheelcounter", SCRIPT)
    # A real 1x1 PNG, owned by the package and discoverable after extraction.
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aOuoAAAAASUVORK5CYII=")
    wheel(root / "multicap-1.0.0-py3-none-any.whl", "multicap", MULTI, extra={"multicap/textures/one.png": png})
    wheel(root / "traversal-1.0.0-py3-none-any.whl", "traversal", SCRIPT, extra={"../../escaped.txt": b"must not extract"})
    for version in ["1.0.0", "2.0.0"]:
        wheel(root / f"contract_dep-{version}-py3-none-any.whl", "contract_dep", f"VALUE = {version!r}\n", version=version)

    for variant in ["updated", "broken", "import_error", "dependency_error", "crash"]:
        folder = root / variant
        folder.mkdir()
        header = HEADER.replace('version = "1.0.0"', 'version = "2.0.0"')
        code = SCRIPT.replace('"executed"', '"updated"')
        if variant == "broken":
            code = code.replace('    def execute(self):', '    def on_load(self):\n        self.save_config(json.dumps({"count": 999}))\n        raise RuntimeError("replacement on_load failed")\n    def execute(self):')
        elif variant == "import_error":
            code = 'raise RuntimeError("replacement import failed")\n'
        elif variant == "dependency_error":
            header = header.replace('dependencies = []', 'dependencies = ["definitely-missing-contract-package==1.0.0"]')
        elif variant == "crash":
            code = code.replace('    def execute(self):', '    def on_load(self):\n        self.save_config(json.dumps({"count": 999}))\n        import os; os._exit(82)\n    def execute(self):')
        (folder / "counter.py").write_text(header + code)
