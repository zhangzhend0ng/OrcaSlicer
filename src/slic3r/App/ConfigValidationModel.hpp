#ifndef slic3r_App_ConfigValidationModel_hpp_
#define slic3r_App_ConfigValidationModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>

namespace Slic3r {

class DynamicPrintConfig;

/// Pure-C++ config validation and resolution logic.
/// Extracted from Tab.cpp (static functions: bed_type_to_rule_key,
/// nozzle_diameter_to_rule_key, intersect/concat/substruct,
/// resolved_model_config_for_tab).
///
/// Zero wxWidgets dependency. All results via Property<T>.
class ConfigValidationModel {
public:
    // ?? Static pure helpers (no state needed) ??

    /// Convert bed type enum to rule key string for compatibility lookup.
    static std::string bedTypeToRuleKey(int bedType);

    /// Convert nozzle diameter to rule key string (e.g., 0.4 -> "0.4mm").
    static std::string nozzleDiameterToRuleKey(double diameter);

    /// Set operations on string vectors.
    static std::vector<std::string> intersect(
        const std::vector<std::string>& a,
        const std::vector<std::string>& b);

    static std::vector<std::string> unionSets(
        const std::vector<std::string>& a,
        const std::vector<std::string>& b);

    static std::vector<std::string> subtract(
        const std::vector<std::string>& a,
        const std::vector<std::string>& b);

    /// Resolve filament assignments for multi-extruder configuration.
    /// If extruder is set but individual filament slots are not,
    /// fills them with the active extruder value.
    static DynamicPrintConfig resolveModelConfig(const DynamicPrintConfig& config);

    // ?? Observable State (for GUI binding) ??

    /// Current set of validation warnings.
    struct Warning {
        std::string key;
        std::string message;
        enum Severity { Info, Warn, Error } severity{Warn};
    };

    MVVP::Property<std::vector<Warning>> warnings{{}};
    MVVP::Property<bool>                 hasWarnings{false};

    /// Check if a settings category should be hidden based on context.
    /// From GUI_Factories.cpp L84.
    static bool isImproperCategory(const std::string& category,
                                   int filamentCount,
                                   bool isObjectSettings = true);
};

} // namespace Slic3r

#endif /* slic3r_App_ConfigValidationModel_hpp_ */
