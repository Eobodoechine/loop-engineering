#!/usr/bin/env bash
# session_start.sh — Loop-team SessionStart hook
# Loads orchestrator dispatch constraints into additionalContext on session start.
#
# Behaviour:
#   - If constraints file exists: exit 0, emit JSON with hookSpecificOutput.additionalContext
#   - If constraints file is missing: exit 0 silently (empty stdout)
#
# The constraints file path can be overridden via LOOP_CONSTRAINTS_FILE env var
# (used for test isolation).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONSTRAINTS_FILE="${LOOP_CONSTRAINTS_FILE:-${SCRIPT_DIR}/orchestrator-constraints.txt}"

if [ ! -f "$CONSTRAINTS_FILE" ]; then
  # File absent — exit 0 silently (no output)
  exit 0
fi

# Use python3 to read and JSON-encode safely (handles quotes, newlines, etc.)
python3 - "$CONSTRAINTS_FILE" <<'PYEOF'
import json, sys

path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    constraints = f.read()

payload = {
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": constraints
    }
}
print(json.dumps(payload))
PYEOF
