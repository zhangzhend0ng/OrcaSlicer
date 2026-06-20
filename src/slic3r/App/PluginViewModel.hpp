#ifndef slic3r_App_PluginViewModel_hpp_
#define slic3r_App_PluginViewModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>

namespace Slic3r {

/// Plugin metadata for View display.
struct PluginInfo {
    std::string name;
    std::string version;
    std::string author;
    std::string description;
    bool        enabled{true};
    bool        isBuiltin{false};
};

/// MVVP ViewModel for plugin management (extracted from GUI_App).
class PluginViewModel {
public:
    // ?? Observable State ??
    MVVP::Property<std::vector<PluginInfo>> plugins{{}};
    MVVP::Property<int>                     selectedPluginIndex{-1};

    // ?? Commands ??
    MVVP::Command toggleSelected{
        [this] { /* toggle enabled/disabled for selected plugin */ },
        [this] { return selectedPluginIndex.get() >= 0; }
    };
    MVVP::Command installPlugin{
        [this] { /* open file dialog, load DLL plugin */ }
    };
    MVVP::Command uninstallSelected{
        [this] { /* remove selected plugin */ },
        [this] { return selectedPluginIndex.get() >= 0; }
    };

    // ?? Interface ??
    void discoverPlugins(const std::string& pluginDir);
    void loadPlugin(const std::string& path);
};

} // namespace Slic3r

#endif /* slic3r_App_PluginViewModel_hpp_ */
