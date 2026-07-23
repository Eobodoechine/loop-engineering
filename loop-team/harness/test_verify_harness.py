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


REPO_ROOT = os.path.normpath(os.path.join(HARNESS_DIR, "..", ".."))
EVALS_DIR = os.path.join(REPO_ROOT, "loop-team", "evals")
PASSING_PROJECT_FIXTURE = os.path.join(EVALS_DIR, "fixtures", "passing_project")


class AC6ConfcutdirRegression(unittest.TestCase):
    """[BEHAVIORAL] AC6 -- the real round-2 regression test.

    Spec: runs/2026-07-02_pytest-root-collection-fault/specs/spec.md, AC6.

    Now that a root-level pytest.ini exists (round-1 fix), ANY pytest
    invocation whose target path is nested under loop-team/evals/ resolves
    rootdir=~/Claude/loop and walks the path down through loop-team/evals/,
    loading loop-team/evals/conftest.py's `collect_ignore_glob =
    ["fixtures/*", "_shims/*"]` along the way -- a rule meant only to keep
    evals' OWN test collection from sweeping in its fixture inputs. That
    ignore rule now ALSO fires when verify.py invokes pytest directly and
    SOLELY against loop-team/evals/fixtures/passing_project, so the harness
    collects 0 tests and reports passed=False for a project that is not
    broken.

    This is the literal repro command from the spec:
        python3 loop-team/harness/verify.py loop-team/evals/fixtures/passing_project

    Currently RED: fails until verify.py's pytest invocation pins
    --confcutdir=<project> (~L210, `argv = [py_runner, "-q"]`).
    """

    def test_verify_py_passes_on_passing_project_fixture(self):
        self.assertTrue(
            os.path.isdir(PASSING_PROJECT_FIXTURE),
            "fixture missing: %s" % PASSING_PROJECT_FIXTURE,
        )
        res = _run_harness(PASSING_PROJECT_FIXTURE)
        self.assertTrue(
            res["passed"],
            "verify.py must report passed=True for "
            "loop-team/evals/fixtures/passing_project (it has one real "
            "passing test), got %r -- this is the ancestor-conftest leak "
            "from loop-team/evals/conftest.py's collect_ignore_glob "
            "reaching a directly-targeted fixture run; fix is "
            "--confcutdir=<project> in verify.py's pytest argv (~L210)" % res,
        )


class AC5ConfcutdirInvocationShapeCollectsRealTest(unittest.TestCase):
    """[BEHAVIORAL] AC5 -- verify.py's own invocation shape, WITH
    --confcutdir pinned, collects exactly 1 test (not 0) against
    loop-team/evals/fixtures/passing_project, confirming the ancestor
    loop-team/evals/conftest.py no longer leaks into a directly-targeted
    fixture run.

    This replicates verify.py's exact invocation shape (subprocess pytest,
    cwd=project, argv = [pytest, "-q", "--confcutdir=<project>"]) directly,
    rather than depending on verify.py already having the flag wired in --
    so it independently proves the flag itself is sufficient, decoupled
    from whether the Coder has patched verify.py yet.

    Currently RED as a *characterization* of the pre-fix world: this test
    asserts the FIXED behavior (1 collected), which only holds once
    --confcutdir is present in the invocation -- so it fails on a bare
    invocation without the flag and must be read alongside
    AC6ConfcutdirRegression, which exercises the real verify.py subprocess
    end-to-end.
    """

    def test_confcutdir_pinned_invocation_collects_one_test(self):
        project = PASSING_PROJECT_FIXTURE
        argv = [sys.executable, "-m", "pytest", "-q",
                "--confcutdir=%s" % project, "--collect-only"]
        p = subprocess.run(argv, cwd=project, capture_output=True, text=True)
        combined = p.stdout + p.stderr
        self.assertIn(
            "1 test collected", combined,
            "verify.py's invocation shape (with --confcutdir=<project> "
            "pinned) must collect exactly 1 test from passing_project's "
            "tests/test_ok.py, got:\n%s" % combined,
        )
        self.assertNotIn("no tests collected", combined)

    def test_verify_py_json_shows_evidence_of_real_one_test_run(self):
        """Cross-check via verify.py's own JSON output: once fixed, the
        summary/output fields must show a real 1-test pytest run (exit=0,
        no '0 tests collected' forced-fail banner), not the zero-collection
        signature."""
        res = _run_harness(PASSING_PROJECT_FIXTURE)
        self.assertNotEqual(
            res.get("summary"), "0 tests collected — forced fail",
            "verify.py still reports the zero-collection forced-fail "
            "summary for passing_project, got %r" % res,
        )
        self.assertNotIn("no tests ran", res.get("output", ""))
        self.assertEqual(
            res.get("runner"), "pytest",
            "expected the pytest branch to run and report a real result, "
            "got %r" % res,
        )


class AC8ProjectLocalConfigStillHonored(unittest.TestCase):
    """[BEHAVIORAL] AC8 -- verify.py must still honor a project-local
    pytest.ini/conftest.py after the --confcutdir fix.

    --confcutdir only stops pytest from walking ABOVE the pinned directory
    looking for ancestor conftests; it must NOT disable in-project config
    discovery WITHIN <project> itself. This builds a throwaway fixture
    (tempfile-based, per the spec's suggestion -- none of the checked-in
    fixtures under loop-team/evals/fixtures/* currently ship their own
    pytest.ini/conftest.py) with a project-local conftest.py that defines a
    detectable fixture function consumed by a project-local test, and
    confirms verify.py's real subprocess run actually uses it (the test
    would fail/error with a fixture-not-found error if the project-local
    conftest.py were NOT loaded).

    Currently RED for the same underlying reason as AC6: verify.py's
    subprocess pytest run against this project also lives under
    loop-team/evals/'s directory tree conceptually via the fixtures
    machinery is NOT the issue here -- this fixture is built fresh under
    tempfile, outside loop-team/evals/ entirely, so it should already
    isolate cleanly from the ancestor-conftest bug. It is included as a
    regression guard so that WHEN --confcutdir is added, it does not
    over-correct and cut off legitimate project-local config discovery
    too.
    """

    def _make_project_with_local_conftest(self):
        d = tempfile.mkdtemp()
        conftest_body = (
            "import pytest\n\n"
            "@pytest.fixture\n"
            "def magic_number():\n"
            "    return 42\n"
        )
        with open(os.path.join(d, "conftest.py"), "w") as f:
            f.write(conftest_body)
        tdir = os.path.join(d, "tests")
        os.makedirs(tdir)
        test_body = (
            "def test_uses_project_local_fixture(magic_number):\n"
            "    assert magic_number == 42\n"
        )
        with open(os.path.join(tdir, "test_local_conftest.py"), "w") as f:
            f.write(test_body)
        return d

    def test_project_local_conftest_fixture_is_honored(self):
        d = self._make_project_with_local_conftest()
        try:
            res = _run_harness(d)
            self.assertTrue(
                res["passed"],
                "verify.py must honor the project-local conftest.py's "
                "`magic_number` fixture (a test consuming it must pass, "
                "proving the project-local config was actually loaded), "
                "got %r" % res,
            )
            self.assertNotIn(
                "fixture 'magic_number' not found", res.get("output", ""),
                "project-local conftest.py was not honored -- pytest could "
                "not resolve the fixture it defines, got output:\n%s"
                % res.get("output", ""),
            )
        finally:
            import shutil as _shutil
            _shutil.rmtree(d, ignore_errors=True)

    def test_project_local_pytest_ini_marker_is_honored(self):
        """A project-local pytest.ini registering a custom marker must
        still be respected (no 'unknown marker' warning-as-error / the
        marker-using test must still collect and run cleanly)."""
        d = tempfile.mkdtemp()
        try:
            with open(os.path.join(d, "pytest.ini"), "w") as f:
                f.write("[pytest]\nmarkers =\n    slow: marks a slow test\n")
            tdir = os.path.join(d, "tests")
            os.makedirs(tdir)
            with open(os.path.join(tdir, "test_marker.py"), "w") as f:
                f.write(
                    "import pytest\n\n"
                    "@pytest.mark.slow\n"
                    "def test_marked_ok():\n"
                    "    assert True\n"
                )
            res = _run_harness(d)
            self.assertTrue(
                res["passed"],
                "verify.py must honor a project-local pytest.ini, got %r" % res,
            )
            self.assertNotIn("PytestUnknownMarkWarning", res.get("output", ""))
        finally:
            import shutil as _shutil
            _shutil.rmtree(d, ignore_errors=True)


class AC7FullSuiteCrossCheck(unittest.TestCase):
    """[BEHAVIORAL] AC7 cross-check -- the representative full-suite
    collection interaction.

    Spec AC7 names 5 real, pre-existing test functions in loop-team/evals/
    that must all pass when run TOGETHER in one pytest invocation (the
    shape that originally surfaced the round-2 regression: each spins up
    run_evals.run_suite() in-process against the real verify.py subprocess,
    and only running them together, alongside other files, is
    representative of a real full-suite run). Those 5 tests already exist
    and are correct -- this class does not rewrite them.

    Per the Test-writer brief for this spec: this is documentation/cross-
    check, not a new independent assertion of new behavior. The actual
    coverage is AC6ConfcutdirRegression (verify.py's own JSON verdict)
    plus this cross-check, which proves AC6's fix, when exercised in the
    SAME pytest process as loop-team/evals/test_run_evals.py and friends,
    does not reintroduce the collection issue -- i.e. AC6's new test is
    safe to run scoped alongside the existing eval suite in one invocation.
    """

    AC7_NAMED_TESTS = [
        "loop-team/evals/fault_injection/test_corpus_batch.py::TestSuiteSafety::test_default_run_suite_green_all_fi_pending",
        "loop-team/evals/test_run_evals.py::SuiteOnRealHarness::test_no_good_case_regression",
        "loop-team/evals/test_run_evals.py::SuiteOnRealHarness::test_suite_is_green",
        "loop-team/evals/test_run_evals.py::SuiteRobustness::test_malformed_case_isolated_as_error_not_crash",
        "loop-team/evals/test_verify_build.py::RedTeamAndGreen::test_eval_suite_is_green",
    ]

    def test_ac7_named_tests_pass_together_in_one_invocation(self):
        """Run the 5 AC7-named tests in ONE pytest invocation (not
        individually) -- this is the shape that caught the regression in
        the first place, since running them individually in isolation
        passed even on a broken tree (each gets its own cwd/rootdir when
        run alone)."""
        argv = [sys.executable, "-m", "pytest", "-q"] + self.AC7_NAMED_TESTS
        p = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True, text=True)
        combined = p.stdout + p.stderr
        self.assertEqual(
            p.returncode, 0,
            "the 5 AC7-named tests must all pass when run together in one "
            "pytest invocation from the repo root (the representative "
            "full-suite shape); got returncode=%s, output:\n%s"
            % (p.returncode, combined),
        )
        self.assertNotIn("'regression' != 'ok'", combined)

    def test_new_ac6_test_alongside_evals_suite_does_not_reintroduce_collection_issue(self):
        """The new AC6 regression test (this file's
        AC6ConfcutdirRegression) must keep passing when collected/run in
        the SAME invocation as loop-team/evals/test_run_evals.py -- i.e.
        adding this test file's coverage does not itself reintroduce a
        collection collision."""
        argv = [
            sys.executable, "-m", "pytest", "-q",
            os.path.join(HARNESS_DIR, "test_verify_harness.py") +
            "::AC6ConfcutdirRegression",
            os.path.join(EVALS_DIR, "test_run_evals.py"),
        ]
        p = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True, text=True)
        combined = p.stdout + p.stderr
        self.assertNotIn("ModuleNotFoundError", combined)
        self.assertEqual(
            p.returncode, 0,
            "AC6's new test, run alongside loop-team/evals/test_run_evals.py "
            "in one invocation, must not reintroduce the collection issue; "
            "got returncode=%s, output:\n%s" % (p.returncode, combined),
        )


if __name__ == "__main__":
    unittest.main()
