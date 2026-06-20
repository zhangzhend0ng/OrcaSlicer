#ifndef slic3r_App_NullProgressReporter_hpp_
#define slic3r_App_NullProgressReporter_hpp_

#include "libslic3r/Ports/IProgressReporter.hpp"
#include <atomic>

namespace Slic3r {

/// Minimal implementation of IProgressReporter for headless/CLI use.
/// Progress is silently consumed; cancellation is never requested.
class NullProgressReporter : public IProgressReporter {
public:
    void report_progress(int /*percent*/, std::string_view /*stage*/) override {}
    bool was_cancelled() const override { return cancelled_.load(std::memory_order_relaxed); }

    /// Allow external cancellation (e.g., Ctrl+C handler).
    void cancel() { cancelled_.store(true, std::memory_order_relaxed); }

private:
    std::atomic<bool> cancelled_{false};
};

} // namespace Slic3r

#endif /* slic3r_App_NullProgressReporter_hpp_ */
