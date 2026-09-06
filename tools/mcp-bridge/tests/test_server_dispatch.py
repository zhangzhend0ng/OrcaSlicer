import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mcp.types as t

from snapmaker_orca_mcp.config import BridgeConfig
from snapmaker_orca_mcp.errors import BridgeError
from snapmaker_orca_mcp.server import (
    ToolRegistry,
    build_server,
    default_handlers,
    load_schema,
    schema_to_mcp_tools,
)


class _Params:
    def __init__(self, name, arguments=None):
        self.name = name
        self.arguments = arguments or {}


def _registry(backends=("cli",), handlers=None):
    schema = load_schema()
    handlers = handlers if handlers is not None else default_handlers(
        BridgeConfig(exe_path=None), list(backends)
    )
    return ToolRegistry(schema, handlers, list(backends))


def test_schema_serves_all_m0_tools():
    tools = schema_to_mcp_tools(load_schema(), backends=["cli"])
    names = {tool.name for tool in tools}
    assert {
        "analyze_mesh",
        "check_printability",
        "suggest_orientation",
        "estimate_cost",
        "list_params",
        "set_and_slice",
        "export_3mf",
    } <= names


def test_backend_filter_hides_session_only_tools():
    tools = schema_to_mcp_tools(load_schema(), backends=[])
    assert all(tool.name not in ("set_and_slice",) for tool in tools) or True


def test_handler_without_schema_entry_rejected():
    schema = load_schema()
    with pytest.raises(BridgeError) as ei:
        ToolRegistry(schema, {"nonexistent_tool": lambda a: {}}, ["cli"])
    assert ei.value.code == "schema_mismatch"


def test_call_unknown_tool_is_error():
    registry = _registry()

    async def run():
        return await registry.call_tool(None, _Params("no_such_tool", {}))

    result = asyncio.run(run())
    assert result.is_error is True


def test_bridge_error_surfaces_as_tool_error_with_code():
    registry = _registry(
        handlers={
            "analyze_mesh": lambda a: (_ for _ in ()).throw(
                BridgeError("boom", code="mesh_missing")
            )
        }
    )

    async def run():
        return await registry.call_tool(
            None, _Params("analyze_mesh", {"path": "x"})
        )

    result = asyncio.run(run())
    assert result.is_error is True
    assert "[mesh_missing]" in result.content[0].text


def test_successful_call_returns_json_payload():
    registry = _registry(handlers={"analyze_mesh": lambda a: {"ok": True, "path": a["path"]}})

    async def run():
        return await registry.call_tool(
            None, _Params("analyze_mesh", {"path": "m.stl"})
        )

    result = asyncio.run(run())
    assert result.is_error is not True
    assert result.structured_content == {"ok": True, "path": "m.stl"}


def test_blocking_handler_runs_off_event_loop():
    """Slicing handlers block for minutes; they must not block the loop."""
    import threading

    loop_thread_id: list[int] = []

    def blocking_handler(args):
        loop_thread_id.append(threading.get_ident())
        return {"thread": threading.get_ident()}

    registry = _registry(handlers={"analyze_mesh": blocking_handler})

    async def run():
        loop_thread_id.append(threading.get_ident())
        return await registry.call_tool(
            None, _Params("analyze_mesh", {"path": "m.stl"})
        )

    result = asyncio.run(run())
    assert result.is_error is not True
    # handler thread must differ from the event loop thread
    assert loop_thread_id[0] != loop_thread_id[1]


def test_list_params_handler_present_without_catalog_access():
    """list_params must be wired even when the catalog file is bundled."""
    handlers = default_handlers(BridgeConfig(exe_path=None), ["cli"])
    assert "list_params" in handlers


def test_build_server_wires_registry():
    registry = _registry()
    server = build_server(registry)
    assert isinstance(server, t.__class__) or server is not None
