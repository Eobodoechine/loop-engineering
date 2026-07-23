# Single-writer, append-only JSONL schema: prior art + recommendation

**Date:** 2026-07-09
**Mode:** A (adjacent — schema-design prior art, not a PACE experiment; no `radar.md` entry, this is a design recommendation)
**Problem statement:** a single writer appends one JSON record per review round to a `.jsonl`
file over time. Some rounds are "partial" (a sub-task failed, some data missing). A prior attempt
supported two record shapes (a canonical wrapped shape and a flat per-item shape) in the same file
"for generality," and this produced self-contradicting validation rules. Task: find the simplest
robust schema for this exact case, grounded in the JSONL spec and real production systems.

---

## 1. The JSON Lines spec itself: silent on schema, but the ecosystem's own best-practices layer is explicit

[jsonlines.org](https://jsonlines.org/) is the closest thing to a canonical spec. I fetched it
directly. It defines only the *transport* format — UTF-8, `\n`-separated, one JSON value per line,
no embedded raw newlines, `.jsonl` extension, `gzip`/`bzip2` companions — and says nothing about
whether records in a file must share a shape. That silence is a gap third-party conformance guides
fill in explicitly. [jsonlkit.com/jsonl-specification](https://jsonlkit.com/jsonl-specification),
fetched directly, states it as a hard rule in its "Conformance checklist for producers":

> "Same record shape every line."

and on mixed shapes:

> "Mixed types across lines. Valid per the spec. *Almost no consumer expects this* — strict tools
> will reject it, ML pipelines will produce wrong results. Stick to one shape per file."

This is exactly the failure mode described in the prompt: supporting two shapes is *technically*
legal JSONL (each line is independently valid JSON), but it breaks every consumer that assumes a
stable shape — which is why it produced self-contradicting validation rules rather than a parse
error. The fix is not a cleverer validator; it's "don't do that."

## 2. Real single-writer, append-only production logs: one canonical envelope, optional fields via omission

I used `gh search code` to pull real, in-production `.jsonl` files matching this exact pattern
(single writer, one record per unit-of-work, append-over-time, some optional metadata). All of the
following were opened and confirmed, not inferred from search snippets:

- **[character-ai/larch — `review-findings-full.jsonl`](https://github.com/character-ai/larch/blob/main/larch-logs/implement/9C7CDB30-2B1E-45E4-B7EB-77EDC4557CB3/review-findings-full.jsonl)**
  — this is closest analog I found to the exact use case: a code-review pipeline's per-finding
  log. I fetched and parsed all 49 lines with a script:
  ```
  total lines: 49
  distinct key-sets: 1
  ('category', 'id', 'issue_number', 'outcome', 'phase', 'prose_body', 'reviewer_slots', 'round_num', 'schema_version')
  ```
  Every single line — across 49 independent review findings appended over time — has the **exact
  same key set**, including a `"schema_version": "2"` field and a `"round_num"` field. One flat
  shape, no wrapper/flat variant split, versioned.

- **[character-ai/larch — session transcript, same run](https://github.com/character-ai/larch/blob/main/larch-logs/implement/9C7CDB30-2B1E-45E4-B7EB-77EDC4557CB3/session-transcript.jsonl)**
  — a real, concretely diagnosed bug in the *exact* failure class the prompt describes. Turn 278:
  > "The `audit-compute-counters.sh` requires a `partial_reason` field that `audit-scan-run.sh`
  > never emits."

  Turn 289:
  > "The tests distinguish two partial cases: detail `"review-findings-full.jsonl not found"` →
  > skip; other partial reasons → count. Need to check `detail` field, not `partial_reason`."

  Two different consumers were checking two *differently-named* fields for the same
  "why is this partial" concept (`partial_reason` vs `detail`), and that naming drift — not a
  parse-level ambiguity — is what broke validation. This is a direct precedent for the prompt's
  own "self-contradicting validation rules" and it confirms the fix is **field-name discipline**:
  exactly one canonical name for the partial-marker concept, emitted the same way by every writer
  path.

- **[squall321/SignalForge — `audit/stage5c_sequential.jsonl`](https://github.com/squall321/SignalForge/blob/main/audit/stage5c_sequential.jsonl)**
  — a single-writer, append-per-stage audit log with the shape `{ts, round, track, stage, action,
  result: {...}, worker: {...}, mem_after: {...}}`, where `result` carries an **optional**
  `"partial_reason"` string only when the round was incomplete (`"partial_reason": "all 3 fetched
  200 OK; current top-N items did not contain Galaxy/Samsung keywords..."`). One flat outer shape,
  a nested optional field for the partial case — no second record shape.

- **[AlignTrue/aligntrue — `data/ops-core-events.jsonl`](https://github.com/AlignTrue/aligntrue/blob/main/data/ops-core-events.jsonl)**
  — single writer, one flat envelope per event (`event_id, event_type, payload, occurred_at,
  ingested_at, correlation_id, source_ref, actor, capability_scope, schema_version`). Confirmed by
  direct read: line 1 and line 2 have **different populated payload sub-fields**
  (`end_time`/`organizer`/`location`/`attendees` present on line 1, absent on line 2) — i.e.
  optional fields are handled by **omitting the key**, not by switching to a different top-level
  record shape. `schema_version: 1` stays constant across both.

- **[pajama-studio/thriller — `assets/gep/events.jsonl`](https://github.com/pajama-studio/thriller/blob/main/assets/gep/events.jsonl)**
  — same pattern: `schema_version: "1.5.0"` constant across all lines, but a `capsule_id` field
  appears only in later events, absent in earlier ones. Confirms: **adding an optional field over
  time is not a breaking schema change and does not require a version bump** — only a change to
  what's *required* does.

- **[ianm199/omnilua — `harness/work-packets.jsonl`](https://github.com/ianm199/omnilua/blob/main/harness/work-packets.jsonl)**
  — single flat envelope (`schema_version, id, phase, role, selector, ...`) where a `"role"` field
  (`"runner"` vs `"test-fixer"`) determines *which optional fields are populated* (`runner`/
  `targets` for runner rows; `source_ranges`/`exclusive` for test-fixer rows) — but it is still
  **one JSON shape**, not two parsers. This is the right way to let record "kind" drive which
  optional fields are meaningful, without forking the shape.

- **[Rul1an/assay — `traces/ci.jsonl`](https://github.com/Rul1an/assay/blob/main/traces/ci.jsonl)**
  — `{"schema_version": 1, "type": "assay.trace", request_id, prompt, response, model, provider}`
  with an optional `"meta"` object present on only one of three lines. Same pattern again.

- **[mick-gsk/drift — `docs/decisions/fact_id_migrations.jsonl`](https://github.com/mick-gsk/drift/blob/main/docs/decisions/fact_id_migrations.jsonl)**
  — the one real counter-example I found of "two shapes in one file," and it's instructive because
  of *how carefully* it's disambiguated. Fetched directly, the file's own first line is:
  > `{"schema_version": 1, "note": "Append-only registry for drift_retrieve fact-ID migrations.
  > Each non-comment line: {"old_id": str, "new_id": str, "reason": str, "migrated_at":
  > ISO8601-date}. Introduced by ADR-091. **Lines starting with `{"schema_version"...}` or
  > `{"note"...}` are metadata and ignored by the resolver.** Never delete or reorder entries."`

  This is a fixed, single metadata **header line**, distinguished by a key (`schema_version`/
  `note`) that is *mutually exclusive* with the data-line keys (`old_id`/`new_id`/`reason`/
  `migrated_at`) — and the disambiguation rule is documented in-band. It is not general
  interleaving of two data shapes throughout the file; it's "line 1 is a header, everything else
  is one data shape." That distinction matters: it's the narrow, safe form of "more than one shape
  per file," not the open-ended one that caused the prompt's bug.

## 3. Audit-log / event-sourcing systems at the platform level: same conclusion

- **[HashiCorp Vault audit log schema](https://developer.hashicorp.com/vault/docs/audit/schema)**
  (fetched directly): every entry has a `type` field whose value is `"request"` or `"response"` —
  this is the discriminator. Fields like `response`, `error`, `auth` are *conditionally present*
  depending on `type`, but there is no second incompatible shape; `type` plus optional fields is
  the entire mechanism. There is **no explicit `format_version`/`schema_version` field** in Vault's
  audit schema — schema evolution rides on Vault's own product versioning, which the docs
  themselves flag as a gap (no inline version field is a real limitation, not a feature to copy for
  a new design).

- **Kubernetes audit log** (`audit.k8s.io` `Event` type, confirmed via
  [kubernetes/apiserver types.go](https://github.com/kubernetes/apiserver/blob/master/pkg/apis/audit/v1/types.go)
  and [the audit docs](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/)): one canonical
  `Event` struct (with the standard `TypeMeta` — `kind`/`apiVersion` — plus `auditID`, `stage`,
  `requestURI`, `verb`, `user`, `objectRef`, `responseStatus`, timestamps, `annotations`). The
  `stage` field (`RequestReceived` / `ResponseStarted` / `ResponseComplete` / `Panic`) determines
  which optional fields are populated (e.g. `responseStatus` only exists once the response stage is
  reached) — same "one shape, a status/stage field gates which optional fields are meaningful"
  pattern as Vault and `ianm199/omnilua` above.

- **OpenTelemetry Logs Data Model** (fetched directly,
  [opentelemetry.io/docs/specs/otel/logs/data-model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)):
  explicitly designed as **one canonical log record shape** with ~12 named top-level fields
  (`Timestamp`, `TraceId`, `Body`, `Resource`, `Attributes`, etc.) plus a generic `Attributes` map
  for anything less common — rather than defining multiple record variants for different kinds of
  logs. The design rationale given is that top-level named fields are reserved for what's
  "mandatory for all records or... frequently present," and everything else goes in the generic
  attribute bag — i.e. extensibility is achieved via **optional/generic fields on one shape**, not
  via alternate shapes.

- **OpenTelemetry schema versioning** (`schema_url`, confirmed via
  [opentelemetry.io/docs/specs/otel/schemas](https://opentelemetry.io/docs/specs/otel/schemas/) and
  the schema-file-format spec): each record carries a `schema_url` identifying its schema version;
  a separate schema file defines the field-rename/transform rules needed to convert between
  adjacent versions. This is the heavyweight end of "how do you evolve a required-field schema
  without breaking old records" — full transform-on-read — but the *lightweight* version of the
  same idea (a version field + "old readers ignore fields they don't know, new readers tolerate
  missing optional fields from old records") is exactly what the smaller real-world JSONL corpus
  above already does with a bare `schema_version` integer/string.

## 4. How real systems disambiguate genuinely different shapes (when they do it on purpose)

The formal, well-supported mechanism — confirmed via the
[JSON Schema / OpenAPI discriminator pattern](https://endjin.com/blog/json-schema-patterns-dotnet-polymorphism-with-discriminator-properties)
and a second confirming source on
[Java tagged unions with Jackson](https://www.speakeasy.com/blog/java-unions-jackson) — is:

> "Using const-valued properties as discriminators in a `oneOf` union implements the polymorphic
> dispatch pattern... a property called `tag`... present in each subschema with a different const
> value, producing a discriminated union." / "JSON Schema's `oneOf` keyword creates exhaustive
> discriminated unions, solving the two biggest problems with inheritance-based unions:
> invasiveness and missing-case bugs."

The rule that matters for the prompt's bug: the discriminator must be a **required, always-present
field with a fixed, mutually-exclusive value per shape** (or a mutually-exclusive `required` set
per shape) — never "infer the shape from which optional fields happen to be present." That
inference-from-presence approach is precisely what silently breaks, because the moment a partial
record legitimately omits some optional fields, it becomes indistinguishable from "this line uses
the other shape." The `mick-gsk/drift` file is the one clean real-world example of *deliberately*
supporting two shapes, and it does so by making the header line's keys **completely disjoint** from
the data line's keys, restricting it to exactly one header line, and documenting the rule in-band —
not by having two general-purpose, overlapping-field record types compete.

## 5. Recommendation for this exact case

**Use one flat, canonical record shape. Do not reintroduce a wrapped-vs-flat split.**

```jsonc
// One line per review round, appended in order. Every line has this shape.
{
  "schema_version": 1,            // int; bump ONLY on a breaking change (see below)
  "round": 4,                     // required, monotonic — the round number
  "timestamp": "2026-07-09T18:22:00Z",  // required, ISO 8601
  "status": "complete",           // required enum: "complete" | "partial" — NEVER inferred
                                   // from which optional fields are present
  // ... the round's required fields, always present ...
  "partial_reason": "sub-task X timed out"  // OPTIONAL — present iff status == "partial".
                                             // Exactly ONE canonical field name for this concept.
                                             // Every writer path that can produce a partial round
                                             // must emit this same field name — the larch bug
                                             // above (partial_reason vs detail) is what happens
                                             // when two code paths pick different names for the
                                             // same concept.
}
```

Concrete rules, each grounded above:

1. **One shape, full stop.** Every line has the same top-level key set for its *required* fields.
   (jsonlkit.com: "same record shape every line" / "stick to one shape per file"; confirmed as
   universal practice across every real single-writer JSONL log opened above — larch, SignalForge,
   AlignTrue, thriller, omnilua, assay.)
2. **Required fields are always present, no exceptions.** Optionality lives only in a small,
   named set of optional fields — never in whether a required field shows up.
3. **Optional fields are represented by key omission**, not `null` placeholders or a shape switch
   (matches every real corpus example: AlignTrue, thriller, omnilua, SignalForge all simply omit
   the key when a field doesn't apply to that record).
4. **The partial/complete distinction is an explicit, required, enum-like field** (`status`), never
   inferred from "some optional field is missing so this must be the partial variant." Vault's
   `type` field and Kubernetes' `stage` field are the production-grade version of this same
   principle — a required discriminator field, not shape-guessing.
5. **Exactly one canonical field name for the partial-completion detail.** Pick one
   (`partial_reason`, or whatever the team already calls it) and make every writer path that can
   emit a partial round use that same name. The `character-ai/larch` transcript is a live example
   of two consumers checking `partial_reason` vs `detail` for the same concept and failing —
   this is the single highest-value concrete fix for the "self-contradicting validation" the prompt
   describes.
6. **`schema_version` as a plain integer (or string), bumped only on breaking changes** — a field
   rename, a required field becoming optional or vice versa, or a required field removed. Adding a
   new *optional* field is non-breaking and does not require a bump (confirmed by `pajama-studio`'s
   `capsule_id` appearing mid-stream at constant `schema_version`, and by OpenTelemetry's own
   `schema_url`-driven migration model, which only fires transforms across schema-version
   boundaries — not for every new optional field).
7. **A validator/reader should:** require the small required-field set on every line; treat every
   other known field as optional-but-typed-if-present; and explicitly ignore unknown fields rather
   than reject the line (forward-compatible reading — this is what lets you add a new optional
   field later without breaking old readers, same posture Vault and Kubernetes take toward
   conditionally-present fields).
8. **If a genuinely different kind of record is ever needed in this file** (not indicated by the
   prompt, but worth stating for future-proofing): do it the `mick-gsk/drift` way — a single fixed
   header/metadata line with a key set *disjoint* from the data lines, documented in-band — or the
   formal JSON-Schema-discriminator way (a required `type` const per shape with mutually exclusive
   `required` sets), never an ad hoc "guess the shape from which fields are present" scheme. That
   ad hoc form is exactly what the prompt's prior attempt did, and it's exactly what broke.

**Bottom line:** the simplest robust design is *not* a cleverer two-shape validator — it's
collapsing back to the one-shape convention that essentially every real single-writer JSONL log
already uses (Vault, Kubernetes, OpenTelemetry, and every `gh`-searched production repo above),
with a required `status` field standing in for "partial or not" and a single, consistently-named
optional field carrying the partial reason.

## Sources (all opened and quoted directly, not from search snippets alone)

- [jsonlines.org](https://jsonlines.org/) — the JSON Lines spec itself
- [jsonlkit.com/jsonl-specification](https://jsonlkit.com/jsonl-specification) — "same record shape
  every line" / "stick to one shape per file"
- [HashiCorp Vault audit log entry schema](https://developer.hashicorp.com/vault/docs/audit/schema)
- [Kubernetes auditing docs](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/) and
  [kubernetes/apiserver audit v1 types.go](https://github.com/kubernetes/apiserver/blob/master/pkg/apis/audit/v1/types.go)
- [OpenTelemetry Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/)
- [OpenTelemetry Telemetry Schemas](https://opentelemetry.io/docs/specs/otel/schemas/) and
  [Schema File Format 1.0.0](https://opentelemetry.io/docs/specs/otel/schemas/file_format_v1.0.0/)
- [JSON Schema polymorphism via discriminators (endjin)](https://endjin.com/blog/json-schema-patterns-dotnet-polymorphism-with-discriminator-properties)
- [Java Unions with Jackson: Discriminated, Non-Discriminated, and Primitives (Speakeasy)](https://www.speakeasy.com/blog/java-unions-jackson)
- [character-ai/larch — `review-findings-full.jsonl`](https://github.com/character-ai/larch/blob/main/larch-logs/implement/9C7CDB30-2B1E-45E4-B7EB-77EDC4557CB3/review-findings-full.jsonl)
  (49 lines, fetched + parsed directly — 1 distinct key-set)
- [character-ai/larch — session transcript, same run](https://github.com/character-ai/larch/blob/main/larch-logs/implement/9C7CDB30-2B1E-45E4-B7EB-77EDC4557CB3/session-transcript.jsonl)
  (turns 278/289 — the `partial_reason` vs `detail` field-naming bug)
- [squall321/SignalForge — `audit/stage5c_sequential.jsonl`](https://github.com/squall321/SignalForge/blob/main/audit/stage5c_sequential.jsonl)
- [AlignTrue/aligntrue — `data/ops-core-events.jsonl`](https://github.com/AlignTrue/aligntrue/blob/main/data/ops-core-events.jsonl)
- [pajama-studio/thriller — `assets/gep/events.jsonl`](https://github.com/pajama-studio/thriller/blob/main/assets/gep/events.jsonl)
- [ianm199/omnilua — `harness/work-packets.jsonl`](https://github.com/ianm199/omnilua/blob/main/harness/work-packets.jsonl)
- [Rul1an/assay — `traces/ci.jsonl`](https://github.com/Rul1an/assay/blob/main/traces/ci.jsonl)
- [mick-gsk/drift — `docs/decisions/fact_id_migrations.jsonl`](https://github.com/mick-gsk/drift/blob/main/docs/decisions/fact_id_migrations.jsonl)
  (fetched directly — the header-line-as-metadata convention)

All GitHub file contents above were fetched via `curl`/`gh api` against the raw file (not inferred
from `gh search code` snippets), except where noted as snippet-only in the raw research log; every
citation used in the recommendation section was opened directly.
