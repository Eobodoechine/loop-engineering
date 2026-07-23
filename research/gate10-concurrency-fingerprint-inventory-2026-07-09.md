# Inventory: what's already known vs. genuinely uncovered for Gate 10's 3 open problems (2026-07-09)

**Mode:** A-adjacent inventory pass (read-only; no sub-agents dispatched, all reading done
directly per the dispatch's constraint). **Task:** across every existing `research/` artifact
plus `fix_plan.md` plus the live harness source (`reconcile_gap_records.py`,
`plancheck_saturation.py`, `verify.py`, `DESIGN_CHECKLIST.md`, `orchestrator.md`), inventory
what's already known vs. not yet covered for 3 unsolved problems in the design of a
`plancheck_gate10_runner.py` mechanism + `orchestrator.md`'s plan-check dispatch protocol.
`plancheck_gate10_runner.py` itself does not exist on disk yet (confirmed via
`find . -iname "*gate10*"` — zero hits); the file being hardened is the still-in-design
successor to the existing `plancheck_saturation.py`.

Every citation below is to a file/line I opened directly this session — no citation is
reported from memory or a search snippet.

---

## PROBLEM 1 — Deterministic defect fingerprinting

### The bug, reconfirmed directly in the live code (not previously documented anywhere in `research/`)

`loop-team/harness/reconcile_gap_records.py` (444 lines), `cluster_near_duplicates()`
(lines 225–264):

```python
# line 254
if _mechanism_refs(records[i]).isdisjoint(_mechanism_refs(records[j])):
    continue
similarity = SequenceMatcher(None, texts[i], texts[j]).ratio()
```

`_mechanism_refs()` (line 136–137) is `set(_field(record, "mechanism_refs", []) or [])` —
when a record's `mechanism_refs` is absent/empty, this is `set()`. Python:
`set().isdisjoint(set())` → `True`. So whenever **either** record has an empty
`mechanism_refs` (the common case — it's an optional field lenses aren't required to
populate, and no existing dispatch prompt enforces non-empty), the `continue` fires and the
`SequenceMatcher` text-similarity check **never runs at all** — confirmed by direct
inspection, exactly as the dispatch prompt described. A sibling function,
`orthogonality_filter()` (lines 164–180, used by `needs_mechanism_trace()` at lines
187–217), has a **related but distinct** flaw: if two records both have empty `touches`
**and** empty `mechanism_refs`, it returns `INDEPENDENT` outright (both disjointness checks
are vacuously true) — meaning two records that both simply forgot to populate these
optional fields are waved through as *guaranteed unrelated*, never even reaching a
mechanism-trace. This second flaw is not named in the dispatch prompt but is the same root
cause and should be fixed alongside it. **No existing `research/` file, and no `fix_plan.md`
entry, mentions either flaw** — confirmed via `grep -rn "isdisjoint" loop-team/ fix_plan.md
research/` (only the 3 in-code hits above; zero discussion anywhere).

### What prior research already says (exact citations)

1. **`research/plan-check-reconciliation-prior-art-2026-07-02.md`** — the design doc
   `reconcile_gap_records.py`'s own docstring cites by name (confirmed: its docstring at
   lines 17–33 says *"Design: research/plan-check-reconciliation-prior-art-2026-07-02.md
   ('Reconciliation-step sketch' section...)"*, and line 64's comment says *"a concrete,
   already-tuned number from a real deployed system -- see the research doc's Candidate
   3.2"*).
   - **Candidate 3.1 (DefectDojo SARIF dedup, lines 166–181 of that doc):** confirms
     industry-standard dedup is solved via a **structured hashcode** built from concrete,
     positively-identifying fields — *"default hashcode fields: title, cwe, line, file
     path, description"* — and explicitly states *"the documentation makes no mention of
     any mechanism for detecting contradictory findings."* Relevant precedent for "what
     does a working fingerprint look like" (concrete structured fields, not free-text
     alone) but for a **different** problem (dedup, not cross-round recurrence of a
     prose-described defect).
   - **Candidate 3.2 (`calimero-network/ai-code-reviewer`, lines 183–241):** the actual
     origin of the `SequenceMatcher >= 0.85` threshold now in `reconcile_gap_records.py`.
     Critically, the **original tool's own clustering precondition is NOT the same as
     loop-team's adaptation**: ai-code-reviewer clusters on *"same file, category,
     overlapping line ranges (±5 lines), and combined title+description similarity ≥
     0.85"* — i.e. concrete, always-populated identity fields (a finding always has a
     file and line range). Loop-team's adaptation substituted an **optional, often-empty
     tag set** (`mechanism_refs`) as the gating precondition — this substitution is what
     introduced the empty-set bug; the original tool never had this failure mode because
     its gating fields aren't optional.
   - **Candidate 4.2 (NLI requirements-conflict detection, lines 298–334):** F1 22–55%,
     and — the load-bearing finding — explicitly documented to **miss compositional
     conflicts** (two things fine individually, conflicting only via a shared third
     factor). This is a same-round pairwise **contradiction** classifier, not a
     cross-round **recurrence/identity** classifier — answers "do these two disagree,"
     not "is this the same defect worded differently a second time." Directly relevant as
     a *near-miss* prior art, not a solution.
2. **`loop-team/DESIGN_CHECKLIST.md` gate 10 (lines 104–206, read in full):** defines
   "recurring signature" for `[BINDING]` findings only as a **prose category description**
   (*"the same binding signature (bare/undeclared identifiers, missing
   imports/exports/directives)"*, line 187) — never formalized as an algorithm or exact-
   match rule. The gate's own text (lines 196–206) explicitly worries about **surface
   resemblance causing false recurrence** ("a tagger relying on surface resemblance alone
   ... could plausibly mistag" a genuinely-new finding as the old recurring one) — i.e.
   the design doc already names the exact risk a naive fingerprint for
   LOGIC/CONCURRENCY/SECURITY would create, without solving it.
3. **`loop-team/harness/plancheck_saturation.py` (340 lines, read in full):** the ONE
   already-shipped precedent for a "signature" field, but scoped to `[BINDING]` only. Its
   docstring's canonical record shape (lines 12–13): `{"tag": "BINDING", "signature":
   "..."}`. `evaluate_records()` compares signatures for the last-3-round window via **exact
   string equality after `str()` coercion** (`unique_signatures = sorted(set(str(signature)
   for signature in signatures))`) — i.e. it assumes the tagging LLM already authored an
   identical string across rounds, with zero normalization/matching logic of its own. There
   is **no equivalent field or convention for LOGIC/CONCURRENCY/SECURITY tags** anywhere in
   this file — confirmed by reading the full 340 lines; `NON_BINDING_TAGS` records are only
   ever checked for *presence* in the 3-round window (which disqualifies the stop, per
   `evaluate_records`'s `non_binding` check), never fingerprinted for their own recurrence.
4. **`loop-team/harness/verify.py`'s shipped compiler-error fingerprint (lines 437–509,
   read in full) — the closest REAL, WORKING fingerprint design in this codebase**, and a
   graduation of `research/compiler-feedback-loop-gate-design-2026-07-08.md`'s proposal
   (that design doc, lines 51–55, specified *"a stable per-error fingerprint (file + TS
   error code + normalized message ... explicitly not raw file:line)"*; the shipped
   version in `verify.py` simplified further). `_parse_tsc_errors()` (lines 437–454):
   > *"Fingerprint shape is (relative_file_path, ts_error_code) ONLY -- deliberately
   > excludes line/column and message text: line numbers shift as unrelated code in the
   > same file changes across micro-steps, so a line-sensitive fingerprint would
   > manufacture a false 'new' error on every step even when the underlying defect is
   > unchanged."*
   Persisted via `_load_type_check_baseline()` (lines 457–509) as a self-bootstrapping,
   plain-JSON list of `[file, code]` pairs at `.loop_type_check_baseline.json` (a
   single-snapshot file, not append-only). **This is a real, deployed, stable fingerprint
   that collapses reliably across differently-worded surface output** — but it works
   *only* because `tsc` emits a **closed, discrete, machine-generated error-code
   vocabulary** (`TS2307`, `TS2352`, ...). This is the crux transfer-condition gap for
   Problem 1: Gate 10's LOGIC/CONCURRENCY/SECURITY findings have **no equivalent closed
   vocabulary** — they are free English prose independently authored by different LLM
   reviewers each round, with no compiler-equivalent discrete code to key a tuple on.
5. **`research/defect-taxonomy-standards-prior-art-2026-07-02.md` (lines 1–30):** IBM's
   Orthogonal Defect Classification (ODC) is real, 30+ years field-validated (*"Reaches
   around 3000 IBM engineers worldwide ('99)... Motorola, Telcordia, Nortel, Lucent...
   are also users"*), and uses the word **"signature"** in its own primary source (*"ODC...
   enables in-process feedback... by extracting signatures on the development process from
   defects"*) — but ODC's "signature" is a **categorical classification vector** (defect
   type × trigger × impact, etc.), not a literal deduplication string. Real, mature, but
   answers a different question ("what class of defect is this," not "does this
   free-text description collapse to the same string as an earlier one").
6. **`research/plancheck-nonbinding-saturation-2026-07-09.md`** (the sibling
   stopping-criterion research): its top candidate (capture-recapture / Chapman estimator)
   explicitly **depends on** a working overlap/clustering computation between lenses'
   findings — quoting its own text: *"this project is one small step away from having the
   raw ingredient... (lens A's found-count, lens B's found-count, their overlap)"* — and
   names `reconcile_gap_records.py`'s clustering as that ingredient's source. **This is a
   previously-unstated cross-document risk worth flagging explicitly**: the saturation
   research's own top candidate is built on the assumption that `cluster_near_duplicates()`
   correctly detects overlap, which the confirmed bug above undermines whenever
   `mechanism_refs` is empty (the common case).

### Real external prior art already identified (do not re-research — see the docs above for full detail)

- DefectDojo (OWASP, SARIF hashcode dedup) — `research/plan-check-reconciliation-prior-art-2026-07-02.md` Candidate 3.1.
- `calimero-network/ai-code-reviewer` (`_cluster_raw_findings`, `SequenceMatcher>=0.85`) — Candidate 3.2, same doc.
- NLI requirements-conflict detection (arXiv 2405.05135) — Candidate 4.2, same doc.
- IBM Orthogonal Defect Classification (ODC) — `research/defect-taxonomy-standards-prior-art-2026-07-02.md`.
- SAT/SMT unsatisfiable-core analysis — Candidate 4.1 (same prior-art doc) — flagged there as domain-mismatched (needs pre-formalized clauses, not English text) but conceptually useful for "localize which assumption conflicts."

### What is NOT yet covered — the genuine gap for the next research phase

- **No research anywhere proposes a concrete, testable scheme for a stable signature over
  FREE-TEXT LLM-authored LOGIC/CONCURRENCY/SECURITY findings that collapses across
  differently-worded rounds.** Every fingerprint design found in this repo (the tsc
  `(file, code)` tuple) or in prior art (DefectDojo's hashcode, ai-code-reviewer's
  file+line+similarity gate) depends on a structured, positionally-anchored, or
  closed-vocabulary field that simply does not exist for prose-described logic bugs.
- **No research has evaluated whether an LLM call itself, prompted specifically to emit a
  canonical/normalized slug at tagging time** (the same "tag-at-write-time" convention
  `DESIGN_CHECKLIST.md` gate 9 already uses for `[SECURITY-ORACLE]`), would collapse
  consistently round-over-round for the SAME underlying defect worded differently by
  different reviewer personas — this is untested, not just undesigned.
- **The `reconcile_gap_records.py` bug itself has never been flagged, diagnosed, or
  proposed-fixed in any `research/` artifact** — it is a genuinely fresh finding from this
  inventory pass, not a rediscovery.
- **No research has audited whether fixing the empty-`mechanism_refs` gate (e.g., falling
  back to always running `SequenceMatcher` regardless of `mechanism_refs` overlap, or
  requiring `mechanism_refs`/`touches` to be non-empty at write time) would itself be
  sufficient**, or whether `SequenceMatcher`'s character-level similarity is even a sound
  metric for LLM-paraphrased prose (it was tuned by ai-code-reviewer for code-review
  finding titles/descriptions, not necessarily representative of loop-team's own lens
  wording distributions) — no A/B or backtest of this specific question exists.
- **No design exists for what fields a general (non-BINDING) `signature` should even
  contain** — e.g., should it be a hash of `(gap_type, touches, mechanism_refs)`, an
  LLM-authored slug, or something else — this is downstream of, and blocked on, resolving
  the above.

---

## PROBLEM 2 — Async completion barrier for N parallel lens dispatches

### What prior research already says (exact citations)

1. **`fix_plan.md` H-GUARD-3 / H-LT7 / H-GUARD-MICROSTEP / H-GUARD-SUBAGENT-2** (lines
   1231–1256, close-out section lines 1360–1374, `guard-hooks-async build`): this project
   ALREADY built and shipped a cross-turn, structural completion-signal mechanism — but for
   tracking **one** async event (a plan-check PLAN_PASS), not for counting N-of-N. Root
   cause (quoted, line 1241): *"the real holes were the credit SEMANTICS: consume-all-on-
   one-turn + one-credit-for-N-steps + order-sensitivity -- replaced by a non-consuming
   24h-TTL read + order-insensitive turn scan."* Mechanism: `SubagentStop` hook
   (`hooks/subagent_stop_gate.py`) writes a marker file per completion event, read by
   `loop_stop_guard.py` before allowing the next action — i.e., a working precedent for
   "verify-before-proceed" for a SINGLE tracked signal, already hardened against the exact
   "recorded in a log ≠ enforced" failure mode Problem 2 describes.
2. **`research/coder-detection-structural-signal-subagentstop-2026-07-08.md`** (read in
   full, §1–2): confirms, via live `~/.loop-gate/subagent_gate_debug.jsonl` evidence and
   direct filesystem inspection, that `agent_id`/`agent_type` **are** populated on every
   `SubagentStop` firing in this project's actual runtime (build 1.0.117), and that a
   per-agent transcript file (`subagents/agent-<id>.jsonl` + `.meta.json`, carrying
   `agentType`/`toolUseId`) exists on disk for every dispatched sub-agent — i.e., the
   **structural identity signal needed to distinguish N distinct lens completions from
   each other already exists and is verified real**, contra the now-outdated
   `anthropics/claude-code#7881` ("SubagentStop hook cannot identify which specific
   subagent finished") which the doc confirms is fixed in this runtime. Also explicitly
   discloses, as an **unresolved architectural gap**: "backgrounded/still-running
   sub-agents" — no mechanism found or designed anywhere for detecting a dispatch that
   never fires `SubagentStop` at all (a genuine hang, not an error).
3. **`research/subagent-commit-violation-signaling-2026-07-03.md`** (read in full) — the
   single most directly on-point piece of prior art for the N-of-N counting requirement.
   Documents, with primary-source citations: official docs confirm `SubagentStop`'s
   `agent_id` field is *"Present only when the hook fires inside a subagent call"* (no
   parent-context bridge exists — `additionalContext` only reaches the sub-agent's own
   conversation, never the parent's); GitHub issue **#5812** ("Allow Hooks to Bridge
   Context Between Sub-Agents and Parent Agents") is closed **NOT PLANNED** by Anthropic,
   whose own "Alternatives Considered" section names *"writing changes to temporary state
   files"* as the accepted workaround — independent, if indirect, validation of this
   project's flag-file-bridge pattern; GitHub issue **#7881** is confirmed fixed in this
   runtime (cross-referenced with finding 2 above). Critically, the doc's own "Reliability
   / race risk" analysis (quoted): *"if TWO sub-agents in the same session both raw-commit
   a scope file, and Oga's Stop hook only checks 'any fresh flag exists' rather than
   resolving per-agent, Oga could clear the block after addressing only one violation
   while a second (different SHA, different agent_id) flag sits unaddressed. Mitigation:
   don't just check flag EXISTENCE -- read and surface the CONTENT of every fresh matching
   flag."* This is an **already-articulated, though not yet built, design principle
   directly transferable to Problem 2**: glob for `~/.loop-gate/<session_id>_*.<ext>`,
   enumerate distinct `agent_id`s present, and structurally compare that count/set against
   the expected N — rather than a bare existence check.
4. **`loop-team/orchestrator.md` lines 51–66** (plan-check dispatch protocol, read
   directly): specifies the conditional trigger for dispatching N parallel lenses and
   hands reconciliation to `reconcile_gap_records.py`, but **nowhere specifies how Oga
   confirms N results (not fewer) were actually collected** before calling reconcile — the
   dispatch protocol describes what to do with the results once you have them, not how to
   verify you have all of them.
5. **`loop-team/orchestrator.md` lines 583–613** (`robustLensDispatch` JS wrapper for the
   `Workflow` tool, read directly, filed as `H-PLANCHECK-STRUCTUREDOUTPUT-FLAKY-1`): an
   **already-shipped, bounded-retry + explicit-fallback mechanism**, but scoped to a
   SINGLE lens's own retry loop, not to the outer question of whether all N lenses'
   wrapper calls were even invoked/awaited:
   ```js
   async function robustLensDispatch(schemaPrompt, freeTextPrompt, schema, opts) {
     try { return await agent(schemaPrompt, { ...opts, schema }) }
     catch (e) {
       const text = await agent(freeTextPrompt, opts)
       const gateMatch = text.match(/LOOP_GATE:\s*(PLAN_PASS|PLAN_FAIL)/i)
       return { lens: opts.label, reasoning: text, gaps: [],
                loop_gate: gateMatch ? gateMatch[1].toUpperCase() : 'PLAN_FAIL' }
     }
   }
   ```
   Note the "default to FAIL, never silently PASS an unparseable fallback" discipline —
   directly reusable design principle for Problem 2's own partial-completion fallback
   state.
6. **`loop-team/orchestrator.md` line 579 (`H-WF-DELEGATE-1`, read directly):** documents
   a REAL, already-occurred incident of exactly the failure class Problem 2 exists to
   prevent — an async, fire-and-forget dispatch (a lens's own internal helper sub-agent)
   launched in the background and never awaited or consumed: *"finished its own reasoning
   and returned its final answer WITHOUT waiting for or stopping that child -- orphaning
   it. The child kept running... for over an hour... This compounds across every
   parallel-lens round (3 rounds × 4 lenses = up to 12 potential orphans)."* Concrete,
   dated, motivating precedent for why a structural (not instructional) barrier matters
   here specifically.
7. **`research/loop-team-process-retrospective-review-2026-07-02.md`** (lines 440–498,
   634–653, read directly) — the origin document for the N-parallel-lens design
   (`proposal #2`), on record a full week before any of the above hardening existed:
   *"The structural gap this dossier flagged for proposal #2 -- no reconciliation
   mechanism for multiple simultaneous LOOP_GATE/gap records from parallel lenses -- is
   STILL not built... exactly the 'instructional-only guarantee'... without a structural
   check that reconciliation actually happened correctly every time."* And, in the
   required transfer-condition section (lines 646–651): *"If proposal #2 were adopted
   purely instructionally ('dispatch N Verifiers, then Oga synthesizes'), the
   reconciliation guarantee would be enforced ONLY by Oga's own judgment in the moment,
   with no structural check... this is exactly the kind of instructional-only guarantee
   that can fail silently."* This is the exact framing Problem 2 restates — already
   diagnosed, still not fixed.

### Real external prior art already identified

- Claude Code CLI hooks reference (`code.claude.com/docs/en/hooks`) — `SubagentStop` schema, `agent_id`/`agent_type` fields — cited in both subagent-signaling docs above.
- `anthropics/claude-code` GitHub issues **#5812** (parent/sub-agent context bridge, closed not-planned) and **#7881** (SubagentStop can't distinguish concurrent sub-agents, confirmed fixed in this runtime) — both fetched directly per `research/subagent-commit-violation-signaling-2026-07-03.md`.
- TDD Guard (`nizos/tdd-guard`) and claudefa.st's `.claude/incomplete-task` marker-file pattern — cited in the same doc as the "sanctioned cross-turn state" pattern this project already follows.

### What is NOT yet covered — the genuine gap for the next research phase

- **Zero hits anywhere in `research/` for any formal distributed-systems completion-barrier
  primitive** (`CountDownLatch`, `WaitGroup`, `threading.Barrier`, `quorum`,
  `as_completed`/`Promise.allSettled`) — confirmed via `grep -rliE` across the whole
  `research/` directory. This class of prior art has simply never been looked at for this
  project.
- **No design exists anywhere for an explicit N-count verify-before-proceed step** — e.g.,
  "collect all N dispatch results, assert `len(results) == N`, and treat any missing/timed-
  out entry as a named `PARTIAL_COMPLETION` state before calling
  `reconcile_gap_records.py`." The closest existing mechanism (`robustLensDispatch`) only
  guarantees a single lens's OWN call eventually resolves to *something* (real result or a
  defaulted PLAN_FAIL) — it does not verify that the outer orchestration actually invoked
  and awaited all N wrapper calls in the first place.
- **No research confirms the `Workflow` tool's actual concurrency semantics** — whether N
  `agent()` calls issued in a loop/array genuinely execute concurrently (true parallel
  dispatch, requiring an explicit `Promise.all`/`Promise.allSettled`-style join) or execute
  sequentially by default. This is a foundational, unverified fact that any barrier design
  needs before it can be built — not established anywhere in this repo's research.
- **No design exists for what Oga should structurally DO once a partial-completion state
  is confirmed** (retry only the missing lens with a bounded cap? proceed with N−1 records
  and flag the gap explicitly in `plan_check_log.md`? escalate to the human?) — this
  decision is named as needed by the retrospective and subagent-commit-violation docs but
  never designed.
- **The disclosed "backgrounded/still-running sub-agent" gap** (a dispatch that never
  fires `SubagentStop` at all — a true hang, not a caught error) is named in
  `coder-detection-structural-signal-subagentstop-2026-07-08.md` but has **no proposed
  timeout/kill/liveness-check mechanism anywhere in this repo's research.**

---

## PROBLEM 3 — Single-writer JSONL schema for `plan_check_records.jsonl`

### What prior research already says (exact citations)

1. **`loop-team/harness/plancheck_saturation.py`** (340 lines, read in full) — the only
   existing JSONL-schema precedent directly in the Gate 10 family, and itself **already an
   instance of the exact anti-pattern Problem 3 warns against**. Its docstring (lines
   10–18) states the canonical shape is one JSON object per line,
   `{"round": 3, "records": [{"tag": "BINDING", "signature": "..."}]}` — **but also**
   accepts a second, different shape: *"For convenience, JSONL files may also contain flat
   record objects with their own `round` field; the CLI groups those by round before
   evaluating."* `_normalize_rounds()` (lines 68–111) detects which shape is present
   (`has_canonical_round = any(isinstance(item, dict) and "records" in item for item in
   rounds)`) and branches accordingly. **This is a live, currently-shipped example of
   "supporting two different record shapes in the same file" — the exact class of design
   this project already learned creates self-contradicting validation rules elsewhere, but
   this particular instance has not been flagged or audited against that lesson anywhere.**
   Per-record validation (`_validate_binding_tags`, lines 114–144) shows a real, working
   example of conditionally-required fields: `tag` (required always), `signature`
   (required only when `tag == "BINDING"`), `compiler_catchable` (bool, defaults `False`),
   `exclusion` (defaults `"none"`), `note` (fully optional, only affects `coder_notes`
   text).
2. **`loop-team/harness/reconcile_gap_records.py`'s `GapRecord` shape** (docstring +
   `_field`/`_touches`/`_mechanism_refs` helpers, lines 126–153): the closest existing
   schema sketch for one lens's one-round finding: `lens`, `round`, `gap_type`,
   `broken_assumption`, `why_it_fails`, `proposed_fix` (all effectively required), plus
   `touches` and `mechanism_refs` (both lists, both optional, default `[]` via
   `_field(record, name, []) or []`). This is an **in-memory Python dict convention
   consumed by the reconciliation pipeline**, not itself a persisted JSONL log format — it
   is the *input* shape reconciliation expects per lens-record, not the *accumulated,
   appended, round-over-round* log Problem 3 is asking about.
3. **`research/plan-check-reconciliation-prior-art-2026-07-02.md` Candidate 3.1
   (DefectDojo, lines 166–181):** *"DefectDojo enforces 'One Tool Per Test,' meaning
   results from different SARIF-producing tools cannot even be combined into a single
   Test."* Direct, real-world precedent for **avoiding mixed-shape merges via strict
   separation** (one schema per source/kind) rather than a permissive union schema that
   has to conditionally validate N different shapes in the same file — a transferable
   design principle directly applicable to Problem 3's stated anti-pattern.
4. **`loop-team/harness/verify.py`'s persisted-state conventions** (read directly):
   `_load_type_check_baseline()` (lines 457–509) and the pre-existing `smoke_manifest.json`
   contract (`verify.py` lines ~297–331, `{"artifacts": ["<relpath>", ...]}`) are both
   single-snapshot **plain JSON** files (not JSONL, not append-only), each with a single,
   strictly-validated shape, and each **raises a loud, distinctly-labeled `ValueError`** on
   a malformed/wrong-shape file rather than silently coercing or accepting an alternate
   shape (*"malformed %s: expected a JSON list of [file, code] pairs"*). This is a real,
   already-adopted convention in this codebase — "fail loud and distinctly on a
   malformed/wrong-shape persisted-state file" — directly reusable as a validation
   discipline for `plan_check_records.jsonl`, even though neither source is itself a
   JSONL/append-only precedent.

### Real external prior art already identified

- DefectDojo's "One Tool Per Test" strict-separation convention — `research/plan-check-reconciliation-prior-art-2026-07-02.md` Candidate 3.1 (see above).
- No other external JSONL/event-log schema-design tool or paper has been researched anywhere in this repo (see gap below).

### What is NOT yet covered — the genuine gap for the next research phase

- **Zero research anywhere in this repo on JSON Lines/ndjson conventions, event-sourcing /
  append-only-log schema design, or schema-versioning fields** (a `schema_version` key, an
  additive-only field-evolution discipline) for a single-writer, round-over-round
  accumulating log — confirmed via `grep -rliE "ndjson|json lines|event.sourcing|schema.
  version|schema_version"` across the whole `research/` directory (zero hits). This is
  genuinely virgin territory for this project — no comparison has been made against, e.g.,
  OpenTelemetry's log-record schema, the JSON Lines spec's own conventions, or how mature
  event-sourced systems (EventStore, Kafka schema registry) handle "one accumulating file,
  optional fields, single writer."
- **`plancheck_saturation.py`'s own existing dual-shape support has never been flagged or
  audited against the "two record shapes = self-contradicting validation" lesson** — this
  is a live, shipped instance of the anti-pattern Problem 3 names, sitting in the exact
  codebase being hardened, and it has not been surfaced anywhere as a thing to fix or as a
  cautionary case study before this inventory pass.
- **No design exists yet for the general (not just `[BINDING]`) `plan_check_records.jsonl`
  schema at all** — i.e., which fields every entry needs regardless of tag (round number,
  lens name or "generalist", timestamp, `gap_type`, verdict token) versus which fields are
  genuinely conditional on tag (a `signature` field is only meaningful once Problem 1's
  fingerprint design exists for LOGIC/CONCURRENCY/SECURITY). **This schema design is
  structurally blocked on Problem 1** — the `signature` field's contract (what it contains,
  when it's required, how it's validated) cannot be finalized until the fingerprinting
  scheme for non-BINDING tags is designed. This dependency has not been stated explicitly
  in any prior document and is worth carrying forward as an ordering constraint for the
  next design pass (Problem 1 before Problem 3, not in parallel).
- **No research has considered whether the "two shapes in one file" problem is better
  solved by a strict single-shape schema (DefectDojo's model) vs. a deliberately-versioned
  envelope** (e.g., every line is `{"schema_version": 1, "type": "round_summary" | "gap_record",
  ...}` with `type`-conditional required fields formally enumerated) — both are plausible
  fixes and neither has been evaluated against this project's actual read/write patterns
  (single writer, Oga-only, append-only, read back by `plancheck_saturation.py`/
  `reconcile_gap_records.py`/a human).

---

## Cross-problem dependency note (new finding from this inventory, not previously stated anywhere)

The three problems are not independent design tracks. **Problem 3's schema cannot be
finalized until Problem 1's fingerprint design exists** (the `signature` field's contract
depends on it), and **Problem 1's own sibling research
(`plancheck-nonbinding-saturation-2026-07-09.md`)'s top candidate (capture-recapture
stopping) depends on `reconcile_gap_records.py`'s clustering being correct** — which the
confirmed empty-`mechanism_refs` bug currently undermines. Recommended solve order for the
next design pass: **Problem 1 (fingerprint + fix the clustering bug) → Problem 3 (schema,
now that the `signature` contract is known) → Problem 2 (barrier design, which is largely
independent of the other two but shares the "instructional vs. structural" discipline
already established in `research/loop-team-process-retrospective-review-2026-07-02.md`).**

## Files read directly this session (grounding for every citation above)

- `research/plan-check-reconciliation-prior-art-2026-07-02.md` (full, 578 lines)
- `research/plancheck-nonbinding-saturation-2026-07-09.md` (full, 476 lines)
- `research/ops-clock-alt-method-experiment-2026-07-02.md` (full — not directly relevant to any of the 3 problems beyond the general saturation-research thread; noted, not cited as prior art)
- `research/candidate-ranking-prior-art.md` (full — priority-ranking rubric only, not directly relevant to these 3 problems; noted per task instruction, not cited as prior art)
- `research/loop-team-process-retrospective-review-2026-07-02.md` (targeted sections: lines 440–498, 625–653)
- `research/coder-detection-structural-signal-subagentstop-2026-07-08.md` (targeted: lines 1–200)
- `research/subagent-commit-violation-signaling-2026-07-03.md` (full, 359 lines)
- `research/claude-code-duplicate-session-detection-2026-07-02.md` (targeted skim — different concurrency problem, duplicate-process detection, not sub-agent completion counting; not directly relevant)
- `research/defect-taxonomy-standards-prior-art-2026-07-02.md` (targeted: lines 1–45)
- `research/ops-clock-gap-taxonomy-2026-07-02.md` (grepped for fingerprint/signature/dedup terms — one relevant line, already covered via the prior-art doc it cites)
- `research/compiler-feedback-loop-gate-design-2026-07-08.md` (full read of the fingerprint-relevant sections: lines 1–410)
- `research/padsplit-cockpit-structured-logging-2026-07-03.md` (targeted skim — different domain, Next.js app logging, not JSONL schema for plan-check; not directly relevant)
- `research/run-logging-enforcement-gap-codex-vs-claude-code-2026-07-09.md`, `research/claim-ledger-goal-drift-mechanism-spec-2026-07-07.md` (grepped for JSONL/schema terms — no directly relevant content beyond what's cited)
- `research/radar.md` (grepped for fingerprint/signature/dedup/barrier/jsonl-schema terms — confirmed no additional rows beyond what's already covered above)
- `loop-team/harness/reconcile_gap_records.py` (full, 444 lines)
- `loop-team/harness/plancheck_saturation.py` (full, 340 lines)
- `loop-team/harness/verify.py` (targeted: lines 437–605, the type-check/baseline/smoke-manifest sections)
- `loop-team/DESIGN_CHECKLIST.md` (full, 221 lines)
- `loop-team/orchestrator.md` (targeted: lines 1–90, 570–650)
- `fix_plan.md` (grepped for `H-GUARD-3`, `H-LT7`, `H-STOPGUARD-SUBAGENTTYPE-ADJACENCY-SELFMATCH-1`, `async`; read lines 1230–1430 and 5710–5780 in full)
