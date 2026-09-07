"""M1 E2E (bridge): MCP client -> bridge session backend -> Orca listener.

Launches the real Orca GUI (MCP enabled), then talks to it exclusively
through the bridge package over MCP stdio - the full three-hop chain an
AI client would use.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
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


def foreground_window(title_contains: str) -> None:
    """Bring the Orca window to the foreground.

    The wxGLCanvas only paints when the window is actually shown; a
    background window makes thumbnail rendering (part of slice finalize)
    stall on some VMs.
    """
    import ctypes
    user32 = ctypes.windll.user32
    top = user32.GetTopWindow(0)
    length = 512
    buffer = ctypes.create_unicode_buffer(length)
    while top:
        size = user32.GetWindowTextLengthW(top)
        if size > 0:
            user32.GetWindowTextW(top, buffer, max(length, size + 1))
            if title_contains.lower() in buffer.value.lower():
                user32.ShowWindow(top, 9)  # SW_RESTORE
                user32.SetForegroundWindow(top)
                return
        top = user32.GetWindow(top, 2)  # GW_HWNDNEXT


def payload_of(result):
    """Decode a tool result; raises with the message when isError."""
    if getattr(result, "is_error", False):
        raise RuntimeError(result.content[0].text)
    return json.loads(result.content[0].text)


async def run(exe: Path, work: Path) -> None:
    import trimesh
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # seed datadir (real conf base + MCP on)
    data_dir = work / "datadir"
    data_dir.mkdir(parents=True)
    raw = (Path.home() / "AppData" / "Roaming" / "Snapmaker_Orca"
           / "Snapmaker_Orca.conf")
    try:
        seed = json.loads(raw.read_text(encoding="utf-8")[: raw.read_text(encoding="utf-8").rfind("}") + 1])
    except (OSError, json.JSONDecodeError):
        seed = {}
    seed.setdefault("app", {})["mcp_enabled"] = True
    seed["firstguide"] = {"finish": True}
    seed["presets"] = {"machine": "Snapmaker Artisan (0.4 nozzle)",
                       "filaments": ["Generic PLA"]}
    conf = json.dumps(seed, indent=4)
    md5 = hashlib.md5(conf.encode("utf-8")).hexdigest().upper()
    (data_dir / "Snapmaker_Orca.conf").write_text(
        conf + "\r\n# MD5 checksum " + md5 + "\r\n", encoding="utf-8")

    mesh = trimesh.creation.icosphere(subdivisions=3, radius=12.0)
    mesh2 = trimesh.creation.icosphere(subdivisions=3, radius=8.0)
    mesh2.apply_translation([18.0, 0.0, 0.0])
    (mesh + mesh2).export(work / "twospheres.stl", file_type="stl")

    proc = subprocess.Popen(
        [str(exe), f"--datadir={data_dir}"],
        cwd=str(exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        discovery = data_dir / "mcp_session.json"
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from e2e_m1_session import wait_for_listener
        port, token = wait_for_listener(discovery)
        check("orca listener up", port is not None)

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "snapmaker_orca_mcp", "--backends", "session",
                  "--log-level", "ERROR"],
            env={
                **os.environ,
                "PYTHONPATH": str(BRIDGE),
                "SNAPMAKER_ORCA_MCP_DISCOVERY": str(discovery),
            },
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                check("bridge initialize ok",
                      init.server_info.name == "snapmaker-orca-mcp")

                listed = await session.list_tools()
                names = {t.name for t in listed.tools}
                check("session tools served",
                      {"get_state", "slice", "export_gcode", "poll_job",
                       "get_plate_screenshot"} <= names, str(sorted(names)))

                # get_state through the full chain
                deadline = time.monotonic() + 120
                payload = {}
                while time.monotonic() < deadline:
                    result = await session.call_tool("get_state", {})
                    payload = payload_of(result)
                    if payload.get("ready"):
                        break
                    await asyncio.sleep(1.0)
                check("get_state via bridge", payload.get("ready") is True,
                      str(payload)[:200])

                # load + slice through the full chain
                result = await session.call_tool(
                    "load_models",
                    {"paths": [str(work / "twospheres.stl")]},
                )
                payload_of(result)
                check("load_models accepted", True)

                deadline = time.monotonic() + 60
                loaded = False
                while time.monotonic() < deadline:
                    result = await session.call_tool("get_state", {})
                    payload = payload_of(result)
                    if payload.get("objects"):
                        loaded = True
                        break
                    await asyncio.sleep(1.0)
                check("objects visible via bridge", loaded)

                await asyncio.to_thread(foreground_window, "Snapmaker Orca")
                payload = {}
                for attempt in range(3):
                    try:
                        result = await session.call_tool(
                            "slice", {"plate": 1, "timeout_s": 300})
                        payload = payload_of(result)
                        break
                    except RuntimeError as exc:
                        # The slice-finalize thumbnail render can stall on
                        # VMs with a broken on-screen GL canvas (watchdog
                        # fails the job); retrying restarts the background
                        # process. A cancelled finalize can also reset the
                        # scene, so re-load the model before retrying.
                        print(f"       (slice attempt {attempt + 1}: {exc})")
                        await asyncio.sleep(2)
                        try:
                            result = await session.call_tool(
                                "load_models",
                                {"paths": [str(work / "twospheres.stl")]},
                            )
                            payload_of(result)
                        except RuntimeError:
                            pass
                check("slice via bridge done",
                      payload.get("outcome") == "sliced", str(payload)[:200])

                # export gcode through the chain
                out = work / "bridge_export.gcode"
                result = await session.call_tool(
                    "export_gcode", {"path": str(out), "timeout_s": 300})
                payload = payload_of(result)
                check("export_gcode via bridge done",
                      payload.get("bytes", 0) > 0, str(payload)[:200])
                check("gcode file exists via bridge", out.is_file())
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--exe",
        default=str(REPO_ROOT / "build" / "src" / "Release" / "snapmaker-orca.exe"),
    )
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="orca_m1_bridge_"))
    print(f"E2E workdir: {work}")
    asyncio.run(run(Path(args.exe), work))
    print()
    if FAILURES:
        print(f"BRIDGE E2E RESULT: RED ({FAILURES})")
        return 1
    print("BRIDGE E2E RESULT: GREEN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
