"""Tests for dashboard.py's trace wiring.

Regression test for H-DASHBOARD-READTRACE-IMPORT-1: dashboard.py used to do
``from trace import read_trace``, which silently resolved to the Python
stdlib `trace` module (no `read_trace` attribute) instead of the real
``loop-team/runner/run_trace.py``. The bare `except Exception` around the
import then fired every time, quietly falling back to a stub that always
returned `[]` -- so trace/token/cost data was lost for every run, with no
error ever surfaced.

These tests prove:
  1. dashboard.read_trace really is runner.run_trace.read_trace (not the
     stdlib trace module and not the local no-op fallback).
  2. A real trace.jsonl fixture with genuine token/cost data comes back
     as real parsed events (non-empty), both from read_trace directly and
     end-to-end through dashboard.build()'s generated HTML.

Run with:
    python3 -m pytest loop-team/harness/test_dashboard.py -q
"""
import json
import os
import sys
import tempfile
import unittest

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HARNESS_DIR)
import dashboard  # noqa: E402


class ReadTraceIsTheRealOne(unittest.TestCase):
    """dashboard.read_trace must be the runner/run_trace.py implementation,
    not the stdlib `trace` module and not the local stub fallback."""

    def test_resolves_to_runner_run_trace_module(self):
        self.assertEqual(dashboard.read_trace.__module__, "run_trace")

    def test_source_file_is_runner_run_trace_py(self):
        import inspect
        src = inspect.getsourcefile(dashboard.read_trace)
        self.assertTrue(src.endswith(os.path.join("runner", "run_trace.py")),
                         "expected runner/run_trace.py, got {}".format(src))

    def test_is_not_the_do_nothing_fallback_stub(self):
        # The old broken behavior always returned [] regardless of input.
        # Prove this is a real reader by giving it a run_dir with a real
        # trace.jsonl and confirming it does NOT come back empty.
        with tempfile.TemporaryDirectory() as run_dir:
            _write_fixture_trace(run_dir)
            events = dashboard.read_trace(run_dir)
            self.assertNotEqual(events, [])
            self.assertEqual(len(events), 2)


def _write_fixture_trace(run_dir):
    """Write a small, realistic 2-line trace.jsonl fixture into run_dir."""
    lines = [
        {
            "ts": "2026-07-04T10:00:00", "event_type": "role_dispatch",
            "role": "coder", "model": "claude-sonnet-4-5", "iteration": 1,
            "tokens_in": 1000, "tokens_out": 500, "cum_tokens": 1500,
            "cum_cost_usd": 0.0105, "cost_usd": 0.0105,
            "outcome": None, "verdict": None, "note": "initial build",
        },
        {
            "ts": "2026-07-04T10:05:00", "event_type": "verdict",
            "role": "verifier", "model": "claude-sonnet-4-5", "iteration": 1,
            "tokens_in": 2000, "tokens_out": 300, "cum_tokens": 3800,
            "cum_cost_usd": 0.0195, "cost_usd": 0.009,
            "outcome": "PASS", "verdict": "PASS", "note": "all tests green",
        },
    ]
    path = os.path.join(run_dir, "trace.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for rec in lines:
            fh.write(json.dumps(rec) + "\n")
    return path


class ParseRunIncludesRealTraceData(unittest.TestCase):
    """parse_run() must surface real cumulative token/cost totals from a
    genuine trace.jsonl fixture, not the empty/None values the broken import
    silently produced."""

    def test_parse_run_summarizes_real_trace(self):
        with tempfile.TemporaryDirectory() as run_dir:
            _write_fixture_trace(run_dir)
            # Give it a minimal log so discover_runs / parse_run treats this
            # as a real run directory.
            with open(os.path.join(run_dir, "run_log.md"), "w") as fh:
                fh.write("VERDICT: PASS\n")

            record = dashboard.parse_run(run_dir)

            self.assertIsNotNone(record["trace"])
            self.assertEqual(record["trace"]["n_events"], 2)
            self.assertEqual(record["trace"]["cum_tokens"], 3800)
            self.assertAlmostEqual(record["trace"]["cum_cost_usd"], 0.0195)
            self.assertTrue(record["trace"]["cost_known"])


class BuildRendersRealTraceIntoHtml(unittest.TestCase):
    """End-to-end: dashboard.build() over a run root containing a real
    trace.jsonl must render real token/cost numbers into the output HTML,
    not the '0 events / no trace' shape the broken import produced."""

    def test_generated_html_contains_real_token_and_cost_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_root = os.path.join(tmp, "runs")
            run_dir = os.path.join(run_root, "2026-07-04_fixture-run")
            os.makedirs(run_dir)
            _write_fixture_trace(run_dir)
            with open(os.path.join(run_dir, "run_log.md"), "w") as fh:
                fh.write("VERDICT: PASS\n")

            out_path = os.path.join(tmp, "dashboard.html")
            out, runs = dashboard.build(roots=[run_root], out=out_path)

            self.assertEqual(len(runs), 1)
            self.assertIsNotNone(runs[0]["trace"])
            self.assertEqual(runs[0]["trace"]["cum_tokens"], 3800)

            with open(out_path, encoding="utf-8") as fh:
                html_text = fh.read()

            # The rendered card must show the real cumulative token count,
            # the real cost, and the verifier verdict pulled from the trace
            # -- not the "0 events / no trace" shape the broken import
            # silently produced.
            self.assertIn("3,800 tok", html_text)
            self.assertIn("$0.02", html_text)
            self.assertIn("chip-trace", html_text)
            # Summary stat: exactly one run counted with a live trace.
            self.assertIn(
                "<div class=\"stat\"><div class=\"n\">1</div>"
                "<div class=\"l\">Runs with live trace</div></div>",
                html_text,
            )


if __name__ == "__main__":
    unittest.main()
