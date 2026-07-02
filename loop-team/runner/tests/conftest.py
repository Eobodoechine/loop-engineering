"""
conftest.py — shared fixtures for runner tests.

Key design decisions resolved here:
- sample_config writes a real temp file at a known path so the config parser
  can be tested end-to-end (no mocking of file I/O for the happy path).
- LOOP_TEAM_BASE_DIR points to the live repo so AC3 (role file loading) uses
  the real coder.md without any additional fixtures.
- The fixture tears down the temp config file after each test.
"""
import os
import pathlib
import textwrap
import pytest


# Canonical base dir: the directory that CONTAINS the loop-team/ tree (with
# roles/ and optimize/). Tests that touch the real filesystem use this.
#
# Derived from this file's location so it resolves correctly in any checkout
# (CI, sandbox, fresh clone) instead of a hardcoded home path. This file lives
# at <repo>/loop-team/runner/tests/conftest.py, and the runner expects role
# files at <base_dir>/loop-team/roles/*.md, so base_dir is the repo root that
# contains loop-team/.
LOOPTEAM_DIR = pathlib.Path(__file__).resolve().parents[2]  # <repo>/loop-team
REAL_BASE_DIR = LOOPTEAM_DIR.parent                          # <repo> (contains loop-team/)

# Fail loudly if the layout assumption is wrong, rather than letting tests fail
# later with an opaque FileNotFoundError on roles/coder.md.
assert (REAL_BASE_DIR / "loop-team" / "roles" / "coder.md").exists(), (
    f"REAL_BASE_DIR derivation is wrong: expected role file at "
    f"{REAL_BASE_DIR / 'loop-team' / 'roles' / 'coder.md'} but it does not exist"
)


@pytest.fixture
def sample_config(tmp_path, monkeypatch):
    """
    Write a minimal ~/.loop-team-config substitute to a temp file and return
    its path.  The fixture also monkeypatches the HOME so that any code that
    looks up ~/.loop-team-config will find this temp file automatically.

    Config contents:
        base_dir=<REAL_BASE_DIR>           (repo root containing loop-team/)
        provider=anthropic
        default_model=claude-haiku-4-5-20251001
        role.coder.provider=openai
        role.coder.model=gpt-4o-mini
    """
    # Write config into a fake HOME so ~/.loop-team-config resolves correctly.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    config_text = textwrap.dedent(f"""\
        base_dir={REAL_BASE_DIR}
        provider=anthropic
        default_model=claude-haiku-4-5-20251001
        role.coder.provider=openai
        role.coder.model=gpt-4o-mini
    """)
    config_path = fake_home / ".loop-team-config"
    config_path.write_text(config_text)
    return config_path


@pytest.fixture
def real_base_dir():
    """Return the canonical base_dir Path (repo root containing loop-team/, derived from __file__)."""
    return REAL_BASE_DIR
