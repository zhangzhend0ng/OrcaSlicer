"""Generate data/params_catalog.json from src/libslic3r/PrintConfig.cpp.

The C++ config registry is the single source of truth for print parameters
(``PrintConfigDef`` tables). This dev-time generator extracts, for every
option: type, label, tooltip, enum values/labels, min/max, default (best
effort), and scope classification (machine / process / filament) derived from
the config-def class the option is registered in.

Usage (from repo root, with the worktree checked out)::

    python tools/mcp-bridge/scripts/generate_params_catalog.py \
        --print-config src/libslic3r/PrintConfig.cpp \
        --out tools/mcp-bridge/snapmaker_orca_mcp/data/params_catalog.json

The parser is intentionally conservative: entries it cannot fully
understand are exported with partial metadata rather than dropped, and the
generator refuses to run against a file whose structure no longer matches
(a layout version marker guards silent drift).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

LAYOUT_MARKER = "ConfigOptionDef* def;"

# Registration order inside PrintConfig.cpp: each `this->add(...)` happens
# inside a specific XxxConfigDef constructor, which determines the scope.
CONSTRUCTOR_SCOPES = [
    ("PrintConfigDef::PrintConfigDef", ["process", "filament", "machine"]),
    ("PrintObjectConfigDef::PrintObjectConfigDef", ["process"]),
    ("PrintRegionConfigDef::PrintRegionConfigDef", ["process"]),
    ("MachineConfigDef", ["machine", "filament"]),
    ("CLIActionsConfigDef", []),
    ("CLITransformConfigDef", []),
    ("CLIMiscConfigDef", []),
]


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return text


def split_top_level_functions(text: str) -> list[tuple[str, str]]:
    """Return [( 'ClassName::Ctor', body ), ...] for the config-def ctors."""
    out = []
    ctor_re = re.compile(
        r"(\w+Def::\w+Def)\s*\(\s*[^)]*\)\s*\{", re.S
    )
    matches = list(ctor_re.finditer(text))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append((m.group(1), text[start:end]))
    return out


def parse_options(body: str) -> dict:
    """Parse `def = this->add("key", coType);` blocks."""
    # Cut trailing helper methods that follow the ctor body's add() block:
    # blocks always start with `def = this->add(` - stop at the first
    # non-add method definition.
    options = {}
    add_re = re.compile(
        r'def\s*=\s*this->add\(\s*"([^"]+)"\s*,\s*(co\w+)\s*\);',
        re.S,
    )
    for m in add_re.finditer(body):
        key, ctype = m.group(1), m.group(2)
        nxt = add_re.search(body, m.end())
        block_end = nxt.start() if nxt else min(m.end() + 4000, len(body))
        block = body[m.end() : block_end]
        opt = {"type": ctype.lstrip("co"), "scopes": []}
        label = re.search(r"def->label\s*=\s*L\(\"([^\"]*)\"\)", block)
        if label:
            opt["label"] = label.group(1)
        tooltip = re.search(r"def->tooltip\s*=\s*L\(\"(.*?)\"\);", block, re.S)
        if tooltip:
            opt["tooltip"] = tooltip.group(1)[:500]
        enums = re.findall(r"def->enum_values\.push_back\(\s*\"([^\"]*)\"\s*\)", block)
        if enums:
            opt["enum_values"] = enums
        enum_labels = re.findall(
            r"def->enum_labels\.push_back\(\s*L\(\"([^\"]*)\"\)\s*\)", block
        )
        if enum_labels:
            opt["enum_labels"] = enum_labels
        minv = re.search(r"def->min\s*=\s*([\d.eE+-]*\d[\d.eE+-]*)", block)
        if minv:
            opt["min"] = float(minv.group(1))
        maxv = re.search(r"def->max\s*=\s*([\d.eE+-]*\d[\d.eE+-]*)", block)
        if maxv:
            opt["max"] = float(maxv.group(1))
        default_str = re.search(
            r"set_default_value\(new\s+ConfigOption\w+\(\s*\"([^\"]*)\"", block
        )
        if default_str:
            opt["default"] = default_str.group(1)
        else:
            default_num = re.search(
                r"set_default_value\(new\s+ConfigOption\w+\(\s*([^\(\)]*?)\s*\)\)",
                block,
            )
            if default_num:
                opt["default"] = default_num.group(1).strip()
        cli = re.search(r'def->cli\s*=\s*"([^"]*)"', block)
        if cli:
            opt["cli"] = cli.group(1)
        options[key] = opt
    return options


SCOPE_RULES = [
    # option key prefix -> scope
    ("filament_", "filament"),
    ("nozzle_", "machine"),
    ("printable_", "machine"),
    ("bed_", "machine"),
    ("machine_", "machine"),
    ("printer_", "machine"),
    ("gcode_", "machine"),
]

KNOWN_PROCESS_ONLY = {
    "layer_height", "initial_layer_print_height", "sparse_infill_density",
    "support_threshold_angle", "brim_width", "wall_loops", "top_shell_layers",
    "bottom_shell_layers", "infill_pattern", "support_type",
}


def classify(key: str, default_scopes: list[str]) -> list[str]:
    scopes = list(default_scopes)
    if key in KNOWN_PROCESS_ONLY:
        return ["process"]
    for prefix, scope in SCOPE_RULES:
        if key.startswith(prefix) and scope not in scopes:
            scopes.append(scope)
    return scopes or ["process"]


def generate(print_config_path: Path) -> dict:
    raw = print_config_path.read_text(encoding="utf-8", errors="replace")
    if LAYOUT_MARKER not in raw:
        raise SystemExit(
            "PrintConfig.cpp layout changed (marker not found); this "
            "generator needs updating - refusing to emit a stale catalog."
        )
    text = strip_comments(raw)
    catalog: dict = {"source": str(print_config_path.name), "options": {}}
    skipped_cli = 0
    for ctor_name, body in split_top_level_functions(text):
        default_scopes = ["process", "filament", "machine"]
        for pat, scopes in CONSTRUCTOR_SCOPES:
            if ctor_name.startswith(pat.split("::")[0]):
                default_scopes = scopes
                break
        if ctor_name.startswith(("CLIActionsConfigDef", "CLITransformConfigDef", "CLIMiscConfigDef")):
            default_scopes = []
        for key, opt in parse_options(body).items():
            if not default_scopes:
                opt["scopes"] = ["cli"]
            else:
                opt["scopes"] = classify(key, default_scopes)
            if not opt["scopes"]:
                skipped_cli += 1
                opt["scopes"] = ["cli"]
            catalog["options"][key] = opt
    catalog["total"] = len(catalog["options"])
    catalog["cli_only_options"] = skipped_cli
    catalog["scopes_legend"] = {
        "machine": "printer-level settings",
        "process": "print quality / structure settings",
        "filament": "material settings",
        "cli": "CLI-only verbs (not print parameters)",
    }
    return catalog


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--print-config",
        type=Path,
        default=Path("src/libslic3r/PrintConfig.cpp"),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("tools/mcp-bridge/snapmaker_orca_mcp/data/params_catalog.json"),
    )
    args = ap.parse_args()
    catalog = generate(args.print_config)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"wrote {catalog['total']} options to {args.out}")


if __name__ == "__main__":
    main()
