// Full-app business-path tests: drive the REAL GUI_App through production
// state transitions (model load, slicing, preset switching, undo/redo, menu
// commands, tab switching) and assert on production state (Plater model,
// PresetBundle, PartPlate slice results) — no mocks, no UI-internals.
//
// Build requirements / runtime requirements: same as wx_gui_app_tests.cpp
// (WX_GUI_FULL_APP=ON, ORCA_GUI_TEST_MODE=1, interactive Windows session).
//
// Layering: everything here is event-layer (ProcessEvent) or direct
// production-API — headless-safe, no OS input injection, no modal dialogs:
//   - parameter edits go through Tab::get_config() + MainFrame::on_config_changed
//     (the exact chain a field edit triggers);
//   - preset switches go through Tab::select_preset (the combo-box path);
//   - menu commands dispatch wxEVT_MENU through the frame handler chain with
//     the real menu item ids;
//   - object transforms take a snapshot first, then mutate the ModelInstance
//     and refresh via Plater::changed_object — the same sequence the gizmo
//     uses — and are rolled back through Plater::undo()/redo().
//
// Fixtures: tests/data/test_3mf/mixed_filament_test.3mf (project 3mf, embeds
// "Snapmaker U1 (0.8 nozzle)" + 0.40 Standard print preset, 5 filaments),
// tests/data/test_3mf/snapmates_nonmixed.3mf (multi-plate project),
// tests/data/test_3mf/Prusa.stl (single-object geometry).

#include <catch_main.hpp>
#include <catch2/catch_approx.hpp>

#include <wx/wx.h>
#include <wx/menu.h>

#include <chrono>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include "slic3r/GUI/GUI_App.hpp"
#include "slic3r/GUI/MainFrame.hpp"
#include "slic3r/GUI/Plater.hpp"
#include "slic3r/GUI/Tab.hpp"
#include "slic3r/GUI/PartPlate.hpp"
#include "slic3r/GUI/GLCanvas3D.hpp"
#include "libslic3r/Model.hpp"
#include "libslic3r/Format/bbs_3mf.hpp" // LoadStrategy / SaveStrategy

#include <boost/filesystem.hpp>

using namespace Slic3r;
using namespace Slic3r::GUI;

// Shared one-shot wx / GUI_App bootstrap, implemented in wx_gui_tests_main.cpp.
bool ensure_wx_initialized();

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

static GUI_App& fullapp()
{
    REQUIRE(ensure_wx_initialized());
    REQUIRE(wxTheApp != nullptr);
    return static_cast<GUI_App&>(*wxApp::GetInstance());
}

// Pump events briefly so posted events (tab switch -> view switch, snapshot
// UI refresh) get dispatched.
static void pump_events(int ms = 150)
{
    wxYield();
    std::this_thread::sleep_for(std::chrono::milliseconds(ms));
    wxYield();
}

// Wait until the UI job worker (scene refresh etc.) is idle; reslice() refuses
// to start while it is busy.
static void wait_ui_worker_idle(Plater* plater, int seconds = 30)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
    while (!plater->get_ui_job_worker().is_idle() && std::chrono::steady_clock::now() < deadline) {
        wxYield();
        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }
}

// Poll the plate's slice-result flag (production state) until valid.
// The slice pipeline needs the main thread to pump events (wxYield) — without
// it the background process never completes.
static void wait_slice_valid(PartPlate* plate, int seconds = 120)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
    while (!plate->is_slice_result_valid() && std::chrono::steady_clock::now() < deadline) {
        wxYield();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
}

// Poll until the plate's temp gcode content differs from `old_content` (a new
// slice finished). Returns true on success, false on timeout.
static bool wait_gcode_change(PartPlate* plate, const std::string& old_content, int seconds = 120)
{
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(seconds);
    while (std::chrono::steady_clock::now() < deadline) {
        wxYield();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        std::ifstream in(plate->get_tmp_gcode_path(), std::ios::binary);
        std::stringstream buf;
        buf << in.rdbuf();
        const std::string current = buf.str();
        if (!current.empty() && current != old_content)
            return true;
    }
    // Diagnostics for the timeout case: is the slice result still the old one?
    const std::string path = plate->get_tmp_gcode_path();
    boost::system::error_code ec;
    const uintmax_t size = boost::filesystem::exists(path, ec) ? boost::filesystem::file_size(path, ec) : 0;
    std::fprintf(stderr, "[wait_gcode_change] timeout: slice valid = %s, path = %s, size = %llu, old size = %llu\n",
                 plate->is_slice_result_valid() ? "true" : "false", path.c_str(),
                 static_cast<unsigned long long>(size),
                 static_cast<unsigned long long>(old_content.size()));
    return false;
}

static std::string read_file_text(const std::string& path)
{
    std::ifstream in(path, std::ios::binary);
    std::stringstream buf;
    buf << in.rdbuf();
    return buf.str();
}

// Read the current plate's temp gcode (the artifact of the last slice).
static std::string read_gcode(PartPlate* plate)
{
    return read_file_text(plate->get_tmp_gcode_path());
}

// Load a file through the real Plater::load_files (model + config).
static std::vector<size_t> load_project_file(Plater* plater, const std::string& path)
{
    const std::vector<std::string> files{path};
    return plater->load_files(files);
}

// Unique output path under %TEMP%/wx_gui_slice_output — a fixed name can be
// locked by another process (the running Orca app keeps the previous export
// open), so every artifact gets a per-run unique file name.
static std::string make_output_path(const std::string& stem, const std::string& ext)
{
    static unsigned seq = 0;
    const std::string dir = std::string(::getenv("TEMP")) + "/wx_gui_slice_output";
    boost::system::error_code ec;
    boost::filesystem::create_directories(dir, ec);
    const auto now = std::chrono::steady_clock::now().time_since_epoch().count();
    const std::string name = stem + "_" + std::to_string(now) + "_" + std::to_string(seq++) + ext;
    return (boost::filesystem::path(dir) / name).string();
}

// Extract the value of a "; key = value" header line from the gcode.
static std::string gcode_header_value(const std::string& gcode, const std::string& marker)
{
    const size_t pos = gcode.find(marker);
    if (pos == std::string::npos)
        return {};
    const size_t eol = gcode.find('\n', pos);
    const size_t len = (eol == std::string::npos ? gcode.size() : eol) - pos - marker.size();
    std::string value = gcode.substr(pos + marker.size(), len);
    while (!value.empty() && (value.back() == '\r' || value.back() == ' '))
        value.pop_back();
    return value;
}

// Extract the "; filament_type = ..." value from the gcode header.
static std::string gcode_filament_type(const std::string& gcode)
{
    return gcode_header_value(gcode, "; filament_type = ");
}

// Largest "M104/M109 T<tool> S<temp>" temperature for the given tool in the
// gcode (the nozzle temperature the header commands).
static double gcode_nozzle_temp(const std::string& gcode, size_t tool = 0)
{
    std::istringstream is(gcode);
    std::string line;
    double max_temp = 0.0;
    while (std::getline(is, line)) {
        if (line.rfind("M104", 0) != 0 && line.rfind("M109", 0) != 0)
            continue;
        std::istringstream ls(line);
        std::string tok;
        bool matches_tool = false;
        double temp = 0.0;
        while (ls >> tok) {
            if (tok.size() > 1 && tok[0] == 'T') {
                matches_tool = (std::strtol(tok.c_str() + 1, nullptr, 10) == static_cast<long>(tool));
            } else if (tok.size() > 1 && tok[0] == 'S') {
                temp = std::strtod(tok.c_str() + 1, nullptr);
            }
        }
        if (matches_tool && temp > max_temp)
            max_temp = temp;
    }
    return max_temp;
}

// Find a menu item anywhere under `menu` (recursing into submenus) whose label
// ends with the given accelerator suffix (e.g. "\tCtrl+D"). Matching on the
// accelerator keeps the lookup independent of the UI language.
static wxMenuItem* find_menu_item_by_accel(wxMenu* menu, const wxString& accel_suffix)
{
    if (menu == nullptr)
        return nullptr;
    for (wxMenuItem* item : menu->GetMenuItems()) {
        if (item->IsSubMenu()) {
            wxMenuItem* found = find_menu_item_by_accel(item->GetSubMenu(), accel_suffix);
            if (found != nullptr)
                return found;
        } else if (item->GetItemLabel().EndsWith(accel_suffix)) {
            return item;
        }
    }
    return nullptr;
}

// ---------------------------------------------------------------------------
// P0-1: parameter change -> reslice -> different gcode.
//
// Business path: mutate the print tab's edited config (the same memory the
// UI fields edit), push the change through MainFrame::on_config_changed (the
// same chain a field edit triggers), reslice, and verify the new G-code
// artifact differs from the old one.
//
// NOTE on option access: sparse_infill_density is a ConfigOptionPercent, so
// opt_float() (which matches ConfigOptionFloat::static_type() exactly) would
// return nullptr and crash — read the value through the typed option instead.
// ---------------------------------------------------------------------------
TEST_CASE("reslice after infill change produces different gcode", "[gui][fullapp][slow]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.plater_ != nullptr);

    const std::string model_path = std::string(TEST_DATA_DIR) + "/test_3mf/mixed_filament_test.3mf";
    const std::vector<size_t> loaded = load_project_file(app.plater_, model_path);
    REQUIRE(!loaded.empty());
    REQUIRE(app.plater_->model().objects.size() > 0);
    wait_ui_worker_idle(app.plater_);

    PartPlate* plate = app.plater_->get_partplate_list().get_curr_plate();
    REQUIRE(plate != nullptr);

    // Slice once with the project's own settings.
    app.plater_->reslice();
    wait_slice_valid(plate);
    REQUIRE(plate->is_slice_result_valid());
    const std::string gcode_before = read_gcode(plate);
    REQUIRE(gcode_before.size() > 1000);

    // Change infill density through the print tab's edited config.
    Tab* print_tab = app.get_tab(Preset::TYPE_PRINT);
    REQUIRE(print_tab != nullptr);
    const ConfigOptionPercent* density_opt =
        print_tab->get_config()->opt<ConfigOptionPercent>("sparse_infill_density");
    REQUIRE(density_opt != nullptr);
    const double old_density = density_opt->value;
    const double new_density = old_density >= 25.0 ? 15.0 : 40.0;
    print_tab->get_config()->set_key_value("sparse_infill_density", new ConfigOptionPercent(new_density));
    app.mainframe->on_config_changed(print_tab->get_config());
    pump_events();

    // Reslice; the new artifact must differ from the old one.
    app.plater_->reslice();
    REQUIRE(wait_gcode_change(plate, gcode_before));
    const std::string gcode_after = read_gcode(plate);
    INFO("infill density " << old_density << "% -> " << new_density
         << ", gcode sizes " << gcode_before.size() << " -> " << gcode_after.size());
    REQUIRE(gcode_after != gcode_before);

    // Restore the original value so the edited print preset matches the
    // selected one again (new_project does not reset preset dirtiness, and
    // later cases must start from a clean preset state).
    print_tab->get_config()->set_key_value("sparse_infill_density", new ConfigOptionPercent(old_density));
    app.mainframe->on_config_changed(print_tab->get_config());

    // Leave a clean slate for other cases in the same process.
    app.plater_->new_project(true);
}

// ---------------------------------------------------------------------------
// P0-2: print-preset switch -> gcode header follows the new preset.
//
// Business path: Tab::select_preset (the preset combo-box path) on the print
// tab, then reslice; assert the "; layer_height" header line and the gcode
// artifact moved with the preset (0.40 Standard -> 0.24 Standard).
//
// NOTE on the preset type: the filament-preset variant is not exercised here
// because on this machine the user config boots with 5 filament slots; in a
// multi-filament project the per-slot physical filament assignments drive the
// header, and the tab's select_preset does not rewrite them (only the
// `num_filaments <= 1` path in PresetBundle::full_fff_config maps the edited
// preset directly). The print preset is slot-independent, so the
// switch->reslice->header linkage is exercised deterministically with it.
// ---------------------------------------------------------------------------
TEST_CASE("print preset switch changes gcode header", "[gui][fullapp][slow]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.plater_ != nullptr);
    REQUIRE(app.preset_bundle != nullptr);

    const std::string model_path = std::string(TEST_DATA_DIR) + "/test_3mf/Prusa.stl";
    const std::vector<size_t> loaded = load_project_file(app.plater_, model_path);
    REQUIRE(!loaded.empty());
    wait_ui_worker_idle(app.plater_);

    PartPlate* plate = app.plater_->get_partplate_list().get_curr_plate();
    REQUIRE(plate != nullptr);

    app.plater_->reslice();
    wait_slice_valid(plate);
    REQUIRE(plate->is_slice_result_valid());
    const std::string gcode_before = read_gcode(plate);
    const std::string layer_before = gcode_header_value(gcode_before, "; layer_height = ");
    INFO("layer height before = [" << layer_before << "]");
    REQUIRE(!layer_before.empty());

    // Fresh project: nothing dirty, so select_preset must not ask to save.
    // (Defensive: an earlier case may have left the print preset dirty —
    // new_project does not reset preset dirtiness — so revert it first via
    // the production "discard changes" path.)
    Tab* print_tab = app.get_tab(Preset::TYPE_PRINT);
    REQUIRE(print_tab != nullptr);
    if (print_tab->current_preset_is_dirty())
        app.preset_bundle->prints.discard_current_changes();
    REQUIRE(!print_tab->current_preset_is_dirty());

    // Pick a print preset with a different layer height than the current one.
    std::string target = "0.24 Standard @Snapmaker U1 (0.8 nozzle)";
    if (layer_before.find("0.24") != std::string::npos)
        target = "0.40 Standard @Snapmaker U1 (0.8 nozzle)";
    const std::string target_layer = target.find("0.24") != std::string::npos ? "0.24" : "0.4";
    INFO("switching print preset to " << target << " (layer " << target_layer << ")");

    const bool switched = print_tab->select_preset(target);
    REQUIRE(switched);
    CHECK(print_tab->get_presets()->get_selected_preset_name() == target);
    pump_events();

    app.plater_->reslice();
    REQUIRE(wait_gcode_change(plate, gcode_before));
    const std::string gcode_after = read_gcode(plate);
    const std::string layer_after = gcode_header_value(gcode_after, "; layer_height = ");
    INFO("layer height after = [" << layer_after << "]");

    REQUIRE(layer_after != layer_before);
    REQUIRE(layer_after.find(target_layer) != std::string::npos);

    // Switch back so later cases slice with the project default preset.
    const std::string prev_name = print_tab->get_presets()->get_selected_preset_name();
    if (prev_name != target) {
        const bool switched_back = print_tab->select_preset(prev_name);
        REQUIRE(switched_back);
    }

    app.plater_->new_project(true);
}

// ---------------------------------------------------------------------------
// P0-3: multi-plate project — every plate slices to its own G-code artifact.
// snapmates_nonmixed.3mf carries 7 plates / 19 objects; each plate must be
// resliced individually and produce a non-empty temp gcode.
// ---------------------------------------------------------------------------
TEST_CASE("multi-plate project slices every plate", "[gui][fullapp][slow]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.plater_ != nullptr);
    REQUIRE(app.app_config != nullptr);

    // The project embeds preset configs that validate_presets flags as
    // "modified G-code", which would pop a modal confirm dialog and hang the
    // test. Setting this app_config key is the persisted "don't warn again"
    // checkbox of that very dialog — the same business path a user takes.
    const std::string prev_no_warn = app.app_config->get("no_warn_when_modified_gcodes");
    app.app_config->set("no_warn_when_modified_gcodes", "true");

    const std::string model_path = std::string(TEST_DATA_DIR) + "/test_3mf/snapmates_nonmixed.3mf";
    const std::vector<size_t> loaded = load_project_file(app.plater_, model_path);
    REQUIRE(!loaded.empty());
    wait_ui_worker_idle(app.plater_, 60);

    Slic3r::GUI::PartPlateList& plates = app.plater_->get_partplate_list();
    const int plate_count = plates.get_plate_count();
    INFO("loaded plates = " << plate_count
         << ", objects = " << app.plater_->model().objects.size());
    REQUIRE(plate_count >= 2);
    CHECK(app.plater_->model().objects.size() >= 2);

    for (int i = 0; i < plate_count; ++i) {
        app.plater_->select_plate(i);
        pump_events(50);
        REQUIRE(plates.get_curr_plate_index() == i);
        PartPlate* plate = plates.get_plate(i);
        REQUIRE(plate != nullptr);

        app.plater_->reslice();
        wait_slice_valid(plate, 180);
        REQUIRE(plate->is_slice_result_valid());
        const std::string gcode = read_gcode(plate);
        INFO("plate " << i << ": gcode size = " << gcode.size());
        CHECK(gcode.size() > 1000);
    }

    // Restore the user's original warning preference.
    app.app_config->set("no_warn_when_modified_gcodes", prev_no_warn);

    app.plater_->new_project(true);
}

// ---------------------------------------------------------------------------
// P0-4: export_3mf writes a real artifact that reloads as a project.
// ---------------------------------------------------------------------------
TEST_CASE("export_3mf artifact reloads as a project", "[gui][fullapp]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.plater_ != nullptr);

    const std::string model_path = std::string(TEST_DATA_DIR) + "/test_3mf/mixed_filament_test.3mf";
    const std::vector<size_t> loaded = load_project_file(app.plater_, model_path);
    REQUIRE(!loaded.empty());
    wait_ui_worker_idle(app.plater_);
    const size_t obj_count_before = app.plater_->model().objects.size();
    REQUIRE(obj_count_before > 0);

    // Export through the production path with an explicit path (no dialog).
    const std::string out_path = make_output_path("export_test", ".3mf");
    const int ret = app.plater_->export_3mf(out_path, SaveStrategy::Default);
    INFO("export_3mf ret = " << ret << ", path = " << out_path);
    REQUIRE(ret == 0);
    REQUIRE(boost::filesystem::exists(out_path));
    CHECK(boost::filesystem::file_size(out_path) > 0);

    // The artifact must reload as a project with the same scene.
    app.plater_->new_project(true);
    CHECK(app.plater_->model().objects.empty());

    const std::vector<size_t> reloaded = load_project_file(app.plater_, out_path);
    REQUIRE(!reloaded.empty());
    CHECK(app.plater_->model().objects.size() == obj_count_before);
    CHECK(app.preset_bundle->printers.get_selected_preset_name() == "Snapmaker U1 (0.8 nozzle)");

    app.plater_->new_project(true);
}

// ---------------------------------------------------------------------------
// P1-5: select an object and transform it; the instance matrix reflects the
// move/rotate/scale. Selection goes through the canvas selection path (the
// same one a click uses); the transform takes a snapshot first and refreshes
// via changed_object — the same sequence the gizmo applies.
// ---------------------------------------------------------------------------
TEST_CASE("object transform reflects in instance matrix", "[gui][fullapp]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.plater_ != nullptr);

    const std::string model_path = std::string(TEST_DATA_DIR) + "/test_3mf/Prusa.stl";
    const std::vector<size_t> loaded = load_project_file(app.plater_, model_path);
    REQUIRE(!loaded.empty());
    REQUIRE(app.plater_->model().objects.size() == 1);

    // Select object 0 through the selection API the object list / canvas
    // click paths use.
    GLCanvas3D* canvas = app.plater_->get_view3D_canvas3D();
    REQUIRE(canvas != nullptr);
    canvas->get_selection().add_object(0);
    pump_events(30);
    INFO("selection object idx = " << app.plater_->get_selection().get_object_idx());
    CHECK(app.plater_->get_selection().get_object_idx() == 0);

    ModelObject* obj = app.plater_->model().objects.front();
    REQUIRE(obj != nullptr);
    REQUIRE(!obj->instances.empty());
    ModelInstance* inst = obj->instances.front();

    app.plater_->take_snapshot("test move/rotate/scale");
    inst->set_offset(Vec3d(60.0, 60.0, 0.0));
    inst->set_rotation(Vec3d(0.0, 0.0, PI / 4.0));
    inst->set_scaling_factor(Vec3d(1.5, 1.5, 1.5));
    app.plater_->changed_object(*obj);
    pump_events();

    CHECK(inst->get_offset() == Vec3d(60.0, 60.0, 0.0));
    const Vec3d rotation = inst->get_rotation();
    INFO("rotation = " << rotation(0) << "," << rotation(1) << "," << rotation(2));
    CHECK(rotation(2) == Catch::Approx(PI / 4.0));
    const Vec3d scaling = inst->get_scaling_factor();
    INFO("scaling = " << scaling(0) << "," << scaling(1) << "," << scaling(2));
    CHECK(scaling(0) == Catch::Approx(1.5));

    app.plater_->new_project(true);
}

// ---------------------------------------------------------------------------
// P1-6: undo/redo roll the instance transform back and forth through the real
// UndoRedo stack (snapshot -> mutate -> undo -> redo).
// ---------------------------------------------------------------------------
TEST_CASE("undo and redo restore instance transform", "[gui][fullapp]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.plater_ != nullptr);

    const std::string model_path = std::string(TEST_DATA_DIR) + "/test_3mf/Prusa.stl";
    const std::vector<size_t> loaded = load_project_file(app.plater_, model_path);
    REQUIRE(!loaded.empty());
    REQUIRE(app.plater_->model().objects.size() == 1);

    ModelObject* obj = app.plater_->model().objects.front();
    REQUIRE(obj != nullptr);
    REQUIRE(!obj->instances.empty());
    const Vec3d orig_offset = obj->instances.front()->get_offset();

    app.plater_->take_snapshot("test move");
    obj->instances.front()->set_offset(Vec3d(60.0, 60.0, 0.0));
    app.plater_->changed_object(*obj);
    pump_events(30);
    CHECK(obj->instances.front()->get_offset() == Vec3d(60.0, 60.0, 0.0));

    // Undo: the model is restored from the snapshot, so re-fetch the objects.
    REQUIRE(app.plater_->can_undo());
    app.plater_->undo();
    pump_events(30);
    obj = app.plater_->model().objects.front();
    CHECK(obj->instances.front()->get_offset() == orig_offset);

    // Redo: the transform comes back.
    REQUIRE(app.plater_->can_redo());
    app.plater_->redo();
    pump_events(30);
    obj = app.plater_->model().objects.front();
    CHECK(obj->instances.front()->get_offset() == Vec3d(60.0, 60.0, 0.0));

    app.plater_->new_project(true);
}

// ---------------------------------------------------------------------------
// P1-7: delete one object and clear the whole scene; the model count follows.
// ---------------------------------------------------------------------------
TEST_CASE("delete object and clear scene update model count", "[gui][fullapp]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.plater_ != nullptr);

    // Two single-object projects side by side give a 2-object scene.
    const std::string stl_path = std::string(TEST_DATA_DIR) + "/test_3mf/Prusa.stl";
    const std::string m3mf_path = std::string(TEST_DATA_DIR) + "/test_3mf/mixed_filament_test.3mf";
    const std::vector<size_t> loaded = load_project_file(app.plater_, stl_path);
    REQUIRE(!loaded.empty());
    const std::vector<size_t> loaded2 = load_project_file(app.plater_, m3mf_path);
    REQUIRE(!loaded2.empty());
    const size_t n = app.plater_->model().objects.size();
    REQUIRE(n >= 2);

    REQUIRE(app.plater_->delete_object_from_model(0));
    CHECK(app.plater_->model().objects.size() == n - 1);

    app.plater_->delete_all_objects_from_model();
    CHECK(app.plater_->model().objects.empty());

    app.plater_->new_project(true);
}

// ---------------------------------------------------------------------------
// P2-8: topbar edit-menu command dispatched through the frame handler chain
// (wxEVT_MENU with the real menu item id) — the "Delete all" business path.
// ---------------------------------------------------------------------------
TEST_CASE("topbar edit menu delete-all dispatches via ProcessEvent", "[gui][fullapp]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.mainframe != nullptr);

    const std::string model_path = std::string(TEST_DATA_DIR) + "/test_3mf/mixed_filament_test.3mf";
    const std::vector<size_t> loaded = load_project_file(app.plater_, model_path);
    REQUIRE(!loaded.empty());
    REQUIRE(app.plater_->model().objects.size() > 0);

    // The edit menu ("Delete all" = Ctrl+D) is a dropdown submenu of the
    // topbar's top menu on Windows.
    wxMenu* top_menu = app.mainframe->topbar()->GetTopMenu();
    REQUIRE(top_menu != nullptr);
    wxMenuItem* delete_all = find_menu_item_by_accel(top_menu, "\tCtrl+D");
    REQUIRE(delete_all != nullptr);

    // Dispatch the menu event through the owning menu's handler chain: on
    // Windows the menu items bind their handler on the wxMenu itself (see
    // append_menu_item in wxExtensions.cpp), so the event must be processed
    // by the menu, not the frame.
    wxMenuEvent evt(wxEVT_MENU, delete_all->GetId());
    evt.SetEventObject(app.mainframe);
    wxMenu* owner_menu = delete_all->GetMenu();
    REQUIRE(owner_menu != nullptr);
    const bool handled = owner_menu->GetEventHandler()->ProcessEvent(evt);
    pump_events();
    INFO("menu event handled = " << (handled ? "true" : "false"));
    CHECK(handled);
    CHECK(app.plater_->model().objects.empty());

    app.plater_->new_project(true);
}

// ---------------------------------------------------------------------------
// P2-9: tab switching flips the plater between the 3D editor and the preview
// view (production view state, not control internals).
// ---------------------------------------------------------------------------
TEST_CASE("tab switching flips prepare and preview views", "[gui][fullapp]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.mainframe != nullptr);
    REQUIRE(app.plater_ != nullptr);

    app.mainframe->select_tab(MainFrame::tp3DEditor);
    pump_events();
    INFO("view3D shown after Prepare tab = " << (app.plater_->is_view3D_shown() ? "true" : "false"));
    CHECK(app.plater_->is_view3D_shown());

    app.mainframe->select_tab(MainFrame::tpPreview);
    pump_events();
    INFO("preview shown after Preview tab = " << (app.plater_->is_preview_shown() ? "true" : "false"));
    CHECK(app.plater_->is_preview_shown());

    app.mainframe->select_tab(MainFrame::tp3DEditor);
    pump_events();
    CHECK(app.plater_->is_view3D_shown());
}

// ---------------------------------------------------------------------------
// P3-13: an empty scene rejects slicing (production sliceability state).
// The plater's slice gate requires printable instances; reslicing an empty
// scene must not produce a slice result.
// ---------------------------------------------------------------------------
TEST_CASE("empty scene rejects slicing", "[gui][fullapp]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.plater_ != nullptr);

    app.plater_->new_project(true);
    REQUIRE(app.plater_->model().objects.empty());

    PartPlate* plate = app.plater_->get_partplate_list().get_curr_plate();
    REQUIRE(plate != nullptr);
    CHECK(!plate->has_printable_instances());

    // Slicing an empty scene must not produce an artifact: poll briefly and
    // assert the slice result stays invalid.
    app.plater_->reslice();
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(5);
    while (std::chrono::steady_clock::now() < deadline) {
        wxYield();
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    INFO("slice result valid after empty reslice = " << (plate->is_slice_result_valid() ? "true" : "false"));
    CHECK(!plate->is_slice_result_valid());
}

// ---------------------------------------------------------------------------
// P3-12: a corrupted 3mf fails the load gracefully — no crash, no model
// mutation, and the plater stays fully functional for the next project.
// ---------------------------------------------------------------------------
TEST_CASE("corrupted 3mf load fails without crash", "[gui][fullapp]")
{
    GUI_App& app = fullapp();
    REQUIRE(app.plater_ != nullptr);

    app.plater_->new_project(true);
    const size_t objects_before = app.plater_->model().objects.size();

    const std::string bad_path = make_output_path("corrupt_probe", ".3mf");
    {
        std::ofstream out(bad_path, std::ios::binary);
        out << "this is not a 3mf archive";
    }

    const std::vector<size_t> loaded = app.plater_->load_files(
        std::vector<std::string>{bad_path},
        LoadStrategy::LoadModel | LoadStrategy::LoadConfig | LoadStrategy::Silence);
    pump_events();
    INFO("load result for corrupt file = " << loaded.size() << " objects");
    CHECK(loaded.empty());
    CHECK(app.plater_->model().objects.size() == objects_before);

    // The plater must still accept a real project afterwards.
    const std::string model_path = std::string(TEST_DATA_DIR) + "/test_3mf/mixed_filament_test.3mf";
    const std::vector<size_t> ok = load_project_file(app.plater_, model_path);
    REQUIRE(!ok.empty());
    CHECK(app.plater_->model().objects.size() > 0);

    app.plater_->new_project(true);
}
