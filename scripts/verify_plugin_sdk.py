#!/usr/bin/env python3
"""Verify an exported SDK's hashes, syntax and exact live-member inventory."""
import argparse
import ast
import json
from pathlib import Path

from package_plugin_runtime import digest, checked_relative


def declared_members(nodes):
    members = {}
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            members[node.name] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            members[node.target.id] = node
        elif isinstance(node, ast.ImportFrom) and node.module is None:
            for alias in node.names:
                members[alias.asname or alias.name] = node
    return members


def verify_members(nodes, entries, scope):
    actual = declared_members(nodes)
    expected = {entry["name"] for entry in entries}
    if set(actual) != expected:
        raise ValueError(f"SDK/live inventory mismatch at {scope}")
    for entry in entries:
        if "members" in entry:
            node = actual[entry["name"]]
            if not isinstance(node, ast.ClassDef):
                raise ValueError(f"Missing live class {scope}.{entry['name']}")
            verify_members(node.body, entry["members"], scope + "." + entry["name"])


def verify_sdk(root):
    root = root.resolve(strict=True)
    manifest = json.loads((root / "sdk.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("source") != "live-embedded-orca":
        raise ValueError("Unsupported SDK provenance")
    actual = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("SDK symlinks are not supported")
        if path.is_file() and path != root / "sdk.json":
            actual[path.relative_to(root).as_posix()] = digest(path)
    for path in manifest["files"]:
        checked_relative(path)
    if actual != manifest["files"]:
        raise ValueError("SDK integrity mismatch")
    api = json.loads((root / "api.json").read_text(encoding="utf-8"))
    modules = api["modules"]
    for name, members in modules.items():
        if name != "orca" and not name.startswith("orca."):
            raise ValueError("Unexpected exported module")
        if not all(part.isidentifier() for part in name.split(".")):
            raise ValueError("Invalid module name")
        stub = root.joinpath("typings", *name.split("."), "__init__.pyi")
        tree = ast.parse(stub.read_text(encoding="utf-8"))
        verify_members(tree.body, members, name)
    if len(list((root / "typings").rglob("*.pyi"))) != len(modules):
        raise ValueError("Unexpected stub module")
    return {"integrity": "passed", "live_members": "matched", "modules": len(modules)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify_sdk(args.root)))
    except (OSError, ValueError, SyntaxError, KeyError) as error:
        parser.exit(1, f"SDK verification failed: {error}\n")


if __name__ == "__main__":
    main()
