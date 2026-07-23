# Domain brief — AC7 backing-record provenance design (control-plane dashboard v1 redesign)

**Mode:** D (domain research for a build — this repo's own architecture).
**Dispatched by:** Oga, after 3 consecutive plan-check PLAN_FAILs on AC7 in
`runs/2026-07-12_control-plane-dashboard-redesign/plan_check_log.md`.
**Scope:** read-only investigation of `loop-team/harness/product_dashboard.py` +
its test files. No edits made to any file except this brief.

## question

Three plan-check rounds found real gaps in AC7 (render elapsed-time-since-verification
for the *specific* proof record that backs an item's current derived `evidence_label`),
each because the spec kept teaching the RENDERER more of `derive_evidence_label`'s
internal selection logic (which record "wins," the tie-break, the live-smoke
genuineness gate). Is there a structurally better design than continuing to hand-write
that selection logic into the renderer — specifically, comparing (A) extending
`derive_evidence_label`'s return value to carry a backing-record reference, vs.
(B) extracting a shared selection function — and is either compatible with this
build's own scope lock (spec.md AC11: "No edits to ... `derive_evidence_label` ...")?

## answer

**Recommend a minimized form of Option B — call it B′ — that requires ZERO edits to
`derive_evidence_label`'s body, and is fully compliant with AC11 as literally written,
with no spec amendment needed.**

### The decisive fact I found: the module already factors out everything the renderer needs

`derive_evidence_label`'s internal ladder (`product_dashboard.py:698-740`) does NOT
contain any logic that is uniquely private to it. Every predicate it uses to decide
"does this tier's proof exist" is already a separate, standalone, already-importable
piece of the same module:

- `_joined_valid_records(item, proof_records)` (line 651) — the join-key filter
  (product+claim match, `stale_or_valid=="valid"`). Already a free function, not a
  closure inside `derive_evidence_label`.
- `_is_genuine_live_smoke(record)` (line 670) — the live-smoke genuineness gate
  (non-demo, non-mock, `exit_code==0`, non-empty `output_hash`/`artifact_hashes`).
  Already a free function; `derive_evidence_label` line 727 calls it exactly like any
  other caller would (`any(_is_genuine_live_smoke(rec) for rec in valid)`).
- `LABEL_REQUIRED_PROOF_CLASS` (line 480) — a module-level dict already mapping
  `"mock-tested"->"unit_or_mock"`, `"build-clean"->"build_or_typecheck"`,
  `"preflight-pass"->"preflight"`, `"live-smoke-pass"->"live_smoke"` (deliberately
  omits `"ready"`, per its own comment: "never a valid single-record claim"). This is
  the EXACT tier→proof_class mapping AC7's tie-break needs for the bottom 3 tiers.
  It is currently consumed only by `validate_proof_record` (line 574, a *different*
  per-record self-consistency check) — `derive_evidence_label`'s ladder does not
  consult it (its ladder is a separate hardcoded `if/elif` chain on string literals).
  Reusing it in a new helper is safe, additive reuse of an existing constant, not a
  new coupling.
- `_parse_timestamp(value)` (line 512) — the ISO-8601 parser already used by
  `validate_proof_record` to decide staleness. Because `validate_proof_record` marks
  a record `stale` whenever its timestamp fails to parse (line ~597: `if parsed_ts is
  None: stale = True`), **every record that survives to `stale_or_valid=="valid"` is
  guaranteed to have a parseable timestamp** — the tie-break helper never needs to
  handle an unparseable timestamp among candidates.

Given that, a brand-new private function can implement the *entire* AC7 selection
rule — tier matching, live-smoke genuineness gating, and the "most recent timestamp,
ties by list order" tie-break — by calling only these four already-existing,
already-standalone pieces, **without adding one line to `derive_evidence_label`
itself**. It is a pure addition to the module (a new function + nothing else), which
squarely fits AC11's own carve-out language: "clearly-named new small private
helpers" are explicitly not in AC11's touched-file exclusion list; only
`derive_evidence_label`'s existing body is.

### Why this beats both of the dispatch's original options

**Option A (str-subclass / namedtuple return)** — REJECTED.
- Blast radius check requested by the dispatch: I found **no existing caller (production
  or test) that would break** on a str-subclass return — see Source list below for the
  full 20-call-site survey. Every use is `==`/`!=`/`in (tuple)`/`not in (tuple)`
  membership, or `.format()` string interpolation, or a dict `.get()` lookup
  (`EVIDENCE_LABEL_RANK.get(derived_label, 0)` in `wip_mismatch`) — all inherited
  str behavior a subclass gets for free as long as it doesn't override `__eq__`/`__hash__`.
  So Option A is *not* blocked by caller compatibility.
- But it is still **strictly worse than B′ on the axis that actually matters here**:
  it requires editing every one of `derive_evidence_label`'s 6 return statements
  (lines 731, 732, 735, 737, 739, 740) to wrap the plain string, which is a real,
  non-trivial diff to the exact function AC11 locks down — with zero compensating
  benefit, since B′ achieves the same outcome (renderer gets the backing record) with
  *no* diff to that function at all. Option A trades a bigger, riskier edit for no
  gain.

**Option B as originally framed (shared function ALSO called internally by
`derive_evidence_label`)** — unnecessary, and it's the one that literally trips AC11's
"No edits to ... `derive_evidence_label`" line (any edit to make it call the new
helper is a diff to that function, however small — AC11's stated verification method
is diff review against a fixed touched-list that does not include
`derive_evidence_label`). The refactor would in fact be *safe* in the classic
software-engineering sense (behavior-preserving extract-function, provable by the
existing 56 tests staying green untouched) — but it doesn't buy anything B′ doesn't
already get, because `derive_evidence_label`'s ladder already delegates its one
genuinely reusable predicate (`_is_genuine_live_smoke`) to a standalone function; there
is no second, independently-authored copy of that logic to *fix* by rewiring the
ladder itself. The only "duplication" risk in B′ is one narrow, explicitly-flagged
spot (below, under `constraints`), not the tier-matching or genuineness logic.

### What B′ does NOT resolve (be explicit with Oga about this)

Round 3's SECOND finding — the cited regression test (`cp-mismatch`/"stale" branch,
`wip_column="Done Verified"` making `cp-mismatch` fire unconditionally, and no AC
actually mandating the literal substring `"stale"`) — is a **test-citation and
AC-wording defect**, unrelated to record-selection design. No selection-logic design
(A, B, or B′) fixes it; it needs a direct AC7 text fix (cite a different existing test,
or accept a new isolating test written from scratch) independent of this brief's
recommendation.

## source

Everything below was opened and read this session (no fabricated line numbers):

- `loop-team/harness/product_dashboard.py`:
  - `_is_genuine_live_smoke` — lines 670-695 (full function read).
  - `derive_evidence_label` — lines 698-740 (full function + docstring read).
  - `EVIDENCE_LABEL_RANK` — lines 474-477.
  - `LABEL_REQUIRED_PROOF_CLASS` — lines 480-483, and its comment "AC4 per-label
    required proof_class (self-referential). 'ready' is absent -- never a valid
    single-record claim (needs 2-3 classes), so always rejected."
  - `_NOMINAL_TAG_PROOF_CLASSES` — lines 486-488.
  - `_parse_timestamp` — lines 512-527.
  - `_joined_valid_records` — lines 651-667 (full function read).
  - `validate_proof_record` — lines 530-608 (full function read), specifically line
    574-575 (`required_class = LABEL_REQUIRED_PROOF_CLASS.get(evidence_label)` /
    the nominal-tag skip) and the staleness block confirming `parsed_ts is None =>
    stale = True`.
  - `wip_mismatch` — lines 743-763 read for its `EVIDENCE_LABEL_RANK.get(derived_label, 0)`
    dict-key usage (the one place a derived label's *hashability* matters).
  - `_validate_item_records` — lines 884-903 (full function read) — confirms the
    renderer already holds the exact `valid_records` list `derive_evidence_label`
    receives, with zero extra plumbing needed for a B′-style call.
  - `_render_cp_card` — lines 906-982 (full function read) — the single production
    call site of `derive_evidence_label` is line 931; `derived` is used at lines 933
    (`wip_mismatch`), 949 (`== "ready"` literal comparison), and 954
    (`_esc(derived)` inside `.format()`).
- **Full-tree caller grep (blast radius for any return-shape change):**
  `grep -rn "derive_evidence_label" loop-team/` → exactly 2 files reference the name:
  `product_dashboard.py` (the 1 definition + 1 production call site, line 931) and
  `test_control_plane_dashboard.py` (20 references: 1 docstring mention + 19 actual
  calls, at lines 112(doc), 197(doc), 542, 551, 611, 618, 633, 640, 654, 753, 756, 798,
  802, 806, 971, 984, 1089, 1091, 1463, 1474(doc), 1480, 1488, 1512, 1543). A
  repo-wide `grep -rln "derive_evidence_label" .` (outside `loop-team/`) found it
  named only in `research/internal-audit-adhd-control-plane-dashboard-2026-07-12.md`
  (a docs mention, not a code caller). **No other file in the repo calls this
  function.** I read the actual assertion lines around several representative call
  sites (535-660, 1450-1543) and confirmed every one uses `==`, `!=`, `in (tuple)`,
  or `not in (tuple)` against the returned label — none does `isinstance`/`type(x) is
  str`/`json.dumps` on it. `grep -n "json.dump"` in both files found only 3 unrelated
  `json.dump(data, fh)`/`json.dump(status_data, fh)`/`json.dump([], fh)` calls, none
  touching a `derive_evidence_label` return value.
- `runs/2026-07-12_control-plane-dashboard-redesign/plan_check_log.md` — all 3 rounds
  read in full (the 6 gap records + the round-3 "pattern worth naming explicitly" note
  recommending either a Researcher dispatch or a cruder AC7).
- `runs/2026-07-12_control-plane-dashboard-redesign/spec.md` — read in full;
  AC7 (lines 131-155) and AC11 (lines 184-188, the scope lock: "No edits to
  `discover_control_plane_items`, `validate_proof_record`, `derive_evidence_label`,
  `wip_mismatch`, any `_cli_*_lookup` function... Verify by diff review: only
  `render_control_plane`, `_render_cp_card`, `render_html`'s signature+body, `STYLE`,
  and clearly-named new small private helpers are touched.") — this exact wording is
  what makes B′ (pure addition, zero diff to `derive_evidence_label`) the only
  option that needs no AC11 amendment.

## code_pattern

Pseudocode sketch — a new, fully independent private helper, added to
`product_dashboard.py` near `_joined_valid_records`/`_is_genuine_live_smoke` (not
inside `derive_evidence_label`, not editing it):

```python
def _select_backing_record(item, proof_records, derived_label):
    """Return the single validated proof record that backs `item`'s CURRENT
    `derived_label` (as computed by derive_evidence_label), for AC7's
    elapsed-time display -- or None when no record can be attributed (derived
    label is "Unverified", or -- degenerate, already implied -- zero valid
    records exist).

    Built entirely from derive_evidence_label's own already-standalone
    building blocks (_joined_valid_records, _is_genuine_live_smoke,
    LABEL_REQUIRED_PROOF_CLASS) so there is exactly one place each predicate
    is defined -- this function does not re-derive any of them, only
    recombines them for a different question ("which one", vs.
    derive_evidence_label's "does one exist").
    """
    valid = _joined_valid_records(item, proof_records)

    if derived_label == "ready" or derived_label == "live-smoke-pass":
        # Same gate derive_evidence_label itself uses for these two tiers
        # (product_dashboard.py:727) -- kept as a literal 2-value check here
        # because LABEL_REQUIRED_PROOF_CLASS deliberately omits "ready"
        # (see its own comment) and both tiers share the live_smoke gate.
        candidates = [r for r in valid if _is_genuine_live_smoke(r)]
    else:
        required_class = LABEL_REQUIRED_PROOF_CLASS.get(derived_label)
        if required_class is None:
            return None  # "Unverified" (or any future non-tier label): no backing record
        candidates = [r for r in valid if r.get("proof_class") == required_class]

    if not candidates:
        return None

    # Every "valid" record has a parseable timestamp (validate_proof_record
    # marks unparseable timestamps stale -- see source notes above), so this
    # never sees None. max() returns the FIRST maximal item on ties, which is
    # exactly "most recent, ties broken by list order" (Python docs guarantee).
    return max(candidates, key=lambda r: _parse_timestamp(r["timestamp"]))
```

Renderer call site (`_render_cp_card`, right after the existing line 931 —
additive, no signature change to `_render_cp_card` itself):

```python
derived = derive_evidence_label(item, valid_records, live_repo_health=live_health)
backing_record = _select_backing_record(item, valid_records, derived)
if backing_record is not None:
    age_text = _format_elapsed(_parse_timestamp(backing_record["timestamp"]))  # "2h ago"/"14d ago"
else:
    age_text = "age unknown"
```

(`_format_elapsed` is a small new formatting helper the Coder writes — turns a
`datetime` + "now" into `"2h ago"`/`"14d ago"` text; not shown here, purely a
render-layer string-formatting concern with no selection logic in it.)

## constraints

- **Do not add or modify anything inside `derive_evidence_label`'s body.** B′
  requires zero diff there; if the Coder finds itself editing that function for
  any reason while implementing AC7, that's a signal it has drifted off B′ and
  back toward the pattern all 3 plan-check rounds already rejected.
- **The `"ready"`/`"live-smoke-pass"` two-value literal check inside
  `_select_backing_record` is a deliberate, small, DOCUMENTED exception** — it
  duplicates (in the weak, single-line sense) the fact that both tiers share the
  live-smoke gate in `derive_evidence_label`'s own ladder (line 727). This is the
  one place true parallel maintenance exists between the two functions. Mitigate
  by a code comment in `_select_backing_record` that explicitly cross-references
  `derive_evidence_label`'s docstring/line 727, so a future edit to the ladder's
  tier structure is more likely to prompt a matching edit here. This is a much
  smaller and more localized risk than the 3-rounds' worth of full ladder-logic
  duplication that was being spec'd directly into the renderer.
- **`LABEL_REQUIRED_PROOF_CLASS`'s tier-name coupling to `derive_evidence_label`'s
  ladder strings is pre-existing**, not introduced by this design — it already
  says "self-referential" in its own comment and is already relied on by
  `validate_proof_record`. B′ adds a second reader of that same dict; it does not
  create a new coupling.
- **Every "valid" record is guaranteed to have a parseable `timestamp`.** Do not
  add None-handling for `_parse_timestamp` inside the candidates list in
  `_select_backing_record` — it would be dead code, and if it ever DID trigger it
  would mean a `validate_proof_record` invariant broke elsewhere (a bug to
  surface, not silently swallow).
- **AC12 / AC1 regression bar**: because `derive_evidence_label` is untouched and
  its return value/type/contract is unchanged, all 19 existing test call sites
  against it (`test_control_plane_dashboard.py`) need zero edits for this design
  — the new coverage AC7 requires is purely additive tests of
  `_select_backing_record` and/or the rendered elapsed-time text, not a rewrite of
  existing assertions.
- **Naming**: call the new helper something AC11-obviously "small and new" (e.g.
  `_select_backing_record`) so a diff-reviewer immediately recognizes it as the
  kind of addition AC11's own carve-out anticipates, not a renamed/refactored
  piece of `derive_evidence_label`.

## not_found

- I did not find, and did not look for, a pre-existing test that isolates AC7's
  new "age unknown" branch independent of `cp-mismatch` (round 3's second gap).
  That is a distinct defect in AC7's test citation/wording that this brief's
  design does not fix — it needs a direct spec-text or Test-writer decision, out
  of scope for the record-selection question I was dispatched to research.
- I did not check whether any file OUTSIDE `loop-team/` (this repo has no other
  Python packages importing `product_dashboard`) could ever import
  `derive_evidence_label` in the future — the grep above covered the whole repo
  as it exists today (2026-07-12), not hypothetical future callers.
