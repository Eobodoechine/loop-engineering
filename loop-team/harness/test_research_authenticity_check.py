"""Tests for research_authenticity_check.py (closes H-DEGENERATE-OUTPUT-1).

Behavioral, CLI-first tests, matching this repo's convention for a
deterministic, Oga-run harness script (see test_live_smoke.py / test_verify_harness.py):
invoke the real script as a subprocess against fixture markdown files and assert on its
JSON verdict — the actual public interface Oga uses (`python3
research_authenticity_check.py <saved_file_path>`), not internal function names.

Written BEFORE the implementation exists (harness/research_authenticity_check.py is not
yet built) — these tests are expected to fail with ModuleNotFoundError/ImportError-shaped
subprocess failures (a non-zero exit + a traceback naming the missing file) until the
Coder delivers. That is correct per the test-writer role brief.

Fixture field vocabularies are the REAL ones from roles/researcher.md's "You produce"
sections (Mode A ~line 85-97, Mode B ~194-205, Mode C ~245-270, Mode D ~305-315) — not
invented field names:
  Mode A: name, source, maturity, claim, where_it_wires_in, triage, priority, risks, experiment
  Mode B: diagnosis, candidate_fixes (list, each with its own source), falsifiable_check,
          if_not_found
  Mode C: id, target, expected, artifact, failure_mode, why_hard, objective_fact
  Mode D: question, answer, source, code_pattern, constraints, not_found

Run: python3 -m pytest loop-team/harness/test_research_authenticity_check.py -q
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "research_authenticity_check.py")

# The real excerpt used for the AC2 "hard good" — pulled directly from this session's own
# committed research doc, research/plan-check-reconciliation-prior-art-2026-07-02.md
# (Candidate 3.2, ai-code-reviewer). Copied verbatim (not paraphrased) so the "hard good"
# fixture is genuinely real content, not a test-author's invented stand-in.
REAL_MODE_A_EXCERPT = {
    "name": "ai-code-reviewer (calimero-network)",
    "source": "https://github.com/calimero-network/ai-code-reviewer",
    "maturity": "Real, small but genuinely implemented (not a stub) -- pip-installable "
                "(pip install ai-code-reviewer), MIT license, Docker + GitHub Actions "
                "integration, 7 stars.",
    "claim": "Runs N specialized review agents in parallel (Security, Performance/Logic, "
             "Patterns/Style) and clusters findings that share the same file, category, "
             "overlapping line ranges (+/-5 lines), and combined title+description "
             "similarity >= 0.85, each cluster becoming one ConsolidatedFinding with "
             "consensus_score = unique_agents_in_cluster / total_agents.",
    "where_it_wires_in": "A generic dedup/consensus pattern loop-team could adapt for "
                         "the compatible-merge half of reconciling N parallel plan-check "
                         "Verifier gap records into one action list.",
    "triage": "IMPLEMENTABLE_NOW",
    "risks": "Low external adoption signal (7 stars) even though the implementation "
             "itself is concretely real and non-trivial; has no cross-agent OR "
             "cross-round contradiction detection, confirmed by reading the full "
             "architecture doc -- only solves dedup + consensus, not conflict detection.",
    "experiment": "n/a -- research-only prior-art survey, not itself an adopted change.",
}


def _write(tmpdir, name, text):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _run(path):
    """Invoke the real CLI: python3 research_authenticity_check.py <saved_file_path>.

    Returns (exit_code, parsed_json_or_None, raw_stdout, raw_stderr).
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


def _mode_a_block(claim, where_it_wires_in, risks, source="https://example.com/real-doc",
                   name="Some Tool", maturity="Real, verified.", triage="TESTABLE",
                   priority="0.5", experiment="n/a"):
    return (
        "## Candidate: {name}\n"
        "- name: {name}\n"
        "- source: {source}\n"
        "- maturity: {maturity}\n"
        "- claim: {claim}\n"
        "- where_it_wires_in: {where_it_wires_in}\n"
        "- triage: {triage}\n"
        "- priority: {priority}\n"
        "- risks: {risks}\n"
        "- experiment: {experiment}\n"
    ).format(name=name, source=source, maturity=maturity, claim=claim,
             where_it_wires_in=where_it_wires_in, triage=triage, priority=priority,
             risks=risks, experiment=experiment)


# ---------------------------------------------------------------------------
# AC1 -- reconstructed H-DEGENERATE-OUTPUT-1 incident + isolated rule 1 / rule 2
# ---------------------------------------------------------------------------

class AC1RealIncidentReconstruction(unittest.TestCase):
    """A Mode A block with claim/where_it_wires_in/risks all literally "test" must be
    flagged by BOTH rule 1 (literal denylist token) and rule 2 (identical-across-fields)
    independently -- this is the exact shape of the real H-DEGENERATE-OUTPUT-1 incident
    (fix_plan.md: claim="test", source="test", verdict="test" for every field)."""

    def test_all_three_fields_literally_test_is_flagged(self):
        tmp = tempfile.mkdtemp()
        text = _mode_a_block(claim="test", where_it_wires_in="test", risks="test")
        path = _write(tmp, "incident.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(
            data, f"expected JSON on stdout, got stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        self.assertNotEqual(code, 0)
        self.assertTrue(data["flagged"], "must flag at least one block")

    def test_incident_reconstruction_flagged_by_rule_1_denylist(self):
        """Rule 1: at least one flagged entry's reason must reference the literal
        placeholder-token match (not just rule 2)."""
        tmp = tempfile.mkdtemp()
        text = _mode_a_block(claim="test", where_it_wires_in="test", risks="test")
        path = _write(tmp, "incident.md", text)
        _, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        reasons = " ".join(r.get("reason", "").lower() for r in data["flagged"])
        self.assertTrue(
            any(tok in reasons for tok in ("denylist", "placeholder", "literal")),
            f"expected a rule-1 (denylist/placeholder) reason among flags, got: {data['flagged']}",
        )

    def test_incident_reconstruction_flagged_by_rule_2_identical_across_fields(self):
        """Rule 2: at least one flagged entry's reason must reference identical values
        across the mode's distinct fields (not just rule 1)."""
        tmp = tempfile.mkdtemp()
        text = _mode_a_block(claim="test", where_it_wires_in="test", risks="test")
        path = _write(tmp, "incident.md", text)
        _, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        reasons = " ".join(r.get("reason", "").lower() for r in data["flagged"])
        self.assertTrue(
            any(tok in reasons for tok in ("identical", "same value", "duplicate")),
            f"expected a rule-2 (identical-across-fields) reason among flags, got: {data['flagged']}",
        )

    def test_rule_1_fires_in_isolation_when_only_one_field_is_a_bare_denylist_token(self):
        """Fixture crafted to trigger ONLY rule 1: one field is exactly "placeholder"
        (a denylist token) while the other two rule-2-compared fields are non-identical,
        substantive, real-looking prose -- so rule 2 (identical-across-fields) and rule 3
        (too-short) must NOT be what catches this; only rule 1 should."""
        tmp = tempfile.mkdtemp()
        text = _mode_a_block(
            claim="placeholder",
            where_it_wires_in="This wires into the Coder's retry-budget check in "
                               "orchestrator.md step 4, replacing the fixed N=3 cap "
                               "with a stall-signature-aware one.",
            risks="Adds a new config knob that could be silently misconfigured if the "
                  "default is changed without updating the docs; moderate maintenance cost.",
        )
        path = _write(tmp, "rule1_only.md", text)
        _, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        flagged_fields = [f.get("field") for f in data["flagged"]]
        self.assertIn("claim", flagged_fields, data["flagged"])
        reasons = " ".join(r.get("reason", "").lower() for r in data["flagged"])
        self.assertTrue(
            any(tok in reasons for tok in ("denylist", "placeholder", "literal")),
            data["flagged"],
        )

    def test_rule_2_fires_in_isolation_when_fields_share_a_non_denylisted_phrase(self):
        """Fixture crafted to trigger ONLY rule 2: all three Mode A rule-2 fields
        (claim/where_it_wires_in/risks) are identically "some non-denylisted phrase" --
        long enough to dodge rule 3 (short-field) and not a literal denylist token
        (dodges rule 1) -- so only the identical-across-fields rule should catch it."""
        tmp = tempfile.mkdtemp()
        shared = "some non-denylisted phrase that is long enough to not be short"
        text = _mode_a_block(claim=shared, where_it_wires_in=shared, risks=shared)
        path = _write(tmp, "rule2_only.md", text)
        _, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        reasons = " ".join(r.get("reason", "").lower() for r in data["flagged"])
        self.assertTrue(
            any(tok in reasons for tok in ("identical", "same value", "duplicate")),
            f"expected identical-across-fields reason, got: {data['flagged']}",
        )
        # Must NOT be explained away as a rule-1 denylist hit -- the phrase is not a
        # denylist token, so if a "placeholder"/"denylist" reason shows up standing in
        # for rule 2, the rules are conflated rather than independently implemented.
        self.assertNotIn("denylist token", reasons)


# ---------------------------------------------------------------------------
# AC2 -- "hard good": genuine, real research excerpt must NOT be flagged
# ---------------------------------------------------------------------------

class AC2HardGoodRealResearchExcerpt(unittest.TestCase):
    """A verifier that flags everything is as broken as one that flags nothing --
    confirm a REAL, substantive, well-formed Mode A excerpt from this session's own
    committed research doc (research/plan-check-reconciliation-prior-art-2026-07-02.md,
    Candidate 3.2 ai-code-reviewer) passes clean."""

    def test_real_committed_research_excerpt_is_not_flagged(self):
        tmp = tempfile.mkdtemp()
        text = _mode_a_block(**REAL_MODE_A_EXCERPT)
        path = _write(tmp, "hard_good.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["flagged"], [], data["flagged"])
        self.assertEqual(code, 0)


# ---------------------------------------------------------------------------
# AC3 -- rule 3 (short-field) in isolation
# ---------------------------------------------------------------------------

class AC3ShortFieldRuleInIsolation(unittest.TestCase):
    """A real-looking but too-short claim ("Yes.") must be flagged for length alone --
    not a denylist token (rule 1), not identical across fields (rule 2), and with a
    present, well-formed http(s) source (rule 4 does not apply)."""

    def test_too_short_claim_is_flagged_for_length(self):
        tmp = tempfile.mkdtemp()
        text = _mode_a_block(
            claim="Yes.",
            where_it_wires_in="Wires into the Researcher Mode A radar scan step in "
                               "orchestrator.md, as a new weekly deep-pass check.",
            risks="License is MIT so no legal risk; moderate maintenance burden since "
                  "the maintainer has had gaps of 6+ months between releases before.",
            source="https://example.com/real-and-verified-doc",
        )
        path = _write(tmp, "short_field.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        flagged_fields = [f.get("field") for f in data["flagged"]]
        self.assertIn("claim", flagged_fields, data["flagged"])
        reasons = " ".join(
            r.get("reason", "").lower() for r in data["flagged"] if r.get("field") == "claim"
        )
        self.assertTrue(
            any(tok in reasons for tok in ("short", "length", "minimum")),
            f"expected a length-based reason for the too-short claim, got: {data['flagged']}",
        )
        # Must not be mis-explained as rule 1 or rule 2 -- "Yes." is not a denylist
        # token and the other two rule-2 fields are neither identical to it nor to
        # each other.
        self.assertNotIn("denylist", reasons)
        self.assertNotIn("identical", reasons)


# ---------------------------------------------------------------------------
# AC4 -- rule 4 (missing source URL) in isolation
# ---------------------------------------------------------------------------

class AC4MissingSourceUrlRuleInIsolation(unittest.TestCase):
    """A source field present but containing no http/https substring must be flagged --
    independent of rules 1/2/3 (all other fields real, substantive, and distinct)."""

    def test_source_without_url_is_flagged(self):
        tmp = tempfile.mkdtemp()
        text = _mode_a_block(
            claim="This tool clusters near-duplicate findings using a 0.85 "
                  "SequenceMatcher similarity threshold before merging them.",
            where_it_wires_in="Plugs into the reconcile_gap_records.py harness step "
                              "that runs after parallel plan-check Verifiers return.",
            risks="Low external adoption (single-digit stars) but the implementation "
                  "itself is concretely real, not a stub.",
            source="see the calimero-network GitHub repo (no link handy)",
        )
        path = _write(tmp, "missing_source_url.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        flagged_fields = [f.get("field") for f in data["flagged"]]
        self.assertIn("source", flagged_fields, data["flagged"])
        reasons = " ".join(
            r.get("reason", "").lower() for r in data["flagged"] if r.get("field") == "source"
        )
        self.assertTrue(
            any(tok in reasons for tok in ("url", "http", "source")),
            f"expected a missing-URL reason on the source field, got: {data['flagged']}",
        )


# ---------------------------------------------------------------------------
# AC5 -- per-mode coverage (rule 2's explicit field-pair list per mode, + rule 4's
# mode-specific application/skip)
# ---------------------------------------------------------------------------

class AC5ModeACoverage(unittest.TestCase):
    """Mode A: claim / where_it_wires_in / risks (rule 2's exact field list)."""

    def test_mode_a_identical_claim_where_it_wires_in_risks_flagged(self):
        tmp = tempfile.mkdtemp()
        shared = "identical degenerate content across all three mode a fields here"
        text = _mode_a_block(claim=shared, where_it_wires_in=shared, risks=shared)
        path = _write(tmp, "mode_a.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)


class AC5ModeBCoverage(unittest.TestCase):
    """Mode B: diagnosis / if_not_found (rule 2's exact field list, candidate_fixes
    handled separately); rule 4 applies PER candidate_fixes[].source item, not a
    nonexistent top-level `source` field."""

    def _mode_b_block(self, diagnosis, if_not_found, candidate_fixes):
        fixes_text = ""
        for i, cf in enumerate(candidate_fixes):
            fixes_text += (
                f"  - fix {i}: {cf['fix']}\n"
                f"    source: {cf['source']}\n"
            )
        return (
            "## Bug-fix dossier\n"
            f"- diagnosis: {diagnosis}\n"
            "- candidate_fixes:\n"
            f"{fixes_text}"
            "- falsifiable_check: apply fix 0, re-run failing test T, confirm it passes.\n"
            f"- if_not_found: {if_not_found}\n"
        )

    def test_mode_b_identical_diagnosis_and_if_not_found_flagged(self):
        tmp = tempfile.mkdtemp()
        shared = "identical degenerate content across both mode b free text fields"
        text = self._mode_b_block(
            diagnosis=shared,
            if_not_found=shared,
            candidate_fixes=[
                {"fix": "Increase the connection pool size from 5 to 20 in db.py.",
                 "source": "https://example.com/db-pool-docs"},
            ],
        )
        path = _write(tmp, "mode_b_identical.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)

    def test_mode_b_candidate_fixes_item_missing_source_url_flagged_by_item(self):
        """A candidate_fixes list where ONE item's source lacks a URL must be flagged,
        referencing that specific item -- not a nonexistent top-level `source` field."""
        tmp = tempfile.mkdtemp()
        text = self._mode_b_block(
            diagnosis="The connection pool exhausts under concurrent load because the "
                      "default pool_size=5 is far below the observed 40 concurrent "
                      "requests during the stress test.",
            if_not_found="",
            candidate_fixes=[
                {"fix": "Increase pool_size to 20 in db.py's create_engine call.",
                 "source": "https://example.com/sqlalchemy-pool-docs"},
                {"fix": "Switch to a connection-per-request model instead of pooling.",
                 "source": "found this in an old chat, no link"},
            ],
        )
        path = _write(tmp, "mode_b_missing_source.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        # Must reference the specific flagged candidate_fixes item, not a top-level
        # `source` field (Mode B has no top-level source per roles/researcher.md).
        relevant = [f for f in data["flagged"]
                    if "source" in (f.get("field") or "").lower()]
        self.assertTrue(relevant, data["flagged"])
        self.assertTrue(
            any("1" in str(f.get("field", "")) or "candidate_fixes" in str(f.get("field", ""))
                or "connection-per-request" in str(f.get("value_excerpt", ""))
                for f in relevant),
            f"expected the flag to identify WHICH candidate_fixes item lacks a URL, "
            f"got: {data['flagged']}",
        )
        # The good item (index 0, real URL) must not itself be flagged for missing URL.
        good_item_flagged = any(
            "sqlalchemy-pool-docs" in str(f.get("value_excerpt", "")) for f in relevant
        )
        self.assertFalse(good_item_flagged, data["flagged"])


class AC5ModeCCoverage(unittest.TestCase):
    """Mode C: why_hard / objective_fact / failure_mode (rule 2's exact field list);
    rule 4 must be SKIPPED entirely (Mode C has no top-level `source` field at all per
    roles/researcher.md -- a Mode C record with no `source` field must NOT be flagged
    for a missing source)."""

    def _mode_c_block(self, why_hard, objective_fact, failure_mode):
        return (
            "## Adversarial case\n"
            "- id: case-017\n"
            "- target: verifier\n"
            "- expected: FALSE-PASS\n"
            "- artifact: A synthesis paragraph citing a benchmark number with no "
              "traceable source, phrased in an authoritative tone.\n"
            f"- failure_mode: {failure_mode}\n"
            f"- why_hard: {why_hard}\n"
            f"- objective_fact: {objective_fact}\n"
        )

    def test_mode_c_identical_why_hard_objective_fact_failure_mode_flagged(self):
        tmp = tempfile.mkdtemp()
        shared = "identical degenerate content across all three mode c fields here"
        text = self._mode_c_block(why_hard=shared, objective_fact=shared, failure_mode=shared)
        path = _write(tmp, "mode_c_identical.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)

    def test_mode_c_missing_source_field_is_not_flagged_rule_4_skipped(self):
        """A genuine Mode C record (no source field at all, since Mode C never has one)
        with real, distinct, substantive why_hard/objective_fact/failure_mode content
        must pass clean -- rule 4 must not fabricate a requirement Mode C never has."""
        tmp = tempfile.mkdtemp()
        text = self._mode_c_block(
            why_hard="The current Verifier tends to trust an authoritative tone as a "
                     "proxy for correctness, per the known judge-bias literature on "
                     "sycophancy toward confident phrasing.",
            objective_fact="The cited benchmark number does not appear anywhere in the "
                           "linked paper's actual results table, which is independently "
                           "checkable by opening the PDF.",
            failure_mode="unsourced-authoritative-claim",
        )
        path = _write(tmp, "mode_c_no_source.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["flagged"], [], data["flagged"])
        source_flags = [f for f in data["flagged"]
                         if "source" in (f.get("field") or "").lower()]
        self.assertEqual(source_flags, [], source_flags)


class AC5ModeDCoverage(unittest.TestCase):
    """Mode D: question / answer / not_found (rule 2's exact field list, comparing only
    question/answer when not_found is empty/absent); Mode D has a top-level `source`
    field so rule 4 DOES apply there (same as Mode A)."""

    def _mode_d_block(self, question, answer, source, not_found=""):
        return (
            "## Domain brief\n"
            f"- question: {question}\n"
            f"- answer: {answer}\n"
            f"- source: {source}\n"
            "- code_pattern: n/a\n"
            "- constraints: n/a\n"
            f"- not_found: {not_found}\n"
        )

    def test_mode_d_identical_question_and_answer_flagged(self):
        tmp = tempfile.mkdtemp()
        shared = "identical degenerate content shared between question and answer here"
        text = self._mode_d_block(
            question=shared, answer=shared, source="https://example.com/real-api-docs",
        )
        path = _write(tmp, "mode_d_identical.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)

    def test_mode_d_missing_source_url_flagged(self):
        tmp = tempfile.mkdtemp()
        text = self._mode_d_block(
            question="What auth flow does the Stripe Connect API use for onboarding "
                     "a new platform account?",
            answer="OAuth 2.0 with a platform-specific `client_id`, redirecting to "
                   "Stripe's hosted onboarding flow and returning an authorization code.",
            source="the official Stripe docs (didn't grab the exact link)",
        )
        path = _write(tmp, "mode_d_missing_url.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        flagged_fields = [f.get("field") for f in data["flagged"]]
        self.assertIn("source", flagged_fields, data["flagged"])


# ---------------------------------------------------------------------------
# AC1-8 -- MODE_OPTIONAL_FIELDS / ABSENCE_TOKENS (H-DEGENERATE-OUTPUT-1
# follow-up): rule 1's denylist scoped so a genuine "n/a"/"na" in Mode D's
# code_pattern/constraints is not flagged, while every other denylist token
# and every other field's full-denylist behavior is unchanged.
#
# These tests exercise the mechanism described in the spec's "Public
# interface" section (MODE_OPTIONAL_FIELDS, ABSENCE_TOKENS, and the modified
# rule-1 loop in check_block()) -- none of which exists yet in
# research_authenticity_check.py as of this writing, so all 8 are expected
# to fail (not error) against the current implementation.
# ---------------------------------------------------------------------------

def _mode_d_block_full(question, answer, source, code_pattern, constraints,
                        not_found=""):
    """Like AC5ModeDCoverage's _mode_d_block, but with code_pattern/constraints
    as explicit parameters (that helper hardcodes both to "n/a") so these tests
    can control the exempted fields directly."""
    return (
        "## Domain brief\n"
        f"- question: {question}\n"
        f"- answer: {answer}\n"
        f"- source: {source}\n"
        f"- code_pattern: {code_pattern}\n"
        f"- constraints: {constraints}\n"
        f"- not_found: {not_found}\n"
    )


_REAL_QUESTION = (
    "What retry backoff strategy does the Stripe Python SDK use by default "
    "for idempotent requests?"
)
_REAL_ANSWER = (
    "Exponential backoff with jitter, starting at 0.5s and capped at 2s, "
    "up to 2 retries by default, controlled by the Stripe.max_network_retries "
    "class attribute."
)
_REAL_SOURCE = "https://github.com/stripe/stripe-python/blob/master/stripe/_http_client.py"


class AC1ModeDCodePatternNAIsNotFlagged(unittest.TestCase):
    """AC1: a Mode D block with code_pattern: n/a and otherwise fully
    substantive, non-denylisted fields must pass clean -- the core
    false-positive this spec fixes."""

    def test_code_pattern_n_a_with_substantive_other_fields_passes_clean(self):
        tmp = tempfile.mkdtemp()
        text = _mode_d_block_full(
            question=_REAL_QUESTION, answer=_REAL_ANSWER, source=_REAL_SOURCE,
            code_pattern="n/a", constraints="No hard constraints beyond respecting "
                                             "the SDK's built-in rate limiter.",
        )
        path = _write(tmp, "ac1_code_pattern_na.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["flagged"], [], data["flagged"])
        self.assertEqual(code, 0)


class AC2ModeDConstraintsNAIsNotFlagged(unittest.TestCase):
    """AC2: same as AC1 but for constraints: n/a instead of code_pattern --
    both optional fields are covered independently."""

    def test_constraints_n_a_with_substantive_other_fields_passes_clean(self):
        tmp = tempfile.mkdtemp()
        text = _mode_d_block_full(
            question=_REAL_QUESTION, answer=_REAL_ANSWER, source=_REAL_SOURCE,
            code_pattern="Uses a decorator-based retry wrapper around the "
                         "underlying urllib3 PoolManager call.",
            constraints="n/a",
        )
        path = _write(tmp, "ac2_constraints_na.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["flagged"], [], data["flagged"])
        self.assertEqual(code, 0)


class AC3ModeDBothOptionalFieldsNAIsNotFlagged(unittest.TestCase):
    """AC3: same as AC1 but with BOTH code_pattern: n/a AND constraints: n/a
    in the same block -- still passed: true, zero flags (the exemption is
    not order- or count-dependent)."""

    def test_both_code_pattern_and_constraints_n_a_passes_clean(self):
        tmp = tempfile.mkdtemp()
        text = _mode_d_block_full(
            question=_REAL_QUESTION, answer=_REAL_ANSWER, source=_REAL_SOURCE,
            code_pattern="n/a", constraints="n/a",
        )
        path = _write(tmp, "ac3_both_na.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["flagged"], [], data["flagged"])
        self.assertEqual(code, 0)


class AC4ModeDCodePatternLazyTokenStillFlagged(unittest.TestCase):
    """AC4: a Mode D block with code_pattern: test (a genuinely lazy/
    placeholder token, NOT n/a) is STILL flagged by rule 1 -- proves the fix
    narrows the exemption to ABSENCE_TOKENS specifically, not the whole
    denylist for optional fields."""

    def test_code_pattern_literally_test_is_still_flagged(self):
        tmp = tempfile.mkdtemp()
        text = _mode_d_block_full(
            question=_REAL_QUESTION, answer=_REAL_ANSWER, source=_REAL_SOURCE,
            code_pattern="test", constraints="No hard constraints beyond respecting "
                                              "the SDK's built-in rate limiter.",
        )
        path = _write(tmp, "ac4_code_pattern_test.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        flagged_fields = [f.get("field") for f in data["flagged"]]
        self.assertIn("code_pattern", flagged_fields, data["flagged"])
        reasons = " ".join(
            r.get("reason", "").lower() for r in data["flagged"]
            if r.get("field") == "code_pattern"
        )
        self.assertTrue(
            any(tok in reasons for tok in ("denylist", "placeholder", "literal")),
            f"expected a rule-1 denylist reason on code_pattern, got: {data['flagged']}",
        )


class AC5ModeDRequiredFieldQuestionNAStillFlagged(unittest.TestCase):
    """AC5: a Mode D block with question: n/a (a REQUIRED field, not in
    MODE_OPTIONAL_FIELDS["D"]) is STILL flagged by rule 1 -- proves the
    exemption doesn't leak to non-optional fields."""

    def test_question_n_a_is_still_flagged(self):
        tmp = tempfile.mkdtemp()
        text = _mode_d_block_full(
            question="n/a", answer=_REAL_ANSWER, source=_REAL_SOURCE,
            code_pattern="n/a", constraints="n/a",
        )
        path = _write(tmp, "ac5_question_na.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        flagged_fields = [f.get("field") for f in data["flagged"]]
        self.assertIn("question", flagged_fields, data["flagged"])
        reasons = " ".join(
            r.get("reason", "").lower() for r in data["flagged"]
            if r.get("field") == "question"
        )
        self.assertTrue(
            any(tok in reasons for tok in ("denylist", "placeholder", "literal")),
            f"expected a rule-1 denylist reason on question, got: {data['flagged']}",
        )


class AC6ModeDSourceTestStillFlaggedRegressionGuard(unittest.TestCase):
    """AC6: a Mode D block with source: test is STILL flagged by rule 1 --
    regression guard for the exact real incident H-DEGENERATE-OUTPUT-1
    describes (source must never be exemptable), confirming the spec's
    correction to the original follow-up note's proposed mechanism actually
    holds in the implementation, not just in prose."""

    def test_source_literally_test_is_still_flagged(self):
        tmp = tempfile.mkdtemp()
        text = _mode_d_block_full(
            question=_REAL_QUESTION, answer=_REAL_ANSWER, source="test",
            code_pattern="n/a", constraints="n/a",
        )
        path = _write(tmp, "ac6_source_test.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        flagged_fields = [f.get("field") for f in data["flagged"]]
        self.assertIn("source", flagged_fields, data["flagged"])
        reasons = " ".join(
            r.get("reason", "").lower() for r in data["flagged"]
            if r.get("field") == "source"
        )
        self.assertTrue(
            any(tok in reasons for tok in ("denylist", "placeholder", "literal")),
            f"expected a rule-1 denylist reason on source, got: {data['flagged']}",
        )


class AC7ModeARisksNAStillFlaggedModeScoped(unittest.TestCase):
    """AC7: a Mode A block with risks: n/a (Mode A has no entry in
    MODE_OPTIONAL_FIELDS, so nothing is exempted for it) is STILL flagged by
    rule 1 -- proves the exemption is mode-scoped and doesn't silently apply
    everywhere."""

    def test_mode_a_risks_n_a_is_still_flagged(self):
        tmp = tempfile.mkdtemp()
        text = _mode_a_block(
            claim="Runs N specialized review agents in parallel and clusters "
                  "findings sharing file, category, and line-range overlap.",
            where_it_wires_in="A generic dedup/consensus pattern loop-team "
                              "could adapt for reconciling parallel Verifier "
                              "gap records into one action list.",
            risks="n/a",
        )
        path = _write(tmp, "ac7_mode_a_risks_na.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertFalse(data["passed"], data)
        flagged_fields = [f.get("field") for f in data["flagged"]]
        self.assertIn("risks", flagged_fields, data["flagged"])
        reasons = " ".join(
            r.get("reason", "").lower() for r in data["flagged"]
            if r.get("field") == "risks"
        )
        self.assertTrue(
            any(tok in reasons for tok in ("denylist", "placeholder", "literal")),
            f"expected a rule-1 denylist reason on risks, got: {data['flagged']}",
        )


class AC8FullSuiteRegressionAfterOptionalFieldsChange(unittest.TestCase):
    """AC8: existing behavior for a fully substantive, non-n/a Mode D block
    (already covered by the existing 16 tests) is unaffected -- run the
    original hard-good-style Mode D fixture directly here as an explicit
    regression guard tied to this spec's change (the broader "full suite
    still passes" requirement is additionally verified by running the whole
    file, not just this one test)."""

    def test_fully_substantive_non_na_mode_d_block_still_passes_clean(self):
        tmp = tempfile.mkdtemp()
        text = _mode_d_block_full(
            question=_REAL_QUESTION, answer=_REAL_ANSWER, source=_REAL_SOURCE,
            code_pattern="Uses a decorator-based retry wrapper around the "
                         "underlying urllib3 PoolManager call.",
            constraints="Must remain compatible with both sync and async "
                        "Stripe client instances.",
        )
        path = _write(tmp, "ac8_fully_substantive.md", text)
        code, data, out, err = _run(path)
        self.assertIsNotNone(data, f"stdout={out!r} stderr={err!r}")
        self.assertTrue(data["passed"], data)
        self.assertEqual(data["flagged"], [], data["flagged"])
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
