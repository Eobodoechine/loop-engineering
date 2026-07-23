# PadSplit Stryker mutation-testing — scope reconciliation (comparative analysis, not a fix)

**Date:** 2026-07-11
**Scope of this document:** pure comparison of what was built (uncommitted, in
`~/Claude/loop-worktrees/padsplit-stryker-mutation-testing`) against what was
plan-checked. No code was written or fixed as part of this research. No
go/no-go recommendation is made here — that call belongs to Oga/Nnamdi.

**Headline finding, stated up front because it changes the framing of the whole
question:** there are **two different, mutually exclusive specs** for this
build living in two different directories in the worktree, not one approved
spec that the build deviated from. Only one of them has a plan-check log file
on disk, and it is **not** the one the actual build matches.

---

## 0. The two specs (this was not in the original briefing and is the central fact)

| | **Spec A** (`db-rls.ts`-only) | **Spec B** (Tier-1 multi-file) |
|---|---|---|
| Path | `loop-team/runs/2026-07-10_stryker-mutation-testing/specs/spec.md` | `runs/2026-07-10_stryker-mutation-testing/specs/spec.md` (repo root `runs/`, **no** `loop-team/` prefix) |
| mtime | 2026-07-10 17:51:12 | 2026-07-10 18:54:46 |
| Title | "Spec — Adopt Stryker (JS/TS mutation testing) in padsplit-cockpit" | "Spec: adopt Stryker mutation testing in padsplit-cockpit (Tier-1 scope)" |
| `mutate` scope | `["src/lib/db-rls.ts"]` only | `sla-clock.ts`, `dashboard-metrics.ts`, `inbox/view.ts`, `inbox/direction.ts`, `task-recompute.ts:54-74` |
| Task classification | `hardening-bugfix` | `new-capability` |
| Cited research dossier | `research/loop-improvement-db-test-isolation-and-rls-catching-2026-07-09.md` | `research/stryker-mutation-testing-integration-2026-07-10.md` |
| Plan-check log on disk? | **Yes** — `loop-team/runs/2026-07-10_stryker-mutation-testing/plan_check_log.md`, one round logged: `Round 1 — PLAN_FAIL`, revised to "v2" per its own header. **No round-2 entry exists in this file or anywhere else.** | **No plan_check_log.md file exists anywhere in `runs/2026-07-10_stryker-mutation-testing/`** (verified: `find runs/2026-07-10_stryker-mutation-testing -type f` returns only `specs/spec.md`, nothing else). The spec's own prose *claims* "Revision 2 (round 1 plan-check was PLAN_FAIL...)" and "Revision 3 (round 2 plan-check was PLAN_FAIL...)" but there is zero independent artifact confirming either round happened, and **no PLAN_PASS is recorded for it anywhere.** |
| AC4/AC-4 doc target | `loop-team/runs/2026-07-10_stryker-mutation-testing/run_log.md` | `web/docs/mutation-testing.md` (new file) |
| Matches what was actually built? | **No** — `db-rls.ts` is never touched by the built config. | **Yes**, closely — see §1 below, near-verbatim match on `mutate` scope, file list, `checkers`, `thresholds`. |

Cross-check that confirms directionality: a repo-wide `grep -rn "LOOP_GATE\|PLAN_PASS\|PLAN_FAIL"` across the whole worktree finds exactly one `plan_check_log.md` for this build (Spec A's, round 1 only) and **no second plan-check log, no `PLAN_PASS` verdict of any kind, for the Stryker build, anywhere.** The `run_log.md` that Spec A's own AC4 calls for as the closing deliverable **does not exist** either (`loop-team/runs/2026-07-10_stryker-mutation-testing/` contains only `plan_check_log.md` and `specs/spec.md` — confirmed via direct file listing).

Also notable: Spec A cites `research/loop-improvement-db-test-isolation-and-rls-catching-2026-07-09.md` as its source research — **this file does not exist anywhere in the worktree** (`find . -iname "*loop-improvement-db-test-isolation*"` returns nothing). The only research dossier that actually exists on disk is `research/stryker-mutation-testing-integration-2026-07-10.md` (mtime 18:38:32, between Spec A's v2 and Spec B's write time) — and that dossier is the one Spec B cites, not Spec A.

**mtime timeline, reconstructed:**
1. 17:50 — Spec A round-1 plan-check log written (`PLAN_FAIL`, db-rls.ts scope)
2. 17:51 — Spec A revised to "v2" (still db-rls.ts scope)
3. 18:38 — a *new* domain-research dossier appears (`research/stryker-mutation-testing-integration-2026-07-10.md`), scoped to Tier-1 multi-file analysis, not db-rls.ts
4. 18:54 — Spec B appears (Tier-1 multi-file scope), citing the 18:38 dossier, with its own internal (unlogged) revision-history narrative
5. 19:27 — `web/stryker.config.mjs` is written, matching Spec B's `mutate` list exactly
6. 19:33 — the `dashboard-metrics.ts` equivalent-mutant fix is applied

This reads as two sequential, apparently-unaware-of-each-other planning threads for the same task, where the second (Spec B) supplanted the first (Spec A) without ever being logged through the same plan-check mechanism Spec A went through — it only has its own self-narrated claim of having done so.

---

## 1. `web/stryker.config.mjs` — verbatim quotes (Task 1)

Full config, `web/stryker.config.mjs:1-79` (comments are the load-bearing part, quoted verbatim):

**Scope statement (lines 1-14):**
> ```
> // Stryker Mutator config — Tier-1 (pure, DB-free) mutation-testing scope for
> // padsplit-cockpit's web/ package. See web/docs/mutation-testing.md for how to
> // run this, what it covers, and the disable-comment convention for
> // genuinely-equivalent mutants.
> //
> // Scope is deliberately narrow and explicit (no globs): exactly the 4
> // confirmed-pure Tier-1 files, plus ONE line-range within task-recompute.ts
> // scoping mutation to its single genuinely-exported, directly-testable pure
> // function, `tenancyMatchesCurrentMember` (lines 54-74 as of this build —
> // re-confirm this range if the file is edited, per the spec's own warning
> // that it drifts). Everything else in task-recompute.ts (the DB-touching
> // `recomputeAlertState` and the module-private `pickAlertState`/
> // `alertSinceFor` helpers, which have no coverage path other than through
> // ~18 real-Postgres-transaction tests) is intentionally excluded.
> ```

**DB-touching exclusions (lines 16-22):**
> ```
> // Explicitly OUT of scope for this pass (see spec's Non-goals):
> // - src/lib/state-machine.ts (zero test coverage, zero call sites — see the
> //   spec's AC-OPEN-1 follow-up note, not resolved by this build)
> // - src/lib/resolveOrg.ts (makes a real Prisma DB call; both its own test
> //   files require live Postgres / a live dev server)
> // - extension/*.js (sibling npm-workspace, not reachable from this cwd)
> ```

**`testFiles` scoping reasoning — the whole-suite dry-run avoidance (lines 23-55, the load-bearing block):**
> ```
> // `testFiles` (documented, first-class Stryker option, honored directly by
> // @stryker-mutator/vitest-runner — NOT a workaround): Stryker's dry run
> // otherwise executes vitest's own default test discovery across the WHOLE
> // project (all 66 files/1113 tests), not just the files related to `mutate`
> // scope, because it needs a full coverage map up front. This repo's suite
> // includes two "meta" tests with zero relation to any Tier-1 file
> // (`tests/dashboard-actions.test.ts`'s AC19 `tsc --noEmit` check and AC20,
> // which spawns a second nested `npx vitest run` of the ENTIRE suite and
> // asserts it exits 0) that break specifically under Stryker's own sandbox,
> // independent of anything in `mutate` scope:
> //   - AC20's nested full-suite run fails `tests/signout-ui.test.ts`'s AC3
> //     (a strict first-line-content check on src/components/SignOutButton.tsx)
> //     because Stryker's typescript-checker preprocessing legitimately
> //     prepends `// @ts-nocheck` to every file OUTSIDE `mutate` scope (see
> //     @stryker-mutator/core's DisableTypeChecksPreprocessor — this is
> //     documented, intentional Stryker behavior, not a bug), which changes
> //     that unrelated file's first line.
> //   - `tests/crm-contacts-db.test.ts`'s AC4 also failed inside that same
> //     nested run — a real DB-driven side effect of the codebase's shared,
> //     single-Postgres-fixture test-isolation model (see the "One session
> //     per worktree" / shared-DB-flakiness pattern this loop framework has
> //     hit before) colliding with Stryker running the full suite a second,
> //     redundant time inside its own sandbox.
> // Neither failure is a defect in — or in any way "related to" (in Stryker's
> // perTest-coverage sense) — the 5 Tier-1 files/range actually being mutated
> // here; both tests would never be exercised by any real mutant in this
> // `mutate` scope. `testFiles` limits BOTH the dry run and every subsequent
> // per-mutant run to exactly the 5 files whose own dedicated, DB-free (or,
> // for task-recompute.ts, DB-backed-but-directly-relevant) unit tests are the
> // intended kill mechanism for this scope — matching this option's documented
> // purpose ("verify that a module's dedicated unit tests can kill all its
> // mutants independently") and avoiding a large, irrelevant, and in this case
> // environment-fragile chunk of the suite on every run.
> ```

**Actual config body (lines 58-79):**
```js
const config = {
  testRunner: 'vitest',
  tsconfigFile: 'tsconfig.src.json',
  checkers: ['typescript'],
  mutate: [
    'src/lib/sla-clock.ts',
    'src/lib/dashboard-metrics.ts',
    'src/lib/inbox/view.ts',
    'src/lib/inbox/direction.ts',
    'src/lib/task-recompute.ts:54-74',
  ],
  testFiles: [
    'tests/sla-clock.test.ts',
    'tests/dashboard-metrics.test.ts',
    'tests/inbox-view.test.ts',
    'tests/crm-direction.test.ts',
    'tests/task-recompute.test.ts',
  ],
  thresholds: { high: 80, low: 60, break: null },
}
```

Note the comment header's own cross-reference: `// See web/docs/mutation-testing.md` — that file does **not** exist on disk (§5). This is the config's own stated intent, unmet.

### The applied fix — `web/src/lib/dashboard-metrics.ts` (git diff, task 1 second half)

```diff
@@ -33,6 +33,13 @@ export function computeKpis(rooms: RoomMetricInput[]): DashboardKpis {
     }
     if (r.presenceState === 'VACANT') vacantCount++
     if (r.alertState !== 'NONE') alertCount++
+    // outstandingCents is a pure `+=` running sum: whether a member with
+    // balanceCents===0 is included or excluded by this guard contributes
+    // exactly 0 to the sum either way (adding 0 is a no-op), so `>` vs `>=`
+    // here is behaviorally unobservable for ANY input, not merely untested.
+    // Confirmed genuinely equivalent by the 2026-07-10 AC-4 baseline run —
+    // see web/docs/mutation-testing.md.
+    // Stryker disable next-line EqualityOperator: >= is equivalent to > here because outstandingCents only ever sums the guarded value (0 contributes nothing either way)
     if (r.member != null && r.member.balanceCents != null && r.member.balanceCents > 0) {
       outstandingCents += r.member.balanceCents
     }
```

This again references "the 2026-07-10 AC-4 baseline run" and `web/docs/mutation-testing.md` — both are Spec B's own AC numbering (Spec A's AC numbering has no AC-4-as-baseline-run; Spec A's AC3 is the falsifiable run and AC4 is the doc requirement pointing at a *different* path). This is independent confirmation the whole build traces to Spec B, not Spec A.

The mathematical reasoning itself (0 contributes nothing to a running sum regardless of a `>` vs `>=` boundary at exactly 0) is correct as stated — this is a legitimate equivalent-mutant case, not a rationalization, *on its own terms*. See §3 for the broader merit assessment.

---

## 2. Git state — exact enumeration (Task 2)

```
On branch hardening/stryker-mutation-testing
Changes not staged for commit:
	modified:   package-lock.json
	modified:   package.json
	modified:   web/package.json
	modified:   web/src/lib/dashboard-metrics.ts
	modified:   web/vitest.config.ts

Untracked files:
	loop-team/
	research/
	runs/2026-07-10_stryker-mutation-testing/
	web/reports/
	web/stryker.config.mjs
```

`git diff --stat` (tracked files only):
```
 package-lock.json                | 1427 +++++++++++++++++++++++++++++++++++++-
 package.json                     |    3 +-
 web/package.json                 |    6 +-
 web/src/lib/dashboard-metrics.ts |    7 +
 web/vitest.config.ts             |   22 +-
 5 files changed, 1429 insertions(+), 36 deletions(-)
```

- **`package.json`** (root): adds `"test:mutation": "npm run test:mutation --workspace=web"` script.
- **`web/package.json`**: adds `"test:mutation": "stryker run"` script; adds three devDependencies — `@stryker-mutator/core@^9.6.1`, `@stryker-mutator/typescript-checker@^9.6.1`, `@stryker-mutator/vitest-runner@^9.6.1`.
- **`web/vitest.config.ts`**: adds a `createRequire`-based resolution for the `server-only` alias, replacing a hardcoded `path.resolve(__dirname, '../node_modules/...')`. Its own new comment states the reason directly: *"Stryker... copies the whole project into a sandbox one directory level deeper (`web/.stryker-tmp/sandbox-<id>/`) before running vitest against it... A hardcoded path... silently pointed at a nonexistent path in that sandbox... breaking every test that imports `src/lib/ai/draft.ts` (discovered running Stryker's initial dry run — AC-4 of the 2026-07-10 stryker-mutation-testing spec)."* This is a real, load-bearing fix required to make Stryker's sandboxing work at all with this repo's existing vitest config, and it too cites "AC-4" — Spec B's numbering, not Spec A's.
- **Untracked directories/files:**
  - `loop-team/runs/2026-07-10_stryker-mutation-testing/{plan_check_log.md, specs/spec.md}` — Spec A + its one plan-check round.
  - `runs/2026-07-10_stryker-mutation-testing/specs/spec.md` — Spec B, no accompanying plan-check log.
  - `research/stryker-mutation-testing-integration-2026-07-10.md` — the Mode-D domain dossier backing Spec B (434 lines).
  - `web/reports/mutation/mutation.html` — a Stryker HTML report, produced by an actual completed run.
  - `web/stryker.config.mjs` — the config analyzed in §1.
  - (Also pre-existing/unrelated untracked material under `runs/2026-07-08_*` and `runs/2026-07-09_*` and `runs/20260628_155228`, `runs/2026-06-27` — these predate this build and are other sessions' run logs, not part of this Stryker work; listed here only because `git status --porcelain` groups the whole `runs/` directory as one untracked entry.)

No `.stryker-tmp/` sandbox directory or raw JSON mutation report was found alongside `mutation.html` in `web/reports/mutation/` — only the HTML report is present (not independently re-parsed as part of this research per the "no code, no execution" instruction).

---

## 3. Engineering merit of the Tier-1 scope choice, bracketing process (Task 3)

Assessing Spec B / the built config strictly on technical reasoning, independent of which spec "approved" it:

- **File-exclusion reasoning (DB-touching exclusion) — sound.** Excluding `resolveOrg.ts` (real Prisma call, both test files require live Postgres/dev server) and the DB-touching parts of `task-recompute.ts` from a *first* mutation-testing pass, while scoping in only the one exported pure function (`tenancyMatchesCurrentMember`, via Stryker's documented `file.ts:startLine-endLine` mutate-range syntax) is a defensible, conservative choice for establishing a fast, low-flake baseline. The line-range mechanism is real and documented (Stryker's config docs support `path/to/file.ts:startLine[:startColumn]-endLine[:endColumn]`), not an invented workaround.
- **`testFiles` scoping — technically accurate as described, and a genuinely different concern from "DB exclusion."** The config comment's claim that Stryker's dry run otherwise runs the *whole* suite to build a coverage map, and that this repo has two specific tests (`dashboard-actions.test.ts` AC19/AC20) that break under Stryker's sandbox for reasons unrelated to any Tier-1 file, is a plausible and specific failure mode, not hand-waved: it cites a named mechanism (`@stryker-mutator/core`'s `DisableTypeChecksPreprocessor` injecting `@ts-nocheck` into out-of-scope files) and a named consequence (breaking a strict first-line-content assertion in `signout-ui.test.ts`). A security-minded reviewer would find this **specific and falsifiable** — it names an exact test, an exact mechanism, and an exact symptom, which is the standard this project holds evidence to elsewhere (per this session's "Verify the verification mechanism" and "Live DOM verification needs stated coverage" standing lessons). It is *not*, however, independently re-verified in this research pass (no live Stryker run was executed by this researcher to confirm the `@ts-nocheck` claim reproduces exactly as described) — it is documented reasoning, consistent with Stryker's own known preprocessing behavior, but taken at the comment's word here.
- **A reviewer would likely flag one gap:** the config comment states Stryker's "documented purpose" for `testFiles` is to "verify that a module's dedicated unit tests can kill all its mutants independently" — this is a correct description of what `testFiles` mechanically does (restricts the coverage/perTest analysis to a named test subset) but the framing implicitly assumes the 5 named test files are in fact the *complete* real coverage for the 5 mutate targets. If any Tier-1 file has an additional real consumer test outside the 5 named files (the same "hand-curation risk" Spec A's own round-1 plan-check caught for `db-rls.ts`'s consumers — see spec.md's "Do NOT hand-enumerate" instruction), `testFiles` would silently suppress it, understating the true mutation score. This is exactly the failure class Spec A explicitly designed around (letting Stryker's own coverage analysis pick consumers rather than hand-listing them) — and the built config does the opposite: it hand-lists `testFiles`. This is a real, structural tension between the two specs' philosophies, not just a scope-size difference.
- **On its own terms, is the reasoning "rationalized/weak"?** No — the *reasoning chain itself* (named mechanism → named test → named symptom → scoping decision) is specific and checkable, which is a meaningfully higher bar than a vague "some tests broke so we scoped it down." But it is reasoning for **why a narrower, easier-to-run Tier-1 pass was chosen**, not reasoning for **why this Tier-1 pass satisfies the security goal the approved (Spec A) experiment was actually designed to test** — those are two different questions, and the config's comments only answer the first.

---

## 4. Characterizing the deviation (Task 4)

**This is not a superset expansion of Spec A. It is a disjoint scope that never touches `db-rls.ts` at all.**

- Spec A's `mutate` list: `["src/lib/db-rls.ts"]` — exactly one file, chosen explicitly (per its "Files to read" section) because it is "the org-scoped Prisma client factory (`forOrg(orgId)`) that wraps every query in a transaction whose first statement sets the `app.org_id` Postgres session variable the RLS policies key on," and because "a mutation here... is exactly the class of silent, security-relevant regression a 'well-tested' file can still hide."
- The built `stryker.config.mjs`'s `mutate` list contains **zero overlap** with `["src/lib/db-rls.ts"]`: `sla-clock.ts`, `dashboard-metrics.ts`, `inbox/view.ts`, `inbox/direction.ts`, `task-recompute.ts:54-74`. `db-rls.ts` is explicitly *excluded* from the built config's own comments' Tier-2/future-scope framing (it isn't even named in the "Explicitly OUT of scope" list in the config comments — it simply never appears anywhere in the built artifact).
- Spec B (the one the build actually matches) makes this explicit and intentional in its own text: `db-rls.ts` doesn't appear in its target list either — it targets Tier-1 "pure, DB-free" files specifically *because* they're DB-free, which is the opposite selection criterion from Spec A's (Spec A specifically wanted the DB-touching, security-relevant RLS wrapper).

**Plain statement: Spec A's stated goal — mutation-test the security-relevant RLS wrapper (`db-rls.ts`) to check whether its "well-tested" status actually catches security-relevant mutations (transaction-order swap, the `set_config(...)` `TRUE` literal, etc.) — was not attempted, let alone met, by what was built.** What was built is a different, legitimate-on-its-own-terms mutation-testing baseline over unrelated pure business-logic files (SLA clock math, dashboard KPI aggregation, inbox view/direction helpers, one tenancy-matching predicate). It answers "does Stryker work on this repo's easy, DB-free code" — a real and useful question — but not "does Stryker catch a security regression in the RLS wrapper," which was the specific falsifiable experiment Spec A (the only spec with a logged plan-check round) was designed to run.

---

## 5. The docs question (Task 5)

- **`web/docs/mutation-testing.md` does not exist.** Confirmed directly: `find . -iname "mutation-testing.md"` returns nothing; `ls web/docs/` returns `No such file or directory` (the `web/docs/` directory itself does not exist in this worktree).
- **`loop-team/runs/2026-07-10_stryker-mutation-testing/run_log.md` (the path Spec A's AC4 actually calls for) also does not exist.** Direct listing of that run directory shows only `plan_check_log.md` and `specs/spec.md` — no `run_log.md`.
- **So neither spec's documentation deliverable was completed.** Spec A's AC4 wanted a `run_log.md` under `loop-team/runs/2026-07-10_stryker-mutation-testing/` recording the mutation score/decision/follow-up note — missing. Spec B's AC-7 wanted a new `web/docs/mutation-testing.md` documenting the disable-comment convention and Tier-1 scope — also missing, despite two separate places in the built artifacts (`stryker.config.mjs`'s header comment, and the `dashboard-metrics.ts` disable-comment) pointing readers *at* that file as if it exists.
- **Is the config's `web/docs/mutation-testing.md` reference itself evidence of scope/process drift, independent of the file-scope question in §4?** Yes, and it is a *second, independent* signal (not just a restatement of §4's finding): Spec A never mentions `web/docs/mutation-testing.md` anywhere in its text — its only doc target is `loop-team/runs/.../run_log.md`. The fact that the built config's very first comment block points at a path that only appears in Spec B's AC-7 is direct textual proof (independent of the `mutate` file list) that the implementation was executed against Spec B's acceptance criteria, not Spec A's — and that even Spec B's own doc AC was left unmet by the build.

---

## 6. The Nnamdi-approval angle (Task 6)

`~/Claude/loop/fix_plan.md:7895-7898`, the "2026-07-10 — Decisions log: TaxAhead / PadSplit Cockpit structure review" entry:

> "**Tool adoptions (PadSplit Cockpit):** all 5 candidates from the 2026-07-09 Researcher Mode A dossier approved for dispatch — DB transactional test isolation (vitest-environment-prisma-postgres / transactional-prisma-testing), Stryker (JS/TS mutation testing), pgrls + rlsgrid (RLS static analyzer), fast-check (property-based testing), zod schema validation at the sync API ingress (not from the original dossier, surfaced by the project audit's root-cause diagnosis)."

This is authorization for **adopting Stryker as a tool, in principle** — one line among five tool-candidate approvals, with no file scope, target selection, or acceptance-criteria detail attached to it at all. It says nothing about `db-rls.ts` vs. Tier-1 pure files, nothing about `hardening-bugfix` vs. `new-capability` classification, and nothing about a doc target path. **Concept-approval is not scope-approval.** The actual scope decision (which file(s), why, what counts as success) was made later, downstream of this decision-log entry, by whichever planning thread wrote each spec — and only one of those two scope decisions (Spec A's `db-rls.ts` choice) went through a plan-check round that left a log on disk, and even that one has no confirmed final PLAN_PASS for its v2 revision.

---

## Summary table

| Question | Finding |
|---|---|
| What got built | Tier-1 multi-file scope (`sla-clock.ts`, `dashboard-metrics.ts`, `inbox/view.ts`, `inbox/direction.ts`, `task-recompute.ts:54-74`) + one equivalent-mutant disable comment in `dashboard-metrics.ts` |
| What Spec A (only spec with a logged plan-check round) approved | `db-rls.ts` only, one file, chosen specifically for RLS security relevance |
| Does the build match Spec A | No — zero file overlap |
| Does the build match anything | Yes — near-verbatim match to a *second*, undated-in-log Spec B found at a different path (`runs/` not `loop-team/runs/`), whose own claimed 2-round plan-check history has no corroborating log file anywhere in the worktree |
| Is the built scope superset or disjoint vs. Spec A | Disjoint — `db-rls.ts` is untouched |
| Was Spec A's stated security goal met | No |
| Engineering merit of what was actually built, on its own terms | The exclusion/`testFiles` reasoning is specific and falsifiable (names exact mechanisms/tests/symptoms), a genuine strength; one real internal tension exists between Spec B's hand-listed `testFiles` and the coverage-completeness philosophy Spec A's own round-1 plan-check established as the safer pattern |
| Doc deliverables | Both specs' doc ACs (Spec A's `run_log.md`, Spec B's `web/docs/mutation-testing.md`) are unmet — neither file exists, though built artifacts reference the Spec-B path as if it does |
| Nnamdi approval scope | Concept-level only ("Stryker adoption" as 1 of 5 tools) — no file-scope or classification detail in the decision-log entry |

---

## Sources / files read directly (for reproducibility)

- `~/Claude/loop-worktrees/padsplit-stryker-mutation-testing/web/stryker.config.mjs` (full, 79 lines)
- `~/Claude/loop-worktrees/padsplit-stryker-mutation-testing/loop-team/runs/2026-07-10_stryker-mutation-testing/specs/spec.md` (full, Spec A)
- `~/Claude/loop-worktrees/padsplit-stryker-mutation-testing/loop-team/runs/2026-07-10_stryker-mutation-testing/plan_check_log.md` (full)
- `~/Claude/loop-worktrees/padsplit-stryker-mutation-testing/runs/2026-07-10_stryker-mutation-testing/specs/spec.md` (full, Spec B — found via `diff` against Spec A after git status showed a suspicious duplicate untracked path)
- `~/Claude/loop-worktrees/padsplit-stryker-mutation-testing/research/stryker-mutation-testing-integration-2026-07-10.md` (partial — header + tail sections read directly)
- `git status`, `git diff --stat`, `git diff -- package.json web/package.json web/vitest.config.ts web/src/lib/dashboard-metrics.ts`, `git log --oneline`, `git merge-base HEAD main` — all run live in the worktree
- `find`/`ls` direct filesystem checks for `web/docs/mutation-testing.md`, `loop-team/runs/2026-07-10_stryker-mutation-testing/run_log.md`, `research/loop-improvement-db-test-isolation-and-rls-catching-2026-07-09.md` (all confirmed absent)
- `~/Claude/loop/fix_plan.md:7895-7898` (the Decisions-log entry)
- `stat -f "%Sm %N"` on all key files, for the mtime timeline in §0
