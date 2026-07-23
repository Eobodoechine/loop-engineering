# exp2_phoenix — RESULT

## What was built

An **additive** OpenTelemetry emit shim that reads an existing Loop run trace
and re-emits it as OTel spans for viewing in a span UI (e.g. Arize Phoenix).
Nothing in the canonical pipeline was modified: `trace.jsonl`, `run_trace.py`,
and the stdout contract are untouched. The shim is read-only over the trace.

Files under `experiments/exp2_phoenix/`:

- **`otel_trace_export.py`**
  - `spans_from_trace(events, exporter)` — walks the ordered event stream once
    and emits spans.
  - `export_run(run_dir, exporter=None, otlp_endpoint=None)` — reads
    `<run_dir>/trace.jsonl` via the runner's `read_trace` (imported, not
    duplicated; the runner dir is added to `sys.path` the way sibling modules
    do), selects an exporter, and emits.
  - **Parent-child rule (positional, deterministic):** the most-recent
    `role_dispatch` opens parent span `role:<role>`; each subsequent
    verify/verdict/plan_check/adversarial_bug/lesson event is a CHILD of that
    open parent until the next `role_dispatch`. This is positional over the
    stream, **not** an iteration-join — two dispatches sharing one `iteration`
    still yield two distinct parents.
  - **Orphan handling (documented choice):** child-type events appearing before
    any `role_dispatch` attach to a lazily-created synthetic root span named
    `"run"`. The root is only created if such an orphan exists.
  - **Parent attributes (GenAI semconv names):** `gen_ai.request.model`,
    `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`,
    `loop.iteration`, `loop.cost_usd` (per-event `cost_usd`, NOT cumulative).
    None values are omitted entirely (`set_attribute` is never called with
    None).
  - **Child spans:** named by `event_type`; carry outcome/verdict (omit if
    None). A `verdict` of FAIL or FALSE-PASS sets `StatusCode.ERROR`; PASS sets
    `StatusCode.OK`.
  - **Exporter selection:** explicit `exporter` wins; else an explicit
    `otlp_endpoint` arg or `LOOP_OTLP_ENDPOINT` env var instantiates the
    OTLP/HTTP exporter (the OTLP class is imported and constructed **only** on
    this branch); else the default is `InMemorySpanExporter` with **no** network
    connection.

- **`test_exp2_phoenix.py`** — 7 acceptance tests (6 behavioral, 1 doc).
- **`README.md`** — Phoenix run commands (pip + Docker), `LOOP_OTLP_ENDPOINT`
  setup, the M1 evaluation protocol (waterfall vs grep over K seeded failures,
  wall-clock), and the privacy note.

## Headless verification outcome

Command run (in the headless Linux verification environment, equivalent to the
Mac command in the task):

```
cd loop-team && python3 -m pytest experiments/exp2_phoenix/test_exp2_phoenix.py -q
```

**Result: 7 passed in ~0.2s.** All verification used
`opentelemetry.sdk.trace.export.in_memory_span_exporter.InMemorySpanExporter`;
no network connection was opened. Tests covered: the positional parent-child
rule (two dispatches sharing one iteration, child links to the most-recent
parent — not iteration-matched), GenAI semconv attribute names/values with a
None cost ABSENT, verdict status mapping (FAIL/FALSE-PASS -> ERROR, PASS not
ERROR), the no-egress default (isinstance check) plus a spy proving the OTLP
class is constructed only on the explicit-endpoint branch, a real on-disk
`trace.jsonl` written by `run_trace.Tracer` with `cost_usd=None` not crashing,
and the README doc checks.

## What must be run by the user on their Mac (cannot run headless here)

- Starting **local Arize Phoenix** (pip or Docker — neither Phoenix nor Docker
  is installed in this headless, displayless environment).
- The **Phoenix UI** waterfall browsing of exported spans.
- The **M1 diagnosis-time comparison** (waterfall vs grep over K seeded
  failures, wall-clock) — this is an interactive, human-timed protocol that
  cannot be executed in CI.

## Adoption

Adoption is **human-gated**. This experiment provides the additive shim and
headless evidence that it emits correct spans with zero egress by default. It
does not adopt the Phoenix path into the loop; that decision rests with the
human after running the M1 comparison on their Mac.
