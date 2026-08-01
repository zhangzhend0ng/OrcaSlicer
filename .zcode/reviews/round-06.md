# Round 06 — Misleading "Connect a printer" mock banner

Harness: error-handling (C) item 2 ("messages for operators, be specific /
accurate"), PRD §5 (gaps spoken honestly).
Files: DeviceFilamentZone.cpp, FulfillmentPanel.cpp.

## Finding
The offline-mock path fires whenever build_machine_filament_list produces an empty
real list — which happens in THREE cases:
1. no printer connected;
2. a connected printer that hasn't reported its stock yet (boot / pre-WCP-refresh);
3. a connected printer with all trays physically empty.
The mock banner ("Connect a printer to see the real stock") and the match-time
dialog ("Connect a printer and re-run Match") asserted case 1 only — wrong in
cases 2 and 3, where the printer IS connected. Misleading operator messaging.

## Fix
Rephrased both messages to be source-and-action rather than connection-state:
"inferred from the printer preset, not read from a connected machine. Sync the
printer (or connect one) and refresh / re-run Match". Accurate in all three cases.

## Adversarial re-check
- Case 1 (no printer): "sync or connect" → connect is the right action. ✓
- Case 2 (connected, not reported): "sync the printer" → user clicks refresh/sync,
  WCP reports, mock clears. ✓
- Case 3 (connected, empty trays): "sync" → re-sync confirms empty; mock stays
  (correct — there's genuinely no filament), and the wording no longer falsely
  implies the printer is absent. ✓
- No behavioural change, only user-visible strings.

## Verdict: APPROVE (fix applied), build green.
