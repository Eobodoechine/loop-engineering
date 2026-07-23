"""Evidence-Gate Phase 5 -- AC12 full-suite-green regression cross-check
(spec: loop-team/runs/2026-07-09_evidence-gate-phase5/specs/spec.md, AC12:
"Full existing test suites across everything this phase touches or imports
from remain green.")

Deliberately a SEPARATE, STANDALONE file (not appended into any of the
suites it names) so the subprocess pytest invocation below never has to
worry about self-recollecting the file it lives in -- the same unbounded-
recursion hazard test_fixplan_closure_lint.py's own AC11 precedent and
test_verify_harness.py's AC7FullSuiteCrossCheck precedent both navigate the
same way (see those files' own docstrings/banners for the identical
reasoning).

Names the 4 pre-existing (already-shipped, Phase 1-4) suites this phase's
Items 2/3/4 reuse-from or additively-extend, unmodified in their own logic
per this whole phase's Non-goals ("No change to any Phase 1-4 function's own
logic"):
  - loop-team/harness/test_fixplan_closure_lint.py (fixplan_closure_lint.py
    is reused UNCHANGED by closure_freshness_sweep.py, evidence_ledger.py,
    and 3 of the 4 mutation-regression targets)
  - loop-team/harness/test_research_authenticity_check.py
    (research_authenticity_check.py gains genre "E", additive-only)
  - loop-team/harness/test_run_and_record.py (run_and_record.py is reused
    UNCHANGED to build every real Proof-block fixture across this whole
    phase's own test files)
  - hooks/test_closure_touch_scan.py (closure_touch_scan.py's
    CLOSURE_HEADING_RE is the 4th mutation-regression target in
    test_closure_lint_mutation_regression.py)

Deliberately does NOT include this phase's own new test files
(test_closure_freshness_sweep.py, test_closure_lint_mutation_regression.py,
test_evidence_ledger.py, and the genre-E additions inside
test_research_authenticity_check.py) in THIS specific cross-check -- those
are individually gated by AC1-11 above and (with the sole exception of
test_closure_lint_mutation_regression.py, whose 4 targets are all
already-shipped code -- see that file's own docstring) are EXPECTED to fail
until the Coder's implementation lands, per roles/test_writer.md's own
header. AC12's own concern is narrower and different: that this phase's
ADDITIVE changes never regress what was ALREADY shipped and green before
this build started.

This is why this file's own test is expected to ALREADY PASS on a clean
checkout, TODAY, before any Phase 5 code lands, and must keep passing after
it does -- a regression guard, not a red-until-implemented test (matching
test_fixplan_closure_lint.py's own AC7/AC11 precedent, and
test_verify_harness.py's AC7FullSuiteCrossCheck precedent, for the identical
"pre-existing suite must not regress" situation).

Run: python3 -m pytest loop-team/harness/test_evidence_gate_phase5_full_suite_regression.py -q
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))

AC12_NAMED_SUITES = [
    "loop-team/harness/test_fixplan_closure_lint.py",
    "loop-team/harness/test_research_authenticity_check.py",
    "loop-team/harness/test_run_and_record.py",
    "hooks/test_closure_touch_scan.py",
]


class TestAC12FullExistingSuitesRemainGreen:
    def test_each_named_suite_file_actually_exists(self):
        """Sanity precondition -- if a named path were ever wrong/renamed,
        the subprocess cross-check below could otherwise mask that as a
        pytest usage error rather than a clearly-attributable missing-file
        failure."""
        for rel_path in AC12_NAMED_SUITES:
            abs_path = os.path.join(REPO_ROOT, rel_path)
            assert os.path.isfile(abs_path), "expected %s to exist" % abs_path

    def test_named_pre_existing_suites_pass_together_in_one_invocation(self):
        """Run the 4 AC12-named, pre-existing suites in ONE pytest
        invocation (not individually, and not via this file's own process)
        -- the representative "run together" shape that would surface a
        cross-file collection/fixture interaction regression that running
        each file alone could hide."""
        argv = [sys.executable, "-m", "pytest", "-q"] + AC12_NAMED_SUITES
        p = subprocess.run(
            argv, cwd=REPO_ROOT, capture_output=True, text=True, timeout=900,
        )
        combined = p.stdout + p.stderr
        assert p.returncode == 0, (
            "the 4 pre-existing, already-shipped suites this phase reuses "
            "from or additively extends must all pass when run together in "
            "one pytest invocation from the repo root; got returncode=%s, "
            "output:\n%s" % (p.returncode, combined)
        )


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-q"]))
