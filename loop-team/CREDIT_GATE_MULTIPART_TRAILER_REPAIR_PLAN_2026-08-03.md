# Credit-gate multipart trailer repair — implementation plan

## Decision and scope

**Goal.** Reconcile the live credit-gate behavior with AC4 without weakening the
authorization boundary: a standalone `agentId:` string remains invalid in ordinary
model-controlled text, while the one canonical runtime metadata form is accepted only
when the original `tool_result.content` is a trusted multipart sequence that proves the
metadata crossed a content-part boundary. An optional, already-supported canonical
`<usage>...</usage>` trailer may follow that metadata part.

**Task class:** `modify/fix/continue`.

```text
COST_OF_DELAY: HIGH
COD_REASON: The combined registry acceptance cannot become green or be committed while
the current hook accepts a plain-string trailer that AC4 correctly treats as model-controlled.
COD_FAMILY: UNREGISTERED
```

This is the dedicated repair required by
`H-CREDITGATE-AC4-SEPARATE-AGENTID-CONTRACT-CONFLICT-1`. It does not reopen the
registry design, benchmark work, or any unrelated dirty work.

## Current semantic audit (authoritative starting point)

`hooks/spec_bound_verifier_credit.py` currently flattens a list-valued `content` to
newline-joined text in `tool_result_text()` (lines 363-370 at plan authoring), then its
trailing walk in `classify_plan_result_for_hash()` accepts one separate-line
`agentId:` by text shape alone (lines 491-519). Once flattened, a model-authored
plain string and a runtime multipart result are indistinguishable. That is why
`NonUsageTrailingContentRejectedAC4.test_trailing_standalone_agentid_line_rejected`
expects `False` but currently receives `True`.

The source already has two distinct, retained allowances that this repair must not
broaden or remove:

1. an optional single well-formed `<usage>...</usage>` block after the gate;
2. the narrowly validated `agentId:` glued directly to the gate line (and the exact
   terminal `</result>` glue), including its malformed-suffix and decoy-token guards.

The needed distinction is therefore structural, not a looser trailer regex.

## Exact source and test boundaries

### Files to modify in the source-repair slice

- `hooks/spec_bound_verifier_credit.py`
  - `tool_result_text()` (currently lines 363-370): retain its general text extraction
    for callers that need it, but do not make it the authority for whether a
    standalone trailer is trusted.
  - `classify_plan_result_for_hash()` (currently lines 446-617): derive a
    fail-closed trailer provenance classification from the original `tool_result`
    before the content parts are flattened; use it only for the standalone-agentId
    exception.
- `hooks/test_spec_bound_verifier_credit.py`
  - `plain_result()` (currently lines 1165-1172) remains the raw-string fixture
    helper. Add a narrowly named multipart helper rather than silently changing what
    `plain_result()` means.
  - retained AC1/AC2/AC3/AC4/AC7/AC8 fixtures around lines 2929-3387;
  - `ProductionAuthorizationBoundaryAC6` around lines 3143-3219.

### Files to verify and carry in the registry-lineage slice, after source is final

- `loop-team/contract_registry/v1/manual_overlays/spec_bound_verifier_credit.v1.json`
  - replace `target_source_sha256` with the raw-byte hash of the committed source-repair
    version;
  - re-audit every listed source span against that exact source. Preserve the 30 unique
    literal rejection reasons and their ordering only if that re-audit proves the literal
    inventory did not change; update spans where source movement requires it.
  - do not change its dossier provenance merely to refresh the source hash.
- `loop-team/harness/test_gate_contract_registry.py`, only if its assertions freeze the
  target hash/spans or generated-lineage behavior affected by the overlay update.
- generated projections, never hand-edited:
  - `loop-team/contract_registry/v1/gate_contracts.v1.json`
  - `loop-team/contract_registry/v1/gate_contract_coverage.v1.md`

The registry-lineage commit is self-contained. It must also include the already-untracked
registry implementation and provenance artifacts that make these projections reproducible:

- `loop-team/harness/gate_contract_registry.py`
- `loop-team/harness/test_gate_contract_registry.py`
- `loop-team/harness/testdata/gate_contract_registry/**`
- `loop-team/contract_registry/v1/scope_manifest.v1.json`
- `loop-team/GATE_CONTRACT_REGISTRY_IMPLEMENTATION_PLAN_2026-08-02.md`
- `loop-team/FRAMEWORK_OWNER_CONTINUATION_RECEIPT_2026-08-02.md`, only after it is
  reconciled to the repair's actual receipts and commit topology;
- `loop-team/specs/gate-diagnosis-phase1-contract-registry.md`, if its current content
  is required provenance for the V1 implementation and passes the same full read/review.

Before staging, make a provenance ledger for every one of those currently untracked
paths: raw SHA-256, current status, origin, purpose, whether it was re-read against the
final source, and explicit `include` or `exclude` disposition. An unreviewed baseline
file must not become a convenient passenger in this commit.

### Hash-pinned 2026-07-29 dossier is a prior provenance gate

The manual overlay's `dossier_relative_path` is
`research/spec-bound-verifier-coder-credit-gate-marker-2026-07-29.md`, pinned to raw-byte
SHA-256 `19199513bc80239d8c81bc2cf7e930e1b7353134a60c6ba7930f89c26a2cad81`. Because that
file is currently untracked, it cannot be silently relied upon by a later registry commit.

Use **option B0: a separate provenance commit first**. Before source repair, independently
read the dossier in full, reproduce its raw-byte hash with `/opt/anaconda3/bin/python`,
and verify that it supports the overlay's all-functions/30-reason enumeration. Only then
make a one-file provenance commit containing that exact dossier. It contains no registry
generator, test, manifest, overlay, projection, source, or source-test path. If the file
does not verify exactly, stop: do not commit it, do not carry its old hash into the overlay,
and do not bundle a replacement without a newly reviewed dossier and explicit plan revision.

No other `loop-team` plans, registry contracts, policy documents, or source modules are
in scope.

## Required target semantics

### A. Ordinary text remains fail-closed

For `content` that is a string (including a string containing newline characters), the
existing AC4 rule remains literal: a separate trailing `agentId:` line is rejection
content. The following must return non-PASS:

- `LOOP_GATE: PLAN_PASS` followed by a standalone canonical-looking `agentId:` line;
- that same line followed by `<usage>...</usage>`;
- any arbitrary prose, `PLAN_SUPPORT_JSON`, hash, or additional `LOOP_GATE:` tail;
- a second usage block, unterminated usage, or content after a usage block.

The raw-string `test_trailing_standalone_agentid_line_rejected` is retained unchanged
as the direct regression lock. The repair must not solve it by weakening, deleting, or
relabeling AC4.

### B. Narrow multipart-only exception

The exception is available only when `tool_result["content"]` is an actual ordered list
of text-bearing content parts. It is not inferred from the newline-joined output of
`tool_result_text()`.

The accepted shape is exactly:

```text
part 0: model-controlled valid PLAN_SUPPORT_JSON / REVIEWED_SPEC_SHA256 / one valid gate
part 1: one canonical runtime agentId metadata part
part 2: optional one complete canonical <usage>...</usage> metadata part
EOF
```

The Coder must encode the canonical agentId grammar from the existing frozen runtime
capture, including a non-empty identifier, the deterministic `use SendMessage` marker,
and its matching recipient identity. The match must consume the entire metadata part;
it may not merely find a canonical-looking prefix. The optional usage part remains
subject to the existing one-block, properly-closed rules and must be after the agentId
part. The implementation may accept either existing real usage format, but only as one
complete part and never as arbitrary content.

The ordinary direct string form that currently accepts a usage-only trailer remains
covered by AC1/AC2. This plan only moves the **separate-line agentId** allowance behind
the multipart provenance boundary. The existing same-line agentId glue and `</result>`
logic remain governed by their current narrow validation.

### C. Boundary and ordering rejections

All of the following are required negative cases, even if their flattened string would
otherwise look like an accepted trail:

1. a standalone agentId inside the same first/model text part as the gate;
2. the exact valid-looking multipart sequence supplied as one ordinary string;
3. malformed ID, missing/changed SendMessage structure, mismatched repeated ID, or
   trailing characters in the agentId metadata part;
4. duplicate agentId parts, duplicate usage parts, or two complete usage blocks;
5. usage before agentId, agentId after usage, or any accepted metadata part followed by
   another non-empty part;
6. an unexpected/non-text content part in the post-gate metadata region;
7. a second gate marker, `PLAN_SUPPORT_JSON`, reviewed-hash text, or any
   case-insensitive `LOOP_GATE`-shaped decoy embedded in either metadata part;
8. `is_error: true`, PreToolUse-deny text, invalid/missing support binding, duplicate
   gate lines, and all existing glued-suffix malformed/decoy cases.

Whitespace-only parts may be ignored only if the implementation proves they cannot
create or hide an ordering boundary. Otherwise reject rather than normalize them into a
new bypass surface. Do not add a generic `startswith("agentId:")` branch anywhere.

## Implementation sequence

1. **Test writer: executable contract first.** Add an explicit multipart fixture builder
   that emits `content` as distinct `{"text": ...}` parts, and a raw-string companion
   using the exact same visible text. Add focused behavioral tests for the positive
   canonical multipart agentId case, agentId-plus-each real usage format, and every
   negative group in section C. Reuse the captured runtime strings already in this test
   file; do not invent a model-friendly substitute fixture.

2. **Update AC6's production-boundary fixture.** Change only AC6's verifier
   `tool_result` construction to use the canonical multipart content sequence (model
   result ending in the real gate, canonical agentId part, optional real usage part).
   It must still call `authorize_coder_from_transcript()` through the foreground
   dispatch-to-Coder path. This makes AC6 prove the production caller preserves and
   consumes the multipart boundary rather than only testing the leaf parser.

3. **Coder: preserve raw boundaries before flattening.** Add the smallest private helper
   (or equivalent local structure) that inspects the original `content` list, validates
   the permitted post-gate metadata sequence, and returns a narrow provenance fact. The
   parser may then authorize precisely that fact; it must not use a reconstructed string
   as evidence that a boundary existed. Keep `tool_result_text()` backward compatible for
   all unrelated consumers and leave upstream transcript flattening untouched.

4. **Re-run the whole focused source test file with the target interpreter.** Resolve
   source/test disagreement by preserving the target semantics above, never by weakening
   AC4 or by adding a broad text exception.

5. **Independent semantic review before either commit.** A Verifier who did not write the
   code must inspect the exact diff, the raw versus multipart fixtures, the parser's
   use of original content boundaries, and the negative matrix. Its report must state
   whether a model-controlled string can still gain credit through any accepted
   standalone-agentId shape.

6. **Commit the verified dossier as the separate B0 provenance commit first.** This is
   explicitly not a registry-baseline commit. It exists so the registry lineage can point
   to an already-reviewed, tracked dossier rather than silently absorbing pre-existing
   research at the end.

7. **Commit the source repair only after its independent review and bounded source
   receipts pass.** Commit B1's required allow-list is exactly
   `hooks/spec_bound_verifier_credit.py` and
   `hooks/test_spec_bound_verifier_credit.py`. This repair plan may join B1 only after a
   separate full reread and review-to-commit record; otherwise leave it out. B1 must not
   stage or commit any current registry baseline, generated projection, registry plan,
   continuation receipt, generator, registry test, testdata, manifest, or overlay. It
   does not claim current registry projection hashes are fresh.

8. **Re-establish registry lineage only after B1.** Recompute the exact new source hash,
   re-audit the manual overlay's 30 reason strings and spans, reconcile the implementation
   plan and continuation receipt to actual post-repair truth, and verify the complete
   untracked registry baseline through the provenance ledger. Run the registry generator
   only after the overlay points at the B1 source. Do not hand-edit either generated
   projection. A changed target source hash without a reviewed overlay refresh is
   `MANUAL_OVERLAY_SOURCE_DRIFT`, not an acceptable intermediate final state.

9. **Independently verify and then commit the complete registry-lineage slice (B2).**
   B2's allow-list is the self-contained set in "Files to verify and carry" above, plus
   only re-reviewed registry implementation paths required to make that set executable.
   It is not permitted to silently pick up unrelated old material. B2 is made only after
   `--generate`, `--check`, source tests, registry tests, JSON parse, diff checks, a
   staged-path allow-list comparison, and an independent review all pass.

## Acceptance matrix and bounded receipts

All commands run from `<HOME>/Claude/loop` with exactly
`/opt/anaconda3/bin/python`; do not substitute a shell-default `python3`.

Create durable, unambiguous run receipts under the implementation run directory
`loop-team/runs/2026-08-03_credit-gate-multipart-trailer-repair/`. Each receipt records
the full command, interpreter path, start/end timestamps, elapsed seconds, exit code,
and complete stdout/stderr. A process that exceeds its declared bound is recorded as
`TIMED_OUT`, not a test failure or pass.

### 1. Semantic receipt — bounded 240 seconds

```bash
/opt/anaconda3/bin/python -m pytest hooks/test_spec_bound_verifier_credit.py -q \
  -k 'not ProductionAuthorizationBoundaryAC6'
```

Record this as `semantic_receipt.md`. It proves the leaf parser and all existing
non-AC6 structural controls, including retained raw-string AC4 rejection, current
glued-agentId cases, usage-only cases, and decoy defenses. It does not certify AC6.

### 2. AC6 receipt — bounded 480 seconds

```bash
/opt/anaconda3/bin/python -m pytest \
  hooks/test_spec_bound_verifier_credit.py::ProductionAuthorizationBoundaryAC6 -q
```

Record this separately as `ac6_receipt.md`. AC6 itself has a five-sibling-hooks
subprocess regression floor with a 400-second internal timeout; the outer 480-second
bound prevents an unbounded suite from being reported as a result. A timeout is neither
`AC6_PASS` nor evidence that the semantic receipt failed.

### 3. Provenance receipt — before B0, bounded 60 seconds

```bash
/opt/anaconda3/bin/python -c 'import hashlib, pathlib; p = pathlib.Path("research/spec-bound-verifier-coder-credit-gate-marker-2026-07-29.md"); print(hashlib.sha256(p.read_bytes()).hexdigest())'
```

Record this as `dossier_provenance_receipt.md` alongside a full-review statement. It must
equal `19199513bc80239d8c81bc2cf7e930e1b7353134a60c6ba7930f89c26a2cad81` before the
one-file B0 dossier commit. Hash equality alone is not the review; it only establishes
the raw bytes reviewed and later pinned.

### 4. Registry and combined receipt — bounded 600 seconds

```bash
/opt/anaconda3/bin/python -m pytest loop-team/harness/test_gate_contract_registry.py -q
/opt/anaconda3/bin/python loop-team/harness/gate_contract_registry.py --repo-root . --generate
/opt/anaconda3/bin/python loop-team/harness/gate_contract_registry.py --repo-root . --check
/opt/anaconda3/bin/python -m pytest \
  hooks/test_spec_bound_verifier_credit.py loop-team/harness/test_gate_contract_registry.py -q
/opt/anaconda3/bin/python -c 'import json, pathlib; json.loads(pathlib.Path("loop-team/contract_registry/v1/gate_contracts.v1.json").read_text(encoding="utf-8"))'
git diff --check
```

Record outputs and per-command exits in `registry_lineage_receipt.md`. This final combined
run cannot replace the separate semantic or AC6 receipts; it corroborates them after the
overlay and generated files are refreshed. The receipt also lists the B2 staged paths and
asserts exact equality with this allow-list (after the explicit ledger disposition):

```text
loop-team/harness/gate_contract_registry.py
loop-team/harness/test_gate_contract_registry.py
loop-team/harness/testdata/gate_contract_registry/**
loop-team/contract_registry/v1/scope_manifest.v1.json
loop-team/contract_registry/v1/manual_overlays/spec_bound_verifier_credit.v1.json
loop-team/contract_registry/v1/gate_contracts.v1.json
loop-team/contract_registry/v1/gate_contract_coverage.v1.md
loop-team/GATE_CONTRACT_REGISTRY_IMPLEMENTATION_PLAN_2026-08-02.md
loop-team/FRAMEWORK_OWNER_CONTINUATION_RECEIPT_2026-08-02.md (only if reconciled)
loop-team/specs/gate-diagnosis-phase1-contract-registry.md (only if ledger-included)
```

No other path may be staged in B2. If a required untracked registry path is discovered
outside this allow-list, stop, add it to the plan with its provenance/disposition, and
re-run independent review; do not fold it into B2 opportunistically.

Before each commit, inspect `git status --short`, a path-limited staged diff, and
`git diff --check`. Preserve every pre-existing dirty/untracked path. Do not stage the
unrelated research file, images, or any file outside the commit's explicit allow-list.
The B0 dossier commit is the sole exception for the pinned 2026-07-29 research file;
the current older `research/spec-bound-verifier-coder-credit-gate-marker-2026-07-17.md`
remains excluded. For every `loop-team/` path in B1/B2, use the repository's
review-to-commit re-diff procedure rather than raw staging/commit.

## Completion conditions

The repair is complete only when all are true:

1. Raw text containing a separate `agentId:` remains rejected by the unchanged AC4 lock.
2. Only the canonical multipart `(gate, agentId, optional usage)` sequence gains the
   separate-line exception; malformed, duplicate, reversed, extra, non-text, and decoy
   variants are rejected.
3. AC6 exercises that exact multipart shape at the production authorization boundary and
   has its own non-timeout PASS receipt.
4. Semantic, AC6, registry, and combined receipts are individually green; none is
   silently substituted for another.
5. The hash-pinned 2026-07-29 dossier is independently reviewed and committed alone
   before source repair; it is never silently carried as untracked registry provenance.
6. The manual overlay has a deliberate exact-source re-audit, retains a justified
   30-reason inventory, and `--check` sees no source/overlay/generated drift.
7. Three independently verified commits exist in this order: B0 dossier provenance,
   B1 source/test semantic repair, then B2 complete self-contained registry lineage.

## Non-goals

- Do not accept a plain-string standalone agentId just because it resembles harness output.
- Do not broaden the existing gate-line glued-agentId, `</result>`, or usage tolerances.
- Do not change `RUN.md`, `VERIFIER.md`, `fix_plan.md`, `loop-team/orchestrator.md`, role
  briefs, the benchmark protocol, or any unrelated hook.
- Do not add runtime installation, external browser testing, credentials, or new dependencies.
- Do not stage, commit, reset, delete, or otherwise normalize pre-existing dirty work.

## Concise plan-check input

```text
PLAN-CHECK INPUT — credit-gate multipart trailer repair

Scope: repair only hooks/spec_bound_verifier_credit.py and
hooks/test_spec_bound_verifier_credit.py, then separately refresh the already-existing
credit manual overlay and generated contract-registry projections after the source hash
changes. Preserve all unrelated dirty work.

Accept only if:
1. A plain string with a separate agentId line still fails AC4; the test itself remains
   an unchanged raw-string regression lock.
2. Separate agentId acceptance comes only from an original ordered multipart tool_result
   content boundary: valid model gate part, one fully canonical agentId part, then at most
   one complete usage part. Flattened text alone cannot establish that provenance.
3. Tests reject malformed IDs, duplicated or reversed agentId/usage parts, unexpected or
   non-text parts, extra tails, and embedded decoy LOOP_GATE/support/hash content; existing
   glued-agentId and exact </result> defenses remain green.
4. AC6 is converted to that multipart fixture and is run/reported independently from the
   semantic test selection, with bounded receipts using /opt/anaconda3/bin/python.
5. The 2026-07-29 hash-pinned dossier is independently read, hash-verified, and committed
   alone before source repair; a replacement dependency requires an explicit revised plan.
6. After source changes, the overlay source hash and spans are re-audited, every required
   untracked registry artifact is ledger-reviewed and carried in one self-contained B2
   commit, generator output is regenerated (never hand-edited), and --check plus the
   combined source/registry suite pass.
7. B1 contains only source/test semantic repair (with this plan only if separately
   reread), B2 contains no unreviewed passenger paths, and both are independently verified.

Reject if the allowance can be triggered by model-controlled flattened text, if AC4 is
weakened, if AC6 is merged into an unbounded/general receipt, or if registry source drift is
left stale between the final commits.
```
