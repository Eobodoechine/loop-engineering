# ADHD Control-Plane Dashboard — Fused Design Brief

**Date:** 2026-07-12
**Purpose:** synthesize three research passes into one actionable design brief for a
dashboard-redesign build through the loop. This is the spec INPUT for that build, not the
spec itself — a plan-check Verifier should still review the resulting spec before any Coder
work starts.

**Inputs fused here (read each for full detail/citations):**
1. `research/internal-audit-adhd-control-plane-dashboard-2026-07-12.md` — traces our
   EXISTING plan/spec decisions to their sources; found the trust-model was well-researched
   but visual/interaction design was not.
2. `research/deep-research-adhd-dashboard-uiux-patterns-2026-07-12-report.json` — UI
   patterns + comparable products (Linear, calm tech, cards, progressive disclosure).
   104 agents, 9 high-confidence findings, adversarially verified (2 claims refuted and
   excluded).
3. `research/deep-research-adhd-clinical-foundations-2026-07-12-report.json` — the clinical
   cognitive-science layer (Barkley, Cowan, Sweller/Paas, Risko & Gilbert, Masicampo &
   Baumeister). 111 agents, 8 high-confidence findings, 28 sources, zero refuted.

---

## 1. The one-sentence brief

**Minimize what the surface asks the user to hold in his head or decide, put state and the
next action AT the point of work, and make "verified" earn a visibly different signal than
"claimed" — because the entire value of this dashboard is that it can be trusted as external
memory, and trust is what determines whether an ADHD user actually uses it instead of
reverting to holding everything in his head.**

---

## 2. Why (the science, condensed to what changes the design)

Each line is a design-determining finding, not background reading.

- **ADHD is a performance disorder, not a knowledge one (Barkley 1997).** The user already
  knows what's done and what's not — the problem is that *knowing* doesn't reliably convert
  to *acting* on it. Internal/covert information is a weak trigger for behavior. →
  **Implication: this dashboard cannot just be "information available somewhere." It must
  be an overt, physical, always-visible cue placed where work happens — not documentation
  you have to go read.**

- **Point of performance (Barkley).** Interventions work when inserted at the exact
  place/time behavior needs to change — not as knowledge delivered elsewhere. →
  **Implication: the dashboard's value depends on WHERE Nnamdi encounters it (ideally at
  the start of a work session / in the dev environment), not just that it exists.** This is
  a deployment/workflow question, not just a rendering one — flag as a build decision, not
  only a CSS one.

- **Working memory holds ~3-4 items (Cowan, not Miller's 7±2), and ADHD's WM deficit is
  large and replicated (Martinussen 2005, ES 0.43-1.06).** → **Never require more than
  ~3-5 live decision-relevant items in view. Everything else must be collapsed, chunked, or
  peripheral.**

- **Cognitive Load Theory's real principle is SUBSTITUTE load, not just reduce it
  (Sweller; Paas & van Merriënboer 2020).** Stripping decorative chrome while keeping
  action-relevant density is correct; stripping information the user needs to act is not.
  → **Every element on the page must justify itself as action-relevant. "Looks clean" is
  not the goal — "every remaining pixel helps you act" is.**

- **Cognitive offloading works, but only if the tool is TRUSTED (Risko & Gilbert 2016;
  Boldt & Gilbert 2019).** Whether someone offloads to a tool is governed by (a) their own
  low confidence in memory — which is exactly the doubt-prone population this is for — and
  (b) trust in the tool's reliability. Unreliable state gets abandoned. →
  **This is the strongest justification yet found for the CLAIMED vs. VERIFIED distinction
  already built into the spec. It is not a nice-to-have; it is the mechanism that makes the
  whole dashboard usable as external memory at all.** A dashboard that ever shows "verified"
  when it wasn't will be trusted less on every subsequent use — the credibility cost is
  asymmetric.

- **Open loops (unfinished, plan-less tasks) cause measurable intrusive rumination
  (Zeigarnik / Masicampo & Baumeister 2011) — but a CONCRETE NEXT STEP eliminates most of
  that interference.** A bare list of unfinished work can make rumination worse, not
  better. → **Every open/mismatch item must show a concrete next action, not just a status
  label. "Done Verified — MISMATCH" is not enough; it must also say what to do about it.**
  This is a genuinely new requirement the current spec doesn't have.

- **Time blindness / temporal discounting (Barkley; adolescent evidence, adult magnitude
  inferred).** ADHD behavior is governed by the immediate now; distant consequences don't
  register. → **Surface elapsed/staleness time explicitly ("verified 2 days ago" / "claimed
  14 days ago, never re-checked") rather than only a static badge.** This also has a
  mechanical hook already: `validate_proof_record`'s `stale_or_valid` axis — currently
  computed but not rendered anywhere. Rendering it is a small, high-value addition.

- **Motivation must be externally supplied too, not just information (Barkley) — small,
  immediate, frequent cues — but this is in real tension with calm/low-stimulation design
  (open question, not resolved by either research pass).** → Ship the calm/low-stimulation
  version first (it has the stronger, more direct evidence); treat momentum/reward cues as
  a deliberately deferred, separately-tested addition, not bundled into v1.

**Two things researchers explicitly could NOT verify — do not present these as settled:**
redundant color+icon+text encoding for ADHD specifically (real WCAG 1.4.1 principle, but
not sourced to ADHD research in this pass — apply it anyway as basic accessibility, just
don't cite it as ADHD-specific), and task-initiation / "wall of awful" (no surviving primary
citation — the single-focus-pointer design is supported only indirectly, via
externalization + Masicampo & Baumeister's plan-making finding).

---

## 3. What (concrete rendering changes, mapped to the actual dashboard)

Current render (`render_control_plane` in `product_dashboard.py`) emits per-item text that
runs together with minimal hierarchy, and has no page-level structure beyond a flat card
grid. Concrete restructuring, each tagged with its evidence basis and its buildability:

| # | Change | Evidence basis | Stack |
|---|--------|----------------|-------|
| 1 | **One focus banner at the very top**, visually dominant, above the card grid — not just a `.cp-focus` class on a card buried in the grid | Barkley point-of-performance + externalization; UI-pattern finding #0 | Pure CSS |
| 2 | **Three-tier visual weight**: focus (loudest, center) > mismatch/claimed-unverified (loud, warning glyph) > verified (quiet, desaturated, can be visually secondary/collapsed) | Calm-technology (periphery for stable state) + WM-capacity (don't compete for attention with settled items) | Pure CSS |
| 3 | **One card, one concept**: product name + status as the dominant visual element, sized/weighted well above everything else; generous whitespace; near-black-on-off-white, not stark pure-contrast | UI-pattern finding — fixes the exact "text running together" symptom reported | Pure CSS |
| 4 | **Redundant status encoding**: every state = icon/glyph + text label + color, never color alone (✓ verified / ⚠ mismatch / ○ unverified) | WCAG 1.4.1 (apply as general accessibility good practice; not ADHD-sourced) | Pure CSS/HTML entities |
| 5 | **Progressive disclosure of the evidence trail**: derived-evidence detail (which proof records, staleness) collapsed by default via native `<details>/<summary>`, expand on demand | WM capacity + CLT chunking | Native HTML, zero JS |
| 6 | **Render `stale_or_valid` explicitly as elapsed time** ("verified 2h ago" vs. "claimed 14d ago, unconfirmed"), not just a binary badge | Time-blindness / temporal-discounting finding | The field already exists in the schema (`validate_proof_record`'s output) — this is a render-layer addition only |
| 7 | **A mismatch item must render a concrete next action**, not just the contradiction ("claims Done Verified but derived Unverified" → add "next: re-run live smoke" or similar), not merely the warning text already in AC-RENDER | Zeigarnik / open-loop plan-making finding — genuinely new requirement | Requires either a convention for authoring next-actions in status.json, or a generic fallback ("re-verify this claim") |
| 8 | **CLAIMED vs. VERIFIED as the single loudest visual distinction on the page** — sharper contrast between these two than between any other pair of states | Cognitive-offloading/trust finding (the whole dashboard's credibility rests on this) + Linear precedent (refuses auto-complete without confirmation) | Pure CSS, but this is a DESIGN PRIORITY constraint on 1-4, not a separate element |
| 9 | Empty-state and all-frozen-state get an explicit, calm, non-alarming render (not "0 items" as dead space) | Internal-audit gap #4 (currently unspecified) | Pure CSS/HTML |

**Stack verdict (from the UI/UX pass, and consistent with the current build's own
constraints):** native `<details>` + CSS covers ~90% of the value. A small, optional
vanilla-JS sprinkle for a quiet state-flip confirmation is defensible later; a JS framework
is explicitly NOT justified — it fights the calm-minimalism goal and the project's own
stdlib-only convention. **Recommendation: v1 stays 100% static HTML/CSS, zero JS,
consistent with the existing build.**

---

## 4. Open questions this brief does NOT resolve (surface to Nnamdi before spec-writing)

1. **Collapse the evidence/proof trail by default, or show it?** Progressive disclosure
   reduces load, but hiding the proof could undercut trust in "verified" — the whole point
   is that verified means something. Leaning: show a ONE-LINE proof summary always
   (e.g. "✓ verified · live smoke 2h ago"), collapse only the full record detail.
2. **Momentum/reward cues** — explicitly deferred out of v1 per §2 above; revisit only if
   Nnamdi finds the calm version demotivating in practice.
3. **How much accessibility redundancy for an audience of one?** The 8%-CVD-prevalence
   argument is population-level. Cheap to just do it right (icon+text+color) regardless —
   recommend building it in regardless of the answer, since the cost is near-zero.
4. **Where does he actually encounter this dashboard?** (terminal output, a browser tab
   left open, a morning ritual, etc.) — point-of-performance theory says this matters as
   much as the visual design; it's a workflow decision, not a rendering one, and needs
   Nnamdi's input, not research.
5. **Next-action authoring for item #7 above** — does this require a new status.json field
   (a real spec/schema change, bigger scope), or is a generic fallback message acceptable
   for v1? Recommend generic fallback for v1, real field as a fast-follow if it proves
   valuable.

---

## 5. Recommended next step

Spec a **v1 redesign of `render_control_plane`** scoped to table §3 items 1-6, 8-9 (pure
CSS/HTML, no schema changes) as a fast, low-risk loop build. Defer item #7 (next-action
authoring) to a v2 once the schema question in open-question #5 is resolved. Run it through
the standard loop: spec → plan-check Verifier → test-writer → coder → independent Verifier
PASS, per `orchestrator.md`.
