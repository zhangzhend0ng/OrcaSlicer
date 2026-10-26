#!/usr/bin/env python3
"""Drive the runtime_wait runner in both dispatch modes (no-app / console)."""
import argparse
from pathlib import Path
import json
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--binary", type=Path, required=True)
args = parser.parse_args()
binary = str(args.binary.resolve())

for mode in ("no-app", "console"):
    with tempfile.TemporaryDirectory(prefix=f"runtime-wait-{mode}-") as root:
        run = subprocess.run([binary, mode, str(Path(root) / "run")], capture_output=True, text=True, timeout=300)
        # The runner refuses to run twice into the same directory and the report
        # is written before exit, so read it back from the captured copy first.
        assert run.returncode == 0, f"{mode} mode failed rc={run.returncode}\nstdout: {run.stdout}\nstderr: {run.stderr}"
        assert "PASS runtime_wait" in run.stdout, run.stdout + run.stderr
        print(f"PASS runtime_wait {mode}")
print("PASS load-wait contract, observer dispatch (console queue / no-app inline)")
