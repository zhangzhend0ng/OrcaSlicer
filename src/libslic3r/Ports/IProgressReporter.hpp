#ifndef libslic3r_Ports_IProgressReporter_hpp_
#define libslic3r_Ports_IProgressReporter_hpp_

#include <string_view>
#include <functional>

namespace Slic3r {

/// Interface for progress reporting and cancellation during long operations.
/// Defined in libslic3r (Layer 2), implemented by Application (Layer 3).
/// Replaces: wxPostEvent from Print/PrintObject to GUI for progress updates.
class IProgressReporter {
public:
    using ProgressFn = std::function<void(int percent, std::string_view stage)>;
    using CancelFn    = std::function<bool()>;

    virtual ~IProgressReporter() = default;

    /// Report progress (0-100). Called from worker threads.
    /// Implementations must dispatch to main thread as needed.
    virtual void report_progress(int percent, std::string_view stage) = 0;

    /// Check if the operation has been cancelled.
    virtual bool was_cancelled() const = 0;
};

} // namespace Slic3r

#endif /* libslic3r_Ports_IProgressReporter_hpp_ */
