#ifndef slic3r_GUI_FulfillmentPanel_hpp_
#define slic3r_GUI_FulfillmentPanel_hpp_

// The FulfillmentPanel is the standalone "canvas" for the Expected-View side of
// the dual-view model (PRD §5.2/§5.3). It owns the fulfilment display: a Match
// trigger, a colour-coded global health summary, and per-design-intent rows
// (the single canvas indexed by design intent — not a split screen).
//
// It is deliberately SEPARATE from DeviceFilamentZone (which shows the physical
// stock, PRD §8): the canvas is the Fulfilment Layer's UI; the device zone is
// the Physical Layer's UI. They share the FulfillmentStore but not a panel.
//
// All writes go to the FulfillmentStore (class-A edits); the Design Layer is
// never touched (PRD §1-3).

#include <wx/panel.h>

#include "FulfillmentStore.hpp"

class ScalableButton;
class StaticBox;
class SegmentedToggle;
class wxFlexGridSizer;
class wxStaticText;

namespace Slic3r {
namespace GUI {

class FulfillmentPanel : public wxPanel
{
public:
    explicit FulfillmentPanel(wxWindow* parent, FulfillmentStore& store);

    // Re-render the canvas from the store (no re-solve). Call after solve or
    // after a design/device change marked the plan stale.
    void refresh_fulfilment();

private:
    // Solve the store against live Design + Physical snapshots (read-only),
    // then refresh. Bound to the Match button.
    void on_match();
    // Build one canvas row from a FulfillmentEntry.
    void add_fulfilment_row(wxFlexGridSizer* grid, const FulfillmentEntry& e);

    FulfillmentStore& m_store;

    StaticBox*      m_panel_title      = nullptr;
    ScalableButton* m_match_btn        = nullptr; // solve against device stock
    SegmentedToggle* m_view_toggle     = nullptr; // Design/Expected view switch
    wxPanel*        m_panel_content    = nullptr; // summary + per-intent rows
    wxStaticText*   m_health_summary   = nullptr; // "N perfect / M tunable / K broken"
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FulfillmentPanel_hpp_
