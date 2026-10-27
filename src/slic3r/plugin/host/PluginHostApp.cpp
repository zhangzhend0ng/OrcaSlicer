#include "PluginHostBindings.hpp"

#include <pybind11/cast.h>
#include <pybind11/pybind11.h>
#include <pybind11/pytypes.h>

#include <libslic3r/AppConfig.hpp>
#include <libslic3r/Config.hpp>
#include <libslic3r/Format/bbs_3mf.hpp>
#include <libslic3r/Model.hpp>
#include <libslic3r/PresetBundle.hpp>
#include <libslic3r/Semver.hpp>

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
    py::class_<GUI::Plater, std::unique_ptr<GUI::Plater, py::nodelete>>(host, "Plater")
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
           "Unlocked read, safe to poll.");

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
}

} // namespace Slic3r
