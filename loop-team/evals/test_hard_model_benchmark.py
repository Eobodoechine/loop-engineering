import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = Path(EVALS_DIR).parents[1]
sys.path.insert(0, EVALS_DIR)
import hard_model_benchmark as hmb  # noqa: E402


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture_root():
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    _write(root / "loop-team" / "runs" / "a" / "gap_records_single.json", json.dumps({
        "lens": "state-completeness",
        "round": 1,
        "gap_type": "DESIGN",
        "tag": "[LOGIC]",
        "touches": ["AC-SOURCE-ONE"],
        "broken_assumption": "SENTINEL_BROKEN_ASSUMPTION_LEAK",
        "why_it_fails": "SENTINEL_WHY_IT_FAILS_LEAK",
        "proposed_fix": "SENTINEL_PROPOSED_FIX_LEAK",
        "mechanism_refs": ["SENTINEL_MECHANISM_REF_LEAK"],
    }))
    _write(root / "loop-team" / "runs" / "b" / "gap_records_list.json", json.dumps([
        {"gap_type": "DESIGN", "touches": ["AC-SOURCE-TWO"], "broken_assumption": "hidden"},
        {"gap_type": "DESIGN", "touches": ["AC-SOURCE-THREE"], "why_it_fails": "hidden"},
    ]))
    _write(root / "loop-team" / "runs" / "c" / "gap_records_lines.jsonl",
           '{"gap_id":"JSONL-SHAPE","category":"OBSERVABILITY","status":"OPEN_DISCLOSED"}\n'
           'not-json\n'
           '{"gap_type":"DESIGN","touches":["AC-JSONL-TWO"]}\n')
    _write(root / "loop-team" / "runs" / "d" / "gap_records_reconciled.json", json.dumps({
        "merged_items": [
            {"records": [{"gap_type": "DESIGN", "touches": ["AC-MERGED-ONE"]}]},
            {"records": [{"gap_type": "DESIGN", "touches": ["AC-MERGED-TWO"]}]},
        ]
    }))
    _write(root / "loop-team" / "runs" / "e" / "gap_records_bad.json", "{not valid")

    top_case = {
        "id": "original-active-id",
        "origin": "origin string with expected FAIL and trap filename",
        "type": "BEHAVIORAL",
        "target": "verifier",
        "expected": "FAIL",
        "artifact": "Artifact text says original-active-id and FAIL and /Use"
        "rs/eobodoechine/private",
        "rubric": "Rubric says PASS or FALSE-PASS should not leak as the answer.",
    }
    _write(root / "loop-team" / "evals" / "cases" / "z-trap-fail-name.json", json.dumps(top_case))
    _write(root / "loop-team" / "evals" / "cases" / "hard" / "excluded.json", json.dumps({
        "id": "hard-original-id", "expected": "PASS", "artifact": "excluded"
    }))
    _write(root / "loop-team" / "evals" / "cases" / "candidates" / "excluded.json", json.dumps({
        "id": "candidate-original-id", "expected": "PASS", "artifact": "excluded"
    }))
    _write(root / "loop-team" / "evals" / "cases" / "objective" / "excluded.json", json.dumps({
        "id": "objective-original-id", "expected": "PASS", "artifact": "excluded"
    }))
    return tmp, root


def _assert_model_input_boundary(testcase, packets):
    forbidden_fragments = [
        "SENTINEL_BROKEN_ASSUMPTION_LEAK",
        "SENTINEL_WHY_IT_FAILS_LEAK",
        "SENTINEL_PROPOSED_FIX_LEAK",
        "SENTINEL_MECHANISM_REF_LEAK",
        "original-active-id",
        "z-trap-fail-name.json",
        "/Use" "rs/",
        "gap_records",
        "plan_check",
    ]
    forbidden_keys = [
        "oracle",
        "expected",
        "mechanism_refs",
        "proposed_fix",
        "why_it_fails",
        "broken_assumption",
        "source_path",
    ]
    for packet in packets:
        text = json.dumps(packet["model_input"], sort_keys=True)
        lower = text.lower()
        for fragment in forbidden_fragments:
            testcase.assertNotIn(fragment, text)
        for key in forbidden_keys:
            testcase.assertNotIn('"%s"' % key, text)
        for label in (" false-pass", " pass", " fail", " trap", " good"):
            testcase.assertNotIn(label, lower)


class BuildCases(unittest.TestCase):
    def test_ac1_ac2_ac3_ac7_ac9_build_is_deterministic_and_sanitized(self):
        tmp, root = _fixture_root()
        self.addCleanup(tmp.cleanup)
        first = hmb.build_cases(root, max_gap_cases=20, max_eval_cases=20)
        second = hmb.build_cases(root, max_gap_cases=20, max_eval_cases=20)
        self.assertEqual(first, second)
        self.assertEqual(len([p for p in first if p["lane"] == "plan_check_gap"]), 7)
        eval_packets = [p for p in first if p["lane"] == "active_eval_case"]
        self.assertEqual(len(eval_packets), 1)
        self.assertEqual(eval_packets[0]["source_path"], "loop-team/evals/cases/z-trap-fail-name.json")
        for packet in first:
            self.assertEqual(packet["schema"], hmb.SCHEMA)
            self.assertRegex(packet["case_id"], r"^case-\d{6}$")
            self.assertTrue(packet["source_path"].startswith("loop-team/"))
            self.assertEqual(len(packet["source_sha256"]), 64)
            self.assertEqual(len(packet["payload_sha256"]), 64)
            self.assertTrue(packet["role_targets"])
            payload = dict(packet)
            payload.pop("payload_sha256")
            self.assertEqual(packet["payload_sha256"], hmb._sha256_json(payload))
        _assert_model_input_boundary(self, first)

    def test_ac8_real_root_builds_both_lanes_stably_and_real_inputs_are_sanitized(self):
        first = hmb.build_cases(REPO_ROOT, max_gap_cases=3, max_eval_cases=3)
        second = hmb.build_cases(REPO_ROOT, max_gap_cases=3, max_eval_cases=3)
        self.assertEqual(first, second)
        self.assertGreater(len([p for p in first if p["lane"] == "plan_check_gap"]), 0)
        self.assertGreater(len([p for p in first if p["lane"] == "active_eval_case"]), 0)
        _assert_model_input_boundary(self, first)


class ScoreResponse(unittest.TestCase):
    def setUp(self):
        tmp, root = _fixture_root()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp
        self.packets = hmb.build_cases(root, max_gap_cases=20, max_eval_cases=20)
        self.gap = next(p for p in self.packets if p["lane"] == "plan_check_gap")
        self.active = next(p for p in self.packets if p["lane"] == "active_eval_case")

    def test_ac4_gap_response_passes_and_fail_closes(self):
        term = self.gap["oracle"]["expected_source_terms"][0]
        ok = {"case_id": self.gap["case_id"], "verdict": "GAP_FOUND",
              "summary": "grounded on %s" % term, "source_grounding": [term]}
        self.assertTrue(hmb.score_response(self.gap, ok)["passed"])
        self.assertTrue(hmb.score_response(self.gap, json.dumps(ok))["passed"])
        self.assertFalse(hmb.score_response(self.gap, "{bad json")["passed"])
        wrong_id = dict(ok, case_id="case-999999")
        self.assertFalse(hmb.score_response(self.gap, wrong_id)["passed"])
        wrong_verdict = dict(ok, verdict="PASS")
        self.assertFalse(hmb.score_response(self.gap, wrong_verdict)["passed"])
        no_grounding = dict(ok)
        no_grounding.pop("source_grounding")
        self.assertFalse(hmb.score_response(self.gap, no_grounding)["passed"])
        bare_mechanism = {
            "case_id": self.gap["case_id"],
            "verdict": "GAP_FOUND",
            "summary": "SENTINEL_MECHANISM_REF_LEAK",
            "source_grounding": ["SENTINEL_MECHANISM_REF_LEAK"],
        }
        scored = hmb.score_response(self.gap, bare_mechanism)
        self.assertFalse(scored["passed"])
        self.assertIn("missing expected source-term overlap", scored["reasons"])

    def test_ac4_active_response_uses_frozen_expected_verdict(self):
        ok = {"case_id": self.active["case_id"], "verdict": "FAIL", "summary": "rejects the case"}
        self.assertTrue(hmb.score_response(self.active, ok)["passed"])
        self.assertFalse(hmb.score_response(self.active, dict(ok, verdict="PASS"))["passed"])
        self.assertFalse(hmb.score_response(self.active, {"case_id": self.active["case_id"], "verdict": "FAIL"})["passed"])


class CliAndMatrix(unittest.TestCase):
    def setUp(self):
        tmp, root = _fixture_root()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp
        self.root = root
        self.packets = hmb.build_cases(root, max_gap_cases=2, max_eval_cases=1)

    def test_ac5_cli_build_and_score_emit_json(self):
        build_out = subprocess.check_output([
            sys.executable, str(Path(EVALS_DIR) / "hard_model_benchmark.py"),
            "build", "--root", str(self.root), "--json",
        ], text=True)
        cases = json.loads(build_out)
        self.assertTrue(cases)
        responses = []
        for packet in cases[:2]:
            if packet["lane"] == "plan_check_gap":
                term = packet["oracle"]["expected_source_terms"][0]
                response = {"case_id": packet["case_id"], "verdict": "GAP_FOUND",
                            "summary": term, "source_grounding": [term]}
            else:
                response = {"case_id": packet["case_id"], "verdict": packet["oracle"]["expected_verdict"],
                            "summary": "ok"}
            responses.append({"provider": "openai", "model": "gpt-test", "effort": "high",
                              "case_id": packet["case_id"], "response": response})
        cases_path = self.root / "cases.json"
        responses_path = self.root / "responses.json"
        cases_path.write_text(json.dumps(cases[:2]), encoding="utf-8")
        responses_path.write_text(json.dumps(responses), encoding="utf-8")
        score_out = subprocess.check_output([
            sys.executable, str(Path(EVALS_DIR) / "hard_model_benchmark.py"),
            "score", "--cases", str(cases_path), "--responses", str(responses_path),
        ], text=True)
        report = json.loads(score_out)
        self.assertEqual(report["schema"], "loop_team_hard_model_score_matrix.v1")
        self.assertEqual(report["arms"]["openai:gpt-test:high"]["passed_cases"], 2)

    def test_ac12_ac13_ac14_matrix_scores_joint_arms_and_honest_telemetry(self):
        gap = next(p for p in self.packets if p["lane"] == "plan_check_gap")
        active = next(p for p in self.packets if p["lane"] == "active_eval_case")
        term = gap["oracle"]["expected_source_terms"][0]
        rows = [
            {"provider": "openai", "model": "m", "effort": "high", "case_id": gap["case_id"],
             "response": {"case_id": gap["case_id"], "verdict": "GAP_FOUND", "summary": term,
                          "source_grounding": [term]},
             "latency_ms": 100, "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
             "estimated_cost_usd": 0.01, "cost_authority": "local_static_rate"},
            {"provider": "openai", "model": "m", "effort": "medium", "case_id": gap["case_id"],
             "response": {"case_id": gap["case_id"], "verdict": "PASS", "summary": "wrong"}},
            {"provider": "claude", "model": "m", "effort": "high", "case_id": active["case_id"],
             "response": json.dumps({"case_id": active["case_id"],
                                     "verdict": active["oracle"]["expected_verdict"],
                                     "summary": "ok"}),
             "latency_ms": 200, "usage": {"input_tokens": 8, "output_tokens": 4},
             "authoritative_cost_usd": 0.02, "cost_authority": "billing_surface"},
        ]
        report = hmb.score_matrix(self.packets, rows)
        self.assertIn("openai:m:high", report["arms"])
        self.assertIn("openai:m:medium", report["arms"])
        self.assertIn("claude:m:high", report["arms"])
        self.assertEqual(hmb.arm_id({"provider": "openai", "model": "m", "effort": "high"}), "openai:m:high")
        self.assertEqual(hmb.arm_id({"provider": "openai", "model": "m", "effort": None}), "openai:m:none")
        self.assertTrue(report["cases"][gap["case_id"]]["openai:m:high"]["passed"])
        self.assertFalse(report["cases"][gap["case_id"]]["openai:m:medium"]["passed"])
        self.assertEqual(report["arms"]["openai:m:high"]["total_observed_tokens"], 15)
        self.assertEqual(report["arms"]["claude:m:high"]["total_observed_tokens"], 12)
        self.assertIsNone(report["arms"]["openai:m:medium"]["estimated_cost_usd"])
        self.assertIn("usage", report["arms"]["openai:m:medium"]["missing_telemetry_dimensions"])
        self.assertIn("authoritative_cost_usd", report["arms"]["openai:m:high"]["missing_telemetry_dimensions"])
        self.assertEqual(report["quality_ranking"][0], "claude:m:high")


class FakeSubscriptionAdapter:
    def __init__(self, arm, results=None, auth_mode=None, route_type=None, **attrs):
        self.arm = arm
        self.results = list(results or [])
        self.calls = []
        self.auth_mode = auth_mode or hmb.EXPECTED_AUTH_MODES[arm]
        if route_type is not None:
            self.route_type = route_type
        for key, value in attrs.items():
            setattr(self, key, value)

    def execute(self, packet):
        self.calls.append(packet["case_id"])
        if self.results:
            result = self.results.pop(0)
            if isinstance(result, BaseException):
                raise result
            return result
        return {"status": "succeeded", "response": {"case_id": packet["case_id"], "verdict": "OK"}}


def _tiny_packets(count=3):
    return [
        {"case_id": "case-%06d" % (index + 1), "model_input": {"task": "smoke"}}
        for index in range(count)
    ]


def _limits(**overrides):
    values = {
        "max_cases": 3,
        "enabled_arms": ("codex_subscription", "claude_code_subscription"),
        "max_attempts_per_case": 1,
        "max_retries_per_failure": 0,
        "max_concurrency": 1,
        "max_runtime_seconds": 30,
    }
    values.update(overrides)
    return hmb.SubscriptionBenchmarkLimits(**values)


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class SubscriptionSafeguards(unittest.TestCase):
    def test_caps_bound_cases_arms_attempts_retries_concurrency_and_runtime(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        adapter = FakeSubscriptionAdapter("codex_subscription", [
            hmb.TransientBenchmarkError("temporary local failure"),
            {"status": "succeeded", "response": "ok", "usage": {"input_tokens": 3}},
            {"status": "succeeded", "response": "ok", "usage": {"output_tokens": 4}},
        ])
        summary = hmb.run_subscription_scheduler(
            _tiny_packets(5),
            _limits(max_cases=1, enabled_arms=("codex_subscription",),
                    max_attempts_per_case=2, max_retries_per_failure=1,
                    max_concurrency=1, max_runtime_seconds=30),
            {"codex_subscription": adapter},
            result_path,
            run_id="run-caps",
        )
        records = _records(result_path)
        self.assertEqual(summary["scheduled_calls"], 2)
        self.assertEqual(summary["max_concurrency"], 1)
        self.assertEqual([r["case_id"] for r in records], ["case-000001", "case-000001"])
        self.assertEqual([r["attempt_number"] for r in records], [1, 2])
        self.assertEqual(records[0]["retry_count"], 1)
        self.assertEqual(records[0]["adapter_attempts"], 2)
        self.assertEqual(adapter.calls, ["case-000001", "case-000001", "case-000001"])

    def test_codex_subscription_limit_marks_arm_and_stops_new_codex_work(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        codex = FakeSubscriptionAdapter("codex_subscription", [
            {"status": "failed", "error_code": "rate_limit_error", "message": "usage cap reached"},
        ])
        claude = FakeSubscriptionAdapter("claude_code_subscription")
        summary = hmb.run_subscription_scheduler(
            _tiny_packets(3), _limits(max_concurrency=1),
            {"codex_subscription": codex, "claude_code_subscription": claude},
            result_path, run_id="run-limit-codex",
        )
        records = _records(result_path)
        self.assertEqual(codex.calls, ["case-000001"])
        self.assertEqual(claude.calls, ["case-000001", "case-000002", "case-000003"])
        self.assertIn("codex_subscription", summary["limited_arms"])
        limited = next(r for r in records if r["arm_id"] == "codex_subscription")
        self.assertEqual(limited["status"], "subscription_limited")
        self.assertEqual(limited["failure_category"], "rate_limited")
        self.assertNotEqual(limited["failure_category"], "provider_failure")

    def test_claude_subscription_limit_marks_arm_and_stops_new_claude_work(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        codex = FakeSubscriptionAdapter("codex_subscription")
        claude = FakeSubscriptionAdapter("claude_code_subscription", [
            hmb.SubscriptionLimitError("Claude Code cooldown active", "cooldown"),
        ])
        summary = hmb.run_subscription_scheduler(
            _tiny_packets(3), _limits(max_concurrency=1),
            {"codex_subscription": codex, "claude_code_subscription": claude},
            result_path, run_id="run-limit-claude",
        )
        self.assertEqual(codex.calls, ["case-000001", "case-000002", "case-000003"])
        self.assertEqual(claude.calls, ["case-000001"])
        self.assertIn("claude_code_subscription", summary["limited_arms"])
        limited = [r for r in _records(result_path) if r["arm_id"] == "claude_code_subscription"][0]
        self.assertEqual(limited["status"], "subscription_limited")
        self.assertEqual(limited["failure_category"], "cooldown")

    def test_resume_skips_completed_work_and_preserves_partial_results(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        original = {
            "schema": hmb.SUBSCRIPTION_RESULT_SCHEMA,
            "run_id": "resume-run",
            "matrix": "full",
            "case_id": "case-000001",
            "arm_id": "codex_subscription",
            "attempt_number": 1,
            "status": "succeeded",
            "latency_ms": 12,
            "usage": None,
        }
        result_path.write_text(json.dumps(original, sort_keys=True) + "\n", encoding="utf-8")
        adapter = FakeSubscriptionAdapter("codex_subscription")
        hmb.run_subscription_scheduler(
            _tiny_packets(2),
            _limits(max_cases=2, enabled_arms=("codex_subscription",)),
            {"codex_subscription": adapter},
            result_path,
            run_id="resume-run",
        )
        records = _records(result_path)
        self.assertEqual(records[0], original)
        self.assertEqual(adapter.calls, ["case-000002"])
        self.assertEqual(len(records), 2)

    def test_telemetry_records_latency_failures_attempts_and_unknown_usage_not_zero(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        adapter = FakeSubscriptionAdapter("codex_subscription", [
            {"status": "failed", "failure_category": "model_error", "message": "bad output"},
            {"status": "succeeded", "response": "ok"},
        ])
        hmb.run_subscription_scheduler(
            _tiny_packets(2),
            _limits(max_cases=2, enabled_arms=("codex_subscription",)),
            {"codex_subscription": adapter},
            result_path,
            run_id="telemetry-run",
        )
        first, second = _records(result_path)
        self.assertIsInstance(first["latency_ms"], int)
        self.assertGreaterEqual(first["latency_ms"], 0)
        self.assertEqual(first["attempt_number"], 1)
        self.assertEqual(first["failure_category"], "model_error")
        self.assertEqual(first["status"], "failed")
        self.assertIsNone(first["usage"])
        self.assertIsNone(second["usage"])
        self.assertNotEqual(first["usage"], 0)
        self.assertNotEqual(second["usage"], 0)

    def test_runtime_cap_stops_scheduling_new_work(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        adapter = FakeSubscriptionAdapter("codex_subscription")
        original_monotonic = hmb.time.monotonic
        ticks = [0.0, 31.0]
        hmb.time.monotonic = lambda: ticks.pop(0) if ticks else 31.0
        try:
            summary = hmb.run_subscription_scheduler(
                _tiny_packets(2),
                _limits(max_cases=2, enabled_arms=("codex_subscription",), max_runtime_seconds=30),
                {"codex_subscription": adapter},
                result_path,
                run_id="runtime-stop",
            )
        finally:
            hmb.time.monotonic = original_monotonic
        self.assertEqual(summary["scheduled_calls"], 0)
        self.assertIn("max_runtime_seconds", summary["stop_reasons"])
        self.assertEqual(adapter.calls, [])
        self.assertFalse(result_path.exists())

    def test_api_keys_do_not_enable_openai_or_anthropic_api_fallback(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        old_openai = os.environ.get("OPENAI_API_KEY")
        old_anthropic = os.environ.get("ANTHROPIC_API_KEY")
        os.environ["OPENAI_API_KEY"] = "sk-test-openai-do-not-use"
        os.environ["ANTHROPIC_API_KEY"] = "sk-test-anthropic-do-not-use"
        try:
            result_path = Path(tmp.name) / "results.jsonl"
            codex = FakeSubscriptionAdapter("codex_subscription")
            claude = FakeSubscriptionAdapter("claude_code_subscription")
            hmb.run_subscription_scheduler(
                _tiny_packets(1), _limits(max_cases=1),
                {"codex_subscription": codex, "claude_code_subscription": claude},
                result_path, run_id="env-keys-ignored",
            )
            self.assertEqual(codex.calls, ["case-000001"])
            self.assertEqual(claude.calls, ["case-000001"])
        finally:
            if old_openai is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = old_openai
            if old_anthropic is None:
                os.environ.pop("ANTHROPIC_API_KEY", None)
            else:
                os.environ["ANTHROPIC_API_KEY"] = old_anthropic

    def test_direct_api_and_paid_credit_routes_are_rejected_before_execution(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        with self.assertRaises(hmb.SubscriptionOnlyViolation):
            hmb.run_subscription_scheduler(
                _tiny_packets(1), _limits(enabled_arms=("openai_api",)), {},
                result_path, run_id="bad-arm",
            )
        bad_adapter = FakeSubscriptionAdapter("codex_subscription", route_type="openai_api")
        with self.assertRaises(hmb.SubscriptionOnlyViolation):
            hmb.run_subscription_scheduler(
                _tiny_packets(1), _limits(enabled_arms=("codex_subscription",)),
                {"codex_subscription": bad_adapter}, result_path, run_id="bad-route",
            )
        self.assertEqual(bad_adapter.calls, [])
        paid_adapter = FakeSubscriptionAdapter(
            "claude_code_subscription", purchase_credits=lambda: (_ for _ in ()).throw(AssertionError("called"))
        )
        with self.assertRaises(hmb.SubscriptionOnlyViolation):
            hmb.run_subscription_scheduler(
                _tiny_packets(1), _limits(enabled_arms=("claude_code_subscription",)),
                {"claude_code_subscription": paid_adapter}, result_path, run_id="bad-paid",
            )
        self.assertEqual(paid_adapter.calls, [])

    def test_subscription_auth_unavailable_fails_closed_without_fallback(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        adapter = FakeSubscriptionAdapter("codex_subscription", [
            hmb.SubscriptionAuthUnavailableError("ChatGPT subscription auth unavailable"),
        ])
        summary = hmb.run_subscription_scheduler(
            _tiny_packets(1), _limits(enabled_arms=("codex_subscription",)),
            {"codex_subscription": adapter}, result_path, run_id="auth-missing",
        )
        self.assertEqual(summary["scheduled_calls"], 1)
        record = _records(result_path)[0]
        self.assertEqual(record["status"], "auth_unavailable")
        self.assertEqual(record["failure_category"], "subscription_auth_unavailable")
        self.assertEqual(adapter.calls, ["case-000001"])

    def test_smoke_matrix_gate_persists_records_before_full_launch(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        codex = FakeSubscriptionAdapter("codex_subscription", [
            {"status": "succeeded", "response": "smoke", "usage": None},
            {"status": "succeeded", "response": "full", "usage": {"total_tokens": 7}},
        ])
        claude = FakeSubscriptionAdapter("claude_code_subscription", [
            {"status": "succeeded", "response": "smoke", "usage": {"input_tokens": 1}},
            {"status": "succeeded", "response": "full", "usage": None},
        ])
        report = hmb.launch_subscription_benchmark(
            _tiny_packets(2), _limits(max_cases=2),
            {"codex_subscription": codex, "claude_code_subscription": claude},
            result_path, run_id="smoke-then-full",
        )
        records = _records(result_path)
        smoke = [r for r in records if r["matrix"] == "smoke"]
        full = [r for r in records if r["matrix"] == "full"]
        self.assertTrue(report["full_launched"])
        self.assertEqual(len(smoke), 2)
        self.assertEqual({r["arm_id"] for r in smoke}, {"codex_subscription", "claude_code_subscription"})
        self.assertTrue(all("latency_ms" in r and "attempt_number" in r and "usage" in r for r in smoke))
        self.assertEqual([r["case_id"] for r in full], ["case-000002", "case-000002"])

    def test_full_benchmark_refuses_to_launch_when_smoke_fails(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        result_path = Path(tmp.name) / "results.jsonl"
        codex = FakeSubscriptionAdapter("codex_subscription", [
            {"status": "failed", "failure_category": "model_error", "message": "smoke failed"},
        ])
        report = hmb.launch_subscription_benchmark(
            _tiny_packets(2), _limits(enabled_arms=("codex_subscription",), max_cases=2),
            {"codex_subscription": codex}, result_path, run_id="smoke-fails",
        )
        self.assertFalse(report["full_launched"])
        self.assertEqual(report["blocked_reason"], "smoke_matrix_not_passed")
        self.assertEqual(codex.calls, ["case-000001"])



class ExistingSuiteUnaffected(unittest.TestCase):
    def test_ac6_run_evals_contract_still_imports(self):
        import run_evals
        self.assertIn(run_evals.classify("PASS", "PASS"), ("ok",))


if __name__ == "__main__":
    unittest.main()
