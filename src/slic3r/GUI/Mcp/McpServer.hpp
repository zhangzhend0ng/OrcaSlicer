#pragma once
/**
 * @brief Facade for the in-process MCP listener: lifecycle, token and
 *        discovery-file management, snapshot cache, job marshaling to the
 *        UI thread.
 *
 * - The listener speaks the private POST JSON-RPC protocol on 127.0.0.1
 *   port 13620 (never on the 13618/13619 servers).
 * - HTTP threads never block on the UI thread: reads are served from a
 *   snapshot cache; writes create jobs, post work to the UI thread via
 *   CallAfter, and answer immediately with a job id.
 * - The interface is off by default; enabling persists to app_config and
 *   generates a random token. A discovery file in the data dir lets the
 *   external bridge find port and token without hardcoding.
 */

#include <atomic>
#include <chrono>
#include <memory>
#include <mutex>
#include <map>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>
#include <wx/event.h>
#include <wx/timer.h>

class wxWindow;

namespace Slic3r {
namespace Mcp {

class HttpListener;

/// Fixed service port. Binding is failure-fatal by decision (no +1000 drift).
constexpr unsigned short McpServicePort = 13620;

constexpr const char* ConfigKeyEnabled = "mcp_enabled";
constexpr const char* ConfigKeyToken   = "mcp_token";

/// Marshals UI-thread work from listener threads; lives on the UI thread.
class UiMarshaler : public wxEvtHandler
{
public:
    void post(std::function<void()> fn) { CallAfter(std::move(fn)); }
};

class McpServer
{
public:
    /// Process-wide instance (GUI_App owns the first reference implicitly).
    static McpServer& instance();

    /// Apply persisted preference: start the listener if enabled in
    /// app_config. Called from GUI_App::on_init (UI thread).
    void startup_from_config();

    /// Stop everything; called from GUI_App::shutdown (UI thread).
    void shutdown();

    /// Enable from the preferences dialog: generates a token when missing,
    /// persists config, starts listener, writes discovery file.
    /// Returns false when the port is unavailable (state stays disabled).
    bool enable();

    /// Disable from the preferences dialog: stops listener, removes the
    /// discovery file, persists the preference.
    void disable();

    bool is_enabled() const;
    bool is_running() const;
    std::string token() const;

    /// Rebuild the state snapshot NOW on the UI thread.
    void rebuild_snapshot();

    /// Snapshot accessor for HTTP threads; returns a copy under the mutex.
    nlohmann::json snapshot_copy() const;

    /// Test seam: forget snapshot state.
    void clear_snapshot_for_tests();

private:
    McpServer();

    /// Runs on listener threads: pure dispatcher, no wx calls.
    std::string dispatch(const std::string& method, const std::string& body);

    /// UI-thread workers (run via UiMarshaler::post).
    void ui_slice(int job_id, int plate);
    void ui_load_models(int job_id, const std::vector<std::string>& paths);
    void ui_export_gcode(int job_id, const std::string& path);
    void ui_export_gcode_step(int job_id, const std::string& path, int attempt);
    void ui_export_3mf(int job_id, const std::string& path);
    void ui_render_screenshot(int job_id, int plate_index, int width, int height);
    void ui_install_plater_hooks();
    void ui_set_params(int job_id, const std::map<std::string, std::string>& params);
    void ui_set_object_params(int job_id, std::int64_t object_id,
                              const std::map<std::string, std::string>& params);
    void ui_set_plate_params(int job_id, int plate_index,
                             const std::map<std::string, std::string>& params);
    void ui_remove_object(int job_id, std::int64_t object_id);
    void ui_set_transform(int job_id, std::int64_t object_id,
                          const nlohmann::json& translation,
                          const nlohmann::json& rotation,
                          const nlohmann::json& scaling_factor);
    void ui_arrange(int job_id);
    void ui_undo(int job_id);
    void ui_send_to_print(int job_id);
    void ui_run_calibration(int job_id, const std::string& mode);
    /// True while a modal dialog owns the UI: writes must be refused.
    bool ui_busy() const { return m_modal_depth.load() > 0; }

    /// Snapshot builder; UI thread only.
    nlohmann::json build_snapshot();

    std::unique_ptr<HttpListener> m_listener;
    std::shared_ptr<UiMarshaler>  m_marshaler;
    std::unique_ptr<wxTimer>      m_snapshot_timer;
    std::unique_ptr<wxTimer>      m_slice_watchdog_timer;
    std::unique_ptr<wxTimer>      m_slice_start_watchdog_timer;
    std::unique_ptr<wxTimer>      m_export_retry_timer;
    int                           m_export_retry_job = 0;
    int                           m_export_retry_attempt = 0;
    std::string                   m_export_retry_path;
    wxWindow*                     m_hook_plater = nullptr;

    mutable std::mutex            m_snapshot_mutex;
    nlohmann::json                m_snapshot = nlohmann::json::object();

    std::mutex                    m_jobs_in_flight_mutex;
    int                           m_slice_job_in_flight  = 0;
    int                           m_export_job_in_flight = 0;
    // Start-watchdog bookkeeping; enforced both by a one-shot timer and by
    // rebuild_snapshot (the snapshot beat is the one proven to keep running
    // when slicing stalls).
    std::chrono::steady_clock::time_point m_slice_watch_start;
    std::atomic<bool>             m_slice_progress_seen{false};

    std::atomic<bool>             m_enabled{false};
    std::atomic<int>              m_modal_depth{0};
};

/// Generate a 32-char lowercase hex token (crypto/rand-backed).
std::string generate_token();

/// Discovery file: `<data_dir>/mcp_session.json` = {"port":N,"token":"..."}.
/// The bridge MUST read it - port discovery is file-based, never hardcoded
/// guesses (legacy server drifts ports, see HttpServer.cpp:491).
bool write_discovery_file(const std::string& data_dir, unsigned short port, const std::string& token);
void remove_discovery_file(const std::string& data_dir);

} // namespace Mcp
} // namespace Slic3r
