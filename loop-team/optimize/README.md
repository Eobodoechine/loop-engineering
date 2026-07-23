# Loop Team — Measured Optimizer (Phase 1, Sub-phase B)

Unlocked by the eval suite (`../evals/`). The suite gives the **metric**; this
gives the **safe, measured improvement** of a role prompt against that metric.
Start with the **Verifier** (`roles/verifier.md`) — highest leverage, the heart
of the gate.

## The loop

1. **Metric = suite score.** Wrap `evals/run_evals.py` as a metric function:
   maximize caught-hole rate, minimize false-pass rate, with a **hard penalty for
   any regression** (a good-case flipped to FAIL). A candidate that regresses any
   frozen lesson scores −∞.
2. **Propose.** Express `roles/verifier.md` as a DSPy module, or run **GEPA**
   (reflective prompt evolution; reads the suite's failure traces to propose
   targeted edits). See `../evals/requirements.txt`.
3. **Accept with PACE, not raw score.** Do **not** promote because the candidate
   scored higher on the reused suite — that's dev-set p-hacking. Score incumbent
   and candidate on the **same** cases, then gate promotion through
   `evals/acceptor.py::pace_accept` (paired betting e-process; false-accept ≤ α
   under unlimited peeking). Build pairs with `acceptor.pairs_from_correctness`.
4. **Validate the judge first.** Any LLM-judge used to score role-level cases must
   pass `evals/judge_validate.py` (MVVP: κ ≥ 0.6, position-flip ≤ 0.10,
   test-retest > 0.95) before its verdicts count.
5. **Human-review the diff, then log.** Promote only after a diff review; append
   the promotion to `fix_plan.md` (versioned, reviewable — never a silent
   self-edit). Full Oga-rewrites-the-team self-improvement is Phase 5, and is
   only safe on top of this.

## Sketch

```python
from evals import run_evals, acceptor

def metric(role_prompt) -> dict:
    report = run_evals.run_suite(judge_spec=make_judge(role_prompt))
    if report["counts"]["regression"]:
        return {"score": float("-inf"), "report": report}   # hard fail on regression
    return {"score": report["caught_hole_rate"] - report["false_pass_rate"],
            "report": report}

# ... GEPA/DSPy proposes candidate prompts ...
inc = score_each_case(incumbent_prompt)     # per-case correctness on shared cases
cand = score_each_case(candidate_prompt)
result = acceptor.pace_accept(acceptor.pairs_from_correctness(inc, cand))
if result.decision == "ACCEPT":
    ...  # human diff-review -> promote -> log to fix_plan.md
```

## Status

Seam only — the deterministic backbone it depends on (suite, acceptor, judge
validator, regression gate) is built and tested. Implementing this step requires
an LLM (judge + GEPA) and the scoped deps; it is **Definition-of-Done criterion #6**
and the next thing to build.
