# Compiler/Typecheck Feedback Gate — Design Proposal (2026-07-08)

**Status: design for approval, revised after 4 independent adversarial reviews.** All verification below — greps, file reads, git archaeology, and live command execution — was performed directly in this session; no sub-agents were dispatched (H-WF-DELEGATE-1 respected). Where a fact was in dispute between the draft and a reviewer, I re-ran the actual check myself rather than trusting either account; those results are cited inline with the exact command.

**Corrected bibliographic facts** (minor, but the draft staked credibility on exact citations so these are fixed): `harness/verify.py` is 404 lines, not 405 (`_smoke_gate` ends line 370, `main()` starts line 373, wiring block lines 385–398 — all confirmed by direct read). `orchestrator.md` is 588 lines, not 589. `fix_plan.md`'s `above|below` count is 107, not 106 (re-run live: `grep -ciE "\b(as (mentioned|noted|described) )?(above|below)\b" fix_plan.md` → 107).

## Summary

The core mechanism — an additive `type_check` key in `harness/verify.py`, mirroring `_smoke_gate`'s exact additive-key/`(dict, error)` contract — survives review and is still the right shape. **Everything else about the draft's rollout plan does not survive review and has been redesigned:**

1. **The gate as originally specified would break the real target repo today, not hypothetically.** I reproduced this live: `cd ~/Claude/Projects/padsplit-cockpit/web && npx --no-install tsc --noEmit -p tsconfig.json` returns exit 2 with 3 real errors right now, against untracked, intentionally-RED Test-writer files (`git status --porcelain` confirms `?? web/tests/airbnb-calendar-*.test.ts`; the module one of them imports, `web/src/app/dashboard/calendar-sync/actions`, does not exist on disk). A gate that force-fails every checkpoint on a repo in its ordinary, correct, mid-TDD state is not shippable as designed. Fixed by redesigning the gate to be **baseline/erosion-scoped** (fail only on NEW errors vs. a per-slice baseline), not "any nonzero exit forced-fails."
2. **The literal proposed invocation has a real bug and a real hidden dependency.** `npx --no-install tsc` on an uninstalled toolchain returns exit 1 (not the assumed 127) and — reproduced in a synthetic scratch project — resolves the wrong npm package (`tsc@2.0.4`, an unrelated abandoned package, not TypeScript). Separately, I discovered (not caught by any of the 4 reviews) that the reason the command "worked" against padsplit-cockpit/web at all is that `web/node_modules` is essentially empty and npx's resolution is silently walking UP to the **monorepo root's** hoisted `node_modules/.bin/tsc` (`typescript@5.9.3`, via npm workspaces — `web`/`extension` are declared workspaces of the root `package.json`). Fixed by resolving the binary explicitly (project → parent workspace roots → pinned `npx --package typescript`) instead of relying on bare `npx tsc`.
3. **The gate's claimed motivating incident is a partial mischaracterization.** The ~9-of-31-round "identifier never bound" burn in the real 2026-07-04 airbnb-calendar plan-check run happened entirely in prose, before any Coder was dispatched and before any file existed on disk — a mechanical `tsc` gate would have produced zero signal at any point during those rounds, because there was nothing yet to compile. The draft's claim that "real files plainly already existed" by round 20 was a misreading of an unrelated later citation. This is corrected in Question 1 below, and the gate's scope is now stated honestly: it helps only *after* Coder starts landing real files, not during pre-code plan-check.

None of this kills the proposal. It narrows its claimed value (real, but smaller than advertised) and adds required design work (baseline scoping, binary resolution) before it is safe to validate, let alone ship.

## Question 1: Where does the check fire

**Corrected answer, in two parts: it fires nowhere useful during plan-check, and it cannot fire unconditionally at every micro-step either — both halves of the original claim were wrong, for different, independently-confirmed reasons.**

### 1a. Plan-check: zero effect, and the "real files existed" claim doesn't hold up

The draft argued the round-20-24 burn was moot because a mechanical gate makes plan-check binding-review unnecessary once real files exist. I re-read the primary incident record directly (`~/Claude/loop/runs/2026-07-04_airbnb-calendar/plan_check_log.md`, 2550 lines) rather than trusting either the draft or the reviewer summaries:

- **Round 27's regression-audit finding** (lines ~2156–2167) states explicitly: *"a full-document grep for `@/lib/` returned ZERO hits, meaning `getSession`, `db`, `forOrg`, and `logger` — all called as bare identifiers in `saveCalendarLink`/`syncNowAction`, in a brand-new file that doesn't exist yet — have never had their imports written down anywhere."* This is prose review of spec text describing a file that does not exist, five rounds into a six-time-recurring bug class (rounds 17, 22, 23, 24, 26 per the same log).
- `find ~/Claude/Projects/padsplit-cockpit -iname "*calendar-sync*"` returns exactly one file: the Test-writer's own test, whose header states plainly *"syncAirbnbCalendar, CalendarLink, and Reservation do not exist yet... These tests are RED until the Coder lands them. That is correct."* No implementation directory (`web/src/app/dashboard/calendar-sync/`) exists anywhere in the tree.
- The draft's "real files plainly already existed" claim cited `fix_plan.md` line 5016's phrase "the real `saveCalendarLink` code." I re-read that entry in full: it is the **H-AC-ORACLE-TARGET-1 gate-validation dispatch**, dated 2026-07-08 (today) — a *separate* validation exercise for a *different* gate (the adversarial-AC oracle-targeting checklist item), which was handed a scratch copy of code as validation context. "Real" there means faithfully-quoted-not-paraphrased, not "existing in the tree during rounds 17–31 of the calendar-sync plan-check." The draft picked the wrong resolution of its own internal contradiction (it correctly quotes the "receives only the spec + ACs, not any prototype code" rule two sentences earlier, then contradicts it).
- What actually ended the burn, confirmed by reading the log's own record of it (lines ~2523–2549): a **manual, human process-pivot decision** at round 31. Its own text is unusually on-the-nose for this proposal: *"the large majority of them (missing imports, missing `export`/`'use client'`/`'use server'` directives...) are exactly what `next build`/`tsc` catches in seconds, for free — we were hand-simulating a compiler by reading prose very carefully."* That's strong corroborating evidence the *category* of gate is right — but it's a decision Nnamdi made in the room, not a structural rule this proposal installs. **This proposal, as scoped, would not have shortened that specific 31-round burn by a single round**, since it only fires once real files exist, which happened after round 31, not during it.

**Revised, honest framing:** the `type_check` gate has no effect on pre-code plan-check. The pre-code binding-review cost this proposal was drafted to cite as its motivating incident is, candidly, **not solved by this proposal** — it remains exactly as manual and round-expensive as before, with the round-31 pivot ("stop prose review, get to Coder/tsc sooner when the finding class keeps repeating") as the only currently-known mitigation, and that mitigation is still a judgment call, not a rule. I considered proposing a structural trigger here (e.g., "≥3 rounds finding the same mechanical bug class → mandatory pivot to stub-and-compile") but that is a materially different, undesigned change to `orchestrator.md`'s plan-check section and does not belong bundled into this proposal — flagged as a named follow-on in Open Risks, not designed here.

### 1b. Post-code (micro-step loop): fires, but not unconditionally, and not as "any nonzero exit fails"

The draft was correct that the micro-step build loop (`orchestrator.md` lines 139–172) calls `verify.py`/`pytest --testmon` at every checkpoint starting from the first Coder dispatch, with no round-number or maturity gate. What the draft got wrong is treating that as sufficient — it never checked what state the target repo is actually in when that first checkpoint fires.

I ran the literal proposed check against the real repo:

```
$ cd ~/Claude/Projects/padsplit-cockpit/web && npx --no-install tsc --noEmit -p tsconfig.json
tests/airbnb-calendar-ui-actions.test.ts(63,28): error TS2307: Cannot find module '../src/app/dashboard/calendar-sync/actions'...
tests/ops-clock-adversarial.test.ts(53,11): error TS2352: Conversion of type ... may be a mistake...
tests/sync-padsplit-tasks.test.ts(85,11): error TS2352: Conversion of type ... may be a mistake...
(exit 0 from the shell wrapper, tsc itself printed 3 errors — 6.75s wall-clock via `time`)
```

This is not a stale, fixed-since-2026-07-02 state (`fix_plan.md` line 740's "PSC-TSC-1 RESOLVED... full `npx tsc --noEmit` exits 0" claim was true when written and is false today — the repo has moved on). It's the **ordinary, correct, currently-open state of a repo mid-TDD-cycle**: Test-writer wrote 6 calendar-sync test files ahead of any Coder work, exactly as the framework's own "Tests are the executable form of the verifier... write them before the code" principle instructs (`orchestrator.md` step 2). A gate that force-fails every downstream micro-step checkpoint because of files a *later*, not-yet-dispatched micro-step is responsible for is not a design bug in the target repo — it's a design bug in the gate.

**Redesigned answer:** the gate fires starting at the first Coder-dispatch checkpoint of a slice (same call site as originally proposed — item 2 of the micro-step loop, same place `pytest --testmon` already runs), but its pass/fail semantics are **baseline/erosion-scoped**, not "any nonzero tsc exit fails":

- A baseline snapshot of tsc errors is captured once, at the moment the micro-step loop begins for a slice (i.e., right after Test-writer's RED suite lands, before the first Coder dispatch touches the tree). This captures Test-writer's known, intentional, not-yet-resolved errors (missing modules the Coder hasn't written yet) as the accepted floor.
- Each subsequent checkpoint's tsc run is compared against that *same* baseline by a stable per-error fingerprint (file + TS error code + normalized message — explicitly **not** raw `file:line`, since line numbers shift as unrelated code in the same file changes across micro-steps, which would otherwise manufacture false "new" errors on every step).
- A checkpoint fails **only** on a fingerprint not present in the baseline — i.e., a genuinely new binding/type defect the current step's own change introduced. A fingerprint that was already in the baseline (some other not-yet-reached micro-step's still-unresolved reference) does not block.
- The baseline is expected to shrink to empty as the slice's micro-steps land; reaching baseline-empty is the slice's own close-out condition (checked once, not per-step), mirroring how the micro-step loop already treats "green → checkpoint" as a discrete event, not a running requirement.

This is genuinely new design work beyond anything either the draft or the 4 reviews fully specified (reviewer 1 named the requirement — "diff/baseline-scoping mode... fail only on a NEW error count increase" — as one acceptable fix among three options; I'm adopting that option and sketching the mechanism, not just naming it). **It is unvalidated** — flagged explicitly in Open Risks below, and it is the single largest piece of net-new design risk in this document.

## Question 2: New role vs harness addition — exact diffs

Confirmed by direct reading of `roles/verifier.md`, `roles/test_writer.md`, `roles/coder.md`, `DESIGN_CHECKLIST.md` (117/117 lines), and `harness/verify.py` (404/404 lines): this is a `harness/verify.py` addition, one scoping bullet in `orchestrator.md`, one anti-gaming line in `roles/coder.md`, and one heading-fix + footnote in `DESIGN_CHECKLIST.md`. No new role, no new numbered gate. This scoping conclusion was independently confirmed sound by reviewer 3 (full read of all 9 gates: each carries an explicit role-owner and none claims binding/import-correctness territory) — kept as-is.

### 2a. Real target-repo grounding (re-verified, corrected for current state)

`web/tsconfig.json` sets `"noEmit": true` and its `include` covers test files (`**/*.ts`, `**/*.tsx`), unlike the narrower `web/tsconfig.src.json` (`{"extends": "./tsconfig.json", "include": ["src/**/*"]}`). The real PSC-TSC-1 incident's 6 errors (`fix_plan.md` line 745: missing `@types/jsdom` ×3, non-callable mocks ×2, one mock-type conversion — confirmed against the real fix commit `acc2e2f`) were all in test files, so **the gate must target the root `tsconfig.json`, not `tsconfig.src.json`** — this part of the draft's reasoning is correct and unchanged.

**New finding, not caught by the draft or any of the 4 reviews:** `web/node_modules` is essentially empty (`.cache`/`.vite` only — no `typescript`, no `.bin/`). `padsplit-cockpit` is an **npm workspaces monorepo** (`root package.json`: `"workspaces": ["web", "extension"]`), and the real, installed `typescript@5.9.3` lives hoisted at the **monorepo root's** `node_modules/.bin/tsc`. The reason `npx --no-install tsc` "worked" against `web/` at all is that npx's resolution walked up five directories to that hoisted binary. This is an undocumented, silent dependency the original design never accounted for — if `verify.py`'s `project` argument were ever pointed at an isolated copy of `web/` (a CI checkout of the subdirectory alone, a differently-configured monorepo without hoisting, e.g. strict-mode pnpm), the exact same invocation would either resolve nothing or — reproduced live in a synthetic scratch project with `typescript` declared but not installed — fall through to `npm error npx canceled due to missing packages... ["tsc@2.0.4"]`, exit **1** (not 127), silently resolving to an unrelated abandoned npm package literally named `tsc`, not the TypeScript compiler.

`package.json` confirms `"typescript": "^5"` devDependency present, no `typecheck`/`tsc` npm script (only `dev`/`build`/`start`/`lint`/`seed`/`test`), and — checked directly, addressing reviewer 1's requested comparison — `next.config.ts` is a bare `NextConfig` object with no `typescript: { ignoreBuildErrors: true }`, meaning `npm run build` already performs full type-checking as a side effect. **Design call: keep standalone `tsc --noEmit`, do not switch to `next build`.** Reasoning: (1) the monorepo-hoisting fix below sidesteps the npx-collision concern that motivated considering `next build` in the first place, without inheriting `next build`'s bundler-artifact side effects or ~10x longer runtime; (2) the real round-31 pivot text names `next build` *and* `tsc --noEmit` as two complementary checks run together, not alternatives — nothing in the primary incident record argues for choosing one over the other; (3) a CHECK-only gate producing build artifacts as a side effect is itself a scope smell the draft's own `_type_check_gate` docstring already flagged and rejected for a different reason (never depend on a target's own `tsconfig` `noEmit` setting). Whether to *additionally* run `next build` is left as a named, undesigned open question, not a required substitution.

### 2b. Exact diff — `harness/verify.py` (materially revised from the draft)

Insert after `_smoke_gate` (line 370), before `def main()` (line 373):

```python
def _resolve_tsc_binary(project):
    """Find a real tsc binary without going through bare `npx tsc`, which
    collides with an unrelated, abandoned npm package literally named `tsc`
    (confirmed live, 2026-07-08: `npx --no-install tsc` in a project that
    declares `typescript` but hasn't installed it exits 1 -- NOT 127 -- with
    npm error ... canceled due to missing packages ... ["tsc@2.0.4"]).

    Resolution order, cheapest/most-specific first:
      1. <project>/node_modules/.bin/tsc -- direct project install.
      2. Walk parent directories (npm/yarn/pnpm workspace hoisting) for
         node_modules/.bin/tsc. CONFIRMED this is what padsplit-cockpit/web
         actually resolves to today: web/node_modules has no local install;
         the real typescript@5.9.3 binary is hoisted five directories up at
         the monorepo root. This was a silent, undocumented dependency of
         the original bare-npx design.
      3. `npx --no-install --package typescript tsc` -- pins the package
         name to avoid the tsc@2.0.4 collision; still exits non-zero with
         the same "canceled due to missing packages" text if typescript
         truly isn't installed/cached anywhere npx can see -- treated as a
         toolchain-unresolvable forced fail by the caller, not a type error.
      4. None resolve -> caller returns a distinct, honest forced-fail
         message; never folded into the same code path as a real tsc error.
    """
    candidate = os.path.join(project, "node_modules", ".bin", "tsc")
    if os.path.isfile(candidate):
        return [candidate]
    d = project
    for _ in range(6):  # bounded walk -- workspace roots are shallow
        parent = os.path.dirname(d)
        if not parent or parent == d:
            break
        d = parent
        candidate = os.path.join(d, "node_modules", ".bin", "tsc")
        if os.path.isfile(candidate):
            return [candidate]
    return ["npx", "--no-install", "--package", "typescript", "tsc"]


def has_typescript_project(project):
    """True only when BOTH a tsconfig.json exists AND package.json declares
    `typescript` as a dependency -- mirrors detect_node_runner's dependency-
    declaration gate, not just file presence. Targets the ROOT tsconfig.json
    specifically (PSC-TSC-1's real 6 errors were in TEST files only the root
    config's wider `include` catches; a src-only config would have missed
    it). Silent-skip on tsconfig-present-but-no-declared-dep is a known,
    UNRESOLVED edge case -- see Open Risks; VAC7's precedent argues for a
    loud forced-fail instead, not decided here.
    """
    tsconfig_path = os.path.join(project, "tsconfig.json")
    if not os.path.isfile(tsconfig_path):
        return False
    pkg = _load_package_json(project)
    if pkg is None:
        return False
    deps = {}
    deps.update(pkg.get("dependencies") or {})
    deps.update(pkg.get("devDependencies") or {})
    return "typescript" in deps


def _type_check_gate(project):
    """Additive, BASELINE-SCOPED type-check gate. (dict, error) contract,
    mirroring _smoke_gate exactly.

    Design correction (2026-07-08, post-adversarial-review): a naive "any
    non-zero tsc exit fails" version was reproduced LIVE to break
    permanently on this real repo's ordinary, correct, mid-TDD state --
    Test-writer deliberately lands RED test files referencing not-yet-
    created modules (its own header: "these do not exist yet ... RED until
    the Coder lands them. That is correct."). Confirmed today: bare
    `tsc --noEmit -p tsconfig.json` on padsplit-cockpit/web returns 3 real
    TS2307/TS2352 errors that no in-flight micro-step is responsible for.

    Fix: compare the current error set against a BASELINE captured once,
    when the micro-step loop begins for a slice (right after Test-writer's
    RED suite lands, before the first Coder dispatch) -- not against a
    clean-repo assumption. A checkpoint fails ONLY on a fingerprint absent
    from that baseline (a genuinely NEW error this step's change
    introduced). Fingerprint = (relpath, tsc error code, message with
    absolute paths/line numbers stripped) -- not raw file:line, since line
    numbers shift as unrelated code in the same file changes across steps.

    NOT YET IMPLEMENTED / net-new design, unlike the rest of this function's
    reuse of _smoke_gate's shape: _parse_tsc_errors (robust multi-line tsc
    output parsing) and _load_type_check_baseline (where/how the baseline
    is persisted -- candidate: a git-tracked JSON file written once per
    slice, analogous to smoke_manifest.json) are named but not designed to
    diff-level here. Flagged as the largest unvalidated piece of this
    proposal -- see Open Risks.
    """
    if not has_typescript_project(project):
        return {"ran": False, "passed": True, "output": "", "new_errors": []}, None

    argv = _resolve_tsc_binary(project) + [
        "--noEmit", "-p", os.path.join(project, "tsconfig.json"),
    ]
    code, out, err = run(argv, project, timeout=TIMEOUT)
    combined = (out + "\n" + err).strip()

    if "canceled due to missing packages" in combined or (
            code not in (0, 1, 2) or ("error TS" not in combined and code != 0)):
        # Toolchain genuinely unresolvable -- distinct from a real type
        # error; never misreport a missing install as "your code is wrong."
        return ({"ran": False, "passed": False, "output": combined[-2000:]},
                "package.json declares typescript but no tsc binary could be "
                "resolved (checked project + parent node_modules/.bin, then "
                "npx --package typescript) -- type-check gate forced fail, "
                "not a type error")

    current_errors = _parse_tsc_errors(combined)          # TODO: implement
    baseline_errors = _load_type_check_baseline(project)  # TODO: implement
    new_errors = sorted(current_errors - baseline_errors)

    return ({"ran": True, "passed": len(new_errors) == 0,
             "new_errors": new_errors, "output": combined[-8000:]}, None)
```

Wire into `main()` (after the existing `smoke` wiring, lines 386–398, same additive pattern):

```diff
     result = detect_and_run(project)
+    type_check, type_check_error = _type_check_gate(project)
+    result["type_check"] = type_check  # additive; existing contract keys untouched
+    if type_check_error is not None:
+        result["passed"] = False
+        result["summary"] = ("%s | TYPE-CHECK GATE FORCED FAIL: %s"
+                             % (result.get("summary") or "", type_check_error))
+    elif type_check["ran"] and not type_check["passed"]:
+        result["passed"] = False
+        result["summary"] = ("%s | type-check gate FAILED (%d new tsc error(s) vs baseline)"
+                             % (result.get("summary") or "", len(type_check["new_errors"])))
     smoke, smoke_error = _smoke_gate(project)
     result["smoke"] = smoke  # additive; existing contract keys untouched
```

**Confirmed sound, unchanged from the draft:** the additive-JSON-contract claim. Read `test_verify_node.py` in full (336 lines) and grepped it plus `test_verify_harness.py` for any full-dict-equality assertion — none exist; every VAC1–VAC7 check tests specific keys/substrings. A new top-level `type_check` key breaks nothing mechanically, same precedent as the `smoke` key.

### 2c. `DESIGN_CHECKLIST.md` — confirmed sound, kept

Reviewer 3 independently re-read all 117 lines and confirmed: none of the 9 existing gates claims binding/import-correctness territory; no gate needs walking back. The live "eight gates below" (line 9) vs. "## The nine gates" (line 11) mismatch is real — confirmed by direct read — a stale count left from H-AC-ORACLE-TARGET-1's own gate-9 addition.

```diff
-trustworthy?"). Enforce that structurally with the eight gates below.
+trustworthy?"). Enforce that structurally with the nine gates below.
+(Mechanical/structural correctness checks — e.g. `harness/verify.py`'s `type_check`
+gate, or any future compiler/linter-class check — are deliberately NOT numbered gates
+here: they are unconditional, un-skippable subprocess checks, not judgment a role must
+remember to apply. This checklist is reserved for adversarial reasoning a mechanical
+check cannot perform.)
```

### 2d. `roles/coder.md` — anti-gaming addition, extended to cover the new baseline mechanism

The original anti-gaming addition (ban suppressing type errors via `@ts-ignore`/`as any`/disabled `strict`) is unchanged and still needed. **Extended** to close a gaming vector the baseline design in 2b introduces that didn't exist in the draft's simpler version — a Coder could "pass" the gate by padding the baseline file instead of fixing code:

```diff
@@ Hard rules @@
 - **No hard-coding to the tests.** Solve the general problem, not the specific assertions.
+- **Never suppress a type-check error instead of fixing the underlying binding/type
+  mismatch** (`// @ts-ignore`, `// @ts-expect-error` without a genuinely tracked reason,
+  a broad `as any` cast used to make an error disappear, disabling `strict` in
+  `tsconfig.json`, or an equivalent Python-side suppression like a bare `# noqa` on a
+  real `F821`). A suppressed error is the same anti-gaming failure as editing a test to
+  pass. The same rule covers the type-check gate's baseline file: never widen or
+  hand-edit the tsc-error baseline to make a genuinely new error look pre-existing —
+  that is editing the gate's answer key, not fixing code.
 - Match the brief's constraints (language, deps, style). Don't add dependencies unless the brief allows it.
```

### 2e. `roles/verifier.md` / `roles/test_writer.md` — confirmed no change needed

`verifier.md`'s Layer 1 reads `passed`/`runner`/`output` generically and was never updated for the `smoke` key either (grepped: zero mentions of "smoke"). `test_writer.md` runs strictly pre-implementation and never touches `verify.py`. Unchanged from the draft.

### 2f. `orchestrator.md` — scoping bullet, rewritten to state the narrower, honest scope from Q1a

```diff
    - **After producing the spec, run a plan-check: dispatch the Verifier**
      (`roles/verifier.md`) on the PLAN before dispatching the Coder. The Verifier's job
      here is to catch a mis-aimed spec — does each acceptance criterion test the right
      thing? Is anything likely to pass green while the goal remains broken?
+   - **The type-check gate has ZERO effect during plan-check and does not shorten a
+     binding-correctness burn that happens before Coder is dispatched.** Plan-check
+     reviews spec.md prose against ACs — there is no code for `harness/verify.py`'s
+     `type_check` key to run against (confirmed against the real 2026-07-04
+     airbnb-calendar incident: the ~9-round "identifier never bound" burn, rounds
+     17–31, was entirely prose-vs-prose; no calendar-sync implementation file existed
+     on disk at any point during those rounds). Binding/wiring correctness moves to
+     the mechanical `type_check` gate ONLY once the micro-step build loop begins and
+     Coder starts landing real files — strictly after plan-check converges, not as a
+     reason to cut plan-check rounds short. If plan-check itself burns many rounds on
+     the same binding-correctness finding class, that is a separate, still-open
+     problem this gate does not solve — the only currently-known mitigation is the
+     2026-07-04 run's own manual round-31 pivot (stop prose review, dispatch
+     Test-writer/Coder, verify with `next build`/`tsc --noEmit` sooner instead of more
+     rounds), which remains Nnamdi's judgment call, not a structural rule, after this
+     proposal. See `fix_plan.md` H-TYPECHECK-GATE-1 "Open, not resolved."
    - **When to dispatch parallel adversarial-lens plan-check Verifiers instead of one
      generalist...**
```

### 2g. Implementation ownership and landing mechanism (new — required, was missing from the draft entirely)

Reviewer 3 found this gap and it's confirmed real: the draft presented finished diffs to `harness/verify.py`, `roles/coder.md`, `orchestrator.md`, `DESIGN_CHECKLIST.md` without ever stating who applies them or how they land, despite all four files being inside — or covered by the catch-all in — the Review-to-commit re-diff gate's mandatory scope (confirmed by direct read of `orchestrator.md` lines 366–401: scope list is `loop-team/orchestrator.md`, `loop-team/*.md` role briefs, `RUN.md`, `VERIFIER.md`, `VERIFIER_RENTALS.md`, `fix_plan.md`, `search_playbook.md`, plus any other loop-team-root prose/config — this gate exists *because* exactly this file class had unreviewed content silently land twice on 2026-07-02, commits `96693f8` and `5884604`, both confirmed via `git show -s`).

- **Every diff above is to be applied by dispatching a fresh Coder Agent call**, per `orchestrator.md`'s "How roles are dispatched" — not authored directly by Oga, and not authored inline in this proposal. The dispatch prompt should point at this design document by path, not paste diffs inline for the Coder to reinterpret.
- **Landing requires `harness/commit_diff_reread.py record <file>`** on each touched file immediately after its diff is reviewed, then **`harness/commit_diff_reread.py commit <file1> <file2> ... -- <message>`** listing every touched scope-listed file together — never a raw `git add`/`git commit`. I confirmed via `git log` that this tool did not exist when the precedent Node/vitest addition to `verify.py` landed (`e19f454`, 2026-07-02 08:30) — `commit_diff_reread.py` was created later that same day (`a7e17f7`) specifically in response to `96693f8`/`5884604`. That means the framework's own history does **not** show a clean prior example of this exact landing chain for `verify.py` — the current requirement must be stated explicitly here rather than assumed from precedent.
- **`harness/verify.py` and `roles/coder.md` are also independently hook-gated.** `grep -n harness ~/Claude/loop/hooks/loop_stop_guard.py` confirms a `ROLE_OR_HARNESS` regex (`"harness/[a-z0-9_]+\.py"` / `"roles/[a-z0-9_]+\.md"`) that requires the eval/regression suite to be green in the *same turn* as any edit to these paths — a second, structurally-enforced requirement independent of `commit_diff_reread.py`, and it applies to two of the four files this proposal touches.
- Followed by an independent Verifier re-check of the diff before any commit, per this framework's standing practice for shared-harness changes.

## Question 3: Cross-reference anti-pattern scope

**Answer, corrected: yes, it's real and mechanically checkable, but the draft's risk-ranking methodology doesn't hold up, and the count of raw hits is not a reliable proxy for actual rot risk — the one CONFIRMED live instance is in the lowest-count file measured.**

### 3a. Measurement (re-run live, corrected, with the missing file added)

| Artifact | `\b(above\|below)\b` hits | Structural type | Confirmed live rot? |
|---|---|---|---|
| `fix_plan.md` | **107** (draft said 106) | Chronological append log, occasionally edited in place (see 3b) | No confirmed instance — the cited "two lines below" example (line 57) currently resolves correctly |
| `orchestrator.md` | 18 | Actively-revised framework file | Not directly, but same mechanism as `DESIGN_CHECKLIST.md`'s bug |
| `learnings.md` | **13 — not measured in the draft at all** | Chronological append log, same structural family as `fix_plan.md` | Not checked |
| `DESIGN_CHECKLIST.md` | 2 | Actively-revised framework file | **YES — the "eight gates"/"nine gates" heading mismatch found in 2c is a real, live instance of exactly this rot** |
| `roles/*.md` (5 files) | 0–3 each | Low-risk, self-contained | No |

`learnings.md` was required by this task's own check list and omitted from the draft's Q3 table entirely — added here. It shares `fix_plan.md`'s dated, chronologically-appended, permanently-growing structure (`## YYYY-MM-DD —` headers, 1536 lines), so it belongs in the same risk-surface family, not excluded.

**The methodological problem the draft didn't surface: raw hit count does not rank actual risk.** `DESIGN_CHECKLIST.md` has only 2 hits and already contains a real, live, currently-broken cross-reference. `fix_plan.md` has 107 hits and zero confirmed-broken instances found so far. Presenting 107/18/13/2 as directly comparable "risk surface" numbers, as the draft's closing synthesis did, overstates what the count alone tells you — the count says nothing about whether a given reference is a precise, rot-prone positional pointer ("two lines below," "the four lenses above") versus a vague rhetorical one that doesn't actually depend on document position ("supersedes... notes below," referring to "everywhere else in this document"). The 107/18/13/2 figures conflate both categories.

### 3b. The append-only vs. revision-prone distinction — softened, with disclosed evidence limits

The draft asserted fix_plan.md's positional pointers are "genuinely fragile" because "nothing before an entry ever moves." I checked this against the file's own limited git history rather than asserting it: `fix_plan.md` has only 3 commits total (it went gitignored early — confirmed via `.gitignore:27:fix_plan.md`), and the earliest tracked version (`34b8900`, 2026-06-28) shows the H6/H7 entries the draft's own example cites as **bare, unannotated `[ ]` open bullets** with none of the "[DONE... closed by... entry two lines below... reconciled 2026-07-02]" annotation text visible in the file today. That annotation, dated "2026-07-02" in its own text, was necessarily added to those lines **after** 2026-06-28 — an in-place edit to an already-existing entry, not a pure, immutable append. In this specific case the edit happened not to insert a line between the anchor and its target, so "two lines below" still resolves correctly today — but that's a spot check surviving, not proof of a general write-once guarantee, and it's the same underlying failure mode (an editor updates content near a positional reference without re-verifying the reference itself) that produced the confirmed-live `DESIGN_CHECKLIST.md` bug. **Revised claim: `fix_plan.md`'s failure mechanism is a weaker but non-zero relative of `spec.md`'s reordering risk — in-place annotation edits happen and can silently break a positional pointer — not the fully immutable append-only log the draft characterized it as.** This is disclosed as unverified beyond the one spot-checked case, not presented as an established fact.

### 3c. Mechanism and triggers — kept, with the "same evidentiary discipline" claim corrected

Per the paper-verification dossier (confirmed via direct fetch of the actual YAML): `errata-ai/Google`'s `WordList.yml` ships a real `substitution` rule, `above: preceding`, `level: warning`, which does not cover `below` or full phrases (`see above`, `as discussed below`) — those need a small custom Vale `existence` rule. **Enforcement level: advisory** (Vale's own default), not structural — a documentation-quality defect doesn't break anything the loop executes, and this repo's own stated posture for exactly this instructional-vs-structural distinction (`orchestrator.md` line 397: Review-to-commit is "presently an instructional, not structural, guarantee") is the direct precedent, kept as-is.

Triggers reuse three existing mechanisms rather than inventing new ones: (1) the Review-to-commit gate's existing scope list, (2) piggybacking the `commit_diff_reread.py` call site on the same files, (3) the existing ≥2-plan-check-rounds threshold for `spec.md` specifically. **Corrected claim about their grounding:** the draft characterized these as following "the same evidentiary discipline" as the state-transition-table lens, whose triggers are each grounded in a named, path-cited real incident that specifically measured *that* technique's marginal value. None of the three above/below triggers has an equivalent — they reuse machinery validated for *different* problems (unreviewed content landing in commits; a tool whose source was never read, only its prose description in `orchestrator.md`; a Verifier-misreads-revision-history incident). This is legitimate administrative economy, not equivalent rigor, and the honest grounding for why a mechanical check earns its keep at all is the one real, if modest, instance found in this session: the `DESIGN_CHECKLIST.md` heading bug, which survived **two independent Verifier passes** on the H-AC-ORACLE-TARGET-1 change per `fix_plan.md`'s own account — real evidence that adversarial human/LLM re-reading does not reliably catch this class, which is the actual argument for a mechanical check, stated honestly rather than borrowing a different technique's evidentiary framing.

### 3d. `DESIGN_CHECKLIST.md` diff — unchanged, correct as drafted (see 2c above; not repeated).

## Adversarial review disposition

- **Lens 1 (mechanism feasibility) — NEEDS_REVISION, confirmed and applied.** Independently re-reproduced both headline findings live (3 real tsc errors on padsplit-cockpit/web today; npx exit-1/`tsc@2.0.4` collision in a synthetic scratch project). Applied: baseline/erosion redesign of `_type_check_gate` (Q1b, Q2b), binary-resolution fix via `_resolve_tsc_binary` (Q2b) — chose direct binary resolution over switching to `next build`, a deliberate, explained disagreement with one reading of this lens's 3rd required revision (see 2a). The "cumulative wall-clock across sequential gates" finding is noted as an existing, non-new property (`_smoke_gate` already has it) and not separately redesigned.
- **Lens 2 (timing/residual gap) — NEEDS_REVISION, confirmed and applied.** Re-read `plan_check_log.md` rounds 27 and 31 directly; confirmed the "real files existed" claim was a misreading of an unrelated `fix_plan.md` citation, and confirmed the round-31 pivot was a manual human decision, not gate-driven. Applied: full rewrite of Question 1 (both 1a and 1b), and `orchestrator.md`'s scoping bullet rewritten to state the residual pre-code gap honestly rather than claiming it's solved.
- **Lens 3 (process conformance) — NEEDS_REVISION, confirmed and applied.** Confirmed `DESIGN_CHECKLIST.md` scoping was already sound (kept as-is) and independently confirmed the live heading bug. Confirmed the `commit_diff_reread.py`/`e19f454` timeline and the `loop_stop_guard.py` `ROLE_OR_HARNESS` hook via direct `git log`/`grep`. Applied: added Q2g (implementation ownership + landing mechanism), and replaced the synthetic blind-validation fixture with the real `acc2e2f~1` vs. `acc2e2f` commit pair (Open Risks below).
- **Lens 4 (documentation anti-pattern scope) — NEEDS_REVISION, confirmed and applied.** Re-ran every grep live and confirmed the 106→107 and 589→588 discrepancies, and the missing `learnings.md` measurement (13 hits, added). Confirmed the H6/H7 in-place-edit counter-evidence via direct git archaeology (`34b8900` shows the entries as unannotated at that commit). Applied: softened the append-only framing (3b), added the raw-count-isn't-risk-ranking correction (3a), corrected the "same evidentiary discipline" overclaim (3c).

No two lenses directly contradicted each other's facts; all four were corroborated by my own independent checks. The closest thing to a disagreement was lens 1 nudging toward replacing `tsc --noEmit` with `next build` to sidestep the npx collision — resolved above (2a) by fixing the collision directly via binary resolution instead, since the real incident record shows both checks used together historically, not as substitutes.

## Open risks / what still needs the H-AC-ORACLE-TARGET-1-style blind validation before this is trusted

1. **The baseline/erosion `_type_check_gate` redesign is wholly new, unvalidated design work**, not reused machinery like `_smoke_gate`. `_parse_tsc_errors` and `_load_type_check_baseline` are named, not implemented. This is the single largest piece of unproven design in this document and needs its own dedicated spec + validation round before being trusted, independent of the rest of this proposal.
2. **`_resolve_tsc_binary`'s fallback chain is unwritten/untested as code**, though every individual behavior it's built on was independently confirmed this session (project-local resolution semantics, parent-workspace hoisting on the real repo, the exit-1/`tsc@2.0.4` collision, the `--package typescript` fix reducing but not eliminating the "not installed" failure mode — still exit 1 with the same "canceled" text when nothing is installed anywhere npx can see).
3. **`has_typescript_project`'s silent-skip-vs-loud-fail edge case remains undecided** (tsconfig present, `typescript` dep accidentally absent from `package.json`) — VAC7 precedent argues for loud, but this isn't resolved here.
4. **`commit_diff_reread.py`'s actual source was never read** by the draft, by any of the 4 reviews, or by this synthesis — only its prose description in `orchestrator.md`. The landing-mechanism requirement in Q2g rests on that prose description; if the tool's real interface doesn't support this cleanly, a standalone Oga-run fallback is weaker precedent than stated.
5. **Pre-code plan-check binding-review is explicitly NOT solved by this proposal** (Q1a) — whether the round-31 pivot should become a structural trigger (round-count or repeat-finding-class) in `orchestrator.md`'s plan-check section, or whether a complementary early-stub mechanism is worth designing, is named but not designed here.
6. **Near-empty/new-project semantics for the baseline model are not fully worked out**: `has_typescript_project` flipping False→True mid-build (once scaffolding creates `tsconfig.json`/`package.json`) needs a defined "baseline moment," and a micro-step's own necessarily-incomplete cross-file references (not an untouched unrelated file, but the current step's own unfinished graph) is a distinct failure shape from "a pre-existing Test-writer RED file" that the baseline design may or may not handle gracefully — not proven either way.
7. **The Python-side (`flake8` fatal-set) sibling is named but not designed** — most of loop-team's past builds are Python, and this proposal scoped entirely to the TS side because that's what the real incident and real target repo ground.
8. **The Vale lint mechanism (Q3) was never actually run.** Only the existence and content of `errata-ai/Google`'s `above: preceding` rule was confirmed (via direct fetch); no custom `below`/phrase-anchor rule was written or tested against any real file in this session.
9. **Blind gate validation must use real incident data, not a synthetic fixture** — supersedes the draft's proposed synthetic "one unbound identifier" test. Two real, recoverable fixtures exist and should be used: (a) the PSC-TSC-1 commit pair (`acc2e2f~1` = real 6-error pre-fix state, `acc2e2f` = real clean post-fix state, both confirmed to exist via `git show --stat`); (b) the padsplit-cockpit/web repo's actual current state (3 real errors, confirmed live today) as the first test of whether the baseline-scoping redesign correctly treats Test-writer's intentional RED files as non-blocking. A fresh agent, blind to this document and to the PSC-TSC-1/fix_plan.md narrative, should run the wired-in gate against both.

## Not yet done

This is a **design document for approval**, not an implementation. Consistent with the standing "plan before execution" rule: no code has been written or applied in this session (all diffs above remain proposals grounded in direct reads of the real files, not committed changes); no `fix_plan.md` entry has been filed (the H-TYPECHECK-GATE-1 draft below is a proposal, marked `PROPOSED, not yet filed/applied`); the ownership/landing mechanism (Q2g: fresh Coder dispatch, `commit_diff_reread.py record`/`commit`, `loop_stop_guard.py` green-suite requirement, independent Verifier re-check) is specified but not executed. The next required step, before any of this is trusted, is the blind validation named in Open Risk 9 — grounded in the real PSC-TSC-1 commit pair and the real current padsplit-cockpit/web red state, not a synthetic fixture — followed by an independent Verifier re-check of whatever diff actually gets applied.

```
## H-TYPECHECK-GATE-1 (PROPOSED, not yet filed/applied) -- harness/verify.py has no
compiler/typecheck signal; binding/wiring bugs (unbound identifiers, missing
imports/exports) are caught only by manual `tsc` runs or plan-check prose re-reading,
not structurally, once real files exist.

**Found by:** deep-research dossiers, corroborated by direct reads of learnings.md
(2026-07-01 vitest-only-idiom entry) and fix_plan.md H-LT5/PSC-TSC-1 (the Node/vitest
half of this gap closed 2026-07-01; the tsc half never filed as its own entry).

**Scope, corrected after review:** this gate does NOT shorten pre-code plan-check
binding-review rounds -- confirmed against the real 2026-07-04 airbnb-calendar
incident (rounds 17-31 were entirely prose-vs-prose; no implementation file existed
during any of those rounds). It applies ONLY from the first Coder dispatch of a
slice's micro-step loop onward. The actual historical resolution of that burn was a
manual human process-pivot at round 31 ("stop prose review, verify with next
build/tsc instead"), which this gate structurally formalizes for the phase AFTER
that pivot point, not before it.

**Fix proposed:** `_resolve_tsc_binary()` + `has_typescript_project()` +
`_type_check_gate()` (BASELINE/EROSION-SCOPED, not naive nonzero-exit-fails) in
`harness/verify.py`, wired into `main()` as an additive `type_check` key ANDed into
`passed`. One scoping bullet in orchestrator.md (plan-check does not claim
binding-correctness territory once real files exist; states explicitly it does NOT
solve the pre-code burn). One anti-gaming line in roles/coder.md (no suppressing
type errors or padding the baseline). Heading fix + footnote in DESIGN_CHECKLIST.md.

**CONFIRMED LIVE, 2026-07-08, that the naive (non-baseline) version of this gate is
NOT safe to ship:** `npx --no-install tsc --noEmit -p tsconfig.json` against the real
padsplit-cockpit/web returns 3 real errors right now, against untracked,
intentionally-RED Test-writer files for a slice whose Coder has not yet been
dispatched. A gate without baseline scoping would force-fail every micro-step
checkpoint on this repo starting today, for reasons unrelated to any given step.

**Gate validation required before trusting it (NOT YET DONE):** dispatch a fresh
agent, blind to this entry and to PSC-TSC-1/fix_plan.md, against TWO real fixtures:
(a) the real PSC-TSC-1 commit pair (`acc2e2f~1` = 6 real pre-fix errors, `acc2e2f` =
real clean state); (b) the current live padsplit-cockpit/web state, to confirm the
baseline-scoping logic correctly treats Test-writer's known RED files as non-blocking
while still catching a genuinely new error. Plus an independent Verifier re-check of
the verify.py diff itself.

**Open, not resolved by this entry:** the baseline/erosion design itself
(_parse_tsc_errors, _load_type_check_baseline) is unimplemented; has_typescript_project's
silent-skip-vs-loud-fail edge case undecided; near-empty/new-project baseline-moment
semantics unresolved; pre-code plan-check binding-review remains exactly as manual as
before this proposal; Python-side flake8 sibling undesigned; commit_diff_reread.py's
actual source interface never read (landing mechanism rests on orchestrator.md's prose
description of it only).
```

Files read directly in this session (all line/byte counts and command outputs above are from live re-verification, not trusted from the draft or the 4 reviews): `~/Claude/loop/loop-team/harness/verify.py`, `~/Claude/loop/loop-team/orchestrator.md`, `~/Claude/loop/loop-team/DESIGN_CHECKLIST.md`, `~/Claude/loop/loop-team/roles/coder.md`, `~/Claude/loop/loop-team/harness/test_verify_node.py`, `~/Claude/loop/loop-team/learnings.md`, `~/Claude/loop/fix_plan.md`, `~/Claude/loop/hooks/loop_stop_guard.py`, `~/Claude/loop/runs/2026-07-04_airbnb-calendar/plan_check_log.md`, `~/Claude/Projects/padsplit-cockpit/{package.json,web/{tsconfig.json,tsconfig.src.json,next.config.ts,package.json},web/tests/airbnb-calendar-sync.test.ts}`, plus git history on both repos (`e19f454`, `a7e17f7`, `96693f8`, `5884604`, `acc2e2f`, `34b8900`) and live command execution of the proposed `tsc` invocation against both the real target repo and a synthetic scratch fixture at `/private/tmp/claude-501/.../scratchpad/tsc-test`.

---

## Related research (this design session)

- `research/compiler-feedback-loop-prior-art-2026-07-08.md` — GitHub repo search: Drift Validator has no code anywhere (industry-wide, not just here); arXiv:2601.19106's companion repo is academic-only (2 stars); Aider/Cline/OpenHands prior art; conclusion that the compiler itself is already the best available tool for this bug class.
- `research/compiler-feedback-loop-paper-verification-2026-07-08.md` — primary-source verification: arXiv:2606.27045 is an unimplemented, unevaluated single-author preprint; arXiv:2601.19106's numbers confirmed (Python-only, 200 samples); Google/Microsoft/MDN cross-reference style guidance confirmed 3-for-3; Vale's `errata-ai/Google` `above: preceding` rule confirmed real.
- `research/spec-first-vs-code-first-ai-agent-builds-2026-07-08.md` — originating research that first flagged this gap.
- `research/radar.md` — updated with new candidate rows from the prior-art dossier.
