"""Tests for lens_completion_barrier.py.

Spec source:
    research/async-completion-barrier-prior-art-2026-07-09.md
    research/gate10-concurrency-fingerprint-inventory-2026-07-09.md

Run with:
    python3 -m pytest loop-team/harness/test_lens_completion_barrier.py -q
"""
import importlib
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "lens_completion_barrier.py")
sys.path.insert(0, HERE)

lcb = importlib.import_module("lens_completion_barrier")


def test_build_expected_set_normalizes_and_sorts_dispatch_ids():
    expected = lcb.build_expected_set([" security ", "binding", "logic"])

    assert expected == ("binding", "logic", "security")


@pytest.mark.parametrize("values", [[], ["logic", " logic "], ["logic", ""]])
def test_build_expected_set_rejects_empty_duplicate_or_blank_ids(values):
    with pytest.raises(ValueError):
        lcb.build_expected_set(values)


def test_ready_only_when_completed_set_equals_expected_set():
    result = lcb.evaluate_lens_completion(
        expected=["logic", "security", "binding"],
        completed=["security", "binding", "logic"],
    )

    assert result["verdict"] == lcb.READY_TO_RECONCILE
    assert result["reconciliation_mode"] == lcb.COMPLETE_RECONCILIATION
    assert result["can_reconcile_complete"] is True
    assert result["can_reconcile_partial"] is False
    assert result["missing"] == []
    assert lcb.assert_ready_for_reconcile(result) is True


def test_missing_lens_blocks_even_when_completed_count_matches_expected_count():
    result = lcb.evaluate_lens_completion(
        expected=["logic", "security", "binding"],
        completed=["logic", "security", "phantom"],
    )

    assert result["verdict"] == lcb.INVALID_BARRIER
    assert result["can_reconcile_complete"] is False
    assert result["unexpected"] == ["phantom"]
    assert "unexpected" in " ".join(result["reasons"])


def test_missing_expected_lens_waits_for_result_not_reconciliation():
    result = lcb.evaluate_lens_completion(
        expected=["logic", "security", "binding"],
        completed=["logic", "security"],
    )

    assert result["verdict"] == lcb.WAITING_FOR_RESULTS
    assert result["reconciliation_mode"] == lcb.BLOCKED_RECONCILIATION
    assert result["missing"] == ["binding"]
    with pytest.raises(lcb.BarrierNotReady):
        lcb.assert_ready_for_reconcile(result)


def test_failed_lens_below_retry_limit_waits_for_bounded_retry():
    result = lcb.evaluate_lens_completion(
        expected=["logic", "security"],
        completed=["logic"],
        failed=["security"],
        retry_counts={"security": 0},
        retry_limit=1,
    )

    assert result["verdict"] == lcb.WAITING_FOR_RETRY
    assert result["retryable"] == ["security"]
    assert result["can_reconcile_complete"] is False
    assert result["can_reconcile_partial"] is False


def test_retry_exhausted_failure_becomes_visible_partial_not_ready():
    result = lcb.evaluate_lens_completion(
        expected=["logic", "security"],
        completed=["logic"],
        failed=["security"],
        retry_counts={"security": 1},
        retry_limit=1,
    )

    assert result["verdict"] == lcb.PARTIAL_COMPLETION
    assert result["reconciliation_mode"] == lcb.PARTIAL_RECONCILIATION
    assert result["terminal"] == ["logic", "security"]
    assert result["can_reconcile_complete"] is False
    assert result["can_reconcile_partial"] is True
    assert "retry-exhausted" in " ".join(result["reasons"])
    with pytest.raises(lcb.BarrierNotReady):
        lcb.assert_ready_for_reconcile(result)


def test_explicit_abandoned_lens_is_partial_completion_not_success():
    result = lcb.evaluate_lens_completion(
        expected=["logic", "security", "binding"],
        completed=["logic", "binding"],
        abandoned=["security"],
    )

    assert result["verdict"] == lcb.PARTIAL_COMPLETION
    assert result["abandoned"] == ["security"]
    assert result["missing"] == []
    assert result["can_reconcile_complete"] is False
    assert result["can_reconcile_partial"] is True


def test_timeout_below_retry_limit_waits_and_timeout_at_limit_is_partial():
    waiting = lcb.evaluate_lens_completion(
        expected=["logic"],
        timed_out=["logic"],
        retry_counts={"logic": 0},
        retry_limit=1,
    )
    partial = lcb.evaluate_lens_completion(
        expected=["logic"],
        timed_out=["logic"],
        retry_counts={"logic": 1},
        retry_limit=1,
    )

    assert waiting["verdict"] == lcb.WAITING_FOR_RETRY
    assert waiting["retryable"] == ["logic"]
    assert partial["verdict"] == lcb.PARTIAL_COMPLETION
    assert partial["timed_out"] == ["logic"]


def test_same_lens_cannot_be_success_and_failed():
    result = lcb.evaluate_lens_completion(
        expected=["logic"],
        completed=["logic"],
        failed=["logic"],
    )

    assert result["verdict"] == lcb.INVALID_BARRIER
    assert "multiple states" in " ".join(result["reasons"])


def test_retry_count_for_unknown_lens_is_invalid():
    result = lcb.evaluate_lens_completion(
        expected=["logic"],
        completed=["logic"],
        retry_counts={"phantom": 1},
    )

    assert result["verdict"] == lcb.INVALID_BARRIER
    assert result["unexpected"] == ["phantom"]


def _write_json(tmp_path, payload):
    path = tmp_path / "barrier_state.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _run_cli(state_path, *extra):
    return subprocess.run(
        [sys.executable, SCRIPT, "--state", state_path] + list(extra),
        capture_output=True,
        text=True,
    )


def test_cli_exits_zero_only_for_complete_reconciliation_by_default(tmp_path):
    state = _write_json(tmp_path, {
        "expected": ["logic", "security"],
        "completed": ["security", "logic"],
    })

    result = _run_cli(state)
    payload = json.loads(result.stdout)

    assert result.returncode == lcb.EXIT_READY
    assert payload["verdict"] == lcb.READY_TO_RECONCILE


def test_cli_blocks_missing_lens_before_reconcile(tmp_path):
    state = _write_json(tmp_path, {
        "expected": ["logic", "security"],
        "completed": ["logic"],
    })

    result = _run_cli(state)
    payload = json.loads(result.stdout)

    assert result.returncode == lcb.EXIT_WAITING
    assert payload["verdict"] == lcb.WAITING_FOR_RESULTS
    assert payload["missing"] == ["security"]


def test_cli_treats_partial_completion_as_nonzero_without_opt_in(tmp_path):
    state = _write_json(tmp_path, {
        "expected": ["logic", "security"],
        "completed": ["logic"],
        "failed": ["security"],
        "retry_counts": {"security": 1},
    })

    result = _run_cli(state)
    payload = json.loads(result.stdout)

    assert result.returncode == lcb.EXIT_PARTIAL
    assert payload["verdict"] == lcb.PARTIAL_COMPLETION


def test_cli_can_opt_into_partial_completion_for_explicit_fallback(tmp_path):
    state = _write_json(tmp_path, {
        "expected": ["logic", "security"],
        "completed": ["logic"],
        "abandoned": ["security"],
    })

    result = _run_cli(state, "--allow-partial")
    payload = json.loads(result.stdout)

    assert result.returncode == lcb.EXIT_READY
    assert payload["verdict"] == lcb.PARTIAL_COMPLETION
    assert payload["can_reconcile_complete"] is False
    assert payload["can_reconcile_partial"] is True


def test_cli_invalid_state_exits_invalid(tmp_path):
    state = _write_json(tmp_path, {
        "expected": ["logic"],
        "completed": ["logic"],
        "retry_counts": {"phantom": 1},
    })

    result = _run_cli(state)
    payload = json.loads(result.stdout)

    assert result.returncode == lcb.EXIT_INVALID
    assert payload["verdict"] == lcb.INVALID_BARRIER
