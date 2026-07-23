# What's Already Out There — Re-examining the "Gaps"

*Deep research, June 17 2026. You pushed me to widen the search before building, and you were right to. The honest headline: **4 of the 5 things I claimed "weren't out there" are, in fact, well-covered by existing, verifiable projects.** Only one is genuinely yours to build, and it's thin glue, not new capability.*

---

## How this was verified (and its limits)

You asked for full-source reads and verified links, so here is exactly what happened. The research environment's network was **allowlisted to GitHub only** (`github.com` + `raw.githubusercontent.com`). That had real consequences:

- **Primary-source-verified [✓]** — for every open-source system below, the **full GitHub README was fetched and read** (not snippets). These carry verified links.
- **Search-only [~]** — arXiv abstract pages and **closed commercial products** (Devin, Cursor, Copilot coding agent, Amp/Sourcegraph, Qodo, Ellipsis) could **not** be fetched (blocked) and are flagged as unverified. I'm not presenting them as confirmed.

Star counts are as captured from GitHub during the research pass (mid-2026) and move over time.

---

## The verdict, gap by gap

I earlier named five things as not-out-there. Here's what the evidence actually shows.

| My claimed "gap" | Reality | Verdict |
|---|---|---|
| 1. Multi-repo / portfolio "team manager" | OpenHands **Agent Canvas** (OSS) + Devin/Codegen/Factory (commercial) largely do this | **Mostly covered** — narrow OSS-maturity gap remains |
| 2. Experiment harness (run variants, keep winner) | DSPy, GEPA, EvoAgentX, AFlow, Trace, TextGrad | **Fully covered** — I was wrong |
| 3. Self-improvement loop (team improves itself) | ADAS, GPTSwarm, MaAS, EvoAgent, Gödel Agent, SEAL, DGM, Voyager, Letta | **Covered in research**, emerging in products |
| 4. Cowork-native glue / scheduling | Nothing external does *your* environment | **Genuinely open** — but it's integration, not invention |
| 5. Pluggable verifier (incl. non-code) | Inspect, DeepEval, OpenAI Evals, Ragas, Braintrust, SWE-bench, Terminal-Bench, Agent-as-a-Judge | **Fully covered** — I was wrong |

So my "thin shell of uncovered gaps" was mostly wrong. Below is the verified evidence for each.

---

## Gap 2 — Experiment harness (run multiple methods, keep the best): SOLVED

This is your "test out different methods at the same time and see what's best" requirement, and it's thoroughly built.

- **DSPy** [✓] — the standard. Programs LM pipelines, then *compiles* them with optimizers (MIPROv2) that search prompts + few-shot demos against your metric. ~35k★, extremely active. https://github.com/stanfordnlp/dspy
- **GEPA** [✓] — reflective evolutionary optimizer over a **Pareto frontier**; optimizes prompts *and* code/agent architectures/configs. README reports e.g. an ARC-AGI agent 32%→89% via architecture discovery, and ~35× fewer rollouts than RL. ~5k★, very active; plugs into DSPy as `dspy.GEPA`. https://github.com/gepa-ai/gepa
- **EvoAgentX** [✓] — the closest to a turnkey "run several optimizers and keep the winner": **bundles TextGrad, MIPRO, AFlow, EvoPrompt** and benchmarks them head-to-head on the same system (their README shows the comparison table). ~3k★. https://github.com/EvoAgentX/EvoAgentX
- **AFlow** [✓] — MCTS search over agentic *workflows* (code), shipped inside **MetaGPT** (~69k★). https://github.com/FoundationAgents/MetaGPT (`examples/aflow`)
- **Trace / OptoPrime** [✓] — Microsoft Research; "AutoDiff for AI systems" — propagates general feedback (rewards, text, compiler errors) to optimize prompts *and* code. ~743★. https://github.com/microsoft/Trace
- **TextGrad** [✓] — "autograd via text"; backprops natural-language critique to optimize any text variable. Published in *Nature* 2025. ~3.6k★. https://github.com/zou-group/textgrad

**Takeaway:** don't build an experiment harness. Use DSPy (+GEPA), or EvoAgentX if you want the multi-optimizer bake-off out of the box.

---

## Gap 5 — Pluggable verifier (incl. non-code objectives): SOLVED

You wanted an objective verifier you could plug in, including a "gamifier." Three classes exist, all verified:

**Execution / test oracles** (non-gameable-by-rhetoric, but code-locked):
- **SWE-bench** harness [✓] — patch → run repo tests → pass/fail. ~5.2k★. https://github.com/SWE-bench/SWE-bench
- **Terminal-Bench** [✓] — agents in real sandboxed terminals; each task ships a test script that verifies success. ~2.4k★. https://github.com/laude-institute/terminal-bench

**Programmable eval frameworks** (the most pluggable as a loop objective):
- **Inspect** (UK AI Security Institute) [✓] — multi-paradigm scorers (test, dataset, model-graded); built for frontier-model evals. ~2.2k★. https://github.com/UKGovernmentBEIS/inspect_ai
- **DeepEval** [✓] — "Pytest for LLMs," 30+ metrics including **agentic** ones (Task Completion, Tool Correctness, Plan Adherence) and deterministic LLM-judge builders (G-Eval, DAG). ~16k★. https://github.com/confident-ai/deepeval
- **OpenAI Evals** [✓] — templated model-graded evals, no code needed. ~19k★. https://github.com/openai/evals
- **Ragas** [✓] (https://github.com/vibrantlabsai/ragas), **Braintrust Autoevals** [✓] (https://github.com/braintrustdata/autoevals), **Langfuse** [✓] self-hostable eval+observability (~29k★, https://github.com/langfuse/langfuse).

**Agentic reward-signal judge:**
- **Agent-as-a-Judge** [✓] — an *agent* evaluates another agent step-by-step, producing reward signals (not just pass/fail). Research-grade, code-gen-proven. ~784★. https://github.com/metauto-ai/agent-as-a-judge

**Takeaway:** don't build a verifier abstraction. For code, wrap SWE-bench/Terminal-Bench-style test execution. For non-code, use DeepEval or Inspect. (My `verify.py` was a 120-line toy version of DeepEval.)

---

## Gap 3 — A system that improves the agent team itself: COVERED (mostly research)

This is the "Oga improves the team" idea. It has a whole research literature with running code.

- **ADAS / Meta Agent Search** [✓] — a meta-agent **writes new agents as code**, accumulating an archive of discoveries; outperforms hand-designed agents. ~1.6k★ (research code, last commit early 2025). https://github.com/ShengranHu/ADAS
- **GPTSwarm** [✓] — represents agent swarms as **optimizable graphs**; optimizes both node prompts and the inter-agent *topology*. ICML 2024 oral (Schmidhuber lab). ~1k★. https://github.com/metauto-ai/GPTSwarm
- **MaAS** [✓] — "agentic supernet": samples a custom multi-agent system per query; reports matching/beating prior systems at 6–45% of the cost. ICML 2025 oral. https://github.com/bingreeky/MaAS
- **AgentSquare** [✓] — searches a modular space (Planning/Reasoning/Tool-use/Memory). https://github.com/tsinghua-fib-lab/AgentSquare
- **Gödel Agent** [✓] — self-referential agent that **monkey-patches its own runtime code** toward a reward. ACL 2025. https://github.com/Arvid-pku/Godel_Agent
- **SEAL (Self-Adapting LLMs)** [✓] — MIT; RL loop where the model generates its own finetuning data ("self-edits") and **updates its own weights**. https://github.com/Continual-Intelligence/SEAL
- **Darwin-Gödel Machine** [✓] — evolutionary archive of agents that rewrite their own code, empirically validated (SWE-bench 20%→50%). https://github.com/jennyzzt/dgm
- **Voyager** [✓] — accumulates an **ever-growing skill library of executable code** (frozen weights); lifelong learning. https://github.com/MineDojo/Voyager

**Takeaway:** the "self-improving team" is real and runnable, but research-grade — exactly the part to treat carefully (and sandbox). If/when you want it, ADAS and GPTSwarm are the reference designs; SEAL is the one that actually touches weights.

---

## Gap 1 — Multi-repo / portfolio team manager: MOSTLY COVERED

- **OpenHands "Agent Canvas"** [✓] — the clearest open-source attempt. Its README describes an **Agent Server** (REST API running multiple agents on a machine), a UI that **connects to multiple Agent Servers**, and an **Automation Server** that runs agents on a **schedule or webhook/Slack/GitHub/Linear events** — e.g. "automatically decomposing GitHub issues into tasks." It can drive its own agent *or* Claude Code / Codex / Gemini. Marked **beta**, self-host-centric. https://github.com/All-Hands-AI/OpenHands
- **Codegen** [✓ SDK] — async SDK to fan out parallel sandboxed agents triggered from Slack/Linear/GitHub. https://github.com/codegen-sh/codegen
- **Factory "Droids"** [✓ README] — multi-surface (CLI/Web/Slack/Linear) enterprise agent fleet + GitHub Action. https://github.com/Factory-AI/factory
- **Devin 2.0 / Cursor / Copilot coding agent** [~ search-only] — all advertise parallel agents across repos, but inside walled platforms; **not primary-source-verified here.**

**The one real remnant:** a *mature, vendor-neutral* cross-repo program manager that ingests a backlog, decomposes it across many repos, schedules/prioritizes a fleet, tracks inter-build dependencies, and reports portfolio status. OpenHands Agent Canvas is the most explicit attempt but is beta. So: a narrow maturity gap, not an empty field.

> Note: **AutoGen is now in maintenance mode** [✓ README] — Microsoft directs new users to the **Microsoft Agent Framework**. Worth knowing before building on it. **ChatDev** (CEO/CTO/Programmer software-company roles), **CrewAI** (role-based crews + Flows), and **CAMEL** (role-playing, "Workforce") all remain active multi-agent team frameworks [✓].

---

## Gap 4 — Cowork-native glue / scheduling: the ONLY genuinely open piece

Nothing external runs as a skill in *your* Cowork environment, on *your* scheduled tasks, with *your* connectors. But this is **integration glue, not new capability** — wiring proven components into your setup. It's real work, and it's legitimately yours; it's just not something you'd expect a repo to provide.

---

## What this means for what we build

I owe you a correction: my "keep my thin shell" framing was mostly wrong, because the shell is largely off-the-shelf too. The honest recommendation is **assemble, don't invent**:

- **Worker (builds code):** OpenHands or SWE-agent. Not hand-rolled.
- **Experiment harness / optimizer:** DSPy + GEPA (or EvoAgentX for the multi-optimizer bake-off). Not hand-rolled.
- **Verifier:** SWE-bench/Terminal-Bench-style execution for code; DeepEval or Inspect for everything else. Not hand-rolled (`verify.py` retires).
- **Team self-improvement (later, sandboxed):** borrow ADAS / GPTSwarm patterns; SEAL if you ever want weight-level.
- **Multi-repo orchestration:** start from OpenHands Agent Canvas rather than building a fleet manager from zero.
- **The only thing you actually write:** the **Cowork integration layer** — Oga as a thin skill that invokes these tools, runs on your schedules, and uses your connectors.

Net: this is an **integration project**, not an invention project. That's a much cheaper, more reliable path than what I scaffolded earlier.

---

## Verification ledger

**Primary-source-verified (full README fetched & read):** DSPy, GEPA, EvoAgentX, MetaGPT/AFlow, Trace, TextGrad, ADAS, GPTSwarm, MaAS, AgentSquare, EvoAgent, Gödel Agent, SEAL, Darwin-Gödel Machine, Voyager, Letta/MemGPT, ChatDev, AutoGen, CrewAI, CAMEL, OpenHands, Codegen, Factory, SWE-agent, Aider, Sweep (defunct notice), Agent-as-a-Judge, Inspect, OpenAI Evals, DeepEval, Ragas, Braintrust Autoevals, Langfuse, LangSmith SDK, SWE-bench, Terminal-Bench.

**Search-only / NOT verified (blocked by the GitHub-only network):** all arXiv abstract pages; and the commercial products **Devin, Cursor, Copilot coding agent, Amp/Sourcegraph, Qodo, Ellipsis** — claims about these should be independently checked before relying on them.

*If you want, I can re-verify the commercial products and the arXiv papers in an environment with open web access, and turn the "assemble" recommendation into a concrete integration plan with specific package choices.*
