#ifndef slic3r_VoxelToMesh_hpp_
#define slic3r_VoxelToMesh_hpp_

#include "VoxelEditor/VoxelTypes.hpp"
#include <vector>

namespace Slic3r {

class Octree;
class VoxelGrid;
class TriangleMesh;
struct indexed_triangle_set;

// Converts voxel data back to a triangle mesh for Plater integration.
// Generates only surface faces (voxel faces that border empty space),
// then merges coplanar quads to reduce triangle count.
class VoxelToMesh {
public:
    // Convert an Octree to a TriangleMesh at the given voxel resolution.
    static TriangleMesh convert(const Octree& octree, float voxel_size_mm = 1.0f);

    // Convert a VoxelGrid directly.
    static TriangleMesh convert(const VoxelGrid& grid);
};

} // namespace Slic3r

#endif // slic3r_VoxelToMesh_hpp_
