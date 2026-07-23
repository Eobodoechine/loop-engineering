# H-GUARD-6 research dossier — Stop-hook false-positive on doc-only close-out turns
(2026-07-02, two parallel research agents: Claude Code hook mechanics + community prior art. Seeds the eventual H-GUARD-6 mini-spec. Citation fidelity preserved: [fetched] vs [secondary] vs [inference] flags carried through.)

## The problem (restated)
`loop_stop_guard.py`'s FEATURE gate is BLOB-based: it regex-scans the turn's JSON blob for a Write/Edit near a code-extension token. A doc-only close-out turn (edits only `.md` logs whose PROSE names the `.py` files changed earlier) matches → exit 2 false positive. Compounded by cross-turn blindness: the verifier ran, but in a prior turn (async), which a per-turn scan can't see.

## Finding 1 — the fix the whole field uses is candidate (a): path-glob over the real file_path, never content
- **TDD Guard (`nizos/tdd-guard`, MIT)** [fetched: repo + docs/ignore-patterns.md, configuration.md, quick-commands.md, enforcement.md; nizar.se blog] is the closest prior art. It gates PreToolUse on Write/Edit/MultiEdit and classifies doc-vs-code by an `ignorePatterns` glob **allowlist over the tool_use `file_path`** — default list ignores `*.md`, `*.txt`, `*.log`, `*.json`, `*.yml/*.yaml`, `*.xml`, `*.html`, `*.css`, `*.erb`, `*.rst`. It never scans edit CONTENT for filenames. Our exact false positive (a `.md` whose prose names `.py`) is the textbook case where content-regex fails and path-glob succeeds.
- **Gotcha to carry into the spec** [fetched]: TDD Guard docs warn "custom patterns REPLACE the defaults entirely" — an allowlist must be complete, not additive.
- **Mechanics agent** [fetched code.claude.com/docs/en/hooks]: Write/Edit tool_use `input` carries the target in `file_path`; prose can't populate it. Confirms (a) is mechanically sound. Our repo already has `_rh_structural_writes()` (loop_stop_guard.py ~L149-163) enumerating real write paths — the fix is largely REUSE, not net-new.
- **Caveat for the builder** [fetched/flagged]: `MultiEdit` and `NotebookEdit` input schemas differ — NotebookEdit uses `cell_id`, not `file_path`. A structural detector must handle those tool names explicitly or it silently misses them.
- **disler/claude-code-hooks-mastery** and **pascalporedda/awesome-claude-code** [both fetched]: their Stop/SubagentStop hooks are logging/TTS ONLY — no gating pattern. (Corrects the prior assumption they'd hold gate patterns.)

## Finding 2 — candidate (b) is real and sanctioned, with two corrections
- Marker-file-as-cross-turn-state is the sanctioned pattern: official docs' worked example keys a state file by `$HOME/.claude/hooks/state/$session_id.json` and states `session_id` "is unique per session and persists across resume/continue" [fetched docs]. claudefa.st uses `.claude/incomplete-task` + `{"decision":"block","reason":...}` while it exists [fetched].
- **Correction A (contradiction caught vs our own running code):** the mechanics agent claimed SubagentStop does NOT provide `last_assistant_message`. But our `subagent_stop_gate.py` reads exactly that field and it WORKS — this session's PLAN_PASS wrote its flag through it at 00:08 (verified live). So the field IS available in this runtime (under-documented, not absent). Implication: for a `VERDICT: PASS` cross-turn credit we can read `last_assistant_message` DIRECTLY, exactly as the plan-pass path already does — no transcript scraping needed.
- **Correction B (prefer state-invalidation over wall-clock TTL):** prior art [fetched: TDD Guard overwrites `test.json` on next run; no primary source for a wall-clock TTL] favors "marker is stale if a source edit happened AFTER it" (monotonic) over a time TTL. Relevant to our just-shipped H-GUARD-3 plan-pass credit, which uses a 24h wall-clock TTL — works as a safety bound, but a state-based staleness check would be more precise. Not urgent; note for any (b) build.

## Finding 3 — transcript-blob scraping is a KNOWN-brittle anti-pattern
- `anthropics/claude-code#68665` (ralph-loop: Stop hook failed to detect a valid `<promise>` because the transcript window held a control character) [secondary: title/summary via search, issue body not opened]. Direct argument against our current blob-scan and FOR structured signals (path enumeration + marker file). Our FEATURE gate IS the fragile pattern this reports.
- morphllm.com/claude-code-hooks [fetched]: canonical false-positive menu — "gate the block on a REAL condition… return exit 0 once it clears"; termination condition must be "marker-file / bounded-retry / transcript-check" so it "cannot block twice for the same reason." We already have the `stop_hook_active` early-exit (mechanics + claudefa.st [fetched] confirm the idiom).

## Recommended shape for the H-GUARD-6 mini-spec (converged, both agents)
1. **PRIMARY — make FEATURE detection structural (candidate a).** Replace the blob regex with an enumeration of real Write/Edit/MultiEdit/NotebookEdit tool_use targets; classify by `file_path` extension/glob; a doc-only turn (all `.md`) short-circuits to allow. Reuse `_rh_structural_writes()`. This ALONE fixes the reported false positive and retires the #68665-class brittleness. Handle MultiEdit/NotebookEdit field differences explicitly.
2. **OPTIONAL — VERDICT:PASS cross-turn credit (candidate b, refined).** SubagentStop matches a `VERDICT: PASS` final line via `last_assistant_message` (proven field) and writes a `session_id`-keyed marker; the Stop gate honors it. Use STATE-based staleness (invalidate if a source edit lands after the marker) rather than wall-clock TTL. Only needed for the "verifier ran a prior turn" half — (1) already covers the doc-only half.
3. **Keep** the `stop_hook_active` re-entry guard and the "gate on a real condition, exit 0 when clear" invariant (already present).
- **Decision note for the spec:** candidates (a) and (b) are NOT either/or — the field converges on layering (path-glob to decide IF a verifier is needed + session marker that it ran + re-entry guard). But (a) is sufficient for the reported bug; (b) is an enhancement. Failure-direction tradeoff still stands: (a) narrows detection (risk: a real code edit mis-extensioned slips), (b) widens credit (risk: a stale PASS licenses an unverified edit) — the state-staleness refinement mitigates (b)'s risk.

## Honesty flags (unverified / secondary — do not treat as fetched)
- TDD Guard's exact TEST-file path patterns (`.test.`, `/tests/`, `__tests__/`) — search summaries only; approach (path-based) confirmed, literal list not.
- Issues #68665 and #19220 (SubagentStop event-name bug) — titles real via search, bodies not opened.
- Wall-clock TTL as prior art — none found; the fetched idiom is overwrite-on-new-state.
- Ecosystem forks (tdd-guard-rust/pytest, obra/superpowers#384) — named by search, not opened; leads only.
- debugg.ai (404) and claudelog.com (403) — could not fetch; disregarded.

## Sources actually fetched
github.com/nizos/tdd-guard (+ docs/ignore-patterns, configuration, quick-commands, enforcement); nizar.se/tdd-guard-for-claude-code; github.com/disler/claude-code-hooks-mastery (+ stop.py); github.com/pascalporedda/awesome-claude-code; code.claude.com/docs/en/hooks; claudefa.st/blog/tools/hooks/stop-hook-task-enforcement; morphllm.com/claude-code-hooks.
