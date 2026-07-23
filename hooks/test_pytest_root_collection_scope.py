#!/usr/bin/env python3
"""Tests for the repo-root pytest collection-scope fix.

Spec: loop-team/runs/2026-07-02_pytest-root-collection-fault/specs/spec.md

Bare `pytest -q` (or `pytest --testmon -q` on a cold cache) invoked from the
repo root recursively discovers every `tests/` directory under the tree,
including historical, isolated build artifacts under `runs/<timestamp>/project/
tests/`. Multiple sibling `runs/*/project/tests/` directories each define a
same-named `tests` package, and pytest's default rootdir-relative import
registers only the first one under `sys.modules['tests']` — every subsequent
same-named module in a *different* `runs/*/project/tests/` directory then
fails collection with `ModuleNotFoundError`.

The fix must be a PATH-ANCHORED exclusion (e.g. `--ignore-glob=runs/*` in a
root `pytest.ini`), NOT a basename-only `norecursedirs = runs` — the latter
was empirically DISPROVEN in round 1 of this spec's plan-check: pytest's
`norecursedirs` does `fnmatch_ex` against the basename at every depth, so it
also matches the unrelated `loop-team/runs/` directory (which holds 39 real,
currently-passing tests) and silently drops coverage (734 collected instead
of the correct 773).

These tests are RED-BY-DESIGN as written: no pytest.ini exists yet at the
repo root, so AC1's config-content test and the subprocess collection tests
below are expected to fail until the Coder adds the path-anchored fix. Do
not weaken these assertions to make them pass early — that would defeat the
point of a red-by-design test.
"""
import configparser
import os
import re
import subprocess
import sys

import pytest

# Repo root = two levels up from hooks/test_pytest_root_collection_scope.py
# (hooks/ -> repo root).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PYTEST_INI_PATH = os.path.join(REPO_ROOT, "pytest.ini")

# The exact historical artifact path round-1 plan-check flagged as the
# regression risk: a same-named sibling `tests` package under the top-level
# `runs/` directory that must be EXCLUDED after the fix.
EXCLUDED_HISTORICAL_PATH = "runs/2026-06-29-rent-from-owner-mode"

# The exact path proving the 39 real tests under loop-team/runs/ are NOT
# swept up by a basename-only exclusion — this must remain COLLECTED.
MUST_REMAIN_COLLECTED_PATH = (
    "loop-team/runs/2026-06-21_181725-fb-launchd-pathA"
)


def _run_pytest(args, cwd=REPO_ROOT, timeout=120):
    """Run a real pytest subprocess from the repo root and capture output."""
    return subprocess.run(
        [sys.executable, "-m", "pytest"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class TestPytestIniExistsAndIsPathAnchored:
    """[DOC] A pytest.ini must exist at repo root and its content must encode
    a path-anchored exclusion, not the disproven basename-only pattern."""

    def test_pytest_ini_exists_at_repo_root(self):
        """AC4: a pytest.ini (or equivalent) exists at ~/Claude/loop/pytest.ini."""
        assert os.path.isfile(PYTEST_INI_PATH), (
            f"Expected a pytest config at {PYTEST_INI_PATH}. "
            "No root-level pytest.ini/pyproject.toml/setup.cfg/conftest.py "
            "exists yet — this is the uncorrected state this spec fixes."
        )

    def test_pytest_ini_does_not_use_bare_norecursedirs_runs(self):
        """AC4: must NOT use the disproven basename-only `norecursedirs = runs`
        anti-pattern, which fnmatch-matches the basename at every depth and
        silently also excludes the unrelated loop-team/runs/ directory."""
        if not os.path.isfile(PYTEST_INI_PATH):
            pytest.fail(f"{PYTEST_INI_PATH} does not exist yet (see previous test).")

        content = open(PYTEST_INI_PATH, encoding="utf-8").read()

        # Look for a norecursedirs line whose value set includes the bare
        # basename "runs" (with no path separator / anchor) — this is the
        # exact anti-pattern round-1 plan-check disproved.
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            m = re.match(r"norecursedirs\s*=\s*(.+)$", stripped)
            if not m:
                continue
            values = m.group(1).split()
            for v in values:
                assert v.strip() != "runs", (
                    "pytest.ini uses bare `norecursedirs = runs`, the "
                    "disproven anti-pattern: pytest's norecursedirs does "
                    "fnmatch_ex against the basename at EVERY depth, so it "
                    "also matches loop-team/runs/ and silently drops the "
                    "39 real tests there (734 collected instead of 773). "
                    "Use a path-anchored exclusion instead "
                    "(e.g. --ignore-glob=runs/* in addopts)."
                )

    def test_pytest_ini_uses_path_anchored_exclusion(self):
        """AC4: the fix must use a path-anchored exclusion relative to repo
        root (e.g. `--ignore-glob=runs/*` in addopts), so only the top-level
        runs/ is excluded and loop-team/runs/ keeps collecting normally."""
        if not os.path.isfile(PYTEST_INI_PATH):
            pytest.fail(f"{PYTEST_INI_PATH} does not exist yet (see previous test).")

        parser = configparser.ConfigParser()
        parser.read(PYTEST_INI_PATH)
        assert parser.has_section("pytest"), (
            "pytest.ini has no [pytest] section — cannot verify addopts."
        )

        addopts = parser.get("pytest", "addopts", fallback="")

        # Path-anchored pattern: must reference "runs/*" or "./runs/*" (a
        # glob anchored at repo root), not a bare "runs" basename token.
        path_anchored = re.search(r"(?:^|[\s=])\.?/?runs/\*", addopts)
        assert path_anchored, (
            "pytest.ini's [pytest] addopts does not contain a path-anchored "
            "exclusion for the top-level runs/ directory (expected something "
            "like `--ignore-glob=runs/*`). Got addopts=" + repr(addopts)
        )

        # Explicitly confirm it's expressed via --ignore-glob (the mechanism
        # round-1 plan-check empirically verified: 773 collected, 0 errors)
        # rather than via norecursedirs (already independently checked above,
        # but assert the presence of the positive mechanism too).
        assert "--ignore-glob" in addopts, (
            "Expected --ignore-glob=runs/* (or equivalent path-anchored "
            "ignore mechanism) in addopts. Got addopts=" + repr(addopts)
        )


class TestBarePytestCollectionFromRepoRoot:
    """[BEHAVIORAL] Real subprocess invocations of pytest from the repo root
    must not produce collection errors, must not drop the loop-team/runs/
    coverage, and must exclude the top-level runs/ historical artifacts."""

    def test_bare_pytest_collect_only_exits_cleanly_with_no_module_not_found_errors(self):
        """AC1: `python3 -m pytest -q --collect-only` from repo root exits
        0 or 5 and produces zero ModuleNotFoundError / collection errors."""
        result = _run_pytest(["-q", "--collect-only"])
        combined = result.stdout + result.stderr

        assert result.returncode in (0, 5), (
            f"Expected exit code 0 or 5, got {result.returncode}.\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
        assert "ModuleNotFoundError" not in combined, (
            "Bare pytest collection from repo root produced a "
            "ModuleNotFoundError — sibling runs/*/project/tests/ packages "
            "are colliding under sys.modules['tests']. Full output:\n"
            f"{combined}"
        )
        assert "errors during collection" not in combined, (
            "Bare pytest collection from repo root reported collection "
            f"errors. Full output:\n{combined}"
        )

    def test_top_level_runs_historical_artifact_is_excluded_from_collection(self):
        """AC2/AC4: the excluded top-level runs/ path must NOT appear
        anywhere in the collected item list after the fix."""
        result = _run_pytest(["-q", "--collect-only"])
        combined = result.stdout + result.stderr

        assert EXCLUDED_HISTORICAL_PATH not in combined, (
            f"Expected '{EXCLUDED_HISTORICAL_PATH}' to be absent from "
            "collect-only output (it must be excluded by the path-anchored "
            f"runs/* ignore), but it was found. Output:\n{combined}"
        )

    def test_loop_team_runs_real_tests_still_collected(self):
        """AC2 (regression guard): the 39 real, currently-passing tests
        under loop-team/runs/ must still be discovered and collected — this
        is the exact regression a basename-only `norecursedirs = runs`
        anti-pattern would silently cause (734 collected instead of 773)."""
        result = _run_pytest(["-q", "--collect-only"])
        combined = result.stdout + result.stderr

        assert MUST_REMAIN_COLLECTED_PATH in combined, (
            f"Expected '{MUST_REMAIN_COLLECTED_PATH}' to still appear in "
            "collect-only output (loop-team/runs/ must NOT be swept up by "
            "the runs/ exclusion — only the top-level runs/ should be "
            f"excluded). Output:\n{combined}"
        )


class TestTestmonColdCacheCollectionFromRepoRoot:
    """[BEHAVIORAL] AC3 — the exact invocation _testmon_gate runs
    (`pytest --testmon -q` from repo root) must also exit cleanly on a cold
    .testmondata cache, since that's the first real exercise of a bare
    root-level pytest run once micro-step gates are armed."""

    def test_testmon_cold_cache_collection_has_no_errors(self):
        testmondata = os.path.join(REPO_ROOT, ".testmondata")
        if os.path.isfile(testmondata):
            os.remove(testmondata)

        try:
            result = _run_pytest(["--testmon", "-q"], timeout=1200)
        except FileNotFoundError:
            pytest.skip(
                "pytest-testmon plugin not installed in this environment; "
                "cannot exercise the exact _testmon_gate invocation shape."
            )
            return

        combined = result.stdout + result.stderr

        if "unrecognized arguments" in combined and "--testmon" in combined:
            pytest.skip(
                "pytest-testmon plugin not installed in this environment; "
                "cannot exercise the exact _testmon_gate invocation shape."
            )
            return

        assert result.returncode in (0, 5), (
            f"Expected exit code 0 or 5 on cold-cache --testmon run, got "
            f"{result.returncode}.\n--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
        assert "ModuleNotFoundError" not in combined, (
            "Cold-cache `pytest --testmon -q` from repo root produced a "
            f"ModuleNotFoundError. Full output:\n{combined}"
        )
        assert "errors during collection" not in combined, (
            "Cold-cache `pytest --testmon -q` from repo root reported "
            f"collection errors. Full output:\n{combined}"
        )


class TestSelfConsistency:
    """Sanity check: this test file itself must be correctly collected under
    the new pytest.ini, once it exists — proving the fix doesn't accidentally
    exclude the live hooks/ test surface it's supposed to protect."""

    def test_this_file_is_collected_under_hooks(self):
        """This file lives under hooks/, which the spec explicitly requires
        stay discoverable by a bare root pytest run. Does not assume the fix
        is in place when written; will fail red (or the whole run will error
        out before reaching this point) until pytest.ini exists."""
        result = _run_pytest(
            ["-q", "--collect-only", "hooks/test_pytest_root_collection_scope.py"]
        )
        combined = result.stdout + result.stderr

        assert result.returncode in (0, 5), (
            "Expected this test file to be collectible on its own "
            f"(exit 0 or 5), got {result.returncode}.\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
        assert "test_pytest_root_collection_scope.py" in combined, (
            "This test file did not appear in its own scoped collect-only "
            f"output. Output:\n{combined}"
        )
