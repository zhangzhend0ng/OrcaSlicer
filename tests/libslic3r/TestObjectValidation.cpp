#include "catch2/catch.hpp"
#include "slic3r/App/ObjectValidationModel.hpp"

using namespace Slic3r;

TEST_CASE("ObjectValidation totalFilamentsCount", "[ObjectValidation]") {
    REQUIRE(ObjectValidationModel::totalFilamentsCount(1) == 1);
    REQUIRE(ObjectValidationModel::totalFilamentsCount(4) == 4);
}

TEST_CASE("ObjectValidation roundToBin preserves zero", "[ObjectValidation]") {
    REQUIRE(ObjectValidationModel::roundToBin(0.0f) == 0.0f);
    REQUIRE(ObjectValidationModel::roundToBin(-1.0f) == 0.0f);
}

TEST_CASE("ObjectValidation roundToBin rounds correctly", "[ObjectValidation]") {
    float v = ObjectValidationModel::roundToBin(1.0f);
    REQUIRE(v > 0.9f);
    REQUIRE(v < 1.1f);
}

TEST_CASE("ObjectValidation findClosestLayerIndex empty", "[ObjectValidation]") {
    std::vector<double> empty;
    REQUIRE(ObjectValidationModel::findClosestLayerIndex(empty, 1.0, 0.1) == -1);
}

TEST_CASE("ObjectValidation findClosestLayerIndex exact match", "[ObjectValidation]") {
    std::vector<double> zs = {0.0, 0.2, 0.4, 0.6, 0.8};
    int idx = ObjectValidationModel::findClosestLayerIndex(zs, 0.4, 0.01);
    REQUIRE(idx == 2);
}

TEST_CASE("ObjectValidation findClosestLayerIndex near match", "[ObjectValidation]") {
    std::vector<double> zs = {0.0, 0.2, 0.4, 0.6, 0.8};
    int idx = ObjectValidationModel::findClosestLayerIndex(zs, 0.21, 0.05);
    REQUIRE(idx == 1);
}

TEST_CASE("ObjectValidation findClosestLayerIndex out of range", "[ObjectValidation]") {
    std::vector<double> zs = {0.0, 0.2, 0.4};
    int idx = ObjectValidationModel::findClosestLayerIndex(zs, 10.0, 0.1);
    REQUIRE(idx == -1);
}

TEST_CASE("ObjectValidation canAddVolumesToObject null", "[ObjectValidation]") {
    REQUIRE_FALSE(ObjectValidationModel::canAddVolumesToObject(nullptr));
}
