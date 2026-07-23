# Master Priority Ranking — everything surfaced this session

*2026-06-23. Every candidate from the radar + the AlphaSignal Jan–Jun mining, ordered by **expected impact to the loop-team's current trajectory** (Phase 1 = eval+optimizer is active; Phase 2 = worker swap is next). This is impact-weighted, not a raw composite sort: an item that directly advances the active phase, is verified/runnable, and is cheap to test ranks above a higher-composite item that serves a far-future phase. Composite scores shown for reference. Adoption discipline unchanged — ranking orders the dive-in queue; the PACE-gated experiment + human review decide adoption.*

## TIER 1 — Act now (directly advances the active Phase 1 optimizer)
1. **SkillOpt** (≈0.69, MIT, runnable) — bounded-edit skill trainer w/ held-out gate + reject buffer; *exact match* to the `optimize/` design and **beats GEPA+EvoSkill as baselines**. The single highest-leverage adopt.
2. **Karpathy Autoresearch** (≈0.75, ~21k★) — the canonical self-improving outer loop (edit→budget→one metric→commit-on-gain/revert). The reference skeleton for `optimize/`.
3. **GEPA** (current pick, in flight) — the incumbent optimizer; the **SkillOpt-vs-GEPA A/B is the literal Phase-1B experiment**. Already specced.
4. **Meta-Harness** (≈0.67, arXiv 2603.28052) — optimizer that uses *full history via filesystem* (not summaries); a concrete design upgrade to fold into `optimize/`.
5. **SERA** (≈0.59, Ai2, open) — a **soft, LLM-free verifier** (Phase 1) *and* a ~$400 own-able coder (Phase 2). Cheap, dual-use, high leverage.

## TIER 2 — Strengthen the gate (Phase 1 verifier + harder evals — "the verifier is the product")
6. **Verifier-pattern bundle** — mine into `verifier.md`: CUDA-Agent **execution-reward**, Claude-Code-Security **self-prove/disprove**, Leanstral **formal Lean-4**, SERA **soft verifier**.
7. **DeepSWE** (≈0.44) — contamination-free, harder-to-game coding benchmark for Coder swaps.
8. **FrontierCode** — PR-"mergeability" eval (frontier models ~13%); a real "is the diff shippable" signal beyond tests.
9. **DeepEval / Inspect / Promptfoo** — eval substrates (you've built your own; these are optional substrate, not urgent).

## TIER 3 — Phase 2 worker (the next phase)
10. **mini-swe-agent** (IMPLEMENTABLE) — the minimal scaffold; the Phase-2 base.
11. **Live-SWE-agent** (≈0.42 but strategic) — self-evolving wrapper *on top of* mini; a config swap, +effect.
12. **Qwen3.6-27B** (≈0.71, Apache-2.0) — best cheap permissive open worker model; runs on ~18GB.
13. **GLM-5.2** (≈0.50, MIT) — best-verified MIT worker model; **experiment already queued** (`spec_glm52_worker_model.md`).
14. **OpenAI Agents SDK** (≈0.79 composite) — ready-made harness+sandbox; high score but it's a *platform choice*, adopt only if you want to own less of the harness. Reference now, decide at Phase-2 start.
15. **EvoSkill** (≈0.58) — GEPA-style skill discovery for coding (also Phase 4/5).
16. **OpenCode / DeerFlow 2.0** (≈0.50–0.52) — open scaffolds (alt to OpenHands).
17. **Open-model pool** — Kimi K2.7, Qwen3.5-397B (Apache), DeepSeek V4, GLM-4.7-Flash, Poolside Laguna, MiniMax M3/Nex N2 (caveats). Pick by license + independent benchmark at Phase-2 start; don't chase each.

## TIER 4 — Phase 4/5 (future, sandbox-only) + cheap prototypes
18. **Ralph Wiggum plugin** (≈0.50, official Anthropic) — cheapest possible self-loop to *prototype the mechanic today* (cost-to-test 0.15).
19. **TTT-Discover** (≈0.52) — RL at test time; Phase-5 self-improvement engine (GPU-heavy).
20. **MiniMax M2.7** (≈0.52) — open model that *built its own RL harness over 100+ rounds*; Phase-5 precedent.
21. **Hyperagents/DGM-H, OpenClaw-RL1, SICA, DGM** — self-rewrite precedents; read for safety before Phase 5.
22. **Together Aurora** (≈0.52) — self-improving speculative decoding; serving-speed adaptation.

## TIER 5 — Reference / decay-watch (not candidates to build)
23. **Dive-into-Claude-Code** — harness design reference for Oga (read-and-mine, NC license).
24. **Terminal-Bench 2.0/2.1 (Harbor)** — the live yardstick + the authority that catches vendor-only worker-model claims.
25. **Decay alarms**: AutoGen (maintenance), classic SWE-agent (superseded), Promptfoo (now OpenAI-owned), Ragas→VibrantLabs, OpenAI Evals (stagnating).

## The one-paragraph version
The most impactful work right now is **finishing Phase 1's optimizer with the best available design** — that means running the **SkillOpt-vs-GEPA A/B** (1, 3) informed by **Autoresearch + Meta-Harness** (2, 4), and **hardening the verifier** with SERA's soft verifier + the execution/formal patterns (5, 6). Everything in Tier 3 (the worker) is the *next* phase and shouldn't pull focus until the gate is sharp. Tier 4 is deliberately last — the team's own sequencing rule is "measurement and safety before power."
