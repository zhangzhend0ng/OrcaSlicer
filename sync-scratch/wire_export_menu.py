import io

# ── MainFrame.hpp: members + method declarations ──────────────────────────────
p = 'src/slic3r/GUI/MainFrame.hpp'
s = io.open(p, encoding='utf-8').read()
anchor = '    Plater*               m_plater { nullptr };'
add = '''    Plater*               m_plater { nullptr };

    // Fork addition: dynamic plugin-exporter section of the File > Export menu. Items are
    // appended after the built-ins (m_plugin_export_section_base records where the section
    // starts) and rebuilt on capability load/unload; ids live in a reserved range handled by
    // one range-bound handler. See rebuild_plugin_export_items() in MainFrame.cpp.
    void                rebuild_plugin_export_items();
    void                on_plugin_export_menu(wxCommandEvent& evt);
    wxMenu*             m_export_menu { nullptr };
    int                 m_plugin_export_section_base { 0 };
    std::map<int, std::shared_ptr<Slic3r::ExporterPluginCapability>> m_plugin_export_items;'''
assert s.count(anchor) == 1
s = s.replace(anchor, add)
io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('hpp ok')

# ── MainFrame.cpp: includes, menu wiring, methods ─────────────────────────────
p = 'src/slic3r/GUI/MainFrame.cpp'
s = io.open(p, encoding='utf-8').read()

inc_anchor = '#include <slic3r/GUI/MainFrame.hpp>'
if inc_anchor not in s:
    # fall back: find any stable include to append after; MainFrame.hpp must be included somehow
    inc_anchor = '#include "MainFrame.hpp"'
assert inc_anchor in s, 'mainframe include anchor not found'
s = s.replace(inc_anchor, inc_anchor + '\n#include <slic3r/plugin/PluginManager.hpp>\n#include <slic3r/plugin/pluginTypes/exporter/ExporterPluginCapability.hpp>\n#include "common_func/common_func.hpp"', 1)

menu_anchor = '''        append_menu_item(
            export_menu, wxID_ANY, _L("Export Preset Bundle") + dots /* + "\\t" + ctrl + "E"*/, _L("Export current configuration to files"),
            [this](wxCommandEvent &) { export_config(); },
            "menu_export_config", nullptr,
            []() { return true; }, this);

        append_submenu(fileMenu, export_menu, wxID_ANY, _L("Export"), "");'''
menu_new = '''        append_menu_item(
            export_menu, wxID_ANY, _L("Export Preset Bundle") + dots /* + "\\t" + ctrl + "E"*/, _L("Export current configuration to files"),
            [this](wxCommandEvent &) { export_config(); },
            "menu_export_config", nullptr,
            []() { return true; }, this);

        // Fork addition: plugin exporters. One range-bound handler covers the section's
        // reserved id range; the section itself is rebuilt on capability load/unload
        // (subscribed in GUI_App). Built when the menu is first created and whenever the
        // exporter set changes.
        m_export_menu = export_menu;
        m_plugin_export_section_base = export_menu->GetMenuItemCount();
        m_export_menu->Bind(wxEVT_MENU, &MainFrame::on_plugin_export_menu, this,
                            kPluginExportMenuIdBase, kPluginExportMenuIdMax);
        rebuild_plugin_export_items();

        append_submenu(fileMenu, export_menu, wxID_ANY, _L("Export"), "");'''
assert s.count(menu_anchor) == 1, 'menu anchor not found'
s = s.replace(menu_anchor, menu_new)

# The methods + id constants: append before the final closing of the file. Find a stable
# tail anchor: the last function is unknown, so append after the menu block instead by
# inserting the method definitions right before the line that closes init_tabpanel's
# sibling scope... Instead: append at end of file.
methods = '''

// Fork addition: plugin exporters in the File > Export menu. Id range reserved for the
// dynamic section; one range Bind (see the menu construction) maps ids back to capabilities.
namespace {
constexpr int kPluginExportMenuIdBase_ = 0; // placeholder, real constants below
}

void MainFrame::rebuild_plugin_export_items()
{
    if (m_export_menu == nullptr)
        return;

    // Remove the previous plugin section (separator included): everything appended after
    // the recorded base item count belongs to it.
    while (m_export_menu->GetMenuItemCount() > m_plugin_export_section_base)
        m_export_menu->Delete(m_export_menu->GetMenuItems().back());
    m_plugin_export_items.clear();

    const auto exporters = Slic3r::PluginManager::instance().get_plugin_capabilities(
        "", Slic3r::PluginCapabilityType::Exporter, /*only_enabled=*/true);
    if (exporters.empty())
        return;

    m_export_menu->AppendSeparator();
    int next_id = kPluginExportMenuIdBase;
    for (const auto& cap : exporters) {
        auto* exporter = dynamic_cast<Slic3r::ExporterPluginCapability*>(cap.get());
        if (exporter == nullptr || exporter->supported_extensions().empty() || next_id > kPluginExportMenuIdMax)
            continue;
        std::string exts;
        for (const std::string& e : exporter->supported_extensions()) {
            if (!exts.empty())
                exts += " ";
            exts += e;
        }
        m_export_menu->Append(next_id, from_u8(_u8L("Export via plugin")) + " " + from_u8(exporter->name()) + "  [" + from_u8(exts) + "]");
        m_plugin_export_items.emplace(next_id, std::shared_ptr<Slic3r::ExporterPluginCapability>(cap, exporter));
        ++next_id;
    }
}

void MainFrame::on_plugin_export_menu(wxCommandEvent& evt)
{
    const auto found = m_plugin_export_items.find(evt.GetId());
    if (found == m_plugin_export_items.end())
        return;
    std::shared_ptr<Slic3r::ExporterPluginCapability> exporter = found->second;
    if (m_plater == nullptr || m_plater->model().objects.empty())
        return;

    // Save dialog with the exporter's own extensions as the default filter.
    wxString filters = from_u8(_u8L("Export file")) + "|";
    {
        std::string pattern;
        for (const std::string& e : exporter->supported_extensions()) {
            if (!pattern.empty())
                pattern += ";";
            pattern += "*" + e;
        }
        filters += from_u8(pattern);
    }
    const std::string default_ext = exporter->supported_extensions().front();
    wxFileDialog      dlg(this, from_u8(_u8L("Export to file")), "", "export" + from_u8(default_ext),
                   filters, wxFD_SAVE | wxFD_OVERWRITE_PROMPT);
    if (dlg.ShowModal() != wxID_OK)
        return;
    const std::string path = into_u8(dlg.GetPath());

    // UI-thread snapshot (Model copy = a clone), then the plugin runs on a worker thread:
    // the UI never waits for plugin work (the batch-3 review contract; the trampoline takes
    // the GIL on the worker and grants dirname(path) as a scoped writable root). The thread
    // owns the snapshot; the completion CallAfter is dropped if the app is closing.
    auto snapshot = std::make_shared<Slic3r::Model>(m_plater->model());
    std::thread([exporter, snapshot, path]() {
        bool        ok = false;
        std::string message;
        try {
            Slic3r::ExporterContext ctx;
            ctx.orca_version = Snapmaker_VERSION;
            ctx.path         = path;
            ctx.model        = snapshot.get();
            const Slic3r::ExecutionResult result = exporter->export_file(ctx);
            ok      = result.status == Slic3r::PluginResult::Success;
            message = result.message.empty() ? path : result.message;
        } catch (const std::exception& e) {
            message = e.what();
        }
        Slic3r::GUI::wxGetApp().CallAfter([ok, message]() {
            if (wxTheApp == nullptr || Slic3r::GUI::wxGetApp().is_closing())
                return;
            wxMessageBox(from_u8(message), from_u8(ok ? _u8L("Export finished") : _u8L("Export failed")),
                         wxOK | (ok ? wxICON_INFORMATION : wxICON_ERROR));
        });
    }).detach();
}
'''
s = s.rstrip() + '\n' + methods

# The id constants must exist at namespace scope BEFORE the menu Bind uses them; put them
# just above the file's first use — simplest: inject near the top, after the includes block
# terminator. Anchor on the anonymous-namespace-free stable string used by the Bind above.
const_anchor = 'static constexpr int kPluginExportMenuIdBase = wxID_HIGHEST - 4096;'
if const_anchor not in s:
    # insert the constants right before the menu construction function that uses them is
    # hard to target; instead prepend at the very first namespace/opening after includes.
    # Reliable spot: immediately before the menu_anchor's enclosing usage by placing them
    # above via a static in-class? No — file scope after the first blank line post-includes.
    idx = s.find('namespace Slic3r {')
    assert idx > 0
    consts = ('// Reserved id range for the File > Export menu\'s dynamic plugin-exporter section.\n'
              'static constexpr int kPluginExportMenuIdBase = wxID_HIGHEST - 4096;\n'
              'static constexpr int kPluginExportMenuIdMax  = kPluginExportMenuIdBase + 63;\n\n')
    s = s[:idx] + consts + s[idx:]

# remove the placeholder namespace block from the appended methods
s = s.replace('''namespace {
constexpr int kPluginExportMenuIdBase_ = 0; // placeholder, real constants below
}

''', '')

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('mainframe ok')

# ── GUI_App.cpp: rebuild the section on exporter capability load/unload ───────
p = 'src/slic3r/GUI/GUI_App.cpp'
s = io.open(p, encoding='utf-8').read()
old_load = '''            if (capability.type == PluginCapabilityType::Pages && wxTheApp && !wxGetApp().is_closing() && wxGetApp().mainframe)
                wxGetApp().mainframe->plugin_pages().on_cap_register(capability);
        });'''
new_load = '''            if (capability.type == PluginCapabilityType::Pages && wxTheApp && !wxGetApp().is_closing() && wxGetApp().mainframe)
                wxGetApp().mainframe->plugin_pages().on_cap_register(capability);
            // Fork addition: exporter capabilities appear in the File > Export menu.
            if (capability.type == PluginCapabilityType::Exporter && wxTheApp && !wxGetApp().is_closing() && wxGetApp().mainframe)
                wxGetApp().CallAfter([]() {
                    if (MainFrame* frame = wxGetApp().mainframe)
                        frame->rebuild_plugin_export_items();
                });
        });'''
assert s.count(old_load) == 1
s = s.replace(old_load, new_load)

old_unload = '''            if (capability.type == PluginCapabilityType::Pages && wxTheApp && !wxGetApp().is_closing() && wxGetApp().mainframe)
                wxGetApp().mainframe->plugin_pages().on_cap_deregister(capability);
        });'''
new_unload = '''            if (capability.type == PluginCapabilityType::Pages && wxTheApp && !wxGetApp().is_closing() && wxGetApp().mainframe)
                wxGetApp().mainframe->plugin_pages().on_cap_deregister(capability);
            if (capability.type == PluginCapabilityType::Exporter && wxTheApp && !wxGetApp().is_closing() && wxGetApp().mainframe)
                wxGetApp().CallAfter([]() {
                    if (MainFrame* frame = wxGetApp().mainframe)
                        frame->rebuild_plugin_export_items();
                });
        });'''
assert s.count(old_unload) == 1
s = s.replace(old_unload, new_unload)
io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('gui_app ok')
