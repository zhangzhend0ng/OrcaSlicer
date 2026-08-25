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
#include "slic3r/GUI/Plater.hpp"
#include "slic3r/Utils/PresetUpdater.hpp"

#include <boost/filesystem.hpp>
#include <fstream>
#include <sstream>

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

// ---------------------------------------------------------------------------
// (5) END-TO-END slicing flow (slow): open a real 3mf on the real Plater,
//     slice it through the real background process, and verify the generated
//     G-code on disk. This exercises model loading, preset selection, the
//     slicing pipeline (worker thread + completion event) and the G-code
//     artifact — all on the production code paths.
// ---------------------------------------------------------------------------
TEST_CASE("slice 3mf and verify gcode end-to-end", "[gui][fullapp][slow]")
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);

    GUI_App& app = static_cast<GUI_App&>(*wxApp::GetInstance());
    REQUIRE(app.plater_ != nullptr);

    // The GL context was initialized during ensure_wx_initialized (post_init
    // ran with the frame briefly shown), so slicing progress updates can
    // refresh the 3D scene while the frame stays hidden.

    // ① Open the REAL project 3mf with its config (LoadModel|LoadConfig — the
    //    default). The file embeds the preset selection (printer_settings_id
    //    "Snapmaker U1 (0.8 nozzle)", print settings, model/filament config),
    //    so opening it applies those presets automatically — no manual choice.
    //    (The machine presets were installed during app init — see the test
    //    mode block in GUI_App::on_init_inner — so the embedded selection
    //    resolves against real Snapmaker system presets.)
    const std::string model_path = std::string(TEST_DATA_DIR) + "/test_3mf/mixed_filament_test.3mf";
    INFO("loading model: " << model_path);
    const std::vector<std::string> files{model_path};
    const std::vector<size_t>      loaded = app.plater_->load_files(files); // default strategy: model + config
    REQUIRE(!loaded.empty());
    CHECK(app.plater_->model().objects.size() > 0);
    CHECK(app.plater_->model().objects.front()->instances.size() > 0);

    // The project's own preset selection must have been applied by the load.
    CHECK(app.preset_bundle->printers.get_selected_preset_name() == "Snapmaker U1 (0.8 nozzle)");

    // Loading schedules UI jobs (scene refresh etc.); reslice() refuses to
    // start while the UI worker is busy (stop_queue timeout -> early return),
    // so wait for it to become idle first.
    const auto load_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(30);
    while (!app.plater_->get_ui_job_worker().is_idle() && std::chrono::steady_clock::now() < load_deadline) {
        wxYield();
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
    INFO("UI worker idle after load = " << (app.plater_->get_ui_job_worker().is_idle() ? "true" : "false"));

    // ② Slice on the background thread; wait for completion by polling the
    //    plate's slice result (production state — the completion event symbol
    //    is file-local in Plater.cpp and cannot be linked from here). Hard
    //    timeout so a slicing failure fails the test instead of hanging it.
    auto* plate = app.plater_->get_partplate_list().get_curr_plate();
    REQUIRE(plate != nullptr);

    app.plater_->reslice();
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(120);
    while (!plate->is_slice_result_valid() && std::chrono::steady_clock::now() < deadline) {
        wxYield();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    INFO("slice result valid after waiting = " << (plate->is_slice_result_valid() ? "true" : "false"));
    REQUIRE(plate->is_slice_result_valid());

    // ③ Verify the G-code artifact: the background process wrote the temp
    //    G-code during slicing; exporting copies that file, so asserting the
    //    artifact itself (exists, non-empty, real moves) validates the whole
    //    pipeline up to and including G-code generation.
    const std::string gcode_path = plate->get_tmp_gcode_path();
    INFO("temp gcode path = " << gcode_path);
    REQUIRE(boost::filesystem::exists(gcode_path));

    std::ifstream gcode_in(gcode_path, std::ios::binary);
    std::stringstream gcode_buf;
    gcode_buf << gcode_in.rdbuf();
    const std::string gcode = gcode_buf.str();
    INFO("gcode size = " << gcode.size() << " bytes");
    CHECK(gcode.size() > 1000);             // real slicing output, not a stub
    CHECK(gcode.find("G1 ") != std::string::npos); // actual tool moves
    const bool has_temp_cmd = gcode.find("M104") != std::string::npos || gcode.find("M140") != std::string::npos;
    CHECK(has_temp_cmd);

    // ④ Export step: the production export path (Plater::export_gcode →
    //    schedule_export) copies the temp G-code to the chosen location; its
    //    UI entry is a modal file dialog, so perform the same copy into a
    //    fixed output dir that survives the test — this is the slice result
    //    the user can open. The file name is unique per run: a fixed name
    //    collides with a still-open export from a previously running app
    //    instance (the file stays locked -> copy_file fails).
    const std::string out_dir = std::string(::getenv("TEMP")) + "/wx_gui_slice_output";
    boost::system::error_code ec;
    boost::filesystem::create_directories(out_dir, ec);
    REQUIRE(!ec);
    const std::string export_path = (boost::filesystem::path(out_dir) /
        ("mixed_filament_test_" + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".gcode")).string();
    boost::filesystem::copy_file(gcode_path, export_path, boost::filesystem::copy_option::overwrite_if_exists, ec);
    REQUIRE(!ec);
    INFO("exported gcode = " << export_path);
    REQUIRE(boost::filesystem::exists(export_path));
    CHECK(boost::filesystem::file_size(export_path) == gcode.size());

    // Leave a clean slate for other cases in the same process.
    app.plater_->new_project(true); // skip_confirm: no dialogs in test mode
}
