# Adversarial Loop Journal — wxUIActionSimulator Windows validation

Task: validate branch `test/wx-ui-action-simulator` on Windows (route A:
prove wxUIActionSimulator can drive a real wxWindow). Loop run with the
adversarial-development-loop skill on 2026-08-04, machine = Windows 10
22H2 (19045.4291).

---

## Iteration 1 — Why does sim.Text()/MouseClick() deliver nothing on Windows?

### Triggered theoretical gap
macOS failed because `wxTextCtrl::SetFocus()` never grants focus inside the
modal loop. On Windows the first run showed focus WORKS
(`m_textctrl_had_focus=true`) yet `sim.Text("hello")`/`sim.MouseClick()`
produced empty results. Why do events not arrive when focus is good?

### grep journal / prior art
None (first loop). Pulled authoritative wxWidgets test patterns instead:
- `tests/controls/textctrltest.cpp:215-237` and `tests/validators/valnum.cpp:254-310`
  use the canonical pattern: control = child of `wxTheApp->GetTopWindow()`
  (non-modal top frame); `m_text->SetFocus(); sim.Text("abcdef"); wxYield();`
  single yield, no ShowModal/CallAfter/sleep. This pattern is assumed-correct
  on wxMSW.

### Shape enumeration (failure shapes for "no input arrives")
| Shape | Distinguishing field | Possible? | Verdict after probes |
|---|---|---|---|
| S1 modal+nested-yield blocks dispatch | wxYield inside ShowModal/CallAfter | initial suspect | FALSIFIED (non-modal variant fails identically) |
| S2 console-subsystem not foreground | GetForegroundWindow() != our HWND | initial suspect (REFUTE's bet) | FALSIFIED (foreground IS our window) |
| S3 UIPI / privilege | higher-priv target | — | EXCLUDED (no elevated target) |
| S5/S6 focus "logical yes, physical no" | GetFocus() != TextCtrl | — | FALSIFIED (GetFocus()==TextCtrl) |
| T1 keybd_event deprecated/broken on Win10 | inject not honored | — | FALSIFIED for the API (GetAsyncKeyState sometimes 0x8001) |
| T2 wxEventLoop dispatch bug | wxYield doesn't retrieve/dispatch | suspect | FALSIFIED (raw native PeekMessage loop ALSO retrieves 0) |
| T3 session input-interception layer | remote-control/mirror suppresses inject | — | **CONFIRMED (root cause)** |

### Initial plan (refuted)
Rewrite test to non-modal top frame + canonical single-yield + foreground fix
(`SetForegroundWindow`/`AllowSetForegroundWindow`). Commit CMake fixes.

### Adversarial review (REFUTE) conclusions
- [blocker] F1/F2: "modal+nested-yield is NOT the cause; foreground-target
  delivery is the real cause; `SetForegroundWindow` alone is a no-op under
  foreground lock; need `AttachThreadInput`. Recommend probing
  `GetForegroundWindow()` before rewriting."
- [major] F3/F4: non-modal frame alone is insufficient; lifetime/return gap.
- [minor] F5: head comment / pump_events comment wrongly apply macOS model to wxMSW.
- accepted: keep CONSOLE subsystem (WIN32_EXECUTABLE conflicts with Catch2 main).
- accepted (f): CMake fixes complete and correct (5 Qhull + 5 no-as-needed, no sibling missed).

### Revised plan (probe-first, per REFUTE recommendation)
Add Win32 diagnostics (`GetForegroundWindow`, `GetFocus`, dialog/TextCtrl
HWNDs) + `AttachThreadInput` foreground attempt; do NOT blindly rewrite. Let
data decide.

### Data-flow / probe results (the decisive evidence)
| Probe | Result | What it ruled |
|---|---|---|
| diag at sim time (modal) | foreground=dialog (yes), focus=TextCtrl (yes), AttachThreadInput applied=no; input still "" | FALSIFIES REFUTE's foreground hypothesis on THIS machine |
| non-modal canonical variant | foreground=frame (yes), focus=TextCtrl (yes); input still "" | FALSIFIES modal-structure hypothesis |
| raw `keybd_event('A')` + `wxYield` | GetAsyncKeyState=0x8001 (OS accepted) OR 0x0 (rejected) non-deterministically; TextCtrl="" | isolates: NOT wxUIActionSimulator's fault |
| raw `keybd_event('A')` + native PeekMessage/TranslateMessage/DispatchMessage loop | retrieved WM_KEYDOWN/UP=0, WM_CHAR=0 | injected events never enter the thread's message queue at all |
| environment scan | GameViewerService/Server/Healthd/GameViewer.exe running; "GameViewer Virtual Display Adapter" present | ROOT CAUSE: remote-control layer intercepts session input |

### Root cause (settled)
Machine runs **NetEase GameViewer** (remote display/control). Its virtual
display adapter + input-injection interception suppresses synthetic input
(`keybd_event`/`SendInput`/`mouse_event`) from processes in the session —
non-deterministically accepted into the global key state but never queued for
retrieval. wxUIActionSimulator cannot work HERE, independent of dialog
structure, focus, foreground, or wx. **Route A is NOT validated on this
machine; it is expected to work on a clean Windows console.**

### Variant grep (sibling sites)
- `find_package(Qhull` → 0 remaining (all 5 fixed).
- unguarded `--no-as-needed` → 0 remaining (all 5 guarded under `if (UNIX AND NOT APPLE)`).
- `-framework`/`-liconv` at `tests/CMakeLists.txt:25` → already guarded by `if (APPLE)`; not a sibling defect.
- No `find_package` of other in-tree deps_src targets. No other GNU-only link flags.

### Changes committed (this branch, ahead of origin by 3)
1. `build(tests): fix MSVC configure/link blockers` (d2fccf31c8) — CMake fixes.
2. `test(wx_gui): add Win32 input-target diagnostics + foreground probe` (69aa22bd23) — diagnostics that FALSIFIED the foreground hypothesis.
3. `test(wx_gui): add non-modal canonical pattern + settle input root cause` (a1b74c190a) — canonical variant + diagnostic NOTE + corrected head comment.

### Test evidence (string-level, not timestamps)
- `strings wx_gui_tests.exe | grep "[diag]"` → present in binary.
- exe timestamp newer than source after each rebuild.
- Full runs captured: modal (1/3), non-modal (1/3), rawprobe (0/1) — all on a GameViewer-hijacked session.

### Process surprises / deviations
- The adversarial REFUTE's central hypothesis (foreground) was itself
  FALSIFIED by runtime data — the REFUTE was overconfident about a root cause
  it had not measured. Probing first (its own recommendation, ironically) was
  the move that exposed it. Lesson: even a well-sourced refutation must yield
  to a 10-minute probe.
- Root cause was environmental, not in the code under test — none of the
  enumerated code-level shapes (S1/S2/S5/T1/T2) explained it. The unknown
  unknown (T3, a remote-control layer) only surfaced via a raw OS-level probe
  that bypassed the entire wx stack. The ENUMERATE step's "enumerate failure
  shapes" cannot enumerate environmental hijacking without leaving the code —
  the OS-level probe was the missing move.

### Backlog
- Re-run this PoC on a **clean Windows console** with GameViewer (and any
  remote-control/virtual-display tool) fully stopped, to actually validate
  route A. Until then, route A on Windows remains UNVERIFIED (not disproven).
- If green there: consider replacing the macOS-shaped modal+CallAfter design
  with the canonical non-modal pattern for cross-platform consistency, and
  add a guard that skips `[gui]` tests when a known remote-control layer is
  detected (to avoid these red herrings in future CI/local runs).
