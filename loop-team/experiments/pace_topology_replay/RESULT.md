# PACE topology replay result

## Outcome

The deterministic variant removed 1,306 of 1,757 recorded control actions,
leaving 451 actions: a 74.331246% action reduction.

| Decision surface | Result |
|---|---:|
| Historical cases | 5 |
| Baseline actions | 1,757 |
| Variant actions | 451 |
| Action savings | 1,306 (74.331246%) |
| Timing cases with required telemetry | 0/5 |
| Timing result | `INSUFFICIENT_TELEMETRY` |
| Simulation verdict | `INSUFFICIENT_EVIDENCE` |
| Statistical verdict | `NOT_APPLICABLE` |
| Adoption verdict | `NOT_APPLICABLE` |
| PACE acceptance | `false` |

No case positively proves every mandatory topology and safety invariant under
the strict terminal-verdict grammar. All five are `UNMEASURABLE`, so the
aggregate verdict is `INSUFFICIENT_EVIDENCE`. No absent stage or incidental
`PASS` word is inferred as authority.

## Executed proof

Regression and source verification:

```text
$ pytest -q loop-team/experiments/pace_topology_replay/test_simulator.py
............................                                             [100%]
58 passed in 0.11s

$ python3.10 -u loop-team/experiments/pace_topology_replay/extract_cases.py
EXTRACT_PASS cases=5 pointers=3514 source_statuses=APPENDED_AFTER_SEAL,SEALED_EXACT,SEALED_EXACT,APPENDED_AFTER_SEAL,SEALED_EXACT

$ python3.10 -u loop-team/experiments/pace_topology_replay/verify_sources.py
SOURCE_VERIFY_PASS cases=5 pointers=3514 source_statuses=APPENDED_AFTER_SEAL,SEALED_EXACT,SEALED_EXACT,APPENDED_AFTER_SEAL,SEALED_EXACT
```

These statuses are observations from the final documentation verification
execution on 2026-08-02, not durable counts: two sources had records appended
after their seals and three were exact at that instant. `APPENDED_AFTER_SEAL`
means the exact sealed prefix still verified; future append activity may change
an observed `SEALED_EXACT` status without changing the frozen replay.

Two independent scorer executions produced the same bytes:

```text
1d6b4115fdafa8ec5fb7541d2ede76b807d5c9f6c0664b659eb41ca87492fd7a  loop-team/experiments/pace_topology_replay/fixtures/simulation_result.json
1d6b4115fdafa8ec5fb7541d2ede76b807d5c9f6c0664b659eb41ca87492fd7a  loop-team/experiments/pace_topology_replay/fixtures/simulation_result.json
```

The existing `loop-team/evals/acceptor.py::pace_accept` was invoked with no
fabricated paired observations. It rejected promotion, while the replay score
retained the required non-applicable verdicts:

```text
PACE_ACCEPTOR_DECISION=REJECT
PACE_ACCEPTOR_REASON=too few discordant pairs (0 < 5)
STATISTICAL_VERDICT=NOT_APPLICABLE
ADOPTION_VERDICT=NOT_APPLICABLE
PACE_ACCEPTANCE=false
```

## Limitations

- These are five selected historical, non-IID counterfactual replays.
- No case exposes labelled baseline-only active critical-path spans together
  with retained-work overlap and variant replacement overhead.
- Poll and heartbeat blocked durations remain child/runtime waiting and are not
  claimed as savings.
- The measured 74.33% is an action-count reduction, not elapsed-time reduction.
- Historical dispatches or stages that cannot be positively classified from a
  native source record remain unmeasurable and prevent aggregate simulation pass.
- All five cases lack an authoritative independent-verifier terminal under the
  strict grammar. Hospitable and CI triage also contain unclassified dispatches;
  those two lack authoritative preflight-pass terminals as well.
- This pilot does not modify the orchestrator or PMS product code.
