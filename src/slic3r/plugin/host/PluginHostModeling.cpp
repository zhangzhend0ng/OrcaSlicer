#include "PluginHostModeling.hpp"

#include <pybind11/stl.h> // std::optional casts for size/name parameters

#include <libslic3r/BuildVolume.hpp>
#include <libslic3r/CutUtils.hpp>
#include <libslic3r/Emboss.hpp>
#include <libslic3r/EmbossShape.hpp>
#include <libslic3r/Model.hpp>
#include <libslic3r/NSVGUtils.hpp>
#include <libslic3r/TextConfiguration.hpp>
#include <libslic3r/TriangleMesh.hpp>
#include <libslic3r/Utils.hpp> // resources_dir()

#include <slic3r/GUI/Gizmos/GLGizmoSVG.hpp>
#include <slic3r/GUI/Gizmos/GLGizmosManager.hpp>
#include <slic3r/GUI/GLCanvas3D.hpp>
#include <slic3r/GUI/GUI.hpp>
#include <slic3r/GUI/GUI_App.hpp>
#include <slic3r/GUI/MainFrame.hpp>
#include <slic3r/GUI/GUI_ObjectList.hpp>

#include <boost/algorithm/string/predicate.hpp>
#include <boost/filesystem.hpp>
#include <boost/nowide/convert.hpp>

#include <wx/utils.h> // wxBusyCursor

#include <algorithm>
#include <cmath>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace py = pybind11;

namespace Slic3r {
namespace {

// Same gate every Plater mutator in PluginHostApp.cpp runs: the model graph,
// the object list and the undo stack are UI-thread state.
void require_main_thread(const char* function_name)
{
    if (!wxIsMainThread())
        throw std::runtime_error(std::string(function_name) + "() must be called from the UI thread");
}

// NativeCommands.cpp's object_op() pattern: the modeling surface is gated on
// the Prepare tab's 3D view being shown — can_undo()/undo() check
// is_view3D_shown() (Plater.cpp:25394) and the gizmos lazy-init on the first
// 3D render — so switch there first, like a user-driven menu action would.
void ensure_3d_view(GUI::Plater& plater)
{
    if (!plater.is_view3D_shown()) {
        plater.select_view_3D("3D");
        if (GUI::MainFrame* mf = GUI::wxGetApp().mainframe; mf != nullptr)
            mf->select_tab(TAB_ID_PREPARE);
    }
}

// The read-side twin of the audit PluginHostApp.cpp raises before C++ file
// writes: Emboss::create_font_file and the SVG loader read from C++, so raise
// the same open(path, "r") event Python's open() raises — the plugin gets the
// same deny list, permissions and prompt as for reading the file itself.
void audit_plugin_read(const std::string& path)
{
    if (PySys_Audit("open", "ssi", path.c_str(), "r", 0) < 0)
        throw py::error_already_set();
}

// NaN-safe positive check (!(v > 0) rejects 0, negatives and NaN) with an
// upper bound against absurd geometry.
void validate_positive_mm(const char* function_name, const char* what, double value, double max_mm)
{
    if (!(value > 0.))
        throw py::value_error(std::string(function_name) + ": " + what + " must be a positive number (mm)");
    if (!(value <= max_mm))
        throw py::value_error(std::string(function_name) + ": " + what + " must not exceed " + std::to_string((long long) max_mm) + " mm");
}

constexpr uintmax_t MAX_FONT_SVG_FILE_SIZE = 50ull * 1024ull * 1024ull; // fonts/SVGs are far below this

void validate_readable_file(const char* function_name, const std::string& path, const char* what)
{
    const boost::filesystem::path fs_path(path);
    boost::system::error_code ec;
    if (!boost::filesystem::exists(fs_path, ec) || ec)
        throw py::value_error(std::string(function_name) + ": the " + what + " does not exist: " + path);
    const uintmax_t size = boost::filesystem::file_size(fs_path, ec);
    if (ec || size == static_cast<uintmax_t>(-1))
        throw py::value_error(std::string(function_name) + ": the " + what + " cannot be stat'ed: " + path);
    if (size > MAX_FONT_SVG_FILE_SIZE)
        throw py::value_error(std::string(function_name) + ": the " + what + " is larger than 50 MB");
}

// The multi-line text also becomes the default volume/object name; the GUI
// replaces newlines with spaces there (create_emboss_data_base).
std::string single_line(const std::string& text)
{
    std::string out = text;
    std::replace(out.begin(), out.end(), '\n', ' ');
    return out;
}

// ── Primitives ─────────────────────────────────────────────────────────────

const std::vector<std::string>& primitive_shape_names()
{
    static const std::vector<std::string> shapes = {"cube", "cylinder", "sphere", "slab", "cone", "disc", "torus"};
    return shapes;
}

bool is_known_primitive_shape(const std::string& shape)
{
    const std::vector<std::string>& names = primitive_shape_names();
    return std::find(names.begin(), names.end(), shape) != names.end();
}

// Upstream SoftFever/OrcaSlicer GUI_ObjectList.cpp (after #16848, "Ask for the
// size of a primitive"): the facet step keeps a circle of this radius within
// 0.002 mm of ideal, clamped to 16..720 segments. The fork's create_mesh still
// uses the fixed PI/90..PI/60 steps; the host API follows the upstream formula.
double primitive_angle_step(double radius)
{
    const double step = 2. * std::acos(1. - std::min(1., 0.002 / radius));
    return std::clamp(step, 2. * PI / 720., 2. * PI / 16.);
}

// The geometry table of GUI_ObjectList::create_mesh (GUI_ObjectList.cpp:2396):
// everything scales with one "side" length except the slab, which is sized
// from the target instance's bounding box. Default dimensions per shape match
// the fork's menu defaults (disc height 0.2 mm, torus tube 1/8 of the side).
TriangleMesh create_primitive_mesh(const std::string& shape, double side, const BoundingBoxf3& slab_bb)
{
    if (shape == "cube")
        return TriangleMesh(its_make_cube(side, side, side));
    if (shape == "cylinder")
        return TriangleMesh(its_make_cylinder(0.5 * side, side, primitive_angle_step(0.5 * side)));
    if (shape == "sphere")
        return TriangleMesh(its_make_sphere(0.5 * side, primitive_angle_step(0.5 * side)));
    if (shape == "slab")
        return TriangleMesh(its_make_cube(slab_bb.size().x() * 1.5, slab_bb.size().y() * 1.5, slab_bb.size().z() * 0.5));
    if (shape == "cone")
        return TriangleMesh(its_make_cone(0.5 * side, side, primitive_angle_step(0.5 * side)));
    if (shape == "disc")
        return TriangleMesh(its_make_cylinder(0.5 * side, 0.2, primitive_angle_step(0.5 * side)));
    return TriangleMesh(its_make_torus(0.5 * side, 0.125 * side, primitive_angle_step(0.5 * side)));
}

// GLCanvas3D::get_size_proportional_to_max_bed_size(0.1): 10% of the larger
// bed side, computed without the canvas.
double bed_proportional_side(GUI::Plater& plater)
{
    const BoundingBoxf bed_bb = plater.build_volume().bounding_volume2d();
    return 0.1 * std::max(bed_bb.size()[0], bed_bb.size()[1]);
}

std::string default_primitive_name(const std::string& shape)
{
    std::string name = shape;
    if (!name.empty())
        name[0] = static_cast<char>(std::toupper(static_cast<unsigned char>(name[0])));
    return name;
}

size_t add_primitive_object(GUI::Plater& plater, const std::string& shape, bool has_size, double size,
                            const std::optional<std::string>& name)
{
    ensure_3d_view(plater);
    // The GUI's standalone-slab path passes an empty bounding box and produces
    // a degenerate 0x0x0 cube (GUI_ObjectList.cpp:2412 uses the caller's bb;
    // load_shape_object passes a default-constructed one) — refuse it here.
    if (shape == "slab")
        throw py::value_error("add_primitive: \"slab\" is sized from an existing object's bounding box; "
                              "add it with add_primitive_volume() instead");
    if (has_size)
        validate_positive_mm("add_primitive", "size", size, 10000.);
    const double side = has_size ? size : bed_proportional_side(plater);

    TriangleMesh mesh = create_primitive_mesh(shape, side, BoundingBoxf3());
    if (mesh.empty())
        throw std::runtime_error("add_primitive: the primitive mesh could not be created");

    GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list();
    if (obj_list == nullptr || plater.canvas3D() == nullptr)
        throw std::runtime_error("add_primitive: the 3D view is not ready yet");
    // load_mesh_object does not snapshot itself — load_shape_object wraps the
    // call (GUI_ObjectList.cpp:2541); mirror that pairing here.
    GUI::Plater::TakeSnapshot snapshot(&plater, "Add Primitive");
    obj_list->load_mesh_object(mesh, GUI::from_u8(name.value_or(default_primitive_name(shape))));
    // Model::add_object appends, so the new object is the last one.
    return plater.model().objects.size() - 1;
}

// ObjectList::apply_object_instance_transfrom_to_all_volumes (GUI_ObjectList.cpp:6256)
// is private; replicated with the assemble-matrix update the add-primitive
// caller takes. Absorbs the instance transform into every volume and keeps the
// object in place, so the BBS assemble view and the scene stay consistent.
void apply_instance_transform_to_all_volumes(GUI::Plater& plater, ModelObject* model_object)
{
    const Geometry::Transformation instance_transformation = model_object->instances[0]->get_transformation();
    const Vec3d original_instance_center = instance_transformation.get_offset();

    Geometry::Transformation instance_no_offset = instance_transformation;
    instance_no_offset.set_offset(Vec3d(0., 0., 0.));
    const Transform3d instance_inverse_matrix = instance_no_offset.get_matrix().inverse();
    const Transform3d assemble_matrix = model_object->instances[0]->get_assemble_transformation().get_matrix();
    model_object->instances[0]->set_assemble_from_transform(assemble_matrix * instance_inverse_matrix);

    const Transform3d transformation_matrix = instance_transformation.get_matrix();
    for (ModelVolume* volume : model_object->volumes)
        volume->set_transformation(transformation_matrix * volume->get_matrix());
    model_object->instances[0]->set_transformation(Geometry::Transformation());

    model_object->ensure_on_bed();
    model_object->translate(-original_instance_center);
    model_object->translate_instances(original_instance_center);

    plater.update();
}

size_t add_primitive_volume(GUI::Plater& plater, const std::string& shape, int object_idx, int instance_idx,
                            ModelVolumeType type, bool has_size, double size, const std::optional<std::string>& name)
{
    ensure_3d_view(plater);
    if (type == ModelVolumeType::INVALID)
        throw py::value_error("add_primitive_volume: volume_type must not be Invalid");
    if (shape == "slab" && has_size)
        throw py::value_error("add_primitive_volume: \"slab\" takes its size from the target instance's "
                              "bounding box; size is not accepted for it");
    if (has_size)
        validate_positive_mm("add_primitive_volume", "size", size, 10000.);
    const double side = has_size ? size : bed_proportional_side(plater);

    Model& model = plater.model();
    if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
        throw py::value_error("object index out of range");
    ModelObject* model_object = model.objects[object_idx];
    if (instance_idx < 0 || instance_idx >= static_cast<int>(model_object->instances.size()))
        throw py::value_error("instance index out of range");

    const BoundingBoxf3 instance_bb = model_object->instance_bounding_box(instance_idx);
    TriangleMesh mesh = create_primitive_mesh(shape, side, instance_bb);
    if (mesh.empty())
        throw std::runtime_error("add_primitive_volume: the primitive mesh could not be created");

    // The model section of load_generic_subobject (GUI_ObjectList.cpp:2424),
    // with the explicit object/instance in place of the GUI selection. The
    // TipsDialog and the params-panel switch at the end are GUI-only and
    // deliberately not run.
    GUI::Plater::TakeSnapshot snapshot(&plater, "Add primitive");
    ModelVolume* new_volume = model_object->add_volume(std::move(mesh), type);

    // Align the new volume with the print bed and move it to a pickable spot:
    // the left front corner of the instance's bounding box (the slab is only
    // lifted to the bed).
    const ModelInstance& instance = *model_object->instances[instance_idx];
    new_volume->set_transformation(instance.get_transformation().get_matrix_no_offset().inverse());
    const BoundingBoxf3 mesh_bb = new_volume->mesh().bounding_box();
    const Vec3d offset = (shape == "slab") ?
        Vec3d(0., 0., 0.5 * mesh_bb.size().z() + instance_bb.min.z() - instance.get_offset().z()) :
        Vec3d(instance_bb.max.x(), instance_bb.min.y(), instance_bb.min.z()) + 0.5 * mesh_bb.size() - instance.get_offset();
    new_volume->set_offset(instance.get_transformation().get_matrix_no_offset().inverse() * offset);

    Slic3r::save_object_mesh(*model_object);
    new_volume->name = name.value_or("Generic-" + shape);
    // A default extruder, like the GUI: the object's extruder for model parts, 0 otherwise.
    int extruder_id = 0;
    if (type == ModelVolumeType::MODEL_PART && model_object->config.has("extruder"))
        extruder_id = model_object->config.opt_int("extruder");
    new_volume->config.set_key_value("extruder", new ConfigOptionInt(extruder_id));
    new_volume->source.is_from_builtin_objects = true;

    GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list();
    if (obj_list == nullptr)
        throw std::runtime_error("add_primitive_volume: the object list is not ready yet");
    obj_list->select_item([&obj_list, object_idx, new_volume]() {
        wxDataViewItemArray items = obj_list->reorder_volumes_and_get_selection(object_idx,
            [new_volume](const ModelVolume* volume) { return volume == new_volume; });
        return items.IsEmpty() ? wxDataViewItem() : items.front();
    });
    if (type == ModelVolumeType::MODEL_PART)
        if (GUI::GLCanvas3D* canvas = plater.get_view3D_canvas3D())
            canvas->update_instance_printable_state_for_object(static_cast<size_t>(object_idx));
    apply_instance_transform_to_all_volumes(plater, model_object);
    obj_list->selection_changed();
    obj_list->notify_instance_updated(object_idx);

    // reorder_volumes_and_get_selection may re-sort model_object->volumes;
    // resolve the answer by identity.
    for (size_t i = 0; i < model_object->volumes.size(); ++i)
        if (model_object->volumes[i] == new_volume)
            return i;
    throw std::runtime_error("add_primitive_volume: the added volume could not be resolved");
}

// ── Plane cut ──────────────────────────────────────────────────────────────

std::vector<size_t> cut_plane(GUI::Plater& plater, int object_idx, int instance_idx, double z,
                              bool keep_upper, bool keep_lower, bool keep_as_parts,
                              bool flip_upper, bool flip_lower, bool place_on_cut_upper, bool place_on_cut_lower)
{
    ensure_3d_view(plater);
    Model& model = plater.model();
    if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
        throw py::value_error("object index out of range");
    ModelObject* object = model.objects[object_idx];
    if (instance_idx < 0 || instance_idx >= static_cast<int>(object->instances.size()))
        throw py::value_error("instance index out of range");
    // cut_horizontal silently returns on this (Plater.cpp:18767); a host call
    // doing nothing invisibly is worse than an error.
    if (!keep_upper && !keep_lower)
        throw py::value_error("cut_horizontal: at least one of keep_upper/keep_lower is required");

    // An out-of-range z makes the kept side empty; the upstream flow would
    // then still delete the object (apply_cut_object_to_model erases it before
    // appending nothing, Plater.cpp:20714) — silent data loss, so reject the
    // z up front instead. NaN-safe: !(z > lo && z < hi) rejects NaN.
    const BoundingBoxf3 instance_bb = object->instance_bounding_box(instance_idx);
    const double eps = 1e-6;
    if (!(z > instance_bb.min.z() + eps && z < instance_bb.max.z() - eps))
        throw py::value_error("cut_horizontal: z must lie strictly inside the instance's bounding box (Z "
                              + std::to_string(instance_bb.min.z()) + ".." + std::to_string(instance_bb.max.z())
                              + ", bed/world coordinates)");

    // only_if is enum_bitmask's conditional-flag helper (enum_bitmask.hpp);
    // bitmask::operator|= has a latent defect and is avoided.
    const ModelObjectCutAttributes attributes = ModelObjectCutAttribute::KeepUpper
        | only_if(keep_lower,        ModelObjectCutAttribute::KeepLower)
        | only_if(keep_as_parts,     ModelObjectCutAttribute::KeepAsParts)
        | only_if(flip_upper,        ModelObjectCutAttribute::FlipUpper)
        | only_if(flip_lower,        ModelObjectCutAttribute::FlipLower)
        | only_if(place_on_cut_upper, ModelObjectCutAttribute::PlaceOnCutUpper)
        | only_if(place_on_cut_lower, ModelObjectCutAttribute::PlaceOnCutLower);

    std::set<int> object_ids_before;
    for (const ModelObject* o : model.objects)
        object_ids_before.insert(o->id().id);
    {
        // The same sequence Plater::cut_horizontal runs (Plater.cpp:18760),
        // plus the snapshot the gizmo path takes around perform_cut
        // (GLGizmoCut.cpp:3327) — the calibration-tower callers of
        // cut_horizontal rely on their own enclosing snapshot.
        GUI::Plater::TakeSnapshot snapshot(&plater, "Cut by Plane");
        wxBusyCursor wait;
        const Vec3d instance_offset = object->instances[instance_idx]->get_offset();
        Cut cut(object, instance_idx, Geometry::translation_transform(z * Vec3d::UnitZ() - instance_offset), attributes);
        const ModelObjectPtrs new_objects = cut.perform_with_plane();
        plater.apply_cut_object_to_model(static_cast<size_t>(object_idx), new_objects);
    }

    // apply_cut_object_to_model erases the original mid-vector and appends the
    // results at the tail (every index above object_idx shifts down by one),
    // so the new objects are resolved by identity — never by size difference.
    std::vector<size_t> added;
    for (size_t i = 0; i < model.objects.size(); ++i)
        if (object_ids_before.count(model.objects[i]->id().id) == 0)
            added.push_back(i);
    return added;
}

// ── Text volumes ───────────────────────────────────────────────────────────

// EmbossJob.cpp:63 — the surface offset keeps flat emboss volumes from
// z-fighting with the object they sit on.
constexpr float SAFE_SURFACE_OFFSET = 0.015f; // [in mm]
// The mesh build below is synchronous and O(len(text)); the GUI runs it on a
// worker job, this API runs it on the calling (UI) thread, so cap the input.
constexpr size_t MAX_TEXT_LENGTH = 1000;

void validate_text_params(const char* function_name, const std::string& text, double height_mm, double depth_mm)
{
    if (text.empty())
        throw py::value_error(std::string(function_name) + ": text must not be empty");
    if (text.size() > MAX_TEXT_LENGTH)
        throw py::value_error(std::string(function_name) + ": text is longer than 1000 characters");
    validate_positive_mm(function_name, "height_mm", height_mm, 10000.);
    validate_positive_mm(function_name, "depth_mm", depth_mm, 10000.);
}

// The synchronous core of the Emboss jobs (EmbossJob.cpp try_create_mesh /
// TextDataBase): glyph outlines from the font, merged, projected into a solid.
// Also fills the volume metadata that makes the result re-editable in the
// Emboss gizmo (ModelVolume::text_configuration / emboss_shape).
TriangleMesh create_text_mesh(const char* function_name, const std::string& text, const std::string& font_path,
                              double height_mm, double depth_mm, ModelVolumeType type,
                              EmbossShape& shape_out, TextConfiguration& tc_out)
{
    auto font_file = Emboss::create_font_file(font_path.c_str());
    if (!font_file)
        throw py::value_error(std::string(function_name) + ": the font file could not be loaded: " + font_path);
    Emboss::FontFileWithCache font(std::move(font_file));

    FontProp fp; // FontProp(float line_height = 10.f): the line height in mm
    fp.size_in_mm = static_cast<float>(height_mm);
    fp.per_glyph  = false;

    tc_out.style.name = boost::filesystem::path(font_path).stem().string();
    tc_out.style.path = font_path;
    tc_out.style.type = EmbossStyle::Type::file_path;
    tc_out.style.prop = fp;
    tc_out.text       = text;

    shape_out.projection.depth       = static_cast<float>(depth_mm);
    shape_out.projection.use_surface = false;
    shape_out.scale                  = Emboss::get_text_shape_scale(fp, *font.font_file);
    shape_out.shapes_with_ids        = Emboss::text2vshapes(font, boost::nowide::widen(text), fp);
    if (shape_out.shapes_with_ids.empty())
        throw py::value_error(std::string(function_name) + ": the text produced no glyphs (wrong font or unsupported characters)");
    // union_with_delta lives at Slic3r scope (Emboss.hpp:471), the delta constants in Emboss.
    const ExPolygons shapes = union_with_delta(shape_out, Emboss::UNION_DELTA, Emboss::UNION_MAX_ITERATIN);
    if (shapes.empty())
        throw py::value_error(std::string(function_name) + ": the glyph outlines could not be merged into a solid cross-section");

    // try_create_mesh (EmbossJob.cpp:926): scale the integer glyph coordinates
    // to mm, extrude by depth/scale, and shift out of / into the surface.
    const double depth = shape_out.projection.depth / shape_out.scale;
    auto         projectZ = std::make_unique<Emboss::ProjectZ>(depth);
    const bool   is_outside = (type == ModelVolumeType::MODEL_PART);
    const float  offset = is_outside ? -SAFE_SURFACE_OFFSET : (SAFE_SURFACE_OFFSET - shape_out.projection.depth);
    const Transform3d tr = Eigen::Translation<double, 3>(0., 0., static_cast<double>(offset)) * Eigen::Scaling(shape_out.scale);
    const Emboss::ProjectTransform project(std::move(projectZ), tr);
    indexed_triangle_set its = Emboss::polygons2model(shapes, project);
    if (its.empty())
        throw py::value_error(std::string(function_name) + ": the text volume mesh could not be created");
    return TriangleMesh(std::move(its));
}

std::string resolve_font_path(const char* function_name, const std::optional<std::string>& font_path)
{
    // The bundled fallback font matches what StyleManager falls back to when
    // no system font works (GLGizmoEmboss.cpp) — note the GUI's default is the
    // system font; a headless host call has no style manager, so the packaged
    // font is the deterministic choice.
    const std::string path = font_path.value_or(resources_dir() + "/fonts/HarmonyOS_Sans_SC_Regular.ttf");
    audit_plugin_read(path);
    validate_readable_file(function_name, path, "font file");
    return path;
}

size_t add_text_object(GUI::Plater& plater, const std::string& text, const std::optional<std::string>& font_path,
                       double height_mm, double depth_mm, const std::optional<std::string>& name)
{
    ensure_3d_view(plater);
    validate_text_params("add_text_object", text, height_mm, depth_mm);
    const std::string font = resolve_font_path("add_text_object", font_path);
    EmbossShape shape;
    TextConfiguration tc;
    TriangleMesh mesh = create_text_mesh("add_text_object", text, font, height_mm, depth_mm,
                                         ModelVolumeType::MODEL_PART, shape, tc);

    GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list();
    if (obj_list == nullptr)
        throw std::runtime_error("add_text_object: the object list is not ready yet");
    // CreateObjectJob::finalize (EmbossJob.cpp:341) model section; placement
    // follows load_mesh_object (a free bed cell) instead of the screen ray the
    // job uses, so the object lands deterministically. The gizmo the job opens
    // at the end is not opened here.
    plater.take_snapshot("Add Emboss text object");
    const BoundingBoxf3 bb = mesh.bounding_box();
    Model& model = plater.model();
    ModelObject* new_object = model.add_object();
    new_object->name = name.value_or(single_line(text));
    new_object->add_instance();
    ModelVolume* new_volume = new_object->add_volume(std::move(mesh));
    new_volume->config.set_key_value("extruder", new ConfigOptionInt(0));
    new_volume->text_configuration = tc;
    new_volume->emboss_shape       = std::move(shape);

    new_object->invalidate_bounding_box();
    new_object->translate(-bb.center());
    const Vec2d bed_center = plater.build_volume().bounding_volume2d().center();
    Vec2d cell = bed_center;
    if (GUI::GLCanvas3D* canvas = plater.get_view3D_canvas3D()) {
        const Vec2f free_cell = canvas->get_nearest_empty_cell({static_cast<float>(bed_center.x()), static_cast<float>(bed_center.y())});
        cell = Vec2d(free_cell.x(), free_cell.y());
    }
    new_object->instances[0]->set_offset(to_3d(cell, -new_object->origin_translation.z()));
    new_object->ensure_on_bed();
    model.InitializeAssemblyPositions({new_object});
    obj_list->paste_objects_into_list({model.objects.size() - 1});
    return model.objects.size() - 1;
}

size_t add_text_volume(GUI::Plater& plater, const std::string& text, int object_idx,
                       const std::optional<std::string>& font_path, double height_mm, double depth_mm,
                       ModelVolumeType type, const std::optional<std::string>& name)
{
    ensure_3d_view(plater);
    // The emboss gizmo accepts exactly these three (GLGizmoEmboss::init_create).
    if (type != ModelVolumeType::MODEL_PART && type != ModelVolumeType::NEGATIVE_VOLUME && type != ModelVolumeType::PARAMETER_MODIFIER)
        throw py::value_error("add_text_volume: volume_type must be ModelPart, NegativeVolume or ParameterModifier");
    validate_text_params("add_text_volume", text, height_mm, depth_mm);

    Model& model = plater.model();
    if (object_idx < 0 || object_idx >= static_cast<int>(model.objects.size()))
        throw py::value_error("object index out of range");
    ModelObject* model_object = model.objects[object_idx];
    if (model_object->instances.empty())
        throw std::runtime_error("add_text_volume: the object has no instances");

    const std::string font = resolve_font_path("add_text_volume", font_path);
    EmbossShape shape;
    TextConfiguration tc;
    TriangleMesh mesh = create_text_mesh("add_text_volume", text, font, height_mm, depth_mm, type, shape, tc);

    // The create_volume helper of the Emboss jobs (EmbossJob.cpp:1060): add a
    // placeholder cube (add_volume centers the mesh), then swap in the real
    // mesh, then transform under the front of the instance. The gizmo opening
    // and selection grab at the end are skipped.
    plater.take_snapshot("Add Emboss text Volume");
    const BoundingBoxf3 instance_bb = model_object->instance_bounding_box(0);
    ModelVolume* volume = model_object->add_volume(make_cube(1., 1., 1.), type);
    volume->set_mesh(std::move(mesh));
    volume->calculate_convex_hull();
    volume->config.set_key_value("extruder", new ConfigOptionInt(0));
    volume->source.is_from_builtin_objects = true;
    volume->name = name.value_or(single_line(text));

    const Vec3d volume_size = volume->mesh().bounding_box().size();
    const Vec3d offset_tr(0., // centered with the instance in X
                          -instance_bb.size().y() / 2 - volume_size.y() / 2, // in front of the object
                          volume_size.z() / 2 - instance_bb.size().z() / 2); // laid on the bed
    const Transform3d tr = model_object->instances.front()->get_transformation().get_matrix_no_offset().inverse();
    volume->set_transformation(tr * Eigen::Translation3d(offset_tr));

    volume->text_configuration = tc;
    volume->emboss_shape       = std::move(shape);

    if (type == ModelVolumeType::MODEL_PART) {
        model_object->ensure_on_bed();
        if (GUI::GLCanvas3D* canvas = plater.get_view3D_canvas3D())
            canvas->update_instance_printable_state_for_object(static_cast<size_t>(object_idx));
    }

    GUI::ObjectList* obj_list = GUI::wxGetApp().obj_list();
    if (obj_list == nullptr)
        throw std::runtime_error("add_text_volume: the object list is not ready yet");
    obj_list->select_item([&obj_list, object_idx, volume]() {
        wxDataViewItemArray items = obj_list->reorder_volumes_and_get_selection(object_idx,
            [volume](const ModelVolume* v) { return v == volume; });
        return items.IsEmpty() ? wxDataViewItem() : items.front();
    });
    obj_list->selection_changed();
    plater.update();

    for (size_t i = 0; i < model_object->volumes.size(); ++i)
        if (model_object->volumes[i] == volume)
            return i;
    throw std::runtime_error("add_text_volume: the added volume could not be resolved");
}

// ── SVG object ─────────────────────────────────────────────────────────────

void queue_add_svg_object(GUI::Plater& plater, const std::string& svg_path)
{
    ensure_3d_view(plater);
    if (svg_path.empty())
        throw py::value_error("add_svg_object: svg_path must not be empty");
    if (!boost::iends_with(svg_path, ".svg"))
        throw py::value_error("add_svg_object: the file name must end in .svg");
    audit_plugin_read(svg_path);
    validate_readable_file("add_svg_object", svg_path, "SVG file");

    // Pre-parse with the same loader the gizmo uses (init_image → nsvgParse),
    // so a bad file fails here instead of inside the job, whose error path is
    // a modal message box (GLGizmoSVG.cpp:2218-2239).
    EmbossShape::SvgFile probe;
    probe.path = svg_path;
    if (init_image(probe) == nullptr)
        throw py::value_error("add_svg_object: the SVG file could not be parsed: " + svg_path);
    if (get_shapes_count(*probe.image) == 0)
        throw py::value_error("add_svg_object: the SVG file does not contain a single path to be embossed");

    // An empty selection forces start_create_volume_without_position into its
    // create-new-object branch (EmbossJob.cpp:601), which always builds a
    // MODEL_PART volume — the only form this method exposes.
    plater.deselect_all();
    GUI::GLCanvas3D* canvas = plater.get_view3D_canvas3D();
    if (canvas == nullptr)
        throw std::runtime_error("add_svg_object: the 3D view is not ready yet");
    GUI::GLGizmoBase* gizmo_base = canvas->get_gizmos_manager().get_gizmo(GUI::GLGizmosManager::Svg);
    if (gizmo_base == nullptr)
        throw std::runtime_error("add_svg_object: the SVG tool is not present in the gizmo manager");
    auto* svg_gizmo = dynamic_cast<GUI::GLGizmoSVG*>(gizmo_base);
    if (svg_gizmo == nullptr)
        throw std::runtime_error("add_svg_object: the gizmo at the Svg slot is not GLGizmoSVG");
    if (!svg_gizmo->create_volume(svg_path, ModelVolumeType::MODEL_PART))
        throw std::runtime_error("add_svg_object: the SVG creation job could not be queued");
}

} // namespace

void host_bindings::register_modeling_methods(pybind11::class_<GUI::Plater, std::unique_ptr<GUI::Plater, pybind11::nodelete>>& plater)
{
    // ── Modeling (fork addition). Synchronous model-graph mutations that end
    //    in the same snapshot/refresh chain the matching GUI menu path runs,
    //    so undo, the object list and other plugins' lifecycle hooks see a
    //    plugin edit exactly like a user edit. All UI thread only.
    plater
        .def("get_primitive_shapes", [](GUI::Plater&) -> py::list {
            py::list shapes;
            for (const std::string& shape : primitive_shape_names())
                shapes.append(py::str(shape));
            return shapes;
        },
           "The shape names add_primitive()/add_primitive_volume() accept: "
           "cube, cylinder, sphere, slab, cone, disc, torus.")
        .def("add_primitive", [](GUI::Plater& p, const std::string& shape, std::optional<double> size, std::optional<std::string> name) {
            require_main_thread("add_primitive");
            if (!is_known_primitive_shape(shape))
                throw py::value_error("add_primitive: unknown shape \"" + shape + "\" (see get_primitive_shapes())");
            if (name && name->empty())
                throw py::value_error("add_primitive: name must not be empty");
            return add_primitive_object(p, shape, size.has_value(), size.value_or(0.), name);
        }, py::arg("shape"), py::arg("size") = py::none(), py::arg("name") = py::none(),
           "Add a primitive (cube/cylinder/sphere/cone/disc/torus) as a new standalone object "
           "(the Add Primitive menu path). size is the shape's side in mm; without it the shape "
           "is 10% of the larger bed side like the GUI default. \"slab\" has no standalone form "
           "(it is sized from an existing object) — use add_primitive_volume() for it. Returns "
           "the new object's index (it selects the new object). UI thread only.")
        .def("add_primitive_volume", [](GUI::Plater& p, const std::string& shape, int object_idx, int instance_idx,
                                        ModelVolumeType volume_type, std::optional<double> size, std::optional<std::string> name) {
            require_main_thread("add_primitive_volume");
            if (!is_known_primitive_shape(shape))
                throw py::value_error("add_primitive_volume: unknown shape \"" + shape + "\" (see get_primitive_shapes())");
            if (name && name->empty())
                throw py::value_error("add_primitive_volume: name must not be empty");
            return add_primitive_volume(p, shape, object_idx, instance_idx, volume_type, size.has_value(), size.value_or(0.), name);
        }, py::arg("shape"), py::arg("object_idx"), py::arg("instance_idx") = 0,
           py::arg("volume_type") = ModelVolumeType::PARAMETER_MODIFIER,
           py::arg("size") = py::none(), py::arg("name") = py::none(),
           "Add a primitive as a volume of an existing object — a part, negative volume, modifier "
           "or support blocker/enforcer (the Add > primitive submenu path, placed at the front "
           "left corner of the target instance and lifted to the bed). \"slab\" takes its size "
           "from that instance's bounding box, so size is rejected for it. Returns the new "
           "volume's index. UI thread only.")
        .def("cut_horizontal", [](GUI::Plater& p, int object_idx, double z, int instance_idx, bool keep_upper, bool keep_lower,
                                  bool keep_as_parts, bool flip_upper, bool flip_lower, bool place_on_cut_upper, bool place_on_cut_lower) {
            require_main_thread("cut_horizontal");
            return cut_plane(p, object_idx, instance_idx, z, keep_upper, keep_lower, keep_as_parts,
                             flip_upper, flip_lower, place_on_cut_upper, place_on_cut_lower);
        }, py::arg("object_idx"), py::arg("z"), py::arg("instance_idx") = 0,
           py::arg("keep_upper") = true, py::arg("keep_lower") = true, py::arg("keep_as_parts") = false,
           py::arg("flip_upper") = false, py::arg("flip_lower") = false,
           py::arg("place_on_cut_upper") = false, py::arg("place_on_cut_lower") = false,
           "Cut one object with a horizontal plane at world (bed) height z — Plater::cut_horizontal, "
           "the programmatic cut the calibration towers use, with the gizmo cut's attribute flags. "
           "The original object is REMOVED and the kept sides are appended as new objects: every "
           "object index above object_idx shifts down by one, and previously returned object "
           "references are invalidated. Returns the indices of the newly appended objects "
           "(empty is impossible: z is validated inside the instance's bounding box). Geometric "
           "cut only — connectors/dowels and cut-info editing need the gizmo. UI thread only.")
        .def("add_text_object", [](GUI::Plater& p, const std::string& text, std::optional<std::string> font_path,
                                   double height_mm, double depth_mm, std::optional<std::string> name) {
            require_main_thread("add_text_object");
            if (name && name->empty())
                throw py::value_error("add_text_object: name must not be empty");
            return add_text_object(p, text, font_path, height_mm, depth_mm, name);
        }, py::arg("text"), py::arg("font_path") = py::none(), py::arg("height_mm") = 10.0, py::arg("depth_mm") = 1.0,
           py::arg("name") = py::none(),
           "Create an embossed text object (the Add Text menu path, built synchronously instead of "
           "through the edit gizmo; the result stays re-editable in the Emboss gizmo). text is "
           "limited to 1000 characters (the mesh build is O(len)). font_path defaults to the "
           "bundled HarmonyOS Sans SC; a custom path must be a readable .ttf/.ttc (audit-checked "
           "like a plugin file read). height_mm is the line height, depth_mm the extrusion depth "
           "(upstream defaults). Returns the new object's index. UI thread only.")
        .def("add_text_volume", [](GUI::Plater& p, const std::string& text, int object_idx, std::optional<std::string> font_path,
                                   double height_mm, double depth_mm, ModelVolumeType volume_type, std::optional<std::string> name) {
            require_main_thread("add_text_volume");
            if (name && name->empty())
                throw py::value_error("add_text_volume: name must not be empty");
            return add_text_volume(p, text, object_idx, font_path, height_mm, depth_mm, volume_type, name);
        }, py::arg("text"), py::arg("object_idx"), py::arg("font_path") = py::none(),
           py::arg("height_mm") = 10.0, py::arg("depth_mm") = 1.0,
           py::arg("volume_type") = ModelVolumeType::MODEL_PART, py::arg("name") = py::none(),
           "Add an embossed text volume to an existing object — a part, negative volume or "
           "modifier placed in front of the object's first instance and laid on the bed. Same "
           "font/text rules as add_text_object(); the volume stays re-editable in the Emboss "
           "gizmo. Returns the new volume's index. UI thread only.")
        .def("add_svg_object", [](GUI::Plater& p, const std::string& svg_path) {
            require_main_thread("add_svg_object");
            queue_add_svg_object(p, svg_path);
        }, py::arg("svg_path"),
           "Create an SVG emboss object from a path file (the Add SVG menu path with the file "
           "chosen up front). The path is audit-checked like a plugin file read and pre-parsed, "
           "so bad files raise instead of popping a dialog. Unlike the other modeling methods "
           "this queues a background job: it returns immediately, the object appears when the "
           "job finishes and the SVG gizmo opens on it (poll the scene/model). Always creates a "
           "standalone part object. UI thread only.");
}

} // namespace Slic3r
