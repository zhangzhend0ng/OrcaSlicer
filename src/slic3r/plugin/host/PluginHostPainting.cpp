#include "PluginHostPainting.hpp"

#include <pybind11/pybind11.h>

#include <libslic3r/Model.hpp>
#include <libslic3r/TriangleSelector.hpp>

#include <slic3r/GUI/Event.hpp>
#include <slic3r/GUI/GLCanvas3D.hpp>
#include <slic3r/GUI/GUI.hpp>
#include <slic3r/GUI/GUI_App.hpp>
#include <slic3r/GUI/GUI_ObjectList.hpp>
#include <slic3r/GUI/MainFrame.hpp>

#include <wx/event.h>

#include <string>

namespace py = pybind11;

namespace Slic3r {
namespace {

// Same gates as PluginHostModeling.cpp / PluginHostEditing.cpp (duplicated per binding TU).
void require_main_thread(const char* function_name)
{
    if (!wxIsMainThread())
        throw std::runtime_error(std::string(function_name) + "() must be called from the UI thread");
}

// NativeCommands.cpp's object_op() pattern (see PluginHostModeling.cpp).
void ensure_3d_view(GUI::Plater& plater)
{
    if (!plater.is_view3D_shown()) {
        plater.select_view_3D("3D");
        if (GUI::MainFrame* mf = GUI::wxGetApp().mainframe; mf != nullptr)
            mf->select_tab(TAB_ID_PREPARE);
    }
}

// The four annotation slots of ModelVolume and their paint-state alphabets.
// States are TriangleSelector::EnforcerBlockerType values: support/seam use
// NONE/ENFORCER/BLOCKER (0/1/2), fuzzy uses NONE/ENFORCER, and MMU stores the
// 1-based extruder number (state N paints facet with extruder N).
struct LayerInfo
{
    const char*                name;
    FacetsAnnotation ModelVolume::*slot;
    uint8_t                    max_state; // cap independent of the loaded filaments
};

const LayerInfo* find_layer(const std::string& name)
{
    static const LayerInfo layers[] = {
        {"fdm_support", &ModelVolume::supported_facets,        2},
        {"seam",        &ModelVolume::seam_facets,             2},
        {"mmu",         &ModelVolume::mmu_segmentation_facets, 255},
        {"fuzzy_skin",  &ModelVolume::fuzzy_skin_facets,       1},
    };
    for (const LayerInfo& info : layers)
        if (name == info.name)
            return &info;
    return nullptr;
}

ModelVolume* resolve_volume(GUI::Plater& plater, int object_idx, int volume_idx, const char* function_name)
{
    Model& model = plater.model();
    if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
        throw py::value_error("object index out of range");
    ModelObject* model_object = model.objects[object_idx];
    if (volume_idx < 0 || volume_idx >= static_cast<int>(model_object->volumes.size()))
        throw py::value_error("volume index out of range");
    ModelVolume* volume = model_object->volumes[volume_idx];
    // The painting gizmos only paint parts (update_model_object skips the rest).
    if (!volume->is_model_part())
        throw py::value_error(std::string(function_name) + ": only ModelPart volumes carry facet painting");
    return volume;
}

int loaded_filament_count(GUI::Plater& plater)
{
    return static_cast<int>(plater.get_extruder_colors_from_plater_config().size());
}

} // namespace

void host_bindings::register_painting_methods(pybind11::class_<GUI::Plater, std::unique_ptr<GUI::Plater, pybind11::nodelete>>& plater)
{
    // ── Facet painting (fork addition). The paint data of the four painting
    //    tools (FDM supports, seam, MMU segmentation, fuzzy skin) as one typed
    //    per-facet state array — the same shape the tools' selectors use
    //    internally, never a JSON/hex string (the 3mf hex form is an on-disk
    //    compatibility format, not a contract). State alphabet per layer is
    //    documented on set_facet_painting().
    plater
        .def("get_facet_painting", [](GUI::Plater& p, int object_idx, int volume_idx, const std::string& layer) {
            const LayerInfo* info = find_layer(layer);
            if (info == nullptr)
                throw py::value_error("get_facet_painting: unknown layer \"" + layer + "\" (fdm_support/seam/mmu/fuzzy_skin)");
            ModelVolume* volume = resolve_volume(p, object_idx, volume_idx, "get_facet_painting");
            const size_t facet_count = volume->mesh().facets_count();
            // A plain int list keeps the API usable on the embedded runtime (no numpy
            // guaranteed); np.asarray(result) restores a typed view when available.
            py::list states(facet_count);
            if ((volume->*info->slot).empty()) {
                for (size_t i = 0; i < facet_count; ++i)
                    PyList_SET_ITEM(states.ptr(), static_cast<Py_ssize_t>(i), py::int_(0).release().ptr());
                return states;
            }
            // Rebuild the per-facet view the painting gizmos hold in memory:
            // a fresh selector over the volume mesh with the annotation applied.
            TriangleSelector selector(volume->mesh());
            selector.deserialize((volume->*info->slot).get_data());
            for (size_t i = 0; i < facet_count; ++i)
                PyList_SET_ITEM(states.ptr(), static_cast<Py_ssize_t>(i),
                    py::int_(static_cast<uint8_t>(selector.get_facet(static_cast<int>(i)))).release().ptr());
            return states;
        }, py::arg("object_idx"), py::arg("volume_idx"), py::arg("layer"),
           "Read one volume's facet painting as a list of ints with one state per "
           "original triangle (index = triangle index into volume.mesh()). State "
           "alphabets: fdm_support/seam 0=none 1=enforcer 2=blocker; fuzzy_skin 0/1; "
           "mmu = the 1-based extruder painting the facet (0 = none). No painting is an "
           "all-zero array. Unlocked read, like the other model-data reads.")
        .def("set_facet_painting", [](GUI::Plater& p, int object_idx, int volume_idx, const std::string& layer,
                                      const py::sequence& states) {
            require_main_thread("set_facet_painting");
            ensure_3d_view(p);
            const LayerInfo* info = find_layer(layer);
            if (info == nullptr)
                throw py::value_error("set_facet_painting: unknown layer \"" + layer + "\" (fdm_support/seam/mmu/fuzzy_skin)");
            ModelVolume* volume = resolve_volume(p, object_idx, volume_idx, "set_facet_painting");

            // Any flat int sequence works (list/tuple, or a 1-D numpy array through
            // the sequence protocol) — the embedded runtime does not guarantee numpy.
            std::vector<uint8_t> input;
            input.reserve(states.size());
            for (py::handle item : states)
                input.push_back(static_cast<uint8_t>(PyLong_AsLong(item.ptr())));
            const size_t facet_count = volume->mesh().facets_count();
            if (input.size() != facet_count)
                throw py::value_error("set_facet_painting: expected " + std::to_string(facet_count) +
                                      " states (one per triangle of volume.mesh()), got " + std::to_string(input.size()));
            const uint8_t* in = input.data();
            uint8_t state_cap = info->max_state;
            if (layer == "mmu")
                // MMU states are 1-based extruder numbers; a state past the loaded
                // filaments would be silently ignored by slicing, so reject it.
                state_cap = static_cast<uint8_t>(std::max(2, loaded_filament_count(p)));
            for (size_t i = 0; i < facet_count; ++i)
                if (in[i] > state_cap)
                    throw py::value_error("set_facet_painting: state " + std::to_string(in[i]) + " at facet " + std::to_string(i) +
                                          " is out of range for layer \"" + layer + "\" (max " + std::to_string(state_cap) + ")");

            // A fresh all-NONE selector, the non-zero facets applied, then the
            // annotation replaced in one shot (FacetsAnnotation::set — the same
            // write the painting gizmos' update_model_object does).
            TriangleSelector selector(volume->mesh());
            size_t painted = 0;
            for (size_t i = 0; i < facet_count; ++i)
                if (in[i] != 0) {
                    selector.set_facet(static_cast<int>(i), static_cast<EnforcerBlockerType>(in[i]));
                    ++painted;
                }

            p.take_snapshot("Facet painting");
            const bool updated = (volume->*info->slot).set(selector);
            if (updated) {
                // The tail of GLGizmoFdmSupports::update_model_object: refresh the
                // object list info and let the host reslice in the background.
                if (GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list())
                    obj_list->update_info_items(static_cast<size_t>(object_idx));
                wxPostEvent(&p, SimpleEvent(EVT_GLCANVAS_SCHEDULE_BACKGROUND_PROCESS));
            }
            return painted;
        }, py::arg("object_idx"), py::arg("volume_idx"), py::arg("layer"), py::arg("states"),
           "Replace one volume's facet painting from a flat int sequence (list/tuple, or a "
           "1-D numpy array) with one state per original triangle — get_facet_painting's "
           "counterpart; "
           "0 leaves the facet unpainted. The write goes through the same FacetsAnnotation "
           "path the painting gizmos use, so undo, the 3D view and the next slice all see "
           "it. mmu states must not exceed the loaded filament count. Returns the number of "
           "painted facets. UI thread only.")
        .def("clear_facet_painting", [](GUI::Plater& p, int object_idx, int volume_idx, const std::string& layer) {
            require_main_thread("clear_facet_painting");
            const LayerInfo* info = find_layer(layer);
            if (info == nullptr)
                throw py::value_error("clear_facet_painting: unknown layer \"" + layer + "\" (fdm_support/seam/mmu/fuzzy_skin)");
            ModelVolume* volume = resolve_volume(p, object_idx, volume_idx, "clear_facet_painting");
            FacetsAnnotation& annotation = volume->*info->slot;
            if (annotation.empty())
                return false;
            p.take_snapshot("Facet painting");
            annotation.reset();
            if (GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list())
                obj_list->update_info_items(static_cast<size_t>(object_idx));
            wxPostEvent(&p, SimpleEvent(EVT_GLCANVAS_SCHEDULE_BACKGROUND_PROCESS));
            return true;
        }, py::arg("object_idx"), py::arg("volume_idx"), py::arg("layer"),
           "Remove one volume's facet painting on a layer (the eraser-everything path). "
           "Returns True if there was painting to remove. UI thread only.");
}

} // namespace Slic3r
