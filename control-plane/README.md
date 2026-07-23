# TaxAhead Dashboard and Parallel Reverification

Run these commands from `<HOME>/Claude/loop`. The dashboard reads
the project contracts and repo snapshots; it mutates only the revisioned focus
and priority state under `.mission-control/`.

## Contracts

Load and validate both canonical contracts:

```sh
python3 -c 'import sys; sys.path.insert(0, "loop-team/harness"); from mission_control import load_projects; paths=["control-plane/projects/taxahead.json", "control-plane/projects/padsplit-cockpit.json"]; projects=load_projects(paths); print("validated:", ", ".join(p["id"] for p in projects))'
```

Export the validated dashboard JSON atomically:

```sh
python3 loop-team/harness/mission_control.py --export /tmp/taxahead-dashboard.json
python3 -m json.tool /tmp/taxahead-dashboard.json >/dev/null
```

Serve the live API on loopback:

```sh
python3 loop-team/harness/mission_control.py --serve 8765
```

The server prints `http://127.0.0.1:8765`. Endpoints are `GET /`,
`GET /health`, `GET /api/dashboard`, `POST /api/focus`, and
`POST /api/priority`.

## Focused verification

```sh
PYTHONDONTWRITEBYTECODE=1 pytest -p no:cacheprovider -q \
  loop-team/harness/test_mission_control.py \
  loop-team/harness/test_reconcile_manifest.py
```

## Lovable/local manifests

Snapshots include Git identity, tracked and untracked files, hashes, status, and
safe exclusions. They do not modify either checkout. Set `LOVABLE_CHECKOUT` to
the clean Lovable `main` checkout used for reconciliation:

```sh
LOVABLE_CHECKOUT=/absolute/path/to/clean/lovable-main
TAXAHEAD_CHECKOUT=<HOME>/Claude/Projects/taxahead
python3 loop-team/harness/reconcile_manifest.py "$TAXAHEAD_CHECKOUT" \
  > /tmp/taxahead-manifest.json
python3 loop-team/harness/reconcile_manifest.py "$LOVABLE_CHECKOUT" \
  --compare-root "$TAXAHEAD_CHECKOUT" \
  > /tmp/lovable-vs-taxahead-manifest-diff.json
```

The comparison reports `identical`, `modified`, `binary`, `only_local`,
`only_remote`, and `excluded`. Reconcile overlapping paths manually according to
the approved precedence, then establish one clean canonical baseline SHA.

## Mutations

Every focus or priority edit is a confirmed compare-and-swap. The request must
contain `confirmed: true`, a non-empty `reason`, and the current integer
`expected_revision`. A successful edit increments the revision and appends one
audit event. A stale revision returns HTTP `409` with `current_revision` and
cannot overwrite newer state. Audit-write failure returns `500` and restores
the prior state.

Confirm focus:

```sh
curl -sS -X POST http://127.0.0.1:8765/api/focus \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"taxahead","expected_revision":0,"reason":"TaxAhead is the human focus","confirmed":true,"pivot_trigger":"confirmed focus decision"}'
```

Focus also requires a non-empty `pivot_trigger`; priority does not.

Priority requires every matrix input: `goal_impact`, `critical_path`,
`risk_reduction`, `cost_of_delay` in `0..5`; `confidence` in `0.5`, `0.8`,
`1.0`; and `effort` in `1`, `2`, `3`, `5`, `8`.

```sh
curl -sS -X POST http://127.0.0.1:8765/api/priority \
  -H 'Content-Type: application/json' \
  -d '{"project_id":"taxahead","expected_revision":1,"reason":"Reduce reverification risk","confirmed":true,"goal_impact":5,"critical_path":5,"risk_reduction":5,"cost_of_delay":5,"confidence":1.0,"effort":1}'
```

## Failure signals

The signal is derived from three finite axes:

- `outcome`: `PASS`, `FAIL`, `BLOCKED_EXTERNAL`, `IN_PROGRESS`, `NOT_RUN`,
  `RETIRED`
- `stage`: `SPEC`, `PLAN_CHECK`, `BUILD`, `UNIT_TEST`, `E2E`, `INTEGRATION`,
  `LIVE_SMOKE`, `SECURITY`, `DATA_INTEGRITY`, `VERIFIER`
- `failure_type`: `REQUIREMENTS`, `COMPILE`, `ASSERTION`, `AUTH`, `SYNC`,
  `CLEANUP`, `RLS`, `NAVIGATION`, `ENVIRONMENT`, `HARNESS`

`FAIL` and `BLOCKED_EXTERNAL` require `failure_type` and produce
`<STAGE>_<FAILURE_TYPE>_<OUTCOME>`, for example
`LIVE_SMOKE_AUTH_BLOCKED_EXTERNAL`. All other outcomes forbid
`failure_type` and produce `<STAGE>_<OUTCOME>`, for example `BUILD_PASS`.
External blockers and audit completion never imply product readiness.

## Post-baseline read-only lanes

After manifest reconciliation and all baseline checks, create every lane from
the same clean canonical SHA. The original checkout and all lanes are read-only
for product code and configuration:

```sh
INTEGRATION=/absolute/path/to/clean/reconciled-taxahead
WORKTREES=/tmp/taxahead-reverification
BASELINE_SHA="$(git -C "$INTEGRATION" rev-parse HEAD)"
mkdir -p "$WORKTREES"
git -C "$INTEGRATION" worktree add --detach "$WORKTREES/taxahead-reverify-core" "$BASELINE_SHA"
git -C "$INTEGRATION" worktree add --detach "$WORKTREES/taxahead-reverify-ui" "$BASELINE_SHA"
git -C "$INTEGRATION" worktree add --detach "$WORKTREES/taxahead-reverify-connectors" "$BASELINE_SHA"
git -C "$INTEGRATION" worktree add --detach "$WORKTREES/pms-reverify" "$BASELINE_SHA"
```

Lane IDs are `codex/taxahead-reverify-core`,
`codex/taxahead-reverify-ui`, `codex/taxahead-reverify-connectors`, and
`codex/pms-reverify`. Each lane receives the exact `BASELINE_SHA`, its finite
claim subset, the failure schema above, and this instruction: inspect and run
proof only; do not edit product files, shared state, or published history.

The common done sentence is:

> DONE: On baseline `<BASELINE_SHA>`, this lane verified every assigned claim with evidence or recorded a typed blocker; no product files were modified.

Each claim ledger row contains:
`claim_id`, `title`, `lane`, `baseline_sha`, `stage`, `outcome`,
`failure_type` (only for `FAIL` or `BLOCKED_EXTERNAL`), `signal`, `explanation`,
`slice`, `evidence_path`, and `next_action`. Record evidence before using the
done sentence; a missing or unrun proof is `NOT_RUN`, not `PASS`.
