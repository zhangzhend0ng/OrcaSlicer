# Round 04 — Untrusted `physical_extruder` → unbounded allocation

Harness: input-validation (N) item 1/2/4, integer-safety (N) item 3/7,
parsing-and-validation (C) item 3.
File: FulfillmentSliceMapping.cpp:126-130 (consumes ConnectMachineInfo.extruder).

## Finding
`machineData.extruder` is parsed verbatim from device WCP JSON
(SSWCP.cpp:1648: `j_value["extruder_map_table"][i].get<int>()`) with NO bounds
check. It flows into PhysicalSlot.physical_extruder → DeviceFilamentRow.
In build_device_filament_space:

    int max_t = -1;
    for (const DeviceFilamentRow& r : rows)
        if (r.physical_extruder > max_t) max_t = r.physical_extruder;
    const int num_physical = all_unmapped ? rows.size() : (max_t + 1);
    std::vector<std::string> t_indexed_colors(num_physical, ...);

If a device (or a malformed/attacker-controlled WCP payload) reports
extruder_map_table = [999999], then max_t=999999, num_physical=1000000, and
t_indexed_colors allocates ~1M entries — an unbounded, input-driven allocation.
Negative values are incidentally safe (max_t stays -1 → all_unmapped fallback),
but large positives are not.

A physical extruder index can never legitimately exceed the number of device
filaments reported (device.size() == WCP filament_official count): a T-number
beyond the slot count names a slot the device does not have.

## Fix
Clamp each row's physical_extruder to [0, device.size()) at row-build time inside
need_slot: values outside that range are treated as unmapped (-1), preserving the
existing Moonraker/Klipper fallback path. This bounds num_physical to at most
device.size(), which is itself bounded by the WCP array length.

## Adversarial re-check
- A legitimate device reports extruder in [0, slot_count). Clamp preserves those. ✓
- A malformed large value → clamped to -1 → row sorts to unmapped tail, fallback
  path (all_unmapped if every row is) sizes by row count. No runaway alloc. ✓
- A malformed negative value → already < 0, treated as -1 (unchanged behaviour). ✓
- Does clamping change the T-number alignment for legit sparse sets (T0/T1/T3)?
  No — those are all < device.size(), so they pass through. ✓
- The clamp lives in need_slot (the single point rows are constructed), so Pass 1
  and the downstream T-indexed array both see the sanitised value. ✓

## Verdict: REQUEST CHANGES — (N)-tier input-validation failure. Fixed below.
