#include "catch2/catch.hpp"
#include "slic3r/App/MixedFilamentViewModel.hpp"

using namespace Slic3r;

TEST_CASE("MixedFilamentVM empty state", "[MixedFilamentVM][MVVP]") {
    MixedFilamentViewModel vm;
    REQUIRE_FALSE(vm.hasMixedFilaments.get());
    REQUIRE(vm.entries.get().empty());
    REQUIRE(vm.selectedIndex.get() == -1);
}

TEST_CASE("MixedFilamentVM makeLabel builds filament string", "[MixedFilamentVM]") {
    MixedFilament mf;
    mf.component_a = 1;
    mf.component_b = 2;
    REQUIRE(MixedFilamentViewModel::makeLabel(mf) == "F1+F2");
}

TEST_CASE("MixedFilamentVM makeLabel handles three filaments", "[MixedFilamentVM]") {
    MixedFilament mf;
    mf.component_a = 1;
    mf.component_b = 2;
    mf.component_c = 3;
    REQUIRE(MixedFilamentViewModel::makeLabel(mf) == "F1+F2+F3");
}

TEST_CASE("MixedFilamentVM buildPreviewSequence", "[MixedFilamentVM]") {
    MixedFilament mf;
    mf.component_a = 1;
    mf.component_b = 2;

    auto seq = MixedFilamentViewModel::buildPreviewSequence(mf, 4, 2);
    REQUIRE_FALSE(seq.empty());
    REQUIRE(seq[0] == 1); // first wall loop uses component_a
}

TEST_CASE("MixedFilamentVM blendDisplayColor", "[MixedFilamentVM]") {
    std::vector<std::string> colors = {"#FF0000FF", "#0000FFFF"};
    std::vector<unsigned int> seq = {1, 2};

    std::string result = MixedFilamentViewModel::blendDisplayColor(colors, seq);
    REQUIRE(!result.empty());
    REQUIRE(result[0] == '#');
}

TEST_CASE("MixedFilamentVM setPhysicalFilaments triggers recalc", "[MixedFilamentVM][MVVP]") {
    MixedFilamentViewModel vm;

    bool notified = false;
    auto sub = vm.entries.subscribe([&](const auto&, const auto&) { notified = true; });

    vm.setPhysicalFilaments({"#FF0000FF", "#00FF00FF"}, {0.4, 0.4});
    REQUIRE(notified); // Property subscription fired
}

TEST_CASE("MixedFilamentVM selection updates entry flags", "[MixedFilamentVM][MVVP]") {
    MixedFilamentViewModel vm;

    MixedFilament mf;
    mf.component_a = 1;
    mf.component_b = 2;
    vm.setPhysicalFilaments({"#FF0000FF", "#00FF00FF"}, {0.4, 0.4});
    vm.setMixedFilaments({mf});
    vm.setSelection(0);

    REQUIRE(vm.selectedIndex.get() == 0);
    REQUIRE(vm.entries.get()[0].isSelected);
}
