"""otel_trace_export.py — exp2_phoenix: ADDITIVE OpenTelemetry emit shim.

This module is *additive*. It does NOT modify the trace.jsonl format, the
runner (run_trace.py), or any stdout contract. It only *reads* an existing
run's events (via run_trace.read_trace) and re-emits them as OpenTelemetry
spans so a trace can be browsed in a span UI such as Arize Phoenix.

WHY ADDITIVE: the canonical trace lives in trace.jsonl and is consumed by the
dashboard. OTel export is an optional second sink. Nothing here writes to or
changes trace.jsonl; it is pure read -> emit.

PARENT-CHILD RULE (POSITIONAL, deterministic — NOT an iteration-join):
We walk read_trace's ordered event stream once, in order. The most recent
``role_dispatch`` event opens the current parent span ``"role:<role>"``. Each
subsequent verify / verdict / plan_check / adversarial_bug / lesson event
becomes a CHILD of that currently-open parent, until the next ``role_dispatch``
opens a new parent. This is strictly positional over the stream: two
role_dispatch events that share the same ``iteration`` value still produce two
distinct parents, and a child is attached to whichever dispatch most recently
preceded it — never joined by matching iteration.

EVENTS BEFORE ANY role_dispatch — DOCUMENTED CHOICE:
Any child-type event that appears before the first role_dispatch is attached
to a synthetic root span named ``"run"``. The synthetic root is created lazily
(only if such an event exists) so a normal run that starts with a dispatch
emits no spurious root. role_dispatch events are always top-level (their own
parents); they are never nested under the synthetic root.

EXPORTER SELECTION (export_run):
  1. If ``exporter`` is passed explicitly -> use it (caller owns the choice).
  2. Else if ``otlp_endpoint`` arg OR the ``LOOP_OTLP_ENDPOINT`` env var is
     EXPLICITLY set -> instantiate the OTLP/HTTP exporter pointed at that URL.
     This is the ONLY branch that constructs the OTLP exporter or touches the
     network.
  3. Else (DEFAULT) -> InMemorySpanExporter. NO network connection is made.

GenAI semantic-convention attribute names are used on the parent span so a
Phoenix/OTel viewer recognizes model + token usage. None-valued attributes are
OMITTED entirely (set_attribute is never called with None).
"""
import os
import sys

# --- import read_trace from the runner dir the way sibling modules do ---------
# Sibling experiment modules add directories to sys.path relative to this file.
# The runner lives at <repo>/loop-team/runner/ ; this file is at
# <repo>/loop-team/experiments/exp2_phoenix/ . Go up two levels, into runner.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_LOOP_TEAM_DIR = os.path.normpath(os.path.join(_THIS_DIR, "..", ".."))
_RUNNER_DIR = os.path.join(_LOOP_TEAM_DIR, "runner")
if _RUNNER_DIR not in sys.path:
    sys.path.insert(0, _RUNNER_DIR)

from run_trace import read_trace  # noqa: E402  (do NOT duplicate read_trace)

from opentelemetry import trace as _trace_api  # noqa: E402
from opentelemetry.sdk.trace import TracerProvider  # noqa: E402
from opentelemetry.sdk.trace.export import SimpleSpanProcessor  # noqa: E402
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)
from opentelemetry.trace import Status, StatusCode  # noqa: E402


# Default localhost Phoenix OTLP/HTTP traces endpoint. Used ONLY as the *value*
# when the user opts in with no explicit URL of their own — never auto-dialed.
DEFAULT_PHOENIX_OTLP_ENDPOINT = "http://localhost:6006/v1/traces"

# The env var a user sets to opt into OTLP export.
OTLP_ENDPOINT_ENV = "LOOP_OTLP_ENDPOINT"

# Event types that become children of the currently-open parent.
_CHILD_EVENT_TYPES = frozenset(
    {"verify", "verdict", "plan_check", "adversarial_bug", "lesson"}
)

# Name of the synthetic root span for orphan (pre-dispatch) child events.
SYNTHETIC_ROOT_NAME = "run"


def _maybe_set(span, key, value):
    """set_attribute(key, value) only when value is not None.

    Per spec: when a value is None we OMIT the attribute entirely. We never
    call set_attribute with a None value.
    """
    if value is not None:
        span.set_attribute(key, value)


def _verdict_status(verdict):
    """Map a verdict string to an OTel Status, or None to leave unset.

    FAIL or FALSE-PASS -> ERROR. PASS -> OK. Anything else -> None (unset).
    Comparison is case-insensitive on the trimmed string.
    """
    if verdict is None:
        return None
    v = str(verdict).strip().upper()
    if v in ("FAIL", "FALSE-PASS", "FALSE_PASS"):
        return Status(StatusCode.ERROR)
    if v == "PASS":
        return Status(StatusCode.OK)
    return None


def spans_from_trace(events, exporter):
    """Emit OTel spans for ``events`` to ``exporter`` and return the tracer provider.

    Walks the ordered event list ONCE, applying the positional parent-child
    rule documented in the module docstring. Spans are ended deterministically
    (children end immediately; a parent ends when the next role_dispatch opens,
    and all open spans are ended at the close of the walk). After the walk the
    span processor is force-flushed so a synchronous exporter (e.g. InMemory)
    has every span available to the caller.

    Args:
        events: ordered list of event dicts (as returned by read_trace).
        exporter: a configured OTel SpanExporter to receive the spans.

    Returns:
        The TracerProvider used (handy for force_flush/shutdown in tests).
    """
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("loop.exp2_phoenix.otel_trace_export")

    # Currently-open parent span + its context, and the lazily-created synthetic
    # root for orphan children that precede the first role_dispatch.
    current_parent = None
    current_parent_ctx = None
    synthetic_root = None
    synthetic_root_ctx = None

    def _end_current_parent():
        nonlocal current_parent, current_parent_ctx
        if current_parent is not None:
            current_parent.end()
            current_parent = None
            current_parent_ctx = None

    for ev in events:
        etype = ev.get("event_type")

        if etype == "role_dispatch":
            # A new dispatch opens a brand-new parent and closes the previous
            # one. This is what makes the rule positional: a fresh parent per
            # dispatch regardless of iteration value.
            _end_current_parent()
            role = ev.get("role")
            name = "role:%s" % (role if role is not None else "unknown")
            span = tracer.start_span(name)
            # GenAI semantic-convention attributes (omit any None).
            _maybe_set(span, "gen_ai.request.model", ev.get("model"))
            _maybe_set(span, "gen_ai.usage.input_tokens", ev.get("tokens_in"))
            _maybe_set(span, "gen_ai.usage.output_tokens", ev.get("tokens_out"))
            _maybe_set(span, "loop.iteration", ev.get("iteration"))
            # Per-event cost (NOT cumulative).
            _maybe_set(span, "loop.cost_usd", ev.get("cost_usd"))
            _maybe_set(span, "loop.role", role)
            current_parent = span
            current_parent_ctx = _trace_api.set_span_in_context(span)
            continue

        if etype in _CHILD_EVENT_TYPES:
            if current_parent_ctx is not None:
                parent_ctx = current_parent_ctx
            else:
                # Orphan: appears before any role_dispatch. Attach to a lazily
                # created synthetic root span named "run".
                if synthetic_root is None:
                    synthetic_root = tracer.start_span(SYNTHETIC_ROOT_NAME)
                    synthetic_root_ctx = _trace_api.set_span_in_context(
                        synthetic_root
                    )
                parent_ctx = synthetic_root_ctx

            child = tracer.start_span(etype, context=parent_ctx)
            _maybe_set(child, "loop.outcome", ev.get("outcome"))
            _maybe_set(child, "loop.verdict", ev.get("verdict"))
            _maybe_set(child, "loop.iteration", ev.get("iteration"))
            _maybe_set(child, "loop.cost_usd", ev.get("cost_usd"))

            if etype == "verdict":
                status = _verdict_status(ev.get("verdict"))
                if status is not None:
                    child.set_status(status)

            child.end()
            continue

        # Any other (unknown / free-form) event type: emit as a child of the
        # current parent if one is open, else top-level. Keep it simple and
        # non-crashing; the canonical vocabulary is handled above.
        if current_parent_ctx is not None:
            other = tracer.start_span(etype or "event", context=current_parent_ctx)
        else:
            other = tracer.start_span(etype or "event")
        _maybe_set(other, "loop.outcome", ev.get("outcome"))
        _maybe_set(other, "loop.verdict", ev.get("verdict"))
        other.end()

    # Close any still-open spans at the end of the stream.
    _end_current_parent()
    if synthetic_root is not None:
        synthetic_root.end()

    provider.force_flush()
    return provider


def _select_exporter(exporter, otlp_endpoint):
    """Choose the exporter per the documented selection rule.

    Returns (exporter_instance, endpoint_used_or_None). The OTLP exporter is
    constructed ONLY on the explicit-endpoint branch — never by default.
    """
    # 1. Explicit exporter wins.
    if exporter is not None:
        return exporter, None

    # 2. Explicit endpoint (arg takes precedence over env). Empty string is
    #    treated as "not set" so an accidentally-empty env var doesn't dial out.
    endpoint = otlp_endpoint
    if endpoint is None:
        endpoint = os.environ.get(OTLP_ENDPOINT_ENV)
    if endpoint is not None and str(endpoint).strip() != "":
        # Import locally so the OTLP exporter class is only touched on this
        # branch (no import side effects on the no-egress default path).
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        return OTLPSpanExporter(endpoint=endpoint), endpoint

    # 3. DEFAULT: in-memory, no network.
    return InMemorySpanExporter(), None


def export_run(run_dir, exporter=None, otlp_endpoint=None):
    """Read an on-disk run trace and emit it as OTel spans.

    Reads ``<run_dir>/trace.jsonl`` via run_trace.read_trace (never re-implements
    it), selects an exporter per the documented rule, and emits spans with
    spans_from_trace.

    Args:
        run_dir: directory containing trace.jsonl.
        exporter: optional explicit SpanExporter. If given, used as-is.
        otlp_endpoint: optional explicit OTLP/HTTP endpoint URL. If given (or if
            LOOP_OTLP_ENDPOINT is set in the environment), the OTLP exporter is
            constructed and pointed there. Otherwise the in-memory exporter is
            used and NO network connection is made.

    Returns:
        dict with keys: exporter (the instance used), provider (TracerProvider),
        n_events (int), otlp_endpoint (the endpoint used, or None).
    """
    events = read_trace(run_dir)
    chosen, endpoint_used = _select_exporter(exporter, otlp_endpoint)
    provider = spans_from_trace(events, chosen)
    return {
        "exporter": chosen,
        "provider": provider,
        "n_events": len(events),
        "otlp_endpoint": endpoint_used,
    }
