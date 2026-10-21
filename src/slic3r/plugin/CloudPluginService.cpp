#include "CloudPluginService.hpp"

#include <boost/log/trivial.hpp>

namespace Slic3r {

// Snapmaker port: the upstream OrcaCloudServiceAgent architecture (multi-provider cloud
// agents, ICloudServiceAgent) is not part of this branch. This service is compiled as a
// disabled stub so the plugin manager keeps its upstream shape: every cloud-subscription
// operation reports "unavailable / not signed in" and local plugin side-loading is
// unaffected. Never construct a real agent: set_cloud_agent() is never called by the port.
void CloudPluginService::set_cloud_agent(std::shared_ptr<OrcaCloudServiceAgent> agent) { m_orca_agent = std::move(agent); }

std::shared_ptr<OrcaCloudServiceAgent> CloudPluginService::get_cloud_agent() const { return m_orca_agent; }

bool CloudPluginService::can_fetch_cloud_plugins() const
{
    BOOST_LOG_TRIVIAL(info) << "Orca cloud plugin subscriptions are unavailable in this build";
    return false;
}

bool CloudPluginService::fetch_manifests_into_descriptors(std::vector<PluginDescriptor>&,
                                                      std::vector<std::string>&,
                                                      std::vector<std::string>&) const
{
    return false;
}

bool CloudPluginService::request_cloud_subscribe(const std::string&, std::string& error) const
{
    error = "cloud plugin subscriptions are unavailable in this build";
    return false;
}

bool CloudPluginService::request_cloud_unsubscribe(const PluginDescriptor&, std::string& error) const
{
    error = "cloud plugin subscriptions are unavailable in this build";
    return false;
}

bool CloudPluginService::request_cloud_delete(const PluginDescriptor&, std::string& error) const
{
    error = "cloud plugin subscriptions are unavailable in this build";
    return false;
}

bool CloudPluginService::download_cloud_plugin(PluginDescriptor&,
                                               const std::string&,
                                               CloudPluginDownload&,
                                               std::string& error) const
{
    error = "cloud plugin subscriptions are unavailable in this build";
    return false;
}

bool CloudPluginService::fetch_plugin_changelog(const PluginDescriptor&, std::vector<PluginChangelog>&, std::string& error) const
{
    error = "cloud plugin subscriptions are unavailable in this build";
    return false;
}

bool CloudPluginService::fetch_plugin_changelog(const std::vector<PluginDescriptor>&,
                                                std::unordered_map<std::string, std::vector<PluginChangelog>>&,
                                                std::string& error) const
{
    error = "cloud plugin subscriptions are unavailable in this build";
    return false;
}

} // namespace Slic3r
