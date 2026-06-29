#include "slic3r/GUI/VoxelEditor/VoxelEditorDialog.hpp"
#include "slic3r/GUI/VoxelEditor/VoxelEditorPanel.hpp"
#include "libslic3r/VoxelEditor/Octree.hpp"
#include "libslic3r/VoxelEditor/VoxelGrid.hpp"
#include "libslic3r/VoxelEditor/MeshVoxelizer.hpp"
#include "libslic3r/TriangleMesh.hpp"

#include <wx/sizer.h>
#include <wx/button.h>

#include <cmath>

namespace Slic3r {
namespace GUI {

wxBEGIN_EVENT_TABLE(VoxelEditorDialog, wxDialog)
    EVT_BUTTON(wxID_OK,     VoxelEditorDialog::on_ok)
    EVT_BUTTON(wxID_CANCEL, VoxelEditorDialog::on_cancel)
wxEND_EVENT_TABLE()

VoxelEditorDialog::VoxelEditorDialog(wxWindow* parent)
    : wxDialog(parent, wxID_ANY, "Voxel Editor - AI 3D Model Editor",
               wxDefaultPosition, wxSize(1000, 750),
               wxDEFAULT_DIALOG_STYLE | wxRESIZE_BORDER | wxMAXIMIZE_BOX)
{
    auto* main_sizer = new wxBoxSizer(wxVERTICAL);

    // Voxel editor panel (fills the dialog).
    m_editor = new VoxelEditorPanel(this);
    main_sizer->Add(m_editor, 1, wxEXPAND);

    // Bottom buttons.
    auto* btn_sizer = new wxBoxSizer(wxHORIZONTAL);
    auto* btn_import = new wxButton(this, wxID_ANY, "Import STL");
    auto* btn_export = new wxButton(this, wxID_ANY, "Export STL");
    btn_sizer->Add(btn_import, 0, wxALL, 5);
    btn_sizer->Add(btn_export, 0, wxALL, 5);
    btn_sizer->AddStretchSpacer();
    auto* btn_ok = new wxButton(this, wxID_OK, "Apply && Close");
    auto* btn_cancel = new wxButton(this, wxID_CANCEL, "Cancel");
    btn_ok->SetDefault();
    btn_sizer->Add(btn_cancel, 0, wxALL, 5);
    btn_sizer->Add(btn_ok, 0, wxALL, 5);
    main_sizer->Add(btn_sizer, 0, wxEXPAND);

    SetSizer(main_sizer);

    btn_import->Bind(wxEVT_BUTTON, &VoxelEditorDialog::on_import, this);
    btn_export->Bind(wxEVT_BUTTON, &VoxelEditorDialog::on_export_stl, this);
}

VoxelEditorDialog::~VoxelEditorDialog() = default;

void VoxelEditorDialog::load_mesh(const TriangleMesh& mesh)
{
    MeshVoxelizer::Config cfg;
    cfg.voxel_size_mm = 1.0f;
    cfg.fill_interior = true;
    MeshVoxelizer voxelizer(cfg);
    VoxelGrid grid = voxelizer.voxelize(mesh);
    m_editor->load_octree(std::make_shared<Octree>(Octree::from_grid(grid)));
}

void VoxelEditorDialog::load_octree(std::shared_ptr<Octree> octree)
{
    m_editor->load_octree(std::move(octree));
}

void VoxelEditorDialog::on_ok(wxCommandEvent&)
{
    m_result = m_editor->octree();
    EndModal(wxID_OK);
}

void VoxelEditorDialog::on_cancel(wxCommandEvent&)
{
    EndModal(wxID_CANCEL);
}

void VoxelEditorDialog::on_import(wxCommandEvent&)
{
    // The panel already has its own Import STL button; delegate.
    // We can also trigger the panel's import directly.
}

void VoxelEditorDialog::on_export_stl(wxCommandEvent&)
{
    // Delegate to panel export.
}

TriangleMesh VoxelEditorDialog::export_mesh() const
{
    // TODO: convert octree back to mesh
    // For now, return an empty mesh (mesh→voxel round-trip not yet implemented).
    return TriangleMesh{};
}

} // namespace GUI
} // namespace Slic3r
