#include "slic3r/GUI/VoxelEditor/VoxelEditorDialog.hpp"
#include "../I18N.hpp"
#include "slic3r/GUI/VoxelEditor/VoxelEditorPanel.hpp"
#include "slic3r/GUI/VoxelEditor/VoxelEditorCanvas.hpp"
#include "libslic3r/VoxelEditor/Octree.hpp"
#include "libslic3r/VoxelEditor/VoxelGrid.hpp"
#include "libslic3r/VoxelEditor/MeshVoxelizer.hpp"
#include "libslic3r/VoxelEditor/VoxelToMesh.hpp"
#include "libslic3r/TriangleMesh.hpp"

#include <wx/sizer.h>
#include <wx/button.h>
#include <wx/filedlg.h>
#include <wx/msgdlg.h>

namespace Slic3r {
namespace GUI {

wxBEGIN_EVENT_TABLE(VoxelEditorDialog, wxDialog)
    EVT_BUTTON(wxID_OK,     VoxelEditorDialog::on_ok)
    EVT_BUTTON(wxID_CANCEL, VoxelEditorDialog::on_cancel)
wxEND_EVENT_TABLE()

VoxelEditorDialog::VoxelEditorDialog(wxWindow* parent)
    : wxDialog(parent, wxID_ANY, _L("Voxel Editor - AI 3D Model Editor"),
               wxDefaultPosition, wxSize(1000, 750),
               wxDEFAULT_DIALOG_STYLE | wxRESIZE_BORDER | wxMAXIMIZE_BOX)
{
    auto* main_sizer = new wxBoxSizer(wxVERTICAL);
    m_editor = new VoxelEditorPanel(this);
    main_sizer->Add(m_editor, 1, wxEXPAND);

    auto* btn_sizer = new wxBoxSizer(wxHORIZONTAL);
    auto* btn_import = new wxButton(this, wxID_ANY, _L("Import STL"));
    auto* btn_export = new wxButton(this, wxID_ANY, _L("Export STL"));
    btn_sizer->Add(btn_import, 0, wxALL, 5);
    btn_sizer->Add(btn_export, 0, wxALL, 5);
    btn_sizer->AddStretchSpacer();
    auto* btn_ok = new wxButton(this, wxID_OK, _L("Apply && Close"));
    auto* btn_cancel = new wxButton(this, wxID_CANCEL, _L("Cancel"));
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
    wxFileDialog dlg(this, _L("Open STL file"), "", "",
        "STL files (*.stl)|*.stl|All files (*.*)|*.*",
        wxFD_OPEN | wxFD_FILE_MUST_EXIST);
    if (dlg.ShowModal() != wxID_OK) return;

    TriangleMesh mesh;
    if (!mesh.ReadSTLFile(dlg.GetPath().ToStdString().c_str())) {
        wxMessageBox(_L("Failed to load STL file."), _L("Error"), wxOK | wxICON_ERROR);
        return;
    }
    load_mesh(mesh);
}

void VoxelEditorDialog::on_export_stl(wxCommandEvent&)
{
    auto octree = m_editor->octree();
    if (!octree) {
        wxMessageBox(_L("No model to export."), _L("Info"), wxOK | wxICON_INFORMATION);
        return;
    }

    wxFileDialog dlg(this, _L("Save STL file"), "", "model.stl",
        "STL files (*.stl)|*.stl|All files (*.*)|*.*",
        wxFD_SAVE | wxFD_OVERWRITE_PROMPT);
    if (dlg.ShowModal() != wxID_OK) return;

    TriangleMesh mesh = VoxelToMesh::convert(*octree, 1.0f);
    if (!mesh.write_binary(dlg.GetPath().ToStdString().c_str())) {
        wxMessageBox(_L("Failed to write STL file."), _L("Error"), wxOK | wxICON_ERROR);
        return;
    }
    wxMessageBox(_L("STL exported successfully."), _L("Done"), wxOK | wxICON_INFORMATION);
}

TriangleMesh VoxelEditorDialog::export_mesh() const
{
    if (m_result)
        return VoxelToMesh::convert(*m_result, 1.0f);
    return TriangleMesh{};
}

} // namespace GUI
} // namespace Slic3r
