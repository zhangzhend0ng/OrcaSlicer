#include "catch2/catch.hpp"
#include "slic3r/App/GeometryValidationModel.hpp"
#include <Eigen/Geometry>

using namespace Slic3r;

TEST_CASE("GeometryValidation isLeftHanded linear part", "[GeometryValidation]") {
    Transform3d::ConstLinearPart identity = Transform3d::Identity().linear();
    REQUIRE_FALSE(GeometryValidationModel::isLeftHanded(identity));

    // Mirror in X = left-handed
    Transform3d mirror = Transform3d::Identity();
    mirror(0, 0) = -1.0;
    REQUIRE(GeometryValidationModel::isLeftHanded(mirror.linear()));
}

TEST_CASE("GeometryValidation isLeftHanded full transform", "[GeometryValidation]") {
    Transform3d t = Transform3d::Identity();
    REQUIRE_FALSE(GeometryValidationModel::isLeftHanded(t));
}

TEST_CASE("GeometryValidation isRotationXYSynchronized same rotation", "[GeometryValidation]") {
    Transform3d rot1 = Transform3d::Identity();
    Transform3d rot2 = Transform3d::Identity();
    REQUIRE(GeometryValidationModel::isRotationXYSynchronized(rot1, rot2));
}

TEST_CASE("GeometryValidation isRotationXYSynchronized Z-only diff", "[GeometryValidation]") {
    Transform3d rot1 = Transform3d::Identity();
    Transform3d rot2 = Eigen::AngleAxisd(M_PI / 4.0, Vec3d::UnitZ());
    REQUIRE(GeometryValidationModel::isRotationXYSynchronized(rot1, rot2));
}

TEST_CASE("GeometryValidation localeToApiFormat", "[GeometryValidation]") {
    REQUIRE(GeometryValidationModel::localeToApiFormat("zh_CN") == "zh-CN");
    REQUIRE(GeometryValidationModel::localeToApiFormat("en_US") == "en-US");
    REQUIRE(GeometryValidationModel::localeToApiFormat("en") == "en");
}
