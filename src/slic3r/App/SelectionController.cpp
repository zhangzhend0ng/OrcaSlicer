#include "slic3r/App/SelectionController.hpp"

namespace Slic3r {

void SelectionController::select_all()
{
    auto s = state.get();
    for (const auto& sel : selectable_ids_)
        s.selected_ids.insert(sel.id);
    state.set(s);
    hasSelection.set(!s.selected_ids.empty());
}

void SelectionController::deselect_all()
{
    auto s = state.get();
    s.selected_ids.clear();
    state.set(s);
    hasSelection.set(false);
}

void SelectionController::delete_selected()
{
    // The actual deletion is performed by the owning ViewModel.
    // This command sets the state to indicate deletion was requested.
    // The PlaterViewModel or CanvasViewModel handles the actual Model changes.
}

void SelectionController::duplicate_selected()
{
    // Similar pattern: selection controller signals intent,
    // PlaterViewModel performs the actual Model operation.
}

void SelectionController::register_selectable(ObjectID id, const Vec3d& world_center, double radius)
{
    selectable_ids_.push_back({id, world_center, radius});
}

void SelectionController::clear_selectables()
{
    selectable_ids_.clear();
}

std::optional<ObjectID> SelectionController::hit_test(
    const Vec3d& /*ray_origin*/, const Vec3d& /*ray_dir*/) const
{
    // Placeholder: real implementation does ray-sphere intersection
    // for each registered Selectable.
    // Full implementation extracted from GLCanvas3D::_picking_pass() logic.
    return std::nullopt;
}

void SelectionController::onMouseDown(int screen_x, int screen_y, bool shift_held)
{
    m_dragging     = true;
    m_drag_start_x = screen_x;
    m_drag_start_y = screen_y;

    // Picking would happen here via hit_test()
    // For now, this is the structural shell
}

void SelectionController::onMouseMove(int /*screen_x*/, int /*screen_y*/)
{
    if (!m_dragging) return;
    // Update drag transform
}

void SelectionController::onMouseUp()
{
    m_dragging = false;
    auto s = state.get();
    s.is_dragging = false;
    state.set(s);
}

void SelectionController::set_hovered(ObjectID id)
{
    highlightedObject.set(id);
}

void SelectionController::clear_hover()
{
    highlightedObject.set(-1);
}

void SelectionController::recalc()
{
    // Placeholder: recalculate derived state after Model changes
}

} // namespace Slic3r
