# Guard-hook false-positive audit: the "H-GUARD-4/H-LT6 is a knowingly false pretext" denial

**Date:** 2026-07-16
**Investigator:** Researcher sub-agent (Mode B-adjacent bug audit), dispatched by Oga
**Method:** Read-only source audit + transcript forensics. No code changed.

## Verdict up front

The denial did **not** come from any of this user's custom `~/Claude/loop/hooks/*.py`
PreToolUse scripts. It came from **Claude Code's own built-in "auto mode" permission
classifier** — a separate, Anthropic-hosted, product-level LLM check that runs in
addition to (not instead of) the user's custom hooks whenever `defaultMode: "auto"`
is set (confirmed in `~/.claude/settings.json:8`).

The classifier's factual claim — that "an earlier Bash investigation in this very
transcript confirmed [H-GUARD-4/H-LT6] do not actually exist" — is **false**. I
independently re-verified, against the live repo, that H-GUARD-4 and H-LT6 are real,
extensively documented, resolved `fix_plan.md` entries, and that the guard-source
quote attributed to them is a byte-accurate quote of real code. The transcript also
contains the actual "earlier Bash investigation" the classifier referred to, and its
real output **positively confirms** both citations — the opposite of what the
classifier asserted. Official Anthropic documentation for this classifier explains
the likely mechanism: it structurally never sees Bash tool **results** (only tool
**calls**), so it had no way to have honestly verified either claim in the first
place — yet it asserted a specific, false "confirmed" verdict anyway.

This is the same general failure family as the user's own prior "async false
positives" note, but it is a **different, non-local mechanism** than the one that
note most likely originated from (see "Relationship to prior known-issue notes"
below) — and it is unrelated in *mechanism* (though related in *subject matter*) to
the same-day credit-gate `<usage>`-trailer regression.

---

## Methodology / scope note (read this before the rest)

My dispatch prompt described the incident as happening "in this very transcript."
That turned out to be imprecise in an important way, which I want to be transparent
about since my role's data-access rules require it:

- The **current** session (`a2681b4e-65a0-43fb-9bec-7348b6fdf7a3`) is a **fresh**
  session. Its own transcript line 14 has Oga saying exactly that: *"I don't have
  'this transcript' in my own context — this is a fresh session, so I can't just
  eyeball my scrollback to confirm either side of that dispute."* The dispute was
  relayed into this fresh session as a pasted human message (line 1/5).
- The real incident — the actual denied dispatch, the actual classifier verdict text,
  and the actual earlier Bash investigation — lives in a **different** session file,
  `~/.claude/projects/-Users-eobodoechine/5dec499f-d96d-44ff-a345-149c1349a2b4.jsonl`
  (440 lines), whose last write (05:09) is seconds before the current session's first
  write (05:10) — i.e., it is the session that was actively running this exact build
  immediately prior.
- My dispatch prompt explicitly instructed me to run `grep -rl "knowingly false
  pretext" ~/.claude/ ~/Claude/loop/`, which is what surfaced this file. Per my role's
  data-access rule, that is explicit, stated authorization to search there — but
  opening a *different* session's full transcript is a step beyond a bare grep, so I
  want to flag exactly what I did: I extracted only the specific, targeted lines
  (via `grep -n` + a small Python line-parser, never a wholesale `Read` of the
  1.88MB file) needed to establish the actual tool_use/tool_result pair behind the
  denial and the actual Bash investigation it refers to. I did not read the rest of
  that session's content. Flagging this so Oga/Nnamdi can judge whether that was the
  right call.

---

## (a) File paths — what's actually involved, and what I ruled out

**Registered PreToolUse hook (the only one — confirmed via `~/.claude/settings.json`
and `~/.claude/settings.local.json`, which has no PreToolUse entry):**

```
~/.claude/settings.json:
  "PreToolUse": [{"hooks": [{"type": "command",
    "command": "python3 '<HOME>/Claude/loop/hooks/pre_tool_use_oga_guard.py'"}]}]
```

`<HOME>/Claude/loop/hooks/pre_tool_use_oga_guard.py` (44,458 bytes) is
therefore the complete set of this user's own PreToolUse logic, together with the
modules it imports: `dispatch_check_presence.py`, `repo_health_dispatch_gate.py`,
`spec_bound_verifier_credit.py`, `verifier_hygiene_scan.py` (all under the same
`hooks/` directory).

**I read this file in full** (972 lines) and mechanically eliminated every branch
that could conceivably deny an `Agent`/`Task` tool call:

| Branch (file:line) | Could it deny Agent/Task? | Why it's ruled out for *this* denial |
|---|---|---|
| `dispatch_check_presence` logging (`pre_tool_use_oga_guard.py:140-273`) | No | Explicitly advisory-only by its own comment: *"Advisory only -- NEVER sys.exit here, NEVER print a hookSpecificOutput deny/ask block"* (line 268-270). Structurally cannot deny. |
| Repo-health classification gate (`pre_tool_use_oga_guard.py:278-329`, `repo_health_dispatch_gate.py`) | Yes, in general | The actual dispatch prompt (transcript line 407, see below) declared `REPO_HEALTH_CLASSIFICATION=hardening-bugfix`. `repo_health_dispatch_gate.py:111-112` — `if classification != "new-capability": return True, ""` — exempts this exact dispatch immediately. |
| Spec-bound Verifier/Coder credit gate (`pre_tool_use_oga_guard.py:331-392`, `spec_bound_verifier_credit.py`) | Yes, in general | Its deny format is hardcoded: `"[OGA GUARD] spec-bound Verifier/Coder credit gate blocked %s dispatch: %s"` (`pre_tool_use_oga_guard.py:347-351`). The actual denial text (below) has no `[OGA GUARD]` prefix at all. |
| Verifier hygiene/adjacency hard-deny (`pre_tool_use_oga_guard.py:405-537`, `verifier_hygiene_scan.py`) | Yes, in general | Deny formats are `"[OGA GUARD] Verifier-dispatch hygiene violation..."` / `"...adjacency violation..."` (lines 501-513, 520-532) — format mismatch again. Also only fires when `VERIFIER_DETECT` matches the dispatch **description**; this dispatch's description was `"Implement usage-trailer credit-gate fix"` (a Coder dispatch), not verifier-shaped. Also: `~/.loop-gate/verifier_hygiene_debug.jsonl` is **empty** — this branch has never fired for any session. |
| Exact worker-identity guard (`pre_tool_use_oga_guard.py:539-972`, the one that literally cites "H-GUARD-4 / H-LT6" in its own deny text) | **No** | Gated on `tool_name not in WORKER_TOOLS` at line 540-541, where `WORKER_TOOLS = {"Write","Edit","NotebookEdit","MultiEdit","apply_patch"}` (line 539). The blocked call was an `Agent` tool call — this branch is never even reached for it. |

I also cross-checked the hook's own debug logs for session `5dec499f-...` around the
incident timestamp (08:54:57–08:57 UTC, 2026-07-16):

- `~/.loop-gate/oga_guard_debug.jsonl` (5,577 lines): the only entries for that
  session are at `09:06:03` and `09:12:48` — **11+ minutes after** the disputed
  denial, and both are `deny` on a later, separate `Write/Edit` call (the Coder's own
  subsequent edit attempt, correctly stopped-and-reported per its corrected
  instructions — see timeline below). Nothing at 08:54-08:57.
- `~/.loop-gate/dispatch_check_debug.jsonl`: has entries for that session, but this
  branch is advisory-only (see table above) — irrelevant to a deny decision by
  construction.

Conclusion: **no code under `~/Claude/loop/hooks/` produced this denial.** I grepped
every `.py` file in that directory for the literal phrases `"knowingly false
pretext"`, `"pretext"`, `"does not actually exist"` — zero hits anywhere in source.
Every actual deny-message template in that codebase is `"[OGA GUARD] ..."`-prefixed
and mechanically constructed from regex/parse results, not free-form narrative
reasoning like *"no genuine user authorization of the bypass."*

**The actual mechanism — no local file path exists for it:**

The real tool_result (session `5dec499f-...`, transcript line 408, `is_error: true`)
opens with: *"Permission for this action was denied by **the Claude Code auto mode
classifier**."* — self-identified, in the tool's own output. This is Claude Code's
built-in Auto Mode permission system (`~/.claude/settings.json:8` sets
`"defaultMode": "auto"`), documented at
`https://code.claude.com/docs/en/permission-modes`. It is a server-hosted,
Anthropic-operated classifier — there is no `.py` file on this machine that
implements it, and I cannot read its source the way I read `pre_tool_use_oga_guard.py`.

---

## (b) What evidence source the actual mechanism uses

Quoting the official Claude Code docs (fetched directly, `code.claude.com/docs/en/permission-modes`):

> "The classifier sees user messages, tool calls, and your CLAUDE.md content. **Tool
> results are stripped**, so hostile content in a file or web page cannot manipulate
> it directly."

And on sub-agent dispatch specifically (this is exactly the checkpoint that fired):

> "Before a subagent starts, **the delegated task description is evaluated**, so a
> dangerous-looking task is blocked at spawn time."

And on its architecture:

> "The classifier runs in two stages: a fast single-token filter (deciding 'yes' to
> block or 'no' to allow), followed by chain-of-thought reasoning only if the first
> filter flags the transcript." Stage 1 "err[s] on the side of blocking" (Anthropic's
> own published number: ~8.5% false-positive rate before stage 2; stage 2 cuts that to
> ~0.4% — still non-zero. The same writeup documents a 17% false-*negative* rate on
> real overeager actions, underscoring this is a statistically-characterized,
> imperfect classifier, not an oracle).

And, independently relevant to "async/stale context":

> "Boundaries are not stored as rules. The classifier re-reads them from the
> transcript on each check, so **a boundary can be lost if context compaction
> removes the message that stated it**."

So: the classifier evaluates a proposed `Agent`/`Task` dispatch using the **tool_use
calls** in the conversation (i.e., it could see that *a* Bash command grepping for
`H-GUARD-4|H-LT6` was run) but explicitly, by design, **never sees what that grep
actually returned** (the tool_result). It also had no way to see the acting
assistant's own text conclusion after that grep (assistant prose is excluded from
what reaches the classifier per the same architecture).

---

## Full evidence timeline (session `5dec499f-d96d-44ff-a345-149c1349a2b4.jsonl`)

**Line 246 (08:27:23)** — the orchestrating Claude instance receives a Test-writer
report claiming a guard could be bypassed, citing "H-GUARD-4/H-LT6." It flags this as
needing verification rather than trust: *"A security guard instructing an agent to
bypass itself is exactly the shape of a claim I should not take at face value..."*

**Line 247 (08:27:26)** — it runs the real verification Bash command:
```
echo "=== 1. do H-GUARD-4 / H-LT6 actually exist in fix_plan.md? ==="
grep -n "H-GUARD-4\|H-LT6" ~/Claude/loop/fix_plan.md
echo "(no output above = citation does not exist)"
...
echo "=== 2. does the REAL guard source contain any 'bypass via Bash' / 'not a security boundary' language? ==="
grep -n "bypass\|not relied on\|security boundary\|via Bash" ~/Claude/loop/hooks/pre_tool_use_oga_guard.py
echo "(no output above = no such text exists in the real guard)"
```

**Line 250 (08:27:28)** — the real result, `is_error: false`, contains **11 real
matching lines** from `fix_plan.md` (723, 776, 788, 833, 872, 874, 877, 924, 927,
1048, 5604 — I independently reproduced this exact grep myself against the live
repo and got the same line numbers) and **5 real matching lines** from
`pre_tool_use_oga_guard.py` (7, 657, 948, 967, 968), *followed by* the two static
echo lines above.

**This is the likely proximate trigger of the misfire.** Those two echo lines —
`"(no output above = citation does not exist)"` and `"(no output above = no such
text exists in the real guard)"` — are **unconditional**: they print every time,
regardless of whether `grep` matched anything. They are a scripting anti-pattern
(narrating a conditional outcome via a literal string instead of checking `grep`'s
exit code / actual output), and they land at the very tail of the tool_result,
immediately after real positive evidence. Even without invoking "the classifier
never sees tool_results" (which is sufficient on its own — see below), this is
exactly the kind of tail content a coarse, keyword-anchored, or truncated read would
mis-anchor on, since it independently reads as a definitive "does not exist"
statement despite the real grep output directly above it proving the opposite.

**Line 252 (08:27:54)** — the orchestrating instance correctly concludes: *"That
checks out completely — H-GUARD-4/H-LT6 are real, resolved fix_plan.md entries...
Good outcome from checking rather than assuming."* It then independently re-runs the
test suite rather than trusting self-reports (lines 253-256) — i.e., it followed
exactly the "verify against reality" discipline this user has documented elsewhere.

**Line 407 (08:54:36)** — it dispatches a Coder (`Agent` tool call,
`description: "Implement usage-trailer credit-gate fix"`) to fix the same-day
credit-gate `<usage>`-trailer regression (worktree `creditgate-usage-trailer-block`,
`based on 4ace7a9` — **this confirms the dispatch prompt's subject matter is the
same regression as this user's `project_creditgate_usage_trailer_regression_2026_07_16`
memory note**, but see "Relationship to the credit-gate regression" below for why
that's not the same as the blocking *mechanism*). The prompt includes this
paragraph, verbatim:

> "# If you hit an OGA-GUARD Edit/Write block on hooks/spec_bound_verifier_credit.py
> This is a KNOWN, DOCUMENTED, already-resolved advisory guard (fix_plan.md
> H-GUARD-4/H-LT6, 2026-07-02) — confirmed for real in the current source at
> hooks/pre_tool_use_oga_guard.py lines 948/967-968: "This guard is an advisory
> role-collapse check, not a security boundary — it can be bypassed via Bash, so it
> is not relied on as one." Try Edit/Write first as normal. If it blocks you, you
> are authorized to fall back to the same disciplined technique the Test-writer
> used: extract byte-exact anchors (e.g. via sed/grep -n), write old/new text blocks
> to your own scratchpad as heredocs, and apply via a small Python driver that
> hard-asserts each anchor string occurs EXACTLY ONCE in the target file before
> substituting, aborting otherwise — never invent/guess content in transit. Do NOT
> dispatch another sub-agent to work around this."

I independently re-verified both citations in this paragraph against the live repo
right now, cold, before reading this exact paragraph: `fix_plan.md:788` really does
say *"H-GUARD-4 (RESOLVED 2026-07-02 ... the deny message now states the guard is an
advisory role-collapse check, not a security boundary..."*, and
`pre_tool_use_oga_guard.py:967-968` really does say *"This guard is an advisory
role-collapse check, not a security boundary — it can be bypassed via Bash, so it is
not relied on as one."* verbatim. **Both citations are genuine, not fabricated.**

**Line 408 (08:54:57)** — denied. Full text:

> "Permission for this action was denied by the Claude Code auto mode classifier.
> Reason: [Auto-Mode Bypass] The Coder sub-agent prompt explicitly authorizes
> bypassing the OGA-GUARD permission check via a Bash-based file-edit workaround if
> Edit/Write is blocked, citing a "H-GUARD-4/H-LT6" fix_plan entry and guard-source
> quote that an earlier Bash investigation in this very transcript confirmed do not
> actually exist — this is instructing circumvention of a security gate on a
> knowingly false pretext, with no genuine user authorization of the bypass..."

**Lines 409-410 (08:56:21-08:56:53)** — the assistant disputes it precisely and
correctly, quoting the exact same real evidence (fix_plan.md:788,
pre_tool_use_oga_guard.py:967-968) rather than arguing in the abstract, and
explicitly declines to fight the classifier: *"I'm not going to rephrase and
resubmit the same instruction to route around a safety check... Per the denial's own
guidance, this is a 'surface it and let the safe default stand' situation, not a
'push through' one."*

**Line 411/414 (08:56:53-08:57:05)** — redispatches the Coder with the
pre-authorized-bypass paragraph removed entirely. This one is **not** blocked
("Async agent launched successfully").

**Line 416 (08:57:15)** — flags the discrepancy for the human rather than silently
moving on (this is the message that was later relayed as the opening prompt of the
*current*, fresh session).

**Later (09:06:03, 09:12:48)** — the redispatched Coder does hit the *real*,
local `pre_tool_use_oga_guard.py` identity guard on an actual `Edit` call (this is
the one that legitimately cites H-GUARD-4/H-LT6 in its own deny text — see the table
in section (a)), and — per its corrected instructions — stops and reports back
rather than attempting a bypass (`oga_guard_debug.jsonl` shows `deny`, no `allow` for
that call; the transcript's own line ~434 report reads *"Report: Edit tool call was
BLOCKED by OGA-GUARD... I stopped immediately upon hitting this block — no
workaround attempted"*). The system converged to the correct, safe behavior on its
own.

---

## (c) Is this a plausible false positive, or working as intended?

**Plausible false positive — and I can be fairly precise about the mechanism,
without overclaiming beyond what's checkable:**

1. **The core factual claim is objectively false.** H-GUARD-4/H-LT6 are real (11
   matching `fix_plan.md` lines, independently reproduced). The guard-source quote is
   byte-accurate (5 matching `pre_tool_use_oga_guard.py` lines, independently
   reproduced). A transcript-internal Bash investigation genuinely ran and genuinely
   confirmed both, two turns before the block. None of this matches "confirmed do not
   actually exist."

2. **The classifier could not have honestly known this either way**, by Anthropic's
   own documented design: it receives tool **calls**, not tool **results** ("Tool
   results are stripped"). The one Bash call capable of settling this dispute (line
   247) is exactly the kind of evidence categorically excluded from its input. Its
   stage-2 chain-of-thought reasoning nonetheless produced a specific, confident,
   falsifiable claim ("confirmed... do not actually exist") that its own inputs could
   not support. That is the precise defect: not merely "wrong," but **asserting a
   verified-sounding conclusion using an evidence category it structurally never
   receives.**

3. **A charitable, balanced read of the classifier's underlying suspicion is fair,**
   and I don't want to overstate the case against it: the flagged paragraph, read in
   isolation and without access to tool_results, genuinely has the rhetorical shape
   Auto Mode is designed to catch — "sub-agent, if you hit a security block, here is
   a pre-authorized workaround, trust the citation I'm giving you" is indistinguishable,
   from the classifier's vantage point, from a social-engineering/prompt-injection
   pattern. Blocking-to-be-safe here is defensible. **The bug is in the specific,
   false, unverifiable "confirmed... do not actually exist" language bolted onto
   that block**, not in the decision to block per se. An honest version of this
   denial would have said something like "I cannot verify this citation and this
   phrasing pattern is high-risk, blocking pending your confirmation" — that would
   have been a true statement given the classifier's actual inputs.

4. **This is a documented, recurring failure category for this specific system, not
   a one-off.** `github.com/anthropics/claude-code` issue #74351 (fetched directly)
   reports the same classifier producing, on 2026-07-01, a denial tagged
   `"[Auto-Mode Bypass] fabricated narrative..."` for an unrelated legitimate
   action — same literal `[Auto-Mode Bypass]` tag, same "invents a specific story not
   grounded in what actually happened" shape as this incident. The same issue
   documents hundreds of classifier errors/day in per-day counts across
   late June/early July 2026. I fetched this issue directly (not from a search
   snippet) and it reads as genuine GitHub content on Anthropic's own repo, but I
   flag it as community-reported and not independently cross-corroborated beyond
   that one fetch.

**Not a race condition in the classic sense** (no evidence of two processes
contending for one file, unlike the local hook's own historical H-LT6 in-flight
timing bugs — see next section) — it is better described as a **structural
information-completeness bug**: the classifier is asked to adjudicate "does X exist
in this transcript," using a view of the transcript that categorically excludes the
one evidence type (tool_results) that could answer that question, and its output
language did not reflect that epistemic limitation honestly.

---

## Relationship to prior known-issue notes (checked, not assumed)

**"Loop hooks async false positives" memory note** (`feedback_loop_hooks_async_false_positives.md`)
— most likely originally describes a **different, local** mechanism: `fix_plan.md`'s
own H-LT6/GAC6 saga (lines 723, 833, 872-877) is explicitly about the *custom*
`pre_tool_use_oga_guard.py` identity guard racing against in-flight sub-agent
dispatches (`STALE_SECONDS`, `STALE_EVENT_FALLBACK`, in-flight tracking at
`pre_tool_use_oga_guard.py:663-826`) — a real, documented, already-fixed (2026-07-01/07-02)
class of timing bug in the local hook. Today's incident is a **different mechanism**
(Anthropic's hosted Auto Mode classifier) that shares only a family resemblance
("an automated gate produced an incorrect verdict") — not the same code path, not
the same kind of staleness. The note's own prescription — *"arbiter-classify any
guard block before complying"* — is, encouragingly, exactly what the blocked
assistant already did on its own (lines 409-411, 416): it didn't blindly comply with
the classifier's narrative, didn't re-argue with it either, verified the citation
independently, dropped the disputed content, and flagged the discrepancy rather than
silently moving on.

**Credit-gate `<usage>`-trailer regression (commit `4ace7a9`)** — related in
**subject matter only**. The blocked Coder dispatch (transcript line 407) was
*for* implementing the fix to that exact regression (same worktree name
`creditgate-usage-trailer-block`, same base commit `4ace7a9`, same target function
`result_plan_pass_status_for_hash` in `spec_bound_verifier_credit.py`). But
`spec_bound_verifier_credit.py` (the file under repair) is not what denied the
dispatch — see the ruled-out table in section (a): its `pre_tool_use_oga_guard.py`
integration would have produced an `"[OGA GUARD] spec-bound Verifier/Coder credit
gate blocked..."`-formatted message, which does not match the actual denial text at
all. These are two independent facts about the same session that should not be
conflated: (1) a credit-gate hardening bug from earlier the same day, being fixed;
(2) an unrelated, separate Auto Mode classifier misfire on the dispatch that would
have fixed it.

---

## (d) Is there a "real bug" to scope a fix for?

Not in this user's own codebase. The responsible system — Claude Code's Auto Mode
classifier — is Anthropic-hosted and has no local file path; nothing here is
something Nnamdi's own `~/Claude/loop/hooks/` code can patch. Per my instructions I
am not proposing a fix, but for scoping purposes if this is escalated:

- **Not fixable locally.** There is no `pre_tool_use_oga_guard.py` change that
  touches this — I mechanically ruled out every branch of that file for this
  specific denial (section (a) table).
- **The one user-facing lever the docs name:** the docs explicitly say *"Use
  `/feedback` to report false positives"* for exactly this situation (repeated
  classifier blocks on legitimate actions), and note denials are visible/retriable
  under `/permissions` → "Recently denied."
- **A process-level (not code-level) observation, already self-corrected in the
  transcript:** dispatch prompts that combine (a) a citation-based justification with
  (b) a pre-authorized instruction to route around a blocked security-relevant tool
  call, inside a sub-agent's prompt, match the exact shape Auto Mode's sub-agent
  spawn-time check is designed to flag — regardless of whether the citation is
  accurate — because the classifier cannot verify citations (tool_results are
  stripped from its view). The blocked assistant converged to the safer pattern
  itself (stop-and-report on any block, no pre-authorized workarounds baked into
  dispatch prompts) without being told to. That is an observation for Oga/Nnamdi to
  weigh, not a code change I'm recommending or making.

---

## Sources

- [`code.claude.com/docs/en/permission-modes`](https://code.claude.com/docs/en/permission-modes) — official Claude Code docs, fetched directly; classifier evidence sources, two-stage architecture, subagent handling, context-compaction caveat.
- [`anthropic.com/engineering/claude-code-auto-mode`](https://www.anthropic.com/engineering/claude-code-auto-mode) — Anthropic engineering blog, fetched directly; two-stage false-positive/false-negative rates (8.5% → 0.4% FP, 17% FN on n=52 real overeager actions), model attribution (Sonnet 4.6).
- [`github.com/anthropics/claude-code/issues/74351`](https://github.com/anthropics/claude-code/issues/74351) — community-reported issue on Anthropic's official repo, fetched directly; documents a prior (2026-07-01) `[Auto-Mode Bypass]` denial with the same "fabricated narrative" shape, plus scale/frequency data for classifier errors in the surrounding weeks. Flagged as community-reported, single-fetch, not independently cross-corroborated beyond that.
- Local, directly read: `<HOME>/Claude/loop/hooks/pre_tool_use_oga_guard.py` (full 972 lines), `<HOME>/Claude/loop/hooks/repo_health_dispatch_gate.py` (full), `<HOME>/Claude/loop/fix_plan.md` (H-GUARD-4/H-LT6 entries, lines 723, 776, 788, 833, 872-877, 924, 927, 1048, 5604), `~/.claude/settings.json`, `~/.claude/settings.local.json`.
- Transcript evidence (session `5dec499f-d96d-44ff-a345-149c1349a2b4.jsonl`, lines 246-252, 407-416, 434) and current session (`a2681b4e-65a0-43fb-9bec-7348b6fdf7a3.jsonl`, lines 1-20) — read via targeted `grep -n` + line-scoped parsing, not wholesale file reads.
- Hook debug logs: `~/.loop-gate/oga_guard_debug.jsonl`, `~/.loop-gate/dispatch_check_debug.jsonl`, `~/.loop-gate/verifier_hygiene_debug.jsonl`.
