"""Tests for runner.version() — currently FAILING (function not yet implemented).

All tests are classified as [DOC] or [BEHAVIORAL] in inline comments.
"""
import pathlib
import sys

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PYPROJECT_TOML = pathlib.Path(__file__).parent.parent / "pyproject.toml"


def _read_pyproject_version() -> str:
    """Parse the version string from runner/pyproject.toml at test-run time.

    Strategy (in order):
      1. tomllib  — stdlib on Python 3.11+
      2. tomli    — third-party back-port for 3.10
      3. text fallback — locate the line `version = "x.y.z"` in the [project]
         section; safe for simple single-line values.
    """
    raw = PYPROJECT_TOML.read_text(encoding="utf-8")

    # Attempt proper TOML parsing first.
    try:
        if sys.version_info >= (3, 11):
            import tomllib  # type: ignore[import]
            data = tomllib.loads(raw)
        else:
            import tomli  # type: ignore[import]
            data = tomli.loads(raw)
        return data["project"]["version"]
    except (ImportError, ModuleNotFoundError):
        pass

    # Text fallback: scan for `version = "..."` after the [project] header.
    in_project = False
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("[") and stripped != "[project]":
            in_project = False
        if in_project and stripped.startswith("version"):
            _, _, rhs = stripped.partition("=")
            return rhs.strip().strip('"').strip("'")

    raise RuntimeError(
        f"Could not extract version from {PYPROJECT_TOML}"
    )


# ---------------------------------------------------------------------------
# [DOC] Sanity: pyproject.toml is readable and has a version field
# ---------------------------------------------------------------------------

def test_pyproject_toml_exists_and_has_version():
    # [DOC] Confirms the test fixture itself is healthy; if this fails the
    # pyproject.toml file is missing or malformed, not runner.version.
    version_str = _read_pyproject_version()
    assert isinstance(version_str, str), "pyproject.toml version must be a string"
    assert version_str, "pyproject.toml version must not be empty"


# ---------------------------------------------------------------------------
# [BEHAVIORAL] version() is importable from the runner package
# ---------------------------------------------------------------------------

def test_version_is_importable():
    # [BEHAVIORAL] Importing `version` from `runner` must not raise.
    from runner import version  # noqa: F401  — ImportError = fail


# ---------------------------------------------------------------------------
# [BEHAVIORAL] version() returns exactly '0.1.0'
# ---------------------------------------------------------------------------

def test_version_returns_current_string():
    # [BEHAVIORAL] Core acceptance: version() == '0.1.0' (the value locked in
    # pyproject.toml at the time this spec was written).
    from runner import version
    assert version() == "0.1.0"


# ---------------------------------------------------------------------------
# [BEHAVIORAL] version() == pyproject.toml at runtime (future-proof gate)
# ---------------------------------------------------------------------------

def test_version_matches_pyproject_toml():
    # [BEHAVIORAL] If pyproject.toml is bumped (e.g. to '0.2.0') but
    # runner.version() is not updated, this test must FAIL — ensuring the two
    # sources stay in sync.
    from runner import version
    expected = _read_pyproject_version()
    assert version() == expected, (
        f"runner.version() returned {version()!r} but pyproject.toml says {expected!r}"
    )


# ---------------------------------------------------------------------------
# [BEHAVIORAL] Return type is str (not bytes, int, None, or other)
# ---------------------------------------------------------------------------

def test_version_return_type_is_str():
    # [BEHAVIORAL] Edge case: version() must return a plain str, not bytes,
    # int, float, None, or any other type.
    from runner import version
    result = version()
    assert isinstance(result, str), (
        f"version() must return str, got {type(result).__name__!r}"
    )


# ---------------------------------------------------------------------------
# [BEHAVIORAL] 'version' appears in runner.__all__
# ---------------------------------------------------------------------------

def test_version_in_dunder_all():
    # [BEHAVIORAL] The public API contract: 'version' must be listed in
    # runner.__all__ so `from runner import *` exposes it.
    import runner
    assert hasattr(runner, "__all__"), "runner must define __all__"
    assert "version" in runner.__all__, (
        f"'version' not found in runner.__all__: {runner.__all__!r}"
    )
