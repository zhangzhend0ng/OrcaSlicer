#include "FulfillmentSnapshots.hpp"

#include "../MixedColorMatchHelpers.hpp" // try_parse_color_match_hex
#include "../filamentsync/FilamentData.hpp" // FilamentData, getMainColor, is_none_filament
#include "../Plater.hpp"                   // build_design_filament_list / build_machine_filament_list
#include "libslic3r/PresetBundle.hpp"

namespace Slic3r {
namespace GUI {

std::vector<DesignIntent> snapshot_design_intent(const PresetBundle& bundle)
{
    // Reuse the existing build_design_filament_list — same source the sync dialog
    // uses — rather than touching project_config directly. Keeps the design-side
    // filament/type/preset resolution identical across the app.
    std::vector<FilamentData> list;
    build_design_filament_list(const_cast<PresetBundle*>(&bundle), list);

    std::vector<DesignIntent> out;
    out.reserve(list.size());
    for (const FilamentData& fd : list) {
        DesignIntent di;
        di.design_extruder = fd.m_index;
        di.color = fd.m_color.PrimaryColor();
        di.type  = fd.m_type;
        out.push_back(std::move(di));
    }
    return out;
}

std::vector<PhysicalSlot> snapshot_device_stock(const PresetBundle& bundle)
{
    // Reuse build_machine_filament_list — the SAME function the sync dialog uses
    // to read device filaments. It resolves the WCP source
    // (m_connect_machine_info_list) and falls back appropriately, so this works
    // for WCP/Moonraker devices (the case the hand-rolled filament_ams_list read
    // missed entirely). Do NOT re-implement device-data reading here.
    std::vector<FilamentData> list;
    build_machine_filament_list(const_cast<PresetBundle*>(&bundle), list);

    std::vector<PhysicalSlot> out;
    out.reserve(list.size());
    for (const FilamentData& fd : list) {
        PhysicalSlot s;
        s.ams_key   = static_cast<int>(fd.m_index);
        s.tray_name = std::to_string(fd.m_index + 1); // 1-based label
        s.type      = fd.m_type;
        s.exists    = !is_none_filament(fd);
        s.physical_extruder = fd.m_extruder;
        s.is_mock   = fd.m_mock;
        wxColour c;
        if (try_parse_color_match_hex(wxString::FromUTF8(fd.m_color.PrimaryColor()), c))
            s.color = c;
        out.push_back(std::move(s));
    }
    return out;
}

} // namespace GUI
} // namespace Slic3r
