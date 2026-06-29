#include "VoxelEditor/VoxelOperations.hpp"
#include "VoxelEditor/Octree.hpp"
#include "VoxelEditor/VoxelGrid.hpp"

#include <cmath>
#include <stdexcept>

namespace Slic3r {
namespace VoxelOps {

// All template functions now use the same pattern: create a VoxelGrid, fill,
// then convert to Octree. This ensures consistent world_bbox dimensions.

Octree make_box(const BoundingBoxf3& world_bbox, float voxel_size)
{
    VoxelGrid grid = VoxelGrid::from_bbox(world_bbox, voxel_size);
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x)
                grid.at(x, y, z) = 1.0f;
    return Octree::from_grid(grid);
}

Octree make_sphere(const BoundingBoxf3& world_bbox, float voxel_size)
{
    Vec3d center = world_bbox.center();
    double radius = std::min({world_bbox.size().x(), world_bbox.size().y(),
                               world_bbox.size().z()}) * 0.5;
    VoxelGrid grid = VoxelGrid::from_bbox(world_bbox, voxel_size);
    double r2 = radius * radius;
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d p = grid.voxel_to_world(x, y, z);
                double dx = p.x() - center.x(), dy = p.y() - center.y(), dz = p.z() - center.z();
                if (dx*dx + dy*dy + dz*dz <= r2) grid.at(x, y, z) = 1.0f;
            }
    return Octree::from_grid(grid);
}

Octree make_cylinder(const BoundingBoxf3& world_bbox, float voxel_size)
{
    Vec3d center = world_bbox.center();
    double radius = std::min(world_bbox.size().x(), world_bbox.size().y()) * 0.5;
    VoxelGrid grid = VoxelGrid::from_bbox(world_bbox, voxel_size);
    double r2 = radius * radius;
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d p = grid.voxel_to_world(x, y, z);
                double dx = p.x() - center.x(), dy = p.y() - center.y();
                if (dx*dx + dy*dy <= r2) grid.at(x, y, z) = 1.0f;
            }
    return Octree::from_grid(grid);
}

Octree make_torus(const BoundingBoxf3& world_bbox, float voxel_size, float tube_radius)
{
    Vec3d center = world_bbox.center();
    double major_radius = std::min(world_bbox.size().x(), world_bbox.size().y()) * 0.5 - tube_radius;
    VoxelGrid grid = VoxelGrid::from_bbox(world_bbox, voxel_size);
    double tr2 = tube_radius * tube_radius;
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d p = grid.voxel_to_world(x, y, z);
                double dx = p.x() - center.x(), dy = p.y() - center.y(), dz = p.z() - center.z();
                double r_xy = std::sqrt(dx*dx + dy*dy);
                double dist2 = (r_xy - major_radius) * (r_xy - major_radius) + dz*dz;
                if (dist2 <= tr2) grid.at(x, y, z) = 1.0f;
            }
    return Octree::from_grid(grid);
}

// --- Boolean Operations ---

Octree boolean_union(const Octree& a, const Octree& b, float voxel_size)
{
    BoundingBoxf3 ua = a.world_bbox(), ub = b.world_bbox();
    BoundingBoxf3 combined(
        {std::min(ua.min.x(), ub.min.x()), std::min(ua.min.y(), ub.min.y()), std::min(ua.min.z(), ub.min.z())},
        {std::max(ua.max.x(), ub.max.x()), std::max(ua.max.y(), ub.max.y()), std::max(ua.max.z(), ub.max.z())}
    );
    VoxelGrid grid = VoxelGrid::from_bbox(combined, voxel_size);
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d pt = grid.voxel_to_world(x, y, z);
                grid.at(x, y, z) = std::max(a.sample(pt), b.sample(pt));
            }
    return Octree::from_grid(grid);
}

Octree boolean_subtract(const Octree& a, const Octree& b, float voxel_size)
{
    BoundingBoxf3 ua = a.world_bbox(), ub = b.world_bbox();
    BoundingBoxf3 combined(
        {std::min(ua.min.x(), ub.min.x()), std::min(ua.min.y(), ub.min.y()), std::min(ua.min.z(), ub.min.z())},
        {std::max(ua.max.x(), ub.max.x()), std::max(ua.max.y(), ub.max.y()), std::max(ua.max.z(), ub.max.z())}
    );
    VoxelGrid grid = VoxelGrid::from_bbox(combined, voxel_size);
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d pt = grid.voxel_to_world(x, y, z);
                VoxelValue va = a.sample(pt), vb = b.sample(pt);
                grid.at(x, y, z) = (va >= 0.5f && vb < 0.5f) ? 1.0f : 0.0f;
            }
    return Octree::from_grid(grid);
}

Octree boolean_intersect(const Octree& a, const Octree& b, float voxel_size)
{
    BoundingBoxf3 ua = a.world_bbox(), ub = b.world_bbox();
    BoundingBoxf3 combined(
        {std::min(ua.min.x(), ub.min.x()), std::min(ua.min.y(), ub.min.y()), std::min(ua.min.z(), ub.min.z())},
        {std::max(ua.max.x(), ub.max.x()), std::max(ua.max.y(), ub.max.y()), std::max(ua.max.z(), ub.max.z())}
    );
    VoxelGrid grid = VoxelGrid::from_bbox(combined, voxel_size);
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d pt = grid.voxel_to_world(x, y, z);
                grid.at(x, y, z) = std::min(a.sample(pt), b.sample(pt));
            }
    return Octree::from_grid(grid);
}

// --- Region Operations ---

void region_fill(Octree& tree, const BoundingBoxf3& region, VoxelValue val) { tree.fill_region(region, val); }

// --- Shell / Hollow ---

Octree hollow(const Octree& tree, float wall_thickness_mm, float voxel_size)
{
    VoxelGrid grid = tree.to_grid(voxel_size);
    VoxelGrid shell(grid.size_x(), grid.size_y(), grid.size_z());
    shell.set_origin(grid.origin_mm());
    shell.set_voxel_size(grid.voxel_size_mm());
    int wall_voxels = static_cast<int>(std::ceil(wall_thickness_mm / voxel_size));
    const VoxelGrid& cgrid = grid;
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                if (cgrid.at(x, y, z) < 0.5f) continue;
                bool at_surface = false;
                for (int dz = -wall_voxels; dz <= wall_voxels && !at_surface; ++dz)
                    for (int dy = -wall_voxels; dy <= wall_voxels && !at_surface; ++dy)
                        for (int dx = -wall_voxels; dx <= wall_voxels && !at_surface; ++dx)
                            if (cgrid.at(x + dx, y + dy, z + dz) < 0.5f) at_surface = true;
                if (at_surface) shell.at(x, y, z) = 1.0f;
            }
    return Octree::from_grid(shell);
}

// --- Array / Pattern ---

Octree linear_array(const Octree& tree, const Vec3d& axis, int count, float spacing_mm, float voxel_size)
{
    if (count <= 0) return Octree{};
    if (count == 1) return Octree::from_grid(tree.to_grid(voxel_size));
    Vec3d dir = axis.normalized();
    VoxelGrid base = tree.to_grid(voxel_size);
    BoundingBoxf3 bbox = tree.world_bbox();
    BoundingBoxf3 total_bbox(
        bbox.min.cwiseMin(bbox.min + dir * (spacing_mm * (count - 1))),
        bbox.max.cwiseMax(bbox.max + dir * (spacing_mm * (count - 1)))
    );
    total_bbox.min -= Vec3d(voxel_size, voxel_size, voxel_size);
    total_bbox.max += Vec3d(voxel_size, voxel_size, voxel_size);
    VoxelGrid result = VoxelGrid::from_bbox(total_bbox, voxel_size);
    for (int i = 0; i < count; ++i) {
        Vec3d offset = dir * (spacing_mm * i);
        for (int32_t z = 0; z < base.size_z(); ++z)
            for (int32_t y = 0; y < base.size_y(); ++y)
                for (int32_t x = 0; x < base.size_x(); ++x) {
                    if (base.at(x, y, z) < 0.5f) continue;
                    Vec3d pt = base.voxel_to_world(x, y, z) + offset;
                    VoxelCoord vc = result.world_to_voxel(pt);
                    if (result.in_bounds(vc)) result.at(vc) = 1.0f;
                }
    }
    return Octree::from_grid(result);
}

Octree grid_array(const Octree& tree, int nx, int ny, float sx_mm, float sy_mm, float voxel_size)
{
    if (nx <= 0 || ny <= 0) return Octree{};
    if (nx == 1 && ny == 1) return Octree::from_grid(tree.to_grid(voxel_size));
    VoxelGrid base = tree.to_grid(voxel_size);
    BoundingBoxf3 bbox = tree.world_bbox();
    BoundingBoxf3 total_bbox(bbox.min,
        {bbox.min.x() + sx_mm * (nx - 1) + bbox.size().x(),
         bbox.min.y() + sy_mm * (ny - 1) + bbox.size().y(), bbox.max.z()});
    total_bbox.min -= Vec3d(voxel_size, voxel_size, voxel_size);
    total_bbox.max += Vec3d(voxel_size, voxel_size, voxel_size);
    VoxelGrid result = VoxelGrid::from_bbox(total_bbox, voxel_size);
    for (int iy = 0; iy < ny; ++iy)
        for (int ix = 0; ix < nx; ++ix) {
            Vec3d offset(sx_mm * ix, sy_mm * iy, 0.0);
            for (int32_t z = 0; z < base.size_z(); ++z)
                for (int32_t y = 0; y < base.size_y(); ++y)
                    for (int32_t x = 0; x < base.size_x(); ++x) {
                        if (base.at(x, y, z) < 0.5f) continue;
                        Vec3d pt = base.voxel_to_world(x, y, z) + offset;
                        VoxelCoord vc = result.world_to_voxel(pt);
                        if (result.in_bounds(vc)) result.at(vc) = 1.0f;
                    }
        }
    return Octree::from_grid(result);
}

// --- Smoothing ---

Octree smooth(const Octree& tree, int iterations, float voxel_size)
{
    VoxelGrid grid = tree.to_grid(voxel_size);
    for (int iter = 0; iter < iterations; ++iter) {
        VoxelGrid smoothed = grid;
        const VoxelGrid& cgrid = grid;
        for (int32_t z = 1; z < grid.size_z() - 1; ++z)
            for (int32_t y = 1; y < grid.size_y() - 1; ++y)
                for (int32_t x = 1; x < grid.size_x() - 1; ++x) {
                    float sum = 0.0f;
                    for (int dz = -1; dz <= 1; ++dz)
                        for (int dy = -1; dy <= 1; ++dy)
                            for (int dx = -1; dx <= 1; ++dx)
                                sum += cgrid.at(x + dx, y + dy, z + dz);
                    smoothed.at(x, y, z) = sum / 27.0f;
                }
        grid = std::move(smoothed);
    }
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x)
                grid.at(x, y, z) = (grid.at(x, y, z) >= 0.5f) ? 1.0f : 0.0f;
    return Octree::from_grid(grid);
}

// --- Block-level Operations ---

void place_block(Octree& tree, const Vec3d& world_pos, float size_mm, VoxelValue val)
{
    float half = size_mm * 0.5f;
    tree.fill_region(BoundingBoxf3({world_pos.x()-half, world_pos.y()-half, world_pos.z()-half},
                                    {world_pos.x()+half, world_pos.y()+half, world_pos.z()+half}), val);
}

// --- Brush Operations ---

void brush_sphere(Octree& tree, const Vec3d& center, float radius_mm, VoxelValue val)
{
    BoundingBoxf3 region({center.x()-radius_mm, center.y()-radius_mm, center.z()-radius_mm},
                          {center.x()+radius_mm, center.y()+radius_mm, center.z()+radius_mm});
    float vs = radius_mm * 0.1f;
    VoxelGrid grid = VoxelGrid::from_bbox(region, vs);
    double r2 = radius_mm * radius_mm;
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d p = grid.voxel_to_world(x, y, z);
                double dx = p.x()-center.x(), dy = p.y()-center.y(), dz = p.z()-center.z();
                if (dx*dx + dy*dy + dz*dz <= r2) grid.at(x, y, z) = val;
            }
    Octree brush_tree = Octree::from_grid(grid);
    tree.apply_op(brush_tree, VoxelOp::Union);
}

void brush_cube(Octree& tree, const Vec3d& center, float size_mm, VoxelValue val)
{
    float half = size_mm * 0.5f;
    tree.fill_region(BoundingBoxf3({center.x()-half, center.y()-half, center.z()-half},
                                    {center.x()+half, center.y()+half, center.z()+half}), val);
}

// --- Utility ---

VoxelGrid to_grid(const Octree& tree, float voxel_size) { return tree.to_grid(voxel_size); }

OctreeStats stats(const Octree& tree)
{
    OctreeStats s;
    s.node_count = tree.node_count();
    s.memory_bytes = tree.memory_bytes();
    s.world_bbox = tree.world_bbox();
    s.max_depth = Octree::MAX_DEPTH;
    return s;
}

} // namespace VoxelOps
} // namespace Slic3r
