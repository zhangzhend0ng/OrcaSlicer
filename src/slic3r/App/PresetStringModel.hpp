#ifndef slic3r_App_PresetStringModel_hpp_
#define slic3r_App_PresetStringModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>

namespace Slic3r {

/// Pure-C++ preset name parsing and string utilities.
/// Extracted from CreatePresetsDialog.cpp (11 static functions).
/// Zero wxWidgets dependency. All functions are static.
class PresetStringModel {
public:
    // ?? String cleaning ??

    /// Remove special characters from a string.
    static std::string removeSpecialKeys(const std::string& str);

    /// Check if string consists entirely of digit characters.
    static bool isAllDigits(const std::string& str);

    /// Case-insensitive string comparison.
    static bool caseInsensitiveCompare(const std::string& a, const std::string& b);

    // ?? Time formatting ??

    /// Get current time as formatted string (default: YYYY_MM_DD_HH_MM_SS).
    static std::string currentTime(const char* format = "%Y_%m_%d_%H_%M_%S");

    /// Get current timestamp string.
    static std::string currentTimestamp();

    // ?? Preset name parsing ??

    /// Extract machine name from preset name (e.g. "Snapmaker J1 0.4 PLA" -> "Snapmaker J1").
    static std::string extractMachineName(const std::string& presetName);

    /// Extract filament name from preset name.
    static std::string extractFilamentName(std::string& presetName);

    /// Extract vendor name from preset name.
    static std::string extractVendorName(std::string& presetName);

    // ?? Hashing ??

    /// Calculate MD5 hash of input string.
    static std::string md5Hash(const std::string& input);

    /// Generate filament identifier from vendor+type+serial.
    static std::string filamentId(const std::string& vendorTypeSerial);

    /// Extract nozzle diameter from printer preset name.
    static std::string extractNozzleDiameter(const std::string& printerName);

    // ?? From ConfigWizard.cpp (L2342, L2362) ??

    /// Find presets that were newly added between two snapshots.
    static std::set<std::string> findNewPresets(
        const std::map<std::string, std::string>& oldData,
        const std::map<std::string, std::string>& newData);

    /// Get the name of the first newly added preset.
    static std::string firstNewPreset(
        const std::map<std::string, std::string>& oldData,
        const std::map<std::string, std::string>& newData);
};

} // namespace Slic3r

#endif /* slic3r_App_PresetStringModel_hpp_ */
