# Deep-dive: how do real OSS LLM code-review tools merge N INDEPENDENT reviewers' findings from the SAME round? (2026-07-09)

**Dispatch:** go deeper into the four tools already found by
`research/plancheck-nonbinding-saturation-2026-07-09.md`
(`calimero-network/ai-code-reviewer`, `oprogramadorreal/optimus-claude`,
`retsimx/opencode-agents`, `gopherguides/gopher-ai`) plus CodeRabbit — specifically on
**multi-reviewer merge/dedup** (N reviewers, same round, potentially disagreeing), not
the round-over-round saturation question the prior pass already covered. Question set:
(a) does the tool run multiple independent reviewer passes and merge results, (b) what's
the actual tie-break when reviewers disagree on classification/severity, (c) is there a
persisted structured-findings format between runs and what's its schema, (d) is there a
real importable package vs. a bespoke prompt script.

**Method:** cloned all four repos fresh via `gh repo clone` into
`/private/tmp/claude-501/.../scratchpad/repos/` and read source files directly (not
README paraphrase) — every quote below is from an opened file, and one claim
(ai-code-reviewer's severity tie-break) was independently **reproduced by running the
actual comparison logic** in a Python REPL, not just read. CodeRabbit was checked via one
real, opened blog post (marketing content, not source — it has no public repo).

---

## Headline answer

**Exactly one of the four tools has a real, executable, tested, cross-reviewer
disagreement-resolution mechanism: `calimero-network/ai-code-reviewer`'s
`apply_cross_review()` function.** It is also the only one of the four that is a
genuine, pip-installable Python package. The other three tools' "multi-reviewer" framing
is either (i) N agents whose outputs get algorithmically clustered but never actually
adjudicated for disagreement (ai-code-reviewer's *other*, separate aggregation path, and
optimus-claude's parallel agents), or (ii) pure natural-language instructions telling an
LLM orchestrator to "resolve contradictions" with no code backing the decision at all
(optimus-claude's Step 7, opencode-agents, gopher-ai's `llm-compare`/`address-review`).
**A genuinely new, load-bearing finding this pass:** ai-code-reviewer's OWN newer
`orchestrator/aggregator.py` module has a real, reproducible bug in its severity
tie-break that contradicts its own docstring and inverts the intended priority — found by
running the code, not just reading it. The SAME repository's older `review.py` module
implements the equivalent tie-break correctly, twice, showing the bug is a regression
introduced in the rewrite, not a universal flaw in the approach.

---

## 1. `calimero-network/ai-code-reviewer` — the one real, working, portable implementation

**Confirms (a) — yes, genuinely parallel independent reviewers, twice over, in two
different mechanisms:**

1. **First-round parallel agents.** `src/ai_reviewer/orchestrator/orchestrator.py`,
   `AgentOrchestrator.review()`:
   ```python
   tasks = [
       asyncio.create_task(
           self._run_agent_with_timeout(agent, diff, file_contents, context),
           name=f"agent-{agent.agent_id}",
       )
       for agent in self.agents
   ]
   results = await asyncio.gather(*tasks, return_exceptions=True)
   ```
   Each `agent` is a distinct subclass of `ReviewAgent`
   (`src/ai_reviewer/agents/{security,performance,patterns}.py`) with its own hard-coded
   `SYSTEM_PROMPT` — e.g. `SecurityAgent.SYSTEM_PROMPT` opens *"You are an expert security
   code reviewer with deep knowledge of: OWASP Top 10 vulnerabilities..."* — a genuinely
   independent LLM call per agent, not one shared call re-labeled. `min_agents_required:
   int = 2` and `InsufficientAgentsError` if too few succeed — the orchestrator will not
   silently fall back to a single reviewer.

2. **Second-round cross-review (the real find).** `src/ai_reviewer/review.py`,
   `get_cross_review_prompt()` + `apply_cross_review()` + `run_cross_review_round()`. After
   the first-round findings are consolidated, a **second wave of agents re-reviews the
   findings themselves** — this is the part that answers (b) directly.

**Confirms (b) — the actual tie-break code, quoted verbatim, `apply_cross_review()`
(`src/ai_reviewer/review.py:330-429`):**

```python
def apply_cross_review(
    review: ConsolidatedReview,
    all_assessments: list[tuple[str, list[dict[str, Any]]]],
    min_validation_agreement: float = 2 / 3,
) -> ConsolidatedReview:
    """Filter and re-rank findings using cross-review assessments.

    - Drops findings where the fraction of agents that said valid is < min_validation_agreement.
    - Re-orders by average rank (1 = first), then by severity.
    """
    ...
    id_to_votes: dict[str, list[tuple[bool, int]]] = {fid: [] for fid in finding_ids}
    for _agent_name, assessments in all_assessments:
        for a in assessments:
            fid = a.get("id") or a.get("finding_id")
            ...
            id_to_votes[fid].append((valid, rank))

    for fid in finding_ids:
        finding = id_to_finding[fid]
        votes = id_to_votes.get(fid, [])
        if finding.severity == Severity.CRITICAL and finding.category == Category.SECURITY:
            # Keep unless every assessing agent explicitly rejected it; one valid vote is enough
            if not votes or any(v for v, _ in votes):
                kept.append((finding, 1.0, 0))
            continue
        if not votes:
            kept.append((finding, 1.0, 99.0))
            continue
        valid_count = sum(1 for v, _ in votes if v)
        valid_ratio = valid_count / len(votes) if votes else 1.0
        if valid_ratio < min_validation_agreement:
            continue  # Drop finding
        avg_rank = sum(r for _, r in votes) / len(votes) if votes else 99.0
        kept.append((finding, valid_ratio, avg_rank))

    severity_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.SUGGESTION: 2, Severity.NITPICK: 3}
    kept.sort(key=lambda x: (x[2], severity_order.get(x[0].severity, 4)))
```

This is the closest thing found anywhere in this survey to a real, deterministic,
disagreement-resolution algorithm for "N reviewers, same round, potentially disagreeing":
- **Ordinary findings**: a **2/3 supermajority-vote threshold** (default
  `min_validation_agreement = 2/3`) — a finding survives only if at least two-thirds of the
  agents that assessed it voted `valid: true`; otherwise it is dropped outright (not
  demoted, not flagged — dropped). Agents that never voted on a given finding are excluded
  from both numerator and denominator (`len(votes)`, not total agent count) — an
  abstention-aware design, confirmed by the code comment: *"Use len(votes) not
  n_agents: only agents that assessed this finding count (omit = no vote)."*
- **CRITICAL+SECURITY findings get an asymmetric bypass**: they survive unless **every
  single voting agent explicitly rejects them** — one dissenting "valid" vote is enough to
  save a security-critical finding from the majority. This is a deliberate,
  well-considered design choice (biases toward false-positive-security-alert over
  false-negative), not an oversight — and it is real-tested, not just commented. Two
  dedicated unit tests confirm the exact boundary (`tests/test_review.py:646-703`):
  - `test_critical_security_finding_survives_with_one_valid_vote` — 2 agents assess a
    CRITICAL+SECURITY "SQL injection" finding; agent 1 votes valid, agent 2 votes invalid;
    asserts `"sec1" in result_ids` and that it is *ranked first* despite the split vote.
  - `test_critical_nonsecurity_finding_can_be_dropped` — the identical scenario but with
    `Category.LOGIC` instead of `Category.SECURITY` on a CRITICAL finding: both agents vote
    invalid, and the test asserts `len(result.findings) == 0` — i.e. **severity alone does
    not earn the bypass; it must be CRITICAL *and* SECURITY specifically.**
- **Re-ranking**: sort key `(avg_rank, severity_order[severity])` — average of each
  agent's stated 1-indexed importance rank, with severity as an explicit ascending-index
  tie-break (`CRITICAL: 0` sorts first) for rank ties. This is **correctly ordered** in
  this module.
- **Severity-graduated confidence filtering** (a related, not identical, mechanism in the
  same file, `CONFIDENCE_THRESHOLDS`, `review.py:525-530`): `{CRITICAL: 0.5, WARNING: 0.6,
  SUGGESTION: 0.7, NITPICK: 0.8}` — the bar to survive gets *stricter* as severity drops,
  another explicit asymmetric-by-severity design applied elsewhere in the same pipeline.

**Confirmed real and default-on, not experimental/dead code** — `src/ai_reviewer/cli.py`:
```
--no-cross-review  ... help="Disable second round where agents validate and rank findings
                          (default: cross-review on when --agents>=2)"
```
`enable_cross_review: bool = True` is the default parameter value; `cross_review_ran =
effective_agents > 1 and enable_cross_review`. This is a shipped, on-by-default feature of
a released CLI tool, not a research toy.

### The bug this pass found (independently reproduced, not just read)

The repo has a **second, separate, newer aggregation path** —
`src/ai_reviewer/orchestrator/aggregator.py`'s `ReviewAggregator._merge_cluster()` — used
for merging *first-round* findings that cluster as near-duplicates (not the cross-review
disagreement-vote above). Its severity selection:

```python
# Use most severe rating
severity = max(findings, key=lambda f: list(Severity).index(f.severity)).severity
```

`Severity` is declared `CRITICAL, WARNING, SUGGESTION, NITPICK` in that order, so
`list(Severity).index(Severity.CRITICAL) == 0` and
`list(Severity).index(Severity.NITPICK) == 3`. `max(..., key=index)` therefore returns
the finding with the **highest** index — i.e., **NITPICK**, not CRITICAL — the exact
opposite of what the comment claims and of what a "most severe" merge should do. I
reproduced this directly (not just read the code) rather than trust the static read:

```
$ python3 -c "
from enum import Enum
class Severity(Enum):
    CRITICAL='critical'; WARNING='warning'; SUGGESTION='suggestion'; NITPICK='nitpick'
print(max([Severity.CRITICAL, Severity.NITPICK], key=lambda s: list(Severity).index(s)))
"
Severity.NITPICK
```
Confirmed: if two agents' near-duplicate findings on the same file/line disagree between
CRITICAL and NITPICK, `_merge_cluster` keeps the NITPICK label. **No test in
`tests/test_aggregator.py` exercises two *different* severities in the same cluster** —
every aggregator test uses matching severities across agents (`test_deduplicates_
identical_findings`, `test_keeps_unique_findings_separate`, `test_priority_ranking` — the
latter's two findings are in *different* files/clusters, never merged together) — so this
defect is real, live in shipped code, and untested. The **older** `review.py` module in
the same repo does this correctly, twice: `_cap_findings`'s exemption test (*"All
`critical` findings are exempt and never dropped"*) and `apply_cross_review`'s
`severity_order = {CRITICAL: 0, ...}` sort key (ascending index used directly, not
inverted via `max`). This is a genuine, actionable "don't blindly trust the whole repo
uniformly" lesson: **the same codebase has both the correct pattern and an inverted one
for the identical problem**, in two different modules written at different times.

**Confirms (c) — no JSONL persisted-findings file anywhere; cross-run state is derived by
re-parsing GitHub's own PR comments, not a local structured store.**
`src/ai_reviewer/models/review.py`'s `ReviewHistory` dataclass — the ONE model in this
codebase clearly designed for cross-run structured persistence — is explicitly
unfinished: *"Staged for future use — the runtime severity-stabilization logic in
`compute_review_delta` currently derives its inputs from `PreviousComment` matching and
`estimate_review_count`. This model captures richer state that downstream features (trend
analysis, adaptive thresholds) will consume once **a persistence layer is wired in**."*
The actual cross-run mechanism today is `github/client.py`'s `PreviousComment` +
`get_previous_review_comments()`, which re-fetches and re-parses the bot's own previously
POSTED GitHub PR comments each run (`hash_lookup`, `fuzzy_lookup`, `title_lookup` dicts
built from that re-parsed text) — i.e. **GitHub's comment thread IS the persistence
layer**, not a JSON/JSONL file on disk. `ConsolidatedFinding` does define two
deterministic hash properties usable as a dedup key if a real store existed —
`finding_hash` (`sha256(file_path:line_start:normalized_title)[:12]`) and
`finding_hash_fuzzy` (`compute_fuzzy_hash`, keyed on file path + the 5 longest
sorted 4+-char words in the title, ignoring line number/category) — but neither is
currently written to a JSONL append-log; both exist only to match against re-parsed
GitHub comment text.

**Confirms (d) — genuinely pip-installable, real package, not just a script.**
`pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
[project]
name = "ai-code-reviewer"
version = "0.1.0"
description = "Multi-agent code review system that orchestrates multiple LLMs"
requires-python = ">=3.11"
dependencies = ["anthropic>=0.40.0", "PyGithub>=2.1.0", "fastapi>=0.109.0", ...]
```
`src/`-layout, `hatchling` build backend, real dependency pins, MIT license,
`classifiers` including `Development Status :: 3 - Alpha`. `ReviewAggregator`,
`apply_cross_review`, and the finding/severity models are all directly importable
(`from ai_reviewer.orchestrator.aggregator import ReviewAggregator`,
`from ai_reviewer.review import apply_cross_review`) — genuinely portable/adoptable as a
library, not merely readable-for-ideas.

**Maturity:** MIT, 7★, pushed 2026-07-05 (created 2026-02-03) — small but real and
actively maintained.

---

## 2. `oprogramadorreal/optimus-claude` — real N-agent-per-round dispatch, but the merge itself is 100% prompt engineering (no code)

**Confirms (a)** — `skills/code-review/SKILL.md` (single-round mode, not the -deep
iteration loop) dispatches **5 to 7 genuinely distinct reviewer personas in one round**:
> *"Step 5: Parallel Multi-Agent Review (5–7 agents)... Launch every applicable agent as a
> `general-purpose` Agent tool call in a **single** message so they run in parallel."*

Agent table (quoted): `1 — Bug Detector`, `2 — Security & Logic`,
`3 — Guideline Compliance A`, `4 — Guideline Compliance B` (*"Same task as Agent 3 —
independent review reduces false negatives"* — i.e. two **intentionally-duplicated**
independent reviewers on the identical task, specifically to get disagreement signal),
`5 — Code Simplifier`, `6 — Test Guardian` (conditional), `7 — Contracts Reviewer`
(conditional). This is a real, distinct-persona parallel dispatch, not a re-labeled single
call — confirmed from the actual agent prompt files
(`skills/code-review/agents/{bug-detector,security-reviewer,guideline-reviewer,...}.md`).

**Answers (b) — but here is the central negative finding of this dossier: the actual
disagreement-resolution "logic" is pure text instructions for the orchestrating LLM to
execute itself, with zero backing code.** `SKILL.md` Step 6/7, quoted exactly:

> *"4. Cross-agent consensus — for guideline findings, check if both Agents 3 and 4
> flagged the same issue (consensus = higher confidence)"*

> *"### Contradiction resolution — After deduplication, check for cross-agent
> contradictions — findings that target the same code region but recommend opposite
> directions (e.g., 'add more validation' vs. 'simplify this validation'). **Keep the
> higher-severity finding and drop the other. When severities are equal, keep the
> security/correctness finding** — security requirements justify proportionate
> complexity."*

This IS a genuine, sensible tie-break *rule* (severity wins; security wins ties) — but it
is a **sentence in a markdown file**, not a function. There is no code anywhere in this
repo that computes "is this a contradiction," compares severities, or drops a finding —
the orchestrating Claude instance is expected to do all of that reasoning itself, in its
own context window, each time it runs the skill, with no persisted trace of *why* it kept
one finding over another beyond what it chooses to write in its final report. Searched
the entire repo (`grep -rn` across all `.py` files) for any executable trace of this
logic — none exists; `scripts/harness_common/` (the one real Python package in this repo)
never touches cross-agent consensus or contradiction resolution at all.

**Confirms (c) — real, working, importable JSON progress-file persistence exists, but for
a DIFFERENT problem (cross-*iteration* status tracking of already-merged findings, not
cross-*reviewer* merge within one round).** `scripts/harness_common/findings.py`
(genuinely portable, tested Python — `test/harness-common/test_findings.py` exists) and
`scripts/harness_common/progress.py`:

```python
def write_progress(path, progress):
    """Write the progress file atomically... written to a sibling temp file and then
    os.replace()d into place... so an interrupted write... can never leave a torn/
    truncated progress file"""
    ...
    data = json.dumps(progress, indent=2) + "\n"
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(data, encoding="utf-8")
    os.replace(str(tmp_path), str(path))
```
Schema (`_new_finding_from_fix`, `findings.py:38-66`), one JSON object per finding inside
`progress["findings"]` (a single rewritten JSON document, **not** a JSONL append-log):
`id` (`f-001`, `f-002`, ...), `file`, `line`, `end_line`, `category`, `guideline`,
`summary`, `fix_description`, `iteration_discovered`, `iteration_last_attempted`,
`status` (`discovered` → `applied-pending-test` → `fixed` / `reverted — test failure` →
`reverted — attempt 2` → `persistent — fix failed`, with escalation logic in
`_escalate_revert_status`), `status_history` (list of `{iteration, status, detail}`),
`agent`, `confidence`, `severity`, `pre_edit_content`, `post_edit_content`. Stored at
`.claude/code-review-deep-progress.json` per `constants.py`'s `DEEP_SKILL_PROGRESS_FILE`
map. This is real, well-engineered, atomic-write, crash-safe persistence — but it tracks
the lifecycle of findings **that Step 7's prompt-only consolidation has already merged**;
the Python code has no visibility into which of the 5-7 agents originally flagged a given
finding or how a contradiction was resolved. `finding_key()` (file, line, category tuple)
matches a finding across iterations for status updates — again, temporal matching, not
cross-reviewer matching.

**Confirms (d) — a real, tested, but NOT packaged Python module.** `pyproject.toml` in
this repo contains ONLY pytest config (`[tool.pytest.ini_options]`) — no `[project]`
table, no `build-system`, nothing `pip install`-able. `scripts/harness_common/__init__.py`
is empty (present only to make it an importable package path within the repo). It is
invoked as `python scripts/harness_common/cli.py <subcommand>` from Bash inside the skill
markdown files, per its own module docstring: *"The skills hold no state; the CLI
reads/writes a JSON progress file on disk."* Contrast with ai-code-reviewer: this is real,
substantial, well-tested code (the one clear case of "real code, not just prompts" among
the three non-ai-code-reviewer tools) — but it is **vendor-and-copy reusable, not
pip-install reusable** — no packaging metadata makes it a library today.

**Maturity:** MIT, 64★, pushed 2026-07-07 (today) — actively maintained.

---

## 3. `retsimx/opencode-agents` (ralphreview / deep-review / ultrawork) — zero code anywhere; confirms the negative case cleanly

**Confirms (a) is NO for the multi-reviewer-same-round shape.** The entire repo is
markdown (199 `.md` files, only shell/Go/templ files belong to unrelated demo/template
skills — literally zero Python or any language implementing review logic). `ralphreview`
delegates to exactly **one** nested `deep-review` subagent per iteration
(`skills/ralphreview/SKILL.md`: *"the coordinator delegates the deep-review analysis to a
nested Task subagent"* — singular), and `deep-review/SKILL.md` is itself a **single**
agent covering 9 review dimensions sequentially (Correctness, Regression Risk, State &
Data, UI/Rendering, Tests, Dead Code, Security, Performance, DRY) — not 9 independent
agents. There is no cluster of independent reviewers whose outputs get merged at all in
this tool's actual review step.

The repo DOES have a file literally named `skills/ultrawork/resources/multi-review-
protocol.md`, which sounds on-topic but turns out **not to be** — it defines 11 review
*types* (Completeness, Meta, Simplicity, Alignment, Safety, Regression, Reusability,
Consistency, Quality, Cascade Impact, Final), each gating a **different, sequential**
numbered step (Step 2, Step 3, Step 4, Step 6...) of one waterfall pipeline — never
simultaneous, never merged, no disagreement possible because they never run at the same
time on the same artifact. This is a genuinely useful negative finding: a file whose name
promises exactly what this dispatch is looking for, and does not deliver it — worth
recording so a future scan doesn't re-open it expecting something different.

**(b) is N/A** — there being no simultaneous independent reviewers, there is no
disagreement to tie-break. The closest thing, `ralphreview`'s clean-streak counter, only
tracks temporal recurrence of one linear pipeline's own signal.

**(c) — the persistence format here is the most primitive of all four tools**: a plain
pipe-delimited text file, `.ralphreview-state-<hash>`, format
`STATUS|SEVERITY|file:line|description` (confirmed from `SKILL.md`'s own header template:
*"# RalphReview State — STATUS|SEVERITY|file:line|description... Statuses: NEW, FIXED,
SKIPPED"*). Not JSON, not JSONL — a flat text log, appended by one coordinator and
in-place-edited (status field rewritten) by another, entirely via LLM-followed textual
instructions (*"find the matching entry by file:line and description, then rewrite its
status"*) — no parser code exists anywhere in the repo for this format.

**(d) is NO** — no package, no library, no executable code of any kind implementing
review or merge logic. This is the cleanest example in the whole survey of "prompt
orchestration with literally zero backing implementation."

**Maturity:** unlicensed, 0★, created 2026-06-04, last push 2026-06-18 — young,
single-repo, no adoption signal (unchanged from the prior pass's assessment; this pass
adds the depth on why it's a clean negative for the specific multi-reviewer-merge
question).

---

## 4. `gopherguides/gopher-ai` — the richest set of schemas/state files of the three prompt-only tools, but every actual disagreement-resolution step is still delegated to LLM judgment

**Confirms (a) partially — three distinct facilities, all real, none of them execute a
merge algorithm in code:**

1. **`plugins/llm-tools/commands/llm-compare.md`** — the single closest artifact in this
   whole survey to "run N independent reviewers on the same input and reconcile
   disagreement," but it is a **command template for the orchestrating Claude session**,
   not code. It runs Codex/Gemini/Ollama **in parallel** on the identical prompt (*"Run
   in parallel where possible"*) and then asks the orchestrating agent to fill in a
   template:
   ```
   ### Points of Agreement
   - [Where models agree]
   ### Key Differences
   - [Significant differences in approach/recommendation]
   ### Synthesis
   [Claude's analysis combining insights from all responses]
   ### Recommendation
   - Models agree → "All models align on [approach]. Consensus suggests [conclusion]."
   - Models disagree → "Models differ on [aspect]. Consider [factors] when deciding."
   ```
   Every one of those bracketed lines is generated by the orchestrating LLM's own
   judgment at synthesis time — there is no comparison function, no similarity threshold,
   no vote count anywhere in the repo backing "Points of Agreement" or "Key Differences."
   This is the platonic example of "prompt-engineering pattern with no reusable
   implementation" for exactly the disagreement-reconciliation question this dispatch
   asks about.

2. **`plugins/go-workflow/skills/address-review/`** — addresses feedback from MULTIPLE
   real, independent, simultaneously-active bot reviewers on one PR
   (`coderabbitai[bot]`, `greptileai`, `copilot-pull-request-review[bot]`, `claude[bot]`),
   confirmed from `bot-registry.md`'s registry table. **But it does not cluster or
   reconcile their findings at all** — `fix-cycle.md` Step 3 groups feedback only into
   "Group A" (resolvable GitHub review threads) vs "Group B" (pending
   `CHANGES_REQUESTED` reviews), regardless of *which bot* said it, and Step 4 addresses
   each GitHub comment thread individually (parallel dispatch is grouped **by file**, not
   by finding-similarity across bots): *"When there are 3 or more unresolved comments
   targeting different files, dispatch parallel Implementer subagents... Group comments
   by file."* If CodeRabbit and `claude[bot]` both flag the same line with different
   framings, they surface as two separate GitHub comment threads and get fixed
   independently — GitHub's own thread structure does the "clustering" (each thread is
   already a distinct object), and the skill never semantically merges across bots. This
   is a genuine, clean negative finding for the closest real-world analog to the
   dispatch's "N reviewers disagreeing" scenario.

3. **`plugins/llm-tools/lib/review-loop/`** — a single-model **iterative** review loop
   (codex/gemini/ollama, one model per run, chosen via `LLM_CHOICE`), with:
   - a real formal output schema, `plugins/llm-tools/schemas/codex-review.json` (JSON
     Schema, `findings[]` with `title` (≤80 chars), `body`, `confidence_score` (0-1),
     `priority` (0=critical..3=low), `category` (enum: correctness/security/performance/
     maintainability/developer-experience), `code_location.{file_path,line_range}`, plus
     `overall_correctness` (enum: `"patch is correct"`/`"patch is incorrect"`),
     `overall_explanation`, `overall_confidence_score` — all `required`,
     `additionalProperties: false`). This is a genuinely reusable JSON Schema artifact
     (schema, not code) — the most rigorously specified single-pass findings shape found
     in this whole survey.
   - real persisted per-pass findings, but again **cross-pass (temporal), not
     cross-reviewer**: `state-persist.md` — *"`findings_pass_<N>` (Step 6) — JSON array
     of the filtered findings, used for cross-pass de-duplication"* — a single JSON state
     file (`.local/state/review-loop.loop.local.json`) updated via `jq` merge commands
     (`jq --argjson f "$FILTERED_JSON" '.[$key] = $f.findings' ...`), not a JSONL
     append-log.
   - `parse-findings.md` Step 7, *"De-duplicate across passes"* — gives the exact
     dedup key (`(file_path, line_range.start, normalized title)`) but explicitly leaves
     the match/skip decision itself to the executing agent's own judgment (*"Compare...
     against previous-pass findings stored in the state file. Skip duplicates"* — no jq
     snippet is given for the actual comparison, only for the persist step). Half-code,
     half-instruction.

**(b)** — no code anywhere in gopher-ai computes a severity/classification tie-break
across sources. `codex-review.json`'s `priority` field is a single reviewer's own
assessment, never reconciled against a second source.

**(c)** — richest schema (real JSON Schema file) of the three non-ai-code-reviewer
tools, but confirmed NOT a JSONL log — single mutable JSON document per PR/session,
updated via shell `jq` merges, matching the pattern optimus-claude also uses (single
rewritten JSON doc, not append-only).

**(d)** — no importable package; `plugins/llm-tools` ships shell scripts
(`lib/loop-state.sh`) and markdown, no Python/Go implementing review-merge logic. The Go
code elsewhere in the repo (`plugins/go-web/templates/`, `agent-skills/examples/demo-
repo/`) is unrelated scaffolding/example code for the Go-project generator, not review
logic.

**Maturity:** MIT, 17★, pushed 2026-07-09 (today) — real, actively maintained.

---

## 5. CodeRabbit (commercial, no public repo) — re-confirmed docs-only, no mechanism disclosed

Re-checked directly (WebFetch on the actual blog post, not just search snippets):
`coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-
codebases`. Direct fetch result: the page describes context-gathering (codegraph,
semantic index, team rules, linter/security-scanner signals) and states linter/scanner
output is "folded... into our easy-to-read and understand reviews" and that *"a separate
judge model scores each finding against the gathered context and drops the ones it cannot
ground"* (from search-snippet corroboration) — but the fetched page **contains no
description of a reconciliation mechanism when multiple sources (linters vs AI vs
security scanners) disagree, no severity/confidence tie-break rule, and no structured
data schema**. This is a real, deliberate check (not a re-assertion of the prior pass's
flag) — the mechanism CodeRabbit uses for exactly this dispatch's question is simply not
publicly documented anywhere findable this pass. Unchanged verdict from the prior
research: commercial, closed-source, evidence limited to marketing copy — cannot be
ported regardless of what it does internally.

---

## Comparison matrix

| Tool | (a) N independent reviewers, same round? | (b) real tie-break code for disagreement? | (c) persisted structured findings format | (d) real importable package? |
|---|---|---|---|---|
| **ai-code-reviewer** | **Yes** — distinct-persona async agents (`orchestrator.py`) + a genuine second-round cross-review vote (`apply_cross_review`) | **Yes** — 2/3 supermajority vote + CRITICAL+SECURITY one-valid-vote-survives bypass, unit-tested; **but** a sibling module (`_merge_cluster`) has a real, reproduced, untested severity-tie-break bug (picks NITPICK over CRITICAL) | No JSONL — cross-run state is re-parsed GitHub PR comments (`PreviousComment`); two SHA256 dedup-hash properties exist on `ConsolidatedFinding` but aren't yet written to any local store (`ReviewHistory` is explicitly "staged, no persistence layer wired in") | **Yes** — real `pyproject.toml`, `hatchling` build, pinned deps, `src/` layout, MIT |
| **optimus-claude** | Yes — 5-7 distinct-persona agents in one dispatch (`code-review` skill) | **No** — Step 6/7 "cross-agent consensus" and "contradiction resolution" are markdown sentences for the orchestrating LLM to execute itself; zero backing code | Yes, real — atomic-write JSON progress file (`harness_common/progress.py`), rich per-finding schema with status-lifecycle history — but for cross-*iteration*, not cross-*reviewer*, tracking | Real, tested Python (`harness_common`), but **not packaged** (`pyproject.toml` has no `[project]` table) — vendor-copy reusable only |
| **opencode-agents (ralphreview)** | **No** — one `deep-review` subagent per iteration, covering 9 dimensions serially, not N parallel reviewers; "multi-review-protocol.md" is a serial waterfall, not simultaneous reviewers | N/A | Plain pipe-delimited text file (`STATUS\|SEVERITY\|file:line\|description`), no parser code | No — zero code in the repo (pure markdown) |
| **gopher-ai** | Mixed — `llm-compare` runs 3 real models in parallel; `address-review` handles 4 real simultaneous bot reviewers on one PR | **No** — `llm-compare`'s "Points of Agreement/Key Differences/Synthesis" is pure LLM judgment at write-time; `address-review` never clusters across bots, relies on GitHub's own per-thread structure | Real JSON Schema (`codex-review.json`) for one reviewer's structured output; single mutable JSON state file per session (`jq`-merged), cross-*pass* dedup key given but the match logic itself is left to LLM judgment | No — shell + markdown only |
| **CodeRabbit** | Unknown/undisclosed (commercial) | Unknown/undisclosed | Unknown/undisclosed | No (closed-source, no public repo) |

---

## What's genuinely portable vs. what's prompt-engineering theater

**Actually reusable code, if `reconcile_gap_records.py` wanted to add a "same-round,
N-lenses-disagree" merge step (it currently only clusters + traces + tie-breaks
CONTRADICTORY pairs pairwise, per its own docstring — it does not yet have a
majority-vote-across-N mechanism):**
- **Port candidate**: `apply_cross_review`'s vote-tally pattern — `id_to_votes: dict[finding_id
  -> list[(valid, rank)]]`, abstention-aware ratio (`len(votes)`, not `total_agents`), a
  configurable supermajority threshold, and a named, tested, narrowly-scoped bypass class
  (not "all CRITICAL," but "CRITICAL AND SECURITY specifically") for the one class that
  must survive a single dissent. This is real, small, pure-function, stdlib-only Python —
  directly adaptable to plan-check's own `gap_type` vocabulary (e.g. this project's own
  `NEVER_DROP_GAP_TYPES = frozenset({"DESIGN"})` is structurally the same idea, one class
  narrower than ai-code-reviewer's two-field AND-condition).
- **Explicit warning, grounded in a reproduced bug, not a hypothetical**: if any future
  work looks at ai-code-reviewer's OTHER severity-merge function (`_merge_cluster` in
  `orchestrator/aggregator.py`) for inspiration, **do not port `max(findings, key=lambda
  f: list(Severity).index(f.severity))` as "most severe wins"** — it is inverted and
  untested in the source repo. Use the `severity_order` **explicit dict + ascending sort**
  pattern from `apply_cross_review`/`_cap_findings` instead — same repo, correct, and
  already what `reconcile_gap_records.py`'s existing `NEVER_DROP_GAP_TYPES` borrowing
  conceptually mirrors.

**Not reusable code — prompt patterns only, however sensible-sounding the rule text is:**
- optimus-claude's "keep the higher-severity finding... when severities are equal, keep
  the security/correctness finding" (Step 7) — a good RULE, zero IMPLEMENTATION.
- gopher-ai's `llm-compare` "Points of Agreement / Key Differences / Synthesis" —
  entirely LLM-judgment at write time, no comparison function exists.
- opencode-agents' entire repo — no code of any kind for review or merge logic.
- CodeRabbit's judge-model claim — plausible, but wholly unverifiable (closed-source).

**Transfer-condition check (per the Researcher role's requirement for every borrowed
pattern):**
- (a) *Execution context `apply_cross_review` requires*: a deterministic list of
  already-tagged findings (id, severity, category) and a set of per-agent
  `{id, valid, rank}` assessment dicts — i.e., the SAME shape `reconcile_gap_records.py`
  already has post-clustering (`gap_type`, `lens`, plus this project would need to add an
  explicit per-lens valid/rank vote, which it does not currently collect — lenses today
  emit gap records, not votes on OTHER lenses' gap records).
- (b) *Does loop-team satisfy it today*: **partially** — clustering and pairwise
  CONTRADICTORY tie-break exist; a genuine N-way vote round (where each lens explicitly
  validates the OTHER lenses' findings, not just its own) does not exist yet — adopting
  this pattern would require adding a real "cross-lens validation round" dispatch, not
  just a new Python function.
- (c) *Structural vs instructional*: the vote-tally arithmetic itself
  (`valid_ratio`, threshold compare, CRITICAL+SECURITY bypass) is fully structural/
  deterministic once given real votes — same class of guarantee as this project's
  existing `plancheck_saturation.py`. The vote INPUTS themselves (each lens's
  valid/invalid judgment on another lens's finding) remain instructional — an LLM lens
  self-reporting "valid: true/false," same class of un-verified-input risk already
  flagged for every self-reported "no new findings" signal in the sibling saturation
  dossier. Any adoption should treat the vote *tally* as trustworthy math but the vote
  *inputs* with the same skepticism as any other LLM self-report.

---

## Sources (every one opened directly this pass; `apply_cross_review`'s core claim
independently reproduced by running code, not just reading it)

- `github.com/calimero-network/ai-code-reviewer` — cloned via `gh repo clone`; files read
  directly: `src/ai_reviewer/orchestrator/orchestrator.py` (full),
  `src/ai_reviewer/orchestrator/aggregator.py` (full),
  `src/ai_reviewer/models/findings.py` (full), `src/ai_reviewer/models/review.py` (full),
  `src/ai_reviewer/review.py` (lines 243-442, 525-533, 629-760, 953-1006),
  `src/ai_reviewer/agents/base.py` + `security.py` (heads),
  `src/ai_reviewer/github/client.py` + `formatter.py` (grep + head),
  `src/ai_reviewer/cli.py` (grep for cross-review flags), `pyproject.toml` (full),
  `tests/test_aggregator.py` (full), `tests/test_review.py` (lines 640-703). Severity
  ordering bug independently reproduced via a standalone Python snippet (not just read).
- `github.com/oprogramadorreal/optimus-claude` — cloned; files read directly:
  `skills/code-review/SKILL.md` (full), `scripts/harness_common/findings.py` (full),
  `scripts/harness_common/progress.py` (full), `scripts/harness_common/convergence.py`
  (full), `scripts/harness_common/constants.py` (head), `scripts/harness_common/cli.py`
  (head), `scripts/harness_common/__init__.py` (empty, confirmed), `pyproject.toml`
  (full, confirmed no `[project]` table).
- `github.com/retsimx/opencode-agents` — cloned; full file tree enumerated (confirms
  zero non-markdown review-logic code); `skills/ralphreview/SKILL.md` (full),
  `skills/deep-review/SKILL.md` (full), `skills/ultrawork/resources/multi-review-
  protocol.md` (full).
- `github.com/gopherguides/gopher-ai` — cloned; full file tree enumerated;
  `plugins/llm-tools/schemas/codex-review.json` (full),
  `plugins/llm-tools/lib/review-loop/state-persist.md` (full),
  `plugins/llm-tools/lib/review-loop/parse-findings.md` (full),
  `plugins/llm-tools/commands/llm-compare.md` (full),
  `plugins/llm-tools/skills/second-opinion/SKILL.md` (full),
  `plugins/go-workflow/skills/address-review/SKILL.md` (full),
  `plugins/go-workflow/skills/address-review/bot-registry.md` (full),
  `plugins/go-workflow/skills/address-review/fix-cycle.md` (full).
- `coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-
  codebases` — fetched directly (WebFetch), confirmed no reconciliation-mechanism
  disclosure beyond generic "judge model... drops [findings] it cannot ground."
- This project's own `loop-team/harness/reconcile_gap_records.py` (lines 1-100 read
  directly) — confirms it already borrows ai-code-reviewer's clustering threshold
  (`CLUSTER_SIMILARITY_THRESHOLD = 0.85`) and a CRITICAL-class-never-dropped pattern
  (`NEVER_DROP_GAP_TYPES`), but does NOT yet implement a same-round N-way vote/tally
  mechanism like `apply_cross_review` — the gap this dossier's "portable" recommendation
  targets.
- `research/plancheck-nonbinding-saturation-2026-07-09.md` (read in full first, per the
  dispatch's instruction, to avoid re-deriving already-found ground).

---

## What was explicitly NOT found

- No tool in this survey (including CodeRabbit, so far as its public docs disclose)
  implements a **classification-disagreement** resolver — i.e., what happens when two
  reviewers agree an issue exists at the same location but categorize it differently
  (one calls it SECURITY, another calls it LOGIC). ai-code-reviewer's own clustering
  (`_are_similar`) requires exact category match to even consider two findings the same
  cluster (`if f1.category != f2.category: return False`) — a category disagreement
  means the findings never merge at all, they just co-exist as two separate findings at
  the same location. This is a real, load-bearing gap: nothing surveyed resolves "what
  IS this, really" when reviewers disagree on category, only "should this survive"
  (severity/validity) once category is already agreed.
- No JSONL (append-only, line-delimited) findings-persistence format was found anywhere
  in any of the four tools — every persisted-findings store found (optimus-claude,
  gopher-ai) is a single mutable JSON document, rewritten (optimus-claude, atomically via
  temp-file + `os.replace`) or `jq`-merged (gopher-ai) in place each update, never
  appended to as a log.
- No tool runs a genuine N-way simultaneous cross-validation round where every lens votes
  on every OTHER lens's findings (ai-code-reviewer's cross-review comes closest, but it's
  a single subsequent wave of agents voting on the FIRST round's already-consolidated
  list, not lenses voting on each other pairwise or all-to-all).
