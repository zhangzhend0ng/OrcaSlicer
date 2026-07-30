#include "DeviceFilamentZone.hpp"

#include "Fulfillment/FulfillmentSnapshots.hpp"
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
#include <wx/button.h>
#include <wx/bmpbuttn.h>
#include <wx/colour.h>
#include <iomanip>
#include <sstream>

namespace Slic3r {
namespace GUI {

DeviceFilamentZone::DeviceFilamentZone(wxWindow* parent, FulfillmentStore& store)
    : wxPanel(parent, wxID_ANY), m_store(store)
{
    const bool   is_dark = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);
    const wxColour title_bg    = wxColour(248, 248, 248); // mirrors Sidebar::Sidebar title_bg

    SetBackgroundColour(content_bg);

    auto* root = new wxBoxSizer(wxVERTICAL);

    // --- Title bar (mirrors Filaments title bar: Plater.cpp:2747-2810) ---
    m_panel_title = new StaticBox(this, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxTAB_TRAVERSAL | wxBORDER_NONE);
    m_panel_title->SetBackgroundColor(title_bg);
    m_panel_title->SetBackgroundColor2(0xF1F1F1);
    m_panel_title->SetMinSize(wxSize(-1, FromDIP(30)));
    m_panel_title->SetMaxSize(wxSize(-1, FromDIP(30)));

    auto* title_icon = new ScalableButton(m_panel_title, wxID_ANY, "filament");
    auto* title_label = new Label(m_panel_title, _L("Device Filaments"), LB_PROPAGATE_MOUSE_EVENT);

    m_match_btn = new ScalableButton(m_panel_title, wxID_ANY, "sync_filament");
    m_match_btn->SetToolTip(_L("Match design colours to this device's stock (read-only, never changes your design)"));

    m_refresh_btn = new ScalableButton(m_panel_title, wxID_ANY, "refresh");
    m_refresh_btn->SetToolTip(_L("Refresh device filaments"));

    auto* h_title = new wxBoxSizer(wxHORIZONTAL);
    auto* white_left = new wxPanel(m_panel_title, wxID_ANY, wxDefaultPosition, wxSize(FromDIP(SidebarProps::ContentMargin()), -1));
    white_left->SetBackgroundColour(*wxWHITE);
    h_title->Add(white_left, 0, wxEXPAND, 0);
    h_title->Add(title_icon, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, FromDIP(SidebarProps::TitlebarMargin()));
    h_title->AddSpacer(FromDIP(SidebarProps::ElementSpacing()));
    h_title->Add(title_label, 0, wxALIGN_CENTER_VERTICAL);
    h_title->AddStretchSpacer();
    h_title->Add(m_match_btn, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(4));
    h_title->Add(m_refresh_btn, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(8));
    auto* white_right = new wxPanel(m_panel_title, wxID_ANY, wxDefaultPosition, wxSize(FromDIP(SidebarProps::ContentMargin()), -1));
    white_right->SetBackgroundColour(*wxWHITE);
    h_title->Add(white_right, 0, wxEXPAND, 0);
    m_panel_title->SetSizer(h_title);
    m_panel_title->Layout();

    // --- Device stock content (two-column grid, mirrors Filaments layout) ---
    m_panel_content = new wxPanel(this, wxID_ANY);
    m_panel_content->SetBackgroundColour(content_bg);
    m_panel_content->SetSizer(new wxBoxSizer(wxVERTICAL));

    // --- Fulfilment summary + detail panel (derived; design-safe) ---
    m_panel_fulfilment = new wxPanel(this, wxID_ANY);
    m_panel_fulfilment->SetBackgroundColour(content_bg);
    auto* ful_sizer = new wxBoxSizer(wxVERTICAL);
    m_health_summary = new wxStaticText(m_panel_fulfilment, wxID_ANY, "");
    m_health_summary->SetBackgroundColour(content_bg);
    ful_sizer->Add(m_health_summary, 0, wxALL, FromDIP(8));
    m_panel_fulfilment->SetSizer(ful_sizer);

    // Refresh button: ONLY re-reads device state into filament_ams_list (read-only,
    // no dialog, no design-side mutation). Deliberately NOT sync_ams_list(), which
    // would pop a modal and drop the user's design-side filament/colors.
    m_refresh_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        auto* obj = wxGetApp().getDeviceManager() ? wxGetApp().getDeviceManager()->get_selected_machine() : nullptr;
        if (obj)
            GUI::wxGetApp().sidebar().load_ams_list(obj->dev_id, obj);
        refresh();
    });

    // Match button: snapshot Design (RO) + Device (RO), solve the store, refresh.
    // Design-safe: writes only the Fulfillment store, never project_config.
    m_match_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        PresetBundle* pb = wxGetApp().preset_bundle;
        if (!pb) return;
        auto design = snapshot_design_intent(*pb);
        auto device = snapshot_device_stock(*pb);
        if (design.empty()) {
            m_health_summary->SetLabel(_L("No design filaments to match."));
            return;
        }
        if (device.empty()) {
            m_health_summary->SetLabel(_L("No device stock. Connect a printer and refresh."));
            return;
        }
        m_store.solve(design, device);
        refresh_fulfilment();
    });

    root->AddSpacer(FromDIP(8));
    root->Add(m_panel_title, 0, wxEXPAND, 0);
    root->AddSpacer(FromDIP(8));
    root->Add(m_panel_content, 0, wxEXPAND, 0);
    root->Add(m_panel_fulfilment, 0, wxEXPAND, 0);
    root->AddSpacer(FromDIP(8));

    SetSizer(root);
    Layout();
}

void DeviceFilamentZone::refresh()
{
    // Tear down previous content children and rebuild.
    m_panel_content->DestroyChildren();
    const bool is_dark = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);

    auto* grid = new wxFlexGridSizer(2, FromDIP(4), FromDIP(4));
    grid->AddGrowableCol(0);
    grid->AddGrowableCol(1);

    PresetBundle* pb = wxGetApp().preset_bundle;
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

void DeviceFilamentZone::refresh_fulfilment()
{
    const bool is_dark = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);

    // Rebuild the fulfilment panel: summary + per-intent rows.
    m_panel_fulfilment->DestroyChildren();
    auto* sizer = new wxBoxSizer(wxVERTICAL);

    if (!m_store.has_solved()) {
        // No solve yet — show a neutral hint, no health claim (PRD §12.3:
        // don't claim match state without a prior solve).
        auto* hint = new Label(m_panel_fulfilment,
            _L("Design colours vs device stock: press Match to check."),
            LB_PROPAGATE_MOUSE_EVENT);
        hint->SetBackgroundColour(content_bg);
        sizer->Add(hint, 0, wxALL, FromDIP(8));
        m_panel_fulfilment->SetSizer(sizer, true);
        m_panel_fulfilment->Layout();
        Layout();
        return;
    }

    // Summary line (PRD §5.3 global health, §5 gaps spoken).
    const auto roll = m_store.rollup();
    // Plural-safe summary; uses _L Plural awareness via simple conditional.
    wxString summary = wxString::Format(_L("Design vs device:  %d perfect, %d tunable, %d broken"),
                                        roll.perfect, roll.tunable, roll.broken);
    auto* sum_label = new wxStaticText(m_panel_fulfilment, wxID_ANY, summary);
    sum_label->SetBackgroundColour(content_bg);
    // Colour the summary by worst state (red/yellow/green) for glanceability.
    const wxColour sum_color = roll.broken > 0 ? wxColour(198, 80, 80)
                             : roll.tunable > 0 ? wxColour(200, 160, 60)
                                                : wxColour(80, 160, 90);
    sum_label->SetForegroundColour(sum_color);
    sizer->Add(sum_label, 0, wxALL, FromDIP(8));

    // Per-intent rows (single canvas, indexed by design intent — PRD §5.3).
    auto* grid = new wxFlexGridSizer(1, FromDIP(2), FromDIP(4));
    for (const FulfillmentEntry& e : m_store.entries())
        add_fulfilment_row(grid, e);
    sizer->Add(grid, 0, wxEXPAND | wxLEFT | wxRIGHT, FromDIP(8));

    m_panel_fulfilment->SetSizer(sizer, true);
    m_panel_fulfilment->Layout();
    Layout();
}

void DeviceFilamentZone::add_fulfilment_row(wxFlexGridSizer* grid, const FulfillmentEntry& e)
{
    const bool is_dark = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);

    // Glyph + colour for health (PRD §12.5: shape+colour redundancy, not colour-only).
    const char* glyph;
    wxColour    glyph_color;
    switch (e.health) {
        case HealthState::Perfect:  glyph = "\xE2\x9C\x93"; /* ✓ */ glyph_color = wxColour(80, 160, 90); break;
        case HealthState::Tunable:  glyph = "~";             glyph_color = wxColour(200, 160, 60); break;
        default:                    glyph = "\xE2\x9C\x97"; /* ✗ */ glyph_color = wxColour(198, 80, 80); break;
    }

    auto* row = new wxPanel(m_panel_fulfilment, wxID_ANY);
    row->SetBackgroundColour(content_bg);
    auto* row_sizer = new wxBoxSizer(wxHORIZONTAL);

    // Design colour swatch (labelled by 1-based extruder index, like design side).
    std::string swatch_label = std::to_string(e.design_extruder + 1);
    std::string icon_color = e.design_color.empty() ? (is_dark ? "#646468" : "#C8C8C8") : e.design_color;
    auto* swatch = new wxBitmapButton(row, wxID_ANY, wxNullBitmap, wxDefaultPosition,
                                      wxSize(FromDIP(24), FromDIP(16)), wxBORDER_NONE);
    swatch->SetBitmap(*get_extruder_color_icon(icon_color, swatch_label, FromDIP(24), FromDIP(16)));
    swatch->SetBackgroundColour(content_bg);

    // Type token.
    std::string type_str = e.design_type.empty() ? "?" : e.design_type;

    // Plan description (human language — PRD §5 "gaps spoken").
    wxString plan;
    if (e.kind == PlanKind::Direct) {
        plan = wxString::Format(_L("direct match (slot %d)"), e.direct_slot);
    } else if (e.kind == PlanKind::Synthesised) {
        plan = wxString::Format(_L("mix slot %d + %d @ %d%%"), e.synth_slot_a, e.synth_slot_b, e.synth_ratio_b_percent);
    } else {
        plan = _L("no same-type stock — type gap");
    }

    auto* status = new wxStaticText(row, wxID_ANY, wxString::FromUTF8(glyph));
    status->SetForegroundColour(glyph_color);
    status->SetBackgroundColour(content_bg);
    auto* type_label = new Label(row, wxString::FromUTF8(type_str), LB_PROPAGATE_MOUSE_EVENT);
    type_label->SetBackgroundColour(content_bg);
    auto* plan_label = new wxStaticText(row, wxID_ANY, plan);
    plan_label->SetBackgroundColour(content_bg);

    row_sizer->Add(swatch, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(6));
    row_sizer->Add(status, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(4));
    row_sizer->Add(type_label, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(6));
    row_sizer->Add(plan_label, 1, wxALIGN_CENTER_VERTICAL);
    row->SetSizer(row_sizer);

    grid->Add(row, 0, wxEXPAND | wxBOTTOM, FromDIP(3));
}

void DeviceFilamentZone::add_tray_item(wxFlexGridSizer* grid, const std::string& tray_name,
                                       const std::string& filament_type, const std::string& color_hex, bool exists)
{
    const bool   is_dark = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);

    // Decide display color & label by state (see plan's three-state handling):
    //  1. !exists            -> empty slot, grey block + "Empty"
    //  2. exists but no type -> loaded but RFID not resolved, real color (or grey) + "Unknown"
    //  3. otherwise          -> real color + type abbreviation
    std::string icon_color;
    std::string type_label = filament_type;
    if (!exists) {
        icon_color = is_dark ? "#646468" : "#C8C8C8";
        type_label = "Empty";
    } else {
        // filament_colour is stored as "#RRGGBB"; get_extruder_color_icon wants a wxColor-parseable string.
        icon_color = color_hex.empty() ? (is_dark ? "#646468" : "#C8C8C8") : color_hex;
        if (type_label.empty())
            type_label = "Unknown";
    }
    // The color swatch label shows the slot id (A1, Ext, ...) like the design side does.
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
