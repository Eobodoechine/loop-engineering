# Domain brief — H-C1-4 (spec_C1_b2_tests.md, Revision 2): closing the "own-byproduct vs. foreign-intruder" ambiguity in the §E step-6 process rescan

**Mode:** D (domain research for a build). **Requested by:** Oga, per `orchestrator.md`'s DESIGN-gap-type
branching rule (`orchestrator.md:86`), to check whether a better solution exists than the plan-check lens's own
`proposed_fix` for finding H-C1-4 before it is adopted into Revision 3.
**Scope:** this repo (`padsplit-cockpit`, migration worktree
`<HOME>/Claude/loop-worktrees/padsplit-job3-migration-2026-07-14`) plus Vitest's own official docs,
Vitest's GitHub issue tracker, and Node.js's official `child_process` docs — all opened and quoted below, per the
honesty bar. No sub-agents were dispatched; all reads/greps/fetches were done directly.
**Date:** 2026-07-15.

---

## 1. The finding being researched (verbatim, for reference)

From `~/Claude/loop/loop-team/runs/2026-07-14_test-suite-ownership-implementation/continuation/job3_padsplit_migration/plan_check_log_spec_c1.md`, Round 2, `H-C1-4` (DESIGN):

> **broken_assumption:** That the newly-strict rule adopted to close [H-C1-3] ... can reliably distinguish a
> foreign intruder session from this spec's own legitimate byproduct, when §E steps 2 and 8's mandatory triple
> test-suite runs are the step's own highest-risk process-spawning windows and this codebase has documented
> history of its Vitest suite terminating or recursing infinitely...
>
> **proposed_fix (the lens's own, NOT yet adopted):** Require steps 2 and 8's test-suite captures to verify zero
> residual test-runner processes remain (`cwd` in the worktree) as part of completing each capture, so no
> artifact exists for the step-6 rescan to misidentify. The strict cwd-only-is-automatic-abort rule itself stays
> unchanged.

## 2. What I actually read in the repo (grounding facts)

### 2.1 `vitest.config.ts` — the real recursion guard, quoted

`<HOME>/Claude/loop-worktrees/padsplit-job3-migration-2026-07-14/web/vitest.config.ts:5-23`:

```
// When vitest is spawned from *inside* a running vitest worker (e.g. AC12/AC20's
// inner `npx vitest run`), the environment inherits VITEST_WORKER_ID. In that
// nested context we must NOT re-run any test file that itself spawns a nested
// `npx vitest run` ("spawner" tests) — otherwise the spawners re-invoke each
// other and the recursion never terminates. Excluding every spawner in the
// nested run breaks every cycle while leaving them in the top-level run
// (VITEST_WORKER_ID undefined), so the top-level `npx vitest run` still
// exercises them for real.
//
// LOOP-M1 (traversal-completeness): the spawner list below is DISCOVERED from
// disk at config-load time ... rather than hand-maintained. A hand-maintained
// list silently goes stale the moment a new spawner test file is added...
```

Mechanism: `discoverSpawnerTestFiles()` walks `web/tests/`, regex-matches `spawnSync(<cmd>, [...])` call sites
containing both `'vitest'` and `'run'` tokens, and — **only when `VITEST_WORKER_ID` is already set** (i.e. this
run is itself nested inside another vitest run) — excludes every discovered spawner file from that nested run
(`vitest.config.ts:65-67,90-97`). This is what stops infinite recursion; it does **not** touch process
lifecycle/teardown at all — it prevents a spawn-storm from starting, it does not clean up after one.

Pool/teardown-relevant settings actually present (`vitest.config.ts:83-101`):
```
test: {
  environment: 'node',
  globals: true,
  testTimeout: 15000,
  setupFiles: ['dotenv/config'],
  pool: 'threads',
  maxWorkers: 1,
  exclude: [ ...default excludes..., ...nestedExclude ],
}
```
There is **no `teardownTimeout` override** (Vitest default applies — see §3), **no `poolOptions`**, and **no
`forceRerunTriggers`** override in this file.

### 2.2 `package.json` — no external timeout wrapper on the test command

`<HOME>/Claude/loop-worktrees/padsplit-job3-migration-2026-07-14/web/package.json:11`:
```
"test": "vitest run"
```
`npm test` is a bare `vitest run` — nothing wraps it with an OS-level wall-clock kill. If the process never
returns, `npm test` never returns either.

### 2.3 The actual "spawner" tests already use Node's own `timeout` option — real local precedent

Two of the discovered spawner files bound their nested `spawnSync` calls with Node's built-in per-call timeout,
which is exactly the primitive candidate 3 below reuses:

`tests/ai-draft-approve.test.ts:722-731`:
```
const result = spawnSync('npx', ['vitest', 'run', 'tests/inbox-queries-db.test.ts'], {
  cwd: ROOT, encoding: 'utf-8', timeout: 120_000, env: { ...process.env },
})
expect(result.status, `inbox-queries-db.test.ts failed:\n${result.stdout}\n${result.stderr}`).toBe(0)
```
`tests/airbnb-calendar-message-thread.test.ts:402-411` does the same with `timeout: 150_000` across a 3-file
nested run. **No spawner test in this codebase uses `detached: true` or tracks a process group** — confirmed via
`grep -rn "detached\s*:\s*true\|setsid\|process\.kill(-"` across `web/`, zero matches. Positive PID/PGID
attribution (candidates below) would be a genuinely new mechanism here, not an existing pattern being extended.

### 2.4 §E steps 2 and 8, quoted — what a "capture" actually is

`spec_C1_b2_tests.md:456-466` (step 2) and `:540-549` (step 8): each "capture" is three separate CLI invocations
from `web/`: (a) `npx vitest list` (collect-only), (b) `npm test` (→ `vitest run`, full suite), (c) a targeted
`npx vitest run <16 files>` invoked at the top level so `VITEST_WORKER_ID` is unset. Each is persisted as its own
raw runner log (`step2_baseline_*.log` / `step8_postmerge_*.log`). Nothing in the spec text currently specifies
*how* these are invoked (opaque foreground shell command vs. a script that tracks the child's PID) — this is an
open implementation choice Revision 3 will fix, and it materially changes which candidate below is even
implementable (see §5's transfer-condition check).

### 2.5 The step-6 rescan and its stated criterion

`spec_C1_b2_tests.md:359-368` (§C) and `:516-523` (§E step 6): **any** live process with `cwd` inside the
migration worktree is automatic abort-and-escalate, "regardless of open-handle status" — no `lsof` open-handle
carve-out for the worktree (unlike the primary checkout's cwd-only leniency at `:355-358`). This is the rule
H-C1-4 says cannot currently distinguish the spec's own still-draining test process from a real intruder.

## 3. Vitest's own documented mechanisms for process teardown (external sources, all opened)

| Question | Answer | Source |
|---|---|---|
| What's the current default `pool`? | `'forks'` | vitest.dev/config/pool — fetched; "Default: `'forks'`" |
| Why does Vitest recommend `forks` over `threads`? | "While `'forks'` pool is better for compatibility issues ([hanging process](/guide/common-errors#failed-to-terminate-worker) and [segfaults]...), it may be slightly slower than `pool: 'threads'` in larger projects." | vitest.dev/guide/improving-performance — fetched, quoted verbatim |
| What does the "Failed to terminate worker" doc say to do? | Recommends switching from `pool: 'threads'` (this repo's actual setting) to the default `pool: 'forks'`, or `'vmForks'` | vitest.dev/guide/common-errors#failed-to-terminate-worker — fetched |
| What is `teardownTimeout` and its default? | `number`, default **`10000`** (ms) — "Default timeout to wait for close when Vitest shuts down" | vitest.dev/config/teardowntimeout — fetched |
| What is `testTimeout` and its default? | `number`, default `5_000` (Node) / `15_000` (browser) — "Default timeout of a test in milliseconds." This repo overrides it to `15000` (`vitest.config.ts:86`). | vitest.dev/config/testtimeout — fetched |
| Is there a documented mechanism to see *what* is keeping a Vitest process alive? | Yes — a built-in `'hanging-process'` **reporter**: add it alongside `'default'` in `reporters`; it inspects and reports open handles preventing exit (e.g. "There are N handle(s) keeping the process running", with FILEHANDLE/PIPEWRAP-type entries) when Vitest cannot exit cleanly. Documented as resource-intensive, "reserve for debugging." | vitest.dev/guide/reporters (WebSearch summary) + github.com/vitest-dev/vitest discussions #4797 and #9246 (WebSearch summary — **not independently opened**, flagged below) |
| Is orphaned/hanging-process behavior a known, real, currently-open class of bug (not hypothetical)? | Yes. Confirmed open issues (fetched or search-confirmed): **#3077** "Timeout abort can leave process(es) running in the background" — reporter: "Vitest seems to leave the hung Node.js process running with the process peaked at 100% CPU usage" after `^C`; references a fix PR (#5047) but is not a closed/settled non-issue. **#3909** "Flag to allow for graceful exit on hanging process" — reporter describes ~75% of their runs hanging on open handles despite tests passing, asks for an `--ignore-open-handles` escape hatch; closed with no visible maintainer fix in the fetched content. Additional 2026-era issues surfaced by search (titles only, **not opened, not independently verified** — see §6): #8766, #8861, #8968 (v4-specific forks-pool timeout/termination issues), #8564, #8133 ("Terminating Worker Thread"/"Error: Terminating worker thread"), cloudflare/workers-sdk#8837 (vitest-integration processes orphaned for up to 14 days). | github.com/vitest-dev/vitest/issues/3077 (fetched directly) and /issues/3909 (fetched directly); the rest via WebSearch snippet only |

## 4. Node.js's documented process-group mechanism for positive attribution

`nodejs.org/api/child_process.html` (`optionsdetached` section, fetched directly):
> "On non-Windows platforms, if `options.detached` is set to `true`, the child process will be made the leader
> of a new process group and session... Child processes of child processes will not be terminated when
> attempting to kill their parent. This is likely to happen when running a new process in a shell or with the
> use of the `shell` option of `ChildProcess`."
> "`subprocess.pid` — Returns the process identifier (PID) of the child process."

**Honesty flag:** I could **not** locate an official Node.js docs page that itself spells out the
`process.kill(-child.pid)` negative-PID convention for killing an entire process group (two targeted fetches and
one targeted search did not surface it in the fetched content). That specific technique is standard **POSIX
`kill(2)` semantics** ("if pid is negative, ... sig shall be sent to all processes whose process group ID is
equal to the absolute value of pid") applied to a group Node's own `detached: true` documented behavior creates
— I'm citing the POSIX convention plus Node's documented group-leader behavior, not a single Node-docs page that
states the combination outright. Treat this one sub-claim as verified-by-composition, not verified-by-single-quote.

## 5. Candidate designs compared

### Candidate 1 — the lens's own `proposed_fix`, as literally worded

"Require steps 2 and 8's test-suite captures to verify zero residual test-runner processes remain (`cwd` in the
worktree) as part of completing each capture."

- **Closes the false-positive gap?** Partially, and only for one sub-case. It stops the *misidentification
  artifact* from surviving to step 6 for a capture that **finishes** with a slow-exiting residual process — but
  as worded it specifies only a passive *check* ("verify zero remain"), with **no stated remediation**. Read
  literally, a residual process found during this new step-2/8 check has no defined next action — the ambiguity
  it exists to resolve (is this ours, still finishing, or is it foreign?) is simply relocated one step earlier,
  not resolved. Nothing in the fix's text distinguishes "wait a bit longer, it's draining" from "abort now."
- **Closes it if Vitest genuinely hangs/recurses?** **No.** The fix is scoped to run "as part of completing each
  capture" — if the capture's own top-level process never returns (a true recursion storm, or a hang that
  `testTimeout` cannot reach — see note below), the capture never completes, so this check never executes at
  all. This is the direct answer to the task's explicit question: **the spec has no path forward in the
  genuine-hang case under this fix**, because the fix's activation condition presupposes the very thing that
  didn't happen.
  - *Reasoned inference, not a documented Vitest claim (flagging per the honesty bar):* `testTimeout` is
    implemented against the test function's returned/awaited control flow. A test that calls `spawnSync` (a
    **synchronous, blocking** system call) cannot be preempted by `testTimeout` while the child is running,
    because Node's single-threaded event loop cannot service the timer until the blocking call returns. If a
    nested spawner's child process itself hung, `testTimeout: 15000` would not rescue the outer capture. This
    is standard Node.js/JS execution-model reasoning, not something I found stated in the fetched Vitest docs —
    I could not find a Vitest doc page that addresses `spawnSync`-specific timeout preemption, so I'm stating
    this as my own grounded inference, not a citation.
- **Complexity:** Low — one additional check appended to two existing steps.
- **New risk introduced:** Low complexity-wise, but the undefined-remediation gap above is itself a risk: an
  under-specified "verify" step is exactly the kind of ambiguity a Coder or Verifier could resolve
  inconsistently (silently pass through, or hard-abort a healthy run) without spec guidance either way.

### Candidate 2 — positive attribution via spawn-time PID/process-group manifest + explicit kill-and-confirm

Design: when steps 2/8 invoke each of the three captures, spawn it as an explicitly-tracked child (Node
`detached: true`, matching the documented group-leader behavior in §4), record `{pid, pgid, command,
start_time, log_path}` in a small JSON spawn manifest per capture (idiomatically consistent with the spec's
existing manifest pattern, e.g. `b2_tests_preimage_manifest.json`). After the capture's own process exits,
poll (bounded retry, e.g. up to Vitest's own documented `teardownTimeout` default of 10s — grounding the wait
window in a real Vitest-internal shutdown allowance rather than an arbitrary number, §3) for the recorded
PID/PGID to actually vanish from the process table. If still present after that window: explicitly `kill`
(SIGTERM, then SIGKILL after a short grace — the conventional two-stage idiom) and log the action. Step 6's
rescan then only needs to flag a `cwd`-in-worktree process that does **not** match any completed capture's
manifest — turning "verify none remain" (absence-only) into "positively attribute every one we find."

- **Closes the false-positive gap?** Yes, structurally for the completes-but-slow-exit case — a process matching
  a manifest entry is provably C1's own, whether still draining or explicitly killed; anything unmatched is
  unambiguously foreign. This is a real improvement over Candidate 1's passive check.
- **Closes it if Vitest genuinely hangs/recurses?** **Not on its own** — same blind spot as Candidate 1: all of
  this logic is gated on "after the capture's own process exits." A true hang never reaches that point.
- **Complexity:** Moderate — requires the step-2/8 runner to be a script that itself calls `spawn`/`spawnSync`
  with `detached: true` and tracks PID/PGID (not an opaque `npm test > log.txt` shell redirect), plus new
  poll/kill logic. Every primitive is a documented one (§3, §4), not invented.
- **New risk introduced:** A group-kill is broader than a single-PID kill (by design — it's meant to catch
  grandchildren `npx` may spawn) — mitigated by scoping kills strictly to PGIDs recorded in the manifest as
  "ours," never anything discovered ad hoc.

### Candidate 3 (recommended) — Candidate 2 + an outer wall-clock bound on the whole capture, reusing this codebase's own already-precedented `spawnSync({ timeout })` idiom

Everything in Candidate 2, **plus**: wrap the entire top-level capture invocation itself (not just the nested
spawner children, which are already bounded per §2.3) in the same `timeout` option Node's `spawn`/`spawnSync`
already exposes — the exact mechanism `tests/ai-draft-approve.test.ts:725` and
`tests/airbnb-calendar-message-thread.test.ts:410` already use for their own inner nested `npx vitest run`
calls (`timeout: 120_000`/`150_000`, which per Node's documented `options.timeout` behavior sends `killSignal`
— default `SIGTERM` — to the child if it hasn't completed in time). This is not a new idiom for the codebase;
it is the *same* primitive already proven in two of the very spawner tests the recursion guard exists to
handle, applied one level up.

- **Closes the false-positive gap?** Yes, same as Candidate 2.
- **Closes it if Vitest genuinely hangs/recurses?** **Yes — this is the piece Candidates 1 and 2 both lack.**
  The outer bound guarantees the capture reaches a terminal state (clean completion, or a forced, *logged*
  kill-after-timeout) within a known wall-clock window regardless of what happens inside. A genuine recursion
  storm or unreachable hang now produces a distinguishable, actionable log entry ("capture forcibly killed
  after Ns — investigate/escalate") instead of leaving the whole C1 job silently stuck with the step-6 rescan
  never even reached.
- **Complexity:** Moderate-plus — one additional parameter on the same spawn call Candidate 2 already needs.
  Marginal cost over Candidate 2 is small since the tracking infrastructure is already there.
- **New risk introduced:** A timeout that's too short could kill a legitimately slow (not hung) full-suite run
  mid-flight, corrupting the "baseline vs. post-merge" comparison AC-7 depends on. Mitigation: size the bound
  generously off a real measurement (e.g. run `step2_baseline_full_execution` once un-bounded first, or size it
  well above the sum of the codebase's existing spawner-test bounds: 120s + 150s + normal suite time), and log
  the bound used so the Verifier can sanity-check it wasn't the cause of an unexpected "FAIL."
- **Platform constraint (checked directly, not assumed):** verified on this Darwin/macOS host that a shell-level
  `timeout`/`gtimeout` binary is **not present** (`which timeout gtimeout` → both "not found"; `timeout 1 echo
  hi` → "command not found"). This rules out a shell-script wrapper built on the GNU `timeout(1)` coreutil as
  the implementation vehicle. Node's own `spawn`/`spawnSync` `{ timeout }` option, by contrast, is implemented
  inside Node itself (a JS-level timer that calls `kill` on the child) and has **no dependency on an external
  `timeout` binary** — which is exactly why it's the right primitive here and why the codebase's own spawner
  tests already use it rather than shelling out to `timeout`. (I checked this on my own current session's
  Darwin host, not the migration worktree's host directly — flagging as an inference-by-same-OS-family, not a
  direct check of that exact machine.)

### Direct answer to the task's explicit sub-question

> "does it also close it if Vitest genuinely hangs/recurses ... does it retry-and-kill, or does the spec still
> have no path forward?"

**Candidate 1 (as-is): no path forward** — the check is scoped to run only after the capture completes, so a
genuine hang means the check-that-would-resolve-the-ambiguity never runs at all, and nothing else in the spec
currently bounds the capture's own runtime. **Candidate 3: retry-and-kill, with a hard outer bound** — the
capture is guaranteed to terminate (cleanly or forcibly) within a known window, and every kill action is logged,
giving the Verifier and step-6 rescan a concrete trail to reason from instead of an open-ended stall.

## 6. Recommendation

**Do not adopt the lens's `proposed_fix` as-is.** Adopt **Candidate 3**: spawn each of steps 2/8's three
captures with `detached: true` and a bounded `timeout` (Node's own documented `child_process` options — §4,
§2.3), record `{pid, pgid, command, timeout_ms}` per capture in a small spawn manifest (same idiom as the
spec's existing preimage manifest), and after each capture reaches a terminal state (clean exit or
forced-kill-after-timeout, both logged) confirm via the recorded PGID that nothing remains — only *then* is the
capture "complete." Step 6's rescan then treats any `cwd`-in-worktree process **not** attributable to a
manifest entry as automatic grounds for abort-and-escalate (the strict rule stays exactly as strict as H-C1-3
made it — this only adds a positive-attribution filter in front of it, per H-C1-4's own instruction that "the
strict cwd-only-is-automatic-abort rule itself stays unchanged"). This mirrors the shape of the
`H-REVIEW-COMMIT-1` precedent cited in the dispatch: the lens's single proposed_fix only reduces the
misattribution surface for one sub-case (completes-but-slow); Candidate 3 zeroes both the false-positive
problem (via positive attribution) *and* the undefined-genuine-hang problem (via the outer bound) that the
lens's fix leaves completely open — using only primitives already documented (Vitest's `teardownTimeout`,
Node's `detached`/`timeout` options) or already precedented in this exact codebase (the spawner tests' own
`spawnSync({ timeout })` calls), not invented mechanism.

**Secondary, non-blocking observation for Revision 3's drafting, not a required change:** this repo's
`vitest.config.ts:88` sets `pool: 'threads'`, which Vitest's own docs identify as the pool type more prone to
exactly the "hanging process"/"Failed to terminate worker" class of bug the docs recommend `pool: 'forks'`
(the current default) to avoid (§3). Changing the suite's pool is out of scope for spec C1 (C1's scope is the
16 test files only, per §D.2's exclusion of the 6 C2 production/config files), so this is not something
Revision 3 should attempt — but it is worth recording as a `fix_plan.md`-style follow-up candidate for whichever
spec eventually owns `vitest.config.ts`, since it's a plausible root-cause contributor to the "documented history
of terminating or recursing infinitely" the recursion guard's own comment references.

## 7. `not_found` / honesty flags (explicit)

- **Not independently opened:** vitest.dev/guide/reporters (the `hanging-process` reporter's own doc page), and
  GitHub discussions #4797 and #9246 — summarized only from WebSearch's own synthesis, not fetched and quoted
  directly. The reporter's *existence* and general behavior is corroborated by two independent search results
  plus a direct-fetched cross-reference from `common-errors#failed-to-terminate-worker`, so I'm treating its
  existence as reasonably confirmed, but I have not personally read its full doc page or confirmed its exact
  current-version config syntax — a Coder implementing "add the hanging-process reporter" should verify the
  exact config key against `vitest.dev/guide/reporters` directly before using it.
- **Not independently opened:** GitHub issues #8766, #8861, #8968, #8564, #8133, and
  cloudflare/workers-sdk#8837 — titles and WebSearch snippet summaries only, not fetched. Listed in §3 as
  corroborating evidence that hanging/orphaned-process bugs are a live, recurring class of Vitest issue across
  versions including v4 (this repo runs `vitest ^4.1.9` per `package.json:41`), **not** as individually verified
  citations. Do not cite these issue numbers as confirmed facts beyond "search results surfaced these titles."
  connected to hanging/orphan-process reports."
- **Not verified:** the exact `process.kill(-pid)` negative-PID group-kill line inside official Node.js docs
  (§4) — composed from a fetched Node docs quote (`detached` → process-group-leader) plus general POSIX
  `kill(2)` semantics, not a single fetched Node-docs sentence stating the combination.
- **Not checked directly:** whether `timeout`/`gtimeout` is absent on the actual migration-worktree host
  (`<HOME>/Claude/loop-worktrees/padsplit-job3-migration-2026-07-14`) — I checked my own current
  session's Darwin host only (same OS family, but not literally the same machine/shell environment) and
  inferred the same absence there.
- **Not found anywhere:** a Vitest doc or issue stating that `testTimeout` *can* preempt a test blocked inside a
  synchronous `spawnSync` call — I looked for this specifically (§5, Candidate 1's evaluation) and did not find
  it either confirmed or denied in Vitest's own docs; my conclusion that it *cannot* is reasoned from Node.js's
  documented single-threaded event-loop execution model, not a Vitest-specific citation.

## 8. Transfer-condition check (per `roles/researcher.md` guardrails — required for every borrowed mechanism)

| Mechanism | Requires | Does spec_C1's context satisfy it? | Enforcement |
|---|---|---|---|
| `detached: true` + PGID tracking (Node `child_process`) | The capture must be launched via a Node-level `spawn`/`spawnSync` call the Coder controls (not an opaque foreground shell redirect) | **Not yet** — §2.4 notes the spec text does not currently specify the invocation mechanism; Revision 3 must specify "invoke via a small tracked-spawn script," or this mechanism has nothing to attach to | Structural once specified: the manifest either exists with real PID/PGID data or it doesn't — a Coder can't silently skip it without an empty/missing manifest being independently checkable by the Verifier |
| `timeout` option on the outer capture spawn | Same — Node-level spawn call, not shell `timeout(1)` (confirmed absent on this Darwin host, §5 Candidate 3) | Same gap as above — needs Revision 3 to mandate the invocation mechanism | Structural: Node enforces the timeout itself once the option is set; not dependent on a participant remembering to check a clock |
| `teardownTimeout`-sized poll window | Reading Vitest's own configured/default value, not re-deriving an arbitrary number | Satisfied — `teardownTimeout` is unset in `vitest.config.ts`, so Vitest's documented default (10000ms, §3) applies and can be read directly from the docs without new config | Structural (a fixed, documented constant) |
| `hanging-process` reporter (secondary/optional diagnostic) | Adding `'hanging-process'` to `reporters` in `vitest.config.ts` | vitest.config.ts is out of C1's scope (§D.2) — **not adoptable within C1 itself**; flagged in §6 as a separate follow-up candidate, not part of the Candidate 3 recommendation | N/A — explicitly excluded from this spec's adoption surface |

**Compliance-failure-mode flag:** none of Candidate 3's core pieces are instructional-only in the sense the
guardrail warns about (a participant "should" do something with no structural check) — the manifest's presence
and the logged kill/timeout events are artifacts a Verifier can mechanically confirm exist (or don't), same as
the spec's other raw-log requirements. The one genuinely instructional residual is sizing the timeout bound
generously enough not to kill a legitimately slow full run (§5, Candidate 3's risk note) — that's a judgment
call Revision 3's drafter must make explicitly and record, not something a hook can verify is "correct," only
that a value was chosen and logged.

---

**Saved to:** `<HOME>/Claude/loop/research/vitest-process-teardown-attribution-h-c1-4-2026-07-15.md`
