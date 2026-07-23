# TaxAhead And Mission Control Continuation Brief

Read this brief before editing. Verify every claim against the live files and
checkouts; prior summaries are not proof.

## Goal

Make TaxAhead the only human-focus project. Build the internal Mission Control
dashboard in the simpler approved project-list and project-detail format while
TaxAhead is repaired. PMS reverification and connector audits remain read-only
parallel evidence lanes and never take the human focus away from TaxAhead.

## Non-negotiable boundaries

- Preserve the dirty checkout at <HOME>/Claude/Projects/taxahead.
  Do not reset, clean, rebase, or write there.
- The canonical TaxAhead integration checkout is
  <HOME>/Claude/Projects/taxahead-integration on branch
  codex/taxahead-canonical-reconciled at commit
  a78f13598cf7a425de4bd20e92d6b97f140eedb3.
- Do not push the canonical branch to Lovable or GitHub until the requested
  verification gates pass and the user approves publication.
- Keep these worktrees read-only:
  <HOME>/Claude/Projects/taxahead-reverification/connectors
  and <HOME>/Claude/Projects/padsplit-reverification/pms.
- Never expose raw secrets. Missing provider credentials, fixtures, deployed
  functions, browser setup, or databases are BLOCKED_EXTERNAL, not product
  failures.

## What actually exists now

1. The canonical TaxAhead baseline includes selected Lovable UI and selected
   local behavior: auth, filing bootstrap, upload/extraction/scoring,
   tax-package adapters, connector code, migrations, tracing, and tests.
   It does not contain every dirty-checkout document or research artifact.
2. The dirty-checkout reconciliation register now exists at
   <HOME>/Claude/loop/artifacts/taxahead-reconciliation-register.json.
   Its first capture marked 80 artifacts IMPORTED, 40
   INTENTIONALLY_EXCLUDED, and one PENDING_REVIEW. The pending path is
   src/routes/api/tts.test.ts. Re-run or inspect the register before using
   those counts.
3. The linked TaxAhead project contracts now include lifecycle phase,
   ordered slices, evidence paths, and phase history:
   <HOME>/Claude/loop/control-plane/projects/taxahead.json
   and <HOME>/Claude/loop/control-plane/projects/padsplit-cockpit.json.
4. Mission Control has a validated claim/focus/priority backend in
   <HOME>/Claude/loop/loop-team/harness/mission_control.py.
   It supports append-only audit events and expected-revision conflict
   rejection.
5. The dashboard UI rewrite was interrupted before a replacement patch landed.
   Do not assume the current UI matches the approved reference screenshots.
   Inspect <HOME>/Claude/loop/loop-team/harness/mission_control_ui.html
   and then implement the approved primary format.

## Required dashboard outcome

Build this in the loop control plane, not inside the TaxAhead customer app.

Primary Projects view:

- Project cards only for real project contracts. Do not invent projects,
  progress, estimates, or activity.
- Each card shows name, description, current phase, phase progress,
  outstanding count, estimate, last activity, and a specific failure signal.
- Lifecycle is Idea, Spec and plan-check, Building, Verifying, Shipped.

Project detail view:

- Back to all projects navigation.
- Lifecycle tracker, estimate, last activity, outstanding blockers, next
  action, ordered slices, claims, evidence, and phase history.
- Every slice must expose its spec path, acceptance criteria, frontend/mock
  contract, backend status, verification evidence, dependencies, and next
  action.
- Failure presentation must show signal, plain-language explanation, affected
  slice, evidence path, and next action.

Dashboard v1 is read-only for product data. The only allowed mutations are
focus and priority. They require user confirmation, a reason, a pivot trigger
for focus, an expected revision, and an append-only audit event. Concurrent
stale writes must return HTTP 409.

## Required TaxAhead sequence

Keep one active slice: compile and contract repair.

1. Repair the canonical checkout TypeScript errors:
   - stale session/demo scenario contract
   - nullable edge-function request body
   - connections search parameters
   - protected route callers that construct connection searches
2. Prove typecheck, build, unit tests, and frontend-wiring tests still pass.
3. Replace the tax-package route demo path with real filing-unit and scoring
   data. Preserve loading, empty, error, and BLOCKED_EXTERNAL states.
4. Wire the grounded askTaxahead wrapper into the real feed/conversation UI
   with loading, answer/evidence, error, and unavailable states.
5. Run the complete evidence ladder. TaxAhead is not Ready while any mandatory
   claim is FAIL or BLOCKED_EXTERNAL.

The current known blockers include mock-backed tax package UI, no application
call site for grounded Q&A, TypeScript failures, non-green lint, no production
connector adapters, and unavailable credentialed live smoke.

## Parallel lanes

Connectors:

- Reverify OAuth start/callback, adapter registration, sync, disconnect,
  cleanup, RLS/Vault, UI wiring, and live-provider proof.
- Keep local fake-adapter tests distinct from production readiness.
- Report claim rows only. Do not modify shared product code.

PMS:

- Reverify historical workflow, sync and extension registration, database/RLS,
  browser extension proof, and readiness statements.
- Report typed evidence or BLOCKED_EXTERNAL. Do not modify shared product code.

## Verification commands

Before editing, capture:

1. git status --short --branch in the dirty checkout, canonical checkout, and
   both verification worktrees.
2. In the loop checkout:
   python3 -m pytest loop-team/harness/test_mission_control.py
   loop-team/harness/test_reconcile_manifest.py -q
3. In the canonical TaxAhead checkout:
   npx tsc --noEmit --pretty false
   bun run build
   bun run test
   bun run test:frontend-wiring

After dashboard implementation, use a browser to prove the Projects list,
detail navigation, filters, tabs, focus confirmation, priority confirmation,
and stale-revision rejection. Compare the primary layout to the user-approved
reference screenshots: it should be the simple projects list and detail
experience, not the operator-heavy metrics-first screen.

## Completion condition

Report exactly what changed, exact test outcomes, and every remaining typed
blocker. Do not call TaxAhead Ready unless every mandatory lifecycle claim is
PASS. Do not call the dashboard build-driving until it renders the real ordered
slices and evidence above from the contract files.
