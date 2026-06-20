#include "catch2/catch.hpp"
#include "slic3r/App/ConfigValidationModel.hpp"
#include "slic3r/App/MixedFilamentViewModel.hpp"
#include "slic3r/App/UndoRedoController.hpp"
#include "libslic3r/PrintConfig.hpp"

using namespace Slic3r;

// ============================================================
// Integration tests: pure logic extracted from GUI files
// All tests run WITHOUT wxApp, wxPanel, or any GUI framework.
// ============================================================

TEST_CASE("Extracted: bedTypeToRuleKey covers known types", "[ExtractedLogic]") {
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(0) == "btPEI");
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(1) == "btGESP");
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(-1) == "");
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(999) == "");
}

TEST_CASE("Extracted: nozzleDiameterToRuleKey formats correctly", "[ExtractedLogic]") {
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.4) == "0.4mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.60) == "0.6mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.80) == "0.8mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(1.0) == "1mm");
}

TEST_CASE("Extracted: ConfigValidation set operations", "[ExtractedLogic]") {
    std::vector<std::string> a = {"PLA","ABS","PETG","TPU"};
    std::vector<std::string> b = {"PLA","PETG","NYLON"};

    auto inter = ConfigValidationModel::intersect(a, b);
    REQUIRE(inter.size() == 2);

    auto uni = ConfigValidationModel::unionSets(a, b);
    REQUIRE(uni.size() == 5);

    auto sub = ConfigValidationModel::subtract(a, b);
    REQUIRE(sub.size() == 2);
    REQUIRE(sub[0] == "ABS");
    REQUIRE(sub[1] == "TPU");
}

TEST_CASE("Extracted: resolveModelConfig fills filament slots", "[ExtractedLogic]") {
    DynamicPrintConfig config;
    config.set_key_value("extruder", new ConfigOptionInt(2));

    auto resolved = ConfigValidationModel::resolveModelConfig(config);
    REQUIRE(resolved.opt_int("wall_filament") == 2);
    REQUIRE(resolved.opt_int("sparse_infill_filament") == 2);
    REQUIRE(resolved.opt_int("solid_infill_filament") == 2);
}

TEST_CASE("Extracted: MixedFilamentVM makeLabel", "[ExtractedLogic]") {
    MixedFilament mf;
    mf.component_a = 1; mf.component_b = 2;
    REQUIRE(MixedFilamentViewModel::makeLabel(mf) == "F1+F2");

    mf.component_c = 3;
    REQUIRE(MixedFilamentViewModel::makeLabel(mf) == "F1+F2+F3");
}

TEST_CASE("Extracted: MixedFilamentVM blendDisplayColor", "[ExtractedLogic]") {
    std::vector<std::string> colors = {"#FF0000FF", "#0000FFFF"};
    std::vector<unsigned int> seq = {1, 2};
    std::string result = MixedFilamentViewModel::blendDisplayColor(colors, seq);
    REQUIRE(!result.empty());
    REQUIRE(result[0] == '#');
    REQUIRE(result.size() == 9); // #RRGGBBAA
}

TEST_CASE("Extracted: UndoRedoController full cycle", "[ExtractedLogic]") {
    UndoRedoController urc;
    int val = 0;

    // Push: set val to 42, undo sets it back to 0
    urc.push([&]{ val = 42; }, [&]{ val = 0; }, "set 42");
    val = 42;
    REQUIRE(urc.canUndo_.get());
    REQUIRE_FALSE(urc.canRedo_.get());

    // Undo
    urc.undo();
    REQUIRE(val == 0);
    REQUIRE_FALSE(urc.canUndo_.get());
    REQUIRE(urc.canRedo_.get());

    // Redo
    urc.redo();
    REQUIRE(val == 42);
    REQUIRE(urc.canUndo_.get());
    REQUIRE_FALSE(urc.canRedo_.get());
}

TEST_CASE("Extracted: UndoRedoController discards redo on new push", "[ExtractedLogic]") {
    UndoRedoController urc;
    int val = 0;

    urc.push([&]{ val = 1; }, [&]{ val = 0; }, "set 1");
    val = 1;
    urc.undo(); // val=0
    REQUIRE(urc.canRedo_.get());

    // New push should discard redo history
    urc.push([&]{ val = 42; }, [&]{ val = 0; }, "set 42");
    val = 42;
    REQUIRE_FALSE(urc.canRedo_.get());
    REQUIRE(val == 42);
}
