#include "catch2/catch.hpp"
#include "slic3r/App/TabViewModel.hpp"
#include "slic3r/App/PrintTabViewModel.hpp"
#include "slic3r/App/FilamentTabViewModel.hpp"
#include "slic3r/App/PrinterTabViewModel.hpp"

using namespace Slic3r;

TEST_CASE("TabViewModel default state", "[TabViewModel][MVVP]") {
    PrintTabViewModel ptvm;
    REQUIRE(ptvm.tabTitle.get() == "Print Settings");
    REQUIRE_FALSE(ptvm.hasDirtyChanges.get());
    REQUIRE_FALSE(ptvm.applyChanges.canExecute());
    REQUIRE_FALSE(ptvm.revertChanges.canExecute());
}

TEST_CASE("TabViewModel apply requires dirty state", "[TabViewModel][MVVP]") {
    PrintTabViewModel ptvm;
    ptvm.hasDirtyChanges.set(true);
    REQUIRE(ptvm.applyChanges.canExecute());
    REQUIRE(ptvm.revertChanges.canExecute());
}

TEST_CASE("PrintTabViewModel extruder defaults", "[PrintTabViewModel][MVVP]") {
    PrintTabViewModel ptvm;
    REQUIRE(ptvm.activeExtruder.get() == 0);
    REQUIRE(ptvm.extruderCount.get() == 1);
    REQUIRE_FALSE(ptvm.hasExtruderOverrides.get());
}

TEST_CASE("FilamentTabViewModel title and defaults", "[FilamentTabViewModel][MVVP]") {
    FilamentTabViewModel ftvm;
    REQUIRE(ftvm.tabTitle.get() == "Filament Settings");
    REQUIRE(ftvm.activeFilament.get() == 0);
    REQUIRE(ftvm.filaments.get().empty());
}

TEST_CASE("PrinterTabViewModel defaults", "[PrinterTabViewModel][MVVP]") {
    PrinterTabViewModel prtvm;
    REQUIRE(prtvm.tabTitle.get() == "Printer Settings");
    REQUIRE(prtvm.firmwareFlavor.get() == "Marlin");
    REQUIRE(prtvm.hasHeatedBed.get());
    REQUIRE_FALSE(prtvm.hasEnclosure.get());
}

TEST_CASE("PrinterTabViewModel machine limits exist", "[PrinterTabViewModel][MVVP]") {
    PrinterTabViewModel prtvm;
    auto limits = prtvm.machineLimits.get();
    REQUIRE(limits.maxFeedrateX > 0.0f);
    REQUIRE(limits.maxFeedrateY > 0.0f);
    REQUIRE(limits.maxAccelX > 0.0f);
    REQUIRE(limits.minExtrudeTemp > 0.0f);
    REQUIRE(limits.maxExtrudeTemp > limits.minExtrudeTemp);
}

TEST_CASE("TabViewModel search filter updates", "[TabViewModel][MVVP]") {
    PrintTabViewModel ptvm;
    ptvm.setSearchFilter("layer");
    REQUIRE(ptvm.searchFilter.get() == "layer");
    ptvm.setSearchFilter("");
    REQUIRE(ptvm.searchFilter.get() == "");
}
