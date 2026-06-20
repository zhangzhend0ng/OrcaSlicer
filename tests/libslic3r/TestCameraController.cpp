#include "catch2/catch.hpp"
#include "slic3r/App/CameraController.hpp"
#include <cmath>

using namespace Slic3r;

// CameraController is pure C++: no wxWidgets, no OpenGL, no window needed.

TEST_CASE("CameraController default state", "[CameraController][MVVP]") {
    CameraController cc;
    auto& state = cc.state.get();
    REQUIRE(state.zoom == Approx(1.0));
    REQUIRE(state.theta == Approx(0.0));
}

TEST_CASE("CameraController viewTop orients correctly", "[CameraController][MVVP]") {
    CameraController cc;
    cc.viewTop.execute();
    // viewTop sets phi = 90 degrees (top-down)
    auto pos = cc.get_position();
    REQUIRE(pos.z() > 0.0); // camera should be above target
}

TEST_CASE("CameraController viewFront orients correctly", "[CameraController][MVVP]") {
    CameraController cc;
    cc.viewFront.execute();
    auto dir = cc.get_dir_forward();
    REQUIRE(dir.y() < 0.0); // looking along -Y
}

TEST_CASE("CameraController orbit updates state property", "[CameraController][MVVP]") {
    CameraController cc;
    CameraState oldState = cc.state.get();

    bool notified = false;
    auto sub = cc.state.subscribe([&](const CameraState& s, const CameraState&) {
        notified = true;
    });

    cc.orbit(45.0, 0.0);  // rotate 45 degrees azimuth
    REQUIRE(notified);
    REQUIRE(cc.state.get().theta != oldState.theta);
}

TEST_CASE("CameraController toggleProjection toggles isOrtho", "[CameraController][MVVP]") {
    CameraController cc;
    REQUIRE_FALSE(cc.isOrtho.get());

    cc.toggleProjection.execute();
    REQUIRE(cc.isOrtho.get());

    cc.toggleProjection.execute();
    REQUIRE_FALSE(cc.isOrtho.get());
}

TEST_CASE("CameraController zoom clamps to valid range", "[CameraController][MVVP]") {
    CameraController cc;
    double initial = cc.state.get().zoom;

    cc.zoom(1000.0); // try to zoom way in
    REQUIRE(cc.state.get().zoom <= 100.0);

    cc.zoom(0.001); // try to zoom way out
    REQUIRE(cc.state.get().zoom >= 0.1);
}

TEST_CASE("CameraController resetView restores defaults", "[CameraController][MVVP]") {
    CameraController cc;

    // Change camera
    cc.orbit(90.0, 30.0);
    cc.zoom(5.0);

    // Reset
    cc.resetView.execute();

    REQUIRE(cc.state.get().zoom == Approx(1.0));
    REQUIRE(cc.state.get().distance > 0.0);
}
