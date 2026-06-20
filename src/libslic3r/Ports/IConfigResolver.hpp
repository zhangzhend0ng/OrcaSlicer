#ifndef libslic3r_Ports_IConfigResolver_hpp_
#define libslic3r_Ports_IConfigResolver_hpp_

#include <string>
#include <string_view>
#include <optional>

namespace Slic3r {

/// Interface for resolving dynamic configuration overrides.
/// Defined in libslic3r (Layer 2), implemented by Application (Layer 3).
/// Replaces: dependency on GUI_App::get_config() for dynamic config values.
class IConfigResolver {
public:
    virtual ~IConfigResolver() = default;

    /// Get a configuration value by section and key.
    /// Returns nullopt if the key is not found.
    virtual std::optional<std::string> get_config_value(
        std::string_view section, std::string_view key) const = 0;
};

} // namespace Slic3r

#endif /* libslic3r_Ports_IConfigResolver_hpp_ */
