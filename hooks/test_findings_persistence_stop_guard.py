#!/usr/bin/env python3
"""Contract tests for H-FINDINGS-PERSISTENCE-1 v2.

These tests intentionally encode the approved Stop-hook contract before the
production gate exists. They drive hooks/loop_stop_guard.py as a subprocess
with realistic dispatch/result transcript entries and temporary target repos.

Run with:
    python3 -m pytest hooks/test_findings_persistence_stop_guard.py -q
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid


HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HOOKS_DIR, "loop_stop_guard.py")
LOOP_ROOT = os.path.realpath(os.path.join(HOOKS_DIR, ".."))


def _write_jsonl(events, path):
    with open(path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def _tool_use(name, tool_id, **inp):
    return {"type": "tool_use", "name": name, "id": tool_id, "input": inp}


def _assistant_msg(*parts):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(parts)}}


def _human_turn_start():
    return {"type": "user", "message": {"role": "user", "content": "run the review"}}


def _tool_result_event(tool_use_id, content, is_error=False):
    part = {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}
    if is_error:
        part["is_error"] = True
    return {"type": "user", "message": {"role": "user", "content": [part]}}


def _dispatch_tool(tool_name, tool_id, dispatch_text):
    if tool_name == "Workflow":
        return _tool_use(tool_name, tool_id, script=dispatch_text)
    return _tool_use(
        tool_name,
        tool_id,
        description="adversarial bug-hunt findings contract",
        prompt=dispatch_text,
    )


def _marked_dispatch_text(target_repo=None, run_id="fp-run-001", extra=""):
    lines = [
        "Adversarial bug-hunt findings contract.",
        "FINDINGS_PERSISTENCE_REQUIRED",
    ]
    if target_repo is not None:
        lines.append("TARGET_REPO=%s" % target_repo)
    if run_id is not None:
        lines.append("FINDINGS_RUN_ID=%s" % run_id)
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def _structured_result(findings, status="completed"):
    return json.dumps({"status": status, "findings": findings}, indent=2)


def _confirmed(title, component="calendar-sync", severity="HIGH"):
    return {
        "verdict": "CONFIRMED",
        "title": title,
        "component": component,
        "severity": severity,
        "description": "A real defect in %s that affects persisted behavior." % component,
    }


def _non_confirmed(verdict):
    return {
        "verdict": verdict,
        "title": "%s candidate" % verdict,
        "component": "calendar-sync",
        "description": "Candidate that must not trigger persistence.",
    }


def _review_turn(*dispatches):
    parts = []
    results = []
    for dispatch in dispatches:
        tool_id = dispatch.get("tool_id", "review-%s" % uuid.uuid4().hex)
        parts.append(_dispatch_tool(dispatch.get("tool_name", "Agent"), tool_id, dispatch["text"]))
        results.append(_tool_result_event(
            tool_id,
            dispatch.get("result", ""),
            is_error=dispatch.get("is_error", False),
        ))
    return [_human_turn_start(), _assistant_msg(*parts)] + results


def _run_guard(events, env_extra=None):
    gate_dir = tempfile.mkdtemp(prefix="findings-gate-")
    fd, transcript = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        _write_jsonl(events, transcript)
        payload = {"transcript_path": transcript, "stop_hook_active": False}
        env = dict(os.environ, LOOP_GATE_DIR=gate_dir)
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, GUARD],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
        )
        return proc.returncode, proc.stderr
    finally:
        os.remove(transcript)
        shutil.rmtree(gate_dir, ignore_errors=True)


class FindingsPersistenceContract(unittest.TestCase):
    def setUp(self):
        self._cleanup_dirs = []

    def tearDown(self):
        for path in self._cleanup_dirs:
            shutil.rmtree(path, ignore_errors=True)

    def _mkrepo(self):
        root = tempfile.mkdtemp(prefix="findings-target-")
        self._cleanup_dirs.append(root)
        subprocess.run(["git", "-C", root, "init", "-q"], check=True)
        os.makedirs(os.path.join(root, "src"), exist_ok=True)
        with open(os.path.join(root, "src", "calendar.py"), "w", encoding="utf-8") as f:
            f.write("def sync():\n    return True\n")
        return root

    def _write_ledger(self, root, run_id, entries, preamble=""):
        path = os.path.join(root, "KNOWN_ISSUES.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Known Issues\n\n")
            if preamble:
                f.write(preamble.rstrip() + "\n\n")
            if run_id:
                f.write("FINDINGS_RUN_ID=%s\n\n" % run_id)
            for entry in entries:
                f.write(entry.rstrip() + "\n\n")
        return path

    def _issue_entry(self, title, component="calendar-sync"):
        return (
            "## %s\n"
            "Component: %s\n"
            "Severity: HIGH\n"
            "Status: confirmed\n"
            "The %s path has a durable behavior defect that requires code changes."
        ) % (title, component, component)

    def _placeholder_entry(self):
        return "## TODO\nComponent: TBD\nStatus: pending\nMore details later."

    def _assert_blocked_for_findings(self, events, expected_text):
        code, err = _run_guard(events)
        self.assertEqual(code, 2, err)
        self.assertIn("FINDINGS_PERSISTENCE", err)
        self.assertIn(expected_text, err)

    def test_marked_agent_confirmed_finding_without_known_issues_blocks_and_names_path(self):
        repo = self._mkrepo()
        finding = _confirmed("Reservation cancellation leaves stale iCal event")
        events = _review_turn({
            "tool_name": "Agent",
            "text": _marked_dispatch_text(repo, "fp-run-missing-ledger"),
            "result": _structured_result([finding]),
        })

        self._assert_blocked_for_findings(
            events, os.path.join(repo, "KNOWN_ISSUES.md"))

    def test_marked_task_confirmed_finding_with_current_run_id_and_strong_match_passes(self):
        repo = self._mkrepo()
        title = "Reservation cancellation leaves stale iCal event"
        self._write_ledger(repo, "fp-run-pass", [self._issue_entry(title)])
        events = _review_turn({
            "tool_name": "Task",
            "text": _marked_dispatch_text(repo, "fp-run-pass"),
            "result": _structured_result([_confirmed(title)]),
        })

        code, err = _run_guard(events)
        self.assertEqual(code, 0, err)

    def test_dirty_uncommitted_ledger_delta_without_current_run_id_blocks(self):
        repo = self._mkrepo()
        title = "Reservation cancellation leaves stale iCal event"
        self._write_ledger(repo, None, [self._issue_entry(title)])
        events = _review_turn({
            "text": _marked_dispatch_text(repo, "fp-run-required"),
            "result": _structured_result([_confirmed(title)]),
        })

        self._assert_blocked_for_findings(events, "FINDINGS_RUN_ID=fp-run-required")

    def test_dirty_baseline_plus_current_run_id_and_title_passes(self):
        repo = self._mkrepo()
        title = "Reservation cancellation leaves stale iCal event"
        stale = "## Old calendar-sync issue\nComponent: calendar-sync\nStatus: confirmed"
        self._write_ledger(repo, "fp-run-current", [stale, self._issue_entry(title)])
        events = _review_turn({
            "text": _marked_dispatch_text(repo, "fp-run-current"),
            "result": _structured_result([_confirmed(title)]),
        })

        code, err = _run_guard(events)
        self.assertEqual(code, 0, err)

    def test_generic_common_file_token_only_in_stale_dirty_delta_blocks(self):
        repo = self._mkrepo()
        self._write_ledger(repo, "older-run", [
            "## calendar.py issue\nComponent: files\nStatus: confirmed\nMentions src/calendar.py only."
        ])
        events = _review_turn({
            "text": _marked_dispatch_text(repo, "fp-run-token-only"),
            "result": _structured_result([_confirmed(
                "Reservation cancellation leaves stale iCal event")]),
        })

        self._assert_blocked_for_findings(events, "fp-run-token-only")

    def test_placeholder_padding_under_current_run_id_blocks(self):
        repo = self._mkrepo()
        self._write_ledger(repo, "fp-run-placeholder", [self._placeholder_entry()])
        events = _review_turn({
            "text": _marked_dispatch_text(repo, "fp-run-placeholder"),
            "result": _structured_result([_confirmed("Webhook retry drops failures")]),
        })

        self._assert_blocked_for_findings(events, "substantive")

    def test_workflow_fallback_confirmed_count_five_one_entry_blocks_three_entries_pass(self):
        repo_one = self._mkrepo()
        repo_three = self._mkrepo()
        run_one = "fp-run-fallback-one"
        run_three = "fp-run-fallback-three"
        fallback_one = (
            "{malformed json\n"
            "CONFIRMED FINDINGS: 5\n"
            "1. Calendar cancellation remains visible to guests.\n"
        )
        fallback_three = (
            "{malformed json\n"
            "CONFIRMED FINDINGS: 5\n"
            "1. Calendar cancellation remains visible to guests.\n"
            "2. Import dedupe skips overlapping reservations.\n"
            "3. Retry failure is swallowed without alerting.\n"
        )
        self._write_ledger(repo_one, run_one, [
            self._issue_entry("Calendar cancellation remains visible to guests")
        ])
        self._write_ledger(repo_three, run_three, [
            self._issue_entry("Calendar cancellation remains visible to guests"),
            self._issue_entry("Import dedupe skips overlapping reservations", "importer"),
            self._issue_entry("Retry failure is swallowed without alerting", "retry-worker"),
        ])

        code_one, err_one = _run_guard(_review_turn({
            "tool_name": "Workflow",
            "text": _marked_dispatch_text(repo_one, run_one),
            "result": fallback_one,
        }))
        self.assertEqual(code_one, 2, err_one)
        self.assertIn("FINDINGS_PERSISTENCE", err_one)
        self.assertIn("3", err_one)

        code_three, err_three = _run_guard(_review_turn({
            "tool_name": "Workflow",
            "text": _marked_dispatch_text(repo_three, run_three),
            "result": fallback_three,
        }))
        self.assertEqual(code_three, 0, err_three)

    def test_plausible_refuted_false_positive_only_has_no_requirement(self):
        repo = self._mkrepo()
        events = _review_turn({
            "text": _marked_dispatch_text(repo, "fp-run-non-confirmed"),
            "result": _structured_result([
                _non_confirmed("PLAUSIBLE"),
                _non_confirmed("REFUTED"),
                _non_confirmed("FALSE_POSITIVE"),
            ]),
        })

        code, err = _run_guard(events)
        self.assertEqual(code, 0, err)

    def test_denied_errored_blocked_marked_result_has_no_requirement(self):
        repo = self._mkrepo()
        events = _review_turn({
            "text": _marked_dispatch_text(repo, "fp-run-denied"),
            "result": "Hook PreToolUse: denied this tool call before dispatch",
            "is_error": True,
        })

        code, err = _run_guard(events)
        self.assertEqual(code, 0, err)

    def test_missing_target_repo_or_missing_invalid_run_id_with_confirmed_findings_blocks(self):
        repo = self._mkrepo()
        cases = [
            (_marked_dispatch_text(None, "fp-run-no-target"), "TARGET_REPO"),
            (_marked_dispatch_text(repo, None), "FINDINGS_RUN_ID"),
            (_marked_dispatch_text(repo, "not a valid run id"), "FINDINGS_RUN_ID"),
        ]
        for dispatch_text, expected in cases:
            with self.subTest(dispatch_text=dispatch_text):
                events = _review_turn({
                    "text": dispatch_text,
                    "result": _structured_result([_confirmed("Webhook retry drops failures")]),
                })
                self._assert_blocked_for_findings(events, expected)

    def test_relative_or_nonexistent_target_repo_blocks(self):
        cases = ["relative/repo", "/definitely/not/a/real/repo/%s" % uuid.uuid4().hex]
        for target in cases:
            with self.subTest(target=target):
                events = _review_turn({
                    "text": _marked_dispatch_text(target, "fp-run-bad-target"),
                    "result": _structured_result([_confirmed("Webhook retry drops failures")]),
                })
                self._assert_blocked_for_findings(events, "TARGET_REPO")

    def test_loop_root_target_requires_dispatch_marker_not_env_override(self):
        title = "Loop root review persistence escape hatch"
        ledger = os.path.join(LOOP_ROOT, "KNOWN_ISSUES.md")
        original_exists = os.path.exists(ledger)
        original = None
        if original_exists:
            with open(ledger, encoding="utf-8") as f:
                original = f.read()

        def restore():
            if original_exists:
                with open(ledger, "w", encoding="utf-8") as f:
                    f.write(original)
            else:
                try:
                    os.remove(ledger)
                except FileNotFoundError:
                    pass

        self.addCleanup(restore)
        self._write_ledger(LOOP_ROOT, "fp-run-loop-root", [self._issue_entry(title)])
        events = _review_turn({
            "text": _marked_dispatch_text(LOOP_ROOT, "fp-run-loop-root"),
            "result": _structured_result([_confirmed(title, component="loop-hooks")]),
        })
        marked_events = _review_turn({
            "text": _marked_dispatch_text(
                LOOP_ROOT,
                "fp-run-loop-root",
                extra="TARGET_REPO_IS_LOOP_FRAMEWORK=1",
            ),
            "result": _structured_result([_confirmed(title, component="loop-hooks")]),
        })

        code_block, err_block = _run_guard(events)
        self.assertEqual(code_block, 2, err_block)
        self.assertIn("loop root", err_block.lower())

        code_env, err_env = _run_guard(
            events,
            env_extra={"FINDINGS_PERSISTENCE_ALLOW_LOOP_ROOT": "1"},
        )
        self.assertEqual(code_env, 2, err_env)
        self.assertIn("TARGET_REPO_IS_LOOP_FRAMEWORK=1", err_env)

        code_pass, err_pass = _run_guard(marked_events)
        self.assertEqual(code_pass, 0, err_pass)

    def test_unmarked_routine_code_review_security_review_confirmed_looking_result_no_block(self):
        repo = self._mkrepo()
        routine = (
            "Routine code-review/security-review dispatch for %s. "
            "TARGET_REPO=%s FINDINGS_RUN_ID=fp-run-unmarked"
        ) % (repo, repo)
        events = _review_turn({
            "text": routine,
            "result": _structured_result([_confirmed("Looks confirmed but unmarked")]),
        })

        code, err = _run_guard(events)
        self.assertEqual(code, 0, err)

    def test_subagent_marked_confirmed_dispatch_is_in_scope(self):
        repo = self._mkrepo()
        events = _review_turn({
            "tool_name": "Subagent",
            "text": _marked_dispatch_text(repo, "fp-run-subagent"),
            "result": _structured_result([_confirmed("Subagent confirmed defect")]),
        })

        self._assert_blocked_for_findings(events, os.path.join(repo, "KNOWN_ISSUES.md"))

    def test_duplicate_and_refuted_entries_count_only_unique_confirmed_findings(self):
        repo = self._mkrepo()
        title = "Reservation cancellation leaves stale iCal event"
        self._write_ledger(repo, "fp-run-dedupe", [self._issue_entry(title)])
        events = _review_turn({
            "text": _marked_dispatch_text(repo, "fp-run-dedupe"),
            "result": _structured_result([
                _confirmed(title),
                _confirmed(title),
                _non_confirmed("REFUTED"),
            ]),
        })

        code, err = _run_guard(events)
        self.assertEqual(code, 0, err)

    def test_nested_target_repo_path_resolves_to_repo_root_ledger(self):
        repo = self._mkrepo()
        nested = os.path.join(repo, "src", "deep")
        os.makedirs(nested, exist_ok=True)
        title = "Nested target resolves to root ledger"
        self._write_ledger(repo, "fp-run-nested", [self._issue_entry(title)])
        events = _review_turn({
            "text": _marked_dispatch_text(nested, "fp-run-nested"),
            "result": _structured_result([_confirmed(title)]),
        })

        code, err = _run_guard(events)
        self.assertEqual(code, 0, err)

    def test_multiple_marked_reviews_one_missing_ledger_blocks(self):
        repo_ok = self._mkrepo()
        repo_missing = self._mkrepo()
        title_ok = "Persisted review finding"
        title_missing = "Unpersisted review finding"
        self._write_ledger(repo_ok, "fp-run-multi-ok", [self._issue_entry(title_ok)])
        events = _review_turn(
            {
                "tool_id": "review-ok",
                "text": _marked_dispatch_text(repo_ok, "fp-run-multi-ok"),
                "result": _structured_result([_confirmed(title_ok)]),
            },
            {
                "tool_id": "review-missing",
                "text": _marked_dispatch_text(repo_missing, "fp-run-multi-missing"),
                "result": _structured_result([_confirmed(title_missing)]),
            },
        )

        self._assert_blocked_for_findings(
            events, os.path.join(repo_missing, "KNOWN_ISSUES.md"))

    def test_malformed_json_with_fallback_phrase_enforces_fallback_without_phrase_no_trigger(self):
        repo = self._mkrepo()
        malformed_with_phrase = "{not json\nCONFIRMED FINDINGS: 1\n- Webhook retry drops failures."
        malformed_without_phrase = "{not json\n- Webhook retry drops failures."

        events_with = _review_turn({
            "tool_name": "Workflow",
            "text": _marked_dispatch_text(repo, "fp-run-malformed-with"),
            "result": malformed_with_phrase,
        })
        self._assert_blocked_for_findings(events_with, os.path.join(repo, "KNOWN_ISSUES.md"))

        events_without = _review_turn({
            "tool_name": "Workflow",
            "text": _marked_dispatch_text(repo, "fp-run-malformed-without"),
            "result": malformed_without_phrase,
        })
        code, err = _run_guard(events_without)
        self.assertEqual(code, 0, err)

    def test_different_findings_run_id_ledger_does_not_satisfy_current_run(self):
        repo = self._mkrepo()
        title = "Reservation cancellation leaves stale iCal event"
        self._write_ledger(repo, "fp-run-other", [self._issue_entry(title)])
        events = _review_turn({
            "text": _marked_dispatch_text(repo, "fp-run-current"),
            "result": _structured_result([_confirmed(title)]),
        })

        self._assert_blocked_for_findings(events, "fp-run-current")

    def test_current_run_id_section_with_no_issue_substance_blocks(self):
        repo = self._mkrepo()
        self._write_ledger(repo, "fp-run-empty-section", [])
        events = _review_turn({
            "text": _marked_dispatch_text(repo, "fp-run-empty-section"),
            "result": _structured_result([_confirmed("Webhook retry drops failures")]),
        })

        self._assert_blocked_for_findings(events, "substantive")


if __name__ == "__main__":
    unittest.main()
