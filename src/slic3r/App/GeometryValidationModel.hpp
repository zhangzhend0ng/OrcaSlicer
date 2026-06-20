#ifndef slic3r_App_GeometryValidationModel_hpp_
#define slic3r_App_GeometryValidationModel_hpp_

#include "libslic3r/MVVP.hpp"
#include "libslic3r/Point.hpp"

#include <Eigen/Geometry>
#include <string>

namespace Slic3r {

/// Pure-C++ geometry/transform validation utilities.
/// Extracted from:
///   - Selection.cpp: is_left_handed(), is_rotation_xy_synchronized()
///   - GUI_App.cpp: convert_studio_language_to_api()
/// Zero wxWidgets dependency. All functions are static and stateless.
class GeometryValidationModel {
public:
    // ?? Transform validation (from Selection.cpp) ??

    /// Check if a 3x3 linear transform is left-handed (negative determinant).
    static bool isLeftHanded(const Transform3d::ConstLinearPart& m);

    /// Check if a full 3D transform is left-handed.
    static bool isLeftHanded(const Transform3d& m);

    /// Verify that two rotation transforms differ only by Z-axis rotation.
    /// Used to validate that object instances have synchronized XY rotation.
    static bool isRotationXYSynchronized(
        const Transform3d& rot_xyz_from,
        const Transform3d& rot_xyz_to);

    // ?? String utilities (from GUI_App.cpp) ??

    /// Convert locale code from underscore format to hyphen format.
    /// e.g., "zh_CN" -> "zh-CN"
    static std::string localeToApiFormat(std::string langCode);

    /// Decode binary path data from extra string (UPX-encoded).
    /// From GUI_App.cpp L1372. Pure byte manipulation, no wx types.
    static std::string decodePathExtra(const std::string& extra);

    // ?? From Mouse3DController.cpp: 3D mouse input conversion ??
    static double convert3DConnexionInput(int coordLow, int coordHigh, double deadzone);
    static double convertSpaceNavInput(int value);
};

} // namespace Slic3r

#endif /* slic3r_App_GeometryValidationModel_hpp_ */
