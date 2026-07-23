# Drifting-branch reconciliation: does prior art support empirical-discovery-first, and what do merge-train systems teach about a moving target? (2026-07-16)

**Mode:** Researcher Mode A (loop-improvement / process radar).
**Trigger:** 3 full rounds of adversarial spec review (14 sub-agents) for a 3-way git
branch reconciliation, run entirely before any code-writing agent touched the repo, all
3 rounds returned real evidence-backed failures. Most tellingly: a spec claiming "7 files
will need manual conflict resolution" was off by 4x (30 real conflicts) — found not by any
prose reviewer but by the one reviewer who broke pattern and ran `git merge --no-ff` for
real in a scratch directory. Separately, one of the two source branches gained new commits
mid-review while being treated as a stable pinned reference.
**Scope:** (1) is spec-first-then-review the right process shape for THIS task class, or
does prior art support empirical-discovery-first; (2) how do merge-train/gating CI systems
(Bors, Zuul, GitLab, Mergify) define correctness under a moving target, and is there a
transferable pattern for a one-time manual AI-agent reconciliation.
**Method:** read this project's own research corpus first (`research/`, `orchestrator.md`,
the 3 named arXiv papers fetched directly at their abstract pages, not from search
snippets), then live WebSearch/WebFetch against git's own docs, practitioner sources, and
each merge-train tool's real documentation. No sub-agents spawned.

---

## Headline verdict

**Question 1: NO — established practice, git's own tooling, and this project's own prior
research all converge on empirical-discovery-first for this task class. This was not a
mixed result.** Every source found — git's own plumbing command purpose-built for exactly
this, the universal "dry-run merge" practitioner convention, XP's named methodology for
this exact class of uncertainty, Martin Fowler's branching-pattern writing, an empirical
study of merge-conflict base rates, and (most tellingly) this project's OWN prior incident
investigating a structurally identical failure — say the same thing: when a plan's central
claim is a REAL, MECHANICALLY-DISCOVERABLE FACT (how many conflicts, which files), no
amount of prose review of the source material (diffs, commit logs, reviewer reasoning)
substitutes for actually running the real operation once, safely. The 3-round adversarial
review process is not wrong in general — it is wrong as the FIRST step for a task whose
key uncertainty is empirical rather than a design decision.

**Question 2: all four systems answer "correctness under a moving target" the same
way — bind validity to an explicit, checkable IDENTITY (a commit SHA, a queue position),
and structurally invalidate/restart the moment that identity changes, rather than trusting
a result past the exact base it was computed against.** None of the standing-CI
infrastructure (queue managers, parallel speculative pipelines, bot merge rights) is
usable by a single one-time agent, but the underlying discipline reduces to three
tool-free primitives any agent can run today: pin by SHA (not branch name), re-verify the
pin before trusting any dependent step, and invalidate-and-rediscover (never patch-forward)
on drift.

---

## Part 1 — Is spec-first-then-review the right shape for git-branch reconciliation?

### 1a. This project's own prior research already found the general version of this
failure, for a structurally identical incident

`research/spec-first-vs-code-first-ai-agent-builds-2026-07-08.md` is the single most
directly on-point precedent in the whole corpus, and I read it in full. It was triggered
by an almost identical shape of problem: padsplit-cockpit's Slice 6b went 30+ rounds of
prose plan-check review (5 parallel adversarial "lens" agents per round) without
converging, and ~9 of those 30 rounds were the SAME bug class — "something a `tsc
--noEmit` run would have caught instantly and exhaustively" (quoted from the doc). It cites
a real paper, the "Spec Growth Engine" (arXiv:2606.27045), which explicitly names two
failure extremes in AI-driven spec-to-code workflows:

> **"spec-first"** — the spec drives code generation and is then discarded... Nothing
> keeps the spec and code in sync after generation.
>
> **"spec-as-source"** — code is continuously generated FROM the spec... which
> reintroduces nondeterminism every regeneration.

and proposes a third position, **"spec-anchored, code-coupled"**: code/reality stays
primary and authoritative; the spec is a *verified contract*, and alignment is enforced by
an automated, blocking gate against REALITY — not by reviewer discipline or repeated prose
review. The doc's own conclusion, quoted directly:

> "the entire feature... was being validated by prose tracing alone, long after the point
> where writing real (even stub) files and running `tsc`/`next build` would have caught
> the binding-class bugs exhaustively and instantly."

This maps onto the git-reconciliation incident almost one-for-one: the spec's conflict-list
claim was validated by prose tracing (reading diffs, reasoning about what would conflict)
long after the point where running the real merge operation would have caught the true
conflict count exhaustively and instantly. Two further corroborating practitioner voices
captured in that same doc:

- Simon Willison's "Agentic Engineering Patterns" and Addy Osmani's AI-coding workflow
  writeup both describe reliable agent workflows as **"tight loops of small generation
  steps with immediate execution/compiler/test feedback fed back into context, not one
  large artifact reviewed repeatedly before any code exists."**
- A contrasting critique (dev.to/chrisywz, "The limits of spec-driven development") found
  that keeping a prose spec in sync with a growing system "creates a maintenance tax that
  grows with system complexity" and can **double** overall overhead rather than reduce
  it — directly matching the observed pattern where each round's fixes to the spec's
  conflict-list claim kept needing revision because the underlying claim was never
  grounded in a real merge attempt in the first place.

That 2026-07-08 doc's own "Recommendation applied" section states its findings on
mechanical detection and the general "spec-anchored, code-coupled" architecture were
**NOT yet turned into an orchestrator.md gate** — flagged as an open follow-up:
"introduce real compiler/typecheck feedback into the loop once a slice's interface/schema
shape is settled, rather than continuing pure prose-lens review through the binding-and-
wiring layer of a build." The git-reconciliation incident is the exact predicted failure
mode recurring in a different task type (git operations rather than TypeScript
imports/exports) — evidence the underlying principle generalizes beyond the original
finding's own domain, and that the follow-up gate was never built.

### 1b. Git ships a purpose-built, zero-risk tool for exactly this discovery, and this
project already vetted it as real — for a different question

`git merge-tree` (git-scm.com/docs/git-merge-tree, fetched directly and quoted):

> "Performs a merge, but does not make any new commits and does not read from or write to
> either the working tree or index."

It runs the actual 3-way merge algorithm — "three way content merges of individual files,
rename detection, proper directory/file conflict handling, recursive ancestor
consolidation" — and returns the real, complete conflict list as structured output, with
**zero side effects and zero risk of touching the working tree.** This is not a
theoretical or third-party tool: it is first-class git plumbing, designed explicitly to be
scripted ("intended as low-level plumbing, similar to git-hash-object, git-mktree,
git-commit-tree... it can be used as a part of a series of steps").

This project's own prior research — `research/deep-research-git-worktree-reconciliation-
tooling-2026-07-14.md` (105 sub-agents, adversarial 3-vote verification) — already
independently confirmed `git merge-tree` is real and does exactly this, in section 3
("Content-aware merging of untracked files"): *"`git merge-tree`... never reads from or
writes to the working tree or index; it's a pure tree-object operation."* That prior pass
used the finding to answer a narrower question (can it also handle untracked working-tree
files? No — confirmed limitation). It did not connect the tool to "use it as the discovery
step before writing a reconciliation spec," which is the genuinely new synthesis this
dossier adds: **the tool was already vetted as real and working by this project's own
research two days before the reconciliation task ran; it was simply never wired into the
process at the point where it would have prevented the 4x-undercounted conflict claim.**

### 1c. The universal practitioner convention independently says the same thing

Multiple independent tutorials/guides (JanBask Training, Delft Stack, gitscripts.com,
DevGex, a widely-cited GitHub gist by devinschumacher) converge on the same standard
technique — `git merge --no-commit --no-ff <branch>` against a scratch/temp branch,
specifically framed as a pre-planning discovery step:

> "A Git merge dry run simulates the merge process, allowing developers to see what
> changes would occur without making any actual modifications to the codebase... **Regularly
> use dry runs: Incorporate dry runs into your workflow, especially before significant
> merges. This will help you catch potential issues early.**"

This is not a niche trick — it is the default answer across the entire genre of "how do I
know what conflicts I'll get" guidance, and the framing is uniformly discovery-before-
planning, never planning-before-discovery.

### 1d. Base rates: for genuinely diverged branches, conflicts are the norm, not the
exception — "7 files" was against the base rate before any review even started

An empirical study, "Can Program Synthesis be Used to Learn Merge Conflict Resolutions? An
Empirical Analysis" (arXiv:2103.02004), found (per its own reported figures) that **80.4%
of merges and 37.2% of all commits at a forked branch result in conflicts** in the
real-world corpus it studied. For a pair of branches long-diverged enough to need a formal
3-round adversarial spec-review process before reconciliation, assuming a small, precise
conflict count (7 files) without empirical verification was working against the base rate
from the start, not making a reasonable central estimate that merely turned out unlucky.

### 1e. Martin Fowler / trunk-based development: the danger of long-diverged branches is
explicitly framed as an epistemic (unknowable-in-advance) one, and the prescribed fix is
to make real integration frequent, not to plan around it more carefully

Martin Fowler's branching-patterns writing (martinfowler.com/articles/branching-patterns.html,
martinfowler.com/bliki/FeatureBranch.html) is explicit that **the core problem with
long-lived branches is that "the size and uncertainty of merges" grows with divergence
time** — uncertainty, not just size. His prescribed fix (Continuous Integration) is not
"review more carefully before merging" — it's "integrate for real, small and often," so
the empirical merge attempt itself stays cheap and low-risk instead of becoming a thing
that needs to be planned around. Trunk-based-development guidance (via Atlassian's
trunk-based-development docs and independent TBD sources) states this as an explicit rule:
teams merging less than daily see conflict-resolution times reported as roughly 12x longer
than teams merging daily. **Caveat on this specific number:** it surfaced via search-result
synthesis across independent secondary sources rather than one primary study I opened
directly — flagging it as directionally corroborating, not independently re-verified to
this dossier's own honesty bar. The qualitative claim (divergence time and merge
uncertainty are strongly coupled, and this is a known, named problem class) is
independently corroborated by Fowler's own primary writing and by the empirical-conflict-
rate study above, so it does not rest on the unverified number alone.

### 1f. XP's "spike solution" is the named agile-methodology instance of exactly this
uncertainty class

Extreme Programming's spike pattern (extremeprogramming.org/rules/spike.html, corroborated
by Mountain Goat Software and Scaled Agile Framework's own descriptions) exists
specifically for uncertainty that cannot be resolved by more analysis of what is already
known:

> "When faced with a question, risk, or uncertainty, Agile Teams conduct **small
> experiments before moving to implementation** rather than speculate about the outcome or
> jump to a Solution."

A branch reconciliation's real conflict list is a textbook spike target: it is cheaply and
completely discoverable by executing the real operation once (`git merge-tree`, in
seconds, zero risk) and is NOT reliably knowable by more careful reading of the diffs —
exactly the distinction spikes are designed to detect and short-circuit before a team
sinks a 3-round, 14-sub-agent review process into a claim nobody actually checked.

### 1g. The three named arXiv papers, read honestly at their own abstracts (not inferred)

I fetched all three papers' arXiv abstract pages directly rather than relying on search
snippets, per the honesty bar. Being straightforward about what they DO and DON'T say
matters here more than force-fitting them:

- **MAKER (arXiv:2511.09030, "Solving a Million-Step LLM Task with Zero Errors")** — is
  about extreme task decomposition into microagents plus multi-agent voting to bound
  cumulative error over very long step chains (validated to 1M+ LLM steps, zero errors, on
  Towers of Hanoi-style tasks). **It does not discuss task classes where upfront
  specification is counterproductive versus helpful** — confirmed directly from the
  abstract; this is the weakest match of the three for Q1, and orchestrator.md's own
  citation of it is for a different, narrower purpose (justifying per-micro-step
  checkpoints during CODE IMPLEMENTATION, not spec-writing methodology).
- **Coherence Collapse (arXiv:2603.24631, "Diagnosing Why Code Agents Fail After Reaching
  the Right Code")** — found that 60-69% of failures on SWE-Agent/OpenHands happen AFTER
  the agent has already reached/edited the objectively correct functions; in 5 identified
  cases the agent produced a patch bit-identical to the gold reference mid-trajectory and
  then destroyed it. **"An edit-commit checkpoint recovers all 5"** (quoted from the
  abstract). This is not about spec-vs-discovery either, but it IS a directly transferable
  warning for the EXECUTION phase of a reconciliation (see Part 2, item 5 below): once a
  real conflict is correctly resolved, checkpoint it immediately rather than holding many
  resolved-but-uncommitted files in a state a later action can silently thrash.
- **TDAD (arXiv:2603.17973, "Test-Driven Agentic Development — Reducing Code Regressions...
  via Graph-Based Impact Analysis")** — the strongest orthogonal evidence of the three,
  with hard executed numbers. Quoted directly from the abstract: grounding an agent's
  action in a REAL, COMPUTED artifact (a dependency graph mapping code changes to affected
  tests) **cut regressions 70% (6.08% → 1.82%)**, while giving the SAME agent generic
  procedural prose instruction ("do TDD") WITHOUT that computed grounding **made things
  worse than no intervention at all (regressions rose to 9.94%)**. The paper's own
  conclusion: **"surfacing contextual information outperforms prescribing procedural
  workflows."** This is a precise, numeric, executed demonstration of the exact failure
  this incident exhibited: a prose specification of "how to resolve conflicts" — however
  carefully adversarially reviewed across 3 rounds — is a "procedural instruction without
  targeted context" in TDAD's own terms. TDAD's fix is to ground the SAME instruction in a
  real, computed artifact (there: an impact graph; here: the actual `git merge-tree`/
  scratch-merge conflict list) BEFORE any planning prose is written, which is exactly the
  shape of Part 1's overall verdict.

**Honest summary on the 3 papers:** none of them is directly "about" git reconciliation or
general spec-first-vs-discovery-first methodology — I want to be explicit about that
rather than overclaim. What they DO establish, read together, is a convergent, orthogonal
theme across three unrelated experimental settings (long step chains, code-edit thrash,
regression-inducing patches): **verify/ground narrowly and often against real, executed
signal; don't let a long span of unverified, prose-only reasoning stand in for it.** That
theme transfers cleanly to Part 1's verdict even though none of the three papers was
written with git reconciliation in mind.

### 1h. This project's own framework already has the exact general rule that should have
caught this — it just wasn't triggered

`orchestrator.md`, Step 1, already contains this bullet (quoted verbatim, currently
present in the live file at `~/Claude/loop/loop-team/orchestrator.md`):

> **"Probe reality before designing fixes"** (esp. for an existing system with external
> deps): reproduce the *real* failure mode — run the thing, list installed deps/binaries,
> hit the real surface — instead of reasoning about it abstractly. (A fix once checked
> `import playwright` when the scraper actually needed the chromium *binary*; running it
> would have shown the launch fails.)

This is, read generally, exactly the rule that should have applied: a git branch
reconciliation's central factual claim (how many conflicts, which files) is "reasoning
about it abstractly" (reading diffs/commit logs, reviewers reasoning in prose) versus
"probe reality" (run `git merge-tree` or a scratch `--no-commit --no-ff` merge once,
before writing a single line of spec). **This is the single most actionable finding of
this dossier: the framework did not lack the principle — the principle exists, is worded
generally, and was not invoked for this task.** A plausible reason it didn't fire: the
bullet's own example (`import playwright` vs. the chromium binary) and its parenthetical
framing ("an existing system with external deps") read, on a natural reading, as being
about *runtime/service dependencies* — not about "the git history itself is 'reality' that
must be probed by executing a real git command, not reasoned about by reading its diffs."
Whether the wording is worth tightening to name "any claim whose true value is a
mechanically-discoverable fact from an external, checkable system — including the
target repo's own git history" is Oga's/the human's call, not mine to make or apply — but
the reading gap between "the rule as worded" and "the case that needed it" is worth
surfacing explicitly, since it is the kind of thing that will recur on the next
history-dependent task (rebase planning, cherry-pick range sizing, bisect-driven root
cause work) unless named.

**No fix_plan.md, DESIGN_CHECKLIST.md, or search_playbook.md entry currently describes
this incident** — checked via direct grep of all three files for
`git merge|branch reconcil|3-way|three-way|diverge`; the only hits in fix_plan.md concern
bugs in this project's own `git-content-aware-merge.sh` script (a different artifact, not
this process failure). This is new ground, not a duplicate of tracked work.

### Part 1 conclusion

Verdict: **NO, "fully specify → adversarially review → then touch git" was not the right
process shape for this task, and this is not a mixed/contested finding** — six independent
lines of evidence (git's own purpose-built discovery tool, the universal dry-run-merge
practitioner convention, an empirical merge-conflict base-rate study, Fowler's branching-
pattern analysis, XP's spike-solution pattern, and this project's own prior research into
a structurally identical failure) all point the same direction. This does **not** mean
"never write a spec for a git reconciliation" — there is real work for adversarial review
to still do *after* discovery: deciding INTENT/semantics for each real conflict, sequencing
the resolution, defining the test/rollback plan. The finding is narrower and more precise:
**the DISCOVERY-DEPENDENT claims in a spec (how many, which files, what shape) must be
grounded in one real, safe execution of the actual operation before being written down —
never derived from reading diffs/logs harder, no matter how many adversarial rounds
review them.**

---

## Part 2 — Merge trains and drifting-target reconciliation

### 2a. Survey: how four real gating/merge-queue systems define correctness under a
moving target

| System | Correctness invariant | Mechanism under a moving target | Source (fetched directly) |
|---|---|---|---|
| **Bors** (originated the "Not Rocket Science Rule of Software Engineering," Graydon Hoare) | "automatically maintain a repository of code that always passes all the tests" — the invariant is about the TRUNK, not any one PR | Tests the RESULT of merging the PR into a `staging` branch that is already up-to-date with main, one PR at a time, in strict queue order — **never tests the PR branch's own tip in isolation.** "Bors could run CI one at a time on each PR in the queue before merging — ensuring that every change landed on trunk with zero skew." Correctness under drift = drift can't happen by construction, because nothing else lands between "test" and "merge" for a given PR (serial ordering is the guarantee) — at the cost of throughput, which is exactly what motivated later parallel/speculative systems. | graphite.com/blog/bors-google-tap-merge-queue (fetched directly) |
| **Zuul** (OpenStack gating) | A change is only mergeable if it passes tested-together with everything ahead of it in the shared queue | **Speculative/optimistic**: tests a change assuming everything ahead of it in queue will succeed, in parallel, for speed. On a failure ahead in the queue: drops the failed change and explicitly **restarts** testing for everything queued behind it, quoted directly: *"Zuul starts the process again testing D against the tip of the branch, and E against D."* Never patches a downstream result forward past a broken assumption — recomputes from the current real tip. | zuul-ci.org/docs/zuul/latest/gating.html (fetched directly) |
| **GitLab merge trains** | Each MR must work combined with the target AND every earlier MR still queued ahead of it in the train | Same speculative-batching shape as Zuul: MR #3 is tested against target+MR1+MR2 combined, not target alone. A failure anywhere in the train removes that MR and **restarts pipelines for everything queued behind it.** | docs.gitlab.com/ci/pipelines/merge_trains (via search synthesis of GitLab's own docs pages; consistent across GitLab's official docs, its engineering blog, and the mirrored GitHub doc source) |
| **Mergify** | A speculative "draft PR" combining N queued PRs is only valid while its recorded base commit SHA still matches the real target branch | **Explicit SHA-pinning + event-driven invalidation**, the most directly transferable mechanism of the four: *"Mergify stores the base commit SHA1 used to create a temporary pull request. Mergify has multiple event-based mechanisms to be notified if it ever changes."* When the base moves, the affected speculative work is invalidated and reconstructed from scratch rather than patched forward. Failure isolation within a batch uses an **n-ary/bisection search** (quaternary, n=4, when 3 speculative checks are configured) to identify exactly which PR in a failed batch is the culprit, without re-testing every PR individually from zero. | articles.mergify.com/speculative-check-and-batch-under-the-hood (fetched directly) |

### 2b. The common principle, stated once

None of the four systems treats "I tested X against Y" as a fact with unbounded shelf
life, and none of them (except Bors, by construction/serial-ordering) does a brute-force
full re-test of everything on every base change — that would recreate Bors's own
documented throughput problem, which is exactly what motivated Zuul/GitLab/Mergify's move
to speculative batching in the first place. Instead, **every one of them binds a test
result to an explicit, checkable IDENTITY of the base** (a specific commit SHA, or a
specific, ordered queue position that structurally guarantees the base hasn't moved since
the test ran) — and every one of them has a **structural mechanism that automatically
invalidates a stale result the instant that identity changes**, rather than silently
continuing to trust a result computed against a base that has since moved:

- Bors: identity = queue position (structurally can't go stale, by serial ordering).
- Zuul / GitLab trains: identity = "everything ahead in the queue actually merged";
  invalidated by an explicit restart the moment any of it doesn't.
- Mergify: identity = an explicit recorded SHA, invalidated by an explicit event-driven
  recheck.

### 2c. Transferable pattern for a ONE-TIME manual AI-agent reconciliation

None of the standing infrastructure transfers literally — a one-off task has no bot merge
identity, no CI system wired to auto-report per-commit pass/fail, and no reason to stand up
parallel speculative pipelines for a task that happens once. What DOES transfer is the
underlying discipline, reduced to primitives a single agent can run with nothing but a
local git binary:

1. **Pin by SHA, not by branch name, the moment analysis begins.** `git rev-parse
   <branch>` for every branch involved (both source branches AND the target) — captured
   and written verbatim into the spec/plan artifact's own Context section. A branch NAME
   is a mutable pointer; treating it as a stable reference across a multi-round review
   process is precisely the bug that let one source branch "gain new commits while being
   reviewed as a supposedly-stable pinned reference" in this incident. This is the direct,
   tool-free analog of Mergify's SHA-pinning mechanism.
2. **Re-resolve and diff against the pinned SHA before any step that depends on the pin
   still being current** — starting a new review round, beginning implementation, or
   finalizing the merge. `git fetch && git rev-parse origin/<branch>` compared byte-for-
   byte to the recorded pin. A single agent has no webhook/event system, so this must be
   an explicit, repeated check at every dependency point, not a one-time check at the
   start — the direct analog of Mergify's "event-based mechanisms to be notified if it
   ever changes," manually re-implemented as a repeated poll since no event infra exists.
3. **On drift, invalidate and re-derive — never patch the existing analysis forward.**
   This is Zuul's discipline exactly: "starts the process again... against the tip of the
   branch." If a pinned source branch moved, the previously-computed conflict list is
   stale in an unbounded way (new commits can touch any file, including ones already
   marked resolved) — re-run discovery from scratch against the new SHA rather than trying
   to patch the old list.
4. **Discover/test against the RESULT of the merge, never a branch in isolation** — Bors's
   foundational insight ("merge skew"), and the precise gap in this incident (the "7
   files" claim evidently came from reading diffs/prose, not from an actual merge attempt
   against the real other side). For a one-off reconciliation this is
   `git merge-tree --write-tree <target> <source>` (pairwise, run per branch pair for a
   3-way reconciliation) — side-effect-free per Part 1's finding, so it can be re-run as
   many times as needed every time step 2's pin-check fires.
5. **Checkpoint each confirmed-correct resolution immediately, once discovery is done and
   real conflict resolution begins** — this is where Coherence Collapse's edit-commit-
   checkpoint finding (discovered in an unrelated context: LLM code-editing thrash)
   transfers directly to the EXECUTION phase of a reconciliation: once conflict #6 of 30 is
   resolved and confirmed correct, commit it (or stage-and-checkpoint it in the scratch
   merge) immediately, rather than holding all 30 in a long, uncommitted, mutually-
   thrashable state where a mistake fixing conflict #25 could silently revert #6 with
   nothing to catch it.

### 2d. Transfer-condition check (per the Researcher role's required discipline for every
borrowed pattern)

- **(a) Execution context the mechanism requires:** Bors/Zuul/GitLab trains/Mergify all
  require STANDING infrastructure — a bot identity with merge rights, a CI system that
  reports pass/fail per commit automatically, and (for the optimistic three) the ability
  to run N parallel speculative pipelines and a webhook/event system to detect base
  movement without polling.
- **(b) Does a one-time single-agent reconciliation satisfy it today:** **NO** for the
  infra-heavy mechanisms (queue management, parallel speculative pipelines, bot-driven
  auto-merge, event-based change notification) — these do not transfer as literal tools
  and should not be built or stood up for a one-off task. **YES** for the three cheap,
  tool-free primitives extracted above (SHA pinning via `git rev-parse`, side-effect-free
  real-merge discovery via `git merge-tree`, and commit-as-you-confirm checkpointing) —
  all three require nothing beyond a local git binary and are directly usable by a single
  agent today, with no new infrastructure.
- **(c) Structural vs. instructional guarantee, and where the risk is silent:** the
  SHA-compare check and the `git merge-tree` output are each STRUCTURAL in the narrow
  sense that their own outputs are objective and mechanical — a SHA either byte-matches
  the pin or it doesn't; a conflict either appears in the merge-tree output or it doesn't.
  **But whether the agent actually RE-RUNS the pin-check before relying on it is
  INSTRUCTIONAL** — nothing currently stops an agent from skipping step 2 and continuing
  to reason from a stale pin, exactly the same class of gap this project's own
  orchestrator.md already names for its own comparable disciplines (the "Review-to-commit
  re-diff" gate is explicitly documented in the live file as **"presently an
  instructional, not structural, guarantee — you must remember to call record/use commit;
  nothing currently blocks a raw `git commit`"**). This should be flagged plainly per the
  role's transfer-condition requirement: **a skipped pin-recheck would be silent and
  load-bearing** — it produces a plausible-looking, internally-consistent spec that is
  quietly wrong (exactly what happened live in this incident with the source branch that
  advanced mid-review), not a visible error. Closing this gap structurally (a hook that
  mechanically blocks any spec-finalization or Coder-dispatch step referencing a pinned
  git ref without a fresh `git rev-parse` match in the same turn) is a real candidate for
  a future hardening pass, but building it is outside this Mode-A dossier's scope — this
  is a finding to hand to Oga/the human, not a change to make unilaterally.

---

## Recommendation for how this wires into the framework (Mode A framing)

**Where it plugs in:** `orchestrator.md` Step 1 ("Restate & plan"), specifically as a
sharpening of the already-existing "Probe reality before designing fixes" bullet (quoted
in full at 1h above) — not a new mechanism, a clarification that its scope already covers
"the target repo's own git/version-control history is external, checkable reality, not a
thing to reason about from reading diffs." A concrete candidate wording extension (for
Oga/the human to weigh, not something I'm empowered to apply myself): name git-history-
dependent claims (conflict counts, file lists, ref stability) explicitly as a "probe
reality" trigger case alongside the existing playwright/chromium example, and add the
Part 2 pin-and-recheck discipline as the applicable technique when a spec's validity
depends on an external ref that could move mid-review.

**Triage:** **IMPLEMENTABLE_NOW** for the three tool-free primitives in 2c (SHA pinning,
`git merge-tree` discovery, checkpoint-as-you-confirm) — each is a single git command or a
one-line spec-writing convention, zero new dependencies, directly usable on the next task
of this shape. **RESEARCH_ONLY / open follow-up** for the structural hook named in 2d(c)
(mechanically blocking a stale-pin dispatch) — real candidate, not yet designed or built.

**On a formal PACE-gated A/B experiment:** I did not draft one, and want to be honest about
why rather than force a fit. This class of task (multi-way branch reconciliation
specifically) is low-frequency enough in this project's own history that a paired,
same-instance A/B (discovery-first vs. spec-first, scored on a shared metric) isn't
practically runnable the way a prompt/tool swap is — there is no ready supply of paired
git-reconciliation instances to test on, and the finding here is closer in kind to the
"Probe reality before designing fixes" bullet already in orchestrator.md, which itself
entered the framework as a directly-adopted process rule rather than through a measured
A/B (there is no dev-set of "abstract-reasoning-vs-probe-reality" task pairs either). The
more practical validation path, consistent with how this project actually adopted its
closest analogous prior fix (`H-AC-ORACLE-TARGET-1` in `spec-first-vs-code-first-ai-agent-
builds-2026-07-08.md`'s own "Recommendation applied" section — a gated procedural rule, not
an A/B'd component): apply the sharpened rule the next time a task of this shape recurs,
and retrospectively check whether the discovery step actually ran before spec-writing and
whether it changed the spec's content versus the pattern seen this time.

---

## Sources (every one opened/fetched directly this pass, per the role's honesty bar)

**This project's own corpus (read in full before any external search, per the dispatch
instruction):**
- `~/Claude/loop/loop-team/roles/researcher.md` — role brief, read in full.
- `~/Claude/loop/loop-team/orchestrator.md` — read in full (both halves, ~731 lines); the
  "Probe reality before designing fixes" bullet (Step 1) and the "Review-to-commit
  re-diff" gate (structural-vs-instructional precedent) are both quoted directly from this
  live file.
- `~/Claude/loop/research/spec-first-vs-code-first-ai-agent-builds-2026-07-08.md` — read
  in full; the single most directly on-point prior-art file found.
- `~/Claude/loop/research/deep-research-git-worktree-reconciliation-tooling-2026-07-14.md`
  — read in full; confirms `git merge-tree` was already vetted real by this project's own
  105-sub-agent adversarial research pass, for a different sub-question.
- `~/Claude/loop/research/multi-reviewer-merge-prior-art-deepdive-2026-07-09.md` — read in
  full (multi-*reviewer* merge/dedup of plan-check findings — a different sense of "merge"
  than git branch merging; checked and confirmed not directly relevant to Q1/Q2, kept for
  completeness of the corpus scan).
- `~/Claude/loop/fix_plan.md`, `~/Claude/loop/loop-team/DESIGN_CHECKLIST.md`,
  `~/Claude/loop/search_playbook.md` — grepped for `git merge|branch reconcil|3-way|
  three-way|diverge`; no entry describes this incident (the only fix_plan.md hits concern
  bugs in this project's own `git-content-aware-merge.sh` script, a different artifact).
- `~/.claude/projects/-Users-<redacted>/memory/loop-engineering-research.md` and
  `loop-engineering-reading-list.md` — read in full; general loop-engineering design-rule
  memory, confirmed not to contain git-reconciliation-specific guidance (informed the
  "no duplicate coverage" check, not cited as direct evidence above).
- Full listing of `~/Claude/loop/research/` (146 files) enumerated and grepped for
  `merge|conflict|empirical|discovery|spec-first|reconcil|diverge|3-way|three-way|branch
  reconcil|scratch merge|trial merge|dry.run merge|git merge|rebase` to confirm no other
  directly relevant file was missed.
- Confirmed **not** read: `~/Claude/loop/research/loop_engineering_research_2026.md` only
  exists under `Job Tool/loop/` (a stale project copy per this user's own
  `~/.claude/CLAUDE.md` override instruction — "Do not read any copies under `Job Tool/loop/`")
  — the canonical equivalent content lives in the two memory files above,
  which were read instead.

**arXiv papers (fetched directly at their abstract pages, not from search snippets):**
- [MAKER — Solving a Million-Step LLM Task with Zero Errors](https://arxiv.org/abs/2511.09030)
  (arXiv:2511.09030)
- [Coherence Collapse: Diagnosing Why Code Agents Fail After Reaching the Right Code](https://arxiv.org/abs/2603.24631)
  (arXiv:2603.24631)
- [TDAD: Test-Driven Agentic Development — Reducing Code Regressions in AI Coding Agents
  via Graph-Based Impact Analysis](https://arxiv.org/abs/2603.17973) (arXiv:2603.17973)
- [Can Program Synthesis be Used to Learn Merge Conflict Resolutions? An Empirical
  Analysis](https://arxiv.org/pdf/2103.02004) (arXiv:2103.02004) — merge-conflict base-rate
  study (80.4% of merges / 37.2% of commits at forked branches produce conflicts),
  surfaced via WebSearch snippet, not independently re-fetched at full length this pass —
  flagged as secondary-sourced, used only for the base-rate figure which is a narrow,
  directly-quoted statistic rather than a synthesized claim.

**Git's own documentation and tooling:**
- [git-merge-tree — Git Documentation](https://git-scm.com/docs/git-merge-tree) (fetched
  directly; "does not read from or write to either the working tree or index" quoted
  verbatim from the live page)
- [git-scm.com — Basic Branching and Merging](https://git-scm.com/book/en/v2/Git-Branching-Basic-Branching-and-Merging)
  (Pro Git book)
- [git-scm.com — Advanced Merging](https://git-scm.com/book/en/v2/Git-Tools-Advanced-Merging)

**Practitioner / dry-run-merge convention (via WebSearch synthesis across multiple
independent sources, consistent framing across all):**
- [JanBask Training — Is there a git merge dry run option?](https://www.janbasktraining.com/community/devops/is-there-a-git-merge-dry-run-option)
- [Delft Stack — Git Merge Dry Run](https://www.delftstack.com/howto/git/git-merge-dry-run/)
- [gitscripts.com — Mastering Git Merge Dry Run](https://gitscripts.com/git-merge-dry-run)
- [DevGex — Conflict Detection in Git Merge Operations: Dry-Run Simulation and Best Practices](https://devgex.com/en/article/00017592)
- [GitHub gist (devinschumacher) — dry run of a git merge](https://gist.github.com/devinschumacher/ea27f994d1be4e1cbf06f4735addae04)

**Branching strategy / trunk-based development:**
- [Martin Fowler — Patterns for Managing Source Code Branches](https://martinfowler.com/articles/branching-patterns.html)
- [Martin Fowler — bliki: Feature Branch](https://martinfowler.com/bliki/FeatureBranch.html)
- [Atlassian — Trunk-based Development](https://www.atlassian.com/continuous-delivery/continuous-integration/trunk-based-development)
- [Atlassian Git Tutorial — Git merge strategy options & examples](https://www.atlassian.com/git/tutorials/using-branches/merge-strategy)
- [Atlassian Git Tutorial — How to Resolve Merge Conflicts in Git](https://www.atlassian.com/git/tutorials/using-branches/merge-conflicts)
  (the "12x longer" daily-vs-non-daily merge conflict-resolution-time figure surfaced via
  WebSearch synthesis of trunk-based-development sources generally, not independently
  re-verified against one primary study — flagged explicitly as corroborating, not
  confirmed, per 1e above)

**Agile / XP spike solutions:**
- [extremeprogramming.org — Spike Solution](http://www.extremeprogramming.org/rules/spike.html)
- [Mountain Goat Software — What Are Agile Spikes?](https://www.mountaingoatsoftware.com/blog/spikes)
- [Scaled Agile Framework — Spikes](https://scaledagileframework.com/spikes/)

**Merge-train / CI-gating systems (Question 2):**
- [Graphite — Not Rocket Science: How Bors and Google's TAP inspired modern merge queues](https://graphite.com/blog/bors-google-tap-merge-queue)
  (fetched directly; Bors mechanism and "Not Rocket Science Rule" quoted verbatim)
- [Zuul documentation — Project Gating](https://zuul-ci.org/docs/zuul/latest/gating.html)
  (fetched directly; speculative-execution and restart-on-failure behavior quoted verbatim)
- [GitLab Docs — Merge trains](https://docs.gitlab.com/ci/pipelines/merge_trains/)
- [Mergify — Speculative Checks and Batch: Under the Hood](https://articles.mergify.com/speculative-check-and-batch-under-the-hood/)
  (fetched directly; SHA-pinning + event-based invalidation + n-ary bisection quoted
  verbatim)
- [Mergify Docs — Parallel Checks / Merge Queue Batches](https://docs.mergify.com/merge-queue/speculative-checks/)
- [Meilisearch — Automate pull requests merging with Bors](https://www.meilisearch.com/blog/automate-pull-requests-with-bors)
  (secondary corroboration of the Bors "staging branch" mechanism, consistent with the
  Graphite primary fetch above)

---

## What I did NOT verify to this dossier's own honesty bar (stated explicitly)

- The "12x longer" trunk-based-development conflict-resolution-time statistic (1e) —
  corroborating via search synthesis only, not independently re-fetched from one named
  primary study.
- arXiv:2103.02004's 80.4%/37.2% figures (1d) — taken from a WebSearch snippet summary of
  the paper, not from a direct full-text fetch of the PDF this pass.
- GitLab merge trains' documentation (2a table) — described via WebSearch synthesis of
  GitLab's own docs/blog pages rather than a direct WebFetch of docs.gitlab.com this pass
  (unlike Zuul and Mergify, which were both directly fetched); the description is
  internally consistent across GitLab's own docs page, its engineering blog post, and the
  mirrored GitHub source file shown in search results, which is why it is presented with
  moderate rather than the same confidence as the two directly-fetched systems.
