#include "VoxelEditor/Octree.hpp"
#include "VoxelEditor/VoxelGrid.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <cstring>

namespace Slic3r {

// --- Static factory: efficient top-down build from VoxelGrid ---

static void build_node_from_grid(Octree::Node& node,
                                  const VoxelGrid& grid,
                                  const VoxelCoord& min_v,
                                  const VoxelCoord& max_v,
                                  const BoundingBoxf3& node_bbox,
                                  int depth)
{
    int32_t sx = max_v.x() - min_v.x() + 1;
    int32_t sy = max_v.y() - min_v.y() + 1;
    int32_t sz = max_v.z() - min_v.z() + 1;

    if (depth >= Octree::MAX_DEPTH || (sx <= 1 && sy <= 1 && sz <= 1)) {
        VoxelValue v = grid.at(min_v.x(), min_v.y(), min_v.z());
        VoxelNodeState s = (v <= 0.0f) ? VoxelNodeState::Empty
                          : (v >= 1.0f) ? VoxelNodeState::Filled
                          : VoxelNodeState::Partial;
        node.set_uniform(s, v);
        return;
    }

    VoxelValue first = grid.at(min_v.x(), min_v.y(), min_v.z());
    bool uniform = true;
    for (int32_t z = min_v.z(); z <= max_v.z() && uniform; ++z)
        for (int32_t y = min_v.y(); y <= max_v.y() && uniform; ++y)
            for (int32_t x = min_v.x(); x <= max_v.x() && uniform; ++x)
                if (grid.at(x, y, z) != first) uniform = false;

    if (uniform) {
        VoxelNodeState s = (first <= 0.0f) ? VoxelNodeState::Empty
                          : (first >= 1.0f) ? VoxelNodeState::Filled
                          : VoxelNodeState::Partial;
        node.set_uniform(s, first);
        return;
    }

    node.state = VoxelNodeState::Mixed;
    node.uniform_value = 0.0f;

    int32_t mx = min_v.x() + sx / 2 - 1; if (mx < min_v.x()) mx = min_v.x();
    int32_t my = min_v.y() + sy / 2 - 1; if (my < min_v.y()) my = min_v.y();
    int32_t mz = min_v.z() + sz / 2 - 1; if (mz < min_v.z()) mz = min_v.z();

    Vec3d wcenter = node_bbox.center();

    struct CZ { VoxelCoord cmin, cmax; bool valid; };
    CZ cz[8] = {
        {{min_v.x(),   min_v.y(),   min_v.z()}, {mx,        my,        mz},        true},
        {{mx+1,        min_v.y(),   min_v.z()}, {max_v.x(), my,        mz},        sx > 1},
        {{min_v.x(),   my+1,        min_v.z()}, {mx,        max_v.y(), mz},        sy > 1},
        {{mx+1,        my+1,        min_v.z()}, {max_v.x(), max_v.y(), mz},        sx > 1 && sy > 1},
        {{min_v.x(),   min_v.y(),   mz+1},      {mx,        my,        max_v.z()}, sz > 1},
        {{mx+1,        min_v.y(),   mz+1},      {max_v.x(), my,        max_v.z()}, sx > 1 && sz > 1},
        {{min_v.x(),   my+1,        mz+1},      {mx,        max_v.y(), max_v.z()}, sy > 1 && sz > 1},
        {{mx+1,        my+1,        mz+1},      {max_v.x(), max_v.y(), max_v.z()}, sx > 1 && sy > 1 && sz > 1}
    };

    for (int i = 0; i < 8; ++i) {
        if (!cz[i].valid) continue;
        bool all_empty = true;
        for (int32_t z = cz[i].cmin.z(); z <= cz[i].cmax.z() && all_empty; ++z)
            for (int32_t y = cz[i].cmin.y(); y <= cz[i].cmax.y() && all_empty; ++y)
                for (int32_t x = cz[i].cmin.x(); x <= cz[i].cmax.x() && all_empty; ++x)
                    if (grid.at(x, y, z) > 0.0f) all_empty = false;
        if (all_empty) continue;

        node.children[i] = std::make_unique<Octree::Node>();
        Vec3d cmin_w, cmax_w;
        cmin_w.x() = (i & 1) ? wcenter.x() : node_bbox.min.x();
        cmax_w.x() = (i & 1) ? node_bbox.max.x() : wcenter.x();
        cmin_w.y() = (i & 2) ? wcenter.y() : node_bbox.min.y();
        cmax_w.y() = (i & 2) ? node_bbox.max.y() : wcenter.y();
        cmin_w.z() = (i & 4) ? wcenter.z() : node_bbox.min.z();
        cmax_w.z() = (i & 4) ? node_bbox.max.z() : wcenter.z();
        build_node_from_grid(*node.children[i], grid,
                              cz[i].cmin, cz[i].cmax,
                              BoundingBoxf3(cmin_w, cmax_w), depth + 1);
    }

    bool any = false;
    for (int i = 0; i < 8; ++i) if (node.children[i]) { any = true; break; }
    if (!any) node.set_uniform(VoxelNodeState::Empty, 0.0f);
}

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

    if (grid.total_voxels() == 0) return tree;

    VoxelCoord min_v(0, 0, 0);
    VoxelCoord max_v(grid.size_x() - 1, grid.size_y() - 1, grid.size_z() - 1);
    build_node_from_grid(*tree.m_root, grid, min_v, max_v, tree.m_world_bbox, 0);
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
    if (node.is_leaf()) return node.uniform_value;
    if (depth >= MAX_DEPTH) return node.uniform_value;
    int idx = child_index(node_bbox, pt);
    if (!node.children[idx]) return 0.0f;
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
    if (!bboxes_overlap(node_bbox, region)) return;

    Vec3d node_size = node_bbox.size();
    double min_dim = std::min({node_size.x(), node_size.y(), node_size.z()});
    if (min_dim < 1.0) {
        if (val > 0.0f) {
            VoxelNodeState s = (val >= 1.0f) ? VoxelNodeState::Filled : VoxelNodeState::Partial;
            node.set_uniform(s, val);
        }
        return;
    }
    if (depth >= MAX_DEPTH) {
        if (val > 0.0f) {
            VoxelNodeState s = (val >= 1.0f) ? VoxelNodeState::Filled : VoxelNodeState::Partial;
            node.set_uniform(s, val);
        }
        return;
    }

    if (node.is_leaf()) {
        if (node.state == VoxelNodeState::Empty && val <= 0.0f) return;
        subdivide(node);
    }

    for (int i = 0; i < 8; ++i) {
        BoundingBoxf3 cb = child_bbox(node_bbox, i);
        if (bboxes_overlap(cb, region)) {
            if (!node.children[i]) node.children[i] = std::make_unique<Node>();
            fill_region_recursive(*node.children[i], cb, region, val, depth + 1);
        }
    }

    bool all_empty = true;
    for (int i = 0; i < 8; ++i)
        if (node.children[i] && node.children[i]->state != VoxelNodeState::Empty) { all_empty = false; break; }
    if (all_empty) node.set_uniform(VoxelNodeState::Empty, 0.0f);
}

// --- Sphere brush ---

void Octree::brush_sphere(const Vec3d& center, float radius_mm, VoxelValue val)
{
    BoundingBoxf3 region({center.x()-radius_mm, center.y()-radius_mm, center.z()-radius_mm},
                          {center.x()+radius_mm, center.y()+radius_mm, center.z()+radius_mm});
    fill_region(region, val);
}

// --- Boolean operations ---

void Octree::apply_op(const Octree& other, VoxelOp op)
{
    float vs = 0.5f;
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
    for (int32_t z = 0; z < sz; ++z)
        for (int32_t y = 0; y < sy; ++y)
            for (int32_t x = 0; x < sx; ++x) {
                Vec3d pt = grid.voxel_to_world(x, y, z);
                if (m_world_bbox.contains(pt)) grid.at(x, y, z) = sample(pt);
            }
    return grid;
}

// --- Traversal ---

void Octree::visit_leaves(std::function<void(const BoundingBoxf3&,VoxelNodeState,VoxelValue)> cb) const
{
    visit_leaves_recursive(*m_root, m_world_bbox, cb, 0);
}

void Octree::visit_leaves_recursive(const Node& node, const BoundingBoxf3& node_bbox,
    std::function<void(const BoundingBoxf3&,VoxelNodeState,VoxelValue)>& cb, int depth) const
{
    if (node.is_leaf() || depth >= MAX_DEPTH) { cb(node_bbox, node.state, node.uniform_value); return; }
    for (int i = 0; i < 8; ++i)
        if (node.children[i]) visit_leaves_recursive(*node.children[i], child_bbox(node_bbox, i), cb, depth + 1);
}

// --- Memory stats ---

size_t Octree::node_count() const { return count_nodes(*m_root); }
size_t Octree::count_nodes(const Node& node) const {
    size_t n = 1;
    for (int i = 0; i < 8; ++i) if (node.children[i]) n += count_nodes(*node.children[i]);
    return n;
}
size_t Octree::memory_bytes() const { return node_count() * sizeof(Node); }

// --- Internal helpers ---

void Octree::subdivide(Node& node) {
    VoxelValue v = node.uniform_value;
    node.state = VoxelNodeState::Mixed;
    for (int i = 0; i < 8; ++i)
        if (v > 0.0f) {
            node.children[i] = std::make_unique<Node>();
            VoxelNodeState s = (v >= 1.0f) ? VoxelNodeState::Filled : VoxelNodeState::Partial;
            node.children[i]->set_uniform(s, v);
        }
}

int Octree::child_index(const BoundingBoxf3& nb, const Vec3d& pt) const {
    Vec3d c = nb.center();
    return (pt.x()>=c.x()?1:0) | ((pt.y()>=c.y()?1:0)<<1) | ((pt.z()>=c.z()?1:0)<<2);
}

BoundingBoxf3 Octree::child_bbox(const BoundingBoxf3& nb, int idx) const {
    Vec3d c = nb.center();
    return BoundingBoxf3(
        {(idx&1)?c.x():nb.min.x(), (idx&2)?c.y():nb.min.y(), (idx&4)?c.z():nb.min.z()},
        {(idx&1)?nb.max.x():c.x(), (idx&2)?nb.max.y():c.y(), (idx&4)?nb.max.z():c.z()}
    );
}

bool Octree::bboxes_overlap(const BoundingBoxf3& a, const BoundingBoxf3& b) const {
    return a.min.x()<=b.max.x() && a.max.x()>=b.min.x()
        && a.min.y()<=b.max.y() && a.max.y()>=b.min.y()
        && a.min.z()<=b.max.z() && a.max.z()>=b.min.z();
}

} // namespace Slic3r
