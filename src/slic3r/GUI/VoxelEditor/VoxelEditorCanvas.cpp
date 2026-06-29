#include "GUI/VoxelEditor/VoxelEditorCanvas.hpp"
#include "VoxelEditor/Octree.hpp"

#include <wx/dcclient.h>

#ifdef _WIN32
#include <GL/gl.h>
// GLU not available - using manual implementations
#else
#include <OpenGL/gl.h>
#include <OpenGL/glu.h>
#endif

#include <cmath>
#include <algorithm>`n#include <cstring>

namespace Slic3r {
namespace GUI {

wxBEGIN_EVENT_TABLE(VoxelEditorCanvas, wxGLCanvas)
    EVT_PAINT(VoxelEditorCanvas::OnPaint)
    EVT_SIZE(VoxelEditorCanvas::OnSize)
    EVT_MOUSE_EVENTS(VoxelEditorCanvas::OnMouse)
    EVT_KEY_DOWN(VoxelEditorCanvas::OnKeyDown)
    EVT_TIMER(wxID_ANY, VoxelEditorCanvas::OnTimer)
    EVT_IDLE(VoxelEditorCanvas::OnIdle)
wxEND_EVENT_TABLE()

VoxelEditorCanvas::VoxelEditorCanvas(wxWindow* parent, wxGLContext* shared_ctx)
    : wxGLCanvas(parent, wxID_ANY, nullptr, wxDefaultPosition, wxSize(800, 600),
                 0, "VoxelEditor")
    , m_render_timer(this)
{
    int gl_attrs[] = {
        WX_GL_RGBA,
        WX_GL_DOUBLEBUFFER,
        WX_GL_DEPTH_SIZE, 24,
        WX_GL_STENCIL_SIZE, 8,
        0
    };
    // Recreate canvas with proper attributes
    // (wxGLCanvas needs attributes at construction, we inherit defaults)

    if (shared_ctx)
        m_gl_context = new wxGLContext(this, shared_ctx);
    else
        m_gl_context = new wxGLContext(this);

    m_render_timer.Start(33); // ~30 fps
}

VoxelEditorCanvas::~VoxelEditorCanvas()
{
    m_render_timer.Stop();
    if (m_gl_context) {
        SetCurrent(*m_gl_context);
        delete m_gl_context;
        m_gl_context = nullptr;
    }
}

void VoxelEditorCanvas::set_octree(std::shared_ptr<Octree> octree)
{
    m_octree = std::move(octree);
    reset_camera();
}

void VoxelEditorCanvas::reset_camera()
{
    if (m_octree) {
        auto bbox = m_octree->world_bbox();
        auto size = bbox.size();
        m_camera.dist = std::max({size.x(), size.y(), size.z()}) * 2.0;
        auto center = bbox.center();
        m_camera.tx = -center.x();
        m_camera.ty = -center.y();
        m_camera.yaw = 45.0;
        m_camera.pitch = 30.0;
    }
    Refresh();
}

// --- OpenGL Init ---

void VoxelEditorCanvas::init_opengl()
{
    if (m_gl_initialized) return;
    if (!SetCurrent(*m_gl_context)) return;

    glClearColor(0.15f, 0.15f, 0.18f, 1.0f);
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glEnable(GL_LIGHTING);
    glEnable(GL_LIGHT0);
    glEnable(GL_COLOR_MATERIAL);
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE);

    GLfloat light_pos[] = { 1.0f, 1.0f, 1.0f, 0.0f };
    GLfloat light_amb[] = { 0.2f, 0.2f, 0.2f, 1.0f };
    GLfloat light_dif[] = { 0.8f, 0.8f, 0.8f, 1.0f };
    glLightfv(GL_LIGHT0, GL_POSITION, light_pos);
    glLightfv(GL_LIGHT0, GL_AMBIENT, light_amb);
    glLightfv(GL_LIGHT0, GL_DIFFUSE, light_dif);

    m_gl_initialized = true;
}

// --- Rendering ---

void VoxelEditorCanvas::OnPaint(wxPaintEvent&)
{
    wxPaintDC dc(this);
    init_opengl();
    if (!SetCurrent(*m_gl_context)) return;
    render();
    SwapBuffers();
}

void VoxelEditorCanvas::OnSize(wxSizeEvent& event)
{
    Refresh();
    event.Skip();
}

void VoxelEditorCanvas::OnTimer(wxTimerEvent&)
{
    Refresh();
}

void VoxelEditorCanvas::OnIdle(wxIdleEvent& event)
{
    // Request more idle events for continuous rendering
    event.RequestMore();
}

void VoxelEditorCanvas::render()
{
    int w, h;
    GetClientSize(&w, &h);
    if (w <= 0 || h <= 0) return;

    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    setup_projection(w, h);
    apply_camera();

    render_grid();
    if (m_octree) render_octree();
    if (m_tool != Tool::None) render_cursor();
}

void VoxelEditorCanvas::setup_projection(int w, int h)
{
    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    double aspect = double(w) / std::max(1, h);
    // Manual perspective (replaces gluPerspective)
    double fovy = 45.0 * M_PI / 180.0;
    double f = 1.0 / std::tan(fovy / 2.0);
    double proj_mat[16] = {
        f / aspect, 0, 0, 0,
        0, f, 0, 0,
        0, 0, (1000.0 + 0.1) / (0.1 - 1000.0), -1,
        0, 0, (2 * 1000.0 * 0.1) / (0.1 - 1000.0), 0
    };
    glMultMatrixd(proj_mat);
    glMatrixMode(GL_MODELVIEW);
}

void VoxelEditorCanvas::apply_camera()
{
    glLoadIdentity();
    // Orbit camera: translate to target, rotate, then zoom
    glTranslated(m_camera.tx, m_camera.ty, -m_camera.dist);
    glRotated(m_camera.pitch, 1.0, 0.0, 0.0);
    glRotated(m_camera.yaw,   0.0, 1.0, 0.0);
}

void VoxelEditorCanvas::render_grid()
{
    glDisable(GL_LIGHTING);
    glColor4f(0.3f, 0.3f, 0.35f, 0.5f);
    glBegin(GL_LINES);
    float gsize = 50.0f;
    float step  = 5.0f;
    for (float i = -gsize; i <= gsize; i += step) {
        glVertex3f(i, -gsize, 0.0f);
        glVertex3f(i,  gsize, 0.0f);
        glVertex3f(-gsize, i, 0.0f);
        glVertex3f( gsize, i, 0.0f);
    }
    glEnd();

    // X/Y axes
    glBegin(GL_LINES);
    glColor3f(1.0f, 0.2f, 0.2f); // X red
    glVertex3f(0, 0, 0); glVertex3f(20, 0, 0);
    glColor3f(0.2f, 1.0f, 0.2f); // Y green
    glVertex3f(0, 0, 0); glVertex3f(0, 20, 0);
    glEnd();
    glEnable(GL_LIGHTING);
}

void VoxelEditorCanvas::render_octree()
{
    if (!m_octree) return;

    float vs = m_voxel_size;
    float half = vs * 0.5f;

    glColor3f(0.3f, 0.6f, 0.9f);

    // Walk the octree leaves and draw each filled region as a cube.
    m_octree->visit_leaves([&](const BoundingBoxf3& bbox, VoxelNodeState state, VoxelValue val) {
        if (state == VoxelNodeState::Empty || val <= 0.0f) return;

        Vec3d c = bbox.center();
        Vec3d s = bbox.size();
        float alpha = std::min(1.0f, val);

        // Color based on height (z).
        float z_norm = float((c.z() - m_octree->world_bbox().min.z()) /
                        std::max(1.0, m_octree->world_bbox().size().z()));
        glColor4f(0.3f + z_norm * 0.5f, 0.5f + z_norm * 0.3f, 0.6f + z_norm * 0.4f, alpha);

        // Only draw if the node is a reasonable size for display.
        double min_dim = std::min({s.x(), s.y(), s.z()});
        if (min_dim < 0.05) return; // skip microscopic nodes

        glPushMatrix();
        glTranslated(c.x(), c.y(), c.z());
        glScaled(s.x() * 0.5, s.y() * 0.5, s.z() * 0.5);

        // Simple cube via GLUT-like quad strips, or 6 quads manually.
        // We'll draw a unit cube scaled to the node size.
        float sx2 = 1.0f, sy2 = 1.0f, sz2 = 1.0f;

        glBegin(GL_QUADS);
        // Front face
        glNormal3f(0, 0, 1);
        glVertex3f(-sx2, -sy2,  sz2); glVertex3f( sx2, -sy2,  sz2);
        glVertex3f( sx2,  sy2,  sz2); glVertex3f(-sx2,  sy2,  sz2);
        // Back face
        glNormal3f(0, 0, -1);
        glVertex3f( sx2, -sy2, -sz2); glVertex3f(-sx2, -sy2, -sz2);
        glVertex3f(-sx2,  sy2, -sz2); glVertex3f( sx2,  sy2, -sz2);
        // Top face
        glNormal3f(0, 1, 0);
        glVertex3f(-sx2,  sy2,  sz2); glVertex3f( sx2,  sy2,  sz2);
        glVertex3f( sx2,  sy2, -sz2); glVertex3f(-sx2,  sy2, -sz2);
        // Bottom face
        glNormal3f(0, -1, 0);
        glVertex3f(-sx2, -sy2, -sz2); glVertex3f( sx2, -sy2, -sz2);
        glVertex3f( sx2, -sy2,  sz2); glVertex3f(-sx2, -sy2,  sz2);
        // Right face
        glNormal3f(1, 0, 0);
        glVertex3f( sx2, -sy2,  sz2); glVertex3f( sx2, -sy2, -sz2);
        glVertex3f( sx2,  sy2, -sz2); glVertex3f( sx2,  sy2,  sz2);
        // Left face
        glNormal3f(-1, 0, 0);
        glVertex3f(-sx2, -sy2, -sz2); glVertex3f(-sx2, -sy2,  sz2);
        glVertex3f(-sx2,  sy2,  sz2); glVertex3f(-sx2,  sy2, -sz2);
        glEnd();

        glPopMatrix();
    });
}

void VoxelEditorCanvas::render_cursor()
{
    // Show cursor position in 3D (simplified: show at origin for now).
    glDisable(GL_LIGHTING);
    glColor4f(1.0f, 0.8f, 0.2f, 0.8f);
    glPointSize(6.0f);
    glBegin(GL_POINTS);
    glVertex3d(0, 0, 0);
    glEnd();
    glEnable(GL_LIGHTING);
}

// --- Mouse Interaction ---

void VoxelEditorCanvas::OnMouse(wxMouseEvent& event)
{
    int x = event.GetX(), y = event.GetY();

    if (event.LeftDown()) {
        m_mouse_down_x = x;
        m_mouse_down_y = y;
        m_camera_drag_yaw   = m_camera.yaw;
        m_camera_drag_pitch = m_camera.pitch;
        m_camera_drag_tx    = m_camera.tx;
        m_camera_drag_ty    = m_camera.ty;

        if (event.ShiftDown()) {
            m_panning = true;
        } else {
            m_dragging = true;
        }
        CaptureMouse();
    }
    else if (event.LeftUp()) {
        if (HasCapture()) ReleaseMouse();
        if (!m_dragging && !m_panning && m_tool != Tool::None) {
            // Click: place or remove a block.
            // Convert screen click to world ray.
            double ox, oy, oz, dx, dy, dz;
            screen_to_world(x, y, ox, oy, oz, dx, dy, dz);
            double hx, hy, hz;
            if (ray_pick(ox, oy, oz, dx, dy, dz, hx, hy, hz)) {
                if (m_edit_cb)
                    m_edit_cb(hx, hy, hz, m_tool == Tool::Place || m_tool == Tool::Brush);
            }
        }
        m_dragging = false;
        m_panning  = false;
    }
    else if (event.Dragging()) {
        int dx = x - m_mouse_down_x;
        int dy = y - m_mouse_down_y;

        if (m_panning) {
            m_camera.tx = m_camera_drag_tx + dx * 0.1;
            m_camera.ty = m_camera_drag_ty - dy * 0.1;
        } else if (m_dragging) {
            m_camera.yaw   = m_camera_drag_yaw   + dx * 0.5;
            m_camera.pitch = m_camera_drag_pitch - dy * 0.5;
            m_camera.pitch = std::max(-89.0, std::min(89.0, m_camera.pitch));
        }
    }
    else if (event.GetWheelRotation() != 0) {
        double delta = event.GetWheelRotation() > 0 ? 0.9 : 1.1;
        m_camera.dist *= delta;
        m_camera.dist = std::max(1.0, std::min(500.0, m_camera.dist));
    }

    m_mouse_x = x;
    m_mouse_y = y;
}

void VoxelEditorCanvas::OnKeyDown(wxKeyEvent& event)
{
    switch (event.GetKeyCode()) {
    case 'R': reset_camera(); break;
    case '1': m_tool = Tool::Place;  break;
    case '2': m_tool = Tool::Remove; break;
    case '3': m_tool = Tool::Brush;  break;
    case WXK_ESCAPE: m_tool = Tool::None; break;
    default: event.Skip();
    }
}


// Manual unproject (replaces gluUnProject).
static void unproject(double winx, double winy, double winz,
                       const double* mv, const double* proj, const int* vp,
                       double& ox, double& oy, double& oz)
{
    // Compute inverse of MVP matrix manually.
    // Build MVP = proj * mv
    double mvp[16];
    for (int i = 0; i < 4; ++i)
        for (int j = 0; j < 4; ++j) {
            mvp[i*4+j] = 0;
            for (int k = 0; k < 4; ++k)
                mvp[i*4+j] += proj[i*4+k] * mv[k*4+j];
        }

    // Invert 4x4 matrix (simple Gauss-Jordan).
    double inv[16] = {1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1};
    double tmp[16];
    memcpy(tmp, mvp, sizeof(tmp));

    for (int i = 0; i < 4; ++i) {
        double pivot = tmp[i*4+i];
        if (std::abs(pivot) < 1e-10) { ox=oy=oz=0; return; }
        for (int j = 0; j < 4; ++j) { tmp[i*4+j] /= pivot; inv[i*4+j] /= pivot; }
        for (int k = 0; k < 4; ++k) {
            if (k == i) continue;
            double factor = tmp[k*4+i];
            for (int j = 0; j < 4; ++j) {
                tmp[k*4+j] -= factor * tmp[i*4+j];
                inv[k*4+j] -= factor * inv[i*4+j];
            }
        }
    }

    // Normalized device coords.
    double nx = (winx - vp[0]) / vp[2] * 2.0 - 1.0;
    double ny = (winy - vp[1]) / vp[3] * 2.0 - 1.0;
    double nz = winz * 2.0 - 1.0;

    double w = inv[3] * nx + inv[7] * ny + inv[11] * nz + inv[15];
    if (std::abs(w) < 1e-10) { ox=oy=oz=0; return; }
    ox = (inv[0]*nx + inv[4]*ny + inv[8]*nz  + inv[12]) / w;
    oy = (inv[1]*nx + inv[5]*ny + inv[9]*nz  + inv[13]) / w;
    oz = (inv[2]*nx + inv[6]*ny + inv[10]*nz + inv[14]) / w;
}

void VoxelEditorCanvas::screen_to_world(int sx, int sy,
    double& ox, double& oy, double& oz, double& dx, double& dy, double& dz)
{
    int w, h;
    GetClientSize(&w, &h);
    if (w <= 0 || h <= 0) { ox=oy=oz=dx=dy=dz=0; return; }

    GLint viewport[4];
    GLdouble mv[16], proj[16];
    glGetIntegerv(GL_VIEWPORT, viewport);
    glGetDoublev(GL_MODELVIEW_MATRIX, mv);
    glGetDoublev(GL_PROJECTION_MATRIX, proj);

    double winx = double(sx), winy = double(h - sy); // flip Y
    double wx, wy, wz;

    // Near plane
    unproject(winx, winy, 0.0, mv, proj, viewport, ox, oy, oz);
    // Far plane
    unproject(winx, winy, 1.0, mv, proj, viewport, wx, wy, wz);

    dx = wx - ox;
    dy = wy - oy;
    dz = wz - oz;
}

bool VoxelEditorCanvas::ray_pick(double ox, double oy, double oz,
    double dx, double dy, double dz, double& hx, double& hy, double& hz)
{
    if (!m_octree) return false;

    // Simple stepping along the ray with voxel-sized steps.
    double len = std::sqrt(dx*dx + dy*dy + dz*dz);
    if (len < 1e-6) return false;
    dx /= len; dy /= len; dz /= len;

    double step = m_voxel_size * 0.5;
    double max_dist = 200.0;
    int n_steps = int(max_dist / step);

    for (int i = 0; i < n_steps; ++i) {
        double t = i * step;
        double px = ox + dx * t;
        double py = oy + dy * t;
        double pz = oz + dz * t;

        VoxelValue v = m_octree->sample(Vec3d(px, py, pz));
        if (v >= 0.5f) {
            // Snap to voxel grid.
            hx = std::floor(px / m_voxel_size) * m_voxel_size + m_voxel_size * 0.5;
            hy = std::floor(py / m_voxel_size) * m_voxel_size + m_voxel_size * 0.5;
            hz = std::floor(pz / m_voxel_size) * m_voxel_size + m_voxel_size * 0.5;
            return true;
        }
    }
    return false;
}

} // namespace GUI
} // namespace Slic3r
