# PadSplit Cockpit — recurring bug-class root-cause diagnosis

**Source:** a project-state audit sub-agent dispatched 2026-07-09 as part of the TaxAhead/PadSplit Cockpit structure review (see `two-tier-team-vs-gate-2026-07-10.md` and `deep-research-build-vs-debug-team-2026-07-10.md` for the downstream research this fed into). Saved 2026-07-10 after a plan-check round for `repo_health_gate.py` found this diagnosis had never been persisted to a citable file — it existed only in conversation.

## Root-cause diagnosis (from reading real diffs, not commit messages)

Not a series of unrelated one-off bugs. Three distinct, recurring mechanisms:

### (a) Shared-DB fragility

Shared, non-isolated local dev Postgres + hardcoded fixture data + concurrent writers. The fixture-flakiness fix, the orphaned-row bug, the RLS cross-FK gap, the AC17 shared-state flake (`fix_plan.md`, 2026-07-02), and a live `deadlock detected` error observed during the audit's own test run are all the same underlying mechanism: tests and sync code share one mutable Postgres instance (`dev-org-1`, port 5433) with hardcoded, non-randomized keys, no per-test isolation, and multi-step non-transactional writes.

Cited instances: `KNOWN_ISSUES.md` line 229 (`[FIXED local patch 2026-07-09]` hardcoded fixture-email entry); `fix_plan.md`'s `H-FULLSUITE-INSTABILITY-1` (2026-07-09 addendum, line ~3173).

**Correction (2026-07-10, made after a round-3 plan-check + Oga's own `git show` follow-up):** an earlier version of this entry also cited `KNOWN_ISSUES.md` line 163. That citation is real and accurately quoted, but on independent re-read it describes an RLS cross-table FK-ownership schema-completeness gap — a different mechanism (missing an `EXISTS` check in a migration's RLS policy) than shared-DB/fixture/concurrency fragility. Removed from this entry; it does not belong here.

### (b) Allowlist drift

Hand-maintained enumeration/allowlist constants silently drift as the codebase grows. `EXPECTED_SITES`, `CALL_SITES`, and `REQUIRED_IMPORTER_PAGES` have each been "re-anchored to real call sites" repeatedly across many separate commits, verified via `git show` on 2026-07-10 (not just commit-message recall):

`8b470dc`, `9d45a0f`, `fef4458`, `f56f288`, `28906e2` — each confirmed to touch `web/tests/rls-source-sweep.test.ts`, re-anchoring `EXPECTED_SITES` rows to real call sites — plus the signout-allowlist `CALL_SITES` gap fixed in `b8fb2d2` (`web/tests/auth-setup.test.ts`/`web/tests/signout-ui.test.ts`).

This is 6 separate, real, `git show`-verified commits re-touching the identical class of constant across the repo's history — the class-wide evidence for this entry, not just its most recent instance.

**Correction (2026-07-10):** an earlier version of this entry also cited `19c0881` and the vitest `spawnerTestFiles` list. Both removed after independent verification: `19c0881` is a real commit but touches `dashboard-actions.test.ts`/`dashboard-adversarial.test.ts` for an unrelated Task-fixture-restoration bug — no mention of `EXPECTED_SITES`/`CALL_SITES`/`REQUIRED_IMPORTER_PAGES` anywhere in its diff. `spawnerTestFiles` is stale as a "currently drifting" example — `web/tests/register-route-gate-source.test.ts` now has an explicit regression test asserting the config `must come from a real disk walk (fs.readdirSync)... not a hand-maintained array literal`, i.e. that specific constant was already fixed and is no longer an instance of this class.

### (c) Unvalidated API ingress

No runtime schema validation at the sync API ingress boundary. `route.ts` parses external POST bodies with a bare `as SyncPayload` cast — no zod/safeParse anywhere. Root of a family of separately-discovered bugs:
- The SSRF-via-unvalidated-`icalExportUrl` finding (`KNOWN_ISSUES.md` line 44, `[FIXED 27d7cef]`).
- AC18's boolean-bypasses-null-check finding (`KNOWN_ISSUES.md` line 193, `[FIXED 27d7cef]`).
- The still-open, already-written `web/tests/sync-malformed-payload-matrix.test.ts` (confirmed to exist and exercise this exact gap, per the round-2 plan-check's own direct grep of that file, lines 149–667) — proves but does not fix that a confused nested-array field crashes both sync routes with `.reduce is not a function`.

## Compounding factor (not a 4th class, context for (a))

Concurrent worktrees/sessions against the same repo and same shared local DB is why (a)'s symptoms get misdiagnosed as "flaky" before someone traces them to the real mechanism.
