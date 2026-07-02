#!/usr/bin/env python3
"""Preflight gate — probe ONCE before a batch, classify the blocker, fail FAST.

The expensive lesson: a batch of live judge calls spun for ~an hour because the
Anthropic account was OUT OF CREDITS — a PERMANENT error the runner kept treating
as retryable. A 5-second probe would have said "out of credits, add at console"
and saved the hour. This module is that probe.

`preflight(probe)` runs one minimal real call and returns a structured result:
  {ok, category, action, detail}
`category` in {ok, credits, auth, bad_model, overloaded, rate_limit, unknown}.
A PERMANENT category (credits / auth / bad_model) means STOP and surface the
`action` to the human — do NOT launch the batch. A TRANSIENT one (overloaded /
rate_limit) means the resumable sweep can ride it out.

Generalizes beyond credits: any blocker gets a category + a one-line actionable
next step, instead of a silent grind. Reuses `optimize/llm.py`'s own
transient/permanent classification so preflight and call_with_retry never disagree.
"""
import os
import sys

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
OPT_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "optimize"))
sys.path.insert(0, OPT_DIR)
import llm  # noqa: E402  -- is_transient_error, _PERMANENT_SUBSTRINGS

_CREDIT_MARKERS = ("insufficient_quota", "exceeded your current quota",
                   "check your plan and billing", "credit balance is too low",
                   "plans & billing", "purchase credits")
_AUTH_MARKERS = ("invalid_api_key", "invalid api key", "incorrect api key",
                 "authentication", "x-api-key", "permission denied",
                 "_api_key not set", "api key not set", "no api key",
                 # permanent account/policy blocks a retry can't fix
                 "suspend", "deactivated", "access revoked",
                 "account is not active", "account is inactive")
_BAD_MODEL_MARKERS = ("model not found", "does not exist", "unknown model",
                      "invalid model")

# Permanent categories: a retry/sweep can never fix these — stop and tell the human.
PERMANENT = ("credits", "auth", "bad_model")

_ACTION = {
    "ok": "proceed",
    "credits": "Account out of credits: add at console.anthropic.com -> Billing, OR "
               "run the judging via subscription sub-agents (the Agent tool) instead of "
               "the metered ANTHROPIC_API_KEY.",
    "auth": "Bad/missing API key: check ~/.config/anthropic/key (or ~/.config/openai/key).",
    "bad_model": "Model id not accepted: check the --models value against current ids.",
    "overloaded": "Transient overload (5xx/529): a resumable sweep will ride it out; "
                  "no action needed.",
    "rate_limit": "Rate limited (429): throttle or wait; transient.",
    "unknown": "Unrecognized error — read `detail` and decide.",
}


def classify_error(exc_or_msg):
    """Map a probe failure to a `category`. Permanent (credits/auth/bad_model) is
    checked FIRST so a billing 429 isn't mis-read as a retryable rate limit."""
    msg = str(exc_or_msg).lower()
    # HTTP status gives a permanent signal even when the message wording is novel:
    # 402 Payment Required -> credits; 401/403 -> auth. (429 stays for the
    # substring/transient logic below so a billing-429 still routes to credits.)
    status = getattr(exc_or_msg, "status_code", None) if isinstance(exc_or_msg, BaseException) else None
    if any(s in msg for s in _CREDIT_MARKERS) or status == 402:
        return "credits"
    if any(s in msg for s in _AUTH_MARKERS) or status in (401, 403):
        return "auth"
    if any(s in msg for s in _BAD_MODEL_MARKERS):
        return "bad_model"
    # Defer transient-vs-not to llm.py so we never disagree with call_with_retry.
    try:
        transient = llm.is_transient_error(exc_or_msg) if isinstance(exc_or_msg, BaseException) \
            else any(s in msg for s in llm._TRANSIENT_SUBSTRINGS)
    except Exception:  # noqa: BLE001
        transient = False
    if transient:
        return "rate_limit" if ("rate limit" in msg or "429" in msg) else "overloaded"
    return "unknown"


def is_permanent(category):
    return category in PERMANENT


def result(category, detail=""):
    return {"ok": category == "ok", "category": category,
            "action": _ACTION.get(category, _ACTION["unknown"]), "detail": detail}


def preflight(probe):
    """Run `probe()` once (a minimal real call). Returns {ok, category, action,
    detail}. ok=True only if the probe returned without raising. Call this BEFORE
    a long batch: if `not ok and is_permanent(category)`, STOP and surface."""
    try:
        probe()
    except Exception as e:  # noqa: BLE001 -- any failure is classified, not raised
        return result(classify_error(e), detail=str(e)[-200:])
    return result("ok")


def _live_probe(model="claude-sonnet-4-6", provider="anthropic"):
    """Return a zero-arg probe for the CLI. Building the client happens INSIDE the
    probe (not here), so a missing-key/setup failure is caught and classified by
    preflight() as `auth` instead of escaping as a traceback."""
    sys.path.insert(0, EVALS_DIR)

    def probe():
        import meta_validate as mv
        import role_runner
        judge = mv.build_live_judge(model, provider=provider, max_tokens=16)
        return judge(role_runner.build_prompt(mv.load_role("verifier.md"),
                                              {"artifact": "1BR, rent under cap, whole unit."}))
    return probe


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Preflight a live-judge endpoint")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--provider", default="anthropic")
    args = ap.parse_args()
    r = preflight(_live_probe(args.model, args.provider))
    mark = "OK" if r["ok"] else ("BLOCKED(permanent)" if is_permanent(r["category"]) else "degraded")
    print("PREFLIGHT %s [%s] %s/%s" % (mark, r["category"], args.provider, args.model))
    print("  action:", r["action"])
    if r["detail"]:
        print("  detail:", r["detail"])
    # Exit nonzero on a permanent block so a wrapper script stops instead of spinning.
    sys.exit(2 if is_permanent(r["category"]) else 0)


if __name__ == "__main__":
    main()
