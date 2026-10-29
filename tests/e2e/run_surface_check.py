"""One-boot runtime verification of the 2026-10-29 host-API extension batch.

Installs sandboxes/api_surface_dump_plugin.py (enabled) into an isolated datadir,
boots the freshly built exe, waits for the api_surface.json dump, then asserts
the new fork-addition symbols are present in the live module tree. Never touches
user data. Usage:

  python tests/e2e/run_surface_check.py
"""

import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from e2elib import AppSession, check, install_plugin_dir, wait_until

EXE = os.path.join(HERE, "..", "..", "build-port", "src", "Release", "snapmaker-orca.exe")
SEED = os.path.join(HERE, "_work", "lifecycle", "datadir", "Snapmaker_Orca.conf")
WORK = os.path.join(HERE, "_work", "surface_check")
DUMP_PLUGIN_SRC = os.path.join(HERE, "..", "..", "sandboxes", "api_surface_dump_plugin.py")

# The batch under test: every symbol this run added to the live surface.
NEW_PLATE = ["plate_count", "current_plate_index", "plate", "select_plate", "select_plate_by_object",
             "create_plate", "duplicate_plate", "delete_plate"]
NEW_PLATE_CLASS = ["index", "name", "size", "origin", "object_indices", "object_count",
                   "objects_bounding_box", "extruders", "bed_type", "can_slice",
                   "is_slice_result_valid", "slice_ready_for_print", "slice_ready_for_export",
                   "gcode_filename", "has_valid_gcode_file"]
NEW_PLATER = ["remove_object", "delete_all_objects", "remove_selected", "select_all", "deselect_all",
              "select_current_plate_objects", "is_selection_empty", "increase_instances",
              "decrease_instances", "duplicate_selection", "center_selection", "mirror", "split_object",
              "split_volume", "optimize_rotation", "arrange", "orient", "fill_bed_with_instances",
              "scale_selection_to_fit_print_volume", "convert_unit", "copy_selection", "cut_selection",
              "paste", "set_selected_visible", "exit_gizmo", "undo", "redo", "can_undo", "can_redo",
              "can_arrange", "can_mirror", "can_split", "can_increase_instances",
              "can_decrease_instances", "can_copy_to_clipboard", "can_paste_from_clipboard",
              "open_project", "new_project", "save_project", "is_loading_project",
              "get_export_gcode_filename", "select_view", "select_view_3D", "is_preview_shown",
              "only_gcode_mode", "using_exported_file",
              # batch 2 (2026-10-29): model editing + STL export
              "rename_object", "rename_volume", "apply_object_transform", "apply_volume_config",
              "set_object_printable", "set_instance_printable", "merge_volumes",
              "export_object_stl", "export_stl",
              # batch 4 (2026-10-29): modeling domain (primitives, plane cut, text/SVG volumes)
              "get_primitive_shapes", "add_primitive", "add_primitive_volume", "cut_horizontal",
              "add_text_object", "add_text_volume", "add_svg_object",
              # batch 5 (2026-10-29): editing completion (simplify, repair, extruders)
              "simplify_volume", "is_netfabb_repair_available", "fix_through_netfabb",
              "set_object_extruder", "set_volume_extruder",
              # batch 6 (2026-10-29): facet painting (support/seam/mmu/fuzzy)
              "get_facet_painting", "set_facet_painting", "clear_facet_painting"]
# batch 7 (2026-10-29): flushing volumes — module-level functions on orca.host.
NEW_HOST_FUNCS = ["get_flush_volumes", "set_flush_volumes", "flush_volume_between"]


def main():
    check(os.path.isfile(EXE), "exe not built: %s" % EXE)
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)

    session = AppSession(EXE, WORK, seed_conf=SEED)
    src_dir = os.path.join(WORK, "dump_src")
    os.makedirs(src_dir)
    shutil.copyfile(DUMP_PLUGIN_SRC, os.path.join(src_dir, "api_surface_dump_plugin.py"))
    install_plugin_dir(session.plugins_dir, "api-surface-dump", src_dir, enabled=True)

    dump = os.path.join(session.plugins_dir, "api-surface-dump", "api_surface.json")
    session.launch()
    try:
        session.wait_up()
        check(wait_until(lambda: os.path.isfile(dump), timeout=90, interval=2,
                         what="api_surface.json written"), "dump file never appeared: %s" % dump)
        with open(dump, encoding="utf-8") as fh:
            surface = json.load(fh)

        # The dump is flat, keyed by full module name ("orca.host", "orca.host.plate", ...).
        host = surface["modules"]["orca.host"]
        plate = surface["modules"]["orca.host.plate"]
        missing = []
        for name in NEW_PLATE:
            if name not in plate.get("functions", {}):
                missing.append("orca.host.plate.%s" % name)
        # The dump splits callables (methods) from def_property members (properties):
        # Plate.index/name are properties, the rest of the class surface is methods.
        plate_cls = plate.get("classes", {}).get("Plate", {})
        plate_members = dict(plate_cls.get("methods", {}))
        plate_members.update(plate_cls.get("properties", {}))
        for name in NEW_PLATE_CLASS:
            if name not in plate_members:
                missing.append("orca.host.plate.Plate.%s" % name)
        for name in NEW_PLATER:
            if name not in host.get("classes", {}).get("Plater", {}).get("methods", {}):
                missing.append("orca.host.Plater.%s" % name)
        if "API_VERSION" not in host.get("constants", {}):
            missing.append("orca.host.API_VERSION")
        api_version = host.get("constants", {}).get("API_VERSION")
        if api_version not in ("int", "ERROR"):
            # enum-like values record as "int"; anything else means the attribute vanished.
            missing.append("orca.host.API_VERSION (type=%s)" % api_version)
        if "data_dir" not in host.get("functions", {}):
            missing.append("orca.host.data_dir")
        for name in NEW_HOST_FUNCS:
            if name not in host.get("functions", {}):
                missing.append("orca.host.%s" % name)
        if "Axis" not in host.get("classes", {}) or "enum_members" not in host["classes"]["Axis"]:
            missing.append("orca.host.Axis")
        # Batch 3: importer/exporter capability modules (fork-provisional).
        for mod_name, cls, methods in (
            ("orca.importer", "ImporterPluginCapabilityBase",
             ["get_type", "get_supported_extensions", "import_file"]),
            ("orca.exporter", "ExporterPluginCapabilityBase",
             ["get_type", "get_supported_extensions", "export_file"])):
            module = surface["modules"].get(mod_name)
            if module is None:
                missing.append("%s (module)" % mod_name)
                continue
            members = module.get("classes", {}).get(cls, {})
            found = set(members.get("methods", {})) | set(members.get("properties", {}))
            for name in methods:
                if name not in found:
                    missing.append("%s.%s.%s" % (mod_name, cls, name))
        if "ExporterContext" not in surface["modules"].get("orca.exporter", {}).get("classes", {}):
            missing.append("orca.exporter.ExporterContext")
        check(not missing, "missing new symbols in live surface: %s" % missing)
        print("SURFACE CHECK PASSED: all %d new symbols live (plate module %d + Plate %d + Plater %d + host 2)"
              % (len(NEW_PLATE) + len(NEW_PLATE_CLASS) + len(NEW_PLATER) + 2,
                 len(NEW_PLATE), len(NEW_PLATE_CLASS), len(NEW_PLATER)))
    finally:
        session.terminate()


if __name__ == "__main__":
    main()
