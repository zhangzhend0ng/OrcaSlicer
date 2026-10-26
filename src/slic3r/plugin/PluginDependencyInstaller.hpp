#pragma once
#include <string>
#include <vector>
namespace Slic3r::plugin_loader {
struct DependencyInstallOptions
{
    bool        offline = false;
    std::string wheelhouse;
};
// Host-owned policy persisted in the current application profile; no Python API.
bool                     configure_dependency_install(const DependencyInstallOptions& options, std::string& error);
DependencyInstallOptions dependency_install_options();
// Recover before CPython exposes the shared package path. Never invokes Python or uv.
bool                     recover_dependency_install(std::string& error);
bool                     install_packages_transactionally(const std::vector<std::string>& requirements, std::string& error);
} // namespace Slic3r::plugin_loader
