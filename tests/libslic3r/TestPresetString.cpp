#include "catch2/catch.hpp"
#include "slic3r/App/PresetStringModel.hpp"

using namespace Slic3r;

TEST_CASE("PresetString removeSpecialKeys", "[PresetString]") {
    REQUIRE(PresetStringModel::removeSpecialKeys("hello@world") == "helloworld");
    REQUIRE(PresetStringModel::removeSpecialKeys("test;data") == "testdata");
    REQUIRE(PresetStringModel::removeSpecialKeys("clean") == "clean");
}

TEST_CASE("PresetString isAllDigits", "[PresetString]") {
    REQUIRE(PresetStringModel::isAllDigits("12345"));
    REQUIRE_FALSE(PresetStringModel::isAllDigits("123a5"));
    REQUIRE_FALSE(PresetStringModel::isAllDigits(""));
}

TEST_CASE("PresetString caseInsensitiveCompare", "[PresetString]") {
    REQUIRE(PresetStringModel::caseInsensitiveCompare("PLA", "pla"));
    REQUIRE(PresetStringModel::caseInsensitiveCompare("ABS", "ABS"));
    REQUIRE_FALSE(PresetStringModel::caseInsensitiveCompare("PLA", "ABS"));
}

TEST_CASE("PresetString currentTime format", "[PresetString]") {
    auto t = PresetStringModel::currentTime();
    REQUIRE(!t.empty());
    REQUIRE(t.find('_') != std::string::npos);
}

TEST_CASE("PresetString extractMachineName", "[PresetString]") {
    auto name = PresetStringModel::extractMachineName("Snapmaker J1 0.4 PLA");
    REQUIRE(name == "Snapmaker J1");
}

TEST_CASE("PresetString extractNozzleDiameter", "[PresetString]") {
    auto d = PresetStringModel::extractNozzleDiameter("Snapmaker J1 0.4 PLA");
    REQUIRE(d == "0.4");
}

TEST_CASE("PresetString extractNozzleDiameter not found", "[PresetString]") {
    auto d = PresetStringModel::extractNozzleDiameter("Snapmaker J1");
    REQUIRE(d == "");
}

TEST_CASE("PresetString md5Hash produces output", "[PresetString]") {
    auto h = PresetStringModel::md5Hash("test");
    REQUIRE(!h.empty());
}
