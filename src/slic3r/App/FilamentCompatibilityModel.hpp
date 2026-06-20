#ifndef slic3r_App_FilamentCompatibilityModel_hpp_
#define slic3r_App_FilamentCompatibilityModel_hpp_

#include "libslic3r/MVVP.hpp"
#include <string>
#include <vector>

namespace Slic3r {

/// Filament category for compatibility checking.
enum class FilamentCategory {
    Unknown, PLA, ABS, PETG, TPU, PA, PC, PVA, HIPS, PP, ASA,
    Composite, Support, Other
};

/// Resolved filament category with normalized type.
struct ResolvedFilamentCategory {
    std::string      rawType;
    std::string      normalizedType;
    FilamentCategory category{FilamentCategory::Unknown};
};

/// Pure-C++ filament compatibility logic.
/// Extracted from MixedColorMatchHelpers.cpp (6 static functions).
/// Zero wxWidgets dependency.
class FilamentCompatibilityModel {
public:
    /// Build NxN compatibility matrix (all true initially).
    static std::vector<std::vector<bool>> buildCompatibilityMatrix(size_t n);

    /// Check if two filament categories are compatible.
    static bool isCategoryCompatible(FilamentCategory a, FilamentCategory b);

    /// Resolve raw filament types to categories.
    static std::vector<ResolvedFilamentCategory> resolveCategories(
        const std::vector<std::string>& filamentTypes);

    /// Normalize filament type string for comparison.
    static std::string normalizeFilamentType(const std::string& type);

    /// Parse filament category from string.
    static FilamentCategory parseCategory(const std::string& type);

    // ?? Observable State ??
    MVVP::Property<bool> compatibilityLoaded{false};
};

} // namespace Slic3r

#endif /* slic3r_App_FilamentCompatibilityModel_hpp_ */
