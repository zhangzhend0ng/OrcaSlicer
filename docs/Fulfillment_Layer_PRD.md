# Filament Fulfillment Layer — Design Intent vs. Physical Reality

Status: Draft for later implementation (post-adversarial-review revision r1)
Last updated: 2026-07-31
Owner: Snapmaker Orca engineering
Codename: Fulfillment Layer (履约层)

---

## 0. TL;DR

Today the slicer stores the user's design intent (filament colours, types, model
painting) in a **single mutable state** (`filament_colour`, `preset_bundle`,
model `extruder_id`). Sync-from-AMS and the Colour Mixing Match feature both
**write back into that state** — dropping presets, recolouring the model,
deleting physical slots. The result is the well-documented Bambu-class UX
failure: silent colour substitution, "I didn't know it was the wrong filament
until it printed", and mappings that drift.

This PRD proposes a strict **three-layer separation**: an immutable **Design
Layer** (user sovereignty), a derived **Fulfillment Layer** (how the device will
realise the design — mappings + mixing recipes, editable but never written back
to design), and a read-only **Physical Layer** (what the device actually has
loaded). All sync/match/mix operations live in the Fulfillment Layer and are
forbidden from touching the Design Layer. A **Dual View** (Design / Expected)
lets the user author intent and inspect the realisation plan without the two
ever contaminating each other.

---

## 1. Problem Statement

The current architecture conflates three concerns into one mutable container,
which directly produces the reported pain points:

### 1.1 Sync overwrites design

`Sidebar::sync_ams_list()` (`Plater.cpp:8610`) drops the user's selected
presets and colours and overwrites them with device state. The confirmation
dialog states verbatim: *"Sync filaments with AMS will drop all current
selected filament presets and colours."* This is a write into the Design Layer.

### 1.2 Colour Mixing Match overwrites design

`apply_batch_match_to_model` (`Plater.cpp:2624`) repaints the model, rewrites
the palette, and deletes physical slots (`cleanup_unused_filaments_after_batch_match`,
`Plater.cpp:8295`). A single match operation wholesale re-orders the user's
design intent (which filament each part is assigned to).

### 1.3 Mixing recipes live inside the design container

`MixedFilamentManager` (`src/libslic3r/MixedFilament.hpp`) — the mixing recipes
themselves — is a member of `PresetBundle`, i.e. it is stored **inside the
Design Layer**. Because recipes are reachable from the design container, every
recipe edit/apply mechanically contaminates design state.

### 1.4 Consequences (mapped to user-reported pain)

| Reported pain | Root cause here |
|---|---|
| Silent colour substitution; wrong filament printed ([GH #39442](https://forum.bambulab.com/t/when-filament-not-loaded-it-prints-with-a-different-color/39442)) | §1.1/§1.2 write device reality into design; mismatch never surfaced |
| "I thought AMS would override the slicer" mental break (Reddit r/BambuLab) | §1.1 — authority (design vs device) is ambiguous and unstated |
| Auto-mapping unreliable, forced manual each time ([GH #6350](https://github.com/bambulab/BambuStudio/issues/6350), [#10945](https://github.com/bambulab/BambuStudio/issues/10945)) | Mappings are transient, recomputed, not owned/lockable by user |
| Mappings drift / are forgotten ([forum #145120](https://forum.bambulab.com/t/why-does-bambu-studio-forget-what-filament-is-in-my-ams/145120)) | No persistent, locked mapping asset |
| Colour-only matching picks wrong slot ([GH #2190](https://github.com/bambulab/BambuStudio/issues/2190)) | Type dimension ignored; only colour distance used |

---

## 2. Architecture Constraints (verified against current code)

- Model parts store `extruder_id`, **not** colour (`3DScene.cpp:684,708`). Colour
  is resolved at render time via `extruder_id` → `filament_colour[]`.
  → Colour can be substituted at the render/realisation layer without touching
  the model.
- Main 3D view colour source is `get_extruder_colors_from_plater_config()`
  (`Plater.cpp:21876`), which **unconditionally reads `filament_colour`** from
  config. There is **no injection point** today; the thumbnail path
  (`render_thumbnail_*`) is the only one that accepts an explicit colour vector.
- `batch_match_model_colors()` (`MixedColorMatchHelpers.cpp:1608`) takes
  `(model_colors, physical_colors, min/max %, …) → recipes + ΔE` as its
  **explicit** signature. Its core algorithm (ΔE optimisation, recipe search) is
  reusable. **Caveat — not a pure function:** the implementation also reads
  global `preset_bundle` state internally (`MixedColorMatchHelpers.cpp:636-683`:
  full_spectrum preset lookup, `nozzle_diameter`, mixed-feature flags). So
  reusing it against "device physical colours" is **not** a mere parameter
  swap — every internal `preset_bundle` read site must be audited and either
  parameterised or severed, or the two physical-colour sources (device stock
  we feed in vs. recommended CMYG the engine fetches itself) will conflict.
- `filament_extruder_map` (`app_config`) stores `design_idx → ConnectMachineInfo::index`
  — a **third index space**, distinct from AMS `ams_id*4+tray_id`. Index alignment
  is a Fulfillment-Layer responsibility.
- Mixing recipes already carry `mix_b_percent`, `gradient_component_ids/weights`
  (`MixedFilament.hpp:46-61`) — the recipe model needed for per-recipe fine-tune
  already exists.

---

## 3. The Compass — Six Constitutional Principles

Every architectural and UI decision must pass all six. When in conflict, the
lower-numbered principle wins.

> **§1 Design is sovereignty.** The Design Layer (colours × types × model
> painting) is the single source of truth. Read-only to everything except the
> user. No mechanism may write to it.
>
> **§2 Sync must not modify design.** Device state may be *mapped onto* the
> design, never *poured into* it. Reading the device is allowed; overwriting
> design is forbidden.
>
> **§3 Mixing must not modify design.** A mixing recipe is a *plan to realise
> the design*, not a part of *what the design is*. Recipes may be recomputed
> and edited, but never written back into the Design Layer.
>
> **§4 Type is a hard constraint; colour is a soft constraint.** Type mismatch
> = functional failure (non-negotiable: swap filament or change design). Colour
> mismatch = cosmetic (negotiable: synthesise via mixing). They differ in
> severity and **must** be presented and handled in tiers.
>
> **§5 Gaps must be spoken, never silent.** Any mismatch between design and
> device must be surfaced explicitly, in human language, before printing. Silent
> substitution is prohibited.
>
> **§6 Decision authority rests with the user.** The system proposes and seeds;
> no automatic action may override the user's expressed intent. User decisions
> may be locked, are respected, and are not overwritten by recompute.

**Calibration check** for any proposed feature/screen — answer six questions:
Does it read or write design? Does sync touch design? Does mixing touch design?
Are type and colour tiered? Is mismatch surfaced? Does it override user intent?

---

## 3.5 Non-Goals (scope honesty)

- **Single-device assumption (Phase 1–2).** The Fulfillment Layer is the plan
  *for one currently-selected device*. Multi-device (the same design printed on
  different AMS configurations) is **out of scope and an open problem**: a recipe
  lock, a ΔE, a slot mapping are all device-specific, so switching device
  invalidates the whole Fulfillment Layer. This is acknowledged as unresolved;
  it is not silently assumed away. (Bambu wiki itself notes auto-mapping is
  disabled across multiple devices — a real, shared pain.)
- **Print-parameter conflicts between co-printed types** (e.g. PLA + PETG in the
  same layer needing incompatible temperatures) are not modelled by this PRD.
  They belong to slice-time concerns; here we only ensure type *availability*,
  not type *co-existence feasibility*.
- **Network/printer connection reliability** (the "studio forgets what's in the
  AMS" class of bug) is not addressed — this PRD assumes the Physical Layer is
  trustworthy; if it isn't, all downstream layers inherit the unreliability.

---

## 4. Conceptual Architecture — Three-Layer Separation

```
┌─────────────────────────────────────────────────────────────┐
│  Design Layer                       user sovereignty, RO ext │
│  · model painting: part → design_extruder_id               │
│  · design filaments: design_extruder → (colour, type, cfg) │
│  · This IS the Filaments list, in its true identity         │
│  · Writer: user only. sync/mix/map: FORBIDDEN               │
└─────────────────────────────────────────────────────────────┘
                          ▲ read-only ref ▲
┌─────────────────────────────────────────────────────────────┐
│  Fulfillment Layer        system-derived, editable, recompute│
│  · mapping: design_extruder → physical slot (direct/synth)  │
│  · mixing recipe: components + ratio                         │
│  · lock flags: user-pinned decisions, recompute must keep   │
│  · health / freshness state                                  │
│  · Writer: system recomputes, user fine-tunes. Never writes │
│    back to Design.                                           │
└─────────────────────────────────────────────────────────────┘
                          ▲ read-only ref ▲
┌─────────────────────────────────────────────────────────────┐
│  Physical Layer                     device reality, read-only│
│  · AMS slots: (colour, type, remain, brand)                 │
│  · virtual tray (external spool)                             │
│  · Writer: device/MQTT only. Users & system cannot "edit    │
│    what's in the device".                                    │
└─────────────────────────────────────────────────────────────┘
```

### 4.1 Key migration

`MixedFilamentManager` (mixing recipes) currently lives in `PresetBundle`
(Design Layer). **It must be relocated to the Fulfillment Layer.** While recipes
remain inside the design container, §3 is mechanically unenforceable.

### 4.2 Invariants (correctness criteria)

1. **The Design Layer is modified only by user actions.** After any sync,
   match, mix, or device update event, the Design Layer is byte-identical.
2. **The Fulfillment Layer may be invalidated** by Design or Physical changes,
   but a stale layer is recomputable in one action, and user-locked entries
   survive recompute.

### 4.3 Lock scope and invalidation (definition — prevents "ghost locks")

A lock (🔒) binds to a **(design-intent id, recipe)** pair, not to a free-floating
recipe. A lock is meaningful only while its owning design intent exists and is
materially unchanged. Invalidation rules:

- **Design intent deleted** → its locks are **automatically dropped** (the recipe
  has no subject).
- **Design intent's type changed** → its locks are **invalidated** (a recipe for
  "red PETG" cannot transfer to the intent becoming "red PLA"; type is a hard
  constraint per §4, so the recipe space changed entirely).
- **Design intent's colour changed beyond a ΔE threshold** → its locks are
  **flagged stale but kept**, prompting the user: "you changed this colour; keep
  the old recipe or recompute?" (colour is a soft constraint, so the old recipe
  may still be acceptable).
- **Physical stock change** (filament swapped) → locks keep, but if a locked
  recipe references a now-absent physical slot, it is flagged **broken** and the
  user must re-resolve (cannot silently rebind to a different slot — that would
  violate §6).

Rationale: without these rules, recomputing after a design edit would leave
locks pointing at recipes whose design subject no longer exists ("ghost locks"),
corrupting the next solve.

---

## 5. Interaction Architecture

### 5.1 Mental model (one sentence for the user)

> *"You design what you want (colour, material). 'Whether and how it can be
> printed' is the system's job — it computes it, shows it, lets you tune and
> decide — but it never changes your design."*

### 5.2 Dual View

| View | Shows | Source | When |
|---|---|---|---|
| **Design View** | design intent (colour × type) | Design Layer (RO) | authoring, colour, material — "what I want" |
| **Expected View** | how each intent will be realised | Fulfillment Layer (derived) | review, recipe tuning, pre-print — "how it'll print" |

> **Phase-1 naming honesty:** A true "Expected View" means seeing the *3D model
> in its realised colours*. That needs the 3D colour injection (§9.1), which is
> Phase 2. In Phase 1 the view is **canvas + report + a thumbnail render**
> (thumbnail path accepts an explicit colour vector today, so a small realised
> preview is feasible), but **not** a full recoloured 3D scene. To avoid
> over-promising, Phase 1 labels this view "Fulfillment Plan" (履约方案), not
> "Expected View"; the label upgrades to "Expected View" once 3D injection
> lands in Phase 2.

Switching views changes **only what layer you look at**, never writes design (§1).
Design View renders the 3D model with Design colours (current behaviour, zero
change). Expected View renders with Fulfillment-resolved colours (physical
colour for direct matches, synthesised colour for mixes, flagged for the
impossible). The 3D-injection engineering cost remains, but architecturally it
is now a *legitimate, data-owned* Fulfillment output, not a render hack.

### 5.2.1 What layer does a "Resolve" write? (disambiguation — critical)

Constitution §1 forbids non-user writes to the Design Layer; the **user** may
still change their own design. This creates an ambiguity the UI must resolve
explicitly: some "Resolve" choices in the Fulfillment Canvas (e.g. fixing a
type gap by choosing "swap the bracket from PETG to PLA") are **design edits**,
not fulfilment edits — they change *what the design is*, so they write the
**Design Layer** and leave the Fulfillment view.

To keep the two layers visually honest, two distinct action classes:

| Action class | Writes | UI affordance | Stays in view? |
|---|---|---|---|
| **A — Fulfilment edit** (tune ratio, swap *which physical slot* realises an intent, lock 🔒) | Fulfillment Layer | inline ⚙ / 🔒, stays in canvas | yes |
| **B — Design edit** (change the intent's *colour* or *type*, remove an intent) | Design Layer | clearly marked "Edit design →", **switches to Design View** | no — returns to Design View |

Rule: **an action that changes the intent itself is a Design edit (class B) and
must leave the Expected View.** Mixing the two under one affordance would make
"am I tuning the plan or changing my design?" ambiguous — defeating the layer
separation. A class-B action taken from the canvas is therefore a *shortcut into
Design View*, not a write performed inside Expected View.

### 5.3 Fulfillment Canvas (Expected View body)

A single canvas indexed by **design intent** (not a split screen). Each row
answers one complete question:

> "This design intent (colour C + type T) — can my device print it? How?"

```
Design intent        Colour         Type        Plan
────────────         ─────          ────        ────
① bracket red+PETG   ●red ✓ A1red  ✗ no PETG   🔴 [Resolve]
② shell   blue+PLA   ●blu ✓ A2blu  ✓ A2 PLA    🟢 perfect
③ trim    pink+PLA   ●pnk ~ R+W40 60 ✓ PLA mix 🟡 ΔE1.8 ⚙
④ grip    blk+TPU    ●blk ✗ none    ✗ no TPU    🔴 [Resolve]

Global health: 2 fatal (type gap) · 1 tunable · 1 perfect
Device stock: A1 red PLA · A2 blue PLA · A3 white PLA · A4 grey PLA (4)
                                          [expand device details 🔽]
[Recompute recipes]   [Lock all]   [Back to Design View]
```

Design rules (each maps to a principle or pain point):

1. **Type column before colour (§4).** Type determines green/red; a failed type
   makes the row red regardless of colour accuracy.
2. **Recipe is fine-tunable (⚙)** (§6). Tune ratio / swap source material
   in-place. Edits write the Fulfillment Layer, never Design.
3. **Fatal items get a "Resolve" action, not an error** (§5). Choosing opens a
   consequence-stated decision: "No PETG. Bracket is load-bearing; PLA is ~30%
   weaker. Swap to PLA / ABS / must load PETG." Material decisions require
   informed consent (§6); never auto-substituted.
4. **Device stock collapses to a bottom summary.** Device zone is not a peer
   region; it's the recipe's ingredient shelf — one summary line, expandable to
   swap slots (echoes [GH #11060](https://github.com/bambulab/BambuStudio/issues/11060)).
5. **Global health (§5).** "2 fatal, 1 tunable" — instant whole-picture read.

### 5.4 Why single canvas, not split screen

A split screen (design left / device right) **reinforces a two-world dichotomy**
— the exact failure mode behind "can't tell design colour from device colour".
The single canvas indexes by **design intent** and dissolves the device into
each row's "plan" plus a bottom summary. **Design is always the subject; the
device is always subordinate.**

---

## 6. Core User Flows

### Flow A — Authoring (Design View)

1. User assigns (colour, type) to parts in Filaments → Design Layer grows.
2. Each design intent shows a **lightweight health dot** (green/yellow/red) —
   live, read-only, side-effect-free. It answers only "can it?", never "how?".
3. User keeps authoring. The system **never auto-recomputes recipes** during
   authoring — that would override decisions (§6) and clobber fine-tunes.

The health dot exists solely to satisfy §5 (gaps spoken). It is the "live hint"
tier: read-only, only to "can it" granularity, no expensive recipe solve.

### Flow B — Fulfilment & fine-tune (Expected View)

1. User switches to Expected View (or clicks a yellow/red dot).
2. System solves each intent's plan using **real device stock**:
   - Type filter (hard): only same-type physical filaments may participate in a
     mix (§4).
   - Colour match: ΔE<1 → direct; else `batch_match` over same-type stock.
3. Canvas shows: which are direct, which synthesised, which impossible.
4. User fine-tunes per row (⚙ ratio/material) or locks (🔒). All edits land in
   the Fulfillment Layer; the Design Layer is byte-identical.
5. User resolves fatal items. Per §5.2.1, this splits by action class:
   "load filament / swap *which slot* realises it" = class A (Fulfillment);
   "change this part's type" = class B (Design edit → switches to Design View).
   A type-gap resolution that edits the design is **never** performed silently
   inside the canvas.

The solve runs **on demand**. The engine reuses `batch_match_model_colors`'s
core, but **not** as a parameter swap: it must first be audited and severed
from its internal `preset_bundle` reads (see §2 caveat), then fed **real device
stock colours** with `check_compatible=true` (force same-type mixing, §4).

### Flow C — Pre-print physical (mandatory gate)

1. User clicks "Print".
2. System scans the Fulfillment Layer and emits a **pre-print physical report**
   (human language, not a mapping table):
   - ✓ 4 perfectly fulfilled
   - ⚠ 1 colour synthesis (ΔE 3.1, fine-tuned & confirmed)
   - ✗ 2 type gaps (unprintable unless filament loaded)
3. Any ✗ → **print blocked**, guided to resolve (never silent — directly fixes
   the silent-substitution pain). All green/yellow → confirm → print.

This is §5's ultimate backstop. Any mismatch that would cause wrong-filament /
failed prints is **forced into the open** here; there is no silent path through.

---

## 7. Fulfillment-Layer Lifecycle (freshness)

| Trigger event | Design | Fulfillment | Physical |
|---|---|---|---|
| User edits design (colour/type/paint) | ✏️ user writes | ⚠️ mark stale, health dot recomputes (light), recipes pending recompute | — |
| Device changes (filament swap / MQTT) | unchanged (§2) | ⚠️ mark stale, health dot recomputes | ✏️ device writes |
| User clicks "Recompute recipes" | unchanged | ♻️ recompute (keep 🔒 locks) | unchanged |
| User fine-tunes a recipe | unchanged (§3) | ✏️ user writes | unchanged |

Two guarantees:
- Design Layer is written **only** on the "user edits design" row. On all other
  events Design is invariant (§1-3).
- After Fulfillment goes stale, the health dot (light, RO) still reflects new
  reality, but detailed recipes are **not** auto-overwritten — they wait for the
  user, and locks survive (§6).

---

## 8. Region Ownership (final allocation)

| Region | Layer | Role | Writable by |
|---|---|---|---|
| **Filaments list** | Design | carrier of design intent (colour × type) | user only |
| **Model painting** (part → extruder) | Design | where intent lands on the model | user only |
| **Health dot** (green/yellow/red in Design View) | Fulfillment (derived display) | live "can it?" hint | read-only |
| **Fulfillment Canvas** (Expected View body) | Fulfillment | "how to realise" + fine-tune | system + user |
| **Mixing recipes** | Fulfillment | synthesis plan (**migrated out of preset_bundle**) | system + user |
| **Mapping scheme** | Fulfillment | design_extruder → physical slot | system + user |
| **Device zone** (DeviceFilamentZone) | Physical | real stock; collapses to summary + details drawer in the canvas | device only |

---

## 9. Engineering Notes (known hard parts; do not shake the architecture)

1. **3D Expected View colour injection (§5.2):** the main 3D view reads colour
   from `get_extruder_colors_from_plater_config()` unconditionally — no
   injection point today. A full recoloured 3D Expected View needs "render by
   Fulfillment-resolved colour". Real engineering cost, but architecturally now
   legitimate (Fulfillment's job to produce the real colour), not a hack.
   **Phase-1 bridge:** the *thumbnail* render path (`render_thumbnail_*`) already
   accepts an explicit colour vector, so a small realised preview thumbnail is
   feasible in Phase 1; the full live 3D Expected View is Phase 2. See §5.2
   naming rule.
2. **Three-index alignment:** design extruder / AMS tray / `ConnectMachineInfo::index`
   are three numbering spaces; alignment is a Fulfillment-Layer responsibility.
3. **Recipe relocation:** moving `mixed_filaments` out of `preset_bundle` touches
   the slice pipeline and save/load paths — migration cost, mechanical.
4. **Demo vs clean-slate — honest about Phase 1:** Phase 1 **cannot** enforce a
   truly read-only Design Layer, because the functions that violate it —
   `sync_ams_list`, `apply_batch_match_to_model` — are **this branch's own core
   features**, deeply coupled into the sidebar, slice pipeline, and save/load.
   A runtime read-only assertion would only fire *after* the violation (crash
   the demo), not prevent it; and Colour Mixing Match must repaint the model by
   design, so asserting "model painting never changes" would break the feature.
   Therefore Phase 1's framing is explicit: it validates the **experience**
   (canvas, health dots, report) using **logical** layer separation in new code
   paths, while legacy sync/match paths continue to write design as today.
   Making the Design-Layer invariant *structurally* true (severing legacy writes)
   is itself the Phase 2 work — it cannot be a Phase 1 precondition.

---

## 10. Phasing

- **Phase 0 (done):** read-only `DeviceFilamentZone` showing real device stock.
- **Phase 1 — Fulfillment Canvas + health dots (experience validation):** the
  core experience. Design View gets health dots; Expected View gets the single
  canvas with type-tiered rows, real-stock recipe solve, per-row fine-tune +
  lock, pre-print report. **Caveat:** the Design-Layer read-only invariant is
  *not* structurally enforced this phase — legacy `sync_ams_list` /
  `apply_batch_match_to_model` still write design as today; new fulfilment code
  paths observe design read-only by convention. 3D Expected View deferred;
  Expected View is canvas+report only (see §5.2 / §9.1 naming).
- **Phase 2 — Architectural clean-up:** relocate `mixed_filaments` out of
  `preset_bundle`; **sever legacy design-writing paths** (reroute/replace
  `sync_ams_list` and `apply_batch_match_to_model` so they write Fulfillment,
  not Design) to make the read-only invariant structurally true; add 3D
  Expected View colour injection.
- **Phase 3 — Device-zone refactor:** collapse the standalone DeviceFilamentZone
  into the canvas's summary + details drawer.

---

## 11. Success Metrics (qualitative)

- A user who designs a multi-colour, multi-type model on a device missing some
  colours/types learns **every mismatch before printing** — never via a failed
  print.
- A user's design (colours, types, painting) is **identical** after running sync
  or mixing-match (verifiable: byte-diff the Design Layer before/after).
- A user who fine-tunes a recipe, then triggers a recompute, **keeps** their
  fine-tune (and locked decisions).
- No "silent colour substitution" path exists anywhere in the print flow.
