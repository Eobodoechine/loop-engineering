# Implementation Research — GEPA · DSPy · mini-swe-agent

*Researcher dossier, compiled 2026-06-23. Three parallel research passes run to `roles/researcher.md` discipline: every repo, paper, and docs page was **opened and quoted** before citing; maturity (stars / recency / license / real-vs-artifact) recorded; anything unverifiable is flagged plainly. Purpose: how to actually implement each, with verified repos, papers, and real-world usage — to wire GEPA/DSPy into the `optimize/` seam (Phase 1B) and swap mini-swe-agent in as the Coder (Phase 2).*

---

## Summary triage

| Tool | Repo | Stars | License | Latest | Triage | Wires into |
|---|---|---|---|---|---|---|
| **GEPA** | gepa-ai/gepa | ~4.4k | MIT | v0.1.1 (Mar 2026) | IMPLEMENTABLE_NOW | `optimize/` — Verifier prompt, metric = suite score+feedback |
| **DSPy** | stanfordnlp/dspy | ~35k | MIT | 3.2.1 (May 2026) | IMPLEMENTABLE_NOW | `optimize/` — Verifier as Module, `compile()` against suite metric |
| **mini-swe-agent** | SWE-agent/mini-swe-agent | ~4.9k | MIT | v2.3.0 (May 2026) | IMPLEMENTABLE_NOW | Phase 2 — replaces hand-rolled Coder; Verifier+suite unchanged |

All three: MIT-licensed, on PyPI, actively maintained, with verified real-world usage of the exact pattern the roadmap wants. The two judge-optimization references (Pydantic→GEPA, Dropbox→DSPy) map directly onto the Verifier use case.

---

## 1. GEPA — reflective prompt optimizer

### Verified sources
- **Repo:** https://github.com/gepa-ai/gepa — ~4.4k★, 362 forks, 789 commits. MIT. 42 releases, latest **v0.1.1 (Mar 16, 2026)** — actively maintained. Real implementation (separate artifact repo at `gepa-ai/gepa-artifact`). 70% notebooks / 29% Python.
  - README quote: *"GEPA (Genetic-Pareto) is a framework for optimizing any system with textual parameters against any evaluation metric. Unlike RL or gradient-based methods that collapse execution traces into a single scalar reward, GEPA uses LLMs to read full execution traces — error messages, profiling data, reasoning logs — to diagnose why a candidate failed and propose targeted fixes."*
  - The **"Actionable Side Information (ASI)"** concept is named in the README: *"diagnostic feedback returned by evaluators that serves as the text-optimization analogue of a gradient."* This is the exact seam the team wants.
  - Install: `pip install gepa` (or `pip install "gepa[confidence]"`).
- **Paper:** https://arxiv.org/abs/2507.19457 — v2, **ICLR 2026 (Oral)**. Abstract quote: *"Across six tasks, GEPA outperforms GRPO by 6% on average and by up to 20%, while using up to 35x fewer rollouts. GEPA also outperforms the leading prompt optimizer, MIPROv2, by over 10% (e.g., +12% accuracy on AIME-2025)."*
- **DSPy integration `dspy.GEPA`:** https://dspy.ai/api/optimizers/GEPA/overview/ — verified. The metric returns `float | ScoreWithFeedback`; docs: *"the metric should return {'score': float, 'feedback': str}."* `reflection_lm` is required (a strong model, e.g. `dspy.LM(model='gpt-5', temperature=1.0, max_tokens=32000)`).

### ⚠️ Correction to prior notes
The **"ARC-AGI 32%→89%"** figure (cited in the June refresh) is **only in the repo README / a linked blog**, NOT in the arXiv paper. The paper's headline numbers are GRPO +6/up-to-20pp and MIPROv2 +10pp/+12pp on AIME-2025. Cite ARC-AGI as a repo/blog claim, not a paper result.

### Real-world usage (opened & confirmed)
- **Pydantic AI / Pydantic Evals** — https://pydantic.dev/articles/prompt-optimization-with-gepa (2026-02-02). Closest analog to the team's intended use: a custom `EvalsGEPAAdapter` over an eval harness, **86.88% → 96.88%** on contact extraction. Code: `github.com/pydantic/pydantic-stack-demo/tree/main/pai-gepa-prompt-optimization`. Adapter protocol: *"GEPA provides a `GEPAAdapter` protocol that defines three methods: `evaluate()`, `make_reflective_dataset()`, `propose_new_texts()`."*
- **MLflow** — https://mlflow.org/docs/latest/genai/prompt-registry/optimize-prompts/ — GEPA integrated as `mlflow.genai.optimize_prompts()`. Existence confirmed; exact code surface not deep-quoted (Docusaurus render).
- Repo-listed (not independently opened): Comet Opik (`gepa_optimizer`), Google ADK, OpenAI Cookbook, HuggingFace Cookbook (`dspy_gepa`), plus "50+ production uses" (Shopify, Databricks, Dropbox). Treat as repo-asserted.

### How to implement
**Path A — pure `gepa` (recommended for `optimize/`, no DSPy dep).** Verified `gepa.optimize(...)` README example:
```python
import gepa
trainset, valset, _ = gepa.examples.aime.init_dataset()
seed_prompt = {"system_prompt": "You are a helpful assistant. Answer the question. "
                                "Put your final answer in the format '### <answer>'"}
result = gepa.optimize(
    seed_candidate=seed_prompt,
    trainset=trainset, valset=valset,
    task_lm="openai/gpt-4.1-mini",
    max_metric_calls=150,
    reflection_lm="openai/gpt-5",
)
print("Optimized prompt:", result.best_candidate['system_prompt'])
```
For the Verifier run through the eval-suite, implement a `GEPAAdapter` whose reflective dataset carries the caught-hole / false-pass text as the ASI.

**Path B — DSPy (`dspy.GEPA`), cleanest score+feedback mapping:**
```python
import dspy
from dspy.teleprompt.gepa.gepa import ScoreWithFeedback

def verifier_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    report = eval_suite.run(pred)
    feedback = "\n".join(report.caught_holes + report.false_passes)   # textual ASI
    return ScoreWithFeedback(score=report.score, feedback=feedback)

optimizer = dspy.GEPA(
    metric=verifier_metric,
    max_metric_calls=150,
    reflection_lm=dspy.LM(model="gpt-5", temperature=1.0, max_tokens=32000),
    track_stats=True,
)
optimized = optimizer.compile(student=VerifierProgram(), trainset=train, valset=heldout)
```

### Wires into
`optimize/` seam. `seed_candidate = {"verifier_prompt": <current role prompt>}`; metric = eval-suite caught-hole / false-pass score, with per-case failure text as `feedback` (the ASI — the whole reason to pick GEPA over a scalar optimizer). `trainset` drives reflective mutation; held-out `valset` drives Pareto selection so the Verifier isn't overfit to the cases tuning it.

### Risks
- License MIT — clean. Path A is light; Path B/Pydantic pull more deps.
- **Cost:** reflection requires a strong LM. Pydantic: *"For 50 iterations with 8 test cases, that's 400+ LLM calls."*
- **Overfitting / gaming (central hazard for a Verifier):** Pydantic warns *"GEPA can only optimize what you can measure. If your evaluator has blind spots, the optimized prompt will exploit them."* Mitigate with held-out valset + rotating/expanding suite cases.

---

## 2. DSPy — declarative LM pipelines + optimizers

### Verified sources
- **Repo:** https://github.com/stanfordnlp/dspy — **35.1k★**, 3k forks, 4,562 commits. **MIT** (LICENSE opened: "Copyright (c) 2023 Stanford Future Data Systems"). Latest stable **3.2.1 (May 5, 2026)**, 109 releases; 3.3.0b1 beta in flight. 99.4% Python — real package.
  - README quote: *"DSPy is the framework for programming—rather than prompting—language models… offers algorithms for optimizing their prompts and weights. DSPy stands for Declarative Self-improving Python."*
  - Install: `pip install dspy`. Homepage traction: "6.4M+ monthly downloads", "433+ contributors", in production at Databricks, Shopify, Dropbox.
- **Docs:** https://dspy.ai/ — Signatures (typed I/O), Modules (`dspy.Predict` / `dspy.ChainOfThought` / `dspy.ReAct`), optimizers. Quoted compile example: `tp = dspy.GEPA(metric=semantic_f1, auto="medium"); opt = tp.compile(rag, trainset)` → "Before: 0.41 F1 → After: 0.63 F1".
- **MIPROv2 API:** https://dspy.ai/api/optimizers/MIPROv2/ — verified constructor + `compile(student, *, trainset, valset=None, num_trials=None, minibatch=True, ...)`. Official runnable GSM8K example present.
- **Papers:**
  - DSPy — https://arxiv.org/abs/2310.03714 (ICLR 2024): *"self-bootstrap pipelines that outperform standard few-shot prompting (generally by over 25% and 65%…)."*
  - MIPROv2 — https://arxiv.org/abs/2406.11695 (EMNLP 2024): *"MIPRO outperforms baseline optimizers on five of seven… by as high as 13% accuracy."*

### Real-world usage (opened & confirmed)
- **Dropbox engineering** — https://dropbox.tech/machine-learning/optimizing-dropbox-dash-relevance-judge-with-dspy (2026-03-17). Directly relevant: they optimized an **LLM-as-a-judge** against a fixed metric. *"we reduced NMSE by 45 percent (from 8.83 to 4.86)… Model adaptation time dropped from one to two weeks of manual iteration to one to two days."* (MIPROv2; malformed JSON dropped >97%.) This is the team's Verifier pattern, in production.
- Homepage "in production" (linked, not independently opened): Shopify (~550× cost reduction), AWS Nova migration, JetBlue on Databricks, Replit code-repair.

### How to implement
```python
import dspy
from dspy.teleprompt import MIPROv2

dspy.configure(lm=dspy.LM("openai/gpt-4o-mini"))

class Verify(dspy.Signature):
    """Decide whether a candidate solution satisfies the task requirements."""
    task: str = dspy.InputField()
    candidate: str = dspy.InputField()
    verdict: str = dspy.OutputField(desc="pass or fail")
    reason: str = dspy.OutputField()

verifier = dspy.ChainOfThought(Verify)

def metric(example, pred, trace=None):
    return float(pred.verdict.strip().lower() == example.verdict.strip().lower())

tp = MIPROv2(metric=metric, auto="medium")
optimized_verifier = tp.compile(verifier, trainset=trainset)   # list[dspy.Example]
optimized_verifier.save("verifier.v2.json")
```
Swap `MIPROv2` → `dspy.BootstrapFewShot` (cheapest) or `dspy.GEPA(metric=..., auto="medium")` (reflective; what Dropbox used for cross-model adaptation). Same `.compile(program, trainset)` shape.

### Wires into
`optimize/` seam: `compile()` consumes trainset + metric, emits an optimized program saved as versionable JSON. The Verifier role instruction becomes the Signature docstring + fields; the strategy (direct/CoT/ReAct) is the Module wrapper. Metric = the eval-suite score the team already has.

### Risks
- Heavier deps (pulls LiteLLM + LM stack); **pin the version** (109 releases, 3.3 beta, deprecations like `requires_permission_to_run`).
- LM-call cost on compile (bootstrap demos + instruction proposals + Bayesian-opt trials). Start `auto="light"`, small valset. Homepage cites "$2.18 / 200 examples."
- Optimization is stochastic — treat compiled prompts as artifacts to regression-test, not reproducible builds.

---

## 3. mini-swe-agent — the Coder swap (Phase 2)

### Verified sources
- **Repo:** https://github.com/SWE-agent/mini-swe-agent — **4.9k★**, 660 forks, 984 commits, **Python 100%**, **MIT**. Latest release **v2.3.0 (May 21, 2026)**, 57 releases — current, evolving (v2 with migration guide).
  - README quote: *"Just some 100 lines of python for the agent class… no fancy dependencies!"* and *"Supports all models via litellm, openrouter, portkey, and more."*
  - Install (confirmed): `pip install mini-swe-agent` → CLI entrypoint `mini`; or `uvx mini-swe-agent`.
- **Control loop** (src/minisweagent/agents/default.py, opened): `DefaultAgent.run` loops `self.step()` until an `"exit"` role message; `step()` = `execute_actions(self.query())`; limits in `query()` (`step_limit`, `cost_limit` default **3.0** USD/task). Linear message history.
- **Bash-only design** (src/minisweagent/environments/local.py, opened): each action via `subprocess.run(command, shell=True, cwd=..., timeout=...)`. README: *"every action is completely independent (as opposed to keeping a stateful shell session running)."*
- **Diff capture:** `_check_finished` raises `Submitted` when output begins with sentinel `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`; the swebench prompt has the LM do `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT && cat patch.txt` — so **`submission` is literally a git diff** for the Verifier.
- **Score:** README banner *">74% on SWE-bench verified"* (Gemini 3 Pro); classic SWE-agent README notes the 100-line launch hit *"65% on SWE-bench verified."* Default model `anthropic/claude-sonnet-4-5-20250929`, Docker env, `step_limit: 250`. *(Exact Claude % read off leaderboard not independently confirmed — see flags.)*
- **Classic SWE-agent superseded:** https://github.com/SWE-agent/SWE-agent (19.6k★, last release v1.1.0 May 2025) README: *"Most of our current development effort is on mini-swe-agent, which has superseded SWE-agent… use mini-SWE-agent instead… going forward."* Confirms the "pick mini, not classic" call.

### Real-world usage (opened & confirmed)
- **Anyscale + Ray** — https://www.anyscale.com/blog/massively-parallel-agentic-simulations-with-ray (2025-09-10). The exact Coder→capture-diff→test-gate split: *"we adopted mini-swe-agent because it is extremely simple and hackable and also gives good performance on software engineering problems without extra complexity."* Drives mini in a Ray task, then `git apply`s the patch and runs the real test suite.
- **SkyRL (NovaSky-AI)** embed referenced (`MiniSweAgentGenerator`) — reported in the Anyscale post, PR #222 / skyrl docs **not independently opened**.
- **Cookbook** (https://mini-swe-agent.com/latest/advanced/cookbook/, opened): `ValidatingAgent` recipe blocks forbidden patterns (`rm -rf /`, …) before execution — directly useful for sandboxing the Coder.

### How to implement
```python
from minisweagent.agents.default import DefaultAgent
from minisweagent.models import get_model
from minisweagent.environments.docker import DockerEnvironment   # sandbox; LocalEnvironment() for trusted local

def run_coder(task: str, model_name="anthropic/claude-sonnet-4-5-20250929") -> dict:
    agent = DefaultAgent(
        get_model(input_model_name=model_name),
        DockerEnvironment(),
        cost_limit=3.0, step_limit=250,
    )
    result = agent.run(task)          # -> {"exit_status": ..., "submission": <git diff>}
    return {
        "diff": result.get("submission", ""),
        "exit_status": result.get("exit_status"),
        "messages": agent.messages,   # full trajectory for logging / Verifier
    }
```
CLI / batch alternative (as Anyscale uses): `mini-extra swebench-single -m <model> -i <id> --environment-class docker --output <traj.json> --exit-immediately`, or batch `mini-extra swebench --model <model> --subset verified --split test --workers N -o <dir>` → `preds.json` (`{instance_id → model_patch}`).

### Wires into
Phase 2. mini replaces the hand-rolled **Coder**; Oga drives `DefaultAgent.run()` (or shells `mini-extra`), captures `submission` (diff) + `exit_status` + `messages`. **Verifier + eval suite unchanged** — they consume the diff exactly as before. Anyscale demonstrates this split working.

### Risks
- **Cost:** `cost_limit: 3.0` USD/task, `step_limit: 250`; a full run is hundreds of agents. Cap with `MSWEA_GLOBAL_COST_LIMIT` / `MSWEA_GLOBAL_CALL_LIMIT`.
- **Sandbox required:** `LocalEnvironment` runs `shell=True` with **no isolation** — docs say not recommended without user interaction. For autonomous Oga runs use Docker/podman/apptainer/bubblewrap. SWE-bench Docker images are x86-Linux only; pulls can time out.
- Light deps (pydantic, jinja2, typer, litellm); `full` extra heavier (benchmark mode only).
- **Error introduction:** only bash, full shell power. Mitigate with the cookbook `ValidatingAgent` guard + sandbox. mini does **not** self-verify correctness — the Verifier gate is essential.

---

## Couldn't verify (flagged)
- GEPA "ARC-AGI 32%→89%": repo/blog claim, not in the paper.
- GEPA: MLflow exact API surface; Comet/ADK/cookbook integrations and "50+ production uses" — repo-asserted, not opened.
- DSPy: Shopify/AWS/JetBlue/Replit figures (homepage claims); GEPA paper abstract not opened by the DSPy pass.
- mini: exact Claude SWE-bench-Verified % off the leaderboard; SkyRL PR/docs; PyPI page content; README adopter list (Meta/NVIDIA/IBM…).

## Next steps
1. Hand to Oga → turn each into a PACE-gated `experiments/` spec (one variable each).
2. Phase 1B: wire **GEPA** (Path A) into `optimize/` with the suite as metric+feedback; held-out valset; human-review the diff before promoting to `fix_plan.md`.
3. Phase 2: drop **mini-swe-agent** in as the Coder behind the existing gates; prove no regression on the Phase 1 suite before it goes load-bearing.
