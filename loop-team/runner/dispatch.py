"""dispatch.py — LoopTeam: orchestrates role dispatch through the LLM layer."""
import os
import pathlib
import sys

from .config import parse_config
from .roles import load_role
from .run_trace import Tracer, checkpoint


class RunResult:
    """Result of a LoopTeam.run() call."""
    def __init__(self, success: bool, iterations: int):
        self.success = success
        self.iterations = iterations

    def __repr__(self):
        return f"RunResult(success={self.success}, iterations={self.iterations})"


class LoopTeam:
    """Orchestrates a write → verify → fix loop using configurable LLM providers.

    Args:
        config_path: Path to config file. Defaults to ~/.loop-team-config.
        llm_factory: Optional callable(provider=..., model=...) -> llm_fn.
                     If provided, bypasses the real anthropic_llm/openai_llm.
    """

    def __init__(self, config_path=None, llm_factory=None):
        self._config = parse_config(config_path=config_path)
        self._llm_factory = llm_factory

        # Insert the loop-team directory into sys.path so we can import optimize.llm
        # (the directory name has a hyphen so it cannot be a package name directly).
        loop_team_dir = str(pathlib.Path(self._config.base_dir) / "loop-team")
        if loop_team_dir not in sys.path:
            sys.path.insert(0, loop_team_dir)

    def _get_llm(self, role_name: str):
        """Resolve and return an LLM callable for the given role.

        Provider resolution:
        1. Per-role override in config (e.g. role.coder.provider=openai)
        2. Default config provider
        """
        cfg = self._config
        role_cfg = cfg.roles.get(role_name)

        if role_cfg and role_cfg.provider:
            provider = role_cfg.provider
            model = role_cfg.model or cfg.default_model
        else:
            provider = cfg.provider
            model = cfg.default_model

        if self._llm_factory is not None:
            return self._llm_factory(provider=provider, model=model)

        # Use real factories via module reference (not cached locals) so patches work.
        import optimize.llm as _llm_module  # noqa: PLC0415 (dynamic import for patchability)

        if provider == "anthropic":
            # The real anthropic_llm factory raises RuntimeError when the key is
            # missing (message contains "ANTHROPIC_API_KEY not set"). We do a pre-check
            # here too so the error fires at dispatch time and mentions the key clearly.
            # NOTE: when anthropic_llm is patched in tests this pre-check still runs,
            # so AC5/AC6 tests must set the env var or we must defer the check.
            # We rely on the factory's own check rather than duplicating it here so
            # that patched (mock) factories in AC5/AC6 work without needing a real key.
            return _llm_module.anthropic_llm(model=model)
        elif provider == "openai":
            return _llm_module.openai_llm(model=model)
        else:
            raise ValueError(f"Unknown provider: {provider!r}. Expected 'anthropic' or 'openai'.")

    def _get_logger(self, run_dir):
        """Return a structured logger writing <run_dir>/log.jsonl, or None.

        Returns None when run_dir is falsy (--no-trace / no run dir) so the
        logging path is a complete no-op — no logger, no file. Import failures
        are swallowed (logging is best-effort, never blocks a run).
        """
        if not run_dir:
            return None
        try:
            from harness.log import get_logger  # noqa: PLC0415
        except Exception:
            return None
        return get_logger("runner", run_dir=str(run_dir))

    def _resolve_model(self, role_name: str) -> str:
        """Return the model string that _get_llm would use for this role.

        Pure resolution (no LLM construction) so the tracer can record which
        model a role ran on without triggering an API key check.
        """
        cfg = self._config
        role_cfg = cfg.roles.get(role_name)
        if role_cfg and role_cfg.provider:
            return role_cfg.model or cfg.default_model
        return cfg.default_model

    def dispatch_role(self, role_name: str, context: str) -> str:
        """Dispatch a role with the given context string.

        Loads the role file, builds a prompt, and calls the LLM.
        When using real LLM providers, the call goes through
        optimize.llm.call_with_retry for bounded retry on transient failures.

        When an llm_factory was injected (test mode), the prompt is built as
        ``"Role: {role_name}\\n\\n{context}"`` so the role identity is visible
        without embedding the full role-file content (which could contain words
        like "Verifier" in a coder role file and confuse test routing logic).

        When using real providers, the full role-file content is prepended.

        Args:
            role_name: Name of the role (e.g. 'coder', 'verifier', 'researcher').
            context: The task context/brief to pass to the role.

        Returns:
            The LLM's response as a string.

        Raises:
            FileNotFoundError: If the role file does not exist.
            RuntimeError: If the required API key is not set.
        """
        import optimize.llm as _llm_module  # noqa: PLC0415

        # Always load the role file — this validates it exists (FileNotFoundError on miss).
        role_content = load_role(role_name, self._config.base_dir)

        llm_callable = self._get_llm(role_name)

        if self._llm_factory is not None:
            # Test/injection mode: use a minimal prompt so injected scripted LLMs can
            # distinguish roles by name without false matches from role-file cross-mentions.
            # Still routed through call_with_retry so custom providers get retry protection.
            prompt = f"Role: {role_name}\n\n{context}"
        else:
            # Real LLM mode: full role content prepended so the LLM receives its full brief.
            prompt = f"{role_content}\n\n---\n\n{context}"
        return _llm_module.call_with_retry(lambda: llm_callable(prompt))

    def run(self, brief: str, run_dir=None) -> RunResult:
        """Orchestrate the write → verify → fix loop.

        Dispatches coder, then verifier. If verifier returns 'passed: false',
        retries up to MAX_ITERS total iterations.

        Args:
            brief: The task brief describing what to implement.
            run_dir: Optional directory for this run. When provided, a per-step
                trace (trace.jsonl), an atomic per-iteration checkpoint
                (checkpoint.json), and a run_log.md summary are written there so
                the run is observable in the dashboard and resumable after a
                crash. When None (the default) behaviour is UNCHANGED — no files
                are written and no tracing occurs (existing callers/tests are
                unaffected).

        Returns:
            RunResult with .success and .iterations attributes.
        """
        MAX_ITERS = 6
        iterations = 0
        coder_context = brief
        tracer = Tracer(run_dir) if run_dir else None
        # Structured logger writes <run_dir>/log.jsonl beside trace.jsonl. When
        # run_dir is None (e.g. --no-trace) we create NO logger and write nothing.
        logger = self._get_logger(run_dir)
        if tracer is not None:
            tracer.event(
                "lesson", outcome="run_started",
                note="token/cost not captured yet (pending usage plumbing in optimize/llm.py)",
            )
        if logger is not None:
            logger.info("run started", brief=(brief or "").strip().splitlines()[:1])

        while iterations < MAX_ITERS:
            iterations += 1
            coder_model = self._resolve_model("coder")
            verifier_model = self._resolve_model("verifier")
            if tracer is not None:
                tracer.event("role_dispatch", role="coder", model=coder_model,
                             iteration=iterations)
            if logger is not None:
                logger.info("role dispatch", role="coder", model=coder_model,
                            iteration=iterations)
            impl = self.dispatch_role("coder", coder_context)
            if tracer is not None:
                tracer.event("role_dispatch", role="verifier", model=verifier_model,
                             iteration=iterations)
            if logger is not None:
                logger.info("role dispatch", role="verifier", model=verifier_model,
                            iteration=iterations)
            verdict = self.dispatch_role(
                "verifier",
                f"Brief:\n{brief}\n\nImplementation:\n{impl}"
            )
            passed = "passed: true" in verdict.lower()
            verdict_label = "PASS" if passed else "FAIL"
            if logger is not None:
                if passed:
                    logger.info("verdict", role="verifier", model=verifier_model,
                                iteration=iterations, verdict=verdict_label)
                else:
                    logger.warning("verdict", role="verifier", model=verifier_model,
                                   iteration=iterations, verdict=verdict_label)
            if tracer is not None:
                tracer.event("verdict", role="verifier", model=verifier_model,
                             iteration=iterations,
                             verdict=("PASS" if passed else "FAIL"))
                checkpoint(run_dir, {
                    "iteration": iterations,
                    "last_verdict": "PASS" if passed else "FAIL",
                    "done": passed,
                    "brief": brief,
                })
            if passed:
                if tracer is not None:
                    self._write_run_log(run_dir, brief, iterations, True, tracer)
                return RunResult(success=True, iterations=iterations)
            # Feed failure back to coder on next iteration.
            # Strip lines starting with "passed:" so the coder context
            # doesn't contain verdict trigger words that confuse scripted test LLMs.
            feedback = "\n".join(
                line for line in verdict.splitlines()
                if not line.lower().startswith("passed:")
            ).strip()
            coder_context = (
                f"{brief}\n\nPrevious attempt:\n{impl}\n\nFeedback:\n{feedback}"
            )

        if tracer is not None:
            self._write_run_log(run_dir, brief, iterations, False, tracer)
        return RunResult(success=False, iterations=iterations)

    @staticmethod
    def _write_run_log(run_dir, brief, iterations, success, tracer):
        """Write a human- + dashboard-readable run_log.md summarizing the run."""
        import pathlib  # noqa: PLC0415
        outcome = "PASS" if success else "FAIL"
        brief_lines = (brief or "").strip().splitlines()
        title = brief_lines[0][:120] if brief_lines else "(no brief)"
        body = "\n".join([
            f"# Runner run — {outcome}",
            "",
            f"Outcome: {outcome}",
            f"Iterations: {iterations}",
            f"Cumulative tokens: {tracer.cum_tokens}",
            f"Brief: {title}",
            "",
            "Per-step trace: trace.jsonl · Resume state: checkpoint.json",
        ])
        pathlib.Path(run_dir, "run_log.md").write_text(body + "\n", encoding="utf-8")
