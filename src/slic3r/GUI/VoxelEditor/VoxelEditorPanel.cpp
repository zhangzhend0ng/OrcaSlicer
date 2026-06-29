#include "GUI/VoxelEditor/VoxelEditorPanel.hpp"
#include "GUI/VoxelEditor/VoxelEditorCanvas.hpp"
#include "VoxelEditor/Octree.hpp"

#include <wx/stattext.h>
#include <wx/button.h>
#include <wx/sizer.h>
#include <wx/tglbtn.h>

namespace Slic3r {
namespace GUI {

wxBEGIN_EVENT_TABLE(VoxelEditorPanel, wxPanel)
    EVT_BUTTON(wxID_ANY, VoxelEditorPanel::on_place_tool)
wxEND_EVENT_TABLE()

VoxelEditorPanel::VoxelEditorPanel(wxWindow* parent)
    : wxPanel(parent, wxID_ANY, wxDefaultPosition, wxSize(900, 650))
{
    auto* main_sizer = new wxBoxSizer(wxVERTICAL);

    // Toolbar.
    auto* toolbar = new wxBoxSizer(wxHORIZONTAL);
    auto* btn_place  = new wxButton(this, wxID_ANY, "Place (1)");
    auto* btn_remove = new wxButton(this, wxID_ANY, "Remove (2)");
    auto* btn_brush  = new wxButton(this, wxID_ANY, "Brush (3)");
    auto* btn_reset  = new wxButton(this, wxID_ANY, "Reset View");

    // Use unique IDs for event binding.
    btn_place->SetId(1001);
    btn_remove->SetId(1002);
    btn_brush->SetId(1003);
    btn_reset->SetId(1004);

    toolbar->Add(btn_place,  0, wxALL, 4);
    toolbar->Add(btn_remove, 0, wxALL, 4);
    toolbar->Add(btn_brush,  0, wxALL, 4);
    toolbar->AddStretchSpacer();
    toolbar->Add(btn_reset,  0, wxALL, 4);

    m_status = new wxStaticText(this, wxID_ANY, "Tool: None");
    m_node_count = new wxStaticText(this, wxID_ANY, "Nodes: 0");
    toolbar->Add(m_status, 0, wxALL | wxALIGN_CENTER_VERTICAL, 4);
    toolbar->Add(m_node_count, 0, wxALL | wxALIGN_CENTER_VERTICAL, 4);

    main_sizer->Add(toolbar, 0, wxEXPAND);

    // 3D canvas.
    m_canvas = new VoxelEditorCanvas(this, nullptr);
    main_sizer->Add(m_canvas, 1, wxEXPAND);

    SetSizer(main_sizer);

    // Bind events.
    btn_place->Bind(wxEVT_BUTTON,  &VoxelEditorPanel::on_place_tool,  this);
    btn_remove->Bind(wxEVT_BUTTON, &VoxelEditorPanel::on_remove_tool, this);
    btn_brush->Bind(wxEVT_BUTTON,  &VoxelEditorPanel::on_brush_tool,  this);
    btn_reset->Bind(wxEVT_BUTTON,  &VoxelEditorPanel::on_reset_view,  this);

    // Canvas edit callback.
    m_canvas->set_edit_callback([this](double x, double y, double z, bool place) {
        on_edit(x, y, z, place);
    });
}

VoxelEditorPanel::~VoxelEditorPanel() = default;

void VoxelEditorPanel::load_octree(std::shared_ptr<Octree> octree)
{
    m_octree = std::move(octree);
    m_canvas->set_octree(m_octree);
    update_status_text();
}

void VoxelEditorPanel::on_place_tool(wxCommandEvent&)
{
    m_canvas->set_tool(VoxelEditorCanvas::Tool::Place);
    update_status_text();
}

void VoxelEditorPanel::on_remove_tool(wxCommandEvent&)
{
    m_canvas->set_tool(VoxelEditorCanvas::Tool::Remove);
    update_status_text();
}

void VoxelEditorPanel::on_brush_tool(wxCommandEvent&)
{
    m_canvas->set_tool(VoxelEditorCanvas::Tool::Brush);
    update_status_text();
}

void VoxelEditorPanel::on_reset_view(wxCommandEvent&)
{
    m_canvas->reset_camera();
}

void VoxelEditorPanel::on_edit(double wx, double wy, double wz, bool place)
{
    if (!m_octree) return;

    float vs = 1.0f;
    if (place) {
        m_octree->fill_region(
            BoundingBoxf3({wx - vs*0.5f, wy - vs*0.5f, wz - vs*0.5f},
                           {wx + vs*0.5f, wy + vs*0.5f, wz + vs*0.5f}), 1.0f);
    } else {
        m_octree->fill_region(
            BoundingBoxf3({wx - vs*0.5f, wy - vs*0.5f, wz - vs*0.5f},
                           {wx + vs*0.5f, wy + vs*0.5f, wz + vs*0.5f}), 0.0f);
    }
    m_canvas->set_octree(m_octree);
    update_status_text();
}

void VoxelEditorPanel::update_status_text()
{
    const char* tool_names[] = {"None", "Place", "Remove", "Brush"};
    int t = static_cast<int>(m_canvas->tool());
    m_status->SetLabel(wxString::Format("Tool: %s", tool_names[t]));

    if (m_octree)
        m_node_count->SetLabel(wxString::Format("Nodes: %zu", m_octree->node_count()));
    else
        m_node_count->SetLabel("Nodes: 0");
}

} // namespace GUI
} // namespace Slic3r
