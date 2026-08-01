# Round 09 — dangling m_health_summary + misleading empty-rollup indicator

Harness: lifetime UB-4 (use-after-free), error-handling (C) messaging, PRD §5.
Files: FulfillmentPanel.cpp, Plater.cpp.

## Finding 1 (lifetime)
FulfillmentPanel::m_health_summary is a raw wxStaticText*. refresh_fulfilment calls
m_panel_content->DestroyChildren(), which deletes the widget, but the member kept
pointing at the freed object. The current single-reader flow happens to reassign
it (solved branch) or return early (unsolved branch) before any read, so no crash
today — but the dangling member is a latent UB-4 trap: any future caller, an added
`if (m_health_summary)` guard, or a reordered early-return would dereference freed
memory.

## Fix 1
Set m_health_summary = nullptr immediately after DestroyChildren, with a comment
that the solved branch reassigns it. The dangling state can no longer arise.

## Finding 2 (messaging)
update_fulfillment_health_indicator showed "0✓ 0~ 0✗" when a solve ran but
produced no rows (empty design). That reads as "everything perfect" when there is
in fact nothing to evaluate — a misleading signal (PRD §5: gaps must be spoken
honestly, including the absence of anything to match).

## Fix 2
Added an entries().empty() branch that blanks the indicator and tooltips "No
design colours to match yet." Accurate for the no-design / post-reset case.

## Adversarial re-check
- m_health_summary null after destroy; reassigned only in solved branch; unsolved
  branch returns without touching it. ✓
- Indicator blank for empty entries, neutral for unsolved, rollup otherwise. ✓
- Removed an accidental duplicate null-guard line I introduced mid-edit. ✓

## Verdict: APPROVE (fix applied), build green.
