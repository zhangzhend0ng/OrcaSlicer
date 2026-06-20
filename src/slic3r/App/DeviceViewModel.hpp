#ifndef slic3r_App_DeviceViewModel_hpp_
#define slic3r_App_DeviceViewModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>

namespace Slic3r {

/// Connection state for a device.
enum class ConnectionState {
    Disconnected,
    Connecting,
    Connected,
    Error,
};

/// Lightweight device info for View display.
struct DeviceInfo {
    std::string     serialNumber;
    std::string     name;
    std::string     model;
    std::string     ipAddress;
    ConnectionState state{ConnectionState::Disconnected};
    int             progress{0};
    float           nozzleTemp{0.0f};
    float           bedTemp{0.0f};
};

/// MVVP ViewModel for device/printer management (extracted from GUI_App).
/// Handles MQTT connection, device discovery, printer status.
class DeviceViewModel {
public:
    // ?? Observable State ??
    MVVP::Property<std::vector<DeviceInfo>> devices{{}};
    MVVP::Property<int>                     selectedDeviceIndex{-1};
    MVVP::Property<bool>                    isScanning{false};
    MVVP::Property<std::string>             lastError{""};

    // ?? Commands ??
    MVVP::Command scanNetwork{
        [this] { /* start mDNS/MQTT discovery */ },
        [this] { return !isScanning.get(); }
    };
    MVVP::Command connectSelected{
        [this] { /* connect to selected device */ },
        [this] { return selectedDeviceIndex.get() >= 0; }
    };
    MVVP::Command disconnectSelected{
        [this] { /* disconnect selected device */ },
        [this] { return selectedDeviceIndex.get() >= 0; }
    };
    MVVP::Command sendPrintJob{
        [this] { /* send current GCode to device */ }
    };

    // ?? Interface ??
    void onDeviceDiscovered(const DeviceInfo& info);
    void onDeviceStatusUpdate(const std::string& serial, int progress, float nozzle, float bed);
    void onConnectionError(const std::string& serial, const std::string& error);
};

} // namespace Slic3r

#endif /* slic3r_App_DeviceViewModel_hpp_ */
