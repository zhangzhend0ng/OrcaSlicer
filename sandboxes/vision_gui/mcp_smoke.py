#!/usr/bin/env python3
# mcp_smoke.py — end-to-end protocol smoke for mcp_server.py (zero deps).
#
# Spawns the server, speaks MCP stdio JSON-RPC, and walks the full loop:
# initialize -> tools/list -> app_launch -> status/window -> shot -> click ->
# ocr -> app_close. Asserts protocol shape, image payload, and that the app
# process is really gone afterwards. Any failure exits non-zero.

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = [str(HERE / ".venv" / "Scripts" / "python.exe"), str(HERE / "mcp_server.py")]

_expect_id = 0


def send(proc, method, params=None, notify=False):
    global _expect_id
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if not notify:
        _expect_id += 1
        msg["id"] = _expect_id
    proc.stdin.write(json.dumps(msg) + "\n")
    proc.stdin.flush()
    return None if notify else _expect_id


def recv(proc, want_id, timeout_s=120):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout unexpectedly")
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if msg.get("id") == want_id:
            return msg
        # skip server-initiated messages / notifications
    raise RuntimeError(f"timeout waiting for id {want_id}")


def call(proc, name, args=None, timeout_s=120):
    rid = send(proc, "tools/call", {"name": name, "arguments": args or {}})
    resp = recv(proc, rid, timeout_s)
    result = resp.get("result")
    assert result is not None, f"no result for {name}: {resp}"
    assert result.get("isError") is not True, f"{name} errored: {result}"
    return result


def text_of(result) -> dict:
    for c in result.get("content", []):
        if c.get("type") == "text":
            return json.loads(c["text"])
    return {}


def main() -> int:
    proc = subprocess.Popen(SERVER, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    try:
        # initialize
        rid = send(proc, "initialize", {"protocolVersion": "2025-06-18",
                                        "clientInfo": {"name": "mcp_smoke", "version": "0"}})
        init = recv(proc, rid)["result"]
        assert init["serverInfo"]["name"] == "vision-gui", init
        send(proc, "notifications/initialized", notify=True)

        # tools/list
        rid = send(proc, "tools/list")
        tools = [t["name"] for t in recv(proc, rid)["result"]["tools"]]
        print(f"[smoke] tools: {tools}")
        assert {"app_launch", "app_close", "shot", "click"} <= set(tools)

        # launch the real app (isolated datadir + stealth boot)
        t0 = time.monotonic()
        info = text_of(call(proc, "app_launch", {"fresh": True}, timeout_s=150))
        print(f"[smoke] launched pid={info['pid']} hwnd={info['hwnd']} "
              f"rect={info['rect']} in {time.monotonic() - t0:.1f}s")

        text_of(call(proc, "app_status"))
        text_of(call(proc, "window"))

        # shot: must carry a real image payload
        shot = call(proc, "shot", timeout_s=60)
        imgs = [c for c in shot["content"] if c.get("type") == "image"]
        assert imgs and len(imgs[0]["data"]) > 10000, "image payload missing/too small"
        meta = text_of(shot)
        print(f"[smoke] shot {meta['size']} -> {meta['saved']} "
              f"({len(imgs[0]['data']) // 1024} KB b64)")

        # click a harmless spot: the app window's own title-less topbar center-ish
        l, t, r, b = info["rect"]
        text_of(call(proc, "click", {"x": (l + r) // 2, "y": t + 18}))
        print("[smoke] click ok (topbar, message-injected)")

        # guardrail: clicking OUTSIDE the app window must be refused
        rid = send(proc, "tools/call", {"name": "click", "arguments": {"x": 5, "y": 5}})
        resp = recv(proc, rid)
        assert resp["result"].get("isError") is True, "outside-window click was NOT refused"
        print("[smoke] outside-window click correctly refused")

        # guardrail: run_case must refuse while an interactive session is active
        rid = send(proc, "tools/call", {"name": "run_case",
                                        "arguments": {"script": "m0_boot_check.py"}})
        resp = recv(proc, rid)
        assert resp["result"].get("isError") is True, "run_case did NOT refuse during interactive session"
        print("[smoke] run_case correctly refused during interactive session")

        text_of(call(proc, "app_close", timeout_s=60))
        print("[smoke] app closed")

        # ---- M2: case listing, real case run, artifact access ----
        cases = text_of(call(proc, "list_cases"))["cases"]
        names = [c["script"] for c in cases]
        assert "m0_boot_check.py" in names, names
        print(f"[smoke] list_cases: {len(names)} cases (m0..m3 suite present)")

        run = text_of(call(proc, "run_case",
                           {"script": "m0_boot_check.py", "timeout_s": 300},
                           timeout_s=330))
        assert run["exit_code"] == 0 and run["green"] is True, run
        print(f"[smoke] run_case m0_boot_check: GREEN in {run['duration_s']}s "
              f"(orphans closed: {run['orphan_windows_closed']})")

        arts = text_of(call(proc, "get_artifacts", {"limit": 50}))["files"]
        assert any(f["path"].replace("\\", "/").startswith("mcp/cases/") for f in arts), arts[:5]
        log_text = text_of(call(proc, "get_artifact", {"path": run["log_path"]}))
        assert "[m0]" in log_text.get("text", ""), "case log unreadable"
        print(f"[smoke] artifacts: {len(arts)} recent files; case log readable")

        # guardrail: artifact path escape must be refused
        rid = send(proc, "tools/call", {"name": "get_artifact",
                                        "arguments": {"path": "../mcp_server.py"}})
        resp = recv(proc, rid)
        assert resp["result"].get("isError") is True, "artifact path escape was NOT refused"
        print("[smoke] artifact path escape correctly refused")

        # ---- M3: scaffold + template crop ----
        scaffold = text_of(call(proc, "case_scaffold",
                                {"name": "m9z_smoke_draft", "goal": "smoke scaffold check"}))
        draft = Path(scaffold["draft"])
        assert draft.exists(), scaffold
        print(f"[smoke] case_scaffold -> {draft.name} (human review gate)")
        draft.unlink()  # smoke cleans up after itself

        tpl = text_of(call(proc, "crop_template",
                           {"shot_path": meta["saved"], "x": 500, "y": 300,
                            "w": 60, "h": 24, "name": "smoke_tpl"}))
        assert Path(tpl["template"]).exists(), tpl
        print(f"[smoke] crop_template -> {Path(tpl['template']).name}")
        Path(tpl["template"]).unlink()

        time.sleep(1.0)
        return 0
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=15)
        except Exception:
            proc.kill()
        print(f"[smoke] server exit code: {proc.returncode}")


if __name__ == "__main__":
    raise SystemExit(main())
