# Experiment spec — SkillOpt vs GEPA optimizing `verifier.md`

*Queued by the Researcher (2026-06-23, deep run) from the #1 radar candidate (SkillOpt, priority ≈ 0.69, verified). **Status: QUEUED — blocked on the hard-case suite + an `optimize/` proposer adapter.** Both arms optimize the same target (`roles/verifier.md`) against the same eval cases under the same budget; only the proposer differs. This is the literal Phase-1B optimizer A/B the master ranking calls out.*

## Candidates
- **baseline = GEPA proposer** ([gepa-ai/gepa](https://github.com/gepa-ai/gepa), MIT, ICLR'26 Oral) — `gepa.optimize`, seed `{"verifier_prompt": current roles/verifier.md}`, metric = suite score + per-case failure text as Actionable Side Information.
- **variant = SkillOpt proposer** ([microsoft/SkillOpt](https://github.com/microsoft/SkillOpt) · [arXiv 2605.23904](https://arxiv.org/abs/2605.23904) · `pip install skillopt`, MIT, alpha) — rollout → failure/success-minibatch reflection → **bounded add/del/replace edits under a textual-LR (cosine) budget** → **rejected-edit buffer** → held-out gate. Set `slow_update_gate_with_selection: true` to match paper §3.6 (shipped default is looser force-accept).

## Why a clean A/B
Same target file, same metric, same budget — one variable (the proposer). SkillOpt's design is nearly isomorphic to the team's `optimize/` loop; its **bounded edits + reject-buffer** map onto the verifier's hardest constraint (don't regress a frozen lesson) better than GEPA's freer Pareto mutation. SkillOpt's paper claims it **beats GEPA + EvoSkill on all 52 cells** (e.g. GPT-5.5 LiveMath 43.2→66.9) — but that is **self-reported on coding/QA accuracy, not the team's caught-hole/false-pass metric**, so we measure.

## Critical integration rule
SkillOpt's native accept is a **raw "strictly-improves" threshold** — exactly the dev-set p-hacking `optimize/README.md` step 3 forbids. **Route accept through `evals/acceptor.py::pace_accept`, NOT SkillOpt's internal gate.** Use SkillOpt as *proposer only*; keep the team's PACE acceptor as the gate. Map: SkillOpt's `rollout.py` reward callback ≈ `optimize_verifier.score()` (per-case correctness from `run_evals`); its skill `.md` ≈ `roles/verifier.md`; its proposer replaces the body of `optimize_verifier.propose()`.

## Metric
Primary: **suite caught-hole rate − false-pass rate** on a held, paired **test** split, with **−∞ for any frozen good-case regression**. Secondary (report, don't gate): edits accepted, accepted-edit regressions (must be 0), optimizer LM calls/$, final token count.

## Decision
PACE accept (anytime-valid, false-accept ≤ α) on paired per-case correctness — a higher raw rate is NOT acceptance. The optimizing judge must first pass MVVP (`judge_validate.py`: κ≥0.6). Then human diff-review before promotion to `roles/verifier.md` + log to `fix_plan.md`. Never silent-promote.

## Predicted effect / kill criterion
Predicted: SkillOpt ≥ GEPA at equal budget with **0 accepted regressions** and a more compact diff (effect ≈ 0.6, confidence ≈ 0.45 — strong but self-reported, alpha code, metric-transfer untested).
**Kill** if: no PACE-accepted advantage on the hard test split; OR SkillOpt accepts any edit that regresses a frozen good-case (raw gate let through what PACE rejects); OR bounded edits can't express the rewrites the verifier metric needs; OR alpha `skillopt`/`skillopt_sleep` can't be vendored cleanly without heavy deps. (Prefer vendoring the decoupled, zero-dep `skillopt_sleep/` engine over the paper harness.)

## Blockers (must exist first)
1. The **hard-case discrimination suite** (`research/hard-case-discrimination-dossier-2026-06-23.md`) with train/selection/test splits — today's suite is **saturated** (RRD/answer-block A/Bs both PACE-REJECTED at 39/39), so neither optimizer can be measured against it.
2. An **`optimize/` proposer adapter** wrapping each of `gepa.optimize` and SkillOpt's edit loop behind the existing `optimize_verifier.optimize()` interface (reuse `score()`, `verifier_cases()`, `pace_accept`, proposal-file writing).
3. An **MVVP-validated** optimizing judge before any verdict counts.
