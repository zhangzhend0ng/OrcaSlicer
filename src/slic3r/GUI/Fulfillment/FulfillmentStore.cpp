#include "FulfillmentStore.hpp"

#include "../MixedColorMatchHelpers.hpp" // build_best_color_match_recipe, color_delta_e00

#include <algorithm>
#include <cassert>
#include <unordered_set>
#include <boost/algorithm/string/predicate.hpp> // boost::iequals

namespace Slic3r {
namespace GUI {

namespace {
// Above this a synthesised match is still "tunable" but no longer "perfect".
// (The direct-match threshold is the shared kColorMatchDirectThreshold in
// MixedColorMatchHelpers.hpp — used by name, no local copy.)
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

// A locked recipe pins specific device slots (component_ams_keys). Those keys
// are only meaningful against the device snapshot the lock was made against; if
// the snapshot changed (e.g. mock<->real, slot removed), the same integer may
// now name a different filament or none at all. The lock is only safe to keep
// while every key it references is still present in the current snapshot. A
// missing key means the user-pinned recipe can no longer be honoured as-is, so
// solve() drops the lock and re-matches against the live device.
bool lock_components_present(const FulfillmentEntry& prior, const std::unordered_set<int>& device_ams_keys)
{
    if (!prior.locked) return false;
    for (int key : prior.component_ams_keys)
        if (device_ams_keys.find(key) == device_ams_keys.end()) return false;
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

    // Device ams_key set for this snapshot — used to validate that a locked
    // entry's component_ams_keys still resolve against the CURRENT device. The
    // ams_key namespace is NOT stable across a device snapshot change: a real
    // machine's ams_key is the WCP filament_official array position, while the
    // offline mock's is the extruder index, so the SAME integer can name a
    // different physical filament before/after a (dis)connect. A locked recipe
    // whose ams_keys no longer exist must be re-solved rather than silently
    // rewired to whatever now sits at that key (or dropped mid-slice).
    std::unordered_set<int> device_ams_keys;
    device_ams_keys.reserve(device.size());
    for (const PhysicalSlot& s : device) device_ams_keys.insert(s.ams_key);

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
        // It is ALSO dropped if any recipe component no longer maps to a device
        // slot in the current snapshot (device changed under the lock) — see
        // device_ams_keys above.
        const bool lock_survives_this = prior && prior->locked && lock_survives(*prior, intent)
                                     && lock_components_present(*prior, device_ams_keys);
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
            // Fresh-solved entries are current (not stale). (FulfillmentEntry.stale
            // defaults true; without this, has_solved() — which checks front().stale
            // — would wrongly return false and refresh_fulfilment would show the
            // hint instead of the solved rows.)
            e.stale = false;
        }
        next.push_back(std::move(e));
    }
    // Intent deleted → its entry (and lock) simply isn't copied forward.
    // (PRD §4.3: "design intent deleted → locks automatically dropped".)
    m_entries = std::move(next);
    m_ever_solved = true;
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
        // Case-insensitive type match (PLA vs pla). boost::iequals avoids the
        // fragile std::equal-with-second-sequence-length pitfall.
        if (boost::iequals(s.type, intent.type))
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
    // Direct: closest slot within ΔE < kColorMatchDirectThreshold (pure filament preferred).
    //
    // Colour validity is a precondition for an honest ΔE: color_delta_e00 reads
    // RGB channels unconditionally and, given an invalid wxColour (default-
    // constructed, channels read as 0), silently treats it as BLACK — yielding a
    // finite, plausible-looking ΔE that can wrongly elect a slot as the "best
    // direct match" (PRD §5: gaps must be spoken, never silently substituted).
    // An invalid target colour (unparseable design intent) or an invalid slot
    // colour (unparseable device-reported hex — snapshot_device_stock only sets
    // s.color when try_parse_color_match_hex succeeds, else leaves it invalid)
    // therefore cannot be matched honestly.
    const wxColour target(intent.color);
    if (!target.IsOk()) {
        // Same-type stock exists, but the design colour itself is unresolvable —
        // a colour gap. Surface it as Unmet rather than matching against black.
        out.kind = PlanKind::Unmet;
        out.health = HealthState::Broken;
        out.recipe = {};
        out.component_ams_keys.clear();
        return;
    }
    const PhysicalSlot* best_direct = nullptr;
    double best_direct_de = std::numeric_limits<double>::max();
    for (const PhysicalSlot* s : same_type) {
        if (!s->color.IsOk()) continue; // can't compute an honest ΔE for this slot
        double de = color_delta_e00(target, s->color);
        if (de < best_direct_de) { best_direct_de = de; best_direct = s; }
    }
    if (best_direct && best_direct_de < kColorMatchDirectThreshold) {
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
        out.component_tray_names.assign(1, best_direct->tray_name);
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
    // Skip slots with an invalid colour for the same reason as the direct loop
    // above: GetAsString(wxC2S_HTML_SYNTAX) on an invalid wxColour returns
    // "#000000" (black), so including it would let a colour-unresolvable slot
    // silently contribute black to the blend — a hidden substitution (PRD §5).
    // Track which slots made it into the palette so component_ams_keys aligns.
    std::vector<const PhysicalSlot*> palette_slots;
    palette_slots.reserve(same_type.size());
    for (const PhysicalSlot* s : same_type) {
        if (!s->color.IsOk()) continue;
        palette.push_back(s->color.GetAsString(wxC2S_HTML_SYNTAX).ToStdString());
        palette_slots.push_back(s);
    }
    if (palette.size() < 2) {
        // Fewer than 2 honest-colour same-type slots: no blend possible. (1 slot
        // was already handled by the direct path above if it qualified, so here
        // it either didn't meet the direct threshold or its colour was invalid.)
        out.kind = PlanKind::Unmet;
        out.health = HealthState::Broken;
        out.recipe = {};
        out.component_ams_keys.clear();
        out.component_tray_names.clear();
        return;
    }

    out.recipe = build_best_color_match_recipe(
        palette, target, /*min_component_percent=*/0, /*max_component_percent=*/100,
        /*check_compatible=*/true);

    if (out.recipe.valid) {
        out.kind = PlanKind::Synthesised;
        // Store the FULL recipe verbatim (component_a/b, mix_b_percent,
        // manual_pattern, gradient_*, preview_color, delta_e) — no projection,
        // so nothing the solver (or later MixedFilamentDialog) produces is lost.
        // component_a/b are 1-based indices into `palette`, which was built
        // parallel to `palette_slots` (same iteration order, invalid-colour slots
        // excluded from BOTH). So component_ams_keys/tray_names must be filled
        // from palette_slots — indexing them from `same_type` would misalign
        // recipe components to the wrong slots whenever a same-type slot had an
        // unresolvable colour and was skipped.
        out.component_ams_keys.clear();
        out.component_ams_keys.reserve(palette_slots.size());
        out.component_tray_names.clear();
        out.component_tray_names.reserve(palette_slots.size());
        for (const PhysicalSlot* s : palette_slots) {
            out.component_ams_keys.push_back(s->ams_key);
            out.component_tray_names.push_back(s->tray_name);
        }
        out.health = (out.recipe.delta_e < kTunableDeltaE) ? HealthState::Tunable : HealthState::Broken;
    } else {
        // Same-type slots exist but no valid blend — unmet (colour-wise
        // unreachable even with synthesis).
        out.kind = PlanKind::Unmet;
        out.health = HealthState::Broken;
        out.component_ams_keys.clear();
        out.component_tray_names.clear();
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
    e.health = (e.recipe.delta_e < kColorMatchDirectThreshold)  ? HealthState::Perfect
             : (e.recipe.delta_e < kTunableDeltaE) ? HealthState::Tunable
                                                   : HealthState::Broken;
}

void FulfillmentStore::mark_stale()
{
    for (FulfillmentEntry& e : m_entries) e.stale = true;
}

bool FulfillmentStore::has_stale() const
{
    for (const FulfillmentEntry& e : m_entries)
        if (e.stale) return true;
    return false;
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

void FulfillmentStore::set_direct_slot(unsigned int design_extruder, int slot,
                                        const std::string& tray_name)
{
    for (FulfillmentEntry& e : m_entries) {
        if (e.design_extruder == design_extruder) {
            e.kind = PlanKind::Direct;
            e.recipe.valid = true;
            e.recipe.component_a = 1;
            e.recipe.component_b = 1;
            e.recipe.mix_b_percent = 0;
            e.component_ams_keys.assign(1, slot);
            e.component_tray_names.assign(1, tray_name);
            return;
        }
    }
}

void FulfillmentStore::set_direct_with_color(unsigned int design_extruder, int slot,
                                             const wxColour& realised_color, const std::string& design_color_hex,
                                             const std::string& tray_name)
{
    for (FulfillmentEntry& e : m_entries) {
        if (e.design_extruder != design_extruder) continue;
        e.kind = PlanKind::Direct;
        e.recipe.valid = true;
        e.recipe.component_a = 1;
        e.recipe.component_b = 1;
        e.recipe.mix_b_percent = 0;
        e.recipe.preview_color = realised_color;
        // Compute ΔE vs the design colour.
        wxColour dc(design_color_hex);
        e.recipe.delta_e = (dc.IsOk() && realised_color.IsOk())
                         ? color_delta_e00(dc, realised_color)
                         : std::numeric_limits<double>::infinity();
        e.health = (e.recipe.delta_e < kColorMatchDirectThreshold) ? HealthState::Perfect
                 : (e.recipe.delta_e < kTunableDeltaE)             ? HealthState::Tunable
                                                                  : HealthState::Broken;
        e.component_ams_keys.assign(1, slot);
        e.component_tray_names.assign(1, tray_name);
        e.locked = true;   // user explicitly chose this filament
        e.stale = false;
        return;
    }
}

void FulfillmentStore::apply_edited_recipe(unsigned int design_extruder,
                                           unsigned int component_a, unsigned int component_b, int mix_b_percent,
                                           const std::string& manual_pattern,
                                           const std::string& gradient_component_ids,
                                           const std::string& gradient_component_weights,
                                           const std::vector<int>& component_ams_keys,
                                           const std::vector<std::string>& component_tray_names)
{
    for (FulfillmentEntry& e : m_entries) {
        if (e.design_extruder != design_extruder) continue;
        e.recipe.valid = true;
        e.recipe.component_a = component_a;
        e.recipe.component_b = component_b;
        e.recipe.mix_b_percent = std::clamp(mix_b_percent, 0, 100);
        e.component_ams_keys = component_ams_keys; // update slot mapping for the new palette
        e.component_tray_names = component_tray_names;
        e.recipe.manual_pattern = manual_pattern;
        e.recipe.gradient_component_ids = gradient_component_ids;
        e.recipe.gradient_component_weights = gradient_component_weights;
        // Honest ΔE: the user just changed the recipe, so the prior ΔE (computed
        // against the OLD recipe) no longer applies. Invalidate it rather than
        // show a stale number that contradicts the new recipe; the next Match
        // re-solves and refreshes. Health is Tunable: the user has intervened, so
        // the row is "user-accepted, pending re-verification".
        e.recipe.delta_e = std::numeric_limits<double>::infinity();
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

void FulfillmentStore::reset_all()
{
    for (FulfillmentEntry& e : m_entries) { e.locked = false; e.stale = true; }
    m_ever_solved = false;
}

void FulfillmentStore::clear_all_locks()
{
    for (FulfillmentEntry& e : m_entries) e.locked = false;
}

} // namespace GUI
} // namespace Slic3r
