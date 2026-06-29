#include "VoxelEditor/Octree.hpp"
#include "VoxelEditor/VoxelGrid.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

namespace Slic3r {

// --- Static factory ---

Octree Octree::from_grid(const VoxelGrid& grid)
{
    Octree tree;
    Vec3d origin = grid.origin_mm();
    float vs     = grid.voxel_size_mm();
    Vec3d extent = {
        origin.x() + grid.size_x() * vs,
        origin.y() + grid.size_y() * vs,
        origin.z() + grid.size_z() * vs
    };
    tree.m_world_bbox = BoundingBoxf3(origin, extent);

    // Fill leaf nodes from dense grid data.
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x) {
                VoxelValue v = grid.at(x, y, z);
                if (v <= 0.0f) continue;

                Vec3d center = grid.voxel_to_world(x, y, z);
                BoundingBoxf3 voxel_bbox(
                    {center.x() - vs * 0.5f, center.y() - vs * 0.5f, center.z() - vs * 0.5f},
                    {center.x() + vs * 0.5f, center.y() + vs * 0.5f, center.z() + vs * 0.5f}
                );
                tree.fill_region(voxel_bbox, v);
            }
    return tree;
}

// --- Sample ---

VoxelValue Octree::sample(const Vec3d& world_pt) const
{
    if (!m_world_bbox.contains(world_pt)) return 0.0f;
    return sample_recursive(*m_root, m_world_bbox, world_pt, 0);
}

VoxelValue Octree::sample_recursive(const Node& node, const BoundingBoxf3& node_bbox,
                                     const Vec3d& pt, int depth) const
{
    if (node.is_leaf())
        return node.uniform_value;

    if (depth >= MAX_DEPTH)
        return node.uniform_value;

    int idx = child_index(node_bbox, pt);
    if (!node.children[idx])
        return 0.0f;

    return sample_recursive(*node.children[idx], child_bbox(node_bbox, idx), pt, depth + 1);
}

// --- Fill region ---

void Octree::fill_region(const BoundingBoxf3& world_region, VoxelValue val)
{
    fill_region_recursive(*m_root, m_world_bbox, world_region, val, 0);
}

void Octree::fill_region_recursive(Node& node, const BoundingBoxf3& node_bbox,
                                    const BoundingBoxf3& region, VoxelValue val, int depth)
{
    // If the region fully contains this node, set it uniformly.
    if (region.min.x() <= node_bbox.min.x() && region.min.y() <= node_bbox.min.y() &&
        region.min.z() <= node_bbox.min.z() &&
        region.max.x() >= node_bbox.max.x() && region.max.y() >= node_bbox.max.y() &&
        region.max.z() >= node_bbox.max.z()) {
        VoxelNodeState s = (val <= 0.0f) ? VoxelNodeState::Empty
                          : (val >= 1.0f) ? VoxelNodeState::Filled
                          : VoxelNodeState::Partial;
        node.set_uniform(s, val);
        return;
    }

    // If no overlap, nothing to do.
    if (!bboxes_overlap(node_bbox, region)) return;

    // If we've hit max depth, write the value directly.
    if (depth >= MAX_DEPTH) {
        if (val > 0.0f) {
            VoxelNodeState s = (val >= 1.0f) ? VoxelNodeState::Filled : VoxelNodeState::Partial;
            node.set_uniform(s, val);
        }
        return;
    }

    // Partial overlap: subdivide if leaf, then recurse.
    if (node.is_leaf()) {
        if (node.state == VoxelNodeState::Empty && val <= 0.0f) return;
        subdivide(node);
    }

    for (int i = 0; i < 8; ++i) {
        BoundingBoxf3 cb = child_bbox(node_bbox, i);
        if (bboxes_overlap(cb, region)) {
            if (!node.children[i])
                node.children[i] = std::make_unique<Node>();
            fill_region_recursive(*node.children[i], cb, region, val, depth + 1);
        }
    }

    // Collapse if all children are uniform and identical.
    // (Simplified: only collapse to empty; a full collapse check would compare all 8)
    bool all_empty = true;
    for (int i = 0; i < 8; ++i) {
        if (node.children[i] && node.children[i]->state != VoxelNodeState::Empty) {
            all_empty = false;
            break;
        }
    }
    if (all_empty)
        node.set_uniform(VoxelNodeState::Empty, 0.0f);
}

// --- Sphere brush ---

void Octree::brush_sphere(const Vec3d& center, float radius_mm, VoxelValue val)
{
    BoundingBoxf3 region(
        {center.x() - radius_mm, center.y() - radius_mm, center.z() - radius_mm},
        {center.x() + radius_mm, center.y() + radius_mm, center.z() + radius_mm}
    );
    // Approximate sphere by bounding box for broad phase; the dense grid handles exact shape.
    fill_region(region, val);
}

// --- Boolean operations ---

void Octree::apply_op(const Octree& other, VoxelOp op)
{
    // Convert both to dense grids at a common resolution, apply op, rebuild.
    float vs = 0.5f; // Default 0.5mm voxel resolution for op
    VoxelGrid self_grid  = this->to_grid(vs);
    VoxelGrid other_grid = other.to_grid(vs);
    self_grid.apply_op(other_grid, op);
    *this = Octree::from_grid(self_grid);
}

// --- Conversion to dense grid ---

VoxelGrid Octree::to_grid(float voxel_size) const
{
    Vec3d size = m_world_bbox.size();
    int32_t sx = static_cast<int32_t>(std::ceil(size.x() / voxel_size)) + 1;
    int32_t sy = static_cast<int32_t>(std::ceil(size.y() / voxel_size)) + 1;
    int32_t sz = static_cast<int32_t>(std::ceil(size.z() / voxel_size)) + 1;

    VoxelGrid grid(sx, sy, sz);
    grid.set_origin(m_world_bbox.min);
    grid.set_voxel_size(voxel_size);

    // For each voxel in the dense grid, sample the octree.
    for (int32_t z = 0; z < sz; ++z) {
        for (int32_t y = 0; y < sy; ++y) {
            for (int32_t x = 0; x < sx; ++x) {
                Vec3d pt = grid.voxel_to_world(x, y, z);
                if (m_world_bbox.contains(pt))
                    grid.at(x, y, z) = sample(pt);
            }
        }
    }
    return grid;
}

// --- Traversal ---

void Octree::visit_leaves(
    std::function<void(const BoundingBoxf3&, VoxelNodeState, VoxelValue)> callback) const
{
    visit_leaves_recursive(*m_root, m_world_bbox, callback, 0);
}

void Octree::visit_leaves_recursive(const Node& node, const BoundingBoxf3& node_bbox,
                                     std::function<void(const BoundingBoxf3&, VoxelNodeState, VoxelValue)>& cb,
                                     int depth) const
{
    if (node.is_leaf() || depth >= MAX_DEPTH) {
        cb(node_bbox, node.state, node.uniform_value);
        return;
    }

    for (int i = 0; i < 8; ++i) {
        if (node.children[i])
            visit_leaves_recursive(*node.children[i], child_bbox(node_bbox, i), cb, depth + 1);
    }
}

// --- Memory stats ---

size_t Octree::node_count() const
{
    return count_nodes(*m_root);
}

size_t Octree::count_nodes(const Node& node) const
{
    size_t n = 1;
    for (int i = 0; i < 8; ++i)
        if (node.children[i])
            n += count_nodes(*node.children[i]);
    return n;
}

size_t Octree::memory_bytes() const
{
    return node_count() * sizeof(Node);
}

// --- Internal helpers ---

void Octree::subdivide(Node& node)
{
    VoxelValue v = node.uniform_value;
    node.state = VoxelNodeState::Mixed;
    for (int i = 0; i < 8; ++i) {
        if (v > 0.0f) {
            node.children[i] = std::make_unique<Node>();
            VoxelNodeState s = (v >= 1.0f) ? VoxelNodeState::Filled : VoxelNodeState::Partial;
            node.children[i]->set_uniform(s, v);
        }
    }
}

int Octree::child_index(const BoundingBoxf3& node_bbox, const Vec3d& pt) const
{
    Vec3d center = node_bbox.center();
    int ix = (pt.x() >= center.x()) ? 1 : 0;
    int iy = (pt.y() >= center.y()) ? 1 : 0;
    int iz = (pt.z() >= center.z()) ? 1 : 0;
    return ix | (iy << 1) | (iz << 2);
}

BoundingBoxf3 Octree::child_bbox(const BoundingBoxf3& node_bbox, int idx) const
{
    Vec3d center = node_bbox.center();
    Vec3d cmin, cmax;
    cmin.x() = (idx & 1) ? center.x() : node_bbox.min.x();
    cmax.x() = (idx & 1) ? node_bbox.max.x() : center.x();
    cmin.y() = (idx & 2) ? center.y() : node_bbox.min.y();
    cmax.y() = (idx & 2) ? node_bbox.max.y() : center.y();
    cmin.z() = (idx & 4) ? center.z() : node_bbox.min.z();
    cmax.z() = (idx & 4) ? node_bbox.max.z() : center.z();
    return BoundingBoxf3(cmin, cmax);
}

bool Octree::bboxes_overlap(const BoundingBoxf3& a, const BoundingBoxf3& b) const
{
    return a.min.x() <= b.max.x() && a.max.x() >= b.min.x()
        && a.min.y() <= b.max.y() && a.max.y() >= b.min.y()
        && a.min.z() <= b.max.z() && a.max.z() >= b.min.z();
}

} // namespace Slic3r
