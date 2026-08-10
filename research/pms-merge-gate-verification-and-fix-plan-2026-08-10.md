# PMS merge-gate: verification of codex repair + execution plan for remaining debt

Date: 2026-08-10
Scope: `NEO-Venturez/pms-cockpit` (PMS), `NEO-Venturez/gate-defs` (upstream gate definitions),
`Eobodoechine/loop-engineering` (this repo — consumes the gate via `closure-adapter/`).
Status of codex work under review: **BLOCKED — draft PR #13 published, not merged.**

This document is written to be self-sufficient: an agent with GitHub access to the two
NEO-Venturez repos can verify every claim and execute every phase without other context.

---

## 1. Context — what this gate is and why it matters

- `NEO-Venturez/pms-cockpit` has a workflow `.github/workflows/slice-closure-gate.yml`.
  It produces a GitHub **check run named `slice-closure-gate / slice-closure-gate`**
  (workflow name / job name).
- That exact check name is a hard dependency of this repo:
  `closure-adapter/recompute_verdict.sh` + `closure-adapter/kanban_closure_gate.plugin.py`
  gate `kanban_complete` by querying `gh api repos/<owner>/<repo>/commits/<HEAD_SHA>/check-runs`
  and requiring ≥1 run with that name where **all** such runs conclude `success`.
  Missing or non-success → RED → kanban closure blocked (fail-closed). The legacy commit
  status `slice-gate-verdict` is data-only and never sufficient.
  **Consequence: never rename the workflow or job in `slice-closure-gate.yml`; a rename
  silently turns every kanban closure RED.**
- The workflow previously ran on `pull_request_target`. With any checkout of the PR head,
  that trigger runs untrusted PR code with a write-scoped token + secrets ("pwn request").
  Codex's PR #13 switches triggers to `pull_request` + `merge_group`. That is the standard,
  correct security fix.
- The workflow delegates gate logic to `NEO-Venturez/gate-defs`, **pinned by commit SHA**
  inside `slice-closure-gate.yml` (or a script it calls). The pin is the crux of the
  remaining red gate — see §3.

## 2. Verification of the codex report

Constraint: `NEO-Venturez/pms-cockpit` and `NEO-Venturez/gate-defs` are private; this
session's GitHub scope is `eobodoechine/loop-engineering` only, and the `add_repo`
attach required an interactive approval that was not granted. So GitHub-side claims are
classified below as *verified locally*, *consistent-unverified*, or *disputed*.

### 2.1 Verified against local evidence (this repo)

| Claim | Verdict |
|---|---|
| The gate's check name and fail-closed consumer exist as described | ✅ `closure-adapter/` requires `slice-closure-gate / slice-closure-gate` at head SHA |
| Trigger swap preserves the check name (workflow+job names untouched) | ✅ safe for the closure-adapter, *provided* the PR really only changed the `on:` block |

### 2.2 Consistent but unverified (needs repo access; commands in §4 Phase 1)

- PR #13 exists, is draft, head commit `53d857121d851aa3559db5cf1e03fe54e1dba48f`,
  and touches only `.github/workflows/slice-closure-gate.yml`.
- Typecheck and named-test-debt checks green on the PR.
- `main` has no branch protection; effective rules `[]`.
- gate-defs old pin `b552…` incorrectly requires `gates/contract.yml`; current
  `f09fd46…` fixes that fallback but not `merge_group` payloads.

### 2.3 Findings the codex report gets wrong or underplays

1. **The "proven upstream debt" framing is half-wrong.** The *bug* lives upstream in
   gate-defs, but the *remedy for the red PR gate* is PMS-local: bump the pinned
   gate-defs SHA in `slice-closure-gate.yml` from `b552…` to `f09fd46…` (which codex
   itself states fixes the `gates/contract.yml` fallback). That is a one-line,
   PMS-only change squarely inside the stated scope, and codex did not make it.
   Only true `merge_group` payload support genuinely requires touching gate-defs.
2. **The `merge_group` trigger added in PR #13 is currently dead code, twice over.**
   (a) Merge queue only dispatches `merge_group` events when a ruleset/branch protection
   with required checks exists — effective rules are `[]`. (b) The org is on **GitHub
   Team**; GitHub's merge queue is available for public org repos and for private repos
   only on Enterprise Cloud. If pms-cockpit is private (it is unreadable
   unauthenticated, consistent with private), `merge_group` cannot fire at all on this
   plan. Harmless future-proofing, but it means "gate-defs lacks merge_group support"
   is **not the blocking debt** — on Team, the enforcement path is branch
   protection / rulesets over `pull_request` checks (codex's own "Track A"), which
   needs §4 Phases 3 and 5, not gate-defs work.
3. **Minor risk to confirm during review:** `pull_request` (unlike `pull_request_target`)
   gets no secrets on fork PRs. If `slice-closure-gate.yml` checks out the private
   gate-defs repo using a PAT/secret, fork PRs will show the gate as failed/skipped.
   Acceptable for an org-internal repo, but verify same-repo PRs are the only intended
   audience.

**Bottom line: codex's security correction is sound and its facts are plausible, but its
"BLOCKED on upstream" conclusion is wrong — the red observation gate is fixable with a
second PMS-only one-line PR (pin bump), and enforcement on the Team plan never needed
merge_group in the first place.**

## 3. The remaining issue, precisely

The slice-closure observation gate is RED on PRs because `slice-closure-gate.yml` pins
gate-defs at `b552…`, whose logic unconditionally requires a file `gates/contract.yml`
that pms-cockpit does not have. gate-defs `f09fd46…` already fixes that fallback.
Nothing upstream blocks going green on PR events — only the pin bump does. Independent,
lower-priority debt: gate-defs cannot parse `merge_group` event payloads, which only
matters if/when the org gains merge-queue capability (Enterprise Cloud or public repo).

## 4. Execution plan (phased; each phase independently landable)

> Model-routing guidance for the executing system: Phases 1–3 are mechanical
> (cheap/fast model, e.g. Haiku/Sonnet-class). Phase 4 needs code comprehension in an
> unseen repo (Sonnet-class or better). Phase 5 is config + judgment (Sonnet-class).

### Phase 0 — Access (blocker for everything below)
Attach `NEO-Venturez/pms-cockpit` (push) and `NEO-Venturez/gate-defs` (push) via the
session's `add_repo`, or run with a `gh` auth that has write on both.

### Phase 1 — Re-verify codex's claims (~5 min, read-only)
```
gh pr view 13 -R NEO-Venturez/pms-cockpit --json isDraft,headRefOid,files,mergeable,statusCheckRollup
# expect: draft=true, headRefOid=53d857121d851aa3559db5cf1e03fe54e1dba48f,
#         files == [.github/workflows/slice-closure-gate.yml]
gh api repos/NEO-Venturez/pms-cockpit/rules/branches/main        # expect []
gh api repos/NEO-Venturez/pms-cockpit/branches/main/protection   # expect 404
gh api repos/NEO-Venturez/gate-defs/commits/f09fd46 --jq .sha    # resolve full SHA
grep -n "b552" .github/workflows/slice-closure-gate.yml          # find the pin (in pms-cockpit clone)
```
Confirm the PR diff is exactly `on: pull_request_target` → `on: pull_request` +
`merge_group` and check whether the same file checks out gate-defs with a secret
(fork-PR caveat, §2.3.3). If any expectation fails, stop and report — do not proceed
on stale facts.

### Phase 2 — Merge PR #13 (needs explicit human go: "merge PR 13")
Mark ready-for-review and merge. Zero enforcement risk: rules are `[]`, so nothing can
start blocking merges as a side effect. This closes the `pull_request_target` hole and
should not wait on any other phase.

### Phase 3 — PMS-only pin bump (fixes the red gate; new small PR to pms-cockpit)
1. In pms-cockpit, locate every occurrence of the old gate-defs pin:
   `grep -rn "b552" .github/ scripts/ Makefile* 2>/dev/null`
2. Replace with the full SHA of gate-defs `f09fd46…` (from Phase 1). Do not switch to a
   branch ref — keep SHA pinning (supply-chain hygiene).
3. Open PR; confirm on the PR itself that the `slice-closure-gate / slice-closure-gate`
   check now concludes `success` (this is the acceptance test — the gate goes green
   because the `gates/contract.yml` false requirement is gone at `f09fd46`).
4. Do NOT rename the workflow or job (see §1 consumer contract). Merge on green.

### Phase 4 — gate-defs merge_group support (upstream; only needed for a future merge queue)
Discovery first, since the executing agent hasn't seen gate-defs:
1. `grep -rn "event.pull_request\|GITHUB_HEAD_REF\|pull_request.head.sha\|github.head_ref" .`
   in gate-defs — every hit is a site that assumes a PR payload.
2. Add an event branch: when `github.event_name == "merge_group"`, take the verdict SHA
   from `github.event.merge_group.head_sha` and the ref from
   `github.event.merge_group.head_ref` (refs look like
   `refs/heads/gh-readonly-queue/<base>/pr-<N>-<sha>`; parse `<N>` from the ref if a PR
   number is needed, and skip PR-comment/annotation steps that require a PR context).
3. Fail-closed default: unknown event name → RED with a message, never silent pass.
4. Add a fixture test with a recorded `merge_group` webhook payload alongside the
   existing pull_request fixtures; run gate-defs' own CI.
5. After merging, bump the pms-cockpit pin again (repeat Phase 3 with the new SHA).
Priority: LOW until the org has Enterprise Cloud or the repo goes public — merge_group
cannot fire on GitHub Team + private (§2.3.2).

### Phase 5 — Turn observation into enforcement (the actual end-goal)
Only after Phase 3 has the gate reliably green on PRs for a soak period (suggest ≥5
consecutive green PRs or 1 week):
```
gh api -X POST repos/NEO-Venturez/pms-cockpit/rulesets --input - <<'JSON'
{ "name": "main-required-checks", "target": "branch", "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "rules": [ { "type": "required_status_checks", "parameters": {
      "strict_required_status_checks_policy": true,
      "required_status_checks": [ { "context": "slice-closure-gate" } ] } },
    { "type": "pull_request", "parameters": { "required_approving_review_count": 0,
      "dismiss_stale_reviews_on_push": false, "require_code_owner_review": false,
      "require_last_push_approval": false, "required_review_thread_resolution": false,
      "allowed_merge_methods": ["merge", "squash", "rebase"] } } ] }
JSON
```
Adjust `context` strings to the exact check names shown on a recent PR (also add
typecheck and the named-test-debt gate — they are already green and ratcheted).
Start with `"enforcement": "evaluate"` if a dry-run period is wanted, then flip to
`active`. This is the Track A (GitHub Team) enforcement path; no merge queue involved.

## 5. Decision needed from the human
- "merge PR 13" — Phase 2 (codex already asked; still pending).
- Approve `add_repo` for the two NEO-Venturez repos (Phase 0) so Phases 1/3 can run.
- Green-light Phase 3 as a follow-up PMS-only PR (recommended: yes, it is the actual
  unblock; codex's BLOCKED verdict dissolves once it lands).
