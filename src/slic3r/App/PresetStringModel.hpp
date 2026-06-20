#ifndef slic3r_App_PresetStringModel_hpp_
#define slic3r_App_PresetStringModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>
#include <set>
#include <map>

namespace Slic3r {

/// Pure-C++ preset name parsing and string utilities.
/// Extracted from CreatePresetsDialog.cpp, UnsavedChangesDialog.cpp, IMSlider.cpp.
/// Zero wxWidgets dependency. All functions are static.
class PresetStringModel {
public:
    static std::string removeSpecialKeys(const std::string& str);
    static bool isAllDigits(const std::string& str);
    static bool caseInsensitiveCompare(const std::string& a, const std::string& b);
    static std::string currentTime(const char* format = "%Y_%m_%d_%H_%M_%S");
    static std::string currentTimestamp();
    static std::string extractMachineName(const std::string& presetName);
    static std::string extractFilamentName(std::string& presetName);
    static std::string extractVendorName(std::string& presetName);
    static std::string md5Hash(const std::string& input);
    static std::string filamentId(const std::string& vendorTypeSerial);
    static std::string extractNozzleDiameter(const std::string& printerName);
    static std::string pureOptionKey(std::string optKey);
    static size_t idFromOptionKey(std::string optKey);
    static std::string presetIconName(int presetType, int printerTechnology);
    static std::set<std::string> findNewPresets(
        const std::map<std::string, std::string>& oldData,
        const std::map<std::string, std::string>& newData);
    static std::string firstNewPreset(
        const std::map<std::string, std::string>& oldData,
        const std::map<std::string, std::string>& newData);
};

} // namespace Slic3r

#endif /* slic3r_App_PresetStringModel_hpp_ */
