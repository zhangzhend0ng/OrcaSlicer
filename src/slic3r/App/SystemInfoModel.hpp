#ifndef slic3r_App_SystemInfoModel_hpp_
#define slic3r_App_SystemInfoModel_hpp_

#include "libslic3r/MVVP.hpp"
#include <string>
#include <map>

namespace Slic3r {

/// Pure-C++ system information parsing utilities.
/// Extracted from SendSystemInfoDialog.cpp.
/// Zero wxWidgets dependency. Platform-specific parts (registry) not included.
class SystemInfoModel {
public:
    /// Parse key=value-style config file content.
    static std::map<std::string, std::string> parseKeyValueConfig(
        const std::string& content, char delimiter = '=');

    /// Generate a unique machine identifier.
    static std::string generateUniqueId();

    /// Generate JSON string from key-value system info map.
    static std::string systemInfoToJson(
        const std::map<std::string, std::string>& info);

    // ?? Observable State ??
    MVVP::Property<std::map<std::string, std::string>> sysInfo{{}};
    MVVP::Property<bool> infoLoaded{false};
};

} // namespace Slic3r

#endif /* slic3r_App_SystemInfoModel_hpp_ */
