# Async completion barrier (fan-out/fan-in) — prior art survey

**Date:** 2026-07-09
**Mode:** Researcher Mode A (on-demand; not a radar cycle — this is a targeted design question, so no radar row is added; results below are the deliverable)
**Question:** How do real production orchestration systems reliably know "all N parallel workers have reached a terminal state" before acting on the aggregate — specifically the exact mechanism that closes the race between "recording expected work" and "acting once it's done" — and what, if anything, is directly portable to a single-process, turn-based LLM tool-calling orchestrator (no persistent background process, no message queue)?

## TL;DR answer

Every mature system studied uses the **same one structural idiom**, dressed differently:

> **Fix the expected set synchronously, at dispatch time, before any unit of work can possibly return — then gate on set-equality (`completed == expected`), never on a bare counter or an event/notification stream.**

The size/sophistication of the surrounding machinery (durable histories, DAG schedulers, state-machine ARNs) is there to survive **failure domains our orchestrator doesn't have** — multi-process crashes, cross-machine workers, multi-day durations, exactly-once delivery. For a **single-process, single-turn, foreground tool-calling loop**, the barrier is **already provided structurally, for free, by the Anthropic Messages API's tool-use protocol**: an assistant turn that emits N `tool_use` blocks cannot be followed by a next assistant turn until a user message carries a `tool_result` for every one of those N ids. That is a Promise.all()/asyncio.gather() built into the wire protocol, not a convention — and it's already what the loop-team's own harness rides on for foreground `Task`/`Agent` dispatch.

The one place this breaks in practice is **background dispatch** (`run_in_background: true`, now the *default* for subagents as of Claude Code v2.1.198 per its own docs) — because completion is then delivered via an async notification channel, and that channel is **documented and reproduced as unreliable at N>1 concurrency** in Anthropic's own issue tracker (see §6). That is a live, real-world demonstration of exactly the "record a count and hope" anti-pattern the dispatch brief warns about — happening inside the very tool this team runs on.

---

## 1. Temporal.io — `Promise.allOf()` / `Promise.all()` over Activities & Child Workflows

**Source:** [`temporalio/sdk-java` — `Promise.java`](https://github.com/temporalio/sdk-java/blob/master/temporal-sdk/src/main/java/io/temporal/workflow/Promise.java) (opened directly via `curl` of the raw file, confirmed real):

```java
/**
 * Returns Promise that becomes completed when all arguments are completed. A single promise
 * failure causes resulting promise to deliver the failure immediately.
 */
static Promise<Void> allOf(Promise<?>... promises) {
  return WorkflowInternal.promiseAllOf(promises);
}
```
(lines 155–161 of the file, current `master`)

**TypeScript SDK fan-out/fan-in** (Temporal docs, `develop/typescript/child-workflows`):
```ts
const responseArray = await Promise.all(
  names.map((name) => executeChild(childWorkflow, { args: [name] })),
);
```
`executeChild()` — "To start a Child Workflow Execution and await its completion, use `executeChild`."

**Go SDK — when you need per-item control (not just `Promise.all`)**, the community-documented pattern ([Temporal community forum](https://community.temporal.io/t/correct-way-to-wait-for-all-activities-to-complete/12659)) uses an explicit **counter compared against a known total**, driven by a `Selector`:
```go
selector.AddReceive(signalChan, func(c workflow.ReceiveChannel, more bool) {
    var projectID string
    for c.ReceiveAsync(&projectID) {
        fut := workflow.ExecuteActivity(ctx, Activity, args)
        selector.AddFuture(fut, callback)
        activeFutures++
    }
})
for activeFutures > 0 || totalSignals != metricsCount {
    selector.Select(ctx)
}
```
The loop condition is explicitly a **count-vs-expected-total gate** (`activeFutures > 0 || totalSignals != metricsCount`) — note it is *two* conditions, not one counter: "no futures still outstanding" AND "we've actually seen every signal we expected to see" (guarding against under-counting from a race in signal delivery). This is the deeper idiom under the sugar: expected-total is captured/verified independently, not just decremented blindly.

**Retry:** Temporal Activities carry a first-class `RetryPolicy` (bounded retry is a config field on the Activity, not hand-rolled) — the workflow code above "relies on Temporal's built-in retry mechanism" per the same thread. **Transfer note:** this requires Temporal's durable execution engine (workflow history replay after crash) — not present in our context; see §7.

## 2. Apache Airflow — trigger rules (`all_success` / `all_done` / `none_failed_min_one_success`)

**Source:** [Astronomer / Apache Airflow docs on trigger rules](https://www.astronomer.io/docs/learn/airflow-trigger-rules) (fetched directly):

- **`all_success`** (default): "The task runs only when all upstream tasks have succeeded."
- **`all_done`**: "The task runs once all upstream tasks are done with their execution" — regardless of individual success/fail — this is the **partial-completion fallback trigger rule**, used for a fan-in ("join") task that must run even if some branches failed.
- **`all_failed`**: "The task runs only when all upstream tasks are in a `failed` or `upstream_failed` state."
- **`none_failed_min_one_success`**: recommended for a fan-in after conditional branching — "at least one upstream task has succeeded" AND "no upstream tasks are in the `failed` or `upstream_failed` state" (skipped branches don't block it).

**The mechanism that closes the race:** Airflow's scheduler does **not** poll a live counter. Each `TaskInstance`'s terminal state is persisted in the metadata DB the moment it finishes; the downstream (fan-in) task's dependencies are evaluated by the scheduler against the **fixed, DAG-defined set of upstream `task_ids`** (declared at DAG-parse time, before any task instance runs) compared to their current DB state. The "expected set" is the DAG structure itself, captured before execution starts — so there is no window where the fan-in task could observe a subset and be fooled: its trigger-rule check is a query over *all* declared upstream task_ids' persisted states, not an incrementing counter.

**Retry:** per-task `retries` + `retry_delay` (bounded, declared per-operator) — the Airflow analogue of "bounded retry for a worker that fails." **Transfer note:** requires a scheduler + metadata DB across scheduler restarts; heavy overkill for one turn (see §7).

## 3. AWS Step Functions — `Parallel` state

**Source:** [official AWS docs, `state-parallel.html`](https://docs.aws.amazon.com/step-functions/latest/dg/state-parallel.html) (fetched directly, full text captured):

> "A `Parallel` state causes AWS Step Functions to execute each branch, starting with the state named in that branch's `StartAt` field, as concurrently as possible, and **wait until all branches terminate** (reach a terminal state) before processing the `Parallel` state's `Next` field."

Error handling (this is the explicit partial-fallback machinery):

> "If any branch fails, because of an unhandled error or by transitioning to a `Fail` state, the entire `Parallel` state is considered to have failed and all its branches are stopped."

- `Retry` field: "an array of objects, called Retriers, that define a retry policy in case the state encounters runtime errors" — **bounded, declarative retry**, directly the shape asked for.
- `Catch` field: "an array of objects, called Catchers, that define a fallback state that is executed if the state encounters runtime errors and its retry policy is exhausted" — **exactly** "explicit partial-completion fallback if retry also fails."

**Mechanism:** Step Functions is a managed state machine service — the "expected set" is the `Branches` array in the state's own JSON definition, fixed before execution starts; the service's execution history (an append-only, durable event log per execution ARN) is what the service itself queries to know when all branches have reached a terminal state. Structural, but backed by AWS's own persistent execution-history store — not something we have.

## 4. Python `asyncio.gather()` — the mechanism, read from CPython source

**Source:** [`python/cpython` `Lib/asyncio/tasks.py`](https://raw.githubusercontent.com/python/cpython/main/Lib/asyncio/tasks.py), fetched directly via `curl`. This is the clearest, most literal answer to "what closes the race, structurally, not by convention":

```python
def gather(*coros_or_futures, return_exceptions=False):
    ...
    def _done_callback(fut, cur_task=cur_task):
        nonlocal nfinished
        nfinished += 1
        ...
        if nfinished == nfuts:
            # All futures are done; create a list of results
            # and set it to the 'outer' future.
            results = []
            for fut in children:
                ...
            outer.set_result(results)

    arg_to_fut = {}
    children = []
    nfuts = 0
    nfinished = 0
    ...
    for arg in coros_or_futures:
        ...
        nfuts += 1
        arg_to_fut[arg] = fut
        ...
        fut.add_done_callback(_done_callback)
        ...
        children.append(fut)

    outer = _GatheringFuture(children, loop=loop)
    ...
    return outer
```

**Why this structurally cannot race** (the exact answer to the brief's question): `nfuts` is incremented **synchronously**, inside the same, single-threaded call to `gather()`, in the *same* loop that registers each future's `add_done_callback`. Because `asyncio` is single-threaded cooperative scheduling, **no `_done_callback` can possibly run until this synchronous `for` loop returns control to the event loop** — so by the time the *first* completion callback can fire, `nfuts` already equals the true, final expected count. The gate `if nfinished == nfuts` is therefore comparing a live running count against a **count that was fixed before any unit of work could complete** — there is no window in which a callback observes a partially-populated `nfuts`. This is "counting semaphore" done correctly: the total is latched *before* the race can start, not read concurrently with it.

`return_exceptions=True` is the "gather with exception handling" idiom named in the brief: a failed/cancelled future's exception is captured into `results` (as a value, not raised) so **the outer future still only resolves once `nfinished == nfuts`** — a straggler failure doesn't create a null/undefined slot; every position in the result list is guaranteed filled or it doesn't resolve. That guarantee — no result acted on before all N are accounted for — is the exact property the brief asks about, and it's not "by convention," it's because resolving `outer` is the *only* code path that ever reads `children`, and that code path is gated by the synchronously-fixed `nfuts`.

`asyncio.wait(aws, return_when=ALL_COMPLETED)` — confirmed via [official docs](https://docs.python.org/3/library/asyncio-task.html) — is the "completion set vs expected set" idiom in its most literal form: it returns `(done, pending)` sets, and "unlike `wait_for()`, `wait()` does not cancel the futures when a timeout occurs" — you inspect `done` and `pending` directly rather than trust a counter.

## 5. LLM multi-agent frameworks — do any of them add a genuinely new primitive?

**LangGraph** ([`langchain-ai/langgraph`](https://github.com/langchain-ai/langgraph), MIT, 36.9k★, last push 2026-07-09 — confirmed live via `gh api`): the `Send` API (`libs/langgraph/langgraph/types.py`) dispatches parallel branches; LangGraph's own "Pregel" execution model groups them into a **superstep** — "a superstep is an execution unit in LangGraph that groups together nodes that can run concurrently, where all nodes in a superstep execute at the same time and must all complete before the graph proceeds to the next step" (per docs/tutorials cross-checked against `libs/langgraph/langgraph/pregel/_algo.py` and `_loop.py`, both real files in the repo per `gh api search/code`). Two things worth stealing conceptually even though the runtime is unrelated to ours:
  - The **merge/reduce step matters as much as the barrier**: "A common bug is defining a state field as `list[str]` instead of `Annotated[list[str], operator.add]` — the code runs fine but only the last branch's result stays." I.e. a correct barrier with a last-write-wins merge silently drops N−1 of N results. This is a direct analogue to a reconciliation step that must *append/collect*, not overwrite.
  - **Atomic failure**: "If one parallel node fails, the entire superstep fails atomically... neither result gets saved to state" — i.e., their default is closer to Step Functions' Parallel-state semantics (all-or-nothing) than a partial-completion fallback; you have to opt in to partial acceptance.

**CrewAI** ([official docs, `docs.crewai.com/en/learn/kickoff-async`](https://docs.crewai.com/en/learn/kickoff-async), fetched directly): the **official, documented pattern for running multiple crews in parallel is literally**:
```python
results = await asyncio.gather(
    crew_1.akickoff(inputs={...}),
    crew_2.akickoff(inputs={...})
)
```
No CrewAI-specific fan-in primitive — they defer entirely to the Python stdlib idiom from §4, and (confirmed by direct read) **the docs show no error-handling/retry wrapper at all** for individual crew failures — that's left to the caller. This is strong evidence that even a widely-used, funded multi-agent framework doesn't believe a bespoke barrier primitive is needed once you have real language-level async.

**Microsoft Agent Framework** ([official Microsoft Learn tutorial](https://learn.microsoft.com/en-us/agent-framework/tutorials/workflows/simple-concurrent-workflow), fetched directly) has `ConcurrentBuilder(participants=[a, b, c]).build()` with a default aggregator; per the companion architecture writeup (cross-checked, [Arafat Tehsin's post citing the framework's own `AddFanOutEdge`/`AddFanInEdge`](https://arafattehsin.com/blog/agent-orchestration-patterns-part-3/)): "**Fan in edges requires all inputs to be available before the target executor is triggered**" and "the fan-in barrier... ensures the aggregator only fires when all three reviewers have completed (or timed out)." Note "or timed out" — i.e. their barrier condition is `completed ∪ timed-out == expected`, not `completed == expected`; a hung branch still eventually unblocks the barrier as a (marked) failure rather than blocking forever. That maps directly to "bounded retry, then explicit partial-completion fallback."

**AutoGen** — not surveyed in depth; it is oriented around sequential/round-robin conversational turn-taking (group chat), not N-way parallel fan-out, so it's a weaker match for this specific question than the three above. Flagging as **not deeply verified** rather than asserting a finding I didn't confirm.

## 6. Claude Agent SDK / Claude Code itself — the most directly relevant, and where it actually breaks

This is the system whose failure mode is most load-bearing for us, since it's the substrate the orchestrator runs on.

**(a) The structural guarantee that already exists — foreground tool calls.** Per the [official tool-use docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use) and cross-checked general API behavior: when Claude's turn contains multiple `tool_use` blocks, "your code executes the operations and sends back `tool_result` blocks... each `tool_use` block must have a corresponding `tool_result` block in the next message... you cannot send partial results and expect the model to wait." **This is enforced by the API, not by agent discipline**: the next assistant turn is not generated from an incomplete tool_result set. When Oga (the orchestrator) dispatches N `Task`/`Agent` tool calls **in one turn without `run_in_background`**, the harness cannot produce Oga's next turn until it has collected all N `tool_result`s — that IS `Promise.all()` / `asyncio.gather()`, implemented at the wire-protocol level, for free.

**(b) Where it breaks — background subagents.** Per the [official subagents doc](https://code.claude.com/docs/en/agent-sdk/subagents) (fetched directly): "**Subagents run in the background by default**. An Agent tool call that omits the `run_in_background` input launches a background subagent... Before v2.1.198, omitting `run_in_background` ran the subagent synchronously." So the *current* default silently opts into the async-notification path unless the dispatcher explicitly passes `run_in_background: false`.

Once backgrounded, completion is delivered via a `<task-notification>` message — and this channel is **documented broken at N>1 concurrency, with two independent, real, currently-open/closed issues opened directly and read in full via `gh issue view`**:

- [**#20754**](https://github.com/anthropics/claude-code/issues/20754) (OPEN, filed 2026-01-25, v2.1.19): "When running multiple background agents (`run_in_background: true`) in parallel, completion notifications are not consistently delivered to the main session. Only 1 out of 3 agents sent a notification upon completion... All agents completed successfully (verified via `tail` on output files), but only 1 notification was delivered." Their own listed workaround: **"Manually check agent output files"** — i.e., abandon the notification stream and directly diff a completed-set against the expected set by reading each unit's own terminal artifact. That workaround *is* the correct idiom (§4/§5); the bug is that the framework's own convenience layer (the notification) is not a substitute for it.
- [**#21165**](https://github.com/anthropics/claude-code/issues/21165) (CLOSED, filed 2026-01-27, v2.1.20): "Agent processes only first notification when multiple background tasks complete in parallel, remaining notifications queued indefinitely" — 5 background tasks, only the first notification is processed, session hangs at "0 tokens" until manual ESC, and one task's notification (#5) never surfaces even after the interrupt. The reporter's own root-cause hypotheses (queue capacity, state-machine lock, race in the event handler) all describe the **exact anti-pattern the research brief calls out**: relying on an event-count/notification-arrival signal instead of verifying a completion set.

**Anthropic's own architectural answer for scale ("more than a few tasks per turn") is not to fix the notification channel — it's to leave the turn-based paradigm entirely.** Per the [subagents doc](https://code.claude.com/docs/en/agent-sdk/subagents): "**Subagents work well for a few delegated tasks per turn. For runs that coordinate dozens to hundreds of agents, use the `Workflow` tool**, which moves the orchestration into a script the runtime executes outside the conversation context." Per the [dedicated workflows doc](https://code.claude.com/docs/en/workflows): a workflow is literally "a JavaScript script... Claude writes the script... a runtime executes it in the background," with primitives like `agent()` (spawn one) and `pipeline()` (run one per item in a list) — i.e., it re-enters a **real async runtime** (Node/JS event loop) where genuine `Promise.all`-style semantics apply again, specifically *because* the turn-based conversational loop cannot give you a reliable N-way barrier once N is more than "a few." I could not find the `pipeline()`/`agent()` function signatures or their documented retry/partial-failure semantics in the fetched TypeScript SDK reference page (the excerpt returned did not contain a dedicated Workflow-tool section) — **flagging this as not found** rather than guessing at retry semantics for it.

## 7. Direct answer: what's portable, what's overkill

**Portable, zero new infrastructure, use it as the default:**
Dispatch all N sub-agents as **foreground** tool calls in a single assistant turn (i.e., do not set `run_in_background: true`, or set it explicitly to `false`). The Anthropic Messages API's tool-use protocol *is* the barrier: it structurally cannot produce Oga's next turn without a `tool_result` for every `tool_use` id from that turn. This is the same shape as `Promise.all()` (Temporal TS SDK), `asyncio.gather()` (CrewAI's own recommended pattern), and Step Functions Parallel's "wait until all branches terminate" — except we get it from the substrate itself, for free, enforced structurally rather than by any participant's compliance. **Transfer-condition check:** (a) requires nothing beyond what the harness already provides — no hook, no extra runtime; (b) our context satisfies it as long as dispatch stays foreground/synchronous within one turn; (c) the guarantee is **structural** (the API enforces it, non-compliance is impossible, not merely discouraged).

**Portable, needs one small piece of orchestrator-side bookkeeping (not new infra — a data structure, not a service):**
If background dispatch is unavoidable (e.g. a unit of work exceeds a practical foreground-turn duration), do **not** gate on the notification stream. Maintain:
- an **expected set**, fixed at dispatch time (the list of unit IDs / agent_ids you just launched, captured *before* any of them can finish — mirroring `nfuts` in `asyncio.gather` and the DAG's declared `task_ids` in Airflow),
- a **completed set**, populated only by *directly reading each unit's own terminal state* (its output file / session transcript / an explicit status check — exactly issue #20754's own documented workaround), never by counting notification arrivals,
- proceed to reconciliation only when `completed ∪ abandoned == expected` (set equality, not a counter reaching a number) — this is the Microsoft Agent Framework's "all inputs available... or timed out" fan-in condition and Airflow's `all_done`/`none_failed_min_one_success` trigger rules, translated into a plain check the orchestrator runs itself.

**Portable, straightforward mapping for retry/fallback:**
- **Bounded retry (1 retry):** for any unit in `expected − completed` after a reasonable check, dispatch exactly one fresh replacement sub-agent for that unit only (never re-run the whole batch) — this is Step Functions' `Retry` field and Airflow's per-task `retries`, both bounded and declarative rather than open-ended.
- **Explicit partial-completion fallback:** if the retry also lands in `expected − completed`, do **not** silently proceed as if it succeeded and do **not** block indefinitely — record it as an explicit "N−1 of N; unit X abandoned, reason Y" state and carry that into reconciliation. This mirrors Step Functions' `Catch` fallback state and Airflow's `all_done` rule (proceed regardless of individual state, but the state is visible, not silently coerced to success).
- **Merge discipline at reconciliation:** collect into a list/append structure, not last-write-wins — LangGraph's own documented bug class (`list[str]` vs `Annotated[list[str], operator.add]`) is a direct warning: a correct barrier feeding a lossy merge still drops results silently.

**Overkill for this context (name it so it's not mistakenly reached for):**
- **Temporal's durable execution** (workflow history replay, Activity heartbeating, cross-process/cross-machine crash recovery, `RetryPolicy` objects with backoff curves) — solves surviving a *process* or *machine* crash mid-workflow across a fleet of workers; our orchestrator is one process, one conversation, no crash-and-resume-elsewhere requirement.
- **Airflow's scheduler + metadata DB + trigger-rule engine** — solves cross-run, cross-DAG scheduling at a shared, persistent, multi-tenant level; we have one run, one DAG-of-one-fan-out, no scheduler.
- **AWS Step Functions' state-machine execution service** — solves durable, externally-inspectable state visible across independent AWS services via execution ARNs; we have no external service boundary to bridge.
- **A custom message queue / pub-sub layer** for subagent-to-orchestrator completion signaling — this is precisely what Claude Code's own background-task notification channel already *is*, and it's the one piece of this whole survey that's **documented broken** (§6). Building more of that shape, rather than less, would be reproducing the exact fragile layer that's already failing in production for the underlying tool.

## 8. Transfer-condition check (per role-brief requirement, for every borrowed pattern)

| Pattern | Requires | Our context satisfies it? | Guarantee type |
|---|---|---|---|
| API-enforced tool_result barrier (foreground dispatch) | Staying inside one assistant turn, no `run_in_background` | Yes, by construction — costs nothing, just don't background it | **Structural** (API refuses to proceed without all N results) |
| `asyncio.gather`-style fixed-`nfuts`-before-callbacks | A single synchronous scheduling point where the expected count is latched before async work can resolve | Yes — the dispatch turn itself is that synchronous point | **Structural**, if implemented as "compute my full unit list, then dispatch all N, then don't act until you've directly checked all N" |
| Expected-set vs completed-set (Airflow/Step Functions/asyncio.wait) | Bookkeeping the orchestrator itself maintains (a plain list/dict) | Yes — no service, just a return value Oga tracks in its own turn | **Structural** *if* completed-set is populated by direct state reads, **instructional** (i.e., breakable) if it's populated by trusting an async notification — this is exactly where #20754/#21165 broke |
| Bounded retry + explicit fallback (Step Functions Retry/Catch, Airflow retries + all_done) | Nothing beyond re-dispatching one unit and recording a visible "abandoned" state | Yes | **Instructional** — the orchestrator must actually check and record it; nothing forces this except the orchestrator's own discipline, so it should be a checklist item in the reconciliation step, not assumed |
| Temporal/Airflow/Step-Functions-as-infrastructure | A persistent external engine (durable history / scheduler+DB / AWS service) | **No** — none of these exist in a single-process turn-based loop | N/A — do not adopt |

**Flag per the role brief's mandatory clause:** the one place a compliance failure would be **silent and load-bearing** — i.e., produce a wrong/incomplete reconciliation that still *looks* fine — is exactly the completed-set bookkeeping in the background-dispatch case. If the orchestrator populates its "completed set" by trusting an arriving notification count (rather than directly verifying each unit's terminal artifact), a dropped notification (proven to happen, §6) silently yields `completed_count == N` while one unit never actually reported in — and reconciliation proceeds on N−1 real results plus one phantom. This is not hypothetical; it is the literal bug in #20754/#21165. The fix is cheap (verify by direct read, not by count) but it is easy to skip because "wait for N notifications" reads as correct until you've seen the failure mode.

## Sources (all opened directly before citing, per honesty bar)

- [Temporal `sdk-java` `Promise.java`](https://github.com/temporalio/sdk-java/blob/master/temporal-sdk/src/main/java/io/temporal/workflow/Promise.java) — `allOf()` source, fetched raw
- [Temporal TypeScript child-workflows docs](https://docs.temporal.io/develop/typescript/child-workflows) — `Promise.all()` + `executeChild()` pattern
- [Temporal community forum — waiting for all activities](https://community.temporal.io/t/correct-way-to-wait-for-all-activities-to-complete/12659) — Go `Selector`/counter pattern
- [Astronomer / Airflow trigger rules docs](https://www.astronomer.io/docs/learn/airflow-trigger-rules) — `all_success`/`all_done`/`none_failed_min_one_success` definitions
- [AWS Step Functions — Parallel state, official docs](https://docs.aws.amazon.com/step-functions/latest/dg/state-parallel.html) — full state semantics, Retry/Catch fields
- [CPython `Lib/asyncio/tasks.py`](https://raw.githubusercontent.com/python/cpython/main/Lib/asyncio/tasks.py) — `gather()` source, `nfuts`/`nfinished` mechanism
- [Python `asyncio` docs — Coroutines and Tasks](https://docs.python.org/3/library/asyncio-task.html) — `gather()`/`wait()`/`ALL_COMPLETED` semantics
- [LangGraph repo](https://github.com/langchain-ai/langgraph) (36.9k★, MIT, pushed 2026-07-09) — `Send`/Pregel superstep source files confirmed present via `gh api search/code`
- [CrewAI — Kickoff Crew Asynchronously, official docs](https://docs.crewai.com/en/learn/kickoff-async) — `asyncio.gather` as CrewAI's own recommended fan-in
- [Microsoft Agent Framework — Concurrent workflow tutorial](https://learn.microsoft.com/en-us/agent-framework/tutorials/workflows/simple-concurrent-workflow) — `ConcurrentBuilder`, default aggregator
- [Arafat Tehsin — Agent Orchestration Patterns Part 3](https://arafattehsin.com/blog/agent-orchestration-patterns-part-3/) — `AddFanOutEdge`/`AddFanInEdge` fan-in barrier description
- [Anthropic — Define tools / implement tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/implement-tool-use) — tool_use/tool_result protocol requirement
- [Anthropic — Subagents in the SDK](https://code.claude.com/docs/en/agent-sdk/subagents) — background-by-default (v2.1.198+), "a few tasks per turn" limit
- [Anthropic — Dynamic workflows](https://code.claude.com/docs/en/workflows) — `Workflow` tool, `agent()`/`pipeline()`, 16-concurrent/1000-total agent caps
- [anthropics/claude-code issue #20754](https://github.com/anthropics/claude-code/issues/20754) — background notification loss at N=3, opened via `gh issue view`
- [anthropics/claude-code issue #21165](https://github.com/anthropics/claude-code/issues/21165) — background notification queue only processes first of N=5, opened via `gh issue view`

## Not found / not verified (honesty flags)

- Exact `agent()`/`pipeline()` function signatures and their documented retry/partial-failure semantics inside the Workflow tool — the fetched TypeScript SDK reference excerpt did not contain this section; would need the dedicated Workflow-tool reference page (not reached in this pass).
- AutoGen's own documented fan-out/fan-in primitive — not deeply surveyed; its dominant pattern (round-robin/sequential group chat) is a weaker match for N-way parallel fan-out than LangGraph/CrewAI/Microsoft Agent Framework, so it was deprioritized rather than force-fit.
- Airflow's exact scheduler-internals source (`trigger_rule` evaluation code path in the current `airflow` package) was not opened directly — the docs page's plain-language definitions were used and are official, but the claim about "the scheduler queries persisted per-task state against the DAG-declared task_id set" is inference from Airflow's known architecture (DB-backed TaskInstance model), not a quoted line of scheduler source. Flagging this one inference explicitly as lower-confidence than the rest, which are all direct quotes/source.
