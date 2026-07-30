#ifndef slic3r_GUI_DeviceFilamentZone_hpp_
#define slic3r_GUI_DeviceFilamentZone_hpp_

#include <wx/panel.h>

class ScalableButton;
class StaticBox;
class wxFlexGridSizer;
class wxStaticText;

namespace Slic3r {
namespace GUI {

// Read-only panel that mirrors what the selected device physically has loaded.
//
// This is the PHYSICAL LAYER's UI (PRD §8): it only shows AMS stock. The
// derived fulfilment canvas lives in the separate FulfillmentPanel. The refresh
// button only re-reads device state (load_ams_list) — it never touches the
// design-side filaments (use the Filaments section's own Sync button for a
// destructive sync_ams_list).
//
// NOTE: an earlier version of this class also hosted the fulfilment canvas +
// Match button; that was split out (round-4) so each panel has one job.
class DeviceFilamentZone : public wxPanel
{
public:
    explicit DeviceFilamentZone(wxWindow* parent);

    // Re-read preset_bundle->filament_ams_list and rebuild the tray rows.
    void refresh();

private:
    // Builds one tray row for a single filament_ams_list entry.
    void add_tray_item(wxFlexGridSizer* grid, const std::string& tray_name,
                       const std::string& filament_type, const std::string& color_hex, bool exists);

    StaticBox*      m_panel_title   = nullptr;
    ScalableButton* m_refresh_btn   = nullptr;
    wxPanel*        m_panel_content = nullptr; // device tray rows
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_DeviceFilamentZone_hpp_

