#!/usr/bin/env python3
"""Analyze module dependency cycles from module_deps.json."""
import json, sys, os

ROOT = r"D:\OrcaSlicer_fork"
DEPS_FILE = os.path.join(ROOT, "analysis_output", "module_deps.json")

def find_cycles(deps):
    modules = {m["module"]: set(m.get("depends_on", [])) for m in deps.get("modules", [])}
    def dfs(node, visited, stack):
        visited.add(node)
        stack.append(node)
        cycles = []
        for neighbor in modules.get(node, set()):
            if neighbor not in modules:
                continue
            if neighbor not in visited:
                cycles.extend(dfs(neighbor, visited, stack))
            elif neighbor in stack:
                idx = stack.index(neighbor)
                cycles.append(stack[idx:] + [neighbor])
        stack.pop()
        return cycles
    all_cycles = []
    visited = set()
    for node in sorted(modules.keys()):
        if node not in visited:
            all_cycles.extend(dfs(node, visited, []))
    unique = []
    seen = set()
    for c in all_cycles:
        key = tuple(sorted(c[:-1]))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique

def is_cross(cycle):
    has_core = any("libslic3r" in m for m in cycle)
    has_gui = any("slic3r::" in m for m in cycle)
    return has_core and has_gui

def main():
    with open(DEPS_FILE, encoding="utf-8") as f:
        deps = json.load(f)
    cycles = find_cycles(deps)
    cross = [c for c in cycles if is_cross(c)]
    print("Total cycles: {}, Cross-boundary: {}".format(len(cycles), len(cross)))
    if cross:
        print("CROSS-BOUNDARY CYCLES:")
        for c in cross:
            print("  " + " -> ".join(c))
        sys.exit(1)
    elif cycles:
        print("Internal cycles only:")
        for c in cycles:
            print("  " + " -> ".join(c))
    else:
        print("PASS: Zero cycles.")
    sys.exit(0)

if __name__ == "__main__":
    main()
