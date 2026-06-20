#include "catch2/catch.hpp"
#include "slic3r/App/SystemInfoModel.hpp"

using namespace Slic3r;

TEST_CASE("SystemInfo parseKeyValueConfig", "[SystemInfo]") {
    std::string content = "key1=value1
key2 = value2
#comment
key3=val3";
    auto result = SystemInfoModel::parseKeyValueConfig(content);
    REQUIRE(result.size() == 3);
    REQUIRE(result["key1"] == "value1");
    REQUIRE(result["key2"] == "value2");
    REQUIRE(result["key3"] == "val3");
}

TEST_CASE("SystemInfo generateUniqueId produces valid UUID", "[SystemInfo]") {
    auto id = SystemInfoModel::generateUniqueId();
    REQUIRE(id.size() == 36); // UUID format: 8-4-4-4-12
    REQUIRE(id[8] == '-');
    REQUIRE(id[13] == '-');
}

TEST_CASE("SystemInfo systemInfoToJson", "[SystemInfo]") {
    std::map<std::string, std::string> info = {{"os", "Windows"}, {"ram", "16GB"}};
    auto json = SystemInfoModel::systemInfoToJson(info);
    REQUIRE(json.find(""os"") != std::string::npos);
    REQUIRE(json.find(""Windows"") != std::string::npos);
    REQUIRE(json.find(""ram"") != std::string::npos);
    REQUIRE(json[0] == '{');
}
