#include "VoxelEditor/VoxelGrid.hpp"

#include <cmath>
#include <stdexcept>

namespace Slic3r {

VoxelGrid VoxelGrid::from_bbox(const BoundingBoxf3& physical_bbox, float voxel_size, VoxelValue init_val)
{
    if (voxel_size <= 0.0f)
        throw std::invalid_argument("VoxelGrid::from_bbox: voxel_size must be positive");

    Vec3d size_mm = physical_bbox.size();
    int32_t sx = static_cast<int32_t>(std::ceil(size_mm.x() / voxel_size)) + 1;
    int32_t sy = static_cast<int32_t>(std::ceil(size_mm.y() / voxel_size)) + 1;
    int32_t sz = static_cast<int32_t>(std::ceil(size_mm.z() / voxel_size)) + 1;

    VoxelGrid grid(sx, sy, sz, init_val);
    grid.m_origin     = physical_bbox.min;
    grid.m_voxel_size = voxel_size;
    return grid;
}

VoxelValue VoxelGrid::at(int32_t x, int32_t y, int32_t z) const
{
    if (!in_bounds(x, y, z)) return 0.0f;
    int64_t idx = static_cast<int64_t>(z) * m_dims.y() * m_dims.x()
                + static_cast<int64_t>(y) * m_dims.x() + x;
    return m_data[static_cast<size_t>(idx)];
}

VoxelValue& VoxelGrid::at(int32_t x, int32_t y, int32_t z)
{
    if (!in_bounds(x, y, z))
        throw std::out_of_range("VoxelGrid::at: coordinate out of bounds");
    int64_t idx = static_cast<int64_t>(z) * m_dims.y() * m_dims.x()
                + static_cast<int64_t>(y) * m_dims.x() + x;
    return m_data[static_cast<size_t>(idx)];
}

bool VoxelGrid::in_bounds(int32_t x, int32_t y, int32_t z) const
{
    return x >= 0 && x < m_dims.x()
        && y >= 0 && y < m_dims.y()
        && z >= 0 && z < m_dims.z();
}

void VoxelGrid::fill(VoxelValue val)
{
    std::fill(m_data.begin(), m_data.end(), val);
}

void VoxelGrid::fill_region(const VoxelBBox& region, VoxelValue val)
{
    VoxelBBox clamped{
        {std::max(0, region.min.x()), std::max(0, region.min.y()), std::max(0, region.min.z())},
        {std::min(m_dims.x() - 1, region.max.x()),
         std::min(m_dims.y() - 1, region.max.y()),
         std::min(m_dims.z() - 1, region.max.z())}
    };
    if (clamped.empty()) return;

    for (int32_t z = clamped.min.z(); z <= clamped.max.z(); ++z)
        for (int32_t y = clamped.min.y(); y <= clamped.max.y(); ++y)
            for (int32_t x = clamped.min.x(); x <= clamped.max.x(); ++x)
                at(x, y, z) = val;
}

void VoxelGrid::apply_op(const VoxelGrid& other, VoxelOp op)
{
    if (other.m_dims != m_dims)
        throw std::invalid_argument("VoxelGrid::apply_op: grids must have identical dimensions");

    const size_t count = m_data.size();
    switch (op) {
    case VoxelOp::Union:
        for (size_t i = 0; i < count; ++i)
            m_data[i] = std::max(m_data[i], other.m_data[i]);
        break;
    case VoxelOp::Subtract:
        for (size_t i = 0; i < count; ++i)
            if (other.m_data[i] > 0.5f) m_data[i] = 0.0f;
        break;
    case VoxelOp::Intersect:
        for (size_t i = 0; i < count; ++i)
            m_data[i] = std::min(m_data[i], other.m_data[i]);
        break;
    case VoxelOp::Replace:
        std::copy(other.m_data.begin(), other.m_data.end(), m_data.begin());
        break;
    }
}

VoxelLayer VoxelGrid::extract_layer(int32_t z) const
{
    if (z < 0 || z >= m_dims.z())
        throw std::out_of_range("VoxelGrid::extract_layer: z out of range");

    VoxelLayer layer(m_dims.x(), m_dims.y());
    for (int32_t y = 0; y < m_dims.y(); ++y)
        for (int32_t x = 0; x < m_dims.x(); ++x)
            layer.at(x, y) = at(x, y, z);
    return layer;
}

Vec3d VoxelGrid::voxel_to_world(int32_t x, int32_t y, int32_t z) const
{
    return {
        m_origin.x() + (x + 0.5) * m_voxel_size,
        m_origin.y() + (y + 0.5) * m_voxel_size,
        m_origin.z() + (z + 0.5) * m_voxel_size
    };
}

VoxelCoord VoxelGrid::world_to_voxel(const Vec3d& world) const
{
    return {
        static_cast<int32_t>(std::floor((world.x() - m_origin.x()) / m_voxel_size)),
        static_cast<int32_t>(std::floor((world.y() - m_origin.y()) / m_voxel_size)),
        static_cast<int32_t>(std::floor((world.z() - m_origin.z()) / m_voxel_size))
    };
}

} // namespace Slic3r
