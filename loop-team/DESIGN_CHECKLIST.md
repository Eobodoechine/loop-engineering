# Design-time adversarial checklist

*The loop's throughline is "something must be able to say **no**." `ACCEPTANCE_AND_VERIFICATION.md`
makes the "no" statistically honest at commit time. This checklist makes it honest at
**design time** — before code ships, not after a leak.*

**Root principle: be adversarial at design time.** The default failure is *builder mode*
("it produces output → done"). The loop must operate in *auditor mode* ("is the output
trustworthy?"). Enforce that structurally with the eight gates below.

## The eight gates (who owns each)

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

## Where this came from
Distilled from real bug arcs. Rental scraper: an enumerated room/share regex leaked case
after case; a city-level Walk Score was presented as unit-level; a single in-run fetch was
trusted as verification; a rising "valid count" was mistaken for progress. Verifier-loop:
a judge's self-corrected verdict, parsed by its first token, was mistaken for a model
"blind spot" and chased for hours without anyone reading the model's actual reasoning or
checking the harness. Each maps to a gate above.
