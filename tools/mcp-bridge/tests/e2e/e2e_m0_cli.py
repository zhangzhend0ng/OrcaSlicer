"""M0 E2E: bridge backend tools against a REAL Snapmaker Orca CLI build.

Run from the worktree root::

    python tools/mcp-bridge/tests/e2e/e2e_m0_cli.py \
        --exe build/src/Release/snapmaker-orca.exe

Checks (each prints PASS/FAIL and the script exits non-zero on failure):
  1. analyze_mesh on a real exported Orca 3mf (resources/handy_models)
  2. check_printability / suggest_orientation / estimate_cost on a real
     geometric mesh generated on the fly (two spheres - solid, non-trivial)
  3. list_params catalog query
  4. set_and_slice: OBJ + Artisan presets + layer_height override -> gcode
     with the override visible in the gcode config block + stats footer
  5. set_and_slice rejects unknown override keys (structured error)
  6. slicing a newer-version project 3mf reports the documented upstream
     CLI crash as a clean structured error (no hang, no traceback)
  7. export_3mf mesh wrap round-trips through trimesh
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

BRIDGE = Path(__file__).resolve().parents[2]
REPO_ROOT = BRIDGE.parents[1]
sys.path.insert(0, str(BRIDGE))

from snapmaker_orca_mcp.cli_backend import CliBackend  # noqa: E402
from snapmaker_orca_mcp.config import BridgeConfig  # noqa: E402
from snapmaker_orca_mcp.errors import BridgeError  # noqa: E402
from snapmaker_orca_mcp.knowledge import mesh_tools  # noqa: E402
from snapmaker_orca_mcp.params_catalog import ParamsCatalog  # noqa: E402

FAILURES: list[str] = []
REAL_3MF = REPO_ROOT / "resources" / "handy_models" / "3DBenchy.3mf"
NEWER_3MF = REPO_ROOT / "resources" / "calib" / "pressure_advance" / "pa_pattern.3mf"


def check(name: str, condition: bool, detail: str = "") -> None:
    mark = "PASS" if condition else "FAIL"
    print(f"[{mark}] {name}" + (f" :: {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(name)


def make_fixture(out_dir: Path) -> Path:
    """Real solid geometry (two merged spheres), not a degenerate stub."""
    import trimesh

    a = trimesh.creation.icosphere(subdivisions=3, radius=12.0)
    b = trimesh.creation.icosphere(subdivisions=3, radius=8.0)
    b.apply_translation([18.0, 0.0, 0.0])
    merged = a + b
    p = out_dir / "twospheres.obj"
    merged.export(p, file_type="obj")
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--exe",
        default=str(REPO_ROOT / "build" / "src" / "Release" / "snapmaker-orca.exe"),
    )
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="orca_m0_e2e_"))
    print(f"E2E workdir: {work}")

    config = BridgeConfig(
        exe_path=args.exe,
        resources_dir=REPO_ROOT / "resources",
        data_dir=Path.home() / "AppData" / "Roaming" / "Snapmaker_Orca",
        default_timeout_s=900,
    )
    catalog = ParamsCatalog()
    cli = CliBackend(config, catalog=catalog)
    fixture = make_fixture(work)
    print(f"fixture: {fixture}")

    # ---- 1. knowledge tools on a real exported Orca 3mf ----------------
    t0 = time.time()
    info = mesh_tools.analyze_mesh(str(REAL_3MF))
    check("analyze_mesh(3DBenchy.3mf) volume>0", info.get("volume_mm3", 0) > 0,
          json.dumps(info)[:300])
    check("analyze_mesh format=3mf", info.get("format") == "3mf")
    check("analyze_mesh triangles>100", info.get("triangles", 0) > 100)
    print(f"       (analyze took {time.time()-t0:.2f}s, "
          f"vol={info.get('volume_mm3')}mm3, tris={info.get('triangles')})")

    # ---- 2. knowledge tools on the fixture mesh -------------------------
    printable = mesh_tools.check_printability(
        str(fixture), build_volume_mm=[400, 350, 350]
    )
    check("check_printability ok", printable.get("printable") is True,
          json.dumps(printable)[:300])
    orient = mesh_tools.suggest_orientation(str(fixture))
    check("suggest_orientation ranked", len(orient.get("candidates", [])) >= 3)
    cost = mesh_tools.estimate_cost(str(fixture), filament_price_per_kg=20.0)
    check("estimate_cost weight>0", cost.get("filament_weight_g", 0) > 0,
          json.dumps(cost)[:300])

    # ---- 3. list_params --------------------------------------------------
    res = catalog.list_params(scope="process", search="layer_height")
    check("list_params finds layer_height", "layer_height" in res["options"],
          json.dumps(res)[:200])
    check("list_params total>500", res["total_options"] > 500)

    # ---- 4. set_and_slice with override ----------------------------------
    t0 = time.time()
    try:
        sliced = cli.set_and_slice(
            model_path=str(fixture),
            plate=1,
            overrides={"layer_height": 0.3, "sparse_infill_density": "15%"},
            printer_preset="Snapmaker Artisan (0.4 nozzle)",
            process_preset="0.16 Optimal @Snapmaker Artisan (0.4 nozzle)",
            filament_presets=["Generic PLA"],
        )
        gcode = Path(sliced["gcode_files"][0])
        check("set_and_slice produced gcode", gcode.is_file())
        stats = sliced.get("stats", {})
        check("stats layers>0", stats.get("layers", 0) > 0, json.dumps(stats)[:300])
        check("stats time>0", stats.get("estimated_time_s", 0) > 0)
        check("stats weight>0", stats.get("filament_used_g", 0) > 0)
        gcode_text = gcode.read_text(encoding="utf-8", errors="replace")
        check(
            "layer_height override reached gcode",
            "; layer_height = 0.3" in gcode_text,
            "expected '; layer_height = 0.3' in config block",
        )
        check(
            "infill override reached gcode",
            "; sparse_infill_density = 15%" in gcode_text,
        )
        print(f"       (slice took {time.time()-t0:.1f}s -> {gcode.name}, "
              f"layers={stats.get('layers')}, time={stats.get('estimated_time_human')})")
    except BridgeError as exc:
        check("set_and_slice completed", False, f"[{exc.code}] {exc}")

    # ---- 5. unknown override key rejected --------------------------------
    try:
        cli.set_and_slice(
            model_path=str(fixture),
            printer_preset="Snapmaker Artisan (0.4 nozzle)",
            process_preset="0.16 Optimal @Snapmaker Artisan (0.4 nozzle)",
            filament_presets=["Generic PLA"],
            overrides={"not_a_real_param": 1},
        )
        check("unknown override rejected", False, "no error raised")
    except BridgeError as exc:
        check("unknown override rejected", exc.code == "unknown_param", exc.code)

    # ---- 6. newer-version 3mf -> clean structured error -------------------
    if NEWER_3MF.is_file():
        t0 = time.time()
        try:
            cli.set_and_slice(
                model_path=str(NEWER_3MF),
                printer_preset="Snapmaker Artisan (0.4 nozzle)",
                process_preset="0.16 Optimal @Snapmaker Artisan (0.4 nozzle)",
                filament_presets=["Generic PLA"],
                timeout_s=240,
            )
            check("3mf crash surfaces as error", False, "no error raised")
        except BridgeError as exc:
            check(
                "3mf crash surfaces as error",
                exc.code in ("cli_crash", "cli_error", "cli_failed"),
                f"code={exc.code}",
            )
        print(f"       (crash path surfaced in {time.time()-t0:.1f}s, no hang)")

    # ---- 7. export_3mf round-trip -----------------------------------------
    import trimesh

    out = cli.export_3mf(str(fixture), str(work / "twospheres_out.3mf"))
    reloaded = trimesh.load(out["output_file"], force="mesh")
    check("export_3mf roundtrip volume", reloaded.volume > 1000,
          f"volume={reloaded.volume}")

    print()
    if FAILURES:
        print(f"E2E RESULT: RED ({len(FAILURES)} failed): {FAILURES}")
        return 1
    print("E2E RESULT: GREEN (all checks passed)")
    if not args.keep:
        shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
