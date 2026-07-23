# Prior-art research — sync-concurrency / disconnect-race guard for Gmail connector D.15

**Mode D (domain/prior-art) research for the Gmail connector spec revision.**
Dispatched by Oga (orchestrator), 2026-07-09, during a plan-check cycle for
`feature/connector-gmail-planrevision` (worktree `<HOME>/Claude/Projects/taxahead-gmail-planrevision`).

**Question:** the Gmail spec's §D.15 hand-rolls a single atomic Postgres RPC
`acquire_sync_guard`; Round-3 plan-check found ~7 real bugs in it AND discovered the
sibling `feature/connector-google-drive` branch already shipped a working,
differently-designed mechanism for the same problem class. Should D.15 ADOPT / ADAPT /
REJECT the sibling's mechanism?

**All findings below are from files read this session in the read-only sibling worktree
`<HOME>/.codex/worktrees/f378/taxahead-connector-platform` (branch
`feature/connector-google-drive`).** Every table Gmail uses (`sources`,
`source_sync_jobs`, `oauth_connection_states`, `source_credentials`) comes from the
SHARED migrations 0001/0005/0006/0009, identical on both branches — so the mechanism
transfers 1:1.

---

## Provenance / doc-availability honesty note

- **Migration `0010_connector_generation_guards.sql` is UNTRACKED (not committed)** — it
  shows in `git status` under "Untracked files", `git log -- <file>` returns nothing.
  mtime Jul 9 15:34, i.e. AFTER the only run dir (`2026-07-09_connector-core-runtime`,
  created 14:03).
- **No committed design/spec doc explains 0010.** The one run dir's `specs/spec.md` is
  "Increment 1: Core Runtime + Secret Vault" (ACs 1–10) and does **not** mention
  generation guards, concurrency, reaping, or races at all — it predates 0010.
  `plan_check_log.md` for that run has no concurrency findings. `grep` for
  `connector_generation`/`one_running_per_source`/`reconnect race` across all `*.md`
  returned nothing.
- Design rationale below is therefore **reconstructed from the actual consumer code +
  tests + two UNTRACKED testing docs** (`docs/testing/google_drive_readiness_report.md`,
  `docs/testing/google_drive_connector_test_gaps.md`), not from any authored design spec.
  Where the testing docs self-assess the design I quote them; otherwise I cite code.

---

## `mechanism_found` — what is actually in 0010 + its consumers

### Migration 0010 is SCHEMA-ONLY — no functions, no RPC (verbatim, 23 lines)

The whole guard is a **monotonic generation counter + a partial unique index +
app-level CAS-through-RLS**. There is NO `acquire_sync_guard`-style RPC. The migration adds:

- `sources.connector_generation integer not null default 0` (L4–5)
- `oauth_connection_states`: `source_id uuid references sources(id) on delete cascade`,
  `mode text not null default 'connect' check (mode in ('connect','reconnect'))`,
  `source_generation integer`, `source_status text` (L7–12)
- `create index oauth_connection_states_source_created_idx on (source_id, created_at desc)` (L14–15)
- `source_sync_jobs.source_generation integer` (L17–18)
- **THE atomic primitive:**
  `create unique index if not exists source_sync_jobs_one_running_per_source_idx on source_sync_jobs (source_id) where status = 'running';` (L20–22)

Header comment (L1–2): *"Additive only: supports CAS checks without introducing a new
source_status enum."*

### Base schema facts that make the mechanism work (0001_init.sql)

- `create type source_status as enum ('connected','syncing','error','disconnected')` (L8);
  `sources.status source_status not null default 'connected'` (L45).
- `create policy "fu sources" on sources for all using (owns_fu(filing_unit_id))` (L188) —
  **sources is RLS-protected by `owns_fu`.** Because the entire guard runs through the
  edge function's caller-JWT RLS-bound client (never a SECURITY DEFINER function), the
  tenant-ownership check is enforced automatically by this policy on every guard write.
- `source_sync_jobs.status` check is `('queued','running','succeeded','failed')`
  (0005 L34) and `.mode` check is `('initial','incremental','manual')` (0005 L33).

### The consumer logic (all in TypeScript edge functions, all uncommitted/modified)

1. **at-most-one-running** — `_shared/sync-jobs.ts::startSyncJob` (L19–42): SELECT for an
   existing `status='running'` row for the source → `throw new Error("sync_already_running")`
   (L27); then `insert({ ..., status:'running', started_at: now(), source_generation })`
   (L29–42). The partial unique index is the atomic backstop that makes the
   SELECT-then-INSERT safe under a real race. `mode: args.mode` is passed through
   **faithfully** (L35) — not hardcoded.
2. **disconnect CAS bump** — `disconnect-source/index.ts` (L63–77):
   `update({ status:'disconnected', disconnected_at:now(), last_error:null, sync_cursor:{},
   connector_generation: connectorGeneration + 1 }).eq('id', sourceId)
   .eq('connector_generation', connectorGeneration)` — monotonic increment guarded on the
   old value; `if (!source) return 403` (L80). Then best-effort
   `rpc('delete_source_credential', {p_source_id})` (L85–94).
3. **sync write CAS + up-front disconnect gate** — `sync-source/index.ts`:
   - `if (source.status === "disconnected") return json({error:"source_disconnected"},409)` (L68).
   - `sourceGeneration = source.connector_generation ?? 0` (L69–70).
   - `assertSourceCurrent()` (L136–146): re-SELECT `.eq('connector_generation', sourceGeneration)
     .neq('status','disconnected')`, returns Boolean(row).
   - `updateSourceIfCurrent(payload)` (L148–159): `update(payload).eq('id',source.id)
     .eq('connector_generation', sourceGeneration).neq('status','disconnected').select('id')
     .maybeSingle()` → returns whether a row was hit; **0 rows ⇒ stale.**
   - Checkpoints: before credential read (L161), before + after `adapter.refreshToken`
     (L175, L180), and the final cursor/status update (L230–239). Any 0-row result ⇒
     `finishSyncJobFailure(job.id,'stale_source_generation')` + `409` (L162–163, 176–177,
     181–182, 236–239).
   - **EVERY `sources.status` write carries the CAS**: no-adapter error path (L97–102),
     no-adapter success path (L106–111), adapter final update (L230–235), catch/error path
     (L256–261). All four use `.eq('connector_generation', sourceGeneration).neq('status','disconnected')`.
   - Nonexistent source: `if (!source) return 403 source_not_found_or_unauthorized` (L67).
   - Race catch: `if (String(e).includes("sync_already_running")) return 409` (L129–130), else
     `sync_job_create_failed` 500 (L132).
4. **job-completion CAS** — `sync-jobs.ts` `finishSyncJobSuccess`/`finishSyncJobFailure`
   (L46–75): `update({status:'succeeded'|'failed', finished_at, ...}).eq('id',jobId)
   .eq('status','running')`; success throws `sync_job_finish_stale` if 0 rows (L59).
5. **reconnect CAS** — `start-connection/index.ts` (L106–109) stows
   `source_generation = reconnectSource.connector_generation` and
   `source_status = reconnectSource.status` into the `oauth_connection_states` row;
   `complete-oauth-connection/index.ts` reconnect branch (L141–165) applies
   `{status:'connected', disconnected_at:null, ...}` only `.eq('connector_generation',
   oauthState.source_generation).neq('status','disconnected')` → else `source_reconnect_stale`
   409 (L164). A second CAS-guarded update on credential-store failure (L209–214).

### Tests that prove the mechanism (real, in the branch)

- `sync-source/index.test.ts:1016` "overlapping running sync is rejected before inserting
  another job" → `sync_already_running`.
- `sync-source/index.test.ts:970` "disconnected source cannot start a sync job or be
  resurrected to connected" → `source_disconnected`, asserts no job created / no status update.
- `sync-source/index.test.ts:1055` "stale source generation cannot be marked connected by
  an old sync finisher" → asserts the `.neq('status','disconnected')` guard is present in the
  update filters (L1095–1096) and returns `stale_source_generation`.
- `complete-oauth-connection/index.test.ts:868` "stale reconnect generation cannot resurrect
  or replace a source" → `source_reconnect_stale`.

---

## `solves` — the 4 problems, assessed against the real code

| Problem | Verdict | Evidence |
|---|---|---|
| **(a) at-most-one concurrent sync, atomic acquire** | **SOLVED (atomic)** | Partial unique index `...one_running_per_source_idx ... where status='running'` (0010 L20–22) makes it structurally impossible for a 2nd running row to exist. startSyncJob SELECT-check gives clean 409 in the common case. Test :1016. |
| **(b) recover a stuck/crashed sync (staleness/reaping)** | **NOT SOLVED — real gap** | NO time-staleness anywhere (grep `interval/stale/reap` finds only the unrelated oauth 15-min expiry). Jobs are inserted directly as `'running'` (never `'queued'`); if the function crashes/times out, no catch runs, the row stays `'running'` forever, and then BOTH the unique index AND startSyncJob's SELECT permanently block all future syncs for that source. Disconnect bumps generation but never touches `source_sync_jobs`, so it doesn't clear a wedged job either. **This is the one thing my D.15 addresses that the sibling does not.** |
| **(c) racing disconnect vs in-flight credential-store write** | **PARTIAL — same residual TOCTOU my design has** | disconnect deletes the credential + bumps generation + sets disconnected (L63–94); sync guards `storeCredential` with `assertSourceCurrent()` before/after refresh (L175, L180). BUT `store_source_credential` (0009) is NOT generation-aware and is a separate RPC call, so a disconnect landing between the check and the store re-inserts the secret (status stays disconnected, but the token leaks back into Vault + source_credentials). The branch's own readiness report concedes this (see quote below). |
| **(d) racing disconnect vs in-flight completion (cursor/status)** | **SOLVED** | Final cursor/status write via `updateSourceIfCurrent` (CAS on generation + not-disconnected); a racing disconnect bumps generation ⇒ 0 rows ⇒ `stale_source_generation` 409, sync's own writes become no-ops. Up-front gate L68. Tests :970, :1055, and reconnect :868. |

Readiness-report self-assessment, verbatim
(`docs/testing/google_drive_readiness_report.md:194`):
> "Production atomic state claim would be stronger as a single DB RPC/CAS over
> state/generation. Current implementation uses the existing table update shape because no
> migration/RPC was in scope."

This is the author of the sibling design telling us exactly where it is weaker — the (c)
credential atomicity — which is the one place my hand-rolled-RPC instinct was directionally
right (mine was just buggy).

---

## `gaps` — bug-class check vs my D.15's 7 findings

| My D.15 bug | Recurs in sibling? | Evidence |
|---|---|---|
| Hardcodes `mode='incremental'` | **NO** — mode preserved | `sync-jobs.ts:35` `mode: args.mode`; no-adapter path `sync-source.ts:84` passes `mode`. Tests :267/:296/:326 assert routing. |
| `coalesce(started_at, now())` makes a `queued` row un-stale | **N/A** — no queued, no time-staleness at all | Mechanism never inserts `'queued'` and does no interval check; the self-contradiction can't exist. (Cost: no reaping — problem (b).) |
| Credential defense not atomic (no `FOR UPDATE`) | **YES — shares it** | `store_source_credential` (0009) has no FOR UPDATE / no generation param; app-level `assertSourceCurrent` is TOCTOU. This is problem (c). |
| No `owns_fu` tenant-ownership check | **NO — present via RLS** | Guard runs through caller-JWT RLS client (not SECURITY DEFINER), so `"fu sources" ... owns_fu` (0001:188) applies to every write. Advantage of the app-level-CAS approach. |
| Nonexistent `source_id` → silent NULL | **NO — handled** | `if (!source) return 403` in sync-source (L67) and disconnect (L80). |
| Completion does 2 non-atomic writes | **PARTIAL** — narrowed, not eliminated | Cursor/status update + job finish are still 2 statements, but both are CAS-guarded (generation, and `status='running'` respectively), so a crash between them leaves a recoverable state rather than a silent success — except the (b) reaper is still missing to recover a job stuck at that point. |
| Extra unconditional `sources.status` writes | **NO — all CAS-guarded** | All 4 status write-sites carry `.eq('connector_generation',…).neq('status','disconnected')` (L97–102, 106–111, 230–235, 256–261). |

**New imperfection the sibling introduces (minor):** on a TRUE concurrent race where both
callers pass startSyncJob's SELECT, the loser hits the unique-index violation whose Postgres
message ("duplicate key value violates unique constraint …") does NOT contain
`"sync_already_running"`, so sync-source's catch (L129) falls through to a 500
`sync_job_create_failed` instead of a clean 409. The **at-most-one guarantee still holds
atomically**; only the HTTP status on the rare true-race is off. Easy to fix on the Gmail port.

---

## `recommendation` — **ADAPT**

Take the sibling's whole generation-counter + partial-unique-index + app-level-CAS-through-RLS
scaffold **verbatim** (it transfers 1:1 because Gmail shares the exact same tables), and
**layer on two additions** where my design's intent was right but its RPC impl was buggy.

Why not REJECT: it is strictly better than my hand-rolled RPC on 4 of 5 bug axes
(mode, tenant-ownership, nonexistent-source, queued-null-timestamp) and equal on the 5th
(credential atomicity) — and it's real, tested, and running on a sibling branch.

Why not ADOPT-as-is: it leaves two holes my spec explicitly must close — (b) crash-reaping
and (c) credential-store atomicity.

Why drop my `acquire_sync_guard` entirely: all six of its enumerated bugs are properties of
having a monolithic SECURITY DEFINER RPC that re-implements things RLS + a unique index give
for free. Deleting the RPC deletes the bugs.

**Transfer-condition check (role-brief requirement):**
- (a) is **STRUCTURAL** — the DB partial unique index makes a second running row physically
  impossible; no participant can forget to enforce it.
- (d)/(c)/reconnect are **enforced by DB CAS predicates** but are **instructional at the
  code level**: the guarantee holds only if *every* `sources` write site includes
  `.eq('connector_generation', …).neq('status','disconnected')`. A write site that omits the
  predicate **silently resurrects state** (load-bearing, silent — passes all downstream
  checks). The sibling gets this right at all 4 status sites + reconnect + credential-error
  path; a Gmail port **must enumerate and CAS-guard every sources-write site** and not drop
  one. Flag specifically: the (c) TOCTOU failure (leaked secret after disconnect) is silent
  and load-bearing — harden it, don't just copy it.

---

## `concrete_mechanism_for_gmail` — what to write into D.15

### 1. Migration (copy 0010 verbatim; same tables apply to Gmail)

```sql
alter table sources
  add column if not exists connector_generation integer not null default 0;

alter table oauth_connection_states
  add column if not exists source_id uuid references sources(id) on delete cascade,
  add column if not exists mode text not null default 'connect'
    check (mode in ('connect','reconnect')),
  add column if not exists source_generation integer,
  add column if not exists source_status text;

create index if not exists oauth_connection_states_source_created_idx
  on oauth_connection_states (source_id, created_at desc);

alter table source_sync_jobs add column if not exists source_generation integer;

create unique index if not exists source_sync_jobs_one_running_per_source_idx
  on source_sync_jobs (source_id) where status = 'running';
```

**Delete the hand-rolled `acquire_sync_guard` RPC from D.15 entirely.**

### 2. startSyncJob (copy `_shared/sync-jobs.ts` L19–42), with one fix

SELECT-running → throw `sync_already_running`; INSERT `status:'running'` +
`source_generation` + faithful `mode`. **Fix the sibling's 500-vs-409:** in sync-source's
catch, map BOTH `sync_already_running` AND a Postgres unique-violation on
`source_sync_jobs_one_running_per_source_idx` (SQLSTATE `23505` / message containing the
index name) to the 409, so the true-race loser also gets a clean 409.

### 3. disconnect / sync-writes / job-completion / reconnect

Copy the sibling patterns 1:1:
- disconnect: `disconnect-source/index.ts` L63–94 (CAS bump `connector_generation+1` on old
  value; then best-effort `delete_source_credential`).
- sync writes: `assertSourceCurrent()`/`updateSourceIfCurrent()` (L136–159) applied to
  **every** `sources` write; 0 rows ⇒ `finishSyncJobFailure('stale_source_generation')` + 409.
- job completion: `finishSyncJobSuccess/Failure` CAS on `.eq('status','running')` (L46–75).
- reconnect: thread `source_generation`/`source_status` through `oauth_connection_states`
  (start-connection L106–109) and CAS the reconnect update (complete-oauth L141–165).
- Keep the up-front `if (source.status === 'disconnected') return 409` gate (sync-source L68).

### ADAPT addition #1 — close (b), the sibling's real gap (crash-reaping)

Add a bounded reaper so a crashed `'running'` job cannot permanently wedge a source.
Do it correctly (avoiding my `coalesce(started_at, now())` bug): jobs are inserted directly
as `'running'` with a **non-null** `started_at`, so use `started_at` directly, no coalesce.
In `startSyncJob`, **before** the running-check:

```sql
update source_sync_jobs
   set status = 'failed', error = 'reaped_stale', finished_at = now()
 where source_id = $1
   and status = 'running'
   and started_at < now() - interval '15 minutes';
```

Runs through RLS (owns_fu enforced), atomic per row. Ordering matters: reap first, so a
genuinely-stale job clears and the new sync proceeds, while a fresh (<15 min) running job
still correctly blocks (`sync_already_running`). Because `started_at` is always non-null on a
running row, the staleness predicate is sound — the exact defect that sank my D.15 version
cannot recur here.

### ADAPT addition #2 — harden (c), credential-store atomicity (shared TOCTOU)

Make the credential write generation-aware so it cannot resurrect a disconnected source's
secret. Add `p_expected_generation integer` to `store_source_credential` and gate the upsert
atomically inside the RPC (after the existing `owns_fu` check), locking the source row:

```sql
-- inside store_source_credential, after the owns_fu check, before the upsert:
perform 1 from public.sources
   where id = p_source_id
     and connector_generation = p_expected_generation
     and status <> 'disconnected'
   for update;
if not found then
  raise exception 'stale_source_generation';
end if;
```

`for update` on the sources row serializes against disconnect's generation-bump (which
updates that same row), closing the "no FOR UPDATE" TOCTOU Round-3 flagged. sync-source passes
`sourceGeneration` as `p_expected_generation`; a racing disconnect that already bumped the
generation makes the credential store raise `stale_source_generation` instead of resurrecting
the token. This is the **single** place a small SECURITY-DEFINER-level CAS is warranted
(credential writes are the security-critical resurrection vector) — and it is precisely the
"single DB RPC/CAS over state/generation" the sibling's readiness report calls "stronger"
(`google_drive_readiness_report.md:194`).

**Do NOT** reintroduce a monolithic `acquire_sync_guard`. Everything except credential-store
stays app-level-CAS-through-RLS as the sibling does it — that is what dodges 4 of my 5 bug
classes for free.

---

## Files read this session (all read-only, sibling worktree unless noted)

- `supabase/migrations/0010_connector_generation_guards.sql` (untracked; the mechanism)
- `supabase/migrations/0001_init.sql` (sources enum + RLS `owns_fu`), `0005_connector_platform.sql`
  (source_sync_jobs/status/mode checks), `0006_oauth_connection_states.sql`, `0009_secret_vault_rpc.sql`
- `supabase/functions/_shared/sync-jobs.ts`, `sync-source/index.ts`, `disconnect-source/index.ts`,
  `complete-oauth-connection/index.ts`, `start-connection/index.ts`
- `supabase/functions/sync-source/index.test.ts` + `complete-oauth-connection/index.test.ts` (test names/asserts)
- `loop-team/runs/2026-07-09_connector-core-runtime/specs/spec.md` (Increment 1 — does NOT cover 0010)
- `docs/testing/google_drive_readiness_report.md` (L180, L194 self-assessment),
  `docs/testing/google_drive_connector_test_gaps.md` (L74–76 disconnect/resurrect gap) — both untracked
```
