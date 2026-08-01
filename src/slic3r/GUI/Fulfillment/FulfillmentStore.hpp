#ifndef slic3r_GUI_FulfillmentStore_hpp_
#define slic3r_GUI_FulfillmentStore_hpp_

#include <cstdint>
#include <limits>
#include <string>
#include <vector>

#include <wx/colour.h>

#include "../MixedColorMatchHelpers.hpp" // MixedColorMatchRecipeResult (the
                                        // canonical recipe model — do NOT
                                        // re-define a parallel one)

namespace Slic3r {
namespace GUI {

// One design intent's realisation plan, derived from the (immutable) Design
// Layer and the (read-only) Physical Layer. Populated by FulfillmentSolver.
// All identity is keyed by design_extruder (0-based), which the Design Layer
// guarantees stable within a session.
//
// Phase 1: in-memory only, not persisted (PRD §12.2).

enum class PlanKind   { Direct, Synthesised, Unmet };
enum class HealthState { Perfect, Tunable, Broken }; // green / yellow / red

// The unit the canvas renders as one row, and the pre-print gate rolls up.
struct FulfillmentEntry
{
    unsigned int design_extruder = 0;   // 0-based identity (Design Layer index)
    std::string  design_color;          // hex snapshot at solve time ("#RRGGBB")
    std::string  design_type;           // snapshot ("PLA", "PETG", ...)

    PlanKind     kind   = PlanKind::Unmet;
    HealthState  health = HealthState::Broken;

    // The recipe as returned by the solver (build_best_color_match_recipe) and
    // edited via MixedFilamentDialog. Stores component_a/b, mix_b_percent,
    // manual_pattern, gradient_component_ids/weights, preview_color, delta_e.
    //
    // NOTE (deliberate Phase-1 scope): we store MixedColorMatchRecipeResult, NOT
    // Slic3r::MixedFilament, even though MixedFilament is the slice/edit
    // authority. Reason: MixedFilament.component_a/b are GLOBAL physical
    // filament IDs, which would pull in the ams_key↔global-ID alignment problem
    // (PRD §9.2) — unneeded for Phase 1's show/edit/gate purposes, which only
    // need "which device slots + ratio + preview + ΔE". recipe.component_a/b are
    // palette-local indices (resolved to device slots via component_ams_keys
    // below), so no global-ID dependency. When Phase 2 actually writes a recipe
    // back into the slice pipeline, THAT is when we build the global-ID mapping
    // and convert to MixedFilament. Do not store MixedFilament prematurely.
    MixedColorMatchRecipeResult recipe;

    // recipe.component_a/b are 1-based indices into the palette passed to the
    // solver. component_ams_keys[i-1] is the device ams_key for component id i,
    // so rendering/locking can resolve recipe components to real slots without
    // any global physical-filament-ID mapping.
    std::vector<int> component_ams_keys;

    bool         locked = false; // user-pinned; survives recompute (PRD §4.3)
    bool         stale  = true;  // needs (re)solve
};

// Snapshot of one physical device slot used by the solver. Decoupled from
// filament_ams_list's DynamicPrintConfig so the store/solver stay testable
// without preset_bundle.
struct PhysicalSlot
{
    // Position index of this slot in build_machine_filament_list's output, which
    // follows the WCP `filament_official` array order (NOT the filament_ams_list
    // ams_id*4+tray_id key — that map covers BBL/AMS only).
    int          ams_key = -1;
    std::string  tray_name;      // "A1".."Ext"
    std::string  type;           // "PLA", ... (empty if unknown)
    wxColour     color;
    bool         exists = false; // filament_present
    // Device-reported physical extruder (G-code T-number, 0-based) for this slot,
    // from WCP `extruder_map_table`. This is the authoritative "slot -> extruder"
    // mapping used to build the slice device-space filament array (whose indices
    // must equal G-code T-numbers). -1 = device did not report (fallback).
    int          physical_extruder = -1;
};

struct DesignIntent
{
    unsigned int design_extruder = 0; // 0-based
    std::string  color;               // "#RRGGBB"
    std::string  type;                // "PLA", ...
};

// UI-thread-owned derived plan (PRD §12.4). No wx widgets here — pure data +
// logic, so it is unit-testable without a GUI.
class FulfillmentStore
{
public:
    // Roll-up for the pre-print gate / global indicator.
    struct HealthRollup { int perfect = 0, tunable = 0, broken = 0; };

    // Replace design + device snapshots and (re)solve every entry.
    // Honours §4.3 lock invalidation: a lock whose intent was deleted or had
    // its type changed is dropped; a colour-only change keeps the lock but
    // marks the entry stale. Phase 1 runs synchronously on the calling thread
    // (the per-intent solve via build_best_color_match_recipe is cheap enough
    // for typical colour counts; PRD §12.3 still applies for the heavy path).
    void solve(const std::vector<DesignIntent>& design,
               const std::vector<PhysicalSlot>& device);

    // Invalidate without solving (design/device changed signals).
    void mark_stale();

    // Read access.
    const std::vector<FulfillmentEntry>& entries() const { return m_entries; }
    const FulfillmentEntry*              find(unsigned int design_extruder) const;
    HealthRollup                         rollup() const;
    // "Has a solve ever been performed?" — independent of stale. Stale means the
    // data MAY be out of date (design/device changed); it should NOT cause the UI
    // to hide already-computed results. Without this decoupling, any model drag
    // (which fires EVT_FILAMENT_USAGE_CHANGED) wipes the displayed plan.
    bool                                 has_solved() const { return m_ever_solved; }

    // Class-A edits (PRD §5.2.1): write Fulfillment, never Design.
    void set_ratio(unsigned int design_extruder, int ratio_b_percent);
    void set_direct_slot(unsigned int design_extruder, int slot);
    // Direct match with full colour/delta_e/health (used when user picks a
    // specific physical filament from MachineFilamentPicker).
    void set_direct_with_color(unsigned int design_extruder, int slot,
                               const wxColour& realised_color, const std::string& design_color_hex);
    // Apply a recipe edited via MixedFilamentDialog. Component ids are
    // palette-local (1-based into the entry's component_ams_keys). Marks the
    // entry locked (an explicit edit is a user decision worth keeping, §6) and
    // recomputes health/preview from the new recipe.
    void apply_edited_recipe(unsigned int design_extruder,
                             unsigned int component_a, unsigned int component_b, int mix_b_percent,
                             const std::string& manual_pattern,
                             const std::string& gradient_component_ids,
                             const std::string& gradient_component_weights,
                             const std::vector<int>& component_ams_keys);
    void toggle_lock(unsigned int design_extruder);
    void reset_all();                                     // discard all manual edits
    void clear_all_locks();                               // PRD §12.1 panic button

private:
    // Set true after the first solve(), never reset. Independent of stale flags
    // so has_solved() stays true across model drags that mark entries stale.
    bool m_ever_solved = false;

    // Resolves a single design intent against the device snapshot into `out`.
    // Type-first (hard constraint, PRD §4), then colour via build_best_color_match_recipe.
    static void solve_intent(const DesignIntent& intent,
                             const std::vector<PhysicalSlot>& device,
                             FulfillmentEntry& out);

    // Re-derive health/delta_e for an entry whose recipe is already set (used
    // when a locked recipe is preserved but the design colour snapshot moved,
    // so the dot still reflects current truth). Does not change the recipe.
    static void recompute_health_from_recipe(const DesignIntent& intent,
                                             const std::vector<PhysicalSlot>& device,
                                             FulfillmentEntry& e);

    std::vector<FulfillmentEntry> m_entries;
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FulfillmentStore_hpp_
