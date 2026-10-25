# Application-level E2E scenarios

Unit suites cover libraries; these scenarios cover the **software cycle** of the real
executable: clean boot, plugin install/enable/use/disable/uninstall, restart persistence,
restore, and CLI slicing with a deterministic G-code gate. Every driving technique was
first proven in the manual forensic rounds of 2026-10-23/25 (see
`docs/reviews/port-python-plugins-absorption-ledger.md`, "三方复查轮") and is productized
here as a repeatable harness.

## Layout

| Path | What it is |
|---|---|
| `e2elib.py` | Driver library: isolated `--datadir` sessions, CDP client, native window/confirm helpers, UIA tab-strip probe, plugin fixture install. |
| `scenario_lifecycle.py` | 9-leg / 21-assertion plugin cycle (legs 5 and 8/9 are the regression surface of the Pages boot race fixed in `df6a5fdd40`). |
| `scenario_slice.py` | CLI slice of the shipped `pa_pattern.3mf` calibration project: two runs must be byte-identical after comment normalization; optional golden compare. |
| `run_e2e.py` | Orchestrator (fresh workspace per invocation, one process per scenario, nonzero exit on any failure). |
| `fixtures/e2e_probe/` | Committed Pages-capability plugin the lifecycle legs assert on. |
| `golden/pa_pattern_plate1.sha256` | Normalized G-code hash minted on `port/python-plugins` @ `350c133cdb` (2026-10-25). |

## Requirements

- Windows with an **interactive desktop session** (real GUI is driven; not for headless CI).
- The Release build (e.g. `build-port/src/Release/snapmaker-orca.exe`).
- Python 3 with `websocket-client`; in-box PowerShell.
- A **seed conf**: the `Snapmaker_Orca.conf` of a first-run-complete profile (privacy flag
  accepted, a printer selected). It is copied into each isolated datadir so the app skips
  the setup wizard; user data is never touched. Take it from any configured machine once:
  `cp %APPDATA%/Snapmaker_Orca/Snapmaker_Orca.conf <somewhere>/seed.conf`.

## Run

```
python tests/e2e/run_e2e.py \
  --exe C:/coil/Projects/SnapmakerOrca-plugin-port/build-port/src/Release/snapmaker-orca.exe \
  --seed-conf C:/somewhere/seed.conf
```

Scenario-only runs:

```
python tests/e2e/scenario_lifecycle.py --exe <exe> --work <fresh-dir> --seed-conf <seed>
python tests/e2e/scenario_slice.py    --exe <exe> --work <fresh-dir> [--golden tests/e2e/golden/pa_pattern_plate1.sha256]
```

## G-code golden protocol (the A/B regression gate)

`scenario_slice.py` normalizes three run-volatile comment line families (wall-clock
header, random object-id comments -- proved by repeated two-run byte diffs) and hashes the
rest. Two runs in one invocation must match (determinism); `--golden` compares against the
recorded hash. **Protocol for proving a port/change does not alter slicing output:**

1. On the trusted baseline build (e.g. the fork merge-base), run
   `scenario_slice.py --write-golden <file>` and keep the result.
2. On the candidate build, run with `--golden <file>`.
3. A mismatch means the G-code of the calibration project drifted -- bisect by diffing
   the two `plate_1.gcode` outputs before accepting any intentional change (then re-mint).

The committed golden was minted on this branch at `350c133cdb`; absorbing upstream
`557feba649` or touching the slicing pipeline must re-run this gate.

## Why not ctest

The scenarios maximize/raise windows and synthesize input on the interactive desktop;
wiring them into the default `ctest` run would break headless builders. Gate them from
release checklists instead (see the ledger's release-readiness list).
