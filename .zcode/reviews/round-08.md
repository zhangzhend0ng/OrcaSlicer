# Round 08 — Locked recipe silently rebound on same-type slot swap

Harness: PRD §4.3 (physical-stock-change invalidation), §5 (gaps spoken),
correctness. File: FulfillmentStore.cpp solve() + lock helpers.

## Finding
A locked recipe survives recompute while its component_ams_keys are all present
in the current device snapshot (lock_components_present). But "present" checks
only the ams_key integer, not the slot's CONTENT. Two real failure modes:
1. Same-type slot swap on a real machine: slot 2 was red PLA when the user
   locked a mix using it; the user (or MQTT) swaps slot 2 to blue PLA. ams_key 2
   is still present → lock survives → the recipe now silently blends blue instead
   of red. Wrong colour, no warning. PRD §5 violation.
2. mock<->real transition: the round-2 comment in solve() explicitly flagged that
   the same ams_key integer can name a different physical filament across the
   transition, but lock_components_present couldn't detect it.

## Fix
- Added FulfillmentEntry.component_colors: a per-component hex snapshot of the
  device colour each component pointed at when the recipe was locked/solved.
  Populated at every site that fills component_ams_keys (solve_intent direct +
  synth, set_direct_with_color, apply_edited_recipe; set_direct_slot clears it
  since its legacy API has no colour).
- apply_edited_recipe now takes component_colors; the Panel caller passes the
  dialog palette (parallel to palette_ams_keys/tray_names).
- Added lock_components_unchanged(): compares each component's captured colour to
  the current slot's colour via color_delta_e00, using kTunableDeltaE as the
  "same filament vs different filament" threshold (within the band = batch drift,
  kept; beyond = different filament, lock dropped). Legacy locks with no
  fingerprint (empty component_colors) skip the check and behave as before.
- solve() builds a device ams_key→colour map and requires BOTH
  lock_components_present AND lock_components_unchanged for a lock to survive.

## Adversarial re-check
- Same-type swap (red→blue PLA at slot 2, ΔE>5): lock dropped, entry re-solved
  against live stock → user sees the new reality. ✓
- Batch drift (red→slightly-different-red, ΔE<5): lock kept (intentional — same
  filament, vendor variance). ✓
- mock→real transition (different filament at same ams_key, ΔE>5): lock dropped. ✓
- Legacy lock (component_colors empty): unchanged behaviour. ✓
- Misaligned sizes (defensive): treated as trust-presence, not lock-drop. ✓
- kTunableDeltaE is file-local (line 17), visible to the anon-namespace helper. ✓

## Verdict: APPROVE (fix applied), build green.
