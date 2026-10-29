#include "PluginHostEditing.hpp"

#include <pybind11/gil.h> // py::gil_scoped_release (call guard)
#include <pybind11/pybind11.h>
#include <pybind11/stl.h> // std::optional casts

#include <libslic3r/Format/3mf.hpp>
#include <libslic3r/Model.hpp>
#include <libslic3r/QuadricEdgeCollapse.hpp>
#include <libslic3r/TriangleMesh.hpp>

#include <slic3r/GUI/Gizmos/GLGizmosManager.hpp>
#include <slic3r/GUI/GUI.hpp>
#include <slic3r/GUI/GUI_App.hpp>
#include <slic3r/GUI/GUI_ObjectList.hpp>
#include <slic3r/GUI/MainFrame.hpp>
#include <slic3r/GUI/ObjectDataViewModel.hpp>
#include <slic3r/Utils/FixModelByWin10.hpp>

#include <boost/filesystem.hpp>
#include <boost/thread.hpp>

#include <algorithm>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

namespace py = pybind11;

namespace Slic3r {
namespace {

// Same gates as PluginHostApp.cpp / PluginHostModeling.cpp (duplicated per binding TU):
// the model graph, the object list and the undo stack are UI-thread state.
void require_main_thread(const char* function_name)
{
    if (!wxIsMainThread())
        throw std::runtime_error(std::string(function_name) + "() must be called from the UI thread");
}

// NativeCommands.cpp's object_op() pattern (see PluginHostModeling.cpp): undo and the
// gizmos are gated on the Prepare tab's 3D view being shown.
void ensure_3d_view(GUI::Plater& plater)
{
    if (!plater.is_view3D_shown()) {
        plater.select_view_3D("3D");
        if (GUI::MainFrame* mf = GUI::wxGetApp().mainframe; mf != nullptr)
            mf->select_tab(TAB_ID_PREPARE);
    }
}

// ObjectList::fix_through_netfabb / ::simplify refuse to run with a gizmo open
// (GUI_ObjectList.cpp:5665, :5802) — "the snapshot time would refer to the
// internal stack". Same refusal here, as an exception naming the way out.
void require_gizmos_closed(GUI::Plater& plater, const char* function_name)
{
    GUI::GLCanvas3D* canvas = plater.get_view3D_canvas3D();
    if (canvas == nullptr)
        throw std::runtime_error(std::string(function_name) + ": the 3D view is not ready yet");
    if (!canvas->get_gizmos_manager().check_gizmos_closed_except(GUI::GLGizmosManager::Undefined))
        throw std::runtime_error(std::string(function_name) + ": a gizmo is open — call exit_gizmo() first "
                              "(an open gizmo would corrupt the undo snapshot)");
}

// NaN-safe positive check (!(v > 0) rejects 0, negatives and NaN), as in PluginHostModeling.cpp.
void validate_positive(const char* function_name, const char* what, double value)
{
    if (!(value > 0.))
        throw py::value_error(std::string(function_name) + ": " + what + " must be a positive number");
}

// ── Simplify ───────────────────────────────────────────────────────────────

size_t simplify_volume(GUI::Plater& plater, int object_idx, int volume_idx,
                       const std::optional<double>& keep_ratio, const std::optional<long long>& target_triangle_count,
                       const std::optional<double>& max_error)
{
    if (keep_ratio.has_value() == target_triangle_count.has_value())
        throw py::value_error("simplify_volume: give exactly one of keep_ratio / target_triangle_count");
    if (keep_ratio.has_value() && !(*keep_ratio > 0. && *keep_ratio <= 1.))
        throw py::value_error("simplify_volume: keep_ratio must be in (0, 1] (fraction of triangles to KEEP — "
                              "the GUI slider's percentage is the complement, removed triangles)");
    if (max_error.has_value())
        validate_positive("simplify_volume", "max_error", *max_error);

    Model& model = plater.model();
    if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
        throw py::value_error("object index out of range");
    ModelObject* model_object = model.objects[object_idx];
    if (volume_idx < 0 || volume_idx >= static_cast<int>(model_object->volumes.size()))
        throw py::value_error("volume index out of range");
    ModelVolume* volume = model_object->volumes[volume_idx];

    indexed_triangle_set its = volume->mesh().its; // copy: the collapse rewrites in place
    // The GUI's decimate_ratio is the REMOVED percentage (fix_count_by_ratio,
    // GLGizmoSimplify.cpp:689); this API takes the kept fraction instead.
    const uint32_t target = target_triangle_count.has_value()
        ? static_cast<uint32_t>(*target_triangle_count)
        : static_cast<uint32_t>(std::llround(static_cast<double>(its.indices.size()) * *keep_ratio));
    if (target < 4)
        throw py::value_error("simplify_volume: the target is below 4 triangles");
    if (target >= its.indices.size())
        throw py::value_error("simplify_volume: the volume is already at or below the target triangle count");

    float  quadric_max_error = max_error.value_or(0.f);
    float* quadric_max_error_ptr = max_error.has_value() ? &quadric_max_error : nullptr;
    // Pure libslic3r computation; the binding releases the GIL for it, so other
    // Python threads keep running while this (UI) thread works. Do not read the
    // model from another thread until this returns.
    its_quadric_edge_collapse(its, target, quadric_max_error_ptr);

    // The apply chain of GLGizmoSimplify::apply_simplify (GLGizmoSimplify.cpp:531-553).
    plater.take_snapshot("Simplify " + volume->name);
    plater.clear_before_change_mesh(object_idx);
    volume->set_mesh(TriangleMesh(std::move(its)));
    volume->calculate_convex_hull();
    volume->invalidate_convex_hull_2d();
    volume->set_new_unique_id();
    model_object->invalidate_bounding_box();
    model_object->ensure_on_bed();
    plater.changed_mesh(object_idx);
    if (GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list())
        obj_list->update_item_error_icon(object_idx, -1);
    return volume->mesh().facets_count();
}

// ── Netfabb-style repair (Windows 10 SDK WinRT backend) ────────────────────

bool netfabb_repair_available()
{
#ifdef HAS_WIN10SDK
    // Runtime check: is_windows10() reads the registry ProductName and rejects
    // builds the WinRT Printing3D repair does not support (FixModelByWin10.cpp:195).
    return is_windows10();
#else
    return false;
#endif
}

#ifdef HAS_WIN10SDK

// The worker body of fix_model_by_win10_sdk_gui (FixModelByWin10.cpp:342-411)
// without the progress dialog / cancellation plumbing: per volume a temp-3mf
// roundtrip through the WinRT repair, then the repaired meshes are applied.
// Runs on its own boost::thread like the GUI's, because COM needs an MTA
// context and the wx UI thread is STA; the UI thread joins without pumping,
// which is deadlock-safe because nothing here re-enters the UI.
bool netfabb_repair_worker(ModelObject& model_object, int volume_idx, std::string& failure)
{
    std::vector<ModelVolume*> volumes = (volume_idx == -1) ?
        model_object.volumes : std::vector<ModelVolume*>{model_object.volumes[volume_idx]};

    try {
        std::vector<TriangleMesh> meshes_repaired;
        meshes_repaired.reserve(volumes.size());
        for (ModelVolume* volume : volumes) {
            boost::filesystem::path path_src = boost::filesystem::temp_directory_path() / boost::filesystem::unique_path();
            path_src += ".3mf";
            boost::filesystem::path path_dst = boost::filesystem::temp_directory_path() / boost::filesystem::unique_path();
            path_dst += ".3mf";
            try {
                // store_3mf bakes the volume transform into the mesh; the dummy
                // volume's transform is neutralized so the repaired mesh, pushed
                // back into the original volume below, is not transformed twice.
                Model dummy;
                ModelObject* dummy_object = dummy.add_object();
                dummy_object->add_volume(*volume);
                dummy_object->volumes.back()->set_transformation(Geometry::Transformation());
                dummy_object->add_instance();
                if (!Slic3r::store_3mf(path_src.string().c_str(), &dummy, nullptr, false, nullptr, false))
                    throw Slic3r::RuntimeError("Exporting 3mf file failed");
                // The core invokes both callbacks unconditionally, so pass no-ops:
                // headless repair is uncancellable and swallows progress.
                fix_model_by_win10_sdk(path_src.string(), path_dst.string(),
                    [](const char*, unsigned) {}, []() {});
                Model repaired;
                DynamicPrintConfig config;
                ConfigSubstitutionContext config_substitutions{ForwardCompatibilitySubstitutionRule::EnableSilent};
                if (!Slic3r::load_3mf(path_dst.string().c_str(), config, config_substitutions, &repaired, false))
                    throw Slic3r::RuntimeError("Import 3mf file failed");
                if (repaired.objects.size() != 1)
                    throw Slic3r::RuntimeError(repaired.objects.empty() ?
                        "Repaired 3mf file does not contain any object" : "Repaired 3mf file contains more than one object");
                if (repaired.objects.front()->volumes.size() != 1)
                    throw Slic3r::RuntimeError(repaired.objects.front()->volumes.empty() ?
                        "Repaired 3mf file does not contain any volume" : "Repaired 3mf file contains more than one volume");
                meshes_repaired.emplace_back(std::move(repaired.objects.front()->volumes.front()->mesh()));
            } catch (...) {
                // Temp files must not survive any failure path (the GUI wrapper
                // leaks them; this side does not).
                boost::system::error_code ec;
                boost::filesystem::remove(path_src, ec);
                boost::filesystem::remove(path_dst, ec);
                throw;
            }
            boost::system::error_code ec;
            boost::filesystem::remove(path_src, ec);
            boost::filesystem::remove(path_dst, ec);
        }
        for (size_t i = 0; i < volumes.size(); ++i) {
            volumes[i]->set_mesh(std::move(meshes_repaired[i]));
            volumes[i]->calculate_convex_hull();
            volumes[i]->invalidate_convex_hull_2d();
            volumes[i]->set_new_unique_id();
        }
        model_object.invalidate_bounding_box();
        return true;
    } catch (const std::exception& ex) {
        failure = ex.what();
        return false;
    } catch (...) {
        failure = "unknown repair failure";
        return false;
    }
}

#endif // HAS_WIN10SDK

void fix_through_netfabb(GUI::Plater& plater, int object_idx, int volume_idx)
{
    require_gizmos_closed(plater, "fix_through_netfabb");
#ifndef HAS_WIN10SDK
    (void) object_idx;
    throw std::runtime_error("fix_through_netfabb: this build has no Windows 10 SDK repair backend "
                             "(is_netfabb_repair_available() is False)");
#else
    if (!is_windows10())
        throw std::runtime_error("fix_through_netfabb: Only Windows 10 is supported.");

    Model& model = plater.model();
    if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
        throw py::value_error("object index out of range");
    ModelObject* model_object = model.objects[object_idx];
    if (volume_idx != -1 && (volume_idx < 0 || volume_idx >= static_cast<int>(model_object->volumes.size())))
        throw py::value_error("volume index out of range");

    // The refresh chain of ObjectList::fix_through_netfabb (GUI_ObjectList.cpp:5661),
    // one object at a time, minus the progress dialog and its cancellation.
    GUI::Plater::TakeSnapshot snapshot(&plater, "Repairing model object");
    plater.clear_before_change_mesh(object_idx);

    std::string failure;
    bool        success = false;
    {
        boost::thread worker([&model_object, volume_idx, &failure, &success]() {
            success = netfabb_repair_worker(*model_object, volume_idx, failure);
        });
        worker.join();
    }
    if (!success) {
        // The GUI leaves the cleared-mesh state behind on failure; restore a
        // consistent scene before raising, so a failed plugin call is a no-op.
        plater.changed_mesh(object_idx);
        throw std::runtime_error("fix_through_netfabb: " + failure);
    }

    model_object->ensure_on_bed();
    plater.changed_mesh(object_idx);
    plater.get_partplate_list().notify_instance_update(object_idx, 0);
    if (GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list()) {
        obj_list->update_plate_values_for_items();
        obj_list->update_item_error_icon(object_idx, volume_idx);
        obj_list->update_info_items(static_cast<size_t>(object_idx));
    }
#endif
}

// ── Extruder assignment (the fill_color data path) ─────────────────────────

int loaded_filament_count(GUI::Plater& plater)
{
    // include_mixed stays at its default true — the GUI gate counts the virtual
    // mixed filaments too (set_extruder_for_selected_items, GUI_ObjectList.cpp:5990).
    return static_cast<int>(plater.get_extruder_colors_from_plater_config().size());
}

void validate_extruder(GUI::Plater& plater, int extruder)
{
    if (extruder < 0)
        throw py::value_error("extruder must be >= 0 (0 = inherit)");
    const int count = loaded_filament_count(plater);
    if (extruder > count)
        throw py::value_error("extruder exceeds the number of loaded filaments (" + std::to_string(count) + ")");
}

// The refresh tail set_extruder_for_selected_items runs for one tree item
// (GUI_ObjectList.cpp:6046-6067): fila-column icon, scene update, usage notify.
void refresh_extruder_assignment(GUI::Plater& plater, GUI::ObjectList* obj_list, int object_idx, int volume_idx, int extruder)
{
    if (obj_list == nullptr)
        return;
    if (ObjectDataViewModel* objects_model = obj_list->GetModel()) {
        const wxDataViewItem item = (volume_idx == -1) ?
            objects_model->GetItemById(object_idx) : objects_model->GetItemByVolumeId(object_idx, volume_idx);
        if (item.IsOk())
            objects_model->SetExtruder(wxString::Format("%d", extruder), item);
    }
    plater.update();
    plater.notify_filament_usage_changed();
    obj_list->Refresh(); // repaint the extruder/filament column
}

bool set_object_extruder(GUI::Plater& plater, int object_idx, int extruder)
{
    validate_extruder(plater, extruder);
    Model& model = plater.model();
    if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
        throw py::value_error("object index out of range");
    ModelObject* model_object = model.objects[object_idx];

    bool changed = model_object->config.has("extruder") ?
        model_object->config.opt_int("extruder") != extruder : extruder != 0;

    plater.take_snapshot("Change Filaments");
    if (model_object->config.has("extruder"))
        model_object->config.set("extruder", extruder);
    else
        model_object->config.set_key_value("extruder", new ConfigOptionInt(extruder));
    // The GUI clears the object's part volumes' own extruder overrides so they
    // follow the object again (GUI_ObjectList.cpp:6049-6053).
    for (ModelVolume* volume : model_object->volumes)
        if (volume->type() == ModelVolumeType::MODEL_PART && volume->config.has("extruder")) {
            volume->config.erase("extruder");
            changed = true;
        }

    refresh_extruder_assignment(plater, GUI::wxGetApp().obj_list(), object_idx, -1, extruder);
    return changed;
}

bool set_volume_extruder(GUI::Plater& plater, int object_idx, int volume_idx, int extruder)
{
    validate_extruder(plater, extruder);
    Model& model = plater.model();
    if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
        throw py::value_error("object index out of range");
    ModelObject* model_object = model.objects[object_idx];
    if (volume_idx < 0 || volume_idx >= static_cast<int>(model_object->volumes.size()))
        throw py::value_error("volume index out of range");
    ModelVolume* volume = model_object->volumes[volume_idx];
    if (volume->type() != ModelVolumeType::MODEL_PART && volume->type() != ModelVolumeType::PARAMETER_MODIFIER)
        throw py::value_error("set_volume_extruder: only ModelPart and ParameterModifier volumes take an extruder");

    // The GUI bakes extruder 0 on a part to the parent object's current
    // extruder instead of storing 0 (GUI_ObjectList.cpp:6024-6032); modifiers
    // keep the 0 ("inherit").
    int effective = extruder;
    if (extruder == 0 && volume->type() == ModelVolumeType::MODEL_PART)
        effective = model_object->config.has("extruder") ? model_object->config.opt_int("extruder") : 0;

    const bool changed = volume->config.has("extruder") ?
        volume->config.opt_int("extruder") != effective : effective != 0;

    plater.take_snapshot("Change Filaments");
    if (volume->config.has("extruder"))
        volume->config.set("extruder", effective);
    else
        volume->config.set_key_value("extruder", new ConfigOptionInt(effective));

    refresh_extruder_assignment(plater, GUI::wxGetApp().obj_list(), object_idx, volume_idx, effective);
    return changed;
}

} // namespace

void host_bindings::register_editing_methods(pybind11::class_<GUI::Plater, std::unique_ptr<GUI::Plater, pybind11::nodelete>>& plater)
{
    // ── Editing completion (fork addition): mesh simplification, netfabb-style
    //    repair and extruder assignment, running the same snapshot/refresh
    //    chains the matching GUI paths run. UI thread only (except the
    //    availability probe).
    plater
        .def("simplify_volume", [](GUI::Plater& p, int object_idx, int volume_idx, std::optional<double> keep_ratio,
                                   std::optional<long long> target_triangle_count, std::optional<double> max_error) {
            require_main_thread("simplify_volume");
            ensure_3d_view(p);
            require_gizmos_closed(p, "simplify_volume");
            return simplify_volume(p, object_idx, volume_idx, keep_ratio, target_triangle_count, max_error);
        }, py::arg("object_idx"), py::arg("volume_idx"), py::arg("keep_ratio") = py::none(),
           py::arg("target_triangle_count") = py::none(), py::arg("max_error") = py::none(),
           py::call_guard<py::gil_scoped_release>(),
           "Quadric-edge-collapse decimation of one volume (the Simplify tool's engine, without its "
           "preview gizmo). Give exactly one of keep_ratio — fraction of triangles to KEEP; note the "
           "GUI slider shows the complement, removed percentage — or target_triangle_count (>= 4, "
           "below the current count). max_error optionally caps the quadric error. Synchronous and "
           "runs on the calling thread: large meshes freeze the UI for the duration, and the GIL is "
           "released so other Python threads run but must not read the model meanwhile. Returns the "
           "new triangle count. UI thread only.")
        .def("is_netfabb_repair_available", [](GUI::Plater&) { return netfabb_repair_available(); },
           "True when this build carries the Windows 10 SDK repair backend AND this system supports "
           "the WinRT Printing3D repair it uses. Unlocked read, safe from any thread.")
        .def("fix_through_netfabb", [](GUI::Plater& p, int object_idx, int volume_idx) {
            require_main_thread("fix_through_netfabb");
            ensure_3d_view(p);
            fix_through_netfabb(p, object_idx, volume_idx);
        }, py::arg("object_idx"), py::arg("volume_idx") = -1,
           "Repair one object's mesh (volume_idx = -1) or a single volume through the Windows 10 "
           "SDK's netfabb-style WinRT repair — the Fix through netfabb menu path minus its progress "
           "dialog. Synchronous: blocks the calling thread until the repair finishes; throws when the "
           "backend is unavailable (probe with is_netfabb_repair_available()) or the repair fails "
           "(leaving the model unchanged). Raises while any gizmo is open — call exit_gizmo() first. "
           "UI thread only.")
        .def("set_object_extruder", [](GUI::Plater& p, int object_idx, int extruder) {
            require_main_thread("set_object_extruder");
            ensure_3d_view(p);
            return set_object_extruder(p, object_idx, extruder);
        }, py::arg("object_idx"), py::arg("extruder"),
           "Assign a whole object to an extruder/filament (the assemble-view fill_color data path): "
           "extruder is 1-based, 0 means inherit the global default, and it must not exceed the "
           "number of loaded filaments. The object's part volumes drop their own extruder "
           "overrides, following the object again. Returns True if anything changed. UI thread only.")
        .def("set_volume_extruder", [](GUI::Plater& p, int object_idx, int volume_idx, int extruder) {
            require_main_thread("set_volume_extruder");
            ensure_3d_view(p);
            return set_volume_extruder(p, object_idx, volume_idx, extruder);
        }, py::arg("object_idx"), py::arg("volume_idx"), py::arg("extruder"),
           "Assign one volume to an extruder/filament — parts and parameter modifiers only. "
           "extruder 0 on a part is baked to the parent object's current extruder (the GUI "
           "behavior); a modifier keeps the 0 (inherit). Returns True if anything changed. "
           "UI thread only.");
}

} // namespace Slic3r
