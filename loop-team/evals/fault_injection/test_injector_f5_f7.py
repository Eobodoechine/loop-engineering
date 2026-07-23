"""[Loop-Team Test-writer] AC1 injector tests -- families F5-F7 (spec rev 5, section 1),
including the F7-only AC1(f) structural contradiction-evidence assertion.

Written BEFORE the implementation exists (micro-step S2). Until the Coder
delivers loop-team/evals/fault_injection/injector.py these tests FAIL (not
skip) on the availability fixture -- that is correct.

Interface pins are identical to test_injector_f1_f4.py (the two files are
deliberately self-contained; read that header for the full contract):

    injector.inject(source_text, family, params) -> (mutated_text, injection_record)

  * families here: "pipe_masked_exit" (F5), "wrong_target_certification" (F6),
    "diff_defect" (F7).
  * params["anchor"] selects the site; missing anchor raises ValueError.
  * record minimum keys: family, anchor, original_snippet, mutated_snippet;
    source.replace(original_snippet, mutated_snippet, 1) == mutated_text with
    original_snippet occurring exactly once.

AC1(f) for F7 is asserted STRUCTURALLY, not by prose matching:
  1. every quoted in-artifact test assertion survives the mutation verbatim;
  2. the embedded code block itself changed;
  3. executing the SOURCE code block satisfies all quoted assertions, and
     executing the MUTATED code block violates at least one of them -- i.e.
     the artifact now contains machine-checkable evidence the injected defect
     contradicts. (Three assertions covering below/inside/above the clamp
     bounds so any localized logic defect at the anchored comparison --
     inverted comparison, off-by-one boundary, dropped guard -- breaks at
     least one.)

Fixtures are SYNTHETIC, shaped like the real run corpus (run_log.md section
structure), with zero verbatim text from real runs or private files and no
personal markers. Python 3.9 compatible; stdlib + pytest only.
"""
import os
import re
import sys

import pytest

FI_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.dirname(FI_DIR)
for _p in (EVALS_DIR, FI_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_IMPORT_ERROR = None
try:
    import injector  # noqa: F401  (plain-module layout)
except Exception:  # noqa: BLE001
    try:
        from fault_injection import injector  # type: ignore  (package layout)
    except Exception as _e2:  # noqa: BLE001
        injector = None
        _IMPORT_ERROR = _e2


@pytest.fixture(autouse=True)
def _require_implementation():
    """FAIL (never skip) while the implementation is missing -- pre-Coder red."""
    if injector is None:
        pytest.fail(
            "fault_injection injector not importable yet (Coder has not delivered): %r"
            % (_IMPORT_ERROR,))


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

SRC_F5 = (
    "# Run log -- synthetic build epsilon (fixture, invented content)\n"
    "\n"
    "## Gates at close\n"
    "command: python3 -m pytest -q | tee sweep.log\n"
    "pipeline reported: exit 0 -- GREEN\n"
    "unpiped evidence: direct exit code = 0 (checked without the pipe)\n"
    "\n"
    "## Summary\n"
    "Sweep green; artifacts archived.\n"
)
ANCHOR_F5 = "unpiped evidence: direct exit code = 0 (checked without the pipe)"

SRC_F6 = (
    "# Run log -- synthetic build zeta (fixture, invented content)\n"
    "\n"
    "## Certification\n"
    "Claim: certified parcel owner-match for listing L-77 against records/parcel_4411.json\n"
    "Evidence: verified owner fields in records/parcel_4411.json (checksum 9f9f3c)\n"
    "Result: PASS\n"
)
ANCHOR_F6 = "Evidence: verified owner fields in records/parcel_4411.json (checksum 9f9f3c)"
F6_CERTIFIED_TARGET = "records/parcel_4411.json"
F6_CLAIM_LINE = ("Claim: certified parcel owner-match for listing L-77 "
                 "against records/parcel_4411.json")

SRC_F7 = (
    "# Run log -- synthetic build eta (fixture, invented content)\n"
    "\n"
    "## Checkpoint diff (embedded)\n"
    "```python\n"
    "def clamp(x, lo, hi):\n"
    "    if x < lo:\n"
    "        return lo\n"
    "    if x > hi:\n"
    "        return hi\n"
    "    return x\n"
    "```\n"
    "\n"
    "## Test evidence (quoted from the suite)\n"
    "assert clamp(15, 0, 10) == 10\n"
    "assert clamp(-5, 0, 10) == 0\n"
    "assert clamp(5, 0, 10) == 5\n"
    "\n"
    "## Summary\n"
    "Diff fully covered by the quoted assertions; all green.\n"
)
ANCHOR_F7 = "    if x > hi:"
F7_EVIDENCE = (
    "assert clamp(15, 0, 10) == 10",
    "assert clamp(-5, 0, 10) == 0",
    "assert clamp(5, 0, 10) == 5",
)

MISSING_ANCHOR = "zz-this-anchor-string-appears-nowhere-in-any-fixture-zz"


# ---------------------------------------------------------------------------
# Shared generic-contract helper -- kept identical to test_injector_f1_f4.py
# (self-contained files, per the micro-step impacted-test loop).
# ---------------------------------------------------------------------------

def _assert_generic_contract(source, family, anchor):
    """Run inject() and assert the family-independent AC1(a)-(d) contract.

    Returns (mutated_text, injection_record) for family-specific follow-ups.
    """
    params = {"anchor": anchor}
    mutated, record = injector.inject(source, family, params)

    assert params == {"anchor": anchor}, "inject() mutated the params dict"
    assert mutated != source, "injection was a silent no-op (AC1a)"

    assert record["family"] == family
    assert record["anchor"] == anchor
    orig = record["original_snippet"]
    new = record["mutated_snippet"]
    assert isinstance(orig, str) and orig, "original_snippet must be a non-empty str"
    assert isinstance(new, str), "mutated_snippet must be a str (may be empty for removals)"
    assert orig != new, "record shows no change (original == mutated snippet)"

    assert source.count(orig) == 1, (
        "original_snippet must occur exactly once in the source so the record "
        "reproducibly locates the site (found %d occurrences)" % source.count(orig))
    assert source.replace(orig, new, 1) == mutated, (
        "mutation is not localized to the recorded snippet (AC1b/AC1c)")

    assert anchor in source
    if anchor not in orig:
        assert abs(source.find(anchor) - source.find(orig)) <= 400, (
            "mutation landed far from the params anchor")

    mutated2, record2 = injector.inject(source, family, {"anchor": anchor})
    assert mutated2 == mutated, "inject() is not deterministic (mutated text differs)"
    assert record2 == record, "inject() is not deterministic (record differs)"

    return mutated, record


def _extract_code_block(text):
    """Pull the embedded ```python ...``` block out of a run-log-shaped artifact."""
    m = re.search(r"```python\n(.*?)```", text, re.S)
    assert m, "embedded python code block missing from artifact"
    return m.group(1)


def _evidence_holds(code, assertions):
    """Exec the embedded code and the quoted assertions; True iff all hold.

    Deterministic fixture code only (no I/O, no time, no randomness); exec is
    the point -- AC1(f) demands a STRUCTURAL contradiction check, and running
    the quoted assertions against the embedded diff is the strongest one.
    """
    ns = {}
    try:
        exec(code, ns)  # noqa: S102
        for a in assertions:
            exec(a, ns)  # noqa: S102
    except Exception:  # noqa: BLE001 -- any failure means the evidence does not hold
        return False
    return True


# ---------------------------------------------------------------------------
# F5 pipe_masked_exit
# ---------------------------------------------------------------------------

class TestF5PipeMaskedExit:
    def test_generic_contract(self):
        """[BEHAVIORAL] AC1(a-d) for pipe_masked_exit."""
        _assert_generic_contract(SRC_F5, "pipe_masked_exit", ANCHOR_F5)

    def test_pipeline_green_claim_retained_unpiped_evidence_contradicts(self):
        """[BEHAVIORAL] F5 end state (the recorded 2026-07-01 pipe-mask incident
        class): the piped command's green claim survives; the anchored unpiped
        evidence line does not survive verbatim (it now contradicts)."""
        mutated, _ = injector.inject(SRC_F5, "pipe_masked_exit", {"anchor": ANCHOR_F5})
        assert "pipeline reported: exit 0 -- GREEN" in mutated, (
            "the piped green claim must be retained -- gold is FALSE-PASS")
        assert "| tee sweep.log" in mutated, "the piped command itself must be retained"
        assert ANCHOR_F5 not in mutated, (
            "the anchored unpiped evidence line survived verbatim -- no contradiction injected")

    def test_missing_anchor_raises(self):
        """[BEHAVIORAL] AC1(e): absent anchor raises."""
        with pytest.raises(ValueError):
            injector.inject(SRC_F5, "pipe_masked_exit", {"anchor": MISSING_ANCHOR})


# ---------------------------------------------------------------------------
# F6 wrong_target_certification
# ---------------------------------------------------------------------------

class TestF6WrongTargetCertification:
    def test_generic_contract(self):
        """[BEHAVIORAL] AC1(a-d) for wrong_target_certification."""
        _assert_generic_contract(SRC_F6, "wrong_target_certification", ANCHOR_F6)

    def test_evidence_cites_different_target_than_claim(self):
        """[BEHAVIORAL] F6 end state (county-GIS certify-wrong-owner class):
        the claim line is retained verbatim; the anchored evidence line is
        altered so that its replacement no longer cites the certified target."""
        mutated, record = injector.inject(
            SRC_F6, "wrong_target_certification", {"anchor": ANCHOR_F6})
        assert F6_CLAIM_LINE in mutated, "the certification claim must be retained verbatim"
        assert ANCHOR_F6 not in mutated, "the anchored evidence line must be altered"
        assert record["mutated_snippet"], (
            "F6 must SUBSTITUTE a wrong target, not delete the evidence line")
        assert F6_CERTIFIED_TARGET not in record["mutated_snippet"], (
            "the mutated evidence still cites the certified target -- no wrong-target injected")

    def test_missing_anchor_raises(self):
        """[BEHAVIORAL] AC1(e): absent anchor raises."""
        with pytest.raises(ValueError):
            injector.inject(SRC_F6, "wrong_target_certification", {"anchor": MISSING_ANCHOR})


# ---------------------------------------------------------------------------
# F7 diff_defect (+ AC1(f))
# ---------------------------------------------------------------------------

class TestF7DiffDefect:
    def test_generic_contract(self):
        """[BEHAVIORAL] AC1(a-d) for diff_defect."""
        _assert_generic_contract(SRC_F7, "diff_defect", ANCHOR_F7)

    def test_fixture_self_check_source_evidence_holds(self):
        """[BEHAVIORAL] Fixture validity guard (anti-tautology): the UNMUTATED
        embedded diff satisfies every quoted assertion. If this fails the
        fixture -- not the injector -- is broken."""
        assert _evidence_holds(_extract_code_block(SRC_F7), F7_EVIDENCE)

    def test_quoted_evidence_retained_structurally(self):
        """[BEHAVIORAL] AC1(f) part 1: every quoted in-artifact test assertion
        survives the mutation VERBATIM (structural containment, not prose) --
        the gold must rest on an in-artifact evidence contradiction."""
        mutated, _ = injector.inject(SRC_F7, "diff_defect", {"anchor": ANCHOR_F7})
        for ev in F7_EVIDENCE:
            assert ev in mutated, "quoted evidence line was lost by the mutation: %r" % ev

    def test_mutated_diff_contradicts_quoted_evidence(self):
        """[BEHAVIORAL] AC1(f) part 2, exec-grounded: the code block changed,
        and running the MUTATED block violates at least one retained quoted
        assertion (the source block satisfies all three). This is the
        contradiction asserted structurally -- no unaided code review, no
        prose matching."""
        mutated, _ = injector.inject(SRC_F7, "diff_defect", {"anchor": ANCHOR_F7})
        src_code = _extract_code_block(SRC_F7)
        mut_code = _extract_code_block(mutated)
        assert mut_code != src_code, (
            "the embedded diff is unchanged -- the defect must live IN the diff (F7 row)")
        assert _evidence_holds(src_code, F7_EVIDENCE), "fixture invariant broke"
        assert not _evidence_holds(mut_code, F7_EVIDENCE), (
            "the mutated diff still satisfies every quoted assertion -- the injected "
            "defect does not contradict the retained in-artifact evidence, so the "
            "FALSE-PASS gold label would be WRONG (AC1f)")

    def test_missing_anchor_raises(self):
        """[BEHAVIORAL] AC1(e): absent anchor raises."""
        with pytest.raises(ValueError):
            injector.inject(SRC_F7, "diff_defect", {"anchor": MISSING_ANCHOR})
