# Loop-Team Operating Standard — execute-what-it-says, self-improving, ADHD-friendly, multi-project

Author: 2026-07-11 synthesis. Grounds the standard in what was PROVEN this session + the research
(saved in `research/loop-team-reliability-adhd-dashboard-2026-07-11.md`, the 5 cross-domain briefs, and
`str-*`/`padsplit-*`/`cm-api-*` product research). This is the durable answer to Nnamdi's goal:
"standardized and actually execute what it said it did… self-improve… stay focused… visibility… verifiably
tell if it's really fixed… stay organized across multiple tools."

---

## 0. The core problem, named precisely
Empirically, "false success" — an agent claiming done while reality disagrees — is **75.8% of coding-agent
failures** (arXiv 2606.09863), and **an LLM judge cannot catch it** (AUROC ≤0.65) while a **deterministic
ground-truth check can** (0.83–0.95). So the fix is NOT a smarter agent or more prose rules — it is *cheap
code that reads ground truth the writer cannot fake*, plus *independent verification*, plus *visibility*.

## 1. The standardized loop (proven this session — 6 builds, all shipped)
Every non-trivial build runs this exact pipeline. No step is skippable; each is enforced structurally
where possible, by discipline otherwise.

```
spec (isolated in specs/, hash-bound)
  → PLAN-CHECK (independent Verifier reviews the SPEC before code; catches green-while-broken bugs)
  → TEST-WRITER (executable tests = the contract, written before code)
  → CODER (minimal impl; may NOT edit tests; pastes real command output; DECISION LOG)
  → ORCHESTRATOR GROUND-TRUTH RE-RUN (re-run the tests yourself; never relay a self-report)
  → INDEPENDENT POST-BUILD VERIFIER (re-runs + live-renders + mutation-checks the guards)
  → run_log.md (brief, spec, iterations, verdicts, summary)
```
**Evidence it works (this session):** the plan-check caught **6 real spec bugs at design time** (an
unsatisfiable type-check AC, two dashboard self-contradictions, a green-while-broken shell-wrap hole, an
arg-provenance gap, a conflicting pre-existing test) — *before* any buggy building. Every "done" was
re-verified against reality; two builds were mutation-tested (rip out the guard → the test must go red).

## 2. Unfakeable verification + visibility (the "verifiably tell if it's really fixed" requirement)
- **`reality_gate.py`** is the ONLY writer of `verified:true` in a product `status.json`, and it writes it
  ONLY after a git+test ground-truth check passes in the same call. An agent can write `"claimed"`; only
  the gate writes `"verified"`. (Proven: real commit → green; phantom commit → rejected.)
- **`product_dashboard.py`** renders every product's `status.json` as a board: green **VERIFIED** iff the
  gate confirmed it, amber **CLAIMED** if an agent merely said "fixed". One glanceable surface across all
  products. Run: `python3 loop-team/harness/product_dashboard.py` (default-globs `~/Claude/Projects/*/status.json`).
- **Per-product `status.json`** = the single source of truth (BUILT/DOING/BROKEN, evidence-linked). This
  is the ADHD "where am I / what's broken / is it really fixed" surface.

## 3. The 5 reliability principles (from cross-domain research → the mechanisms)
1. **Independent ground-truth verification** (dual-control drops false-success ~46%→3%; DNA MMR is a
   *second, independent* audit) → the post-build Verifier re-derives success from git/tests/live-render the
   Coder never touched. NEVER the writer grading itself.
2. **Layered gates, each catching a different class** (Swiss-cheese model; kinetic proofreading) →
   plan-check + reality-gate + live-smoke are independent slices; a defect must survive all.
3. **Requisite variety** (Ashby) → the Verifier's checking variety must match the failure-mode variety;
   `fix_plan.md` + `memory/` ARE the enumerated failure catalogue the lenses must cover.
4. **Structural, not instructional** (never-events; p53 checkpoints halt before propagation) → the highest-
   value rules are hooks that BLOCK, not prose the agent must remember. (This session: the gate stack.)
5. **Blameless postmortem → system change** (aviation ASRS; SRE) → every miss becomes a durable gate/
   memory, not a scolding. This is the self-improvement engine (§4).

## 4. Self-improvement mechanism (how the loop gets better without intervention)
Every surprising failure this session was written to BOTH `~/.claude/.../memory/` AND (where relevant) a
durable gate. The rule: **a miss is not "fixed" until it can't recur.**
- Found a gate bug → fixed the gate + wrote `feedback_spec_bound_credit_usage_suffix_bug.md` (incl. the
  turn-scoping discovery) so it never costs 2 hours again.
- Found the plan-check missing conflicting-test detection → logged as a standing lesson.
- Findings → memory (recall next session) + regression gates (mechanical re-check). Keep the Evaluator an
  EXTERNAL execution result (test exit code), never the actor re-reading itself (avoids Reflexion's
  degeneration-of-thought).

## 5. Prioritization framework (serial vs parallel — the decision you asked the system to make)
Decide by DEPENDENCY, not by vibe:
- **Parallel** across INDEPENDENT axes: different products (separate git worktrees), independent research
  streams, independent review lenses. (This session: 2 products' scoping + 5 cross-domain research streams
  ran in parallel; the two product builds are independent.)
- **Sequential** where dependencies force it: micro-steps WITHIN one build (interdependent), and any
  gate-before-build ordering (the reality-gate must exist before builds are trustworthy).
- **WIP-limit-1 for the HUMAN** (Nnamdi): the agents parallelize; the *dashboard* is your single surface so
  the ADHD context-switch tax lands on agents, not you. One product in "Doing" for your attention at a time.

## 6. Multi-project + Codex standardization
- Each product/repo gets its OWN `status.json` (matches "every repo needs its own tracker"); the dashboard
  rolls them up. No cross-repo `fix_plan.md` conflation.
- The SAME pipeline (§1) runs per product, in isolated worktrees, so N products build without interfering.
- **Codex**: the loop contract is platform-agnostic — the gates are prose+hooks, the trackers are
  status.json, the verification is git/test ground truth. Run the same spec→plan-check→coder→verify loop on
  Codex; point a `status.json` at that repo; the same dashboard shows it beside the others. (Codex-parity
  hook work already exists in `hooks/codex_*`.)

## 7. ADHD operating rules (from the evidence-based research)
- **Single source of truth** = the dashboard + per-product `status.json` (Barkley: externalize at the point
  of performance; Extended-Mind: the tracker IS part of your cognition — keep it ONE file, low load).
- **≤5 MUST-haves = the whole MVP**; everything else → a `## WON'T (this weekend)` list (MoSCoW; Full Scale).
- **Written DONE sentence per product**; when true, STOP (definition-of-done kills perpetual polish).
- **Parking lot** for every shiny tangent (discharges the Zeigarnik open-loop so it stops taxing memory).
- **50/10 work blocks**, always leave a "next tiny action" breadcrumb (avoid the blank-page restart).

## 8. Hardened this session vs. still-open roadmap
**Hardened + proven:** the gate stack unblocked (spec-bound credit `<usage>`-suffix bug fixed);
reality_gate.py + product_dashboard.py built + independently verified; run-log + spec-isolation discipline;
the full pipeline demonstrated end-to-end on 6 builds.
**Open (do next, ranked):**
1. **Make the credit turn-scoping robust** — it resets on every background-task completion; either honor the
   `.verifier_pass` flag (survives resets) or widen the window. (Biggest friction remaining.)
2. **Plan-check must grep for existing tests** on the functions being changed (missed the additive-vs-adapter
   conflict; caught at Test-writer instead). Add to the plan-check checklist.
3. **Auto-emit `status.json`** from the loop (a SubagentStop hook that updates the tracker as builds land) so
   the dashboard is live without manual writes — copy disler's hook→emit pattern.
4. **Convert more prose gates to structural hooks** (the 731-line orchestrator.md's load-bearing 20%).
5. **Retrospective e-triggers** over run logs (Safer-Dx style): auto-flag "test count dropped after a fix",
   "'done' with no test invocation" for review.

## 9. How to run it going forward (the runbook)
1. Per product: write a `status.json` (or `reality_gate.py init-status`), a DONE sentence, ≤5 MUST-haves.
2. For each build: spec (in `specs/`) → plan-check → test-writer → coder → **you (Oga) re-run the tests** →
   independent Verifier → run_log. Never accept a self-reported "done."
3. Gate discipline in THIS runtime: run plan-check + `repo_health_gate.py` + coder **foreground, back-to-back,
   no background completion between** (credit is turn-scoped until §8.1 lands). Verifier dispatches carry a
   `SPEC:` line + `SPEC_SHA256`; keep specs in `specs/` away from run logs.
4. Watch the dashboard for the true state; trust only green VERIFIED.
5. Every surprise → memory + a gate. That is the self-improvement loop.
```
```
See also: research/loop-team-reliability-adhd-dashboard-2026-07-11.md and the 5 cross-domain briefs
(medicine/biology/safety-science/control-theory/ADHD) for the full evidence base and citations.

See also: loop-team/orchestrator.md's Step 1 plan-check bullet list for the plan-size governor
(`plan_size_governor.py` — `SHIP_NARROW_PLAN`/`INVALID_PLAN_BOUNDARY`/`WITHIN_MVP_BOUNDARY`) mechanism's
full treatment, and research/2026-07-16-planning-stop-governor-internal-grounding-redteam.md for the
source research it implements — not restated here, per this file's own cite-by-reference discipline.
```
