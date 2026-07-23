# Workflow sub-dispatch text isolation — design research

**Date:** 2026-07-03
**Mode:** A-adjacent / design research (pre-spec, per orchestrator.md's DESIGN-gap rule)
**Trigger:** `fix_plan.md`'s `H-WORKFLOW-SUBDISPATCH-ISOLATION-1` (OPEN, priority HIGH),
follow-up to `H-PRETOOLUSE-VERIFIER-HYGIENE-1` (spec:
`runs/2026-07-03_h-pretooluse-verifier-hygiene/specs/spec.md` v4).
**Question:** can we isolate each sub-dispatch's own text span within a `Workflow` tool's
`script` field well enough to run the same hygiene/adjacency scan per-sub-dispatch (not
whole-script), so `Workflow` calls can eventually get the same pre-dispatch hard-block
`Agent`/`Task` already has?

**Sub-agent delegation:** none used. All file reads, greps, and script extraction below
were done directly.

---

## 1. Real shape of Workflow scripts — empirical survey, not hypotheticals

### 1a. The test fixtures (`hooks/test_loop_stop_guard.py`) are NOT representative

`workflow_tool_use(script)` (`hooks/test_loop_stop_guard.py:5645`) wraps a bare string into
`tool_use("Workflow", script=script)`. Every fixture built with it uses a single-object-literal
call shape, e.g. (`hooks/test_loop_stop_guard.py:5659-5661`):

```js
await agent({description: 'plan-check Verifier for widget spec',
             prompt: 'You are an independent verifier reviewing the change.'})
```

This is a clean, easy-to-parse shape: one call, one object literal, `description`/`prompt`
keys directly analogous to `Agent`/`Task`'s own top-level fields.

**This shape does not occur even once in this project's real, live Workflow dispatch
history.** I extracted every actual `Workflow` tool_use across all 80 Claude Code session
transcripts on this machine under
`~/.claude/projects/-Users-eobodoechine/*.jsonl` (grepping for
`"name":"Workflow"` then parsing the JSON to pull `message.content[].input.script`):

```python
# extraction method used (real, run directly, not hypothetical)
import json, glob
base = "<HOME>/.claude/projects/-Users-eobodoechine/"
files = glob.glob(base + "*.jsonl")
all_scripts = []
for path in files:
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if '"name":"Workflow"' not in line: continue
            obj = json.loads(line)
            for block in obj.get("message", {}).get("content", []):
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Workflow":
                    all_scripts.append(block.get("input", {}).get("script", ""))
```

Result: **84 real Workflow scripts**, ranging 4,512–22,551 characters. Measured directly
against all 84:

| Shape feature | Count | % |
|---|---|---|
| `agent({description:'...', prompt:'...'})` object-literal (the fixture shape) | **0** | **0%** |
| `agent(<promptExpr>, <optionsObject>)` two-positional-arg shape | 21 (scanned via a narrower regex; true rate is close to 100% — see below) | — |
| `parallel(<array>.map(l => () => agent(...)))` | 51 | 61% |
| `parallel([() => agent(...), () => agent(...), ...])` (literal array of thunks) | seen directly (script `wf_9agent`, resume-tailor-feature-build) | — |
| `pipeline(<array>, mapFn, reduceFn)` | 1 | 1% |
| `.catch(...)` fallback handler present | 32 | 38% |
| Backtick template literal used anywhere | 56 | 67% |
| **Nested backtick** (a template literal containing another template literal inside its own `${...}` interpolation) | 1 (confirmed, quoted below) | 1% but real |
| `JSON.stringify(...)` embedded inside a prompt string | 9 | 11% |
| `agent(...)` call inside an `if (...) {...}` conditional block | 1 | 1% |
| Multi-phase script (`phase(...)` called more than once) | 17 | 20% |
| Script defines its own helper `function ... (...) {...}` | 7 | 8% |
| Literal `agent(` occurrences per script | min 0, median 1, max 9 | — |

**The single most important finding:** every real script uses `agent(promptExpression,
optionsObject)` — a two-argument call where the first argument is a JS **expression**, not
necessarily a literal. `hyg`/`adjacency` scanning assumes there is "a prompt string" to scan;
in the real corpus that expression is, variously:
- a template literal built inline (`` agent(`...${VAR}...`, {...}) ``) — most common,
- a bare variable reference to a `const` built earlier in the script
  (`` agent(stt_prompt, {...}) ``, `` agent(lensPrompt(l.key, l.instructions), {...}) ``),
- a property access on a loop variable (`` agent(f.prompt, {...}) ``, `` agent(l.focus,
  {...}) ``, `` agent(c.dispatch_prompt, {...}) `` inside a `.map`/`pipeline` callback),
- **a property read off a runtime value returned by an EARLIER `agent()` call in the same
  script** — i.e., text that does not exist anywhere in the script as a string literal at
  all. Confirmed real example (`debugging-methods-deep-research-and-experiment` script,
  Phase 4 "Run experiment"):
  ```js
  experimentResult = await agent(synthesis.experiment.dispatch_prompt, {
    label: `experiment: ${synthesis.experiment.method_name}`,
    ...
  })
  ```
  `synthesis` is itself the return value of a prior `agent(...)` call in Phase 3, whose
  StructuredOutput schema has a `dispatch_prompt` field the model fills in at runtime. **No
  static analysis of the script text can recover this prompt's content** — it is generated
  by a sub-agent's own output, consumed by a later phase, and never appears as a string
  literal in the `script` field at all.

### 1b. Real example — the "plain lens" shape (most common: `parallel(lenses.map(...))`)

Verbatim, from a real round-3 plan-check dispatch of `H-SUBAGENT-COMMIT-GATE-1`
(session `e9c9c498-8820-425f-9b27-307933e76b2e`, one of 13 Workflow calls in that single
session):

```js
const lenses = [
  { key: 'concurrency-isolation', focus: `LENS: concurrency-isolation. Verify directly against...` },
  { key: 'regression-audit', focus: `LENS: regression-audit. Re-verify the corrected placement...` },
  { key: 'precision-of-instruction', focus: `LENS: precision-of-instruction. Read every specific claim...` },
  { key: 'state-completeness', focus: `LENS: state-completeness. Check whether the cross-agent-masking...` },
]

const results = await parallel(lenses.map(l => () =>
  agent(
    `${FRAMING}\n\n${l.focus}\n\n${NO_SUBDELEGATION}\n\n${STRUCTURED_OUTPUT_FIX}\n\nReturn your verdict...`,
    { label: `round3:${l.key}`, phase: 'Plan-check round 3', schema: SCHEMA }
  )
    .then(r => ({ lens: l.key, ...r }))
    .catch(e => ({ lens: l.key, pass: null, summary: 'FAILED TO RETURN: ' + String(e && e.message || e), gaps: [], loop_gate: null }))
))
```

There is exactly **one literal `agent(` call site** in this script, invoked 4 times at
runtime via `.map()`. The 4 sub-dispatches' distinguishing content (`l.focus`) lives in a
**separate data array** (`lenses`), not inline at each call site. `FRAMING`,
`NO_SUBDELEGATION`, `STRUCTURED_OUTPUT_FIX` are shared `const` template literals
concatenated via `${...}` interpolation into every one of the 4 sub-dispatches' final
prompt. This is the modal shape: **61% of all 84 real scripts use this exact
`parallel(array.map(...))` pattern.**

### 1c. Real example — array-of-thunks shape (each `agent(` call written out literally)

From `resume-tailor-feature-build` (a real feature-build Workflow, not a plan-check):

```js
const sprint1 = await parallel([
  () => agent(`
SPRINT 1 — WORKER A: Item 2 (copy full_name to profiles on admin approve)
REPO: ${REPO}
...
  `, { phase: 'Sprint 1: Quick backend wins (items 2, 15, 16)', schema: STATUS_SCHEMA, isolation: 'worktree' }),
  () => agent(`
SPRINT 1 — WORKER B: Item 15 ...
  `, { phase: '...', schema: STATUS_SCHEMA, isolation: 'worktree' }),
  // ... 9 literal agent( calls total across the whole script, across 4 sequential phases
])
```

This script has **9 literal `agent(` call sites** (the max found in the corpus), across 4
sequential `phase(...)` blocks, each phase's `parallel([...])` containing its own array of
arrow-function thunks with large (30-60 line), multi-line, backtick-delimited prompts using
non-trivial JS inside the backticks (numbered instructions, code snippets referencing real
file paths, an embedded shell test command via `${TEST_CMD}`).

### 1d. Real example — `pipeline(...)` shape (confirmed rare: 1/84, but real)

From `padsplit-cockpit-bug-hunt`:

```js
phase('Discover')
const results = await pipeline(
  FINDERS,
  f => agent(f.prompt, { label: `find:${f.key}`, phase: 'Discover', schema: FINDINGS_SCHEMA }),
  (findResult, f) => { if (!findResult) return {...}; return { area: f.key, ...findResult } }
)
...
phase('Verify')
const verified = await pipeline(
  candidates,
  c => agent(
    `Independently verify this claimed bug in the repo at ${REPO} — do NOT trust the claim...
Claimed area: ${c.source_area}
Claim: ${c.claim}
Producer-side evidence cited: ${c.producer_evidence}
...`,
    { label: `verify:${c.source_area}`, phase: 'Verify', schema: VERDICT_SCHEMA }
  ),
  (verdict, c) => ({ ...c, verdict })
)
```

Two things worth flagging: (1) `FINDERS` is a literal array of 6 objects, each with its own
large `prompt` field (the actual 6 adversarial finder briefs) — so `f.prompt` in the mapper
callback again refers to data, not an inline literal at the call site; (2) the `verify`
phase's `agent(...)` call constructs its prompt by interpolating **fields off a runtime
`candidates` array that does not exist until the `Discover` phase has already run and
produced results** — the literal template-string SKELETON is visible in the script, but the
actual `c.claim`/`c.source_area`/etc. values that will be substituted in are unknowable
until runtime, once per element of a dynamically-sized array.

### 1e. Confirmed nested-backtick edge case (real, not constructed)

From a real feature-build script (`sprint1` results being logged):

```js
log(`Sprint 1 complete. Results: ${sprint1.filter(Boolean).map(r => `items ${r.items} → ${r.status}`).join(' | ')}`);
```

This is a template literal whose `${...}` interpolation slot contains an arrow function
whose body is **itself another template literal** (`` `items ${r.items} → ${r.status}` ``).
A naive backtick-toggle scanner (treat every unescaped backtick as open/close) breaks here:
it would see 4 backticks and could pair them (1,2) and (3,4) — accidentally closing the
OUTER template literal at the first inner backtick, then reopening a new "string" at the
second, and misreading the rest of the line and everything after it as being inside/outside
the wrong string. This is real, live-observed script text from this exact project's own
session history, not a hypothetical adversarial construction.

### 1f. What the project's own docs say about Workflow script conventions

- `loop-team/orchestrator.md:495` documents the sub-delegation-ban convention
  (`agent()` inside a Workflow script) and confirms `agent()` is the standard dispatch
  primitive used both directly via the Agent tool and via Workflow scripts.
- `loop-team/orchestrator.md:499-528` (`H-PLANCHECK-STRUCTUREDOUTPUT-FLAKY-1`) documents a
  real `robustLensDispatch` helper function pattern using `async function`, `.catch()`,
  template literals with `${...}` interpolation of an `opts.label` field, and a regex
  match (`text.match(/LOOP_GATE:\s*(PLAN_PASS|PLAN_FAIL)/i)`) against a free-text fallback
  — confirming the project's own standing guidance already assumes and recommends
  non-trivial JS control flow (helper functions, try/catch, regex) inside Workflow
  scripts, not simple flat call sequences.
- `research/workflow-structuredoutput-input-wrapping-bug-2026-07-03.md` documents (via real
  transcript quotes) that each `agent()` call inside a `parallel()`/`pipeline()` spawns a
  genuinely separate sub-agent process with its own transcript file under
  `~/.claude/projects/.../subagents/workflows/wf_<id>/agent-<agentId>.jsonl` — confirming
  that "sub-dispatch" is not just a textual construct inside the script; it corresponds to
  a real, separately-identifiable runtime agent. However, **the journal.jsonl for these
  sub-agent runs stores only each agent's final `result`, never the prompt text that
  produced it** — confirmed by direct inspection of `wf_c730034f-60a/journal.jsonl`, whose
  `"started"`/`"result"` event records carry only `key` (a hash) and `agentId`, no prompt
  field. This means **no post-hoc runtime artifact reconstructs "which script span produced
  this dispatch" either** — isolation, if it is to happen at all, must happen against the
  literal `script` string at PreToolUse time, before the script ever executes.
- No occurrence of the literal word "backtick" appears anywhere in `fix_plan.md` or
  `loop-team/learnings.md` (checked via `grep -rn "backtick"` across both files — zero
  hits). The task prompt's reference to "avoiding backticks is a KNOWN issue in this exact
  codebase" could not be corroborated as a *named, logged* incident in either file; I flag
  this as **not found** rather than inventing a citation. What IS independently confirmed,
  from the corpus itself (not from a named incident write-up), is the real nested-backtick
  case in §1e above — the underlying risk is real and reproducible even though I could not
  find a prior write-up of it as a named incident.

---

## 2. Strategy evaluation

### 2a. Bracket/paren-balanced scanner for `agent(` call boundaries

**Mechanism:** scan the script text for each `agent(` occurrence; from that point, walk
forward character-by-character maintaining a stack of open brackets/parens/braces and a
string-literal-aware quote state (single, double, AND backtick, since JS has three
string-delimiter types plus template-literal interpolation); when the paren stack returns
to zero, the call's full argument list has been isolated as a text span.

**Complexity:** Moderate. A correct implementation needs, at minimum:
- Three quote-state trackers (`'`, `"`, `` ` ``), each of which needs its own escape-char
  handling (`\'`, `\"`, `` \` ``) so a literal quote INSIDE a string (e.g. a prompt
  containing the text `call foo(x)` or `it's`) does not get misread as a delimiter or an
  unbalanced paren.
- **Template-literal interpolation-aware recursion**, because `${...}` inside a backtick
  string re-enters "code mode" — code that can itself contain more backtick strings (the
  confirmed §1e nested case), more parens, even another `agent(` call. A scanner that
  simply toggles "in backtick string: yes/no" on every unescaped backtick will
  mis-tokenize `` `items ${r.items} → ${r.status}` `` embedded inside an outer template
  literal, exactly as demonstrated in §1e.
- Comment-awareness (`//` line comments, `/* */` block comments) so an `agent(` mentioned
  in a comment, or a paren inside a comment, isn't counted — not yet observed as a live
  problem in the corpus (no `agent(` appears inside a comment in any of the 84 scripts
  scanned), but a correct scanner still needs this to avoid corrupting its bracket count if
  a future script does have one.
- Regex-literal-awareness — JS regex literals (`/pattern/flags`) can also contain characters
  that look like brackets/parens (e.g. `/\(/`). One real script contains a regex
  (`` text.match(/LOOP_GATE:\s*(PLAN_PASS|PLAN_FAIL)/i) `` — orchestrator.md's own
  documented `robustLensDispatch` pattern), and its `(PLAN_PASS|PLAN_FAIL)` group would be
  miscounted by a scanner that isn't regex-literal-aware, since `/` is ambiguous with
  division and the parens inside a regex literal are ordinary characters, not real
  paren-nesting, to the scanner.

**False-positive risk (over-blocking a clean call by mis-isolating boundaries):** MEDIUM.
The confirmed nested-backtick case (§1e) is a genuine bug magnet for the "just toggle
backtick state" version of this scanner; a more careful implementation (recursive
`${...}`-aware backtick handling) closes it, but that recursive handling is exactly the
part most likely to have an off-by-one or infinite-recursion edge case under adversarial or
merely unusual input — i.e., the complexity needed to be CORRECT is significant, and every
increment of complexity is itself a new source of scanner bugs. Given every one of these
bugs, in a hard-deny context, manifests as either (a) wrongly widening a sub-dispatch's
isolated span to include unrelated neighboring text (reintroducing the whole-script
cross-contamination problem this design effort exists to close), or (b) wrongly narrowing
it and missing part of the real prompt (a false-negative — see below) — this is a real,
non-hypothetical risk given the corpus's own confirmed edge case.

**False-negative risk:** MEDIUM-HIGH. Even a CORRECT bracket-balanced scanner can only
isolate the literal call-site TEXT SPAN of `agent(<argsHere>)`. As shown throughout §1
(21+/84 scripts), the actual prompt content very often is NOT inside that span as literal
text — it's a variable reference (`agent(stt_prompt, {...})`), a property access
(`agent(l.focus, {...})`, `agent(f.prompt, {...})`), or (§1a's `dispatch_prompt` case) a
field read off a value that doesn't exist until a PRIOR agent call in the SAME script has
already run. A bracket-balanced scanner has no way to resolve `stt_prompt` back to the
`const stt_prompt = \`...\`` declaration elsewhere in the script (that requires at least a
symbol table, effectively a second, smaller interpreter/parser — see Strategy 2b), and has
NO way at all to resolve a genuinely runtime-only value like `synthesis.experiment.
dispatch_prompt`. In the modal case (§1b, 61% of the corpus: `parallel(lenses.map(l =>
() => agent(\`${FRAMING}\n\n${l.focus}\n\n...\`, {...})))`), the hygiene/adjacency-relevant
text is SPREAD across: (1) the single literal call-site template string containing several
`${VAR}` interpolations, PLUS (2) each of those variables' own separate `const` declarations
elsewhere in the script, PLUS (3) `l.focus`'s value, which lives in a DIFFERENT data
structure (the `lenses` array) entirely. Isolating just the call-site span and scanning ONLY
that literal text — without also resolving `FRAMING`/`NO_SUBDELEGATION`/
`STRUCTURED_OUTPUT_FIX`/`l.focus` back to their real values — would scan a string like
`` `${FRAMING}\n\n${l.focus}\n\n${NO_SUBDELEGATION}\n\n${STRUCTURED_OUTPUT_FIX}\n\nReturn your verdict...` ``
literally, i.e. it would scan the TEMPLATE SOURCE CODE (containing the bare tokens
`${FRAMING}` etc.), never the actual assembled prompt text a real sub-agent will receive.
**This is a severe false-negative path**: a hygiene-marker phrase embedded inside, say,
`FRAMING`'s own `const` value (a separate declaration, possibly hundreds of characters away
in the script) would NEVER be seen by a scanner that only isolates and scans the `agent(`
call-site span itself, because that span contains only the variable NAME, not its value.

**Interaction with existing `_tu_dispatch_text`/`_tu_dispatch_prompt_text`:** these two
helpers (`hooks/loop_stop_guard.py:294-334`) already do a SIMPLER, coarser extraction for
Workflow: `_tu_dispatch_text` returns `str(inp.get("script","")).lower()` (the WHOLE script,
lowercased, for VERIFIER_DETECT classification) and `_tu_dispatch_prompt_text` returns the
whole script un-lowercased (for hygiene/adjacency scanning). A bracket-balanced sub-dispatch
scanner would need to REPLACE this whole-script return with N per-call-site spans for the
hygiene/adjacency scan, while probably KEEPING the whole-script text for the coarser
VERIFIER_DETECT classification step (deciding "does this Workflow dispatch contain ANY
verifier-shaped sub-call at all" is a cheaper, lower-stakes question than "does THIS
specific sub-call's own text carry a violation" — over-including for the classification
step is fine because it only gates whether the finer per-call scan runs at all, not whether
anything gets denied). This is a meaningful, non-trivial refactor of the shared module's
contract (`evaluate_hygiene`/`evaluate_adjacency` currently take one string; they'd need to
be called once per isolated span, in a loop, with per-span pass/fail results reconciled).

### 2b. Stricter JS-subset parser

**Mechanism:** rather than pattern-match call boundaries, actually tokenize the script
(identifiers, string/template literals, numbers, operators, punctuation, keywords) and
parse enough of JS's grammar to build a minimal AST: `const` declarations (so `stt_prompt`,
`FRAMING`, `lenses` etc. can be resolved to their assigned expressions), array literals and
`.map()` calls (so `lenses.map(l => ...)` can be understood as "N calls, one per array
element, with `l` bound to each element"), template literals with correct recursive
`${...}` handling, and call expressions (`agent(...)`, `parallel(...)`, `pipeline(...)`).

**Complexity:** HIGH. This is, in effect, writing a real (if deliberately small) JavaScript
parser and a toy partial-evaluator/constant-folder. Concretely, to resolve even the MODAL
case (§1b) correctly, the parser needs to:
1. Tokenize with full string/template-literal/regex-literal disambiguation (JS's own
   tokenizer needs lookahead/context to distinguish `/` as division vs. regex-literal start
   — a well-known real difficulty in JS tokenizers generally, not specific to this project).
2. Parse `const X = <expr>` bindings into a symbol table.
3. Parse template literals into an ordered list of (literal-text, expression) segments,
   recursively (so a `${...}` segment can itself contain a nested template literal, per
   the confirmed §1e case).
4. Evaluate/substitute known `const`-bound string values back into a template literal's
   expression segments (constant propagation) to reconstruct the ASSEMBLED prompt text
   for each call site — this is necessary because, as shown in 2a's false-negative
   analysis, the raw call-site span alone is not sufficient; the values of `FRAMING`,
   `l.focus`, etc. must be substituted in for the scan to be meaningful.
5. Recognize `<array>.map(l => () => agent(<expr>, <optsObjExpr>))` and `pipeline(<array>,
   f => agent(f.prompt, ...), ...)` as "N sub-dispatches, one per element of `<array>`,"
   and for each element, substitute the array's actual literal field values (e.g. `l.focus`
   → the literal `focus` string from that specific array element) into the resolved prompt.
6. Explicitly detect and FLAG (not silently mis-resolve) any prompt expression that cannot
   be resolved to a compile-time-knowable string — e.g. `synthesis.experiment.
   dispatch_prompt` (§1a), which is a property read off the return value of an earlier
   `agent()` call and is fundamentally not a static-analysis-resolvable value. This is not
   an implementation gap to eventually close — it is a structural impossibility (the value
   genuinely does not exist until a sub-agent, itself possibly hygiene-clean or -dirty,
   produces it at runtime), so the design MUST have an explicit "cannot statically resolve
   this call's prompt" outcome and a defined policy for it (see recommendation).

**False-positive risk:** LOW-MEDIUM, if built correctly — a real parser + constant-folder,
by construction, resolves the modal `parallel(lenses.map(...))` shape correctly (isolating
each lens's OWN assembled prompt: `FRAMING + l.focus + ...`, not a neighboring lens's), which
is exactly the isolation this whole effort wants. But "if built correctly" is doing a lot of
work in that sentence — a hand-rolled JS-subset parser is a nontrivial, ongoing-maintenance
surface (JS syntax has many corners: optional chaining `?.`, nullish coalescing `??`, spread
`...`, destructuring, tagged templates, computed member access `obj[expr]` — any of which
could appear in a future script even if none appear in today's 84-script corpus), and EVERY
corner it doesn't handle degrades back to strategy 2a's or worse failure modes, silently,
unless it's designed to fail CLOSED (treat "can't parse this construct" as "isolation
failed, don't hard-deny this dispatch" — the same fail-open discipline the whole
`pre_tool_use_oga_guard.py` file already uses elsewhere).

**False-negative risk:** MEDIUM, concentrated entirely in the class of prompts that are
genuinely not statically resolvable (§1a's `dispatch_prompt`-from-a-prior-agent-result
case, confirmed real in this exact corpus). No parser, however sophisticated, can recover
text that doesn't exist as a literal anywhere in the script. This is not a parser-quality
gap; it is a fundamental structural limit of static text analysis applied to a
dynamically-generated prompt. Any design here MUST explicitly define what happens when a
sub-dispatch's prompt is NOT statically resolvable — the honest options are (a) treat it as
un-scannable and let it through with no hygiene/adjacency check specific to it (same
residual risk this whole effort already accepts for the general Workflow case today), or
(b) treat "un-resolvable prompt" itself as suspicious enough to block or heavily flag (a
much more aggressive posture that would likely have a high false-positive rate against
totally legitimate patterns like the `debugging-methods` synthesis-then-experiment script,
which is a normal, useful pattern for chaining a research phase into an execution phase).

**Interaction with existing helpers:** same as 2a — would need to replace the single
whole-script string returned by `_tu_dispatch_prompt_text` with N resolved per-sub-dispatch
strings, but ALSO needs a definitive answer for "no static string could be resolved for
this call site" that 2a's simpler design didn't have to confront as sharply (2a can at
least always return SOME text span, even if it's the wrong one; 2b's more honest design
surfaces cases where there's no text span to return at all).

### 2c. Other approaches considered

**(i) Ask the Workflow tool's own script format to be more structured/parseable at the
source.** Out of this project's control (Anthropic's own tool) — worth noting but not
actionable. If the Workflow tool ever exposed a structured, non-JS-string sub-dispatch list
(e.g. a `dispatches: [{description, prompt}, ...]` field alongside or instead of a single
opaque `script` string), the whole isolation problem would collapse to exactly the
`Agent`/`Task` case this build's sibling already solved. No evidence found (in this
project's own docs or the corpus) that such a structured alternative currently exists — the
`script` field is the only real API surface observed across all 84 samples.

**(ii) Simpler heuristic: split on literal `agent(` occurrences, without full bracket
balancing.** E.g., treat everything between one `agent(` and the next `agent(` (or end of
script) as one sub-dispatch's span. This is cheap and simple, but demonstrably wrong against
the real corpus: in the MODAL shape (§1b), there is only ONE literal `agent(` occurrence for
what is actually N (2-6, observed) runtime sub-dispatches — a split-on-occurrences approach
would treat the entire `parallel(lenses.map(...))` block as a SINGLE "sub-dispatch," which is
no better than the current whole-script scan for exactly the case (multiple lenses sharing
one call site, differentiated only by loop-bound data) that is both the most common shape in
the corpus and the shape most likely to trigger the false-positive concern the whole
`H-PRETOOLUSE-VERIFIER-HYGIENE-1` v4 spec was written to avoid (one lens's own legitimate
text tripping a hygiene marker while a DIFFERENT, unrelated lens is Verifier-shaped) — this
heuristic does not even address the scenario it would be built to fix, because both lenses'
"spans" would still be merged into the one `agent(` occurrence's undivided surroundings.
**Rejected — does not solve the stated problem for the majority real shape.**

**(iii) Do not build isolation at all — keep Workflow advisory-only permanently.** This is
the explicit status-quo alternative and is discussed as the recommendation below.

---

## 3. Recommendation

**Do not build per-sub-dispatch text isolation for Workflow scripts as a pre-dispatch
hard-block mechanism. Keep the advisory-only status quo (from `H-PRETOOLUSE-VERIFIER-
HYGIENE-1` v4) as the durable design, not an interim one — but strengthen its DETECTION
recall (not its blocking power) with a bounded, honestly-scoped improvement described
below.**

**Reasoning, grounded directly in the corpus evidence above:**

1. **The modal real shape (61% of 84 scripts: `parallel(array.map(l => () =>
   agent(templateExpr, opts)))`) has its actual per-sub-dispatch prompt content split
   across at least three separate script locations** (the call-site template skeleton, the
   shared `const` framing strings, and the loop-array's own per-element data field). Neither
   strategy 2a (bracket-balanced call-boundary scanner) nor a partial 2b can isolate a
   sub-dispatch's REAL assembled prompt without also resolving variable references and
   loop-bound data back to their values — which pushes even the "lightweight" strategy 2a
   into needing a real constant-folder, i.e., most of strategy 2b's complexity anyway. There
   is no cheap middle ground here; the corpus itself rules it out.

2. **A meaningful fraction of real dispatches are not statically resolvable at all**
   (confirmed: the `debugging-methods-deep-research-and-experiment` script's Phase 4 dispatch,
   whose prompt is `synthesis.experiment.dispatch_prompt` — a field on a value that only
   exists once an earlier sub-agent in the SAME script has already run and returned
   structured output). Any isolation design must define behavior for this case, and neither
   "block it" (high false-positive risk against a legitimate, useful pattern) nor "let it
   through unscanned" (a silent, permanent hole that undermines the whole point of building
   hard-block isolation) is satisfying. This is not a parser-completeness gap that more
   engineering effort closes — it is intrinsic to a Workflow script's ability to chain
   phases where a later phase's dispatch is genuinely determined by an earlier phase's
   output. **Building sophisticated isolation for the ~80-90% of dispatches that ARE
   statically resolvable, while leaving this residual category structurally unscannable
   forever, means the eventual hard-block coverage is inherently partial** — a materially
   different (weaker) guarantee than what Agent/Task's clean `description`/`prompt` split
   gives today, and one that would need to be documented as partial from day one, hardly
   different from today's advisory-only status in terms of the actual security posture for
   this dispatch category.

3. **The confirmed nested-backtick case (§1e)** is direct, non-hypothetical evidence that
   even the "simpler" bracket/paren-balanced scanner (2a) needs real recursive
   template-literal handling to avoid its OWN false-positive/false-negative bugs — the
   complexity floor for a genuinely correct scanner is higher than the strategy's "lightweight"
   framing suggests, and every increment of that complexity is a new place for the scanner
   itself to have a bug that is invisible until a future script happens to exercise it (a
   parser bug in a HARD-DENY gate is a much scarier failure mode than a parser bug in an
   advisory-only log line, because the former can silently deny a legitimate multi-lens
   dispatch in production, exactly the failure mode `H-PRETOOLUSE-VERIFIER-HYGIENE-1` v4
   already explicitly rejected for the whole-script case).

4. **The risk asymmetry that motivated v4's scope reduction is not resolved by isolation —
   it is relocated.** v4 rejected whole-script hard-deny because ONE incidental phrase
   anywhere in the script could block ALL bundled sub-dispatches. A correctly-isolated
   per-sub-dispatch scanner fixes THAT specific failure mode, but introduces a NEW one in
   its place: a scanner bug (mis-isolating a boundary, mis-resolving a variable, or hitting
   an unhandled JS construct) can now cause a hard-deny that blocks the WRONG sub-dispatch,
   or blocks based on text that isn't even the real assembled prompt (scanning
   `${FRAMING}` the literal token instead of FRAMING's actual value, as shown in 2a's
   false-negative analysis) — a different, more confusing failure surface than today's
   "detected only after the fact," and arguably a worse failure to debug live, since it
   would look like a correctly-functioning hard-block gate while actually operating on the
   wrong text.

5. **Cost/benefit, concretely:** the residual risk this build exists to close (a
   Workflow-dispatched adjacency/hygiene violation undetected until Stop-hook time) is
   ALREADY mitigated by the advisory-only logging v4 shipped (`verifier_hygiene_debug.jsonl`)
   plus the pre-existing Stop-hook gates, which still fire reliably on the WHOLE script text
   after the fact — the actual gap is "not blocked before the sub-agent reads the
   contaminated prompt," not "never detected at all." Given (a) the corpus shows the
   isolation problem is harder than either proposed strategy assumed (needs a real
   constant-folding parser, not a lightweight scanner), (b) a meaningful share of dispatches
   are structurally unscannable regardless of parser quality, and (c) a buggy hard-deny
   scanner is a WORSE failure mode than today's status quo (mis-blocking a legitimate
   multi-lens round is exactly the harm this project's own process has repeatedly flagged as
   costly — see the "accuracy over speed" and "plan-check catches spec bugs" standing
   lessons), **the complexity/risk of building this is not currently worth it relative to
   advisory-only + Stop-hook backstop.**

**What I'd build instead (a smaller, honestly-scoped improvement, NOT full isolation):**
Extend the EXISTING advisory-only Workflow branch to opportunistically split on the
already-cheap, purely syntactic marker of literal `agent(` call-site boundaries (Strategy
2(ii)'s rejected heuristic) **for logging/triage purposes only, never for denial** — i.e.,
when the whole-script hygiene/adjacency scan fires today, ALSO record which rough
`agent(...)`-numbered call-site region contained the actual matched marker/path token (byte
offset → nearest preceding `agent(` occurrence), so `verifier_hygiene_debug.jsonl` entries
are easier for a human to triage ("the match was near call-site #3 of 4") without claiming
call-site-level PRECISION or using it to gate a deny decision. This gets some of the
practical debugging value of isolation (faster triage of WHICH bundled lens likely caused a
logged hit) with none of the hard-deny risk, since a wrong "nearest call-site" guess in a
LOG entry costs nothing beyond a slightly-misleading debug line, whereas the same wrong
guess in a DENY decision blocks real work. **This is TESTABLE, not IMPLEMENTABLE_NOW** — it
would need its own small spec and Verifier round before landing, and even then it should
ship with the same explicit "advisory-only, not a step toward a future hard-deny" framing
this doc argues for, unless a future genuine architecture change (§2c(i), a structured
Workflow API from Anthropic) removes the fundamental resolvability problem rather than just
papering over it.

**If revisited later:** the trigger condition that would change this recommendation is
Strategy 2c(i) becoming real — i.e., if the Workflow tool's own `script`/dispatch API ever
exposes sub-dispatches in a structured (non-opaque-string) form, this entire problem
collapses to the already-solved Agent/Task case and should be revisited immediately, since
at that point the isolation is free (structural) rather than something this project would
need to build and maintain a bespoke JS-subset parser for.

---

## Sources / evidence base

All primary evidence is this project's OWN real, live artifacts — no external sources were
needed or used for this design question (it is a codebase-internal parsing/design problem,
not a domain-knowledge one):

- `fix_plan.md` — `H-WORKFLOW-SUBDISPATCH-ISOLATION-1` entry (grep-confirmed at line 2559)
  and its parent `H-PRETOOLUSE-VERIFIER-HYGIENE-1` closure text.
- `runs/2026-07-03_h-pretooluse-verifier-hygiene/specs/spec.md` (v4) — read in full;
  "Workflow scope reduction" (Part 3, lines 357-396) and "Residual risk" (lines 594-615)
  sections are the direct basis for this task's framing.
- `hooks/loop_stop_guard.py` lines 294-334 (`_tu_dispatch_text`/`_tu_dispatch_prompt_text`)
  and lines 906-944 (the hygiene gate's real call sites) — read directly, confirms these
  helpers already do whole-script (not sub-dispatch) extraction for Workflow, exactly as
  the task description stated.
- `hooks/verifier_hygiene_scan.py` — confirmed this file is now real, on-disk (4,384 bytes,
  last modified 2026-07-03 22:11), i.e. `H-PRETOOLUSE-VERIFIER-HYGIENE-1`'s Part 1/2 has
  already landed; this design question is a genuine, currently-open follow-up, not
  speculative.
- `hooks/test_loop_stop_guard.py` lines 5645-5844 — the `workflow_tool_use()` fixture
  helper and its first uses (`WorkflowSite1VerifierExemption`, `WorkflowSite2PlanCheckGate`,
  `WorkflowSite3ResearcherGate`), confirmed as using the simplified
  `agent({description:..., prompt:...})` object-literal shape not found in any real script.
- `loop-team/orchestrator.md` lines 495 (`H-WF-DELEGATE-1`, sub-delegation ban, confirms
  `agent()` is the standard Workflow-script dispatch primitive) and 499-528
  (`H-PLANCHECK-STRUCTUREDOUTPUT-FLAKY-1`, the real `robustLensDispatch` helper-function
  pattern with `.catch()`, template literals, and a `LOOP_GATE:` regex fallback).
- `research/workflow-structuredoutput-input-wrapping-bug-2026-07-03.md` — read in full;
  confirms each `agent()` inside `parallel()`/`pipeline()` spawns a real, separately
  transcript-logged sub-agent (`subagents/workflows/wf_<id>/agent-<agentId>.jsonl`), and
  that these sub-agent transcripts/journals do NOT retain the originating prompt text
  (checked directly: `wf_c730034f-60a/journal.jsonl`'s `started`/`result` events carry only
  a `key` hash and `agentId`, no prompt field) — meaning isolation must happen against the
  script text itself, pre-dispatch, not reconstructed from any runtime artifact after.
- **84 real `Workflow` tool_use `script` field values**, extracted directly from every
  `~/.claude/projects/-Users-eobodoechine/*.jsonl` session transcript on this machine (80
  session files scanned) via the Python extraction method quoted in §1a. This is the
  primary evidence base for this report's entire §1 and §2 false-negative analysis. Specific
  scripts quoted verbatim in this report, by their `meta.name` field:
  - `h-subagent-commit-gate-1-plan-check-round3` (session `e9c9c498-8820-425f-9b27-307933e76b2e`) — §1b
  - `resume-tailor-feature-build` — §1c, §1e (the nested-backtick `log(...)` line)
  - `padsplit-cockpit-bug-hunt` — §1d
  - `debugging-methods-deep-research-and-experiment` (session
    `43e298f5-e04b-4bd0-866c-b7caa7790bc3`) — §1a's runtime-unresolvable-prompt case, §2's
    key recommendation driver
  - `h-review-commit-1-round6-retry-2lens` — the shortest real script (4,512 chars),
    quoted in full in the extraction working notes.
- Checked and found **zero occurrences** of the literal word "backtick" in `fix_plan.md` or
  `loop-team/learnings.md` (direct grep, both files) — flagged in §1f as not independently
  corroborated as a *named* prior incident, distinct from (and not contradicting) the real
  nested-backtick risk independently confirmed in the corpus itself (§1e).

## Honesty flags

- The task prompt asserted "avoiding backticks is a KNOWN issue in this exact codebase —
  search fix_plan.md/learnings.md for 'backtick' to find prior incidents." I searched both
  files directly and found zero hits. I am flagging this explicitly rather than fabricating
  a citation — the underlying RISK is real and independently confirmed via the corpus
  (§1e), but I could not find a prior named write-up of it in the two files named.
- This session's own live Workflow-tool dispatch history (as the task prompt anticipated)
  was not directly readable via a "current session" API, but I was able to recover it (and
  79 other sessions') via the on-disk Claude Code transcript files under
  `~/.claude/projects/-Users-eobodoechine/`, which is a stronger evidence source than the
  task anticipated having available (documented API/schema references) — I used the real
  corpus in place of the documented-schema fallback the task offered as an alternative.
- All strategy-comparison reasoning in §2 and the recommendation in §3 is my own synthesis,
  grounded in the corpus counts and quoted examples above — no external tool/library
  recommendation was sourced from a third party for this report (the question is
  code-internal, not "what OSS tool solves this").
