# PACE topology replay

This bounded experiment replays five historical Codex Desktop orchestration
transcripts against a proposed single-root topology. It measures deterministic
control-action reductions. It does not execute agents, estimate unobserved
causal wall-clock savings, authorize production changes, or produce an IID
sample suitable for PACE acceptance.

## Source authority

`manifest.json` seals the exact transcript prefix used by each case with:

- manifest version;
- extracted one-based record count `N`;
- SHA-256 of the exact original bytes through record `N`, including original
  line terminators;
- a binding hash over version, `N`, prefix hash, case, and source path.

`fixtures/source_seals.json` additionally records the canonical SHA-256 of
every JSON record in each sealed prefix. `verify_sources.py` permits records
appended after `N` only as the visible status `APPENDED_AFTER_SEAL`. Mutation,
reordering, deletion, or truncation within the prefix fails. Once generated,
`extract_cases.py` refuses to overwrite any non-identical frozen artifact.

Every counted action resolves to a full sealed-prefix SHA-256, one-based record
index, canonical record SHA-256, and native call ID. A call start and output may
share a native `call_id`, but remain distinct evidence because their indexes
and record hashes differ.

## Deterministic rules

- Polls and heartbeats reduce action counts only. Their blocked durations are
  never counted as saved time.
- Time savings require labelled baseline-only active spans on the causal
  critical path, with retained-work overlap removed and variant overhead
  subtracted.
- Missing lifecycle endpoints or overhead are `unmeasurable_ms`.
- Historical safety is computed only from source-backed topology actions and
  their evidence pointers. Missing mandatory proof is `UNMEASURABLE`; synthetic
  safety fixtures cannot authorize historical cases.
- Positive completion evidence uses a strict terminal grammar: final
  `LOOP_GATE: PLAN_PASS` or final explicit `VERDICT: PASS`. Incidental `PASS`,
  focused-test status, false-pass wording, provisional failures, or any mixed
  positive/negative verdict record is not authoritative.
  Negative verdicts are parsed as a normalized key/value grammar across
  verdict, status, result, summary, audit, and overall fields, including
  whitespace, hyphen, and underscore variants—not as a finite phrase list.
  Common Markdown list markers and emphasis/code decoration are removed
  structurally before negative parsing, so formatting cannot hide a verdict.
- Safety is absolute: an unsafe result is rejected even if faster.
- Simulation, timing, statistical, and adoption verdicts are separate.
- Five historical non-IID replays cannot produce PACE acceptance.

## Reproduce

Run from `<HOME>/Claude/loop`:

```text
pytest -q loop-team/experiments/pace_topology_replay/test_simulator.py
python3.10 -u loop-team/experiments/pace_topology_replay/extract_cases.py
python3.10 -u loop-team/experiments/pace_topology_replay/verify_sources.py
python3.10 -u loop-team/experiments/pace_topology_replay/scorer.py
shasum -a 256 loop-team/experiments/pace_topology_replay/fixtures/simulation_result.json
```

See `RESULT.md` for the executed outcome and limitations.
