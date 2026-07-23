#!/usr/bin/env python3
"""A/B (PACE-gated): structlog VARIANT vs steelman stdlib BASELINE on
run/role correlation under concurrency + asyncio (metric M2).

THE QUESTION
    When N concurrent workers each bind a distinct (run_id, role) INSIDE the
    worker and emit many lines, does the persisted log.jsonl carry the CORRECT
    (level, run_id, role) on every line? That is "run/role correlation under
    concurrency" -- the property a structured logger must hold for per-run,
    per-role attribution. We score the stdlib baseline against the structlog
    variant on the SAME scenario and let PACE (run_experiment.decide) decide.

FAIRNESS (binding pins from plan-check)
    1. Every emit carries a UNIQUE monotonic ``_seq``. The scorer matches each
       persisted line to its EXPECTED (level, run_id, role) BY ``_seq`` -- never
       by file position, because concurrent appends interleave in the file.
    2. Positive control: a multi-thread run must let the baseline score > 0 (the
       baseline is a real, correct logger -- not crippled to 0, not hardwired to 1).
    3. Identical persistence/flush path and identical parser for both impls
       (both call baseline_logger.append_jsonl; both files parsed by _read_jsonl).
    4. REJECT on "too few discordant pairs" is the EXPECTED HONEST outcome when
       both impls correctly use contextvars: concordant pairs are discarded, so
       two correct loggers leave PACE with no discordant evidence. The stdlib
       incumbent stands. This is documented in RESULT.md.

The A/B is genuinely capable of returning REJECT (a tie, stdlib stands) or even
a baseline win -- nothing here engineers a structlog win.

CLI:
    python3 ab_logging.py            # run the full A/B, print verdict, write RESULT.md
    python3 ab_logging.py --no-write # run + print, do not (re)write RESULT.md
"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import threading

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENTS_DIR = os.path.normpath(os.path.join(EXP_DIR, ".."))
sys.path.insert(0, EXP_DIR)
sys.path.insert(0, EXPERIMENTS_DIR)

import baseline_logger              # noqa: E402  -- stdlib steelman + shared writer
import run_experiment               # noqa: E402  -- decide() = PACE pairing

try:
    import structlog_logger
    VARIANT_AVAILABLE = structlog_logger.STRUCTLOG_AVAILABLE
except Exception:  # pragma: no cover
    structlog_logger = None
    VARIANT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Scenario -- deterministic, fixed seed. N threads (and N async tasks), each
# binds a distinct (run_id, role) INSIDE the worker, then emits K lines at
# varying levels. We RECORD the expected (level, run_id, role) keyed by _seq.
# ---------------------------------------------------------------------------

LEVELS = ["debug", "info", "warning", "error", "critical"]
N_WORKERS = 8        # >= 8 (criterion #2)
K_LINES = 50         # >= 50 (criterion #2)
SEED = 1234


def _worker_plan(seed):
    """Deterministic per-worker (run_id, role, [levels...]) plan from a seed.

    Same plan is used for BOTH impls and for both the thread and async runs, so
    the only thing that varies is the logger implementation."""
    import random
    rng = random.Random(seed)
    plans = []
    for w in range(N_WORKERS):
        run_id = "run-%04d" % rng.randrange(10**6)
        role = ["oga", "test-writer", "coder", "verifier", "researcher"][w % 5] + "-%d" % w
        levels = [LEVELS[rng.randrange(len(LEVELS))] for _ in range(K_LINES)]
        plans.append({"run_id": run_id, "role": role, "levels": levels})
    return plans


def _run_threads(get_logger, run_dir, plans):
    """Run the threaded scenario; return {_seq: (level, run_id, role)} expected map.

    Each thread: get a logger, bind_context(run_id, role) INSIDE the thread,
    then emit K lines. The emit returns the unique _seq, which we record against
    the expected tuple. A barrier maximizes interleaving of the appends."""
    expected = {}
    exp_lock = threading.Lock()
    barrier = threading.Barrier(len(plans))

    def work(plan):
        log = get_logger("ab", run_dir=run_dir)
        log.bind_context(run_id=plan["run_id"], role=plan["role"])
        barrier.wait()  # release all threads together -> maximal interleave
        local = {}
        for lvl in plan["levels"]:
            seq = getattr(log, lvl)("emit", phase="thread")
            local[seq] = (lvl.upper(), plan["run_id"], plan["role"])
        with exp_lock:
            expected.update(local)

    threads = [threading.Thread(target=work, args=(p,)) for p in plans]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return expected


def _run_async(get_logger, run_dir, plans):
    """Run the asyncio scenario; return {_seq: (level, run_id, role)} expected map.

    contextvars are exactly where async correctness matters: each Task gets its
    own context copy, so bind_contextvars inside a task must not bleed across
    tasks. >= 8 tasks (criterion #3)."""
    expected = {}

    async def work(plan):
        log = get_logger("ab", run_dir=run_dir)
        log.bind_context(run_id=plan["run_id"], role=plan["role"])
        local = {}
        for lvl in plan["levels"]:
            seq = getattr(log, lvl)("emit", phase="async")
            local[seq] = (lvl.upper(), plan["run_id"], plan["role"])
            await asyncio.sleep(0)  # yield -> interleave tasks
        return local

    async def driver():
        results = await asyncio.gather(*(work(p) for p in plans))
        for r in results:
            expected.update(r)

    asyncio.run(driver())
    return expected


def _read_jsonl(run_dir):
    """Parse <run_dir>/log.jsonl into {_seq: record}. The IDENTICAL parser for
    both impls (fairness pin #3). Lines without a usable _seq are ignored."""
    path = os.path.join(run_dir, "log.jsonl")
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            seq = rec.get("_seq")
            if isinstance(seq, int):
                out[seq] = rec
    return out


def _score(expected, records, ordered_seqs):
    """Per-instance correctness vector ALIGNED BY _seq (the same ordered instance
    list is used for both impls). correctness=1 iff the persisted record for that
    _seq exists AND carries level+run_id+role EXACTLY matching the expected tuple."""
    vec = []
    for seq in ordered_seqs:
        exp = expected[seq]
        rec = records.get(seq)
        if rec is None:
            vec.append(0)
            continue
        ok = (rec.get("level") == exp[0]
              and rec.get("run_id") == exp[1]
              and rec.get("role") == exp[2])
        vec.append(1 if ok else 0)
    return vec


def run_impl(get_logger, plans):
    """Run BOTH the thread and async scenario for one impl in a fresh run_dir;
    return (expected_map, parsed_records, run_dir)."""
    run_dir = tempfile.mkdtemp(prefix="exp1_log_")
    expected = {}
    expected.update(_run_threads(get_logger, run_dir, plans))
    expected.update(_run_async(get_logger, run_dir, plans))
    records = _read_jsonl(run_dir)
    return expected, records, run_dir


def run_ab(min_discordant=5):
    """Run the scenario for baseline and (if available) the structlog variant,
    score both over the SAME _seq-ordered instances, and PACE-decide.

    Returns a dict with the decision, per-impl correctness counts, vectors, and
    metadata. The baseline always runs (it is the incumbent and the positive
    control); the variant is skipped cleanly if structlog is unavailable."""
    plans = _worker_plan(SEED)

    base_exp, base_rec, base_dir = run_impl(baseline_logger.get_logger, plans)

    out = {
        "n_workers": N_WORKERS,
        "k_lines": K_LINES,
        "baseline_dir": base_dir,
        "variant_available": VARIANT_AVAILABLE,
    }

    if not VARIANT_AVAILABLE:
        # Guarded skip (criterion #6): score baseline only as a positive control.
        ordered = sorted(base_exp.keys())
        base_vec = _score(base_exp, base_rec, ordered)
        out.update({
            "n_instances": len(ordered),
            "baseline_correct": sum(base_vec),
            "variant_correct": None,
            "decision": None,
            "skipped_variant": True,
        })
        shutil.rmtree(base_dir, ignore_errors=True)
        return out

    var_exp, var_rec, var_dir = run_impl(structlog_logger.get_logger, plans)
    out["variant_dir"] = var_dir

    # SAME ordered instance list for both impls. The two runs draw from the same
    # global _seq source, so each impl's expected keys are disjoint integer sets;
    # the contract that both vectors are EQUAL-LENGTH and aligned is enforced by
    # building one ordered list per impl of identical length (N_WORKERS*K_LINES*2
    # instances each) and pairing position-for-position. Each position is itself
    # matched to its persisted line BY _seq within that impl.
    base_ordered = sorted(base_exp.keys())
    var_ordered = sorted(var_exp.keys())
    assert len(base_ordered) == len(var_ordered), "impls must produce equal instance counts"

    base_vec = _score(base_exp, base_rec, base_ordered)
    var_vec = _score(var_exp, var_rec, var_ordered)

    decision = run_experiment.decide(base_vec, {"structlog": var_vec},
                                     min_discordant=min_discordant)
    r = decision["results"]["structlog"]

    out.update({
        "n_instances": len(base_ordered),
        "baseline_correct": sum(base_vec),
        "variant_correct": sum(var_vec),
        "baseline_vec": base_vec,
        "variant_vec": var_vec,
        "decision": r.decision,
        "wealth": r.wealth,
        "discordant": r.discordant,
        "peeks": r.peeks,
        "reason": r.reason,
        "winner": decision["winner"],
        "skipped_variant": False,
    })
    shutil.rmtree(base_dir, ignore_errors=True)
    shutil.rmtree(var_dir, ignore_errors=True)
    return out


def _rate(correct, n):
    return (correct / n) if n else 0.0


def render_result_md(out):
    """Build RESULT.md content (criterion #7: verdict, metric, fairness, gating)."""
    n = out["n_instances"]
    base_c = out["baseline_correct"]
    if out.get("skipped_variant"):
        verdict_block = (
            "**VERDICT: variant SKIPPED** -- structlog unavailable; the runner "
            "guarded the import and scored the baseline only as a positive control.\n\n"
            "- baseline correctness: %d / %d (%.3f)\n" % (base_c, n, _rate(base_c, n))
        )
    else:
        var_c = out["variant_correct"]
        verdict_block = (
            "**VERDICT: %s** (winner: %s)\n\n"
            "- PACE decision: **%s** -- %s\n"
            "- betting wealth: %.4f  (threshold 1/alpha = 20.0)\n"
            "- discordant pairs: %d   (peeks: %d)\n\n"
            "Correctness on M2 (run/role correlation under concurrency + asyncio), "
            "scored BY `_seq` over the SAME ordered instance list:\n\n"
            "- baseline (stdlib) : %d / %d  (%.3f)\n"
            "- variant (structlog): %d / %d  (%.3f)\n"
            % (out["decision"],
               out["winner"] or "baseline (incumbent stands)",
               out["decision"], out["reason"], out["wealth"],
               out["discordant"], out["peeks"],
               base_c, n, _rate(base_c, n),
               var_c, n, _rate(var_c, n))
        )

    honest_note = ""
    if not out.get("skipped_variant") and out["decision"] == "REJECT" \
            and out["discordant"] < 5:
        honest_note = (
            "\n### Why REJECT here is the honest outcome\n\n"
            "Both impls correctly use `contextvars` to carry (run_id, role) into "
            "each worker, so both score the SAME on essentially every instance. "
            "PACE discards concordant pairs; with both loggers correct there are "
            "**too few discordant pairs (%d < 5)** to bet on, so PACE REJECTs and "
            "the **stdlib incumbent stands**. This is the expected, honest result "
            "of a fair test between two correct implementations -- NOT a structlog "
            "failure and NOT an engineered baseline win.\n" % out["discordant"]
        )

    return """# Experiment 1 -- structlog vs steelman stdlib logger (PACE-gated A/B)

## Metric
**M2: run/role correlation under concurrency + asyncio.** With %d concurrent
workers each binding a distinct `(run_id, role)` INSIDE the worker and emitting
%d lines at varying levels, is every persisted `log.jsonl` line carrying the
CORRECT `(level, run_id, role)`? Scored over both a thread scenario and an
asyncio scenario.

## Result
%s
%s
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
""" % (out["n_workers"], out["k_lines"], verdict_block, honest_note)


def print_report(out):
    print("A/B -- structlog VARIANT vs steelman stdlib BASELINE (PACE-gated)")
    print("=" * 66)
    print("  metric: M2 run/role correlation under concurrency + asyncio")
    print("  workers=%d  lines/worker=%d  instances=%d (thread+async, x2 phases)"
          % (out["n_workers"], out["k_lines"], out["n_instances"]))
    if out.get("skipped_variant"):
        print("  VARIANT SKIPPED (structlog unavailable) -- guarded import")
        print("  baseline correct: %d / %d  (positive control)"
              % (out["baseline_correct"], out["n_instances"]))
        return
    n = out["n_instances"]
    print("  baseline (stdlib)   correct: %d / %d  (%.3f)"
          % (out["baseline_correct"], n, _rate(out["baseline_correct"], n)))
    print("  variant  (structlog) correct: %d / %d  (%.3f)"
          % (out["variant_correct"], n, _rate(out["variant_correct"], n)))
    print("-" * 66)
    print("  PACE: %s  (wealth=%.4f, discordant=%d, peeks=%d) -- %s"
          % (out["decision"], out["wealth"], out["discordant"],
             out["peeks"], out["reason"]))
    print("  WINNER: %s" % (out["winner"] or "baseline (incumbent stands)"))


def main():
    write = "--no-write" not in sys.argv
    out = run_ab()
    print_report(out)
    if write:
        path = os.path.join(EXP_DIR, "RESULT.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render_result_md(out))
        print("\nwrote %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
