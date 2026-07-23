# Deep-research: production multi-agent AI coding systems — writer/verifier/test loop design

**Run date:** 2026-07-09
**Mechanism:** `deep-research` skill / Workflow (`wf_49a20caf-ea0`), 110 sub-agents, 819 tool uses, adversarial 3-vote claim verification, ~6.15M sub-agent tokens.
**Journal (full per-agent transcripts, do not bulk-read):** `<HOME>/.claude/projects/-Users-eobodoechine/682bb744-1325-4b77-9e21-10f7a8c865fd/subagents/workflows/wf_49a20caf-ea0/journal.jsonl`
**Reproduce/extend:** `Workflow({scriptPath: '<HOME>/.claude/projects/-Users-eobodoechine/682bb744-1325-4b77-9e21-10f7a8c865fd/workflows/scripts/deep-research-wf_49a20caf-ea0.js', resumeFromRunId: 'wf_49a20caf-ea0', args: ...})`

## Question researched

Survey production-grade multi-agent AI coding systems and frameworks (MetaGPT, ZeroRepo/RPG, SWT-Bench, Agentless, SWE-Doctor, AutoSafeCoder, DARS, L2MAC, Lingma SWE-GPT, AutoGen, OpenHands/OpenDevin, SWE-agent, Cognition's Devin, Aider, CrewAI, LangGraph, Anthropic's property-based-testing agent, and others) on: (1) how they structure writer/verifier/test loops to produce well-tested software with low escaped-bug rates, (2) how they maintain project structure/milestone discipline across long multi-phase builds, (3) concrete techniques (mutation testing, property-based testing, per-step verification, impact-mapped test selection, adversarial spec review) that measurably reduce bugs — grounded in real, retrieved sources, with a "what's directly applicable" section for a solo writer→verifier→fix loop (Test-writer → Coder → Verifier, + Researcher).

## Synthesis

Across MetaGPT, ZeroRepo/RPG, SWT-Bench, Agentless, SWE-Doctor, AutoSafeCoder, DARS, L2MAC, Lingma SWE-GPT, and Anthropic's property-based-testing agent, the strongest and most repeatable lever for cutting escaped bugs is the same everywhere: **generate tests from spec before or alongside the code, then gate progress on actually executing those tests (not static self-review), inside a bounded retry loop (3–8 iterations is typical) rather than an open-ended one.**

This single mechanism produces the largest measured deltas in the literature:
- Agentless's SWE-bench-Lite ablation: 77→96/300 fixes (+15) from adding LLM-generated reproduction tests.
- MetaGPT: +4.2pp / +5.4pp Pass@1 (HumanEval/MBPP) from executable feedback vs. an ablation without it.
- ZeroRepo: 27.3/35.8-point lead over Claude Code CLI from graph-planned TDD applied at every leaf node.

**Long-horizon coherence** across multi-phase builds is preserved not by bigger context windows but by imposing *external structure*:
- MetaGPT's document-mediated, publish-subscribe message pool (agents exchange structured documents/diagrams, not free-form dialogue; each role pulls only role-relevant messages from a shared pool).
- ZeroRepo's Repository Planning Graph with staged unit → regression → integration verification.
- L2MAC's von-Neumann-style instruction-register/file-store split.

All three are explicitly built to counter a documented failure mode where single-agent trajectories of 30–40 turns become uninterpretable and undebuggable.

**Three further concrete techniques** show measured bug-rate reductions beyond plain pass/fail testing:
- LLM-generated mutation testing with an LLM equivalence-mutant filter (Meta's ACH): 0.79→0.95 precision, 73% engineer test-acceptance in production.
- Dual static+dynamic/fuzzing feedback loops (AutoSafeCoder): −13pp vulnerability rate.
- Execution-feedback-guided search over linear/random sampling (DARS): 47% Pass@1 on SWE-Bench Lite.

**Useful negative case:** Lingma SWE-GPT ships with *no* test-execution verification (only syntax/lint self-correction) and self-reports this as its principal limitation — underscoring by contrast how load-bearing an execution-gated test loop is in every system that has one.

## Key findings (claim / confidence / source / evidence)

1. **MetaGPT's bounded retry loop.** The Engineer role runs write-code → execute-unit-tests → debug, capped at 3 retries; this alone lifts Pass@1 by 4.2pp (HumanEval) / 5.4pp (MBPP). *High confidence.* Source: arxiv.org/html/2308.00352v6 (ICLR 2024). Quote: "adding executable feedback into MetaGPT leads to a significant improvement of 4.2% and 5.4% in Pass@1 on HumanEval and MBPP"; the loop continues "until the test is passed or a maximum of 3 retries is reached."
   **Applicable:** bound the Coder↔Verifier retry loop at a small fixed count and escalate rather than spin indefinitely — this framework's own `MAX_ITERS=6` and 2-per-step microstep retry cap are already inside the literature's 3–8 range; no change needed, just confirmation the existing design is right.

2. **MetaGPT's structured-artifact communication.** 5-role pipeline (PM → Architect → Project Manager → Engineer → QA) exchanges documents/diagrams via a shared publish-subscribe message pool with role-specific interest filtering, not raw chat. *High confidence.* Source: same paper, corroborated by a 2024 survey (arXiv 2402.01680).
   **Applicable:** the loop-team's spec/decision-log/run-log artifacts already implement this pattern; the finding validates continuing to route information through named artifacts rather than inline prose recap.

3. **ZeroRepo's three-tier verification, TDD-at-every-leaf-node.** Tests derived from spec *before* implementation; failing code revised until passing or an iteration cap (8 debugging iterations / 20 localization attempts); three verification tiers — unit tests per function/class from its own docstring spec, regression tests auto-triggered when a validated component is later modified, integration tests once a subgraph/module is complete. *High confidence.* Source: arxiv.org/pdf/2509.16198 (ICLR 2026, Microsoft). Quote: "Each function or class is first verified in isolation through unit tests... Validated components trigger regression tests upon modification, while completed subgraphs undergo integration tests."
   **Applicable — the single most directly transplantable recipe found.** This is a more precise, concrete version of the loop-team's existing micro-step build loop; worth writing explicitly into `orchestrator.md`'s micro-step section as a named three-tier scheme.

4. **ZeroRepo benchmark lead.** On the authors' RepoCraft benchmark, ZeroRepo (o3-mini) reaches 81.5% functional coverage / 69.7% test accuracy, beating baselines including Claude Code CLI by 27.3–35.8 points — attributed to graph-planned TDD, not raw model capability. *High confidence*, same source.

*(Full findings list — additional claims on AutoSafeCoder's dual static/dynamic loop, DARS's execution-feedback search, Meta ACH's mutation-testing precision numbers, and Lingma SWE-GPT's no-test-execution negative case — is in the workflow's `journal.jsonl` `result` entries; the summary above already carries the load-bearing numbers.)*

## What's directly applicable to this loop-team

1. Test-writer generates tests from the spec **before** the Coder's implementation is trusted; "tests pass" remains the sole hard gate (Agentless/ZeroRepo/MetaGPT) — already the design; this is a confirmation, not a change.
2. Bound every fix loop at a small fixed retry count (3–8) and escalate rather than loop forever (MetaGPT/ZeroRepo) — already true (`MAX_ITERS=6`, per-step retry cap 2). No change needed.
3. **Formalize three verification tiers explicitly** — unit tests per function/class from its spec, regression tests re-run automatically whenever a previously-passing unit is touched, integration tests once a subgraph/module is complete (ZeroRepo). This is the most concrete, currently-unadopted refinement to the micro-step build loop.
4. Route inter-role communication through structured artifacts (specs, plans, test files, decision logs), not raw chat recap — already the design (spec/decision-log/run-log), confirmed as correct by MetaGPT's and L2MAC's convergent design.
5. Add a lightweight mutation-testing pass (LLM-generated mutants + LLM judge to discard unkillable/equivalent ones) as a cheap self-test of test-suite strength (Meta's ACH) — directly complements the Researcher Mode A dossier's Stryker recommendation (same session, see `loop-improvement-db-test-isolation-and-rls-catching-2026-07-09.md`).
6. For security- or contract-sensitive code paths, add a second independent verification signal beyond unit tests (static analysis, or property-based/fuzz testing) since dual-signal verification measurably beat single-signal in both AutoSafeCoder and the general literature — directly relevant to PadSplit Cockpit's diagnosed missing-schema-validation-at-ingress bug class (see project audit, same session).

## Cross-reference to this session's other research/audit outputs

- `loop-improvement-db-test-isolation-and-rls-catching-2026-07-09.md` (Researcher Mode A dossier, same day) — DB transactional test isolation, Stryker, pgrls/rlsgrid, fast-check. Item 5 above and that dossier's candidate #2 (Stryker) are independently convergent recommendations from two different research passes.
- PadSplit Cockpit project audit (this session, not a saved file — see run transcript) — diagnosed three recurring bug classes (shared-DB/fixture flakiness, allowlist drift, unchecked API ingress) that map directly onto items 3, 5, and 6 above.
- TaxAhead project audit (this session) — diagnosed a parallel-worktree coherence-collapse risk that maps directly onto this report's "long-horizon coherence" finding (item 2/4): the fix is external structure (a committed shared-guard mechanism, a real ROADMAP.md), not a bigger context window or more careful individual sessions.
