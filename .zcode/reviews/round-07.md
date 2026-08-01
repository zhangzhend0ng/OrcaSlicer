# Round 07 — remap_extruder_field guard re-introduced phantom-filament leak

Harness: correctness/logic, error-handling (C), PRD §1 (G-code must reference only
real device filaments).
File: Plater.cpp prepare_slice_inputs, remap_extruder_field lambda.

## Finding
The rewrite of volume/object/layer-range `extruder` fields (added in the prior
"empty slot leak" fix) guarded with:
    if ((size_t)e >= state_map.size() || (int)e > num_total) return;
`e` is a 1-based DESIGN extruder; `num_total` is the DEVICE count. When the design
has more extruders than the device (8-colour design on a 4-extruder device),
design extruders 5-8 have `e > num_total` → early return UNMAPPED. Those volumes
kept their original design-space extruder index against the device-space config,
leaking phantom filaments into the slice / filament list — the exact failure the
rewrite exists to prevent.

This is a guard-domain error: `state_map[e]` is indexed by the DESIGN id and
already holds the correct DEVICE id (real or fallback) for every design extruder
in range. The DESIGN-vs-DEVICE count comparison is meaningless here; the only
valid bounds check is against state_map's size.

(The sibling guard at line 13122 — `device_id > num_total` on the RESOLVED device
id — is correct: there both sides are device-space. Left unchanged.)

## Fix
- Drop the `(int)e > num_total` early-return; keep only the state_map-size check.
- Add a defensive post-mapping clamp: if `state_map[e]` somehow exceeds num_total,
  clamp to 1 (first physical slot) rather than write an out-of-range extruder.
- `mapped != e` write-guard preserved (idempotent).

## Adversarial re-check
- 8-colour design, 4-extruder device, design extruder 6 unfulfilled: previously
  e=6 > num_total=4 → unmapped (phantom). Now state_map[6] holds the fallback
  device id → volume rewritten → no phantom. ✓
- Fully-fulfilled design (no fallback needed): state_map[e] == real device id;
  behaviour unchanged. ✓
- Defensive clamp never triggers in normal flow (the loop at 13109-13125 only
  writes ids ≤ num_total), but guards against future state_map corruption. ✓

## Verdict: APPROVE (fix applied), build green.
