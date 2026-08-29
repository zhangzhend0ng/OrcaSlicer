#!/usr/bin/env python3
# mcp_server.py — MCP stdio server exposing the vision_gui driver as AI tools.
#
# The "AI client" half of the unified human/AI black-box entry (see README,
# "人机统一入口"): the CustomTkinter UI and an MCP client (ZCode et al.) are
# two equal clients over the same harness layer. This server adds what ad-hoc
# shell driving lacks — the README pitfalls encoded as SERVER-SIDE invariants
# rather than prompt-level hopes:
#
#   - app_close only goes through AppSession.close() (graceful WM_CLOSE);
#     there is deliberately NO kill tool (Sentry crashpad pitfall #11)
#   - click() refuses coordinates outside the app window (a stray synthetic
#     click lands in whatever the USER is doing — blast-radius guard);
#     there is deliberately NO raw SendInput tool (SendInput stays internal
#     to the case scripts' menu path)
#   - app_launch always uses an isolated seeded datadir and boots with the
#     stealth watchdog (no pop-to-top over the user's desktop)
#   - a session lock file allows exactly one driver (UI or AI) at a time
#
# Protocol: MCP stdio — newline-delimited JSON-RPC 2.0 on stdin/stdout.
# Zero dependencies beyond the sandbox venv (no `mcp` package): the four
# methods that matter are initialize / notifications/initialized /
# tools/list / tools/call (+ ping). STDOUT DISCIPLINE: harness modules
# print() diagnostics, so sys.stdout is permanently redirected to stderr at
# startup and protocol frames go through the saved original stdout only.

import ast
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PROTO_OUT = sys.__stdout__   # the ONLY writer to the protocol channel
sys.stdout = sys.stderr      # harness print()s become client-visible logs

from harness import launcher, profile, session_lock, winutil  # noqa: E402
from harness.ocr_util import ocr_hwnd  # noqa: E402

SERVER_NAME = "vision-gui"
SERVER_VERSION = "0.2.0"
HERE_ART = HERE / "artifacts" / "mcp"
DRAFTS = HERE / "drafts"
RESOURCE_IMAGES = HERE / "resource" / "image"
CASE_TIMEOUT_MAX_S = 3600

SESSION = {"app": None, "last_target": None}   # app: AppSession | None


# --- tool implementations ----------------------------------------------------

def _app() -> "launcher.AppSession":
    if SESSION["app"] is None:
        raise RuntimeError("no app session — call app_launch first")
    return SESSION["app"]


def _png_bgr(bgr) -> tuple[str, bytes]:
    import cv2
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise RuntimeError("png encode failed")
    return "image/png", buf.tobytes()


def tool_app_launch(exe: str | None = None, model: str | None = None,
                    fresh: bool = True) -> dict:
    if SESSION["app"] is not None and SESSION["app"].alive():
        raise RuntimeError(f"app already running (pid {SESSION['app'].pid}) — call app_close first")
    ok, why = session_lock.acquire()
    if not ok:
        raise RuntimeError(f"cannot acquire session lock: {why}")
    datadir = HERE_ART / "profile"
    profile.seed_profile(datadir, fresh=fresh)
    try:
        session = launcher.launch(exe=exe, datadir=datadir, model=model)
    except BaseException:
        session_lock.release()
        raise
    SESSION["app"] = session
    SESSION["last_target"] = session.hwnd
    return {"pid": session.pid, "hwnd": hex(session.hwnd),
            "rect": session.rect(), "datadir": str(datadir),
            "note": "stealth watchdog active for 12s; model auto-load hands-off in progress"}


def tool_app_close() -> dict:
    app = _app()
    app.close()  # graceful WM_CLOSE -> wait -> (harness) last-resort kill
    SESSION["app"] = None
    SESSION["last_target"] = None
    session_lock.release()
    return {"closed": True, "exited": not app.alive()}


def tool_app_status() -> dict:
    app = SESSION["app"]
    if app is None:
        return {"running": False, "lock": str(session_lock.LOCK)}
    return {"running": app.alive(), "pid": app.pid, "hwnd": hex(app.hwnd),
            "rect": app.rect() if app.alive() else None}


def _inside_window(x: int, y: int) -> None:
    l, t, r, b = _app().rect()
    if not (l <= x < r and t <= y < b):
        raise ValueError(f"({x},{y}) is outside the app window ({l},{t})-({r},{b}) — "
                         f"refusing to click into the user's desktop")


def tool_window() -> dict:
    return {"hwnd": hex(_app().hwnd), "rect": _app().rect(),
            "last_target": hex(SESSION["last_target"] or 0)}


def tool_shot() -> dict:
    app = _app()
    cap = winutil.capture_window(app.hwnd)
    import cv2
    import numpy as np
    bgr = cv2.cvtColor(np.frombuffer(cap[2], np.uint8).reshape(cap[1], cap[0], 4),
                       cv2.COLOR_BGRA2BGR)
    out_dir = HERE_ART / "shots"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"shot_{int(time.time() * 1000)}.png"
    mime, png = _png_bgr(bgr)
    out.write_bytes(png)
    return {"image": {"mime": mime, "b64": base64.b64encode(png).decode()},
            "size": [cap[0], cap[1]], "saved": str(out)}


def tool_click(x: int, y: int) -> dict:
    app = _app()
    _inside_window(x, y)
    hit = winutil.msg_click_screen(x, y, root_hwnd=app.hwnd)
    SESSION["last_target"] = hit
    return {"clicked": True, "target_hwnd": hex(hit), "note": "message-level injection (no focus taken)"}


def _target() -> int:
    if not SESSION["last_target"]:
        raise RuntimeError("no target control — click(x, y) on a field first")
    return SESSION["last_target"]


def tool_type_text(text: str) -> dict:
    hwnd = _target()
    winutil.msg_text(hwnd, text)
    return {"typed": True, "target_hwnd": hex(hwnd)}


def tool_key(vk: int, modifiers: int = 0) -> dict:
    hwnd = _target()
    winutil.msg_key(hwnd, vk, modifiers)
    return {"sent": True, "vk": vk, "target_hwnd": hex(hwnd)}


def tool_ocr() -> dict:
    return {"text": ocr_hwnd(_app().hwnd)}


# --- M2: case runner + artifact access ----------------------------------------

_CASE_SKIP = {"ui_runner.py", "mcp_server.py", "mcp_smoke.py", "m3_common.py",
              "inspect_window.py"}


def _case_scripts() -> dict[str, Path]:
    """Runnable case scripts in the sandbox root (m<digit>* / diag_*)."""
    out = {}
    for p in sorted(HERE.glob("*.py")):
        n = p.name
        if n in _CASE_SKIP:
            continue
        if (len(n) > 1 and n[0] == "m" and n[1].isdigit()) or n.startswith("diag_"):
            out[n] = p
    return out


def tool_list_cases() -> dict:
    cases = []
    for name, path in _case_scripts().items():
        try:
            doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8"))) or ""
        except Exception:
            doc = ""
        cases.append({"script": name, "summary": doc.strip().splitlines()[0] if doc.strip() else ""})
    return {"cases": cases, "count": len(cases)}


def _sweep_orphan_apps() -> int:
    """Gracefully close apps left behind by a killed/failed case: any
    snapmaker-orca.exe whose command line references this sandbox dir. The
    USER's own app (different datadir) is never touched."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='snapmaker-orca.exe'\" | "
             "Where-Object { $_.CommandLine -match 'vision_gui' } | "
             "ForEach-Object { $_.ProcessId }"],
            capture_output=True, text=True, timeout=30).stdout.split()
    except Exception as e:
        print(f"[mcp] orphan sweep failed: {e}", file=sys.stderr)
        return 0
    closed = 0
    for s in out:
        try:
            pid = int(s)
        except ValueError:
            continue
        for hwnd, wpid in winutil.enum_windows():
            if wpid == pid:
                winutil.close_window(hwnd)
                closed += 1
    if closed:
        time.sleep(3.0)  # give WM_CLOSE a moment to finish the exit
    return closed


def tool_run_case(script: str, args: dict | None = None, timeout_s: int = 1800) -> dict:
    """Run a case script to completion, holding the session lock. A timeout
    kills ONLY the case driver (never the app directly) and then sweeps any
    orphaned app via graceful WM_CLOSE."""
    app = SESSION["app"]
    if app is not None and app.alive():
        raise RuntimeError("an interactive app session is active — call app_close first "
                           "(run_case drives its own app instances)")
    scripts = _case_scripts()
    if script not in scripts:
        raise ValueError(f"unknown case {script!r} — use list_cases")
    timeout_s = min(int(timeout_s), CASE_TIMEOUT_MAX_S)
    ok, why = session_lock.acquire()
    if not ok:
        raise RuntimeError(f"cannot take the session lock: {why}")
    log_dir = HERE_ART / "cases"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{Path(script).stem}_{int(time.time())}.log"
    cmd = [sys.executable, str(scripts[script])]
    for k, v in (args or {}).items():
        if v is True:
            cmd.append(f"--{k}")
        elif v is False or v is None:
            continue
        else:
            cmd.extend([f"--{k}", str(v)])
    env = {k: v for k, v in os.environ.items() if k.upper() != "ORCA_GUI_TEST_MODE"}
    print(f"[mcp] run_case {script} (timeout {timeout_s}s)", file=sys.stderr)
    started = time.monotonic()
    timed_out = False
    try:
        with open(log_path, "w", encoding="utf-8") as log_f:
            proc = subprocess.Popen(cmd, stdout=log_f, stderr=subprocess.STDOUT,
                                    text=True, cwd=str(HERE), env=env)
            try:
                rc = proc.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()          # the DRIVER, not the app (invariant)
                rc = proc.wait()
    finally:
        orphaned = _sweep_orphan_apps()
        session_lock.release()
    duration = time.monotonic() - started
    text = log_path.read_text(encoding="utf-8", errors="replace")
    green = None  # explicit GREEN/RED marker if the case prints one
    verdict: dict[str, str] = {}
    in_block = False
    for line in text.splitlines():
        if "=== verdict ===" in line:
            in_block = True
            continue
        if in_block:
            s = line.strip()
            if s.startswith("["):
                in_block = False
            elif ":" in s:
                k2, _, v2 = s.partition(":")
                verdict[k2.strip()] = v2.strip()
        if "GREEN" in line:
            green = True
        elif "RED" in line:
            green = False
    if green is None:
        # m0/m1/m2 convention: the exit code IS the verdict (no GREEN marker)
        green = (rc == 0) and not timed_out
    return {"script": script, "exit_code": rc, "green": green, "timed_out": timed_out,
            "duration_s": round(duration, 1), "verdict": verdict or None,
            "orphan_windows_closed": orphaned, "log_path": str(log_path),
            "log_tail": "\n".join(text.splitlines()[-30:])}


def _art_root() -> Path:
    root = (HERE / "artifacts").resolve()
    root.mkdir(exist_ok=True)
    return root


def tool_get_artifacts(subdir: str = "", limit: int = 25) -> dict:
    root = _art_root()
    base = (root / subdir).resolve() if subdir else root
    if base != root and root not in base.parents:
        raise ValueError("subdir escapes artifacts/")
    if not base.exists():
        return {"files": [], "root": str(root)}
    files = sorted((p for p in base.rglob("*") if p.is_file()),
                   key=lambda p: p.stat().st_mtime, reverse=True)[:max(1, min(int(limit), 100))]
    return {"root": str(root),
            "files": [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size}
                      for p in files]}


_IMAGE_EXT = {".png", ".bmp", ".jpg", ".jpeg"}


def tool_get_artifact(path: str) -> dict:
    root = _art_root()
    given = Path(path)
    target = (given if given.is_absolute() else root / given).resolve()
    if target != root and root not in target.parents:
        raise ValueError("path escapes artifacts/")
    if not target.exists():
        raise FileNotFoundError(path)
    if target.suffix.lower() in _IMAGE_EXT:
        data = target.read_bytes()
        mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(
            target.suffix.lower())
        if mime is None:  # bmp: normalize to png for transport
            import cv2
            import numpy as np
            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            mime, data = _png_bgr(img)
        return {"image": {"mime": mime, "b64": base64.b64encode(data).decode()},
                "path": str(target), "bytes": len(data)}
    text = target.read_text(encoding="utf-8", errors="replace")
    return {"path": str(target), "truncated": len(text) > 60000,
            "text": text[:60000]}


# --- M3: AI drafts new cases, human reviews ------------------------------------

_SCAFFOLD = '''#!/usr/bin/env python3
# {name}.py — DRAFT (AI-generated, NOT reviewed — keep out of the suite until promoted)
#
# Goal: {goal}
#
# Human review checklist (README "M3 流程") — promote only after every box ticks:
#   [ ] ran once against the dev build:  python drafts/{name}.py --fresh
#   [ ] verdict GREEN and the artifacts (screenshots / case log) look right
#   [ ] black-box only: no app internals; waits are event-driven (wait_for), not sleeps
#   [ ] templates it uses exist in resource/image/ (drop the draft_ prefix on promotion)
#   [ ] BLACKBOX_CASES.md entry written
# Promote:  git mv drafts/{name}.py {name}.py

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent   # drafts/ -> sandbox root
sys.path.insert(0, str(HERE))

from m3_common import add_common_args, boot_session, verdict  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    args = ap.parse_args()

    results = {{}}
    session = boot_session(args)
    try:
        # TODO: implement "{goal}" — drive via winutil message injection,
        # observe via captures / OCR, assert into results[].
        results["placeholder"] = "FAIL (draft — steps not implemented yet)"
    finally:
        session.close()
    return verdict(results)


if __name__ == "__main__":
    raise SystemExit(main())
'''


def tool_case_scaffold(name: str, goal: str) -> dict:
    import re
    if not re.fullmatch(r"m\d[a-z][a-z0-9]*(?:_[a-z0-9]+)*", name):
        raise ValueError("case name must look like m3t_mixing_foo (lowercase a-z0-9)")
    DRAFTS.mkdir(exist_ok=True)
    out = DRAFTS / f"{name}.py"
    if out.exists():
        raise FileExistsError(f"{out} already exists")
    out.write_text(_SCAFFOLD.format(name=name, goal=goal.strip()), encoding="utf-8")
    return {"draft": str(out),
            "next": ["human runs + reviews per the checklist in the file header",
                     f"promote with: git mv drafts/{name}.py {name}.py"]}


def tool_crop_template(shot_path: str, x: int, y: int, w: int, h: int, name: str) -> dict:
    """Crop a region out of an artifacts/ image into a draft template for
    vision matching. draft_ prefix marks it unreviewed."""
    import cv2
    import numpy as np
    root = _art_root()
    given = Path(shot_path)
    src = (given if given.is_absolute() else root / given).resolve()
    if src != root and root not in src.parents:
        raise ValueError("shot_path must be inside artifacts/")
    if not src.exists():
        raise FileNotFoundError(shot_path)
    img = cv2.imdecode(np.fromfile(str(src), dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"cannot decode {src} as an image")
    h_img, w_img = img.shape[:2]
    if not (0 <= x and 0 <= y and w > 0 and h > 0 and x + w <= w_img and y + h <= h_img):
        raise ValueError(f"crop ({x},{y},{w},{h}) outside image {w_img}x{h_img}")
    RESOURCE_IMAGES.mkdir(parents=True, exist_ok=True)
    out = RESOURCE_IMAGES / f"draft_{name}.png"
    cv2.imwrite(str(out), img[y:y + h, x:x + w])
    return {"template": str(out), "size": [w, h],
            "note": "draft_ prefix marks it unreviewed; drop the prefix when promoting the case"}


# --- MCP plumbing -------------------------------------------------------------

TOOLS = [
    ("app_launch", "Seed an isolated datadir and launch the app under test (stealth boot).",
     {"type": "object", "properties": {
         "exe": {"type": "string", "description": "app exe path (default: dev build)"},
         "model": {"type": "string", "description": "optional 3mf/stl to auto-load"},
         "fresh": {"type": "boolean", "description": "re-seed the datadir (default true)"}},
     }),
    ("app_close", "Gracefully close the app (WM_CLOSE; never a hard kill).",
     {"type": "object", "properties": {}}),
    ("app_status", "Is the app running? pid/hwnd/rect.",
     {"type": "object", "properties": {}}),
    ("window", "App window rect + current injection target.",
     {"type": "object", "properties": {}}),
    ("shot", "Capture the app window (PNG image + saved path). GL canvas included.",
     {"type": "object", "properties": {}}),
    ("click", "Left-click at app-window coordinates via message injection (no focus, remote-control proof).",
     {"type": "object", "properties": {
         "x": {"type": "integer"}, "y": {"type": "integer"}},
      "required": ["x", "y"]}),
    ("type_text", "Type text into the last-clicked control (WM_CHAR per char).",
     {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}),
    ("key", "Send a virtual key (e.g. 13=Enter) with optional modifier vk to the last-clicked control.",
     {"type": "object", "properties": {
         "vk": {"type": "integer"}, "modifiers": {"type": "integer"}},
      "required": ["vk"]}),
    ("ocr", "OCR the whole app window (Tesseract).",
     {"type": "object", "properties": {}}),
    ("list_cases", "List runnable black-box case scripts with their summaries.",
     {"type": "object", "properties": {}}),
    ("run_case", "Run a case script end-to-end (holds the session lock; drives its "
                 "own app instances). Returns exit code, GREEN/RED verdict and log tail.",
     {"type": "object", "properties": {
         "script": {"type": "string", "description": "case file name, e.g. m3a_empty_slice.py"},
         "args": {"type": "object", "description": "CLI args mapping: {\"--flag\": true, \"--opt\": value}"},
         "timeout_s": {"type": "integer", "description": "default 1800, max 3600"}},
      "required": ["script"]}),
    ("get_artifacts", "List recent files under artifacts/ (newest first).",
     {"type": "object", "properties": {
         "subdir": {"type": "string"}, "limit": {"type": "integer"}}}),
    ("get_artifact", "Read one artifact: images return MCP image content, text files text.",
     {"type": "object", "properties": {
         "path": {"type": "string", "description": "path relative to artifacts/"}},
      "required": ["path"]}),
    ("case_scaffold", "M3: generate a reviewed-pending case draft in drafts/ from the "
                      "standard skeleton (human review + promotion required).",
     {"type": "object", "properties": {
         "name": {"type": "string", "description": "e.g. m3t_mixing_foo"},
         "goal": {"type": "string", "description": "what the case must verify"}},
      "required": ["name", "goal"]}),
    ("crop_template", "M3: crop a region of an artifacts/ image into a draft vision "
                      "template (resource/image/draft_<name>.png).",
     {"type": "object", "properties": {
         "shot_path": {"type": "string"}, "x": {"type": "integer"}, "y": {"type": "integer"},
         "w": {"type": "integer"}, "h": {"type": "integer"}, "name": {"type": "string"}},
      "required": ["shot_path", "x", "y", "w", "h", "name"]}),
]

HANDLERS = {
    "app_launch": tool_app_launch,
    "app_close": tool_app_close,
    "app_status": tool_app_status,
    "window": tool_window,
    "shot": tool_shot,
    "click": tool_click,
    "type_text": tool_type_text,
    "key": tool_key,
    "ocr": tool_ocr,
    "list_cases": tool_list_cases,
    "run_case": tool_run_case,
    "get_artifacts": tool_get_artifacts,
    "get_artifact": tool_get_artifact,
    "case_scaffold": tool_case_scaffold,
    "crop_template": tool_crop_template,
}


def _reply(msg: dict) -> None:
    PROTO_OUT.write(json.dumps(msg, ensure_ascii=False) + "\n")
    PROTO_OUT.flush()


def _result(id_, payload: dict) -> None:
    _reply({"jsonrpc": "2.0", "id": id_, "result": payload})


def _error(id_, code: int, message: str) -> None:
    _reply({"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}})


def _tool_result(payload: dict) -> dict:
    content = []
    image = payload.pop("image", None)
    if image:
        content.append({"type": "image", "data": image["b64"], "mimeType": image["mime"]})
    content.append({"type": "text", "text": json.dumps(payload, ensure_ascii=False)})
    return {"content": content, "isError": False}


def dispatch(req: dict) -> None:
    method = req.get("method", "")
    id_ = req.get("id")
    if method == "initialize":
        _result(id_, {
            "protocolVersion": req.get("params", {}).get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })
    elif method == "notifications/initialized" or method.startswith("notifications/"):
        pass  # notifications get no response
    elif method == "ping":
        _result(id_, {})
    elif method == "tools/list":
        _result(id_, {"tools": [
            {"name": n, "description": d, "inputSchema": s} for (n, d, s) in TOOLS]})
    elif method == "tools/call":
        params = req.get("params", {})
        name = params.get("name", "")
        args = params.get("arguments", {}) or {}
        handler = HANDLERS.get(name)
        if handler is None:
            _result(id_, {"content": [{"type": "text", "text": f"unknown tool {name}"}],
                          "isError": True})
            return
        try:
            _result(id_, _tool_result(handler(**args)))
        except Exception as e:
            _result(id_, {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                          "isError": True})
    elif id_ is not None:
        _error(id_, -32601, f"method not found: {method}")


def main() -> int:
    print(f"[{SERVER_NAME}] stdio MCP server up; harness prints are routed to stderr",
          file=sys.stderr)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError as e:
            _error(None, -32700, f"parse error: {e}")
            continue
        try:
            dispatch(req)
        except Exception as e:  # never die on one bad request
            print(f"[{SERVER_NAME}] dispatch error: {e}", file=sys.stderr)
            if req.get("id") is not None:
                _error(req["id"], -32603, f"internal error: {e}")
    if SESSION["app"] is not None:  # stdin closed: do not leak the app
        try:
            SESSION["app"].close()
        finally:
            session_lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
