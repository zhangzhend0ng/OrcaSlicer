#!/usr/bin/env python3
"""Drive the observer_queue runner (real wx console queue, real ResourceTexture)."""
import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--binary", type=Path, required=True)
args = parser.parse_args()
binary = str(args.binary.resolve())

with tempfile.TemporaryDirectory(prefix="observer-queue-") as root:
    run = subprocess.run([binary, str(Path(root) / "run")], capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, f"observer_queue failed rc={run.returncode}\nstdout: {run.stdout}\nstderr: {run.stderr}"
    assert "PASS pending load / interpreter shutdown / real wx event drain" in run.stdout, run.stdout + run.stderr
    print("PASS observer_queue")
print("PASS lifecycle observer ordering through a real wx console queue")
