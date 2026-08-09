#!/usr/bin/env python3
# test_plugin.py -- BEHAVIOR tests for the kanban closure adapter plugin.
#
# Usage:  python3 test_plugin.py
#
# Behaviorally drives the `pre_tool_call` callback of the (not-yet-written)
# kanban_closure_gate.plugin.py against:
#   * a temp sqlite kanban DB mirroring the real ~/.hermes/kanban.db
#     `tasks` schema (id, branch_name, ...),
#   * a branches.conf mapping file (lines `codex/<slice-id> -> <owner>/<repo>`),
#   * a PATH-stubbed recompute_verdict.sh delivering canned GREEN / RED /
#     crash / hang outcomes.
#
# Loader-independent by design: the plugin is imported as a plain stdlib
# module (importlib) -- no Hermes imports, no pytest.
#
# CALLBACK CONTRACT (fixed by this harness; written for the implementer):
#   The plugin module exposes a `pre_tool_call` callback (name contains
#   "pre_tool_call", e.g. closure_gate_pre_tool_call) callable with kwargs
#   tool_name (str), args (dict), task_id (str), and optionally ctx
#   (an object carrying config; the harness passes a SimpleNamespace with
#   kanban_db_path / branches_conf_path / required_context). Return values:
#       None                                        -> allow the tool call
#       {"action": "block", "message": <non-empty>} -> block the tool call
#   Any other shape, an empty/missing message, or a raised exception is a
#   FAIL. Config may ALSO be read from the env (KANBAN_DB_PATH,
#   BRANCHES_CONF_PATH, CLOSURE_GATE_CONTEXT); the harness sets env + ctx
#   to the same values so either implementation style passes.

import importlib.util
import inspect
import os
import signal
import sqlite3
import sys
import tempfile
import textwrap
import time
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_FILE = os.path.join(HERE, "kanban_closure_gate.plugin.py")

REQUIRED_CONTEXT = "slice-closure-gate / slice-closure-gate"
MAPPED_BRANCH = "codex/slice-x"
REPO = "NEO-Venturez/wf-fix-test"


class FakeRecompute:
    """Writes an executable recompute_verdict.sh stub into a temp dir.

    The stub records its argv to $FAKE_STUB_LOG and behaves per
    $FAKE_STUB_MODE: green -> exit 0 / GREEN line; red -> exit 1 / RED line;
    crash -> exit 99; hang -> sleep 120 (must be killed by the plugin's
    own timeout).
    """

    def __init__(self, tmpdir, mode):
        self.dir = os.path.join(tmpdir, "bin")
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "recompute_verdict.sh")
        self.log = os.path.join(tmpdir, "recompute.log")
        body = textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            # fake recompute_verdict.sh -- reached via PATH
            if [ -n "${{FAKE_STUB_LOG:-}}" ]; then
                printf 'STUB|%s\\n' "$*" >> "$FAKE_STUB_LOG"
            fi
            case "$FAKE_STUB_MODE" in
                hang)  sleep 120 ;;
                green)
                    echo "GREEN {REPO} 0000000000000000 {REQUIRED_CONTEXT}"
                    exit 0
                    ;;
                red)
                    echo "RED {REPO} 0000000000000000 : one check run failed (stub red)"
                    exit 1
                    ;;
                crash)
                    echo "RED {REPO} 0000000000000000 : stub crashed" >&2
                    exit 99
                    ;;
                *)
                    echo "RED {REPO} 0000000000000000 : stub mode unset" >&2
                    exit 1
                    ;;
            esac
            """
        )
        with open(self.path, "w") as f:
            f.write(body)
        os.chmod(self.path, 0o755)
        self.mode = mode


class Harness:
    """One test environment: temp kanban DB + branches.conf + stub on PATH."""

    def __init__(self, mode):
        self.tmp = tempfile.mkdtemp(prefix="closure-gate-test-")
        self.db_path = os.path.join(self.tmp, "kanban.db")
        self.conf_path = os.path.join(self.tmp, "branches.conf")
        self.recompute = FakeRecompute(self.tmp, mode)
        with open(self.conf_path, "w") as f:
            f.write(f"{MAPPED_BRANCH} -> {REPO}\n")
        self._make_db(self.db_path)
        self.ctx = types.SimpleNamespace(
            kanban_db_path=self.db_path,
            branches_conf_path=self.conf_path,
            required_context=REQUIRED_CONTEXT,
        )
        os.environ["KANBAN_DB_PATH"] = self.db_path
        os.environ["BRANCHES_CONF_PATH"] = self.conf_path
        os.environ["CLOSURE_GATE_CONTEXT"] = REQUIRED_CONTEXT
        os.environ["FAKE_STUB_MODE"] = mode
        os.environ["FAKE_STUB_LOG"] = self.recompute.log
        os.environ["PATH"] = self.recompute.dir + os.pathsep + os.environ.get("PATH", "")

    def _make_db(self, db_path):
        conn = sqlite3.connect(db_path)
        conn.execute(
            # Minimal `tasks` schema mirroring ~/.hermes/kanban.db (column
            # names/constraints copied from the real DDL).
            """
            CREATE TABLE tasks (
                id                   TEXT PRIMARY KEY,
                title                TEXT NOT NULL,
                status               TEXT NOT NULL,
                created_at           INTEGER NOT NULL,
                workspace_kind       TEXT NOT NULL DEFAULT 'scratch',
                consecutive_failures INTEGER NOT NULL DEFAULT 0,
                goal_mode            INTEGER NOT NULL DEFAULT 0,
                block_recurrences    INTEGER NOT NULL DEFAULT 0,
                branch_name          TEXT
            );
            """
        )
        now_ms = int(time.time()) * 1000
        conn.executemany(
            "INSERT INTO tasks (id, title, status, created_at, branch_name) "
            "VALUES (?, ?, 'open', ?, ?)",
            [
                ("task-with-branch", "mapped task", now_ms, MAPPED_BRANCH),
                ("task-unmapped", "branch absent from conf", now_ms, "codex/slice-zzz"),
                ("task-no-branch", "no branch at all", now_ms, None),
            ],
        )
        conn.commit()
        conn.close()

    def load_plugin(self):
        """Import the plugin module as a plain stdlib module."""
        spec = importlib.util.spec_from_file_location(
            "kanban_closure_gate_plugin", PLUGIN_FILE
        )
        if spec is None or spec.loader is None:
            raise AssertionError(f"cannot build import spec for {PLUGIN_FILE}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def find_callback(self, module):
        """Return the module's pre_tool_call callback (name contains
        'pre_tool_call'), preferring the names documented in the spec."""
        candidates = [
            getattr(module, n)
            for n in sorted(vars(module))
            if callable(getattr(module, n, None)) and "pre_tool_call" in n
        ]
        if not candidates:
            raise AssertionError(
                "plugin exposes no callable whose name contains 'pre_tool_call'"
            )
        for name in (
            "closure_gate_pre_tool_call",
            "kanban_complete_pre_tool_call",
            "pre_tool_call",
        ):
            for c in candidates:
                if getattr(c, "__name__", "") == name:
                    return c
        return candidates[0]

    def call(self, tool_name, task_id):
        """Invoke the callback with kwargs the signature accepts."""
        module = self.load_plugin()
        cb = self.find_callback(module)
        params = list(inspect.signature(cb).parameters)
        kw = {}
        if "tool_name" in params:
            kw["tool_name"] = tool_name
        if "args" in params:
            kw["args"] = {}
        if "task_id" in params:
            kw["task_id"] = task_id
        if "ctx" in params:
            kw["ctx"] = self.ctx
        if kw:
            try:
                return cb(**kw)
            except TypeError:
                pass  # fall through to positional
        if len(params) >= 3:
            return cb(tool_name, task_id, self.ctx)
        return cb()

    def stub_log(self):
        try:
            with open(self.recompute.log) as f:
                return f.read()
        except FileNotFoundError:
            return ""


def assert_block(result):
    """[BEHAVIORAL] every returned action is exactly the directive shape
    {"action": "block", "message": <non-empty string>}."""
    assert isinstance(result, dict), f"block result must be a dict, got {result!r}"
    assert result.get("action") == "block", f"action must be 'block', got {result!r}"
    msg = result.get("message")
    assert isinstance(msg, str) and msg.strip(), \
        f"block message must be a non-empty string, got {msg!r}"


class TestClosureGate(unittest.TestCase):

    def test_green_allows(self):
        "[BEHAVIORAL] GREEN recompute -> callback returns None (allow)"
        h = Harness("green")
        self.assertIsNone(h.call("kanban_complete", "task-with-branch"))

    def test_green_passes_correct_arguments(self):
        "[BEHAVIORAL] plugin invokes recompute_verdict.sh with <repo> <branch> <context>"
        h = Harness("green")
        h.call("kanban_complete", "task-with-branch")
        log = h.stub_log()
        self.assertIn(REPO, log)
        self.assertIn(MAPPED_BRANCH, log)
        self.assertIn(REQUIRED_CONTEXT, log)

    def test_red_blocks(self):
        "[BEHAVIORAL] RED recompute -> block dict with non-empty message"
        h = Harness("red")
        assert_block(h.call("kanban_complete", "task-with-branch"))

    def test_branch_without_mapping_contract(self):
        "[BEHAVIORAL] branch_name present but no branches.conf mapping -> block, message contains 'no contract'"
        h = Harness("green")
        result = h.call("kanban_complete", "task-unmapped")
        assert_block(result)
        self.assertIn("no contract", result["message"])

    def test_no_branch_at_all_contract(self):
        "[BEHAVIORAL] task with NULL branch_name -> block, message contains 'no contract'"
        h = Harness("green")
        result = h.call("kanban_complete", "task-no-branch")
        assert_block(result)
        self.assertIn("no contract", result["message"])

    def test_crash_stub_fail_closed(self):
        "[BEHAVIORAL] recompute crashes (exit 99) -> block, NEVER None, non-empty message"
        h = Harness("crash")
        result = h.call("kanban_complete", "task-with-branch")
        self.assertIsNotNone(result)
        assert_block(result)

    def test_hang_stub_times_out(self):
        "[BEHAVIORAL] hang stub (sleep 120): callback returns within <=40s and blocks"

        def timeout_handler(signum, frame):
            raise TimeoutError("plugin callback did not return within 40s")

        h = Harness("hang")
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(40)
        start = time.monotonic()
        try:
            result = h.call("kanban_complete", "task-with-branch")
        finally:
            signal.alarm(0)
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 40.0, f"hang guard too slow: {elapsed:.1f}s")
        self.assertIsNotNone(result)
        assert_block(result)

    def test_non_kanban_tool_not_gated(self):
        "[BEHAVIORAL] a non-kanban_complete tool (bash) -> None; recompute stub never invoked"
        h = Harness("red")
        self.assertIsNone(h.call("bash", "task-with-branch"))
        self.assertNotIn("STUB|", h.stub_log())


def main():
    if not os.path.exists(PLUGIN_FILE):
        print(f"ERROR: plugin under test not found: {PLUGIN_FILE}")
        print("Expected: kanban_closure_gate.plugin.py is not yet written --")
        print("this harness FAILS until the Coder implements it.")
        return 1
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TestClosureGate)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())