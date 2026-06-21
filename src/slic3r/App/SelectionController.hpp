#ifndef slic3r_App_SelectionController_hpp_
#define slic3r_App_SelectionController_hpp_

#include "libslic3r/MVVP.hpp"
#include "libslic3r/Point.hpp"
#include "libslic3r/ObjectID.hpp"

#include <vector>
#include <set>
#include <optional>

namespace Slic3r {


/// Selection mode.
enum class SelectionMode {
    Object,     // whole object selection
    Vertex,     // per-vertex editing
    Edge,       // per-edge editing
    Face,       // per-face editing
};

/// Snapshot of current selection state.
struct SelectionState {
    std::set<ObjectID>  selected_ids;
    SelectionMode       mode{SelectionMode::Object};
    std::optional<Vec3d> hovered_world_pos;
    bool                is_dragging{false};

    
};

/// Pure-C++ selection controller with MVVP interface.
/// Handles picking, multi-select, transform logic.
/// Zero dependency on OpenGL or wxWidgets.
class SelectionController {
public:
    // ?? Observable State ??
    MVVP::Property<SelectionState> state{SelectionState{}};
    MVVP::Property<ObjectID>  highlightedObject{ObjectID()};
    MVVP::Property<bool>           hasSelection{false};

    // ?? Discrete Commands ??
    MVVP::Command selectAll{
        [this] { select_all(); },
        [this] { return !selectable_ids_.empty(); }
    };
    MVVP::Command deselectAll{
        [this] { deselect_all(); },
        [this] { return hasSelection.get(); }
    };
    MVVP::Command deleteSelected{
        [this] { delete_selected(); },
        [this] { return hasSelection.get(); }
    };
    MVVP::Command duplicateSelected{
        [this] { duplicate_selected(); },
        [this] { return hasSelection.get(); }
    };

    // ?? Continuous Input (called from View at 60fps) ??
    void onMouseDown(int screen_x, int screen_y, bool shift_held);
    void onMouseMove(int screen_x, int screen_y);
    void onMouseUp();

    // ?? Hit-testing (View provides screen?world mapping) ??
    void register_selectable(ObjectID id, const Vec3d& world_center, double radius);
    void clear_selectables();
    std::optional<ObjectID> hit_test(const Vec3d& ray_origin, const Vec3d& ray_dir) const;

    // ?? Hover ??
    void set_hovered(int id);
    void clear_hover();
    void set_hovered_id(int id);

private:
    void select_all();
    void deselect_all();
    void delete_selected();
    void duplicate_selected();
    void recalc();

    struct Selectable {
        ObjectID id;
        Vec3d    center;
        double   radius;
    };
    std::vector<Selectable> selectable_ids_;

    // Drag state
    bool     m_dragging{false};
    int      m_drag_start_x{0}, m_drag_start_y{0};
};

} // namespace Slic3r

#endif /* slic3r_App_SelectionController_hpp_ */
