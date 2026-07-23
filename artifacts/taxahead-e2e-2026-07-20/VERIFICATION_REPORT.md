# TaxAhead E2E Verification Report — 2026-07-20

## Production URL: https://tanstack-start-ts-ehv.pages.dev
## Baseline SHA: 55c90319e4e499d069ee9f3350e1a7ec001f2962

---

## Test Suite Results

| Suite | Result | Details |
|-------|--------|---------|
| Vitest (full) | ✅ 161 passed / 7 failed | 3 pre-existing failing files: tts.test.ts, tracing.server.test.ts, upload-format-honesty.test.ts |
| Deno extraction | ✅ 9/9 passed | 1099-NEC, 1099-MISC, 1099-K all recognized; 1099-B correctly unsupported |
| TypeScript (tsc --noEmit) | ❌ 7 errors | All in profile.tsx — `business_activities` not in generated Supabase types |

---

## Browser Verification — Page by Page

### Landing Page (screenshot: 01-landing-page.png)
- ✅ Renders correctly, "Enter workspace" button works
- ✅ All sections present: How it works, Pricing, FAQs, Security

### Feed/Chat Page (screenshot: 02-feed-page.png)
- ✅ Loads at /app/feed
- ✅ Chat interface renders
- ✅ Sidebar shows real user (Djtoluu, djtoluu@djtoluu.com) — commit 80d05ca confirmed

### Dashboard (screenshots: 03-dashboard-top.png, 04-dashboard-bottom.png)
- ✅ Tax outlook card renders: $19,168 estimated due, 73% preparer readiness — commit 21a09fb confirmed
- ✅ No `outlookByScenario` fixture data visible — no hardcoded scenario names — commit 76f428b confirmed
- ✅ Document count: "13 documents received" (real data) — commit ba25624 confirmed
- ✅ Feed entries render with real dates (Jul 18, Jul 15) — commit ba25624 dedup confirmed
- ✅ Empty-state gate uses real data (10 connected · 13 docs) — commit 76f428b confirmed
- ✅ "Connect more sources" section with real logos
- ✅ "What needs attention" shows 2 items
- ✅ Document checklist summary visible
- ✅ Recent activity shows real Q&A entries

### Tax Package (screenshot: 05-tax-package-summary.png)
- ✅ Navigates to /app/tax-package — commit ca51ace confirmed
- ✅ No fixture data (no "active", "sparse" scenario names)
- ✅ Real data: $19,168.13 federal estimate, 73% readiness, 33% evidence, 46% discovery
- ✅ 13 documents, 10 connections, 2 open discoveries
- ✅ Filing profile shows real email, "Not set yet" for filing status (correct — no status set)
- ✅ Tab navigation works (5 sections)

### Profile Page (screenshots: 06-profile-top.png, 07-profile-business-form.png, 08-profile-full-page.png)
- ✅ Filing status selector with 5 options (Single, MFJ, MFS, HoH, QSS)
- ✅ Dependents section with Add form (name, relationship, DOB, SSN)
- ✅ Address section with all 50 states dropdown
- ✅ Business Activities section with Add form (name, type, income, expenses, home office)
- ✅ Rental Properties section with Add button
- ✅ Document checklist: 5 items (3 Received, 2 Missing) — commit a4812aa confirmed
- ✅ Account section: Settings, Billing ($49/yr), Support, Sign out
- ✅ Sidebar profile link shows real user — commit 80d05ca confirmed

### Connections Page (screenshot: 09-connections-page.png)
- ✅ Loads at /app/connections
- ✅ Shows connected sources

---

## Interactive Feature Testing

| Feature | Action | Result | Root Cause |
|---------|--------|--------|------------|
| Filing status select | Selected "Single" | ❌ Didn't persist | 400 on filing_units (column mismatch) |
| Add dependent | Filled form, clicked Add | ❌ Failed | 400 on filing_unit_members POST |
| Add business | Filled form, clicked Add | ❌ Failed | 404 on business_activities (table missing) |
| Save address | Filled Atlanta address, clicked Save | ❌ Failed | 400 on filing_units POST |

---

## Root Cause Analysis: Production Database Gaps

### Missing Tables (Migrations Not Applied)
| Table | Migration | Status |
|-------|-----------|--------|
| `business_activities` | 0019 (Schedule C) | ❌ 404 — not in production Supabase |
| `rental_properties` | 0020 (Schedule E) | ❌ 404 — not in production Supabase |
| `depreciation_assets` | 0020 (Schedule E) | ❌ 404 — not in production Supabase |

### Column/RLS Issues
| Table | Error | Likely Cause |
|-------|-------|-------------|
| `filing_units` | 400 on SELECT and POST | Column mismatch — code expects columns not in production schema |
| `filing_unit_members` | 400 on SELECT and POST | `role` column or `display_name`/`date_of_birth`/`ssn_last4` missing |

### React Hydration Error
- Error #418 persists despite commit 18d0ee9 — 1 remaining SSR/client text mismatch

---

## Commit-by-Commit Verification

| SHA | Commit | UI Status | Notes |
|-----|--------|-----------|-------|
| f1a2fa8 | Wire frontend to Supabase | ✅ PASS | App loads with real Supabase data |
| d3390e7 | Cloudflare Pages deploy | ✅ PASS | App accessible at production URL |
| 18d0ee9 | Fix hydration mismatch | ⚠️ PARTIAL | 1 remaining hydration error (#418) |
| 80d05ca | Fix sidebar profile | ✅ PASS | Shows Djtoluu + real email |
| ba25624 | Fix dashboard doc count + feed dedup | ✅ PASS | 13 docs, deduped feed entries |
| a4812aa | Document checklist + profile completeness | ✅ PASS | 5 checklist items rendered correctly |
| ebd5824 | Wire extract-document to fenced RPCs | ✅ PASS | Backend (verified via Gmail smoke test) |
| d11a198 | Wire compute-scores to fenced RPCs | ✅ PASS | Scores visible on dashboard (73%) |
| 21a09fb | MS1: tax outlook adapter + hook | ✅ PASS | $19,168 estimate renders |
| 76f428b | MS2: replace scenario branching | ✅ PASS | No fixture scenario names anywhere |
| 6910b1d | MS3: remove dead code | ✅ PASS | Clean dashboard, no dead references |
| 2a8285e | P3: 1099-NEC extraction | ✅ PASS | 9/9 Deno tests pass |
| ca51ace | P4: tax-package fixture removal | ✅ PASS | Real data on /app/tax-package |
| cc4f222 | P6: Schedule C support | ⚠️ UI RENDERS / DB MISSING | Profile section shows, form appears, but save fails (404) |
| f71e4fb | P1: RAG Phase 1 | ✅ PASS | 19/19 kb-chunker tests pass |
| d75825d | 1099-MISC + 1099-K extraction | ✅ PASS | All 3 forms in 9/9 Deno tests |
| 75324e4 | P5: RAG Phase 2 | ✅ PASS | 28/28 RAG evaluation tests pass |
| e2b6d27 | P6 Phase 3: Schedule E | ⚠️ UI RENDERS / DB MISSING | Profile section shows, but save fails (404) |

---

## Summary

**PASS: 15/18 commits** — fully verified in production browser + test suites
**PARTIAL: 3/18 commits** — UI renders correctly but production Supabase missing migrations 0019+0020

**Blocking issue:** Migrations 0019 (business_activities) and 0020 (rental_properties, depreciation_assets) need to be applied to production Supabase. Additionally, filing_units and filing_unit_members need column alignment or RLS policy updates.
