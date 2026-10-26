"""Actual Script capability and orca bindings; native fixture supplies owned geometry.

No Python point loop and no mutable-mesh API is fabricated. Mesh copies are
Python-owned; polygon writeback uses the existing supported mutable interface.
"""
import json
import sys
import time
import weakref
import numpy as np
import orca

_inputs = None
_watch = None
_capability = None

def configure(mesh, polygon, side, watch):
    global _inputs, _watch
    _inputs = (mesh, polygon, side)
    _watch = watch
    watch["refs"].extend([weakref.ref(sys.modules[__name__]), _capability])

class Bulk(orca.script.ScriptPluginCapabilityBase):
    def get_name(self): return "Benchmark NumPy Bulk"
    def on_load(self):
        global _capability
        _capability = weakref.ref(self)
    def on_unload(self):
        if _watch is not None: _watch["unload_calls"] += 1
    def execute(self):
        mesh, polygon, side = _inputs
        durations = {}
        start = time.perf_counter_ns()
        vertices, triangles = mesh.vertices(), mesh.triangles()
        durations["mesh_zero_copy_views"] = time.perf_counter_ns() - start
        n = (side + 1) ** 2
        assert vertices.shape == (n, 3) and vertices.dtype == np.float32
        assert triangles.shape == (side * side * 2, 3) and triangles.dtype == np.int32
        assert not vertices.flags.writeable and not triangles.flags.writeable
        assert vertices.base is not None and triangles.base is not None
        start = time.perf_counter_ns()
        vertex_sum = float(vertices.sum(dtype=np.float64))
        triangle_sum = int(triangles.sum(dtype=np.int64))
        durations["mesh_vectorized_read"] = time.perf_counter_ns() - start
        assert vertex_sum == side * (side + 1) ** 2
        assert triangle_sum == 3 * side ** 3 * (side + 2)
        start = time.perf_counter_ns()
        copied = vertices.copy()
        copied += np.array([1, 2, 3], dtype=np.float32)
        durations["owned_mesh_copy_vectorized_write"] = time.perf_counter_ns() - start
        assert copied.flags.writeable and not np.shares_memory(copied, vertices)
        assert float(copied.sum(dtype=np.float64)) == vertex_sum + 6 * n
        assert float(vertices.sum(dtype=np.float64)) == vertex_sum
        start = time.perf_counter_ns()
        normals = mesh.face_normals()
        durations["native_face_normals_owned_return"] = time.perf_counter_ns() - start
        assert normals.shape == triangles.shape and normals.dtype == np.float32
        assert np.all(normals[:, :2] == 0) and np.all(normals[:, 2] == 1)
        # A simple rectangular ring with many collinear points, constructed in
        # vectorized NumPy operations. The native consumer verifies the writeback.
        k = side * side // 4
        i = np.arange(k, dtype=np.int64)
        zero, edge = np.zeros(k, dtype=np.int64), np.full(k, k, dtype=np.int64)
        points = np.concatenate((np.column_stack((i, zero)), np.column_stack((edge, i)),
                                 np.column_stack((k-i, edge)), np.column_stack((zero, k-i))))
        start = time.perf_counter_ns()
        polygon.set_points(points)
        durations["numpy_to_native_polygon_set_points"] = time.perf_counter_ns() - start
        start = time.perf_counter_ns()
        writable = polygon.as_array()
        writable += np.array([7, -11], dtype=np.int64)
        durations["native_polygon_view_vectorized_write"] = time.perf_counter_ns() - start
        assert writable.shape == points.shape and writable.dtype == np.int64 and writable.flags.writeable
        assert np.array_equal(polygon.as_array(), points + np.array([7, -11], dtype=np.int64))
        _watch["refs"].extend(weakref.ref(value) for value in (vertices, triangles, copied, normals, points, writable))
        return orca.ExecutionResult.success("", json.dumps({"metrics_ns": durations,
            "vertex_checksum": vertex_sum, "triangle_checksum": triangle_sum,
            "vertices": n, "triangles": len(triangles), "polygon_points": len(points),
            "mesh_access": "immutable native view; explicit Python copy for writes",
            "native_writeback": "Polygon.set_points/as_array", "passed": True}, sort_keys=True))

@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(Bulk)
