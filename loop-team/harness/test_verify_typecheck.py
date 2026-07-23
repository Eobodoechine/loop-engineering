"""Behavioral tests for verify.py's baseline-scoped type-check gate --
H-TYPECHECK-GATE-1.

Covers the 4 new functions + their composition, named in
research/compiler-feedback-loop-gate-design-2026-07-08.md section 2b:

  _resolve_tsc_binary(project)      -- VAC1-VAC3
  has_typescript_project(project)   -- VAC4-VAC7
  _parse_tsc_errors(combined_output) -- VAC8-VAC13
  _load_type_check_baseline(project) -- VAC14-VAC16
  _type_check_gate(project)         -- VAC17-VAC21 (composed)

These functions do NOT exist in verify.py yet (this is TDD: tests written
before implementation). Every test below is expected to fail with an
AttributeError until the Coder lands the 4-5 functions -- that is correct
and expected, not a bug in this file.

The design doc left TWO open questions as explicit TODOs; this file
RESOLVES both and each choice is restated in the relevant VAC's docstring
(these choices become the contract the Coder implements against):

  1. _parse_tsc_errors fingerprint shape: (relative_file_path,
     ts_error_code) ONLY -- explicitly excludes line/column and message
     text, so line-number churn in unrelated code never manufactures a
     false "new" error. See VAC13 (the sharpest test of this) and VAC8-12
     for the surrounding parse cases.

  2. _load_type_check_baseline is SELF-BOOTSTRAPPING: no baseline file ->
     compute current tsc errors (via the same invocation
     _type_check_gate uses), write them to
     <project>/.loop_type_check_baseline.json, return them as the
     baseline (so the first checkpoint of a slice always passes with zero
     new errors, with no separate "capture baseline" step). Existing file
     -> load verbatim, never re-derive. Corrupted file -> fail loud with a
     distinct exception, never silently return an empty/wrong baseline and
     never let a low-level JSONDecodeError-class crash escape uncaught
     from the COMPOSED _type_check_gate (which must still return its
     normal (dict, error) forced-fail contract). See VAC14-16 and VAC19.

VAC20 is the critical baseline-scoping regression test named in the
dispatch: a synthetic project with 2 pre-existing tsc errors (matching the
baseline on the first run) plus, after one NEW error is introduced, a
second run that must report EXACTLY 1 new error (not 3) -- the 2
pre-existing ones must never resurface as "new".

Real-fixture format/exit-code assumptions below (tsc's `file(line,col):
error TSXXXX: message` line format, exit 0 on a clean run with empty
output, exit 2 with N error lines for N real errors) were verified LIVE
against the real, hoisted typescript@5.9.3 binary at
padsplit-cockpit/node_modules/.bin/tsc in this session before this file
was written, not assumed.

Run with:
    python3 -m pytest loop-team/harness/test_verify_typecheck.py -q
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import pytest

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
VERIFY = os.path.join(HARNESS_DIR, "verify.py")
PADSPLIT_ROOT = os.path.expanduser("~/Claude/Projects/padsplit-cockpit")
_PADSPLIT_HOISTED_TSC = os.path.join(PADSPLIT_ROOT, "node_modules", ".bin", "tsc")

sys.path.insert(0, HARNESS_DIR)
import verify  # noqa: E402


def _node_available():
    return shutil.which("node") is not None


def _padsplit_hoisted_tsc_available():
    """True only when the REAL padsplit-cockpit monorepo has an actually
    installed, hoisted tsc binary -- stronger than just checking the repo
    directory exists, since VAC2/VAC14/VAC19/VAC21 depend on this exact
    binary being resolvable and runnable (confirmed live, this session:
    `padsplit-cockpit/node_modules/.bin/tsc --version` -> "Version 5.9.3";
    `padsplit-cockpit/web/node_modules/.bin/tsc` does NOT exist)."""
    return os.path.isfile(_PADSPLIT_HOISTED_TSC)


def _make_tsc_scratch_dir():
    """Create a synthetic project dir that can resolve a REAL tsc binary
    via parent-workspace hoisting, with zero network access.

    Mirrors test_verify_node.py's _make_vitest_scratch_dir() helper exactly
    (same rationale, same technique -- nesting a scratch project directly
    under the real padsplit-cockpit monorepo root so Node's normal upward
    node_modules resolution finds the already-installed, hoisted
    typescript@5.9.3 binary for free) applied to tsc instead of vitest.
    This is test-fixture plumbing only; it does not change what
    _resolve_tsc_binary/_type_check_gate actually do.
    """
    d = tempfile.mkdtemp(dir=PADSPLIT_ROOT, prefix=".verify_typecheck_scratch_")
    return d


def _write(path, content=""):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


TSCONFIG_JSON = json.dumps({
    "compilerOptions": {
        "target": "es2020",
        "module": "commonjs",
        "strict": True,
        "noEmit": True,
        "skipLibCheck": True,
    },
    "include": ["**/*.ts"],
})

PACKAGE_JSON_WITH_TS_DEV = json.dumps({
    "name": "typecheck-fixture",
    "version": "1.0.0",
    "devDependencies": {"typescript": "^5"},
})

PACKAGE_JSON_WITH_TS_DEP = json.dumps({
    "name": "typecheck-fixture-dep",
    "version": "1.0.0",
    "dependencies": {"typescript": "^5"},
})

PACKAGE_JSON_NO_TS = json.dumps({
    "name": "typecheck-fixture-no-ts",
    "version": "1.0.0",
    "devDependencies": {"lodash": "^4"},
})

# Verified live (this session) against padsplit-cockpit's real hoisted
# typescript@5.9.3: each of these single-statement files produces EXACTLY
# one TS2322 error, at (1,7), and nothing else.
ONE_TS_ERROR_FILE = 'const x: number = "not a number";\n'      # a.ts -> TS2322
ANOTHER_TS_ERROR_FILE = 'const y: string = 42;\n'               # b.ts -> TS2322
THIRD_TS_ERROR_FILE = 'const z: boolean = "nope";\n'            # c.ts -> TS2322
CLEAN_TS_FILE = 'export const ok: number = 1;\n'                # zero errors


# =====================================================================
# _resolve_tsc_binary(project) -- VAC1-VAC3
# =====================================================================

class VAC1ResolveTscBinaryProjectLocal(unittest.TestCase):
    """[BEHAVIORAL] VAC1: a project-local node_modules/.bin/tsc is resolved
    FIRST -- the cheapest, most-specific candidate, taking priority over
    any parent/workspace-hoisted binary that might also exist."""

    def test_project_local_bin_tsc_is_resolved(self):
        d = tempfile.mkdtemp()
        try:
            bin_dir = os.path.join(d, "node_modules", ".bin")
            os.makedirs(bin_dir)
            tsc_path = os.path.join(bin_dir, "tsc")
            _write(tsc_path, "#!/bin/sh\necho fake-tsc\n")
            result = verify._resolve_tsc_binary(d)
            self.assertEqual(result, [tsc_path])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC2ResolveTscBinaryParentWorkspaceHoisted(unittest.TestCase):
    """[BEHAVIORAL] VAC2: with NO project-local install, resolution walks
    UP parent directories and finds a workspace-hoisted
    node_modules/.bin/tsc. Uses the REAL padsplit-cockpit monorepo --
    confirmed live this session: padsplit-cockpit/node_modules/.bin/tsc is
    a real, working typescript@5.9.3 binary, and a scratch dir nested
    directly under padsplit-cockpit/ has no node_modules of its own,
    exactly reproducing the real-world case the design doc found
    (padsplit-cockpit/web itself has no local tsc install; the hoisted
    root binary is what actually resolves today)."""

    @unittest.skipUnless(_padsplit_hoisted_tsc_available(),
                         "padsplit-cockpit hoisted tsc binary not present on this machine")
    def test_parent_hoisted_bin_tsc_is_resolved(self):
        d = _make_tsc_scratch_dir()
        try:
            self.assertFalse(
                os.path.isfile(os.path.join(d, "node_modules", ".bin", "tsc")),
                "fixture invariant broken: scratch dir must have no local tsc install"
            )
            result = verify._resolve_tsc_binary(d)
            self.assertEqual(result, [_PADSPLIT_HOISTED_TSC])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC3ResolveTscBinaryNoResolutionFallsBackToNpx(unittest.TestCase):
    """[BEHAVIORAL] VAC3: with no local AND no resolvable parent tsc
    binary, resolution falls back to the pinned `npx --no-install
    --package typescript tsc` invocation -- never bare `npx tsc`, which
    collides with an unrelated, abandoned npm package literally named
    `tsc` (confirmed live by the design doc, 2026-07-08: bare `npx
    --no-install tsc` on an uninstalled toolchain resolves tsc@2.0.4 and
    exits 1, not 127)."""

    def test_fully_isolated_dir_falls_back_to_pinned_npx(self):
        # tempfile.mkdtemp() with no `dir=` lands under the OS temp root
        # (NOT nested under padsplit-cockpit or any other
        # node_modules-bearing tree), so the bounded parent walk finds
        # nothing to resolve to.
        d = tempfile.mkdtemp()
        try:
            result = verify._resolve_tsc_binary(d)
            self.assertEqual(
                result,
                ["npx", "--no-install", "--package", "typescript", "tsc"],
            )
        finally:
            shutil.rmtree(d, ignore_errors=True)


# =====================================================================
# has_typescript_project(project) -- VAC4-VAC7
# =====================================================================

class VAC4HasTypescriptProjectTrueCases(unittest.TestCase):
    """[BEHAVIORAL] VAC4: True requires BOTH a root tsconfig.json AND a
    package.json declaring `typescript` -- in EITHER dependencies or
    devDependencies (mirrors detect_node_runner's own dependency-
    declaration gate, which also checks both dep buckets)."""

    def test_true_when_typescript_in_devdependencies(self):
        d = tempfile.mkdtemp()
        try:
            _write(os.path.join(d, "tsconfig.json"), TSCONFIG_JSON)
            _write(os.path.join(d, "package.json"), PACKAGE_JSON_WITH_TS_DEV)
            self.assertTrue(verify.has_typescript_project(d))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_true_when_typescript_in_dependencies(self):
        d = tempfile.mkdtemp()
        try:
            _write(os.path.join(d, "tsconfig.json"), TSCONFIG_JSON)
            _write(os.path.join(d, "package.json"), PACKAGE_JSON_WITH_TS_DEP)
            self.assertTrue(verify.has_typescript_project(d))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC5HasTypescriptProjectNoTsconfig(unittest.TestCase):
    """[BEHAVIORAL] VAC5: no tsconfig.json at all -> False, even though
    package.json declares `typescript`. Targets the ROOT tsconfig.json
    specifically per the design doc (PSC-TSC-1's real errors were in test
    files that only a wider root config's `include` catches); with no
    tsconfig.json anywhere, there is nothing for `tsc -p` to point at."""

    def test_false_without_tsconfig(self):
        d = tempfile.mkdtemp()
        try:
            _write(os.path.join(d, "package.json"), PACKAGE_JSON_WITH_TS_DEV)
            self.assertFalse(os.path.isfile(os.path.join(d, "tsconfig.json")))
            self.assertFalse(verify.has_typescript_project(d))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC6HasTypescriptProjectNoTypescriptDependencyDeclared(unittest.TestCase):
    """[BEHAVIORAL] VAC6: tsconfig.json present, package.json present, but
    `typescript` is NOT declared in either dependency bucket.

    Chosen contract (resolves the design doc's Open Risk 3 / explicitly
    undecided edge case, per this task's own instruction: "should return
    False/skip, not error"): has_typescript_project returns False -- a
    silent SKIP, not a raised exception and not a loud forced fail.
    Rationale: this function is a ROUTING predicate (should the tsc gate
    run at all), analogous to detect_node_runner's own silent
    return-None-on-no-known-runner behavior; VAC7's precedent for a LOUD
    forced fail belongs to detect_and_run's own "package.json present but
    declares no known TEST runner" call site, a different function with a
    different, already-established contract -- not this one."""

    def test_false_and_does_not_raise_without_typescript_dependency(self):
        d = tempfile.mkdtemp()
        try:
            _write(os.path.join(d, "tsconfig.json"), TSCONFIG_JSON)
            _write(os.path.join(d, "package.json"), PACKAGE_JSON_NO_TS)
            try:
                result = verify.has_typescript_project(d)
            except Exception as e:
                self.fail("must not raise on a tsconfig-without-typescript-dep "
                         "project, got %r: %s" % (type(e), e))
            self.assertFalse(result)
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC7HasTypescriptProjectTsconfigNoPackageJson(unittest.TestCase):
    """[BEHAVIORAL] VAC7: tsconfig.json present but NO package.json file
    at all -> False, not an error (edge case named explicitly in this
    task's brief). Package.json absence means the dependency-declaration
    check can never be confirmed, so the routing gate must fail closed
    (skip the tsc gate) rather than raise or default to True."""

    def test_false_and_does_not_raise_without_package_json(self):
        d = tempfile.mkdtemp()
        try:
            _write(os.path.join(d, "tsconfig.json"), TSCONFIG_JSON)
            self.assertFalse(os.path.isfile(os.path.join(d, "package.json")))
            try:
                result = verify.has_typescript_project(d)
            except Exception as e:
                self.fail("must not raise when package.json is missing, "
                         "got %r: %s" % (type(e), e))
            self.assertFalse(result)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# =====================================================================
# _parse_tsc_errors(combined_output) -- VAC8-VAC13
# =====================================================================

class VAC8ParseTscErrorsSingleError(unittest.TestCase):
    """[BEHAVIORAL] VAC8: one tsc error line -> a set with exactly one
    (relpath, code) fingerprint."""

    def test_single_error_returns_one_fingerprint(self):
        output = (
            "src/foo.ts(12,5): error TS2322: Type 'string' is not "
            "assignable to type 'number'.\n"
        )
        result = verify._parse_tsc_errors(output)
        self.assertIsInstance(result, set)
        self.assertEqual(result, {("src/foo.ts", "TS2322")})


class VAC9ParseTscErrorsMultipleErrorsSameFile(unittest.TestCase):
    """[BEHAVIORAL] VAC9: two DIFFERENT error codes in the SAME file ->
    two distinct fingerprints (file alone is not the whole fingerprint)."""

    def test_two_different_codes_same_file(self):
        output = (
            "src/foo.ts(12,5): error TS2322: Type 'string' is not "
            "assignable to type 'number'.\n"
            "src/foo.ts(20,10): error TS2345: Argument of type 'number' "
            "is not assignable to parameter of type 'string'.\n"
        )
        result = verify._parse_tsc_errors(output)
        self.assertEqual(
            result,
            {("src/foo.ts", "TS2322"), ("src/foo.ts", "TS2345")},
        )


class VAC10ParseTscErrorsMultipleFiles(unittest.TestCase):
    """[BEHAVIORAL] VAC10: errors spread across multiple files -> one
    fingerprint per (file, code) pair."""

    def test_errors_across_multiple_files(self):
        output = (
            "src/foo.ts(12,5): error TS2322: Type 'string' is not "
            "assignable to type 'number'.\n"
            "src/bar.ts(3,1): error TS2307: Cannot find module "
            "'./missing'.\n"
        )
        result = verify._parse_tsc_errors(output)
        self.assertEqual(
            result,
            {("src/foo.ts", "TS2322"), ("src/bar.ts", "TS2307")},
        )


class VAC11ParseTscErrorsZeroErrors(unittest.TestCase):
    """[BEHAVIORAL] VAC11: no error lines present -> empty set. Covers
    both a fully empty string and a clean tsc run's actual output shape
    (verified live this session: a clean `tsc --noEmit` run prints
    nothing at all to stdout/stderr, exit 0)."""

    def test_empty_string_returns_empty_set(self):
        self.assertEqual(verify._parse_tsc_errors(""), set())

    def test_whitespace_only_output_returns_empty_set(self):
        self.assertEqual(verify._parse_tsc_errors("\n"), set())


class VAC12ParseTscErrorsMalformedInput(unittest.TestCase):
    """[BEHAVIORAL] VAC12: garbage/non-diagnostic text (npm warnings, log
    noise, anything that isn't a `file(line,col): error TSXXXX: ...`
    line) must be safely ignored -> empty set, no crash."""

    def test_garbage_text_with_no_tsc_error_lines_does_not_crash(self):
        output = (
            "npm WARN deprecated some-package@1.0.0: use something else\n"
            "some random noise that is not a tsc diagnostic at all\n"
            "Found 0 errors. Watching for file changes.\n"
        )
        try:
            result = verify._parse_tsc_errors(output)
        except Exception as e:
            self.fail("must not crash on non-diagnostic text, got %r: %s"
                      % (type(e), e))
        self.assertEqual(result, set())


class VAC13ParseTscErrorsFingerprintExcludesLineAndMessage(unittest.TestCase):
    """[BEHAVIORAL] VAC13: the CRITICAL fingerprint-shape decision (this
    is the design doc's open TODO #1, resolved here). Chosen contract: a
    fingerprint is (relative_file_path, ts_error_code) ONLY -- explicitly
    NOT line/column and NOT the raw message text.

    Two tsc error lines for the SAME file and the SAME error code, but
    with DIFFERENT line/column numbers AND different message text, MUST
    collapse to a single fingerprint in the returned set. This is
    required because line numbers shift as unrelated code in the same
    file changes across micro-steps -- a line- or message-sensitive
    fingerprint would manufacture a false "new" error on every
    micro-step even when nothing about that specific defect changed,
    which is exactly the false-positive failure mode the design doc's
    baseline redesign exists to prevent."""

    def test_same_file_and_code_different_line_and_message_collapses_to_one(self):
        output = (
            "src/foo.ts(12,5): error TS2322: Type 'string' is not "
            "assignable to type 'number'.\n"
            "src/foo.ts(99,1): error TS2322: Type 'boolean' is not "
            "assignable to type 'number'.\n"
        )
        result = verify._parse_tsc_errors(output)
        self.assertEqual(
            result, {("src/foo.ts", "TS2322")},
            "same file+code at different line/col with different message "
            "text must collapse to ONE fingerprint, got %r" % (result,)
        )

    def test_fingerprint_tuples_are_exactly_file_and_code_shape(self):
        """Each element of the returned set must be a 2-element (file,
        code) pair -- not a 3+ element structure that also carries
        line/column/message alongside them."""
        output = (
            "src/foo.ts(12,5): error TS2322: Type 'string' is not "
            "assignable to type 'number'.\n"
        )
        result = verify._parse_tsc_errors(output)
        self.assertEqual(len(result), 1)
        entry = tuple(next(iter(result)))
        self.assertEqual(
            len(entry), 2,
            "fingerprint must be exactly (file, code), got %r" % (entry,)
        )
        self.assertEqual(entry, ("src/foo.ts", "TS2322"))


# =====================================================================
# _load_type_check_baseline(project) -- VAC14-VAC16
# =====================================================================

@pytest.mark.slow
@unittest.skipUnless(_padsplit_hoisted_tsc_available(),
                     "padsplit-cockpit hoisted tsc binary not present on this machine")
@unittest.skipUnless(_node_available(), "node not on PATH")
class VAC14LoadTypeCheckBaselineBootstrap(unittest.TestCase):
    """[BEHAVIORAL] VAC14: the SELF-BOOTSTRAPPING contract (design doc's
    open TODO #2, resolved here). When <project>/.loop_type_check_baseline
    .json does NOT exist, this is the FIRST checkpoint for the slice:
    _load_type_check_baseline computes the project's CURRENT tsc error
    set (via the SAME invocation _type_check_gate itself uses --
    _resolve_tsc_binary + `--noEmit -p tsconfig.json`, parsed by
    _parse_tsc_errors), WRITES that set to the baseline file, and RETURNS
    it. This makes the very first checkpoint of a slice always establish
    baseline == current state, so it always passes with zero new errors
    -- no separate "capture baseline" step is ever required."""

    def test_bootstrap_creates_file_and_returns_current_errors(self):
        d = _make_tsc_scratch_dir()
        try:
            _write(os.path.join(d, "tsconfig.json"), TSCONFIG_JSON)
            _write(os.path.join(d, "package.json"), PACKAGE_JSON_WITH_TS_DEV)
            _write(os.path.join(d, "a.ts"), ONE_TS_ERROR_FILE)
            _write(os.path.join(d, "b.ts"), ANOTHER_TS_ERROR_FILE)
            baseline_path = os.path.join(d, ".loop_type_check_baseline.json")
            self.assertFalse(os.path.isfile(baseline_path),
                             "baseline file must not pre-exist before bootstrap")

            # Independently compute "current errors" via the same public
            # primitives _type_check_gate itself uses, so this test does
            # not just trust whatever _load_type_check_baseline claims --
            # it cross-checks against a fresh, separately-run tsc call.
            argv = verify._resolve_tsc_binary(d) + [
                "--noEmit", "-p", os.path.join(d, "tsconfig.json"),
            ]
            code, out, err = verify.run(argv, d, timeout=120)
            expected_current = verify._parse_tsc_errors((out + "\n" + err).strip())
            self.assertEqual(
                len(expected_current), 2,
                "fixture must independently reproduce exactly 2 real tsc "
                "errors, got %r (exit=%s)" % (expected_current, code)
            )

            baseline = verify._load_type_check_baseline(d)

            self.assertTrue(os.path.isfile(baseline_path),
                            "bootstrap must have written the baseline file")
            self.assertEqual(set(tuple(x) for x in baseline), expected_current)

            with open(baseline_path) as f:
                on_disk = json.load(f)
            self.assertEqual(
                set(tuple(x) for x in on_disk), expected_current,
                "baseline file on disk must match the current error set"
            )
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC15LoadTypeCheckBaselineExistingFileNotReBootstrapped(unittest.TestCase):
    """[BEHAVIORAL] VAC15: an EXISTING baseline file is loaded AS-IS,
    never re-derived from a fresh tsc run.

    Deliberately uses a directory with NO tsconfig.json / package.json at
    all (so if the implementation mistakenly tried to run tsc here, it
    would have nothing valid to run against) and pre-writes a baseline
    file containing fingerprints that could not possibly match any real
    tsc output for this project. If _load_type_check_baseline returns
    exactly the pre-written content, and the file's bytes are unchanged
    afterward, that proves the existing-file path never invokes tsc and
    never rewrites the file -- this test needs no real tsc/npx/node and
    is not marked slow."""

    def test_existing_baseline_loaded_verbatim_no_bootstrap(self):
        d = tempfile.mkdtemp()
        try:
            baseline_path = os.path.join(d, ".loop_type_check_baseline.json")
            fake_baseline = [["totally/fake/file.ts", "TS9999"],
                             ["another/fake.ts", "TS1234"]]
            with open(baseline_path, "w") as f:
                json.dump(fake_baseline, f)
            with open(baseline_path, "rb") as f:
                original_bytes = f.read()

            baseline = verify._load_type_check_baseline(d)

            self.assertEqual(
                set(tuple(x) for x in baseline),
                {("totally/fake/file.ts", "TS9999"),
                 ("another/fake.ts", "TS1234")},
                "must return the file's existing content unmodified"
            )

            with open(baseline_path, "rb") as f:
                self.assertEqual(
                    f.read(), original_bytes,
                    "existing baseline file must NOT be rewritten on a "
                    "normal load"
                )
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC16LoadTypeCheckBaselineCorruptedJson(unittest.TestCase):
    """[BEHAVIORAL] VAC16: a corrupted/malformed baseline file must fail
    LOUD with a clear, distinct message -- not silently return an
    empty/wrong baseline, and not let a low-level, unexplained exception
    (e.g. a bare json.JSONDecodeError) be the only signal.

    Chosen contract: _load_type_check_baseline RAISES an exception whose
    message clearly identifies the baseline file as the problem --
    mirroring _smoke_gate's existing "malformed smoke_manifest.json
    (...) -- smoke gate forced fail" text pattern. See VAC19 for the
    composed _type_check_gate behavior: it must catch this exception and
    convert it into the SAME (dict, error) forced-fail contract already
    used for the toolchain-unresolvable case, not let it escape."""

    def test_invalid_json_raises_clear_error(self):
        d = tempfile.mkdtemp()
        try:
            baseline_path = os.path.join(d, ".loop_type_check_baseline.json")
            with open(baseline_path, "w") as f:
                f.write("{not valid json at all")
            with self.assertRaises(Exception) as ctx:
                verify._load_type_check_baseline(d)
            msg = str(ctx.exception).lower()
            self.assertTrue(
                "baseline" in msg or "json" in msg,
                "exception message should clearly identify the baseline "
                "file as the problem, got: %r" % (str(ctx.exception),)
            )
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_wrong_schema_raises_clear_error(self):
        """Valid JSON but the WRONG SHAPE (not a list of [file, code]
        pairs, e.g. a bare object) must also fail loud, not be silently
        accepted as an empty/garbage baseline."""
        d = tempfile.mkdtemp()
        try:
            baseline_path = os.path.join(d, ".loop_type_check_baseline.json")
            with open(baseline_path, "w") as f:
                json.dump({"not": "a list of pairs"}, f)
            with self.assertRaises(Exception):
                verify._load_type_check_baseline(d)
        finally:
            shutil.rmtree(d, ignore_errors=True)


# =====================================================================
# _type_check_gate(project) -- VAC17-VAC21 (composed)
# =====================================================================

class VAC17TypeCheckGateNoTypescriptProjectInert(unittest.TestCase):
    """[BEHAVIORAL] VAC17: a non-TypeScript project is fully inert --
    ran=False, passed=True, new_errors=[] -- mirroring the pre-existing
    naive _run_tsc_gate's own "ran=False, passed=True" no-op contract, so
    a plain Python/JS project is never affected by this gate."""

    def test_no_tsconfig_is_inert(self):
        d = tempfile.mkdtemp()
        try:
            result, error = verify._type_check_gate(d)
            self.assertIsNone(error)
            self.assertFalse(result["ran"])
            self.assertTrue(result["passed"])
            self.assertEqual(result.get("new_errors"), [])
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC18TypeCheckGateToolchainUnresolvableForcedFail(unittest.TestCase):
    """[BEHAVIORAL] VAC18: when tsc genuinely cannot be resolved/run (npx
    reports "canceled due to missing packages", i.e. typescript isn't
    installed/cached anywhere), _type_check_gate must return a DISTINCT
    forced-fail -- (dict, error) with error not None -- never folded into
    the same path as a real type error, so a missing toolchain is never
    misreported as "your code is wrong."

    Mocks verify.run directly (no real subprocess) so this test needs no
    network and is not marked slow."""

    @mock.patch.object(verify, "run")
    def test_toolchain_unresolvable_is_distinct_forced_fail(self, mock_run):
        d = tempfile.mkdtemp()
        try:
            _write(os.path.join(d, "tsconfig.json"), TSCONFIG_JSON)
            _write(os.path.join(d, "package.json"), PACKAGE_JSON_WITH_TS_DEV)
            mock_run.return_value = (
                1, "",
                'npm error npx canceled due to missing packages: ["tsc@2.0.4"]',
            )
            result, error = verify._type_check_gate(d)
            self.assertIsNotNone(
                error, "toolchain-unresolvable case must return a non-None error"
            )
            self.assertFalse(result["passed"])
            self.assertFalse(result.get("ran", False))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class VAC19TypeCheckGateCorruptedBaselinePropagatesAsForcedFailNotCrash(unittest.TestCase):
    """[BEHAVIORAL] VAC19: a corrupted baseline file must surface through
    the COMPOSED _type_check_gate as the SAME (dict, error) forced-fail
    contract used for the toolchain-unresolvable case -- never an
    uncaught exception escaping the function. This is what "matching the
    existing forced-fail pattern _smoke_gate/_type_check_gate already use
    for toolchain-unresolvable" (per this task's own brief) means at the
    composed-gate level: main()'s always-prints-JSON contract must never
    be broken by a bad baseline file on disk."""

    @mock.patch.object(verify, "run")
    def test_corrupted_baseline_forced_fail_not_uncaught_exception(self, mock_run):
        d = tempfile.mkdtemp()
        try:
            _write(os.path.join(d, "tsconfig.json"), TSCONFIG_JSON)
            _write(os.path.join(d, "package.json"), PACKAGE_JSON_WITH_TS_DEV)
            baseline_path = os.path.join(d, ".loop_type_check_baseline.json")
            with open(baseline_path, "w") as f:
                f.write("{not valid json at all")
            # Simulate a clean, successful tsc run (0 errors, exit 0) so the
            # toolchain-unresolvable branch does NOT fire -- isolating the
            # baseline-corruption path specifically.
            mock_run.return_value = (0, "", "")

            try:
                result, error = verify._type_check_gate(d)
            except Exception as e:  # the exact failure mode this test targets
                self.fail(
                    "a corrupted baseline file must not crash _type_check_gate "
                    "with an uncaught exception; got %r: %s" % (type(e), e)
                )

            self.assertIsNotNone(
                error, "corrupted baseline must produce a non-None forced-fail error"
            )
            self.assertFalse(result["passed"])
        finally:
            shutil.rmtree(d, ignore_errors=True)


@pytest.mark.slow
@unittest.skipUnless(_padsplit_hoisted_tsc_available(),
                     "padsplit-cockpit hoisted tsc binary not present on this machine")
@unittest.skipUnless(_node_available(), "node not on PATH")
class VAC20TypeCheckGateBaselineScopingRegression(unittest.TestCase):
    """[BEHAVIORAL] VAC20: THE critical baseline-scoping regression test
    named explicitly in this task's brief.

    A synthetic project starts with 2 PRE-EXISTING tsc errors, each in
    its own file (a.ts, b.ts -- both TS2322, confirmed live this session
    to be the actual tsc output for these exact fixtures). On the FIRST
    call to _type_check_gate, no baseline file exists yet, so
    _load_type_check_baseline bootstraps: it runs tsc itself, captures
    the current 2-error set as the baseline, and _type_check_gate must
    report passed=True with an EMPTY new_errors list -- the 2
    pre-existing errors are the accepted floor, not "new". This is what
    makes Test-writer's pre-existing RED files non-blocking with no
    separate "capture baseline" step, exactly as the design doc requires.

    A SECOND call, after one genuinely NEW error is introduced in a third
    file (c.ts, also TS2322), must report passed=False with new_errors
    containing EXACTLY ONE fingerprint -- c.ts's -- and must NOT
    re-surface either of the 2 original pre-existing errors as "new".
    This is the regression this test exists to catch: a scoping bug that
    diffs against an empty/wrong baseline, or re-derives the baseline
    fresh on every run instead of loading the persisted file, would
    incorrectly report 3 new errors instead of 1.
    """

    def test_first_run_bootstraps_baseline_second_run_flags_only_the_new_error(self):
        d = _make_tsc_scratch_dir()
        try:
            _write(os.path.join(d, "tsconfig.json"), TSCONFIG_JSON)
            _write(os.path.join(d, "package.json"), PACKAGE_JSON_WITH_TS_DEV)
            _write(os.path.join(d, "a.ts"), ONE_TS_ERROR_FILE)
            _write(os.path.join(d, "b.ts"), ANOTHER_TS_ERROR_FILE)
            baseline_path = os.path.join(d, ".loop_type_check_baseline.json")
            self.assertFalse(os.path.isfile(baseline_path),
                             "baseline file must not pre-exist before the first run")

            # -- First run: bootstrap. --
            result1, error1 = verify._type_check_gate(d)
            self.assertIsNone(error1, "first run must not forced-fail: %r" % (error1,))
            self.assertTrue(result1["ran"])
            self.assertTrue(
                result1["passed"],
                "first run must PASS -- baseline bootstraps to current state "
                "(2 pre-existing errors), so new_errors must be empty: %r" % result1
            )
            self.assertEqual(result1.get("new_errors"), [])
            self.assertTrue(os.path.isfile(baseline_path),
                            "first run must have written the baseline file")

            # -- Introduce exactly ONE new, genuine error in a third file. --
            _write(os.path.join(d, "c.ts"), THIRD_TS_ERROR_FILE)

            # -- Second run: baseline file already exists, must be LOADED,
            #    not re-bootstrapped -- so it still only contains a.ts/b.ts's
            #    2 original errors, making c.ts's the only new one. --
            result2, error2 = verify._type_check_gate(d)
            self.assertIsNone(error2)
            self.assertTrue(result2["ran"])
            self.assertFalse(
                result2["passed"],
                "second run must FAIL -- a genuinely new error was introduced: %r" % result2
            )
            new_errors = result2.get("new_errors") or []
            self.assertEqual(
                len(new_errors), 1,
                "expected EXACTLY 1 new error (c.ts's), got %d: %r -- a "
                "baseline-scoping bug would re-surface a.ts/b.ts's 2 "
                "pre-existing errors as new, producing 3 instead of 1"
                % (len(new_errors), new_errors)
            )
            new_file, new_code = tuple(new_errors[0])
            self.assertTrue(
                new_file.endswith("c.ts"),
                "the single new error must belong to c.ts, got %r" % (new_file,)
            )
            self.assertEqual(new_code, "TS2322")

            new_fingerprint_files = {f for f, _c in (tuple(e) for e in new_errors)}
            self.assertFalse(
                any(f.endswith("a.ts") for f in new_fingerprint_files),
                "a.ts's pre-existing error incorrectly resurfaced as new"
            )
            self.assertFalse(
                any(f.endswith("b.ts") for f in new_fingerprint_files),
                "b.ts's pre-existing error incorrectly resurfaced as new"
            )
        finally:
            shutil.rmtree(d, ignore_errors=True)


@pytest.mark.slow
@unittest.skipUnless(_padsplit_hoisted_tsc_available(),
                     "padsplit-cockpit hoisted tsc binary not present on this machine")
@unittest.skipUnless(_node_available(), "node not on PATH")
class VAC21TypeCheckGateCleanProjectBootstrapsEmptyBaseline(unittest.TestCase):
    """[BEHAVIORAL] VAC21: a project with ZERO tsc errors on its first run
    bootstraps an EMPTY baseline and passes -- the empty-baseline edge of
    the same bootstrap contract VAC14/VAC20 exercise with a non-empty
    one."""

    def test_clean_project_first_run_passes_with_empty_baseline(self):
        d = _make_tsc_scratch_dir()
        try:
            _write(os.path.join(d, "tsconfig.json"), TSCONFIG_JSON)
            _write(os.path.join(d, "package.json"), PACKAGE_JSON_WITH_TS_DEV)
            _write(os.path.join(d, "ok.ts"), CLEAN_TS_FILE)

            result, error = verify._type_check_gate(d)
            self.assertIsNone(error)
            self.assertTrue(result["ran"])
            self.assertTrue(result["passed"])
            self.assertEqual(result.get("new_errors"), [])

            baseline_path = os.path.join(d, ".loop_type_check_baseline.json")
            self.assertTrue(os.path.isfile(baseline_path))
            with open(baseline_path) as f:
                on_disk = json.load(f)
            self.assertEqual(on_disk, [])
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
