#!/usr/bin/env python3
"""Acceptance tests for exp1_logging (structlog vs steelman stdlib logger).

Labels: [BEHAVIORAL] = exercises real behavior; [DOC] = checks the result file.

Run:  cd loop-team && python3 -m pytest experiments/exp1_logging/test_exp1_logging.py -q
"""
import ast
import json
import os
import sys
import tempfile

import pytest

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENTS_DIR = os.path.normpath(os.path.join(EXP_DIR, ".."))
sys.path.insert(0, EXP_DIR)
sys.path.insert(0, EXPERIMENTS_DIR)

import ab_logging              # noqa: E402
import baseline_logger         # noqa: E402

try:
    import structlog_logger
    HAVE_STRUCTLOG = structlog_logger.STRUCTLOG_AVAILABLE
except Exception:
    structlog_logger = None
    HAVE_STRUCTLOG = False

LEVEL_METHODS = ["debug", "info", "warning", "error", "critical"]

# Impls under test: the baseline always; the variant only if structlog present.
IMPLS = [("baseline", baseline_logger.get_logger)]
if HAVE_STRUCTLOG:
    IMPLS.append(("structlog", structlog_logger.get_logger))


def _read(run_dir):
    path = os.path.join(run_dir, "log.jsonl")
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


# ---------------------------------------------------------------------------
# 1 [BEHAVIORAL] Shared conformance: identical public surface for BOTH impls,
#                each writing a parseable JSON line carrying the bound context.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,get_logger", IMPLS)
def test_conformance_public_surface(name, get_logger):
    run_dir = tempfile.mkdtemp(prefix="exp1_conf_")
    log = get_logger("conf", run_dir=run_dir)
    # surface: get_logger + bind_context + 5 level methods
    assert hasattr(log, "bind_context")
    for m in LEVEL_METHODS:
        assert callable(getattr(log, m)), "%s missing %s" % (name, m)
    log.bind_context(run_id="R1", role="coder")
    for m in LEVEL_METHODS:
        getattr(log, m)("hello", extra=m)
    recs = _read(run_dir)
    assert len(recs) == len(LEVEL_METHODS)
    seen_levels = set()
    for rec in recs:
        # parseable JSON line carrying bound context + reserved keys
        assert rec["run_id"] == "R1"
        assert rec["role"] == "coder"
        assert rec["logger"] == "conf"
        assert rec["msg"] == "hello"
        assert isinstance(rec["_seq"], int)
        seen_levels.add(rec["level"])
    assert seen_levels == {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


# ---------------------------------------------------------------------------
# 2 [BEHAVIORAL] Under concurrency the scorer yields EQUAL-LENGTH paired vectors
#                for both impls over the same _seq-ordered instances.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not HAVE_STRUCTLOG, reason="variant requires structlog")
def test_equal_length_paired_vectors_under_concurrency():
    out = ab_logging.run_ab()
    assert not out["skipped_variant"]
    assert len(out["baseline_vec"]) == len(out["variant_vec"])
    # concurrency floor: >= 8 workers x >= 50 lines, across thread+async phases
    assert out["n_workers"] >= 8
    assert out["k_lines"] >= 50
    assert out["n_instances"] == out["n_workers"] * out["k_lines"] * 2


# ---------------------------------------------------------------------------
# 3 [BEHAVIORAL] An asyncio scenario is exercised and scores correctly by _seq.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name,get_logger", IMPLS)
def test_async_scenario_exercised(name, get_logger):
    plans = ab_logging._worker_plan(ab_logging.SEED)
    run_dir = tempfile.mkdtemp(prefix="exp1_async_")
    expected = ab_logging._run_async(get_logger, run_dir, plans)
    # async path actually emitted N_WORKERS * K_LINES instances
    assert len(expected) == ab_logging.N_WORKERS * ab_logging.K_LINES
    records = ab_logging._read_jsonl(run_dir)
    ordered = sorted(expected.keys())
    vec = ab_logging._score(expected, records, ordered)
    # A correct contextvars logger associates run/role with each async task line.
    assert sum(vec) == len(vec), "%s mis-correlated under asyncio" % name


# ---------------------------------------------------------------------------
# 4 [BEHAVIORAL] decide()/pace_accept runs on the paired vectors and returns a
#                documented ACCEPT or REJECT with wealth + discordant.
# ---------------------------------------------------------------------------
@pytest.mark.skipif(not HAVE_STRUCTLOG, reason="variant requires structlog")
def test_pace_decision_documented():
    out = ab_logging.run_ab()
    assert out["decision"] in ("ACCEPT", "REJECT")
    assert isinstance(out["wealth"], float)
    assert isinstance(out["discordant"], int)
    assert isinstance(out["reason"], str) and out["reason"]


# ---------------------------------------------------------------------------
# 5 [BEHAVIORAL] Positive control: baseline scores > 0 under multi-thread
#                concurrency (steelman, not crippled to 0 and not hardwired to 1).
# ---------------------------------------------------------------------------
def test_positive_control_baseline_multithread():
    plans = ab_logging._worker_plan(ab_logging.SEED)
    run_dir = tempfile.mkdtemp(prefix="exp1_pc_")
    expected = ab_logging._run_threads(baseline_logger.get_logger, run_dir, plans)
    records = ab_logging._read_jsonl(run_dir)
    ordered = sorted(expected.keys())
    vec = ab_logging._score(expected, records, ordered)
    score = sum(vec)
    # Must be > 0 (not crippled) AND this is multi-thread, not single-thread.
    assert score > 0, "baseline scored 0 under multi-thread -- crippled, not steelman"
    assert ab_logging.N_WORKERS >= 8
    assert len(vec) == ab_logging.N_WORKERS * ab_logging.K_LINES
    # Not hardwired: the scorer CAN return < full. Prove it by feeding a record
    # set with one deliberately corrupted line and seeing the score drop.
    bad_seq = ordered[0]
    corrupted = dict(records)
    rec = dict(corrupted[bad_seq]); rec["role"] = "WRONG"
    corrupted[bad_seq] = rec
    bad_vec = ab_logging._score(expected, corrupted, ordered)
    assert sum(bad_vec) == score - 1, "scorer must not be hardwired to a constant"


# ---------------------------------------------------------------------------
# 6 [BEHAVIORAL] Import hygiene: baseline imports NO third-party module;
#                structlog imported ONLY in structlog_logger.py; guarded so the
#                runner skips the variant cleanly if structlog were absent.
# ---------------------------------------------------------------------------
_STDLIB_OK = {
    "contextvars", "datetime", "itertools", "json", "os", "threading", "sys",
    "asyncio", "tempfile", "shutil", "ast", "collections",
}
# first-party modules the experiment files may import
_FIRSTPARTY_OK = {"baseline_logger", "structlog_logger", "ab_logging",
                  "run_experiment", "acceptor", "run_evals"}


def _top_level_imports(path):
    with open(path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                mods.add(node.module.split(".")[0])
    return mods


def test_baseline_imports_no_third_party():
    mods = _top_level_imports(os.path.join(EXP_DIR, "baseline_logger.py"))
    third_party = mods - _STDLIB_OK - _FIRSTPARTY_OK
    assert not third_party, "baseline must be stdlib-only, found: %s" % third_party
    assert "structlog" not in mods


def test_structlog_only_imported_in_variant():
    # structlog appears in structlog_logger.py ...
    var_mods = _top_level_imports(os.path.join(EXP_DIR, "structlog_logger.py"))
    assert "structlog" in var_mods
    # ... and NOT in the baseline or the runner.
    for f in ("baseline_logger.py", "ab_logging.py"):
        assert "structlog" not in _top_level_imports(os.path.join(EXP_DIR, f)), \
            "structlog leaked into %s" % f


def test_variant_import_is_guarded():
    # The variant defines a STRUCTLOG_AVAILABLE flag and get_logger raises (not
    # imports at top) when unavailable, so the runner can guard cleanly.
    assert hasattr(structlog_logger, "STRUCTLOG_AVAILABLE")
    # The runner consults the flag and exposes a clean skip path.
    src = open(os.path.join(EXP_DIR, "ab_logging.py")).read()
    assert "VARIANT_AVAILABLE" in src
    assert "skipped_variant" in src


# ---------------------------------------------------------------------------
# 7 [DOC] RESULT.md records verdict, metric, fairness invariants, human-gating.
# ---------------------------------------------------------------------------
def test_result_md_documents_everything():
    # Generate it from a real run so the doc reflects an actual verdict.
    out = ab_logging.run_ab()
    md = ab_logging.render_result_md(out)
    low = md.lower()
    assert "m2" in low and "run/role correlation" in low
    assert "verdict" in low
    assert "fairness invariants" in low
    assert "_seq" in md and "never by file position" in low
    assert "positive control" in low
    assert "human-gated" in low and "does not adopt" in low
    if not out.get("skipped_variant"):
        assert out["decision"] in md  # ACCEPT or REJECT literal present


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
