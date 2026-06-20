#include "catch2/catch.hpp"
#include "slic3r/App/PlaterViewModel.hpp"
#include "slic3r/App/ObjectViewModel.hpp"
#include "slic3r/App/ColorMixViewModel.hpp"
#include "slic3r/App/UndoRedoController.hpp"

using namespace Slic3r;

// PlaterViewModel tests ? NO wxApp, NO window, NO OpenGL needed

TEST_CASE("PlaterViewModel initial state is Idle", "[PlaterViewModel][MVVP]") {
    PlaterViewModel vm;
    REQUIRE(vm.sliceState.get() == SliceState::Idle);
    REQUIRE(vm.sliceProgress.get() == Approx(0.0));
    REQUIRE(vm.objects.get().empty());
    REQUIRE_FALSE(vm.isSlicing.get());
}

TEST_CASE("PlaterViewModel slice command requires objects", "[PlaterViewModel][MVVP]") {
    PlaterViewModel vm;
    REQUIRE_FALSE(vm.slice.canExecute()); // no objects, can't slice
}

TEST_CASE("PlaterViewModel arranged command enabled when objects exist", "[PlaterViewModel][MVVP]") {
    PlaterViewModel vm;
    REQUIRE_FALSE(vm.arrange.canExecute());

    // Simulate having objects
    auto& objs = vm.objects.mutate();
    objs.push_back(ObjectInfo{0, "test.stl", "PLA", 1, true});
    vm.objects.notifyMutation();

    REQUIRE(vm.arrange.canExecute());
}

TEST_CASE("ObjectViewModel default state", "[ObjectViewModel][MVVP]") {
    ObjectViewModel ovm(0, "test_object");
    REQUIRE(ovm.objectId == 0);
    REQUIRE(ovm.name == "test_object");
    REQUIRE_FALSE(ovm.isSelected.get());
    REQUIRE(ovm.isVisible.get());
}

TEST_CASE("ObjectViewModel toggleVisibility", "[ObjectViewModel][MVVP]") {
    ObjectViewModel ovm(0, "test");
    REQUIRE(ovm.isVisible.get());
    ovm.toggleVisibility.execute();
    REQUIRE_FALSE(ovm.isVisible.get());
    ovm.toggleVisibility.execute();
    REQUIRE(ovm.isVisible.get());
}

TEST_CASE("ColorMixViewModel panelVisible depends on filament count", "[ColorMixViewModel][MVVP]") {
    ColorMixViewModel vm;
    REQUIRE_FALSE(vm.panelVisible.get());
    vm.updateVisibility(1);
    REQUIRE_FALSE(vm.panelVisible.get());
    vm.updateVisibility(2);
    REQUIRE(vm.panelVisible.get());
    vm.updateVisibility(4);
    REQUIRE(vm.panelVisible.get());
}

TEST_CASE("UndoRedoController push and undo", "[UndoRedoController][MVVP]") {
    UndoRedoController urc;
    int value = 0;

    REQUIRE_FALSE(urc.canUndo_.get());
    REQUIRE_FALSE(urc.canRedo_.get());

    urc.push(
        [&] { value = 42; },
        [&] { value = 0; },
        "Set value"
    );
    REQUIRE(urc.canUndo_.get());
    REQUIRE_FALSE(urc.canRedo_.get());

    // Do the action
    value = 42;
    REQUIRE(value == 42);

    // Undo
    urc.undo();
    REQUIRE(value == 0);
    REQUIRE_FALSE(urc.canUndo_.get());
    REQUIRE(urc.canRedo_.get());

    // Redo
    urc.redo();
    REQUIRE(value == 42);
    REQUIRE(urc.canUndo_.get());
    REQUIRE_FALSE(urc.canRedo_.get());
}

TEST_CASE("UndoRedoController clear discards history", "[UndoRedoController][MVVP]") {
    UndoRedoController urc;
    int value = 0;

    urc.push([&]{value=1;}, [&]{value=0;}, "Set 1");
    REQUIRE(urc.canUndo_.get());
    urc.clear();
    REQUIRE_FALSE(urc.canUndo_.get());
    REQUIRE_FALSE(urc.canRedo_.get());
}
