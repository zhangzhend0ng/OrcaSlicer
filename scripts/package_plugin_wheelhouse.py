#!/usr/bin/env python3
"""Lock, assemble and test an offline wheelhouse using the packaged interpreter.

Never downloads packages, builds sdists, or modifies a real plugin profile.
"""
import argparse
import email
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile

from package_plugin_runtime import digest, run, verify, MANIFEST, fresh_output


def wheel_metadata(path):
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        for entry in members:
            name = PurePosixPath(entry.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in entry.filename or ":" in entry.filename:
                raise ValueError(f"Unsafe wheel member in {path.name}")
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError(f"Wheel symlink rejected in {path.name}")
        metadata = [e for e in members if e.filename.endswith(".dist-info/METADATA")]
        tags = [e for e in members if e.filename.endswith(".dist-info/WHEEL")]
        if len(metadata) != 1 or len(tags) != 1:
            raise ValueError(f"Missing/ambiguous wheel metadata in {path.name}")
        info = email.message_from_bytes(archive.read(metadata[0]))
        wheel = email.message_from_bytes(archive.read(tags[0]))
        if not info["Name"] or not info["Version"] or not wheel.get_all("Tag"):
            raise ValueError(f"Incomplete wheel metadata in {path.name}")
        if any("@" in requirement for requirement in info.get_all("Requires-Dist", [])):
            raise ValueError(f"Direct URL dependency is not an offline wheelhouse dependency: {path.name}")
        return {"name": info["Name"], "version": info["Version"], "tags": wheel.get_all("Tag"),
                "requires_dist": info.get_all("Requires-Dist", []), "sha256": digest(path)}


def pins(path):
    result = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.split("#", 1)[0].strip()
        if not value:
            continue
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*(?:\[[A-Za-z0-9_,.-]+\])?==[A-Za-z0-9][A-Za-z0-9_.+!-]*", value):
            raise ValueError("Requirements must be exact name==version pins, with optional extras; no URLs/options")
        result.append(value)
    if not result:
        raise ValueError("Requirements are empty")
    return result


def check_import(python, target, module):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)*", module):
        raise ValueError("Invalid module name")
    code = """import sys, importlib, pathlib
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
module = importlib.import_module(sys.argv[2])
paths = [module.__file__] if getattr(module, '__file__', None) else list(getattr(module, '__path__', []))
assert paths and all(pathlib.Path(p).resolve().is_relative_to(root) for p in paths), 'Import did not come from installed wheelhouse'
"""
    run([python, "-I", "-B", "-c", code, target, module])


def package(args):
    root = args.runtime.resolve(strict=True)
    output = fresh_output(args.output, root, args.wheelhouse)
    verification = verify(root, native=True)
    runtime = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    python = root / runtime["layout"]["python"] / runtime["layout"]["executable"]
    uv = root / runtime["layout"]["uv"]
    requirements = pins(args.requirements)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".offline-package-", dir=output.parent) as temporary:
        stage = Path(temporary) / "package"
        wheelhouse = stage / "wheelhouse"
        wheelhouse.mkdir(parents=True)
        wheels = {}
        for path in sorted(args.wheelhouse.resolve(strict=True).glob("*.whl")):
            if path.is_symlink():
                raise ValueError("Wheelhouse source must contain regular wheel files")
            wheels[path.name] = wheel_metadata(path)
            shutil.copy2(path, wheelhouse / path.name)
        if not wheels:
            raise ValueError("Wheelhouse has no wheels")
        source = stage / "requirements.in"
        source.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        lock = stage / "requirements.lock"
        common = ["--python", python, "--no-python-downloads", "--no-managed-python", "--offline", "--no-index",
                  "--find-links", wheelhouse, "--only-binary", ":all:"]
        # --no-cache proves that all transitive wheels are present in this package.
        run([uv, "--no-config", "--no-cache", "pip", "compile", source, *common,
             "--generate-hashes", "--no-header", "--no-annotate", "-o", lock])
        target = Path(temporary) / "installed"
        run([uv, "--no-config", "--no-cache", "pip", "install", *common, "--require-hashes",
             "--target", target, "--link-mode", "copy", "-r", lock])
        imports = []
        for module in args.check_import:
            check_import(python, target, module)
            imports.append(module)
        manifest = {"schema": 1, "platform": runtime["platform"], "machine": verification["native"]["machine"],
                    "python_version": runtime["python_version"], "uv_version": runtime["uv_version"],
                    "runtime_manifest_sha256": digest(root / MANIFEST), "wheels": wheels,
                    "requirements_sha256": digest(source), "lock_sha256": digest(lock),
                    "offline_install": "passed-with-empty-cache", "imports": imports}
        (stage / "wheelhouse.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        stage.rename(output)
    print(json.dumps({"output": str(args.output), "wheels": len(wheels),
                      "offline_install": "passed-with-empty-cache", "imports": imports}))


def verify_package(args):
    package_root = args.verify_package.resolve(strict=True)
    manifest = json.loads((package_root / "wheelhouse.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1:
        raise ValueError("Unsupported wheelhouse manifest")
    runtime = args.runtime.resolve(strict=True)
    runtime_manifest = json.loads((runtime / MANIFEST).read_text(encoding="utf-8"))
    verify(runtime, native=True)
    if digest(runtime / MANIFEST) != manifest["runtime_manifest_sha256"]:
        raise ValueError("Wheelhouse belongs to a different runtime manifest")
    actual = {}
    for path in (package_root / "wheelhouse").iterdir():
        if path.is_symlink() or not path.is_file() or path.suffix != ".whl":
            raise ValueError("Unexpected wheelhouse entry")
        actual[path.name] = wheel_metadata(path)
    if actual != manifest["wheels"]:
        raise ValueError("Wheelhouse inventory mismatch")
    for name, key in [("requirements.in", "requirements_sha256"), ("requirements.lock", "lock_sha256")]:
        if digest(package_root / name) != manifest[key]:
            raise ValueError("Requirements checksum mismatch")
    pins(package_root / "requirements.in")
    layout = runtime_manifest["layout"]
    python = runtime / layout["python"] / layout["executable"]
    with tempfile.TemporaryDirectory(prefix="plugin-offline-verify-") as temporary:
        run([runtime / layout["uv"], "--no-config", "--no-cache", "pip", "install", "--python", python,
             "--no-python-downloads", "--no-managed-python", "--offline", "--no-index", "--find-links",
             package_root / "wheelhouse", "--only-binary", ":all:", "--require-hashes", "--target", temporary,
             "--link-mode", "copy", "-r", package_root / "requirements.lock"])
        for module in manifest.get("imports", []):
            check_import(python, temporary, module)
    print(json.dumps({"integrity": "passed", "offline_install": "passed-with-empty-cache", "wheels": len(actual),
                      "imports": manifest.get("imports", [])}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--requirements", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-package", type=Path)
    parser.add_argument("--check-import", action="append", default=[])
    args = parser.parse_args()
    try:
        if args.verify_package:
            verify_package(args)
        elif args.wheelhouse and args.requirements and args.output:
            package(args)
        else:
            parser.error("Provide --verify-package, or all of --wheelhouse, --requirements and --output")
    except subprocess.TimeoutExpired:
        parser.exit(1, "Offline packaging failed: A runtime or uv operation exceeded its 120 second time limit\n")
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        parser.exit(1, f"Offline packaging failed: {error}\n")


if __name__ == "__main__":
    main()
