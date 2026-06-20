#ifndef slic3r_App_PluginLoader_hpp_
#define slic3r_App_PluginLoader_hpp_

#include "libslic3r/MVVP.hpp"
#include "slic3r/App/IPlugin.hpp"

#include <string>
#include <vector>
#include <memory>
#include <functional>

namespace Slic3r {

/// Loaded plugin entry.
struct LoadedPlugin {
    std::string            id;
    std::string            name;
    std::string            version;
    PluginType             type{PluginType::General};
    std::string            filePath;
    bool                   enabled{true};
    std::unique_ptr<IPlugin> instance;
};

/// Discovers and loads plugin DLLs from the plugin directory.
/// Handles version checking, dependency resolution, and sandboxing.
class PluginLoader {
public:
    /// Set the host that plugins can interact with.
    void setHost(IPluginHost* host) { host_ = host; }

    /// Set the plugin search directory.
    void setPluginDirectory(const std::string& dir) { pluginDir_ = dir; }

    /// Discover plugins without loading them.
    std::vector<std::string> discover();

    /// Load all discovered plugins.
    void loadAll();

    /// Load a specific plugin by file path.
    bool loadPlugin(const std::string& path);

    /// Unload all plugins.
    void unloadAll();

    // ?? Observables ??
    MVVP::Property<std::vector<LoadedPlugin>> plugins{{}};

    /// Check API version compatibility.
    static bool isCompatible(int pluginApiVersion);

private:
    IPluginHost* host_{nullptr};
    std::string  pluginDir_;
};

} // namespace Slic3r

#endif /* slic3r_App_PluginLoader_hpp_ */
