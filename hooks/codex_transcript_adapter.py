#!/usr/bin/env python3
"""codex_transcript_adapter.py -- Codex enforcement parity adapter.

Deliverable A of research/spec-codex-parity-and-consent-installer-2026-07-09.md
("Codex enforcement parity + consent-gated installer"). Sibling module,
imported by both hooks/loop_stop_guard.py and hooks/micro_step_gates.py
(mirroring hooks/verifier_hygiene_scan.py's own shared-module pattern --
one canonical implementation, not two that can drift, per
H-VERIFIER-REGEX-DUPLICATE-1's already-documented lesson).

It does NOT replace the existing Claude-Code-shaped detection logic in
loop_stop_guard.py/micro_step_gates.py; it is consulted ADDITIONALLY, gated
on the runtime discriminator below (_detect_runtime), and its job is to
produce the SAME normalized shape the existing logic already consumes (a
list of VerifierDispatch tuples pairing a verifier-shaped dispatch with its
result text) so the RUNLOG_MISSING / thrash-past-green decision-making in
those two files is reused unchanged, not reimplemented per-runtime.

Runtime discriminator (AC-3, v2 round-2 -- content-based, STRICT structural
matching only): parses each transcript line independently via json.loads()
and checks ONLY that parsed line's own top-level "type" key -- never a
substring/regex/blob scan across raw file bytes, nested content/message/text
fields, or across line boundaries. This discipline exists specifically so
that this spec document's OWN prose (which contains the literal strings
"session_meta" and '{"type": "response_item", "payload": {...}}' as
illustrative text) embedded inside a tool_result in the Coder's own Claude
Code transcript can never misclassify that genuine Claude Code session as
Codex -- see AC-4b / TestAC4bAdversarialEmbeddedTextCollisionPair in
hooks/test_codex_transcript_adapter.py, and the spec's own REVISION NOTE.
"""
import glob
import json
import os
import re
import sys
from typing import NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# AC-8 / H-VERIFIER-REGEX-DUPLICATE-1: import the shared regex, never define
# a second copy of it here.
from verifier_hygiene_scan import VERIFIER_DETECT as _VERIFIER_DETECT


# Deliberately case-insensitive and owned by THIS module (unlike
# _VERIFIER_DETECT, this is not the regex H-VERIFIER-REGEX-DUPLICATE-1 is
# about -- it is a small, local classifier of a dispatch's own result text).
VERDICT_PASS_RE = re.compile(r'verdict:\s*pass', re.I)


class VerifierDispatch(NamedTuple):
    """AC-2's public shape. `result_source` is one of
    "wait_agent_summary" (the completion text came straight from the
    wait_agent function_call_output that resolved this agent_id) or
    "child_transcript" (the summary was insufficient -- no VERDICT: PASS
    match -- so the sub-agent's own separate rollout-*.jsonl file was
    located and read instead)."""
    agent_id: str
    agent_type: str
    prompt_text: str
    result_text: str
    result_source: str


# ---------------------------------------------------------------------------
# AC-3 -- _detect_runtime: strict structural matching only.
# ---------------------------------------------------------------------------

def _detect_runtime(transcript_path):
    """Returns "codex", "claude_code", or "unknown".

    Per line (parsed independently via json.loads(), malformed lines
    silently skipped -- one bad line never aborts the whole scan):
      - "codex"       iff that line's OWN top-level "type" == "session_meta".
      - "claude_code" iff that line's "message" dict has a "content" list
                       containing an item whose OWN "type" == "tool_use"
                       (the real structural position -- never a bare
                       top-level "type": "tool_use", and never a nested
                       marker found via string search).
    Neither found in the whole file -> "unknown" (falls through to the
    existing, unmodified Claude-Code-shaped scan path -- safe default, zero
    regression on ambiguous/unrecognized input, per the spec's explicit
    three-way return: "never a guess from absence").
    """
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return "unknown"

    saw_codex = False
    saw_claude_code = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue

        if obj.get("type") == "session_meta":
            saw_codex = True

        message = obj.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        saw_claude_code = True
                        break

    if saw_codex:
        return "codex"
    if saw_claude_code:
        return "claude_code"
    return "unknown"


# ---------------------------------------------------------------------------
# Internal parsing helpers (AC-2).
# ---------------------------------------------------------------------------

def _load_jsonl_indexed(path):
    """list of (idx, obj) for every successfully-parsed dict-shaped JSONL
    line, in file order. idx is a dense 0..N-1 sequence over the SUCCESSFUL
    parses only (a malformed line contributes nothing and does not consume
    an index) -- ordering between real entries is preserved either way.
    Raises OSError if the file cannot be opened (caller's job to decide
    fail-open behavior -- see AC-7)."""
    entries = []
    idx = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                entries.append((idx, obj))
                idx += 1
    return entries


def _load_jsonl(path):
    """Same as _load_jsonl_indexed but drops the index -- used by the
    child-transcript lookup, which only needs the objects themselves."""
    return [obj for _idx, obj in _load_jsonl_indexed(path)]


def _parse_maybe_json(raw):
    """raw: expected to be a JSON-encoded STRING (the real, confirmed shape
    of both function_call.arguments and function_call_output.output -- see
    _codex_fixture_builders.py's own module docstring). Returns the parsed
    value, or None if raw isn't a string or fails to parse (never raises --
    AC-7's per-field fail-soft discipline)."""
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _extract_message_text(payload):
    """payload: a response_item payload whose own "type" == "message". Its
    "content" is a list of parts (e.g. {"type": "output_text", "text": ...})
    -- concatenates every part's "text", matching the real, confirmed shape.
    Also tolerates a bare string "content" (defensive, not a shape this
    codebase has directly observed for Codex but costs nothing to accept)."""
    content = payload.get("content")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts)
    if isinstance(content, str):
        return content
    return ""


def _find_wait_agent_summary(entries, after_idx, agent_id):
    """Forward-scans `entries` (as returned by _load_jsonl_indexed) for the
    FIRST function_call_output response_item AFTER `after_idx` whose parsed
    `output` is a dict carrying `status.<agent_id>.completed` -- per the
    spec's own wording: correlation is by agent_id, never by call_id/
    tool_use_id 1:1 pairing (a single wait_agent call batches multiple
    agent_ids and uses its own, independent call_id). Returns the
    "completed" text, or None if never found."""
    for idx, obj in entries:
        if idx <= after_idx:
            continue
        if obj.get("type") != "response_item":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "function_call_output":
            continue
        parsed = _parse_maybe_json(payload.get("output"))
        if not isinstance(parsed, dict):
            continue
        status = parsed.get("status")
        if isinstance(status, dict) and agent_id in status:
            entry = status[agent_id]
            if isinstance(entry, dict):
                completed = entry.get("completed")
                if isinstance(completed, str):
                    return completed
    return None


def _find_child_verdict(parent_transcript_path, agent_id):
    """AC-2's child_transcript fallback: locates the sub-agent's OWN,
    separate rollout-*.jsonl file (session_meta.payload.session_id ==
    agent_id) under the SAME directory as the parent's transcript_path, and
    returns the first assistant message text containing "VERDICT: PASS"
    found in it (or, best-effort, the LAST assistant message text if no
    explicit pass-verdict is found there either -- still more informative
    than a summary already confirmed insufficient). Returns None if no
    matching sibling file / no usable text at all -- caller falls back to
    keeping the original wait_agent summary text unchanged in that case.
    Best-effort/fail-soft throughout (AC-7): any OSError here degrades to
    None, never propagates."""
    try:
        directory = os.path.dirname(os.path.abspath(parent_transcript_path))
        candidates = sorted(glob.glob(os.path.join(directory, "*.jsonl")))
    except OSError:
        return None

    parent_real = os.path.abspath(parent_transcript_path)
    for cand in candidates:
        if os.path.abspath(cand) == parent_real:
            continue
        try:
            objs = _load_jsonl(cand)
        except OSError:
            continue

        session_match = any(
            obj.get("type") == "session_meta"
            and isinstance(obj.get("payload"), dict)
            and obj["payload"].get("session_id") == agent_id
            for obj in objs
        )
        if not session_match:
            continue

        assistant_texts = []
        for obj in objs:
            if obj.get("type") != "response_item":
                continue
            payload = obj.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "message":
                continue
            text = _extract_message_text(payload)
            if text:
                assistant_texts.append(text)

        for text in assistant_texts:
            if VERDICT_PASS_RE.search(text):
                return text
        if assistant_texts:
            return assistant_texts[-1]
        return None
    return None


# ---------------------------------------------------------------------------
# AC-2 -- public entry point.
# ---------------------------------------------------------------------------

def _current_turn_start(entries):
    current_start = -1
    for idx, obj in entries:
        if obj.get("type") == "turn_context":
            current_start = idx
    return current_start


def _codex_dispatch_says_verifier(args):
    if not isinstance(args, dict):
        return False
    agent_type = args.get("agent_type", "")
    if isinstance(agent_type, str) and agent_type.strip().lower() == "verifier":
        return True
    message = args.get("message")
    return isinstance(message, str) and bool(_VERIFIER_DETECT.search(message.lower()))


def extract_verifier_dispatches(transcript_path, current_turn_only=False):
    """Pure function: transcript_path (str) -> list[VerifierDispatch].

    Detects a Verifier-shaped dispatch by scanning spawn_agent function_call
    items' arguments.message text with the shared _VERIFIER_DETECT regex --
    NOT by tool/function name (every spawn_agent shares the same function
    name regardless of role). Correlates a spawn_agent call to its eventual
    result by agent_id (from that call's own function_call_output.output.
    agent_id), then forward-scans subsequent wait_agent function_call_output
    entries for that SAME agent_id's completed text. Falls back to the
    sub-agent's own separate transcript (_find_child_verdict) when the
    wait_agent summary does not itself contain a VERDICT: PASS match.

    Fail-soft per AC-7: a missing transcript file returns [] rather than
    raising; malformed/unexpected shapes at the level of an individual
    call/output are skipped rather than aborting the whole scan. A
    genuinely unexpected error elsewhere is allowed to propagate -- callers
    (loop_stop_guard.py / micro_step_gates.py) already wrap every risk-
    bearing gate in the SAME `except Exception: sys.stderr.write(...)`
    fail-open pattern this whole framework uses everywhere else.
    """
    try:
        entries = _load_jsonl_indexed(transcript_path)
    except OSError:
        return []

    current_start = _current_turn_start(entries) if current_turn_only else -1

    calls = []    # (idx, call_id, name, args_dict_or_None)
    outputs = []  # (idx, call_id, raw_output)
    for idx, obj in entries:
        if obj.get("type") != "response_item":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            continue
        ptype = payload.get("type")
        if ptype == "function_call":
            args = _parse_maybe_json(payload.get("arguments"))
            if args is None and isinstance(payload.get("arguments"), dict):
                args = payload.get("arguments")  # tolerate a dict-typed
                # arguments field too, even though the real/confirmed shape
                # is always a JSON-encoded string -- costs nothing to accept.
            calls.append((idx, payload.get("call_id"), payload.get("name"), args))
        elif ptype == "function_call_output":
            outputs.append((idx, payload.get("call_id"), payload.get("output")))

    output_by_call_id = {}
    for idx, call_id, raw in outputs:
        if call_id is not None and call_id not in output_by_call_id:
            output_by_call_id[call_id] = (idx, raw)

    dispatches = []
    for idx, call_id, name, args in calls:
        if idx <= current_start:
            continue
        if name != "spawn_agent" or not isinstance(args, dict):
            continue
        if not _codex_dispatch_says_verifier(args):
            continue
        message = args.get("message")
        if not isinstance(message, str):
            message = ""

        out = output_by_call_id.get(call_id)
        if out is None:
            continue
        out_idx, out_raw = out
        parsed_out = _parse_maybe_json(out_raw)
        agent_id = parsed_out.get("agent_id") if isinstance(parsed_out, dict) else None
        if not agent_id:
            continue

        agent_type = args.get("agent_type", "")
        result_text = _find_wait_agent_summary(entries, out_idx, agent_id) or ""
        result_source = "wait_agent_summary"
        if not VERDICT_PASS_RE.search(result_text):
            child_text = _find_child_verdict(transcript_path, agent_id)
            if child_text is not None:
                result_text = child_text
                result_source = "child_transcript"

        dispatches.append(VerifierDispatch(
            agent_id=agent_id,
            agent_type=agent_type if isinstance(agent_type, str) else str(agent_type),
            prompt_text=message,
            result_text=result_text,
            result_source=result_source,
        ))

    return dispatches


# ---------------------------------------------------------------------------
# Low-level helpers reused by micro_step_gates.py's thrash-past-green
# Codex-path (AC-6). Deliberately public (no leading underscore) -- these
# hand back STRUCTURAL data (parsed spawn_agent / exec_command calls,
# correlated with their outputs); classification (e.g. "is this output text
# a green/red verify result") stays owned by micro_step_gates.py itself, so
# this module never needs to import back from its own callers (which would
# create a circular import) and micro_step_gates.py's existing classifier
# (_is_verify_result) is reused unchanged, not duplicated here.
# ---------------------------------------------------------------------------

def extract_function_calls(transcript_path, name=None):
    """list of dicts: {"index", "call_id", "name", "arguments", "output"}
    for every response_item function_call in the transcript (optionally
    filtered to a single function `name`, e.g. "spawn_agent"/"exec_command"),
    each paired with its own function_call_output's raw `output` text (a
    STRING -- the caller decides how/whether to further parse it; a real
    exec_command's output is often plain text, not JSON, so this
    deliberately does NOT attempt to JSON-decode it the way
    extract_verifier_dispatches does for spawn_agent/wait_agent's own,
    confirmed-JSON-encoded, output shape). `index` is the SAME dense
    ordering _find_wait_agent_summary relies on, so callers can do their own
    epoch/ordering comparisons exactly like the existing Claude-Code-shaped
    gate logic does today. Fail-soft: a missing/unreadable file returns []."""
    try:
        entries = _load_jsonl_indexed(transcript_path)
    except OSError:
        return []

    outputs_by_call_id = {}
    for idx, obj in entries:
        if obj.get("type") != "response_item":
            continue
        payload = obj.get("payload")
        if isinstance(payload, dict) and payload.get("type") == "function_call_output":
            call_id = payload.get("call_id")
            if call_id is not None and call_id not in outputs_by_call_id:
                outputs_by_call_id[call_id] = (idx, payload.get("output"))

    results = []
    for idx, obj in entries:
        if obj.get("type") != "response_item":
            continue
        payload = obj.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "function_call":
            continue
        call_name = payload.get("name")
        if name is not None and call_name != name:
            continue
        args = _parse_maybe_json(payload.get("arguments"))
        call_id = payload.get("call_id")
        out_idx, out_raw = outputs_by_call_id.get(call_id, (None, None))
        results.append({
            "index": idx,
            "output_index": out_idx,
            "call_id": call_id,
            "name": call_name,
            "arguments": args,
            "timestamp": obj.get("timestamp"),
            "output": out_raw,
        })
    return results


def extract_spec_credit_records(transcript_path):
    """Return spec_bound_verifier_credit-shaped records for Codex dispatches.

    Codex records sub-agent launches as `spawn_agent` function_call entries
    and later completion text through `wait_agent`, not Claude Code's nested
    `tool_use` / `tool_result` parts. Normalize only the current Codex turn
    (after the last top-level turn_context marker) into the same record shape
    consumed by the shared spec-bound Verifier/Coder credit gate.
    """
    try:
        entries = _load_jsonl_indexed(transcript_path)
    except OSError:
        return []

    current_start = _current_turn_start(entries)

    raw_records = []
    for call in extract_function_calls(transcript_path):
        idx = call.get("index")
        if idx is None or idx <= current_start:
            continue

        name = call.get("name")
        args = call.get("arguments")
        if name == "spawn_agent" and isinstance(args, dict):
            out = _parse_maybe_json(call.get("output"))
            agent_id = out.get("agent_id") if isinstance(out, dict) else None
            if not isinstance(agent_id, str) or not agent_id:
                continue
            message = args.get("message", "")
            agent_type = args.get("agent_type", "")
            raw_records.append((idx, {
                "kind": "tool_use",
                "part": {
                    "type": "tool_use",
                    "id": agent_id,
                    "name": "Agent",
                    "input": {
                        "description": "",
                        "prompt": message if isinstance(message, str) else str(message),
                        "subagent_type": (
                            agent_type if isinstance(agent_type, str)
                            else str(agent_type)
                        ),
                    },
                },
            }))
        elif name == "wait_agent":
            out = _parse_maybe_json(call.get("output"))
            status = out.get("status") if isinstance(out, dict) else None
            if not isinstance(status, dict):
                continue
            output_index = call.get("output_index")
            record_index = output_index if output_index is not None else idx
            for agent_id, entry in status.items():
                if not isinstance(agent_id, str) or not isinstance(entry, dict):
                    continue
                completed = entry.get("completed")
                if not isinstance(completed, str):
                    continue
                raw_records.append((record_index, {
                    "kind": "tool_result",
                    "part": {
                        "type": "tool_result",
                        "tool_use_id": agent_id,
                        "content": completed,
                    },
                }))

    records = []
    for ordinal, (_idx, record) in enumerate(sorted(raw_records, key=lambda x: x[0])):
        record["ordinal"] = ordinal
        records.append(record)
    return records
