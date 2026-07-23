# Loop Team — Eval / Regression Suite (the verifier-for-the-verifier)

Phase 1 of the roadmap: turn the project's principle *"a rule only counts if a
check enforces it"* inward. Every hard-won gate-lesson in `fix_plan.md` becomes a
**frozen case** here, so editing a role or the harness instantly shows whether an
old gate regressed — and nothing in the team's own gate surface can change
without the suite proving it still holds.

## What's here

| File | Role |
|---|---|
| `run_evals.py` | Replays `cases/*.json` through the relevant role/harness; prints a scorecard measuring the gate as a **rejector** (caught / missed / false-pass). Zero deps. |
| `cases/*.json` | Frozen cases seeded from `fix_plan.md` holes. Deterministic `target: harness` cases run today; `requires: "judge"` cases await an LLM-judge adapter. |
| `fixtures/` | Tiny projects fed to `verify.py` (zero-test, passing, failing, no-runner). Not collected as tests (see `conftest.py`). |
| `acceptor.py` | **PACE** anytime-valid commit test — accept a candidate only if significantly better, false-accept ≤ α under unlimited peeking. The statistically-honest replacement for "scored higher → keep it." |
| `judge_validate.py` | **MVVP** — validate an LLM judge (chance-corrected κ, position-swap, test-retest) before its verdicts count. |
| `disagreement_harness.py` | Runs a cross-family OpenAI judge alongside the Anthropic verifier over a case pool and emits the cases where they **disagree** as candidate hard cases (flagged for human gold). The non-saturating way to source new discriminating cases. `--selftest` runs with FakeLLM (no keys). |

### Domain coverage

Cases are weighted toward the domains with the worst production history (rental,
job/career/resume). Newer additions extend coverage to previously-uncovered
domains — **calendar** (double-book, timezone), **finance** (reconciliation,
variance sign), **marketing** (CTR miscompute, unsubstantiated benchmark),
**Apollo/prospecting** (domain mismatch, stale count) — plus **execution-grounded
(Lane C)** `recorded_fetch` cases (report-vs-snapshot contradictions), which your
own hard-case finding shows are the kind that *don't* saturate. The saturated
text-judgment band is a known ceiling: the durable next gains come from execution
grounding and cross-family disagreement, not harder text prompts.

## Run it

```bash
python3 loop-team/evals/run_evals.py            # scorecard; exit 0 iff GREEN
python3 loop-team/evals/run_evals.py --json     # machine-readable (for gate/acceptor)
python3 loop-team/evals/acceptor.py --selftest  # PACE false-accept bound ≤ α
python3 loop-team/evals/judge_validate.py --selftest
python3 -m pytest loop-team/evals -q            # the suite's own tests
```

A **green suite is required** to finish a turn that edits `roles/*.md` or
`harness/*.py` — enforced deterministically by `hooks/loop_stop_guard.py`.

## Scorecard semantics

A *trap* case (`expected: FAIL` / `FALSE-PASS`) is a wrong artifact the gate must
reject: rejecting it is **caught**, letting it through is a **missed / false-pass**
(the project's deepest failure mode). A *good* case (`expected: PASS`) wrongly
rejected is a **regression**. The suite is GREEN iff `missed == regression == error == 0`.

## Suite validity ("test the tests")

A case is only worth anything if it can tell a good target from a broken one.
`test_run_evals.py::SuiteValidity` disables `verify.py`'s zero-test guard and
asserts `zero-test-green` flips to MISSED — proving the case discriminates. (It
forces the unittest path via `hide_pytest`, because with pytest installed a
0-test run is already caught by exit-code 5; the guard is only load-bearing on
unittest's exit-0 "Ran 0 tests" — the actual H-LOOPTEAM-1 bug.)

## Judge adapter contract (for the `requires: "judge"` cases)

Supply `--judge PATH` where the module exposes:

```python
def judge(case: dict) -> str:   # returns "PASS" | "FAIL" | "FALSE-PASS"
    ...
```

It receives the case (with `artifact`, `rubric`, `target`, `expected`) and returns
a verdict for the relevant role. Validate any such judge with `judge_validate.py`
(κ ≥ 0.6, flip ≤ 0.10, retest > 0.95) against the suite's `expected` gold **before**
trusting it. See `../optimize/README.md` for how the optimizer then improves the
Verifier prompt against this suite, gated by `acceptor.py`.
