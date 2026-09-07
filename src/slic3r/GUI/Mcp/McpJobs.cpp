#include "McpJobs.hpp"

#include <algorithm>
#include <chrono>

namespace Slic3r {
namespace Mcp {

namespace {

std::int64_t unix_now()
{
    return std::chrono::duration_cast<std::chrono::seconds>(
               std::chrono::system_clock::now().time_since_epoch())
        .count();
}

} // namespace

const char* job_state_name(JobState state)
{
    switch (state) {
    case JobState::Pending: return "pending";
    case JobState::Running: return "running";
    case JobState::Done:    return "done";
    case JobState::Failed:  return "failed";
    }
    return "unknown";
}

McpJobRegistry& McpJobRegistry::instance()
{
    static McpJobRegistry registry;
    return registry;
}

int McpJobRegistry::create(const std::string& kind)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    Job                         job;
    job.snapshot.id         = m_next_id++;
    job.snapshot.kind       = kind;
    job.snapshot.state      = JobState::Pending;
    job.snapshot.updated_at = unix_now();
    const int id            = job.snapshot.id;
    m_jobs.emplace_back(std::move(job));
    return id;
}

void McpJobRegistry::set_running(int id, int percent, const std::string& message)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    auto                        it = std::find_if(m_jobs.begin(), m_jobs.end(),
                                  [id](const Job& job) { return job.snapshot.id == id; });
    if (it == m_jobs.end()) {
        return;
    }
    if (it->snapshot.state == JobState::Done || it->snapshot.state == JobState::Failed) {
        // Never resurrect a terminal job from a late progress event.
        return;
    }
    it->snapshot.state      = JobState::Running;
    it->snapshot.percent    = percent;
    if (!message.empty()) {
        it->snapshot.message = message;
    }
    it->snapshot.updated_at = unix_now();
}

void McpJobRegistry::set_result(int id, const nlohmann::json& result)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    auto                        it = std::find_if(m_jobs.begin(), m_jobs.end(),
                                  [id](const Job& job) { return job.snapshot.id == id; });
    if (it == m_jobs.end()) {
        return;
    }
    it->snapshot.state      = JobState::Done;
    it->snapshot.percent    = 100;
    it->snapshot.result     = result;
    it->snapshot.updated_at = unix_now();
    it->finished_at         = unix_now();
}

void McpJobRegistry::set_failed(int id, const std::string& message)
{
    std::lock_guard<std::mutex> lock(m_mutex);
    auto                        it = std::find_if(m_jobs.begin(), m_jobs.end(),
                                  [id](const Job& job) { return job.snapshot.id == id; });
    if (it == m_jobs.end()) {
        return;
    }
    it->snapshot.state      = JobState::Failed;
    it->snapshot.message    = message;
    it->snapshot.updated_at = unix_now();
    it->finished_at         = unix_now();
}

bool McpJobRegistry::get(int id, McpJobSnapshot& out) const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    auto                        it = std::find_if(m_jobs.begin(), m_jobs.end(),
                                  [id](const Job& job) { return job.snapshot.id == id; });
    if (it == m_jobs.end()) {
        return false;
    }
    out = it->snapshot;
    return true;
}

std::size_t McpJobRegistry::prune_finished(std::int64_t max_age_seconds)
{
    const std::int64_t        now = unix_now();
    std::lock_guard<std::mutex> lock(m_mutex);
    const std::size_t         before = m_jobs.size();
    m_jobs.erase(std::remove_if(m_jobs.begin(), m_jobs.end(),
                                [now, max_age_seconds](const Job& job) {
                                    return job.finished_at > 0
                                        && (now - job.finished_at) > max_age_seconds;
                                }),
                 m_jobs.end());
    return before - m_jobs.size();
}

void McpJobRegistry::clear_for_tests()
{
    std::lock_guard<std::mutex> lock(m_mutex);
    m_jobs.clear();
    m_next_id = 1;
}

} // namespace Mcp
} // namespace Slic3r
