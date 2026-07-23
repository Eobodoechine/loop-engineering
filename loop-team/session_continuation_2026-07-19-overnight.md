# Session Continuation — 2026-07-20 (overnight, fence-wiring build)

## /loop-team goal 3: Dashboard/tax-package data-source unification

**Status:** Research complete, fence-wiring prerequisite DONE, implementation pending.

---

## What was accomplished this session

### Fence-Wiring Build (prerequisite to unblock repo-health gate)

| Step | Status | Detail |
|------|--------|--------|
| Research: data-source architecture | ✅ Done | Domain brief at `~/Claude/Projects/taxahead/research/data-source-unification.md` |
| Research: fence audit | ✅ Done | Found 9 dead fenced RPCs (migration 0008) with zero JS callers |
| Spec: wire edge functions to RPCs | ✅ Done | `~/Claude/loop/loop-team/runs/2026-07-19_231651-fence-wiring/specs/spec.md` |
| Plan-check | ✅ PASS | Hash `7c89a610...`, 3 rounds to get credit gate contract right |
| MS1: extract-document → 6 RPCs | ✅ 20/20 | Commit `ebd5824` |
| MS2: compute-scores → 2 RPCs | ✅ 8/8 + 20/20 | Commit `d11a198` |
| TAXAHEAD-FENCE-ENUM-INCOMPLETE-1 | ✅ CLOSED | Hardening ledger updated 2026-07-20 |
| Repo-health gate | ✅ CLEAR | 0 open items, 0 recurring classes |

### Key commits
- `ebd5824` — Wire extract-document to fenced RPCs (MS1): 230 insertions, 177 deletions
- `d11a198` — Wire compute-scores to fenced RPCs (MS2): 255 insertions, 107 deletions

### Process lessons logged
Added to `~/Claude/loop/loop-team/learnings.md` (2026-07-19):
1. Credit gate requires 3-line contract: PLAN_SUPPORT_JSON + REVIEWED_SPEC_SHA256 + LOOP_GATE
2. PLAN_SUPPORT_JSON evidence digest must use Python `splitlines()` + `'\n'.join()` (not `sed | sha256sum`)
3. Never edit spec between plan-check PASS and Coder dispatch (hash mismatch = permanent veto)
4. PLAN_SUPPORT_JSON must cite files that won't be modified by the build

---

## What's next: Data-Source Unification (original goal)

### Current state
- **Profile route** (`app.profile.tsx`): uses real DB ✅ (completed in MS3 prior session)
- **Dashboard route** (`app.dashboard.tsx`): uses scenario fixtures ❌ (3 fixture usages)
- **Tax-package route** (`app.tax-package.tsx`): uses scenario fixtures ❌ (5 fixture usages)

### Research findings (from domain brief)
The dashboard uses fixtures for:
1. `outlookByScenario` — hardcoded tax outlook (refund/owe amounts, deduction counts)
2. `resolveFilingProfile(scenario, ...)` — hardcoded filing profile
3. Already using real data: readiness score, document count, feed items, connections

The tax-package uses fixtures for:
1. `PackageFixture` objects with hardcoded income/deductions/credits/investments/businesses
2. `byScenario` map selecting fixtures per scenario
3. Already using real data: executive summary, supporting evidence, documents, connections

### Existing real-data infrastructure (already built)
- **Edge functions** (`src/lib/edge-functions.ts`): 11 typed wrappers including `getTaxPackage()`, `computeScores()`, `listSources()`
- **React Query hooks** (`src/lib/real-data-hooks.ts`): `useMember()`, `useFeed()`, `useReadiness()`, `useDashboardConnections()`, `useDashboardDocuments()`
- **Adapters** (`src/lib/real-data-adapters.ts` + `src/lib/tax-package-adapter.ts`): map backend → UI types

### Recommended phases
- **Phase 1 (Dashboard, LOW RISK):** Replace 3 fixture usages with real data adapters
- **Phase 2 (Tax Package, MEDIUM RISK):** Add 4 adapters for facts/insights/missing_items
- **Phase 3 (Cleanup, LOW RISK):** Remove unused fixtures, gate scenario switcher behind dev flag

### Key files to read
- `~/Claude/Projects/taxahead/research/data-source-unification.md` — full domain brief
- `~/Claude/Projects/taxahead/src/routes/app.dashboard.tsx` — dashboard route
- `~/Claude/Projects/taxahead/src/routes/app.tax-package.tsx` — tax-package route
- `~/Claude/Projects/taxahead/src/lib/real-data-hooks.ts` — existing real-data hooks
- `~/Claude/Projects/taxahead/src/lib/tax-package-adapter.ts` — existing adapter pattern

---

## Deployment (ready when you are)
```bash
cd ~/Claude/Projects/taxahead && npm run build && npx wrangler pages deploy dist --project-name tanstack-start-ts
```

## Other next-session priorities (from user's list)
1. RAG knowledge corpus (IRS pubs, pgvector)
2. 1099-NEC extraction
3. ~~Dashboard/tax-package data-source unification~~ ← this session's goal (research done, implementation pending)
