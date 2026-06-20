#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Check that libslic3r never includes slic3r/GUI headers (Layer 2 -> Layer 4 violation)."""
import os, re, sys

ROOT = r"D:\OrcaSlicer_fork"
SRC = os.path.join(ROOT, "src")
LIBSLIC3R = os.path.join(SRC, "libslic3r")

FORBIDDEN = [
    r'#include\s+[<"]slic3r/GUI/',
    r'#include\s+[<"]slic3r/Gizmos/',
    r'#include\s+[<"]slic3r/Widgets/',
]

COMMENT_RE = re.compile(r'^\s*//|^\s*\*|^\s*/\*')

def check_file(filepath):
    violations = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            for lineno, line in enumerate(f, 1):
                stripped = line.strip()
                # Skip comment-only lines
                if COMMENT_RE.match(stripped):
                    continue
                for pat in FORBIDDEN:
                    if re.search(pat, line):
                        violations.append((lineno, line.strip()))
    except OSError:
        pass
    return violations

def main():
    all_v = {}
    for root, dirs, files in os.walk(LIBSLIC3R):
        for fn in files:
            if fn.endswith((".cpp", ".hpp", ".h", ".c", ".cc")):
                fp = os.path.join(root, fn)
                v = check_file(fp)
                if v:
                    all_v[os.path.relpath(fp, ROOT)] = v
    if all_v:
        total = sum(len(v) for v in all_v.values())
        print("FOUND {} LAYER VIOLATIONS (libslic3r -> GUI):".format(total))
        for fp, vs in sorted(all_v.items()):
            print("  {}:".format(fp))
            for ln, line in vs[:5]:
                print("    L{}: {}".format(ln, line))
        sys.exit(1)
    else:
        print("OK: No libslic3r -> GUI include violations.")
        sys.exit(0)

if __name__ == "__main__":
    main()
