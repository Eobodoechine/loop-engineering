"""Tests for Deliverable C (fallback docs) -- AC-16/AC-17 -- and the
bootstrap snippet files AC-14 depends on, spec-codex-parity-and-consent-
installer-2026-07-09.md.

Written BEFORE any implementation exists. Every test here MUST currently
fail (FileNotFoundError -- none of loop-guards/README.md,
loop-guards/bootstrap/CLAUDE_MD_SNIPPET.md, loop-guards/bootstrap/
AGENTS_MD_SNIPPET.md exist yet) -- correct and expected at this stage.

These are [DOC] tests per the role brief's DOC-vs-BEHAVIORAL rule: AC-16/
AC-17 are prose-completeness criteria about an artifact's TEXT, not a claim
about the world that needs to be executed. Per LOOP-M2 (spec<->code
contract), the JSON blocks the README promises are additionally parsed as
real JSON (not just grepped for keywords) to confirm they're not merely
prose that LOOKS like a JSON block.
"""
import json
import os
import re

import pytest

LOOP_GUARDS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(LOOP_GUARDS_DIR, "README.md")
CLAUDE_SNIPPET = os.path.join(LOOP_GUARDS_DIR, "bootstrap", "CLAUDE_MD_SNIPPET.md")
AGENTS_SNIPPET = os.path.join(LOOP_GUARDS_DIR, "bootstrap", "AGENTS_MD_SNIPPET.md")

HOOK_EVENTS = ("Stop", "SubagentStop", "PreToolUse", "SessionStart",
               "UserPromptSubmit")


def _require_readme():
    if not os.path.isfile(README):
        pytest.fail("loop-guards/README.md does not exist yet (Deliverable "
                     "C, expected pre-build).")
    return open(README, encoding="utf-8").read()


def _fenced_json_blocks(text):
    """Extract the content of every ```json ... ``` fenced block (also
    tolerates a bare ``` fence containing a JSON object, since AC-16 does
    not mandate the `json` language tag specifically)."""
    blocks = re.findall(r'```(?:json)?\s*\n(.*?)```', text, re.S)
    parsed = []
    for b in blocks:
        try:
            parsed.append(json.loads(b))
        except Exception:
            continue
    return parsed


# ===========================================================================
# AC-16 -- Manual install section, both tools, copy-pasteable -- [DOC]
# ===========================================================================

class TestAC16ManualInstallSection:
    def test_readme_has_a_manual_install_section(self):
        text = _require_readme()
        assert re.search(r'manual install', text, re.I), (
            "README.md must contain a 'Manual install' section (AC-16).")

    def test_readme_contains_numbered_steps(self):
        text = _require_readme()
        assert re.search(r'^\s*\d+[.)]\s', text, re.M), (
            "AC-16 requires 'copy-pasteable, numbered steps' -- no numbered "
            "list found in README.md.")

    def test_readme_contains_a_real_parseable_json_block_for_claude_settings(
            self):
        text = _require_readme()
        assert "~/.claude/settings.json" in text, (
            "README.md must name the exact target file "
            "~/.claude/settings.json (AC-16).")
        blocks = _fenced_json_blocks(text)
        assert blocks, (
            "no real, parseable JSON code block found in README.md -- "
            "AC-16 requires 'the exact JSON block to add', not prose "
            "describing one.")
        # at least one JSON block must reference the hooks structure and
        # ALL 5 hook events (a partial manual-install snippet that only
        # shows e.g. Stop would leave a human silently under-protected).
        matches = [b for b in blocks if isinstance(b, dict) and "hooks" in b]
        assert matches, (
            "no JSON block in README.md has a top-level 'hooks' key -- "
            "found blocks: %r" % blocks)
        combined_keys = set()
        for b in matches:
            combined_keys |= set(b.get("hooks", {}).keys())
        missing = set(HOOK_EVENTS) - combined_keys
        assert not missing, (
            "README.md's Claude Code JSON block(s) are missing hook "
            "event(s) %r -- AC-16 requires the complete manual-install "
            "block, not a partial one that leaves some gates unenforced."
            % missing)

    def test_readme_contains_a_real_parseable_json_block_for_codex_hooks(self):
        text = _require_readme()
        assert "~/.codex/hooks.json" in text, (
            "README.md must name the exact target file "
            "~/.codex/hooks.json (AC-16).")
        blocks = _fenced_json_blocks(text)
        matches = [b for b in blocks if isinstance(b, dict) and "hooks" in b]
        # Distinguish the Codex block from the Claude Code block by proximity
        # to the "~/.codex/hooks.json" mention rather than assuming ordering.
        codex_idx = text.find("~/.codex/hooks.json")
        assert codex_idx != -1
        # Find the JSON fence nearest AFTER the codex path mention.
        after = text[codex_idx:]
        fence = re.search(r'```(?:json)?\s*\n(.*?)```', after, re.S)
        assert fence, (
            "no JSON code block found near the ~/.codex/hooks.json mention "
            "in README.md.")
        try:
            codex_block = json.loads(fence.group(1))
        except Exception as e:
            pytest.fail("the JSON block near ~/.codex/hooks.json in "
                        "README.md is not valid JSON: %r" % (e,))
        combined_keys = set(codex_block.get("hooks", {}).keys())
        missing = set(HOOK_EVENTS) - combined_keys
        assert not missing, (
            "README.md's Codex JSON block is missing hook event(s) %r"
            % missing)

    def test_readme_includes_the_hooks_trust_approval_reminder(self):
        """AC-16: '...plus the /hooks trust-approval reminder from AC-13'."""
        text = _require_readme()
        assert "/hooks" in text, (
            "README.md's manual-install section must include the /hooks "
            "trust-approval reminder (AC-13/AC-16) for a human who "
            "manually edits ~/.codex/hooks.json.")
        assert re.search(r'approve', text, re.I), text


# ===========================================================================
# AC-17 -- states plainly what breaks without the guards -- [DOC]
# ===========================================================================

class TestAC17WhatBreaksWithoutGuards:
    def test_readme_states_runlog_and_checkpoint_gates_become_advisory(self):
        text = _require_readme()
        assert re.search(r'run[- ]?log', text, re.I), (
            "README.md must describe what breaks without the guards: the "
            "run-log gate (RUNLOG_MISSING).")
        assert re.search(r'checkpoint|thrash', text, re.I), (
            "README.md must describe what breaks without the guards: the "
            "checkpoint/thrash-past-green gate.")
        assert re.search(r'advisory|no ?longer (enforced|block)|purely prose',
                         text, re.I), (
            "README.md must state the effect in plain terms -- the gates "
            "become 'purely advisory prose again' without the guards "
            "installed (AC-17's own wording), not merely mention their "
            "names.")


# ===========================================================================
# Bootstrap snippets (AC-14's own dependency, self-contained prose a fresh
# agent can act on with no other context) -- [DOC]
# ===========================================================================

class TestBootstrapSnippetsAreSelfContainedAndToolScoped:
    def test_claude_md_snippet_exists_and_names_the_tool_scoped_invocation(
            self):
        if not os.path.isfile(CLAUDE_SNIPPET):
            pytest.fail("loop-guards/bootstrap/CLAUDE_MD_SNIPPET.md does "
                        "not exist yet (expected pre-build).")
        text = open(CLAUDE_SNIPPET, encoding="utf-8").read()
        assert "detect_install_state.py" in text
        assert re.search(r'--tool\s+claude_code', text), (
            "CLAUDE_MD_SNIPPET.md must invoke detect_install_state.py "
            "with the explicit, tool-scoped `--tool claude_code` flag "
            "(AC-14) -- never an aggregate/no-flag check.")
        assert "--tool codex" not in text, (
            "CLAUDE_MD_SNIPPET.md queries the WRONG tool -- it must check "
            "claude_code, not codex, from the Claude-Code-read file.")

    def test_agents_md_snippet_exists_and_names_the_tool_scoped_invocation(
            self):
        if not os.path.isfile(AGENTS_SNIPPET):
            pytest.fail("loop-guards/bootstrap/AGENTS_MD_SNIPPET.md does "
                        "not exist yet (expected pre-build).")
        text = open(AGENTS_SNIPPET, encoding="utf-8").read()
        assert "detect_install_state.py" in text
        assert re.search(r'--tool\s+codex', text), (
            "AGENTS_MD_SNIPPET.md must invoke detect_install_state.py "
            "with the explicit, tool-scoped `--tool codex` flag (AC-14).")
        assert "--tool claude_code" not in text, (
            "AGENTS_MD_SNIPPET.md queries the WRONG tool -- it must check "
            "codex, not claude_code, from the AGENTS.md-read file.")

    def test_snippets_explain_effect_before_asking_for_accept_reject(self):
        """AC-14: 'summarize in plain language what the guards do ...
        and their effect ... then explicitly ask the human to accept or
        reject'."""
        for path in (CLAUDE_SNIPPET, AGENTS_SNIPPET):
            if not os.path.isfile(path):
                pytest.fail("%s does not exist yet (expected pre-build)."
                            % path)
            text = open(path, encoding="utf-8").read()
            assert re.search(r'accept|reject|install', text, re.I), (
                "%s must instruct the agent to explicitly ask the human to "
                "accept or reject." % path)
            assert re.search(r'run[- ]?log|checkpoint', text, re.I), (
                "%s must summarize what the guards do (run-log + "
                "checkpoint enforcement) before asking for accept/reject."
                % path)
