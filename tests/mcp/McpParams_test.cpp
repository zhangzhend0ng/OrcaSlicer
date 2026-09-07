#include <catch_main.hpp>

#include "slic3r/GUI/Mcp/McpParams.hpp"

#include <string>

using namespace Slic3r::Mcp::McpParams;

TEST_CASE("object param scope matches object+region config options", "[McpParams]") {
    // PrintObjectConfig scope
    REQUIRE(is_valid_object_param("layer_height"));
    REQUIRE(is_valid_object_param("enable_support"));
    // PrintRegionConfig scope
    REQUIRE(is_valid_object_param("sparse_infill_density"));
    REQUIRE(is_valid_object_param("wall_loops"));
    // Machine/process-global scope must NOT be writable per-object.
    // Mutation guard: deleting the whitelist lookup fails this test.
    REQUIRE_FALSE(is_valid_object_param("printer_model"));
    REQUIRE_FALSE(is_valid_object_param("printer_settings_id"));
    REQUIRE_FALSE(is_valid_object_param("curr_bed_type"));
    REQUIRE_FALSE(is_valid_object_param("no_such_option_anywhere"));
}

TEST_CASE("plate param whitelist is the dialog-free semantic setters", "[McpParams]") {
    REQUIRE(is_valid_plate_param("curr_bed_type"));
    REQUIRE(is_valid_plate_param("print_sequence"));
    // spiral_mode pops a confirmation dialog on enable: out of scope.
    REQUIRE_FALSE(is_valid_plate_param("spiral_mode"));
    // Object/project scope keys must not slip into the plate whitelist.
    REQUIRE_FALSE(is_valid_plate_param("sparse_infill_density"));
    REQUIRE_FALSE(is_valid_plate_param("layer_height"));
    REQUIRE_FALSE(is_valid_plate_param("no_such_option_anywhere"));
}

TEST_CASE("deserialize_all applies valid typed values", "[McpParams]") {
    Slic3r::DynamicPrintConfig config;
    std::map<std::string, std::string> params = {
        {"sparse_infill_density", "15%"},
        {"enable_support", "1"},
    };
    REQUIRE(deserialize_all(config, params).empty());
    REQUIRE(config.opt_serialize("sparse_infill_density") == "15%");
    REQUIRE(config.opt_serialize("enable_support") == "1");
}

TEST_CASE("deserialize_all reports the rejected entry", "[McpParams]") {
    // Numeric options go through istringstream and fail on garbage. Note:
    // bool options are LENIENT in Orca ("x" coerces to true), so bools are
    // not a usable rejection probe.
    Slic3r::DynamicPrintConfig config;
    std::map<std::string, std::string> params = {
        {"sparse_infill_density", "abc"},
    };
    const std::string error = deserialize_all(config, params);
    REQUIRE(error.find("sparse_infill_density") != std::string::npos);
    REQUIRE(error.find("rejected") != std::string::npos);
}
