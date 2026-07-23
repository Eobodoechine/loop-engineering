# Mode A dossier — closing the padsplit-cockpit bug cluster (fixture flakiness, orphaned DB rows, RLS cross-tenant FK gaps) + multi-phase roadmap discipline

**Dispatched:** 2026-07-09, loop-team Researcher, Mode A (loop improvement).
**Trigger:** Nnamdi's direct complaint — a cluster of 3 real bug classes (test-fixture flakiness from
hardcoded emails in `seedOrgWithUser`, an orphaned DB row, an 8-table RLS cross-tenant FK ownership
gap) all landed on padsplit-cockpit in a single day (2026-07-09), on top of an already-rigorous
plan-check/Verifier/fix_plan apparatus. Task: find real, sourced techniques/tools that catch this
class of bug EARLIER in the loop, plus real prior art on multi-phase roadmap discipline in agent
frameworks (MetaGPT, ChatDev, AutoGen, OpenHands, SWE-agent, Aider, CrewAI, Devin/Cognition).

**Prior-work check (read in full before researching, per role brief):** `research/radar.md` (all
557+ lines, including the compiler-feedback-loop dive, the Gate-10 saturation dive, the SkillOpt/RHO/
Self-Harness optimizer thread) and `loop-team/learnings.md` (all 2061 lines). Neither file already
covers: (a) database-test-isolation tooling (transactional rollback / ephemeral containers) as a
structural fix for the shared-dev-DB flakiness class, or (b) a static/dynamic RLS analyzer purpose-
built for the cross-tenant-FK bug class padsplit-cockpit hit. Both are genuinely new to the radar.
The mutation-testing gate (`orchestrator.md` step 5.5) IS already on the radar, but only via `mutmut`
— a Python-only tool; no JS/TS equivalent has ever been evaluated, and padsplit-cockpit is a
TypeScript/Next.js/Prisma/Vitest codebase. This is a real, previously-unflagged structural gap: the
adversarial-mutation safety net currently does nothing for the exact codebase where the bug cluster
landed.

**What the existing learnings.md record shows about THIS bug cluster's root causes (read in full,
summarized here as the diagnostic starting point, not re-litigated):**
1. `2026-07-09 — padsplit-cockpit fixture-flakiness fix` — hardcoded, non-randomized fixture emails
   in `seedOrgWithUser` collided against a *unique* constraint once enough accumulated rows existed
   in a shared, never-reset dev DB — "a hardcoded-fixture-email unique constraint collides once enough
   accumulated rows exist in the shared DB from repeated test invocations, not on every invocation."
2. `2026-07-09 — inbox revalidatePath fix` (lesson 3) — "a shared, non-reset dev database across many
   test runs in one build session makes 'pre-existing failure' a moving target" — a sub-agent's own
   "I reran it, not flaky" claim was itself false, discovered only when Oga independently reran it.
3. `2026-07-02 — D1 fault-injection run` / `2026-07-09 — padsplit-cockpit RLS cross-FK fix` (lesson 3)
   — two SEPARATE incidents of "a concurrent session hitting the SAME SHARED LOCAL DEV DATABASE
   produces a full-suite failure signature indistinguishable from a real regression."
4. `2026-07-02 — RLS cutover` — enabling Postgres RLS broke 40 existing tests because the fixture
   audit migrated WRITES to a bypass client but left READS on the app-role client, which RLS
   default-denies with no per-request org GUC — required manual, iterative discovery.
5. `2026-07-02 — RLS plan-check: prove the class is EMPTY` — the RLS spec took **4 plan-check
   iterations**, each finding a DIFFERENT unclassified policy-bearing table/call-site, before the team
   hand-built a complete `db.<model>` classification table + an exhaustive disk-glob sweep as the
   acceptance criterion. This is the manual version of what a schema-driven RLS test-matrix generator
   does automatically (Candidate 2 below).
6. `2026-07-09 — padsplit-cockpit RLS cross-FK fix` (lesson 1) — a genuinely subtle Postgres
   RLS self-referencing-subquery recursion trap, where the "obvious" fix (wrap in any function call)
   is a DIFFERENT, quieter correctness bug (false-negatives a legitimate same-org row) unless the
   wrapper is `SECURITY DEFINER` owned by a `BYPASSRLS` role.

**Common thread:** every one of these is a bug class where the loop's existing safety net (plan-check
prose review, hand-written tests, an independent post-build Verifier) is instructional — it depends on
a human or an LLM reviewer *noticing* the gap and *remembering* to check it, and it takes multiple
rounds each time to converge (4 rounds for the RLS class-emptiness proof; a fixture-tautology class
that recurred at least 3 times independently: 2026-06-24 ×2, 2026-07-09). The candidates below are
selected specifically because they convert these instructional guarantees into STRUCTURAL ones — the
`FIXED` vs `PATCHED` distinction this project's own `learnings.md` (2026-07-03 entry) already names as
the load-bearing test for whether an incident is actually closed.

---

## Candidate 1 — Transactional per-test DB isolation for Prisma/Postgres/Vitest
**(chax-at/transactional-prisma-testing + codepunkt/vitest-environment-prisma-postgres)**

- **source:**
  - https://github.com/chax-at/transactional-prisma-testing — verified via direct WebFetch.
    Quote: *"Provides an easy way to execute database tests in a transaction that will be rolled back
    after each test for fast testing."* Setup pattern (quoted from README):
    ```typescript
    async function before() {
      if (!prismaTestingHelper) {
        const originalPrismaService = new PrismaService();
        prismaTestingHelper = new PrismaTestingHelper(originalPrismaService);
        prismaService = prismaTestingHelper.getProxyClient();
      }
      await prismaTestingHelper.startNewTransaction();
    }
    function after() { prismaTestingHelper?.rollbackCurrentTransaction(); }
    ```
  - https://github.com/codepunkt/vitest-environment-prisma-postgres — verified via direct WebFetch.
    Quote: *"Seed your database once with production-like data, then run each test in a transaction
    that is rolled back after execution. Tests remain isolated without expensive reseeding."* Config
    (quoted): `environment: 'prisma-postgres'` in `vitest.config.ts`, `environmentOptions` pointing at
    the generated Prisma client path. Confirmed: *"can connect to a local PostgreSQL instance, Docker
    container, Testcontainers-created instance, or cloud-hosted PostgreSQL"* — no Docker requirement.
- **maturity:**
  - `chax-at/transactional-prisma-testing`: 52 stars, MIT, created 2022-05-02, last push
    2026-01-09 (`gh api` confirmed) — ~6 months stale as of this scan but a small, stable-API library
    (limitations documented: no Fluent API support, sequence values persist across rollbacks — real
    honesty in its own docs, not silent).
  - `codepunkt/vitest-environment-prisma-postgres`: 42 stars, MIT, created 2025-11-27, last push
    2026-07-08 (`gh api` confirmed) — actively developed, and it is the more directly relevant of the
    two since it is Vitest-native (padsplit-cockpit's confirmed test runner per `learnings.md`'s
    "Vitest-only idioms break a repo whose gate includes full tsc" entry) rather than a generic
    "works with every framework" claim.
  - Both real, working, quoted-from-source, not stubs.
- **claim:** converts "don't leave fixture rows lying around" / "randomize your fixture data" from a
  discipline every future Test-writer/Coder must remember, into a structural guarantee — every test
  runs inside its own transaction, rolled back at teardown, so no test's fixture data can EVER survive
  to collide with a later test's fixture data, regardless of how many times the suite has run against
  the same dev DB. This directly targets bug-cluster items 1, 2, and 3 above (hardcoded-email
  collision after accumulated rows; "reran it, not flaky" claims defeated by shared mutable state;
  concurrent-session cross-contamination on a shared local Postgres instance — a per-test transaction
  still can't fully solve TWO SEPARATE PROCESSES writing outside a transaction at the same time, but it
  eliminates the far more common single-process accumulation failure mode entirely).
- **where_it_wires_in:** `orchestrator.md`'s micro-step build loop, item 2 ("OGA runs the impacted
  tests ITSELF... `pytest --testmon` via the gate's target python, or `verify.py`") — for a Node/
  Prisma/Postgres target repo, this becomes the default `vitest.config.ts` test environment, wired in
  once per target repo (padsplit-cockpit specifically) rather than per-build. Also directly informs
  `roles/test_writer.md`: any fixture-seeding helper (`seedOrgWithUser` and siblings) should be written
  assuming automatic rollback, removing the motivation to hand-write cleanup/deletion logic that itself
  becomes a source of bugs (the "orphaned org row" incident was exactly a hand-written, one-time,
  destructive cleanup action that needed its own dedicated plan-check pass — see `learnings.md`
  2026-07-09 "padsplit-cockpit fixture-flakiness fix" lesson 1).
- **triage:** **IMPLEMENTABLE_NOW** — no new infra (works against the existing dev Postgres instance),
  a `vitest.config.ts` + fixture-helper change, MIT-licensed, matches the exact confirmed stack.
- **priority:**
  - `effect` = 0.85 — directly, structurally closes 3 of the reported bug-cluster's root causes.
  - `confidence` = 0.75 — real, quoted, working code; codepunkt's lib is Vitest-native and fresh;
    chax-at's is older/stabler but 6mo-stale (bounded down slightly for that).
  - `phase_fit` = 1.0 — current active bug-fix work on padsplit-cockpit.
  - `risk_reduction` = 0.85 — the flakiness class has independently recurred at least 4 times across
    2 different builds in the last week per `learnings.md`.
  - `uncertainty` = 0.5 — first integration in this repo; specific interaction with padsplit-cockpit's
    custom RLS `SET LOCAL`/GUC-per-request pattern and the `SECURITY DEFINER` wrapper functions is
    UNVERIFIED (see risks below) — this is exactly the kind of under-tested unknown UCB's exploration
    bonus exists to surface, not a reason to skip it.
  - `cost_to_test` = 0.15 — an npm install + config file + one fixture-helper rewrite; no new
    dependency infra, no GPU, no schema migration.
  - **priority = 0.40·(0.85×0.75) + 0.20·1.0 + 0.15·0.85 + 0.10·0.5 − 0.15·0.15 = 0.255 + 0.20 +
    0.1275 + 0.05 − 0.0225 = 0.61**
- **risks:**
  - License/dependency weight: none — both MIT, small surface.
  - **Transfer-condition check (mandatory, per role brief):**
    (a) *Execution context required:* a single shared `PrismaClient` instance whose queries can be
    proxied/intercepted (both libraries work by wrapping the Prisma client, not by patching the raw
    `pg` driver), and a test runner (Vitest) that supports a custom `environment`/setup-file hook.
    (b) *Does padsplit-cockpit satisfy it:* very likely (standard Prisma + Vitest setup per
    `learnings.md`'s repeated references), but UNCONFIRMED — the experiment's first step must be
    reading padsplit-cockpit's actual `PrismaService`/client-instantiation code to confirm no code path
    bypasses the shared client (e.g., a raw `$queryRaw` connection pool opened separately for RLS
    `SET LOCAL` context-setting would evade the transaction wrapper).
    (c) *Structural or instructional:* **structural** once wired — a test cannot "forget" to roll back;
    the guarantee holds regardless of Test-writer discipline. This is the single most important
    property here, since the bug class it replaces (hand-remembered fixture cleanup / randomization)
    has already been "fixed" instructionally at least twice (2026-06-24 fixture-tautology fixes) and
    recurred anyway.
  - **Known interaction risk, unverified, must be checked in the experiment, not assumed:** padsplit-
    cockpit's RLS design (per `research/postgres-rls-self-referencing-recursion-messages-2026-07-09.md`,
    referenced in `learnings.md`) depends on a per-request `SET LOCAL app.<org_guc>` or equivalent,
    which is transaction-scoped in Postgres. A per-test transaction wrapper and a per-request RLS GUC
    are usually complementary (both transaction-scoped), but the SPECIFIC interaction (does the test
    wrapper's outer transaction conflict with, or need to re-issue, the app's own `SET LOCAL` call
    inside a nested savepoint?) is NOT verified by anything read this pass — flag as the first thing
    the experiment must probe, before trusting any green result under RLS-enabled tables.

**Falsifiable `experiment` for `experiments/run_experiment.py`:**
- **metric:** count of flaky/order-dependent test failures across N repeated full-suite runs against
  the SAME dev DB (no reset between runs) — i.e., directly reproduce the class of bug already logged
  4 times, but as a repeatable measurement instead of an incident report. Secondary metric: wall-clock
  time per test-suite run (transactional rollback is typically faster than `TRUNCATE`/reseed, so this
  should not regress and may improve).
- **baseline:** padsplit-cockpit's CURRENT fixture/test-DB setup (whatever `seedOrgWithUser` and
  sibling helpers do today, post-2026-07-09 fix) run 5× back-to-back against the same dev DB instance
  with no reset in between.
- **variant:** the SAME test suite, with `vitest-environment-prisma-postgres` wired in per its own
  `vitest.config.ts` pattern (seed once, each test in a rolled-back transaction), run 5× back-to-back
  against the same DB with no reset in between.
- **instances:** the padsplit-cockpit test suite as it exists today (paired — same test files, same
  DB, only the isolation mechanism differs).
- **decision:** accept the variant only if `evals/acceptor.py`/`pace_accept` confirms a
  significant reduction in cross-run failure count (not a single lucky run) AND zero new failures
  introduced by the wrapper itself (e.g., an RLS GUC interaction bug).
- **predicted_effect:** baseline should show ≥1 flaky failure by run 3-5 (reproducing the documented
  pattern); variant should show 0 across all 5 runs.
- **kill_criterion:** if the variant produces a NEW failure class (e.g., RLS policies silently
  denying reads because the app's `SET LOCAL` GUC call doesn't survive inside the wrapper's outer
  transaction) that the baseline didn't have, treat this as a real transfer-condition failure — stop,
  do not force it, and either find the RLS-specific integration pattern (nest the app's `SET LOCAL`
  inside the same transaction rather than a separate connection) or drop the candidate for this repo.

---

## Candidate 2 — Postgres RLS static analyzer + auto-generated cross-tenant test matrix
**(pgrls/pgrls + matte97p/rlsgrid)**

- **source:**
  - https://github.com/pgrls/pgrls — verified via direct fetch of the raw README
    (`raw.githubusercontent.com/pgrls/pgrls/main/README.md`, not just the rendered page, to reduce
    WebFetch summarization risk on a listing/table page per the honesty-bar note in the role brief).
    Quoted rules directly relevant to padsplit-cockpit's actual bug:
    - **SEC027** — *"RLS table has an owner / user-identity column that no policy scopes by — rows
      may be visible across users within the same tenant."*
    - **SEC040** — *"Permissive `FOR ALL` policy whose `USING` scopes by a tenant/owner key but whose
      explicit `WITH CHECK` binds no identity column at all — a `FOR ALL` insert is governed by
      WITH CHECK alone."*
    - **SEC047** — *"A foreign key whose parent (referenced) table has RLS enabled is a cross-tenant
      existence covert channel when a low-trust role can write the child."* — this is, nearly
      verbatim, the exact bug class padsplit-cockpit's "8-table cross-tenant FK ownership gap" fix
      closed by hand.
    - `pgrls diff`: *"the semantic policy diff command... classifies every RLS change as SAFE,
      BREAKING, REQUIRES_REVIEW, or DANGEROUS. Use it in CI to gate deployments on actual security
      regressions."*
    - `pgrls.testing` pytest plugin: *"opens a connection, starts a per-test transaction, lets you
      switch roles + claims for each scenario, and rolls back at end so nothing persists between
      tests."* (Python-only — relevant to a Python target repo, not directly to padsplit-cockpit's
      TS/Vitest stack; the STATIC ANALYZER half of pgrls (`pgrls check` against the live schema) is
      language-agnostic since it inspects the Postgres catalog directly via CLI, and is the half that
      transfers to padsplit-cockpit.)
  - https://github.com/matte97p/rlsgrid — verified via direct WebFetch. Quote: *"Schema-driven
    Row-Level Security test matrix generator and cross-tenant fuzzer for Postgres/Supabase."* Matrix
    structure (quoted): rows = `role × table × operation`, cells labeled `allow` / `deny` /
    `conditional` / `unrestricted`. Usage (quoted):
    ```bash
    rlsgrid init --from-db      # reads schema, writes config
    rlsgrid check --tenants 5   # seeds, fuzzes, tears down
    ```
    This is the automated version of the exact manual process `learnings.md`'s 2026-07-02 "RLS
    plan-check: prove the class is EMPTY" entry describes building by hand across 4 plan-check
    iterations (a hand-authored `db.<model>` classification table + a disk-glob sweep).
- **maturity:**
  - `pgrls/pgrls`: 22 stars, MIT, created 2026-04-24, pushed 2026-07-10 (same day as this scan) —
    genuinely very young (~2.5 months old) but extremely high release velocity (146 releases,
    v0.48.1) confirmed via WebFetch. Real, `pip install`-able, not a stub — but low star count is a
    real adoption-risk signal for a security-critical tool; treat findings as a strong LEAD to
    manually verify, not as ground truth to auto-apply.
  - `matte97p/rlsgrid`: 4 stars, MIT, created 2026-05-26, pushed 2026-06-23 (~2.5 weeks stale) — 27
    commits, 5 open issues, self-described "Alpha" but "exercised end to end in CI against a rich
    multi-tenant schema" per its own README. Very young, very low adoption signal — genuinely
    experimental.
- **claim:** both tools structurally replace a hand-authored "prove the class is empty" sweep (which
  cost 4 plan-check rounds on padsplit-cockpit's RLS cutover, and cost a separate 3-lesson RLS
  cross-FK fix a week later — the same underlying bug CLASS, SEC047, recurring because nothing
  automatically re-checks it after the fix) with a deterministic, re-runnable check against the LIVE
  schema. `pgrls check`/`pgrls diff` can run as a CI/pre-merge gate on every migration; `rlsgrid check`
  can run as a live fuzzer confirming the matrix holds against actual seeded multi-tenant data.
- **where_it_wires_in:** `orchestrator.md`'s deterministic gate layer (alongside the existing
  `smoke_manifest.json`-driven live-smoke gate in `harness/verify.py`) — a new additive AND-ed check,
  `rls_check`, that runs `pgrls check <schema>` (and, once past Alpha, `rlsgrid check`) against the
  target repo's migrations before `passed` can be true for any Postgres/RLS-touching build. Also
  informs `roles/verifier.md`'s plan-check mode directly: the "name the complete class... enumerate
  every member explicitly" rule (`orchestrator.md`, already-written) currently requires a human/LLM
  Verifier to hand-build that enumeration; `pgrls`'s rule set is exactly that enumeration, running
  deterministically instead of via prose review.
- **triage:** **TESTABLE** — real, runnable, but young enough (both <3 months old, <25 stars) that it
  needs a trial run against padsplit-cockpit's actual schema before being trusted as a gate, not
  IMPLEMENTABLE_NOW like Candidate 1.
- **priority:**
  - `effect` = 0.85 — SEC047 is a near-exact match for the actual bug class that shipped; `pgrls diff`
    directly targets "did this migration reintroduce a closed RLS gap," which is the precise
    regression-prevention question a re-opened bug class implies is currently unanswered.
  - `confidence` = 0.6 — real, working, MIT, with a startlingly precise rule-for-rule match to the
    real incident (raises confidence above what star count alone would suggest) — but still young/
    low-adoption tools, so not treated as high-confidence as Candidate 1's more established libraries.
  - `phase_fit` = 1.0 — current active bug-fix phase.
  - `risk_reduction` = 0.8 — directly targets the SPECIFIC bug class (cross-tenant FK via
    RLS-enabled parent tables) already proven costly (4 plan-check rounds + a dedicated 3-lesson fix).
  - `uncertainty` = 0.6 — genuinely unverified against padsplit-cockpit's real, Prisma-managed
    migration history; UCB exploration bonus applies since this is exactly the kind of high-variance,
    under-tested candidate worth a cheap trial.
  - `cost_to_test` = 0.15 — `pip install pgrls`, point it at the dev DB connection string, read the
    output; zero code changes required to try it once (read-only static/dynamic checks).
  - **priority = 0.40·(0.85×0.6) + 0.20·1.0 + 0.15·0.8 + 0.10·0.6 − 0.15·0.15 = 0.204 + 0.20 + 0.12 +
    0.06 − 0.0225 = 0.5615 ≈ 0.56**
- **risks:**
  - Both tools are pre-1.0/young — treat every finding as a lead to independently confirm against the
    real schema and RLS policy source, not as ground truth (same honesty-bar posture the role brief
    already requires for any external citation).
  - **Transfer-condition check:** (a) execution context — a `DATABASE_URL` connection to the real
    Postgres instance with enough privilege to read `pg_policies`/`pg_proc`/`pg_roles` (both tools are
    read-only static analyzers against the live catalog, ORM-agnostic — Prisma vs raw SQL migrations
    doesn't matter to them). (b) padsplit-cockpit satisfies this trivially (it's the exact Postgres
    instance already in use for dev/test). (c) **structural once wired as a CI/pre-merge gate** — a
    migration that reintroduces an unscoped-owner-column or an RLS-enabled-parent-FK gap fails the
    gate mechanically, regardless of whether the Coder or a plan-check Verifier happened to notice.
    Until wired as a gate, running it manually is only as good as remembering to run it — an
    instructional half-measure; the PACE experiment below should measure whether it catches the SAME
    class of bug the team already had to hand-discover, as the bar for whether it's worth the
    CI-gate investment.
  - **Known gap, explicitly NOT covered:** neither tool's rule set (as quoted) includes a rule for
    self-referencing-subquery RLS recursion (the OTHER real bug found in the same incident,
    `learnings.md` lesson 1) — the existing hand-written research doc
    (`research/postgres-rls-self-referencing-recursion-messages-2026-07-09.md`) remains the authority
    for that specific sub-class; do not assume adopting pgrls/rlsgrid closes it.

**Falsifiable `experiment`:**
- **metric:** true-positive rate against the team's OWN historical RLS bug corpus — run `pgrls check`
  against padsplit-cockpit's schema/migrations AS THEY EXISTED immediately before each of the 2 real
  RLS fixes shipped this month (the RLS cutover fix and the RLS cross-FK fix), using `git worktree` to
  check out the pre-fix commit. Score: does `pgrls` flag the SAME table/policy the team found by hand?
- **baseline:** the team's existing process — 4 plan-check rounds to find the RLS cutover class-
  emptiness gap; a plan-check lens + a Researcher dispatch to find the cross-FK recursion gap.
- **variant:** `pgrls check` run once, read-only, against the pre-fix schema state.
- **instances:** the 2 real historical incidents (paired, not synthetic).
- **decision:** accept as a CANDIDATE→CI-gate promotion only if `pgrls` independently flags at least
  one of the 2 real historical gaps the team found by hand (a clean positive signal against REAL,
  already-known-correct gold) — per `pace_accept`, not a single subjective read.
- **predicted_effect:** SEC047 should fire on the cross-FK incident's pre-fix schema (it's a near-
  literal description of that bug). The RLS-cutover class-emptiness gap is a read/write-path
  application-code issue, not purely a schema/policy issue — `pgrls` may NOT catch it (it's a static
  schema analyzer, not an application-code analyzer), which would be an honest, informative negative
  result, not a failure of the experiment design.
- **kill_criterion:** if `pgrls check` produces zero relevant findings against BOTH historical
  incidents (a true negative on cases we know are positive), drop it as a false lead despite the
  promising rule-text match — the honesty bar requires trusting the empirical backtest over the
  plausible-sounding README quote.

---

## Candidate 3 — Stryker (JS/TS mutation testing) — closing the Python-only `mutmut` gap

- **source:** https://github.com/stryker-mutator/stryker-js — verified via direct WebFetch. Quote:
  *"Mutation testing for JavaScript and friends."* CLI: `npx stryker run`. Confirmed via `gh api`:
  2,940 stars, Apache-2.0, created 2016-02-12, pushed 2026-07-09T23:39:04Z (same day as this scan) —
  the field's de facto standard JS/TS mutation tester, actively maintained for a decade.
- **maturity:** mature, high-adoption, Apache-2.0, no archival/decay signal of any kind.
- **claim:** `orchestrator.md` step 5.5 (adversarial Tier-2 testing) currently runs `mutmut` — read
  directly from the file: `mutmut run --paths-to-mutate <impl_file>` — which is a **Python-only**
  mutation tester (confirmed: `mutmut` operates on Python AST). Padsplit-cockpit is TypeScript/
  Next.js/Prisma (confirmed repeatedly in `learnings.md`: vitest, tsc, Prisma, Next.js references
  throughout). This means the entire mutation-testing safety net — the mechanism specifically
  designed to surface "untested paths" (per `orchestrator.md`'s own LOOP-M5 note: "a surviving mutant
  proves an untested seam") — silently does nothing on the exact codebase where the reported bug
  cluster shipped. This is a structural gate gap, not a tuning problem: nobody chose to skip mutation
  testing on padsplit-cockpit; the tool wired into the loop simply cannot run on its language.
- **where_it_wires_in:** `orchestrator.md` step 5.5, as a parallel/sibling invocation to the existing
  `mutmut` block — detect target-repo language (presence of `tsconfig.json`/`package.json` vs
  `pyproject.toml`) and run `npx stryker run --mutate <impl_file_glob>` with an equivalent timeout
  budget, feeding surviving mutants to `roles/adversarial_test_writer.md` the same way `mutmut`
  results are already fed in. Also feeds `linear_reporter.py`'s existing "surviving mutant" reporting
  path unchanged (it's a title/description string, language-agnostic).
- **triage:** **IMPLEMENTABLE_NOW** — mirrors an existing, already-designed gate step; the change is
  "add the JS/TS branch," not "design a new step."
- **priority:**
  - `effect` = 0.8 — closes a real, structural blind spot in the existing mutation-testing gate for
    the exact codebase (padsplit-cockpit) where 3 real bugs shipped in one day.
  - `confidence` = 0.85 — extremely mature, gold-standard tool, direct CLI equivalence to the existing
    `mutmut` invocation pattern.
  - `phase_fit` = 1.0.
  - `risk_reduction` = 0.75 — restores parity between the loop's OWN documented safety net and the
    codebase it's supposed to protect.
  - `uncertainty` = 0.3 — well-understood, low novelty-risk mechanism (it's the same technique already
    adopted for Python, just the JS/TS sibling).
  - `cost_to_test` = 0.15 — `npx stryker init` + a config file + one impl-file run at the existing
    120s timeout budget.
  - **priority = 0.40·(0.8×0.85) + 0.20·1.0 + 0.15·0.75 + 0.10·0.3 − 0.15·0.15 = 0.272 + 0.20 + 0.1125
    + 0.03 − 0.0225 = 0.592 ≈ 0.59**
- **risks:** Stryker requires a real TS build + test command to run mutants against (slower per-
  mutant than `mutmut`'s Python interpreter loop) — the existing 120s soft-timeout pattern
  (`orchestrator.md`: "skip silently if mutmut not installed or times out") should be reused verbatim
  so a slow Stryker run degrades gracefully rather than blocking the loop.
  **Transfer-condition check:** (a) execution context — a working `npm`/`npx` on PATH (already
  confirmed working per `learnings.md`'s 2026-07-08 taxahead entry: "`npm`/`npx`... DO resolve" even
  though `bun` doesn't) and a passing test command Stryker can re-run per mutant. (b) padsplit-cockpit
  satisfies this (it already has a working `npm run test`/vitest setup). (c) **structural** once
  wired as an advisory (non-blocking) step mirroring `mutmut`'s current usage — surviving mutants are
  reported, not silently absorbed, same as today.

**Falsifiable `experiment`:** metric = mutation score (% killed) on one padsplit-cockpit implementation
file already touched by the fixture-flakiness or RLS fix (e.g. the `seedOrgWithUser` helper or the
RLS-policy-adjacent Prisma middleware). baseline = the file's current test coverage as measured by
line/branch coverage alone (what the team already has via `slipcover`-equivalent for TS, or none if
untracked). variant = the SAME file run through `npx stryker run`, reporting surviving mutants.
decision = accept as an adopted gate step only if it surfaces at least one genuinely untested branch
in a file the team already believes is well-tested (a real, falsifiable check — not "it ran cleanly").
predicted_effect: at least one surviving mutant on a fixture-helper file, given the class of bug that
already escaped there. kill_criterion: if Stryker reports 100% mutation score with zero actionable
findings on every file tried, and per-mutant runtime makes the gate impractically slow (>10x the
existing mutmut budget), drop it as not-worth-the-cost for this repo size, and note the finding rather
than force adoption.

---

## Candidate 4 — fast-check (property-based testing) for fixture-generation

- **source:** https://github.com/dubzzz/fast-check — verified via `gh api`: 5,056 stars, MIT, created
  2017-10-30, pushed 2026-07-10 (same day). Description: *"Property based testing framework for
  JavaScript (like QuickCheck) written in TypeScript."*
- **maturity:** mature, high-adoption, MIT, actively maintained; the de facto TS/JS property-testing
  library (analogous to Python's `hypothesis`, also independently confirmed real and active: 8,769
  stars, created 2013, pushed 2026-07-08, `gh api` confirmed).
- **claim:** the "fixture tautology" bug class is independently logged at least 3 times in
  `learnings.md` (2026-06-24 ×2: hardcoded/crafted-to-match test fixtures; 2026-07-09: hardcoded,
  non-randomized fixture emails colliding on a unique constraint). Each time, the FIX was
  instructional ("use real Oga labels," "randomize the fixture email") — exactly the FIXED-vs-PATCHED
  distinction the project's own 2026-07-03 `learnings.md` entry warns about: a prose reminder to
  "randomize your fixtures" is a patch on the one instance; property-based generation (`fc.emailAddress()`,
  `fc.uuid()`, `fc.string()` for arbitrary-but-valid fixture fields) makes hardcoded/collision-prone
  fixture values structurally harder to write in the first place, because the natural API for
  generating test data is "give me an arbitrary valid X," not "hand-type a specific X."
- **where_it_wires_in:** `roles/test_writer.md` — when writing fixture-seeding helpers
  (`seedOrgWithUser` and any sibling `seed*` helper), use `fast-check` arbitraries for any field that
  must be unique-but-otherwise-arbitrary (emails, IDs, org names) instead of a literal string constant.
  Directly informs the existing "Fixture tautology" rule already written into `learnings.md` and (via
  Oga's review habits) into how Test-writer dispatches are checked.
- **triage:** **IMPLEMENTABLE_NOW** — an `npm install fast-check` + a rewrite of the specific fixture
  helpers already implicated in the 2026-07-09 incident.
- **priority:**
  - `effect` = 0.7 — targets a real, 3-times-recurring bug class, but narrower blast radius than the
    DB-isolation (Candidate 1) or RLS (Candidate 2) fixes, since property-based fixture generation
    only prevents COLLISION-shaped bugs, not the shared-DB-state or RLS-policy classes.
  - `confidence` = 0.85 — extremely mature, well-documented, directly Vitest-compatible.
  - `phase_fit` = 1.0.
  - `risk_reduction` = 0.6.
  - `uncertainty` = 0.35 — low novelty risk; the main unknown is Test-writer adoption discipline
    (will future fixture helpers actually use arbitraries), which is itself the same
    instructional-vs-structural question — see risks below.
  - `cost_to_test` = 0.1 — trivial to try on one fixture helper.
  - **priority = 0.40·(0.7×0.85) + 0.20·1.0 + 0.15·0.6 + 0.10·0.35 − 0.15·0.1 = 0.238 + 0.20 + 0.09 +
    0.035 − 0.015 = 0.548 ≈ 0.55**
- **risks:** **Transfer-condition check:** (a) execution context — none beyond `npm install`+import.
  (b) satisfied trivially. (c) **this one is only PARTIALLY structural** — fast-check makes it EASY to
  generate non-colliding fixture data, but nothing forces a Test-writer to use `fc.emailAddress()`
  instead of a literal string; a Test-writer can still hardcode a value with fast-check installed and
  unused. Flagging this explicitly per the role brief's guardrail: **the guarantee here is
  instructional at the point of use (a Test-writer must choose to use an arbitrary), even though the
  library itself is a structural improvement over "remember to randomize by hand."** Pair this
  candidate with a cheap, real structural backstop: a lint rule / grep-based check (same pattern as
  the project's own `no-contiguous-literals` sweep already used elsewhere) that flags a literal
  string assigned to a field named `email`/`*Email` inside any file matching `seed*`/`*fixture*` —
  this converts "use fast-check" from a suggestion into a checked convention.

**Falsifiable `experiment`:** metric = whether a rewritten `seedOrgWithUser` (using `fc.emailAddress()`
for the email field, sampled once per test run via a seeded PRNG for reproducibility) reproduces the
exact 2026-07-09 collision when deliberately run 50× against a shared, non-reset dev DB (baseline:
current hardcoded-email version, expected to collide within a bounded number of runs, reproducing the
documented bug on demand — a genuine regression test for the incident itself). variant: the
arbitrary-generated version, same 50 runs, expected zero collisions. decision: accept only if the
variant achieves zero collisions across the full run AND the lint-rule backstop above independently
fires when tested against a deliberately-reintroduced hardcoded literal (a sabotage-smoke-test, per
the project's own already-documented technique from the 2026-07-03 "Sabotage-smoke-test" learnings.md
entry). kill_criterion: if the seeded-PRNG arbitrary generator itself produces a collision (e.g. a bad
seed choice), treat as a harness-fault in the experiment design, not evidence against the technique.

---

## Candidate 5 (lower priority, part b of the task) — Multi-phase roadmap/document-persistence patterns from MetaGPT / ChatDev / Aider

**Framing:** loop-team already has a comparable mechanism (`ROADMAP.md`/`NEXT_PHASE.md`, git-branch-
name-encodes-phase convention, `fix_plan.md` as a durable gate-hole log, per-run `runs/<ts>/` dirs).
The question this candidate answers is whether any of the named frameworks (MetaGPT, ChatDev, AutoGen,
OpenHands, SWE-agent, Devin/Cognition, Aider, CrewAI) have a MATERIALLY better mechanism worth porting
— the honest answer, after checking real sources, is: not a structural upgrade, but two lightweight,
concrete, real ideas are worth noting.

- **MetaGPT (github.com/FoundationAgents/MetaGPT — note: moved from `geekan/MetaGPT`, redirect
  confirmed via `gh api`)** — verified via `gh api`: 69,282 stars, MIT, created 2023-06-30, **last
  push 2026-01-21 — ~5.5 months stale as of this scan (2026-07-10)**, despite its star count. This is
  itself a DECAY signal worth logging (a huge, widely-cited repo that has gone quiet for over half a
  year). Verified via direct fetch of `metagpt/actions/write_prd.py`: MetaGPT's SOP pattern persists
  every phase's artifact as a versioned `Document` object (`self.repo.docs.prd.save()`), tracks which
  files changed per iteration (`self.repo.docs.prd.changed_files`), and emits an explicit completion
  message (`"PRD is completed"`) consumed by the next phase's action. **The transferable idea:**
  phase-transition state as a structured, versioned artifact with an explicit machine-readable
  completion signal — closer to what loop-team ALREADY does with `fix_plan.md` CLOSED headings and
  `plan_check_log.md`, but MetaGPT's pattern additionally tracks a `changed_files` diff per phase,
  which loop-team does not currently do explicitly at the phase (not micro-step) level for a
  multi-phase project like TaxAhead's stated 10-phase plan.
  **Triage: WATCH** — the concept is validated by a widely-cited (if currently quiet) project, but
  adopting MetaGPT itself is not recommended (decay signal + architecture mismatch: MetaGPT runs its
  own agent loop, not a drop-in library loop-team could wire into `orchestrator.md`).
  **priority:** effect 0.35, confidence 0.45 (real+shipped code, but decayed + narrow relevance),
  phase_fit 0.5 (relevant to "keep clear structure," a real but non-acute ask), risk_reduction 0.35,
  uncertainty 0.4, cost_to_test 0.3 (would require designing a phase-state schema, not a config swap).
  priority = 0.40·(0.35×0.45) + 0.20·0.5 + 0.15·0.35 + 0.10·0.4 − 0.15·0.3 = 0.063 + 0.10 + 0.0525 +
  0.04 − 0.045 = **0.21** — parked well below the bug-catching candidates above, appropriately, since
  it addresses a hygiene concern rather than the acute, actively-recurring pain point.

- **Aider (Aider-AI/aider, already on radar as WATCH/RESEARCH_ONLY)** — verified via WebSearch of
  aider's own official docs (`aider.chat/docs/usage/conventions.html`). Real, concrete, lightweight
  pattern: a `CONVENTIONS.md` file, loaded read-only and cache-marked into every session
  (`aider --read CONVENTIONS.md`), explicitly recommended to be kept "under 200 lines for reliable
  rule adherence." **Not a new idea for loop-team** — this is functionally identical to what
  `~/Claude/CLAUDE.md` + per-project `CLAUDE.md` files + role briefs already do (a persistent,
  explicitly-loaded standards document). No action item here beyond confirming loop-team's existing
  practice already matches the field's best-known lightweight pattern — logged as a corroboration,
  not a new candidate, per the radar's own dedup discipline.

- **ChatDev, AutoGen, OpenHands, SWE-agent, CrewAI:** already tracked on `research/radar.md`
  (AutoGen: DECAYING/REJECTED; CrewAI/CAMEL/ChatDev: WATCH/RESEARCH_ONLY; OpenHands: WATCH/TESTABLE
  with a real Stop-hook quality-gate mechanism already mined in the 2026-07-08 compiler-feedback dive).
  No new phase/roadmap-tracking mechanism was found in any of them beyond what the existing radar rows
  already document (OpenHands's Stop-hook pattern is about per-step quality gating, not multi-phase
  roadmap tracking specifically). **Devin/Cognition:** confirmed via WebSearch that Devin remains a
  closed product with no public repo — its internal "Devin Wiki"/playbook system for maintaining
  context across long sessions is described in Cognition's own blog posts but not independently
  verifiable via source code; treated as RESEARCH_ONLY / not independently confirmable, per the
  honesty bar (no repo to open and quote).

**Bottom line for part (b):** loop-team's existing `ROADMAP.md`/`NEXT_PHASE.md`/`fix_plan.md`/
git-branch-naming apparatus is not behind the field — none of the surveyed frameworks has a
meaningfully better mechanism for multi-phase state tracking that's also adoptable (MetaGPT's closest
analog is decaying and architecturally mismatched). The one concrete, low-cost improvement worth
flagging: adopt MetaGPT's "explicit changed-files-per-phase" idea as a documentation convention — when
Oga updates `ROADMAP.md`/`NEXT_PHASE.md` at a phase boundary (for TaxAhead's stated 10-phase plan or
padsplit-cockpit's spec v3 phases), also record the file-diff/commit-range that phase actually touched,
directly in that phase's roadmap entry — this is a config/prose change, not a new dependency, and
directly answers Nnamdi's "keep clear structure/timeline" ask without adopting new infrastructure.
This is a documentation-convention recommendation, not a PACE-gated experiment (no measurable metric
to A/B against) — handed back as a low-cost, low-risk suggestion, not queued in the dive-in queue.

---

## Ranked dive-in queue (this dossier only)

| Rank | Candidate | Priority | Triage | Target project |
|---|---|---|---|---|
| 1 | Transactional per-test DB isolation (Candidate 1) | 0.61 | IMPLEMENTABLE_NOW | padsplit-cockpit |
| 2 | Stryker JS/TS mutation testing (Candidate 3) | 0.59 | IMPLEMENTABLE_NOW | padsplit-cockpit (+ taxahead if TS) |
| 3 | pgrls/rlsgrid RLS static analysis + test-matrix (Candidate 2) | 0.56 | TESTABLE | padsplit-cockpit |
| 4 | fast-check property-based fixture generation (Candidate 4) | 0.55 | IMPLEMENTABLE_NOW | padsplit-cockpit |
| 5 | MetaGPT changed-files-per-phase documentation convention (Candidate 5) | 0.21 | WATCH (doc-only, not PACE-gated) | both (roadmap docs) |

**Diversity rule applied:** candidates 1-4 all sit in the SAME active-phase bucket (bug-catching /
gate layer) and compete for the same experiment slot; per the "diversity, not greedy top-N" rule,
Oga should not simply always pick #1 — but #1 (DB isolation) is recommended as the FIRST dive-in
specifically because it is the only candidate that structurally addresses the SPECIFIC incident named
in the dispatch (fixture flakiness), has the highest confidence (established libraries, exact stack
match), and lowest cost-to-test. #2 (Stryker) is recommended as the SECOND dive-in regardless of
outcome on #1, since it closes a genuine structural gap in the existing loop (mutmut's Python-only
scope) that is otherwise silently unaddressed forever.

## Why padsplit-cockpit, not TaxAhead, for the first PACE experiment

Every real bug in the triggering incident (fixture flakiness, orphaned DB row, RLS cross-tenant FK
gap) is documented against padsplit-cockpit specifically (`learnings.md`, 2026-07-09 entries). The
dispatch context states TaxAhead's Phase 1 (core runtime + Vault) is "done+verified" with no reported
bug cluster; its tech stack (Python vs TS, Postgres vs another store) was not confirmed anywhere in
context available to this research pass, and per the role brief's honesty bar, I am not guessing it —
sizing a DB-isolation/RLS-analyzer experiment on an unconfirmed stack risks a wasted dispatch. All 4
of the top candidates are directly grounded in padsplit-cockpit's CONFIRMED stack (Postgres + Prisma +
Vitest + Next.js/TypeScript, repeatedly referenced across `learnings.md`). Recommend Oga confirm
TaxAhead's stack via a quick Mode D dispatch or direct read before deciding whether Candidates 1-4
generalize there too.

## Sources consulted (all opened/fetched directly, not from training-data memory)

- `gh api repos/pgrls/pgrls`, `gh api repos/matte97p/rlsgrid`, `gh api repos/chax-at/transactional-prisma-testing`, `gh api repos/codepunkt/vitest-environment-prisma-postgres`, `gh api repos/stryker-mutator/stryker-js`, `gh api repos/dubzzz/fast-check`, `gh api repos/geekan/MetaGPT` (redirects to `FoundationAgents/MetaGPT`), `gh api repos/HypothesisWorks/hypothesis` — all via direct `gh` CLI calls, raw JSON confirmed (stars/license/created/pushed dates quoted above).
- `gh search repos` for: `"prisma" "test" "transaction"`, `"row level security" test policy`, `"supabase" "test" "RLS"` — used as lead generation only, every hit that made it into this dossier was independently opened and quoted per the honesty bar.
- WebFetch (direct, raw-README where possible to reduce rendered-page summarization risk):
  `github.com/pgrls/pgrls` (+ `raw.githubusercontent.com/pgrls/pgrls/main/README.md` for the exact
  rule-ID quotes), `github.com/matte97p/rlsgrid`, `github.com/chax-at/transactional-prisma-testing`,
  `github.com/codepunkt/vitest-environment-prisma-postgres`, `github.com/stryker-mutator/stryker-js`,
  `raw.githubusercontent.com/FoundationAgents/MetaGPT/main/metagpt/actions/write_prd.py`.
- WebSearch: `aider.chat/docs/usage/conventions.html` (Aider CONVENTIONS.md pattern), general search
  for Devin/Cognition architecture (no independently-verifiable repo found — noted as RESEARCH_ONLY /
  not independently confirmable).
- Full re-read of `research/radar.md` (all rows, all sections, the full change log) and
  `loop-team/learnings.md` (all 2061 lines, read in 5 sequential chunks) as the dedup/prior-art check
  required before any candidate in this dossier was proposed.
