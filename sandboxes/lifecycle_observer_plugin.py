# /// script
# requires-python = ">=3.12"
#
# [tool.orcaslicer.plugin]
# id = "lifecycle-observer"
# name = "Lifecycle Observer"
# description = "Unattended recorder of lifecycle events seen during boot (name, count, first-seen order, plater-readiness) to lifecycle_events.json. Tooling for port verification; not for end users."
# author = "port-audit"
# version = "1.0.1"
# ///
"""Lifecycle observer — records which lifecycle events reach a plugin during
an unattended boot, and whether the Plater is touchable when they do.

Answers the smoke-harness question "which event can a probe hook to run host
mutators after the UI is up" with observations instead of guesses. Output:
lifecycle_events.json next to the plugin:
  events      [{name, count}] in first-seen order
  plater_at_load   whether orca.host.plater() answered during on_load
  ui_thread        name of the thread on_load ran on
"""

import json
import os
import threading
import traceback

import orca

OUT_FILENAME = "lifecycle_events.json"
LOG_PREFIX = "[lifecycle-observer]"

_seen = {}
_seq = []


def _record(event):
    name = getattr(event, "name", str(event))
    if name not in _seen:
        _seen[name] = 0
        _seq.append(name)
    _seen[name] += 1


def _flush(base):
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, OUT_FILENAME), "w", encoding="utf-8") as fh:
            json.dump({"events": [{"name": n, "count": _seen[n]} for n in _seq], **base},
                      fh, indent=1, sort_keys=True)
    except Exception:
        print(LOG_PREFIX + " flush failed: " + traceback.format_exc())


class ObserverCapability(orca.script.ScriptPluginCapabilityBase):
    def get_name(self):
        return "observer"

    def on_load(self):
        try:
            orca.host.plater()
            plater_ok = True
        except Exception as exc:
            plater_ok = "%s: %s" % (type(exc).__name__, exc)
        base = {"ui_thread": threading.current_thread().name, "plater_at_load": plater_ok}
        print("{} load thread={} plater={}".format(LOG_PREFIX, base["ui_thread"], plater_ok))
        _flush(base)

    def on_lifecycle_event(self, event, ctx):
        _record(event)
        _flush({"ui_thread": "see-load", "plater_at_load": "see-load"})


@orca.plugin
class LifecycleObserverPlugin(orca.base):
    def register_capabilities(self):
        orca.register_capability(ObserverCapability)
