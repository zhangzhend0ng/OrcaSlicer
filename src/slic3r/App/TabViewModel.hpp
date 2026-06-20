#ifndef slic3r_App_TabViewModel_hpp_
#define slic3r_App_TabViewModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>
#include <map>

namespace Slic3r {

/// A single config key-value pair for View display.
struct ConfigEntry {
    std::string key;
    std::string value;
    std::string defaultValue;
    std::string label;          // localized display name
    std::string tooltip;        // localized tooltip
    std::string category;       // grouping category
    bool        isOverridden{false};
    bool        isDirty{false};
    bool        isReadOnly{false};
};

/// Config category group.
struct ConfigCategory {
    std::string              name;
    std::vector<ConfigEntry> entries;
};

/// Base MVVP ViewModel for config editing tabs.
/// Each Tab subclass gets a corresponding TabViewModel subclass.
/// Pure C++, zero wxPropertyGrid dependency.
class TabViewModel {
public:
    // ?? Observable State ??
    MVVP::Property<std::vector<ConfigCategory>> config{{}};
    MVVP::Property<bool>                        hasDirtyChanges{false};
    MVVP::Property<std::string>                 tabTitle{""};
    MVVP::Property<std::string>                 searchFilter{""};
    MVVP::Property<bool>                        isExpertMode{false};

    // ?? Commands ??
    MVVP::Command applyChanges{
        [this] { apply(); },
        [this] { return hasDirtyChanges.get(); }
    };
    MVVP::Command revertChanges{
        [this] { revert(); },
        [this] { return hasDirtyChanges.get(); }
    };
    MVVP::Command resetToFactory{
        [this] { resetToDefaults(); }
    };

    // ?? Interface ??
    virtual void loadConfig() = 0;
    virtual void apply();
    virtual void revert();
    virtual void resetToDefaults();
    void setSearchFilter(const std::string& filter);

    /// Set a single config value (called from View when user edits a field).
    void setConfigValue(const std::string& key, const std::string& value);
    /// Get current value or default.
    std::string getConfigValue(const std::string& key) const;

protected:
    // Derived classes populate this map during loadConfig().
    std::map<std::string, std::string> currentValues_;
    std::map<std::string, std::string> originalValues_; // snapshot at load time
    std::map<std::string, std::string> defaultValues_;
};

} // namespace Slic3r

#endif /* slic3r_App_TabViewModel_hpp_ */
