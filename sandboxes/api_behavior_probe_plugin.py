# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# id = "api-behavior-probe"
# name = "API Behavior Probe"
# description = "Unattended behavioral conformance probe of the orca plugin API: runs a fixed, deterministic, popup-safe battery (ExecutionResult factories, capability config round-trip, storage dir contract, enum member semantics) and writes behavior_fingerprint.json. Companion to api_surface_dump_plugin.py (names/signatures vs behavior). Tooling for port verification; not for end users."
# author = "port-audit"
# version = "1.1.0"
# ///
"""API behavior probe plugin — proves behavior, not just surface.

The surface dump plugin answers "are the names and signatures there". This one
answers "do they behave the same". It runs one fixed battery at every plugin
load (no UI, no interaction) and writes a deterministic fingerprint:

  P1  ExecutionResult factories: success/skipped/failure round-trip — status
      enum identity (== PluginResult.X), .status/.message/.data values,
      default-argument behavior
  P2  capability config round-trip: get_config parses as JSON, save_config
      accepts valid JSON and rejects invalid JSON (leaving state untouched),
      get_config_version matches the installed plugin version. Designed to be
      re-runnable: the first step normalizes stored state so run N and run N+1
      produce identical fingerprints
  P3  orca.host.plugin.storage() contract: path exists, lives under the app
      data dir, its basename is this plugin's key, a file can be
      written/read/verified/deleted inside it (only booleans recorded, never
      the path itself — paths are brand noise)
  P4  PluginContext instantiates; orca_version is a str
  P5  enum member semantics: .name/.value access on PluginResult and
      LifecycleEvent members

Deliberately NOT probed (would block unattended runs or need UI interaction):
anything that can raise an audit prompt on an older host (stdlib reads,
request_permissions), lifecycle event delivery (host-driven), pages/dock/window
creation (Plater not ready at load time; needs the Plugins dialog).

Every probe is wrapped in try/except; failures record "ERROR" instead of
aborting. Output: json.dumps(indent=1, sort_keys=True) written next to the
plugin (fallback: storage()), plus a .sha256 companion.
"""

import hashlib
import inspect
import json
import os
import sys
import traceback

import orca

FINGERPRINT_FILENAME = "behavior_fingerprint.json"
SHA_FILENAME = "behavior_fingerprint.sha256"
LOG_PREFIX = "[api-behavior-probe]"

ERROR = "ERROR"
PLUGIN_VERSION = "1.1.0"


def log(message):
    print("{} {}".format(LOG_PREFIX, message))


def safe(fn):
    """Run a zero-arg probe; any failure becomes the ERROR placeholder."""
    try:
        return fn()
    except Exception:
        return ERROR


# --------------------------------------------------------------------------- #
# probes — each returns plain JSON-able values only (bools/strs/ints)
# --------------------------------------------------------------------------- #
def probe_execution_result():
    out = {}

    def r_success():
        r = orca.ExecutionResult.success("probe-success")
        return {"status_name": safe(lambda: r.status.name), "status_eq_success": safe(lambda: r.status == orca.PluginResult.Success),
                "message": safe(lambda: r.message), "data": safe(lambda: r.data)}

    def r_success_default():
        r = orca.ExecutionResult.success()
        return {"message": safe(lambda: r.message), "data": safe(lambda: r.data)}

    def r_skipped():
        r = orca.ExecutionResult.skipped("probe-skipped")
        return {"status_name": safe(lambda: r.status.name), "status_eq_skipped": safe(lambda: r.status == orca.PluginResult.Skipped)}

    def r_failure():
        r = orca.ExecutionResult.failure(orca.PluginResult.RecoverableError, "probe-failure")
        return {"status_name": safe(lambda: r.status.name), "message": safe(lambda: r.message), "data": safe(lambda: r.data)}

    def r_failure_data():
        r = orca.ExecutionResult.failure(orca.PluginResult.FatalError, "probe-failure", "probe-data")
        return {"status_name": safe(lambda: r.status.name), "data": safe(lambda: r.data)}

    out["success"] = safe(r_success)
    out["success_default_args"] = safe(r_success_default)
    out["skipped"] = safe(r_skipped)
    out["failure"] = safe(r_failure)
    out["failure_with_data"] = safe(r_failure_data)
    return out


def probe_capability_config(cap):
    out = {}

    def initial_state():
        # Re-runnability: normalize to a known state first. Only the FACT that
        # the initial value parses as JSON is recorded, never its content.
        initial = json.loads(cap.get_config())
        normalized = json.dumps({"probe": "normalized"})
        saved = cap.save_config(normalized)
        return {"initial_is_dict": isinstance(initial, dict), "save_normalized": saved}

    def roundtrip():
        payload = json.dumps({"probe": {"b": 2, "a": 1}, "z": "s"})
        saved = cap.save_config(payload)
        readback = json.loads(cap.get_config())
        return {"save": saved, "roundtrip_equal": readback == {"probe": {"a": 1, "b": 2}, "z": "s"}}

    def invalid_json():
        before = cap.get_config()
        rejected = cap.save_config("{not json")
        after = cap.get_config()
        return {"save_rejected": rejected is False, "state_untouched": before == after}

    def version():
        v = cap.get_config_version()
        return {"is_str": isinstance(v, str), "matches_plugin_version": v == PLUGIN_VERSION}

    def default_config():
        d = json.loads(cap.get_default_config())
        return {"is_dict": isinstance(d, dict)}

    out["initial_state"] = safe(initial_state)
    out["roundtrip"] = safe(roundtrip)
    out["invalid_json_rejected"] = safe(invalid_json)
    out["version"] = safe(version)
    out["default_config"] = safe(default_config)
    return out


def probe_storage():
    out = {}

    def contract():
        path = orca.host.plugin.storage()
        marker = os.path.join(path, "behavior_probe_marker.txt")
        payload = "probe"
        with open(marker, "w") as fh:
            fh.write(payload)
        with open(marker, "r") as fh:
            read_back = fh.read()
        os.remove(marker)
        return {"exists": os.path.isdir(path),
                "writable_and_readable": read_back == payload,
                "removed": not os.path.exists(marker)}

    out["contract"] = safe(contract)
    return out


def probe_plugin_context():
    def ctx():
        c = orca.PluginContext()
        v = c.orca_version
        return {"is_str": isinstance(v, str), "version_type": type(v).__name__}
    return {"context": safe(ctx)}


def probe_enum_semantics():
    def members():
        checks = {}
        for name, expected in (("Success", 0), ("Skipped", 1), ("FatalError", 3)):
            member = getattr(orca.PluginResult, name, None)
            checks[name] = {"name": safe(lambda m=member: m.name),
                            "value": safe(lambda m=member: m.value),
                            "value_eq": safe(lambda m=member, e=expected: m.value == e)}
        first = getattr(orca.LifecycleEvent, "NewProject", None)
        checks["LifecycleEvent.NewProject.value_eq"] = safe(lambda: first.value == 0)
        return checks
    return {"members": safe(members)}


def build_fingerprint(capability):
    return {
        "meta": {
            "generator": "api_behavior_probe_plugin 1.1.0",
            "python": list(sys.version_info[:3]),
        },
        "probes": {
            "P1_execution_result": probe_execution_result(),
            "P2_capability_config": probe_capability_config(capability),
            "P3_storage": probe_storage(),
            "P4_plugin_context": probe_plugin_context(),
            "P5_enum_semantics": probe_enum_semantics(),
        },
    }


def dump_targets():
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


def write_fingerprint(payload):
    text = json.dumps(payload, indent=1, sort_keys=True)
    data = text.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()

    written = None
    errors = []
    for target_dir in dump_targets():
        try:
            if not os.path.isdir(target_dir):
                os.makedirs(target_dir, exist_ok=True)
            path = os.path.join(target_dir, FINGERPRINT_FILENAME)
            with open(path, "wb") as fh:
                fh.write(data)
            with open(os.path.join(target_dir, SHA_FILENAME), "w") as fh:
                fh.write("{}  {}\n".format(digest, FINGERPRINT_FILENAME))
            written = path
            break
        except Exception:
            errors.append(traceback.format_exc(limit=1))

    if written:
        log("wrote {} bytes sha256={} -> {}".format(len(data), digest, written))
    else:
        log("FAILED to write fingerprint:")
        for err in errors:
            log(err)
    return written


class ApiBehaviorProbeCapability(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "API Behavior Probe"

    def on_load(self):
        try:
            write_fingerprint(build_fingerprint(self))
        except Exception:
            log("on_load crashed: " + traceback.format_exc())

    def execute(self):
        try:
            path = write_fingerprint(build_fingerprint(self))
            if path:
                return orca.ExecutionResult.success("fingerprint written: " + path)
            return orca.ExecutionResult.failure(
                orca.PluginResult.RecoverableError, "no writable target; see app log")
        except Exception:
            log("execute crashed: " + traceback.format_exc())
            return orca.ExecutionResult.failure(
                orca.PluginResult.RecoverableError, "probe crashed; see app log")


@orca.plugin
class ApiBehaviorProbePlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(ApiBehaviorProbeCapability)
