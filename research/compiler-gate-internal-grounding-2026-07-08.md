# Compiler-gate proposal: internal grounding against the real record (2026-07-08)

## Scope and method

This is a follow-up to `~/Claude/loop/research/spec-first-vs-code-first-ai-agent-builds-2026-07-08.md`
(read in full before starting this task). That doc's three unactioned findings (#1 mechanical
binding-bug detection, #2 relative-cross-reference anti-pattern, #6 "spec-anchored, code-coupled"
architecture) motivate three design questions handed to me. This document answers them by reading
the ACTUAL round-by-round record of the padsplit-cockpit Slice 6b plan-check loop and the current
state of every file the questions reference — no speculation, every claim below has a file path
and line number I read directly via the `Read`/`Bash`/`grep` tools in this session.

Files read in full or via targeted grep, all fresh off disk this session:
- `~/Claude/loop/loop-team/roles/researcher.md` (my own role brief)
- `~/Claude/loop/RUN.md`
- `~/Claude/loop/loop-team/orchestrator.md` (both halves — it truncates at 495 lines in one Read
  call; I read lines 1–495 and 496–589 separately)
- `~/Claude/loop/loop-team/DESIGN_CHECKLIST.md` (117 lines, full read — note: this file lives at
  `loop-team/DESIGN_CHECKLIST.md`, NOT at the repo root; a naive path guess would miss it)
- `~/Claude/loop/loop-team/roles/test_writer.md`, `roles/coder.md`, `roles/verifier.md` (full reads)
- `~/Claude/loop/loop-team/roles/adversarial_test_writer.md` (targeted: header + `## `/`### ` headings)
- `~/Claude/loop/fix_plan.md` lines 4900–5072 (the full `H-AC-ORACLE-TARGET-1` entry) and lines
  720–746 (`PSC-TSC-1`), plus grep sweeps for `tsc`, `H-BROWSER-UI-CHECK-MISSING-1`, anchor/
  cross-reference language across the whole file
- `~/Claude/loop/research/spec-first-vs-code-first-ai-agent-builds-2026-07-08.md` (full read)
- `~/Claude/loop/runs/2026-07-04_airbnb-calendar/plan_check_log.md` — **2550 lines, found via broad
  disk search** (`grep -rliE "slice.?6b"` across `~/Claude`), read in full across 4 `Read` calls
  (offsets 1, 1062, 1605, 2154)
- `~/.claude/agents/plan-check-verifier.md`, `verifier.md`, `coder.md`, `test-writer.md` (the actual
  custom-subagent-type frontmatter files — tool permissions, not just role-brief prose)
- `~/Claude/loop/loop-team/harness/verify.py` (targeted reads — header + `detect_node_runner`/
  `node_runner_argv` functions) and a full-file grep for `tsc|typecheck|next build|compile`

No sub-agents were dispatched for this task — I did every read/grep myself, per the "no
Agent/Task tool" instruction and the researcher.md sub-delegation ban.

---

## Q1 — Where does plan-check actually transition into binding-class findings, and is the "round 20-24" claim real?

**The run record exists and is real.** `~/Claude/loop/runs/2026-07-04_airbnb-calendar/plan_check_log.md`
is a genuine 31-round plan-check log (2550 lines) for padsplit-cockpit's Airbnb iCal calendar-sync
slice, matching the prior research doc's description exactly (5 parallel adversarial lenses per
round: state-completeness, concurrency-isolation, precision-of-instruction, state-transition-table,
regression-audit).

**The "round 20-24" shift-point claim in the dispatch prompt is NOT supported by the record —
say this plainly rather than assuming it.** Here is what the record actually shows:

### The binding/wiring bug class starts at round 16-17, not round 20

- **Round 16** (`plan_check_log.md:1183-1199`), state-completeness: `§B.3`'s `reservation.upsert`
  `create` clause omits the schema-required `orgId` field — confirmed against the real
  `web/prisma/schema.prisma` and `web/src/lib/db-rls.ts`. This is already a binding/schema-contract
  bug, one round before the hypothesized window opens.
- **Round 17** (`plan_check_log.md:1362-1379`), regression-audit — quoted verbatim: *"tracing WHERE
  each value in the create clause actually comes from... found the most severe bug of this whole
  process: `confirmationCode`, `checkIn`, `checkOut`, `threadId`, and `propertyId` are all bare,
  undeclared identifiers in §B.3's code block... Inserted verbatim: 5 TypeScript 'Cannot find name'
  compile errors."* The round's own header (`plan_check_log.md:1305-1308`) calls this **"the single
  most severe individual finding of the whole process."** This is the canonical binding-class bug
  the compiler-gate proposal is about — and it happens at round 17, three rounds before the
  hypothesized window even starts.

### The binding-class bug class recurs continuously through round 30, not just rounds 20-24

The log itself explicitly tracks recurrence of this exact bug class (undeclared identifier / missing
import / missing export directive) across rounds, in its own words:
- Round 22 (`plan_check_log.md:1801-1807`): `propertyId`/`icalExportUrl` bare identifiers.
- Round 23 (`plan_check_log.md:1838-1853`): **all four** failing lenses independently find `orgId`
  unbound in the same function — the log calls this *"a third-consecutive-round instance of 'fix
  some identifiers, miss another in the same function'"* (line 1836).
- Round 24 (`plan_check_log.md:1900-1909`): `syncAirbnbCalendar` called with no import anywhere.
- Round 26 (`plan_check_log.md:2081-2095`): `revalidatePath` called with no import — the log itself
  states *"the same 'identifier called, binding never shown' bug class already rated SEVERE four
  times in this run (rounds 17, 22, 23, 24)"* (line 2088-2089).
- Round 27 (`plan_check_log.md:2155-2167`): a whole new file's imports (`getSession`, `db`, `forOrg`,
  `logger`) never written down — *"despite this exact bug class already being rated SEVERE five
  times in this run (rounds 17, 22, 23, 24, 26)"* (line 2165-2167).
- Round 28 (`plan_check_log.md:2242-2253`): *"7th instance of this run's most persistent bug class"*
  — two more sibling files with the same gap.
- Round 29 (`plan_check_log.md:2302-2323`): `CalendarLinkForm` never exported/imported/rendered at
  all — unreachable dead code, converged on independently by two lenses.
- Round 30 (`plan_check_log.md:2415-2419`): regression-audit explicitly declares *"the missing-import
  bug class (8 prior instances) is genuinely exhausted this round."*

That is 9 explicit, self-tracked recurrences of the identical bug class spanning rounds 17 through
30 — a 14-round span, not a narrow round-20-24 window.

### Design/logic/security findings did NOT stop during this same window — the two classes were interleaved, not sequential

This is the part of the hypothesis most clearly falsified: real, non-binding design bugs kept
surfacing throughout the exact rounds where binding bugs were also recurring:
- **Round 19** (`plan_check_log.md:1508-1518`): a genuine, previously-unaddressed cross-tenant
  security gap — `propertyId` was client-submitted and never validated against the requesting org.
  Pure design/security, unrelated to compilation.
- **Round 20** (`plan_check_log.md:1609-1619`): a real React/Next.js framework-mechanism bug (Server
  Action return values don't reach rendered UI without `useActionState`) — an architecture-level
  finding, not something `tsc` alone would flag.
- **Round 21** (`plan_check_log.md:1684-1701`): a genuine TypeScript discriminated-union
  type-narrowing bug (`SyncNowResult` has no `status` field) — this ONE actually would be caught
  by a compiler, interleaved with the two above which would not be.
- **Round 30** (`plan_check_log.md:2438-2451`): the AC19 cross-org security-oracle bug — the exact
  incident that produced `H-AC-ORACLE-TARGET-1` — found at round 30, well after the hypothesized
  round-20-24 "transition."
- **Round 31** (`plan_check_log.md:2494-2502`): a second, structurally identical security-oracle gap
  (AC16), found the very next round.

So findings never cleanly shifted from "design/logic/concurrency" to "binding/wiring" at any single
point — both classes co-occurred from round 16/17 onward, and the two most consequential findings
of the ENTIRE 31-round process (the two security-oracle bugs that produced `H-AC-ORACLE-TARGET-1`)
landed at rounds 30 and 31, the very end.

### The real, explicit decision anchor is "rounds 24-31," decided by the human at round 31 — not a mechanical round-20 inflection

The closest thing to the hypothesis's claim that actually exists in the record is Nnamdi's own
words at the process-pivot decision (`plan_check_log.md:2523-2536`), quoted in full because it is
load-bearing:

> "**Process pivot decision (Nnamdi, this round):** 31 rounds is a lot. Reviewing the pattern
> across rounds 24-31: ~30+ findings, almost all concentrated in one ~700-line UI wiring section,
> and the large majority of them (missing imports, missing `export`/`'use client'`/`'use server'`
> directives, variable-naming collisions, un-shown literal code) are exactly what `next build`/`tsc`
> catches in seconds, for free, — we were hand-simulating a compiler by reading prose very
> carefully... The backend (§B.2/§B.3 concurrency/locking logic) converged genuinely early and
> stayed clean (7 consecutive rounds). The two real, non-mechanical findings this run's process
> caught that a compiler never could — AC19 (round 30) and AC16 (round 31), both cross-org
> test-assertion traps — are exactly what this adversarial process is FOR, and neither would have
> surfaced without it."

This is real, and it is a legitimate anchor — but it is **"rounds 24-31," stated retrospectively by
a human reviewing the whole arc**, not a mechanically-detected inflection at round 20. The
underlying bug class the pivot is about had already been recurring since round 17. **Verdict: the
dispatch prompt's "round 20-24" claim should be treated as unsupported by the primary source and
corrected to "the binding-class bug class first appears at round 16-17 and recurs continuously
through round 30; the explicit human stop-decision, quoting a 'rounds 24-31' concentration pattern,
lands at round 31."**

One structural note worth carrying forward: the backend concurrency/locking logic (§B.2/§B.3)
genuinely DID converge early and stay clean — concurrency-isolation passed 7 consecutive rounds by
the end (`plan_check_log.md:2482-2484`). So there IS a real "the design-sensitive core stabilized
earlier than the UI-wiring layer" pattern in this data — it's just not cleanly dated to round 20-24,
and the UI-wiring layer's own binding bugs never stopped recurring until the human called it.

---

## Q2 — Should the compiler gate be a new role, folded into Test-writer, or a DESIGN_CHECKLIST gate?

### Architectural facts that constrain the answer (read directly, not inferred)

**1. The plan-check Verifier is tool-level, structurally incapable of running a compiler — this is
not a convention, it's a hard block.** `~/.claude/agents/plan-check-verifier.md` (identical copy at
`~/Claude/loop/.claude/agents/plan-check-verifier.md`):
```
tools: Read, Grep, Glob
disallowedTools: Agent, Write, Edit, NotebookEdit, Bash
```
and line 3's `description`: *"Reviews a spec/plan BEFORE the Coder implements it... Read-only, no
code execution — no implementation exists yet to run."* Line 14-15 of the same file: *"Do not
attempt to run code or tests — you have no Bash tool and none exists to run yet."* Any design that
asks a plan-check lens itself to run a compiler is a non-starter without first changing this
subagent type's tool grant (and per the operational-gotchas learning, a custom subagent type edit
needs a session restart to take effect — a real adoption cost).

**2. Folding this into Test-writer's existing remit (option b) repeats a mistake this exact
framework already made and fixed, four days before this dispatch.** `roles/test_writer.md:1` states
the role runs *"Tier 1 — spec-only, runs BEFORE implementation"* and its own LOOP-M3 section says
explicitly (`test_writer.md:42-44`): *"You run before any implementation exists (see this file's own
header), so you cannot execute a mutation check here — there is nothing yet to mutate."*
`fix_plan.md:4986-4991` documents that `H-AC-ORACLE-TARGET-1`'s FIRST attempt put an executable
mutation-check directly in `roles/test_writer.md`, and it had to be revised *"after an independent
Verifier caught that the first version put the executable mutation-check in `roles/test_writer.md`
— which runs strictly BEFORE any implementation exists... making the original steps literally
unexecutable there."* A compiler/typecheck pass has the identical shape (it needs real files to
execute against) — proposing it inside Test-writer's current, stated pre-implementation contract is
the same category error, already caught once. (Note for precision: the `test-writer` SUBAGENT type's
tool grant at `~/.claude/agents/test-writer.md:4` DOES include `Write, Edit, Bash` — so the blocker
here is the role brief's stated TIMING model, not a tool restriction. That distinction matters
because it means option (b) isn't tool-impossible, just contract-inconsistent with the file's own
current framing — and orchestrator.md's own de-priming rule (lines 75-86) exists specifically to
keep "no implementation exists yet" as a stable, load-bearing fact at plan-check time; introducing
real files there would require revising that rule too, not just Test-writer's header.)

**3. Oga itself is explicitly forbidden from writing code, including stub files.**
`orchestrator.md:5-19`: *"Your permitted outputs — nothing else: 1. Agent tool calls... 2. Synthesis
and reporting... 3. Questions... Everything else — research, code-writing, test-writing,
verification, web searches, file edits — is sub-agent work. If you are producing it yourself, you
are out of role and must stop."* The one carve-out (line 15-18) is running `verify.py`/
`pytest --testmon` — an existing command, not writing new files. So whatever writes stub files must
be a sub-agent dispatch; Oga cannot do it inline even as a shortcut.

**4. Coder already has full Write/Edit/Bash (`~/.claude/agents/coder.md:4`) and the micro-step build
loop already decomposes a slice into ≤200-line steps (`orchestrator.md:139-166`) — but Coder's
stated contract assumes tests already exist** (`roles/coder.md:7`: *"You receive: ...The test
file(s) the implementation must satisfy"*). A stub-and-compile pass dispatched BEFORE Test-writer
has no tests to satisfy yet, which is a real (if smaller) contract mismatch for option (a) if the
new phase is placed before Test-writer, as the dispatch prompt's option (a) literally specifies
("inserted between plan-check and Test-writer").

**5. `harness/verify.py` — "the objective signal the whole loop optimizes against"
(`verify.py:5-6`) — has ZERO compiler/typecheck/build step, confirmed by direct code read.** Its
Node path (`verify.py:121-157`, `detect_node_runner`/`node_runner_argv`) only ever shells to
`npx vitest run` or `npx jest --ci`; a full-file grep for `tsc|typecheck|next build|compile` across
`verify.py` returns zero hits. Meanwhile `fix_plan.md:740-746` (`PSC-TSC-1`) shows `tsc --noEmit`
HAS been run for this exact project, but manually/ad hoc — *"verified this session, repeatedly, as
the RLS slice's tsc gate"* — never as a standing part of any role's contract or of `verify.py`
itself. This is a genuine, structural gap independent of where in the role sequence a compiler
check gets triggered: even after Coder's real implementation pass, nothing in the deterministic
harness enforces a compile/typecheck step today.

**6. The actual, lived resolution for THIS exact slice did not create a new phase or role — it
extended the EXISTING Test-writer → Coder pipeline with an explicit build-verification
requirement.** `plan_check_log.md:2538-2548`, quoted in full: *"Decision: STOP the prose plan-check
loop... Next steps: dispatch Test-writer against the current spec (revision 35), then Coder for
implementation, with REQUIRED real-build verification (`next build`, `tsc --noEmit`) plus the
mandatory live-browser check (H-BROWSER-UI-CHECK-MISSING-1) before considering this slice done —
verifying with real tools instead of more prose rounds, per Nnamdi's direct instruction this
round."* This is the closest thing to ground truth for "what actually happened when this exact
question was faced for real," and it is neither option (a) nor (b) as literally specified — it's
closest to a version of (c): a rule about WHEN to stop plan-check and what the Coder/verify step
must additionally require, using existing roles.

### Recommendation

Given (2) and (3) above, **option (b) (fold into Test-writer's stated remit) is the weakest choice**
— it repeats a dated, four-day-old, already-corrected mistake in this same framework, on the exact
same shape of problem (an execution-dependent check placed in a role whose own header says
execution can't happen yet).

Given (1) and the learnings.md-documented cost of new custom subagent types (session restart
required, no gate in this framework's history has been introduced this way — `H-AC-ORACLE-TARGET-1`
itself, the literal template this dispatch told me to use, spread its fix across **four existing
role files**, adding zero new roles), **a brand-new "Stub-and-compile" subagent type (option a, as a
new `subagent_type`) is the heaviest and least-precedented choice.** If a new role is wanted, it
would be lighter-weight to add it as a documented NEW MODE of an existing role (the way
`roles/verifier.md` already supports two modes — plan-check vs. post-build — from one file) than as
a wholly new agent type; but even that needs Coder's or a similar role's contract explicitly widened
to accept "no tests yet, stub-only" as a valid input shape, which is a real edit, not a free lunch.

Given (5) and (6), **my reasoned recommendation is a variant of option (c), shaped narrowly around
what the record shows actually worked, not the abstract "if interfaces have stabilized" trigger the
dispatch hypothesized:**
1. A `DESIGN_CHECKLIST.md` stopping-rule gate for plan-check itself: once N consecutive rounds'
   findings are saturated on the same binding-class signature (undeclared identifier / missing
   import / missing export directive) with zero NEW logic/concurrency/security finding in that same
   window, plan-check STOPS further prose rounds for that finding class and proceeds to
   Test-writer → Coder — instead of the abstract, harder-to-detect "once interface shapes have
   stabilized" framing, which the round-by-round record shows doesn't have a clean single trigger
   point (Q1 above).
2. Separately, and independently justified regardless of (1): **wire an actual `tsc --noEmit` /
   `next build` (or the ecosystem-appropriate equivalent) into `harness/verify.py` as a standing,
   structural step** for any TS/JS project, the same way pytest/vitest/jest already are — this is a
   concrete, provable gap (confirmed by direct code read, section 5 above) independent of the
   plan-check-timing question, and it is what makes stopping plan-check earlier SAFE rather than
   lossy: binding bugs stop being caught by expensive prose lens rounds and start being caught by
   the compiler the loop already trusts as "the objective signal" — for free, on every Coder
   checkpoint, not just the final slice-closing manual run `PSC-TSC-1` describes.
3. This reuses existing roles and tools completely — no new subagent type, no restructuring of
   Coder's or Test-writer's stated contracts, no session-restart cost — and it directly matches what
   was actually decided and executed for this real slice (section 6 above), rather than inventing an
   untested new mechanism.

This is a recommendation, not a build decision — per my role, adopting it should go through the SAME
validate-before-trust sequence `H-AC-ORACLE-TARGET-1` used (design it, log it in `fix_plan.md`,
validate with a blind test before trusting it, get an independent Verifier pass, confirm a green
`run_evals.py`) before it enters `DESIGN_CHECKLIST.md`/`orchestrator.md`/`verify.py` for real. That
call belongs to Oga/Nnamdi.

---

## Q3 — Does the relative-cross-reference anti-pattern get the same treatment?

**Confirmed: orchestrator.md gives zero spec.md-authoring guidance on cross-reference style,
anywhere.** A grep across `orchestrator.md`, `RUN.md`, `fix_plan.md`, and `learnings.md` for
"see above / see below / anchor" language returns no spec-authoring rule at all — the only hits are
unrelated uses of "anchor" (regex/`.gitignore` anchoring, evidence anchoring for judges, decision-log
anchoring bias) or a single incidental "see below" inside `roles/coder.md:22` referring to that
file's own structure, not spec.md. There is also no `SPEC_TEMPLATE.md` or equivalent file anywhere
under `~/Claude/loop` (confirmed via `find`). The only place orchestrator.md discusses spec.md
authoring at all is step 1's "Produce a short spec" instruction (`orchestrator.md:47`) and the
"Context section" pre-implementation framing rule (`orchestrator.md:75-86`) — neither says anything
about cross-reference format.

**This is not a hypothetical risk — the SAME real run that grounds Q1/Q2 shows this anti-pattern
cost real review cycles repeatedly, independent of the binding-bug question:**
- Round 15/16 (`plan_check_log.md:1229-1231`, `1291`): a namespace-count/pointer correction
  ("below" → "above").
- Round 23 (`plan_check_log.md:1862-1863`, `1871`): *"a genuine backwards directional pointer
  ('above' instead of 'further below')"* — fixed.
- Round 24 (`plan_check_log.md:1896-1897`, `1915`): *"a second backwards directional pointer"* — the
  SAME section, one paragraph further on, structurally identical to the one round 23 just fixed.
- Round 27 (`plan_check_log.md:2152-2153`, `2182`, `2202`): two lenses independently converge on the
  same backwards "below" pointer; **both** are corrected.
- Round 29 (`plan_check_log.md:2330-2332`): *"the SAME live-editing pattern round 25 established...
  had itself introduced 3 NEW backwards pointers in the fixes just applied"* — the act of FIXING a
  prior finding created three fresh instances of the same bug class.
- Round 30 (`plan_check_log.md:2429`): 2 more backwards pointers found via a dedicated mechanical
  sweep.
- Round 31 (`plan_check_log.md:2504-2510`): a full, dedicated *"mechanical sweep of ~90 directional
  pointers"* still turns up 2 more.

That is at least **9 distinct rounds** across a single 31-round run where a lens had to spend real
review effort finding and fixing this exact class of defect — a materially larger, more-repeated
real-incident base than `H-AC-ORACLE-TARGET-1` had at the point it was filed (that gate was filed
off ONE incident, AC19; this pattern already has 9+ in the very same run, fully on the record).

**A precise, important nuance the record reveals:** this spec.md ALREADY uses stable, anchored
section IDs for its own STRUCTURE — `§A.2`, `§B.3`, `§C.1`, etc. are cited constantly and reliably
throughout the log (e.g., every "Fixes applied" list references them by anchor, never by position).
The bug is narrower than "no anchors exist" — it's that PROSE cross-references BETWEEN sections
still use relative positional language ("above," "below," "further above") instead of citing the
target's own anchor (e.g., "see §B.2 point 4," which the doc's own convention already supports and
already uses elsewhere). This makes the fix cheap and precise: ban relative positional words in
cross-references, require the anchor form the document already has, everywhere.

### Does it matter only pre-code, becoming moot once code exists?

No — for two grounded reasons, not intuition:
1. **spec.md is explicitly a maintained, living artifact in this framework's OWN design, not a
   discard-after-generation "spec-first" document** (the exact anti-pattern the prior research doc
   names and this project is explicitly moving away from, per finding #6/the round-31 decision
   itself). `roles/test_writer.md:35-39` (LOOP-M2, "SPEC↔CODE CONTRACT") requires ongoing
   spec-vs-code consistency checks, and `roles/verifier.md:27` (Layer 2 judgment check) explicitly
   instructs the post-build Verifier to *"Re-read the goal and acceptance criteria"* — i.e. re-read
   spec.md, AFTER code exists. A stale relative pointer inside spec.md can mislead a reader in
   exactly the same way post-code as pre-code; the document does not stop being read once
   implementation starts.
2. **The exposure shape changes for the worse, not the better, post-code.** Pre-code, a dedicated
   mechanism exists that catches this specifically — the regression-audit/precision-of-instruction
   lenses run a "full cross-reference sweep" almost every round (e.g. `plan_check_log.md:1108`,
   "150+ pointers, all resolved correctly"; `2506`, "~90 directional pointers"). Post-code, per the
   round-31 decision, that dedicated sweeping stops (plan-check rounds end); the only remaining
   reader is a single post-build Verifier pass and any future maintainer skimming the doc — with NO
   comparable mechanism left to catch a drifted "see above" pointer. So the absolute frequency of
   exposure likely drops post-code (fewer full-document reads happen at all), but each remaining
   read is LESS protected, not more.

### Should it be its own rule, and should it gate on line count?

Yes to a rule; **no to gating on raw line count** — the evidence points at a different, cheaper, and
already-precedented trigger. The FIRST instance of this bug class occurs at round 15-16
(`plan_check_log.md:1229-1231`), well before the document's size is ever mentioned in the log (the
"~3900-line document" figure appears only at round 26, `plan_check_log.md:2087`) — so line count is
not what's actually driving the harm. What IS driving it, visibly, is **iterative revision**: every
one of the 31 rounds edits the document, and any edit anywhere can invalidate a relative pointer
anywhere else in the document, regardless of overall size (a 200-line spec revised 10 times carries
the identical risk mechanism as a 4000-line spec revised twice). Recommend anchoring the rule to
REVISION COUNT, not size — and note that `orchestrator.md:75` already uses exactly this kind of
threshold elsewhere in the same file (*"After 2 or more plan-check rounds on the same spec..."*), so
tying a new rule to "once a spec.md has undergone ≥2 plan-check revision rounds, every cross-reference
must cite the target's own anchored section ID, never a relative positional word" reuses an
already-adopted threshold in this exact file rather than inventing a new line-count constant that
would need its own justification.

This rule is materially cheaper to adopt than the compiler gate: it requires no new tool
permissions, no new role, and no changes to `verify.py` — it is a pure text-authoring convention,
mechanically checkable with a trivial grep (e.g. `grep -inE '\b(see |further )?(above|below)\b'
spec.md`, flag hits for anchor-only rewrite) that Oga or the precision-of-instruction lens could run
BEFORE spending a full lens round rediscovering the same class of typo by hand. Given the volume of
real, self-documented recurrence already on file (9+ instances in one run, including one case where
the fix for a prior instance created three new ones), this is a well-grounded, low-cost candidate for
its own `DESIGN_CHECKLIST.md`/plan-check hygiene rule, independent of whatever happens with the
compiler-gate question in Q2 — it does not need to wait on that larger, harder decision.

---

## Summary of concrete file:line citations used above (for quick re-verification)

- `~/Claude/loop/runs/2026-07-04_airbnb-calendar/plan_check_log.md` — 2550 lines total; key anchors:
  1183-1199 (round 16, first schema-binding bug), 1305-1379 (round 17, "single most severe finding,"
  5 undeclared identifiers), 1508-1518 (round 19, cross-tenant design bug), 1609-1619 (round 20,
  Server Action UI bug), 1684-1701 (round 21, type-narrowing bug), 1836-1853 (round 23, orgId
  unbound, all 4 lenses converge), 1900-1909 (round 24, missing import), 2081-2095 (round 26),
  2155-2167 (round 27, "5 times... now 6th"), 2242-2253 (round 28, "7th instance"), 2302-2323
  (round 29), 2415-2419 (round 30, "genuinely exhausted"), 2438-2451 (round 30, AC19 security-oracle
  bug), 2494-2510 (round 31, AC16 + pointer sweep), 2523-2550 (Nnamdi's process-pivot decision and
  STOP instruction).
- `~/Claude/loop/loop-team/orchestrator.md` — 5-19 (Oga's permitted-outputs self-check), 47-107
  (step 1, plan-check protocol), 75-86 (pre-implementation framing rule, the "≥2 rounds" threshold),
  139-172 (micro-step build loop).
- `~/Claude/loop/loop-team/DESIGN_CHECKLIST.md` — full file, 117 lines; gate 9 at lines 83-102.
- `~/Claude/loop/loop-team/roles/test_writer.md` — line 1 (Tier-1/pre-implementation header),
  35-39 (LOOP-M2), 41-53 (LOOP-M3, explicit "cannot execute a mutation check here").
- `~/Claude/loop/loop-team/roles/coder.md` — line 7 (receives "the test file(s)... must satisfy"),
  line 22 ("see below," incidental, not spec-authoring guidance).
- `~/Claude/loop/loop-team/roles/verifier.md` — line 27 (Layer 2, re-reads goal/ACs post-build).
- `~/Claude/loop/loop-team/roles/adversarial_test_writer.md` — line 3 ("a working implementation
  that already passes the standard test suite"), line 156 (Phase 3.5 heading).
- `~/Claude/loop/fix_plan.md` — 4900-5072 (`H-AC-ORACLE-TARGET-1` full entry, including the
  test_writer.md placement mistake and its fix at 4986-4991), 720-746 (`PSC-TSC-1`,
  `tsc --noEmit` run manually/ad hoc), 3974-4016 (`H-BROWSER-UI-CHECK-MISSING-1`, cited for
  context on the same live-browser-check requirement referenced by the round-31 decision).
- `~/.claude/agents/plan-check-verifier.md` — lines 3-5, 14-15 (tool grant + explicit "no Bash").
- `~/.claude/agents/coder.md` — line 4 (`Write, Edit, NotebookEdit, Bash, Grep, Glob`).
- `~/.claude/agents/test-writer.md` — line 4 (`Write, Edit, Bash, Grep, Glob` — tools ARE granted;
  the blocker for option (b) is `roles/test_writer.md`'s stated timing, not this tool grant).
- `~/Claude/loop/loop-team/harness/verify.py` — lines 1-25 (module docstring, no compile step
  mentioned), 121-157 (`detect_node_runner`/`node_runner_argv` — vitest/jest only, confirmed via
  full-file grep for `tsc|typecheck|next build|compile` returning zero hits).

No sub-agents were used to produce this document; every quoted line above was read directly in this
session via `Read`/`Bash`/`grep` tool calls.
