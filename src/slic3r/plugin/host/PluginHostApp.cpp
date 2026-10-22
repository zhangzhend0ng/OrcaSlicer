#include "PluginHostBindings.hpp"

#include <pybind11/cast.h>
#include <pybind11/pybind11.h>
#include <pybind11/pytypes.h>

#include <libslic3r/AppConfig.hpp>
#include <libslic3r/Model.hpp>
#include <libslic3r/PresetBundle.hpp>
#include <libslic3r/Semver.hpp>

#include "common_func/common_func.hpp" // Snapmaker_VERSION
#include <slic3r/GUI/GUI.hpp>
#include <slic3r/GUI/GUI_App.hpp>
#include <slic3r/GUI/OpenGLManager.hpp>
#include <slic3r/GUI/Plater.hpp>

#include <boost/algorithm/string/predicate.hpp>

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
             "file name and saved state are not changed, and the signed-in account is not written as the designer.");

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
