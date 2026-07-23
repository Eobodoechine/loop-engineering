# exp2_phoenix — additive OpenTelemetry emit shim for Loop run traces

This experiment adds an **optional, additive** OpenTelemetry export path for an
existing Loop run trace. It reads `<run_dir>/trace.jsonl` (via the runner's
`read_trace`) and re-emits the events as OTel spans so a run can be browsed in a
span/trace UI such as **Arize Phoenix**.

It is strictly additive: it does **not** modify `trace.jsonl`, `run_trace.py`,
or any stdout contract. The canonical trace remains the JSONL file; OTel is a
second, opt-in sink.

---

## Files

- `otel_trace_export.py` — `spans_from_trace(events, exporter)` and
  `export_run(run_dir, exporter=None, otlp_endpoint=None)`.
- `test_exp2_phoenix.py` — headless acceptance tests (InMemorySpanExporter).
- `README.md` — this file.
- `RESULT.md` — what was built + headless verification outcome.

---

## Running local Phoenix on a Mac (M-series)

Pick **one** of the two forms. Phoenix listens on port `6006`; its OTLP/HTTP
trace endpoint is `http://localhost:6006/v1/traces`.

**Option A — pip (no Docker):**

```bash
pip install arize-phoenix && python3 -m phoenix.server.main serve
```

**Option B — Docker:**

```bash
docker run -p6006:6006 arizephoenix/phoenix
```

Then open the Phoenix UI at `http://localhost:6006`.

> Note: neither `arize-phoenix` nor Docker is installed in the headless CI
> environment where the tests run, which is exactly why all automated
> verification uses the in-memory exporter and makes no network connection. The
> commands above are run by **you, on your Mac**.

---

## Pointing the shim at local Phoenix

Set the endpoint env var to Phoenix's local OTLP/HTTP traces URL, then call
`export_run` on a run directory:

```bash
export LOOP_OTLP_ENDPOINT="http://localhost:6006/v1/traces"
python3 -c "from otel_trace_export import export_run; export_run('../../runs/<run_id>')"
```

You can also pass it explicitly instead of via the env var:

```python
from otel_trace_export import export_run
export_run("runs/<run_id>", otlp_endpoint="http://localhost:6006/v1/traces")
```

The OTLP exporter is constructed **only** when an endpoint is explicitly set
(arg or `LOOP_OTLP_ENDPOINT`). With no endpoint set, the shim uses an in-memory
exporter and opens **no** network connection.

---

## M1 evaluation protocol (to run on your Mac)

M1 measures whether the Phoenix waterfall view speeds up failure diagnosis
versus reading the raw trace with `grep`. It is a **wall-clock** comparison over
**K seeded failures**.

1. **Seed K failures.** Produce K run traces, each with a known injected fault
   (e.g. a `verdict=FAIL` or `verdict=FALSE-PASS` at a specific iteration, a
   missing `verify` before a `verdict`, a cost spike). Record the ground-truth
   cause for each — *do not reveal it to the diagnoser.*
2. **Arm both tools.**
   - *Waterfall:* `export_run` each seeded trace into local Phoenix
     (`LOOP_OTLP_ENDPOINT=http://localhost:6006/v1/traces`) and diagnose from
     the span waterfall UI.
   - *grep:* diagnose the same trace from `trace.jsonl` using only `grep`/text
     tools (e.g. `grep -n verdict trace.jsonl`, `grep FAIL`, manual scrolling).
3. **Measure wall-clock per case.** For each of the K seeded failures, time how
   long it takes to correctly name the root cause under each tool. Use the same
   diagnoser, counterbalance the order across cases to cancel learning effects,
   and stop the clock only on a *correct* diagnosis.
4. **Compare.** Report median and per-case wall-clock for waterfall vs grep,
   plus how many cases each tool diagnosed correctly. Adoption is human-gated:
   the waterfall path is adopted only if it is meaningfully faster (or catches
   cases grep misses) without weakening the canonical trace.

---

## Privacy note

- **Localhost only.** The default OTLP endpoint value is
  `http://localhost:6006/v1/traces` — a process on your own machine. Nothing is
  sent to a third party.
- **Zero egress by default.** If you do **not** set `LOOP_OTLP_ENDPOINT` (and do
  not pass `otlp_endpoint`), the shim uses an in-memory exporter and makes **no
  network connection at all**. The OTLP/HTTP exporter is instantiated only on
  the explicit-endpoint branch — opting in is a deliberate, local-only action.
