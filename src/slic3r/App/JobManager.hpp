#ifndef slic3r_App_JobManager_hpp_
#define slic3r_App_JobManager_hpp_

#include "libslic3r/MVVP.hpp"

#include <functional>
#include <string>
#include <vector>
#include <memory>
#include <queue>
#include <mutex>
#include <condition_variable>
#include <thread>
#include <atomic>

namespace Slic3r {

/// Priority for background jobs.
enum class JobPriority {
    Low       = 0,
    Normal    = 1,
    High      = 2,
    Critical  = 3,
};

/// A single background job.
struct Job {
    std::string  name;
    JobPriority  priority{JobPriority::Normal};
    std::function<void()> work;       // runs on background thread
    std::function<void()> onComplete; // runs on main thread

    bool operator<(const Job& other) const {
        return static_cast<int>(priority) < static_cast<int>(other.priority);
    }
};

/// Centralized background job scheduler.
/// Replaces scattered boost::thread / std::thread creation across the codebase.
/// Jobs are queued by priority and executed on a worker thread pool.
///
/// Lives in Application layer (Layer 3).
/// All onComplete callbacks should be dispatched to the main thread by the caller.
class JobManager {
public:
    explicit JobManager(int workerThreads = 2);
    ~JobManager();

    // Non-copyable
    JobManager(const JobManager&) = delete;
    JobManager& operator=(const JobManager&) = delete;

    // ?? Job Queue ??
    /// Enqueue a job for background execution.
    void enqueue(Job job);

    /// Cancel all pending jobs (running jobs complete).
    void cancelAll();

    // ?? Observables ??
    MVVP::Property<int>         pendingJobs_{0};
    MVVP::Property<int>         activeJobs_{0};
    MVVP::Property<std::string> currentJobName_{""};
    MVVP::Property<bool>        isIdle_{true};

    /// Wait for all jobs to complete (for testing/shutdown).
    void waitForAll();

private:
    void workerLoop();

    struct JobCompare {
        bool operator()(const Job& a, const Job& b) const {
            return a.priority < b.priority; // higher priority first
        }
    };

    std::priority_queue<Job, std::vector<Job>, JobCompare> queue_;
    std::mutex               queueMutex_;
    std::condition_variable  queueCV_;
    std::atomic<bool>        running_{true};
    std::atomic<int>         activeCount_{0};
    std::vector<std::thread> workers_;
};

} // namespace Slic3r

#endif /* slic3r_App_JobManager_hpp_ */
