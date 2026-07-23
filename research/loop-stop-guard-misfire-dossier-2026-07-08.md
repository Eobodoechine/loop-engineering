# loop_stop_guard.py — Mode B Coder-unblock dossier: two false-positive misfires (2026-07-08)

**Status:** diagnosis + precedent only. No fix proposed, no code edited, no sub-agents
spawned during this research (Mode B constraint honored).

**Dispatch context:** a single session on 2026-07-08 dispatched ONLY `subagent_type:
"researcher"` Agent calls (no Coder, no Verifier) and still tripped two separate
`loop_stop_guard.py` gates. This dossier grounds both root causes directly in the live
source (quoted, with line numbers), cites the fix_plan.md precedent this framework has
for gate-hole fixes (H-AC-ORACLE-TARGET-1 as the template; H-GUARD-3/H-GUARD-4/H-LT4/H-LT6
as prior guard-fix precedent on this exact file), confirms the hook-registration/trust
question, and reports existing eval coverage so a future test-writer doesn't duplicate work.

Files read in full for this dossier:
- `<HOME>/Claude/loop/hooks/loop_stop_guard.py` (1360 lines)
- `<HOME>/Claude/loop/hooks/verifier_hygiene_scan.py` (151 lines)
- `<HOME>/Claude/loop/fix_plan.md` (5072 lines; targeted sections read in full)
- `<HOME>/Claude/loop/hooks/test_loop_stop_guard.py` (targeted sections, ~6300+ lines total)
- `<HOME>/Claude/loop/hooks/test_verifier_hygiene_gate.py` (targeted sections)
- `<HOME>/.claude/settings.json`, `<HOME>/.claude/settings.local.json`
- `<HOME>/Claude/loop/loop-team/evals/run_evals.py` (top of file, cases dir listing)

---

## 1. Misfire-1 root cause — "A Coder sub-agent was dispatched this turn without a preceding plan-check Verifier"

**The gate that fired:** the `PLAN_CHECK` gate, `loop_stop_guard.py` lines 687-817. The
exact message template (lines 811-817):

```
811	    _VIOLATIONS.append(("PLAN_CHECK",
812	        "[LOOP STOP-GUARD] A Coder sub-agent was dispatched this turn without a preceding "
813	        "plan-check Verifier. Per orchestrator.md step 1: produce the spec, dispatch the "
814	        "Verifier on the spec/ACs, get its approval, THEN dispatch the Coder. "
815	        "See loop-team/orchestrator.md step 1."
816	        + " Matched: %r" % (_coder_snippet,)
817	    ))
```

**The classifier's own regex, verbatim (line 703):**
```
703	_CODER_DETECT = re.compile(r'role:\s*coder\b|\bcoder for\b|roles/coder')
```

**How it's applied (lines 722-748):**
```
721	_first_coder_match_tu = None
722	for _tu in _TOOL_USES:
723	    if _tu.get("name", "").lower() not in ("task", "agent", "subagent", "workflow"):
724	        continue
725	    _inp = _tu_dispatch_text(_tu)
...
730	    if _VERIFIER_DETECT.search(_inp):
731	        _seen_verifier_anywhere = True
...
745	    elif _CODER_DETECT.search(_inp) or _CODER_DETECT.search(_tu_dispatch_prompt_text(_tu).lower()):
746	        _seen_coder_anywhere = True
747	        if _first_coder_match_tu is None:
748	            _first_coder_match_tu = _tu
```

`_inp = _tu_dispatch_text(_tu)` is the narrow field — per its own docstring (lines
294-321) it returns `description` if non-empty, else falls back to `prompt`, and for a
`Workflow` tool_use returns the `script` field. It never reads `subagent_type`. The
`elif` branch **also** searches `_tu_dispatch_prompt_text(_tu).lower()` — the FULL raw
`prompt` field, lowercased, independent of whatever `description` said (lines 324-334
define this helper; it just returns `inp.get("prompt", "")`, or `script` for Workflow).

**Grounded diagnosis: this is 100% free-text regex matching, never `subagent_type`.**
Direct proof, not inference:

```
$ grep -rn "subagent_type" <HOME>/Claude/loop/hooks/loop_stop_guard.py <HOME>/Claude/loop/hooks/verifier_hygiene_scan.py
(no output — the string "subagent_type" does not appear anywhere in either file)
```

The gate has no code path that reads the Agent tool call's actual `subagent_type`
parameter at all. Classification is entirely: does the dispatch's `description` (or
`prompt` fallback) match `_VERIFIER_DETECT`? If not, does EITHER the same narrow text
OR the full raw `prompt` match `_CODER_DETECT`'s three alternatives (`role:\s*coder\b`,
`\bcoder for\b`, `roles/coder`)? A `subagent_type: "researcher"` dispatch is invisible
to this logic — the ONLY thing that matters is whether the dispatch's own `description`/
`prompt` text happens to contain one of those three substrings, anywhere.

**This is a deliberate, known, and separately-tested design decision** — not an
accidental gap. `hooks/test_loop_stop_guard.py` lines 1474-1628 (the
"custom-subagent-types spec" block, `CustomSubagentTypeDispatchRegression` class) exists
specifically to pin this behavior. Its own header comment (lines 1479-1488, quoted
verbatim):

```
1479	# changes the SHAPE of a real Agent dispatch: `subagent_type` is now set to
1480	# the matching custom type name (e.g. "coder", "plan-check-verifier"), and
1481	# `prompt` carries only a short delegation message (no pasted role-brief
1482	# text), while `description` conventions are REQUIRED to stay exactly as
1483	# they are today (spec.md's "Preserve, verbatim, the existing description
1484	# field conventions..." instruction) precisely because _CODER_DETECT /
1485	# _VERIFIER_DETECT match against the full serialized `input` dict
1486	# (_tu_input(), i.e. description + prompt + subagent_type + model +
1487	# everything -- see loop_stop_guard.py's own _tu_input() docstring-equivalent
1488	# comment), NOT against subagent_type alone.
```

(Note: this comment's mention of `_tu_input()`/full-serialized-dict is imprecise for
the PLAN_CHECK gate specifically — the PLAN_CHECK loop actually uses the narrower
`_tu_dispatch_text()`/`_tu_dispatch_prompt_text()` helpers, which read only
`description`/`prompt`/`script`, not the whole input dict. `_tu_input()` — full
`json.dumps(tu.get("input","")).lower()` — is a *different* helper used elsewhere in
the file, e.g. the `SUITE_GREEN`/`_rh_judge_suite_green` checks at lines 359-389. This
does not change the conclusion: whichever exact helper, none of them special-case
`subagent_type` as a structural field: it either isn't read at all (`_tu_dispatch_text`/
`_tu_dispatch_prompt_text`) or is swept in only as more free text to pattern-match
(`_tu_input`) — never checked by field name/value.)

The suite's own negative-control test proves this explicitly (lines 1603-1613):
```
1603	    def test_subagent_type_alone_does_not_satisfy_verifier_detect(self):
1604	        code, err = run_guard(make_turn(
1605	            [NEW_SHAPE_SUBAGENT_TYPE_ALONE_NOT_ENOUGH, NEW_SHAPE_CODER_AGENT]))
1606	        self.assertEqual(
1607	            code, 2,
1608	            "subagent_type='plan-check-verifier' alone (description NOT starting "
1609	            'with "plan-check Verifier") must NOT satisfy _VERIFIER_DETECT -- if '
1610	            "this passes (exit 0), the description-prefix rule has been silently "
1611	            "superseded by subagent_type, which is the exact regression risk "
1612	            "spec.md flags. Got exit %r, stderr=%s" % (code, err),
1613	        )
```

So the framework has *already* deliberately chosen text/convention-based classification
(the `description` field's "`<Role> for <task>`" prefix convention) over the structural
`subagent_type` field, and has a regression test locking that choice in.

**Where the actual gap is — confirmed by absence of coverage, not inference:**
`_CODER_DETECT` is checked against BOTH `description` (narrow) AND the full `prompt`
text (broadened, per the H-GUARD-1-adjacent comment at lines 732-746, added because a
generic `description` could otherwise mask a real "role: coder for ..." buried in
`prompt`). That broadening is exactly the surface a non-Coder, non-Verifier dispatch
(e.g. a Researcher) can trip: if the Researcher's `prompt` — which can be long and
quote framework file paths or role-brief prose — happens to contain the literal
substring `"coder for"`, `"role: coder"`, or `"roles/coder"` ANYWHERE, `_seen_coder_
anywhere` is set True regardless of the dispatch's real purpose. I searched the existing
test suite for a regression test covering this exact shape (a Researcher/other-role
dispatch whose *prompt* incidentally contains a coder-shaped substring) and found none:

```
$ grep -n "RESEARCHER\|Researcher\b" hooks/test_loop_stop_guard.py | grep -i "class \|def test"
(no output)
```

All existing `PlanBeforeCoderGate` / `H_GUARD_1_Regression` / `WorkflowSite4Site5
NonMisfireAdversarial` tests cover: (a) prose-only mentions with no real tool_use
(`test_prose_coder_mention_does_not_trigger_gate`, line 242 — but this uses a plain
`text()` turn, not an Agent/Task dispatch at all), (b) a Verifier-described dispatch
whose prompt discusses Coder dispatch *formats* (`H_GUARD_1_Regression`, fixed by
checking `_VERIFIER_DETECT` first), and (c) a Coder-described dispatch whose prompt
contains verifier language (the reverse direction). None test a dispatch that is
*neither* Coder- nor Verifier-described (i.e. `_VERIFIER_DETECT` doesn't match and the
dispatch is legitimately some other role) whose prompt still trips `_CODER_DETECT`
incidentally. I could not access this session's own transcript to quote the literal
matched substring (out of the Researcher role's data-access scope — session
transcripts outside the current repo require explicit authorization not granted in
this dispatch), so I cannot name the exact string that fired; the mechanism above is
proven directly from the source and the negative-space test-coverage check, independent
of that transcript.

**Verdict on the stated hypothesis:** CONFIRMED. The classifier is unambiguously
keyword/regex-based over free text (`description` with `prompt` fallback, plus a
separate full-`prompt` scan), never inspects the real `subagent_type` parameter, and
this is a documented, deliberately-chosen, tested tradeoff — but the specific false-
positive shape (a non-Coder-described, non-Verifier-described dispatch's *prompt* text
incidentally containing a `_CODER_DETECT` substring) has no existing regression test.

---

## 2. Misfire-2 root cause — "Verifier-dispatch adjacency violation" on `plan_check_log.md` itself

**The gate that fired:** the `VERIFIER_ADJACENCY` gate, `loop_stop_guard.py` lines
975-1034. Its own header (lines 980-986, quoted) states the intended scope precisely:

```
980	# The hygiene gate above blocks result-shaped PROSE in the prompt. It cannot
981	# stop a clean prompt that merely POINTS at a path which happens to sit beside
982	# a status doc (HANDOFF.md, plan_check_log.md, a decision-log file, a run-log
983	# file, a summary) — the Verifier finds those by exploring the directory, not
984	# by reading the prompt. This gate makes that adjacency DETERMINISTICALLY
985	# blocked: for every existing path referenced in a Verifier dispatch prompt,
986	# inspect its real parent directory for a status-doc-shaped filename.
```

That intent statement already frames the gate as being about a path *beside* a status
doc — but the implementation does not encode that distinction; it treats "beside" and
"is" identically. The actual scan (`loop_stop_guard.py` lines 1013-1022) delegates to
`verifier_hygiene_scan.evaluate_adjacency()`:

```
1013	for _tu in _TOOL_USES:
1014	    if _adj_violation:
1015	        break
1016	    if _tu.get("name", "").lower() not in ("task", "agent", "subagent", "workflow"):
1017	        continue
1018	    _adj_desc = _tu_dispatch_text(_tu)
1019	    if not _VERIFIER_DETECT.search(_adj_desc):
1020	        continue
1021	    _adj_prompt = _tu_dispatch_prompt_text(_tu)
1022	    _adj_violation = _shared_evaluate_adjacency(_adj_prompt, _adj_cwd, _adj_target_dir)
```

The message template fired (lines 1027-1034), matching the incident description
essentially verbatim:
```
1027	    _VIOLATIONS.append(("VERIFIER_ADJACENCY",
1028	        ("[LOOP STOP-GUARD] Verifier-dispatch adjacency violation: the dispatch references "
1029	         "%r, whose directory also contains the status doc %r. A hygiene-clean prompt is not "
1030	         "enough — the Verifier can find prior verdicts/decision-" + "logs by exploring the "
1031	         "directory. Remedy: copy the spec to an isolated specs/ dir (or a scratch path) "
1032	         "so Verifier inputs never sit beside run-status docs, then re-dispatch.")
1033	        % (_adj_path, _adj_doc)
1034	    ))
```

**The actual matching logic — `verifier_hygiene_scan.py` lines 125-151, quoted in full:**

```
125	def adj_status_doc_in_dir(dirpath):
126	    try:
127	        entries = os.listdir(dirpath)
128	    except OSError:
129	        return None
130	    for name in entries:
131	        low = name.lower()
132	        for pat in STATUS_DOC_DENYLIST:
133	            if fnmatch.fnmatch(low, pat):
134	                return name
135	    return None
136	
137	
138	def evaluate_adjacency(prompt_text, cwd, target_dir):
139	    """Returns (offending_path, status_doc_name) or None."""
140	    for tok in adj_extract_tokens(prompt_text):
141	        for cand in adj_candidate_paths(tok, cwd, target_dir):
142	            if not os.path.exists(cand):
143	                continue
144	            real = os.path.realpath(cand)
145	            parent = real if os.path.isdir(real) else os.path.dirname(real)
146	            if not parent or not os.path.isdir(parent):
147	                continue
148	            hit = adj_status_doc_in_dir(parent)
149	            if hit:
150	                return (cand, hit)
151	    return None
```

with the denylist (lines 15-19):
```
15	STATUS_DOC_DENYLIST = [
16	    "handoff*", "plan_check_log*", "*decision_log*",
17	    "run_log*", "*run_log*",
18	    "summary*", "run_summary*",
19	]
```

**Grounded diagnosis — walking the exact code path for the reported incident.** The
referenced path was `.../runs/2026-07-04_airbnb-calendar/plan_check_log.md` — the
literal, sole read target named in the instruction, per the dispatch prompt. Trace it
through `evaluate_adjacency()`:
1. `cand` resolves to the full path ending in `plan_check_log.md`.
2. `real = os.path.realpath(cand)` — still the same file (a file, not a dir).
3. `parent = ... os.path.dirname(real)` — since `real` is a file, `parent` becomes the
   **containing directory** (`.../runs/2026-07-04_airbnb-calendar/`), i.e. the very
   directory that itself contains `plan_check_log.md`.
4. `adj_status_doc_in_dir(parent)` lists every entry of that directory and returns the
   first one whose lowercased name `fnmatch`es any denylist pattern. `plan_check_log.md`
   itself matches the pattern `"plan_check_log*"` (line 16) — so the function returns
   `hit = "plan_check_log.md"`, which is the **exact same file the dispatch was
   instructed to read**, not a different, incidental neighbor.
5. `evaluate_adjacency` returns `(cand, hit)` where `cand` and `hit` name the *same*
   file — and the gate fires with `_adj_path` == the literal target and `_adj_doc` also
   naming that same target, worded as if it were a *sibling* ("whose directory also
   contains the status doc").

**There is no code anywhere in `adj_status_doc_in_dir()` or `evaluate_adjacency()` that
excludes the referenced file `cand`/`real` itself from the directory-listing scan of its
own parent.** The function computes "parent directory of the target" and then asks "does
this directory contain ANY denylist-shaped filename" without ever checking whether that
denylist-shaped filename IS the target being read. Mechanically, "the file IS the status
doc being fact-checked" and "the file sits next to an unrelated status doc" produce
byte-identical code paths and an identical violation tuple shape.

**Confirmed via the existing test suite's own coverage gap, not just static reading.**
`hooks/test_verifier_hygiene_gate.py`'s `TestAdjacencyGateH_LT4` class (lines 178-306,
ACs 1-4e) and `hooks/test_loop_stop_guard.py`'s `WorkflowSite5AdjacencyGateLiveIncident`
class (lines 5809-5872, including `test_workflow_script_referencing_path_beside_
plan_check_log_blocks` at line 5816 — a Workflow-shaped dispatch, the same tool shape
as the actual misfire) test EXCLUSIVELY the "target references a SEPARATE spec.md file
that sits BESIDE an unrelated status doc (HANDOFF.md / plan_check_log.md / run_summary.md
/ summary.md)" shape — every single fixture creates a distinct `spec.md` (or `README.md`)
as the referenced token and a SEPARATE status-doc file in the same directory. Quoting the
representative pattern (lines 196-207 of `test_verifier_hygiene_gate.py`):
```
196	    def test_ac1_dirty_absolute_spec_beside_handoff_blocks(self, tmp_path):
197	        rundir = tmp_path / "rundir"
198	        rundir.mkdir()
199	        (rundir / "spec.md").write_text("spec content")
200	        (rundir / "HANDOFF.md").write_text("handoff content")
201	        r = self._run_adj([{
202	            "description": "plan-check Verifier for widget spec",
203	            "prompt": "Spec at %s. Review and emit the gate line." % (rundir / "spec.md")}])
204	        assert r.returncode == 2, r.stderr
205	        assert str(rundir / "spec.md") in r.stderr
206	        assert "HANDOFF.md" in r.stderr
```
and the closest analogue to the real incident (`test_loop_stop_guard.py` lines 5816-5833):
```
5816	    def test_workflow_script_referencing_path_beside_plan_check_log_blocks(self):
...
5819	            spec_path = os.path.join(d, "spec.md")
...
5822	            with open(os.path.join(d, "plan_check_log.md"), "w", encoding="utf-8") as f:
5823	                f.write("prior plan-check verdict here\n")
...
5826	                "prompt: 'Read the spec at %s and review it.'})" % spec_path)
```
Note the referenced token is `spec.md`, and `plan_check_log.md` is the *separate,
incidental* file. **Zero existing tests construct the case where the referenced token
itself IS the status-doc-named file** (i.e., a dispatch instructed to read
`plan_check_log.md` directly, with no separate `spec.md` in the picture at all). This is
a genuine, previously-unexercised gap in test coverage — not a case where an existing
green test already encodes "target==denylist-match should also block" as intended
behavior that a fix would need to work around.

**Verdict on the stated hypothesis:** CONFIRMED. `adj_status_doc_in_dir()` performs an
undifferentiated directory-listing scan of the target's own parent directory and never
excludes the target file itself from that scan; the code has no notion of "this path IS
the instructed read target" versus "this path is an incidental neighbor of a different
target." The distinct, correctly-scoped "de-priming run-dir leak" concern (H-LT4, see
section 3) is about a Verifier's *independent judgment on a separate implementation-vs-
spec question* being contaminated by a neighboring decision log it stumbles on while
exploring — it was never meant to apply when the decision-log-shaped file **is** the
literal object of the read/fact-check instruction, and the code's current form does not
draw that line.

---

## 3. `fix_plan.md` precedent

### H-AC-ORACLE-TARGET-1 (full text, verbatim, lines 4955-5072 — the process template cited in this dispatch)

```
## H-AC-ORACLE-TARGET-1 (CLOSED 2026-07-08, filed 2026-07-08, priority: HIGH) -- a
hand-written adversarial/security AC can be structurally unfalsifiable and no amount
of manual scenario re-derivation catches it

**Found by Nnamdi, 2026-07-08**, mid-way through a 30+-round plan-check loop on
padsplit-cockpit Slice 6b (Airbnb iCal calendar sync) that was grinding on repeat
findings without full convergence. Nnamdi asked for deep research into why, and
separately identified that one of the research's four recommendations (an executable
mutation-check for adversarial security tests, rather than trusting repeated manual
scenario walk-throughs) should become a permanent, gated, procedural loop-team rule
-- not just a one-off fix for this slice -- and required the new gate itself be
validated before being trusted.

**The incident that motivated it:** AC19 (`saveCalendarLink` cross-org rejection,
introduced revision 20) asserted, as proof no cross-org row was written, that
`forOrg(orgB).calendarLink.findMany({where: {propertyId: orgBPropertyId}})` returned
EMPTY. This is checking the wrong org's table: `saveCalendarLink`'s `create` clause
writes `orgId` from the session (Org A, the attacker), never from the referenced
`propertyId`'s real owner -- so a wrongly-created row, if the ownership guard ever
failed, would carry `orgId: orgA`, and `forOrg(orgB)` could never see it regardless
of whether the guard worked, was silently narrowed, or was deleted outright. Ten
separate plan-check rounds (20 through 29) re-walked the identical cross-org
scenario and confirmed the REASONING was sound every time -- the scenario really
was correctly blocked by the real guard -- without anyone asking "which org's table
would a wrongly-created row actually land in?" Round 30's ordinary re-verification
dispatch (no special ownership-tracing instruction -- just "re-verify the now-
revision-31 spec.md against all 5 lenses simultaneously") is what finally caught
it; round 31's dispatch, written AFTER the fix landed, was the one explicitly
instructed to re-walk every adversarial AC with maximum skepticism as a reaction to
this exact incident, not its cause.

**Fix applied 2026-07-08:** four files, spanning design-time reasoning, correctly-
timed executable enforcement, and independent re-verification. (Revised once,
2026-07-08, after an independent Verifier caught that the first version put the
executable mutation-check in `roles/test_writer.md` -- which runs strictly BEFORE
any implementation exists, per that file's own header -- making the original
steps literally unexecutable there.)
- `DESIGN_CHECKLIST.md` gains a 9th gate ("Adversarial-AC oracle targeting"),
  requiring any plan-check lens (owned by state-transition-table + verifier) to
  identify, in writing, which actor's/org's state would actually change if a
  security guard were weakened, and confirm the AC's assertion targets THAT actor.
- `roles/test_writer.md` (Tier 1, pre-implementation) gains **LOOP-M3 — FLAG
  ADVERSARIAL ACs FOR TIER-2 ORACLE-TARGETING**: since no implementation exists yet
  to mutate, the Tier-1 Test-writer's job is narrower -- label every security/
  cross-tenant/adversarial AC's test `# [SECURITY-ORACLE]` as a handoff signal.
- `roles/adversarial_test_writer.md` (Tier 2, dispatched AFTER the Coder delivers
  and standard tests pass) gains **Phase 3.5 — Adversarial-AC oracle-targeting**:
  for every `[SECURITY-ORACLE]`-labeled test, make a scratch copy of the real
  implementation with the specific guard clause weakened/removed, re-run the AC's
  own test against it, and confirm it goes RED before trusting it green on the
  correct implementation -- not optional, stated explicitly per-AC in the attack
  summary.
- `roles/verifier.md` gains **LOOP-M6 — INDEPENDENT ADVERSARIAL-ORACLE MUTATION
  RE-RUN**: the Verifier independently repeats the exact same mutation check rather
  than trusting the Adversarial Test-writer's report (gate 3, propose ≠ verify) --
  a test that stays green on a deliberately-weakened guard is a FALSE-PASS on the
  original verification, full stop, regardless of how many times the scenario was
  walked.

**Gate validation (2026-07-08), before trusting the new rule -- PASSED.** Dispatched
a fresh `plan-check-verifier` agent with ONLY the new DESIGN_CHECKLIST.md gate-9
text plus AC19's ORIGINAL, pre-fix wording and the real `saveCalendarLink` code
context -- explicitly NOT told there was a known bug, NOT pointed at AC19/
padsplit-cockpit by name, and instructed not to search for either. Applying gate 9
cold, it independently: (1) traced that `orgId` on any written row is
session-derived (the attacker's own org), never the referenced `propertyId`'s real
owner; (2) concluded the original test's `forOrg(orgB)`-emptiness assertion checks
a location a wrongly-created row could never occupy, "regardless of whether the
ownership check works, is silently narrowed, or is deleted outright" -- its own
words, independently arrived at; (3) named the exact correct fix,
`forOrg(orgA).calendarLink.findMany(...)` returns empty, for the exact right
reason; (4) returned verdict FAIL (gate correctly flags the defect), no hedging.
One dispatch, cold, no prior context -- the gate reproduces in a single round what
took the live padsplit-cockpit process 10 rounds of manual scenario re-derivation
to surface. Gate trusted; no further validation needed before adoption.

**Independent verifier (2026-07-08): FAIL on first pass, PASS after fix.** A
`verifier`-role agent, dispatched per the loop's own stop-guard (any edit to
`roles/*.md` requires independent re-verification, not writer self-testing),
independently re-ran the eval suite (confirmed `SUITE: GREEN` itself, 15/15
traps, 0 regressions), confirmed the incident narrative against the real
`plan_check_log.md`/`spec.md` records, and found: (1) the blocking placement bug
described above (LOOP-M3's original executable steps were unexecutable in
`test_writer.md`'s pre-implementation timing -- fixed by moving them to
`adversarial_test_writer.md` Phase 3.5, per this entry's revised "Fix applied"
section); (2) this entry had wrongly attributed round 30's catch to a specially-
instructed dispatch when the real round-30 dispatch was generic (fixed above); (3)
this entry's original claim that the deep-research writeup was "not persisted to a
separate file" was false -- the file already existed at the path cited below,
dated the same day. All three fixed in this entry and the three role files.
Cross-file `LOOP-M3` numbering collision noted (test_writer.md's new LOOP-M3 vs.
verifier.md's pre-existing, unrelated LOOP-M3 "NO-SILENT-FALLBACK") -- judged
non-blocking since every cross-reference in these files is file-qualified
("`roles/test_writer.md` LOOP-M3", never a bare "LOOP-M3"), consistent with the
pre-existing cross-file LOOP-M5 collision already tolerated in this same scheme.

**Re-verification (2026-07-08): PASS**, two non-blocking cosmetic findings, both
fixed. A second, independent `verifier`-role agent re-checked the corrected
4-file design: confirmed the placement bug is genuinely resolved (traced
`adversarial_test_writer.md`'s Phase 1 wording and `orchestrator.md`'s Step 5.5
dispatch timing directly -- Phase 3.5 runs strictly post-implementation, matching
its executable steps), confirmed both fix_plan.md factual corrections against the
real `plan_check_log.md` record verbatim, confirmed the cited research file is
real and substantial (not a stub), and re-ran the eval suite itself
(`SUITE: GREEN`, 15/15 traps, 0 regressions). Two cosmetic findings, both fixed
immediately: `DESIGN_CHECKLIST.md`'s heading said "eight gates" after a 9th was
added (now "nine gates"); `adversarial_test_writer.md`'s structured "Attack
summary" output template didn't have a line item for the new
`[SECURITY-ORACLE]` mutation-check results (added two lines). Eval suite
re-confirmed GREEN after both fixes. Gate adoption complete.

**Cross-reference:** padsplit-cockpit's own `~/Claude/loop/runs/
2026-07-04_airbnb-calendar/plan_check_log.md` round-30 entry has the full original
finding and fix. Deep-research sources backing the general principle (test coverage
/ scenario re-derivation does not establish oracle correctness; mutation testing and
differential/metamorphic oracles are the literature's answer) are synthesized and
cited in full in `~/Claude/loop/research/
spec-first-vs-code-first-ai-agent-builds-2026-07-08.md`.
```

**The reusable template this entry establishes:** design → log in fix_plan.md → validate
the new gate BLIND (a fresh agent given only the new rule text, not told about the known
bug, must independently reproduce the diagnosis) → independent Verifier PASS (re-runs the
eval suite itself, fact-checks the narrative against real records) → a SECOND independent
re-verification pass before calling it closed. Any fix to the two misfires diagnosed in
this dossier should follow the same shape: spec → blind gate-validation → independent
Verifier → eval suite green → re-verification.

### Prior guard-fix precedent on this EXACT file (`loop_stop_guard.py`)

**H-LT4 — DE-PRIMING LEAKS VIA RUN-DIR ADJACENCY** (the gate whose intent Misfire-2
mis-executes). Original finding (line 1148, verbatim):
```
- [x] H-LT4 [DONE 2026-07-01 — CLOSED per the "[DONE 2026-07-01 — loop-verified] H-LT4 CLOSED" entry below (adjacency gate live in loop_stop_guard.py, independent Verifier PASS); residuals tracked there] DE-PRIMING LEAKS VIA RUN-DIR ADJACENCY — the post-build Verifier was dispatched clean
  (hygiene hook enforced the PROMPT), but the spec path points into the run dir, which ALSO holds
  HANDOFF.md carrying the Coder decision log + prior green results; the Verifier read it during
  exploration. Withholding-by-prompt is defeated by co-located status docs. FIX options: (a) keep
  specs in a specs/ subdir and status/decision docs in a private/ subdir the Verifier is told is
  out of bounds; (b) hygiene-gate the Verifier's Read paths (deterministic, preferred); (c) copy
  the spec to a scratch path for the dispatch. Apply to orchestrator.md dispatch rules + hooks.
  Blast-radius note this run: verdict evidence was independently tool-grounded (live e2e, curl
  parity, clean install, real generator), so PASS accepted WITH contamination disclosed.
```
Note the original incident (and every AC written for it, per section 2 above) was always
about a SEPARATE spec path sitting beside a decision log — never about the decision log
itself being the instructed read target. The fix landed at line 1171 ("H-LT4
deterministic fix landed" — the adjacency gate, denylist, 3-form path extraction) and
closed at line 1294 ("H-LT4 CLOSED: adjacency gate live in loop_stop_guard.py ... Residual
open: one-hop in-spec references (v1 scope)").

**H-GUARD-3 / H-GUARD-3b — `/tmp/` and `~/.claude/settings.json` false positives** (lines
634-680): the FEATURE gate false-fired on temp-file and settings-file writes; fixed via
structural realpath-based exemptions (`_rh_exempt_paths_only`), not a blob-regex patch —
i.e. the precedent for THIS class of fix in this file favors structural, realpath-based
disambiguation over broadening/narrowing a regex.

**H-GUARD-4 / H-GUARD-SUBAGENT-2 — PreToolUse oga-guard blocking Coder sub-agent edits**
(lines 1243-1255): resolved by H-LT6's GAC6 in-flight detection; the resolution note (line
1255) explicitly documents the "advisory, not security boundary" honesty framing adopted
when a structural fix wasn't fully available — a precedent for how this framework handles
a guard whose false-positive can't be perfectly eliminated.

**H-LT6 — OGA GUARD FALSE-POSITIVES ON SUB-AGENTS THAT READ orchestrator.md** (lines
1190-1229, 1300-1316): originally diagnosed as sub-agent self-arming, then CORRECTED
("diagnosed beyond doubt, supersedes the mechanism above") after running the guard's
exact detection against the real failing transcript and finding neither marker present —
the real cause was a turn-slicing race on the MAIN transcript. Closed via GAC6 in-flight
detection, then a PROPER fix (line 1305) once Claude Code's real hook payload was found to
carry a structural `agent_id` field for sub-agent PreToolUse calls — i.e., the eventual
fix for a similarly-shaped "can't tell who really dispatched this" problem in this same
hooks/ directory *was* to find and use a real structural signal, once one was confirmed
to exist in the runtime payload. (Memory: `pretooluse-agent-id-distinguishes-subagents`.)

**H-GUARD-6 (still partially OPEN, sub-case d) — FEATURE gate false-positives on doc-only
turns whose prose names a `.py`/`.md` path** (lines 1366-1374): the closest prior-art match
for "a gate keys off a filename/path pattern appearing in text, without checking whether
that reference is the actual target vs. incidental." The PRIOR-ART RESEARCH note (line
1366) found and cited a real external precedent: "TDD Guard (nizos/tdd-guard) does
candidate (a) via a file_path glob allowlist (never content)" — i.e. the same lesson this
dossier's Misfire-1/Misfire-2 both point at (prefer structural, tool_use-input-derived
signals over blob/prose-text matching) has independent, cited prior art from outside this
codebase. Sub-case (d) is explicitly still `[ ] STILL OPEN` as of the last close-out.

**H-VERIFIER-REGEX-DUPLICATE-1** (line 3638, referenced repeatedly at 2554/3412/3699):
filed because `_VERIFIER_DETECT` and related hygiene/adjacency logic used to be
hand-duplicated between `loop_stop_guard.py` and `pre_tool_use_oga_guard.py` — this is WHY
the current file imports the shared implementation from `verifier_hygiene_scan.py` (see
`loop_stop_guard.py` lines 17-42's own comment). Directly relevant: any fix to the
Misfire-2 mechanism must be made in `verifier_hygiene_scan.py` (the single canonical
implementation both hooks import), not hand-patched separately in `loop_stop_guard.py`,
or it re-creates the exact duplicate-drift class this entry was filed to prevent.

**H-PRETOOLUSE-VERIFIER-HYGIENE-1** (line 2504) and **H-WORKFLOW-BLINDSPOT-1** (line
3290): the builds that produced the current shared-module architecture
(`verifier_hygiene_scan.py`) and Workflow-tool-use coverage (`_tu_dispatch_text`/
`_tu_dispatch_prompt_text`'s Workflow branch) — i.e., the precedent for how a change to
this exact gate family was planned, spec'd, and independently verified before landing.

---

## 4. Hook registration / trust-mechanism finding

**Quoted directly from `<HOME>/.claude/settings.json`** (the file that
registers `loop_stop_guard.py` as the Stop hook):

```json
{
  "permissions": {
    "allow": [
      "Bash(ln -sf ../../scripts/auto-publish-on-commit.sh .git/hooks/post-commit)"
    ]
  },
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "python3 '<HOME>/Claude/loop/hooks/loop_guard.py'" } ] }
    ],
    "Stop": [
      { "hooks": [ { "type": "command", "command": "python3 '<HOME>/Claude/loop/hooks/loop_stop_guard.py'" } ] }
    ],
    "SessionStart": [
      { "matcher": "startup", "hooks": [ { "type": "command", "command": "bash '<HOME>/Claude/loop/hooks/session_start.sh'", "statusMessage": "Loading loop-team constraints..." } ] }
    ],
    "SubagentStop": [
      { "hooks": [ { "type": "command", "command": "python3 '<HOME>/Claude/loop/hooks/subagent_stop_gate.py'" } ] }
    ],
    "PreToolUse": [
      { "hooks": [ { "type": "command", "command": "python3 '<HOME>/Claude/loop/hooks/pre_tool_use_oga_guard.py'" } ] }
    ]
  },
  "skipWorkflowUsageWarning": true,
  "tui": "fullscreen"
}
```

This is a **plain literal command-string reference** — `python3 '<absolute path>'` — with
no hash, signature, checksum, or any other content-verification field anywhere in the
JSON structure (checked the whole file; there is no `hooks.state`-equivalent key, no
`trusted_hash`, no fingerprint block of any kind). `~/.claude/settings.local.json` (also
read in full) likewise contains no hook-trust structures — only a `permissions.allow`
list and one unrelated `UserPromptSubmit` hook for a different script. I also checked
`~/.claude.json` (the account/session-level config) for any top-level key that might hold
a hook-trust store; its full key list is: `numStartups, installMethod, autoUpdates,
hasSeenTasksHint, tipsHistory, promptQueueUseCount, cachedGrowthBookFeatures, ...,
mcpServers, ..., machineID, ...` (89 keys total) — nothing resembling `hooks.state` or a
per-hook trust hash.

**Corroborating evidence from official Claude Code docs** (via WebFetch of
`code.claude.com/docs/en/hooks` and `/docs/en/settings` — flagged as a secondary,
AI-summarized source, not a direct quote I independently re-verified byte-for-byte
against the raw doc HTML): "Claude Code watches your settings files and reloads them
when they change, so edits to most keys apply to the running session without a restart.
This includes `permissions`, `hooks`, and credential helpers." A separate search result
(from a third-party guide, also secondary) states: "Project hooks in `.claude/
settings.json` require approval on first use, because anyone in the repo could have
modified them" — but this describes a one-time **project-scoped** (repo-local
`.claude/settings.json`, shared/multi-author) trust prompt for the hooks BLOCK ITSELF
when first registered, not a hash keyed to the CONTENT of the script file the hook's
`command` string points at. It also does not apply to this specific registration, which
lives in the **user-level** `~/.claude/settings.json` that Nnamdi owns directly, not a
project-local file another contributor could have tampered with.

**Conclusion (moderate-high confidence, not from official written confirmation of
absence):** there is no evidence of an analogous trust-hash layer to Codex's
`~/.codex/config.toml` `[hooks.state]` mechanism (documented in fix_plan.md's
`H-CODEX-PARITY-2026-07-08` entry, lines 4861-4954 — SHA-256 `trusted_hash` per hook,
computed over canonicalized JSON content, silently excludes a hook on ANY content change
until a human re-approves via `/hooks`). Claude Code's Stop-hook registration here is a
plain path reference re-executed with whatever the target `.py` file's CURRENT on-disk
content is at each Stop event — editing `loop_stop_guard.py`'s content directly (without
touching `settings.json`'s `hooks` block) should NOT silently disable the hook. This is an
absence-of-evidence finding, not a positive confirmation from Anthropic's own docs stating
"there is no such mechanism" in so many words — the cheap, conclusive way to fully close
this question before relying on it is a live sanity probe: make a trivial content edit to
`loop_stop_guard.py` (e.g. a comment-only change) and confirm in the very next Stop event
that the hook still fires (e.g. still exits 2 on a deliberately-triggering turn). That
probe was NOT run as part of this research dispatch (Mode B research only; no code edits
authorized) but is the recommended pre-flight check before or immediately after any fix
lands.

---

## 5. Existing eval coverage for these two classifiers

**`loop-team/evals/run_evals.py` — direct answer: NO, it contains zero cases exercising
either classifier.** Read the file's header and case-loading logic (lines 1-48):
```
1	#!/usr/bin/env python3
2	"""Loop Team -- Eval/Regression Suite runner (the verifier-for-the-verifier).
3	
4	Replays each frozen case in evals/cases/*.json through the relevant role or
5	harness and compares the verdict to the case's `expected`. Prints a scorecard
6	that measures the gate as a REJECTOR...
```
`run_evals.py`'s cases live in `loop-team/evals/cases/*.json` (100 files total) and grade
the **Verifier ROLE's own artifact-judgment quality** — e.g.
`verifier-audit-whole-surface.json`, `verifier-citation-fabrication-identifier.json`,
`verifier-hourly-annualize-floor.json`, `verifier-recall-precision-only-pass.json`. None
of the 100 case filenames reference "guard," "adjacency," "de-prim(ing)," "hygiene," or
"stop_guard." This is a categorically different thing from `loop_stop_guard.py`'s own
internal gate logic — `run_evals.py` never invokes `loop_stop_guard.py` at all (it drives
`harness/verify.py` and, for judge-graded cases, an LLM-judge adapter over role prose).
**A future test-writer targeting either misfire should NOT add cases to
`evals/cases/*.json`** — that suite is scoped to Verifier-role judgment, not hook-gate
mechanics.

**The real regression coverage for these two classifiers lives in a separate pytest
suite:** `hooks/test_loop_stop_guard.py` and `hooks/test_verifier_hygiene_gate.py`
(driven directly, not through `run_evals.py`). Relevant existing classes/tests, so a
future test-writer doesn't duplicate them:

- **PLAN_CHECK / Coder-vs-Verifier classification** — `hooks/test_loop_stop_guard.py`:
  - `PlanBeforeCoderGate` (line 211): `test_coder_without_verifier_blocks`,
    `test_verifier_before_coder_passes`, `test_coder_before_verifier_blocks`,
    `test_verifier_alone_passes`, `test_prose_coder_mention_does_not_trigger_gate` (line
    242 — plain-text turn, NOT a real Agent/Task dispatch),
    `test_stop_hook_active_bypasses_gate`, `test_coder_with_verify_in_prompt_still_blocks`,
    `test_researcher_verify_does_not_satisfy_plan_verifier` (line 262 — tests that a
    RESEARCHER dispatch mentioning "verify" does NOT satisfy the VERIFIER side; this is
    the mirror-image case, not the Misfire-1 shape, which needs a Researcher dispatch
    incidentally tripping the CODER side).
  - `H_GUARD_1_Regression` (line 269): `test_plan_check_verifier_by_description_passes`,
    `test_verifier_plan_check_description_variant_passes`,
    `test_plan_check_verifier_then_coder_passes`,
    `test_coder_before_plan_check_verifier_still_blocks`,
    `test_coder_with_verify_prompt_not_misclassified_as_verifier`.
  - `CustomSubagentTypeDispatchRegression` (line 1548):
    `test_new_shape_coder_alone_still_detected_and_blocks`,
    `test_new_shape_plan_check_verifier_then_coder_passes`,
    `test_new_shape_plan_check_verifier_alone_passes`,
    `test_subagent_type_alone_does_not_satisfy_verifier_detect` (line 1603 — the negative
    control discussed in section 1),
    `test_subagent_type_alone_dispatch_in_isolation_is_inert` (line 1626).
  - `WorkflowSite4Site5NonMisfireAdversarial` (line 5905):
    `test_agent_coder_dispatch_with_verifier_language_in_prompt_not_misclassified` (line
    5930), `test_workflow_coder_script_with_no_verifier_language_not_swept_into_hygiene_
    scan`, `test_workflow_script_mixing_coder_dispatch_with_narrative_verifier_mention_
    sweeps_into_hygiene`/`_adjacency` — all cover Coder-described dispatches whose PROMPT
    contains verifier language (the reverse direction from Misfire 1).
  - **Confirmed gap:** no test class/method name matches `Researcher`/`RESEARCHER`
    anywhere in this file's PLAN_CHECK-relevant sections (grep returned zero hits) — i.e.
    no existing test constructs "a non-Coder-described, non-Verifier-described dispatch
    whose prompt incidentally contains a `_CODER_DETECT` substring."

- **VERIFIER_ADJACENCY classification** — `hooks/test_verifier_hygiene_gate.py`:
  - `TestAdjacencyGateH_LT4` (line 178): `test_ac1_dirty_absolute_spec_beside_handoff_
    blocks`, `test_ac2_spec_moved_to_specs_subdir_allows`,
    `test_ac3_coder_dispatch_referencing_dirty_dir_allows`,
    `test_ac4_nonexistent_path_token_does_not_flag`,
    `test_ac4b_bare_relative_path_beside_handoff_blocks`,
    `test_ac4c_eval_baseline_readme_no_false_positive`,
    `test_ac4d_symlink_evasion_via_real_parent_blocks`,
    `test_ac4e_run_summary_doc_adjacency_blocks`, `test_ac4e_summary_doc_adjacency_blocks`.
  - `hooks/test_loop_stop_guard.py`, `WorkflowSite5AdjacencyGateLiveIncident` (line 5809):
    `test_workflow_script_referencing_path_beside_plan_check_log_blocks` (line 5816 — the
    closest existing fixture to the real Misfire-2 shape, but still references a SEPARATE
    `spec.md` beside `plan_check_log.md`, not `plan_check_log.md` as the sole/literal
    target), `test_workflow_script_referencing_clean_path_allows`,
    `test_equivalent_agent_dispatch_already_blocks`.
  - **Confirmed gap:** every single fixture across both files creates the referenced
    token as a DISTINCT file (`spec.md`/`README.md`) from the status-doc file that
    triggers the denylist match. None construct the case where the referenced token IS
    itself the denylist-matching filename (e.g., a dispatch prompt whose sole/literal
    path argument is `plan_check_log.md`). This is the exact shape of the real Misfire-2
    incident and has zero existing coverage in either direction (no test currently
    asserts it SHOULD block, and no test currently asserts it SHOULD pass) — a fully
    open gap, not a case where a fix risks regressing an existing green assertion.

---

## Summary for the Coder

1. **Misfire 1** (`PLAN_CHECK` gate, `loop_stop_guard.py` lines 687-817, `_CODER_DETECT`
   at line 703): confirmed keyword/regex match over `description`+`prompt` free text,
   never `subagent_type`. This is a KNOWN, deliberate, tested design choice (see the
   `CustomSubagentTypeDispatchRegression` negative-control test) — but the specific
   false-positive shape (non-Coder-described dispatch's prompt incidentally containing
   `"coder for"`/`"role: coder"`/`"roles/coder"`) has zero regression coverage.
2. **Misfire 2** (`VERIFIER_ADJACENCY` gate, `verifier_hygiene_scan.py` lines 125-151,
   `adj_status_doc_in_dir`/`evaluate_adjacency`): confirmed the code never excludes the
   referenced target file from the directory-scan of its own parent, so "target IS the
   status doc" and "target sits beside an unrelated status doc" are structurally
   indistinguishable today. Any fix belongs in `verifier_hygiene_scan.py` (the single
   canonical shared implementation both `loop_stop_guard.py` and
   `pre_tool_use_oga_guard.py` import — see H-VERIFIER-REGEX-DUPLICATE-1), not
   hand-patched separately in either caller.
3. **Precedent**: H-AC-ORACLE-TARGET-1 is the template (spec → blind gate-validation →
   independent Verifier → eval-suite-green → re-verification). H-LT4/H-GUARD-3/
   H-GUARD-3b/H-GUARD-4/H-LT6/H-GUARD-6 are all prior fixes to false-positives in this
   exact `loop_stop_guard.py`/`pre_tool_use_oga_guard.py` family, and the pattern across
   nearly all of them is: prefer a structural, tool_use-input-derived signal over
   broadening/narrowing a text regex (H-GUARD-3's realpath-based exemptions; H-LT6's
   eventual `agent_id`-based proper fix; H-GUARD-6's cited external prior art, TDD
   Guard's file_path-glob-not-content approach).
4. **Hook registration**: plain path reference in `~/.claude/settings.json`, no
   hash/trust-pinning found in that file, `settings.local.json`, or `~/.claude.json`.
   Distinct from the Codex `hooks.json` trust-hash mechanism (H-CODEX-PARITY-2026-07-08).
   Recommend a cheap live sanity probe (trivial edit + confirm the hook still fires) as
   the belt-and-suspenders check before/after any fix, since this is an absence-of-
   evidence conclusion, not a documented guarantee from Anthropic.
5. **Eval coverage**: `run_evals.py`'s `cases/*.json` suite is out of scope (grades
   Verifier-role judgment, never invokes `loop_stop_guard.py`). The real test home is
   `hooks/test_loop_stop_guard.py` + `hooks/test_verifier_hygiene_gate.py`; both misfire
   shapes are confirmed, genuine, previously-unexercised gaps in that suite (not
   collisions with any existing green assertion).
