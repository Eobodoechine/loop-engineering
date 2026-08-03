# Gate contract dossier: spec-bound Verifier/Coder credit gate (2026-07-29 update)

**Date:** 2026-07-29
**Supersedes:** `research/spec-bound-verifier-coder-credit-gate-marker-2026-07-17.md` (line numbers
there are stale by ~180 lines; two mechanisms below did not exist when it was written — see
"What changed since 2026-07-17" below). That file's section 5 live-verification *methodology*
remains valid and is not repeated here.
**Requested by:** Oga, after a `subagent_type="plan-check-verifier"` Agent dispatch with the
entire spec inlined as prose (no file-path reference at all) was blocked pre-execution with
`[OGA GUARD] spec-bound Verifier/Coder credit gate blocked Agent dispatch: expected exactly one
spec ref`.
**Confidence:** CONFIRMED for the mechanism (full source read, exact string reproduced from code,
`git log`/`git status`/`git diff` used to confirm the exact commit and zero uncommitted drift).
One item (whether the failing dispatch's ref-count was exactly 0 vs. some other count != 1) is
flagged as inferred-from-description, not transcript-confirmed — see that section.

## 1. Source location

- **Gate logic:** `hooks/spec_bound_verifier_credit.py`, function `extract_spec_info_from_text`,
  **line 344**: `if len(refs) != 1: return None, "expected exactly one spec ref"`.
- **Wiring:** `hooks/pre_tool_use_oga_guard.py`, "Spec-bound Verifier/Coder credit gate v1" block,
  lines 358-415. The deny print (lines 369-380) is:
  ```python
  def _sb_deny(_reason):
      print(json.dumps({"hookSpecificOutput": {
          "hookEventName": "PreToolUse", "permissionDecision": "deny",
          "permissionDecisionReason": (
              "[OGA GUARD] spec-bound Verifier/Coder credit gate blocked "
              "%s dispatch: %s") % (tool_name, _reason)}}))
      _sb_sys.exit(0)
  ```
  With `tool_name="Agent"`, `_reason="expected exactly one spec ref"` this reproduces the exact
  reported string byte-for-byte — confirms this is the precise firing code, not a plausible guess.
- **Confirmed current commit:** `f05d516` (2026-07-23, "fix(hooks): wire orphaned .verifier_pass
  flag into spec-bound credit gate"). `git status --short` / `git diff --stat` against this file
  both returned empty — the working tree exactly matches this commit; no local drift beyond it.
- **Directory note:** the gate lives in `hooks/` (Claude Code PreToolUse/Stop hook scripts), not
  `loop-team/harness/` (a separate family of ~14 standalone evidence/proof-chain scripts —
  `fixplan_closure_lint.py`, `status_claim_audit.py`, etc.). Confirmed by direct grep: the literal
  strings `"expected exactly one spec ref"` and `"OGA GUARD"` exist only under `hooks/`.

## 2. The exact rule (three checks, in order, first failure wins)

`extract_spec_info_from_text(prompt_text, cwd)`:

1. **Ref count.** Scan lines matching
   `SPEC_LINE_RE = r"(?im)^\s*(?:SPEC|Review exactly one spec)\s*:\s*(.+?)\s*$"`; from each match,
   extract `.md`-suffixed path tokens via
   `SPEC_TOKEN_RE = r"(?:~|/|\.\.?/)?[^\s\"'\`),;]+\.md\b"`. **If that strict scan finds 0 or 2+
   refs**, fall back to scanning the *entire* prompt text (not just SPEC:-prefixed lines) for any
   `.md`-shaped token; if exactly one such token exists anywhere, use it. The final count must be
   exactly 1 or the gate returns `"expected exactly one spec ref"`.
2. **Hash count** (only reached if step 1 passes). Needs exactly one `SPEC_SHA256=<64 lowercase
   hex>` occurrence — checked first via the strict whole-line form
   `SPEC_HASH_LINE_RE = r"(?im)^\s*SPEC_SHA256\s*=\s*([0-9a-f]{64})\s*$"`, falling back to the
   bare inline form `HASH_RE = r"\bSPEC_SHA256=([0-9a-f]{64})\b"` if the line-anchored search finds
   none. Wrong count -> `"expected exactly one SPEC_SHA256"`.
3. **File existence** (only reached if step 2 passes). `canonical_spec_path()`: `~`-expand, resolve
   relative-to-cwd if not absolute, `os.path.abspath`, then `os.path.isfile()`. Fails ->
   `"spec ref is not a readable file"`.

A fourth check happens one level up, in `verifier_dispatch_hash_error` (the Verifier pre-dispatch
entry point) and again inside `prior_verifier_credit` (the Coder authorization entry point):
**live hash match** — the declared `SPEC_SHA256=` must equal the actual current sha256 of the
resolved file's bytes (`current_spec_hash_matches`), else `"SPEC_SHA256 does not match current
spec bytes"` (Verifier path) or `"current spec bytes do not match the Coder SPEC_SHA256"` (Coder
path).

**Why this specific dispatch scored a wrong count:** the prompt was entirely inline prose
(background, context, a full "Phase 1 spec" section, instructions) with no file-path reference to
a spec anywhere, per the dispatcher's own description. That means both the strict `SPEC:`-line
scan and the 2026-07-23 broad fallback scan return an empty list -> `len(refs) == 0 != 1`. This is
the most consistent read of the described mechanism. Caveat, stated plainly: the identical message
also fires on a count of 2+ (e.g. an incidental second `.md` mention such as a "read
roles/plan-check-verifier.md first" aside). I did not read the literal dispatch payload/transcript
to count bytes directly — that is session-transcript content outside this role's default scope
without explicit authorization — so 0-vs-2+ is inferred from the reported absence of any spec
file reference, not transcript-confirmed. The remedy is identical either way.

## 3. Detection logic — does this gate apply to all dispatches?

No. `pre_tool_use_oga_guard.py` no-ops immediately for any `tool_name` other than `Bash` (a
separate, unrelated auto-arm side effect) or `Agent`/`Task`/`Workflow`. Within that, this specific
gate only evaluates the subset that `is_verifier_dispatch()` / `is_coder_dispatch()` classify
positively. Quoted verbatim (`hooks/spec_bound_verifier_credit.py`):

```python
def is_verifier_dispatch(tool_use):
    if not is_dispatch_tool(tool_use):
        return False
    inp = tool_input(tool_use)
    text = dispatch_text(tool_use)
    content_says_verifier = (
        VERIFIER_DETECT.search(text) is not None
        or VERIFIER_FALLBACK_RE.search(text) is not None
        or VERIFIER_ROLE_MODE_RE.search(dispatch_prompt(tool_use)) is not None
    )
    subagent_says_verifier = (
        str(inp.get("subagent_type", "") or "").strip().lower() == "plan-check-verifier"
    )
    if not (content_says_verifier or subagent_says_verifier):
        return False
    # subagent_type is caller-supplied and structurally unenforced -- it may only
    # ADD to verifier classification, never SUBTRACT Coder-detection scope.
    if subagent_says_verifier and not content_says_verifier and is_coder_dispatch(tool_use):
        return False
    return True
```

This is a hybrid: exact-string `subagent_type == "plan-check-verifier"` OR a content-regex hit on
`description` (checked first, falls back to `prompt` only if `description` is empty) — with an
anti-laundering rule (comment cites two prior adversarial-exploit rounds, "Misfire-1/2/3") that a
Coder-shaped prompt cannot hide behind a Verifier `subagent_type`. The reported dispatch used
`subagent_type: "plan-check-verifier"`, which alone satisfies `subagent_says_verifier` — no
content match was needed for this gate to activate.

`is_coder_dispatch()`: fast-path exact `subagent_type == "coder"`, OR `CODER_DETECT_STRONG` (role
assignments / direct implementation directives — always wins regardless of `subagent_type`), OR
`CODER_DETECT_WEAK` (incidental mentions like "coder for X" / "roles/coder.md" — suppressed only
when `subagent_type` is in an explicit non-Coder allowlist that includes `"plan-check-verifier"`,
`"verifier"`, `"researcher"`, `"explore"`, `"test-writer"`, `"general-purpose"`, etc.). The
STRONG/WEAK split was added 2026-07-19 (commit `7aab2a4`) specifically so Explore/Researcher
dispatches whose prompts merely *quote* orchestrator.md (which mentions "Coder" liberally) stop
getting misclassified — see that commit's message and the in-source comment at
`spec_bound_verifier_credit.py:252-258`.

**Tool-name scoping within the gate itself:** the Verifier hash-check sub-branch is restricted to
`if dispatch_tool_name in ("Agent", "Task") and is_verifier_dispatch(...)` — a Workflow-based
Verifier dispatch never reaches this specific check. The Coder authorization sub-branch has no
such restriction (`if is_coder_dispatch(...)`, evaluated for Agent/Task/Workflow alike), though a
Workflow Coder dispatch is separately hard-denied ("Workflow Coder dispatch is unsupported in v1")
before reaching the credit check at all.

## 4. Exit-code semantics (non-obvious — worth stating precisely for the Phase 1 registry)

This hook is a PreToolUse script. **Every path — allow or deny — ends in process exit 0.** The
deny/allow signal lives entirely in the STDOUT JSON payload's `hookSpecificOutput.permissionDecision`
field ("deny" vs. no output at all / silent fall-through), never in a nonzero exit code. A future
`gate_contract_registry.py` must not assume uniform exit-code semantics across gates — per the
2026-07-29 diagnosis plan's own Part 2 "Latent offenders" list, `lens_completion_barrier.py` uses
exit 3, and `repo_health_gate.py`'s FROZEN state is exit 0 with the caller required to parse
stdout — three different conventions in the same codebase.

## 5. Full rejection/reason-string catalog

Every distinct literal string this module's functions can return as a "reason" (grant-side
annotations like `"authorized by a valid evidence-bound PLAN_PASS..."` and
`"authorized by cross-turn verifier_pass flag"` are listed separately at the end, not counted as
rejections). Grouped by originating function, in the order each function checks them:

**`extract_spec_info_from_text`** (feeds both the Verifier pre-check and the Coder authorization
path, since both call `extract_spec_info`):
1. `expected exactly one spec ref`
2. `expected exactly one SPEC_SHA256`
3. `spec ref is not a readable file`

**`verifier_dispatch_hash_error`** (Verifier-dispatch PreToolUse entry point; reuses 1-3 above,
plus):
4. `SPEC_SHA256 does not match current spec bytes`

**`_validate_plan_support_json`** (validates one `PLAN_SUPPORT_JSON=` line inside a Verifier's
*result* text):
5. `malformed support`
6. `missing artifact/span`
7. `support spec hash mismatch`
8. `evidence hash mismatch`

**`classify_plan_result_for_hash`** (validates the Verifier's full *result* text structure):
9. `tool result is an error or PreToolUse deny`
10. `expected exactly one LOOP_GATE line`
11. `unexpected content after final gate line`
12. `unterminated <usage> block after final gate line`
13. `explicit LOOP_GATE: PLAN_FAIL` (paired with the `EXPLICIT_PLAN_FAIL` outcome)
14. `final gate line is not LOOP_GATE: PLAN_PASS`
15. `malformed agentId suffix on gate line`
16. `decoy LOOP_GATE token in agentId suffix`
17. `expected exactly one REVIEWED_SPEC_SHA256 before final gate`
18. `reviewed spec hash mismatch`
19. `no PLAN_SUPPORT_JSON support citation` (neutral/`SUPPORT_INVALID_DECLARED_PASS`, not a veto)

**`prior_verifier_credit`** (Coder-side cross-dispatch authorization):
20. `transcript JSONL was not strictly readable`
21. `current-window dispatch ids are missing, duplicate, or non-string`
22. `current spec bytes do not match the Coder SPEC_SHA256`
23. `a qualifying Verifier dispatch for this spec hash returned an explicit PLAN_FAIL (veto)`
24. `a qualifying Verifier dispatch for this spec hash returned a non-PASS/invalid result: %s` (templated with one of 9-19 above as `%s`)
25. `no prior successful paired Verifier result reviewed this spec hash` (optionally suffixed with a support-invalid count)

**`check_verifier_pass_flags`** (cross-turn fallback, see section 6):
26. `no session_id for flag lookup`
27. `no spec hash for flag lookup`
28. `no matching verifier_pass flag for this spec hash`

**`authorize_coder_from_transcript`** (top-level Coder entry point; reuses 20-28 above, plus):
29. `transcript unreadable or malformed`
30. `missing spec info` (defensive-only fallback: `info_error or "missing spec info"` — reachable
    only if `extract_spec_info` returns `(None, None)`, which none of its own return paths actually
    do; kept here for completeness since Phase 1's stated goal is exhaustive extraction, not just
    the reachable subset)

**Total: 30 distinct literal reason strings**, not 21. (Noting this discrepancy plainly rather than
adjusting the count to match: the difference is likely scope — e.g. counting only strings that can
reach a *Verifier pre-dispatch* PreToolUse deny directly gives a much smaller number, around 4-5.
Which scoping is "correct" for a per-gate registry entry is exactly the kind of definitional
question `gate_contract_registry.py` needs to fix mechanically and apply identically across all
gates, rather than leaving it to per-author judgment call.)

**Grant-side strings** (not rejections): `""` (empty, plain success), `authorized by a valid
evidence-bound PLAN_PASS; ...` (+ optional support-invalid/unresolved-sibling notes),
`authorized by cross-turn verifier_pass flag`.

## 6. What changed since the 2026-07-17 dossier (confirmed via `git log -S`, not assumed)

| Mechanism | Commit | Date | What it changes |
|---|---|---|---|
| Fallback broad `.md`-token scan in `extract_spec_info_from_text` | `f05d516` | 2026-07-23 | The strict-only `SPEC:`-line scan the 07-17 dossier documented is no longer the whole story — a 0-or-2+ result now gets a second chance via a whole-prompt scan. |
| `CODER_DETECT_STRONG`/`CODER_DETECT_WEAK` split | `7aab2a4` | 2026-07-19 | `is_coder_dispatch()`'s classification is now two-tiered; the 07-17 dossier only knew a single `CODER_DETECT`. |
| Cross-turn `.verifier_pass` flag credit (`check_verifier_pass_flags`, wired into `authorize_coder_from_transcript`) | `f05d516` | 2026-07-23 | **Directly contradicts** the 07-17 dossier's section 4 claim that "a PASS from an earlier turn is invisible to a later turn's Coder dispatch." As of now, a fresh (<24h TTL), non-empty, hash-matching flag file at `$LOOP_GATE_DIR/<session_id>_*.verifier_pass` grants cross-turn credit even when same-turn transcript credit fails. |

File size grew 676 -> 853 lines across these commits, so every absolute line number in the 07-17
dossier is stale by a wide, non-constant margin. This is a live instance of the diagnosis plan's
own central thesis: "the code is the source of truth and moves faster than any doc describing it."

## 7. What a passing dispatch must contain, right now — grounded in a real historical example

`hooks/test_spec_bound_verifier_credit.py` documents a byte-exact **real historical dispatch
prompt** that passed (`REAL_DISPATCH_PROMPT_TEMPLATE`, sourced from an actual transcript, not
invented — the test file's own docstring calls out that the hash/path slots are the only
substitutions, "never an invented approximation of the shape itself"):

```
SPEC: <path-to-spec>.md
SPEC_SHA256=<64-hex sha256 of that exact file's current bytes>

<delegation/context prose -- never the spec text itself>
...
```

Concrete recipe:
1. Materialize the spec as an actual file under `loop-team/specs/` (not `loop-team/` root — that
   directory contains `HANDOFF_GATE_DIAGNOSIS_PLAN_2026-07-29.md`, whose name matches the
   *separate* hygiene/adjacency gate's `STATUS_DOC_DENYLIST` pattern `"handoff*"`
   (`verifier_hygiene_scan.py:15-19`); any other file dispatched from that same directory would
   trip `[OGA GUARD] Verifier-dispatch adjacency violation` immediately after clearing this gate).
   `specs/`'s own listing has no denylist collisions.
2. Compute its real hash from the file's actual current bytes (`shasum -a 256 <path>` or
   equivalent) before dispatching — not before the file is finalized.
3. Dispatch `prompt` starts with the two lines above, then delegation/context only.
4. Per `orchestrator.md`'s own dispatch-template convention: `description` should start with the
   literal `"plan-check Verifier for ..."` and `subagent_type: "plan-check-verifier"`.
5. For eventual Coder credit (separate, later concern): the Verifier's *result* text must end with
   `PLAN_SUPPORT_JSON=...` / `REVIEWED_SPEC_SHA256=...` / `LOOP_GATE: PLAN_PASS`, ideally produced
   via `hooks/plan_check_credit_output.py <spec_path> <line_start> <line_end> --claim '...'` (the
   dedicated helper that computes the exact hash algorithm the validator expects, added
   2026-07-20 per `orchestrator.md` after 5 failed credit-grant attempts from hand-rolled hashing).

## 8. Structured contract record (Phase-1-registry-shaped)

```json
{
  "gate_id": "spec_bound_verifier_credit",
  "source_file": "hooks/spec_bound_verifier_credit.py",
  "wired_from": "hooks/pre_tool_use_oga_guard.py:358-415 (PreToolUse hook)",
  "confirmed_commit": "f05d516 2026-07-23 (git status/diff show zero local drift)",
  "applies_to": {
    "tool_names": ["Agent", "Task", "Workflow (Coder authorization path only; Workflow Verifier hash-check is excluded)"],
    "classifier_verifier": "is_verifier_dispatch(): subagent_type=='plan-check-verifier' (exact, case-insensitive) OR regex hit on description-then-prompt (VERIFIER_DETECT | VERIFIER_FALLBACK_RE | VERIFIER_ROLE_MODE_RE), minus anti-laundering override when subagent_type is the ONLY signal and content independently qualifies as Coder",
    "classifier_coder": "is_coder_dispatch(): subagent_type=='coder' (exact) OR CODER_DETECT_STRONG (always wins) OR CODER_DETECT_WEAK (suppressed when subagent_type in non-coder allowlist)"
  },
  "required_inputs": {
    "field_scanned": "tool_input.prompt (tool_input.script for Workflow) -- NEVER description",
    "spec_ref": {
      "primary": "line matching ^\\s*(?:SPEC|Review exactly one spec)\\s*:\\s*(.+)$, exactly one .md token extracted",
      "fallback_added_2026_07_23_commit_f05d516": "if primary yields 0 or 2+, scan whole prompt for .md tokens; use if exactly 1",
      "must_resolve_to": "an existing regular file on disk (~-expanded, cwd-resolved, abspath'd, os.path.isfile)"
    },
    "spec_hash": {
      "literal": "SPEC_SHA256=<64 lowercase hex>, exactly one occurrence",
      "must_equal": "live sha256 of the resolved spec file's current bytes"
    },
    "cross_turn_fallback_added_2026_07_23_commit_f05d516": {
      "mechanism": "check_verifier_pass_flags(session_id, coder_spec_hash)",
      "path": "$LOOP_GATE_DIR/<session_id>_*.verifier_pass (default ~/.loop-gate)",
      "ttl": "24h; stale flags deleted on read",
      "content_requirement": "non-empty, must equal the coder's declared spec hash exactly"
    }
  },
  "regexes_literals": {
    "SPEC_LINE_RE": "(?im)^\\s*(?:SPEC|Review exactly one spec)\\s*:\\s*(.+?)\\s*$",
    "SPEC_TOKEN_RE": "(?:~|/|\\.\\.?/)?[^\\s\"'`),;]+\\.md\\b",
    "HASH_RE": "\\bSPEC_SHA256=([0-9a-f]{64})\\b",
    "SPEC_HASH_LINE_RE": "(?im)^\\s*SPEC_SHA256\\s*=\\s*([0-9a-f]{64})\\s*$",
    "REVIEWED_HASH_RE": "\\bREVIEWED_SPEC_SHA256=([0-9a-f]{64})(?:\\b|(?=agentId:))",
    "PLAN_SUPPORT_PREFIX": "PLAN_SUPPORT_JSON=",
    "SHA256_RE": "^[0-9a-f]{64}$",
    "CODER_DETECT_STRONG_added_2026_07_19_commit_7aab2a4": "role:\\s*coder\\b | you are (?:now )?the coder | act as (?:the )?coder | implement...(edit|write|multiedit|apply_patch) tools? | (edit|write|multiedit|apply_patch) tools?...implement",
    "CODER_DETECT_WEAK_added_2026_07_19_commit_7aab2a4": "coder for | roles/coder"
  },
  "exit_code_semantics": "always process exit 0; deny/allow carried in stdout JSON hookSpecificOutput.permissionDecision ('deny' vs no output) -- NOT a process exit code, unlike some sibling gates (lens_completion_barrier.py uses exit 3; repo_health_gate.py's FROZEN is exit 0 with stdout parsing required)",
  "rejection_strings_count": 30,
  "rejection_strings_count_caveat": "count depends on scope -- 30 if counting every distinct literal across all functions in the module (grant-annotations excluded); a much smaller number (~4-5) if scoped only to strings reachable from a direct Verifier-pre-dispatch PreToolUse deny. Full enumerated list in section 5 above.",
  "rejection_strings": [
    "expected exactly one spec ref", "expected exactly one SPEC_SHA256", "spec ref is not a readable file",
    "SPEC_SHA256 does not match current spec bytes", "malformed support", "missing artifact/span",
    "support spec hash mismatch", "evidence hash mismatch", "tool result is an error or PreToolUse deny",
    "expected exactly one LOOP_GATE line", "unexpected content after final gate line",
    "unterminated <usage> block after final gate line", "explicit LOOP_GATE: PLAN_FAIL",
    "final gate line is not LOOP_GATE: PLAN_PASS", "malformed agentId suffix on gate line",
    "decoy LOOP_GATE token in agentId suffix", "expected exactly one REVIEWED_SPEC_SHA256 before final gate",
    "reviewed spec hash mismatch", "no PLAN_SUPPORT_JSON support citation",
    "transcript JSONL was not strictly readable", "current-window dispatch ids are missing, duplicate, or non-string",
    "current spec bytes do not match the Coder SPEC_SHA256",
    "a qualifying Verifier dispatch for this spec hash returned an explicit PLAN_FAIL (veto)",
    "a qualifying Verifier dispatch for this spec hash returned a non-PASS/invalid result: %s",
    "no prior successful paired Verifier result reviewed this spec hash",
    "no session_id for flag lookup", "no spec hash for flag lookup",
    "no matching verifier_pass flag for this spec hash", "transcript unreadable or malformed",
    "missing spec info"
  ],
  "documented_in_producer_facing_docs": {
    "status": "PARTIALLY DOCUMENTED (H5-shaped, not H1)",
    "where": "orchestrator.md ~line 632 (\"Verifier dispatch prompts reference the spec by path, never inline it\") and ~line 679 (plan_check_credit_output.py helper instruction, added 2026-07-20)",
    "what_is_NOT_documented_anywhere_outside_code": [
      "the exact SPEC:/SPEC_SHA256 literal marker syntax and regex shape",
      "the 2026-07-23 broad-fallback .md scan",
      "the full rejection-string catalog (section 5)",
      "the cross-turn .verifier_pass flag mechanism and its 24h TTL",
      "the anti-laundering subagent_type-cannot-subtract-Coder-scope rule",
      "the exit-code-vs-stdout-JSON deny semantics"
    ],
    "calibration_note": "this gate should NOT be flagged fully UNDOCUMENTED in a coverage matrix -- it is a useful calibration case showing H5 (delivery/condensed-summary drift: the doc states the policy but not the mechanism) rather than H1 (pure discovery failure, contract exists nowhere producers look)."
  }
}
```

## Sources (all opened directly, this session)

- `hooks/spec_bound_verifier_credit.py` (full file, 853 lines, current as of commit `f05d516`)
- `hooks/pre_tool_use_oga_guard.py` (lines 1-60, 60-170, 280-560 read directly; call sites for
  `extract_spec_info`/`verifier_dispatch_hash_error`/`authorize_coder_from_transcript`/
  `is_verifier_dispatch`/`is_coder_dispatch` grepped and confirmed)
- `hooks/verifier_hygiene_scan.py` (full file — `VERIFIER_DETECT`, `STATUS_DOC_DENYLIST`,
  `evaluate_adjacency` self-match-exclusion logic)
- `hooks/test_spec_bound_verifier_credit.py` (grepped for `SPEC:` fixtures across ~30 call sites;
  `REAL_DISPATCH_PROMPT_TEMPLATE` and its provenance docstring read in full, lines 1-134)
- `hooks/plan_check_credit_output.py` (full file)
- `loop-team/orchestrator.md` (lines 600-700: dispatch-template conventions, the
  spec-by-path-never-inline rule, the plan-check-verifier credit-output-helper instruction)
- `loop-team/HANDOFF_GATE_DIAGNOSIS_PLAN_2026-07-29.md` (full file, 128 lines — the broader
  diagnosis project this contract record is a Phase-1 seed for)
- `research/spec-bound-verifier-coder-credit-gate-marker-2026-07-17.md` (full file, prior dossier
  on this same gate, superseded by this one — see top-of-file pointer added there)
- `git log --format="%h %ad %s" --date=short -- hooks/spec_bound_verifier_credit.py`, `git log -S`
  against three specific strings to date the fallback-scan, flag-mechanism, and strong/weak-split
  additions, `git status --short` / `git diff --stat` to confirm zero uncommitted drift
- `ls loop-team/specs/` (naming/location convention: 5 existing files, none matching the
  hygiene-gate's status-doc denylist)
