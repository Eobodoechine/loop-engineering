#!/usr/bin/env python3
"""
subagent_stop_gate.py — SubagentStop hook that writes a flag file when a
plan-check Verifier sub-agent completes with LOOP_GATE: PLAN_PASS as its
last non-empty output line.

INSTALL: hooks.SubagentStop in ~/.claude/settings.json
"""
import sys
import json
import os
import time

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)

# AC3 (plan_check_spec.md, H-GUARD-SUBAGENT-2): diagnostics for the credit
# path. Every invocation that successfully parses its stdin payload (i.e.
# reaches this point) appends one best-effort JSON line to
# $LOOP_GATE_DIR/subagent_gate_debug.jsonl, mirroring the existing
# oga_guard_debug.jsonl pattern, so the no-flag-written path is diagnosable
# instead of silent.
_dbg_session_id = None
_dbg_agent_id = None
_dbg_last_line = None
_dbg_wrote_flag = False

try:
    session_id = data.get("session_id")
    agent_id = data.get("agent_id")
    lam = data.get("last_assistant_message")

    _dbg_session_id = session_id if isinstance(session_id, str) else None
    _dbg_agent_id = agent_id if isinstance(agent_id, str) else None

    # last_assistant_message must be a non-None string
    if lam is None or not isinstance(lam, str):
        pass
    else:
        lines = [x.strip() for x in lam.split('\n') if x.strip()]
        if lines:
            last_line = lines[-1].lower()
            _dbg_last_line = lines[-1][:80]

            if last_line == 'loop_gate: plan_pass' and session_id and isinstance(session_id, str) and session_id.strip():
                aid = agent_id if (agent_id and str(agent_id).strip()) else 'unknown'
                try:
                    gate_dir = os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
                    os.makedirs(gate_dir, exist_ok=True)
                    flag_path = os.path.join(gate_dir, f"{session_id}_{aid}.verifier_pass")
                    open(flag_path, "w").close()
                    _dbg_wrote_flag = True
                except Exception:
                    pass
except Exception:
    pass

try:
    gate_dir = os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
    os.makedirs(gate_dir, exist_ok=True)
    debug_path = os.path.join(gate_dir, "subagent_gate_debug.jsonl")
    with open(debug_path, "a", encoding="utf-8") as dbg:
        dbg.write(json.dumps({
            "ts": time.time(),
            "session_id": _dbg_session_id,
            "agent_id": _dbg_agent_id,
            "last_line": _dbg_last_line,
            "wrote_flag": _dbg_wrote_flag,
        }) + "\n")
except Exception:
    pass

sys.exit(0)
