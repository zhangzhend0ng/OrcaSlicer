# Round 21 — three-colour mix degraded to two (gradient space mismatch)

Reported bug: "映射的三个混色被处理成两色混色了" (a mapped three-colour mix was
processed as a two-colour mix). Root cause verified against
MixedFilamentDialog::collect_result and the recipe data model.

## Root cause (two cooperating defects in build_device_filament_space)

**Defect A — Pass 1 only collected the primary pair.**
Pass 1 enumerated recipe components with `ncomp = (Direct || mix==0) ? 1 : 2`,
collecting only component_a/component_b into the device-space `rows`/colours
array. A 3+ colour mix stores its extra component ids in gradient_component_ids
(palette-local, 1-based, same space as component_a/b — verified: dialog's
get_filament_index returns the m_filament_colours index, collect_result does +1,
and FulfillmentPanel passes palette_ams_keys parallel to the dialog palette).
So the third slot was never added to `rows` → absent from device_colors.

**Defect B — Pass 2 passed gradient_component_ids in the WRONG id space.**
Pass 2 remapped component_a/b to device-space (T-number+1) via component_device_id,
but assigned `be.gradient_component_ids = e.recipe.gradient_component_ids` VERBATIM
— those are PALETTE-LOCAL ids. MixedFilamentManager reads them as device-space
(clamps to device_colors.size(), indexes colours by [id-1]). So even if the third
slot HAD been in device_colors, its id was the palette-local number, pointing at
the wrong device filament. The combination of A+B made any 3-colour mix silently
lose/degrade its third component.

## Fix

**Pass 1**: collect ALL palette-local component ids the recipe references —
component_a, component_b (synth only), and every id in gradient_component_ids
(decoded via decode_gradient_component_ids(.,0), bounds-checked against
component_ams_keys). rows/device_colors now covers every slot the recipe needs.

**Pass 2**: remap gradient_component_ids from palette-local → device-space before
storing on the batch entry — decode each id, resolve via component_device_id,
re-encode with encode_gradient_component_ids. If any gradient component is
unmapped (slot vanished on device change), drop the whole synth (honest fallback
to design colour, PRD §5) rather than emit a partial/wrong gradient. Weights are
positional and parallel to the decoded id list, so they need no reordering as
long as id order is preserved through the remap.

## Verified against MixedFilamentDialog::collect_result
- MODE_RATIO 3-row (line 3257): gradient_component_ids = all 3 row ids, weights =
  r0/r1/r2 — parallel, order preserved by my remap. ✓
- MODE_MATCH 3-weight tri (line 3318): ids = weight>0 tri indices, weights parallel. ✓
- MODE_MATCH 2-colour gradient (line 3346): ids = {a,b}, weights empty — my remap
  yields {dev_a,dev_b}, weights stay empty; normalize_gradient_component_weights
  returns empty for size mismatch → Simple/default path, same as before (no
  regression). ✓
- id space: dialog's filament_indices pushes the raw m_filament_colours index j
  (line 1428), get_filament_index returns it, collect_result does +1 → palette-
  local 1-based, identical to component_a/b's space. ✓

## Adversarial re-check
- 2-colour mix (no gradient ids): Pass 1 collects a/b only; Pass 2 clears gradient
  fields. Behaviour unchanged. ✓
- 3-colour mix, all slots present: Pass 1 collects all 3; Pass 2 remaps all 3 to
  device-space; MixedFilamentManager sees correct device ids + device-space colours.
  Third colour preserved. ✓
- 3-colour mix, one slot vanished on device change: Pass 2 drops the synth (honest),
  not a silent wrong-colour gradient. ✓
- Build green.

## Verdict: APPROVE (fix applied), build green. This is a real user-reported
correctness bug, not the routine round-01..20 calibre.
