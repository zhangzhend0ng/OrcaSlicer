#!/usr/bin/env python3
"""Generate an SDK from a built production-binding exporter, without launching GUI."""
import argparse
import ast
import json
from pathlib import Path
import shutil
import tempfile

from package_plugin_runtime import digest, run, UPSTREAM
from verify_plugin_sdk import verify_sdk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exporter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists():
        parser.error("Output already exists; choose a new SDK artifact directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    exporter = args.exporter.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix=".plugin-sdk-", dir=output.parent) as temporary:
        stage = Path(temporary) / "sdk"
        run([exporter, repo / "scripts/export_plugin_sdk.py", stage, Path(temporary) / "isolated-profile"])
        api = json.loads((stage / "api.json").read_text(encoding="utf-8"))
        if api.get("source") != "live-embedded-orca" or not api.get("modules", {}).get("orca"):
            raise ValueError("Exporter produced no live binding inventory")
        for stub in stage.rglob("*.pyi"):
            ast.parse(stub.read_text(encoding="utf-8"))
        shutil.copytree(repo / "docs/plugins/examples", stage / "examples",
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        (stage / "README.md").write_text(
            "# Snapmaker Orca local plugin SDK\n\n"
            "Point your editor's Python analysis extra paths at `typings`. The `orca` module is provided by the host, "
            "so these stubs cannot run plugins in standalone Python. `api.json` records the live exported members "
            "and original binding documentation. Unrepresentable signatures use Any.\n\n"
            "Examples target the local phase-one host. Device/printer-agent APIs are not part of this SDK.\n", encoding="utf-8")
        manifest = {"schema": 1, "upstream_commit": UPSTREAM, "source": "live-embedded-orca",
                    "exporter_sha256": digest(exporter), "files": {
                        path.relative_to(stage).as_posix(): digest(path) for path in sorted(stage.rglob("*")) if path.is_file()}}
        (stage / "sdk.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        verify_sdk(stage)
        stage.rename(output)
    print(json.dumps({"output": str(output), "modules": len(api["modules"]), "source": "live-embedded-orca"}))


if __name__ == "__main__":
    main()
