# Deep-research: build-vs-debug team/gate structuring — independent confirmation pass

**Run date:** 2026-07-10
**Mechanism:** `deep-research` skill/Workflow (`wf_5840a5b5-884`), 107 sub-agents, 707 tool uses, adversarial 3-vote claim verification, ~5.73M sub-agent tokens.
**Purpose:** independent, full-rigor confirmation of the lighter 3-angle workflow's verdict (see `two-tier-team-vs-gate-2026-07-10.md`), requested explicitly by Nnamdi to match the same research depth as the earlier multi-agent-coding-systems survey.

## Question researched

Whether/how software teams formally separate build from debug/maintenance work with real measurable mechanisms (Google SRE error budgets, Kanban class-of-service, Shape Up cool-down, dual-track agile, bug-bash cadences, documented failure modes of team-splitting), solo/small-team focus techniques across concurrent projects, and whether any AI-agent coding framework runs a structurally separate maintenance role/loop or an error-budget-style gate — with an opinionated "what's applicable" section for a solo builder deciding whether to split his agent loop into a build track and a debug track.

## Bottom line (converges with the lighter workflow's verdict)

**Don't split into permanent separate feature/bug agent crews.** Both Shape Up and dual-track agile independently warn this produces ownership loss and handoff friction ("throw it over the wall"). Instead borrow the *shape* of the real mechanisms:
- A Shape-Up-style **recurring cool-down window per project** — a scheduled hardening cycle the same writer→verifier→fix loop enters periodically, not a separate team.
- A **Personal-Kanban-style single board across both projects with one shared WIP limit** — this is the one lever with actual regression-backed productivity evidence (below).
- A **Renovate-style fully automated, non-reasoning bot** absorbing pure dependency/lint-level maintenance, so it never competes with judgment-requiring feature or bug work at all — a genuinely new idea versus the lighter pass.

## Key findings, with the refinements this pass adds beyond the lighter workflow

1. **Google SRE error budgets are real but narrower than folklore: root-cause-conditional, not a blanket freeze.** *High confidence.* Verified across 3 primary Google sources + 1 corroborating post. The freeze triggers only when the SLO miss traces to an **internal** cause (code defects, procedural errors, dependency issues) — external causes (infra outages, other teams' incidents, unusual traffic) are explicitly exempted, and P0/security fixes proceed even during a freeze. Two over-reaching framings (a universal no-exceptions mandate; a fully mechanical velocity-to-budget tie with no manager judgment) were adversarially tested and refuted.
   **Refinement to the repo-health-gate design:** this is good news for the mechanism already proposed — `fix_plan.md` open items and named recurring bug classes ARE internal-cause defects, so gating new-slice work on them is exactly the right scope; no change needed, just added confidence.

2. **Shape Up's cool-down confirmed as the cleanest scheduling separation, with an explicit anti-separate-team argument.** Two-week mandatory ad-hoc/bug-fixing slot between six-week bets; Shape Up explicitly argues most bugs aren't crises and large bugs should compete at the betting table like feature pitches — i.e., no standing bug team, ever.

3. **Dual-track agile confirmed as a different axis (discovery/delivery, not build/debug) — used here as a cautionary analogy.** It runs both tracks in parallel with ONE cross-functional team specifically to prevent a discovery-to-delivery handoff — directly relevant as a structural warning against literally splitting people (or agents) into separate build and fix crews.

4. **New, citation-backed finding not in the lighter pass: a real empirical study on multitasking and productivity.** A 372-developer / 3,269-developer-week regression found that *fewer concurrent projects* and *repetitive (not random) day-to-day switching patterns* predict higher productivity — raw daily multitasking count alone does not. A separate qualitative finding: industry developers (unlike OSS contributors) are pulled into multitasking specifically by bug-fixing/production-support interrupts.
   **Applicable:** this is real evidence for two things already recommended — combining the WIP limit across both repos (fewer concurrent projects), AND making the weekly cadence a fixed, *repeating* pattern (Mon–Wed build / Thu hardening / Fri gate-check) rather than ad hoc day-to-day choices — the "repetitive, not random" finding specifically validates a structured rotation over improvised daily picks.

5. **No AI-agent coding framework has an error-budget/SLO-style health gate on feature work — a named open gap in the 2026 literature, not something to copy.** A comprehensive 2026 agentic-SE survey explicitly flags this as future work and describes current multi-agent coordination as "simple" (sequential pipelines/centralized orchestration). The closest real analogue is Renovate/Dependabot-style bots — a genuinely separate, structurally distinct loop, but for pure dependency-update maintenance, not bug-fixing or reasoning-based hardening.
   **Implication:** `repo_health_gate.py` (already queued) is genuinely a first-of-its-kind design for this framework, well-grounded in cross-domain analogy (SRE + Kanban) rather than an existing AI-agent pattern being copied — worth knowing going in, so expectations are calibrated (build-and-validate-the-thresholds, not "just port a known-good system").

6. **New idea worth adding to the plan: a deterministic, non-agentic bot for pure dependency/lint maintenance.** Neither TaxAhead nor PadSplit Cockpit's audits mentioned whether Dependabot/Renovate is already configured. Worth a cheap check — if not, adding one is a free way to remove pure-toil maintenance from the combined WIP budget entirely, since it never touches judgment-requiring work.

## Cross-reference

- Lighter-workflow companion dossier (same-day, situated recommendation with the concrete `repo_health_gate.py` mechanism and weekly cadence): `two-tier-team-vs-gate-2026-07-10.md`.
- Feeds into: the decisions-log entry being appended to `fix_plan.md` this same session, and the queued `repo_health_gate.py` build.
