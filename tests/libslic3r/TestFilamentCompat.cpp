#include "catch2/catch.hpp"
#include "slic3r/App/FilamentCompatibilityModel.hpp"

using namespace Slic3r;

TEST_CASE("FilamentCompat normalizeFilamentType removes separators", "[FilamentCompat]") {
    REQUIRE(FilamentCompatibilityModel::normalizeFilamentType("PLA-PRO") == "PLAPRO");
    REQUIRE(FilamentCompatibilityModel::normalizeFilamentType("PLA PRO") == "PLAPRO");
    REQUIRE(FilamentCompatibilityModel::normalizeFilamentType("petg") == "PETG");
}

TEST_CASE("FilamentCompat parseCategory recognizes common types", "[FilamentCompat]") {
    REQUIRE(FilamentCompatibilityModel::parseCategory("PLA") == FilamentCategory::PLA);
    REQUIRE(FilamentCompatibilityModel::parseCategory("ABS") == FilamentCategory::ABS);
    REQUIRE(FilamentCompatibilityModel::parseCategory("PETG") == FilamentCategory::PETG);
    REQUIRE(FilamentCompatibilityModel::parseCategory("TPU") == FilamentCategory::TPU);
    REQUIRE(FilamentCompatibilityModel::parseCategory("PA") == FilamentCategory::PA);
    REQUIRE(FilamentCompatibilityModel::parseCategory("NYLON") == FilamentCategory::PA);
    REQUIRE(FilamentCompatibilityModel::parseCategory("SUPPORTG") == FilamentCategory::Support);
}

TEST_CASE("FilamentCompat isCategoryCompatible same type", "[FilamentCompat]") {
    REQUIRE(FilamentCompatibilityModel::isCategoryCompatible(
        FilamentCategory::PLA, FilamentCategory::PLA));
}

TEST_CASE("FilamentCompat support compatible with everything", "[FilamentCompat]") {
    REQUIRE(FilamentCompatibilityModel::isCategoryCompatible(
        FilamentCategory::PLA, FilamentCategory::Support));
}

TEST_CASE("FilamentCompat buildCompatibilityMatrix", "[FilamentCompat]") {
    auto m = FilamentCompatibilityModel::buildCompatibilityMatrix(3);
    REQUIRE(m.size() == 3);
    REQUIRE(m[0].size() == 3);
}

TEST_CASE("FilamentCompat resolveCategories", "[FilamentCompat]") {
    auto resolved = FilamentCompatibilityModel::resolveCategories({"PLA-Basic", "Abs Pro"});
    REQUIRE(resolved.size() == 2);
    REQUIRE(resolved[0].category == FilamentCategory::PLA);
    REQUIRE(resolved[1].category == FilamentCategory::ABS);
}
