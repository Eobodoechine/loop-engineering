"""Tests for the plan-check gap-record reconciliation harness.

Spec: loop-team/runs/2026-07-02_plan-check-reconciliation/specs/spec.md
Design: research/plan-check-reconciliation-prior-art-2026-07-02.md
        ("Reconciliation-step sketch" section + its pseudocode).

Run with:
    python3 -m pytest loop-team/harness/test_reconcile_gap_records.py -q

Written BEFORE `reconcile_gap_records.py` exists (Test-writer role, Tier 1).
These tests WILL fail on collection/import until the Coder delivers the
module -- that is expected and correct for this stage of the loop.

--- Real-incident provenance (NOT invented fixtures) ---

AC2 and AC3 fixtures are built from the LITERAL text of
`runs/2026-07-02_ops-clock/plan_check_log.md`, read directly for this
assignment. Quoting exactly what was found:

Iteration 14 (three INDEPENDENT gaps, disjoint mechanisms), verbatim:
    "regression-audit: dismissAlert rewrite silently dropped the atomic
    concurrent-dismiss guard (Room.updateMany({alertState:{not:'NONE'}}),
    today's mechanism behind a currently-green adversarial test) and the
    explicit cross-org ownership check (backing AC12) ... Added AC35, AC36."

    "concurrency-isolation: the shared recompute step (3a/3b/dismissAlert/
    completeTask) has a genuine write-skew race under Postgres ReadCommitted
    -- two concurrent transactions closing DIFFERENT tasks on the SAME room
    can each read a stale open-task snapshot and the later write silently
    stomps the earlier one ... Fixed with a row lock (SELECT...FOR UPDATE)
    as the recompute's first statement. Added AC34."

    "state-completeness: alertState=PENDING_VACANCY + an open COLLECTIONS/
    DISPUTE Task underneath (AC27-proven reachable) was an uncovered matrix
    cell in BOTH dismissAlert's PENDING_VACANCY fallback (silently orphaned
    the open Task) and the badge-adjacent countdown's reverse-map table (no
    PENDING_VACANCY entry). Fixed both. Added AC37, AC38."

Gap-28 (iteration 16, the CONTRADICTORY pair), verbatim:
    "gap 28 (precision-of-instruction): a genuine CONTRADICTION between AC28
    (non-empty open-task set must always override preserved PENDING_VACANCY)
    and AC42 (must NOT override in the dual-open-then-partial-dismiss case)
    -- no single empty-set-gated branch satisfies both. This is a real
    design conflict, not a wording gap. Fixed by introducing an explicit
    trigger:'CREATE'|'CLOSE' parameter to the recompute step: CREATE always
    overrides (AC28), CLOSE preserves PENDING_VACANCY unconditionally on
    prior state regardless of remaining open-task set (AC27 + AC42/AC43
    simultaneously)."

    "gap 28 is qualitatively different from every prior gap in this
    thread -- it's not a missing rule or an unstated edge case, it's two
    ALREADY-ADOPTED, previously-verified ACs (28 and 42, from two different
    rounds) turning out to be mutually unsatisfiable under the algorithm as
    worded."

The spec (AC2) names the shared mechanism as "AlertState recompute" and the
contradictory pair as AC28 vs AC42 -- both fixtures below use those literal
identifiers, not invented stand-ins.
"""
import os
import sys
import unittest

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HARNESS_DIR)

try:
    import reconcile_gap_records as rgr  # noqa: E402
    IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - exercised until Coder delivers
    rgr = None
    IMPORT_ERROR = exc


def _require_module():
    """Fail loudly (not skip) when the module under test doesn't exist yet.

    This is intentional Tier-1 (Test-writer-before-Coder) behavior: right now
    there is no `reconcile_gap_records.py`, so every test below MUST fail,
    not be silently skipped -- a skip would understate how much of the
    acceptance criteria is currently unmet. Each test calls this at the top
    of its body so the failure is attributed to that specific test (clear
    per-AC signal) rather than only to one module-level import test.
    """
    if rgr is None:
        raise AssertionError(
            "harness/reconcile_gap_records.py does not exist/import yet "
            "(expected to fail until the Coder delivers it): %r"
            % (IMPORT_ERROR,)
        )


# ---------------------------------------------------------------------------
# Shared fixture builders
# ---------------------------------------------------------------------------

def _make_record(lens, round_, gap_type, broken_assumption, why_it_fails,
                  proposed_fix, touches, mechanism_refs):
    """Build a gap_record dict matching roles/verifier.md's plan-check format
    plus the two new required fields (touches, mechanism_refs) this spec adds.
    Using a plain dict (not the module's constructor) here on purpose for the
    AC1 interface-shape test; other tests use rgr.GapRecord once import
    succeeds, to also exercise the module's own constructor.
    """
    return {
        "lens": lens,
        "round": round_,
        "gap_type": gap_type,
        "broken_assumption": broken_assumption,
        "why_it_fails": why_it_fails,
        "proposed_fix": proposed_fix,
        "touches": touches,
        "mechanism_refs": mechanism_refs,
    }


def _gap28_ac28_record():
    """The real AC28 side of the gap-28 contradiction (iteration 16 -> gap 28,
    tracing back to AC28's original rule from earlier in the log): "non-empty
    open-task set must always override preserved PENDING_VACANCY"."""
    return _make_record(
        lens="precision-of-instruction",
        round_=12,
        gap_type="DESIGN",
        broken_assumption=(
            "AC28: a non-empty open-task set must always override a "
            "preserved PENDING_VACANCY alertState."
        ),
        why_it_fails=(
            "As worded, AC28 is unconditional on any non-empty open-task "
            "set, with no branch for the dual-open-then-partial-dismiss "
            "case that AC42 covers."
        ),
        proposed_fix=(
            "Recompute must override PENDING_VACANCY whenever the open-task "
            "set is non-empty, with no exception."
        ),
        touches=["AC28"],
        mechanism_refs=["AlertState recompute"],
    )


def _gap28_ac42_record():
    """The real AC42 side of the gap-28 contradiction (iteration 15 -> gap 25):
    "must NOT override in the dual-open-then-partial-dismiss case"."""
    return _make_record(
        lens="precision-of-instruction",
        round_=15,
        gap_type="DESIGN",
        broken_assumption=(
            "AC42: recompute must NOT override a preserved PENDING_VACANCY "
            "in the dual-open-then-partial-dismiss case, even though the "
            "open-task set is still non-empty afterward."
        ),
        why_it_fails=(
            "AC42's dual-open-then-partial-dismiss case has a non-empty "
            "remaining open-task set (AC27's reachable state) yet must "
            "still preserve PENDING_VACANCY, contradicting an unconditional "
            "non-empty-set-overrides rule."
        ),
        proposed_fix=(
            "Recompute must preserve PENDING_VACANCY when only a partial "
            "dismiss has occurred, regardless of remaining non-empty "
            "open-task set."
        ),
        touches=["AC42", "AC43", "AC27"],
        mechanism_refs=["AlertState recompute"],
    )


def _iteration14_three_independent_records():
    """The real iteration-14 result: 3 of 4 lenses failed with disjoint gaps
    (regression-audit / concurrency-isolation / state-completeness), verbatim
    per plan_check_log.md quoted in the module docstring above."""
    regression_audit = _make_record(
        lens="regression-audit",
        round_=14,
        gap_type="DESIGN",
        broken_assumption=(
            "dismissAlert's rewrite silently dropped the atomic "
            "concurrent-dismiss guard (Room.updateMany with "
            "alertState:{not:'NONE'}) and the explicit cross-org ownership "
            "check backing AC12."
        ),
        why_it_fails=(
            "Moving the read inside the transaction never restated either "
            "guard, so both are silently lost."
        ),
        proposed_fix=(
            "Use an atomic conditional Task update (updateMany + count "
            "check) and explicitly retain the ownership check."
        ),
        touches=["AC12", "AC35", "AC36"],
        mechanism_refs=["dismissAlert concurrent-dismiss guard"],
    )
    concurrency_isolation = _make_record(
        lens="concurrency-isolation",
        round_=14,
        gap_type="DESIGN",
        broken_assumption=(
            "The shared recompute step (3a/3b/dismissAlert/completeTask) "
            "has a write-skew race under Postgres ReadCommitted."
        ),
        why_it_fails=(
            "Two concurrent transactions closing DIFFERENT tasks on the "
            "SAME room can each read a stale open-task snapshot and the "
            "later write silently stomps the earlier one."
        ),
        proposed_fix=(
            "Add a row lock (SELECT...FOR UPDATE) as the recompute step's "
            "first statement."
        ),
        touches=["AC34"],
        mechanism_refs=["recompute row-lock ordering"],
    )
    state_completeness = _make_record(
        lens="state-completeness",
        round_=14,
        gap_type="DESIGN",
        broken_assumption=(
            "alertState=PENDING_VACANCY with an open COLLECTIONS/DISPUTE "
            "Task underneath (AC27-proven reachable) was an uncovered "
            "matrix cell."
        ),
        why_it_fails=(
            "Both dismissAlert's PENDING_VACANCY fallback and the "
            "badge-adjacent countdown's reverse-map table silently orphan "
            "or mishandle this cell."
        ),
        proposed_fix=(
            "Add a PENDING_VACANCY entry to both dismissAlert's fallback "
            "and the countdown reverse-map table."
        ),
        touches=["AC27", "AC37", "AC38"],
        mechanism_refs=["countdown reverse-map table"],
    )
    return [regression_audit, concurrency_isolation, state_completeness]


def _cluster_with_one_design_record():
    """A cluster where a DESIGN-severity record sits among lower-severity
    (KNOWLEDGE) records and must survive clustering/trimming (AC7)."""
    design_record = _make_record(
        lens="concurrency-isolation",
        round_=20,
        gap_type="DESIGN",
        broken_assumption="Row lock ordering is violated under retry.",
        why_it_fails="A retried transaction can re-acquire locks out of order.",
        proposed_fix="Sort lock acquisition by primary key before FOR UPDATE.",
        touches=["AC50"],
        mechanism_refs=["recompute row-lock ordering"],
    )
    knowledge_record_1 = _make_record(
        lens="regression-audit",
        round_=20,
        gap_type="KNOWLEDGE",
        broken_assumption="Unclear whether retries are bounded here.",
        why_it_fails="Retry cap isn't documented for this call site.",
        proposed_fix="unknown",
        touches=["AC50"],
        mechanism_refs=["recompute row-lock ordering"],
    )
    knowledge_record_2 = _make_record(
        lens="precision-of-instruction",
        round_=20,
        gap_type="KNOWLEDGE",
        broken_assumption="Ambiguous which retry count applies.",
        why_it_fails="Two different retry constants are referenced nearby.",
        proposed_fix="unknown",
        touches=["AC50"],
        mechanism_refs=["recompute row-lock ordering"],
    )
    return [design_record, knowledge_record_1, knowledge_record_2]


class RecordingMechanismTracer:
    """A fake, injectable stand-in for the real sub-agent mechanism-trace
    dispatch. Records every call (args) so tests can assert call count and
    call arguments without any network/Agent access -- this is the
    "mockable/injectable dependency" design the assignment requires for the
    contradiction-trigger / tie-break logic.
    """

    def __init__(self, verdict="CONTRADICTORY", breaking_assumption="stub"):
        self.calls = []
        self._verdict = verdict
        self._breaking_assumption = breaking_assumption

    def __call__(self, record_a, record_b, shared_spec_text=None):
        self.calls.append((record_a, record_b, shared_spec_text))
        if rgr is not None and hasattr(rgr, "TraceResult"):
            return rgr.TraceResult(
                verdict=self._verdict,
                breaking_assumption=self._breaking_assumption,
            )
        return {
            "verdict": self._verdict,
            "breaking_assumption": self._breaking_assumption,
        }


class RecordingTieBreaker:
    """Same recording-fake pattern as RecordingMechanismTracer, for the
    tie-break dispatch used when a pair is found CONTRADICTORY."""

    def __init__(self, verdict="TIEBREAK_RESOLVED"):
        self.calls = []
        self._verdict = verdict

    def __call__(self, record_a, record_b, trace_result=None):
        self.calls.append((record_a, record_b, trace_result))
        return {"verdict": self._verdict}


# ---------------------------------------------------------------------------
# AC1 -- module exists / importable; 3 core functions independently testable
# ---------------------------------------------------------------------------

class TestAC1ModuleShape(unittest.TestCase):
    """[DOC + structural BEHAVIORAL] The module exists, is importable, and
    exposes the orthogonality pre-filter, clustering, and contradiction-
    trigger logic as independently-callable public functions/classes (not
    buried inside one monolithic entry point that can't be unit tested)."""

    def test_module_is_importable(self):
        self.assertIsNone(
            IMPORT_ERROR,
            "harness/reconcile_gap_records.py must exist and import "
            "cleanly; import failed with: %r" % (IMPORT_ERROR,),
        )

    def test_orthogonality_filter_is_independently_callable(self):
        _require_module()
        self.assertTrue(
            hasattr(rgr, "orthogonality_filter"),
            "expected a public `orthogonality_filter` function/callable "
            "usable independently of the full reconcile() pipeline",
        )
        self.assertTrue(callable(rgr.orthogonality_filter))

    def test_clustering_is_independently_callable(self):
        _require_module()
        self.assertTrue(
            hasattr(rgr, "cluster_near_duplicates"),
            "expected a public `cluster_near_duplicates` function/callable "
            "usable independently of the full reconcile() pipeline",
        )
        self.assertTrue(callable(rgr.cluster_near_duplicates))

    def test_contradiction_trigger_is_independently_callable(self):
        _require_module()
        self.assertTrue(
            hasattr(rgr, "needs_mechanism_trace"),
            "expected a public `needs_mechanism_trace` function/callable "
            "that decides, from two gap records alone, whether the "
            "mandatory mechanism-trace dispatch must fire -- usable "
            "independently of the full reconcile() pipeline",
        )
        self.assertTrue(callable(rgr.needs_mechanism_trace))

    def test_three_core_functions_are_distinct_callables(self):
        # Guards against a trivial "all three names point at the same
        # monolithic function" shortcut that would defeat independent
        # testability even though hasattr() checks above pass.
        _require_module()
        fns = {
            rgr.orthogonality_filter,
            rgr.cluster_near_duplicates,
            rgr.needs_mechanism_trace,
        }
        self.assertEqual(
            len(fns), 3,
            "orthogonality_filter, cluster_near_duplicates, and "
            "needs_mechanism_trace must be three distinct callables, not "
            "aliases of one monolithic function",
        )


# ---------------------------------------------------------------------------
# AC2 -- REAL gap-28 shape triggers the mechanism-trace path
# ---------------------------------------------------------------------------

class TestAC2Gap28TriggersMechanismTrace(unittest.TestCase):
    """[BEHAVIORAL] Two records sharing mechanism_refs == ["AlertState
    recompute"] with contradictory proposed_fix text (the REAL AC28 vs AC42
    pair) must trigger the mandatory mechanism-trace path, not a silent
    merge -- per the spec's "mandatory whenever two records share ALL
    mechanism_refs" rule (sketch step (b)(3))."""

    def setUp(self):
        _require_module()
        self.ac28 = _gap28_ac28_record()
        self.ac42 = _gap28_ac42_record()

    def test_needs_mechanism_trace_is_true_for_full_mechanism_overlap(self):
        self.assertTrue(
            rgr.needs_mechanism_trace(self.ac28, self.ac42),
            "two records sharing ALL mechanism_refs (['AlertState "
            "recompute']) must be flagged for a mandatory mechanism-trace, "
            "per the spec's shared-mechanism trigger -- this is the exact "
            "case gap-28 shows was previously missed silently",
        )

    def test_orthogonality_filter_does_not_mark_gap28_pair_independent(self):
        # The orthogonality pre-filter is the FIRST, cheapest check; it must
        # NOT short-circuit this pair to INDEPENDENT, since their
        # mechanism_refs fully overlap (["AlertState recompute"] both sides).
        result = rgr.orthogonality_filter(self.ac28, self.ac42)
        independent_verdict = getattr(rgr, "INDEPENDENT", "INDEPENDENT")
        self.assertNotEqual(
            result, independent_verdict,
            "the gap-28 pair shares mechanism_refs=['AlertState recompute'] "
            "and must not be marked INDEPENDENT by the orthogonality "
            "pre-filter -- doing so would silently skip the mechanism-trace "
            "that this whole feature exists to make mandatory",
        )

    def test_reconcile_dispatches_mechanism_trace_for_gap28_pair(self):
        # Full pipeline: reconcile() must actually invoke the injected
        # mechanism-trace dependency for this pair, proving the trigger is
        # wired end-to-end, not just correct in isolation.
        tracer = RecordingMechanismTracer(
            verdict="CONTRADICTORY",
            breaking_assumption=(
                "AC28's unconditional override contradicts AC42's "
                "preserve-on-partial-dismiss rule"
            ),
        )
        tie_breaker = RecordingTieBreaker()
        rgr.reconcile(
            [self.ac28, self.ac42],
            round=16,
            mechanism_tracer=tracer,
            tie_breaker=tie_breaker,
        )
        self.assertEqual(
            len(tracer.calls), 1,
            "reconcile() must dispatch exactly one mechanism-trace call "
            "for the gap-28 (AC28 vs AC42) pair, not silently merge them",
        )

    def test_contradictory_verdict_does_not_silently_merge(self):
        # If the injected tracer says CONTRADICTORY, the reconciliation
        # result must record the contradiction (not silently fold both
        # records into one merged spec item as if they were compatible).
        tracer = RecordingMechanismTracer(verdict="CONTRADICTORY")
        tie_breaker = RecordingTieBreaker()
        result = rgr.reconcile(
            [self.ac28, self.ac42],
            round=16,
            mechanism_tracer=tracer,
            tie_breaker=tie_breaker,
        )
        contradictions = getattr(result, "contradictions", None)
        if contradictions is None and isinstance(result, dict):
            contradictions = result.get("contradictions")
        self.assertTrue(
            contradictions,
            "reconcile() must surface at least one recorded contradiction "
            "for the gap-28 pair when the mechanism-trace verdict is "
            "CONTRADICTORY -- silently merging would reproduce the exact "
            "incident this feature exists to prevent",
        )

    def test_contradictory_verdict_dispatches_tie_break(self):
        tracer = RecordingMechanismTracer(verdict="CONTRADICTORY")
        tie_breaker = RecordingTieBreaker()
        rgr.reconcile(
            [self.ac28, self.ac42],
            round=16,
            mechanism_tracer=tracer,
            tie_breaker=tie_breaker,
        )
        self.assertEqual(
            len(tie_breaker.calls), 1,
            "a CONTRADICTORY mechanism-trace verdict must dispatch exactly "
            "one bounded tie-break call (sketch step (d)) -- not zero "
            "(silently dropped) and not unbounded retries",
        )


# ---------------------------------------------------------------------------
# AC3 -- REAL iteration-14 shape: 3 independent records, no unnecessary trace
# ---------------------------------------------------------------------------

class TestAC3Iteration14Independence(unittest.TestCase):
    """[BEHAVIORAL] The REAL iteration-14 scenario (3 records, disjoint
    mechanism_refs/touches: regression-audit / concurrency-isolation /
    state-completeness) must be marked INDEPENDENT and merge cleanly, with
    NO unnecessary mechanism-trace dispatches -- asserting the trace-dispatch
    call COUNT (cost-discipline), not just the final merge outcome."""

    def setUp(self):
        _require_module()
        self.records = _iteration14_three_independent_records()

    def test_all_three_pairs_marked_independent_by_orthogonality_filter(self):
        independent_verdict = getattr(rgr, "INDEPENDENT", "INDEPENDENT")
        a, b, c = self.records
        for r1, r2, label in (
            (a, b, "regression-audit vs concurrency-isolation"),
            (a, c, "regression-audit vs state-completeness"),
            (b, c, "concurrency-isolation vs state-completeness"),
        ):
            self.assertEqual(
                rgr.orthogonality_filter(r1, r2), independent_verdict,
                "pair (%s) has disjoint touches AND disjoint mechanism_refs "
                "in the real iteration-14 log and must be marked "
                "INDEPENDENT by the free, deterministic pre-filter" % label,
            )

    def test_none_of_the_three_need_mechanism_trace(self):
        a, b, c = self.records
        for r1, r2 in ((a, b), (a, c), (b, c)):
            self.assertFalse(
                rgr.needs_mechanism_trace(r1, r2),
                "iteration-14's three real gaps have disjoint "
                "mechanism_refs pairwise; none should require a mandatory "
                "mechanism-trace dispatch",
            )

    def test_reconcile_dispatches_zero_mechanism_traces_for_iteration14(self):
        # This is the cost-discipline assertion the spec explicitly calls
        # out: prove the orthogonality pre-filter actually SHORT-CIRCUITS
        # (zero expensive dispatches), not merely that the final merge
        # looks right despite calling the tracer anyway.
        tracer = RecordingMechanismTracer()
        tie_breaker = RecordingTieBreaker()
        rgr.reconcile(
            self.records,
            round=14,
            mechanism_tracer=tracer,
            tie_breaker=tie_breaker,
        )
        self.assertEqual(
            len(tracer.calls), 0,
            "reconcile() must dispatch ZERO mechanism-trace calls for the "
            "real iteration-14 scenario (3 disjoint-mechanism gaps) -- any "
            "call here is an unnecessary, costly dispatch the "
            "orthogonality pre-filter exists to prevent",
        )
        self.assertEqual(
            len(tie_breaker.calls), 0,
            "no tie-break dispatch should ever fire when nothing was "
            "flagged CONTRADICTORY",
        )

    def test_reconcile_merges_all_three_records_with_no_contradictions(self):
        tracer = RecordingMechanismTracer()
        tie_breaker = RecordingTieBreaker()
        result = rgr.reconcile(
            self.records,
            round=14,
            mechanism_tracer=tracer,
            tie_breaker=tie_breaker,
        )
        contradictions = getattr(result, "contradictions", None)
        if contradictions is None and isinstance(result, dict):
            contradictions = result.get("contradictions")
        self.assertFalse(
            contradictions,
            "the real iteration-14 scenario has no contradictions; "
            "reconcile() must not fabricate one",
        )
        merged = getattr(result, "merged_items", None)
        if merged is None and isinstance(result, dict):
            merged = result.get("merged_items")
        self.assertIsNotNone(
            merged,
            "reconcile() must return the merged spec items for the "
            "successful (all-independent) case",
        )
        self.assertEqual(
            len(merged), 3,
            "all 3 distinct, non-duplicate iteration-14 records must "
            "survive the merge as 3 separate items (none are "
            "near-duplicates of each other)",
        )


# ---------------------------------------------------------------------------
# AC7 -- a DESIGN-severity record in a cluster must never be silently dropped
# ---------------------------------------------------------------------------

class TestAC7DesignRecordSurvivesClustering(unittest.TestCase):
    """[BEHAVIORAL] Mirrors ai-code-reviewer's explicit severity-bypass
    design choice ("findings with severity==CRITICAL ... are unconditionally
    kept regardless of cross-review validation scores"), applied to
    loop-team's own gap_type vocabulary: a gap_type=DESIGN record inside a
    cluster with lower-severity (KNOWLEDGE) records must survive
    clustering/trimming, never silently dropped."""

    def setUp(self):
        _require_module()
        self.records = _cluster_with_one_design_record()

    def test_design_record_present_in_clustering_output(self):
        clusters = rgr.cluster_near_duplicates(self.records)
        # Flatten whatever cluster representation the module returns into
        # one list of records so we can assert presence without over-
        # constraining the exact cluster data structure.
        flattened = []
        for cluster in clusters:
            items = cluster if isinstance(cluster, (list, tuple)) else [cluster]
            flattened.extend(items)

        design_survived = any(
            (r.get("gap_type") if isinstance(r, dict) else getattr(r, "gap_type", None))
            == "DESIGN"
            for r in flattened
        )
        self.assertTrue(
            design_survived,
            "the gap_type=DESIGN record must survive cluster_near_duplicates "
            "-- a DESIGN gap must never be silently dropped during "
            "clustering/trimming, mirroring ai-code-reviewer's CRITICAL "
            "severity-bypass design",
        )

    def test_reconcile_merged_output_retains_design_record(self):
        tracer = RecordingMechanismTracer()
        tie_breaker = RecordingTieBreaker()
        result = rgr.reconcile(
            self.records,
            round=20,
            mechanism_tracer=tracer,
            tie_breaker=tie_breaker,
        )
        merged = getattr(result, "merged_items", None)
        if merged is None and isinstance(result, dict):
            merged = result.get("merged_items")
        self.assertIsNotNone(merged)

        def _has_design(items):
            for item in items:
                if isinstance(item, dict):
                    if item.get("gap_type") == "DESIGN":
                        return True
                    nested = item.get("records") or item.get("members")
                    if nested and _has_design(nested):
                        return True
                elif getattr(item, "gap_type", None) == "DESIGN":
                    return True
                elif hasattr(item, "records") and _has_design(item.records):
                    return True
            return False

        self.assertTrue(
            _has_design(merged),
            "the final merged spec-revision items from reconcile() must "
            "still contain the DESIGN-severity record from the cluster -- "
            "it must never be silently trimmed away even though it shares "
            "a cluster with lower-severity KNOWLEDGE records",
        )


class TestEmptyMechanismRefsClusteringRegression(unittest.TestCase):
    """[BEHAVIORAL] Regression for the empty-mechanism_refs clustering bug.

    research/gate10-concurrency-fingerprint-inventory-2026-07-09.md documents
    that `set().isdisjoint(set())` made `cluster_near_duplicates()` skip the
    SequenceMatcher comparison whenever `mechanism_refs` was empty. Empty
    mechanism refs are explicitly allowed for most plan-check gaps, so "no
    mechanism tag" must not mean "cannot be a duplicate."
    """

    def setUp(self):
        _require_module()

    def test_near_duplicate_empty_mechanism_refs_still_cluster(self):
        rec_a = _make_record(
            lens="regression-audit",
            round_=2,
            gap_type="LOGIC",
            broken_assumption="AC7 checks the count after filtering",
            why_it_fails=(
                "The assertion checks the filtered list count after the bug "
                "has already dropped hidden rows."
            ),
            proposed_fix=(
                "Assert the pre-filter source count and then compare the "
                "filtered count separately."
            ),
            touches=["AC7"],
            mechanism_refs=[],
        )
        rec_b = _make_record(
            lens="precision-of-instruction",
            round_=2,
            gap_type="LOGIC",
            broken_assumption="AC7 checks the count after filtering",
            why_it_fails=(
                "The assertion checks the filtered list count after the bug "
                "has already dropped hidden rows."
            ),
            proposed_fix=(
                "Assert the pre-filter source count and then compare the "
                "filtered count separately."
            ),
            touches=["AC7"],
            mechanism_refs=[],
        )

        clusters = rgr.cluster_near_duplicates([rec_a, rec_b])

        self.assertEqual(len(clusters), 1)
        self.assertEqual(
            sorted(r["lens"] for r in clusters[0]),
            ["precision-of-instruction", "regression-audit"],
        )

    def test_empty_mechanism_refs_do_not_force_unrelated_text_to_cluster(self):
        rec_a = _make_record(
            lens="regression-audit",
            round_=2,
            gap_type="LOGIC",
            broken_assumption="AC7 checks the count after filtering",
            why_it_fails="Filtered rows are counted after deletion.",
            proposed_fix="Assert source count before filtering.",
            touches=["AC7"],
            mechanism_refs=[],
        )
        rec_b = _make_record(
            lens="security",
            round_=2,
            gap_type="SECURITY",
            broken_assumption="The OAuth callback accepts any state token",
            why_it_fails="A forged callback can bind a provider account.",
            proposed_fix="Store and compare a nonce-bound OAuth state.",
            touches=["AC21"],
            mechanism_refs=[],
        )

        clusters = rgr.cluster_near_duplicates([rec_a, rec_b])

        self.assertEqual(len(clusters), 2)


if __name__ == "__main__":
    unittest.main()
