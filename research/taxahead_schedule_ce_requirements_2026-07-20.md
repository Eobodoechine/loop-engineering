# TaxAhead Schedule C & Schedule E Support Requirements

**Date:** 2026-07-20
**Target repo:** `~/Claude/Projects/taxahead`

---

## 1. Current State Assessment

### 1.1 Supported Document Types (Extraction Pipeline)

**`extraction.ts` (lines 5-18):**
```
DOC_TYPES = [w2_2025, 1099_int_2025, 1099_div_2025, 1099_nec_2025, unknown_tax_document]
SUNDAY_MVP_SUPPORTED_DOC_TYPES = [w2_2025, 1099_int_2025, 1099_div_2025]
```

**Key finding:** `1099_nec_2025` exists in `DOC_TYPES` but is **NOT** in `SUNDAY_MVP_SUPPORTED_DOC_TYPES`. The normalization function (`normalizeSundayMvpExtraction`, line 170) routes any doc type not in the MVP set to `unknown_tax_document`. The existing test (`extraction.sunday-mvp.test.ts:97`) confirms 1099-NEC is rejected. The system prompt (line 131) states: "Only these classes are supported: w2_2025, 1099_int_2025, 1099_div_2025."

**What this means for Schedule C/E:**
- **1099-NEC** (Schedule C income): NOT supported in extraction pipeline — routes to unknown
- **1099-MISC** (Schedule E rents/royalties): NOT in DOC_TYPES at all
- **1099-K** (Schedule C/E payment card income): NOT in DOC_TYPES
- **1098** (mortgage interest for Schedule E): NOT in DOC_TYPES

### 1.2 Tax Estimate Engine

**`tax-estimate.ts`:**
- Computes federal income tax using ordinary income brackets + standard deduction
- `INCOME_KEYS` (lines 153-166): wages, interest, dividends only
- `PAYMENT_KEYS` (lines 168-177): federal withholding, estimated payments only
- **Explicitly excluded** (line 44): "self-employment tax, capital gains rates, NIIT, penalties"
- **No Schedule C income keys** (no `box_1_nonemployee_compensation`, no `self_employment_income`)
- **No Schedule E income keys** (no `rental_income`, no `rents`)
- No SECA (self-employment tax) computation
- No QBI (Qualified Business Income) deduction
- No depreciation logic

### 1.3 Schema (Migrations)

**`0001_init.sql` — Core tables:**

| Table | Schedule C/E Ready? | Notes |
|-------|---------------------|-------|
| `filing_units` | Partial | Has `filing_status`, `jurisdiction`, `tax_year`. No business/rental attributes |
| `filing_unit_members` | Yes | Generic member model, can represent business owners |
| `sources` | Yes | Provider-agnostic, any connector type |
| `documents` | Yes | `doc_type` is free text (no enum), supports any form type |
| `evidence` | Yes | JSONB `extracted` field, stores any raw extraction |
| `facts` | Yes | Generic `category`/`key`/`value` (JSONB) model — supports any fact |
| `expected_items` | Partial | Has `profile` field (employee/freelancer/homeowner/investor). No `landlord` profile |
| `detected_profiles` | Partial | Same 4 profiles. No `landlord`/`rental` profile |
| `scores` | Yes | Generic scoring model |
| `insights` | Yes | Generic insight model |
| `feed_messages` | Yes | Generic feed model |

**`0017_profile_completeness.sql`:** Added `primary_state`, `primary_address` (JSONB) to `filing_units`, plus `relationship`, `date_of_birth`, `ssn_last4` to `filing_unit_members`.

**No tables exist for:**
- Business activities / sole proprietorships (Schedule C entities)
- Rental properties (Schedule E entities)
- Business expense categories
- Depreciation schedules
- Asset acquisition/disposition records

**Schema assessment:** The `facts` table is generic enough to store any Schedule C/E data without new tables, but there's no structured model for business activities or rental properties as first-class entities. This matters because a single filer can have multiple businesses and multiple rental properties, each with their own income/expense streams.

### 1.4 Profile Model

**`profiles.ts` — Expected items:**

```typescript
employee: [employer, wages, federal_withholding]
freelancer: [self_employment_income, business_expenses, estimated_tax_payments]
homeowner: [mortgage_interest, property_tax]
investor: [brokerage_activity, dividend_income, capital_gains]
```

**Profile triggers** (profiles.ts:34-44):
```
income.employer → employee
income.wages → employee
income.self_employment_income → freelancer
business.business_expenses → freelancer
property.mortgage_interest → homeowner
property.property_tax → homeowner
investment.* → investor
```

**Missing:**
- No `landlord` profile (for Schedule E rental income)
- No `rental_income` expected item or trigger
- No `rental_property` expected item or trigger
- No `depreciation` expected item or trigger
- Freelancer profile exists but has only 3 items — missing: business type, gross receipts, COGS, home office, vehicle use, other Schedule C line items

### 1.5 Edge Function (`get-tax-package/index.ts`)

**`SUNDAY_SUPPORTED_DOC_TYPES`** (line 71):
```typescript
new Set(["w2_2025", "1099_int_2025", "1099_div_2025"])
```

**What it does:** Controls which documents show as "extracted" vs "needs_preparer_review" in the tax package UI. Documents not in this set get routed to `unsupported_or_excluded_items`.

**Assembly queries** (lines 147-179): 9 parallel queries — scores, facts, documents, expected_items, insights, feed, sources, evidence, fact_evidence. All are generic and RLS-scoped. No Schedule C/E specific logic.

**`potentialDeductionsTotal`** (lines 274-288): Sums `deduction` and `credit` category facts with high confidence. This would capture business expenses if they were stored as deduction facts, but currently no extraction pipeline produces them.

### 1.6 Frontend / UI

**Mock data (`mock-data.ts`)** — extensive Schedule C mock content already exists:
- `taxPackageSections` includes `"Business Activity"` section (verified: 1, total: 3)
- Documents list includes `"Schedule C · Beacon Studio"` (type: "Schedule C draft", status: "Action Required")
- Feed entries reference Schedule C, home-office deduction, freelance income
- Tax package page (`app.tax-package.tsx`) has a full "Businesses" section with gross receipts, business expenses, estimated tax payments

**Mock data Schedule E references:**
- `app.feed.tsx:2020`: "Schedule E evidence: cleaning, supplies, and depreciation records" (Airbnb scan profile)
- `app.feed.tsx:648`: "Lakeview Cabin 1099-K... matched 94 host payouts against your Airbnb transaction history" (rental activity)
- `mock-data.ts:700`: `"1099-K · Airbnb"` document with section "Rental Activity"
- Landing page (`index.tsx:553`): references `$1,840 home-office deduction` to Schedule C

**Assessment:** The UI already has mock/placeholder content for both Schedule C and Schedule E scenarios. None of it is wired to real extraction, real facts, or real edge function data.

---

## 2. Tax Knowledge Base 2 Coverage

### 2.1 Schedule C Coverage

**`Business, Investment & Entity Knowledge.docx`** — 421 matches for Schedule C/business terms:
- Defines Sole Proprietorship, Single-Member LLC, and other entity types
- Business Income, Business Expense, Self-Employment Income all defined
- Covers: business expense deductions, self-employment tax, depreciation and amortization, QBI deduction
- "Business Activity" entity defined connecting taxpayer → trade/business → income → expenses

**`Income Knowledge.docx`** — 81 matches:
- **Self-Employment Income** fully defined (lines 1268-1326):
  - "Income earned by a taxpayer from carrying on a trade, business, profession, or other income-producing activity as a self-employed individual"
  - Covers: gross income, earned income classification, self-employment tax, estimated tax, business expense deductions
  - Discovery: "identify self-employment activities using tax documents, payment records, invoices, business records, financial accounts"
  - Tax Graph: "preserve relationships independently from income classifications... distinguishable from employee compensation"

**`Deduction Knowledge.docx`** — 62 matches:
- Business Expense Deduction defined
- Self-Employment Deduction defined
- Ordinary and Necessary Expense requirement covered

**`IRS Forms Library.docx`** — 257 matches:
- Schedule C, Schedule E, Schedule SE all listed as supported forms
- Form 1099-NEC covered
- Self-Employment and Rental Income listed as tax concepts

### 2.2 Schedule E Coverage

**`Income Knowledge.docx`** — Rental Income fully defined (lines 1629-1683):
- "Income derived from granting another person or entity the right to use or occupy real property or personal property in exchange for consideration"
- May arise from residential, commercial, land, equipment, vehicles
- Covers: gross income, passive income classification, depreciation deductions, rental expense deductions
- Source requirements: lease arrangement, property nature, ownership interest, participation level
- Discovery: "identify Rental Income using lease agreements, property management statements, bank transactions, accounting records"
- Tax Graph: "connected to a taxpayer, rental property, lease arrangement, tenant relationship, supporting documentation"

**`Business, Investment & Entity Knowledge.docx`**:
- References to depreciation, passive activity rules
- Property-related income and expense tracking

### 2.3 Knowledge Base Assessment

The Tax Knowledge Base 2 has **comprehensive coverage** of both Schedule C and Schedule E concepts. The knowledge is defined in the standardized TaxAhead concept structure (Definition → Purpose → Why It Matters → Source Requirements → Related Concepts → Discovery/Tax Graph/Dashboard/AI Feed Implications). This means:

- The RAG/intelligence layer has the domain knowledge needed
- The gap is entirely in the **engineering implementation** (extraction, schema, edge functions, UI wiring)

---

## 3. Schedule C Requirements (Detailed)

### 3.1 IRS Schedule C Structure

**Schedule C (Form 1040) — Profit or Loss From Business (Sole Proprietorship)**

**Part I — Income:**
- Line 1: Gross receipts or sales (from 1099-NEC Box 1, 1099-K, invoices)
- Line 2: Returns and allowances
- Line 3: Line 1 minus Line 2
- Line 4: Cost of goods sold (from Part III)
- Line 5: Gross profit
- Line 6: Other income (business credit, fuel tax refund, etc.)
- Line 7: Gross income

**Part II — Expenses (14 categories):**
- Line 8: Advertising
- Line 9: Car and truck expenses (or standard mileage rate)
- Line 10: Commissions and fees
- Line 11: Contract labor
- Line 12: Depletion
- Line 13: Depreciation (Form 4562)
- Line 14: Employee benefit programs
- Line 15: Insurance (other than health)
- Line 16a: Mortgage interest
- Line 16b: Other interest
- Line 17: Legal and professional services
- Line 18: Office expense
- Line 19: Pension and profit-sharing plans
- Line 20a: Rent/lease — vehicles, machinery, equipment
- Line 20b: Rent/lease — other business property
- Line 21: Repairs and maintenance
- Line 22: Supplies
- Line 23: Taxes and licenses
- Line 24a: Travel
- Line 24b: Deductible meals
- Line 25: Utilities
- Line 26: Wages
- Line 27a: Other expenses (from Part V)
- Line 28: Total expenses
- Line 29: Tentative profit
- Line 30: Expenses for business use of home (Form 8829)
- Line 31: Net profit or loss

**Part III — Cost of Goods Sold** (for businesses with inventory)

**Part IV — Information on Your Vehicle** (if claiming car/truck expenses)

**Part V — Other Expenses** (detailed list)

### 3.2 Schedule SE — Self-Employment Tax

**Computation:**
- Net earnings from self-employment (Schedule C Line 31)
- Multiply by 92.35% (0.9235) → net earnings subject to SE tax
- Social Security tax: 12.4% on first $168,600 (2024) / $176,100 (2025)
- Medicare tax: 2.9% on all net earnings
- Additional Medicare tax: 0.9% on earnings over $200,000 (single)
- **Deductible half:** 50% of SE tax is deductible above-the-line (Schedule 1, Line 15)

### 3.3 Home Office Deduction (Form 8829)

**Two methods:**
1. **Simplified method:** $5/sqft, max 300 sqft = $1,500 max
2. **Regular method:** Percentage of home used for business × actual expenses
   - Mortgage interest, real estate taxes, insurance, utilities, repairs, depreciation

### 3.4 QBI Deduction (Section 199A)

- 20% of qualified business income from sole proprietorships
- Subject to income thresholds and phase-outs
- Limited to lesser of: 20% of QBI or 20% of taxable income

### 3.5 Source Documents for Schedule C

| Source | Data | Form/Connector |
|--------|------|----------------|
| 1099-NEC | Gross receipts (Box 1) | Extraction pipeline |
| 1099-K | Payment card/third-party income | Extraction pipeline |
| 1099-MISC | Rents (Box 1), other income (Box 3) | Extraction pipeline |
| Bank statements | Income/expense reconciliation | Plaid connector |
| Accounting software | P&L, expense categories | QBO/Xero connector |
| Invoices | Gross receipts | Gmail/Drive discovery |
| Receipts | Business expenses | Manual upload, email discovery |
| Vehicle records | Mileage log, actual expenses | Manual upload |
| Home office | Square footage, home expenses | Manual input |

---

## 4. Schedule E Requirements (Detailed)

### 4.1 IRS Schedule E Structure

**Schedule E (Form 1040) — Supplemental Income and Loss**

**Part I — Income or Loss From Rental Real Estate and Royalties:**

**For each property (up to 3 on page 1, additional on page 2):**
- Line 1: Physical address of rental property
- Line 2: Type of property (single family, multi-family, commercial, land, etc.)
- Line 3: Fair rental days / personal use days
- Line 4: Qualified joint venture checkbox

**Income (per property):**
- Line 3: Rents received
- Line 4: Royalties received
- Line 5: Other income

**Expenses (per property, 19 categories):**
- Line 5: Advertising
- Line 6: Auto and travel
- Line 7: Cleaning and maintenance
- Line 8: Commissions
- Line 9: Insurance
- Line 10: Legal and other professional fees
- Line 11: Management fees
- Line 12: Mortgage interest paid to financial institutions (Form 1098)
- Line 13: Other interest
- Line 14: Repairs
- Line 15: Supplies
- Line 16: Taxes
- Line 17: Utilities
- Line 18: Depreciation expense or depletion (Form 4562)
- Line 19: Total expenses
- Line 20: Subtract line 19 from income (rental profit/loss before deductible loss limits)
- Line 21: Net income/loss per property
- Line 22: Deductible rental loss after limitation (passive activity rules)
- Line 23-26: Totals across all properties

**Part II — Income or Loss From Partnerships and S Corporations** (K-1s — separate scope)

**Part III — Income or Loss From Estates and Trusts** (K-1s — separate scope)

### 4.2 Depreciation (Form 4562)

**Rental property depreciation:**
- **Residential rental property:** 27.5-year straight-line (MACRS GDS)
- **Commercial property:** 39-year straight-line
- **Land improvements:** 15-year
- **Land:** Not depreciable
- **Personal property (appliances, furniture):** 5-year or 7-year MACRS
- **Bonus depreciation:** Phase-down (60% in 2024, 40% in 2025)
- **Section 179:** Generally not available for rental property (with limited exceptions)

**Required data for depreciation schedule:**
- Property acquisition date
- Property acquisition cost (allocation between land and building)
- Improvement dates and costs
- Depreciation method and recovery period
- Prior-year depreciation taken

### 4.3 Passive Activity Rules

- Rental activities are generally **passive** by default
- Passive losses can only offset passive income (with $25,000 exception for active participation)
- **Real estate professional** exception: material participation allows full loss deduction
- **At-risk rules** limit loss deductions to amount at risk

### 4.4 Source Documents for Schedule E

| Source | Data | Form/Connector |
|--------|------|----------------|
| 1098 | Mortgage interest | Extraction pipeline |
| 1099-MISC Box 1 | Rents received (if payer issues one) | Extraction pipeline |
| 1099-K | Short-term rental income (Airbnb/Vrbo) | Extraction pipeline |
| Property management statements | Income/expense summaries | Manual upload, connector |
| Bank statements | Rent deposits, expense payments | Plaid connector |
| Insurance statements | Property insurance premiums | Gmail/Drive discovery |
| Tax assessor | Property tax amounts | Manual upload, county GIS |
| Closing disclosures | Acquisition date/cost for depreciation | Manual upload |
| Improvement receipts | Capital improvements | Manual upload |

---

## 5. Gap Analysis: What Exists vs What's Needed

### 5.1 Schedule C Gaps

| Area | Status | Gap Size |
|------|--------|----------|
| 1099-NEC extraction | In DOC_TYPES but NOT in MVP set | Small — add to supported set |
| 1099-K extraction | NOT in DOC_TYPES | Medium — new doc type |
| 1099-MISC extraction | NOT in DOC_TYPES | Medium — new doc type |
| Business expense tracking | Freelancer profile has 1 item (`business_expenses`) | Large — need 14+ expense categories |
| Home office deduction | Mock UI has placeholder | Large — Form 8829 logic needed |
| Self-employment tax (SECA) | Explicitly excluded from tax estimate | Large — Schedule SE computation |
| QBI deduction | Not implemented | Medium — Section 199A logic |
| Business activity entity | No table/model | Medium — need `business_activities` table |
| Cost of goods sold | Not implemented | Small — only for inventory businesses |
| Vehicle deduction | Not implemented | Medium — standard mileage vs actual |
| Fact keys for Schedule C | None defined in extraction schema | Medium — need ~30+ fact keys |
| Tax estimate income keys | No NEC/K/MISC keys | Small — add to INCOME_KEYS |

### 5.2 Schedule E Gaps

| Area | Status | Gap Size |
|------|--------|----------|
| `landlord` profile | NOT in profiles.ts | Small — add profile + expected items |
| Rental property entity | No table/model | Large — need `rental_properties` table |
| Depreciation schedule | No model/logic | Large — MACRS computation, Form 4562 |
| Rental income fact keys | None defined | Medium — need ~25+ fact keys |
| 1098 extraction | NOT in DOC_TYPES | Medium — new doc type |
| Rental expense categories | Not implemented | Medium — 19 expense categories |
| Passive activity rules | Not implemented | Large — complex limitation logic |
| Property address tracking | Only `filing_units.primary_address` | Medium — need per-property addresses |
| Fair rental days tracking | Not implemented | Small — simple integer field |
| Mortgage interest (Schedule E) | Homeowner profile has it (Schedule A) | Small — needs dual routing |

---

## 6. Schema Changes Required

### 6.1 New Tables

**`business_activities`** — Schedule C entity:
```sql
CREATE TABLE business_activities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  filing_unit_id uuid NOT NULL REFERENCES filing_units(id) ON DELETE CASCADE,
  owner_member_id uuid REFERENCES filing_unit_members(id),
  business_name text NOT NULL,
  business_type text,              -- sole_proprietorship, single_member_llc, etc.
  business_description text,
  principal_business_code text,   -- IRS NAICS code
  start_date date,
  method text DEFAULT 'cash',     -- cash or accrual
  has_inventory boolean DEFAULT false,
  home_office boolean DEFAULT false,
  home_office_sqft int,
  total_home_sqft int,
  vehicle_use boolean DEFAULT false,
  tax_year int NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

**`rental_properties`** — Schedule E entity:
```sql
CREATE TABLE rental_properties (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  filing_unit_id uuid NOT NULL REFERENCES filing_units(id) ON DELETE CASCADE,
  owner_member_id uuid REFERENCES filing_unit_members(id),
  property_address jsonb NOT NULL,  -- {street, city, state, zip}
  property_type text,                -- single_family, multi_family, commercial, etc.
  acquisition_date date,
  acquisition_cost numeric,
  land_value numeric,               -- for depreciation allocation
  building_value numeric,
  fair_rental_days int,
  personal_use_days int,
  qualified_joint_venture boolean DEFAULT false,
  material_participation boolean DEFAULT false,
  is_short_term_rental boolean DEFAULT false,  -- Airbnb/Vrbo
  tax_year int NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

**`depreciation_assets`** — Depreciation schedule:
```sql
CREATE TABLE depreciation_assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  filing_unit_id uuid NOT NULL REFERENCES filing_units(id) ON DELETE CASCADE,
  property_id uuid REFERENCES rental_properties(id) ON DELETE CASCADE,
  business_id uuid REFERENCES business_activities(id) ON DELETE CASCADE,
  description text NOT NULL,
  acquisition_date date NOT NULL,
  cost numeric NOT NULL,
  recovery_period_years int,       -- 27.5, 39, 15, 7, 5
  method text DEFAULT 'sl',        -- straight-line, 200db, 150db
  convention text,                  -- mid_month, mid_quarter, half_year
  prior_depreciation numeric DEFAULT 0,
  current_year_depreciation numeric,
  bonus_depreciation_pct numeric,
  section_179_amount numeric,
  tax_year int NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

**RLS:** All three tables need `enable row level security` + `owns_fu(filing_unit_id)` policies (same pattern as existing tables).

### 6.2 Profiles Extension

**`profiles.ts` — Add `landlord` profile:**
```typescript
landlord: [
  { category: "rental", key: "rental_property", label: "Rental property" },
  { category: "rental", key: "rental_income", label: "Rental income" },
  { category: "rental", key: "rental_expenses", label: "Rental expenses" },
  { category: "rental", key: "depreciation", label: "Depreciation schedule" },
  { category: "rental", key: "mortgage_interest", label: "Mortgage interest (rental)" },
],
```

**Extend `freelancer` profile:**
```typescript
freelancer: [
  { category: "income", key: "self_employment_income", label: "Self-employment income" },
  { category: "income", key: "gross_receipts", label: "Gross receipts" },
  { category: "business", key: "business_type", label: "Business type" },
  { category: "business", key: "business_expenses", label: "Business expenses" },
  { category: "business", key: "home_office", label: "Home office deduction" },
  { category: "business", key: "vehicle_expenses", label: "Vehicle expenses" },
  { category: "withholding", key: "estimated_tax_payments", label: "Estimated tax payments" },
],
```

**New profile triggers:**
```typescript
"income.box_1_nonemployee_compensation": "freelancer",
"income.gross_receipts": "freelancer",
"business.business_type": "freelancer",
"business.home_office": "freelancer",
"rental.rental_income": "landlord",
"rental.rental_property": "landlord",
"rental.depreciation": "landlord",
"property.rental_mortgage_interest": "landlord",
```

### 6.3 New Fact Categories

**`extraction.ts` — Add to FACT_CATEGORIES:**
```typescript
export const FACT_CATEGORIES = [
  "income", "withholding", "deduction", "credit", "contribution",
  "investment", "property", "business", "identity",
  "rental",  // NEW
] as const;
```

---

## 7. Edge Function Changes

### 7.1 Extraction Pipeline (`extraction.ts`)

**Phase 1 — Add 1099-NEC to MVP set:**
- Add `1099_nec_2025` to `SUNDAY_MVP_SUPPORTED_DOC_TYPES`
- Add fact key guidance for 1099-NEC (payer_name, payer_tin, recipient_name, recipient_tin, box_1_nonemployee_compensation, box_4_federal_tax_withheld)
- Update SYSTEM_PROMPT to include 1099-NEC
- Update EXTRACTION_TOOL description

**Phase 2 — Add new document types:**
- `1099_misc_2025` — Box 1 (rents), Box 2 (royalties), Box 3 (other income)
- `1099_k_2025` — Payment card/third-party network transactions
- `1098_2025` — Mortgage interest statement (for rental properties)

**Phase 3 — Add Schedule C/E fact vocabulary:**
- Schedule C expense categories (advertising, car_truck, commissions, insurance, legal, office, rent, repairs, supplies, travel, utilities, other)
- Schedule E expense categories (advertising, auto_travel, cleaning_maintenance, commissions, insurance, legal, management_fees, mortgage_interest, other_interest, repairs, supplies, taxes, utilities, depreciation)
- Business metadata (business_name, business_type, principal_business_code)
- Rental metadata (property_address, property_type, fair_rental_days, personal_use_days)

### 7.2 Tax Estimate (`tax-estimate.ts`)

**Phase 1 — Include self-employment income in gross income:**
- Add `box_1_nonemployee_compensation`, `self_employment_income`, `gross_receipts` to `INCOME_KEYS`
- Add `box_4_federal_tax_withheld` to `PAYMENT_KEYS`

**Phase 2 — Self-employment tax computation:**
- Add SECA calculation: net SE income × 0.9235 × (12.4% + 2.9%)
- Add deductible half of SE tax to above-the-line deductions
- Track SE income separately from wages for SS wage base interaction

**Phase 3 — Schedule E integration:**
- Add `rental_income`, `rents_received` to `INCOME_KEYS`
- Add rental expenses as deduction facts
- Include net rental profit/loss in AGI computation

### 7.3 Get-Tax-Package (`get-tax-package/index.ts`)

**Phase 1:**
- Add `1099_nec_2025` to `SUNDAY_SUPPORTED_DOC_TYPES`

**Phase 2:**
- Add new doc types as they become supported
- Consider adding business_activities and rental_properties to the assembly queries
- Add Schedule C/E summary sections to the response payload

---

## 8. UI Changes Needed

### 8.1 Tax Package Page (`app.tax-package.tsx`)

**Current mock content already shows:**
- Business Activity section with gross receipts, expenses, estimated payments
- Schedule C · Beacon Studio (freelance design)
- Home-office deduction line item
- SEP-IRA evidence review

**Needs real wiring:**
- Replace mock data with edge function data for `businesses` section
- Add Schedule E section (rental properties, income, expenses, depreciation)
- Wire `unsupported_or_excluded_items` to show 1099-NEC/MISC/K when not yet supported

### 8.2 Feed Page (`app.feed.tsx`)

**Current mock content references:**
- Schedule C (home-office deduction, QBI, freelance income)
- Schedule E (Airbnb rental income, cleaning/supplies/depreciation)

**Needs real wiring:**
- Feed entries generated from actual insights/expected_items for Schedule C/E
- Clarification questions for business income classification

### 8.3 New UI Components (Future)

- **Business Activity Form:** Capture business name, type, description, NAICS code
- **Business Expense Tracker:** 14-category expense input with evidence attachment
- **Home Office Calculator:** Simplified vs regular method comparison
- **Rental Property Setup:** Address, type, acquisition info, depreciation inputs
- **Rental Expense Tracker:** 19-category expense input per property
- **Depreciation Schedule:** MACRS calculator, asset listing, prior-year carryforward

---

## 9. Estimated Effort

### Phase 1: 1099-NEC Extraction → Schedule C Foundation (4-6 hours)

| Task | Effort |
|------|--------|
| Add `1099_nec_2025` to MVP supported types | 30 min |
| Add fact key guidance + system prompt | 30 min |
| Update tax estimate INCOME_KEYS | 15 min |
| Update profiles.ts triggers | 15 min |
| Update get-tax-package supported types | 15 min |
| Update edge-functions.ts types | 15 min |
| Update/fix extraction tests | 1 hr |
| Manual testing with real 1099-NEC PDFs | 2 hrs |
| **Subtotal** | **~5 hrs** |

### Phase 2: Schedule C Full Support (16-24 hours)

| Task | Effort |
|------|--------|
| `business_activities` table + migration + RLS | 2 hrs |
| Business expense fact vocabulary (14 categories) | 2 hrs |
| Extraction pipeline: 1099-K, 1099-MISC doc types | 4 hrs |
| Self-employment tax (SECA) computation | 3 hrs |
| Home office deduction logic (Form 8829) | 3 hrs |
| QBI deduction (Section 199A) — basic | 2 hrs |
| UI: Business Activity section wiring | 3 hrs |
| UI: Business expense input/tracking | 3 hrs |
| Tests | 3 hrs |
| **Subtotal** | **~25 hrs** |

### Phase 3: Schedule E Full Support (20-30 hours)

| Task | Effort |
|------|--------|
| `rental_properties` table + migration + RLS | 2 hrs |
| `depreciation_assets` table + migration + RLS | 2 hrs |
| Landlord profile + expected items + triggers | 1 hr |
| Rental income/expense fact vocabulary | 2 hrs |
| Extraction pipeline: 1098 doc type | 3 hrs |
| Depreciation computation (MACRS, Form 4562) | 5 hrs |
| Passive activity loss limitation logic | 4 hrs |
| Tax estimate: include rental income/expenses | 2 hrs |
| UI: Rental Properties section | 3 hrs |
| UI: Depreciation schedule view | 2 hrs |
| UI: Per-property income/expense tracking | 3 hrs |
| Tests | 3 hrs |
| **Subtotal** | **~32 hrs** |

### Total Estimated Effort

| Phase | Hours | Priority |
|-------|-------|----------|
| Phase 1: 1099-NEC extraction | 4-6 | **High** — enables Schedule C, standalone task |
| Phase 2: Schedule C full | 16-24 | **High** — core user persona (freelancer) |
| Phase 3: Schedule E full | 20-30 | **Medium** — landlord persona, more complex |
| **Total** | **40-60** | |

---

## 10. Priority Ranking vs Other Work

### Context from Memory

From `project_taxahead_connector_platform.md` (memory):
- Main unified (4-way reconciliation)
- Gmail smoke live-reverified 2026-07-19
- **TA-MVP-2 needs human sign-off**

From `project_taxahead_plaid_connector_status.md` (memory):
- Plaid connector landed 2026-07-18, fail-closed by design
- Gap = Link-token + exchange
- IRS §7216 consent needed

### Proposed Priority Order

1. **TA-MVP-2 human sign-off** (blocker for next phase) — needs Nnamdi
2. **Plaid connector completion** (Link-token + exchange + §7216) — already in progress
3. **Phase 1: 1099-NEC extraction** (this work) — 4-6 hrs, enables freelancer persona
4. **Phase 2: Schedule C full** — 16-24 hrs, high-value for self-employed users
5. **Phase 3: Schedule E full** — 20-30 hrs, important for real estate investors (Nnamdi's own use case)
6. **Additional doc types** (1098, 1099-B, 5498, etc.) — incremental expansion

### Rationale

- **Phase 1 is the highest-priority item from this research** because:
  - It's a small, self-contained change (~42 lines)
  - No schema migration needed
  - Unblocks the freelancer persona that already exists in mock data
  - The 1099-NEC research (saved earlier today) already has the full implementation checklist
  - Nnamdi's test case includes 1099 contractor income → this is the entry point

- **Phase 2 should follow Phase 1** because:
  - Schedule C is the most common self-employment filing scenario
  - The mock data already demonstrates the UX vision
  - Business expense tracking unlocks the "intelligence layer" value prop
  - SECA tax is a major pain point for freelancers

- **Phase 3 is medium priority** because:
  - Rental income is important but less common than self-employment
  - Depreciation is complex (MACRS, mid-month convention, land allocation)
  - Passive activity rules add significant complexity
  - However, Nnamdi is a real estate investor, so this has personal relevance

### Dependencies

- **Phase 1 depends on:** Nothing (self-contained)
- **Phase 2 depends on:** Phase 1 + Plaid connector (for bank transaction expense categorization)
- **Phase 3 depends on:** Phase 1 (for 1099-MISC/1098 extraction) + property data connectors

---

## 11. Test Case Alignment

The user's tax situation maps to these requirements:

| Income Source | Schedule | Phase | Status |
|--------------|----------|-------|--------|
| W-2 employment income | Form 1040 Line 1 | ✅ Done | Supported (w2_2025) |
| 1099 contractor income (1099-NEC) | Schedule C | Phase 1 | Not yet supported |
| Self-employment income | Schedule C | Phase 1-2 | Not yet supported |
| Real estate income | Schedule E | Phase 3 | Not yet supported |
| 1 state | State return | Out of scope | Federal-only for now |

**Full coverage requires Phases 1 + 2 + 3.**

---

## 12. Implementation Checklist

### Phase 1 (Immediate)

- [ ] Gather 3-5 sample 1099-NEC PDFs for testing
- [ ] Add `1099_nec_2025` to `SUNDAY_MVP_SUPPORTED_DOC_TYPES`
- [ ] Add fact key guidance to EXTRACTION_TOOL description
- [ ] Update SYSTEM_PROMPT
- [ ] Add NEC keys to tax estimate INCOME_KEYS and PAYMENT_KEYS
- [ ] Add NEC profile trigger to profiles.ts
- [ ] Add to `SUNDAY_SUPPORTED_DOC_TYPES` in get-tax-package
- [ ] Update edge-functions.ts type definitions
- [ ] Fix/update extraction tests
- [ ] Manual extraction test with real 1099-NEC

### Phase 2 (Next Sprint)

- [ ] Design `business_activities` table schema
- [ ] Write migration 0018 + RLS policies
- [ ] Define Schedule C fact vocabulary (14 expense categories)
- [ ] Add 1099-K and 1099-MISC doc types to extraction
- [ ] Implement SECA tax computation
- [ ] Implement home office deduction (simplified + regular)
- [ ] Implement basic QBI deduction
- [ ] Wire Business Activity section in tax package UI
- [ ] Build business expense input/tracking UI
- [ ] Tests for all new logic

### Phase 3 (Future Sprint)

- [ ] Design `rental_properties` + `depreciation_assets` table schemas
- [ ] Write migration 0019 + RLS policies
- [ ] Add `landlord` profile + expected items + triggers
- [ ] Define Schedule E fact vocabulary (19 expense categories)
- [ ] Add 1098 doc type to extraction
- [ ] Implement MACRS depreciation computation
- [ ] Implement passive activity loss limitations
- [ ] Wire Rental Properties section in tax package UI
- [ ] Build depreciation schedule UI
- [ ] Build per-property income/expense tracking UI
- [ ] Tests for all new logic
