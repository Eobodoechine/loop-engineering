"""Tests for research_authenticity_check.py's new genre "E" (Evidence-Gate
Phase 5, spec: loop-team/runs/2026-07-09_evidence-gate-phase5/specs/spec.md,
Item 4 -- ACs 9-11).

DELIBERATELY a separate, standalone file from
loop-team/harness/test_research_authenticity_check.py (which covers genres
A-D only and is left COMPLETELY UNTOUCHED by this dispatch) -- NOT because
this codebase avoids extending that file in place across builds (it has
precedent for doing so, e.g. its own AC1-8 "Mode D optional fields" banner),
but because THIS phase's own AC12 ("full existing test suites... remain
green") separately cross-checks test_research_authenticity_check.py by name
in test_evidence_gate_phase5_full_suite_regression.py as a suite that must
ALREADY be green TODAY, before any Phase 5 code lands. Appending these new,
deliberately-expected-to-currently-fail genre-E tests directly into that
file would make AC12's own precondition false on day one for a reason that
has nothing to do with a genre A-D regression -- keeping this genre-E
coverage in its own file avoids that self-conflict cleanly.

Written BEFORE genre E exists (research_authenticity_check.py's own module
already exists and imports fine -- MODE_FIELDS["E"] etc. and detect_mode()'s
new early branch do not exist yet) -- every test below is EXPECTED to fail
with a real assertion failure (detect_mode() returning "A" instead of "E",
since genre E's vocabulary currently has no dedicated scoring branch and
falls through to the generic A-D overlap loop) until the Coder builds it,
per roles/test_writer.md's own header. This is a real AssertionError, not an
ImportError/ModuleNotFoundError -- research_authenticity_check.py itself
already exists; only its genre-E additions are missing.

Fixture/import conventions match
loop-team/harness/test_research_authenticity_check.py exactly (subprocess
CLI for the primary public-interface test, a couple of in-process unit-level
calls for finer-grained edge cases -- matching that file's own stated
convention).

Run: python3 -m pytest loop-team/harness/test_research_authenticity_check_genre_e.py -q
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "research_authenticity_check.py")

sys.path.insert(0, HERE)
import research_authenticity_check as rac  # noqa: E402 -- module exists; genre-E additions do not


def _write(tmpdir, name, text):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _run(path):
    """Invoke the real CLI: python3 research_authenticity_check.py <saved_file_path>.

    Returns (exit_code, parsed_json_or_None, raw_stdout, raw_stderr).
    Matches test_research_authenticity_check.py's own identical helper.
    """
    p = subprocess.run(
        [sys.executable, SCRIPT, path],
        capture_output=True, text=True, timeout=30,
    )
    try:
        data = json.loads(p.stdout)
    except (json.JSONDecodeError, ValueError):
        data = None
    return p.returncode, data, p.stdout, p.stderr


def _proof_span_text(command, exit_code, proof_snapshot, verified_at, files=None):
    """A Proof: block's own isolated span text -- the SAME shape
    fixplan_closure_lint.py's `_extract_proof_span` hands to `parse_blocks`
    (a bare `Proof:` line + contiguous `- field: value` lines, no `## `
    header of its own -- `parse_blocks` treats a headerless span as one
    implicit block, per its own docstring: "Content before the first
    header: treat as an implicit block")."""
    lines = [
        "Proof:",
        "- command: %s" % command,
        "- exit_code: %s" % exit_code,
        "- proof_snapshot: %s" % proof_snapshot,
    ]
    if files:
        lines.append("- files: %s" % files)
    lines.append("- verified_at: %s" % verified_at)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# AC9 [BEHAVIORAL]: detect_mode() on a real Proof: block's own parsed fields
# (via parse_blocks on an isolated Proof: span, matching how
# fixplan_closure_lint.py already uses it) returns "E", not misclassified as
# A/B/C/D.
# ---------------------------------------------------------------------------

class AC9GenreEDetectedFromRealProofBlockFields(unittest.TestCase):
    def test_real_proof_block_fields_classified_as_mode_e(self):
        span = _proof_span_text(
            command="python3 run_and_record.py -- true",
            exit_code="0",
            proof_snapshot="/tmp/some/real/snapshot.json",
            verified_at="2026-07-09T00:00:00+00:00",
        )
        blocks = rac.parse_blocks(span)
        self.assertEqual(len(blocks), 1, blocks)
        fields = blocks[0]["_fields"]
        self.assertEqual(rac.detect_mode(fields), "E", fields)

    def test_real_proof_block_with_files_field_still_classified_as_mode_e(self):
        span = _proof_span_text(
            command="cat /tmp/evidence.txt", exit_code="0",
            proof_snapshot="/tmp/some/real/snapshot2.json",
            verified_at="2026-07-09T01:00:00+00:00",
            files="/tmp/evidence.txt",
        )
        blocks = rac.parse_blocks(span)
        fields = blocks[0]["_fields"]
        self.assertEqual(rac.detect_mode(fields), "E", fields)

    def test_mode_e_detection_does_not_regress_existing_mode_b_special_case(self):
        """detect_mode()'s special-case-B-first branch must remain FIRST and
        UNCHANGED (spec's own explicit instruction) -- a real Mode B block
        (diagnosis/if_not_found present, no Proof-block vocabulary at all)
        must still classify as "B", proving genre E's new early branch was
        added AFTER, not in place of, B's own special case. This test uses
        ONLY already-shipped genre-B code and is expected to ALREADY PASS
        today -- it exists here as a same-file regression tripwire that will
        catch the Coder's change if it ever regresses B's own precedence."""
        fields = {
            "diagnosis": "The root cause is a stale cache entry never invalidated on write.",
            "candidate_fixes": [],
            "falsifiable_check": "Clear the cache and confirm the stale value disappears.",
            "if_not_found": "If it persists, the bug is elsewhere.",
        }
        self.assertEqual(rac.detect_mode(fields), "B", fields)


# ---------------------------------------------------------------------------
# AC10 [BEHAVIORAL]: a fabricated Proof block whose `command` and
# `proof_snapshot` are both the literal string "test" is flagged by
# check_block() under genre E (rule 1, placeholder token) -- proving the
# reused scanner has real teeth against a Proof block, not just against
# Researcher output.
# ---------------------------------------------------------------------------

class AC10FabricatedProofBlockFlaggedUnderGenreE(unittest.TestCase):
    def _fabricated_block(self):
        span = _proof_span_text(
            command="test", exit_code="0", proof_snapshot="test",
            verified_at="2026-07-09T00:00:00+00:00",
        )
        blocks = rac.parse_blocks(span)
        return blocks[0]

    def test_check_block_flags_fabricated_command_and_proof_snapshot_in_process(self):
        block = self._fabricated_block()
        self.assertEqual(rac.detect_mode(block["_fields"]), "E", block)
        flags = rac.check_block(block)
        self.assertTrue(flags, "expected at least one flag on a fabricated genre-E block")
        reasons = " ".join(f.get("reason", "").lower() for f in flags)
        self.assertTrue(
            any(tok in reasons for tok in ("denylist", "placeholder", "literal")),
            f"expected a rule-1 (denylist/placeholder) reason among flags, got: {flags}",
        )
        flagged_fields = [f.get("field") for f in flags]
        self.assertIn("command", flagged_fields, flags)
        self.assertIn("proof_snapshot", flagged_fields, flags)

    def test_fabricated_proof_block_flagged_through_the_real_cli(self):
        """Same fixture, driven through the real public entrypoint (the
        CLI, matching test_research_authenticity_check.py's own primary
        convention) -- not just the in-process unit-level check above.

        DISCRIMINATION NOTE (confirmed empirically while writing this test,
        against the REAL, current, genre-E-less script): rule 1 alone
        (a bare "test" token) already fires on ANY field regardless of mode
        classification -- it does NOT by itself prove genre E was correctly
        added, since a block that falls through to the generic A-D scoring
        loop and gets misclassified (e.g. as "A", with zero real vocabulary
        overlap) would STILL trip rule 1 on "command"/"proof_snapshot"
        today, even with no genre-E code at all. What DOES discriminate:
        `MODE_RULE2_FIELDS["E"] = ["command", "proof_snapshot"]` pairs
        these two specific fields for the identical-value-across-fields
        check -- under the CURRENT (pre-genre-E) fallback classification,
        neither field is in ANY existing mode's own rule-2 list, so NO
        "identical value" flag fires for them today (confirmed directly:
        the real, current script produces exactly 2 rule-1 flags and ZERO
        rule-2 flags for this exact fixture). This assertion additionally
        requires that rule-2 flag, so this test only passes once genre E's
        own MODE_RULE2_FIELDS entry is real."""
        tmp = tempfile.mkdtemp()
        text = "## Fabricated closure Proof block\n" + _proof_span_text(
            command="test", exit_code="0", proof_snapshot="test",
            verified_at="2026-07-09T00:00:00+00:00",
        )
        path = _write(tmp, "fabricated_genre_e.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        reasons_by_flag = [r.get("reason", "").lower() for r in data["flagged"]]
        combined_reasons = " ".join(reasons_by_flag)
        self.assertTrue(
            any(tok in combined_reasons for tok in ("denylist", "placeholder", "literal")),
            f"expected a rule-1 reason, got: {data['flagged']}",
        )
        # Genre-E-specific discriminator: rule 2 pairs command+proof_snapshot
        # under genre E (MODE_RULE2_FIELDS["E"]) -- this must ALSO fire, or
        # this test would pass vacuously off rule 1 alone even without
        # genre E ever being implemented (see docstring note above).
        identical_flags = [
            f for f in data["flagged"]
            if "identical" in f.get("reason", "").lower()
        ]
        self.assertTrue(
            identical_flags,
            "expected an ADDITIONAL rule-2 'identical value across distinct "
            "fields' flag pairing command+proof_snapshot (genre E's own "
            "MODE_RULE2_FIELDS entry) -- got only: %r" % data["flagged"],
        )
        self.assertTrue(
            any(
                "command" in f.get("field", "") and "proof_snapshot" in f.get("field", "")
                for f in identical_flags
            ),
            "expected the rule-2 'identical' flag to name both command and "
            "proof_snapshot together, got: %r" % identical_flags,
        )


# ---------------------------------------------------------------------------
# AC11 [BEHAVIORAL]: genres A-D's own existing test suite (in the SEPARATE
# test_research_authenticity_check.py file) remains fully green, unchanged,
# after adding genre E. The authoritative check is running that file's own
# suite directly (this class's own docstring note; matches that file's
# established "run the whole file" precedent for an identical situation,
# e.g. its AC8FullSuiteRegressionAfterOptionalFieldsChange class) --
# test_evidence_gate_phase5_full_suite_regression.py's own AC12 cross-check
# separately, mechanically enforces this by naming that file directly. This
# class is a SAME-FILE-as-genre-E, lighter-weight regression guard tying a
# few representative Mode A/B/C/D fixtures directly to genre E's addition,
# so a regression in genuinely SHARED code (detect_mode's scoring loop,
# check_block's rule dispatch) surfaces even if only this file is run in
# isolation, in addition to the dedicated cross-suite check.
# ---------------------------------------------------------------------------

class AC11ExistingGenreABCDBehaviorUnaffectedByGenreEAddition(unittest.TestCase):
    MODE_A_TEMPLATE = (
        "## Candidate: Some Tool\n"
        "- name: Some Tool\n"
        "- source: https://example.com/real-doc\n"
        "- maturity: Real, verified.\n"
        "- claim: {claim}\n"
        "- where_it_wires_in: {where_it_wires_in}\n"
        "- triage: TESTABLE\n"
        "- priority: 0.5\n"
        "- risks: {risks}\n"
        "- experiment: {experiment}\n"
    )

    def test_mode_a_hard_good_still_passes_clean_after_genre_e_addition(self):
        tmp = tempfile.mkdtemp()
        text = self.MODE_A_TEMPLATE.format(
            claim="Runs N specialized review agents in parallel and clusters findings "
                  "that share the same file, category, and overlapping line ranges.",
            where_it_wires_in="A generic dedup/consensus pattern loop-team could adapt "
                               "for reconciling parallel plan-check Verifier gap records.",
            risks="Low external adoption signal even though the implementation itself "
                  "is concretely real and non-trivial; no cross-round contradiction "
                  "detection.",
            # NOTE: bare "n/a" is unconditionally rule-1-denylisted for EVERY
            # field regardless of mode (MODE_OPTIONAL_FIELDS only exempts
            # Mode D's code_pattern/constraints) -- a substantive sentence is
            # required here for a genuinely clean "hard good" fixture.
            experiment="n/a -- research-only prior-art survey, not itself an adopted change.",
        )
        path = _write(tmp, "ac11_mode_a_hard_good.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["flagged"], [], data["flagged"])

    def test_mode_a_incident_reconstruction_still_flagged_after_genre_e_addition(self):
        tmp = tempfile.mkdtemp()
        text = self.MODE_A_TEMPLATE.format(
            claim="test", where_it_wires_in="test", risks="test", experiment="n/a"
        )
        path = _write(tmp, "ac11_incident.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)

    def test_mode_b_diagnosis_block_still_classified_as_mode_b_after_genre_e_addition(self):
        fields = {
            "diagnosis": "The root cause is a stale cache entry never invalidated on write.",
            "candidate_fixes": [],
            "falsifiable_check": "Clear the cache and confirm the stale value disappears.",
            "if_not_found": "If it persists, the bug is elsewhere.",
        }
        self.assertEqual(rac.detect_mode(fields), "B", fields)

    def test_mode_c_and_mode_d_field_vocabularies_unaffected_after_genre_e_addition(self):
        mode_c_fields = {
            "id": "C1", "target": "some target", "expected": "some expected value",
            "artifact": "some artifact",
            "failure_mode": "some real, substantive failure mode text here",
            "why_hard": "genuinely hard to test because of nondeterministic timing",
            "objective_fact": "confirmed via direct repro on 2026-07-09",
        }
        self.assertEqual(rac.detect_mode(mode_c_fields), "C", mode_c_fields)
        mode_d_fields = {
            "question": "does X really do Y", "answer": "yes, confirmed by direct repro",
            "source": "https://example.com/real-doc", "code_pattern": "n/a",
            "constraints": "n/a", "not_found": "",
        }
        self.assertEqual(rac.detect_mode(mode_d_fields), "D", mode_d_fields)


if __name__ == "__main__":
    unittest.main()
