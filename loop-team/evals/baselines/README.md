# Certified verifier-verdict baselines

`verifier_verdicts.json` — the verifier's verdicts on the 41 `requires:judge`
cases, produced via the FREE sub-agent path (`JUDGE_ADAPTER_SUBAGENT.md`) on
2026-06-23 and **MVVP-certified**: test-retest accept/reject agreement **1.000**
(two independent runs, zero flips), κ vs gold **1.000** on both runs.

## What it's for
A regression baseline. After a change to `roles/verifier.md` (or anything that
moves the judge), re-run the free path and **diff** to see which verdicts moved.

## How to regenerate + diff (all $0, on the subscription)
1. `python3 -c "import sys,json;sys.path.insert(0,'evals');import run_evals,replay_judge;json.dump(replay_judge.export_blind([c for c in run_evals.load_cases() if c.get('requires')=='judge']),open('/tmp/judge_blind.json','w'))"`
2. Spawn a judging sub-agent (bare `verifier.md`, blind `/tmp/judge_blind.json`,
   judge each independently) → write `/tmp/v.json` = `[{id,verdict,reason}]`.
3. `REPLAY_VERDICTS_PATH=/tmp/v.json python3 evals/run_evals.py --judge evals/replay_judge.py --arith-guard`
4. Diff `/tmp/v.json` vs this baseline. **Compare on accept/reject** — the
   FAIL↔FALSE-PASS sub-label carries run-to-run noise (this run: 35/41 exact
   3-label agreement but 41/41 accept/reject), so only an accept↔reject move is a
   real regression.

## Honest scope
κ=1.000 here certifies stability + accuracy on the FROZEN regression suite (cases
the verifier was hardened against — saturated). It is NOT evidence of perfection
on hard cases; the fresh adversarial batches are where real weaknesses surface.
