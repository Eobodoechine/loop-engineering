"""run_trace.py — LoopTeam: per-run event tracing + atomic iteration checkpoints.

Stdlib only. Named run_trace (not trace) to avoid shadowing the Python stdlib
`trace` module. Two responsibilities:

  1. Tracer — append one JSON object per event to ``<run_dir>/trace.jsonl``.
     Append-mode + flush-as-you-go so a crash mid-run still leaves valid,
     line-delimited JSON on disk (every line is a complete event or absent —
     never a half-written record). Cumulative token + cost totals accumulate
     across events; cost is computed from a small per-model rate table and is
     null for an unknown model (we never guess a price).

  2. Checkpoint — ``checkpoint(run_dir, state)`` writes ``checkpoint.json`` via
     write-temp-then-rename so the on-disk checkpoint is always whole (atomic
     replace on POSIX). ``resume(run_dir)`` reads the last checkpoint back, or
     returns None when there is none / it is unreadable.

This mirrors the optimizer's "bounded, never-open-ended, crash-survivable"
posture: a run that dies between iterations resumes from its last good
checkpoint, and the trace it left behind is parseable rather than corrupt.
"""
import datetime
import json
import os
import tempfile


# Per-model USD rates, dollars per 1 token (in / out). Keep this small and
# explicit; an unknown model yields cost=null rather than a fabricated number.
# Values are list-priced per-token (i.e. per-1M price / 1_000_000).
DEFAULT_RATES = {
    # Anthropic
    "claude-opus-4-8":            {"in": 15.0 / 1e6, "out": 75.0 / 1e6},
    "claude-sonnet-4-5":          {"in": 3.0 / 1e6,  "out": 15.0 / 1e6},
    "claude-haiku-4-5":           {"in": 0.80 / 1e6, "out": 4.0 / 1e6},
    "claude-haiku-4-5-20251001":  {"in": 0.80 / 1e6, "out": 4.0 / 1e6},
    # OpenAI (cross-family judge)
    "gpt-4o":                     {"in": 2.5 / 1e6,  "out": 10.0 / 1e6},
    "gpt-4o-mini":                {"in": 0.15 / 1e6, "out": 0.60 / 1e6},
}

# Canonical event types (free-form is allowed; these document the vocabulary
# the dashboard understands).
EVENT_TYPES = (
    "role_dispatch",   # a role (coder/verifier/...) was dispatched
    "verify",          # a verification step ran
    "verdict",         # a PASS/FAIL verdict was issued
    "plan_check",      # a plan-check round (PLAN_FAIL / PLAN_PASS)
    "adversarial_bug", # an adversarial test caught a real bug
    "lesson",          # a lesson / gate-hole captured for memory
)


def _now_iso():
    """ISO-8601 timestamp with seconds resolution, local time."""
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _cost_for(model, tokens_in, tokens_out, rates):
    """USD cost for one event, or None if the model is unpriced.

    Unknown tokens (None) count as 0 toward cost so a partially-known event
    still yields a real (lower-bound) number rather than collapsing to null.
    """
    if model is None:
        return None
    rate = rates.get(model)
    if rate is None:
        return None
    ti = tokens_in or 0
    to = tokens_out or 0
    return ti * rate["in"] + to * rate["out"]


class Tracer:
    """Appends run events to ``<run_dir>/trace.jsonl``, one JSON object per line.

    Args:
        run_dir: Directory for this run. Created if missing.
        rates: Optional per-model rate table (see DEFAULT_RATES shape). When
            omitted, DEFAULT_RATES is used. Pass an empty dict to disable
            costing entirely (every cost becomes null).

    Cumulative state (cum_tokens, cum_cost_usd) lives on the instance and is
    written onto each event, so the trace is self-describing — a reader never
    has to re-sum the file to know the running totals at any point.
    """

    def __init__(self, run_dir, rates=None):
        self.run_dir = str(run_dir)
        os.makedirs(self.run_dir, exist_ok=True)
        self.path = os.path.join(self.run_dir, "trace.jsonl")
        self.rates = DEFAULT_RATES if rates is None else rates
        self.cum_tokens = 0
        self.cum_cost_usd = 0.0
        self._cost_known = True  # becomes False once an unpriced event appears

    def event(self, event_type, *, role=None, model=None, iteration=None,
              tokens_in=None, tokens_out=None, outcome=None, verdict=None,
              note=None, ts=None):
        """Append one event and return the full record dict that was written.

        Token + cost accumulation:
          - cum_tokens adds (tokens_in or 0) + (tokens_out or 0).
          - cum_cost_usd adds this event's cost. Once ANY event has an
            unpriced model, cum_cost_usd is reported as null for that event
            and all later ones (the running total is no longer trustworthy).
        """
        ev_tokens_in = tokens_in
        ev_tokens_out = tokens_out
        self.cum_tokens += (ev_tokens_in or 0) + (ev_tokens_out or 0)

        cost = _cost_for(model, ev_tokens_in, ev_tokens_out, self.rates)
        # An event that involved a model but had no priced rate poisons the
        # cumulative cost (we can't honestly total it). Events with no model
        # at all (e.g. a 'lesson') are cost-neutral and don't poison anything.
        if model is not None and cost is None:
            self._cost_known = False
        elif cost is not None:
            self.cum_cost_usd += cost

        record = {
            "ts": ts or _now_iso(),
            "event_type": event_type,
            "role": role,
            "model": model,
            "iteration": iteration,
            "tokens_in": ev_tokens_in,
            "tokens_out": ev_tokens_out,
            "cum_tokens": self.cum_tokens,
            "cum_cost_usd": round(self.cum_cost_usd, 6) if self._cost_known else None,
            "cost_usd": round(cost, 6) if cost is not None else None,
            "outcome": outcome,
            "verdict": verdict,
            "note": note,
        }
        self._append(record)
        return record

    def _append(self, record):
        """Append one record as a single line and flush+fsync immediately, so a
        crash leaves only complete lines (never a torn final record)."""
        line = json.dumps(record, ensure_ascii=False)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
            fh.flush()
            os.fsync(fh.fileno())


def read_trace(run_dir):
    """Read ``<run_dir>/trace.jsonl`` into a list of event dicts.

    Tolerant by design: skips blank lines and any trailing torn/partial line
    (a half-written record from a crash) rather than raising — the whole point
    of the append-as-you-go format is that a corrupt tail doesn't lose the
    good prefix.
    """
    path = os.path.join(str(run_dir), "trace.jsonl")
    events = []
    if not os.path.exists(path):
        return events
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                # Torn final line from a crash — stop; nothing valid follows.
                break
    return events


def checkpoint(run_dir, state):
    """Atomically write ``state`` (a JSON-serializable dict) to
    ``<run_dir>/checkpoint.json`` using write-temp-then-rename.

    os.replace() is an atomic rename on the same filesystem, so a reader never
    sees a half-written checkpoint: it sees either the previous one or the new
    one, never a torn file. We fsync the temp file before the rename so the
    bytes are durable, then fsync the directory so the rename itself survives.
    """
    run_dir = str(run_dir)
    os.makedirs(run_dir, exist_ok=True)
    final = os.path.join(run_dir, "checkpoint.json")
    payload = json.dumps(state, ensure_ascii=False, indent=2)

    fd, tmp = tempfile.mkstemp(prefix=".checkpoint-", suffix=".tmp", dir=run_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, final)  # atomic
    except Exception:
        # Don't leave a stray temp file behind on failure.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    # Best-effort: durably persist the directory entry for the rename.
    try:
        dfd = os.open(run_dir, os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except (OSError, AttributeError):
        pass  # e.g. platform without O_DIRECTORY — the file is still written

    return final


def resume(run_dir):
    """Return the last checkpoint dict for ``run_dir``, or None.

    None when there is no checkpoint or it is unreadable/corrupt — a caller
    treats None as "start fresh" rather than crashing on a bad file.
    """
    path = os.path.join(str(run_dir), "checkpoint.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
