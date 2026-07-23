#!/usr/bin/env python3
"""Acceptance tests for exp2_phoenix (additive OTel emit shim).

Labels: [BEHAVIORAL] = exercises real behavior; [DOC] = checks a result file.

HEADLESS: arize-phoenix / Docker are NOT installed and the env has no display,
so ALL verification here uses opentelemetry's InMemorySpanExporter. We never
open a network connection.

Run:  cd loop-team && python3 -m pytest experiments/exp2_phoenix/test_exp2_phoenix.py -q
"""
import os
import sys
import tempfile

import pytest

pytest.importorskip("opentelemetry")  # optional experimental dep (exp2 is not core); see requirements-dev.txt

EXP_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, EXP_DIR)

import otel_trace_export as ote  # noqa: E402

from opentelemetry.sdk.trace.export.in_memory_span_exporter import (  # noqa: E402
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.export import ConsoleSpanExporter  # noqa: E402
from opentelemetry.trace import StatusCode  # noqa: E402

# read_trace + Tracer come from the runner via the module's sys.path setup.
from run_trace import Tracer  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _ev(event_type, **kw):
    """Build a full event dict with all read_trace fields, defaulting to None.

    Mirrors run_trace's record shape so spans_from_trace sees realistic input.
    """
    rec = {
        "ts": kw.get("ts", "2026-06-30T00:00:00"),
        "event_type": event_type,
        "role": kw.get("role"),
        "model": kw.get("model"),
        "iteration": kw.get("iteration"),
        "tokens_in": kw.get("tokens_in"),
        "tokens_out": kw.get("tokens_out"),
        "cum_tokens": kw.get("cum_tokens"),
        "cum_cost_usd": kw.get("cum_cost_usd"),
        "cost_usd": kw.get("cost_usd"),
        "outcome": kw.get("outcome"),
        "verdict": kw.get("verdict"),
        "note": kw.get("note"),
    }
    return rec


def _by_name(spans):
    out = {}
    for s in spans:
        out.setdefault(s.name, []).append(s)
    return out


# --------------------------------------------------------------------------- #
# 1 [BEHAVIORAL] POSITIONAL parent-child rule (not iteration-join).
#    Two role_dispatch events SHARE one iteration value; a verify+verdict child
#    appears AFTER the second dispatch. The children must link to the SECOND
#    (most-recent) parent — proving positional attachment, not iteration-join.
# --------------------------------------------------------------------------- #
def test_positional_parent_child_not_iteration_join():
    events = [
        _ev("role_dispatch", role="coder", model="claude-opus-4-8", iteration=7),
        _ev("verify", iteration=7, outcome="ran"),          # child of dispatch #1
        _ev("role_dispatch", role="verifier", model="gpt-4o", iteration=7),
        _ev("verify", iteration=7, outcome="ran-again"),    # child of dispatch #2
        _ev("verdict", iteration=7, verdict="PASS"),        # child of dispatch #2
    ]
    exporter = InMemorySpanExporter()
    ote.spans_from_trace(events, exporter)
    spans = exporter.get_finished_spans()

    by_name = _by_name(spans)
    # Exactly TWO parents, with the right names, despite sharing iteration=7.
    assert sorted(s.name for s in spans if s.name.startswith("role:")) == [
        "role:coder",
        "role:verifier",
    ], "positional rule must produce two distinct parents for two dispatches"

    coder = by_name["role:coder"][0]
    verifier = by_name["role:verifier"][0]
    # The two parents have distinct span_ids (sanity: not the same span).
    assert coder.context.span_id != verifier.context.span_id

    verify_spans = by_name["verify"]
    verdict_spans = by_name["verdict"]
    assert len(verify_spans) == 2 and len(verdict_spans) == 1

    # First verify is under coder (dispatch #1); it ran before dispatch #2.
    first_verify = [s for s in verify_spans if s.attributes.get("loop.outcome") == "ran"][0]
    second_verify = [s for s in verify_spans if s.attributes.get("loop.outcome") == "ran-again"][0]

    assert first_verify.parent is not None
    assert first_verify.parent.span_id == coder.context.span_id, \
        "first verify must attach to the dispatch that preceded it (coder)"

    # The verify + verdict AFTER the second dispatch must link to verifier,
    # NOT to coder — even though coder shares iteration=7. This is the crux.
    assert second_verify.parent.span_id == verifier.context.span_id, \
        "child must link to the MOST-RECENT dispatch, not iteration-matched one"
    assert verdict_spans[0].parent.span_id == verifier.context.span_id, \
        "verdict after second dispatch must link positionally to verifier"

    # And explicitly NOT the iteration-join answer:
    assert second_verify.parent.span_id != coder.context.span_id


# --------------------------------------------------------------------------- #
# 2 [BEHAVIORAL] GenAI semconv attribute NAMES + values on the parent; a None
#    cost attribute is ABSENT (not present-with-None).
# --------------------------------------------------------------------------- #
def test_genai_semconv_attrs_and_none_omitted():
    events = [
        _ev("role_dispatch", role="coder", model="claude-opus-4-8",
            iteration=3, tokens_in=120, tokens_out=45, cost_usd=0.0123),
        # A second dispatch with cost_usd=None: the loop.cost_usd attr must be
        # ABSENT on this span, not present with value None.
        _ev("role_dispatch", role="verifier", model="gpt-4o",
            iteration=3, tokens_in=10, tokens_out=None, cost_usd=None),
    ]
    exporter = InMemorySpanExporter()
    ote.spans_from_trace(events, exporter)
    by_name = _by_name(exporter.get_finished_spans())

    coder = by_name["role:coder"][0]
    attrs = dict(coder.attributes)
    assert attrs["gen_ai.request.model"] == "claude-opus-4-8"
    assert attrs["gen_ai.usage.input_tokens"] == 120
    assert attrs["gen_ai.usage.output_tokens"] == 45
    assert attrs["loop.iteration"] == 3
    assert attrs["loop.cost_usd"] == pytest.approx(0.0123)

    verifier = by_name["role:verifier"][0]
    vattrs = dict(verifier.attributes)
    # cost_usd was None -> attribute must be entirely ABSENT.
    assert "loop.cost_usd" not in vattrs, "None cost must be omitted, not set to None"
    # tokens_out None -> absent too; tokens_in present.
    assert "gen_ai.usage.output_tokens" not in vattrs
    assert vattrs["gen_ai.usage.input_tokens"] == 10
    # No attribute anywhere should have a literal None value.
    for s in exporter.get_finished_spans():
        for k, v in dict(s.attributes).items():
            assert v is not None, "attribute %s was set to None" % k


# --------------------------------------------------------------------------- #
# 3 [BEHAVIORAL] verdict status mapping: FAIL & FALSE-PASS -> ERROR; PASS -> not ERROR.
# --------------------------------------------------------------------------- #
def test_verdict_status_mapping():
    events = [
        _ev("role_dispatch", role="verifier", model="gpt-4o", iteration=1),
        _ev("verdict", verdict="FAIL"),
        _ev("verdict", verdict="FALSE-PASS"),
        _ev("verdict", verdict="PASS"),
    ]
    exporter = InMemorySpanExporter()
    ote.spans_from_trace(events, exporter)
    verdicts = {s.attributes.get("loop.verdict"): s
                for s in exporter.get_finished_spans() if s.name == "verdict"}

    assert verdicts["FAIL"].status.status_code == StatusCode.ERROR
    assert verdicts["FALSE-PASS"].status.status_code == StatusCode.ERROR
    assert verdicts["PASS"].status.status_code != StatusCode.ERROR
    assert verdicts["PASS"].status.status_code == StatusCode.OK


# --------------------------------------------------------------------------- #
# 4 [BEHAVIORAL] No-egress default (constructive). With no endpoint, the chosen
#    exporter is InMemory/Console. The OTLP class is constructed ONLY on the
#    explicit-endpoint branch — proven by patching it and asserting call count.
# --------------------------------------------------------------------------- #
def test_default_is_no_egress_inmemory(monkeypatch):
    # Ensure no ambient env opt-in.
    monkeypatch.delenv(ote.OTLP_ENDPOINT_ENV, raising=False)

    run_dir = tempfile.mkdtemp(prefix="exp2_default_")
    # write a tiny real trace so export_run has something to read
    t = Tracer(run_dir)
    t.event("role_dispatch", role="coder", model="claude-opus-4-8", iteration=0,
            tokens_in=5, tokens_out=5)

    result = ote.export_run(run_dir)
    assert isinstance(result["exporter"], (InMemorySpanExporter, ConsoleSpanExporter)), \
        "default exporter must be in-memory/console (no egress)"
    assert result["otlp_endpoint"] is None


def test_otlp_constructed_only_on_explicit_endpoint(monkeypatch):
    # Patch the OTLP class at its source module so the local import inside
    # _select_exporter resolves to our spy. Count constructions.
    import opentelemetry.exporter.otlp.proto.http.trace_exporter as otlp_mod

    calls = {"n": 0, "endpoints": []}
    real_cls = otlp_mod.OTLPSpanExporter

    class _SpyOTLP:
        def __init__(self, *args, **kwargs):
            calls["n"] += 1
            calls["endpoints"].append(kwargs.get("endpoint"))
            # do NOT call the real __init__ -> no socket/exporter setup at all.

        def export(self, spans):
            return None

        def shutdown(self):
            return None

        def force_flush(self, timeout_millis=None):
            return True

    monkeypatch.setattr(otlp_mod, "OTLPSpanExporter", _SpyOTLP)

    run_dir = tempfile.mkdtemp(prefix="exp2_otlp_")
    t = Tracer(run_dir)
    t.event("role_dispatch", role="coder", model="claude-opus-4-8", iteration=0)

    # (a) Default path: OTLP must NOT be constructed.
    monkeypatch.delenv(ote.OTLP_ENDPOINT_ENV, raising=False)
    ote.export_run(run_dir)
    assert calls["n"] == 0, "OTLP must NOT be constructed on the default branch"

    # (b) Explicit arg endpoint: OTLP constructed exactly once, pointed there.
    ote.export_run(run_dir, otlp_endpoint="http://localhost:6006/v1/traces")
    assert calls["n"] == 1
    assert calls["endpoints"][-1] == "http://localhost:6006/v1/traces"

    # (c) Explicit env endpoint: OTLP constructed again.
    monkeypatch.setenv(ote.OTLP_ENDPOINT_ENV, "http://localhost:6006/v1/traces")
    ote.export_run(run_dir)
    assert calls["n"] == 2
    assert real_cls is not None  # sanity: we actually had a class to shadow


# --------------------------------------------------------------------------- #
# 5 [BEHAVIORAL] export_run reads a REAL on-disk trace.jsonl through read_trace;
#    an event with cost_usd=None does not crash (gpt model unpriced -> None cost
#    via the real Tracer, plus a None-token event).
# --------------------------------------------------------------------------- #
def test_export_run_reads_real_trace_with_none_cost():
    run_dir = tempfile.mkdtemp(prefix="exp2_real_")
    t = Tracer(run_dir)
    # Unknown model -> Tracer writes cost_usd=None (it never guesses a price).
    t.event("role_dispatch", role="coder", model="totally-unknown-model",
            iteration=0, tokens_in=100, tokens_out=20)
    # A lesson with no model -> cost_usd None as well.
    t.event("lesson", note="gate hole found")
    # A verify/verdict to exercise children + status.
    t.event("verify", iteration=0, outcome="ran")
    t.event("verdict", iteration=0, verdict="FAIL")

    exporter = InMemorySpanExporter()
    result = ote.export_run(run_dir, exporter=exporter)
    assert result["n_events"] == 4

    spans = exporter.get_finished_spans()
    names = sorted(s.name for s in spans)
    assert "role:coder" in names
    assert "verify" in names and "verdict" in names and "lesson" in names

    coder = [s for s in spans if s.name == "role:coder"][0]
    # cost_usd was None on disk -> omitted here.
    assert "loop.cost_usd" not in dict(coder.attributes)
    # The lesson event preceded no... actually it follows the dispatch, so it is
    # a child of role:coder. Confirm it attached (positional) under the parent.
    lesson = [s for s in spans if s.name == "lesson"][0]
    assert lesson.parent is not None
    assert lesson.parent.span_id == coder.context.span_id


# --------------------------------------------------------------------------- #
# 6 [DOC] README.md documents the Phoenix command, LOOP_OTLP_ENDPOINT, the M1
#    evaluation protocol, and the privacy note.
# --------------------------------------------------------------------------- #
def test_readme_documents_everything():
    path = os.path.join(EXP_DIR, "README.md")
    assert os.path.exists(path), "README.md missing"
    md = open(path, encoding="utf-8").read()
    low = md.lower()
    # exact Mac command to run local Phoenix (one of the two accepted forms)
    assert ("python3 -m phoenix.server.main serve" in md) or \
           ("docker run -p6006:6006 arizephoenix/phoenix" in md) or \
           ("docker run -p 6006:6006 arizephoenix/phoenix" in md)
    assert "arize-phoenix" in low or "arizephoenix/phoenix" in low
    # how to set the endpoint env var to the local OTLP URL
    assert "LOOP_OTLP_ENDPOINT" in md
    assert "6006" in md and "v1/traces" in md
    # M1 evaluation protocol: waterfall vs grep, seeded failures, wall-clock
    assert "waterfall" in low and "grep" in low
    assert "seeded" in low
    assert "wall-clock" in low or "wall clock" in low
    # privacy note: localhost only, zero egress by default
    assert "localhost" in low
    assert "egress" in low


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
