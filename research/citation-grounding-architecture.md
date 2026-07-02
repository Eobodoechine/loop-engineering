# Citation Grounding Architecture - solution map

**Added:** 2026-06-27. **Origin:** verifier citation-fabrication incident: the verifier found a real spec gap, then invented specific GitHub issue numbers as evidence.

## Executive finding

The reliable boundary is not "tell the verifier to cite carefully." It is: **citation authority belongs to code, not the model.**

The model may reason over retrieved artifacts and propose claims. It must not mint source identifiers, issue numbers, URLs, document IDs, or quote text in the final report. Code retrieves artifacts, assigns canonical evidence IDs, validates references, and renders citations/quotes from stored evidence.

This closes the identifier-fabrication path. It does not close every evidence-use problem: a model can still select a true span that is misleading for the claim. That is a verdict-quality problem, not citation minting, and needs a separate support/relevance check.

## What the outside work says

### Structured generation is useful but only structural

- OpenAI Structured Outputs with `strict: true` can enforce schema adherence, not the semantic truth of field values. The official docs distinguish schema adherence from plain JSON mode and show `strict: true` as the enabling control: [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).
- Outlines advertises guaranteed schema compliance for JSON Schema, regex, and context-free grammars: [Outlines docs](https://dottxt-ai.github.io/outlines/latest/).
- XGrammar frames constrained decoding with context-free grammars as a way to enable structured generation and reports efficient grammar-constrained generation: [XGrammar paper](https://arxiv.org/abs/2411.15100).

Implication for this project: schema/grammar constraints are still worth using, but only to force an output shape like `evidence_ids: ["EVIDENCE_001"]` and `quote_spans: [{start, end}]`. They cannot prove `EVIDENCE_001` was actually retrieved or that the selected span supports the claim.

### Assertion/retry systems reduce errors but stay reactive

- DSPy Assertions introduce computational constraints and inference-time self-refinement for LM pipelines: [DSPy Assertions](https://arxiv.org/abs/2312.13382).

Implication: assertions are useful as a Tier-1/Tier-1.5 guard, but they are post-generation or retry-oriented. They do not create a capability boundary where a model cannot emit an identifier unless retrieval has occurred.

### Citation quality remains an active RAG/eval problem

- ALCE evaluates LLM answers with citations across fluency, correctness, and citation quality, and reports that even strong systems lacked complete citation support on ELI5 50% of the time: [ALCE](https://arxiv.org/abs/2305.14627).
- LongCite targets fine-grained sentence-level citations in long-context QA and builds a citation benchmark/dataset because citation quality still has room to improve: [LongCite](https://arxiv.org/abs/2409.02897).
- SelfCite improves context attribution by using context ablation as a reward signal: remove cited text and the answer should no longer be preserved; keep cited text and it should be preserved: [SelfCite](https://arxiv.org/abs/2502.09604).
- RAGChecker separates retrieval and generation diagnostics for RAG systems and evaluates fine-grained behavior instead of a single coarse pass/fail: [RAGChecker](https://arxiv.org/abs/2408.08067).
- FActScore decomposes long-form generations into atomic facts and checks support against a reliable source: [FActScore](https://arxiv.org/abs/2305.14251).
- "Lost in the Middle" shows long-context models can fail to robustly use relevant information depending on where it appears in context: [Lost in the Middle](https://arxiv.org/abs/2307.03172).

Implication: external work points toward fine-grained claim/support checking, retrieval diagnostics, and ablation-style sufficiency tests. It does not remove the need for deterministic enforcement around source identity and quote rendering.

## Architecture that should be built

### 1. Retriever owns evidence identity

Retriever output is an immutable artifact dictionary:

```json
{
  "EVIDENCE_001": {
    "source_type": "github_issue",
    "source_id": "65795",
    "url": "https://github.com/org/repo/issues/65795",
    "retrieved_at": "2026-06-27T15:00:00Z",
    "excerpt": "The exact retrieved text...",
    "sha256": "..."
  }
}
```

Rules:

- Evidence keys are assigned by code.
- Raw source identifiers are metadata, not citation tokens the model can freely print.
- The verdict model sees evidence keys and excerpts.
- The final renderer is the only component allowed to print `source_id`, `url`, or quote text.

### 2. Verdict model outputs structured claim records only

The model emits JSON:

```json
{
  "claims": [
    {
      "claim": "The retrieved issue describes retry failure after compaction.",
      "claim_type": "external_artifact",
      "evidence_ids": ["EVIDENCE_001"],
      "quote_spans": [
        {"evidence_id": "EVIDENCE_001", "start": 0, "end": 67}
      ]
    }
  ]
}
```

Rules:

- No generated quote strings.
- No generated URLs.
- No generated issue numbers.
- Quotes are spans into stored excerpts.
- Unsupported analysis must be explicitly typed as `analysis` or `unsupported`.

### 3. Deterministic validator rejects invalid authority

Validator checks in pure Python:

- every `evidence_id` exists in the artifact dictionary
- every quote span is in bounds
- every rendered quote is exactly `excerpt[start:end]`
- every `external_artifact` or `external_authority` claim has at least one evidence ID
- no raw citation-like strings appear in model-authored prose outside rendered citation fields
- no authority markers (`according to`, `per`, `published framework`, `market data shows`, `industry standard`) appear unless the claim has evidence

Violation output should preserve the failing claim:

```json
{
  "status": "invalid_evidence",
  "claim": "Issue #65796 confirms the scheduler bug.",
  "missing_evidence_id": "EVIDENCE_099",
  "raw_output_location": "$.claims[2].evidence_ids[0]",
  "recommended_action": "retrieve_or_escalate"
}
```

Retry policy:

- Formatting-only violation: allow one retry.
- Absent evidence ID or raw unsupported citation: do not blind-retry.
- Either retrieve the missing artifact explicitly, or escalate with the exact claim and violation record.

### 4. Renderer is the only citation printer

Renderer takes validated claim records and evidence objects and prints citations/quotes. If a source ID or URL is not present in evidence metadata, the renderer cannot print it.

This is the capability boundary. A verifier can hallucinate `#65796` internally, but the report cannot contain it unless code has a retrieved artifact whose metadata says `source_id: "65796"`.

## Deterministic traps to add

The current frozen case `verifier-cites-absent-evidence-id.json` is a good role-judge trap, but it still requires a judge. The next deterministic rung should test the validator/renderer directly with no model.

### Trap A - absent evidence ID

Input:

- artifacts contain `EVIDENCE_001` with source_id `65795` and `EVIDENCE_002` with source_id `65797`
- model output references `EVIDENCE_003` or raw `#65796`

Expected:

- validator returns `invalid_evidence`
- renderer refuses to print a report
- no output report contains `65796`

### Trap B - fabricated quote text

Input:

- artifact excerpt: `The scheduler retries twice after compaction.`
- model output includes generated quote: `resumeFromRunId silently restarts from scratch`

Expected:

- schema rejects generated quote field if quotes are not allowed
- span-only quote rendering cannot produce the fabricated sentence

### Trap C - out-of-bounds or wrong-source span

Input:

- model cites `EVIDENCE_001`
- quote span points past excerpt length, or claim cites `EVIDENCE_001` while span references `EVIDENCE_002`

Expected:

- validator rejects with exact JSON path

### Trap D - authoritative prose with no identifier

Input:

- model output claim: `Per the company's published compensation framework, this band is standard for the role.`
- `evidence_ids: []`

Expected:

- validator rejects as unsupported authority
- renderer may only print: `No retrieved evidence supports the compensation-framework claim.`

### Trap E - supported quote but weak support

Input:

- span is exact and in bounds, but does not entail the claim

Expected:

- deterministic citation validator passes identity/span checks
- a separate support judge or NLI-style scorer must evaluate claim support

This trap is important because it prevents overclaiming what the citation validator proves.

## Build plan for this repo

1. Add `loop-team/evals/citation_grounding.py` with:
   - `validate_claims(model_output, artifacts) -> (status, violations)`
   - `render_report(validated_claims, artifacts) -> str`
   - conservative regex checks for raw citation-like strings and authority markers
2. Add `loop-team/evals/test_citation_grounding.py` covering traps A-D plus good cases.
3. Add a `target: "citation_grounding"` runner to `run_evals.py`, analogous to `target: "recorded_fetch"`.
4. Convert the current judge-only absent-ID case into a deterministic sibling case, leaving the judge case in place.
5. Later: add a separate `citation_support` lane for Trap E. That lane can use claim decomposition, context-ablation scoring, or an LLM/NLI judge, but it must be named separately so nobody confuses "citation identity valid" with "claim supported."

## Open design choices

- **Span indexing:** use Python string character offsets for speed, or byte offsets for exact cross-runtime reproducibility. Recommendation: start with character offsets and store the original `sha256`; switch to byte offsets if multi-language renderers appear.
- **Raw identifier regex:** strict enough to catch issue numbers, arXiv IDs, URLs, and `EVIDENCE_999`; conservative enough not to block ordinary prose. Recommendation: fail only in final report fields, not internal diagnostic fields.
- **Authority markers:** marker list should be intentionally small at first to avoid over-rejection. Treat marker catches as `unsupported_authority`, not as proof the underlying claim is false.
- **Evidence exposure:** the model can see source metadata for reasoning, but renderer owns printing. For stricter mode, hide raw source IDs and expose only evidence keys plus excerpts.

## Bottom line

Use current citation/RAG research for evaluation ideas, not as the enforcement boundary. The enforcement boundary is local and mechanical:

retriever creates evidence -> model references evidence keys/spans -> validator checks keys/spans/authority -> renderer prints citations.

Anything else remains probabilistic grounding.
