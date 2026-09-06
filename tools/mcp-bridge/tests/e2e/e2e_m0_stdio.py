"""M0 E2E (protocol): talk to the bridge over real MCP stdio using the
official SDK client - initialize, list tools, call tools, verify payloads.

Run from the worktree root::

    python tools/mcp-bridge/tests/e2e/e2e_m0_stdio.py \
        --exe build/src/Release/snapmaker-orca.exe
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[2]
REPO_ROOT = BRIDGE.parents[1]
sys.path.insert(0, str(BRIDGE))

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" :: {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


async def run(exe: Path) -> None:
    from mcp import ClientSession, StdioServerParameters, types as t
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m", "snapmaker_orca_mcp",
            "--exe", str(exe),
            "--log-level", "ERROR",
        ],
        cwd=str(BRIDGE.parent.parent),  # repo root (env for module path)
        env={
            **__import__("os").environ,
            "PYTHONPATH": str(BRIDGE.parent.parent / "tools" / "mcp-bridge"),
            "SNAPMAKER_ORCA_EXE": str(exe),
            "SNAPMAKER_ORCA_RESOURCES": str(REPO_ROOT / "resources"),
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            check(
                "initialize returns server name",
                init.server_info.name == "snapmaker-orca-mcp",
                str(init.server_info),
            )

            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            check(
                "list_tools has M0 surface",
                {"analyze_mesh", "list_params", "set_and_slice", "export_3mf"} <= names,
                str(sorted(names)),
            )

            # knowledge tool over real MCP transport
            work = Path(tempfile.mkdtemp(prefix="orca_m0_stdio_"))
            import trimesh

            box = trimesh.creation.box(extents=(10.0, 12.0, 14.0))
            mesh_path = work / "box.obj"
            box.export(mesh_path, file_type="obj")
            result = await session.call_tool(
                "analyze_mesh", {"path": str(mesh_path)}
            )
            check("call_tool analyze_mesh ok", result.is_error is not True,
                  result.content[0].text[:200] if result.content else "empty")
            payload = json.loads(result.content[0].text)
            check("analyze_mesh payload volume", payload["volume_mm3"] > 0)

            # structured error propagation
            result = await session.call_tool(
                "analyze_mesh", {"path": "Z:/missing.stl"}
            )
            check("missing file -> isError", result.is_error is True)
            check("error carries code", "[mesh_missing]" in result.content[0].text,
                  result.content[0].text)

            # list_params round trip
            result = await session.call_tool(
                "list_params", {"search": "nozzle", "limit": 5}
            )
            payload = json.loads(result.content[0].text)
            check("list_params matched>0", payload["matched"] > 0,
                  json.dumps(payload)[:200])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--exe",
        default=str(REPO_ROOT / "build" / "src" / "Release" / "snapmaker-orca.exe"),
    )
    args = ap.parse_args()
    import asyncio

    asyncio.run(run(Path(args.exe)))
    print()
    if FAILURES:
        print(f"STDIO E2E RESULT: RED ({FAILURES})")
        return 1
    print("STDIO E2E RESULT: GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
