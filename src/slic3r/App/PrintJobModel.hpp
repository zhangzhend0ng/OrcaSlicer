#ifndef slic3r_App_PrintJobModel_hpp_
#define slic3r_App_PrintJobModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>

namespace Slic3r {

/// Pure-C++ print job state and utilities.
/// Extracted from Jobs/PrintJob.cpp and Jobs/SendJob.cpp.
/// Zero wxWidgets dependency.
class PrintJobModel {
public:
    // ?? Job state enum ??

    enum class JobState {
        Idle,
        Preparing,
        Sending,
        Printing,
        Completed,
        Failed,
        Cancelled,
    };

    static std::string jobStateToString(JobState state);

    // ?? File validation ??

    /// Validate a GCode file path (check extension, existence handled by caller).
    static bool isValidGCodePath(const std::string& path);

    /// Extract print time estimate from GCode comments.
    static std::string extractPrintTime(const std::string& gcodePath);

    // ?? Network utilities ??

    /// Parse a host:port string into components.
    static bool parseHostPort(const std::string& hostPort,
                              std::string& host, int& port);

    // ?? Observable State ??

    MVVP::Property<JobState>      jobState{JobState::Idle};
    MVVP::Property<double>        uploadProgress{0.0};
    MVVP::Property<std::string>   currentFileName{""};
    MVVP::Property<std::string>   statusMessage{""};

    // ?? Commands ??

    MVVP::Command cancelJob{
        [this] { jobState.set(JobState::Cancelled); },
        [this] {
            auto s = jobState.get();
            return s == JobState::Sending || s == JobState::Printing;
        }
    };
};

} // namespace Slic3r

#endif /* slic3r_App_PrintJobModel_hpp_ */
