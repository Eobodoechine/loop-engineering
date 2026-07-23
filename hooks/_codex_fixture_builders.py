"""_codex_fixture_builders.py -- shared, non-production fixture construction
helpers for Deliverable A's test suite
(research/spec-codex-parity-and-consent-installer-2026-07-09.md).

Contains ONLY fixture/test-data construction (JSONL line builders) -- zero
adapter/gate logic. Deliberately named without a `test_` prefix so pytest
does not try to collect it as its own test module; it is imported BY the
test modules.

Every builder here is structurally faithful to two REAL, directly-read files
(AC-1b's own requirement -- "fixtures structurally faithful to" the real
transcripts, not either tool's docs alone):

  - Claude Code: ~/.claude/projects/-Users-eobodoechine/
    0b468db8-1390-4952-aec8-ea19573095c9/subagents/agent-ae1f93647ff39d063.jsonl
    Independently re-confirmed by this test-writer pass (2026-07-09):
    `python3 -c "..."` over every line's top-level "type" showed only
    {"user": 40, "assistant": 68} -- NEVER "session_meta"; a case-sensitive
    grep for '"type":"session_meta"' / '"type": "session_meta"' across the
    whole 108-line file returned zero matches. tool_use/tool_result blocks
    live nested inside `message.content[]` items, never as a line's own
    top-level "type".

  - Codex: ~/.codex/sessions/2026/07/09/
    rollout-2026-07-09T14-03-17-019f480c-5c61-7b53-8b62-25f48e47cefb.jsonl
    Independently re-read by this test-writer pass: 752 lines; first line is
    literally {"type":"session_meta",...}; top-level type distribution
    {'session_meta': 6, 'event_msg': 227, 'response_item': 507,
    'world_state': 5, 'turn_context': 6, 'compacted': 1}; response_item
    payload types {'message': 141, 'reasoning': 48, 'tool_search_call': 2,
    'tool_search_output': 2, 'function_call': 151, 'function_call_output':
    151, 'custom_tool_call': 6, 'custom_tool_call_output': 6}; function_call
    names {'spawn_agent': 28, 'wait_agent': 28, 'send_input': 1,
    'exec_command': 71, 'close_agent': 23}.

    IMPORTANT structural detail independently confirmed and reproduced
    faithfully below (this is easy to get wrong when hand-building a
    fixture from the spec's prose alone): a real `function_call` payload's
    `arguments` field, and a real `function_call_output` payload's `output`
    field, are BOTH JSON-ENCODED STRINGS (e.g. `"arguments":
    "{\\"agent_type\\":\\"explorer\\",...}"`), NOT nested JSON objects. A
    fixture using dict-typed `arguments`/`output` would NOT be real-shaped
    and could let an implementation that (incorrectly) expects a dict slip
    through a test that never exercises the real string-encoding. Also
    confirmed: correlation between a function_call and its
    function_call_output is via the function_call's own `call_id` field
    (distinct from its `id` field, e.g. `id: "fc_0568..."` vs
    `call_id: "call_B0mb..."`) -- the function_call_output payload carries
    ONLY `call_id`, matching the function_call's `call_id`, never its `id`.
"""
import json

# ---------------------------------------------------------------------------
# Claude Code fixture builders (real shape: top-level "type" in
# {"user", "assistant"} only; tool_use/tool_result nested inside
# message.content[] items).
# ---------------------------------------------------------------------------


def cc_user(content):
    """content: a plain string OR a list of content parts (e.g. a
    tool_result part), matching the real file's own two observed shapes."""
    return {"type": "user", "message": {"role": "user", "content": content}}


def cc_assistant(*content_parts):
    return {"type": "assistant",
            "message": {"role": "assistant", "content": list(content_parts)}}


def cc_tool_use(tool_use_id, name, **input_kwargs):
    return {"type": "tool_use", "id": tool_use_id, "name": name,
            "input": input_kwargs}


def cc_tool_result(tool_use_id, content_text):
    """A tool_result CONTENT PART (nested inside a user message's content
    list) -- not a standalone event. Use cc_tool_result_event() for the
    standalone-event form."""
    return {"type": "tool_result", "tool_use_id": tool_use_id,
            "content": content_text}


def cc_tool_result_event(tool_use_id, content_text):
    return cc_user([cc_tool_result(tool_use_id, content_text)])


def write_jsonl(path, events):
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")
    return path


# ---------------------------------------------------------------------------
# Codex fixture builders (real shape: session_meta/turn_context/event_msg/
# response_item/world_state/compacted top-level envelope types;
# response_item payload carries its OWN nested "type"
# (function_call/function_call_output/message/reasoning/...); spawn_agent/
# wait_agent/close_agent are function_call `name` values, never top-level
# envelope types).
# ---------------------------------------------------------------------------


def codex_session_meta(session_id, cwd="<HOME>/.codex/worktrees/x/y",
                        thread_source=None, cli_version="0.144.0-alpha.4"):
    payload = {
        "session_id": session_id, "id": session_id,
        "timestamp": "2026-07-09T18:03:17.768Z", "cwd": cwd,
        "originator": "Codex Desktop", "cli_version": cli_version,
        "source": "vscode", "model_provider": "openai",
    }
    if thread_source:
        payload["thread_source"] = thread_source
    return {"timestamp": "2026-07-09T18:03:22.994Z", "type": "session_meta",
            "payload": payload}


def codex_turn_context():
    return {"timestamp": "2026-07-09T18:03:23.000Z", "type": "turn_context",
            "payload": {"cwd": "/x", "model": "gpt-5"}}


def codex_event_msg(msg_type="task_started"):
    return {"timestamp": "2026-07-09T18:03:24.000Z", "type": "event_msg",
            "payload": {"type": msg_type}}


def codex_function_call(call_id, fc_id, name, arguments_dict,
                         namespace="multi_agent_v1", timestamp=None):
    """`arguments` is JSON-ENCODED AS A STRING -- matches the real captured
    shape (see module docstring); a dict here would be un-real-shaped.
    `timestamp`: ISO8601 (Z-suffixed) override, needed by gate-level tests
    that must control real chronological ordering (e.g. thrash-past-green's
    green-verify-vs-commit epoch comparison); defaults to a fixed realistic
    string for the structural/detection tests that don't care about time."""
    return {"timestamp": timestamp or "2026-07-09T18:04:28.423Z",
            "type": "response_item",
            "payload": {"type": "function_call", "id": fc_id, "name": name,
                        "namespace": namespace,
                        "arguments": json.dumps(arguments_dict),
                        "call_id": call_id}}


def codex_function_call_output(call_id, output_obj, timestamp=None):
    """output_obj: a dict (JSON-encoded to a string, matching the real
    shape) OR a raw string (used verbatim -- needed for the AC-4b
    embedded-prose adversarial fixture, where the output text is free-form
    prose, not a JSON-encoded status object)."""
    output = output_obj if isinstance(output_obj, str) else json.dumps(output_obj)
    return {"timestamp": timestamp or "2026-07-09T18:04:35.160Z",
            "type": "response_item",
            "payload": {"type": "function_call_output", "call_id": call_id,
                        "output": output}}


def codex_spawn_agent(call_id, fc_id, agent_id, agent_type, message,
                       nickname="Ohm", timestamp=None, output_timestamp=None):
    """Returns [function_call, function_call_output] events for a real-
    shaped spawn_agent dispatch plus its correlation-id-bearing result
    (the ONLY channel that reveals agent_id -- confirmed real shape:
    `output: {"agent_id": "<uuid>", "nickname": "<name>"}`)."""
    spawn = codex_function_call(call_id, fc_id, "spawn_agent",
                                 {"agent_type": agent_type, "message": message},
                                 timestamp=timestamp)
    output = codex_function_call_output(
        call_id, {"agent_id": agent_id, "nickname": nickname},
        timestamp=output_timestamp or timestamp)
    return [spawn, output]


def codex_wait_agent(call_id, fc_id, targets, statuses, timed_out=False,
                      timeout_ms=600000, timestamp=None, output_timestamp=None):
    """statuses: {agent_id: {"completed": "<text>"}, ...} -- supports the
    real, confirmed BATCHED multi-target shape (>=1 agent_id keys per
    call), and a `call_id` independent of any spawn_agent's own call_id
    (confirmed: correlation is by agent_id, never by call_id/tool_use_id
    1:1 pairing)."""
    wait = codex_function_call(call_id, fc_id, "wait_agent",
                                {"targets": targets, "timeout_ms": timeout_ms},
                                timestamp=timestamp)
    output = codex_function_call_output(call_id, {"status": statuses,
                                                    "timed_out": timed_out},
                                         timestamp=output_timestamp or timestamp)
    return [wait, output]


def codex_close_agent(call_id, fc_id, agent_id, timestamp=None):
    close = codex_function_call(call_id, fc_id, "close_agent",
                                 {"agent_id": agent_id}, timestamp=timestamp)
    output = codex_function_call_output(call_id, {"closed": True},
                                         timestamp=timestamp)
    return [close, output]


def codex_exec_command(call_id, fc_id, command, output_text,
                        timestamp=None, output_timestamp=None):
    """A real, confirmed function_call name (71 occurrences in the cited
    real rollout file) -- Codex's shell-execution primitive, the analog of
    Claude Code's Bash tool_use. Used by gate-integration tests to build a
    Codex-shaped 'verify ran' signal (output_text carrying the same
    pytest/JSON verdict shapes micro_step_gates.py's _is_verify_result()
    already recognizes)."""
    call = codex_function_call(call_id, fc_id, "exec_command",
                                {"command": command}, timestamp=timestamp)
    output = codex_function_call_output(call_id, output_text,
                                         timestamp=output_timestamp or timestamp)
    return [call, output]


# ---------------------------------------------------------------------------
# AC-4b: the two adversarial embedded-text fixtures, verbatim per the spec's
# own AC-4b wording -- both quote real spec text so the fixtures are the
# EXACT collision round-2 plan-check identified, not a paraphrase of it.
# ---------------------------------------------------------------------------

# Literal excerpt of THIS spec's own Step 2b / AC-3 text (contains the two
# strings AC-4b names verbatim: "session_meta" and
# '{"type": "response_item", "payload": {...}}').
CODEX_SHAPED_PROSE_EXCERPT = (
    "Confirmed real structure: Top-level `type` values: `session_meta`, "
    "`turn_context`, `event_msg`, `response_item`, `world_state`, "
    "`compacted`. `response_item` payloads carry a `type` of their own: "
    "`function_call` (148 in this file), `function_call_output` (147), "
    "`message` (136), `reasoning` (47)... a Codex transcript's tool-call "
    "entries are `response_item` payloads with `type: \"function_call\"` "
    'and `name` in {"spawn_agent","wait_agent","close_agent","exec_command"} '
    'inside a {"type": "response_item", "payload": {...}} envelope with '
    "sibling top-level `type` values (`session_meta`, `turn_context`, "
    "`event_msg`, `world_state`) that never appear in a Claude Code "
    "transcript at all."
)

# Literal excerpt describing Claude Code's tool_use shape, as prose (the
# symmetric collision for the Codex-side fixture). A single string (not a
# tuple) -- deliberately verified by the unit test in
# test_codex_transcript_adapter.py that asserts isinstance(..., str).
CLAUDE_CODE_SHAPED_PROSE_EXCERPT = (
    "For reference, a Claude Code transcript's tool-call entries are "
    "`tool_use` blocks with `name` in "
    '{"task","agent","subagent","workflow"} -- e.g. a real assistant '
    'message part looks like {"type": "tool_use", "name": "Task", '
    '"input": {"description": "Coder for the build", "prompt": "..."}} '
    "nested inside `message.content[]`, never as a top-level line "
    '"type" value.'
)


def build_ac4b_fixture1_claude_code_embedding_codex_prose(path, prose=None):
    """AC-4b Fixture 1 (Claude-Code-side): a REAL-shaped Claude Code
    transcript (structure per agent-ae1f93647ff39d063.jsonl) containing a
    tool_result whose text content is a Read() of a file embedding
    Codex-shaped example JSON/prose -- literally this spec's own text.
    _detect_runtime() on this MUST still return "claude_code"."""
    prose = prose if prose is not None else CODEX_SHAPED_PROSE_EXCERPT
    events = [
        cc_user("Read the spec at /x/spec.md and continue the build."),
        cc_assistant(cc_tool_use(
            "t1", "Read", file_path="/x/spec.md")),
        cc_tool_result_event("t1", prose),
        cc_assistant(cc_tool_use(
            "t2", "Bash", command="python3 loop-team/evals/run_evals.py")),
        cc_tool_result_event("t2", "SUITE:" + " GREEN"),
    ]
    return write_jsonl(path, events)


def build_ac4b_fixture2_codex_embedding_claude_code_prose(path, prose=None):
    """AC-4b Fixture 2 (Codex-side, symmetric): a REAL-shaped Codex rollout
    transcript (structure per the cited real rollout-*.jsonl) containing a
    function_call_output whose `output` text embeds Claude-Code-shaped
    example text as PROSE (not a real structural tool_use block).
    _detect_runtime() on this MUST still return "codex"."""
    prose = prose if prose is not None else CLAUDE_CODE_SHAPED_PROSE_EXCERPT
    session_id = "019f9999-embedtest-0000-000000000001"
    agent_id = "019f9999-embedtest-0000-000000000002"
    events = [
        codex_session_meta(session_id),
        codex_turn_context(),
        *codex_spawn_agent("call_1", "fc_1", agent_id, "explorer",
                            "You are an explorer agent. Read the docs and "
                            "report back on the hooks reference."),
        # A function_call_output whose `output` is free-form prose (a
        # "read this doc" style tool result) embedding the Claude-Code-
        # shaped excerpt, rather than the usual JSON-encoded status object.
        codex_function_call_output("call_2", prose),
    ]
    return write_jsonl(path, events)
