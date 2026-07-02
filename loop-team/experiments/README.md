# Loop Team — Experiment harness ("does it really help?")

The engine that turns a Researcher's candidate into a measured **ACCEPT / REJECT**.
It scores a baseline and one or more variants on the **same** instances and
accepts a variant only if `evals/acceptor.py` (PACE) says it is significantly
better — anytime-valid, false-accept ≤ α. A higher raw score is *not* acceptance;
that's the dev-set p-hacking the acceptor exists to stop.

Pairs with `roles/researcher.md`: the Researcher finds techniques and emits an
`experiment` spec; this runs it.

## Run

```bash
# A/B two harness implementations on the live eval suite:
python3 loop-team/experiments/run_experiment.py \
  --baseline loop-team/harness/verify.py \
  --variant improved=/path/to/verify_v2.py

python3 -m pytest loop-team/experiments -q
```

## Pluggable scorer

`run_experiment(baseline, variants, scorer=...)` accepts any scorer returning a
per-instance correctness vector (`list[int]`), as long as baseline and variants
are scored on the **same ordered instances** (paired — PACE requires it).

- **`harness_scorer`** (built in) — scores a `verify.py` by the suite's per-case
  correctness. Use it to A/B harness/role changes today.
- **task-success scorer** (Phase 2+) — drop in a callable that runs a held set of
  coding tasks and returns pass/fail per task. Same interface; that's how
  "improves the coding" becomes the literal measured number.

## Prompt-format A/Bs (judge prompt variants)

Two runnable A/Bs over judge **prompt** variants (same model, same cases, same
parser, PACE-decided on accuracy):

- **`ab_answer_block.py`** — `<answer>`-block verdict format vs the one-line format.
  Result: PACE REJECT (no accuracy gain on saturated objective cases); not adopted.
- **`ab_rrd.py`** — Recursive Rubric Decomposition (decompose→evaluate-with-evidence
  →aggregate) vs the flat one-shot prompt, scored on the **balanced verifier-target**
  cases. Result: PACE REJECT on both Sonnet (39/39 vs 39/39, 0 discordant) and Haiku
  (39/39 vs 37/39); not adopted — the suite is **saturated** so no prompt change is
  measurable. Two durable lessons baked in: (1) **equal token budget** — a verbose
  variant truncates under a tight cap and parses to garbage; the first run's "RRD
  22/39" was a 512-token artifact (`FAIR_MAX_TOKENS=2000` now, equal for both arms);
  (2) you can't measure an improvement against a saturated baseline — see
  `research/hard-case-discrimination-dossier-2026-06-23.md` for the hard-suite plan.

## Why one change per experiment

`decide()` PACEs each variant independently against the baseline. Bundle two
changes and you can't attribute the effect — so the Researcher's spec enforces
one variable per experiment, and `decide` reports each variant's wealth,
discordant-pair count, and reason so a REJECT is legible ("too few discordant
pairs" = insufficient evidence, not "worse").
