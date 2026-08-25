// Full-app smoke tests: boot the REAL GUI_App (OrcaSlicer itself) in test
// mode and assert the application comes up, then drive real dialogs/controls
// via ProcessEvent / Win32MessageSimulator.
//
// Build requirements:
//   - CMake option WX_GUI_FULL_APP=ON (defines ORCA_FULL_GUI_APP) so
//     wx_gui_tests_main.cpp compiles PoCApp out and the wxApp instance is the
//     real GUI_App (wxIMPLEMENT_APP in GUI_App.cpp, linked via libslic3r_gui).
// Runtime requirements:
//   - ORCA_GUI_TEST_MODE=1: GUI_App::on_init_inner skips the network / splash
//     / registry side effects (see gui_test_mode() in GUI_App.cpp) but still
//     boots MainFrame, Plater and the preset bundles.
//   - A GUI session (Windows desktop). Optionally WX_GUI_DESKTOP=1 to run on a
//     private desktop so the main window never disturbs the user.
//
// These tests are headless-ish: they do NOT need the OS-level simulator, so
// they run fine while a remote-control layer (GameViewer) is active.

#include <catch_main.hpp>

#include <wx/wx.h>
#include <wx/menu.h>

#include <chrono>
#include <thread>

#include "slic3r/GUI/GUI_App.hpp"
#include "slic3r/GUI/MainFrame.hpp"

// Shared one-shot wx / GUI_App bootstrap, implemented in wx_gui_tests_main.cpp.
bool ensure_wx_initialized();

// ---------------------------------------------------------------------------
// (1) Boot smoke: the real application comes up — MainFrame, Plater, config,
//     preset bundle. Everything else in this file depends on this passing.
// ---------------------------------------------------------------------------
TEST_CASE("full app boots MainFrame, Plater and presets", "[gui][fullapp]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    GUI_App& app = static_cast<GUI_App&>(*wxApp::GetInstance());

    INFO("GUI_App data dir = " << app.app_config->config_path());
    CHECK(app.mainframe != nullptr);
    CHECK(app.plater_ != nullptr);
    CHECK(app.app_config != nullptr);
    CHECK(app.preset_bundle != nullptr);

    if (app.mainframe != nullptr) {
        // Test mode keeps the main window hidden (no flashing windows over the
        // user's desktop); the boot signal is a functional, enabled frame.
        INFO("MainFrame enabled = " << (app.mainframe->IsEnabled() ? "true" : "false"));
        CHECK(app.mainframe->IsEnabled());
    }
}

// ---------------------------------------------------------------------------
// (2) Event pipeline on the real frame: MainFrame uses a borderless
//     BBLTopbar (no wxMenuBar), so verify the topbar exists and that
//     ProcessEvent on the frame's handler chain is safe to call (the
//     canonical daily-batch injection path — no OS input involved).
// ---------------------------------------------------------------------------
TEST_CASE("full app topbar dispatches events via ProcessEvent", "[gui][fullapp]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    GUI_App& app = static_cast<GUI_App&>(*wxApp::GetInstance());
    REQUIRE(app.mainframe != nullptr);

    REQUIRE(app.mainframe->topbar() != nullptr);

    // The frame's event handler chain must accept an injected command event
    // without corrupting state (events no handler claims are simply skipped).
    wxMenuEvent menu_evt(wxEVT_MENU, wxID_ANY);
    menu_evt.SetEventObject(app.mainframe);
    app.mainframe->GetEventHandler()->ProcessEvent(menu_evt);

    wxYield();
    CHECK(app.mainframe->IsEnabled());
}

// ---------------------------------------------------------------------------
// (3) SHOWN-mode smoke: the only path that exercises display-dependent
//     behavior (layout, first-paint, show-event chain) — everything else in
//     this file runs with the main window hidden. Tagged [shown] so bulk runs
//     can exclude it with ~[shown]; when it runs, the window appears for ~1s
//     but ShowWithoutActivating() never steals focus and no mouse is moved.
// ---------------------------------------------------------------------------
TEST_CASE("full app main window shows and lays out", "[gui][fullapp][shown]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    GUI_App& app = static_cast<GUI_App&>(*wxApp::GetInstance());
    REQUIRE(app.mainframe != nullptr);

    app.mainframe->ShowWithoutActivating();
    // Keep the window BEHIND the user's current windows: no activation, no
    // focus steal, and Lower() pushes it to the bottom of the z-order so it
    // never covers what the user is looking at. Layout/paint still run.
    app.mainframe->Lower();
    // Pump layout / paint events so the show-event chain and sizer layout run.
    wxYield();
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    wxYield();

    INFO("MainFrame shown = " << (app.mainframe->IsShown() ? "true" : "false")
         << ", size = " << app.mainframe->GetSize().x << "x" << app.mainframe->GetSize().y);
    CHECK(app.mainframe->IsShown());
    CHECK(app.mainframe->GetSize().x > 0);
    CHECK(app.mainframe->GetSize().y > 0);

    // Leave the desktop as we found it.
    app.mainframe->Show(false);
    wxYield();
}

// ---------------------------------------------------------------------------
// (4) Network test mode (ORCA_GUI_TEST_MODE=network): the device stack is
//     initialized for real (DeviceManager always exists; network plugin loaded
//     when the test data dir has one), so the device panel comes up on its
//     real code path. Run with:
//       ORCA_GUI_TEST_MODE=network wx_gui_tests.exe "[devices]"
// ---------------------------------------------------------------------------
TEST_CASE("device panel present in network test mode", "[gui][fullapp][devices]")
{
    if (!Slic3r::GUI::gui_test_mode_network())
        SKIP("run with ORCA_GUI_TEST_MODE=network to exercise the real device stack");

    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    GUI_App& app = static_cast<GUI_App&>(*wxApp::GetInstance());
    REQUIRE(app.mainframe != nullptr);

    INFO("DeviceManager = " << (app.getDeviceManager() != nullptr ? "present" : "absent"));
    CHECK(app.getDeviceManager() != nullptr);

    // MonitorPanel is constructed when the DeviceManager exists (empty-state
    // UI on its real code path; no devices on a test machine without printers).
    if (app.mainframe->m_monitor != nullptr) {
        CHECK(app.mainframe->m_monitor->IsEnabled());
    } else {
        WARN("MonitorPanel not created (device stack unavailable)");
    }
}
