# Spec: Plan-size governor (`SHIP_NARROW_PLAN` / `INVALID_PLAN_BOUNDARY`)

**Status: plan-check CONVERGED — `LOOP_GATE: PLAN_PASS` at round 7, the first PASS after 6 consecutive
FAIL rounds (rounds 1-6).** Round 7 was dispatched as `plan-check-verifier` (a real custom subagent type,
not a `general-purpose` fallback) — the first genuinely independent, unprimed read since the post-round-6
AC5 grid restructure. It reviewed the spec at `shasum -a 256` =
`0da4b3e59268dc9c2a0c7af68b5afd1f68852696a3c84b3bfca304de2c8a5873` (the post-restructure version) and
returned `LOOP_GATE: PLAN_PASS`; the full record is in
`runs/2026-07-18_165820-plan-size-governor/plan_check_log.md`'s `## Round 7` entry.

**What this PASS means and does NOT mean, stated plainly (do not overstate it):** it means the spec is
judged ready to build against. It does NOT mean the feature is built, tested, or committed — **no
implementation exists yet: Test-writer and Coder have not run**, and that is expected and correct at this
stage. **No user authorization to build or ship has been given, and none is implied here.**
**Carry-forward caveat for the credit gate:** the round-7 verdict emitted
`evidence_sha256=UNAVAILABLE_NO_HASH_TOOL_THIS_ROUND` — a placeholder, not a real digest — because the
`plan-check-verifier` role had no Bash/hash tool this round and so could not cryptographically recompute
the spec's SHA256; it instead corroborated the dispatch-supplied hash against this run's
`plan_check_log.md` recorded post-restructure ending hash character-for-character (circumstantial, NOT
cryptographic, evidence) and explicitly declined to fabricate a digest. Consequently, **if this PASS is
to mechanically auto-credit a downstream Coder dispatch through the credit gate, a hash-capable
re-confirmation step is still required first — the credit gate is NOT already satisfied by this
placeholder.** (The round-7 verdict did include a
`REVIEWED_SPEC_SHA256=0da4b3e59268dc9c2a0c7af68b5afd1f68852696a3c84b3bfca304de2c8a5873` line immediately
before its `LOOP_GATE` line.)

**Prior-round history (rounds 1-6, all `LOOP_GATE: PLAN_FAIL`, all since fixed).** Round 4 findings fixed;
round 5 findings fixed via a post-round-5 systematic sweep (combined find+fix, not an independent review
round — see below and `## Revision history`); AC5 subsequently restructured from an ordered-priority
narrative into an explicit small grid, closing a further malformed-priority gap in the same function (see
the "Post-round-6 AC5 grid restructure" paragraph later in this Status block and `## Revision history`);
round 6 (`plan-check-verifier`) returned `LOOP_GATE: PLAN_FAIL` on the malformed-vs-`SHIP_NARROW_PLAN`
grid gap, which that restructure then closed (grid cells B6/B7) ahead of the round-7 PASS. Round 1
(`LOOP_GATE: PLAN_FAIL`,
4 findings in AC3/AC5/AC10/AC14), round 2 (`LOOP_GATE: PLAN_FAIL`, 2 further findings in
AC1/AC10), round 3 (dispatched as 2 parallel lenses — state-transition-table enumeration, and
regression-audit + precision-of-instruction — both `LOOP_GATE: PLAN_FAIL`, 4 further findings,
one converged on independently by both lenses), and round 4 (dispatched as
`plan-check-verifier`, a real custom subagent type, not a `general-purpose` fallback —
`LOOP_GATE: PLAN_FAIL`, 2 primary findings + 2 secondary/cosmetic findings) are all fully
logged in `runs/2026-07-18_165820-plan-size-governor/plan_check_log.md`. Round 3 hit
`orchestrator.md`'s "max 2 direct revisions" cap (round 1->2 was revision 1, round 2->3 was
revision 2): per that rule, a 3rd automated revision-and-recheck round was not authorized at
that point, and the process's own next step was to stop and put the accumulated findings in
front of the user rather than keep looping. That happened — the user was told the pace, given
the findings, and **explicitly directed Oga to apply them using its own judgment and proceed
to implementation without a further automated plan-check round.** Oga applied all 4 round-3
findings under that explicit direction (documented in the `## Revision history` section
below). **A round-4 `plan-check-verifier` dispatch subsequently gave the resulting spec its
first real verifier read since that closure, and returned a genuine `LOOP_GATE: PLAN_FAIL`:**
2 primary findings (a wrong AC12/AC13 cross-reference pair miscited as AC14/AC15 in the "Files
to read" section; AC7's combined missing-file/wrong-arg-count clause tested as one fixture
instead of two independently-required cases) plus 2 secondary/cosmetic findings (AC6's
fixture not forcing an actual duplicate AC token; an inaccurate `sys.path insertion` citation
in the Constraints section). All 4 are fixed in this revision; the findings are recorded
verbatim in `plan_check_log.md`'s `## Round 4` entry. **Round 5 subsequently found 2 further findings (the
same two recurring gap-shapes traced back through rounds 3-5 — see `## Revision history`'s "Post-round-5
systematic sweep" entry for the full record, including a note that `plan_check_log.md` itself has no
`## Round 5` section as of this sweep). Rather than wait for a round-6 independent reviewer to trip over a
further instance of either shape, a user-directed mechanical sweep fixed both seeded findings plus 2
further instances found by sweeping the rest of the spec for the same two shapes — 4 fixes total, all
recorded in `## Revision history`.**

**Post-round-6 AC5 grid restructure (user-directed, combined find+fix, not an independent review round).**
AC5's `evaluate_plan_boundary` malformed-priority contract was converted from an ordered-priority prose
narrative ("step 1 takes priority over everything after") into an explicit small state grid (7 cells,
Part 5.B), matching AC3's 8-cell grid and AC10's a-k list's own verifiable-by-inspection convention — the
same conversion this Status paragraph's own history shows those two ACs already surviving 6 rounds under,
unlike AC5's narrative form, which leaked a real gap twice: once found by round 5 (malformed-vs-`MISSING`,
fixed by the post-round-5 systematic sweep above) and once described by this pass's own dispatch as already
found by an independent "round 6" (malformed-vs-`SHIP_NARROW_PLAN`). **Record-keeping note, stated
plainly, matching the same disclosure discipline the post-round-5 systematic sweep applied to its own
round-5 characterization:** this file (prior to this edit) and `plan_check_log.md` both state round 6 has
not been dispatched, and neither contains a `## Round 6` entry, dispatch record, or spec snapshot — this
restructure could not confirm the "round 6" gap's reporting provenance from any on-disk artifact (see
`plan_check_log.md`'s matching entry for the full account of what was and was not found). What WAS
independently confirmed, by direct analysis of the live AC5 text against `evaluate_plan_boundary`'s
4-branch logic before any fix was applied: the gap itself is real — no existing AC5 sub-case pinned the
"one dimension malformed, the OTHER validly-declared-and-EXCEEDED" state (grid cells B6/B7) — regardless of
whether a round-6 verifier dispatch actually produced that description. It is fixed now either way. This
pass also tightened two Public interface docstring passages (`parse_mvp_boundary`, `evaluate_plan_boundary`
step 1) that previously named only the priority-over-`MISSING` relationship rather than priority over every
later step — the documentation-level root cause of why the second race went unstated, and consequently
untested, for as long as it did — and added light cross-references from AC2 and AC3 to AC5's new grid so
the full 16-cell state partition is checkable by inspection from any of the three ACs. **No claim of
round-6 authorization, closure-by-judgment, or process-complete is made here — round 6 plan-check has
still not been dispatched and is still pending**, exactly as this paragraph stated before this pass; this
pass changed AC5's structure and closed a specific gap, it did not run or stand in for an independent
plan-check round. This is still a pre-implementation design review: no code exists yet for this build, and
that is expected and correct at this stage, not itself a finding. The revision-history language in this
paragraph and the `## Revision history` section before the Acceptance Criteria section describes
corrections to the SPEC TEXT across plan-check rounds, not changes already applied to any codebase.

**[Update, appended after the round-7 dispatch.]** This supersedes this paragraph's "round 6 ... still not
been dispatched and is still pending" framing on the provenance/status question; the paragraph is left
otherwise unedited as the honest record of what this restructure pass knew when it ran. A `## Round 6`
entry (`plan-check-verifier`, `LOOP_GATE: PLAN_FAIL` on the malformed-vs-`SHIP_NARROW_PLAN` grid gap this
restructure closed via cells B6/B7) was subsequently backfilled into `plan_check_log.md` — a same-day
backfill exactly like round 5's — and an independent round 7 `plan-check-verifier` read of this
restructured spec has since returned `LOOP_GATE: PLAN_PASS` (see the convergence summary at the top of
this Status block and `plan_check_log.md`'s `## Round 7` entry). The "no implementation exists yet" and
"no user authorization to build or ship" statements above remain fully in force — the round-7 PASS is a
plan-check PASS only.

**[Update, round 8, same day.]** A further independent `plan-check-verifier` re-read (dispatched for an
unrelated credit-gate mechanical reason, not because round 7 was doubted) found one genuine gap:
Public interface section 1 (`spec_revision_diff.py`, `--check-ac-inventory`) step 3's "list of objects"
ledger contract was not actually enforced per-element, so a non-dict element in an otherwise-valid JSON
list would crash `entry.get(...)` uncaught, defaulting to exit 1 and colliding with this tool's own
pre-existing exit-1 meaning — silently defeating Key rule 2 in exactly the scenario it exists to prevent.
Fixed in this revision: step 3 now requires an explicit per-entry `isinstance(entry, dict)` check, and
AC10 gained sub-case l covering it. This is a real operative-content change, not meta/bookkeeping — the
round-7/round-"same-turn-reconfirmation" convergence claims above describe the state BEFORE this fix; a
fresh plan-check round on this revised content is required and is in progress.

## Context

Source issue (hash-verified, `REVIEWED_SPEC_SHA256=a7a1263d681141b2e2a7cbbd3dadc522b8a1c4f318c5cc781c0257fe1de23651`,
confirmed by direct `sha256sum` against the on-disk file before this spec was written):
`research/2026-07-16-planning-stop-governor-internal-grounding-redteam.md`.

That research killed a proposed `EXPECTED_PLAN_CHANGE` judgment-based stop-test (backtested 15:0 against
this repo's own history, reinstates a revoked rule, anti-correlated with unknown-unknowns) and instead
recommends building the ONE genuinely new, real-precedent-backed piece: `SHIP_NARROW_PLAN` as a mechanical
**artifact-size governor** — it cuts the *plan*, not the *review*. Precedent already on disk: the TaxAhead
782→97-line spec rewrite (`learnings.md:2717, 2729-2734`) that resolved 5 rounds of escalating scrutiny by
shrinking the artifact, then re-verifying the smaller one (the review got cheaper, it never stopped).

This build implements exactly that recommendation, per Nnamdi's own "Verified plan pass" file list and two
key rules (quoted verbatim in the "Key rule 1"/"Key rule 2" paragraphs immediately following this one), NOT
a re-derivation — this spec operationalizes those rules into a public interface, not a change to them.

**Key rule 1:** oversized plan + missing `MVP_MAX_LINES` / `MVP_MAX_ACS` must return
`INVALID_PLAN_BOUNDARY/missing_mvp_boundary`, not `SHIP_NARROW_PLAN`. `SHIP_NARROW_PLAN` is only legal after
an explicit MVP boundary exists.

**Key rule 2:** every old AC from the pre-shrink spec must appear either in the narrowed spec or in
`hardening_ledger.json` under `deferred_ac_ids`. Silent drops are a hard failure.

**Explicit non-goals** (scope-freeze, stated up front so this build doesn't repeat the disease it's fixing):
- Does NOT implement the `EXPECTED_PLAN_CHANGE` stop-test in any form — the research spec kills it outright.
- Does NOT modify `plancheck_saturation.py`, `plan_check_records.py`, or `reconcile_gap_records.py` — those
  are a *different*, already-shipped mechanism (round-saturation on a recurring `[BINDING]` signature) that
  this governor must not collide with or duplicate. In particular `plancheck_saturation.py:28`'s
  `CONTINUE_PLAN_CHECK` string is NOT reused here (research spec finding: reusing it would be "a live
  collision hazard" between judgment-based and deterministic semantics of the same name).
- Does NOT modify the real `hardening_ledger.json` file's existing entries/content — only documents and
  exercises the additive `deferred_ac_ids` field convention on synthetic fixtures.
- Does NOT implement the research spec's Part 4.2 (per-section convergence freeze) or Part 4.3
  (non-convergence → change mechanism) — both are marked `CONSIDER`, not `BUILD`, in the source spec.

## Task-intent classification (for the Coder's read pass)

Mixed build:
- `plan_size_governor.py` + its tests: **new**.
- `spec_revision_diff.py` + its tests: **modify/fix/continue** (extend, never break existing behavior).
- `orchestrator.md`, `LOOP_TEAM_STANDARD.md`: **modify/fix/continue** (insert new prose at named points).

**Files to read (Coder, before writing anything):**
- `loop-team/harness/spec_revision_diff.py` — the existing tool being extended; its docstring states the
  exact-match-not-fuzzy philosophy this build's AC-extraction must follow (word-bounded, exact tokens, no
  fuzzy matching), and its `extract_headings`/`find_dropped_headings` pair is the pattern `extract_ac_ids`
  must mirror.
- `loop-team/harness/test_spec_revision_diff.py` — every existing test class must still pass unmodified.
- `loop-team/harness/plancheck_saturation.py` — read ONLY to confirm the verdict vocabulary
  (`CONTINUE_PLAN_CHECK`/`STOP_PROSE_REVIEW`/`INVALID_TAGGING`) so this build's own verdict strings
  (`SHIP_NARROW_PLAN`/`WITHIN_MVP_BOUNDARY`/`INVALID_PLAN_BOUNDARY`) are provably disjoint from it — do not
  import from or modify this file.
- `loop-team/harness/hardening_ledger.json` — the real schema (`id`, `repo`, `kind`, `status`, `basis`,
  `description`, `citation`, `opened`, `closed`, `closing_reference`) that `deferred_ac_ids` is an
  *additive, optional* field on top of, never a replacement for.
- `loop-team/orchestrator.md` — read the WHOLE plan-check bullet list under step 1 (search for the
  `[BINDING]`/`[LOGIC]`/`[CONCURRENCY]`/`[SECURITY]` tag-sequence bullet citing `DESIGN_CHECKLIST.md gate
  10` and `plancheck_saturation.py` — that is the exact insertion anchor, see AC12) before editing.
- `LOOP_TEAM_STANDARD.md` — read its existing "See also" citation style (end of file) before adding the
  pointer (AC13). **(Both pointers corrected round 4, closes round-4 Finding 1: this section previously
  cited AC14 — the unrelated `commit_diff_reread.py` record/commit gate — and AC15 — the unrelated
  `fix_plan.md` entry — instead of AC12/AC13, the ACs that actually specify each file's insertion anchor
  and content.)**

## Public interface

### 1. `loop-team/harness/spec_revision_diff.py` — extend (new, additive)

```python
AC_ID_RE = re.compile(r'\bAC\d+[a-z]?\b')  # e.g. AC7, AC19, AC46b — word-bounded, uppercase "AC" exact

def extract_ac_ids(content: str) -> list[str]:
    """Distinct AC\\d+[a-z]? tokens, in first-occurrence order, scanned across the WHOLE text (not
    scoped to headings — real specs in this repo reference ACs inline, e.g. "AC19 (round 30)", not only
    in heading lines). Mirrors the dedupe-on-first-seen, ordered-list contract `find_dropped_headings`
    applies to `extract_headings`'s output (corrected round 3: `extract_headings` itself does not dedupe
    — it appends every match unconditionally; the dedupe/ordering precedent this function mirrors lives in
    `find_dropped_headings`'s own `seen`-set logic, exercised by `test_duplicate_old_heading_reported_once`
    — the prior citation named the wrong function/test as the precedent, though it didn't change what this
    function itself must do, which is fully specified by the sentence above independent of the citation).

    Known, accepted risk (documented candidly, same trade-off class as verify.py's tsc fingerprint
    collision note): a literal "AC123"-shaped substring inside unrelated prose (not actually an
    acceptance-criterion reference) would be picked up. No threshold avoids this without inventing a
    structural AC-declaration syntax this repo does not have; exact-token-match, deliberately
    over-inclusive, is the same philosophy this file's own module docstring already argues for headings.
    """
```

CLI extension (strictly additive — the existing 2-positional-arg form's behavior, output text, and exit
codes 0/1/2 are UNCHANGED):

```
usage: spec_revision_diff.py <old_file> <new_file> [--check-ac-inventory <hardening_ledger.json>]
```

When `--check-ac-inventory <ledger_path>` is present, in addition to the existing heading-diff:
1. `old_acs = extract_ac_ids(old_content)`, `new_acs = extract_ac_ids(new_content)`.
2. `dropped_acs = [a for a in old_acs if a not in set(new_acs)]` (old-file order, dedup-on-first-seen —
   same convention as `find_dropped_headings`).
3. Load `ledger_path` as JSON. Top-level value must be a list, and every element of that list must itself
   be a JSON object (a dict), else usage error (exit 2) — a missing file, unreadable file, invalid JSON, a
   non-list top-level, OR a list containing any element that is not itself a JSON object (a bare
   string/number/null/array in place of an entry) are ALL usage errors here, never silently treated as
   "zero deferred ACs" (a wrong/missing ledger path must fail loud, not mask real deferrals as drops).
   **The per-entry `isinstance(entry, dict)` check is REQUIRED, not incidental** (added this revision,
   closes an independent Verifier finding): the prose "list of objects" contract was previously enforced
   only at the top-level-is-a-list granularity, not per-element — `entry.get("deferred_ac_ids", [])` on a
   non-dict list element raises an uncaught `AttributeError`, which Python's default uncaught-exception
   handling turns into exit code **1**, silently colliding with this SAME tool's own pre-existing,
   differently-scoped exit-1 meaning ("headings dropped, advisory"). Per this build's own AC12
   `orchestrator.md` bullet, a nonzero-3 exit is meant to be a hard block on silent AC drops; a crash
   landing on exit 1 instead would be misread by that same branching logic as a harmless heading-only
   advisory — precisely the "Key rule 2: silent AC drops are a hard failure" scenario this governor exists
   to prevent. This is the third instance of the same bug-shape (uncaught exception -> wrong default exit
   code -> collision with the pre-existing exit-1 meaning) already found and fixed twice elsewhere in this
   spec (AC10.i's JSON-decode distinction; `evaluate_spec_file`'s `UnicodeDecodeError` fix) — closed here
   for the ledger-entry-type case too. By the time step 4 below runs, every entry is already confirmed a
   dict, so `.get` itself cannot raise.
4. `deferred_set = union of (raw if isinstance(raw, list) else []) across every entry, where
   raw = entry.get("deferred_ac_ids", [])` (an entry missing the field, or where the field is present but
   not a list, contributes nothing — never an error; the field is optional per-entry). **The
   `isinstance(raw, list)` guard is REQUIRED, not incidental** (added round 2, closes round-1 Finding 3): a
   literal `entry.get("deferred_ac_ids", [])` sketch WITHOUT this guard does not actually achieve
   "contributes nothing" for a non-list value — e.g. a ledger entry with `"deferred_ac_ids": "AC7"` (a bare
   string, a plausible authoring mistake for a single-id case) would, without the guard, be unioned via
   iteration over its characters (`'A'`, `'C'`, `'7'`) rather than treated as contributing nothing. The
   guard is what makes the stated prose contract true of the actual code, not just of the description.
5. `unaccounted = [a for a in dropped_acs if a not in deferred_set]`.
6. If `unaccounted` is non-empty: print one line per unaccounted AC (`UNACCOUNTED: <id>`) plus a summary
   line, and the process's exit code is **3** (new — distinguishable from exit 1's existing "headings
   dropped, advisory" meaning; this is the hard-failure code for "silent AC drop"). Exit 3 takes priority
   over exit 1/0 from the heading-diff part of the same invocation — i.e. if BOTH a heading was dropped
   (would be exit 1 alone) AND an AC is unaccounted-for, the combined exit code is 3.
7. If `unaccounted` is empty: print a confirming line naming how many dropped ACs were retained-as-deferred
   (if any), and the exit code is whatever the heading-diff part alone would produce (0 or 1) — the AC
   check does not independently force a nonzero exit when everything is accounted for.

Known scoping limitation (state this candidly in the module docstring, matching this repo's house style of
naming residual risk rather than hiding it): `deferred_ac_ids` is checked as a **flat, ledger-wide set**,
not scoped per-spec/per-build. If two unrelated specs coincidentally reuse the same literal AC id (e.g.
both happen to define an "AC7"), a deferral recorded against one could mask a genuine silent drop in the
other. Mitigation is a documentation note (use build-unique AC ids, or manually cross-check the ledger
entry's `citation`), not a code fix in this pass — flag it, do not silently solve it with an unproven
scoping heuristic.

### 2. `loop-team/harness/plan_size_governor.py` — new

```python
VERDICT_SHIP_NARROW = "SHIP_NARROW_PLAN"
VERDICT_WITHIN_BOUNDARY = "WITHIN_MVP_BOUNDARY"
VERDICT_INVALID_BOUNDARY = "INVALID_PLAN_BOUNDARY"

REASON_MISSING = "missing_mvp_boundary"
REASON_MALFORMED = "malformed_mvp_boundary"

def count_lines(text: str) -> int:
    """len(text.splitlines()) — the same mechanical line-count convention used elsewhere in this repo
    (e.g. roles/verifier.md's PLAN_SUPPORT_JSON span-digest)."""

def parse_mvp_boundary(text: str) -> dict:
    """Scan `text` for directive lines '^MVP_MAX_LINES:\\s*(.+?)\\s*$' and '^MVP_MAX_ACS:\\s*(.+?)\\s*$'
    (MULTILINE). First match wins if a directive appears more than once. Returns:
        {"mvp_max_lines": int|None, "mvp_max_acs": int|None,
         "malformed": [<"mvp_max_lines"|"mvp_max_acs"> for any directive line that matched but whose
                       captured value did not parse as a non-negative int]}
    A directive that matched but failed int-parsing is NOT silently treated as absent — it lands in
    `malformed`, and `evaluate_plan_boundary` must surface REASON_MALFORMED for it (see AC5's full
    malformed-priority grid), never fall through to REASON_MISSING, SHIP_NARROW_PLAN, or
    WITHIN_MVP_BOUNDARY — malformed takes priority over every other outcome, not only the missing-boundary
    one. **(Prose widened in the post-round-6 AC5 grid restructure — previously named only the
    priority-over-REASON_MISSING relationship, which is what let that one relationship get tested for
    several rounds while the priority-over-SHIP_NARROW_PLAN relationship went unstated here, and
    consequently untested, until that restructure; see AC5.)**
    """

def evaluate_plan_boundary(actual_lines: int, actual_acs: int,
                            mvp_max_lines: int | None, mvp_max_acs: int | None,
                            malformed: list[str] | None = None) -> dict:
    """Pure, deterministic. Returns:
        {"verdict": SHIP_NARROW_PLAN | WITHIN_MVP_BOUNDARY | INVALID_PLAN_BOUNDARY,
         "reason": REASON_MISSING | REASON_MALFORMED | None,
         "actual": {"lines": actual_lines, "acs": actual_acs},
         "declared": {"max_lines": mvp_max_lines, "max_acs": mvp_max_acs},
         "exceeded": {"lines": {"actual":.., "max":..}, "acs": {"actual":.., "max":..}}  # only the
             dimension(s) that actually exceeded; keys for dimensions that didn't exceed or weren't
             declared are OMITTED FROM WITHIN this dict, but the dict ITSELF is ALWAYS present (never
             None/omitted at the top level) — see the round-3 fix note below,
         "message": "<one-sentence human-readable summary>"}

    Logic (mechanical, no invented magic-number 'is this big enough to need a boundary' threshold —
    the ONLY question this function answers is 'given what was actually declared, does the artifact
    exceed it, and was anything declared at all'):
      1. If `malformed` is non-empty -> INVALID_PLAN_BOUNDARY / REASON_MALFORMED. Takes priority over
         EVERY later step — 2 (missing-boundary), 3 (exceeded/SHIP_NARROW_PLAN), and 4 (within-boundary)
         alike — not only the missing-boundary check (a malformed directive is a DIFFERENT, more specific
         problem than a merely-absent one, an exceeded one, or a within-boundary one). This is a genuine
         if/elif/elif/else SHORT-CIRCUIT, not an independently-evaluated priority ranking: once step 1's
         own condition is true, steps 2-4 are never reached at all, regardless of what any of them would
         separately have evaluated to. `exceeded` is `{}` (see round-3 fix note below). **(Prose widened in
         the post-round-6 AC5 grid restructure — closes the exact documentation gap that let AC5's
         sub-cases explicitly test the priority-over-step-2 race for several rounds while the
         priority-over-step-3 race went unstated in prose, and consequently untested, until this pass; see
         AC5 for the full grid this now backs.)**
      2. Elif mvp_max_lines is None AND mvp_max_acs is None -> INVALID_PLAN_BOUNDARY / REASON_MISSING,
         REGARDLESS of actual_lines/actual_acs (a tiny spec with no declared boundary is STILL
         INVALID_PLAN_BOUNDARY under this contract — see AC2; the caller/orchestrator.md decides WHEN
         it's worth invoking this tool at all, this function never guesses). `exceeded` is `{}`.
      3. Else (at least one dimension declared): for each declared dimension, actual > declared is
         'exceeded'. If ANY declared dimension exceeded -> SHIP_NARROW_PLAN, reason=None, `exceeded`
         populated for every dimension that exceeded (declared-but-not-exceeded dimensions omitted from
         `exceeded`).
      4. Else (declared, nothing exceeded) -> WITHIN_MVP_BOUNDARY, reason=None, `exceeded` is `{}`.

    **Round-3 fix (self-identified independently by both parallel lenses this round):** `exceeded`'s
    top-level presence was previously left ambiguous ("omitted/empty") for the WITHIN_MVP_BOUNDARY branch
    and unstated entirely for both INVALID_PLAN_BOUNDARY branches — two good-faith implementations could
    diverge (one returning `exceeded: {}`, another omitting the key or returning `None`) on 3 of this
    function's 4 reachable branches with nothing in the original ACs able to catch the divergence. Fixed
    by pinning ONE definite shape, applied uniformly: **`exceeded` is ALWAYS a dict, present in every
    returned result regardless of verdict; it is only ever EMPTY (`{}`) or POPULATED, never absent, None,
    or any other type.** Every logic step above now states its own `exceeded` value explicitly; AC2, AC3,
    and AC5 (below) each assert this shape directly, not just the verdict string.
    """

def evaluate_spec_file(spec_path: str) -> dict:
    """Read spec_path (utf-8), compute actual_lines=count_lines(text), actual_acs=len(set(extract_ac_ids
    (text))) (extract_ac_ids imported from spec_revision_diff.py — single source of truth, not a second
    copy), parse_mvp_boundary(text), then evaluate_plan_boundary(...). Raises the same OSError a plain
    `open()` would on a missing/unreadable file, AND the same UnicodeDecodeError a plain
    `open(spec_path, encoding="utf-8").read()` would on a file that exists/is readable but contains
    non-UTF-8 bytes — the CLI wrapper (not this function) turns EITHER into the documented exit-2 usage
    error. **Added round 3 (self-identified by the state-transition-table lens):** the UnicodeDecodeError
    case was previously undocumented here — `UnicodeDecodeError` is a `ValueError` subclass, not an
    `OSError` subclass, so a wrapper that only catches `OSError` (the natural reading of the pre-round-3
    text) would let it propagate uncaught into an undocumented default exit code 1, the exact same failure
    shape AC10.i already fixed for the ledger-load path in this same spec's `spec_revision_diff.py`
    extension. This is not hypothetical: `spec_revision_diff.py`'s own existing, unmodified file-read code
    has this identical unfixed gap today, and the Coder is directed (see "Files to read" above) to mirror
    that file's conventions, making reproduction likely absent this explicit correction."""
```

CLI:
```
usage: plan_size_governor.py <spec_file>
```
Prints one JSON object (the `evaluate_spec_file` return value) to stdout via `json.dumps(result,
sort_keys=True)`. **Exit code 0 for every SUCCESSFULLY COMPUTED verdict — including
INVALID_PLAN_BOUNDARY** (mirrors `plancheck_saturation.py`'s own CLI contract exactly: the verdict is
communicated through the JSON payload's `verdict` field, never through the shell exit code, so Oga's
dispatch logic branches on the string, not the process outcome). Exit code **2** on a missing/unreadable
spec file or wrong argument count (usage error), stderr usage message, matching every sibling harness
script's convention.

## Revision history

**Round 1 -> Round 2** (full round-1 gap record: `runs/2026-07-18_165820-plan-size-governor/plan_check_log.md`).
`LOOP_GATE: PLAN_FAIL`, `gap_type: DESIGN` — four LOOP-M5 grid/enumeration gaps, each a case a literal,
good-faith implementation of round 1's ACs could miss while every round-1-specified test still passed. All
four are additive AC/pseudocode clarifications, not mechanism changes; no Researcher dispatch was needed
(see the round-1 plan_check_log.md entry for that triage). Fixes, each marked inline at its AC with
"Added round 2":
1. **AC3** — the 8-cell grid's "within boundary" cells (b, d, h) didn't require testing the exact-equality
   boundary value, so a `>=` vs `>` off-by-one in "exceeded" could ship undetected. Now requires an explicit
   equality-value test in each.
2. **AC10 + Public interface step 4** — the `deferred_ac_ids` union step's prose contract ("non-list
   contributes nothing") wasn't actually achieved by the literal pseudocode sketch for a non-list JSON
   value; a `null`/number value would crash uncaught. Added an explicit `isinstance(raw, list)` guard to the
   pseudocode itself (not just a test), plus a new AC10 sub-case exercising the crash-prone values.
3. **AC5** — only the non-numeric malformed case (`not-a-number`) was tested; a syntactically-valid negative
   integer (`-5`) satisfies a naive `int()` parse and could slip through as a "validly declared" boundary.
   Added an explicit, independently-tested negative-value sub-case.
4. **AC14** — required only `commit_diff_reread.py record`, which alone leaves the actual `git commit`
   unblocked. Added the mandatory `commit_diff_reread.py commit <files> -- <message>` step, matching what
   `orchestrator.md`'s own standing gate already requires.

Also applied this revision: the `H-SPEC-XREF-1` cross-reference discipline (spec at/entering its 2nd
plan-check round) — ran `grep -inE '\b(above|below|earlier|later)\b'` against this file and replaced hits
that pointed across a section boundary with a named anchor (the Context section's forward-reference to
"Key rule 1"/"Key rule 2", and two Acceptance-criteria-to-Public-interface references) with an anchored
reference; hits that stayed as same-bullet/same-paragraph narrative prose (AC3, AC5) were left as-is per
that rule's own "not automatically wrong" guidance. **Correction (round 3): this paragraph originally also
listed AC1 among the "correctly left local" hits — that was wrong. AC1's "with the signatures above" is the
FIRST acceptance criterion, with no earlier content in its own bullet, so "above" could only ever mean the
Public interface section — the same cross-section pattern as the two hits that WERE correctly fixed. Round
2's own self-description of this cleanup pass was therefore itself inaccurate; round 3's Revision history
entry below documents the correction. See round-2 Finding 2 in `plan_check_log.md` for the full trace.**

**Round 2 -> Round 3** (full round-2 gap record: `runs/2026-07-18_165820-plan-size-governor/plan_check_log.md`).
`LOOP_GATE: PLAN_FAIL`, `gap_type: DESIGN` — two further gaps, both surfaced by a fresh full re-read (not
limited to the round-1 diffs), same underlying shape as round 1's findings: an enumerable class named in
this spec's own prose that wasn't fully operationalized. Both mechanical; no Researcher dispatch needed:
1. **AC10** — Public interface step 3 names 4 ledger-load usage-error modes in prose ("a missing file,
   unreadable file, invalid JSON, or non-list top-level"), but AC10's sub-cases only exercised 2 of the 4
   (missing/unreadable path; non-list top-level) — a syntactically-invalid-JSON ledger file was never
   tested, and `json.JSONDecodeError` being a `ValueError` (not `OSError`) subclass means a natural
   "except OSError around open()" implementation would let it crash uncaught, colliding with this same
   tool's pre-existing unrelated exit-1 meaning. Added AC10 sub-case i.
2. **AC1** — see the "Correction" paragraph immediately above; fixed the stale "above" reference to a named
   anchor, matching the AC5/AC9 pattern from round 2.

**Also self-identified and fixed by Oga before dispatching round 3** (not from a Verifier finding — applying
the same "enumerate every claimed behavior against the AC list" discipline proactively, since round 3 is the
last automatic round available and each round so far has found real gaps of this same shape):
- **AC5** — `parse_mvp_boundary`'s own docstring claims "first match wins if a directive appears more than
  once" and implies a `malformed` list that can hold both directive names — neither claim had a test
  anywhere. Added both sub-cases.
- **AC10** — Public interface step 6's explicit "exit 3 takes priority over exit 1" claim had no end-to-end
  fixture where both a dropped heading and an unaccounted AC were present simultaneously. Added sub-case j,
  and tightened sub-case b's previously-ambiguous "(0 or 1 depending on headings)" wording so it no longer
  reads as satisfiable by testing only one of the two variants.

**Round 3 findings (2 parallel lenses — state-transition-table enumeration; regression-audit +
precision-of-instruction) and their fixes** (full gap records in `plan_check_log.md`). Both lenses returned
`LOOP_GATE: PLAN_FAIL`. This is round 3's re-check, and per `orchestrator.md`'s "max 2 direct revisions"
cap this exhausted the automated-revision budget; the user was informed of the pace and findings and
explicitly directed Oga to close these out with its own judgment and proceed to implementation, rather than
dispatch a 4th automated round. Findings, all `gap_type: DESIGN`, all the same recurring shape (an
enumerable class or an explicitly-stated contract left partially unoperationalized), none requiring a
Researcher dispatch:
1. **AC10.b/AC10.j self-contradiction — found independently by BOTH lenses (convergent, highest-confidence
   finding this round).** AC10.b's own round-3 parenthetical claimed sub-case j covered "heading dropped +
   AC fully accounted-for -> exit 1"; j's actual text covers a different cell ("heading dropped + AC NOT
   accounted-for -> exit 3"). The cell b's text promised was untested anywhere in AC10 a-j. Fixed: added
   sub-case k with the genuinely-missing fixture, corrected b's parenthetical to point at k instead of j.
2. **`exceeded` dict shape unstated on 3 of 4 reachable verdict/reason branches** (state-transition-table
   lens). The docstring hedged "omitted/empty" for `WITHIN_MVP_BOUNDARY` and said nothing for either
   `INVALID_PLAN_BOUNDARY` reason. Fixed: pinned `exceeded` to always be a present dict (`{}` when nothing
   to report, populated otherwise) across all 4 branches in the `evaluate_plan_boundary` docstring; added
   explicit `exceeded == {}` assertions to AC2, AC3 (b/d/h), and AC5.
3. **AC5's malformed-directive grid tested `lines` independently but never `acs` independently**
   (state-transition-table lens) — the only acs-malformed fixture also had lines malformed, confounding
   isolation of an acs-specific bug. Fixed: added acs-non-numeric-alone and acs-negative-alone sub-cases,
   mirroring the existing lines-alone ones.
4. **`evaluate_spec_file` documented only `OSError` for the spec-file read; a non-UTF-8 file raises
   `UnicodeDecodeError` (a `ValueError` subclass) uncaught** (state-transition-table lens) — the identical
   failure shape AC10.i already fixed for the ledger-load path, left unfixed for the spec-file-load path;
   confirmed not hypothetical, since `spec_revision_diff.py`'s own existing file-read code (which the
   Coder is directed to mirror) has this same unfixed gap today. Fixed: extended `evaluate_spec_file`'s
   documented exception contract to cover `UnicodeDecodeError` alongside `OSError`, both mapping to exit 2;
   added an AC7 sub-case with a non-UTF-8 fixture.

Also fixed (cosmetic-only, flagged by the regression-audit/precision-of-instruction lens, not FAIL-worthy
on its own): `extract_ac_ids`'s docstring cited `extract_headings` as the dedupe-on-first-seen precedent;
the real dedupe logic lives in the sibling function `find_dropped_headings`. Corrected the citation; the
function's own behavioral spec (first sentence) was already complete and correct independent of this
citation, so no test or implementation guidance changed.

**Round 4 findings (dispatched as `plan-check-verifier`, a real custom subagent type, not a
`general-purpose` fallback — this was the resulting spec's first real verifier read since round 3's
user-authorized closure) and their fixes** (full gap record in `plan_check_log.md`'s `## Round 4` entry).
`LOOP_GATE: PLAN_FAIL`. Both primary findings are `gap_type: DESIGN` (Finding 2 additionally tagged
`LOGIC`), the same recurring shape as every prior round — an explicitly-stated contract or cross-reference
left unoperationalized or miscited — neither requiring a Researcher dispatch:
1. **Wrong AC cross-references in the "Files to read" section.** The section's parenthetical pointers cited
   `see AC14` for the `orchestrator.md`-bullet insertion anchor and `(AC15)` for the `LOOP_TEAM_STANDARD.md`
   pointer — both wrong. AC12 is the AC that actually specifies the `orchestrator.md` bullet's insertion
   anchor and content; AC14 is the unrelated `commit_diff_reread.py` record/commit gate. AC13 is the AC
   that actually specifies the `LOOP_TEAM_STANDARD.md` pointer's content; AC15 is the unrelated
   `fix_plan.md` entry. This evaded the spec's own `H-SPEC-XREF-1` grep mitigation since it used explicit
   `AC14`/`AC15` tokens rather than flagged relative-position words (above/below/earlier/later) — a
   previously-undetected instance of the exact cross-reference failure class that mitigation was built for.
   Fixed: `see AC14` -> `see AC12`, `(AC15)` -> `(AC13)`.
2. **AC7's ungranular missing-file/wrong-arg-count clause.** argv-length validation and file-open error
   handling are two structurally independent code branches in the real `spec_revision_diff.py main()`; the
   sibling `test_spec_revision_diff.py` test suite already treats them as such with 3 separate test
   methods. AC7's ungranular phrasing let a Test-writer satisfy the letter of the AC with only one fixture,
   leaving the other case unexercised — e.g. a CLI reading `sys.argv[1]` before any length check, guarded
   only by `except OSError`, would raise an uncaught `IndexError` (exit 1, not the documented exit 2) on a
   zero-arg invocation, silently violating AC7's own contract. Fixed: split into two explicitly separate,
   independently-required test cases matching `TestUsageErrors`' convention of testing each usage-error
   mode as its own method.

Also fixed in the same pass (secondary/cosmetic, not FAIL-worthy on their own): AC6's fixture now requires
an actual duplicate AC token (previously nothing forced a repeat, so the assertion could not distinguish a
correctly-deduping implementation from one that does not dedupe at all); the Constraints section's
`sys.path insertion` citation is corrected (the real `plancheck_saturation.py` -> `plan_check_records`
import is a bare import with no `sys.path.insert()` anywhere in that file — the real
`sys.path.insert(0, HERE)` precedent is `test_spec_revision_diff.py`'s own test-file sibling-import
convention, a different file serving a different purpose).

**Round 5 has not been dispatched.** This revision closes out round 4's findings only; it does not carry
any claim of user authorization, closure-by-judgment, or process-complete — the next plan-check round
(round 5) is pending.

**Post-round-5 systematic sweep (user-directed, combined find+fix, not an independent review round).**
Round 5 identified two findings, both instances of two gap-shapes that recur (in different specific
locations) through rounds 3, 4, and 5: (Shape A) an enumerable class or multi-branch contract with only one
member mandated for testing; (Shape B) an explicit precedence/priority claim between two conditions never
jointly tested. **Record note:** as of this sweep, `plan_check_log.md` contains no `## Round 5` entry — its
`## Round 4` entry is followed directly by this sweep's own log entry. The 2 seeded findings below were
independently re-verified against the live spec text (both confirmed genuinely present) before any fix was
applied; this sweep did not itself witness a round-5 verifier transcript and makes no claim that one is
recorded on disk — that gap is for whoever ran round 5 to reconcile. Rather than wait for a round-6
independent reviewer to trip over a further instance of either shape, this pass mechanically swept the
ENTIRE spec for every remaining instance of both and fixed all of them in one pass, per explicit user
direction:
1. **AC5 (round-5 Finding 1, Shape B).** No AC5 sub-case ever made BOTH the malformed condition's trigger
   (`malformed` non-empty) AND the missing condition's trigger (`mvp_max_lines is None AND mvp_max_acs is
   None`) true at once in the same `evaluate_plan_boundary` call — every sub-case paired "malformed" with
   "the other boundary validly declared" (a real int, never `None`), so the docstrings' explicit priority
   claim (malformed must win, never fall through to missing) was never exercised as a genuine race. Fixed:
   extended the existing "both directives simultaneously malformed" sub-case to also assert the downstream
   `evaluate_plan_boundary` verdict (previously it stopped at `parse_mvp_boundary`'s own output); added two
   new sub-cases pairing one malformed directive with the OTHER genuinely ABSENT from the fixture text
   (`MVP_MAX_LINES` and its `MVP_MAX_ACS` mirror), each asserting `INVALID_PLAN_BOUNDARY`/
   `malformed_mvp_boundary`, `exceeded == {}`.
2. **AC7 (round-5 Finding 2, Shape A).** The "wrong argument count (zero args, or more than one)" bullet —
   itself already the product of round 4 splitting "missing file" away from "wrong arg count" — was itself
   a 2-member class (zero-argument invocation; greater-than-one-argument invocation) collapsed into one
   assertion, the same shape recurring one level deeper than round 4 had gone. Fixed: split into two
   independently-required sub-cases, each asserting exit 2 and a stderr usage message.

Also found by actively sweeping the rest of the spec for both shapes (grepping precedence language and
scanning every AC for ungranular "X or Y" bundling, per this sweep's own methodology) — not seeded, and
reported here explicitly rather than omitted:
3. **AC10.c/AC10.d (Shape B, same pattern as round 3's own fix to sub-case b).** Sub-case b was tightened in
   round 3 to explicitly pin "with NO heading dropped in the same fixture," closing exactly this ambiguity
   for the exit-0 cell. Sub-cases c and d were never given the same pin, so under a literal reading either
   could be satisfied by a fixture that also drops a heading — collapsing onto the same cell sub-case j
   already covers (heading-dropped + AC-unaccounted) and leaving the heading-NOT-dropped + AC-unaccounted
   cell of this AC's exit-code grid never independently exercised. Fixed: both c and d now explicitly
   require "with NO heading dropped in the same fixture," mirroring b's own round-3 fix.
4. **AC5's "first match wins," valid-then-malformed direction (Shape A, surfaced via this sweep's own
   "first match wins" grep instruction).** Round 3 proved a directive malformed on its FIRST occurrence and
   validly formed on a LATER occurrence still resolves as malformed (lines/acs mirror) — but the reverse
   direction (valid FIRST, malformed LATER, which per "first match wins" must resolve as VALID) was never
   tested, and is not redundant with the existing direction: an implementation that takes the first match's
   value correctly but separately checks malformed-ness across every occurrence (not only the first) would
   pass the existing malformed-first test while wrongly flagging a valid-first fixture too. Fixed: added the
   mirrored valid-then-malformed sub-case pair (lines and acs).

The rest of the spec was swept and found clean for both shapes: AC3's `actual > declared` comparison is a
single unified check, not a two-step "equality-then-exceeded" claim, so it has no analogous joint-test gap;
AC10's b/c/d/j/k now cover all four cells of the heading-dropped x AC-unaccounted grid; the
"missing/unreadable file" pairing in AC7 and AC10.e is a single Python `OSError`-class exception path with
no plausible implementation divergence between its two members (unlike the JSON-decode-vs-OSError and
UnicodeDecode-vs-OSError splits already fixed in rounds 2/3, which cross exception-hierarchy boundaries),
so neither was split further; AC10.h's null/number pairing and AC10.i's illustrative invalid-JSON examples
are, for the same reason, genuine single conditions rather than collapsed multi-member classes.

**This sweep does not constitute round 5 or round 6 and makes no claim of authorization, closure, or
process-complete beyond the specific fixes listed above.** A round-6 independent `plan-check-verifier`
dispatch — a fresh, unprimed read of the whole spec — is still pending and required before this spec is
considered ready for implementation.

**Post-round-6 AC5 grid restructure (user-directed, combined find+fix, not an independent review round).**
Rounds 5 and 6 (the latter as characterized by this pass's own dispatch — see the record-keeping note
below) found the same underlying gap-shape twice, one branch apart, in the same function: AC5's sub-cases
locked `evaluate_plan_boundary`'s documented malformed-takes-priority contract against `REASON_MISSING`
(logic step 2) but not against `SHIP_NARROW_PLAN` (logic step 3). Patching one branch-pair at a time was not
converging, so this pass redesigned AC5 as an explicit small grid instead of an ordered-priority narrative —
the same style AC3's 8-cell grid and AC10's a-k list already use, both of which have survived 6 rounds with
zero gaps found in either.

1. **State model.** Defined 4 mutually exclusive states per dimension (`MVP_MAX_LINES`, `MVP_MAX_ACS`
   independently): (a) malformed, (b) absent, (c) valid & not exceeded, (d) valid & exceeded.
2. **Part 5.A (per-directive detection, preserved).** AC5's existing 12 sub-cases (non-numeric/negative
   detection, both-simultaneously-malformed, duplicate-directive first-match-wins in both directions, both
   dimensions mirrored throughout) were kept, relettered a1-a12 for stable addressability, with exactly two
   precision edits: sub-case a1 (the original opening example, lines malformed / acs "validly declared") and
   its acs-mirror a3 were pinned to a concrete NOT-exceeded relationship (previously "validly declared" was
   ambiguous about the actual-vs-declared relationship, which meant no existing sub-case reliably
   instantiated the "malformed vs. not-exceeded" grid cell below). No other Part 5.A content changed in
   substance.
3. **Part 5.B (the new grid, `evaluate_plan_boundary`'s malformed-priority contract).** 7 cells — every
   state-pair where at least one dimension is malformed, since that is exactly when the priority contract is
   in play. 5 of the 7 (both-malformed; malformed+absent, both directions; malformed+not-exceeded, both
   directions) were already covered by Part 5.A's existing sub-cases and are cited by reference. **2 of the
   7 (malformed+EXCEEDED, both directions — grid cells B6/B7) were newly added by this pass** — this is the
   specific gap the dispatch for this pass described as already found by "round 6."
4. **Record-keeping note, stated plainly, matching the disclosure discipline the post-round-5 systematic
   sweep applied to its own round-5 characterization above:** neither this spec file (prior to this edit)
   nor `plan_check_log.md` contains any `## Round 6` entry, dispatch record, or spec snapshot as of this
   pass — this restructure could not confirm that a round-6 `plan-check-verifier` dispatch actually produced
   the "malformed-vs-exceeded" finding from any on-disk artifact (checked: `plan_check_log.md`'s section
   list; this file's own Status header, which still read "round 6... not yet dispatched" going into this
   pass; the run directory's `spec_round*.md` snapshots, none newer than round 3; `trace.jsonl`, which has
   no recoverable role/verdict/finding fields for any dispatch beyond what rounds 1-5 already account for).
   Independently of that provenance question, this pass DID independently confirm the gap itself is real, by
   direct analysis of the live AC5 text against `evaluate_plan_boundary`'s 4-branch logic before applying
   any fix — no existing sub-case, before this pass, ever paired a malformed dimension with the OTHER
   dimension validly-declared-and-exceeded in an asserted `evaluate_plan_boundary` call. It is fixed now
   (grid cells B6/B7), regardless of whether a round 6 dispatch is ever located or reconciled separately.
5. **Documentation root-cause fix.** The Public interface section's `evaluate_plan_boundary` docstring (step
   1) and `parse_mvp_boundary` docstring previously stated malformed's priority ONLY over the
   missing-boundary outcome (step 2), never explicitly over the exceeded/`SHIP_NARROW_PLAN` outcome (step
   3) or the within-boundary outcome (step 4) — even though the actual if/elif/elif/else code structure
   always implied priority over all three. This prose gap is the likely reason AC5's sub-cases, when derived
   from that prose, only ever exercised the step-2 race explicitly. Both docstrings now state priority over
   steps 2, 3, AND 4 explicitly.
6. **Cross-references.** Added a short pointer from AC2 (the grid's `(b) absent x (b) absent` cell) and from
   AC3 (its own 8 cells) to AC5's Part 5.B, so the full 4x4=16-cell partition (AC2: 1 cell, AC3: 8 cells,
   AC5: 7 cells) is stated and independently checkable from any of the three ACs, not just AC5.
7. **Confirmatory scan (per this pass's own dispatch instruction):** scanned AC1-4, AC6-15, and the Public
   interface section for any OTHER function described via an ordered priority/precedence narrative (rather
   than an exhaustive grid) with more than 2 branches — the same shape that made `evaluate_plan_boundary`
   bug-prone. **None found.** Two near-misses were considered and are recorded here as cleared, not
   silently skipped: (a) the `--check-ac-inventory` CLI's "exit 3 takes priority over exit 1/0" claim
   (Public interface section, step 6) is only a 2-branch (not >2) relationship, and is already fully
   grid-tested by AC10's a-k list (confirmed clean in the post-round-5 sweep's own "areas checked" section
   above); (b) AC12's "on `SHIP_NARROW_PLAN`... on `INVALID_PLAN_BOUNDARY`... on `WITHIN_MVP_BOUNDARY`..."
   3-way dispatch is a switch over `evaluate_plan_boundary`'s own already-resolved, single-valued `verdict`
   string (never more than one true at once by construction), not an ordered evaluation of independent raw
   conditions — it cannot exhibit the same order-of-check bug class `evaluate_plan_boundary`'s OWN internal
   chain could, since there is nothing for a wrong check-order to race against.

Full completeness table (state-pair -> owning AC -> sub-case), reproduced from AC5's own "Completeness by
inspection" paragraph so it is checkable from this history section without cross-referencing forward:

| Dimension-pair state | Owning AC | Sub-case |
|---|---|---|
| (b,b) — both absent | AC2 | AC2's own test |
| (b,c)/(c,b)/(b,d)/(d,b)/(c,c)/(c,d)/(d,c)/(d,d) — 8 cells, neither malformed | AC3 | AC3.a-h |
| (a,a) — both malformed | AC5 | a5 = B1 |
| (a,b)/(b,a) — one malformed, other absent | AC5 | a9/a10 = B2/B3 |
| (a,c)/(c,a) — one malformed, other valid & not exceeded | AC5 | a1/a3 (pinned) = B4/B5 |
| (a,d)/(d,a) — one malformed, other valid & exceeded | AC5 | NEW = B6/B7 |

1 + 8 + 1 + 2 + 2 + 2 = 16 = 4x4, no cell double-owned or unowned.

**Round 6 -> Round 7 (`LOOP_GATE: PLAN_PASS` — plan-check converged; no spec text changed this round.)**
Full record: `runs/2026-07-18_165820-plan-size-governor/plan_check_log.md`'s `## Round 7` entry. Round 7
was dispatched as `plan-check-verifier` (a real custom subagent type) — the first genuinely independent,
unprimed read of the post-round-6-AC5-grid-restructure spec (`shasum -a 256` =
`0da4b3e59268dc9c2a0c7af68b5afd1f68852696a3c84b3bfca304de2c8a5873`). It **independently re-derived the
4x4 = 16-cell state-pair partition from first principles** (not trusting this section's own completeness
table), confirming AC2's 1 cell (both-absent) + AC3's 8 cells (neither malformed) + AC5 Part 5.B's 7
cells (B1-B7, at least one malformed) exhaustively and non-overlappingly cover all 16 — and explicitly
caught the inclusion-exclusion subtlety that a naive 4+4=8 malformed-cell count double-counts the
both-malformed cell (correct union = 7). It hand-simulated the "check-exceeded-before-malformed" bug
against every B-cell and confirmed cells **B6/B7** (malformed + other-dimension-valid-and-exceeded) are
load-bearing — a buggy implementation passes B1-B5 but returns `SHIP_NARROW_PLAN` instead of
`INVALID_PLAN_BOUNDARY` on B6/B7 — and confirmed all three malformed-vs-{missing, exceeded, within} races
are each backed by a genuinely forcing fixture. It spot-checked 12 external citations against the real
files (no defects) and confirmed AC numbering 1-15, AC5's a1-a12/B1-B7 lettering, and AC10's a-k grid are
each sequential and complete. **This is a plan-check PASS — the spec is judged ready to build against —
NOT a claim that anything is built: no code exists yet for this build (Test-writer/Coder have not run),
and no user authorization to build or ship is given or implied.** This entry records the convergence
only; `plan-check-verifier` is read-only, so **no spec text was changed by round 7.** **Credit-gate
caveat (do not overstate):** the PASS's `evidence_sha256` is the placeholder
`UNAVAILABLE_NO_HASH_TOOL_THIS_ROUND` (the role had no Bash/hash tool this round and corroborated the
reviewed-spec hash against `plan_check_log.md`'s recorded ending hash character-for-character rather than
recomputing it), so a hash-capable re-confirmation is still required before this PASS can mechanically
auto-credit a downstream Coder dispatch through the credit gate — it does not already satisfy it.
Non-blocking caveats the Verifier disclosed: sub-case a4's wording is dense but not actually ambiguous on
close reading; AC15's "~150 `H-*` ids" is approximate (round 1 found 191) but does not affect the
operative "grep first" instruction; and a 1028-vs-1029 line-count discrepancy is most likely a `wc -l`-vs-
`splitlines()` trailing-newline artifact, not content drift.

## Acceptance criteria

Exhaustive per LOOP-M5 (this spec implies a finite grid of `{lines declared?, acs declared?} ×
{exceeds?}` cells — every cell gets its own check, not a generic "review the boundary logic").

1. **[BEHAVIORAL]** `plan_size_governor.py` is importable; exposes `count_lines`, `parse_mvp_boundary`,
   `evaluate_plan_boundary`, `evaluate_spec_file` with the signatures given in the "Public interface"
   section's `plan_size_governor.py` block. **(Anchor fixed round 3 — closes round-2 Finding 2: this AC has
   no earlier content in its own bullet, so the prior "signatures above" could only mean the Public
   interface section ~170 lines prior, the same cross-section-reference risk already fixed elsewhere in
   round 2 but missed here.)**
2. **[BEHAVIORAL]** `evaluate_plan_boundary` returns `INVALID_PLAN_BOUNDARY`/`missing_mvp_boundary` when
   BOTH `mvp_max_lines` and `mvp_max_acs` are `None` — tested with both a SMALL actual size (e.g. 10
   lines / 1 AC) and a LARGE actual size (e.g. 2000 lines / 100 ACs): both must return this verdict,
   proving the check never silently guesses a threshold from the artifact's own size. **Added round 3
   (closes the `exceeded`-shape gap described in `evaluate_plan_boundary`'s docstring's round-3 fix note,
   "Public interface" section): both tests also assert `result["exceeded"] == {}`** (a dict, present and
   empty — not omitted, not `None`). **Cross-reference added in the post-round-6 AC5 grid restructure:**
   this is the `(b) absent x (b) absent` cell of the full 4x4 state grid AC5's Part 5.B documents — see
   AC5 for that full partition and for the malformed-inclusive cells this AC does not cover.
3. **[BEHAVIORAL]** Full 8-cell grid for the declared-boundary case, each its own test. **Cross-reference
   added in the post-round-6 AC5 grid restructure:** these 8 cells, together with AC2's 1 cell and AC5's
   Part 5.B's 7 cells, exhaust the full 4x4=16-cell state grid over {malformed, absent, valid-not-exceeded,
   valid-exceeded} x {malformed, absent, valid-not-exceeded, valid-exceeded} — see AC5 for that full
   partition and the malformed-inclusive cells this AC does not cover.
   **Boundary-equality lock, added round 2 (closes round-1 Finding 2):** cells b, d, and h
   below each require TWO tests, not one — a comfortably-under value AND the exact-equality
   value (`actual == max`) — because the equality point is the one value that actually
   distinguishes a correct `>` (exceeded) implementation from an incorrect `>=` one, and a
   suite that only ever tests comfortably-under values would go fully green under either
   implementation:
   a. `lines` declared only, actual lines > max -> `SHIP_NARROW_PLAN`, `exceeded` has only `lines`.
   b. `lines` declared only, actual lines <= max -> `WITHIN_MVP_BOUNDARY`. Test both a
      comfortably-under value AND `actual lines == max` — the equality case must resolve to
      `WITHIN_MVP_BOUNDARY`, locking in `>` (not `>=`) as the exceeded-comparison operator.
      **Added round 3: both variants also assert `exceeded == {}`** (present, empty dict — closes the
      `exceeded`-shape gap for this branch; see the `evaluate_plan_boundary` docstring's round-3 fix note).
   c. `acs` declared only, actual acs > max -> `SHIP_NARROW_PLAN`, `exceeded` has only `acs`.
   d. `acs` declared only, actual acs <= max -> `WITHIN_MVP_BOUNDARY`. Test both a
      comfortably-under value AND `actual acs == max`, same equality requirement as b, and (added round 3,
      same as b) both variants assert `exceeded == {}`.
   e. both declared, both exceeded -> `SHIP_NARROW_PLAN`, `exceeded` has both `lines` and `acs`.
   f. both declared, only lines exceeded -> `SHIP_NARROW_PLAN`, `exceeded` has only `lines`.
   g. both declared, only acs exceeded -> `SHIP_NARROW_PLAN`, `exceeded` has only `acs`.
   h. both declared, neither exceeded -> `WITHIN_MVP_BOUNDARY`. Test both a comfortably-under
      pair AND the pair where BOTH `actual lines == max_lines` and `actual acs == max_acs`
      simultaneously — the double-equality case, the strictest test of the `>` operator
      applied independently on both dimensions in the same call. **Added round 3: both variants also
      assert `exceeded == {}`**, same as b/d.
4. **[BEHAVIORAL]** `WITHIN_MVP_BOUNDARY`'s literal string is asserted to differ from
   `plancheck_saturation.CONTINUE_PLAN_CHECK` (`"CONTINUE_PLAN_CHECK"`) — a direct regression test
   against the collision the source research spec flagged as a live hazard. Two further assertions are
   required to reach full coverage of this AC's "provably disjoint" claim across all three verdict pairs
   (previously only this first pair had a locking assertion):
   - `INVALID_PLAN_BOUNDARY`'s literal string is asserted to differ from
     `plancheck_saturation.INVALID_TAGGING` (`"INVALID_TAGGING"`) — the most confusable pair of the three,
     both sharing the `INVALID_`-prefix convention.
   - `SHIP_NARROW_PLAN`'s literal string is asserted to differ from
     `plancheck_saturation.STOP_PROSE_REVIEW` (`"STOP_PROSE_REVIEW"`).
5. **[BEHAVIORAL]** `evaluate_plan_boundary`'s malformed-priority contract, restructured (this revision) as
   an explicit small grid per LOOP-M5 — matching AC3's 8-cell grid and AC10's a-k list's own
   verifiable-by-inspection convention — replacing the ordered-priority prose narrative this AC used
   through the post-round-5 systematic sweep. That narrative form let two branch-pair gaps go undetected
   one at a time, in separate passes, in the SAME function: malformed-vs-step-2/MISSING (found round 5,
   fixed by the post-round-5 systematic sweep above) and malformed-vs-step-3/SHIP_NARROW_PLAN (fixed by
   this pass — grid cells B6/B7 below). **Record-keeping note, stated plainly:** the dispatch for this
   pass described the second gap as already found by an independent "round 6" — but neither this file
   (prior to this edit) nor `plan_check_log.md` contains any `## Round 6` entry, dispatch record, or spec
   snapshot, and this restructure could not confirm that provenance from any on-disk artifact (see
   `## Revision history`'s matching entry for the full account). What WAS independently confirmed, by
   direct analysis of the live AC5 text against `evaluate_plan_boundary`'s 4-branch logic before any fix
   was applied: the gap itself is real — no existing AC5 sub-case pinned the "one dimension malformed,
   the OTHER validly-declared-and-EXCEEDED" state — regardless of whether a round-6 verifier dispatch
   actually produced that description. It is fixed below either way.

   **State model.** For each of `MVP_MAX_LINES` and `MVP_MAX_ACS` independently, exactly one of 4 states
   holds, relative to a single `evaluate_plan_boundary` call:
   - **(a) malformed** — a directive line for this dimension is present in the fixture text, but its
     captured value does not parse as a non-negative int (non-numeric, or syntactically-valid-but-negative)
     — `parse_mvp_boundary` places the directive's key name in `malformed`, and the corresponding
     `mvp_max_lines`/`mvp_max_acs` value passed to `evaluate_plan_boundary` is `None`.
   - **(b) absent** — no directive line for this dimension appears anywhere in the fixture text at all —
     `mvp_max_lines`/`mvp_max_acs` is `None`, and the dimension's name is NOT in `malformed`.
   - **(c) valid, not exceeded** — a directive line is present with a value that DOES parse as a
     non-negative int, and the fixture's actual count for that dimension is `<=` the declared value.
   - **(d) valid, exceeded** — same as (c), except the actual count is `>` the declared value.

   Only (a) and (b) can make a dimension's `mvp_max_lines`/`mvp_max_acs` value `None`; (c) and (d) always
   supply a real int. Only (a) puts the dimension's name in `malformed`.

   **Part 5.A — per-directive detection (`parse_mvp_boundary`): does a single dimension resolve to state
   (a) correctly, including under repetition?** These sub-cases establish HOW a dimension lands in state
   (a) vs (c) in the first place — first-match-wins ordering, non-numeric vs negative detection — each one
   pairs its dimension-under-test with the OTHER dimension pinned to a concrete, boring state (never left
   ambiguous, unlike before this revision) so it cannot be confused with, or silently substitute for, one
   of Part 5.B's grid cells below:
   a1. **Base case — `MVP_MAX_LINES: not-a-number`, with `MVP_MAX_ACS: 50` validly declared AND NOT
       exceeded** (the fixture's actual distinct AC-token count is comfortably under 50, e.g. 5) ->
       `parse_mvp_boundary(...)["malformed"] == ["mvp_max_lines"]`, and
       `evaluate_plan_boundary(actual_lines=<any>, actual_acs=5, mvp_max_lines=None, mvp_max_acs=50,
       malformed=["mvp_max_lines"])` returns `INVALID_PLAN_BOUNDARY`/`malformed_mvp_boundary`,
       `exceeded == {}`. **(Pinned this revision — closes an ambiguity this restructure found: previously
       this sub-case said only "the OTHER boundary is validly declared," without stating whether the
       fixture's actual acs count was under, over, or at that boundary, so no single existing sub-case
       reliably instantiated grid cell B4 below. This pin is what lets this sub-case now serve as B4's
       citation. Originally added round 1 Finding 4 / round 3 `exceeded=={}` fix — see prior revision
       history entries for that lineage.)**
   a2. **`MVP_MAX_LINES: -5`** (syntactically-valid negative) -> `parse_mvp_boundary(...)["malformed"] ==
       ["mvp_max_lines"]`. Parse-level only — no `evaluate_plan_boundary` assertion required here, since
       the downstream priority behavior for ANY reason a dimension lands in `malformed` is already
       exercised end-to-end by a1/a3/a5/a9/a10 below; this sub-case's own job is narrower: proving the
       negative-value guard, not the numeric-vs-non-numeric guard, also lands the directive in
       `malformed`. **Added round 2, closes round-1 Finding 4 — unchanged this revision.**
   a3. **`MVP_MAX_ACS: not-a-number`, with `MVP_MAX_LINES: 500` validly declared AND NOT exceeded** (the
       fixture text is naturally well under 500 lines) -> mirror of a1: `parse_mvp_boundary(...)["malformed"]
       == ["mvp_max_acs"]`, and `evaluate_plan_boundary(actual_lines=<small>, actual_acs=<any>,
       mvp_max_lines=500, mvp_max_acs=None, malformed=["mvp_max_acs"])` returns
       `INVALID_PLAN_BOUNDARY`/`malformed_mvp_boundary`, `exceeded == {}`. **(Pinned this revision, same
       reason and same B5 citation role as a1's pin above. Originally added round 3, isolating the acs
       dimension independently of lines per AC3's own b/d precedent.)**
   a4. **`MVP_MAX_ACS: -5`, with `MVP_MAX_LINES` in the same pinned state as a3** -> same assertions as a3
       (mirror of a2), inheriting a3's now-pinned "lines validly declared and not exceeded" state via this
       cross-reference rather than restating it — isolating the negative-value guard specifically on the
       acs dimension. **Added round 3 — unchanged in substance this revision, cross-reference target
       renamed from prose to "a3."**
   a5. **Both directives simultaneously malformed** (`MVP_MAX_LINES: not-a-number` AND `MVP_MAX_ACS: -5` in
       the same text) -> `parse_mvp_boundary(...)["malformed"]` contains BOTH `"mvp_max_lines"` AND
       `"mvp_max_acs"` (order not asserted), AND `evaluate_plan_boundary(actual_lines=<any>,
       actual_acs=<any>, mvp_max_lines=None, mvp_max_acs=None, malformed=["mvp_max_lines", "mvp_max_acs"])`
       returns `INVALID_PLAN_BOUNDARY`/`malformed_mvp_boundary`, `exceeded == {}`. Distinct from a1/a3: a
       `parse_mvp_boundary` that early-`return`s after the first malformed hit would silently drop the
       second, which the list-content assertion (`contains BOTH`) — not just the downstream verdict —
       is what actually catches. **Added round 3; extended with the `evaluate_plan_boundary` call in the
       post-round-5 systematic sweep — unchanged this revision. Serves as grid cell B1 below.**
   a6. **A directive repeated more than once, both occurrences validly formed with DIFFERENT values** (e.g.
       `MVP_MAX_LINES: 500` then later `MVP_MAX_LINES: 900`) -> first value wins:
       `parse_mvp_boundary(...)["mvp_max_lines"] == 500`, not `900`, no error. **Added round 3 — unchanged
       this revision.** (Noted, not fixed, this revision: no `MVP_MAX_ACS`-dimension mirror of this specific
       "both-valid, different-values" case exists in this AC; that asymmetry pre-dates this revision, is
       not part of `evaluate_plan_boundary`'s malformed-priority contract this restructure targets — it is
       orthogonal, a `parse_mvp_boundary`-only, both-values-valid case — and is left unchanged here as out
       of scope for this dispatch.)
   a7. **`MVP_MAX_LINES` malformed on its FIRST occurrence, validly formed on a LATER occurrence** (e.g.
       `not-a-number` then later `500`) must still resolve MALFORMED, per "first match wins" ->
       `parse_mvp_boundary(...)["malformed"] == ["mvp_max_lines"]`, and
       `evaluate_plan_boundary(..., malformed=["mvp_max_lines"])` returns
       `INVALID_PLAN_BOUNDARY`/`malformed_mvp_boundary`, `exceeded == {}`. **Added round 3 — unchanged this
       revision.**
   a8. **Mirror of a7 for `MVP_MAX_ACS`** — same assertions and rationale, isolating "first match wins" on
       the acs dimension. **Added round 3 — unchanged this revision.**
   a9. **`MVP_MAX_LINES: not-a-number`, with NO `MVP_MAX_ACS` directive line anywhere in the fixture text**
       (genuinely absent, not merely unmentioned in the assertion) -> `parse_mvp_boundary(...) ==
       {"mvp_max_lines": None, "mvp_max_acs": None, "malformed": ["mvp_max_lines"]}`, and
       `evaluate_plan_boundary(actual_lines=<any>, actual_acs=<any>, mvp_max_lines=None, mvp_max_acs=None,
       malformed=["mvp_max_lines"])` returns `INVALID_PLAN_BOUNDARY`/`malformed_mvp_boundary`, NOT
       `missing_mvp_boundary`, `exceeded == {}`. **Added in the post-round-5 systematic sweep (closed
       round-5 Finding 1) — unchanged this revision. Serves as grid cell B2 below.**
   a10. **Mirror of a9: `MVP_MAX_ACS: -5`, with NO `MVP_MAX_LINES` directive line anywhere in the fixture
        text** -> same shape, isolating the priority requirement on the acs dimension. **Added in the
        post-round-5 systematic sweep — unchanged this revision. Serves as grid cell B3 below.**
   a11. **`MVP_MAX_LINES` validly formed on its FIRST occurrence, malformed on a LATER occurrence** (e.g.
        `500` then later `not-a-number`, with `MVP_MAX_ACS` validly declared) must resolve VALID, per
        "first match wins" -> `parse_mvp_boundary(...)["mvp_max_lines"] == 500`, and `malformed` does NOT
        contain `"mvp_max_lines"` — the later malformed occurrence is never reached. **Added in the
        post-round-5 systematic sweep — unchanged this revision.**
   a12. **Mirror of a11 for `MVP_MAX_ACS`** — same assertions and rationale. **Added in the post-round-5
        systematic sweep — unchanged this revision.**

   **Part 5.B — `evaluate_plan_boundary`'s malformed-priority grid.** `evaluate_plan_boundary`'s logic (see
   the "Public interface" section's `plan_size_governor.py` block) is a 4-branch if/elif/elif/else chain:
   step 1 malformed-check, step 2 both-None-check ("missing"), step 3 at-least-one-exceeded-check ("ship
   narrow"), step 4 else ("within boundary"). Step 1 is a genuine SHORT-CIRCUIT over steps 2-4 alike (this
   revision also tightened the Public interface section's own docstring prose to state this explicitly,
   where previously it named only the priority-over-step-2 relationship). Since only state (a) can ever
   make step 1's own trigger (`malformed` non-empty) true, the grid below covers every state-pair where AT
   LEAST ONE dimension is in state (a) — exactly the cells where step 1's priority claim is actually in
   play. Every cell requires `INVALID_PLAN_BOUNDARY`/`malformed_mvp_boundary`, `exceeded == {}`, regardless
   of what the OTHER dimension's state would otherwise have produced:

   | Cell | `MVP_MAX_LINES` state | `MVP_MAX_ACS` state | What step 1 overrides | Sub-case |
   |------|------------------------|----------------------|------------------------|----------|
   | B1 | (a) malformed | (a) malformed | step 2 (MISSING) | = a5 |
   | B2 | (a) malformed | (b) absent | step 2 (MISSING) | = a9 |
   | B3 | (b) absent | (a) malformed | step 2 (MISSING) | = a10 (mirror of B2) |
   | B4 | (a) malformed | (c) valid, not exceeded | step 4 (WITHIN_MVP_BOUNDARY) | = a1 |
   | B5 | (c) valid, not exceeded | (a) malformed | step 4 (WITHIN_MVP_BOUNDARY) | = a3 (mirror of B4) |
   | B6 | (a) malformed | (d) valid, exceeded | step 3 (SHIP_NARROW_PLAN) | NEW, below |
   | B7 | (d) valid, exceeded | (a) malformed | step 3 (SHIP_NARROW_PLAN) | NEW, below (mirror of B6) |

   B1-B5 are satisfied entirely by Part 5.A's a5/a9/a10/a1/a3 as pinned/cited above — no further text
   needed for those five. **B6 and B7 are new this revision** — the gap this pass's dispatch described as
   already-found ("round 6"), verified genuinely absent from the pre-restructure spec text (see the
   record-keeping note above) before being added here:
   - **B6 — `MVP_MAX_LINES: not-a-number` (malformed) with `MVP_MAX_ACS: 2` validly declared AND EXCEEDED**
     (the fixture's actual distinct AC-token count is deliberately above 2, e.g. 5 real `AC<k>` tokens) ->
     `parse_mvp_boundary(...) == {"mvp_max_lines": None, "mvp_max_acs": 2, "malformed": ["mvp_max_lines"]}`,
     and `evaluate_plan_boundary(actual_lines=<any>, actual_acs=5, mvp_max_lines=None, mvp_max_acs=2,
     malformed=["mvp_max_lines"])` returns `INVALID_PLAN_BOUNDARY`/`malformed_mvp_boundary`, `exceeded ==
     {}` — NOT `SHIP_NARROW_PLAN`, which step 3 alone would produce given `mvp_max_acs=2` is declared and
     `5 > 2` exceeds it. This is the genuine race step 1 vs step 3: without the malformed short-circuit,
     step 3 (not step 2 or step 4) is what execution would otherwise reach, since the other dimension is
     both declared AND exceeded. An implementation that checks "any dimension exceeded" (step 3) before,
     or instead of, "any dimension malformed" (step 1) — e.g. because a Coder reads the docstring's
     numbered steps as informational ordering rather than as a strict short-circuit and implements
     `if any_exceeded: SHIP_NARROW elif malformed: INVALID/MALFORMED ...` — would pass every B1-B5 cell
     above (step 3's own condition is never true in any of them, since none pairs malformed with a
     declared-and-exceeded dimension) while silently returning `SHIP_NARROW_PLAN` here instead of the
     documented `INVALID_PLAN_BOUNDARY`.
   - **B7 — mirror: `MVP_MAX_ACS: not-a-number` (malformed) with `MVP_MAX_LINES: 3` validly declared AND
     EXCEEDED** (the fixture text is deliberately more than 3 lines long, e.g. 10) ->
     `parse_mvp_boundary(...) == {"mvp_max_lines": 3, "mvp_max_acs": None, "malformed": ["mvp_max_acs"]}`,
     and `evaluate_plan_boundary(actual_lines=10, actual_acs=<any>, mvp_max_lines=3, mvp_max_acs=None,
     malformed=["mvp_max_acs"])` returns `INVALID_PLAN_BOUNDARY`/`malformed_mvp_boundary`, `exceeded ==
     {}` — NOT `SHIP_NARROW_PLAN`. Isolates the same step-1-vs-step-3 race specifically on the acs
     dimension, mirroring this spec's lines/acs-independence convention (AC3's b/d split; a1/a3, a9/a10,
     a11/a12 above).

   **Completeness by inspection.** `MVP_MAX_LINES` and `MVP_MAX_ACS` each independently occupy one of the
   4 states (a)-(d) defined above — a 4x4 = 16-cell full cross product. Every cell is owned by exactly one
   AC in this spec, stated here so the partition can be checked by inspection rather than trusted by prose
   claim:
   - **1 cell** — (b) absent x (b) absent, i.e. both `None` with neither malformed — is AC2's
     `missing_mvp_boundary` case.
   - **8 cells** — every combination of {(b) absent, (c) not exceeded, (d) exceeded} x {(b) absent, (c) not
     exceeded, (d) exceeded} EXCEPT the double-(b) cell AC2 already owns — is AC3's existing 8-cell grid:
     (d,b)=AC3.a, (c,b)=AC3.b, (b,d)=AC3.c, (b,c)=AC3.d, (d,d)=AC3.e, (d,c)=AC3.f, (c,d)=AC3.g, (c,c)=AC3.h
     (`(lines-state, acs-state)` pairs; letters per AC3's own lettering, not restated here as a second
     source of truth for that AC's content).
   - **7 cells** — every combination where at least one dimension is (a) malformed — is this AC's Part 5.B,
     table above (B1-B7).
   - 1 + 8 + 7 = 16 = 4 x 4. No cell is owned by zero ACs or by more than one; every state-pair
     `evaluate_plan_boundary` can actually receive across its 4-branch chain is accounted for by
     construction, not by narrative claim of priority.
6. **[BEHAVIORAL]** `evaluate_spec_file` on a real temp-file fixture (containing `MVP_MAX_LINES:`/
   `MVP_MAX_ACS:` directives, N real lines, and M distinct `AC<k>` tokens) returns actual counts that
   exactly match the fixture's constructed N and M. **Added round 4 (closes round-4 Finding 3,
   secondary/cosmetic):** the fixture MUST include at least one `AC<k>` token mentioned more than once
   (e.g. `AC7` appearing twice) — without a forced repeat, nothing distinguishes a correctly-deduping
   implementation from one that does not dedupe at all, since both produce the same count when no token
   repeats. The assertion must confirm the returned `acs` count still equals M, the DISTINCT token count,
   despite the repeat (i.e. strictly less than the fixture's total AC-token occurrence count).
7. **[BEHAVIORAL]** CLI: `python3 plan_size_governor.py <spec_file>` prints valid JSON matching
   `evaluate_spec_file`'s shape and exits 0 for a fixture that produces EACH of the three verdicts (three
   separate CLI-level tests, not just the importable-function tests) — proving exit code never encodes
   verdict. **Added round 4 (closes round-4 Finding 2):** missing file and wrong arg count are
   INDEPENDENTLY-REQUIRED test cases, not one combined fixture — matching the granularity convention
   AC3/AC10 already use elsewhere in this spec ("N separate tests," never a single fixture standing in for
   multiple cases). The real `spec_revision_diff.py main()` treats these as two structurally separate code
   branches (an `if len(args) != 2` argv-length check, distinct from the `try/except OSError` around each
   file `open()`), and its own sibling `TestUsageErrors` class already tests them as three separate methods
   (`test_missing_old_file_exits_2`, `test_missing_new_file_exits_2`, `test_wrong_arg_count_exits_2`) rather
   than one combined test. **(Further split in the post-round-5 systematic sweep, closes round-5 Finding
   2: round 4 established "missing file" and "wrong arg count" as independent categories but left "wrong
   arg count" itself bundling zero-arg and greater-than-one-arg invocations under one assertion — the
   third bullet below.)** All three of the following must be independently tested here, each asserting
   exit 2 with a usage message on stderr:
   - **Missing/unreadable spec file** -> exit 2, stderr usage message.
   - **Zero-argument invocation** (`python3 plan_size_governor.py` with no `spec_file` argument at all) ->
     exit 2, stderr usage message. A CLI that reads `sys.argv[1]` before checking argv length, guarded only
     by `except OSError` around the file-open call, would raise an uncaught `IndexError` on a zero-arg
     invocation (Python's default uncaught-exception exit code 1, not the documented 2) — a bug a
     missing-file-only fixture can never expose, since it always supplies a well-formed single argument.
   - **Greater-than-one-argument invocation** (e.g. `python3 plan_size_governor.py <spec_file>
     <extra_arg>`) -> exit 2, stderr usage message. **(Split out from the single "zero args, or more than
     one" bullet in the post-round-5 systematic sweep, closes round-5 Finding 2 — that bullet was itself a
     2-member class collapsed into one assertion, the same shape round 4 had already split "missing file"
     away from "wrong arg count" for, just recurring one level deeper.)** This is a DISTINCT failure mode
     from the zero-argument case above, not a variant collapsible into it: a CLI that guards only a lower
     bound (e.g. `if len(sys.argv) < 2: usage_error()`, a common single-sided-range oversight) would
     correctly reject zero args yet silently accept and run on trailing extra arguments — ignoring them
     rather than reporting the documented usage error — passing the zero-argument sub-case above while
     still violating this AC's own "wrong argument count -> exit 2" contract. A fix for the under-count
     guard does not imply the over-count guard exists, and vice versa, so each requires its own
     independent fixture.

   **Added round 3 (closes the `evaluate_spec_file` UnicodeDecodeError gap above):** a spec_file that
   exists and is readable but contains non-UTF-8 bytes (e.g. write a fixture with `open(path,
   "wb").write(b"\xff\xfe...")`) -> exit 2 via the real CLI, stderr usage message, NOT an uncaught
   traceback — the same "exists/readable but fails to parse as the expected format" shape as AC10.i's
   invalid-JSON case, applied here to the spec file's own encoding.
8. **[DOC]** Module docstring states: the AC-token false-positive risk (candidly, per house style), that
   a boundary is evaluated per-declared-dimension (declaring only one of the two is valid and sufficient
   to authorize a verdict on that dimension), and that this governor **never suppresses a plan-check
   round** — it is a cut test, not a stop test, and `SHIP_NARROW_PLAN` always requires a FRESH plan-check
   round on the narrowed artifact afterward (cites the research spec's Part 4.1 "Also required" clause and
   `H-SPEC-REWRITE-DIFF-1`'s full-rewrite risk).
9. **[BEHAVIORAL]** `spec_revision_diff.py` gains `extract_ac_ids` per the "Public interface" section's
   `spec_revision_diff.py` block. Unit test mirrors `TestExtractHeadingsUnit`'s structural shape only
   (direct function calls isolated from file I/O — no subprocess/CLI — the same isolation
   `TestExtractHeadingsUnit` itself uses), NOT its dedup coverage: `TestExtractHeadingsUnit` never itself
   tests dedup on `extract_headings` (which does not dedupe at all — see the Public interface section's
   `extract_ac_ids` docstring for the corrected citation); its one dedup-relevant test,
   `test_duplicate_old_heading_reported_once`, exercises the sibling `find_dropped_headings`, not
   `extract_headings`. `extract_ac_ids` itself must dedupe INTERNALLY per its own docstring, so the new
   unit test asserts that directly, as `extract_ac_ids`'s own requirement rather than an inheritance from
   `TestExtractHeadingsUnit`: distinct tokens in first-occurrence order, duplicates collapsed, tokens found
   both inside and outside heading lines.
10. **[BEHAVIORAL]** `--check-ac-inventory` end-to-end, via the real CLI (subprocess), covering:
    a. Clean case: no headings dropped, no ACs dropped -> exit 0.
    b. AC dropped but present in ledger's `deferred_ac_ids`, with NO heading dropped in the same fixture ->
       exit 0 (heading-diff alone contributes nothing here), confirming message names the retained-as-deferred
       AC. **(Tightened round 3: previously worded "exit reflects heading-diff alone (0 or 1 depending on
       headings)," which left it ambiguous whether a test needed to actually construct both variants or
       could satisfy the AC by exercising only one; sub-case b now pins the no-heading-drop/exit-0 variant
       specifically, and sub-case k below adds the heading-drop/exit-1 variant combined with an
       accounted-for AC.)**
    c. AC dropped and NOT in ledger, with NO heading dropped in the same fixture -> exit 3, output names
       the specific unaccounted AC id(s). **(Pinned in the post-round-5 systematic sweep — a new finding,
       not one of the 2 seeded instances: without this pin, a fixture satisfying this sub-case could
       coincidentally also drop a heading, leaving the heading-NOT-dropped / AC-unaccounted cell of this
       AC's exit-code grid — the mirror of what sub-case b already pins for the exit-0 cell — never
       independently exercised. Sub-case j below already covers the heading-dropped + AC-unaccounted
       combination, so this sub-case must isolate the other one, matching the same discipline round 3
       already applied to tighten sub-case b.)**
    d. AC dropped, some accounted (deferred) and some not, with NO heading dropped in the same fixture ->
       exit 3, output distinguishes the two. **(Pinned in the post-round-5 systematic sweep, same finding
       and rationale as sub-case c immediately above.)**
    e. Missing/unreadable ledger path -> exit 2, never treated as "zero deferred."
    f. Ledger file whose top-level JSON is not a list -> exit 2.
    g. Ledger entry with no `deferred_ac_ids` key at all (pre-existing real-shaped entries, e.g. the ones
       already in the real `hardening_ledger.json`) does not error — contributes nothing, exercised
       against a copy of a REAL entry shape from the actual ledger (schema fields present, no
       `deferred_ac_ids`).
    h. **Added round 2 (closes round-1 Finding 3):** ledger entry with `deferred_ac_ids` present but NOT a
       list, covering TWO distinct sub-values because they exercise different failure modes:
       - `"deferred_ac_ids": null` (JSON null -> Python `None`). This is the sub-value that actually
         distinguishes a guarded from an unguarded implementation: `dict.get("deferred_ac_ids", [])`
         returns `None` here, NOT the `[]` default, because the key IS present (just null-valued) — a
         plain `set().update(None)` (or any bare iteration over `None`) raises `TypeError`, an uncaught
         crash that violates the "never an error" contract. The guarded implementation must instead
         produce a clean, non-crashing "contributes nothing" result. Also test a JSON number (e.g.
         `"deferred_ac_ids": 7`) for the same non-iterable-crash reason.
       - `"deferred_ac_ids": "AC7"` (a bare string). This does NOT crash even without the guard — Python
         iterates a string into its individual characters, and since every real extracted AC id is at
         least 3 characters (`AC_ID_RE` requires literal `AC` plus digits), no single-character fragment
         can ever collide with a real dropped AC id via the `unaccounted` membership check. **What the
         test must assert, precisely** (this sub-value must NOT be described or tested as proof that a
         dropped AC gets wrongly marked accounted-for; it does not, with or without the guard, given this
         repo's AC-id token shape): build the fixture with a SEPARATE AC genuinely dropped and not
         accounted for anywhere else in the ledger, alongside this bare-string entry, then assert via the
         real CLI (a) that AC's id still appears in the `UNACCOUNTED:` output — proving `"A"`/`"C"`/`"7"`
         did not silently enter the effective `deferred_ac_ids` set and rescue it — and (b) the process
         exit code is **3**, the same well-defined UNACCOUNTED code sub-case c uses, unaffected by the
         malformed entry's presence (not a crash, not exit 0, not any other code).
    i. **Added round 3 (closes round-2 Finding 1):** ledger file that EXISTS and IS readable, but whose
       content is not syntactically valid JSON (e.g. truncated/corrupted text, a trailing comma, or plain
       non-JSON text) — via the real CLI/subprocess. Must exit **2** (usage error), the same as sub-cases e
       and f, and the process must NOT crash with an unhandled traceback. This is a DISTINCT failure mode
       from e (a missing/unreadable file — an `OSError`-class problem raised by `open()`) and from f (a
       file that parses fine as JSON but has the wrong top-level shape): `json.load`/`json.loads` raises
       `json.JSONDecodeError`, which is a **`ValueError` subclass, not an `OSError` subclass** — an
       implementation that catches only `OSError` around the file-open step (the natural reading of how
       sub-case e is satisfied) will NOT catch this, and an uncaught Python exception exits with code 1 by
       default. That default exit-1 would collide with THIS SAME TOOL's own pre-existing, differently-scoped
       exit-1 meaning ("headings dropped, advisory" — unrelated to the ledger at all), so a caller branching
       on exit codes (per AC12's new `orchestrator.md` bullet) could misread a silently-crashed AC-inventory
       check as a harmless advisory — precisely the "Key rule 2: silent AC drops are a hard failure"
       scenario this build exists to prevent. Public interface step 3 already states the contract correctly
       in prose ("invalid JSON... usage error (exit 2)"); this sub-case is what actually forces an
       implementation to catch `json.JSONDecodeError` (or the broader `ValueError`) as its own explicit
       case, separately from the file-access exception path.
    j. **Added round 3 (self-identified by Oga, same discipline as the AC5 additions above):** a single
       fixture pair where BOTH conditions hold at once — at least one heading is dropped between old and
       new file (which, on its own, the pre-existing heading-diff logic alone would report as exit 1) AND
       at least one AC is dropped and NOT accounted for in the ledger (exit 3 on its own). Assert the
       combined real-CLI exit code is **3, not 1** — this is the one end-to-end fixture that actually
       exercises Public interface step 6's explicit priority claim ("Exit 3 takes priority over exit 1/0
       from the heading-diff part of the same invocation"), which up through sub-case i is asserted only in
       prose and never in a test where both failure conditions are simultaneously present in one real
       invocation. Also assert the printed output still contains the `UNACCOUNTED:` line (the combined exit
       code must not hide which specific check actually triggered it).
    k. **Added round 3, closing a self-contradiction found by both round-3 lenses independently:** the
       fixture sub-case b's own parenthetical actually promises — heading dropped (which alone would yield
       exit 1) AND every dropped AC accounted for in `deferred_ac_ids` (or no AC dropped at all) -> the
       combined real-CLI exit code is **1, not 3 and not 0**. This is a DIFFERENT cell from j: j proves
       exit-3 wins when the AC-side is genuinely unaccounted; k proves the AC-inventory check does NOT
       spuriously force a nonzero-3 exit merely because a heading was dropped elsewhere in the same
       invocation, i.e. that Public interface step 7 ("the AC check does not independently force a nonzero
       exit when everything is accounted for") holds even in the presence of an unrelated heading drop, not
       only in isolation. Before this sub-case existed, no test in this AC actually exercised this cell —
       sub-case b's own text asserted it was covered by j, and it was not; an implementation that let ANY
       heading-drop leak into forcing exit 3 (contrary to step 7) would have shipped with a fully green
       suite, and AC12's `orchestrator.md` bullet treats a nonzero-3 exit as a hard block, so this bug would
       have caused Oga to wrongly treat a clean `SHIP_NARROW_PLAN` cut-and-reissue as blocked.
    l. **Added this revision (independent Verifier finding, gap_type: DESIGN):** a ledger file whose
       top-level IS a valid JSON list, but one element of that list is not itself a JSON object (e.g. a
       bare string, a number, `null`, or a nested array standing in for an entry) — via the real CLI —
       must exit **2** (usage error) with a stderr usage message, NOT an uncaught traceback. This is
       distinct from sub-case f (top-level itself not a list) and from every other sub-case in this list
       (which all assume well-formed dict entries): a good-faith `entry.get("deferred_ac_ids", [])`
       implementation with no `isinstance(entry, dict)` guard would raise `AttributeError` on the
       malformed element, defaulting to exit 1 — the same "wrong default exit code collides with this
       tool's own pre-existing exit-1 meaning" shape sub-case i already closes for invalid-ledger-JSON,
       applied here to a valid-JSON-but-wrong-element-shape ledger instead.
11. **[BEHAVIORAL]** Every existing test in `test_spec_revision_diff.py` (`TestNoDroppedHeadingsExitsZero`,
    `TestDroppedHeadingDetected`, `TestExactMatchNotFuzzy`, `TestUsageErrors`, `TestExtractHeadingsUnit`,
    `TestRealFilesDoNotCrash`) still passes, unmodified, after this extension — regression gate, not a
    new test.
12. **[DOC, framework]** `loop-team/orchestrator.md` step 1's plan-check bullet list gains a new bullet,
    inserted immediately after the existing `[BINDING]`/`[LOGIC]`/`[CONCURRENCY]`/`[SECURITY]` tag-sequence
    bullet (the one citing `DESIGN_CHECKLIST.md gate 10` and `plancheck_saturation.py` by reference) and
    before "2. **Dispatch Test-writer**". Content (paraphrased here; Coder writes the final prose, matching
    this file's existing bold-lead-sentence + citation style):
    - Before dispatching every plan-check round (not only the first), run
      `python3 <BASE_DIR>/loop-team/harness/plan_size_governor.py <spec_path>`.
    - On `SHIP_NARROW_PLAN`: this is a CUT test, never a stop test. Cut the spec to its own declared MVP
      boundary. Defer every cut AC into a new `hardening_ledger.json` entry's `deferred_ac_ids` field
      (cite the mechanism + schema). Then MANDATORILY run `spec_revision_diff.py <old_spec> <new_spec>
      --check-ac-inventory <hardening_ledger.json>` before dispatching the next plan-check round on the
      narrowed spec (mirrors the existing `H-SPEC-REWRITE-DIFF-1` full-rewrite usage note — a
      `SHIP_NARROW_PLAN` cut IS that kind of rewrite). A nonzero (3) exit is a hard block: resolve every
      unaccounted AC — restore it into the spec, or explicitly add it to `deferred_ac_ids` — before
      proceeding. The cut is NEVER a terminal state: a fresh plan-check round on the smaller spec is
      still required afterward.
    - On `INVALID_PLAN_BOUNDARY` (either reason): this is NOT authorization to cut anything.
      `SHIP_NARROW_PLAN` is only ever legal once an explicit `MVP_MAX_LINES`/`MVP_MAX_ACS` boundary exists
      in the spec — state/fix the boundary directive first, then re-run the governor.
    - On `WITHIN_MVP_BOUNDARY`: no action; plan-check proceeds normally.
    - State explicitly: this governor never suppresses or substitutes for a plan-check round — cite the
      research spec (`research/2026-07-16-planning-stop-governor-internal-grounding-redteam.md` Part 4.1)
      and the TaxAhead 782→97 precedent (`learnings.md`).
    Per `orchestrator.md`'s OWN standing rule (the bullet immediately preceding the insertion point, and
    the file-class rule at the top of step 1), this edit — being to `orchestrator.md` itself — REQUIRES
    full plan-check regardless of how small the diff looks; this spec/plan-check round covers it.
13. **[DOC, framework]** `LOOP_TEAM_STANDARD.md` gains a short pointer (a few lines, not a restatement of
    the mechanism) referencing the plan-size governor and pointing at `orchestrator.md`'s fuller treatment
    plus the source research doc, in that file's existing "See also"-style citation convention (end of
    file). Not a duplication — `orchestrator.md` stays the single source of truth for the mechanism's
    substance (same "cite by reference, don't duplicate" discipline `orchestrator.md` itself already
    applies to `DESIGN_CHECKLIST.md` gate 10).
14. **[BEHAVIORAL, process]** Both framework-file edits (`orchestrator.md`, `LOOP_TEAM_STANDARD.md`) go
    through the FULL "Review-to-commit re-diff" mandatory gate already standing in `orchestrator.md` for
    this exact file class — **[Added round 2, closes round-1 Finding 1]: this means BOTH of the following
    steps, not `record` alone**, since `record` alone leaves the actual commit unblocked and open to a
    raw `git commit` that bypasses the gate entirely (reproducing the exact failure class closed by commits
    `96693f8`/`5884604`):
    1. `python3 commit_diff_reread.py record <file>` for each of `orchestrator.md` and
       `LOOP_TEAM_STANDARD.md`, immediately after Oga's own review of the final diff for that file.
    2. Commit ONLY via `python3 commit_diff_reread.py commit orchestrator.md LOOP_TEAM_STANDARD.md --
       <message>` (both files in one invocation, per the tool's own re-check-all-listed-files-together
       contract) — **never** a raw `git add`/`git commit` on either file. A `commit` exit code of 1
       (blocked — mismatch or missing snapshot) or 2 (usage error) means the gate did its job; resolve the
       cause and re-run `record` + `commit`, do not fall back to a raw git command.
15. **[DOC]** A new `fix_plan.md` entry documents this build: problem, root cause (the research spec's
    3-ground refutation of `EXPECTED_PLAN_CHANGE` + what was salvaged), the fix (this interface), and
    justification/citations (the hash-verified source spec, `H-SPEC-REWRITE-DIFF-1`, `H-SPEC-XREF-1`,
    `learnings.md`'s TaxAhead precedent) — id collision-checked against the existing ~150 `H-*` ids before
    naming it (grep first, per `H-SPEC-XREF-1`'s own documented practice).

## Constraints

- Python stdlib-only for both `plan_size_governor.py` and the `spec_revision_diff.py` extension — matches
  every sibling harness script's documented convention (no third-party deps).
- No hard-coding to fixture values — general boundary-comparison logic, not special-cased test inputs.
- `plan_size_governor.py` must NOT import from `plancheck_saturation.py` or `plan_check_records.py` (see
  non-goals) — it may (and should) import `extract_ac_ids` from `spec_revision_diff.py` (a bare import,
  matching the existing `plancheck_saturation.py` -> `plan_check_records` import convention — both live in
  the same harness directory, no `sys.path` insertion needed or used by that precedent). **(Citation
  corrected round 4, closes round-4 Finding 4, secondary/cosmetic: previously cited as "sys.path
  insertion" — the real `plancheck_saturation.py` -> `plan_check_records` import is a bare
  `from plan_check_records import (...)` with no `sys.path.insert()` anywhere in that file; the real
  `sys.path.insert(0, HERE)` precedent is `test_spec_revision_diff.py`'s own test-file sibling-import
  convention, a different file serving a different purpose.)**
- Do not modify `hardening_ledger.json`'s real content.

<!-- hash-bump 2026-07-18: re-dispatch after a harness tool-result formatting artifact (a trailing
<usage> block glued onto the prior Verifier's agentId suffix with no separating newline) caused the
credit-gate to misclassify a substantively genuine PLAN_PASS as "unexpected content after final gate
line" -- this permanently vetoes credit for the prior hash per prior_verifier_credit()'s unconditional
per-hash veto rule, so a fresh hash + a fresh Verifier dispatch is the documented recovery, not a retry
against the same hash. No operative content above this line changed. -->
