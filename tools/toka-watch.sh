#!/usr/bin/env bash
# toka-watch - Watch .tk files and auto-recompile on changes.
# Uses fswatch (macOS) or inotifywait (Linux).
#
# Usage:
#   toka-watch demo.tk                    # Watch single file
#   toka-watch -I lib -I . demo.tk        # With include paths
#   toka-watch --run demo.tk              # Re-run after compile
#   toka-watch --check-only demo.tk       # Only type-check

set -euo pipefail

ARGS=()
WATCH_FILES=()
RUN_AFTER=false
CHECK_ONLY=false
TOKAC="${TOKAC:-./build/bin/tokac}"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --run) RUN_AFTER=true; shift ;;
        --check-only) CHECK_ONLY=true; shift ;;
        -I) ARGS+=("-I" "$2"); shift 2 ;;
        *) WATCH_FILES+=("$1"); shift ;;
    esac
done

if [[ ${#WATCH_FILES[@]} -eq 0 ]]; then
    echo "Usage: toka-watch [--run] [--check-only] [-I dir ...] file.tk"
    exit 1
fi

# Determine watch command
if command -v fswatch &>/dev/null; then
    WATCH_CMD="fswatch -1"
elif command -v inotifywait &>/dev/null; then
    WATCH_CMD="inotifywait -e modify -qq"
else
    echo "ERROR: need fswatch (macOS) or inotifywait (Linux)"
    echo "  brew install fswatch  # macOS"
    echo "  apt install inotify-tools  # Linux"
    exit 1
fi

echo "🔍 Watching: ${WATCH_FILES[*]}"
echo "   Compile:  ${TOKAC}"
echo "   Args:     ${ARGS[*]:-(none)}"
echo "   Run:      $RUN_AFTER"
echo "   Check:    $CHECK_ONLY"
echo ""

compile_and_run() {
    local ts
    ts=$(date '+%H:%M:%S')
    
    if $CHECK_ONLY; then
        echo "[$ts] 🔍 Type-checking..."
        "$TOKAC" --check-only "${ARGS[@]}" "${WATCH_FILES[@]}" 2>&1
        local rc=$?
    else
        echo "[$ts] 🔨 Compiling..."
        local out_file="${WATCH_FILES[0]%.tk}"
        "$TOKAC" -o "$out_file" "${ARGS[@]}" "${WATCH_FILES[@]}" 2>&1
        local rc=$?
    fi
    
    if [[ $rc -eq 0 ]]; then
        echo "   ✅ OK"
        if $RUN_AFTER && ! $CHECK_ONLY; then
            echo "   🚀 Running ./$out_file"
            "./$out_file"
        fi
    else
        echo "   ❌ Failed (exit $rc)"
    fi
    echo ""
}

# Initial compile
compile_and_run

# Watch loop
while true; do
    $WATCH_CMD "${WATCH_FILES[@]}" 2>/dev/null
    compile_and_run
done
