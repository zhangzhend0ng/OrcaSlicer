#ifndef slic3r_App_AppViewModel_hpp_
#define slic3r_App_AppViewModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <memory>

namespace Slic3r {

// Forward declarations
class PlaterViewModel;
class CanvasViewModel;
class PresetViewModel;
class DeviceViewModel;
class SettingsViewModel;
class AccountViewModel;
class PluginViewModel;
class Print;
class PresetBundle;
class DynamicConfig;

/// Top-level application state.
enum class AppPage {
    Prepare,     // main Plater workspace
    Preview,     // GCode preview
    Device,      // device/printer management
    Calibration, // calibration tools
};

/// MVVP ViewModel for GUI_App (extracted from 734-method god class).
/// Owns all sub-ViewModels and the Model layer objects.
/// Zero wxWidgets dependency.
class AppViewModel {
public:
    AppViewModel();

    // ?? Observable State ??
    MVVP::Property<AppPage>     currentPage{AppPage::Prepare};
    MVVP::Property<bool>        isInitialized{false};
    MVVP::Property<bool>        isShuttingDown{false};
    MVVP::Property<std::string> statusBarText{""};
    MVVP::Property<bool>        darkMode{true};
    MVVP::Property<std::string> currentLanguage{"en"};

    // ?? Commands ??
    MVVP::Command showPrepare    { [this] { currentPage.set(AppPage::Prepare);     } };
    MVVP::Command showPreview    { [this] { currentPage.set(AppPage::Preview);     } };
    MVVP::Command showDevice     { [this] { currentPage.set(AppPage::Device);      } };
    MVVP::Command showCalibration{ [this] { currentPage.set(AppPage::Calibration); } };
    MVVP::Command toggleDarkMode {
        [this] { darkMode.set(!darkMode.get()); }
    };

    // ?? Sub-ViewModels (owned) ??
    std::unique_ptr<PlaterViewModel>  platerVM;
    std::unique_ptr<CanvasViewModel>  canvasVM;
    std::unique_ptr<PresetViewModel>  presetVM;
    std::unique_ptr<DeviceViewModel>  deviceVM;
    std::unique_ptr<SettingsViewModel> settingsVM;
    std::unique_ptr<AccountViewModel> accountVM;
    std::unique_ptr<PluginViewModel>  pluginVM;

    // ?? Model layer (owned by App, injected into sub-VMs) ??
    // In the actual implementation, these are created during init.
    // Print        print_;
    // PresetBundle presets_;
    // DynamicConfig appConfig_;

    // ?? Lifecycle ??
    bool initialize();
    void shutdown();
};

} // namespace Slic3r

#endif /* slic3r_App_AppViewModel_hpp_ */
