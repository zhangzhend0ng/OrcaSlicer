#ifndef slic3r_App_CameraController_hpp_
#define slic3r_App_CameraController_hpp_

#include "libslic3r/MVVP.hpp"
#include "libslic3r/Point.hpp"

#include <Eigen/Geometry>

namespace Slic3r {

/// Camera state snapshot (immutable, copyable, safe for any thread).
struct CameraState {
    Vec3d    target         = Vec3d::Zero();
    float    zenith         = 45.0f;
    double   zoom           = 1.0;
    double   distance       = 0.0;
    double   theta          = 0.0;  // azimuthal angle in radians
    double   phi            = 0.0;  // polar angle in radians

    bool operator==(const CameraState&) const = default;
    bool operator!=(const CameraState&) const = default;
};

/// Pure-C++ camera controller with MVVP interface.
/// Separates camera math from OpenGL/wxWidgets rendering.
/// Lives in Application layer (Layer 3), zero GUI dependencies.
class CameraController {
public:
    using mv = MVVP;

    // ?? Observable State ??
    MVVP::Property<CameraState> state{CameraState{}};
    MVVP::Property<bool>        isOrtho{false};
    MVVP::Property<bool>        isAnimating{false};

    // ?? Discrete Commands ??
    MVVP::Command resetView{
        [this] { set_default_orientation(); zoom_to_default(); }
    };
    MVVP::Command viewTop{
        [this] { set_orientation(0.0, 90.0); }
    };
    MVVP::Command viewFront{
        [this] { set_orientation(0.0, 0.0); }
    };
    MVVP::Command viewRight{
        [this] { set_orientation(90.0, 0.0); }
    };
    MVVP::Command toggleProjection{
        [this] {
            isOrtho.set(!isOrtho.get());
            recalc();
        }
    };

    // ?? Continuous Input (called from View at 60fps) ??
    void onMouseDown(int x, int y);
    void onMouseMove(int x, int y);
    void onMouseUp();
    void onMouseWheel(int delta);
    void onPinchGesture(double scale);

    // ?? Direct Camera Control ??
    void set_orientation(double theta_deg, double phi_deg);
    void set_default_orientation();
    void zoom_to_box(const BoundingBoxf3& box);
    void zoom_to_default();
    void orbit(double delta_theta_deg, double delta_phi_deg);
    void pan(double dx, double dy);
    void zoom(double factor);

    // ?? Derived Values (for rendering) ??
    Vec3d get_position() const;
    Vec3d get_dir_forward() const;
    Vec3d get_dir_right() const;
    Vec3d get_dir_up() const;
    double get_view_angle() const;

private:
    void recalc();

    // Raw state (not directly observable; state Property is updated from these)
    Vec3d  m_target{0, 0, 0};
    double m_theta{0.0};     // azimuth (radians)
    double m_phi{M_PI / 4.0}; // polar (radians)
    double m_distance{1000.0};
    double m_zoom{1.0};
    bool   m_dragging{false};
    int    m_drag_start_x{0}, m_drag_start_y{0};
    double m_drag_start_theta{0}, m_drag_start_phi{0};
};

} // namespace Slic3r

#endif /* slic3r_App_CameraController_hpp_ */
