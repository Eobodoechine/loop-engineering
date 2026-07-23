# Synthesis: Gate 10's 3 open problems — best real-world technique, portability, and the concrete spec change (2026-07-09)

**Mode:** synthesis only (per dispatch instruction) — no new research performed. This
document reconciles one inventory pass and four deep-research sweeps, all already saved
to disk, plus direct verification reads of the live code this synthesis recommends
changing (`loop-team/harness/reconcile_gap_records.py`, `loop-team/harness/
plancheck_saturation.py`, `loop-team/orchestrator.md`) to ground each recommendation in
exact file/line references rather than paraphrase.

**Inputs synthesized (read in full before writing this doc):**
- `research/gate10-concurrency-fingerprint-inventory-2026-07-09.md` (inventory pass)
- `research/defect-fingerprinting-prior-art-2026-07-09.md` (Problem 1 sweep)
- `research/async-completion-barrier-prior-art-2026-07-09.md` (Problem 2 sweep)
- `research/single-writer-jsonl-schema-prior-art-2026-07-09.md` (Problem 3 sweep)
- `research/multi-reviewer-merge-prior-art-deepdive-2026-07-09.md` (adjacent sweep — not
  one of the 3 named problems; reconciled in as a bonus section, see below)
- Direct reads this session: `loop-team/harness/reconcile_gap_records.py` (444 lines,
  full), `loop-team/harness/plancheck_saturation.py` (340 lines, full),
  `loop-team/orchestrator.md` (targeted: lines 51–90, 577–650, plus a full-file grep for
  `Promise`/`Workflow`/`agent(` to check whether a fan-out+join call site already exists)

**Target system, restated for grounding:** a single-process, turn-based LLM orchestrator
(Oga) that dispatches N parallel adversarial-lens plan-check Verifiers (via the `Workflow`
tool's `agent(prompt, {schema})` form, per `orchestrator.md` line 66 and the
`robustLensDispatch` wrapper at lines 595–607) and reconciles their gap records via
`harness/reconcile_gap_records.py`. `plancheck_gate10_runner.py` does not exist on disk
yet — it is the still-in-design successor to `plancheck_saturation.py` (confirmed via
`find` in the inventory pass, re-confirmed not contradicted this pass).

---

## Problem 1 — Deterministic defect fingerprinting

### Best available real-world technique

There is **no single best tool to adopt** — the fingerprinting sweep's headline finding,
independently confirmed across GitHub Code Scanning/CodeQL (`fingerprints.ts`, a rolling
hash of the flagged *line's content*), SonarQube (rule+line-hash tier, message
explicitly irrelevant), Semgrep (`get_match_based_key()` — rule + matched-code-with-
metavariables, never the free-text message), Coverity (checker+function merge key), and
DefectDojo (the closest real analog — an aggregator that must dedupe across 180+
independently-worded scanner outputs) is that **every real system computes identity from
a structural/positional/categorical signal and excludes free-text description from it.**
Where a real system is forced to fall back to text (DefectDojo's `compute_hash_code_legacy`,
SonarQube's message-match tier), it requires **literal, unmodified string equality** —
not paraphrase tolerance — and DefectDojo's own currently-open/recently-closed GitHub
issues (#13497, #12320, #3958, #12924) show that fallback still misfires in production.
The one field that directly studies "same defect, reworded, by independent people"
(duplicate bug report detection) never produces a deterministic identical string at all —
it produces a ranked similarity score + threshold + human adjudication.

**Direct conclusion:** our exact ask — an exact-equality signature that collapses
arbitrarily-reworded free text with no structural signal and no taxonomy — **is not a
solved problem anywhere in production software or the closest academic literature.** This
is the honest finding to act on, not a reason to invent a fix. (`research/defect-
fingerprinting-prior-art-2026-07-09.md`, "Direct answer" section.)

### Portability — split into two cases, per the sweep's own honest split

- **Case A (`mechanism_refs` non-empty):** directly portable. Structural fields already
  exist on our `GapRecord` (`touches`, `mechanism_refs`); canonicalizing and hashing them
  is a ~20-line, stdlib-only change modeled on Semgrep's `get_match_based_key()`/
  `get_match_based_id()` shape. **Transfer-condition check:** requires `mechanism_refs` to
  actually be populated at write time — currently **instructional, not structural**
  (nothing forces a lens to fill it in), which is exactly why this is the common-case gap
  today, per the inventory's own finding.
- **Case B (`mechanism_refs` empty):** **not portable from anywhere** — no real tool
  solves this shape. The only defensible next step is an original, falsifiable
  experiment (LLM-authored controlled-vocabulary tuple at write time), explicitly labeled
  TESTABLE, not IMPLEMENTABLE_NOW, per the fingerprinting sweep's own triage.

### The live bug this uncovered (confirmed by direct re-read this session)

`loop-team/harness/reconcile_gap_records.py`:
- `cluster_near_duplicates()` line 254: `if _mechanism_refs(records[i]).isdisjoint(_mechanism_refs(records[j])): continue` — `set().isdisjoint(set())` is `True` in Python, so whenever *either* record's `mechanism_refs` is empty, the `SequenceMatcher` similarity check on line 256 never runs.
- `orthogonality_filter()` (lines 166–182) has the same root flaw twice-over: it ANDs `touches`-disjointness with `mechanism_refs`-disjointness (lines 176–179), so two records that both simply omit *both* optional fields are declared `INDEPENDENT` outright.
- `needs_mechanism_trace()` (lines 189–218) inherits the flaw transitively: its fallback path (line 216) calls `orthogonality_filter()` and treats its `INDEPENDENT` result as "no trace needed" — so the same empty-optional-fields case that produces a false `INDEPENDENT` in the pre-filter also short-circuits the mandatory mechanism-trace, the *second* structural safety net this module has.

Neither flaw has ever been flagged in `research/` or `fix_plan.md` before this inventory
pass (confirmed via grep). The module's own docstring (lines 32–43) already states the
correct design philosophy — *"fail toward more checking, not less"* — the empty-set
case is simply not implemented to match that stated philosophy yet.

### Adopt this / change our spec this way

1. **Bug fix (do this regardless of anything else below — small, mechanical, no design
   debate needed):** in `cluster_near_duplicates()` and `orthogonality_filter()`, stop
   treating "both empty" as "provably disjoint." Concretely: `mechanism_refs`-disjointness
   should only count as a *signal* when **both** records have non-empty `mechanism_refs`;
   when either is empty, treat that axis as "no signal" (drop it from the AND-condition in
   `orthogonality_filter`, and always fall through to `SequenceMatcher` in
   `cluster_near_duplicates` rather than `continue`-ing past it). This directly implements
   the module's own already-stated "fail toward more checking, not less" rule for the case
   it currently doesn't cover.
2. **Case A, IMPLEMENTABLE_NOW (still needs an A/B before load-bearing, per the
   Researcher role's own guardrail):** add a `_structural_signature(record)` helper to
   `reconcile_gap_records.py` that canonicalizes (sort + normalize path casing)
   `mechanism_refs` **and `touches`** — **deliberately excluding `gap_type`/`tag` from the
   hash input** (see the cross-sweep refinement below) — and hashes the tuple
   (`hashlib.sha256`), modeled on Semgrep's `get_match_based_key()`. Wire this as the
   `signature` field for non-BINDING tags whenever `mechanism_refs` is non-empty. This
   REQUIRES a companion spec change: make `mechanism_refs` a **required** field in the
   plan-check lens dispatch prompt (`orchestrator.md`) for every LOGIC/CONCURRENCY/
   SECURITY finding, not the currently-optional, often-empty convention — otherwise Case A
   only ever covers the minority of findings, per the inventory's own kill criterion.
3. **Cross-sweep refinement (new synthesis-level finding, not stated by either sweep
   alone):** the fingerprinting sweep's Case A sketch included `gap_type`/tag in the hash
   input; the separate multi-reviewer-merge deep-dive found that **no tool anywhere
   resolves classification disagreement** (two reviewers agree on the defect, disagree on
   its category — `calimero-network/ai-code-reviewer`'s own clustering requires exact
   category match, so a category disagreement just produces two permanently-separate
   findings). Reconciling these two: **exclude `gap_type` from the Case A structural hash
   input.** `mechanism_refs` + `touches` identify *what part of the system* a finding is
   about, which is a stabler cross-round identity than a lens's own category label — this
   sidesteps the classification-disagreement failure mode entirely rather than
   inheriting it.
4. **Case B, TESTABLE only — do not ship an equality gate on it without the experiment:**
   add a controlled-vocabulary `{primary_entity, defect_class}` tuple, extracted by the
   SAME LLM call that writes the finding (mirroring `DESIGN_CHECKLIST.md` gate 9's
   `[SECURITY-ORACLE]` tag-at-write-time convention already live in this codebase). Before
   trusting it as a gate: run the paraphrase-convergence backtest the fingerprinting
   sweep specifies (N real findings × M independent paraphrases → measure % producing an
   identical tuple), pre-registered kill criterion **<70% convergence → do not gate on it**.
   Until that experiment runs and clears the bar, `plancheck_gate10_runner.py` must treat
   every empty-`mechanism_refs` LOGIC/CONCURRENCY/SECURITY finding as "new" for saturation
   purposes — fail toward more review, never a silent auto-collapse. This is the honest
   default given no real fix exists anywhere, not a placeholder to feel bad about.
5. **Bonus check performed, clean result:** the multi-reviewer-merge deep-dive found a
   real, reproduced severity-merge bug in a *sibling* module of the tool
   `reconcile_gap_records.py` already borrows from
   (`calimero-network/ai-code-reviewer`'s `orchestrator/aggregator.py::_merge_cluster()`,
   `max(findings, key=lambda f: list(Severity).index(f.severity))` — picks NITPICK over
   CRITICAL, the opposite of its own comment). I checked `reconcile_gap_records.py`'s own
   `_consolidate()` (lines 267–286) against this exact bug class: it uses an explicit
   membership check against `NEVER_DROP_GAP_TYPES`, not an enum-index `max()` — **confirmed
   not vulnerable to this bug shape.** No action needed here; recorded so a future
   contributor doesn't reach for `_merge_cluster` as a model if ever extending this logic.

**Citations:** `research/defect-fingerprinting-prior-art-2026-07-09.md` (§1–7, "Direct
answer," Case A/B recommendation); `research/gate10-concurrency-fingerprint-inventory-
2026-07-09.md` (bug location, DESIGN_CHECKLIST gate 9/10 tag-at-write-time convention);
`research/multi-reviewer-merge-prior-art-deepdive-2026-07-09.md` (`_merge_cluster` bug,
classification-disagreement gap); `loop-team/harness/reconcile_gap_records.py` lines
136–137, 166–182, 189–218, 225–264, 267–286 (direct read, this session).

---

## Problem 2 — Async N-of-N completion barrier for parallel lens dispatch

### Best available real-world technique

**One universal structural idiom, confirmed by reading the actual CPython `asyncio.gather()`
source, not just docs:** fix the expected set synchronously, *before* any unit of work can
return, then gate on **set-equality** (`completed == expected`), never a bare counter or a
notification stream. In `asyncio.gather()`, `nfuts` is incremented in the same synchronous
loop that registers every future's done-callback — no callback can fire until that loop
returns control, so there is no window where a callback observes a partially-populated
`nfuts`. Every mature orchestration system studied (Temporal `Promise.allOf`, Airflow
trigger rules against DAG-declared `task_ids`, Step Functions' `Parallel` state waiting on
its own fixed `Branches` array) is the same idiom dressed in heavier survival machinery for
failure domains (multi-process crash, cross-machine workers) our single-process loop
doesn't have.

**Most directly relevant finding, not a generic pattern but a fact about the actual tool
this team runs on:** Anthropic's own subagent background-dispatch notification channel is
**documented broken at N>1 concurrency**, confirmed via two real, opened GitHub issues:
[#20754](https://github.com/anthropics/claude-code/issues/20754) (3 parallel background
agents, only 1 notification delivered, all 3 actually completed) and
[#21165](https://github.com/anthropics/claude-code/issues/21165) (5 parallel background
agents, only the first notification processed, one never surfaces). This is a live
demonstration, inside our own substrate, of exactly the "record a count and hope"
anti-pattern the problem statement warns against.

### Portability

**Partially structural, partially still a design gap in our own code — and this is the
most important grounded finding of this synthesis, not repeated by either sweep alone.**

The async-barriers sweep's default recommendation ("dispatch as foreground `Task`/`Agent`
tool calls in one turn — the Messages API's `tool_use`/`tool_result` protocol is a free
`Promise.all`") **does not directly apply to this system as currently designed**, because
`orchestrator.md` line 66 and the `robustLensDispatch` wrapper (lines 595–607) confirm
plan-check lenses are dispatched via the **`Workflow` tool's `agent(prompt, {schema})`
form** — a JavaScript script executed by a separate runtime, *outside* the conversational
turn boundary (per the sweep's own §6, citing Anthropic's workflows doc: "a runtime
executes it in the background"). Inside that JS runtime, `Promise.all`/`Promise.allSettled`
semantics *can* provide the same structural guarantee `asyncio.gather()` does — **but only
if the script actually uses them.** I grepped the entirety of `orchestrator.md` for
`Promise` and found **zero hits**: `robustLensDispatch` only wraps ONE lens's own
retry/fallback; there is currently **no fan-out+join call site anywhere in this codebase**
that dispatches N lenses and waits on all N before calling `reconcile_gap_records.py`. This
is exactly the gap the inventory and the barrier sweep each named ("no design exists
anywhere for an explicit N-count verify-before-proceed step") — confirmed here by direct
grep, not inferred.

A second unresolved fact, also unresolved by the sweep itself (its own "Not found /
not verified" section): whether the `Workflow` tool's `agent()` calls, when composed
inside a `Promise.allSettled`, genuinely execute concurrently in the underlying runtime, or
whether the JS-level composition is cosmetic over an actually-sequential dispatcher. This
must be verified with a cheap, real probe before the design below is trusted (per this
team's own "probe before you theorize" standing practice) — see step 2 below.

### Adopt this / change our spec this way

1. **Add the fan-out+join call site that does not currently exist**, inside the
   Workflow script that dispatches plan-check lenses:
   ```js
   const expected = lenses.map(l => l.label);          // fixed BEFORE any dispatch —
                                                          // mirrors asyncio.gather's nfuts latch
   const settled = await Promise.allSettled(
     lenses.map(l => robustLensDispatch(l.schemaPrompt, l.freeTextPrompt, l.schema, l.opts))
   );
   const collected = settled.map((r, i) => r.status === 'fulfilled'
     ? r.value
     : { lens: expected[i], loop_gate: 'PLAN_FAIL', gaps: [],
         reasoning: `dispatch error: ${r.reason}`, partial: true });
   ```
   Use `Promise.allSettled`, **not** `Promise.all` — a single lens's hard rejection must
   not discard the other N−1 real results (this is Step Functions' `Catch`/Airflow's
   `all_done` shape, the deliberate opposite of the all-or-nothing default `Promise.all`
   or a bare Step-Functions `Parallel` state would give you).
2. **Before relying on step 1 structurally, run the cheap probe the sweep itself flagged
   as missing:** dispatch 3 trivial stub `agent()` calls inside a `Promise.allSettled`,
   each instructed to sleep ~20s, and measure wall-clock time. ~20s total → the runtime
   genuinely parallelizes and the design above holds structurally. ~60s total → it's
   secretly sequential and this whole approach needs redesigning (e.g., true background
   dispatch + our own polling of terminal artifacts, per step 6). This is a real,
   falsifiable, ~1-minute test — do not ship the fan-out design on the assumption alone.
3. **`plancheck_gate10_runner.py` must structurally assert completeness before calling
   `reconcile_gap_records.reconcile()`:** `assert len(collected) == len(expected)` AND
   `{c["lens"] for c in collected} == set(expected)` — a bare count is insufficient
   (catches a dropped lens but not a duplicate/misrouted one); checking the label SET is
   the concrete form of `research/subagent-commit-violation-signaling-2026-07-03.md`'s
   already-articulated principle ("don't just check flag EXISTENCE — read and surface the
   CONTENT"). This must be literal code, not a markdown instruction to Oga — writing it in
   prose is exactly the "instructional, and a compliance failure would be silent and
   load-bearing" risk class the Researcher role brief's transfer-condition check exists to
   catch.
4. **Bounded retry, one lens at a time:** for any label in `expected − collected_labels`,
   retry that single lens exactly once via the existing `robustLensDispatch` (never
   re-dispatch the whole batch) — Step Functions' `Retry`/Airflow's per-task `retries`,
   already a shape this codebase partially has for a single lens's own schema-vs-free-text
   fallback, just not yet for a whole-lens non-response.
5. **Explicit partial-completion fallback, never silent:** if the retry also fails, record
   an explicit `status: "partial"` + `partial_reason: "lens <X> did not return after 1
   retry"` (see Problem 3's schema) in the JSONL record and `plan_check_log.md`, and
   default that lens's contribution to `PLAN_FAIL` — mirroring `robustLensDispatch`'s own
   existing "default to FAIL, never silently PASS an unparseable fallback" line (line 604).
   Never block indefinitely, never treat the missing lens as if it had returned
   `INDEPENDENT`/`COMPATIBLE`.
6. **Never rely on the background-subagent notification channel for lens completion** —
   it is confirmed broken at N>1 in the actual tool (#20754, #21165). If a lens genuinely
   must be backgrounded (e.g., exceeds a practical foreground-turn duration), completion
   must be verified by directly reading that lens's own terminal artifact (output
   file/transcript), never by counting notification arrivals — issue #20754's own
   documented workaround, and the one piece of new infrastructure this synthesis
   explicitly recommends AGAINST building (a custom notification/queue layer would
   reproduce the exact fragile piece already proven broken upstream).

**Citations:** `research/async-completion-barrier-prior-art-2026-07-09.md` (§1–8,
`asyncio.gather` source walkthrough, §6 Claude Code background-notification findings, §7–8
transfer-condition table); `loop-team/orchestrator.md` lines 51–66, 577–613 (direct read,
this session — confirms Workflow-tool dispatch path and the absence of any existing
fan-out+join site); `research/subagent-commit-violation-signaling-2026-07-03.md` (cited via
the inventory, "check content not existence" principle).

---

## Problem 3 — Single-writer JSONL schema for `plan_check_records.jsonl`

### Best available real-world technique

**Fully solved elsewhere, directly portable, no gap.** Every real single-writer,
append-only JSONL log opened directly this pass (`character-ai/larch`'s
`review-findings-full.jsonl` — the closest real analog, a code-review-findings log —
plus `squall321/SignalForge`, `AlignTrue/aligntrue`, `pajama-studio/thriller`,
`ianm199/omnilua`, `Rul1an/assay`) uses **one flat record shape per file**, with optional
fields represented purely by key omission, a required discriminator-like field where the
record's "kind" varies, and a `schema_version` bumped only on breaking changes. Platform-
grade systems (HashiCorp Vault's `type` field, Kubernetes audit's `stage` field,
OpenTelemetry's Logs Data Model) confirm the identical pattern at the mature end. The one
real counter-example found (`mick-gsk/drift`'s single disjoint-keyset header line) is the
narrow, safe exception, not license to mix shapes generally.

**The single most load-bearing piece of evidence:** `character-ai/larch`'s own session
transcript documents a real, live bug in the *exact* failure class this problem names —
one script required a `partial_reason` field, another emitted `detail` for the identical
concept, and validation broke. This is a direct, real-world precedent for the strongest,
cheapest fix: **exactly one canonical field name for "why is this partial," emitted
identically by every writer path.**

### Portability

Directly portable, no adaptation gap — this is transport/schema convention, not a
runtime-dependent mechanism, so there is no transfer-condition mismatch to flag.

### Adopt this / change our spec this way

1. **Fix `plancheck_saturation.py`'s existing dual-shape support — itself a live instance
   of the anti-pattern.** Confirmed by direct re-read: the docstring (lines 10–19) states
   the canonical shape as `{"round": 3, "records": [...]}` but also accepts, "for
   convenience," a flat per-record shape with its own `round` field; `_normalize_rounds()`
   (lines 73–114) detects which is present via `has_canonical_round` and branches. **Drop
   the wrapped-round shape entirely.** Adopt ONE flat shape, one JSON object per line, one
   record per line — this matches every real corpus found with zero exceptions, and it is
   also the more natural shape for THIS writer: Oga appends one lens's result as it's
   produced, and the wrapped shape requires buffering an entire round's N records before
   the first write, which fights single-writer append-only discipline. Keep
   `_normalize_rounds()`'s grouping-by-round logic (it still needs to reconstruct rounds
   from flat records for evaluation) — delete only the `has_canonical_round` branch and
   the docstring's "for convenience" clause.
2. **New required schema, one line per finding:**
   ```json
   {
     "schema_version": 1,
     "round": 4,
     "lens": "concurrency-isolation",
     "timestamp": "2026-07-09T18:22:00Z",
     "tag": "CONCURRENCY",
     "status": "complete",
     "signature": "a1b2c3...",
     "signature_kind": "structural",
     "touches": ["src/foo.py"],
     "mechanism_refs": ["scheduler.enqueue"],
     "compiler_catchable": false,
     "exclusion": "none",
     "note": null,
     "partial_reason": null
   }
   ```
   - **Always required:** `schema_version`, `round`, `lens`, `timestamp`, `tag`, `status`.
   - **Conditionally required:** `signature` — required + exact-string-equality when
     `tag == "BINDING"` (unchanged from today's convention); **optional and explicitly
     experimental-flagged** for LOGIC/CONCURRENCY/SECURITY, populated only per Problem 1's
     Case A (structural hash, `signature_kind: "structural"`) when `mechanism_refs` is
     non-empty. `partial_reason` — required **iff** `status == "partial"`, exactly one
     canonical name, no synonyms across any writer path (the single highest-value fix per
     the schema sweep's own strongest evidence).
   - **Always optional, omit when absent:** `touches`, `mechanism_refs`,
     `compiler_catchable`, `exclusion`, `note`.
3. **`status` is a required enum (`"complete"|"partial"`), never inferred from which
   optional fields happen to be present** — the Vault `type` / Kubernetes `stage` /
   JSON-Schema-discriminator precedent, and the direct fix for Problem 3's stated failure
   mode. This is also exactly where Problem 2's partial-completion state (a lens missing
   after bounded retry) lands in the persisted record — the two problems share one field.
4. **`schema_version` bump:** adding `status`/`partial_reason`/`signature_kind` as new
   required-or-conditionally-required fields is a breaking change to the existing implicit
   shape — treat today's undocumented shape as version 0, bump to `schema_version: 1` now.
   Future purely-additive optional fields do not require another bump (confirmed
   convention: `pajama-studio/thriller`'s `capsule_id` field appeared mid-stream at
   constant `schema_version`).
5. **Validator discipline — reuse, don't reinvent:** `verify.py`'s own
   `_load_type_check_baseline()`/smoke-manifest convention (raise a loud, distinctly-labeled
   `ValueError` on a malformed/wrong-shape file rather than silently coercing) is already
   adopted elsewhere in this codebase — apply the same discipline to the new
   `plan_check_records.jsonl` reader: require the small required-field set on every line,
   ignore unknown fields (forward-compat), reject (not silently accept) a line matching the
   old wrapped-round shape once it's deprecated.
6. **Explicit, stated cross-problem dependency (do not build Problem 3's `signature`
   validation logic before Problem 1's Case A/B lands):** the `signature_kind` field exists
   precisely so `plancheck_gate10_runner.py`'s saturation logic never conflates an
   unvalidated experimental signature with the hardened BINDING exact-match convention.
   Ship the schema now with the field defined; do not turn on any automatic
   recurrence-based stopping for `signature_kind: "structural"` or a future `"llm_slug"`
   until Problem 1's respective experiments clear their kill criteria.

**Citations:** `research/single-writer-jsonl-schema-prior-art-2026-07-09.md` (full corpus,
the `larch` `partial_reason`/`detail` bug, the 8 concrete rules, the recommended record
shape); `loop-team/harness/plancheck_saturation.py` lines 10–19, 73–114, 117–148 (direct
read, this session — confirms the live dual-shape anti-pattern and the existing
conditionally-required-field validation pattern to extend); `loop-team/harness/verify.py`
(cited via the inventory doc, malformed-file discipline).

---

## Cross-problem dependency and recommended build order (unchanged from the inventory,
reconfirmed by this synthesis, not contradicted by anything in the four sweeps)

**Problem 1 → Problem 3 → Problem 2**, in that order:
1. **Problem 1 first** — fix the `reconcile_gap_records.py` bug (a pure, low-risk mechanical
   fix, ship immediately) and land Case A's structural signature + the mandatory
   `mechanism_refs` dispatch-prompt change. This is a hard prerequisite for Problem 3's
   `signature`/`signature_kind` fields to have a real contract, and it also directly
   improves the input quality Problem 2's reconciliation step consumes (a correct
   clustering decision on N real records matters more once N is verified complete).
2. **Problem 3 second** — now that `signature`'s contract is known, fix
   `plancheck_saturation.py`'s dual-shape anti-pattern and land the new flat schema with
   `status`/`partial_reason`/`signature_kind`.
3. **Problem 2 third** — largely independent of the other two mechanically, but its
   partial-completion state needs Problem 3's `status`/`partial_reason` fields to have
   somewhere real to land, so it is the natural last piece to wire in end-to-end (the
   fan-out+join code itself, and its probe in step 2 of that section, can be built and
   tested in parallel with the other two — only the final JSONL-write step depends on
   Problem 3's schema existing).

---

## Bonus / adjacent finding (sweep 4 — not one of the 3 named problems, reconciled in
because it directly touches `reconcile_gap_records.py`'s existing mechanism)

The multi-reviewer-merge deep-dive (`research/multi-reviewer-merge-prior-art-deepdive-
2026-07-09.md`) was dispatched against a *different* open question (same-round N-lens
disagreement merge, not cross-round fingerprinting or the completion barrier) but
surfaced two things worth carrying forward:

- **A real, tested, portable pattern for a FUTURE capability this codebase doesn't have
  yet:** `calimero-network/ai-code-reviewer`'s `apply_cross_review()`
  (`src/ai_reviewer/review.py:330-429`) — an abstention-aware 2/3 supermajority vote with a
  narrowly-scoped CRITICAL+SECURITY one-valid-vote-survives bypass, backed by two dedicated
  unit tests. `reconcile_gap_records.py` today only pairwise-traces `CONTRADICTORY` pairs
  (via the injected `mechanism_tracer`/`tie_breaker` callables) — it has no N-way "every
  lens votes on every other lens's findings" mechanism. This is **TESTABLE, not urgent for
  Gate 10 itself** — it is out of scope for the 3 concrete problems this dispatch was
  scoped to, and is recorded here as a dive-in-queue candidate for a later session, not a
  required change now.
- **The severity-merge bug check already folded into the Problem 1 section above**
  (`_merge_cluster`'s inverted `max()` — confirmed our own `_consolidate()` is not
  vulnerable) and the **classification-disagreement gap** already folded into Problem 1's
  cross-sweep refinement (exclude `gap_type` from the Case A structural signature hash).

No JSONL/append-log persistence pattern was found in any of the four tools surveyed in
that dossier — reinforcing (not contradicting) Problem 3's own separately-sourced
recommendation.

---

## What is genuinely NOT solved anywhere — stated plainly, per problem

- **Problem 1, Case B (empty `mechanism_refs`):** no real tool or paper solves exact-match
  fingerprinting of arbitrarily-reworded free text. The only defensible path is the
  original, falsifiable paraphrase-convergence experiment above — home-grown, explicitly
  flagged as an experiment, not a proven technique.
- **Problem 2:** the formal distributed-systems primitives (`CountDownLatch`, `WaitGroup`,
  Temporal/Airflow/Step-Functions-as-infrastructure) are real and well-understood but
  solve failure domains (multi-process/multi-machine crash survival) this system doesn't
  have — correctly identified as overkill by the sweep, not adopted here. What genuinely
  has no precedent anywhere is the exact concurrency behavior of Anthropic's own `Workflow`
  tool's `agent()`/`pipeline()` calls — this is a gap in Anthropic's own public
  documentation, not a gap in this project's research; the home-grown answer is the cheap
  live probe (step 2 of Problem 2's recommendation), not a borrowed guarantee.
- **Problem 3:** fully solved elsewhere; no home-grown component needed.

## Files read directly this session (grounding for every claim above)

- `research/gate10-concurrency-fingerprint-inventory-2026-07-09.md` (full)
- `research/defect-fingerprinting-prior-art-2026-07-09.md` (full)
- `research/async-completion-barrier-prior-art-2026-07-09.md` (full)
- `research/single-writer-jsonl-schema-prior-art-2026-07-09.md` (full)
- `research/multi-reviewer-merge-prior-art-deepdive-2026-07-09.md` (full)
- `loop-team/roles/researcher.md` (full, role brief)
- `loop-team/harness/reconcile_gap_records.py` (full, 444 lines)
- `loop-team/harness/plancheck_saturation.py` (full, 340 lines)
- `loop-team/orchestrator.md` (lines 51–90, 577–650; full-file grep for `Promise`/
  `Workflow`/`agent(`, zero `Promise` hits confirmed)
- `research/radar.md` (read for structure/format before adding the pointer entry below)
