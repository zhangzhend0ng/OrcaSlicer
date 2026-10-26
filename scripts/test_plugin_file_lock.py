#!/usr/bin/env python3
"""Exercise the native install lock with competing processes and an abrupt exit."""
import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument("--binary", type=Path, required=True)
args = parser.parse_args()
binary = str(args.binary.resolve())
with tempfile.TemporaryDirectory(prefix="plugin-lock-中文-") as root:
    path = Path(root) / "guard"
    owner = subprocess.Popen([binary, str(path), "hold"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        assert owner.stdout.readline().strip() == "locked", "Owner did not acquire lock"
        competing = subprocess.run([binary, str(path), "try"], capture_output=True, text=True, timeout=10)
        assert competing.returncode == 1 and "busy" in competing.stderr, competing
        # Only this test's child is terminated. OS cleanup must release ownership.
        owner.kill()
        owner.wait(timeout=10)
        recovered = subprocess.run([binary, str(path), "try"], capture_output=True, text=True, timeout=10)
        assert recovered.returncode == 0, recovered.stderr
        assert path.is_file(), "Lock file must persist to avoid competing inodes"
    finally:
        if owner.poll() is None:
            owner.kill()
            owner.wait(timeout=10)
    target = Path(root) / "target"
    target.write_text("preserved")
    link = Path(root) / "link"
    try:
        link.symlink_to(target)
    except OSError:
        print("SKIP symlink denial: OS does not permit symlink creation")
    else:
        denied = subprocess.run([binary, str(link), "try"], capture_output=True, text=True, timeout=10)
        assert denied.returncode == 1
        assert target.read_text() == "preserved"
print("PASS competing owner, crash recovery, persistent lock, Unicode path")
