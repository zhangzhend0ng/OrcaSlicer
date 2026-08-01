# Round 11 — remove unused `device` param from recompute_health_from_recipe

Harness: interface-contracts (N) — narrow/wide contracts, no misleading signatures.
File: FulfillmentStore.hpp/.cpp recompute_health_from_recipe.

## Finding
recompute_health_from_recipe(const DesignIntent&, const std::vector<PhysicalSlot>& device,
FulfillmentEntry&) took `device` but never read it — the body only recomputes ΔE
from the recipe's preview_color vs the new intent colour. A misleading unused
parameter suggests the function re-validates the device, which it doesn't (and
doesn't need to: solve() already ran lock_components_present +
lock_components_unchanged before calling it, so the recipe's components are
current).

## Fix
Dropped the `device` parameter from the declaration, definition, and the single
call site in solve(). Comment now states WHY the device isn't needed (the upstream
lock-content checks), so a future reader doesn't re-add it thinking it was missed.

## Adversarial re-check
- No behaviour change (param was unread).
- solve() call site updated. ✓
- Comment explains the upstream invariant. ✓

## Verdict: APPROVE (cleanup), build green.
