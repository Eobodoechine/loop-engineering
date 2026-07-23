#!/usr/bin/env python3
"""Loop Team -- Reconciliation harness for parallel plan-check gap records.

When Oga dispatches N parallel adversarial-lens plan-check Verifiers against
the same spec (proposal #2), each lens returns its own independent gap
record. This script is the deterministic, Oga-run mechanism for merging those
N records into one contradiction-checked spec revision -- NOT a sub-agent
judgment call for its mechanical parts (the orthogonality pre-filter,
near-duplicate clustering, and the mandatory-trace TRIGGER condition are all
pure functions of the record fields). The two genuinely judgment-requiring
sub-steps (tracing two proposed fixes against a shared mechanism; breaking a
tie between two contradictory fixes) are injected as callables
(`mechanism_tracer`, `tie_breaker`) so this module has no Agent/network
dependency of its own and is fully unit-testable.

Spec:   loop-team/runs/2026-07-02_plan-check-reconciliation/specs/spec.md
Design: research/plan-check-reconciliation-prior-art-2026-07-02.md
        ("Reconciliation-step sketch" section + its pseudocode), which
        borrows three explicitly-labeled fragments:
          (i)   `ai-code-reviewer`'s clustering (SequenceMatcher >= 0.85 on
                combined title+description text, gated on overlapping
                mechanism_refs) and its severity-bypass rule (a DESIGN-class
                finding is never silently dropped).
          (ii)  CodeRabbit's fail-closed decision pattern (abort the merge
                for a contradictory pair rather than guess; name the reason).
          (iii) The NLI requirements-conflict paper's own documented blind
                spot (a pure text/entailment screen misses COMPOSITIONAL
                conflicts) -- which is why the mandatory mechanism-trace
                trigger below fires on full `mechanism_refs` overlap alone,
                never relying on a text-similarity screen as the sole gate.

Known v1 scope cut (see spec's "Non-goals"): the cheap NLI/LLM pairwise
screening step (sketch step (b)(2)) is NOT implemented -- there is no cheap
screen here to call. Per the spec's explicit "fail toward more checking, not
less" instruction, any pair that is not proven INDEPENDENT by the
(free, deterministic) orthogonality pre-filter is treated as needing the
mechanism-trace dispatch. This is a strictly larger trigger surface than the
"mandatory only on FULL mechanism_refs overlap" case (it also fires on
PARTIAL touches/mechanism_refs overlap) -- a known, accepted, and more
expensive-than-necessary v1 cost tradeoff, not an oversight. A future
iteration that adds the real cheap screen can narrow this back down to
"NEEDS_TRACE from the screen OR full mechanism_refs overlap" per the
original sketch.

No third-party dependencies (stdlib `difflib.SequenceMatcher` only), mirroring
`verify.py` / `stall_detector.py` conventions in this same directory.
"""
from collections import namedtuple
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# Constants / verdict tokens
# ---------------------------------------------------------------------------

INDEPENDENT = "INDEPENDENT"
NEEDS_TRACE = "NEEDS_TRACE"
COMPATIBLE = "COMPATIBLE"
CONTRADICTORY = "CONTRADICTORY"
INCONCLUSIVE = "INCONCLUSIVE"
NEEDS_HUMAN = "NEEDS_HUMAN"

# Clustering threshold reused verbatim from ai-code-reviewer's
# `_cluster_raw_findings` (a concrete, already-tuned number from a real
# deployed system -- see the research doc's Candidate 3.2).
CLUSTER_SIMILARITY_THRESHOLD = 0.85

# gap_type values that must never be silently dropped during clustering or
# any future trimming/cap step (mirrors ai-code-reviewer's CRITICAL+SECURITY
# severity-bypass, applied to loop-team's own gap_type vocabulary).
NEVER_DROP_GAP_TYPES = frozenset({"DESIGN"})

# Bounded retry discipline for the tie-break dispatch (same cap discipline as
# the existing Researcher stall-escalation rule in orchestrator.md): exactly
# one tie-break attempt per contradictory pair, never unbounded.
MAX_TIE_BREAK_ATTEMPTS = 1


TraceResult = namedtuple("TraceResult", "verdict breaking_assumption")


class GapRecord(dict):
    """A gap record: a plain dict subclass so callers get both attribute-free
    dict access (`record["touches"]`) AND the option of `.get(...)` -- matches
    roles/verifier.md's plan-check gap-record shape plus this spec's two new
    required fields (`touches`, `mechanism_refs`).

    Deliberately a dict subclass (not a dataclass) so it interoperates with
    the plain-dict fixtures the test suite also constructs directly (AC1's
    "plain dict on purpose" interface-shape test) -- both representations
    must work identically everywhere in this module.
    """

    def __init__(self, lens, round, gap_type, broken_assumption, why_it_fails,
                 proposed_fix, touches=None, mechanism_refs=None):
        super().__init__(
            lens=lens,
            round=round,
            gap_type=gap_type,
            broken_assumption=broken_assumption,
            why_it_fails=why_it_fails,
            proposed_fix=proposed_fix,
            touches=list(touches or []),
            mechanism_refs=list(mechanism_refs or []),
        )

    def __getattr__(self, name):
        # Allow GapRecord.gap_type as well as GapRecord["gap_type"] -- some
        # call sites (this module's own helpers) read either shape since
        # plain dicts are also accepted throughout.
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


ReconciliationResult = namedtuple(
    "ReconciliationResult",
    "merged_items contradictions needs_human contradiction_log final_check",
)


# ---------------------------------------------------------------------------
# Field access helpers (accept plain dicts OR GapRecord/attr-style objects)
# ---------------------------------------------------------------------------

def _field(record, name, default=None):
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _touches(record):
    return set(_field(record, "touches", []) or [])


def _mechanism_refs(record):
    return set(_field(record, "mechanism_refs", []) or [])


def _gap_type(record):
    return _field(record, "gap_type")


def _cluster_text(record):
    """Combined title+description text for similarity comparison, matching
    ai-code-reviewer's "combined title+description similarity" input -- this
    module has no separate title field, so `broken_assumption` (the closest
    analogue to a finding's title) is combined with `why_it_fails` and
    `proposed_fix` (the closest analogue to a finding's description)."""
    parts = [
        _field(record, "broken_assumption", "") or "",
        _field(record, "why_it_fails", "") or "",
        _field(record, "proposed_fix", "") or "",
    ]
    return "".join(parts)


def _never_drop(record):
    return _gap_type(record) in NEVER_DROP_GAP_TYPES


# ---------------------------------------------------------------------------
# (1) Orthogonality pre-filter -- free, deterministic, cheapest check first
# ---------------------------------------------------------------------------

def orthogonality_filter(record_a, record_b):
    """Mark a pair INDEPENDENT iff BOTH `touches` and `mechanism_refs` are
    disjoint between the two records (sketch step (b)(1)). This is the
    common case per the real iteration-14 log: 3 distinct lenses found 3
    distinct, non-conflicting gaps.

    Returns the INDEPENDENT token, or None when the pair is NOT provably
    independent (i.e. needs further checking) -- callers should treat any
    non-INDEPENDENT result as "cannot short-circuit this pair."
    """
    touches_disjoint = _touches(record_a).isdisjoint(_touches(record_b))
    mechanisms_disjoint = _mechanism_refs(record_a).isdisjoint(
        _mechanism_refs(record_b)
    )
    if touches_disjoint and mechanisms_disjoint:
        return INDEPENDENT
    return None


# ---------------------------------------------------------------------------
# (2) Mandatory mechanism-trace trigger -- deterministic condition
# ---------------------------------------------------------------------------

def needs_mechanism_trace(record_a, record_b):
    """True whenever the mandatory mechanism-trace dispatch MUST fire.

    Per the sketch (step (b)(3)): mandatory whenever two records share ALL
    `mechanism_refs`, regardless of any cheap-screen result -- this is the
    direct fix for the gap-28 incident, where two conflicting ACs were never
    cross-checked because nothing forced a shared-mechanism trace.

    This build has no cheap NLI/LLM pairwise screen implemented (see the
    spec's Non-goals / this module's docstring): per the explicit "fail
    toward more checking, not less" instruction, ANY pair not already proven
    INDEPENDENT by `orthogonality_filter` also needs the trace -- a strictly
    larger trigger surface than "full mechanism_refs overlap alone," and a
    known, accepted v1 cost tradeoff (not silently narrowed to look cheaper
    than it is).
    """
    mech_a = _mechanism_refs(record_a)
    mech_b = _mechanism_refs(record_b)

    # The mandatory, spec-named trigger: full mechanism_refs overlap (both
    # non-empty and identical as sets).
    if mech_a and mech_a == mech_b:
        return True

    # No cheap screen exists yet -- fail toward more checking: anything the
    # orthogonality pre-filter could NOT clear to INDEPENDENT also needs a
    # trace, per the Non-goals section's explicit v1 tradeoff.
    if orthogonality_filter(record_a, record_b) == INDEPENDENT:
        return False
    return True


# ---------------------------------------------------------------------------
# (3) Near-duplicate clustering -- reuses ai-code-reviewer's tuned threshold
# ---------------------------------------------------------------------------

def cluster_near_duplicates(records, threshold=CLUSTER_SIMILARITY_THRESHOLD):
    """Group records whose structured overlap (when present) and combined
    title+description text similarity >= `threshold` (SequenceMatcher,
    character-level) indicate near-duplication. Missing/empty
    `mechanism_refs` are not treated as proof that two records cannot be
    duplicates; they fall back to the text-similarity check. Every other
    record is its own singleton cluster. Returns a list of clusters, each a
    list of records.

    Never drops a record: every input record appears in exactly one output
    cluster (this is what makes the "never drop a DESIGN record" rule
    upheld structurally rather than by convention -- clustering never
    discards anything, it only groups).
    """
    records = list(records)
    n = len(records)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    texts = [_cluster_text(r) for r in records]
    for i in range(n):
        for j in range(i + 1, n):
            mech_i = _mechanism_refs(records[i])
            mech_j = _mechanism_refs(records[j])
            touches_i = _touches(records[i])
            touches_j = _touches(records[j])
            if (
                mech_i
                and mech_j
                and mech_i.isdisjoint(mech_j)
                and touches_i.isdisjoint(touches_j)
            ):
                continue
            similarity = SequenceMatcher(None, texts[i], texts[j]).ratio()
            if similarity >= threshold:
                union(i, j)

    groups = {}
    for idx, record in enumerate(records):
        root = find(idx)
        groups.setdefault(root, []).append(record)
    return list(groups.values())


def _consolidate(cluster):
    """Consolidate one cluster of (near-)duplicate records into a single
    merged spec-revision item. Keeps every record's data (never trims a
    DESIGN member) -- the "merged item" is itself a dict carrying the full
    membership so downstream never-drop checks can walk `records`."""
    gap_types = [_gap_type(r) for r in cluster]
    # Prefer surfacing as DESIGN if any member is DESIGN (never-drop rule),
    # otherwise use the first member's gap_type.
    consensus_gap_type = "DESIGN" if any(
        gt in NEVER_DROP_GAP_TYPES for gt in gap_types
    ) else gap_types[0]
    return {
        "gap_type": consensus_gap_type,
        "records": list(cluster),
        "lenses": [_field(r, "lens") for r in cluster],
        "touches": sorted(set().union(*(_touches(r) for r in cluster))) if cluster else [],
        "mechanism_refs": sorted(
            set().union(*(_mechanism_refs(r) for r in cluster))
        ) if cluster else [],
    }


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def _all_pairs(items):
    n = len(items)
    for i in range(n):
        for j in range(i + 1, n):
            yield i, j


def reconcile(gap_records, round=None, mechanism_tracer=None, tie_breaker=None,
              shared_spec_text=None):
    """Merge N independently-produced gap records into one
    contradiction-checked ReconciliationResult.

    Pipeline (mirrors the research doc's pseudocode):
      1. Pairwise-mark every pair: INDEPENDENT (free pre-filter) or, when the
         mandatory mechanism-trace trigger fires, dispatch `mechanism_tracer`
         and mark COMPATIBLE / CONTRADICTORY / NEEDS_HUMAN accordingly.
      2. On CONTRADICTORY: dispatch exactly one bounded `tie_breaker` call
         and log the contradiction (fail-closed -- do not auto-pick a fix).
      3. Cluster near-duplicates (text-similarity + overlapping mechanisms).
      4. Build merged_items: a cluster with any CONTRADICTORY pair inside it
         is NOT silently merged as if compatible -- its records still
         surface in `merged_items` (tagged unresolved) so a DESIGN record
         inside it is never dropped, per the never-drop rule; all other
         clusters consolidate normally.

    `mechanism_tracer(record_a, record_b, shared_spec_text=None)` and
    `tie_breaker(record_a, record_b, trace_result=None)` are injected
    callables (see RecordingMechanismTracer/RecordingTieBreaker in the test
    suite) -- this module never dispatches an Agent/sub-process itself.
    """
    records = list(gap_records)
    contradictions = []
    needs_human = []
    contradiction_log = []
    # pair_verdict: (i, j) -> verdict token, for pairs that were traced.
    pair_verdict = {}

    for i, j in _all_pairs(records):
        r1, r2 = records[i], records[j]
        if orthogonality_filter(r1, r2) == INDEPENDENT:
            pair_verdict[(i, j)] = INDEPENDENT
            continue
        if not needs_mechanism_trace(r1, r2):
            pair_verdict[(i, j)] = COMPATIBLE
            continue

        if mechanism_tracer is None:
            # No tracer injected: fail toward caution, not silence -- treat
            # as needing human attention rather than silently merging.
            # needs_human shape 1 (spec section B): {"pair": (r1, r2)} only --
            # does NOT carry a top-level "lenses" key. A downstream consumer
            # must fall back to walking pair[0]["lens"]/pair[1]["lens"].
            pair_verdict[(i, j)] = NEEDS_HUMAN
            needs_human.append({"pair": (r1, r2)})
            continue

        trace = mechanism_tracer(r1, r2, shared_spec_text=shared_spec_text)
        verdict = _field(trace, "verdict")
        breaking_assumption = _field(trace, "breaking_assumption")

        if verdict == CONTRADICTORY:
            pair_verdict[(i, j)] = CONTRADICTORY
            entry = {
                "pair": (r1, r2),
                "lenses": (_field(r1, "lens"), _field(r2, "lens")),
                "proposed_fixes": (
                    _field(r1, "proposed_fix"),
                    _field(r2, "proposed_fix"),
                ),
                "mechanism_refs": sorted(
                    _mechanism_refs(r1) & _mechanism_refs(r2)
                ) or sorted(_mechanism_refs(r1) | _mechanism_refs(r2)),
                "trace_verdict": verdict,
                "breaking_assumption": breaking_assumption,
                "round": round,
            }
            # Bounded tie-break: exactly one dispatch per contradictory pair
            # (MAX_TIE_BREAK_ATTEMPTS), fail-closed (CodeRabbit pattern) --
            # never auto-pick one fix over the other.
            # needs_human shape 2 (spec section B): the full contradiction
            # `entry` dict, appended below by EITHER branch (tie-breaker
            # returned INCONCLUSIVE, or no tie_breaker was injected at all) --
            # both branches produce the identical shape, and this is the
            # ONLY needs_human shape that carries a top-level "lenses" key
            # (set above at ~354: entry["lenses"] = (lens_a, lens_b)).
            if tie_breaker is not None:
                tie_result = tie_breaker(r1, r2, trace_result=trace)
                entry["tie_break_verdict"] = _field(tie_result, "verdict")
                if _field(tie_result, "verdict") == INCONCLUSIVE:
                    needs_human.append(entry)
            else:
                needs_human.append(entry)
            contradictions.append(entry)
            contradiction_log.append(entry)
        elif verdict == COMPATIBLE:
            pair_verdict[(i, j)] = COMPATIBLE
        else:  # INCONCLUSIVE or unrecognized
            # needs_human shape 3 (spec section B): {"pair": (r1, r2),
            # "trace_verdict": verdict, "round": round} -- does NOT carry a
            # top-level "lenses" key; fall back to pair[0]["lens"]/
            # pair[1]["lens"] as with shape 1.
            pair_verdict[(i, j)] = NEEDS_HUMAN
            needs_human.append({
                "pair": (r1, r2),
                "trace_verdict": verdict,
                "round": round,
            })

    clusters = cluster_near_duplicates(records)

    # Map each record's identity to its index for pair-verdict lookups.
    index_of = {id(r): idx for idx, r in enumerate(records)}

    def _cluster_has_contradiction(cluster):
        idxs = [index_of[id(r)] for r in cluster]
        for a, b in _all_pairs(sorted(idxs)):
            key = (min(idxs[a], idxs[b]), max(idxs[a], idxs[b]))
            if pair_verdict.get(key) == CONTRADICTORY:
                return True
        return False

    merged_items = []
    for cluster in clusters:
        if _cluster_has_contradiction(cluster):
            # Fail-closed: do not auto-merge this cluster as if compatible.
            # The records still surface (never silently dropped -- a DESIGN
            # record inside stays visible) but tagged unresolved.
            merged_items.append({
                "gap_type": "DESIGN" if any(
                    _never_drop(r) for r in cluster
                ) else _gap_type(cluster[0]),
                "status": "CONTRADICTION_UNRESOLVED",
                "records": list(cluster),
            })
        else:
            merged_items.append(_consolidate(cluster))

    final_check = None
    return ReconciliationResult(
        merged_items=merged_items,
        contradictions=contradictions,
        needs_human=needs_human,
        contradiction_log=contradiction_log,
        final_check=final_check,
    )


if __name__ == "__main__":
    import argparse
    import json
    import sys

    # `--out <path>` (spec: loop-team/runs/2026-07-09_reconcile-json-persistence
    # /specs/spec.md, section D.1): when given, persists the full
    # ReconciliationResult (all 5 fields) as JSON after reconcile() returns,
    # before the existing stdout summary is printed. Purely additive -- when
    # omitted, this flag's code path is never entered and behavior is
    # byte-identical to before this flag existed.
    parser = argparse.ArgumentParser(
        description="Merge N parallel plan-check gap records (read as a JSON "
        "array on stdin) and print a 3-key summary + exit code.",
    )
    parser.add_argument(
        "--out", default=None, metavar="PATH",
        help="Optional path to also write the full ReconciliationResult (all "
        "5 fields, JSON) to disk. The parent directory must already exist -- "
        "a missing parent directory (or any other write failure) raises "
        "uncaught, matching this framework's fail-loud convention.",
    )
    parser.add_argument(
        "--barrier-state", default=None, metavar="PATH",
        help="Optional JSON file for lens_completion_barrier.py preflight. "
        "When provided, reconciliation proceeds only if the expected lens set "
        "is fully complete; missing/retryable/invalid/partial states print the "
        "barrier result JSON and exit nonzero before --out is written.",
    )
    parser.add_argument(
        "--allow-partial-barrier", action="store_true",
        help="Allow a PARTIAL_COMPLETION barrier state to proceed to "
        "reconciliation. This is an explicit fallback opt-in; by default "
        "PARTIAL_COMPLETION exits nonzero and writes no --out file.",
    )
    args = parser.parse_args()

    if args.barrier_state is not None:
        from lens_completion_barrier import (  # noqa: PLC0415
            evaluate_state_file,
            exit_code_for_result,
        )
        barrier_result = evaluate_state_file(args.barrier_state)
        barrier_exit = exit_code_for_result(
            barrier_result,
            allow_partial=args.allow_partial_barrier,
        )
        if barrier_exit != 0:
            print(json.dumps(barrier_result, sort_keys=True))
            sys.exit(barrier_exit)

    raw = sys.stdin.read() if not sys.stdin.isatty() else "[]"
    try:
        records = json.loads(raw)
    except ValueError:
        print(json.dumps({"error": "invalid JSON input"}))
        sys.exit(2)

    result = reconcile(records)

    if args.out is not None:
        # No custom JSONEncoder needed (spec section B, empirically
        # confirmed): dict subclasses (GapRecord) and 2-tuples (e.g.
        # entry["pair"], entry["lenses"]) serialize natively via json.dumps.
        # No parent-directory auto-creation -- a missing parent directory
        # raises FileNotFoundError uncaught rather than silently failing.
        with open(args.out, "w") as out_file:
            out_file.write(json.dumps(result._asdict(), indent=2))

    print(json.dumps({
        "merged_item_count": len(result.merged_items),
        "contradiction_count": len(result.contradictions),
        "needs_human_count": len(result.needs_human),
    }))
    sys.exit(0 if not result.contradictions else 1)
