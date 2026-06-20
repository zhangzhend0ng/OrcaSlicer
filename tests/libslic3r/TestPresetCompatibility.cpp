#include "catch2/catch.hpp"
#include "slic3r/App/PresetCompatibilityModel.hpp"

using namespace Slic3r;

TEST_CASE("PresetCompat null filament returns empty", "[PresetCompat]") {
    auto printers = PresetCompatibilityModel::getCompatiblePrinters(nullptr);
    REQUIRE(printers.empty());
}

TEST_CASE("PresetCompat null filament/printer is incompatible", "[PresetCompat]") {
    auto result = PresetCompatibilityModel::checkFilamentPrinterCompatibility(nullptr, nullptr);
    REQUIRE_FALSE(result.isCompatible);
}

TEST_CASE("PresetCompat warnings property default empty", "[PresetCompat]") {
    PresetCompatibilityModel model;
    REQUIRE(model.warnings.get().empty());
}
