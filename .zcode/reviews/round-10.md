# Round 10 — AGENTS.md anti-reinvention audit + concurrency invariant check

Harness: AGENTS.md "Reuse Before You Build", thread-safety (N), PRD §12.4.

## Anti-reinvention audit (all 5 dimensions)
1. **Data model**: PASS. FulfillmentEntry stores MixedColorMatchRecipeResult verbatim
   (FulfillmentStore.hpp:52), with an explicit Phase-1-scope note explaining why
   MixedFilament is NOT stored prematurely (avoids the ams_key↔global-ID alignment
   problem). No bespoke recipe subset.
2. **Algorithm**: PASS. color_delta_e00 (9 uses), build_best_color_match_recipe (solve
   + edit paths). No re-implemented ΔE or blend search.
3. **Widget/dialog**: PASS. MixedFilamentDialog (mix editor), MachineFilamentPicker
   (physical picker), get_extruder_color_icon (swatches). No bespoke control.
4. **Signal**: PASS. load_ams_list reused in DeviceFilamentZone. No invented refresh path.
5. **Constants**: PASS. kColorMatchDirectThreshold referenced by name (no local copy);
   kTunableDeltaE=5.0 is local but legitimately new (the matcher has no "tunable" band).
   The two type-compare sites now both use boost::iequals (round-01), linked via a
   MUST-stay-in-sync comment (AGENTS.md §6).

## Concurrency invariant (PRD §12.4)
- Demo code never touches the unsynchronised filament_ams_list directly — only via
  build_machine_filament_list + m_connect_machine_info_list (UI-thread reads).
- All FulfillmentStore mutations (solve/set_*/apply_*/toggle/reset/clear/mark_stale)
  originate from UI-thread handlers (button clicks, wxEVT_TIMER in DeviceFilamentZone,
  slice entry). wxTimer events dispatch on the main loop. Store is UI-thread-owned. ✓
- prepare_slice_inputs' store.solve() (when stale) runs in update_background_process,
  confirmed UI-thread-only (no worker-thread caller). ✓
- PRE-EXISTING HAZARD (out of demo scope): m_connect_machine_info_list is mutated by the
  MQTT parse thread and read here without synchronisation — a data race inherited from
  the existing codebase, NOT introduced by this demo. PRD §12.4 acknowledges it. Fixing
  it is a structural change to the network layer, correctly deferred.

## Verdict: APPROVE — no code change. Audit confirms reuse discipline + UI-thread
ownership. The one concurrency hazard is pre-existing and out of scope.
