#include "FulfillmentSliceMapping.hpp"

#include "FulfillmentStore.hpp"
#include "FulfillmentSnapshots.hpp"     // snapshot_device_stock
#include "../MixedColorMatchHelpers.hpp" // try_parse_color_match_hex

#include "libslic3r/MixedFilament.hpp"   // MixedFilamentManager, MixedFilamentBatchEntry
#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/Config.hpp"

#include <algorithm>
#include <unordered_map>

#include <boost/log/trivial.hpp>

namespace Slic3r {
namespace GUI {

namespace {

// One device filament that the slice must reference, with the physical extruder
// it maps to. Collected from solved recipes, then sorted by physical_extruder
// to define the device-space T-numbering (slot with smallest physical_extruder
// -> device array index 0 -> T0).
struct DeviceFilamentRow
{
    int         ams_key          = -1;   // PhysicalSlot.ams_key (WCP array index)
    int         physical_extruder = -1;   // device-reported T-number (0-based)
    std::string color_hex;               // "#RRGGBB"
    std::string type;                    // "PLA", ...
};

// Compare so mapped slots sort first (ascending extruder), unmapped (-1) last.
// This makes device array indices [0..k-1] the slots the device gave us a real
// T-number for, in T-number order; unmapped slots (fallback) append at the end.
bool device_row_less(const DeviceFilamentRow& a, const DeviceFilamentRow& b)
{
    // Both unmapped: keep stable-ish order by ams_key.
    if (a.physical_extruder < 0 && b.physical_extruder < 0) return a.ams_key < b.ams_key;
    // Mapped before unmapped.
    if (a.physical_extruder < 0) return false;
    if (b.physical_extruder < 0) return true;
    return a.physical_extruder < b.physical_extruder;
}

} // namespace

std::optional<DeviceFilamentSpace>
build_device_filament_space(const DynamicPrintConfig& design_full_config,
                            const PresetBundle&       bundle,
                            const FulfillmentStore&   store)
{
    // Only act on a solved store with at least one realisable entry.
    if (!store.has_solved()) return std::nullopt;

    const std::vector<PhysicalSlot> device = snapshot_device_stock(bundle);

    // Index device slots by ams_key (== PhysicalSlot.ams_key == WCP array index,
    // the same value stored in FulfillmentEntry.component_ams_keys).
    std::unordered_map<int, const PhysicalSlot*> slot_by_ams_key;
    slot_by_ams_key.reserve(device.size());
    for (const PhysicalSlot& s : device) slot_by_ams_key.emplace(s.ams_key, &s);

    // ---- Pass 1: enumerate the distinct device filaments the recipes need ----
    // For each solved entry, resolve its recipe's components to device slots.
    // Build a unique, sorted device filament list (the device-space array).
    //
    // NOTE: this lambda returns void by design. An earlier version returned
    // `const DeviceFilamentRow*` = `&rows.back()` immediately after a push_back
    // that could reallocate `rows` — a use-after-reallocation dangling pointer
    // (harness UB-3/UB-4). The sole caller discards the result anyway, so the
    // return value was both dead and a latent trap. Returning void removes both.
    std::vector<DeviceFilamentRow> rows;
    // Sanitise the device-reported physical_extruder (T-number). It is parsed
    // verbatim from untrusted device WCP JSON (SSWCP.cpp:1648,
    // extruder_map_table[i].get<int>()) with no upstream bounds check. A
    // legitimate T-number is always in [0, device.size()) — a slot index beyond
    // the reported filament count names a slot the device does not have. Without
    // this clamp, a malformed/huge value would set max_t to that value and make
    // num_physical = max_t+1, driving an unbounded allocation of t_indexed_colors
    // (input-validation (N), integer-safety (N)). Out-of-range values are mapped
    // to -1 (unmapped), preserving the existing Moonraker/Klipper fallback path.
    const auto device_extruder_limit = static_cast<int>(device.size());
    auto need_slot = [&](int ams_key) -> void {
        for (const DeviceFilamentRow& r : rows)
            if (r.ams_key == ams_key) return; // already collected
        auto it = slot_by_ams_key.find(ams_key);
        if (it == slot_by_ams_key.end() || it->second == nullptr) return;
        const PhysicalSlot* s = it->second;
        DeviceFilamentRow r;
        r.ams_key = s->ams_key;
        const int reported = s->physical_extruder;
        r.physical_extruder = (reported >= 0 && reported < device_extruder_limit) ? reported : -1;
        if (s->color.IsOk()) r.color_hex = s->color.GetAsString(wxC2S_HTML_SYNTAX).ToStdString();
        r.type = s->type;
        rows.push_back(std::move(r));
    };

    const std::vector<FulfillmentEntry>& entries = store.entries();

    // design_to_device is indexed by design_extruder (0-based); size to cover
    // the largest design extruder we saw. 0 means "no realisation".
    unsigned int max_design_extruder = 0;
    for (const FulfillmentEntry& e : entries)
        max_design_extruder = std::max(max_design_extruder, e.design_extruder);

    for (const FulfillmentEntry& e : entries) {
        if (e.kind == PlanKind::Unmet || !e.recipe.valid) continue;
        // Direct: component_a is the sole (palette-local) component.
        // Synthesised: component_a and component_b are the two palette-local components.
        // Degenerate single-component recipe (a==b, mix==0) is treated as direct.
        const unsigned int comps[2] = { e.recipe.component_a, e.recipe.component_b };
        const int          ncomp    = (e.kind == PlanKind::Direct || e.recipe.mix_b_percent == 0) ? 1 : 2;
        for (unsigned int ci = 0; ci < (unsigned int)ncomp; ++ci) {
            const unsigned int palette_idx = comps[ci]; // 1-based into component_ams_keys
            if (palette_idx < 1 || palette_idx > e.component_ams_keys.size()) {
                BOOST_LOG_TRIVIAL(warning) << "build_device_filament_space: recipe component "
                                           << palette_idx << " out of range for design extruder "
                                           << e.design_extruder << " (component_ams_keys.size="
                                           << e.component_ams_keys.size() << ")";
                continue;
            }
            need_slot(e.component_ams_keys[palette_idx - 1]);
        }
    }
    if (rows.empty()) return std::nullopt;

    std::sort(rows.begin(), rows.end(), device_row_less);

    // Device-space array index MUST equal the device's real G-code T-number, so a
    // sparse T-number set (e.g. T0/T1/T3 with T2 empty) stays aligned — the slicer
    // indexes per-extruder config arrays by T-number, and G-code Tn reads
    // filament_*[n]. Compacting by row position would renumber T3 as T2 and point
    // G-code at the wrong physical slot. So size the array to max_T+1 (placeholder
    // slots for gaps) unless no slot reported a T-number (Moonraker/Klipper fallback:
    // size by count and index by row position, preserving prior behaviour).
    int max_t = -1;
    for (const DeviceFilamentRow& r : rows)
        if (r.physical_extruder > max_t) max_t = r.physical_extruder;
    const bool all_unmapped = (max_t < 0);
    const int  num_physical = all_unmapped ? static_cast<int>(rows.size()) : (max_t + 1);

    // Map a row to its device-space array index: the real T-number when reported,
    // else (fallback) its sorted row position.
    auto row_device_index = [&](const DeviceFilamentRow& r, size_t row_pos) -> int {
        return all_unmapped ? static_cast<int>(row_pos) : r.physical_extruder;
    };

    // Colours indexed by device T-number (gaps filled with a placeholder). Shared by
    // Pass 3 (filament_colour) and the mixed-filament manager (component colours) so
    // both see the same T-number-aligned palette — the manager clamps component refs
    // to [1, size], so it must see the gap-aware array, not the compacted rows.
    std::vector<std::string> t_indexed_colors(num_physical, "#9E9E9E"); // placeholder for empty slots
    for (size_t i = 0; i < rows.size(); ++i) {
        int idx = row_device_index(rows[i], i);
        if (idx >= 0 && idx < num_physical)
            t_indexed_colors[idx] = rows[i].color_hex.empty() ? std::string("#26A69A") : rows[i].color_hex;
    }

    // ams_key -> row position in `rows` (0-based). Used to look up the row (for its
    // physical_extruder / colour) and then convert to a device T-number via
    // row_device_index. Kept as a row index (not a T-number) so component_device_id
    // can still inspect rows[it->second].physical_extruder to detect unmapped slots.
    std::unordered_map<int, int> device_index_by_ams_key;
    device_index_by_ams_key.reserve(rows.size());
    for (size_t i = 0; i < rows.size(); ++i)
        device_index_by_ams_key.emplace(rows[i].ams_key, static_cast<int>(i));

    // ---- Pass 2: build the synthesised (virtual) mixed rows ----
    // For synthesised entries whose components all resolve to KNOWN device slots
    // (physical_extruder != -1), emit a MixedFilamentBatchEntry so the slice
    // blends those two device filaments by layer cadence. Entries with any
    // unmapped component are skipped (fallback: that design extruder slices as
    // its original design colour — the caller leaves it at 0 in design_to_device).
    bool any_unmapped_component_seen = false;
    MixedFilamentManager mgr;
    std::vector<MixedFilamentBatchEntry> batch_entries;

    // Track per-entry whether it became a virtual row, to assign design_to_device.
    // We collect entries-to-virtual-id after add_batch.
    struct SynthMapping { unsigned int design_extruder; };
    std::vector<SynthMapping> synth_order; // parallel to batch_entries

    auto component_device_id = [&](const FulfillmentEntry& e, unsigned int palette_idx) -> int {
        // Returns 1-based device filament id (T-number+1), or 0 if unmapped/unresolvable.
        if (palette_idx < 1 || palette_idx > e.component_ams_keys.size()) return 0;
        int ams_key = e.component_ams_keys[palette_idx - 1];
        auto it = device_index_by_ams_key.find(ams_key);
        if (it == device_index_by_ams_key.end()) return 0;
        if (rows[it->second].physical_extruder < 0) return 0; // fallback: skip synth
        // Device id is the real T-number (+1 for 1-based), so G-code Tn aligns with
        // the physical slot even when other slots are empty (sparse T-number set).
        return row_device_index(rows[it->second], it->second) + 1;
    };

    for (const FulfillmentEntry& e : entries) {
        if (e.kind != PlanKind::Synthesised || !e.recipe.valid) continue;
        if (e.recipe.mix_b_percent == 0) continue; // effectively direct
        int a = component_device_id(e, e.recipe.component_a);
        int b = component_device_id(e, e.recipe.component_b);
        if (a <= 0 || b <= 0 || a == b) {
            any_unmapped_component_seen = true;
            BOOST_LOG_TRIVIAL(info) << "build_device_filament_space: skipping synthesised recipe for "
                                    << "design extruder " << e.design_extruder
                                    << " (component a=" << a << " b=" << b
                                    << " — unmapped device slot, fallback to design colour)";
            continue;
        }
        MixedFilamentBatchEntry be;
        be.component_a   = static_cast<unsigned int>(a);
        be.component_b   = static_cast<unsigned int>(b);
        be.mix_b_percent = e.recipe.mix_b_percent;
        be.manual_pattern            = e.recipe.manual_pattern;
        be.gradient_component_ids    = e.recipe.gradient_component_ids;
        be.gradient_component_weights= e.recipe.gradient_component_weights;
        be.distribution_mode         = int(MixedFilament::Simple);
        if (e.recipe.preview_color.IsOk())
            be.display_color = e.recipe.preview_color.GetAsString(wxC2S_HTML_SYNTAX).ToStdString();
        batch_entries.push_back(be);
        synth_order.push_back({ e.design_extruder });
    }

    std::vector<unsigned int> assigned_ids; // 1-based virtual ids per batch entry (0 if dropped)
    if (!batch_entries.empty()) {
        // add_batch_custom_filaments clamps component refs to [1,n] (n = colours.size())
        // and indexes colours by [component-1]. Component refs are T-numbers+1, so the
        // colour array MUST be T-number-indexed (with placeholder gaps) — reusing the
        // compacted rows here would clamp a T3 component (id 4) down to the row count
        // and pick the wrong colour.
        std::vector<std::string> device_colors = t_indexed_colors;
        // NOTE: we deliberately do NOT call auto_generate() on this local manager.
        // auto_generate would emit all C(N,2) pairwise rows into m_mixed, which
        // serialize_custom_entries() would then include in the string — polluting
        // the device space with rows the recipes never asked for. We want the
        // serialized string to contain ONLY the synthesised rows we explicitly
        // add. (Print::apply's own auto_generate is suppressed around the slice
        // call by the caller — see prepare_slice_inputs — so virtual IDs stay
        // deterministic: num_physical + (synth index) + 1.)
        mgr.add_batch_custom_filaments(batch_entries, device_colors, &assigned_ids);
    }

    const int num_total = num_physical + static_cast<int>(mgr.enabled_count());

    if (any_unmapped_component_seen) {
        BOOST_LOG_TRIVIAL(info) << "build_device_filament_space: device did not report "
                                << "extruder_map_table for some slots; synthesised recipes on those "
                                << "slots were skipped (fallback to design colour).";
    }

    // ---- Pass 3: build the device-space config ----
    DeviceFilamentSpace out;
    out.config        = design_full_config; // value copy — we never write back to preset_bundle
    out.num_physical  = num_physical;
    out.num_total     = num_total;

    // Resize ALL per-extruder arrays to the device count, padding/truncating
    // with defaults. Then overwrite the content keys we care about.
    out.config.set_num_extruders(static_cast<unsigned int>(num_physical));

    {
        auto* colours = out.config.option<ConfigOptionStrings>("filament_colour");
        auto* types   = out.config.option<ConfigOptionStrings>("filament_type");
        auto* diam    = out.config.option<ConfigOptionFloats>("filament_diameter");
        // Fill every slot (including empty/placeholder gaps) with defaults first.
        for (int i = 0; i < num_physical; ++i) {
            if (colours) colours->values[i] = t_indexed_colors[i]; // real colour or placeholder grey
            if (types)   types->values[i]   = "PLA";   // placeholder type for empty slots
            if (diam)    diam->values[i]    = 1.75;     // sane default; device stock has none
        }
        // Overwrite types for slots that actually have a loaded filament. colours
        // already came from t_indexed_colors (T-number aligned); types follow the
        // same T-number indexing. (Iterating rows, not 0..num_physical, avoids
        // out-of-bounds when num_physical > rows.size() due to empty-slot gaps.)
        for (size_t i = 0; i < rows.size(); ++i) {
            int idx = row_device_index(rows[i], i);
            if (idx >= 0 && idx < num_physical && types && !rows[i].type.empty())
                types->values[idx] = rows[i].type;
        }
    }

    // Inject synthesised rows as the mixed_filament_definitions string. This is
    // the ONLY input Print::apply reads to rebuild its MixedFilamentManager.
    out.config.opt_string("mixed_filament_definitions", true) = mgr.serialize_custom_entries();

    // ---- Pass 4: design_extruder -> device filament id map ----
    out.design_to_device.assign(static_cast<size_t>(max_design_extruder) + 1, 0u);
    auto set_map = [&](unsigned int design_extruder, unsigned int device_id) {
        if (design_extruder < out.design_to_device.size())
            out.design_to_device[design_extruder] = device_id;
    };

    // Synthesised entries that became virtual rows.
    for (size_t i = 0; i < synth_order.size() && i < assigned_ids.size(); ++i) {
        if (assigned_ids[i] != 0)
            set_map(synth_order[i].design_extruder, assigned_ids[i]);
    }
    // Direct entries (and synthesised entries we skipped above — fall back to
    // their primary component if it resolves, else stay 0 = use design colour).
    for (const FulfillmentEntry& e : entries) {
        if (e.kind == PlanKind::Unmet || !e.recipe.valid) continue;
        if (e.design_extruder >= out.design_to_device.size()) continue;
        if (out.design_to_device[e.design_extruder] != 0) continue; // already a synth virtual id
        int a = component_device_id(e, e.recipe.component_a);
        if (a > 0) set_map(e.design_extruder, static_cast<unsigned int>(a));
        // else: stays 0 -> caller slices this extruder with original design colour (fallback)
    }

    // Snapshot the synthesised rows' display colours (device virtual T-number order).
    // mgr is fully refreshed after add_batch_custom_filaments, so display_colors()
    // is current. Held alongside the config so the Expected-View preview palette
    // can show device-filament blends for virtual extruders without re-deriving.
    out.virtual_display_colors = mgr.display_colors();

    return out;
}

} // namespace GUI
} // namespace Slic3r
