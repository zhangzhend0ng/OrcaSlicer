#ifndef slic3r_App_PresetViewModel_hpp_
#define slic3r_App_PresetViewModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>

namespace Slic3r {

/// Preset type identifier.
enum class PresetType {
    Print,
    Filament,
    Printer,
    SLA_Print,
    SLA_Material,
    PhysicalPrinter,
};

/// Lightweight preset info for View display.
struct PresetInfo {
    std::string name;
    std::string vendor;
    std::string version;
    bool        isSystem{false};
    bool        isCompatible{true};
    bool        isDirty{false};
};

/// MVVP ViewModel for Preset management (extracted from GUI_App).
/// Handles preset CRUD, validation, loading, saving, and migration.
class PresetViewModel {
public:
    // ?? Observable State ??
    MVVP::Property<std::vector<PresetInfo>> printPresets{{}};
    MVVP::Property<std::vector<PresetInfo>> filamentPresets{{}};
    MVVP::Property<std::vector<PresetInfo>> printerPresets{{}};
    MVVP::Property<int>                     selectedPrintIndex{-1};
    MVVP::Property<int>                     selectedFilamentIndex{-1};
    MVVP::Property<int>                     selectedPrinterIndex{-1};
    MVVP::Property<bool>                    hasUnsavedChanges{false};
    MVVP::Property<bool>                    isLoading{false};

    // ?? Commands ??
    MVVP::Command savePreset{
        [this] { /* save current preset */ },
        [this] { return hasUnsavedChanges.get(); }
    };
    MVVP::Command discardChanges{
        [this] { /* reload from disk */ },
        [this] { return hasUnsavedChanges.get(); }
    };
    MVVP::Command importPreset{
        [this] { /* import from file */ }
    };
    MVVP::Command exportPreset{
        [this] { /* export to file */ },
        [this] { return selectedPrintIndex.get() >= 0; }
    };

    // ?? Interface ??
    void loadAll();
    void loadPresetsOfType(PresetType type);
    void selectPreset(PresetType type, int index);
};

} // namespace Slic3r

#endif /* slic3r_App_PresetViewModel_hpp_ */
