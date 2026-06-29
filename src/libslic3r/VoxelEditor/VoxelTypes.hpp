#ifndef slic3r_VoxelTypes_hpp_
#define slic3r_VoxelTypes_hpp_

#include "libslic3r.h"
#include "Point.hpp"
#include "BoundingBox.hpp"

#include <cstdint>
#include <vector>
#include <array>
#include <algorithm>
#include <functional>

namespace Slic3r {

using VoxelCoord = Vec3i32;
using VoxelValue = float;
using VoxelBlock = Vec3i32;

class VoxelBBox {
public:
    VoxelCoord min{0, 0, 0};
    VoxelCoord max{0, 0, 0};

    VoxelBBox() = default;
    VoxelBBox(const VoxelCoord& min_, const VoxelCoord& max_) : min(min_), max(max_) {}

    bool contains(const VoxelCoord& p) const {
        return p.x() >= min.x() && p.y() >= min.y() && p.z() >= min.z()
            && p.x() <= max.x() && p.y() <= max.y() && p.z() <= max.z();
    }

    VoxelCoord size() const { return {max.x() - min.x() + 1, max.y() - min.y() + 1, max.z() - min.z() + 1}; }
    int64_t volume() const {
        VoxelCoord s = size();
        return static_cast<int64_t>(s.x()) * s.y() * s.z();
    }
    bool empty() const { return max.x() < min.x() || max.y() < min.y() || max.z() < min.z(); }

    void extend(const VoxelCoord& p) {
        if (empty()) { min = p; max = p; return; }
        min.x() = std::min(min.x(), p.x());
        min.y() = std::min(min.y(), p.y());
        min.z() = std::min(min.z(), p.z());
        max.x() = std::max(max.x(), p.x());
        max.y() = std::max(max.y(), p.y());
        max.z() = std::max(max.z(), p.z());
    }

    void extend(const VoxelBBox& other) {
        if (other.empty()) return;
        extend(other.min);
        extend(other.max);
    }

    bool operator==(const VoxelBBox& o) const { return min == o.min && max == o.max; }
    bool operator!=(const VoxelBBox& o) const { return !(*this == o); }
};

class VoxelLayer {
public:
    int32_t width  = 0;
    int32_t height = 0;
    std::vector<VoxelValue> pixels;

    VoxelLayer() = default;
    VoxelLayer(int32_t w, int32_t h) : width(w), height(h), pixels(w * h, 0.0f) {}
    VoxelValue  at(int32_t x, int32_t y) const { return pixels[y * width + x]; }
    VoxelValue& at(int32_t x, int32_t y)       { return pixels[y * width + x]; }
    void fill(VoxelValue v) { std::fill(pixels.begin(), pixels.end(), v); }
    bool empty() const { return pixels.empty(); }
    size_t size_bytes() const { return pixels.size() * sizeof(VoxelValue); }
};

enum class VoxelOp : uint8_t { Union, Subtract, Intersect, Replace };
enum class VoxelNodeState : uint8_t { Empty = 0, Filled = 1, Mixed = 2, Partial = 3 };

inline int64_t voxel_index(const VoxelCoord& c, const VoxelCoord& dims) {
    return static_cast<int64_t>(c.z()) * dims.y() * dims.x()
         + static_cast<int64_t>(c.y()) * dims.x() + c.x();
}

inline VoxelCoord voxel_coord(int64_t idx, const VoxelCoord& dims) {
    int32_t xy = dims.x() * dims.y();
    int32_t z  = static_cast<int32_t>(idx / xy);
    int32_t r  = static_cast<int32_t>(idx % xy);
    int32_t y  = r / dims.x();
    int32_t x  = r % dims.x();
    return {x, y, z};
}

} // namespace Slic3r

#endif // slic3r_VoxelTypes_hpp_
