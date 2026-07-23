# Research: detecting two Claude Code CLI processes on the same session_id

Date: 2026-07-02
Mode: D (unblock plan-check KNOWLEDGE gap via new research)
Requested by: loop-team plan-check Verifier, relayed via Oga
Claude Code version checked against: 2.1.196 (matches locally installed `claude --version`)

## Problem recap (not re-litigated — see prompt for full prior evidence)

Need: detect when two `claude` CLI processes are both attached to the same
`session_id` concurrently, from inside a `PreToolUse` hook (the only hook type
already registered with no matcher restriction, firing on every tool call).
Plan-check already disqualified: `session_id` (identical by definition),
`transcript_path` (identical per official docs), `os.getppid()` under the
CURRENT shell-form hook registration (resolves to a transient `sh`, not the
`claude` process), and all documented hook env vars (static, not per-instance).

## Finding 1 — Exec-form hook registration DOES change the process topology (angle #1, CONFIRMED NEW)

Source: https://code.claude.com/docs/en/hooks (fetched 2026-07-02, current docs)

Claude Code hooks support two distinct invocation forms, selected by whether
`args` is present on the hook config:

**Shell form** (no `args` — what's currently registered):
```json
{ "type": "command", "command": "python3 '...'" }
```
Spawns via `sh -c` (or Git Bash/PowerShell on Windows). This is the form
plan-check already tested and correctly disqualified.

**Exec form** (`args` present):
```json
{ "type": "command", "command": "python3", "args": ["$CLAUDE_PROJECT_DIR/.claude/hooks/validate.py", "--strict"] }
```
Verbatim from docs: *"Claude Code resolves `command` as an executable on
`PATH` and spawns it directly with `args` as the argument vector. There is no
shell..."*

**Verdict on the specific question asked ("would `os.getppid()` then
correctly resolve to the actual claude CLI process"): partially yes, but it
does not close the gap.**

- Exec form removes the transient `sh -c` layer, so the hook subprocess's
  direct parent is whatever spawned it in the Claude Code process tree —
  no longer a throwaway shell.
- BUT this does not by itself prove the parent is the *root* `claude` CLI
  process the user is watching. Claude Code's own architecture (see Finding 2)
  now runs background/agent-view sessions under a **per-user supervisor
  process**, and ordinary interactive sessions are still just "the process
  tied to that terminal." Nothing in the hooks docs states hooks are spawned
  as a direct child of the top-level `claude` binary specifically (vs. some
  internal worker/dispatcher layer) — this was not asserted anywhere in the
  fetched docs, so treat "getppid resolves to the exact top-level CLI PID" as
  UNVERIFIED even under exec form.
- Even if it did resolve correctly, `getppid()` alone still can't detect
  "two DIFFERENT processes both have this session_id open" — it only tells
  the hook who its own parent is, once, for this one invocation. Two
  processes with two different real PIDs, both parenting their own hook
  invocations correctly, look identical from inside either hook individually.
  You'd still need a **shared registry** to cross-reference "have I already
  seen a live PID for this session_id from a different process" — which
  brings us to Finding 2, the actual unblock.

So: exec form is real, easy (just add an `args` array to the existing hook
registration), and worth doing regardless as a hardening step — but it is
NOT sufficient alone. It only fixes the "what's my own PID" half of the
problem, not the "is someone else also alive on this session_id" half.

## Finding 2 — `claude agents --json` + `~/.claude/jobs/<id>/state.json` is a genuine first-party liveness primitive (angle #2, CONFIRMED NEW, THE KEY FINDING)

Source: https://code.claude.com/docs/en/agent-view (fetched 2026-07-02, docs
current as of Claude Code v2.1.196; agent view itself is "research preview,"
introduced v2.1.139)

This is exactly the kind of internal-use-first primitive the research
prompt hypothesized might exist. Verbatim from docs:

> `claude agents --json` — Print active sessions as a JSON array and exit:
> every live session, plus background sessions that are still working or
> blocked even when their process has exited. Add `--all` to also include
> completed background sessions. Each entry has `cwd`, `kind`, and
> `startedAt`. Background entries also have `id` ... and `state`: one of
> `working`, `blocked`, `done`, `failed`, or `stopped`. **`pid` and `status`
> are present only while the process is alive** ... `sessionId` and `name`
> appear when set.

State is stored on disk, readable by any local process (a hook is just a
subprocess — no special permission needed to `cat` these files):

| Path | Contents |
|---|---|
| `~/.claude/daemon.log` | Supervisor log |
| `~/.claude/daemon/roster.json` | List of running background sessions, used to reconnect after a restart |
| `~/.claude/jobs/<id>/state.json` | Per-session state shown in agent view |
| `~/.claude/jobs/<id>/tmp/` | Per-session scratch dir |

`claude daemon status` additionally reports the supervisor's own PID,
version, socket directory, and live background-session count.

**This is real, per-process-instance, disk-resident, and includes a `pid`
field gated on actual liveness** — precisely the primitive plan-check said
might not exist. Locally verified `claude --version` = 2.1.196, matching the
docs' currency; `~/.claude/jobs/` doesn't exist on this machine only because
no background/agent-view session has been dispatched here yet (confirmed via
`ls`), which is consistent with the docs, not a contradiction of them.

### The load-bearing caveat that limits this to a partial fix

Verbatim, same page, "Monitor sessions with agent view" section:

> **"Interactive sessions you have open in other terminals don't appear
> until you [background them]."**

And under "How background sessions are hosted":

> "Every session listed in agent view is considered a background session...
> By contrast, **a session started by running `claude` directly is tied to
> that terminal and ends when it closes**, unless you send it to the
> background."

**This directly determines buildability against the actual crash-relaunch
scenario in the problem statement.** The incident was: an ordinary
interactive `claude` process crashed, got relaunched with `--resume
<session-id>`, and the ORIGINAL interactive process (also just a plain
foreground terminal session, not something ever sent to `/bg` or dispatched
from `claude agents`) kept running too. Neither process was ever backgrounded
— so **neither would ever appear in `claude agents --json`, and neither would
have a `~/.claude/jobs/<id>/` directory.** The roster/jobs mechanism only
tracks sessions that went through the background-session supervisor
pathway (`/bg`, `claude --bg`, or dispatched from agent view). A garden-variety
`claude --resume <id>` in a fresh terminal is invisible to this entire system.

**So Finding 2 is real, but it solves a narrower problem than the one in the
ticket.** It would detect duplicates among background/agent-view sessions
sharing a session_id — a real and useful case — but not the reported
incident, which was two plain foreground `claude` processes.

## Finding 3 — Self-daemonizing hooks: documented failure mode, and a documented-but-informal workaround exists; not a sanctioned pattern (angle #3, CONFIRMED, MIXED)

Source: GitHub issue #43123, anthropics/claude-code (fetched 2026-07-02)

Real, reproduced bug: a `SessionStart` hook backgrounding a process
(`caffeinate -s &`) made Claude Code hang completely as of v2.1.87+.
Root cause, per the issue analysis: *"The background process inherits the
parent process's stdin/stdout file descriptors. Since claude-code
communicates with [its host] via stream-json through these pipes, the
background process holding them open caused claude-code to wait
indefinitely."* Symptom: `Session timed out after 649s
(hadFirstResponse=false, reason=no_response)`.

The workaround that resolved it in the thread (informal, from a user, not
from an Anthropic maintainer, and the issue was closed as a duplicate with
no official guidance page found):
```bash
nohup caffeinate -s </dev/null >/dev/null 2>&1 & echo $! > ~/.claude/caffeinate.pid
```
i.e., fully detach stdio (`</dev/null >/dev/null 2>&1`) plus `nohup`, so the
child holds none of the parent's file descriptors open.

**Verdict:** spawning a detached background watcher from a hook (e.g. on
first `SessionStart` or first `PreToolUse`) is *technically possible* if you
scrupulously redirect all three standard file descriptors away from the
parent's pipes — but:
- It is not a documented, sanctioned pattern anywhere in the official hooks
  reference. I found zero mention of "long-lived hook watcher" or
  "persistent hook daemon" as a supported use case in `code.claude.com/docs/en/hooks`.
- The one real-world data point is a *bug report*, not a how-to — the
  takeaway from Anthropic's own architecture is "this hangs the CLI unless
  you get every stdio redirect exactly right," which is fragile-by-design:
  a single missed `2>&1` or a Claude Code version that changes how it wires
  stdio (as v2.1.87 apparently did, per the issue) silently reintroduces
  the hang.
- Related: a live proposal, GitHub issue #39391, argues for a first-party
  "persistent daemon eliminates process spawning overhead (112x faster)"
  precisely because today's hook model is stateless/per-invocation — this is
  an open feature request, not shipped. Similarly, "Chyros" (per
  MindStudio's writeup on a source leak) is reportedly an internal codename
  for a future always-on background daemon, unshipped and unannounced by
  Anthropic as of this research. Neither exists today.
- **This is fighting the framework, not using a documented feature of it.**
  If loop-team builds this, it inherits an undocumented, version-fragile
  contract for a mechanism Anthropic itself doesn't officially expose.

## Finding 4 — Other agent/coding-tool ecosystems (angle #4): no transferable pattern found

Targeted search across Cursor, Windsurf, Cline, Aider, OpenHands for
"duplicate concurrent session / same conversation lock file / two instances"
returned no concrete technical results — only marketing/comparison content.
This is a genuine dead end via web search; I did not fabricate a citation
here. If this angle matters later, it would need direct source-code
inspection of one of these tools (e.g. Aider is open source and Python,
most tractable) rather than search, which is out of scope for this pass.

## Corroborating evidence the underlying bug class is real (not hypothetical)

Search for the exact failure mode turned up a live, matching Anthropic
GitHub issue: **#25295** ("VS Code sessions spontaneously split, swap, and
duplicate between panels"), which includes this evidence block from a user's
`ps aux | grep resume` output:

```
PID 71397 --resume c615748f (started 9:55 PM, active)
PID 78674 --resume c615748f (started 11:07 PM, zombie)
PID 81142 --resume c615748f (started 11:21 PM, zombie)
```

Three separate `claude` processes attached to the same session file,
spawned without user action. The issue was **closed as a duplicate with no
fix, workaround, or mechanism disclosed** — confirmed by direct read of the
issue: "No fix acknowledgment / No workaround suggested / No planned
mechanism disclosed... No mention of file locking, PID tracking, or
session registry." This validates that Anthropic has an open, unresolved
instance of exactly this bug class, and has not (yet) shipped any detection
mechanism — first-party or hook-facing — that covers the ordinary-interactive-
session case.

## Recommendation

**Not cleanly buildable-with-X as a fully automated, hook-only, general
solution — but partially buildable, and here is the precise scope split:**

1. **Ship exec-form hook registration regardless** (Finding 1). It's a
   strict improvement — correct, low-effort, and removes the transient-`sh`
   noise from `getppid()` — but be honest in the spec that it does not by
   itself solve cross-process duplicate detection. Don't oversell it.

2. **Build a `claude agents --json` / `~/.claude/jobs/*/state.json` check as
   a hook-side guard, but scope the spec honestly**: it will catch
   duplicate session_ids *among background/agent-view sessions* (a real
   and probably growing case as agent-view adoption increases) but it is
   **provably blind to the exact incident in the ticket** — two ordinary
   foreground `claude --resume` processes never touch the jobs/roster
   system at all. If loop-team ships this, the spec/fix_plan entry must say
   explicitly "covers backgrounded sessions only, not foreground
   `--resume` duplicates" so nobody mistakes it for a full fix later.

3. **Do not build the self-daemonizing hook pattern (Finding 3) as the
   primary mechanism.** It's real but undocumented, contradicted by a
   confirmed hang bug in Anthropic's own issue tracker, and fragile across
   CLI versions. If pursued at all, treat it as an experimental fallback
   behind a feature flag, never the default path, and pin tested against a
   specific Claude Code version.

4. **The honest bottom line for the actual reported incident (two plain
   foreground `--resume` processes on one session_id): this cannot be
   solved automatically from inside today's hook architecture.** No
   documented Claude Code primitive — hook field, env var, exec-form
   process topology, or the agents/jobs subsystem — exposes cross-process
   liveness for ordinary interactive sessions. Anthropic's own tracker
   (#25295) shows they have the same open problem with no shipped fix.

   **Recommended pragmatic fallback**: a manual, process-level discipline
   rule, not an automated gate — e.g. add to loop-team's operational rules
   (candidate for `fix_plan.md` or a CLAUDE.md rule alongside the existing
   "one session per worktree" memory):
   > *Before running `claude --resume <session-id>`, run
   > `ps aux | grep -- '--resume <session-id>'` (or equivalent) and confirm
   > no other live process already holds it. This is the same discipline
   > already adopted for "one session per worktree" — extend it explicitly
   > to cover crash-relaunch, since that's the scenario that bit us.*

   This mirrors the user's own existing memory
   `feedback_one_session_per_worktree.md`, which already encodes "never run
   two live sessions in one git working tree" as a human-enforced rule
   after a similar incident — the same category of fix, extended to cover
   the resume-after-crash case specifically.

## Sources (all fetched/verified 2026-07-02)

- https://code.claude.com/docs/en/hooks — hook command forms (shell vs exec), env vars, common input fields (`session_id`, `transcript_path`)
- https://code.claude.com/docs/en/sessions — session storage, `--resume` semantics, no lock-file/liveness mechanism documented
- https://code.claude.com/docs/en/agent-view — `claude agents --json` schema, `~/.claude/jobs/<id>/state.json`, `~/.claude/daemon/roster.json`, supervisor architecture, explicit caveat that non-backgrounded interactive sessions are invisible to this system
- https://github.com/anthropics/claude-code/issues/25295 — live confirmed instance of 3 processes on one session_id, closed as duplicate, no fix/mechanism disclosed
- https://github.com/anthropics/claude-code/issues/43123 — SessionStart hook + background process hangs the CLI via stdio pipe inheritance; informal `nohup ... </dev/null >/dev/null 2>&1` workaround, not officially sanctioned
- https://github.com/anthropics/claude-code/issues/39391 — open feature request for a persistent hook daemon (unshipped), confirms today's hook model is stateless-by-design
- Local verification: `claude --version` → `2.1.196` (matches doc currency); `~/.claude/jobs/` absent locally, consistent with docs (no background session ever dispatched on this machine)
- Cursor/Windsurf/Cline/Aider/OpenHands search — no transferable pattern found; genuine dead end, not fabricated
