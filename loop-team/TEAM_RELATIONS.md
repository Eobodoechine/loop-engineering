# Loop-Team Member Relations

> **Purpose:** Quick-reference for Oga — look up a situation, find the right dispatch, check preconditions, and verify handoff rules without re-reading every role file.

---

## Quick-reference: situation → team member

| Situation | Who Oga dispatches | What must precede | What must follow |
|-----------|-------------------|-------------------|-----------------|
| **Build (new capability)** step 1 — plan-check | Verifier | Spec + ACs written by Oga | Revised spec (if gaps found) |
| **Build** step 2 — write tests | Test-writer | Finalized spec + ACs | Failing test file(s) |
| **Build** step 3 — implement | Coder | Spec + failing tests | Implementation + Decision Log |
| **Build** step 4–5 — verify loop | Verifier | Implementation (no Decision Log, no green verdict) | PASS/FAIL/FALSE-PASS verdict |
| **Build** step 6 — judgment check | Verifier | Artifact + spec (no prior PASS signal) | Final verdict; if gap → back to Coder |
| **Build** step 6.5 — live smoke | Live-smoke | Green harness result; external-touching artifact | PASS or FAIL with URL/dep/pipeline map |
| **Mode A** — loop improvement | Researcher | Radar file read; current phase/roadmap context | Candidate dossier + PACE-gated experiment spec |
| **Mode B** — stuck Coder (unblock) | Researcher | Stall detector fires; N failure signatures identical; Decision Log | Bug-fix dossier; 1 research-informed Coder attempt |
| **Mode C** — eval hardening | Researcher | Current Verifier prompt; `fix_plan.md`; failure taxonomy sources | Adversarial case batch for Gold Judge to validate |
| **Mode D** — domain research | Researcher | Brief with external-service reference or Coder assumption to ground | Domain brief for Coder; not a radar entry |
| **Gold Judge** — case validation | Gold Judge | Mode C case batch (artifact only, NO Verifier reasoning) | Per-case VERDICT: PASS/FAIL/FALSE-PASS |

---

## Role profiles

### Coder

| Field | Detail |
|-------|--------|
| **Trigger** | Oga dispatches after Test-writer delivers failing tests; or on each retry after Verifier returns FAIL |
| **Receives** | Spec + public interface; failing test file(s); on `modify/fix/continue` tasks: explicit "Files to read" list; on retries: Verifier's failing output |
| **Withheld from it** | The green harness verdict (irrelevant mid-iteration); Verifier's reasoning (not in its role) |
| **Produces** | Implementation files (full or precise diff); one-line change note on retries; **Decision Log** (spec interpretation, assumptions, alternatives rejected, uncertainties) |
| **Model alias** | `sonnet` (default); upgrade to `opus` for complex architecture problems |
| **Hard constraint** | May NOT edit, delete, weaken, or skip a test to make it pass — that is the one unforgivable failure |

---

### Test-writer

| Field | Detail |
|-------|--------|
| **Trigger** | Oga dispatches after plan-check Verifier approves the spec (step 2) |
| **Receives** | Spec + public interface + ACs; brief constraints (language, test framework) |
| **Withheld from it** | Coder's Decision Log (tests must encode spec intent, not implementation assumptions) |
| **Produces** | Test file(s) runnable by a standard runner; happy path + edge cases + failure modes; each test labeled `[DOC]` or `[BEHAVIORAL]` |
| **Model alias** | `sonnet` |
| **Hard constraint** | Must flag un-executable `[BEHAVIORAL]` criteria to Oga rather than silently downgrading to a `[DOC]` grep |

---

### Verifier

| Field | Detail |
|-------|--------|
| **Trigger (plan-check)** | Oga dispatches on the SPEC before step 2 — catches mis-aimed ACs before any code is written |
| **Trigger (code verify)** | Oga dispatches after Coder delivers (steps 5–6); always dispatches fresh, never carrying prior PASS signal |
| **Receives** | Spec + ACs + artifact; access to real input corpus; harness JSON result (weighed AFTER its own independent read) |
| **Withheld from it** | Coder's Decision Log; the green `last verdict` / "tests passed" signal — BOTH withheld until Verifier has committed its own provisional verdict; Oga must not paraphrase, summarize, or hint at either |
| **Produces** | Structured verdict: `verdict` (PASS/FAIL/FALSE-PASS), `spec_conformance`, `goal_achievement`, `recall_note`, `erosion_note` (slop-gate shadow summary, or "not applicable — no code diff"), `caveats` (even on PASS), `harness`, `notes` |
| **Model alias** | `sonnet` for code verify; `sonnet` for plan-check |
| **Independence rule** | Must write its own provisional verdict BEFORE reconciling against harness result — the harness green is evidence it weighs, not a license it starts from |

---

### Researcher

| Field | Detail |
|-------|--------|
| **Trigger — Mode A** | Scheduled scan or Oga calls to find loop-improvement techniques |
| **Trigger — Mode B** | Stall detector fires — same failure signature recurred N times (default 2) |
| **Trigger — Mode C** | Oga calls to harden the eval suite with adversarial cases |
| **Trigger — Mode D** | Brief references external platform/API, or Coder Decision Log has an ungrounded external assumption |
| **Receives — Mode A** | `research/radar.md`; current phase/roadmap context |
| **Receives — Mode B** | Failing test + full traceback; diffs already tried; installed dep versions; **Coder's Decision Log** (only mode where this is shared) |
| **Receives — Mode C** | Current Verifier prompt; `fix_plan.md`; failure taxonomy sources |
| **Receives — Mode D** | Build Brief; specific domain question(s); language/runtime/version constraints |
| **Withheld from it** | Verifier's reasoning (Researcher does not score artifacts); Gold Judge verdicts (Researcher is not a judge) |
| **Produces — Mode A** | Candidate dossier with priority score + PACE-gated experiment spec; radar.md updates |
| **Produces — Mode B** | Bug-fix dossier: `diagnosis`, `candidate_fixes` (1–3, ranked, each sourced), `falsifiable_check`, `if_not_found` |
| **Produces — Mode C** | Adversarial case batch (hard traps + hard goods, balanced); taxonomy gap note |
| **Produces — Mode D** | Domain brief: `question`, `answer`, `source`, `code_pattern`, `constraints`, `not_found` |
| **Model alias** | `sonnet` (Modes A/C/D); `opus` (Mode B — deeper diagnosis for stuck bug) |

---

### Gold Judge

| Field | Detail |
|-------|--------|
| **Trigger** | Oga (or the eval loop) dispatches to validate adversarial cases produced by Researcher Mode C |
| **Receives** | The artifact only — the thing the Verifier judges; its own facts/numbers; no Verifier reasoning, no Researcher rationale, no expected label justification |
| **Withheld from it** | Verifier's reasoning (independence is the entire point); Researcher's proposed gold reasoning (Gold Judge must rule from first principles, not confirm someone else's answer) |
| **Produces** | Exactly one verdict line: `VERDICT: PASS`, `VERDICT: FAIL`, or `VERDICT: FALSE-PASS`, plus one sentence naming the two facts and comparison that settles it |
| **Model alias** | Not specified in role file; Oga should choose a model tier distinct from the Verifier-under-test to avoid self-grading |
| **Scope** | Settles only claims that can be resolved by checking a fact or doing arithmetic — not stylistic or judgment calls |
| **Note** | Role file exists at `roles/gold_judge.md`. Mechanical arithmetic/fact checker only — a "second opinion" for the meta-verification layer |

---

### Live-smoke

| Field | Detail |
|-------|--------|
| **Trigger** | Mandatory at step 6.5 for ANY artifact that references URLs, shell commands, dependencies, or external files |
| **Receives** | Artifact path(s); one-line description of what it does and what it depends on |
| **Withheld from it** | Harness test results (its job is reality, not re-confirming green tests); Decision Log |
| **Produces** | LIVE/DEAD/BOT_WALLED URL map; command/dep execution results; pipeline smoke result; PASS or FAIL verdict |
| **Model alias** | Not specified in role file; dispatched as a sub-agent using `roles/live_smoke.md` |
| **Three passes** | (1) Fast headless URL sweep via `harness/live_smoke.py`; (2) Production-browser recheck for BOT_WALLED; (3) ≥1 real input through full pipeline |
| **Authoritative signal** | DEAD is authoritative from headless; BOT_WALLED must be rechecked in real browser (headless 403 ≠ dead) |
| **Note** | Role file exists at `roles/live_smoke.md`. A green test suite over an artifact that was never actually run is NOT done |

---

## Dependency chains by situation

### Micro-step build loop (code builds) + failure arbiter

Steps 3-5 of the build run as verified micro-steps (see orchestrator.md "The micro-step
build loop"): decompose ≤200-line steps → per step Coder → OGA-run impacted tests
(testmon) in the main transcript → green → checkpoint commit → next step; retry cap 2
per step then Mode B; slop-gate shadow verdict read per checkpoint. Deterministic
enforcement: `hooks/micro_step_gates.py` (armed by `$LOOP_GATE_DIR/<session>_target`,
written at run start, deleted at close). Every red result passes the FAILURE ARBITER
(code-bug / test-bug / spec-gap / harness-fault, evidence quoted) before any re-dispatch;
route by class per orchestrator.md.

### Build (new capability) — full sequence

```
Oga (spec + plan-check dispatch)
  └─► Verifier [plan-check]
        ↓ gaps found → Oga revises spec → re-dispatch Verifier
        ↓ spec approved
  └─► Test-writer
        ↓ failing test file(s)
  └─► Coder
        ↓ implementation + Decision Log
  └─► Verifier [code verify — receives artifact, NOT Decision Log, NOT prior PASS]
        ↓ FAIL → Coder (iteration, up to MAX_ITERS=6)
        ↓ PASS
  └─► [if external-touching] Live-smoke
        ↓ FAIL → back to Coder (step 3)
        ↓ PASS
  └─► Oga writes run log; lessons checkpoint
```

### Plan-check only (step 1 escape: ≤2 DOC-type ACs)

- Oga may self-review the spec instead of dispatching Verifier, but must state that it is doing so and why.
- All other escapes still require Verifier dispatch.

### Mode D — domain research (pre-build or mid-build)

```
Oga identifies external-service reference in Brief (or Coder Decision Log flags ungrounded assumption)
  └─► Researcher [Mode D]
        ↓ domain brief (question / answer / source / code_pattern / constraints / not_found)
  └─► Oga incorporates into spec or hands directly to Coder
        ↓ Coder continues build with grounded domain knowledge
```

### Mode A — loop improvement

```
Oga (scheduled or on-demand)
  └─► Researcher [Mode A]
        ↓ reads research/radar.md first
        ↓ candidate dossier + ranked dive-in queue + PACE-gated experiment spec
  └─► Oga scores/ranks queue; routes top candidate to experiment harness
        ↓ PACE gate passes → adoption (never direct to critical path)
```

### Mode C — eval hardening

```
Oga
  └─► Researcher [Mode C]
        ↓ adversarial case batch (hard traps + hard goods, taxonomy-grounded)
  └─► Gold Judge [per-case, independent — receives artifact ONLY, not Researcher rationale]
        ↓ per-case VERDICT
  └─► Oga: keep only verifier-beating, judge-confirmed, human-spot-checked cases
        ↓ frozen regressions added to eval suite
```

### Live-smoke close (step 6.5)

```
[Green harness result on external-touching artifact]
  └─► Live-smoke [pass 1: headless URL sweep via harness/live_smoke.py]
        ↓ any DEAD → FAIL → back to Coder
        ↓ BOT_WALLED found
  └─► Live-smoke [pass 2: production-browser recheck for every BOT_WALLED]
        ↓ DEAD in real browser → FAIL → back to Coder
        ↓ all URLs confirmed LIVE
  └─► Live-smoke [pass 3: ≥1 real input through full pipeline via production path]
        ↓ broken pipeline → FAIL → back to Coder
        ↓ PASS
  └─► Oga declares done
```

---

## Information-access and withholding rules

| Information | Oga | Coder | Test-writer | Verifier | Researcher (Mode B) | Researcher (other modes) | Gold Judge | Live-smoke |
|-------------|-----|-------|------------|---------|---------------------|--------------------------|-----------|-----------|
| Spec + ACs | ✓ | ✓ | ✓ | ✓ | ✓ (for context) | ✓ | ✗ (artifact only) | ✗ |
| Coder's Decision Log | ✓ (primary diagnosis input) | ✓ (produces it) | ✗ | ✗ WITHHELD — not even paraphrase/hint | ✓ (explicitly shared to find wrong assumptions) | ✗ | ✗ | ✗ |
| Green harness verdict / "tests passed" signal | ✓ | ✗ (not relevant) | ✗ | ✗ WITHHELD until Verifier commits own provisional verdict | ✗ | ✗ | ✗ | ✗ |
| Verifier's reasoning / raw output | ✓ | ✗ | ✗ | N/A (produces it) | ✗ | ✗ | ✗ WITHHELD — Gold Judge must rule from first principles | ✗ |
| Researcher's proposed gold verdict rationale | ✓ | ✗ | ✗ | ✗ | N/A | N/A | ✗ WITHHELD — case artifact only, no answer leakage | ✗ |
| Failing test output (on iterations) | ✓ | ✓ | ✗ | ✓ (harness JSON) | ✓ (full traceback) | ✗ | ✗ | ✗ |
| Diffs already tried (Mode B) | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ |
| Installed dep versions | ✓ | limited | ✗ | ✓ (for reality-check) | ✓ (version-correct research) | ✗ | ✗ | ✗ |
| Stall signature from stall_detector.py | ✓ | ✗ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ |
| Artifact (built output) | ✓ | produces it | ✗ | ✓ | limited (code + traceback) | ✗ | ✓ (only this) | ✓ |
| Real input corpus | ✓ | ✗ | ✗ | ✓ (MUST access for classifier/filter work) | ✗ | ✗ | ✗ | ✓ (≥1 real input) |
| Run log / prior run history | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

**Key withholding rules (verbatim from source files):**

1. **Coder's Decision Log → withheld from Verifier:** "Withholding the document is not enough — do NOT paraphrase, summarize, quote, or hint at the decision log anywhere in the Verifier's handoff." (orchestrator.md)
2. **Green verdict → withheld from Verifier:** "Do NOT lead the Verifier with 'tests passed' / the green `last verdict` — that anchors it toward acceptance." Verifier must commit its OWN provisional verdict first. (orchestrator.md)
3. **Verifier's reasoning → withheld from Gold Judge:** Gold Judge "must never see [Verifier] reasoning — you read only the artifact in front of you and rule on it from first principles." (gold_judge.md)
4. **Decision Log → shared with Researcher Mode B only:** "A recurring bug is frequently a wrong assumption the Coder wrote down plainly. Check its assumptions against reality first." (researcher.md)
5. **Coder's Decision Log → withheld from Test-writer:** "Tests must encode the spec's intent, not a trivial restatement" — reading the Coder's rationale would encode implementation assumptions. (orchestrator.md)

---

## Mode B branch (stuck Coder)

Mode B is a branch off the main build loop, not a parallel path. It fires only when an objective signal (the stall detector) confirms the Coder is grinding, not progressing.

### Stall-detector trigger condition

```
harness/stall_detector.py  →  stuck_from_outputs(outputs)  →  StallVerdict
```

- Normalizes line numbers, paths, and addresses across attempts so the *same* bug reads the same signature regardless of minor variation.
- Reports `stuck` when the last **N attempts** (default 2) share a signature.
- `stuck` is an **objective signal**, not a human judgment call — Oga does not escalate on a hunch; it escalates when the detector fires.

### Branch diagram

```
Main build loop
  │
  ├─ [iteration N: Coder attempt → Verifier FAIL]
  ├─ [iteration N+1: Coder attempt → Verifier FAIL]
  │                   ↓
  │        stall_detector.py fires: stuck = True
  │                   ↓
  │   ┌── MODE B BRANCH ──────────────────────────────────────┐
  │   │                                                        │
  │   │  Oga dispatches Researcher (Mode B, model: opus)       │
  │   │    receives: failing test + full traceback             │
  │   │              diffs already tried + why each failed     │
  │   │              installed dep versions                    │
  │   │              Coder's Decision Log  ← (only Mode B)    │
  │   │              stall signature                           │
  │   │                   ↓                                    │
  │   │  Researcher produces bug-fix dossier:                  │
  │   │    diagnosis / candidate_fixes / falsifiable_check     │
  │   │                   ↓                                    │
  │   │  Oga hands TOP FIX to Coder for ONE attempt            │
  │   │                   ↓                                    │
  │   │  [Verifier re-runs — step 4]                           │
  │   │                   ↓                                    │
  │   │     PASS? ──► rejoin main loop at step 5               │
  │   │     FAIL + same signature still recurs?                │
  │   │              ↓                                         │
  │   │     STOP — escalate to HUMAN                           │
  │   │     (attach: Researcher dossier + all attempts tried)  │
  │   └────────────────────────────────────────────────────────┘
  │
  └─ [main loop continues if Mode B unblocks]
```

### Stop condition for Mode B

- **One** research-informed Coder attempt per escalation.
- If the same signature recurs after applying the Researcher's top fix: **do not loop Mode B again**. Escalate to the human with the dossier and all attempts attached.
- Human starts with full context, not cold.

### Also reconsider the spec (mandatory alongside Mode B)

When stuck, Oga must also ask: is the *test* wrong, or should the task be split? A stuck loop is often a mis-aimed criterion. Re-run the plan-check mental model against the failing criterion — sometimes the fix is in the spec, not the code.
