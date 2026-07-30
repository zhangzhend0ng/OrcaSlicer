#include "FulfillmentStore.hpp"

#include "../MixedColorMatchHelpers.hpp" // build_best_color_match_recipe, color_delta_e00

#include <algorithm>
#include <cassert>

namespace Slic3r {
namespace GUI {

namespace {
// ΔE below this means a direct (pure) match — mirrors batch_match pass-1
// K_REUSE_THRESHOLD (MixedFilamentBatchDialog.cpp:2357, PRD §6 Flow B).
constexpr double kDirectDeltaE = 1.0;
// Above this a synthesised match is still "tunable" but no longer "perfect".
constexpr double kTunableDeltaE = 5.0;

// Pull a prior lock forward only if its owning intent is materially unchanged
// (PRD §4.3). Returns true iff the lock survives.
bool lock_survives(const FulfillmentEntry& prior, const DesignIntent& now)
{
    if (!prior.locked) return false;
    // Type change → hard-constraint space changed → lock invalidated.
    if (prior.design_type != now.type) return false;
    // Colour change beyond ΔE threshold → keep lock but caller marks stale.
    // (Survival here is "intent still exists & same type"; staleness is set
    // separately by solve() comparing the entry's stored colour snapshot.)
    return true;
}
} // namespace

void FulfillmentStore::solve(const std::vector<DesignIntent>& design,
                             const std::vector<PhysicalSlot>& device)
{
    // Build the new entry list, carrying forward locks that survive (PRD §4.3).
    // Index prior entries by design_extruder for O(1) lookup.
    std::vector<FulfillmentEntry> next;
    next.reserve(design.size());
    for (const DesignIntent& intent : design) {
        FulfillmentEntry e;
        e.design_extruder = intent.design_extruder;
        e.design_color    = intent.color;
        e.design_type     = intent.type;

        // Carry a prior lock if this intent is the same type as before.
        if (const FulfillmentEntry* p = find(intent.design_extruder)) {
            if (p->locked && lock_survives(*p, intent)) {
                e.locked = true;
                // Colour materially changed? Keep lock but flag stale so the
                // user is prompted (PRD §4.3 soft-constraint path).
                wxColour old_c(p->design_color);
                wxColour new_c(intent.color);
                if (old_c.IsOk() && new_c.IsOk() && color_delta_e00(old_c, new_c) > kTunableDeltaE)
                    e.stale = true;
                else
                    e.stale = false;
            }
        }

        solve_intent(intent, device, e);
        next.push_back(std::move(e));
    }
    // Intent deleted → its entry (and lock) simply isn't copied forward.
    // (PRD §4.3: "design intent deleted → locks automatically dropped".)
    m_entries = std::move(next);
}

void FulfillmentStore::solve_intent(const DesignIntent& intent,
                                    const std::vector<PhysicalSlot>& device,
                                    FulfillmentEntry& out)
{
    // ---- Pass 1: TYPE FILTER (hard constraint, PRD §4) ----
    // Only same-type physical slots may participate. If none, unmet & broken.
    std::vector<const PhysicalSlot*> same_type;
    same_type.reserve(device.size());
    for (const PhysicalSlot& s : device) {
        if (!s.exists) continue;
        if (intent.type.empty() || s.type.empty()) continue; // unknown type = cannot confirm match
        // Case-insensitive compare on type token (PLA vs pla).
        if (s.type.size() == intent.type.size() &&
            std::equal(s.type.begin(), s.type.end(), intent.type.begin(),
                       [](char a, char b) { return std::tolower(a) == std::tolower(b); }))
            same_type.push_back(&s);
    }

    if (same_type.empty()) {
        out.kind = PlanKind::Unmet;
        out.health = HealthState::Broken;
        out.direct_slot = -1;
        out.synth_slot_a = out.synth_slot_b = -1;
        out.delta_e = std::numeric_limits<double>::infinity();
        return;
    }

    // ---- Pass 2: COLOUR MATCH among same-type slots ----
    // Direct: closest slot within ΔE < 1.0 (pure filament preferred).
    const wxColour target(intent.color);
    const PhysicalSlot* best_direct = nullptr;
    double best_direct_de = std::numeric_limits<double>::max();
    for (const PhysicalSlot* s : same_type) {
        double de = color_delta_e00(target, s->color);
        if (de < best_direct_de) { best_direct_de = de; best_direct = s; }
    }
    if (best_direct && best_direct_de < kDirectDeltaE) {
        out.kind = PlanKind::Direct;
        out.health = HealthState::Perfect;
        out.direct_slot = best_direct->ams_key;
        out.synth_slot_a = out.synth_slot_b = -1;
        out.synth_preview_color = best_direct->color;
        out.delta_e = best_direct_de;
        return;
    }

    // Synthesised: ask build_best_color_match_recipe for the best two-slot blend
    // over the same-type palette. This helper is a pure function (verified: no
    // preset_bundle/app_config reads), so feeding it our device-derived palette
    // is safe and bypasses the batch_match audit task entirely (impl §4 caveat).
    std::vector<std::string> palette;
    palette.reserve(same_type.size());
    for (const PhysicalSlot* s : same_type) palette.push_back(s->color.GetAsString(wxC2S_HTML_SYNTAX).ToStdString());

    MixedColorMatchRecipeResult recipe = build_best_color_match_recipe(
        palette, target, /*min_component_percent=*/0, /*max_component_percent=*/100,
        /*check_compatible=*/true); // same-type already filtered, but keep defensive

    if (recipe.valid) {
        // component_a/b are 1-based indices into the palette we passed.
        const unsigned int ia = recipe.component_a;
        const unsigned int ib = recipe.component_b;
        out.kind = PlanKind::Synthesised;
        out.direct_slot = -1;
        if (ia >= 1 && ia <= same_type.size()) out.synth_slot_a = same_type[ia - 1]->ams_key;
        if (ib >= 1 && ib <= same_type.size()) out.synth_slot_b = same_type[ib - 1]->ams_key;
        out.synth_ratio_b_percent = recipe.mix_b_percent;
        out.synth_preview_color = recipe.preview_color;
        out.delta_e = recipe.delta_e;
        out.health = (recipe.delta_e < kTunableDeltaE) ? HealthState::Tunable : HealthState::Broken;
    } else {
        // Same-type slots exist but no valid blend — treat as unmet (colour-wise
        // unreachable even with synthesis).
        out.kind = PlanKind::Unmet;
        out.health = HealthState::Broken;
        out.direct_slot = -1;
        out.synth_slot_a = out.synth_slot_b = -1;
        out.delta_e = std::numeric_limits<double>::infinity();
    }
}

void FulfillmentStore::mark_stale()
{
    for (FulfillmentEntry& e : m_entries) e.stale = true;
}

const FulfillmentEntry* FulfillmentStore::find(unsigned int design_extruder) const
{
    for (const FulfillmentEntry& e : m_entries)
        if (e.design_extruder == design_extruder) return &e;
    return nullptr;
}

FulfillmentStore::HealthRollup FulfillmentStore::rollup() const
{
    HealthRollup r;
    for (const FulfillmentEntry& e : m_entries) {
        switch (e.health) {
            case HealthState::Perfect:  ++r.perfect; break;
            case HealthState::Tunable:  ++r.tunable; break;
            case HealthState::Broken:   ++r.broken;  break;
        }
    }
    return r;
}

// ---- Class-A edits (PRD §5.2.1): write Fulfillment only ----

void FulfillmentStore::set_ratio(unsigned int design_extruder, int ratio_b_percent)
{
    ratio_b_percent = std::clamp(ratio_b_percent, 0, 100);
    for (FulfillmentEntry& e : m_entries) {
        if (e.design_extruder == design_extruder && e.kind == PlanKind::Synthesised) {
            e.synth_ratio_b_percent = ratio_b_percent;
            return;
        }
    }
}

void FulfillmentStore::set_direct_slot(unsigned int design_extruder, int slot)
{
    for (FulfillmentEntry& e : m_entries) {
        if (e.design_extruder == design_extruder) {
            e.kind = PlanKind::Direct;
            e.direct_slot = slot;
            e.synth_slot_a = e.synth_slot_b = -1;
            return;
        }
    }
}

void FulfillmentStore::toggle_lock(unsigned int design_extruder)
{
    for (FulfillmentEntry& e : m_entries) {
        if (e.design_extruder == design_extruder) {
            e.locked = !e.locked;
            return;
        }
        }
}

void FulfillmentStore::reset_to_computed(unsigned int design_extruder)
{
    // Phase 1 simplest honest semantics: mark the row stale and clear its lock
    // so the next solve recomputes it cleanly. (A full per-row re-solve would
    // require re-running solve_intent here with the last snapshots; deferred —
    // the "recompute all" button covers the common case.)
    for (FulfillmentEntry& e : m_entries) {
        if (e.design_extruder == design_extruder) {
            e.locked = false;
            e.stale = true;
            return;
        }
    }
}

void FulfillmentStore::reset_all()
{
    for (FulfillmentEntry& e : m_entries) { e.locked = false; e.stale = true; }
}

void FulfillmentStore::clear_all_locks()
{
    for (FulfillmentEntry& e : m_entries) e.locked = false;
}

} // namespace GUI
} // namespace Slic3r
