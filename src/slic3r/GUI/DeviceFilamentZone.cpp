#include "DeviceFilamentZone.hpp"

#include "Fulfillment/FulfillmentStore.hpp"
#include "Fulfillment/FulfillmentPanel.hpp"
#include "GUI_App.hpp"
#include "Plater.hpp"                       // build_machine_filament_list
#include "DeviceManager.hpp"
#include "filamentsync/FilamentData.hpp"     // FilamentData, is_none_filament
#include "Widgets/StaticBox.hpp"
#include "Widgets/Label.hpp"
#include "wxExtensions.hpp" // get_extruder_color_icon, ScalableButton

#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/PrintConfig.hpp"

#include <wx/sizer.h>
#include <wx/stattext.h>
#include <wx/bmpbuttn.h>
#include <wx/colour.h>

namespace Slic3r {
namespace GUI {

DeviceFilamentZone::DeviceFilamentZone(wxWindow* parent) : wxPanel(parent, wxID_ANY)
{
    const bool     is_dark    = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);
    const wxColour title_bg   = wxColour(248, 248, 248); // mirrors Sidebar::Sidebar title_bg

    SetBackgroundColour(content_bg);

    auto* root = new wxBoxSizer(wxVERTICAL);

    // --- Title bar ---
    m_panel_title = new StaticBox(this, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxTAB_TRAVERSAL | wxBORDER_NONE);
    m_panel_title->SetBackgroundColor(title_bg);
    m_panel_title->SetBackgroundColor2(0xF1F1F1);
    m_panel_title->SetMinSize(wxSize(-1, FromDIP(30)));
    m_panel_title->SetMaxSize(wxSize(-1, FromDIP(30)));

    auto* title_icon  = new ScalableButton(m_panel_title, wxID_ANY, "filament");
    auto* title_label = new Label(m_panel_title, _L("Device Filaments"), LB_PROPAGATE_MOUSE_EVENT);

    m_refresh_btn = new ScalableButton(m_panel_title, wxID_ANY, "refresh");
    m_refresh_btn->SetToolTip(_L("Refresh device filaments"));

    auto* h_title     = new wxBoxSizer(wxHORIZONTAL);
    auto* white_left  = new wxPanel(m_panel_title, wxID_ANY, wxDefaultPosition, wxSize(FromDIP(SidebarProps::ContentMargin()), -1));
    white_left->SetBackgroundColour(*wxWHITE);
    h_title->Add(white_left, 0, wxEXPAND, 0);
    h_title->Add(title_icon, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, FromDIP(SidebarProps::TitlebarMargin()));
    h_title->AddSpacer(FromDIP(SidebarProps::ElementSpacing()));
    h_title->Add(title_label, 0, wxALIGN_CENTER_VERTICAL);
    h_title->AddStretchSpacer();
    h_title->Add(m_refresh_btn, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(8));
    auto* white_right = new wxPanel(m_panel_title, wxID_ANY, wxDefaultPosition, wxSize(FromDIP(SidebarProps::ContentMargin()), -1));
    white_right->SetBackgroundColour(*wxWHITE);
    h_title->Add(white_right, 0, wxEXPAND, 0);
    m_panel_title->SetSizer(h_title);
    m_panel_title->Layout();

    // --- Device stock content ---
    m_panel_content = new wxPanel(this, wxID_ANY);
    m_panel_content->SetBackgroundColour(content_bg);
    m_panel_content->SetSizer(new wxBoxSizer(wxVERTICAL));

    // Refresh button: re-reads device state into filament_ams_list (read-only,
    // no dialog, no design-side mutation). Deliberately NOT sync_ams_list().
    // If no machine is explicitly selected, fall back to the first one returned
    // by get_my_machine_list() (which already applies its own validity filter —
    // do NOT re-filter here, that double-gated LAN access checks and dropped
    // legitimately-connected devices, e.g. WCP/Moonraker ones).
    m_refresh_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        auto* dm = wxGetApp().getDeviceManager();
        MachineObject* obj = dm ? dm->get_selected_machine() : nullptr;
        if (!obj && dm) {
            const auto ml = dm->get_my_machine_list();
            if (!ml.empty()) obj = ml.begin()->second;
        }
        if (obj)
            GUI::wxGetApp().sidebar().load_ams_list(obj->dev_id, obj);
        refresh();
    });

    root->AddSpacer(FromDIP(8));
    root->Add(m_panel_title, 0, wxEXPAND, 0);
    root->AddSpacer(FromDIP(8));
    root->Add(m_panel_content, 0, wxEXPAND, 0);
    root->AddSpacer(FromDIP(8));

    SetSizer(root);
    Layout();

    // Auto-refresh timer: poll device stock every 2s; refresh only when it
    // changes. This picks up WCP sync data (m_connect_machine_info_list) without
    // the user needing to click refresh, and also marks the fulfilment store
    // stale so the FulfillmentPanel stays current.
    Bind(wxEVT_TIMER, &DeviceFilamentZone::on_timer, this);
    m_auto_timer.Start(2000);
}

void DeviceFilamentZone::on_timer(wxTimerEvent&)
{
    PresetBundle* pb = wxGetApp().preset_bundle;
    if (!pb) return;
    std::vector<FilamentData> machine_list;
    build_machine_filament_list(pb, machine_list);
    if (machine_list.size() != m_last_stock_count) {
        m_last_stock_count = machine_list.size();
        refresh();
        // Also notify the fulfilment store that device data may have changed.
        auto& store = wxGetApp().plater()->sidebar().fulfillment_store();
        store.mark_stale();
        if (auto* panel = wxGetApp().plater()->sidebar().fulfillment_panel())
            panel->refresh_fulfilment();
        wxGetApp().plater()->sidebar().update_fulfillment_health_indicator();
    }
}

void DeviceFilamentZone::refresh()
{
    // Tear down previous content children and rebuild.
    m_panel_content->DestroyChildren();
    const bool     is_dark    = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);

    auto* grid = new wxFlexGridSizer(2, FromDIP(4), FromDIP(4));
    grid->AddGrowableCol(0);
    grid->AddGrowableCol(1);

    // Reuse build_machine_filament_list — the SAME function the sync dialog
    // uses — so device filaments resolve identically (WCP source via
    // m_connect_machine_info_list). Reading filament_ams_list directly missed
    // WCP/Moonraker devices entirely.
    PresetBundle* pb = wxGetApp().preset_bundle;
    std::vector<FilamentData> machine_list;
    if (pb) build_machine_filament_list(pb, machine_list);

    if (machine_list.empty()) {
        auto* hint = new Label(m_panel_content,
            _L("No device filaments detected. Connect a printer, ensure it's selected in the Device page, then click refresh."),
            LB_PROPAGATE_MOUSE_EVENT);
        hint->SetBackgroundColour(content_bg);
        hint->Wrap(FromDIP(220));
        auto* wrap = new wxBoxSizer(wxVERTICAL);
        wrap->Add(hint, 0, wxALL, FromDIP(8));
        m_panel_content->SetSizer(wrap, true);
        m_panel_content->Layout();
        Layout();
        return;
    }

    for (const FilamentData& fd : machine_list) {
        std::string slot_label = std::to_string(fd.m_index + 1);
        add_tray_item(grid, slot_label, fd);
    }

    auto* wrap = new wxBoxSizer(wxVERTICAL);
    wrap->Add(grid, 0, wxEXPAND | wxALL, FromDIP(8));
    m_panel_content->SetSizer(wrap, true);
    m_panel_content->Layout();
    Layout();
}

void DeviceFilamentZone::add_tray_item(wxFlexGridSizer* grid, const std::string& slot_label, const FilamentData& fd)
{
    const bool     is_dark    = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);
    const bool     exists     = !is_none_filament(fd);

    // Display colour: the filament's actual colour, or grey for empty slots.
    std::string icon_color = exists ? fd.m_color.PrimaryColor()
                                    : (is_dark ? "#646468" : "#C8C8C8");
    if (icon_color.empty()) icon_color = is_dark ? "#646468" : "#C8C8C8";

    // Display name: the full brand/model name (e.g. "Snapmaker PLA Matte") when
    // loaded; "Empty" when not. This is what the user actually wants to see —
    // the concrete vendor filament, not a hand-rolled type abbreviation.
    std::string display_name = exists ? fd.m_name : "Empty";
    if (display_name.empty()) display_name = exists ? fd.m_type : "Empty";
    if (display_name.empty()) display_name = "Unknown";

    auto* row = new wxPanel(m_panel_content, wxID_ANY);
    row->SetBackgroundColour(content_bg);
    auto* row_sizer = new wxBoxSizer(wxHORIZONTAL);

    auto* swatch = new wxBitmapButton(row, wxID_ANY, wxNullBitmap, wxDefaultPosition,
                                      wxSize(FromDIP(24), FromDIP(16)), wxBORDER_NONE);
    swatch->SetBitmap(*get_extruder_color_icon(icon_color, slot_label, FromDIP(24), FromDIP(16)));
    swatch->SetBackgroundColour(content_bg);

    auto* text = new Label(row, wxString::FromUTF8(display_name), LB_PROPAGATE_MOUSE_EVENT);
    text->SetBackgroundColour(content_bg);
    text->Wrap(FromDIP(180));

    row_sizer->Add(swatch, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(6));
    row_sizer->Add(text, 1, wxALIGN_CENTER_VERTICAL);
    row->SetSizer(row_sizer);

    grid->Add(row, 0, wxEXPAND | wxALL, FromDIP(2));
}

} // namespace GUI
} // namespace Slic3r
