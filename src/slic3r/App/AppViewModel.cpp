#include "slic3r/App/AppViewModel.hpp"
#include "slic3r/App/PlaterViewModel.hpp"
#include "slic3r/App/CanvasViewModel.hpp"
#include "slic3r/App/PresetViewModel.hpp"
#include "slic3r/App/DeviceViewModel.hpp"
#include "slic3r/App/SettingsViewModel.hpp"
#include "slic3r/App/AccountViewModel.hpp"
#include "slic3r/App/PluginViewModel.hpp"

namespace Slic3r {

AppViewModel::AppViewModel()
    : platerVM(std::make_unique<PlaterViewModel>())
    , canvasVM(std::make_unique<CanvasViewModel>())
    , presetVM(std::make_unique<PresetViewModel>())
    , deviceVM(std::make_unique<DeviceViewModel>())
    , settingsVM(std::make_unique<SettingsViewModel>())
    , accountVM(std::make_unique<AccountViewModel>())
    , pluginVM(std::make_unique<PluginViewModel>())
{
}

bool AppViewModel::initialize()
{
    // 1. Load configuration
    // 2. Inject Models into sub-ViewModels
    //    platerVM->setModels(&print_, &presets_);
    // 3. Load presets
    //    presetVM->loadAll();
    // 4. Discover plugins
    //    pluginVM->discoverPlugins(pluginPath);

    isInitialized.set(true);
    return true;
}

void AppViewModel::shutdown()
{
    isShuttingDown.set(true);
    // Cleanup: save state, disconnect network, etc.
}

} // namespace Slic3r
