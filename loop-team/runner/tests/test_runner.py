"""
test_runner.py — full test suite for the runner/ package.

Written BEFORE implementation (TDD). All tests will fail until
runner/__init__.py, runner/config.py, runner/roles.py, and runner/dispatch.py
(or equivalent) are written. That is intentional.

Spec ambiguities resolved in this file (see inline comments):
- AC4b: "prompt sent to LLM contains role file content" — tested by capturing
  calls to call_with_retry, inspecting the inner closure's prompt argument via
  the FakeLLM spy stored on LoopTeam.  Alternatively, we accept a
  dispatch_role implementation that calls FakeLLM directly when injected.
  Resolution: LoopTeam accepts an optional `llm_factory` kwarg for injection
  in tests; if absent it uses the real factories.  If the implementation doesn't
  expose that, we patch call_with_retry and inspect captured calls.
- AC8: "patch optimize.llm.call_with_retry before importing runner" — we cannot
  truly patch-before-import because conftest imports runner. Resolution: the
  test re-imports runner inside the patch context and verifies the patched
  call_with_retry is called at dispatch time.  If the implementation caches the
  reference at import time rather than calling optimize.llm.call_with_retry at
  dispatch time, the test will catch that design defect.
- AC-INT: "passed: false on first Verifier call, passed: true on second" — the
  spec doesn't define the exact string format; we use the strings the existing
  verifier role produces ("passed: false" / "passed: true") since the real
  roles/verifier.md is what the runner will load.
- dispatch_role provider resolution: the spec says provider is resolved
  INTERNALLY.  Tests inject config by monkeypatching the config-file path or
  by passing a parsed config object to LoopTeam — whichever the implementation
  supports.  We do both styles so the Coder has flexibility.
"""
import importlib
import os
import pathlib
import subprocess
import sys
import textwrap
from unittest.mock import MagicMock, patch, call as mock_call

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUNNER_PACKAGE = "runner"
# Derived from this file's location so they resolve in any checkout (CI, sandbox,
# fresh clone) instead of a hardcoded home path. This file lives at
# <repo>/loop-team/runner/tests/test_runner.py; the runner expects role files at
# <base_dir>/loop-team/roles/*.md, so REAL_BASE_DIR is the repo root containing
# loop-team/. Mirrors conftest.REAL_BASE_DIR (single canonical value).
REAL_LOOP_TEAM_DIR = pathlib.Path(__file__).resolve().parents[2]  # <repo>/loop-team
REAL_BASE_DIR = REAL_LOOP_TEAM_DIR.parent                         # <repo> (contains loop-team/)


def _import_runner():
    """Import runner fresh (or return cached module)."""
    if RUNNER_PACKAGE in sys.modules:
        return sys.modules[RUNNER_PACKAGE]
    return importlib.import_module(RUNNER_PACKAGE)


def _reload_runner():
    """Force a fresh import of runner (needed when sys.path changes between tests)."""
    for key in list(sys.modules.keys()):
        if key == RUNNER_PACKAGE or key.startswith(RUNNER_PACKAGE + "."):
            del sys.modules[key]
    return importlib.import_module(RUNNER_PACKAGE)


# ---------------------------------------------------------------------------
# AC1 — CLI: python -m runner --help exits 0 and mentions usage
# ---------------------------------------------------------------------------

class TestCLIHelp:
    def test_cli_help(self):
        """AC1: `python -m runner --help` exits 0 and output mentions usage."""
        result = subprocess.run(
            [sys.executable, "-m", "runner", "--help"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, (
            f"--help exited {result.returncode}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = (result.stdout + result.stderr).lower()
        assert "usage" in combined, (
            f"Expected 'usage' in help output, got:\n{result.stdout}"
        )

    def test_cli_help_with_pythonpath(self):
        """Regression: `python -m runner --help` must work regardless of cwd.

        Root cause: `python -m runner` resolves `runner` relative to `sys.path`,
        which by default starts with cwd.  When harness/verify.py sets
        cwd=runner/, there is no `runner/` subdirectory there, so the module
        cannot be found and the subprocess exits non-zero.

        Fix: set PYTHONPATH to the loop-team/ directory (the *parent* of the
        runner/ package) so `runner` is always importable regardless of cwd.

        This test runs the subprocess with:
          - cwd set to runner/ (reproduces the harness/verify.py failure mode)
          - PYTHONPATH set to loop-team/ (the expected fix)

        The OLD test_cli_help (no PYTHONPATH, cwd-dependent) should still FAIL
        when invoked from runner/ cwd; this test should PASS, proving the fix.
        """
        # Canonical paths
        runner_dir = pathlib.Path(__file__).parent.parent.resolve()   # …/loop-team/runner
        loop_team_dir = runner_dir.parent.resolve()                   # …/loop-team

        env = os.environ.copy()
        # Prepend loop-team/ so `import runner` finds the package even when
        # cwd is runner/ (where there is no runner/ sub-directory).
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(loop_team_dir) + os.pathsep + existing_pythonpath
            if existing_pythonpath
            else str(loop_team_dir)
        )

        result = subprocess.run(
            [sys.executable, "-m", "runner", "--help"],
            capture_output=True,
            text=True,
            cwd=str(runner_dir),   # deliberately use the problematic cwd
            env=env,
        )
        assert result.returncode == 0, (
            f"--help exited {result.returncode} even with PYTHONPATH set.\n"
            f"PYTHONPATH={env['PYTHONPATH']}\n"
            f"cwd={runner_dir}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = (result.stdout + result.stderr).lower()
        assert "usage" in combined, (
            f"Expected 'usage' in help output, got:\n{result.stdout}"
        )


# ---------------------------------------------------------------------------
# AC2 — Config parsing
# ---------------------------------------------------------------------------

class TestConfigParsing:
    """Config parser reads ~/.loop-team-config and returns a structured object."""

    def _get_parser(self):
        """Import the config parsing callable from runner."""
        runner = _import_runner()
        # Accept either runner.parse_config or runner.config.parse_config
        if hasattr(runner, "parse_config"):
            return runner.parse_config
        from runner import config as config_mod  # noqa: PLC0415
        return config_mod.parse_config

    def test_config_parsed_base_dir(self, sample_config):
        """AC2a: base_dir is parsed and ~ is expanded to an absolute path."""
        parse_config = self._get_parser()
        cfg = parse_config(config_path=sample_config)

        # The implementation must expose base_dir as a pathlib.Path or str
        base_dir = cfg.base_dir if hasattr(cfg, "base_dir") else cfg["base_dir"]
        base_dir = pathlib.Path(base_dir)

        assert base_dir.is_absolute(), f"base_dir should be absolute after expansion, got {base_dir}"
        assert str(base_dir) == str(REAL_BASE_DIR), (
            f"Expected {REAL_BASE_DIR}, got {base_dir}"
        )

    def test_config_parsed_provider(self, sample_config):
        """AC2b: provider is parsed as the string 'anthropic'."""
        parse_config = self._get_parser()
        cfg = parse_config(config_path=sample_config)

        provider = cfg.provider if hasattr(cfg, "provider") else cfg["provider"]
        assert provider == "anthropic"

    def test_config_parsed_default_model(self, sample_config):
        """AC2c: default_model is parsed correctly."""
        parse_config = self._get_parser()
        cfg = parse_config(config_path=sample_config)

        model = cfg.default_model if hasattr(cfg, "default_model") else cfg["default_model"]
        assert model == "claude-haiku-4-5-20251001"

    def test_config_parsed_role_override(self, sample_config):
        """AC2d: role.coder.provider and role.coder.model are parsed as role-specific overrides."""
        parse_config = self._get_parser()
        cfg = parse_config(config_path=sample_config)

        # Accept various structures: cfg.roles["coder"], cfg.role_overrides["coder"], etc.
        # The test looks for the values regardless of nested structure.
        cfg_dict = cfg if isinstance(cfg, dict) else vars(cfg) if hasattr(cfg, "__dict__") else {}

        # Walk any reasonable structure to find coder overrides
        def _find_coder_overrides(obj):
            """Recursively find coder-specific provider/model settings."""
            if isinstance(obj, dict):
                if "coder" in obj:
                    return obj["coder"]
                for v in obj.values():
                    result = _find_coder_overrides(v)
                    if result:
                        return result
            return None

        coder_cfg = _find_coder_overrides(cfg_dict)
        assert coder_cfg is not None, (
            f"Expected coder role overrides in parsed config, got:\n{cfg_dict}"
        )

        coder_provider = (
            coder_cfg.get("provider") if isinstance(coder_cfg, dict)
            else getattr(coder_cfg, "provider", None)
        )
        coder_model = (
            coder_cfg.get("model") if isinstance(coder_cfg, dict)
            else getattr(coder_cfg, "model", None)
        )

        assert coder_provider == "openai", f"Expected coder.provider='openai', got {coder_provider!r}"
        assert coder_model == "gpt-4o-mini", f"Expected coder.model='gpt-4o-mini', got {coder_model!r}"


# ---------------------------------------------------------------------------
# AC3 — Role file loading
# ---------------------------------------------------------------------------

class TestRoleLoading:
    def _get_load_role(self):
        runner = _import_runner()
        if hasattr(runner, "load_role"):
            return runner.load_role
        from runner import roles as roles_mod  # noqa: PLC0415
        return roles_mod.load_role

    def test_role_file_loads(self, real_base_dir):
        """AC3: load_role('coder', base_dir) returns a non-empty string mentioning Coder."""
        load_role = self._get_load_role()
        content = load_role("coder", real_base_dir)

        assert isinstance(content, str), "load_role must return a str"
        assert len(content) > 0, "Loaded role content must not be empty"
        assert "coder" in content.lower(), (
            "Expected 'coder' or 'Coder' in coder.md content"
        )


# ---------------------------------------------------------------------------
# AC4 — dispatch_role behaviour (mocked LLM)
# ---------------------------------------------------------------------------

class TestDispatchRole:
    """dispatch_role tests use a mocked/injected LLM so no API key is needed."""

    def _make_team(self, sample_config, fake_llm=None):
        """Build a LoopTeam pointed at the sample config, optionally injecting a fake LLM."""
        runner = _import_runner()
        LoopTeam = runner.LoopTeam  # AC7 ensures this exists

        kwargs = {"config_path": sample_config}
        if fake_llm is not None:
            kwargs["llm_factory"] = lambda *a, **kw: fake_llm
        return LoopTeam(**kwargs)

    def test_dispatch_role_returns_string(self, sample_config, monkeypatch):
        """AC4a: dispatch_role returns a str when LLM is mocked."""
        fake_llm = MagicMock(return_value="This is the coder's response.")

        team = self._make_team(sample_config, fake_llm=fake_llm)
        result = team.dispatch_role("coder", "Write a hello-world function.")

        assert isinstance(result, str), f"Expected str, got {type(result)}"
        assert len(result) > 0, "dispatch_role must return a non-empty string"

    def test_dispatch_role_uses_role_content(self, sample_config, monkeypatch):
        """AC4b: The prompt passed to the LLM contains the role file content.

        We verify this by inspecting what the fake LLM was called with.
        The role file content (roles/coder.md) includes 'Role: Coder' so we
        check for 'coder' (case-insensitive) in the captured prompt.
        """
        captured_prompts = []

        def capturing_llm(prompt):
            captured_prompts.append(prompt)
            return "response from coder"

        team = self._make_team(sample_config, fake_llm=capturing_llm)
        team.dispatch_role("coder", "Implement fibonacci.")

        assert len(captured_prompts) >= 1, "LLM was never called"
        combined_prompt = " ".join(captured_prompts)
        assert "coder" in combined_prompt.lower(), (
            f"Expected role content ('coder') in LLM prompt, got:\n{combined_prompt[:500]}"
        )


# ---------------------------------------------------------------------------
# AC5 — Provider routing: anthropic
# ---------------------------------------------------------------------------

class TestProviderRoutingAnthropic:
    def test_provider_routing_anthropic(self, sample_config, monkeypatch):
        """AC5: When provider=anthropic, anthropic_llm factory is called, not openai_llm."""
        # Ensure the real factories aren't called (no keys needed)
        mock_anthropic_llm = MagicMock(return_value=MagicMock(return_value="anthropic response"))
        mock_openai_llm = MagicMock(return_value=MagicMock(return_value="openai response"))

        # Patch at the optimize.llm level; the runner imports from there
        with patch("optimize.llm.anthropic_llm", mock_anthropic_llm), \
             patch("optimize.llm.openai_llm", mock_openai_llm):
            _reload_runner()
            runner = sys.modules[RUNNER_PACKAGE]
            LoopTeam = runner.LoopTeam

            # Coder has a per-role openai override; use "researcher" which has no override
            # so it falls through to the default provider (anthropic)
            team = LoopTeam(config_path=sample_config)
            team.dispatch_role("researcher", "Summarize the internet.")

        mock_anthropic_llm.assert_called(), "anthropic_llm factory was not called for default-provider role"
        mock_openai_llm.assert_not_called_for_researcher = True  # informational
        # Key assertion: openai_llm was NOT called for "researcher"
        # (it may have been called for the coder override in a different dispatch, but not here)
        for c in mock_openai_llm.call_args_list:
            # The only call to openai_llm should be for the coder role, not researcher
            # Since we only dispatched "researcher", openai_llm must not have been called at all
            pass
        assert mock_openai_llm.call_count == 0, (
            "openai_llm was called when dispatching 'researcher' (default provider=anthropic)"
        )


# ---------------------------------------------------------------------------
# AC6 — Per-role provider override
# ---------------------------------------------------------------------------

class TestPerRoleOverride:
    def test_per_role_override(self, sample_config, monkeypatch):
        """AC6: Dispatching 'coder' calls openai_llm when role.coder.provider=openai."""
        mock_anthropic_llm = MagicMock(return_value=MagicMock(return_value="anthropic response"))
        mock_openai_llm = MagicMock(return_value=MagicMock(return_value="openai response"))

        with patch("optimize.llm.anthropic_llm", mock_anthropic_llm), \
             patch("optimize.llm.openai_llm", mock_openai_llm):
            _reload_runner()
            runner = sys.modules[RUNNER_PACKAGE]
            LoopTeam = runner.LoopTeam

            team = LoopTeam(config_path=sample_config)
            team.dispatch_role("coder", "Write a bubble sort.")

        assert mock_openai_llm.call_count >= 1, (
            "openai_llm factory was not called when dispatching 'coder' (role.coder.provider=openai)"
        )
        assert mock_anthropic_llm.call_count == 0, (
            "anthropic_llm was incorrectly called when dispatching 'coder' (override should route to openai)"
        )


# ---------------------------------------------------------------------------
# AC7 — LoopTeam importable and is a class
# ---------------------------------------------------------------------------

class TestLoopTeamImportable:
    def test_loop_team_importable(self):
        """AC7: `from runner import LoopTeam` succeeds and LoopTeam is a class."""
        from runner import LoopTeam  # noqa: PLC0415
        assert isinstance(LoopTeam, type), (
            f"LoopTeam must be a class (type), got {type(LoopTeam)}"
        )


# ---------------------------------------------------------------------------
# AC8 — call_with_retry is in the dispatch chain (structural test)
# ---------------------------------------------------------------------------

class TestCallWithRetryInChain:
    def test_call_with_retry_in_chain(self, sample_config):
        """AC8: Patching optimize.llm.call_with_retry and dispatching a role
        must result in call_with_retry being invoked — i.e., the runner does not
        bypass it by calling the SDK directly.

        Implementation note: this test patches at the module-attribute level
        (optimize.llm.call_with_retry) so the runner's imported reference sees
        the patch only if the runner accesses it via the module (not a closed-over
        local).  If the test fails with call_count==0, it means the implementation
        cached call_with_retry at import time — the Coder must access it via
        `optimize.llm.call_with_retry(...)` or equivalent.
        """
        call_with_retry_mock = MagicMock(return_value="mocked LLM result")

        # We also need the LLM factory to return something without hitting the API.
        # Patch both the factory and call_with_retry; call_with_retry is what we assert.
        fake_client_fn = MagicMock(return_value="inner call result")
        fake_llm_callable = MagicMock(return_value="llm output")

        with patch("optimize.llm.call_with_retry", call_with_retry_mock), \
             patch("optimize.llm.anthropic_llm", return_value=fake_llm_callable), \
             patch("optimize.llm.openai_llm", return_value=fake_llm_callable):
            _reload_runner()
            runner = sys.modules[RUNNER_PACKAGE]
            LoopTeam = runner.LoopTeam

            team = LoopTeam(config_path=sample_config)
            # Use a role that maps to the default provider (anthropic) so the
            # anthropic_llm path is exercised (which calls call_with_retry internally).
            team.dispatch_role("researcher", "What is the meaning of life?")

        assert call_with_retry_mock.call_count >= 1, (
            "call_with_retry was never called during dispatch_role. "
            "The runner must route through optimize.llm.call_with_retry, not bypass it."
        )


# ---------------------------------------------------------------------------
# AC-ERR1 — Missing API key raises a clear error
# ---------------------------------------------------------------------------

class TestMissingApiKeyError:
    def test_missing_api_key_error(self, sample_config, monkeypatch):
        """AC-ERR1: When ANTHROPIC_API_KEY is not set, dispatch_role raises a
        RuntimeError (or subclass) whose message mentions the API key.

        This tests the real error path: no mock of anthropic_llm itself — we
        remove the env var and let the runner's key-check fire.
        """
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        _reload_runner()
        runner = sys.modules[RUNNER_PACKAGE]
        LoopTeam = runner.LoopTeam

        # Config says default provider=anthropic, so researcher (no override) hits anthropic path
        team = LoopTeam(config_path=sample_config)

        with pytest.raises(Exception) as exc_info:
            team.dispatch_role("researcher", "test context")

        err_msg = str(exc_info.value).lower()
        # Must mention the key in some form — not a bare AttributeError
        assert any(kw in err_msg for kw in ("api_key", "api key", "anthropic_api_key", "key")), (
            f"Error message should mention the API key, got: {exc_info.value!r}"
        )
        # Must NOT be a bare AttributeError or KeyError (those are implementation bugs)
        assert not isinstance(exc_info.value, (AttributeError, KeyError)), (
            f"Exception must not be AttributeError or KeyError, got {type(exc_info.value)}"
        )


# ---------------------------------------------------------------------------
# AC-ERR2 — Missing role file raises a clear error naming the file
# ---------------------------------------------------------------------------

class TestMissingRoleFileError:
    def test_missing_role_file_error(self, sample_config):
        """AC-ERR2: Dispatching a non-existent role name raises an exception
        whose message names the missing file (e.g. 'roles/nonexistent_role.md').
        """
        # Use a fake LLM so we isolate the error to role-file loading
        fake_llm = MagicMock(return_value="should not be reached")

        _reload_runner()
        runner = sys.modules[RUNNER_PACKAGE]
        LoopTeam = runner.LoopTeam

        team = LoopTeam(config_path=sample_config, llm_factory=lambda *a, **kw: fake_llm)

        with pytest.raises(Exception) as exc_info:
            team.dispatch_role("nonexistent_role_xyz", "some context")

        err_msg = str(exc_info.value).lower()
        assert "nonexistent_role_xyz" in err_msg or "nonexistent_role_xyz.md" in err_msg, (
            f"Error message should name the missing role file, got: {exc_info.value!r}"
        )


# ---------------------------------------------------------------------------
# AC-INT — Full loop cycle: write → verify → fix
# ---------------------------------------------------------------------------

class TestLoopCycle:
    """Integration test: LoopTeam runs a write→verify→fix loop.

    The mocked LLM returns 'passed: false' on the first Verifier call and
    'passed: true' on the second, forcing at least one retry iteration.

    Design resolution: LoopTeam.run(brief) orchestrates the loop, calling
    dispatch_role("coder", ...) then dispatch_role("verifier", ...) then
    optionally dispatch_role("coder", ...) again on failure. We test the
    abstract run() method, which returns a dict/object with at least:
      - result.success == True
      - result.iterations >= 2  (or equivalent attribute name)

    If the implementation uses a different return type, we also accept a
    plain str return where the test checks that the loop ran multiple times
    by counting LLM calls.
    """

    def test_loop_cycle_write_verify_fix(self, sample_config):
        """AC-INT: LoopTeam.run(brief) retries when verifier returns 'passed: false',
        succeeds when verifier returns 'passed: true', and runs >= 2 iterations.
        """
        call_count = {"n": 0}

        # The LLM responder:
        #   - All coder calls → return a stub implementation
        #   - First verifier call → "passed: false\nreason: needs improvement"
        #   - Second verifier call (and beyond) → "passed: true\nreason: looks good"
        verifier_call_count = {"n": 0}

        def scripted_llm(prompt):
            prompt_lower = prompt.lower()
            call_count["n"] += 1
            if "verifier" in prompt_lower or "verify" in prompt_lower or "passed" in prompt_lower:
                verifier_call_count["n"] += 1
                if verifier_call_count["n"] == 1:
                    return "passed: false\nreason: The implementation is missing edge cases."
                else:
                    return "passed: true\nreason: All acceptance criteria met."
            # Coder / researcher / other roles
            return "def hello():\n    return 'hello world'\n"

        _reload_runner()
        runner = sys.modules[RUNNER_PACKAGE]
        LoopTeam = runner.LoopTeam

        team = LoopTeam(
            config_path=sample_config,
            llm_factory=lambda *a, **kw: scripted_llm,
        )

        brief = textwrap.dedent("""\
            # Brief: Hello World
            Write a Python function hello() that returns 'hello world'.
            ## Acceptance criteria
            - Returns the string 'hello world'
        """)

        result = team.run(brief)

        # Assert success
        if hasattr(result, "success"):
            assert result.success is True, f"Expected success=True, got {result.success}"
        elif isinstance(result, dict):
            assert result.get("success") is True, f"Expected success in result dict, got {result}"
        else:
            # Fallback: a non-exception return implies success
            assert result is not None, "run() returned None — expected a result indicating success"

        # Assert at least 2 iterations (write + fail-verify + fix)
        if hasattr(result, "iterations"):
            assert result.iterations >= 2, (
                f"Expected >= 2 iterations, got {result.iterations}"
            )
        else:
            # Verify via call counts: at least 2 LLM calls total (one coder + two verifier)
            assert call_count["n"] >= 2, (
                f"Expected >= 2 total LLM calls to confirm retry, got {call_count['n']}"
            )

        # Verify the verifier was called at least twice (once fail, once pass)
        assert verifier_call_count["n"] >= 2, (
            f"Expected verifier to be called >= 2 times, got {verifier_call_count['n']}. "
            "The loop may have stopped at the first 'passed: false' instead of retrying."
        )
