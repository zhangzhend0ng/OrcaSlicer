#!/usr/bin/env python3
"""Drive the unload_overlap runner through every portable scenario.

Each scenario runs in its own isolated profile: the fixture suspends the old
generation's real Python on_unload on a release file, so every scenario below
asserts a contract about what may or may not enter while that teardown runs.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

SCENARIOS = ("overlap", "bulk_overlap", "shutdown", "bulk_shutdown", "replacement", "delete", "shutdown_gil")

parser = argparse.ArgumentParser()
parser.add_argument("--binary", type=Path, required=True)
args = parser.parse_args()
binary = str(args.binary.resolve())

for scenario in SCENARIOS:
    with tempfile.TemporaryDirectory(prefix=f"unload-overlap-{scenario}-") as root:
        run = subprocess.run([binary, scenario, str(Path(root) / "run")], capture_output=True, text=True, timeout=300)
        assert run.returncode == 0, f"scenario {scenario} failed rc={run.returncode}\nstdout: {run.stdout}\nstderr: {run.stderr}"
        assert f"PASS {scenario}" in run.stdout, run.stdout + run.stderr
        print(f"PASS unload_overlap {scenario}")
print("PASS unload/teardown overlap contract for all scenarios")
