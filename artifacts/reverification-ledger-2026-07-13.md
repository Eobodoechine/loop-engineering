# Parallel Reverification Ledger

Baseline date: 2026-07-13

## TaxAhead baseline

- Lovable source: `Eobodoechine/remix-of-taxahead.ai`
- Lovable commit: `bab4b1b22634386fbc88079ea2d1562401ca277b`
- Canonical reconciled commit: `a78f13598cf7a425de4bd20e92d6b97f140eedb3`
- Integration checkout: `<HOME>/Claude/Projects/taxahead-integration`
- Original dirty checkout preserved: `<HOME>/Claude/Projects/taxahead`

## TaxAhead lanes

| Lane | Worktree | Result | Signal | Evidence / note |
|---|---|---|---|---|
| Core | `<HOME>/Claude/Projects/taxahead-reverification/core` | Partial | `E2E_REQUIREMENTS_FAIL`, `E2E_NAVIGATION_FAIL`, `BUILD_COMPILE_FAIL`, `LIVE_SMOKE_ENVIRONMENT_BLOCKED_EXTERNAL` | Auth/bootstrap, upload/extraction, and scoring passed focused tests. Tax package remains mock-backed; Q&A wrapper has no application call sites; TypeScript has 18 errors; credentialed smoke setup is absent. |
| UI | `<HOME>/Claude/Projects/taxahead-reverification/ui` | Partial | `BROWSER_REQUIREMENTS_PASS`, `BROWSER_NAVIGATION_FAIL`, `BROWSER_ASSERTION_FAIL`, `TYPECHECK_COMPILE_FAIL`, `LIVE_AUTH_BLOCKED_EXTERNAL`, `LINT_COMPILE_FAIL` | Public entry, auth entry, assigned app routes, loading/error states, and admin navigation passed. Admin child refresh, hydration markers, TypeScript, lint/test harness, and live auth/sync remain open. |
| Connectors | `<HOME>/Claude/Projects/taxahead-reverification/connectors` | Partial | `UNIT_TEST_PASS`, `INTEGRATION_REQUIREMENTS_FAIL`, `LIVE_SMOKE_ENVIRONMENT_BLOCKED_EXTERNAL`, `VERIFIER_HARNESS_FAIL` | Local callback/sync/cleanup/RLS tests pass. No production adapter is registered; live credentials, fixtures, deployed functions, and smoke harness are absent. Deno suite passed 110 tests; lint remains non-green. |

The connector reports that looked contradictory are stage-separated: local contract tests are PASS, while production readiness is FAIL or BLOCKED_EXTERNAL. They are retained as separate claims rather than collapsed into one status.

## PMS background lane

- Worktree: `<HOME>/Claude/Projects/padsplit-reverification/pms`
- Branch: `codex/pms-reverify`
- Baseline: `4a396220b598d640e4bea5fb703c24efe83c23c5`
- Live workflow, schema/RLS, and extension proof: `BLOCKED_EXTERNAL` because browser/server/database/fixtures were unavailable.
- Historical readiness: `VERIFIER_REQUIREMENTS_FAIL`; retained evidence records 6 failures, 1,052 passes, and 11 skips.
- Current build/test attempt: build failed at missing generated Prisma client; full test command remained non-green without database configuration.

## Readiness boundary

TaxAhead is not Ready. The canonical frontend baseline is built and focused wiring is verified, but mandatory product claims still fail or are externally blocked: real tax package output, grounded Q&A wiring, TypeScript, production connector adapters, and credentialed live smoke.
