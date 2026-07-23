# Experiment spec — GLM-5.2 as the Phase-2 worker model

*Queued by the Researcher (2026-06-23) from a verified AlphaSignal lead. Status: **QUEUED — blocked on Phase-2 worker integration + a task-success scorer.** This is a worker-MODEL swap, so it cannot run on today's `harness_scorer` (which scores `verify.py` on the eval suite); it needs the Phase-2 task-success scorer described in `experiments/README.md` ("a callable that runs a held set of coding tasks and returns pass/fail per task"). The spec is written now so it's ready the moment that scorer + a worker scaffold (mini-swe-agent / Live-SWE-agent) are wired in.*

## Candidate
- **GLM-5.2** (zai-org / Z.ai) — 753B MoE, MIT, 1M ctx, self-hostable (vLLM/SGLang). [HF card](https://huggingface.co/zai-org/GLM-5.2). Radar: CANDIDATE / TESTABLE, priority ≈ 0.50.
- Why it's a clean fit: Z.ai benchmarks GLM-5.2 *under mini-swe-agent* (DeepSWE footnote on the card), the exact scaffold Phase 2 targets — so the swap is a litellm model-name change, not a new dependency.

## Hypothesis
Swapping the worker's model to GLM-5.2 matches or beats the current Coder model on coding-task resolve rate at acceptable cost — i.e. a cheaper/MIT/self-hostable model can hold quality.

## One variable (per the harness rule)
- **baseline** = chosen Phase-2 worker scaffold (mini-swe-agent or Live-SWE-agent) + current Coder model, default settings.
- **variant** = the **same** scaffold + GLM-5.2 as the model (litellm: hosted `GLM-5.2` first; self-host `openai/zai-org/GLM-5.2` via vLLM later). Nothing else changes.

## Metric (the measured number)
- Primary: **pass@1** on a held, paired set of coding tasks (the Phase-2 task-success scorer; same ordered instances for both arms — PACE requires paired).
- Secondary (report, don't gate): **cost/task** and **wall-time/task**.

## Decision
- `run_experiment.py` → `decide()` → **PACE acceptor** (`evals/acceptor.py`): accept the variant ONLY if PACE returns ACCEPT (anytime-valid, false-accept ≤ α). A higher raw pass@1 is **not** acceptance.
- Then human diff-review before any promotion.

## Predicted effect / kill criterion
- Predicted: GLM-5.2 ≥ baseline pass@1 at ≤ 1.5× cost/task (effect ≈ 0.85, but benches are vendor-reported — confidence ≈ 0.70).
- **Kill** if: no PACE-accepted gain; OR cost/task > 1.5× baseline with no quality gain; OR tokenizer/chat-template (`glm_moe_dsa`) breaks the harness; OR self-host hardware (H100-class) makes it impractical and hosted-only routes data in a way the team won't accept (China-data caveat).

## Caveats carried from verification (don't relaunder)
- TB2.1 = 81.0 and SWE-bench Pro = 62.1 are **vendor-reported**; GLM-5.2 is **not yet on the independent tbench.ai leaderboard** (which lists GLM-5.1 at 58.7). The newsletter "DeepSWE 44% / +17% vs Kimi" is **unverified** (card says 46.2, no Kimi column). This experiment exists precisely because the numbers can't be trusted — measure, don't assume.

## Blockers (must exist before this runs)
1. A Phase-2 worker scaffold wired into the loop (mini-swe-agent or Live-SWE-agent).
2. A task-success scorer over a held coding set (per `experiments/README.md`), returning per-task pass/fail as a paired correctness vector.
3. Access: a GLM-5.2 hosted endpoint (cheap) or self-host (H100-class) for the variant arm.
