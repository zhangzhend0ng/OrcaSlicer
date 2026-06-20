#ifndef libslic3r_Ports_INotificationSink_hpp_
#define libslic3r_Ports_INotificationSink_hpp_

#include <string>
#include <string_view>

namespace Slic3r {

/// Severity level for notifications.
enum class NotificationSeverity {
    Info,
    Warning,
    Error,
};

/// Interface for warnings, errors, and status messages from core to UI.
/// Defined in libslic3r (Layer 2), implemented by Application (Layer 3).
/// Replaces: show_error() and similar calls from core to GUI.
class INotificationSink {
public:
    virtual ~INotificationSink() = default;

    /// Display a notification to the user.
    virtual void notify(NotificationSeverity severity,
                        std::string_view title,
                        std::string_view message) = 0;
};

} // namespace Slic3r

#endif /* libslic3r_Ports_INotificationSink_hpp_ */
