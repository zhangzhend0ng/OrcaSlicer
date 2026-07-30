#include "DeviceFilamentZone.hpp"

#include "GUI_App.hpp"
#include "Plater.hpp"
#include "DeviceManager.hpp"
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

    // Refresh button: ONLY re-reads device state into filament_ams_list (read-only,
    // no dialog, no design-side mutation). Deliberately NOT sync_ams_list().
    m_refresh_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        auto* obj = wxGetApp().getDeviceManager() ? wxGetApp().getDeviceManager()->get_selected_machine() : nullptr;
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

    PresetBundle* pb       = wxGetApp().preset_bundle;
    const auto&   ams_list = pb ? pb->filament_ams_list : std::map<int, DynamicPrintConfig>{};

    if (ams_list.empty()) {
        auto* hint = new Label(m_panel_content,
            _L("No device filaments. Connect a printer in the Device page and click refresh."),
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

    for (const auto& kv : ams_list) {
        const DynamicPrintConfig& cfg = kv.second;
        std::string tray_name = cfg.opt_string("tray_name", 0u);
        std::string type      = cfg.opt_string("filament_type", 0u);
        std::string color     = cfg.opt_string("filament_colour", 0u);
        bool        exists    = cfg.opt_bool("filament_exist", 0u);
        add_tray_item(grid, tray_name, type, color, exists);
    }

    auto* wrap = new wxBoxSizer(wxVERTICAL);
    wrap->Add(grid, 0, wxEXPAND | wxALL, FromDIP(8));
    m_panel_content->SetSizer(wrap, true);
    m_panel_content->Layout();
    Layout();
}

void DeviceFilamentZone::add_tray_item(wxFlexGridSizer* grid, const std::string& tray_name,
                                       const std::string& filament_type, const std::string& color_hex, bool exists)
{
    const bool     is_dark    = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);

    // Decide display color & label by state:
    //  1. !exists            -> empty slot, grey block + "Empty"
    //  2. exists but no type -> loaded but RFID not resolved, real color (or grey) + "Unknown"
    //  3. otherwise          -> real color + type abbreviation
    std::string icon_color;
    std::string type_label = filament_type;
    if (!exists) {
        icon_color = is_dark ? "#646468" : "#C8C8C8";
        type_label = "Empty";
    } else {
        icon_color = color_hex.empty() ? (is_dark ? "#646468" : "#C8C8C8") : color_hex;
        if (type_label.empty())
            type_label = "Unknown";
    }
    std::string swatch_label = tray_name.empty() ? std::string("?") : tray_name;

    auto* row = new wxPanel(m_panel_content, wxID_ANY);
    row->SetBackgroundColour(content_bg);
    auto* row_sizer = new wxBoxSizer(wxHORIZONTAL);

    auto* swatch = new wxBitmapButton(row, wxID_ANY, wxNullBitmap, wxDefaultPosition,
                                      wxSize(FromDIP(24), FromDIP(16)), wxBORDER_NONE);
    swatch->SetBitmap(*get_extruder_color_icon(icon_color, swatch_label, FromDIP(24), FromDIP(16)));
    swatch->SetBackgroundColour(content_bg);

    auto* text = new Label(row, wxString::FromUTF8(type_label), LB_PROPAGATE_MOUSE_EVENT);
    text->SetBackgroundColour(content_bg);

    row_sizer->Add(swatch, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(6));
    row_sizer->Add(text, 0, wxALIGN_CENTER_VERTICAL);
    row->SetSizer(row_sizer);

    grid->Add(row, 0, wxEXPAND | wxALL, FromDIP(2));
}

} // namespace GUI
} // namespace Slic3r
