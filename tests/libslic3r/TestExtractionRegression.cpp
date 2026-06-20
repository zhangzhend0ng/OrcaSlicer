#include "catch2/catch.hpp"
#include "slic3r/App/ConfigValidationModel.hpp"
#include "slic3r/App/GeometryValidationModel.hpp"
#include "slic3r/App/MixedFilamentViewModel.hpp"
#include "slic3r/App/UndoRedoController.hpp"
#include "libslic3r/PrintConfig.hpp"

#include <Eigen/Geometry>
#include <vector>
#include <string>

using namespace Slic3r;

// ============================================================
// REGRESSION TESTS: verify extracted logic = original behavior
// ============================================================
// Each test runs the SAME inputs through the extracted model
// and verifies the output matches expected behavior.
// These tests serve as golden checks: if extraction changes
// behavior, these tests will catch it.

// ?? ConfigValidation regression ??

TEST_CASE("REGRESSION: bedTypeToRuleKey matches Tab.cpp original", "[Regression]") {
    // Tab.cpp L69-76: static std::string bed_type_to_rule_key(BedType)
    // Matches exact output of original function
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(0) == "btPEI");
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(1) == "btGESP");
    // Unknown types return empty (same as original)
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(42) == "");
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(-5) == "");
}

TEST_CASE("REGRESSION: nozzleDiameterToRuleKey matches Tab.cpp original", "[Regression]") {
    // Tab.cpp L78-88: static std::string nozzle_diameter_to_rule_key(double)
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.4) == "0.4mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.40) == "0.4mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.60) == "0.6mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.8) == "0.8mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(1.0) == "1mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(1.20) == "1.2mm");
    // Edge: whole number
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(2.0) == "2mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.0) == "0mm");
}

TEST_CASE("REGRESSION: resolveModelConfig fills filament slots", "[Regression]") {
    // Tab.cpp L2850+: resolved_model_config_for_tab()
    DynamicPrintConfig cfg;
    cfg.set_key_value("extruder", new ConfigOptionInt(3));

    auto resolved = ConfigValidationModel::resolveModelConfig(cfg);
    REQUIRE(resolved.opt_int("wall_filament") == 3);
    REQUIRE(resolved.opt_int("sparse_infill_filament") == 3);
    REQUIRE(resolved.opt_int("solid_infill_filament") == 3);
}

TEST_CASE("REGRESSION: resolveModelConfig respects existing slots", "[Regression]") {
    DynamicPrintConfig cfg;
    cfg.set_key_value("extruder", new ConfigOptionInt(3));
    cfg.set_key_value("wall_filament", new ConfigOptionInt(1));

    auto resolved = ConfigValidationModel::resolveModelConfig(cfg);
    // wall_filament was already set, should be preserved
    REQUIRE(resolved.opt_int("wall_filament") == 1);
    // Others filled from extruder
    REQUIRE(resolved.opt_int("sparse_infill_filament") == 3);
    REQUIRE(resolved.opt_int("solid_infill_filament") == 3);
}

TEST_CASE("REGRESSION: resolveModelConfig solid_filament from sparse", "[Regression]") {
    // When solid_infill is missing but sparse_infill exists, copy from sparse
    DynamicPrintConfig cfg;
    cfg.set_key_value("sparse_infill_filament", new ConfigOptionInt(2));

    auto resolved = ConfigValidationModel::resolveModelConfig(cfg);
    REQUIRE(resolved.opt_int("solid_infill_filament") == 2);
}

// ?? GeometryValidation regression ??

TEST_CASE("REGRESSION: isLeftHanded identity is right-handed", "[Regression]") {
    // Selection.cpp L2835: identity matrix has determinant 1, not left-handed
    REQUIRE_FALSE(GeometryValidationModel::isLeftHanded(Transform3d::Identity()));
}

TEST_CASE("REGRESSION: isLeftHanded mirror X is left-handed", "[Regression]") {
    Transform3d mirror = Transform3d::Identity();
    mirror(0, 0) = -1.0;
    REQUIRE(GeometryValidationModel::isLeftHanded(mirror));
    REQUIRE(GeometryValidationModel::isLeftHanded(mirror.linear()));
}

TEST_CASE("REGRESSION: isRotationXYSynchronized identical transforms", "[Regression]") {
    auto rot = Eigen::AngleAxisd(0.5, Vec3d::UnitZ()).toRotationMatrix();
    Transform3d t1 = Transform3d::Identity();
    t1.linear() = rot;
    Transform3d t2 = t1;
    REQUIRE(GeometryValidationModel::isRotationXYSynchronized(t1, t2));
}

TEST_CASE("REGRESSION: isRotationXYSynchronized Z-only diff is ok", "[Regression]") {
    Transform3d t1 = Transform3d::Identity();
    Transform3d t2 = Transform3d::Identity();
    t2.linear() = Eigen::AngleAxisd(M_PI / 3.0, Vec3d::UnitZ()).toRotationMatrix();
    REQUIRE(GeometryValidationModel::isRotationXYSynchronized(t1, t2));
}

TEST_CASE("REGRESSION: isRotationXYSynchronized XY diff is not ok", "[Regression]") {
    Transform3d t1 = Transform3d::Identity();
    Transform3d t2 = Transform3d::Identity();
    t2.linear() = Eigen::AngleAxisd(M_PI / 4.0, Vec3d::UnitX()).toRotationMatrix();
    REQUIRE_FALSE(GeometryValidationModel::isRotationXYSynchronized(t1, t2));
}

// ?? MixedFilament regression ??

TEST_CASE("REGRESSION: makeLabel 2 filaments matches Plater.cpp", "[Regression]") {
    MixedFilament mf;
    mf.component_a = 1; mf.component_b = 2;
    REQUIRE(MixedFilamentViewModel::makeLabel(mf) == "F1+F2");
}

TEST_CASE("REGRESSION: makeLabel 3 filaments", "[Regression]") {
    MixedFilament mf;
    mf.component_a = 1; mf.component_b = 2; mf.component_c = 3;
    REQUIRE(MixedFilamentViewModel::makeLabel(mf) == "F1+F2+F3");
}

TEST_CASE("REGRESSION: makeLabel skip zero components", "[Regression]") {
    MixedFilament mf;
    mf.component_a = 1; mf.component_b = 0; mf.component_c = 3;
    REQUIRE(MixedFilamentViewModel::makeLabel(mf) == "F1+F3");
}

TEST_CASE("REGRESSION: blendDisplayColor empty input", "[Regression]") {
    std::string result = MixedFilamentViewModel::blendDisplayColor({}, {});
    REQUIRE(!result.empty());
}

TEST_CASE("REGRESSION: blendDisplayColor single filament", "[Regression]") {
    std::vector<std::string> colors = {"#FF0000FF"};
    std::vector<unsigned int> seq = {1};
    std::string result = MixedFilamentViewModel::blendDisplayColor(colors, seq);
    REQUIRE(result == "#FF0000FF");
}

TEST_CASE("REGRESSION: blendDisplayColor blend two colors", "[Regression]") {
    std::vector<std::string> colors = {"#FF0000FF", "#0000FFFF"};
    std::vector<unsigned int> seq = {1, 2};
    std::string result = MixedFilamentViewModel::blendDisplayColor(colors, seq);
    // Result should be a blend (purple-ish)
    REQUIRE(!result.empty());
    REQUIRE(result[0] == '#');
    REQUIRE(result.size() == 9);
    // Should NOT be pure red (it's a blend)
    REQUIRE(result != "#FF0000FF");
    REQUIRE(result != "#0000FFFF");
}

// ?? UndoRedoController regression ??

TEST_CASE("REGRESSION: undo/redo preserves value", "[Regression]") {
    UndoRedoController urc;
    int val = 0;
    urc.push([&]{ val = 42; }, [&]{ val = 0; }, "set");
    val = 42;

    urc.undo(); REQUIRE(val == 0);
    urc.redo(); REQUIRE(val == 42);
    urc.undo(); REQUIRE(val == 0);
}

TEST_CASE("REGRESSION: undo/redo stack handles multiple pushes", "[Regression]") {
    UndoRedoController urc;
    int val = 0;

    urc.push([&]{ val = 10; }, [&]{ val = 0; }, "step1");
    val = 10;
    urc.push([&]{ val = 20; }, [&]{ val = 10; }, "step2");
    val = 20;

    urc.undo(); REQUIRE(val == 10);
    urc.undo(); REQUIRE(val == 0);
    REQUIRE_FALSE(urc.canUndo_.get());
}

// ?? isImproperCategory regression (from GUI_Factories.cpp L84) ??

TEST_CASE("REGRESSION: isImproperCategory empty category is improper", "[Regression]") {
    REQUIRE(ConfigValidationModel::isImproperCategory("", 2));
}

TEST_CASE("REGRESSION: isImproperCategory extruders hidden with 1 filament", "[Regression]") {
    REQUIRE(ConfigValidationModel::isImproperCategory("Extruders", 1));
    REQUIRE_FALSE(ConfigValidationModel::isImproperCategory("Extruders", 2));
}

TEST_CASE("REGRESSION: isImproperCategory wipe options hidden with 1 filament", "[Regression]") {
    REQUIRE(ConfigValidationModel::isImproperCategory("Wipe options", 1));
    REQUIRE_FALSE(ConfigValidationModel::isImproperCategory("Wipe options", 4));
}

TEST_CASE("REGRESSION: isImproperCategory support hidden for non-object", "[Regression]") {
    REQUIRE_FALSE(ConfigValidationModel::isImproperCategory("Support material", 2, true));
    REQUIRE(ConfigValidationModel::isImproperCategory("Support material", 2, false));
}

// ?? findNewPresets regression (from ConfigWizard.cpp) ??

TEST_CASE("REGRESSION: findNewPresets detects added keys", "[Regression]") {
    std::map<std::string, std::string> old = {{"a","1"},{"b","2"}};
    std::map<std::string, std::string> nu  = {{"a","1"},{"b","2"},{"c","3"}};
    auto added = PresetStringModel::findNewPresets(old, nu);
    REQUIRE(added.size() == 1);
    REQUIRE(added.count("c") == 1);
}

TEST_CASE("REGRESSION: findNewPresets detects changed values", "[Regression]") {
    std::map<std::string, std::string> old = {{"a","1"}};
    std::map<std::string, std::string> nu  = {{"a","2"}};
    auto added = PresetStringModel::findNewPresets(old, nu);
    REQUIRE(added.size() == 1);
}

TEST_CASE("REGRESSION: findNewPresets empty when identical", "[Regression]") {
    std::map<std::string, std::string> old = {{"a","1"}};
    std::map<std::string, std::string> nu  = {{"a","1"}};
    auto added = PresetStringModel::findNewPresets(old, nu);
    REQUIRE(added.empty());
}

TEST_CASE("REGRESSION: firstNewPreset returns first added", "[Regression]") {
    std::map<std::string, std::string> old;
    std::map<std::string, std::string> nu = {{"x","1"},{"y","2"}};
    auto first = PresetStringModel::firstNewPreset(old, nu);
    REQUIRE(!first.empty());
}


// ?? pureOptionKey regression (from UnsavedChangesDialog.cpp L573) ??

TEST_CASE("REGRESSION: pureOptionKey strips extruder suffix", "[Regression]") {
    REQUIRE(PresetStringModel::pureOptionKey("wall_loops#2") == "wall_loops");
    REQUIRE(PresetStringModel::pureOptionKey("layer_height") == "layer_height");
    REQUIRE(PresetStringModel::pureOptionKey("infill_density#1#2") == "infill_density");
}

TEST_CASE("REGRESSION: idFromOptionKey extracts index", "[Regression]") {
    REQUIRE(PresetStringModel::idFromOptionKey("wall_loops#2") == 2);
    REQUIRE(PresetStringModel::idFromOptionKey("layer_height") == 0);
}

TEST_CASE("REGRESSION: presetIconName returns correct icon", "[Regression]") {
    REQUIRE(PresetStringModel::presetIconName(0, 0) == "cog");      // Print
    REQUIRE(PresetStringModel::presetIconName(1, 0) == "spool");    // Filament
    REQUIRE(PresetStringModel::presetIconName(2, 0) == "printer");  // Printer FFF
}
