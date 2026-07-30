#ifndef slic3r_GUI_FulfillmentStore_hpp_
#define slic3r_GUI_FulfillmentStore_hpp_

#include <cstdint>
#include <limits>
#include <string>
#include <vector>

#include <wx/colour.h>

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

    // Direct match: the physical slot (key into filament_ams_list) that
    // satisfies this intent within ΔE < 1.0. -1 = none.
    int          direct_slot = -1;

    // Synthesised match: two same-type slots blended. -1 / empty = none.
    int          synth_slot_a = -1;
    int          synth_slot_b = -1;
    int          synth_ratio_b_percent = 0; // 0..100 share of slot_b
    wxColour     synth_preview_color;       // predicted realised colour

    double       delta_e = std::numeric_limits<double>::infinity();

    bool         locked = false; // user-pinned; survives recompute (PRD §4.3)
    bool         stale  = true;  // needs (re)solve
};

// Snapshot of one physical device slot used by the solver. Decoupled from
// filament_ams_list's DynamicPrintConfig so the store/solver stay testable
// without preset_bundle.
struct PhysicalSlot
{
    int          ams_key = -1;   // key in filament_ams_list (ams_id*4+tray_id)
    std::string  tray_name;      // "A1".."Ext"
    std::string  type;           // "PLA", ... (empty if unknown)
    wxColour     color;
    bool         exists = false; // filament_present
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
    bool                                 has_solved() const { return !m_entries.empty() && !m_entries.front().stale; }

    // Class-A edits (PRD §5.2.1): write Fulfillment, never Design.
    void set_ratio(unsigned int design_extruder, int ratio_b_percent);
    void set_direct_slot(unsigned int design_extruder, int slot);
    void toggle_lock(unsigned int design_extruder);
    void reset_to_computed(unsigned int design_extruder); // undo manual edits on a row
    void reset_all();                                     // discard all manual edits
    void clear_all_locks();                               // PRD §12.1 panic button

private:
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
