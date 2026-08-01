# Round 13 — empty synth manager erased design-layer mixed_filament_definitions

Harness: correctness, PRD §1/§3 (design not silently changed). File: FulfillmentSliceMapping.cpp.

## Finding
build_device_filament_space unconditionally did:
    out.config.opt_string("mixed_filament_definitions", true) = mgr.serialize_custom_entries();
out.config is a copy of full_config, which carries the user's design-layer
mixed_filament_definitions. When the manager added NO synthesised rows (every
recipe direct, or all synth rows dropped by MAXIMUM_FILAMENT_NUMBER / clamp
paths), serialize_custom_entries() returns "" — so the assignment ERASED the
user's design-layer mixes for this slice run. They'd silently not apply.

(The rest of the SliceMapping synth path was reviewed this round and is correct:
Pass 1 collects slots with dedup; mix_b_percent==0 / a==b degenerate synths are
treated as direct consistently across Pass 1/2/4; synth_order||assigned_ids
parallelism holds; add_batch_custom_filaments clamps to [1,n] matching our
T-number-indexed palette; num_total = num_physical + enabled_count() matches
dropped-row accounting.)

## Fix
Only overwrite mixed_filament_definitions when mgr.enabled_count() > 0. When the
manager is empty, the existing (design-layer) string is preserved, keeping the
user's mixes live. When synths ARE added, the overwrite is correct and necessary:
the device-space config's palette is T-number-indexed (remapped device colours),
so the design-layer mix string (which indexes the design palette) would point at
the wrong colours — the fulfilment synth string is the authoritative definition
for the device-space slice.

## Adversarial re-check
- No synth rows + user has design mixes: preserved, mixes apply. ✓
- Synth rows added: fulfilment string replaces design string (correct — device
  palette is remapped). ✓
- build_device_filament_space returns nullopt when rows empty AND no realisable
  entry, so this path only runs with ≥1 row; the empty-mgr case is "rows exist
  but all are direct", which is the case the fix protects. ✓

## Verdict: APPROVE (fix applied), build green.
