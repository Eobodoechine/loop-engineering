# Control-Plane Dashboard Redesign Brief

Date: 2026-07-12

Purpose: fuse the existing control-plane dashboard audit, ADHD clinical-foundations
research, ADHD/UI pattern research, built control-plane spec, and build run log into one
design brief that a future Test-writer/Coder can implement through the loop.

This brief is not an implementation claim. It is the design input for a future build.

## Source Pack

Read these before editing dashboard code:

- `research/internal-audit-adhd-control-plane-dashboard-2026-07-12.md`
- `research/deep-research-adhd-dashboard-uiux-patterns-2026-07-12-report.json`
- `research/deep-research-adhd-clinical-foundations-2026-07-12-report.json`
- `research/loop-team-reliability-adhd-dashboard-2026-07-11.md`
- `runs/2026-07-11_control-plane-dashboard/specs/spec.md`
- `runs/2026-07-11_control-plane-dashboard/run_log_build.md`
- `runs/2026-07-11_control-plane-dashboard/browser_proof/README.md`

## North Star

The dashboard answers one question for a tired human managing multiple AI-built products:

> Where am I, what needs my attention next, and is this really verified or only claimed?

The primary product promise is not prettier telemetry. It is a trustworthy external memory
surface for product-building state.

## Non-Negotiable Truth Mechanics

Do not weaken these mechanics in a redesign:

- An authored/product status claim is not proof.
- `wip_column` is authored and validated, but `evidence_label` is derived from proof.
- `Done Verified` plus derived `ready` plus repo-health `CLEAR` is the positive verified
  state.
- `.cp-mismatch` is the loudest warning state: authored status overstates or contradicts
  derived proof.
- `.cp-verified` is the trustworthy success state.
- `.cp-focus` is a single human-attention pointer, not a hard global WIP gate.
- `.cp-demo` means demo-path source, not real product state.
- `.cp-legacy-label` means old-shaped status mapped down with a caveat.
- `FROZEN` comes from live repo-health at render time, not a stale stored status.
- Proof can be disclosed progressively, but proof status must always be visible.

Event buses, waiters, hooks, and notifications may wake agents or carry proof pointers; they
must not become the authority for readiness, PASS, DONE, or verification.

## Evidence Basis

The research converges on five design requirements:

1. **Externalize state at the point of performance.**
   ADHD/executive-function research supports making state, next action, time, and motivation
   visible where work happens. The dashboard should be something the user reads instead of
   something they remember.

2. **Keep working memory load around 3-5 live chunks.**
   The UI should not ask the user to compare many products and proof states in their head.
   It should group, rank, and collapse details while preserving action-critical status.

3. **Trust is part of usability.**
   Cognitive offloading works only when the external store is reliable. Claimed-vs-verified
   separation is therefore not merely a safety feature; it is the condition that lets the
   user trust the dashboard as memory.

4. **Open loops need concrete plans, not bare reminders.**
   Each unresolved product/blocker should have a captured next tiny action. A list of
   unfinished things without a plan can increase rumination.

5. **Calm does not mean vague.**
   Stable verified states should be quiet. Focus, mismatch, blocked, stale, and frozen states
   should be unmistakable. The interface should avoid decorative load while preserving all
   action-relevant signals.

## Page-Level Hierarchy

Render in this order:

1. **Now / Focus strip**
   - One current focus product if present.
   - One next tiny action.
   - Why this is the focus.
   - If no focus is set, say "No focus set" and show the safest command/action to set one.

2. **Risk strip**
   - Count and link to mismatches, frozen products, blocked external setup, stale proofs, and
     unverified claims.
   - This should be the loudest area only when there is real risk.

3. **Product card grid**
   - One card per product.
   - Cards sorted by attention priority:
     1. focused product
     2. mismatch / frozen / blocked
     3. claimed-but-unverified
     4. doing / evidence-needed
     5. verified/stable
     6. demo/legacy

4. **Proof and history disclosure**
   - Proof details live under native `<details>/<summary>`.
   - The summary line must expose proof class and freshness without expansion.

5. **Legend and rules**
   - Include a compact legend explaining claimed, verified, mismatch, frozen, demo, legacy,
     and focus.
   - This is reference material, not first-screen content.

## Product Card Anatomy

Each card should contain exactly these visible zones:

1. **Header**
   - Product name.
   - Focus marker if focused.
   - Primary state badge.
   - Proof/evidence badge.

2. **Truth row**
   - Authored WIP column.
   - Derived evidence label.
   - Repo health.
   - Mismatch indicator if any.

3. **Next action**
   - One tiny action, written as a command or concrete step.
   - If the item is verified and has no required action, show "No action needed".

4. **Progress**
   - Steps done / total if available.
   - Last verified/proof time if available.
   - Stale or missing proof label if relevant.

5. **Proof disclosure**
   - Collapsed by default.
   - Summary text must be meaningful, e.g. "Proof: pytest command, exit 0, fresh" or
     "Proof: missing".
   - Expanded content may show command, proof snapshot, output hash, commit, and relevant
     paths.

## Status Encoding

Never encode status with color alone. Every state must have:

- text label
- icon or shape
- color
- stable CSS class

Suggested state treatments:

- Verified: quiet checkmark, low-saturation green, label `VERIFIED`, class `.cp-verified`.
- Claimed/unverified: hollow check or document icon, amber/neutral, label `CLAIMED`, class
  `.cp-unverified` or existing derived-label class.
- Mismatch: warning triangle, high-contrast border/bar, label `MISMATCH`, class
  `.cp-mismatch`.
- Frozen: stop/lock icon, firm border, label `FROZEN`, repo-health text visible.
- Focus: target/pin marker, clear header bar, label `FOCUS`, class `.cp-focus`.
- Demo: dashed outline or lab marker, label `DEMO`, class `.cp-demo`.
- Legacy: caveat/info marker, label `LEGACY`, class `.cp-legacy-label`.

## Accessibility Requirements

Before any redesign is accepted:

- No state may rely on color alone.
- Text contrast should avoid harsh pure-black-on-pure-white while still meeting accessibility
  contrast needs.
- Cards must be keyboard navigable.
- `<summary>` labels must be descriptive.
- Screen-reader text must include the status label, not only the icon.
- The page must remain usable at narrow widths.
- Text must not overflow cards, badges, or controls.

## Empty, Frozen, And Error States

The current root control-plane render can legitimately show `0 control-plane item(s)`.
That is expected until products emit control-plane-shaped `runs/**/status.json` files.

Design the empty state as an orientation state, not a failure:

- "No control-plane product status files found."
- "The dashboard feature is installed; products have not emitted status yet."
- Show the expected status.json shape or command path in a collapsed setup detail.
- Do not show green success merely because the page rendered.

Frozen state:

- Show why the repo/product is frozen.
- Show what work is allowed: hardening, continuation, or explicit unfreeze path.
- Block or visually de-prioritize new-capability actions.

Error state:

- Show which product/status file failed validation.
- Show the schema error.
- Never silently drop invalid product cards.

## Interaction Rules

Keep the first implementation mostly static/stdlib-compatible:

- Native `<details>/<summary>` for proof details.
- Optional tiny vanilla JS only for quiet local state such as "collapse all", "expand
  mismatches", or "copy command".
- No framework unless a later plan-check proves the static implementation cannot meet the
  interaction requirement.

Do not add confetti, gamification, noisy animations, or alert storms. Small immediate
confirmation is useful; stimulation is not the goal.

## Build-Now Slice

The next implementation should be a narrow render/validator slice:

1. Update control-plane HTML card anatomy and CSS classes in
   `loop-team/harness/product_dashboard.py`.
2. Preserve all existing schema and truth logic.
3. Add tests that assert structure, not substring-only presence:
   - focus strip exists
   - mismatch is before/above stable verified content
   - product card has header/truth row/next action/progress/proof disclosure
   - every state has text plus class/icon marker
   - proof details are collapsed but proof summary remains visible
   - empty state explains no status files vs feature failure
4. Regenerate durable browser proof after implementation.

## Later Slices

Defer these until the first redesign slice is verified:

- UI control for setting focus instead of CLI-only `--focus`.
- Waitbus/event-bus notifications for root unsafe, verifier fail/pass, and repo frozen.
- Live refresh or state-change animation.
- Cross-product timeline/history.
- Personal preference toggles.
- Mobile-specific optimization beyond responsive basics.

## Acceptance Criteria For The Redesign Build

A future Coder is done only when all are true:

1. Existing control-plane tests still pass.
2. New structural render tests pass.
3. Existing proof semantics are unchanged.
4. A real browser proof shows:
   - focused product is visually dominant
   - mismatch is louder than verified
   - verified is visible but quiet
   - proof details can expand
   - empty state is understandable
5. Accessibility tree includes readable labels for focus, mismatch, verified, demo, legacy,
   and frozen.
6. Independent verifier confirms the dashboard did not promote any claimed/unverified item to
   verified.

## Explicit Non-Goals

- Do not redesign the loop process itself in this slice.
- Do not patch hook/guard/credit-gate files as part of this UI work.
- Do not require real product status files to exist before the dashboard can render.
- Do not make the dashboard the authority for truth; it renders truth derived elsewhere.
- Do not collapse `blocked`, `mock-tested`, `build-clean`, `live-smoke-pass`, and `ready`.

## One-Sentence Build Brief

Redesign the control-plane dashboard into a calm, ADHD-friendly external-memory surface that
puts the current focus and next action first, makes mismatch/claimed-vs-verified impossible
to miss, keeps proof visible-but-collapsed, and preserves the existing mechanical truth gates.
