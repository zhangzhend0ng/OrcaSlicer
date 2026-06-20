#ifndef slic3r_App_SettingsViewModel_hpp_
#define slic3r_App_SettingsViewModel_hpp_

#include "libslic3r/MVVP.hpp"

#include <string>
#include <vector>

namespace Slic3r {

/// Supported language entry.
struct LanguageInfo {
    std::string code;   // "en", "zh_CN", etc.
    std::string name;   // "English", "????"
};

/// Application settings observable state.
struct AppSettings {
    std::string language{"en"};
    std::string theme{"dark"};
    bool        checkUpdates{true};
    bool        sendUsageStats{false};
    int         maxRecentFiles{10};
    std::string defaultExportPath;
};

/// MVVP ViewModel for application settings (extracted from GUI_App).
class SettingsViewModel {
public:
    // ?? Observable State ??
    MVVP::Property<AppSettings>         settings{AppSettings{}};
    MVVP::Property<std::vector<LanguageInfo>> languages{{}};
    MVVP::Property<bool>                isDirty{false};

    // ?? Commands ??
    MVVP::Command applySettings{
        [this] { /* save to config file */ isDirty.set(false); },
        [this] { return isDirty.get(); }
    };
    MVVP::Command resetDefaults{
        [this] { settings.set(AppSettings{}); isDirty.set(true); }
    };

    // ?? Interface ??
    void setLanguage(const std::string& code);
    void setTheme(const std::string& theme);
    void load();
    void save();
};

} // namespace Slic3r

#endif /* slic3r_App_SettingsViewModel_hpp_ */
