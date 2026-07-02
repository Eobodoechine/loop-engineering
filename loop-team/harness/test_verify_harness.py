"""Behavioral tests for the Loop Team harness (verify.py) — H-LOOPTEAM-1.

These EXECUTE the harness's real logic, not its description:
- unit-test the zero-tests detector against the actual runner output strings
  (unittest "Ran 0 tests" + exit 0; pytest "no tests ran"; pytest exit 5);
- integration-test verify.py end-to-end on fixture projects (0-test / passing / failing).

Authored by Oga as a meta-test of the harness itself. Run with:
    python3 -m pytest loop-team/harness/test_verify_harness.py -q
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFY = os.path.join(HARNESS_DIR, "verify.py")
sys.path.insert(0, HARNESS_DIR)
import verify  # noqa: E402  (imports cleanly; main() is guarded by __main__)


def _run_harness(project_dir):
    p = subprocess.run([sys.executable, VERIFY, project_dir],
                       capture_output=True, text=True)
    return json.loads(p.stdout)


class ZeroTestDetector(unittest.TestCase):
    """The harness MUST treat a 0-collected run as a failure, even on exit 0.

    Requires verify.py to expose a helper `_zero_tests(output, code) -> bool`.
    """

    def setUp(self):
        if not hasattr(verify, "_zero_tests"):
            self.fail("verify.py must expose a _zero_tests(output, code) helper "
                      "that flags a 0-collected run (H-LOOPTEAM-1)")

    def test_unittest_zero_tests_is_flagged(self):
        out = "\n----------------------------------------------------------------------\nRan 0 tests in 0.000s\n\nOK\n"
        self.assertTrue(verify._zero_tests(out, 0))

    def test_pytest_no_tests_ran_is_flagged(self):
        self.assertTrue(verify._zero_tests("no tests ran in 0.01s", 5))
        self.assertTrue(verify._zero_tests("no tests ran in 0.01s", 0))

    def test_real_tests_are_not_flagged(self):
        self.assertFalse(verify._zero_tests("Ran 7 tests in 0.10s\n\nOK", 0))
        self.assertFalse(verify._zero_tests("7 passed in 0.10s", 0))


class HarnessIntegration(unittest.TestCase):
    """End-to-end: invoke verify.py on real fixture projects."""

    def _make(self, body):
        d = tempfile.mkdtemp()
        tdir = os.path.join(d, "tests")
        os.makedirs(tdir)
        open(os.path.join(tdir, "__init__.py"), "w").close()
        with open(os.path.join(tdir, "test_fixture.py"), "w") as f:
            f.write(body)
        return d

    def test_zero_tests_project_fails(self):
        # tests/ exists but contains no test methods -> must NOT pass
        d = tempfile.mkdtemp()
        tdir = os.path.join(d, "tests")
        os.makedirs(tdir)
        with open(os.path.join(tdir, "not_a_test.py"), "w") as f:
            f.write("x = 1\n")
        res = _run_harness(d)
        self.assertFalse(res["passed"],
                         "0-test project must report passed=False, got %r" % res)

    def test_passing_project_passes(self):
        d = self._make("import unittest\n"
                       "class T(unittest.TestCase):\n"
                       "    def test_ok(self):\n        self.assertEqual(1, 1)\n")
        res = _run_harness(d)
        self.assertTrue(res["passed"], "passing project must report passed=True, got %r" % res)
        assert "duration_s" in res
        assert isinstance(res["duration_s"], float)
        assert "attempts" in res
        assert isinstance(res["attempts"], list)

    def test_failing_project_fails(self):
        d = self._make("import unittest\n"
                       "class T(unittest.TestCase):\n"
                       "    def test_bad(self):\n        self.assertEqual(1, 2)\n")
        res = _run_harness(d)
        self.assertFalse(res["passed"], "failing project must report passed=False, got %r" % res)


class RunnerPackageResolution(unittest.TestCase):
    """BEHAVIORAL: detect_and_run() on the runner/ package must return passed=True.
    Currently FAILS (no PYTHONPATH injection) — will pass after the Coder's fix."""

    def test_runner_package_resolves_and_passes(self):
        """[BEHAVIORAL] detect_and_run(runner_dir) must succeed without ModuleNotFoundError."""
        runner_dir = os.path.normpath(os.path.join(HARNESS_DIR, "..", "runner"))
        result = verify.detect_and_run(runner_dir)
        self.assertNotIn(
            "ModuleNotFoundError",
            result.get("output", ""),
            "PYTHONPATH injection is missing — subprocess cannot resolve 'import runner'. "
            "Fix: inject parent dir into PYTHONPATH before calling subprocess.run()."
        )
        self.assertTrue(
            result["passed"],
            "detect_and_run(runner_dir) returned passed=False. "
            "Full output:\n%s" % result.get("output", "")
        )


if __name__ == "__main__":
    unittest.main()
