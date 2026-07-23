#!/usr/bin/env python3
"""Tests for hooks/dispatch_check_presence.py (H-BLOB-DISPLAY-1, Part B).

Covers spec.md AC5: `find_dispatch_check_blocks`/`evaluate_presence` correctly
parse a real, well-formed `dispatch_check` block (the exact JSON shape from
`orchestrator.md`'s own example), report `present=False` for text with none,
and report `complete=False` with the right `missing_keys` for a block missing
-- or emptying -- one or more of the 4 required keys (each tested
individually). Also the v3 unbalanced-brace adversarial fixture: a prose
value containing a lone, unmatched `{` character must still parse correctly
via `json.JSONDecoder().raw_decode()` (string/escape-aware), where a naive
brace-depth counter would be displaced from the object's true closing brace.

This module is new (hooks/dispatch_check_presence.py does not exist yet) --
these tests are RED until the Coder implements it, per Tier-1 test-writer
convention (tests before implementation).

Run: python3 -m pytest hooks/test_dispatch_check_presence.py -q
"""
import os
import sys

import pytest

HOOKS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HOOKS)
from dispatch_check_presence import find_dispatch_check_blocks, evaluate_presence  # noqa: E402

ORCH = os.path.expanduser("~/Claude/loop/loop-team/orchestrator.md")
REQUIRED_KEYS = ("task", "role", "why_this_role", "why_not_other")


def _real_orchestrator_dispatch_check_example():
    """Fixture-tautology guard: pull the REAL `dispatch_check` JSON block out
    of orchestrator.md's own "Required output structure before every Agent
    dispatch" section, rather than hand-typing a block that merely resembles
    it. Returns the raw fenced-code-block text (including the ```json fence)
    so a caller can embed it verbatim inside surrounding assistant prose,
    exactly as it would appear in a real transcript."""
    if not os.path.exists(ORCH):
        pytest.skip("orchestrator.md not found at documented root path")
    with open(ORCH, encoding="utf-8") as f:
        content = f.read()
    marker = "**Required output structure before every Agent dispatch:**"
    idx = content.index(marker)
    # The real example is the next ```json ... ``` fenced block after the
    # marker.
    fence_start = content.index("```json", idx)
    fence_end = content.index("```", fence_start + len("```json"))
    block = content[fence_start:fence_end + 3]
    assert '"dispatch_check"' in block, "orchestrator.md's example lost its dispatch_check key"
    for key in REQUIRED_KEYS:
        assert ('"%s"' % key) in block, (
            "orchestrator.md's real example no longer names required key %r" % key)
    return block


def _wrap_in_turn_prose(fenced_block, prefix="Dispatching now.\n", suffix="\nProceeding."):
    """Simulate the block appearing inside a larger assistant-turn text blob
    (surrounding prose before/after), not as the ENTIRE text -- the realistic
    shape find_dispatch_check_blocks must handle."""
    return prefix + fenced_block + suffix


class TestRealWellFormedBlockParses:
    """AC5, core case: a real, well-formed dispatch_check block (the exact
    JSON shape from orchestrator.md's own documented example) parses
    correctly."""

    def test_find_dispatch_check_blocks_returns_one_block_for_real_example(self):
        """[BEHAVIORAL] The real orchestrator.md example, embedded in
        surrounding turn prose, yields exactly one parsed block."""
        text = _wrap_in_turn_prose(_real_orchestrator_dispatch_check_example())
        blocks = find_dispatch_check_blocks(text)
        assert len(blocks) == 1, blocks

    def test_parsed_block_contains_all_four_required_keys_with_real_values(self):
        """[BEHAVIORAL] The single parsed block has all 4 required keys, and
        each value is the real placeholder-filled text from the doc's
        example (not empty, not missing)."""
        text = _wrap_in_turn_prose(_real_orchestrator_dispatch_check_example())
        blocks = find_dispatch_check_blocks(text)
        block = blocks[0]
        for key in REQUIRED_KEYS:
            assert key in block, block
            assert isinstance(block[key], str) and block[key].strip(), block

    def test_evaluate_presence_reports_present_and_complete_true(self):
        """[BEHAVIORAL] evaluate_presence on the real, well-formed example
        reports present=True, complete=True, missing_keys=[]."""
        text = _wrap_in_turn_prose(_real_orchestrator_dispatch_check_example())
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is True, result
        assert result["missing_keys"] == [], result


class TestNoBlockPresent:
    """AC5: present=False for text with no dispatch_check block at all."""

    def test_plain_prose_with_no_json_at_all_reports_present_false(self):
        """[BEHAVIORAL] Ordinary assistant turn text, no JSON anywhere."""
        result = evaluate_presence(
            "I'll dispatch a Coder sub-agent now to implement the fix.")
        assert result["present"] is False, result
        assert result["complete"] is False, result
        assert result["missing_keys"] == list(REQUIRED_KEYS), result

    def test_unrelated_json_block_reports_present_false(self):
        """[BEHAVIORAL] A DIFFERENT JSON object appears in the text (not a
        dispatch_check block at all) -- must not be misdetected as one."""
        text = 'Here is the config: {"unrelated": {"a": 1, "b": 2}}'
        result = evaluate_presence(text)
        assert result["present"] is False, result

    def test_find_dispatch_check_blocks_returns_empty_list_for_no_match(self):
        """[BEHAVIORAL] find_dispatch_check_blocks itself returns [] (not
        None, not a truthy sentinel) when nothing matches."""
        blocks = find_dispatch_check_blocks("nothing to see here")
        assert blocks == []


class TestMissingKeyIndividually:
    """AC5: complete=False with the correct missing_keys list when exactly
    one of the 4 required keys is absent entirely (each tested one at a
    time, not just as a group)."""

    def _block_missing_key(self, missing_key):
        fields = {
            "task": "fix the login bug",
            "role": "Coder",
            "why_this_role": "implementation work, not review",
            "why_not_other": "ruled out Verifier -- no code exists yet to verify",
        }
        del fields[missing_key]
        body = ",\n    ".join('"%s": "%s"' % (k, v) for k, v in fields.items())
        return '{"dispatch_check": {\n    %s\n  }}' % body

    @pytest.mark.parametrize("missing_key", REQUIRED_KEYS)
    def test_each_key_missing_entirely_reports_correct_missing_keys(self, missing_key):
        """[BEHAVIORAL] Parametrized over each of the 4 required keys: when
        that key is absent from an otherwise well-formed block, present=True
        (the block itself still parses), complete=False, and missing_keys ==
        [that exact key]."""
        text = self._block_missing_key(missing_key)
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is False, result
        assert result["missing_keys"] == [missing_key], result


class TestKeyPresentButEmptyStringIndividually:
    """AC5: complete=False with the correct missing_keys list when exactly
    one of the 4 required keys is present but an empty string (not absent --
    a distinct case from 'missing entirely'), each tested individually."""

    def _block_with_empty_key(self, empty_key):
        fields = {
            "task": "fix the login bug",
            "role": "Coder",
            "why_this_role": "implementation work, not review",
            "why_not_other": "ruled out Verifier -- no code exists yet to verify",
        }
        fields[empty_key] = ""
        body = ",\n    ".join('"%s": "%s"' % (k, v) for k, v in fields.items())
        return '{"dispatch_check": {\n    %s\n  }}' % body

    @pytest.mark.parametrize("empty_key", REQUIRED_KEYS)
    def test_each_key_present_but_empty_string_reports_correct_missing_keys(self, empty_key):
        """[BEHAVIORAL] Parametrized over each of the 4 required keys: when
        that key is present but an empty string, present=True, complete=
        False, and missing_keys == [that exact key] -- proving evaluate_
        presence treats empty-after-strip the same as absent, per its own
        documented contract."""
        text = self._block_with_empty_key(empty_key)
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is False, result
        assert result["missing_keys"] == [empty_key], result

    @pytest.mark.parametrize("empty_key", REQUIRED_KEYS)
    def test_each_key_whitespace_only_also_treated_as_empty(self, empty_key):
        """[BEHAVIORAL] A value that is whitespace-only (e.g. '   ') must be
        treated the same as an empty string, per evaluate_presence's own
        documented .strip()-based contract -- not naively truthy-checked."""
        fields = {
            "task": "fix the login bug",
            "role": "Coder",
            "why_this_role": "implementation work, not review",
            "why_not_other": "ruled out Verifier -- no code exists yet to verify",
        }
        fields[empty_key] = "   "
        body = ",\n    ".join('"%s": "%s"' % (k, v) for k, v in fields.items())
        text = '{"dispatch_check": {\n    %s\n  }}' % body
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is False, result
        assert result["missing_keys"] == [empty_key], result


class TestMultipleKeysMissingAtOnce:
    """Sanity companion (not explicitly enumerated in AC5's per-key wording,
    but implied by evaluate_presence's own documented contract): more than
    one required key missing/empty at once must all be reported, not just
    the first one found."""

    def test_two_keys_missing_reports_both_in_missing_keys(self):
        """[BEHAVIORAL] task present, role present, why_this_role missing,
        why_not_other empty -- both must appear in missing_keys."""
        text = ('{"dispatch_check": {"task": "fix bug", "role": "Coder", '
                '"why_not_other": ""}}')
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is False, result
        assert set(result["missing_keys"]) == {"why_this_role", "why_not_other"}, result


class TestUnbalancedBraceAdversarialFixture:
    """AC5 (v3, round-2 state-completeness gap): a prose value containing a
    LONE, UNMATCHED '{' character (one '{', zero '}') displaces a naive
    brace-depth counter's depth-zero crossing point away from the object's
    true closing brace on this input -- only a string/escape-aware parser
    (json.JSONDecoder().raw_decode) recovers the correct result. This is
    explicitly NOT the v2 fixture ("a dict literal {'a': 1}", a BALANCED
    pair that would let a still-broken counter cancel out and pass by
    accident) -- this fixture actually discriminates fixed-from-broken."""

    def _unbalanced_brace_block(self, trailing_prose="\nAll set, proceeding."):
        why_this_role = "note: see the { config section for details"
        assert why_this_role.count("{") == 1
        assert why_this_role.count("}") == 0
        block = (
            '{"dispatch_check": {'
            '"task": "fix the login bug", '
            '"role": "Coder", '
            '"why_this_role": "%s", '
            '"why_not_other": "ruled out Verifier -- no code exists yet"'
            '}}'
        ) % why_this_role
        return block + trailing_prose

    def test_unbalanced_brace_in_prose_value_still_parses_present_and_complete(self):
        """[BEHAVIORAL] The core v3 assertion: present=True AND complete=True
        despite the unmatched '{' inside why_this_role's prose value."""
        text = self._unbalanced_brace_block()
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is True, result
        assert result["missing_keys"] == [], result

    def test_unbalanced_brace_fixture_recovers_the_literal_prose_value(self):
        """[BEHAVIORAL] Stronger than presence/completeness alone: the parsed
        why_this_role value must be recovered VERBATIM (proving the parser
        actually found the true closing brace, not some other boundary that
        happens to also satisfy the 4-key completeness check)."""
        text = self._unbalanced_brace_block()
        blocks = find_dispatch_check_blocks(text)
        assert len(blocks) == 1, blocks
        assert blocks[0]["why_this_role"] == "note: see the { config section for details", blocks[0]

    def test_unbalanced_brace_fixture_with_trailing_prose_containing_braces(self):
        """[BEHAVIORAL] Adversarial escalation: trailing prose AFTER the
        block also contains stray brace characters (a second, unrelated
        excursion) -- must not affect this block's own correct parse."""
        text = self._unbalanced_brace_block(
            trailing_prose="\nSeparately, { note the other module also uses "
                            "braces in its config } for something else.")
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is True, result


class TestMalformedJsonSkipPathContract:
    """AC5 (v5, round-4 state-completeness gap): the malformed-JSON skip path
    (`except Exception: continue` inside find_dispatch_check_blocks) has an
    explicit contract -- a genuinely truncated/malformed dispatch_check body
    (NOT the unbalanced-brace-in-prose-value case above, which IS valid JSON
    once correctly parsed -- actually invalid JSON) must silently collapse to
    present=False, identical to "no block ever attempted." A hook that
    cannot parse a block must never claim complete=True for it -- fail
    toward under-counting, never over-counting, since Part B's whole purpose
    is calibration data quality.

    This fixture is deliberately an UNTERMINATED STRING VALUE, not a brace-
    position trick: per the spec's own reasoning, a balanced-brace case could
    accidentally self-correct (a still-broken hand-rolled counter might
    happen to land on the right boundary by luck), but an unterminated
    string is guaranteed to raise json.JSONDecodeError from
    json.JSONDecoder().raw_decode regardless of implementation approach --
    there is no valid closing-brace position to accidentally recover, since
    the string literal itself was never closed. Confirmed directly (not
    assumed): text ends immediately mid-string, with ZERO characters --
    and in particular no stray closing quote of any kind -- anywhere after
    the malformed point, so there is no way for the underlying parser to
    stumble onto an accidental close."""

    def _unterminated_string_block(self):
        # "why_this_role"'s value opens a string with a `"` and is never
        # closed -- the text simply ends there. No closing quote, no closing
        # brace, nothing at all follows the malformed point.
        text = ('{"dispatch_check": {"task": "fix the login bug", '
                '"role": "Coder", '
                '"why_this_role": "this value never gets closed off, it just trails')
        assert not text.endswith('"'), (
            "fixture sanity: must not end on a quote, or the string would "
            "accidentally be terminated")
        return text

    def test_dispatch_check_regex_prefix_matches_the_malformed_fixture(self):
        """[BEHAVIORAL] Sanity precondition: _DISPATCH_CHECK_RE's own prefix
        (the literal '"dispatch_check": {') really is present in this
        fixture -- proving the exception path, not a regex non-match, is
        what's under test here."""
        import re
        prefix_re = re.compile(r'"dispatch_check"\s*:\s*\{', re.I)
        assert prefix_re.search(self._unterminated_string_block())

    def test_unterminated_string_value_raises_jsondecodeerror_directly(self):
        """[BEHAVIORAL] Ground-truth probe against the stdlib parser itself
        (independent of this module's own wrapping): raw_decode on this
        fixture genuinely raises JSONDecodeError -- confirming the fixture
        exercises real invalid JSON, not a construction that happens to
        parse by accident."""
        import json as _json
        text = self._unterminated_string_block()
        decoder = _json.JSONDecoder()
        start = text.index("{", text.index('"dispatch_check"'))
        with pytest.raises(_json.JSONDecodeError):
            decoder.raw_decode(text, start)

    def test_find_dispatch_check_blocks_returns_empty_list_for_malformed_body(self):
        """[BEHAVIORAL] The core AC5 v5 assertion: find_dispatch_check_blocks
        must return [] (the except-Exception-continue skip path), not raise,
        and not return a partial/garbage block."""
        blocks = find_dispatch_check_blocks(self._unterminated_string_block())
        assert blocks == [], blocks

    def test_evaluate_presence_reports_present_false_for_text_with_only_malformed_block(self):
        """[BEHAVIORAL] evaluate_presence on text containing ONLY this
        malformed block reports present=False, complete=False, and
        missing_keys == all 4 required keys -- identical to the "no block
        ever attempted" case, making explicit that "attempted but malformed"
        is intentionally folded into "absent," never surfaced as a false
        complete=True."""
        result = evaluate_presence(self._unterminated_string_block())
        assert result["present"] is False, result
        assert result["complete"] is False, result
        assert result["missing_keys"] == list(REQUIRED_KEYS), result


class TestMultipleBlocksInOneText:
    """evaluate_presence's own documented contract: 'usually zero or one,
    but never assume exactly one' -- if multiple dispatch_check blocks
    appear (e.g. two Agent dispatches drafted in one turn), the BEST one
    (fewest missing keys) determines the reported result."""

    def test_incomplete_then_complete_block_reports_complete_true(self):
        """[BEHAVIORAL] First block is missing a key, second block (later in
        the text) is fully complete -- overall result must be complete=True,
        proving evaluate_presence doesn't just examine the FIRST match."""
        incomplete = '{"dispatch_check": {"task": "a", "role": "Coder"}}'
        complete = ('{"dispatch_check": {"task": "b", "role": "Verifier", '
                    '"why_this_role": "independent check", '
                    '"why_not_other": "not a build step"}}')
        text = incomplete + "\n...more text...\n" + complete
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is True, result
        assert result["missing_keys"] == [], result

    def test_two_incomplete_blocks_reports_the_smaller_missing_set(self):
        """[BEHAVIORAL] Neither block is complete, but one is missing fewer
        keys than the other -- missing_keys must reflect the BEST (smallest)
        missing set, per evaluate_presence's documented tie-breaking."""
        missing_three = '{"dispatch_check": {"task": "a"}}'
        missing_one = ('{"dispatch_check": {"task": "b", "role": "Coder", '
                       '"why_this_role": "implementation", '
                       '"why_not_other": ""}}')
        text = missing_three + "\n...\n" + missing_one
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is False, result
        assert result["missing_keys"] == ["why_not_other"], result


class TestNonStringKeyValueTreatedAsMissing:
    """Type-robustness companion to AC5: evaluate_presence's own documented
    contract checks `isinstance(b.get(k), str) and b.get(k).strip()` -- a
    non-string value (e.g. a required key holding a number or null) must be
    treated as missing, not crash the evaluator."""

    def test_null_value_for_a_required_key_is_treated_as_missing(self):
        """[BEHAVIORAL] why_not_other is JSON null (parses to Python None,
        not a string) -- must be reported as missing, no exception raised."""
        text = ('{"dispatch_check": {"task": "a", "role": "Coder", '
                '"why_this_role": "b", "why_not_other": null}}')
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is False, result
        assert result["missing_keys"] == ["why_not_other"], result

    def test_numeric_value_for_a_required_key_is_treated_as_missing(self):
        """[BEHAVIORAL] role is a JSON number, not a string -- must be
        reported as missing, no exception raised."""
        text = ('{"dispatch_check": {"task": "a", "role": 42, '
                '"why_this_role": "b", "why_not_other": "c"}}')
        result = evaluate_presence(text)
        assert result["present"] is True, result
        assert result["complete"] is False, result
        assert result["missing_keys"] == ["role"], result


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
