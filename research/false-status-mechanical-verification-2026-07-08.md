# False status / mechanical verification before CLOSED — research dossier

Date: 2026-07-08
Mode: A-style loop-improvement research (per `roles/researcher.md`), one-off design dossier
per explicit user (Nnamdi) specification — NOT a radar entry, NOT a PACE experiment spec.
No implementation performed this run; this is research + design only. No file was edited
except this one.

**Core question:** how do we make it mechanically hard or impossible for `fix_plan.md` or
loop-team reports to say "DONE/CLOSED/PASS/fixed/verified" unless there is attached,
current, executable evidence?

---

## 1. Existing local research found (files actually opened, and what they told me)

### Role/process baseline

- **`<HOME>/Claude/loop/loop-team/roles/researcher.md`** (read in full). Governs
  the honesty bar for this dossier: real sources only, opened and quoted before citing;
  maturity signals (stars/recency/license) recorded for every repo; a "transfer-condition
  check" required for every borrowed mechanism — (a) what execution context it needs, (b)
  whether this repo's context satisfies it, (c) whether the guarantee is **structural**
  (non-compliance is impossible) or **instructional** (a participant must follow instructions),
  flagging any instructional guarantee whose failure would be silent and load-bearing. This
  last point turned out to be the single most load-bearing lens for this whole dossier — see
  §4/§7.

- **`<HOME>/Claude/loop/search_playbook.md`** (read in full, small file). Not
  directly about closure/status verification, but it demonstrates the exact discipline this
  dossier recommends transplanting: every discovery round is scored with hard denominators
  (`precision = qualifying / opened`, `false-pass rate`, `coverage`), a round is only "better"
  if the numbers say so, and templates only mutate when a measured trigger fires
  ("mutate the templates... when ANY of: a cluster misses N; precision drops below the prior
  best; or false-pass > 0"). This is the same "a claim only counts if a check can reject it"
  principle applied to search-query design — direct precedent for measuring the closure-lint's
  own catch rate rather than trusting that it works.

- **`<HOME>/Claude/loop/loop-team/learnings.md`** (read in full, 1580 lines).
  The single richest local source. Load-bearing entries:
  - **"I wrote it down" is not "I fixed it" (2026-07-03)** — the standing, permanent
    FIXED-vs-PATCHED classification this dossier's recommendation must satisfy: "before
    considering ANY incident closed, classify it explicitly as ... **FIXED** — a code/gate/
    script change now exists such that the SAME mistake is structurally harder or impossible
    ... **PATCHED** — only the one reported instance was corrected; the underlying CLASS
    remains exploitable." This is the exact test the current `fixplan_closure_lint.py`
    (wording-only) fails against a genuinely fabricated closure claim, and the exact bar the
    recommended architecture in §4 is designed to clear.
  - **"Keep verdict language OUT of checkpoint commit messages" (2026-07-01)** — git history
    itself is a co-located status channel that can leak an unverified "all green"/"verified
    PASS" claim into a place a later de-primed Verifier will read; directly informs the
    evidence-ledger design's need to keep proof **separate from narrative claims**.
  - **`cmd | tail; echo EXIT=$?` reports the wrong exit code — hit TWICE independently in
    this project.** A structural lesson for any acceptance test in this dossier's own §8:
    never pipe a verification command through `tail`/`head` before capturing its exit code.
  - **The sabotage-smoke-test technique (2026-07-03)** — a Test-writer proved its tests had
    teeth by temporarily inserting a deliberately BROKEN implementation, confirming the tests
    catch it, then restoring byte-for-byte (`git diff --stat` clean). Directly reused in §8's
    acceptance tests.
  - **"Verify the verification mechanism itself, not just its wording" (2026-07-08, taxahead
    TTS)** — 5 plan-check rounds all found gaps in HOW an acceptance criterion was checked
    (a `wrangler` binary that wasn't installed, a `bun` that wasn't on `PATH`, a git-diff check
    against an untracked directory that produces a **vacuous** "0 changes" non-check) — the
    exact failure class this dossier's recommended design must not reproduce: a proof
    mechanism whose own foundational assumption (does this command/hash-check even apply to
    this file/environment?) was never itself verified.
  - **Component-built paths evade literal greps (2026-07-01)** and **"a fix's own correction
    can introduce a WORSE bug" (2026-07-03)** — both argue for re-verifying any new gate
    against the LIVE file/environment, not against imagined fixtures only.
  - **`H-CODEX-PARITY-2026-07-08` narrative also appears here** (cross-referenced from
    `fix_plan.md`, see below) as the concrete "configured vs fired" incident.

- **`<HOME>/Claude/loop/loop-team/harness/fixplan_closure_lint.py`** (read in
  full — the actual code, not a description). **What it does:** scans `fix_plan.md`'s `## `
  heading blocks; if a block's BODY contains a closure-shaped phrase — `"PLAN_PASS achieved"`,
  `"IMPLEMENTATION COMPLETE"`, `"VERDICT: PASS"`, or a backtick-wrapped 7–40-char hex token
  within 40 characters of the word "commit" on the same line — while the HEADING does not
  contain the literal, case-sensitive uppercase token `CLOSED`, it is flagged as a mismatch.
  Exit 0 (no mismatches), 1 (mismatches found, printed as plain text), 2 (usage error).
  **What it explicitly does NOT do (confirmed by reading the code, not inferred):**
  - It never checks that a cited commit SHA actually exists in `git log` — it only regex-matches
    a backtick-hex-token-near-the-word-"commit" text shape.
  - It never re-runs any command, re-checks a test result, or touches the filesystem beyond
    reading the one target file.
  - It never checks git worktree cleanliness, staleness of referenced files, or whether the
    thing claimed CLOSED still matches the current code.
  - It is **purely a wording-consistency lint between two positions in the same document**
    (heading vs. body) — it cannot catch a heading that says CLOSED with a body that is
    internally consistent but simply **false** (a fabricated SHA, a fabricated "all green,"
    a stale claim about code that has since changed). This is precisely the "wording lint vs.
    proof validation" gap the dispatch prompt asked me to characterize.

- **`<HOME>/Claude/loop/loop-team/harness/test_fixplan_closure_lint.py`** (read
  in full). Confirms the coverage boundary exactly: tests cover heading/body consistency in
  both directions, the SHA-proximity-window edge cases (a real `doc_id` hex string is
  correctly NOT flagged), and a real-file smoke test that only asserts the tool "does not
  crash" against the actual `fix_plan.md` — there is **no test anywhere in this file that
  exercises truth-checking** (no test constructs a fixture with a fabricated-but-well-formed
  SHA, a stale file reference, or a dirty worktree), because the tool was never designed to
  check those things. This is the exact coverage ceiling the dispatch asked me to state
  precisely, confirmed by reading the tests, not assuming.

- **`fix_plan.md`** (698KB — never read whole; searched via `rg` for the required terms, 521
  hits on the closure/evidence/status-drift term set, then read specific sections at their
  line offsets):
  - **`H-FIXPLAN-CLOSURE-CONSISTENCY-1`** (line 2671, CLOSED 2026-07-03) — the entry that
    produced `fixplan_closure_lint.py`. Its own text states the origin incident precisely:
    "Oga appended 'IMPLEMENTATION COMPLETE' content without changing the heading from OPEN to
    a CLOSED form, caught only because an independent post-build Verifier happened to grep the
    heading directly." Also states, explicitly, the tool's own known limits: "a fixed instance
    is not a fixed class" (the FIXED-vs-PATCHED distinction was already being reasoned about
    here, before it was formalized as a standing rule).
  - **`H-CLAIM-LEDGER-1`** (line 4830, OPEN, filed 2026-07-07, priority LOW) — see the
    dedicated read below (`claim-ledger-goal-drift-mechanism-spec-2026-07-07.md`). The
    fix_plan.md entry itself records the final verdict verbatim: "NOT recommended to build --
    all 3 critique lenses found real, code-cited holes in the design (gameable escape hatches,
    a mis-cited async-in-flight check, a 'fail-open retry-cap' precedent that actually blocks,
    an arming heuristic that likely wouldn't have caught the incident that motivated it)."
  - **`H-SUBAGENT-MASKING-1`** (lines 2312, 2437, 2477) and **`H-SUBAGENT-COMMIT-GATE-1`**
    (lines 2694–2827) — the review-to-commit / commit-scope-gate build chain. Directly
    relevant: this chain is this repo's own closest prior art for "detect a violation of a
    review-before-commit guarantee, mechanically, using structural signals from a hook
    payload" — and its round-2 plan-check finding is a live example of exactly the
    "verify the verification mechanism" failure class: a proposed fix referenced a variable
    (`_rc_target`) not yet bound at that point in the file, which would have silently thrown
    `NameError`, swallowed by the gate's own fail-open wrapper, meaning "the entire secondary
    defense layer would never actually run, on every single invocation, forever" — a **silent,
    permanent, structural false-pass in a gate built specifically to prevent false-passes**.
  - **`H-CODEX-PARITY-2026-07-08`** (line 4863) — the concrete, sourced "configured vs fired"
    incident named in the dispatch prompt. Read in full. Quoting the mechanism directly:
    Codex's hook-trust system (confirmed at the SOURCE level, `codex-rs/hooks/src/engine/
    discovery.rs` + `codex-rs/config/src/fingerprint.rs`) "stores a SHA-256 `trusted_hash` per
    hook in `~/.codex/config.toml`'s `[hooks.state]` section, computed over the hook's
    canonicalized JSON content... change the content, the hash no longer matches, and Codex
    silently EXCLUDES that hook from dispatch (`HookTrustStatus::Modified`, not `Trusted`)
    until a human re-approves." A "reliability" edit (adding `timeout: 30`) very likely
    silently disabled all 5 loop-team safety hooks in Codex, with **zero visible error at
    edit time**. This is the canonical local proof that "the config file says the hook is
    registered" and "the hook actually fires" are two different facts, and that a system can
    diverge between them with no loud signal. Directly informs §4/§7's "configured vs fired"
    self-test requirement.
  - **`rent-from-owner ROUND 3`** (line 999) — "independent live Verifier caught a FALSE-PASS
    (460 green, live crash at nbhd 4)." Quoted directly: "The 5 dare fixes + 5 gated checks
    passed 460/460 deterministic tests but the live Verifier RAN the harness and found reality
    diverges — the exact 'green harness prints PASS while broken' trap." This is the clearest
    local evidence that a large, green, deterministic test suite is not proof of truth — only
    proof of what the suite was written to check.
  - **`H-AC-ORACLE-TARGET-1`** (line 4960, CLOSED 2026-07-08) — a hand-written adversarial AC
    survived 10 manual re-derivation rounds (rounds 20–29) checking the wrong org's table,
    caught only by round 30's ordinary re-verification. The fix that closed it is a
    **mutation-check gate**: weaken/remove the guard clause in a scratch copy, re-run the AC's
    own test, confirm it goes RED before trusting it green. This is a direct, already-adopted
    local precedent for §6's recommendation to periodically mutation-test the closure-lint
    itself.

- **`<HOME>/Claude/loop/loop-team/harness/commit_diff_reread.py`** (read in
  full — this is the closest existing analog to a hash-anchored evidence mechanism in this
  repo). Mechanism: `record <file>` snapshots the file's current bytes (sha256 + full text +
  ISO timestamp) into `~/.loop-gate/reviewed/<sha256-of-abspath>.json`; `check <file>` compares
  current bytes' hash against the last snapshot; `commit <file...> -- <msg>` re-checks **every**
  listed file within a single invocation (closing the TOCTOU window separate `check` calls
  would leave open) and only then runs `git add`+`git commit`, all-or-nothing. This is exactly
  the "content-hash freshness + all-or-nothing" pattern §4 recommends generalizing from
  "reviewed file bytes" to "cited evidence file bytes."

- **`<HOME>/Claude/loop/loop-team/harness/research_authenticity_check.py`** (read
  in full). A deterministic, mode-aware scanner that flags placeholder/degenerate Researcher
  output (`claim="test"`, identical values duplicated across distinct fields, suspiciously
  short fields, a `source` field with no real URL) — schema-agnostic markdown block parsing
  (`## <id>` headers, `- field: value` lines). Its own docstring states its own limit
  precisely: it catches **form**-level fabrication (a schema-valid but substantively empty
  field), not semantic truth. This is the same class of "necessary, not sufficient" check the
  recommended closure-proof validator needs, and its field-line parsing convention is the
  direct template used for the proof-block schema in §4.

- **`<HOME>/Claude/loop/loop-team/harness/verify.py`** (read the header/core).
  This repo's actual local, no-cloud-CI equivalent of a required check: auto-detects
  pytest/unittest/vitest/jest, and — notably — has an explicit false-green guard,
  `_zero_tests()`, that treats "0 tests collected" (exit 5, or "Ran 0 tests", or "no tests ran")
  as a **failure**, not a pass, because a suite that silently collects nothing would otherwise
  report a clean, meaningless green. Direct local precedent for "a green result is not proof
  unless you also prove the check actually ran against real content" — the same principle
  §4 applies to fix_plan.md closure claims (a Proof block is not proof unless proof exists
  that the referenced command/hash was actually produced by execution, not typed by hand).

- **`<HOME>/Claude/loop/loop-team/harness/dashboard.py`** (read the header).
  Worth flagging as a related, currently-unaddressed surface: it extracts each run's "final
  status (pass/fail/done/unknown)" by **parsing narrative text** out of `run_log.md`/
  `summary.md` files — i.e. the dashboard itself currently trusts the same kind of
  self-reported status string this whole dossier is about, one level up from `fix_plan.md`.
  Not in scope to fix here, but the recommended architecture (§4/§6) should be designed so its
  machine-checkable evidence could later feed a dashboard-trustworthy status field instead of
  a parsed adjective.

- **`<HOME>/Claude/loop/loop-team/orchestrator.md`** (targeted read, lines
  180–450, located via `rg` on "Review-to-commit|commit_diff_reread|Failure Arbiter|checkpoint
  commit"). Confirms:
  - The **micro-step checkpoint discipline**: "green → git checkpoint commit immediately" —
    every gate's "last checkpoint" is HEAD, evidence is a real commit, not a claim.
  - The **Failure Arbiter's 6 classes** (code-bug / test-bug / spec-gap / harness-fault /
    silent-throttle / degenerate-output) — a taxonomy for classifying a red (or suspiciously
    clean) result BEFORE re-dispatching anyone; directly informs §7's failure-mode analysis
    (a proof-validation gate itself needs the same "rule out our own measurement first"
    discipline).
  - The **Review-to-commit re-diff gate** section (lines 414–449) — the exact prose already
    quoted above from `learnings.md`, plus the tool's own honest self-classification: "This is
    presently an **instructional, not structural**, guarantee — you must remember to call
    `record`/use `commit`; nothing currently blocks a raw `git commit`." This repo already
    names its own residual gap in writing; §7 inherits it explicitly rather than re-discovering it.
  - The **Research checkpoint** and **Lessons checkpoint** (step 7) — mandatory persistence-
    and-linkage requirements that this very dossier is complying with.

- **`<HOME>/Claude/loop/loop-team/DESIGN_CHECKLIST.md`** (read in full, 221
  lines). The "ten gates" design-time adversarial checklist. Two gates are directly load-
  bearing for this dossier's recommendation: **Gate 2, "Provenance over value"** — "Every
  field that gets presented or stored must trace to a source that supports the claim attached
  to it. A value derived from a coarser proxy... is downgraded or withheld, never presented at
  full confidence" — this is precisely the principle a Proof block enforces for closure claims.
  **Gate 3, "Propose ≠ verify"** — "The component that produces a result may not certify it.
  An independent stage must re-derive the result against reality... before acceptance" — this
  is why §7 states plainly that no mechanical proof-block scheme substitutes for an
  independent Verifier; it only raises the floor under self-report. Gate 9 (added
  2026-07-08, `H-AC-ORACLE-TARGET-1`) is the mutation-check precedent already cited above.

- **`research/claim-ledger-goal-drift-mechanism-spec-2026-07-07.md`** (read in full). The
  fullest existing local treatment of "keep a claim honest across a session," already
  critiqued and explicitly not recommended as specced. Load-bearing findings reused in §3/§9:
  - **arXiv:2606.09863** ("From Confident Closing to Silent Failure," June 2026) — tested
    giving a judge model a concrete completion checklist across 9,876 tau2-bench and 1,879
    AppWorld trajectories; checklist condition barely moved detection accuracy (AUROC ~0.576)
    and **actively degraded** detection for Claude Sonnet on AppWorld (0.368 → 0.274); base
    rate 45–78% of "success" self-reports in these benchmarks were false. Direct evidence that
    a free-text LLM judge re-reading a checklist against a transcript is not a reliable
    completion gate on its own.
  - A real abandonment precedent: `johnnylugm-tech/harness-methodology` built a CI gate
    blocking pushes unless every checklist item was checked, and removed it, quoted directly:
    "only verified checkbox state (`- [x]`)... trivially bypassed by checking boxes without
    doing the work."
  - `anthropics/claude-code#55754` (+3 duplicates: #3573, #10205, #20221) — a Stop hook that
    blocks whenever it judges a task incomplete looped ~50 minutes when the agent was
    legitimately waiting on async background subagents; Anthropic's fix was
    `CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` (default caps re-blocking at 8 in a row), not removing
    the mechanism — direct evidence any new Stop-hook-based gate in this dossier must inherit
    a bounded retry/fail-open cap, never an unconditional block.
  - The critique's own cheaper alternative (not yet built) — seed literal claims into
    `fix_plan.md`'s Open section, require a Verifier check them before PASS — is a
    structurally different problem (goal-drift across an in-flight session) from THIS
    dossier's problem (mechanical proof at the moment of closure), and is explicitly not
    re-litigated here per its own "not to be re-litigated without new evidence" instruction.

- **`research/h-subagent-masking-1-full-closure-design-2026-07-03.md`** (read in full, 389
  lines). Its "Recommendation" and "Prior art" sections (read directly, not summarized): the
  chosen design (Candidate 3, minimal-diff, report-first-by-file-order) is grounded in a real,
  fetched source — Django's form-validation `run_validators()`/`Form.clean()` machinery,
  quoted directly from `https://docs.djangoproject.com/en/6.0/ref/forms/validation/`: "the
  cleaning methods for all remaining fields are still executed" even after one field's
  validator raises — a genuine, widely-deployed "run every check, aggregate, decide once"
  pattern. Its own Transfer-condition check states this guarantee is **structural, not
  instructional** once ported: "there is no way for a gate to 'forget' to report short of a
  bug in that gate's own code." Directly informs §4's preference for structural (code-path)
  guarantees over prose-remembered ones wherever the execution context allows it.

- **`research/subagent-commit-violation-signaling-2026-07-03.md`** (read the "Bottom line"
  and Finding 1 sections, 568 lines total). This is the **flag-file bridge** design that
  became `H-SUBAGENT-COMMIT-GATE-1`: `SubagentStop`'s own hook payload officially documents
  `session_id`/`agent_id`/`transcript_content`; a sub-agent's own `git commit` violation is
  detected from ITS OWN transcript and written as a small JSON flag file
  (`{session_id}_{agent_id}.commit_violation`), which Oga's own (visibility-having) `Stop`
  hook then globs for and blocks on. Explicitly ranked ABOVE a competing design (direct
  transcript-scan of `<session>/subagents/agent-<id>.jsonl`) specifically because that
  directory layout is **undocumented** ("not documented anywhere in the official Claude Code
  hooks or Agent SDK reference docs... nothing prevents Anthropic from changing this layout in
  a future release without a deprecation notice") versus the flag-file bridge, which depends
  "SOLELY on officially-documented, version-stable fields." This is the concrete local
  precedent for §4's principle: prefer officially-documented hook-payload fields over inferred
  internal file layouts when building a structural gate.

- **`research/coder-detection-structural-signal-subagentstop-2026-07-08.md`** (read section
  3 and 4 directly, 981 lines total). Contains a **load-bearing correction** this dossier
  reuses directly: a prior local citation of TDD Guard (`nizos/tdd-guard`) as "structural,
  file-path-glob, never content" detection is a mischaracterization — confirmed by reading
  the actual TDD Guard source (`src/validation/validator.ts`, quoted verbatim): the real
  violation-detection mechanism is **an LLM call** (`await modelClient.ask(prompt)` →
  `parseModelResponse`), with the path-glob only deciding *whether to invoke it*. Also cites
  **arXiv:2606.04990** ("From Agent Traces to Trust: A Survey of Evidence Tracing and
  Execution Provenance in LLM Agents"), independently re-fetched and re-confirmed by me
  directly this run (§2), which frames "execution provenance as the typed graph of an agent
  execution" — the general academic framing for exactly what §4's Proof-block/snapshot design
  implements narrowly and locally.

- **`research/loop-stop-guard-misfire-dossier-2026-07-08.md`** and **`research/workflow-
  subdispatch-isolation-design-2026-07-03.md`** — grepped for "structural signal"/"H-LT6"/
  "agent_id". Confirms the `H-LT6` precedent quoted directly: "the eventual resolution for a
  similarly-shaped 'can't tell who really dispatched this' problem in this same hooks/
  directory *was* to find and use a real structural signal, once one was confirmed to exist in
  the runtime payload" — same throughline as the flag-file bridge above; not read in full
  (out of direct scope for this dossier, correctly bounded per the researcher persistence rule
  against unnecessary breadth), but the specific section located and quoted is genuine, not
  inferred.

- **`research/SOURCES_INDEX.md`** and **`research/radar.md`** — grepped for
  `slsa|in-toto|provenance|attestation|evidence.ledger|proof.carrying`: **zero hits**. This
  confirms no prior local research exists on the supply-chain-provenance literature (SLSA,
  in-toto, attestation frameworks) — the external research in §2 is genuinely new ground for
  this repo, not a duplicate of existing work.

- **`ls research/`** — 56 files confirmed present; the ones not individually opened above
  (padsplit/Airbnb-domain files, compiler-feedback-loop files, career-search files) were
  scanned by filename/date and judged out of scope for this dossier's topic (rental/domain
  research, compiler-gate design for a different project) — not silently skipped, explicitly
  excluded as irrelevant to false-status/closure verification after checking their titles
  against the grep term set above (none matched).

**Local files count for AC1: 18 distinct local files actually opened/inspected** (well above
the ≥8 minimum): researcher.md, search_playbook.md, learnings.md, fixplan_closure_lint.py,
test_fixplan_closure_lint.py, fix_plan.md (7 distinct sections), commit_diff_reread.py,
research_authenticity_check.py, verify.py, dashboard.py, orchestrator.md, DESIGN_CHECKLIST.md,
claim-ledger-goal-drift-mechanism-spec-2026-07-07.md, h-subagent-masking-1-full-closure-
design-2026-07-03.md, subagent-commit-violation-signaling-2026-07-03.md, coder-detection-
structural-signal-subagentstop-2026-07-08.md, loop-stop-guard-misfire-dossier-2026-07-08.md
(targeted), workflow-subdispatch-isolation-design-2026-07-03.md (targeted grep), plus
SOURCES_INDEX.md/radar.md (grepped for gap-confirmation).

---

## 2. External sources and GitHub repos inspected (real, opened, quoted)

`which gh` confirmed `/opt/homebrew/bin/gh`, authenticated as `Eobodoechine` — used for every
GitHub repo below (`gh repo view` for metadata, `gh api .../contents/...` for real file bytes),
per the dispatch's explicit preference for `gh` over WebFetch where available.

1. **SLSA v1.0 Provenance spec** — `https://slsa.dev/spec/v1.0/provenance` (WebFetch, fetched
   directly). Schema: `buildDefinition` (`buildType`, `externalParameters`,
   `resolvedDependencies`) + `runDetails` (`builder.id`, `metadata.invocationId/startedOn/
   finishedOn`). Quoted: `builder.id` is "the sole determiner of the SLSA Build level" — i.e.
   trust is anchored to WHO/WHAT generated the evidence, not to the claim's own text. This is
   the core idea §4 borrows: evidence must be **producer-anchored** (generated by a specific,
   trusted mechanism), not self-declared.

2. **in-toto Attestation Framework** — `https://github.com/in-toto/attestation` (WebFetch,
   fetched directly). The Statement/Predicate model: `subject` (identifies the specific
   artifact), `predicateType` (category of claim), `predicate` (the actual evidence). Quoted:
   this "binding \[of\] verifiable evidence directly to identified artifacts" is what makes a
   claim "proof-carrying." Direct model for §4's Proof-block schema (a claim bound to specific
   files/hashes, not a bare assertion).

3. **`nizos/tdd-guard`** (github.com/nizos/tdd-guard) — verified directly via `gh repo view`:
   MIT license, 2,248 stars, last push 2026-07-06 (2 days before this dispatch — actively
   maintained). Confirms the metadata already captured in the internal research file cited
   above (source-code quote of `src/validation/validator.ts` reused from that prior, already-
   verified fetch — re-confirmed here independently via `gh repo view` metadata rather than
   re-fetching the identical source bytes a second time). Real, shipped proof that a
   Claude-Code-hook-based enforcement tool with 2,200+ stars uses an LLM-judged validator as
   its CORE mechanism (not a replacement for structural checks — a narrow, deterministic
   "exactly one test added" fast-path skips the LLM call for the easy case), directly relevant
   to §3/§6's ranking of an LLM-judge layer as secondary-only.

4. **`changesets/changesets`** (github.com/changesets/changesets) — `gh api
   repos/changesets/changesets/contents/.changeset/README.md`, real file fetched, 12,091 stars,
   MIT, pushed 2026-07-08 (today). This is a real, widely-deployed "required proof block"
   pattern: a package cannot be versioned/released without a `.changeset/*.md` file (a small,
   structured markdown file with YAML frontmatter naming which packages bump and how)
   physically present in the PR diff.

5. **`changesets/action`** (github.com/changesets/action) — `gh api
   repos/changesets/action/contents/action.yml`, real file fetched, 1,042 stars. Quoted output
   field: `has-changesets: A boolean about whether there were changesets` — the CI action's
   own structural output is "does a machine-readable proof artifact exist," not "does the PR
   description claim a change was made." Direct real-world precedent for a required,
   structurally-checked proof artifact gating a status transition (unreleased → released).

6. **`ossf/scorecard`** (github.com/ossf/scorecard) — `gh api
   repos/ossf/scorecard/contents/checks/evaluation/signed_releases.go`, real Go source fetched
   (100 lines read), 5,572 stars, Apache-2.0, pushed 2026-07-06. The `SignedReleases` check
   computes its score from `findings` produced by real **probes** (`releasesAreSigned`,
   `releasesHaveProvenance`, `releasesHaveVerifiedProvenance`) that query the actual GitHub
   Releases API and actual provenance-attestation presence — never from a project's
   self-reported "we sign our releases" claim. Direct precedent for an **evidence-backed
   status ledger**: a score/status is only as good as the underlying, independently-queried
   evidence it's computed from.

7. **Sigstore `cosign` attestation docs** — `https://docs.sigstore.dev/cosign/verifying/
   attestation/` (WebFetch, fetched directly). `cosign attest --predicate <file> ... <image>`
   binds a predicate (test results, SBOM, etc.) to a specific artifact **digest** via a
   DSSE-signed in-toto Statement; `cosign verify-attestation` checks it later, optionally
   against CUE/Rego policy. Quoted: "Signatures can guarantee a file has not been tampered
   with, but they can't guarantee the file arrives at all" — i.e. even cryptographic
   attestation only proves non-tampering of a specific artifact, not that the RIGHT thing was
   attested to. Relevant to §7's residual-risk framing.

8. **GitHub branch-protection / required status checks docs** —
   `https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/
   managing-protected-branches/about-protected-branches` (WebFetch, fetched directly). Quoted
   directly: "Required status checks must have a `successful`, `skipped`, or `neutral` status
   before collaborators can make changes to a protected branch," and the strict/loose
   distinction — "Require branches to be up to date before merging" (strict) vs. loose, where
   "status checks may fail after you merge your branch if there are incompatible changes." This
   is the exact real-world precedent for §4's **freshness/staleness** requirement: a passing
   check computed against an OLD state of the code is not proof about the CURRENT state.

9. **`pre-commit/pre-commit`** (github.com/pre-commit/pre-commit) — `gh repo view`, 15,409
   stars, MIT, pushed 2026-06-17. The dominant real-world local-hook-framework precedent for
   "a git hook that runs a deterministic check before a commit lands" — this repo's own house
   style (stdlib-only, no PyPI dependency, invoked directly by Oga/hooks) deliberately diverges
   from pre-commit's plugin-manifest model, but the underlying idea (a local, pre-commit-time
   deterministic gate) is the same class of mechanism §4 recommends, already proven at scale
   elsewhere.

10. **`conventional-changelog/commitlint`** (github.com/conventional-changelog/commitlint) —
    `gh repo view`, 18,645 stars, MIT, pushed 2026-07-08 (today). Deliberately cited as a
    **contrast case**: commitlint enforces commit-message FORMAT (`type(scope): subject`) —
    it is, structurally, exactly the class of check `fixplan_closure_lint.py` already is
    (a wording/format lint), and it makes NO claim about whether the commit's content is
    truthful. Useful negative precedent for §9 ("do not build" a wording-only gate and call
    it proof).

11. **`actions/attest-build-provenance`** (github.com/actions/attest-build-provenance) — `gh
    api .../contents/action.yml`, real file fetched, 972 stars, MIT, pushed 2026-06-26. A
    real, GitHub-native implementation of SLSA provenance generation: its own inputs
    (`subject-path`/`subject-digest`/`subject-checksums`, `predicate-type`, `predicate`) show
    the SLSA Statement/Predicate model implemented as an actual, widely-used CI primitive, not
    just a paper spec.

12. **Bazel Build Event Protocol** — `https://bazel.build/remote/bep` (WebFetch, fetched
    directly). BEP is "a set of protocol buffer messages" forming "a directed acyclic graph"
    of build/test events (`BuildStarted` → command-produced test results → `BuildFinished`).
    Honestly reported gap: the fetched documentation page does **not** describe content-
    addressing/hashing or independent verification of a specific test's execution — it is a
    machine-readable EVENT LOG, not a cryptographic proof mechanism. Recorded as a partial,
    not overstated, source (per the honesty bar).

13. **`danger/danger`** (github.com/danger/danger) — `gh api repos/danger/danger/contents/
    README.md`, real file fetched, 5,684 stars, MIT, pushed 2026-06-22. Quoted directly: "You
    can: Enforce CHANGELOGs... Look out for common anti-patterns... Give specific files extra
    focus" — a real, shipped example of a PR-time gate that checks the actual DIFF CONTENT
    against a claimed change (did this diff actually touch the CHANGELOG it claims to have
    updated), rather than trusting a description. Direct precedent for §4's requirement that a
    closure claim's Proof block reference files that are ACTUALLY part of the diff, not merely
    named in prose.

14. **arXiv:2606.04990** — "From Agent Traces to Trust: A Survey of Evidence Tracing and
    Execution Provenance in LLM Agents" (WebFetch, abstract fetched directly, independently
    re-confirmed this run rather than only trusting the internal research file's earlier
    fetch). Quoted: "Final-answer accuracy alone cannot explain how an output was produced,
    which evidence supported each claim, whether tool calls were justified... or where
    failures originated." Frames "execution provenance as the typed graph of an agent
    execution" — the academic umbrella term for what this dossier implements narrowly.

**External source count for AC2: 14 sources, of which 8 are real GitHub repositories actually
opened via `gh` (source files or repo metadata fetched directly)** — well above the ≥10
sources / ≥5 repos minimum: SLSA spec, in-toto framework, TDD Guard, changesets, changesets/
action, OpenSSF Scorecard, cosign docs, GitHub branch-protection docs, pre-commit, commitlint,
attest-build-provenance, Bazel BEP, Danger, arXiv:2606.04990.

---

## 3. Candidate mechanisms — ranked and scored

Scoring: **Mech** = mechanical strength (1–5, does it structurally prevent the false claim vs.
merely make it harder), **Complex** = implementation complexity (1–5, 5 = heaviest),
**FP-risk** = false-positive risk (1–5, 5 = highest risk of blocking a legitimate closure),
**Fit** = fit for THIS repo's scale/style (1–5), **Local** = can it run fully locally with no
cloud CI (1–5, 5 = trivially local).

| # | Mechanism | Mech | Complex | FP-risk | Fit | Local | Grounded in |
|---|---|---|---|---|---|---|---|
| 1 | **Required Proof block** (inline, per-CLOSED-heading, fixed schema: command/exit_code/output_hash/files/verified_at) | 3 | 2 | 2 | 5 | 5 | commit_diff_reread.py's snapshot idea; research_authenticity_check.py's field-line parser; changesets' "required file present" pattern; in-toto Statement model |
| 2 | **Producer-anchored evidence snapshot** (`run_and_record.py` executes the command itself and writes the snapshot; the Proof block must reference a REAL snapshot file, not hand-typed text) | 5 | 3 | 2 | 5 | 5 | SLSA's builder-anchored provenance ("builder.id is the sole determiner"); commit_diff_reread.py's record/check pattern generalized |
| 3 | **Closure-lint upgraded to cross-check snapshots + re-hash cited files (STALE detection)** | 4 | 2 | 2 | 5 | 5 | GitHub's strict-mode "up to date before merging"; commit_diff_reread.py's sha256-check-before-commit |
| 4 | **Dirty-worktree gate on cited evidence files** (`git status --porcelain -- <files>` must be clean before a CLOSED heading is accepted) | 4 | 1 | 2 | 5 | 5 | this repo's own leading-space `.strip()` porcelain-parsing lesson (learnings.md 2026-07-02); Danger's diff-content gating |
| 5 | **Stop-hook wiring** (block Oga's own Stop turn if it just introduced/edited a CLOSED heading with no valid Proof block, fail-open on internal error, bounded retry) | 4 | 3 | 3 | 4 | 5 | loop_stop_guard.py's existing gate architecture; anthropics/claude-code#55754's block-cap precedent |
| 6 | **SubagentStop flag-file bridge for sub-agent-authored closures** (a Coder/Verifier that appends a CLOSED heading inside its own dispatch is caught the same way H-SUBAGENT-COMMIT-GATE-1 catches a raw sub-agent `git commit`) | 4 | 4 | 2 | 4 | 5 | H-SUBAGENT-COMMIT-GATE-1's proven flag-file-bridge design; officially-documented SubagentStop payload fields |
| 7 | **Configured-vs-fired self-test** (a session-start smoke test that runs the lint against a synthetic known-bad AND known-good fixture in one invocation, writing a heartbeat log entry) | 3 | 2 | 1 | 5 | 5 | H-CODEX-PARITY hook-trust-hash regression (silent exclusion, no visible error); learnings.md's sabotage-smoke-test technique |
| 8 | **Full cryptographic DSSE/SLSA attestation chain with signing keys** | 5 | 5 | 2 | 1 | 3 | SLSA/in-toto/cosign spec |
| 9 | **LLM-judged semantic consistency check** (does the claimed command plausibly support the claimed fix) as a SECONDARY, non-blocking layer | 2 | 3 | 4 | 2 | 5 | TDD Guard's real architecture (LLM as core, but gated behind structural pre-filter); arXiv:2606.09863 (checklist-judges barely help, sometimes hurt) |
| 10 | **Fully-specced Claim Ledger** (session-wide claim tracking, new Stop-hook gate, new `claims.md` artifact) | — | — | — | — | — | already researched, already NOT recommended (H-CLAIM-LEDGER-1) — not re-scored, listed only to show it was considered and explicitly excluded, not overlooked |

**Reading the table:** #1+#2+#3+#4 together are the mechanical core of the recommendation
(§4) — each individually cheap, individually well-grounded in an existing local pattern, and
together they close the wording-lint gap without introducing a new heavy artifact class. #5
and #6 make the gate structurally enforced rather than remembered. #7 closes the specific,
already-proven-real "configured but not firing" failure mode. #8 and #9 are explicitly scored
low on fit/complexity and are the primary contents of §9 ("do not build" — at least not now).
#10 is not re-litigated, per that entry's own written instruction not to without new evidence.

---

## 4. Recommended architecture

**Principle, stated once and applied everywhere below:** a closure claim (any `## ` heading in
`fix_plan.md` — or, by the same pattern, a loop-team run-log's final verdict — that contains
the literal token `CLOSED`, or body text matching `fixplan_closure_lint.py`'s existing
closure-shaped-phrase set) is not valid evidence of anything **unless it is immediately
followed by a Proof block that (a) names the exact command run, (b) references a
producer-anchored snapshot of that command's real output — not hand-typed text, (c) names the
exact files the claim depends on, with their content hashes at verification time, and (d) is
re-checkable at any later moment for freshness (do the cited files still hash the same?) and
for worktree cleanliness (were they actually committed, not just sitting dirty on disk?).**

### 4.1 The Proof block (inline, next to `fix_plan.md`'s own CLOSED heading — not a separate
hand-maintained ledger file)

Every CLOSED heading's body must contain, within its first ~15 lines, a fixed-shape block
using the exact `- field: value` convention `research_authenticity_check.py` already parses
elsewhere in this repo (schema-agnostic, human-diffable, no new file format to learn):

```
## H-EXAMPLE-1 — some real fix -- CLOSED (2026-07-08, commit `abcdef1`)
Proof:
- command: python3 -m pytest hooks/test_example.py -q
- exit_code: 0
- proof_snapshot: ~/.loop-gate/proof/3f9a1c2b4d5e.json
- files: hooks/example.py, hooks/test_example.py
- verified_at: 2026-07-08T21:14:03Z
```

Why inline rather than a separate `evidence_ledger.jsonl` the dispatch's target-design-space
explicitly lists: this repo has already been burned TWICE by two sources of truth silently
diverging (the heading-vs-body mismatch that motivated the original lint; `hooks.json`
content vs. `config.toml`'s stale `trusted_hash`). A hand-maintained second ledger file
creates exactly that risk — an entry could be added to `fix_plan.md` and never mirrored into
the ledger, or vice versa. **If a separate `evidence_ledger.jsonl` is wanted for querying/
dashboarding (§6), it must be MACHINE-DERIVED from the inline Proof blocks by a script, never
hand-authored as a second source.** This directly answers the dispatch's "Evidence ledger next
to fix_plan.md" item: the ledger effectively lives INSIDE fix_plan.md, adjacent to each claim,
which is stronger than "next to" in the sense that it cannot drift out of sync with the claim
it backs.

### 4.2 Producer-anchored snapshots (`run_and_record.py`) — the SLSA "builder.id" principle,
translated to this repo's scale

New harness script, matching `commit_diff_reread.py`'s exact conventions (stdlib-only,
`~/.loop-gate`/`LOOP_GATE_DIR` env-var + TTL-sweep, `json.dumps` to stdout):

```
python3 loop-team/harness/run_and_record.py -- <command...>
```

Executes the command as a real subprocess, captures stdout+stderr+exit_code, computes
`sha256(stdout + stderr)`, records `{command, exit_code, output_sha256, files: {path: sha256,
...} (auto-hashed: any file path appearing in the command's own argv), captured_at,
dirty_at_capture: <bool, from git status --porcelain on the same files>}` to
`~/.loop-gate/proof/<key>.json` (key = sha256 of the full JSON, matching
`commit_diff_reread.py`'s hash-of-content addressing style), and prints a ready-to-paste Proof
block. **This is the SLSA insight applied locally: the snapshot's trustworthiness comes from
being WRITTEN BY THE SCRIPT'S OWN EXECUTION, not from being typed by whichever agent is
closing the entry.** A hand-typed `exit_code: 0` in a Proof block with no matching snapshot
file is exactly what §4.3's lint upgrade must catch.

### 4.3 Closure-lint upgraded from wording lint to proof validation

Extend `fixplan_closure_lint.py` (same file, same style, additive — do not rewrite its
existing, already-tested heading/body phrase-consistency check, which stays valid and useful):

1. **Existing check, unchanged:** heading/body closure-phrase consistency (today's behavior).
2. **NEW — proof-block-required:** any heading containing `CLOSED` must have a parseable Proof
   block (reuse `research_authenticity_check.py`'s `- field: value` parser verbatim — same
   module, imported, not reimplemented). Missing block ⇒ flag, same style as today's mismatch
   flags.
3. **NEW — snapshot cross-check (the actual "wording lint → proof validation" upgrade):** for
   each Proof block, resolve `proof_snapshot` and confirm (a) the file exists, (b) its stored
   `output_sha256`/`command` match what the Proof block claims. **A Proof block whose
   `proof_snapshot` path does not exist, or whose content doesn't match, is flagged as
   "no matching proof snapshot found (possible fabricated evidence)"** — this is the single
   line that turns the tool from checking TEXT SHAPE to checking EVIDENCE EXISTENCE.
4. **NEW — freshness/staleness:** for each file listed in `files`, re-hash it NOW and compare
   to the hash recorded in the referenced snapshot at `verified_at` time. Mismatch ⇒ flag
   `STALE: <file> changed since <verified_at>` (see §4.5 — never silently un-close; always an
   additive, visible flag).
5. **NEW — dirty-worktree check:** `git status --porcelain -- <files>` (using the exact
   non-stripped porcelain-line handling this repo already learned the hard way — see
   learnings.md 2026-07-02, "leading-space signal is destroyed by `.strip()`") on every file
   the Proof block cites, plus `fix_plan.md` itself. Any uncommitted change ⇒ flag
   "evidence file has uncommitted changes."

Exit codes/output format unchanged (0/1/2, plain text) — this keeps it a drop-in replacement,
same CLI contract, same test-harness convention (`test_fixplan_closure_lint.py`'s existing
subprocess-invocation tests keep passing unmodified; new tests are additive).

### 4.4 Wiring into the existing Stop-hook architecture (structural, not remembered)

Reuse `loop_stop_guard.py`'s existing gate pattern exactly (fail-open on internal error,
bounded, same file): detect (via the same turn-diff/file-scope idiom `commit_scope_scan.py`
already uses for `H-REVIEW-COMMIT-1`) that THIS turn introduced or modified a `CLOSED` heading
in `fix_plan.md`; if so, run the upgraded lint (§4.3) against the current file; on FAIL, block
the Stop (`sys.exit(2)`) with the lint's own flagged-mismatch text surfaced verbatim in stderr
(matching `H-GUARD-8`'s already-adopted principle: always surface the real matched evidence,
never a generic message). This makes the guarantee **structural for Oga's own turns** — no
more "you must remember to run the lint" — while inheriting this repo's own honest, existing
caveat for the raw-`git commit`-outside-the-hook case (§7).

For a **sub-agent** (Coder/Verifier/Test-writer) that appends a CLOSED heading inside its own
dispatch: extend `subagent_stop_gate.py`'s existing 4th responsibility (the
`H-SUBAGENT-COMMIT-GATE-1` flag-file bridge) with a 5th — the SAME snapshot-cross-check logic,
called against the sub-agent's own transcript content, writing
`{session_id}_{agent_id}.closure_proof_violation` on a hit, which `loop_stop_guard.py`'s own
`Stop` glob already knows how to check (same TTL-glob pattern already proven for
`.commit_violation`). This closes the identical class of blind spot H-SUBAGENT-COMMIT-GATE-1
was built to close, for closure claims specifically instead of raw commits.

### 4.5 Auto-downgrade stale claims, without ever silently un-closing anything

A periodic sweep (`loop-team/harness/closure_freshness_sweep.py`, invoked from
`session_start.sh` or manually) re-runs §4.3's freshness check (step 4) against **every**
existing `CLOSED` heading in `fix_plan.md`, not just ones touched this turn. On a stale hit, it
**appends** a new heading — never edits the original in place — following the exact,
already-adopted local convention: "closing a fix_plan.md entry means APPENDING a new
`-- CLOSED` heading... not editing an open entry's title in place" (learnings.md, 2026-07-03),
generalized here to append a `-- STALE (auto-flagged <date>, <file> changed since
<verified_at>)` follow-up instead. This mirrors GitHub's strict-mode "up to date before
merging" idea (§2 item 8): a passing check computed against an old state is not proof about the
current state, and the fix is to re-check freshness, not to trust the original timestamp
forever.

### 4.6 "Configured vs fired" — the H-CODEX-PARITY lesson, applied to this new gate itself

Any new gate is itself subject to the exact failure this repo already suffered once (a hook
whose config looks right but silently doesn't fire). Mitigation, cheap and concrete: a
session-start self-test (`fixplan_closure_lint.py --selftest`, or a small wrapper) runs the
upgraded lint against ONE synthetic known-bad fixture (a CLOSED heading with a fabricated,
non-existent `proof_snapshot`) and ONE synthetic known-good fixture (a real, freshly-generated
snapshot) in the same invocation, asserts the bad one is flagged and the good one is not, and
appends a heartbeat line to `~/.loop-gate/closure_lint_selftest.log`. **The self-test's own
absence is therefore itself detectable** (an empty/stale heartbeat log is a visible signal,
addressing the recursive "what if the self-test itself doesn't fire" risk named in §7).

### 4.7 Dirty-worktree and stale-evidence handling, restated as first-class requirements

Both are already built into §4.3 (steps 4 and 5) rather than bolted on separately — this is
deliberate: staleness and dirtiness are two instances of the same underlying question
("does the cited evidence still describe the current, durable state of the code?"), and
building them as two branches of one check (re-hash + re-check-worktree) is cheaper and less
error-prone than two independent mechanisms that could drift out of sync with each other.

---

## 5. Minimal viable implementation plan

Scoped to land in roughly the same effort class as this repo's own recent gate builds
(`H-REVIEW-COMMIT-1`, `H-SUBAGENT-COMMIT-GATE-1` — each a spec + plan-check + Coder +
Test-writer + independent Verifier cycle, ~1 session each):

1. **Spec** (per this repo's own "Plan before execution" standing rule — no code before a
   plan-check round, no exceptions) covering exactly §4.1–§4.3 (the inline Proof block schema,
   `run_and_record.py`, and the upgraded lint) — the MVP deliberately EXCLUDES the Stop-hook
   wiring (§4.4) and the freshness sweep (§4.5) as a first slice, so the new checking logic can
   be exercised manually before it becomes load-bearing/blocking.
2. **`run_and_record.py`** (~100–150 lines, follows `commit_diff_reread.py`'s exact structure:
   `_gate_dir()`, `_sweep_stale()`, hash-keyed snapshot files, `json.dumps` stdout, documented
   exit codes).
3. **`fixplan_closure_lint.py` v2** (additive to the existing ~240-line file; §4.3 steps 2–3
   only for MVP — proof-block-required + snapshot-cross-check; defer freshness/dirty-worktree
   to the "stronger" tier, §6, since they require re-hashing arbitrary cited files rather than
   just the one target file this tool already knows how to open).
4. **Test-writer** builds real subprocess-invoked tests matching `test_fixplan_closure_lint.py`'s
   existing convention (fixture files on `tmp_path`, assert on stdout/exit code), PLUS one
   sabotage-smoke-test (§8, item 8) proving the new checks have teeth, built independently from
   the spec's ACs per this repo's existing Test-writer discipline (never shown the
   implementation first).
5. **Plan-check** the spec (mandatory per this repo's own standing practice, not optional even
   for "simple" deterministic logic — `learnings.md`'s 2026-06-24 entry: "the plan-check
   Verifier step is not optional even for 'simple' logic... a spec Verifier evaluating the
   logic against \[real\] fixtures... is the only reliable catch").
6. **Independent post-build Verifier**, de-primed per this repo's existing convention (spec +
   artifact + real input corpus, forms its own provisional verdict before reconciling against
   any green-suite claim).
7. **No wiring into `loop_stop_guard.py` yet** — the MVP is deliberately opt-in/manual
   (`python3 loop-team/harness/fixplan_closure_lint.py` run explicitly at session close,
   exactly how the original v1 lint is used today per its own docstring: "Run it as a standing
   step (a) at the end of any Oga session that closed a build"). This bounds the MVP's blast
   radius (no risk of a new false-positive blocking a real Stop turn) while still closing the
   core "wording lint → proof validation" gap the dispatch asked for.

Estimated total: 2 Coder micro-steps (run_and_record.py; lint v2) + 1 Test-writer pass + 1–2
plan-check rounds + 1 post-build Verifier pass — comparable in size to `H-GUARD-8`
(the smallest recent closure-adjacent build in this repo) plus roughly half of
`H-REVIEW-COMMIT-1`'s scope.

---

## 6. Stronger long-term implementation plan

Once the MVP (§5) has run manually for a real closure or two and is trusted:

1. **Stop-hook wiring** (§4.4) — block Oga's own Stop turn on a fresh, proof-invalid CLOSED
   heading. Bounded retry / fail-open on internal error, matching every other gate in
   `loop_stop_guard.py` (never an unconditional block, per the `claude-code#55754` precedent).
2. **SubagentStop flag-file bridge extension** (§4.4, 5th responsibility) — closes the sub-
   agent-authored-closure blind spot, mirroring `H-SUBAGENT-COMMIT-GATE-1` exactly.
3. **`closure_freshness_sweep.py`** (§4.5) — periodic re-hash of every existing CLOSED entry's
   cited files, append-only STALE flagging, run from `session_start.sh` (cheap: hashing is
   fast; this must NOT re-EXECUTE every cited command on every session start — see §9 for why
   that specific escalation is explicitly rejected).
4. **Session-start self-test** (§4.6) — the configured-vs-fired heartbeat check.
5. **Mutation-test the closure-lint itself, periodically** — directly reusing the
   `H-AC-ORACLE-TARGET-1` pattern already adopted in this repo (`DESIGN_CHECKLIST.md` gate 9):
   weaken/remove the snapshot-cross-check in a SCRATCH copy of the lint, confirm a known-good
   fixture that should now silently pass a fabricated Proof block actually does (proving the
   check WOULD have caught the regression), then confirm the real, unmodified lint still
   flags it. Freeze as a standing regression test, not a one-time manual check.
6. **Derived, queryable `evidence_ledger.jsonl`** — generated FROM the inline Proof blocks by
   a small script (never hand-authored — see §4.1's explicit reasoning against a second source
   of truth), feeding `dashboard.py` (§1's finding: it currently parses narrative status
   adjectives out of `run_log.md` text) a genuinely evidence-backed status field instead.
7. **Extend the Proof-block schema to a 5th "closure" genre** in
   `research_authenticity_check.py`'s existing per-mode field-vocabulary pattern (it already
   has 4 genres for Researcher output; a 5th genre for closure/verdict reports would let the
   SAME deterministic degenerate-output scanner (placeholder tokens, suspiciously-short
   fields, duplicate-value-across-fields) apply to Proof blocks too, for free, reusing tested
   code rather than writing a parallel scanner).
8. **Optional, explicitly secondary, LLM-judged semantic-consistency pass** (§3 candidate #9)
   — "does the claimed command plausibly relate to the claimed fix" — gated the way TDD Guard
   actually gates its own LLM call (only invoked on Proof blocks that pass the structural
   checks but look suspicious by some cheap heuristic, e.g. `echo`/`true`/no-op-shaped
   commands), NEVER load-bearing alone, and never a substitute for an independent Verifier
   dispatch (DESIGN_CHECKLIST gate 3, "Propose ≠ verify" — this whole mechanism still cannot
   let the same actor propose AND certify).

---

## 7. Failure modes the design still would not catch

Stated plainly, per this repo's own honesty-bar convention of naming residual gaps rather than
implying a design is complete:

1. **A real command that "passes" but doesn't actually test the claim.** `run_and_record.py`
   proves a command was executed and produced a specific output — it does NOT prove that
   command is the RIGHT test for the claim (`echo ok` genuinely hashes and snapshots cleanly).
   This is the exact residual `cosign`'s own docs name (§2 item 7: signatures prove
   non-tampering, not correctness) and exactly why DESIGN_CHECKLIST gate 3 ("Propose ≠ verify")
   remains necessary — an independent Verifier spot-checking that the cited command is
   substantively relevant is not eliminated by this design, only reduced in frequency of need.
2. **Out-of-band commits.** Exactly as `orchestrator.md` already documents for
   `H-REVIEW-COMMIT-1`: "nothing currently blocks a raw `git commit`" from outside the hooked
   session (a terminal window, a different tool). A CLOSED heading appended via a fully
   out-of-band edit is invisible to any Stop-hook-based gate. This is an inherited, not new,
   residual.
3. **Two concurrent sessions sharing one worktree** (standing documented risk, "one session per
   worktree"). `~/.loop-gate/proof/` is machine-wide, keyed by content hash, not
   session-namespaced (same design as `commit_diff_reread.py`'s existing snapshot dir) — a
   second session's `run_and_record.py` call for a semantically-different but textually
   similar command could theoretically collide on key derivation in rare cases; low risk given
   sha256 keying, but not formally proven collision-free, and inherits the exact concurrent-
   write hazard class this repo has hit multiple times (commits `96693f8`, `5884604`).
4. **The self-test's own recursive risk** (§4.6 partially mitigates, does not eliminate): if
   the session-start self-test is itself never invoked (e.g. `session_start.sh` silently fails
   to run, or the self-test call is removed by a future edit), the heartbeat log simply stops
   growing — detectable only by someone actually checking it. This is a strictly smaller
   version of the same "configured vs fired" problem this whole mechanism is meant to close,
   one layer up, and it is honestly disclosed rather than claimed solved.
5. **A sub-agent that runs the real command in a scratch/throwaway environment** (a temp
   clone, a different branch) whose result doesn't reflect what's about to be committed to
   `fix_plan.md`'s target repo — the snapshot's `files` hashes are recorded against WHATEVER
   path the command touched, and nothing in this design forces that path to be the actual
   target repo's working tree unless the Proof block's file paths are independently checked to
   resolve inside the target repo (a cheap additional check, not yet specced — flagged here as
   a gap for the eventual spec to close explicitly, not silently assumed handled).
6. **Semantic hallucination surviving structural checks entirely** — an agent could construct
   a Proof block whose command, when actually run via `run_and_record.py`, DOES produce a
   real, matching snapshot, but the underlying claim ("this fixes bug X") is simply wrong
   because the test itself doesn't cover the bug. No mechanical proof-block scheme closes this
   — it is the same "Propose ≠ verify" gap named in #1, restated: mechanical evidence answers
   "did something real happen," never "was the something real the RIGHT thing."

---

## 8. Concrete acceptance tests for the recommended design

All commands below are real, runnable, stdlib-only Python invocations following this repo's
existing test/CLI conventions (no piping through `tail`/`head` before capturing exit codes,
per the twice-hit local lesson).

```bash
# 1. Missing Proof block on a CLOSED heading -> flagged
python3 loop-team/harness/fixplan_closure_lint.py fixtures/missing_proof_block.md
# expect: exit 1; stdout contains "missing proof block" (or equivalent flag text)

# 2. Valid Proof block referencing a REAL, matching snapshot -> passes
python3 loop-team/harness/run_and_record.py -- echo hello
# expect: exit 0; stdout is JSON containing "output_sha256" and a real
# ~/.loop-gate/proof/<key>.json file now exists on disk (verify with `ls`)
python3 loop-team/harness/fixplan_closure_lint.py fixtures/valid_proof_block.md
# expect: exit 0; stdout "no mismatches found"

# 3. Fabricated Proof block (hand-typed hash, no matching snapshot file) -> flagged
python3 loop-team/harness/fixplan_closure_lint.py fixtures/fabricated_proof_block.md
# expect: exit 1; stdout contains "no matching proof snapshot found"

# 4. Stale evidence (file changed after verified_at) -> flagged
python3 loop-team/harness/run_and_record.py -- python3 -m pytest tests/test_x.py -q
#   ...then modify tests/test_x.py or the code it covers...
python3 loop-team/harness/fixplan_closure_lint.py fixtures/now_stale.md
# expect: exit 1; stdout contains "STALE"

# 5. Dirty-worktree evidence file -> flagged
#   (touch an uncommitted change in a file the Proof block cites)
python3 loop-team/harness/fixplan_closure_lint.py fixtures/dirty_evidence.md
# expect: exit 1; stdout contains "uncommitted changes"

# 6. Full existing + new test suite green
python3 -m pytest loop-team/harness/test_fixplan_closure_lint.py \
                   loop-team/harness/test_run_and_record.py -q
# expect: all tests pass, 0 failures (capture exit code directly: echo EXIT=$?
# immediately after, never through a pipe)

# 7. Sabotage-smoke-test (per this repo's own established technique,
#    learnings.md 2026-07-03): temporarily stub the snapshot-cross-check to
#    always return True, re-run test #3's fixture -> now WRONGLY exits 0
#    (proves the test has teeth: it correctly fails when the check is broken),
#    then restore the real check byte-for-byte and confirm:
git diff --stat loop-team/harness/fixplan_closure_lint.py
# expect: empty output (zero residual change) after the stub is reverted

# 8. Self-test / configured-vs-fired
python3 loop-team/harness/fixplan_closure_lint.py --selftest
# expect: exit 0 ONLY if a synthetic bad fixture is flagged AND a synthetic
# good fixture passes, both within this one invocation; a new line is
# appended to ~/.loop-gate/closure_lint_selftest.log (verify with `tail -1`)

# 9. Real-file regression (must never crash against the live repo file)
python3 loop-team/harness/fixplan_closure_lint.py
# expect: exit code in {0, 1} (never 2, never an uncaught traceback), matching
# the existing TestRealFixPlanDoesNotCrash convention

# 10. Mutation-check on the lint itself (H-AC-ORACLE-TARGET-1 pattern, §6 item 5)
#     in a scratch copy: remove the snapshot-cross-check block, re-run test #3's
#     fixture -> confirm it now WRONGLY passes (exit 0) before restoring, proving
#     the check is load-bearing and not vacuous
```

---

## 9. Do NOT build (ideas that sound good but are weak or too complex for this repo)

- **A full cryptographic DSSE/SLSA/in-toto signed attestation chain with a PKI and a
  verification key pair.** Massively over-scoped for a single-operator local repo with no
  external distribution and no multi-party trust boundary. Signing solves "prove a THIRD PARTY
  didn't tamper with this after it left a trusted producer" — this repo's actual threat model
  is "the SAME agent that would fabricate a claim could also sign it with its own key,"
  which cryptographic signing does not address at all. Revisit only if this repo ever gets
  external contributors whose commits need non-repudiation against each other.
- **The fully-specced Claim Ledger** (`H-CLAIM-LEDGER-1` as previously designed — new
  `claims.md` file, new bounded Stop-hook gate). Already researched and explicitly NOT
  recommended by 3 independent adversarial lenses that found real, code-cited holes (gameable
  escape hatches, a wrong-flag reuse, a "fail-open retry-cap" precedent that actually blocks,
  an arming heuristic that likely wouldn't have caught its own motivating incident). Do not
  re-litigate without new evidence, per that entry's own written verdict — and note this is a
  DIFFERENT problem (session-wide goal-drift tracking) from this dossier's (mechanical proof at
  closure time); solving this dossier's problem does not require reopening that one.
- **An unconditional, unbounded Stop-hook block-until-proof-valid gate.** Proven failure mode
  (`anthropics/claude-code#55754` + 3 duplicates — a Stop hook that blocks whenever it judges a
  task incomplete looped ~50 minutes on legitimately-in-flight async work; Anthropic's own fix
  was a bounded re-block cap, not removal). Any Stop-hook wiring in §6 MUST inherit this
  repo's existing `stop_hook_active` re-entry guard and retry-cap conventions from the start,
  never ship as a fresh unconditional block.
- **An LLM-judge-only completion/closure checker with no structural backing.**
  arXiv:2606.09863's direct finding: checklist-based LLM judges barely moved detection accuracy
  (AUROC ~0.576) and actively DEGRADED detection for Claude Sonnet on one benchmark
  (0.368→0.274), against a 45–78% false-success self-report base rate. This repo's own design
  principle already bans blob-text-only verification signals for exactly this reason. An LLM
  judge may exist as an OPTIONAL, clearly-secondary layer (§6 item 8) — never as the mechanism
  itself.
- **A separate, hand-maintained JSON/YAML evidence ledger file kept in sync with fix_plan.md's
  prose by a human/agent remembering to update both.** This is the precise "two sources of
  truth that silently diverge" class this repo has already been burned by twice (the
  heading-vs-body mismatch that motivated the original lint; `hooks.json` content vs.
  `config.toml`'s stale `trusted_hash`). If a ledger file exists at all, it must be
  machine-derived from the inline Proof blocks (§6 item 6), never a second hand-authored
  source of the same fact.
- **Requiring a Proof block on EVERY fix_plan.md entry, not just CLOSED/DONE/PASS-shaped
  ones.** Over-scoping into ritual — the exact objection real abandoned projects raised
  (`harness-methodology`: "too rigid"; another project cited in the claim-ledger research:
  "invisible governance," worried workflows "forced through become ritual"). Scope strictly to
  closure-shaped claims; leave OPEN/IN-PROGRESS entries free-form, exactly as today.
- **Re-executing every cited command on every single Stop-hook turn (a full re-run, not just a
  freshness hash-check).** Real, already-measured latency cost this repo's own research
  explicitly flagged for an analogous design (`h-subagent-masking-1-full-closure-design`:
  "`_testmon_gate`'s live `pytest` subprocess call... now runs on every single Stop-hook
  invocation... a real, user-visible latency change"). Default to hash/freshness-only
  re-checking (§4.3 step 4) for the per-turn gate; make full command re-execution an explicit,
  opt-in `--strict` flag or a periodic (not per-turn) sweep, never the per-turn default.
- **Extending this mechanism to police prose OUTSIDE `fix_plan.md`** (e.g. every chat message,
  every run-log paragraph) in this first pass. `dashboard.py`'s narrative-status-parsing gap
  (§1) is real and worth fixing eventually (§6 item 6 addresses it indirectly, once a derived
  ledger exists), but scoping the FIRST build to `fix_plan.md` closure headings only — the
  exact surface the dispatch asked about — keeps the blast radius and plan-check burden
  proportionate to the actual, demonstrated incident history.

---

## Summary of local vs. external grounding

Every mechanism recommended in §4 ties to at least one concrete local failure mode (the
wording-lint gap itself; the `H-CODEX-PARITY` configured-vs-fired incident; the rent-from-owner
460-green-while-crashing false-pass; the leading-space porcelain-parsing bug; the
review-to-commit TOCTOU incidents) AND at least one independently-verified external precedent
(SLSA's builder-anchored provenance; in-toto's Statement/Predicate binding; GitHub's
strict-mode freshness requirement; changesets' required-proof-artifact pattern; OpenSSF
Scorecard's evidence-from-real-API-not-self-report design; TDD Guard's real, LLM-core
architecture as a cautionary contrast). No recommended mechanism floats free of evidence, per
AC3 of this dispatch's own acceptance criteria.

---

## Supplementary pass — deep-research Workflow tool (independent second pass, same day)

**Provenance of this section, stated plainly:** everything below did NOT come from the
Researcher agent/session that produced §1–9 above. It came from a **separate, dedicated
`deep-research` Workflow tool** — an independent multi-agent harness (fan-out web search →
fetch → 3-vote adversarial claim verification → synthesis) — run at the user's explicit
request as a second, independently-verified pass over the *same underlying question* stated
in this dossier's title. That run hit a real bug (a degenerate/empty synthesis output on
first attempt); the bug was fixed and this result was independently confirmed to be genuine
(not a hallucinated artifact of the failure) before being handed to this Researcher dispatch
to persist and reconcile. This Researcher did **not** re-open or re-verify any of the claims
below — that verification already happened inside the deep-research tool's own 3-vote
adversarial pipeline (88 claims extracted, 25 voted on, 21 confirmed, 4 killed, 19 sources
fetched, 101 agent calls). This section only persists that result to durable storage and
reconciles it against §1–9's independently-derived recommendation.

Source artifact (ephemeral, now superseded by this persisted copy):
`/private/tmp/claude-501/-Users-eobodoechine/76bbdf7a-6070-4f9a-b7c5-b8bb1b371571/scratchpad/deep_research_final_result.json`

### Summary (verbatim from the tool's output)

> Real-world precedent for a mechanically-enforced "no DONE without evidence" gate is
> scattered across four proven building blocks, none of which requires cloud CI: (1) a
> structured, per-entry evidence-manifest schema (openclaw/releases' `evidence/<release-id>/`
> directory; in-toto's Link predicate) that replaces prose status with named JSON fields for
> commands, materials, and digests; (2) cryptographic content-addressing (SHA256 digest
> binding, in-toto/SLSA/Sigstore attestations) that makes "proof" re-hashable and
> tamper-evident rather than typed; (3) hard technical merge/commit gates (GitHub required
> status checks bound to an exact commit SHA; pre-commit's nonzero-exit-code contract) that
> block the state transition itself rather than auditing it after the fact; and (4)
> real-time enforcement hooks (TDD Guard) that intercept an AI agent's file edits against
> live test-runner output rather than linting the words it writes. Upgrading "wording lint"
> into "proof validation" has a direct precedent in `gh attestation verify` /
> `cosign verify-blob-attestation`, both of which re-derive a local file's digest and
> cryptographically re-check identity + artifact-binding + claimed properties rather than
> parsing text. The clearest gap for a local-only design is that GitHub's and Sigstore's
> strongest guarantees (Fulcio certs, Rekor transparency log, `attest-build-provenance`)
> depend on live OIDC/cloud infrastructure, so a solo-developer local gate would need to
> borrow the *schema and hashing* patterns (in-toto Link predicate, SHA256 content-addressing,
> SHA-bound freshness) while substituting local git hooks (pre-commit's exit-code primitive)
> for the cloud-dependent signing/transparency-log layer. Changesets is a useful negative
> precedent: it shows a widely-adopted "structured evidence-linked status change" workflow
> that deliberately stops at presence/format checking and never re-executes or audits the
> claim's truth, which is exactly the failure mode the research question wants to avoid.

### Findings (9, each carried the tool's own 3-vote adversarial confirmation)

1. **`openclaw/releases`' structured evidence manifest** (confidence: high). Each release's
   evidence lives under `evidence/<release-id>/` as a fixed set of files
   (`release-evidence.md`, `release-evidence.json`, `index.json`, `runs/<label>.json`) instead
   of one prose status sentence; each per-run JSON carries CI-provenance fields (run URLs,
   workflow names, git refs/SHAs, pass/fail state, timing, artifact names/sizes). Confirmed by
   direct fetch of `evidence/2026.5.27/` (5 real run files) plus `docs.openclaw.ai/reference/
   RELEASING`, which independently states the publish workflow "verifies the referenced
   preflight, validation, and plugin run identities" using "the exact run URL, job names, and
   workflow file path" and "full 40-character SHAs." Sources: github.com/openclaw/releases,
   the `2026.5.27/release-evidence.md` file, docs.openclaw.ai/reference/RELEASING.

2. **SLSA provenance + in-toto Link predicate define the proof-manifest schema shape**
   (confidence: high). SLSA provenance (schema URI `https://slsa.dev/provenance/v0.1`) is an
   in-toto predicate that "describes how an artifact or set of artifacts was produced"; the
   Link predicate requires every cited material to carry `name`+`digest`, and has a
   schema-separate, required `command` field. `actions/attest-build-provenance` implements
   this by binding a named artifact+digest to a SLSA provenance predicate in in-toto format.
   Verified against three primary sources directly. Sources: slsa.dev/spec/v0.1/provenance,
   in-toto/attestation `link.md`, actions/attest-build-provenance.

3. **Real re-verification tooling exists (the actual "wording lint → proof validation"
   upgrade path)** (confidence: high). `gh attestation verify` and
   `cosign verify-blob-attestation --bundle [file] --new-bundle-format` (cosign v2.4.0+)
   re-check a Sigstore-based cryptographic attestation — identity/instance origin,
   artifact-digest binding, provenance-content matching — rather than parsing text presence.
   Sources: actions/attest-build-provenance README, blog.sigstore.dev/cosign-verify-bundles.

4. **Cryptographic signing is what makes an attestation categorically stronger than a
   regex/keyword lint** (confidence: medium). A short-lived Sigstore/Fulcio cert (OIDC-tied,
   ~10 min) plus (for public repos) an append-only Rekor transparency log makes an attestation
   tamper-evident. Explicit caveat carried over from the tool's own verification: this proves
   provenance/identity of who attested, **not the semantic truthfulness of the payload** —
   whoever controls the CI/OIDC identity can still get a validly-signed attestation for a
   false claim. Source: actions/attest-build-provenance README.

5. **Required status checks are a hard, pre-transition merge gate bound to an exact commit
   SHA** (confidence: high). A check run against a previous SHA cannot satisfy the gate even
   if it passed — any new commit invalidates prior "proof" and forces re-verification. Direct
   precedent for detecting stale closure claims. Sources: GitHub branch-protection docs,
   GitHub required-status-checks troubleshooting docs.

6. **Offline attestation verification binds evidence to a SHA256 digest, but the offline
   trust-root has an unmitigated freshness gap** (confidence: medium). `trusted_root.jsonl`
   has no built-in expiration — "anything signed after the file is generated will verify
   until that Sigstore instance rotates its key material" (a few times/year), and revocations
   since the last regeneration are invisible. Independently corroborated by an open
   sigstore-python issue (#1175, "`--offline` should warn when the trust root is unreasonably
   old"). Source: docs.github.com verifying-attestations-offline.

7. **pre-commit's core primitive is a nonzero-exit-code contract, but its default isolation
   does not cover untracked files** (confidence: high). "The hook must exit nonzero on failure
   or modify files" is the framework's sole pass/fail signal; a pre-commit maintainer confirms
   in issue #708 that pre-commit "stashes unstaged changes, but not... untracked files," so a
   full-worktree test/coverage hook can pass or fail against content that isn't actually part
   of the commit. Sources: pre-commit.com, pre-commit/pre-commit#708.

8. **TDD Guard is real-time AI-agent enforcement via a PreToolUse hook, feeding live
   test-runner output** (confidence: medium). Blocks Write/Edit/MultiEdit before execution
   when there's no corresponding failing test, and blocks over-implementation beyond current
   test requirements. Explicit caveat carried over: "the validator is an LLM judgment call,
   not a fully deterministic check," with a documented history of false-positive
   over-blocking during a model transition. Source: github.com/nizos/tdd-guard.

9. **Changesets is a structured, evidence-linked status-change precedent that deliberately
   never re-executes or audits content** (confidence: medium). A changeset file is "an intent
   to release... with a summary of changes made"; the optional changeset-bot only detects
   file *presence*, not content; `changeset status` only checks a file exists relative to a
   base branch. Explicitly logged by the tool as "a useful negative example: a mature, adopted
   tool that solves 'structured evidence-linked status' but deliberately does NOT solve 'proof
   validation.'" Source: github.com/changesets/changesets.

### Refuted (4) — claims this pass's own adversarial verification killed

These matter as negative signal — each was a plausible-sounding claim the pipeline
specifically tested and rejected, not just left unverified:

1. **"openclaw/releases labels each CI run 'blocking' vs 'advisory' at the data-model
   level"** — voted 1-2, killed. No such required/optional distinction was confirmed in the
   schema.
2. **"SLSA provenance's 'recipe' is specific enough for bit-for-bit re-execution as
   verification"** — voted 0-3, killed. SLSA describes *how* something was built; it does not
   enable literally re-running it as a verification step.
3. **"GitHub's pre-commit stashing behavior by itself solves 'dirty worktree' evidence
   detection"** — voted 1-2, killed. Directly consistent with finding 7 above (untracked
   files aren't stashed) — a local gate needs its own explicit dirty-worktree check, not a
   reliance on pre-commit defaults.
4. **"GitHub required status checks have a 7-day time-based freshness window"** — voted 0-3,
   killed. GitHub's actual staleness mechanism is purely commit-SHA-based (finding 5), not
   time-based — "freshness" in this space means "tied to current HEAD," not "recently run."

### Sources (19 fetched this pass)

Primary (opened and fetched): github.com/openclaw/releases; github.com/actions/
attest-build-provenance; slsa.dev/spec/v0.1/provenance; github.com/nizos/tdd-guard;
github.com/changesets/changesets; docs.github.com .../about-protected-branches;
docs.github.com .../verifying-attestations-offline; github.com/in-toto/attestation
`link.md`; blog.sigstore.dev/cosign-verify-bundles; pre-commit.com; pre-commit/
pre-commit#708; docs.github.com .../troubleshooting-required-status-checks;
docs.github.com .../artifact-attestations (concepts page).
Secondary/forum/blog (lower weight, still fetched): mikael.barbero.tech's SLSA-and-in-toto
post; github.com/cli/cli#10059; darrenlester.com's git-pre-commit-stash post;
jyn.dev's "pre-commit hooks are fundamentally broken" post; github.com/changesets/
changesets/discussions/912; emmer.dev's "skippable GitHub status checks aren't really
required" post.

### Reconciliation against the original dossier (§1–9 above)

**`openclaw/releases` — genuinely new, not previously inspected.** This repo does not appear
anywhere in §2's list of 14 external sources / 8 opened repos from the original pass
(SLSA, in-toto, TDD Guard, changesets, changesets/action, OpenSSF Scorecard, cosign docs,
GitHub branch-protection, pre-commit, commitlint, attest-build-provenance, Bazel BEP, Danger,
arXiv:2606.04990). It is a real, additional, independently-confirmed lead.

**Verdict on its effect: it STRENGTHENS §4.2 ("Producer-anchored evidence snapshots") by
triangulation, but it does not change the local-only implementation choice, and it
should NOT be read as "adopt openclaw's exact pattern instead."** Reasoning:
- openclaw/releases is a real, shipped, third example (alongside SLSA/in-toto and OpenSSF
  Scorecard, both already in §2) of the same underlying design principle §4.2 borrows from
  SLSA — evidence must be **producer-anchored** (named run URLs, workflow names, git SHAs
  pinned to a specific CI execution) rather than self-declared prose. Three independent real
  ecosystems (SLSA/in-toto's formal spec, OpenSSF Scorecard's probe-based scoring, and now
  openclaw's per-release JSON manifest) converging on the same "structured fields + CI
  identity, not sentence" shape is stronger evidence for that design principle than either
  the original dossier or this pass alone.
- But openclaw's own verification mechanism is explicitly **cloud-CI-dependent**: the publish
  workflow "verifies the referenced... run identities using the exact run URL, job names, and
  workflow file path" — i.e. its proof is only checkable by dereferencing a live GitHub
  Actions run URL. This is the same cloud-dependency gap the original dossier's §2 item 8 and
  its "caveats" field already named for `attest-build-provenance`/Sigstore (Fulcio/Rekor
  require live OIDC). A solo developer with no cloud CI cannot verify a `run_url` field the
  way openclaw's own workflow does — there is no live run to dereference.
- Net effect: openclaw/releases is evidence that the **schema shape** (§4.1's Proof block:
  named command/files/hashes fields, one JSON record per claim) is right and battle-tested at
  a third real-world site — reinforcing, not just duplicating, §4.1/§4.2 — while the original
  dossier's specific engineering choice for a local-only, no-cloud-CI gate (§4.2's
  `run_and_record.py`, which computes its own local SHA256 content hash rather than trusting
  a dereferenced remote CI run URL) remains the correct substitution, exactly as §4.2 already
  reasoned by analogy from SLSA's `builder.id`. This new repo would strengthen the original
  dossier's §2 source list if inspected there; it does not surface any reason to redesign §4.

**Other overlaps and where the two passes agree or diverge:**
- **GitHub required-checks SHA-binding / staleness ("stale after new commit SHA," not
  time-based).** Strong, independent agreement. Both passes separately fetched
  docs.github.com's branch-protection and required-status-checks pages and landed on the
  identical fact: checks are invalidated by a new commit SHA, not by elapsed time. This
  pass's finding 5 and refuted claim 4 (killing a hypothesized "7-day freshness window")
  independently confirm the original dossier's §2 item 8 / §4.5 design choice to make
  staleness detection **hash/SHA-based, not time-based** — two separately-run research
  processes converging on the same primary-source fact is a meaningful triangulation, not
  just a duplicate citation.
- **pre-commit's dirty-worktree/untracked-file gap.** Strong, independent agreement, and
  notably this pass's own adversarial pipeline explicitly tested and KILLED the more
  optimistic claim ("pre-commit's stashing solves dirty-worktree detection," refuted #3),
  landing on the same conclusion the original dossier already reached in §2 item 9 and acted
  on in §4.3 step 5 / §4.7: pre-commit's default stash does not cover untracked files, so a
  local gate needs its **own** explicit dirty-worktree check rather than relying on
  pre-commit's isolation. This is a second, independently-derived confirmation that the
  original design's dirty-worktree gate (§3 candidate #4, §4.3 step 5) is solving a real,
  non-imaginary gap and not a hypothetical one.
- **TDD Guard: real-time hook interception vs. this repo's own closure-time lint.** Agreement
  on mechanism, with the same caveat both passes independently surfaced. This pass's finding
  8 states TDD Guard's validator is "an LLM judgment call, not a fully deterministic check" —
  this matches the original dossier's own corrected characterization (§1, citing
  `coder-detection-structural-signal-subagentstop-2026-07-08.md`'s direct source-code read of
  `src/validation/validator.ts`: the real mechanism is an LLM call gated by a structural
  pre-filter, not a purely structural check). Both passes therefore independently rank TDD
  Guard as a real precedent for *real-time* AI-agent interception (as opposed to
  after-the-fact lint), while agreeing it should not be cited as a purely-structural/
  deterministic mechanism. This is consistent with — and adds a second, independent citation
  for — the original dossier's decision (§3 candidate #9, §6 item 8) to keep any LLM-judged
  layer strictly secondary/optional, never load-bearing alone.
- **Changesets as a negative precedent.** Agreement, and this pass states it more bluntly.
  The original dossier already used changesets/changesets and changesets/action as evidence
  for the "required proof artifact present" pattern while separately noting (via
  changesets/action's `has-changesets` boolean output) that it checks presence, not content.
  This pass's finding 9 makes the same point as an explicit, named "useful negative example"
  — a mature, 12k-star, actively-maintained tool that solves structured evidence-linked
  status changes but deliberately never re-executes or audits the claim. Both passes reach
  the same verdict: changesets is precedent for the *shape* of a required-artifact gate, not
  for *proof validation* — directly supporting the original dossier's own explicit contrast
  framing in §2 item 4/5 and its choice to build snapshot cross-checking (§4.3 step 3) rather
  than stop at presence-checking the way changesets does.
- **New material not previously covered:** the offline Sigstore trust-root freshness gap
  (finding 6 — `trusted_root.jsonl` has no expiration, corroborated by open issue
  sigstore-python#1175) is a new, additional argument (not present in the original dossier)
  for keeping full cryptographic Sigstore/SLSA attestation chains out of scope for this repo
  (original dossier §9, "Do NOT build... full cryptographic DSSE/SLSA/in-toto signed
  attestation chain"). It reinforces that decision from a different angle: even the offline
  verification path this repo could theoretically borrow from has its own known, currently
  unmitigated staleness weakness, on top of the original dossier's own stated reason
  (wrong threat model for a single-operator repo).

### Bottom line

This second, independently-run pass does not change the original dossier's top-3-mechanism
recommendation (§4.1 Required Proof block + §4.2 Producer-anchored evidence snapshot +
§4.3 upgraded closure-lint with SHA/hash-based freshness and dirty-worktree checks) — it
**reinforces** it: the one genuinely new lead (`openclaw/releases`) is additional real-world
triangulation for the same producer-anchored-evidence design principle rather than a
competing architecture, and every other point of overlap (GitHub SHA-based staleness,
pre-commit's incomplete dirty-worktree isolation, TDD Guard's LLM-core mechanism, changesets
as a presence-only negative precedent) was independently re-derived by a separate research
process and landed on the same conclusion the original dossier already reached.
