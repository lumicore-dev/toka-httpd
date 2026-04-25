#!/usr/bin/env bash
# toka-watch - Watch .tk files and hot-reload on changes.
#
# Uses fswatch for efficiency (macOS). Falls back to stat polling.
#
# Usage:
#   toka-watch demo.tk                    # Type-check on change
#   toka-watch --dev demo.tk              # Dev server hot-reload
#   toka-watch --dev -- demo.tk -- -p 9000
#   toka-watch -I lib -I . --dev demo.tk

set -euo pipefail

DEV_MODE=false
CHECK_ONLY=false
SERVER_ARGS=()
ARGS_I=()
WATCH_FILES=()
TOKAC="${TOKAC:-./build/bin/tokac}"
SERVER_PID=""
POLL_INTERVAL="${POLL_INTERVAL:-0.5}"
MTIME_FILE="/tmp/toka-watch-mtimes.$$"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dev) DEV_MODE=true; shift ;;
        --check-only) CHECK_ONLY=true; shift ;;
        --poll) POLL_INTERVAL="$2"; shift 2 ;;
        -I) ARGS_I+=("$1" "$2"); shift 2 ;;
        --)
            shift
            while [[ $# -gt 0 && "$1" != "--" ]]; do
                WATCH_FILES+=("$1"); shift
            done
            [[ "$1" == "--" ]] && shift
            SERVER_ARGS=("$@")
            break
            ;;
        *) WATCH_FILES+=("$1"); shift ;;
    esac
done

if [[ ${#WATCH_FILES[@]} -eq 0 ]]; then
    echo "Usage: toka-watch [--dev] [--check-only] [-I dir ...] file.tk [-- --server-args]"
    exit 1
fi

OUT_FILE="${WATCH_FILES[0]%.tk}"
[[ "$OUT_FILE" == "${WATCH_FILES[0]}" ]] && OUT_FILE="a.out"

# --- Change detection ---

if command -v fswatch &>/dev/null; then
    wait_for_change() {
        fswatch -1 "${WATCH_FILES[@]}" 2>/dev/null
    }
    DETECT_METHOD="fswatch"
else
    get_mtime() {
        if [[ "$(uname)" == "Darwin" ]]; then
            stat -f "%m" "$1" 2>/dev/null || echo "0"
        else
            stat -c "%Y" "$1" 2>/dev/null || echo "0"
        fi
    }
    save_mtimes() {
        > "$MTIME_FILE"
        for f in "${WATCH_FILES[@]}"; do
            echo "$f|$(get_mtime "$f")" >> "$MTIME_FILE"
        done
    }
    files_changed() {
        for f in "${WATCH_FILES[@]}"; do
            local old_mtime
            old_mtime=$(grep "^$f|" "$MTIME_FILE" 2>/dev/null | cut -d'|' -f2)
            local new_mtime
            new_mtime=$(get_mtime "$f")
            if [[ "$new_mtime" != "$old_mtime" ]]; then
                save_mtimes
                return 0
            fi
        done
        return 1
    }
    wait_for_change() {
        files_changed && return 0
        sleep "$POLL_INTERVAL"
        return 1
    }
    DETECT_METHOD="poll (${POLL_INTERVAL}s)"
    save_mtimes
fi

# --- Server lifecycle ---

cleanup() {
    stop_server
    rm -f "$MTIME_FILE"
    echo "👋 Bye"
}
trap cleanup EXIT INT TERM

stop_server() {
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "   🛑 Stopping server (PID $SERVER_PID)"
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
        SERVER_PID=""
    fi
}

start_server() {
    [[ $DEV_MODE == false ]] && return
    echo "   🚀 Starting: ./$OUT_FILE ${SERVER_ARGS[@]:+${SERVER_ARGS[@]}}"
    "./$OUT_FILE" "${SERVER_ARGS[@]:+${SERVER_ARGS[@]}}" > /tmp/toka-watch-server.log 2>&1 &
    SERVER_PID=$!
    sleep 1
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "   ❌ Server died. Log:"
        cat /tmp/toka-watch-server.log 2>/dev/null
    else
        echo "   PID: $SERVER_PID"
    fi
}

compile() {
    local ts
    ts=$(date '+%H:%M:%S')
    
    if [[ $CHECK_ONLY == true ]]; then
        echo "[$ts] 🔍 Type-checking..."
        "$TOKAC" --check-only "${ARGS_I[@]}" "${WATCH_FILES[@]}" 2>&1
    else
        echo "[$ts] 🔨 Compiling..."
        "$TOKAC" -o "$OUT_FILE" "${ARGS_I[@]}" "${WATCH_FILES[@]}" 2>&1
    fi
    
    local rc=$?
    if [[ $rc -eq 0 ]]; then
        echo "   ✅ OK"
        return 0
    else
        echo "   ❌ Failed (exit $rc)"
        return 1
    fi
}

# --- Main ---

echo "═══════════════════════════════════"
echo "  toka-watch"
echo "  Watch:  ${WATCH_FILES[*]}"
echo "  Mode:   $([[ $DEV_MODE == true ]] && echo 'DEV (hot reload)' || echo 'CHECK')"
echo "  Detect: $DETECT_METHOD"
echo "═══════════════════════════════════"
echo ""

# Initial run
if compile; then
    start_server
fi

# Watch loop
while true; do
    wait_for_change
    
    if [[ "$DETECT_METHOD" == "poll" ]] && ! files_changed; then
        continue
    fi
    
    [[ $DEV_MODE == true ]] && stop_server
    compile && start_server || true
done
