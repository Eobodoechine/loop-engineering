# Research: dynamic-screen / single-focus UI patterns for a "review mode"

**Date:** 2026-07-12. **Trigger:** after seeing the shipped control-plane dashboard redesign,
Nnamdi said he's "overwhelmed by too much on one page" and wants it "dynamic with screen
changes." This research grounds what that should actually look like — not just a request to
research and forget.

**Method:** 4 parallel research agents (Workflow, high effort) covering ADHD planning apps,
focus-timer apps, non-ADHD-branded step/wizard UX patterns (Typeform/Duolingo/Linear/Notion),
and written ADHD/cognitive-load UX guidance (W3C COGA, clinical/institutional sources). 60 tool
calls, ~299k tokens. One synthesis agent fused the findings into a design brief.

## The one-sentence finding

Real ADHD-native planning apps (Tiimo, Structured) keep a dense **timeline/overview as the
default view** and treat single-focus mode as an **opt-in layer** (a Focus Timer you step into)
— they do NOT default to single-item wizards. Pure single-focus tools (Llama Life, Forest,
Amazing Marvin's Super Focus Mode) are task-timers, a different job than a status dashboard, and
Marvin's own docs frame single-focus as an opt-in "Strategy," not a baseline mode.

## Net recommendation

Treat a staged, single-focus flow as an **additive "review mode"** layered on top of the
existing dashboard (never a replacement): scoped to flagged/actionable items only, capped in
length (research: one-question-per-screen degrades past ~12-15 items — Typeform/Fillout), with
an always-visible escape hatch back to the full comparison view. The full dense view stays the
default for "what's going on," because comparison across items (do two mismatches relate? did
verification status change together?) is structurally hostile to a pure sequential wizard — none
of the sequential-flow research (forms, lessons, onboarding) covers a comparison use case, and
that's a real gap, not an oversight to route around.

## 8 concrete mechanisms, ranked (each sourced — see full JSON for citations)

1. **Task player with an ambient "remaining queue"** (not fully hidden) — Llama Life, Marvin's
   "Top of Mind" floating window.
2. **One decision per screen, forward-only, completion-gated advance** — Linear onboarding,
   Typeform, Duolingo.
3. **Visible, action-gated progress indicator** (not just a step-counter) — Duolingo's
   fill-as-you-go bar (goal-gradient effect), Notion's "position + next-step preview" pairing.
4. **Externalized ambient time cue, never a bare digit** — Barkley's externalization principle
   (time-blindness), Tiimo's ring+numeral combo, Forest's growing tree.
5. **Non-punitive, low-stakes completion feedback** — Tiimo ("nothing turns red, nothing gets
   marked as failed"), Llama Life's confetti + extend-or-done choice (not forced auto-advance).
6. **Progressive disclosure of detail, summary first** — W3C COGA "Avoid Too Much Content" /
   "Support Simplification," Gareth Ford Williams' recognition-over-recall.
7. **Explicit skip affordance for non-decisions** — Notion's optional steps, Linear's
   "import or skip" pattern; verified/calm items get batched, not forced through single-focus.
8. **Session-end review/digest screen** — Session's post-session reflection, Duolingo/Linear's
   checklist-as-destination.

## Where the research argues AGAINST going further

- Real ADHD planners default to overview, not wizard (see above) — the dense grid should stay
  the default entry point, not be replaced.
- Typeform/Fillout's own scoping caps this pattern at short flows; beyond ~12-15 sequential
  screens it reads as *slower*, the opposite of the goal.
- No research category studied a comparison task directly — a real gap. Mitigation: the "view
  full dashboard" escape hatch is load-bearing, not polish.
- Linear's "no progress indicator" and Duolingo's "no back navigation" are context-specific to
  low-stakes/no-consequence flows — a judgment-heavy review flow (is this claim still accurate?)
  should keep both a progress bar and undo/back, unlike those sources' own defaults.

## Sources (representative — full citations in the workflow journal)

W3C WAI COGA "Making Content Usable" (w3.org/TR/coga-usable); Gareth Ford Williams,
uxdesign.cc/adhd-dyslexic-perspective-on-cognitive-accessibility; University of St Andrews
Digital Communications, "Designing for users with ADHD"; Russell Barkley's externalization/
time-blindness research (via reachlink.com summary); Tiimo (tiimoapp.com/product/focus);
Llama Life (llamalife.co, via nesslabs.com interview + focusbear.io review); Forest
(forestapp.cc, via resetadhd.com); Amazing Marvin Super Focus Mode docs
(help.amazingmarvin.com); Typeform history (smashingmagazine.com) + scoping guidance
(fillout.com); Duolingo case study (usabilitygeek.com) + goal-gradient analysis
(motivate.design); Linear onboarding teardowns (candu.ai, supademo.com); Notion onboarding
(goodux.appcues.com).

## Mockup built from this research

An interactive stepper widget (triage summary → single-focus item screens with progress bar and
ambient queue → batched skip screen for verified items → session summary → persistent "view
full dashboard" escape hatch) was shown inline in the same session. Not yet a spec — this is
design exploration, not a build. If Nnamdi wants this as a real feature, it needs its own spec →
plan-check → Test-writer → Coder loop, scoped to a "review mode" additive to
`render_control_plane`, not a replacement.
