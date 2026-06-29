#include "slic3r/GUI/VoxelEditor/VoxelEditorPanel.hpp"
#include "slic3r/GUI/VoxelEditor/VoxelEditorCanvas.hpp"
#include "libslic3r/VoxelEditor/Octree.hpp"
#include "libslic3r/VoxelEditor/VoxelGrid.hpp"
#include "libslic3r/VoxelEditor/VoxelOperations.hpp"
#include "libslic3r/VoxelEditor/VoxelSlicer.hpp"
#include "libslic3r/VoxelEditor/MeshVoxelizer.hpp"
#include "libslic3r/TriangleMesh.hpp"
#include "libslic3r/Format/STL.hpp"

#include <wx/button.h>
#include <wx/stattext.h>
#include <wx/slider.h>
#include <wx/textctrl.h>
#include <wx/sizer.h>
#include <wx/msgdlg.h>
#include <wx/filedlg.h>
#include <wx/textdlg.h>

#include <fstream>
#include <sstream>

namespace Slic3r {
namespace GUI {

// ---------- helpers ----------

static std::string prompt_string(wxWindow* parent, const std::string& title, const std::string& default_val)
{
    wxTextEntryDialog dlg(parent, title, title, default_val);
    if (dlg.ShowModal() == wxID_OK)
        return dlg.GetValue().ToStdString();
    return "";
}

static double prompt_double(wxWindow* parent, const std::string& title, double default_val)
{
    auto s = prompt_string(parent, title, std::to_string(default_val));
    if (s.empty()) return -1;
    try { return std::stod(s); } catch (...) { return -1; }
}

static int prompt_int(wxWindow* parent, const std::string& title, int default_val)
{
    auto s = prompt_string(parent, title, std::to_string(default_val));
    if (s.empty()) return -1;
    try { return std::stoi(s); } catch (...) { return -1; }
}

// ---------- event table ----------

wxBEGIN_EVENT_TABLE(VoxelEditorPanel, wxPanel)
wxEND_EVENT_TABLE()

VoxelEditorPanel::VoxelEditorPanel(wxWindow* parent)
    : wxPanel(parent, wxID_ANY, wxDefaultPosition, wxSize(900, 700))
{
    auto* main_sizer = new wxBoxSizer(wxVERTICAL);

    // ===== Toolbar Row 1: High-level ops =====
    auto* t1 = new wxBoxSizer(wxHORIZONTAL);

    auto* lbl_templates = new wxStaticText(this, wxID_ANY, "Templates:");
    t1->Add(lbl_templates, 0, wxALL | wxALIGN_CENTER_VERTICAL, 3);

    auto* btn_cube     = new wxButton(this, wxID_ANY, "Cube",     wxDefaultPosition, wxSize(55,28));
    auto* btn_sphere   = new wxButton(this, wxID_ANY, "Sphere",   wxDefaultPosition, wxSize(55,28));
    auto* btn_cylinder = new wxButton(this, wxID_ANY, "Cylinder", wxDefaultPosition, wxSize(60,28));
    auto* btn_torus    = new wxButton(this, wxID_ANY, "Torus",    wxDefaultPosition, wxSize(50,28));
    t1->Add(btn_cube,     0, wxALL, 2);
    t1->Add(btn_sphere,   0, wxALL, 2);
    t1->Add(btn_cylinder, 0, wxALL, 2);
    t1->Add(btn_torus,    0, wxALL, 2);

    t1->AddSpacer(12);
    auto* lbl_bool = new wxStaticText(this, wxID_ANY, "Boolean:");
    t1->Add(lbl_bool, 0, wxALL | wxALIGN_CENTER_VERTICAL, 3);

    auto* btn_union     = new wxButton(this, wxID_ANY, "Union",    wxDefaultPosition, wxSize(50,28));
    auto* btn_subtract  = new wxButton(this, wxID_ANY, "Subtract", wxDefaultPosition, wxSize(60,28));
    auto* btn_intersect = new wxButton(this, wxID_ANY, "Intersect",wxDefaultPosition, wxSize(60,28));
    auto* btn_clipboard = new wxButton(this, wxID_ANY, "Copy",     wxDefaultPosition, wxSize(45,28));
    t1->Add(btn_union,     0, wxALL, 2);
    t1->Add(btn_subtract,  0, wxALL, 2);
    t1->Add(btn_intersect, 0, wxALL, 2);
    t1->Add(btn_clipboard, 0, wxALL, 2);

    t1->AddSpacer(12);
    auto* lbl_mod = new wxStaticText(this, wxID_ANY, "Modify:");
    t1->Add(lbl_mod, 0, wxALL | wxALIGN_CENTER_VERTICAL, 3);

    auto* btn_hollow = new wxButton(this, wxID_ANY, "Hollow", wxDefaultPosition, wxSize(55,28));
    auto* btn_smooth = new wxButton(this, wxID_ANY, "Smooth", wxDefaultPosition, wxSize(55,28));
    auto* btn_arr_lin = new wxButton(this, wxID_ANY, "ArrayLin", wxDefaultPosition, wxSize(60,28));
    auto* btn_arr_grid= new wxButton(this, wxID_ANY, "ArrayGrid",wxDefaultPosition, wxSize(65,28));
    t1->Add(btn_hollow,   0, wxALL, 2);
    t1->Add(btn_smooth,   0, wxALL, 2);
    t1->Add(btn_arr_lin,  0, wxALL, 2);
    t1->Add(btn_arr_grid, 0, wxALL, 2);

    main_sizer->Add(t1, 0, wxEXPAND | wxALL, 2);

    // ===== Toolbar Row 2: Mid-level + utility =====
    auto* t2 = new wxBoxSizer(wxHORIZONTAL);

    auto* lbl_edit = new wxStaticText(this, wxID_ANY, "Edit:");
    t2->Add(lbl_edit, 0, wxALL | wxALIGN_CENTER_VERTICAL, 3);

    auto* btn_place  = new wxButton(this, wxID_ANY, "Place",  wxDefaultPosition, wxSize(50,28));
    auto* btn_remove = new wxButton(this, wxID_ANY, "Remove", wxDefaultPosition, wxSize(55,28));
    auto* btn_brush  = new wxButton(this, wxID_ANY, "Brush",  wxDefaultPosition, wxSize(50,28));
    t2->Add(btn_place,  0, wxALL, 2);
    t2->Add(btn_remove, 0, wxALL, 2);
    t2->Add(btn_brush,  0, wxALL, 2);

    // Brush size slider.
    t2->AddSpacer(8);
    m_brush_size_label = new wxStaticText(this, wxID_ANY, "Size:2");
    t2->Add(m_brush_size_label, 0, wxALL | wxALIGN_CENTER_VERTICAL, 3);
    m_brush_size_slider = new wxSlider(this, wxID_ANY, 2, 1, 20,
        wxDefaultPosition, wxSize(100, 28), wxSL_HORIZONTAL | wxSL_LABELS);
    t2->Add(m_brush_size_slider, 0, wxALL, 2);

    t2->AddSpacer(12);
    auto* btn_undo = new wxButton(this, wxID_ANY, "Undo", wxDefaultPosition, wxSize(45,28));
    auto* btn_redo = new wxButton(this, wxID_ANY, "Redo", wxDefaultPosition, wxSize(45,28));
    t2->Add(btn_undo, 0, wxALL, 2);
    t2->Add(btn_redo, 0, wxALL, 2);

    t2->AddSpacer(12);
    auto* btn_import = new wxButton(this, wxID_ANY, "Import STL", wxDefaultPosition, wxSize(75,28));
    auto* btn_slice  = new wxButton(this, wxID_ANY, "Slice",      wxDefaultPosition, wxSize(50,28));
    auto* btn_export = new wxButton(this, wxID_ANY, "Export GCode",wxDefaultPosition, wxSize(85,28));
    t2->Add(btn_import, 0, wxALL, 2);
    t2->Add(btn_slice,  0, wxALL, 2);
    t2->Add(btn_export, 0, wxALL, 2);

    t2->AddStretchSpacer();
    auto* btn_reset = new wxButton(this, wxID_ANY, "Reset View", wxDefaultPosition, wxSize(75,28));
    t2->Add(btn_reset, 0, wxALL, 2);

    main_sizer->Add(t2, 0, wxEXPAND | wxALL, 2);

    // ===== Status bar =====
    auto* status_bar = new wxBoxSizer(wxHORIZONTAL);
    m_status = new wxStaticText(this, wxID_ANY, "Tool: None");
    m_node_count = new wxStaticText(this, wxID_ANY, "Nodes: 0");
    status_bar->Add(m_status, 0, wxALL | wxALIGN_CENTER_VERTICAL, 4);
    status_bar->AddStretchSpacer();
    status_bar->Add(m_node_count, 0, wxALL | wxALIGN_CENTER_VERTICAL, 4);
    main_sizer->Add(status_bar, 0, wxEXPAND);

    // ===== 3D Canvas =====
    m_canvas = new VoxelEditorCanvas(this, nullptr);
    main_sizer->Add(m_canvas, 1, wxEXPAND);

    SetSizer(main_sizer);

    // ---- Bind events ----
    btn_cube->Bind(wxEVT_BUTTON,     &VoxelEditorPanel::on_template_cube,     this);
    btn_sphere->Bind(wxEVT_BUTTON,   &VoxelEditorPanel::on_template_sphere,   this);
    btn_cylinder->Bind(wxEVT_BUTTON, &VoxelEditorPanel::on_template_cylinder, this);
    btn_torus->Bind(wxEVT_BUTTON,    &VoxelEditorPanel::on_template_torus,    this);
    btn_union->Bind(wxEVT_BUTTON,    &VoxelEditorPanel::on_boolean_union,     this);
    btn_subtract->Bind(wxEVT_BUTTON, &VoxelEditorPanel::on_boolean_subtract,  this);
    btn_intersect->Bind(wxEVT_BUTTON,&VoxelEditorPanel::on_boolean_intersect, this);
    btn_clipboard->Bind(wxEVT_BUTTON,[this](wxCommandEvent&){ m_clipboard = m_octree; update_status_text(); });
    btn_hollow->Bind(wxEVT_BUTTON,   &VoxelEditorPanel::on_hollow,    this);
    btn_smooth->Bind(wxEVT_BUTTON,   &VoxelEditorPanel::on_smooth,    this);
    btn_arr_lin->Bind(wxEVT_BUTTON,  &VoxelEditorPanel::on_array_linear, this);
    btn_arr_grid->Bind(wxEVT_BUTTON, &VoxelEditorPanel::on_array_grid,  this);
    btn_place->Bind(wxEVT_BUTTON,    &VoxelEditorPanel::on_place_tool,  this);
    btn_remove->Bind(wxEVT_BUTTON,   &VoxelEditorPanel::on_remove_tool, this);
    btn_brush->Bind(wxEVT_BUTTON,    &VoxelEditorPanel::on_brush_tool,  this);
    btn_undo->Bind(wxEVT_BUTTON,     &VoxelEditorPanel::on_undo,   this);
    btn_redo->Bind(wxEVT_BUTTON,     &VoxelEditorPanel::on_redo,   this);
    btn_reset->Bind(wxEVT_BUTTON,    &VoxelEditorPanel::on_reset_view, this);
    btn_import->Bind(wxEVT_BUTTON,   &VoxelEditorPanel::on_import_stl, this);
    btn_slice->Bind(wxEVT_BUTTON,    &VoxelEditorPanel::on_slice_gcode, this);
    btn_export->Bind(wxEVT_BUTTON,   &VoxelEditorPanel::on_export_gcode, this);
    m_brush_size_slider->Bind(wxEVT_SLIDER, &VoxelEditorPanel::on_brush_size_changed, this);

    m_canvas->set_edit_callback([this](double x, double y, double z, bool place) {
        on_edit(x, y, z, place);
    });
}

VoxelEditorPanel::~VoxelEditorPanel() = default;

// ===== Load / Undo =====

void VoxelEditorPanel::load_octree(std::shared_ptr<Octree> octree)
{
    m_octree = std::move(octree);
    m_canvas->set_octree(m_octree);
    m_undo_stack.clear();
    m_redo_stack.clear();
    m_last_gcode.clear();
    update_status_text();
}

void VoxelEditorPanel::push_undo()
{
    if (!m_octree) return;
    m_redo_stack.clear();
    Snapshot snap;
    snap.grid = std::make_unique<VoxelGrid>(m_octree->to_grid(1.0f));
    snap.label = "edit";
    m_undo_stack.push_back(std::move(snap));
    if (m_undo_stack.size() > MAX_UNDO)
        m_undo_stack.pop_front();
}

void VoxelEditorPanel::on_undo(wxCommandEvent&)
{
    if (!m_octree || m_undo_stack.empty()) return;
    Snapshot snap;
    snap.grid = std::make_unique<VoxelGrid>(m_octree->to_grid(1.0f));
    snap.label = "redo";
    m_redo_stack.push_back(std::move(snap));
    if (m_redo_stack.size() > MAX_UNDO)
        m_redo_stack.pop_front();

    auto state = std::move(m_undo_stack.back());
    m_undo_stack.pop_back();
    m_octree = std::make_shared<Octree>(Octree::from_grid(*state.grid));
    m_canvas->set_octree(m_octree);
    update_status_text();
}

void VoxelEditorPanel::on_redo(wxCommandEvent&)
{
    if (!m_octree || m_redo_stack.empty()) return;
    Snapshot snap;
    snap.grid = std::make_unique<VoxelGrid>(m_octree->to_grid(1.0f));
    snap.label = "undo";
    m_undo_stack.push_back(std::move(snap));

    auto state = std::move(m_redo_stack.back());
    m_redo_stack.pop_back();
    m_octree = std::make_shared<Octree>(Octree::from_grid(*state.grid));
    m_canvas->set_octree(m_octree);
    update_status_text();
}

// ===== Templates =====

void VoxelEditorPanel::on_template_cube(wxCommandEvent&)
{
    double s = prompt_double(this, "Cube size (mm)", 20.0);
    if (s <= 0) return;
    push_undo();
    BoundingBoxf3 bb({0,0,0}, {s,s,s});
    *m_octree = VoxelOps::make_box(bb, 1.0f);
    m_canvas->set_octree(m_octree);
    m_canvas->reset_camera();
    update_status_text();
}

void VoxelEditorPanel::on_template_sphere(wxCommandEvent&)
{
    double s = prompt_double(this, "Sphere diameter (mm)", 20.0);
    if (s <= 0) return;
    push_undo();
    BoundingBoxf3 bb({0,0,0}, {s,s,s});
    *m_octree = VoxelOps::make_sphere(bb, 1.0f);
    m_canvas->set_octree(m_octree);
    m_canvas->reset_camera();
    update_status_text();
}

void VoxelEditorPanel::on_template_cylinder(wxCommandEvent&)
{
    double d = prompt_double(this, "Cylinder diameter (mm)", 20.0);
    if (d <= 0) return;
    double h = prompt_double(this, "Cylinder height (mm)", 30.0);
    if (h <= 0) return;
    push_undo();
    BoundingBoxf3 bb({0,0,0}, {d,d,h});
    *m_octree = VoxelOps::make_cylinder(bb, 1.0f);
    m_canvas->set_octree(m_octree);
    m_canvas->reset_camera();
    update_status_text();
}

void VoxelEditorPanel::on_template_torus(wxCommandEvent&)
{
    double d = prompt_double(this, "Torus major diameter (mm)", 30.0);
    if (d <= 0) return;
    double t = prompt_double(this, "Tube thickness (mm)", 5.0);
    if (t <= 0) return;
    push_undo();
    BoundingBoxf3 bb({0,0,0}, {d,d,d*0.5});
    *m_octree = VoxelOps::make_torus(bb, 1.0f, t);
    m_canvas->set_octree(m_octree);
    m_canvas->reset_camera();
    update_status_text();
}

// ===== Boolean operations =====

Octree VoxelEditorPanel::clipboard_or_empty() const
{
    if (m_clipboard) return *m_clipboard;
    // Return an empty octree with the same world bbox.
    Octree empty;
    if (m_octree) empty.set_world_bbox(m_octree->world_bbox());
    return empty;
}

void VoxelEditorPanel::on_boolean_union(wxCommandEvent&)
{
    if (!m_octree) return;
    push_undo();
    *m_octree = VoxelOps::boolean_union(*m_octree, clipboard_or_empty(), 1.0f);
    m_canvas->set_octree(m_octree);
    update_status_text();
}

void VoxelEditorPanel::on_boolean_subtract(wxCommandEvent&)
{
    if (!m_octree) return;
    push_undo();
    *m_octree = VoxelOps::boolean_subtract(*m_octree, clipboard_or_empty(), 1.0f);
    m_canvas->set_octree(m_octree);
    update_status_text();
}

void VoxelEditorPanel::on_boolean_intersect(wxCommandEvent&)
{
    if (!m_octree) return;
    push_undo();
    *m_octree = VoxelOps::boolean_intersect(*m_octree, clipboard_or_empty(), 1.0f);
    m_canvas->set_octree(m_octree);
    update_status_text();
}

// ===== Modify operations =====

void VoxelEditorPanel::on_hollow(wxCommandEvent&)
{
    if (!m_octree) return;
    double wall = prompt_double(this, "Wall thickness (mm)", 2.0);
    if (wall <= 0) return;
    push_undo();
    *m_octree = VoxelOps::hollow(*m_octree, static_cast<float>(wall), 1.0f);
    m_canvas->set_octree(m_octree);
    update_status_text();
}

void VoxelEditorPanel::on_smooth(wxCommandEvent&)
{
    if (!m_octree) return;
    int iter = prompt_int(this, "Smooth iterations", 1);
    if (iter <= 0) return;
    push_undo();
    *m_octree = VoxelOps::smooth(*m_octree, iter, 1.0f);
    m_canvas->set_octree(m_octree);
    update_status_text();
}

void VoxelEditorPanel::on_array_linear(wxCommandEvent&)
{
    if (!m_octree) return;
    int count = prompt_int(this, "Number of copies", 3);
    if (count <= 1) return;
    double spacing = prompt_double(this, "Spacing (mm)", 25.0);
    if (spacing <= 0) return;
    push_undo();
    *m_octree = VoxelOps::linear_array(*m_octree, Vec3d(1,0,0), count, static_cast<float>(spacing), 1.0f);
    m_canvas->set_octree(m_octree);
    m_canvas->reset_camera();
    update_status_text();
}

void VoxelEditorPanel::on_array_grid(wxCommandEvent&)
{
    if (!m_octree) return;
    int nx = prompt_int(this, "Count X", 3);
    if (nx <= 1) return;
    int ny = prompt_int(this, "Count Y", 3);
    if (ny <= 1) return;
    double sx = prompt_double(this, "Spacing X (mm)", 25.0);
    double sy = prompt_double(this, "Spacing Y (mm)", 25.0);
    if (sx <= 0 || sy <= 0) return;
    push_undo();
    *m_octree = VoxelOps::grid_array(*m_octree, nx, ny, static_cast<float>(sx), static_cast<float>(sy), 1.0f);
    m_canvas->set_octree(m_octree);
    m_canvas->reset_camera();
    update_status_text();
}

// ===== Edit tools =====

void VoxelEditorPanel::on_place_tool(wxCommandEvent&)  { m_canvas->set_tool(VoxelEditorCanvas::Tool::Place);  update_status_text(); }
void VoxelEditorPanel::on_remove_tool(wxCommandEvent&) { m_canvas->set_tool(VoxelEditorCanvas::Tool::Remove); update_status_text(); }
void VoxelEditorPanel::on_brush_tool(wxCommandEvent&)  { m_canvas->set_tool(VoxelEditorCanvas::Tool::Brush);  update_status_text(); }

void VoxelEditorPanel::on_brush_size_changed(wxCommandEvent&)
{
    int size = m_brush_size_slider->GetValue();
    float vs = static_cast<float>(size);
    m_canvas->set_brush_size(vs);
    m_brush_size_label->SetLabel(wxString::Format("Size:%d", size));
}

void VoxelEditorPanel::on_reset_view(wxCommandEvent&) { m_canvas->reset_camera(); }

// ===== Canvas edit =====

void VoxelEditorPanel::on_edit(double wx, double wy, double wz, bool place)
{
    if (!m_octree) return;
    push_undo();

    float vs = static_cast<float>(m_brush_size_slider->GetValue());
    float half = vs * 0.5f;
    BoundingBoxf3 region(
        {wx - half, wy - half, wz - half},
        {wx + half, wy + half, wz + half}
    );

    if (m_canvas->tool() == VoxelEditorCanvas::Tool::Brush) {
        // Brush: sphere region
        VoxelOps::brush_sphere(*m_octree, Vec3d(wx, wy, wz), half, place ? 1.0f : 0.0f);
    } else {
        VoxelValue val = place ? 1.0f : 0.0f;
        m_octree->fill_region(region, val);
    }
    m_canvas->set_octree(m_octree);
    update_status_text();
}

// ===== Import / Slice / Export =====

void VoxelEditorPanel::on_import_stl(wxCommandEvent&)
{
    wxFileDialog dlg(this, "Open STL file", "", "",
        "STL files (*.stl)|*.stl|All files (*.*)|*.*",
        wxFD_OPEN | wxFD_FILE_MUST_EXIST);
    if (dlg.ShowModal() != wxID_OK) return;

    std::string path = dlg.GetPath().ToStdString();
    TriangleMesh mesh;
    if (!mesh.ReadSTLFile(path.c_str())) {
        wxMessageBox("Failed to load STL file.", "Error", wxOK | wxICON_ERROR);
        return;
    }

    MeshVoxelizer::Config vcfg;
    vcfg.voxel_size_mm = 1.0f;
    vcfg.fill_interior = true;
    MeshVoxelizer voxelizer(vcfg);
    auto grid = voxelizer.voxelize(mesh);

    load_octree(std::make_shared<Octree>(Octree::from_grid(grid)));
}

void VoxelEditorPanel::on_slice_gcode(wxCommandEvent&)
{
    if (!m_octree) {
        wxMessageBox("No model to slice.", "Info", wxOK | wxICON_INFORMATION);
        return;
    }
    VoxelSlicerConfig cfg;
    cfg.layer_height_mm = 0.2;
    cfg.nozzle_diameter  = 0.4;
    cfg.wall_loops       = 2;
    cfg.fill_density     = 0.15f;
    VoxelSlicer slicer(cfg);
    m_last_gcode = slicer.slice_to_gcode(*m_octree, 1.0f);

    std::ostringstream msg;
    msg << "G-code generated.\n";
    int lines = 0;
    for (char c : m_last_gcode) if (c == '\n') ++lines;
    msg << lines << " lines total.\n\n";
    msg << "Click 'Export GCode' to save.";

    wxMessageBox(msg.str(), "Slice Complete", wxOK | wxICON_INFORMATION);
}

void VoxelEditorPanel::on_export_gcode(wxCommandEvent&)
{
    if (m_last_gcode.empty()) {
        wxMessageBox("Slice first before exporting.", "Info", wxOK | wxICON_INFORMATION);
        return;
    }
    wxFileDialog dlg(this, "Save G-code", "", "model.gcode",
        "G-code files (*.gcode)|*.gcode|All files (*.*)|*.*",
        wxFD_SAVE | wxFD_OVERWRITE_PROMPT);
    if (dlg.ShowModal() != wxID_OK) return;

    std::ofstream out(dlg.GetPath().ToStdString());
    if (!out) {
        wxMessageBox("Failed to write file.", "Error", wxOK | wxICON_ERROR);
        return;
    }
    out << m_last_gcode;
    out.close();
    wxMessageBox("G-code exported.", "Done", wxOK | wxICON_INFORMATION);
}

// ===== Helpers =====

void VoxelEditorPanel::update_status_text()
{
    const char* tool_names[] = {"None", "Place", "Remove", "Brush"};
    int t = static_cast<int>(m_canvas->tool());
    m_status->SetLabel(wxString::Format("Tool: %s | Brush: %dmm",
        tool_names[t], m_brush_size_slider->GetValue()));

    if (m_octree)
        m_node_count->SetLabel(wxString::Format("Nodes: %zu | Undo: %zu | Redo: %zu",
            m_octree->node_count(), m_undo_stack.size(), m_redo_stack.size()));
    else
        m_node_count->SetLabel("Nodes: 0");
}

} // namespace GUI
} // namespace Slic3r
