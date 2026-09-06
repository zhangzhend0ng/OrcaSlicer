"""MCP stdio server wiring: schema -> handler dispatch (official SDK).

The server speaks MCP over stdio via the official `mcp` SDK; every tool's
schema comes from tools_schema.json (single source of truth) and is served
unchanged, so list_tools can never drift from the dispatch table.
"""

from __future__ import annotations

import functools
import json
import logging
import traceback
from pathlib import Path
from typing import Any, Callable

import anyio
from mcp.server.lowlevel import Server
import mcp.types as t

from .errors import BridgeError

logger = logging.getLogger("snapmaker_orca_mcp")

Handler = Callable[[dict], Any]


def load_schema(path: Path | None = None) -> dict:
    schema_path = path or Path(__file__).parent / "tools_schema.json"
    with schema_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def schema_to_mcp_tools(schema: dict, backends: list[str]) -> list[t.Tool]:
    out: list[t.Tool] = []
    for entry in schema.get("tools", []):
        if backends and not (set(entry.get("backends", [])) & set(backends)):
            continue
        out.append(
            t.Tool(
                name=entry["name"],
                description=entry.get("description", ""),
                inputSchema=entry.get("inputSchema", {"type": "object"}),
            )
        )
    return out


class ToolRegistry:
    """Maps tool names from the schema to python handlers."""

    def __init__(self, schema: dict, handlers: dict[str, Handler], backends: list[str]) -> None:
        self.schema = schema
        self.handlers = handlers
        self.backends = backends
        self.served = schema_to_mcp_tools(schema, backends)
        names = {tool.name for tool in self.served}
        unknown = set(handlers) - names
        if unknown:
            raise BridgeError(
                f"handlers without schema entries: {sorted(unknown)}",
                code="schema_mismatch",
            )

    async def list_tools(
        self, ctx: Any, params: Any
    ) -> t.ListToolsResult:
        return t.ListToolsResult(tools=self.served)

    async def call_tool(self, ctx: Any, params: Any) -> t.CallToolResult:
        name = params.name
        arguments = dict(params.arguments or {})
        entry = next(
            (e for e in self.schema["tools"] if e["name"] == name), None
        )
        if entry is None or not (set(entry.get("backends", [])) & set(self.backends)):
            return _error_result(f"unknown tool: {name}")
        handler = self.handlers.get(name)
        if handler is None:
            return _error_result(
                f"tool '{name}' is declared but not available in backend(s) "
                f"{self.backends}"
            )
        try:
            # Handlers do blocking work (slicing subprocess, mesh IO); run
            # them on a worker thread so the event loop keeps serving pings
            # and progress for the duration of long slices.
            payload = await anyio.to_thread.run_sync(
                functools.partial(handler, arguments)
            )
        except BridgeError as exc:
            return _error_result(f"[{exc.code}] {exc}")
        except Exception as exc:  # noqa: BLE001 - surfaced to the client
            logger.error("tool %s failed: %s\n%s", name, exc, traceback.format_exc())
            return _error_result(f"internal error in tool {name}: {exc}")
        return t.CallToolResult(
            content=[t.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
            structuredContent=payload if isinstance(payload, dict) else None,
        )


def _error_result(message: str) -> t.CallToolResult:
    return t.CallToolResult(
        content=[t.TextContent(type="text", text=message)],
        isError=True,
    )


def build_server(registry: ToolRegistry, name: str = "snapmaker-orca-mcp") -> Server:
    server = Server(
        name,
        on_list_tools=registry.list_tools,
        on_call_tool=registry.call_tool,
    )
    return server


def default_handlers(config, backends: list[str]) -> dict[str, Handler]:
    """Construct the M0 handler set (CLI + knowledge + catalog)."""
    from .cli_backend import CliBackend
    from .knowledge import mesh_tools
    from .params_catalog import ParamsCatalog

    catalog: ParamsCatalog | None = None
    try:
        catalog = ParamsCatalog()
    except BridgeError as exc:
        if "list_params" in _required_tool_names():
            logger.warning("params catalog unavailable: %s", exc)

    cli = CliBackend(config, catalog=catalog)

    def _require(args: dict, key: str) -> Any:
        value = args.get(key)
        if value in (None, ""):
            raise BridgeError(f"missing required argument: {key}", code="bad_request")
        return value

    handlers: dict[str, Handler] = {}

    if "cli" in backends or True:  # knowledge tools are backend-independent
        handlers["analyze_mesh"] = lambda a: mesh_tools.analyze_mesh(_require(a, "path"))
        handlers["check_printability"] = lambda a: mesh_tools.check_printability(
            _require(a, "path"),
            build_volume_mm=a.get("build_volume_mm"),
            layer_height_mm=float(a.get("layer_height_mm", 0.2)),
            nozzle_diameter_mm=float(a.get("nozzle_diameter_mm", 0.4)),
            overhang_angle_deg=float(a.get("overhang_angle_deg", 50.0)),
        )
        handlers["suggest_orientation"] = lambda a: mesh_tools.suggest_orientation(
            _require(a, "path"),
            overhang_angle_deg=float(a.get("overhang_angle_deg", 50.0)),
            max_suggestions=int(a.get("max_suggestions", 5)),
        )
        handlers["estimate_cost"] = lambda a: mesh_tools.estimate_cost(
            _require(a, "path"),
            infill_density_pct=float(a.get("infill_density_pct", 20.0)),
            wall_count=int(a.get("wall_count", 2)),
            nozzle_diameter_mm=float(a.get("nozzle_diameter_mm", 0.4)),
            layer_height_mm=float(a.get("layer_height_mm", 0.2)),
            filament_density_g_cm3=float(a.get("filament_density_g_cm3", 1.24)),
            filament_price_per_kg=a.get("filament_price_per_kg"),
            electricity_price_per_kwh=a.get("electricity_price_per_kwh"),
            machine_power_w=float(a.get("machine_power_w", 100.0)),
            effective_flow_mm3_s=float(a.get("effective_flow_mm3_s", 7.5)),
        )
        handlers["export_3mf"] = lambda a: cli.export_3mf(
            _require(a, "model_path"), _require(a, "output_path")
        )

    if catalog is not None:
        handlers["list_params"] = lambda a: catalog.list_params(
            scope=a.get("scope"),
            search=a.get("search"),
            limit=int(a.get("limit", 60)),
            offset=int(a.get("offset", 0)),
        )

    if "cli" in backends:
        handlers["set_and_slice"] = lambda a: cli.set_and_slice(
            model_path=_require(a, "model_path"),
            plate=int(a.get("plate", 1)),
            overrides=a.get("overrides"),
            printer_preset=a.get("printer_preset"),
            process_preset=a.get("process_preset"),
            filament_presets=a.get("filament_presets"),
            output_dir=a.get("output_dir"),
            timeout_s=(float(a["timeout_s"]) if a.get("timeout_s") else None),
            allow_newer_file=bool(a.get("allow_newer_file", True)),
        )

    return handlers


def _required_tool_names() -> list[str]:
    return ["list_params"]
