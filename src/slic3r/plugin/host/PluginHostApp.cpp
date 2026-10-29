#include "PluginHostBindings.hpp"
#include "PluginHostEditing.hpp"   // register_editing_methods (editing-completion domain)
#include "PluginHostModeling.hpp" // register_modeling_methods (modeling domain)
#include "PluginHostPainting.hpp" // register_painting_methods (facet-painting domain)

#include <pybind11/cast.h>
#include <pybind11/pybind11.h>
#include <pybind11/pytypes.h>

#include <libslic3r/AppConfig.hpp>
#include <libslic3r/Config.hpp>
#include <libslic3r/Format/bbs_3mf.hpp>
#include <libslic3r/Format/STL.hpp> // store_stl
#include <libslic3r/LifecycleEvents.hpp> // fire_lifecycle_event / ObjectRenamed
#include <libslic3r/Model.hpp>
#include <libslic3r/PresetBundle.hpp>
#include <libslic3r/Semver.hpp>
#include <libslic3r/Utils.hpp> // data_dir()

#include "common_func/common_func.hpp" // Snapmaker_VERSION
#include <slic3r/GUI/BackgroundSlicingProcess.hpp>
#include <slic3r/GUI/GUI.hpp>
#include <slic3r/GUI/GUI_App.hpp>
#include <slic3r/GUI/GUI_ObjectList.hpp>
#include <slic3r/GUI/OpenGLManager.hpp>
#include <slic3r/GUI/PartPlate.hpp>
#include <slic3r/GUI/Plater.hpp>
#include <slic3r/GUI/Selection.hpp>

#include <boost/algorithm/string/predicate.hpp>
#include <boost/filesystem.hpp>

#include <chrono>
#include <memory>
#include <stdexcept>
#include <string>
#include <utility>

#include <wx/app.h>
#include <wx/string.h>
#include <wx/thread.h>

namespace py = pybind11;

namespace Slic3r {
namespace {

GUI::Plater* current_plater()
{
    if (wxTheApp == nullptr)
        throw std::runtime_error("OrcaSlicer application is not initialized");

    GUI::Plater* plater = GUI::wxGetApp().plater();
    if (plater == nullptr)
        throw std::runtime_error("Plater is not available");

    return plater;
}

PresetBundle* current_preset_bundle()
{
    if (wxTheApp == nullptr)
        throw std::runtime_error("OrcaSlicer application is not initialized");

    PresetBundle* preset_bundle = GUI::wxGetApp().preset_bundle;
    if (preset_bundle == nullptr)
        throw std::runtime_error("Preset bundle is not available");

    return preset_bundle;
}

GUI::GUI_App& current_app()
{
    if (wxTheApp == nullptr)
        throw std::runtime_error("OrcaSlicer application is not initialized");
    return GUI::wxGetApp();
}

// The plater is only safe to touch from the UI thread, and the 3MF export renders thumbnails,
// which needs the UI thread's GL context.
void require_main_thread(const char* function_name)
{
    if (!wxIsMainThread())
        throw std::runtime_error(std::string(function_name) + "() must be called from the UI thread");
}

// Rebuild the object-settings page the way a re-selection does: changed_object() invalidates
// the print, but an external (plugin) write does not change the selection, so the left panel's
// per-object parameter list would keep showing the stale view until the user re-clicks the
// object. part_selection_changed() is the same refresh the GUI runs after its own object-
// settings edits.
void refresh_object_settings_page()
{
    if (GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list())
        obj_list->part_selection_changed();
}

void export_3mf_copy(GUI::Plater& plater, const std::string& path)
{
    require_main_thread("export_3mf_copy");
    if (!boost::iends_with(path, ".3mf"))
        throw py::value_error("export_3mf_copy() needs a path ending in .3mf");
    // The thumbnails are rendered by the 3D view, which may not exist yet while plugins load.
    if (!GUI::OpenGLManager::get_gl_info().is_detected())
        throw std::runtime_error("export_3mf_copy() needs the 3D view, which is not ready yet");
    // The file is written from C++, so raise the audit event Python's open(path, "w") raises: the
    // plugin gets the same deny list, permissions and prompt as for writing the file itself.
    if (PySys_Audit("open", "ssi", path.c_str(), "w", 0) < 0)
        throw py::error_already_set();
    if (!plater.export_3mf_copy(GUI::into_path(GUI::from_u8(path))))
        throw std::runtime_error("Failed to write " + path);
}

// Single-object 3MF export: the model is cloned and pruned to the one object
// (all its instances, at their current positions), then stored through the
// same store_bbs_3mf machinery export_3mf_copy uses, minus the project
// bookkeeping (SaveStrategy::Silence: no project-filename takeover, no plate
// thumbnails — so, unlike export_3mf_copy, no GL context is needed). The
// archive carries the full merged preset config (full_config_secure), the
// same payload a project save embeds. The clone gets a scratch backup path
// because the exporter serializes the config into <backup>/_temp_1.config
// before adding it to the archive.
std::string export_object_3mf_one(GUI::Plater& plater, int object_idx, const std::string& path)
{
    require_main_thread("export_object_3mf");
    if (!boost::iends_with(path, ".3mf"))
        throw py::value_error("export_object_3mf() needs a path ending in .3mf");
    // The file is written from C++, so raise the audit event Python's open(path, "w") raises: the
    // plugin gets the same deny list, permissions and prompt as for writing the file itself.
    if (PySys_Audit("open", "ssi", path.c_str(), "w", 0) < 0)
        throw py::error_already_set();

    Model& model = plater.model();
    if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
        throw py::value_error("object index out of range");

    // Clone so the live model, its plates and its backup directory stay
    // untouched; prune the clone to the requested object (delete_object —
    // ModelObject's destructor is Model-private).
    Model clone = model;
    ModelObject* keep_object = clone.objects[object_idx];
    for (ModelObject* obj : clone.objects)
        if (obj != keep_object)
            clone.delete_object(obj);

    const boost::filesystem::path scratch = boost::filesystem::temp_directory_path() /
        ("orca_export_object_" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
    boost::system::error_code ec;
    boost::filesystem::create_directories(scratch, ec);
    clone.set_backup_path(scratch.string());

    DynamicPrintConfig config = current_preset_bundle()->full_config_secure();

    StoreParams params;
    params.path     = path.c_str();
    params.model    = &clone;
    params.config   = &config;
    params.project  = nullptr;
    params.profile  = nullptr;
    params.strategy = SaveStrategy::Silence | SaveStrategy::Zip64;

    const bool stored = store_bbs_3mf(params);
    boost::filesystem::remove_all(scratch, ec);
    if (!stored)
        throw std::runtime_error("Failed to write " + path);
    return path;
}

py::object gl_info()
{
    const GUI::OpenGLManager::GLInfo& info = GUI::OpenGLManager::get_gl_info();
    if (!info.is_detected())
        return py::none();
    py::dict out;
    out["vendor"]       = info.get_vendor();
    out["renderer"]     = info.get_renderer();
    out["version"]      = info.get_version();
    out["glsl_version"] = info.get_glsl_version();
    // Upstream also reports core_profile; this fork's GLInfo does not track it.
    return std::move(out);
}

py::dict app_info()
{
    GUI::GUI_App& app = current_app();
    // The app config has no lock of its own; the UI thread is where it is written.
    require_main_thread("app_info");
    py::dict out;
    out["version"] = Snapmaker_VERSION;
    out["mode"]    = app.is_editor() ? "editor" : "gcode viewer";
    out["language"] = GUI::into_u8(app.current_language_code_safe());
    // The app config file is deny-listed for plugins; these are the parts a bug report needs.
    const boost::optional<Semver>& config_version = app.last_config_version();
    out["app_config_version"] = config_version && config_version->valid() ? config_version->to_string_sf() : std::string();
    out["stealth_mode"]       = app.app_config != nullptr && app.app_config->get_stealth_mode();
    // Upstream also reports the Orca/Bambu cloud sign-in states and the network plugin version;
    // those agents are trimmed on this fork, so only this build's own login is reported.
    out["is_signed_in"] = app.is_user_login();
    return out;
}

} // namespace

// Access to the live GUI application: the Plater and the module-level
// plater()/model()/preset_bundle() accessors. Everything here is owned by the
// app and only reachable once the GUI is up (the accessors throw before that).
void host_bindings::register_app(py::module_& host)
{
    // Transform/units enums used by the Plater mutators below. Axis carries E/F in
    // libslic3r (extruder/feed axes); only X/Y/Z are meaningful for mirror(), so only
    // those are exported.
    py::enum_<Axis>(host, "Axis").value("X", X).value("Y", Y).value("Z", Z);
    py::enum_<ConversionType>(host, "ConversionType")
        .value("ToInch", ConversionType::CONV_TO_INCH)
        .value("FromInch", ConversionType::CONV_FROM_INCH)
        .value("ToMeter", ConversionType::CONV_TO_METER)
        .value("FromMeter", ConversionType::CONV_FROM_METER);

    auto plater_class = py::class_<GUI::Plater, std::unique_ptr<GUI::Plater, py::nodelete>>(host, "Plater")
        .def("model", static_cast<Model& (GUI::Plater::*)()>(&GUI::Plater::model), py::return_value_policy::reference_internal)
        .def("is_project_dirty", &GUI::Plater::is_project_dirty)
        .def("is_presets_dirty", &GUI::Plater::is_presets_dirty)
        .def("inside_snapshot_capture", &GUI::Plater::inside_snapshot_capture)
        // Path the project was last opened from or saved to; empty while it has never been saved.
        .def("project_path", [](GUI::Plater& plater) {
            require_main_thread("project_path");
            return GUI::into_u8(plater.get_project_filename(".3mf"));
        })
        .def("export_3mf_copy", &export_3mf_copy, py::arg("path"),
             "Write the current project, unsaved changes included, to path as a 3MF copy. The project's "
             "file name and saved state are not changed, and the signed-in account is not written as the designer.")
        // Read-only view of the 3D-view selection: indices into
        // plater.model().objects() of the objects the user selected (any
        // instance selected counts). The py::list is built by hand — this TU
        // keeps clear of pybind11/stl.h container casts.
        .def("selected_object_indices", [](GUI::Plater& plater) -> py::list {
            require_main_thread("selected_object_indices");
            const GUI::Selection& selection = plater.get_selection();
            py::list indices;
            for (const auto& entry : selection.get_content())
                indices.append(py::int_(entry.first)); // map keys: unique, ascending
            return indices;
        },
           "Indices of the objects currently selected in the 3D view. UI thread only.")
        // Apply per-object process overrides: keys are Orca config keys,
        // values the string serialization the config parser expects. Returns
        // a per-key list of (key, ok, error) so partial application is
        // visible; a successful write is followed by changed_object() so the
        // GUI refreshes like any other object-settings edit.
        .def("apply_object_config", [](GUI::Plater& plater, int object_idx, py::dict values) -> py::list {
            require_main_thread("apply_object_config");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            ModelObject* object = model.objects[object_idx];
            py::list results;
            bool any_applied = false;
            for (auto item : values) {
                const std::string key = py::str(item.first);
                const std::string value = py::str(item.second);
                try {
                    ConfigSubstitutionContext substitutions(ForwardCompatibilitySubstitutionRule::Disable);
                    object->config.set_deserialize(key, value, substitutions);
                    results.append(py::make_tuple(key, true, ""));
                    any_applied = true;
                } catch (const std::exception& ex) {
                    results.append(py::make_tuple(key, false, ex.what()));
                }
            }
            if (any_applied) {
                plater.changed_object(object_idx);
                refresh_object_settings_page();
            }
            return results;
        }, py::arg("object_idx"), py::arg("values"),
           "Apply per-object process overrides (Orca config keys, string-serialized values). "
           "UI thread only. Returns [(key, ok, error), ...].")
        // Remove per-object process overrides — the opposite of
        // apply_object_config: after reset the key inherits from the presets
        // again. Erasing a key that merely inherited is a no-op reported as
        // was_set=False (idempotent). Object-level scope only — per-volume
        // and height-range overrides are untouched.
        .def("reset_object_config", [](GUI::Plater& plater, int object_idx, py::list keys) -> py::list {
            require_main_thread("reset_object_config");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            ModelObject* object = model.objects[object_idx];
            py::list results;
            bool any_erased = false;
            for (auto item : keys) {
                const std::string key = py::str(item);
                const bool was_set = object->config.erase(key);
                results.append(py::make_tuple(key, was_set));
                any_erased = any_erased || was_set;
            }
            if (any_erased) {
                plater.changed_object(object_idx);
                refresh_object_settings_page();
            }
            return results;
        }, py::arg("object_idx"), py::arg("keys"),
           "Remove per-object process overrides. Returns [(key, was_set), ...]; "
           "was_set=False means the key was never overridden (no-op). UI thread only.")
        // Merged process view for one object: the current presets' full
        // config with this object's overrides applied. Values use the same
        // string serialization apply_object_config consumes. Object-level
        // overrides only — per-volume and height-range overrides are NOT
        // merged in. Re-derives full_config() per call: an on-demand
        // snapshot, not for tight polling.
        .def("get_effective_config", [](GUI::Plater& plater, int object_idx) -> py::dict {
            require_main_thread("get_effective_config");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            ModelObject* object = model.objects[object_idx];
            const DynamicPrintConfig presets = current_preset_bundle()->full_config();
            py::dict result;
            for (const std::string& key : presets.keys()) {
                const ModelConfig& overrides = object->config;
                const std::string value = overrides.has(key) ? overrides.opt_serialize(key) : presets.opt_serialize(key);
                result[py::str(key)] = py::str(value);
            }
            for (const std::string& key : object->config.keys())
                if (!result.contains(py::str(key)))
                    result[py::str(key)] = py::str(object->config.opt_serialize(key));
            return result;
        }, py::arg("object_idx"),
           "Per-object effective process config: current presets merged with this object's "
           "overrides (string-serialized; object-level overrides only). UI thread only.")
        // Export one object standalone; the audit/prompt path is the same as
        // export_3mf_copy's.
        .def("export_object_3mf", &export_object_3mf_one, py::arg("object_idx"), py::arg("path"),
             "Export one object (all its instances, current positions) as a standalone 3MF carrying "
             "the current preset config. The path is audit-checked like a plugin file write. "
             "UI thread only. Returns the path.")
        // Schedule a real slice of the current plate with the G-code exported
        // to the caller-chosen path, then restart the background process
        // (reslice() = set_task + FORCE_RESTART, so the plate is genuinely
        // re-sliced and the export branch consumes the scheduled path — the
        // same machinery the Export G-code menu uses, minus the file dialog).
        // Fire-and-forget: poll the file or is_export_gcode_scheduled().
        .def("schedule_plate_gcode_export", [](GUI::Plater& plater, const std::string& output_path) -> std::string {
            require_main_thread("schedule_plate_gcode_export");
            if (plater.model().objects.empty())
                throw std::runtime_error("plate is empty — nothing to slice");
            BackgroundSlicingProcess& process = plater.background_process();
            if (process.is_export_scheduled())
                throw std::runtime_error("another G-code export job is already running");
            process.schedule_export(output_path, false);
            plater.reslice();
            return output_path;
        }, py::arg("output_path"),
           "Slice the current plate now and export its G-code to output_path (async; poll the file). "
           "UI thread only.")
        // Import model files (stl/obj/3mf/step/...) onto the current plate as
        // geometry — the same path a drag-and-drop onto the 3D view takes:
        // load_files() with LoadModel only, so presets and the current plate
        // layout stay untouched. Like a manual import it can raise modal
        // error dialogs on bad files.
        .def("load_model_files", [](GUI::Plater& plater, py::list paths) -> py::list {
            require_main_thread("load_model_files");
            if (paths.empty())
                throw py::value_error("paths must not be empty");
            std::vector<std::string> files;
            files.reserve(paths.size());
            for (auto item : paths) {
                const std::string path = py::str(item);
                if (path.empty())
                    throw py::value_error("paths contains an empty path");
                files.emplace_back(path);
            }
            const std::vector<size_t> added = plater.load_files(files, LoadStrategy::LoadModel);
            py::list indices;
            for (const size_t idx : added)
                indices.append(py::int_(idx));
            return indices;
        }, py::arg("paths"),
           "Import model file(s) onto the current plate (added like a drag-and-drop). "
           "UI thread only. Returns the indices of the added objects.")
        // Coarse slicing state for polling plugins. "idle" = not slicing;
        // "slicing" = slicing without an export scheduled; "exporting" =
        // slicing with a scheduled G-code export (schedule_plate_gcode_export
        // jobs report "exporting" for the whole run — the export is scheduled
        // up front). Unlike the mutators above these are unlocked flag reads
        // (Plater's public state queries), deliberately NOT gated on
        // require_main_thread so a plugin worker thread can poll them.
        .def("slice_state", [](GUI::Plater& plater) -> std::string {
            if (!plater.is_background_process_slicing())
                return "idle";
            return plater.is_export_gcode_scheduled() ? "exporting" : "slicing";
        },
           "Coarse slicing state: \"idle\", \"slicing\", or \"exporting\" "
           "(export-scheduled jobs report \"exporting\" throughout). Unlocked read, safe to poll.")
        // Whether a schedule_plate_gcode_export job still holds an export
        // path — flips back to false when the export finalizes.
        .def("is_export_gcode_scheduled", &GUI::Plater::is_export_gcode_scheduled,
           "True while a scheduled G-code export path is still held. Unlocked read, safe to poll.")
        // Last reported slicing progress of the current plate in whole
        // percent, or -1 when none was reported (the sentinel, NOT 0%).
        .def("slice_progress", [](GUI::Plater& plater) -> int {
            GUI::PartPlate* plate = plater.get_partplate_list().get_curr_plate();
            return plate == nullptr ? -1 : static_cast<int>(plate->get_slicing_percent());
        },
           "Slicing progress percent of the current plate, or -1 if none was reported yet. "
           "Unlocked read, safe to poll.")
        // ── Fork addition: plater actions (object management, layout, history, project,
        //    view). No upstream counterpart on either absorbed line; every mutator runs the
        //    same GUI path the corresponding menu item takes, so prompts, undo snapshots
        //    and refreshes behave exactly as if the user clicked it. All UI thread only.
        .def("remove_object", [](GUI::Plater& plater, int object_idx) {
            require_main_thread("remove_object");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            plater.remove(static_cast<size_t>(object_idx));
        }, py::arg("object_idx"),
           "Delete one object (the Delete menu path: removes it from the model, its plates and "
           "the undo history entry is created). UI thread only.")
        .def("delete_all_objects", [](GUI::Plater& plater) {
            require_main_thread("delete_all_objects");
            plater.delete_all_objects_from_model();
        }, "Delete every object on every plate. UI thread only.")
        .def("remove_selected", [](GUI::Plater& plater) {
            require_main_thread("remove_selected");
            plater.remove_selected();
        }, "Delete the objects selected in the 3D view. UI thread only.")
        .def("select_all", [](GUI::Plater& plater) {
            require_main_thread("select_all");
            plater.select_all();
        }, "Select every object in the 3D view. UI thread only.")
        .def("deselect_all", [](GUI::Plater& plater) {
            require_main_thread("deselect_all");
            plater.deselect_all();
        }, "Clear the 3D-view selection. UI thread only.")
        .def("select_current_plate_objects", [](GUI::Plater& plater) {
            require_main_thread("select_current_plate_objects");
            plater.select_curr_plate_all();
        }, "Select the objects on the current plate. UI thread only.")
        .def("is_selection_empty", &GUI::Plater::is_selection_empty,
           "True when nothing is selected in the 3D view. UI thread only.")
        .def("increase_instances", [](GUI::Plater& plater, int num) {
            require_main_thread("increase_instances");
            if (num < 1)
                throw py::value_error("increase_instances: num must be >= 1");
            plater.increase_instances(static_cast<size_t>(num));
        }, py::arg("num") = 1,
           "Add copies of the selected object (the + button). Acts on the current selection. "
           "UI thread only.")
        .def("decrease_instances", [](GUI::Plater& plater, int num) {
            require_main_thread("decrease_instances");
            if (num < 1)
                throw py::value_error("decrease_instances: num must be >= 1");
            plater.decrease_instances(static_cast<size_t>(num));
        }, py::arg("num") = 1,
           "Remove copies of the selected object (the - button). Acts on the current selection. "
           "UI thread only.")
        .def("duplicate_selection", [](GUI::Plater& plater) {
            require_main_thread("duplicate_selection");
            plater.clone_selection();
        }, "Duplicate the selected object(s) onto free space (the Duplicate menu path). UI thread only.")
        .def("center_selection", [](GUI::Plater& plater) {
            require_main_thread("center_selection");
            plater.center_selection();
        }, "Center the selected object(s) on the plate. UI thread only.")
        .def("mirror", [](GUI::Plater& plater, Axis axis) {
            require_main_thread("mirror");
            plater.mirror(axis);
        }, py::arg("axis"),
           "Mirror the selected object(s) across the given Axis (X/Y/Z). UI thread only.")
        .def("split_object", [](GUI::Plater& plater) {
            require_main_thread("split_object");
            plater.split_object();
        }, "Split the selected multi-part object into separate objects. UI thread only.")
        .def("split_volume", [](GUI::Plater& plater) {
            require_main_thread("split_volume");
            plater.split_volume();
        }, "Split the selected object into its constituent volumes. UI thread only.")
        .def("optimize_rotation", [](GUI::Plater& plater) {
            require_main_thread("optimize_rotation");
            plater.optimize_rotation();
        }, "Run the rotation optimizer on the selected object(s). UI thread only.")
        .def("arrange", [](GUI::Plater& plater) {
            require_main_thread("arrange");
            plater.arrange();
        }, "Auto-arrange all objects (the Arrange button; runs as a background job — poll "
           "slice_state()/the scene, it does not block). UI thread only.")
        .def("orient", [](GUI::Plater& plater) {
            require_main_thread("orient");
            plater.orient();
        }, "Auto-orient all objects (background job, like arrange()). UI thread only.")
        .def("fill_bed_with_instances", [](GUI::Plater& plater) {
            require_main_thread("fill_bed_with_instances");
            plater.fill_bed_with_instances();
        }, "Fill the bed with copies of the selected object (the Fill bed menu path). UI thread only.")
        .def("scale_selection_to_fit_print_volume", [](GUI::Plater& plater) {
            require_main_thread("scale_selection_to_fit_print_volume");
            plater.scale_selection_to_fit_print_volume();
        }, "Scale the selected object(s) down to fit the print volume. UI thread only.")
        .def("convert_unit", [](GUI::Plater& plater, ConversionType conv) {
            require_main_thread("convert_unit");
            plater.convert_unit(conv);
        }, py::arg("conv_type"),
           "Convert the selected object(s) between mm and inch/meter (the Convert unit menu "
           "path). UI thread only.")
        .def("copy_selection", [](GUI::Plater& plater) {
            require_main_thread("copy_selection");
            plater.copy_selection_to_clipboard();
        }, "Copy the selected object(s) to the internal clipboard. UI thread only.")
        .def("cut_selection", [](GUI::Plater& plater) {
            require_main_thread("cut_selection");
            plater.cut_selection_to_clipboard();
        }, "Cut the selected object(s) to the internal clipboard. UI thread only.")
        .def("paste", [](GUI::Plater& plater) {
            require_main_thread("paste");
            plater.paste_from_clipboard();
        }, "Paste from the internal clipboard. UI thread only.")
        .def("set_selected_visible", [](GUI::Plater& plater, bool visible) {
            require_main_thread("set_selected_visible");
            plater.set_selected_visible(visible);
        }, py::arg("visible"),
           "Show or hide the selected object(s) (hidden objects are not sliced). UI thread only.")
        .def("exit_gizmo", [](GUI::Plater& plater) {
            require_main_thread("exit_gizmo");
            plater.exit_gizmo();
        }, "Close any open gizmo (move/rotate/scale/...) and drop its selection grabber. "
           "UI thread only.")
        .def("undo", [](GUI::Plater& plater) {
            require_main_thread("undo");
            plater.undo();
        }, "Undo one step (the Edit menu path). UI thread only.")
        .def("redo", [](GUI::Plater& plater) {
            require_main_thread("redo");
            plater.redo();
        }, "Redo one step. UI thread only.")
        .def("can_undo", &GUI::Plater::can_undo, "True when undo is available. UI thread only.")
        .def("can_redo", &GUI::Plater::can_redo, "True when redo is available. UI thread only.")
        .def("can_arrange", &GUI::Plater::can_arrange, "True when arrange() is currently possible. UI thread only.")
        .def("can_mirror", &GUI::Plater::can_mirror, "True when mirror() is currently possible. UI thread only.")
        .def("can_split", &GUI::Plater::can_split, py::arg("to_objects"),
           "True when the selection can be split to objects (to_objects=True) or volumes "
           "(to_objects=False). UI thread only.")
        .def("can_increase_instances", &GUI::Plater::can_increase_instances,
           "True when increase_instances() is currently possible. UI thread only.")
        .def("can_decrease_instances", &GUI::Plater::can_decrease_instances,
           "True when decrease_instances() is currently possible. UI thread only.")
        .def("can_copy_to_clipboard", &GUI::Plater::can_copy_to_clipboard,
           "True when copy_selection() is currently possible. UI thread only.")
        .def("can_paste_from_clipboard", &GUI::Plater::can_paste_from_clipboard,
           "True when paste() is currently possible. UI thread only.")
        // ── Project lifecycle. new_project/save_project run the same flows as the menu
        //    items, including their confirmation and file dialogs; open_project is
        //    load_files() with LoadModel|LoadConfig, i.e. what a project open does.
        .def("open_project", [](GUI::Plater& plater, py::list paths) -> py::list {
            require_main_thread("open_project");
            if (paths.empty())
                throw py::value_error("paths must not be empty");
            std::vector<std::string> files;
            files.reserve(paths.size());
            for (auto item : paths) {
                const std::string path = py::str(item);
                if (path.empty())
                    throw py::value_error("paths contains an empty path");
                files.emplace_back(path);
            }
            const std::vector<size_t> added = plater.load_files(files,
                LoadStrategy::LoadModel | LoadStrategy::LoadConfig);
            py::list indices;
            for (const size_t idx : added)
                indices.append(py::int_(idx));
            return indices;
        }, py::arg("paths"),
           "Open a project file (3MF): its objects are added and its embedded presets are "
           "applied, like the Open Project menu path. Unlike load_model_files() this changes "
           "the active presets. UI thread only. Returns the indices of the added objects.")
        .def("new_project", [](GUI::Plater& plater, bool skip_confirm, bool silent, const std::string& project_name) {
            require_main_thread("new_project");
            return plater.new_project(skip_confirm, silent, wxString::FromUTF8(project_name));
        }, py::arg("skip_confirm") = false, py::arg("silent") = false, py::arg("project_name") = "",
           "Start a new empty project (the New Project menu path). skip_confirm suppresses the "
           "unsaved-changes prompt, silent suppresses progress feedback. UI thread only.")
        .def("save_project", [](GUI::Plater& plater, bool save_as) {
            require_main_thread("save_project");
            return plater.save_project(save_as);
        }, py::arg("save_as") = false,
           "Save the project; save_as=True raises the file dialog (the Save As menu path). "
           "UI thread only.")
        .def("is_loading_project", &GUI::Plater::is_loading_project,
           "True while a project is being loaded. Unlocked read, safe to poll.")
        .def("get_export_gcode_filename", [](GUI::Plater& plater, bool only_filename) {
            require_main_thread("get_export_gcode_filename");
            return GUI::into_u8(plater.get_export_gcode_filename(".gcode", only_filename, false));
        }, py::arg("only_filename") = false,
           "The G-code file name the next export would use (derived from the project name), "
           "or an empty string when none is derivable. only_filename strips the directory. "
           "UI thread only.")
        // ── View control.
        .def("select_view", [](GUI::Plater& plater, const std::string& direction) {
            require_main_thread("select_view");
            plater.select_view(direction);
        }, py::arg("direction"),
           "Point the camera: \"iso\", \"top\", \"bottom\", \"front\", \"rear\", \"left\", "
           "\"right\" or \"plate\". Applies to the current 3D/Preview panel. UI thread only.")
        .def("select_view_3D", [](GUI::Plater& plater, const std::string& name, bool no_slice) {
            require_main_thread("select_view_3D");
            plater.select_view_3D(name, no_slice);
        }, py::arg("name"), py::arg("no_slice") = true,
           "Switch the main view: \"3D\", \"Preview\" (slices if needed) or \"Assemble\". "
           "UI thread only.")
        .def("is_preview_shown", &GUI::Plater::is_preview_shown,
           "True when the Preview tab is the active view. UI thread only.")
        .def("only_gcode_mode", &GUI::Plater::only_gcode_mode,
           "True when the app runs in G-code viewer mode. Unlocked read, safe to poll.")
        .def("using_exported_file", &GUI::Plater::using_exported_file,
           "True when the current scene came from an exported/sliced file rather than a "
           "project. Unlocked read, safe to poll.")
        // ── Model editing (fork addition). Same architecture as apply_object_config:
        //    a direct Model-graph edit followed by the same snapshot/refresh/event the
        //    corresponding GUI path runs, so undo, the object list and other plugins'
        //    lifecycle hooks all see a plugin edit exactly like a user edit.
        .def("rename_object", [](GUI::Plater& plater, int object_idx, const std::string& name) {
            require_main_thread("rename_object");
            if (name.empty())
                throw py::value_error("rename_object: a name must not be empty");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            ModelObject* object = model.objects[object_idx];
            if (object->name == name)
                return false;
            const std::string previous_name = object->name;
            plater.take_snapshot("Rename Object");
            object->name = name;
            // The GUI rename propagates an object's name to its single volume.
            if (object->volumes.size() == 1)
                object->volumes[0]->name = name;
            Slic3r::save_object_mesh(*object);
            LifecycleEventContext ctx;
            ctx.name          = name;
            ctx.previous_name = previous_name;
            ctx.id            = std::to_string(object->id().id);
            ctx.index         = object_idx;
            ctx.source        = "object";
            fire_lifecycle_event(LifecycleEvent::ObjectRenamed, ctx);
            if (GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list())
                obj_list->update_name_for_items();
            return true;
        }, py::arg("object_idx"), py::arg("name"),
           "Rename one object (fires the same object-renamed lifecycle event and undo snapshot "
           "as the GUI rename; a single-volume object's volume is renamed with it). Returns "
           "True if the name changed, False if it already was that name. UI thread only.")
        .def("rename_volume", [](GUI::Plater& plater, int object_idx, int volume_idx, const std::string& name) {
            require_main_thread("rename_volume");
            if (name.empty())
                throw py::value_error("rename_volume: a name must not be empty");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            ModelObject* object = model.objects[object_idx];
            if (volume_idx < 0 || volume_idx >= static_cast<int>(object->volumes.size()))
                throw py::value_error("volume index out of range");
            ModelVolume* volume = object->volumes[volume_idx];
            if (volume->name == name)
                return false;
            const std::string previous_name = volume->name;
            plater.take_snapshot("Rename Part");
            volume->name = name;
            LifecycleEventContext ctx;
            ctx.name          = name;
            ctx.previous_name = previous_name;
            ctx.id            = std::to_string(volume->id().id);
            ctx.index         = volume_idx;
            ctx.source        = "volume";
            fire_lifecycle_event(LifecycleEvent::ObjectRenamed, ctx);
            if (GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list())
                obj_list->update_name_for_items();
            return true;
        }, py::arg("object_idx"), py::arg("volume_idx"), py::arg("name"),
           "Rename one volume of an object (same lifecycle event and undo snapshot as the GUI "
           "rename). Returns True if the name changed. UI thread only.")
        .def("apply_object_transform", [](GUI::Plater& plater, int object_idx, py::object translate,
                                          py::object rotate, py::object scale, py::object mirror) {
            require_main_thread("apply_object_transform");
            // Absolute set semantics, matching the readers (offset()/rotation()/...): each
            // given tuple REPLACES that transform component on every instance of the object.
            auto as_vec3 = [](py::object value, const char* who) -> Vec3d {
                if (value.is_none() || !py::isinstance<py::sequence>(value) || py::isinstance<py::str>(value))
                    throw py::value_error(std::string("apply_object_transform: ") + who
                                          + " must be an (x, y, z) tuple of numbers");
                py::sequence seq = py::reinterpret_borrow<py::sequence>(value);
                if (py::len(seq) != 3)
                    throw py::value_error(std::string("apply_object_transform: ") + who
                                          + " must be an (x, y, z) tuple");
                return Vec3d(seq[0].cast<double>(), seq[1].cast<double>(), seq[2].cast<double>());
            };
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            ModelObject* object = model.objects[object_idx];
            if (object->instances.empty())
                throw std::runtime_error("apply_object_transform: the object has no instances");
            bool any = false;
            Vec3d v;
            if (!translate.is_none()) { v = as_vec3(translate, "translate"); for (auto* inst : object->instances) inst->set_offset(v);      any = true; }
            if (!rotate.is_none())    { v = as_vec3(rotate, "rotate");       for (auto* inst : object->instances) inst->set_rotation(v);    any = true; }
            if (!scale.is_none())     { v = as_vec3(scale, "scale");         for (auto* inst : object->instances) inst->set_scaling_factor(v); any = true; }
            if (!mirror.is_none())    { v = as_vec3(mirror, "mirror");       for (auto* inst : object->instances) inst->set_mirror(v);       any = true; }
            if (any) {
                plater.take_snapshot("Transform Object");
                plater.changed_object(object_idx);
                refresh_object_settings_page();
            }
        }, py::arg("object_idx"), py::arg("translate") = py::none(), py::arg("rotate") = py::none(),
           py::arg("scale") = py::none(), py::arg("mirror") = py::none(),
           "Set transform components of every instance of one object (absolute, in the same "
           "units/angles offset()/rotation()/scaling_factor()/mirror() report: mm and radians; "
           "mirror is +/-1 per axis). Omitted components are untouched. Follows the same "
           "invalidation path as a GUI transform (undo snapshot + changed_object). UI thread only.")
        .def("apply_volume_config", [](GUI::Plater& plater, int object_idx, int volume_idx, py::dict values) -> py::list {
            require_main_thread("apply_volume_config");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            ModelObject* object = model.objects[object_idx];
            if (volume_idx < 0 || volume_idx >= static_cast<int>(object->volumes.size()))
                throw py::value_error("volume index out of range");
            ModelVolume* volume = object->volumes[volume_idx];
            py::list results;
            bool any_applied = false;
            for (auto item : values) {
                const std::string key   = py::str(item.first);
                const std::string value = py::str(item.second);
                try {
                    ConfigSubstitutionContext substitutions(ForwardCompatibilitySubstitutionRule::Disable);
                    volume->config.set_deserialize(key, value, substitutions);
                    results.append(py::make_tuple(key, true, ""));
                    any_applied = true;
                } catch (const std::exception& ex) {
                    results.append(py::make_tuple(key, false, ex.what()));
                }
            }
            if (any_applied) {
                plater.changed_object(object_idx);
                refresh_object_settings_page();
            }
            return results;
        }, py::arg("object_idx"), py::arg("volume_idx"), py::arg("values"),
           "Apply per-volume process overrides (the volume-level counterpart of "
           "apply_object_config). Returns [(key, ok, error), ...]. UI thread only.")
        .def("set_object_printable", [](GUI::Plater& plater, int object_idx, bool printable) {
            require_main_thread("set_object_printable");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            plater.take_snapshot("");
            for (auto* instance : model.objects[object_idx]->instances)
                instance->printable = printable;
            plater.get_view3D_canvas3D()->update_instance_printable_state_for_objects({static_cast<size_t>(object_idx)});
            plater.update();
            plater.reload_paint_after_background_process_apply();
        }, py::arg("object_idx"), py::arg("printable"),
           "Set the printable flag on every instance of one object (the object-level printable "
           "toggle). Follows the same snapshot/canvas refresh path as the GUI toggle. "
           "UI thread only.")
        .def("set_instance_printable", [](GUI::Plater& plater, int object_idx, int instance_idx, bool printable) {
            require_main_thread("set_instance_printable");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            ModelObject* object = model.objects[object_idx];
            if (instance_idx < 0 || instance_idx >= static_cast<int>(object->instances.size()))
                throw py::value_error("instance index out of range");
            plater.take_snapshot("");
            object->instances[instance_idx]->printable = printable;
            plater.get_view3D_canvas3D()->update_instance_printable_state_for_objects({static_cast<size_t>(object_idx)});
            plater.update();
            plater.reload_paint_after_background_process_apply();
        }, py::arg("object_idx"), py::arg("instance_idx"), py::arg("printable"),
           "Set the printable flag of one instance (the per-instance printable toggle). "
           "UI thread only.")
        .def("merge_volumes", [](GUI::Plater& plater, int object_idx, py::list volume_indices) {
            require_main_thread("merge_volumes");
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            ModelObject* object = model.objects[object_idx];
            std::vector<int> indices;
            indices.reserve(py::len(volume_indices));
            for (auto item : volume_indices) {
                const int volume_idx = item.cast<int>();
                if (volume_idx < 0 || volume_idx >= static_cast<int>(object->volumes.size()))
                    throw py::value_error("volume index out of range");
                indices.push_back(volume_idx);
            }
            if (indices.size() < 2)
                throw py::value_error("merge_volumes: at least two volume indices are required");
            // Plater::merge is a dead declaration on this fork; the model-level merge the
            // GUI wraps is ModelObject::merge_volumes (GUI_ObjectList.cpp's commented-out
            // merge_volumes shows the pairing with changed_object + list rebuild).
            object->merge_volumes(indices);
            plater.changed_object(object_idx);
            if (GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list())
                obj_list->part_selection_changed();
        }, py::arg("object_idx"), py::arg("volume_indices"),
           "Merge the given volumes of one object into a single part (the Merge button's "
           "path). UI thread only.")
        // ── Mesh export (fork addition). Same audit-checked write pattern as
        //    export_object_3mf: the plugin's file permission applies to C++ writes too.
        .def("export_object_stl", [](GUI::Plater& plater, int object_idx, const std::string& path, bool binary) {
            require_main_thread("export_object_stl");
            if (!boost::iends_with(path, ".stl"))
                throw py::value_error("export_object_stl() needs a path ending in .stl");
            if (PySys_Audit("open", "ssi", path.c_str(), "w", 0) < 0)
                throw py::error_already_set();
            Model& model = plater.model();
            if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
                throw py::value_error("object index out of range");
            if (!store_stl(path.c_str(), model.objects[object_idx], binary))
                throw std::runtime_error("Failed to write " + path);
            return path;
        }, py::arg("object_idx"), py::arg("path"), py::arg("binary") = true,
           "Export one object's mesh as an STL file (the object's merged volumes in its local, "
           "untransformed frame — the same mesh store_stl writes for the GUI). The path is "
           "audit-checked like a plugin file write. UI thread only. Returns the path.")
        .def("export_stl", [](GUI::Plater& plater, const std::string& path, bool binary) {
            require_main_thread("export_stl");
            if (!boost::iends_with(path, ".stl"))
                throw py::value_error("export_stl() needs a path ending in .stl");
            if (PySys_Audit("open", "ssi", path.c_str(), "w", 0) < 0)
                throw py::error_already_set();
            Model& model = plater.model();
            if (model.objects.empty())
                throw std::runtime_error("the project is empty — nothing to export");
            if (!store_stl(path.c_str(), &model, binary))
                throw std::runtime_error("Failed to write " + path);
            return path;
        }, py::arg("path"), py::arg("binary") = true,
           "Export the whole model as one STL file (all objects, all instances at their world "
           "positions — the Export STL menu item's mesh, minus the file dialog). The path is "
           "audit-checked like a plugin file write. UI thread only. Returns the path.");

    // Modeling domain (fork addition): primitives, plane cut, text/SVG volumes.
    host_bindings::register_modeling_methods(plater_class);
    // Editing completion (fork addition): simplify, netfabb repair, extruders.
    host_bindings::register_editing_methods(plater_class);

    // Facet painting (fork addition): support/seam/MMU/fuzzy paint data.
    host_bindings::register_painting_methods(plater_class);

    host.def("plater", &current_plater, py::return_value_policy::reference);
    host.def("model", []() -> Model& {
        return current_plater()->model();
    }, py::return_value_policy::reference);
    host.def("preset_bundle", &current_preset_bundle, py::return_value_policy::reference);
    // UI language of the running app ("en_US", "ru_RU", ...), so plugins can
    // localize their own dialogs. The app config file that stores this value
    // is deny-listed by the audit hook (it sits next to cloud secrets), so a
    // read-only accessor is the supported way to get just the language.
    // Kept as a fork addition; upstream folded this into app_info().
    host.def("app_language", []() -> std::string {
        if (wxTheApp == nullptr)
            throw std::runtime_error("OrcaSlicer application is not initialized");
        return GUI::into_u8(GUI::wxGetApp().current_language_code_safe());
    });
    host.def("app_info", &app_info,
             "The running app: version, mode, language, app_config_version (the version that wrote the app config "
             "before this run, empty when there was none), stealth_mode and is_signed_in. Upstream also reports the "
             "Orca/Bambu cloud states and the network plugin version; those agents are trimmed on this fork.");
    host.def("gl_info", &gl_info,
             "OpenGL vendor, renderer, version and glsl_version of the 3D view; None before it has been created. "
             "Upstream also reports core_profile; this fork's GLInfo does not track it.");
    // Fork addition: the app's data directory (presets, user data). Read-only string;
    // actually reading files there still goes through the filesystem permission sandbox.
    host.def("data_dir", []() -> std::string { return data_dir(); },
             "The application data directory (presets, caches, plugin storage live under it). "
             "Fork addition; accessing files under it still requires filesystem permission.");
}

} // namespace Slic3r
