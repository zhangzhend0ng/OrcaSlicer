#include "McpParams.hpp"

#include <set>

namespace Slic3r {
namespace Mcp {
namespace McpParams {

bool is_valid_object_param(const std::string& opt_key)
{
    static const std::set<std::string> object_keys = []() {
        std::set<std::string> keys;
        for (const std::string& key : PrintObjectConfig().keys()) {
            keys.insert(key);
        }
        for (const std::string& key : PrintRegionConfig().keys()) {
            keys.insert(key);
        }
        return keys;
    }();
    return object_keys.find(opt_key) != object_keys.end();
}

bool is_valid_plate_param(const std::string& opt_key)
{
    static const std::set<std::string> plate_keys = {"curr_bed_type",
                                                     "print_sequence"};
    return plate_keys.find(opt_key) != plate_keys.end();
}

std::string deserialize_all(DynamicPrintConfig& config,
                            const std::map<std::string, std::string>& params)
{
    for (const auto& entry : params) {
        ConfigSubstitutionContext substitutions(
            ForwardCompatibilitySubstitutionRule::Enable);
        try {
            config.set_deserialize(entry.first, entry.second, substitutions);
        } catch (const std::exception& ex) {
            return "parameter '" + entry.first + "' rejected: " + ex.what();
        } catch (...) {
            return "parameter '" + entry.first + "' rejected";
        }
    }
    return std::string();
}

} // namespace McpParams
} // namespace Mcp
} // namespace Slic3r
