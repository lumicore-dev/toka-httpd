#!/usr/bin/env bash
# toka-smoke - HTTP smoke test runner
#
# Usage:
#   toka-smoke demo.tk                    # Auto: compile + start + test
#   toka-smoke --server ./my_server       # Already compiled
#
# Inline tests:
#   toka-smoke --server ./srv --test "/hello" "Hello" 200 --test "/404" "Not Found" 404

set -euo pipefail

PORT="${PORT:-8080}"
BASE="http://localhost:$PORT"
SERVER_PID=""
TESTS=()
SERVER_BIN=""
SOURCE_FILE=""
TOKAC="${TOKAC:-./build/bin/tokac}"

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --server) SERVER_BIN="$2"; shift 2 ;;
            --port) PORT="$2"; BASE="http://localhost:$PORT"; shift 2 ;;
            --test)
                if [[ $# -lt 4 ]]; then
                    echo "❌ --test needs 3 args: url expected_text expected_status"
                    exit 1
                fi
                TESTS+=("$2|$3|$4")
                shift 4
                ;;
            -I)
                ARGS_I+=("$1" "$2")
                shift 2
                ;;
            *) SOURCE_FILE="$1"; shift ;;
        esac
    done
}

parse_args "$@"

if [[ -n "$SOURCE_FILE" ]]; then
    SERVER_BIN="${SOURCE_FILE%.tk}"
    echo "🔨 Compiling $SOURCE_FILE..."
    "$TOKAC" -o "$SERVER_BIN" "${ARGS_I[@]}" "$SOURCE_FILE" 2>&1
    echo "   ✅ Compiled to $SERVER_BIN"
fi

if [[ -z "$SERVER_BIN" ]]; then
    echo "❌ No server binary specified (use --server or pass a .tk file)"
    exit 1
fi

# Start server
echo "🚀 Starting $SERVER_BIN on :$PORT..."
"./$SERVER_BIN" > /tmp/toka-smoke.log 2>&1 &
SERVER_PID=$!
sleep 2

if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "❌ Server failed to start"
    cat /tmp/toka-smoke.log
    exit 1
fi

trap "kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null; echo '   🛑 Server stopped'" EXIT INT TERM

# Run tests
PASS=0
FAIL=0
echo ""
echo "═══════════════════════════════════"
echo "  Smoke Tests — $BASE"
echo "═══════════════════════════════════"

for test in "${TESTS[@]}"; do
    IFS='|' read -r url expected status <<< "$test"
    
    resp=$(curl -s -o /tmp/toka-smoke-resp.txt -w "%{http_code}" --max-time 3 "$BASE$url" 2>/dev/null)
    body=$(cat /tmp/toka-smoke-resp.txt 2>/dev/null)
    
    status_ok=false; text_ok=false
    [[ "$resp" == "$status" ]] && status_ok=true
    echo "$body" | grep -q "$expected" && text_ok=true
    
    if $status_ok && $text_ok; then
        echo "  ✅ $url → $resp, '$expected' ✓"
        PASS=$((PASS + 1))
    else
        echo "  ❌ $url"
        $status_ok || echo "      status: got $resp, want $status"
        $text_ok || echo "      body: missing '$expected', got '${body:0:80}'"
        FAIL=$((FAIL + 1))
    fi
done

echo ""
echo "═══════════════════════════════════"
echo "  $PASS passed, $FAIL failed"
echo "═══════════════════════════════════"
exit $FAIL
