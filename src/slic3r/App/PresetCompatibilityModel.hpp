#ifndef slic3r_App_PresetCompatibilityModel_hpp_
#define slic3r_App_PresetCompatibilityModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>
#include <unordered_map>

namespace Slic3r {

class Preset;
class PresetBundle;

/// Pure-C++ preset compatibility resolution.
/// Extracted from CreatePresetsDialog.cpp.
/// Zero wxWidgets dependency.
class PresetCompatibilityModel {
public:
    // ?? From CreatePresetsDialog.cpp L273 ??

    /// Get the list of compatible printers for a filament preset.
    static std::vector<std::string> getCompatiblePrinters(const Preset* filamentPreset);

    // ?? From CreatePresetsDialog.cpp L90 ??

    /// Validate that filament type is compatible with hot bed and nozzle for a printer.
    struct CompatibilityResult {
        bool    isCompatible{true};
        std::string filamentType;
        std::string printerModel;
        std::string bedType;
        double  nozzleDiameter{0.4};
    };

    static CompatibilityResult checkFilamentPrinterCompatibility(
        const Preset* filamentPreset,
        const Preset* printerPreset);

    // ?? Observable State ??

    struct IncompatibilityWarning {
        std::string filamentName;
        std::string printerName;
        std::string reason;
    };

    MVVP::Property<std::vector<IncompatibilityWarning>> warnings{{}};
};

} // namespace Slic3r

#endif /* slic3r_App_PresetCompatibilityModel_hpp_ */
