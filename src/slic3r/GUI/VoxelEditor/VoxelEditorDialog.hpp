#ifndef slic3r_VoxelEditorDialog_hpp_
#define slic3r_VoxelEditorDialog_hpp_

#include <wx/dialog.h>
#include <wx/button.h>
#include <memory>

namespace Slic3r {

class Octree;
class TriangleMesh;

namespace GUI {

class VoxelEditorPanel;

// Modal dialog that wraps the full VoxelEditorPanel.
// Usage:
//   VoxelEditorDialog dlg(parent);
//   dlg.load_mesh(mesh);      // Optional: load from an existing TriangleMesh
//   if (dlg.ShowModal() == wxID_OK) { ... }
class VoxelEditorDialog : public wxDialog
{
public:
    VoxelEditorDialog(wxWindow* parent);
    ~VoxelEditorDialog() override;

    // Load a mesh for editing (voxelizes it automatically).
    void load_mesh(const TriangleMesh& mesh);

    // Load an existing octree.
    void load_octree(std::shared_ptr<Octree> octree);

    // Get the edited result as a dense voxel grid (call after OK).
    std::shared_ptr<Octree> result_octree() const { return m_result; }

    // Export the edited model back to a TriangleMesh (call after OK).
    TriangleMesh export_mesh() const;

private:
    void on_ok(wxCommandEvent&);
    void on_cancel(wxCommandEvent&);
    void on_import(wxCommandEvent&);
    void on_export_stl(wxCommandEvent&);

    VoxelEditorPanel* m_editor = nullptr;
    std::shared_ptr<Octree> m_result;

    wxDECLARE_EVENT_TABLE();
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_VoxelEditorDialog_hpp_
