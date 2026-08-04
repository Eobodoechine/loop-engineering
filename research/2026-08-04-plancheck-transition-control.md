# Plan-check → execution transition control (interim prompt control + follow-up harness)

**Date:** 2026-08-04
**Question:** What is the smallest reliable control that stops Loop-Team from over-analyzing
prose in plan-check/spec review, without weakening real verification?
**Status:** Design/spec. Interim prompt patch is implementation-ready. The `plancheck_transition.py`
harness is designed, **not** built (no implementation authorized yet).

Produced by the Loop Team: Researcher (repo/prior-art evidence, Sonnet) → Architect (design, Opus)
+ Harness designer (schema, Sonnet) → independent Verifier (Opus) + challenger (Fable). The Verifier
returned **PLAN_FAIL** on the first design; this document is the **hardened v2** that applies its
prescribed fix. Process trail: `runs/2026-08-04_plancheck-transition/` (local; gitignored).

---

## 0. Why the existing controls are partial (verified against code)

| Control | File | Fires only when | Cannot act on |
|---|---|---|---|
| `STOP_PROSE_REVIEW` | `harness/plancheck_saturation.py` | last **3 consecutive** rounds are **only** compiler-catchable `[BINDING]`, one signature, zero `[LOGIC]/[CONCURRENCY]/[SECURITY]` | any wording/citation/formatting/refinement churn — it returns `CONTINUE_PLAN_CHECK` forever for **every** non-`BINDING` tag |
| `SHIP_NARROW_PLAN` | `harness/plan_size_governor.py` | spec exceeds a **self-declared** `MVP_MAX_LINES`/`MVP_MAX_ACS` | anything if no boundary is declared (→ `INVALID_PLAN_BOUNDARY`); it has no concept of a "finding" or round history |
| Cost-of-delay transition | `orchestrator.md:138-150` + `hooks/cod_state.py` | — | **nothing today: it is not live.** `cod_state.py` is enforcement-shaped SQLite machinery with **zero callers**; the repo's own AST registry tags it `UNINSTALLED_ORPHANED`. "Instructional only" (`orchestrator.md:99`) is still accurate. |
| Sidecar Researcher | `orchestrator.md:26-64` | 3rd spec revision | it is additive and can itself *extend* analysis |

**The gap:** nothing forces a *per-round* decision over the *whole* finding taxonomy, and nothing
offers the `EXECUTE_PROOF` route (change the oracle) — which the prior art says does the most work.

## 1. The binding law (from `research/2026-07-16-planning-stop-governor-SYNTHESIS.md`, 5 evidence legs)

- **Semantic signals REDIRECT; only counters and cost caps TERMINATE.** No surveyed shipped framework
  trusts a model's judgment in the *give-up* direction to end a run (gameability + noise).
  → **All 5 decisions here are REDIRECTS. None terminates verification.**
- **The hazard is FLAT** (measured, 59 logs: round 3 still finds a real defect ~84% of the time;
  late-round backtest **15:0**). The **zero-new-finding clause is mandatory** (`DESIGN_CHECKLIST.md`
  gate 10) — a myopic "diminishing returns" stop is empirically refuted and pre-registered as an
  automatic kill.
- **The real fix is the ORACLE, not the round count** (Huang et al. ICLR 2024: execution-grounding
  29.1%→47.7% while cutting overthinking 2.43→1.05). → this is `EXECUTE_PROOF`.
- **Persistent yield ⇒ rewrite/CUT the artifact, never review harder** (TaxAhead 782→97). → `CUT_SCOPE`,
  authorized by artifact **size**, not by re-labelling a finding.
- **A prompt-layer governor fails silently** — real bounds live in a loop the model cannot reach.
  → this patch is **interim**; the durable bound is a hook + on-disk counter (§4).
- **Finding-identity/novelty is UNSOLVED by string comparison** (`reconcile_gap_records.py` difflib
  @0.85: **0 merges on 2,491 pairs**; a true duplicate scored 0.338). → novelty must never sit on the
  safety-critical path (this is the v1→v2 fix).

---

## 2. RECOMMENDED PROMPT PATCH (261 words — insert into Step 1's plan-check loop, after the plan-size-governor bullet)

> **Analysis→execution transition — pick exactly one after every failed plan-check round.** After each
> `LOOP_GATE: PLAN_FAIL`, before dispatching another plan-check or a Coder, select ONE of
> `CONTINUE_PLAN_CHECK` / `STOP_PROSE_ANALYSIS` / `CUT_SCOPE` / `EXECUTE_PROOF` / `ASK_USER`. All five
> REDIRECT; none skips Test-writer, Coder, the independent Verifier, or live smoke. CONTINUE is the fail-safe.
>
> **Tier 0 — fail-safe, dominates all.** If this round holds ANY still-open implementation-blocking
> finding — DESIGN, LOGIC, SECURITY, CONCURRENCY, ORACLE, COVERAGE, or finite-state — choose
> **CONTINUE_PLAN_CHECK**, revise per the `gap_type` branch, and re-check. "Open" is independent of
> novelty: a blocking finding that recurs because its prior fix did not clear it is still open — never
> route a blocking finding to STOP/CUT/PROOF because it is "not new," a "refinement," or "probably
> minor." Unsure about kind, severity, OR novelty ⇒ CONTINUE. Zero findings recorded after a PLAN_FAIL
> ⇒ CONTINUE (extraction failed, not clean). Only `plan_size_governor.py` (artifact size), never a
> finding's novelty, may authorize a cut.
>
> **Only if NO open blocking finding exists this round:**
> 1. `plan_size_governor.py` → `SHIP_NARROW_PLAN` ⇒ **CUT_SCOPE**: cut to the declared MVP boundary,
>    defer cut ACs to `hardening_ledger.json`, run `spec_revision_diff.py --check-ac-inventory`, fresh
>    plan-check on the smaller spec.
> 2. `plancheck_saturation.py` → `STOP_PROSE_REVIEW` ⇒ **STOP_PROSE_ANALYSIS**: carry its `coder_notes`
>    verbatim; `verify.py`'s build/`tsc` gate is the oracle.
> 3. A residual FACTUAL premise provable now by an existing surface — exported? wired? typechecks?
>    live? ⇒ **EXECUTE_PROOF** (`verify.py`, `grep`/AST, `gate_contract_registry.py`); fold the result
>    in. Never "prove" a race/oracle/wiring class with a surface blind to it.
> 4. A product/scope/authority decision ⇒ **ASK_USER** (never wording). No authenticated reply ⇒ record
>    `ASK_UNANSWERED`, REPAIR/CONTINUE, never terminate.
> 5. Else leftovers are all verified-cosmetic ⇒ **STOP_PROSE_ANALYSIS**: carry verbatim as Coder notes.
>
> Every branch still ends Test-writer → Coder → independent Verifier (`LOOP-M8/M9`) → live smoke.

**The v1→v2 change (the fix the Verifier required):** v1 gated the CONTINUE fail-safe on
`novelty ∈ {NEW, UNKNOWN}`, so a blocking finding *confidently* mislabeled `REFINEMENT_OF_PRIOR` fell
through to CUT/STOP. v2 makes **any open implementation-blocking finding ⇒ CONTINUE, regardless of
novelty**, and lets **only `plan_size_governor` (artifact size) authorize a cut**. Novelty is demoted
off the safety path — exactly where the measured evidence says the unreliable signal belongs.

---

## 3. DECISION TABLE

| # | Round's finding profile (inputs) | Decision | Next concrete action |
|---|---|---|---|
| 0 | ANY still-open implementation-blocking finding (DESIGN/LOGIC/SECURITY/CONCURRENCY/ORACLE/COVERAGE/finite-state) — **new OR recurring-unfixed**; or unsure about kind/severity/novelty; or zero findings recorded after a PLAN_FAIL | **CONTINUE_PLAN_CHECK** (fail-safe) | Revise on the finding via its `gap_type` branch (`orchestrator.md:152-155`); dispatch next plan-check round. Governors still run for hygiene; they never override Tier 0. |
| 1 | No open blocking finding; `plan_size_governor.py` → `SHIP_NARROW_PLAN` | **CUT_SCOPE** | Cut to declared MVP boundary; defer cut ACs to `hardening_ledger.json` `deferred_ac_ids`; run `spec_revision_diff.py --check-ac-inventory` (nonzero = hard block; **must also refuse to defer any AC carrying a blocking finding** — §5); **fresh plan-check on narrowed spec**. |
| 2 | No open blocking finding; `plancheck_saturation.py` → `STOP_PROSE_REVIEW` | **STOP_PROSE_ANALYSIS** (binding-saturation instance) | Carry checker `coder_notes` verbatim as Coder notes; proceed Test-writer → Coder; `tsc --noEmit`/build in `verify.py` is the oracle. |
| 3 | No open blocking finding; residual is a **factual premise** provable now by an existing surface (exported? imported? wired? existing file typechecks? URL live? commit happened?) **and the surface can actually observe that class** | **EXECUTE_PROOF** | Run the matching surface: `verify.py` (test/`tsc`/live-smoke), `grep`/AST, `gate_contract_registry.py` (is-it-wired), `reality_gate.py`/`live_smoke.py`. Fold the machine result into the spec; proceed (or CONTINUE if the proof surfaced a new blocking finding). |
| 4 | No open blocking finding; residual is a **product/scope/authority** decision (MVP contents, desired behavior, who authorizes) — not wording, not proof-answerable | **ASK_USER** | Post the specific decision to the human. No runtime-authenticated reply → record `ASK_UNANSWERED`, take the deterministic fallback **REPAIR/CONTINUE** (never CUT); never terminate. |
| 5 | No open blocking finding; governors silent; nothing provable-now; no authority question; **every** leftover is verified wording/citation/section-ref/formatting/schema-polish/prior-round-refinement/impl-note/compiler-catchable-binding | **STOP_PROSE_ANALYSIS** (general fail-through) | Stop prose rounds; carry leftovers verbatim as Coder notes; proceed Test-writer → Coder → independent Verifier → live smoke. |

Every row's tail is identical: **Test-writer → Coder → independent post-build Verifier (`LOOP-M8`/`LOOP-M9`) → live smoke (6.5/6.6).** No row weakens plan-check-before-Coder, Test-writer-before-Coder, the independent Verifier, or live/runtime proof.

### Three cases where another PROSE round is FORBIDDEN
- **EXECUTE_PROOF (the `cod_state` case).** Rounds keep re-litigating "will the COD hook enforce the cut?"; no round produces a *new* defect. An AST extractor settles it in one run: `gate_contract_registry.py` → `cod_state.py = UNINSTALLED_ORPHANED` (zero callers). Prose is forbidden because a machine answers "is it wired?" definitively.
- **STOP_PROSE_ANALYSIS (binding-saturation).** Three consecutive rounds flag the same "prose describes the import but never shows the literal `import` line" signature, `compiler_catchable=true`, zero `[LOGIC]/[CONCURRENCY]/[SECURITY]`. `plancheck_saturation.py` → `STOP_PROSE_REVIEW`; carry verbatim as Coder notes — `next build`/`tsc` catches them for free.
- **CUT_SCOPE (over-boundary artifact).** A spec that declared `MVP_MAX_ACS: 8` now addresses 14 ACs, no new blocking finding, `plan_size_governor.py` → `SHIP_NARROW_PLAN`. Cut to 8, defer 6 (none carrying a blocking finding), fresh plan-check on the smaller spec. Reviewing the bloated artifact harder just multiplies churn.

### Three cases where another PLAN-CHECK round is STILL REQUIRED (CONTINUE wins)
- **Late-round SECURITY finding — the exact false-stop this must never make.** After ~10 stable rounds, an ordinary re-verification surfaces a new cross-org access defect (the AC19/round-30 pattern). New blocking SECURITY → CONTINUE, **even if it is honestly labeled `REFINEMENT_OF_PRIOR`** (v2: novelty is off the safety path). Flat hazard + 15:0 backtest forbid a stop here.
- **Late-round CONCURRENCY / finite-state finding.** The state-transition-table lens finds a *missing row* — an entire unaddressed state with no defined behavior (CLOSED-then-recurred; ops-clock dual-open). New finite-state/CONCURRENCY blocking finding, structurally invisible to narrative review → CONTINUE. A stop ships the silent state.
- **Recurring-unfixed blocking finding.** Round N's LOGIC gap was "fixed," round N+1 shows the fix was inadequate; honest label is `PARAPHRASE_OF_PRIOR`, `blocking=true`. Still open → CONTINUE. (v1 sent this to CUT/STOP — the confirmed bug.)

---

## 4. FALSE-STOP RISK ANALYSIS (what the adversarial pass found)

The independent Verifier returned **PLAN_FAIL**; the Fable challenger independently flagged the same
root. Both are now closed or bounded. This is the deliverable's most important section: a stop control
is only as good as its worst false-stop.

**CONFIRMED & FIXED (Verifier-authoritative):**
1. **Confident-wrong novelty (root; Verifier primary + Fable #1).** v1's fail-safe was gated on
   `novelty ∈ {NEW,UNKNOWN}`; a new blocking finding confidently mislabeled `REFINEMENT_OF_PRIOR`
   bypassed CONTINUE → `CUT_SCOPE`/wrong-oracle `EXECUTE_PROOF`. **Fixed in §2/§3:** any open blocking
   finding ⇒ CONTINUE for all novelty values; the novelty→CUT branch is deleted.
2. **Silenced deferred AC (Verifier defense-in-depth + Fable #5).** `spec_revision_diff.py
   --check-ac-inventory` is inventory-accounting only (Verifier read the source: no blocking-ness
   guard), so a deferred blocking AC is "accounted for" and never re-reviewed. **Fix (code, §5):** a
   hard block that refuses to defer any AC carrying a `BLOCKING_KINDS` finding.
3. **EXECUTE_PROOF laundering (Verifier secondary + Fable #2).** A green result from a surface blind to
   the finding's class (a race under `tsc`, data-wiring under `grep`) reads as *resolution*. **Fixed
   two ways:** the primary fix already routes every blocking finding to CONTINUE before Step 2 can
   fire; and the harness (§5) adds a `finding_kind × proof_surface` compatibility matrix.

**FOLDED INTO THE HARNESS AS DEFENSE-IN-DEPTH (Fable advisory, not yet Verifier-confirmed):**
4. **BINDING must preserve gate 10's compiler-invisible exclusions.** `exception_handling`,
   `data_wiring`, `ui_default` are compiler-AND-test-invisible; they must be `BLOCKING_KINDS`
   (⇒ CONTINUE), never blanket stop-eligible. The harness carries `compiler_catchable` + `exclusion`
   fields (matching `plancheck_saturation.py`) and only a `compiler_catchable ∧ exclusion=none` BINDING
   is stop-eligible.
5. **Down-tag policing (rule x, symmetric).** A SECURITY/CONCURRENCY/ORACLE finding marked
   `blocking=false` requires a stated justification field, else `INVALID_TAGGING` — so escaping
   CONTINUE by down-tagging *severity* is visible.
6. **Single-round STOP window.** General `STOP_PROSE_ANALYSIS` requires ≥2 consecutive all-cosmetic
   rounds (or a completeness attestation) — reusing the window discipline that lives in the narrow
   Tier-2 tool, so one shallow/truncated round cannot end prose review.
7. **ORACLE circularity.** ORACLE-kind findings may never route to STOP or to proof-via-the-indicted
   suite; force CONTINUE/ASK until the oracle is re-derived (gate 9).

**IRREDUCIBLE RESIDUAL (stated honestly).** After the fix, the control trusts the orchestrator's `kind`
+ `implementation_blocking` tags. Rule x catches `blocking=true ∧ cosmetic-kind`; #5 catches an
unjustified severity down-tag on the high-risk kinds. But if **both** the kind and the blocking flag are
wrongly down-tagged with a plausible justification, no *per-round* rule catches it — by construction, a
prompt-layer control cannot. That residual is bounded, not by this control, but by the gates it never
weakens: the **independent post-build Verifier + live smoke**, and ultimately **kind-diversity** (a
mechanical detector with flat detection probability — the synthesis's recommendation #3). This is the
correct place for the residual to land, per the law: semantic self-report is never the terminal
authority.

---

## 5. WHAT TO IMPLEMENT LATER AS CODE (`plancheck_transition.py` + two edits)

The prompt patch **raises the floor**; it is not a bound. A rule in `orchestrator.md` lives in the
prompt layer — Oga can silently not run it, and nothing outside Oga's context notices. The living proof
is in this very repo: `cod_state.py` is exactly the hook-shaped machinery a real bound needs, and it is
`UNINSTALLED_ORPHANED`. A durable control needs three code pieces:

**(a) `loop-team/harness/plancheck_transition.py`** — a deterministic, stdlib-only, side-effect-free
reducer matching the house CLI contract (`json.dumps(sort_keys=True)` to stdout; exit 0 for any
computed verdict incl. `INVALID_TAGGING`; exit 2 for usage errors; never exit 1).

*Record schema* (one Round record per invocation):

| Field | Grain | Type | Values |
|---|---|---|---|
| `round` | round | int | ≥ 1 |
| `target_revision` | round | int | ≥ 0 |
| `finding_kind` | finding | enum | DESIGN\|LOGIC\|SECURITY\|CONCURRENCY\|ORACLE\|COVERAGE\|FINITE_STATE (blocking) · WORDING\|CITATION\|SECTION_REF\|FORMATTING\|SCHEMA_POLISH\|REFINEMENT\|IMPL_NOTE\|BINDING (stop-eligible) |
| `implementation_blocking` | finding | bool | required, no silent default |
| `proof_surface` | finding | enum | NONE\|TYPECHECK\|BUILD\|TEST\|GREP_AST\|LIVE_SMOKE\|RUNTIME_PROBE\|HARNESS |
| `novelty_class` | finding | enum | NEW\|PARAPHRASE_OF_PRIOR\|REFINEMENT_OF_PRIOR\|UNKNOWN *(audit-only in v2; not on the safety path)* |
| `recommended_transition` | finding | enum\|null | advisory input only; the core never branches on it (output key is `verdict`) |
| `signature` | finding | str | non-empty |
| `compiler_catchable` | finding | bool | required iff `finding_kind=BINDING` (gate-10 operational test) |
| `exclusion` | finding | enum | none\|exception_handling\|data_wiring\|ui_default (BINDING only) |

*Precedence (round → `verdict`), safe-by-default:*
0. **Validation** → `INVALID_TAGGING` (absolute priority). Includes rule x (`blocking=true ∧
   kind∈STOP_ELIGIBLE`) **and** its mirror (`blocking=false ∧ kind∈{SECURITY,CONCURRENCY,ORACLE}`
   without a justification) **and** a BINDING with `compiler_catchable=false` or an `exclusion≠none`
   claiming stop-eligibility.
1. **Any** finding `implementation_blocking=true ∧ kind∈BLOCKING_KINDS` → **`CONTINUE_PLAN_CHECK`**
   (wins unconditionally, **all** novelty values — the zero-new-finding clause, v2-widened). A
   `data_wiring`/`exception_handling`/`ui_default` BINDING is treated as blocking here.
2. **Any** finding `proof_surface≠NONE` **and** `(finding_kind × proof_surface)` compatible → **`EXECUTE_PROOF`**.
   (Incompatible pairs — CONCURRENCY/ORACLE/COVERAGE/data-wiring via TYPECHECK/BUILD/GREP_AST — coerce
   `proof_surface→NONE`.)
3. **All** findings (≥1) `kind∈STOP_ELIGIBLE_KINDS` **and** the ≥2-consecutive-cosmetic-round window is
   satisfied → **`STOP_PROSE_ANALYSIS`**.
4. Else → **`CONTINUE_PLAN_CHECK`** (safe default; also empty `findings`). **No novelty→CUT branch.**

`CUT_SCOPE` and `ASK_USER` are **not** computed by this reducer: `CUT_SCOPE` is owned by
`plan_size_governor.py` (artifact size), and `ASK_USER` has no honest machine signal. Output is
`{verdict, round, target_revision, reasons[], routing[] (1:1 per finding, nothing dropped), coder_notes[]}`.

**(b) Edit `spec_revision_diff.py --check-ac-inventory`** — add a hard-block (nonzero exit) that
refuses to treat any AC as accounted-for-by-deferral when that AC carries a `BLOCKING_KINDS` finding.

**(c) The tamper-proof bound** — a PreToolUse-style hook + durable on-disk counter/capability
**outside Oga's context** (the shape `cod_state.py` already implements) that consumes a one-use
transition capability for the actual matching next dispatch, and a `MAX_ITERS`→escalate-to-human counter
as the sole terminal authority. This is what converts the reducer from advice into a bound; it is the
same seam the orphaned COD hook was meant to fill.

**The genuinely hard part a harness cannot finesse:** `novelty_class` is not computable by string
comparison (`reconcile_gap_records.py`: 0 merges on 2,491 pairs). v2 removes novelty from the safety
path precisely so the harness does not depend on solving it; it remains an audit field until a real
novelty oracle (or human attestation) exists.

## 6. Is pydantic the solution to this? — No.

Pydantic is a data-**validation** library. It can enforce the record's **shape** (enum membership,
required fields, `bool` is `bool`) — i.e. Step-0 checks (i)–(ix). It **cannot**:
- make the **decision** (is this finding implementation-blocking? is there a cheaper proof surface? is
  it a genuine new defect or a paraphrase of last round?) — that is the precedence reduction, not a schema;
- express the **cross-field semantic** rule x (`blocking=true ∧ cosmetic-kind → invalid`) as anything
  more than a custom validator you write yourself — at which point pydantic is holding *your* logic, not
  supplying it;
- classify `novelty_class` — the actually hard part — at all;
- provide the **tamper-proof bound** (hook + durable counter outside Oga's context), which is what makes
  the control real rather than advisory.

So pydantic is, at most, an implementation detail of the reducer's shape-validation half — never the
control. (Distinct question: "Pydantic AI Harness + Temporal" appears on the runtime-benchmark
candidate list in `FRAMEWORK_OWNER_CONTINUATION_RECEIPT_2026-08-02.md`, but it is **UNADMITTED /
needs-benchmark-first** — a different matter from "use the pydantic library to validate a record," and
not a shortcut around any of the above.)

## 7. Exact next prompt to run, if we choose to implement

> Loop-Team build. Target repo: this repo (`loop-engineering`), `REPO_HEALTH_CLASSIFICATION=new-capability`.
> Goal: implement `loop-team/harness/plancheck_transition.py` and its edits per
> `research/2026-08-04-plancheck-transition-control.md` §5. Scope (MVP): the deterministic reducer
> (schema + precedence 0-4 exactly as specified, incl. rule x + its mirror + the BINDING
> `compiler_catchable`/`exclusion` gate-10 test + the `finding_kind × proof_surface` compatibility
> matrix), stdlib-only, house CLI contract (stdout JSON, exit 0/2, never 1). Plus the
> `spec_revision_diff.py --check-ac-inventory` blocking-AC hard-block (edit b). Defer the PreToolUse
> hook + durable counter (edit c) to a separate slice — note it in `hardening_ledger.json`.
> `MVP_MAX_LINES: 400`. Run the full loop: **plan-check the spec before any Coder**; Test-writer writes
> the adversarial table (every precedence branch, every INVALID_TAGGING rule, the confident-wrong-novelty
> case from this doc's §4.1 must go to CONTINUE, the class×surface laundering case must NOT resolve, a
> deferred blocking AC must hard-block) **before** the Coder; independent Verifier confirms against the
> spec; do not weaken any existing gate. Then apply the ≤300-word prompt patch (§2) to `orchestrator.md`
> Step 1 as a separate, full-plan-check-gated edit.
