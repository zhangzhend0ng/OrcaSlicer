# Round 05 — Silent black-substitution from invalid colours

Harness: input-validation (N) item 1/4, error-handling (C) item 1, PRD §5.
File: FulfillmentStore.cpp solve_intent (Pass 2: direct + synth).

## Finding
color_delta_e00 (MixedColorMatchHelpers.cpp:349) reads lhs.Red()/Green()/Blue()
unconditionally — on an invalid (default-constructed) wxColour these read as 0,
so the colour is silently treated as BLACK, yielding a finite, plausible ΔE.
Two leaks of this into the matcher:

1. Target colour: wxColour target(intent.color) was never IsOk()-checked. If the
   design intent's hex were ever unparseable, matching proceeded against black.
2. Slot colour: snapshot_device_stock only sets s.color when try_parse_color_match_hex
   succeeds, else leaves it invalid. Such a slot still entered the same_type list
   (if its type matched) and:
   - the direct loop computed ΔE(target, invalid) → could elect it "best direct";
   - the synth palette did s->color.GetAsString(...) → "#000000" → black entered
     the blend.

This is exactly the silent colour substitution PRD §5 forbids: a colour gap
masquerades as a black match. (In practice intent.color is always valid hex via
PrimaryColor()'s fallback, and device colours come from device JSON — but the
matcher must be robust to an unparseable value, not assume its callers sanitise.)

## Fix (solve_intent)
- Guard target.IsOk() before matching; else mark the entry Unmet/Broken (colour
  gap spoken, not silently matched against black).
- Skip slots whose colour is invalid in BOTH the direct loop and the synth
  palette build.
- Build component_ams_keys/tray_names from the new palette_slots (parallel to the
  filtered palette), NOT from same_type — otherwise excluding an invalid-colour
  slot from the palette would misalign recipe component_a/b to the wrong ams_key.
- If fewer than 2 honest-colour same-type slots remain, no blend is possible →
  Unmet/Broken.

## Adversarial re-check (the alignment hazard)
Excluding invalid-colour slots from `palette` but leaving component_ams_keys
indexed from `same_type` would be a NEW bug: component_a=N (1-based into palette)
would resolve to same_type[N-1], which after a skip is the WRONG slot. Fixed by
introducing palette_slots (parallel, same order) and indexing keys from it.
Verified: palette and palette_slots are built in one shared loop, so order is
identical; component_a → palette[N-1] → palette_slots[N-1].ams_key. ✓

## Verdict: APPROVE (fix applied), build green.
