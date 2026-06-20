#!/usr/bin/env python3
"""Audit god classes (>200 methods) from ctags index."""
import os, sys

ROOT = r"D:\OrcaSlicer_fork"
TAGS_FILE = os.path.join(ROOT, "orcaslicer.tags")
THRESHOLD = 200

def parse_tags(tags_file):
    counts = {}
    files = {}
    with open(tags_file, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("!"):
                continue
            fields = line.rstrip().split("	")
            if len(fields) < 3:
                continue
            name = fields[0]
            fpath = fields[1]
            kind = "?"
            parent = ""
            for i, field in enumerate(fields):
                if field in "cfmpsdvgetnux" and len(field) == 1:
                    if i >= 2 and ';"' in fields[i-1]:
                        kind = field
                        for ef in fields[i+1:]:
                            if ":" in ef:
                                k, v = ef.split(":", 1)
                                if k in ("class", "struct"):
                                    parent = v
                        break
            if kind in ("c", "s"):
                full = parent + "::" + name if parent else name
                if full not in counts:
                    counts[full] = 0
                    files[full] = fpath
            if kind in ("f", "m", "p") and parent in counts:
                counts[parent] += 1
    return counts, files

def main():
    if not os.path.exists(TAGS_FILE):
        print("ERROR: Tags file not found: " + TAGS_FILE)
        sys.exit(1)
    counts, files = parse_tags(TAGS_FILE)
    gods = [(c, n, files.get(c, "")) for c, n in counts.items() if n > THRESHOLD]
    gods.sort(key=lambda x: -x[1])
    if gods:
        print("GOD CLASSES (> {} methods): {}".format(THRESHOLD, len(gods)))
        for cls, n, fp in gods:
            rel = os.path.relpath(fp, ROOT) if fp else "?"
            print("  {:5d}  {}  ({})".format(n, cls, rel))
        sys.exit(1)
    else:
        print("PASS: No classes exceed {} methods.".format(THRESHOLD))
    sys.exit(0)

if __name__ == "__main__":
    main()
