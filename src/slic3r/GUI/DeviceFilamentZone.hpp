#ifndef slic3r_GUI_DeviceFilamentZone_hpp_
#define slic3r_GUI_DeviceFilamentZone_hpp_

#include <wx/panel.h>
#include <wx/timer.h>

namespace Slic3r { namespace GUI { struct FilamentData; } }

class ScalableButton;
class StaticBox;
class wxFlexGridSizer;

namespace Slic3r {
namespace GUI {

// Read-only panel that mirrors what the selected device physically has loaded.
//
// This is the PHYSICAL LAYER's UI (PRD §8): it only shows AMS stock. The
// derived fulfilment canvas lives in the separate FulfillmentPanel. The refresh
// button only re-reads device state (load_ams_list) — it never touches the
// design-side filaments.
//
// A timer auto-refreshes when device filament data changes (e.g. after a WCP
// sync populates m_connect_machine_info_list), so the user sees real device
// stock without manual clicks.
class DeviceFilamentZone : public wxPanel
{
public:
    explicit DeviceFilamentZone(wxWindow* parent);

    // Re-read device stock via build_machine_filament_list and rebuild the rows.
    void refresh();

private:
    // Builds one tray row from a device FilamentData (brand/model name + colour).
    void add_tray_item(wxFlexGridSizer* grid, const std::string& slot_label, const FilamentData& fd);

    // Timer callback: check if device stock changed, auto-refresh if so.
    void on_timer(wxTimerEvent& evt);

    StaticBox*      m_panel_title      = nullptr;
    ScalableButton* m_refresh_btn      = nullptr;
    wxPanel*        m_panel_content    = nullptr; // device tray rows
    wxTimer         m_auto_timer;
    size_t          m_last_stock_count = size_t(-1); // last seen device stock size
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_DeviceFilamentZone_hpp_
