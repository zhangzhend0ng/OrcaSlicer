#ifndef slic3r_App_ColorMixViewModel_hpp_
#define slic3r_App_ColorMixViewModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>

namespace Slic3r {

/// A single mixed filament entry.
struct ColorMixEntry {
    int         mixId{-1};
    std::string displayColor;       // hex "#RRGGBBAA"
    std::vector<int> filamentIndices; // which physical filaments
    std::vector<float> ratios;        // blend ratios
};

/// MVVP ViewModel for the mixed filament / color mix panel.
/// Extracted from Plater sidebar color mix feature.
class ColorMixViewModel {
public:
    // ?? Observable State ??
    MVVP::Property<std::vector<ColorMixEntry>> entries{{}};
    MVVP::Property<bool>                        panelVisible{false};
    MVVP::Property<int>                         selectedMixIndex{-1};

    // ?? Commands ??
    MVVP::Command addMix{
        [this] { /* open AddColorMixDialog, add to entries */ },
        [this] { return entries.get().size() < 16; }  // max 16 entries
    };
    MVVP::Command editSelectedMix{
        [this] { /* open edit dialog for selectedMixIndex */ },
        [this] { return selectedMixIndex.get() >= 0; }
    };
    MVVP::Command deleteSelectedMix{
        [this] { /* remove selectedMixIndex from entries */ },
        [this] { return selectedMixIndex.get() >= 0; }
    };

    /// Update visibility based on physical filament count.
    void updateVisibility(int filamentCount) {
        panelVisible.set(filamentCount >= 2);
    }
};

} // namespace Slic3r

#endif /* slic3r_App_ColorMixViewModel_hpp_ */
