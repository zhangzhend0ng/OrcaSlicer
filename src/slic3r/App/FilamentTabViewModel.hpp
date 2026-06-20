#ifndef slic3r_App_FilamentTabViewModel_hpp_
#define slic3r_App_FilamentTabViewModel_hpp_

#include "slic3r/App/TabViewModel.hpp"

#include <string>
#include <vector>

namespace Slic3r {

/// Filament info for extruder selection View.
struct FilamentInfo {
    int         extruderIndex{0};
    std::string presetName;
    std::string material;       // PLA, ABS, PETG, etc.
    std::string colorHex;       // "#FF0000FF"
    float       diameter{1.75f};
    float       density{1.24f};
    float       costPerKg{20.0f};
    int         nozzleTemp{210};
    int         bedTemp{60};
};

/// MVVM ViewModel for Filament Settings tab.
/// Handles: filament diameter, temperature, cooling, extrusion multiplier,
///          retraction, wiping, color, material properties.
class FilamentTabViewModel : public TabViewModel {
public:
    FilamentTabViewModel() { tabTitle.set("Filament Settings"); }

    void loadConfig() override;

    MVVP::Property<std::vector<FilamentInfo>> filaments{{}};
    MVVP::Property<int>                       activeFilament{0};
    MVVP::Property<bool>                      hasMultipleFilaments{false};

    void addFilament();
    void removeFilament(int index);
    void setActiveFilament(int index);
};

} // namespace Slic3r

#endif /* slic3r_App_FilamentTabViewModel_hpp_ */
