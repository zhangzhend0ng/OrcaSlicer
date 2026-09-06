# snapmaker-orca-mcp (bridge)

MCP (Model Context Protocol) bridge for Snapmaker Orca. Exposes Orca capabilities
to any MCP client (Claude Desktop, etc.) over stdio using the official MCP SDK.

## Architecture

```
Claude / any MCP client
   | stdio (official MCP SDK)
   v
[snapmaker-orca-mcp bridge]  (this package)
   |
   +-- CLI backend (M0): spawns headless Snapmaker_Orca.exe CLI
   |     set_and_slice / export_3mf
   +-- Session backend (M1+): HTTP JSON-RPC to in-process Orca listener
         get_state / slice / export_gcode / get_plate_screenshot ...
   +-- Knowledge layer (M0, local): trimesh-based mesh analysis
         analyze_mesh / check_printability / suggest_orientation / estimate_cost
         + list_params (generated parameter catalog)
```

Tool schemas live in a single source of truth: `snapmaker_orca_mcp/tools_schema.json`.
Both backends must serve the same schema (see risk register in the integration plan).

## Install / run

```bash
pip install -r requirements.txt
python -m snapmaker_orca_mcp --help
```

Environment overrides:

| Variable | Meaning |
|---|---|
| `SNAPMAKER_ORCA_EXE` | Path to `snapmaker-orca.exe` / `Snapmaker_Orca.exe` |
| `SNAPMAKER_ORCA_RESOURCES` | Path to Orca `resources/` directory |
| `SNAPMAKER_ORCA_DATA_DIR` | Orca data directory (datadir) |
| `SNAPMAKER_ORCA_MCP_DISCOVERY` | Path of M1+ session discovery file (port+token) |

## Layout

- `snapmaker_orca_mcp/server.py` - MCP stdio server, tool dispatch
- `snapmaker_orca_mcp/tools_schema.json` - single source of truth for tool schemas
- `snapmaker_orca_mcp/config.py` - exe/resources/datadir/discovery resolution
- `snapmaker_orca_mcp/cli_backend.py` - headless CLI subprocess wrapper
- `snapmaker_orca_mcp/gcode_stats.py` - gcode footer statistics parser
- `snapmaker_orca_mcp/knowledge/mesh_tools.py` - trimesh knowledge tools
- `snapmaker_orca_mcp/params_catalog.py` - parameter catalog access
- `scripts/generate_params_catalog.py` - regenerates `data/params_catalog.json`
  from `src/libslic3r/PrintConfig.cpp` (dev-time, not shipped to end users)

## Tests

```bash
python -m pytest tools/mcp-bridge/tests -q          # unit tests (no Orca needed)
python tools/mcp-bridge/tests/e2e/e2e_m0_cli.py     # E2E (needs built Snapmaker_Orca.exe)
```
