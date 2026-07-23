# PLAN_SUPPORT_JSON evidence_sha256 values for a real, still-open gap in claude_product_pilot.md

**Date:** 2026-07-17. **Follow-up to:** `research/spec-bound-verifier-coder-credit-gate-marker-2026-07-17.md`.
**Requested by:** Oga, on behalf of a plan-check-verifier that is read-only (no Bash, cannot
hash anything itself) and needs real `evidence_sha256` values to replace its placeholder
`"UNCOMPUTABLE_NO_HASH_TOOL_IN_THIS_DISPATCH"`.
**Confidence: CONFIRMED** — transform re-read from live source (not trusted from paraphrase),
both hashes computed directly from the real on-disk file, and both live-verified against the
real, unmodified `_validate_plan_support_json()` — including two independent mutation/negative
checks proving the validator genuinely discriminates rather than rubber-stamping.

## 1. Transform confirmed from live source (not the paraphrase alone)

Re-read fresh from disk, `<HOME>/Claude/loop/hooks/spec_bound_verifier_credit.py:299-306`:

```python
def _support_span_digest(path, line_start, line_end):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if line_start < 1 or line_end < line_start or line_end > len(lines):
        return None, "missing artifact/span"
    selected = lines[line_start - 1:line_end]
    joined = "\n".join(selected)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), None
```

The paraphrase ("read file UTF-8 → splitlines() → lines[line_start-1:line_end] → join with
'\n' → sha256 hexdigest") is **exactly correct**, word for word matching the real code.

## 2. Top-level file hash — reconfirmed, unchanged

```
<HOME>/Claude/loop/loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md
7745e91e689f8091406ae5e7037ef2c150cfc9bd298ac5a1513e94cdc197b61b
```
Recomputed fresh via `shasum -a 256` and Python `hashlib.sha256` (both agree); 58,123 bytes;
mtime `Fri Jul 17 10:30:43 2026` — **unchanged from the two prior checks earlier this session**
(same value reported in both prior dossiers). **No drift** — the line numbers 447-456 and
668-680 are safe to use against the file as it stands right now.

## 3. Content sanity-check (read directly, not taken on the verifier's word)

Read both spans directly off disk before hashing, to confirm they are what they're claimed
to be:

- **Lines 447-456** (§5 closing paragraph): ends "...reusing `_AtomicPreparationWriter`
  and the `_canonical_bytes`/`_canonical_hash`/`packet_hash`/`manifest_hash`/`approval_hash`
  helpers **directly from `codex_subscription_pilot.py`**... two concurrent threads are
  actively patching **that same file** right now..." — mentions only
  `codex_subscription_pilot.py`, no `codex_exec_adapter.py`.
- **Lines 668-680** (§11 point 2): "...the canonical-hash helpers directly from
  `codex_subscription_pilot.py`... two separate concurrent threads are independently
  patching **that same file and `codex_exec_adapter.py`** for an unrelated argv-ordering bug
  right now..." — explicitly names both files.

This confirms the plan-check-verifier's finding is real and the two spans are the correct,
exact evidence for it: §5's version of the concurrency rationale is missing the
`codex_exec_adapter.py` mention that §11 point 2 has.

## 4. Computed evidence_sha256 values

| span | artifact_path | line_start | line_end | evidence_sha256 |
|---|---|---|---|---|
| §5 concurrency rationale | `.../specs/claude_product_pilot.md` | 447 | 456 | `9d0d4effae5e3ef6d4a12ac64d72d454d3a355a0c6cc4a03607c4b68d78df686` |
| §11 point 2 | `.../specs/claude_product_pilot.md` | 668 | 680 | `9232f416ed850395ee79b0294e4cd77c2ed56f785c5c72b3edaf3ebc6c523332` |

Both length-checked programmatically at exactly 64 hex characters (never hand-counted), and
carried directly from the computing variable into the constructed JSON/report below —
never manually retyped between steps, to eliminate transcription risk on a load-bearing hash.

## 5. Live verification against the real `_validate_plan_support_json()`

**Positive (the actual values above, real function, real file):**
```
PLAN_SUPPORT_JSON={"artifact_path": ".../claude_product_pilot.md", "line_start": 447, "line_end": 456,
"evidence_sha256": "9d0d4effae5e3ef6d4a12ac64d72d454d3a355a0c6cc4a03607c4b68d78df686", "claim": "...",
"spec_sha256": "7745e91e689f8091406ae5e7037ef2c150cfc9bd298ac5a1513e94cdc197b61b"}
-> _validate_plan_support_json(...) -> valid=True reason=''

PLAN_SUPPORT_JSON={... "line_start": 668, "line_end": 680,
"evidence_sha256": "9232f416ed850395ee79b0294e4cd77c2ed56f785c5c72b3edaf3ebc6c523332", ...}
-> _validate_plan_support_json(...) -> valid=True reason=''
```

**Negative/mutation checks (proving the validator actually discriminates, not a rubber
stamp — same discipline as the AC-oracle-targeting practice used earlier this session):**
- Same two spans, `evidence_sha256` with its last hex character flipped (everything else
  identical) → **both** `valid=False reason='evidence hash mismatch'`.
- Same two spans, ORIGINAL (correct) hash but `line_end` shifted +1 (wrong span, right hash
  string) → **both** `valid=False reason='evidence hash mismatch'` — confirms the check is
  span-sensitive, not just comparing an opaque string.

**End-to-end sanity:** built a full synthetic Verifier result containing both
`PLAN_SUPPORT_JSON=` lines, `REVIEWED_SPEC_SHA256=<top hash>`, and `LOOP_GATE: PLAN_FAIL`
(the semantically correct gate value here, since this is a genuine reported gap, not a
pass), and ran it through the real `classify_plan_result_for_hash()` →
`PlanResultOutcome.EXPLICIT_PLAN_FAIL`, `"explicit LOOP_GATE: PLAN_FAIL"`. Note for the
verifier's own write-up: `classify_plan_result_for_hash` checks for an explicit
`LOOP_GATE: PLAN_FAIL` line and returns `EXPLICIT_PLAN_FAIL` **before** it ever parses/
validates any `PLAN_SUPPORT_JSON=` lines (the FAIL branch short-circuits ahead of the
support-citation logic) — so this mechanical gate doesn't strictly require valid support
citations to recognize a FAIL. The citations are still the right, and now hash-verified,
evidence to include in the write-up for a real, defensible gap report; they just aren't
what makes this specific parser register it as a FAIL.

## Sources

- `<HOME>/Claude/loop/hooks/spec_bound_verifier_credit.py:290-350` (`_support_span_digest`,
  `_validate_plan_support_json`, re-read fresh this round)
- `<HOME>/Claude/loop/loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md`
  — lines 440-459 and 660-684 read directly; full-file hash recomputed via `shasum -a 256`
  and Python `hashlib.sha256`
- Live re-execution of `_support_span_digest` and `_validate_plan_support_json` (positive +
  2 independent mutation/negative cases) and `classify_plan_result_for_hash`, all against the
  real, unmodified module and the real on-disk file — performed during this dossier, not
  merely read.

## Update (same day, later): file shifted again — re-grepped and re-verified fresh

Top-level hash changed: `b7d296bc2fda04f9f3b3830006fb53f7b888e2da0539f24db6fc834647cbbb1e`
(was `7745e91e689f8091406ae5e7037ef2c150cfc9bd298ac5a1513e94cdc197b61b` above — flagged
immediately per instruction; file grew 58,123 -> 64,501 bytes). Re-grepped fresh for
`"actively patching that same file right now"` rather than trusting an estimate: now at
line 483, full closing-paragraph span **475-484** (confirmed by direct read: paragraph
starts right after the blank line at 474, ends right before the blank line at 485/new
`## 6.` heading at 486).

- `evidence_sha256` for 475-484 = `9d0d4effae5e3ef6d4a12ac64d72d454d3a355a0c6cc4a03607c4b68d78df686`
  — **identical** to the original 447-456 value, because the paragraph's text is byte-for-byte
  unchanged, only its line position shifted (hash depends on selected text, not position) —
  a good internal-consistency signal, not a coincidence to be suspicious of.
- Live-verified against real `_validate_plan_support_json()` with `spec_sha256` set to the
  NEW top-level hash: `valid=True, reason=''`. Mutation check (corrupted hash, same span):
  `valid=False, reason='evidence hash mismatch'`.
