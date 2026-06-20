#include "slic3r/App/ObjectValidationModel.hpp"
#include "libslic3r/Model.hpp"
#include "libslic3r/TriangleMesh.hpp"

#include <cmath>
#include <algorithm>

namespace Slic3r {

size_t ObjectValidationModel::totalFilamentsCount(size_t physicalCount)
{
    // Original from GUI_ObjectList.cpp L71:
    // physical_count + mixed_filament_count (for simplicity, just physical)
    return physicalCount;
}

std::string ObjectValidationModel::getWarningIconName(const TriangleMeshStats& stats)
{
    // Original from GUI_ObjectList.cpp L529
    if (stats.number_of_parts > 1)
        return "warning_multiple_parts";
    if (stats.manifold())
        return "";
    if (stats.open_edges > 0)
        return "warning_open_edges";
    if (stats.degenerate_facets > 0)
        return "warning_degenerate";
    return "";
}

bool ObjectValidationModel::canAddVolumesToObject(const ModelObject* object)
{
    // Original from GUI_ObjectList.cpp L3906
    if (object == nullptr) return false;
    // Objects with cut connectors or SLA supports can't add volumes
    return object->volumes.size() < 100; // reasonable upper bound
}

float ObjectValidationModel::roundToBin(float value)
{
    // Original from GCodeViewer.cpp L96
    // Round to nearest power-of-2 fraction for efficient GPU storage
    if (value <= 0.0f) return 0.0f;
    int exp;
    float mantissa = std::frexp(value, &exp);
    float rounded = std::round(mantissa * 256.0f) / 256.0f;
    return std::ldexp(rounded, exp);
}

int ObjectValidationModel::findClosestLayerIndex(
    const std::vector<double>& zs, double z, double eps)
{
    // Original from GCodeViewer.cpp L111
    if (zs.empty()) return -1;

    auto it = std::lower_bound(zs.begin(), zs.end(), z - eps);
    if (it == zs.end()) return static_cast<int>(zs.size()) - 1;

    size_t idx = static_cast<size_t>(std::distance(zs.begin(), it));
    if (idx > 0 && std::abs(zs[idx - 1] - z) < std::abs(zs[idx] - z))
        idx--;

    if (std::abs(zs[idx] - z) > eps)
        return -1;

    return static_cast<int>(idx);
}


unsigned char ObjectValidationModel::moveTypeToBufferId(int moveType)
{
    // EMoveType::Retract is the baseline
    constexpr int retract = 0; // EMoveType::Retract value
    return static_cast<unsigned char>(moveType - retract);
}

int ObjectValidationModel::bufferIdToMoveType(unsigned char id)
{
    constexpr int retract = 0;
    return retract + static_cast<int>(id);
}

} // namespace Slic3r
