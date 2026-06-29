#ifndef slic3r_VoxelEditorPanel_hpp_
#define slic3r_VoxelEditorPanel_hpp_

#include <wx/panel.h>
#include <wx/stattext.h>
#include <wx/slider.h>
#include <wx/sizer.h>

#include <memory>
#include <vector>
#include <deque>
#include <string>

namespace Slic3r {

class Octree;
class VoxelGrid;
struct VoxelSlicerConfig;

namespace GUI {

class VoxelEditorCanvas;

// Complete voxel editor panel with toolbar for all three editing tiers
// (Section 4.1) plus undo/redo and G-code export.
class VoxelEditorPanel : public wxPanel
{
public:
    VoxelEditorPanel(wxWindow* parent);
    ~VoxelEditorPanel() override;

    // Load a voxel model for editing.
    void load_octree(std::shared_ptr<Octree> octree);
    std::shared_ptr<Octree> octree() const { return m_octree; }

    // ---- Toolbar callbacks (high-level ops) ----
    void on_template_cube(wxCommandEvent&);
    void on_template_sphere(wxCommandEvent&);
    void on_template_cylinder(wxCommandEvent&);
    void on_template_torus(wxCommandEvent&);
    void on_boolean_union(wxCommandEvent&);
    void on_boolean_subtract(wxCommandEvent&);
    void on_boolean_intersect(wxCommandEvent&);
    void on_hollow(wxCommandEvent&);
    void on_smooth(wxCommandEvent&);
    void on_array_linear(wxCommandEvent&);
    void on_array_grid(wxCommandEvent&);

    // ---- Toolbar callbacks (mid-level ops) ----
    void on_place_tool(wxCommandEvent&);
    void on_remove_tool(wxCommandEvent&);
    void on_brush_tool(wxCommandEvent&);
    void on_brush_size_changed(wxCommandEvent&);

    // ---- Toolbar callbacks (low-level + utility) ----
    void on_reset_view(wxCommandEvent&);
    void on_undo(wxCommandEvent&);
    void on_redo(wxCommandEvent&);
    void on_import_stl(wxCommandEvent&);
    void on_slice_gcode(wxCommandEvent&);
    void on_export_gcode(wxCommandEvent&);

    // Edit callback from canvas.
    void on_edit(double wx, double wy, double wz, bool place);

private:
    void update_status_text();
    void push_undo();
    const Octree& clipboard_or_empty() const;

    VoxelEditorCanvas* m_canvas = nullptr;
    std::shared_ptr<Octree> m_octree;

    // Undo/Redo: snapshots stored as VoxelGrid via to_grid.
    struct Snapshot {
        std::unique_ptr<VoxelGrid> grid;
        std::string label;
    };
    std::deque<Snapshot> m_undo_stack;
    std::deque<Snapshot> m_redo_stack;
    static constexpr size_t MAX_UNDO = 50;

    // Clipboard for boolean ops.
    std::shared_ptr<Octree> m_clipboard;

    // Last generated G-code (for export).
    std::string m_last_gcode;

    // UI widgets.
    wxStaticText* m_status = nullptr;
    wxStaticText* m_node_count = nullptr;
    wxSlider*     m_brush_size_slider = nullptr;
    wxStaticText* m_brush_size_label = nullptr;

    wxDECLARE_EVENT_TABLE();
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_VoxelEditorPanel_hpp_
