#ifndef slic3r_Octree_hpp_
#define slic3r_Octree_hpp_

#include "VoxelEditor/VoxelTypes.hpp"

#include <memory>
#include <vector>
#include <array>
#include <cstdint>
#include <functional>

namespace Slic3r {

// An 8-way octree for sparse voxel storage.
// Each node is either a leaf (uniform state) or an internal node with 8 children.
// Supports efficient region queries, boolean operations, and incremental editing.
//
// Maximum depth is limited by MAX_DEPTH to bound recursion.
class Octree {
public:
    static constexpr int MAX_DEPTH = 12;

    // Internal node structure.
    struct Node {
        VoxelNodeState state = VoxelNodeState::Empty;
        VoxelValue      uniform_value = 0.0f;  // Used when state is Empty, Filled, or Partial
        std::array<std::unique_ptr<Node>, 8> children;

        bool is_leaf() const { return state != VoxelNodeState::Mixed; }
        void set_uniform(VoxelNodeState s, VoxelValue v) {
            state         = s;
            uniform_value = v;
            for (auto& c : children) c.reset();
        }
    };

    // --- Construction ---
    Octree() : m_root(std::make_unique<Node>()) {}

    // Build an octree from a dense VoxelGrid.
    // The grid's bounding box defines the octree root's world extent.
    static Octree from_grid(const class VoxelGrid& grid);

    // --- World extent ---
    const BoundingBoxf3& world_bbox() const { return m_world_bbox; }
    void set_world_bbox(const BoundingBoxf3& bbox) { m_world_bbox = bbox; }

    // --- Voxel access (world-space) ---
    VoxelValue sample(const Vec3d& world_pt) const;

    // --- Region operations ---
    // Set a world-space AABB region to a uniform value.
    void fill_region(const BoundingBoxf3& world_region, VoxelValue val);

    // Apply a sphere brush at the given world position.
    void brush_sphere(const Vec3d& center, float radius_mm, VoxelValue val);

    // --- Boolean operations ---
    void apply_op(const Octree& other, VoxelOp op);

    // --- Conversion ---
    // Export back to a dense VoxelGrid at the given resolution.
    VoxelGrid to_grid(float voxel_size) const;

    // --- Traversal ---
    // Visit every leaf node with its world-space bounding box.
    void visit_leaves(std::function<void(const BoundingBoxf3&, VoxelNodeState, VoxelValue)> callback) const;

    // --- Memory ---
    size_t node_count() const;
    size_t memory_bytes() const;

private:
    std::unique_ptr<Node> m_root;
    BoundingBoxf3         m_world_bbox;

    // Internal helpers
    void fill_region_recursive(Node& node, const BoundingBoxf3& node_bbox,
                                const BoundingBoxf3& region, VoxelValue val, int depth);
    VoxelValue sample_recursive(const Node& node, const BoundingBoxf3& node_bbox,
                                 const Vec3d& pt, int depth) const;
    void to_grid_recursive(const Node& node, const BoundingBoxf3& node_bbox,
                            VoxelGrid& grid, int depth) const;
    void visit_leaves_recursive(const Node& node, const BoundingBoxf3& node_bbox,
                                 std::function<void(const BoundingBoxf3&, VoxelNodeState, VoxelValue)>& cb,
                                 int depth) const;
    size_t count_nodes(const Node& node) const;
    void subdivide(Node& node);
    int child_index(const BoundingBoxf3& node_bbox, const Vec3d& pt) const;
    BoundingBoxf3 child_bbox(const BoundingBoxf3& node_bbox, int idx) const;
    bool bboxes_overlap(const BoundingBoxf3& a, const BoundingBoxf3& b) const;
};

} // namespace Slic3r

#endif // slic3r_Octree_hpp_
