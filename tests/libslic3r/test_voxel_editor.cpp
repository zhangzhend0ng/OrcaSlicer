#include <catch2/catch.hpp>

#include <libslic3r/TriangleMesh.hpp>
#include <libslic3r/VoxelEditor/VoxelTypes.hpp>
#include <libslic3r/VoxelEditor/VoxelGrid.hpp>
#include <libslic3r/VoxelEditor/Octree.hpp>
#include <libslic3r/VoxelEditor/MeshVoxelizer.hpp>
#include <libslic3r/VoxelEditor/VoxelSlicer.hpp>
#include <libslic3r/VoxelEditor/VoxelOperations.hpp>

#include <string>
#include <sstream>
#include <cmath>

using namespace Slic3r;

// Helper: create a small test cube mesh.
static TriangleMesh make_test_cube(float size = 8.0f) {
    indexed_triangle_set its = its_make_cube(size, size, size);
    return TriangleMesh(its);
}

TEST_CASE("VoxelGrid: basic access and bounds", "[VoxelEditor]") {
    VoxelGrid grid(10, 10, 10, 0.0f);
    REQUIRE(grid.total_voxels() == 1000);
    REQUIRE(grid.in_bounds(5, 5, 5));
    REQUIRE(!grid.in_bounds(-1, 0, 0));
    REQUIRE(!grid.in_bounds(10, 0, 0));

    grid.at(3, 4, 5) = 0.7f;
    REQUIRE(grid.at(3, 4, 5) == 0.7f);
}

TEST_CASE("VoxelGrid: fill and region operations", "[VoxelEditor]") {
    VoxelGrid grid(10, 10, 10, 0.0f);
    grid.fill(1.0f);
    REQUIRE(grid.at(5, 5, 5) == 1.0f);

    grid.fill_region(VoxelBBox({2,2,2}, {7,7,7}), 0.5f);
    REQUIRE(grid.at(5, 5, 5) == 0.5f);
    REQUIRE(grid.at(0, 0, 0) == 1.0f);
}

TEST_CASE("VoxelGrid: boolean operations", "[VoxelEditor]") {
    VoxelGrid a(5, 5, 5, 0.0f);
    VoxelGrid b(5, 5, 5, 0.0f);
    a.at(2, 2, 2) = 1.0f;
    b.at(2, 2, 2) = 1.0f;
    b.at(3, 3, 3) = 1.0f;

    a.apply_op(b, VoxelOp::Union);
    REQUIRE(a.at(2, 2, 2) == 1.0f);
    REQUIRE(a.at(3, 3, 3) == 1.0f);

    a.apply_op(b, VoxelOp::Subtract);
    REQUIRE(a.at(2, 2, 2) == 0.0f); // was 1.0, b has 1.0 -> cleared
    REQUIRE(a.at(3, 3, 3) == 0.0f);
}

TEST_CASE("Octree: basic construction and sampling", "[VoxelEditor]") {
    BoundingBoxf3 world({0,0,0}, {8,8,8});
    Octree tree;
    tree.set_world_bbox(world);
    tree.fill_region(BoundingBoxf3({2,2,2}, {6,6,6}), 1.0f);

    REQUIRE(tree.sample(Vec3d(4, 4, 4)) >= 0.5f);
    REQUIRE(tree.sample(Vec3d(1, 1, 1)) < 0.5f);

    REQUIRE(tree.node_count() > 0);
}

TEST_CASE("Octree: sphere brush", "[VoxelEditor]") {
    BoundingBoxf3 world({0,0,0}, {10,10,10});
    Octree tree;
    tree.set_world_bbox(world);
    tree.brush_sphere(Vec3d(5, 5, 5), 3.0f, 1.0f);

    REQUIRE(tree.sample(Vec3d(5, 5, 5)) >= 0.5f);
    REQUIRE(tree.sample(Vec3d(1, 1, 1)) < 0.5f);
}

TEST_CASE("Octree: from grid round-trip", "[VoxelEditor]") {
    VoxelGrid grid(4, 4, 4, 0.0f);
    grid.at(1, 1, 1) = 1.0f;
    grid.at(2, 2, 2) = 1.0f;
    grid.set_origin(Vec3d(0, 0, 0));
    grid.set_voxel_size(2.0f);

    Octree tree = Octree::from_grid(grid);
    VoxelGrid grid2 = tree.to_grid(2.0f);

    int filled1 = 0, filled2 = 0;
    for (int32_t z = 0; z < 4; ++z)
        for (int32_t y = 0; y < 4; ++y)
            for (int32_t x = 0; x < 4; ++x) {
                if (grid.at(x, y, z) >= 0.5f) ++filled1;
                if (grid2.at(x, y, z) >= 0.5f) ++filled2;
            }
    REQUIRE(filled1 > 0);
    REQUIRE(filled2 > 0);
}

TEST_CASE("VoxelOperations: make_box template", "[VoxelEditor]") {
    BoundingBoxf3 bbox({0,0,0}, {8,8,8});
    Octree box = VoxelOps::make_box(bbox, 2.0f);
    REQUIRE(box.node_count() > 0);
    REQUIRE(box.sample(Vec3d(4, 4, 4)) >= 0.5f);
}

TEST_CASE("VoxelOperations: boolean subtract", "[VoxelEditor]") {
    BoundingBoxf3 bbox({0,0,0}, {10,10,10});
    Octree cube = VoxelOps::make_box(bbox, 2.0f);
    Octree sphere = VoxelOps::make_sphere(BoundingBoxf3({3,3,3}, {7,7,7}), 2.0f);
    Octree result = VoxelOps::boolean_subtract(cube, sphere, 2.0f);

    REQUIRE(result.sample(Vec3d(5, 5, 5)) < 0.5f); // center subtracted
    REQUIRE(result.sample(Vec3d(1, 1, 1)) >= 0.5f); // corner remains
}

TEST_CASE("VoxelOperations: hollow", "[VoxelEditor]") {
    BoundingBoxf3 bbox({0,0,0}, {10,10,10});
    Octree solid = VoxelOps::make_box(bbox, 2.0f);
    Octree shell = VoxelOps::hollow(solid, 3.0f, 2.0f);

    REQUIRE(shell.sample(Vec3d(5, 5, 5)) < 0.5f); // hollow center
    REQUIRE(shell.sample(Vec3d(1, 1, 1)) >= 0.5f); // surface
}

TEST_CASE("VoxelSlicer: generates G-code", "[VoxelEditor]") {
    // Create a simple 2-layer voxel grid (small column).
    VoxelGrid grid(8, 8, 4, 0.0f);
    grid.set_origin(Vec3d(0, 0, 0));
    grid.set_voxel_size(1.0f);

    // Mark a 2x2x2 block as filled.
    for (int32_t z = 1; z < 3; ++z)
        for (int32_t y = 3; y < 5; ++y)
            for (int32_t x = 3; x < 5; ++x)
                grid.at(x, y, z) = 1.0f;

    VoxelSlicerConfig cfg;
    cfg.layer_height_mm = 1.0f;
    cfg.nozzle_diameter  = 0.4f;
    cfg.wall_loops       = 1;
    VoxelSlicer slicer(cfg);

    std::string gcode = slicer.slice_to_gcode(grid);
    REQUIRE(!gcode.empty());
    REQUIRE(gcode.find("G21") != std::string::npos);
    REQUIRE(gcode.find("G1") != std::string::npos);
}

TEST_CASE("MeshVoxelizer: voxelize small cube", "[VoxelEditor][.slow]") {
    TriangleMesh cube = make_test_cube(8.0f);
    MeshVoxelizer::Config cfg;
    cfg.voxel_size_mm = 4.0f;
    cfg.fill_interior = true;
    MeshVoxelizer voxelizer(cfg);
    VoxelGrid grid = voxelizer.voxelize(cube);

    int filled = 0;
    for (int32_t z = 0; z < grid.size_z(); ++z)
        for (int32_t y = 0; y < grid.size_y(); ++y)
            for (int32_t x = 0; x < grid.size_x(); ++x)
                if (grid.at(x, y, z) >= 0.5f) ++filled;
    REQUIRE(filled > 0);
}

TEST_CASE("VoxelEditor: full pipeline", "[VoxelEditor][.slow]") {
    // End-to-end: primitive -> edit -> slice -> G-code.
    BoundingBoxf3 bbox({0,0,0}, {10,10,10});
    Octree box = VoxelOps::make_box(bbox, 2.0f);
    Octree hollowed = VoxelOps::hollow(box, 3.0f, 2.0f);

    VoxelSlicerConfig cfg;
    cfg.layer_height_mm = 1.0f;
    cfg.nozzle_diameter  = 0.4f;
    cfg.wall_loops       = 1;
    VoxelSlicer slicer(cfg);

    std::string gcode = slicer.slice_to_gcode(hollowed, 2.0f);
    REQUIRE(!gcode.empty());
    REQUIRE(gcode.find("M84") != std::string::npos);
}
