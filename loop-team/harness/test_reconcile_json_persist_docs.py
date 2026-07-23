"""[DOC] Doc-content tests for the reconcile-JSON-persistence spec's prose
edits (spec sections D.2/D.3/D.4):

- orchestrator.md's reconciliation-invocation sentence mandates --out
  (AC4) and its persistence instruction gains a structured-JSON sibling
  requirement (AC5).
- roles/verifier.md gains a LOOP-M10 gate matching the spec's
  "completeness, not correctness of grouping" framing -- NOT the
  earlier-rejected "lenses key, 2+ distinct values" framing the spec's D.3
  explicitly disclaims as a NON-CHECK (AC6).
- fix_plan.md gains the H-RECONCILE-JSON-PERSIST-1 entry (AC7).

These are simple grep/read-based assertions against live prose files, per
the Test-writer role's [DOC] classification -- no separate test runner
needed.

Spec: loop-team/runs/2026-07-09_reconcile-json-persistence/specs/spec.md
Written BEFORE the Coder's implementation exists (Test-writer role, Tier 1)
-- every test in this file is expected to FAIL until the Coder applies
these prose edits to the live files.

Run with:
    python3 -m pytest loop-team/harness/test_reconcile_json_persist_docs.py -v
"""
import os
import re
import unittest

THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # .../loop-team/harness
LOOP_TEAM_DIR = os.path.dirname(THIS_DIR)                        # .../loop-team
LOOP_DIR = os.path.dirname(LOOP_TEAM_DIR)                        # .../loop

ORCHESTRATOR_PATH = os.path.join(LOOP_TEAM_DIR, "orchestrator.md")
VERIFIER_PATH = os.path.join(LOOP_TEAM_DIR, "roles", "verifier.md")
FIX_PLAN_PATH = os.path.join(LOOP_DIR, "fix_plan.md")


def _require_file(path):
    if not os.path.exists(path):
        raise AssertionError("expected file to exist: %s" % path)


# ---------------------------------------------------------------------------
# AC4 -- orchestrator.md invocation sentence mandates --out
# ---------------------------------------------------------------------------

class TestOrchestratorMandatesOutFlag(unittest.TestCase):
    """[DOC] AC4: orchestrator.md's reconciliation-invocation sentence (spec
    D.2) is amended to mandate `--out <run_dir>/gap_records_reconciled.json`,
    with an explicit "round is not complete until <file> exists" framing --
    while preserving the existing pre-filter/clustering/mandatory-trace
    substance verbatim (a diff-review style check: substance intact, only
    additive)."""

    @classmethod
    def setUpClass(cls):
        _require_file(ORCHESTRATOR_PATH)
        with open(ORCHESTRATOR_PATH) as f:
            cls.text = f.read()

    def _invocation_sentence(self):
        idx = self.text.find("run `harness/reconcile_gap_records.py")
        self.assertNotEqual(
            idx, -1,
            "expected to find the reconcile_gap_records.py invocation "
            "sentence in orchestrator.md",
        )
        return self.text[idx:idx + 700]

    def test_invocation_sentence_mandates_out_flag(self):
        sentence = self._invocation_sentence()
        self.assertIn(
            "--out", sentence,
            "the reconcile_gap_records.py invocation sentence must mandate "
            "the --out flag (spec D.2)",
        )

    def test_invocation_sentence_names_the_output_path(self):
        sentence = self._invocation_sentence()
        self.assertIn(
            "gap_records_reconciled.json", sentence,
            "the invocation sentence must name the structured-JSON output "
            "path, gap_records_reconciled.json (spec D.2)",
        )

    def test_invocation_sentence_states_round_not_complete_until_file_exists(self):
        sentence = self._invocation_sentence()
        self.assertIn(
            "round is not complete until", sentence,
            "the invocation sentence must preserve the explicit 'round is "
            "not complete until <file> exists' completion condition (spec "
            "D.2 -- Coder may adjust phrasing but must preserve this "
            "framing)",
        )

    def test_invocation_sentence_preserves_existing_prefilter_clustering_trace_substance(self):
        sentence = self._invocation_sentence()
        for phrase in (
            "pre-filter independent pairs",
            "cluster near-duplicates",
            "mandatorily trace",
        ):
            self.assertIn(
                phrase, sentence,
                "the amendment must be additive -- the existing "
                "pre-filter/clustering/mandatory-trace substance must "
                "survive intact (spec D.2, AC4)",
            )


# ---------------------------------------------------------------------------
# AC5 -- orchestrator.md persistence instruction gains a JSON sibling
# ---------------------------------------------------------------------------

class TestOrchestratorPersistenceInstructionGainsJsonSibling(unittest.TestCase):
    """[DOC] AC5: orchestrator.md's persistence instruction (spec D.2) gains
    a structured-JSON sibling requirement, additive to (not replacing) the
    existing narrative plan_check_log.md line."""

    @classmethod
    def setUpClass(cls):
        _require_file(ORCHESTRATOR_PATH)
        with open(ORCHESTRATOR_PATH) as f:
            cls.text = f.read()

    def _persistence_instruction(self):
        idx = self.text.find("Persist each plan-check cycle to")
        self.assertNotEqual(
            idx, -1,
            "expected to find the persistence instruction in orchestrator.md",
        )
        return self.text[idx:idx + 700]

    def test_persistence_instruction_still_has_narrative_plan_check_log_line(self):
        instruction = self._persistence_instruction()
        self.assertIn("plan_check_log.md", instruction)
        self.assertIn("broken_assumption", instruction)

    def test_persistence_instruction_gains_structured_json_sibling_requirement(self):
        instruction = self._persistence_instruction()
        self.assertIn(
            "gap_records_reconciled.json", instruction,
            "the persistence instruction must gain a structured-JSON "
            "sibling requirement naming gap_records_reconciled.json (spec "
            "D.2, AC5) -- additive, not a replacement of the narrative line",
        )
        self.assertIn("--out", instruction)


# ---------------------------------------------------------------------------
# AC6 -- roles/verifier.md gains LOOP-M10 (completeness, not grouping)
# ---------------------------------------------------------------------------

class TestVerifierLoopM10CompletenessGate(unittest.TestCase):
    """[DOC] AC6: roles/verifier.md gains a new `## LOOP-M10` section,
    immediately after the existing LOOP-M9 section, framed as a
    completeness check (existence + well-formed JSON + every raw GapRecord
    accounted for) -- explicitly NOT the earlier-rejected "lenses key, 2+
    distinct values" framing spec D.3 disclaims as a non-check."""

    @classmethod
    def setUpClass(cls):
        _require_file(VERIFIER_PATH)
        with open(VERIFIER_PATH) as f:
            cls.text = f.read()

    def _loop_m10_section(self):
        match = re.search(r"## LOOP-M10[^\n]*\n", self.text)
        self.assertIsNotNone(
            match, "expected a '## LOOP-M10' heading in roles/verifier.md",
        )
        start = match.start()
        next_heading = re.search(r"\n## ", self.text[match.end():])
        end = match.end() + next_heading.start() if next_heading else len(self.text)
        return self.text[start:end]

    def test_loop_m10_heading_exists_immediately_after_loop_m9(self):
        m9_idx = self.text.find("## LOOP-M9")
        m10_idx = self.text.find("## LOOP-M10")
        self.assertNotEqual(m9_idx, -1, "expected an existing '## LOOP-M9' section")
        self.assertNotEqual(m10_idx, -1, "expected a new '## LOOP-M10' section")
        self.assertGreater(
            m10_idx, m9_idx,
            "LOOP-M10 must be added immediately after the existing LOOP-M9 "
            "section (spec D.3)",
        )

    def test_loop_m10_title_mentions_reconciliation_json_existence_and_completeness(self):
        section = self._loop_m10_section()
        heading_line = section.split("\n", 1)[0]
        self.assertIn("RECONCILIATION", heading_line.upper())
        self.assertTrue(
            "COMPLETENESS" in heading_line.upper()
            or "EXISTENCE" in heading_line.upper(),
            "LOOP-M10's heading must reflect the existence & completeness "
            "framing (spec D.3): %r" % heading_line,
        )

    def test_loop_m10_states_existence_check(self):
        section = self._loop_m10_section()
        self.assertIn(
            "gap_records_reconciled.json", section,
            "LOOP-M10 must name the persisted JSON artifact it checks for "
            "existence (spec D.3, item 1)",
        )

    def test_loop_m10_states_well_formed_json_check(self):
        section = self._loop_m10_section()
        self.assertIn(
            "well-formed", section.lower(),
            "LOOP-M10 must state the well-formed-JSON check (spec D.3, "
            "item 2)",
        )

    def test_loop_m10_states_per_round_completeness_check_every_raw_gap_record_findable(self):
        section = self._loop_m10_section()
        self.assertIn("GapRecord", section)
        self.assertIn(
            "findable", section.lower(),
            "LOOP-M10 must state the completeness check: every raw "
            "GapRecord from the round's lens dispatches is findable "
            "somewhere in the file (spec D.3, item 3)",
        )

    def test_loop_m10_explicitly_disclaims_grouping_correctness_as_out_of_scope(self):
        section = self._loop_m10_section()
        self.assertTrue(
            "does not check" in section.lower(),
            "LOOP-M10 must explicitly state what it does NOT check -- that "
            "merged_items grouping correctly identifies same-finding "
            "overlap across lenses (spec D.3) -- the completeness-not-"
            "grouping-correctness framing that distinguishes this gate "
            "from the earlier-rejected 'lenses key, 2+ distinct values' "
            "proposal",
        )
        self.assertIn("grouping", section.lower())

    def test_loop_m10_does_not_gate_its_check_on_a_lenses_key_presence(self):
        section = self._loop_m10_section()
        # The earlier-rejected framing gated the check on entries that
        # ALREADY carry a "lenses" key (checking 2+ distinct values inside
        # it) -- spec D.3 explicitly disclaims this as a NON-CHECK, since
        # same-finding pairs land as separate singletons with NO "lenses"
        # key at all and would trivially evade it. Assert the gate instead
        # documents the fallback: walking each entry's own nested
        # GapRecord(s).
        self.assertTrue(
            "fall back" in section.lower() or "walking" in section.lower(),
            "LOOP-M10 must document the fallback-to-walking-nested-"
            "GapRecords rule (spec B's consumer rule, cited by D.3 item 3) "
            "rather than gating completeness on a 'lenses' key's presence",
        )


# ---------------------------------------------------------------------------
# AC7 -- fix_plan.md gains the H-RECONCILE-JSON-PERSIST-1 entry
# ---------------------------------------------------------------------------

class TestFixPlanReconcileJsonPersistEntry(unittest.TestCase):
    """[DOC] AC7: fix_plan.md gains the H-RECONCILE-JSON-PERSIST-1 entry
    (D.4), status OPEN, including the prior-art check against
    H-FINDINGS-PERSISTENCE-1 and the git-log-proof closure requirement
    verbatim."""

    @classmethod
    def setUpClass(cls):
        _require_file(FIX_PLAN_PATH)
        with open(FIX_PLAN_PATH) as f:
            cls.text = f.read()

    def test_entry_heading_exists_with_open_status(self):
        idx = self.text.find("H-RECONCILE-JSON-PERSIST-1")
        self.assertNotEqual(
            idx, -1,
            "expected an 'H-RECONCILE-JSON-PERSIST-1' entry in fix_plan.md",
        )
        heading_window = self.text[idx:idx + 200]
        self.assertIn("OPEN", heading_window)

    def test_entry_cites_prior_art_check_against_findings_persistence_1(self):
        idx = self.text.find("H-RECONCILE-JSON-PERSIST-1")
        self.assertNotEqual(idx, -1)
        window = self.text[idx:idx + 4000]
        self.assertIn(
            "H-FINDINGS-PERSISTENCE-1", window,
            "the entry must include the prior-art check against the "
            "existing, related-but-distinct H-FINDINGS-PERSISTENCE-1 entry "
            "(spec D.4)",
        )

    def test_entry_requires_git_log_proof_for_closure(self):
        idx = self.text.find("H-RECONCILE-JSON-PERSIST-1")
        self.assertNotEqual(idx, -1)
        window = self.text[idx:idx + 6000]
        self.assertIn("git log", window)
        self.assertIn(
            "may only be marked CLOSED", window,
            "the entry must require literal git-log-proof of the described "
            "diffs before it may be marked CLOSED (spec D.4's closure "
            "requirement, guarding against the phantom-CLOSED-entry "
            "pattern already found twice in this file)",
        )


if __name__ == "__main__":
    unittest.main()
