# TaxAhead RAG / Tax Knowledge System Audit

**Date:** 2026-07-20
**Auditor:** Mode D Research (direct file reads, no sub-agents)
**Repo:** `<HOME>/Claude/Projects/taxahead`
**Scope:** ask-taxahead edge function, extraction pipeline, knowledge base, tax coverage

---

## Executive Summary

**TaxAhead does not have a RAG system or a tax knowledge base.** The `ask-taxahead`
edge function is a **grounded Q&A endpoint** that retrieves only the user's own
structured tax facts from the database and asks Claude to answer questions strictly
from that context. There are zero IRS publications, zero tax law documents, zero
form instructions, zero state tax rules, and zero vector embeddings anywhere in the
codebase. The system cannot answer general tax questions — it can only report back
what it already knows about the user's discovered tax data.

This is by design for the current "Sunday MVP" milestone, which is explicitly scoped
to: **single filer, federal-only, TY2024/2025, uploads-first document discovery**.
The architecture is solid for its scope, but the scope is dramatically narrower than
"support actual tax filing for ANYONE."

---

## 1. Where Is the Knowledge Base?

**There is no knowledge base.** Exhaustive search across the entire repository found:

| Location searched | Result |
|---|---|
| `docs/` | 4 files — all internal engineering docs, no tax content |
| `knowledge/`, `rag/`, `data/`, `corpus/`, `embeddings/` | **Do not exist** |
| `supabase/functions/ask-taxahead/` | 2 files — the function + its tests |
| Vector store / pgvector config | `config.toml` has `[storage.vector]` section **commented out** |
| `.env` files | No `OPENAI_API_KEY`, no embedding config, no vector DB URL |
| `package.json` | No embedding/vector dependencies |
| Migrations (16 SQL files) | No pgvector extension, no vector columns |
| PDF/tax document corpus | **None** in the repo (only a test W-2 PDF in loop-team/research) |

**The only "tax knowledge" hardcoded into the system is:**
- `tax-estimate.ts`: TY2024 and TY2025 federal tax brackets and standard deductions
  (for single, MFJ, MFS, HOH) — ~100 lines of constants
- `profiles.ts`: 4 taxpayer profiles (employee, freelancer, homeowner, investor) with
  3 expected items each — ~45 lines
- `extraction.ts`: 3 supported document types — W-2, 1099-INT, 1099-DIV

---

## 2. RAG Architecture — What Actually Exists

### 2.1 The ask-taxahead Pipeline

```
User Question
     │
     ▼
┌─────────────────┐
│ Auth (JWT)       │ ← Supabase RLS enforces ownership
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ 3 parallel DB queries (grounding slice): │
│  • scores: readiness, filing_confidence  │
│  • facts: all facts for filing unit      │
│    (joined to evidence→documents→sources)│
│  • expected_items: missing items         │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Context Assembly:                        │
│  "Tax year: 2025. Filing status: single" │
│  "Readiness: 72%. Confidence: 81%."      │
│  "Discovered facts:"                     │
│   - [C1] [income] wages: 123456.78       │
│     (confidence 0.99; W-2; ACME Corp)    │
│  "Missing information:"                  │
│   - Self-employment income (freelancer)  │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Claude API call:                         │
│  • System prompt: "answer ONLY from      │
│    CONTEXT block, never invent facts"    │
│  • Forced tool: answer_from_evidence     │
│    {status, answer, citation_ids}        │
│  • Single-turn, stateless               │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│ Server-side validation:                  │
│  • Every citation_id must be a known ID  │
│  • Every [C1] marker must match a known  │
│    citation                              │
│  • Every sentence must have ≥1 citation  │
│  • bidirectional marker↔id check         │
│  • SHA-256 context hash for audit trail  │
└────────┬────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Response:        │
│  answer + citations + proof metadata     │
│  (or fail-closed error)                  │
└─────────────────┘
```

### 2.2 Key Architectural Properties

| Property | Status | Assessment |
|---|---|---|
| **Retrieval mechanism** | SQL query, not vector search | Deterministic, no embedding step. Retrieves ALL facts for the filing unit — no relevance filtering |
| **Chunking/embedding** | None | No document chunking, no embeddings, no vector similarity search |
| **Grounding** | Strict — system prompt + forced tool + server-side validation | Best-in-class for its scope. Every factual sentence must cite a known fact ID |
| **Citations** | Yes — [C1], [C2] markers trace to fact→evidence→document→source chain | Full provenance chain back to the original document bytes |
| **Hallucination guardrails** | Strong — 3 layers | (1) System prompt forbids invention (2) Forced tool output schema (3) Server-side bidirectional marker validation |
| **Dollar figure guard** | Explicit prohibition | System prompt: "NEVER compute or state a dollar figure not already in the context" |
| **Fail-closed design** | Excellent | Unknown citations, uncited sentences, missing markers → 502, no answer returned |
| **Multi-turn memory** | None | Stateless single-turn. History persisted to feed_messages but never read back |
| **Scope boundary** | Enforced | `out_of_scope` status for non-tax-record questions |

### 2.3 What the System CAN Answer

- "What were my wages?" → reads fact from W-2
- "What documents do you have?" → lists discovered documents
- "How ready am I to file?" → reads readiness score
- "What information is missing?" → reads expected_items
- "What's my federal tax estimate?" → reads the computed tax_estimate (from tax-estimate.ts)

### 2.4 What the System CANNOT Answer

- "Should I itemize or take the standard deduction?"
- "How does self-employment tax work?"
- "What's the home office deduction?"
- "Am I eligible for the EITC?"
- "What are my state tax obligations?"
- "How do I report my 1099-NEC income?"
- "What's the difference between a 1099-NEC and 1099-MISC?"
- Any question requiring tax law knowledge not already in the user's facts

---

## 3. Coverage Audit — Tax Topics Checklist

### 3.1 Document Extraction Coverage (extraction.ts)

Only **3 document types** are supported for extraction:

| Document Type | Supported? | Notes |
|---|---|---|
| W-2 (2025) | ✅ | Full extraction: wages, federal withholding, employer info |
| 1099-INT (2025) | ✅ | Interest income extraction |
| 1099-DIV (2025) | ✅ | Ordinary + qualified dividends extraction |
| 1099-NEC | ❌ | Classified as `unknown_tax_document` |
| 1099-MISC | ❌ | Classified as `unknown_tax_document` |
| 1099-B | ❌ | No brokerage proceeds support |
| 1099-S | ❌ | No real estate sale support |
| 1098 | ❌ | No mortgage interest extraction |
| 1098-T | ❌ | No education expense extraction |
| 1099-G | ❌ | No unemployment/state refund support |
| 1099-R | ❌ | No retirement distribution support |
| 1099-SA | ❌ | No HSA distribution support |
| Schedule K-1 | ❌ | No partnership/S-corp support |
| Form 1095-A/B/C | ❌ | No health insurance extraction |

### 3.2 Tax Knowledge Coverage

| Topic | Covered? | Where | Depth |
|---|---|---|---|
| **Filing status rules** (Single, MFJ, MFS, HOH, QSS) | ⚠️ Partial | `tax-estimate.ts` has bracket tables for single/mfj/mfs/hoh; QSS not supported | Brackets only, no eligibility rules |
| **W-2 income reporting** (Form 1040 lines 1-5) | ✅ Extraction | W-2 extraction covers wages + withholding. No 1040 line mapping | Fact-level only |
| **1099-NEC/MISC** (contractor income) | ❌ | Not a supported doc type; routed to `unknown_tax_document` | Zero |
| **Schedule C** (self-employment profit/loss) | ❌ | `profiles.ts` has "freelancer" expected items but no Schedule C logic | Expected items only: "self-employment income", "business expenses", "estimated tax payments" |
| **Schedule E** (rental/royalty income) | ❌ | Not modeled at all | Zero |
| **Schedule D + Form 8949** (capital gains) | ❌ | `profiles.ts` mentions "capital gains activity" as investor expected item | Expected item only, no extraction |
| **Standard vs itemized deductions** (Schedule A) | ⚠️ Partial | `tax-estimate.ts` applies standard deduction only. `EXCLUDED_ITEMS` explicitly lists "itemized deductions" | Standard deduction amounts hardcoded for TY2024/2025 |
| **Common credits** (EITC, CTC, education, energy) | ❌ | `EXCLUDED_ITEMS`: "credits" listed as excluded | Zero |
| **Self-employment tax** (Schedule SE) | ❌ | `EXCLUDED_ITEMS`: "self-employment tax" explicitly excluded | Zero |
| **Estimated tax payments** | ⚠️ Partial | `PAYMENT_KEYS` in tax-estimate.ts includes estimated_tax_payments. Profiles.ts lists it as freelancer expected item | Key recognized but no quarterly logic |
| **State tax rules** | ❌ | `jurisdiction` defaults to `US-FED`. `EXCLUDED_ITEMS`: "State tax" explicitly excluded. Migration comment: "P2 expands beyond federal" | Zero |
| **Dependent qualification rules** | ❌ | Schema has `member_role` enum with 'dependent' but no qualification logic | Schema stub only |
| **Retirement contributions** (IRA, 401k) | ❌ | Not modeled | Zero |
| **Health insurance** (ACA, HSA) | ❌ | Not modeled | Zero |
| **Home office deduction** | ❌ | Not modeled | Zero |
| **Business expense categories** | ❌ | `profiles.ts` has single "business_expenses" expected item for freelancer profile | Expected item label only |

### 3.3 Tax Estimate Module Coverage (tax-estimate.ts)

The `computeFederalTaxEstimate` function is a **simple bracket calculator**:

**Included:**
- Federal ordinary income tax rates for TY2024 and TY2025
- Standard deduction for 4 filing statuses
- Income from: wages, interest, ordinary dividends (via key matching)
- Payments from: federal withholding, estimated tax payments
- Refund/amount_due direction

**Explicitly excluded** (from the code's own `EXCLUDED_ITEMS` array):
> "State tax, itemized deductions, dependents, credits, AMT, self-employment tax,
> capital gains rates, NIIT, penalties, and filing advice are excluded."

**Additional limitations:**
- Qualified dividends NOT given preferential rates
- No above-the-line deductions (student loan interest, HSA, etc.)
- No phase-outs or income limitations
- No tax credit computation
- Only 2 tax years supported (2024, 2025)

### 3.4 User's Tax Situation vs System Coverage

| User's situation | Covered? | Notes |
|---|---|---|
| W-2 employment income | ✅ | W-2 extraction works. Tax estimate handles wages |
| 1099-NEC contractor income | ❌ | Doc type not supported. Routed to unknown |
| Self-employment (Schedule C) | ❌ | Freelancer profile has expected items but no extraction or computation |
| Real estate income (Schedule E) | ❌ | Not modeled at all |
| 1 state | ❌ | Federal-only. State explicitly excluded |

**Bottom line:** TaxAhead currently covers approximately **1 of 5** aspects of this user's tax situation (W-2 only).

---

## 4. Gap Analysis — What a Real Tax Preparer Needs

### 4.1 Critical Gaps (block any real filing)

1. **No tax knowledge base.** The system has zero external tax knowledge — no IRS
   publications, no form instructions, no tax code references, no state rules. It
   can only echo back what was extracted from uploaded documents.

2. **Only 3 document types supported.** W-2, 1099-INT, 1099-DIV. A real filer with
   the user's situation needs at minimum: 1099-NEC, 1099-MISC, Schedule K-1 (if
   applicable), and expense tracking for Schedule C.

3. **No Schedule C logic.** Self-employment requires: gross income, business expense
   categorization (18+ IRS categories), home office calculation (simplified vs
   regular), vehicle expense (standard mileage vs actual), depreciation, and SE tax.

4. **No Schedule E logic.** Rental income requires: property-level income/expense
   tracking, depreciation (MACRS), passive activity loss rules, at-risk rules,
   and material participation tests.

5. **No state tax support.** 41 states + DC have income tax. Each has different
   brackets, deductions, credits, and conformity to federal rules.

6. **No self-employment tax computation.** SE tax is 15.3% on net SE income
   (12.4% SS + 2.9% Medicare), with a deduction for half of SE tax. This is a
   major liability component that the system ignores.

7. **No credit computation.** EITC, CTC/ACTC, education credits (AOTC/LLC),
   Saver's Credit, energy credits — all require complex eligibility and phase-out
   logic.

### 4.2 Architecture Gaps (for a knowledge-grounded system)

8. **No vector store / retrieval infrastructure.** When a tax knowledge base is
   added, the system will need: embeddings, a vector DB (pgvector or external),
   chunking strategy, relevance scoring, and retrieval-then-grounding pipeline.

9. **No multi-turn conversation memory.** The system is stateless single-turn.
   Tax Q&A often requires follow-up clarification ("What counts as a business
   expense?" → "What about my home office?" → "How do I calculate that?").

10. **No proactive tax guidance.** The system answers questions about existing data
    but never proactively suggests actions ("You have contractor income but no
    estimated tax payments recorded — you may owe penalties").

11. **No form mapping.** Extracted facts are stored in a generic key-value schema
    but never mapped to specific 1040 line numbers, schedule lines, or form fields.

12. **No multi-year support beyond 2024-2025.** Tax brackets, standard deductions,
    and credit amounts change annually. The constants are hardcoded.

### 4.3 Compliance / Trust Gaps

13. **No IRS Circular 230 disclaimer.** Tax advice in the US is regulated. The
    system doesn't surface required disclaimers about the limitations of AI-
    generated tax information.

14. **No "not a tax advisor" boundary enforcement.** The system prompt tells Claude
    not to compute dollar figures, but there's no structural enforcement preventing
    Claude from giving interpretive tax advice ("You should probably...").

15. **No audit trail for AI reasoning.** The proof metadata captures run_id,
    grounding_status, and context_hash, but not the model's internal reasoning
    chain (thinking/chain-of-thought).

---

## 5. Architecture Quality Assessment

### 5.1 What's Good (and Worth Preserving)

| Strength | Detail |
|---|---|
| **Citation integrity** | The 3-layer grounding (prompt + tool + server validation) is production-quality. Bidirectional marker↔ID checking catches both hallucinated citations and dropped citations. Every uncited sentence fails the answer. |
| **Fail-closed design** | 11 test cases verify that errors, missing data, invalid citations, and edge cases all result in no answer rather than a wrong answer. This is the right default for tax. |
| **Provenance chain** | fact → fact_evidence → evidence → document → source. Every fact traces back to the original document bytes with confidence scores at each step. |
| **RLS ownership boundary** | Every query runs under the caller's JWT. The filing_unit ownership check at the top prevents cross-tenant data access. Every citation lineage row is checked for filing_unit_id match. |
| **Dollar figure prohibition** | System prompt explicitly forbids computing or stating dollar figures not in the context. This prevents the most dangerous hallucination class in tax software. |
| **Audit hash** | SHA-256 of the full context sent to the model, persisted in the proof metadata. Enables post-hoc verification that the answer was based on specific data. |
| **Tracing integration** | Every invocation creates a run via `startRun`, with proper `finish('failed')` on every error path and `finish('succeeded')` on success. |

### 5.2 What Needs to Change (for general tax filing)

| Gap | Current State | What's Needed |
|---|---|---|
| **Knowledge retrieval** | None — facts only | Vector store + tax knowledge corpus (IRS pubs, form instructions, state rules) |
| **Retrieval relevance** | ALL facts sent (no filtering) | Semantic search over both user facts AND tax knowledge, with relevance ranking |
| **Context window management** | Simple string concatenation | Chunking strategy for large fact sets + knowledge passages, with token budget management |
| **Multi-turn memory** | None (stateless) | Conversation history store + context windowing for follow-up questions |
| **Proactive guidance** | None | Event-driven insight generation when new data arrives or deadlines approach |
| **Form mapping** | None | Fact-to-form-line mapping layer (fact key → 1040/Schedule line number) |
| **Multi-state** | Federal only | State tax rule engine with state-specific brackets, deductions, credits |

### 5.3 The Core Architectural Insight

The system's current architecture is best understood as a **"mirror" not a "brain"**:
it reflects the user's own data back to them through Claude, with strict citation
grounding. It does NOT reason about tax law, suggest strategies, or compute tax
liability. The comment at the top of `ask-taxahead/index.ts` is explicit:

> "refund/liability estimation is the Tax Compliance Engine's job (P2, external),
> not this endpoint's"

This is a **deliberate architectural boundary** — TaxAhead's intelligence layer
discovers and organizes tax data, but the actual tax computation and legal advice
are deferred to a future "Tax Compliance Engine" (labeled P2 in the roadmap).

---

## 6. Prioritized Recommendations

### P0 — Unlocks the User's Own Tax Situation

1. **Add 1099-NEC extraction.** The extraction tool schema needs a `1099_nec_2025`
   doc_type with fields: payer_name, recipient_name, tax_year, box_1_nonemployee_compensation.
   This is a ~2-hour change to `extraction.ts` and the extraction prompt.

2. **Add Schedule C expected items.** Expand the freelancer profile with: gross_receipts,
   cost_of_goods_sold, advertising, car_and_truck, commissions, contract_labor,
   insurance, legal, office, rent, repairs, supplies, taxes_licenses, travel,
   utilities, other_expenses.

3. **Add SE tax computation to tax-estimate.ts.** 15.3% on net SE earnings (with the
   half-SE-tax deduction). This is ~50 lines of code.

4. **Add Schedule E expected items.** Create a "landlord" profile with: rental_income,
   mortgage_interest, property_tax, insurance, repairs, depreciation, other_expenses.

### P1 — Knowledge Foundation

5. **Build a tax knowledge corpus.** Start with the most-referenced IRS publications:
   - Pub 17 (Your Federal Income Tax) — the master reference
   - Pub 334 (Tax Guide for Small Business) — Schedule C
   - Pub 527 (Residential Rental Property) — Schedule E
   - Pub 583 (Starting a Business and Keeping Records)
   - Form instructions for 1040, Schedule A, B, C, D, E, SE

6. **Set up pgvector.** Add the Supabase vector extension, create an embeddings
   table, and build a chunking + embedding pipeline for the tax corpus.

7. **Add hybrid retrieval to ask-taxahead.** Combine the current structured-fact
   retrieval with vector similarity search over the knowledge corpus. The context
   sent to Claude should include BOTH the user's facts AND relevant tax knowledge
   passages, with distinct citation namespaces (e.g., [C1] for user facts, [K1]
   for knowledge).

### P2 — Filing Capability

8. **Add form mapping layer.** Map each fact key to its 1040/Schedule line number.
   This enables the system to say "Your W-2 wages of $X go on Form 1040 line 1a."

9. **Add multi-state support.** Start with the user's state. Build a state constants
   registry similar to the federal one in tax-estimate.ts.

10. **Add multi-turn conversation memory.** Store conversation history per filing
    unit, retrieve recent turns as additional context for follow-up questions.

### P3 — Intelligence Layer

11. **Proactive tax guidance engine.** Generate insights when: a new document is
    classified (new tax implications), a deadline approaches (estimated payments),
    or a gap is detected (missing expected items for an active profile).

12. **Scenario modeling.** "What if I contribute $6,000 to a traditional IRA?"
    requires re-running the tax estimate with modified inputs.

13. **IRS Circular 230 disclaimer layer.** Surface required disclaimers on any
    response that could be construed as tax advice.

---

## 7. Answer to the User's Two Questions

### Q1: Is the knowledge base comprehensive enough to support actual tax filing for ANYONE?

**No.** There is no knowledge base. The system is a data-mirror, not a tax advisor.
It can:
- Extract data from 3 document types (W-2, 1099-INT, 1099-DIV)
- Compute a rough federal tax estimate (standard deduction + ordinary brackets only)
- Report back discovered facts with citations

It cannot:
- Answer "how should I report this?" questions
- Compute self-employment tax, state tax, credits, or itemized deductions
- Handle 1099-NEC, Schedule C, Schedule E, or any of the user's non-W-2 income
- Provide any tax planning or optimization advice

For the user's specific situation (W-2 + 1099 contractor + Schedule C + Schedule E + 1 state),
the system covers approximately **20%** — the W-2 portion only.

### Q2: How good is the RAG architecture for this purpose?

**The architecture is excellent for what it does, but what it does is much narrower
than RAG.** Specifically:

- The grounding/citation/validation pipeline is **production-quality** and should be
  preserved as-is when a knowledge layer is added
- The fail-closed design is **the right default for tax software** — it's better to
  say "I don't have enough information" than to give wrong tax advice
- The provenance chain (fact→evidence→document→source) is **auditable and traceable**
- But there is **no retrieval over external knowledge**, no vector search, no chunking,
  and no embedding — so calling it "RAG" would be a misnomer

When a knowledge layer is added, the current architecture provides a strong foundation:
the citation validation framework can be extended to cover knowledge citations alongside
fact citations, and the fail-closed approach ensures that hallucinated tax advice never
reaches the user.

---

*Research saved to `<HOME>/Claude/loop/research/taxahead_rag_audit_2026-07-20.md`*
