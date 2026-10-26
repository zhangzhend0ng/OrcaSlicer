#!/usr/bin/env python3
"""Test real dependency publication crashes and fresh host startup on macOS.

Never builds, starts a GUI, changes an existing profile or claims non-macOS
verification. The fault library is test-only and is injected only into seed
processes; all recovery processes run without injection.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--fault-library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixtures-source", type=Path, default=Path(__file__).resolve().parents[1] / "tests/plugin_core/fixtures.py")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("This real rename fault injector is macOS-specific; Windows/Linux are not verified")
    binary = args.binary.resolve(strict=True)
    library = args.fault_library.resolve(strict=True)
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error("Output must be a fresh artifact directory")
    output.mkdir(parents=True)
    spec = importlib.util.spec_from_file_location("dependency_fixtures", args.fixtures_source.resolve(strict=True))
    fixtures = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixtures)
    wheelhouse = output / "fixtures"
    wheelhouse.mkdir()
    fixtures.wheel(wheelhouse / "contract_dep-1.0.0-py3-none-any.whl", "contract_dep", 'VALUE = "1.0.0"\n')
    fixtures.wheel(wheelhouse / "recovery_new_dep-1.0.0-py3-none-any.whl", "recovery_new_dep", 'VALUE = "new"\n')
    rows = []
    before = {"binary": digest(binary), "fault_library": digest(library)}

    def run(case, action, expected):
        directory = output / case
        directory.mkdir(exist_ok=True)
        profile = directory / "profile-中文"
        log, report = directory / (action + ".log"), directory / (action + ".json")
        environment = dict(os.environ)
        environment.pop("DYLD_INSERT_LIBRARIES", None)
        for key in list(environment):
            if key.startswith("ORCA_DEP_TEST_"):
                del environment[key]
        if action.endswith("crash"):
            environment["DYLD_INSERT_LIBRARIES"] = str(library)
        code = "not-run"
        try:
            with log.open("w", encoding="utf-8") as stream:
                code = subprocess.run([str(binary), action, str(wheelhouse), str(profile), str(report)],
                                      env=environment, stdout=stream, stderr=subprocess.STDOUT, timeout=45).returncode
        except subprocess.TimeoutExpired:
            code = "timeout"
        except OSError as error:
            code = "spawn-error"
            log.write_text(str(error), encoding="utf-8")
        row = {"case": case, "action": action, "returncode": code, "expected": expected,
               "matched": code == expected, "profile": str(profile), "log": str(log), "log_sha256": digest(log)}
        if report.is_file():
            row.update(report=str(report), report_sha256=digest(report))
            record = json.loads(report.read_text(encoding="utf-8"))
            if expected == 86:
                row["matched"] = row["matched"] and record.get("real_std_filesystem_rename_completed") is True
            else:
                row["matched"] = row["matched"] and record.get("passed") is True and record.get("interpreter_stopped") is True
        else:
            row["matched"] = False
        rows.append(row)
        print(case, action, code, "expected", expected, flush=True)
        if not row["matched"]:
            raise RuntimeError(f"Dependency recovery failed: {case}/{action}; see {log}")
        return profile

    error = None
    try:
        for case in ("interrupted-publication", "legacy-empty-target", "blocked-target", "completed-publication"):
            profile = run(case, "published-crash" if case == "completed-publication" else "seed-crash", 86)
            target, previous = profile / "python/packages/cp312", profile / "python/packages/.cp312.previous"
            state = {"target_exists": target.exists(), "previous_exists": previous.exists(),
                     "previous_files": sorted(str(path.relative_to(previous)) for path in previous.rglob("*") if path.is_file()),
                     "target_files": sorted(str(path.relative_to(target)) for path in target.rglob("*") if path.is_file())}
            (output / case / "crash-filesystem.json").write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            if case == "legacy-empty-target":
                target.mkdir()
            if case == "blocked-target":
                target.write_text("fixture obstruction; do not remove", encoding="utf-8")
                run(case, "blocked-recovery", 0)
                target.unlink()  # Only the obstruction this fixture just created.
            action = {"legacy-empty-target": "resume-empty", "completed-publication": "resume-published"}.get(case, "resume")
            run(case, action, 0)
    except (OSError, ValueError, RuntimeError) as failure:
        error = str(failure)
    after = {"binary": digest(binary), "fault_library": digest(library)}
    passed = error is None and len(rows) == 9 and before == after and all(row["matched"] for row in rows)
    result = {"schema": 1, "platform": platform.platform(), "binary": str(binary), "fault_library": str(library),
              "sha256_before": before, "sha256_after": after, "runs": rows, "passed": passed,
              "error": error, "windows_linux": "not-run", "gui_started": False}
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": passed, "steps": len(rows), "results": str(output / "results.json")}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
