# TaxAhead Knowledge Base & RAG Pipeline — Factual Audit

**Date:** 2026-07-20
**Project root:** `<HOME>/Claude/Projects/taxahead`
**Auditor:** Mode D Researcher (leaf worker, no sub-delegation)

---

## 1. KB Content Inventory

### Source Documents: 30 .docx files across 5 layer directories

Source root: `Tax Knowledge Base  2/` (note: double-space in directory name, hardcoded at `scripts/ingest-knowledge-base.ts:26`)

| Layer Directory | Layer Enum | File Count | Documents |
|---|---|---|---|
| **Foundation/** | `foundation` | 3 | Knowledge Base Architecture, Tax Concepts & Glossary, Tax Entity Library |
| **Federal & State Tax Knowledge /** | `federal_state` | 14 | Annual Tax Reference Framework, Business/Investment/Entity Knowledge, Credit Knowledge, Deduction Knowledge, Federal Tax Intelligence, Filing Requirements & Compliance Knowledge, Filing Status & Filing Unit Knowledge, Income Knowledge, IRS Forms Library, Multi-State Tax Intelligence & Interstate AI Reasoning, State Tax Knowledge & Multi-State Intelligence (Part 1), State Tax Knowledge & Multi-State Intelligence (Part 2), Tax Calendar & Time-Based Rules Knowledge, Tax Intelligence Architecture |
| **Intelligence Layer/** | `intelligence` | 6 | Confidence & Validation Knowledge, Document Classification Knowledge, Evidence & Verification Knowledge, Financial Institution & Account Intelligence, Relationship Knowledge, TaxAhead Learning System |
| **Applied Intelligence/** | `applied` | 3 | IRS Authority & References, Life Event Knowledge (Part 1), Life Event Knowledge (Part 2) |
| **Engineering Guidelines /** | `engineering` | 4 | Annual Tax Reference Center Implementation Guide, Engineering Principles, Knowledge Base Architecture Brief, Source Monitoring & Data Ingestion Guide |

**Total: 30 source documents.**

### What is NOT ingested
- No PDF, Markdown, HTML, or plain-text sources — `.docx` only (`ingest-knowledge-base.ts:362`)
- No IRS publications directly (Pub 501, 502, 503, 527, 535, 587, 596, 970, etc. referenced in gold questions but not present as standalone sources)
- No state-specific tax forms, instructions, or statutory text
- No annual update manifests, changelog, or version tracking files

---

## 2. Schema & Metadata Map

### Table: `kb_documents` (migration `0018_rag_knowledge_base.sql:20-30`)

| Column | Type | Constraints | Populated? |
|---|---|---|---|
| `id` | `uuid` | PK, default `gen_random_uuid()` | ✅ auto |
| `source_file` | `text` | NOT NULL | ✅ e.g. `"Federal & State Tax Knowledge /Income Knowledge.docx"` |
| `layer` | `text` | NOT NULL, CHECK IN (foundation, federal_state, intelligence, applied, engineering) | ✅ from directory mapping |
| `title` | `text` | NOT NULL | ✅ basename without `.docx` |
| `content` | `text` | NOT NULL | ✅ chunk text |
| `chunk_index` | `int` | NOT NULL | ✅ sequential per file |
| `embedding` | `vector(1536)` | nullable | ✅ from text-embedding-3-small |
| `metadata` | `jsonb` | default `'{}'` | ❌ **Always empty `{}`** (see `ingest-knowledge-base.ts:309`) |
| `created_at` | `timestamptz` | default `now()` | ✅ auto |

**Unique constraint:** `(source_file, chunk_index)` — prevents duplicates on re-ingestion.

### What metadata is TRACKED
- Source file path (directory + filename)
- Layer classification (5-value enum)
- Chunk ordering within a document

### What metadata is MISSING
- **Jurisdiction** — no column, no metadata field, no extraction logic
- **Tax year / effective date** — no temporal metadata at all
- **Source version / amendment tracking** — none
- **Author / publisher / authority reference** — none
- **Confidence / review status** — none
- **Document type classification** (beyond layer) — none
- **IRC section / regulation reference** — none
- **Superseded-by / deprecation markers** — none

### Indexes

| Index | Type | Purpose |
|---|---|---|
| `kb_documents_source_chunk` | UNIQUE btree | Dedup on (source_file, chunk_index) |
| `kb_documents_embedding_idx` | IVFFlat (lists=100) | Vector cosine similarity search |
| `kb_documents_content_fts_idx` | GIN on `to_tsvector('english', content)` | Full-text search |
| `kb_documents_layer_idx` | btree on `layer` | Layer-filtered queries |

**No jurisdiction index** (column doesn't exist).
**No temporal index** (no temporal column exists).

---

## 3. Retrieval Pipeline

### End-to-End Flow

```
User Question
    │
    ▼
[ask-taxahead/index.ts]
    │
    ├── 1. Fetch filing_unit (tax_year, filing_status)
    ├── 2. Fetch scores (readiness, filing_confidence, discovery_confidence)
    ├── 3. Fetch facts with full citation lineage (C1, C2, ...)
    ├── 4. Fetch expected_items (missing items)
    │
    ▼
[searchKB() — ask-taxahead/index.ts:348-380]
    │
    ├── Embed query via text-embedding-3-small (kb-embeddings.ts)
    ├── Call search_knowledge_base() RPC with 4 params:
    │     query_embedding, query_text, match_count=3, layer_filter=null
    │     ⚠️ NO jurisdiction_filter passed
    │     ⚠️ NO state context passed
    ├── Format results as KB context with [K1], [K2], [K3] markers
    │
    ▼
[Compose context block]
    │  Tax year + filing status header
    │  Readiness scores
    │  Discovered facts [C*]
    │  Tax knowledge [K*]
    │  Missing items
    │
    ▼
[Claude API call — claude-sonnet-5]
    │  System prompt enforces grounded-only answers
    │  Tool: answer_from_evidence (status, answer, citation_ids, knowledge_citation_ids)
    │
    ▼
[Validate answer]
    ├── Bidirectional [C*] marker ↔ citation_id consistency
    ├── Bidirectional [K*] marker ↔ kb_citation_id consistency
    ├── Every sentence must have at least one valid citation
    ├── Circular 230: detectUncitedRecommendations() checks interpretive claims
    │
    ▼
[Response to caller]
    answer + citations + kb_citations + disclaimer + proof metadata
```

### Standalone search-knowledge endpoint (search-knowledge/index.ts)

```
POST { query, layer?, top_k?, state? }
    │
    ├── 1. Embed query
    ├── 2. Build jurisdiction_filter from state param:
    │     state="GA" → ["US-FED", "US-GA"]
    │     null state → no filter (return all)
    ├── 3. Call search_knowledge_base() RPC with 5 params:
    │     query_embedding, query_text, match_count, layer_filter, jurisdiction_filter
    │     ⚠️ CRITICAL: jurisdiction_filter is NOT a parameter of the SQL function
    ├── 4. Re-rank via Cohere Rerank (or keyword-overlap fallback)
    ├── 5. Assign citation keys K1..Kn
    ├── 6. Derive jurisdiction per result via deriveJurisdiction()
    │
    ▼
Response: { results, query, result_count, state_filter }
```

### Re-ranking layer (kb-reranker.ts)

- **Primary:** Cohere Rerank API (`rerank-english-v3.0`), requires `COHERE_API_KEY`
- **Fallback:** Keyword-overlap scoring (Jaccard-like with stopword removal, blended 70% keyword / 30% original combined_score)
- Candidate expansion: retrieves `min(topK × 3, 50)` candidates before re-ranking

### Jurisdiction derivation (search-knowledge/index.ts:306-342)

`deriveJurisdiction()` attempts to infer jurisdiction from:
1. `metadata.jurisdiction` — **always empty `{}`** (ingestion never populates it)
2. Source file path pattern matching (50 state name → US-XX mappings) — **KB filenames don't contain state names** (e.g., "State Tax Knowledge & Multi-State Intelligence (Part 1).docx" would NOT match any state; "Multi-State Tax Intelligence..." also won't match)
3. Default: `"US-FED"` — **everything falls through to this**

---

## 4. Computation Engine Status

### Federal Tax Estimate (`_shared/tax-estimate.ts`)

**Jurisdiction:** Hardcoded `"US-FED"` only. Returns `status: "unsupported"` for any non-federal jurisdiction (line 369).

**Tax years covered:** 2024 and 2025 only (lines 187-190). Any other year → `unsupported`.

**Filing statuses:** single, mfj, mfs, hoh (lines 288-295).

**What it computes:**

| Calculation | Implementation | Notes |
|---|---|---|
| Gross income | Sum of discovered income facts (24 key patterns) | W-2, 1099-INT/DIV/NEC/MISC/K |
| Self-employment tax (SECA) | `net_profit × 0.9235 × 15.3%` | Simplified — ignores SS wage base interaction with W-2 |
| QBI deduction (Section 199A) | `20% × self_employment_income` | Simplified — no W-2 wage or capital limitations |
| Standard deduction | Filing-status lookup from hardcoded tables | TY2024 + TY2025 from IRS Rev. Proc. |
| Federal income tax | Ordinary rate brackets only | No preferential rates for qualified dividends |
| Rental income (Schedule E) | Gross − expenses − depreciation | Passive loss limited by §469(i) $25K allowance |
| Passive loss phaseout | $100K-$150K MAGI phaseout | Active-participant only |
| Refund/amount due | Payments − total tax | |

**What it explicitly EXCLUDES (lines 79-85):**
- State tax
- Itemized deductions
- Dependents
- Credits (all)
- AMT
- Capital gains rates
- NIIT (3.8%)
- Penalties
- Filing advice
- SS wage base ceiling for SECA
- Additional Medicare Tax
- Real-estate-professional status
- At-risk limitations
- Suspended-loss carryforwards

**State tax handling:** **None.** There is zero state tax computation anywhere in the codebase. The only reference to `state_tax` as a fact category appears in a test fixture (`tax-estimate.test.ts:70`) where it's used as a non-matching fact (correctly ignored by the federal-only engine).

### Hardcoded Constants

| Constant | Value | Location |
|---|---|---|
| SE net earnings ratio | 92.35% | line 343 |
| SE Social Security rate | 12.4% | line 344 |
| SE Medicare rate | 2.9% | line 345 |
| SE deductible half | 50% | line 347 |
| QBI rate | 20% | line 350 |
| Passive loss max allowance | $25,000 | line 355 |
| Passive loss phaseout start | $100,000 | line 356 |
| Passive loss phaseout end | $150,000 | line 357 |

### Tax Package Assembly (`get-tax-package/index.ts`)

- Queries `filing_units` for `jurisdiction` field (line 218) — but jurisdiction is always `'US-FED'` (default in `0001_init.sql:28`)
- Passes `fu.jurisdiction` to `computeFederalTaxEstimate()` (line 401) — always `"US-FED"`, so this always succeeds
- `potential_deductions_total` is a **sum of discovered deduction/credit facts** — explicitly labeled "Not a tax calculation or refund estimate" (line 377-378)
- Assembles business_activities (Schedule C) and rental_properties + depreciation_assets (Schedule E)
- No "Column Tax" references found anywhere in the codebase

---

## 5. Evaluation Coverage

### Gold Question Set: 60 questions

**File:** `tests/rag-evaluation/gold-questions.json`

**Difficulty distribution:**
| Difficulty | Count |
|---|---|
| Basic | 23 |
| Intermediate | 26 |
| Advanced | 11 |

**Tax year coverage:**
- 7 questions explicitly mention "2025" (standard deduction ×3, SE tax rate, tax brackets, gift tax exclusion, bonus depreciation)
- 53 questions are year-agnostic (general tax law questions)
- 0 questions for 2024 or any other year

**Jurisdiction coverage:**
| Jurisdiction | Count | Questions |
|---|---|---|
| US-FED (federal only) | 54 | All standard tax topics |
| CA (California) | 1 | "Does California have a state income tax?" |
| TX (Texas) | 1 | "Does Texas have a state income tax?" |
| GA (Georgia) | 1 | "Does Georgia have a state income tax?" |
| Multi-state | 1 | "I moved to a different state during the year. How do I file?" |
| SALT (federal+state interaction) | 2 | "What is the SALT deduction cap?", "Can I deduct state income taxes on my federal return?" |

**Topic categories (derived from expected_topics analysis):**

| Category | Count | Examples |
|---|---|---|
| Filing basics (status, deadline, thresholds) | 7 | Filing deadline, standard deduction, filing requirements |
| Income reporting | 5 | W-2, 1099-NEC, side gig, crypto, gambling |
| Self-employment / business | 7 | SE tax, QBI, Schedule C, bonus depreciation, business expenses |
| Credits | 6 | EITC, CTC, AOTC, LLC, CDCC, Saver's Credit |
| Deductions | 7 | Home office, medical, charitable, student loan, SALT, above/below the line |
| Retirement / investment | 6 | IRA, 401(k), stock options, wash sale, capital gains, HSA |
| Rental / real estate | 4 | Rental income, expenses, depreciation, room rental |
| Life events | 4 | Marriage, divorce, baby, inheritance |
| Compliance / penalties | 4 | Late filing, IRS notices, estimated payments, ITIN |
| State tax | 4 | CA, TX, GA, multi-state |
| Advanced / niche | 6 | AMT, NIIT, FEIE, kiddie tax, gift tax, foreign earned income |

**Evaluation infrastructure:** Only the gold-questions.json file exists. No evaluation runner script, no scoring harness, no baseline results file found in `tests/rag-evaluation/`.

---

## 6. Gap Matrix

### State × Year × Topic × Source Type

```
                    TY2024    TY2025    TY2026
US-FED (Federal)
  Income             ⚠️        ⚠️        ❌
  Deductions         ⚠️        ⚠️        ❌
  Credits            ⚠️        ⚠️        ❌
  Filing             ⚠️        ⚠️        ❌
  Business/SE        ⚠️        ⚠️        ❌
  Rental             ⚠️        ⚠️        ❌
  Retirement         ⚠️        ⚠️        ❌
  Compliance         ⚠️        ⚠️        ❌
  Computation        ✅        ✅        ❌
  
US-CA (California)
  All topics         ❌        ❌        ❌
  
US-GA (Georgia)
  All topics         ❌        ❌        ❌
  
US-TX (Texas)
  All topics         ❌        ❌        ❌
  
US-{other 47 states}
  All topics         ❌        ❌        ❌
```

**Legend:**
- ✅ = implemented with hardcoded constants (federal tax computation only)
- ⚠️ = KB documents exist but: no metadata for year/jurisdiction; no evaluation coverage; ingestion writes empty metadata
- ❌ = no documents, no computation, no evaluation

### Pipeline Coverage

| Capability | Status | Evidence |
|---|---|---|
| Federal KB ingestion | ⚠️ Partial | 30 docs ingested, metadata always `{}` |
| Federal tax computation | ✅ TY2024-2025 | tax-estimate.ts |
| State KB ingestion | ❌ | No state-specific docs; 3 state docs in federal_state layer lack jurisdiction tagging |
| State tax computation | ❌ | Zero implementation; explicitly excluded |
| Jurisdiction filtering at search | ❌ | SQL function doesn't accept jurisdiction_filter param |
| Year-aware retrieval | ❌ | No year column, no year metadata, no year filter |
| Source versioning | ❌ | No version/amendment tracking |
| Evaluation runner | ❌ | Gold questions exist but no runner script |
| Multi-turn conversation | ❌ | Stateless, single-turn by design |

---

## 7. Concrete Findings

### CRITICAL — Runtime Errors & Schema Gaps

1. **`jurisdiction_filter` parameter is passed to a SQL function that doesn't accept it.**
   - `search-knowledge/index.ts:152` passes `jurisdiction_filter: jurisdictionFilter` as a 5th parameter to `search_knowledge_base()`
   - The SQL function (`0018_rag_knowledge_base.sql:61-66`) only accepts 4 parameters: `query_embedding, query_text, match_count, layer_filter`
   - Postgres silently ignores extra named parameters to RPC calls via PostgREST, so the jurisdiction filter is **silently dropped** — all searches return results from all jurisdictions regardless of the `state` parameter
   - **Impact:** The `state` parameter on the search-knowledge endpoint is non-functional. A user searching with `state=GA` gets the same results as a user searching with no state filter.

2. **`kb_documents.metadata` is always empty `{}` — the jurisdiction derivation pipeline is dead code.**
   - `ingest-knowledge-base.ts:309` hardcodes `metadata: {}`
   - `deriveJurisdiction()` in `search-knowledge/index.ts:306-342` first checks `metadata.jurisdiction` (always absent), then checks filename patterns (no KB filenames contain state names), then defaults to `"US-FED"`
   - **Impact:** Every KB chunk is tagged `"US-FED"` regardless of its actual content. The 3 state tax documents ("State Tax Knowledge & Multi-State Intelligence Parts 1 & 2", "Multi-State Tax Intelligence & Interstate AI Reasoning") are all tagged US-FED.

3. **`ask-taxahead` does not pass jurisdiction or state context to KB search.**
   - `ask-taxahead/index.ts:348-361` (`searchKB()`) calls `search_knowledge_base` with only 4 params — no `jurisdiction_filter`, no state
   - The filing unit's `jurisdiction` field is queried but only used for the tax estimate, never for KB search
   - The filing unit's state (if any) is never queried or passed
   - **Impact:** Even if the SQL function supported jurisdiction filtering, ask-taxahead wouldn't use it.

### HIGH — Missing Capabilities

4. **Zero state tax computation exists anywhere in the codebase.**
   - `tax-estimate.ts` returns `status: "unsupported"` for any jurisdiction other than `"US-FED"` (line 369)
   - The `filing_units.jurisdiction` column defaults to `'US-FED'` (`0001_init.sql:28`) with comment "P2 expands beyond federal"
   - No state brackets, rates, credits, or rules are implemented
   - **Impact:** Any state-specific tax question can only be answered from KB content (which lacks jurisdiction tagging).

5. **No temporal/year metadata in KB — year-aware retrieval is impossible.**
   - No `tax_year`, `effective_date`, or `superseded_at` columns exist in `kb_documents`
   - The ingestion script extracts no temporal information from documents
   - Gold evaluation questions reference 2025, but the KB has no way to distinguish 2024 vs 2025 content
   - **Impact:** A question about "2024 standard deduction" would retrieve the same chunks as "2025 standard deduction," even though values differ.

6. **No evaluation runner exists for the 60 gold questions.**
   - `tests/rag-evaluation/` contains only `gold-questions.json`
   - No test script, no scoring harness, no baseline results
   - Gold questions have `expected_topics` (keyword lists) and `authority_refs` but no ground-truth answers
   - **Impact:** There is no way to measure RAG retrieval quality, answer accuracy, or regression detection.

### MEDIUM — Structural Gaps

7. **KB source corpus is 30 .docx files with no update/versioning mechanism.**
   - No manifest file listing expected documents
   - No hash or checksum tracking for content changes
   - No re-ingestion diffing (upsert on `(source_file, chunk_index)` replaces chunks but doesn't detect removed documents)
   - **Impact:** When tax law changes (e.g., OBBBA provisions), there's no systematic way to identify stale content.

8. **Gold evaluation set has only 6 state-related questions (10% of corpus), covering only 3 states.**
   - California: 1 question (does it have income tax?)
   - Texas: 1 question (does it have income tax?)
   - Georgia: 1 question (does it have income tax?)
   - Multi-state: 1 question (part-year residency filing)
   - SALT: 2 questions (federal deduction cap, deducting state taxes on federal return)
   - All 3 state questions are trivially simple (yes/no + rate)
   - **Impact:** No evaluation coverage for complex state topics (credits, multi-state allocation, state-specific deductions).

9. **Only TY2025 is represented in year-specific gold questions.**
   - 7 of 60 questions mention "2025" explicitly
   - 0 questions for 2024 (despite the computation engine supporting it)
   - **Impact:** No way to evaluate whether the system handles prior-year questions correctly.

10. **`ask-taxahead` limits KB retrieval to top-3 results.**
    - `ask-taxahead/index.ts:517` calls `searchKB(..., 3)` with `topK=3`
    - The standalone search endpoint defaults to 10 and allows up to 50
    - Each KB chunk is truncated to 800 characters in the context (`ask-taxahead/index.ts:538`)
    - **Impact:** Complex questions may need more context; 3 × 800 chars = 2,400 chars maximum KB context, which may be insufficient for multi-faceted tax questions.

11. **The `searchKB` call in `ask-taxahead` bypasses the re-ranking layer.**
    - `ask-taxahead/index.ts:348-380` calls the SQL RPC directly, then formats results
    - It does NOT use the Cohere reranker or keyword-overlap fallback
    - The standalone `search-knowledge/index.ts` endpoint DOES use re-ranking
    - **Impact:** The chat endpoint (which users actually interact with) gets lower-quality retrieval than the standalone search API.

### LOW — Observations

12. **Chunking uses ~512 token target with 50-token overlap, paragraph-boundary-first.**
    - `ingest-knowledge-base.ts:34-36` and `kb-chunker.ts:14-16` both define identical constants (code duplication)
    - The ingestion script has its own copy of the chunker rather than importing the shared module
    - Minimum chunk: 100 chars; large paragraphs split at sentence boundaries

13. **Embedding model is `text-embedding-3-small` (1536 dimensions) — the lowest-cost OpenAI embedding model.**
    - No comparison data for `text-embedding-3-large` or domain-specific models
    - IVFFlat index with `lists=100` tuned for ~4K-8K chunks (comment in migration)

14. **No "Column Tax" references found anywhere in the codebase.**
    - `grep -ri "column.tax"` across all .ts, .tsx, .sql, .json files returned zero results

15. **The system prompt for `ask-taxahead` includes Circular 230 compliance enforcement.**
    - `INTERPRETIVE_PATTERNS` regex array (8 patterns, lines 164-173) detects recommendation-like language
    - `detectUncitedRecommendations()` flags sentences with interpretive patterns but no `[K*]` citation
    - `CIRCULAR_230_DISCLAIMER` appended to responses using KB content
    - This is a compliance wrapper, not a substitute for actual Circular 230 review

16. **LLM model for ask-taxahead is `claude-sonnet-5`** (configurable via `CHAT_MODEL` env var, line 571), called via direct Anthropic Messages API with forced tool use (`tool_choice: { type: "tool", name: "answer_from_evidence" }`).

---

## Appendix: File Reference Map

| Component | File Path | Key Lines |
|---|---|---|
| Ingestion script | `scripts/ingest-knowledge-base.ts` | Dir path: 26, Chunking: 34-36, Metadata: 309, Layer map: 75-89 |
| RAG migration | `supabase/migrations/0018_rag_knowledge_base.sql` | Table: 20-30, Search fn: 61-153, Indexes: 48-57 |
| Search endpoint | `supabase/functions/search-knowledge/index.ts` | Jurisdiction filter: 113-121, RPC call: 145-154, deriveJurisdiction: 306-342 |
| Chat endpoint | `supabase/functions/ask-taxahead/index.ts` | searchKB: 348-380, System prompt: 122-153, Circular 230: 164-196 |
| Tax estimate | `supabase/functions/_shared/tax-estimate.ts` | Years: 187-190, Brackets: 91-185, Exclusions: 79-85 |
| Tax package | `supabase/functions/get-tax-package/index.ts` | Jurisdiction query: 218, Estimate call: 399-406 |
| KB embeddings | `supabase/functions/_shared/kb-embeddings.ts` | Model: 13, Dims: 14 |
| KB reranker | `supabase/functions/_shared/kb-reranker.ts` | Cohere: 76-118, Fallback: 130-172 |
| KB chunker | `supabase/functions/_shared/kb-chunker.ts` | Constants: 14-16, Layer map: 138-153 |
| Gold questions | `tests/rag-evaluation/gold-questions.json` | 60 questions, 3 state-specific |
| Filing units table | `supabase/migrations/0001_init.sql` | Jurisdiction default: 28 |
