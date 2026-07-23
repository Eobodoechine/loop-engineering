"""Behavioral tests for verify.py's structural smoke gate — AC-RH4 of
residual_holes_spec.md (runs/2026-07-02_003000-stopguard-residual-holes).

If <project_dir>/smoke_manifest.json exists (schema {"artifacts": [relpath,
...]}), verify.py must sweep each artifact's URLs via live_smoke, AND the
smoke pass into the JSON `passed`, and expose an additive
`"smoke": {"ran": bool, "passed": bool, "dead": [...]}` field.

All five cases here are OFFLINE-ONLY: none may ever reach a real network
sweep. Written spec-first — they are RED against the unmodified verify.py by
design (it has no "smoke" key yet).

Deliberately a SEPARATE file from test_verify_harness.py: that file is
re-executed as a subprocess by test_verify_node.py's VAC5 meta-test
(test_existing_harness_tests_still_pass), which asserts it is fully green —
red-by-design cases must not sit inside it during the red phase.

Run with:
    python3 -m pytest loop-team/harness/test_verify_smoke_gate.py -q
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFY = os.path.join(HARNESS_DIR, "verify.py")

# A poisoned playwright package: importing it writes a sentinel file (so even
# a try/except-swallowed import is detected) and then raises. Placed FIRST on
# PYTHONPATH it shadows the real site-packages playwright for verify.py's
# process AND any subprocess it spawns (they inherit the env).
_POISON_PLAYWRIGHT = (
    "import os\n"
    "_s = os.environ.get('VERIFY_POISON_SENTINEL')\n"
    "if _s:\n"
    "    with open(_s, 'w') as _f:\n"
    "        _f.write('playwright imported')\n"
    "raise ImportError('poisoned playwright: verify.py must not import "
    "playwright for a zero-URL smoke manifest (AC-RH4)')\n"
)


def _make_passing_project():
    """A minimal fixture project whose test suite passes, so any passed=False
    below is attributable to the smoke gate alone."""
    d = tempfile.mkdtemp()
    tdir = os.path.join(d, "tests")
    os.makedirs(tdir)
    with open(os.path.join(tdir, "test_fixture.py"), "w") as f:
        f.write("def test_ok():\n    assert 1 == 1\n")
    return d


def _write_manifest(project_dir, text):
    with open(os.path.join(project_dir, "smoke_manifest.json"), "w") as f:
        f.write(text)


def _run_harness_proc(project_dir, env_extras=None):
    """Run verify.py as a subprocess and return the CompletedProcess (not the
    parsed JSON) so contract tests can assert stdout parses at all."""
    env = os.environ.copy()
    if env_extras:
        env.update(env_extras)
    return subprocess.run([sys.executable, VERIFY, project_dir],
                          capture_output=True, text=True, env=env)


def _run_harness(project_dir, env_extras=None):
    return json.loads(_run_harness_proc(project_dir, env_extras).stdout)


class SmokeGateRH4(unittest.TestCase):
    """[BEHAVIORAL] AC-RH4: manifest-declared smoke gate, offline cases only."""

    def test_no_manifest_contract_unchanged_smoke_not_ran(self):
        """No smoke_manifest.json -> no behavior change: passed stays True on
        a passing project, existing contract keys intact, and the additive
        smoke field reports ran=False."""
        d = _make_passing_project()
        res = _run_harness(d)
        self.assertTrue(res["passed"], res)
        for key in ("passed", "runner", "summary", "output"):
            self.assertIn(key, res)
        self.assertIn("smoke", res,
                      "AC-RH4 requires an additive smoke field even without a manifest")
        self.assertFalse(res["smoke"]["ran"],
                         "no manifest -> smoke must not run: %r" % (res.get("smoke"),))

    def test_empty_artifacts_list_smoke_ran_and_passed(self):
        """Manifest with an empty artifacts list -> the gate runs, trivially
        passes, and does not affect the overall verdict."""
        d = _make_passing_project()
        _write_manifest(d, json.dumps({"artifacts": []}))
        res = _run_harness(d)
        self.assertTrue(res["passed"], res)
        self.assertIn("smoke", res)
        self.assertTrue(res["smoke"]["ran"], res["smoke"])
        self.assertTrue(res["smoke"]["passed"], res["smoke"])
        self.assertEqual(res["smoke"]["dead"], [])

    def test_artifact_with_no_urls_short_circuits_without_playwright_import(self):
        """A manifest-listed artifact containing zero http(s) URLs must
        short-circuit to smoke ran+passed WITHOUT importing playwright
        (offline/CI-safe). Proven by shadowing playwright with a poisoned
        package whose import writes a sentinel file and raises: if verify.py
        (or anything it spawns) imports playwright, the sentinel appears."""
        d = _make_passing_project()
        with open(os.path.join(d, "notes.md"), "w") as f:
            f.write("Offline design notes. No links live in this artifact.\n")
        _write_manifest(d, json.dumps({"artifacts": ["notes.md"]}))

        poison_root = tempfile.mkdtemp(prefix="rh4-poison-")
        pkg = os.path.join(poison_root, "playwright")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "__init__.py"), "w") as f:
            f.write(_POISON_PLAYWRIGHT)
        sentinel = os.path.join(tempfile.mkdtemp(prefix="rh4-sentinel-"),
                                "playwright_imported.flag")
        existing = os.environ.get("PYTHONPATH", "")
        pythonpath = (poison_root + os.pathsep + existing) if existing else poison_root

        p = _run_harness_proc(d, env_extras={
            "PYTHONPATH": pythonpath,
            "VERIFY_POISON_SENTINEL": sentinel,
        })
        res = json.loads(p.stdout)
        self.assertTrue(res["passed"], res)
        self.assertIn("smoke", res)
        self.assertTrue(res["smoke"]["ran"], res["smoke"])
        self.assertTrue(res["smoke"]["passed"], res["smoke"])
        self.assertFalse(
            os.path.exists(sentinel),
            "playwright was imported for a zero-URL artifact — the smoke gate "
            "must short-circuit before any sweep that imports playwright")

    def test_malformed_manifest_forced_fail_json(self):
        """A malformed smoke_manifest.json -> LOUD forced-fail: passed False,
        exit code 1, stdout still a single parseable JSON object (the
        always-prints-JSON contract — never an uncaught exception)."""
        d = _make_passing_project()
        _write_manifest(d, "{this is not json!!")
        p = _run_harness_proc(d)
        try:
            res = json.loads(p.stdout)
        except ValueError:
            self.fail("verify.py broke its always-prints-JSON contract on a "
                      "malformed manifest. stdout=%r stderr=%r"
                      % (p.stdout[-500:], p.stderr[-500:]))
        self.assertFalse(res["passed"],
                         "malformed manifest must force-fail, got %r" % res)
        self.assertEqual(p.returncode, 1, (p.returncode, p.stderr[-300:]))
        blob = ((res.get("summary") or "") + (res.get("output") or "")).lower()
        self.assertIn("manifest", blob,
                      "forced-fail must be explanatory (name the manifest): %r" % res)

    def test_missing_artifact_file_forced_fail_json(self):
        """A manifest listing an artifact file that does not exist -> LOUD
        forced-fail with the offending relpath named, JSON contract intact."""
        d = _make_passing_project()
        _write_manifest(d, json.dumps({"artifacts": ["ghost_artifact.md"]}))
        p = _run_harness_proc(d)
        try:
            res = json.loads(p.stdout)
        except ValueError:
            self.fail("verify.py broke its always-prints-JSON contract on a "
                      "missing artifact. stdout=%r stderr=%r"
                      % (p.stdout[-500:], p.stderr[-500:]))
        self.assertFalse(res["passed"],
                         "missing artifact must force-fail, got %r" % res)
        self.assertEqual(p.returncode, 1, (p.returncode, p.stderr[-300:]))
        blob = (res.get("summary") or "") + (res.get("output") or "")
        self.assertIn("ghost_artifact.md", blob,
                      "forced-fail must name the missing artifact: %r" % res)


if __name__ == "__main__":
    unittest.main()
