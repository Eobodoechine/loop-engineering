# Merge-Gate Architecture Plan — Verified and Revised

> **Implementers:** this file is the rationale and the verification record.
> The binding implementation contract — exact check names, full workflow YAML,
> the evidence receipt JSON Schema, the ruleset payload, and the acceptance
> matrix — is in **`MERGE_GATE_SPEC.md`**, same repo and branch. Build from
> the spec; read this for why.

Revision of the original merge-gate issue, checked against this repository, the
connected GitHub account, and GitHub feature gating. Verification session:
2026-08-09. Claims that could not be checked from the available tooling are
marked, not silently kept.

## 1. Verification verdict

| # | Original claim | Verdict | Evidence |
|---|---|---|---|
| 1 | "NEO-Venturez has GitHub Team and four private repositories" | **Org confirmed; tier still unverified** | An independent PMS Cockpit session (2026-08-09) inspected the live `NEO-Venturez/pms-cockpit` remote, so the org exists. It is invisible to *this* session's GitHub integration, which returns only personal `Eobodoechine` repos — an access-scoping gap, not an existence gap. The **Team-vs-Enterprise tier remains unverified** and still gates §4. |
| 2 | `gate-defs`, `wf-fix-test`, `taxahead`, `pms-cockpit` exist as rollout targets | **Partly confirmed** | `NEO-Venturez/pms-cockpit` confirmed live. The other three are unconfirmed from any session so far; `NEO-Venturez/wf-fix-test` currently appears here only as a fixture string in `closure-adapter/branches.conf`. Confirm each by name in Phase −1 rather than assuming the set of four. |
| 3 | TaxAhead `main` unprotected; `Mission Slice main` runs post-push; `record-evidence` failed and was never retried; no recovery issue | **Unverifiable from this session** | The TaxAhead repo is private and attaching it required an interactive approval that was not available. Treat as asserted; verify in Phase −1 below. |
| 4 | The current shared gate uses `pull_request_target` and executes PR code with elevated permissions | **Corroborated** | The PMS session found an unmerged `gate/observe` adapter in `NEO-Venturez/pms-cockpit` using `pull_request_target`. It is unmerged and observe-only, so it is not yet enforcing anything — but it confirms the pattern is in play and must not be merged as-is. Phase 1's replacement requirements stand. |
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
| `NEO-Venturez` (org, Team plan) | **Exists** (confirmed via the PMS session), but invisible to this session's integration | Authorize the GitHub integration on the org so automation can read it; record the actual plan tier |
| `gate-defs` | Unconfirmed; central gate logic currently lives in this repo (`closure-adapter/`, hooks) | Confirm or create it, then port the gate as a reusable workflow |
| `wf-fix-test` | Unconfirmed as a live repo; appears here as a fixture string. `Eobodoechine/wf-scope-test-20260808` and `Eobodoechine/prove-rulesets-probe` are known-real sandboxes | Confirm the sandbox repo and update `closure-adapter/branches.conf` if it moves |
| `taxahead` | Unconfirmed under the org; `Eobodoechine/remix-of-taxahead.ai` (private, personal) is the known checkout | Determine which is canonical; if it is the personal repo, transfer it into the org (org rules cannot cover a personal repo) |
| `pms-cockpit` | **`NEO-Venturez/pms-cockpit` exists and is live** | No creation needed. Already carries an unmerged `gate/observe` adapter and an unmerged named-test-debt ratchet branch |

Current enforcement is **local-only**: the `closure-adapter` Hermes plugin
blocks `kanban_complete` unless GitHub check-runs for the mapped repo/SHA are
all green (`recompute_verdict.sh`, fail-closed). On PMS the `gate/observe`
adapter is unmerged and observe-only, so it enforces nothing either. No
configured required check on any product `main` has been demonstrated by any
session to date. The plan's core diagnosis — the lock is installed after the
door — is correct and extends further than the issue stated: there is no
GitHub-side lock anywhere yet.

Two pieces of work already exist on PMS and should be reused rather than
rebuilt: the unmerged **named-test-debt ratchet branch** (which is exactly the
Phase 2 ratchet, already started) and the unmerged **`gate/observe` adapter**
(whose observe-only posture is the right rollout shape, but whose
`pull_request_target` trigger must be replaced per Phase 1 before it merges).

## 3. Phase −1 — Preconditions and ground-truth audit (new)

Nothing else starts until each row of the table in §2 is resolved and the
following are read back through the API and recorded:

1. Plan tier of the (confirmed-to-exist) `NEO-Venturez` org, and whether org
   rulesets / required workflows / merge queue are actually offered on that
   tier (one docs check each). Also authorize the GitHub integration on the
   org — automation that cannot see the org cannot verify or enforce anything
   in it, which is precisely why this plan's first draft mis-read the ground
   truth.
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

## 8. Cross-session coordination (learned the hard way)

A PMS Cockpit session stalled for 30 minutes and made no changes because it
looked for the plan branch and `MERGE_GATE_PLAN.md` **inside
`NEO-Venturez/pms-cockpit`**. The plan does not live there and never did:

| Field | Value |
|---|---|
| Repo | `Eobodoechine/loop-engineering` |
| Branch | `claude/merge-gate-architecture-plan-m012ag` |
| Path | `MERGE_GATE_PLAN.md` |

Rules that follow, so this does not recur:

- **The plan is central; the adapters are local.** Any migration prompt sent
  to a product repo must carry the plan's repo, branch, and commit SHA
  explicitly. A bare branch name is ambiguous across repos and will be
  resolved against the wrong remote.
- **A missing artifact is a lookup failure until proven otherwise.** "Branch
  does not exist in this remote" means check which remote before concluding
  the artifact was never produced.
- **Credentials are a precondition, not a discovery.** A session that cannot
  authenticate to GitHub cannot read back rulesets, and reading back rulesets
  is the only accepted proof of enforcement. Verify `gh auth status` at the
  start of a rollout slice, not at the end.
- The PMS session's refusal to change anything while blocked was the correct
  behavior and should be preserved: no ruleset or gate change ships without
  a read-back.
