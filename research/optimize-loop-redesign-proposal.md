# Proposal — redesign the `optimize/` outer loop (trace-fed, commit-on-gain, PACE-gated)

*Researcher deep-run finding, 2026-06-23. Grounded in primary sources (Karpathy Autoresearch README + `program.md`; Meta-Harness arXiv 2603.28052 §3 + Algorithm 1 + Table 3 ablation) and the team's own code (`optimize_verifier.py`, `acceptor.py`, `stall_detector.py`, `orchestrator.md`). This is a design proposal, not code.*

## The headline finding (a real, cheap fix)

The team's optimizer (`optimize_verifier.py::propose()`) currently reflects on a **280-character truncated rubric slice** (`c.get("rubric","")[:280]`) — i.e. a *summary*. Meta-Harness's ablation (Table 3) tested exactly this and found it is the **weakest** input channel:

| Proposer input | Median acc | Best acc |
|---|---|---|
| Scores only | 34.6 | 41.3 |
| Scores **+ summary** | 34.9 | **38.7** (summary made *best* worse) |
| **Full execution traces** | **50.0** | **56.7** |

Verbatim: *"even its median candidate outperforms the best candidate found under either ablation … summaries do not recover the missing signal, and may even hurt by compressing away diagnostically useful details."* The win comes from the proposer doing **counterfactual diagnosis across raw traces** ("was candidate 3's regression caused by its structural edit or confounded by its prompt change?") — impossible from a scalar or a summary.

**So the single highest-leverage change to `optimize/` is to stop feeding the proposer a summary and start feeding it the raw judge transcripts** — which the team *already captures* via `role_runner.run_role_explained` ("retains the full response") but currently discards.

## Three outer-loop designs, scored against what the team already owns

| Design | Mechanism | Buys | Team already has? |
|---|---|---|---|
| (a) GEPA/MIPRO reflective-summary | reflect on compressed feedback | cheap, simple | this is `propose()` today — the weak link |
| (b) Autoresearch commit-on-gain | edit→run→keep-on-gain/revert→TSV log | git archive = lineage; frozen scorer = anti-hack; autonomy | git + `fix_plan.md` (the TSV equivalent); "tests are sacred" = frozen scorer |
| (c) Meta-Harness full-history | proposer `grep`/`cat`s all prior source+scores+**traces** | +15 median / 10× eval-efficiency / cross-candidate diagnosis | **missing — the one new piece to build** |

The team is unusually well-positioned: it owns the three hardest pieces and is missing only the cheap one.
- **PACE acceptor** (`acceptor.py`) is *strictly better* than both (b)'s raw "lower→keep" and (c)'s implicit Pareto-keep — it's the statistically honest accept under unlimited peeking. Autoresearch's worst flaw (greedy raw-score commit = exactly the dev-set p-hacking PACE stops) is already solved here. **Reuse as the gate.**
- **git + `fix_plan.md`** = Autoresearch's `branch + results.tsv` archive. **Reuse.**
- **`stall_detector.py`** = the local-optimum/no-progress interrupt that *neither* external system has. **Reuse.**
- **frozen eval suite** = Autoresearch's read-only `evaluate_bpb`. **Reuse.**
- **Missing:** a per-run **trace filesystem** (Meta-Harness 𝒟). **Build this.**

## Recommended architecture: "commit-on-gain over a trace filesystem, PACE-gated"

Keep the current shape (propose → score → PACE-gate → write proposal → human-review → log) and change **what the proposer reads**:
1. **Run archive 𝒟 (NEW):** `optimize/runs/<NNN>/` per candidate — full prompt + `scores.json` (per-case correctness) + **`traces/<case_id>.txt`** (raw judge transcripts via `run_role_explained`). The data already flows; it's just persisted instead of discarded.
2. **Proposer reads 𝒟, not a summary:** a coding sub-agent gets read access to `optimize/runs/`, `grep`/`cat`s the raw transcripts of missed cases across all prior candidates, does counterfactual diagnosis, proposes a targeted edit. No parent-selection rule (per Meta-Harness §3).
3. **Frozen scorer:** `run_evals.py`/`verify.py` stay un-editable ("tests are sacred").
4. **Accept = PACE, not raw gain:** `pace_accept` on paired per-case correctness — the team's structural advantage over both externals.
5. **Commit-on-accept to 𝒟:** on ACCEPT → numbered proposal → human review → promote + append to `fix_plan.md`. On REJECT, the run dir **stays in 𝒟 as a negative example the next proposer can read** (autoresearch discards; this is the Meta-Harness improvement).
6. **Stall interrupt:** run rejected candidates' failure signatures through `stall_detector.stuck_from_outputs`; on `stuck`, stop climbing and escalate to human (the principled version of autoresearch's discouraged "rewind").
7. **Diversity over greedy top-1:** keep a Pareto/diverse frontier of accepted prompts (per `orchestrator.md`'s existing rule), not a single greedy line.

## Smallest first step (≈1 day, no new deps, A/B-able)

Three changes to the existing `optimize_verifier.py`:
1. **Persist traces** — in `score()`, dump each judge's raw transcript (`run_role_explained`) to `optimize/runs/<NNN>/traces/<case_id>.txt` alongside `scores.json` (~15 lines; data already flows).
2. **Feed traces to `propose()`** — replace the 280-char rubric slice with: *"Here are the raw judge transcripts for the cases this prompt got wrong, plus how prior candidates (`optimize/runs/`) handled them. Diagnose why each verdict was wrong from the actual reasoning, then propose a targeted edit."*
3. **Keep PACE + proposal-file + fix_plan logging untouched.**

This is directly A/B-testable: old truncated-rubric `propose()` vs new trace-reading `propose()`, same cases, both PACE-gated, measure caught-hole − false-pass. If the Meta-Harness ablation transfers, the trace-fed proposer produces ACCEPTed candidates the summary-fed one misses.

> Note: `RUN.md` shows the team already runs a Ralph-style one-unit-per-tick, git-backed loop at the project level — so the *cadence* is solved. The missing ingredient is the **full-history trace filesystem** that makes each tick's proposal a diagnosis instead of a guess.

## Related new research (same vein — verify/track)
This is a hot area: **RHO** (arXiv 2606.05922, MSR — label-free retrospective harness optimization, SWE-Pro 59→78% in one round) and **Self-Harness** (arXiv 2606.09498, Shanghai AI Lab — weakness-mine → propose → regression-gate) are both 2026 papers doing *exactly* this loop. Both on the radar now; RHO is the closest external analog to the team's own design and worth a deeper read before building.
