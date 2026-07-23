# Experiment 1 -- structlog vs steelman stdlib logger (PACE-gated A/B)

## Metric
**M2: run/role correlation under concurrency + asyncio.** With 8 concurrent
workers each binding a distinct `(run_id, role)` INSIDE the worker and emitting
50 lines at varying levels, is every persisted `log.jsonl` line carrying the
CORRECT `(level, run_id, role)`? Scored over both a thread scenario and an
asyncio scenario.

## Result
**VERDICT: REJECT** (winner: baseline (incumbent stands))

- PACE decision: **REJECT** -- too few discordant pairs (0 < 5)
- betting wealth: 1.0000  (threshold 1/alpha = 20.0)
- discordant pairs: 0   (peeks: 800)

Correctness on M2 (run/role correlation under concurrency + asyncio), scored BY `_seq` over the SAME ordered instance list:

- baseline (stdlib) : 800 / 800  (1.000)
- variant (structlog): 800 / 800  (1.000)


### Why REJECT here is the honest outcome

Both impls correctly use `contextvars` to carry (run_id, role) into each worker, so both score the SAME on essentially every instance. PACE discards concordant pairs; with both loggers correct there are **too few discordant pairs (0 < 5)** to bet on, so PACE REJECTs and the **stdlib incumbent stands**. This is the expected, honest result of a fair test between two correct implementations -- NOT a structlog failure and NOT an engineered baseline win.

## Fairness invariants honored
1. **Per-emit unique `_seq`.** Every emit embeds a monotonic, globally-unique
   `_seq`. The scorer matches each persisted line to its expected
   `(level, run_id, role)` **by `_seq`, never by file position** -- mandatory
   because concurrent appends interleave in the file.
2. **Positive control.** A multi-thread run lets the baseline score > 0 (it is a
   real, correct steelman logger -- not crippled to 0, not hardwired to 1). The
   test suite asserts this directly.
3. **Identical persistence + parser.** Both impls persist through the SAME
   `baseline_logger.append_jsonl` (write -> flush -> `os.fsync` under a per-path
   lock, mirroring `harness/log.py`), and both files are read by the SAME
   `_read_jsonl` parser. The only variable is the emit/context-propagation path.
4. **REJECT-on-too-few-discordant is honest.** When both impls correctly use
   contextvars, concordant pairs dominate and PACE has no discordant evidence to
   bet on; it REJECTs and the stdlib incumbent stands. Documented above.

## Adoption is HUMAN-GATED
This run measures and reports a verdict. It **does not adopt anything.** No
production logger is swapped. Replacing `harness/log.py` (or adding a structlog
dependency) is a SEPARATE, diff-reviewed, human-approved change -- and per the
result above, the evidence does not justify it.
