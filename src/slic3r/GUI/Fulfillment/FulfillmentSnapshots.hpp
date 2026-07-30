#ifndef slic3r_GUI_FulfillmentSnapshots_hpp_
#define slic3r_GUI_FulfillmentSnapshots_hpp_

// Read-only adapters that bridge the existing Design Layer (preset_bundle
// project_config: filament_colour / filament_type) and the Physical Layer
// (preset_bundle->filament_ams_list) into the plain structs the
// FulfillmentStore consumes. Keeping the preset_bundle parsing here (and out of
// the store) keeps the store testable without a GUI/preset_bundle.

#include <vector>

#include "FulfillmentStore.hpp"

namespace Slic3r {
class PresetBundle;
namespace GUI {

// Snapshot the Design Layer read-only. Returns one DesignIntent per physical
// filament slot (0-based design_extruder). Never writes preset_bundle.
std::vector<DesignIntent> snapshot_design_intent(const PresetBundle& bundle);

// Snapshot the Physical Layer read-only. Returns one PhysicalSlot per AMS tray
// in filament_ams_list. Skips slots with no tray_name. Never writes preset_bundle.
std::vector<PhysicalSlot> snapshot_device_stock(const PresetBundle& bundle);

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FulfillmentSnapshots_hpp_
