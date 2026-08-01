# Round 01 — Harness-Driven Review

Scope: demo/filament-design-zone working tree (Fulfillment layer demo).
Harnesses applied (B1 discovery): UB (N), dangling-references (N), const-correctness (N),
exception-safety (N), integer-safety (N), type-safety (N), thread-safety (N),
performance (N), parameter-validation (C), input-validation (N), parsing-and-validation (C).

## Findings

| # | File:line | Harness / tier | Finding | Disposition |
|---|-----------|----------------|---------|-------------|
| F1 | FulfillmentPanel.cpp:339-341, 391-393 | UB-3 out-of-bounds (N) | `std::equal(fd.m_type.begin(), fd.m_type.end(), e.design_type.begin(), pred)` reads `e.design_type` up to `fd.m_type.size()` chars. If `e.design_type` is SHORTER, this is an out-of-bounds read (UB). This is the EXACT pitfall FulfillmentStore.cpp:130-132 was written to avoid with `boost::iequals`. | **FIX (Round 1)** |
| F2 | FulfillmentSliceMapping.cpp:68-81 | UB-4 use-after-move (N), perf | `need_slot` returns `const DeviceFilamentRow*` = `&rows.back()` immediately after `push_back` (may realloc). Returned ptr is discarded by the only caller (Pass 1 loop). Dead return + dangling trap. | FIX (Round 2) — refactor to `void` |
| F3 | FulfillmentSnapshots.cpp:17,39 | const-correctness-1/7 (C) | `const_cast<PresetBundle*>(&bundle)` casts away const to call `build_*_filament_list` which only READS the bundle. | Document / wide-API, defer |
| F4 | FulfillmentStore.cpp:70 | perf (A) | `solve()` calls `find()` (linear) inside the per-intent loop → O(N²). At N≤64 trivial. | No-action (in budget) |
| F5 | FulfillmentSliceMapping.cpp:100,170 | integer-safety-3 (C) | `palette_idx > e.component_ams_keys.size()` compares `unsigned int` to `size_t`; well-defined via promotion, but conversion noise. | Low — defer |
| F6 | FulfillmentPanel.cpp:143-147 | correctness | `on_match` toggles expected_view false→true to force repaint, but `set_expected_view` early-returns when `active==on` (Plater.cpp:22333). If view was OFF, the false call no-ops, true call turns it ON — changes user state. If ON, toggles off+on (correct). The OFF path is benign here (only fires when already ON), but reads as state mutation. | Verify (Round 3) |

## Verdict for Round 1
**REQUEST CHANGES** — F1 is a confirmed (N)-tier out-of-bounds read. Fixed below.

## Adversarial re-check of the F1 fix
- Replaced BOTH `std::equal(begin,end,other.begin(),pred)` with `boost::iequals(a,b)` — length-safe.
- `boost/algorithm/string/predicate.hpp` already included transitively? No — must add the include in Panel.
- Same `is_none_filament` reuse is preserved; only the type-compare changed.
- Behaviour preserved: case-insensitive equality, now correct when lengths differ (returns false instead of OOB read).
