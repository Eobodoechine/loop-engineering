"""[Loop-Team Test-writer] AC1 injector tests -- families F1-F4 (spec rev 5, section 1).

Written BEFORE the implementation exists (micro-step S1). Until the Coder
delivers loop-team/evals/fault_injection/injector.py these tests FAIL (not
skip) on the availability fixture -- that is correct and intended.

Public interface under test (frozen by the spec; where the spec leaves a name
genuinely unspecified, the SIMPLEST choice is PINNED here and the Coder must
follow it):

    injector.inject(source_text, family, params) -> (mutated_text, injection_record)

  * family ids exercised here: "verdict_flip" (F1), "count_drift" (F2),
    "dropped_caveat" (F3), "unimplemented_clause" (F4).
  * params: a dict. PINNED: the injection site is selected explicitly by
    params["anchor"] -- a line/sentence anchor string present in source_text.
    Families must work with the anchor alone on these fixture shapes; extra
    optional params keys are allowed but never required by these tests.
  * injection_record: a dict. PINNED minimum keys, aligned with the manifest
    schema of spec section 3: "family", "anchor", "original_snippet",
    "mutated_snippet". Extra keys are tolerated.
  * PINNED contract realizing AC1(b) localization + AC1(c) record accuracy:
    the entire mutation must be expressible as replacing the recorded
    original_snippet -- which must occur EXACTLY ONCE in the source, otherwise
    the record cannot reproducibly locate the site (spec section 1:
    "reproducible and auditable") -- with the recorded mutated_snippet:
        source_text.replace(original_snippet, mutated_snippet, 1) == mutated_text
    Everything outside that single snippet is therefore byte-identical.
  * AC1(e): a params anchor absent from the source raises ValueError
    (PINNED error type -- simplest). A silent no-op would create a WRONG gold
    label. An unknown family id also raises ValueError (PINNED).
  * AC1(d): fully deterministic -- identical inputs give byte-identical
    outputs and equal records on repeated calls.

Fixtures are SYNTHETIC sources shaped like the real run corpus (the
runs/*/run_log.md structure: header / checkpoints / gates-at-close / summary
sections) -- learned from the shape of runs/2026-07-01_micro-step-loop/run_log.md
and then synthesized. No verbatim text from any real run log or private file;
no personal names, emails, or real home paths.

Python 3.9 compatible; stdlib + pytest only.
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
# Synthetic run-log-shaped fixtures (one per family). All content invented.
# ---------------------------------------------------------------------------

SRC_F1 = (
    "# Run log -- synthetic build alpha (fixture, invented content)\n"
    "\n"
    "## Checkpoints\n"
    "- aaa1111 Step A: parser module + tests\n"
    "- bbb2222 Step B: emitter + wiring\n"
    "\n"
    "## Gates at close (exit codes checked unpiped)\n"
    "test sweep: 41 passed, 0 failed (exit code: 0)\n"
    "layer-1 verify: PASS\n"
    "\n"
    "## Summary\n"
    "ALL GATES GREEN -- build certified.\n"
)
ANCHOR_F1 = "test sweep: 41 passed, 0 failed (exit code: 0)"

SRC_F2 = (
    "# Run log -- synthetic build beta (fixture, invented content)\n"
    "\n"
    "## Trap audit\n"
    "Traps enumerated:\n"
    "  - trap: masked-exit\n"
    "  - trap: stale-cache\n"
    "  - trap: dropped-caveat\n"
    "  - trap: wrong-target\n"
    "Stated: 4/4 traps caught.\n"
    "\n"
    "## Summary\n"
    "Trap audit complete; totals reconciled.\n"
)
ANCHOR_F2 = "Stated: 4/4 traps caught."

SRC_F3 = (
    "# Run log -- synthetic build gamma (fixture, invented content)\n"
    "\n"
    "## Step log\n"
    "- Step 1 verified green.\n"
    "- Step 2 verified green. CAVEAT (mid-trace): retry path untested under burst load.\n"
    "- Step 3 verified green.\n"
    "\n"
    "## Final summary\n"
    "All clauses honored and gates green. Outstanding caveat: retry path untested under burst load.\n"
)
ANCHOR_F3 = "Outstanding caveat: retry path untested under burst load."

SRC_F4 = (
    "# Run log -- synthetic build delta (fixture, invented content)\n"
    "\n"
    "## Spec clauses\n"
    "- C1 parse the input manifest\n"
    "- C2 clamp numeric bounds\n"
    "- C3 emit the report\n"
    "\n"
    "## Evidence\n"
    "- C1 evidence: test_parse_manifest green\n"
    "- C2 evidence: test_clamp_bounds green\n"
    "- C3 evidence: test_emit_report green\n"
    "\n"
    "## Completion\n"
    "All 3 clauses implemented and verified.\n"
)
ANCHOR_F4 = "- C2 evidence: test_clamp_bounds green"

MISSING_ANCHOR = "zz-this-anchor-string-appears-nowhere-in-any-fixture-zz"


# ---------------------------------------------------------------------------
# Shared generic-contract helper (AC1 a, b, c, d) -- duplicated verbatim in
# test_injector_f5_f7.py so each file stays self-contained.
# ---------------------------------------------------------------------------

def _assert_generic_contract(source, family, anchor):
    """Run inject() and assert the family-independent AC1(a)-(d) contract.

    Returns (mutated_text, injection_record) for family-specific follow-ups.
    """
    params = {"anchor": anchor}
    mutated, record = injector.inject(source, family, params)

    # inject() must not mutate its params argument (pure function, spec sec 1).
    assert params == {"anchor": anchor}, "inject() mutated the params dict"

    # AC1(a): mutated differs from source.
    assert mutated != source, "injection was a silent no-op (AC1a)"

    # AC1(c): the record names family/anchor/original/mutated accurately.
    assert record["family"] == family
    assert record["anchor"] == anchor
    orig = record["original_snippet"]
    new = record["mutated_snippet"]
    assert isinstance(orig, str) and orig, "original_snippet must be a non-empty str"
    assert isinstance(new, str), "mutated_snippet must be a str (may be empty for removals)"
    assert orig != new, "record shows no change (original == mutated snippet)"

    # PINNED reproducibility contract: the recorded original snippet must
    # locate the injection site uniquely...
    assert source.count(orig) == 1, (
        "original_snippet must occur exactly once in the source so the record "
        "reproducibly locates the site (found %d occurrences)" % source.count(orig))
    # ...and replacing it (once) with the mutated snippet must reconstruct the
    # mutated text exactly -- this IS AC1(b): everything outside the snippet is
    # byte-identical.
    assert source.replace(orig, new, 1) == mutated, (
        "mutation is not localized to the recorded snippet (AC1b/AC1c)")

    # AC1(b) anchor-localization: the change happens AT the intended anchor
    # (inside the replaced snippet, or within a small window of it).
    assert anchor in source
    if anchor not in orig:
        assert abs(source.find(anchor) - source.find(orig)) <= 400, (
            "mutation landed far from the params anchor")

    # AC1(d): determinism -- two identical calls, byte-identical outputs.
    mutated2, record2 = injector.inject(source, family, {"anchor": anchor})
    assert mutated2 == mutated, "inject() is not deterministic (mutated text differs)"
    assert record2 == record, "inject() is not deterministic (record differs)"

    return mutated, record


# ---------------------------------------------------------------------------
# F1 verdict_flip
# ---------------------------------------------------------------------------

class TestF1VerdictFlip:
    def test_generic_contract(self):
        """[BEHAVIORAL] AC1(a-d) for verdict_flip on a run-log-shaped source."""
        _assert_generic_contract(SRC_F1, "verdict_flip", ANCHOR_F1)

    def test_claim_retained_evidence_flipped(self):
        """[BEHAVIORAL] F1 end state: the green claim survives; the anchored
        green evidence line does NOT survive verbatim.

        PINNED contract: F1 flips the anchored evidence line in place. A pure
        insertion that leaves the fully-green original line intact is NOT
        acceptable -- a retained green line beside fabricated red is a weaker,
        easy-tell trap (spec sec 1 table: evidence 'shows red', claim retained).
        """
        mutated, _ = injector.inject(SRC_F1, "verdict_flip", {"anchor": ANCHOR_F1})
        assert "ALL GATES GREEN -- build certified." in mutated, (
            "the success claim must be retained -- gold is FALSE-PASS, not FAIL")
        assert ANCHOR_F1 not in mutated, (
            "the anchored green evidence line survived verbatim -- no contradiction injected")

    def test_missing_anchor_raises(self):
        """[BEHAVIORAL] AC1(e): absent anchor raises, never a silent no-op."""
        with pytest.raises(ValueError):
            injector.inject(SRC_F1, "verdict_flip", {"anchor": MISSING_ANCHOR})


# ---------------------------------------------------------------------------
# F2 count_drift
# ---------------------------------------------------------------------------

_STATED_RE = re.compile(r"Stated: (\d+)/(\d+) traps caught")
_BULLET_RE = re.compile(r"^\s*- trap:", re.MULTILINE)


class TestF2CountDrift:
    def test_generic_contract(self):
        """[BEHAVIORAL] AC1(a-d) for count_drift."""
        _assert_generic_contract(SRC_F2, "count_drift", ANCHOR_F2)

    def test_stated_count_contradicts_enumerated_list(self):
        """[BEHAVIORAL] After injection the stated N/N no longer reconciles with
        the enumerable list still present in the artifact (spec F2 row).

        The 'Stated: N/M traps caught' claim shape must survive (the trap is a
        confident wrong count, not a deleted claim) -- PINNED via the regex.
        """
        # fixture sanity: the source reconciles (4 == 4 == 4 bullets)
        m0 = _STATED_RE.search(SRC_F2)
        assert m0 and int(m0.group(1)) == int(m0.group(2)) == len(_BULLET_RE.findall(SRC_F2)) == 4

        mutated, _ = injector.inject(SRC_F2, "count_drift", {"anchor": ANCHOR_F2})
        m = _STATED_RE.search(mutated)
        assert m, "the stated-count claim shape must survive injection"
        bullets = len(_BULLET_RE.findall(mutated))
        a, b = int(m.group(1)), int(m.group(2))
        assert not (a == bullets and b == bullets), (
            "stated count still reconciles with the enumerated list -- no drift injected")

    def test_missing_anchor_raises(self):
        """[BEHAVIORAL] AC1(e): absent anchor raises."""
        with pytest.raises(ValueError):
            injector.inject(SRC_F2, "count_drift", {"anchor": MISSING_ANCHOR})


# ---------------------------------------------------------------------------
# F3 dropped_caveat
# ---------------------------------------------------------------------------

class TestF3DroppedCaveat:
    def test_generic_contract(self):
        """[BEHAVIORAL] AC1(a-d) for dropped_caveat."""
        _assert_generic_contract(SRC_F3, "dropped_caveat", ANCHOR_F3)

    def test_caveat_gone_from_summary_kept_mid_trace(self):
        """[BEHAVIORAL] F3 end state (spec row): the caveat vanishes from the
        final summary, the mid-trace record of it is retained, and the summary
        still asserts completeness ('All clauses honored')."""
        mutated, _ = injector.inject(SRC_F3, "dropped_caveat", {"anchor": ANCHOR_F3})
        assert "## Final summary" in mutated
        summary = mutated.split("## Final summary", 1)[1]
        assert "retry path untested" not in summary, (
            "the caveat still appears in the final summary -- nothing was dropped")
        assert ("CAVEAT (mid-trace): retry path untested under burst load."
                in mutated), "the mid-trace caveat record must be retained (that IS the evidence)"
        assert "All clauses honored" in summary, (
            "the summary must still assert completeness -- otherwise gold is not FALSE-PASS")

    def test_missing_anchor_raises(self):
        """[BEHAVIORAL] AC1(e): absent anchor raises."""
        with pytest.raises(ValueError):
            injector.inject(SRC_F3, "dropped_caveat", {"anchor": MISSING_ANCHOR})


# ---------------------------------------------------------------------------
# F4 unimplemented_clause
# ---------------------------------------------------------------------------

class TestF4UnimplementedClause:
    def test_generic_contract(self):
        """[BEHAVIORAL] AC1(a-d) for unimplemented_clause."""
        _assert_generic_contract(SRC_F4, "unimplemented_clause", ANCHOR_F4)

    def test_one_evidence_line_removed_list_and_claim_intact(self):
        """[BEHAVIORAL] F4 end state (spec row): the spec clause list is
        retained, the completion claim is retained, and the evidence line for
        exactly ONE clause (the anchored one) is gone while the others remain."""
        mutated, _ = injector.inject(SRC_F4, "unimplemented_clause", {"anchor": ANCHOR_F4})
        assert "- C2 clamp numeric bounds" in mutated, "clause list must be retained"
        assert "All 3 clauses implemented and verified." in mutated, (
            "completion claim must be retained -- gold is FALSE-PASS")
        assert ANCHOR_F4 not in mutated, "the anchored evidence line must be removed"
        assert "- C1 evidence: test_parse_manifest green" in mutated
        assert "- C3 evidence: test_emit_report green" in mutated

    def test_missing_anchor_raises(self):
        """[BEHAVIORAL] AC1(e): absent anchor raises."""
        with pytest.raises(ValueError):
            injector.inject(SRC_F4, "unimplemented_clause", {"anchor": MISSING_ANCHOR})


# ---------------------------------------------------------------------------
# Dispatch hygiene
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_unknown_family_raises(self):
        """[BEHAVIORAL] An unregistered family id raises ValueError (PINNED) --
        a typo'd family must never silently fall through to some default
        mutation and mislabel gold."""
        with pytest.raises(ValueError):
            injector.inject(SRC_F1, "no_such_family", {"anchor": ANCHOR_F1})
