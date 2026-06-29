#include "VoxelEditor/MeshVoxelizer.hpp"
#include "VoxelEditor/VoxelGrid.hpp"
#include "VoxelEditor/Octree.hpp"
#include "TriangleMesh.hpp"

#include <cmath>
#include <algorithm>
#include <limits>
#include <cstring>

namespace Slic3r {

VoxelGrid MeshVoxelizer::voxelize(const TriangleMesh& mesh) const
{
    BoundingBoxf3 bbox = mesh.bounding_box();
    // Pad slightly to avoid boundary artifacts.
    float pad = m_config.voxel_size_mm * 2.0f;
    bbox.min -= Vec3d(pad, pad, pad);
    bbox.max += Vec3d(pad, pad, pad);

    VoxelGrid grid = VoxelGrid::from_bbox(bbox, m_config.voxel_size_mm);

    // First pass: mark voxels intersected by the mesh surface.
    // Raycast along Z (from below) for each XY column.
    for (int32_t y = 0; y < grid.size_y(); ++y) {
        for (int32_t x = 0; x < grid.size_x(); ++x) {
            Vec3d voxel_center = grid.voxel_to_world(x, y, 0);
            Vec3d origin(voxel_center.x(), voxel_center.y(),
                          bbox.min.z() - pad * 0.5f);
            Vec3d direction(0.0, 0.0, 1.0);

            // Supersample with multiple rays per column for anti-aliasing.
            int intersections = count_intersections(origin, direction, mesh);

            // Walk up the column and mark interior.
            if (intersections % 2 == 1) {
                // Find the z range that's inside by sampling.
                bool inside = false;
                for (int32_t z = 0; z < grid.size_z(); ++z) {
                    Vec3d pt = grid.voxel_to_world(x, y, z);
                    // Check if this z level is past the intersection boundary.
                    Vec3d ray_origin(pt.x(), pt.y(), bbox.min.z() - pad * 0.5f);
                    int hits = count_intersections(ray_origin, direction, mesh);
                    bool new_inside = (hits % 2 == 1);
                    if (new_inside && m_config.fill_interior)
                        grid.at(x, y, z) = 1.0f;
                    inside = new_inside;
                }
            }

            // Shell detection: mark voxels near the surface.
            if (m_config.fill_interior) {
                for (int32_t z = 0; z < grid.size_z(); ++z) {
                    if (grid.at(x, y, z) > 0.0f) {
                        // Check if this filled voxel is near an empty neighbor (surface).
                        bool at_surface = false;
                        for (int dz = -1; dz <= 1 && !at_surface; ++dz)
                            for (int dy = -1; dy <= 1 && !at_surface; ++dy)
                                for (int dx = -1; dx <= 1 && !at_surface; ++dx)
                                    if (grid.at(x + dx, y + dy, z + dz) <= 0.0f)
                                        at_surface = true;
                        // Surface voxels keep value 1.0; interior can optionally be lower.
                    }
                }
            }
        }
    }
    return grid;
}

Octree MeshVoxelizer::voxelize_to_octree(const TriangleMesh& mesh) const
{
    VoxelGrid grid = voxelize(mesh);
    return Octree::from_grid(grid);
}

bool MeshVoxelizer::ray_triangle_intersect(
    const Vec3d& origin, const Vec3d& direction,
    const Vec3d& v0, const Vec3d& v1, const Vec3d& v2,
    double& t) const
{
    const double EPSILON = 1e-8;

    Vec3d edge1 = (v1 - v0).cast<double>();
    Vec3d edge2 = (v2 - v0).cast<double>();
    Vec3d h     = direction.cross(edge2);
    double a    = edge1.dot(h);

    if (std::abs(a) < EPSILON) return false; // Ray parallel to triangle.

    double f = 1.0 / a;
    Vec3d  s = origin - v0.cast<double>();
    double u = f * s.dot(h);

    if (u < 0.0 || u > 1.0) return false;

    Vec3d  q = s.cross(edge1);
    double v = f * direction.dot(q);

    if (v < 0.0 || u + v > 1.0) return false;

    t = f * edge2.dot(q);
    return t > EPSILON;
}

int MeshVoxelizer::count_intersections(const Vec3d& origin, const Vec3d& direction,
                                        const TriangleMesh& mesh) const
{
    int count = 0;
    double t_min = std::numeric_limits<double>::max();

    for (size_t fi = 0; fi < mesh.its.indices.size(); ++fi) {
        const auto& idx = mesh.its.indices[fi];
        Vec3d v0 = mesh.its.vertices[idx(0)].cast<double>();
        Vec3d v1 = mesh.its.vertices[idx(1)].cast<double>();
        Vec3d v2 = mesh.its.vertices[idx(2)].cast<double>();

        double t;
        if (ray_triangle_intersect(origin, direction, v0, v1, v2, t)) {
            if (t > 1e-6) {
                // Count unique intersections (avoid double-counting at edges).
                bool duplicate = false;
                if (std::abs(t - t_min) < 1e-4) duplicate = true;

                if (!duplicate) {
                    ++count;
                    t_min = t;
                }
            }
        }
    }
    return count;
}

float MeshVoxelizer::supersample_voxel(const Vec3d& voxel_center, float voxel_size,
                                        const TriangleMesh& mesh) const
{
    int n       = m_config.num_rays;
    int samples = 0;
    int hits    = 0;

    float half = voxel_size * 0.5f;

    for (int sz = 0; sz < n; ++sz) {
        for (int sy = 0; sy < n; ++sy) {
            for (int sx = 0; sx < n; ++sx) {
                double offset_x = (n > 1) ? (sx / double(n - 1) - 0.5) * voxel_size : 0.0;
                double offset_y = (n > 1) ? (sy / double(n - 1) - 0.5) * voxel_size : 0.0;
                double offset_z = (n > 1) ? (sz / double(n - 1) - 0.5) * voxel_size : 0.0;

                Vec3d origin(voxel_center.x() + offset_x,
                              voxel_center.y() + offset_y,
                              voxel_center.z() - half * 2.0f);
                Vec3d direction(0.0, 0.0, 1.0);

                int c = count_intersections(origin, direction, mesh);
                if (c % 2 == 1) ++hits;
                ++samples;
            }
        }
    }
    return samples > 0 ? static_cast<float>(hits) / samples : 0.0f;
}

} // namespace Slic3r
