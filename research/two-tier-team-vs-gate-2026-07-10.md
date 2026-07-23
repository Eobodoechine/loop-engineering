# Should loop-team split into a feature-building track and a bug-fixing/hardening track?

**Researcher — Mode A. Dispatched by Oga 2026-07-10. Question:** does any real coding-agent
framework run a structurally separate maintenance/bug-triage agent role vs feature-agent role,
and does that argue for adding a second "hardening-coder" subagent type to loop-team, gated by
an error-budget-style threshold — or is the real gap a missing GATE/RULE on the existing single
Coder role, not a missing ROLE?

**Verdict up front: it's a missing GATE, not a missing ROLE.** Do not add a second Coder
subagent type. Add a repo-health gate (a small deterministic checker + an orchestrator.md
prose rule) that blocks starting a new slice/phase for a repo while it has more than N
verified-open `fix_plan.md` items or M non-flaky suite failures, and a rule that propagates a
*named recurring defect class* into the next plan-check round for that repo. Both are
implementable as a prose-rule + a script, exactly the pattern the framework already uses for
`plancheck_saturation.py` / `MAX_ITERS` / the plan-check-before-Coder gate — no new role file,
no new `subagent_type`, no new dispatch machinery.

---

## 1. What I read in THIS framework first (grounding, not assumed)

- `loop-team/orchestrator.md` — single `Coder` role (`roles/coder.md`, 69 lines) handles
  both feature-build micro-steps and bug-fix/retry dispatches; nothing in the Coder role
  brief or its dispatch conventions distinguishes "feature" from "fix" — it receives a spec
  + failing tests and implements minimally, whatever the spec says. The **Failure Arbiter**
  (orchestrator.md, "Failure arbiter" section) classifies every red result into 6 classes
  (code-bug / test-bug / spec-gap / harness-fault / silent-throttle / degenerate-output) and
  routes by class — but always back to the SAME Coder/Test-writer/Verifier roles, never to a
  differently-scoped agent.
- `MAX_ITERS` (default 6) and the micro-step **retry cap of 2** are per-build/per-step
  circuit breakers, not repo-level gates — nothing currently checks "does this repo have too
  much open debt" before starting the NEXT phase/slice.
- `fix_plan.md` (7,824 lines) is explicitly "the durable gate-hole log" — an append-only
  record, not an enforced gate. Nothing reads it to block a new Brief.
- The **"Name the complete class"** rule (orchestrator.md step 1) already exists for exactly
  the recurring-bug-class problem Nnamdi describes — "if a plan-check round finds one
  violating instance of a cross-cutting pattern, treat it as a signal that the WHOLE class
  needs naming and sweeping" — but it is scoped to ONE plan-check thread on ONE spec. It does
  **not** propagate a named class forward into a DIFFERENT spec's plan-check later, which is
  precisely how `H-FENCE-ENUM-INCOMPLETE-1` happened twice on unrelated TaxAhead specs.
- `fix_plan.md:7501-7559`, `H-FENCE-ENUM-INCOMPLETE-1` (filed 2026-07-08, OPEN): the exact
  "fencing enumeration incomplete" bug the task description references. Root cause
  (fix_plan.md:7523-7531): *"enumerating 'every write of a class' by re-reading a file and
  reasoning about control flow is not equivalent to a mechanical, exhaustive search for the
  literal write pattern... a human/model re-reading under revision pressure... can miss an
  adjacent, un-named sibling with the identical shape."* **Its own proposed fix
  (fix_plan.md:7542-7554) is a plan-check-verifier-mode addition — "require the revision to
  be accompanied by... a literal grep for the write's structural signature... Candidate
  location: `roles/verifier.md`'s plan-check-mode instructions... and/or a line in
  orchestrator.md's 'Name the complete class' section"** — i.e. the team that found this bug
  already diagnosed the fix as a RULE/mechanism addition to the *existing* Verifier role, not
  a new agent. This is strong internal corroboration for the verdict below.
- The orchestrator's own **"Roadmap (not yet built)"** section already lists a "Bug-identifier
  — proactively hunts failure cases beyond the current tests" as a *planned, distinct* future
  role. Note carefully what it is: a bug-*finding* role (an adversarial fuzzer/prober), not a
  bug-*fixing* role — it would feed the SAME Coder, not replace or duplicate it. This is not
  evidence for a second Coder type; if anything it's evidence the framework already
  considered a role split and concluded the split that matters is "finder vs fixer" for
  *discovery*, not "feature-fixer vs bug-fixer" for *implementation*.

## 2. External research — Q1: does any real framework structurally separate a bug-fixing agent from a feature agent?

**OpenHands (All-Hands-AI/OpenHands, ~78.5k stars, already on the loop-team radar as WATCH/
TESTABLE):**
- Direct fetch of `github.com/OpenHands/OpenHands/tree/main/skills` (the real, current file
  list) shows: `add_agent.md, add_repo_inst.md, address_pr_comments.md, agent-builder.md,
  agent_memory.md, ... code-review.md, fix_test.md, security.md, update_pr_description.md,
  update_test.md` — **no `bug_fix.md` or `feature.md` file exists.** (A WebSearch summary
  claimed these files existed as "dedicated skill files" — that claim is **false**; the
  direct repo fetch refutes it. Flagging this explicitly per the honesty bar: a search
  snippet is a lead, not a fact, and this is a live example of one being wrong.)
- Direct fetch of `docs.openhands.dev/overview/first-projects` confirms: *"OpenHands can
  assist with nearly any coding task"* — the doc walks through Hello World → building →
  refactoring → debugging as **the same general-purpose agent** given different prompts, not
  different scaffolds.
- The OpenHands *blog* (`openhands.dev/blog/ai-agent-workflow-automation`, real fetch,
  quoted directly) describes a recommended **router pattern for automation pipelines built
  on top of OpenHands**: *"A router reads an incoming event and decides which workflow
  should handle it. An inbound issue might go to a labeling agent, a bug with a clear
  reproduction to a fixing agent, and anything ambiguous to a person."* This is real and on
  point for the question — but it is **advice for users wiring OpenHands into their own CI
  automation** (route by task TYPE to a differently-PROMPTED instance of the same
  underlying agent), not a structurally distinct agent architecture inside the OpenHands
  product itself. Transfer-condition check: (a) requires the operator to build the router +
  maintain separate prompt templates per workflow; (b) this framework already has the
  moral equivalent (Oga classifies `new` vs `modify/fix/continue` intent, orchestrator.md
  step 1) — so this pattern is **already adopted here**, just not labeled "two agents"; (c)
  the guarantee is instructional (a human/orchestrator must classify correctly) — same as
  loop-team's own `new` vs `modify/fix/continue` classification already is.

**GitHub Dependabot → AI coding agents (`github.blog/changelog/2026-04-07-dependabot-alerts-
are-now-assignable-to-ai-agents-for-remediation/`, real fetch, quoted):**
*"You can now assign Dependabot alerts to AI coding agents, including Copilot, Claude, and
Codex, to analyze the vulnerability and open a draft pull request with a proposed fix."*
GitHub is explicit this is **complementary, not a separate scaffold**: *"Both tools work
together: Dependabot automatically keeps your dependencies current, and coding agents help
tackle the fixes that require deeper analysis."* The agent assigned to a CVE fix is the SAME
Copilot/Claude/Codex coding agent used for feature PRs — routed by a different TRIGGER
(a Dependabot alert vs a human/issue), not a different subagent type or scaffold.

**Facebook/Meta SapFix + Getafix (`engineering.fb.com`, real fetch, quoted; 2018, proprietary,
current status unverifiable):**
This IS a genuinely separate, continuously-running pipeline: Sapienz (fuzz-testing bug
finder) + Infer (static analysis) localize a bug → Getafix (mines historical human fixes,
hierarchical clustering) proposes fix templates → SapFix (mutation-based end-to-end repair)
generates and validates a patch → human review. *"SapFix relies on templates served up from
Getafix... those templates are based on previous fixes that human developers made."*
This is real architectural separation from feature development — but three honesty flags:
(1) it is **not an LLM agent** — template-mining + mutation testing, 2018-era tooling,
architecturally a different kind of system than loop-team's Coder; (2) it is **proprietary
Meta infra**, not open, no repo to check — I could not confirm current maintenance status as
of 2026 (last public technical detail is the 2018 blog post; no 2024-2026 update found in
this search); flagging as **unverified-current, do not rely on this as an active precedent**;
(3) even where it separates *detection+repair* from *feature dev*, it does **not gate feature
dev** — it ran continuously, in parallel, never blocking releases on a debt threshold. This
is the closest real precedent for "a genuinely distinct hardening pipeline," but it answers a
different question (parallel automated repair) than the one Nnamdi is actually asking
(should a build LOOP pause feature work until debt clears).

**Net for Q1:** I found no real, currently-verifiable framework that gives a bug-fixing task
a *structurally different agent scaffold* (different tools, different verification method,
different subagent type) than a feature-building task. Every real example routes the SAME
underlying coding-agent capability to different tasks via a different TRIGGER or PROMPT, not
a different ROLE. This matches loop-team's own Coder role, which already takes a spec of
either shape.

## 3. External research — Q2: an error-budget-style GATE that pauses feature work until health recovers

**The root pattern (Google SRE book, `sre.google/sre-book/embracing-risk/`, real fetch,
quoted):** *"As long as the uptime measured is above the SLO... new releases can be pushed...
If SLO violations occur frequently enough to expend the error budget, releases are
temporarily halted while additional resources are invested in system testing and development
to make the system more resilient."* This is the canonical, extremely well-documented
"feature freeze until reliability work restores budget" gate — but it is written for
**production services** (uptime/latency SLOs), not an AI-agent build loop's bug backlog.

**Adaptation to AI agents (real, but a different context than a build loop):** Microsoft
Community Hub (`techcommunity.microsoft.com/.../applying-site-reliability-engineering-to-
autonomous-ai-agents/`) and a dev.to post ("Your Agent Acts Without Checking Your Error
Budget") both describe adapting error budgets to gate an **agent's autonomy to act in
production operations** — e.g. *"If error budget is below threshold... the agent does not
act autonomously. It escalates."* This is a real, live pattern — but it gates whether an
*ops/incident-response* agent may self-remediate a live system, not whether a *build loop*
may start a new feature phase. I could **not** find a documented instance of anyone applying
an error-budget-style gate specifically to "may this AI coding-agent loop start new feature
work" — the mechanism (threshold → freeze → remediate → resume) is extremely well-precedented
in the parent domain (SRE) and its ops-agent-autonomy adaptation is a genuine, verified
transplant of that same mechanism into an *adjacent* AI-agent context, but the exact
application Nnamdi is proposing (repo-health gate on a *dev/build* loop) does not yet have a
named, documented precedent anywhere I found. That is not a mark against the idea — it means
it would be a **novel-to-this-space instantiation of an extremely well-proven root
mechanism**, which is a much stronger position than inventing the mechanism itself from
scratch.

**Transfer-condition check for the SRE error-budget pattern:** (a) requires a
machine-readable health signal (an SLO metric in SRE; here, `fix_plan.md`'s verified-open
count + the harness's non-flaky-failure count) and a point in the workflow where a
GO/NO-GO decision is actually made before new work starts; (b) loop-team already has both —
`fix_plan.md` as the debt ledger and orchestrator.md step 1 ("Restate & plan") as the
pre-work decision point; (c) the guarantee can be made **structural, not merely
instructional** — the same way `plancheck_saturation.py` already turns a prose "stop
re-reviewing" rule into a script Oga must run and obey (`DESIGN_CHECKLIST.md` gate 10). This
is the strongest-precedent, lowest-risk piece of the three sub-questions to adopt, precisely
because the framework already has the exact "prose rule + deterministic checker script"
mechanism this would reuse.

## 4. External research — Q3: Dependabot/Renovate as a transplantable "background hardening loop" pattern

**Renovate (`docs.renovatebot.com/key-concepts/automerge/`, real fetch, quoted):** runs on
its own schedule, independent of feature-dev cadence, but explicitly **test-gated**:
*"Renovate will wait for the required tests to pass before it automerges"* and will not
force a merge into active-development churn: *"if you or others keep committing to the
default branch then Renovate cannot find a suitable gap to automerge into."* On failure it
falls back to a human-reviewed PR rather than proceeding.

**Dependabot** (per the changelog fetch in section 2): same shape — continuous, scheduled,
narrow-scope (version bumps / CVE patches), PR-gated, human-reviewed before merge; only
escalates to a coding agent when the fix needs "deeper analysis" (breaking changes, package
downgrades).

**The transplantable insight — and its limit:** both of these succeed because their scope is
**narrow and mechanically well-defined** (a dependency version bump; a specific CVE). Neither
is a general "fix whatever bugs exist" loop. The one real system I found that DOES attempt
general automated bug-fixing (SapFix/Getafix, section 2) required a much heavier, separately
built detection+repair pipeline (a fuzzer, a static analyzer, years of historical
fix-pattern mining) — because "just fix any open bug" is a categorically harder, less
bounded problem than "bump this dependency and re-run the suite." **This is a real caution
against Nnamdi's literal "hardening-coder" framing**: if it were scoped to "fix whatever is
in fix_plan.md," it would face the harder, less-bounded problem Dependabot/Renovate
specifically avoid by staying narrow. The well-functioning precedent argues for narrow,
mechanically-triggered fixes (a specific named recurring bug class, a specific flaky-test
signature) — which loop-team already handles via the Failure Arbiter's routing, not for a
generically-scoped second Coder.

**Transfer-condition check:** (a) requires a well-defined trigger (a version diff; a CVE ID)
and a test suite to gate merge; (b) loop-team's target repos have both (fix_plan.md items are
individually well-defined bugs, and `verify.py`/`harness/verify.py` is the test gate); (c) the
guarantee (only merge if tests pass) is **already structural** in loop-team via `verify.py`'s
exit code and the git-checkpoint-on-green discipline — this piece requires no new machinery
at all, just applying the existing micro-step loop to fix_plan.md items on a scheduled/
gated cadence instead of ad hoc.

## 5. Direct answer to the framing question

**Is the gap a missing ROLE, or a missing GATE?** Missing GATE.

Evidence against a second Coder subagent type:
1. **No real precedent gives bug-fixing a different scaffold.** Every framework I could
   verify (OpenHands, GitHub's agent-assignment feature) routes the identical underlying
   coding-agent capability to bug work via a different TRIGGER or PROMPT, never a
   structurally different tool-access profile or verification method. loop-team's own
   `roles/coder.md` is already trigger-agnostic — it takes a spec + failing tests regardless
   of whether the spec describes a feature or a fix.
2. **A second subagent type buys nothing mechanistic here.** `subagent_type` in this
   framework controls tool-access profile (`disallowedTools: Agent`, etc.) and which
   `.claude/agents/<name>.md` frontmatter governs the dispatch. A "hardening-coder" would need
   the *same* file-edit/test-run access as the feature-Coder — there is no capability,
   tool, or verification difference between fixing `H-FENCE-ENUM-INCOMPLETE-1` and
   implementing a new Gmail OAuth flow. Adding a second role file to maintain in lockstep
   with `coder.md` is pure duplication risk (two files that must never drift) for zero new
   guarantee.
3. **The framework's own diagnosed fix for the exact recurring bug in the prompt
   (`H-FENCE-ENUM-INCOMPLETE-1`) is a rule addition to the Verifier's plan-check mode**, not
   a new role — direct textual evidence from `fix_plan.md:7542-7554`, written by the team
   itself before this dispatch even ran.
4. **The real gap Nnamdi is describing is sequencing, not capability.** TaxAhead's Gmail
   connector being stuck on PLAN_FAIL round 3 and PadSplit Cockpit doing 3 recurring hardening
   passes with no new slice are both symptoms of "nothing forces a decision about when to stop
   hardening and return to features, or when to stop starting features and clear debt first" —
   that is exactly the SRE error-budget shape (a THRESHOLD-TRIGGERED PAUSE, not a different
   team), and it is a rule/gate change, cleanly analogous to `MAX_ITERS`,
   `plancheck_saturation.py`, and the plan-check-before-Coder credit mechanism already in
   orchestrator.md.

## 6. Concrete gate proposal (implementable now, low risk, reuses existing machinery)

Add to `orchestrator.md` step 1 ("Restate & plan"), before decomposing a new Brief into
micro-steps for repo R:

1. **A deterministic checker**, `harness/repo_health_gate.py <fix_plan_path> <repo_name>
   [--max-open N] [--max-failures M]`, mirroring the existing `plancheck_saturation.py`
   pattern:
   - Parses `fix_plan.md` for entries tagged with `repo_name` whose status is verified-OPEN
     (reusing the existing phantom-CLOSED-entry lesson already in memory — a CLOSED label is
     not proof; the checker should require the same evidence bar Oga already applies when
     reconciling fix_plan.md, not trust the label alone).
   - Reads the last recorded `verify.py`/full-suite run's non-flaky failure count for that
     repo (the `H-FULLSUITE-INSTABILITY-1` flakiness-distinguishing logic already exists in
     this repo's history — reuse it, don't reinvent it).
   - Returns `PROCEED` / `REMEDIATE_FIRST` with the counts and which specific items exceeded
     threshold.
2. **The gate rule:** if `REMEDIATE_FIRST`, the next Brief Oga plans for that repo MUST be a
   fix_plan.md-remediation spec (through the exact same Test-writer → Coder → Verifier
   micro-step pipeline, unchanged), not a new feature/slice — until a re-run returns
   `PROCEED`. This is a sequencing rule, enforced the same way `plancheck_saturation.py`'s
   `STOP_PROSE_REVIEW` verdict is already obeyed today: Oga runs the script and follows its
   verdict rather than deciding for itself.
3. **Recurring-class propagation (closes the actual `H-FENCE-ENUM-INCOMPLETE-1` gap):** when
   a plan-check gap record's `broken_assumption` matches a class already logged OPEN in
   `fix_plan.md` for that repo, the NEXT plan-check dispatch for ANY spec on that repo must be
   handed that named class explicitly (as a targeted check, per the fix_plan.md entry's own
   proposed fix — a literal grep for the structural signature, not a re-read) — not
   rediscovered from scratch on a second unrelated spec.
4. **Thresholds are Nnamdi's call, not derived here** — e.g. N=2 verified-open items (or any
   single item flagged as hitting ≥2 specs, which should auto-qualify regardless of N) and
   M = whatever non-flaky-failure count he judges unacceptable for a repo of that size. This
   research recommends the MECHANISM; the specific numbers are a product decision.

This is a prose-rule + a ~50-100 line Python checker, following exactly the same shape as
`plancheck_saturation.py` already does for plan-check round saturation. No new role file, no
new `subagent_type`, no change to `roles/coder.md`, `roles/verifier.md`'s core role, or the
dispatch machinery in "How roles are dispatched."

## Sources (all opened/fetched directly, per the honesty bar)

- [OpenHands skills directory](https://github.com/OpenHands/OpenHands/tree/main/skills) — real file list confirms no `bug_fix.md`/`feature.md` split; refutes a false WebSearch summary claim.
- [OpenHands: AI Agent Workflow Automation for Engineering Teams](https://www.openhands.dev/blog/ai-agent-workflow-automation) — router-pattern quote.
- [OpenHands docs: First Projects](https://docs.openhands.dev/overview/first-projects) — "one general-purpose agent" confirmation.
- [Dependabot alerts are now assignable to AI agents for remediation — GitHub Changelog](https://github.blog/changelog/2026-04-07-dependabot-alerts-are-now-assignable-to-ai-agents-for-remediation/) — exact feature description + "complementary, not separate" framing.
- [GitHub Docs: About Dependabot security updates](https://docs.github.com/en/code-security/dependabot/dependabot-security-updates/about-dependabot-security-updates) — background-process confirmation.
- [Renovate docs: Automerge](https://docs.renovatebot.com/key-concepts/automerge/) — scheduled, test-gated, non-blocking-of-active-dev confirmation.
- [Meta Engineering: Finding and fixing software bugs automatically with SapFix and Sapienz](https://engineering.fb.com/2018/09/13/developer-tools/finding-and-fixing-software-bugs-automatically-with-sapfix-and-sapienz/) — pipeline architecture quote; flagged unverified-current (2018, proprietary).
- [Meta Engineering: Getafix](https://engineering.fb.com/2018/11/06/developer-tools/getafix-how-facebook-tools-learn-to-fix-bugs-automatically/) — fix-template-mining detail.
- [Google SRE Book: Embracing Risk](https://sre.google/sre-book/embracing-risk/) — canonical error-budget/release-freeze policy quote.
- [Microsoft Community Hub: Applying SRE to Autonomous AI Agents](https://techcommunity.microsoft.com/blog/linuxandopensourceblog/applying-site-reliability-engineering-to-autonomous-ai-agents/4521357) — error-budget-gates-agent-autonomy adaptation (ops context, not build-loop context).
- [arXiv 2606.08960 — Hardening Agent Benchmarks with Adversarial Hacker-Fixer Loops](https://arxiv.org/pdf/2606.08960) — checked and ruled OUT as inapplicable: this is adversarial verifier-hardening (a hacker/fixer/solver triad stress-testing a benchmark's verifier), not a feature-vs-maintenance agent split. Recorded here so a future scan doesn't re-chase this same false lead.
- Internal grounding (not external, but directly read this session): `~/Claude/loop/loop-team/orchestrator.md` (full), `~/Claude/loop/loop-team/roles/coder.md` (full), `~/Claude/loop/fix_plan.md:7501-7559` (`H-FENCE-ENUM-INCOMPLETE-1`).

## What I could not verify / honesty flags

- SapFix/Getafix's current (2026) operational status at Meta — no post-2018 primary source
  found; treat as historical precedent only, not a live example to cite as "currently running."
- No documented instance anywhere of an error-budget-style gate applied specifically to an
  AI-agent BUILD loop's feature/hardening balance (as opposed to production-ops agent
  autonomy or classic SRE release cadence) — the proposal in section 6 is a novel transplant
  of a well-proven mechanism, not a copy of an existing implementation. Flagging this
  plainly rather than overstating precedent.
