"""
Tests for loop-team session enforcement interventions.

Covers:
  AC1  - session_start.sh exits 0 when constraints file exists
  AC2  - session_start.sh outputs valid JSON with hookSpecificOutput.additionalContext
  AC3  - additionalContext is a non-empty string containing "dispatch"
  AC4  - session_start.sh exits 0 silently when constraints file does not exist
  AC5  - orchestrator-constraints.txt exists, is non-empty, and contains all four key rules
  AC6  - ~/.claude/settings.json contains SessionStart with matcher "startup"
  AC7  - orchestrator.md contains dispatch_check JSON structure with all four fields
  AC8  - dispatch_check structure appears BEFORE "If you are not invoking the Agent tool"
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Paths under test
# ---------------------------------------------------------------------------

LOOP_ROOT = Path.home() / "Claude" / "loop"
HOOKS_DIR = LOOP_ROOT / "hooks"
SESSION_SCRIPT = HOOKS_DIR / "session_start.sh"
CONSTRAINTS_FILE = HOOKS_DIR / "orchestrator-constraints.txt"
ORCHESTRATOR_MD = LOOP_ROOT / "loop-team" / "orchestrator.md"
SETTINGS_JSON = Path.home() / ".claude" / "settings.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_script(env_override=None) -> subprocess.CompletedProcess:
    """Run session_start.sh and capture stdout/stderr/returncode."""
    env = os.environ.copy()
    if env_override:
        env.update(env_override)
    return subprocess.run(
        ["bash", str(SESSION_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )


def run_script_with_fake_constraints(constraints_path: str) -> subprocess.CompletedProcess:
    """
    Run session_start.sh with LOOP_CONSTRAINTS_FILE overridden so the script
    reads from an arbitrary path.  The script must honour this env-var (or
    accept it as a positional arg) — the Coder decides the exact mechanism;
    we try the env-var convention first and fall back to positional arg.
    """
    env = os.environ.copy()
    env["LOOP_CONSTRAINTS_FILE"] = constraints_path
    result = subprocess.run(
        ["bash", str(SESSION_SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    # Fallback: try passing path as first positional argument
    if result.returncode != 0 and "LOOP_CONSTRAINTS_FILE" not in open(SESSION_SCRIPT).read():
        result = subprocess.run(
            ["bash", str(SESSION_SCRIPT), constraints_path],
            capture_output=True,
            text=True,
        )
    return result


# ---------------------------------------------------------------------------
# AC1 — script exits 0 when constraints file exists
# ---------------------------------------------------------------------------


class TestAC1_ScriptExitsZeroWithConstraints:
    def test_exits_zero_when_constraints_file_present(self):
        """session_start.sh must exit 0 when orchestrator-constraints.txt exists."""
        assert SESSION_SCRIPT.exists(), (
            f"session_start.sh not found at {SESSION_SCRIPT} — Coder must create it"
        )
        assert CONSTRAINTS_FILE.exists(), (
            f"orchestrator-constraints.txt not found at {CONSTRAINTS_FILE} — Coder must create it"
        )
        result = run_script()
        assert result.returncode == 0, (
            f"session_start.sh exited {result.returncode}.\n"
            f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
        )


# ---------------------------------------------------------------------------
# AC2 — output is valid JSON with hookSpecificOutput.additionalContext
# ---------------------------------------------------------------------------


class TestAC2_ValidJsonOutput:
    def test_stdout_is_valid_json(self):
        """session_start.sh stdout must be parseable as JSON."""
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        result = run_script()
        assert result.stdout.strip(), (
            "session_start.sh produced no stdout — expected a JSON object"
        )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            pytest.fail(
                f"stdout is not valid JSON: {exc}\nRaw stdout: {result.stdout!r}"
            )
        assert isinstance(payload, dict), (
            f"Expected JSON object at top level, got {type(payload).__name__}"
        )

    def test_hookSpecificOutput_key_present(self):
        """Top-level JSON must contain 'hookSpecificOutput' key."""
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        result = run_script()
        payload = json.loads(result.stdout)
        assert "hookSpecificOutput" in payload, (
            f"'hookSpecificOutput' key missing from JSON output.\nGot keys: {list(payload.keys())}"
        )

    def test_additionalContext_key_present(self):
        """hookSpecificOutput must contain 'additionalContext' key."""
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        result = run_script()
        payload = json.loads(result.stdout)
        hook_output = payload.get("hookSpecificOutput", {})
        assert "additionalContext" in hook_output, (
            f"'additionalContext' key missing from hookSpecificOutput.\n"
            f"hookSpecificOutput contents: {hook_output}"
        )

    def test_hook_event_name_present(self):
        """Claude Code 2.1 requires hookSpecificOutput.hookEventName."""
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        result = run_script()
        payload = json.loads(result.stdout)
        hook_output = payload.get("hookSpecificOutput", {})
        assert hook_output.get("hookEventName") == "SessionStart", (
            "SessionStart hook output must declare hookSpecificOutput.hookEventName "
            f"as 'SessionStart'. Got: {hook_output!r}"
        )


# ---------------------------------------------------------------------------
# AC3 — additionalContext is non-empty and contains "dispatch"
# ---------------------------------------------------------------------------


class TestAC3_AdditionalContextContent:
    def _get_additional_context(self) -> str:
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        result = run_script()
        payload = json.loads(result.stdout)
        return payload["hookSpecificOutput"]["additionalContext"]

    def test_additionalContext_is_string(self):
        ctx = self._get_additional_context()
        assert isinstance(ctx, str), (
            f"additionalContext must be a string, got {type(ctx).__name__}"
        )

    def test_additionalContext_is_non_empty(self):
        ctx = self._get_additional_context()
        assert ctx.strip(), "additionalContext must not be empty"

    def test_additionalContext_contains_dispatch(self):
        ctx = self._get_additional_context()
        assert "dispatch" in ctx.lower(), (
            f"additionalContext does not contain the word 'dispatch'.\n"
            f"Value: {ctx!r}"
        )


# ---------------------------------------------------------------------------
# AC4 — script exits 0 silently when constraints file does not exist
# ---------------------------------------------------------------------------


class TestAC4_SilentExitWhenNoConstraints:
    def test_exits_zero_without_output_when_file_missing(self):
        """
        When the constraints file is absent, session_start.sh must:
          - exit 0
          - produce no stdout
        """
        assert SESSION_SCRIPT.exists(), f"session_start.sh not found at {SESSION_SCRIPT}"
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = os.path.join(tmpdir, "nonexistent_constraints.txt")
            # Ensure the file really does not exist
            assert not os.path.exists(missing_path)
            result = run_script_with_fake_constraints(missing_path)
        assert result.returncode == 0, (
            f"script should exit 0 when constraints file is absent, "
            f"got {result.returncode}.\nstderr: {result.stderr!r}"
        )
        assert result.stdout.strip() == "", (
            f"script should produce no output when constraints file is absent.\n"
            f"Got stdout: {result.stdout!r}"
        )


# ---------------------------------------------------------------------------
# AC5 — orchestrator-constraints.txt exists, non-empty, contains four key rules
# ---------------------------------------------------------------------------


_REQUIRED_PHRASES = [
    "permitted outputs",
    "Agent tool call",
    "routing rationale",
    "self-check",
]


class TestAC5_ConstraintsFileContent:
    def test_constraints_file_exists(self):
        assert CONSTRAINTS_FILE.exists(), (
            f"orchestrator-constraints.txt not found at {CONSTRAINTS_FILE}"
        )

    def test_constraints_file_non_empty(self):
        assert CONSTRAINTS_FILE.exists(), f"orchestrator-constraints.txt missing"
        content = CONSTRAINTS_FILE.read_text(encoding="utf-8")
        assert content.strip(), "orchestrator-constraints.txt must not be empty"

    @pytest.mark.parametrize("phrase", _REQUIRED_PHRASES)
    def test_constraints_file_contains_required_phrase(self, phrase: str):
        assert CONSTRAINTS_FILE.exists(), f"orchestrator-constraints.txt missing"
        content = CONSTRAINTS_FILE.read_text(encoding="utf-8")
        assert phrase.lower() in content.lower(), (
            f"Required phrase {phrase!r} not found in orchestrator-constraints.txt.\n"
            f"(Case-insensitive search over {len(content)} chars.)"
        )


# ---------------------------------------------------------------------------
# AC6 — ~/.claude/settings.json has SessionStart with matcher "startup"
# ---------------------------------------------------------------------------


class TestAC6_SettingsJsonSessionStart:
    def test_settings_json_exists(self):
        assert SETTINGS_JSON.exists(), (
            f"~/.claude/settings.json not found at {SETTINGS_JSON}"
        )

    def test_settings_json_valid(self):
        assert SETTINGS_JSON.exists(), f"settings.json missing"
        try:
            json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            pytest.fail(f"settings.json is not valid JSON: {exc}")

    def test_session_start_key_present(self):
        assert SETTINGS_JSON.exists(), f"settings.json missing"
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        hooks = settings.get("hooks", {})
        assert "SessionStart" in hooks, (
            f"'SessionStart' key missing from settings.json hooks.\n"
            f"hooks keys: {list(hooks.keys())}"
        )

    def test_session_start_has_startup_matcher(self):
        """
        settings.json hooks.SessionStart must contain an entry with matcher: "startup".
        Claude Code reads SessionStart from inside the hooks object, not at top level.
        """
        assert SETTINGS_JSON.exists(), f"settings.json missing"
        settings = json.loads(SETTINGS_JSON.read_text(encoding="utf-8"))
        hooks = settings.get("hooks", {}).get("SessionStart", [])
        if isinstance(hooks, dict):
            hooks = [hooks]
        matchers = [h.get("matcher", "") for h in hooks if isinstance(h, dict)]
        assert "startup" in matchers, (
            f"No SessionStart hook entry with matcher 'startup' found.\n"
            f"Found matchers: {matchers}"
        )


# ---------------------------------------------------------------------------
# AC7 — orchestrator.md contains dispatch_check JSON structure with all four fields
# ---------------------------------------------------------------------------


_DISPATCH_FIELDS = ["task", "role", "why_this_role", "why_not_other"]


def _read_orchestrator() -> str:
    assert ORCHESTRATOR_MD.exists(), f"orchestrator.md missing at {ORCHESTRATOR_MD}"
    return ORCHESTRATOR_MD.read_text(encoding="utf-8")


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _assert_terms_near(text: str, anchor: str, terms: list[str], span: int = 1400):
    low = _squash(text)
    anchor_low = anchor.lower()
    pos = low.find(anchor_low)
    assert pos != -1, f"anchor {anchor!r} not found in orchestrator.md"
    window = low[max(0, pos - span): pos + len(anchor_low) + span]
    missing = [term for term in terms if term.lower() not in window]
    assert not missing, (
        f"terms missing near {anchor!r}: {missing}\n"
        f"window: {window[:900]!r}..."
    )


class TestAC7_OrchestratorDispatchCheck:
    def test_orchestrator_md_exists(self):
        assert ORCHESTRATOR_MD.exists(), (
            f"orchestrator.md not found at {ORCHESTRATOR_MD}"
        )

    def test_dispatch_check_key_present(self):
        assert ORCHESTRATOR_MD.exists(), f"orchestrator.md missing"
        content = ORCHESTRATOR_MD.read_text(encoding="utf-8")
        assert "dispatch_check" in content, (
            "'dispatch_check' not found in orchestrator.md"
        )

    @pytest.mark.parametrize("field", _DISPATCH_FIELDS)
    def test_dispatch_check_contains_field(self, field: str):
        assert ORCHESTRATOR_MD.exists(), f"orchestrator.md missing"
        content = ORCHESTRATOR_MD.read_text(encoding="utf-8")
        # Field should appear as a JSON key: "field"
        assert f'"{field}"' in content, (
            f"dispatch_check field {field!r} (as JSON key) not found in orchestrator.md"
        )


# ---------------------------------------------------------------------------
# AC8 — dispatch_check structure appears BEFORE "If you are not invoking the Agent tool"
# ---------------------------------------------------------------------------


class TestAC8_DispatchCheckOrderInOrchestrator:
    _SENTINEL = "If you are not invoking the Agent tool"

    def test_dispatch_check_before_sentinel(self):
        assert ORCHESTRATOR_MD.exists(), f"orchestrator.md missing"
        content = ORCHESTRATOR_MD.read_text(encoding="utf-8")

        dc_pos = content.find("dispatch_check")
        sentinel_pos = content.find(self._SENTINEL)

        assert dc_pos != -1, "'dispatch_check' not found in orchestrator.md"
        assert sentinel_pos != -1, (
            f"Sentinel text {self._SENTINEL!r} not found in orchestrator.md — "
            "cannot verify ordering"
        )
        assert dc_pos < sentinel_pos, (
            f"'dispatch_check' appears at char {dc_pos} but sentinel "
            f"{repr(self._SENTINEL)} appears at char {sentinel_pos}. "
            "'dispatch_check' must come FIRST."
        )


class TestSidecarResearchGovernorCorrectionSpec:
    """Regression checks for runs/2026-07-18_oga-third-revision-sidecar-correction/spec.md."""

    def test_bounded_read_only_orientation_and_synthesis_permission_is_removed(self):
        text = _read_orchestrator()
        low = _squash(text)
        forbidden = [
            "bounded read-only orientation and synthesis",
            "oga may do bounded read-only orientation",
            "oga must still read the repo structure",
            "read live framework files, inspect repo structure, search local files",
            "synthesize a brief, spec, or status update",
        ]
        assert not any(phrase in low for phrase in forbidden), (
            "orchestrator.md still grants Oga the accidental bounded read-only "
            "orientation/synthesis permission"
        )

    def test_permitted_outputs_are_only_dispatch_reporting_and_questions(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "Your permitted outputs",
            [
                "Agent tool calls",
                "Synthesis and reporting",
                "Questions to the user",
            ],
        )
        permitted_block = text[
            text.index("**Your permitted outputs"): text.index("**Self-check gate")
        ]
        assert "Bounded read-only orientation" not in permitted_block
        assert "repo structure" not in permitted_block

    def test_hard_non_worker_rule_lists_required_sub_agent_work(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "Everything else is sub-agent work",
            [
                "Research",
                "code-writing",
                "test-writing",
                "test-running",
                "verification",
                "web searches",
                "file edits",
                "repo archaeology",
                "documentation review",
                "appropriate sub-agent",
            ],
        )

    def test_self_check_stops_before_worker_work(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "Am I about to research",
            [
                "write code",
                "write tests",
                "run tests",
                "perform verification",
                "web search",
                "edit files",
                "repo archaeology",
                "review documentation",
                "If YES",
                "Agent tool call",
            ],
            span=1800,
        )

    def test_self_check_does_not_grant_broad_test_running_carveout(self):
        text = _read_orchestrator()
        self_check_block = text[
            text.index("**Self-check gate"): text.index("## Sidecar research governor")
        ]
        low = _squash(self_check_block)
        forbidden = [
            "running the deterministic verify/testmon gate command",
            "established oga action",
            "oga runs the impacted tests itself",
        ]
        assert "run tests" in low, "self-check must explicitly cover running tests"
        assert "worker output" in low, "self-check must distinguish worker output from harness evidence"
        assert "not permission for oga" in low, (
            "self-check must state deterministic harness evidence is not Oga test-running authority"
        )
        assert not any(phrase in low for phrase in forbidden), (
            "self-check still contains broad or conflicting Oga test-running permission"
        )

    def test_sidecar_trigger_is_third_spec_revision_only(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "third spec revision",
            [
                "same spec/build",
                "two plan-check rounds",
                "LOOP_GATE: PLAN_FAIL",
                "forced two revisions",
                "draft revision 3",
                "parallel/additive Researcher",
            ],
            span=2200,
        )

    def test_sidecar_is_parallel_additive_and_non_blocking_by_default(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "The sidecar is additive",
            [
                "does not stop and wait by default",
                "keeps moving",
                "normal spec revision",
                "plan-check process",
                "existing gate blocks",
                "pending sidecar is not",
                "stop condition",
            ],
            span=1800,
        )

    def test_sidecar_ledger_records_required_fields(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "sidecar research ledger",
            ["scope", "agent id", "status", "spec_affecting", "reconciliation"],
        )

    def test_reconciliation_outcomes_are_exhaustive(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "no_change",
            [
                "reconciliation",
                "exactly one",
                "cited reason",
                "spec_revised",
                "new spec hash",
                "fresh plan-check",
                "deferred_out_of_scope",
                "human",
            ],
        )

    def test_spec_affecting_sidecar_stales_prior_plan_check_credit(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "prior same-spec plan-check credit is stale",
            ["sidecar", "change design or scope", "spec hash", "rerun", "Test-writer", "Coder"],
            span=1600,
        )

    def test_direct_oga_framework_edits_remain_prohibited_and_route_to_coder(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "must not write",
            [
                "Oga",
                "source",
                "config",
                "hook",
                "role",
                "framework",
                "Coder",
                "plan-check",
            ],
        )

    def test_final_verification_remains_independent(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "final implementation verification",
            ["Oga", "cannot self-certify", "Verifier", "live-smoke", "harness"],
        )

    def test_research_to_edit_still_requires_plan_check(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "research-to-edit",
            ["requires", "plan-check", "before execution"],
        )

    def test_deterministic_checkpoint_language_is_not_worker_test_running(self):
        text = _read_orchestrator()
        low = _squash(text)
        forbidden = [
            "oga runs the impacted tests itself",
            "established oga action",
            "one carve-out: running the deterministic verify/testmon gate command",
        ]
        assert not any(phrase in low for phrase in forbidden), (
            "orchestrator.md still preserves the old broad deterministic harness carve-out"
        )
        _assert_terms_near(
            text,
            "Require the Verifier harness checkpoint",
            [
                "deterministic gate result",
                "not a grant",
                "Oga",
                "run project tests",
                "worker output",
                "dispatched roles",
                "deterministic harness gate",
            ],
            span=1400,
        )
        _assert_terms_near(
            text,
            "require the deterministic checkpoint result",
            [
                "main transcript",
                "pytest --testmon",
                "verify.py",
                "not permission",
                "Oga",
                "run tests",
                "select tests",
                "debug failures",
                "verification judgment",
                "worker output",
            ],
            span=1700,
        )


class TestDispatchCheckBlockIsStillCoupledToAgentCall:
    def test_dispatch_check_block_has_exact_four_fields(self):
        text = _read_orchestrator()
        candidates = re.findall(r"```json\s*(.*?)\s*```", text, re.S)
        dispatch_blocks = [candidate for candidate in candidates if '"dispatch_check"' in candidate]
        assert dispatch_blocks, "No fenced JSON dispatch_check block found in orchestrator.md"
        block = json.loads(dispatch_blocks[0])
        assert list(block) == ["dispatch_check"]
        assert list(block["dispatch_check"]) == _DISPATCH_FIELDS

    def test_dispatch_check_still_precedes_agent_call_coupling_warning(self):
        text = _read_orchestrator()
        dc_pos = text.find("dispatch_check")
        sentinel_pos = text.find("If you are not invoking the Agent tool")
        assert dc_pos != -1, "'dispatch_check' not found in orchestrator.md"
        assert sentinel_pos != -1, "Agent-call coupling warning missing"
        assert dc_pos < sentinel_pos

    def test_dispatching_still_means_real_agent_call_not_role_play(self):
        text = _read_orchestrator()
        _assert_terms_near(
            text,
            "Dispatching means one thing",
            ["Agent tool call", "Not a prose summary", "Not inline work"],
            span=3200,
        )
        low = _squash(text)
        assert "agent/task tool" in low
        assert "each role is a sub-agent" in low
