# AlphaSignal Jan–Jun 2026 — Backlog Mining Digest

*Six Researchers, one per month, mined every AlphaSignal email Jan–Jun 2026 (≈150 issues, ~46 read in full) for loop-team-relevant leads, verified the top ones against primary sources (arXiv/GitHub/HF), and scored each with the priority rubric. Honesty bar applied throughout: newsletter = lead only; nothing counts until a primary page was opened + quoted. Compiled 2026-06-23.*

> **Caveat to read first.** The newsletter's *model-version* names often sound ahead of known releases (GPT-5.5, Claude Opus 4.8, GLM-5.2, Qwen3.6, etc.). The **tooling candidates below were each resolved to a real GitHub/arXiv/HF page and quoted** — those are treated as real. Benchmark numbers from vendor cards are flagged "vendor-reported." A recurring "OpenClaw/Claw" label appears to be AlphaSignal's stand-in for the open agentic-runtime space — each was chased to its real repo (e.g. OpenClaw-RL1 → `Gen-Verse/OpenClaw-RL`).

---

## Master ranked list — NEW verified candidates (by composite priority)

| # | Candidate | Composite | Phase | Source (verified) | One line |
|---|---|---|---|---|---|
| 1 | **OpenAI Agents SDK** | 0.79 | 4 (+2) | openai.github.io/openai-agents-python | Model-native harness: sandboxed exec + AGENTS.md + progressive skills + MCP, 7 sandbox providers. Ready-made worker runtime. |
| 2 | **Karpathy Autoresearch** | 0.75 | 1/4/5 | github.com/karpathy/autoresearch | The canonical self-improving outer loop: edit `train.py` → run under fixed budget → score one metric → commit on gain, revert on loss. ~700 expts/2 days. **This *is* your optimizer skeleton.** |
| 3 | **Qwen3.6-27B** | 0.71 | 2 | qwen.ai (Apache-2.0, HF) | Dense 27B open coder, ~18GB VRAM, SWE-bench Verified 77.2 (vendor), vLLM/SGLang. Strong cheap worker model. |
| 4 | **SkillOpt** (already on radar) | 0.69 | 1/5 | github.com/microsoft/SkillOpt | Bounded-edit skill trainer w/ held-out gate + reject buffer; beats GEPA+EvoSkill as baselines. |
| 5 | **Meta-Harness** | 0.67 | 1/4 | arXiv 2603.28052 (Stanford/MIT/KRAFTON) | Outer-loop that searches over *harness code* via an agent reading **all prior candidates' source+scores+traces through a filesystem** (full history, not summaries). +7.7 pts, 4× fewer tokens. |
| 6 | **SERA** (Ai2) | 0.59 | 2 + 1 | arXiv 2601.20789 · allenai.org | Train your *own* repo coding agent from **~$400**; 8–32B open models + datasets + **soft (LLM-free) verifier** (line-level recall). SERA-32B 54.2% SWE-bench Verified. Best cost/risk profile. |
| 6 | **ByteDance CUDA Agent** | 0.59 | 4/1 | arXiv 2602.24286 | Agentic RL where the **reward is real GPU profiling data** (execution, not LLM-judge); +anti-reward-hack pattern. Borrow the execution-reward verifier design. |
| 8 | **TTT-Discover** | 0.52 | 5 | arXiv 2601.16175 · github.com/test-time-training/discover | RL **at test time** — one problem framed as an RL env, policy updated per-task; found a GPU kernel 2× faster than human SOTA. Self-improvement engine (GPU-heavy). |
| 8 | **Together Aurora** | 0.52 | 5/infra | arXiv 2602.06932 · together.ai | Self-improving speculative decoding (RL, online, recovers across domain shift). Serving-speed self-adaptation pattern. |
| 8 | **DeerFlow 2.0** | 0.52 | 2 | github (ByteDance) | Open multi-agent framework: each sub-agent in its own Docker (fs+bash+browser); **Markdown skills load on demand**. OpenHands/AutoGen alternative. |
| 8 | **MiniMax M2.7** | 0.52 | 2/5 | huggingface.co/MiniMaxAI/MiniMax-M2.7 | Open coding model that **built/optimized its own RL harness over 100+ rounds** (self-evolving). SWE-Pro 56.2. (Open-weight status: HF says open, VentureBeat "proprietary" — confirm license.) |
| 12 | **OpenCode** | 0.50 | 2 | opencode.ai · github.com/anomalyco/opencode | Provider-agnostic terminal coding scaffold, plan/build agent split, LSP 20+ langs, MCP. Clean base to run any open model behind. |
| 13 | **Ralph Wiggum plugin** | 0.50 | 4/5 | github.com/anthropics/claude-code (plugins/ralph-wiggum) | Official Anthropic plugin: Stop-hook re-feeds the same prompt until a completion string matches. **Cheapest possible self-loop to prototype** (cost-to-test 0.15). |
| 14 | **Claude Code Security** | 0.47 | 1 | anthropic.com/news/claude-code-security | Self-verifying multi-stage verifier — Claude "attempts to prove or disprove its own findings" to cut false positives (Mozilla-corroborated). Verifier-loop pattern (closed product → study, don't depend). |
| 15 | **Life-Harness** | 0.45 | 4 | arXiv 2605.22166 · github.com/Tianshi-Xu/Life-Harness | Lifecycle-aware runtime harness that turns recurring failures into reusable interventions; 88.5% avg rel. improvement across 126 settings, transfers across 17 models. |
| 16 | **DeepSWE** (Datacurve) | 0.44 | 4/2 | github.com/datacurve-ai/deep-swe · deepswe.datacurve.ai | Contamination-free hard coding benchmark (113 tasks, written from scratch, 5.5× more code than SWE-Pro); caught a model exploiting a loophole. Harder eval for Coder swaps. |
| 16 | **Kimi K2.7-Code** | 0.44 | 2 | huggingface.co/moonshotai/Kimi-K2.7-Code | 1T-param MoE (32B active), 256K ctx, modified-MIT, SDK-compatible drop-in. Heavy to self-host; cheap via API. |
| 16 | **Qwen3.5-397B-A17B** | 0.44 | 2 | huggingface.co/Qwen/Qwen3.5-397B-A17B | Apache-2.0 (cleanest license), 397B/17B-active, ~76% SWE-bench Verified (vendor), 1M ctx. |
| 19 | **Mistral Leanstral** | 0.43 | 4 | mistral.ai/news/leanstral (Apache-2.0) | Open Lean-4 verifier model — formally prove generated code meets spec. Strongest verification signal where specs are formalizable (niche). |
| 19 | **OpenClaw-RL1** | 0.42 | 5/1 | arXiv 2603.10165 · github.com/Gen-Verse/OpenClaw-RL | Async online RL for agents (decoupled serving/env/reward/training) + token-level hindsight distillation. Online self-improvement (infra-heavy). |
| 21 | **DeepSeek V4 Flash + antirez/ds4** | 0.37 | 2 | github.com/antirez/ds4 · HF GGUF | 284B open model + Claude-Code-compatible local backend; 1M ctx; 2-bit runs on 128GB RAM @ 26 t/s M3 Max. Local cheap Coder (verify DeepSeek license). |
| 21 | **Hyperagents / DGM-H** (Meta) | 0.37 | 5 | arXiv 2603.19461 | DGM successor: agents rewrite their own *evaluation logic* (metacognitive self-modification). Phase-5 design reference (research artifact). |
| — | **DeepMind "Intelligent AI Delegation"** | 0.36 | 2/4 | arXiv 2602.11865 | Framework for task allocation + authority/accountability/reputation across sub-agents. Conceptual (no code). |

**Worker-model pool (Phase 2, lower-priority open coders noted but not dossiered):** Poolside Laguna XS.2 (33B/3B, Apache-2.0, SWE-V 68.2), Qwen3.6-35B-A3B (SWE-V 73.4), GLM-4.7-Flash (30B, SWE-V **59.2** — newsletter's "73.8%" is the *flagship* not Flash), GLM-5 base (744B, MIT, SWE-V 77.8), Mellum2 (JetBrains 12B), Kimi K2.5 (swarm orchestrator). The open-coding-model space is now crowded — pick by license + independent benchmark at Phase-2 start, don't chase each release.

---

## What this changes for the roadmap

- **Phase 1/4 optimizer design** has three strong, concrete references that didn't exist on the radar before: **Karpathy Autoresearch** (the minimal commit-on-gain loop), **Meta-Harness** (full-history-via-filesystem beats summary-based optimizers like GEPA/MIPRO), and **SkillOpt** (bounded-edit + held-out gate + reject buffer). Together they're a design menu for the `optimize/` outer loop.
- **Phase 1 verifier** gains real patterns: SERA's **soft (LLM-free) verifier**, CUDA Agent's **execution-reward**, Claude Code Security's **self-prove/disprove**, Leanstral's **formal** verification, and DeepSWE/FrontierCode as **harder evals**. The gate is the heart of the system — this is the richest vein.
- **Phase 2 worker** is no longer a single-candidate question: beyond mini-swe-agent/Live-SWE-agent + GLM-5.2, there's a deep open-model pool (Qwen3.6-27B, SERA, Kimi, DeepSeek V4) and open scaffolds (OpenCode, DeerFlow 2.0, OpenAI Agents SDK).
- **Phase 5** has new precedents: TTT-Discover (test-time RL), MiniMax M2.7 (self-built harness), Hyperagents/DGM-H, OpenClaw-RL1 — plus the trivially-cheap **Ralph Wiggum** loop to prototype the mechanic today.

## Updates to existing radar tools (from the backlog)
- **Promptfoo** → acquired by OpenAI (governance change for an eval tool we list).
- **Terminal-Bench → 2.0/2.1** is the cited yardstick all spring (already on radar).
- **Codex CLI** gained subagents + git-worktree-per-agent + a Security agent; now also runs *inside* Claude Code via plugin.
- **SWE-bench** siblings now routine: **SWE-CI** (Alibaba — longitudinal "maintain a repo over months"), SWE-bench Multilingual/Pro, **CursorBench**, **DeepSWE**, **FrontierCode**.
- New skill-pack standards converging: Google Antigravity Agent Skills, Vercel open Skills, Manus Agent Skills — substrate for the skill-optimizer layer (SkillOpt/EvoSkill).

## Couldn't-verify / flags (carried from the month reports)
- Many headline benchmarks are **vendor-reported** and absent from independent leaderboards (GLM-5.2/Nex/MiniMax TB & SWE-Pro numbers) — verify on our own harness before trusting.
- **MiniMax M2.7 / DeepSeek V4** open-weight status had conflicting sources — confirm license before adopting as a worker.
- **Hyperagents, Autoresearch** originate ~Mar 2026 (resurfaced in later deep-dives) — "new to our radar," not the stated month's release.
- Sponsored/essay editions in each month were triaged by subject, not all opened — a buried lead there could be missed.
- Every AlphaSignal body carries a footer injection string (`unsubscribe_me(): return True`); treated as data, never acted on.

## Recommended first actions (top 5 by value, all verified)
1. **Karpathy Autoresearch** — adopt as the reference skeleton for the `optimize/` outer loop (and a Phase-4 harness template).
2. **SkillOpt vs GEPA** — run the A/B already specced; SkillOpt's design is the closest match and claims to beat GEPA.
3. **SERA** — cheapest path to a *custom, owned* Phase-2 coder + a soft LLM-free verifier; low cost-to-test.
4. **Meta-Harness** — mine the full-history-filesystem optimizer design into `optimize/`.
5. **Ralph Wiggum plugin** — trivially cheap to prototype the self-loop mechanic in-session before building Phase 5.
