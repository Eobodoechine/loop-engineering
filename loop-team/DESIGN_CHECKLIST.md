# Design-time adversarial checklist

*The loop's throughline is "something must be able to say **no**." `ACCEPTANCE_AND_VERIFICATION.md`
makes the "no" statistically honest at commit time. This checklist makes it honest at
**design time** — before code ships, not after a leak.*

**Root principle: be adversarial at design time.** The default failure is *builder mode*
("it produces output → done"). The loop must operate in *auditor mode* ("is the output
trustworthy?"). Enforce that structurally with the ten gates below.

## The ten gates (who owns each)

1. **Model the category, then red-team it — from the REAL corpus.** *(coder + test_writer)*
   For any classifier/filter/regex, write down what the class IS, then enumerate
   adversarial members AND counter-members. Ship only after both sets pass. Reject
   "added the phrase that just leaked" — that's whack-a-mole, not a model.
   **Crucially, draw the adversarial set from REAL production inputs, not imagination** —
   pull a sample of actual listings/leads/rows and run the classifier on them. Imagined
   cases share the coder's blind spots; the failure that bites is the *unmodeled category*
   that exists in the wild but nobody pictured (a by-the-bed "4x4 student apartment" room
   passed as a whole unit). Ask: "does the model cover the real distribution?"

2. **Provenance over value.** *(coder + verifier)*
   Every field that gets presented or stored must trace to a source that supports the
   claim attached to it. A value derived from a coarser proxy (city-level score for a
   unit-level claim) is downgraded or withheld, never presented at full confidence.

3. **Propose ≠ verify.** *(verifier + live_smoke)*
   The component that produces a result may not certify it. An independent stage must
   re-derive the result against reality (re-load, re-run, re-measure) before acceptance.

4. **Precision, not throughput — FULL-READ the certified set, INCLUDING IMAGES, both
   directions.** *(verifier + gold_judge)*
   Never report "more passed" as success. The metric is *of what passed, how much is
   truly correct* — established by **opening and reading the actual passing outputs
   end-to-end, in full, IMAGES INCLUDED** (the real listing/page/row), not by counting
   flags or trusting title/text (both are routinely gamed; flyer photos carry the real
   terms — "ROOM FOR RENT · shared bath"). Two populations, two rules: **sample** only for
   DISCOVERY over an unbounded input space; **read EVERY item** of the finite certified set
   — exhaustive, images included (a PM-managed shared room sat at #1 of a "verified" list
   because no one opened its flyer). And audit the filter in **both directions** — open a
   real sample of the DROPS too (with images) to catch good items wrongly discarded by a
   brittle shape/keyword/geo rule. A title-level drop audit is itself untrustworthy.

5. **Skeptic by default.** *(all roles)*
   Assume the output is wrong and try to break it. Diagnose causes from the run's own
   artifacts, never from circumstantial signals (timestamps, "it was probably X").

6. **Probe before you theorize — and distrust your own instrument.** *(all roles)*
   When something looks broken or surprising, reach for the CHEAPEST real test first
   (read the label, vary one knob and measure, look at the actual page) before building a
   theory or a fix. A whole session was lost theorizing "capture pollution / GraphQL
   doc_id isolation" when the cause was a 100-mile radius setting findable in one probe.
   And before trusting any conclusion, validate the MEASUREMENT: an indiscriminate recon
   made "Marketplace is dead" look true when it was the tool, not the world. Never
   *conclude* from a flawed instrument, and never *commit* to a method you haven't proven
   end-to-end against reality.

7. **Recall & goal-achievement — own what gets DROPPED, not just what passes.** *(orchestrator + verifier)*
   Precision and recall are orthogonal: a filter can be flawless on every item it keeps and
   still FAIL the goal by silently dropping real results. So someone must own recall:
   **sample the DROPS against the user's actual goal criteria, estimate the false-negative
   rate, and report recall — not just precision.** A precise-but-thin result (far fewer real
   fits than the corpus plausibly holds) is a goal FAILURE, weighted equally to a false-pass.
   Report *goal-achievement* (did the user get enough real, valid results?) separately from
   *spec-conformance* (do the tests pass). Spend MORE scrutiny on the drops than the passes
   (LLM judges have a precision bias — they over-trust what's kept). Surface caveats on a
   PASS, not only a FAIL. "Everyone assumed someone else checked the drops" is how a clean,
   empty pipeline ships.

8. **Understand the WHY before the fix — read the reasoning, rule out the harness.** *(orchestrator + verifier)*
   When something fails or surprises, do NOT iterate on the verdict — capture and READ the
   actor's actual reasoning / raw output, then locate the gap: the model's logic, the spec,
   or OUR measurement (verdict parser, sampling temperature / nondeterminism, a silently
   dropped model). **Rule out the measurement before concluding the model is wrong.** A
   self-correcting judge ("VERDICT: FAIL … wait … VERDICT: PASS") scored on its FIRST token
   manufactured a fake cross-model "blind spot" that cost hours of looping — the model was
   right, the parser was wrong. You cannot fix what you have not diagnosed, and the
   diagnosis lives in the reasoning you have to actually read (`role_runner.run_role_explained`
   retains it and flags self-correction). Ask what a sharp human asks: *why did it answer
   that way? did we read it, or assume?*

9. **Adversarial-AC oracle targeting — trace which entity's state actually changes, don't
   re-derive the scenario.** *(state-transition-table lens + verifier)*
   For every SECURITY/cross-tenant/adversarial acceptance criterion (a "reject cross-org
   X" or "actor A cannot affect actor B" claim), do not just re-walk the scenario and
   confirm the reasoning holds — **identify, in writing, which actor's/org's/row's state
   would actually change if the guard were silently weakened or removed**, then verify the
   AC's own DB-state assertion targets THAT actor, not the one that merely sounds like the
   victim. A write's `orgId`/owner column is normally session-derived (the ATTACKER's own
   identity), not the id the attacker merely referenced in the payload — an assertion that
   checks the REFERENCED org's table for emptiness is checking a location the wrongly-
   written row can never appear in, and passes green whether the guard works, is silently
   narrowed, or is removed entirely. Re-deriving the same scenario a second, third, or
   tenth time does not catch this — the walk-through was never wrong, the CHECK was wrong,
   and repeating identical reasoning against a fixed oracle predictably reproduces the same
   blind spot every time. `roles/test_writer.md` LOOP-M3 flags any such AC's test
   `# [SECURITY-ORACLE]` at write time (before code exists, so it cannot itself run a
   mutation check). Once code exists, `roles/adversarial_test_writer.md` Phase 3.5 MUST
   run this reasoning check for real on every `[SECURITY-ORACLE]` test: deliberately
   narrow the specific guard clause and confirm the AC's OWN test goes red on the weakened
   version before trusting it goes green on the correct one.

10. **Binding-class saturation — stop hand-simulating the compiler once it's
    the ONLY thing still recurring, and only past an explicit operational
    test, never on surface resemblance alone.** *(orchestrator + coder)*
    A plan-check PLAN_FAIL can mean two very different things: a genuine
    logic/concurrency/security defect the lenses exist to catch, or a
    **binding-class** defect — an undeclared identifier, a missing
    import/export, a missing `'use client'`/`'use server'` directive, a
    naming collision, or "prose describes an edit but never shows the
    literal code" — that a real compiler/bundler (`tsc --noEmit`, `next
    build`) catches for free in seconds, no prose review required. Before
    assigning `[BINDING]` to any finding, the tagger must apply one
    concrete, operational test: **would `tsc --noEmit` or `next build`
    literally reject this, with ZERO code executed?** If yes, tag
    `[BINDING]`. If the defect only manifests as wrong behavior AT RUNTIME —
    a thrown exception nobody catches, a value nobody wires through, a
    control that renders but defaults wrong — tag it `[LOGIC]` (or
    `[CONCURRENCY]`/`[SECURITY]`), never `[BINDING]`, regardless of how
    closely it resembles a `[BINDING]` exemplar on the page. Three named
    exclusions are carved out of the bucket for exactly this reason — this
    run's own data shows all three recur, all three superficially fit the
    bucket's "prose describes an edit but never shows the literal code"
    wording, and all three are compiler-invisible: (a) **missing exception-
    handling for a stated invariant** ("never throws," with an unguarded
    call sitting outside the only `try`/`catch`) — round 24's exact bug,
    where the new `getSession()` guard sat in its own code block before
    `saveCalendarLink`'s only `try`/`catch`, found independently by four
    lenses, compiling cleanly either way; (b) **missing data-wiring between
    a UI element and its consumer** (a hidden input never connected to the
    value it must carry) — round 27's exact bug, where `syncNowAction` read
    `formData.get('calendarLinkId')` but no `<input type="hidden"
    name="calendarLinkId">` was ever specified, silently breaking every real
    "Sync now" click while every test built `FormData` programmatically and
    stayed green — notable because this class is invisible to BOTH the
    compiler AND the test suite; (c) **UI/UX default-state correctness**
    (e.g. a `<select>` defaulting to the wrong option) — round 28's exact
    bug, where no mechanism was specified to stop the property selector from
    visually defaulting to its first `<option>` in the "no property
    selected" state. Tag every PLAN_FAIL finding at write time as
    `[BINDING]` or `[LOGIC]`/`[CONCURRENCY]`/`[SECURITY]` (mirroring
    `test_writer.md`'s existing `[SECURITY-ORACLE]` tag-at-write-time
    convention, gate 9 above), applying the operational test and the three
    exclusions above before any tag is treated as final. Once the last **3
    consecutive rounds** each carry a `[BINDING]` tag on the SAME recurring
    signature AND **zero** `[LOGIC]`/`[CONCURRENCY]`/`[SECURITY]` tag
    appears anywhere in that 3-round window, STOP dispatching further prose
    rounds for that finding class: carry any still-open `[BINDING]` findings
    forward verbatim as Coder implementation notes (caught by the real
    build/compile gate, not more prose) and proceed to Test-writer → Coder.
    The zero-new-finding clause is load-bearing, not optional — it stands
    the counter down the instant a lens is still finding a real bug, so a
    stretch that is ALSO producing new non-binding findings never triggers a
    stop no matter how many binding recurrences pile up next to it. N=3, not
    lower or higher — but N=3 is a REASONED JUDGMENT CALL, not a rule this
    run's own history literally fired three-in-a-row: a single occurrence is
    just a bug, but a SECOND recurrence of the identical signature was
    already enough for this project's own regression-audit lens to call it
    "a systematic authoring gap worth addressing structurally" — said
    explicitly on the THIRD occurrence of the same bare/undeclared-
    identifier signature (rounds 17, 22, and 23 of the airbnb-calendar-sync
    spec). Cite those three rounds ONLY as evidence that this project's own
    lenses treat three occurrences as the point recurrence stops looking
    like coincidence — NOT as a worked example of this gate's literal round-
    adjacent trigger, because rounds 17→22→23 are not consecutive round
    numbers (rounds 18-21 sit between them, including round 19's real cross-
    tenant security finding). Checked honestly against the full rounds 16-31
    log: no genuinely round-adjacent (N, N+1, N+2) 3-round stretch of
    pure-`[BINDING]`-with-zero-non-binding actually exists anywhere in this
    run. Rounds 25 and 26 are each, individually, clean `[BINDING]`-only
    rounds (a real try/catch scoping defect and a missing-import defect,
    respectively — both genuinely compiler-catchable) — but 23-24-25 and
    24-25-26 are disqualified by round 24's exclusion-(a) defect above, and
    25-26-27 is disqualified by round 27's exclusion-(b) defect; every other
    3-round window from 16 through 31 is disqualified the same way, carrying
    at least one live `[LOGIC]`/`[CONCURRENCY]`/`[SECURITY]` finding from
    some lens. So 3 is used here as the earliest point recurrence is
    distinguishable from coincidence, not because this run ever literally
    tripped the mechanical trigger — a higher N (5+) only buys more rounds
    of pure re-confirmation cost, since safety against a premature stop is
    carried entirely by the zero-new-finding clause, not by counting higher.
    If a future run produces a real round-adjacent 3-in-a-row
    pure-`[BINDING]` stretch, THAT becomes the first worked example; say
    plainly that this run isn't it, rather than implying a precedent exists
    where none does. In the run this gate is built from, the same binding
    signature (bare/undeclared identifiers, missing
    imports/exports/directives) recurred 9 times through round 30, while
    genuinely new `[LOGIC]`/`[CONCURRENCY]`/`[SECURITY]` findings kept
    surfacing throughout the SAME overall stretch — not only rounds 19-21,
    but round 24 (exclusion (a)), round 27 (exclusion (b)), and round 28
    (exclusion (c)) above, plus AC19 (round 30) and AC16 (round 31), the
    run's two most important findings, landing at the very end. This is
    exactly why the operational test and the three named exclusions matter
    more than the round-count itself: rounds 24, 27, and 28 all
    superficially resemble the `[BINDING]` bucket's own wording, and a
    tagger relying on surface resemblance alone — primed, for instance, by
    two immediately-preceding clean-`[BINDING]` rounds — could plausibly
    mistag any of them `[BINDING]`, manufacturing a false clean 3-round
    window and firing a premature STOP rounds before AC19/AC16 ever
    surfaced. Any 3-round window touching 19-21, 24, 27, 28, or 30-31
    carries a live non-binding tag under the corrected classification and is
    correctly disqualified, while a run of rounds producing nothing but the
    same binding recurrence — with the operational test and exclusions
    correctly applied — is exactly what this gate exists to cut short before
    a human has to eyeball the pattern by hand.

## Where this came from
Distilled from real bug arcs. Rental scraper: an enumerated room/share regex leaked case
after case; a city-level Walk Score was presented as unit-level; a single in-run fetch was
trusted as verification; a rising "valid count" was mistaken for progress. Verifier-loop:
a judge's self-corrected verdict, parsed by its first token, was mistaken for a model
"blind spot" and chased for hours without anyone reading the model's actual reasoning or
checking the harness. padsplit-cockpit Slice 6b: a hand-written cross-org adversarial AC
asserted `forOrg(orgB).calendarLink.findMany(...)` returned empty as proof no cross-org
row was written — but a wrongly-created row would carry the session's OWN org (orgA), so
the check was structurally guaranteed to pass whether the ownership guard worked, was
narrowed, or was deleted outright. Ten separate plan-check rounds re-walked the identical
cross-org scenario and confirmed the REASONING was sound every time, because the bug
lived in the CHECK, not the scenario, and no round asked "which org's table would the
wrong row actually land in?" until round 30. Each maps to a gate above.
