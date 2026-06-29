#ifndef slic3r_VoxelEditorCanvas_hpp_
#define slic3r_VoxelEditorCanvas_hpp_

#include <wx/glcanvas.h>
#include <wx/timer.h>

#include <memory>`n#include <functional>
#include <vector>

namespace Slic3r {

class Octree;
class VoxelGrid;

namespace GUI {

// Camera state for the voxel editor viewport.
struct VoxelCamera {
    double yaw   = 45.0;   // degrees, rotation around Y axis
    double pitch = 30.0;   // degrees, elevation
    double dist  = 50.0;   // distance from target
    double tx    = 0.0;    // pan X (world units)
    double ty    = 0.0;    // pan Y (world units)
};

// Renders an Octree as colored cubes using OpenGL.
// Provides orbit/pan/zoom camera controls and click-based block editing.
class VoxelEditorCanvas : public wxGLCanvas
{
public:
    VoxelEditorCanvas(wxWindow* parent, wxGLContext* shared_ctx = nullptr);
    ~VoxelEditorCanvas() override;

    // Set the voxel model to display.
    void set_octree(std::shared_ptr<Octree> octree);

    // Set the voxel size for rendering (mm per voxel).
    void set_voxel_size(float vs) { m_voxel_size = vs; }
    void set_brush_size(float bs) { m_brush_size = bs; }
    float brush_size() const { return m_brush_size; }

    // Camera control.
    const VoxelCamera& camera() const { return m_camera; }
    void reset_camera();

    // Editing mode.
    enum class Tool { None, Place, Remove, Brush };
    void set_tool(Tool t) { m_tool = t; }
    Tool tool() const { return m_tool; }

    // Callback when a block is placed or removed.
    using EditCallback = std::function<void(double wx, double wy, double wz, bool place)>;
    void set_edit_callback(EditCallback cb) { m_edit_cb = std::move(cb); }

protected:
    void OnPaint(wxPaintEvent& event);
    void OnSize(wxSizeEvent& event);
    void OnMouse(wxMouseEvent& event);
    void OnKeyDown(wxKeyEvent& event);
    void OnTimer(wxTimerEvent& event);
    void OnIdle(wxIdleEvent& event);

private:
    void init_opengl();
    void render();
    void render_octree();
    void render_grid();
    void render_cursor();

    void setup_projection(int w, int h);
    void apply_camera();

    // Convert screen coordinates to a world-space ray.
    void screen_to_world(int sx, int sy, double& ox, double& oy, double& oz,
                          double& dx, double& dy, double& dz);

    // Find the first octree leaf intersected by a ray.
    bool ray_pick(double ox, double oy, double oz,
                   double dx, double dy, double dz,
                   double& hit_x, double& hit_y, double& hit_z);

    wxGLContext* m_gl_context = nullptr;
    bool m_gl_initialized = false;

    std::shared_ptr<Octree> m_octree;
    float m_voxel_size = 1.0f;
    float m_brush_size = 2.0f;

    VoxelCamera m_camera;
    Tool m_tool = Tool::None;

    // Mouse state.
    int m_mouse_x = 0, m_mouse_y = 0;
    int m_mouse_down_x = 0, m_mouse_down_y = 0;
    double m_camera_drag_yaw = 0, m_camera_drag_pitch = 0;
    double m_camera_drag_tx = 0, m_camera_drag_ty = 0;
    bool m_dragging = false;
    bool m_panning  = false;

    EditCallback m_edit_cb;
    wxTimer m_render_timer;

    wxDECLARE_EVENT_TABLE();
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_VoxelEditorCanvas_hpp_
