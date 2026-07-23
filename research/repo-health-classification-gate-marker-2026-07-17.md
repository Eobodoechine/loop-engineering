# Coder-unblock dossier: `REPO_HEALTH_CLASSIFICATION` marker syntax (Mode B)

**Date:** 2026-07-17
**Requested by:** Oga (orchestrator), after an Agent dispatch (subagent_type=coder) was
blocked pre-execution by `[OGA GUARD] repo-health classification gate blocked Agent
dispatch: expected exactly one REPO_HEALTH_CLASSIFICATION marker`.
**Target dispatch:** edit `loop-team/runs/2026-07-17_claude-model-routing-pace/specs/claude_product_pilot.md`.
**Confidence:** CONFIRMED — grounded in live source, an exact error-string match, a
currently-passing test suite (12/12), and a direct live re-execution of the real function
with both the failing and fixed inputs (all below). Nothing in this dossier is inferred or
guessed.

## Diagnosis

The gate that fired is `authorize_dispatch()` / `dispatch_markers()` in
`<HOME>/Claude/loop/hooks/repo_health_dispatch_gate.py:8-32`, invoked from
`<HOME>/Claude/loop/hooks/pre_tool_use_oga_guard.py:274-329` (the "Repo-health
classification gate v1" block) for every `Agent`/`Task` dispatch whose `tool_input`
identifies as a Coder dispatch (`spec_bound_verifier_credit.is_coder_dispatch`, i.e.
`subagent_type == "coder"` or text matching `CODER_DETECT`).

`dispatch_markers()` scans the **concatenation of `tool_input["description"]` and
`tool_input["prompt"]`** (`"%s\n%s" % (description, prompt)` — `raw_dispatch_text()`,
line 14-21) for two regexes:

```python
CLASS_RE = re.compile(
    r"\bREPO_HEALTH_CLASSIFICATION=(new-capability|continuing-phase|hardening-bugfix)\b"
)
REPO_RE = re.compile(r"\bREPO_HEALTH_REPO=([A-Za-z0-9._-]+)\b")
```

It requires **exactly one** match of each. Zero matches (marker missing, wrong separator
like `:` instead of `=`, wrong case, or a value outside the 3-item enum) *or* two-or-more
matches (marker duplicated, e.g. present in both `description` and `prompt`) both trip the
same "expected exactly one ... marker" error. The dispatched call had zero (or an invalid)
`REPO_HEALTH_CLASSIFICATION=` occurrence — the exact reported string
`"expected exactly one REPO_HEALTH_CLASSIFICATION marker"` is the literal return value at
`repo_health_dispatch_gate.py:29`, and `pre_tool_use_oga_guard.py:296-298` wraps it verbatim
into the `[OGA GUARD] repo-health classification gate blocked %s dispatch: %s` message —
word-for-word match to what was observed, confirming this is the exact code path, not a
similarly-worded different gate.

## Exact marker syntax (verbatim, quoted from source)

- **Literal token format:** `REPO_HEALTH_CLASSIFICATION=<value>` and
  `REPO_HEALTH_REPO=<repo-id>` — no space around `=`, case-sensitive, must match
  `\b...\b` word boundaries. `<repo-id>` matches `[A-Za-z0-9._-]+` (no enum constraint on
  this one — any repo-shaped token is syntactically accepted).
- **Where it must appear:** `tool_input["description"]` **or** `tool_input["prompt"]` of the
  `Agent`/`Task` tool call — the two fields are concatenated before scanning, so either field
  works, but the total count across **both combined** must be exactly 1 per marker. Putting
  the same marker in both fields is itself a failure (duplicate).
- **Valid `REPO_HEALTH_CLASSIFICATION` values — exactly three, nothing else:**
  `new-capability` | `continuing-phase` | `hardening-bugfix` (kebab-case, lowercase, no
  quotes). These are **not** a git-tree-cleanliness vocabulary (there is no `CLEAN` /
  `DIRTY` / `DIRTY_UNRELATED` value anywhere in this code) — see "Correcting the framing"
  below.
- **Source of truth for meaning:** `<HOME>/Claude/loop/loop-team/orchestrator.md:647-703`
  ("Repo-health gate" section) — Oga is asked to "log an explicit classification line...in
  this exact shape: `"this dispatch is: new-capability | continuing-phase |
  hardening-bugfix, because <reason>"`" (line 659-661; this prose line itself is NOT what the
  hook parses — the hook parses the `REPO_HEALTH_CLASSIFICATION=` token, which is the
  **mechanical enforcement layer**, filed as `H-REPO-GATE-CLASSIFICATION-MECHANICAL-1` in
  `fix_plan.md:6995` and now built — note `orchestrator.md:697-703` still says this step is
  "presently INSTRUCTIONAL only... not yet built," which is now **stale**; the hook's own
  code comment at `pre_tool_use_oga_guard.py:275-277` calls itself "Structural follow-up for
  fix_plan.md H-REPO-GATE-CLASSIFICATION-MECHANICAL-1," i.e. that follow-up has since shipped
  and orchestrator.md's prose was not updated to match. Worth a doc-fix pass separately.)

### What each value actually gates (not git status — a per-repo hardening-backlog freeze)

`repo_health_gate.py`'s own docstring (lines 2-17): this is an SRE-error-budget-style
mechanism that "freezes NEW-CAPABILITY Coder dispatches on a repo once its open hardening
backlog crosses a threshold" (tracked in `loop-team/harness/hardening_ledger.json`).
`authorize_dispatch()` (repo_health_dispatch_gate.py:97-123):
- `classification != "new-capability"` → **returns `True` immediately** — no further check,
  regardless of the repo's ledger state. Both `continuing-phase` and `hardening-bugfix` take
  this branch.
- `classification == "new-capability"` → additionally requires a **prior** `Bash` call in the
  *current transcript turn* matching `python3? .../loop-team/harness/repo_health_gate.py
  <repo-id>` whose JSON result has `"repo": <repo-id>` and `"verdict": "CLEAR"` (not
  `"FROZEN"`, not missing/malformed) — see `latest_same_repo_verdict()` (lines 62-94). This
  is a mechanical prerequisite Bash step, not something the classifier computes inline.

## Correcting the framing in the request

The task described this as if it were about **git working-tree cleanliness** (guessing
values like `CLEAN`/`DIRTY`/`DIRTY_UNRELATED`) and asked me to pick a value based on "repo
has unrelated live dirty files elsewhere; target file itself is untracked/gitignored." That
framing does not match the actual mechanism: **this gate never reads `git status` at all** —
`dispatch_markers()` only regex-scans the dispatch's own `description`/`prompt` text, and
`authorize_dispatch()`'s only other input is the transcript (for the `new-capability` ledger
check). The 4 unrelated modified files in `loop-team/runner/` and the target file's
gitignored/untracked status are **not inputs to this decision at all** — they don't move
which of the three enum values is correct. What actually determines the correct value is
**what kind of work this dispatch is** (brand-new capability vs. continuing already-scoped
work vs. hardening/bugfix), per `orchestrator.md`'s own definitions.

(I did independently confirm the git facts, since they were asked for: `.gitignore:41` is
`loop-team/runs/` and `git check-ignore -v` confirms the target file matches it;
`git ls-files --error-unmatch` confirms it is not tracked; `git status --short` in
`~/Claude/loop` currently shows exactly the 4 modified files named in the request. All true —
just not relevant inputs to this particular gate.)

## Given the concrete situation: which value to use

**`REPO_HEALTH_REPO=loop`** — the target file lives inside `~/Claude/loop` (the loop-team
framework's own repo), matching the only precedent found for loop-team's-own-artifact
dispatches (a real prior task record: `REPO_HEALTH_CLASSIFICATION=hardening-bugfix +
REPO_HEALTH_REPO=loop` for a dispatch editing `hooks/verifier_hygiene_scan.py` /
`hooks/codex_transcript_adapter.py` — also inside `~/Claude/loop`). `hardening_ledger.json`
currently has **zero** entries for repo `"loop"` (5 total entries, all `taxahead` /
`padsplit-cockpit`) — moot for `continuing-phase`/`hardening-bugfix` (no ledger check either
way), but noted for completeness: even `new-capability` would resolve `CLEAR` today for this
repo, if that path were ever taken.

**`REPO_HEALTH_CLASSIFICATION=continuing-phase`** — reasoning: the target run directory
`loop-team/runs/2026-07-17_claude-model-routing-pace/` and its spec
`specs/claude_product_pilot.md` (57,935 bytes) **already exist** — this is not new-capability
work on the `loop` repo, it is a further edit to an already-scoped, already-existing pilot
spec within an already-existing run (confirmed via `ls -la` on the run dir, and via memory
`project_model_routing_pace_spec_fabricated_claim.md`, which records the same spec having
been "read in full" earlier the same day and describes the open next-step as *extending* the
existing spec, not authoring a new capability from scratch). `orchestrator.md:674-678`
defines `continuing-phase` as "already-scoped ongoing work" — a direct fit.
`hardening-bugfix` ("fixing/hardening existing functionality") would ALSO be
gate-accepted (identical `return True` branch — operationally no different), and would be the
more precise choice **only if** the actual edit is specifically correcting a defect in the
spec's content. I was not given the dispatch's actual edit instructions (only the target
path), so Oga should confirm which is truthful against the real edit being made — the
recommendation here is `continuing-phase` as the best fit for "editing an existing,
already-scoped spec," not a claim about the edit's exact content.

## Falsifiable check (performed live, not just read)

Ran the real, unmodified `authorize_dispatch()` directly (bypassing unrelated hook gates) —
this is the actual function, actual repo, right now, not a mock:

```
$ python3 -c "... rh.authorize_dispatch('Agent', broken_input, transcript_path='/nonexistent.jsonl')"
REPRO (missing CLASSIFICATION marker): False 'expected exactly one REPO_HEALTH_CLASSIFICATION marker'

$ python3 -c "... rh.authorize_dispatch('Agent', fixed_input, transcript_path='/nonexistent.jsonl')"
FIX (continuing-phase + repo=loop): True ''
```

`broken_input`'s prompt omitted `REPO_HEALTH_CLASSIFICATION=` (only `REPO_HEALTH_REPO=loop`
present) — reproduces the exact reported error string. `fixed_input`'s prompt added
`REPO_HEALTH_CLASSIFICATION=continuing-phase\nREPO_HEALTH_REPO=loop` — authorized cleanly
(`True, ''`).

Also ran the gate's own test class live: `python3 -m pytest
hooks/test_pre_tool_use_oga_guard.py -k TestRepoHealthClassificationPreToolUse -v` →
**12 passed**, including `test_continuing_phase_and_hardening_bugfix_allow_with_markers`,
which asserts exactly `REPO_HEALTH_CLASSIFICATION=continuing-phase` +
`REPO_HEALTH_REPO=loop` is NOT denied via the real subprocess-invoked hook (not just the
imported function).

## Recommended fix — exact marker line to add to the next Agent dispatch's `prompt`

```
REPO_HEALTH_CLASSIFICATION=continuing-phase
REPO_HEALTH_REPO=loop
```

(One occurrence of each, anywhere in `description` or `prompt`, not both places at once.)

## Adjacent gate — flagged, not investigated (out of this dossier's scope)

`pre_tool_use_oga_guard.py:331+` runs a **separate** "Spec-bound Verifier/Coder credit gate
v1" immediately after this one, for the same `Agent`/`Task`/`Workflow` dispatches. A real
prior task record shows Coder dispatches commonly also need `SPEC_SHA256=<hash matching the
spec file>` plus, in some configurations, a citation of a prior plan-check PASS. This dossier
did not investigate that gate's exact requirements — only the repo-health-classification
gate that actually fired was in scope for this escalation (Mode B: one fix per escalation).
If the next dispatch attempt trips a *different* denial after adding the markers above, that
is expected to be this adjacent gate, and warrants its own unblock pass rather than assuming
today's fix was incomplete.

## Sources (all opened directly, not summarized from search)

- `<HOME>/Claude/loop/hooks/repo_health_dispatch_gate.py` (full file, 124 lines)
- `<HOME>/Claude/loop/loop-team/harness/repo_health_gate.py` (full file, 605 lines)
- `<HOME>/Claude/loop/hooks/pre_tool_use_oga_guard.py:250-339`
- `<HOME>/Claude/loop/loop-team/orchestrator.md:630-710`
- `<HOME>/Claude/loop/fix_plan.md:6995-7010` (`H-REPO-GATE-CLASSIFICATION-MECHANICAL-1`)
- `<HOME>/Claude/loop/hooks/test_pre_tool_use_oga_guard.py:1772-2050` (test
  fixtures + live pytest run, 12/12 passed)
- `<HOME>/Claude/loop/loop-team/harness/hardening_ledger.json` (5 entries, 0 for
  repo `loop`)
- `<HOME>/Claude/loop/.gitignore:41` + live `git check-ignore -v` / `git ls-files
  --error-unmatch` / `git status --short` in `~/Claude/loop`
- `~/.claude/projects/-Users-eobodoechine/memory/project_model_routing_pace_spec_fabricated_claim.md`
  (context on the target run/spec's history)
- Live re-execution of `repo_health_dispatch_gate.authorize_dispatch()` (both failing and
  fixed inputs) and live `pytest` run of the gate's own test class, both performed during
  this dossier's research, not merely read.
