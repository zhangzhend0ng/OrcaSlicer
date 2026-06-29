#ifndef slic3r_MeshVoxelizer_hpp_
#define slic3r_MeshVoxelizer_hpp_

#include "VoxelEditor/VoxelTypes.hpp"

#include <memory>
#include <vector>
#include <cstdint>

namespace Slic3r {

class TriangleMesh;
class VoxelGrid;
class Octree;

// Converts a TriangleMesh to voxel representations using raycasting.
// Supports both dense VoxelGrid and sparse Octree output.
class MeshVoxelizer {
public:
    struct Config {
        float voxel_size_mm = 0.5f;     // Edge length of each voxel in mm
        bool  fill_interior = true;      // Fill interior after shell detection
        bool  grayscale     = false;     // Enable sub-voxel precision (partial fills)
        int   num_rays      = 3;         // Rays per voxel for anti-aliasing (1/3/5)
    };

    explicit MeshVoxelizer(const Config& cfg = Config{}) : m_config(cfg) {}

    // Voxelize a mesh into a dense VoxelGrid.
    // Returns the grid with voxel values set where the mesh interior is detected.
    VoxelGrid voxelize(const TriangleMesh& mesh) const;

    // Voxelize directly into an Octree for sparse storage.
    Octree voxelize_to_octree(const TriangleMesh& mesh) const;

    // Get/set configuration.
    const Config& config() const { return m_config; }
    void set_config(const Config& cfg) { m_config = cfg; }

private:
    Config m_config;

    // Ray-triangle intersection test (Moller-Trumbore).
    bool ray_triangle_intersect(const Vec3d& origin, const Vec3d& direction,
                                 const Vec3d& v0, const Vec3d& v1, const Vec3d& v2,
                                 double& t) const;

    // Count ray-mesh intersections along a ray.
    int count_intersections(const Vec3d& origin, const Vec3d& direction, double max_distance,
                             const TriangleMesh& mesh) const;

    // Voxelize a single horizontal slice for interior filling.
    void fill_interior_slice(VoxelGrid& grid, int32_t z, const TriangleMesh& mesh) const;

    // Sub-voxel precision: estimate partial fill using supersampling.
    float supersample_voxel(const Vec3d& voxel_center, float voxel_size,
                             const TriangleMesh& mesh) const;
};

} // namespace Slic3r

#endif // slic3r_MeshVoxelizer_hpp_
