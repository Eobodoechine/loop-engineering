# Spec — Free (subscription) sub-agent judge adapter for `run_evals`

*Status: SPEC (not built). Decided 2026-06-23. Extends — does not replace — the
"Judge adapter contract" in `README.md`.*

## Problem

`run_evals.py` has ~41 `requires: "judge"` cases that need a real LLM verdict to
score. Two ways to supply one:

- **Metered** — `judge = role_runner.make_role_judge(anthropic_llm(), verifier_md)`
  fits the existing `--judge MODULE` contract in ~10 lines, but every call spends
  pay-per-token credit (the thing that ran us dry this session).
- **Subscription** — judging via the Agent tool runs on the user's Max plan ($0;
  proven this session: the deep-dive + batch-3/4 judge runs all completed free
  while the metered key was out of credits). But a sub-agent is spawned by the
  **orchestrator**, not callable from a Python `judge(case)` — so it *cannot* be a
  loadable module.

## Key idea — decouple judging from scoring via a recorded-verdicts file

The orchestrator does the (free) judging out-of-band and writes the verdicts to a
file; a tiny file-backed module reads that file and exposes `judge(case)`. That
module **does** satisfy the existing `--judge MODULE` contract. So the free path
reuses all the scoring/PACE/arith-guard machinery unchanged — no new scoring code.

```
[orchestrator]                         [run_evals.py, Python]
 1. export blind cases  ──►  /tmp/judge_cases_blind.json  (id + artifact only)
 2. spawn judging sub-agent(s) on the SUBSCRIPTION (bare verifier.md)
 3. write verdicts      ──►  /tmp/verdicts.json  [{id, verdict, raw}]
                                        4. REPLAY_VERDICTS_PATH=/tmp/verdicts.json \
                                              run_evals --judge replay_judge.py --arith-guard
                                           replay_judge reads $REPLAY_VERDICTS_PATH;
                                           judge(case) = recorded verdict[id]
                                           (wrapped by the deterministic arithmetic layer)
                                        5. scorecard / PACE, exactly as today
```

## Pieces to build (each small)

1. **`export_blind(cases) -> [{id, artifact}]`** — strip every gold-side field
   (`expected`, `rubric`, `objective_fact`, `failure_mode`, ...) from the
   `requires:judge`/`target:verifier` cases. (We already do this ad-hoc; make it a
   helper so leakage can't slip in.)
2. **The sub-agent prompt template** — bare `verifier.md` + the blind artifacts +
   "judge each INDEPENDENTLY; output JSON `[{id, verdict, reason}]`; add no rule
   not in verifier.md." (See the confound rule below — this is load-bearing.)
3. **`replay_judge.py`** — a generic file-backed adapter exposing `judge(case)`
   returning the recorded verdict for `case["id"]`. It reads the verdicts-file path
   from the **`REPLAY_VERDICTS_PATH` env var** (set by the orchestrator before the
   run), NOT a CLI flag — `run_evals --judge MODULE` imports the module and calls
   `mod.judge(case)`, passing nothing, so a flag cannot reach it (caught in spec
   review; `load_judge` forwards no args). It MUST raise on a missing/empty verdicts
   file AND on a missing/unknown id (never silently default a verdict — a gap in the
   recorded set is an error, not a PASS). Optional `model` field (+ a `REPLAY_MODEL`
   env) so a multi-model panel can be replayed by column.
4. **Compose with the two-layer verifier** — `replay_judge` is wrapped by the
   existing `arith_guard` (a provably-wrong stated number → FALSE-PASS without even
   consulting the recorded LLM verdict). Free judging + deterministic arithmetic.

## Honesty / independence constraints (hard-won lessons — non-negotiable)

- **Bare `verifier.md` only.** Do NOT inject "do the arithmetic" / "don't demand
  live proof" hints into the judging prompt — those are the *fixes*; baking them in
  confounds the measurement (we made exactly this mistake on batch-4: a confounded
  20/20). The sub-agent applies the role as written and nothing more.
- **Blind artifacts.** The judge sees only `artifact` — never `expected` /
  `objective_fact` / `rubric` (gold stays orchestrator-side; verified by
  `verify_build`'s leakage lint on the cases, and `export_blind` enforces it).
- **Judge each independently.** One batched sub-agent is cheaper but can let later
  verdicts lean on earlier ones / "notice it's a test set"; instruct strict
  per-item independence. (Open question below.)
- **Record the reasoning (`raw`), not just the label** — the project's
  reasoning-capture rule; lets a disagreement be read, not guessed.

## Validation gate (research-grounded — verdicts don't count until this passes)

Per `README.md` and RECON-4 (MVVP, arXiv 2606.19544): validate the judge with
`judge_validate.py` / `meta_validate.py` **before** trusting its verdicts —
chance-corrected κ ≥ 0.60, position-swap flip ≤ 0.10, test-retest > 0.95, against
the suite's `expected` gold (and report Gwet AC1 alongside κ for the imbalanced
suite). Feasibility notes specific to recorded sub-agent verdicts:

- **test-retest > 0.95** needs the sub-agent run **twice** (independent spawns) and
  the two verdict files compared — sub-agent output is non-deterministic, so this is
  the check that actually catches the judging noise (it's why we record, not assume).
- **position-swap flip ≤ 0.10** needs a second blind export with the artifact
  internally reordered (the `artifact_swapped` pattern already in the objective
  cases) judged the same way.
- κ is computable directly from one verdicts file vs gold.

A judge that fails MVVP is rejected — its verdicts do not enter the scorecard.

## Falsifiable acceptance (how we know the adapter works)

- `REPLAY_VERDICTS_PATH=V.json run_evals.py --judge replay_judge.py` scores
  end-to-end: deterministic harness cases + the replayed judge cases, one scorecard.
- A planted **unknown id** in the case set (no recorded verdict) makes
  `replay_judge` RAISE (→ `error` bucket), never a silent PASS.
- A **known trap** the verifier should catch is `caught`; a **good** case is `ok`.
- With `--arith-guard`, a stated-wrong-math trap is `caught` even if the recorded
  LLM verdict was PASS (the two-layer test, already proven for synthetic judges).
- `judge_validate` on the recorded verdicts reports κ / flip / retest; below gate →
  the run is reported as "judge not certified," not GREEN-on-uncertified-verdicts.

## Cost & safety

- **$0** judging (subscription sub-agents); no metered calls, so **no preflight
  needed** on this path (preflight guards the metered path only).
- Re-runnable: verdicts.json is the durable artifact; re-scoring is free and
  deterministic. (Mirrors the resumable-runner ethos — judge once, score many.)

## Open question (decide at build time)

**Batched vs per-case sub-agent.** One sub-agent judging all N (cheap, 1 spawn) vs
one sub-agent per case (faithful single-shot, N spawns, still free). Recommendation:
**batched with strict per-item independence instruction**, and let MVVP test-retest
*measure* the contamination — if retest drops below 0.95, fall back to per-case.
Don't assume; measure (the session's recurring lesson).

## Build order

1. `export_blind` + a leakage assertion (no API).
2. `replay_judge.py` + tests (no API: synthetic verdicts file; raise-on-missing-id;
   composes with `arith_guard`).
3. Orchestrator runbook: export → spawn judging sub-agent (bare verifier.md) ×2 →
   write verdicts → `REPLAY_VERDICTS_PATH=… run_evals --judge replay_judge.py --arith-guard`.
4. `judge_validate` the recorded verdicts; only then do the verdicts count.

Steps 1–2 are loop-verified code; step 3 is an orchestration pattern (documented,
run by Oga); step 4 is the existing MVVP gate.
