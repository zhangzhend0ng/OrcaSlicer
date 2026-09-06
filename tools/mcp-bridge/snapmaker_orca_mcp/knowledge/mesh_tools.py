"""Knowledge-layer mesh tools built on trimesh.

These tools are pure analysis: they never invoke Orca and work on real mesh
files (STL/OBJ/PLY/3MF). 3MF is read through trimesh's 3MF loader (zipfile +
XML under the hood) - no bespoke parser, per the integration plan.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..errors import BridgeError

MAX_MESH_BYTES = 256 * 1024 * 1024

SUPPORTED_EXTENSIONS = {".stl", ".obj", ".ply", ".3mf", ".off"}

DEFAULT_DENSITY_G_CM3 = 1.24  # PLA
DEFAULT_EFFECTIVE_FLOW_MM3_S = 7.5  # conservative FDM effective throughput


def load_mesh_any(path: str | Path):
    """Load a mesh file and return (single merged Trimesh, metadata dict).

    Multi-body scenes (3MF with several objects) are concatenated so volume
    and area math stay simple; the metadata reports what was merged.
    """
    import trimesh  # deferred so the module imports cleanly without trimesh

    p = Path(path)
    if not p.is_file():
        raise BridgeError(f"mesh file not found: {path}", code="mesh_missing")
    if p.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise BridgeError(
            f"unsupported mesh type '{p.suffix}' "
            f"(supported: {sorted(SUPPORTED_EXTENSIONS)})",
            code="unsupported_mesh",
        )
    if p.stat().st_size > MAX_MESH_BYTES:
        raise BridgeError("mesh file too large (>256MB)", code="mesh_too_large")

    loaded = trimesh.load(str(p), force="scene", process=True)
    metadata = {"file": str(p), "format": p.suffix.lower().lstrip(".")}
    if isinstance(loaded, trimesh.Scene):
        names = list(loaded.geometry.keys())
        if not names:
            raise BridgeError("mesh file contains no geometry", code="empty_mesh")
        meshes = [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        metadata["objects"] = len(meshes)
        metadata["object_names"] = names[:32]
        combined = meshes[0]
        for extra in meshes[1:]:
            combined = combined + extra
    else:
        combined = loaded
        metadata["objects"] = 1
    if combined.is_empty:
        raise BridgeError("mesh is empty after load", code="empty_mesh")
    return combined, metadata


def _overhang_stats(mesh, overhang_angle_deg: float) -> dict:
    """Area-weighted stats for faces that would need support.

    A face needs support when it faces downward with |normal_z| beyond
    cos(threshold) (threshold measured from the horizontal plane, matching
    slicer 'support overhang angle' semantics) AND it does not lie in the
    bed-contact plane: faces resting on the bed print fine without support.
    """
    normals = mesh.face_normals
    areas = mesh.area_faces
    verts_z = mesh.vertices[:, 2]
    tri_z = verts_z[mesh.faces]  # (n_faces, 3) vertex heights per triangle
    min_z = float(tri_z.min())
    # a face is "on the bed" when all of its vertices sit within one layer
    # of the model's lowest point
    on_bed = (tri_z.max(axis=1) - min_z) <= 0.3
    cos_limit = np.cos(np.radians(overhang_angle_deg))
    down = (normals[:, 2] < -cos_limit) & (~on_bed)
    overhang_area = float(areas[down].sum())
    total_area = float(areas.sum())
    return {
        "overhang_angle_deg": overhang_angle_deg,
        "overhang_area_mm2": round(overhang_area, 2),
        "overhang_area_ratio": round(overhang_area / total_area, 4)
        if total_area > 0
        else 0.0,
    }


def analyze_mesh(path: str) -> dict:
    """Structural overview: dimensions, volume, watertightness, components."""
    mesh, meta = load_mesh_any(path)
    extents = mesh.extents
    components = mesh.split(only_watertight=False)
    out = {
        **meta,
        "dimensions_mm": [round(float(v), 3) for v in extents],
        "bounding_box_mm": {
            "min": [round(float(v), 3) for v in mesh.bounds[0]],
            "max": [round(float(v), 3) for v in mesh.bounds[1]],
        },
        "volume_mm3": round(float(mesh.volume), 2),
        "surface_area_mm2": round(float(mesh.area), 2),
        "triangles": int(len(mesh.faces)),
        "vertices": int(len(mesh.vertices)),
        "is_watertight": bool(mesh.is_watertight),
        "is_winding_consistent": bool(mesh.is_winding_consistent),
        "euler_number": int(mesh.euler_number),
        "components": len(components),
    }
    if out["is_watertight"]:
        out["material_note"] = "watertight: volume is trustworthy"
    else:
        out["material_note"] = (
            "not watertight: volume/sliceability uncertain, consider fixing the mesh"
        )
    return out


def check_printability(
    path: str,
    build_volume_mm: list[float] | None = None,
    layer_height_mm: float = 0.2,
    nozzle_diameter_mm: float = 0.4,
    overhang_angle_deg: float = 50.0,
) -> dict:
    """Heuristic printability screen for FDM.

    Checks: size vs build volume, minimum feature height vs layer height,
    overhang burden, watertightness. Heuristics only - final judgement needs
    a real slice (use set_and_slice / session slice).
    """
    mesh, meta = load_mesh_any(path)
    extents = np.asarray(mesh.extents, dtype=float)
    findings: list[str] = []
    ok = True

    if build_volume_mm is not None:
        if len(build_volume_mm) != 3:
            raise BridgeError(
                "build_volume_mm must be [x, y, z] in mm", code="bad_build_volume"
            )
        fits = bool(np.all(extents <= np.asarray(build_volume_mm, dtype=float) + 1e-6))
        if not fits:
            ok = False
            findings.append(
                f"model {extents.round(2).tolist()}mm exceeds build volume "
                f"{build_volume_mm}mm"
            )
        else:
            findings.append("fits build volume")

    min_horizontal = float(extents[:2].min())
    if min_horizontal < nozzle_diameter_mm:
        ok = False
        findings.append(
            f"horizontal feature {min_horizontal:.2f}mm is below one nozzle "
            f"width ({nozzle_diameter_mm}mm)"
        )
    if float(extents[2]) < layer_height_mm:
        ok = False
        findings.append("model is flatter than one layer height")

    if not mesh.is_watertight:
        ok = False
        findings.append("mesh is not watertight; slicers may produce gaps")

    overhang = _overhang_stats(mesh, overhang_angle_deg)
    if overhang["overhang_area_ratio"] > 0.15:
        findings.append(
            f"large overhang area ({overhang['overhang_area_ratio']:.0%} of "
            f"surface beyond {overhang_angle_deg}deg) - supports likely needed"
        )
    else:
        findings.append("overhang burden moderate or low")

    return {
        **meta,
        "printable": ok,
        "findings": findings,
        "overhangs": overhang,
        "assumptions": {
            "layer_height_mm": layer_height_mm,
            "nozzle_diameter_mm": nozzle_diameter_mm,
        },
        "note": "heuristic screen only; slice for a definitive verdict",
    }


def _rotations_candidates() -> list[tuple[str, np.ndarray]]:
    """Named candidate orientations as rotation matrices."""
    import trimesh.transformations as tf

    out: list[tuple[str, np.ndarray]] = [("as_loaded", np.eye(4))]
    for axis_name, axis in (("x", [1, 0, 0]), ("y", [0, 1, 0])):
        for deg in (90, 180, 270):
            out.append(
                (
                    f"rot_{deg}_deg_{axis_name}",
                    tf.rotation_matrix(np.radians(deg), axis),
                )
            )
        for deg in (30, 45, 60, 120, 135, 150):
            out.append(
                (
                    f"tilt_{deg}_deg_{axis_name}",
                    tf.rotation_matrix(np.radians(deg), axis),
                )
            )
    return out


def suggest_orientation(
    path: str,
    overhang_angle_deg: float = 50.0,
    max_suggestions: int = 5,
) -> dict:
    """Rank candidate orientations by exposed overhang area (less is better).

    Pure geometry heuristic: it ignores supports-around-text, bridging
    quality and cosmetic faces; treat it as a starting point.
    """
    mesh, meta = load_mesh_any(path)
    areas = mesh.area_faces
    total_area = float(areas.sum())
    if total_area <= 0:
        raise BridgeError("mesh has zero surface area", code="empty_mesh")
    cos_limit = np.cos(np.radians(overhang_angle_deg))

    ranked: list[dict] = []
    for name, mat in _rotations_candidates():
        rotated = mesh.copy()
        rotated.apply_transform(mat)
        normals = rotated.face_normals
        tri_z = rotated.vertices[:, 2][rotated.faces]
        contact = (tri_z.max(axis=1) - tri_z.min()) <= 0.3
        down = (normals[:, 2] < -cos_limit) & (~contact)
        overhang_area = float(areas[down].sum())
        flat_area = float(areas[(normals[:, 2] < -0.99) & contact].sum())
        ranked.append(
            {
                "orientation": name,
                "overhang_area_mm2": round(overhang_area, 2),
                "overhang_ratio": round(overhang_area / total_area, 4),
                "flat_contact_area_mm2": round(flat_area, 2),
            }
        )
    ranked.sort(key=lambda item: (item["overhang_ratio"], -item["flat_contact_area_mm2"]))
    top = ranked[: max(1, int(max_suggestions))]
    best = top[0]
    return {
        **meta,
        "overhang_angle_deg": overhang_angle_deg,
        "recommended": best["orientation"],
        "candidates": top,
        "note": (
            "ranking by exposed overhang area only; combine with cosmetic and "
            "strength considerations"
        ),
    }


def estimate_cost(
    path: str,
    infill_density_pct: float = 20.0,
    wall_count: int = 2,
    nozzle_diameter_mm: float = 0.4,
    layer_height_mm: float = 0.2,
    filament_density_g_cm3: float = DEFAULT_DENSITY_G_CM3,
    filament_price_per_kg: float | None = None,
    electricity_price_per_kwh: float | None = None,
    machine_power_w: float = 100.0,
    effective_flow_mm3_s: float = DEFAULT_EFFECTIVE_FLOW_MM3_S,
) -> dict:
    """Transparent shell+infill material/energy/cost estimate.

    Model: extruded volume = wall volume (surface_area * wall thickness) plus
    interior volume scaled by infill density; time = volume / effective flow.
    All assumptions are returned so the caller can see how rough it is.
    """
    mesh, meta = load_mesh_any(path)
    solid_volume_mm3 = float(mesh.volume)
    if solid_volume_mm3 <= 0:
        raise BridgeError(
            "mesh volume is not positive (non-watertight or inverted faces)",
            code="bad_volume",
        )
    surface_mm2 = float(mesh.area)
    wall_thickness_mm = wall_count * nozzle_diameter_mm
    wall_volume = surface_mm2 * wall_thickness_mm
    interior_volume = max(0.0, solid_volume_mm3 - wall_volume)
    infill_fraction = min(max(float(infill_density_pct), 0.0), 100.0) / 100.0
    extruded_mm3 = wall_volume + interior_volume * infill_fraction

    weight_g = extruded_mm3 / 1000.0 * float(filament_density_g_cm3)
    time_s = extruded_mm3 / max(float(effective_flow_mm3_s), 0.1)

    cost = {
        "filament_weight_g": round(weight_g, 2),
        "extruded_volume_mm3": round(extruded_mm3, 1),
        "estimated_time_s": int(time_s),
        "estimated_time_human": _human(time_s),
        "model": {
            "solid_volume_mm3": round(solid_volume_mm3, 1),
            "surface_area_mm2": round(surface_mm2, 1),
            "wall_thickness_mm": wall_thickness_mm,
            "infill_density_pct": infill_density_pct,
            "effective_flow_mm3_s": effective_flow_mm3_s,
            "filament_density_g_cm3": filament_density_g_cm3,
        },
    }
    if filament_price_per_kg is not None:
        cost["material_cost"] = round(weight_g / 1000.0 * float(filament_price_per_kg), 3)
    if electricity_price_per_kwh is not None:
        kwh = time_s / 3600.0 * float(machine_power_w) / 1000.0
        cost["energy_cost"] = round(kwh * float(electricity_price_per_kwh), 3)
        cost["energy_kwh"] = round(kwh, 4)
    cost["note"] = (
        "rough pre-slice estimate; slice (set_and_slice) for exact gcode stats"
    )
    return cost


def _human(seconds: float) -> str:
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h {m}m {s}s"
