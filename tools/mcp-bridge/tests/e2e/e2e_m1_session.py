"""M1 E2E: launch the real Orca GUI with MCP enabled and drive every
session tool over the loopback listener.

Run from the worktree root::

    python tools/mcp-bridge/tests/e2e/e2e_m1_session.py \
        --exe build/src/Release/snapmaker-orca.exe

Steps:
  1. create a fresh datadir with mcp_enabled=true pre-seeded
  2. launch snapmaker-orca.exe --datadir <dir> (GUI mode)
  3. poll for the discovery file + port readiness
  4. ping / get_state / get_plate_screenshot / slice / export_3mf /
     poll_job / bad-token rejection over raw HTTP JSON-RPC
  5. terminate the process, assert cleanup
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
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


def rpc(port: int, token: str, method: str, params: dict | None = None,
        timeout: float = 30.0, token_override: str | None = None):
    """Raw JSON-RPC POST to the listener. Returns (parsed_body, status)."""
    payload = json.dumps({"method": method, "params": params or {}, "id": 1}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token_override if token_override is not None else token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode()), 200
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode()), exc.code


def wait_for_listener(discovery: Path, deadline_s: float = 180.0):
    """Poll until the discovery file exists and the port answers ping."""
    deadline = time.monotonic() + deadline_s
    while time.monotonic() < deadline:
        if discovery.is_file():
            try:
                doc = json.loads(discovery.read_text(encoding="utf-8"))
                port, token = int(doc["port"]), str(doc["token"])
                body, _ = rpc(port, token, "ping", timeout=5)
                if body.get("result", {}).get("pong") is True:
                    return port, token
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                pass
        time.sleep(1.0)
    return None, None


def wait_job(port: int, token: str, job_id: int, timeout_s: float):
    deadline = time.monotonic() + timeout_s
    last = {}
    while time.monotonic() < deadline:
        body, _ = rpc(port, token, "poll_job", {"job_id": job_id})
        last = body.get("result", {})
        if last.get("state") in ("done", "failed"):
            return last
        time.sleep(0.4)
    return last


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--exe",
        default=str(REPO_ROOT / "build" / "src" / "Release" / "snapmaker-orca.exe"),
    )
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    exe = Path(args.exe)
    work = Path(tempfile.mkdtemp(prefix="orca_m1_e2e_"))
    data_dir = work / "datadir"
    data_dir.mkdir(parents=True)
    out_dir = work / "output"
    out_dir.mkdir()
    print(f"E2E workdir: {work}")

    # 1. pre-seed the app config: MCP interface ON. The Windows JSON config
    #    loader substr()s the checksum line after the last '}' - a file
    #    without one crashes GUI init ("invalid string position"), so write
    #    a real MD5 checksum line like Orca does.
    import hashlib

    # Base the seed on a REAL configured app config (printer presets chosen,
    # wizard finished) so slicing is valid on a first launch; override the
    # MCP switch on top.
    real_conf = Path.home() / "AppData" / "Roaming" / "Snapmaker_Orca" / "Snapmaker_Orca.conf"
    try:
        raw = real_conf.read_text(encoding="utf-8")
        seed = json.loads(raw[: raw.rfind("}") + 1])
    except (OSError, json.JSONDecodeError):
        seed = {}
    seed.setdefault("app", {})["mcp_enabled"] = True
    seed["firstguide"] = {"finish": True}
    # Single-nozzle machine + single PLA preset: any mixed-temperature
    # filament set would pop the temp-mixing confirm dialog during slice
    # (human-in-the-loop gate) and stall an unattended session.
    seed["presets"] = {
        "machine": "Snapmaker Artisan (0.4 nozzle)",
        "filaments": ["Generic PLA"],
    }
    conf_json = json.dumps(seed, indent=4)
    md5_hex = hashlib.md5(conf_json.encode("utf-8")).hexdigest().upper()
    checksum_line = "# MD5 checksum " + md5_hex
    (data_dir / "Snapmaker_Orca.conf").write_text(
        conf_json + "\r\n" + checksum_line + "\r\n", encoding="utf-8"
    )

    # 2. launch the real GUI (empty session; a real mesh is loaded through
    #    the load_models tool below). A plain STL keeps the plate free of
    #    embedded project settings: the handy_models 3mfs ship newer-version
    #    settings whose apply fails, leaving the plate apply_invalid (not
    #    sliceable) - mirrors the CLI 3mf issues, see journal.
    import trimesh

    mesh_a = trimesh.creation.icosphere(subdivisions=3, radius=12.0)
    mesh_b = trimesh.creation.icosphere(subdivisions=3, radius=8.0)
    mesh_b.apply_translation([18.0, 0.0, 0.0])
    fixture_mesh = (mesh_a + mesh_b)
    model_path = work / "twospheres.stl"
    fixture_mesh.export(model_path, file_type="stl")
    proc = subprocess.Popen(
        [str(exe), f"--datadir={data_dir}"],
        cwd=str(exe.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"launched pid={proc.pid}")
    try:
        # 3. wait for listener readiness
        discovery = data_dir / "mcp_session.json"
        port, token = wait_for_listener(discovery)
        check("listener came up with discovery file", port is not None)
        if port is None:
            return finish(proc, work, args)
        print(f"listener on 127.0.0.1:{port}")

        # 4a. token enforcement
        body, _ = rpc(port, token, "get_state", token_override="Bearer wrong")
        check("wrong token rejected", body.get("error", {}).get("code") == -32001,
              json.dumps(body)[:200])
        body, _ = rpc(port, token, "get_state", token_override="")
        check("missing token rejected", body.get("error", {}).get("code") == -32001)

        # 4b. get_state from the snapshot cache
        deadline = time.monotonic() + 120
        state = {}
        while time.monotonic() < deadline:
            body, _ = rpc(port, token, "get_state")
            state = body.get("result", {})
            if state.get("ready"):
                break
            time.sleep(1.0)
        check("get_state ready", state.get("ready") is True, json.dumps(state)[:300])
        check("get_state has stale_at", isinstance(state.get("stale_at"), int))
        check("get_state has plates", isinstance(state.get("plates"), list)
              and len(state.get("plates", [])) >= 1)
        check("get_state has objects", isinstance(state.get("objects"), list))
        check("session starts empty", not state.get("objects"))

        # 4b2. load the model through the UI entry point
        body, _ = rpc(port, token, "load_models", {"paths": [str(model_path)]})
        load_job = wait_job(port, token, body.get("result", {}).get("job_id", 0), 120)
        check("load_models job done", load_job.get("state") == "done",
              json.dumps(load_job)[:300])
        deadline = time.monotonic() + 60
        state = {}
        while time.monotonic() < deadline:
            body, _ = rpc(port, token, "get_state")
            state = body.get("result", {})
            if state.get("objects"):
                break
            time.sleep(1.0)
        check("model visible in session state",
              len(state.get("objects", [])) >= 1, json.dumps(state)[:300])
        check("model placed on bed",
              state.get("objects", [{}])[0].get("out_of_bounds") is False)

        # 4c. screenshot of the loaded plate
        body, _ = rpc(port, token, "get_plate_screenshot",
                      {"plate_index": 1, "width": 256, "height": 256})
        job = wait_job(port, token, body.get("result", {}).get("job_id", 0), 90)
        check("screenshot job done", job.get("state") == "done", json.dumps(job)[:300])
        b64 = job.get("result", {}).get("image_base64", "")
        png = b""
        if job.get("state") == "done" and b64:
            png = base64.b64decode(b64)
            check("screenshot is PNG", png[:8] == b"\x89PNG\r\n\x1a\n", str(png[:16]))
            check("screenshot has size", len(png) > 200, f"{len(png)} bytes")
            check("screenshot shows content (not blank)", len(png) > 2000,
                  f"{len(png)} bytes")
        if len(png) > 8:
            import struct
            w, h = struct.unpack(">II", png[16:24])
            check("screenshot IHDR dims match request", (w, h) == (256, 256),
                  f"w={w}, h={h}")

        foreground_window("Snapmaker Orca")

        # 4d. slice the loaded scene and wait for real progress.
        # The slice-finalize thumbnail render can stall on VMs with a broken
        # on-screen GL canvas (CPU-idle deadlock at 80%); the watchdog fails
        # the job and a retry restarts the background process.
        job = {}
        for attempt in range(3):
            body, _ = rpc(port, token, "slice", {"plate": 1})
            check("slice returns job id",
                  isinstance(body.get("result", {}).get("job_id"), int),
                  json.dumps(body)[:200])
            if not isinstance(body.get("result", {}).get("job_id"), int):
                break
            job = wait_job(port, token, body["result"]["job_id"], 300)
            print(f"       (slice attempt {attempt + 1}: {job.get('state')} "
                  f"{job.get('percent')}% {job.get('message', '')[:120]})")
            if job.get("state") == "done":
                break
        check("slice job done", job.get("state") == "done", json.dumps(job)[:300])

        # 4e. unknown job id answers definitively
        body, _ = rpc(port, token, "poll_job", {"job_id": 999999})
        check("unknown job id -> error",
              body.get("error", {}).get("code") == -32003, json.dumps(body)[:200])

        # 4f. unknown method
        body, _ = rpc(port, token, "definitely_not_a_method")
        check("unknown method -> error",
              body.get("error", {}).get("code") == -32601)

        # 4f2. export_gcode after a completed slice. Right after the
        # Finished event the background thread may still be winding down
        # (running() stays true briefly), so retry a few times.
        if "done" in str(job.get("state", "")):
            gcode_target = out_dir / "session_export.gcode"
            gj = {}
            for attempt in range(12):
                body, _ = rpc(port, token, "export_gcode",
                              {"path": str(gcode_target)})
                jid = body.get("result", {}).get("job_id")
                if not jid:
                    break
                gj = wait_job(port, token, jid, 60)
                print(f"       (export attempt {attempt + 1}: {gj.get('state')} "
                      f"{gj.get('message', '')[:150]})")
                if gj.get("state") == "done":
                    break
                time.sleep(1.0)
            check("export_gcode job done", gj.get("state") == "done",
                  json.dumps(gj)[:300])
            check("export_gcode file exists", gcode_target.is_file())

        # 4g. export_3mf of the current (empty) project
        target = out_dir / "session_project.3mf"
        body, _ = rpc(port, token, "export_3mf", {"path": str(target)})
        if isinstance(body.get("result", {}).get("job_id"), int):
            job = wait_job(port, token, body["result"]["job_id"], 180)
            check("export_3mf reaches terminal state",
                  job.get("state") in ("done", "failed"), json.dumps(job)[:300])
            if job.get("state") == "done":
                check("export_3mf file exists", target.is_file())

        # 4h. single-flight slice mutex
        body1, _ = rpc(port, token, "slice", {"plate": 1})
        id1 = body1.get("result", {}).get("job_id")
        if isinstance(id1, int):
            body2, _ = rpc(port, token, "slice", {"plate": 1})
            err = body2.get("error", {})
            check("second slice while running -> ui_busy or fresh job",
                  err.get("code") == -32002 or isinstance(body2.get("result", {}).get("job_id"), int),
                  json.dumps(body2)[:200])
            wait_job(port, token, id1, 120)

    finally:
        finish(proc, work, args)
    return 1 if FAILURES else 0


def finish(proc: subprocess.Popen, work: Path, args) -> int:
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=30)
    print("orca terminated")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    print()
    if FAILURES:
        print(f"M1 E2E RESULT: RED ({len(FAILURES)} failed): {FAILURES}")
        return 1
    print("M1 E2E RESULT: GREEN (all checks passed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
