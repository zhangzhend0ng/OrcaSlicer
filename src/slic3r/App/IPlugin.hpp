#ifndef slic3r_App_IPlugin_hpp_
#define slic3r_App_IPlugin_hpp_

#include <string>
#include <memory>

// Forward declarations to avoid wxWidgets dependency in this header
class wxWindow;
class wxPanel;

namespace Slic3r {

class Print;
class PresetBundle;
class DynamicConfig;

/// API version for plugin compatibility checking.
constexpr int ORCA_PLUGIN_API_MAJOR = 1;
constexpr int ORCA_PLUGIN_API_MINOR = 0;

/// Plugin type determines where and when the plugin is activated.
enum class PluginType {
    Tool,          // adds a tool to the 3D canvas
    PostProcessor, // transforms GCode after slicing
    Importer,      // adds a file format importer
    Exporter,      // adds a file format exporter
    Panel,         // adds a UI panel
    General,       // generic extension
};

/// Interface that every plugin must implement.
/// Defined in Application layer (Layer 3).
class IPlugin {
public:
    virtual ~IPlugin() = default;

    /// Unique plugin identifier (e.g., "com.example.hilbertfill").
    virtual std::string id() const = 0;

    /// Human-readable plugin name.
    virtual std::string name() const = 0;

    /// Plugin version string (semver).
    virtual std::string version() const = 0;

    /// Plugin type.
    virtual PluginType type() const { return PluginType::General; }

    /// API version this plugin was compiled against.
    virtual int apiVersion() const {
        return (ORCA_PLUGIN_API_MAJOR << 16) | ORCA_PLUGIN_API_MINOR;
    }

    /// Called once after plugin is loaded. Return false to abort loading.
    virtual bool initialize() { return true; }

    /// Called when the plugin is about to be unloaded.
    virtual void shutdown() {}

    // ?? Optional extension points ??

    /// Create a UI panel. Returns nullptr if plugin has no UI.
    virtual wxPanel* createPanel(wxWindow* /*parent*/) { return nullptr; }

    /// Called before slicing starts. Plugin may modify the Print.
    virtual void onPreSlice(Print& /*print*/) {}

    /// Called after GCode is generated. Plugin may modify the GCode string.
    virtual void onPostGCode(std::string& /*gcode*/) {}
};

/// Interface provided by the host application to plugins.
/// Allows plugins to query application state.
class IPluginHost {
public:
    virtual ~IPluginHost() = default;

    /// Get the current Print object (may be null if no model loaded).
    virtual Print* currentPrint() = 0;

    /// Get the current PresetBundle.
    virtual const PresetBundle* presets() const = 0;

    /// Get application-wide config.
    virtual const DynamicConfig* appConfig() const = 0;

    /// Show a status bar message.
    virtual void showStatus(const std::string& msg) = 0;

    /// Log a message to the application log.
    virtual void log(const std::string& msg) = 0;
};

} // namespace Slic3r

#endif /* slic3r_App_IPlugin_hpp_ */
