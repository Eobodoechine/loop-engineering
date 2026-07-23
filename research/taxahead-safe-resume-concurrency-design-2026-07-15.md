# TaxAhead safe-resume concurrency and recovery design

Date: 2026-07-15  
Mode: Loop-Team Researcher Mode D  
Status: design-supported; no TaxAhead or hook code changed

## Question

What is the smallest coherent mechanism that closes the six round-2 plan gaps without relying on informal writer stoppage, editable authorization fields, a dirty target checkout, or a schema rollback assumption?

## Answer: one Lock/Launch Coordinator

Add one machine-owned **Lock/Launch Coordinator (LLC)**. Every writer in this recovery uses the LLC; workers receive detached disposable worktrees and may not update shared refs or evidence directly. The LLC is the only process allowed to:

1. acquire/renew the run lease;
2. validate and seal evidence;
3. create the one-shot authorization claim and launch the direct Coder;
4. advance the implementation frontier or target branch by compare-and-swap (CAS);
5. open/close migration and recovery boundaries; and
6. write immutable receipts.

The LLC must be implemented, independently tested, and hash-bound into the authorization record before it can be used. Until then the state is `COORDINATOR_UNAVAILABLE`, not “ready”. This is a replacement mechanism, not a claim that the current hooks already provide it.

## Facts established locally

- `git worktree list --porcelain` currently reports **22** linked TaxAhead worktrees.
- The reconciliation worktree resolves `--git-common-dir` to `<HOME>/Claude/Projects/taxahead/.git`; its per-worktree Git directory is `<HOME>/Claude/Projects/taxahead/.git/worktrees/taxahead-four-way-reconciliation`.
- Its branch is `integration/four-way-reconciliation-2026-07-15` at `77dec252078236d2c1a4ab76c78d948e322c97aa`.
- The dirty target branch is `feature/wire-real-backend` at `dad15c0a81f75a29ebce61a3b09c0742297229db`.
- Local Git is 2.50.1 and exposes `git update-ref <ref> <new-oid> [<old-oid>]` plus `--stdin` transactions.
- Local Deno is 2.9.2. `psql` and `supabase` are not on the current shell path, so the non-disposable database phase is not locally executable until the DB operator proves a versioned client/connection path.
- `<HOME>/.codex/hooks.json` registers the loop `PreToolUse`, `SubagentStop`, and `Stop` hooks. The current loop worktree has uncommitted hook changes, including Codex `spawn_agent` normalization. Therefore this design treats the normal Agent/Task/Workflow path as `HOOK_UNLANDED`; the direct route below does not claim automated gate credit.

## 1. Cooperative run lease

### Lease representation

Use one shared Git ref:

`refs/loop-safe-resume/taxahead/lease`

It points to a commit containing canonical JSON with:

`schema_version`, `run_id`, `epoch`, `holder_uuid`, `host`, `pid`, `process_start_utc`, `acquired_utc`, `heartbeat_utc`, `expires_utc`, `scope_digest`, and `previous_lease_oid`.

The scope is finite and hashed: the five named worktree roots, the TaxAhead Git common directory, the integration and target refs, and `<HOME>/Claude/loop/runs/2026-07-15_taxahead-safe-resume-plan/evidence`.

### Acquire, renew, and takeover

- Initial acquire creates the ref only if absent (`old-oid = 0`).
- Renewal creates a new lease commit and updates the lease ref only from the current lease OID.
- TTL is **15 minutes**; heartbeat is **60 seconds**. The holder must stop issuing side effects if its last successful renewal is older than 2 minutes.
- Another process may take over only after expiry **and** after proving the recorded `(host, pid, process_start_utc)` no longer identifies a live process. If it is alive but hung, the user must explicitly terminate it first. Takeover increments `epoch` and CAS-updates from the expired lease OID.
- Every LLC side effect records and rechecks the current `epoch` and lease OID immediately before and after. A mismatch is `LEASE_LOST`; the result is quarantined and cannot advance a ref.

This is structurally exclusive for LLC-mediated shared-ref updates. It is cooperative, not an OS mandatory lock over every path: an unrelated shell can still write a worktree. That residual risk is made detectable by before/after fingerprints and manifest rehashes; any drift is blocking. The plan must prohibit direct writers rather than overstate the lease.

## 2. Evidence validation under the lease

The outer manifest is valid only if the LLC performs this exact validation while holding the lease:

1. Enumerate the declared evidence roots and compare the actual finite path set with the union of child-manifest entries. An omitted or extra path is `MANIFEST_SET_MISMATCH`.
2. For every entry, reject symlink traversal, then recompute type, mode, size, symlink target where applicable, and SHA-256 from the child bytes. Never trust a stored child digest.
3. Recompute each canonical child-manifest digest, then canonical `outer-manifest.json`, then `outer-manifest.sha256`.
4. Repeat file metadata/digest checks after the traversal. A change is `MANIFEST_DRIFT`.
5. Immediately before authorization claim, every frontier CAS, final verification, target landing, and recovery landing, repeat steps 1–4 and write an `O_CREAT|O_EXCL` validation receipt keyed by `(outer_digest, lease_epoch, action_id)`.

The static outer manifest covers preservation, restore, snapshots, canonical spec, and red baseline. Later operational receipts live in a separate append-only control namespace and hash-chain to their predecessor; they do not mutate the sealed outer manifest.

## 3. Exact finite red-baseline table

The current candidate set is exactly the following six paths: five test/fixture files plus `deno.lock`. Final baseline digests are written only after independent review/repair; the observed digests below identify the current candidate and prevent silent omission.

| Manifest key | Exact path | Observed SHA-256 | Bound acceptance criterion | Exact baseline command and expected state |
|---|---|---|---|---|
| `RB-01` | `src/lib/__reconciliation__/edge-functions.region-b-shape.contract.test.ts` | `47a10f34dcd9de60c02dca89f543e7c8bc1c1a8909e43ce8f8c46936cfd1bf68` | Spec AC2 type shape; AC3 CP Deno contracts | `deno test --frozen --allow-read src/lib/__reconciliation__/edge-functions.region-b-shape.contract.test.ts` -> **GREEN 4/4 regression guard**, plus a recorded negative mutation replacing CP unions with main's narrower shapes must fail. It is sealed but does not count as red. |
| `RB-02` | `supabase/functions/ask-taxahead/index.reconciliation.test.ts` | `0e5fbb2cfc7169c2154fd0aed5dcb6618d5d6beda1c46dad8bd22f934774c061` | AC3 lineage suite; AC4 grounded Q&A plus tracing | `deno test --frozen --allow-env --allow-net supabase/functions/ask-taxahead/index.reconciliation.test.ts` -> fetch-only guard green; the three `startRun` integration cases fail by assertion because tracing is absent. |
| `RB-03` | `supabase/functions/complete-oauth-connection/index.reconciliation.test.ts` | `d182ce4d7f2b087df7ddb0865b41e2a0faadb30a4d2d2a14f6040114fe66ea15` | AC3 lineage suite; AC4 real Dropbox OAuth/reconnect safety | `deno test --frozen --allow-env --allow-net supabase/functions/complete-oauth-connection/index.reconciliation.test.ts` -> Dropbox RPC guard green; guarded credential-store and claim-before-exchange cases fail by assertion because merged behavior is absent. |
| `RB-04` | `supabase/tests/reconciliation/migration-sequence-0001-0014.test.ts` | `13ffb7b2773effdb7791a9b71d0abbfa5d658efa9a8b2a5d45f0e3da41538fb2` | AC3 migration/pgTAP preservation; AC4 real pipeline schema | With a fresh throwaway DB at `postgresql://postgres@127.0.0.1:55433/taxahead_test`: `TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55433/taxahead_test deno test --frozen --allow-env=TEST_DATABASE_URL --allow-read=supabase/migrations,supabase/tests/reconciliation --allow-net=127.0.0.1:55433 supabase/tests/reconciliation/migration-sequence-0001-0014.test.ts` -> assertion-level red for missing 0007/0008/0013/0014, not connection/environment error. |
| `RB-05` | `supabase/tests/reconciliation/fixtures/local-pg-stubs.sql` | `b2a48d4d87ee396ac40a7ce63240cb41b069f04ea9d9ee203db44dd2edc41994` | AC3/AC4 fresh-DB migration execution | Dependency of the exact `RB-04` command; manifest must label `fixture_only:true`, `production_apply:false`. A scan must prove it remains outside `supabase/migrations/`. |
| `RB-06` | `deno.lock` | `b4da6efbd614cf254f7ada850513a2cf1c703caf6918e08e1d391c9c9aa78b47` | AC3 reproducible Deno suites | Dependency of `RB-01` through `RB-04`; all four commands use `--frozen`. Any lock change creates a new baseline commit and invalidates authorization. |

Baseline commit creation is path-scoped to only `RB-01`–`RB-06`, from expected parent `77dec252078236d2c1a4ab76c78d948e322c97aa`. The LLC advances `refs/heads/integration/four-way-reconciliation-2026-07-15` to the reviewed baseline only with expected-ref CAS. No other staged path is allowed.

## 4. Single-use human authorization and direct launch

### Canonical claim

After neutral review accepts the exact spec/baseline/outer tuple and the user approves `human-exception.json`, the LLC:

1. holds the lease and rehashes every child manifest;
2. builds a canonical claim commit containing all bound digests, target expected head, permitted scope, neutral-review artifact/outcome, `HOOK_UNLANDED` acknowledgement, LLC code hash, Codex binary path/version, channel ID, and expiry;
3. atomically creates `refs/loop-safe-resume/taxahead/auth/<authorization_id>` from zero to that commit; and
4. mirrors the result to `evidence/authorization/claims/<authorization_id>.json` using `open(..., O_CREAT|O_EXCL|O_NOFOLLOW)`, writes, fsyncs, closes, and reads back the digest.

The ref creation is authoritative. If the ref already exists, the authorization is consumed. If the process crashes after ref creation or the mirror is incomplete, state is `CLAIMED_NO_LAUNCH_OUTCOME`; it remains consumed and requires a fresh user authorization after investigation. The launcher never updates or deletes an auth ref.

### Explicit channel

Channel ID: **`LLC_DIRECT_CODEX_EXEC_V1`**.

The same LLC process that won the claim launches a standalone, ephemeral local Codex worker with the installed binary:

`/Applications/ChatGPT.app/Contents/Resources/codex exec --ephemeral --sandbox workspace-write -C <fresh-detached-worktree> -`

The prompt is generated from the claim and exact spec, identifies the worker as TaxAhead Coder, forbids subagent dispatch and shared-ref/evidence writes, and permits only the current micro-step paths. This is intentionally not an Agent/Task/Workflow dispatch, does not cite `PLAN_PASS`, and does not claim automated hook credit. Existing global hooks remain enabled; the session is a standalone worker, not Oga. PID/session/output and exit are written as immutable outcome receipts. Launch failure consumes the claim.

## 5. Micro-step frontier and failure states

Each step uses a fresh detached disposable worktree at the current integration frontier. The ledger is a hash-chained sequence of immutable receipts.

| State | Required transition |
|---|---|
| `STEP_PLANNED` | Bind sequence, start commit/tree, expected frontier OID, exact AC, allowed paths, command, authorization ID, and lease epoch. |
| `STEP_IN_PROGRESS` | Direct Coder edits only the disposable worktree. Shared frontier remains unchanged. |
| `STEP_ABORTED_PRECOMMIT` | Capture porcelain-v2, staged/unstaged binary diffs, file digests, stdout/stderr, and cause; create an evidence ref for any objects; quarantine the dirty worktree; never clean/reset/reuse it. Resume from a new disposable worktree at the recorded start OID. |
| `STEP_REJECTED_COMMITTED` | Preserve candidate commit/tree under a create-only rejected-evidence ref; do not advance frontier. Build Verifier records the rejection. |
| `STEP_ACCEPTED` | Verifier approves the exact candidate commit/tree; LLC rehashes sealed evidence, verifies expected frontier still equals start, then runs `git update-ref <integration-ref> <candidate> <start>`. CAS failure becomes `STALE_FRONTIER`; candidate remains evidence only. |

No failed step is “reverted” unless its commit actually advanced the frontier. If an accepted frontier commit later needs reversal, the reversal is a new bounded step, independently verified and CAS-landed.

## 6. Merge rehearsal and target CAS

The dirty checkout `<HOME>/Claude/Projects/taxahead` is quarantined: no checkout, merge, reset, stash, clean, index write, or file write occurs there.

1. Create the merge commit in a clean disposable worktree from exact target OID plus exact verified source OID.
2. Verify the resulting merge commit/tree in full and bind all evidence to both parents and the expected target OID.
3. Under the lease, rehash evidence and land with:

   `git update-ref refs/heads/feature/wire-real-backend <verified-merge-oid> <expected-target-oid>`

4. A CAS mismatch is `TARGET_ADVANCED`; rebuild and fully reverify. The dirty checkout's bytes/index are untouched, but its symbolic branch now observes the new ref, so it remains quarantined until its owner reconciles the pre-recorded dirty state.

### Cause-specific failure triage

- `MERGE_SOURCE_FAILED`: conflict/resolution bytes or a test failure reproducible on the exact merge tree. Repair through a new P4 step, then full P5 and P6.
- `MERGE_ENV_FAILED`: merge tree/parents reproduce exactly, but a tool, dependency, permission, fixture, network, or service is unavailable. Preserve the same tree, repair environment only, and rerun verification on that exact tree. Any source edit reclassifies to `MERGE_SOURCE_FAILED`.
- `TARGET_ADVANCED`: no defect inference; rebuild against new target and repeat full exact-tree verification.

## 7. Database boundary and partial migration recovery

Before a non-disposable migration, the DB operator must prove a versioned PostgreSQL client path, database identity, backup ID, successful restore drill, and an enforced traffic freeze that pauses web writes, Edge Functions, scheduled jobs, and sync workers. The LLC then opens one dedicated DB session and acquires one session-level `pg_try_advisory_lock(<run-key>)`. It holds the session and freeze from preflight through final schema/ledger capture.

The advisory lock serializes only cooperating migration runners; PostgreSQL explicitly calls these locks advisory. Therefore the traffic freeze is a separate mandatory gate. If the platform cannot prove it, state is `DB_TRAFFIC_FREEZE_UNPROVEN` and production migration is forbidden.

Apply numbered migrations one file per explicit transaction, recording before/after schema probes and migration-ledger state. `0007_diagnostics_enum.sql` commits alone before `0008_diagnostics.sql`; PostgreSQL documents that a newly added enum value cannot be used until the adding transaction commits.

- `MIGRATION_APPLY_FAILED`: the failing file transaction rolled back and schema/ledger match the last recorded committed frontier. Previously committed files remain; keep freeze/lock and choose reviewed forward completion or tested snapshot restore.
- `PARTIAL_SCHEMA`: connection loss, ledger/schema disagreement, or catalog probes show effects beyond the last recorded frontier. Keep freeze/lock, capture schema-only/catalog/migration-ledger evidence, and permit only an independently reviewed idempotent forward repair or tested snapshot restore with user approval.
- Never infer schema rollback from a code revert. No automatic down migration is permitted for an incompatible/destructive state.

## 8. Post-merge failure loop

On `POST_MERGE_FAILED`, stop rollout and freeze writes. Capture target ref/tree, deployed revision, database identity/schema/migration frontier, and the failed proof.

- **Forward repair:** create a repair spec and tests; obtain a fresh neutral review and a fresh one-shot authorization; run P4 -> P5 -> merge rehearsal -> target CAS -> post-merge/live proof under the applicable DB boundary.
- **Revert:** create the revert commit in a disposable worktree from the exact landed target; DB operator first proves the current schema is compatible with the reverted code or selects a reviewed DB repair/restore. Run the same full exact-tree P5 verification, merge rehearsal, expected-target CAS, and post-action live proof. The revert is not privileged merely because it is a revert.
- Any target movement, tree change, ledger change, or DB-frontier change invalidates prior proof and restarts at the owning gate.

## 9. Transfer-condition checks

| Borrowed mechanism | Required context | Does this setup satisfy it? | Guarantee |
|---|---|---|---|
| Git expected-old ref update | All relevant refs share one Git common directory; installed Git supports three-argument `update-ref`. | Yes: 22 worktrees share `<HOME>/Claude/Projects/taxahead/.git`; Git 2.50.1 supports it. | Structural for each CAS ref update. |
| Git ref lease | Every recovery writer must use the LLC and recheck epoch/OID. | Partly: shared ref substrate exists; LLC is not yet implemented/audited. | Structural inside LLC; instructional for unrelated shell writers, with drift detection as backstop. |
| `O_CREAT|O_EXCL` claim mirror | One local filesystem directory, no symlink following, one canonical filename per authorization. | Yes for the run evidence path. | Structural create-if-absent; partial write fails closed because the auth ref is already consumed. |
| Child-manifest rehash | Finite declared roots, canonical JSON, no unlisted evidence writers during validation. | Yes after finite path tables are added and all recovery writers use LLC. | Structural validation; external writes are detected, not prevented. |
| Standalone Codex direct launch | Installed local Codex CLI; fresh detached workspace; user-approved exception; no nested dispatch. | CLI 0.144.2 is installed. Launcher/audit still required. | Structural single-use claim; Coder scope remains sandbox/prompt plus verifier/CAS enforcement. |
| PostgreSQL advisory lock | Dedicated live DB session and every migration runner cooperates. | PostgreSQL target is implied by Supabase; current shell lacks `psql`/`supabase`, so production readiness is unproven. | Advisory/instructional outside the LLC; fail closed unless traffic freeze is separately proven. |
| Per-file DB transaction | SQL file contains no transaction-prohibited statement; tool executes explicit transactions. | Current scanned files contain no `CREATE INDEX CONCURRENTLY` or similar prohibition; planned `0007` needs its own commit before `0008`. Re-scan the final 0001-0014 set. | Structural rollback for the current file only; the multi-file sequence can still be partial. |

No silent load-bearing guarantee is treated as purely instructional: uncoordinated Git/evidence writes cause drift failure, and unproven DB traffic freeze blocks production migration.

## 10. Primary sources opened and quoted

1. [Git `update-ref` documentation](https://git-scm.com/docs/git-update-ref.html): “updates the master branch head ... only if its current value is `<old-oid>`.” It also documents transactional `start`, `prepare`, and `commit` ref operations.
2. [Git repository layout](https://git-scm.com/docs/gitrepository-layout.html): “All files under common however will be shared between all working trees.” This grounds the one shared ref/lease domain.
3. [POSIX `open()` / `openat()`](https://pubs.opengroup.org/onlinepubs/9799919799/functions/open.html): with `O_CREAT|O_EXCL`, existence check and creation “shall be atomic”. The official page was opened directly with `curl` after the browser endpoint returned 403.
4. [PostgreSQL advisory locks](https://www.postgresql.org/docs/16/explicit-locking.html#ADVISORY-LOCKS): advisory locks are application-defined and “the system does not enforce their use”. Session locks persist until release/session end; transaction locks release at transaction end.
5. [PostgreSQL `ALTER TYPE`](https://www.postgresql.org/docs/current/sql-altertype.html): an enum value added in a transaction “cannot be used until after the transaction has been committed.”
6. [PostgreSQL `BEGIN`](https://www.postgresql.org/docs/current/sql-begin.html): statements after `BEGIN` execute in one transaction until commit/rollback; other sessions cannot see intermediate related changes.

## Planner blueprint

Apply this as one Revision-3 mechanism, not six disconnected patches:

1. Add `Lock/Launch Coordinator` to actors and its refs/receipts to destinations.
2. Put the lease contract and manifest rehash algorithm before P0; make every writer/CAS/launch/DB action require a live lease epoch.
3. Replace P1's unnamed files with `RB-01`–`RB-06`, exact commands, expected mixed green/red states, and path-scoped baseline CAS.
4. Replace editable authorization consumption with the create-only auth ref plus `LLC_DIRECT_CODEX_EXEC_V1` standalone launch and fail-closed outcomes.
5. Replace P4 rollback prose with the four step states and expected-frontier CAS.
6. Split P6 failures into source, environment/operator, and target-advanced states; land the exact verified merge through target-ref CAS without operating in the dirty checkout.
7. Add the DB session-lock + independently proven traffic-freeze boundary, per-file transactions, `MIGRATION_APPLY_FAILED`, and `PARTIAL_SCHEMA` recovery.
8. Route both post-merge forward repair and revert through fresh exact-tree verification, rehearsal, CAS landing, post-action proof, and database compatibility; require fresh authorization for a new Coder launch.
9. Update `§TRANS` and acceptance criteria so every named state has an owner, evidence receipt, invalidation condition, and resume point.

