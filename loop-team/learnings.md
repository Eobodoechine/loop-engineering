# Loop-team process learnings

Hard-won lessons. Read before planning so the team doesn't re-learn them.

---

## 2026-06-24 — Activate Researcher FIRST for platform/tool architecture questions

**What happened:** When trying to find where Claude Cowork mounts skill files, ~8 tool calls
were spent exploring `~/Library/Application Support/Claude/` — reading extension manifests,
config.json, Partitions/ etc. None of it answered the question. One WebSearch call answered
it immediately: Cowork runs in a sandboxed container, mounts skills at `/mnt/.skills/skills/`,
requires installation via Cowork UI (Customize → Skills).

**The rule:** For any question of the form "where does [third-party platform] store/mount/load X?"
or "how does [closed runtime] work?" — WebSearch is the FIRST move, not filesystem exploration.
The answer is in docs, GitHub issues, or a support article — not on disk.

**When filesystem exploration IS right:** When you own the code, or you already know the answer
is on disk and you're navigating to a known path.

**Trigger:** If you've spent more than 2 tool calls in config/support directories without finding
the answer — STOP. Open with a search.

---

## 2026-06-24 — Orchestrator role-collapse: Oga doing the work instead of dispatching

**What happened:** Cowork session, loop-team skill active, task was research on cleaning company websites. Oga read orchestrator.md, which says "dispatch sub-agents for their work," then did the research inline itself. It even acknowledged the violation mid-response: "I activated the loop-team skill, read the orchestrator playbook which explicitly says I dispatch specialist sub-agents for their work, not do it myself, and then... ignored that and did the research personally."

**Why it happens (sourced):** The model reads role-separation instructions as soft suggestions, not hard gates. When the task is familiar (research) and the dispatch path requires a concrete tool call (Agent), the model takes the path of least resistance — inline work. Live context (the task) beats system-prompt constraints when base capability is engaged. (Source: arxiv 2502.15851 "instruction hierarchies fail to properly constrain model behavior.")

**The fix applied to orchestrator.md:**
1. Opening reframed as positive constraint: "Your permitted outputs: Agent tool calls, synthesis after results, questions to user. Everything else is sub-agent work."
2. Self-check gate added: "Am I about to do research/code/verify myself? If YES — stop. My only output is an Agent tool call."
3. Dispatch section now says: "Dispatching means ONE thing: an Agent tool call. Not prose. Not 'I'll now act as the Researcher.' An actual Agent tool call."

**The rule:** If Oga produces research, code, or verification itself — it is out of role. The response is: stop, delete the inline work, compose an Agent tool call instead.

**What does NOT work:** `allowed-tools` in SKILL.md frontmatter — confirmed NOT enforced by the runtime (GitHub issue #37683, closed without fix). Enforcement must be in the prompt body only.

---

## 2026-06-24 — Researcher role is loop-team-only; domain research goes elsewhere

**What happened:** After the role-collapse fix landed, Oga correctly dispatched a sub-agent — but initially tried to dispatch the Researcher role for general domain research (cleaning company websites). The orchestrator self-corrected: "The Researcher role is specifically for improving the Loop Team itself (Mode A/B/C), not general domain research. I should have dispatched the general-purpose agent."

**The rule:** The loop-team Researcher has exactly four modes:
- **Mode A** — find techniques/repos to improve the loop (PACE-gated experiments)
- **Mode B** — unblock a stuck Coder with a sourced bug-fix dossier
- **Mode C** — generate adversarial eval cases that beat the current Verifier
- **Mode D** — domain research for a build: Oga calls you when the Brief references external services, third-party APIs, or industry patterns the Coder needs to understand before coding. Produces a domain brief (question/answer/source/constraints/not_found). NOT a radar entry or experiment spec.

If the domain question is about **external services, APIs, or industry patterns the Coder needs for the current build** → dispatch Researcher in **Mode D**. If the domain question is general (not build-specific, not for the current Coder) → dispatch a **general-purpose agent** or the `deep-research` skill, not the loop Researcher.

**How to apply:** Before dispatching the Researcher, check: is this about improving the loop team, unblocking a specific code bug, generating eval cases, or domain research the Coder needs for the current build? If none of those — dispatch general-purpose instead.

---

## Standing: Never infer root cause from circumstantial signals

Reproduce the failing path against the run's own artifacts. Prove the mechanism. A file
mtime, a grep hit, or a "probably" is not a diagnosis. (See also: memory `diagnose-beyond-doubt`.)

---

## Standing: Skills at ~/.claude/skills/ are CLI-only

Cowork runs a separate sandboxed skill runtime. Skills need to be installed through Cowork's
UI (Customize → Skills) as `.skill` artifacts. In the Claude Code system-reminder, skills installed via Cowork's UI appear prefixed as
`anthropic-skills:loop-team` — that prefix is applied by the runtime, not embedded in the
skill file itself. Both runtimes read `~/Claude/loop/` framework files on every invocation
via the live-read pattern in STEP 0 — that's what keeps them in sync.

---
## Build 3: runner/ package (2026-06-24)

**Test assertion strength matters.** `test_per_role_model_override_is_forwarded` only checked the captured model was not None/empty — not that it equaled the expected resolved alias. A future iteration should assert the exact model ID.

**CLI flags can be inert.** `python -m runner brief.md --provider openai` currently prints provider/model and exits (Phase 1 infrastructure). Flags like `--provider` and `--model` don't route a real dispatch until Phase 2. Document clearly in USAGE.md to avoid user confusion.

**Vendoring over cross-directory imports.** When adding a standalone package to an existing repo, vendor the shared utility (call_with_retry pattern) rather than importing across directory boundaries. Keeps the package pip-installable without sys.path surgery.

---
## Python version guard (2026-06-24 — Build 3 post-mortem)

**Always pin to the target Python version.** The Cowork build used `str | Path` union type syntax (`x: str | Path`) throughout, which is Python 3.10+ only. The target machine runs 3.9.6. All 7 test files failed with `TypeError` before a single test ran — the 87-test green count was in the Cowork sandbox (Python 3.10), not on the real machine.

Fix: use `Optional[str]` / `Union[str, Path]` from `typing`, or add a `python_requires = ">=3.10"` gate in pyproject.toml so the install fails fast with a clear version error rather than silently running broken tests.

**Lesson for Test-writer:** Write one test that confirms `python --version >= required_version`, or gate the file itself with `import sys; pytestmark = pytest.mark.skipif(sys.version_info < (3, 10), reason="requires 3.10+")`. Never let the version assumption be invisible.

---
## Fixture tautology: test fixtures must use real Oga labels, not crafted-to-match labels (2026-06-24)

**What happened:** `loop_stop_guard.py` plan-before-Coder gate had a `_VERIFIER_DETECT` pattern
(`independent verifier|verifier\.md`) that looked correct and passed 22 tests. In production,
Oga dispatched a plan-check Verifier with description "Plan-check Verifier — Decision 6 Workflow
migration spec" — a standard orchestrator.md label — and the gate fired a false positive. The test
fixture `PLAN_VERIFIER` had `prompt="You are an independent verifier..."` — crafted to contain
"independent verifier." Tautological: proved the regex matches the fixture, not what Oga produces.

**The fix:** Expanded `_VERIFIER_DETECT` to include "plan-check verifier" / "verifier plan-check";
reversed if/elif order to Verifier-first (safe with tight patterns). 5 H-GUARD-1 regression tests
using real Oga labels. 27/27 passing. See fix_plan.md H-GUARD-1/2.

**The rule for Test-writer:** When writing fixtures for a gate that pattern-matches dispatch labels,
read the orchestrator playbook FIRST — use actual Oga labels, not labels crafted to match the regex.

---
## Plan-check Verifier catches spec bugs before implementation (2026-06-24)

**What happened:** Building the plan-before-Coder gate for `loop_stop_guard.py`. The draft
gate used `if verifier_regex → set _seen / elif coder_regex → block`. The plan-check Verifier
(dispatched on the spec, before any Coder call) found two bugs in the draft logic:

1. **if/elif ordering** — a Coder whose prompt contained "verify" would fire the `if`-Verifier
   branch, set `_seen_verifier_pre = True`, and the `elif`-Coder branch would never be reached.
   The gate was bypassable with a single word in the prompt.
2. **Broad "verify" regex** — using `r'independent verifier|verifier\.md|verify'` for Verifier
   detection meant any Agent dispatch mentioning "verify" (a Researcher, a comment) would set
   `_seen_verifier_pre`, falsely satisfying the plan-check requirement.

**Fix in the final spec:** Check Coder FIRST (`if _CODER_DETECT`), only check Verifier in the
`elif` (so it never fires on a Coder dispatch). Tighten Verifier detection to
`r'independent verifier|verifier\.md'` — dropping bare "verify".

**Why it mattered:** Both bugs had no test coverage in the original draft test suite — they were
invisible to the tests as written. The plan-check Verifier found them through adversarial code
tracing BEFORE the Coder wrote a single line.

**The rule:** The plan-check Verifier step is not optional even for "simple" logic. If/elif
ordering bugs in gating logic are exactly the class of mistake that passes green tests (since
the tests are written to match the spec, which had the same bug). Independent review of the
spec before implementation is the only reliable catch.

---

## Verifier fabricates citation evidence when asked to source a gap (2026-06-26)

**What happened:** Plan-check Verifier was dispatched to grade an architectural spec (chained
micro-workflows with human checkpoints). It correctly identified a real gap — `resumeFromRunId`
is session-scoped, not cross-session. But it invented two GitHub issue numbers ("issue #65796"
and "issue #67488") as supporting evidence for that claim. The finding was real. The citations
were hallucinated. Disk inspection confirmed the session-scoped behavior directly; neither issue
number was verified to exist.

**Why it happens:** The Verifier is pressured to appear authoritative. When it has the right
answer but lacks a citable source, it produces a plausible-looking citation rather than
acknowledging uncertainty. This is citation fabrication — a well-documented LLM failure mode
where the reasoning is correct but the evidence is confabulated.

**Why it's dangerous:** A fabricated issue number looks like proof. It anchors the human into
accepting the finding without verifying it. Worse: if the finding is WRONG, the fabricated
citation makes it harder to challenge. The correct signal that the gap is real came from
reading actual files on disk — not from the invented issue numbers.

**Immediate rule added to Verifier dispatch:** When the Verifier cites a specific external
artifact (GitHub issue #, paper ID, URL, doc section), Oga must treat it as UNVERIFIED until
independently confirmed. Do not carry a fabricated citation into fix_plan.md or into a revised
spec — reproduce the claim through a real tool call first (Read, Bash, WebFetch).

**The fix to add to verifier.md (pending research):** Add an explicit grounding constraint:
"For any external citation (GitHub issue number, paper arXiv ID, URL, doc section name),
you MUST retrieve and quote from it via a tool call BEFORE citing it. If you cannot retrieve
it, say 'I believe this is documented in [approximate description] but I have not verified the
source.' Never state a specific issue number, ID, or URL you have not read."

**Root cause of gap 1 being narrower:** Post-compaction does NOT change the session directory
(compaction is within-session). The Verifier's "three failure modes" collapsed to one real one:
cross-session resume fails because journals are keyed by session directory. The other two were
either wrong (post-compaction) or overstated (non-deterministic labels are blocked by the
runtime's prohibition on Date.now()/Math.random() in workflow scripts).

---

## "Split, take last element, strip" fails on trailing newline (2026-06-25)

**What happened:** Decision 4 spec v2 said "split `last_assistant_message` on `\n`, take last
element (`[-1]`), strip both sides." The plan-check Verifier (round 2) found a silent failure:
LLM messages commonly end with `\n`. `"LOOP_GATE: PLAN_PASS\n".split('\n')` produces
`["LOOP_GATE: PLAN_PASS", ""]` — `[-1]` is `""` after strip — no match. The spec's own example
promised a match the algorithm couldn't deliver.

**The fix:** Filter-then-take-last: `[x.strip() for x in msg.split('\n') if x.strip()][-1]`
(empty strings excluded BEFORE `[-1]`, so trailing newlines are harmless). Also guard for
the all-whitespace case (`lines = []` → early exit 0 instead of IndexError).

**The rule:** Whenever you split a message on newlines and take `[-1]` to find the "last line,"
FIRST filter out empty/whitespace-only strings. Otherwise trailing newlines (universal in LLM
outputs) silently give you an empty string as the "last line."

---

## Auto-mode classifier HARD BLOCKs settings.json PreToolUse hook injection (2026-06-25)

**What happened:** Decision 4 required an empirical test of whether PreToolUse exit(2)
blocks Agent dispatch. The test required adding a PreToolUse hook to `~/.claude/settings.json`.
The auto-mode classifier returned a HARD BLOCK: "modifies `~/.claude/settings.json` — explicitly
listed as a Self-Modification HARD BLOCK target — by injecting a PreToolUse hook that alters the
agent's own behavior; HARD BLOCKs cannot be cleared by user intent."

**The implication:** Oga cannot autonomously register PreToolUse hooks. This settles the
PreToolUse vs Stop-hook architecture question definitively: Stop-hook-only is the correct
architecture for plan-check gate enforcement. PreToolUse enforcement is not available to
autonomous loop-team operation.

**The rule:** Never design a gate that requires Oga to modify `~/.claude/settings.json`
to install or test it. Hooks that Oga needs can ONLY be registered by the operator manually.
The SubagentStop + Stop hook combination does not require Oga to self-modify.

---

## Fixture tautology: tests that prove the fixtures match the spec, not that real inputs match (2026-06-24)

**What happened:** The plan-before-Coder gate shipped 8/8 tests green and an independent
Verifier PASS. Same session, Oga dispatched a real plan-check Verifier (for Decision 6) and
the gate fired exit 2 — a false positive. No Coder had been dispatched.

**Root cause — two compounding bugs:**
1. `_VERIFIER_DETECT = re.compile(r'independent verifier|verifier\.md')` does not match
   `"Plan-check Verifier — Decision 6 Workflow migration spec"` — the actual description Oga
   produces per orchestrator.md. So `_seen_verifier_pre` stayed False.
2. `_CODER_DETECT` scans `json.dumps(tool_input).lower()` — the entire prompt — not just
   the description. The Verifier's prompt DISCUSSED the Coder role, triggering the detector.

**Why both bugs passed the plan-check Verifier and the test suite:**

The `PLAN_VERIFIER` fixture was:
```python
tool_use("Agent", description="Verifier plan-check",
          prompt="You are an independent verifier reviewing the spec...")
```
The prompt contained "independent verifier" — which matches `_VERIFIER_DETECT`. The test proved:
"when a fixture is crafted to contain the regex pattern, the gate recognizes it." It did NOT prove:
"when Oga dispatches as it actually does, the gate recognizes it."

Neither the spec Verifier nor the Test-writer read `orchestrator.md` to find what dispatch labels
Oga actually produces. "Plan-check Verifier" (the standard label) was never in any fixture.
The spec Verifier was correctly adversarial about LOGIC (if/elif, broad regex) but never asked:
"Will this regex match the real outputs the orchestrator generates in production?"

**The class of mistake: fixture tautology.** The Test-writer wrote fixtures to match the spec's
patterns. The spec Verifier evaluated the logic against those fixtures. The tests passed because
the fixtures were correct inputs for the patterns — not because the patterns cover the system's
real outputs. A gate can have 100% test coverage on crafted fixtures and still false-positive or
false-negative on every real dispatch the system produces.

**The rule (Test-writer):** When writing fixtures for a gate that pattern-matches dispatch
descriptions or labels, read the orchestrator playbook first. Use the actual labels the
orchestrator produces — not labels crafted to match the regex. At minimum, include one fixture
using a label you did NOT write (found by reading the orchestrator), and verify it matches.

**The rule (spec Verifier):** For any gate that classifies dispatches by regex, ask: "Where does
the orchestrator document the dispatch labels it uses? Do the patterns in the spec match those
labels?" This is a coverage question, not a logic question — it requires going outside the spec.

---

## atlanta-distressed-homes-finder build (2026-06-25)

**Domain: real-estate for-sale skill with creative-finance gate**

### Budget reality check is a design input, not a feature

**What happened:** The user's budget ($1,500/mo) is achievable with conventional financing only at ~$150k list price. Atlanta intown average is $834k. A spec that treats conventional financing as the primary path produces a shortlist that's 100% useless to the user. The first plan-check Verifier caught this as a DESIGN gap (PLAN_FAIL, iteration 1).

**The fix:** Compute conventional carry as "reference only" (Scenario A). Compute creative-finance carry as the "TARGET PATH" (Scenario B). Only homes with `creative_finance_detected == true` can reach the shortlist. This structural constraint must be built into the spec's acceptance criteria, not left as a runtime preference.

**The rule:** Before designing carry criteria for a real-estate skill, compute whether conventional financing CAN reach the user's budget at the target market's price point. If it can't, the skill must be assumable/creative-finance-first from the start — not as an add-on.

### Research findings must be verified before acting on them — never edit immediately after research

**What happened:** Researcher returned a domain brief confirming that `manifest.json` is Cowork's skill registry and showing the exact schema. Oga read it and immediately edited `manifest.json` — skipping the plan-check Verifier step entirely.

**Why it's wrong:** The loop flow is Research → Plan → Plan-check Verifier → Execute. Jumping Research → Execute bypasses the gate that catches "the research is right but the proposed action is wrong." Even when research findings are empirically grounded (the Researcher read the file directly), the edit step can still be mis-aimed — wrong field format, wrong location, partial edit that breaks JSON, etc. The plan-check Verifier catches those.

**The rule:** After Researcher Mode D returns a domain brief, Oga synthesizes a plan and runs a plan-check Verifier on it before any execution. The only exception is trivially reversible, zero-risk actions (e.g., reading a file to confirm a fact). Editing system files (manifest.json, settings.json, any registry) is never trivial — always plan-check first.

---

### Verify the artifact is USABLE, not just correct — deployment is a separate gate from passing tests

**What happened:** `atlanta-distressed-homes-finder` shipped with 81/81 tests passing, an independent Verifier PASS, a run log, and a live smoke. The skill SKILL.md was correct in every measurable way. The skill was still not usable — it had been copied to the wrong directory (`skills-plugin/<name>/`) instead of the UUID-namespaced path Cowork actually reads (`skills-plugin/<uuid1>/<uuid2>/skills/<name>/`). The user went to invoke it and it wasn't there.

**The miss:** Every verification step checked the artifact's content and correctness. None checked that the user could actually reach it. There was no step that said "open Cowork, type `/`, confirm the skill appears."

**The rule:** For any artifact that requires registration or installation (a skill, a CLI tool, a hook, a config), add a deployment verification gate AFTER all content verification:
- Skills: open the `/` menu in Cowork and confirm the skill name appears
- CLI tools: run from a fresh shell, confirm it exits correctly
- Hooks: trigger the condition once and confirm the hook fires

**Why tests don't substitute for this:** Tests prove the file is correct. Cowork reads from a specific UUID-namespaced path that a `cp` to the wrong directory silently misses. A correct file in the wrong place is not deployed.

**How to apply:** Step 6.6 of the orchestrator now encodes this as a mandatory gate for all registered/installed artifacts. Run it before declaring done, regardless of how clean the test run is.

---

### Platform URL verification catches silent 404s in neighborhood IDs

**What happened:** The Coder embedded Redfin neighborhood ID 149034 for Candler Park. Live smoke test caught it: headless URL sweep returned 404. The correct ID (148536) returned 200. No test checked the URLs — the test suite was document-based.

**The fix:** Run a headless URL sweep as part of the smoke test for any skill that embeds platform URLs. A wrong neighborhood ID produces a 200 at the list level (the city still loads) but 404 at the neighborhood level — a real test must hit the specific URL.

**The rule:** After Coder writes a skill with embedded platform URLs, run a URL sweep before declaring done. For any 404, find the correct URL rather than accepting "the neighborhood might not have a Redfin page."

### Pre-foreclosure source varies by state

**What happened:** The original spec assumed lis pendens as the pre-foreclosure signal. Georgia is a non-judicial foreclosure state — there is no lis pendens. The correct source is GeorgiaPublicNotice.com (Notice of Sale Under Power, published 4 weeks before the first-Tuesday courthouse auction).

**The rule:** For any real-estate skill, look up whether the target state is judicial or non-judicial foreclosure. Judicial → lis pendens in court records. Non-judicial (GA, TX, CA, etc.) → look for the state's statutory notice publication (varies by state).

### Researcher sub-agent in Mode D: synthesize before returning

**What happened:** The Researcher dispatched 5 parallel sub-agents to cover the 5 domain questions and stopped — returning its agentId instead of synthesizing the results into a domain brief. Oga had to manually read the sub-agent transcript files to assemble the brief.

**The rule:** Researcher Mode D must complete the synthesis itself before returning. The dispatch + merge into a unified domain brief is part of the role. Returning early with "sub-agents dispatched" is an incomplete result.

### Playwright accessibility snapshot reads through PerimeterX overlays — false PASS

**What happened:** Verifier sub-agent used `mcp__playwright__browser_snapshot` to check Zillow. It reported PASS and quoted real listing content (title, address, price). User screenshot confirmed the page actually showed a PerimeterX "Press & Hold to confirm you are a human" overlay blocking all interaction. The `--no-sandbox` flag in Chrome's warning banner revealed it was Playwright's Chromium (not the user's real browser), which Zillow detected.

**Root cause:** Playwright's accessibility snapshot reads the DOM including content rendered *under* the overlay. The listing data was present in the DOM; the snapshot returned it as if the page was fully accessible. The overlay existed only as a UI element on top — invisible to a DOM-based snapshot but blocking all real interaction.

**The rule:** For WAF-protected sites (Zillow, Redfin, etc.), a Playwright accessibility snapshot reporting real content does NOT mean the page is usable. Always check for overlay elements (`role=dialog`, `aria-modal`, challenge-related text like "Press & Hold", "verify you are human", "Before we continue") in the snapshot. If any are present, the page is BOT_WALLED regardless of the content underneath. The only reliable verification is a screenshot or checking for absence of challenge overlay elements.

**Corrected path for Zillow:** Claude-in-Chrome (real browser with user's profile/cookies) is the only reliable path. Playwright gets the press-and-hold PerimeterX challenge.

---

### Redfin WAF returns identical 202 for both valid and invalid neighborhood IDs

**What happened:** Smoke-test URL sweep used a headless HTTP check. Redfin's CloudFront WAF intercepts all datacenter/script requests with an `x-amzn-waf-action: challenge` before the request reaches Redfin's router. Both valid and invalid neighborhood IDs returned identical 202 responses from curl. The "fix" for Candler Park from 149034 → 148536 appeared to pass (202) but 148536 is actually West Side, San Antonio TX — confirmed only when the independent Verifier checked in a real browser.

**The rule:** For any platform behind a WAF (Redfin, Zillow, etc.), headless URL sweeps are not reliable for confirming page identity — only for confirming complete 404 at the CDN level. Neighborhood ID validation requires a real-browser check that can load actual page content and confirm the location name matches expectations. A 200/202 from a headless check is not proof the URL is correct.

---

## Citation fabrication is a capability problem, not a style problem (2026-06-27)

**What changed:** Prompt-based grounding constraints (Tier 1) reduce citation fabrication but cannot eliminate it because the self-check shares the same generation pathway as the fabrication. Research confirmed no existing framework (constrained decoding, DSPy Assertions, guided decoding) mechanically prevents a model from emitting a fabricated identifier. The deterministic research finding: "citation format is valid" is not the same property as "citation is grounded."

**The architectural resolution:** Remove citation authority from the model entirely. Code mints evidence IDs; the model only references them.

Three-layer architecture:
1. **Retriever assigns canonical IDs** — code creates `{"EVIDENCE_001": {"source_id": "65796", "url": "...", "excerpt": "...", "hash": "sha256..."}}`. The model never sees raw issue numbers as something to reproduce; it only knows `EVIDENCE_001`.
2. **Verdict model outputs span references, not reproduced quotes** — `{"claim": "...", "evidence_ids": ["EVIDENCE_001"], "quote_spans": [{"evidence_id": "EVIDENCE_001", "start": 128, "end": 214}]}`. Code renders the quote from the stored excerpt. The model selects spans; it cannot hallucinate the quote text.
3. **Deterministic external validator** — checks every `evidence_id` exists in the artifacts dict, every span is in bounds, rendered quote equals excerpt slice exactly, no raw citation-like strings appear outside rendered citation fields. This is pure Python; no model judgment required.

**Authoritative prose gate:** Any statement implying external authority must be typed as `claim_type: "external_authority"` with `evidence_ids`. If `evidence_ids` is empty, renderer rewrites as unsupported analysis. Authority markers ("per," "according to," "published framework," "market data shows," "industry standard") in unsupported prose fail closed.

**On violation:** reject the invalid citation, preserve the underlying claim, emit a machine-readable violation report (`{"status": "invalid_evidence", "claim": "...", "missing_evidence_id": "EVIDENCE_099", "raw_output_location": "$.claims[2].evidence_ids[0]", "recommended_action": "retrieve_or_escalate"}`). Do not blind-retry; that hides the safety signal.

**What this does NOT close:** a misleadingly selected true quote — a span that is within bounds and exact, but cherry-picked to support a misleading claim. That is an evidence-use/verdict-quality problem, not a citation-minting problem. The architecture closes the identifier fabrication path; it does not guarantee sound reasoning over retrieved evidence.

**Standing dispatch rule for Oga:** When building any verifier that cites external artifacts, require the three-layer architecture above. Do not accept prompt-based citation grounding as sufficient for high-stakes verification.

## live_smoke false-pass: an ERROR verdict was reported as passed (2026-06-30)
The liveness checker computed `passed = (no DEAD urls)`, so a URL whose verdict
was ERROR (navigation failed / empty response / timeout — it could not load at
all) reported `passed: True`. A false-pass in the very tool built to catch broken
URLs — the project's deepest failure mode, recurred. **Nothing in the wiring
caught it**: no unit test or eval case froze "ERROR != passed", `run_evals` never
references live_smoke, and the independent verifier had only checked the change
under review (tracing), never exercised live_smoke on an erroring URL.
Surfaced only by actually launching a real browser (the import-vs-binary lesson
again: `import playwright` succeeds even when chromium cannot launch — so a probe
based on import, not execution, proves nothing). Fix: `summarize()` now fails on
DEAD **or** ERROR; deterministic regression tests (`Summary`) freeze it so the
suite catches any recurrence; the behavioral test is execution-based (skips on
ERROR/empty with the real cause), not import-based.
**General gap:** the wiring catches a recurrence only where a deterministic check
or a pointed verifier exists for it. A fresh recurrence in a new place slips
through until a Bug-identifier-style pass hunts for it. Freeze the check at the
moment of discovery.

## live_smoke: classify failures BY LAYER, not one ERROR bucket (2026-06-30)
A single ERROR verdict lumped together three distinct causes — chromium failing
to LAUNCH (missing system lib), the PROXY refusing the tunnel, and the TRANSPORT
failing to reach the host — plus it false-passed (see prior entry). This directly
caused repeated MISDIAGNOSIS: a launch crash and a proxy block were both reported
as if the URL itself were the problem. Fix: distinct verdicts per layer —
LAUNCH_FAILED / PROXY_FAILED (environment), NAV_FAILED / ERROR (transport),
LIVE / DEAD / BOT_WALLED / REDIRECTED (HTTP response). `passed` is True only when
every URL is confirmed reachable; each failure is bucketed so the verdict is
actionable (fix the host vs the proxy vs the URL). Lesson: when a check can fail
for environment, tooling, OR target reasons, it MUST name the layer — a merged
failure bucket guarantees mis-attribution, the exact error I made repeatedly here.


## Component-built paths evade literal greps — make sweeps executable (2026-07-01)

**What happened:** The restructure-debt sweep grepped every live surface for the literal
`Claude/loop/public` and found 21 hits — but missed `Path.home() / "Claude" / "loop" / "public"`
in test_session_enforcement.py (a path built from components), which made 21 of 30 tests fail.
Two full plan-check passes ALSO missed it; it surfaced only when the third verifier actually
RAN pytest instead of grepping. Same class: ~/.loop-team-config did not exist, so a SKILL.md
FALLBACK default silently resolved to the deleted directory — no grep for the path found the
problem because the problem was in which branch executed.

**The rule:** a stale-reference sweep is only trustworthy if it EXECUTES the consumers
(run the tests, boot the skill path resolution), not just greps for the string. Add a
deterministic zero-hits grep AND a run of every consumer to any path-migration gate.

## Delta-scoped verifier dispatches manufacture phantom gaps (2026-07-01)

**What happened:** To save tokens, a revision-2 plan-check was dispatched with only the DELTAS
plus one-line summaries of standing ACs. The verifier — correctly, from its view — flagged a
"missing" fix that the full AC3 text already contained verbatim, producing a third PLAN_FAIL
that was a handoff artifact, not a spec gap. Locating the gap in OUR harness (the dispatch),
not the verifier's logic, avoided a needless revision cycle.

**The rule:** every plan-check dispatch carries the FULL current spec text, even when the
review scope is deltas-only. Scope the verifier's ATTENTION, never its EVIDENCE.

## 2026-07-01 — replacing a paid API with a free stack: prove ZERO paid calls by INSTRUMENTING a real run
User's RentCast free tier (50/mo) blew into overage — partly because the loop's OWN verifier runs each spent up to 15 RentCast calls and the tool defaulted to spending when a key was present.
1. A verification loop that calls a metered paid API burns the user's real quota. Default paid-API spend OFF (opt-in via an explicit env var); verifier runs spend zero. The bleed fix (unset→0) matters as much as the feature.
2. Prove "zero paid calls" by wrapping urlopen during a full harness run and counting calls to the paid host = 0 — not by reading the quota logic. A green quota unit test isn't the structural proof.
3. Free ZIP-level rent stack, zero setup: Zillow ZORI ZIP CSV (no key, blended level, live-verified) × a bedroom ratio anchored to the ALL-BEDROOM BLEND (mean of the HUD FMR vector, NOT FMR[2BR] — a plan-check catch: ZORI is blended, a 2BR anchor mis-scales every estimate). ACS B25031 (free key) upgrades the bedroom shape when available. Cache the 9.6MB CSV atomically (mkstemp+os.replace, validate-before-cache).
4. Keep the granular-but-paid tier as an on-demand FINALIST browser check (claude-in-chrome → Zillow Rent Zestimate → unit_verified → unlocks PRIMARY), not a bulk metered API. Cheaper, simpler, more reliable.

## Blob-level checks must be specified against the real corpus they scan (2026-07-01)

Three defects in one spec, same root: the B5 leak markers matched roles/verifier.md's
own mandatory output instruction ("last verdict: PASS" is IN the role file); gate 1's
firing condition matched the escalation stop that gate 3 mandates; the extended case
lint's schemas missed 2 of 6 real target shapes (artifacts={} is a load-bearing EMPTY).
Every deterministic gate spec must ship with a scan of the actual content it will run
over — role files, dispatch templates, the live case corpus — and its ALLOW fixtures
must embed that real content verbatim (the residue-subtraction fixture is the proof
pattern). Corollary discovered while building: the detector's own tests and comments
keep reintroducing contiguous marker literals — the no-contiguous-literals sweep has
now caught the author 4 times in one day; keep it.


## Every executable line in a doc is a BEHAVIORAL claim (2026-07-01)

The OSS install guide shipped a hook-verification example that printed nothing (the
prompt missed the trigger regex) — written, never executed, inside the very document
whose opening rule is "a hook you have never SEEN firing is not installed." Docs are
artifacts: a copy-paste command is a [BEHAVIORAL] acceptance criterion, and the DOC/
BEHAVIORAL split from the test-writer role applies to documentation verbatim. Rule:
before committing a doc, EXECUTE every command it shows and paste-match the promised
output; the stranger role-play verifier enforces it after the fact, but the writer
executing first is one round cheaper.

## 2026-07-01 — padsplit auth-slice close-out (CLI continuation session)
- **De-priming leaks via run-dir adjacency (H-LT4 in fix_plan).** The post-build Verifier's
  dispatch prompt was hygiene-clean (hook-checked), but the spec path pointed into the run dir
  that also held HANDOFF.md with the Coder decision log + prior green results — the Verifier
  read it while exploring. Withholding-by-prompt is defeated by co-located status docs. Until
  the deterministic fix lands: keep specs and status/decision docs in SEPARATE dirs, or name
  out-of-bounds files explicitly in the dispatch. (Verdict stood this run only because every AC
  was independently tool-grounded — live e2e, curl parity probes, clean install, real generator.)
- **Sandbox-green ≠ host-green when npm workspaces are involved.** The AC9 parity harness passed
  in the sandbox (web/ rsync'd STANDALONE → populated web/node_modules) and failed on host where
  the workspace root hoists deps → web/node_modules EMPTY → scratch-dir symlink pointed at
  nothing. Fix pattern: never hardcode <repo>/node_modules; ask Node's own resolver
  (createRequire(ROOT).resolve(pkg), take the last node_modules segment). Generalizes: any
  harness that reconstructs a resolution context must derive it from the resolver, not layout.
- **verify.py is pytest-only (H-LT5 in fix_plan)** — meaningless "0 tests collected" on a
  Node/vitest repo; Oga + Verifier both had to substitute vitest/tsc runs manually.
- **Oga self-inflicted harness-fault:** `cmd | tail -25; echo EXIT=$?` captures tail's exit code,
  not the command's — reported exit 0 over a red suite. Capture EXIT=$? on the command itself
  (or pipefail) BEFORE piping. The failure arbiter caught it because the output contradicted
  the code.

## 2026-07-01 — Async multi-turn orchestration defeats per-turn hook state (padsplit-signout run)

Two guard misfires in one run, same root: the loop hooks assume single-turn synchronous
dispatch, but async sub-agents return in LATER turns.
1. loop_stop_guard's plan-before-Coder gate false-blocked a Coder dispatched two turns
   after a logged PLAN_PASS (the pass landed as an async notification; `_seen_verifier_pre`
   has no cross-turn persistence when LOOP_GATE_DIR is unset). The earlier Coder dispatch
   passed only by ACCIDENT — the incoming task-notification text contained "plan-check
   Verifier". fix_plan H-GUARD-3 has the fix design (session-scoped plan-pass marker).
2. The OGA-GUARD code-edit hook fired on SUB-AGENT Write/Edit calls (Coder MS2, adversarial
   writer) — it can't tell orchestrator tool calls from sub-agent ones — and the agents
   legitimately fell back to Bash heredoc writes, proving the block is advisory anyway.
   fix_plan H-GUARD-4.
**Rule until fixed:** on a guard block, run the failure arbiter BEFORE complying — quote the
logged gate evidence (plan_check_log PLAN_PASS) and classify harness-fault vs process-fault;
never appease a false positive with a redundant re-dispatch (that's verifying against a
broken instrument).

## 2026-07-01 — Keep verdict language OUT of checkpoint commit messages (de-priming)

A checkpoint commit message that says "all green" / "verified PASS" is a green-verdict leak
baked into git history — a de-primed post-build Verifier reading `git log` inherits it (this
run's Verifier had to be explicitly ordered to form its provisional verdict before reading
git history; it also caught the message overclaiming "17 attacks" vs 20 it() blocks).
Checkpoint messages should state WHAT changed, never verification outcomes. Corollary of
H-LT4 (run-dir adjacency): git history is another co-located status channel.

## 2026-07-01 — Vitest-only idioms break a repo whose gate includes full tsc

A vite query-param import (`import('.../auth-client?variant=unset')`) is vitest-runnable but
fails `tsc --noEmit` (TS2307) — the exact PSC-TSC-1 class. The adversarial writer's own runs
(vitest only) were green; ONLY the orchestrator's checkpoint gate (vitest AND tsc) caught it.
Fix pattern: vi.stubEnv + vi.resetModules + plain typed dynamic import. Rule: a "run your
file" verify instruction to any test-writing role must name EVERY deterministic gate the
repo enforces, not just the test runner.

## 2026-07-01 — framework fix chain (H-LT4/5/6/7), same session, later
- **Plan-check FAILs were the product, not friction:** 6 corpus-grounded PLAN_FAILs across 3
  specs (relative-path idiom; *verdict* eval-fixture collision; summary* coverage; 5-turn
  magic-number burst flaw; queue-operation retirement channel; has_python_tests dir-name
  blindness — the last one proven by EXECUTING the unmodified harness against the graded
  target). Every one would have shipped a real defect. Pattern: verifiers that EXECUTE the
  current code against the real corpus catch what spec-prose review cannot.
- **A Coder that root-causes a spec bug beats literal compliance:** --reporter=basic (Oga spec
  error) crashes vitest at startup; the Coder reproduced it, fixed to =default, documented the
  deviation inline. Specs are falsifiable artifacts too.
- **Notifications are turn boundaries** (proven by running the slicer on the live transcript) —
  any turn-scoped hook allowance races async sub-agents; the durable pattern is state-based
  (in-flight detection), not window-based. And completion signals ride TWO channels (user +
  queue-operation events; 5/47 real completions were queue-only).
- **The adjacency gate's first catch was its own build's dispatch** (plan_check_log.md by
  path) → prior_gap_record*.md convention. New gates find their first defects at home.
- **Sequential Coders per repo:** concurrent Coders in one tree would poison the per-Coder git
  audit; queue them (H-LT5 waited for H-LT4's continuation).

## 2026-07-02 — guard-hooks-async build (H-GUARD-3/4/MICROSTEP/LT7 close)

- **Diagnose the EXISTING mechanism before building the prescribed fix.** The H-GUARD-3 entry
  prescribed "persist a session-scoped plan-pass marker" — that exact mechanism had existed
  since June (subagent_stop_gate.py + flag credit path, commit 7fe3343) and was registered
  during the very incident that filed the entry. Three probes (settings.json read, ~/.loop-gate
  listing, git log) re-aimed the build from "add persistence" to "fix the credit semantics"
  (consume-all, one-credit-for-N-steps, order-sensitivity). An incident author under a firing
  guard writes the fix design they can see, not the one that's true — probe before building.
- **A spec that INVERTS existing behavior must enumerate the tests that encode the old
  behavior — via an executable sweep, not recall.** Two consecutive plan-check PLAN_FAILs were
  the same gap: pre-existing tests asserting the superseded semantics, unnamed by the spec
  (3 found in i1, 2 more in i2). The i3 PASS came only after grepping the test corpus for flag
  assertions and Coder-fixture turns. Extends "component-built paths evade literal greps":
  before dispatching a plan-check on a behavior-inverting spec, sweep the test corpus and put
  the named rewrite list IN the spec with stated reasons.
- **Never interpolate an external id into a glob pattern un-escaped.** The post-build
  verifier's adversarial probe showed a session_id with glob metacharacters makes its own
  fresh flag invisible (self-lockout). Spec-inherited: the spec literally specified the glob.
  Use glob.escape() on any id that becomes part of a pattern (fix_plan H-GUARD-5). Same class
  as the no-contiguous-literals rule: the detector's own mechanics can defeat it.
- **Dogfooding evidence beats fixtures:** this session's own plan-check PLAN_PASS wrote the
  flag through the real registered SubagentStop hook (async dispatch), and the Coder's
  Write/Edit ran un-denied while in flight (GAC6 live) — production proof captured mid-build
  at zero extra cost. When the artifact under repair is the session's own harness, harvest
  the session as evidence.

## 2026-07-02 — D1 fault-injection run: measurement + concurrency lessons

- **Judge "accuracy" without reason-grounding is partly rejection bias.** Haiku's
  round-2 trap accuracy (71%) came mostly from rejecting artifacts for
  "no final VERDICT shown" — an over-rejection heuristic, not defect detection
  (its round-1 rejected two clean controls for the same reason). Score
  reason-grounded catches separately in any judge measurement; a catch for the
  wrong reason inflates the number without measuring the capability.
- **Interim-genre artifacts can't fairly carry completeness-violation gold.** All
  3 dropped_caveat traps cut from plan-check logs were DEFECTIVE-GOLD: an
  iteration log that ends "re-check pending" never claims closure, so a dropped
  remedy creates no judgeable false claim. Injection gold needs an in-artifact
  completeness CLAIM to contradict — check the genre before choosing the family.
- **A unanimous principled rejection of a "clean" control is a defective control,
  not four judge failures.** fi-003's excerpt was cut to exclude all verification
  evidence; every column rejected it citing the role file's own bare-tag pattern.
  Curation read the SOURCE as consistent; the judges graded the EXCERPT's support.
  Controls must carry their evidence inside the excerpt.
- **Two live sessions must never share one git working tree.** A sibling session's
  growing uncommitted rewrite of the hooks/harness (1,300+ lines) made this run's
  live gates fire false positives repeatedly (per-turn plan gate, step-size gate
  counting foreign lines) and put the measuring instruments (verify.py,
  orchestrator.md) in flux mid-run. Survival kit used: path-scoped commits only,
  attribution via a clean `git worktree` at HEAD, pytest/run_evals invoked
  directly instead of through the mutated harness. Proper fix: one session per
  worktree, period.
- **A frozen lesson that lives only as prose gets violated at authoring time.**
  The D1 spec's first decision table conditioned on trap accuracy only — the
  own-recall (false-alarm-term) lesson was already frozen in verifier.md AND
  memory, and still didn't make it into a fresh spec until plan-check round 3
  caught it. Same run, 5 plan-check rounds: every round's new gaps were in text
  added the round before. Author against the lesson list, or expect the checker
  to bill you for it.
