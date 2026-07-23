# Agent-framework termination prior art — how shipped systems bound deliberation

**Date:** 2026-07-16
**Mode:** D (domain research for a build)
**Consumer:** the stop-governor design for an orchestrator that dispatches review/plan-check sub-agents and can run unbounded.
**Method:** every file below was fetched as **raw source** (`curl` → local file → line-numbered read), not summarized from docs or blogs. Line numbers are pinned to the commit SHAs in *Source provenance*. WebSearch was used only as a lead generator; every lead was opened before citing.

---

## 1. The headline answer (read this first)

The dispatch brief hypothesized: *"Nearly all of these are counters or cost caps, not semantic judgments… does ANY shipped framework implement a value-based / marginal-yield / saturation-based stop? If none do, that is itself the most important finding."*

**The "none do" hypothesis is FALSE, and the true finding is sharper and more useful.**

Two shipped frameworks implement genuine LLM-judged, value-based progress evaluation:
- **Magentic-One** (in *both* AutoGen and its successor Microsoft Agent Framework) — an LLM progress ledger judging `is_request_satisfied` / `is_in_loop` / `is_progress_being_made`.
- **SWE-agent's `ScoreRetryLoop`** — a reviewer model scores a submission against an `accept_score` threshold.

But the structural regularity underneath is the real finding, and it holds across **every single framework surveyed, without exception**:

> ### THE LAW: semantic signals REDIRECT. Only counters and cost caps TERMINATE.
>
> Not one shipped framework lets a model's judgment about its own progress *end the run*. Where a semantic signal exists, it is wired to re-plan, re-prompt, nudge, or select — never to terminate. Termination is invariably gated on a counter, a cost cap, a timeout, or an exact-match repetition check.

Three independent confirmations:

1. **Magentic-One** — `is_progress_being_made == False` does **not** stop anything. It increments `stall_count`, which at threshold calls `_reset_and_replan()`. The run only *ends* on `max_round_count` or `max_reset_count` — both plain counters (`_magentic.py:1107-1121`, `1241-1259`).
2. **SWE-agent** — the value-based `ScoreRetryLoop` exists in shipped code but is used by **zero** shipped configs. The one config that uses a retry loop at all uses `ChooserRetryLoop`, whose `retry()` is *pure* cost + `max_attempts`, and whose model judgment (`get_best()`) runs only at the **end**, to *select* among finished candidates — never to stop (`reviewer.py:524-555`).
3. **CrewAI** — repeated-tool-use detection does not stop; it injects a feedback string *as the tool result*. And `max_iter` does not abort; it forces a final answer (`tool_usage.py:238-249`, `agent_utils.py:303-333`).

The one place a semantic signal *does* terminate is Magentic-One's `is_request_satisfied` → success exit. Note the asymmetry: that is the **success** direction, where a false positive ends a task early and visibly. No framework trusts a model's judgment in the **give-up** direction.

**Why (the mechanism, with evidence — not speculation).** The brief's hypothesis (*"counters are tamper-proof and cheap; semantic stops are gameable by the same model being governed"*) is supported, and the source reveals a **second, independently-attested reason: the semantic signal is noisy.** Both frameworks that shipped a value signal had to build expensive machinery to de-noise it:
- SWE-agent samples the reviewer **5 times** and subtracts a multiple of the standard deviation: `accept = mean(accepts) - penalty`, then `accept -= std * reduce_by_std` — a **variance-penalized / lower-confidence-bound** estimate (`reviewer.py:427-446`, `n_sample: int = 5` at `reviewer.py:166`).
- Magentic-One wraps the verdict in a **leaky-bucket integrator with hysteresis**: `stall_count` increments on no-progress but **decrements toward zero on progress** (`_magentic_one_orchestrator.py:399`, `_magentic.py:1116`).

Both are mitigations for the same root problem: *a model's judgment about its own progress is unreliable and self-interested.* Counters need no such machinery. That is the actual reason the field defaults to them.

---

## 2. The saturation question — answered plainly

**Does any framework stop on SATURATION (no new information)?**

**In code: NO. Not one. Zero instances found across all 14 systems surveyed.** No framework computes novelty, information gain, embedding similarity between successive findings, or redundancy of results.

**In prompts: YES — and this is the most revealing artifact in the dossier.**

`langchain-ai/open_deep_research` → `src/open_deep_research/prompts.py:164-174`, verbatim:

```
<Hard Limits>
**Tool Call Budgets** (Prevent excessive searching):
- **Simple queries**: Use 2-3 search tool calls maximum
- **Complex queries**: Use up to 5 search tool calls maximum
- **Always stop**: After 5 search tool calls if you cannot find the right sources

**Stop Immediately When**:
- You can answer the user's question comprehensively
- You have 3+ relevant examples/sources for the question
- Your last 2 searches returned similar information
</Hard Limits>
```

*"Your last 2 searches returned similar information"* is a textbook saturation criterion. It sits under a heading that calls itself **"Hard Limits"** — and **nothing in the codebase measures it**. No similarity computation exists. The "hard limit" is enforced entirely by the goodwill of the model being governed. The actual code-enforced stop in the same system is a counter (`max_react_tool_calls: int = 10`) plus a self-declared `ResearchComplete` tool call.

This produces the field's real architecture — a **trust gradient**:

| Layer | Enforced by | Mechanisms found there | Gameable by the governed model? |
|---|---|---|---|
| **Code** | the harness (a `while` loop the model cannot reach) | counters, cost caps, timeouts, exact-match repetition | **No** |
| **Prompt** | the governed model's compliance | saturation, "do I have enough to answer", "don't loop" | **Yes** |

**Semantic stopping exists in this field only in the layer the governed model controls.** Every bound that is actually enforced lives in the layer it does not. This is the single most transferable insight for the stop-governor.

Other deep-research systems:
- **GPT-Researcher** — a **fixed-arity tree**: `new_breadth = max(2, breadth // 2)`, `new_depth = depth - 1`, recursing while `depth > 1` (`deep_research.py:324-326`). It performs the same shape of work regardless of what it finds; it *cannot* stop early even if the first search fully answers the question. Zero content-awareness. The purest counter in the survey.
- **OpenAI Deep Research** (hosted) — the only documented control is `max_tool_calls`, described as *"the total number of tool calls… that the model will make before returning a result."* No default is published. Its intrinsic stop criterion is RL-internal and undocumented. **Default: UNVERIFIED** (see *Honesty flags*).

---

## 3. Comparison table

Type legend: **CNT** = counter · **COST** = money/tokens/time · **SELF** = self-declared sentinel emitted by the governed model · **REP** = content-repetition/thrash detection · **SEM** = model-judged value/progress · **AUTH** = per-action human authorization.

| Framework | Mechanism | Type | Default | Failure behavior | Source `file:line` |
|---|---|---|---|---|---|
| **LangGraph** | `recursion_limit` | CNT | **25** | **Throws** `GraphRecursionError`; work lost unless checkpointed | `langchain_core/runnables/config.py:171` (`DEFAULT_RECURSION_LIMIT = 25`); enforced `pregel/_loop.py:607-609`; raised `pregel/main.py:3002-3011` |
| **LangGraph** | conditional edge → `END` | SEM (user-authored) | n/a | graceful | user graph code; framework ships no semantic stop |
| **AutoGen 0.4** `RoundRobinGroupChat` | `termination_condition`, `max_turns` | — | **None / None → UNBOUNDED** | *"the group chat will run indefinitely"* | `_round_robin_group_chat.py:117-119` |
| **AutoGen 0.4** | `MaxMessageTermination` | CNT | **no default** (`max_messages` required) | returns `StopMessage` (graceful) | `conditions/_terminations.py:74`, `:87-91` |
| **AutoGen 0.4** | `TokenUsageTermination` | COST | none (≥1 of 3 required, else `ValueError`) | `StopMessage` | `_terminations.py:250-259` |
| **AutoGen 0.4** | `TimeoutTermination` | COST (wall-clock) | required arg | `StopMessage` | `_terminations.py:358` |
| **AutoGen 0.4** | `TextMentionTermination` | SELF | required arg | `StopMessage` | `_terminations.py:111` |
| **AutoGen 0.4** | `StopMessageTermination`, `SourceMatchTermination`, `TextMessageTermination`, `FunctionCallTermination`, `HandoffTermination` | SELF / protocol | required args | `StopMessage` | `_terminations.py:24, 463, 513, ~560, 313` |
| **AutoGen 0.4** | `ExternalTermination` | AUTH | n/a | `StopMessage` | `_terminations.py:404-422` |
| **AutoGen 0.4** | `FunctionalTermination` | escape hatch | n/a | `StopMessage` | `_terminations.py:158-197` |
| **AutoGen 0.4** | `&` / `|` composition | combinator | n/a | — | `base/_termination.py:79-87` |
| **AutoGen** `MagenticOneGroupChat` | progress ledger + `max_stalls` + `max_turns` | **SEM** + CNT | `max_turns=20`, `max_stalls=3` | stall → **re-plan**; only counters end it | `_magentic_one_group_chat.py:117,119`; orchestrator `:388-406` (leaky bucket `:399`) |
| **AG2 v0.14** | `max_consecutive_auto_reply` | CNT | **100** (class attr fallback) | ends the chat | `conversable_agent.py:174`, fallback `:309` |
| **AG2 v0.14** | `is_termination_msg` | **SELF** | `lambda x: content_str(x.get("content")) == "TERMINATE"` | ends the chat | `conversable_agent.py:275-279` |
| **CrewAI** | `max_iter` | CNT | **25** | **Forced final answer** (one extra LLM call) — work harvested, not lost | `agents/agent_builder/base_agent.py:298-300`; handler `utilities/agent_utils.py:303-333` |
| **CrewAI** | `max_execution_time` | COST | **None** | timeout error | `agent/core.py:203-206` |
| **CrewAI** | `max_rpm` | rate | **None** | throttles (not a stop) | `base_agent.py:287-290` |
| **CrewAI** | `_check_tool_repeated_usage` | **REP** (N=1 exact) | always on | **feedback injection**, not a stop | `tools/tool_usage.py:728-738`, used `:238-249` |
| **OpenAI Agents SDK** | `max_turns` | CNT | **10** | **Throws** `MaxTurnsExceeded` | `run_config.py:33`; check `run.py:1065`; raise `run.py:1073`; `None` disables (`run.py:243`) |
| **Swarm** (superseded) | `max_turns` | CNT | **`float("inf")` → UNBOUNDED** | `while` exits gracefully, returns partial | `swarm/core.py:146,154` |
| **Auto-GPT** (classic) | `continuous_limit` → cycle budget | CNT (**demoted**) | **`math.inf`** unless `-l` set | graceful | `app/main.py:594-600` |
| **Auto-GPT** (classic) | permission manager | **AUTH** | on | denial → feedback, agent re-plans | `agents/agent.py:385-398` |
| **SWE-agent** | `per_instance_cost_limit` | **COST** | **$3.00** | **Throws** `InstanceCostLimitExceededError` | `agent/models.py:73-76`; raise `:665` |
| **SWE-agent** | `total_cost_limit` / `per_instance_call_limit` | COST / CNT | **0.0 / 0** (0 = disabled) | throws | `models.py:77-78`; `:667-670` |
| **SWE-agent** | **step limit** | — | **NONE — no step counter exists** | main loop is `while not step_output.done:` | `agent/agents.py:413` |
| **SWE-agent** | `max_requeries` | CNT (format retries only) | **3** | requery | `agents.py:158,177` |
| **SWE-agent** | `ScoreRetryLoop` (`accept_score`, `max_accepts`) | **SEM** | `max_accepts=1`; others required | **used by 0 shipped configs** | `agent/reviewer.py:200-224`, `:617-645`; scorer `:416-449` |
| **SWE-agent** | `ChooserRetryLoop` (the only shipped retry cfg) | CNT + COST | `cost_limit: 6.0`, `max_attempts: 10`, `min_budget_for_new_attempt: 1.0` | no early stop; model picks best at end | `reviewer.py:524-555`; cfg `config/benchmarks/250212_sweagent_heavy_sbl.yaml:136-139` |
| **OpenHands SDK** | **`StuckDetector`** | **REP** (4 scenarios) | **ON by default**; thresholds 4 / 3 / 3 / 6 | sets terminal status **`STUCK`** (≠ ERROR), graceful | `conversation/stuck_detector.py` (whole file); thresholds `conversation/types.py:150-161`; enforced `impl/local_conversation.py:1796-1804`, break `:1759-1763` |
| **OpenHands SDK** | `max_iteration_per_run` | CNT | **500** | status `ERROR` + event (graceful, no throw) | `local_conversation.py:183`; `:1849-1863` |
| **OpenHands SDK** | `max_budget_per_run` | COST | **None** (disabled) | `MaxBudgetReached` event | `local_conversation.py:201`; `:1846` |
| **MS Agent Framework** (AutoGen successor) | `max_rounds` | CNT | **None → UNBOUNDED** | *"forcing completion"* (graceful) | `_base_group_chat_orchestrator.py:149,165`; `:507-514` |
| **MS Agent Framework** | `termination_condition` | escape hatch | **None** | — | `_base_group_chat_orchestrator.py:59` (`TypeAlias = Callable[[list[Message]], bool | Awaitable[bool]]`), `:150` |
| **MS Agent Framework** `Magentic` | progress ledger | **SEM** | `max_stall_count=3`, `max_reset_count=None`, `max_round_count=None` | stall → **`_reset_and_replan()`**; terminate only on counters | `_magentic.py:473-475`; `:1107-1121`; `:1241-1259` |
| **open_deep_research** | `max_researcher_iterations` / `max_react_tool_calls` | CNT | **6 / 10** | `goto=END` (graceful) | `configuration.py:94-95,107-108`; `deep_researcher.py:247-255` |
| **open_deep_research** | `ResearchComplete` tool / `no_tool_calls` | **SELF** | n/a | `goto=END` | `deep_researcher.py:249-255` |
| **open_deep_research** | *"last 2 searches returned similar information"* | **SEM/saturation — PROMPT ONLY, unenforced** | n/a | none — advisory | `prompts.py:170-173` |
| **GPT-Researcher** | `DEEP_RESEARCH_DEPTH` / `BREADTH` / `MAX_ITERATIONS` | CNT (fixed arity) | **2 / 3 / 3** | recursion bottoms out | `config/variables/default.py:36,37,22`; recursion `skills/deep_research.py:324-326` |
| **OpenAI Deep Research** (hosted) | `max_tool_calls` | CNT | **UNVERIFIED** (not published) | returns result | official API guide (quoted below) |

---

## 4. Findings that matter for the stop-governor

### 4.1 There is no consensus default. The number is chosen by vibes.
Default bounds across the field span **two-plus orders of magnitude**:

`OpenAI Agents SDK 10` · `Magentic-One 20` · `LangGraph 25` · `CrewAI 25` · `OpenHands 500` · `SWE-agent ∞ steps (cost-bounded only)` · `Swarm ∞` · `Auto-GPT ∞` · `AutoGen teams ∞` · `MS Agent Framework ∞`

No framework derives its number; none documents an empirical basis. **Anyone who claims "the right limit is N" is guessing.** Corollary for our design: don't agonize over the constant — invest in what *happens* at the boundary, which is where the frameworks actually differ meaningfully.

### 4.2 "Unbounded by default" is the field's most common posture — including in the framework with the richest taxonomy.
AutoGen ships **11** named termination conditions — the richest taxonomy in the space — and then defaults its teams to `termination_condition=None, max_turns=None`. Its own docstring (`_round_robin_group_chat.py:117-118`):

> *"termination_condition (TerminationCondition, optional): The termination condition for the group chat. Defaults to None. **Without a termination condition, the group chat will run indefinitely.**"*

Its successor kept that posture (`max_rounds=None`). Safety is opt-in almost everywhere. **A stop-governor that is opt-in is, empirically, a stop-governor that is off.** Ours should default to armed.

### 4.3 Failure behavior splits three ways — and "throw" is the wrong choice for a review/plan-check loop.
- **THROW, work lost** — LangGraph (`GraphRecursionError`), OpenAI Agents SDK (`MaxTurnsExceeded`), SWE-agent (`InstanceCostLimitExceededError`).
- **GRACEFUL STATUS, work kept** — OpenHands (`STUCK` / `ERROR` status + event), Swarm (loop exit, partial result), AutoGen (`StopMessage`), MS Agent Framework (*"forcing completion"*).
- **FORCED ANSWER, work harvested** — CrewAI spends **one more LLM call** to convert an exhausted loop into a usable verdict (`agent_utils.py:303-333`). The injected prompt (`translations/en.json` → `errors.force_final_answer`), verbatim:
  > *"Now it's time you MUST give your absolute best final answer. You'll ignore all previous instructions, stop using any tools, and just return your absolute BEST Final answer."*

For a governor over **review/plan-check** sub-agents this distinction is decisive. Throwing at the cap discards every finding the review produced — the most expensive possible outcome, and the one two major frameworks chose. **CrewAI's forced-verdict and OpenHands' `STUCK`-as-a-distinct-terminal-state are the patterns to copy.** Specifically: a plan-check that hits the cap should be forced to emit its best current verdict, and "stopped because it was thrashing" must be distinguishable from "stopped because it failed" and from "stopped because it finished."

### 4.4 Auto-GPT — the archetypal runaway agent — abandoned the counter for AUTHORITY.
The most famous unbounded-loop disaster in the field now reads (`classic/original_autogpt/autogpt/app/main.py:594-600`), verbatim:

```python
def _get_cycle_budget(continuous_mode: bool, continuous_limit: int) -> int | float:
    # Always run continuously - the permission manager handles per-command approval.
    # The cycle budget is now only used for Ctrl+C handling graceful shutdown.
    # If a limit is set, use it; otherwise run indefinitely.
    if continuous_limit:
        return continuous_limit
    return math.inf
```

The counter has been **explicitly demoted to Ctrl+C bookkeeping**, and governance moved to per-command human approval. Auto-GPT also has **no loop detector at all** — a full-tree search for `stuck` / `loop_detect` / `no_progress` returns nothing; its only anti-looping measure is a prompt string after a permission denial: *"Permission denied for command… Try a different approach."* (`agents/agent.py:392-398`).

The lesson the field's worst runaway case actually drew: the fix for an unbounded loop was **not a better counter — it was per-action authorization.**

### 4.5 The closest things to a novelty-based stop, ranked (this was the specific hunt).

**#1 — OpenHands `StuckDetector` — the best prior art available; the only content-based detector that is ON BY DEFAULT.**
`openhands-sdk/openhands/sdk/conversation/stuck_detector.py`. Five declared scenarios, four live:
1. repeating action→observation cycles (threshold **4**)
2. repeating action→error cycles (threshold **3**)
3. agent **monologue** — N consecutive agent messages with no user input (threshold **3**)
4. **alternating** A,B,A,B action/observation loops (threshold **6**) — catches period-2 thrash that a naive "same as last" check misses
5. context-window-error loop — **stubbed out, returns `False`**, `# TODO: blocked by .../issues/282`

Three design ideas worth stealing:
- **Normalized identity, not raw equality.** `_event_eq` (`:276-321`) deliberately ignores ids/metrics and compares *semantic content* (`source`, `thought`, `action`, `tool_name`), with the comment `# Ignore tool_call_id, llm_response_id, action_id as they vary`. Any repeat-detector we build needs exactly this: a canonicalization step, or incidental IDs defeat it.
- **A bounded scan window.** `MAX_EVENTS_TO_SCAN_FOR_STUCK_DETECTION: int = 20` (`:21`), sized deliberately: `# (4 repeats × 2 events per cycle = 8 events minimum, plus buffer)`.
- **The user message resets the detector.** Only events after the last user message count (`:73-83`) — new human input means the situation genuinely changed.

**Its limitation, which we must not inherit:** it requires **exact** content equality, including `event1.thought == event2.thought`. A model that paraphrases its reasoning each round — which is the *default* behavior at temperature > 0 — **escapes this detector entirely**. It catches a deterministic tool-retry loop; it does not catch a model re-deliberating the same conclusion in fresh words. For our stop-governor, whose sub-agents produce *prose review findings*, exact-match repetition detection is close to useless out of the box. This is the single most important limitation in the dossier.

**#2 — Magentic-One progress ledger — the best prior art for the semantic tier.** An LLM answers `is_in_loop` ("Are we in a loop where we are repeating the same requests and or getting the same responses as before? Loops can span multiple turns…", `_magentic.py:205-207`) and `is_progress_being_made` ("True if just starting, or recent messages are adding value. False if recent messages show evidence of being stuck in a loop…", `:208-210`) — each with a forced `reason` **before** the `answer` in the JSON schema (`:219-231`). This handles paraphrase, which #1 cannot.

**#3 — CrewAI `_check_tool_repeated_usage`** — N=1 exact match against a *single* `last_used_tool` slot: same tool name **and** identical arguments as the immediately preceding call (`tool_usage.py:728-738`). Weakest of the three: an A→B→A→B alternation defeats it completely (OpenHands' scenario 4 exists precisely to catch what this misses). Response is a nudge injected as the tool result: *"I tried reusing the same input, I must stop using this action input. I'll try something else instead."*

### 4.6 The three-tier architecture — the design to copy.
Magentic-One's structure is the most sophisticated governor in the field, it survived a **full framework rewrite** (AutoGen → Microsoft Agent Framework) essentially unchanged, and it maps directly onto our problem:

| Tier | Signal | Consequence | Trust |
|---|---|---|---|
| 1 — semantic | LLM: `is_request_satisfied` | success exit | trusted (success direction only) |
| 1 — semantic | LLM: `is_progress_being_made` / `is_in_loop` | +1 to `stall_count` | **not trusted to stop** |
| 2 — integrator | `stall_count > max_stall_count` (**3**) | **`_reset_and_replan()`** — escalate, don't quit | structural |
| 3 — hard counter | `max_round_count` / `max_reset_count` | **terminate** | structural, final |

The integrator is the subtle, load-bearing part (`_magentic.py:1113-1116`; identical logic at `_magentic_one_orchestrator.py:394-399`):

```python
if not self._progress_ledger.is_progress_being_made.answer or self._progress_ledger.is_in_loop.answer:
    self._magentic_context.stall_count += 1
else:
    self._magentic_context.stall_count = max(0, self._magentic_context.stall_count - 1)
```

**It decrements on progress.** A noisy one-off "no progress" verdict cannot trip it; only a *sustained* pattern can. That is hysteresis deliberately engineered around an unreliable signal — and it is the correct answer to "the semantic signal is gameable/noisy." You don't discard the signal; you **integrate it and deny it the authority to terminate**. That both generations of Microsoft's framework kept this exact `max(0, n-1)` line through a ground-up rewrite is strong evidence it earns its keep.

---

## 5. Transfer-condition check (required by the Researcher role guardrail)

For each pattern: **(a)** execution context required · **(b)** does our target satisfy it · **(c)** structural (non-compliance impossible) vs instructional (a participant must choose to comply).

| Pattern | (a) Requires | (b) Our context | (c) Guarantee |
|---|---|---|---|
| Counter (`recursion_limit`, `max_turns`, `max_iter`) | a code-controlled `while` loop the model cannot reach | **Only if** dispatch is code/hook-mediated. If Oga decides in-context to dispatch another review, there is no `while` loop to instrument. | **Structural** in-framework; **instructional** if written into `orchestrator.md` |
| Cost cap (SWE-agent `$3.00`, OpenHands budget) | a metered call path that can raise mid-run | Partially — token/credit accounting exists, but not as a raising interceptor around dispatch | Structural **only** at the metering layer |
| `StuckDetector` (repetition) | a typed, append-only event stream + canonical event identity + a loop that can `break` | Sub-agent outputs are **prose**, not typed events; no canonical identity function exists | Structural **only if** a hook owns the stream |
| Magentic progress ledger | an orchestrator that *calls out* to a judge each round and mechanically consumes JSON | Feasible — but the judge must not be the agent being judged | **Instructional** unless a hook enforces the call |
| Leaky-bucket `stall_count` | durable state across rounds | **Needs a state file**; in-context counting is not durable and not tamper-evident | Structural **only if** state lives on disk outside the model |
| Auto-GPT permission manager | per-action human approval | Matches existing hook/permission infrastructure — the closest fit of any pattern here | **Structural** |

### ⚠️ FLAG — instructional guarantee, silent failure, load-bearing (exactly the case the guardrail names)

**Every code-enforced mechanism in this dossier lives inside a `while` loop written in Python that the governed model cannot reach.** That is the entire reason those bounds hold.

If our stop-governor is expressed as instructions in `orchestrator.md` — "stop dispatching plan-checks when X" — then **it lives in the prompt layer**: the same layer where this field puts *saturation advice*, and demonstrably **not** the layer where it puts any bound it actually needs to hold. `open_deep_research` labels its prompt-level advice **"Hard Limits"** while enforcing nothing; that is precisely the failure mode to avoid replicating.

Worse, the compliance failure is **silent and load-bearing**: an orchestrator that ignores a prompt-level stop rule does not raise, does not log, and produces output that passes every downstream check — it simply dispatches another review and burns budget, indistinguishable from legitimate work. This is the same class as the memory entries `feedback_auto_mode_blocks_documented_gate_arming` and `feedback_loop_team_mechanical_dispatch_markers`: a guarantee that depends on the governed agent choosing to honor it is not a guarantee.

**Implication:** a tamper-proof stop-governor requires a **hook** (Stop / PreToolUse / SubagentStop) owning a **durable on-disk counter**, outside the orchestrator's context. Anything else is advisory. The prior art is unanimous on this point, and it is unanimous by construction rather than by opinion.

---

## 6. Source provenance (pinned; line numbers are valid at these SHAs)

| Repo | Ref | SHA | Stars | Last push | License | Notes |
|---|---|---|---|---|---|---|
| `langchain-ai/langchain` | master | `98216c0c1d` | — | 2026-07-16 | MIT | `DEFAULT_RECURSION_LIMIT` lives here, not in langgraph |
| `langchain-ai/langgraph` | main | `49ae27c2ae` | — | 2026-07-15 | MIT | |
| `microsoft/autogen` | main | `027ecf0a37` | — | **2026-04-06** | MIT | ⚠️ **MAINTENANCE MODE** (below) |
| `ag2ai/ag2` | **v0.14.0** | `aa11de3c0c` | 4,780 | 2026-07-16 | Apache-2.0 | v1.0.0b0 is beta; v0.14.0 is stable line |
| `crewAIInc/crewAI` | main | `df2e68fe0a` | 55,649 | 2026-07-16 | MIT | monorepo: `lib/crewai/src/crewai/` |
| `openai/openai-agents-python` | main | `697a46c4ba` | — | 2026-07-16 | MIT | |
| `openai/swarm` | main | `6af0b4caf3` | 21,799 | 2026-04-15 | MIT | superseded (below) |
| `Significant-Gravitas/AutoGPT` | master | `500a5cafb4` | 185,580 | 2026-07-15 | NOASSERTION ⚠️ | classic agent at `classic/original_autogpt/` |
| `SWE-agent/SWE-agent` | main | `3ea751c087` | — | 2026-07-16 | MIT | |
| `OpenHands/software-agent-sdk` | main | `51c102b9c0` | 904 | 2026-07-16 | — | agent core now lives HERE, not in `OpenHands/OpenHands` |
| `microsoft/agent-framework` | main | — | 12,169 | 2026-07-16 | MIT | AutoGen's official successor |
| `langchain-ai/open_deep_research` | main | `b764481fca` | — | 2026-07-15 | MIT | |
| `assafelovic/gpt-researcher` | master | `5cdad9cb43` | — | 2026-06-23 | — | |

### Repo-location corrections (guessed paths would have 404'd — recorded so the next scan doesn't re-derive)
- **OpenHands moved orgs**: `All-Hands-AI/OpenHands` → **`OpenHands/OpenHands`** (301 redirect). The agent core then **left that repo entirely** → `OpenHands/software-agent-sdk`. `openhands/controller/stuck.py` no longer exists; it is now `openhands-sdk/openhands/sdk/conversation/stuck_detector.py`.
- **CrewAI restructured** to a monorepo: `src/crewai/agent.py` → `lib/crewai/src/crewai/agent/core.py`, and `max_iter` actually lives in `lib/crewai/src/crewai/agents/agent_builder/base_agent.py`.
- **AG2 v1 rewrote the package** from `autogen/` to `ag2/`; `ConversableAgent` / `max_consecutive_auto_reply` are **gone from `main`**. Cited at tag **v0.14.0** (current stable) accordingly.

### Maturity / decay signals
- ⚠️ **AutoGen is in MAINTENANCE MODE.** README, verbatim: *"AutoGen is now in maintenance mode. It will not receive new features or enhancements and is community managed going forward."* and *"New users should start with Microsoft Agent Framework."* Its HEAD is 2026-04-06 (~3 months stale). **The richest termination taxonomy in the field sits on a frozen framework.**
- ⚠️ **Successor regression:** given a clean-sheet rewrite, Microsoft **did not add semantic stops** — it *deleted* the 11-class taxonomy, replacing it with `max_rounds` (default `None`) plus a bare `TerminationCondition: TypeAlias = Callable[[list[Message]], bool | Awaitable[bool]]`. The considered judgment of the team with the most experience here was that a counter plus an escape hatch beats a taxonomy. Magentic-One's ledger was the one thing they carried over intact.
- ⚠️ **Swarm superseded.** README: *"Swarm is now replaced by the OpenAI Agents SDK… We recommend migrating to the Agents SDK for all production use cases."* Cited for historical contrast only.
- ⚠️ **AutoGPT license = `NOASSERTION`** per the GitHub API — mixed licensing; treat as adoption risk if any code is borrowed (patterns/ideas are fine).

### Honesty flags
- **UNVERIFIED — OpenAI Deep Research `max_tool_calls` default.** The official API guide documents the parameter (*"You can also use the `max_tool_calls` parameter… to control the total number of tool calls… that the model will make before returning a result"*) but **states no default**. Not guessed. Its intrinsic stop criterion is undocumented and RL-internal.
- **UNVERIFIED — AutoGen `FunctionCallTermination` exact line.** Confirmed present in the public `__all__` (`conditions/__init__.py:9,30`) and defined in `_terminations.py`; its class-def line was not individually read (approximated `~560` in the table). The taxonomy membership claim is verified; the one line number is not.
- **Self-correction (recorded deliberately).** My first pass reported that a SWE-agent config used the value-based `ScoreRetryLoop`. That was **my own grep bug**: the pattern `"accept_score\|type: retry"` matched `type: retry` (line 7) rather than `accept_score`. On re-check, **`accept_score` appears in zero shipped configs** — all 24 config YAMLs were fetched and searched individually. The corrected finding (a value-based stop exists in code but ships unused) is *stronger* evidence for the thesis than the error was against it. Flagging because the near-miss is the exact failure mode the honesty bar exists to catch.
- **Scope note.** "Shipped framework" here means the code in the repo's default branch at the pinned SHA. "Used by default" is stated separately and explicitly wherever it differs — that distinction (`ScoreRetryLoop` exists / is never used; `StuckDetector` exists *and* is on by default) carries most of the analytical weight in this dossier.

---

### Verified source permalinks (SHA-pinned — these do not rot as `main` drifts)

Every link below was fetched as raw source during this research. Line anchors are valid at the pinned SHA.

**LangGraph / LangChain**
- [`langchain_core/runnables/config.py#L171` — `DEFAULT_RECURSION_LIMIT = 25`](https://github.com/langchain-ai/langchain/blob/98216c0c1d/libs/core/langchain_core/runnables/config.py#L171)
- [`langchain_core/runnables/config.py#L262-L269` — `ensure_config` injects the default](https://github.com/langchain-ai/langchain/blob/98216c0c1d/libs/core/langchain_core/runnables/config.py#L262-L269)
- [`langgraph/pregel/_loop.py#L607-L609` — `out_of_steps` enforcement](https://github.com/langchain-ai/langgraph/blob/49ae27c2ae/libs/langgraph/langgraph/pregel/_loop.py#L607-L609)
- [`langgraph/pregel/main.py#L3002-L3011` — `raise GraphRecursionError`](https://github.com/langchain-ai/langgraph/blob/49ae27c2ae/libs/langgraph/langgraph/pregel/main.py#L3002-L3011)
- [`langgraph/errors.py#L67` — `class GraphRecursionError`](https://github.com/langchain-ai/langgraph/blob/49ae27c2ae/libs/langgraph/langgraph/errors.py#L67)

**AutoGen (maintenance mode) + Magentic-One**
- [`conditions/__init__.py#L20-L32` — the full 11-condition `__all__`](https://github.com/microsoft/autogen/blob/027ecf0a37/python/packages/autogen-agentchat/src/autogen_agentchat/conditions/__init__.py#L20-L32)
- [`conditions/_terminations.py` — all condition implementations](https://github.com/microsoft/autogen/blob/027ecf0a37/python/packages/autogen-agentchat/src/autogen_agentchat/conditions/_terminations.py)
- [`base/_termination.py#L79-L87` — `&` / `|` composition](https://github.com/microsoft/autogen/blob/027ecf0a37/python/packages/autogen-agentchat/src/autogen_agentchat/base/_termination.py#L79-L87)
- [`_round_robin_group_chat.py#L117-L119` — *"will run indefinitely"*](https://github.com/microsoft/autogen/blob/027ecf0a37/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_round_robin_group_chat.py#L117-L119)
- [`_magentic_one_group_chat.py#L117-L119` — `max_turns=20`, `max_stalls=3`](https://github.com/microsoft/autogen/blob/027ecf0a37/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_magentic_one/_magentic_one_group_chat.py#L117-L119)
- [`_magentic_one_orchestrator.py#L388-L406` — **the leaky bucket**](https://github.com/microsoft/autogen/blob/027ecf0a37/python/packages/autogen-agentchat/src/autogen_agentchat/teams/_group_chat/_magentic_one/_magentic_one_orchestrator.py#L388-L406)
- [AutoGen README — maintenance-mode notice](https://github.com/microsoft/autogen/blob/main/README.md)

**Microsoft Agent Framework (AutoGen's successor)**
- [`_base_group_chat_orchestrator.py#L59` — `TerminationCondition` is a bare `Callable`](https://github.com/microsoft/agent-framework/blob/main/python/packages/orchestrations/agent_framework_orchestrations/_base_group_chat_orchestrator.py#L59)
- [`_magentic.py#L1107-L1121` — semantic ledger → stall_count → replan](https://github.com/microsoft/agent-framework/blob/main/python/packages/orchestrations/agent_framework_orchestrations/_magentic.py#L1107-L1121)
- [`_magentic.py#L1241-L1259` — only counters terminate](https://github.com/microsoft/agent-framework/blob/main/python/packages/orchestrations/agent_framework_orchestrations/_magentic.py#L1241-L1259)

**AG2 (v0.14.0 stable)**
- [`conversable_agent.py#L174` — `MAX_CONSECUTIVE_AUTO_REPLY = 100`](https://github.com/ag2ai/ag2/blob/v0.14.0/autogen/agentchat/conversable_agent.py#L174)
- [`conversable_agent.py#L275-L279` — default `is_termination_msg` = `== "TERMINATE"`](https://github.com/ag2ai/ag2/blob/v0.14.0/autogen/agentchat/conversable_agent.py#L275-L279)

**CrewAI**
- [`base_agent.py#L298-L300` — `max_iter: int = Field(default=25)`](https://github.com/crewAIInc/crewAI/blob/df2e68fe0a/lib/crewai/src/crewai/agents/agent_builder/base_agent.py#L298-L300)
- [`agent/core.py#L203-L206` — `max_execution_time = None`](https://github.com/crewAIInc/crewAI/blob/df2e68fe0a/lib/crewai/src/crewai/agent/core.py#L203-L206)
- [`agent_utils.py#L303-L333` — `handle_max_iterations_exceeded` (forced final answer)](https://github.com/crewAIInc/crewAI/blob/df2e68fe0a/lib/crewai/src/crewai/utilities/agent_utils.py#L303-L333)
- [`tool_usage.py#L728-L738` — `_check_tool_repeated_usage`](https://github.com/crewAIInc/crewAI/blob/df2e68fe0a/lib/crewai/src/crewai/tools/tool_usage.py#L728-L738)

**OpenAI Agents SDK / Swarm**
- [`run_config.py#L33` — `DEFAULT_MAX_TURNS = 10`](https://github.com/openai/openai-agents-python/blob/697a46c4ba/src/agents/run_config.py#L33)
- [`run.py#L1065-L1073` — check + `raise MaxTurnsExceeded`](https://github.com/openai/openai-agents-python/blob/697a46c4ba/src/agents/run.py#L1065-L1073)
- [`swarm/core.py#L146` — `max_turns: int = float("inf")`](https://github.com/openai/swarm/blob/6af0b4caf3/swarm/core.py#L146)
- [Swarm README — superseded-by-Agents-SDK notice](https://github.com/openai/swarm/blob/main/README.md)

**Auto-GPT**
- [`app/main.py#L594-L600` — cycle budget demoted to Ctrl+C handling](https://github.com/Significant-Gravitas/AutoGPT/blob/500a5cafb4/classic/original_autogpt/autogpt/app/main.py#L594-L600)
- [`agents/agent.py#L385-L398` — permission manager (AUTHORITY)](https://github.com/Significant-Gravitas/AutoGPT/blob/500a5cafb4/classic/original_autogpt/autogpt/agents/agent.py#L385-L398)

**SWE-agent**
- [`agent/models.py#L73-L78` — `per_instance_cost_limit = 3.0`](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087/sweagent/agent/models.py#L73-L78)
- [`agent/agents.py#L413` — `while not step_output.done:` (no step counter)](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087/sweagent/agent/agents.py#L413)
- [`agent/reviewer.py#L416-L449` — **`n_sample=5` + variance-penalized score**](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087/sweagent/agent/reviewer.py#L416-L449)
- [`agent/reviewer.py#L617-L645` — `ScoreRetryLoop.retry()` (value-based, unused)](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087/sweagent/agent/reviewer.py#L617-L645)
- [`agent/reviewer.py#L524-L555` — `ChooserRetryLoop.retry()` (the shipped one; counters only)](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087/sweagent/agent/reviewer.py#L524-L555)
- [`config/benchmarks/250212_sweagent_heavy_sbl.yaml` — the only shipped retry config](https://github.com/SWE-agent/SWE-agent/blob/3ea751c087/config/benchmarks/250212_sweagent_heavy_sbl.yaml)

**OpenHands (agent core now lives in `software-agent-sdk`)**
- [`conversation/stuck_detector.py` — **the StuckDetector, whole file**](https://github.com/OpenHands/software-agent-sdk/blob/51c102b9c0/openhands-sdk/openhands/sdk/conversation/stuck_detector.py)
- [`conversation/types.py#L150-L161` — thresholds 4 / 3 / 3 / 6](https://github.com/OpenHands/software-agent-sdk/blob/51c102b9c0/openhands-sdk/openhands/sdk/conversation/types.py#L150-L161)
- [`impl/local_conversation.py#L183-L201` — `max_iteration_per_run=500`, `stuck_detection=True`](https://github.com/OpenHands/software-agent-sdk/blob/51c102b9c0/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L183-L201)
- [`impl/local_conversation.py#L1796-L1804` — STUCK status, graceful](https://github.com/OpenHands/software-agent-sdk/blob/51c102b9c0/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py#L1796-L1804)

**Deep research**
- [`open_deep_research/prompts.py#L164-L174` — **the unenforced "Hard Limits" saturation prompt**](https://github.com/langchain-ai/open_deep_research/blob/b764481fca/src/open_deep_research/prompts.py#L164-L174)
- [`open_deep_research/configuration.py#L94-L108` — `max_researcher_iterations=6`, `max_react_tool_calls=10`](https://github.com/langchain-ai/open_deep_research/blob/b764481fca/src/open_deep_research/configuration.py#L94-L108)
- [`open_deep_research/deep_researcher.py#L243-L262` — counter OR self-declared exit](https://github.com/langchain-ai/open_deep_research/blob/b764481fca/src/open_deep_research/deep_researcher.py#L243-L262)
- [`gpt_researcher/config/variables/default.py` — depth 2 / breadth 3 / MAX_ITERATIONS 3](https://github.com/assafelovic/gpt-researcher/blob/5cdad9cb43/gpt_researcher/config/variables/default.py)
- [`gpt_researcher/skills/deep_research.py#L320-L343` — fixed-arity recursion](https://github.com/assafelovic/gpt-researcher/blob/5cdad9cb43/gpt_researcher/skills/deep_research.py#L320-L343)
- [OpenAI Deep Research API guide — `max_tool_calls` (no default published)](https://developers.openai.com/api/docs/guides/deep-research)

**Prior art that is NOT shipped (parked)**
- [arXiv:2603.19896 — *Utility-Guided Agent Orchestration for Efficient LLM Tool Use*](https://arxiv.org/abs/2603.19896) — Liu, Zhao, Xu; submitted 2026-03-20. Proposes exactly the marginal-yield stop the field lacks: *"a utility-guided orchestration policy that selects among actions such as respond, retrieve, tool call, verify, and stop by balancing estimated gain, step cost, uncertainty, and redundancy."* **Research prototype; no public code repository.** RESEARCH-ONLY — the closest published formulation of a value-based stop, and the fact that it has no implementation is itself corroborating evidence for §1.

---

## 7. Recommendations for the stop-governor (handed to Oga; not decisions)

1. **Do not build a saturation stop in the prompt layer.** The field has already run this experiment: `open_deep_research` labels prompt-level saturation advice "Hard Limits" and enforces nothing. If our governor is instructions in `orchestrator.md`, it is advisory — and its failure is silent (§5 flag).
2. **Adopt the three-tier shape** (§4.6): semantic signal → leaky-bucket integrator → hard counter with terminal authority. Never let tier 1 terminate. This is the only design in the field that survived a full rewrite.
3. **Steal the leaky bucket verbatim** — `stall_count = max(0, stall_count - 1)` on progress. It is the cheapest known defense against a noisy semantic verdict, and it is 2-for-2 across framework generations.
4. **Repetition detection needs canonicalization *and* must not rely on exact match.** Copy OpenHands' `_event_eq` idea (ignore incidental IDs) but note its fatal limitation for our case: our sub-agents emit *prose findings*, and exact-match repetition will not fire on a paraphrased re-finding (§4.5). A *finding-identity* function (normalized claim, not normalized text) is the real work here — and no framework has solved it. **This is the genuine gap in the prior art and the highest-value thing we could build.**
5. **At the cap, force a verdict — do not throw.** CrewAI's forced-final-answer (§4.3) is the right shape for review/plan-check: hitting the limit should convert accumulated deliberation into a usable verdict, not discard it. Throwing (LangGraph/OpenAI SDK) is the worst option for our use case.
6. **Make `STUCK` a distinct terminal state**, per OpenHands (`STUCK` ≠ `ERROR` ≠ `FINISHED`). "Stopped thrashing" and "stopped failing" demand different follow-ups; collapsing them loses the signal we most want.
7. **Default it to armed.** The field's dominant posture is unbounded-by-default (§4.2), including AutoGen, its successor, Swarm, and Auto-GPT. An opt-in governor is an off governor.
8. **Don't over-tune the constant.** Defaults span 10 → ∞ with no derivation anywhere (§4.1). Spend the effort on boundary behavior, not the number.
9. **Consider AUTHORITY as a tier.** Auto-GPT — the field's most notorious runaway — concluded the answer was per-action human approval, not a better counter (§4.4). This is also the pattern that best matches our existing hook/permission infrastructure (§5 table).
