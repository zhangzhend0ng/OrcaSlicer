#ifndef slic3r_VoxelGrid_hpp_
#define slic3r_VoxelGrid_hpp_

#include "VoxelEditor/VoxelTypes.hpp"

#include <vector>
#include <cstdint>
#include <cstring>
#include <functional>

namespace Slic3r {

// Dense 3D voxel grid stored as a flat array of VoxelValue.
// Supports O(1) random access, suitable for small-to-medium models
// or as an intermediate representation during mesh voxelization.
class VoxelGrid {
public:
    VoxelGrid() = default;

    // Create a grid with given dimensions in voxel units.
    VoxelGrid(int32_t size_x, int32_t size_y, int32_t size_z, VoxelValue init_val = 0.0f)
        : m_dims(size_x, size_y, size_z)
    {
        m_data.resize(static_cast<size_t>(size_x) * size_y * size_z, init_val);
    }

    // Create a grid that covers the given world-space bounding box at the specified voxel size.
    // physical_bbox: model bounds in mm. voxel_size: edge length of one voxel in mm.
    static VoxelGrid from_bbox(const BoundingBoxf3& physical_bbox, float voxel_size, VoxelValue init_val = 0.0f);

    // --- Accessors ---
    const VoxelCoord& dims() const { return m_dims; }
    int32_t size_x() const { return m_dims.x(); }
    int32_t size_y() const { return m_dims.y(); }
    int32_t size_z() const { return m_dims.z(); }
    int64_t total_voxels() const { return static_cast<int64_t>(m_dims.x()) * m_dims.y() * m_dims.z(); }

    float voxel_size_mm() const { return m_voxel_size; }
    void set_origin(const Vec3d& o) { m_origin = o; }
    void set_voxel_size(float vs) { m_voxel_size = vs; }

    // Physical world offset of voxel (0,0,0) in mm.
    const Vec3d& origin_mm() const { return m_origin; }

    // Get/set voxel value at integer coordinate.
    VoxelValue  at(int32_t x, int32_t y, int32_t z) const;
    VoxelValue& at(int32_t x, int32_t y, int32_t z);

    VoxelValue  at(const VoxelCoord& c) const { return at(c.x(), c.y(), c.z()); }
    VoxelValue& at(const VoxelCoord& c)       { return at(c.x(), c.y(), c.z()); }

    // Check if a coordinate is within bounds.
    bool in_bounds(int32_t x, int32_t y, int32_t z) const;
    bool in_bounds(const VoxelCoord& c) const { return in_bounds(c.x(), c.y(), c.z()); }

    // --- Bulk operations ---
    void fill(VoxelValue val);
    void fill_region(const VoxelBBox& region, VoxelValue val);

    // Clear the grid (set all to 0).
    void clear() { fill(0.0f); }

    // --- Boolean operations ---
    // Apply a boolean operation between this grid and another.
    // The other grid must have the same dimensions and origin.
    void apply_op(const VoxelGrid& other, VoxelOp op);

    // --- Slice extraction ---
    // Extract a single horizontal layer (z-slice) as a 2D bitmap.
    VoxelLayer extract_layer(int32_t z) const;

    // --- Physical coordinate conversion ---
    Vec3d      voxel_to_world(int32_t x, int32_t y, int32_t z) const;
    VoxelCoord world_to_voxel(const Vec3d& world) const;

    // --- Data access ---
    const VoxelValue* data() const { return m_data.data(); }
    VoxelValue*       data()       { return m_data.data(); }

    // --- Memory ---
    size_t memory_bytes() const { return m_data.size() * sizeof(VoxelValue); }

private:
    VoxelCoord            m_dims{0, 0, 0};
    Vec3d                 m_origin{0.0, 0.0, 0.0};
    float                 m_voxel_size = 1.0f;
    std::vector<VoxelValue> m_data;
};

} // namespace Slic3r

#endif // slic3r_VoxelGrid_hpp_
