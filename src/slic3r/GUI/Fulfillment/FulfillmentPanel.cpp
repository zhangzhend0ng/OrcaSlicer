#include "FulfillmentPanel.hpp"

#include "FulfillmentSnapshots.hpp"
#include "../GUI_App.hpp"
#include "../Plater.hpp"
#include "../MainFrame.hpp"
#include "../MixedColorMatchHelpers.hpp"
#include "../MixedFilamentDialog.hpp"    // reuse the existing mix editor (anti-reinvention)
#include "../filamentsync/MachineFilamentPicker.hpp" // reuse the sync dialog's filament picker
#include "../DeviceManager.hpp"
#include "../MsgDialog.hpp"
#include "../Widgets/StaticBox.hpp"
#include "../Widgets/Label.hpp"
#include "../Widgets/Button.hpp"
#include "../Widgets/SegmentedToggle.hpp" // Design/Expected view switch
#include "../wxExtensions.hpp"           // get_extruder_color_icon, ScalableButton

#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/PrintConfig.hpp"
#include "libslic3r/MixedFilament.hpp"

#include <wx/sizer.h>
#include <wx/stattext.h>
#include <wx/bmpbuttn.h>
#include <wx/colour.h>
#include <algorithm>
#include <cmath>

#include <boost/algorithm/string/predicate.hpp> // boost::iequals — length-safe
                                                // case-insensitive compare. The
                                                // hand-rolled std::equal(first,last,
                                                // other.begin(),pred) form reads
                                                // `other` up to (last-first) chars
                                                // and goes out of bounds when other
                                                // is shorter (UB). boost::iequals
                                                // checks both lengths. MUST stay in
                                                // sync with FulfillmentStore.cpp:131
                                                // (the solver's same-type filter).

namespace Slic3r {
namespace GUI {

FulfillmentPanel::FulfillmentPanel(wxWindow* parent, FulfillmentStore& store)
    : wxPanel(parent, wxID_ANY), m_store(store)
{
    const bool     is_dark    = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);
    const wxColour title_bg   = wxColour(248, 248, 248); // mirrors Sidebar title_bg

    SetBackgroundColour(content_bg);

    auto* root = new wxBoxSizer(wxVERTICAL);

    // --- Title bar ---
    m_panel_title = new StaticBox(this, wxID_ANY, wxDefaultPosition, wxDefaultSize, wxTAB_TRAVERSAL | wxBORDER_NONE);
    m_panel_title->SetBackgroundColor(title_bg);
    m_panel_title->SetBackgroundColor2(0xF1F1F1);
    m_panel_title->SetMinSize(wxSize(-1, FromDIP(30)));
    m_panel_title->SetMaxSize(wxSize(-1, FromDIP(30)));

    auto* title_icon  = new ScalableButton(m_panel_title, wxID_ANY, "filament");
    auto* title_label = new Label(m_panel_title, _L("Fulfillment Plan"), LB_PROPAGATE_MOUSE_EVENT);

    m_match_btn = new ScalableButton(m_panel_title, wxID_ANY, "sync_filament");
    m_match_btn->SetToolTip(_L("Match design colours to this device's stock (read-only, never changes your design)"));

    // Expected View toggle: render the 3D model in realised colours (what it'll
    // actually print as). Design-safe — render-only, never writes design.
    // SegmentedToggle gives clear Design/Expected visual state (like Global/Object).
    m_view_toggle = new SegmentedToggle(m_panel_title, {_L("Design"), _L("Expected")}, /*selectedIndex=*/0);
    m_view_toggle->SetToolTip(_L("Switch between Design colours (what you chose) and Expected colours (what will actually print)."));

    auto* h_title     = new wxBoxSizer(wxHORIZONTAL);
    auto* white_left  = new wxPanel(m_panel_title, wxID_ANY, wxDefaultPosition, wxSize(FromDIP(SidebarProps::ContentMargin()), -1));
    white_left->SetBackgroundColour(*wxWHITE);
    h_title->Add(white_left, 0, wxEXPAND, 0);
    h_title->Add(title_icon, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, FromDIP(SidebarProps::TitlebarMargin()));
    h_title->AddSpacer(FromDIP(SidebarProps::ElementSpacing()));
    h_title->Add(title_label, 0, wxALIGN_CENTER_VERTICAL);
    h_title->AddStretchSpacer();
    h_title->Add(m_view_toggle, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(4));
    h_title->Add(m_match_btn, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(8));
    auto* white_right = new wxPanel(m_panel_title, wxID_ANY, wxDefaultPosition, wxSize(FromDIP(SidebarProps::ContentMargin()), -1));
    white_right->SetBackgroundColour(*wxWHITE);
    h_title->Add(white_right, 0, wxEXPAND, 0);
    m_panel_title->SetSizer(h_title);
    m_panel_title->Layout();

    // --- Canvas content (summary + per-intent rows) ---
    m_panel_content = new wxPanel(this, wxID_ANY);
    m_panel_content->SetBackgroundColour(content_bg);
    m_panel_content->SetSizer(new wxBoxSizer(wxVERTICAL));

    m_match_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) { on_match(); });

    m_view_toggle->bindSelectionCallback([this](int index) {
        // index 0 = Design, 1 = Expected
        Plater* plater = wxGetApp().plater();
        if (!plater) return;
        plater->set_expected_view(index == 1);
        if (index == 1 && !m_store.has_solved()) {
            MessageDialog dlg(this, _L("Expected View is on, but no match has been run yet. Press Match to see how your colours will actually print."),
                              _L("Expected View"), wxOK | wxICON_INFORMATION);
            dlg.ShowModal();
        }
    });

    root->AddSpacer(FromDIP(8));
    root->Add(m_panel_title, 0, wxEXPAND, 0);
    root->AddSpacer(FromDIP(8));
    root->Add(m_panel_content, 0, wxEXPAND, 0);
    root->AddSpacer(FromDIP(8));

    SetSizer(root);
    Layout();
}

void FulfillmentPanel::on_match()
{
    PresetBundle* pb = wxGetApp().preset_bundle;
    if (!pb) return;
    auto design = snapshot_design_intent(*pb);
    auto device = snapshot_device_stock(*pb);
    // NOTE: do NOT touch m_health_summary here — it is nullptr until
    // refresh_fulfilment() runs the solved branch and creates it. On the initial
    // (unsolved) display it doesn't exist, so SetLabel would null-deref.
    if (design.empty()) {
        MessageDialog dlg(this, _L("No design filaments to match."), _L("Fulfillment"), wxOK | wxICON_INFORMATION);
        dlg.ShowModal();
        return;
    }
    if (device.empty()) {
        MessageDialog dlg(this, _L("No device filament info. Sync the printer from the Filaments section first, then Match."),
                          _L("Fulfillment"), wxOK | wxICON_INFORMATION);
        dlg.ShowModal();
        return;
    }
    m_store.solve(design, device);
    refresh_fulfilment();
    // If the device snapshot was the offline mock (no printer connected), tell
    // the user the match is against inferred device data, not a live machine —
    // so they know to re-Match once a printer reports the real stock.
    const bool any_mock = std::any_of(device.begin(), device.end(),
                                      [](const PhysicalSlot& s) { return s.is_mock; });
    if (any_mock) {
        // Source-and-action wording (see DeviceFilamentZone refresh): the mock
        // path fires whenever the device reports no filaments — no printer
        // connected, a connected printer that hasn't reported stock yet, or all
        // trays empty. Don't claim "no printer connected"; say where the data
        // came from and how to get the real match.
        MessageDialog dlg(this,
            _L("Device data is an offline mock, inferred from the printer preset, "
               "not read from a connected machine. Sync the printer (or connect one) "
               "and re-run Match to see the real device match."),
            _L("Fulfillment"), wxOK | wxICON_INFORMATION);
        dlg.ShowModal();
    }
    // Guard plater(): null during early init / teardown. The Match button only
    // fires post-init in practice, but the unguarded deref was inconsistent with
    // the guarded pattern used elsewhere in this file (view_toggle callback) and
    // a latent null-deref (UB-2) if a handler ever runs during shutdown.
    if (Plater* plater = wxGetApp().plater()) {
        plater->sidebar().update_fulfillment_health_indicator();
        // If Expected View is active, the 3D model must repaint with the new colours.
        plater->refresh_expected_render();
    }
}

void FulfillmentPanel::sync_view_toggle_to_expected(bool expected)
{
    // setSelected is visual-only (does not fire the callback), so this is safe
    // to call from a path that already set the actual mode (e.g. project reset).
    if (m_view_toggle) m_view_toggle->setSelected(expected ? 1 : 0);
}

void FulfillmentPanel::refresh_fulfilment()
{
    const bool     is_dark    = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);

    m_panel_content->DestroyChildren();
    // DestroyChildren deleted the wxStaticText m_health_summary points at (when
    // the prior render took the solved branch). Null the member so no later code
    // path can dereference a freed widget — a latent use-after-free (lifetime
    // harness UB-4) that the current single-reader flow happens to avoid, but
    // which any future caller or a reordered early-return would trip. It is
    // reassigned in the solved branch below.
    m_health_summary = nullptr;
    auto* sizer = new wxBoxSizer(wxVERTICAL);

    if (!m_store.has_solved()) {
        // No solve yet — neutral hint, no health claim (PRD §12.3).
        auto* hint = new Label(m_panel_content,
            _L("Design colours vs device stock: press Match to check."),
            LB_PROPAGATE_MOUSE_EVENT);
        hint->SetBackgroundColour(content_bg);
        sizer->Add(hint, 0, wxALL, FromDIP(8));
        m_panel_content->SetSizer(sizer, true);
        m_panel_content->Layout();
        Layout();
        return;
    }

    // Summary line (PRD §5.3 global health, §5 gaps spoken).
    const auto roll = m_store.rollup();
    wxString summary = wxString::Format(_L("Design vs device:  %d perfect, %d tunable, %d broken"),
                                        roll.perfect, roll.tunable, roll.broken);
    // PRD §7: after a design/device change the store goes stale — the displayed
    // rows/counts were solved against the PRIOR snapshot, so they may not reflect
    // current reality. The PRD lets recipes wait for the user (no auto-overwrite),
    // but §5 requires the gap to be SPOKEN: without this hint the user could read
    // the rollup as current truth. Append a "stale" marker when has_stale(), so
    // the stats are clearly labelled as pending a re-Match.
    if (m_store.has_stale())
        summary += "  " + _L("(stale — press Match to refresh)");
    m_health_summary = new wxStaticText(m_panel_content, wxID_ANY, summary);
    m_health_summary->SetBackgroundColour(content_bg);
    const wxColour sum_color = roll.broken > 0 ? wxColour(198, 80, 80)
                             : roll.tunable > 0 ? wxColour(200, 160, 60)
                                                : wxColour(80, 160, 90);
    m_health_summary->SetForegroundColour(sum_color);
    sizer->Add(m_health_summary, 0, wxALL, FromDIP(8));

    // Recovery actions (PRD §12.1): reset all, clear all locks.
    bool any_locked = false;
    for (const FulfillmentEntry& e : m_store.entries()) if (e.locked) { any_locked = true; break; }
    auto* action_row    = new wxBoxSizer(wxHORIZONTAL);
    auto* reset_btn     = new Button(m_panel_content, _L("Reset all"));
    reset_btn->SetStyle(ButtonStyle::Confirm, ButtonType::Compact);
    reset_btn->SetToolTip(_L("Discard all manual edits and recompute recipes."));
    reset_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        m_store.reset_all();
        on_match(); // re-solve after reset
    });
    auto* clear_locks_btn = new Button(m_panel_content, _L("Clear locks"));
    clear_locks_btn->SetStyle(ButtonStyle::Confirm, ButtonType::Compact);
    clear_locks_btn->SetToolTip(_L("Unlock every recipe."));
    clear_locks_btn->Enable(any_locked);
    clear_locks_btn->Bind(wxEVT_BUTTON, [this](wxCommandEvent&) {
        m_store.clear_all_locks();
        refresh_fulfilment();
    });
    action_row->Add(reset_btn, 0, wxRIGHT, FromDIP(8));
    action_row->Add(clear_locks_btn, 0);
    sizer->Add(action_row, 0, wxLEFT | wxRIGHT | wxBOTTOM, FromDIP(8));

    // Per-intent rows (single canvas, indexed by design intent — PRD §5.3).
    auto* grid = new wxFlexGridSizer(1, FromDIP(2), FromDIP(4));
    for (const FulfillmentEntry& e : m_store.entries())
        add_fulfilment_row(grid, e);
    sizer->Add(grid, 0, wxEXPAND | wxLEFT | wxRIGHT, FromDIP(8));

    m_panel_content->SetSizer(sizer, true);
    m_panel_content->Layout();
    Layout();
    // Notify the parent (sidebar scrolled area) to re-layout — without this the
    // new rows are added but the scrolled sizer doesn't adjust its height, so
    // the content is invisible until a resize/paint forces it (the 'only shows
    // after dragging' symptom). This mirrors how on_filaments_change etc. call
    // scrolled->Layout() / GetParent()->Layout().
    wxWindow* parent = GetParent();
    if (parent) {
        parent->Layout();
        // FitInside handles scrolled windows' virtual size recalculation.
        if (auto* sw = wxDynamicCast(parent, wxScrolledWindow)) sw->FitInside();
    }
}

void FulfillmentPanel::add_fulfilment_row(wxFlexGridSizer* grid, const FulfillmentEntry& e)
{
    const bool     is_dark    = wxGetApp().dark_mode();
    const wxColour content_bg = is_dark ? wxColour(45, 45, 49) : wxColour(255, 255, 255);

    // Glyph + colour for health (PRD §12.5: shape+colour redundancy).
    const char* glyph;
    wxColour    glyph_color;
    switch (e.health) {
        case HealthState::Perfect:  glyph = "\xE2\x9C\x93"; /* ✓ */ glyph_color = wxColour(80, 160, 90); break;
        case HealthState::Tunable:  glyph = "~";             glyph_color = wxColour(200, 160, 60); break;
        default:                    glyph = "\xE2\x9C\x97"; /* ✗ */ glyph_color = wxColour(198, 80, 80); break;
    }

    auto* row      = new wxPanel(m_panel_content, wxID_ANY);
    row->SetBackgroundColour(content_bg);
    auto* row_sizer = new wxBoxSizer(wxHORIZONTAL);

    // Design colour swatch (1-based extruder label, like the design side).
    std::string swatch_label = std::to_string(e.design_extruder + 1);
    std::string icon_color   = e.design_color.empty() ? (is_dark ? "#646468" : "#C8C8C8") : e.design_color;
    auto* swatch = new wxBitmapButton(row, wxID_ANY, wxNullBitmap, wxDefaultPosition,
                                      wxSize(FromDIP(24), FromDIP(16)), wxBORDER_NONE);
    swatch->SetBitmap(*get_extruder_color_icon(icon_color, swatch_label, FromDIP(24), FromDIP(16)));
    swatch->SetBackgroundColour(content_bg);

    // Expected/realised colour swatch — the OTHER half of the side-by-side
    // comparison (the user "needs to see the original design" next to what it'll
    // actually print as). Source: recipe.preview_color (set by solve for Direct &
    // Synthesised); grey + "–" when unmet (no realisation exists). No GL render
    // needed — the predicted colour is already a recipe output.
    std::string expected_hex;
    std::string expected_label;
    // Show the realised colour only when the recipe is valid AND its ΔE is finite
    // (a freshly hand-edited recipe has delta_e=inf until re-solved, so its stored
    // preview_color is stale — showing it would contradict the new recipe).
    if (e.recipe.valid && e.recipe.preview_color.IsOk() && std::isfinite(e.recipe.delta_e)) {
        expected_hex   = e.recipe.preview_color.GetAsString(wxC2S_HTML_SYNTAX).ToStdString();
        expected_label = "~"; // marks "this is the realised/expected colour"
    } else {
        expected_hex   = is_dark ? "#646468" : "#C8C8C8";
        expected_label = "-";
    }
    auto* expected_swatch = new wxBitmapButton(row, wxID_ANY, wxNullBitmap, wxDefaultPosition,
                                               wxSize(FromDIP(24), FromDIP(16)), wxBORDER_NONE);
    expected_swatch->SetBitmap(*get_extruder_color_icon(expected_hex, expected_label, FromDIP(24), FromDIP(16)));
    expected_swatch->SetBackgroundColour(content_bg);
    expected_swatch->SetToolTip(_L("Expected realised colour (what will actually print)."));

    // Arrow between the two swatches — makes the design→expected comparison explicit.
    auto* arrow = new wxStaticText(row, wxID_ANY, L"\u2192");
    arrow->SetBackgroundColour(content_bg);

    // Type token.
    std::string type_str = e.design_type.empty() ? "?" : e.design_type;

    // Plan description (human language — PRD §5).
    wxString plan;
    // Resolve a recipe component to a human-readable slot label. Prefer the
    // tray_name (1-based, matches DeviceFilamentZone and the design swatches);
    // fall back to ams_key+1 when tray_names weren't captured (e.g. an entry
    // serialised before the tray_names field existed), and finally "?" when the
    // component id is out of range. This deliberately does NOT render the raw
    // 0-based ams_key, which made the first device filament read "slot 0" while
    // every other view labelled it "1".
    auto label_for = [&](unsigned int component_id) -> wxString {
        if (component_id < 1 || component_id > e.component_ams_keys.size()) return "?";
        const size_t idx = component_id - 1;
        if (idx < e.component_tray_names.size() && !e.component_tray_names[idx].empty())
            return wxString::FromUTF8(e.component_tray_names[idx]);
        return wxString::Format("%d", e.component_ams_keys[idx] + 1);
    };
    if (e.kind == PlanKind::Direct) {
        plan = wxString::Format(_L("direct match (slot %s)"), label_for(e.recipe.component_a));
    } else if (e.kind == PlanKind::Synthesised) {
        // Cycle mode (shape D): manual_pattern is non-empty. Its semantics differ
        // from a weighted blend — it's a layer-cadence sequence of filament
        // switches (e.g. "12" = alternate slot 1/2, "13" = alternate 1/3). Show
        // the cycle pattern explicitly rather than the misleading "mix X + Y @ Z%"
        // (which implies a ratio blend). Tokens 1/2 are relative to component_a/b.
        if (!e.recipe.manual_pattern.empty()) {
            plan = wxString::Format(_L("cycle %s (slot %s + %s)"),
                                    wxString::FromUTF8(e.recipe.manual_pattern),
                                    label_for(e.recipe.component_a), label_for(e.recipe.component_b));
        } else {
            // A multi-colour mix (3+) stores its full component list + per-component
            // weights in gradient_component_ids / gradient_component_weights
            // (palette-local, parallel — same space as component_a/b, verified against
            // MixedFilamentDialog::collect_result). The legacy two-colour text
            // ("mix slot X + Y @ Z%") only renders the primary pair and silently
            // dropped the third+ colour, so the UI read as two-colour even after the
            // slice path was fixed (round-21). When the gradient list has 3+ entries,
            // render the full recipe: "mix slot X/Y/Z @ a%/b%/c%". Falls back to the
            // two-colour form for plain 2-component blends (incl. the {a,b} marker
            // dialog stores for 2-colour gradient mode, where weights is empty).
            const auto gids = MixedFilamentManager::decode_gradient_component_ids(e.recipe.gradient_component_ids, 0);
        if (gids.size() >= 3) {
            // Weights are "/"-separated percents parallel to gids; parse them
            // manually (decode_gradient_component_weights is file-static in
            // MixedFilament.cpp). Fall back to mix_b_percent split if absent.
            std::vector<int> gw;
            gw.reserve(gids.size());
            if (!e.recipe.gradient_component_weights.empty()) {
                size_t start = 0;
                for (size_t pos = 0; pos <= e.recipe.gradient_component_weights.size(); ++pos) {
                    if (pos == e.recipe.gradient_component_weights.size() || e.recipe.gradient_component_weights[pos] == '/') {
                        try { gw.push_back(std::stoi(e.recipe.gradient_component_weights.substr(start, pos - start))); }
                        catch (...) { /* malformed weight token — leave absent */ }
                        start = pos + 1;
                    }
                }
            }
            wxString slots, pcts;
            for (size_t i = 0; i < gids.size(); ++i) {
                const wxString lbl = label_for(gids[i]);
                slots += (i ? "/" : "") + lbl;
                if (i < gw.size()) pcts += (i ? "/" : "") + wxString::Format("%d%%", gw[i]);
            }
            if (pcts.empty())
                plan = wxString::Format(_L("mix slot %s"), slots);
            else
                plan = wxString::Format(_L("mix slot %s @ %s"), slots, pcts);
        } else {
            plan = wxString::Format(_L("mix slot %s + %s @ %d%%"),
                                    label_for(e.recipe.component_a), label_for(e.recipe.component_b),
                                    e.recipe.mix_b_percent);
        }
        } // end non-cycle (gradient/2-colour) branch
    } else {
        plan = _L("no same-type stock — type gap");
    }
    // Quantify the colour gap (PRD §5: speak the gap, with a number). Shown only
    // when finite — infinity (unmet / just-edited) means "not computable", and
    // printing it would mislead.
    if (std::isfinite(e.recipe.delta_e)) {
        plan += wxString::Format("  (\u0394E %.1f)", e.recipe.delta_e);
    }

    const bool can_act = (e.kind != PlanKind::Unmet);

    // "Select physical" — pops MachineFilamentPicker (the SAME picker the sync
    // dialog uses) so the user can choose a device filament to use directly
    // (Direct match) instead of the auto-computed recipe. This is the "use a
    // physical filament" option the user asked for.
    auto* phys_btn = new ScalableButton(row, wxID_ANY, "edit");
    phys_btn->SetBackgroundColour(content_bg);
    phys_btn->SetToolTip(_L("Choose a device filament to use for this colour."));
    phys_btn->Enable(can_act);
    phys_btn->Bind(wxEVT_BUTTON, [this, e, can_act, phys_btn](wxCommandEvent&) {
        if (!can_act) return;
        PresetBundle* pb = wxGetApp().preset_bundle;
        if (!pb) return;
        // Build the machine filament list (same as sync dialog / device zone).
        std::vector<FilamentData> machine_list;
        build_machine_filament_list(pb, machine_list);
        if (machine_list.empty()) return;

        // Filter to same-type filaments only. Case-insensitive type match via
        // boost::iequals (length-safe). The std::equal(first,last,other.begin(),pred)
        // form previously used here reads `other` up to (last-first) chars and goes
        // out of bounds when e.design_type is shorter than fd.m_type (UB) — the same
        // pitfall FulfillmentStore.cpp:130-132 calls out. These two filters are
        // orthogonal to the solver's: solver filters design-type-vs-slot at solve
        // time; this filters again at dialog-open time against the live machine list.
        std::vector<FilamentData> same_type_list;
        for (const FilamentData& fd : machine_list) {
            if (is_none_filament(fd)) continue;
            if (boost::iequals(fd.m_type, e.design_type))
                same_type_list.push_back(fd);
        }
        if (same_type_list.empty()) return;

        unsigned int cur_idx = 0;
        if (e.recipe.valid && e.recipe.component_a >= 1 && e.recipe.component_a <= same_type_list.size())
            cur_idx = e.recipe.component_a - 1;

        auto* picker = new MachineFilamentPicker(wxGetApp().mainframe, same_type_list, cur_idx);
        picker->bindSelectionCallback([this, design_extruder = e.design_extruder,
                                       design_color = e.design_color](const FilamentData& data) {
            // User picked a physical filament → set Direct match with full
            // colour/delta_e/health update + force UI repaint. Pass the 1-based
            // tray label so the row reads "slot 1" (matching DeviceFilamentZone),
            // not the raw 0-based ams_key.
            m_store.set_direct_with_color(design_extruder, static_cast<int>(data.m_index),
                                          wxColour(data.m_color.PrimaryColor()), design_color,
                                          std::to_string(data.m_index + 1));
            refresh_fulfilment();
            if (Plater* plater = wxGetApp().plater()) {
                plater->sidebar().update_fulfillment_health_indicator();
                plater->refresh_expected_render();
            }
        });
        wxPoint pos = phys_btn->GetScreenPosition();
        pos.y += phys_btn->GetSize().y;
        picker->popupAt(pos);
    });

    // "Mix" — opens MixedFilamentDialog for fine-tuning the mix recipe (ratio,
    // gradient, pattern). Separate from "select physical" so the user has a
    // clear choice between "use a physical filament directly" and "mix".
    auto* mix_btn = new ScalableButton(row, wxID_ANY, "menu_filament");
    mix_btn->SetBackgroundColour(content_bg);
    mix_btn->SetToolTip(_L("Edit the mix recipe for this colour."));
    mix_btn->Enable(can_act);
    mix_btn->Bind(wxEVT_BUTTON, [this, e, can_act](wxCommandEvent&) {
        if (!can_act) return;
        PresetBundle* pb = wxGetApp().preset_bundle;
        if (!pb) return;
        auto device = snapshot_device_stock(*pb);

        std::vector<std::string> palette;
        std::vector<int>         palette_ams_keys;
        std::vector<std::string> palette_tray_names;
        for (const PhysicalSlot& s : device) {
            if (!s.exists) continue;
            if (boost::iequals(s.type, e.design_type)) {
                palette.push_back(s.color.GetAsString(wxC2S_HTML_SYNTAX).ToStdString());
                palette_ams_keys.push_back(s.ams_key);
                palette_tray_names.push_back(s.tray_name);
            }
        }
        if (palette.empty()) return;
        if (palette.size() < 2) { palette.push_back("#C8C8C8"); palette_ams_keys.push_back(-1); palette_tray_names.emplace_back("?"); }

        Slic3r::MixedFilament seed;
        seed.component_a              = e.recipe.component_a;
        seed.component_b              = e.recipe.component_b;
        seed.mix_b_percent            = e.recipe.mix_b_percent;
        seed.manual_pattern           = e.recipe.manual_pattern;
        seed.gradient_component_ids    = e.recipe.gradient_component_ids;
        seed.gradient_component_weights= e.recipe.gradient_component_weights;
        // Restore the g-code-relevant fields so the dialog reopens in the mode
        // that originally produced this recipe. Without distribution_mode the
        // dialog constructor's heuristic maps a 3-colour RATIO recipe to MATCH
        // (gradient_component_ids non-empty + Simple), and a re-save would
        // corrupt the recipe. Mirrors apply_edited_recipe's write side below.
        seed.distribution_mode        = e.recipe.distribution_mode;
        seed.gradient_enabled         = e.recipe.gradient_enabled;
        seed.gradient_start           = e.recipe.gradient_start;
        seed.gradient_end             = e.recipe.gradient_end;
        seed.ui_mode                  = e.recipe.ui_mode;

        MixedFilamentDialog dlg(wxGetApp().mainframe, palette, seed);
        if (dlg.ShowModal() != wxID_OK) return;
        const Slic3r::MixedFilament& r = dlg.GetResult();
        m_store.apply_edited_recipe(e.design_extruder, r.component_a, r.component_b, r.mix_b_percent,
                                    r.manual_pattern, r.gradient_component_ids, r.gradient_component_weights,
                                    r.distribution_mode, r.gradient_enabled, r.gradient_start, r.gradient_end,
                                    r.ui_mode,
                                    palette_ams_keys, palette_tray_names, palette);
        refresh_fulfilment();
    });

    // Lock (🔒) — class-A edit (PRD §4.3, §6).
    auto* lock_btn = new ScalableButton(row, wxID_ANY, "lock_normal");
    lock_btn->SetBackgroundColour(content_bg);
    lock_btn->SetToolTip(e.locked ? _L("Locked — recipe kept on recompute. Click to unlock.")
                                  : _L("Lock this recipe (keep on recompute)."));
    lock_btn->Enable(can_act);
    lock_btn->Bind(wxEVT_BUTTON, [this, design_extruder = e.design_extruder](wxCommandEvent&) {
        m_store.toggle_lock(design_extruder);
        refresh_fulfilment();
    });

    auto* status     = new wxStaticText(row, wxID_ANY, wxString::FromUTF8(glyph));
    status->SetForegroundColour(glyph_color);
    status->SetBackgroundColour(content_bg);
    auto* type_label = new Label(row, wxString::FromUTF8(type_str), LB_PROPAGATE_MOUSE_EVENT);
    type_label->SetBackgroundColour(content_bg);
    auto* plan_label = new wxStaticText(row, wxID_ANY, plan);
    plan_label->SetBackgroundColour(content_bg);

    row_sizer->Add(swatch, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(2));
    row_sizer->Add(arrow, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(2));
    row_sizer->Add(expected_swatch, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(6));
    row_sizer->Add(status, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(4));
    row_sizer->Add(type_label, 0, wxALIGN_CENTER_VERTICAL | wxRIGHT, FromDIP(6));
    row_sizer->Add(plan_label, 1, wxALIGN_CENTER_VERTICAL);
    row_sizer->Add(phys_btn, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, FromDIP(4));
    row_sizer->Add(mix_btn, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, FromDIP(2));
    row_sizer->Add(lock_btn, 0, wxALIGN_CENTER_VERTICAL | wxLEFT, FromDIP(2));
    row->SetSizer(row_sizer);

    // Resolve (PRD §5.2.1): a broken (type-gap) row is clickable to surface the
    // two resolution paths. Class A = physical (load the filament); class B =
    // design (change this intent's type). Class B is NOT performed in-canvas —
    // it points the user to the Filaments list (Design View), per §5.2.1's rule
    // that an intent-changing action must leave the canvas. No silent design write.
    if (e.kind == PlanKind::Unmet) {
        row->SetCursor(wxCursor(wxCURSOR_HAND));
        row->Bind(wxEVT_LEFT_UP, [this, design_extruder = e.design_extruder,
                                  type_str = e.design_type](wxMouseEvent&) {
            const wxString type_wxs = type_str.empty() ? _L("(unknown type)") : wxString::FromUTF8(type_str);
            wxString msg = wxString::Format(
                _L("Design colour #%d needs %s, but no matching filament is loaded on this device."),
                design_extruder + 1, type_wxs);
            msg += "\n\n" + _L("Options:");
            msg += "\n\u2022 " + _L("Load the filament into the device, then click Match again.");
            msg += "\n\u2022 " + _L("Or change this design colour's filament type in the Filaments list above.");
            MessageDialog dlg(this, msg, _L("Cannot fulfil this colour"), wxOK | wxICON_INFORMATION);
            dlg.ShowModal();
        });
    }

    grid->Add(row, 0, wxEXPAND | wxBOTTOM, FromDIP(3));
}

} // namespace GUI
} // namespace Slic3r
