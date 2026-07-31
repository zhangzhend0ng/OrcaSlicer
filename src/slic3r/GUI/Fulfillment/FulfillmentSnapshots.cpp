#include "FulfillmentSnapshots.hpp"

#include "../MixedColorMatchHelpers.hpp" // try_parse_color_match_hex
#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/PrintConfig.hpp"

namespace Slic3r {
namespace GUI {

std::vector<DesignIntent> snapshot_design_intent(const PresetBundle& bundle)
{
    std::vector<DesignIntent> out;
    const Slic3r::DynamicPrintConfig& cfg = bundle.project_config;
    if (!cfg.has("filament_colour") || !cfg.has("filament_type"))
        return out;

    const auto* colours = cfg.option<ConfigOptionStrings>("filament_colour");
    const auto* types   = cfg.option<ConfigOptionStrings>("filament_type");
    if (!colours || !types)
        return out;

    const size_t n = colours->values.size();
    out.reserve(n);
    for (size_t i = 0; i < n; ++i) {
        DesignIntent di;
        di.design_extruder = static_cast<unsigned int>(i);
        di.color = colours->values[i];
        di.type  = (i < types->values.size()) ? types->values[i] : std::string{};
        out.push_back(std::move(di));
    }
    return out;
}

std::vector<PhysicalSlot> snapshot_device_stock(const PresetBundle& bundle)
{
    std::vector<PhysicalSlot> out;

    // PRIMARY source: m_connect_machine_info_list — covers WCP/Moonraker devices
    // (the common case for Snapmaker printers connected via the cloud/LAN WCP
    // protocol). This is what `build_machine_filament_list` and the filament
    // combos already consume. Each entry's `index` is the physical slot id.
    for (const auto& info : bundle.m_connect_machine_info_list) {
        PhysicalSlot s;
        s.ams_key   = info.index;           // physical slot id (used for display/lock)
        s.tray_name = std::to_string(info.index + 1); // 1-based label like "1","2"
        s.type      = info.filament_type;
        // exists = has a colour + type (an empty slot has neither).
        s.exists    = !info.color_info.empty() && !info.filament_type.empty();
        wxColour c;
        if (try_parse_color_match_hex(wxString::FromUTF8(info.color_info), c))
            s.color = c;
        out.push_back(std::move(s));
    }

    // FALLBACK source: filament_ams_list — the BBL-native AMS tray config. Only
    // used when no ConnectMachineInfo was synced (e.g. a pure BBL AMS printer
    // that hasn't populated m_connect_machine_info_list). Avoids double-adding:
    // if the primary list is non-empty, the device speaks WCP and ams_list is
    // stale/empty anyway.
    if (out.empty()) {
        for (const auto& kv : bundle.filament_ams_list) {
            const DynamicPrintConfig& tray = kv.second;
            PhysicalSlot s;
            s.ams_key = kv.first;
            s.tray_name = tray.opt_string("tray_name", 0u);
            if (s.tray_name.empty())
                continue;
            s.type   = tray.opt_string("filament_type", 0u);
            s.exists = tray.opt_bool("filament_exist", 0u);
            wxColour c;
            if (try_parse_color_match_hex(wxString::FromUTF8(tray.opt_string("filament_colour", 0u)), c))
                s.color = c;
            out.push_back(std::move(s));
        }
    }

    return out;
}

} // namespace GUI
} // namespace Slic3r
