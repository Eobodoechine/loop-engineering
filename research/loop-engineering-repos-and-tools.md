# Code & Repos for Loop Engineering / Self-Improving Code

*Companion to the research report. Compiled June 17, 2026. Organized by family, and within each by maturity: **Production-grade** (battle-tested, actively maintained, safe to build on) → **Research / reference** (faithful implementations, great to learn from or prototype with, less hardened).*

A blunt orientation first: maturity is very uneven across the four families.
- **Agentic loops** and **coding agents** → genuinely production-grade open source exists. Build on it.
- **Prompt/program optimization** → one clearly production-grade framework (DSPy), plus solid research libs.
- **Training feedback loops (RLHF)** → mature, scalable libraries exist, but they need real GPUs and ML-eng skill.
- **Open-ended self-improvement (AlphaEvolve / Gödel-style)** → research-grade only. Impressive, reproducible, but not "drop into prod."

---

## 1. Agentic loops (build the loop)

**Production-grade**

- **LangGraph** — [github.com/langchain-ai/langgraph](https://github.com/langchain-ai/langgraph). The most production-oriented choice for *explicit* agent loops: stateful graph with cycles, durable checkpointing (crash recovery + rollback), and human-in-the-loop interrupts. Use when you need control, retries, and inspectability.
- **OpenAI Agents SDK** — [github.com/openai/openai-agents-python](https://github.com/openai/openai-agents-python). Lightweight, well-documented loop + tool-calling + handoffs + guardrails. Model-agnostic despite the name.
- **Claude Agent SDK** — [docs.claude.com](https://docs.claude.com/en/api/agent-sdk/overview) (`@anthropic-ai/claude-agent-sdk` / `claude-agent-sdk` on PyPI). The harness behind Claude's own agents; gives you the tool-use loop, context management, and sub-agents.
- **Microsoft AutoGen** — [github.com/microsoft/autogen](https://github.com/microsoft/autogen). Mature multi-agent conversation framework; strong for orchestrator-worker patterns.
- **CrewAI** — [github.com/crewAIInc/crewAI](https://github.com/crewAIInc/crewAI). Popular role-based multi-agent framework, fast to stand up.
- **Hugging Face smolagents** — [github.com/huggingface/smolagents](https://github.com/huggingface/smolagents). Minimal (~thousand lines), code-writing agents; good if you want to *see* the whole loop.

**Research / reference (learn the patterns)**

- **Reflexion** — [github.com/noahshinn/reflexion](https://github.com/noahshinn/reflexion). The original self-reflection + episodic-memory retry loop.
- **ReAct** — [github.com/ysymyth/ReAct](https://github.com/ysymyth/ReAct). Reference implementation of reason+act interleaving.
- **Tree of Thoughts** — [github.com/princeton-nlp/tree-of-thought-llm](https://github.com/princeton-nlp/tree-of-thought-llm). Official ToT search code.
- **AutoGPT** — [github.com/Significant-Gravitas/AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) and **BabyAGI** — [github.com/yoheinakajima/babyagi](https://github.com/yoheinakajima/babyagi). Historically important; good for understanding the minimal autonomous loop (and its failure modes).

---

## 2. Self-improving / code-evolving systems (the loop rewrites code)

**Research / reference only — no production-grade option exists yet**

- **OpenEvolve** — [github.com/codelion/openevolve](https://github.com/codelion/openevolve) (now also under the `algorithmicsuperintelligence` org). The most complete open re-implementation of **AlphaEvolve**: LLM-ensemble code generation + evaluator pool + program database + evolutionary controller, working at codebase scale. This is the one to start with if you want to *actually run* an AlphaEvolve-style loop on your own problem. You supply the evaluator — that's where the real work is. ([writeup](https://huggingface.co/blog/codelion/openevolve))
- **FunSearch** — [github.com/google-deepmind/funsearch](https://github.com/google-deepmind/funsearch). DeepMind's official release (Apache 2.0). Note: it ships the method skeleton, *not* the LLMs or distributed infra — it's a reference, not a turnkey system.
- **Darwin-Gödel Machine** — [github.com/jennyzzt/dgm](https://github.com/jennyzzt/dgm). Sakana's self-improving coding-agent code. Run it sandboxed (see the objective-hacking incident in the main report).
- **STOP (Self-Taught Optimizer)** — [github.com/microsoft/stop](https://github.com/microsoft/stop). Recursively self-improving scaffolding code; small and readable.
- **Promptbreeder** — no official DeepMind repo; faithful community ports exist (search "promptbreeder" on GitHub). Paper-first.

Practical note: the "engine" in all of these is easy; the **evaluator/verifier is 90% of the work and is domain-specific.** Budget your effort there.

---

## 3. Prompt & program optimization (the loop improves instructions)

**Production-grade**

- **DSPy** — [github.com/stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) (~16k+ stars, very active). The clear leader: write LM pipelines as typed modules, then *compile* them with optimizers (BootstrapFewShot, MIPROv2) that auto-generate prompts and few-shot demos. This is the one most teams actually ship. Strong docs at [dspy.ai](https://dspy.ai).

**Research / strong libraries**

- **GEPA** — [github.com/gepa-ai/gepa](https://github.com/gepa-ai/gepa). Newer reflective prompt-evolution optimizer (integrates with DSPy); notable recent results, worth watching.
- **TextGrad** — [github.com/zou-group/textgrad](https://github.com/zou-group/textgrad). "Autograd via text" — backpropagate natural-language feedback to optimize prompts, code, or any text variable. Published in *Nature* (2025); clean API.
- **OPRO** — [github.com/google-deepmind/opro](https://github.com/google-deepmind/opro). DeepMind's "LLM as optimizer" reference code (the "take a deep breath" result).
- **APE (Automatic Prompt Engineer)** — [github.com/keirp/automatic_prompt_engineer](https://github.com/keirp/automatic_prompt_engineer).

If you only adopt one thing from this whole document for everyday work: **DSPy**. It's the highest-leverage, lowest-risk way to get a self-optimizing loop into a real system.

---

## 4. Training feedback loops (the loop changes weights)

These are real and scalable but require GPUs and ML-engineering competence.

**Production-grade**

- **TRL (HuggingFace)** — [github.com/huggingface/trl](https://github.com/huggingface/trl). The default entry point: SFT, reward modeling, PPO, DPO, GRPO, tightly integrated with the HF ecosystem. Best place to start.
- **verl (ByteDance)** — [github.com/volcengine/verl](https://github.com/volcengine/verl). High-performance, feature-rich RL stack for LLMs; strong for advanced/agentic RL at scale.
- **OpenRLHF** — [github.com/OpenRLHF/OpenRLHF](https://github.com/OpenRLHF/OpenRLHF). Built on Ray + DeepSpeed + vLLM for large-scale (30B–175B) distributed RLHF.
- **Axolotl** — [github.com/axolotl-ai-cloud/axolotl](https://github.com/axolotl-ai-cloud/axolotl). Config-driven fine-tuning (SFT/DPO/etc.); great ergonomics.

**Self-play / RL environments & reference algorithms**

- **OpenSpiel** — [github.com/google-deepmind/open_spiel](https://github.com/google-deepmind/open_spiel). DeepMind's framework for games + self-play RL (the AlphaZero family of methods).
- **CleanRL** — [github.com/vwxyzjn/cleanrl](https://github.com/vwxyzjn/cleanrl). Single-file, readable reference implementations of PPO and friends — best for *understanding* the algorithms.
- **TRL self-rewarding / Constitutional-AI recipes** live inside TRL and the HF cookbook; "self-rewarding LM" and "RLAIF" are training *recipes* on top of these libraries rather than separate repos.

Caveat from the report: synthetic-data self-improvement loops hit **model collapse** without fresh grounding — keep a verifier or real data in the loop.

---

## 5. Self-healing software & coding agents (the loop fixes/optimizes code)

This is, alongside agent frameworks, the most production-ready family.

**Production-grade coding agents**

- **OpenHands** (formerly OpenDevin) — [github.com/All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands). The leading open-source autonomous software-engineering agent; among the top open agents on SWE-bench. Closest open analogue to Devin.
- **SWE-agent** — [github.com/SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent) and **mini-swe-agent** — [github.com/SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent). Princeton's agent-computer-interface agent; the ~100-line mini version scores >74% on SWE-bench Verified and is an excellent, hackable base.
- **Aider** — [github.com/Aider-AI/aider](https://github.com/Aider-AI/aider). Mature AI pair-programmer in the terminal; reliable for real edits with git integration.
- **AutoCodeRover** — [github.com/nus-apr/auto-code-rover](https://github.com/nus-apr/auto-code-rover). Structure-aware repair with fault localization (acquired by Sonar; still open).

**Benchmarks / harnesses (verify your system)**

- **SWE-bench** — [github.com/SWE-bench/SWE-bench](https://github.com/SWE-bench/SWE-bench). The standard evaluation harness; use **Verified**, and read the contamination caveats in the main report.

**Superoptimization / learned compiler opt (research)**

- **STOKE** — [github.com/StanfordPL/stoke](https://github.com/StanfordPL/stoke). Stochastic x86-64 superoptimizer.
- **MLGO** — [github.com/google/ml-compiler-opt](https://github.com/google/ml-compiler-opt). ML for LLVM compiler optimization (in production LLVM).
- **AlphaDev** — released within DeepMind's [github.com/google-deepmind/alphadev](https://github.com/google-deepmind/alphadev); the discovered sort routines are already merged into LLVM libc++.

---

## How to actually build one — a pragmatic recipe

The report's core lesson applies directly to tooling choice: **the loop engine is the easy part; the verifier is the product.** A sensible build path:

1. **Pick the loop type by what you can verify cheaply.** Have unit tests? Build a coding-agent loop (OpenHands / SWE-agent base). Have a scoreable metric on a program? Use OpenEvolve. Have a task with examples and a metric? Use DSPy. Have human/AI preferences and GPUs? Use TRL.
2. **Invest in the verifier.** Make it fast, hard to game, and held-out. This is where overfitting/reward-hacking is won or lost.
3. **Sandbox and log everything.** Especially for code-rewriting loops — provenance + execution isolation + change limits (the DGM overseer-disabling incident is the cautionary tale).
4. **Start with DSPy or an agent SDK before anything exotic.** Most "self-improving" value in real products comes from automated prompt/pipeline optimization plus a well-instrumented agent loop — not from open-ended self-rewriting code.

---

## Sources

- [OpenEvolve](https://github.com/codelion/openevolve) · [OpenEvolve writeup](https://huggingface.co/blog/codelion/openevolve) · [FunSearch](https://github.com/google-deepmind/funsearch) · [Darwin-Gödel Machine](https://github.com/jennyzzt/dgm) · [STOP](https://github.com/microsoft/stop)
- [LangGraph](https://github.com/langchain-ai/langgraph) · [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) · [AutoGen](https://github.com/microsoft/autogen) · [CrewAI](https://github.com/crewAIInc/crewAI) · [smolagents](https://github.com/huggingface/smolagents) · [Reflexion](https://github.com/noahshinn/reflexion)
- [DSPy](https://github.com/stanfordnlp/dspy) · [GEPA](https://github.com/gepa-ai/gepa) · [TextGrad](https://github.com/zou-group/textgrad) · [OPRO](https://github.com/google-deepmind/opro)
- [TRL](https://github.com/huggingface/trl) · [verl](https://github.com/volcengine/verl) · [OpenRLHF](https://github.com/OpenRLHF/OpenRLHF) · [OpenSpiel](https://github.com/google-deepmind/open_spiel) · [CleanRL](https://github.com/vwxyzjn/cleanrl)
- [OpenHands](https://github.com/All-Hands-AI/OpenHands) · [SWE-agent](https://github.com/SWE-agent/SWE-agent) · [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) · [Aider](https://github.com/Aider-AI/aider) · [AutoCodeRover](https://github.com/nus-apr/auto-code-rover) · [SWE-bench](https://github.com/SWE-bench/SWE-bench) · [STOKE](https://github.com/StanfordPL/stoke) · [MLGO](https://github.com/google/ml-compiler-opt)

*Star counts and maintenance status change quickly; verify a repo is still active before committing to it. "Production-grade" here means actively maintained and used in real systems as of mid-2026 — not a guarantee for your specific use case.*
