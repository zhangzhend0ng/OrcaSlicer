#pragma once

#include <slic3r/GUI/WebPanel.hpp>
#include <slic3r/plugin/PythonPluginInterface.hpp>
#include <slic3r/plugin/pluginTypes/pages/PagesPluginCapability.hpp>

#include <atomic>
#include <map>
#include <memory>
#include <string>

// ADAPTED: fork keeps the wxImageList icon path for plugin pages (upstream switched to a
// per-page wxBitmap); bookctrl/imaglist stay for m_icon_image_id / m_image_list.
#include <wx/bookctrl.h>
#include <wx/imaglist.h>
#include <wx/panel.h>
#include <wx/webview.h>

class Notebook;

namespace Slic3r {

class PluginPage : public GUI::WebPanel
{
public:
    PluginPage(wxWindow* parent, std::shared_ptr<PagesPluginCapability> capability);
    ~PluginPage() override;

    PluginPage() = delete;

    void detach_capability();
    void push_message(const std::string& message);
    void set_icon_image_id(int id) { m_icon_image_id = id; }
    int get_icon_image_id() const { return m_icon_image_id; }

protected:
    std::optional<std::string> page_html() override;
    bool on_page_message(const std::string& kind, const nlohmann::json& data) override;

private:
    void on_new_window(wxWebViewEvent& event);

    std::shared_ptr<PagesPluginCapability> m_cap;
    std::shared_ptr<std::atomic<PluginPage*>> m_lifetime;
    // m_content_loaded moved up to the WebPanel base with the shared web hosting.
    int m_icon_image_id = wxBookCtrlBase::NO_IMAGE;
};

class PluginPages
{
public:
    PluginPages() = default;
    ~PluginPages();

    PluginPages(const PluginPages&)            = delete;
    PluginPages& operator=(const PluginPages&) = delete;

    void initialize(Notebook* parent);
    void shutdown();

    void on_cap_register(const PluginCapabilityId& id);
    void on_cap_deregister(const PluginCapabilityId& id);
    void on_plugin_register(const std::string& plugin_key);
    void on_plugin_deregister(const std::string& plugin_key);

    void select_page(const PluginCapabilityId& id);

private:
    std::shared_ptr<PagesPluginCapability> get_pages_cap(const PluginCapabilityId& id, bool is_enabled) const;
    void remove_page(const PluginCapabilityId& id);
    static wxString page_tab_id(const PluginCapabilityId& id);

    std::map<PluginCapabilityId, PluginPage*> m_pages;
    Notebook* m_parent{nullptr};

    std::unique_ptr<wxImageList> m_image_list;
};

} // namespace Slic3r
