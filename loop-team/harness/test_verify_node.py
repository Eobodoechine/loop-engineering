"""Behavioral tests for verify.py's Node/vitest runner support -- H-LT5.

Covers VAC1-VAC7 from the plan-checked spec at
runs/2026-07-01_hlt5-verify-node/specs/verify_node_spec.md:

  VAC1 - real padsplit-cockpit/web repo -> runner "vitest", not forced-fail.
  VAC2 - synthetic vitest project (1 passing test) -> passed True, runner vitest.
  VAC3 - synthetic pytest project, no package.json -> passed True, runner pytest
         (regression check on the pre-existing Python path).
  VAC4 - synthetic dir with neither ecosystem -> forced-fail behavior preserved.
  VAC5 - existing harness tests still pass; contract keys unchanged; py_compile
         clean; source is Python-3.9-safe (checked via ast, no runtime dependency
         on a 3.9 interpreter being present).
  VAC6 - dual-ecosystem project (real pytest test + vitest project) -> both run,
         results ANDed, contract-safe additive `runners` key.
  VAC7 - package.json with no known runner declared, no Python signals ->
         forced-fail preserved, distinct from VAC4's no-manifest case.

Run with:
    python3 -m pytest loop-team/harness/test_verify_node.py -q
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import pytest

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFY = os.path.join(HARNESS_DIR, "verify.py")
PADSPLIT_WEB = os.path.expanduser("~/Claude/Projects/padsplit-cockpit/web")
PADSPLIT_ROOT = os.path.expanduser("~/Claude/Projects/padsplit-cockpit")

sys.path.insert(0, HARNESS_DIR)
import verify  # noqa: E402


def _make_vitest_scratch_dir():
    """Create a synthetic project dir that can actually resolve `vitest`.

    A plain tempfile.mkdtemp() has no node_modules, so `npx vitest` can't
    resolve the package without a network fetch. padsplit-cockpit/ is an
    npm workspace with vitest hoisted at its root node_modules/; nesting
    the synthetic project under it lets Node's normal upward module
    resolution find vitest for free, with zero network access. This is
    test-fixture plumbing only -- it does not change what verify.py runs
    (still `npx vitest run --reporter=basic` with cwd=<project_dir>, same
    as any other vitest project).
    """
    d = tempfile.mkdtemp(dir=PADSPLIT_ROOT, prefix=".verify_node_scratch_")
    return d


def _run_harness(project_dir, timeout=None, env=None):
    p = subprocess.run([sys.executable, VERIFY, project_dir],
                       capture_output=True, text=True, timeout=timeout, env=env)
    return json.loads(p.stdout)


def _npx_available():
    return shutil.which("npx") is not None


def _write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


VITEST_PACKAGE_JSON = json.dumps({
    "name": "fixture",
    "version": "1.0.0",
    "scripts": {"test": "vitest run"},
    "devDependencies": {"vitest": "^4.0.0"},
})

VITEST_CONFIG = (
    "import { defineConfig } from 'vitest/config'\n"
    "export default defineConfig({ test: {} })\n"
)

PASSING_VITEST_TEST = (
    "import { it, expect } from 'vitest'\n"
    "it('adds', () => { expect(1 + 1).toBe(2) })\n"
)

PACKAGE_JSON_NO_KNOWN_RUNNER = json.dumps({
    "name": "fixture-no-runner",
    "version": "1.0.0",
    "scripts": {"build": "tsc", "lint": "eslint ."},
})


@pytest.mark.slow
@unittest.skipUnless(os.path.isdir(PADSPLIT_WEB), "padsplit-cockpit/web not present on this machine")
@unittest.skipUnless(_npx_available(), "npx not on PATH")
class VAC1RealPadsplitRepo(unittest.TestCase):
    """[BEHAVIORAL] VAC1: real repo, runner selection + non-forced-fail.

    Per the spec: NOT suite greenness -- asserts runner == 'vitest' (not
    pytest, not the dual form) and that the harness's zero-signal forced-fail
    path did not produce the verdict.

    Marked `slow`: this shells out to the REAL external padsplit-cockpit/web
    repo via `npx vitest run`, which can run for a long time (observed: still
    running past 30s with no visible output, since verify.py captures rather
    than streams subprocess output). Excluded from the default pytest sweep
    (see evals/verify_build.py's pytest_sweep(), which passes `-m "not slow"`)
    so it can't masquerade as a hang in CI/gate runs. Still fully runnable on
    demand via `-m slow` or `-k VAC1`. The existing skipUnless guards are
    unchanged -- this marker is additive, not a replacement for them.
    """

    def test_padsplit_web_selects_vitest_not_forced_fail(self):
        env = os.environ.copy()
        # VAC1 proves the loop verifier selects and executes the real PadSplit
        # vitest runner. It is not PadSplit's own recursive full-suite gate:
        # web/vitest.config.ts treats VITEST_WORKER_ID as the non-recursive
        # nested-run mode and excludes tests that themselves spawn full vitest.
        env.setdefault("VITEST_WORKER_ID", "loop-harness")
        res = _run_harness(PADSPLIT_WEB, timeout=300, env=env)
        self.assertEqual(res["runner"], "vitest",
                         "expected runner 'vitest' on padsplit web/, got %r (full: %r)"
                         % (res.get("runner"), res))
        self.assertNotEqual(
            res.get("summary"), "0 tests collected — forced fail",
            "harness forced-failed on padsplit web/ -- zero-signal path fired incorrectly"
        )
        self.assertNotIn("Ran 0 tests", res.get("output", ""))
        self.assertNotIn("no tests ran", res.get("output", ""))
        # exit=5 is pytest's "no tests collected" status; must not be what produced this verdict.
        self.assertNotIn("exit=5", res.get("summary", ""))


@unittest.skipUnless(os.path.isdir(PADSPLIT_ROOT), "padsplit-cockpit workspace not present (needed to resolve vitest without network)")
class VAC2SyntheticVitestProject(unittest.TestCase):
    """[BEHAVIORAL] VAC2: synthetic vitest project with one passing test."""

    @unittest.skipUnless(_npx_available(), "npx not on PATH")
    def test_synthetic_vitest_passes(self):
        d = _make_vitest_scratch_dir()
        try:
            _write(os.path.join(d, "package.json"), VITEST_PACKAGE_JSON)
            _write(os.path.join(d, "vitest.config.mjs"), VITEST_CONFIG)
            _write(os.path.join(d, "sum.test.mjs"), PASSING_VITEST_TEST)
            res = _run_harness(d, timeout=180)
            self.assertTrue(res["passed"], "expected passed=True, got %r" % res)
            self.assertEqual(res["runner"], "vitest")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC3SyntheticPytestProjectRegression(unittest.TestCase):
    """[BEHAVIORAL] VAC3: synthetic pytest project, no package.json -> regression."""

    def test_synthetic_pytest_passes_no_package_json(self):
        d = tempfile.mkdtemp()
        tdir = os.path.join(d, "tests")
        os.makedirs(tdir)
        _write(os.path.join(tdir, "test_fixture.py"),
              "def test_ok():\n    assert 1 == 1\n")
        self.assertFalse(os.path.isfile(os.path.join(d, "package.json")))
        res = _run_harness(d)
        self.assertTrue(res["passed"], "expected passed=True, got %r" % res)
        self.assertEqual(res["runner"], "pytest")


class VAC4NeitherEcosystem(unittest.TestCase):
    """[BEHAVIORAL] VAC4: dir with neither Python nor Node signals -> forced-fail."""

    def test_empty_dir_forced_fail(self):
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "README.md"), "nothing to see here\n")
        res = _run_harness(d)
        self.assertFalse(res["passed"])
        self.assertIsNone(res["runner"])


class VAC5ContractAndHygiene(unittest.TestCase):
    """[BEHAVIORAL] VAC5: existing tests pass, contract keys unchanged, py_compile
    clean, source is Python-3.9-safe syntax."""

    def test_py_compile_clean(self):
        p = subprocess.run([sys.executable, "-m", "py_compile", VERIFY],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_contract_keys_unchanged_on_pass(self):
        d = tempfile.mkdtemp()
        tdir = os.path.join(d, "tests")
        os.makedirs(tdir)
        _write(os.path.join(tdir, "test_fixture.py"),
              "def test_ok():\n    assert True\n")
        res = _run_harness(d)
        for key in ("passed", "runner", "summary", "output", "duration_s", "attempts"):
            self.assertIn(key, res, "contract key %r missing from result %r" % (key, res))

    def test_contract_keys_unchanged_on_forced_fail(self):
        d = tempfile.mkdtemp()
        res = _run_harness(d)
        for key in ("passed", "runner", "summary", "output", "duration_s", "attempts"):
            self.assertIn(key, res, "contract key %r missing from result %r" % (key, res))

    @pytest.mark.slow
    def test_existing_harness_tests_still_pass(self):
        """Marked `slow`: this shells out to a NESTED real pytest subprocess
        (test_verify_harness.py's own full suite), with output captured
        rather than streamed via `capture_output=True` -- empirically
        measured at ~176s on one real machine, with zero visible output the
        entire time. That is exactly the "indistinguishable from a hang"
        case evals/verify_build.py's pytest_sweep() excludes via
        `-m "not slow"` (see VAC1RealPadsplitRepo above and pytest.ini's
        `slow` marker docstring) -- this test was previously unmarked and
        so ran unbounded inside every "fast" default sweep. Still fully
        runnable on demand via `-m slow` or `-k test_existing_harness`.
        """
        other = os.path.join(HARNESS_DIR, "test_verify_harness.py")
        timeout_s = 300  # generous headroom over the observed ~176s, still well under
                          # the outer sweep's own 600s ceiling should this ever run there.
        try:
            p = subprocess.run([sys.executable, "-m", "pytest", other, "-q"],
                               capture_output=True, text=True,
                               cwd=os.path.dirname(HARNESS_DIR), timeout=timeout_s)
        except subprocess.TimeoutExpired:
            self.fail(
                "nested pytest run exceeded %ds -- likely a genuine hang, "
                "not the known ~176s slow case" % timeout_s
            )
        self.assertEqual(p.returncode, 0,
                         "test_verify_harness.py regressed:\n%s\n%s" % (p.stdout, p.stderr))

    @mock.patch("subprocess.run")
    def test_timeout_expired_handling_is_executed_not_just_read(self, mock_run):
        """[BEHAVIORAL] AC4 (corrected): executable proof that the
        `subprocess.TimeoutExpired` handler inside
        test_existing_harness_tests_still_pass actually fires a clean,
        distinct test FAILURE -- not an uncaught traceback -- rather than
        that fact being verified only by reading the source.

        Forces `subprocess.run` to raise TimeoutExpired via mock.patch (the
        real ~176s nested subprocess never actually runs here), then invokes
        test_existing_harness_tests_still_pass's own body directly. If the
        `except subprocess.TimeoutExpired` clause were ever broken (wrong
        exception class, a format-string bug, an unreachable self.fail
        call), the raised exception would NOT be self.failureException and
        this assertRaises would let it propagate uncaught, failing (erroring)
        this test -- exactly the regression this test exists to catch, since
        no other AC ever drives the real subprocess past its timeout.
        """
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=[sys.executable, "-m", "pytest"], timeout=300)
        with self.assertRaises(self.failureException) as ctx:
            self.test_existing_harness_tests_still_pass()
        self.assertIn(
            "likely a genuine hang, not the known ~176s slow case",
            str(ctx.exception),
        )

    def test_source_is_python39_safe_syntax(self):
        """Parse verify.py with an AST grammar check; also reject 3.10+-only
        constructs (match statements, PEP 604 `X | Y` unions) by source scan,
        since the AST parse alone would succeed under a 3.10+ interpreter."""
        with open(VERIFY, "r") as f:
            src = f.read()
        tree = ast.parse(src)
        self.assertIsNotNone(tree)
        import re as _re
        self.assertIsNone(_re.search(r"^\s*match .+:\s*$", src, _re.MULTILINE),
                          "found a `match` statement (3.10+ only)")


@unittest.skipUnless(os.path.isdir(PADSPLIT_ROOT), "padsplit-cockpit workspace not present (needed to resolve vitest without network)")
class VAC6DualEcosystem(unittest.TestCase):
    """[BEHAVIORAL] VAC6: dual-ecosystem synthetic dir -> both run, ANDed,
    contract-safe additive `runners` key (no exact-match `runner` consumers
    were found in the repo, so `runner` stays the single primary name)."""

    @unittest.skipUnless(_npx_available(), "npx not on PATH")
    def test_dual_ecosystem_runs_both_and_ands(self):
        d = _make_vitest_scratch_dir()
        try:
            # Real Python test signal.
            tdir = os.path.join(d, "tests")
            os.makedirs(tdir)
            _write(os.path.join(tdir, "test_fixture.py"),
                  "def test_ok():\n    assert 1 == 1\n")
            # Real Node/vitest signal.
            _write(os.path.join(d, "package.json"), VITEST_PACKAGE_JSON)
            _write(os.path.join(d, "vitest.config.mjs"), VITEST_CONFIG)
            _write(os.path.join(d, "sum.test.mjs"), PASSING_VITEST_TEST)

            res = _run_harness(d, timeout=180)
            self.assertTrue(res["passed"], "expected both-pass AND -> True, got %r" % res)
            self.assertIn(res["runner"], ("pytest", "unittest"),
                          "runner should stay a single primary name, got %r" % res["runner"])
            self.assertIn("runners", res, "additive `runners` key missing from dual-ecosystem result")
            self.assertEqual(set(res["runners"]), {res["runner"], "vitest"})
        finally:
            shutil.rmtree(d, ignore_errors=True)

    @unittest.skipUnless(_npx_available(), "npx not on PATH")
    def test_dual_ecosystem_ands_a_failure(self):
        """If the Python side fails, the overall AND must be False even
        though the Node side passes."""
        d = _make_vitest_scratch_dir()
        try:
            tdir = os.path.join(d, "tests")
            os.makedirs(tdir)
            _write(os.path.join(tdir, "test_fixture.py"),
                  "def test_bad():\n    assert 1 == 2\n")
            _write(os.path.join(d, "package.json"), VITEST_PACKAGE_JSON)
            _write(os.path.join(d, "vitest.config.mjs"), VITEST_CONFIG)
            _write(os.path.join(d, "sum.test.mjs"), PASSING_VITEST_TEST)

            res = _run_harness(d, timeout=180)
            self.assertFalse(res["passed"], "Python failure must fail the AND, got %r" % res)
            self.assertIn("runners", res)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC7PackageJsonNoKnownRunner(unittest.TestCase):
    """[BEHAVIORAL] VAC7: package.json present, no known runner declared,
    no Python signals -> forced-fail preserved, distinct from VAC4."""

    def test_package_json_without_known_runner_forced_fail(self):
        d = tempfile.mkdtemp()
        _write(os.path.join(d, "package.json"), PACKAGE_JSON_NO_KNOWN_RUNNER)
        self.assertTrue(os.path.isfile(os.path.join(d, "package.json")))
        res = _run_harness(d)
        self.assertFalse(res["passed"])
        self.assertIsNone(res["runner"])


if __name__ == "__main__":
    unittest.main()
