#ifndef slic3r_App_PrinterTabViewModel_hpp_
#define slic3r_App_PrinterTabViewModel_hpp_

#include "slic3r/App/TabViewModel.hpp"

#include <string>

namespace Slic3r {

/// Machine limits info.
struct MachineLimits {
    float maxFeedrateX{500.0f};
    float maxFeedrateY{500.0f};
    float maxFeedrateZ{50.0f};
    float maxFeedrateE{100.0f};
    float maxAccelX{9000.0f};
    float maxAccelY{9000.0f};
    float maxAccelZ{500.0f};
    float maxAccelE{10000.0f};
    float maxJerkX{10.0f};
    float maxJerkY{10.0f};
    float maxJerkZ{0.4f};
    float maxJerkE{5.0f};
    float minExtrudeTemp{150.0f};
    float maxExtrudeTemp{300.0f};
    float minBedTemp{0.0f};
    float maxBedTemp{150.0f};
};

/// MVVM ViewModel for Printer Settings tab.
/// Handles: size/coordinates, print bed shape, extruder count, retraction,
///          machine limits, firmware flavor, GCode flavor, start/end GCode.
class PrinterTabViewModel : public TabViewModel {
public:
    PrinterTabViewModel() { tabTitle.set("Printer Settings"); }

    void loadConfig() override;

    MVVP::Property<std::string>  printerModel{""};
    MVVP::Property<std::string>  firmwareFlavor{"Marlin"};
    MVVP::Property<MachineLimits> machineLimits{MachineLimits{}};
    MVVP::Property<std::string>  startGCode{""};
    MVVP::Property<std::string>  endGCode{""};
    MVVP::Property<bool>         hasHeatedBed{true};
    MVVP::Property<bool>         hasEnclosure{false};
    MVVP::Property<int>          bedShape{};  // 0=rect, 1=circular, 2=custom
};

} // namespace Slic3r

#endif /* slic3r_App_PrinterTabViewModel_hpp_ */
