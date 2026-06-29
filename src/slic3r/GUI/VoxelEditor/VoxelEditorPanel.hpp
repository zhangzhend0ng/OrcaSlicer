#ifndef slic3r_VoxelEditorPanel_hpp_
#define slic3r_VoxelEditorPanel_hpp_

#include <wx/panel.h>
#include <wx/button.h>
#include <wx/stattext.h>
#include <wx/sizer.h>

#include <memory>

namespace Slic3r {

class Octree;

namespace GUI {

class VoxelEditorCanvas;

// Main panel for the voxel editor.
// Contains the 3D viewport (VoxelEditorCanvas) and a toolbar.
class VoxelEditorPanel : public wxPanel
{
public:
    VoxelEditorPanel(wxWindow* parent);
    ~VoxelEditorPanel() override;

    // Load a voxel model for editing.
    void load_octree(std::shared_ptr<Octree> octree);

    // Get the current edited octree.
    std::shared_ptr<Octree> octree() const { return m_octree; }

    // Toolbar callbacks.
    void on_place_tool(wxCommandEvent&);
    void on_remove_tool(wxCommandEvent&);
    void on_brush_tool(wxCommandEvent&);
    void on_reset_view(wxCommandEvent&);

    // Edit callback from canvas.
    void on_edit(double wx, double wy, double wz, bool place);

private:
    void update_status_text();

    VoxelEditorCanvas* m_canvas = nullptr;
    std::shared_ptr<Octree> m_octree;
    wxStaticText* m_status = nullptr;
    wxStaticText* m_node_count = nullptr;

    wxDECLARE_EVENT_TABLE();
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_VoxelEditorPanel_hpp_
