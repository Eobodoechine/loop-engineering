# TaxAhead 1099-NEC/MISC Extraction Requirements

**Date:** 2026-07-20
**Target repo:** `~/Claude/Projects/taxahead`

---

## 1. Current State Assessment

### What Exists

**Supported document types** (extraction.ts:5-18):
- `w2_2025` — W-2 wage income
- `1099_int_2025` — 1099-INT interest income
- `1099_div_2025` — 1099-DIV dividend income
- `unknown_tax_document` — fallback for unsupported/low-confidence

**1099-NEC is explicitly excluded.** The test `extraction.sunday-mvp.test.ts:95-109` proves that a `1099_nec_2025` doc_type normalizes to `unknown_tax_document`. The SYSTEM_PROMPT (extraction.ts:125-131) states: "Only these classes are supported: w2_2025, 1099_int_2025, 1099_div_2025."

**Extraction pipeline** (extract-document/index.ts):
- Generic pipeline that works for any document type
- Document classification is driven entirely by the Claude tool schema in `_shared/extraction.ts`
- Pipeline: upload → claim lease → MIME check → download → dedupe → Claude API call → normalize → finalize
- No document-type-specific branching in the pipeline itself

**Schema** (migrations 0001, 0003, 0008):
- `documents` table: stores `doc_type` as free text (no enum constraint)
- `facts` table: stores extracted facts with `category`, `key`, `value` (JSONB), `confidence`, `state`
- `evidence` table: stores raw extraction output with `extracted` (JSONB)
- **No schema changes needed** — the existing schema is already generic enough to store any fact type

**Freelancer profile** (profiles.ts:14-18):
```typescript
freelancer: [
  { category: "income", key: "self_employment_income", label: "Self-employment income" },
  { category: "business", key: "business_expenses", label: "Business expenses" },
  { category: "withholding", key: "estimated_tax_payments", label: "Estimated tax payments" },
]
```

**Profile triggers** (profiles.ts:37-38):
```typescript
"income.self_employment_income": "freelancer",
"business.business_expenses": "freelancer",
```

**Tax estimate** (tax-estimate.ts:153-166):
- `INCOME_KEYS` includes: `wages`, `box_1_wages`, `interest_income`, `box_1_interest_income`, `ordinary_dividends`, `box_1a_total_ordinary_dividends`
- **No 1099-NEC keys** — would need to add `box_1_nonemployee_compensation` or similar
- `EXCLUDED_ITEMS` (tax-estimate.ts:43-46) explicitly excludes self-employment tax

**UI/adapter layer**:
- `SUNDAY_SUPPORTED_DOC_TYPES` in get-tax-package (index.ts:71) controls what shows as "extracted" vs "needs_preparer_review"
- `ExtractDocumentClassification` type in edge-functions.ts:27-31 has only the 3 types + unknown
- Mock data (mock-data.ts:810, 902) already references 1099-NEC in UI examples but not wired to real extraction

### What's Missing

1. **1099-NEC not in supported doc types** — currently routes to `unknown_tax_document`
2. **No 1099-NEC fact key guidance** in extraction tool schema
3. **No 1099-NEC keys in tax estimate INCOME_KEYS** — won't flow to gross income calculation
4. **No profile trigger for 1099-NEC-specific keys** — `box_1_nonemployee_compensation` won't trigger freelancer profile
5. **No 1099-MISC support** — separate form, different boxes (rent, royalties, etc.)
6. **No Schedule C logic** — self-employment tax, business expense deductions, QBI deduction all excluded

---

## 2. 1099-NEC/MISC Field Requirements

### 1099-NEC (Nonemployee Compensation)

**Required fields:**
- **Box 1:** Nonemployee compensation (the primary income amount)
- **Payer info:**
  - Name
  - TIN (Taxpayer Identification Number)
  - Address
- **Recipient info:**
  - Name
  - TIN
  - Address
- **Optional:**
  - Box 2: Payer made direct sales of $5,000+ of consumer products (checkbox)
  - Box 3: (not used in current form)
  - Box 4: Federal income tax withheld (backup withholding)
  - Box 5: State tax withheld
  - Box 6: State/Payer's state no.
  - State ID number

**Schedule C connection:**
- Box 1 → Schedule C Line 1 (Gross receipts or sales)
- Triggers self-employment tax calculation (Schedule SE)
- Subject to QBI deduction (20% pass-through deduction)
- May require estimated tax payments (Form 1040-ES)

### 1099-MISC (Miscellaneous Income)

**Common boxes (partial list):**
- Box 1: Rents
- Box 2: Royalties
- Box 3: Other income
- Box 4: Federal income tax withheld
- Box 6: Medical and health care payments
- Box 7: Direct sales of $5,000+ consumer products
- Box 8: Substitute payments in lieu of dividends or tax-exempt interest
- Box 10: Gross proceeds paid to an attorney
- Box 14: Excess golden parachute payments
- Box 15: Nonqualified deferred compensation
- Boxes 16-18: State tax withholding

**Schedule connections:**
- Box 1 (Rents) → Schedule E
- Box 2 (Royalties) → Schedule E
- Box 3 (Other income) → Schedule 1, Line 8z
- Box 6 (Medical) → Schedule A (if deductible)

---

## 3. Schema Changes Required

### No Schema Changes Needed

The existing schema is already generic:
- `documents.doc_type` is free text (no enum)
- `facts` table stores any `category`/`key`/`value` combination
- `evidence.extracted` is JSONB
- No new tables or columns required

### Optional Schema Enhancement (Low Priority)

If we want to enforce document type validation at the DB level:

```sql
-- Migration: add doc_type enum (NOT RECOMMENDED — breaks extensibility)
-- The current free-text approach is more flexible for future doc types
```

**Decision:** Keep the current free-text `doc_type` column. No schema migration needed.

---

## 4. Extraction Pipeline Changes

### A. Extraction Layer (`supabase/functions/_shared/extraction.ts`)

**Changes required:**

1. **Add 1099-NEC to DOC_TYPES** (line 5-10):
```typescript
export const DOC_TYPES = [
  "w2_2025",
  "1099_int_2025",
  "1099_div_2025",
  "1099_nec_2025",  // NEW
  "1099_misc_2025", // NEW (optional, Phase 2)
  "unknown_tax_document",
] as const;
```

2. **Add to SUNDAY_MVP_SUPPORTED_DOC_TYPES** (line 14-18):
```typescript
export const SUNDAY_MVP_SUPPORTED_DOC_TYPES = [
  "w2_2025",
  "1099_int_2025",
  "1099_div_2025",
  "1099_nec_2025",  // NEW
] as const;
```

3. **Update EXTRACTION_TOOL description** (line 34-42):
```typescript
description:
  "Record the classification and extracted tax facts for a single document. " +
  "Call this exactly once with your best assessment. Only W-2, 1099-INT, " +
  "1099-DIV, and 1099-NEC tax year 2025 are deterministically supported. If the " +
  "document is unsupported, ambiguous, low-confidence, or not tax-relevant, " +
  "set doc_type='unknown_tax_document'.",
```

4. **Add fact key guidance** (line 85-90):
```typescript
key: {
  type: "string",
  description:
    "Snake_case fact name. For w2_2025 use employer_name, employee_name, " +
    "tax_year, box_1_wages, box_2_federal_income_tax_withheld. For " +
    "1099_int_2025 use payer_name, recipient_name, tax_year, " +
    "box_1_interest_income. For 1099_div_2025 use payer_name, " +
    "recipient_name, tax_year, box_1a_total_ordinary_dividends, and " +
    "box_1b_qualified_dividends when present. For 1099_nec_2025 use " +
    "payer_name, payer_tin, recipient_name, recipient_tin, tax_year, " +
    "box_1_nonemployee_compensation, box_4_federal_tax_withheld (if present), " +
    "box_5_state_tax_withheld (if present).",
},
```

5. **Update SYSTEM_PROMPT** (line 125-131):
```typescript
export const SYSTEM_PROMPT =
  "You are the TaxAhead discovery engine. You classify a single document and extract " +
  "structured US federal tax facts from it for the manual-upload Sunday MVP checkpoint. " +
  "Rules: never invent values you cannot read; if a field is unreadable, omit the fact " +
  "rather than guessing. Report low confidence honestly. Only these classes are supported: " +
  "w2_2025, 1099_int_2025, 1099_div_2025, 1099_nec_2025. Unsupported, ambiguous, non-2025, or low-confidence " +
  "documents must be unknown_tax_document. You must call the record_tax_document tool exactly once.";
```

### B. Get-Tax-Package (`supabase/functions/get-tax-package/index.ts`)

**Change line 71:**
```typescript
const SUNDAY_SUPPORTED_DOC_TYPES = new Set(["w2_2025", "1099_int_2025", "1099_div_2025", "1099_nec_2025"]);
```

### C. Edge Function Types (`src/lib/edge-functions.ts`)

**Change line 27-31:**
```typescript
export type ExtractDocumentClassification =
  | "w2_2025"
  | "1099_int_2025"
  | "1099_div_2025"
  | "1099_nec_2025"  // NEW
  | "unknown_tax_document";
```

**Change line 80:**
```typescript
classification: "w2_2025" | "1099_int_2025" | "1099_div_2025" | "1099_nec_2025";
```

### D. Tax Estimate (`supabase/functions/_shared/tax-estimate.ts`)

**Add to INCOME_KEYS (line 153-166):**
```typescript
const INCOME_KEYS = new Set([
  "income.wages",
  "wages",
  "box_1_wages",
  "taxable_wages",
  "w2_wages",
  "interest_income",
  "taxable_interest",
  "box_1_interest_income",
  "ordinary_dividends",
  "dividend_income",
  "total_ordinary_dividends",
  "box_1a_total_ordinary_dividends",
  // NEW: 1099-NEC keys
  "box_1_nonemployee_compensation",
  "nonemployee_compensation",
  "self_employment_income",
]);
```

### E. Profiles (`supabase/functions/_shared/profiles.ts`)

**Add profile trigger (line 37-38):**
```typescript
export const PROFILE_TRIGGERS: Record<string, string> = {
  "income.employer": "employee",
  "income.wages": "employee",
  "income.self_employment_income": "freelancer",
  "income.box_1_nonemployee_compensation": "freelancer",  // NEW
  "business.business_expenses": "freelancer",
  "property.mortgage_interest": "homeowner",
  "property.property_tax": "homeowner",
  "investment.brokerage_activity": "investor",
  "investment.dividend_income": "investor",
  "investment.capital_gains": "investor",
};
```

### F. Tests

**Update `extraction.sunday-mvp.test.ts`:**

1. **Remove/update test at line 95-109** — the test that asserts `1099_nec_2025` → `unknown_tax_document` must be changed to expect it as a supported type.

2. **Add new tests:**
```typescript
Deno.test("[BEHAVIORAL] 1099-NEC high-confidence docs normalize to extracted/classified", () => {
  assertEquals(
    normalizeSundayMvpExtraction(extraction({ doc_type: "1099_nec_2025" })),
    {
      docType: "1099_nec_2025",
      classification: "1099_nec_2025",
      taxYear: 2025,
      issuer: "ACME Payroll",
      classificationConfidence: 0.93,
      checkpointStatus: "extracted",
      documentStatus: "classified",
      persistFacts: true,
    },
  );
});
```

3. **Update SUNDAY_MVP_CLASSES constant** (line 12-17):
```typescript
const SUNDAY_MVP_CLASSES = [
  "w2_2025",
  "1099_int_2025",
  "1099_div_2025",
  "1099_nec_2025",  // NEW
  "unknown_tax_document",
] as readonly string[];
```

4. **Update assertion at line 36-39** — remove the check that 1099-NEC is NOT in the schema.

---

## 5. Estimated Effort

### Code Changes

| File | Lines Changed | Complexity |
|------|---------------|------------|
| `extraction.ts` | ~15 lines | Low (add to arrays, update strings) |
| `get-tax-package/index.ts` | 1 line | Trivial |
| `edge-functions.ts` | 2 lines | Trivial |
| `tax-estimate.ts` | 3 lines | Trivial |
| `profiles.ts` | 1 line | Trivial |
| `extraction.sunday-mvp.test.ts` | ~20 lines | Low (update assertions, add test) |
| **Total** | **~42 lines** | **Low** |

### Testing Effort

- **Unit tests:** 2-3 new test cases (1099-NEC normalization, tax estimate with NEC income, profile trigger)
- **Integration test:** Upload a real 1099-NEC PDF, verify extraction → facts → tax package flow
- **Manual testing:** 1-2 hours to verify Claude extracts 1099-NEC fields correctly from sample documents

### Estimated Time

- **Implementation:** 2-3 hours (including tests)
- **QA/Testing:** 2-3 hours (sample documents, edge cases, UI verification)
- **Total:** 4-6 hours for a single developer

### Risk Assessment

- **Low risk:** Changes are additive, no schema migration, no breaking changes to existing W-2/1099-INT/1099-DIV extraction
- **Claude model behavior:** Need to verify Claude correctly extracts 1099-NEC fields (payer TIN, Box 1, etc.) — may require prompt tuning
- **Test regression:** The existing test that asserts 1099-NEC → unknown must be updated; failing to do so will break CI

---

## 6. Dependencies on Other Priorities

### Blockers

**None.** This is a self-contained change that doesn't depend on other work.

### Dependencies (Downstream)

1. **Plaid connector** (TA-MVP-2): Not a blocker, but 1099-NEC data from bank transactions could enrich extracted facts
2. **Gmail connector improvements**: 1099-NEC documents often arrive via email; better Gmail attachment extraction would improve discovery
3. **Schedule C logic** (future): Full Schedule C support (business expenses, home office deduction, QBI) is a separate work item that would build on 1099-NEC extraction
4. **Self-employment tax calculation** (future): Currently excluded in `tax-estimate.ts:43-46`; adding SE tax would require extending the tax estimate engine

### Priority Context

- **Current MVP scope:** The "Sunday MVP" deliberately scoped to W-2/1099-INT/1099-DIV
- **Freelancer persona:** Already defined in profiles.ts but has no extraction support yet
- **User demand:** Mock data (mock-data.ts:810, 902) shows 1099-NEC in UI examples, suggesting it's a planned feature
- **Competitive parity:** Most tax prep tools (TurboTax, H&R Block) support 1099-NEC extraction; TaxAhead should too

### Recommended Phasing

**Phase 1 (This work):** 1099-NEC extraction → facts → tax package
- Add `1099_nec_2025` to supported types
- Extract Box 1 (nonemployee compensation), payer/recipient info
- Flow to gross income in tax estimate
- Trigger freelancer profile

**Phase 2 (Future):** 1099-MISC support
- Add `1099_misc_2025` to supported types
- Extract Box 1 (rents), Box 2 (royalties), Box 3 (other income)
- Route to appropriate schedules (E, Schedule 1)

**Phase 3 (Future):** Schedule C logic
- Business expense deduction tracking
- Home office deduction calculation
- QBI deduction (20% pass-through)
- Self-employment tax (Schedule SE)

---

## 7. Implementation Checklist

### Pre-Implementation

- [ ] Gather 3-5 sample 1099-NEC PDFs for testing
- [ ] Verify Claude can extract payer TIN, recipient TIN, Box 1 amount from samples
- [ ] Decide on fact key naming: `box_1_nonemployee_compensation` vs `nonemployee_compensation` vs `self_employment_income`

### Implementation

- [ ] Update `extraction.ts`: DOC_TYPES, SUNDAY_MVP_SUPPORTED_DOC_TYPES, EXTRACTION_TOOL, SYSTEM_PROMPT
- [ ] Update `get-tax-package/index.ts`: SUNDAY_SUPPORTED_DOC_TYPES
- [ ] Update `edge-functions.ts`: ExtractDocumentClassification, TaxPackageExtractedInput
- [ ] Update `tax-estimate.ts`: INCOME_KEYS
- [ ] Update `profiles.ts`: PROFILE_TRIGGERS
- [ ] Update `extraction.sunday-mvp.test.ts`: remove old test, add new tests

### Testing

- [ ] Run unit tests: `deno test supabase/functions/_shared/extraction.sunday-mvp.test.ts`
- [ ] Run integration test: upload real 1099-NEC PDF, verify extraction
- [ ] Verify tax estimate includes 1099-NEC income in gross income
- [ ] Verify freelancer profile triggers when 1099-NEC is present
- [ ] Verify UI shows 1099-NEC as "extracted" not "needs_preparer_review"

### Documentation

- [ ] Update README or spec.md to list 1099-NEC as supported
- [ ] Update mock data to remove hardcoded 1099-NEC examples (now real)

---

## 8. Technical Notes

### Fact Key Naming Convention

**Recommendation:** Use `box_1_nonemployee_compensation` for consistency with existing keys:
- `box_1_wages` (W-2)
- `box_1_interest_income` (1099-INT)
- `box_1a_total_ordinary_dividends` (1099-DIV)
- `box_1_nonemployee_compensation` (1099-NEC)

**Alternative:** Use `self_employment_income` to match the existing profile trigger. This would avoid adding a new trigger but is less specific to the form.

**Decision:** Use `box_1_nonemployee_compensation` as the primary key, add it as a profile trigger. This maintains form-specific granularity.

### Backup Withholding (Box 4)

1099-NEC Box 4 (federal tax withheld) should be extracted as `box_4_federal_tax_withheld` and added to `PAYMENT_KEYS` in tax-estimate.ts:

```typescript
const PAYMENT_KEYS = new Set([
  "withholding.federal_withholding",
  "federal_withholding",
  "federal_income_tax_withheld",
  "box_2_federal_income_tax_withheld",
  "federal_tax_withheld",
  "box_4_federal_tax_withheld",  // NEW: 1099-NEC backup withholding
  "estimated_tax_payments",
  "estimated_payments",
  "federal_estimated_tax_payments",
]);
```

### State Tax Withholding (Box 5)

1099-NEC Box 5 (state tax withheld) is out of scope for federal-only MVP. Extract but don't use in tax estimate.

### Payer/Recipient TIN

Extract as `payer_tin` and `recipient_tin` for identity matching and audit trail. Store in facts table but don't display in UI (PII).

---

## 9. Summary

**Current state:** 1099-NEC is explicitly unsupported and routes to `unknown_tax_document`.

**Required changes:** ~42 lines of code across 6 files, no schema migration.

**Estimated effort:** 4-6 hours (implementation + testing).

**Risk:** Low — additive changes, no breaking changes, self-contained.

**Dependencies:** None (blockers), but enables future Schedule C logic.

**Recommendation:** Implement as a focused 1-day task. Gather sample 1099-NEC PDFs first to validate Claude extraction behavior before coding.
