"""AC1/AC2/AC3 (custom-subagent-types spec, runs/2026-07-02_153538-custom-subagent-types):
structural checks on the 5 custom Claude Code subagent-type definitions that this build
must create at BOTH user scope (~/.claude/agents/<name>.md) and project scope
(~/Claude/loop/.claude/agents/<name>.md).

[DOC] tests -- these check facts about the artifact's text/structure (file existence,
byte-identity, YAML validity, required frontmatter keys, disallowedTools content, and body
shape), not runtime behavior. The "body is short, not the full pasted role-brief" check is
the one that actually catches Deviation #2 (see spec.md) being silently dropped -- a Coder
who pastes the full multi-KB role brief into the custom-agent body instead of a short
pointer-stub would still satisfy every other AC1-3 check, so that specific assertion is the
load-bearing one in this file.

This file also covers AC4 (orchestrator.md dispatch-section edit) with grep-based [DOC]
tests confirming the edited file still retains the generic dispatch template and the
plan-check-Verifier description-prefix requirement, AND states the new subagent_type
instruction -- see OrchestratorDispatchSectionEdit below.

These tests are written BEFORE the Coder creates any of the 10 target files or edits
orchestrator.md, and are EXPECTED TO FAIL (red) until the Coder delivers.

Run with:
    python3 -m pytest loop-team/tests/test_custom_subagent_types.py -q
"""
import os
import re
import unittest

import yaml

USER_AGENTS_DIR = os.path.expanduser("~/.claude/agents")
PROJECT_AGENTS_DIR = os.path.expanduser("~/Claude/loop/.claude/agents")

ORCHESTRATOR_MD = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "orchestrator.md"
)

AGENT_NAMES = ["coder", "verifier", "test-writer", "researcher", "plan-check-verifier"]

# Deviation #2 (spec.md lines 70-85): body must be a short pointer-stub (~10-20 lines),
# NOT the full pasted role-brief text (13-23KB per spec line 72). Give real headroom above
# the spec's own "~10-20 lines" estimate before calling it a violation, while still being
# far below what a pasted role-brief body would look like (role briefs run to hundreds of
# lines / many KB -- see loop-team/roles/*.md).
MAX_BODY_LINES = 30

FRONTMATTER_RE = re.compile(r"\A---\n(.*?\n)---\n(.*)\Z", re.DOTALL)


def _paths_for(name):
    return (
        os.path.join(USER_AGENTS_DIR, "%s.md" % name),
        os.path.join(PROJECT_AGENTS_DIR, "%s.md" % name),
    )


def _split_frontmatter(text):
    """Return (yaml_text, body_text) or (None, None) if no frontmatter block found."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, None
    return m.group(1), m.group(2)


class FileStructureExistsAndIdentical(unittest.TestCase):
    """AC1: both copies of all 5 files exist and are byte-identical."""

    def test_all_ten_files_exist(self):
        missing = []
        for name in AGENT_NAMES:
            for p in _paths_for(name):
                if not os.path.isfile(p):
                    missing.append(p)
        self.assertEqual(
            missing, [],
            "missing custom-subagent-type files (expected before the Coder delivers, "
            "should be empty after): %r" % (missing,),
        )

    def test_each_pair_is_byte_identical(self):
        for name in AGENT_NAMES:
            user_p, proj_p = _paths_for(name)
            if not (os.path.isfile(user_p) and os.path.isfile(proj_p)):
                self.fail("cannot compare %r: one or both copies missing" % (name,))
            with open(user_p, "rb") as f:
                user_bytes = f.read()
            with open(proj_p, "rb") as f:
                proj_bytes = f.read()
            self.assertEqual(
                user_bytes, proj_bytes,
                "%s.md differs between user scope (%s) and project scope (%s) -- "
                "spec requires byte-identical deployment (Deviation #1)"
                % (name, user_p, proj_p),
            )


class FrontmatterValidYaml(unittest.TestCase):
    """AC1: each of the 10 files parses as valid YAML frontmatter + Markdown body."""

    def test_frontmatter_parses_as_valid_yaml_for_all_ten_files(self):
        for name in AGENT_NAMES:
            for p in _paths_for(name):
                if not os.path.isfile(p):
                    self.fail("missing file, cannot parse frontmatter: %r" % (p,))
                text = open(p, encoding="utf-8").read()
                yaml_text, body = _split_frontmatter(text)
                self.assertIsNotNone(
                    yaml_text,
                    "%r has no '---'-delimited YAML frontmatter block" % (p,),
                )
                try:
                    parsed = yaml.safe_load(yaml_text)
                except yaml.YAMLError as e:
                    self.fail("%r frontmatter failed to parse as YAML: %r" % (p, e))
                self.assertIsInstance(
                    parsed, dict,
                    "%r frontmatter parsed but is not a mapping: %r" % (p, parsed),
                )


class FrontmatterRequiredKeys(unittest.TestCase):
    """AC1: each file's frontmatter has name, description, tools and/or
    disallowedTools, and model."""

    def _load(self, p):
        text = open(p, encoding="utf-8").read()
        yaml_text, body = _split_frontmatter(text)
        if yaml_text is None:
            self.fail("%r has no YAML frontmatter block" % (p,))
        return yaml.safe_load(yaml_text), body

    def test_required_keys_present_for_all_ten_files(self):
        for name in AGENT_NAMES:
            for p in _paths_for(name):
                if not os.path.isfile(p):
                    self.fail("missing file: %r" % (p,))
                fm, _ = self._load(p)
                for key in ("name", "description"):
                    self.assertIn(key, fm, "%r frontmatter missing required key %r" % (p, key))
                self.assertTrue(
                    "tools" in fm or "disallowedTools" in fm,
                    "%r frontmatter has neither 'tools' nor 'disallowedTools'" % (p,),
                )
                self.assertIn("model", fm, "%r frontmatter missing required key 'model'" % (p,))

    def test_name_field_matches_the_filename_slug(self):
        for name in AGENT_NAMES:
            for p in _paths_for(name):
                if not os.path.isfile(p):
                    self.fail("missing file: %r" % (p,))
                fm, _ = self._load(p)
                self.assertEqual(
                    str(fm.get("name", "")), name,
                    "%r frontmatter 'name' field (%r) does not match expected %r"
                    % (p, fm.get("name"), name),
                )


class AgentToolStructurallyExcluded(unittest.TestCase):
    """AC2: 'Agent' must appear in disallowedTools for every one of the 5 custom types
    (grep-checkable per the spec) -- this is what makes a dispatched sub-agent
    MECHANICALLY incapable of calling Agent/Task, closing the sub-agent-punting failure
    at the tool-availability level."""

    def test_agent_in_disallowed_tools_for_all_ten_files(self):
        for name in AGENT_NAMES:
            for p in _paths_for(name):
                if not os.path.isfile(p):
                    self.fail("missing file: %r" % (p,))
                text = open(p, encoding="utf-8").read()
                yaml_text, _ = _split_frontmatter(text)
                self.assertIsNotNone(yaml_text, "%r has no frontmatter" % (p,))
                fm = yaml.safe_load(yaml_text)
                disallowed = fm.get("disallowedTools", "")
                # disallowedTools may be a YAML list or a comma-separated string per the
                # research doc's schema -- normalize both shapes to a token list.
                if isinstance(disallowed, str):
                    tokens = [t.strip() for t in disallowed.split(",")]
                elif isinstance(disallowed, list):
                    tokens = [str(t).strip() for t in disallowed]
                else:
                    tokens = []
                self.assertIn(
                    "Agent", tokens,
                    "%r does not list 'Agent' in disallowedTools (tokens found: %r) -- "
                    "a dispatched sub-agent using this type would NOT be structurally "
                    "prevented from spawning its own delegate chain" % (p, tokens),
                )


class BodyIsPointerStubNotPastedRoleBrief(unittest.TestCase):
    """AC3: each file's body (after frontmatter) contains a '# Role:' header line AND is
    a SHORT pointer-stub, not the full multi-KB role-brief text pasted inline (Deviation
    #2). This is the check that actually catches Deviation #2 being silently dropped: a
    Coder who pastes roles/coder.md's full body into the custom-agent file would still
    pass every AC1/AC2 check above, so body length is the discriminating signal here."""

    ROLE_HEADER_RE = re.compile(r"^#\s*Role:", re.MULTILINE)

    def test_body_contains_role_header_line(self):
        for name in AGENT_NAMES:
            for p in _paths_for(name):
                if not os.path.isfile(p):
                    self.fail("missing file: %r" % (p,))
                text = open(p, encoding="utf-8").read()
                _, body = _split_frontmatter(text)
                self.assertIsNotNone(body, "%r has no frontmatter/body split" % (p,))
                self.assertRegex(
                    body, self.ROLE_HEADER_RE,
                    "%r body does not contain a '# Role:' header line" % (p,),
                )

    def test_body_instructs_reading_the_canonical_role_brief_file(self):
        # Deviation #2: body must instruct a mandatory first Read of the canonical
        # loop-team/roles/*.md file -- not just have a Role header.
        for name in AGENT_NAMES:
            for p in _paths_for(name):
                if not os.path.isfile(p):
                    self.fail("missing file: %r" % (p,))
                text = open(p, encoding="utf-8").read()
                _, body = _split_frontmatter(text)
                self.assertIsNotNone(body, "%r has no frontmatter/body split" % (p,))
                low = body.lower()
                self.assertIn(
                    "read", low,
                    "%r body does not mention reading the canonical role-brief file" % (p,),
                )
                self.assertIn(
                    "loop-team/roles/", body,
                    "%r body does not reference a loop-team/roles/*.md path" % (p,),
                )

    def test_body_is_short_pointer_stub_not_full_pasted_role_brief(self):
        """The load-bearing check: a body under MAX_BODY_LINES lines. A Coder who pastes
        the full role-brief text (roles/coder.md etc. run to 100+ lines / many KB) in
        place of the short pointer-stub the spec requires must fail this test, even
        though such a body would still satisfy every other AC1-3 check above."""
        for name in AGENT_NAMES:
            for p in _paths_for(name):
                if not os.path.isfile(p):
                    self.fail("missing file: %r" % (p,))
                text = open(p, encoding="utf-8").read()
                _, body = _split_frontmatter(text)
                self.assertIsNotNone(body, "%r has no frontmatter/body split" % (p,))
                stripped_lines = [ln for ln in body.splitlines() if ln.strip()]
                self.assertLessEqual(
                    len(stripped_lines), MAX_BODY_LINES,
                    "%r body has %d non-blank lines (max %d) -- looks like the full "
                    "role-brief text was pasted in instead of a short pointer-stub "
                    "(Deviation #2 silently dropped)"
                    % (p, len(stripped_lines), MAX_BODY_LINES),
                )

    def test_body_does_not_contain_full_role_brief_verbatim(self):
        """Stronger, content-based version of the same check: the custom-agent body must
        NOT contain large verbatim chunks of the canonical roles/*.md file it points to.
        Uses each type's own corresponding roles/*.md source file (coder -> coder.md,
        verifier / plan-check-verifier -> verifier.md, test-writer -> test_writer.md,
        researcher -> researcher.md) and asserts none of that file's real content lines
        (stripped, non-trivial) leak verbatim into the custom-agent body."""
        roles_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "roles"
        )
        source_for = {
            "coder": "coder.md",
            "verifier": "verifier.md",
            "plan-check-verifier": "verifier.md",
            "test-writer": "test_writer.md",
            "researcher": "researcher.md",
        }
        for name in AGENT_NAMES:
            role_file = os.path.join(roles_dir, source_for[name])
            if not os.path.isfile(role_file):
                self.fail("canonical role brief missing, cannot compare: %r" % (role_file,))
            role_lines = {
                ln.strip()
                for ln in open(role_file, encoding="utf-8")
                if len(ln.strip()) > 40  # ignore short/trivial lines (headers, blanks)
            }
            for p in _paths_for(name):
                if not os.path.isfile(p):
                    self.fail("missing file: %r" % (p,))
                text = open(p, encoding="utf-8").read()
                _, body = _split_frontmatter(text)
                self.assertIsNotNone(body, "%r has no frontmatter/body split" % (p,))
                body_lines = {ln.strip() for ln in body.splitlines() if len(ln.strip()) > 40}
                leaked = role_lines & body_lines
                self.assertEqual(
                    leaked, set(),
                    "%r body contains %d substantial line(s) copied verbatim from %r -- "
                    "the full role-brief text appears to be pasted in rather than "
                    "pointed at (Deviation #2 violated): %r"
                    % (p, len(leaked), role_file, list(leaked)[:3]),
                )


class OrchestratorDispatchSectionEdit(unittest.TestCase):
    """AC4 [DOC]: orchestrator.md's 'How roles are dispatched' section must retain the
    exact description-field conventions (generic template + plan-check-Verifier prefix
    requirement) that hooks/loop_stop_guard.py's _CODER_DETECT/_VERIFIER_DETECT regexes
    key off -- see _tu_input() in loop_stop_guard.py, which matches against the Agent
    call's full serialized input, NOT subagent_type. AND must state the NEW instruction
    that subagent_type be set to match each custom type's name.

    These are grep-based checks against the file's current text; they intentionally do
    NOT re-derive the regex objects themselves (that would just restate the spec) -- the
    BEHAVIORAL half of this regression risk (that the regexes still actually match the
    new dispatch shape) is covered separately in
    hooks/test_loop_stop_guard.py::CustomSubagentTypeDispatchRegression, which imports
    and exercises the real hook logic.
    """

    def _read_orchestrator(self):
        if not os.path.isfile(ORCHESTRATOR_MD):
            self.fail("orchestrator.md not found at %r" % (ORCHESTRATOR_MD,))
        return open(ORCHESTRATOR_MD, encoding="utf-8").read()

    def test_generic_dispatch_template_still_present(self):
        text = self._read_orchestrator()
        # The literal generic template, e.g. `"<Role> for <task>"` -- unambiguous
        # evidence it wasn't removed/reworded away during the edit.
        self.assertIn(
            '"<Role> for <task>"', text,
            "orchestrator.md no longer contains the generic dispatch description "
            'template `"<Role> for <task>"` -- this is what _CODER_DETECT (\\bcoder '
            "for\\b) keys off once Oga fills in the role name",
        )

    def test_plan_check_verifier_description_prefix_requirement_still_present(self):
        text = self._read_orchestrator()
        self.assertIn(
            '"plan-check Verifier"', text,
            "orchestrator.md no longer states the literal requirement that plan-check "
            'Verifier dispatches\' description field begin with "plan-check Verifier" '
            "-- dropping this breaks _VERIFIER_DETECT's plan-?check verifier pattern",
        )
        # Must also still say this is a MUST/requirement, not just mention the phrase in
        # passing -- look for the requirement framing near the phrase.
        idx = text.find('"plan-check Verifier"')
        window = text[max(0, idx - 400): idx + 400]
        self.assertRegex(
            window.lower(), r"must (still )?begin|must begin|required",
            "orchestrator.md mentions 'plan-check Verifier' but the surrounding text no "
            "longer frames it as a MUST/required prefix rule",
        )

    def test_subagent_type_instruction_added(self):
        text = self._read_orchestrator()
        low = text.lower()
        self.assertIn(
            "subagent_type", low,
            "orchestrator.md does not mention subagent_type at all -- the spec requires "
            "a new instruction that subagent_type be set to match each custom type's name",
        )
        # Must reference at least the 5 custom type names somewhere near/after the
        # subagent_type instruction, confirming it's the NEW custom-type wiring and not
        # an unrelated pre-existing mention.
        for custom_name in ("coder", "verifier", "test-writer", "researcher",
                             "plan-check-verifier"):
            self.assertIn(
                custom_name, low,
                "orchestrator.md's subagent_type instruction does not mention the "
                "custom type name %r" % (custom_name,),
            )

    def test_prompt_field_instructed_to_carry_only_delegation_message(self):
        text = self._read_orchestrator()
        low = text.lower()
        # Spec requires stating the prompt field now carries ONLY the delegation/context
        # message, not the full role-brief text (since the custom type's own system
        # prompt now does the mandatory-first-Read instead).
        self.assertTrue(
            "role brief" in low or "role-brief" in low,
            "orchestrator.md's dispatch section no longer discusses role-brief content "
            "at all -- expected updated language about the prompt field no longer "
            "carrying the full role-brief text",
        )


if __name__ == "__main__":
    unittest.main()
