#ifndef slic3r_GUI_FulfillmentSliceMapping_hpp_
#define slic3r_GUI_FulfillmentSliceMapping_hpp_

// Slice-time "device filament space" builder.
//
// Product principle (PRD): the G-code produced by slicing must reference ONLY
// the physical filaments actually loaded on the device. The design layer's
// colour intents are realised as combinations of device filaments:
//   - Direct recipe     -> one device filament (its physical extruder / T-number)
//   - Synthesised recipe -> two device filaments blended by layer cadence
//
// This happens ONLY at the slice entry point: we build a *temporary* device
// filament space (a DynamicPrintConfig + a design->device id remap) and feed a
// temporary Model copy with remapped painting into Print::apply. The design
// layer (Plater::priv::model + PresetBundle) is never written — see the temp
// copy flow in Plater::priv::prepare_slice_inputs().

#include <optional>
#include <vector>

#include "libslic3r/Config.hpp"          // DynamicPrintConfig

namespace Slic3r {
class PresetBundle;
namespace GUI {

class FulfillmentStore;

// The slice-time device filament space.
struct DeviceFilamentSpace
{
    DynamicPrintConfig        config;            // device-space full_config (copy)
    int                       num_physical = 0;  // number of device filaments (= G-code extruder count)
    int                       num_total    = 0;  // num_physical + enabled synthesised (virtual) rows
    // design_extruder (0-based) -> device-space filament id (1-based). A physical
    // device filament id is in [1..num_physical]; a synthesised (virtual) mixed
    // id is in [num_physical+1 .. num_total]. 0 = this design extruder has no
    // realisation (kept as design colour / fallback).
    std::vector<unsigned int> design_to_device;

    // Display colours for the synthesised (virtual) mixed rows, in device virtual
    // T-number order (i.e. the trailing [num_physical+1 .. num_total] slots).
    // Mirrors MixedFilamentManager::display_colors() at build time. Consumed by
    // the Expected-View preview palette so G-code virtual extruders show the
    // device-filament blend realised by each synthesised recipe.
    std::vector<std::string>  virtual_display_colors;
};

// Build the device filament space from the solved FulfillmentStore. Returns
// nullopt when no override is applicable (store not solved, or no valid recipe
// resolves to device filaments) — in that case the caller slices with the
// original design-layer config unchanged.
//
// `design_full_config` is the value-copy from preset_bundle->full_config() that
// the caller already obtained; it is the base we rewrite in place. `bundle` is
// read-only (device stock snapshot via snapshot_device_stock).
//
// When the device does not report extruder_map_table (physical_extruder == -1,
// e.g. Moonraker/Klipper), synthesised recipes are skipped (no safe way to map
// components to physical extruders); direct recipes fall back to array-order
// mapping. See plan "fallback" section.
std::optional<DeviceFilamentSpace>
build_device_filament_space(const DynamicPrintConfig& design_full_config,
                            const PresetBundle&       bundle,
                            const FulfillmentStore&   store);

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FulfillmentSliceMapping_hpp_
