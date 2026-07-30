#ifndef slic3r_GUI_DeviceFilamentZone_hpp_
#define slic3r_GUI_DeviceFilamentZone_hpp_

#include <wx/panel.h>

#include "Fulfillment/FulfillmentStore.hpp"

class ScalableButton;
class StaticBox;
class wxFlexGridSizer;
class wxStaticText;

namespace Slic3r {
namespace GUI {

// Read-only panel that mirrors what the selected device physically has loaded,
// AND shows the derived "fulfilment" health: how each design intent (colour ×
// type) can be realised against this device's stock.
//
// Consumes PresetBundle::filament_ams_list (populated by Sidebar::load_ams_list)
// and FulfillmentStore (the derived plan). The refresh button only re-reads
// device state (load_ams_list) — it never touches the design-side filaments
// (use the Filaments section's own Sync button for a destructive sync_ams_list).
// The Match button solves the store against real device stock — also design-safe.
class DeviceFilamentZone : public wxPanel
{
public:
    // `store` is owned by the Sidebar; this panel reads/mutates it but does not
    // own it. Mutations here are class-A (Fulfillment only, never Design).
    explicit DeviceFilamentZone(wxWindow* parent, FulfillmentStore& store);

    // Re-read preset_bundle->filament_ams_list and rebuild the tray rows, then
    // refresh the fulfilment summary. Safe to call repeatedly.
    void refresh();

    // Re-render the fulfilment summary/detail from the store (no re-solve).
    // Called after store.solve() or after design/device-change marks stale.
    void refresh_fulfilment();

private:
    // Builds one tray row for a single filament_ams_list entry.
    void        add_tray_item(wxFlexGridSizer* grid, const std::string& tray_name,
                              const std::string& filament_type, const std::string& color_hex, bool exists);

    // Builds one fulfilment row from a FulfillmentEntry (design intent → plan).
    void        add_fulfilment_row(wxFlexGridSizer* grid, const FulfillmentEntry& e);

    FulfillmentStore& m_store;

    StaticBox*      m_panel_title       = nullptr;
    ScalableButton* m_refresh_btn       = nullptr;
    ScalableButton* m_match_btn         = nullptr; // solves store against device stock
    wxPanel*        m_panel_content     = nullptr; // device tray rows
    wxPanel*        m_panel_fulfilment  = nullptr; // design-intent → plan rows
    wxStaticText*   m_health_summary    = nullptr; // "3 perfect / 1 tunable / 1 broken"
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_DeviceFilamentZone_hpp_

