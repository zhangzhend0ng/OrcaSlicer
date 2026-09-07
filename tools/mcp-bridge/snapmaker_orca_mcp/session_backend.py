"""Session backend: talks to the Orca in-process MCP listener.

Discovery: reads `<data_dir>/mcp_session.json` = {"port": N, "token": "..."}
written by the Orca listener on startup. The port is NEVER guessed: the
legacy HttpServer silently drifts +1000 when busy, so a stale or missing
discovery file is an error, not a fallback condition.

Protocol: private POST JSON-RPC over loopback HTTP with
`Authorization: Bearer <token>` on every request.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from .config import BridgeConfig
from .errors import BridgeError

POLL_INTERVAL_S = 0.5
POLL_DEFAULT_TIMEOUT_S = 900.0


class SessionClient:
    """Thin synchronous client for the Orca listener."""

    def __init__(self, config: BridgeConfig):
        self.config = config
        self._port: int | None = None
        self._token: str | None = None

    def _load_discovery(self) -> None:
        path = self.config.discovery_file()
        if not path.is_file():
            raise BridgeError(
                f"Orca session not available: discovery file missing at {path} "
                "(is the MCP interface enabled in Orca preferences?)",
                code="session_unavailable",
            )
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            self._port = int(doc["port"])
            self._token = str(doc["token"])
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise BridgeError(
                f"discovery file at {path} is malformed: {exc}",
                code="discovery_invalid",
            ) from exc

    def call(self, method: str, params: dict | None = None, timeout_s: float = 30.0) -> dict:
        """One JSON-RPC round trip; returns the result or raises BridgeError."""
        if self._port is None or self._token is None:
            self._load_discovery()
        payload = json.dumps(
            {"method": method, "params": params or {}, "id": 1}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{self._port}/",
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                doc = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError) as exc:
            raise BridgeError(
                f"Orca session unreachable: {exc}", code="session_unreachable"
            ) from exc
        except json.JSONDecodeError as exc:
            raise BridgeError(
                f"Orca session returned non-JSON: {exc}", code="session_bad_response"
            ) from exc
        if "error" in doc:
            err = doc["error"]
            code_map = {
                -32001: "session_auth",
                -32002: "ui_busy",
                -32003: "unknown_job",
                -32601: "unknown_method",
                -32602: "bad_params",
            }
            raise BridgeError(
                f"Orca session error {err.get('code')}: {err.get('message')}",
                code=code_map.get(err.get("code", 0), "session_error"),
            )
        return doc.get("result", {})

    def call_and_wait(
        self,
        method: str,
        params: dict | None = None,
        timeout_s: float = POLL_DEFAULT_TIMEOUT_S,
        progress=None,
    ) -> dict:
        """Start a job and poll it to completion. Returns the job result.

        `progress(job_state_dict)` is invoked after each poll when provided.
        """
        started = self.call(method, params)
        job_id = started.get("job_id")
        if not job_id:
            return started  # method completed synchronously
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            state = self.call("poll_job", {"job_id": job_id})
            if progress is not None:
                progress(state)
            if state.get("state") == "done":
                return state.get("result", {})
            if state.get("state") == "failed":
                raise BridgeError(
                    f"Orca job {state.get('kind')} failed: "
                    f"{state.get('message', 'no detail')}",
                    code="job_failed",
                )
            time.sleep(POLL_INTERVAL_S)
        raise BridgeError(
            f"Orca job {method} timed out after {timeout_s:.0f}s",
            code="job_timeout",
        )


# ---- tool handlers over the session backend -------------------------------


def make_session_handlers(config: BridgeConfig) -> dict:
    """Build the session tool handlers wired to a live Orca instance."""

    def _client() -> SessionClient:
        return SessionClient(config)

    def get_state(args: dict) -> dict:
        state = _client().call("get_state")
        state["backend"] = "session"
        return state

    def load_models(args: dict) -> dict:
        paths = args.get("paths")
        if not paths or not isinstance(paths, list):
            raise BridgeError("paths must be a non-empty list", code="bad_request")
        return _client().call_and_wait(
            "load_models", {"paths": paths},
            timeout_s=float(args.get("timeout_s", 300)))

    def get_plate_screenshot(args: dict) -> dict:
        result = _client().call_and_wait(
            "get_plate_screenshot",
            {
                "plate_index": int(args.get("plate_index", 1)),
                "width": int(args.get("width", 512)),
                "height": int(args.get("height", 512)),
            },
            timeout_s=float(args.get("timeout_s", 60)),
        )
        return {"format": result.get("format", "png"), "image_base64": result.get("image_base64", "")}

    def slice_(args: dict) -> dict:
        state: dict = {}

        def progress(job: dict) -> None:
            state.update(job)

        result = _client().call_and_wait("slice", {"plate": int(args.get("plate", 0))},
                                         timeout_s=float(args.get("timeout_s", 1800)),
                                         progress=progress)
        result["last_percent"] = state.get("percent", 100)
        return result

    def set_params(args: dict) -> dict:
        params = args.get("params")
        if not isinstance(params, dict) or not params:
            raise BridgeError("params must be a non-empty object", code="bad_request")
        return _client().call_and_wait("set_params", {"params": params},
                                       timeout_s=float(args.get("timeout_s", 120)))

    def set_object_params(args: dict) -> dict:
        object_id = args.get("object_id")
        if not object_id:
            raise BridgeError("object_id is required", code="bad_request")
        params = args.get("params")
        if not isinstance(params, dict) or not params:
            raise BridgeError("params must be a non-empty object", code="bad_request")
        return _client().call_and_wait(
            "set_object_params", {"object_id": int(object_id), "params": params},
            timeout_s=float(args.get("timeout_s", 120)))

    def set_plate_params(args: dict) -> dict:
        params = args.get("params")
        if not isinstance(params, dict) or not params:
            raise BridgeError("params must be a non-empty object", code="bad_request")
        payload = {"plate": int(args.get("plate", 0)), "params": params}
        return _client().call_and_wait("set_plate_params", payload,
                                       timeout_s=float(args.get("timeout_s", 120)))

    def remove_object(args: dict) -> dict:
        object_id = args.get("object_id")
        if not object_id:
            raise BridgeError("object_id is required", code="bad_request")
        return _client().call_and_wait("remove_object", {"object_id": int(object_id)},
                                       timeout_s=float(args.get("timeout_s", 120)))

    def set_transform(args: dict) -> dict:
        object_id = args.get("object_id")
        if not object_id:
            raise BridgeError("object_id is required", code="bad_request")
        payload = {"object_id": int(object_id)}
        for key in ("translation_mm", "rotation_deg", "scaling_factor"):
            if args.get(key):
                payload[key] = args[key]
        return _client().call_and_wait("set_transform", payload,
                                       timeout_s=float(args.get("timeout_s", 120)))

    def arrange(args: dict) -> dict:
        return _client().call_and_wait("arrange", {},
                                       timeout_s=float(args.get("timeout_s", 300)))

    def poll_job(args: dict) -> dict:
        return _client().call("poll_job", {"job_id": int(args.get("job_id", 0))})

    def list_devices(args: dict) -> dict:
        return _client().call("list_devices", {})

    def send_to_print(args: dict) -> dict:
        return _client().call_and_wait("send_to_print", {},
                                       timeout_s=float(args.get("timeout_s", 120)))

    def run_calibration(args: dict) -> dict:
        mode = args.get("mode")
        if mode not in ("flow", "pa"):
            raise BridgeError("mode must be 'flow' or 'pa'", code="bad_request")
        return _client().call_and_wait("run_calibration", {"mode": mode},
                                       timeout_s=float(args.get("timeout_s", 120)))

    def export_gcode(args: dict) -> dict:
        path = args.get("path")
        if not path:
            raise BridgeError("path is required", code="bad_request")
        return _client().call_and_wait("export_gcode", {"path": path},
                                       timeout_s=float(args.get("timeout_s", 900)))

    def export_3mf(args: dict) -> dict:
        path = args.get("path")
        if not path:
            raise BridgeError("path is required", code="bad_request")
        return _client().call_and_wait(
            "export_3mf",
            {"path": path, "all_plates": bool(args.get("all_plates", True))},
            timeout_s=float(args.get("timeout_s", 600)),
        )

    return {
        "get_state": get_state,
        "load_models": load_models,
        "set_params": set_params,
        "set_object_params": set_object_params,
        "set_plate_params": set_plate_params,
        "remove_object": remove_object,
        "set_transform": set_transform,
        "arrange": arrange,
        "get_plate_screenshot": get_plate_screenshot,
        "slice": slice_,
        "poll_job": poll_job,
        "list_devices": list_devices,
        "send_to_print": send_to_print,
        "run_calibration": run_calibration,
        "export_gcode": export_gcode,
        "export_3mf": export_3mf,
    }
