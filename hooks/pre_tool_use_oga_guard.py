#!/usr/bin/env python3
"""
pre_tool_use_oga_guard.py — PreToolUse hook that structurally prevents Oga
(the loop-team orchestrator) from writing code directly without first dispatching
a sub-agent via the Agent tool.

Fires BEFORE Write/Edit/NotebookEdit executes. Not bypassable by user interrupt
(unlike the Stop hook, which fires at turn end).

Only activates when the loop-team skill is in scope (detected from transcript).
"""
import json, sys, os, re, time

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

tool_name = data.get("tool_name", "")
WORKER_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}
if tool_name not in WORKER_TOOLS:
    sys.exit(0)

# Only gate code files — not docs, markdown, fixtures, env files
tool_input = data.get("tool_input", {})
file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
CODE_EXT = re.compile(
    r'\.(py|ts|tsx|js|jsx|go|rs|java|rb|sh|php|cpp|cc|c|h|swift|kt|css|vue|yaml|yml|json|sql)$'
    r'|dockerfile$|makefile$|skill\.md$',
    re.I
)
if not CODE_EXT.search(os.path.basename(file_path)):
    sys.exit(0)

# Read transcript
transcript_path = data.get("transcript_path")
if not transcript_path or not os.path.exists(transcript_path):
    sys.exit(0)

try:
    events = [json.loads(l) for l in open(transcript_path, encoding="utf-8").read().splitlines() if l.strip()]
except Exception:
    sys.exit(0)

# Only enforce when the loop-team orchestrator's playbook is actually loaded in
# THIS transcript (H-GUARD-SUBAGENT fix, fix_plan.md). The injected available-
# skills list mentions oga/loop-team in EVERY session -- including Coder
# sub-agents -- so those words alone must never arm the guard. Detection keys
# on orchestrator.md content instead. Markers are built dynamically so a
# session that merely READS this file (or its tests) never self-arms.
_M_OGA = "you are " + "**oga**"
_M_PLAYBOOK = "orchestrator " + "playbook"
session_blob = json.dumps(events).lower()
loop_team_active = (_M_OGA in session_blob) or (_M_PLAYBOOK in session_blob)
if not loop_team_active:
    sys.exit(0)

# --- In-flight sub-agent detection (H-LT6 fix) ---
# The turn-lookback approach raced the main transcript's turn boundaries: any
# interleaved task-notification / stop-hook-feedback opens a new Agent-less
# turn and re-blocks a still-running Coder. The causal condition is not "how
# recent was a dispatch" but whether a dispatched Agent tool_use has been
# RETIRED yet by a completion notification (either channel).
TOOL_USE_ID_RE = re.compile(r'<tool-use-id>([^<]+)</tool-use-id>')
STALE_SECONDS = 60 * 60
STALE_EVENT_FALLBACK = 400


def _content(e):
    m = e.get("message")
    if isinstance(m, dict):
        return m.get("content", [])
    return e.get("content", [])


def _role(e):
    return e.get("role") or (
        e.get("message", {}).get("role", "") if isinstance(e.get("message"), dict) else ""
    )


def _timestamp(e):
    ts = e.get("timestamp")
    if ts is None and isinstance(e.get("message"), dict):
        ts = e["message"].get("timestamp")
    return ts


def _is_queue_operation(e):
    return e.get("type") == "queue-operation"


def _event_text_blob(e):
    """Flatten an event to a string for <tool-use-id> tag scanning."""
    return json.dumps(e)


# 1) Collect dispatched Agent tool_use ids, each with its dispatch index and
#    timestamp (for the staleness cap).
dispatched = {}  # tool_use_id -> {"index": int, "timestamp": ...}
for i, e in enumerate(events):
    c = _content(e)
    if not isinstance(c, list):
        continue
    for p in c:
        if isinstance(p, dict) and p.get("type") == "tool_use" and p.get("name") == "Agent":
            tid = p.get("id") or p.get("tool_use_id")
            if tid:
                dispatched[tid] = {"index": i, "timestamp": _timestamp(e)}

# 2) Scan BOTH channels (role:user events and queue-operation events) for
#    embedded <tool-use-id> tags. A tag only retires a dispatch if its id is
#    in the dispatched-Agent-id set — ids from Monitor/background-Bash
#    notifications never match an Agent id (opaque unique tokens) so they
#    cannot spoof a retirement.
retired = set()
for e in events:
    role = _role(e)
    if role != "user" and not _is_queue_operation(e):
        continue
    for tid in TOOL_USE_ID_RE.findall(_event_text_blob(e)):
        if tid in dispatched:
            retired.add(tid)

# 3) Staleness cap: a dispatch with no retirement in either channel is only
#    "in flight" if it is recent enough. Prefer event timestamps; fall back
#    to an event-count window when timestamps are absent.
now = time.time()
last_index = len(events) - 1


def _is_stale(info):
    ts = info["timestamp"]
    if ts:
        try:
            # Support both epoch numbers and ISO-8601 strings.
            if isinstance(ts, (int, float)):
                dispatch_time = float(ts)
            else:
                import datetime
                s = str(ts)
                if s.endswith("Z"):
                    s = s[:-1] + "+00:00"
                dispatch_time = datetime.datetime.fromisoformat(s).timestamp()
            return (now - dispatch_time) > STALE_SECONDS
        except Exception:
            pass
    # Fallback: no usable timestamp -- use event-count window.
    return (last_index - info["index"]) > STALE_EVENT_FALLBACK


in_flight_ids = [
    tid for tid, info in dispatched.items()
    if tid not in retired and not _is_stale(info)
]

# --- Best-effort debug log (never affects the decision) ---
# AC-RH5 (residual_holes_spec.md): rows also carry caller-identity evidence --
# session_id (verbatim), transcript_basename (basename ONLY; never a home/tmp
# directory path in the log), and payload_keys (sorted top-level stdin keys,
# VALUES redacted). Logging only; the allow/deny decision above is unchanged.
try:
    gate_dir = os.environ.get("LOOP_GATE_DIR") or os.path.expanduser("~/.loop-gate")
    os.makedirs(gate_dir, exist_ok=True)
    with open(os.path.join(gate_dir, "oga_guard_debug.jsonl"), "a", encoding="utf-8") as dbg:
        dbg.write(json.dumps({
            "ts": now,
            "tool": tool_name,
            "file": file_path,
            "decision": "allow" if in_flight_ids else "deny",
            "in_flight_ids": in_flight_ids,
            "session_id": data.get("session_id", ""),
            "transcript_basename": os.path.basename(transcript_path or ""),
            "payload_keys": sorted(data.keys()),
        }) + "\n")
except Exception:
    pass

if in_flight_ids:
    sys.exit(0)  # A dispatched sub-agent is still in flight — allow the Write/Edit

# Block: no in-flight sub-agent
# AC4 (plan_check_spec.md): deny-message text only — no change to the
# allow/deny decision above. Three content points, in order: (i) the
# orchestrator purpose (dispatch a Coder sub-agent rather than edit code
# inline); (ii) misfire guidance for the case where the blocked actor is
# ITSELF a dispatched sub-agent (fix_plan.md H-GUARD-4 / H-LT6) — note the
# misfire in the final report, complete the assigned work with permitted
# tools, and do NOT dispatch another sub-agent in response (the historical
# runaway-delegation-chain failure mode); (iii) this guard is an advisory
# role-collapse check, not a security boundary (Bash writes bypass it).
basename = os.path.basename(file_path)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": (
            f"[OGA GUARD] {tool_name}('{basename}') blocked. In a loop-team session, "
            "the orchestrator (Oga) must dispatch a Coder sub-agent (Agent tool) rather "
            "than edit code inline: dispatch Agent(description='Coder for ...', "
            "prompt='...') first, then the Write/Edit will be allowed. "
            "If you are seeing this message as a DISPATCHED SUB-AGENT (e.g. a Coder "
            "already assigned this work), this block is a known misfire (fix_plan.md "
            "H-GUARD-4 / H-LT6): note the misfire in your final report and complete the "
            "assigned work using your permitted tools — do NOT dispatch another sub-agent "
            "in response, as that produces runaway delegation chains. "
            "This guard is an advisory role-collapse check, not a security boundary — "
            "it can be bypassed via Bash, so it is not relied on as one."
        )
    }
}))
sys.exit(0)
