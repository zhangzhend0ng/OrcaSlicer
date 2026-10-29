# Generated from the live Snapmaker Orca embedded bindings.
from __future__ import annotations
import orca
import typing
import collections.abc
from typing import Any, Callable, ClassVar, Iterable, Iterator, Optional, Sequence, overload

class ScriptPluginCapabilityBase(orca.PythonPluginBase):
    def __init__(self: orca.script.ScriptPluginCapabilityBase) -> None: ...
    def execute(self: orca.script.ScriptPluginCapabilityBase) -> orca.ExecutionResult: ...
    def get_type(self: orca.script.ScriptPluginCapabilityBase) -> orca.PluginType: ...
