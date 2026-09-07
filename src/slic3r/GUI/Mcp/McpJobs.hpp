#pragma once
/**
 * @brief Process-level job registry for long-running MCP operations.
 *
 * Jobs survive a listener restart: the registry is a process singleton, so
 * a poll for a job created before a restart still finds it, and an unknown
 * job id yields a definitive "unknown job" answer instead of hanging
 * (integration plan risk table, "server restart" entry).
 *
 * Thread safety: every public method takes the registry mutex. Payloads
 * are returned by value, never by reference.
 */

#include <nlohmann/json.hpp>
#include <mutex>
#include <string>
#include <vector>

namespace Slic3r {
namespace Mcp {

enum class JobState {
    Pending,   ///< created, UI-side work not started yet
    Running,   ///< UI-side work in progress
    Done,      ///< finished successfully; `result` carries the payload
    Failed,    ///< finished with error; `message` carries the reason
};

const char* job_state_name(JobState state);

/// Immutable snapshot of a job's observable state.
struct McpJobSnapshot
{
    int            id      = 0;
    std::string    kind;
    JobState       state   = JobState::Pending;
    int            percent = 0;
    std::string    message;
    nlohmann::json result  = nlohmann::json::object();
    /// Unix seconds when the snapshot was taken.
    std::int64_t   updated_at = 0;
};

class McpJobRegistry
{
public:
    /// Process-wide singleton (intentionally never destroyed with the
    /// listener; lives until process exit).
    static McpJobRegistry& instance();

    /// Register a new job in Pending state; returns its id (> 0).
    int create(const std::string& kind);

    /// Update progress/state. Unknown ids are ignored (job table kept
    /// alive across listener restarts may have been pruned).
    void set_running(int id, int percent, const std::string& message);
    void set_result(int id, const nlohmann::json& result);
    void set_failed(int id, const std::string& message);

    /// Copy out a job's state. Returns false for unknown ids.
    bool get(int id, McpJobSnapshot& out) const;

    /// Forget finished jobs older than `max_age_seconds`; returns pruned count.
    std::size_t prune_finished(std::int64_t max_age_seconds);

    /// Test seam: drop all jobs (never used in production paths).
    void clear_for_tests();

private:
    McpJobRegistry() = default;

    struct Job
    {
        McpJobSnapshot snapshot;
        /// Unix seconds when the job reached a terminal state (0 while running).
        std::int64_t finished_at = 0;
    };

    mutable std::mutex m_mutex;
    std::vector<Job>   m_jobs;
    int                m_next_id = 1;
};

} // namespace Mcp
} // namespace Slic3r
