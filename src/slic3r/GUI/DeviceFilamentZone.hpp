#ifndef slic3r_GUI_DeviceFilamentZone_hpp_
#define slic3r_GUI_DeviceFilamentZone_hpp_

#include <wx/panel.h>

class ScalableButton;
class StaticBox;
class wxFlexGridSizer;

namespace Slic3r {
namespace GUI {

// Read-only panel that mirrors what the selected device physically has loaded.
// Consumes PresetBundle::filament_ams_list (populated by Sidebar::load_ams_list,
// which is fed by MQTT push / device selection). The refresh button only re-reads
// that list -- it never touches the design-side filaments (use the Filaments
// section's own Sync button for a destructive sync_ams_list).
class DeviceFilamentZone : public wxPanel
{
public:
    explicit DeviceFilamentZone(wxWindow* parent);

    // Re-read preset_bundle->filament_ams_list and rebuild the tray rows.
    // Safe to call repeatedly: get_extruder_color_icon() is backed by a static
    // BitmapCache keyed by color+label+size, so the wxBitmap copies we hold here
    // do not accumulate across refreshes.
    void refresh();

private:
    // Builds one tray row for a single filament_ams_list entry.
    // tray_name e.g. "A1".."A4", "B1".. ; "Ext" for the virtual tray.
    void        add_tray_item(wxFlexGridSizer* grid, const std::string& tray_name,
                              const std::string& filament_type, const std::string& color_hex, bool exists);

    StaticBox*      m_panel_title   = nullptr;
    ScalableButton* m_refresh_btn   = nullptr;
    wxPanel*        m_panel_content = nullptr;
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_DeviceFilamentZone_hpp_
