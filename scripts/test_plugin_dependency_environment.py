#!/usr/bin/env python3
"""Offline dependency install keeps host env vars untouched and packages durable.

Adapted from the women fork: the original ran inside the 55-scenario plugin_core
harness; this standalone orchestrator builds the same wheelhouse fixture (via
tests/plugin_core/fixtures.py) and runs the absorbed contract body in an
isolated profile.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--binary", type=Path, required=True)
parser.add_argument("--fixtures-source", type=Path, default=Path(__file__).resolve().parents[1] / "tests/plugin_core/fixtures.py")
args = parser.parse_args()

spec = importlib.util.spec_from_file_location("plugin_core_fixtures", args.fixtures_source)
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)

with tempfile.TemporaryDirectory(prefix="plugin-dependency-env-") as root:
    root = Path(root)
    wheelhouse = root / "wheelhouse"
    wheelhouse.mkdir()
    fixtures.wheel(wheelhouse / "contract_dep-1.0.0-py3-none-any.whl", "contract_dep", 'VALUE = "1.0.0"\n')
    profile = root / "profile"
    completed = subprocess.run([str(args.binary.resolve()), str(wheelhouse), str(profile)],
                               capture_output=True, text=True, timeout=300, cwd=str(root),
                               env={**os.environ})
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        raise SystemExit("dependency environment contract failed")
    print(completed.stdout.strip())
