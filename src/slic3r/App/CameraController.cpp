#include "slic3r/App/CameraController.hpp"

#include <cmath>
#include <algorithm>

namespace Slic3r {

void CameraController::set_orientation(double theta_deg, double phi_deg)
{
    m_theta = theta_deg * M_PI / 180.0;
    m_phi   = phi_deg   * M_PI / 180.0;
    recalc();
}

void CameraController::set_default_orientation()
{
    m_theta = 0.0;
    m_phi   = M_PI / 4.0;
    recalc();
}

void CameraController::orbit(double delta_theta_deg, double delta_phi_deg)
{
    m_theta += delta_theta_deg * M_PI / 180.0;
    m_phi   += delta_phi_deg   * M_PI / 180.0;
    // Clamp phi to avoid gimbal lock
    m_phi = std::clamp(m_phi, 0.01, M_PI - 0.01);
    recalc();
}

void CameraController::pan(double dx, double dy)
{
    // Pan in camera-local coordinates
    Vec3d right = get_dir_right();
    Vec3d up    = get_dir_up();
    m_target += right * dx + up * dy;
    recalc();
}

void CameraController::zoom(double factor)
{
    m_zoom *= factor;
    m_zoom = std::clamp(m_zoom, 0.1, 100.0);
    recalc();
}

void CameraController::zoom_to_box(const BoundingBoxf3& box)
{
    Vec3d center = box.center();
    double size = box.size().norm();
    m_target   = center;
    m_distance = size * 1.5;
    m_zoom     = 1.0;
    recalc();
}

void CameraController::zoom_to_default()
{
    m_distance = 1000.0;
    m_zoom     = 1.0;
    recalc();
}

void CameraController::onMouseDown(int x, int y)
{
    m_dragging      = true;
    m_drag_start_x  = x;
    m_drag_start_y  = y;
    m_drag_start_theta = m_theta;
    m_drag_start_phi   = m_phi;
}

void CameraController::onMouseMove(int x, int y)
{
    if (!m_dragging) return;
    double dx = static_cast<double>(x - m_drag_start_x);
    double dy = static_cast<double>(y - m_drag_start_y);
    m_theta = m_drag_start_theta + dx * 0.01;
    m_phi   = m_drag_start_phi   - dy * 0.01;
    m_phi   = std::clamp(m_phi, 0.01, M_PI - 0.01);
    recalc();
}

void CameraController::onMouseUp()
{
    m_dragging = false;
}

void CameraController::onMouseWheel(int delta)
{
    zoom(1.0 + delta * 0.001);
}

void CameraController::onPinchGesture(double scale)
{
    zoom(scale);
}

Vec3d CameraController::get_position() const
{
    double r = m_distance * m_zoom * std::sin(m_phi);
    return Vec3d(
        m_target.x() + r * std::cos(m_theta),
        m_target.y() + r * std::sin(m_theta),
        m_target.z() + m_distance * m_zoom * std::cos(m_phi)
    );
}

Vec3d CameraController::get_dir_forward() const
{
    return (m_target - get_position()).normalized();
}

Vec3d CameraController::get_dir_right() const
{
    return get_dir_forward().cross(Vec3d::UnitZ()).normalized();
}

Vec3d CameraController::get_dir_up() const
{
    return get_dir_right().cross(get_dir_forward()).normalized();
}

double CameraController::get_view_angle() const
{
    return isOrtho.get() ? 0.0 : 45.0;  // perspective FOV
}

void CameraController::recalc()
{
    CameraState s;
    s.target   = m_target;
    s.zenith   = static_cast<float>(m_phi * 180.0 / M_PI);
    s.zoom     = m_zoom;
    s.distance = m_distance;
    s.theta    = m_theta;
    s.phi      = m_phi;
    state.set(s);
}

} // namespace Slic3r
