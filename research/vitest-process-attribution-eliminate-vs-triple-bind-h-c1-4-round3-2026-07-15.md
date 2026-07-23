# Domain brief — H-C1-4 Round 3: does eliminating attribution beat the (pid,pgid,start_time) patch?

**Mode:** D (domain research for a build). **Requested by:** Oga, to evaluate whether a structurally
simpler design ("gate step 6 on all captures reaching `complete`, then apply the ORIGINAL unmodified
H-C1-3 strict rule, no PID matching at all") beats the plan-check lens's Round-3 proposed patch
(bind the match to `(pid, pgid, start_time)` instead of `(pid, pgid)` alone) for `spec_C1_b2_tests.md`
Revision 4, and what `spec_C2_b2_production.md` should newly adopt.
**Scope:** this repo (padsplit-cockpit migration worktree,
`<HOME>/Claude/loop-worktrees/padsplit-job3-migration-2026-07-14`), plus Linux/Darwin
process-model documentation (man7.org, Darwin `ps(1)`), POSIX `kill(2)` semantics, and Vitest's own
`pool` docs — all opened and quoted below. No sub-agents dispatched; all reads/greps/fetches done
directly, per the Researcher role's leaf-worker requirement.
**Date:** 2026-07-15.

---

## 0. The lens's finding, independently re-verified against the actual spec text (not just trusted)

I read `spec_C1_b2_tests.md` (Revision 3) directly rather than taking the dispatch's paraphrase on
faith. Two passages confirm the flaw is real, not a misreading:

- §E step 2 (lines 590–592): *"Only once the PGID is confirmed clear does that invocation count as
  complete; this baseline capture (step 2) as a whole is not complete until all three of (a)/(b)/(c)
  have independently reached this same complete state."*
- §E step 6 (lines 649–654): *"...if it matches an entry whose capture already reached `complete`
  (§E step 2's terminal-state/PGID-clear discipline), cite that manifest entry ... and do **not**
  treat it as abort-worthy on its own..."*

Given `complete` is defined as "PGID confirmed to have zero live members," a live process later found
at step 6 that matches a `complete` entry's PID/PGID **cannot be the original process** — that
process, by the definition just quoted, has already certifiably exited. It must be a distinct,
later-spawned OS process that was assigned a recycled PID/PGID number. **The lens's finding is
correct, and I confirm it independently from the primary text, not merely by trusting the dispatch's
summary.** The "match → not abort-worthy" branch as literally worded can only ever fire on a
coincidental PID-reuse collision — in the worst case, exactly the foreign-intruder scenario the whole
mechanism exists to catch.

I also confirmed `spec_C2_b2_production.md` (`.../job3_padsplit_migration/spec_C2_b2_production.md`)
has **zero equivalent mechanism at all** — not even the flawed one. Its §E step 6 (lines 533–538) reads:
*"Abort-and-escalate per §C's criterion, before making any edit, if this rescan finds any live process
with `cwd` inside the migration worktree."* No spawn manifest, no `detached`/tracked PID, no
PGID-confirm-clear discipline anywhere in its four-capture structure (§E step 2: collect-only, full
`npm test`, recursion-guard proof, node-syntax/typecheck — grepped and read directly, lines 458–488).
C2 is currently running the pre-H-C1-3-fix strict rule with the exact same own-byproduct risk C1 had
before H-C1-4, and no attribution layer of any kind.

---

## 1. Does "confirmed clear" actually guarantee zero residual processes?

**Answer: No — not unconditionally. There is a real, well-documented OS-level edge case where a
process can survive SIGKILL indefinitely, on both Linux and Darwin, and the current spec text has no
stated give-up condition for it.**

- **Linux `D` state (uninterruptible sleep):** man7.org's `ps(1)` PROCESS STATE CODES section defines
  `D` as *"uninterruptible sleep (usually I/O)."* Corroborating sources (SUSE KB, Baeldung) explain why
  this matters for signal delivery: a process blocked in an uninterruptible kernel wait "cannot be
  killed with SIGKILL or kill -9 ... they typically don't even respond to SIGKILL" until the underlying
  I/O completes, because the kernel cannot safely unwind a syscall mid-flight without risking data
  corruption. `TASK_KILLABLE` is a partial, code-path-specific modern mitigation, not a guarantee.
- **Darwin (macOS) equivalent:** the Darwin `ps(1)` man page (fetched directly,
  `leopard-adc.pepas.com/.../man1/ps.1.html`) defines its own analogous state letter: *"U  Marks a
  process in uninterruptible wait."* This is the same underlying kernel concept as Linux's `D`, under a
  different letter — **confirming the migration worktree's actual host (Darwin) has this same class of
  unkillable-pending-I/O process state**, not just Linux.
- **Zombie/defunct processes still occupy the PID entry.** man7.org's `ps(1)` defines `Z`: *"defunct
  (\"zombie\") process, terminated but not reaped by its parent."* man7.org's `kill(2)` page confirms
  `sig=0` (a pure existence check) *"performs existence and permission checks"* and succeeds against a
  zombie, because — per the same page and corroborating sources — *"an existing process might be a
  zombie ... but has not yet been wait(2)ed for"*: the PID is still allocated, just unreaped. A
  `kill(pid, 0)`-style liveness poll therefore correctly still reports a zombie as "existing." **The
  ambiguity is implementation-dependent, not resolved by the spec text**: the spec never specifies
  *how* "poll for pgid to have zero remaining live members" is implemented. A `kill(pgid, 0)`-based
  poll would correctly keep reporting a zombie grandchild as present (safe, but could stall
  indefinitely waiting for a reap that never happens if the parent already exited). A `ps`-based poll
  that filters out rows in `Z` state (reasoning "it's not really running") would **falsely** report
  the PGID clear while an unreaped entry still exists — this is a real, concrete gap in the *current*
  Revision-3 text, independent of which of the two candidate designs is chosen, because neither design
  changes what "confirmed clear" itself means or how it's implemented.
- **Does `pool: 'threads'` (this repo's actual `vitest.config.ts:88` setting) make this worse via its
  own worker mechanism?** Fetched directly, `vitest.dev/config/pool`: *"Threads pool: Enable
  multi-threading. When using threads you are unable to use process related APIs such as
  `process.chdir()`."* And: *"Forks pool: Similar as `threads` pool but uses `child_process` instead of
  `worker_threads`. Process related APIs ... are available in `forks` pool."* **This confirms `pool:
  'threads'` workers are Node.js `worker_threads` — in-process JS threads, not separate OS processes
  with their own PID.** So Vitest's own worker mechanism, under this repo's actual config, does **not**
  itself spawn a separately-PID'd OS process that could show up as a stray "test-runner process" at
  step 6 — a stuck worker thread manifests as the single **already-tracked** top-level Vitest CLI
  process (the one whose PID/PGID is in the manifest) failing to exit, which the outer `timeout` +
  SIGTERM/SIGKILL sequence already targets directly. **The genuine zombie/D-state risk in this
  codebase comes from a different, real source**: the codebase's own `spawnSync`/`execFileSync`-based
  "spawner" tests (confirmed present: `tests/ai-draft-approve.test.ts`,
  `tests/airbnb-calendar-message-thread.test.ts`, and per `spec_C2_b2_production.md`'s own drafting-time
  recheck, `tests/register-route.test.ts`, `tests/inbox-page-source.test.ts`, and a not-yet-classified
  `execFileSync` call in `tests/trusted-origins.test.ts`) — these genuinely spawn separate OS child
  processes, and it is *those* grandchildren, not Vitest's own thread-pool workers, that could enter a
  D/U-state (e.g., blocked writing a large stdout buffer to a slow-draining log redirect) or leave a
  zombie entry if reaping is mishandled.
- **Practical consequence:** SIGTERM has the identical limitation as SIGKILL here — per the same D/U-state
  semantics, a process blocked in an uninterruptible kernel wait does not act on *any* signal, including
  the `timeout` option's default `killSignal: 'SIGTERM'`, until it returns from the syscall. **This means
  neither candidate design (eliminate-attribution, nor the triple-bind patch) can force a genuinely
  I/O-blocked grandchild to actually terminate** — both are downstream of the same shared "confirmed
  clear" building block, and neither one fixes its lack of a stated give-up threshold. As currently
  worded, §E step 2's poll/kill sequence (10s poll → SIGTERM → 2s grace → SIGKILL → re-poll, "only once
  confirmed clear does it count as complete") has **no final bound** — if the SIGKILL'd process is D/U-state
  and never exits, "complete" as currently defined can never become true, which stalls the whole job
  exactly the way Candidate 1 stalled on a genuine Vitest hang (the exact prior gap Candidate 3 was
  adopted specifically to close).

**Source:** man7.org `ps(1)` and `kill(2)` (fetched directly, quoted above); Darwin `ps(1)` man page
(fetched directly via `leopard-adc.pepas.com`, quoted above); SUSE KB 000016919 and Baeldung
"What Is an Uninterruptible Process in Linux?" (WebSearch-corroborated, general/non-controversial OS
behavior, not vendor-specific claims); `vitest.dev/config/pool` (fetched directly, quoted above).

---

## 2. Is the "capture N completes / capture N+1 (or a foreign process) spawns microseconds later" race a differentiator between the two designs?

**Answer: No — it is orthogonal to both, and in this specific spec it barely applies at all, for a
reason grounded directly in the spec's own step ordering, not just abstract reasoning.**

Re-reading `spec_C1_b2_tests.md`'s §E step sequence: step 2 (baseline captures, all three sub-invocations
reach `complete`) → step 3 (preimage hash/archive) → step 4 (diff/classify) → step 5 (hard-stop check) →
**step 6 (the rescan + edits)** → step 7 (post-merge rehash) → **step 8** (post-merge captures). **Step 6
sits in a quiet window with no in-flight capture at all**: step 2's captures have already reached
`complete` well before step 6 runs (steps 3/4/5 intervene), and step 8's captures haven't started yet.
So the specific race framed in the task — "capture N+1 spawning inside the worktree microseconds after
capture N's confirmed-clear check passes" — **does not actually occur at step 6's rescan point in this
spec's own design**, because there is no capture N+1 scheduled to start anywhere near step 6.

The race that *can* occur is narrower: the gap between "the last of step 2's three captures is confirmed
`complete`" and "the step-6 rescan actually samples the process table" (essentially the time to write
the final manifest entry plus dispatch the rescan command — a small, bounded window, not the much larger
step-2-to-step-6 gap). Could a **genuinely new, unrelated** process spawn in that narrow window? Yes,
always possible on a shared filesystem/OS — but:

- Under **design (a)** (eliminate-attribution): any such process is live and unattributed by construction
  (it was never in the manifest at all) → automatic abort. Correct behavior — a genuinely new process at
  that moment is exactly the case the strict rule exists to catch.
- Under **design (b)** (triple-bind patch): the same new process was never spawned via this spec's own
  tracked-spawn wrapper, so it has no manifest entry to match by PID+PGID+start_time at all → also
  automatic abort. **Identical outcome.**

Both designs treat a genuinely new process identically (abort), because neither design's match logic can
match against something that was never tracked in the manifest to begin with. **This confirms the task's
own hypothesis: the race is orthogonal to the choice between (a) and (b) — it is not a point of
differentiation.** The only way this race could differentiate is if the "new" process is actually one of
*this spec's own* not-yet-`complete` invocations racing ahead of schedule (e.g., an implementation bug
where step 8 starts before step 6 finishes) — but such a process, being mid-flight, is by definition not
yet `complete` in the manifest, so it fails to match under **either** design's "match only against
`complete` entries" rule, and both correctly abort on it. If anything, this is a point in favor of design
(a): it has no leniency mechanism that could ever accidentally paper over such a sequencing bug, whereas
any positive-attribution scheme always carries a residual risk that a match-condition edge case gets
implemented slightly too permissively.

**Source:** direct read of `spec_C1_b2_tests.md` §E steps 2–9 (line-cited above); reasoning grounded in
the spec's own documented step ordering, not external documentation (no citation needed beyond the spec
itself for this question).

---

## 3. Explicit comparison: (a) eliminate-attribution vs. (b) the (pid,pgid,start_time) triple-bind patch

| Dimension | (a) Eliminate-attribution: gate step 6 on all captures reaching a terminal state, then apply the unmodified H-C1-3 rule unconditionally | (b) Lens's patch: bind the match to `(pid, pgid, start_time)` |
|---|---|---|
| **PID-reuse collision risk** | **Zero.** There is nothing to match, so a coincidental PID/PGID-reuse collision cannot be misread as "ours." | **Non-zero, reduced but not eliminated.** `start_time` makes a false match far less likely (the kernel/OS assigns a fresh start time to the new process), but does not make it structurally impossible — it is still a probabilistic defense, not a proof. |
| **Correctness given a fully-reliable "confirmed clear"** | **Correct by construction.** If `complete` truly means zero live members (the common, expected case per Q1), a live process at step 6 can never legitimately be "ours" — the unconditional strict rule is exactly right with nothing to filter. | **Solves a problem that (by the stated definition) cannot occur.** Applying triple-bind matching to entries that are `complete` (zero-live-members-confirmed) is matching against a set that should never have a live counterpart at all — the patch's own precondition (a live match) contradicts the definition it's matching against, same logical flaw the plan-check lens found in the original (pid,pgid)-only patch, just less likely to misfire. |
| **Dependency on an OS-specific command** | **None.** No re-query of process start time needed. | **Yes — depends on `ps -o lstart=` (Darwin/Linux) or an equivalent**, which the prior brief (`vitest-process-teardown-attribution-h-c1-4-2026-07-15.md` §4, §7) already flagged as `not_found`/unverified for an exact Node-docs citation, and whose output format is not guaranteed portable across `ps` implementations (BSD/Darwin vs. GNU) without a dedicated parse-and-tolerance layer. |
| **Implementation complexity** | **Lower.** One boolean gate ("have all manifest entries for the preceding step reached a terminal state?") plus the pre-existing unmodified strict rule. | **Higher.** Requires live re-querying process start time at rescan time, a comparison-tolerance window, and correct cross-platform parsing — genuinely new mechanism, not reused from anywhere in this codebase. |
| **Failure mode under Q1's D/U-state edge case** | The gate never opens if a capture's poll/kill sequence never reaches a clean zero (mirrors Candidate 1's original genuine-hang blind spot) — **unless** the spec is also fixed to add a bounded give-up (see §4 below), which both designs need regardless of which is chosen. | Same underlying "confirmed clear may never converge" gap exists identically — the patch doesn't touch the poll/kill mechanism, only the downstream matching logic. |
| **Does it need a residual/fallback layer at all?** | Not for the common (`complete_clean`) case. **Does need a scoped fallback** for the small-probability case where a capture's kill sequence exhausts its bound with a known D/U-state or unreaped-zombie residual still present (Q1) — see §4. | Effectively already answers that fallback need for the one case where it's legitimate — but is currently mis-scoped to run against *every* `complete` entry, including the common case where it can never legitimately fire. |

### Is (b) ever still necessary if (a) is adopted?

**Yes — but only as a narrowly-scoped fallback, not as the general mechanism, and only because Q1
shows "confirmed clear" cannot be made unconditionally reliable.** If the spec is revised to allow a
capture to reach a **second, explicitly different** terminal state — `complete_with_residual` (the
poll/kill sequence exhausted its bound and a specific PID/PGID/state is still logged as present,
because it is genuinely stuck in a D/U-state or is an unreaped zombie, per Q1) — then, and only for
entries in *that* state, a live process found later legitimately *could* be the same still-alive
original instance. In that narrow case, re-querying `start_time` to confirm identity before treating it
as non-abort-worthy is exactly the right, proportionate check — because for a `complete_with_residual`
entry (unlike a `complete_clean` one) a live same-instance match is a real possibility, not a
contradiction of the entry's own definition. **This is the one scenario where the lens's patch earns
its keep**: not as competition with design (a), but as design (a)'s own necessary complement for the
one edge case eliminate-attribution alone cannot resolve (because eliminate-attribution's core premise —
"nothing of ours should still be alive by the time we check" — is exactly what breaks down in that edge
case).

---

## 4. Recommendation

### For `spec_C1_b2_tests.md` Revision 4

1. **Split the single `complete` state into two explicit terminal states** in §E steps 2 and 8 (and the
   spawn-manifest schema, §I item 8):
   - `complete_clean` — the PGID poll/kill sequence (SIGTERM → 2s grace → SIGKILL → re-poll within the
     `teardownTimeout`-sized window) confirmed **zero** live members. This is the expected, overwhelming
     majority case.
   - `complete_with_residual` — after the same sequence, a **bounded** number of additional re-poll
     attempts (state a concrete count/window, e.g. 3 attempts over 30s, so this doesn't loop forever)
     still find a live member. Log its PID, the OS-reported process state code if obtainable (Linux `D`
     / Darwin `U` / `Z`, per Q1), and mark the manifest entry `complete_with_residual` rather than
     blocking indefinitely — this closes the currently-unstated "what if SIGKILL never actually clears
     it" gap Q1 found, independent of which downstream design is chosen.
2. **Replace the (pid,pgid)-only match at §C/§E step 6 with design (a) as the PRIMARY mechanism**: gate
   step 6 on every one of the preceding captures' manifest entries having reached **any** terminal state
   (`complete_clean` or `complete_with_residual`), then apply the **original, unmodified** H-C1-3 rule —
   any live worktree-`cwd` process is automatic abort-and-escalate, **no exceptions, no PID matching** —
   for the general case. This is simpler, has zero PID-reuse collision risk, and needs no `ps -o lstart=`
   dependency for the common path.
3. **Apply design (b)'s triple-bind matching ONLY as a narrow fallback**, scoped exclusively to entries
   already flagged `complete_with_residual`: if step 6 finds a live worktree-`cwd` process, first check
   whether it matches a `complete_with_residual` entry by `(pid, pgid, start_time)` (re-querying
   `start_time` live via `ps -o lstart=` or the OS-appropriate equivalent) — a match is logged as a
   still-draining known residual (non-abort-worthy, but flagged in the implementation log for human
   follow-up, since a lingering D/U-state process is itself worth investigating separately); a
   non-match, or any live process not matching a `complete_with_residual` entry at all (including any
   process found against a `complete_clean` entry, which per §3's logic should structurally never
   happen and is itself worth flagging as a spec-conformance anomaly), is unattributed and triggers
   automatic abort-and-escalate exactly as strict as H-C1-3 established.
4. **Verify `ps -o lstart=`'s actual output format on the real migration-worktree host** before relying
   on it in the fallback branch — the prior brief flagged this as unconfirmed for an exact Node-docs
   citation; confirming it live is now lower-stakes since it only gates the rare residual path, not
   every rescan.
5. **Update AC-14/AC-15** to reflect the two-terminal-state model: AC-14 should require every manifest
   entry to resolve to exactly one of `complete_clean`/`complete_with_residual` (never left ambiguous),
   and AC-15 should require the step-6 rescan log to cite, per worktree-`cwd` process found, one of:
   (a) automatic-abort under the unconditional rule (no manifest entry involved at all), (b) a
   `complete_with_residual` triple-bind match (with the queried `start_time` recorded), or (c) an
   unattributed-abort flag — and should treat a logged match against a `complete_clean` entry as a FAIL
   in its own right (a structural impossibility if the mechanism is implemented correctly).

### For `spec_C2_b2_production.md` (new adoption — currently zero protection of any kind)

C2's four captures (`step2_baseline_collect_only`, `step2_baseline_full_execution`,
`step2_baseline_recursion_guard_check`, `step2_baseline_node_syntax_typecheck`, and their step-8
post-merge counterparts) are currently invoked with no tracked spawn, no manifest, no PGID-confirm-clear
discipline at all — and its step-6 rescan (line 538) is the **plain, unmodified strict rule with no
attribution layer whatsoever**, meaning C2 today carries the exact same "own byproduct vs. foreign
intruder" ambiguity H-C1-4 found in C1, entirely unaddressed. Recommend:
- Adopt the **same Revision-4 design being recommended for C1** (tracked `spawn`/`detached`/bounded
  `timeout` per invocation, spawn manifest, two-terminal-state `complete_clean`/`complete_with_residual`
  model, gate-then-unconditional-abort as primary, triple-bind fallback scoped to residual entries only)
  as new required mechanism in C2's §E steps 2/6/8 and §I — not the flawed (pid,pgid)-only design C1's
  Revision 3 briefly carried, since there is no reason to introduce a design already independently proven
  broken.
- This is a **larger structural delta for C2 than for C1** (C2 has nothing to patch — it needs the whole
  mechanism built from scratch, including its own spawn-manifest file, e.g.
  `.../job3_padsplit_migration/preimage/b2_prod_spawn_manifest.json`, mirroring C1's naming convention),
  and should be raised as **C2's own new plan-check finding** (its own `H-C2-*` ID) in a dedicated
  plan-check round for `spec_C2_b2_production.md`, rather than silently folded into C1's revision
  history — the two specs are separate documents with separate plan-check tracks, and C2's own
  Concurrency & Isolation Safety lens should independently confirm the adopted mechanism, not inherit
  C1's fix by reference alone.

---

## 5. `not_found` / honesty flags (explicit)

- **Not independently verified this session:** `ps -o lstart=`'s actual output format/behavior on the
  real migration-worktree host — the prior brief (2026-07-15) already flagged this as checked only on
  the researcher's own current-session Darwin host, not the literal worktree host, and I did not
  re-check it this session either. This matters only for the narrow `complete_with_residual` fallback
  branch recommended above (§4 point 4), not for the primary eliminate-attribution mechanism, which has
  no dependency on this command at all.
- **Not found / not independently confirmed:** a Vitest-specific GitHub issue reporting the exact
  compound scenario ("a `pool:'threads'` config's own `spawnSync`-spawned grandchild entered a D/U-state
  or was left as an unreaped zombie during teardown"). My Q1 answer composes three independently-real,
  separately-sourced facts (Linux/Darwin uninterruptible-wait semantics; zombie/kill(2) semantics;
  Vitest's own `pool` documentation distinguishing `threads`=worker_threads from `forks`=child_process)
  into a reasoned conclusion about this codebase's specific risk surface — it is not a single citation
  of an issue reporting this exact combination happening in production. Flagging per the honesty bar:
  treat the *general* OS/runtime facts as fully sourced (quoted above, real docs), and the *application*
  of them to this codebase's spawner-test grandchildren as my own grounded inference, not a citation.
- **Not re-fetched this session** (relied on the prior brief's direct quote instead, since it already
  opened these pages): `vitest.dev/config/teardowntimeout` (default 10000ms) and
  `vitest.dev/guide/common-errors#failed-to-terminate-worker`. I did independently re-fetch
  `vitest.dev/config/pool` this session (quoted fresh above) since it was the one directly load-bearing
  for the new Q1 sub-question about thread-vs-fork OS-process semantics that the prior brief did not
  address.
- **Not checked:** whether this exact repo's actual `spawnSync` calls in the "spawner" tests set
  `stdio`/buffer options in a way that would make a slow-draining stdout pipe a realistic D/U-state
  trigger in practice (vs. a theoretical possibility) — I did not re-read those test files' exact
  `spawnSync` option objects this session (the prior brief already quoted the `timeout` values from two
  of them; I did not go further into their I/O configuration). This would sharpen the probability
  estimate for how often `complete_with_residual` should actually be expected to fire, but does not
  change the structural recommendation above, which holds regardless of the exact probability.

---

## 6. Transfer-condition-style note on what each mechanism's guarantee actually requires

| Mechanism | Requires | Structural or instructional enforcement? |
|---|---|---|
| Design (a)'s unconditional strict rule | Only that "terminal state reached" is itself correctly gated before the rescan runs — a boolean the Verifier can mechanically check against the manifest's own recorded states. | **Structural** — the manifest either shows every relevant entry terminal or it doesn't; nothing about the match logic is left to a participant's judgment. |
| Design (b)'s triple-bind fallback (as scoped in §4, residual-only) | A live re-query of `start_time` at rescan time, correctly parsed and compared with a stated tolerance — the one piece of this whole mechanism that is not a fixed, pre-documented constant. | **Partially instructional** — sizing the tolerance window and correctly parsing `ps -o lstart=`'s (or the OS-equivalent's) output format is a judgment call a Coder must get right; the Verifier can confirm a tolerance value was chosen and logged, but not that it was the objectively "correct" one, same caveat the prior brief already flagged for Candidate 3's timeout sizing. |
| The `complete_with_residual` give-up bound (new, recommended here) | A concrete retry-count/window the Coder must choose and log (there is no OS-documented "correct" value for this, unlike `teardownTimeout`). | **Instructional or one-time judgment call** — same category as the existing timeout-sizing residual the prior brief already flagged; the Verifier can confirm a bound was chosen, logged, and applied consistently, not that the specific number is optimal. |

No part of either design has a **silent** compliance-failure mode (the guardrail's specific concern) —
every state (`complete_clean`, `complete_with_residual`, matched/unmatched) is a logged, independently
Verifier-checkable artifact under both designs, consistent with how this spec already treats its other
durable records.

---

**Saved to:** `<HOME>/Claude/loop/research/vitest-process-attribution-eliminate-vs-triple-bind-h-c1-4-round3-2026-07-15.md`
