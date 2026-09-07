import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from snapmaker_orca_mcp.config import BridgeConfig
from snapmaker_orca_mcp.errors import BridgeError
from snapmaker_orca_mcp.session_backend import SessionClient, make_session_handlers


class _MockOrca:
    """Minimal stand-in for the Orca listener: token gate + scripted results."""

    def __init__(self, token="tok123"):
        self.token = token
        self.requests = []
        self.script = []  # list of response bodies for poll_job
        self.last_kind = None

    def serve(self):
        orca = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                auth = self.headers.get("Authorization", "")
                orca.requests.append((json.loads(body), auth))
                if auth != f"Bearer {orca.token}":
                    payload = {"error": {"code": -32001, "message": "invalid token"}}
                else:
                    doc = json.loads(body)
                    payload = orca.respond(doc)
                data = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        return server

    def respond(self, doc):
        if doc["method"] == "get_state":
            return {"result": {"ready": True, "plates": [{"index": 1}]}}
        if doc["method"] == "list_devices":
            return {"result": {"devices": [], "selected_device": None}}
        if doc["method"] in ("slice", "set_object_params", "set_plate_params",
                             "send_to_print", "run_calibration"):
            self.last_kind = doc["method"]
            job_id = {"slice": 7, "set_object_params": 8, "set_plate_params": 9,
                      "send_to_print": 10, "run_calibration": 11}[doc["method"]]
            return {"result": {"job_id": job_id, "kind": doc["method"],
                               "state": "pending"}}
        if doc["method"] == "poll_job":
            if self.script:
                return {"result": self.script.pop(0)}
            outcome = "sliced" if self.last_kind == "slice" else "applied"
            if self.last_kind == "send_to_print":
                outcome = "awaiting_user_confirmation"
            return {"result": {"job_id": doc["params"].get("job_id", 0),
                               "state": "done", "percent": 100,
                               "result": {"outcome": outcome}}}
        return {"error": {"code": -32601, "message": "unknown method"}}


@pytest.fixture
def mock_orca(tmp_path):
    orca = _MockOrca()
    server = orca.serve()
    port = server.server_address[1]
    (tmp_path / "mcp_session.json").write_text(
        json.dumps({"port": port, "token": orca.token}), encoding="utf-8"
    )
    config = BridgeConfig(discovery_file=tmp_path / "mcp_session.json")
    yield orca, config
    server.shutdown()


def test_missing_discovery_file(tmp_path):
    config = BridgeConfig(discovery_file=tmp_path / "none.json")
    with pytest.raises(BridgeError) as ei:
        SessionClient(config).call("get_state")
    assert ei.value.code == "session_unavailable"


def test_malformed_discovery_file(tmp_path):
    p = tmp_path / "mcp_session.json"
    p.write_text("{not json", encoding="utf-8")
    config = BridgeConfig(discovery_file=p)
    with pytest.raises(BridgeError) as ei:
        SessionClient(config).call("get_state")
    assert ei.value.code == "discovery_invalid"


def test_call_sends_bearer_token_and_parses_result(mock_orca):
    orca, config = mock_orca
    state = SessionClient(config).call("get_state")
    assert state["ready"] is True
    doc, auth = orca.requests[0]
    assert auth == f"Bearer {orca.token}"
    assert doc["method"] == "get_state"


def test_wrong_token_surfaces_as_auth_error(mock_orca):
    orca, config = mock_orca
    port = json.loads(config.discovery_file().read_text(encoding="utf-8"))["port"]
    client = SessionClient(config)
    client._port = port        # pinned so call() skips the discovery reload
    client._token = "wrong"
    with pytest.raises(BridgeError) as ei:
        client.call("get_state")
    assert ei.value.code == "session_auth"


def test_call_and_wait_polls_until_done(mock_orca):
    orca, config = mock_orca
    orca.script = [
        {"job_id": 7, "state": "running", "percent": 30, "result": {}},
        {"job_id": 7, "state": "running", "percent": 80, "result": {}},
    ]
    seen = []
    result = SessionClient(config).call_and_wait(
        "slice", {}, timeout_s=10, progress=seen.append
    )
    assert result["outcome"] == "sliced"
    assert [s["percent"] for s in seen if s["state"] == "running"] == [30, 80]
    assert seen[-1]["state"] == "done"  # final poll reports terminal state too


def test_call_and_wait_surfaces_failure(mock_orca):
    orca, config = mock_orca
    orca.script = [{"job_id": 7, "state": "failed", "percent": 10,
                    "message": "boom"}]
    with pytest.raises(BridgeError) as ei:
        SessionClient(config).call_and_wait("slice", {}, timeout_s=10)
    assert ei.value.code == "job_failed"
    assert "boom" in str(ei.value)


def test_session_handlers_shape(mock_orca):
    orca, config = mock_orca
    handlers = make_session_handlers(config)
    assert {"get_state", "get_plate_screenshot", "slice", "poll_job",
            "export_gcode", "export_3mf", "set_object_params",
            "set_plate_params"} <= set(handlers)
    assert handlers["get_state"]({})["backend"] == "session"
    with pytest.raises(BridgeError):
        handlers["export_gcode"]({})  # missing path
    with pytest.raises(BridgeError):
        handlers["set_object_params"]({})  # missing object_id/params
    with pytest.raises(BridgeError):
        handlers["set_plate_params"]({})  # missing params


def test_session_object_and_plate_params_roundtrip(mock_orca):
    orca, config = mock_orca
    handlers = make_session_handlers(config)
    result = handlers["set_object_params"](
        {"object_id": 12, "params": {"enable_support": "1"}})
    assert result == {"outcome": "applied"}
    result = handlers["set_plate_params"](
        {"plate": 1, "params": {"print_sequence": "by object"}})
    assert result == {"outcome": "applied"}
    methods = [doc["method"] for doc, _ in orca.requests]
    assert methods.count("set_object_params") == 1
    assert methods.count("set_plate_params") == 1
    obj_doc = next(doc for doc, _ in orca.requests
                   if doc["method"] == "set_object_params")
    assert obj_doc["params"] == {"object_id": 12, "params": {"enable_support": "1"}}
    plate_doc = next(doc for doc, _ in orca.requests
                     if doc["method"] == "set_plate_params")
    assert plate_doc["params"] == {"plate": 1, "params": {"print_sequence": "by object"}}


def test_session_m4_device_tools(mock_orca):
    orca, config = mock_orca
    handlers = make_session_handlers(config)
    assert {"list_devices", "send_to_print", "run_calibration"} <= set(handlers)
    with pytest.raises(BridgeError):
        handlers["run_calibration"]({"mode": "temperature"})  # invalid mode
    result = handlers["list_devices"]({})
    assert result == {"devices": [], "selected_device": None}
    result = handlers["send_to_print"]({})
    assert result == {"outcome": "awaiting_user_confirmation"}
    result = handlers["run_calibration"]({"mode": "flow"})
    assert result == {"outcome": "applied"}  # mock polls to done
    methods = [doc["method"] for doc, _ in orca.requests]
    assert methods.count("list_devices") == 1
    assert methods.count("send_to_print") == 1
    assert methods.count("run_calibration") == 1
