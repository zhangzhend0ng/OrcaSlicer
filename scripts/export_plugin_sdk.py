#!/usr/bin/env python3
"""Executed by orca_plugin_sdk_export inside the production embedded interpreter.

Only inspect live members; do not construct host classes or call their methods.
Signatures that cannot be represented in Python syntax are retained in api.json
and emitted as Any, never replaced with an invented contract.
"""
import ast
import inspect
import json
from pathlib import Path
import re
import types


# Public Python protocols explicitly bound by pybind are API too. Export only
# members actually present; omit implementation metadata such as __dict__.
PUBLIC_SPECIAL_METHODS = {"__" + name + "__" for name in (
    "init", "call", "getitem", "setitem", "delitem", "len", "iter", "next", "contains",
    "repr", "str", "bool", "hash", "int", "float", "index", "eq", "ne", "lt", "le", "gt", "ge",
    "neg", "pos", "abs", "invert", "add", "radd", "iadd", "sub", "rsub", "isub",
    "mul", "rmul", "imul", "matmul", "rmatmul", "imatmul", "truediv", "rtruediv", "itruediv",
    "floordiv", "rfloordiv", "ifloordiv", "mod", "rmod", "imod", "pow", "rpow", "ipow",
    "and", "rand", "iand", "or", "ror", "ior", "xor", "rxor", "ixor", "lshift", "rlshift", "ilshift",
    "rshift", "rrshift", "irshift", "enter", "exit", "copy", "deepcopy"
)}


def signatures(name, value):
    result = []
    for line in (getattr(value, "__doc__", "") or "").splitlines():
        line = re.sub(r"^\d+\.\s*", "", line.strip())
        if not line.startswith(name + "("):
            continue
        line = re.sub(r"<[^<>]+>", "...", line)
        try:
            ast.parse("def " + line + ": ...")
        except SyntaxError:
            continue
        result.append(line)
    result = list(dict.fromkeys(result))
    # pybind places an untyped dispatcher before its numbered overloads. It is
    # not another overload and would mask every typed overload in the editor.
    if len(result) > 1:
        result = [line for line in result if line != name + "(*args, **kwargs)"]
    return result


def export(output):
    import orca
    if getattr(orca, "__file__", None):
        raise RuntimeError("Expected the app's embedded orca module")
    output.mkdir(parents=True, exist_ok=False)
    typings = output / "typings"
    typings.mkdir()
    inventory = {}
    seen = set()

    def members(value, scope, indent=""):
        lines = []
        items = []
        for name in sorted(vars(value)):
            if not name.isidentifier() or (name.startswith("_") and name not in
                    PUBLIC_SPECIAL_METHODS):
                continue
            item = inspect.getattr_static(value, name)
            if isinstance(item, types.ModuleType):
                if item.__name__.startswith("orca."):
                    write_module(item)
                    lines.append(indent + f"from {item.__name__} import *  # submodule: {name}")
                    # Real submodule attribute for type checkers, no imported symbols.
                    lines[-1] = indent + f"from . import {name} as {name}"
                    items.append({"name": name, "kind": "module", "module": item.__name__})
                continue
            entry = {"name": name, "kind": type(item).__name__}
            if isinstance(item, type) and item.__module__.startswith("orca"):
                if id(item) in seen:
                    lines.append(indent + f"{name}: Any")
                else:
                    seen.add(id(item))
                    bases = [base.__module__ + "." + base.__name__ for base in item.__bases__
                             if base.__module__.startswith("orca")]
                    lines.append(indent + f"class {name}" + ("(" + ", ".join(bases) + ")" if bases else "") + ":")
                    body, entry["members"] = members(item, scope + "." + name, indent + "    ")
                    lines.extend(body or [indent + "    ..."])
            elif isinstance(item, property):
                lines.extend([indent + "@property", indent + f"def {name}(self) -> Any: ..."])
                if item.fset is not None:
                    lines.extend([indent + f"@{name}.setter", indent + f"def {name}(self, value: Any) -> None: ..."])
                entry["doc"] = item.__doc__
            elif callable(item) or isinstance(item, (staticmethod, classmethod)):
                target = item.__func__ if isinstance(item, (staticmethod, classmethod)) else item
                found = signatures(name, target)
                entry["signatures"] = found
                entry["doc"] = getattr(target, "__doc__", None)
                static = isinstance(item, staticmethod) or inspect.isbuiltin(item) and isinstance(value, type)
                receiver = "self, " if isinstance(value, type) and not static else ""
                if isinstance(item, classmethod):
                    receiver = "cls, "
                fallback = name + "(" + receiver + "*args: Any, **kwargs: Any) -> " + ("None" if name == "__init__" else "Any")
                for signature in found or [fallback]:
                    if len(found) > 1:
                        lines.append(indent + "@overload")
                    if static:
                        lines.append(indent + "@staticmethod")
                    if isinstance(item, classmethod):
                        lines.append(indent + "@classmethod")
                    lines.append(indent + "def " + signature + ": ...")
            else:
                annotation = type(item).__name__ if type(item).__module__ == "builtins" and type(item).__name__ in {
                    "int", "str", "bool", "float", "bytes"} else "Any"
                lines.append(indent + f"{name}: {annotation}")
            items.append(entry)
        return lines, items

    def write_module(module):
        if module.__name__ in inventory:
            return
        inventory[module.__name__] = []
        lines, entries = members(module, module.__name__)
        inventory[module.__name__] = entries
        target = typings.joinpath(*module.__name__.split("."), "__init__.pyi")
        target.parent.mkdir(parents=True, exist_ok=True)
        source = ("# Generated from the live Snapmaker Orca embedded bindings.\n"
                  "from __future__ import annotations\nimport orca\nimport typing\nimport collections.abc\n"
                  "from typing import Any, Callable, ClassVar, Iterable, Iterator, Optional, Sequence, overload\n\n"
                  + "\n".join(lines) + "\n")
        ast.parse(source)
        target.write_text(source, encoding="utf-8")

    write_module(orca)
    (output / "api.json").write_text(json.dumps({"source": "live-embedded-orca", "modules": inventory}, indent=2) + "\n", encoding="utf-8")


if "SDK_OUTPUT" in globals():
    export(Path(SDK_OUTPUT))
elif __name__ == "__main__":
    raise SystemExit("Run this through generate_plugin_sdk.py and orca_plugin_sdk_export")
