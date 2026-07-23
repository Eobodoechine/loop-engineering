# Codex diagnostic followup — spec-to-code drift validator: reconciliation (2026-07-08)

**Scope/method:** Mode A radar reconciliation. Read all 6 existing same-day dossiers in full before
doing any new work (list below). Independently verified, via direct `WebFetch`/`WebSearch`/`gh`/
`Bash`, every source Codex's separate diagnostic session cited that was NOT already thoroughly
covered in those 6 docs. No sub-agents were dispatched at any point — every fetch, grep, and read
below was done directly in this session (leaf worker, per dispatch instruction).

**The 6 existing docs read first (all dated 2026-07-08, all read in full):**
1. `research/compiler-feedback-loop-gate-design-2026-07-08.md`
2. `research/compiler-feedback-loop-paper-verification-2026-07-08.md`
3. `research/compiler-feedback-loop-prior-art-2026-07-08.md`
4. `research/compiler-gate-design-recommendation-2026-07-08.md`
5. `research/compiler-gate-external-research-2026-07-08.md`
6. `research/compiler-gate-internal-grounding-2026-07-08.md`

Also read directly: `loop-team/orchestrator.md` (full 622 lines, both halves), `loop-team/
DESIGN_CHECKLIST.md` (full, current 150+ lines), `fix_plan.md` (targeted reads: lines 5074–5496),
`loop-team/harness/verify.py` (full-file grep + targeted reads, 704 lines), `loop-team/roles/
coder.md` and `roles/test_writer.md` (targeted greps), `research/radar.md` (full).

---

## Part 1 — Codex citations already thoroughly covered by the 6 existing docs (not re-verified; cited)

These were independently re-verified from primary sources already, in depth, in the existing docs.
Re-doing this work would be wasted effort — cited here with the exact file to consult:

| Codex citation | Where it's already covered | Verdict already established |
|---|---|---|
| Spec Growth Engine (arXiv:2606.27045) | `paper-verification` + `prior-art` + `external-research` docs | Confirmed real; single-author, unreviewed preprint; "Intent Graph"/"Evidence Graph"/"Drift Validator" terms verified verbatim (Section 5.4); **zero code, zero benchmark** — "maintained as an internal design-document set... available from the author on request." RESEARCH_ONLY. |
| GitHub Spec Kit (github/spec-kit) | `prior-art` + `external-research` docs | Confirmed real, 118k★, MIT, extremely active. `/speckit.converge` is pure LLM-prose review ("not a diff tool... no git, no branch comparison"), never blocks. Negative finding: even the most popular spec-driven toolkit hasn't built a mechanical drift gate. |
| "Deterministic AST Analysis" hallucination-detection paper (= arXiv:2601.19106) | `paper-verification` + `prior-art` docs | Confirmed real, FORGE 2026 accepted (peer-reviewed, stronger than Spec Growth Engine). 100% precision / 87.6% recall / 0.934 F1 on 200 Python snippets; per-category breakdown: missing-imports 97.9%, mis-typed-API 84.5%, contextual-mismatch only 33.3%/0%. Repo (`WM-SEMERU/Hallucinations-in-Code`) confirmed real but 2★, unlicensed, academic-only. |
| Aider's lint/test docs | `prior-art` + `external-research` docs | Confirmed from actual source (`aider/linter.py` / `base_coder.py`): `--auto-lint` defaults **True**, `max_reflections=3` hard cap, fatal flake8 set includes `F821` (undefined name — the exact unbound-identifier bug class). Python-only; TS/JS falls back to tree-sitter, not `tsc`. |
| mini-SWE-agent, SWE-agent | `prior-art` + `external-research` docs | Both confirmed real/mature. mini-swe-agent: "does not have any tools other than bash" — zero built-in compiler/lint discipline, confirming the gate must live in the harness, not the Coder scaffold. Classic SWE-agent: superseded by mini per its own README (already REJECTED on radar). |
| OpenHands | `prior-art` + `external-research` docs | Confirmed real (~79k★). Its own `tsc` usage is CI-only on its own source (not agent-generated code). The load-bearing find: OpenHands "Stop hooks" — `{"decision": "deny"}` + `exit 2` — a real, documented, directly-blocking precedent, closest analog found anywhere to "compiler feedback as a structural gate." Maps onto loop-team's own `hooks/subagent_stop_gate.py` + `verify.py` substrate (pattern transfers; file doesn't). |
| Reflexion (arXiv:2303.11366) | `external-research` doc, "Academic compiler-feedback lineage" table | Confirmed real; 91% pass@1 HumanEval via verbal-feedback-into-episodic-memory. Listed alongside CompCoder/Self-Edit/CodeT/RLCF/StepCoder as training-time RL/prompting techniques, not adoptable inference-time harness tooling — corroborates the *category* (compiler/execution feedback in the loop), not something to install. |
| AdverTest / mutation testing (general concept) | Existing radar (`mutmut` already wired into `orchestrator.md` step 5.5) covers the *category*; the specific paper Codex meant is verified fresh in Part 2 below, since it wasn't in the 6 docs by name. |

**TNG/ArchUnit** was also already covered (both `prior-art` and `external-research` docs, plus a live radar row) — confirmed real, 3,758★, Apache-2.0, active, but wrong ecosystem (JVM) for current Python/Node targets. RESEARCH_ONLY, kept.

---

## Part 2 — Codex citations the 6 existing docs miss: independently verified this pass

Every source below was opened directly (arXiv abstract/HTML pages via `WebFetch`, GitHub repos via
`WebFetch`) before being cited, per the honesty bar. None of these appear in any of the 6 existing
docs or in `research/radar.md` before this pass (confirmed by grep).

### 2a. ReqToCode (arXiv:2603.13999) — genuinely different mechanism family from anything in the 6 docs

**Confirmed real.** Fetched `arxiv.org/abs/2603.13999` and `arxiv.org/html/2603.13999` directly.
- **Title (verbatim):** "ReqToCode: Embedding Requirements Traceability as a Structural Property of
  the Codebase." **Author:** Thorsten Schlathölter. Submitted March 14, 2026, cs.SE, 23 pages.
- **The load-bearing difference from Spec Growth Engine:** this one has a **working implementation**,
  quoted verbatim: *"The ReqToCode approach is not purely theoretical. A working implementation —
  Ariadne — exists and is applied to its own development process... currently generates language
  artifacts for Java, C, and C++, and connects to Jira and Codebeamer as requirement sources."*
- **Mechanism, quoted verbatim:** a "Traceable" is *"a generated, language-native code element that
  represents a single requirement."* In Java, *"a RequirementSet is realized as an enumeration type,
  with each Traceable as an enum constant carrying its metadata."* When a requirement changes: *"Any
  code referencing SWR_102_REJECT_STALE_SENSOR_READINGS now produces a compiler warning... When the
  Traceable is eventually removed from the enum, all references produce compilation errors."* This
  reuses the language's own `@Deprecated`/`[[deprecated]]` mechanism — the compiler enforces
  spec-code linkage structurally, by construction, not via a separate static-analysis diff pass.
- **What's missing:** no public repo/GitHub link found anywhere in the paper's text; **no quantitative
  evaluation section at all** (self-application to Ariadne's own dev process, illustrated, not
  measured); Java/C/C++ only, with the paper itself flagging limitations for Rust and dynamically-typed
  languages.
- **Triage: RESEARCH_ONLY.** Real, distinct design pattern ("bake the spec ID into the type system so
  the compiler enforces the link" — categorically different from the tsc/knip "diff code against
  spec prose" approach already designed for loop-team's TS targets), but no code, no benchmark, wrong
  ecosystem for current build targets (padsplit-cockpit is TS/Next.js, not Java/C/C++).
- **Where it wires in — nowhere, today.** Not portable to the current `verify.py` type-check gate
  design. Worth a WATCH entry in case a public Ariadne release or a TS/Python port ever ships — the
  underlying idea (requirement IDs as language-native, compiler-checked constructs) could in
  principle be approximated in TS via a `const enum`/branded-type pattern, but that would be new,
  undesigned work, not something to adopt today.

### 2b. traceSDD (arXiv:2606.30689, "Citation Discipline in Spec-Driven Development") — cheap, measured, and directly relevant to an EXISTING loop-team mechanism

**Confirmed real.** Fetched `arxiv.org/abs/2606.30689` and `arxiv.org/html/2606.30689` directly.
- **Title (verbatim):** "Citation Discipline in Spec-Driven Development: A Cross-Model Empirical
  Study of Output Determinism and Automated Hallucination Detection in LLM-Generated Code." **Author:**
  Subham Panda. Submitted June 28, 2026, 17 pages, cs.SE.
- **Mechanism, quoted verbatim:** traceSDD *"enforces mandatory per-line requirement citations using
  hierarchical REQ-XXX.Y.Z identifiers."* Verification is an *"orphan-REQ check"* — *"extract all REQ
  IDs cited in the generated code, subtract the set of valid REQ IDs from the specification, and flag
  any orphans"* — which *"runs in O(1) per file (a single grep) and requires zero manual effort."*
- **Compared against, verbatim:** "Spec Kit" (artifact-level traceability via user stories/ACs) and
  "OpenSpec" (post-hoc external YAML sidecar trace maps) — traceSDD's per-line citation requirement
  is the differentiator.
- **Real, measured numbers (quoted):** *"The cited condition achieves TDR = 86.4% (Claude) and 88.0%
  (GLM), while all three alternative conditions achieve 0%"* — with *"False Positive Rate: 0.0% across
  all checks."* The honest trade-off, also quoted: *"citation annotations trade determinism for
  verifiability"* — the cited condition is measurably less deterministic run-to-run.
- **What's missing:** no code/repo/data-availability statement found anywhere in the paper.
- **Why this is the most directly load-bearing new find of this pass:** loop-team's own
  `orchestrator.md` (step 1) already has a live rule — *"For verifier/report-generator builds that
  cite external artifacts, require Tier-2 citation grounding... code must own evidence IDs, quote
  rendering, citation printing, and deterministic rejection of unsupported authority
  (`loop-team/evals/citation_grounding.py`)"* — for a **different** artifact class (report-generators
  citing external sources). traceSDD is independent, real, measured evidence (86–88% hallucination
  detection, 0% FPR, negligible compute cost) that the SAME citation-discipline principle — mandatory
  ID citation + a trivial grep-diff check — generalizes to **Coder-generated code citing spec
  requirement IDs**, not just report text citing external sources. This is a genuinely new, cheap,
  falsifiable idea not present in the 6 existing docs: require the Coder to cite the AC/requirement ID
  it's implementing inline (a comment convention), and add an O(1) grep-based orphan check to
  `verify.py` (or a Test-writer-side check) that flags any cited ID absent from spec.md's declared
  ACs. **Triage: TESTABLE** (pattern, no code to adopt, but the mechanism is trivial to build and the
  paper supplies a real measured hallucination-detection number to beat/replicate on our own stack).
  This is a genuinely different mechanism from the tsc/type_check gate (it catches "Coder claims to
  satisfy AC-7 but AC-7 doesn't exist / was renamed," not "identifier X is unbound") — complementary,
  not overlapping, with the compiler-gate design in the 6 existing docs.

### 2c. R2Code (arXiv:2604.22432) — real, peer-reviewed, but wrong shape for this problem

**Confirmed real.** Fetched `arxiv.org/abs/2604.22432` and `arxiv.org/html/2604.22432` directly.
- **Title (verbatim):** "R2Code: A Self-Reflective LLM Framework for Requirements-to-Code
  Traceability." **Authors:** Yifei Wang, Jacky Keung, Xiaoxue Ma, Zhenyu Mao, Kehui Chen, Yishu Li.
  **Venue: IEEE COMPSAC 2026 (accepted)** — a stronger, peer-reviewed venue signal than Spec Growth
  Engine's unreviewed preprint.
- **Mechanism:** Bidirectional Alignment Network (semantic matching) + Self-Reflective Consistency
  Verification (explanation-guided checking) + Dynamic Context-Adaptive Retrieval.
- **Real, quoted numbers:** *"an average F1 gain of 7.4%, while reducing token consumption by up to
  41.7%"* across 5 datasets (iTrust, eTour, SMOS, eANCI — all Java — plus RETRO.NET, C#); on iTrust
  specifically, *"F1-score of 0.7296."*
- **What's missing:** no repo/code-availability statement found; *"presented as an experimental
  framework rather than a deployed running tool."*
- **Why this doesn't change the design recommendation:** R2Code is a **link-recovery** tool —
  designed to mine/reconstruct requirement↔code trace links in an EXISTING, presumably-drifted
  legacy repo (its own datasets are established open-source Java/C# projects), not a **build-time
  drift-prevention gate** for an actively-being-built slice. That's the wrong shape for loop-team's
  actual need (catch drift the instant a Coder introduces it, inside the micro-step loop), even
  setting aside the missing code and Java/C#-only scope. **Triage: RESEARCH_ONLY, parked** — logged
  for completeness per the honesty bar, no further action recommended.

### 2d. bufbuild/buf — real, mature, wrong domain (Protobuf-specific)

Confirmed via direct `WebFetch` of `github.com/bufbuild/buf`: **11.2k★, Apache-2.0, actively
maintained (v1.71.0, 2026-06-16).** Genuine, CI-blockable breaking-change detector for Protobuf
schemas — quoted: *"Run `buf breaking` against Git... before merge"* — with graded compatibility
levels (FILE/PACKAGE/WIRE_JSON/WIRE). This is a real "schema drift as a blocking gate" precedent, but
scoped entirely to Protobuf/gRPC; none of loop-team's current build targets (padsplit-cockpit et al.)
use Protobuf. **Triage: WATCH**, parked until a build target adopts a Protobuf API surface.

### 2e. OpenAPITools/openapi-diff — real, active, complements the already-radar'd openapi-typescript

Confirmed via direct `WebFetch`: **1.1k★, Apache-2.0, active (v2.1.7, 2026-01-26), Java.** Diffs two
OpenAPI 3.x specs and classifies changes "Broken compatibility" vs. "Backward compatible" (endpoints,
parameters, schemas, deprecation status). `openapi-typescript` (already on radar) generates types
FROM a spec (one-directional, forward); `openapi-diff` catches spec-vs-spec drift OVER TIME (the
reverse direction) — together they'd cover more of the Drift Validator's "Intent Graph" concept for
an OpenAPI-contract build, but neither derives an Intent Graph from spec.md prose the way the
Grabowski paper envisions, and loop-team's current targets don't ship an OpenAPI contract. **Triage:
WATCH**, relevant only if/when a build target ships one.

### 2f. pact-foundation/pact-js — real, active, a genuinely different "spec" source

Confirmed via direct `WebFetch`: **1.8k★, MIT, active (v17.0.1, 2026-07-01), TypeScript.**
Consumer-driven contract testing: the "contract" is derived from real CONSUMER usage recordings, not
authored by a human or an LLM, and its `Verifier` class **blocks** CI when the provider's real
behavior diverges. This is mechanistically distinct from every other candidate in this space (the
"Intent" side of the drift check comes from observed real usage, not written intent) — but it only
makes sense for a genuine multi-service architecture. padsplit-cockpit today is a single Next.js app
talking to Postgres/Prisma directly; there's no second service to be a "consumer" of. **Triage:
WATCH**, parked until loop-team builds a real multi-service target.

### 2g. spring-projects/spring-modulith — corroborates the existing ArchUnit finding, adds nothing new

Confirmed via direct `WebFetch`: **1.2k★, Apache-2.0, active (v2.1 GA, 2026-06-11).**
`ApplicationModules.of(Application.class).verify()` runs module-boundary checks as a JUnit test — same
category, same JVM-only limitation, same "wrong ecosystem for current targets" verdict already
recorded for ArchUnit in the existing docs and radar. Logged here only because the dispatch's honesty
bar requires independently verifying every Codex citation, not because it changes any conclusion.
**Triage: RESEARCH_ONLY**, no new action.

### 2h. AdverTest (arXiv:2602.08146) — real, but tangential to drift detection; a Test-writer candidate instead

Confirmed via direct `WebFetch` of `arxiv.org/abs/2602.08146`. **Title (verbatim):** "Test vs Mutant:
Adversarial LLM Agents for Robust Unit Test Generation." **Authors:** Pengyu Chang, Yixiong Fang, Silin
Chen, Yuling Shi, Beijun Shen, Xiaodong Gu. Two co-evolving agents — a test-generation agent (T) and a
mutant-generation agent (M) — where M "hacks" T's blind spots and T iteratively hardens against M's
mutants. On Defects4J with DeepSeek V3.2: fault-detection rate 66.63%, an *"8.6% relative
improvement over HITS (61.38%)"* and *"63.3% improvement over EvoSuite (40.80%)."* **No code/repo
found.**

**Important framing correction:** Codex cited this in the context of a "spec-to-code drift
validator," but it is not a drift-detection tool at all — it's a test-generation-quality technique,
directly relevant to `roles/adversarial_test_writer.md` and the existing `mutmut` step
(`orchestrator.md` step 5.5), not to `harness/verify.py`'s compiler/drift gate. The genuinely new idea
versus what loop-team already does (static `mutmut` mutation + a single adversarial Test-writer pass)
is the **adversarial co-evolution loop itself** (mutant-generator and test-generator iterating against
each other, not a one-shot mutation batch) — but there is no implementation to adopt, and the
published gain over EvoSuite/HITS, while real, is a different baseline than loop-team's current setup.
**Triage: RESEARCH_ONLY**, filed under the correct category (Test-writer/mutation-testing candidate,
not drift-validator), revisit if a public implementation ships.

---

## Part 3 — Live repo state check: this exact topic is mid-implementation, uncommitted, right now

This is the single most important finding of this reconciliation pass, and it directly bears on Part
4's question below. Checked directly via `git status`/`git diff --stat`/`git log` and full-file greps
of the actual live files (not the 6 dossiers' descriptions, which predate this state):

```
$ git status --porcelain -- loop-team/harness/verify.py loop-team/DESIGN_CHECKLIST.md loop-team/orchestrator.md
 M loop-team/DESIGN_CHECKLIST.md
 M loop-team/harness/verify.py
 M loop-team/orchestrator.md

$ git diff --stat -- loop-team/harness/verify.py loop-team/DESIGN_CHECKLIST.md loop-team/orchestrator.md
 loop-team/DESIGN_CHECKLIST.md |  79 ++++++++++-
 loop-team/harness/verify.py   | 302 +++++++++++++++++++++++++++++++++++++++++-
 loop-team/orchestrator.md     |  33 +++++
 3 files changed, 410 insertions(+), 4 deletions(-)

$ git log -1 --format="%H %ci" -- loop-team/harness/verify.py
2cccc7e... 2026-07-02 13:58:14 -0400   # last COMMITTED version — 2026-07-02, pre-dates all of this
```

**None of this is committed.** All four `fix_plan.md` entries this research thread produced today are
still `DESIGNED`/`PROPOSED`, **`NOT YET VALIDATED`**:
- `H-PLANCHECK-BINDING-SATURATION-1` (priority HIGH) — the DESIGN_CHECKLIST stopping-rule.
- `H-VERIFY-TSC-GATE-1` (priority HIGH) — a naive, zero-tolerance `tsc --noEmit` gate.
- `H-TYPECHECK-GATE-1` (filed as "PROPOSED, not yet implemented" in its own header) — the
  baseline/erosion-scoped `tsc` gate the design docs above actually recommend.
- `H-SPEC-XREF-1` (priority MEDIUM) — the cross-reference anti-pattern rule.

**And confirmed live, directly, by reading the actual code (not trusting any doc's description):**
`DESIGN_CHECKLIST.md`'s **gate 10** ("Binding-class saturation — stop hand-simulating the compiler
once it's the ONLY thing still recurring") is **already written into the file right now** — it exists,
in full, with the exact `[BINDING]`/`[LOGIC]`/`[CONCURRENCY]`/`[SECURITY]` tagging convention and the
"3 consecutive rounds, zero non-binding finding" stop rule. Separately, `harness/verify.py` **already
contains BOTH gates simultaneously, uncommitted, and they conflict**:
- `_run_tsc_gate()` (H-VERIFY-TSC-GATE-1, naive) — computed once per run (`_ts_check = _run_tsc_gate(...)`,
  line 282), hard-fails on ANY non-zero `tsc` exit, ANDed into `passed` inside `_finish()` (lines
  284–298).
- `_type_check_gate()` (H-TYPECHECK-GATE-1, baseline-scoped) — computed separately in `main()` (line
  ~663+), fails only on error fingerprints absent from a persisted baseline, ANDed into `passed` at
  lines 677–695.

Confirmed by direct grep that both functions, both call sites, and both `passed`-ANDing paths coexist
in the current 704-line file (the design docs above cite the file at 404 lines — it has grown 300
lines since). This is exactly the "real, reproduced, severe collision" an independent Verifier already
flagged in `fix_plan.md` (quoted there): a project with even one pre-existing/legacy `tsc` error would
be permanently, un-clearably force-failed by the naive gate regardless of what the baseline-scoped
gate correctly concludes. **`H-VERIFY-TSC-GATE-1`'s fix_plan.md entry status is literally "NEEDS
FOLLOW-UP... this gate cannot close"** pending reconciliation (drop the naive gate in favor of the
baseline-scoped one, or explicitly merge them) — not yet done as of this pass.

**Practical implication for anyone picking this thread up next:** do not assume `harness/verify.py`
"has no type-check gate" (true as of the last commit, 2026-07-02) or "has a clean type-check gate"
(also not true — it currently has two, unreconciled, uncommitted, in conflict). Read the live file
before touching it, and resolve the `H-VERIFY-TSC-GATE-1` vs. `H-TYPECHECK-GATE-1` conflict before
either is trusted or committed — that reconciliation is Oga/Nnamdi's call, not filed or resolved by
this dispatch (out of scope: I was asked to reconcile RESEARCH, not resolve a live implementation
conflict).

---

## Part 4 — Is Codex's "stop prose plan-check, transition to compiler-in-the-loop" recommendation covered in `orchestrator.md`?

**Answer: PARTIALLY COVERED — designed in exhaustive depth, and a chunk of it is already sitting in
the live working tree (in sibling files), but `orchestrator.md`'s own Failure Arbiter and micro-step
build-loop sections, read exactly as they stand right now, contain NEITHER half of it. This is a
genuine, currently-open gap in `orchestrator.md` itself, even though the surrounding framework has
already done (most of) the work to close it.**

Read directly, in full: `loop-team/orchestrator.md`'s "Failure arbiter" section (the 6 classes:
code-bug / test-bug / spec-gap / harness-fault / silent-throttle / degenerate-output) and "The
micro-step build loop" section (item 2: dispatch Coder → Oga runs `verify.py`/`pytest --testmon` →
green → checkpoint commit).

- **The Failure Arbiter does not apply to Codex's recommendation at all — it's the wrong mechanism
  for the wrong phase.** It classifies a RED result from a CODE build (post-Coder-dispatch), not a
  `PLAN_FAIL` from plan-check (pre-code). Plan-check's own routing (step 1: `DESIGN` /
  `KNOWLEDGE` gap types) is a separate mechanism, and — confirmed by direct grep — **it contains no
  "binding-class saturation" branch, no `[BINDING]` tag concept, and no reference to `DESIGN_CHECKLIST`
  gate 10 anywhere in `orchestrator.md`'s live text.** `grep -n "\[BINDING\]\|binding-class
  saturation\|gate 10\|the ten gates" loop-team/orchestrator.md` returns zero hits.
- **The micro-step build loop's item 2 calls `verify.py`/`pytest --testmon` per checkpoint, but says
  nothing about type-checking.** As literally written, it has no awareness that `verify.py` might (or
  might not, depending on which uncommitted state you're looking at) run a compiler step at all — the
  loop's text is silent on this, both before and after Part 3's finding.
- **What IS true, and is the "partially" in "partially covered":** the actual DESIGN work Codex's
  recommendation calls for has already been done, independently, by this same research thread,
  today — `DESIGN_CHECKLIST.md` gate 10 (the plan-check stopping-rule half) and `harness/verify.py`'s
  `type_check`/`ts_check` gates (the compiler-in-the-loop half) are BOTH already drafted and sitting
  in the live, uncommitted working tree (Part 3). They are simply (a) not yet reconciled with each
  other (a live, flagged conflict), (b) not yet referenced anywhere in `orchestrator.md`'s own prose
  (no orchestrator.md bullet points at `DESIGN_CHECKLIST` gate 10, and the `[BINDING]` tagging
  convention gate 10 depends on — "mirroring `test_writer.md`'s existing `[SECURITY-ORACLE]`
  tag-at-write-time convention" — is not itself wired into `roles/test_writer.md`; confirmed by grep,
  zero `[BINDING]`/`[LOGIC]`/`[CONCURRENCY]`/`[SECURITY]` hits there), and (c) not committed to git at
  all (last real commit to any of these three files predates today).
- **`roles/coder.md` also does not yet have the anti-gaming line** (`H-TYPECHECK-GATE-1`'s proposed
  "never suppress a type-check error / never pad the baseline" rule) — confirmed by grep, zero hits
  for `@ts-ignore`/`baseline`-suppression language in the live file.

**Bottom line for whoever reads this next:** treat Codex's recommendation as **independently
re-derived and already agreed with** by this project's own research (both arrived at "compiler-gate +
plan-check stopping-rule," from the same real 2026-07-04 airbnb-calendar incident) — this is
convergent validation, not a new lead to chase. But do not report it as "already built" — as of this
exact pass, `orchestrator.md` itself (the file Oga actually reads to decide what to do) has zero
lines implementing either half, the implementation that DOES exist elsewhere is uncommitted and
self-contradictory, and the full landing chain (wire gate 10's tag convention into `test_writer.md`,
reconcile the two `verify.py` gates, add the `coder.md` anti-gaming line, then validate blind per the
`H-AC-ORACLE-TARGET-1` precedent, then commit via `commit_diff_reread.py`) remains open work, tracked
under the four `fix_plan.md` entries named in Part 3.

---

## Part 5 — `research/radar.md` updates made by this pass

Appended a new subsection, `### Codex-diagnostic followup (2026-07-08) — new candidates`, to the
existing `## Compiler/typecheck-feedback prior art (2026-07-08 targeted dive)` section, with 8 new
rows (ReqToCode+Ariadne, traceSDD, R2Code, buf, openapi-diff, pact-js, spring-modulith, AdverTest) —
see `research/radar.md` directly for the exact rows. All 8 are genuinely new to the radar (confirmed
by grep before adding — none of these names appeared anywhere in `radar.md` before this pass). Did
NOT re-add anything already present (Spec Growth Engine, spec-kit, WM-SEMERU repo, Aider, Cline,
OpenHands, mini-swe-agent/SWE-agent, tdd-guard, dependency-cruiser, ArchUnit, tRPC/Zod/
openapi-typescript were all already rows). Added a matching change-log entry.

## Sources opened directly this pass (Part 2 + Part 3, beyond the 6 existing docs)

- https://arxiv.org/abs/2603.13999 , https://arxiv.org/html/2603.13999 , https://arxiv.org/pdf/2603.13999 (ReqToCode)
- https://arxiv.org/abs/2606.30689 , https://arxiv.org/html/2606.30689 (traceSDD)
- https://arxiv.org/abs/2604.22432 , https://arxiv.org/html/2604.22432 (R2Code)
- https://arxiv.org/abs/2602.08146 (AdverTest)
- https://github.com/bufbuild/buf
- https://github.com/OpenAPITools/openapi-diff
- https://github.com/pact-foundation/pact-js
- https://github.com/spring-projects/spring-modulith
- `loop-team/orchestrator.md` (full, direct Read, both halves)
- `loop-team/DESIGN_CHECKLIST.md` (full, direct Read)
- `fix_plan.md` lines 5074–5496 (direct Read)
- `loop-team/harness/verify.py` (full-file grep + targeted Read, live 704-line state)
- `loop-team/roles/coder.md`, `loop-team/roles/test_writer.md` (targeted grep)
- `git status` / `git diff --stat` / `git log` against the live `~/Claude/loop` working tree
- `research/radar.md` (full, direct Read, before editing)
