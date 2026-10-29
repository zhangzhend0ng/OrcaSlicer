#!/usr/bin/env python
"""Diff two api_surface.json dumps produced by api_surface_dump_plugin.py.

Pure local tool: no app, no orca module needed. Each dump is flattened into
path -> value entries (module / class / member kind / name), then compared:

  - entries only in the first dump  (UPSTREAM-ONLY)
  - entries only in the second dump (PORT-ONLY)
  - entries in both with different value (MISMATCH: signature or enum value)

Usage:
  python diff_api_surface.py <upstream.json> <port.json> [--json-out FILE]
"""

import argparse
import json
import sys


def flatten(dump):
    """modules tree -> {path_string: value}"""
    entries = {}
    modules = dump.get("modules", {})
    for mod_name, mod in modules.items():
        entries[mod_name] = "(module)"
        for fn, sig in mod.get("functions", {}).items():
            entries["%s :: function :: %s" % (mod_name, fn)] = sig
        for const, type_name in mod.get("constants", {}).items():
            entries["%s :: constant :: %s" % (mod_name, const)] = type_name
        for cls_name, cls in mod.get("classes", {}).items():
            entries["%s :: class :: %s" % (mod_name, cls_name)] = "(class)"
            entries["%s :: class :: %s :: bases" % (mod_name, cls_name)] = cls.get("bases", [])
            for m, sig in cls.get("methods", {}).items():
                entries["%s :: class :: %s :: method :: %s" % (mod_name, cls_name, m)] = sig
            for p, kind in cls.get("properties", {}).items():
                entries["%s :: class :: %s :: property :: %s" % (mod_name, cls_name, p)] = kind
            for a, type_name in cls.get("attributes", {}).items():
                entries["%s :: class :: %s :: attribute :: %s" % (mod_name, cls_name, a)] = type_name
            for e, value in cls.get("enum_members", {}).items():
                entries["%s :: class :: %s :: enum :: %s" % (mod_name, cls_name, e)] = value
    return entries


def fmt(value):
    if isinstance(value, list):
        return "[" + ", ".join(str(v) for v in value) + "]"
    return str(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("upstream", help="api_surface.json from upstream OrcaSlicer")
    parser.add_argument("port", help="api_surface.json from the Snapmaker port build")
    parser.add_argument("--json-out", help="also write the full report as JSON")
    parser.add_argument("--expect", help="expectation snapshot (JSON with upstream_only/port_only/mismatched path "
                                         "lists, e.g. from --write-expect). Exit code 0 only when every observed "
                                         "difference is expected (absorbed items vanishing from the expectation "
                                         "are reported as LEDGER-UPDATE, not failures)")
    parser.add_argument("--write-expect", help="write the observed diff as a new expectation snapshot")
    args = parser.parse_args()

    with open(args.upstream, "r", encoding="utf-8") as fh:
        up = flatten(json.load(fh))
    with open(args.port, "r", encoding="utf-8") as fh:
        port = flatten(json.load(fh))

    upstream_only = sorted(set(up) - set(port))
    port_only = sorted(set(port) - set(up))
    mismatched = sorted(k for k in set(up) & set(port) if up[k] != port[k])

    def module_of(path):
        return path.split(" :: ")[0]

    def group(paths):
        out = {}
        for p in paths:
            out.setdefault(module_of(p), []).append(p)
        return out

    lines = []
    lines.append("SUMMARY: upstream_only=%d port_only=%d mismatched=%d "
                 "(upstream entries=%d, port entries=%d)" %
                 (len(upstream_only), len(port_only), len(mismatched), len(up), len(port)))

    def section(title, paths, side_values):
        lines.append("")
        lines.append("## %s (%d)" % (title, len(paths)))
        for mod in sorted(group(paths)):
            lines.append("### %s" % mod)
            for p in group(paths)[mod]:
                lines.append("  - %s  =  %s" % (p, fmt(side_values[p])))

    section("UPSTREAM-ONLY (missing from port)", upstream_only, up)
    section("PORT-ONLY (not in upstream)", port_only, port)
    lines.append("")
    lines.append("## MISMATCH (both sides, different signature/value) (%d)" % len(mismatched))
    for p in mismatched:
        lines.append("  - %s" % p)
        lines.append("      upstream: %s" % fmt(up[p]))
        lines.append("      port:     %s" % fmt(port[p]))

    report = "\n".join(lines)
    print(report)

    if args.json_out:
        payload = {
            "summary": {
                "upstream_only": len(upstream_only),
                "port_only": len(port_only),
                "mismatched": len(mismatched),
                "upstream_entries": len(up),
                "port_entries": len(port),
            },
            "upstream_only": upstream_only,
            "port_only": port_only,
            "mismatched": {p: {"upstream": up[p], "port": port[p]} for p in mismatched},
        }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=1, sort_keys=True)

    if args.write_expect:
        with open(args.write_expect, "w", encoding="utf-8") as fh:
            json.dump({"upstream_only": upstream_only, "port_only": port_only, "mismatched": mismatched},
                      fh, indent=1, sort_keys=True)

    if args.expect:
        with open(args.expect, "r", encoding="utf-8") as fh:
            expected = json.load(fh)
        unexpected = []
        ledger_updates = []
        for category, observed in (("upstream_only", upstream_only), ("port_only", port_only), ("mismatched", mismatched)):
            exp = set(expected.get(category, []))
            for path in observed:
                if path not in exp:
                    unexpected.append("%s: %s" % (category, path))
            for path in sorted(exp - set(observed)):
                ledger_updates.append("%s: %s" % (category, path))
        print("")
        print("## EXPECTATION VERDICT")
        print("  unexpected deviations : %d %s" % (len(unexpected), unexpected if unexpected else ""))
        print("  ledger updates needed : %d %s" % (len(ledger_updates), ledger_updates if ledger_updates else ""))
        print("  VERDICT: %s" % ("PERFECT (all differences are ledger-expected)" if not unexpected else
                                 "DEVIATION (untriaged differences present)"))
        return 1 if unexpected else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
