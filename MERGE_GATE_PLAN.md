# Merge-Gate Architecture Plan — Verified and Revised

Revision of the original merge-gate issue, checked against this repository, the
connected GitHub account, and GitHub feature gating. Verification session:
2026-08-09. Claims that could not be checked from the available tooling are
marked, not silently kept.

## 1. Verification verdict

| # | Original claim | Verdict | Evidence |
|---|---|---|---|
| 1 | "NEO-Venturez has GitHub Team and four private repositories" | **Contradicted as stated** | The connected GitHub integration sees no NEO-Venturez organization. Every visible repository lives under the personal account `Eobodoechine`. `NEO-Venturez/wf-fix-test` appears only as a fixture/config string in `closure-adapter/branches.conf` and its tests. |
| 2 | `gate-defs`, `wf-fix-test`, `taxahead`, `pms-cockpit` exist as rollout targets | **Contradicted as named** | None exist under those names in the accessible account. Closest real repos: this repo (central tooling), `Eobodoechine/wf-scope-test-20260808`, `Eobodoechine/remix-of-taxahead.ai`, and `Eobodoechine/prove-rulesets-probe`. No PMS/PadSplit repo is visible at all; the PMS checkout in `control-plane/projects/padsplit-cockpit.json` is a local path. |
| 3 | TaxAhead `main` unprotected; `Mission Slice main` runs post-push; `record-evidence` failed and was never retried; no recovery issue | **Unverifiable from this session** | `remix-of-taxahead.ai` is private and attaching it required an interactive approval that was not available. Treat as asserted; verify in Phase −1 below. |
| 4 | The current shared gate uses `pull_request_target` and executes PR code with elevated permissions | **Unverifiable** | This repository contains no `.github/workflows` directory at all; wherever that shared gate lives, it is not here. The general risk is real and the replacement requirements stand regardless. |
| 5 | An organization ruleset on GitHub Team can centrally require the gate | **Likely wrong — plan-gated** | "Require workflows to pass before merging" is a GitHub Enterprise Cloud ruleset rule (the issue's own citation is under `enterprise-cloud@latest`). Organization-level rulesets are also Enterprise-gated to the best available knowledge (docs.github.com was egress-blocked from this session; confirm with one click before Phase 4). The plan must not depend on either. |
| 6 | Skipped jobs can satisfy required checks unless a final `always()` job rejects them | **Confirmed** | Documented GitHub behavior; also matches the fail-closed rule already implemented locally in `closure-adapter/recompute_verdict.sh` (every check-run with the required name must conclude `success`; missing → RED). |
| 7 | Required checks must pass on the latest SHA | **Confirmed** | Standard GitHub behavior; "require branches to be up to date" or merge queue handles staleness. |
| 8 | Post-merge workflows cannot retroactively block a merge; correctness proof must move pre-merge | **Confirmed** | Sound reasoning; no change. |
| 9 | Implied: rollout can make the listed project checks required now | **Contradicted by the control plane** | `control-plane/projects/taxahead.json` records `typescript` FAIL (COMPILE), `ui-harness` FAIL (1,872 ESLint problems, Vitest cannot start), and several E2E FAILs. Making `tsc`/lint/Vitest required today blocks every TaxAhead merge on day one. PMS is in the same state (`pms-sync` FAIL, database blocked). A burn-down/ratchet step is mandatory. |

Two more constraints the original plan missed:

- **Merge queue needs an organization.** GitHub merge queues are not available on
  personal-account repositories (and private-repo availability is
  plan-gated). "Be current with main or use merge queue" collapses to
  "require branches to be up to date" until the repos live in an org.
- **Personal-account repos cannot be governed.** The owner of a personal repo
  can always edit or delete its rulesets. "No ordinary admin bypass" is only
  enforceable inside an organization with restricted roles. This is the
  strongest argument for actually creating/using the org — stronger than the
  central-ruleset convenience the original plan cited.

## 2. Corrected ground truth

| Planned name | What actually exists today | Action needed |
|---|---|---|
| `NEO-Venturez` (org, Team plan) | Not visible to the connected tooling | Create the org or install/authorize the GitHub integration on it; record the actual plan tier |
| `gate-defs` | Does not exist; central gate logic lives locally in this repo (`closure-adapter/`, hooks) | Create it (or designate this repo) and port the gate as a reusable workflow |
| `wf-fix-test` | Only a fixture string; `Eobodoechine/wf-scope-test-20260808` and `Eobodoechine/prove-rulesets-probe` are the real sandboxes | Pick one sandbox repo and update `closure-adapter/branches.conf` when it moves |
| `taxahead` | `Eobodoechine/remix-of-taxahead.ai` (private, personal account) | Transfer into the org (org rules cannot cover a personal repo) |
| `pms-cockpit` | No visible repo; local checkout only | Create/push the repo, then treat like TaxAhead |

Current enforcement is **local-only**: the `closure-adapter` Hermes plugin
blocks `kanban_complete` unless GitHub check-runs for the mapped repo/SHA are
all green (`recompute_verdict.sh`, fail-closed). Nothing on GitHub itself
prevents a merge today. The plan's core diagnosis — the lock is installed
after the door — is correct and extends further than the issue stated: there
is no GitHub-side lock anywhere yet.

## 3. Phase −1 — Preconditions and ground-truth audit (new)

Nothing else starts until each row of the table in §2 is resolved and the
following are read back through the API and recorded:

1. Org existence, plan tier, and whether org rulesets / required workflows /
   merge queue are actually offered on that tier (one docs check each).
2. Effective rulesets and branch protection on every product repo
   (`GET /repos/{owner}/{repo}/rules/branches/main`).
3. The real workflow files on each product repo's default branch — confirm or
   refute the `pull_request_target` claim and the `record-evidence` failure
   history (Actions run list, filtered to the default branch).
4. A name map committed to `gate-defs` so no document refers to repos that do
   not exist.

## 4. Architecture — two tracks instead of one

The layering (central gate → forced adoption → project adapter → historical
audit) survives. The forcing mechanism must not assume Enterprise.

**Track A — works on Team (and during any personal-account interim). Default.**

- `gate-defs` publishes the gate as a **reusable workflow** (`workflow_call`).
- Each product repo has a thin adapter workflow that calls it, pinned to a
  major tag (`gate-defs/.github/workflows/gate.yml@v1`). A SHA pin would
  freeze propagation of central fixes; a tag pin trades a small trust window
  for central updatability — acceptable because `gate-defs` itself is locked
  down hardest.
- Enforcement is a **ruleset per product repo** (org-level only if the tier
  turns out to support it) requiring two status checks:
  `organization-merge-gate` (from the central gate) and `project-required-ci`.
- Drift control, since Track A cannot make GitHub itself refuse a missing
  adapter: CODEOWNERS on `.github/workflows/**` + required code-owner review,
  and a scheduled conformance audit in `gate-defs` that reads every product
  repo's adapter via the API and opens a `release-blocker` issue on drift.

**Track B — if/when the org is on Enterprise Cloud.**

- Convert the same gate into an organization required workflow
  ("Require workflows to pass before merging") in an org ruleset, exactly as
  the original plan described. Adapters keep running project tests; the
  central gate stops being copy-dependent.

**Known limit of Track A (state it, don't hide it):** a required status check
produced by a workflow in the same repository can be spoofed by a PR that
edits that workflow, because `pull_request` runs use the workflow file from
the PR's merge commit. Mitigations, in order: code-owner review on workflow
paths (above), the central gate re-reading its contracts from the **base**
branch and failing if protected files differ, and optionally a push ruleset
restricting `.github/workflows/**` changes to the governor process. Track B
eliminates the class.

## 5. Revised phases

**Phase 0 — Emergency rule (unchanged).** Freeze direct pushes to product
`main`; PRs only; nothing is "passed/released" while any required main
workflow is red; the asserted TaxAhead `record-evidence` failures are treated
as unresolved release blockers until Phase −1 confirms or refutes them.

**Phase 1 — Build the central gate in `gate-defs`.** All eleven original
requirements stand (plain `pull_request` + `merge_group`, never
`pull_request_target`, `contents: read`, `persist-credentials: false`, no
production secrets, contracts from the base branch, protected-file check,
single `organization-merge-gate` result, no path filters, fail on
failed/cancelled/timed-out/missing/skipped dependencies, automated tests of
the failure behavior). Two additions:

- Build it as `workflow_call` so Track A and Track B share one implementation.
- The final aggregation job must compare `needs` against a **declared list of
  expected job names**, not just iterate over whatever `needs` contains — a
  renamed or deleted job silently vanishes from `needs` and would otherwise
  pass unnoticed. (This mirrors the all-runs-must-pass rule already proven in
  `closure-adapter/recompute_verdict.sh`.)

**Phase 2 — Project adapters, with a ratchet.** One
`project-required-ci` final job per repo, `if: always()`, exact-success
check, no `continue-on-error`, as originally specified. But the control-plane
contracts show TaxAhead's `tsc`, lint, and test harness are currently red, so:

1. Start with the checks that are green today (build, Vitest units that pass,
   Deno edge tests) as required.
2. Burn the red checks down to green on a branch (`tsc` first — the
   control-plane contract already sequences `compile-contract-repair` first).
3. Ratchet each check into the required set the day it turns green on `main`.
   Never flip a red check to required; it invites bypass pressure that
   discredits the whole gate. PMS follows the same ratchet; its
   `continue-on-error` typecheck is either fixed-and-required or removed, as
   the original plan said.

**Phase 3 — Evidence split (unchanged in substance).**
`evidence-preflight` pre-merge (synthetic storage, validation, reconciliation,
concurrency, dry-run projection; cannot write the real evidence branch);
`record-evidence` post-merge (immutable receipt for the accepted SHA; failure
blocks release and opens a recovery issue). Additions: the post-merge job runs
with minimal permissions (`contents: write` scoped to the evidence branch
mechanism, `issues: write`), one `concurrency` group per repo so receipts
serialize, and receipt writes are idempotent keyed by SHA so retries are safe.

**Phase 4 — Rulesets.** As original, minus the Enterprise assumptions:
required PR, the two required checks above, require-up-to-date (merge queue
only after the repos are org-owned and the tier supports it), no force
pushes, no deletions, checks pinned to the GitHub Actions app as source, empty
bypass list. Sequence: destructive negative tests in the sandbox repo first →
Evaluate mode on product repos → canary matrix → Active. `gate-defs` gets its
own stricter ruleset. If org rulesets are unavailable on the actual tier,
replicate the per-repo ruleset from a JSON template in `gate-defs` via the
API, and let the Phase 4 conformance audit diff live rulesets against the
template on a schedule — automation, not humans, keeps the copies identical.

**Phase 5 — Failure recovery (unchanged).** Final `if: always()` recovery job
on every post-main workflow: idempotent issue (search-before-create on a
stable title key), `release-blocker` + `ci-recovery` labels, full run
metadata, project marked BLOCKED, owner assigned, one automatic retry only
for classified transient infrastructure failures, repair PR for everything
else, closure only on a proven fixing/reverting SHA. Metadata-only watchdog
for failed main runs without recovery issues; it never downloads or executes
artifacts.

**Phase 6 — Prove enforcement (unchanged).** The original thirteen-case
matrix stands, plus one Track A-specific case: a PR that edits the adapter
workflow to fake `project-required-ci` must be caught (by code-owner review
or the central gate's protected-file check) — this is the spoofing scenario
in §4 and it needs a test, not an assumption.

**Phase 7 — Historical retest (unchanged).** Full default-branch Actions
audit, per-failure disposition, transient reruns on the same SHA, code
failures reproduced on the old SHA and shown fixed on the fixing SHA, no
destructive deployment reruns, recovery issues for everything unresolved,
final ledger. An unrelated later green run proves nothing about an earlier
failure.

## 6. Revised difficulty

| Item | Original | Revised | Why |
|---|---|---|---|
| Organization ruleset | Easy | **Blocked-then-easy** | Depends on org existing, repos transferred in, and tier support; the fallback is templated per-repo rulesets plus a conformance audit |
| Central workflow | Medium | Medium | Unchanged; `workflow_call` port is straightforward |
| Project adapters | Easy–medium | **Medium** | The ratchet (red baseline) is the real work, not the YAML |
| Evidence split + recovery | Medium–difficult | Medium–difficult | Unchanged |
| Historical retest | Variable | Variable | Unchanged |
| **Phase −1 preconditions** | absent | **New, first** | Org/tier/repo-transfer questions gate everything else |

## 7. Migration prompt for each product repo

Same as the original prompt, with three amendments:

- Header gains `Track: [A|B]` and `Plan tier verified: [TIER, DATE]`.
- Task 2 becomes: "Add or verify one final job named `project-required-ci`
  whose success requires the exact declared set of required jobs; checks not
  yet green on main are listed under RATCHET with a target date, and a check
  is added to the required set the day it is green on main — never before."
- Task 15 gains: "Also read back the adapter workflow and confirm it matches
  the canonical template in `gate-defs` at the pinned tag."

PASS-ONLY-IF and all RULES lines are unchanged, including: never report
partial work as PASS.
