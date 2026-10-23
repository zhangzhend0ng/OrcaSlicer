#!/bin/bash
# Scan a macOS .app bundle for Mach-O files and report their architecture slices.
#
# Usage: scan_app_archs.sh <App.bundle> [--strict] [--all]
#   --strict : exit 1 if any Mach-O under Contents/{MacOS,Frameworks} is missing
#              the x86_64 or arm64 slice (the universal-package contract).
#   --all    : scan the whole bundle (default: Contents/MacOS + Contents/Frameworks,
#              which is where every executable slice lives on our layout).
#
# Companion to verify_universal_archs() in build_release_macos.sh: that one gates
# the build tree, this one verifies a packaged/installed bundle after any signing,
# notarization or repackaging step, so a step that thins or replaces a Mach-O
# cannot pass silently. Runs on macOS only (lipo).
set -u
set -o pipefail

usage() {
    echo "Usage: scan_app_archs.sh <App.bundle> [--strict] [--all]"
    echo "  --strict : exit 1 if any Mach-O under Contents/{MacOS,Frameworks} misses"
    echo "             the x86_64 or arm64 slice (universal-package contract)."
    echo "  --all    : scan the whole bundle instead of the executable trees."
    exit 2
}

APP=""
STRICT=0
WHOLE=0
for arg in "$@"; do
    case "$arg" in
        --strict) STRICT=1 ;;
        --all)    WHOLE=1 ;;
        -h|--help) usage ;;
        *)        APP="$arg" ;;
    esac
done
[ -n "$APP" ] && [ -d "$APP" ] || { echo "ERROR: bundle not found: $APP" >&2; usage; }

if [ "$(uname -s)" != "Darwin" ] || ! command -v lipo >/dev/null 2>&1; then
    echo "ERROR: needs macOS lipo (run on a mac or CI macos runner)" >&2
    exit 2
fi

dirs=()
if [ "$WHOLE" -eq 1 ]; then
    dirs=("$APP")
else
    [ -d "$APP/Contents/MacOS" ] && dirs+=("$APP/Contents/MacOS")
    [ -d "$APP/Contents/Frameworks" ] && dirs+=("$APP/Contents/Frameworks")
fi
[ "${#dirs[@]}" -gt 0 ] || { echo "ERROR: no Contents/MacOS in $APP (not a .app bundle?)" >&2; exit 2; }

universal=0 single=0 other=0 bad=0
while IFS= read -r -d '' f; do
    info=$(lipo -info "$f" 2>/dev/null) || continue   # not a Mach-O: scripts, data, .py
    if echo "$info" | grep -q x86_64 && echo "$info" | grep -q arm64; then
        universal=$((universal + 1))
        status="universal "
    elif echo "$info" | grep -Eq 'x86_64|arm64|arm64_32|ppc'; then
        single=$((single + 1))
        status="SINGLE   "
        [ "$STRICT" -eq 1 ] && bad=$((bad + 1))
    else
        other=$((other + 1))
        status="OTHER    "
        [ "$STRICT" -eq 1 ] && bad=$((bad + 1))
    fi
    printf '%s  %s\n' "$status" "${f#$APP/}"
done < <(find "${dirs[@]}" -type f -print0)

echo "----"
echo "Mach-O total: $((universal + single + other))  universal: $universal  single-arch: $single  other: $other"
if [ "$STRICT" -eq 1 ]; then
    if [ "$bad" -ne 0 ]; then
        echo "FAIL: $bad Mach-O file(s) are not universal" >&2
        exit 1
    fi
    echo "PASS: every Mach-O carries both x86_64 and arm64 slices."
fi
