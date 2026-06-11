#include <catch2/catch_test_macros.hpp>

#include "libslic3r/Model.hpp"
#include "libslic3r/ModelColor.hpp"

#include <algorithm>

using namespace Slic3r;

TEST_CASE("extract_model_extruders returns empty on empty model", "[ModelColor]")
{
    Model model;
    std::vector<int> ids = extract_model_extruders(model);
    REQUIRE(ids.empty());
}

TEST_CASE("extract_model_extruders collects volume-level extruder", "[ModelColor]")
{
    Model model;
    ModelObject *obj = model.add_object();
    REQUIRE(obj);

    TriangleMesh mesh = make_cube(10, 10, 10);
    ModelVolume *vol = obj->add_volume(mesh);
    REQUIRE(vol);

    // By default extruder 0 → get_extruders() returns {1}
    vol->config.set("extruder", 0);

    std::vector<int> ids = extract_model_extruders(model);
    REQUIRE(ids.size() >= 1);
    CHECK(std::find(ids.begin(), ids.end(), 1) != ids.end());
}

TEST_CASE("extract_model_extruders skips negative volumes", "[ModelColor]")
{
    Model model;
    ModelObject *obj = model.add_object();

    TriangleMesh mesh = make_cube(10, 10, 10);

    // negative volume — should be skipped
    ModelVolume *neg = obj->add_volume(mesh, ModelVolumeType::NEGATIVE_VOLUME);
    REQUIRE(neg);
    neg->config.set("extruder", 5);

    std::vector<int> ids = extract_model_extruders(model);
    REQUIRE(ids.empty());
}

TEST_CASE("extract_model_extruders deduplicates", "[ModelColor]")
{
    Model model;
    ModelObject *obj = model.add_object();

    TriangleMesh mesh = make_cube(10, 10, 10);
    ModelVolume *v1 = obj->add_volume(mesh);
    ModelVolume *v2 = obj->add_volume(mesh);
    REQUIRE(v1);
    REQUIRE(v2);

    v1->config.set("extruder", 3);
    v2->config.set("extruder", 3);

    std::vector<int> ids = extract_model_extruders(model);
    REQUIRE(ids.size() == 1);
    CHECK(ids[0] == 3);
}

TEST_CASE("extract_model_colors empty without colours", "[ModelColor]")
{
    Model model;

    std::vector<std::string> colours = extract_model_colors(model, {});
    REQUIRE(colours.empty());
}

TEST_CASE("extract_model_colors maps extruder to filament_colour", "[ModelColor]")
{
    Model model;
    ModelObject *obj = model.add_object();

    TriangleMesh mesh = make_cube(10, 10, 10);
    ModelVolume *vol = obj->add_volume(mesh);
    vol->config.set("extruder", 2); // 1-based → index 1

    std::vector<std::string> filament_colours = {
        "#FF0000",  // extruder 1 → red
        "#00FF00",  // extruder 2 → green
        "#0000FF",  // extruder 3 → blue
    };

    std::vector<std::string> colours = extract_model_colors(
        model, filament_colours);
    REQUIRE(colours.size() == 1);
    CHECK(colours[0] == "#00FF00");
}

TEST_CASE("extract_model_colors deduplicates identical colours", "[ModelColor]")
{
    Model model;
    ModelObject *obj = model.add_object();

    TriangleMesh mesh = make_cube(10, 10, 10);

    // Two volumes with same extruder → same colour, deduplicated
    ModelVolume *v1 = obj->add_volume(mesh);
    ModelVolume *v2 = obj->add_volume(mesh);
    v1->config.set("extruder", 1);
    v2->config.set("extruder", 1);

    std::vector<std::string> filament_colours = {"#ABCDEF"};

    std::vector<std::string> colours = extract_model_colors(
        model, filament_colours);
    REQUIRE(colours.size() == 1);
    CHECK(colours[0] == "#ABCDEF");
}

TEST_CASE("extract_model_colors skips empty colour string", "[ModelColor]")
{
    Model model;
    ModelObject *obj = model.add_object();

    TriangleMesh mesh = make_cube(10, 10, 10);
    ModelVolume *vol = obj->add_volume(mesh);
    vol->config.set("extruder", 1);

    // Empty colour — should not appear in result
    std::vector<std::string> filament_colours = {""};

    std::vector<std::string> colours = extract_model_colors(
        model, filament_colours);
    REQUIRE(colours.empty());
}

TEST_CASE("extract_model_colors returns sorted output", "[ModelColor]")
{
    Model model;
    ModelObject *obj = model.add_object();

    TriangleMesh mesh = make_cube(10, 10, 10);

    ModelVolume *v1 = obj->add_volume(mesh);
    ModelVolume *v2 = obj->add_volume(mesh);
    v1->config.set("extruder", 3);
    v2->config.set("extruder", 1);

    std::vector<std::string> filament_colours = {
        "#AAAAAA",  // extruder 1
        "#BBBBBB",  // extruder 2
        "#CCCCCC",  // extruder 3
    };

    std::vector<std::string> colours = extract_model_colors(
        model, filament_colours);
    REQUIRE(colours.size() == 2);

    // Output is sorted by string value (not extruder order)
    REQUIRE(std::is_sorted(colours.begin(), colours.end()));
}

TEST_CASE("extract_model_colors out-of-range extruder does not crash", "[ModelColor]")
{
    Model model;
    ModelObject *obj = model.add_object();

    TriangleMesh mesh = make_cube(10, 10, 10);
    ModelVolume *vol = obj->add_volume(mesh);
    // Extruder ID beyond filament_colours table
    vol->config.set("extruder", 99);

    std::vector<std::string> filament_colours = {"#FF0000"};

    // Should not crash — out-of-range IDs are skipped gracefully
    std::vector<std::string> colours = extract_model_colors(
        model, filament_colours);
    REQUIRE(colours.empty());
}

TEST_CASE("extract_model_extruders handles modifier volumes", "[ModelColor]")
{
    Model model;
    ModelObject *obj = model.add_object();

    TriangleMesh mesh = make_cube(10, 10, 10);

    ModelVolume *mod = obj->add_volume(mesh, ModelVolumeType::PARAMETER_MODIFIER);
    REQUIRE(mod);
    mod->config.set("extruder", 7);

    std::vector<int> ids = extract_model_extruders(model);
    REQUIRE(ids.size() == 1);
    CHECK(ids[0] == 7);
}
