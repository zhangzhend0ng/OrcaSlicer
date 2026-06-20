#include "catch2/catch.hpp"
#include "slic3r/App/ConfigValidationModel.hpp"

using namespace Slic3r;

TEST_CASE("ConfigValidation bedTypeToRuleKey", "[ConfigValidation]") {
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(0) == "btPEI");
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(1) == "btGESP");
    REQUIRE(ConfigValidationModel::bedTypeToRuleKey(99) == "");
}

TEST_CASE("ConfigValidation nozzleDiameterToRuleKey", "[ConfigValidation]") {
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.4) == "0.4mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(0.6) == "0.6mm");
    REQUIRE(ConfigValidationModel::nozzleDiameterToRuleKey(1.0) == "1mm");
}

TEST_CASE("ConfigValidation set operations", "[ConfigValidation]") {
    std::vector<std::string> a = {"PLA", "ABS", "PETG"};
    std::vector<std::string> b = {"PLA", "TPU"};

    auto inter = ConfigValidationModel::intersect(a, b);
    REQUIRE(inter.size() == 1);
    REQUIRE(inter[0] == "PLA");

    auto uni = ConfigValidationModel::unionSets(a, b);
    REQUIRE(uni.size() == 4);

    auto sub = ConfigValidationModel::subtract(a, b);
    REQUIRE(sub.size() == 2);
}
