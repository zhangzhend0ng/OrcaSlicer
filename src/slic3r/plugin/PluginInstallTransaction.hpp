#pragma once

#include <boost/filesystem/path.hpp>
#include <string>

namespace Slic3r {
class PluginConfig;
struct PluginDescriptor;

// Caller owns the profile's runtime lock. Replacements remain recoverable until
// the candidate has imported, registered and completed on_load successfully.
bool replace_local_plugin_package(const boost::filesystem::path& source, PluginDescriptor& descriptor, std::string& error);
bool has_pending_plugin_replacement(const std::string& plugin_root);
bool can_activate_plugin_replacement(const std::string& plugin_root, std::string& error);
bool finish_plugin_replacement(const std::string& plugin_root, bool accept, PluginConfig& config, std::string& error);
bool recover_plugin_replacements(PluginConfig& config, std::string& error);
} // namespace Slic3r
