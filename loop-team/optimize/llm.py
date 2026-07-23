#!/usr/bin/env python3
"""LLM interface for the optimizer -- one tiny callable contract so the loop
logic stays testable without a network call.

An LLM is any callable `llm(prompt: str) -> str`. Two implementations:
  - FakeLLM: deterministic, scripted -- used in tests to exercise the optimizer
    glue (verdict parsing, scoring, PACE gating, proposal writing) with no key.
  - anthropic_llm(): the real one, used when ANTHROPIC_API_KEY is set and the
    `anthropic` SDK is installed. Defaults to a cheap model for judging.

Every live call goes through `call_with_retry`: a transient infra error (429 /
500 / 503 / 529 Overloaded / timeout) gets a BOUNDED number of backoff retries,
then raises a clear error -- never an open-ended spin. (This is the Python-side
half of the verification-resilience policy; the orchestrator-side half -- how the
loop handles a flaky verifier SUBAGENT -- is in public/VERIFY_POLICY.md. Both
exist because a 529 storm once burned an hour of open-ended retries.)
"""
import os
import random
import time


# Transient = a server/infra hiccup worth a bounded retry (NOT a code/logic bug,
# which must surface immediately). Detected structurally where possible (HTTP
# status / SDK exception class), with a message-substring fallback so it works
# even without the anthropic SDK imported (keeps the wrapper unit-testable).
_TRANSIENT_STATUS = (408, 429, 500, 502, 503, 529)
_TRANSIENT_EXC_NAMES = {
    "APITimeoutError", "APIConnectionError", "InternalServerError",
    "RateLimitError", "OverloadedError", "ServiceUnavailableError",
}
_TRANSIENT_SUBSTRINGS = (
    "overloaded", "529", "rate limit", "timeout", "timed out",
    "temporarily unavailable", "503", "502", "500", "connection",
)
# PERMANENT errors that share a transient-looking status (esp. 429): a quota /
# billing / auth failure will NEVER succeed on retry, so fail FAST -- retrying it
# just wastes the budget. Found in reality: an OpenAI account with no credits
# returns 429 "You exceeded your current quota" (type insufficient_quota), which
# the status/name checks below would otherwise treat as retryable.
_PERMANENT_SUBSTRINGS = (
    "insufficient_quota", "exceeded your current quota", "check your plan and billing",
    "credit balance is too low", "plans & billing", "purchase credits",
    "invalid_api_key", "invalid api key", "incorrect api key",
)


def is_transient_error(exc):
    """True iff `exc` looks like a retryable infra hiccup rather than a real bug or
    a PERMANENT condition (quota/billing/auth). Permanent checks win over the
    status/name heuristics so a quota 429 isn't retried."""
    msg = str(exc).lower()
    if any(s in msg for s in _PERMANENT_SUBSTRINGS):
        return False
    if getattr(exc, "status_code", None) in _TRANSIENT_STATUS:
        return True
    if type(exc).__name__ in _TRANSIENT_EXC_NAMES:
        return True
    return any(s in msg for s in _TRANSIENT_SUBSTRINGS)


def call_with_retry(fn, *, attempts=3, base_delay=1.0, max_delay=30.0,
                    max_total_seconds=120.0, is_transient=is_transient_error,
                    sleep=time.sleep, now=time.monotonic, rand=random.random):
    """Call `fn()`, retrying only TRANSIENT failures with exponential backoff +
    jitter, bounded by BOTH `attempts` and `max_total_seconds`. A non-transient
    error re-raises immediately (don't retry a real bug). When the budget is
    exhausted, raise a clear RuntimeError chaining the last failure -- the caller
    gets a definite "infra unavailable" instead of an endless loop.

    `sleep`/`now`/`rand` are injectable so tests run instantly and deterministically."""
    start = now()
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001 -- classify, then retry-or-reraise
            if not is_transient(e):
                raise
            last = e
            if i == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2 ** i)) * (0.5 + rand())
            if (now() - start) + delay > max_total_seconds:
                break  # next retry would blow the wall-clock budget -> stop now
            sleep(delay)
    raise RuntimeError(
        "infra unavailable after %d attempt(s) over <=%.0fs: %r"
        % (attempts, max_total_seconds, last)) from last


class FakeLLM:
    """Scripted LLM for tests. `responder` is either a dict (prompt-substring ->
    reply), a list (returned in order), or a callable(prompt) -> reply."""

    def __init__(self, responder):
        self.responder = responder
        self.calls = []
        self._i = 0

    def __call__(self, prompt):
        self.calls.append(prompt)
        r = self.responder
        if callable(r):
            return r(prompt)
        if isinstance(r, dict):
            for key, val in r.items():
                if key in prompt:
                    return val
            return r.get("__default__", "VERDICT: FAIL")
        # list
        val = r[self._i] if self._i < len(r) else r[-1]
        self._i += 1
        return val


def anthropic_llm(model="claude-haiku-4-5-20251001", max_tokens=1024):
    """Return a real llm callable backed by the Anthropic API.

    Raises a clear error if the key or SDK is missing -- the optimizer's live run
    is gated on this; the deterministic glue is tested with FakeLLM instead.
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set -- the optimizer's live run needs an API "
            "key. The glue is tested with FakeLLM; set the key to run for real.")
    try:
        import anthropic
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError("`pip install anthropic` to run the optimizer live") from e

    # max_retries=0: our call_with_retry is the single, predictable source of
    # retry behavior (avoids the SDK's own retries multiplying with ours).
    client = anthropic.Anthropic(api_key=key, max_retries=0)

    def llm(prompt):
        def _call():
            msg = client.messages.create(
                model=model, max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}])
            return "".join(getattr(b, "text", "") for b in msg.content)
        return call_with_retry(_call)

    return llm


def openai_llm(model, max_tokens=None, temperature=None, min_interval_s=None):
    """Return a live llm callable backed by the OpenAI API -- a CROSS-FAMILY judge,
    the real fix for the model-independence weakness (all-Anthropic judges fail in
    correlated ways; a disjoint family gives true PoLL diversity).

    Same contract as anthropic_llm: goes through call_with_retry, client built with
    max_retries=0 (single retry source). max_tokens/temperature are OMITTED unless
    given -- newer OpenAI models reject `max_tokens`/non-default `temperature`, so
    omitting them keeps this compatible across whichever model id is chosen at
    runtime (the judge prompt already constrains output to one short line).

    `min_interval_s` PROACTIVELY spaces calls to respect a low RPM tier (a
    just-funded account starts at ~10 RPM; a 27-call panel hammered it). Defaults
    to the OPENAI_MIN_INTERVAL_S env var or 0 (off). This is the right fix for a
    sustained per-minute cap -- retry-after-the-fact backoff fights a window it
    can't see; proactive spacing respects the documented limit."""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY not set -- the cross-family judge needs an OpenAI key. "
            "Set it (OPENAI_API_KEY=$(cat ~/.config/openai/key)) to run live.")
    if min_interval_s is None:
        try:
            min_interval_s = float(os.environ.get("OPENAI_MIN_INTERVAL_S", "0") or 0)
        except ValueError:
            min_interval_s = 0.0
    try:
        from openai import OpenAI
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError("`pip install openai` to use the cross-family judge") from e

    client = OpenAI(api_key=key, max_retries=0)
    last = [0.0]  # monotonic time of the previous call, for proactive throttling

    def llm(prompt):
        def _call():
            if min_interval_s > 0:
                wait = min_interval_s - (time.monotonic() - last[0])
                if wait > 0:
                    time.sleep(wait)
            kwargs = {"model": model,
                      "messages": [{"role": "user", "content": prompt}]}
            if max_tokens is not None:
                kwargs["max_completion_tokens"] = max_tokens
            # A judge should be deterministic -- default to temperature=0; but newer
            # reasoning models reject a non-default temperature, so drop it on that
            # specific error (keeps the judge stable where allowed, compatible where not).
            want_temp = 0 if temperature is None else temperature
            try:
                resp = client.chat.completions.create(temperature=want_temp, **kwargs)
            except Exception as e:  # noqa: BLE001
                if "temperature" in str(e).lower():
                    resp = client.chat.completions.create(**kwargs)
                else:
                    raise
            last[0] = time.monotonic()
            return resp.choices[0].message.content or ""
        return call_with_retry(_call)

    return llm
