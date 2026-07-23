# Internal Research Audit — ADHD / "Where am I · is it really fixed?" Control-Plane Dashboard

**Date:** 2026-07-12
**Purpose:** Consolidate every research and planning artifact WE ALREADY HAVE that informed
the control-plane / product-status dashboard in `~/Claude/loop`, before a separate EXTERNAL
UI/UX research pass. All quotes below are read directly from disk (paths cited); nothing is
paraphrased from memory.

---

## 0. Executive summary

The dashboard is a "Where am I · is it really fixed?" visibility surface across Nnamdi's
software products, with a hard, structural distinction between **claimed done** and
**machine-verified done**. It was born on 2026-07-11 from a single `/goal` session that ran
**three parallel Researcher streams** (agent execution-grounding, ADHD/multi-product shipping,
lightweight build-progress dashboard). Those streams produced ONE saved research file, a plan,
an operating standard, two `fix_plan.md` gate-holes, and — after **7 plan-check rounds (V3→V9)** —
a converged, PLAN_PASS spec that has since been **built, verified, and integrated** (56 tests
green, commit `9720c9f`).

The core invariant that every design decision traces back to:

> "**the only reliable verifier reads ground truth the actor cannot author.**"
> — `research/loop-team-reliability-adhd-dashboard-2026-07-11.md:49`

Applied to the dashboard's central promise:

> "the deterministic reality-gate flips `verified`→true. Coder writes only `"claimed"`; only
> the ground-truth hook writes `"verified"`. → the green badge is structurally unfakeable =
> 'verifiably tell if it's really fixed,' solved."
> — same file, lines 111-113 (THE SYNTHESIS, streams 1+3)

---

## 1. The documents that exist, and where each lives (full paths)

| # | Artifact | Path | Role in the dashboard's design |
|---|----------|------|-------------------------------|
| A | **Primary research** — 3-stream commissioned research | `<HOME>/Claude/loop/research/loop-team-reliability-adhd-dashboard-2026-07-11.md` | The single load-bearing research file. Stream 1 = execution-grounding; Stream 2 = ADHD/multi-product; Stream 3 = the dashboard itself. |
| B | **The consuming plan** | `<HOME>/.claude/plans/hashed-cooking-pebble.md` | Turns the research into a 3-track plan (harden / dashboard / ship MVPs). Defines the `status.json` schema + VERIFIED/CLAIMED trust mechanism. |
| C | **The operating standard** (durable synthesis) | `<HOME>/Claude/loop/LOOP_TEAM_STANDARD.md` | Codifies the research into standing rules. §2 = unfakeable verification; §5 = WIP-limit-1-for-the-HUMAN; §7 = ADHD operating rules (Barkley / Extended-Mind / Zeigarnik). |
| D | **The spec** (V9, PLAN_PASS) | `<HOME>/Claude/loop/runs/2026-07-11_control-plane-dashboard/specs/spec.md` | The buildable design. `SPEC_SHA256=1d59c50d…758b0e`. All ACs (AC1-AC10, AC-RENDER, AC-CLOSEOUT). |
| E | **The plan-check log** (rounds 3-9) | `<HOME>/Claude/loop/runs/2026-07-11_control-plane-dashboard/plan_check_log.md` | Why each design decision was made — the adversarial gaps that forced AC6.3, AC7, AC9, AC-RENDER, `.cp-verified`. |
| F | Reconciled gap records (per round) | `…/2026-07-11_control-plane-dashboard/gap_records_reconciled{,_round5,_round6,_round7}.json` | Machine record of merged adversarial-lens findings per round. |
| G | Build run log | `…/2026-07-11_control-plane-dashboard/run_log_build.md` | The build itself (5 micro-steps, verification). |
| H | **fix_plan gate-hole 1** | `<HOME>/Claude/loop/fix_plan.md:9379` `H-PRODUCT-WIP-STATUS-DASHBOARD-1` | The "process-to-mechanism gap" the dashboard closes. CLOSED 2026-07-12. |
| I | **fix_plan gate-hole 2** | `<HOME>/Claude/loop/fix_plan.md:9473` `H-REALITY-GATE-STATUS-WRITER-1` | The reality-gate writer gap. CLOSED 2026-07-12. |
| J | Design lessons (2 entries) | `<HOME>/Claude/loop/loop-team/learnings.md:2360` and `:2429` | The plan-check lessons + the "100%-green suite still missed AC7" lesson. |
| K | Memory record | `<HOME>/.claude/projects/-Users-eobodoechine/memory/project_control_plane_dashboard_spec.md` | Cross-session state: BUILT+INTEGRATED+CLOSED OUT, locked design decisions. |

**Provenance note:** the 3 research streams were "full-text streams saved in this session's
research" (plan, `hashed-cooking-pebble.md:116`), but on disk only artifact **A** survives as a
distinct file. See GAP-6 below.

---

## 2. What each said — key findings, principles, and product decisions

### 2A. Stream 1 — Agent execution-grounding (the "said-it-did-it" gap)
Source: `loop-team-reliability-adhd-dashboard-2026-07-11.md:10-49`

- **Framing number:** "False success — agent asserts completion while environment state
  disagrees — is **75.8% of failures** in self-assessing coding agents" (line 13-14), citing
  *From Confident Closing to Silent Failure*, arXiv 2606.09863. "Reasoning models give NO
  protection."
- **Dual-control suppresses false success ~10×:** single-control (agent acts + judges) =
  45-48% false success; **dual-control (independent party verifies state) = 3%** (lines 18-21).
  "Structural, not smarter prompting. → Verifier must re-derive success from ground truth the
  Coder never touched (git, filesystem, fresh test run), never from the Coder's prose."
- **LLM judges CANNOT catch false success** (no judge > AUROC 0.65; 0.54 on coding); a trivial
  TF-IDF+XGBoost on closing-message vocab hit AUROC 0.825-0.953 (lines 22-25). "Don't add a
  second LLM grader; add a deterministic post-hook."
- Git-diff re-read AFTER the commit lands; exit-code (not narration) gates done; re-run the
  specific failing path; Step-0 task ledger; end-state evaluation with every claim citing
  file:line (lines 26-42).

→ This stream is the source of the **verified-vs-claimed** distinction and the **reality-gate**
as the sole writer of `verified:true`.

### 2B. Stream 2 — ADHD, multiple parallel products, weekend deadline
Source: `loop-team-reliability-adhd-dashboard-2026-07-11.md:53-87`

- **Core diagnosis:** "two forces kill weekend ships — **context-switch cost** (re-load tax per
  jump) and **won't-cut-scope**" (lines 55-57).
- **WIP limit of 1 active product** (highest leverage): "Kanban WIP limits exist to 'reduce
  context switching… a very serious threat to productivity'" (Atlassian, Perforce). "One product
  in 'Doing'; others in 'Parked,' off-limits until Doing is empty." (lines 61-63)
- **Ruthless must-have MVP:** "aim **3-5 must-have stories.** Litmus: 'does this directly enable
  the core action? No → backlog.'" Cut list: social, gamification, reporting, advanced settings,
  personalization, third-party integrations (lines 64-68).
- **Definition of Done written before building** — "antidote to perpetual polish. One `## DONE =
  …` line per product; when true, STOP." (lines 69-70)
- **Parking lot for every shiny tangent** (line 71-72).
- **Adapted timeboxing — 50/10 not stock 25-min Pomodoro** (25-min timer breaks flow for many
  ADHD devs); "End every block with two lines: state-of-work + next-tiny-action (kills
  blank-page restart)." Marked "50/10 UNVERIFIED as clinical, verified as practitioner
  recommendation" (lines 73-76).
- **Externalize working memory into ONE capture inbox / STATUS.md** (BUILT/DOING/BROKEN) —
  "**the 'where am i' surface.**" (lines 77-78) ← the literal origin of the framing.
- Tool tradeoff: "**plain-text markdown `STATUS.md` per repo = primary recommendation** (zero
  context-switch, git-tracked, portable)." (lines 81-82)

→ This stream is the source of **WIP-limit-1**, the **"where am I" framing**, the **≤5
MUST-haves**, the **written-DONE-sentence**, and the **one-tracker-per-repo** shape.

### 2C. Stream 3 — Lightweight build-progress + verification dashboard
Source: `loop-team-reliability-adhd-dashboard-2026-07-11.md:91-113`

- **Recommendation:** "single static `dashboard.html` that `fetch()`es one `status.json` per
  product, served by `python3 -m http.server`. ~4-6 hrs, zero build pipeline." A partial
  `dashboard.py` already exists to build on (lines 93-95).
- **Evidence-linked schema:** each item carries `{title, phase, status, verified, priority,
  problems:[{desc,evidence}], evidence:{commit,test,log}}`; commit hashes → GitHub links; logs
  in `<details>` expanders (lines 99-101).
- **Two badges surface "is it really fixed?":** "green **VERIFIED** only when `verified:true`;
  amber **CLAIMED** when `status:fixed && !verified`." (lines 102-103)
- "One JSON per repo fits 'every repo needs its own tracker'; dashboard rolls them up." (line 104)
- Existing Claude-Code observability repos "observe **sessions/tokens**, NOT product
  build-status — wrong axis, don't adopt wholesale." (lines 105-108)

→ Source of the **card grid**, the **VERIFIED/CLAIMED badges**, the **evidence-linked schema**,
and the **rollup**.

### 2D. The plan (B) — how the research became a build
Source: `~/.claude/plans/hashed-cooking-pebble.md`

- Context (lines 5-11): Nnamdi "builds multiple production tools at once, has ADHD," and
  `/loop-team` "reports work as done/fixed/committed that never actually landed
  ('said-it-did-it')." He wants "(c) give verifiable visibility — a dashboard of what's built,
  what's broken with evidence, and whether a fix is *really* fixed."
- Root cause (lines 22-26): "Work is scattered across ~12 dirs for two products — **no 'where am
  I' surface.** `fix_plan.md` tracks the *team's process gaps*, not *product state*."
- **The `status.json` schema is first defined here** (lines 38-43): `{product, done_sentence,
  items:[{title, phase:"must|doing|built|broken", status:"claimed|fixed", verified:false,
  priority, evidence:{commit,test,log}}]}`.
- **The trust mechanism** (lines 45-47): "a Coder/Oga may only ever write `verified:false` +
  `status:"claimed"`. Only the deterministic reality-gate flips `verified:true`. So the
  dashboard's green badge is **structurally unfakeable** — that is 'verifiably tell if it's
  really fixed,' solved."
- The dashboard card (lines 68-71): "rollup header (`3 building · 1 blocked · 5 verified`),
  commit hashes → GitHub links… **green VERIFIED badge only when `verified:true`, amber CLAIMED
  when `status:fixed && !verified`.** This is the ADHD 'where am I / what's broken / is it really
  fixed' surface for all products at once."

### 2E. The operating standard (C) — ADHD rules made durable
Source: `LOOP_TEAM_STANDARD.md`

- §2 (lines 36-43): "**`reality_gate.py`** is the ONLY writer of `verified:true`… An agent can
  write `"claimed"`; only the gate writes `"verified"`." "**Per-product `status.json`** = the
  single source of truth (BUILT/DOING/BROKEN, evidence-linked). This is the ADHD **'where am I /
  what's broken / is it really fixed'** surface."
- §5 (lines 75-76): "**WIP-limit-1 for the HUMAN** (Nnamdi): the agents parallelize; the
  *dashboard* is your single surface so the ADHD context-switch tax lands on agents, not you.
  **One product in 'Doing' for your attention at a time.**" ← the exact wording AC7 is grounded in.
- §7 ADHD operating rules (lines 87-93), each with a mechanism citation:
  - "**Single source of truth** = the dashboard + per-product `status.json` (Barkley:
    externalize at the point of performance; Extended-Mind: the tracker IS part of your
    cognition — keep it ONE file, low load)."
  - "**≤5 MUST-haves = the whole MVP**; everything else → a `## WON'T (this weekend)` list."
  - "**Written DONE sentence per product**; when true, STOP."
  - "**Parking lot** for every shiny tangent (discharges the Zeigarnik open-loop…)."
  - "**50/10 work blocks**, always leave a 'next tiny action' breadcrumb."
- §3 five reliability principles cite **cross-domain** sources (dual-control/DNA-MMR;
  Swiss-cheese/kinetic-proofreading; Ashby requisite variety; never-events/p53 checkpoints;
  aviation-ASRS blameless postmortem) — lines 45-56.

### 2F. The two fix_plan gate-holes (H, I)

- **`H-PRODUCT-WIP-STATUS-DASHBOARD-1`** (`fix_plan.md:9379`): "**the ADHD/status-dashboard
  research is not yet a mechanical product-control surface in this repo.** The current harness
  dashboard is run telemetry; it is not the proposed per-product build-status dashboard."
  Boundary (line 9392): "WIP limit 1, `PARKING_LOT.md`, per-repo `STATUS.md`, per-product
  `status.json`, and evidence-backed status badges are still research/process guidance." CLOSED
  2026-07-12 — the control-plane dashboard + `derive_evidence_label`/`wip_mismatch` +
  `no-binding-check` writer gate satisfy both halves (56 tests green).
- **`H-REALITY-GATE-STATUS-WRITER-1`** (`fix_plan.md:9473`): "the product `status.json` /
  reality-gate idea from the status-dashboard research has no current loop source
  implementation." CLOSED 2026-07-12 — `reality_gate.py` (455 lines, commit `9680a11`)
  implements `cmd_init_status`/`cmd_check`/`cmd_verify`, rejects commit-only proof via
  `no-binding-check`, downgrades on failed reverify, atomic write (33 tests green).

---

## 3. The rationale locked into the spec, traced to its source

Spec = `runs/2026-07-11_control-plane-dashboard/specs/spec.md` (V9).

**The core invariant** (spec A.2, lines 40-45):
> "**no author-supplied claim of doneness renders as verified unless machine-checkable proof
> backs it — and, symmetrically, no item whose proofs contradict its authored column renders
> without a visible mismatch warning.**" Motivated empirically: the prior demo's "VERIFIED"
> badge cited commit `adb491fe…` "confirmed NOT a real git object… rendered as plain text via
> `_render_commit()` with no SHA validation."
→ Direct descendant of **Stream 1's** "ground truth the actor cannot author" + **Stream 3's**
VERIFIED/CLAIMED badge, hardened by a real observed fabricated-VERIFIED bug.

| Spec element | What it says | Traced to |
|---|---|---|
| **AC6.1 `wip_column`** — the WIP axis | Closed enum `{Ready, Doing, Evidence Needed, Blocked External, Done Verified}`, author-supplied (spec:174-176) | Stream 2 WIP framing + plan's `phase:"must/doing/built/broken"`, elevated to a closed, validated enum |
| **AC6.2 derived `evidence_label`** — the trust axis | DERIVED top-down from valid proofs; no-proof renders `Unverified` (spec:176-177) | Stream 1 dual-control: the trust value is re-derived from ground truth, never authored |
| **AC6.3 consistency check** — verified/mismatch semantics | On genuine contradiction, render `.cp-mismatch` and NEVER render verified/done; per-column table (spec:178-195) | Plan-check **round 4**, state-transition-table lens: `wip_column=Done Verified` was "an unguarded second path to fabricated-VERIFIED" (`plan_check_log.md:107-112`). **GENERALIZED across all 5 columns by Nnamdi's choice** after round 5 found the fix only covered 1 of 5 (`learnings.md:2374-2381`) |
| **AC7 single-focus pointer** | Focus is a single central `<root>/.control-plane-focus` pointer naming AT MOST ONE product; "**Multiple products having `Doing` items simultaneously is NORMAL and valid — never an error**"; zero focus valid; no hard gate (spec:205-219) | `LOOP_TEAM_STANDARD.md §5` "WIP-limit-1 for the HUMAN… one product in Doing for your attention at a time." Round 3 caught that a *hard* WIP gate contradicted §5 and the demo (which already showed 2 products in Doing) — `plan_check_log.md:29-39`. Softened to a human-attention highlight |
| **AC-RENDER "must be seen" bars** | Each of `.cp-demo / .cp-mismatch / .cp-focus / .cp-legacy-label / .cp-verified` MUST be a dedicated element NOT inside collapsed `<details>`, not `display:none`, distinct CSS class, in the header region; tests assert the structural bar, never substring presence (spec:221-235) | Round 4 finding 5: "visible/unmissable" prose is a "subjective/whole-program property a faithful-to-the-letter Coder can satisfy while defeating the intent" (`plan_check_log.md:104-106`). Replaced prose with a mechanical bar |
| **`.cp-verified`** — the POSITIVE success render | Required exactly when `wip_column=Done Verified` AND derived `=ready` AND repo-health `CLEAR` — "the dashboard's primary success render" (spec:231-233) | Round 5 grid walk: "a spec that only ever specifies the NEGATIVE case… can leave the POSITIVE happy path — the whole point — entirely unspecified" (`learnings.md:2383-2388`). Added `.cp-verified` + test 18 |
| **`ready` ladder & label enums** | `evidence_label` closed to 5 values; legacy `fixed/verified/claimed` REJECTED at record level, mapped-down with `.cp-legacy-label` at item level (spec:114-138, 267-271) | Stream 3 badge semantics + round-5 gap 1 ("claimed evidence_label isn't a closed enum") |
| **AC9 FROZEN — single live source of truth** | Repo-health gated by a SINGLE live `repo_health_gate.py <repo-id>` call at render time, NOT a stored snapshot (which can pass freshness checks while semantically stale) (spec:347-363) | Round 6, found by BOTH lenses: "repo-health dual source-of-truth divergence… can flip CLEAR→FROZEN with NO git commit" (`plan_check_log.md:168-172`) |
| **`demo` per-item by `/demo/` path** | Demo-mode defined per-ITEM by source path, evaluated identically in both modes (spec:365-371) | Round 5 gap 3 / `learnings.md:2390-2395`: a per-CLI-mode "demo mode" term would badge real products' existing dashboards as DEMO — a regression. Fixed by a per-item predicate |
| **`blocker_scan` DESCOPED** | Removed from the `ready` requirement; deferred to a follow-up (spec:456-471) | Round 7 scoping decision, Nnamdi's "drive to PASS" default (`plan_check_log.md:192-207`) |

**Convergence:** real-gap-count trajectory R3=5, R4=7, R5=6, R6=2, R7=4, R8=1, **R9=0 →
PLAN_PASS** (`plan_check_log.md:230-239`). The parallel adversarial lenses — "esp. the
state-transition-table lens — drove the hardest catches."

---

## 4. Explicit GAPS — what the existing research did NOT answer (feeds the external UI/UX pass)

The research we have is strong on the **trust model** and the **data/verification mechanics**.
It is thin-to-silent on **visual/interaction design**. Open questions for an external UI/UX
research pass:

1. **Visual layout & information hierarchy.** Stream 3 says "CSS grid of cards" and a rollup
   header string (`3 building · 1 blocked · 5 verified`) — but nothing on card anatomy, what
   goes above the fold, how to rank/sort cards, or how to make the ONE focused product visually
   dominant for an ADHD "where am I" glance. AC-RENDER only specifies *that* bars must be
   visible (structural), never *how they should look* (color, weight, placement beyond "header
   region").

2. **At-a-glance clarity / overwhelm reduction — no measured UX basis.** The ADHD stream (2B)
   argues for reducing overwhelm and "one file, low load," but the guidance is about the
   *tracker file*, not the *rendered dashboard*. No research on color-coding for the 5
   `wip_column` states + 6 evidence labels without visual clutter, progressive disclosure
   depth, or how many products/items fit before the surface itself becomes overwhelming.

3. **The single-focus pointer's UX.** AC7 defines the *mechanism* (one pointer, `.cp-focus`
   bar) but not the *experience*: how a human sets focus (there's a `--focus` CLI flag, no UI),
   what the focused card should surface differently, or whether "next tiny action" breadcrumbs
   (Stream 2B, line 74) should render on the focused card. The 50/10 cadence and breadcrumb idea
   is in the research but has NO home in the dashboard design.

4. **Empty / zero / error states.** Spec handles the empty state mechanically ("0 control-plane
   item(s)", `fix_plan.md:9416`) but there's no design research on what a first-run / no-data /
   all-frozen dashboard should communicate to keep an ADHD user oriented rather than lost.

5. **Refresh / liveness / notification model.** Stream 3 mentions `setInterval` re-poll and a
   deferred SubagentStop auto-emit hook (`LOOP_TEAM_STANDARD.md §8.3`), but nothing on how state
   *changes* should be surfaced (does a card flipping CLAIMED→VERIFIED animate? notify?),
   which is central to the "is it really fixed?" moment of truth.

6. **Provenance gap (not a UX gap, but a research-integrity gap worth flagging):** the operating
   standard cites "**the 5 cross-domain briefs (medicine/biology/safety-science/control-theory/
   ADHD)**" (`LOOP_TEAM_STANDARD.md:121-122`) and §3/§7 quote specific mechanisms (Barkley,
   Extended-Mind, Zeigarnik, Ashby, Swiss-cheese, kinetic proofreading, p53, ASRS) — but a
   disk sweep (`grep -rIl` for Barkley/Zeigarnik/Ashby/kinetic-proofreading/p53/Swiss-cheese)
   finds **NO standalone brief files**; only artifact **A** (the ADHD stream) survives. Four of
   the five cross-domain briefs, and the deeper ADHD clinical sources behind the Barkley/
   Extended-Mind claims, were never saved to disk (violates the "always save research" standing
   rule). If the external UX pass wants to ground overwhelm/working-memory design in the ADHD
   literature, that literature is currently only a citation, not a retrievable source — it
   should be re-gathered.

7. **Accessibility & multi-device.** No research at all on contrast/colorblind-safe encoding of
   the verified/mismatch/demo/legacy states, keyboard nav, or whether this is desktop-only. The
   verified/mismatch semantics lean heavily on green/amber color — untested for accessibility.

---

## Appendix — one-line index of the trust semantics (for the UX designer)

- **Unverified** — item has no valid proof record (derived-absence label; distinct string from
  the `Evidence Needed` WIP column).
- **CLAIMED / claimed** — an agent asserted "fixed"; `verified:false`. Amber. NOT trustworthy.
- **VERIFIED / `.cp-verified`** — the reality-gate confirmed via git+test ground truth
  (`Done Verified` + derived `ready` + repo-health `CLEAR`). Green. The only trustworthy "done".
- **`.cp-mismatch`** — authored column overstates (or contradicts) the derived evidence; render
  a warning, never as done.
- **`.cp-demo`** — item sourced from a `/demo/` path; not a real product state.
- **`.cp-legacy-label`** — an old `fixed/verified/claimed` item mapped down to a real label with
  a caveat.
- **`.cp-focus`** — the single human-attention pointer (WIP-limit-1-for-the-human).
- **FROZEN** — repo-health blocks readiness; determined live per-product at render time.
