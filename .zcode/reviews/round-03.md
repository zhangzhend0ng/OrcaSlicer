# Round 03 — Expected-View repaint toggle (clarity / duplication)

Harness: interface-contracts (C), code-review/maintainability (A).
Files: Plater.hpp, Plater.cpp, FulfillmentPanel.cpp (2 sites).

## Finding (F6 from round-01)
Two call sites (on_match, MachineFilamentPicker callback) force a 3D repaint after
the store's realised colours change by doing:
    if (plater && plater->is_expected_view()) {
        plater->set_expected_view(false);
        plater->set_expected_view(true); // toggle off/on to force repaint
    }
This is *functionally* correct (state returns to true; set_as_dirty fires twice),
but:
1. It reads as a state change — a future reader may think Match flips the view mode.
2. The pattern is duplicated at two sites that must stay in sync.
3. The guard already ensures it only runs when EV is on, so the toggle's only real
   effect is the set_as_dirty() side-effect — the state change is noise.

## Fix
Added `Plater::refresh_expected_render()` — sets the canvas dirty in the CURRENT
view mode, no state toggle, guarded by `m_expected_view_active` (no-op when EV is
off, since design colours don't depend on the FulfillmentStore). Both sites now
call the one method; the misleading toggle and the duplication are gone.

## Adversarial re-check
- Same dirty trigger as set_expected_view (set_as_dirty). ✓
- Same guard (EV-active) — no behaviour change for the EV-off case. ✓
- `p` null-guard preserved. ✓
- Removed now-unused local `Plater* plater` in on_match (no other use). ✓
- get_expected_render_colors() is read per-frame from the GL render path, so a
  dirty flag is sufficient — no explicit colour-push needed. ✓

## Verdict: APPROVE (fix applied), build pending.
