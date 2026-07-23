# Slice 4 (AI draft-and-approve) spec revision — Mode D domain research

Date: 2026-07-03
Requested by: Oga, ahead of writing Slice 4 spec iteration 2
Run: `~/Claude/loop/runs/2026-07-03_ai-draft-approve/`
Grounds: plan-check iteration 1 gap records #3, #5, #6, #7
(`~/Claude/loop/runs/2026-07-03_ai-draft-approve/plan_check_log.md`)

Scope note (Mode D): this is a domain/codebase research brief to unblock a spec
revision, not a radar/PACE candidate. No `research/radar.md` entry, no
priority score, no experiment spec — per `roles/researcher.md` Mode D.

---

## Q1 — Staleness signal (gap #7): does `syncMembers` ever touch `Contact.updatedAt`?

**Read in full:** `web/src/app/api/sync/padsplit/route.ts` — `syncMembers`
(lines 277-516) and the whole file (grepped for every `Contact`/`contact.`
reference).

**Finding: zero hits.** `grep -n "Contact\|client\.contact\|tx\.contact"
web/src/app/api/sync/padsplit/route.ts` returns nothing. `syncMembers` reads
`property`, `room`, and writes only `member.upsert` (lines 317-334) plus the
COLLECTIONS-risk transaction's `task`/`occupancyEvent` writes (lines 340-503).
It never creates, reads, or updates a `Contact` row at all.

Quoted — the only write in `syncMembers` that touches any host-visible entity
data:
```
317	      await client.member.upsert({
318	        where: { roomId: room.id },
319	        create: {
320	          roomId: room.id,
321	          name: member.name,
322	          moveInDate,
323	          rating: member.rating || null,
324	          financialStatus: member.financialStatus || null,
325	          balanceCents,
326	        },
327	        update: {
328	          name: member.name,
329	          moveInDate,
330	          rating: member.rating || null,
331	          financialStatus: member.financialStatus || null,
332	          balanceCents: balanceCents ?? undefined,
333	        },
334	      })
```

Contrast: the ONLY code anywhere in the repo that writes a `Contact` row is
`web/prisma/backfill_contacts.ts`, a one-time manually-invoked script:
```
81:    const contact = await (db as any).contact.upsert({
```
(confirmed via `grep -n "contact\." web/prisma/backfill_contacts.ts`).

**Answer: the latter is true — `syncMembers` never touches `Contact` at all**
(not "touches it without changing values" — it doesn't reference the model).
Prisma's `@updatedAt` on `Contact.updatedAt` (`schema.prisma:400`) only fires
when a query actually issues an UPDATE against that row; since no live sync
path ever does, `Contact.updatedAt` is frozen at whatever the one-time
backfill script set it to, forever, in real operation. This exactly confirms
plan-check gap #7: staleness gated on `Contact.updatedAt` (scope decision #8,
spec `Approach §B.7`/AC22) would never advance and the warning would either
never fire, or fire permanently and uselessly, depending on the backfill
timestamp vs. `AI_DRAFT_STALENESS_HOURS`.

**Proposed smallest correct fix:** make `syncMembers` always `update()` (not
conditionally) the Contact row's grounding fields on every successful members
sync for that room's contact — regardless of whether the scraped values
changed — using the exact same "always-write" idiom this file already uses
for `Room.lastSyncAt` (line 100: `lastSyncAt: new Date()` is set
unconditionally on every room upsert, proving the codebase already has this
exact convention available to copy). Concretely: resolve `Contact` by
`(orgId, currentRoomId: room.id)` (the existing `@@unique([orgId,
currentRoomId])`, `schema.prisma:406`) inside `syncMembers`, and `update()` it
with the same `rating`/`financialStatus`/`balanceCents` fields already being
written to `Member` in that same call, so `Contact.updatedAt` becomes a true
"last successfully synced" timestamp via Prisma's own `@updatedAt` directive
— no new field needed. **This is the correct minimal fix**, not a workaround:
it makes the field's ambient guarantee (`@updatedAt` = "last write to this
row") actually hold in production, and it is consistent with the AI-draft
grounding context (spec `Approach §B.3`) already reading `Contact.balanceCents
/financialStatus/rating` — those same fields need to flow from `Member` sync
into `Contact` for the AI draft to ever be grounded on live data in the first
place, which today it structurally cannot be (Contact is never touched by any
live code path, so the AI drafting pipeline in §B would be grounding on
backfill-frozen data even before considering staleness at all — this is
actually a second, deeper instance of the SAME "never live-written" class of
bug as plan-check gap #1). Note: `syncMembers` currently has no notion of "one
Contact per Member/Room" write path at all — this fix requires adding it, and
should reuse the room-resolution the function already does (lines 288-312)
rather than re-deriving it.

**Alternative if Oga prefers not to touch `Contact` writes in this slice:**
there is no better existing field to key staleness on instead — `Member`
itself has no analogous "last synced" timestamp (`schema.prisma` `Member`
model has no `updatedAt`/`lastSyncAt`), so if `Contact` writes are ruled out
of scope, the correct fallback is to add `Room.lastSyncAt` (already exists,
line 100, and is unconditionally maintained) as the staleness anchor instead
of `Contact.updatedAt`, joining `Contact.currentRoomId → Room.lastSyncAt` at
read time. But this is a materially worse fit conceptually (it measures "was
this room synced," not "is the contact's balance/rating data fresh"), so the
recommended fix is the direct one above.

---

## Q2 — Conversation race (gap #3): Prisma version + upsert race-safety

**Installed version, confirmed two ways:**
- `web/package.json`: `"@prisma/adapter-pg": "^7.8.0"`, `"@prisma/client":
  "^7.8.0"`, `"prisma": "^7.8.0"`.
- `npm ls prisma @prisma/client` (resolved tree): `@prisma/client@7.8.0` /
  `prisma@7.8.0` deduped, exact, both at the top-level `web` workspace and
  inside `better-auth`'s bundled `@better-auth/prisma-adapter`.

**Is `tx.conversation.upsert({where: {contactId_channel: {...}}, create,
update: {}})` the correct native-upsert replacement?**

Confirmed via Prisma's own docs (`prisma.io/docs/orm/reference/prisma-client-reference`,
"Database upsert query criteria" section, fetched directly):

> "Prisma Client uses a database upsert if: there are no nested queries in the
> upsert's `create` and `update` options — the query modifies only one model —
> **there is only one unique field in the `upsert`'s `where` option** — the
> unique field in the `where` option and the unique field in the `create`
> option have the same value."
>
> "To use a database upsert, Prisma Client sends the SQL construction
> `INSERT ... ON CONFLICT SET .. WHERE` to the database."

And confirmed a composite `@@unique` counts as ONE unique field for this
purpose (not two), which is exactly our `Conversation` shape
(`@@unique([contactId, channel])`, `schema.prisma:441`): a composite
constraint used as a single named `where` key (e.g.
`where: { contactId_channel: { contactId, channel } }`) is treated as one
unit — this is the standard, documented Prisma pattern for composite unique
keys, and matches Prisma's own worked example for compound-key upserts
(`prisma.io/docs/orm/prisma-client/special-fields-and-types/working-with-composite-ids-and-constraints`).

So: **yes, `tx.conversation.upsert({where: {contactId_channel: {contactId,
channel}}, create: {...}, update: {}})` qualifies for Prisma's native
Postgres upsert** (single model, no nested writes, one composite unique key,
`create.contactId`/`create.channel` match the `where` values) — it compiles
to `INSERT ... ON CONFLICT (contactId, channel) DO UPDATE SET ...` (or `DO
NOTHING`-equivalent when `update: {}}`, see caveat below), executed as one
atomic Postgres statement instead of Prisma's own
`findFirst`-then-conditionally-`create` client-side round-trip. This
structurally eliminates the P2002 path the current spec's `findFirst`+`create`
+catch pattern relies on, and it works fine emitted from inside an
`db.$transaction(async tx => {...})` interactive transaction — nothing in
Prisma's transaction docs restricts native upserts to non-transactional
contexts, and this repo's own `syncRooms`/`syncMembers` code already calls
`client.property.upsert(...)` and `client.room.upsert(...)` (non-transactional,
via `forOrg()`) using this exact single-composite-key upsert shape
successfully today (route.ts:63-74, 88-102) — proving the pattern already
works against this schema and this Prisma version in this codebase.

**Known caveat — confirmed real, current, version-adjacent, NOT resolved.**
Prisma's own docs, quoted directly (same reference page, "Database upserts"
section):

> "If two or more upsert operations happen at the same time and the record
> doesn't already exist, then a race condition might happen. As a result, one
> or more of the upsert operations might throw a unique key constraint
> error... Handle the P2002 error in your application code. When it occurs,
> retry the upsert operation to update the row."

This is **not a stale/pre-native-upsert-era caveat** — it is documented as
still applying to the current native-upsert (`ON CONFLICT`) implementation,
and is corroborated by two OPEN GitHub issues against `prisma/prisma`,
confirmed via `gh issue view` (both fetched directly, both still `state: OPEN`
as of their last update, Oct 2025 — i.e. not closed/superseded going into
2026-07-03):

- **`prisma/prisma#25967`** ("Unique constraint failed on field when using
  native DB upsert," opened 2025-01-02, still open, last activity
  2025-10-07). A Prisma maintainer/contributor (`wmadden`, association:
  `contributor`) confirmed it directly in a comment: *"Thanks for the report,
  we have enough information to reproduce this and we'll tackle it as soon as
  we have capacity."* — i.e. Prisma itself has acknowledged this is a real,
  reproducible bug in native upsert, unfixed as of the last recorded
  maintainer comment.
- **`prisma/prisma#22778`** ("`upsert()` results in P2002," opened
  2024-01-23, still open, last activity 2025-10-07) — same symptom, reported
  independently against a single-field (non-composite) unique constraint on
  Postgres, confirming this isn't unique to composite keys.

One comment on `#22778` posts a concrete, working retry-wrapper pattern (a
Prisma Client `$extends` middleware that intercepts the `upsert` operation,
catches `P2002`, re-`findUnique`s, and falls back to `update`/returns the
existing row) — this matches Prisma's own documented recommendation
("handle P2002, retry") almost exactly, and is the shape to reach for **if**
Oga wants to fully close this edge case rather than accept the residual risk.

**Recommendation for the spec:** adopt the `tx.conversation.upsert(...)`
native-upsert replacement (this correctly eliminates the specific
`findFirst`-then-`create`-then-catch-P2002-inside-a-transaction bug the
Verifier flagged in gap #3 — no more transaction-aborting P2002 from THIS
call under the ordinary case), but the spec should **explicitly document the
residual extreme-concurrency TOCTOU risk as an accepted, named limitation**
(same treatment the spec already gives other known edge cases, e.g. §A.6's
duplicate-text dedup limitation) rather than silently claiming this is
airtight — a genuinely simultaneous double-sync race (two extension syncs
landing in the same instant, same contact+channel, both racing the initial
INSERT) can still, per Prisma's own docs and two open unresolved issues,
throw P2002 out of the upsert itself. Given this repo's existing convention
(every other write in this same transaction path already treats P2002 as a
"transaction-terminal no-op, log a warn, return" — see the `FLIP`/
`COLLECTIONS` task-create patterns in `route.ts` lines 140-165, 220-245,
446-461), the pragmatic and consistent fix is: wrap the `upsert` call itself
in the SAME try/catch-P2002-transaction-terminal-no-op convention already
used everywhere else in this file, rather than inventing a new retry-wrapper
mechanism for just this one call site. This closes gap #3's specific concern
(dropping message bubbles from a losing concurrent sync) because on P2002 the
sync can `return` cleanly from the transaction and the caller's outer
try/catch (already present, `route.ts:506-512`) logs and records the error —
matching the existing "log warn, no-op, don't lose the whole sync run"
philosophy — without introducing an un-audited retry loop this codebase
doesn't otherwise use.

---

## Q3 — Rate-limit mechanism (gap #6)

**Full grep, both `web/src` and `extension/`:**
```
grep -riE "cooldown|debounce|rateLimit|rate_limit|RATE_LIMIT|throttle" -r <repo>
```
Every hit inspected:
- `package-lock.json` (root and `web/`): `"perfect-debounce": "^2.1.0"` — a
  **transitive npm dependency** (pulled in by some other package, not
  referenced by any app code; confirmed no `import`/`require` of
  `perfect-debounce` exists anywhere in `web/src` or `extension/`). Not a
  usable pattern — it's not even wired into the app.
- `web/.next/dev/server/chunks/...js`: `ASPNETCORE_RATE_LIMITING_RESULT_VALUE_*`
  constants — these are **Next.js's own bundled internal build artifacts**
  (unrelated ASP.NET-Core-named constants baked into a vendor chunk, likely
  from a bundled dependency's cross-platform string table). Not app code, not
  a rate-limit mechanism this app defines or uses.

**No hits at all** in any file under `web/src/**` or `extension/**` (source
code, not build output).

**Answer: there is no existing debounce/cooldown/rate-limit pattern anywhere
in this codebase.** Slice 4 needs a NEW mechanism, and per Oga's own framing
(confirmed correct): an in-memory `Map`/module-level variable would silently
fail to debounce in a real multi-process deployment (Vercel serverless
functions each get their own isolated memory; even a single long-running
Node process restarting on deploy loses the state) — this is exactly the kind
of "passes a same-process unit test, breaks in the real deployed environment"
risk plan-check gap #6 named. **A DB-backed timestamp is the correct fix
class.** Concretely: add `Conversation.lastDraftRequestedAt DateTime?` (a new
nullable field, additive to schema — consistent with the spec's existing
"additive only" constraint in §D), and in `generateDraft`, read-then-check-
then-set it atomically. The atomic-check-and-set should use a single
conditional `updateMany` (not a separate read then write, which would itself
race under concurrent double-clicks) — e.g.:
```ts
const { count } = await db.conversation.updateMany({
  where: {
    id: conversationId,
    OR: [
      { lastDraftRequestedAt: null },
      { lastDraftRequestedAt: { lt: new Date(Date.now() - 30_000) } },
    ],
  },
  data: { lastDraftRequestedAt: new Date() },
})
if (count === 0) {
  // rate-limited: another request within the last 30s already claimed the slot
  return { rateLimited: true }
}
```
This is a single atomic UPDATE (Postgres row-level locking makes the
check-and-set race-free across processes/instances), needs no new table, and
matches this repo's existing idiom of using conditional `updateMany` +
`count` to detect "did I win the race" (already used identically for the FLIP
task close at `route.ts:176-197` and the COLLECTIONS task close at
`route.ts:479-502`) — so this is not a new pattern class for the codebase,
just a new field applying an existing idiom.

---

## Q4 — Cost-tracking on escalated/rejected drafts (gap #5)

**Schema/codebase grep for any existing cost/usage/audit table:**
```
grep -riE "costCents|tokenUsage|usageLog|auditLog|aiInputTokens|aiOutputTokens|aiCostCents|aiModel" -r <repo excl. node_modules>
```
**Zero hits anywhere** — not in `schema.prisma`, not in any `.ts` file. There
is no existing `AuditLog`/`UsageLog`/cost-tracking model or field in this
codebase today. The `aiInputTokens`/`aiOutputTokens`/`aiCostCents`/`aiModel`
fields referenced in the spec's own §D are net-new, proposed-but-not-yet-built
additions to `Message` — confirmed by reading the current `Message` model in
full (`schema.prisma:447-471`): it has `id, orgId, conversationId, contactId,
channel, direction, status, content, sourceId, senderLabel, isDraft,
aiDraftOfId, aiDrafts, sentAt, createdAt` — no cost/token/model fields exist
yet. This confirms scope decision #7's own framing is accurate as a
description of where cost data WOULD live (on Message, once §D ships) — the
gap is specifically that escalated/rejected drafts never reach the `Message`
row creation step (§B.6: "create NO Message row"), so a real, billed Claude
API call's cost has nowhere to land under the current design.

**Pino logging setup, confirmed via the run log and the live file:**
Per `~/Claude/loop/runs/2026-07-03_add-logging/run_log.md` (commits `5dbc87b`
+ `7ed0e56`, this session), and the actual file at
`web/src/lib/logger.ts`:
```
19	import pino from 'pino'
20	
21	export const logger = pino({
22	  level: process.env.LOG_LEVEL ?? 'info',
23	  base: { env: process.env.VERCEL_ENV ?? 'development' },
24	})
```
This is a plain, synchronous, stdout-only Pino instance — deliberately no
transport/worker-thread (the file's own header comment cites two confirmed
real GitHub issues, `vercel/next.js#86099` and `vercel/next.js#84766`, for why
transport breaks under this app's Next.js 16 + Turbopack stack). It's already
in live use throughout `route.ts` for exactly this kind of structured,
one-off event logging — e.g. `logger.warn({ orgId, roomId, taskType },
'sync/padsplit: ... lost a concurrent race (P2002) — no-op')` (multiple call
sites, e.g. lines 158-161, 193-196, 238-241, 454-457, 497-500) and
`logger.info({ orgId, page, synced, errorCount }, 'sync/padsplit: sync
completed')` (line 571). Structured fields (arbitrary JSON object as the
first arg) plus a message string is the established convention across this
codebase already — not a new pattern to introduce.

**Answer: yes, logging (not persisting) is the right call for this specific
case**, and it fits the existing convention exactly. For an escalated/safety-
rejected draft, `generateDraft` should call
`logger.info({ orgId, conversationId, aiModel, aiInputTokens, aiOutputTokens,
aiCostCents, reason: escalationReason }, 'ai/draft: escalated — Claude call
made but no draft persisted')` (or `.warn` if Oga wants it to stand out in
log-level filtering — either is defensible; `.info` matches the general
severity ops-clock/route.ts uses for "expected, not-a-bug, still worth
recording" events like the P2002 no-ops above, which are a closer behavioral
analogue than an actual error). This gives full cost/token visibility for
MVP_PLAN §7's stated per-draft-cost-tracking goal WITHOUT violating scope
decision #7's explicit "no separate cost-log DB table" constraint — a
structured log line is not a DB table, and Vercel automatically captures
stdout into Function Logs per the `logger.ts` header comment's own stated
rationale, so this data is not lost, just not queryable via SQL. If Oga later
wants aggregate cost reporting across escalated+non-escalated drafts, that
would need a log-drain/analytics pipeline (out of scope for this slice) or a
reversal of scope decision #7 — but for closing THIS specific plan-check gap
(a billed call with literally zero record of what it cost), a structured info
log at the point `generateDraft` learns of the escalation is the smallest
correct fix, consistent with the pattern precedent this session already
established and Verified (PASS) in the logging build.

---

## Sources (all opened directly, not snippet-only)

- `web/src/app/api/sync/padsplit/route.ts` — read in full (575 lines).
- `web/prisma/backfill_contacts.ts` — grepped for `contact.` call sites (line
  81 upsert, 259 findMany, 291 deleteMany).
- `web/prisma/schema.prisma` — `Contact` (385-409), `ContactInbox` (411-423),
  `Conversation` (425-445), `Message` (447-471) models read directly.
- `web/package.json` — read in full; `npm ls prisma @prisma/client` run
  directly against the installed tree (`7.8.0` exact, both packages).
- `web/src/lib/logger.ts` — read in full (25 lines).
- `~/Claude/loop/runs/2026-07-03_add-logging/run_log.md` — read in full
  (commits `5dbc87b`, `7ed0e56`).
- `~/Claude/loop/runs/2026-07-03_ai-draft-approve/plan_check_log.md` and
  `specs/spec.md` — read in full.
- Prisma docs, `prisma.io/docs/orm/reference/prisma-client-reference`
  (fetched directly via WebFetch) — "Database upsert query criteria" and
  "Database upserts" (race condition) sections quoted above.
- Prisma docs, `prisma.io/docs/orm/prisma-client/special-fields-and-types/working-with-composite-ids-and-constraints`
  (confirmed via WebSearch synthesis of the doc content — composite-key
  upsert pattern).
- `github.com/prisma/prisma` issue **#25967** — fetched directly via
  `gh issue view 25967 --repo prisma/prisma` (+ `--comments`), confirmed
  `state: OPEN`, `updatedAt: 2025-10-07`, maintainer-confirmed reproducible.
- `github.com/prisma/prisma` issue **#22778** — fetched directly via
  `gh issue view 22778 --repo prisma/prisma` (+ `--comments`), confirmed
  `state: OPEN`, `updatedAt: 2025-10-07`, includes a working retry-wrapper
  code sample in comments.
- `github.com/prisma/prisma` issue **#11038** — fetched directly via `gh
  issue view`; noted but flagged LOWER RELEVANCE — root cause is
  MySQL/Vitess-specific (`vttablet` connector error), not Postgres; used only
  as secondary corroboration that "upsert inside `$transaction` can still
  race," not as a Postgres-specific citation.
- `grep -riE "cooldown|debounce|rateLimit|rate_limit|RATE_LIMIT|throttle"`
  and `grep -riE "costCents|tokenUsage|usageLog|auditLog|aiInputTokens|..."`
  — run directly against `web/src`, `extension/`, `web/prisma/schema.prisma`,
  and (for completeness) the full repo tree with `node_modules` excluded from
  interpretation (the only hits were in `package-lock.json` metadata and
  `.next/dev` build output, both flagged as not-app-code above).

## Not found / could not verify
- Whether PadSplit's real communication-page DOM exposes a machine-readable
  `datetime`/`title` attribute on message timestamps — explicitly flagged as
  unverified in the spec itself (Context, "Open item requiring live
  verification"); out of scope for this Q1-Q4 dispatch and not re-attempted
  here (would require live browser access to a real logged-in PadSplit host
  account).
- No further open Prisma issues were found suggesting the native-upsert P2002
  race is FIXED as of `7.8.0` specifically (i.e. no changelog/release-note
  entry claiming resolution) — the two cited issues remain open with no
  merged-fix reference, which is the basis for treating the caveat as live,
  not historical.
