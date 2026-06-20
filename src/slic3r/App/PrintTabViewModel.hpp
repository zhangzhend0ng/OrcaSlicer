#ifndef slic3r_App_PrintTabViewModel_hpp_
#define slic3r_App_PrintTabViewModel_hpp_

#include "slic3r/App/TabViewModel.hpp"

namespace Slic3r {

/// MVVM ViewModel for Print Settings tab.
/// Handles: layer height, perimeters, infill, speed, skirt/brim, support material,
///          multi-material, output options, notes, dependencies.
class PrintTabViewModel : public TabViewModel {
public:
    PrintTabViewModel() { tabTitle.set("Print Settings"); }

    void loadConfig() override;

    // Per-extruder override support
    MVVP::Property<int>  activeExtruder{0};
    MVVP::Property<int>  extruderCount{1};
    MVVP::Property<bool> hasExtruderOverrides{false};
};

} // namespace Slic3r

#endif /* slic3r_App_PrintTabViewModel_hpp_ */
