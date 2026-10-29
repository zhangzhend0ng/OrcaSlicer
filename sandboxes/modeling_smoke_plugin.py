# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# id = "modeling-smoke"
# name = "Modeling Smoke"
# description = "Unattended functional smoke of the modeling host API (add_primitive/add_primitive_volume/cut_horizontal/add_text_object/add_text_volume/add_svg_object): runs the battery on the first ProjectDirtyChanged after the UI is up and writes modeling_smoke.json. Tooling for port verification; not for end users."
# author = "port-audit"
# version = "1.1.0"
# ///
"""Modeling smoke — proves the batch-4 modeling host API actually works.

Runs once the UI is up (hooked on ProjectDirtyChanged, the only lifecycle
event an unattended boot fires; retried until the 3D view is ready).

Steps (each wrapped; failure records the exception string):
  s1   get_primitive_shapes() = the 7 shape names
  s2   add_primitive cube -> new object, 1 volume, nonempty mesh, on the bed
  s3a  add_primitive_volume cylinder modifier into it
  s3b  add_primitive_volume slab (instance-bb sized) into it
  s4   add_text_object SMOKE -> new text object with a nonempty mesh
  s5   add_text_volume V as a NegativeVolume into the cube
  s6   cut_horizontal the text object at mid height -> exactly 2 new objects
  s7a-s7h  negative tests: rejected inputs raise ValueError
  s8   undo restores the original object count
  s9   add_svg_object queues (async job; only queuing is asserted)

Bisection: if runsteps.txt exists next to the plugin (comma-separated step
ids), only those steps run. Stage markers stage_*.txt appear per visited
milestone. Output: modeling_smoke.json, booleans only.
"""

import json
import os
import traceback

import orca

OUT_FILENAME = "modeling_smoke.json"
LOG_PREFIX = "[modeling-smoke]"

_done = False
_s9_done = False
_running = False
_attempts = 0
_result = {"steps": {}}

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20">'
       '<path d="M2 2 L18 2 L18 18 Z" fill="black"/></svg>')


def _mark(stage):
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "stage_%s.txt" % stage), "w", encoding="utf-8") as fh:
            fh.write(stage)
    except Exception:
        pass


def _selected_steps():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "runsteps.txt"), encoding="utf-8") as fh:
            return set(s.strip() for s in fh.read().split(",") if s.strip())
    except Exception:
        return None


def run_battery(phase="main"):
    _mark("battery_enter")
    out = {"steps": {}}
    s = out["steps"]
    sel = _selected_steps()

    def want(step):
        if phase == "late":
            return step in ("s8", "s9") and (sel is None or step in sel)
        if step in ("s8", "s9"):
            return False
        return sel is None or step in sel

    def expect(key, fn):
        if not want(key):
            return
        _mark("before_" + key)
        try:
            s[key] = fn()
        except Exception as exc:
            s[key] = "ERROR: %s: %s" % (type(exc).__name__, exc)
        _mark("after_" + key)

    def expect_value_error(key, fn):
        def run():
            try:
                fn()
            except ValueError:
                return True
            return "NO-ERROR"
        expect(key, run)

    p = orca.host.plater()
    m = p.model()
    VT = orca.host.ModelVolumeType
    # The host mutators ensure the 3D view themselves (NativeCommands'
    # object_op pattern); no view switch needed here.
    _mark("battery_plater")

    n0 = m.object_count()
    expect("s1", lambda: sorted(p.get_primitive_shapes()) ==
           sorted(["cube", "cylinder", "sphere", "slab", "cone", "disc", "torus"]))

    cube_holder = {}

    def add_cube():
        cube = p.add_primitive("cube", size=10.0)
        cube_holder["idx"] = cube
        return isinstance(cube, int) and cube == n0 and m.object(cube).volume_count() == 1 \
            and m.object(cube).volume(0).facets_count() > 0 and m.object(cube).name == "Cube" \
            and m.object(cube).bounding_box().min[2] > -0.01
    expect("s2", add_cube)
    cube = cube_holder.get("idx", n0)

    def add_modifier():
        mod = p.add_primitive_volume("cylinder", cube, volume_type=VT.ParameterModifier, size=5.0)
        return mod == 1 and m.object(cube).volume(1).type() == VT.ParameterModifier
    expect("s3a", add_modifier)

    def add_slab():
        slab = p.add_primitive_volume("slab", cube)
        return slab == 2 and m.object(cube).volume_count() == 3
    expect("s3b", add_slab)

    text_holder = {}

    def add_text_object():
        txt = p.add_text_object("SMOKE", height_mm=8.0, depth_mm=1.0)
        text_holder["idx"] = txt
        return txt == n0 + 1 and m.object(txt).volume(0).facets_count() > 0 \
            and m.object(txt).name == "SMOKE"
    expect("s4", add_text_object)
    txt = text_holder.get("idx", n0 + 1)

    def add_text_volume():
        before = m.object(cube).volume_count()
        tv = p.add_text_volume("V", cube, height_mm=4.0, depth_mm=1.0, volume_type=VT.NegativeVolume)
        return isinstance(tv, int) and 0 <= tv < m.object(cube).volume_count() \
            and m.object(cube).volume_count() == before + 1 \
            and m.object(cube).volume(tv).type() == VT.NegativeVolume \
            and m.object(cube).volume(tv).facets_count() > 0
    expect("s5", add_text_volume)

    def cut_text():
        bb = m.object(txt).bounding_box()
        z_mid = 0.5 * (bb.min[2] + bb.max[2])
        added = p.cut_horizontal(txt, z_mid)
        return len(added) == 2 and added == sorted(added) \
            and added[-1] == m.object_count() - 1 and m.object_count() == n0 + 3
    expect("s6", cut_text)

    expect_value_error("s7a", lambda: p.add_primitive("pyramid"))
    expect_value_error("s7b", lambda: p.add_primitive("slab"))
    expect_value_error("s7c", lambda: p.add_primitive_volume("slab", cube, size=9.0))
    expect_value_error("s7d", lambda: p.cut_horizontal(cube, 1.0e6))
    expect_value_error("s7e", lambda: p.cut_horizontal(cube, 5.0, keep_upper=False, keep_lower=False))
    expect_value_error("s7f", lambda: p.add_text_volume("", cube))
    expect_value_error("s7g", lambda: p.add_text_object("x" * 1001))
    expect_value_error("s7h", lambda: p.add_primitive("cube", name=""))

    # ── editing completion (batch 5) ──
    def simplify_half():
        before = m.object(cube).volume(0).facets_count()
        after = p.simplify_volume(cube, 0, keep_ratio=0.5)
        return 0 < after < before and after == m.object(cube).volume(0).facets_count()
    expect("e1", simplify_half)

    expect_value_error("e2a", lambda: p.simplify_volume(cube, 0))                      # neither
    expect_value_error("e2b", lambda: p.simplify_volume(cube, 0, keep_ratio=0.5, target_triangle_count=10))  # both
    expect_value_error("e2c", lambda: p.simplify_volume(cube, 0, keep_ratio=1.5))      # out of (0,1]
    expect_value_error("e2d", lambda: p.simplify_volume(cube, 0, keep_ratio=1.0))      # target == current
    expect_value_error("e2e", lambda: p.simplify_volume(cube, 0, target_triangle_count=3))   # < 4
    expect_value_error("e2f", lambda: p.simplify_volume(cube, 0, target_triangle_count=10**9))  # >= current

    def assign_extruders():
        ok_obj = p.set_object_extruder(cube, 1) is True
        ok_vol = p.set_volume_extruder(cube, 0, 2) is True
        vol_val = m.object(cube).volume(0).config_value("extruder")
        return ok_obj and ok_vol and vol_val == "2"
    expect("e3", assign_extruders)

    def object_clears_volume_override():
        p.set_object_extruder(cube, 1)
        return m.object(cube).volume(0).config_value("extruder") is None
    expect("e4", object_clears_volume_override)

    expect_value_error("e4b", lambda: p.set_object_extruder(cube, 99))
    def negative_volume_rejected():
        # volume order is re-sorted on add (reorder_volumes), so locate by type
        o = m.object(cube)
        neg = next(i for i in range(o.volume_count()) if o.volume(i).type() == VT.NegativeVolume)
        p.set_volume_extruder(cube, neg, 1)
    expect_value_error("e4c", negative_volume_rejected)

    def netfabb_probe():
        available = p.is_netfabb_repair_available()
        if not available:
            return "skipped-unavailable"
        p.fix_through_netfabb(cube)
        return True
    expect("e5", netfabb_probe)

    # ── facet painting (batch 6) ──
    def paint_read_empty():
        n = m.object(cube).volume(0).facets_count()
        states = p.get_facet_painting(cube, 0, "fdm_support")
        return len(states) == n and all(v == 0 for v in states)
    expect("p1", paint_read_empty)

    def paint_write_read():
        n = m.object(cube).volume(0).facets_count()
        painted = p.set_facet_painting(cube, 0, "fdm_support", [1] + [0] * (n - 1))
        back = p.get_facet_painting(cube, 0, "fdm_support")
        return painted == 1 and back[0] == 1 and all(v == 0 for v in back[1:])             and m.object(cube).volume(0).is_fdm_support_painted()
    expect("p2", paint_write_read)

    def paint_mmu_and_gates():
        n = m.object(cube).volume(0).facets_count()
        ok = p.set_facet_painting(cube, 0, "mmu", [1] + [0] * (n - 1)) == 1
        back = p.get_facet_painting(cube, 0, "mmu")
        return ok and back[0] == 1 and m.object(cube).volume(0).is_mm_painted()
    expect("p3", paint_mmu_and_gates)

    expect_value_error("p3b", lambda: p.set_facet_painting(cube, 0, "mmu", [99] + [0] * (m.object(cube).volume(0).facets_count() - 1)))
    expect_value_error("p3c", lambda: p.set_facet_painting(cube, 0, "fdm_support", [1, 0]))  # wrong length
    expect_value_error("p3d", lambda: p.get_facet_painting(cube, 0, "nonsense"))

    def paint_clear():
        cleared = p.clear_facet_painting(cube, 0, "fdm_support") is True
        again = p.clear_facet_painting(cube, 0, "fdm_support") is False
        return cleared and again and not m.object(cube).volume(0).is_fdm_support_painted()
    expect("p4", paint_clear)

    # ── flushing volumes (batch 7) ──
    def flush_roundtrip():
        data = orca.host.get_flush_volumes()
        n = data["n"]
        if n < 1:
            return "no filaments loaded"
        matrix = list(data["matrix"])
        old = matrix[0]
        matrix[0] = old + 1.0
        orca.host.set_flush_volumes(matrix=matrix)
        back = orca.host.get_flush_volumes()
        restored = orca.host.set_flush_volumes(matrix=list(data["matrix"]))  # restore
        return back["matrix"][0] == old + 1.0 and restored is None
    expect("f1", flush_roundtrip)

    def flush_calc():
        same = orca.host.flush_volume_between((255, 255, 0, 0), (255, 255, 0, 0), 0, 280)
        diff = orca.host.flush_volume_between((255, 255, 0, 0), (255, 0, 0, 255), 0, 280)
        return 0 <= same <= diff and diff > 0
    expect("f2", flush_calc)

    expect_value_error("f3a", lambda: orca.host.set_flush_volumes(multiplier=0.0))
    expect_value_error("f3b", lambda: orca.host.set_flush_volumes(matrix=[1.0, 2.0]))          # not N*N
    expect_value_error("f3c", lambda: orca.host.flush_volume_between((255, 0, 0, 0), (255, 0, 0, 0), 10, 5))
    expect_value_error("f3d", lambda: orca.host.flush_volume_between((300, 0, 0, 0), (255, 0, 0, 0), 0, 280))

    def undo_back():
        trace = ["start count=%d can_undo=%s capture=%s" % (
            m.object_count(), p.can_undo(), p.inside_snapshot_capture())]
        for _ in range(25):
            if m.object_count() == n0:
                return True
            if not p.can_undo():
                trace.append("exhausted at count=%d" % m.object_count())
                return "; ".join(trace)
            p.undo()
            trace.append("undo->count=%d" % m.object_count())
        return m.object_count() == n0 or "; ".join(trace)
    expect("s8", undo_back)

    def queue_svg():
        svg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smoke.svg")
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(SVG)
        return p.add_svg_object(svg_path) is None
    expect("s9", queue_svg)

    out["ok"] = all(v is True for v in s.values()) if s else False
    out["attempts"] = _attempts
    return out


def _merge_s9(s9_out):
    _result.setdefault("steps", {}).update(s9_out.get("steps", {}))
    _result["ok"] = all(v is True for v in _result["steps"].values())
    _result["attempts"] = _attempts
    return _result


def _write(out):
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, OUT_FILENAME), "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)


class ModelingSmokeCapability(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        _mark("get_name")
        return "modeling_smoke"

    def on_lifecycle_event(self, event, ctx):
        global _done, _attempts, _s9_done, _running
        name = getattr(event, "name", "")
        _mark("event_" + name)
        if name != "ProjectDirtyChanged" or _running:
            return
        _attempts += 1
        _running = True
        try:
            self._dispatch(name)
        finally:
            _running = False

    def _dispatch(self, name):
        global _done, _s9_done
        # Phase 1 (mutations, s1-s8): skip the boot's own dirty flips — they can
        # fire inside the boot's snapshot-suppression window, which would empty
        # the undo stack the battery wants to verify. Wait for the 2nd event.
        if not _done and _attempts >= 2:
            try:
                out = run_battery(phase="main")
                _done = True
                _result.clear()
                _result.update(out)
                _write(out)
                print("{} main ok={} attempts={}".format(LOG_PREFIX, out["ok"], _attempts))
            except Exception:
                print("{} main attempt {} failed: {}".format(LOG_PREFIX, _attempts, traceback.format_exc()))
        # Phase 2 (s8 undo + s9 svg): both need things that only settle once
        # this callback returns to the event loop — the flutter tab switch
        # (Plater::IsShown(), which can_undo() checks) and the SVG gizmo's
        # lazy init on the 3D view's first render. Run them on a later dirty
        # flip (the battery's own mutations fire them).
        elif _done and not _s9_done:
            try:
                out = run_battery(phase="late")
                _s9_done = True
                merged = _merge_s9(out)
                _write(merged)
                print("{} late ok={} attempts={}".format(LOG_PREFIX, merged.get("ok"), _attempts))
            except Exception:
                print("{} s9 attempt {} failed: {}".format(LOG_PREFIX, _attempts, traceback.format_exc()))
                _s9_done = True
                _write(_merge_s9({"steps": {"late": "ERROR: " + traceback.format_exc()}}))


@orca.plugin
class ModelingSmokePlugin(orca.base):
    def register_capabilities(self):
        _mark("register")
        orca.register_capability(ModelingSmokeCapability)
        _mark("registered")
