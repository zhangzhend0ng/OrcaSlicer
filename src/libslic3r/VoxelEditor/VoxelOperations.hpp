#ifndef slic3r_VoxelOperations_hpp_
#define slic3r_VoxelOperations_hpp_

#include "VoxelEditor/VoxelTypes.hpp"

#include <memory>
#include <vector>
#include <string>
#include <functional>

namespace Slic3r {

class Octree;
class VoxelGrid;

// High-level voxel editing operations implementing Section 4.1 of the design doc.
// These operate on Octrees for efficient sparse storage and fast local edits.
//
// Operations are structured in three tiers:
//   High (80%): templates, booleans, region fill, shell, array
//   Mid  (15%): brushes, smooth, extrude
//   Low  (5%):  individual block placement/removal

namespace VoxelOps {

// --- Template Generation ---

// Generate primitive shapes as Octrees.
// All dimensions in mm within a given world-space bounding box.

// Solid box.
Octree make_box(const BoundingBoxf3& world_bbox, float voxel_size);

// Solid sphere centered in the bbox.
Octree make_sphere(const BoundingBoxf3& world_bbox, float voxel_size);

// Solid cylinder along Z axis.
Octree make_cylinder(const BoundingBoxf3& world_bbox, float voxel_size);

// Torus in XY plane.
Octree make_torus(const BoundingBoxf3& world_bbox, float voxel_size, float tube_radius);

// --- Boolean Operations ---

// Union: result = a | b. Returns new Octree.
Octree boolean_union(const Octree& a, const Octree& b, float voxel_size = 0.5f);

// Subtract: result = a - b. Returns new Octree.
Octree boolean_subtract(const Octree& a, const Octree& b, float voxel_size = 0.5f);

// Intersect: result = a & b. Returns new Octree.
Octree boolean_intersect(const Octree& a, const Octree& b, float voxel_size = 0.5f);

// --- Region Operations ---

// Fill a world-space AABB region with a uniform value.
void region_fill(Octree& tree, const BoundingBoxf3& region, VoxelValue val);

// Clear a world-space AABB region (set to empty).
inline void region_clear(Octree& tree, const BoundingBoxf3& region) {
    region_fill(tree, region, 0.0f);
}

// --- Shell / Hollow ---

// Create a hollow shell of the model with given wall thickness.
// wall_thickness_mm: thickness of the shell walls.
Octree hollow(const Octree& tree, float wall_thickness_mm, float voxel_size = 0.5f);

// --- Array / Pattern ---

// Create a linear array of copies along an axis.
// count: number of copies (including original).
// spacing_mm: distance between copies.
Octree linear_array(const Octree& tree, const Vec3d& axis,
                     int count, float spacing_mm, float voxel_size = 0.5f);

// Create a rectangular grid array in XY plane.
// nx, ny: number of copies in X and Y.
// spacing: spacing between copies in mm.
Octree grid_array(const Octree& tree, int nx, int ny,
                   float spacing_x_mm, float spacing_y_mm,
                   float voxel_size = 0.5f);

// --- Smoothing ---

// Apply a simple 3x3x3 box blur to smooth the model.
// iterations: number of smoothing passes.
// This approximates the "大块换小块序列" approach from Section 2.2.
Octree smooth(const Octree& tree, int iterations = 1, float voxel_size = 0.5f);

// --- Block-level Operations ---

// Place a single voxel at a world-space position.
void place_block(Octree& tree, const Vec3d& world_pos, float size_mm, VoxelValue val = 1.0f);

// Remove a single voxel at a world-space position.
inline void remove_block(Octree& tree, const Vec3d& world_pos, float size_mm) {
    place_block(tree, world_pos, size_mm, 0.0f);
}

// --- Brush Operations ---

// Apply a spherical brush at a world position.
void brush_sphere(Octree& tree, const Vec3d& center, float radius_mm, VoxelValue val);

// Apply a cubic brush at a world position.
void brush_cube(Octree& tree, const Vec3d& center, float size_mm, VoxelValue val);

// --- Utility ---

// Convert an Octree to a dense VoxelGrid at the given resolution.
VoxelGrid to_grid(const Octree& tree, float voxel_size);

// Get statistics about an Octree.
struct OctreeStats {
    size_t node_count;
    size_t memory_bytes;
    BoundingBoxf3 world_bbox;
    int max_depth;
};
OctreeStats stats(const Octree& tree);

} // namespace VoxelOps

} // namespace Slic3r

#endif // slic3r_VoxelOperations_hpp_
