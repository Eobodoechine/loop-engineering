# H-SUBAGENT-MASKING-1 full closure — architecture design brief

Date: 2026-07-03
Mode: A/D hybrid (design-gap survey, not a spec)
Trigger: `fix_plan.md` `H-SUBAGENT-MASKING-1` candidate fix (2) ("two-phase gate
restructuring") — orchestrator.md's DESIGN-gap rule requires checking for a BETTER
option before rubber-stamping the one already on the table.

## Sources consulted (real, opened)

- `hooks/loop_stop_guard.py` (1260 lines) — read in full, both halves (lines 1-989 and
  990-1260 via a second Read call after truncation).
- `hooks/micro_step_gates.py` (432 lines) — read `_activation()` (170-207) and `run()`
  (239-338) in full; confirmed the `_LAST_ACTIVATION` module-level cache mechanism and
  the non-idempotent `_save_sigs()` mutation inside `run()`.
- `hooks/subagent_stop_gate.py`, `hooks/commit_scope_scan.py` — sizes/imports checked
  (454 and 170 lines respectively); `commit_scope_scan.find_commit_scope_violations` is
  the shared, already-extracted detection function both Layer 1/Layer 2 lean on.
- `fix_plan.md` — `H-SUBAGENT-MASKING-1` (2276-2352), `H-SUBAGENT-COMMIT-GATE-1` (2353+,
  confirms Layer 1's placement rationale: "immediately after the _TOOL_USES/_TOOL_RESULTS
  construction... and strictly BEFORE line ~414 (ROLE_OR_HARNESS_EDIT, the FIRST existing
  sys.exit(2)-capable gate)" — i.e. Layer 1's priority-first placement was a deliberate,
  plan-checked design decision, not an accident), `H-REVIEW-COMMIT-1` closure entry (the
  `_LAST_ACTIVATION` module-cache precedent cited by orchestrator.md's own DESIGN-gap rule).
- `runs/2026-07-03_h-subagent-masking-1/specs/spec.md` (173 lines, full read) — the narrow,
  NOT-being-shipped interim fix; grounds exactly which lines/behavior candidate (1) touches
  so the full-closure design brief doesn't duplicate or contradict it.
- `loop-team/orchestrator.md` line 70 — the DESIGN-gap handling rule itself, plus its own
  cited precedent (`H-REVIEW-COMMIT-1`'s module-level-cache 3rd option).
- Django documentation, `https://docs.djangoproject.com/en/6.0/ref/forms/validation/`
  ("Raising multiple errors" section) — fetched directly, quoted below. Real, groundable
  prior art for "run every check, aggregate, then decide" in a mainstream, widely-used
  Python library.
- `research/claude-cookbooks-review-2026-07-02.md`, `research/claude-cookbooks-session-coordination-2026-07-02.md`
  — grepped for validator/chain/gate/policy patterns; nothing in the already-reviewed
  cookbook content matches this exact "N independent policy checks, evaluate all, decide
  once" shape (the cookbook's own patterns/agents content is chaining/parallelization/
  routing of LLM calls, not validation aggregation — see below, "prior art" section).
- WebSearch: `anthropics claude-cookbooks patterns validators chain multiple checks
  aggregate errors` — returned only the chaining/parallelization/routing agent patterns,
  none of which is this pattern; recorded as a genuine miss, not silently dropped.

## The real file's actual shape (grounding for every design below)

`loop_stop_guard.py` is NOT a clean list of independent functions today. It is one flat
module-level script with FIVE materially different gate shapes, in this order:

1. **Layer 1 flag-file gate** (~93-247): wrapped in its own outer
   `try/except Exception` (fail-open) with an INNER `try/except` around JSON-parse
   (malformed-content handling, AC13b) — already exactly the "two try/except layers"
   shape a two-phase refactor would need to preserve per-gate.
2. **Blob-regex gates** (`ROLE_OR_HARNESS_EDIT` ~570-585, `FEATURE` ~587-601): NOT
   wrapped in any try/except — pure regex + boolean logic, no I/O, so these are the
   lowest-risk to convert.
3. **PLAN_PASS gate** (~603-721): NOT wrapped in a gate-level try/except (bare glob +
   time.time() + `_os.remove` calls, unguarded except for the individual `except OSError:
   continue`/`pass` around each file op) — mutates state (deletes stale
   `.verifier_pass` flags) as a side effect of running its OWN detection.
4. **Research gate + hygiene gate + adjacency gate** (~723-1050): mix of pure-logic
   (research gate, hygiene gate) and one gate (`_hyg_known_lines()`) that does disk I/O
   (globs and reads every `roles/*.md` + `orchestrator.md`) but returns `None`
   (fail-open) rather than raising on an unreadable role surface — no unguarded raise
   risk, but real disk I/O cost that would now run on EVERY invocation instead of only
   when reached.
5. **Micro-step-gates block** (~1052-1082): wrapped in its own outer
   `try/except Exception` (fail-open) and delegates to `micro_step_gates.run(data)`,
   which is a SEPARATE MODULE with its own non-trivial internal state:
   - `_activation()` sets the module-level global `_LAST_ACTIVATION` **as a side
     effect**, cached specifically so the LATER commit-scope gate (item 6 below) can
     read it without re-resolving.
   - `run()` calls `_save_sigs(session_id, sigs)` (line 277) which **appends this
     turn's failing verify signatures to a persisted file and truncates to the last
     20** — this is explicitly documented as consume-once: "gate 3 must consume each
     red verify exactly ONCE — the transcript is re-scanned on every Stop, so appending
     from the full history would double-count earlier turns." This is the ONE clearly
     non-idempotent, order-and-frequency-sensitive mutation in the whole file.
   - `run()` also shells out to `git diff`/`git log` (subprocess calls with timeouts)
     and, when code is dirty, runs a **live pytest invocation** (`_testmon_gate`,
     up to `PYTEST_TIMEOUT`) — real wall-clock cost, not free "just also evaluate it."
6. **Commit-scope gate** (~1084-1257, "H-REVIEW-COMMIT-1" + "Layer 2"): wrapped in its
   own outer `try/except Exception` (fail-open). Its detection logic **explicitly
   depends on the micro-step-gates block having ALREADY RUN**: `_rc_target` is resolved
   by reading `_msg_mod._LAST_ACTIVATION`, "the module-level cache set inside
   `_activation()`... this gate runs strictly after the micro-step-gates block above
   (whose own `run(data)` call, and therefore `_activation()`, already ran)." This is
   the file's one explicit, comment-documented **precondition-on-execution-order**
   dependency — exactly the kind of thing the task brief asked me to look for.

**Key finding: the file already has an internal precedent for exactly the "resolve
once into a shared cache, let a later check read it" pattern the two-phase design would
need** — `_LAST_ACTIVATION`. This is also the literal 3rd-option precedent
`orchestrator.md` cites for the DESIGN-gap rule itself (`H-REVIEW-COMMIT-1`).

## Candidate designs

### Candidate 1 — Two-phase restructuring (the one already on the table)

**Description, grounded in the real file:** every one of the 8 or so gate bodies above
becomes a function `def _gate_X(ctx) -> Optional[Verdict]` (or returns `None` on no
violation), called from one driver loop near the top-to-bottom order they already run
in today. No gate calls `sys.exit(2)` directly anymore. After all gates have run and
reported, a single block at the end picks the first (or highest-priority) violation and
calls `sys.exit(2)` once, printing that gate's message.

**Pros (specific to this codebase):**
- Fully closes H-SUBAGENT-MASKING-1 in the general case, not just for Layer 1 vs Layer 2
  — ANY gate N's early exit today can mask ANY gate M>N's independent finding, and this
  is the only design that eliminates that class entirely, for every current and future
  gate pair, not just the one pair (Layer 1/Layer 2) the bug was filed against.
- The file already contains ~4 separate outer `try/except Exception: fail-open` wrappers
  (Layer 1, micro-step-gates, commit-scope) that would map cleanly onto "gate function
  bodies," so the refactor's shape is not inventing a new idiom, it's promoting an
  existing one.

**Cons (specific to this codebase, not generic):**
- **Touches every gate's control flow**, including the two with real, order-dependent
  side effects: `micro_step_gates.run()`'s `_save_sigs()` append-and-consume (would now
  run even on turns where an earlier gate — say the FEATURE gate — already found a
  blocking violation; today it never reaches that far) and the commit-scope gate's hard
  dependency on `_msg_mod._LAST_ACTIVATION` having been set by a PRIOR gate's run. A
  naive "call every gate function unconditionally in a loop" breaks this — you'd have to
  keep the micro-step-gates call BEFORE the commit-scope gate call even in the new
  design, i.e. the "two-phase" framing undersells that gate ORDER still matters for
  correctness, only the EXIT is deferred. The brief's own framing ("evaluate all gates,
  defer exit") is subtly incomplete unless this ordering constraint is called out
  explicitly in the eventual spec.
- **Real, uncontained cost increase.** Today, if the FIRST gate (Layer 1) fires, the
  turn exits in ~milliseconds — none of the later gates run, including the micro-step
  gate's live `pytest --testmon` subprocess call (bounded by `PYTEST_TIMEOUT`, which is
  a real, possibly multi-second cost) or `_hyg_known_lines()`'s glob+read of every
  `roles/*.md`. Two-phase means EVERY Stop-hook invocation now pays the FULL cost of
  EVERY gate, every time, even on a turn that was always going to block on the very
  first check. For a hook that fires on every single agent Stop, this is a real,
  measurable latency regression, not a hypothetical one — `_testmon_gate` alone can run
  a live test suite.
- **`_save_sigs()`'s double-count risk is real, not theoretical.** If two-phase means
  the micro-step-gates block still runs (to collect its verdict) even when an earlier
  gate already found a blocking violation, the append-and-truncate-to-20 mutation still
  happens on a turn that, under today's semantics, would never have reached it. This
  doesn't corrupt data (append is still append), but it changes the stall-detector's
  effective sample rate — a session with many early-gate violations would accumulate
  micro-step-gate signature history faster than today, which could change WHEN gate 3
  ("3 consecutive same signature") fires, in a way nobody explicitly decided.
- **Priority-vs-report-all ambiguity is unresolved by the name "two-phase."** Layer 1
  was deliberately placed FIRST/highest-priority per H-SUBAGENT-COMMIT-GATE-1's own
  spec ("this is before EVERY existing gate that can exit early... This ensures a real
  `.commit_violation` flag is never silently skipped merely because some OTHER gate
  happens to fire first"). If two-phase changes the OUTPUT from "show the
  highest-priority violation" to "show every violation found," that is a bigger,
  separate semantic change (arguably a feature — it's literally what closes
  H-SUBAGENT-MASKING-1 — but it needs to be a stated, deliberate AC, not an implicit
  side effect of "defer all exits").
- Biggest surface-area/regression-risk design of the four: touches every existing gate's
  control flow in a file that already has 153+ passing tests
  (`hooks/test_loop_stop_guard.py`) written against today's early-exit behavior and
  exact stderr wording per gate — a real re-test burden, not a drop-in change.

### Candidate 2 — Registry/plugin pattern (collect-all wrapper, gates keep their bodies mostly intact)

**Description, grounded in the real file:** instead of hand-rewriting every gate's
control flow into a return-a-verdict function immediately, wrap each gate's EXISTING
body (largely unchanged) in a small adapter that catches the `SystemExit` it would have
raised, records it as a "would-have-exited" verdict, and continues to the next gate. A
`_GATES = [gate_l1, gate_role_harness, gate_feature, gate_plan_check, gate_research,
gate_hygiene, gate_adjacency, gate_micro_step, gate_commit_scope]` list is iterated by
one driver; the driver still calls each gate function in the SAME order as today
(preserving the `_LAST_ACTIVATION` ordering dependency automatically, since it's just
"call them in this list order"), catches `SystemExit(2)` from each, records
`(gate_name, message)`, and after the last gate, if any fired, prints ALL of them (or
just the first, by priority) and exits once.

**Pros (specific to this codebase):**
- **Smallest diff of the three real options.** Each gate's existing, already-tested
  logic stays almost byte-identical — only its `sys.exit(2)` call sites change to
  `raise _GateViolation(msg)` (or similar) instead. The 153+ existing tests
  (`test_loop_stop_guard.py`) mostly still pass because they assert on stderr CONTENT
  and exit CODE, not on which Python statement produced them — this needs verification
  per-test but is a much smaller blast radius than Candidate 1's full function-signature
  rewrite.
- **Preserves the file's existing, working ordering-dependency pattern automatically**
  — because gates still run in list order, `_LAST_ACTIVATION` being set by the
  micro-step-gates entry before the commit-scope entry runs is preserved by construction,
  not something the spec has to re-derive and enforce.
- Still fully closes H-SUBAGENT-MASKING-1's general case (every gate gets to report,
  regardless of an earlier gate's violation) — same closure guarantee as Candidate 1.
- Gives a natural, low-risk hook for priority-based reporting: iterate `_GATES` in
  today's order, and REPORT (stderr + exit 2) only the FIRST one that fired — this
  preserves "Layer 1 is highest priority" EXACTLY as originally spec'd, while still
  having evaluated every later gate (so a future extension — e.g. surfacing "N other
  violations also found" the way the narrow interim fix does for Layer 1/Layer 2
  specifically) is a small additive change, not a redesign.

**Cons (specific to this codebase):**
- Doesn't solve the cost-increase problem any better than Candidate 1 — every gate
  still runs (including the live pytest subprocess call) on every invocation now,
  since "collect all, then decide" inherently means no more short-circuiting.
- Using `SystemExit` as an internal control-flow signal inside a `try/except SystemExit`
  is a slightly unusual pattern (normally `sys.exit()`/`SystemExit` is reserved for
  actually terminating the process) — every existing gate's outer
  `except SystemExit: raise` re-raise clauses (Layer 1 and the commit-scope gate both
  have one, specifically to let a REAL exit propagate past their own fail-open
  `except Exception`) would need to be re-audited, since under this design a gate's
  "intentional violation exit" and its outer wrapper's "let real exits through" clause
  would now be catching/re-raising the SAME exception type for two different purposes,
  which is exactly the kind of subtle bug this project's own plan-check discipline
  (round-by-round adversarial review) exists to catch. Slightly higher cognitive/
  correctness risk than an explicit return-value contract (Candidate 1's or 3's).
- Still requires touching every gate (to swap exit-call-sites), just with a smaller
  diff per gate than Candidate 1's full function-extraction.

### Candidate 3 — Ordered check-list with same-invocation short-circuit preserved, but ALL checks still evaluated for reporting (the brief's own option (b))

**Description, grounded in the real file:** keep each gate's detection logic exactly
where it is (same order, no function extraction at all — the file's current flat
top-to-bottom shape is preserved), but change ONLY the OUTPUT contract: instead of each
gate calling `sys.exit(2)` immediately on ITS OWN violation, each gate appends
`(gate_name, message)` to a shared, module-level `_VIOLATIONS` list when it detects a
violation, and CONTINUES to the next gate (no early return, no early exit) — same
effect as candidates 1/2, but implemented as the MINIMAL textual diff: every
`sys.exit(2)` call site becomes `_VIOLATIONS.append((name, msg)); ` with no restructuring
of the surrounding detection code, no new function boundaries, no adapter, no
`SystemExit` reuse. At the very end of the file (where `sys.exit(0)` already lives today
at line 1260), replace the trailing `sys.exit(0)` with: if `_VIOLATIONS` is non-empty,
print the FIRST one (today's priority order, preserved verbatim since gates still run
top-to-bottom in file order) or all of them, then `sys.exit(2)`; else `sys.exit(0)`.

**Pros (specific to this codebase):**
- **Textually the smallest possible diff** — literally a find-and-replace of every
  `sys.exit(2)` call site (there are 9: lines 233, 585, 601, 721, 822, 888, 1050, 1062,
  1160, 1250 — 10 actually, recount needed at spec time) with an append, no other
  structural change anywhere. Zero new functions, zero new classes, zero new control-
  flow abstractions. This is meaningfully lower-risk than Candidates 1/2 for a
  security-relevant file with 153+ existing tests, because it changes the SMALLEST
  possible number of lines while achieving full closure.
- Preserves file order (and therefore the `_LAST_ACTIVATION` dependency, and the
  Layer-1-is-first priority convention) with ZERO extra reasoning required — nothing
  moves, nothing gets wrapped, nothing gets a new signature.
- Easiest to plan-check and easiest for a Test-writer to reason about: "does gate N's
  logic still run in the same place, does it still compute the same verdict, does the
  only-different thing (append vs exit) happen at exactly the old exit call site" is a
  mechanical, line-by-line diffable claim.

**Cons (specific to this codebase):**
- Does NOT solve the cost-increase problem (same as 1/2 — every gate still runs, full
  wall-clock cost every time, including `_testmon_gate`'s live pytest run).
- Does NOT solve the `_save_sigs()` double-count-rate concern (same as 1/2) — this is a
  general two-phase-family risk, not specific to any one of the three designs; it needs
  its own explicit AC regardless of which of 1/2/3 is chosen (see Risks section below).
- Uses a bare module-level global list (`_VIOLATIONS`) rather than a return-value
  contract — stylistically weaker than Candidate 1's per-function return values, though
  the file ALREADY uses several bare module-level globals this way (`_LAST_ACTIVATION`
  in the imported module, `_l1_fresh_reports`, etc.), so it is not introducing a new
  idiom, just extending an existing one.
- Reporting only the FIRST violation (to preserve Layer 1's priority) means this
  design, taken literally, does NOT by itself surface "gate M also found something" —
  it only guarantees gate M's finding is COMPUTED (added to `_VIOLATIONS`) even when
  gate N<M already fired, which closes the "silently never surfaced" half of the bug,
  but the reporting behavior (show first only, vs show all) is a decision this design
  leaves as open as the other two — see "priority vs report-all" note under Candidate 1.

### Candidate 4 — Do nothing further beyond the already-shipped narrow interim fix; treat full closure as low-value

**Description:** ship only candidate-fix (1) from `fix_plan.md` (surfacing "agent B's
status unconfirmed" for the ONE specific Layer-1/Layer-2 pair), and do not build a
general two-phase architecture at all, on the grounds that H-SUBAGENT-MASKING-1's
concrete blast radius is narrow (a same-turn dispatch race between two sub-agents both
committing raw `git commit`s to scope-listed files) and that the general fix's cost
(touching every gate in a security-relevant, 153-test file, plus a real latency
regression from losing short-circuiting on the hot path) may not be justified by the
narrow trigger.

**Pros:** zero additional regression risk beyond what's already shipped; zero latency
cost; the interim fix already converts "silent miss" into "visible uncertainty," which
is most of the harm-reduction value.

**Cons:** **explicitly rejected by the user** — the task brief states plainly "Nnamdi
has now said he wants FULL closure, not the narrow mitigation." Including this option
only for completeness/honesty (a real candidate exists and should be named, per the
role's "report what you dropped and why" discipline) — it is not a live recommendation
given the stated preference.

## Recommendation

**Candidate 3** (minimal-diff append-instead-of-exit, same file order, same functions,
report-first-by-file-order at the end) is the best fit for this specific codebase, for
three concrete reasons grounded in what was actually read:

1. It is the only one of the three real candidates that does NOT require re-deriving or
   re-proving the `_LAST_ACTIVATION` ordering dependency, because nothing about gate
   ORDER or FUNCTION BOUNDARIES changes — the commit-scope gate still runs textually
   after the micro-step-gates block, in the same file, in the same order, for the same
   reason it does today. Candidates 1 and 2 both introduce a NEW abstraction (function
   list / registry) whose correctness w.r.t. that dependency has to be independently
   re-verified — Candidate 3 sidesteps the need entirely by not disturbing what's
   already correct.
2. It is the smallest diff against a file that already has 153+ tests written against
   exact exit-call-site and stderr-content behavior — lowest realistic regression risk
   for a security-relevant hook, which matters given this project's own standing
   "accuracy over speed" instruction and its history of plan-check rounds catching real
   ordering/exception-scope bugs in this exact file (H-SUBAGENT-COMMIT-GATE-1's own
   round-2 finding was precisely an ordering contradiction of this flavor).
3. It preserves Layer 1's deliberately-first priority convention by construction
   (report the first entry in `_VIOLATIONS`, which is filled in file order) while still
   computing every other gate's verdict — so a natural, ADDITIVE follow-up (report
   "N other violations also detected: ..." the way the narrow interim fix does for one
   specific pair, generalized to all gates) becomes a small future increment, not a
   second rewrite.

Two things the eventual spec MUST treat as first-class ACs regardless of which
candidate is chosen (they are not optional cleanup, they are the real risk this
research surfaced):

- **The `_save_sigs()` double-count-rate question.** Explicitly decide and test: does
  `micro_step_gates.run()` still execute (and therefore still call `_save_sigs`,
  mutating the persisted stall-signature file) on a turn where an EARLIER gate already
  found a violation? Under today's semantics it never reaches that code. Under any
  full-closure design it will. This changes gate 3's ("3 consecutive same signature")
  effective sample rate in a way that needs an explicit decision (accept the changed
  rate, or special-case skip the micro-step-gates block's mutating half while still
  running its own detection for reporting purposes) — do not let this be an accidental
  side effect discovered post-hoc.
- **The latency/cost regression.** Every gate — most notably `_testmon_gate`'s live
  `pytest` subprocess call and `_hyg_known_lines()`'s disk scan of every `roles/*.md` —
  now runs on every single Stop-hook invocation, not just the ones that reach that far
  today. This is a real, user-visible latency change to a hook that fires on every
  agent Stop, not a theoretical concern; it should be measured (time the guard
  before/after on a representative transcript) and stated as an accepted or mitigated
  cost in the spec, not left implicit.

Priority ordering (report-first-by-file-order vs report-all) should also be an explicit
spec decision, not an implicit consequence of the refactor — recommend keeping
"report-first-by-file-order" (preserves the H-SUBAGENT-COMMIT-GATE-1 priority
convention exactly) as the default behavior, with a possible later, separately-spec'd
extension to "also list what else fired" generalizing the narrow interim fix's approach.

## Prior art

**Real, retrieved, sourced:** Django's form-validation `Field.run_validators()` /
`Form.clean()` machinery is a genuine, widely-deployed instance of the "run every check,
aggregate, decide once" pattern in mainstream Python. Fetched directly from
`https://docs.djangoproject.com/en/6.0/ref/forms/validation/` ("Raising multiple
errors" section):

> "If you detect multiple errors during a cleaning method and wish to signal all of
> them to the form submitter, it is possible to pass a list of errors to the
> `ValidationError` constructor... it is recommended to pass a list of `ValidationError`
> instances with `code`s and `params`."

And, on cross-field continuation after one field's own validator raises:

> "For any field, if the `Field.clean()` method raises a `ValidationError`, any
> field-specific cleaning method is not called. However, the cleaning methods for all
> remaining fields are still executed."

And `run_validators()` is documented as running "all of the field's validators and
aggregating all the errors into a single `ValidationError`" — i.e. per-field, Django
already does exactly the "run every validator, don't stop at the first, aggregate" thing
this design brief is evaluating for `loop_stop_guard.py`'s gates.

**Real, but a genuine miss (reported honestly, not padded):** WebSearch for
`anthropics claude-cookbooks patterns validators chain multiple checks aggregate
errors` returned only the cookbook's existing, ALREADY-catalogued
chaining/parallelization/routing agent patterns (`patterns/agents/basic_workflows.ipynb`)
— none of which is the "N independent policy checks, evaluate all, decide once"
pattern. The two existing internal dossiers on claude-cookbooks
(`research/claude-cookbooks-review-2026-07-02.md`,
`research/claude-cookbooks-session-coordination-2026-07-02.md`) were also grepped and
contain no matching pattern (their gate-adjacent content is a deterministic pre-pass
gating an LLM reviewer in a GitHub Actions workflow, and a two-tier CI trust gate for
fork-vs-internal contributors — neither is "multiple gates, evaluate all, decide once").
**Conclusion: no claude-cookbooks-specific prior art exists for this pattern; the
closest real prior art found is Django's form-validation aggregation, which was
directly fetched and quoted above, not fabricated.** A "chain of responsibility that
doesn't stop at first match" is a named, real design-pattern variant in general
software-engineering literature, but no specific canonical open-source Python
implementation of it (beyond Django's own validators, which already IS one) was
independently verified in this pass — flagging that as unconfirmed rather than citing a
generic pattern-name without a real source.

## Transfer-condition check (per Researcher role's Guardrails)

For the borrowed Django pattern: (a) it requires code-controlled sequential execution
of independent check functions with a shared error-accumulator — exactly what
`loop_stop_guard.py` already is (a single Python process executing gates in file
order); (b) this target context satisfies that requirement directly, no adaptation
needed; (c) the guarantee is STRUCTURAL, not instructional — once ported (append instead
of exit), there is no way for a gate to "forget" to report short of a bug in that gate's
own code, exactly as in Django's `run_validators()`. No instructional-compliance risk
identified for this specific mechanism.
