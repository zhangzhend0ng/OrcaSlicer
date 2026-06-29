#include "VoxelEditor/VoxelSlicer.hpp"
#include "VoxelEditor/VoxelGrid.hpp"
#include "VoxelEditor/Octree.hpp"

#include <algorithm>
#include <cmath>
#include <set>
#include <sstream>
#include <iomanip>

namespace Slic3r {

// ---------------------------------------------------------------------------
// Moore-neighborhood directions for contour tracing.
// We trace along pixel EDGES (not corners), following the boundary between
// filled (>= 0.5) and empty (< 0.5) pixels.
//
// Edge encoding: 0=top, 1=right, 2=bottom, 3=left
// Direction offsets for each edge (dx, dy for moving along the contour):
// ---------------------------------------------------------------------------
static const int TRACE_DX[4] = { 1,  0, -1,  0};
static const int TRACE_DY[4] = { 0,  1,  0, -1};

// Offsets to check the two pixels adjacent to each edge.
// For edge 0 (top):    pixel above is (x, y-1), pixel below is (x, y)
// For edge 1 (right):  pixel left is  (x, y),   pixel right is (x+1, y)
// For edge 2 (bottom): pixel above is (x, y),   pixel below is (x, y+1)
// For edge 3 (left):   pixel left is  (x-1, y), pixel right is (x, y)
static const int EDGE_PX1_DX[4] = {  0,  0,  0, -1};
static const int EDGE_PX1_DY[4] = { -1,  0,  0,  0};
static const int EDGE_PX2_DX[4] = {  0,  1,  0,  0};
static const int EDGE_PX2_DY[4] = {  0,  0,  1,  0};

// --- Helpers ---

static inline bool is_filled(VoxelValue v) { return v >= 0.5f; }

static inline VoxelValue safe_sample(const VoxelLayer& layer, int32_t x, int32_t y) {
    if (x < 0 || x >= layer.width || y < 0 || y >= layer.height) return 0.0f;
    return layer.at(x, y);
}

// Check if edge 'e' at pixel (px, py) is a boundary edge.
// A boundary edge separates a filled pixel from an empty pixel.
static bool is_boundary_edge(const VoxelLayer& layer, int32_t px, int32_t py, int e) {
    bool p1_filled = is_filled(safe_sample(layer, px + EDGE_PX1_DX[e], py + EDGE_PX1_DY[e]));
    bool p2_filled = is_filled(safe_sample(layer, px + EDGE_PX2_DX[e], py + EDGE_PX2_DY[e]));
    return p1_filled != p2_filled;
}

// Encode an edge visit: key = (y * width + x) * 4 + edge
static inline int64_t edge_key(int32_t x, int32_t y, int e, int32_t width) {
    return (static_cast<int64_t>(y) * width + x) * 4 + e;
}

// --- Contour Extraction ---

void VoxelSlicer::extract_contours(const VoxelLayer& layer,
                                    std::vector<VoxelContour>& outer,
                                    std::vector<VoxelContour>& inner) const
{
    // visited: tracks which pixel edges have been traced.
    int64_t total_edges = static_cast<int64_t>(layer.width) * layer.height * 4;
    std::vector<bool> visited(total_edges, false);

    // Scan all pixels for boundary edges.
    for (int32_t y = 0; y < layer.height; ++y) {
        for (int32_t x = 0; x < layer.width; ++x) {
            for (int e = 0; e < 4; ++e) {
                int64_t key = edge_key(x, y, e, layer.width);
                if (visited[key]) continue;

                if (!is_boundary_edge(layer, x, y, e)) {
                    visited[key] = true;
                    continue;
                }

                // Found an untraced boundary edge — trace a new contour.
                VoxelContour contour = trace_contour(layer, visited, x, y, e);

                if (contour.size() < 4) continue; // discard degenerate

                // Classify as outer or inner based on pixel fill status.
                // If the pixel to the right/below the starting edge is filled, it's an outer contour.
                bool inner_check = is_filled(safe_sample(layer,
                    x + EDGE_PX1_DX[e], y + EDGE_PX1_DY[e]));
                if (inner_check)
                    outer.push_back(std::move(contour));
                else
                    inner.push_back(std::move(contour));
            }
        }
    }
}

VoxelContour VoxelSlicer::trace_contour(const VoxelLayer& layer,
                                         std::vector<bool>& visited,
                                         int32_t start_x, int32_t start_y,
                                         int start_edge) const
{
    VoxelContour contour;
    int32_t cx = start_x, cy = start_y;
    int ce = start_edge;
    int32_t w = layer.width;

    // Maximum steps to prevent infinite loops on malformed data.
    const int64_t max_steps = static_cast<int64_t>(w) * layer.height * 8;

    for (int64_t step = 0; step < max_steps; ++step) {
        int64_t key = edge_key(cx, cy, ce, w);
        if (visited[key]) break;
        visited[key] = true;

        // Record the contour point: the midpoint of this edge.
        // For edge 0 (top):    (cx + 0.5, cy)
        // For edge 1 (right):  (cx + 1,   cy + 0.5)
        // For edge 2 (bottom): (cx + 0.5, cy + 1)
        // For edge 3 (left):   (cx,       cy + 0.5)
        // We store integer coordinates scaled by 2 to avoid floats.
        VoxelPoint2D pt;
        switch (ce) {
        case 0: pt = {cx * 2 + 1, cy * 2 + 0}; break;
        case 1: pt = {cx * 2 + 2, cy * 2 + 1}; break;
        case 2: pt = {cx * 2 + 1, cy * 2 + 2}; break;
        case 3: pt = {cx * 2 + 0, cy * 2 + 1}; break;
        }
        contour.push_back(pt);

        // Determine next edge using Moore neighborhood rules.
        // The next edge depends on the fill state of adjacent pixels.
        //
        // At edge 'ce' of pixel (cx, cy), we need to find the next boundary
        // edge. We look at the 4 edges of the current pixel cell and check
        // which is the next boundary edge in CCW order for outer contours.
        //
        // Simplified turn logic: after traversing edge 'ce', check the
        // corner pixel states to determine whether to go straight, turn left,
        // or turn right.
        int next_edge = ce;
        int next_x = cx, next_y = cy;

        // Check pixel states around the current edge endpoint.
        // The two pixels adjacent to edge ce determine the turn.
        bool p1 = is_filled(safe_sample(layer,
            cx + EDGE_PX1_DX[ce], cy + EDGE_PX1_DY[ce]));
        bool p2 = is_filled(safe_sample(layer,
            cx + EDGE_PX2_DX[ce], cy + EDGE_PX2_DY[ce]));

        // Move to next pixel cell along the edge direction.
        int move_dx = TRACE_DX[ce];
        int move_dy = TRACE_DY[ce];

        // At the end of this edge, check the corner for turn direction.
        // The "ahead" pixel determines left/right turn.
        int ahead_dx = 0, ahead_dy = 0;
        switch (ce) {
        case 0: ahead_dx = 1; ahead_dy = -1; break; // top-right
        case 1: ahead_dx = 1; ahead_dy =  1; break; // bottom-right
        case 2: ahead_dx = -1; ahead_dy = 1; break; // bottom-left
        case 3: ahead_dx = -1; ahead_dy = -1; break; // top-left
        }

        // The pixel "ahead of" the edge direction (p2 side, forward).
        int32_t check_x = cx + move_dx;
        int32_t check_y = cy + move_dy;
        bool ahead_filled = is_filled(safe_sample(layer, check_x + ahead_dx - move_dx,
                                                    check_y + ahead_dy - move_dy));

        // Simplified: check the pixel on the p2 side at the next position.
        int32_t nx1 = cx + move_dx + EDGE_PX1_DX[ce];
        int32_t ny1 = cy + move_dy + EDGE_PX1_DY[ce];
        int32_t nx2 = cx + move_dx + EDGE_PX2_DX[ce];
        int32_t ny2 = cy + move_dy + EDGE_PX2_DY[ce];
        bool next_p1 = is_filled(safe_sample(layer, nx1, ny1));
        bool next_p2 = is_filled(safe_sample(layer, nx2, ny2));

        if (next_p1 != next_p2) {
            // Straight ahead: same edge, next pixel.
            next_edge = ce;
            next_x = cx + move_dx;
            next_y = cy + move_dy;
        } else {
            // Turn: try left turn first (CCW for outer).
            int left_edge = (ce + 3) % 4;
            int32_t lx1 = cx + EDGE_PX1_DX[left_edge];
            int32_t ly1 = cy + EDGE_PX1_DY[left_edge];
            int32_t lx2 = cx + EDGE_PX2_DX[left_edge];
            int32_t ly2 = cy + EDGE_PX2_DY[left_edge];
            bool lp1 = is_filled(safe_sample(layer, lx1, ly1));
            bool lp2 = is_filled(safe_sample(layer, lx2, ly2));

            if (lp1 != lp2) {
                next_edge = left_edge;
                next_x = cx;
                next_y = cy;
            } else {
                // Right turn.
                int right_edge = (ce + 1) % 4;
                next_edge = right_edge;
                // Move to the pixel adjacent to the right edge.
                next_x = cx + TRACE_DX[ce] + TRACE_DX[right_edge];
                next_y = cy + TRACE_DY[ce] + TRACE_DY[right_edge];
            }
        }

        cx = next_x; cy = next_y; ce = next_edge;

        // Safety: if we moved out of bounds, terminate the contour.
        if (cx < 0 || cx >= layer.width || cy < 0 || cy >= layer.height) break;

        // Check for loop closure.
        if (step > 0 && cx == start_x && cy == start_y && ce == start_edge)
            break;
    }

    return contour;
}

// --- Wall Generation (contour offsetting) ---

std::vector<VoxelContour> VoxelSlicer::generate_walls(
    const VoxelContour& contour, int num_loops, bool is_outer) const
{
    std::vector<VoxelContour> walls;
    if (num_loops <= 0 || contour.empty()) return walls;

    // Simplified offset: scale the contour inward/outward by integer pixel amounts.
    // The contour points are in 2x-scaled integer coordinates.
    // Each wall loop is offset by the extrusion width in pixel units.

    double extrusion_pixels = m_config.extrusion_width / m_config.layer_height_mm;
    // Clamp to reasonable range.
    int offset_steps = std::max(1, static_cast<int>(std::round(extrusion_pixels * 0.5)));

    for (int loop = 0; loop < num_loops; ++loop) {
        VoxelContour offset_contour;
        int offset_amount = loop * offset_steps * 2; // in 2x-scaled coords

        if (offset_amount == 0) {
            offset_contour = contour;
        } else {
            // For now, keep the same contour shape; offset would require
            // full polygon offsetting (Clipper). We'll note this as a
            // simplification that works for blocky voxel models.
            offset_contour = contour;

            // Apply simple shift for closed contours: move each point
            // along its approximate normal.
            int n = static_cast<int>(contour.size());
            for (int i = 0; i < n; ++i) {
                int prev = (i + n - 1) % n;
                int next = (i + 1) % n;

                // Approximate normal direction from neighbors.
                int dx = contour[next].x - contour[prev].x;
                int dy = contour[next].y - contour[prev].y;

                // Normal (perpendicular, outward for outer contours).
                int nx = (is_outer ? -dy : dy);
                int ny = (is_outer ? dx : -dx);

                double len = std::sqrt(static_cast<double>(nx) * nx + dy * dy);
                if (len < 1e-6) { offset_contour[i] = contour[i]; continue; }

                offset_contour[i].x = contour[i].x +
                    static_cast<int32_t>(std::round(nx / len * offset_amount));
                offset_contour[i].y = contour[i].y +
                    static_cast<int32_t>(std::round(ny / len * offset_amount));
            }
        }
        walls.push_back(std::move(offset_contour));
    }
    return walls;
}

// --- Fill Generation ---

void VoxelSlicer::generate_fill(VoxelSliceLayer& slice, const VoxelLayer& layer) const
{
    if (m_config.fill_density <= 0.0f) return;

    // Rectilinear fill: parallel lines at the configured angle, spaced by density.
    double angle_rad = m_config.fill_angle_deg * M_PI / 180.0;
    double cos_a = std::cos(angle_rad);
    double sin_a = std::sin(angle_rad);

    // Spacing between fill lines in pixels.
    double line_spacing_px = m_config.extrusion_width /
        (m_config.fill_density * m_config.layer_height_mm);

    // Bounding box of the layer in pixel coords.
    double cx = layer.width * 0.5;
    double cy = layer.height * 0.5;
    double diag = std::sqrt(static_cast<double>(layer.width) * layer.width +
                             static_cast<double>(layer.height) * layer.height);

    int num_lines = std::max(1, static_cast<int>(diag / line_spacing_px));

    for (int i = 0; i < num_lines; ++i) {
        double offset = (i - num_lines / 2.0) * line_spacing_px;

        // Line in rotated coordinate system: x*cos + y*sin = offset
        // We trace this line across the layer bounding box.
        double t_min = -diag;
        double t_max =  diag;

        // Sample along the line, collecting segments where interior.
        std::vector<std::pair<double, double>> segments;
        bool in_segment = false;
        double seg_start = 0.0;
        double sample_step = 0.5; // sample every half pixel

        for (double t = t_min; t <= t_max; t += sample_step) {
            // Un-rotate: world pt = (offset*cos - t*sin, offset*sin + t*cos)
            double px = offset * cos_a - t * sin_a + cx;
            double py = offset * sin_a + t * cos_a + cy;

            int32_t ix = static_cast<int32_t>(std::round(px));
            int32_t iy = static_cast<int32_t>(std::round(py));

            bool inside = (ix >= 0 && ix < layer.width &&
                            iy >= 0 && iy < layer.height &&
                            is_filled(layer.at(ix, iy)));

            if (inside && !in_segment) {
                in_segment = true;
                seg_start = t;
            } else if (!inside && in_segment) {
                in_segment = false;
                double seg_end = t - sample_step;
                if (seg_end - seg_start > sample_step) {
                    // Convert segment endpoints to pixel coords.
                    double sx = offset * cos_a - seg_start * sin_a + cx;
                    double sy = offset * sin_a + seg_start * cos_a + cy;
                    double ex = offset * cos_a - seg_end * sin_a + cx;
                    double ey = offset * sin_a + seg_end * cos_a + cy;

                    VoxelSliceLayer::FillSegment seg;
                    seg.start = {static_cast<int32_t>(std::round(sx * 2)),
                                  static_cast<int32_t>(std::round(sy * 2))};
                    seg.end   = {static_cast<int32_t>(std::round(ex * 2)),
                                  static_cast<int32_t>(std::round(ey * 2))};
                    slice.fill_segments.push_back(seg);
                }
            }
        }
    }
}

// --- Support Detection ---

bool VoxelSlicer::needs_support(const VoxelLayer& current, const VoxelLayer& below,
                                  int32_t x, int32_t y) const
{
    // O(1) integer lookup: a voxel needs support if it is filled
    // and the voxel directly below it is empty.
    // This replaces the traditional floating-point normal + angle threshold check.
    //
    // Section 3.2 advantage #5: "支撑判断 O(1) 整数查表"

    if (!is_filled(safe_sample(current, x, y))) return false;
    if (safe_sample(below, x, y) >= 0.5f) return false; // supported from below

    // Check diagonal support too (neighbors below).
    for (int dy = -1; dy <= 1; dy += 2)
        for (int dx = -1; dx <= 1; dx += 2)
            if (safe_sample(below, x + dx, y + dy) >= 0.5f)
                return false;

    return true;
}

// --- Main Slice ---

std::vector<VoxelSliceLayer> VoxelSlicer::slice(const VoxelGrid& grid) const
{
    std::vector<VoxelSliceLayer> layers;
    layers.reserve(grid.size_z());

    // Physical layer height in voxel units.
    float voxel_height_mm = grid.voxel_size_mm();
    int step_z = std::max(1, static_cast<int>(std::round(m_config.layer_height_mm / voxel_height_mm)));

    // Previous layer data for support detection.
    VoxelLayer prev_layer;

    for (int32_t z = 0; z < grid.size_z(); z += step_z) {
        VoxelLayer layer = grid.extract_layer(z);

        VoxelSliceLayer slice;
        slice.layer_z   = z;
        slice.world_z_mm = grid.origin_mm().z() + z * voxel_height_mm;

        // Extract contours from this layer.
        extract_contours(layer, slice.outer_contours, slice.inner_contours);

        // Generate walls from outer contours.
        for (const auto& contour : slice.outer_contours) {
            auto walls = generate_walls(contour, m_config.wall_loops, true);
            // Store as additional outer contours (simplified: treated as separate loops).
            for (size_t w = 1; w < walls.size(); ++w)
                slice.outer_contours.push_back(std::move(walls[w]));
        }

        // Generate infill.
        generate_fill(slice, layer);

        // Support detection (if enabled and we have a previous layer).
        if (m_config.enable_support && !prev_layer.empty()) {
            for (int32_t y = 0; y < layer.height; ++y) {
                for (int32_t x = 0; x < layer.width; ++x) {
                    if (needs_support(layer, prev_layer, x, y)) {
                        // Mark support region: add a small filled block below.
                        // For now, we just note which voxels need support;
                        // full support structure generation is Phase 3+.
                    }
                }
            }
        }

        layers.push_back(std::move(slice));
        prev_layer = std::move(layer);
    }

    return layers;
}

std::vector<VoxelSliceLayer> VoxelSlicer::slice(const Octree& octree, float voxel_resolution_mm) const
{
    VoxelGrid grid = octree.to_grid(voxel_resolution_mm);
    return slice(grid);
}

// --- G-code Generation ---

std::string VoxelSlicer::generate_gcode(const std::vector<VoxelSliceLayer>& layers) const
{
    std::ostringstream gcode;
    gcode << std::fixed << std::setprecision(3);

    gcode << gcode_header();

    for (size_t li = 0; li < layers.size(); ++li) {
        const auto& slice = layers[li];
        gcode << gcode_layer_change(static_cast<int>(li), slice.world_z_mm);

        // Extrude outer contours.
        for (const auto& contour : slice.outer_contours) {
            if (contour.size() < 2) continue;
            // Move to start.
            double sx = contour[0].x * 0.5 * m_config.layer_height_mm;
            double sy = contour[0].y * 0.5 * m_config.layer_height_mm;
            gcode << gcode_travel_move(sx, sy);

            double line_width = m_config.extrusion_width;
            double layer_h    = m_config.layer_height_mm;

            for (size_t i = 1; i < contour.size(); ++i) {
                double ex = contour[i].x * 0.5 * layer_h;
                double ey = contour[i].y * 0.5 * layer_h;
                double dx = ex - m_current_x;
                double dy = ey - m_current_y;
                double dist = std::sqrt(dx * dx + dy * dy);
                double e_inc = dist * line_width * layer_h /
                    (M_PI * (m_config.nozzle_diameter / 2.0) * (m_config.nozzle_diameter / 2.0));
                m_current_e += e_inc;
                gcode << gcode_extrusion_move(ex, ey, m_current_e, 1200.0);
            }
            // Close the loop back to start.
            double dx = sx - m_current_x;
            double dy = sy - m_current_y;
            double dist = std::sqrt(dx * dx + dy * dy);
            double e_inc = dist * line_width * layer_h /
                (M_PI * (m_config.nozzle_diameter / 2.0) * (m_config.nozzle_diameter / 2.0));
            m_current_e += e_inc;
            gcode << gcode_extrusion_move(sx, sy, m_current_e, 1200.0);
        }

        // Extrude fill segments.
        for (const auto& seg : slice.fill_segments) {
            double sx = seg.start.x * 0.5 * m_config.layer_height_mm;
            double sy = seg.start.y * 0.5 * m_config.layer_height_mm;
            double ex = seg.end.x   * 0.5 * m_config.layer_height_mm;
            double ey = seg.end.y   * 0.5 * m_config.layer_height_mm;

            gcode << gcode_travel_move(sx, sy);
            double dx = ex - sx;
            double dy = ey - sy;
            double dist = std::sqrt(dx * dx + dy * dy);
            double line_width = m_config.extrusion_width * m_config.fill_density;
            double layer_h    = m_config.layer_height_mm;
            double e_inc = dist * line_width * layer_h /
                (M_PI * (m_config.nozzle_diameter / 2.0) * (m_config.nozzle_diameter / 2.0));
            m_current_e += e_inc;
            gcode << gcode_extrusion_move(ex, ey, m_current_e, 2400.0);
        }
    }

    gcode << gcode_footer();
    return gcode.str();
}

std::string VoxelSlicer::slice_to_gcode(const VoxelGrid& grid) const
{
    return generate_gcode(slice(grid));
}

std::string VoxelSlicer::slice_to_gcode(const Octree& octree, float voxel_resolution_mm) const
{
    return generate_gcode(slice(octree, voxel_resolution_mm));
}

// --- G-code Helpers ---

std::string VoxelSlicer::gcode_header() const
{
    m_current_e = 0.0;
    m_current_x = 0.0;
    m_current_y = 0.0;

    std::ostringstream g;
    g << std::fixed << std::setprecision(3);
    g << "; VoxelSlicer G-code\n";
    g << "; Generated from voxel pipeline (Section 3.1)\n";
    g << "; No intermediate mesh format used.\n";
    g << "G21 ; set units to millimeters\n";
    g << "G90 ; use absolute coordinates\n";
    g << "M83 ; use relative distances for extrusion\n";
    g << "G92 E0 ; reset extruder\n";
    g << "G1 Z5.0 F3000 ; move to safe Z\n";
    g << "G1 X0 Y0 F6000 ; move to origin\n";
    return g.str();
}

std::string VoxelSlicer::gcode_footer() const
{
    std::ostringstream g;
    g << std::fixed << std::setprecision(3);
    g << "G91 ; relative positioning\n";
    g << "G1 Z10 F600 ; lift nozzle\n";
    g << "G90 ; absolute positioning\n";
    g << "M104 S0 ; turn off extruder\n";
    g << "M140 S0 ; turn off bed\n";
    g << "M84 ; disable motors\n";
    return g.str();
}

std::string VoxelSlicer::gcode_layer_change(int layer_idx, double z_mm) const
{
    std::ostringstream g;
    g << std::fixed << std::setprecision(3);
    g << "; LAYER:" << layer_idx << " Z:" << z_mm << "\n";
    g << "G1 Z" << z_mm << " F600 ; move to layer height\n";
    return g.str();
}

std::string VoxelSlicer::gcode_extrusion_move(double x_mm, double y_mm, double e,
                                               double feedrate) const
{
    std::ostringstream g;
    g << std::fixed << std::setprecision(3);
    g << "G1 X" << x_mm << " Y" << y_mm << " E" << e
      << " F" << feedrate << " ; extrude\n";
    m_current_x = x_mm;
    m_current_y = y_mm;
    return g.str();
}

std::string VoxelSlicer::gcode_travel_move(double x_mm, double y_mm) const
{
    std::ostringstream g;
    g << std::fixed << std::setprecision(3);
    g << "G1 X" << x_mm << " Y" << y_mm << " F6000 ; travel\n";
    m_current_x = x_mm;
    m_current_y = y_mm;
    return g.str();
}

double VoxelSlicer::pixel_x_to_world(int32_t px, const VoxelGrid& grid) const
{
    return grid.origin_mm().x() + px * grid.voxel_size_mm();
}

double VoxelSlicer::pixel_y_to_world(int32_t py, const VoxelGrid& grid) const
{
    return grid.origin_mm().y() + py * grid.voxel_size_mm();
}

} // namespace Slic3r
