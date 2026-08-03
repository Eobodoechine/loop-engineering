# Phase-1 Gate-Contract Registry — Revised Implementation Plan (2026-08-02)

## 0. Status, authority, and boundary

This is a **pre-implementation design revision**. No registry code, gate, hook, runner,
or producer-facing document has been changed by this plan. The earlier outline at
`loop-team/specs/gate-diagnosis-phase1-contract-registry.md` remains provenance only: its
acceptance criterion says the credit gate has 21 rejection strings, while the current
credit-gate dossier enumerates **30**. This plan replaces that ambiguous requirement; it
does not edit the earlier artifact or retroactively claim it was implemented.

The source of truth for an extracted contract is the current, raw bytes of the in-scope
Python source. The registry is a generated, reviewable projection of that source. Producer
documents are evidence for *documentation coverage only*; they never override code.
Research is a manual-overlay input with pinned provenance, never an authority that can
silently override a changed source file.

This slice adds a read-only registry and its tests. It must not change hook decisions,
hook installation, runner behavior, orchestrator behavior, role prompts, or any existing
architecture. It is not the later repair of a discovered conflict.

## 1. V1 scope manifest: complete, versioned, and explicit

`gate-contract-registry.v1` is a bounded inventory, not a filename glob and not the
historical “14 gates” estimate. At plan authoring it classifies **51 pre-existing non-test
Python sources** under `hooks/` and `loop-team/harness/`: the 30 included sources in section
1.1 and the 21 path-specific exclusions in section 1.2. The implementation must put those
exact paths and their category in `SCOPE_MANIFEST_V1` and preserve those baseline counts.

The registry implementation is necessarily a new non-test Python source inside one scanned
directory. To make `--check` satisfiable without letting the registry audit itself, the
manifest must also contain the exact path
`loop-team/harness/gate_contract_registry.py` with `exclude_reason:
"registry_substrate"`. This is a principled self-exclusion: the file generates and validates
the projection but does not itself consume or enforce a Loop producer-output contract; making
its own AST extraction a gate record would make the source-of-truth checker circular. It is
not a wildcard exemption and cannot cover any sibling.

Every scanned Python path must receive exactly one classification: an exact manifest entry, or
the explicit `test_module` classification when its repository-relative basename matches
`test_*.py`. `test_module` is a closed-vocabulary exclusion reason, not an implicit skip; it
therefore explicitly covers the committed
`loop-team/harness/test_gate_contract_registry.py` and any future conventional test source.
Every other newly discovered non-test source is an `UNCLASSIFIED_SOURCE` check failure until
an owner deliberately creates a new manifest version. There is no implicit “helper files do
not count” rule.

### 1.1 Included contract sources (30)

| Category | Paths |
|---|---|
| Hook entry/policy | `hooks/loop_guard.py`, `hooks/loop_stop_guard.py`, `hooks/pre_tool_use_oga_guard.py`, `hooks/subagent_stop_gate.py`, `hooks/repo_health_dispatch_gate.py`, `hooks/spec_bound_verifier_credit.py` |
| Active hook shared policy component | `hooks/adversarial_review_scan.py`, `hooks/closure_touch_scan.py`, `hooks/commit_scope_scan.py`, `hooks/dispatch_check_presence.py`, `hooks/micro_step_gates.py`, `hooks/slop_gate.py`, `hooks/verifier_hygiene_scan.py` |
| Uninstalled shared-policy candidate | `hooks/cod_state.py` |
| Harness gate/check | `loop-team/harness/closure_freshness_sweep.py`, `loop-team/harness/commit_diff_reread.py`, `loop-team/harness/evidence_ledger.py`, `loop-team/harness/fixplan_closure_lint.py`, `loop-team/harness/lens_completion_barrier.py`, `loop-team/harness/plan_check_records.py`, `loop-team/harness/plan_size_governor.py`, `loop-team/harness/plancheck_saturation.py`, `loop-team/harness/reality_gate.py`, `loop-team/harness/reconcile_gap_records.py`, `loop-team/harness/repo_health_gate.py`, `loop-team/harness/research_authenticity_check.py`, `loop-team/harness/spec_revision_diff.py`, `loop-team/harness/stall_detector.py`, `loop-team/harness/status_claim_audit.py`, `loop-team/harness/verify.py` |

An active “shared policy component” is included even when it lacks a CLI because a current
parent hook enforces its result. Its `ACTIVE` record must name its actual, installed owning
callers and source spans proving both the import/reference and the invocation/use; it is not
allowed to masquerade as an independent hook entry point. A module may be advisory; advisory
elements remain registry records, with `enforcement_mode: "advisory"`, rather than being
omitted.

`hooks/cod_state.py` is deliberately **not** an active shared policy component. The live audit
establishes zero current caller/import references: its P1 commit added only the module and
documents, and its orchestration text says P1 remains instructional until a hook is installed.
V1 must therefore record it as `lifecycle_status: "UNINSTALLED_ORPHANED"`, with
`enforcement_mode: "uninstalled"`, `owning_callers: []`, `caller_evidence: []`, and an explicit
`lifecycle_reason` naming the zero-current-caller finding. It must not invent a future caller,
count instructional prose as installation evidence, or expose the record as an active gate.

Ownership evidence defaults to `direct_python_reference`. The sole V1 active-component
exception is `hooks/slop_gate.py`, whose installed owner is
`hooks/loop_stop_guard.py:1930-1934`: that caller invokes it through `subprocess.run` with an
`os.path.join(..., "slop_gate.py")` command entrypoint. Its only Python import is from excluded
`hooks/slop_calibrate.py`, which is calibration code and is **not** an owner. The V1 manifest
must therefore give `hooks/slop_gate.py` the closed
`allowed_ownership_evidence_types: ["subprocess_entrypoint"]`; every other `ACTIVE` shared
policy component has `allowed_ownership_evidence_types: ["direct_python_reference"]`. No
record receives a broad “subprocess counts as ownership” exemption.

### 1.2 Explicit exclusions

The V1 manifest must also list each current non-test source that is excluded, with exactly
one reason from this closed vocabulary:

* `fixture_only` — `hooks/_codex_fixture_builders.py`, `hooks/codex_hook_stdin_capture.py`.
* `normalization_or_logging` — `hooks/codex_transcript_adapter.py`, `hooks/loop_logger.py`.
* `producer_helper_or_calibration` — `hooks/plan_check_credit_output.py`,
  `hooks/slop_calibrate.py`, `loop-team/harness/run_and_record.py`.
* `worker_or_dashboard_runtime` — `loop-team/harness/claude_coder_runner.py`,
  `loop-team/harness/claude_role_runner.py`, `loop-team/harness/dashboard.py`,
  `loop-team/harness/linear_reporter.py`, `loop-team/harness/log.py`,
  `loop-team/harness/product_dashboard.py`.
* `read_only_audit_or_reconciliation_utility` — `loop-team/harness/full_history_scan.py`,
  `loop-team/harness/identity_audit.py`, `loop-team/harness/path_removal.py`,
  `loop-team/harness/reconcile_manifest.py`, `loop-team/harness/research_sources_index.py`,
  `loop-team/harness/tree_verify.py`, `loop-team/harness/verified_mirror_clone.py`.
* `external_smoke_executor` — `loop-team/harness/live_smoke.py` (it executes a supplied
  external surface; it does not define a Loop producer-output contract).
* `registry_substrate` — `loop-team/harness/gate_contract_registry.py` only. It is the
  explicitly named generator/checker self-exclusion described in section 1, not a contract
  source and not permission to exclude another implementation module.
* `test_module` — any scanned `test_*.py`, including
  `loop-team/harness/test_gate_contract_registry.py`. Tests exercise registry behavior but do
  not define producer-facing contracts; the classifier must still report each such path as
  `test_module` rather than omit it from enumeration.

The test must compare the filesystem enumeration with the manifest/rule classification, so
the list above cannot become prose-only or silently stale. It must separately assert the
preserved 51-source baseline (30 included + 21 path-specific pre-existing exclusions), the
single exact `registry_substrate` entry after implementation, and the explicit
`test_module` classification of the new test file. If a current non-test file other than the
named registry substrate is missing from the manifest, the implementer must add an explicit
entry in a new version before proceeding; they must not infer an exclusion from its name.

## 2. Files and exact generated locations

Create only these new registry-slice paths:

| Purpose | Exact path |
|---|---|
| Extractor/CLI | `loop-team/harness/gate_contract_registry.py` |
| V1 scope manifest and manual overlay | `loop-team/contract_registry/v1/scope_manifest.v1.json`, `loop-team/contract_registry/v1/manual_overlays/spec_bound_verifier_credit.v1.json` |
| Committed machine registry | `loop-team/contract_registry/v1/gate_contracts.v1.json` |
| Committed human coverage projection | `loop-team/contract_registry/v1/gate_contract_coverage.v1.md` |
| Test module and fixtures | `loop-team/harness/test_gate_contract_registry.py`, `loop-team/harness/testdata/gate_contract_registry/` |

The CLI defaults to the two committed output paths above when invoked from the repository
root. It must not write `gate_contracts.json`, `gate_contract_coverage.md`, or a cache into
the repository root, `hooks/`, `/tmp`, or a user home directory. `--out-json` and
`--out-coverage` are allowed only for test/output isolation; `--check` writes nothing.

## 3. Data model and static-extraction limits

The extractor parses source with `ast.parse`; it must neither import nor execute a gate,
run a subprocess, inspect a live transcript, nor call a hook. Each registry record contains:

```json
{
  "schema_version": "gate-contract-registry.v1",
  "relative_path": "hooks/example.py",
  "category": "hook_entry",
  "enforcement_mode": "blocking|advisory|mixed|uninstalled|unknown",
  "lifecycle_status": "ACTIVE|UNINSTALLED_ORPHANED|WIRING_UNRESOLVED",
  "owning_callers": [],
  "caller_evidence": [],
  "allowed_ownership_evidence_types": ["direct_python_reference"],
  "lifecycle_reason": "<required for a non-ACTIVE shared-policy record>",
  "source_sha256": "<sha256 of raw file bytes>",
  "elements": [
    {
      "element_id": "<stable path-qualified id>",
      "kind": "input_path|input_field|input_literal|output_field|exit_semantics|rejection_reason|precondition",
      "value": "<normalized value>",
      "source_spans": [{"line_start": 1, "line_end": 1}],
      "extraction": "ast_literal|manual_overlay",
      "completeness": "observed|manual_exhaustive|unresolved_dynamic"
    }
  ],
  "unresolved_dynamic_sites": [],
  "manual_overlay": null
}
```

An **element** is one atomic, producer-observable contract fact: a required incoming field or
literal, a required output field/literal, a required path, an exit/permission decision, a
precondition, or a rejection reason. A gate is the record that owns zero or more elements.
Strings that are comments, docstrings, generic log messages, grant-side annotations, or test
fixtures are not rejection reasons.

### 3.1 Shared-component lifecycle truth

`lifecycle_status` is a separate fact from documentation coverage and from an element’s
`enforcement_mode`. `caller_evidence[].type` is also closed: only
`direct_python_reference` and `subprocess_entrypoint` are valid. Its lifecycle values and
invariants are:

* `ACTIVE` — for a `shared_policy_component`, `owning_callers` and `caller_evidence` are both
  non-empty. Every cited caller is an in-scope active hook entry/component. For the default
  `direct_python_reference` type, each evidence item supplies `caller_relative_path`, an
  import/reference source span, and a later use/call source span. A docstring, a README, a
  future installation instruction, or a bare unused import cannot satisfy this invariant. The
  manifest permits this type for every active shared component except `hooks/slop_gate.py`.
* `subprocess_entrypoint` — permitted only when the target record’s manifest allow-list names
  this type; V1 permits it only for `hooks/slop_gate.py`. Its single static evidence item must
  contain all of: `caller_relative_path`, `caller_source_sha256`,
  `subprocess_call_line_start`, `subprocess_call_line_end`, `entrypoint_relative_path`,
  `command_literal`, and `command_literal_line`. It is valid only when one AST
  `subprocess.run` call in that caller has a command-vector expression containing an
  `os.path.join(...)` expression whose final literal argument equals `command_literal`, and
  that literal resolves relative to the caller’s source directory to exactly
  `entrypoint_relative_path`. For V1, the literal is exactly `"slop_gate.py"` and the resolved
  entrypoint is exactly `hooks/slop_gate.py`. A bare text match, a standalone `os.path.join`, a
  command assembled dynamically, a different subprocess API, or an import from the excluded
  calibrator cannot establish this type. The source spans and caller hash make the provenance
  deterministic and force regeneration when the launcher moves or changes.
* The strict non-empty owner/caller invariant applies to every `ACTIVE` component. The
  subprocess rule is a narrowly typed installed-owner proof for the sole manifest-approved
  exception; it does not relax the direct-reference rule for any other active record.
* `UNINSTALLED_ORPHANED` — the source declares/implements shared policy but all current
  in-scope caller sources have zero import/reference edges to it. It has exactly empty owner and
  caller-evidence lists, `enforcement_mode: "uninstalled"`, and a non-empty
  `lifecycle_reason`. It is rendered as an installation gap, never as an advisory or blocking
  active record. `hooks/cod_state.py` is the required V1 instance.
* `WIRING_UNRESOLVED` — static extraction finds dynamic/reflection-based wiring that prevents a
  sound zero-edge conclusion but cannot prove an installed import-and-use pair. It has no active
  owner claim, `enforcement_mode: "unknown"`, and a non-empty `lifecycle_reason` plus the
  unresolved source spans. It must not be downgraded to `UNINSTALLED_ORPHANED` merely because
  the extractor cannot understand its wiring.

The extractor must build caller evidence from current source only. For lifecycle purposes it
scans the included hook-entry/component sources for a direct AST import/reference to the shared
module and a use/call after that reference; the record is `ACTIVE` only when both are present.
No plan may assign an owner based on desired future architecture. This lifecycle scan is
read-only and does not import or execute either side of an edge.

Static extraction is deliberately limited. It may record literal `argparse` options,
dictionary subscript/`get` keys, literal regex patterns, literal path names, literal
`sys.exit` values, and literal strings in branch-local failure/deny returns with their source
spans. It must label f-strings, concatenated dynamic values, imported constants, reflection,
computed regular expressions, and semantic reachability it cannot prove as
`unresolved_dynamic_sites`; it must not guess a literal, claim exhaustiveness, or label an
unknown field as undocumented. The generated registry is therefore an observable static
inventory, not a symbolic executor or a runtime conformance proof.

## 4. Credit-gate manual overlay: exact 30-string rule

`hooks/spec_bound_verifier_credit.py` needs a manual overlay because its contract spans
multiple internal functions, reused reasons, a templated reason, and a defensive fallback.
The V1 overlay must pin all of the following values:

* `target_relative_path: "hooks/spec_bound_verifier_credit.py"` and
  `target_source_sha256: "dbaee74f59aa15e6db9795053b4f2a536a7d6f17c0336dd0808ccaca3f28ed75"`.
* Research provenance only: `research/spec-bound-verifier-coder-credit-gate-marker-2026-07-29.md`
  with raw-byte SHA-256
  `19199513bc80239d8c81bc2cf7e930e1b7353134a60c6ba7930f89c26a2cad81`.
* Exactly 30 unique, ordered literal **reason strings**, using the exhaustive all-functions
  scope in the cited dossier’s section 5. This includes the defensive-only `missing spec info`
  fallback and the `%s` template; it includes reused literals only once. It excludes success
  `""`, `authorized by a valid evidence-bound PLAN_PASS; ...`, and
  `authorized by cross-turn verifier_pass flag`, which are grant annotations rather than
  rejection reasons.

The overlay must carry the full literal list, its scope sentence, and a source-span map for
each entry. It must not inherit the obsolete “21 distinct strings” claim from the older Phase-1
outline. Its assertion is: **all distinct literal reason strings returned anywhere by the
module’s contract functions at this pinned source revision**, not “only strings reachable from
a direct Verifier pre-dispatch deny.”

The live Python source is authoritative. The research hash is provenance for the human
enumeration only. `--generate` and `--check` must refuse to merge this overlay and exit
nonzero with `MANUAL_OVERLAY_SOURCE_DRIFT` if the target source hash differs, or
`MANUAL_OVERLAY_DOSSIER_DRIFT` if the pinned research artifact differs. A source change requires
a deliberate re-audit: update the overlay’s target hash, source spans, the 30-entry assertion
(or its justified changed count), and the generated outputs in one reviewed change. No command
may silently retain an old 30-entry record merely because a similarly named file exists.

## 5. Canonical serialization and drift behavior

All SHA-256 values are lowercase hex over raw UTF-8 bytes unless a field says otherwise.
The registry canonical JSON encoding is exactly
`json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`
encoded as UTF-8, with **no trailing newline**. `source_sha256` is over raw source bytes;
`inventory_sha256` is over the canonical ordered V1 manifest; `record_sha256` is over the
record excluding its own hash field; `registry_sha256` is over the registry document excluding
its own hash field. Lists are ordered by manifest path, then element ID; set-like literals are
deduplicated before ordering. The committed `.json` file itself is the canonical bytes, not a
pretty-printed near-equivalent.

`gate_contract_coverage.v1.md` is generated from that same in-memory registry, records the
`inventory_sha256` and `registry_sha256` in its header, and has a deterministic path/element
order. It is a projection: manual edits are detected by `--check` rather than accepted as an
alternate source. Its per-gate table must render `lifecycle_status`, actual caller paths (or
the explicit empty list), and `lifecycle_reason`; for an `ACTIVE` shared component it must also
render the ownership-evidence type and its source/line/command-literal provenance.
`UNINSTALLED_ORPHANED` must render as `INSTALLATION GAP`, not as a coverage or enforcement PASS.

Drift is fail-closed and has distinct causes:

1. Candidate source, manifest, or documentation-source bytes change: regeneration computes a
   new result; `--check` fails `STALE_GENERATED_REGISTRY` until both committed projections are
   regenerated and reviewed.
2. A target source or research provenance pinned by a manual overlay changes: generation itself
   fails with the corresponding `MANUAL_OVERLAY_*_DRIFT`; updating generated files alone is not
   sufficient.
3. A current non-test source is not classified by `scope_manifest.v1.json` (other than the
   one exact `registry_substrate` path): `--check` fails `UNCLASSIFIED_SOURCE`; an owner must
   create the next manifest version rather than quietly widen V1 by a glob. A `test_*.py`
   source is reported under the closed `test_module` classification; it is not silently
   discarded.

## 6. Documentation coverage semantics

The fixed V1 producer-facing documentation corpus is `RUN.md`, `VERIFIER.md`,
`loop-team/orchestrator.md`, `loop-team/TEAM_RELATIONS.md`, and every
`loop-team/roles/*.md`. Tests, research dossiers, generated registry files, `fix_plan.md`, and
gate source are deliberately excluded from this corpus. A coverage hit includes file path,
line range, and source-file hash.

Element documentation status is one of:

* `DOCUMENTED_EXACT` — an allowed document gives the exact normalized field/literal/path or
  exit/permission form as a producer instruction, with a cited line.
* `REFERENCED_NOT_DOCUMENTED` — it names the gate or a generic policy but not this element’s
  required shape. This does **not** count as coverage.
* `UNDOCUMENTED` — no allowed document has an exact producer-facing instruction for the element.
* `NOT_APPLICABLE` — a record metadata item, not a producer-observable contract element.
* `UNKNOWN_DYNAMIC` — extraction could not statically establish the element. This is neither
  documented nor undocumented and prevents a complete-coverage claim.

Gate-level documentation status is an aggregation and must never be copied onto every element:

* `DOCUMENTED` only when every applicable, known element is `DOCUMENTED_EXACT` and there are no
  `UNKNOWN_DYNAMIC` sites.
* `PARTIALLY_DOCUMENTED` when at least one applicable known element is exact but another is
  undocumented/referenced-only, or extraction is incomplete.
* `REFERENCED_ONLY` when the gate is mentioned but no applicable element is exact.
* `UNDOCUMENTED` when no applicable known element is exact and the gate has no permitted-doc
  reference.
* `NO_EXTRACTABLE_CONTRACT` when the included source has no producer-facing static element;
  it is not a claim that its behavior is documented or undocumented.

The expected credit-gate aggregate in V1 is `PARTIALLY_DOCUMENTED`, not fully undocumented and
not fully documented. This preserves its H5 calibration value without allowing a generic
orchestrator reference to erase its undocumented literal contract elements.

## 7. Implementation sequence

1. Add the V1 scope manifest, the credit manual overlay, and test fixtures first. The manifest
   test must prove total classification of the live two directories before extractor behavior is
   written.
2. Write failing tests for AST-only parsing, canonical serialization, source ordering, generic
   element extraction, unknown dynamic sites, no-import/no-execution behavior, output placement,
   coverage-status aggregation, and all drift failures.
3. Implement the stdlib-only extractor/CLI. It reads paths rooted at an explicitly supplied or
   discovered repository root, rejects path traversal outside that root, and validates every
   overlay against raw bytes before merging it.
4. Generate and commit the two projections with `--generate`; run `--check` immediately from a
   clean process. Do not hand-edit a generated output to make the check pass.
5. Independently inspect the 30 credit-gate reasons, their overlay source spans, and the
   generated `PARTIALLY_DOCUMENTED` result. The independent verification must read both current
   source and output; a passing extractor test alone is insufficient for the manual assertion.

## 8. Required tests and acceptance commands

The new test module must include, at minimum:

* exact V1 inclusion set and total include/exclude classification of the live source tree:
  preserve 30 included and 21 path-specific excluded pre-existing non-test sources, classify
  `gate_contract_registry.py` only as `registry_substrate`, and classify the committed test
  module as `test_module`;
* lifecycle fixtures proving an active shared component requires an actual import/reference plus
  later use/call evidence and non-empty owning callers; a bare import and instructional prose
  do not qualify. This direct-reference invariant remains mandatory for every active record
  except the explicitly manifest-approved `hooks/slop_gate.py` subprocess entrypoint;
* the live V1 `hooks/slop_gate.py` record is `ACTIVE` only with one
  `subprocess_entrypoint` evidence item for `hooks/loop_stop_guard.py`, including its current
  `subprocess.run` source span (lines 1930-1934 at plan authoring), caller source hash,
  `os.path.join` command-literal span, literal `slop_gate.py`, and resolved target
  `hooks/slop_gate.py`. A synthetic bare string, standalone join, dynamic command, alternate
  subprocess API, or the excluded `slop_calibrate.py` import must fail ownership validation;
  another active component attempting this evidence type must also fail;
* the live V1 `hooks/cod_state.py` record is `UNINSTALLED_ORPHANED`, with exactly empty owners
  and caller evidence, `enforcement_mode: "uninstalled"`, a non-empty zero-current-caller
  reason, and an `INSTALLATION GAP` coverage rendering; no test may provide or infer a future
  owner to make it active;
* a dynamic-wiring fixture is `WIRING_UNRESOLVED`, not falsely `ACTIVE` or
  `UNINSTALLED_ORPHANED`; every `ACTIVE` shared-policy record still fails the test if either
  owner list or caller-evidence list is empty;
* a synthetic module showing every supported AST element type, plus one dynamic expression that
  is emitted only as `UNKNOWN_DYNAMIC`/`unresolved_dynamic_sites`;
* proof that parsing a fixture with import-time side effects neither imports nor executes it;
* byte-identical JSON across two generation runs, stable IDs/order, valid `record_sha256` and
  `registry_sha256`, and no trailing newline in canonical JSON;
* `--check` detects one-byte source, manifest, documentation, and generated-output drift;
* target-source and dossier-provenance manual-overlay mismatch each fail before an overlay is
  merged;
* the credit overlay has exactly 30 unique strings in documented order, includes `missing spec
  info` and the `%s` reason, and excludes all three grant-side annotations;
* an element-level coverage fixture proving that a generic gate mention is
  `REFERENCED_NOT_DOCUMENTED`, while a gate aggregate may still be
  `PARTIALLY_DOCUMENTED`.

Required acceptance commands, run from `<HOME>/Claude/loop`:

```bash
python3 -m pytest loop-team/harness/test_gate_contract_registry.py -q
python3 -m pytest hooks/test_spec_bound_verifier_credit.py loop-team/harness/test_gate_contract_registry.py -q
python3 loop-team/harness/gate_contract_registry.py --repo-root . --generate
python3 loop-team/harness/gate_contract_registry.py --repo-root . --check
python3 -c 'import json, pathlib; json.loads(pathlib.Path("loop-team/contract_registry/v1/gate_contracts.v1.json").read_text(encoding="utf-8"))'
```

The slice is acceptable only if all five commands exit 0, the generated JSON is canonical and
valid, the test proves the 30-string manual overlay, and `git diff --check` is clean. A green
test suite without a green `--check`, or a generated registry with a stale manual overlay, is
not acceptance.

## 9. Non-goals and deferred work

This slice does **not** repair any H1–H5 finding, reconcile conflicting Proof/gap-record
schemas, inject contracts into agent dispatches, replay historical transcripts, modify a gate’s
decision or error wording, alter `hooks/`, `loop-team/runner/`, `loop-team/orchestrator.md`,
role files, `RUN.md`, `VERIFIER.md`, or `fix_plan.md`, run an external/live smoke, or claim that
all gate contracts are semantically complete. Those may become separately planned slices after
the registry produces machine-backed evidence. No `fix_plan.md` entry is warranted for this
known planning gap unless implementation proves a new, distinct framework defect.

## 10. Concise plan-check input

```text
PLAN-CHECK INPUT — gate-contract-registry.v1
Scope: add only the registry extractor, V1 manifest/manual overlay, deterministic generated
registry/coverage files, and tests at the exact paths in section 2. Do not edit existing gates,
runners, orchestration, roles, or framework policy documents.

Acceptance criteria:
1. The V1 manifest preserves the 51 pre-existing non-test sources (30 included and 21
   path-specific exclusions), explicitly self-excludes only
   loop-team/harness/gate_contract_registry.py as registry_substrate, and reports the
   committed test module via the closed test_module rule. Any other new non-test source fails
   UNCLASSIFIED_SOURCE.
2. Extraction is AST-only, never imports/executes gate code, and represents dynamic uncertainty
   instead of inventing contract facts.
3. Active shared-policy components retain a non-empty, source-proven owner/caller invariant;
   `hooks/cod_state.py` alone is represented as `UNINSTALLED_ORPHANED` with no invented future
   caller, while dynamic wiring is `WIRING_UNRESOLVED`.
4. `hooks/slop_gate.py` is ACTIVE through the sole manifest-approved
   `subprocess_entrypoint` proof from `hooks/loop_stop_guard.py`; its fixed AST launcher,
   line/span, caller hash, command literal, and resolved target are rendered and tested, while
   every other active shared component retains direct Python ownership proof.
5. The credit overlay pins source hash dbaee74f59aa15e6db9795053b4f2a536a7d6f17c0336dd0808ccaca3f28ed75,
   dossier hash 19199513bc80239d8c81bc2cf7e930e1b7353134a60c6ba7930f89c26a2cad81, and exactly the 30
   all-functions literal reasons; both source and dossier drift fail before merge.
6. Canonical output uses the stated JSON bytes/hash rules; --check catches source, manifest,
   docs, output, and unclassified-source drift without writing files.
7. Coverage distinguishes element status from gate aggregate and never turns a generic mention
   into element documentation; credit gate is PARTIALLY_DOCUMENTED.
8. The commands in section 8 pass, and no existing gate/runner/orchestrator architecture changes.

Reject the plan if candidate classification, manual-overlay authority/drift behavior, output
locations, element-versus-gate status aggregation, extractor limits, or acceptance commands
remain implicit.
```
