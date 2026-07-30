#include "FulfillmentStore.hpp"

#include "../MixedColorMatchHelpers.hpp" // build_best_color_match_recipe, color_delta_e00

#include <algorithm>
#include <cassert>

namespace Slic3r {
namespace GUI {

namespace {
// ΔE below this means a direct (pure) match. MUST stay in sync with
// K_REUSE_THRESHOLD (MixedFilamentBatchDialog.cpp:2357) — they express the same
// "ΔE<1 → prefer pure filament" product rule. TODO(phase2): hoist both into
// MixedColorMatchHelpers as a single shared constant so they cannot drift.
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
        // Carry forward a prior entry for this intent (for its lock/recipe).
        const FulfillmentEntry* prior = find(intent.design_extruder);

        FulfillmentEntry e;
        e.design_extruder = intent.design_extruder;
        e.design_color    = intent.color;
        e.design_type     = intent.type;

        // §4.3 / §6: a locked entry SURVIVES recompute — its recipe is the
        // user's pinned decision and must NOT be overwritten by solve_intent.
        // Only the design snapshot (colour/type above) is refreshed. The lock
        // itself is dropped if the intent's type changed (hard-constraint
        // space changed); a colour-only change keeps the lock but flags stale
        // so the user is prompted (soft-constraint path).
        const bool lock_survives_this = prior && prior->locked && lock_survives(*prior, intent);
        if (lock_survives_this) {
            e = *prior;                       // preserve the locked recipe wholesale
            e.design_color = intent.color;    // refresh snapshot
            e.design_type  = intent.type;
            e.locked = true;
            e.stale = false;
            // Colour materially changed? Keep the locked recipe but flag stale.
            wxColour old_c(prior->design_color);
            wxColour new_c(intent.color);
            if (old_c.IsOk() && new_c.IsOk() && color_delta_e00(old_c, new_c) > kTunableDeltaE)
                e.stale = true;
            // Re-derive health from the (possibly colour-shifted) intent vs the
            // preserved recipe, so the dot still reflects current truth.
            recompute_health_from_recipe(intent, device, e);
        } else {
            // Not locked (or lock invalidated): solve fresh.
            solve_intent(intent, device, e);
        }
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
        out.recipe = {}; // invalid recipe; delta_e stays infinity
        out.component_ams_keys.clear();
        return;
    }

    // ---- Pass 2: COLOUR MATCH among same-type slots ----
    // Direct: closest slot within ΔE < kDirectDeltaE (pure filament preferred).
    const wxColour target(intent.color);
    const PhysicalSlot* best_direct = nullptr;
    double best_direct_de = std::numeric_limits<double>::max();
    for (const PhysicalSlot* s : same_type) {
        double de = color_delta_e00(target, s->color);
        if (de < best_direct_de) { best_direct_de = de; best_direct = s; }
    }
    if (best_direct && best_direct_de < kDirectDeltaE) {
        // Express the direct match AS a recipe (single-component), so the entry
        // stores one canonical shape for all resolvable kinds.
        out.kind = PlanKind::Direct;
        out.health = HealthState::Perfect;
        out.recipe.valid = true;
        out.recipe.component_a = 1;       // sole component = the matched slot
        out.recipe.component_b = 1;       // degenerate (a==b) signals "single"
        out.recipe.mix_b_percent = 0;
        out.recipe.preview_color = best_direct->color;
        out.recipe.delta_e = best_direct_de;
        out.component_ams_keys.assign(1, best_direct->ams_key);
        return;
    }

    // Synthesised: ask build_best_color_match_recipe for the best blend over the
    // same-type palette. Pure function (verified: no preset_bundle/app_config
    // reads), so feeding it our device-derived palette is safe and bypasses the
    // batch_match audit task entirely (impl §4 caveat).
    //
    // NOTE on the two orthogonal filters in play (NOT redundant):
    //  · our `same_type` filter above = "design intent type vs slot type" — the
    //    §4 hard constraint (I want PETG; only PLA slots → fatal). Design vs slot.
    //  · check_compatible=true below = "can these two palette filaments mix" —
    //    preset-level material compatibility (e.g. PLA+PETG disallowed). Slot vs slot.
    // Both are required; neither subsumes the other.
    std::vector<std::string> palette;
    palette.reserve(same_type.size());
    for (const PhysicalSlot* s : same_type) palette.push_back(s->color.GetAsString(wxC2S_HTML_SYNTAX).ToStdString());

    out.recipe = build_best_color_match_recipe(
        palette, target, /*min_component_percent=*/0, /*max_component_percent=*/100,
        /*check_compatible=*/true);

    if (out.recipe.valid) {
        out.kind = PlanKind::Synthesised;
        // Store the FULL recipe verbatim (component_a/b, mix_b_percent,
        // manual_pattern, gradient_*, preview_color, delta_e) — no projection,
        // so nothing the solver (or later MixedFilamentDialog) produces is lost.
        out.component_ams_keys.clear();
        out.component_ams_keys.reserve(same_type.size());
        for (const PhysicalSlot* s : same_type) out.component_ams_keys.push_back(s->ams_key);
        out.health = (out.recipe.delta_e < kTunableDeltaE) ? HealthState::Tunable : HealthState::Broken;
    } else {
        // Same-type slots exist but no valid blend — unmet (colour-wise
        // unreachable even with synthesis).
        out.kind = PlanKind::Unmet;
        out.health = HealthState::Broken;
        out.component_ams_keys.clear();
    }
}

void FulfillmentStore::recompute_health_from_recipe(const DesignIntent& intent,
                                                    const std::vector<PhysicalSlot>& device,
                                                    FulfillmentEntry& e)
{
    // Re-derive ΔE/health for a locked entry whose recipe is preserved but whose
    // design colour snapshot moved. The recipe already carries its preview_color
    // (the colour this recipe realises), so just recompute ΔE against the new
    // target — no need to re-resolve components. Unmet stays broken.
    if (e.kind == PlanKind::Unmet || !e.recipe.valid) {
        e.health = HealthState::Broken;
        return;
    }
    const wxColour target(intent.color);
    const wxColour realised = e.recipe.preview_color;
    e.recipe.delta_e = realised.IsOk() && target.IsOk() ? color_delta_e00(target, realised)
                                                        : std::numeric_limits<double>::infinity();
    e.health = (e.recipe.delta_e < kDirectDeltaE)  ? HealthState::Perfect
             : (e.recipe.delta_e < kTunableDeltaE) ? HealthState::Tunable
                                                   : HealthState::Broken;
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
        if (e.design_extruder == design_extruder && e.recipe.valid) {
            e.recipe.mix_b_percent = ratio_b_percent;
            return;
        }
    }
}

void FulfillmentStore::set_direct_slot(unsigned int design_extruder, int slot)
{
    // Class-A edit: force a direct (single-slot) realisation for this intent.
    // Expressed as a degenerate recipe (component_a == component_b, ratio 0).
    for (FulfillmentEntry& e : m_entries) {
        if (e.design_extruder == design_extruder) {
            e.kind = PlanKind::Direct;
            e.recipe.valid = true;
            e.recipe.component_a = 1;
            e.recipe.component_b = 1;
            e.recipe.mix_b_percent = 0;
            e.component_ams_keys.assign(1, slot);
            return;
        }
    }
}

void FulfillmentStore::apply_edited_recipe(unsigned int design_extruder,
                                           unsigned int component_a, unsigned int component_b, int mix_b_percent,
                                           const std::string& manual_pattern,
                                           const std::string& gradient_component_ids,
                                           const std::string& gradient_component_weights)
{
    for (FulfillmentEntry& e : m_entries) {
        if (e.design_extruder != design_extruder) continue;
        // Write the dialog's result into the recipe verbatim. component_a/b are
        // palette-local (the dialog was given this entry's component slots as its
        // palette), so they remain consistent with component_ams_keys.
        e.recipe.valid = true;
        e.recipe.component_a = component_a;
        e.recipe.component_b = component_b;
        e.recipe.mix_b_percent = std::clamp(mix_b_percent, 0, 100);
        e.recipe.manual_pattern = manual_pattern;
        e.recipe.gradient_component_ids = gradient_component_ids;
        e.recipe.gradient_component_weights = gradient_component_weights;
        // If the dialog produced a preview colour it carried it in the MixedFilament
        // result, but MixedColorMatchRecipeResult.preview_color is recomputed at
        // solve; we leave the prior preview here and mark the entry Tunable, since
        // the user has now manually intervened (a precise ΔE refresh happens on the
        // next solve against live device stock).
        e.health = HealthState::Tunable;
        e.locked = true;   // explicit edit = user decision worth keeping (§6)
        e.stale = false;
        return;
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
