#include "PluginHostBindings.hpp"
#include "slic3r/plugin/PluginBindingUtils.hpp"

#include <libslic3r/Model.hpp>
#include <slic3r/GUI/GUI.hpp>
#include <slic3r/GUI/GUI_App.hpp>
#include <slic3r/GUI/PartPlate.hpp>
#include <slic3r/GUI/Plater.hpp>

#include <pybind11/pytypes.h>
#include <pybind11/stl.h>

#include <wx/app.h>
#include <wx/thread.h>

#include <stdexcept>
#include <string>
#include <vector>

namespace py = pybind11;

namespace Slic3r {
namespace {

// Same guard style as PluginHostApp.cpp: the plate list is owned by the Plater and every
// structural change to it (create/delete/select, object adds and removes re-binding
// instances) happens on the UI thread.
GUI::Plater& current_plater()
{
    if (wxTheApp == nullptr)
        throw std::runtime_error("OrcaSlicer application is not initialized");
    GUI::Plater* plater = GUI::wxGetApp().plater();
    if (plater == nullptr)
        throw std::runtime_error("Plater is not available");
    return *plater;
}

void require_main_thread(const char* function_name)
{
    if (!wxIsMainThread())
        throw std::runtime_error(std::string(function_name) + "() must be called from the UI thread");
}

GUI::PartPlateList& plate_list() { return current_plater().get_partplate_list(); }

// Resolve a 0-based plate index, validating against the live count on every call.
GUI::PartPlate& plate_at(int index, const char* who)
{
    GUI::PartPlateList& plates = plate_list();
    if (index < 0 || index >= plates.get_plate_count())
        throw py::value_error(std::string(who) + ": plate index " + std::to_string(index)
                              + " is out of range; this project has "
                              + std::to_string(plates.get_plate_count()) + " plate(s) (0-based)");
    GUI::PartPlate* plate = plates.get_plate(index);
    if (plate == nullptr)
        throw std::runtime_error(std::string(who) + ": plate " + std::to_string(index) + " is not available");
    return *plate;
}

// Bed type as a stable short name, not the localized config label: plugins correlate it
// with the printer's supported list, they do not display it.
const char* bed_type_name(BedType type)
{
    switch (type) {
    case btDefault:    return "default";
    case btPC:         return "pc";
    case btEP:         return "ep";
    case btPEI:        return "pei";
    case btPTE:        return "pte";
    case btPCT:        return "pct";
    case btGESP:       return "gesp";
    case btSuperTack:  return "super_tack";
    default:           return "unknown";
    }
}

// Objects with at least one instance bound to this plate, as indices into
// plater.model().objects(). PartPlate tracks the instance-to-plate binding, so the
// object set is derived from it (get_objects_on_this_plate() walks the model the same
// way but hands out pointers; indices are the stable currency of this API).
std::vector<int> plate_object_indices(GUI::Plater& plater, GUI::PartPlate& plate)
{
    std::vector<int> indices;
    Model&           model = plater.model();
    for (int object_idx = 0; object_idx < static_cast<int>(model.objects.size()); ++object_idx) {
        const ModelObject* object = model.objects[object_idx];
        for (int instance_idx = 0; instance_idx < static_cast<int>(object->instances.size()); ++instance_idx)
            if (plate.contain_instance(object_idx, instance_idx)) {
                indices.push_back(object_idx);
                break;
            }
    }
    return indices;
}

// Handle to one plate by 0-based index. Like PresetEditor it is a category handle, not a
// snapshot: every method re-resolves the live plate list, so it goes stale only in the
// sense that its index may name a different (or no) plate after plates are deleted —
// each call validates the index against the current count and raises ValueError if it no
// longer resolves.
struct PlateHandle
{
    int index = -1;
};

} // namespace

// Fork addition (no upstream counterpart on either absorbed line): the multi-plate
// domain. Upstream's host surface keeps the Plater minimal and has no plate bindings;
// everything here is fork-local and snapshot-gated like the rest of the surface.
void host_bindings::register_plates(py::module_& host)
{
    auto plate = host.def_submodule("plate", "Plate (print job) domain of the plater");

    // Unlocked plain-int reads of the plate list header, same deliberate class as
    // Plater.slice_state()/slice_progress(): safe for a plugin worker to poll.
    plate.def("plate_count", []() { return plate_list().get_plate_count(); },
              "Number of plates in the project (including the unprintable overflow plate if present). "
              "Unlocked read, safe to poll.");
    plate.def("current_plate_index", []() { return plate_list().get_curr_plate_index(); },
              "0-based index of the currently selected plate. Unlocked read, safe to poll.");

    plate.def("plate", [](int index) { return PlateHandle{index}; }, py::arg("index"),
              "Handle to the plate at a 0-based index. The handle re-resolves the live plate list on every "
              "call, so it raises ValueError once the index no longer resolves (e.g. after delete_plate).");

    // Selectors/mutators: UI thread only.
    plate.def("select_plate", [](int index) {
        require_main_thread("plate.select_plate");
        plate_at(index, "plate.select_plate");
        plate_list().select_plate(index);
        return plate_list().get_curr_plate_index();
    }, py::arg("index"),
       "Select the plate at a 0-based index (the same switch the plate bar performs) and return the "
       "now-current index. UI thread only.");
    plate.def("select_plate_by_object", [](int object_idx, int instance_idx) {
        require_main_thread("plate.select_plate_by_object");
        GUI::Plater& plater = current_plater();
        Model&       model  = plater.model();
        if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
            throw py::value_error("plate.select_plate_by_object: object index out of range");
        if (instance_idx < 0 || instance_idx >= static_cast<int>(model.objects[object_idx]->instances.size()))
            throw py::value_error("plate.select_plate_by_object: instance index out of range");
        plate_list().select_plate_by_obj(object_idx, instance_idx);
        return plate_list().get_curr_plate_index();
    }, py::arg("object_idx"), py::arg("instance_idx") = 0,
       "Select the plate holding the given object instance and return the now-current index. "
       "UI thread only.");
    plate.def("create_plate", []() {
        require_main_thread("plate.create_plate");
        return plate_list().create_plate();
    }, "Create an empty plate and return its 0-based index. UI thread only.");
    plate.def("duplicate_plate", [](int index) {
        require_main_thread("plate.duplicate_plate");
        plate_at(index, "plate.duplicate_plate");
        return plate_list().duplicate_plate(index);
    }, py::arg("index"),
       "Duplicate the plate at a 0-based index (objects and layout) and return the new plate's index. "
       "UI thread only.");
    plate.def("delete_plate", [](int index) {
        require_main_thread("plate.delete_plate");
        plate_at(index, "plate.delete_plate");
        plate_list().delete_plate(index);
    }, py::arg("index"),
       "Delete the plate at a 0-based index; its objects return to the overflow area. UI thread only.");

    py::class_<PlateHandle>(plate, "Plate", "Handle to one plate; see plate.plate(index).")
        .def_property_readonly("index", [](const PlateHandle& p) { return p.index; })
        .def_property("name",
            [](PlateHandle& p) {
                require_main_thread("Plate.name");
                return plate_at(p.index, "Plate.name").get_plate_name();
            },
            [](PlateHandle& p, const std::string& name) {
                require_main_thread("Plate.name");
                if (name.empty())
                    throw py::value_error("Plate.name: a plate name must not be empty");
                plate_at(p.index, "Plate.name").set_plate_name(name);
            },
            "Plate display name. UI thread only.")
        .def("size", [](PlateHandle& p) {
            require_main_thread("Plate.size");
            const Vec2d size = plate_at(p.index, "Plate.size").get_size();
            return py::make_tuple(size.x(), size.y());
        }, "Printable plate footprint (width, depth) in mm. UI thread only.")
        .def("origin", [](PlateHandle& p) {
            require_main_thread("Plate.origin");
            return vec3_to_tuple(plate_at(p.index, "Plate.origin").get_origin());
        }, "Plate center origin in world coordinates as (x, y, z). UI thread only.")
        .def("object_indices", [](PlateHandle& p) {
            require_main_thread("Plate.object_indices");
            GUI::Plater& plater = current_plater();
            return plate_object_indices(plater, plate_at(p.index, "Plate.object_indices"));
        }, "Indices into plater.model().objects() of the objects on this plate "
           "(any instance bound counts). UI thread only.")
        .def("object_count", [](PlateHandle& p) {
            require_main_thread("Plate.object_count");
            GUI::Plater& plater = current_plater();
            return static_cast<int>(plate_object_indices(plater, plate_at(p.index, "Plate.object_count")).size());
        }, "Number of objects on this plate. UI thread only.")
        .def("objects_bounding_box", [](PlateHandle& p) {
            require_main_thread("Plate.objects_bounding_box");
            return plate_at(p.index, "Plate.objects_bounding_box").get_objects_bounding_box();
        }, "World-space bounding box of the objects on this plate (a copy). UI thread only.")
        .def("extruders", [](PlateHandle& p) {
            require_main_thread("Plate.extruders");
            return plate_at(p.index, "Plate.extruders").get_extruders();
        }, "1-based extruder (filament) indices used on this plate. UI thread only.")
        .def("bed_type", [](PlateHandle& p) {
            require_main_thread("Plate.bed_type");
            return std::string(bed_type_name(plate_at(p.index, "Plate.bed_type").get_bed_type()));
        }, "Plate bed type as a stable short name (\"default\", \"pc\", \"ep\", \"pei\", \"pte\", "
           "\"pct\", \"gesp\", \"super_tack\"), not the localized label. UI thread only.")
        .def("can_slice", [](PlateHandle& p) {
            require_main_thread("Plate.can_slice");
            return plate_at(p.index, "Plate.can_slice").can_slice();
        }, "True when the plate passes the GUI's slice gate (objects loaded, apply state valid). "
           "UI thread only.")
        .def("is_slice_result_valid", [](PlateHandle& p) {
            require_main_thread("Plate.is_slice_result_valid");
            return plate_at(p.index, "Plate.is_slice_result_valid").is_slice_result_valid();
        }, "True when the plate holds a slice result for the current model/preset state. UI thread only.")
        .def("slice_ready_for_print", [](PlateHandle& p) {
            require_main_thread("Plate.slice_ready_for_print");
            return plate_at(p.index, "Plate.slice_ready_for_print").is_slice_result_ready_for_print();
        }, "True when the slice result is valid for printing (no toolpath outside the plate). UI thread only.")
        .def("slice_ready_for_export", [](PlateHandle& p) {
            require_main_thread("Plate.slice_ready_for_export");
            return plate_at(p.index, "Plate.slice_ready_for_export").is_slice_result_ready_for_export();
        }, "True when the slice result is valid for export (printable and has printable instances). "
           "UI thread only.")
        .def("gcode_filename", [](PlateHandle& p) {
            require_main_thread("Plate.gcode_filename");
            return plate_at(p.index, "Plate.gcode_filename").get_gcode_filename();
        }, "Path of the plate's sliced G-code file, or an empty string when none was produced. "
           "Reading the file still needs filesystem permission. UI thread only.")
        .def("has_valid_gcode_file", [](PlateHandle& p) {
            require_main_thread("Plate.has_valid_gcode_file");
            return plate_at(p.index, "Plate.has_valid_gcode_file").is_valid_gcode_file();
        }, "True when the plate's G-code file exists and matches the current slice. UI thread only.");
}

} // namespace Slic3r
