# Fulfillment Layer — Phase 1 Implementation Design

Status: Draft, paired with `Fulfillment_Layer_PRD.md`
Last updated: 2026-07-31
Scope: Phase 1 only — experience validation. See PRD §10 for phase boundaries.

---

## 0. Phase 1 scope (recap, honest)

Phase 1 delivers a **minimum closed loop** that proves the core experience,
with deliberate deferrals (per PRD §9.4, §10, §12):

- ✅ Design View health dots (live "can it?" hint, cached/cheap).
- ✅ Fulfillment Plan view (single canvas, type-tiered rows, real-stock solve,
  per-row fine-tune + lock, pre-print report). Named "Fulfillment Plan", NOT
  "Expected View" (3D injection is Phase 2 — PRD §5.2).
- ✅ Pre-print physical gate (mandatory report, blocks on ✗).
- ⏸️ NOT in Phase 1: structural Design-Layer read-only enforcement (legacy
  sync/match still write design — PRD §9.4); Fulfillment persistence (in-memory
  only — PRD §12.2); 3D Expected View; multi-device.

**The one rule Phase 1 honours in code:** new fulfilment code paths read the
Design Layer (preset_bundle project_config) **read-only**, and write only into
the new in-memory Fulfillment store. Legacy paths are untouched (they remain
design-writing). This gives an honest demo of the architecture without the
Phase-2 migration cost.

---

## 1. Data model

### 1.1 What already exists (reuse, don't rewrite)

| Concern | Existing | Location |
|---|---|---|
| Design intent (colour) | `filament_colour` (coStrings) | `PrintConfig.cpp:2056` |
| Design intent (type) | `filament_type` (coStrings) | `PrintConfig.cpp:2350` |
| Design → model binding | model `extruder_id` | `3DScene.cpp:684,708` |
| Device stock | `preset_bundle->filament_ams_list` | `PresetBundle.hpp:168` |
| Colour distance | `color_delta_e00(wxColour, wxColour)` | `MixedColorMatchHelpers.hpp:97` |
| Tray DTO | `FilamentData {index,name,type,color}` | `filamentsync/FilamentData.hpp` |
| Solver core | `batch_match_model_colors(...)` | `MixedColorMatchHelpers.cpp:1608` |
| Design-change signal | `EVT_FILAMENT_USAGE_CHANGED` | `Plater.cpp:345` |
| Device-change refresh | `Sidebar::load_ams_list` | `Plater.cpp:8596` |

### 1.2 New: the Fulfillment store (in-memory, Phase 1)

A single owner, UI-thread-affined (PRD §12.4), holding the derived plan.

```cpp
// src/slic3r/GUI/Fulfillment/FulfillmentStore.hpp  (new dir)
namespace Slic3r::GUI {

// One design intent's realisation plan. Immutable snapshot except via
// Store mutators. The "design intent" identity is the 0-based extruder index,
// which the Design Layer guarantees stable within a session.
enum class PlanKind   { Direct, Synthesised, Unmet };
enum class HealthState { Perfect, Tunable, Broken };   // green/yellow/red+glyph

struct FulfillmentEntry {
    unsigned int   design_extruder = 0;     // 0-based; the intent's identity
    std::string    design_color;            // hex, snapshot at solve time
    std::string    design_type;             // snapshot

    PlanKind       kind = PlanKind::Unmet;
    HealthState    health = HealthState::Broken;

    // Direct: the physical slot that satisfies it.
    int            direct_slot = -1;        // -1 = none
    // Synthesised: components + ratio (reuses batch_match recipe shape).
    std::vector<unsigned int> synth_component_slots;
    int            synth_ratio_b_percent = 0;
    double         delta_e = std::numeric_limits<double>::infinity();

    bool           locked = false;          // user-pinned; survives recompute
    bool           stale  = true;           // needs (re)solve
};

// A single solve result, keyed by design_extruder.
class FulfillmentStore {
public:
    // Snapshot design intent + device stock, solve, populate entries.
    // Runs the cheap parts on UI thread; the ΔE solve itself is delegated to
    // batch_match on a worker thread (PRD §12.3). Returns when solved.
    void recompute();

    // Read access for the canvas / health dots / pre-print gate.
    const std::vector<FulfillmentEntry>& entries() const { return m_entries; }
    const FulfillmentEntry* find(unsigned int design_extruder) const;

    // Class-A edits (PRD §5.2.1): write Fulfillment, never Design.
    void set_ratio(unsigned int design_extruder, int ratio_b_percent);
    void set_direct_slot(unsigned int design_extruder, int slot);
    void toggle_lock(unsigned int design_extruder);
    void reset_to_computed(unsigned int design_extruder);   // undo a row
    void reset_all();                                       // full reset
    void clear_all_locks();                                 // PRD §12.1

    // Invalidate without solving (called on design/device change signals).
    void mark_stale();

    // Health roll-up for the pre-print gate / global indicator.
    struct HealthRollup { int perfect=0, tunable=0, broken=0; };
    HealthRollup rollup() const;

private:
    std::vector<FulfillmentEntry> m_entries;
    // cached snapshots to detect what changed since last solve
    std::vector<std::pair<std::string,std::string>> m_last_design; // color,type
    std::vector<FilamentData> m_last_device;
};

} // namespace
```

**Why keyed by `design_extruder` (0-based):** it is the stable identity of a
design intent within a session — the model paints to it, the Filaments list is
indexed by it. Locks bind to it (PRD §4.3 "design-intent id"). When a design
intent is deleted (filament removed), its entry is dropped and its lock goes
with it — no ghost locks.

**Phase 1 honesty:** this store is **in-memory only** (PRD §12.2). Closing the
project loses it; reopening marks all stale. Acceptable for experience
validation; persistence is Phase 2.

---

## 2. Class boundaries & file layout

```
src/slic3r/GUI/Fulfillment/                 (new directory)
  FulfillmentStore.hpp / .cpp               — the derived plan (no UI)
  FulfillmentSolver.hpp / .cpp              — thin wrapper: reads Design+Physical
                                               read-only, calls batch_match core,
                                               translates result -> FulfillmentEntry
  FulfillmentCanvas.hpp / .cpp              — the Expected/Plan view widget
  HealthDot.hpp / .cpp                      — the green/yellow/red glyph widget
src/slic3r/GUI/Plater.cpp                   — wire store into Sidebar; gate print
src/slic3r/GUI/Sidebar / Plater.hpp         — accessors
```

**Separation enforced by directory + dependency direction:**
`FulfillmentStore`/`Solver` depend only on libslic3r + `MixedColorMatchHelpers`
+ `FilamentData` — **no wx UI**. `FulfillmentCanvas`/`HealthDot` depend on the
store. Plater depends on all. This keeps the plan logic testable without a GUI.

---

## 3. The three Phase-1 components

### 3.1 Health dot (Design View)

- A small glyph next to each Filaments row (green ✓ / yellow ~ / red ✗ +
  shape, PRD §12.5 colour-blind redundancy).
- **Computation is cheap (PRD §12.3):** reads `FulfillmentStore::find(idx)`;
  if the store is stale/no-prior-solve, shows only the **type-availability**
  check (does any device slot share this intent's type?) — O(slots), no ΔE.
  A neutral "press Match to solve colour" state when type is OK but no ΔE yet.
- **Refresh trigger:** binds `EVT_FILAMENT_USAGE_CHANGED` (design changed) and
  a new `EVT_FULFILLMENT_CHANGED` the store emits after recompute. No per-frame
  work.
- Does **not** trigger a solve — it only reports.

### 3.2 Fulfillment canvas (Fulfillment Plan view)

The single-canvas view from PRD §5.3. Each row = one `FulfillmentEntry`,
columns: design intent (colour+type) | colour match | type match | plan | lock.

- Type column drives row colour (PRD §4): type unmet → red regardless of ΔE.
- ⚙ opens an inline editor for class-A edits (ratio slider / slot picker) —
  writes store, never design.
- 🔒 toggles lock.
- "Resolve" on a broken row opens consequence-stated options. A class-B option
  ("change this part's type") is labelled "Edit design →" and **navigates to
  Design View** rather than editing in-canvas (PRD §5.2.1).
- Bottom: device-stock summary line + "expand details" (reuses the existing
  DeviceFilamentZone as the drawer content — Phase 3 collapses it; Phase 1
  keeps both visible).

### 3.3 Pre-print gate

Hooks the existing print-send path. Before sending:
- read `FulfillmentStore::rollup()`;
- if `broken > 0` → block, show the human-language report, guide to Resolve
  (PRD §6 Flow C, §5 "gaps spoken"). **No silent path.**
- if only `tunable` → show the report with a confirm.

---

## 4. Solve flow (the heart of Phase 1)

```
user presses "Match" / opens canvas
   │
   ▼
FulfillmentSolver::solve():
   1. READ design intent (RO): preset_bundle->project_config
        filament_colour[], filament_type[]  → design set
   2. READ device stock (RO): preset_bundle->filament_ams_list
        → device set (colour, type, exist) per slot
   3. For each design intent:
        a. TYPE FILTER (hard, PRD §4): collect device slots with matching type.
        b. if none → PlanKind::Unmet, health Broken. (type gap — fatal)
        c. else COLOUR MATCH among same-type slots:
             min ΔE = color_delta_e00(design, slot)
             if min ΔE < 1.0 → Direct (pure, PRD pass-1 rule)
             else → delegate to batch_match core for a synth recipe
                   over same-type slots (PRD §6 Flow B; §2 caveat:
                   batch_match's internal preset_bundle reads are audited
                   and parameterised so they don't override our device input)
   4. populate FulfillmentEntry per intent; preserve locked entries (PRD §4.3)
   5. emit EVT_FULFILLMENT_CHANGED → canvas + health dots refresh
```

**The batch_match caveat (PRD §2 / round-1 漏洞1) is addressed here:** before
reusing the solver, `FulfillmentSolver` must audit `MixedColorMatchHelpers.cpp`
internal `preset_bundle` reads and either inject our device-derived inputs or
sever them. If unaddressed, the engine fetches recommended CMYG itself and
conflicts with our device input. This audit is a Phase-1 task item, not deferred.

---

## 5. Wiring into existing code (minimal surface)

| Touch point | Change |
|---|---|
| `Sidebar::priv` | add `FulfillmentStore m_fulfillment;` |
| `Sidebar::Sidebar()` | add a "Fulfillment Plan" toggle button near Filaments title |
| Filaments row build (`Plater.cpp:2710+`) | add a `HealthDot*` per row |
| `EVT_FILAMENT_USAGE_CHANGED` handler | call `m_fulfillment.mark_stale()` + refresh dots |
| `load_ams_list` (end) | call `m_fulfillment.mark_stale()` (device changed) |
| Print-send path | call pre-print gate (rollup check) |
| CMake | add the new `Fulfillment/*.cpp` files |

**No change** to: `sync_ams_list`, `apply_batch_match_to_model`, the slice
pipeline, preset_bundle structure, or 3MF save/load. Phase 1 is **additive
only** — legacy behaviour is untouched, which is what makes it safe.

---

## 6. Build order (incremental, each step compiles & runs)

1. `FulfillmentStore` + `FulfillmentSolver` (no UI) — unit-testable: feed fake
   design + device sets, assert entries/rollup. Build the lib target.
2. `HealthDot` widget + wire to store + `EVT_FILAMENT_USAGE_CHANGED`. Run: dots
   appear, reflect type-availability, update on design change.
3. `FulfillmentCanvas` + "Match" solve wiring. Run: canvas populates with
   real-stock solve, type-tiered, ΔE shown.
4. Fine-tune (⚙ ratio/slot) + lock (🔒) + reset/clear-locks (PRD §12.1).
5. Pre-print gate. Run: blocked on broken, report shown.
6. batch_match audit task (§4 caveat) — verify device input isn't overridden.

Each step is independently verifiable; a failure localises cleanly.

---

## 7. Phase 1 exit criteria

- [x] Health dots render with shape+colour, update on design/device change,
      stay cheap (no solve on authoring). *(implemented as the DeviceFilamentZone
      summary + per-intent glyph rows rather than per-Filaments-row dots — see §8.)*
- [x] Canvas solves against **real device stock** (not CMYG), type-tiered,
      ΔE correct. *(solved in FulfillmentStore::solve_intent via the pure
      `build_best_color_match_recipe`, not `batch_match_model_colors` — see §8.)*
- [ ] Fine-tune writes Fulfillment only; Design Layer (filament_colour/type)
      byte-identical before/after (assert in debug builds). *(store + mutators
      done; inline ⚙ editor not yet wired — Phase 1.5.)*
- [x] Locks survive recompute; drop on intent delete/type-change (PRD §4.3).
      *(caught & fixed a lock-clobbering bug in pre-UI self-review.)*
- [x] Pre-print gate blocks on any broken row; no silent send.
- [x] All new code compiles via the worktree build; legacy flows unchanged.
      *(622/622 links clean; sync_ams_list / apply_batch_match untouched.)*

---

## 8. Implementation deviations (what actually shipped vs §1-§6)

Recorded so Phase 2 starts from reality, not the idealised plan.

1. **No separate FulfillmentSolver class.** The solve logic was thin enough to
   fold into `FulfillmentStore::solve_intent` (static) + `FulfillmentSnapshots`
   (read-only preset_bundle adapters). The directory is `Fulfillment/` with
   `FulfillmentStore.{hpp,cpp}` + `FulfillmentSnapshots.{hpp,cpp}` only.

2. **`build_best_color_match_recipe` instead of `batch_match_model_colors`.**
   The single-colour pure helper (`MixedColorMatchHelpers.cpp:358`, verified no
   preset_bundle reads) replaced the heavier batch solver. This **eliminated the
   §4/§6 audit task entirely** — there is no CMYG/full_spectrum coupling to sever.
   The store feeds it the real device-derived palette per intent.

3. **Health display lives in DeviceFilamentZone, not per-Filaments-row.** Wiring a
   dot into each dynamically-built Filaments row (double-column, add/del on the
   fly) is invasive. Instead the DeviceFilamentZone (the device-reality panel)
   gained a Match button, a colour-coded summary line, and per-intent rows
   (swatch + ✓/~/✗ glyph + type + human plan). Same information, single panel,
   zero Filaments-row churn. This also fits the architecture: device panel IS the
   reality counterpart where fulfilment status belongs.

4. **Store owned by Sidebar::priv, not a global.** `Sidebar::priv::m_fulfillment_store`
   is a value member; exposed via `Sidebar::fulfillment_store()`. Plater::priv's
   `EVT_FILAMENT_USAGE_CHANGED` handler and `load_ams_list` reach it through that
   accessor. (Earlier draft wrongly put the access in Plater::priv — corrected:
   the two `priv` classes are distinct.)

5. **Pre-print gate only blocks when a match was run and left broken rows.** A
   never-run match does not nag. This honours PRD §5 ("gaps spoken" = detected
   gaps) without turning every send into a forced-checkpoint.

6. **Inline ⚙ fine-tune editor deferred (Phase 1.5).** Store mutators
   (set_ratio/set_direct_slot/toggle_lock/reset/clear-locks) are implemented and
   tested at the API level, but the per-row slider/slot-picker UI is not wired
   yet. The lock/reset/clear path is reachable conceptually; the ratio slider is
   the visible gap.

7. **Solver is synchronous on UI thread in Phase 1.** `build_best_color_match_recipe`
   per intent is cheap for typical counts, so the async/worker-thread plumbing
   (PRD §12.3) was deferred. The 64-colour worst case remains an open perf item.

## 9. Phase 1.5 / Phase 2 entry points

- **Phase 1.5:** wire the inline ⚙ editor (ratio slider, slot picker) to the
  store mutators; add the 🔒 toggle + "reset row"/"clear locks" buttons to the
  canvas. Lowest-risk, finishes the interaction spec.
- **Phase 2:** relocate `mixed_filaments` out of preset_bundle; sever legacy
  design-writes (sync_ams_list / apply_batch_match → Fulfillment); 3D Expected
  View colour injection; Fulfillment persistence (3MF); async solver.
