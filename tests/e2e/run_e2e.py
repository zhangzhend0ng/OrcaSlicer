"""E2E orchestrator: run every scenario against one build in a fresh workspace.

Usage:
  python tests/e2e/run_e2e.py --exe <build>/src/Release/snapmaker-orca.exe \
                              --seed-conf <path-to-a-first-run-complete-Snapmaker_Orca.conf>

Exit code 0 only if all scenarios pass. Each scenario is an independent process; the
workspace (default tests/e2e/_work, or --work) keeps datadirs, gcode outputs and logs for
post-mortem. See README.md for requirements and the golden-gcode A/B protocol.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def run_scenario(name, script, args):
    print("== scenario: %s ==" % name)
    started = time.time()
    p = subprocess.run([sys.executable, os.path.join(HERE, script)] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(p.stdout or "")
    if p.returncode != 0:
        print(p.stderr or "")
        print("== scenario %s FAILED (rc=%d, %.0fs) ==" % (name, p.returncode, time.time() - started))
        return False
    print("== scenario %s passed (%.0fs) ==" % (name, time.time() - started))
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--seed-conf", required=True, help="conf of a first-run-complete profile; copied into each isolated datadir")
    ap.add_argument("--work", default=os.path.join(HERE, "_work"))
    ap.add_argument("--skip", nargs="*", default=[], help="scenario names to skip")
    args = ap.parse_args()

    if os.path.isdir(args.work):
        shutil.rmtree(args.work)
    os.makedirs(args.work, exist_ok=True)

    ok = True
    if "slice" not in args.skip:
        ok &= run_scenario("slice", "scenario_slice.py",
                           ["--exe", args.exe, "--work", os.path.join(args.work, "slice"),
                            "--seed-conf", args.seed_conf])
    if "lifecycle" not in args.skip:
        ok &= run_scenario("lifecycle", "scenario_lifecycle.py",
                           ["--exe", args.exe, "--work", os.path.join(args.work, "lifecycle"),
                            "--seed-conf", args.seed_conf])

    print("E2E %s" % ("PASSED" if ok else "FAILED"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
