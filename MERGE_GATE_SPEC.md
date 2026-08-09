# Merge-Gate Implementation Spec (normative)

Companion to `MERGE_GATE_PLAN.md`. The plan explains *why*; this file defines
*exactly what to build*. It is written to be implemented by an agent with no
prior context.

**Canonical location of this spec** — cite all three fields when handing work
to another session:

| Field | Value |
|---|---|
| Repo | `Eobodoechine/loop-engineering` |
| Branch | `claude/merge-gate-architecture-plan-m012ag` |
| Paths | `MERGE_GATE_SPEC.md` (normative), `MERGE_GATE_PLAN.md` (rationale) |

This spec does **not** live in `taxahead` or `pms-cockpit`. If it is absent
from a product checkout, that is expected — fetch it from the repo above.

MUST / MUST NOT / SHOULD are binding. Anything not stated here is
implementer's choice, except names in §1, which are fixed.

---

## 1. Normative names

These strings are **exact, case-sensitive, and identical across every product
repository**. They are the contract between the workflows and the rulesets.
Do not localize, prefix, or pluralize them.

| Purpose | Exact string | Produced by |
|---|---|---|
| Central gate required check | `organization-merge-gate` | Job in the project adapter that wraps the central reusable workflow |
| Project tests required check | `project-required-ci` | Final aggregation job in the project adapter |
| Adapter workflow file | `.github/workflows/required-ci.yml` | Each product repo |
| Central reusable workflow | `gate-defs/.github/workflows/merge-gate.yml` | `gate-defs` |
| Central workflow pin | `@v1` (moving major tag) | `gate-defs` |
| Post-merge receipt workflow | `.github/workflows/record-evidence.yml` | Each product repo |
| Evidence branch | `evidence` (orphan branch) | Each product repo |
| Recovery labels | `release-blocker`, `ci-recovery` | Each product repo |

Exactly **two** required status checks are configured in the ruleset:
`organization-merge-gate` and `project-required-ci`. No others. Every project
test is a *dependency* of `project-required-ci`, never a directly required
check — that keeps the ruleset stable while the test set evolves.

### 1.1 Check-name mechanics (read this before writing YAML)

The status-check context GitHub records is the **job name**, not the workflow
name. For a job that calls a reusable workflow, the contexts become
`<caller-job-name> / <inner-job-name>` — nested and unstable.

Therefore the adapter MUST NOT expose the reusable call directly as the
required check. It MUST declare a plain job literally named
`organization-merge-gate` that depends on the call and asserts its result.
That yields the exact flat context `organization-merge-gate`. The same applies
to `project-required-ci`.

---

## 2. Central reusable workflow — `gate-defs/.github/workflows/merge-gate.yml`

Security requirements, all mandatory:

- Triggered only via `workflow_call` (callers use `pull_request` + `merge_group`).
- MUST NOT use `pull_request_target` anywhere in the chain.
- MUST NOT check out or execute pull-request head code.
- `permissions:` read-only; no deployment or production secrets are passed.
- All checkouts use `persist-credentials: false`.
- Contracts are read from the **base** branch, never the PR head.

```yaml
name: merge-gate

on:
  workflow_call:
    inputs:
      protected_paths:
        description: Newline-separated globs requiring the governor process to change.
        required: false
        type: string
        default: |
          .github/workflows/**
          .gate/**
          CODEOWNERS
          .github/CODEOWNERS
    outputs:
      result:
        description: '"pass" only when every gate check succeeded.'
        value: ${{ jobs.summarize.outputs.result }}

permissions:
  contents: read
  pull-requests: read

jobs:
  # Reads gate contracts from the BASE branch. PR code is never checked out.
  contracts:
    runs-on: ubuntu-latest
    steps:
      - name: Check out base branch only
        uses: actions/checkout@v4
        with:
          # Exactly one of these is non-null for pull_request / merge_group.
          ref: ${{ github.event.pull_request.base.sha || github.event.merge_group.base_sha }}
          persist-credentials: false
      - name: Validate gate contracts exist and parse
        run: |
          set -euo pipefail
          test -f .github/workflows/required-ci.yml \
            || { echo "::error::adapter .github/workflows/required-ci.yml missing on base"; exit 1; }
          python3 -c 'import sys,yaml; yaml.safe_load(open(".github/workflows/required-ci.yml"))'

  # Detects edits to protected paths WITHOUT fetching or running PR code.
  protected-paths:
    runs-on: ubuntu-latest
    steps:
      - name: Collect changed paths via API
        id: changed
        env:
          GH_TOKEN: ${{ github.token }}
          REPO: ${{ github.repository }}
          PR: ${{ github.event.pull_request.number }}
          BASE: ${{ github.event.merge_group.base_sha }}
          HEAD: ${{ github.event.merge_group.head_sha }}
        run: |
          set -euo pipefail
          if [ -n "${PR:-}" ]; then
            gh api --paginate "repos/$REPO/pulls/$PR/files" --jq '.[].filename' > changed.txt
          else
            gh api "repos/$REPO/compare/$BASE...$HEAD" --jq '.files[].filename' > changed.txt
          fi
          echo "count=$(wc -l < changed.txt)" >> "$GITHUB_OUTPUT"
      - name: Fail closed on unapproved protected-path edits
        env:
          PROTECTED: ${{ inputs.protected_paths }}
          # Governor process: a repo-admin applies this label after review.
          LABELS: ${{ toJSON(github.event.pull_request.labels.*.name) }}
        run: |
          set -euo pipefail
          python3 - <<'PY'
          import fnmatch, json, os, sys
          globs = [g.strip() for g in os.environ["PROTECTED"].splitlines() if g.strip()]
          changed = [l.strip() for l in open("changed.txt") if l.strip()]
          labels = json.loads(os.environ.get("LABELS") or "[]")
          hits = [f for f in changed if any(fnmatch.fnmatch(f, g) for g in globs)]
          if hits and "gate-governor-approved" not in labels:
              print("::error::protected paths changed without governor approval:")
              for h in hits:
                  print(f"::error::  {h}")
              sys.exit(1)
          print(f"protected-path check clean ({len(changed)} files changed)")
          PY

  summarize:
    if: always()
    needs: [contracts, protected-paths]
    runs-on: ubuntu-latest
    outputs:
      result: ${{ steps.verdict.outputs.result }}
    steps:
      - id: verdict
        env:
          NEEDS_JSON: ${{ toJSON(needs) }}
          EXPECTED: contracts protected-paths
        run: |
          set -euo pipefail
          python3 - <<'PY'
          import json, os, sys
          needs = json.loads(os.environ["NEEDS_JSON"])
          expected = set(os.environ["EXPECTED"].split())
          actual = set(needs)
          missing, extra = expected - actual, actual - expected
          bad = {j: v["result"] for j, v in needs.items() if v["result"] != "success"}
          for label, val in (("missing", missing), ("unexpected", extra)):
              if val:
                  print(f"::error::{label} gate jobs: {sorted(val)}")
          if bad:
              print(f"::error::gate jobs not successful: {bad}")
          ok = not (missing or extra or bad)
          with open(os.environ["GITHUB_OUTPUT"], "a") as fh:
              fh.write(f"result={'pass' if ok else 'fail'}\n")
          sys.exit(0 if ok else 1)
          PY
```

---

## 3. Project adapter — `.github/workflows/required-ci.yml`

Identical skeleton in every product repo. Only the project job block and the
`EXPECTED` list differ.

```yaml
name: required-ci

on:
  pull_request:
  merge_group:

permissions:
  contents: read
  pull-requests: read

# Never cancel merge-queue runs; superseded PR runs may be cancelled.
concurrency:
  group: required-ci-${{ github.event.pull_request.number || github.run_id }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}

jobs:
  gate:
    uses: NEO-Venturez/gate-defs/.github/workflows/merge-gate.yml@v1

  # Flat, stable required context. See §1.1.
  organization-merge-gate:
    name: organization-merge-gate
    if: always()
    needs: [gate]
    runs-on: ubuntu-latest
    steps:
      - run: |
          set -euo pipefail
          echo "central gate result: ${{ needs.gate.result }} / ${{ needs.gate.outputs.result }}"
          [ "${{ needs.gate.result }}" = "success" ] || exit 1
          [ "${{ needs.gate.outputs.result }}" = "pass" ] || exit 1

  # ---- project jobs: edit per repo, keep EXPECTED below in sync ----
  typecheck:
    runs-on: ubuntu-latest
    steps: [{ uses: actions/checkout@v4, with: { persist-credentials: false } }]
      # ... npx tsc --noEmit
  unit:
    runs-on: ubuntu-latest
    steps: [{ uses: actions/checkout@v4, with: { persist-credentials: false } }]
      # ... vitest run
  build:
    runs-on: ubuntu-latest
    steps: [{ uses: actions/checkout@v4, with: { persist-credentials: false } }]
  evidence-preflight:
    runs-on: ubuntu-latest
    steps: [{ uses: actions/checkout@v4, with: { persist-credentials: false } }]
      # ... see §4
  # -----------------------------------------------------------------

  project-required-ci:
    name: project-required-ci
    if: always()
    needs: [typecheck, unit, build, evidence-preflight]
    runs-on: ubuntu-latest
    steps:
      - name: Assert the exact expected job set all succeeded
        env:
          NEEDS_JSON: ${{ toJSON(needs) }}
          # MUST equal the needs list above, space separated.
          EXPECTED: typecheck unit build evidence-preflight
        run: |
          set -euo pipefail
          python3 - <<'PY'
          import json, os, sys
          needs = json.loads(os.environ["NEEDS_JSON"])
          expected = set(os.environ["EXPECTED"].split())
          actual = set(needs)
          missing, extra = expected - actual, actual - expected
          # result is one of: success, failure, cancelled, skipped
          bad = {j: v["result"] for j, v in needs.items() if v["result"] != "success"}
          if missing:
              print(f"::error::required jobs absent from needs (renamed or deleted?): {sorted(missing)}")
          if extra:
              print(f"::error::jobs in needs but not in EXPECTED (update EXPECTED): {sorted(extra)}")
          if bad:
              print(f"::error::required jobs not successful: {bad}")
          sys.exit(1 if (missing or extra or bad) else 0)
          PY
```

Binding rules for the adapter:

- `project-required-ci` MUST use `if: always()`. Without it the job is skipped
  when a dependency fails, and a skipped required check can be treated as
  satisfied.
- The `EXPECTED` list MUST be maintained by hand and MUST equal `needs`. The
  mismatch check exists because a renamed or deleted job silently disappears
  from `needs` and would otherwise pass unnoticed.
- No required job may use `continue-on-error`.
- No `paths:` / `paths-ignore:` filters on the triggers. A path-filtered
  required check never reports on unrelated PRs and blocks merge forever.

### 3.1 Ratchet procedure (how a check becomes required)

TaxAhead and PMS both have red baselines today (`control-plane/projects/*.json`
records `tsc` FAIL/COMPILE, ESLint at 1,872 problems, PMS sync FAIL). A check
is added to `needs` + `EXPECTED` **only on the day it is green on `main`.**

1. Job exists in the adapter but is NOT in `needs`/`EXPECTED` → it runs, it is
   advisory, it cannot block.
2. Fix the underlying debt on a branch.
3. When it is green on `main`, add it to both `needs` and `EXPECTED` in one PR.
4. Record the date and the proving run URL in the repo's ratchet table.

Never add a red check to `EXPECTED`. Doing so freezes all merges and creates
pressure to bypass the gate, which destroys it.

---

## 4. Evidence: preflight vs receipt

| | `evidence-preflight` | `record-evidence` |
|---|---|---|
| When | pre-merge, in `required-ci.yml` | post-merge, on push to `main` |
| Question | "would evidence generation work?" | "record what was accepted" |
| Storage | synthetic/temp dir only | the real `evidence` branch |
| Writes evidence branch | MUST NOT | MUST |
| Blocks merge | yes | impossible — see below |
| Failure means | merge is refused | release is blocked + recovery issue |

`evidence-preflight` MUST exercise: receipt generation, schema validation,
reconciliation against a fixture, concurrent-update handling, and a dry-run
projection of the write. It MUST be given a temp path and MUST NOT hold
credentials for the evidence branch.

`record-evidence` MUST NOT be treated as proof that code was tested — it runs
after merge and cannot retroactively refuse anything. Everything that
establishes correctness runs pre-merge.

---

## 5. Evidence receipt schema (v1.0.0)

Storage path on the `evidence` branch, one file per accepted commit:

```
receipts/<YYYY>/<MM>/<full_40_char_commit_sha>.json
```

Idempotency: the key is `commit_sha`. If the file exists and is byte-identical,
the job succeeds without writing. If it exists with **different** content, the
job MUST fail loudly (`RECEIPT_CONFLICT`) and MUST NOT overwrite — a differing
receipt for a fixed SHA means tampering or a schema bug.

The receipt reuses the control-plane vocabulary already defined in
`control-plane/README.md`, so receipts and dashboard claims speak one language:

- `outcome`: `PASS`, `FAIL`, `BLOCKED_EXTERNAL`, `IN_PROGRESS`, `NOT_RUN`, `RETIRED`
- `stage`: `SPEC`, `PLAN_CHECK`, `BUILD`, `UNIT_TEST`, `E2E`, `INTEGRATION`,
  `LIVE_SMOKE`, `SECURITY`, `DATA_INTEGRITY`, `VERIFIER`
- `failure_type` (required iff outcome is `FAIL` or `BLOCKED_EXTERNAL`):
  `REQUIREMENTS`, `COMPILE`, `ASSERTION`, `AUTH`, `SYNC`, `CLEANUP`, `RLS`,
  `NAVIGATION`, `ENVIRONMENT`, `HARNESS`
- `signal` is derived, never hand-written:
  `<STAGE>_<OUTCOME>`, or `<STAGE>_<FAILURE_TYPE>_<OUTCOME>` when
  `failure_type` is present.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "evidence-receipt",
  "type": "object",
  "additionalProperties": false,
  "required": ["schema_version","repository","commit_sha","created_at",
               "producer","required_checks","stage","outcome","signal"],
  "properties": {
    "schema_version": {"const": "1.0.0"},
    "repository":     {"type":"string","pattern":"^[^/]+/[^/]+$"},
    "commit_sha":     {"type":"string","pattern":"^[0-9a-f]{40}$"},
    "parent_sha":     {"type":["string","null"],"pattern":"^[0-9a-f]{40}$"},
    "merged_pr":      {"type":["integer","null"]},
    "created_at":     {"type":"string","format":"date-time"},
    "producer": {
      "type":"object","additionalProperties":false,
      "required":["workflow","run_id","run_attempt","run_url","gate_ref"],
      "properties":{
        "workflow":{"type":"string"},
        "run_id":{"type":"integer"},
        "run_attempt":{"type":"integer"},
        "run_url":{"type":"string","format":"uri"},
        "gate_ref":{"type":"string","description":"gate-defs tag or SHA in force"}
      }
    },
    "required_checks": {
      "type":"array","minItems":2,
      "items":{
        "type":"object","additionalProperties":false,
        "required":["name","conclusion","check_run_id","completed_at"],
        "properties":{
          "name":{"enum":["organization-merge-gate","project-required-ci"]},
          "conclusion":{"enum":["success","failure","cancelled","skipped",
                                "timed_out","action_required","neutral","stale"]},
          "check_run_id":{"type":"integer"},
          "completed_at":{"type":"string","format":"date-time"}
        }
      }
    },
    "stage":        {"enum":["SPEC","PLAN_CHECK","BUILD","UNIT_TEST","E2E",
                             "INTEGRATION","LIVE_SMOKE","SECURITY",
                             "DATA_INTEGRITY","VERIFIER"]},
    "outcome":      {"enum":["PASS","FAIL","BLOCKED_EXTERNAL","IN_PROGRESS",
                             "NOT_RUN","RETIRED"]},
    "failure_type": {"enum":["REQUIREMENTS","COMPILE","ASSERTION","AUTH","SYNC",
                             "CLEANUP","RLS","NAVIGATION","ENVIRONMENT","HARNESS"]},
    "signal":       {"type":"string","pattern":"^[A-Z_]+$"}
  },
  "allOf": [
    {"if":   {"properties":{"outcome":{"enum":["FAIL","BLOCKED_EXTERNAL"]}}},
     "then": {"required":["failure_type"]},
     "else": {"not":{"required":["failure_type"]}}}
  ]
}
```

Example (`receipts/2026/08/<sha>.json`):

```json
{
  "schema_version": "1.0.0",
  "repository": "NEO-Venturez/taxahead",
  "commit_sha": "0000000000000000000000000000000000000000",
  "parent_sha": "1111111111111111111111111111111111111111",
  "merged_pr": 412,
  "created_at": "2026-08-09T19:04:11Z",
  "producer": {
    "workflow": "record-evidence",
    "run_id": 987654321,
    "run_attempt": 1,
    "run_url": "https://github.com/NEO-Venturez/taxahead/actions/runs/987654321",
    "gate_ref": "v1"
  },
  "required_checks": [
    {"name":"organization-merge-gate","conclusion":"success",
     "check_run_id":111,"completed_at":"2026-08-09T19:01:02Z"},
    {"name":"project-required-ci","conclusion":"success",
     "check_run_id":112,"completed_at":"2026-08-09T19:03:40Z"}
  ],
  "stage": "BUILD",
  "outcome": "PASS",
  "signal": "BUILD_PASS"
}
```

Receipt writes MUST serialize per repo:

```yaml
concurrency:
  group: record-evidence-${{ github.repository }}
  cancel-in-progress: false   # never cancel a receipt write
```

---

## 6. Recovery issue spec

Every post-`main` workflow ends with a recovery job using `if: always()`.

Idempotency key — MUST appear verbatim as the last line of the issue body:

```
recovery-key: <owner>/<repo>/<workflow>/<commit_sha>
```

Search by that key before creating; if an open issue matches, comment on it
instead of opening a second one.

- Title: `[ci-recovery] <workflow> failed on <short_sha>`
- Labels: `release-blocker`, `ci-recovery`
- Assignee: the repo's designated owner (MUST be set; unassigned = unowned)
- Body MUST contain: repository, full commit SHA, workflow name, run URL,
  failed job name, failure category (§7), UTC timestamp, and the recovery key.
- The project status becomes `BLOCKED`. It MUST NOT be reported `PASS`.
- Closure requires a **new successful run** plus the SHA that fixed, reverted,
  or superseded the failure, recorded in a closing comment. A later unrelated
  green run does not close it.

A metadata-only watchdog runs on a schedule, lists failed default-branch runs,
and opens a recovery issue for any lacking one. It MUST NOT download or
execute workflow artifacts.

---

## 7. Failure classification

Exactly one automatic retry is permitted, and only for `ENVIRONMENT`:

| Category | Examples | Action |
|---|---|---|
| `ENVIRONMENT` (transient) | runner lost, DNS/TLS failure to a registry, HTTP 429/503, network timeout on a fetch step | one automatic re-run of the same SHA |
| `COMPILE` | `tsc` errors | repair PR |
| `ASSERTION` | failing unit/E2E assertions | repair PR |
| `REQUIREMENTS` | mock-backed path where real path required | repair PR |
| `HARNESS` | test runner cannot start, lint debt | repair PR |
| `AUTH`, `RLS`, `SYNC`, `NAVIGATION`, `CLEANUP` | product defects | repair PR |

Ambiguous cases are classified as **non-transient**. Retrying a real failure
manufactures a false green.

---

## 8. Ruleset payload and read-back

`POST /repos/{owner}/{repo}/rulesets` (org-level equivalent if the plan tier
supports it — see `MERGE_GATE_PLAN.md` §4 Track A vs Track B):

```json
{
  "name": "product-main-merge-gate",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["~DEFAULT_BRANCH"], "exclude": [] } },
  "bypass_actors": [],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": true,
        "require_last_push_approval": false,
        "required_review_thread_resolution": true
      }
    },
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          { "context": "organization-merge-gate", "integration_id": 15368 },
          { "context": "project-required-ci",     "integration_id": 15368 }
        ]
      }
    }
  ]
}
```

`deletion` blocks branch deletion; `non_fast_forward` blocks force pushes;
`strict_required_status_checks_policy: true` forces the branch to be current
with `main`, which is what invalidates a stale green result.

`integration_id` pins the check producer to the GitHub Actions app so a PAT
cannot post a fake green context. **Confirm the numeric ID for this
installation before use** — do not trust the value above blindly:

```sh
gh api "repos/$REPO/commits/$SHA/check-runs" \
  --jq '.check_runs[] | {name, app_id: .app.id, app: .app.slug}'
```

Deploy first with `"enforcement": "evaluate"`, run the §9 matrix, then flip to
`"active"`. Read back and assert:

```sh
gh api "repos/$REPO/rules/branches/main" \
  --jq '[.[].type] | sort'                      # includes the four rule types
gh api "repos/$REPO/rulesets" --jq '.[] | {id, name, enforcement}'
gh api "repos/$REPO/rulesets/$ID" --jq '.bypass_actors'   # MUST be []
```

A ruleset that has not been read back through the API is not proven. Screenshots
and UI impressions are not evidence.

---

## 9. Acceptance matrix

Run in the sandbox repo first, then in Evaluate mode per product repo. Each row
records the PR/run URL that demonstrated it.

| # | Scenario | Required outcome |
|---|---|---|
| 1 | Green PR | merges |
| 2 | Failing required test | merge blocked |
| 3 | Cancelled required test | merge blocked |
| 4 | Skipped required test | merge blocked |
| 5 | Timed-out required test | merge blocked |
| 6 | Required check never reports | merge blocked |
| 7 | New commit after green | prior result invalidated |
| 8 | Direct push to `main` | rejected |
| 9 | Force push to `main` | rejected |
| 10 | Delete `main` | rejected |
| 11 | Ordinary PR edits `.github/workflows/**` | gate fails closed |
| 12 | PR renames a job in `needs` without updating `EXPECTED` | `project-required-ci` fails |
| 13 | PR rewrites its own adapter to fake `project-required-ci` | caught by code-owner review or §2 protected-paths |
| 14 | Post-main failure | recovery issue opened, release blocked |
| 15 | Fix pushed | same gate re-runs; issue closes only with proving SHA |

Rows 12 and 13 are the ones most often skipped; they are the ones that catch
silent gate erosion.

---

## 10. "Nothing can be blocked" — how this resolves

An instruction that no work may end `BLOCKED` is compatible with this spec, but
only under one reading. The two meanings must not be conflated:

- **Gate-blocked** — a required check is red. This is always fixable and MUST
  be fixed. No exceptions, no bypass, no merging around it.
- **Externally blocked** (`BLOCKED_EXTERNAL` / `ENVIRONMENT`) — provider
  credentials, live fixtures, or a database do not exist in the environment.
  `control-plane/projects/*.json` currently records several of these for both
  products (`connector-live`, `core-live`, `pms-integrity`, `pms-extension`).

No amount of code repair turns the second kind green, because the missing
input is external. The resolution is **not** to force them green and **not** to
leave the project sitting in `BLOCKED`:

> Externally blocked items are not required checks yet. They stay out of
> `EXPECTED`, are tracked in the ratchet table with a named owner and the
> specific missing input, and are ratcheted in the day that input exists.

So the gate's answer is always binary and always actionable, and no item is
parked in limbo. What is forbidden is the third option: marking an unproven or
unrunnable item `PASS` to clear a board. A green that was not earned is worse
than a red, because it removes the signal that would have prompted the fix.
If a required input is genuinely unavailable, that is a procurement/config task
with an owner and a date — report it as such, not as PASS.
