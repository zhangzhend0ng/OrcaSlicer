#!/usr/bin/env python3
"""Stage and verify the pinned plugin runtime without touching an installed app.

Output is a runtime overlay, not a signed application installer. Run on the target
OS; --layout-only permits cross-platform assembly but never claims native checks.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import re
import subprocess
import sys
import tempfile

PYTHON_VERSION = "3.12.13"
UV_VERSION = "0.11.16"
# ADAPTED (port): women baseline was 14a1aa333b6da3ecadf853a4a6285b0f193b7605; the
# SDK/runtime manifests record the absorbing tree's lineage instead.
UPSTREAM = "e944e24ccd4671439fbaf297c72aef660a9a50dc"
MANIFEST = "plugin-runtime.json"
LAYOUTS = {
    "macos": {"python": "Contents/Frameworks/python", "executable": "bin/python3.12",
              "uv": "Contents/MacOS/tools/uv/uv", "host": "Contents/MacOS",
              "resources": "Contents/Resources", "library": "lib/libpython3.12.dylib"},
    "windows": {"python": "python", "executable": "python.exe", "uv": "tools/uv/uv.exe",
                "host": ".", "resources": "resources", "library": "python312.dll"},
    "linux": {"python": "lib/python", "executable": "bin/python3.12", "uv": "resources/tools/uv/uv",
              "host": "bin", "resources": "resources", "library": "lib/libpython3.12.so.1.0"},
}


def native_platform():
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def clean_environment():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("PYTHON", "PIP_", "UV_", "DYLD_", "LD_"))}


def run(command, **kwargs):
    result = subprocess.run([str(p) for p in command], env=clean_environment(), text=True, encoding="utf-8", errors="replace",
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, **kwargs)
    if result.returncode:
        # Do not echo arbitrary build flags or inherited environment into release logs.
        raise ValueError(f"{Path(command[0]).name} failed ({result.returncode}): {result.stderr[-3000:]}")
    return result.stdout.strip()


def fresh_output(output, *inputs):
    """Reject aliases into read-only inputs before creating staging directories."""
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists; choose a fresh artifact directory")
    resolved = output.resolve()
    for source in inputs:
        source = source.resolve(strict=True)
        if resolved == source or resolved.is_relative_to(source):
            raise ValueError("Output must be outside every input directory")
    return output


def checked_relative(value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError(f"Unsafe manifest path: {value}")
    return path


def check_links(root):
    root = root.resolve()
    for path in root.rglob("*"):
        if path.is_symlink():
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError(f"External runtime symlink: {path.relative_to(root)}")


def copy_runtime(source, target):
    source = source.resolve(strict=True)
    check_links(source)
    shutil.copytree(source, target, symlinks=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    # Build prefixes sometimes contain absolute internal aliases; make them portable.
    for path in target.rglob("*"):
        if path.is_symlink() and Path(os.readlink(path)).is_absolute():
            original = source / path.relative_to(target)
            relative = original.resolve(strict=True).relative_to(source)
            path.unlink()
            path.symlink_to(os.path.relpath(target / relative, path.parent), target_is_directory=(target / relative).is_dir())
    check_links(target)


def inventory(root):
    check_links(root)
    entries = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if relative == MANIFEST:
            continue
        if path.is_symlink():
            if Path(os.readlink(path)).is_absolute():
                raise ValueError(f"Absolute runtime symlink: {relative}")
            entries[relative] = {"symlink": os.readlink(path)}
        elif path.is_file():
            entries[relative] = {"sha256": digest(path), "size": path.stat().st_size,
                                 "executable": bool(path.stat().st_mode & stat.S_IXUSR)}
    return entries


def macho(path):
    if not path.is_file() or path.is_symlink():
        return False
    with path.open("rb") as stream:
        return stream.read(4) in (b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf",
                                  b"\xfe\xed\xfa\xcf", b"\xfe\xed\xfa\xce", b"\xbe\xba\xfe\xca", b"\xbf\xba\xfe\xca")


def macho_architectures(path):
    """Read CPU types without running target code (also works on other OSes)."""
    with path.open("rb") as stream:
        header = stream.read(8)
        thin = {b"\xcf\xfa\xed\xfe": "<", b"\xce\xfa\xed\xfe": "<",
                b"\xfe\xed\xfa\xcf": ">", b"\xfe\xed\xfa\xce": ">"}
        if header[:4] in thin:
            if len(header) != 8:
                raise ValueError("Truncated Mach-O header")
            return {struct.unpack(thin[header[:4]] + "I", header[4:])[0]}
        fat = {b"\xca\xfe\xba\xbe": (">", 20), b"\xca\xfe\xba\xbf": (">", 32),
               b"\xbe\xba\xfe\xca": ("<", 20), b"\xbf\xba\xfe\xca": ("<", 32)}
        if header[:4] not in fat:
            raise ValueError(f"Not a Mach-O binary: {path.name}")
        if len(header) != 8:
            raise ValueError("Truncated Mach-O universal header")
        endian, entry_size = fat[header[:4]]
        count = struct.unpack(endian + "I", header[4:])[0]
        table = stream.read(entry_size * min(count, 64))
        if not 0 < count <= 64 or len(table) != count * entry_size:
            raise ValueError("Malformed Mach-O universal architecture table")
        return {struct.unpack_from(endian + "I", table, index * entry_size)[0] for index in range(count)}


def macos_check_architectures(root, layout, host=None):
    reference = root / checked_relative(host) if host else root / layout["python"] / layout["executable"]
    expected = macho_architectures(reference)
    count = 0
    for path in root.rglob("*"):
        if not macho(path):
            continue
        count += 1
        if not expected.issubset(macho_architectures(path)):
            raise ValueError(f"Mach-O architectures do not cover the host/interpreter in {path.relative_to(root)}")
    names = {0x01000007: "x86_64", 0x0100000c: "arm64", 7: "i386", 12: "arm"}
    return {"required": [names.get(cpu, hex(cpu)) for cpu in sorted(expected)], "checked_binaries": count}


def macos_relocate(root, source_python, layout):
    python = root / layout["python"]
    for path in sorted(root.rglob("*")):
        if not macho(path):
            continue
        changed = False
        lines = run(["otool", "-L", path]).splitlines()[1:]
        for line in lines:
            dependency = line.strip().split(" (compatibility version", 1)[0]
            if dependency.startswith(str(source_python) + "/"):
                target = python / Path(dependency).relative_to(source_python)
                replacement = "@loader_path/" + os.path.relpath(target, path.parent)
                if target == path:
                    run(["install_name_tool", "-id", replacement, path])
                else:
                    run(["install_name_tool", "-change", dependency, replacement, path])
                changed = True
            elif dependency.startswith("/") and not dependency.startswith(("/usr/lib/", "/System/Library/")):
                raise ValueError(f"Unbundled Mach-O dependency in {path.relative_to(root)}: {dependency}")
        if changed:
            run(["codesign", "--force", "--sign", "-", path])


def elf_dynamic(path):
    """Return None for non-ELF, False for static ELF, True for PT_DYNAMIC.

    Static uv builds are valid runtime tools: patchelf must never be run on
    them. Read program headers directly, independent of the build host OS.
    """
    if path.is_symlink() or not path.is_file():
        return None
    with path.open("rb") as stream:
        header = stream.read(64)
        if header[:4] != b"\x7fELF":
            return None
        if len(header) < 52 or header[4] not in (1, 2) or header[5] not in (1, 2):
            raise ValueError(f"Malformed ELF header: {path.name}")
        endian = "<" if header[5] == 1 else ">"
        if header[4] == 2:
            if len(header) < 64:
                raise ValueError(f"Truncated ELF64 header: {path.name}")
            offset = struct.unpack_from(endian + "Q", header, 32)[0]
            size, count = struct.unpack_from(endian + "HH", header, 54)
        else:
            offset = struct.unpack_from(endian + "I", header, 28)[0]
            size, count = struct.unpack_from(endian + "HH", header, 42)
        if count and (size < (56 if header[4] == 2 else 32) or offset + size * count > path.stat().st_size):
            raise ValueError(f"Truncated ELF program headers: {path.name}")
        for index in range(count):
            stream.seek(offset + size * index)
            if struct.unpack(endian + "I", stream.read(4))[0] == 2:
                return True
        return False


def origin_rpath(path, root, value):
    match = re.fullmatch(r"(?:\$ORIGIN|\$\{ORIGIN\})(/.*)?", value)
    if not match:
        raise ValueError(f"Nonportable ELF RPATH in {path.relative_to(root)}: {value}")
    resolved = (path.parent / (match.group(1) or "").lstrip("/")).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"ELF RPATH escapes runtime in {path.relative_to(root)}: {value}")
    return value


def linux_relocate(root, layout):
    # Linux must use the matching distribution's patchelf and be tested there.
    python = root / layout["python"]
    for path in sorted(root.rglob("*")):
        if elf_dynamic(path) is not True:
            continue
        if not shutil.which("patchelf"):
            raise ValueError("Linux native staging requires patchelf")
        needed = run(["patchelf", "--print-needed", path]).splitlines()
        for dependency in needed:
            if "libpython3.12" in dependency:
                run(["patchelf", "--replace-needed", dependency, "libpython3.12.so.1.0", path])
            elif "/" in dependency:
                raise ValueError(f"Absolute ELF dependency in {path.relative_to(root)}")
        old_rpath = run(["patchelf", "--print-rpath", path])
        relative = "$ORIGIN/" + os.path.relpath(python / "lib", path.parent)
        retained = [origin_rpath(path, root, p) for p in old_rpath.split(":") if p.startswith(("$ORIGIN", "${ORIGIN}"))]
        run(["patchelf", "--set-rpath", ":".join(dict.fromkeys([relative, *retained])), path])


def linux_check_links(root, paths=None):
    count = 0
    for path in paths if paths is not None else root.rglob("*"):
        if elf_dynamic(path) is not True:
            continue
        count += 1
        for value in run(["patchelf", "--print-rpath", path]).split(":"):
            if value:
                origin_rpath(path, root, value)
        needed = run(["patchelf", "--print-needed", path]).splitlines()
        if any("/" in name for name in needed):
            raise ValueError(f"Nonportable ELF dependency in {path.relative_to(root)}")
        if not needed:
            continue
        links = run(["ldd", path])
        if "not found" in links:
            raise ValueError(f"Unresolved ELF dependency in {path.relative_to(root)}")
        for line in links.splitlines():
            target = line.split("=>", 1)[-1].strip().split(" ", 1)[0]
            if not target.startswith("/"):
                continue  # kernel-provided linux-vdso entry
            resolved = Path(target).resolve(strict=True)
            system = any(resolved.is_relative_to(Path(prefix).resolve()) for prefix in ("/lib", "/lib64", "/usr/lib", "/usr/lib64"))
            if not resolved.is_relative_to(root) and not system:
                raise ValueError(f"Unbundled ELF dependency in {path.relative_to(root)}: {target}")
    return count


def macos_check_links(root, executable=None):
    count = 0
    for path in root.rglob("*"):
        if not macho(path):
            continue
        count += 1
        identities = run(["otool", "-D", path]).splitlines()[1:]
        load_commands = run(["otool", "-l", path]).splitlines()
        rpaths = []
        for index, command in enumerate(load_commands):
            if command.strip() == "cmd LC_RPATH":
                rpaths.append(load_commands[index + 2].strip().removeprefix("path ").rsplit(" (offset ", 1)[0])
        for line in run(["otool", "-L", path]).splitlines()[1:]:
            dependency = line.strip().split(" (compatibility version", 1)[0]
            if dependency in identities:
                continue  # LC_ID_DYLIB identifies this file; it is not a load.
            if dependency.startswith(("/usr/lib/", "/System/Library/")):
                continue
            candidates = [dependency]
            if dependency.startswith("@rpath/"):
                candidates = [rpath + "/" + dependency[len("@rpath/"):] for rpath in rpaths]
            resolved_candidates = []
            for candidate in candidates:
                if candidate.startswith("@loader_path/"):
                    resolved_candidates.append((path.parent / candidate[len("@loader_path/"):]).resolve())
                elif executable and candidate.startswith("@executable_path/"):
                    resolved_candidates.append((executable.parent / candidate[len("@executable_path/"):]).resolve())
            if any(resolved.is_relative_to(root) and resolved.is_file() for resolved in resolved_candidates):
                continue
            # Never silently rely on a developer's RPATH or absolute prefix.
            raise ValueError(f"Unresolved/nonportable Mach-O link in {path.relative_to(root)}: {dependency}")
    return count


def probe(root, manifest, runtime_only=False):
    if manifest["platform"] != native_platform():
        raise ValueError("Native verification must run on the target OS")
    layout = manifest["layout"]
    architecture = macos_check_architectures(root, layout, manifest.get("host_binary")) if manifest["platform"] == "macos" else None
    python_root = root / layout["python"]
    executable = python_root / layout["executable"]
    code = """import sys, json, ssl, sqlite3, ctypes, zlib, bz2, lzma, multiprocessing, pathlib
root = pathlib.Path(sys.argv[1]).resolve()
assert sys.version.split()[0] == sys.argv[2], sys.version
assert pathlib.Path(sys.prefix).resolve() == root, sys.prefix
assert all(pathlib.Path(p).resolve().is_relative_to(root) for p in sys.path), sys.path
ctypes.CDLL(str(root / sys.argv[3]))
print(json.dumps({'python': sys.version.split()[0], 'machine': __import__('platform').machine(),
                  'stdlib': ['ssl','sqlite3','ctypes','zlib','bz2','lzma','multiprocessing']}))
"""
    result = json.loads(run([executable, "-I", "-B", "-c", code, python_root, manifest["python_version"], layout["library"]]))
    uv = run([root / layout["uv"], "--version"]).split()
    if len(uv) < 2 or uv[1] != manifest["uv_version"]:
        raise ValueError("Bundled uv does not match pinned version")
    result["uv"] = uv[1]
    if manifest["platform"] == "macos":
        result["macho_architectures"] = architecture
        result["macho_dependency_checks"] = macos_check_links(root, root / checked_relative(manifest["host_binary"]) if manifest.get("host_binary") else None)
    elif manifest["platform"] == "linux":
        result["elf_dependency_checks"] = linux_check_links(root, [root / checked_relative(name) for name in manifest["files"]] if runtime_only else None)
    return result


def verify(root, native=False):
    root = root.resolve(strict=True)
    manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("layout") != LAYOUTS.get(manifest.get("platform")):
        raise ValueError("Unsupported runtime manifest/layout")
    for relative in manifest["files"]:
        checked_relative(relative)
    actual = inventory(root)
    if actual != manifest["files"]:
        missing = sorted(set(manifest["files"]) - set(actual))
        extra = sorted(set(actual) - set(manifest["files"]))
        changed = [p for p in actual.keys() & manifest["files"].keys() if actual[p] != manifest["files"][p]]
        raise ValueError(f"Runtime inventory mismatch: missing={missing[:3]}, extra={extra[:3]}, changed={changed[:3]}")
    result = {"files": len(actual), "platform": manifest["platform"], "integrity": "passed",
              "native": "not-run", "signing": "not-distribution-signed"}
    if native:
        result["native"] = probe(root, manifest)
    return result


def stage(args):
    source = args.python_root.resolve(strict=True)
    output = fresh_output(args.output, source)
    uv = args.uv.resolve(strict=True)
    layout = LAYOUTS[args.platform]
    if not args.layout_only and args.platform != native_platform():
        raise ValueError("Use --layout-only for cross-platform assembly; native validation remains required")
    if not (source / layout["executable"]).is_file() or not (source / layout["library"]).is_file():
        raise ValueError("Python prefix is missing the platform interpreter or shared library")
    encodings = source / ("Lib" if args.platform == "windows" else "lib/python3.12") / "encodings/__init__.py"
    if not encodings.is_file():
        raise ValueError("Python prefix is missing the uncompressed standard library")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".plugin-runtime-", dir=output.parent) as temporary:
        root = Path(temporary) / "payload"
        root.mkdir()
        copy_runtime(source, root / layout["python"])
        target_uv = root / layout["uv"]
        target_uv.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(uv, target_uv)
        (root / layout["resources"]).mkdir(parents=True, exist_ok=True)
        host_binary = None
        if args.host_binary:
            target = root / layout["host"] / args.host_binary.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(args.host_binary.resolve(strict=True), target)
            host_binary = target.relative_to(root).as_posix()
        if args.platform == "windows":
            # The PE loader needs this before PythonInterpreter can run.
            for dll in source.glob("*.dll"):
                shutil.copy2(dll, root / dll.name)
        if not args.layout_only:
            if args.platform == "macos":
                macos_relocate(root, source, layout)
            elif args.platform == "linux":
                linux_relocate(root, layout)
        manifest = {"schema": 1, "upstream_commit": UPSTREAM, "platform": args.platform,
                    "python_version": PYTHON_VERSION, "uv_version": args.uv_version,
                    "layout": layout, "host_binary": host_binary, "relocation": "not-run" if args.layout_only else "native",
                    "source_uv_sha256": digest(uv), "files": inventory(root)}
        (root / MANIFEST).write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = verify(root, native=not args.layout_only)
        root.rename(output)
    print(json.dumps({"output": str(output), **result}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("stage")
    create.add_argument("--platform", choices=LAYOUTS, default=native_platform())
    create.add_argument("--python-root", type=Path, required=True)
    create.add_argument("--uv", type=Path, required=True)
    create.add_argument("--uv-version", default=UV_VERSION)
    create.add_argument("--host-binary", type=Path, help="Optional copied binary; never launched")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--layout-only", action="store_true")
    check = commands.add_parser("verify")
    check.add_argument("root", type=Path)
    check.add_argument("--native", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "stage":
            stage(args)
        else:
            print(json.dumps(verify(args.root, args.native), ensure_ascii=False))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Runtime packaging failed: {error}\n")


if __name__ == "__main__":
    main()
