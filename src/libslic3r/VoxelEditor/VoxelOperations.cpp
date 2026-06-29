#include "VoxelEditor/VoxelOperations.hpp"
#include "VoxelEditor/Octree.hpp"
#include "VoxelEditor/VoxelGrid.hpp"

#include <cmath>
#include <stdexcept>

namespace Slic3r {
namespace VoxelOps {

// --- Template Generation ---

Octree make_box(const BoundingBoxf3& world_bbox, float voxel_size)
{
    Octree tree;
    tree.set_world_bbox(world_bbox);
    tree.fill_region(world_bbox, 1.0f);
    return tree;
}

Octree make_sphere(const BoundingBoxf3& world_bbox, float voxel_size)
{
    Vec3d center = world_bbox.center();
    double radius = std::min({world_bbox.size().x(), world_bbox.size().y(),
                               world_bbox.size().z()}) * 0.5;

    // Convert to a dense grid, fill sphere, convert back.
    VoxelGrid grid = VoxelGrid::from_bbox(world_bbox, voxel_size);
    double r2 = radius * radius;

    for (int32_t z = 0; z < grid.size_z(); ++z) {
        for (int32_t y = 0; y < grid.size_y(); ++y) {
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d p = grid.voxel_to_world(x, y, z);
                double dx = p.x() - center.x();
                double dy = p.y() - center.y();
                double dz = p.z() - center.z();
                if (dx*dx + dy*dy + dz*dz <= r2)
                    grid.at(x, y, z) = 1.0f;
            }
        }
    }
    return Octree::from_grid(grid);
}

Octree make_cylinder(const BoundingBoxf3& world_bbox, float voxel_size)
{
    Vec3d center = world_bbox.center();
    double radius = std::min(world_bbox.size().x(), world_bbox.size().y()) * 0.5;

    VoxelGrid grid = VoxelGrid::from_bbox(world_bbox, voxel_size);
    double r2 = radius * radius;

    for (int32_t z = 0; z < grid.size_z(); ++z) {
        for (int32_t y = 0; y < grid.size_y(); ++y) {
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d p = grid.voxel_to_world(x, y, z);
                double dx = p.x() - center.x();
                double dy = p.y() - center.y();
                if (dx*dx + dy*dy <= r2)
                    grid.at(x, y, z) = 1.0f;
            }
        }
    }
    return Octree::from_grid(grid);
}

Octree make_torus(const BoundingBoxf3& world_bbox, float voxel_size, float tube_radius)
{
    Vec3d center = world_bbox.center();
    double major_radius = std::min(world_bbox.size().x(), world_bbox.size().y()) * 0.5
                          - tube_radius;

    VoxelGrid grid = VoxelGrid::from_bbox(world_bbox, voxel_size);
    double tr2 = tube_radius * tube_radius;

    for (int32_t z = 0; z < grid.size_z(); ++z) {
        for (int32_t y = 0; y < grid.size_y(); ++y) {
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d p = grid.voxel_to_world(x, y, z);
                double dx = p.x() - center.x();
                double dy = p.y() - center.y();
                double dz = p.z() - center.z();
                // Distance from point to the torus ring in XY plane.
                double r_xy = std::sqrt(dx*dx + dy*dy);
                double dist2 = (r_xy - major_radius) * (r_xy - major_radius) + dz*dz;
                if (dist2 <= tr2)
                    grid.at(x, y, z) = 1.0f;
            }
        }
    }
    return Octree::from_grid(grid);
}

// --- Boolean Operations ---

Octree boolean_union(const Octree& a, const Octree& b, float voxel_size)
{
    VoxelGrid ga = a.to_grid(voxel_size);
    VoxelGrid gb = b.to_grid(voxel_size);
    // Align grids (use union of bounding boxes).
    BoundingBoxf3 ua = a.world_bbox();
    BoundingBoxf3 ub = b.world_bbox();
    BoundingBoxf3 combined(
        {std::min(ua.min.x(), ub.min.x()), std::min(ua.min.y(), ub.min.y()),
         std::min(ua.min.z(), ub.min.z())},
        {std::max(ua.max.x(), ub.max.x()), std::max(ua.max.y(), ub.max.y()),
         std::max(ua.max.z(), ub.max.z())}
    );
    VoxelGrid grid = VoxelGrid::from_bbox(combined, voxel_size);

    // Sample both octrees into the combined grid.
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d pt = grid.voxel_to_world(x, y, z);
                VoxelValue va = a.sample(pt);
                VoxelValue vb = b.sample(pt);
                grid.at(x, y, z) = std::max(va, vb);
            }
    return Octree::from_grid(grid);
}

Octree boolean_subtract(const Octree& a, const Octree& b, float voxel_size)
{
    VoxelGrid ga = a.to_grid(voxel_size);
    VoxelGrid gb = b.to_grid(voxel_size);
    ga.apply_op(gb, VoxelOp::Subtract);
    return Octree::from_grid(ga);
}

Octree boolean_intersect(const Octree& a, const Octree& b, float voxel_size)
{
    VoxelGrid ga = a.to_grid(voxel_size);
    VoxelGrid gb = b.to_grid(voxel_size);
    ga.apply_op(gb, VoxelOp::Intersect);
    return Octree::from_grid(ga);
}

// --- Region Operations ---

void region_fill(Octree& tree, const BoundingBoxf3& region, VoxelValue val)
{
    tree.fill_region(region, val);
}

// --- Shell / Hollow ---

Octree hollow(const Octree& tree, float wall_thickness_mm, float voxel_size)
{
    VoxelGrid grid = tree.to_grid(voxel_size);
    VoxelGrid shell(grid.size_x(), grid.size_y(), grid.size_z());

    // For each filled voxel, check if it's within wall_thickness of the surface.
    int wall_voxels = static_cast<int>(std::ceil(wall_thickness_mm / voxel_size));

    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                if (grid.at(x, y, z) < 0.5f) continue;

                // Check if any neighbor within wall_voxels is empty (surface).
                bool at_surface = false;
                for (int dz = -wall_voxels; dz <= wall_voxels && !at_surface; ++dz)
                    for (int dy = -wall_voxels; dy <= wall_voxels && !at_surface; ++dy)
                        for (int dx = -wall_voxels; dx <= wall_voxels && !at_surface; ++dx)
                            if (grid.at(x + dx, y + dy, z + dz) < 0.5f)
                                at_surface = true;

                if (at_surface)
                    shell.at(x, y, z) = 1.0f;
            }

    return Octree::from_grid(shell);
}

// --- Array / Pattern ---

Octree linear_array(const Octree& tree, const Vec3d& axis, int count,
                     float spacing_mm, float voxel_size)
{
    if (count <= 0) return Octree{};
    if (count == 1) { return Octree::from_grid(tree.to_grid(voxel_size)); }

    Vec3d dir = axis.normalized();
    VoxelGrid base = tree.to_grid(voxel_size);
    BoundingBoxf3 bbox = tree.world_bbox();
    Vec3d extent = bbox.size();

    // Compute the total bounding box for all copies.
    Vec3d total_extent = extent + dir * (spacing_mm * (count - 1));
    BoundingBoxf3 total_bbox(
        bbox.min.cwiseMin(bbox.min + dir * (spacing_mm * (count - 1))),
        bbox.max.cwiseMax(bbox.max + dir * (spacing_mm * (count - 1)))
    );
    // Pad slightly.
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
                    if (result.in_bounds(vc))
                        result.at(vc) = 1.0f;
                }
    }
    return Octree::from_grid(result);
}

Octree grid_array(const Octree& tree, int nx, int ny,
                   float spacing_x_mm, float spacing_y_mm,
                   float voxel_size)
{
    if (nx <= 0 || ny <= 0) return Octree{};
    if (nx == 1 && ny == 1) { return Octree::from_grid(tree.to_grid(voxel_size)); }

    VoxelGrid base = tree.to_grid(voxel_size);
    BoundingBoxf3 bbox = tree.world_bbox();

    BoundingBoxf3 total_bbox(
        bbox.min,
        {bbox.min.x() + spacing_x_mm * (nx - 1) + bbox.size().x(),
         bbox.min.y() + spacing_y_mm * (ny - 1) + bbox.size().y(),
         bbox.max.z()}
    );
    total_bbox.min -= Vec3d(voxel_size, voxel_size, voxel_size);
    total_bbox.max += Vec3d(voxel_size, voxel_size, voxel_size);

    VoxelGrid result = VoxelGrid::from_bbox(total_bbox, voxel_size);

    for (int iy = 0; iy < ny; ++iy)
        for (int ix = 0; ix < nx; ++ix) {
            Vec3d offset(spacing_x_mm * ix, spacing_y_mm * iy, 0.0);
            for (int32_t z = 0; z < base.size_z(); ++z)
                for (int32_t y = 0; y < base.size_y(); ++y)
                    for (int32_t x = 0; x < base.size_x(); ++x) {
                        if (base.at(x, y, z) < 0.5f) continue;
                        Vec3d pt = base.voxel_to_world(x, y, z) + offset;
                        VoxelCoord vc = result.world_to_voxel(pt);
                        if (result.in_bounds(vc))
                            result.at(vc) = 1.0f;
                    }
        }
    return Octree::from_grid(result);
}

// --- Smoothing ---

Octree smooth(const Octree& tree, int iterations, float voxel_size)
{
    VoxelGrid grid = tree.to_grid(voxel_size);

    for (int iter = 0; iter < iterations; ++iter) {
        VoxelGrid smoothed = grid; // copy

        for (int32_t z = 1; z < grid.size_z() - 1; ++z)
            for (int32_t y = 1; y < grid.size_y() - 1; ++y)
                for (int32_t x = 1; x < grid.size_x() - 1; ++x) {
                    // 3x3x3 box blur kernel.
                    float sum = 0.0f;
                    for (int dz = -1; dz <= 1; ++dz)
                        for (int dy = -1; dy <= 1; ++dy)
                            for (int dx = -1; dx <= 1; ++dx)
                                sum += grid.at(x + dx, y + dy, z + dz);
                    smoothed.at(x, y, z) = sum / 27.0f;
                }
        grid = std::move(smoothed);
    }

    // Threshold back to binary.
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
    BoundingBoxf3 region(
        {world_pos.x() - half, world_pos.y() - half, world_pos.z() - half},
        {world_pos.x() + half, world_pos.y() + half, world_pos.z() + half}
    );
    tree.fill_region(region, val);
}

// --- Brush Operations ---

void brush_sphere(Octree& tree, const Vec3d& center, float radius_mm, VoxelValue val)
{
    // Use the Octree's built-in sphere brush for the bounding box,
    // then refine with a dense grid for accuracy.
    BoundingBoxf3 region(
        {center.x() - radius_mm, center.y() - radius_mm, center.z() - radius_mm},
        {center.x() + radius_mm, center.y() + radius_mm, center.z() + radius_mm}
    );

    // For a precise sphere: voxelize the region and apply spherical mask.
    float vs = radius_mm * 0.1f; // fine resolution for brush
    VoxelGrid grid = VoxelGrid::from_bbox(region, vs);
    double r2 = radius_mm * radius_mm;

    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d p = grid.voxel_to_world(x, y, z);
                double dx = p.x() - center.x();
                double dy = p.y() - center.y();
                double dz = p.z() - center.z();
                if (dx*dx + dy*dy + dz*dz <= r2)
                    grid.at(x, y, z) = val;
            }

    // Merge the brush result into the octree.
    Octree brush_tree = Octree::from_grid(grid);
    tree.apply_op(brush_tree, VoxelOp::Union);
}

void brush_cube(Octree& tree, const Vec3d& center, float size_mm, VoxelValue val)
{
    float half = size_mm * 0.5f;
    BoundingBoxf3 region(
        {center.x() - half, center.y() - half, center.z() - half},
        {center.x() + half, center.y() + half, center.z() + half}
    );
    tree.fill_region(region, val);
}

// --- Utility ---

VoxelGrid to_grid(const Octree& tree, float voxel_size)
{
    return tree.to_grid(voxel_size);
}

OctreeStats stats(const Octree& tree)
{
    OctreeStats s;
    s.node_count  = tree.node_count();
    s.memory_bytes = tree.memory_bytes();
    s.world_bbox  = tree.world_bbox();
    s.max_depth   = Octree::MAX_DEPTH;
    return s;
}

} // namespace VoxelOps
} // namespace Slic3r
