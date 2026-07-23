#!/usr/bin/env python3
"""
subagent_stop_gate.py — SubagentStop hook that writes a flag file when a
plan-check Verifier sub-agent completes with LOOP_GATE: PLAN_PASS as its
last non-empty output line.

Second, independent detection path for the SAME flag-write responsibility
(spec.md H-TRACE-WIRING-1, Required-fix Problem 2): a Workflow+`schema`
plan-check-verifier dispatch is forced to call a `StructuredOutput` tool and
frequently has no free-text final assistant message at all, so the free-text
check above can never fire for it. This path walks the transcript's JSONL
events structurally (matching hooks/loop_stop_guard.py's parsing idiom),
finds the LAST `StructuredOutput` tool_use block, and inspects its
`input.loop_gate` field. A 3-tier precedence rule (see below) resolves which
path's verdict actually governs the write.

Third responsibility (independent of the flag-write above): on every
SubagentStop completion, best-effort append one trace.jsonl event under the
resolved run directory (bare `runs/<name>/` or `loop-team/runs/<name>/`, see
spec.md, 2026-07-02_auto-trace-logging and H-TRACE-WIRING-1) — fully
fail-open, never affects the flag-write logic or this hook's exit code.

Fourth responsibility (independent of the three above — spec.md
H-SUBAGENT-COMMIT-GATE-1): on every SubagentStop firing, scan THIS
sub-agent's own transcript_content for a raw `git commit` that bypasses
`commit_diff_reread.py` and touches a scope-listed shared framework file,
using the SAME shared, importable `find_commit_scope_violations()` function
(hooks/commit_scope_scan.py) that `loop_stop_guard.py`'s own commit-scope
gate uses for Oga's turn. On a hit, write a
`{session_id}_{agent_id}.commit_violation` flag under `$LOOP_GATE_DIR`
(content: the JSON-serialized violation list) via the SAME
`_write_flag_if_guarded` guard used for `.verifier_pass`, so
`loop_stop_guard.py`'s own Stop hook can block Oga's turn on it — a
sub-agent's `SubagentStop` block only affects the ALREADY-FINISHED
sub-agent's own turn, never Oga's, so this is a detection-and-signal
responsibility, not a blocking one. Wrapped in its own try/except, isolated
from tiers 1-3 and trace-logging exactly like this file's other
responsibilities.

Fifth responsibility (independent of the four above — Evidence-Gate Phase 4
Part B, spec.md loop-team/runs/2026-07-09_evidence-gate-phase4/specs/
spec.md "Part B — sub-agent-authored closure detection"): on every
SubagentStop firing, scan THIS sub-agent's own transcript_content for a
Write/Edit/MultiEdit that touched the closure-relevant portion (heading
line or Proof: span) of a `CLOSED` heading in `fix_plan.md`, using the
shared, importable `closure_touch_scan.find_touched_closed_headings()`
function, then validate each touched heading against the CURRENT on-disk
`fix_plan.md` via `fixplan_closure_lint.check_single_heading(...,
advisory=True)` — the LIVE-git-worktree-reading checks (staleness,
dirty-worktree) are routed to an advisory `warnings` list rather than the
blocking `messages` list, matching Parts C/D/E's own hook-path default (a
sub-agent's SubagentStop hook has no human present to judge live,
shared-worktree context, same rationale as those gates). On any heading
whose `messages` is non-empty, write a `{session_id}_{agent_id}.closure_violation`
flag under `$LOOP_GATE_DIR` (content: a JSON-serialized list of
`{"heading", "messages", "warnings"}` dicts, one per still-blocking touched
heading) via the SAME `_write_flag_if_guarded` guard used for
`.verifier_pass`/`.commit_violation`, so `loop_stop_guard.py`'s own Part D
(a later micro-step) can read it and block Oga's turn on it — same
detection-and-signal rationale as the Fourth responsibility above (a
sub-agent's own SubagentStop block can never affect Oga's turn directly).
`fix_plan.md`'s location is resolved independently, `__file__`-relative to
THIS file's own location (this repo's real layout: `<repo_root>/hooks/
subagent_stop_gate.py` and `<repo_root>/fix_plan.md`, one level up from
`hooks/`) — no dependency on any per-micro-step-target mechanism. Wrapped in
its own try/except, isolated from tiers 1-3, the Fourth responsibility, and
trace-logging exactly like this file's other responsibilities.

File-level structure (spec.md H-TRACE-WIRING-1 "REQUIRED FILE
RESTRUCTURING"): `transcript_content` is read ONCE at the top of this file,
guarded by its own try/except so an unreadable transcript degrades to "no
content" rather than crashing — never re-opened anywhere below. The
flag-write block (tiers 1-3) and the trace-logging block are each still
independently wrapped in their own try/except, per this file's existing
per-responsibility isolation discipline. The debug-log write is relocated to
AFTER all 3 tiers have been evaluated so its `wrote_flag` field always
reflects the true final outcome, never stale tier-1/tier-2-only state.

INSTALL: hooks.SubagentStop in ~/.claude/settings.json
"""
import sys
import json
import os
import re
import time

try:
    from codex_hook_stdin_capture import capture_once as _capture_codex_stdin_once
except Exception:
    def _capture_codex_stdin_once(_raw_stdin, _source_hook):
        return

try:
    _RAW_STDIN = sys.stdin.read()
    _capture_codex_stdin_once(_RAW_STDIN, "subagent_stop_gate.py")
    data = json.loads(_RAW_STDIN)
except Exception:
    sys.exit(0)

# ── ONE-TIME transcript read (spec.md H-TRACE-WIRING-1 REQUIRED FILE
# RESTRUCTURING) ────────────────────────────────────────────────────────────
# transcript_content is read here, ONCE, before the flag-write block, the
# tier-2/tier-3 detection logic, and the debug-log write all run. Both the
# flag-write responsibility (tiers 1-3) and the trace-logging responsibility
# below consume this SAME string; the transcript file is never re-opened.
# Codex SubagentStop payloads include both the parent transcript_path and
# agent_transcript_path. For sub-agent-owned gates, agent_transcript_path is
# authoritative when present; scanning the parent transcript cross-contaminates
# flags with Oga's own tool calls.
# A read failure (missing path, unreadable file, missing/non-string field)
# degrades to "no content" — same fail-open behavior as before this
# restructuring — and must never crash the hook.
transcript_content = None
try:
    _agent_transcript_path = data.get("agent_transcript_path")
    if isinstance(_agent_transcript_path, str) and _agent_transcript_path:
        _transcript_path = _agent_transcript_path
    else:
        _transcript_path = data.get("transcript_path")
    if isinstance(_transcript_path, str) and _transcript_path:
        with open(_transcript_path, "r", encoding="utf-8") as _tf:
            transcript_content = _tf.read()
except Exception:
    transcript_content = None

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
# H-SUBAGENT-COMMIT-GATE-1 (spec item 2, "Required first step"): add `cwd`
# to the fields subagent_gate_debug.jsonl already logs, so a real
# SubagentStop firing's actual payload can be confirmed to populate it (or
# not) during manual testing — independent of whatever that live result
# turns out to be (AC-CWD covers the fallback branch with a direct unit
# test regardless).
_dbg_cwd = None


def _write_flag_if_guarded(session_id, agent_id, ext="verifier_pass", content=""):
    """Shared flag-write guard (spec.md H-TRACE-WIRING-1 Required-fix
    Problem 2, "Flag-write guard reuse"): whichever tier decides to write
    the flag (tier 1 or tier 3 — tier 2 never writes), the actual write goes
    through this SAME guarded logic — non-empty session_id required, else no
    flag is written at all; agent_id falls back to the literal string
    "unknown" when missing/empty/whitespace-only. Returns True iff the flag
    was actually written.

    Signature extended (H-SUBAGENT-COMMIT-GATE-1, spec item 2, "Precision
    correction"): `ext`/`content` are optional, additive parameters. The two
    EXISTING call sites (tier 1, tier 3) pass NO extra arguments, so their
    behavior (an EMPTY `.verifier_pass` file) is byte-for-byte unchanged —
    see AC7b. The new 4th responsibility below calls this with
    `ext="commit_violation"` and `content=json.dumps(violations)`."""
    if not (session_id and isinstance(session_id, str) and session_id.strip()):
        return False
    aid = agent_id if (agent_id and str(agent_id).strip()) else "unknown"
    try:
        gate_dir = os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
        os.makedirs(gate_dir, exist_ok=True)
        flag_path = os.path.join(gate_dir, f"{session_id}_{aid}.{ext}")
        open(flag_path, "w").write(content)
        return True
    except Exception:
        return False


def _last_structured_output_loop_gate(content):
    """Walk `content` as JSONL (matching hooks/loop_stop_guard.py's parsing
    idiom: json.loads per line, message.content -> list of parts, a
    tool_use block is a dict with type == 'tool_use'). Return the `input`
    dict of the LAST tool_use block whose name == 'StructuredOutput', or
    None if no such block exists anywhere in the transcript.

    Per-line exception isolation (spec.md Required-fix Problem 2, "Per-line
    exception isolation"): each individual line's json.loads is wrapped in
    its OWN try/except — matching loop_stop_guard.py's lines 46-48 pattern
    literally — so one malformed/torn line can never abort the walk of the
    other, well-formed lines."""
    if not content:
        return None

    def _content_of(e):
        m = e.get("message")
        if isinstance(m, dict) and "content" in m:
            return m["content"]
        return e.get("content")

    last_input = None
    for ln in content.splitlines():
        try:
            e = json.loads(ln)
        except Exception:
            continue
        try:
            if not isinstance(e, dict):
                continue
            c = _content_of(e)
            if not isinstance(c, list):
                continue
            for p in c:
                if (
                    isinstance(p, dict)
                    and p.get("type") == "tool_use"
                    and p.get("name") == "StructuredOutput"
                ):
                    inp = p.get("input")
                    last_input = inp if isinstance(inp, dict) else {}
        except Exception:
            continue
    return last_input


try:
    session_id = data.get("session_id")
    agent_id = data.get("agent_id")
    lam = data.get("last_assistant_message")

    _dbg_session_id = session_id if isinstance(session_id, str) else None
    _dbg_agent_id = agent_id if isinstance(agent_id, str) else None

    last_line = None
    if isinstance(lam, str):
        _lam_lines = [x.strip() for x in lam.split('\n') if x.strip()]
        if _lam_lines:
            last_line = _lam_lines[-1].lower()
            _dbg_last_line = _lam_lines[-1][:80]

    # 3-tier precedence rule (spec.md H-TRACE-WIRING-1 Required-fix
    # Problem 2, "Precedence rule when both detection paths could apply"):
    #   tier 1: explicit free-text "loop_gate: plan_pass" last line -> write.
    #   tier 2: explicit free-text "loop_gate: plan_fail" last line -> do
    #           NOT write, regardless of any StructuredOutput signal.
    #   tier 3: neither tier 1 nor tier 2 matched -> fall back to the
    #           StructuredOutput path's own verdict (last block, missing
    #           loop_gate key treated as NOT-PASS).
    if last_line == 'loop_gate: plan_pass':
        # Tier 1 — extract spec hash from last_assistant_message and store in flag content.
        _t1_hash = ""
        if isinstance(lam, str):
            _t1_m = re.search(r"\bREVIEWED_SPEC_SHA256=([0-9a-f]{64})", lam)
            if _t1_m:
                _t1_hash = _t1_m.group(1)
        if _write_flag_if_guarded(session_id, agent_id, content=_t1_hash):
            _dbg_wrote_flag = True
    elif last_line == 'loop_gate: plan_fail':
        # Tier 2 — explicit free-text FAIL is authoritative; suppresses any
        # StructuredOutput signal. Not a fault; logged as a normal non-match.
        pass
    else:
        # Tier 3 — StructuredOutput fallback.
        so_input = _last_structured_output_loop_gate(transcript_content)
        if isinstance(so_input, dict) and so_input.get("loop_gate") == "PLAN_PASS":
            _t3_hash = str(so_input.get("reviewed_spec_sha256", "") or "")
            if _write_flag_if_guarded(session_id, agent_id, content=_t3_hash):
                _dbg_wrote_flag = True
except Exception:
    pass

# ── Fourth responsibility (independent of tiers 1-3 and trace-logging below,
# H-SUBAGENT-COMMIT-GATE-1 spec item 2): on every SubagentStop firing, call
# find_commit_scope_violations(...) against the SAME tool_uses/tool_results
# extracted from THIS sub-agent's own transcript_content (already read once
# at the top of this file — reuse, do not re-open). On a hit, write a
# {session_id}_{agent_id}.commit_violation flag under $LOOP_GATE_DIR so
# loop_stop_guard.py's own Stop hook (Layer 1) can block Oga's turn on it.
#
# Wrapped in its OWN try/except, matching this file's existing
# per-responsibility isolation discipline — ANY exception here must never
# affect the flag-write tiers 1-3 above or the trace-logging responsibility
# below, and must never change this hook's exit code (always sys.exit(0),
# unchanged).
try:
    import sys as _cv_sys, os as _cv_os
    _cv_sys.path.insert(0, _cv_os.path.dirname(_cv_os.path.abspath(__file__)))
    from commit_scope_scan import find_commit_scope_violations as _cv_find

    # Re-derive session_id/agent_id independently here (rather than relying
    # on the tiers-1-3 try block's locals) so this responsibility is fully
    # self-contained per the file's own per-responsibility isolation rule.
    _cv_session_id = data.get("session_id")
    _cv_agent_id = data.get("agent_id")

    # Target resolution for the sub-agent case is SIMPLER than Oga's own
    # micro-step-armed-target logic: use data.get("cwd") directly if it is
    # present, non-empty, and a string. Do NOT import micro_step_gates.py's
    # _activation()/_LAST_ACTIVATION for this — that mechanism answers "what
    # is Oga's CURRENTLY-ARMED micro-step target," a different question from
    # "what directory did THIS sub-agent's Bash commands actually run in."
    _cv_cwd = data.get("cwd")
    _dbg_cwd = _cv_cwd if isinstance(_cv_cwd, str) else None
    if isinstance(_cv_cwd, str) and _cv_cwd.strip():
        _cv_target = _cv_cwd
    else:
        # Fallback: cwd missing/empty/non-string — mirror loop_stop_guard.py's
        # own fallback (this file's __file__-relative repo path).
        _cv_target = _cv_os.path.realpath(_cv_os.path.join(
            _cv_os.path.dirname(_cv_os.path.abspath(__file__)), ".."))

    # Construct tool_uses/tool_results from the sub-agent's own
    # transcript_content the same structural way loop_stop_guard.py already
    # does for Oga's own turn (message.content -> list of parts, filtering
    # type == "tool_use"/"tool_result") — but scoped to the ENTIRE sub-agent
    # transcript, not a turn-sliced subset (a sub-agent's whole transcript
    # IS the relevant unit here; it has no multi-turn "current turn" concept
    # the way Oga's session does).
    _cv_events = []
    if isinstance(transcript_content, str) and transcript_content:
        for _cv_ln in transcript_content.splitlines():
            try:
                _cv_events.append(json.loads(_cv_ln))
            except Exception:
                continue

    def _cv_content_of(e):
        m = e.get("message")
        if isinstance(m, dict) and "content" in m:
            return m["content"]
        return e.get("content")

    def _cv_parts(evs):
        for e in evs:
            c = _cv_content_of(e)
            if isinstance(c, list):
                for p in c:
                    if isinstance(p, dict):
                        yield p

    _cv_tool_uses = [p for p in _cv_parts(_cv_events) if p.get("type") == "tool_use"]
    _cv_tool_results = [p for p in _cv_parts(_cv_events) if p.get("type") == "tool_result"]

    _cv_violations = _cv_find(_cv_tool_uses, _cv_tool_results, _cv_target)
    if _cv_violations:
        _cv_payload = [
            {"sha": _cv_sha, "touched": _cv_touched}
            for _cv_sha, _cv_touched in _cv_violations
        ]
        _write_flag_if_guarded(
            _cv_session_id, _cv_agent_id, ext="commit_violation",
            content=json.dumps(_cv_payload))
except Exception:
    pass

# ── Fifth responsibility (independent of tiers 1-3, the Fourth
# responsibility above, and trace-logging below — Evidence-Gate Phase 4
# Part B, spec.md loop-team/runs/2026-07-09_evidence-gate-phase4/specs/
# spec.md "Part B — sub-agent-authored closure detection"): on every
# SubagentStop firing, scan THIS sub-agent's own transcript_content
# (already read once at the top of this file — reuse, do not re-open) for
# CLOSED heading(s) it genuinely touched (closure_touch_scan.
# find_touched_closed_headings), validate each touched heading against the
# CURRENT on-disk fix_plan.md (fixplan_closure_lint.check_single_heading,
# advisory=True — matching Parts C/D/E's hook-path default), and write a
# {session_id}_{agent_id}.closure_violation flag under $LOOP_GATE_DIR on
# any heading that still has a blocking `messages` entry, so
# loop_stop_guard.py's own Part D (a later micro-step) can read it and
# block Oga's turn on it.
#
# fix_plan.md's own target path is resolved independently, __file__-relative
# to THIS file's own location (theme 1's fix — no _rc_target/_msg_mod
# dependency; this repo's real layout is <repo_root>/hooks/
# subagent_stop_gate.py and <repo_root>/fix_plan.md, one level up from
# hooks/), matching fixplan_closure_lint.py's own _default_path()
# resolution.
#
# tool_uses are re-derived from transcript_content the SAME structural way
# the Fourth responsibility above does (message.content -> list of parts,
# filtering type == "tool_use") — this responsibility defines its OWN
# local helpers (`_cts_content_of`/`_cts_parts`) rather than reusing the
# Fourth responsibility's `_cv_content_of`/`_cv_parts` names, so this
# responsibility stays fully self-contained per the file's own
# per-responsibility isolation rule (an unrelated import failure inside the
# Fourth responsibility's own try block must never silently break this one,
# and vice versa).
#
# Wrapped in its OWN try/except, matching this file's existing
# per-responsibility isolation discipline — ANY exception here must never
# affect tiers 1-3, the Fourth responsibility, or the trace-logging
# responsibility below, and must never change this hook's exit code
# (always sys.exit(0), unchanged).
try:
    import sys as _cts_sys, os as _cts_os
    _cts_sys.path.insert(0, _cts_os.path.dirname(_cts_os.path.abspath(__file__)))
    from closure_touch_scan import find_touched_closed_headings as _cts_find_touched

    _cts_harness_dir = _cts_os.path.normpath(_cts_os.path.join(
        _cts_os.path.dirname(_cts_os.path.abspath(__file__)),
        "..", "loop-team", "harness"))
    _cts_sys.path.insert(0, _cts_harness_dir)
    from fixplan_closure_lint import check_single_heading as _cts_check_heading
    from status_claim_audit import (
        audit_fix_plan_content as _cts_status_audit,
        touched_ranges_for_tool_uses as _cts_status_touched_ranges,
    )

    # Re-derive session_id/agent_id independently here (rather than relying
    # on tiers-1-3's or the Fourth responsibility's own locals) so this
    # responsibility is fully self-contained per the file's own
    # per-responsibility isolation rule.
    _cts_session_id = data.get("session_id")
    _cts_agent_id = data.get("agent_id")

    # __file__-relative resolution ONLY (theme 1's fix): one level up from
    # hooks/, matching this repo's real layout (<repo_root>/fix_plan.md).
    _cts_target_path = _cts_os.path.join(
        _cts_os.path.dirname(_cts_os.path.abspath(__file__)), "..", "fix_plan.md")

    # Construct tool_uses from the sub-agent's own transcript_content the
    # same structural way the Fourth responsibility above does (its own
    # `_cv_events`/`_cv_content_of`/`_cv_parts`), independently re-derived
    # here rather than reused by name (see comment block above).
    _cts_events = []
    if isinstance(transcript_content, str) and transcript_content:
        for _cts_ln in transcript_content.splitlines():
            try:
                _cts_events.append(json.loads(_cts_ln))
            except Exception:
                continue

    def _cts_content_of(e):
        m = e.get("message")
        if isinstance(m, dict) and "content" in m:
            return m["content"]
        return e.get("content")

    def _cts_parts(evs):
        for e in evs:
            c = _cts_content_of(e)
            if isinstance(c, list):
                for p in c:
                    if isinstance(p, dict):
                        yield p

    _cts_tool_uses = [p for p in _cts_parts(_cts_events) if p.get("type") == "tool_use"]
    _cts_tool_results = [p for p in _cts_parts(_cts_events) if p.get("type") == "tool_result"]
    _cts_blocked_ids = set()
    _cts_result_ids = set()
    for _cts_tr in _cts_tool_results:
        _cts_tid = _cts_tr.get("tool_use_id") or _cts_tr.get("id")
        if not _cts_tid:
            continue
        _cts_result_ids.add(_cts_tid)
        _cts_txt = str(_cts_tr.get("content", "")).lower()
        if (_cts_tr.get("is_error") is True
                or "denied this tool call" in _cts_txt[:200]
                or _cts_txt.strip().startswith("hook pretooluse:")):
            _cts_blocked_ids.add(_cts_tid)

    def _cts_effective_tool_use(_cts_tu):
        _cts_nm = (_cts_tu.get("name") or "").lower()
        if _cts_nm not in ("write", "edit", "multiedit"):
            return True
        _cts_tid = _cts_tu.get("id") or _cts_tu.get("tool_use_id")
        if _cts_tid in _cts_blocked_ids:
            return False
        if _cts_tid and _cts_tid not in _cts_result_ids:
            _cts_inp = _cts_tu.get("input") if isinstance(_cts_tu.get("input"), dict) else {}
            if _cts_nm == "write":
                return False
            if _cts_nm == "edit":
                return _cts_inp.get("old_string") != _cts_inp.get("new_string")
            _cts_edits = _cts_inp.get("edits") or []
            return not all(
                isinstance(_e, dict) and _e.get("old_string") == _e.get("new_string")
                for _e in _cts_edits
            )
        return True

    _cts_effective_tool_uses = [
        _tu for _tu in _cts_tool_uses if _cts_effective_tool_use(_tu)
    ]

    # Re-read fix_plan.md fresh (post-edit disk state is authoritative at
    # hook-invocation time). The v1 status audit also needs this even when
    # the older CLOSED-heading scanner finds no heading.
    with open(_cts_target_path, encoding="utf-8") as _cts_f:
        _cts_content = _cts_f.read()

    _cts_flag_entries = []
    _cts_touched_headings = _cts_find_touched(_cts_effective_tool_uses, _cts_target_path)
    if _cts_touched_headings:
        for _cts_heading in _cts_touched_headings:
            _cts_result = _cts_check_heading(
                _cts_content, _cts_heading, _cts_target_path, advisory=True)
            _cts_messages = _cts_result.get("messages") or []
            if _cts_messages:
                # A heading with zero blocking messages does not by itself
                # cause anything to be flagged (theme 4: advisory warnings
                # never block on their own) — mirrors Part C's own
                # per-heading rule ("do NOT by themselves cause a block if
                # there are zero actual blocking messages for that
                # heading").
                _cts_flag_entries.append({
                    "heading": _cts_heading,
                    "messages": _cts_messages,
                    "warnings": _cts_result.get("warnings") or [],
                })

    _cts_status_ranges = _cts_status_touched_ranges(
        _cts_effective_tool_uses, _cts_tool_results, _cts_target_path,
        content=_cts_content)
    if _cts_status_ranges:
        _cts_status_result = _cts_status_audit(
            _cts_content, touched_ranges=_cts_status_ranges,
            full_sweep=False)
        for _cts_finding in (_cts_status_result.get("findings") or []):
            if not _cts_finding.get("blocking"):
                continue
            _cts_heading = _cts_finding.get("heading")
            if not isinstance(_cts_heading, str):
                continue
            _cts_flag_entries.append({
                "heading": _cts_heading,
                "messages": [
                    "status claim %r: %s" % (
                        _cts_finding.get("claim"),
                        _cts_finding.get("classifier")),
                ],
                "warnings": [],
            })

    if _cts_flag_entries:
        _write_flag_if_guarded(
            _cts_session_id, _cts_agent_id, ext="closure_violation",
            content=json.dumps(_cts_flag_entries))
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
            "cwd": _dbg_cwd,
            "last_line": _dbg_last_line,
            "wrote_flag": _dbg_wrote_flag,
        }) + "\n")
except Exception:
    pass

# ── trace.jsonl auto-logging (spec: 2026-07-02_auto-trace-logging) ─────────
# Independent responsibility. ANY exception anywhere in this block must
# be swallowed silently and must never affect the flag-write logic above or
# this hook's exit code (AC5) — mirrors the file's existing two top-level
# try/except: pass blocks. Reuses the SAME pre-read transcript_content from
# the top of the file — never re-opens transcript_path.
try:
    if isinstance(transcript_content, str) and transcript_content:
        # Live-transcript truncation guard (spec.md H-TRACE-WIRING-1,
        # Required-fix Problem 1 item 3): transcript_content may be read
        # mid-write by the very sub-agent process whose completion triggered
        # this hook. A non-newline-terminated trailing line may contain a
        # dangling, incomplete run-dir-shaped reference (the capture class
        # [^/\s"'\)]+ has no requirement that a real delimiter follow it, so
        # it would happily match up to bare end-of-string). Drop that final
        # partial line before scanning; an earlier, complete reference in the
        # same transcript is unaffected.
        if transcript_content.endswith("\n"):
            scan_content = transcript_content
        else:
            head = transcript_content.rpartition("\n")[0]
            scan_content = (head + "\n") if head or "\n" in transcript_content else ""

        # AC1/AC2/AC6/AC22-25: recognize BOTH the bare `runs/<name>/...` form
        # and the `loop-team/runs/<name>/...` form. A single regex cannot
        # correctly disambiguate the two (loop-team/runs/<name> textually
        # CONTAINS runs/<name> as a trailing substring) — this uses two
        # independent finditer passes reconciled by span-shadow-exclusion in
        # Python, per spec.md's "Required technique."
        #
        # Boundary rule (exclusion-based, not inclusion-based): a match is
        # valid unless the character immediately preceding it is a word
        # character or a hyphen — expressed as the negative lookbehind
        # (?<![\w-]), applied IDENTICALLY to both patterns.
        #
        # H-MALFORMED-RUN-DIRS-1: the capture class also excludes backtick
        # (`) and backslash (\) — same rationale as the existing `<`/`>`
        # exclusion (see PlaceholderTemplateTextNotCapturedAsRunDir in
        # hooks/test_subagent_stop_gate.py): this project's OWN docs and this
        # very hook's OWN source comments describe the `runs/<name>/...`
        # convention using Markdown-code-span backticks (e.g. this file's own
        # line above, or fix_plan.md prose like "loop-team/runs/`<name>`/" or
        # "loop-team/runs/\`` "), so a sub-agent transcript that happens to
        # quote/read that documentation or source would otherwise have its
        # backtick-wrapped placeholder text mistaken for a literal run-dir
        # name — the exact live bug this fixes (three garbage directories
        # named "`", "<name>`", and "\`` " were found created on disk from
        # real dispatches). Confirmed independently (see decision-log): real
        # slugs on disk under both <repo_root>/runs/ and
        # <repo_root>/loop-team/runs/ use only alphanumerics, `-`, and `_` —
        # never a backtick or backslash — so this exclusion cannot reject any
        # legitimate name.
        LT_PATTERN = re.compile(r'(?<![\w-])loop-team/runs/([^/\s"\'\)<>`\\]+)')
        BARE_PATTERN = re.compile(r'(?<![\w-])runs/([^/\s"\'\)<>`\\]+)')

        lt_matches = list(LT_PATTERN.finditer(scan_content))
        bare_candidates = list(BARE_PATTERN.finditer(scan_content))

        candidates = []
        for m in lt_matches:
            candidates.append(("loop-team", m.start(), m.group(1)))

        for m in bare_candidates:
            bstart = m.start()
            # Condition A: shadowed by a loop-team/-form match's span.
            shadowed_by_span = any(
                lt.start() <= bstart < lt.end() for lt in lt_matches
            )
            if shadowed_by_span:
                continue
            # Condition B (revision-6): the 10 characters immediately
            # preceding this bare-form candidate are the literal string
            # "loop-team/" — covers the case where the loop-team/-form
            # pattern produced NO match at all (its own boundary check
            # failed on whatever precedes "loop-team"), so there is no span
            # to shadow-exclude against, but this "runs/" occurrence is
            # still semantically the tail of a loop-team/runs/ reference.
            preceding = scan_content[max(0, bstart - 10):bstart]
            if preceding == "loop-team/":
                continue
            candidates.append(("bare", bstart, m.group(1)))

        run_match = None
        if candidates:
            candidates.sort(key=lambda c: c[1])
            run_match = candidates[0]

        if run_match:
            form, _start, name = run_match

            # repo_root: mirror micro_step_gates.py's _signature() sys.path
            # idiom — relative to this hook's own __file__, never cwd.
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if form == "loop-team":
                run_dir = os.path.join(repo_root, "loop-team", "runs", name)
                allowed_root = os.path.realpath(
                    os.path.join(repo_root, "loop-team", "runs")
                )
            else:
                run_dir = os.path.join(repo_root, "runs", name)
                allowed_root = os.path.realpath(os.path.join(repo_root, "runs"))

            # Path-containment / traversal guard (spec.md Required-fix
            # Problem 1 item 5): the captured name's character-class
            # exclusion excludes "/" but NOT ".", so a literal ".." is a
            # legal capture. Verify the resolved real path is still
            # contained under the intended runs/ tree before proceeding;
            # on failure, skip the trace-write silently (fail-open).
            real_run_dir = os.path.realpath(run_dir)
            contained = (
                real_run_dir == allowed_root
                or real_run_dir.startswith(allowed_root + os.sep)
            )
            if not contained:
                run_match = None

        if run_match:
            # Role extraction: prefix/regex match against the transcript's
            # role-brief header line (handles both the bare "# Role: Coder"
            # and the parenthetical-suffixed "# Role: Test-writer (...)" forms).
            role = None
            role_match = re.search(
                r'^# Role:\s*([A-Za-z][\w\s-]*?)(?:\s*\(|$)',
                transcript_content,
                re.MULTILINE,
            )
            if role_match:
                role = role_match.group(1).strip()

            # Verdict extraction: last non-empty line of last_assistant_message,
            # if it matches VERDICT: (PASS|FAIL|FALSE-PASS).
            verdict = None
            if isinstance(lam, str):
                lam_lines = [x.strip() for x in lam.split('\n') if x.strip()]
                if lam_lines:
                    verdict_match = re.match(
                        r'VERDICT:\s*(PASS|FAIL|FALSE-PASS)',
                        lam_lines[-1],
                    )
                    if verdict_match:
                        verdict = verdict_match.group(1)

            # Defensive import: hooks/ and loop-team/runner/ are siblings, so
            # insert loop-team/ onto sys.path before importing. ANY exception
            # here (import failure, moved/renamed module) must result in the
            # trace-write being skipped, never a crash.
            sys.path.insert(0, os.path.join(repo_root, "loop-team"))
            from runner.run_trace import Tracer

            Tracer(run_dir).event(
                "role_dispatch",
                role=role,
                verdict=verdict,
                note=_dbg_agent_id,
            )
except Exception:
    pass

sys.exit(0)
