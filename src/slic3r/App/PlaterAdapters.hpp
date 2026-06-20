#ifndef slic3r_App_PlaterAdapters_hpp_
#define slic3r_App_PlaterAdapters_hpp_

// ============================================================
// Adapter layer: bridges old Plater GUI code to new ViewModels.
// 
// Usage: In Plater::priv, replace inline static function calls
// with adapter methods. Wrap with #ifdef ORCA_REFACTOR_V2.
//
// Example migration:
//   OLD: auto seq = build_grouped_manual_pattern_preview_sequence(...)
//   NEW: auto seq = adapters.mixedFilament.buildPreviewSequence(mf, n, wl)
//
// Each adapter method delegates to the corresponding ViewModel.
// The ViewModel is pure C++; the adapter provides a stable API
// that matches the old function signatures for drop-in replacement.
// ============================================================

#include "slic3r/App/MixedFilamentViewModel.hpp"
#include "slic3r/App/ConfigValidationModel.hpp"

namespace Slic3r {

/// Collection of adapters that bridge old Plater code to new ViewModels.
/// Create one instance in Plater::priv and use throughout.
class PlaterAdapters {
public:
    // ?? Mixed Filament (was 13 static functions in Plater.cpp) ??

    MixedFilamentViewModel mixedFilament;

    /// Replace: build_grouped_manual_pattern_preview_sequence()
    std::vector<unsigned int> buildMixedPreviewSequence(
        const MixedFilament& mf, size_t numPhysical, size_t wallLoops)
    {
        return MixedFilamentViewModel::buildPreviewSequence(mf, numPhysical, wallLoops);
    }

    /// Replace: blend_display_color_from_sequence()
    std::string blendMixedColor(
        const std::vector<std::string>& colors,
        const std::vector<unsigned int>& sequence)
    {
        return MixedFilamentViewModel::blendDisplayColor(colors, sequence);
    }

    /// Replace: mixed_filament_apparent_pair_summary()
    std::string makeMixedLabel(const MixedFilament& mf)
    {
        return MixedFilamentViewModel::makeLabel(mf);
    }

    /// Update the ViewModel with current state from Plater.
    /// Call this whenever physical filaments or mixed config changes.
    void syncMixedFilaments(
        const std::vector<std::string>& colors,
        const std::vector<double>& nozzles,
        const std::vector<MixedFilament>& mixed)
    {
        mixedFilament.setPhysicalFilaments(colors, nozzles);
        mixedFilament.setMixedFilaments(mixed);
    }

    // ?? Config Validation (was static functions in Tab.cpp) ??

    /// Replace: bed_type_to_rule_key()
    static std::string bedTypeKey(int bedType) {
        return ConfigValidationModel::bedTypeToRuleKey(bedType);
    }

    /// Replace: nozzle_diameter_to_rule_key()
    static std::string nozzleKey(double d) {
        return ConfigValidationModel::nozzleDiameterToRuleKey(d);
    }

    /// Replace: resolved_model_config_for_tab()
    static DynamicPrintConfig resolveConfig(const DynamicPrintConfig& cfg) {
        return ConfigValidationModel::resolveModelConfig(cfg);
    }

    /// Replace: intersect() / concat() / substruct()
    static std::vector<std::string> setIntersect(
        const std::vector<std::string>& a, const std::vector<std::string>& b) {
        return ConfigValidationModel::intersect(a, b);
    }
    static std::vector<std::string> setUnion(
        const std::vector<std::string>& a, const std::vector<std::string>& b) {
        return ConfigValidationModel::unionSets(a, b);
    }
    static std::vector<std::string> setSubtract(
        const std::vector<std::string>& a, const std::vector<std::string>& b) {
        return ConfigValidationModel::subtract(a, b);
    }
};

} // namespace Slic3r

#endif /* slic3r_App_PlaterAdapters_hpp_ */
