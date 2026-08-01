# Round 12 — stale rollup read as current truth (PRD §5/§7 honesty gap)

Harness: PRD §5 (gaps spoken), §7 (lifecycle). File: FulfillmentPanel.cpp summary.

## Finding
After a design/device change, DeviceFilamentZone::on_timer calls store.mark_stale()
then panel->refresh_fulfilment(). refresh_fulfilment renders the existing (now-stale)
entries and reads m_store.rollup() to build the "N perfect / M tunable / K broken"
summary. But those health values were computed against the PRIOR device snapshot, so
after a device change the summary shows stale counts with no indication they're
out of date. PRD §7 lets recipes wait for the user (no auto-re-solve), but §5
requires the gap to be spoken — a user could read the rollup as current truth and
miss that the device changed under them.

(The resolve dialog and on_timer fingerprint/mock-flag logic were also reviewed
this round — both correct: resolve honours PRD §5.2.1 class-A/class-B split, and
the fingerprint includes the mock flag so mock→real transitions are detected.)

## Fix
When the store has any stale entry (has_stale()), append "(stale — press Match to
refresh)" to the summary. Honest signal: the numbers are labelled as pending a
re-Match, not presented as current. Clears automatically once Match re-solves.

## Adversarial re-check
- has_stale() true after mark_stale(); false after solve() (sets stale=false per
  entry). Marker appears/disappears correctly. ✓
- on_timer → refresh_fulfilment shows the marker right after a device change. ✓
- No re-solve forced (respects §7 — recipes wait for the user). ✓

## Verdict: APPROVE (fix applied), build green.
