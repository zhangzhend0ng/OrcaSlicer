# Round 19 — PRD §12.5 degenerate-input robustness scan

Harness: PRD §12.5 (degenerate inputs defined, not crash), input-validation (N).
Full pass over the four defined degenerate cases + final green-build check.

## Case 1 — 0 device slots (all empty)
on_match: device.empty() → dialog, early return (no solve). ✓
prepare_slice_inputs: build_device_filament_space → snapshot_device_stock empty →
slot_by_ams_key empty → need_slot never adds → rows.empty() → nullopt → no remap,
slices with design config as-is. ✓ No crash.

## Case 2 — 0 design colours (no model / unpainted)
on_match: design.empty() → dialog, early return. ✓
solve() with empty design: loop 0 times, m_entries empty, m_ever_solved=true.
refresh_fulfilment → has_solved() true but entries() empty → round-09 empty-rollup
branch: "No design colours to match yet." ✓

## Case 3 — single-colour design
One intent, one same-type slot. ΔE<threshold → direct match. ΔE≥threshold and only
one slot → palette.size()<2 → round-05 guard → Unmet (honest: "can't realise").
FulfillmentPanel mix_btn pads palette with a #C8C8C8 dummy (ams_key=-1) so the
dialog can open; a dummy selection resolves to ams_key -1 → component_device_id
returns 0 → synth skipped, lock dropped next solve. Harmless. ✓

## Case 4 — no type intersection (all-PETG design, all-PLA device)
solve_intent: same_type empty for every intent → all Unmet. rollup {0,0,N} → red.
prepare_slice_inputs: no entry resolves → rows empty → nullopt → no remap, slices
with design config (no silent substitution). The physical mismatch surfaces at the
existing send/print flow. ✓

## Defensive-path check
set_direct_slot (the no-colour legacy API) is never called by the demo — all direct
picks go through set_direct_with_color, which captures component_colors. The empty
component_colors path in lock_components_unchanged (round-08) is therefore defensive
only; correctly skips the colour check rather than dropping locks spuriously. ✓

## Final build
Clean rebuild: exit 0, binary relinked (111901600 bytes, 04:38). All 18 prior fixes
compile and link together.

## Verdict: APPROVE — all PRD §12.5 degenerate inputs handled without crash;
honest signals in each case. Build green.
