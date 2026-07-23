# TaxAhead RAG Architecture: Options & Recommendations

**Date:** 2026-07-20
**Mode:** D (Domain Research)
**Repo:** `~/Claude/Projects/taxahead`
**Companion audit:** `taxahead_rag_audit_2026-07-20.md`

---

## 1. Current State Summary

TaxAhead today has **no RAG system and no tax knowledge base in code**. The `ask-taxahead`
edge function is a grounded Q&A endpoint that:

- Queries the user's own structured tax facts from PostgreSQL (scores, facts, expected items)
- Sends those facts + the user's question to Claude with a strict "answer ONLY from context" prompt
- Validates every citation bidirectionally (markers ↔ known fact IDs)
- Returns fail-closed if any sentence lacks a citation or any citation is unknown

**What it CAN answer:** "What were my wages?", "What documents do you have?", "How ready am I?"
**What it CANNOT answer:** Any question requiring tax law knowledge — "Should I itemize?",
"How does self-employment tax work?", "Am I eligible for EITC?", state tax questions.

**Infrastructure:** Supabase (PostgreSQL + Edge Functions + Auth/RLS). No pgvector extension,
no embedding pipeline, no vector columns, no vector DB. The `[storage.vector]` section in
`config.toml` is commented out.

**Preserved strengths** (must carry forward into any RAG layer):
- 3-layer grounding: system prompt + forced tool output schema + server-side validation
- Bidirectional citation marker checking
- Fail-closed on any hallucination signal
- Full provenance chain: fact → evidence → document → source
- SHA-256 context hash for audit trail
- RLS ownership enforcement per filing unit

---

## 2. Tax Knowledge Base 2 — Contents Summary

### 2.1 Corpus Statistics

| Metric | Value |
|--------|-------|
| **Files** | 30 .docx documents |
| **Paragraphs** | 179,184 |
| **Characters** | 7,785,465 |
| **Estimated pages** | ~15,570 |
| **Estimated tokens** | ~1,946,366 |

This is a **massive, professionally structured tax knowledge corpus** — far beyond
a collection of IRS publications. It represents a complete tax ontology designed
for machine consumption by an AI reasoning system.

### 2.2 Architecture (4 Layers + Engineering Guidelines)

**Foundation** (3 docs, ~306 pages):
- Knowledge Base Architecture — defines the modular domain structure
- Tax Entity Library — standardized definitions for every entity (people, orgs, accounts, assets, documents, instruments)
- Tax Concepts & Glossary — authoritative definitions of all tax terminology

**Federal & State Tax Knowledge** (15 docs, ~8,248 pages):
- IRS Forms Library — comprehensive form definitions (878 pages)
- Income Knowledge — income recognition, classification, sourcing, characterization (399 pages)
- Deduction Knowledge — above/below-the-line, standard/itemized, limitations, substantiation (428 pages)
- Credit Knowledge — refundable/nonrefundable, eligibility, limitations (379 pages)
- Filing Status & Filing Unit Knowledge — status rules, dependency, filing unit composition (282 pages)
- Filing Requirements & Compliance — filing obligations, deadlines, extensions, post-filing (784 pages)
- Business, Investment & Entity Knowledge — sole prop through C-corp, trusts, estates (2,104 pages)
- Tax Calendar & Time-Based Rules — deadlines, estimated payments, seasonal rules (448 pages)
- Federal Tax Intelligence — federal reasoning framework (387 pages)
- State Tax Knowledge Parts 1 & 2 — all 50 states + DC, individual rules (3,085 pages)
- Multi-State Tax Intelligence — interstate reasoning, reciprocity, credits (297 pages)
- Tax Intelligence Architecture — the evidence→facts→rules→calculations→filing pipeline (220 pages)
- Annual Tax Reference Framework — versioned annual values (brackets, limits, thresholds) (176 pages)

**Intelligence Layer** (6 docs, ~1,947 pages):
- Document Classification Knowledge — how to identify, classify, route documents (177 pages)
- Evidence & Verification Knowledge — what constitutes sufficient evidence (426 pages)
- Confidence & Validation Knowledge — certainty measurement, conflict resolution (192 pages)
- Relationship Knowledge — entity relationships, ownership, authority (857 pages)
- Financial Institution & Account Intelligence — financial ecosystem mapping (96 pages)
- TaxAhead Learning System — verified learning principles (67 pages)

**Applied Intelligence** (3 docs, ~3,515 pages):
- Life Event Knowledge Parts 1 & 2 — life event detection, tax consequences, long-term reasoning (3,137 pages)
- IRS Authority & References — legal hierarchy, authority weighting, citation methodology (378 pages)

**Engineering Guidelines** (4 docs, ~52 pages):
- Knowledge Base Architecture Brief — layer separation philosophy
- Engineering Principles — maintainability, explainability, versioning
- Source Monitoring & Data Ingestion Guide — official source monitoring, validation lifecycle
- Annual Tax Reference Center Implementation Guide — admin dashboard for annual updates

### 2.3 Key Design Decisions Already Made in KB2

The KB2 documents are not just tax content — they include **detailed architectural
specifications** for how a RAG system should consume them:

1. **Permanent knowledge vs annual reference data** — reasoning stays in KB docs;
   annually changing values (brackets, limits, thresholds) go to a separate
   "Annual Tax Reference Center" with versioned datasets
2. **Single source of truth** — no concept defined in multiple domains; cross-references only
3. **Evidence-first reasoning** — tax conclusions only after sufficient verified evidence
4. **Confidence never confused with correctness** — every conclusion carries explicit confidence
5. **Authority hierarchy** — IRC > Treasury Regs > Revenue Rulings > IRS Pubs > IRS Notices
6. **Explainability as engineering requirement** — every conclusion traceable to specific KB docs + facts + evidence
7. **Version everything that affects tax outcomes** — KB docs, annual datasets, reasoning chains

### 2.4 Assessment

This is not a "dump of IRS publications." It is a **structured tax ontology** with:
- Clear domain boundaries and ownership
- Explicit non-responsibilities per domain
- Cross-domain dependency declarations
- Machine-consumable reasoning frameworks
- Evidence and confidence requirements per concept

The corpus is designed to be chunked, indexed, and retrieved — but the retrieval
system it was designed for **does not yet exist**.

---

## 3. RAG Architecture Options — State of the Art (2025-2026)

### 3.1 Vector Database Decision

| Option | Best For | Cost | TaxAhead Fit |
|--------|----------|------|--------------|
| **pgvector** (Supabase) | <1M vectors, already on Postgres | Included in Supabase plan | **Best fit** — TaxAhead already runs Supabase Postgres; zero additional infrastructure; RLS integrates naturally |
| **Pinecone** | 5M+ vectors, fully managed | $70-700/mo at scale | Overkill for initial corpus; adds a vendor dependency |
| **Weaviate** | Hybrid search native | Self-hosted free; cloud $25+/mo | Good hybrid search but adds operational complexity |
| **Qdrant** | Open-source, high perf | Self-hosted free | Fast but requires separate infrastructure management |

**Recommendation: pgvector (Supabase Vector)**

Rationale:
- TaxAhead already runs on Supabase Postgres — pgvector is a `CREATE EXTENSION` away
- The KB2 corpus is ~2M tokens. Even with aggressive chunking (500 tokens/chunk),
  that's ~4,000 chunks — well within pgvector's sweet spot
- RLS policies extend naturally to knowledge retrieval (no cross-tenant leakage)
- Supabase Vector includes hybrid search (semantic + keyword) out of the box
- No additional vendor, no data egress, no separate auth system
- Can upgrade to dedicated vector DB later if corpus grows to millions of chunks

### 3.2 Retrieval Architecture

#### Option A: Pure Semantic Search
- Embed query → find top-K similar chunks by cosine similarity
- **Pros:** Simple, handles paraphrase well
- **Cons:** Misses exact matches (form numbers, IRC sections, specific dollar amounts)
- **Tax risk:** A query about "Form 1040 Schedule C line 12" might not retrieve the
  correct chunk if the embedding doesn't capture the exact form reference

#### Option B: Hybrid Search (BM25 + Semantic) ⭐ RECOMMENDED
- BM25 keyword search + semantic similarity search → Reciprocal Rank Fusion (RRF)
- **Pros:** Catches both exact references AND conceptual queries
- **Cons:** Slightly more complex; needs re-ranking
- **Tax advantage:** Tax queries frequently reference specific form numbers, IRC sections,
  dollar thresholds, and filing deadlines — BM25 excels at these exact matches while
  semantic handles "how does self-employment tax work" conceptual queries
- **Research support:** Fine-Hybrid (BM25 + finetuned SBERT) specifically validated on
  tax compliance datasets; hybrid retrieval recommended as minimum viable baseline for
  regulated industries (Akarsu et al., 2026)
- **Caveat:** Section-level RAG study found BM25-only sometimes outperforms hybrid at
  fine granularity (0.53 MRR vs 0.36) — suggests re-ranking layer is essential

#### Option C: GraphRAG (Knowledge Graph + Vector)
- Build a knowledge graph of tax entities and relationships → augment retrieval with
  graph traversal → combine with vector similarity
- **Pros:** Best for cross-document reasoning, multi-hop queries, regulatory compliance;
  up to 86%+ accuracy on benchmarks (3x improvement over plain RAG)
- **Cons:** Significantly more complex to build and maintain; requires entity extraction
  and relationship mapping from the KB2 corpus
- **Tax advantage:** Tax reasoning is inherently relational — "Does the taxpayer's
  California rental income create a filing obligation in New York where they're
  domiciled?" requires traversing residency → income sourcing → interstate credit →
  filing requirement chains
- **KB2 fit:** The KB2 corpus is already structured as a domain ontology with explicit
  entity definitions, relationship declarations, and cross-domain dependencies —
  it's essentially a knowledge graph in prose form

**Recommendation: Phase 1 = Hybrid Search (Option B). Phase 3 = GraphRAG augmentation.**

### 3.3 Chunking Strategy

The KB2 corpus requires a **domain-aware hierarchical chunking** strategy, not
generic fixed-size splitting.

#### Recommended: Hierarchical + Structural Chunking

```
Level 0: Document (e.g., "Deduction Knowledge")
  Level 1: Major Section (e.g., "Itemized Deductions")
    Level 2: Subsection (e.g., "Medical Expense Deduction")
      Level 3: Concept Block (e.g., "AGI threshold for medical expenses")
```

**Chunk rules:**
1. **Respect document boundaries** — each KB2 document is a distinct knowledge domain;
   never merge chunks across domains
2. **Preserve parent context** — every chunk carries its document name + section
   hierarchy as metadata (enables filtered retrieval: "search only in Credit Knowledge")
3. **Concept-level granularity** — chunk at the concept boundary, not at fixed token counts;
   a concept like "Medical Expense Deduction" should be one chunk even if it's 800 tokens
4. **Annual reference separation** — annual values referenced within chunks should be
   resolved at query time from the Annual Tax Reference Center, not baked into chunks
5. **Cross-reference preservation** — when a chunk references another domain
   (e.g., Deduction Knowledge references Income Knowledge), preserve the reference
   as structured metadata, not inline text

**Chunk size targets:**
- Minimum: 200 tokens (below this, context is too thin for tax concepts)
- Target: 500-800 tokens per chunk
- Maximum: 1,200 tokens (above this, retrieval precision drops)
- Overlap: 50-100 tokens at concept boundaries (not fixed overlap)

**Estimated chunk count:** ~4,000-8,000 chunks for the full KB2 corpus

#### What NOT to Do
- **Don't** use fixed 512-token chunks with 50-token overlap — this splits tax concepts mid-sentence
- **Don't** chunk across document boundaries — "Income Knowledge" and "Deduction Knowledge"
  are separate domains for a reason
- **Don't** embed tables as flat text — IRS form line references, bracket tables, and
  phase-out schedules need structured representation
- **Don't** strip the document hierarchy — the KB2's structure IS the retrieval signal

### 3.4 Embedding Model Selection

| Model | Dimensions | Tax/Legal Fit | Cost |
|-------|-----------|---------------|------|
| **text-embedding-3-large** (OpenAI) | 3072 | General-purpose, high quality | $0.13/1M tokens |
| **text-embedding-3-small** (OpenAI) | 1536 | Good quality, lower cost | $0.02/1M tokens |
| **voyage-3-large** (Voyage AI) | 1024 | Specifically trained for legal/finance | $0.18/1M tokens |
| **jina-embeddings-v3** (Jina) | 1024 | Multi-domain, strong on structured text | $0.02/1M tokens |
| **nomic-embed-text** (Nomic) | 768 | Open-source, good for domain fine-tuning | Free (self-hosted) |

**Recommendation: text-embedding-3-small for Phase 1, upgrade to voyage-3-large for Phase 2+**

Rationale:
- At ~2M tokens, initial embedding cost is ~$0.04 with text-embedding-3-small
- Re-embedding on updates is cheap enough to do on every KB change
- Voyage-3-large is worth evaluating when accuracy benchmarks are established,
  as it's specifically optimized for legal/financial text
- Supabase supports OpenAI embeddings natively through `supabase.ai` integration

### 3.5 Re-Ranking Layer

After initial retrieval (top-20 candidates from hybrid search), apply a re-ranking
model to select the final top-5 for context assembly.

**Options:**
- **Cohere Rerank** — purpose-built re-ranking API, strong on domain text
- **Cross-encoder model** (self-hosted) — ms-marco-MiniLM or similar
- **Claude-as-re_ranker** — use a fast Claude call to score relevance of each chunk
  to the query (expensive but highest quality)

**Recommendation: Cohere Rerank for production; Claude-as-reranker for evaluation baseline**

---

## 4. Compliance Requirements

### 4.1 IRS Circular 230 — AI Tax Practice (Alert 2026-19)

The IRS Office of Professional Responsibility issued formal guidance in June 2026
clarifying how Circular 230 applies to AI-assisted tax preparation:

**Six compliance obligations for TaxAhead's RAG system:**

1. **Due Diligence (§ 10.22):** Every RAG-generated answer must be verifiable.
   The existing citation validation pipeline already satisfies this for user facts.
   For knowledge base citations, the same bidirectional checking must apply.

2. **Technological Literacy (§ 10.35):** The system must be able to explain
   which KB documents contributed to each answer (already an engineering principle
   in the KB2 docs).

3. **Firm Oversight (§ 10.36):** Human review workflow for KB updates — the
   Annual Tax Reference Center Implementation Guide already specifies this.

4. **Written Advice Standards (§ 10.37):** AI-drafted recommendations require
   independent verification of legal and factual premises. RAG answers must
   cite specific authority (IRC section, regulation, revenue ruling).

5. **Data Privacy (§§ 6713, 7216):** Taxpayer data must not leak into the
   knowledge retrieval pipeline. The KB is domain knowledge, not taxpayer data.
   RLS enforcement must ensure knowledge queries don't expose cross-tenant facts.

6. **Billing Transparency (§ 10.27):** Not directly relevant to RAG architecture
   but relevant to product pricing.

### 4.2 Architectural Implications

- **Citation namespace separation:** User fact citations [C1] vs knowledge citations [K1]
  vs authority citations [A1] — all validated independently
- **Authority hierarchy in retrieval:** When multiple KB chunks conflict, the one
  grounded in higher authority wins (IRC > Reg > Ruling > Pub)
- **"Not tax advice" disclaimer layer:** Any response that interprets tax law
  (vs. reporting user facts) must surface appropriate disclaimers
- **Audit trail extension:** The SHA-256 context hash must cover both user facts
  AND retrieved knowledge chunks

---

## 5. Recommended Architecture

### 5.1 Target Architecture (Phase 3 Complete)

```
User Question
     │
     ▼
┌─────────────────────────────────┐
│ Query Classifier                │
│  • Tax question? (scope gate)   │
│  • Query type: factual / legal  │
│    / procedural / multi-hop     │
│  • Jurisdiction: fed / state    │
│  • Tax year(s) implicated       │
└────────┬────────────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────────────────┐
│ User    │ │ Knowledge           │
│ Facts   │ │ Retrieval           │
│ (SQL)   │ │                     │
│         │ │  ┌───────────────┐  │
│ Current │ │  │ Hybrid Search  │  │
│ arch:   │ │  │ BM25 + pgvec  │  │
│ 3 SQL   │ │  │ + re-ranking   │  │
│ queries │ │  └───────────────┘  │
│         │ │                     │
│         │ │  ┌───────────────┐  │
│         │ │  │ Annual Ref    │  │
│         │ │  │ Resolution    │  │
│         │ │  │ (TY lookup)   │  │
│         │ │  └───────────────┘  │
└────┬────┘ └────────┬───────────┘
     │               │
     ▼               ▼
┌─────────────────────────────────┐
│ Context Assembly                 │
│  • User facts [C1..Cn]          │
│  • Knowledge passages [K1..Km]  │
│  • Authority citations [A1..Ap] │
│  • Token budget management      │
│  • Jurisdiction + year filter   │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Claude API                       │
│  • System prompt: answer from   │
│    CONTEXT, cite everything     │
│  • Tools: answer_from_evidence  │
│    (extended with K/A citations)│
│  • Dollar figure guard          │
│  • Out-of-scope detection       │
└────────┬────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Server-Side Validation           │
│  • [C*] markers → fact IDs      │
│  • [K*] markers → KB chunk IDs  │
│  • [A*] markers → authority refs│
│  • All bidirectional            │
│  • SHA-256 of full context      │
│  • Circular 230 disclaimer      │
│    on interpretive answers      │
└────────┬────────────────────────┘
         │
         ▼
    Response + citations + proof metadata
```

### 5.2 What Changes vs What Stays

| Component | Status | Change |
|-----------|--------|--------|
| Auth / RLS | Keep | No change |
| User fact retrieval (3 SQL queries) | Keep | No change |
| System prompt | Extend | Add knowledge citation format, authority references |
| answer_from_evidence tool | Extend | Add `knowledge_citations` and `authority_citations` fields |
| Server-side validation | Extend | Add K/A marker validation alongside C markers |
| Context hash | Extend | Include knowledge chunks in hash |
| Tracing | Keep | No change |
| **NEW: Query classifier** | Build | Route and scope the retrieval |
| **NEW: Knowledge retrieval** | Build | Hybrid search over KB2 chunks |
| **NEW: Annual reference resolver** | Build | Look up TY-specific values |
| **NEW: Context budget manager** | Build | Allocate tokens across facts + knowledge |
| **NEW: KB ingestion pipeline** | Build | Chunk, embed, index the KB2 corpus |
| **NEW: Circular 230 disclaimer layer** | Build | Surface on interpretive answers |

---

## 6. Implementation Phases

### Phase 1: Foundation (Weeks 1-3) — "Can it answer ONE tax law question?"

**Goal:** Get the KB2 corpus indexed and retrievable. Answer a single tax law question
with proper citations.

**Tasks:**
1. **Convert KB2 .docx to structured markdown/JSON** — preserve document hierarchy,
   section headings, concept boundaries
2. **Design chunk schema** — each chunk: {id, domain, section_path, content,
   cross_references[], tax_years[], jurisdictions[], authority_refs[]}
3. **Build chunking pipeline** — hierarchical chunking respecting KB2 document structure
4. **Enable pgvector in Supabase** — `CREATE EXTENSION vector`
5. **Create `kb_chunks` table** with vector column + metadata columns
6. **Embed all chunks** using text-embedding-3-small
7. **Build retrieval function** — hybrid search (pgvector cosine + tsvector BM25)
   with RRF fusion, top-20 → re-rank → top-5
8. **Extend ask-taxahead** — add knowledge retrieval alongside user facts
9. **Extend citation validation** — add [K*] markers for knowledge citations
10. **Write 20 test questions** covering: factual, legal, procedural, multi-hop

**Deliverable:** ask-taxahead can answer "How does self-employment tax work?" with
citations to specific KB2 chunks.

**Estimated cost:** ~$0.04 for initial embedding; ~$0.001 per query thereafter.

### Phase 2: Quality & Coverage (Weeks 4-6) — "Can it answer ACCURATELY?"

**Goal:** Establish accuracy benchmarks, handle edge cases, add compliance layer.

**Tasks:**
1. **Build evaluation dataset** — 100+ tax questions with gold-standard answers
   and expected citations
2. **Measure retrieval accuracy** — precision@5, recall@10, MRR on gold dataset
3. **Evaluate embedding models** — compare text-embedding-3-small vs voyage-3-large
   vs jina-v3 on the tax question set
4. **Add re-ranking layer** — Cohere Rerank or cross-encoder
5. **Build Annual Tax Reference Center** — TY-specific values in a structured table;
   chunks reference variable names that resolve at query time
6. **Add jurisdiction filtering** — state-specific queries only retrieve relevant state chunks
7. **Add Circular 230 disclaimer layer** — detect interpretive answers, append disclaimer
8. **Add authority citations [A*]** — when the KB references specific IRC sections,
   regulations, or rulings, surface them as first-class citations
9. **Build KB update pipeline** — when a KB2 doc is updated, re-chunk, re-embed,
   re-index (with versioning)
10. **Multi-turn conversation memory** — persist conversation history per filing unit;
    retrieve recent turns as additional context

**Deliverable:** 80%+ accuracy on gold evaluation dataset; compliance layer active.

### Phase 3: Intelligence (Weeks 7-12) — "Can it REASON across domains?"

**Goal:** Enable multi-hop reasoning, cross-state analysis, proactive guidance.

**Tasks:**
1. **Build knowledge graph from KB2** — extract entities and relationships from the
   corpus into a graph structure (the KB2 is already an ontology in prose)
2. **GraphRAG augmentation** — for multi-hop queries, traverse the graph to find
   related concepts before vector retrieval
3. **Multi-state reasoning** — implement the interstate reasoning framework from
   the Multi-State Tax Intelligence document
4. **Proactive insight engine** — when new facts arrive, check against KB2 for
   triggered obligations/opportunities
5. **Life event detection** — use the Life Event Knowledge framework to detect
   significant changes and anticipate tax consequences
6. **Confidence propagation** — extend the Confidence & Validation framework to
   RAG answers (every answer has a confidence score based on evidence quality +
   knowledge coverage)
7. **Production evaluation CI/CD** — run the gold evaluation suite on every KB
   update; block deployment if accuracy drops

**Deliverable:** Multi-hop questions like "I moved from CA to TX mid-year and have
rental income in both states — what are my filing obligations?" answered with
full multi-state reasoning chain.

---

## 7. Scaling Considerations

### 7.1 Multi-State Support (50 states × federal × local)

The KB2 corpus already covers all 50 states + DC in ~3,085 pages of state-specific
knowledge plus ~297 pages of interstate reasoning. The chunking strategy should:

- Tag every chunk with `jurisdiction` metadata (US-FED, US-CA, US-TX, etc.)
- Enable jurisdiction-filtered retrieval: "What are California's estimated tax
  payment requirements?" only searches US-CA chunks
- Interstate queries retrieve from both the state-specific chunks AND the
  Multi-State Tax Intelligence chunks

At ~4,000-8,000 total chunks, even with 50 states represented, pgvector handles
this volume trivially. Scaling concern is not vector count — it's retrieval
precision across jurisdictions.

### 7.2 Real-Time Tax Law Updates

The KB2 Engineering Guidelines already specify a **Source Monitoring & Data Ingestion**
workflow:

1. Monitor official government sources (IRS, state DORs, Treasury)
2. Detect updated guidance
3. AI-assisted extraction of changes
4. Comparison with previous filing year
5. Human review and approval
6. Dataset publication with versioning
7. Continuous monitoring for corrections

**Implementation:**
- KB2 documents live in version control (they're already .docx in the repo)
- On update: re-chunk affected documents → re-embed → upsert into `kb_chunks`
  with new version
- Maintain chunk version history for audit trail
- Annual Tax Reference Center updates are separate from KB reasoning updates

### 7.3 Cost at Scale

| Component | Phase 1 Cost | Phase 3 Cost (1K users/day) |
|-----------|-------------|---------------------------|
| Embedding (initial) | ~$0.04 | ~$0.04 (one-time, re-embed on update) |
| Embedding (queries) | ~$0.00004/query | ~$4/day |
| pgvector (Supabase) | Included | Included |
| Re-ranking (Cohere) | $0 (free tier) | ~$5/day |
| Claude API (answers) | Current cost | Current cost + ~20% for longer context |
| **Total monthly** | **~$0** | **~$300-500/month** |

### 7.4 Latency Requirements

| Step | Target Latency | Method |
|------|---------------|--------|
| Query classification | <50ms | Rule-based or small model |
| User fact retrieval | <100ms | Existing SQL queries |
| Knowledge retrieval | <200ms | pgvector + BM25 parallel |
| Re-ranking | <150ms | Cohere API |
| Context assembly | <50ms | String concatenation |
| Claude generation | 2-5s | Streaming response |
| Validation | <50ms | Server-side checks |
| **Total (to first token)** | **<1s** | Streaming from Claude |

---

## 8. Competing Priorities — Where Does RAG Fit?

Based on the RAG audit's gap analysis and the current product state:

| Priority | Work Item | Dependency | Effort |
|----------|-----------|------------|--------|
| **P0** | Add 1099-NEC extraction | None | ~2 hours |
| **P0** | Add Schedule C expected items | None | ~1 hour |
| **P0** | Add SE tax computation | None | ~2 hours |
| **P0** | Add Schedule E expected items | None | ~1 hour |
| **P1** | **KB2 → RAG ingestion (Phase 1)** | None | ~2-3 weeks |
| **P1** | Add more document types (1099-MISC, 1099-B, 1098) | Extraction pipeline | ~2 days each |
| **P1** | **RAG quality & evaluation (Phase 2)** | Phase 1 | ~2-3 weeks |
| **P2** | Form mapping layer (fact → 1040 line) | None | ~1 week |
| **P2** | Multi-state computation | State constants | ~2 weeks |
| **P2** | Multi-turn conversation memory | None | ~3 days |
| **P3** | **GraphRAG + cross-domain reasoning (Phase 3)** | Phase 2 | ~4-6 weeks |
| **P3** | Proactive insight engine | Phase 1 RAG | ~2 weeks |
| **P3** | Life event detection | KB2 + extraction | ~3 weeks |

**RAG is P1 — it's the highest-leverage infrastructure investment.** The P0 items
(document type coverage) are quick wins that improve the existing data-mirror.
RAG transforms TaxAhead from a data-mirror into a tax intelligence platform.

### Why RAG Before Form Mapping or Multi-State

- **Form mapping** requires knowing which facts go where — the KB2's IRS Forms
  Library (878 pages) already defines this; RAG makes it queryable
- **Multi-state computation** requires state-specific rules — the KB2's State Tax
  Knowledge (3,085 pages) already encodes these; RAG makes them retrievable
- Without RAG, both form mapping and multi-state would require building rule engines
  from scratch. With RAG, they become retrieval problems over an existing corpus

---

## 9. Technology Stack Recommendation

```
┌──────────────────────────────────────────────┐
│ Current Stack (Preserved)                     │
│  • Supabase Postgres + Auth + RLS            │
│  • Supabase Edge Functions (Deno)             │
│  • Claude API (Anthropic)                     │
│  • TypeScript frontend                        │
└──────────────────────────────────────────────┘
                    +
┌──────────────────────────────────────────────┐
│ RAG Layer (New)                               │
│  • pgvector extension (Supabase Vector)       │
│  • text-embedding-3-small (OpenAI)            │
│  • Hybrid search: pgvector + tsvector (BM25)  │
│  • Cohere Rerank API                          │
│  • KB2 chunk store: kb_chunks table           │
│  • Annual Reference: annual_tax_values table   │
│  • Conversation history: feed_messages (ext.) │
│  • Query classifier: rule-based + Claude Haiku│
└──────────────────────────────────────────────┘
```

**No new infrastructure.** Everything runs on the existing Supabase + Claude stack.
The only new external dependency is Cohere (re-ranking), which has a generous free
tier and can be replaced with a self-hosted cross-encoder later.

---

## 10. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Hallucinated tax advice** | User files incorrectly, faces penalties | Existing 3-layer grounding extends to knowledge citations; fail-closed on any uncited claim |
| **Stale knowledge** | Tax law changes, system gives outdated advice | KB2 update pipeline with versioning; Annual Reference Center for yearly values |
| **Cross-jurisdiction confusion** | Wrong state rules applied | Jurisdiction-filtered retrieval; interstate reasoning chunks always included for multi-state queries |
| **Circular 230 liability** | IRS enforcement action | Disclaimer layer on interpretive answers; authority citations [A*] for every legal claim |
| **Embedding drift** | Model upgrade breaks retrieval quality | Evaluation CI/CD suite runs on every embedding model change; A/B test before switching |
| **Context window overflow** | Too many chunks, Claude loses precision | Token budget manager allocates fixed budgets: 40% facts, 50% knowledge, 10% system |
| **Data leakage** | Taxpayer facts exposed in knowledge retrieval | RLS on kb_chunks is read-all (KB is not tenant-specific); user facts remain RLS-scoped |

---

## 11. Summary Decision Matrix

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector DB | **pgvector (Supabase)** | Already on Supabase; corpus fits easily; RLS native |
| Retrieval | **Hybrid (BM25 + semantic)** | Tax queries mix exact references and conceptual questions |
| Embedding | **text-embedding-3-small** → voyage-3-large | Start cheap, upgrade for accuracy |
| Chunking | **Hierarchical, domain-aware** | KB2's ontology structure IS the chunk boundary |
| Re-ranking | **Cohere Rerank** | Purpose-built, free tier, swappable |
| Graph layer | **Phase 3** | After hybrid retrieval is validated |
| Framework | **No framework (custom)** | Existing ask-taxahead architecture is strong; LangChain/LlamaIndex add complexity without value here |
| Compliance | **Circular 230 disclaimer + authority citations** | IRS OPR Alert 2026-19 requirements |
| Evaluation | **Gold dataset + CI/CD gate** | Block KB updates that drop accuracy below threshold |

---

## Sources

- [RAG: An Architectural Review and Strategic Outlook for 2025](https://www.linkedin.com/pulse/rag-architectural-review-strategic-outlook-2025-bal%C3%A1zs-feh%C3%A9r-bwzpf)
- [GraphRAG vs RAG: Why Traditional RAG Fails for Regulatory Compliance](https://medium.com/@visrod/raphrag-vs-rag-why-traditional-rag-fails-for-regulatory-compliance-5381c14a3d98)
- [GraphRAG & Standard RAG in Financial Services (Microsoft)](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/unlocking-insights-graphrag--standard-rag-in-financial-services/4253311)
- [GraphRAG vs Vector RAG: Accuracy Benchmark Insights](https://www.falkordb.com/blog/graphrag-accuracy-diffbot-falkordb/)
- [LegalBench-RAG: A Benchmark for RAG in the Legal Domain](https://arxiv.org/abs/2408.10343)
- [FinSage: Multi-aspect RAG for Financial Filings](https://arxiv.org/html/2504.14493v3)
- [Assessing RAG System Capabilities on Financial Documents](https://aclanthology.org/2025.finnlp-2.9.pdf)
- [RAG Architecture for Financial Compliance Knowledge](https://www.auxiliobits.com/blog/rag-architecture-for-domain-specific-knowledge-retrieval-in-financial-compliance/)
- [Production RAG in 2025: Evaluation Suites, CI/CD Quality](https://dextralabs.com/blog/production-rag-in-2025-evaluation-cicd-observability/)
- [HierFinRAG: Hierarchical Multimodal RAG for Financial Reports](https://www.mdpi.com/2227-9709/13/2/30)
- [pgvector vs Pinecone vs Qdrant vs Weaviate (2026)](https://www.kalviumlabs.ai/blog/vector-databases-compared-pgvector-pinecone-qdrant-weaviate/)
- [Best Vector Databases in 2026: Complete Comparison](https://www.firecrawl.dev/blog/best-vector-databases)
- [When to Use pgvector vs Pinecone vs Weaviate](https://dev.to/polliog/postgresql-as-a-vector-database-when-to-use-pgvector-vs-pinecone-vs-weaviate-4kfi)
- [Chunking Strategies for Legal & Reference RAG Systems](https://edtek.ai/kb/chunking-strategies-legal-reference-documents/)
- [How Unstructured Unlocked 100K+ Pages of IRS Manuals](https://medium.com/unstructured-io/leveraging-enterprise-specific-data-with-llms-how-unstructured-unlocked-100k-pages-of-irs-manuals-33e16308c1e3)
- [Citation-Enforced RAG for Fiscal Document Intelligence](https://arxiv.org/html/2603.14170)
- [Legal Chunking: Evaluating Methods for Effective Legal Text Retrieval](https://www.researchgate.net/publication/386472016_Legal_Chunking_Evaluating_Methods_for_Effective_Legal_Text Retrieval)
- [Hybrid Search for RAG: Combining BM25 and Dense Retrieval](https://denser.ai/blog/hybrid-search-for-rag/)
- [Hybrid Search and Re-Ranking in Production RAG](https://towardsdatascience.com/hybrid-search-and-re-ranking-in-production-rag/)
- [Section-Level RAG: Why BM25 Beat Hybrid Search](https://blog.jztan.com/bm25-vs-hybrid-search-section-rag/)
- [Fine-Hybrid: Integration of BM25 and Finetuned SBERT (Tax Compliance)](https://ejournal.ikado.ac.id/index.php/teknika/article/view/1229)
- [IRS Circular 230: Office of Professional Responsibility](https://www.irs.gov/tax-professionals/office-of-professional-responsibility-and-circular-230)
- [IRS Outlines AI Risks, Circular 230 Duties for Tax Practitioners](https://www.journalofaccountancy.com/news/2026/jun/irs-outlines-ai-risks-circular-230-duties-for-tax-practitioners/)
- [2026 IRS Rules on Using AI for Tax Preparation (Thomson Reuters)](https://tax.thomsonreuters.com/blog/irs-circular-230-ai-guidance-explained/)
- [Circular 230 and AI-Assisted Tax Practice (SSRN)](https://papers.ssrn.com/sol3/Delivery.cfm/6818660.pdf?abstractid=6818660&mirid=1)
- [The IRS Just Drew a Clearer Line on AI in Tax Practice (Wolters Kluwer)](https://www.wolterskluwer.com/en/expert-insights/circular-230-ai-update-what-is-means-for-firms)
- [Can Your Tax Advisor Use AI? (Syracuse Law Review)](https://lawreview.syr.edu/can-your-tax-advisor-use-ai-the-irs-says-yes-but-professional-responsibility-still-comes-first/)
- [State of RAG in 2026: GraphRAG, Guardrails & Enterprise](https://squirro.com/squirro-blog/state-of-rag-genai)
- [Haystack vs LangChain: RAG Validation Comparison](https://myscale.com/blog/haystack-vs-langchain-rag-validation-comparison/)
- [Knowledge-Graph-Augmented RAG for Multi-Framework Tax Reasoning](https://arxiv.org/html/2604.23585v1)
- [RAG Techniques You Must Know in 2025](https://pub.towardsai.net/rag-techniques-you-must-know-in-2025-872b074da20a)
- [The Impact of Document Formats on Embedding Performance in Tax Law](https://www.robertodiasduarte.com.br/the-impact-of-document-formats-on-embedding-performance-and-rag-effectiveness-in-tax-law-applications/)

---

*Research saved to `~/Claude/loop/research/taxahead_rag_options_2026-07-20.md`*
*Companion: `~/Claude/loop/research/taxahead_rag_audit_2026-07-20.md`*
