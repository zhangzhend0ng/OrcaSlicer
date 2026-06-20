#ifndef slic3r_App_ObjectViewModel_hpp_
#define slic3r_App_ObjectViewModel_hpp_

#include "libslic3r/MVVP.hpp"
#include "libslic3r/Point.hpp"

#include <string>

namespace Slic3r {

/// Per-object observable state.
/// Each model instance on the plate gets one ObjectViewModel.
/// Aggregated by PlaterViewModel.
class ObjectViewModel {
public:
    ObjectViewModel(int id, std::string name)
        : objectId(id), name(std::move(name)) {}

    const int         objectId;
    const std::string name;

    // ?? Observable State ??
    MVVP::Property<Vec3d>  position{Vec3d::Zero()};
    MVVP::Property<Vec3d>  scale{Vec3d(1.0, 1.0, 1.0)};
    MVVP::Property<Vec3d>  rotation{Vec3d::Zero()};
    MVVP::Property<bool>   isSelected{false};
    MVVP::Property<bool>   isVisible{true};
    MVVP::Property<bool>   isPrintable{true};
    MVVP::Property<int>    extruderIndex{0};
    MVVP::Property<std::string> filamentName{""};

    // ?? Commands ??
    MVVP::Command setPrintable{
        [this] { isPrintable.set(!isPrintable.get()); }
    };
    MVVP::Command toggleVisibility{
        [this] { isVisible.set(!isVisible.get()); }
    };
};

} // namespace Slic3r

#endif /* slic3r_App_ObjectViewModel_hpp_ */
