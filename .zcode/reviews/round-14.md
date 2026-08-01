# Round 14 — unguarded wxGetApp().plater() derefs (null-deref hazard)

Harness: UB-2 null-pointer-deref (N), consistency. Files: FulfillmentPanel.cpp,
DeviceFilamentZone.cpp.

## Finding
Several demo call sites dereferenced wxGetApp().plater()-> without a null check,
while others in the same files guarded it — inconsistent. plater() is non-null
post-init in practice, but the DeviceFilamentZone auto-refresh TIMER handler can
fire during teardown when the Plater is already destroyed: the timer is stopped
in the dtor, but a pending wxEVT_TIMER may already be in the event queue and
dispatches after the Plater is gone → null deref / crash. The two FulfillmentPanel
sites are button/picker callbacks (post-init), lower risk, but still inconsistent
and a latent UB-2 if a handler ever runs during shutdown.

## Fix
Guarded all three sites: bind a local `Plater* plater = wxGetApp().plater();` and
early-return / skip if null. Behaviour unchanged when plater is non-null.

## Adversarial re-check
- on_match tail + picker callback: guarded, skip health/repaint if null. ✓
- DeviceFilamentZone on_timer: early-return after refresh() if plater null — the
  UI refresh already happened; only the store/panel/indicator cascade is skipped,
  which is correct (those need a live Plater). ✓
- No behaviour change in the normal (non-null) path. ✓

## Verdict: APPROVE (fix applied), build green.
