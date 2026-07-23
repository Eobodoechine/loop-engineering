# loop-engineering

A team of agents that builds software and **verifies its own work against an
objective signal** — then applies the same discipline to itself. You hand it a brief;
an orchestrator (Oga) drives plan-check → test-writer → coder → **independent
verifier** in enforced micro-steps until the work passes a real gate, with every rule
backed by a deterministic check that can say *no*.

> **Propose → verify → feed back → repeat. The loop is only as good as its verifier,
> and a rule only counts if a check enforces it.**

_Status as of 2026-07-23._

## What is built and verified (today, on this tree)

| Layer | What | Evidence |
|---|---|---|
| Build loop | Oga + Test-writer + Coder + independent Verifier + Researcher, plan-check gate before any code, failure arbiter before any re-dispatch | `loop-team/orchestrator.md`, `loop-team/TEAM_RELATIONS.md` |
| **Custom Claude Code subagent types** | 5 project- and user-scope `.claude/agents/*.md` files (`coder`, `verifier`, `test-writer`, `researcher`, `plan-check-verifier`), each with `disallowedTools: Agent` — structurally prevents a dispatched sub-agent from spawning its own nested delegate chain, closing the sub-agent-punting failure at the tool-availability level rather than only the prompt level. Confirmed live (after a session restart) as real, selectable `subagent_type` values | `.claude/agents/*.md` (commit `c94918c`), `loop-team/orchestrator.md`'s dispatch-instructions section |
| **Plan-check hardening** | An exhaustive-enumeration rule (name every member of a finite class sharing a mutation pattern instead of discovering them one at a time across rounds) + a plan-check-mode-framing rule (state explicitly, after 2+ rounds, that no implementation is expected yet — a revision history describes spec-text corrections, not codebase state) + `LOOP-M5` in `loop-team/orchestrator.md`/`roles/verifier.md` | commit `22ba9ad` |
| **Adversarial-AC oracle targeting** | A hand-written cross-org security test can assert the *referenced* org's table stays empty — which passes green whether the ownership guard works, is silently narrowed, or is removed entirely, because a wrongly-written row lands under the *attacker's own* org, not the referenced one. This survived 10 plan-check rounds on a real build before being caught. `roles/test_writer.md` LOOP-M3 tags any SECURITY/cross-tenant acceptance test `[SECURITY-ORACLE]` at write time; `roles/adversarial_test_writer.md` Phase 3.5 then deliberately weakens the real guard in a scratch copy and requires the test go red before it's trusted; `roles/verifier.md` LOOP-M6 independently re-runs that mutation check rather than trusting the claim | `loop-team/DESIGN_CHECKLIST.md` gate 9, `loop-team/roles/test_writer.md`, `loop-team/roles/adversarial_test_writer.md`, `loop-team/roles/verifier.md` |
| **Binding-class saturation gate** | Compiler-catchable defects (unbound identifiers, missing imports, missing `'use client'`/`'use server'` directives) were burning many plan-check rounds as prose review that a real compiler run catches for free. `DESIGN_CHECKLIST.md` gate 10 gives an operational test for when a finding may be tagged `[BINDING]` ("would `tsc --noEmit`/`next build` literally reject this with zero code executed?"), three named compiler-invisible exclusions, and a 3-round stop condition; `harness/verify.py`'s new type-check gate (see Deterministic harness row) is the mechanical backstop | `loop-team/DESIGN_CHECKLIST.md` gate 10, `loop-team/orchestrator.md`, `loop-team/roles/coder.md` (`H-TYPECHECK-GATE-1`), `loop-team/roles/verifier.md` (LOOP-M7) |
| **5th Failure Arbiter class: `silent-throttle`** | A server-side tool rate limit that doesn't raise an exception — evidenced by a literal `rate_limit_error`/`too_many_requests`/`quota` string inside an otherwise-green tool result; classified BEFORE code-bug/test-bug/spec-gap on an unexpectedly clean or low-scoring result, routed to a same-step retry after backoff (never a re-dispatch or spec revision) | `loop-team/orchestrator.md`'s Failure Arbiter section (commit `5884604`) |
| **Reconciliation logic for parallel plan-check lenses** | `harness/reconcile_gap_records.py` — an orthogonality pre-filter, near-duplicate clustering (vendored from a real open-source implementation, `ai-code-reviewer`), a mandatory fresh-Verifier mechanism-trace trigger on full `mechanism_refs` overlap between two findings, fail-closed contradiction handling with a bounded (1-attempt) tie-break retry; backed by two rounds of research confirming no off-the-shelf tool solves compositional cross-round conflict detection | `loop-team/harness/reconcile_gap_records.py` (commit `5a4c8d4`) |
| **Micro-step enforcement** | Five deterministic gates in Claude Code hooks (table below) + a shadow erosion gate | `hooks/` |
| Deterministic harness | `verify.py` (zero-test runs force-fail; Node/vitest repos supported, dual-ecosystem results AND-ed), live-smoke URL checker with layer-classified verdicts, stall detector, additive baseline-scoped TypeScript type-check gate (`tsc --noEmit`, fails only on error fingerprints new since a persisted `.loop_type_check_baseline.json`, inert on non-TypeScript projects) | `loop-team/harness/` |
| Verifier-for-the-verifier | Frozen regression cases (15/15 deterministic traps caught, incl. 2 erosion traps + a hard-good over-rejection guard), per-target case lint | `loop-team/evals/run_evals.py` → `SUITE: GREEN` |
| **Fault-injection ratchet** | 7-family deterministic injector over real run artifacts (gold = the injection log, never judge consensus), fail-closed PII sanitizer/emitter, 21-case blind batch (opaque ids), two-tier × two-round scoring with a completeness gate and an exhaustive decision table (control-accuracy preconditions, band agreement, min-n) | `loop-team/evals/fault_injection/` (113 tests incl. 43 adversarial); first live measurement: strong-tier 21.4% trap accuracy → suite audit confirmed 6 real verifier holes (count-reconciliation, target cross-refs) + 5 gold repairs queued |
| **Review-to-commit re-diff gate** | Content can land in a `git commit` diff without ever being reviewed — confirmed twice in one session (one reverted, one an unrelated ~230-word paragraph that rode along undetected for hours). `harness/commit_diff_reread.py` re-hashes a file's exact reviewed bytes and refuses a commit — for any number of listed files, all-or-nothing — unless every one still matches its last recorded snapshot, closing the TOCTOU window a caller sequencing separate checks across turns would leave open. **Hook-enforced on two hook events, not just instructional:** a `hooks/loop_stop_guard.py` Stop-hook gate detects a raw `git commit` (bypassing the tool above) touching a scope-listed file — extracting the real commit SHA from the Bash tool_use's own success line, `git show`-ing it, and blocking the Stop if any scope-listed file was touched. **A dispatched sub-agent's own raw commit (invisible to `Stop`, which only fires for Oga's own turn) is now ALSO covered**, via a two-layer bridge: a `SubagentStop`-side detector (`hooks/subagent_stop_gate.py`) writes a flag file on a hit, which Oga's `Stop` hook checks and blocks on (primary, authoritative path); a direct scan of the sub-agent's own transcript file runs as a defense-in-depth backstop for the async-dispatch-ordering race the flag alone can't close (secondary, since it depends on an undocumented Claude Code directory layout). Shared detection logic lives in one pure module (`hooks/commit_scope_scan.py`) both hooks call — zero duplication. Known, accepted residual: if two sub-agents violate in the same turn and only one has a landed flag, the other's violation can be masked this turn (not permanently — tracked separately, `H-SUBAGENT-MASKING-1`) | `loop-team/harness/commit_diff_reread.py` (18 tests), `hooks/loop_stop_guard.py`'s "Gate: raw git commit..." + Layer 1/2 sections, `hooks/subagent_stop_gate.py`'s 4th responsibility, `hooks/commit_scope_scan.py` (82 new tests across both hook test files), `loop-team/orchestrator.md`'s "Review-to-commit re-diff" section (`H-REVIEW-COMMIT-1`, `H-SUBAGENT-COMMIT-GATE-1`) |
| **Full prior-attempt history for Coder retries** | A retry-2 Coder dispatch previously had no stated rule to include what retry-1 already tried and was rejected for — risking a wasted retry re-discovering the same dead end. Every Coder re-dispatch after a red result now carries the full sequence of prior diffs + DECISION LOGs for that step, reconciled against the existing decision-log-withholding rule with an explicit, narrowly-scoped carve-out (same step only) | `loop-team/orchestrator.md` step 5 + micro-step loop item 4, `loop-team/roles/coder.md`'s "Prior attempts considered" section |
| **Rule-1 denylist scoping fix** | The research-authenticity check's placeholder-token rule flagged a legitimate `n/a` in a conditionally-optional field (Mode D's `code_pattern`/`constraints`) identically to real degenerate output. Scoped the exemption narrowly to `{"n/a", "na"}` for those specific fields only — every other placeholder token, and every non-optional field including `source` (where the original real incident's placeholder actually landed), remains fully checked | `loop-team/harness/research_authenticity_check.py` (`MODE_OPTIONAL_FIELDS`/`ABSENCE_TOKENS`), closes `fix_plan.md`'s `H-DEGENERATE-OUTPUT-1` follow-up |
| **Priority-ranked context handoff** | Adapts a background-thread session-memory-compaction pattern into a discipline this framework can actually run: Oga maintains a running, priority-ordered run-log summary at each micro-step checkpoint — corrections > errors > active work > completed work — instead of reconstructing context from memory when a later dispatch needs it. Each tier is defined against real framework artifacts (`PLAN_FAIL` gap records, the 6 Failure Arbiter classes, "Prior attempts considered" entries, checkpoint commits), not abstract categories; explicitly states what mechanism doesn't transfer (no literal background thread — Oga has no host process to run one on) rather than silently dropping it | `loop-team/orchestrator.md`'s "Priority-ranked context handoff" section, `RUN.md` |
| **5th plan-check technique: state-transition-table enumeration** | The 4 adversarial plan-check lenses are all narrative — read the spec and react to what stands out. A structurally different 5th technique builds the state × consequence grid FIRST, before any narrative reasoning, and traces every cell — catching a missing row (an omission the spec never addresses at all) rather than a flawed sentence, the failure class narrative review is structurally unable to see. Confirmed by two independent real incidents, not one: a 20-round-reviewed spec that still had 2 uncaught gaps, and a 3-round-reviewed spec with an entire unaddressed state (a fixed defect recurring after closure). Dispatched under the same 3 trigger conditions as the narrative lenses, not a separately-gated one | `loop-team/orchestrator.md`'s parallel-lens dispatch section |
| Honest acceptance | **PACE** anytime-valid commit gate (Monte-Carlo verified false-accept ≤ α); **MVVP** judge validation (chance-corrected κ, position-swap, test-retest); adversarial hard-case ratchet | `loop-team/evals/acceptor.py --selftest`, `judge_validate.py` |
| Execution grounding | Deterministic lanes that recompute facts in code — arithmetic checks, recorded-fetch contradiction routing, citation grounding (code owns evidence IDs), erosion metrics | `loop-team/evals/`, `hooks/slop_gate.py` |

**Test suite (this exact checkout, `python3 -m pytest hooks/ loop-team/ -q`): 1021 passing,
11 failing, 6 skipped, 56 subtests passed.** The 11 failures are the same
pre-existing/environmental set as before (a missing `radon` binary, a known
self-referential "suite: green" string-match, a pre-existing erosion-eval bucket
mismatch) — confirmed unrelated to this update both by matching the exact same failure
categories/count already documented here, and by checking that none of the 11 failing
test files were touched by any commit in this session in a way that affects those
specific classes. Cited honestly rather than as a bare "1021 passing" because 11 tests
in the same run are red.

### The five deterministic gates (the micro-step loop)

| Gate | Rule it enforces | On violation |
|---|---|---|
| Thrash-past-green | A green checkpoint is committed before any further coding can bury it | Stop blocked: "commit the green state" |
| Step-size | ≤ 200 changed code lines per micro-step | Stop blocked: commit (WIP if red) first |
| Retry-cap | Same failure signature never gets a third blind retry | Stop blocked: escalate to research |
| Testmon impact gate | The tests a change can break actually ran green; untested new modules can't slip through | Stop blocked: failing tests / orphan module |
| Dispatch hygiene | A Verifier is never primed with prior results or the coder's reasoning | Stop blocked: re-dispatch clean, spec by path |

The **slop gate** (SlopCodeBench-style erosion metrics on radon) runs in SHADOW mode —
it logs a verdict at every checkpoint but never blocks. Arming it is deliberately
deferred: threshold calibration on this repo's history is still degenerate (most
commit transitions have zero erosion delta), and a gate that false-blocks teaches
agents to route around gates. After 5–10 shadow runs, thresholds get fitted to
accepted transitions and arming becomes a measured, PACE-gated decision.

## Quickstart

See **[QUICKSTART.md](QUICKSTART.md)** — clone → run the harness on the shipped
example → install the five hooks (**[hooks/README.md](hooks/README.md)** has the full
`settings.json` block and per-hook verification) → watch a gate refuse an oversized
diff with your own eyes → first real run. The orchestrator entry point ships as
[skills/loop-team.SKILL.template.md](skills/loop-team.SKILL.template.md) +
[.loop-team-config.example](.loop-team-config.example).

**Other runtimes:** the playbooks and CLI tools run anywhere (OpenAI Codex CLI has
imported and used them — user report). Codex CLI, Gemini CLI, and Cursor now ship
Claude-style hooks, so the enforcement layer ports as adapters — the honest
per-runtime map, caveats, and effort-marked backlog live in
**[PORTABILITY.md](PORTABILITY.md)**.

## Lessons this project paid for (distilled)

1. **Verify the world, not the words.** An `import` check passed while the browser
   binary was missing; a documented URL 404'd silently. Execute the real thing.
2. **A green suite can prove nothing.** Zero-tests-collected once read as success;
   the harness now force-fails it.
3. **Fixture tautology.** Tests crafted to match a regex prove the regex matches the
   fixture. Fixtures must use the real labels/content the system produces.
4. **Citation fabrication is a capability problem.** A verifier invented GitHub issue
   numbers as "evidence." Code now owns evidence IDs; models only reference them.
5. **Over-rejection is an invocation artifact.** Terse forced verdicts over-reject;
   reasoning room fixes it. Both failure directions get graded.
6. **Text suites saturate.** Cases with incontestable gold are, by construction,
   reachable by a careful read — both model tiers hit the ceiling. Durable gains come
   from execution grounding, not harder prose.
7. **Blob-level checks must be specified against the real corpus they scan.** A
   leak-marker list matched the verifier role file's own output instructions —
   role-text subtraction fixed it.
8. **A detector must sweep its own home.** Marker literals kept reappearing in the
   detector's comments, tests, and docs — seven self-catches in one day. The sweep
   test is load-bearing.
9. **Pipes mask exit codes.** `pytest | tail` reported the pipe's success and a red
   suite got committed — twice. Gates now check exit codes unpiped.
10. **Same-second, same-size edits run stale bytecode.** Python's mtime+size pyc
    check let a broken function report "1 passed." The gates set
    `PYTHONDONTWRITEBYTECODE=1`.
11. **The published artifact is HEAD, not your working tree.** A freshness gate that
    grepped the filesystem would have waved through a stale committed README — the
    exact forgot-to-commit case it existed to catch.
12. **A prompt-only "don't spawn sub-agents" rule doesn't hold under real dispatch
    pressure.** A general-purpose sub-agent told not to delegate spawned its own child
    anyway (an orphaned research helper kept running after its parent returned). The
    fix had to move from prose to the tool layer: custom Claude Code subagent types
    with `disallowedTools: Agent`, so a dispatched worker is structurally incapable of
    spawning a delegate chain, not just instructed not to.
13. **Reviewing a diff once is not the same as reviewing what you commit.** Content
    landed in a `git commit` twice without ever being reviewed as part of that commit —
    once reverted in real time, once undetected for hours (an unrelated paragraph rode
    along inside a commit about something else entirely). A re-diff immediately before
    every commit, re-hashed against exactly what was reviewed, closes the gap
    independent of root cause — reviewing the diff you were shown once is not a
    guarantee about the bytes that actually land.
14. **Enumeration-first review catches what narrative review structurally cannot.** Four
    independent narrative plan-check lenses, run across three separate rounds on the same
    spec, all missed the same thing: an entire unaddressed state (a fixed defect that
    later recurs), because a narrative reader reads the rule that's THERE and reacts to
    it — an omitted state is invisible to that method by construction. A fifth technique
    — build the full state × consequence grid FIRST, before any prose reasoning, and
    trace every cell — found it immediately. The two techniques catch different failure
    shapes: narrative lenses catch a flawed sentence; enumeration catches a missing row.
    Neither substitutes for the other.

## Future steps

- **Fault-injection round 2** — apply the audited gold repairs (5 traps + 1 control),
  re-measure with reason-grounded catch scoring, freeze the band placement, then point
  the prompt optimizer at the confirmed verifier holes (never hand-patch the prompt
  against the suite that measures it).
- **Reproduction-oracle lane** — a FAIL claim ships an executable repro or an
  explicit reproduction-impossible declaration (the strongest measured oracle signal).
- **Trajectory-check case family** — deterministic detection of
  destroyed-own-correct-patch failures from run traces.
- **Slop-gate arming** (after shadow calibration) and Stop-hook `additionalContext`
  upgrades (corrective feedback instead of bare blocks).
- **Worker swap** (Phase 2): a battle-tested coding agent behind the same verifier +
  eval suite, proven non-regressing before adoption.
- **Portability backlog** — pre-commit/CI package, per-runtime hook adapters and
  templates (see PORTABILITY.md).
- **Self-improvement (Phase 5) hard rules, decided in advance:** the rewritable set
  permanently excludes `verify.py`, the eval cases, the acceptor, and the hooks —
  enforced at the hook layer; role rewrites are never gated on LLM-attributed blame;
  acceptance uses an out-of-family judge or a deterministic gate.

## Reading path

`loop-team/orchestrator.md` (the method) → `loop-team/TEAM_RELATIONS.md` (who is told
what — and what is withheld) → `loop-team/roles/` (verifier.md is the heart) →
`loop-team/evals/README.md` (the measurement layer) → `hooks/README.md` (enforcement)
→ `PORTABILITY.md`. Private per-installation files (a fix_plan gate-hole log, personal
rubrics) are referenced with "skip if missing" semantics throughout — you start
without them and accrete your own.

## Publishing model

This public tree is a single-commit snapshot published by
`scripts/snapshot-publish.sh`: tracked-content-only (`git archive`), a fail-closed PII
gate, generated-output home-path redaction, a **README date-stamp gate** — a push whose
HEAD README stamp predates the HEAD commit date aborts — and a **mechanical
since-last-publish gate**: a marker file
(`.loop-publish-meta.json`) records the MAIN commit published last time, and a publish
whose README is untouched (or touched only on the `Status as of` line) since that
recorded commit fails closed with a message naming which case fired, distinct from the
date-stamp check. This closes the exact gap that let a stamp-only bump pass previously
— what you read here is, enforced-by-construction, the state it describes. License: MIT.
Exact local paths may appear in private research evidence when they are needed to prove
a claim; the generated public snapshot redacts the current user's home prefix before the
privacy scan. Real credentials and key-shaped leaks are never redacted or excused by that
path rule: ordinary files still fail closed, with only narrow detector-tooling examples
excluded from the real-key self-match check.

### Full-history publish pipeline (building blocks, not yet wired into one command)

Separate from the single-commit snapshot method above, `loop-team/harness/` has five
standalone, independently-testable scripts for a *full-git-history* publish path —
walking and cleaning every commit reachable from any ref, not just HEAD:

- `verified_mirror_clone.py` — makes a disposable `git clone --mirror` and
  independently diffs `git for-each-ref` between source and mirror, failing loudly on
  any ref mismatch before anything downstream trusts the clone.
- `identity_audit.py` — read-only; walks every commit's author/committer identity plus
  hostname-shaped strings in commit messages to build a JSON marker superset consumed
  by the scanner below.
- `full_history_scan.py` — walks every commit via `git rev-list --all`, regex-scans the
  raw bytes of every blob (binaries included, never text-mode-only) for identity
  markers/home-paths/emails/API-key shapes, and always flags gitlinks for manual review
  rather than letting them silently clear a run as "clean."
- `path_removal.py` — wraps `git filter-repo --path public/ --path runs/ --path
  loop-team/runs/ --invert-paths --force` against a disposable mirror only, plus a
  commit-callback that unconditionally drops gitlink entries (mode `160000`) that
  `--invert-paths` alone does not reliably strip.
- `tree_verify.py` — an independent, from-scratch re-walk of every commit's tree
  (shares no code with `path_removal.py` or the scanner) proving zero `public/`,
  `runs/`, or `loop-team/runs/` paths remain anywhere in history.

These compose clone → scan → remove → verify but have no combining top-level command
yet — run each with `--help` or read its module docstring for usage.

## Recent changes (auto-published 2026-07-04)

- docs(hooks): document git-native hooks (pii-guard, auto-publish-on-commit)
- H-DASHBOARD-READTRACE-IMPORT-1: import the real runner/run_trace.read_trace, not a nonexistent trace.py
- H-DISPATCH-FALSEPASS-SUBSTRING-1: parse verifier verdict from an anchored line, not a raw substring match
- H-HYGIENE-SCAN-SOURCE-EMBED-FP-1: don't flag embedded source code as a hygiene-marker false positive
- H-EVALS-RADON-MISSING-1: install radon + add graceful skip when radon is unavailable
- H-VERIFY-BUILD-VITEST-HANG-1: exclude real external-repo Vitest test from default pytest sweep

## Recent changes (auto-published 2026-07-04)

- H-MALFORMED-RUN-DIRS-1: exclude backtick/backslash from subagent_stop_gate.py's run-dir capture regex

## Recent changes (auto-published 2026-07-07)

- Mark nested-pytest VAC5 test slow; add TimeoutExpired safety net

## Recent changes (auto-published 2026-07-07)

- Reconcile two verification claims from the 2026-07-04 diagnostic report

## Recent changes (auto-published 2026-07-08)

- Fix malformed-CLI IndexError crashes and untracked .testmondata* noise

## Recent changes (auto-published 2026-07-08)

- Fix SKILL.md/template two-way drift + add structural regression coverage

## Recent changes (auto-published 2026-07-09)

- Revert exploitable Coder-dispatch detection heuristics; fix adjacency self-match + SessionStart hookEventName
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research

## Recent changes (auto-published 2026-07-09)

- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-09)

- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-10)

- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-10)

- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-10)

- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-10)

- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-10)

- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-10)

- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-10)

- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-10)

- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-10)

- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-12)

- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-15)

- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-15)

- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-15)

- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-16)

- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-16)

- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-16)

- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate
- Revert exploitable Coder-dispatch detection heuristics; fix adjacency self-match + SessionStart hookEventName
- Fix SKILL.md/template two-way drift + add structural regression coverage

## Recent changes (auto-published 2026-07-17)

- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate
- Revert exploitable Coder-dispatch detection heuristics; fix adjacency self-match + SessionStart hookEventName

## Recent changes (auto-published 2026-07-17)

- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify
- Add adversarial-AC oracle-targeting gate and binding-class/type-check saturation gate

## Recent changes (auto-published 2026-07-17)

- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research
- Add full-git-history publish pipeline: clone, scan, remove, verify

## Recent changes (auto-published 2026-07-17)

- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline
- Save research: goal-drift/claim-ledger design, compiler-gate design trail, misc project research

## Recent changes (auto-published 2026-07-17)

- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate
- Add session notes; docs(README): document type-check gate, oracle-targeting/binding-class gates, full-history publish pipeline

## Recent changes (auto-published 2026-07-17)

- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output
- Add plan-check saturation gate

## Recent changes (auto-published 2026-07-17)

- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips
- Clarify harness skip and warning output

## Recent changes (auto-published 2026-07-17)

- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)
- Eliminate harness environment skips

## Recent changes (auto-published 2026-07-17)

- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)
- Add run_and_record.py: producer-anchored evidence snapshots (evidence-gate Phase 1, micro-step 1/2)

## Recent changes (auto-published 2026-07-17)

- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha
- Upgrade fixplan_closure_lint.py to v2: proof-block-required + snapshot-cross-check (evidence-gate Phase 1, micro-step 2/2)

## Recent changes (auto-published 2026-07-17)

- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)
- learnings: document the evidence-gate Phase 1 5-round plan-check chain + post-commit hook timeout gotcha

## Recent changes (auto-published 2026-07-17)

- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident
- Add freshness + dirty-worktree checks to fixplan_closure_lint.py v3 (evidence-gate Phase 2)

## Recent changes (auto-published 2026-07-17)

- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)
- learnings: document evidence-gate Phase 2 close-out + post-commit hook branch-switch incident

## Recent changes (auto-published 2026-07-17)

- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson
- Add gitignore-visibility check to dirty-worktree detection (evidence-gate Phase 2b)

## Recent changes (auto-published 2026-07-17)

- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator
- learnings: document Phase 2b close-out + the git-status-omits-gitignored-paths lesson

## Recent changes (auto-published 2026-07-17)

- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)
- Add LOOP-M8/LOOP-M9 live-verification rules to verifier + orchestrator

## Recent changes (auto-published 2026-07-17)

- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry
- Add --selftest flag to fixplan_closure_lint.py v4 (evidence-gate Phase 3)

## Recent changes (auto-published 2026-07-17)

- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)
- Close out evidence-gate Phase 3 (--selftest): learnings entry

## Recent changes (auto-published 2026-07-17)

- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)
- Add closure_touch_scan.py + check_single_heading (evidence-gate Phase 4, micro-step 1/3)

## Recent changes (auto-published 2026-07-17)

- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates
- Add Part B (sub-agent closure detection) to subagent_stop_gate.py (evidence-gate Phase 4, micro-step 2/3)

## Recent changes (auto-published 2026-07-17)

- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90
- Add --out flag to reconcile_gap_records.py + wire it into orchestrator/verifier gates

## Recent changes (auto-published 2026-07-17)

- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)
- Remove dangling (D.1) cross-file reference from orchestrator.md line 90

## Recent changes (auto-published 2026-07-17)

- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry
- Add Parts C/D/E + corrected PLAN_CHECK fix to loop_stop_guard.py (evidence-gate Phase 4, micro-step 3/3)

## Recent changes (auto-published 2026-07-17)

- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E
- Close out evidence-gate Phase 4 (Stop-hook wiring): learnings entry

## Recent changes (auto-published 2026-07-17)

- feat(runner): add Codex containment and pilot governance
- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry
- Evidence-Gate Phase 5: freshness sweep, mutation-test regression, evidence ledger, genre E

## Recent changes (auto-published 2026-07-17)

- wip(runner): checkpoint pilot preparation hardening
- feat(runner): add Codex containment and pilot governance
- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.
- Evidence-Gate Phase 5 close-out: learnings.md entry

## Recent changes (auto-published 2026-07-17)

- docs(runner): track pilot authority contract
- wip(runner): checkpoint pilot preparation hardening
- feat(runner): add Codex containment and pilot governance
- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study
- Add repo-health gate: freeze new-capability Coder dispatches on a repo with unresolved recurring bug classes or 2+ open hardening items.

## Recent changes (auto-published 2026-07-17)

- wip(runner): checkpoint product pilot verifier repairs
- docs(runner): track pilot authority contract
- wip(runner): checkpoint pilot preparation hardening
- feat(runner): add Codex containment and pilot governance
- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites
- Save research from the TaxAhead/PadSplit structure review and build-vs-debug study

## Recent changes (auto-published 2026-07-17)

- feat(pilot): harden product oracle authority
- wip(runner): checkpoint product pilot verifier repairs
- docs(runner): track pilot authority contract
- wip(runner): checkpoint pilot preparation hardening
- feat(runner): add Codex containment and pilot governance
- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern
- Fix H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1: exclude blocked/never-executed dispatches from all 5 replay-detection sites

## Recent changes (auto-published 2026-07-17)

- test(adapter): accept cleanup completion timestamp
- feat(pilot): harden product oracle authority
- wip(runner): checkpoint product pilot verifier repairs
- docs(runner): track pilot authority contract
- wip(runner): checkpoint pilot preparation hardening
- feat(runner): add Codex containment and pilot governance
- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug
- Close PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1: 3 remaining files fixed via pre-clear pattern

## Recent changes (auto-published 2026-07-17)

- Fix stale plan_pass_result() helper in test_loop_stop_guard_dual_window_fix.py
- test(adapter): accept cleanup completion timestamp
- feat(pilot): harden product oracle authority
- wip(runner): checkpoint product pilot verifier repairs
- docs(runner): track pilot authority contract
- wip(runner): checkpoint pilot preparation hardening
- feat(runner): add Codex containment and pilot governance
- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)
- Fix PII-scanner self-trip: full_history_scan.py's own regex matched itself, and snapshot-publish.sh's privacy gate blocked legitimate research-path citations
- Add adversarial-review findings-persistence scanner
- Add reality_gate/product_dashboard/status_claim_audit monitoring stack
- Add plan-check lens completion barrier, strict gap-record schema, and fix reconcile_gap_records.py near-duplicate clustering bug

## Recent changes (auto-published 2026-07-17)

- fix(runner): close preflight tautology gap with real-binary argv acceptance check
- fix(runner): move --ask-for-approval before exec subcommand in both argv builders
- test(runner): add real-binary regression tests for codex exec argv ordering bug
- fix(hooks): add Codex-side exact worker identity guard
- Fix stale plan_pass_result() helper in test_loop_stop_guard_dual_window_fix.py
- test(adapter): accept cleanup completion timestamp
- feat(pilot): harden product oracle authority
- wip(runner): checkpoint product pilot verifier repairs
- docs(runner): track pilot authority contract
- wip(runner): checkpoint pilot preparation hardening
- feat(runner): add Codex containment and pilot governance
- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)
- Save TaxAhead Gmail connector research (read-only docs)
- Save padsplit-cockpit and general loop-process research (read-only docs)
- Append process learnings and radar updates (purely additive)

## Recent changes (auto-published 2026-07-17)

- docs(loop-team): add codex-exec-approval-flag-fix lessons to learnings.md
- docs(research): add Claude+OpenAI role-pairing dossier (2026-07-17)
- docs(loop-team): log model-routing/Claude+Codex backlog for Mission Control triage
- fix(runner): close preflight tautology gap with real-binary argv acceptance check
- fix(runner): move --ask-for-approval before exec subcommand in both argv builders
- test(runner): add real-binary regression tests for codex exec argv ordering bug
- fix(hooks): add Codex-side exact worker identity guard
- Fix stale plan_pass_result() helper in test_loop_stop_guard_dual_window_fix.py
- test(adapter): accept cleanup completion timestamp
- feat(pilot): harden product oracle authority
- wip(runner): checkpoint product pilot verifier repairs
- docs(runner): track pilot authority contract
- wip(runner): checkpoint pilot preparation hardening
- feat(runner): add Codex containment and pilot governance
- feat(experiments): add sealed model routing lane
- feat(harness): add read-only reconciliation manifests
- feat(harness): add Claude role runner bridge
- fix(loop-team): neutralize invalid verifier support attempts
- test: cover snapshot publish safety oracles
- test: cover strict plan-check saturation records
- test: cover fix-plan closure phase four
- Publish Loop harness completion status
- Fix credit-gate usage-trailer structural block (H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1)
- Harden plan-check evidence and worker identity guards
- gitignore: exclude registered worktrees and transient runtime state
- Preserve fix_plan.md 2026-07-15 migration backup
- Add TaxAhead/Cockpit reconciliation artifacts + control-plane project config
- research: ADHD control-plane dashboard UX research + deep-research JSON (2026-07-12)
- research: PadSplit Cockpit business/legal/feature-catalogue sweep (2026-07-12)
- research: V9 hermetic dependency closure + worktree reconciliation tooling (2026-07-14)
- research: Claude usage/credit-reduction options + pxpipe domain/security (2026-07-14/15)
- research: Codex-parity and consent-installer session continuation (2026-07-09)
- research: TaxAhead vitest process-attribution cluster (2026-07-15)
- research: git/worktree multi-way reconciliation methodology (2026-07-16)
- research: credit-gate usage-trailer fix spec + dossier
- research: worker-identity / Oga-guard investigation dossiers (2026-07-16)
- research: planning-stop-governor synthesis + 6 source dossiers (2026-07-16)
- learnings.md: append 12 dated retrospective entries (2026-07-12 to 2026-07-16)
- Fix status_claim_audit.py heading-granularity misattribution (H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1)
- Add loop-g11-analysis-transition run artifacts (gen-8 PLAN_PASS, verified complete)
- Land concurrent hook-lane fixes: is_verifier_dispatch scoping + 5-file suite (58->0)
- Tighten LOOP_GATE: PLAN_PASSagentId: glue check against decoy suffixes
- Fix LOOP_GATE: PLAN_PASS exact-equality check to tolerate glued agentId: suffix
- Fix spec-bound Verifier/Coder credit gate: turn-boundary blindness + agentId-concat hash gap
- control-plane dashboard v1 redesign: micro-step 3 (AC10) + AC8 close
- control-plane dashboard v1 redesign: micro-step 2 (AC4/AC5/AC6/AC7)
- control-plane dashboard v1 redesign: tests + micro-step 1 (AC2/AC3/AC9)
- learnings: port 2 control-plane-dashboard lessons (credit-gate bg-vs-fg; green-suite missed operative AC7)
- Integrate control-plane dashboard into product_dashboard.py (built+verified in worktree)
- Save Zillow rental-search live findings (read-only doc)

## Recent changes (auto-published 2026-07-18)

- Fix Oga guard identity and publish gates

## Recent changes (auto-published 2026-07-18)

- Add subscription benchmark safeguards

## Recent changes (auto-published 2026-07-18)

- Harden loop-team dispatch and coder gates
- Add subscription benchmark safeguards

## Recent changes (auto-published 2026-07-18)

- Fix plan size governor spec wording
- Harden loop-team dispatch and coder gates
- Add subscription benchmark safeguards

## Recent changes (auto-published 2026-07-19)

- Add plan-size governor: SHIP_NARROW_PLAN/WITHIN_MVP_BOUNDARY/INVALID_PLAN_BOUNDARY

## Recent changes (auto-published 2026-07-19)

- Scope verifier-dispatch detection to current turn + agent_type; refine adjacency gate for plan-check vs post-build

## Recent changes (auto-published 2026-07-19)

- fix(spec-gate): tolerate markdown code fences in verifier output + strong/weak coder signal split

## Recent changes (auto-published 2026-07-19)

- spec(plan-size-governor): update status block with rounds 8-15 plan-check history

## Recent changes (auto-published 2026-07-19)

- test(plan-size-governor): break APFS clones so pytest resolves rootdir to main

## Recent changes (auto-published 2026-07-19)

- learnings: APFS clone rootdir redirect lesson from plan-size-governor build

## Recent changes (auto-published 2026-07-20)

- fix: plan-check-verifier Bash access + agentId trailing-line tolerance

## Recent changes (auto-published 2026-07-20)

- chore: mark TAXAHEAD recurring class closed and log gate evidence

## Recent changes (auto-published 2026-07-20)

- chore: add follow-up research and e2e verification artifacts

## Recent changes (auto-published 2026-07-21)

- Add plan-check credit output helper — permanently fix PLAN_SUPPORT_JSON format failures

## Recent changes (auto-published 2026-07-21)

- Add credit output helper + tests + TaxAhead KB audit

## Recent changes (auto-published 2026-07-21)

- WIP (RED): tests for plan_check_credit_output.py LOOP_GATE format fix

## Recent changes (auto-published 2026-07-21)

- fix: emit LOOP_GATE: PLAN_PASS/PLAN_FAIL from plan_check_credit_output.py

## Recent changes (auto-published 2026-07-22)

- chore(ledger): close PADSPLIT-ALLOWLIST-DRIFT-1 and PADSPLIT-UNVALIDATED-INGRESS-1

## Recent changes (auto-published 2026-07-23)

- fix(hooks): wire orphaned .verifier_pass flag into spec-bound credit gate

## Recent changes (auto-published 2026-07-23)

- fix(hooks): tolerant repo-health classification default when markers missing
