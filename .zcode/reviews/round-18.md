# Round 18 — FulfillmentStore not reset on project reset (stale entries leak)

Harness: correctness, PRD §7 (lifecycle). File: Plater.cpp priv::reset.

## Finding
Plater::priv::reset (the "new project" path) cleared the model, palette cache,
print, etc., but did NOT reset the FulfillmentStore. After a project reset the
store kept the previous project's entries (recipes/locks) — mark_stale alone
leaves them displayed (just flagged stale) until the user re-Matches, and a stale
entry could even be consumed by prepare_slice_inputs' stale re-solve against the
new (empty) design before the user notices. Also, Expected View stayed on with no
realisation for the new project, and the Design/Expected toggle kept its old
clicked state — control desynced from the actual mode.

## Fix
- Call sidebar->fulfillment_store().reset_all() in priv::reset — clears entries,
  locks, and m_ever_solved (so has_solved()→false, panel shows the neutral hint).
- Turn Expected View off and snap the toggle back to Design via a new
  FulfillmentPanel::sync_view_toggle_to_expected() (uses SegmentedToggle::setSelected,
  which is visual-only and does NOT fire the callback — no re-entrancy).
- Refresh the panel + health indicator so they reflect the cleared state.

## Adversarial re-check
- reset_all() sets m_ever_solved=false; panel shows hint; indicator blank. ✓
- m_expected_view_active is a priv member (set directly); toggle synced via the new
  method; no callback re-fire (setSelected is visual-only). ✓
- sidebar is a priv member, valid after priv ctor completes (reset is called later);
  also guarded where the panel is fetched (fulfillment_panel() may be null pre-init,
  though here it's non-null). ✓
- Initial build failed (used m_fulfillment_store/m_fulfillment_panel as if priv
  members — they're Sidebar members); corrected to sidebar-> accessors. Rebuild green.

## Verdict: APPROVE (fix applied), build green.
