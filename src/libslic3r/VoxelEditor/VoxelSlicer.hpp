#ifndef slic3r_VoxelSlicer_hpp_
#define slic3r_VoxelSlicer_hpp_

#include "VoxelEditor/VoxelTypes.hpp"

#include <string>
#include <vector>
#include <cstdint>

namespace Slic3r {

class VoxelGrid;
class Octree;

// A 2D point in pixel coordinates (integer, aligned with the design doc's
// zero-floating-point philosophy).
struct VoxelPoint2D {
    int32_t x, y;
    bool operator==(const VoxelPoint2D& o) const { return x == o.x && y == o.y; }
};

// A 2D polyline: ordered sequence of integer pixel-edge coordinates.
using VoxelContour = std::vector<VoxelPoint2D>;

// One processed layer: contours for walls and fill lines.
struct VoxelSliceLayer {
    int32_t              layer_z;           // z index in voxel space
    double               world_z_mm;        // physical Z height
    std::vector<VoxelContour> outer_contours; // outer perimeters (CCW)
    std::vector<VoxelContour> inner_contours; // inner perimeters / holes (CW)

    // Fill: parallel line segments for infill.
    struct FillSegment {
        VoxelPoint2D start, end;
    };
    std::vector<FillSegment> fill_segments;
};

// Configuration for the voxel slicer.
struct VoxelSlicerConfig {
    float    layer_height_mm  = 0.2f;    // physical layer height
    float    nozzle_diameter   = 0.4f;   // nozzle diameter in mm
    int      wall_loops        = 2;      // number of perimeter loops
    double   extrusion_width   = 0.45;   // line width for extrusion
    float    fill_density      = 0.15f;  // infill density (0..1)
    float    fill_angle_deg    = 45.0f;  // infill angle in degrees
    bool     enable_support    = false;  // generate support structures

    // Sub-voxel precision: maps greyscale voxel values to extrusion width.
    // pixel_value * nozzle_diameter = extrusion width (Section 3.4).
    bool     subvoxel_extrusion = false;
};

// Converts a VoxelGrid or Octree directly to G-code without intermediate
// mesh formats. Implements the pipeline from Section 3.1:
//   Octree → 2D bitmap per layer → edge detection → contours → fill → G-code
//
// All edge detection uses integer arithmetic (zero floating point), matching
// the design doc's claim of "零浮点" for the slicing stage.
class VoxelSlicer {
public:
    explicit VoxelSlicer(const VoxelSlicerConfig& cfg = VoxelSlicerConfig{})
        : m_config(cfg) {}

    // Slice a VoxelGrid into per-layer contour + fill data.
    std::vector<VoxelSliceLayer> slice(const VoxelGrid& grid) const;

    // Slice an Octree (converts to grid internally at target resolution).
    std::vector<VoxelSliceLayer> slice(const Octree& octree, float voxel_resolution_mm = 0.5f) const;

    // Generate complete G-code string from sliced layers.
    // Includes header, per-layer extrusion moves, and footer.
    std::string generate_gcode(const std::vector<VoxelSliceLayer>& layers) const;

    // Convenience: full pipeline from VoxelGrid to G-code string.
    std::string slice_to_gcode(const VoxelGrid& grid) const;

    // Convenience: full pipeline from Octree to G-code string.
    std::string slice_to_gcode(const Octree& octree, float voxel_resolution_mm = 0.5f) const;

    const VoxelSlicerConfig& config() const { return m_config; }

private:
    VoxelSlicerConfig m_config;

    // --- Edge Detection (integer-only Marching Squares variant) ---
    // Extract closed contours from a 2D voxel layer.
    // Uses Moore-neighborhood contour tracing: follows the boundary between
    // filled (>= 0.5) and empty (< 0.5) pixels.
    void extract_contours(const VoxelLayer& layer,
                           std::vector<VoxelContour>& outer,
                           std::vector<VoxelContour>& inner) const;

    // Trace a single contour starting from a boundary edge.
    VoxelContour trace_contour(const VoxelLayer& layer,
                                std::vector<bool>& visited,
                                int32_t start_x, int32_t start_y,
                                int start_edge) const;

    // --- Wall Generation ---
    // Generate offset contours for perimeter walls.
    std::vector<VoxelContour> generate_walls(const VoxelContour& contour,
                                              int num_loops, bool is_outer) const;

    // --- Fill Generation ---
    // Generate infill line segments for a region.
    void generate_fill(VoxelSliceLayer& slice, const VoxelLayer& layer) const;

    // --- Support Detection (O(1) integer table lookup) ---
    // Section 3.2 advantage #5: support check via integer lookup table
    // instead of floating-point normal + angle threshold.
    bool needs_support(const VoxelLayer& current, const VoxelLayer& below,
                        int32_t x, int32_t y) const;

    // --- G-code Helpers ---
    std::string gcode_header() const;
    std::string gcode_footer() const;
    std::string gcode_layer_change(int layer_idx, double z_mm) const;
    std::string gcode_extrusion_move(double x_mm, double y_mm, double e,
                                      double feedrate) const;
    std::string gcode_travel_move(double x_mm, double y_mm) const;

    // Pixel-to-world coordinate conversion.
    double pixel_x_to_world(int32_t px, const VoxelGrid& grid) const;
    double pixel_y_to_world(int32_t py, const VoxelGrid& grid) const;

    // Internal state for G-code generation.
    mutable double m_current_e = 0.0;   // cumulative extrusion
    mutable double m_current_x = 0.0;
    mutable double m_current_y = 0.0;
};

} // namespace Slic3r

#endif // slic3r_VoxelSlicer_hpp_
