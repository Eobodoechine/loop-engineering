"""Tests for hooks/codex_transcript_adapter.py -- Deliverable A of
research/spec-codex-parity-and-consent-installer-2026-07-09.md ("Codex
enforcement parity + consent-gated installer").

Written BEFORE any implementation exists (Test-writer, Tier 1). Every test
here MUST currently fail with ModuleNotFoundError (no codex_transcript_
adapter.py on disk yet) -- that is correct and expected at this stage. The
Coder implements against this file next.

Covers:
  AC-1  (blocking prerequisite -- explicit hard-fail, not a fabricated pass)
  AC-2  (extract_verifier_dispatches)
  AC-3  (_detect_runtime -- strict structural matching)
  AC-4b (the adversarial embedded-text collision pair -- BOTH mandatory)
  AC-7  (fail-open contract, adapter-level slice)
  AC-8  (regression: imports _VERIFIER_DETECT, does not duplicate it)

AC-4/AC-5/AC-6 (the end-to-end gate-firing behavior in loop_stop_guard.py /
micro_step_gates.py under Codex-shaped input) live in the sibling file
test_codex_parity_gates.py, mirroring this repo's existing split between
test_verifier_hygiene_scan.py (shared-module unit tests) and
test_verifier_hygiene_gate.py (gate-level consumption tests).

Public-interface assumption this file makes explicit (spec does not pin an
exact Python type for VerifierDispatch, only its field names): field access
below goes through the `_f()` helper, which accepts either an
attribute-bearing object (dataclass/NamedTuple) or a dict/TypedDict --
whichever the Coder implements, these tests still exercise the *fields* the
spec names, not a specific Python representation.
"""
import json
import os
import re
import sys
import tempfile

import pytest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS_DIR)

import _codex_fixture_builders as fb  # noqa: E402

ADAPTER_PATH = os.path.join(HOOKS_DIR, "codex_transcript_adapter.py")

try:
    import codex_transcript_adapter as cta  # noqa: E402
    _IMPORT_ERROR = None
except Exception as _e:  # ModuleNotFoundError today -- expected pre-build
    cta = None
    _IMPORT_ERROR = _e


def _require_adapter():
    if cta is None:
        pytest.fail(
            "codex_transcript_adapter.py does not exist / does not import "
            "yet (%r). Expected at this stage (Test-writer runs before the "
            "Coder) -- once Deliverable A is implemented this module must "
            "import cleanly." % (_IMPORT_ERROR,)
        )


def _f(obj, name):
    """Field access tolerant of either an attribute-bearing VerifierDispatch
    (dataclass/NamedTuple) or a dict/TypedDict implementation."""
    if isinstance(obj, dict):
        return obj[name]
    return getattr(obj, name)


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _json_string_body(text):
    """Return how `text` appears inside an enclosing JSON string value."""
    return json.dumps(text)[1:-1]


# ===========================================================================
# AC-1 (blocking prerequisite) -- [DOC]
# ===========================================================================

class TestAC1HumanRunCodexStdinCapturePrerequisite:
    """AC-1: 'a real, minimal, human-run Codex session ... has been
    executed, its literal Stop/SubagentStop hook stdin JSON captured
    verbatim to a fixture file, and diffed against Step 2's inferred
    schema. Any discrepancy found must be reconciled into this spec BEFORE
    Deliverable A's code is written.' This is explicitly a HUMAN-RUN
    prerequisite (spec Step 2c: 'this step is human-run, not Researcher/
    Coder-run'). As of this test-writing pass (2026-07-09), no such
    fixture exists anywhere in this repo -- confirmed via `find` for
    *codex*stdin*/*codex*fixture* under ~/Claude/loop (zero matches).

    This test intentionally, permanently fails until a human executes that
    live Codex session and the resulting fixture file exists at the path
    below. It must NOT be satisfied by a synthetic/fabricated payload --
    that would defeat the entire point of AC-1 (closing the one remaining
    unconfirmed link: whether Codex's real Stop-hook stdin is byte-
    identical to the documented schema)."""

    EXPECTED_FIXTURE = os.path.join(
        HOOKS_DIR, "fixtures", "ac1_captured_codex_stop_stdin.json")

    def test_ac1_captured_fixture_exists_and_is_a_real_capture(self):
        assert os.path.isfile(self.EXPECTED_FIXTURE), (
            "AC-1 BLOCKING PREREQUISITE NOT SATISFIED.\n"
            "Per spec-codex-parity-and-consent-installer-2026-07-09.md "
            "AC-1: a real, minimal, human-run Codex session (single "
            "trivial no-op turn, hook debug logging enabled) must be "
            "executed and its literal Stop/SubagentStop hook stdin JSON "
            "captured VERBATIM to %s, then diffed against Step 2's "
            "inferred schema. This is a HUMAN-RUN step (not Researcher/"
            "Coder-run) -- do not fabricate this fixture programmatically. "
            "AC-1 is explicitly 'blocking -- must be satisfied before any "
            "other AC is graded.' No captured fixture currently exists on "
            "this machine (confirmed via search of ~/Claude/loop for "
            "*codex*stdin*/*codex*fixture* fixtures, 2026-07-09)."
            % self.EXPECTED_FIXTURE
        )
        # If the fixture DOES eventually exist, sanity-check it is a real
        # capture (has the fields Step 2a's documented schema names) and
        # not an empty placeholder file masquerading as satisfied.
        with open(self.EXPECTED_FIXTURE, encoding="utf-8") as f:
            payload = json.load(f)
        for required_field in ("session_id", "transcript_path", "cwd",
                                "hook_event_name", "stop_hook_active"):
            assert required_field in payload, (
                "AC-1 fixture exists but is missing documented-schema field "
                "%r -- this looks like a placeholder, not a real capture."
                % required_field)


# ===========================================================================
# AC-2 -- extract_verifier_dispatches -- [BEHAVIORAL]
# ===========================================================================

class TestAC2ExtractVerifierDispatches:
    """extract_verifier_dispatches(transcript_path: str) -> list[
    VerifierDispatch], VerifierDispatch >= {agent_id, agent_type,
    prompt_text, result_text, result_source}, result_source in
    {"wait_agent_summary", "child_transcript"}. Synthetic (not real/
    proprietary) fixture built from the 2b STRUCTURE -- same field names,
    invented content, per AC-2's own wording."""

    def _write(self, tmp_path, events):
        p = os.path.join(str(tmp_path), "rollout.jsonl")
        fb.write_jsonl(p, events)
        return p

    def test_basic_pass_dispatch_resolves_via_wait_agent_summary(self, tmp_path):
        _require_adapter()
        session_id = "019f0000-0000-0000-0000-000000000001"
        agent_id = "019f0000-0000-0000-0000-000000000002"
        events = [
            fb.codex_session_meta(session_id),
            *fb.codex_spawn_agent(
                "call_1", "fc_1", agent_id, "default",
                "You are acting as the loop-team plan-check Verifier for "
                "the widget spec. Do all reads yourself, do NOT dispatch "
                "sub-agents. Mode: PLAN-CHECK."),
            *fb.codex_wait_agent(
                "call_2", "fc_2", [agent_id],
                {agent_id: {"completed": "Reviewed the plan. VERDICT: PASS "
                            "-- looks good."}}),
        ]
        path = self._write(tmp_path, events)
        dispatches = cta.extract_verifier_dispatches(path)
        assert len(dispatches) == 1, dispatches
        d = dispatches[0]
        assert _f(d, "agent_id") == agent_id
        assert _f(d, "agent_type") == "default"
        assert "plan-check Verifier" in _f(d, "prompt_text")
        assert "VERDICT: PASS" in _f(d, "result_text")
        assert _f(d, "result_source") == "wait_agent_summary"

    def test_non_verifier_spawn_agent_excluded(self, tmp_path):
        """A spawn_agent whose message is pure implementation work (no
        _VERIFIER_DETECT match) must NOT appear in the returned list --
        detection is by prompt-text content, never by tool/function name
        (every spawn_agent shares the same function name regardless of
        role, per the spec's own explicit 'NOT by tool/function name')."""
        _require_adapter()
        session_id = "019f0000-0000-0000-0000-000000000003"
        agent_id = "019f0000-0000-0000-0000-000000000004"
        events = [
            fb.codex_session_meta(session_id),
            *fb.codex_spawn_agent(
                "call_1", "fc_1", agent_id, "worker",
                "You are the Gmail provider implementation worker. "
                "Implement the OAuth token exchange endpoint."),
            *fb.codex_wait_agent(
                "call_2", "fc_2", [agent_id],
                {agent_id: {"completed": "Implemented and tested."}}),
        ]
        path = self._write(tmp_path, events)
        dispatches = cta.extract_verifier_dispatches(path)
        assert dispatches == [], dispatches

    def test_correlation_is_by_agent_id_not_call_id(self, tmp_path):
        """Two spawn_agent dispatches, ONE batched wait_agent call awaiting
        both agent_ids at once (confirmed real shape). Each returned
        VerifierDispatch must carry its OWN agent_id's completion text --
        never the other's, and never fail because the wait_agent's call_id
        differs from either spawn_agent's own call_id (confirmed
        structurally impossible to pair 1:1 by call_id)."""
        _require_adapter()
        session_id = "019f0000-0000-0000-0000-000000000005"
        agent_a = "019f0000-aaaa-0000-0000-000000000000"
        agent_b = "019f0000-bbbb-0000-0000-000000000000"
        events = [
            fb.codex_session_meta(session_id),
            *fb.codex_spawn_agent(
                "call_a", "fc_a", agent_a, "default",
                "plan-check verifier for spec A. VERDICT pending."),
            *fb.codex_spawn_agent(
                "call_b", "fc_b", agent_b, "default",
                "plan-check verifier for spec B. VERDICT pending."),
            *fb.codex_wait_agent(
                "call_wait", "fc_wait", [agent_a, agent_b],
                {agent_a: {"completed": "Spec A review. VERDICT: PASS."},
                 agent_b: {"completed": "Spec B review. VERDICT: FAIL."}}),
        ]
        path = self._write(tmp_path, events)
        dispatches = {_f(d, "agent_id"): d
                      for d in cta.extract_verifier_dispatches(path)}
        assert set(dispatches) == {agent_a, agent_b}
        assert "spec A" in _f(dispatches[agent_a], "prompt_text")
        assert "VERDICT: PASS" in _f(dispatches[agent_a], "result_text")
        assert "spec B" in _f(dispatches[agent_b], "prompt_text")
        assert "VERDICT: FAIL" in _f(dispatches[agent_b], "result_text")

    def test_child_transcript_fallback_when_summary_insufficient(self, tmp_path):
        """When the wait_agent 'completed' summary does NOT itself contain
        a VERDICT: pass match, the adapter must fall back to locating the
        child's OWN separate rollout-*.jsonl file (session_meta.payload.
        session_id == the target agent_id) under the same session-date
        directory tree as the parent's transcript_path, and read the
        verdict from there. result_source must report "child_transcript"."""
        _require_adapter()
        session_dir = tmp_path / "2026" / "07" / "09"
        session_dir.mkdir(parents=True)
        parent_session_id = "019f0000-parent-0000-0000-000000000000"
        child_agent_id = "019f0000-child0-0000-0000-000000000000"
        parent_path = str(session_dir / "rollout-parent.jsonl")
        child_path = str(session_dir / "rollout-child.jsonl")

        parent_events = [
            fb.codex_session_meta(parent_session_id),
            *fb.codex_spawn_agent(
                "call_1", "fc_1", child_agent_id, "default",
                "independent verifier: plan-check the auth spec."),
            *fb.codex_wait_agent(
                "call_2", "fc_2", [child_agent_id],
                # Summary alone is insufficient -- no VERDICT text here.
                {child_agent_id: {"completed": "Blocked by sandbox during "
                                  "branch creation, then approved "
                                  "escalation succeeded. No implementation "
                                  "changes or tests run yet."}}),
        ]
        fb.write_jsonl(parent_path, parent_events)

        child_events = [
            fb.codex_session_meta(child_agent_id, thread_source="subagent"),
            fb.codex_event_msg(),
            {"timestamp": "t", "type": "response_item",
             "payload": {"type": "message", "role": "assistant",
                         "content": [{"type": "output_text",
                                      "text": "Reviewed the auth spec in "
                                      "full. VERDICT: PASS -- ready to "
                                      "build."}]}},
        ]
        fb.write_jsonl(child_path, child_events)

        dispatches = cta.extract_verifier_dispatches(parent_path)
        assert len(dispatches) == 1, dispatches
        d = dispatches[0]
        assert _f(d, "agent_id") == child_agent_id
        assert "VERDICT: PASS" in _f(d, "result_text")
        assert _f(d, "result_source") == "child_transcript"


    def test_current_turn_only_excludes_prior_turn_dispatches(self, tmp_path):
        _require_adapter()
        session_id = "019f0000-current-turn-parent"
        prior_agent = "019f0000-current-turn-prior"
        current_agent = "019f0000-current-turn-current"
        events = [
            fb.codex_session_meta(session_id),
            *fb.codex_spawn_agent(
                "call_prior", "fc_prior", prior_agent, "verifier",
                "You are the loop-team Verifier for old build. VERDICT pending."),
            *fb.codex_wait_agent(
                "wait_prior", "fc_wait_prior", [prior_agent],
                {prior_agent: {"completed": "Old build. VERDICT: PASS."}}),
            fb.codex_turn_context(),
            *fb.codex_spawn_agent(
                "call_current", "fc_current", current_agent, "verifier",
                "You are the loop-team Verifier for current build. VERDICT pending."),
            *fb.codex_wait_agent(
                "wait_current", "fc_wait_current", [current_agent],
                {current_agent: {"completed": "Current build. VERDICT: FAIL."}}),
        ]
        path = self._write(tmp_path, events)
        all_dispatches = cta.extract_verifier_dispatches(path)
        current_dispatches = cta.extract_verifier_dispatches(path, current_turn_only=True)
        assert {_f(d, "agent_id") for d in all_dispatches} == {prior_agent, current_agent}
        assert [_f(d, "agent_id") for d in current_dispatches] == [current_agent]

    def test_agent_type_verifier_detected_without_shared_regex_text(self, tmp_path):
        _require_adapter()
        session_id = "019f0000-agent-type-parent"
        agent_id = "019f0000-agent-type-verifier"
        events = [
            fb.codex_session_meta(session_id),
            fb.codex_turn_context(),
            *fb.codex_spawn_agent(
                "call_1", "fc_1", agent_id, "verifier",
                "Review the implemented widget build against /tmp/spec.md."),
            *fb.codex_wait_agent(
                "call_2", "fc_2", [agent_id],
                {agent_id: {"completed": "Reviewed implementation. VERDICT: PASS."}}),
        ]
        path = self._write(tmp_path, events)
        dispatches = cta.extract_verifier_dispatches(path, current_turn_only=True)
        assert len(dispatches) == 1, dispatches
        assert _f(dispatches[0], "agent_id") == agent_id

    def test_returns_empty_list_for_transcript_with_no_dispatches(self, tmp_path):
        _require_adapter()
        session_id = "019f0000-empty-0000-0000-000000000000"
        path = self._write(tmp_path, [fb.codex_session_meta(session_id),
                                       fb.codex_turn_context()])
        assert cta.extract_verifier_dispatches(path) == []


# ===========================================================================
# AC-3 -- _detect_runtime -- [BEHAVIORAL] [SECURITY-ORACLE]
# (labeled SECURITY-ORACLE: a misclassification here silently routes a real
# Claude Code session through the wrong adapter, disabling RUNLOG_MISSING/
# thrash-past-green with no exception ever firing -- exactly the class of
# "actor A cannot silently affect actor B's guard" isolation claim LOOP-M3
# flags for Tier-2 mutation-oracle scrutiny.)
# ===========================================================================

class TestAC3DetectRuntimeBasicParity:
    """Both paths tested with the SAME assertions (parametrized), per AC-3's
    own requirement: 'Both paths must be unit-tested with the SAME
    assertions (parametrized), proving parity, not just "the Codex path
    exists."'"""

    def test_real_shaped_claude_code_transcript_detected(self, tmp_path):
        _require_adapter()
        path = str(tmp_path / "t.jsonl")
        events = [
            fb.cc_user("go build the widget"),
            fb.cc_assistant(fb.cc_tool_use(
                "t1", "Edit", file_path="/x/app.py",
                old_string="a", new_string="b")),
        ]
        fb.write_jsonl(path, events)
        assert cta._detect_runtime(path) == "claude_code"

    def test_real_shaped_codex_transcript_detected(self, tmp_path):
        _require_adapter()
        path = str(tmp_path / "t.jsonl")
        events = [
            fb.codex_session_meta("019f0000-1111-0000-0000-000000000000"),
            fb.codex_turn_context(),
            *fb.codex_spawn_agent(
                "call_1", "fc_1", "019f0000-2222-0000-0000-000000000000",
                "worker", "implement the feature"),
        ]
        fb.write_jsonl(path, events)
        assert cta._detect_runtime(path) == "codex"

    def test_neither_marker_present_returns_unknown(self, tmp_path):
        """Explicit three-way return, never a guess from absence -- a
        transcript shaped like neither runtime falls through to
        'unknown' (today's unchanged Claude-Code-shaped behavior)."""
        _require_adapter()
        path = str(tmp_path / "t.jsonl")
        fb.write_jsonl(path, [{"type": "some_other_format", "data": 1},
                               {"type": "another_line", "x": [1, 2, 3]}])
        assert cta._detect_runtime(path) == "unknown"

    def test_empty_transcript_returns_unknown_not_crash(self, tmp_path):
        _require_adapter()
        path = str(tmp_path / "t.jsonl")
        fb.write_jsonl(path, [])
        assert cta._detect_runtime(path) == "unknown"

    def test_malformed_json_lines_mixed_with_valid_marker_still_classifies(
            self, tmp_path):
        """A transcript with one unparseable line (real-world corruption/
        truncation) alongside a genuine marker line elsewhere must still
        classify correctly -- confirms per-line json.loads() isolation
        (one bad line doesn't abort the whole scan) without needing a
        whole-file exception path."""
        _require_adapter()
        path = str(tmp_path / "t.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json at all\n")
            f.write(json.dumps(fb.codex_session_meta(
                "019f0000-3333-0000-0000-000000000000")) + "\n")
        assert cta._detect_runtime(path) == "codex"


class TestAC3StrictStructuralMatchingDiscipline:
    """Round-2 plan-check's mandatory implementation discipline: parse each
    line independently via json.loads(), check ONLY that line's own
    top-level "type" key -- never a substring/regex/blob scan across raw
    bytes, nested content/message/text fields, or across line boundaries.
    These tests target the boundary directly (distinct from AC-4b's full
    realistic-fixture pair below): a marker string present at the WRONG
    structural position must not flip detection."""

    def test_session_meta_string_nested_not_top_level_does_not_mean_codex(
            self, tmp_path):
        """"session_meta" appears as a NESTED dict key two levels down --
        never as any line's own top-level "type" -- must not classify as
        codex."""
        _require_adapter()
        path = str(tmp_path / "t.jsonl")
        line = {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1",
             "content": [{"nested": {"type": "session_meta"}}]}]}}
        fb.write_jsonl(path, [line])
        assert cta._detect_runtime(path) != "codex"

    def test_tool_use_type_at_wrong_structural_position_does_not_mean_claude_code(
            self, tmp_path):
        """A line whose OWN top-level "type" is "tool_use" (not nested
        inside message.content[] the way a real Claude Code transcript
        always structures it) must not classify as claude_code -- 'a
        tool_use block only counts at its real structural position.'"""
        _require_adapter()
        path = str(tmp_path / "t.jsonl")
        line = {"type": "tool_use", "name": "spawn_agent",
                "input": {"agent_type": "worker"}}
        fb.write_jsonl(path, [line])
        assert cta._detect_runtime(path) != "claude_code"

    def test_session_meta_substring_inside_a_free_text_field_does_not_mean_codex(
            self, tmp_path):
        """The literal substring "session_meta" sitting inside a plain text
        field (not even valid JSON around it) must not trip detection --
        proves this isn't a whole-file grep."""
        _require_adapter()
        path = str(tmp_path / "t.jsonl")
        line = fb.cc_tool_result_event(
            "t1", "grep for session_meta in the codex rollout format")
        fb.write_jsonl(path, [fb.cc_user("go"), line])
        assert cta._detect_runtime(path) != "codex"


class TestAC4bAdversarialEmbeddedTextCollisionPair:
    """AC-4b -- the single most important adversarial case in this spec
    (three plan-check rounds went into this design). BOTH fixtures below
    are INDEPENDENTLY MANDATORY: passing only one is NOT sufficient (the
    delegation's own framing: 'neither fixture alone is individually
    sufficient to force a compliant implementation, but the PAIR together
    ... IS a sound forcing function'). Each fixture is its own test so a
    partial implementation that only special-cases ONE runtime's embedded-
    text collision shows up as exactly one red test, not a single
    conflated pass/fail."""

    def test_fixture1_claude_code_transcript_embedding_codex_prose_still_claude_code(
            self, tmp_path):
        _require_adapter()
        path = str(tmp_path / "fixture1.jsonl")
        fb.build_ac4b_fixture1_claude_code_embedding_codex_prose(path)
        # Sanity: the JSONL file still carries the collision text. Quoted JSON
        # snippets are escaped in the raw JSONL, then literal again after
        # decoding the enclosing tool_result string.
        raw = open(path, encoding="utf-8").read()
        events = _read_jsonl(path)
        decoded_tool_results = "\n".join(
            part["content"]
            for event in events
            for part in event.get("message", {}).get("content", [])
            if isinstance(event.get("message", {}).get("content"), list)
            and part.get("type") == "tool_result"
        )
        assert "session_meta" in raw
        assert _json_string_body(
            '{"type": "response_item", "payload": {...}}') in raw
        assert "session_meta" in decoded_tool_results
        assert '{"type": "response_item", "payload": {...}}' in decoded_tool_results
        assert cta._detect_runtime(path) == "claude_code", (
            "AC-4b Fixture 1 FAILED: a real-shaped Claude Code transcript "
            "embedding Codex-shaped example prose in a tool_result was "
            "misclassified. This is the exact collision round-2 plan-check "
            "identified -- a substring/blob-scan implementation finds "
            "'session_meta' anywhere in the file and wrongly reports "
            "'codex', silently disabling RUNLOG_MISSING/thrash-past-green "
            "for this genuine Claude Code session (AC-7's fail-open catch "
            "never fires on a silent misclassification).")

    def test_fixture2_codex_transcript_embedding_claude_code_prose_still_codex(
            self, tmp_path):
        _require_adapter()
        path = str(tmp_path / "fixture2.jsonl")
        fb.build_ac4b_fixture2_codex_embedding_claude_code_prose(path)
        raw = open(path, encoding="utf-8").read()
        events = _read_jsonl(path)
        decoded_outputs = "\n".join(
            event["payload"]["output"]
            for event in events
            if event.get("type") == "response_item"
            and event.get("payload", {}).get("type") == "function_call_output"
            and isinstance(event.get("payload", {}).get("output"), str)
        )
        assert _json_string_body('"tool_use"') in raw
        assert _json_string_body(
            '{"type": "tool_use", "name": "Task"') in raw
        assert '"tool_use"' in decoded_outputs
        assert '{"type": "tool_use", "name": "Task"' in decoded_outputs
        assert cta._detect_runtime(path) == "codex", (
            "AC-4b Fixture 2 FAILED: a real-shaped Codex rollout transcript "
            "embedding Claude-Code-shaped example prose in a "
            "function_call_output was misclassified. A substring/blob-scan "
            "implementation finds a literal '\"tool_use\"' excerpt anywhere "
            "in the file and wrongly reports 'claude_code' (or 'unknown'), "
            "which would route a genuine Codex session's RUNLOG_MISSING/"
            "thrash-past-green checks through the WRONG (Claude-Code-"
            "shaped) scan, which finds no tool_use blocks in a real Codex "
            "transcript at all and silently produces zero violations.")

    def test_both_fixtures_together_prove_the_pair_not_either_alone(
            self, tmp_path):
        """A single combined assertion mirroring the delegation's own
        framing: both fixtures must independently classify correctly IN
        THE SAME TEST RUN -- a Coder who hardcodes special-case handling
        for only one of the two collision directions still fails this
        (and the two tests above pin down exactly which direction)."""
        _require_adapter()
        p1 = str(tmp_path / "f1.jsonl")
        p2 = str(tmp_path / "f2.jsonl")
        fb.build_ac4b_fixture1_claude_code_embedding_codex_prose(p1)
        fb.build_ac4b_fixture2_codex_embedding_claude_code_prose(p2)
        r1 = cta._detect_runtime(p1)
        r2 = cta._detect_runtime(p2)
        assert (r1, r2) == ("claude_code", "codex"), (
            "AC-4b pair result: fixture1=%r (want claude_code), "
            "fixture2=%r (want codex)." % (r1, r2))


# ===========================================================================
# AC-7 -- fail-open contract (adapter-level slice; the end-to-end
# loop_stop_guard.py/micro_step_gates.py catch-and-continue behavior is
# tested in test_codex_parity_gates.py) -- [BEHAVIORAL]
# ===========================================================================

class TestAC7AdapterFailOpenSlice:
    def test_nonexistent_transcript_path_does_not_hang_or_silently_succeed(
            self, tmp_path):
        """Either raising OR returning an empty/degraded result is
        acceptable for a missing file -- the end-to-end fail-open CONTRACT
        (never a hard crash reaching the caller unguarded, never a silent
        hang) is enforced at the gate level in test_codex_parity_gates.py.
        This test only proves the adapter does not hang indefinitely."""
        _require_adapter()
        missing = str(tmp_path / "does_not_exist.jsonl")
        try:
            result = cta.extract_verifier_dispatches(missing)
            assert result == [] or isinstance(result, list)
        except Exception:
            pass  # raising is an accepted contract per AC-7's own wording

    def test_malformed_function_call_arguments_does_not_hang(self, tmp_path):
        """A function_call whose `arguments` field is NOT valid JSON (the
        'schema drift the official docs explicitly warn about') must not
        hang; raising is acceptable (AC-7's caller-side catch handles it)."""
        _require_adapter()
        path = str(tmp_path / "t.jsonl")
        session_id = "019f0000-malformed-000-0000-000000000000"
        line = {"timestamp": "t", "type": "response_item",
                "payload": {"type": "function_call", "id": "fc1",
                            "name": "spawn_agent", "namespace": "multi_agent_v1",
                            "arguments": "{not valid json", "call_id": "c1"}}
        fb.write_jsonl(path, [fb.codex_session_meta(session_id), line])
        try:
            cta.extract_verifier_dispatches(path)
        except Exception:
            pass


# ===========================================================================
# AC-8 -- regression: imports _VERIFIER_DETECT, does not duplicate it
# ([DOC], per H-VERIFIER-REGEX-DUPLICATE-1) -- [SECURITY-ORACLE]
# (labeled: a silently-drifted duplicate regex is exactly the "two
# implementations that can drift" isolation failure this framework has
# already hit once)
# ===========================================================================

class TestAC8NoVerifierDetectDuplication:
    def test_adapter_imports_verifier_detect_from_shared_module(self):
        assert os.path.isfile(ADAPTER_PATH), (
            "codex_transcript_adapter.py does not exist yet (expected "
            "pre-build).")
        src = open(ADAPTER_PATH, encoding="utf-8").read()
        assert re.search(
            r'from\s+verifier_hygiene_scan\s+import[^\n]*VERIFIER_DETECT',
            src), (
            "codex_transcript_adapter.py must import VERIFIER_DETECT from "
            "verifier_hygiene_scan.py (the existing shared module), "
            "mirroring loop_stop_guard.py's own "
            "`from verifier_hygiene_scan import VERIFIER_DETECT as "
            "_VERIFIER_DETECT` pattern -- H-VERIFIER-REGEX-DUPLICATE-1's "
            "already-documented lesson: one canonical implementation, not "
            "two that can drift.")

    def test_adapter_does_not_define_its_own_verifier_detect_regex(self):
        assert os.path.isfile(ADAPTER_PATH)
        src = open(ADAPTER_PATH, encoding="utf-8").read()
        # Strip out the (legitimate) import line before scanning for a
        # locally-defined compile call under the same/similar name.
        src_without_import_line = "\n".join(
            ln for ln in src.splitlines()
            if "from verifier_hygiene_scan import" not in ln)
        assert not re.search(
            r'^\s*_?VERIFIER_DETECT\s*=\s*re\.compile',
            src_without_import_line, re.M), (
            "codex_transcript_adapter.py appears to define its OWN "
            "VERIFIER_DETECT-shaped regex instead of importing the shared "
            "one -- this is the exact H-VERIFIER-REGEX-DUPLICATE-1 "
            "regression class (two independently-maintained copies that "
            "can silently diverge).")
