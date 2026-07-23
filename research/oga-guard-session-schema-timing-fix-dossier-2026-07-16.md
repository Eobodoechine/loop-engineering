# Dossier: session-schema + timing-race fix for H-OGAGUARD-EXACTWORKER-AGENTID-NAMESPACE-MISMATCH-1 — fresh re-derivations beyond the verifier's report

**Mode:** B (Coder-unblock), spec-authoring stage. **Date:** 2026-07-16.

**Scope of this dossier.** This is explicitly NOT a re-investigation of the confirmed diagnosis. A
prior Researcher dispatch proposed a re-diagnosis of `H-OGAGUARD-EXACTWORKER-AGENTID-NAMESPACE-
MISMATCH-1` (`fix_plan.md:9470-9558`), and a separate verifier sub-agent independently re-derived
every quantitative claim in that diagnosis against real evidence moments before this pass began (full
verbatim verifier report is quoted in the dispatch that produced this dossier and this dossier's
companion spec). This document records ONLY what THIS pass — the spec-authoring pass — independently
re-derived or newly discovered on top of that already-confirmed diagnosis, per the explicit
instruction to re-check line numbers fresh rather than trust them blindly, and per this project's
"always save research" convention (`~/.claude/projects/-Users-eobodoechine/memory/
feedback_always_save_research.md`).

**Consumed by:** `loop-team/runs/2026-07-16_oga-guard-session-schema-timing-fix/specs/spec.md`
(Sections B, C, D, E, and I).

## 1. Line numbers re-derived fresh — zero drift from the verifier's citations

Read `hooks/pre_tool_use_oga_guard.py` in full (972 lines) directly, not via grep-only spot checks:
- `_event_session_id()`: **lines 719-725**, confirmed exact. Checks only `e.get("session_id")` (720)
  and `message.get("session_id")` (723) — snake_case only. Direct `grep -c sessionId
  hooks/pre_tool_use_oga_guard.py` on the current file returns 0 — zero camelCase `sessionId`
  anywhere in the file, confirmed fresh.
- `payload_session_id`: line 828. `_same_session()`: lines 831-832. `active_dispatches`: lines
  835-838.
- `dispatched` collector (populates `dispatched[tid]["session_id"]` via `_event_session_id(e)`):
  lines 750-768, the assignment itself at line 765.
- Item-1b AGENT_ID_RE-based `agent_id` population (the launch-ack scrape): lines 770-780.
- Retirement scan: lines 787-794. `_is_stale()`: lines 803-820. `in_flight_ids`: lines 823-826.
- `_canonical_agent_identity` / `_record_key`: lines 841-846. `_resolve_agent_id`: lines 849-856.
  `_resolve_task_or_dispatch_id`: lines 859-867 (see Finding 5 below — this function turns out to be
  directly reusable for the new design, not just background reading).
- Top-level identity resolution branch (`top_agent_id = data.get("agent_id")` and the
  `identity_error` assignment for a failing match): lines 872-895.
- Additional-identity-fields cross-check (`top_agent_id` vs `top_task_id`/`top_dispatch_id`
  agreement): lines 897-918.
- Final `WRITE_CAPABLE_ROLES` gate: lines 920-925.
- Deny message construction, including the `H-GUARD-4 / H-LT6` citation (line 964) and the
  "advisory role-collapse check, not a security boundary... bypassed via Bash" sentence (lines
  967-968): lines 949-972.
- `git diff -- hooks/pre_tool_use_oga_guard.py` against `HEAD` is empty (confirmed via
  `git diff --stat`, zero output) — the production file is byte-identical to the committed state at
  `ff919679a576881d8fb45bbb5219756f1644860d` (branch `fix/oga-guard-codex-worker-identity`); no drift
  since the verifier's own check.

`hooks/test_pre_tool_use_oga_guard.py`'s fixture-tautology region: `_identity_launch_ack` (lines
2512-2517), `_identity_dispatch_events` (lines 2520-2550, the `session_id` assignments specifically
at lines 2542 and 2544), `TestExactWorkerIdentityGuard` (lines 2564-2672, 6 test methods) — all
confirmed exact via direct read.

## 2. Operational-safety drift measured live, between the verifier's check and this pass

The shared tree (`~/Claude/loop`, branch `fix/oga-guard-codex-worker-identity`) is not a static
snapshot; it moved measurably during the few minutes between the verifier's pass and this one:

| Measurement | Verifier's pass | This pass (fresh) |
|---|---|---|
| `git diff --stat -- hooks/test_pre_tool_use_oga_guard.py` | 246 insertions, 0 deletions | **782 insertions, 0 deletions** |
| `python3 -m pytest hooks/test_pre_tool_use_oga_guard.py -q` (shared tree) | 119 passed, 4 failed, 12.95s | **134 passed, 6 failed, 40.73s** |

The two NEW failures beyond the verifier's report are in a class the verifier's report never
mentions: `TestCodexExactWorkerIdentityGuard::test_ac1_subagent_write_capable_task_names_allow` and
`::test_ac10_first_session_meta_event_governs_bidirectionally`. Confirmed by grepping the uncommitted
diff for added class/method names: the new `TestCodexExactWorkerIdentityGuard` class has **16**
methods, named `test_ac1_...` through `test_ac13_...`, mapping directly onto the SIBLING spec's own
Section E AC1-AC13 table (`loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md`).
This is not unrelated WIP — it is that sibling spec's OWN test scaffolding, landing uncommitted in
this exact shared tree, concurrently with this dispatch, even though the sibling spec.md's own header
states "no code changed yet" (true for `pre_tool_use_oga_guard.py` itself, confirmed — but its
test-scaffolding has evidently begun). A `TestDispatchRoleUnaffectedByCodexTaskNameMention` class
(matching the sibling spec's AC6 regression concern) is also new. The remaining new-since-verifier
failures (`TestCodexSpawnAgentV2PreToolUseParity`, 4 methods) plus a
`TestDispatchViewNormalizedOutputGateInteraction` class match the verifier's own identification of
bleed-in from the separate `fix/codex-multiagent-v2-shape-staleness` effort (confirmed present as its
own worktree: `<HOME>/Claude/loop-worktrees/codex-multiagent-v2-shape-staleness`, branch
tip `4ace7a9` per `git worktree list`).

Live Codex process reconfirmed fresh (new PID, later timestamp than the verifier's check): PID 2849
(`codex sandbox -c shell_environment_policy.inherit=...`) paired with PID 2866
(`codex app-server --listen stdio://`), both confirmed bound via `--working-dir
<HOME>/Claude/loop` (via `ps -p 2849 -o command=`, filtered for the `--working-dir`
token). A separate Codex pair (PID 21324/21337) is bound to an unrelated directory
(`<HOME>/Documents/Codex/2026-07-13/f`) and is not a concern for this repo.
`git worktree list` reconfirmed 16 active worktrees, matching the verifier's count.

**Implication:** the case for implementing in a fresh, isolated worktree is even stronger than the
verifier's own snapshot suggested — the shared tree is under continuous, uncoordinated modification,
not a one-time contamination event.

## 3. A genuinely clean, committed-only test baseline (new measurement)

`git status --porcelain` shows every uncommitted change under `hooks/` is confined to **test files**
(`test_codex_parity_gates.py`, `test_codex_transcript_adapter.py`, `test_loop_stop_guard.py`,
`test_pre_tool_use_oga_guard.py`, `test_subagent_stop_gate.py`) — zero production `.py` modules under
`hooks/` (including `pre_tool_use_oga_guard.py` itself) are modified. This makes it possible to
isolate a true committed baseline without needing to create a worktree:

1. Copied `hooks/` to a scratch directory (`/private/tmp/claude-501/.../scratchpad/clean-baseline-check`).
2. Overwrote only `test_pre_tool_use_oga_guard.py` with `git show
   HEAD:hooks/test_pre_tool_use_oga_guard.py` (all other files in the copy are already clean/committed,
   so no further overwrite was needed).
3. Confirmed the extracted file has **zero** occurrences of `TestCodexExactWorkerIdentityGuard` or
   `TestCodexSpawnAgentV2PreToolUseParity` — proving both are 100% uncommitted WIP, not part of `HEAD`.
4. Ran `python3 -m pytest hooks/test_pre_tool_use_oga_guard.py -q` against this clean copy.

**Result: 115 passed, 0 failed, 10.26s** (`HEAD=ff91967`, dated 2026-07-16T15:11:50Z).

This is the number a fresh worktree built from `ff91967` should reproduce on first run, and the
correct gate for the new spec's regression requirement — not the verifier's 119/4, and not this
pass's own contaminated shared-tree 134/6.

## 4. A structurally more robust identity-read mechanism already exists elsewhere — found, and explicitly scoped OUT

Read `hooks/loop_stop_guard.py` at the two locations my own earlier grep for `subagents` surfaced:
lines 590-635 and 1995-2025.

- **Path convention** (`loop_stop_guard.py:603-621` and `:2001-2013`, read directly): `project_dir =
  os.path.dirname(tpath)`; `sub_path = os.path.join(project_dir, session_id, "subagents",
  "agent-%s.jsonl" % agent_id)`. This is the exact `<project_dir>/<session_id>/subagents/` layout the
  new spec's meta.json fallback needs, and it is proven live already (comment at
  `loop_stop_guard.py:2008`: "confirmed live against this machine's own directory structure").
  **Caveat, explicitly flagged for the Coder:** this existing, proven convention constructs a
  `.jsonl` path (the sub-agent's own transcript file, used for a DIFFERENT purpose — nested nested-
  dispatch nested-dispatch scanning), not a `.meta.json` path. The verifier's report cites a real path
  ending `.../subagents/agent-a62aba0bca9a1ea35.meta.json`, consistent with the SAME directory hosting
  both file types as siblings, but I did not personally open that file or its parent directories to
  confirm the full `<project_dir>/<session_id>/` prefix myself — doing so would have meant reading
  another session's transcript path outside this repo, which `roles/researcher.md`'s data-access-scope
  rule requires explicit, separate dispatch authorization for, and this dispatch did not grant that
  (it granted building on the verifier's already-extracted findings, not independently re-opening the
  same session-transcript files). **The Coder must confirm this path template resolves to a real file
  live, before depending on it** (see the spec's Section E, "Residual verification").
- **A structured (non-regex) `agentId` read** (`loop_stop_guard.py:606-612` and `:1995-1999`, read
  directly): `_pe_tur = _pe_ev.get("toolUseResult"); _pe_aid = _pe_tur.get("agentId")` — reads a
  camelCase `agentId` off a tool_result event's own structured `toolUseResult` field, not off
  human-facing text via regex. This is a more robust alternative to `pre_tool_use_oga_guard.py`'s own
  `AGENT_ID_RE` text-scrape (lines 663-664, 770-780). **It does NOT, however, solve the foreground
  timing race on its own**: `loop_stop_guard.py` is a Stop hook, firing at the orchestrator's OWN
  turn-end — by which point a blocking/foreground `Agent` call has already returned and its
  `tool_result` is already present in the transcript. `pre_tool_use_oga_guard.py` fires DURING the
  sub-agent's OWN nested tool call, before the parent's blocking call returns. The two hooks read the
  same transcript file at structurally different points in the timeline, so a mechanism proven
  reliable at Stop-hook time does not automatically transfer its timing guarantee to PreToolUse time.
  **Flagged as a real, adjacent, worthwhile improvement (swap `AGENT_ID_RE`'s regex scrape for this
  structured field read, keeping it at the same tertiary priority) — explicitly OUT OF SCOPE for the
  companion spec** (the originating dispatch asked only to demote `AGENT_ID_RE` to tertiary priority,
  not to replace its extraction mechanism). Recommend a follow-up `fix_plan.md` entry if this is ever
  pursued — not filed by this dossier, since opening/prioritizing `fix_plan.md` entries is Oga's/the
  user's call, not a Researcher's, per `roles/researcher.md`'s guardrail.

## 5. A minimal, high-reuse design became apparent while reading `_resolve_task_or_dispatch_id`

`_resolve_task_or_dispatch_id(value)` (`pre_tool_use_oga_guard.py:859-867`) already does exactly what
a meta.json-derived `toolUseId` fallback needs: it matches `value` against `active_dispatches`'s own
`dispatch_id` field, which is ALREADY gated by staleness (`in_flight_ids`) and same-session
(`_same_session`) — the exact two properties the confirmed diagnosis (Section 5 of the verifier
report) requires the meta.json path to inherit, not bypass. This means a meta.json-based fallback can
be implemented as: locate + validate the meta.json file, extract its camelCase `toolUseId`, then
**delegate entirely** to the existing, already-tested `_resolve_task_or_dispatch_id()` — no
re-implementation of staleness/retirement/session logic needed, and any future change to those checks
automatically applies to both paths. This is the design the companion spec adopts (its Section F).

## Sources consulted this pass

**Read directly:** `hooks/pre_tool_use_oga_guard.py` (full), `hooks/test_pre_tool_use_oga_guard.py`
(lines 2440-2680), `hooks/loop_stop_guard.py` (lines 590-635, 1995-2025), `fix_plan.md` (lines
9460-9568, plus a full-file grep for `H-GUARD-4`/`H-LT6`/`H-GUARD-CODER-DETECT-SELFQUOTE-1`),
`loop-team/runs/2026-07-16_oga-guard-codex-worker-identity/specs/spec.md` (full), `roles/verifier.md`
(full), `roles/researcher.md` (full, own role brief).

**Commands run (read-only/non-destructive):** `git status`, `git diff --stat`, `git log`, `git
worktree list`, `git rev-parse HEAD`, `python3 -m pytest hooks/test_pre_tool_use_oga_guard.py -q`
(both in the shared tree, and against a scratch copy isolating `git show
HEAD:hooks/test_pre_tool_use_oga_guard.py`), `ps aux` / `ps -p <pid> -o command=` for live Codex
processes, `find`/`grep` across `hooks/` for `meta.json` / `toolUseId` / `agentType` / `subagents`
references.

**Deliberately NOT read**, per `roles/researcher.md`'s data-access-scope rule (this dispatch
authorized building on the verifier's already-extracted findings, not independently opening the same
session-transcript files myself): the two real parent transcripts the verifier's report cites by path
(`.../5dec499f-d96d-44ff-a345-149c1349a2b4.jsonl`, `.../23d0beca-f87f-454b-b088-d2080d2f4b41.jsonl`),
and any real `agent-<id>.meta.json` file. All facts about their shape/timing/content are cited as the
verifier's already-confirmed findings, attributed accordingly — not re-derived by this pass.
