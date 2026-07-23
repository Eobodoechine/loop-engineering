# Gmail/OAuth Connector: Codex ("Side A") vs Claude loop-team ("Side B") — Comparison Dossier

Date: 2026-07-10
Researcher mode: D (comparative investigation, per dispatch_check)
Author: Researcher sub-agent (Oga-dispatched)

Scope note: this is a **comparison**, not a verification against a single spec. No
decision is made here — Nnamdi makes the keep/merge call, relayed through Oga. All
file reads were read-only; nothing was edited/staged/committed in either worktree.
`npm install` was run in Side B's worktree (`taxahead-gmail-planrevision-b`) only to
satisfy `deno test`'s `@types/node` resolution requirement — this only populated
`node_modules/` (gitignored dependency install), it did not touch source/config files.

## Locations

- Side A ("Codex"): `<HOME>/.codex/worktrees/af44/taxahead-connector-platform`, branch `feature/connector-gmail`, HEAD `3bfca59` (uncommitted working tree on top).
- Side B ("Claude loop-team"): `<HOME>/Claude/Projects/taxahead-gmail-planrevision-b`, branch `feature/connector-gmail-planrevision-b`, HEAD `5cddbce`.

## IMPORTANT: the dispatch brief is stale on Side A's current state

The dispatch brief described Side A as blocked at "Iteration 15" with **no** smoke
harness at all (no `smoke/` dir, no `connector-smoke-manifest.json`). That was true at
the time the brief was written, but Side A's worktree has continued substantially
since — its own `run_log.md` is now 1628 lines (vs. the ~700 the brief's Iteration-15
snapshot implies) and `git status --short` shows a self-built `smoke/` directory now
exists: `smoke/connector-smoke.ts`, `smoke/connector-smoke-manifest.json`,
`smoke/connector-smoke.test.ts`, `smoke/bootstrap-supabase-smoke.mjs`,
`smoke/gmail-live-runner.test.ts`, `smoke/auth-handoff.test.ts`,
`smoke/google-oauth-handoff.ts`, plus `src/routes/auth.google.callback.tsx`. Per Side
A's own run_log tail (lines ~1250-1628), Side A's own suite (`supabase/` + `smoke/`)
is now **197/197 passing** and Side A produced a
`foundation-live-proof-schema-change-request.md` naming two still-missing shared
tables (`smoke_auth_handoffs`, `smoke_cleanup_audit`) it needs from a foundation
panel. Side A's final state is still `blocked_external_setup` (real Gmail live smoke
was never run), but it is **materially further along** on the smoke-harness front
than the dispatch brief assumed. This is reported as fact, independently reproduced
below (I re-ran the 197/197 suite myself), not merely relayed from Side A's own log.

---

## 1. Architectural comparison: CAS/concurrency-guard mechanism

**Side B has it. Side A does not have it, or any equivalent, at all.**

### Side B's mechanism (verified by direct code read)

- `supabase/migrations/0011_connector_generation_guards.sql`: adds
  `sources.connector_generation integer not null default 0`; adds
  `source_sync_jobs.source_generation`; adds a **partial unique index**
  `source_sync_jobs_one_running_per_source_idx on source_sync_jobs (source_id) where
  status = 'running'` (at-most-one-running-job-per-source, enforced at the DB level);
  includes a pre-index remediation UPDATE to clear pre-existing duplicate "running"
  rows before the index can even be created.
- `supabase/functions/_shared/sync-jobs.ts:9-77` (`startSyncJob`): reaps any
  `running` job older than 15 minutes (`REAP_STALE_AFTER_MS`) before checking for an
  existing running job; maps a true unique-index race (Postgres `23505`) to the same
  `sync_already_running` the SELECT-based check produces (lines 39-46, 67-76).
- `supabase/functions/_shared/sync-jobs.ts:80-122`: `finishSyncJobSuccess`/
  `finishSyncJobFailure` are both CAS-guarded on `.eq("status","running")`;
  `finishSyncJobSuccess` checks the match count and throws `sync_job_finish_stale` on
  a zero-row match (line 98-99), `finishSyncJobFailure` deliberately does NOT (an
  intentional asymmetry, commented at lines 114-121).
- `supabase/functions/sync-source/index.ts:44-91`: `isSourceGenerationCurrent()`
  (read-only checkpoint) and `updateSourceIfCurrent()` (the shared CAS write helper,
  `.eq("connector_generation", sourceGeneration).neq("status","disconnected")`) are
  used at **all 5** `sources`-table write sites in the handler (lines 188, 198, 267,
  350, 410), plus 3 read-checkpoints (Checkpoint A at line 250, pre/post-refresh at
  lines 274, 284).
- `supabase/functions/disconnect-source/index.ts:82-100`: monotonically bumps
  `connector_generation + 1`, CAS-guarded on the previously-read value.
- `supabase/functions/start-connection/index.ts:62-94`: an optional `source_id` in
  the request body triggers a reconnect-mode lookup that snapshots
  `connector_generation`/`status` into `oauth_connection_states` (`mode: "reconnect"`,
  `source_generation`, `source_status` — new columns from migration 0011).
- `supabase/functions/complete-oauth-connection/index.ts:106-224`: branches on
  `oauthState.mode === "reconnect"` — the reconnect branch UPDATEs the existing
  source under `.eq("connector_generation", oauthState.source_generation)
  .neq("status","disconnected")` (never inserts a duplicate); a disconnect racing
  the reconnect makes the CAS miss zero rows → `source_reconnect_stale` (409).
  `storeCredentialGuarded()` (one shared call site, line 182) is generation-aware.
- Race classes this closes (concrete, not abstract): disconnect-resurrection (an
  in-flight sync writing `status:"connected"` after the user disconnects),
  credential-resurrection (a slow token-refresh re-storing a Vault secret for a
  disconnected source), duplicate-running-job / doubled Gmail history reads from two
  concurrent `sync-source` calls, and a wedged-forever `running` job row from a
  crashed invocation.
- Provenance: this mechanism was NOT invented from scratch for Gmail — per
  `loop-team/runs/2026-07-09-gmail-connector/plan_check_log.md:243-292`, an earlier
  hand-rolled `acquire_sync_guard` RPC accumulated real defects over several
  plan-check rounds (no tenant-ownership check on the RPC, an overload-resolution
  ambiguity that risked breaking credential storage for 9 sibling worktrees sharing
  the same `store_source_credential` function, a "two truths at once" bug, a
  deploy-ordering fix that was itself worse than the race it targeted) before being
  **deleted entirely** in spec v4 in favor of porting an already-shipped mechanism
  from a sibling worktree, `feature/connector-google-drive`
  (`0010_connector_generation_guards.sql`), confirmed via a dedicated Researcher
  Mode-D dispatch (`~/Claude/loop/research/gmail-connector-sync-guard-prior-art-2026-07-09.md`,
  referenced at plan_check_log.md:261).

### Side A: confirmed absent (grep + direct read, not inferred)

- `grep -rn "connector_generation\|generation" supabase/functions/_shared/*.ts` →
  zero hits. `grep -rln "connector_generation" supabase/` → zero files.
- `supabase/migrations/0005_connector_platform.sql`, `0006_oauth_connection_states.sql`,
  `0009_secret_vault_rpc.sql` (Side A's full migration set) — no generation/version/
  lease/etag column of any kind on `sources`, `source_sync_jobs`, or
  `oauth_connection_states`.
- `supabase/functions/_shared/sync-jobs.ts` (Side A): `startSyncJob` is a bare
  `.insert()` with **no** running-job check, no unique index, no reaper.
  `finishSyncJobSuccess`/`finishSyncJobFailure` are bare `.update(...).eq("id",
  jobId)` — no status precondition at all.
- `supabase/functions/sync-source/index.ts` (Side A): every `sources` write (lines
  180-186, 198-205, 240-245, 336-344, 363-366) is a plain `.update(...).eq("id",
  source.id)` — no generation, no status-precondition, no read-then-compare anywhere.
- `supabase/functions/disconnect-source/index.ts` (Side A, lines 69-81): same —
  plain unconditional update.
- **Conclusion: Side A is exposed to every one of the race classes Side B's
  mechanism was built to close** — disconnect-resurrection, credential-resurrection,
  duplicate-running-jobs, and a wedged-forever job row on crash — with no mitigation
  of any kind, under a different name or otherwise. This is not a naming difference;
  the concept does not exist in Side A's implementation.
- Side A has a *different* real gap that stems from the same missing "generation"
  concept: it has **no reconnect mode at all** (see §2, `complete-oauth-connection`
  and `start-connection`) — every OAuth completion in Side A unconditionally
  `.insert()`s a brand-new `sources` row (`complete-oauth-connection/index.ts:129-149`,
  `start-connection/index.ts:198-217`), so re-authenticating a disconnected/errored
  Gmail source would create a **duplicate source row** rather than safely reactivate
  the old one. Confirmed via `grep -rln "reconnect" supabase/functions/` — Side A
  only maps failures TO a `reconnect_required` status/error string; it never
  implements the other half (an actual reconnect flow).

---

## 2. Feature/fix delta per shared function (file:line cited both directions)

### `complete-oauth-connection`

| | Side A has | Side B has |
|---|---|---|
| Error sanitization | `redactSecretText()` on every `detail:` — 5 sites: `index.ts:56,155,179,193` | Partial: `classifyProviderError()` on exchange-failure (`index.ts:97`) and rollback (`index.ts:223`), but **raw `.message` leaks** at `index.ts:46` (`stateErr.message`) and `index.ts:166` (`sourceErr?.message`) |
| Reconnect | **None** — always `.insert()`s a new source (`index.ts:129-149`) | Full reconnect branch (`index.ts:106-173`): CAS-guarded UPDATE of the existing source under `.eq("connector_generation", oauthState.source_generation).neq("status","disconnected")`; `source_reconnect_stale` (409) on CAS miss |
| Credential store | Plain `storeCredential()` (`index.ts:162`), unguarded; best-effort delete-rollback only | `storeCredentialGuarded()` (`index.ts:182-187`) — ONE shared call site for both branches, generation-aware, discriminates `stale_source_generation` races from genuine failures before either branch's rollback runs |

### `disconnect-source`

| | Side A has | Side B has |
|---|---|---|
| CAS bump | **None** — plain unconditional update (`index.ts:69-81`) | `connector_generation + 1`, CAS-guarded on the previously-read value (`index.ts:82-100`); a genuine lookup DB error is a hard 500, never silently skipped (`index.ts:29-38` comment explains why) |
| Error sanitization | `redactSecretText()` on update-failure detail (`index.ts:86`) and both delete_source_credential console.error logs (`index.ts:100,106`) | **Zero** redaction calls anywhere in this file — raw `.message` at `index.ts:45,102,111,114` (confirmed via `grep -c redactSecretText... = 0`) |

### `list-sources`

This is Side B's single most concrete, unambiguous gap.

- Side A's `list-sources/index.ts:52`: `sources: (sources ?? []).map(sanitizeSourceForResponse)` — redacts `last_error` AND filters `metadata.provider_options` down to a public allowlist (via `providerOptionsFromMetadata`, `connector-lifecycle.ts:170-180`); also sets `release_readiness_state: "blocked"` specifically for `gmail` (`index.ts:58`).
- Side B's `list-sources/index.ts:31`: `sources: sources ?? []` — **zero** sanitization, and this file is **completely unmodified since the base commit** (`git log --oneline -- supabase/functions/list-sources/index.ts` → only `3bfca59`, the shared base both sides diverged from).
- Side B's own `sanitizeSourceForResponse()` (`_shared/connector-lifecycle.ts:32-39`) exists and IS wired into `sync-source`'s response (`sync-source/index.ts:9`, used at lines 192,204,354,387,422) — it was simply never wired into `list-sources`, the primary "show me all my connected sources" read surface a frontend actually calls. Side B's own code comment (`connector-lifecycle.ts:26-30`) explicitly names the risk this leaves open: *"a once-tainted last_error could otherwise re-leak on every SUBSEQUENT response that includes source"* — and `list-sources` is exactly such a subsequent, unprotected response path.
- Side A built a dedicated `_shared/test-support/sentinel-scanner.ts`/`.test.ts` that scans response/log/DB-row shapes across all 5 functions for secret-shaped sentinels. **Side B has no equivalent file at all** (`find ... -iname "*sentinel*"` → no results in Side B's tree).

### `start-connection`

| | Side A has | Side B has |
|---|---|---|
| Reconnect | **None** | Optional `source_id` in request body triggers reconnect-mode lookup, snapshots `connector_generation`/`status` into `oauth_connection_states` (`index.ts:62-94`) |
| direct_credentials/IMAP branch | Full branch (`index.ts:138-196`) with option validation + secret-key filtering (`normalizeLifecycleOptions`, `buildLifecycleMetadata`) | **None** — only branches on `auth_type !== "file_import"` (treated as OAuth) vs `file_import`, unchanged from base commit `3bfca59` (`git show 3bfca59:...start-connection/index.ts` confirms this 2-branch shape predates both sides). `provider_options` is stored **raw/unfiltered** (`index.ts:102`), no secret-key redaction. Likely out of the Gmail-only spec's scope for Side B (Gmail is OAuth, not direct_credentials) but is a real breadth gap in the shared function. |
| Error sanitization | `redactSecretText()` — 4+ sites | **Zero** — raw `.message` at `index.ts:40,86,106,133` |

### `sync-source`

Already covered in depth in §1 (the CAS mechanism itself). Additional deltas:

- Side B's "two truths at once" fix (`index.ts:240-242, 362-385, 401-422`,
  `sourcesWriteAlreadySucceeded` flag): prevents a late, genuinely-failing
  `finishSyncJobFailure`/`finishSyncJobSuccess` call from clobbering an
  already-landed success response. Side A's catch-all (`index.ts:360-368`) has no
  such flag or scoping — Side A never built the adversarial test class that would
  surface this gap (Side B's own test file has this exact case:
  *"the outer catch-all (post-success path): finishSyncJobSuccess fails genuinely
  AND the subsequent finishSyncJobFailure call ALSO fails genuinely -- the handler
  still returns the ORIGINAL success response"*).
- Side A's `sync-source/index.ts:141` redacts the initial source-lookup error
  (`redactSecretText(sourceErr.message)`); Side B's equivalent line (`index.ts:144`)
  is the **one unredacted spot** in an otherwise well-sanitized file (8 redaction
  call sites elsewhere in this file, confirmed via grep) — a small, isolated miss,
  not a pattern, but real.
- Gmail 403 handling: **both sides implement it, differently.** Side A's
  `_shared/providers/gmail.ts:107-128` (`mapGmailError`) classifies 403 reasons into
  distinct sanitized codes (`gmail_rate_limit_exceeded`, `gmail_daily_limit_exceeded`,
  `gmail_domain_policy_blocked`) but does **not retry** — the first rate-limited
  response fails the sync immediately. Side B's `_shared/gmail-adapter.ts:172-229`
  implements an actual **retry-with-backoff loop** for 403s
  (`GMAIL_403_RETRY_MAX_ATTEMPTS`, `GMAIL_403_BACKOFF_MS`, `sleep()` between
  attempts — confirmed by direct read, not inferred from a test name), only
  terminalizing to a sanitized code (e.g. `rate_limit_retries_exhausted`) once
  attempts are exhausted. This is a genuine behavioral advantage for Side B: a
  transient Gmail rate-limit will self-heal within one sync attempt in Side B, but
  will hard-fail on the first 403 in Side A.
- Side A's 401→refresh→retry (`sync-source/index.ts:76-94,258-310`) is functionally
  similar in *intent* to Side B's refresh-checkpoint logic, but is **not
  generation-guarded** — a disconnect racing Side A's refresh would still
  unconditionally re-store the refreshed credential via plain `storeCredential`,
  unlike Side B's `storeCredentialGuarded`.

---

## 3. Test coverage comparison (both suites actually run, `deno test`, deno 2.9.2)

### Side A (`af44/taxahead-connector-platform`)

- `deno check supabase/functions/**/*.ts` → **clean, exit 0, 0 errors** (I ran this
  directly).
- `deno test --allow-read --allow-write --allow-run --allow-env --allow-net supabase/
  smoke/` → **197 passed, 0 failed** (independently reproduced by me; matches Side
  A's own run_log claim exactly). This includes Side A's newly-built `smoke/`
  directory tests (`connector-smoke.test.ts` 22/22, `gmail-live-runner.test.ts`
  15/15, `auth-handoff.test.ts` 7/7, per Side A's own log — not independently
  re-verified per-file by me, but the aggregate 197/197 total I ran myself confirms
  the sum).
- Scoped to just the 5 shared functions + `_shared/`: **148 passed, 0 failed**.

### Side B (`taxahead-gmail-planrevision-b`)

- `deno test` (default, WITH typecheck) on the 5 functions + `_shared/` →
  **FAILS to typecheck.** Required `npm install` first (missing `@types/node` in
  `node_modules/`, a gitignored dependency dir — not present in git history).
  After that, **8 concrete TS errors**, reproduced directly:
  - `_shared/gmail-adapter.test.ts:336,495` — implicit-`any` parameter (cosmetic).
  - `_shared/gmail-adapter.test.ts:365` — a test-definition shape mismatch (cosmetic).
  - `_shared/sync-jobs.test.ts:28,61` — **real drift**: both call sites call
    `startSyncJob(client, {...})` without the now-required `sourceGeneration` field
    (`sync-jobs.ts:21` declares it required) — the test file was not updated when
    the production signature changed.
  - `sync-source/index.test.ts:1288,1499,1501` — **real drift**: references a
    `.payload` property that does not exist on the `CallRecord` type (the real type
    is `{kind:"rpc", name, args}` — no `payload` field).
- `deno test --no-check` (same scope) → **180 passed, 0 failed** — behaviorally
  green, but this only suppresses the typecheck failure, it does not fix it.
- `deno test --no-check` (repo-wide, `supabase/`) → **180 passed, 0 failed**
  (same total; no smoke dir to add).
- `ls smoke/` → **directory does not exist.** Confirms the dispatch brief's
  description of Side B's missing shared smoke foundation is still accurate for
  Side B (unlike Side A, which has since self-built one — see the header note).
- `npm run lint` (repo-wide) → **4972 problems (4960 errors, 12 warnings)**, 4923
  auto-fixable via `--fix` — overwhelmingly Prettier formatting, but real and
  reproducible, matching the brief's claim. Includes real formatting drift inside
  `sync-source/index.ts` itself (not just unrelated files), e.g. lines 16, 34, 131,
  192, 204, 267, 300, 317, 376, 381, 387, 410, 422 all flagged.

### Honest discrepancy flag

Side B's own `run_log.md` (mid-run, before the final "Live Schema Blocker
Localization" checkpoint) claims `deno check supabase/functions/**/*.ts: passed` and
`deno test ...: passed, 197/197`. **That claim does not reproduce today** — the
identical-scope command fails to typecheck with 8 concrete errors right now. This
could reflect drift since the log entry was written (the project's own standing
lesson `feedback_one_session_per_worktree.md` documents exactly this class of risk —
a sibling session's edits landing in a shared worktree between when a claim was
logged and when it's re-checked), rather than the claim being false when it was
made. Either way: **as of this inspection, Side A's gates are demonstrably clean
end-to-end and Side B's are not** — this is a directly reproducible fact, not a
restated self-report.

---

## 4. Does Side A duplicate or diverge from Side B's known-fixed bug classes?

- **H-FENCE-ENUM-INCOMPLETE-1** (`~/Claude/loop/fix_plan.md:7501-7521`) is from a
  **different build entirely** (the TaxAhead diagnostics-hardening build, not either
  Gmail connector side) and concerns `extract-document`'s post-claim
  `documents.status` writes not all being enumerated into fenced primitives across
  two plan-check rounds. Side A does touch `extract-document/index.ts` (confirmed
  via `git diff dad15c0 -- supabase/functions/extract-document/index.ts`), but **the
  entire diff is pure reformatting** (deno-fmt-style multi-line wrapping of
  `.from(...).select(...)` chains, `.update({status:...})` calls, etc.) — every
  write call site is byte-identical in substance to the pre-existing code. Side A
  introduces no new write path here and neither fixes nor worsens whatever fencing
  state that file was already in; it inherits it unchanged.
- Side B does **not** touch `extract-document/index.ts` at all —
  `git log --oneline -- supabase/functions/extract-document/index.ts` in Side B's
  tree shows only the very first repo commit (`b24febf`). Side B has zero exposure
  to this file's history either way.
- The "7-bug hand-rolled CAS mechanism" is **Side B's own internal history**
  (`plan_check_log.md:243-292`, summarized in §1 above) — an early hand-rolled
  `acquire_sync_guard` RPC that was deleted and replaced with a ported,
  already-proven sibling mechanism. Side A was never exposed to any of those
  specific defects because **Side A never built a CAS mechanism of its own at all**
  — hand-rolled or otherwise. So Side A cannot be said to "reintroduce" any of
  Side B's fixed bugs (there's nothing to regress). The flip side: Side A carries
  100% of the *original*, pre-mitigation race exposure that the hand-rolled (and
  later ported) mechanism was built to close in the first place.
- One notable meta-fact: `plan_check_log.md:365` confirms Side B's own plan-check
  process was directly aware of Side A's worktree path
  (`feature/connector-gmail`/`af44`) as one of three sibling worktrees it verified
  were reachable — so the two builds were not merely unaware of each other in the
  abstract; Side B's process saw Side A's worktree and still built independently,
  confirming the "zero coordination" framing in the dispatch brief.

---

## 5. Recommendation (advisory — Nnamdi decides)

**MERGE, not wholesale-keep-either-side.** Concretely:

1. **Take Side B's `connector_generation`/CAS architecture as the concurrency base.**
   Migration `0011_connector_generation_guards.sql`, `updateSourceIfCurrent`/
   `isSourceGenerationCurrent` (`sync-source/index.ts`), the single-flight guard +
   15-minute reaper (`sync-jobs.ts`), the reconnect-mode plumbing across
   `start-connection`/`complete-oauth-connection`/`disconnect-source`, and the
   "two truths at once" fix. This is real, adversarially-tested engineering (many
   `[SECURITY-ORACLE]`-tagged tests, independently reproduced green by me) closing
   concrete production races Side A has **zero** protection against. Side A also
   has no reconnect flow at all — a real, separate gap (duplicate source rows on
   re-auth) that only Side B addresses.

2. **Layer Side A's uniform secret/error-leakage hygiene on top.** Side A's
   `redactSecretText()`/`sanitizeSourceForResponse()` (with `provider_options`
   allowlist filtering)/`sentinel-scanner`-driven test discipline is applied
   consistently across **all 5** functions. Side B's is uneven — solid in
   `sync-source` and `complete-oauth-connection`, **completely absent** in
   `list-sources`, `disconnect-source`, and `start-connection` (raw `.message`
   leaks confirmed at 9+ call sites across those 3 files; `list-sources` is
   especially exposed since it's the primary read surface and has literally never
   been touched since the base commit). This is the single most concrete,
   fastest-to-fix gap in Side B — it needs the exact pattern Side A already proved
   out, not a new design.

3. **Port Side A's Gmail 403 classification granularity if Side B's own
   classification is coarser** — actually the reverse is true on inspection: Side
   B's retry-with-backoff loop (`gmail-adapter.ts:172-229`) is strictly more
   capable than Side A's classify-and-fail-immediately approach
   (`gmail.ts:107-128`). Keep Side B's version here; no action needed.

4. **Unblock the smoke-harness stalemate pragmatically.** Side B's `blocked` state
   exists purely because the shared smoke foundation (`smoke/`,
   `smoke_auth_handoffs`, `smoke_cleanup_audit`) was never built in this worktree.
   Side A has since built a working (if self-contained) `smoke/` harness with a
   197/197-passing suite including live-runner/auth-handoff/cleanup-oracle tests.
   Porting Side A's `smoke/` scaffolding into whichever base is chosen is very
   likely the fastest path to an actual live-smoke-pass, rather than waiting on a
   separate foundation panel to build the same thing from scratch.

5. **Before merging anything, fix Side B's own currently-broken typecheck.** It's
   small and mechanical (add `sourceGeneration` to 2 call sites in
   `sync-jobs.test.ts`, fix the `.payload` reference in `sync-source/index.test.ts`
   at lines 1288/1499/1501) but it means Side B's gates are not green right now,
   contrary to its own run_log's last full-suite claim — this needs to be
   re-verified clean before anyone treats Side B as a merge-ready base.

The reasoning in one sentence: **Side B solved the harder, more valuable problem
(concurrency correctness) more thoroughly than Side A did (Side A didn't attempt it
at all), while Side A solved an easier, more mechanical problem (uniform leakage
hygiene) more thoroughly than Side B did (Side B did it in 2 of 5 files and stopped).
Neither side's solution to its stronger area is hard to port into the other's
codebase — a merge captures both without re-doing either side's real work.**

---

## Sources (all file:line citations verified by direct read/grep/test-run, not relayed)

- Side A worktree: `<HOME>/.codex/worktrees/af44/taxahead-connector-platform`
  - `supabase/functions/sync-source/index.ts`
  - `supabase/functions/disconnect-source/index.ts`
  - `supabase/functions/list-sources/index.ts`
  - `supabase/functions/start-connection/index.ts`
  - `supabase/functions/complete-oauth-connection/index.ts`
  - `supabase/functions/_shared/sync-jobs.ts`, `_shared/connector-lifecycle.ts`,
    `_shared/providers/gmail.ts`, `_shared/test-support/sentinel-scanner.ts`
  - `supabase/migrations/0005_connector_platform.sql`,
    `0006_oauth_connection_states.sql`, `0009_secret_vault_rpc.sql`
  - `loop-team/runs/2026-07-09-gmail-connector/run_log.md` (1628 lines, read in full)
  - `git diff dad15c0 -- supabase/functions/extract-document/index.ts`
  - Live test runs: `deno check supabase/functions/**/*.ts`;
    `deno test --allow-read --allow-write --allow-run --allow-env --allow-net supabase/ smoke/`
- Side B worktree: `<HOME>/Claude/Projects/taxahead-gmail-planrevision-b`
  - `supabase/functions/sync-source/index.ts`
  - `supabase/functions/disconnect-source/index.ts`
  - `supabase/functions/list-sources/index.ts`
  - `supabase/functions/start-connection/index.ts`
  - `supabase/functions/complete-oauth-connection/index.ts`
  - `supabase/functions/_shared/sync-jobs.ts`, `_shared/connector-lifecycle.ts`,
    `_shared/gmail-adapter.ts`
  - `supabase/migrations/0011_connector_generation_guards.sql`
  - `loop-team/runs/2026-07-09-gmail-connector/run_log.md`,
    `loop-team/runs/2026-07-09-gmail-connector/plan_check_log.md`
  - `git log --oneline`, `git show 3bfca59:supabase/functions/start-connection/index.ts`,
    `git log --oneline -- supabase/functions/list-sources/index.ts`,
    `git log --oneline -- supabase/functions/extract-document/index.ts`
  - Live test runs: `deno test` (default, typecheck); `deno test --no-check`;
    `npm run lint`; `npm install` (dependency population only)
- `~/Claude/loop/fix_plan.md:7501-7521` (`H-FENCE-ENUM-INCOMPLETE-1`)
- `~/Claude/loop/loop-team/roles/researcher.md` (role brief read in full before starting)
