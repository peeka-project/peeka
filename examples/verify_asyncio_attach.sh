#!/bin/bash
set -euo pipefail

# Resolve repo root
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Create temp dir
TMP="$(mktemp -d)"
READY_FILE="$TMP/ready"
JSONL="$TMP/watch.jsonl"
TARGET_PID=""

# Cleanup function - runs on any exit
cleanup() {
    local exit_code=$?
    
    # Attempt detach first (before killing target)
    if [[ -n "$TARGET_PID" ]]; then
        uv run python -m peeka.cli detach 2>/dev/null || true
    fi
    
    # Kill target process if still running
    if [[ -n "$TARGET_PID" ]] && kill -0 "$TARGET_PID" 2>/dev/null; then
        kill -TERM "$TARGET_PID" 2>/dev/null || true
        sleep 2
        kill -9 "$TARGET_PID" 2>/dev/null || true
    fi
    
    # Clean up temp dir
    rm -rf "$TMP"
    
    exit $exit_code
}

trap cleanup EXIT

# Launch target process in background
PEEKA_TEST_READY_FILE="$READY_FILE" uv run python examples/asyncio_attach_target.py --duration 0 > /dev/null 2>&1 &
TARGET_WRAPPER_PID=$!

# Poll for ready file (up to 15s)
POLL_COUNT=0
MAX_POLLS=150  # 15s with 0.1s intervals
while [[ $POLL_COUNT -lt $MAX_POLLS ]]; do
    if [[ -f "$READY_FILE" ]]; then
        break
    fi
    sleep 0.1
    POLL_COUNT=$((POLL_COUNT + 1))
done

if [[ ! -f "$READY_FILE" ]]; then
    echo "ERROR: Target process did not create ready file within 15s" >&2
    kill -9 "$TARGET_WRAPPER_PID" 2>/dev/null || true
    exit 2
fi

# Read PID from ready file
TARGET_PID="$(cat "$READY_FILE")"

# Attach to target
if ! timeout 30 uv run python -m peeka.cli attach "$TARGET_PID" > /dev/null 2>&1; then
    echo "ERROR: Failed to attach to target process $TARGET_PID" >&2
    exit 1
fi

# Run watch command (no --pid flag - watch resolves attached PID from agent socket)
if ! timeout 60 uv run python -m peeka.cli watch "examples.asyncio_attach_target.handle_request" -n 3 > "$JSONL" 2>&1; then
    echo "ERROR: watch command timed out or failed" >&2
    cat "$JSONL" >&2
    exit 1
fi

# Assertion 1: watch_started event
if ! grep -F '"event":"watch_started"' "$JSONL" > /dev/null; then
    echo "ERROR: Missing watch_started event" >&2
    cat "$JSONL" >&2
    exit 1
fi

# Assertion 2: is_coroutine_function is true
if ! grep -F '"is_coroutine_function":true' "$JSONL" > /dev/null; then
    echo "ERROR: is_coroutine_function not true" >&2
    cat "$JSONL" >&2
    exit 1
fi

# Assertion 3: at least one observation event
OBSERVATION_COUNT=$(grep -F '"type":"observation"' "$JSONL" | wc -l)
if [[ $OBSERVATION_COUNT -lt 1 ]]; then
    echo "ERROR: No observation events found (count: $OBSERVATION_COUNT)" >&2
    cat "$JSONL" >&2
    exit 1
fi

# Assertion 4: success is true
if ! grep -F '"success":true' "$JSONL" > /dev/null; then
    echo "ERROR: success not true" >&2
    cat "$JSONL" >&2
    exit 1
fi

# Assertion 5: cost field present
if ! grep -F '"cost":' "$JSONL" > /dev/null; then
    echo "ERROR: cost field missing" >&2
    cat "$JSONL" >&2
    exit 1
fi

# Assertion 6: at least one observation has non-null returnObj
if ! grep -F '"type":"observation"' "$JSONL" | grep -v '"returnObj":null' > /dev/null; then
    echo "ERROR: No observation with non-null returnObj" >&2
    cat "$JSONL" >&2
    exit 1
fi

# Detach from target
if ! timeout 15 uv run python -m peeka.cli detach > /dev/null 2>&1; then
    echo "ERROR: Failed to detach from target process" >&2
    exit 1
fi

# Kill target with SIGTERM and wait
kill -TERM "$TARGET_PID" 2>/dev/null || true
sleep 8

# Success
echo "VERIFY_OK"
exit 0
