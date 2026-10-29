# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# id = "api-surface-dump"
# name = "API Surface Dump"
# description = "Unattended dump of the whole Python-visible orca module tree (classes, methods, signatures, enums, constants by type) to api_surface.json. Tooling for port API surface reconciliation; not for end users."
# author = "port-audit"
# version = "1.1.0"
# ///
"""API surface dump plugin — reconciliation tooling, not an end-user feature.

On every plugin load (no UI interaction, no config) it walks the `orca` module
tree by dynamic discovery — every attribute of `orca` (and recursively of any
attribute that is a module whose name starts with "orca") is catalogued:

  classes    pybind11 and plain classes: base names, public methods with a
             signature (inspect.signature, falling back to the pybind11
             convention of the signature as the first __doc__ line), property
             descriptors, static attributes by type name, enum member values
  functions  module-level callables with a signature
  constants  module-level non-callable names recorded as TYPE NAME ONLY
             (values are deliberately not recorded: app name/path/version
             strings would turn every diff into brand noise; enum member
             values are the exception, they are contract)

Rules the dump follows so it can be diffed across apps deterministically:
  - every name starting with "_" is skipped;
  - every single entry is wrapped in try/except; a failing introspection
    records the literal "ERROR" instead of aborting the dump;
  - the output tree is fully sorted and serialized with
    json.dumps(indent=1, sort_keys=True); the SHA256 of the written bytes is
    logged and stored next to the file in api_surface.sha256.

The file is written next to the plugin itself (inside the app data dir, an
audit-allowed root, so no permission dialog is expected); if that fails, it
falls back to orca.host.plugin.storage().
"""

import collections
import hashlib
import inspect
import json
import os
import re
import sys
import traceback

import orca

DUMP_FILENAME = "api_surface.json"
SHA_FILENAME = "api_surface.sha256"
LOG_PREFIX = "[api-surface-dump]"

ERROR = "ERROR"


def log(message):
    # print() is captured by the host console/log when one is attached; the
    # sha256 companion file is the durable record either way.
    print("{} {}".format(LOG_PREFIX, message))


# --------------------------------------------------------------------------- #
# signature extraction
# --------------------------------------------------------------------------- #
def signature_of(obj):
    """Best-effort signature string for a callable.

    inspect.signature first; pybind11 functions usually reject it, and then the
    __doc__ is used, where pybind11 puts the signature: line 1 for a single
    overload, or an "Overloaded function." block listing every overload as
    "N. signature" lines — the whole set is the contract, so all numbered
    signatures are captured, not just the first.
    """
    try:
        return str(inspect.signature(obj))
    except Exception:
        pass
    doc = getattr(obj, "__doc__", None)
    if not doc:
        return "?"
    lines = [line.strip() for line in doc.strip().splitlines()]
    if any(line == "Overloaded function." for line in lines):
        overloaded = [line.split(". ", 1)[1].strip()
                      for line in lines if re.match(r"^\d+\.\s+\S", line)]
        if overloaded:
            return "\n".join(overloaded)
    first = next((line for line in lines if line), "")
    return first if first else "?"


def enum_members_of(cls):
    """{name: value} for enum-like classes.

    pybind11 py::enum_ classes do NOT subclass enum.Enum (their base is
    pybind11_object), but like Python enums they expose a __members__ dict:
    name -> underlying value on pybind11, name -> member on enum.Enum (take
    .value there). __members__ is the reliable discriminator for both.
    """
    members = getattr(cls, "__members__", None)
    # enum.Enum hands out a mappingproxy, pybind11 a plain dict: accept any Mapping.
    if not isinstance(members, collections.abc.Mapping):
        return None
    out = {}
    for name in sorted(members):
        try:
            raw = members[name]
            value = getattr(raw, "value", raw)
            if isinstance(value, (bool, int, float, str)):
                out[name] = value
            else:
                out[name] = str(value)
        except Exception:
            out[name] = ERROR
    return out


def type_name_of(obj):
    try:
        return type(obj).__name__
    except Exception:
        return ERROR


def is_property_like(attr):
    if isinstance(attr, property):
        return True
    # pybind11 def_readwrite/def_property on classes arrive as builtins from
    # the pybind11_builtins module; match by type name so both pybind11
    # variants are classified without importing pybind11_builtins.
    return "property" in type_name_of(attr).lower()


# --------------------------------------------------------------------------- #
# per-object catalogue
# --------------------------------------------------------------------------- #
def describe_class(cls):
    """Normalized public surface of one class (pybind11 or plain)."""
    out = {
        "bases": [],
        "methods": {},
        "properties": {},
        "attributes": {},
        "enum_members": {},
    }

    try:
        bases = []
        for base in getattr(cls, "__bases__", ()):
            name = getattr(base, "__name__", None)
            bases.append(name if name else type_name_of(base))
        out["bases"] = sorted(bases)
    except Exception:
        out["bases"] = [ERROR]

    is_enum = False
    enum_members = None
    try:
        enum_members = enum_members_of(cls)
        is_enum = enum_members is not None
    except Exception:
        is_enum = False
    if is_enum:
        out["enum_members"] = enum_members

    for name in sorted(dir(cls)):
        if name.startswith("_"):
            continue
        if is_enum and name in out["enum_members"]:
            continue
        try:
            attr = getattr(cls, name)
        except Exception:
            out["attributes"][name] = ERROR
            continue

        try:
            if callable(attr):
                out["methods"][name] = signature_of(attr)
            elif is_property_like(attr):
                out["properties"][name] = type_name_of(attr)
            else:
                out["attributes"][name] = type_name_of(attr)
        except Exception:
            bucket = "methods" if callable(attr) else "attributes"
            out[bucket][name] = ERROR

    return out


def describe_module(mod, seen):
    """Normalized public surface of one module; recurses into orca submodules."""
    out = {
        "classes": {},
        "functions": {},
        "constants": {},
        "modules": [],
    }
    submodules = []

    for name in sorted(dir(mod)):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(mod, name)
        except Exception:
            # The attribute exists but blows up on access: record it as an
            # ERROR constant so the diff still shows the name exists here.
            out["constants"][name] = ERROR
            continue

        mod_name = getattr(attr, "__name__", None)
        if inspect.ismodule(attr) and isinstance(mod_name, str) and mod_name.startswith("orca"):
            if mod_name not in seen:
                submodules.append(name)
            continue

        try:
            if inspect.isclass(attr):
                out["classes"][name] = describe_class(attr)
            elif callable(attr):
                out["functions"][name] = signature_of(attr)
            else:
                out["constants"][name] = type_name_of(attr)
        except Exception:
            out["constants"][name] = ERROR

    out["modules"] = sorted(submodules)
    return out, submodules


def build_tree():
    modules = {}
    seen = set()
    queue = [orca]
    while queue:
        mod = queue.pop(0)
        mod_name = getattr(mod, "__name__", None)
        if not isinstance(mod_name, str) or mod_name in seen or not mod_name.startswith("orca"):
            continue
        seen.add(mod_name)
        # describe_module needs `seen` pre-populated with mod_name so a
        # self-referencing attribute does not queue the module twice.
        description, submodules = describe_module(mod, seen)
        modules[mod_name] = description
        for sub_name in submodules:
            try:
                sub = getattr(mod, sub_name)
                if getattr(sub, "__name__", None) not in seen:
                    queue.append(sub)
            except Exception:
                pass
    return modules


# --------------------------------------------------------------------------- #
# output
# --------------------------------------------------------------------------- #
def dump_targets():
    """Write locations in priority order: the plugin's own folder, then orca.host.plugin.storage()."""
    targets = []
    try:
        own_dir = os.path.dirname(os.path.abspath(__file__))
        if own_dir:
            targets.append(own_dir)
    except Exception:
        pass
    try:
        storage = orca.host.plugin.storage()
        if storage and storage not in targets:
            targets.append(storage)
    except Exception:
        pass
    return targets


def write_dump():
    payload = {
        "meta": {
            "generator": "api_surface_dump_plugin 1.1.0",
            "python": list(sys.version_info[:3]),
        },
        "modules": build_tree(),
    }
    text = json.dumps(payload, indent=1, sort_keys=True)
    data = text.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()

    written = None
    errors = []
    for target_dir in dump_targets():
        try:
            if not os.path.isdir(target_dir):
                os.makedirs(target_dir, exist_ok=True)
            path = os.path.join(target_dir, DUMP_FILENAME)
            with open(path, "wb") as fh:
                fh.write(data)
            with open(os.path.join(target_dir, SHA_FILENAME), "w") as fh:
                fh.write("{}  {}\n".format(digest, DUMP_FILENAME))
            written = path
            break
        except Exception:
            errors.append("{}: {}".format(target_dir, traceback.format_exc(limit=1)))

    if written:
        log("wrote {} bytes sha256={} -> {}".format(len(data), digest, written))
    else:
        log("FAILED to write dump:")
        for err in errors:
            log(err)
    return written


# --------------------------------------------------------------------------- #
# plugin shape
# --------------------------------------------------------------------------- #
class ApiSurfaceDumpCapability(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "API Surface Dump"

    def on_load(self):
        try:
            write_dump()
        except Exception:
            log("on_load crashed: " + traceback.format_exc())

    def execute(self):
        path = None
        try:
            path = write_dump()
        except Exception:
            log("execute crashed: " + traceback.format_exc())
            return orca.ExecutionResult.failure(
                orca.PluginResult.RecoverableError, "api surface dump failed; see app log")
        if path:
            return orca.ExecutionResult.success("dump written: " + path)
        return orca.ExecutionResult.failure(
            orca.PluginResult.RecoverableError, "no writable dump target; see app log")


@orca.plugin
class ApiSurfaceDumpPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(ApiSurfaceDumpCapability)
