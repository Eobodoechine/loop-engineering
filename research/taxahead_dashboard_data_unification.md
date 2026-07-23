# TaxAhead Dashboard — Data-Source Unification Research
**Date:** 2026-07-20
**Scope:** `src/routes/app.dashboard.tsx` fixture → real-data replacement (Phase 1)

---

## 1. Fixture Usages in the Dashboard Route

### 1A. `outlookByScenario` (lines 53–66)
- **What:** A `Record<Scenario, TaxOutlook>` with 11 hardcoded entries.
- **Shape:** `{ direction, amount, headline, detail, deductions?: { amount, count } }`
- **Current values:** Every entry has `direction: "early"`, `amount: "—"`, `headline: "Federal estimate unavailable"`. Deductions vary per scenario (e.g., `active` = $11,800 / 14 items).
- **Consumed at:** Line 88: `const outlook = outlookByScenario[scenario]` → passed to `<TaxOutlookCard>` (line 133).
- **Renders in:** `TaxOutlookCard` (lines 497–562): shows headline, amount, deductions amount/count, readiness score, and a "CONNECT MORE SOURCES" suggestion strip.
- **Real-data equivalent:** `TaxPackageTaxEstimate` exists in `TaxPackageResult.tax_estimate` (edge-functions.ts:107–122, 143). Has `direction`, `refund_or_amount_due`, `standard_deduction`, `gross_income`, `taxable_income`, `status`, `assumptions`. **No adapter maps it to `TaxOutlook` yet.**
- **Gap:** Need a `toTaxOutlook()` adapter + a `useTaxEstimate()` hook (or fold into existing `useDashboardDocuments`/new `useTaxPackage()` hook).

### 1B. `resolveFilingProfile()` (imported line 19, used line 87)
- **What:** Returns a `FilingProfile` from `filingProfileByScenario[scenario]` (filing-profile.ts:14–102) — a scenario-keyed fixture with status, household state, dependents, complexity, etc.
- **Consumed at:** Line 87: `const profile = resolveFilingProfile(scenario, sessionProfile.filing, sessionProfile.spouseFirstName)`.
- **Passed to:** `buildAttentionItems(scenario, feed, readiness, profile)` (line 93).
- **Effect:** Only `profile.household` and `profile.waitingFor` are checked (lines 339–360) to generate "Waiting for X's information" or "Invitation sent to X" attention items.
- **Real-data equivalent:** `TaxPackageResult.filing_unit.filing_status` exists. `bootstrap-filing-unit` returns `filing_status`. No household/member-invitation backend concept yet.
- **Gap:** Need a real filing-status hook; household state has no backend equivalent (must stay session-derived or degrade).

### 1C. `useScenario()` (imported line 15, used line 72)
- **What:** Reads `ta_scenario` from localStorage. Demo store.
- **Consumed in 5 places:**
  1. `outlookByScenario[scenario]` (line 88) — fixture lookup
  2. `resolveFilingProfile(scenario, ...)` (line 87) — fixture lookup
  3. `buildAttentionItems(scenario, ...)` (line 93) — guards `scenario !== "new"` at line 376
  4. `buildBriefing(scenario, ...)` (line 98) — adds "Welcome back" for `"returning"` at line 273
  5. `isEmpty` check: `scenario === "new" || activeConnections.length === 0` (line 102)
- **Real-data equivalent:** None — scenarios are a demo construct.
- **Gap:** Each usage needs an individual real-data replacement (see gap list below).

### 1D. Dead code (defined but never rendered)
- `BriefingCard` component (lines 278–310) — **never instantiated in JSX**. `briefing` is computed (line 98) but never passed to any rendered component.
- `ReadinessProgress` component (lines 642–670) — **never instantiated in JSX**.
- Both can be removed or left as-is; they don't affect the data-source unification.

---

## 2. Existing Real-Data Infrastructure

### Hooks (`src/lib/real-data-hooks.ts`)
| Hook | Edge Function | Adapter | Returns |
|------|---------------|---------|---------|
| `useMember()` | none (session-derived) | inline | `{ id, legalFirstName, email, ... }` |
| `useFeed(filingUnitId)` | `getTaxPackage` | `adaptFeedItems` | `FeedEntry[]` |
| `useReadiness(filingUnitId)` | `computeScores` | `adaptReadiness` | `FilingReadiness` |
| `useDashboardConnections(filingUnitId)` | `listSources` | `adaptConnections` | `Connection[]` |
| `useDashboardDocuments(filingUnitId)` | `getTaxPackage` | none (raw passthrough) | `TaxPackageDocument[]` |

### Adapters (`src/lib/real-data-adapters.ts`)
| Function | Input | Output |
|----------|-------|--------|
| `adaptReadiness(scores)` | `ComputeScoresResult` | `FilingReadiness` |
| `adaptFeedItems(feed)` | `TaxPackageResult.feed` | `FeedEntry[]` (deduped, sorted) |
| `adaptConnections(sources, providers)` | `ConnectedSource[] + ConnectorProvider[]` | `Connection[]` |
| `computeComplexity(input)` | `{ filingStatus, dependentCount, connectedSourceCount }` | `"High"/"Moderate"/"Low"/"Unknown"` |
| `formatTimestamp(iso)` | ISO string | short display label |

### Tax-Package Adapter (`src/lib/tax-package-adapter.ts`)
| Function | Maps | Used by dashboard? |
|----------|------|--------------------|
| `toFilingReadiness(result)` | scores + missing_items → `FilingReadiness` | No (dashboard uses `adaptReadiness` from real-data-adapters) |
| `toConnections(result)` | sources → `Connection[]` | No (dashboard uses `adaptConnections`) |
| `toTaxDocuments(result)` | documents → `TaxDocument[]` | No (dashboard uses raw `TaxPackageDocument[]`) |
| `toSupportingEvidenceItems(result)` | extracted_inputs + unsupported → evidence items | No |
| `toFeedEntries(result)` | feed → `FeedEntry[]` | No (dashboard uses `adaptFeedItems`) |
| `toTaxPackageSections(result)` | → `[]` (always empty) | No |
| `resolveMemberDisplayName(fullName, email)` | name resolution | No |

### Edge Functions (`src/lib/edge-functions.ts`)
| Function | Purpose |
|----------|---------|
| `bootstrapFilingUnit()` | Creates/resolves filing unit, returns `{ id, tax_year, filing_status, jurisdiction }` |
| `createUpload(args)` | Issues signed upload URL |
| `extractDocument(document_id)` | Classifies + extracts from uploaded doc |
| `computeScores(filing_unit_id)` | Returns readiness + confidence scores |
| `getTaxPackage(filing_unit_id)` | Full package: docs, feed, sources, scores, tax_estimate, deductions |
| `askTaxahead(args)` | Grounded Q&A |
| `listSources()` | Connected sources + provider catalog |
| `startConnection(args)` | Begin OAuth/credential connection |
| `completeOAuthConnection(args)` | Finish OAuth flow |
| `syncSource(args)` | Trigger sync job |
| `disconnectSource(source_id)` | Disconnect a source |

---

## 3. Gap Analysis

### Fixtures WITH real-data equivalents (already wired)
| Fixture | Real Source | Status |
|---------|-------------|--------|
| Feed entries | `useFeed()` → `getTaxPackage` → `adaptFeedItems` | ✅ Live |
| Filing readiness | `useReadiness()` → `computeScores` → `adaptReadiness` | ✅ Live |
| Connections | `useDashboardConnections()` → `listSources` → `adaptConnections` | ✅ Live |
| Documents count | `useDashboardDocuments()` → `getTaxPackage` | ✅ Live |
| Member name | `useMember()` (session-derived) | ✅ Live (stub) |

### Fixtures MISSING real-data equivalents
| Fixture | What's Missing | Effort |
|---------|---------------|--------|
| **Tax outlook / estimate** | `TaxPackageTaxEstimate` exists in backend response but no adapter maps it to `TaxOutlook`. No hook fetches it for the dashboard. | Medium — write `toTaxOutlook()` adapter, add `useTaxEstimate()` hook or extend `getTaxPackage` hook |
| **Deductions summary** | `TaxPackageResult.potential_deductions_total` exists (`{ amount, fact_count, basis }`) but no adapter maps it to `{ amount: string, count: number }`. | Small — add to same `toTaxOutlook()` adapter |
| **Filing profile (household state)** | `filing_unit.filing_status` available, but household concept (Active/Incomplete/Invitation Sent, waitingFor) has no backend schema. | Large — needs schema + API, or accept session-derived fallback |
| **Scenario-based empty state** | `scenario === "new"` is used to gate the empty state. Can be replaced with `activeConnections.length === 0 && documentsFound === 0`. | Small |
| **Scenario-based briefing prefix** | "Welcome back" for `"returning"` — cosmetic, can be dropped or derived from `member.joinedAt`. | Trivial |
| **Scenario guard in buildAttentionItems** | `scenario !== "new"` guard (line 376) — replace with `activeConnections.length > 0`. | Trivial |

---

## 4. Scenario Switcher

- **Component:** `src/components/app-shell/scenario-switcher.tsx` — a pill/popover with 11 scenarios.
- **Self-description:** "Demo only — won't ship in production" (line 117).
- **Module doc:** "Real product: this module disappears. Real data comes from the backend" (demo-scenario.ts:10).
- **Dashboard usage:** The dashboard does NOT render `<ScenarioSwitcher>` in its JSX, but it imports and calls `useScenario()` (line 72).
- **Feed page usage:** `<ScenarioSwitcher variant="inline" />` rendered at `app.feed.tsx:686`.
- **Recommendation:** Gate behind `import.meta.env.DEV` or a `VITE_DEMO_MODE` flag. Keep the `useScenario()` hook and store for dev/demo use, but the dashboard should not branch on `scenario` in production code paths.

---

## 5. Recommended Replacement Order

| Priority | Change | Risk | Dependency |
|----------|--------|------|------------|
| **P1** | Write `toTaxOutlook()` adapter: maps `TaxPackageTaxEstimate` + `potential_deductions_total` → `TaxOutlook` | Low | None |
| **P2** | Add `useTaxEstimate(filingUnitId)` hook (or fold into a single `useTaxPackage` hook) | Low | P1 |
| **P3** | Replace `outlookByScenario[scenario]` with `useTaxEstimate()` result in dashboard | Low | P2 |
| **P4** | Replace `scenario === "new"` in `isEmpty` with `activeConnections.length === 0 && documentsFound === 0` | Low | None |
| **P5** | Replace `resolveFilingProfile()` with real `filing_status` from `bootstrapFilingUnit` + session fallback for household | Medium | Schema decision |
| **P6** | Drop `scenario` param from `buildAttentionItems` and `buildBriefing` | Low | P4, P5 |
| **P7** | Remove dead `BriefingCard` and `ReadinessProgress` components | None | None |
| **P8** | Gate `ScenarioSwitcher` behind dev flag across all routes | Low | None |

### Contract test constraint
`app.tax-estimate-ui.contract.test.ts` already enforces:
- Dashboard must not contain hardcoded `$`-prefixed refund/amount-due claims paired with "Estimated refund" or "Estimated tax due" headlines.
- Any estimate language must be backed by `TaxPackageResult.tax_estimate`.
- Current code passes because all outlook entries say `"—"`. The replacement must continue to pass this test.
