# Round 17 — locked-preserve component_colors invariant + design_to_device coverage

Harness: correctness, PRD §4.3. Files: FulfillmentStore.cpp solve().

## Verified (no action)
1. **component_colors invariant under lock-preserve**: when a lock survives, e = *prior
   copies the lock-time component_colors unchanged. They are NOT refreshed to the new
   device colours — correctly, because they are the fixed fingerprint that
   lock_components_unchanged compares the CURRENT colours against on the next solve.
   Refreshing them would make the content-change check a no-op. ✓

2. **design_to_device coverage**: snapshot_design_intent returns one DesignIntent per
   configured extruder (build_design_filament_list iterates filament_presets, the full
   set). So solve() produces an entry for EVERY design extruder (met or unmet),
   max_design_extruder = (design extruder count - 1), and design_to_device is sized to
   cover all of them. The "partial match" failure mode (some design extruders absent
   from design_to_device → identity state_map → phantom) CANNOT occur: either all
   extruders have entries or none (no solve). ✓

3. **palette/palette_slots/component_ams_keys/component_colors alignment**: all four
   built in one shared loop over same_type (skipping invalid-colour slots), so recipe
   component_a/b (1-based into palette) resolve to the correct ams_key/tray/colour. ✓

4. **resolve-dialog lambda lifetime**: captures design_extruder + type_str by value,
   this by raw ptr; row is a grandchild of the panel, can't outlive it. Safe. ✓

## Verdict: APPROVE — no code change. The locked-preserve and full-coverage
invariants hold; the round-08 component_colors fingerprint is used correctly.
