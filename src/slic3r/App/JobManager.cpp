#include "slic3r/App/JobManager.hpp"

#include <chrono>

namespace Slic3r {

JobManager::JobManager(int workerThreads)
{
    for (int i = 0; i < workerThreads; ++i) {
        workers_.emplace_back(&JobManager::workerLoop, this);
    }
}

JobManager::~JobManager()
{
    running_.store(false, std::memory_order_relaxed);
    queueCV_.notify_all();
    for (auto& w : workers_) {
        if (w.joinable()) w.join();
    }
}

void JobManager::enqueue(Job job)
{
    {
        std::lock_guard<std::mutex> lock(queueMutex_);
        queue_.push(std::move(job));
    }
    pendingJobs_.set(static_cast<int>(queue_.size()));
    isIdle_.set(false);
    queueCV_.notify_one();
}

void JobManager::cancelAll()
{
    std::lock_guard<std::mutex> lock(queueMutex_);
    while (!queue_.empty()) queue_.pop();
    pendingJobs_.set(0);
}

void JobManager::waitForAll()
{
    while (activeCount_.load(std::memory_order_relaxed) > 0 ||
           pendingJobs_.get() > 0) {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
}

void JobManager::workerLoop()
{
    while (running_.load(std::memory_order_relaxed)) {
        Job job;
        {
            std::unique_lock<std::mutex> lock(queueMutex_);
            queueCV_.wait(lock, [this] {
                return !queue_.empty() || !running_.load(std::memory_order_relaxed);
            });

            if (!running_.load(std::memory_order_relaxed)) break;
            if (queue_.empty()) continue;

            job = queue_.top();
            queue_.pop();
            pendingJobs_.set(static_cast<int>(queue_.size()));
        }

        activeCount_.fetch_add(1, std::memory_order_relaxed);
        activeJobs_.set(activeCount_.load(std::memory_order_relaxed));
        currentJobName_.set(job.name);

        if (job.work) job.work();

        activeCount_.fetch_sub(1, std::memory_order_relaxed);
        activeJobs_.set(activeCount_.load(std::memory_order_relaxed));

        if (job.onComplete) job.onComplete();
    }
}

} // namespace Slic3r
