# Mode A dossier — Worktree isolation for `/loop-team` builds (fixing "sibling session pollutes shared main tree")

- **Date:** 2026-07-09
- **Researcher mode:** A (loop-improvement), leaf worker (no sub-dispatch)
- **Triage:** IMPLEMENTABLE_NOW (prose/process change + one-time cheap empirical check)
- **Priority (composite):** ≈ **0.50** (high for a process/risk fix — see scoring at end). Not a DECAY-INTERRUPT.
- **Wires in at:** `loop-team/orchestrator.md` → "Stop conditions & guardrails" → the **"Work in isolation"** bullet (line 444); plus a one-line note in `~/Claude/CLAUDE.md` / a memory so `EnterWorktree`'s activation condition is satisfied.

---

## Diagnosis — why this keeps happening

The `/loop-team` framework repo (`~/Claude/loop`) is edited **in place, on `main`, in the single primary working tree**, by every session that runs a framework-improvement build. Nothing isolates one session's working-tree state from another's. When a second, unrelated Claude Code session is live in the same tree (the padsplit-cockpit/TaxAhead session this run kept observing), its uncommitted edits and untracked files sit in the *same* `git status` surface the build's own gates read. This is confirmed live right now:

```
$ git -C ~/Claude/loop status --porcelain
 M loop-team/harness/full_history_scan.py
 M loop-team/harness/test_full_history_scan.py
 M loop-team/learnings.md
 M research/radar.md
 M scripts/snapshot-publish.sh
 M scripts/test_snapshot_publish.py
?? research/integration-mvp-tiers-2026-07-09.md
?? research/nextjs-revalidatePath-useActionState-inbox-refresh-2026-07-09.md
?? research/pii_gate_tooling_false_positive_fix_dossier.md
?? research/plancheck-nonbinding-saturation-2026-07-09.md
?? research/postgres-rls-self-referencing-recursion-messages-2026-07-09.md
?? research/run-logging-enforcement-gap-codex-vs-claude-code-2026-07-09.md
?? research/spec-codex-parity-and-consent-installer-2026-07-09.md
```

Those 7 untracked `research/*.md` files and 6 modified tracked files are a *different* workstream's output living in this build's tree. This is the exact failure class already documented three times:

- **`feedback_one_session_per_worktree.md`** (memory): D1 run, a sibling session accumulated 1,300+ uncommitted lines in `hooks/`, `harness/verify.py`, `orchestrator.md` → the live Stop/PreToolUse hooks were the sibling's half-edited copies (3 tests red), the step-size gate counted foreign lines, and the *measuring instruments themselves* (`verify.py`, `orchestrator.md`) changed under the run using them. **Recurred 2026-07-09 in the taxahead project** (different repo) as a near migration-number collision (`0007`/`0008`) — proving it's a general pattern, not a `~/Claude/loop` fluke.
- **`learnings.md` line 569** ("Two live sessions must never share one git working tree") and **line 1734** (2026-07-09: a sibling session's concurrent vitest run against the same local Postgres produced a full-suite failure signature *indistinguishable from a real regression*).
- **`learnings.md` line 1747** (2026-07-09): this repo's own `post-commit` hook left HEAD on the wrong branch mid-pipeline, and the next commit landed there silently — the same "who touched the shared tree" hazard, this time self-inflicted by the auto-publish hook.

The root cause is structural: **one working tree = one shared, uncommitted, mutable state**, and the loop's deterministic gates read that shared state (`git status --porcelain`, step-size line counts, testmon caches) as if it were the build's own. Worktrees are the standard, now-native fix.

---

## Answers to the 5 questions (with evidence)

### Q1 — Should "Work in isolation" explicitly instruct `EnterWorktree` at run start? What wording triggers its activation condition?

**Yes, it should be upgraded from vague prose to an explicit, mandatory run-start instruction — but the mechanism should be an explicit `git worktree add … HEAD` Bash command, NOT a bare `EnterWorktree` relying on its default base ref** (see Q2 for why the default is broken in this repo).

`EnterWorktree`'s stated activation gate is: *"Use this tool ONLY when explicitly instructed to work in a worktree — either by the user directly, or by project instructions (CLAUDE.md / memory)."* That condition **is** satisfiable by adding explicit text to `orchestrator.md` + `~/Claude/CLAUDE.md` + a memory — those are exactly the "project instructions" it names. So the activation gate is not the blocker; the base-ref default is.

Note the current bullet (line 444) says *"for `existing_repo`, work on a copy or a git branch, never directly on main."* This session has committed directly to `main` all session — and that is **not** simply a violation. It's a **real gap in the rule's scoping**: the "never on main" rule was written for a *target* repo (a user's app being built by the loop). But a framework-self-improvement build's target repo **is** `~/Claude/loop` itself, whose entire publish pipeline (`post-commit` → `snapshot-publish.sh`) is hardwired to fire **only on `main`** (`auto-publish-on-commit.sh`: `branch="$(git rev-parse --abbrev-ref HEAD)"; [ "$branch" = "main" ] || exit 0`). So framework builds *must* ultimately land on main to publish — "never on main" cannot mean "never merge to main here." The rule needs to distinguish (a) *build in isolation on a temp branch/worktree* from (b) *reconcile to main at the very end*. The worktree fixes the collision; the merge-back to main is still required (Q3).

**Transfer-condition / honesty flag (required by `roles/researcher.md`):** this guarantee is **instructional, not structural**. Nothing forces Oga to create the worktree; if Oga forgets, the build silently runs in the shared main tree and the collision recurs invisibly — a *silent, load-bearing* compliance failure (wrong gate verdicts that still "pass"). A structural enforcement (a hook that refuses to arm the micro-step gates unless the target path is a linked worktree, not the primary tree) is **not available to Oga** because it would require a `settings.json`/hook registration, which the auto-mode classifier HARD-BLOCKS (`feedback_settings_json_hard_block.md`; `learnings.md` line 195). This mirrors the repo's own established pattern: ship the instructional fix first, log the structural upgrade as an open `fix_plan.md` follow-up (cf. `H-REVIEW-COMMIT-1`, `H-WF-DELEGATE-1`).

### Q2 — Is `origin/main` close enough to local `main` that `baseRef: fresh` is safe here?

**No — and worse than "lags": `~/Claude/loop` has NO `origin` remote at all.**

```
$ git -C ~/Claude/loop remote -v
(empty)
$ git -C ~/Claude/loop rev-parse origin/main
fatal: ambiguous argument 'origin/main': unknown revision or path not in the working tree
```

The `reference_loop_engineering_repo.md` memory ("~/Claude/loop tracks to github.com/Eobodoechine/loop-engineering") is true only *indirectly*: publishing does **not** happen by pushing this repo. `snapshot-publish.sh` reads MAIN **read-only via `git archive HEAD`** into a *separate* clone (`~/loop-public`), PII-gates it, and force-with-lease pushes **that clone** to GitHub. The private working repo itself has no remote. (A stale `branch.main.vscode-merge-base=origin/main` config exists — set by VS Code — which *assumes* an origin/main that does not exist; ignore it.)

Consequence: `EnterWorktree`'s default `worktree.baseRef: fresh` ("branches from `origin/<default-branch>`") **cannot resolve `origin/main`** in this repo. So the default is not merely risky (the `feedback_worktree_baseref_gotcha.md` "origin lags HEAD" case, real in *padsplit-cockpit* where an origin does exist and was 3 commits behind) — here it is **undefined/broken**, because there is no origin to branch from. `worktree.baseRef` is also **not a native git config key** (`git config --get worktree.baseRef` → unset/exit 1; git has no such key) and it is **not set in any Claude settings file** I could find — it's a Claude-Code internal default. Flipping it to `head` would require a `settings.json` edit, which Oga **cannot** do autonomously (HARD BLOCK, per Q1).

**Therefore: do not rely on `EnterWorktree`'s default. Use an explicit local-HEAD base** — either (a) Nnamdi sets the Claude `worktree.baseRef=head` setting once (human action, since it's a settings edit), or (b) — cleaner and fully under Oga's control — Oga uses the Bash command the two prior incidents already validated: `git worktree add <path> -b <branch> HEAD`. This sidesteps both the no-origin problem and the settings-edit block in one move.

**Empirical unknown to close cheaply (probe, don't theorize):** I could not test what `EnterWorktree` *actually* does when no `origin` exists (fall back to HEAD, or hard-error) without invoking the tool, which is outside a Researcher's remit and its own activation rule. Oga/Nnamdi should test once: create a throwaway worktree, `git rev-parse HEAD` inside it vs main, then discard. Until that's known, prefer the explicit `git worktree add … HEAD` path.

### Q3 — What is the reconciliation workflow, and how does it interact with the same collision risk? Does `git-content-aware-merge.sh` factor in?

Worktrees **share one `.git` object store and ref namespace** (confirmed: `git rev-parse --git-common-dir` → `.git`; and prior art: *"All three directories share exactly one `.git` folder. Commits made in any worktree are immediately visible to all others"*). So a commit made on a worktree branch is **immediately visible from main with NO push/fetch** — reconciliation is a purely *local* ref operation.

For a framework build (must publish → must land on main), the workflow is:

1. Build session creates + enters a worktree on a throwaway branch (`git worktree add <path> -b loop-build-<ts> HEAD`), does **all** Coder/Test-writer/Verifier work and micro-step checkpoint commits **there**. Zero contact with the primary main tree for the whole build. The sibling's edits to main's tree are invisible and harmless.
2. When done + verified, from the **primary** tree: `git merge --ff-only loop-build-<ts>` → lands the commits on main → fires the `post-commit` publish hook exactly as today.
3. `git worktree remove <path>` + `git branch -d loop-build-<ts>`.

**Interaction with the collision risk:** this **shrinks** the shared-main-tree exposure from *the entire build duration* to *a single fast-forward merge instant* — the core risk reduction. It does **not eliminate** it, and honesty requires saying so:
- If the sibling has main's working tree **dirty** on the files the ff-merge would touch, git **safely refuses** (it never clobbers dirty files) → surface to Nnamdi, never stash/discard the sibling's WIP (per `feedback_one_session_per_worktree.md`).
- If the sibling has **advanced main's ref** concurrently, the merge is no longer a fast-forward → `--ff-only` refuses → a real 3-way merge (possible conflict) is needed. Two sessions both trying to *land on main* is the residual root that worktrees don't solve — worktrees isolate the **build**, not the final **publish-to-main**. True elimination needs one-session-per-repo for the main-landing, or serialized merge-backs.

**`~/Claude/scripts/git-content-aware-merge.sh` factors in narrowly, as a backup for step 2's edge case only.** Its job (per its own header) is git's *content-blind untracked-file* merge block — it pre-stages untracked files that are **byte-identical** to the incoming ref's blob so they don't spuriously abort the merge, leaving genuinely-differing files to correctly block. It's relevant if the merge-back hits *"untracked file X would be overwritten by merge"* (e.g. both the worktree branch and main's tree independently created the same new `research/*.md`). It is **not** the primary reconciliation mechanism (a clean ff-merge needs none of it), and its own documented limitation (GCAM-3) is that against an already-diverged, non-fast-forwardable destination it can leave a file staged while `git merge` still fails — i.e. it does **not** rescue the "sibling advanced main" case above; it only smooths the identical-untracked-file case.

### Q4 — Do the `~/.loop-gate` flag files need adjustment for a worktree-isolated workflow?

**No adjustment needed — session_id scoping is sufficient, and I confirmed the reasoning rather than assuming it.**

- The flag dir is a **fixed global**, not per-worktree: `os.path.expanduser(os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))` (`micro_step_gates.py:61`, `subagent_stop_gate.py:119`). It is the same dir regardless of which worktree a session runs in.
- **Every** flag file is `{session_id}`-prefixed: `{session_id}_target`, `{session_id}_signatures.json`, `{session_id}_python` (`micro_step_gates.py:194, 215, 346`); `{session_id}_{agent_id}.verifier_pass`, `{session_id}_{agent_id}.commit_violation` (`subagent_stop_gate.py:121, 293`).
- Session IDs are **unique UUIDv7-style** per Claude Code session — the live `~/.loop-gate` listing shows distinct full IDs even for sessions started in the same second (`019f480c-5c61-…`, `019f480c-5c62-…`, `019f480c-5c7b-…` share only the time prefix). Two worktree-isolated sessions therefore have **disjoint flag namespaces**; they cannot read or clobber each other's flags even sharing one global dir.
- The global dir is in fact a **feature** for worktree correctness, not a bug: the micro-step gate resolves the target repo from the **content** of `{session_id}_target` (`micro_step_gates.py:205`, expanduser'd), not from cwd. A worktree-isolated session simply writes its **worktree path** into that file at run-start (step 0 already writes "the target repo path"), and the gate then operates on the worktree — no cwd/worktree coupling to break.
- Glob-injection is a non-issue for real IDs: UUID session IDs contain no glob metacharacters, and the credit-read path was already hardened with `glob.escape()` (`H-GUARD-5`).

**One thing to state in the run-start instruction (not a code change):** the `{session_id}_target` file must name the **worktree** path, not the primary tree's path. This is automatic if the worktree is created *before* step 0 writes the target file.

### Q5 — Downsides/cost of ALWAYS using a worktree for `/loop-team` builds?

Real, but modest, and mostly avoidable:

1. **Cold caches / dependency setup per worktree.** Prior art: *"each worktree directory needs its own dependency install."* For this Python repo the concrete hits are: no warm `.testmondata` (the micro-step loop's `pytest --testmon` rebuilds it on first run — a slowdown, not a blocker, and orchestrator.md already notes testmon self-builds), no venv, and `slipcover`/`mutmut`/`pytest-isolate` may need installing. Mitigation: base the worktree on HEAD (shares committed caches if any are tracked) and accept a one-time first-run rebuild.
2. **`EnterWorktree`'s in-repo `.claude/worktrees/` location is a gotcha here.** `.claude/` is **NOT gitignored in this repo** (`git check-ignore .claude` → exit 1; no `.gitignore` entry; `.claude/agents/*.md` are tracked). A worktree checkout placed under a non-ignored `.claude/` risks showing up in the primary tree's status surface. Prefer a **sibling dir outside the repo** (`git worktree add ../loop-build-<ts> …`) or ensure `.claude/worktrees/` is gitignored before using EnterWorktree's default location.
3. **Cleanup discipline.** Throwaway branches (`loop-build-<ts>`) and worktree dirs accumulate; each needs `git worktree remove` + `git branch -d`. `ExitWorktree action:"remove"` handles the dir and *safely refuses if dirty* (good — never clobbers), but the branch cleanup is manual.
4. **Friction when the build legitimately needs the current main tree state.** A worktree isolates you *from* main's in-flight state — usually the point, but if a build must compare against main's committed state you use `git show main:<path>` / `git -C <primary-tree> …`; minor.
5. **Overkill for a trivial single-file doc edit.** Spinning a whole worktree to change one line of `orchestrator.md` is heavyweight. Cost/benefit favors mandatory worktrees for **multi-step CODE builds** (the micro-step loop, where the gates read shared state); for a one-shot trivial prose edit it can be optional — though note even prose edits have collided here (the `96693f8` review-to-commit race on `orchestrator.md`), so "optional" ≠ "never."

Net: the costs are setup-time and cleanup-hygiene, not correctness. For the failure class it removes (false gate fires, mis-attributed regressions, migration/ID collisions across sessions), the trade is strongly favorable for real code builds.

---

## Prior art (grounded — how other tools solve "N concurrent AI sessions in one repo")

The mature, converged answer across the ecosystem is exactly **git-worktree-per-task/agent**, now natively supported by Claude Code, Codex, and Cursor. Ground quotes:

- **developersdigest, "Git Worktrees + Claude Code: The 2026 Playbook"** (opened + verified): *"All three directories share exactly one `.git` folder. Commits made in any worktree are immediately visible to all others."* Recommends worktrees as **sibling dirs** (`git worktree add ../project-agent-a -b agent/task-a`); reconciliation is *"`git diff main..agent/branch-name` before merging… Merge one branch at a time"* then `git worktree remove`; explicitly flags the cost *"each worktree directory needs its own dependency install."* Names real usage: Scott Chacon's **Grit** (45B tokens across parallel agents) and Mike Welsh's "5 concurrent worktrees in a monorepo."
- Search-result leads (NOT independently opened — cite as leads only, per honesty bar): Zylos Research, Augment Code guides, MindStudio, ParallelCode — all describe the same worktree-per-agent primitive; one reports **incident.io** running "four to five parallel Claude Code agents routinely" via a bash function that spawns an isolated session on a new branch. These corroborate but were not fetched, so treat the specific claims as unverified.

**Verdict:** there is **no more mature pattern than worktree-per-session** to adopt instead — worktree-per-agent *is* the industry-standard primitive, and Claude Code's `EnterWorktree` is the native implementation of it. The only project-specific adaptations needed are the two this repo's own workflow forces: (1) explicit `HEAD` base (no origin), and (2) merge-back-to-main for the publish pipeline.

---

## Recommendation — exact replacement wording for the "Work in isolation" bullet

Replace `orchestrator.md` line 444:

> - **Work in isolation** — for `existing_repo`, work on a copy or a git branch, never directly on main.

with:

> - **Work in isolation (worktree-per-build).** Before starting any multi-step CODE build — and this is the "project instructions" that satisfies `EnterWorktree`'s activation gate — Oga MUST run the build in its own git worktree, never in the shared primary tree. Two live sessions sharing one working tree is a documented, recurring failure class (`feedback_one_session_per_worktree.md`; `learnings.md` "Two live sessions must never share one git working tree"): foreign uncommitted lines cause false gate fires, mis-attributed regressions, and ID/migration collisions.
>   - **Create it with an explicit local-HEAD base, NOT `EnterWorktree`'s default.** `~/Claude/loop` has NO `origin` remote (it publishes via `snapshot-publish.sh` into a separate `~/loop-public` clone), so `EnterWorktree`'s default `worktree.baseRef: fresh` (branch from `origin/<default-branch>`) cannot resolve and is unsafe here. Use: `git worktree add ../loop-build-<ts> -b loop-build-<ts> HEAD` (sibling dir, since `.claude/` is not gitignored). Only use the `EnterWorktree` tool if Nnamdi has set the Claude `worktree.baseRef=head` setting (a settings edit Oga cannot make itself), and even then verify `git rev-parse HEAD` in the new worktree equals main's HEAD before proceeding.
>   - **Write the worktree path into the step-0 `{session_id}_target` gate file** so the micro-step gates arm against the worktree, not the primary tree.
>   - **Reconcile at the end, not during.** For framework builds (which must land on `main` to publish), when the build is done + verified: from the primary tree run `git merge --ff-only loop-build-<ts>`, then `git worktree remove` + `git branch -d`. This confines shared-main-tree exposure to a single fast-forward. If the ff-merge refuses (sibling dirtied or advanced main), STOP and surface to Nnamdi — never stash, discard, or force past another session's WIP. Use `~/Claude/scripts/git-content-aware-merge.sh` only for the narrow "identical untracked file blocks the merge" case.
>   - This guarantee is **instructional, not structural** — nothing forces the worktree, and forgetting it fails silently (the build runs in the shared tree and gates read foreign state). Log the structural-enforcement upgrade as an open `fix_plan.md` follow-up.
> - **No destructive ops** … *(existing next bullet unchanged)*

(This is a prose edit to a scope-listed framework file → per orchestrator.md it requires a **full plan-check** before commit, and commit via `commit_diff_reread.py`, regardless of how small it looks. Two prior small-prose edits to this file class shipped unvetted content — `96693f8`, `5884604`.)

Also add one line to `~/Claude/CLAUDE.md` and a memory (so the activation condition is unambiguously met from "project instructions / memory"): *"`/loop-team` code builds run in a git worktree created with `git worktree add … HEAD` (this repo has no origin; do not use EnterWorktree's default base ref)."*

---

## Priority score (per `orchestrator.md` → "Prioritizing radar candidates")

| sub-score | value | rationale |
|---|---|---|
| effect | 0.5 | Not a suite caught-hole/false-pass metric move; it's a documented-incident-rate reduction (eliminates a whole class of false gate fires + mis-attribution across ≥3 real incidents). Scored honestly-modest for lacking a suite-metric tie. |
| confidence | 0.8 | Worktrees are mature, natively supported, widely adopted; mechanism is well-understood local git. Docked for the one empirical unknown (EnterWorktree's no-origin behavior). |
| phase_fit | 1.0 | Maximally time-critical — a `/loop-team` build is running in the shared, polluted tree right now. |
| risk_reduction | 0.9 | This IS a risk-reduction candidate; de-risks every future concurrent-session build. |
| uncertainty | 0.3 | Low exploration bonus — well-understood pattern; only genuine unknown is the no-origin EnterWorktree probe. |
| cost_to_test | 0.15 | Cheap: a prose/instruction change + a one-time throwaway-worktree probe. Minor friction (cold testmon cache, cleanup). |

`priority = 0.40·(0.5×0.8) + 0.20·1.0 + 0.15·0.9 + 0.10·0.3 − 0.15·0.15`
`= 0.16 + 0.20 + 0.135 + 0.03 − 0.0225 = ` **≈ 0.50**

Places it as a **high-priority process/risk fix** (well above a typical exploratory candidate ~0.2–0.3). The composite under-weights it slightly because the rubric's `effect` term is tuned for suite-metric movers, not risk fixes — the honest read is that `phase_fit=1.0` + `risk_reduction=0.9` are the load-bearing terms here, and both are strongly justified. Adoption still follows the normal gate: full plan-check on the orchestrator.md edit before it lands (it is not a critical-path *tool* swap needing a PACE experiment, but the doc edit itself must be plan-checked per this repo's own rule).

---

## Sources

- Repo state (this repo, live 2026-07-09): `git remote -v` (empty), `git rev-parse origin/main` (fatal: unknown revision), `git status --porcelain` (6 modified + 7 untracked foreign files), `git config --get worktree.baseRef` (unset/exit 1), `git check-ignore .claude` (exit 1 = not ignored), `git rev-parse --git-common-dir` (`.git`).
- `~/Claude/loop/scripts/auto-publish-on-commit.sh` (post-commit hook; `[ "$branch" = "main" ] || exit 0`) and `scripts/snapshot-publish.sh` header (`git archive HEAD` read-only from MAIN → `~/loop-public` clone → force-with-lease push; MAIN has no remote).
- `~/Claude/loop/hooks/micro_step_gates.py` lines 61, 194, 205, 215, 346 and `hooks/subagent_stop_gate.py` lines 119, 121, 293 (flag-file session_id scoping).
- `~/Claude/loop/loop-team/learnings.md` lines 569, 1654, 1734, 1747, 1789; `orchestrator.md` line 444 + "Prioritizing radar candidates" (487–510) + plan-check/`commit_diff_reread` rules.
- Memories: `feedback_one_session_per_worktree.md`, `feedback_worktree_baseref_gotcha.md`, `feedback_settings_json_hard_block.md`, `reference_loop_engineering_repo.md`.
- `~/Claude/scripts/git-content-aware-merge.sh` (header + GCAM-3 limitation).
- Prior art — OPENED + verified: [developersdigest — Git Worktrees + Claude Code: The 2026 Playbook](https://www.developersdigest.tech/blog/git-worktrees-claude-code-parallel-agents-guide) (shared `.git`, sibling-dir worktrees, diff-before-merge reconciliation, per-worktree dependency cost, Grit / Mike Welsh usage).
- Prior art — search-result LEADS, not independently opened (honesty-flagged): [Zylos Research](https://zylos.ai/research/2026-02-22-git-worktree-parallel-ai-development/), [Augment Code](https://www.augmentcode.com/guides/git-worktrees-parallel-ai-agent-execution), [MindStudio](https://www.mindstudio.ai/blog/git-worktrees-parallel-ai-coding-agents), [ParallelCode](https://parallelcode.app/blog/parallel-ai-agents/) (incident.io "4–5 parallel Claude Code agents" claim is from these — unverified).
