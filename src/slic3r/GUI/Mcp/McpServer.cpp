#include "McpServer.hpp"
#include "McpHttpListener.hpp"
#include "McpJobs.hpp"
#include "McpJsonRpc.hpp"
#include "McpParams.hpp"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <fstream>
#include <random>
#include <sstream>

#include <boost/filesystem.hpp>
#include <boost/log/trivial.hpp>
#include <nlohmann/json.hpp>
#include <wx/base64.h>
#include <wx/timer.h>

#include "libslic3r/Model.hpp"
#include "libslic3r/Utils.hpp"
#include "libslic3r/GCode/ThumbnailData.hpp"
#include "libslic3r/Format/bbs_3mf.hpp"
#include "libslic3r/miniz_extension.hpp"
#include "slic3r/GUI/BackgroundSlicingProcess.hpp"
#include "slic3r/GUI/GLCanvas3D.hpp"
#include "slic3r/GUI/GLToolbar.hpp"
#include "slic3r/GUI/FlowTypeHelper.hpp"
#include "slic3r/GUI/MainFrame.hpp"
#include "libslic3r/PrintConfig.hpp"
#include <wx/modalhook.h>
#include "slic3r/GUI/GUI_App.hpp"
#include "slic3r/GUI/GUI_ObjectList.hpp"
#include "slic3r/GUI/DeviceManager.hpp"
#include "slic3r/GUI/PartPlate.hpp"
#include "slic3r/GUI/Plater.hpp"

namespace Slic3r {
namespace Mcp {

namespace {

constexpr int kSnapshotIntervalMs  = 1500; // low-frequency freshness floor
constexpr int kScreenshotDefaultPx = 512;
constexpr int kSnapshotTimerId     = 4242;
constexpr int kSliceWatchdogId     = 4243;
// If the background process shows no completion event this long after a
// slice request, report failure instead of leaving the job hanging forever
// (observed: slice-finalize thumbnail render can stall on machines with a
// broken on-screen GL canvas).
constexpr int kSliceWatchdogMs     = 180000;
constexpr int kExportRetryId      = 4244;
constexpr int kExportRetryMs      = 1000;
constexpr int kSliceStartWatchdogId = 4245;
// If slicing produces no progress at all this long after the request, the
// slice event was silently swallowed (e.g. reslice() no-ops when a previous
// validation failure set process_completed_with_error). Fail fast with an
// actionable message instead of burning the full watchdog window.
constexpr int kSliceStartWatchdogMs = 25000;

std::int64_t unix_now_seconds()
{
    return std::chrono::duration_cast<std::chrono::seconds>(
               std::chrono::system_clock::now().time_since_epoch())
        .count();
}

/// Counts open modal dialogs. While any modal dialog owns the UI, MCP
/// write operations are refused with "UI busy" instead of queueing behind
/// a dialog the user cannot see (integration plan section 5, item 4).
class ModalDepthHook : public wxModalDialogHook
{
public:
    void Register() { wxModalDialogHook::Register(); }
    int depth() const { return m_depth.load(); }
    /// Title of the most recent dialog to enter modal state (diagnostics:
    /// answers "which dialog owns the UI" for agents and E2E).
    std::string last_title() const
    {
        std::lock_guard<std::mutex> lock(m_title_mutex);
        return m_last_title;
    }
    /// Native handle of that dialog (lets a test harness close it when the
    /// window is not discoverable via Win32 enumeration).
    void* last_handle() const
    {
        std::lock_guard<std::mutex> lock(m_title_mutex);
        return m_last_handle;
    }

protected:
    int Enter(wxDialog* dialog) override
    {
        if (dialog != nullptr) {
            const wxString title = dialog->GetTitle();
            void* handle = dialog->GetHandle();
            std::lock_guard<std::mutex> lock(m_title_mutex);
            m_last_title = title.ToUTF8().data();
            m_last_handle = handle;
        }
        ++m_depth;
        return 0;
    }
    void Exit(wxDialog* /*dialog*/) override { --m_depth; }

private:
    std::atomic<int> m_depth{0};
    mutable std::mutex m_title_mutex;
    std::string m_last_title;
    void* m_last_handle = nullptr;
};

ModalDepthHook* modal_hook()
{
    static ModalDepthHook hook;
    return &hook;
}

Slic3r::GUI::GUI_App* app_or_null()
{
    return wxTheApp == nullptr ? nullptr
               : static_cast<Slic3r::GUI::GUI_App*>(wxTheApp);
}

GUI::Plater* plater_or_null()
{
    Slic3r::GUI::GUI_App* app = app_or_null();
    return app == nullptr ? nullptr : app->plater();
}

std::string data_dir_or_empty()
{
    // The Orca data dir is a process-global set by --datadir (not an
    // app_config key) - the discovery file must land where the bridge looks.
    return data_dir();
}

} // namespace

std::string generate_token()
{
    // 128 bits of randomness, hex-encoded: enough to block browser
    // drive-by posts against loopback (integration plan section 5).
    std::random_device source;
    std::mt19937_64    engine(source());
    std::ostringstream out;
    out << std::hex;
    for (int word = 0; word < 4; ++word) {
        const std::uint64_t value =
            (static_cast<std::uint64_t>(source()) << 32) ^ engine();
        out.width(16);
        out.fill('0');
        out << value;
    }
    return out.str();
}

bool write_discovery_file(const std::string& data_dir, unsigned short port, const std::string& token)
{
    if (data_dir.empty()) {
        return false;
    }
    try {
        const boost::filesystem::path dir(data_dir);
        boost::filesystem::create_directories(dir);
        std::ofstream file((dir / "mcp_session.json").string(),
                           std::ios::out | std::ios::trunc);
        if (!file.is_open()) {
            return false;
        }
        nlohmann::json doc = nlohmann::json::object();
        doc["port"]        = port;
        doc["token"]       = token;
        file << doc.dump() << std::endl;
        return file.good();
    } catch (const std::exception& ex) {
        BOOST_LOG_TRIVIAL(error) << "McpServer discovery file write failed: " << ex.what();
        return false;
    }
}

void remove_discovery_file(const std::string& data_dir)
{
    if (data_dir.empty()) {
        return;
    }
    boost::system::error_code ignored_ec;
    boost::filesystem::remove(boost::filesystem::path(data_dir) / "mcp_session.json",
                              ignored_ec);
}

McpServer& McpServer::instance()
{
    static McpServer server;
    return server;
}

McpServer::McpServer()
    : m_marshaler(std::make_shared<UiMarshaler>())
{}

void McpServer::startup_from_config()
{
    Slic3r::GUI::GUI_App* app = app_or_null();
    if (app == nullptr || app->app_config == nullptr) {
        return;
    }
    if (app->app_config->get(ConfigKeyEnabled) != "true") {
        return;
    }
    if (!enable()) {
        BOOST_LOG_TRIVIAL(error) << "McpServer: preference enabled but startup failed";
    }
}

void McpServer::shutdown()
{
    if (m_snapshot_timer != nullptr) {
        m_snapshot_timer->Stop();
        m_snapshot_timer.reset();
    }
    m_listener.reset();
    m_enabled = false;
    remove_discovery_file(data_dir_or_empty());
}

bool McpServer::is_enabled() const
{
    return m_enabled.load();
}

bool McpServer::is_running() const
{
    return m_listener != nullptr && m_listener->is_running();
}

std::string McpServer::token() const
{
    Slic3r::GUI::GUI_App* app = app_or_null();
    if (app == nullptr || app->app_config == nullptr) {
        return std::string();
    }
    return app->app_config->get(ConfigKeyToken);
}

bool McpServer::enable()
{
    Slic3r::GUI::GUI_App* app = app_or_null();
    if (app == nullptr || app->app_config == nullptr) {
        return false;
    }
    std::string tkn = app->app_config->get(ConfigKeyToken);
    if (tkn.empty()) {
        tkn = generate_token();
        app->app_config->set(ConfigKeyToken, tkn);
        app->app_config->save();
    }
    if (m_listener != nullptr && m_listener->is_running()) {
        m_enabled = true;
        return true;
    }
    m_listener = std::make_unique<HttpListener>(
        tkn, [this](const std::string& method, const std::string& body) {
            return dispatch(method, body);
        });
    if (!m_listener->start(McpServicePort)) {
        m_listener.reset();
        return false;
    }
    const std::string data_dir = data_dir_or_empty();
    if (!write_discovery_file(data_dir, McpServicePort, tkn)) {
        BOOST_LOG_TRIVIAL(warning)
            << "McpServer: discovery file could not be written to " << data_dir;
    }
    app->app_config->set(ConfigKeyEnabled, "true");
    app->app_config->save();
    m_enabled = true;

    // UI-thread follow-ups: plater event hooks, snapshot freshness loop.
    m_marshaler->post([this]() {
        modal_hook()->Register();
        ui_install_plater_hooks();
        rebuild_snapshot();
        m_snapshot_timer = std::make_unique<wxTimer>();
        m_snapshot_timer->SetOwner(m_marshaler.get(), kSnapshotTimerId);
        m_marshaler->Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
            // Freshness floor + post-modal catch-up: runs on the UI thread
            // even while a modal dialog pumps its nested loop.
            if (m_export_retry_job != 0) {
                ui_export_gcode_step(m_export_retry_job, m_export_retry_path,
                                     m_export_retry_attempt);
            }
            rebuild_snapshot();
        }, kSnapshotTimerId);
        m_snapshot_timer->Start(kSnapshotIntervalMs);
    });
    return true;
}

void McpServer::disable()
{
    Slic3r::GUI::GUI_App* app = app_or_null();
    if (app != nullptr && app->app_config != nullptr) {
        app->app_config->set(ConfigKeyEnabled, "false");
        app->app_config->save();
    }
    m_enabled = false;
    if (m_snapshot_timer != nullptr) {
        m_snapshot_timer->Stop();
        m_snapshot_timer.reset();
    }
    // Plater event hooks stay bound for the app lifetime on purpose: they
    // are cheap observers, and Unbind-by-lambda is fragile. The listener is
    // fully stopped, so the hooks have no consumer.
    m_listener.reset();
    remove_discovery_file(data_dir_or_empty());
}

void McpServer::ui_install_plater_hooks()
{
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        return;
    }
    m_hook_plater = plater;
    // Progress observation only: these bindings never mutate Plater.
    plater->Bind(GUI::EVT_SLICING_UPDATE, [this](SlicingStatusEvent& event) {
        {
            std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
            if (m_slice_job_in_flight != 0) {
                McpJobRegistry::instance().set_running(m_slice_job_in_flight,
                                                       event.status.percent,
                                                       event.status.text);
            }
        }
        if (event.status.percent > 0) {
            m_slice_progress_seen = true;
            if (m_slice_start_watchdog_timer != nullptr) {
                m_slice_start_watchdog_timer->Stop();
            }
        }
        std::lock_guard<std::mutex> lock(m_snapshot_mutex);
        if (m_snapshot.is_object()) {
            m_snapshot["slicing_state"] = nlohmann::json{
                {"active", true}, {"percent", event.status.percent}};
        }
    });
    plater->Bind(GUI::EVT_PROCESS_COMPLETED, [this](SlicingProcessCompletedEvent& event) {
        std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
        if (m_slice_job_in_flight != 0) {
            if (event.finished()) {
                McpJobRegistry::instance().set_result(
                    m_slice_job_in_flight,
                    nlohmann::json{{"outcome", "sliced"}});
                m_slice_job_in_flight = 0;
            } else if (event.error()) {
                McpJobRegistry::instance().set_failed(m_slice_job_in_flight,
                                                      "slicing failed (see Orca UI)");
                m_slice_job_in_flight = 0;
            }
            // event.cancelled(): Orca's own restart flow emits Cancelled
            // completions when it tears down a superseded run (e.g. the
            // auto-reslice our explicit slice replaces). Failing the job on
            // those misattributes unrelated teardown; the start watchdog
            // fails the job honestly if no progress ever shows up.
            m_slice_job_in_flight = 0;
        }
        if (m_export_job_in_flight != 0) {
            // The export path was validated when the job was created; the
            // background process finishing is the success signal.
            McpJobRegistry::instance().set_result(
                m_export_job_in_flight, nlohmann::json{{"outcome", "exported"}});
            m_export_job_in_flight = 0;
        }
        m_marshaler->post([this]() { rebuild_snapshot(); });
    });
}

void McpServer::rebuild_snapshot()
{
    // Hooks need a live Plater; enable() runs during on_init, before the
    // mainframe (and its Plater) exists, so retry on every refresh until
    // they stick.
    if (m_hook_plater == nullptr) {
        ui_install_plater_hooks();
    }
    // Belt-and-suspenders start watchdog: this beat runs every 1.5s on the
    // UI thread even when slicing stalls, so enforce the "never started"
    // deadline here as well, not only via the one-shot timer.
    {
        std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
        if (m_slice_job_in_flight != 0 && !m_slice_progress_seen.load()
            && std::chrono::steady_clock::now() - m_slice_watch_start
                   > std::chrono::milliseconds(kSliceStartWatchdogMs)) {
            McpJobSnapshot snapshot;
            if (McpJobRegistry::instance().get(m_slice_job_in_flight, snapshot)
                && (snapshot.state == JobState::Running
                    || snapshot.state == JobState::Pending)) {
                McpJobRegistry::instance().set_failed(
                    m_slice_job_in_flight,
                    "slicing never started - the plate likely has a "
                    "validation error (Orca's reslice() no-ops in that "
                    "state); check the Orca UI");
                m_slice_job_in_flight = 0;
            }
        }
    }
    nlohmann::json snapshot = build_snapshot();
    std::lock_guard<std::mutex> lock(m_snapshot_mutex);
    m_snapshot = std::move(snapshot);
}

void McpServer::clear_snapshot_for_tests()
{
    std::lock_guard<std::mutex> lock(m_snapshot_mutex);
    m_snapshot = nlohmann::json::object();
}

nlohmann::json McpServer::snapshot_copy() const
{
    std::lock_guard<std::mutex> lock(m_snapshot_mutex);
    return m_snapshot;
}

nlohmann::json McpServer::build_snapshot()
{
    // UI thread only (wx object traversal + Model reads).
    nlohmann::json snapshot      = nlohmann::json::object();
    snapshot["stale_at"]         = unix_now_seconds();
    snapshot["slicing_state"]    = nlohmann::json{{"active", false}, {"percent", 0}};

    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        snapshot["ready"] = false;
        return snapshot;
    }
    snapshot["ready"] = true;

    const Model& model = plater->model();
    nlohmann::json objects = nlohmann::json::array();
    for (const ModelObject* object : model.objects) {
        if (object == nullptr) {
            continue;
        }
        nlohmann::json obj = nlohmann::json::object();
        obj["id"]          = static_cast<std::int64_t>(object->id().id);
        obj["name"]        = object->name;
        obj["volumes"]     = static_cast<int>(object->volumes.size());
        nlohmann::json instances = nlohmann::json::array();
        for (const ModelInstance* instance : object->instances) {
            if (instance == nullptr) {
                continue;
            }
            const char* pvs = "unknown";
            switch (instance->print_volume_state) {
            case Slic3r::ModelInstancePVS_Inside:  pvs = "inside"; break;
            case Slic3r::ModelInstancePVS_Partly_Outside: pvs = "partly_outside"; break;
            case Slic3r::ModelInstancePVS_Fully_Outside: pvs = "fully_outside"; break;
            }
            instances.push_back(nlohmann::json{
                {"translation", instance->get_offset()},
                {"rotation", instance->get_rotation()},
                {"scaling_factor", instance->get_scaling_factor()},
                {"print_volume_state", pvs},
            });
        }
        obj["instances"] = std::move(instances);
        if (!object->config.empty()) {
            nlohmann::json overrides = nlohmann::json::object();
            for (const std::string& key : object->config.keys()) {
                overrides[key] = object->config.opt_serialize(key);
            }
            obj["config_overrides"] = std::move(overrides);
        }
        obj["out_of_bounds"] =
            std::any_of(obj["instances"].begin(), obj["instances"].end(),
                        [](const nlohmann::json& entry) {
                            return entry.value("print_volume_state", std::string())
                                != "inside";
                        });
        objects.push_back(std::move(obj));
    }
    snapshot["objects"] = std::move(objects);

    GUI::PartPlateList& plates      = plater->get_partplate_list();
    nlohmann::json  plates_json = nlohmann::json::array();
    const int       plate_count = plates.get_plate_count();
    for (int index = 0; index < plate_count; ++index) {
        GUI::PartPlate* plate = plates.get_plate(index);
        if (plate == nullptr) {
            continue;
        }
        const BoundingBoxf3& bbox = plate->get_bounding_box(false);
        nlohmann::json plate_json = nlohmann::json{
            {"index", index + 1},
            {"bounding_box",
             nlohmann::json{{"min", {bbox.min(0), bbox.min(1), bbox.min(2)}},
                            {"max", {bbox.max(0), bbox.max(1), bbox.max(2)}}}},
        };
        if (plate->config() != nullptr && !plate->config()->empty()) {
            nlohmann::json overrides = nlohmann::json::object();
            for (const std::string& key : plate->config()->keys()) {
                overrides[key] = plate->config()->opt_serialize(key);
            }
            plate_json["config_overrides"] = std::move(overrides);
        }
        plates_json.push_back(std::move(plate_json));
    }
    snapshot["plates"]        = std::move(plates_json);
    snapshot["current_plate"] = plates.get_curr_plate_index() + 1;
    GUI::PartPlate* curr_plate = plates.get_curr_plate();
    if (curr_plate != nullptr) {
        snapshot["current_plate_slice_valid"] = curr_plate->is_slice_result_valid();
        snapshot["current_plate_apply_invalid"] = curr_plate->is_apply_result_invalid();
    }
    snapshot["ui_busy"] = modal_hook()->depth() > 0;
    snapshot["ui_busy_dialog"] = modal_hook()->last_title();
    if (modal_hook()->last_handle() != nullptr) {
        snapshot["ui_busy_hwnd"] = reinterpret_cast<std::intptr_t>(
            modal_hook()->last_handle());
    } else {
        snapshot["ui_busy_hwnd"] = nlohmann::json();
    }
    DeviceManager* device_manager =
        app_or_null() != nullptr ? app_or_null()->getDeviceManager() : nullptr;
    snapshot["devices"]         = nlohmann::json::array();
    snapshot["selected_device"] = nlohmann::json();
    if (device_manager != nullptr) {
        auto add_devices = [&snapshot](const std::map<std::string, MachineObject*>& list,
                                       const char* source) {
            nlohmann::json devices = snapshot.value("devices", nlohmann::json::array());
            for (const auto& entry : list) {
                MachineObject* object = entry.second;
                if (object == nullptr) {
                    continue;
                }
                devices.push_back(nlohmann::json{
                    {"dev_id", object->dev_id},
                    {"name", object->dev_name},
                    {"online", object->is_online()},
                    {"source", source},
                });
            }
            snapshot["devices"] = std::move(devices);
        };
        add_devices(device_manager->get_my_machine_list(), "user");
        add_devices(device_manager->get_local_machine_list(), "local");
        MachineObject* selected = device_manager->get_selected_machine();
        if (selected != nullptr) {
            snapshot["selected_device"] = selected->dev_id;
        }
    }
    return snapshot;
}

std::string McpServer::dispatch(const std::string& /*method*/, const std::string& body)
{
    // Runs on the listener thread. No wx calls may appear below this line;
    // UI work must be deferred through m_marshaler->post.
    const McpRequest request = parse_request(body);
    if (!request.ok) {
        return build_error(RpcErrorCode::ParseError, request.error, request.has_id, request.id);
    }

    if (request.method == "ping") {
        return build_result(nlohmann::json{{"pong", true}}, request.has_id, request.id);
    }
    if (request.method == "get_state") {
        // Snapshot cache read: never touches the UI thread.
        nlohmann::json state = snapshot_copy();
        if (state.empty()) {
            state = nlohmann::json{{"ready", false}};
        }
        return build_result(state, request.has_id, request.id);
    }
    if (request.method == "list_devices") {
        // Snapshot cache read: the device list is gathered on the UI thread
        // like every other read, so a modal dialog never blocks it.
        nlohmann::json state = snapshot_copy();
        if (state.empty()) {
            state = nlohmann::json{{"ready", false}};
        }
        nlohmann::json result = nlohmann::json{
            {"devices", state.value("devices", nlohmann::json::array())},
            {"selected_device",
             state.value("selected_device", nlohmann::json())},
        };
        return build_result(result, request.has_id, request.id);
    }
    if (request.method == "poll_job") {
        const int job_id = request.params.value("job_id", 0);
        McpJobSnapshot snapshot;
        if (job_id <= 0 || !McpJobRegistry::instance().get(job_id, snapshot)) {
            return build_error(RpcErrorCode::UnknownJob,
                               "unknown job id: " + std::to_string(job_id),
                               request.has_id, request.id);
        }
        nlohmann::json result = nlohmann::json::object();
        result["job_id"]      = snapshot.id;
        result["kind"]        = snapshot.kind;
        result["state"]       = job_state_name(snapshot.state);
        result["percent"]     = snapshot.percent;
        result["message"]     = snapshot.message;
        result["result"]      = snapshot.result;
        return build_result(result, request.has_id, request.id);
    }

    // Everything below creates a job and posts UI work. While a modal
    // dialog owns the UI the user wins: refuse writes with UI busy.
    {
        static const char* const write_methods[] = {"load_models", "slice",
            "export_gcode", "export_3mf", "get_plate_screenshot", "set_params",
            "remove_object", "set_transform", "arrange", "set_object_params",
            "set_plate_params", "send_to_print", "run_calibration", "undo"};
        bool is_write = false;
        for (const char* name : write_methods) {
            if (request.method == name) {
                is_write = true;
                break;
            }
        }
        if (is_write && modal_hook()->depth() > 0) {
            return build_error(RpcErrorCode::UiBusy,
                               "a modal dialog is open in the Orca UI - "
                               "close it and retry",
                               request.has_id, request.id);
        }
    }

    int job_id = 0;
    if (request.method == "load_models") {
        const nlohmann::json paths_json = request.params.value("paths", nlohmann::json::array());
        if (!paths_json.is_array() || paths_json.empty()) {
            return build_error(RpcErrorCode::InvalidParams, "paths must be a non-empty array",
                               request.has_id, request.id);
        }
        std::vector<std::string> paths;
        for (const auto& entry : paths_json) {
            if (!entry.is_string() || entry.get<std::string>().empty()) {
                return build_error(RpcErrorCode::InvalidParams,
                                   "every path must be a non-empty string",
                                   request.has_id, request.id);
            }
            paths.push_back(entry.get<std::string>());
        }
        job_id = McpJobRegistry::instance().create("load_models");
        m_marshaler->post([this, job_id, paths]() { ui_load_models(job_id, paths); });
    } else if (request.method == "get_plate_screenshot") {
        const int plate  = request.params.value("plate_index", 1);
        const int width  = request.params.value("width", kScreenshotDefaultPx);
        const int height = request.params.value("height", kScreenshotDefaultPx);
        if (plate < 1 || plate > 1024 || width < 32 || height < 32 || width > 2048
            || height > 2048) {
            return build_error(RpcErrorCode::InvalidParams, "invalid screenshot params",
                               request.has_id, request.id);
        }
        job_id = McpJobRegistry::instance().create("get_plate_screenshot");
        m_marshaler->post([this, job_id, plate, width, height]() {
            ui_render_screenshot(job_id, plate, width, height);
        });
    } else if (request.method == "slice") {
        const int plate = request.params.value("plate", 0);
        if (plate < 0 || plate > 1024) {
            return build_error(RpcErrorCode::InvalidParams,
                               "plate must be 0 (all) or 1..N", request.has_id, request.id);
        }
        {
            std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
            if (m_slice_job_in_flight != 0) {
                McpJobSnapshot snapshot;
                if (McpJobRegistry::instance().get(m_slice_job_in_flight, snapshot)
                    && (snapshot.state == JobState::Running
                        || snapshot.state == JobState::Pending)) {
                    return build_error(RpcErrorCode::UiBusy,
                                       "a slice job is already running (job "
                                           + std::to_string(m_slice_job_in_flight) + ")",
                                       request.has_id, request.id);
                }
            }
            job_id                = McpJobRegistry::instance().create("slice");
            m_slice_job_in_flight = job_id;
        }
        m_marshaler->post([this, job_id, plate]() { ui_slice(job_id, plate); });
    } else if (request.method == "export_gcode") {
        const std::string path = request.params.value("path", std::string());
        if (path.empty()) {
            return build_error(RpcErrorCode::InvalidParams, "path is required",
                               request.has_id, request.id);
        }
        job_id = McpJobRegistry::instance().create("export_gcode");
        m_marshaler->post([this, job_id, path]() { ui_export_gcode(job_id, path); });
    } else if (request.method == "export_3mf") {
        const std::string path = request.params.value("path", std::string());
        if (path.empty()) {
            return build_error(RpcErrorCode::InvalidParams, "path is required",
                               request.has_id, request.id);
        }
        job_id = McpJobRegistry::instance().create("export_3mf");
        m_marshaler->post([this, job_id, path]() { ui_export_3mf(job_id, path); });
    } else if (request.method == "set_params") {
        const nlohmann::json params_json =
            request.params.value("params", nlohmann::json::object());
        if (!params_json.is_object() || params_json.empty()) {
            return build_error(RpcErrorCode::InvalidParams,
                               "params must be a non-empty object of "
                               "{option: value}",
                               request.has_id, request.id);
        }
        std::map<std::string, std::string> params;
        for (auto it = params_json.begin(); it != params_json.end(); ++it) {
            if (it.value().is_string()) {
                params[it.key()] = it.value().get<std::string>();
            } else {
                params[it.key()] = it.value().dump();
            }
        }
        job_id = McpJobRegistry::instance().create("set_params");
        m_marshaler->post([this, job_id, params]() { ui_set_params(job_id, params); });
    } else if (request.method == "set_object_params") {
        const std::int64_t object_id = request.params.value("object_id", 0);
        if (object_id <= 0) {
            return build_error(RpcErrorCode::InvalidParams,
                               "object_id is required (see get_state)",
                               request.has_id, request.id);
        }
        const nlohmann::json params_json =
            request.params.value("params", nlohmann::json::object());
        if (!params_json.is_object() || params_json.empty()) {
            return build_error(RpcErrorCode::InvalidParams,
                               "params must be a non-empty object of "
                               "{option: value}",
                               request.has_id, request.id);
        }
        std::map<std::string, std::string> params;
        for (auto it = params_json.begin(); it != params_json.end(); ++it) {
            if (it.value().is_string()) {
                params[it.key()] = it.value().get<std::string>();
            } else {
                params[it.key()] = it.value().dump();
            }
        }
        job_id = McpJobRegistry::instance().create("set_object_params");
        m_marshaler->post([this, job_id, object_id, params]() {
            ui_set_object_params(job_id, object_id, params);
        });
    } else if (request.method == "set_plate_params") {
        int plate_index = request.params.value("plate", 0);
        const nlohmann::json params_json =
            request.params.value("params", nlohmann::json::object());
        if (!params_json.is_object() || params_json.empty()) {
            return build_error(RpcErrorCode::InvalidParams,
                               "params must be a non-empty object of "
                               "{option: value}",
                               request.has_id, request.id);
        }
        std::map<std::string, std::string> params;
        for (auto it = params_json.begin(); it != params_json.end(); ++it) {
            if (it.value().is_string()) {
                params[it.key()] = it.value().get<std::string>();
            } else {
                params[it.key()] = it.value().dump();
            }
        }
        job_id = McpJobRegistry::instance().create("set_plate_params");
        m_marshaler->post([this, job_id, plate_index, params]() {
            ui_set_plate_params(job_id, plate_index, params);
        });
    } else if (request.method == "remove_object") {
        const std::int64_t object_id = request.params.value("object_id", 0);
        if (object_id <= 0) {
            return build_error(RpcErrorCode::InvalidParams,
                               "object_id is required (see get_state)",
                               request.has_id, request.id);
        }
        job_id = McpJobRegistry::instance().create("remove_object");
        m_marshaler->post([this, job_id, object_id]() {
            ui_remove_object(job_id, object_id);
        });
    } else if (request.method == "set_transform") {
        const std::int64_t object_id = request.params.value("object_id", 0);
        if (object_id <= 0) {
            return build_error(RpcErrorCode::InvalidParams,
                               "object_id is required (see get_state)",
                               request.has_id, request.id);
        }
        nlohmann::json translation = request.params.value("translation_mm", nlohmann::json::object());
        nlohmann::json rotation = request.params.value("rotation_deg", nlohmann::json::object());
        nlohmann::json scaling = request.params.value("scaling_factor", nlohmann::json::object());
        job_id = McpJobRegistry::instance().create("set_transform");
        m_marshaler->post([this, job_id, object_id, translation, rotation, scaling]() {
            ui_set_transform(job_id, object_id, translation, rotation, scaling);
        });
    } else if (request.method == "arrange") {
        job_id = McpJobRegistry::instance().create("arrange");
        m_marshaler->post([this, job_id]() { ui_arrange(job_id); });
    } else if (request.method == "undo") {
        // Protocol-only diagnostic (no MCP tool): the same undo the Edit
        // menu triggers, so an agent - and the E2E suite - can revert its
        // own last write through Orca's real undo path.
        job_id = McpJobRegistry::instance().create("undo");
        m_marshaler->post([this, job_id]() { ui_undo(job_id); });
    } else if (request.method == "send_to_print") {
        job_id = McpJobRegistry::instance().create("send_to_print");
        m_marshaler->post([this, job_id]() { ui_send_to_print(job_id); });
    } else if (request.method == "run_calibration") {
        const std::string mode = request.params.value("mode", std::string());
        if (mode != "flow" && mode != "pa") {
            return build_error(RpcErrorCode::InvalidParams,
                               "mode must be \"flow\" or \"pa\"",
                               request.has_id, request.id);
        }
        job_id = McpJobRegistry::instance().create("run_calibration");
        m_marshaler->post([this, job_id, mode]() {
            ui_run_calibration(job_id, mode);
        });
    } else {
        return build_error(RpcErrorCode::MethodNotFound,
                           "unknown method: " + request.method, request.has_id, request.id);
    }

    McpJobSnapshot snapshot;
    McpJobRegistry::instance().get(job_id, snapshot);
    nlohmann::json result = nlohmann::json::object();
    result["job_id"]      = job_id;
    result["kind"]        = snapshot.kind;
    result["state"]       = job_state_name(snapshot.state);
    return build_result(result, request.has_id, request.id);
}

void McpServer::ui_slice(int job_id, int plate)
{
    // UI thread. Uses the exact same entry point as the slice button.
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
        if (m_slice_job_in_flight == job_id) {
            m_slice_job_in_flight = 0;
        }
        return;
    }
    // Mirror the UI's own gate (MainFrame slice button): never leave the
    // job hanging when the plate is not sliceable - reslice() would return
    // silently and no completion event would ever fire.
    GUI::PartPlateList& plates = plater->get_partplate_list();
    const int curr = plates.get_curr_plate_index();
    if (!plater->is_plate_sliceable(curr)) {
        McpJobRegistry::instance().set_failed(
            job_id, "plate is not sliceable (no objects, invalid settings, "
                    "or blocked filaments) - check the Orca UI");
        std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
        if (m_slice_job_in_flight == job_id) {
            m_slice_job_in_flight = 0;
        }
        return;
    }
    McpJobRegistry::instance().set_running(job_id, 0, "reslice requested");
    // Exact MainFrame slice-button sequence (MainFrame::start_slice): gizmo
    // exit, config update, then the toolbar slice event. Calling
    // Plater::reslice() directly skips the update step and the background
    // process never starts.
    plater->exit_gizmo();
    plater->update(true, true);
    GUI::FlowType::sync_filament_volume_types_for_slice();
    if (plate == 0) {
        wxPostEvent(plater, SimpleEvent(GUI::EVT_GLTOOLBAR_SLICE_ALL));
    } else {
        wxPostEvent(plater, SimpleEvent(GUI::EVT_GLTOOLBAR_SLICE_PLATE));
    }
    // Progress arrives via EVT_SLICING_UPDATE; completion via
    // EVT_PROCESS_COMPLETED (bound in ui_install_plater_hooks). Two
    // watchdogs: the start watchdog fires when slicing never produced any
    // progress at all (the slice event was silently swallowed); the main
    // watchdog only guards against a stalled finalize.
    m_slice_watchdog_timer = std::make_unique<wxTimer>();
    m_slice_watchdog_timer->SetOwner(m_marshaler.get(), kSliceWatchdogId);
    m_slice_start_watchdog_timer = std::make_unique<wxTimer>();
    m_slice_start_watchdog_timer->SetOwner(m_marshaler.get(),
                                           kSliceStartWatchdogId);
    m_marshaler->Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
        {
            std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
            if (m_slice_job_in_flight == 0) {
                return;
            }
            McpJobSnapshot snapshot;
            if (McpJobRegistry::instance().get(m_slice_job_in_flight, snapshot)
                && (snapshot.state == JobState::Running
                    || snapshot.state == JobState::Pending)) {
                std::string message =
                    "slicing never started - the plate likely has a "
                    "validation error (Orca's reslice() no-ops in that "
                    "state); check the Orca UI";
                // UI thread and the background process is idle here, so the
                // live validation result is safe to query and is the most
                // actionable detail we can attach.
                GUI::Plater* plater = plater_or_null();
                if (plater != nullptr) {
                    Print& print =
                        plater->get_partplate_list().get_current_fff_print();
                    StringObjectException error = print.validate();
                    if (!error.string.empty()) {
                        message += " - validation: " + error.string;
                    }
                }
                McpJobRegistry::instance().set_failed(m_slice_job_in_flight,
                                                      message);
                m_slice_job_in_flight = 0;
            }
        }
        if (m_slice_watchdog_timer != nullptr) {
            m_slice_watchdog_timer->Stop();
        }
    }, kSliceStartWatchdogId);
    m_marshaler->Bind(wxEVT_TIMER, [this](wxTimerEvent&) {
        {
            std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
            if (m_slice_job_in_flight == 0) {
                return;
            }
            McpJobSnapshot snapshot;
            if (McpJobRegistry::instance().get(m_slice_job_in_flight, snapshot)
                && (snapshot.state == JobState::Running
                    || snapshot.state == JobState::Pending)) {
                McpJobRegistry::instance().set_failed(
                    m_slice_job_in_flight,
                    "slicing did not complete within the watchdog window - "
                    "check the Orca UI (it may still be finalizing)");
                m_slice_job_in_flight = 0;
            }
        }
        if (m_slice_start_watchdog_timer != nullptr) {
            m_slice_start_watchdog_timer->Stop();
        }
    }, kSliceWatchdogId);
    m_slice_watchdog_timer->StartOnce(kSliceWatchdogMs);
    m_slice_start_watchdog_timer->StartOnce(kSliceStartWatchdogMs);
    m_slice_progress_seen = false;
    m_slice_watch_start = std::chrono::steady_clock::now();
}

void McpServer::ui_load_models(int job_id, const std::vector<std::string>& paths)
{
    // UI thread. Same entry point as dropping files onto the plater.
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    std::vector<boost::filesystem::path> file_paths;
    for (const std::string& path : paths) {
        if (!boost::filesystem::exists(path)) {
            McpJobRegistry::instance().set_failed(job_id,
                                                  "model file not found: " + path);
            return;
        }
        file_paths.emplace_back(path);
    }
    McpJobRegistry::instance().set_running(job_id, 10, "loading models");
    const std::vector<size_t> loaded = plater->load_files(file_paths);
    if (loaded.empty()) {
        McpJobRegistry::instance().set_failed(job_id, "no objects were loaded");
        return;
    }
    McpJobRegistry::instance().set_result(
        job_id, nlohmann::json{{"objects_loaded", loaded.size()}});
    m_marshaler->post([this]() { rebuild_snapshot(); });
}

void McpServer::ui_export_gcode(int job_id, const std::string& path)
{
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    {
        std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
        m_export_job_in_flight = job_id;
    }
    McpJobRegistry::instance().set_running(job_id, 50, "copying sliced gcode");
    ui_export_gcode_step(job_id, path, 0);
}

void McpServer::ui_export_gcode_step(int job_id, const std::string& path, int attempt)
{
    // Runs on the UI thread. Right after the Finished event the background
    // thread may still wind down (running() stays true briefly); requeue
    // ourselves instead of failing while it settles.
    constexpr int kMaxAttempts = 60;
    std::string reason;
    if (plater_or_null() == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    const int export_result = plater_or_null()->mcp_export_gcode_to(path, &reason);
    if (export_result == 2) {
        // Scheduled: EVT_PROCESS_COMPLETED (bound on the plater) finishes
        // this job; nothing else to do here.
        return;
    }
    if (export_result == 1) {
        std::int64_t bytes = 0;
        boost::system::error_code ignored_ec;
        const boost::filesystem::path out_path(path);
        if (boost::filesystem::exists(out_path, ignored_ec)) {
            bytes = static_cast<std::int64_t>(boost::filesystem::file_size(out_path));
        }
        {
            std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
            if (m_export_job_in_flight == job_id) {
                m_export_job_in_flight = 0;
            }
        }
        m_export_retry_job = 0;
        McpJobRegistry::instance().set_result(
            job_id, nlohmann::json{{"path", path}, {"bytes", bytes}});
        return;
    }
    McpJobRegistry::instance().set_failed(job_id, "export failed: " + reason);
    std::lock_guard<std::mutex> lock(m_jobs_in_flight_mutex);
    if (m_export_job_in_flight == job_id) {
        m_export_job_in_flight = 0;
    }
    m_export_retry_job = 0;
}

void McpServer::ui_export_3mf(int job_id, const std::string& path)
{
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    const boost::filesystem::path out_path(path);
    try {
        if (out_path.has_parent_path()) {
            boost::filesystem::create_directories(out_path.parent_path());
        }
    } catch (const std::exception&) {
        // export_3mf will report its own failure for unwritable targets.
    }
    const int result = plater->export_3mf(out_path, SaveStrategy::Silence, -1, nullptr);
    if (result) {
        std::int64_t bytes = 0;
        boost::system::error_code ignored_ec;
        if (boost::filesystem::exists(out_path, ignored_ec)) {
            bytes = static_cast<std::int64_t>(boost::filesystem::file_size(out_path));
        }
        McpJobRegistry::instance().set_result(
            job_id, nlohmann::json{{"path", path}, {"bytes", bytes}});
    } else {
        McpJobRegistry::instance().set_failed(job_id, "export_3mf returned failure");
    }
}

void McpServer::ui_set_params(int job_id,
                              const std::map<std::string, std::string>& params)
{
    // UI thread. Writes project-level print overrides (the same overrides a
    // project 3mf carries); each key/value goes through the config
    // definition's typed deserialization, so an invalid value fails the job
    // with a message the caller can self-correct from.
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    std::vector<std::string> applied;
    Slic3r::GUI::GUI_App* app = app_or_null();
    if (app == nullptr || app->preset_bundle == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "preset bundle not ready");
        return;
    }
    DynamicPrintConfig& project_config = app->preset_bundle->project_config;
    for (const auto& entry : params) {
        const ConfigOptionDef* def = print_config_def.get(entry.first);
        if (def == nullptr) {
            McpJobRegistry::instance().set_failed(
                job_id, "unknown print parameter: " + entry.first
                    + " (see list_params)");
            return;
        }
        ConfigSubstitutionContext substitutions(ForwardCompatibilitySubstitutionRule::Enable);
        try {
            project_config.set_deserialize(entry.first, entry.second,
                                           substitutions);
        } catch (const std::exception& ex) {
            McpJobRegistry::instance().set_failed(
                job_id, "parameter '" + entry.first + "' rejected: " + ex.what());
            return;
        }
        applied.push_back(entry.first);
    }
    plater->take_snapshot("MCP: set parameters");
    // Mark the scene dirty: without this the slice-time forced update is
    // skipped (nothing "needs update"), the background process sees an
    // already-applied UNCHANGED print and, being finished, silently
    // refuses to restart (journal M3).
    // Tab-identical refresh (no force-restart): a force flag would run
    // validation and, on a rejected combination, set the error state
    // that makes reslice() silently no-op (journal M3).
    plater->update(false, false);
    plater->set_need_update(true);
    m_marshaler->post([this]() { rebuild_snapshot(); });
    McpJobRegistry::instance().set_result(
        job_id, nlohmann::json{{"applied", applied},
                               {"note", "project-level overrides; re-slice to apply"}});
}

void McpServer::ui_set_object_params(int job_id, std::int64_t object_id,
                                     const std::map<std::string, std::string>& params)
{
    // UI thread. Writes per-object overrides the same way the object tabs
    // do (ModelObject::config, PrintObjectConfig + PrintRegionConfig scopes)
    // and refreshes the object list through the tab-change handler so the
    // settings badge stays consistent with the model.
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    GUI::GUI_App* app = app_or_null();
    if (app == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "app not ready");
        return;
    }
    ModelObject* target = nullptr;
    for (ModelObject* object : plater->model().objects) {
        if (object != nullptr
            && static_cast<std::int64_t>(object->id().id) == object_id) {
            target = object;
            break;
        }
    }
    if (target == nullptr) {
        McpJobRegistry::instance().set_failed(job_id,
                                              "unknown object_id: "
                                                  + std::to_string(object_id));
        return;
    }
    for (const auto& entry : params) {
        if (!Mcp::McpParams::is_valid_object_param(entry.first)) {
            McpJobRegistry::instance().set_failed(
                job_id,
                "'" + entry.first
                    + "' is not a per-object parameter (object scope = "
                      "object + region options; project scope via "
                      "set_params)");
            return;
        }
    }
    // Stage on a scratch config first so a bad value never leaves a
    // half-applied override behind.
    Slic3r::DynamicPrintConfig staged;
    const std::string error = Mcp::McpParams::deserialize_all(staged, params);
    if (!error.empty()) {
        McpJobRegistry::instance().set_failed(job_id, error);
        return;
    }
    plater->take_snapshot("MCP: set object parameters");
    // Mark the scene dirty: without this the slice-time forced update is
    // skipped (nothing "needs update"), the background process sees an
    // already-applied UNCHANGED print and, being finished, silently
    // refuses to restart (journal M3).
    target->config.apply_only(staged, staged.keys());
    GUI::ObjectList* object_list = app->obj_list();
    if (object_list != nullptr) {
        // Same refresh as TabPrintObject::notify_changed.
        object_list->object_config_options_changed({target, nullptr});
    }
    // Tab-identical refresh (no force-restart): a force flag would run
    // validation and, on a rejected combination, set the error state
    // that makes reslice() silently no-op (journal M3).
    plater->update(false, false);
    plater->set_need_update(true);
    m_marshaler->post([this]() { rebuild_snapshot(); });
    std::vector<std::string> applied;
    applied.reserve(params.size());
    for (const auto& entry : params) {
        applied.push_back(entry.first);
    }
    McpJobRegistry::instance().set_result(
        job_id, nlohmann::json{{"object_id", object_id},
                               {"applied", applied},
                               {"note", "per-object override; re-slice to apply"}});
}

void McpServer::ui_set_plate_params(int job_id, int plate_index,
                                    const std::map<std::string, std::string>& params)
{
    // UI thread. Writes per-plate overrides through the same semantic
    // setters the plate settings dialog uses (no dialogs involved); the
    // background process merges plate config on every slicing apply.
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    GUI::PartPlateList& plates = plater->get_partplate_list();
    GUI::PartPlate* plate = plate_index > 0 ? plates.get_plate(plate_index - 1)
                                            : plates.get_curr_plate();
    if (plate == nullptr) {
        McpJobRegistry::instance().set_failed(
            job_id, "unknown plate: " + std::to_string(plate_index));
        return;
    }
    for (const auto& entry : params) {
        if (!Mcp::McpParams::is_valid_plate_param(entry.first)) {
            McpJobRegistry::instance().set_failed(
                job_id,
                "'" + entry.first
                    + "' is not a per-plate parameter (supported: "
                      "curr_bed_type, print_sequence)");
            return;
        }
    }
    Slic3r::DynamicPrintConfig staged;
    const std::string error = Mcp::McpParams::deserialize_all(staged, params);
    if (!error.empty()) {
        McpJobRegistry::instance().set_failed(job_id, error);
        return;
    }
    plater->take_snapshot("MCP: set plate parameters");
    // Mark the scene dirty: without this the slice-time forced update is
    // skipped (nothing "needs update"), the background process sees an
    // already-applied UNCHANGED print and, being finished, silently
    // refuses to restart (journal M3).
    if (staged.has("curr_bed_type")) {
        plate->set_bed_type(staged.opt_enum<BedType>("curr_bed_type"));
    }
    if (staged.has("print_sequence")) {
        plate->set_print_seq(
            staged.opt_enum<PrintSequence>("print_sequence"));
    }
    // Tab-identical refresh (no force-restart): a force flag would run
    // validation and, on a rejected combination, set the error state
    // that makes reslice() silently no-op (journal M3).
    plater->update(false, false);
    plater->set_need_update(true);
    m_marshaler->post([this]() { rebuild_snapshot(); });
    std::vector<std::string> applied;
    applied.reserve(params.size());
    for (const auto& entry : params) {
        applied.push_back(entry.first);
    }
    McpJobRegistry::instance().set_result(
        job_id, nlohmann::json{{"plate", plate_index > 0 ? plate_index
                                                         : plates.get_curr_plate_index() + 1},
                               {"applied", applied},
                               {"note", "per-plate override; re-slice to apply"}});
}

void McpServer::ui_remove_object(int job_id, std::int64_t object_id)
{
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    Model& model = plater->model();
    for (size_t index = 0; index < model.objects.size(); ++index) {
        const ModelObject* object = model.objects[index];
        if (object != nullptr
            && static_cast<std::int64_t>(object->id().id) == object_id) {
            plater->take_snapshot("MCP: remove object");
            plater->remove(index);
            m_marshaler->post([this]() { rebuild_snapshot(); });
            McpJobRegistry::instance().set_result(
                job_id, nlohmann::json{{"removed_object_id", object_id}});
            return;
        }
    }
    McpJobRegistry::instance().set_failed(job_id,
                                          "unknown object_id: "
                                              + std::to_string(object_id));
}

void McpServer::ui_set_transform(int job_id, std::int64_t object_id,
                                 const nlohmann::json& translation,
                                 const nlohmann::json& rotation,
                                 const nlohmann::json& scaling_factor)
{
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    ModelObject* target = nullptr;
    for (ModelObject* object : plater->model().objects) {
        if (object != nullptr
            && static_cast<std::int64_t>(object->id().id) == object_id) {
            target = object;
            break;
        }
    }
    if (target == nullptr || target->instances.empty()) {
        McpJobRegistry::instance().set_failed(job_id,
                                              "unknown object_id: "
                                                  + std::to_string(object_id));
        return;
    }
    ModelInstance* instance = target->instances.front();
    auto axis_vec = [](const nlohmann::json& value,
                       Vec3d& out) -> bool {
        if (!value.is_object() || value.empty()) {
            return false;
        }
        if (value.contains("x")) out.x() = value.value("x", out.x());
        if (value.contains("y")) out.y() = value.value("y", out.y());
        if (value.contains("z")) out.z() = value.value("z", out.z());
        if (value.contains("0")) out.x() = value.value("0", out.x());
        if (value.contains("1")) out.y() = value.value("1", out.y());
        if (value.contains("2")) out.z() = value.value("2", out.z());
        return true;
    };
    plater->take_snapshot("MCP: set transform");
    // Mark the scene dirty: without this the slice-time forced update is
    // skipped (nothing "needs update"), the background process sees an
    // already-applied UNCHANGED print and, being finished, silently
    // refuses to restart (journal M3).
    Vec3d vec = instance->get_offset();
    if (axis_vec(translation, vec)) {
        instance->set_offset(vec);
    }
    vec = instance->get_rotation();
    if (axis_vec(rotation, vec)) {
        instance->set_rotation(vec);
    }
    vec = instance->get_scaling_factor();
    if (axis_vec(scaling_factor, vec)) {
        instance->set_scaling_factor(vec);
    }
    target->invalidate_bounding_box();
    plater->update(false, false);
    plater->set_need_update(true);
    m_marshaler->post([this]() { rebuild_snapshot(); });
    McpJobRegistry::instance().set_result(
        job_id, nlohmann::json{{"object_id", object_id},
                               {"translation", instance->get_offset()},
                               {"rotation", instance->get_rotation()},
                               {"scaling_factor", instance->get_scaling_factor()}});
}

void McpServer::ui_arrange(int job_id)
{
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    plater->take_snapshot("MCP: arrange");
    plater->arrange();
    m_marshaler->post([this]() { rebuild_snapshot(); });
    McpJobRegistry::instance().set_result(
        job_id, nlohmann::json{{"outcome", "arranged"}});
}

void McpServer::ui_undo(int job_id)
{
    // UI thread. Plater::undo() is the exact handler behind the Edit menu's
    // Undo entry. The menu gates the command on the 3D view being shown
    // (can_undo() also tests is_view3D_shown); switch to the 3D view like a
    // user would so undo works from any page (e.g. after a slice switched
    // to Preview).
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    plater->select_view_3D("3D");
    plater->undo();
    m_marshaler->post([this]() { rebuild_snapshot(); });
    McpJobRegistry::instance().set_result(
        job_id, nlohmann::json{{"outcome", "undone"}});
}

void McpServer::ui_send_to_print(int job_id)
{
    // UI thread. Opens the same modal send dialog the UI button uses: the
    // human confirmation IS the safety gate, so this tool never sends by
    // itself. The job completes when the dialog is up (the modal blocks
    // this worker until the user closes it, which is fine - the outcome
    // was recorded first and writes are refused while the dialog owns the
    // UI anyway).
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    if (plater->model().objects.empty()) {
        McpJobRegistry::instance().set_failed(job_id,
                                              "scene has no objects to print");
        return;
    }
    McpJobRegistry::instance().set_result(
        job_id, nlohmann::json{
                    {"outcome", "awaiting_user_confirmation"},
                    {"note", "the send dialog is open in the Orca UI - a "
                             "human must confirm or cancel the print"}});
    plater->send_to_printer(false);
}

void McpServer::ui_run_calibration(int job_id, const std::string& mode)
{
    // UI thread. Machine-backed calibration dispatch needs real-hardware
    // validation (journal M4); without a device the honest answer is a
    // structured failure, never a fabricated success.
    DeviceManager* device_manager =
        app_or_null() != nullptr ? app_or_null()->getDeviceManager() : nullptr;
    MachineObject* machine =
        device_manager != nullptr ? device_manager->get_selected_machine()
                                  : nullptr;
    if (machine == nullptr) {
        McpJobRegistry::instance().set_failed(
            job_id, "no connected printer - calibration requires a device");
        return;
    }
    McpJobRegistry::instance().set_failed(
        job_id, "calibration ('" + mode + "') dispatch to '"
                    + machine->dev_name
                    + "' is not enabled yet: the device path needs "
                      "real-hardware validation");
}

void McpServer::ui_render_screenshot(int job_id, int plate_index, int width, int height)
{
    GUI::Plater* plater = plater_or_null();
    if (plater == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "plater not ready");
        return;
    }
    GUI::GLCanvas3D* canvas = plater->get_view3D_canvas3D();
    if (canvas == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "3D view not available");
        return;
    }
    ThumbnailData     data;
    ThumbnailsParams  params{Vec2ds(1, Vec2d(width, height)), false, false, true,
                            false, plate_index - 1};
    canvas->render_thumbnail(data, width, height, params, GUI::Camera::EType::Perspective);
    if (!data.is_valid() || data.pixels.empty()) {
        McpJobRegistry::instance().set_failed(job_id, "thumbnail render failed");
        return;
    }
    std::size_t png_size   = 0;
    void*       png_buffer = tdefl_write_image_to_png_file_in_memory_ex(
        data.pixels.data(), data.width, data.height, 4, &png_size, MZ_DEFAULT_LEVEL, 1);
    if (png_buffer == nullptr) {
        McpJobRegistry::instance().set_failed(job_id, "png encode failed");
        return;
    }
    const std::string encoded_str = wxBase64Encode(png_buffer, png_size).ToStdString();
    mz_free(png_buffer);
    McpJobRegistry::instance().set_result(
        job_id,
        nlohmann::json{{"format", "png"},
                       {"width", data.width},
                       {"height", data.height},
                       {"image_base64", encoded_str}});
}

} // namespace Mcp
} // namespace Slic3r
