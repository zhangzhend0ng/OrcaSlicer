#ifndef slic3r_App_ObjectValidationModel_hpp_
#define slic3r_App_ObjectValidationModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>

namespace Slic3r {

class ModelObject;
struct TriangleMeshStats;

/// Pure-C++ object/volume validation utilities.
/// Extracted from GUI_ObjectList.cpp and GCodeViewer.cpp.
/// Zero wxWidgets dependency.
class ObjectValidationModel {
public:
    // ?? From GUI_ObjectList.cpp ??

    /// Calculate total filament count based on physical count.
    static size_t totalFilamentsCount(size_t physicalCount);

    /// Get warning icon name for mesh quality issues.
    static std::string getWarningIconName(const TriangleMeshStats& stats);

    /// Check if volumes can be added to a ModelObject.
    static bool canAddVolumesToObject(const ModelObject* object);

    // ?? From GCodeViewer.cpp ??

    /// Round a float value to nearest binary fraction (power of 2).
    static float roundToBin(float value);

    /// Find the closest layer index for a given Z value within eps.
    static int findClosestLayerIndex(
        const std::vector<double>& zs, double z, double eps);

    // ?? Observable State ??

    struct MeshWarning {
        int objectId{-1};
        int volumeId{-1};
        std::string iconName;
        std::string message;
    };

    MVVP::Property<std::vector<MeshWarning>> meshWarnings{{}};

    // ?? From GCodeViewer.cpp: GCode move type ? buffer ID ??
    static unsigned char moveTypeToBufferId(int moveType);
    static int bufferIdToMoveType(unsigned char id);
};

} // namespace Slic3r

#endif /* slic3r_App_ObjectValidationModel_hpp_ */
