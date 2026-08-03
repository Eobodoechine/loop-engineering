# Phase 1 — Gate Contract Registry Extraction

## Goal
Build `harness/gate_contract_registry.py` that walks `hooks/` + `harness/` and, for each gate script, emits a JSON record of its input contract: required files/paths it reads, required fields/keys it expects, regexes/literals it matches, exit-code semantics, and every distinct rejection/error string it can emit.

Output: `gate_contracts.json` — one record per gate. Seed this registry with the already-confirmed `spec_bound_verifier_credit` contract record from `research/spec-bound-verifier-coder-credit-gate-marker-2026-07-29.md` rather than re-deriving it.

## Second deliverable — coverage matrix
For every contract element in `gate_contracts.json`, grep `orchestrator.md`, `roles/*.md`, and `TEAM_RELATIONS.md` for that element. Produce `gate_contract_coverage.md` — contract element x gate x whether/where it's documented. Zero-hit elements are flagged `UNDOCUMENTED`.

Note: `spec_bound_verifier_credit`'s SPEC:/SPEC_SHA256 contract IS documented (orchestrator.md ~line 632), so it should NOT be flagged UNDOCUMENTED in the coverage matrix — it's a useful calibration case showing a gate that's H5 (delivery/condensed-summary drift) rather than H1 (pure discovery failure).

## Constraints
- Read-only with respect to existing gate behavior — must not modify any existing gate script.
- The registry script is checked into `harness/gate_contract_registry.py`.
- Confirm the 14-gate inventory and the undocumented-gate list against the actual current tree rather than trusting the 2026-07-29 diagnosis plan verbatim — code moves faster than docs, that's the whole thesis.

## Acceptance criteria
- `gate_contract_registry.py` runs successfully against the live repo and produces valid JSON for every gate file found.
- Spot check: `spec_bound_verifier_credit.py`'s full rejection-string list (21 distinct strings per the 07-29 dossier) appears as distinct entries.
- `gate_contract_coverage.md` correctly flags the previously-known-undocumented gates (`fixplan_closure_lint`, `status_claim_audit`, `evidence_ledger`, `reality_gate`, `lens_completion_barrier`, `closure_freshness_sweep`, `plan_check_records`) as `UNDOCUMENTED`, correctly does NOT flag `spec_bound_verifier_credit` or `reconcile_gap_records.py` as fully undocumented.