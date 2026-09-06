"""Headless CLI backend: drives Snapmaker Orca as a slicer subprocess.

Safety model (security harness): the child process is spawned with an
argument **list** (never a shell). Override keys are validated against the
generated parameter catalog plus a small allowlist of CLI action options, so
a caller cannot smuggle arbitrary CLI verbs (e.g. --export-3mf) through
``overrides``.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .config import BridgeConfig
from .errors import BridgeError
from .gcode_stats import parse_gcode_stats
from .presets import prepare_preset_files

# Options the bridge itself may put on the command line.
_BRIDGE_MANAGED_KEYS = {
    "slice", "outputdir", "load_settings", "load_filaments",
    "allow_newer_file", "datadir", "export_3mf", "info", "uptodate",
    "min_save", "no_check", "normative_check", "clone_objects",
    "skip_objects", "loaded_filament_ids", "export_slicedata",
}

# Verb-ish CLI keys must never be reachable through user "overrides".
_FORBIDDEN_OVERRIDE_KEYS = _BRIDGE_MANAGED_KEYS | {"help", "help_center"}


class CliBackend:
    """Runs headless Orca CLI actions and reports structured results."""

    def __init__(self, config: BridgeConfig, catalog=None) -> None:
        self.config = config
        self._catalog = catalog

    # ---- validation -----------------------------------------------------

    def _validate_override_key(self, key: str) -> None:
        if not isinstance(key, str) or not key:
            raise BridgeError("override keys must be non-empty strings", code="bad_override")
        if key.lower() in {k.lower() for k in _FORBIDDEN_OVERRIDE_KEYS}:
            raise BridgeError(
                f"override key is managed by the bridge and cannot be overridden: {key}",
                code="forbidden_override",
            )
        if self._catalog is not None and not self._catalog.has_option(key):
            raise BridgeError(
                f"unknown print parameter: {key} (see list_params for valid keys)",
                code="unknown_param",
            )

    # ---- command assembly -----------------------------------------------

    def build_slice_command(
        self,
        model_path: Path,
        output_dir: Path,
        plate: int,
        overrides: dict[str, object] | None,
        presets: dict,
        allow_newer_file: bool,
    ) -> list[str]:
        exe = str(self.config.find_exe())
        cmd = [exe]
        if allow_newer_file:
            cmd.append("--allow-newer-file")
        data_dir = self.config.data_dir()
        if data_dir is not None:
            cmd += [f"--datadir={data_dir}"]
        if presets.get("machine") or presets.get("process"):
            settings = ";".join(
                p for p in (presets.get("machine"), presets.get("process")) if p
            )
            cmd.append(f"--load-settings={settings}")
        if presets.get("filaments"):
            cmd.append(f"--load-filaments={';'.join(presets['filaments'])}")
        for key, value in (overrides or {}).items():
            self._validate_override_key(key)
            token = self._cli_token_for(key)
            if isinstance(value, bool):
                cmd.append(f"--{token}={1 if value else 0}")
            elif isinstance(value, (list, tuple)):
                cmd.append(f"--{token}={','.join(str(v) for v in value)}")
            else:
                cmd.append(f"--{token}={value}")
        cmd += [f"--slice={plate}", f"--outputdir={output_dir}", str(model_path)]
        return cmd

    def _cli_token_for(self, key: str) -> str:
        """read_cli matches an option's ``cli`` field aliases (dash form); a
        canonical underscore key is only accepted when no alias list exists.
        The catalog therefore decides the exact token."""
        if self._catalog is not None and self._catalog.has_option(key):
            alias = self._catalog.options[key].get("cli")
            if alias:
                return alias.split("|")[0]
        return key.replace("_", "-")

    # ---- execution ------------------------------------------------------

    def _run(self, cmd: list[str], timeout_s: float) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise BridgeError(
                f"Orca CLI timed out after {timeout_s:.0f}s", code="cli_timeout"
            ) from exc
        except OSError as exc:
            raise BridgeError(
                f"failed to launch Orca CLI: {exc}", code="cli_launch_failed"
            ) from exc

    @staticmethod
    def _interpret_exit(proc: subprocess.CompletedProcess) -> dict:
        """Map a CLI exit to a structured status. Crash (neg. code) -> error."""
        code = proc.returncode
        if code >= 2**31:  # Windows reports negative exits as unsigned
            code -= 2**32
        status = {
            "returncode": code,
            "stderr_tail": (proc.stderr or "")[-2000:],
            "stdout_tail": (proc.stdout or "")[-2000:],
        }
        if code == 0:
            status["status"] = "ok"
        elif code < 0 or abs(code) > 128:
            status["status"] = "crashed"
        else:
            status["status"] = "cli_error"
        return status

    # ---- public tools ---------------------------------------------------

    def set_and_slice(
        self,
        model_path: str,
        plate: int = 1,
        overrides: dict[str, object] | None = None,
        printer_preset: str | None = None,
        process_preset: str | None = None,
        filament_presets: list[str] | None = None,
        output_dir: str | None = None,
        timeout_s: float | None = None,
        allow_newer_file: bool = True,
    ) -> dict:
        """Slice one plate headlessly and return gcode path + statistics."""
        src = Path(model_path)
        if not src.is_file():
            raise BridgeError(f"model file not found: {model_path}", code="model_missing")
        if src.suffix.lower() not in {".stl", ".obj", ".3mf", ".ply", ".amf", ".step", ".stp"}:
            raise BridgeError(
                f"unsupported model type: {src.suffix}", code="unsupported_model"
            )
        if not 0 <= plate <= 1024:
            raise BridgeError("plate must be 0 (all) or 1..N", code="bad_plate")

        work_dir = Path(tempfile.mkdtemp(prefix="orca_mcp_slice_"))
        out_dir = Path(output_dir) if output_dir else work_dir / "output"
        out_dir.mkdir(parents=True, exist_ok=True)

        resources = self.config.find_resources_dir()
        presets: dict = {"machine": None, "process": None, "filaments": []}
        if printer_preset or process_preset or filament_presets:
            if resources is None:
                raise BridgeError(
                    "resources directory not found; cannot resolve presets "
                    "(set SNAPMAKER_ORCA_RESOURCES)",
                    code="resources_missing",
                )
            presets = prepare_preset_files(
                resources,
                printer_preset,
                process_preset,
                filament_presets,
                work_dir=work_dir,
            )
        elif src.suffix.lower() != ".3mf":
            raise BridgeError(
                "mesh inputs need explicit presets (printer_preset / "
                "process_preset / filament_presets) or an Orca project 3mf",
                code="presets_required",
            )

        cmd = self.build_slice_command(
            src, out_dir, plate, overrides, presets, allow_newer_file
        )
        started = time.time()
        proc = self._run(cmd, timeout_s or self.config.default_timeout_s)
        elapsed = round(time.time() - started, 2)

        result = self._interpret_exit(proc)
        result.update(
            {
                "command": cmd,
                "elapsed_s": elapsed,
                "output_dir": str(out_dir),
            }
        )
        gcodes = sorted(out_dir.glob("*.gcode"))
        if gcodes:
            result["gcode_files"] = [str(p) for p in gcodes]
            stats = parse_gcode_stats(gcodes[0])
            result["stats"] = stats
        if result["status"] != "ok":
            raise _cli_error(result)
        return result

    def export_3mf(self, model_path: str, output_path: str) -> dict:
        """Produce a 3mf for the given model.

        3mf input is copied through unchanged; mesh input is wrapped into a
        minimal but valid 3mf via trimesh. Full project export (settings +
        thumbnails) requires the Orca GUI session backend (M1+): the CLI
        export path crashes because thumbnail regeneration needs a GL
        context (upstream issue, see docs/mcp-integration-journal.md).
        """
        src = Path(model_path)
        if not src.is_file():
            raise BridgeError(f"model file not found: {model_path}", code="model_missing")
        dst = Path(output_path)
        if dst.suffix.lower() != ".3mf":
            dst = dst.with_suffix(".3mf")
        if dst.resolve() == src.resolve():
            raise BridgeError("output path equals input path", code="bad_output")
        dst.parent.mkdir(parents=True, exist_ok=True)

        if src.suffix.lower() == ".3mf":
            shutil.copyfile(src, dst)
            return {"output_file": str(dst), "bytes": dst.stat().st_size,
                    "method": "copy"}

        from .knowledge.mesh_tools import load_mesh_any  # local import: optional dep
        from .knowledge.threemf_writer import write_minimal_3mf

        mesh, meta = load_mesh_any(src)
        write_minimal_3mf(mesh, dst)
        return {
            "output_file": str(dst),
            "bytes": dst.stat().st_size,
            "method": "minimal_3mf_wrap",
            "source": meta,
        }


def _cli_error(result: dict) -> BridgeError:
    detail = result.get("stderr_tail", "").strip() or result.get("stdout_tail", "").strip()
    last = detail.splitlines()[-1] if detail else "no output"
    kind = {"crashed": "cli_crash", "cli_error": "cli_error"}.get(
        result.get("status"), "cli_failed"
    )
    return BridgeError(
        f"Orca CLI failed (exit {result.get('returncode')}): {last}",
        code=kind,
    )
