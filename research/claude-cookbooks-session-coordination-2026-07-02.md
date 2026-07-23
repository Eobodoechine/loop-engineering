# Session-coordination / concurrent-writer research for loop-team (2026-07-02)

**Trigger:** Mid-session, the Claude Code process running an Oga (loop-team orchestrator)
conversation crashed/restarted and auto-resumed against the SAME session ID as a separate,
already-running process. Both threads acted as Oga on the identical conversation history and
both made real file edits to the same git working tree (`~/Claude/loop`) concurrently for
~18+ minutes, undetected until `git status` showed unexplained files. This research asks: does
Anthropic's own tooling/docs address this failure mode, or the general version of it
(concurrent writers to a shared resource)?

**Method:** Direct fetch of the real `docs.claude.com`/`platform.claude.com` Agent SDK pages
(`sessions`, `session-storage`, `hosting`, `managed-agents/multi-agent`) plus the real
`github.com/anthropics/claude-cookbooks` repo tree via the GitHub API (not filename-guessing —
confirmed root listing) and a real, closed-source GitHub issue on Claude Code's own SQLite
lock contention. All quotes below are verbatim from the fetched pages. This is a companion to,
and deliberately does NOT re-surface, `claude-cookbooks-review-2026-07-02.md` (the prior
5-cluster pass) — see "Relationship to prior pass" at the end for exactly what's new here.

---

## Question 1: Does anything address "session resumed as a NEW process while the original might still be running"?

**Short answer: No. This is explicitly out of scope for every piece of first-party material found.**
Nothing in claude-cookbooks or the Agent SDK docs documents detecting, preventing, or warning
about two processes resuming/writing to the same session concurrently. Below is the exact
evidence for that conclusion, not an inference from silence — I read the specific pages most
likely to cover it and none do.

### `docs.claude.com/en/agent-sdk/sessions` (fetched verbatim, full page)

This is the canonical resume/continue/fork reference. It describes:
- `continue` (most recent session in cwd) and `resume` (specific session ID) as ways to "pick up
  an existing session and add to it."
- `fork` as branching into a **new** session ID, explicitly to avoid one actor's writes affecting
  another: *"The fork gets its own session ID; the original's ID and history stay unchanged."*
- The only concurrency-adjacent tip is about *mismatched `cwd`* causing a resume to return a
  fresh session instead of history — a routing bug, not a duplicate-writer scenario.
- Nowhere does the page discuss what happens if two processes call `resume` with the same
  session ID at the same time. There is no session lock, no "already active" check, no lease/TTL
  concept, no warning.

The **fork** mechanism is the closest first-party primitive to "avoid two writers on one
session" — but it is opt-in and requires the caller to *know in advance* it wants a second,
independent branch. It's a tool for intentional divergence (a human choosing "try a different
approach"), not a safeguard against *accidental* duplicate resumption of the *same* ID. It does
nothing to prevent or detect what actually happened to loop-team (both processes calling
`resume` with the *same* ID, not forking).

### `docs.claude.com/en/agent-sdk/hosting` (fetched verbatim, full page)

This is Anthropic's own production-deployment guidance — the most likely place to find a
"don't double-resume" warning, since it explicitly discusses horizontal scaling and multiple
containers. It does not contain one. Instead:

- *"Horizontal-scale routing depends on your pattern. For long-running sessions, where
  containers hold many sessions, run a pool of containers behind a load balancer and **pin each
  session to one container using consistent hashing on `sessionId`**. A pinned session keeps
  hitting the same container, and therefore the same running subprocess, until it is evicted or
  the container restarts."**

  This is the load-balancer-level answer to "how do you avoid two processes touching one
  session": route by `sessionId` so structurally only one container ever holds a given session
  at a time. It is a *routing convention*, not a lock — nothing stops a misconfigured router (or,
  as in loop-team's case, a crash-and-respawn on the same machine bypassing any router
  entirely) from violating the invariant. The page never claims the SDK itself enforces
  single-ownership; it only says *you* should build your infrastructure that way.

- The **Known limitations** table on that page explicitly lists gaps Anthropic acknowledges and
  leaves to the caller: no top-level session timeout, memory growth over long sessions, no
  per-subagent wall-clock deadline. A duplicate-active-writer scenario is not in this list at
  all — not flagged as solved, not flagged as a known gap. It's simply not modeled.

- **One-agent-one-subprocess is stated as the unit of concurrency**: *"One agent session maps to
  one subprocess. Running N concurrent sessions means N subprocesses, each with its own process
  tree and transcript file."* The document's mental model assumes a 1:1 session:subprocess
  mapping is maintained by the *caller's* orchestration layer (consistent hashing, container
  pinning). It has no built-in mechanism to detect or reject a second subprocess claiming the
  same session ID — that's exactly the gap loop-team hit when the crash/restart produced two
  subprocesses against the same session with no router in between to enforce pinning.

### `docs.claude.com/en/agent-sdk/session-storage` (fetched verbatim, full page)

This page defines the `SessionStore` interface (S3/Redis/Postgres adapters for cross-host
resume) and is the most mechanism-rich page on session persistence. Still nothing about
concurrent-writer detection:

- The dual-write model is explicit: *"The store is a mirror, not a replacement. The Claude Code
  subprocess always writes to local disk first; the SDK then forwards each batch to `append()`."*
  This confirms there is exactly one process's local disk considered authoritative per session at
  the SDK's own design level — the model has no concept of two authoritative local-disk copies
  being reconciled, because the design assumes there's only ever one.
- Mirror writes are described as **best-effort and retried up to 3 times total**, deduplicated by
  `entry.uuid` on the *adapter's* side, not the SDK's: *"Because a retried batch can re-deliver
  entries that already landed, deduplicate by `entry.uuid` in your `append()` implementation."*
  This is a note about idempotent retry of a *single* writer's own batches, not about
  reconciling two independent writers' divergent batches. If two processes were both mirroring to
  the same store under the same session key, both would `append()` and the store would end up
  with an interleaved/undefined-order combination of both processes' entries — the doc doesn't
  address this because it assumes one writer.
- `forkSession` gets its own session ID by design specifically *"so an adapter-level copy or
  `CopyObject` shortcut would produce a transcript that still references the old session ID"* —
  again, this is about intentional branching, not accidental duplication.

**Conclusion for Question 1:** Confirmed absent. I searched the three most likely pages
(sessions, hosting, session-storage) plus web search across `docs.claude.com`/`platform.claude.com`
and the cookbooks repo, and found no session-locking primitive, no "already active" check, no
heartbeat/liveness signal for detecting a live duplicate, and no explicit warning about the
failure mode loop-team hit. The SDK's implicit assumption throughout is **one live process per
session ID**, enforced entirely by the caller's own infrastructure discipline (consistent-hash
routing in hosting.md) — never by the SDK or CLI itself. This is a real gap in Anthropic's own
material relative to loop-team's actual incident, not a case of the right pattern existing under
an unexpected name.

---

## Question 2: General concurrent-write / multi-agent coordination on a shared filesystem — anything transferable?

Two real, load-bearing patterns turned up. One is close to directly applicable; one is a
documented Claude Code bug+fix that is the single most relevant artifact this research found.

### 2a. SQLite lock contention in Claude Code's own local session store — directly relevant precedent

**Source:** `github.com/anthropics/claude-code/issues/14124`, "[BUG] Parallel subagent execution
freezes due to SQLite lock contention in `__store.db`" (verbatim quotes from the fetched issue):

> `PRAGMA journal_mode;` — Returns: `delete`
> `PRAGMA busy_timeout;` — Returns: `0`

> When 3+ subagents run in parallel: All agents simultaneously try to read/write to `__store.db`.
> DELETE journal mode requires EXCLUSIVE lock for writes. `busy_timeout=0` causes instant
> `SQLITE_BUSY` errors. Claude Code likely retries in a tight loop → apparent freeze.

Proposed/verified fix, quoted from the issue:

```javascript
db.pragma('journal_mode = WAL');
db.pragma('busy_timeout = 5000');
```

> Result: 3 parallel Explore agents completed without freezing.

This is Anthropic's *own* infrastructure (Claude Code's local `~/.claude/__store.db`) hitting
almost exactly loop-team's failure class: multiple processes/agents writing to a shared local
state store with no serialization discipline, silently corrupting or freezing instead of failing
loud. Two transferable lessons for loop-team, independent of the exact DB technology:

1. **Default SQLite settings do not give you safe concurrent multi-writer behavior** — `DELETE`
   journal mode + zero busy-timeout means the *first* symptom of concurrent writers is often a
   silent freeze/hang, not a clean error. If loop-team or any tooling around it ever moves state
   tracking (fix_plan, decision logs, run status) into SQLite instead of flat files, this is a
   concrete pre-flight check: verify `journal_mode=WAL` and a nonzero `busy_timeout` before
   assuming concurrent-safe behavior.
2. **The bug was discoverable only via direct PRAGMA inspection**, not via application-level
   symptoms — the "freeze" looked like a hang, and the diagnosis required going around the
   application layer to interrogate the database directly. This mirrors loop-team's own
   discovery of the duplicate-session incident: `git status` (a layer *below* the conversation)
   surfaced the anomaly, not anything inside either Oga thread's own turn-taking. This is an
   argument for periodically probing ground-truth state (git status/log, file mtimes, process
   list) as a structural habit, not just when something already looks wrong — already
   partially captured by the "audit git after Coder" and "diagnose beyond doubt" memory rules,
   but this generalizes it to *self*-audits, not just post-Coder audits.

### 2b. Managed Agents' thread model — explicit single-coordinator ownership, not applicable as-is

**Source:** `platform.claude.com/docs/en/managed-agents/multi-agent` (fetched verbatim, full
page). This is Anthropic's actual multi-agent-on-shared-filesystem product surface, so it's the
right place to look for a coordination pattern — but its answer is architectural exclusion of
the problem, not a solved instance of it:

> All agents share the same sandbox, filesystem, and vault credentials, but each agent runs in
> its own **session thread**, a context-isolated event stream with its own conversation history.

> A maximum of 25 concurrent threads are supported. The coordinator can call multiple copies of a
> single agent in the roster, creating multiple threads associated with one `agent`.

Concurrency here is handled by **giving every sub-agent its own isolated conversation thread**
under **one coordinator that is the sole thing driving delegation** — there is exactly one
decision-maker (the coordinator/primary thread) at all times; sub-agents never independently
decide to act on the shared filesystem without being dispatched. This is structurally the same
shape loop-team already uses (Oga is the sole dispatcher; Coder/Verifier/Researcher never
self-dispatch each other) — it doesn't add a new mechanism, but it does confirm by construction
that Anthropic's own multi-agent product treats "exactly one active orchestrator per
session/sandbox" as foundational, not optional. The duplicate-Oga incident is a violation of
that same invariant (two coordinators, same sandbox, same session) — which the Managed Agents
architecture prevents structurally (session creation is 1:1 with a coordinator; there's no API
path to attach a second coordinator to a running session) rather than by any lock loop-team
could borrow. **This is a design-shape confirmation, not a reusable code pattern** — Managed
Agents' isolation is enforced by Anthropic's own control plane (single `sessions.create` call
owns the coordinator), which loop-team's local-process model has no equivalent of.

### 2c. Explicit idempotent-retry-by-UUID as the SDK's only concurrency-safety primitive

Already quoted in 2a's sibling (session-storage doc, Question 1): `entry.uuid`-keyed
deduplication for retried mirror-writes is the *only* concurrency-safety mechanism anywhere in
the fetched SDK material, and it's scoped narrowly to "the same writer's own retried batch,"
not "two independent writers." No git-based coordination convention, no claim-file/lock-file
pattern, no heartbeat/liveness check exists anywhere in the fetched material. This was searched
for directly (Question 2's literal ask) and not found — stated here as a clean negative rather
than stretched.

**Conclusion for Question 2:** Real, transferable, but partial. The SQLite issue (2a) is a
genuine "shared local state store, concurrent writers, silent-failure-not-loud-failure" precedent
worth citing directly. The Managed Agents thread model (2b) confirms Anthropic's own products
treat single-coordinator-ownership as a hard invariant, which validates loop-team's existing
Oga-is-sole-dispatcher design retroactively, but does not hand loop-team a ready-made
duplicate-process guard — that has to be built locally (see recommendation below).

---

## Question 3: Anything else newly relevant — fresh eyes on the same repo + directories the prior pass never touched

**Real repo root, confirmed via GitHub API `contents/` call** (not WebFetch's lossy rendering —
cross-checked both and they agree): `.claude/`, `.github/`, `anthropic_cookbook/`,
`capabilities/`, `claude_agent_sdk/`, `coding/`, `evals/`, `extended_thinking/`,
`fable_5_fallback_billing/`, `finetuning/`, `images/`, `managed_agents/`, `misc/`, `multimodal/`,
`observability/`, `patterns/`, `scripts/`, `skills/`, `tests/`, `third_party/`,
`tool_evaluation/`, `tool_use/`.

Cross-referencing against the prior dossier's own "Not read (scoped out)" line (`capabilities/*`,
`multimodal/*`, `third_party/*`, `finetuning/*`, `skills/*`), the directories **neither pass has
opened** are: `.claude/` (partially — prior pass read the dogfooding CI config, not full
contents), `.github/`, `anthropic_cookbook/`, `coding/`, `fable_5_fallback_billing/`, `images/`,
`observability/`, `scripts/`, `tests/`.

I spot-checked the ones with plausible orchestration/coordination relevance:

- **`coding/`** — contains exactly one notebook, `prompting_for_frontend_aesthetics.ipynb` (14
  cells). Confirmed via direct fetch: it's a prompting style guide for frontend visual output
  (typography/color/motion guidance for Claude-generated UIs), unrelated to orchestration or
  concurrency. Not relevant to loop-team.
- **`observability/`** — one file, `usage_cost_api.ipynb`. Cost/usage API tutorial, not
  concurrency-related. (Loop-team's existing cost-tracking practice is already ahead of what a
  single-notebook usage-API tutorial would add.)
- **`fable_5_fallback_billing/`** — one file, `guide.ipynb`. Billing-fallback guide for a
  specific product surface (Fable), not orchestration-relevant.
- **`anthropic_cookbook/`** — a single `__init__.py`, i.e., a Python package marker, not content.
- **`registry.yaml`** (repo root, not a directory but worth checking as a structural index) — this
  is the repo's own categorized index of every notebook with title/description/path/category.
  Skimming it confirmed the prior pass's clusters cover the categories that matter
  (`Claude Managed Agents`, `Tools`, `Agent Patterns`, `Evals`, `Integrations`, `Observability`)
  and did not surface an uncovered high-value notebook — the entries visible (data analyst agent,
  Slack data bot, SRE incident responder, threat intel enrichment, knowledge graph construction,
  crop tool, PTC) are either already-covered categories or already-scoped-out categories
  (`capabilities/knowledge_graph`, `multimodal/crop_tool`) per the prior dossier's explicit
  exclusion list.

**Conclusion for Question 3:** No new HIGH-value cluster was missed. The prior pass's scoping
was accurate — the genuinely thin, single-notebook directories (`coding/`, `observability/`,
`fable_5_fallback_billing/`, `anthropic_cookbook/`) don't hide anything orchestration-relevant,
and `registry.yaml`'s full categorized index doesn't surface an unscoped notebook that belongs in
the HIGH tier. `.github/`, `scripts/`, `tests/`, and `images/` are repo-hygiene/CI-plumbing
directories, already partially represented by the prior pass's "dogfooding CI" cluster
(`.claude/` + `.github/workflows/*`) and not worth a further dedicated pass absent a specific
question about them.

---

## Recommendation for loop-team hardening (concrete, scoped to what's actually evidenced above)

Since no first-party mechanism exists to detect or prevent a duplicate-process-on-same-session
(Question 1's clean negative), any fix has to be **built into loop-team's own process**, not
borrowed from the SDK. Based on the two real patterns found (2a's PRAGMA-inspection habit, 2b's
single-coordinator invariant), the smallest concrete addition:

1. **A lightweight local claim file, checked at the start of every Oga turn, not just at
   session start.** E.g. `~/Claude/loop/.oga-lock` containing `{pid, session_id, hostname,
   started_at}`, written on Oga's first turn and re-touched (mtime bump) on every subsequent
   turn as a heartbeat. Before taking any state-modifying action (file write, git operation),
   Oga checks: does a lock file exist, is its PID alive (`kill -0`), and is its heartbeat fresh
   (say, <5 min old)? If yes and it's not *this* process's own PID, halt and surface the
   conflict instead of proceeding — this directly targets the exact failure that happened
   (nothing checked liveness before both threads proceeded). This is a bespoke pattern, not
   sourced from claude-cookbooks — flagging it as an original recommendation, not a "found in
   the source" claim, per the no-fabrication instruction.
2. **Treat `git status`/`git log` as a structural pre-flight check, not just a post-Coder audit.**
   Already partially covered by memory `feedback_audit_git_after_coder.md`, but this incident
   shows the same discipline needs to run *before* Oga's own actions too, mirroring how the
   SQLite bug (2a) was only caught by inspecting ground-truth state directly rather than trusting
   the application layer's self-report.
3. Do **not** invest in adopting `SessionStore`/multi-host patterns for this — they solve a
   different problem (cross-host resume), not same-host duplicate-process detection, and would
   add real complexity for a scenario (crash-auto-resume racing a still-alive process) that a
   simple local heartbeat file fully covers.

None of items 1-3 above are drawn from the cookbook or SDK docs — they are original synthesis in
response to the confirmed absence of a first-party mechanism. Flagged explicitly as such.

---

## Relationship to prior pass (`claude-cookbooks-review-2026-07-02.md`)

No overlap. That dossier's 16 candidates (6 HIGH) are about compaction, tool-denylisting,
independent re-verification, silent-throttle detection, retry-memory, and verifier-rubric
phrasing — all single-session-agent-quality concerns. This pass is about a different axis
entirely (multi-process/duplicate-session safety) that the prior pass's scope never touched,
per its own "not read" disclosure. The one point of contact: prior-pass item 2
(`disallowed_tools` as SDK-level denylist) and this pass's finding that Managed Agents enforces
single-coordinator-ownership at the control-plane level are both instances of the same general
principle ("enforce isolation at the primitive layer, not the prompt layer") — worth noting if
loop-team ever writes a unifying "isolation guarantees" section, but they are not duplicate
findings.
