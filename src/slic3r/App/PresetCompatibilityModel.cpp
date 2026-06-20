#include "slic3r/App/PresetCompatibilityModel.hpp"
#include "libslic3r/Preset.hpp"
#include "libslic3r/PrintConfig.hpp"

namespace Slic3r {

std::vector<std::string> PresetCompatibilityModel::getCompatiblePrinters(
    const Preset* filamentPreset)
{
    // Original from CreatePresetsDialog.cpp L273
    std::vector<std::string> printers;
    if (filamentPreset == nullptr) return printers;

    const auto* compatible = filamentPreset->config.option<ConfigOptionStrings>("compatible_printers");
    if (compatible != nullptr) {
        for (const std::string& printerName : compatible->values) {
            printers.push_back(printerName);
        }
    }
    return printers;
}

PresetCompatibilityModel::CompatibilityResult
PresetCompatibilityModel::checkFilamentPrinterCompatibility(
    const Preset* filamentPreset,
    const Preset* printerPreset)
{
    CompatibilityResult result;
    if (filamentPreset == nullptr || printerPreset == nullptr) {
        result.isCompatible = false;
        return result;
    }

    // Get filament type
    if (const auto* ft = filamentPreset->config.option<ConfigOptionStrings>("filament_type");
        ft != nullptr && !ft->values.empty()) {
        result.filamentType = ft->values.front();
    }

    // Get printer model info
    if (const auto* pm = printerPreset->config.option<ConfigOptionString>("printer_model");
        pm != nullptr) {
        result.printerModel = pm->value;
    }

    // Get nozzle diameter
    if (const auto* nd = printerPreset->config.option<ConfigOptionFloats>("nozzle_diameter");
        nd != nullptr && !nd->values.empty()) {
        result.nozzleDiameter = nd->values.front();
    }

    // Basic compatibility check: filament type must not be empty
    result.isCompatible = !result.filamentType.empty();

    return result;
}

} // namespace Slic3r
