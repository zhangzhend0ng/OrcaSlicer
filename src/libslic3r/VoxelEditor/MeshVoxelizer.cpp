#include "VoxelEditor/MeshVoxelizer.hpp"
#include "VoxelEditor/VoxelGrid.hpp"
#include "VoxelEditor/Octree.hpp"
#include "TriangleMesh.hpp"

#include <cmath>
#include <algorithm>
#include <limits>

namespace Slic3r {

VoxelGrid MeshVoxelizer::voxelize(const TriangleMesh& mesh) const
{
    BoundingBoxf3 bbox = mesh.bounding_box();
    float pad = m_config.voxel_size_mm * 2.0f;
    bbox.min -= Vec3d(pad, pad, pad);
    bbox.max += Vec3d(pad, pad, pad);

    VoxelGrid grid = VoxelGrid::from_bbox(bbox, m_config.voxel_size_mm);

    // Ray origin: below the entire mesh.
    double ray_origin_z = bbox.min.z() - pad * 0.5f;

    for (int32_t z = 0; z < grid.size_z(); ++z) {
        for (int32_t y = 0; y < grid.size_y(); ++y) {
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                Vec3d voxel_center = grid.voxel_to_world(x, y, z);
                Vec3d origin(voxel_center.x(), voxel_center.y(), ray_origin_z);
                Vec3d direction(0.0, 0.0, 1.0);

                // Only count intersections UP TO this voxel (plus a small epsilon).
                double max_dist = voxel_center.z() - ray_origin_z + m_config.voxel_size_mm * 0.5;

                if (m_config.grayscale) {
                    float fill = supersample_voxel(voxel_center,
                                                    m_config.voxel_size_mm, mesh);
                    grid.at(x, y, z) = fill;
                } else {
                    int hits = count_intersections(origin, direction, max_dist, mesh);
                    if (hits % 2 == 1)
                        grid.at(x, y, z) = 1.0f;
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

    if (std::abs(a) < EPSILON) return false;

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
                                        double max_distance,
                                        const TriangleMesh& mesh) const
{
    int count = 0;

    for (size_t fi = 0; fi < mesh.its.indices.size(); ++fi) {
        const auto& idx = mesh.its.indices[fi];
        Vec3d v0 = mesh.its.vertices[idx(0)].cast<double>();
        Vec3d v1 = mesh.its.vertices[idx(1)].cast<double>();
        Vec3d v2 = mesh.its.vertices[idx(2)].cast<double>();

        double t;
        if (ray_triangle_intersect(origin, direction, v0, v1, v2, t)) {
            if (t > 1e-6 && t < max_distance)
                ++count;
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

    for (int sz = 0; sz < n; ++sz) {
        for (int sy = 0; sy < n; ++sy) {
            for (int sx = 0; sx < n; ++sx) {
                double offset_x = (n > 1) ? (sx / double(n - 1) - 0.5) * voxel_size : 0.0;
                double offset_y = (n > 1) ? (sy / double(n - 1) - 0.5) * voxel_size : 0.0;

                Vec3d origin(voxel_center.x() + offset_x,
                              voxel_center.y() + offset_y,
                              voxel_center.z() - voxel_size * 3.0f);
                Vec3d direction(0.0, 0.0, 1.0);
                double max_dist = voxel_size * 3.0f + voxel_size * 0.5;

                int c = count_intersections(origin, direction, max_dist, mesh);
                if (c % 2 == 1) ++hits;
                ++samples;
            }
        }
    }
    return samples > 0 ? static_cast<float>(hits) / samples : 0.0f;
}

} // namespace Slic3r
