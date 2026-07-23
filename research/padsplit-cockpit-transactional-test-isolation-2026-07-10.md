# Domain brief: transactional test isolation for padsplit-cockpit's Vitest suite

**Mode:** D (domain research for a build). Researcher: read all source directly (no
sub-delegation). Date: 2026-07-10.

**Scope of the question:** Given `web/src/lib/db-rls.ts`'s `forOrg(orgId)` — which wraps
every query in `db.$transaction([setConfigCall, query])` (Prisma's array/batch form) and
whose own header comment says **"Never call `.$transaction()` on a `forOrg(...)` client"**
— will wrapping each TEST in an outer DB transaction (the whole mechanism both candidate
libraries use) collide with `forOrg()`'s own internal `.$transaction()` call? Concretely:
raw BEGIN/ROLLBACK vs Prisma `$transaction()` API, driver-adapter (`@prisma/adapter-pg`,
Prisma 7) compatibility, and whether a hand-rolled raw-SQL savepoint approach beats both
named libraries for this repo specifically.

---

## Q1 — How does each library actually implement the per-test transaction wrap?

**Answer:** Both use the **same core mechanism**: an outer Prisma **interactive**
`$transaction(async (tx) => {...})` call that never resolves until the test ends (then
throws/rejects to force a rollback), combined with a **Proxy** that intercepts any
`.$transaction()` call made by code-under-test **during** that window and converts it into
a raw-SQL **SAVEPOINT** via `$executeRawUnsafe` — NOT a nested Prisma `$transaction()` call
(Prisma doesn't support that; see Q3). Neither library uses a raw BEGIN/ROLLACK at the
pool/connection level for the *outer* wrap — both go through Prisma's own interactive
transaction API for that part.

**`vitest-environment-prisma-postgres` (codepunkt), `src/context.ts`** (fetched via GitHub
Blobs API, commit `9d8e9096`, matches npm-published tag `2.0.0`, confirmed by SHA match
between the `main` tree and the `2.0.0` git tag):

Outer wrap (`beginTestTransaction`):
```ts
const testTransactionPromise = originalClient.$transaction(
  testTransactionFn,
  options.transactionOptions,
);
```
Inner interception (comment is the library author's own explanation, quoted verbatim):
```ts
/**
 * Emulates Prisma's nested `$transaction` behavior inside an active interactive
 * transaction using PostgreSQL savepoints. ... To allow code-under-test to use
 * `$transaction` normally, we:
 *   1. Create a SAVEPOINT before running the nested transaction body
 *   2. Execute either the callback form or the array form
 *   3. On success: RELEASE the savepoint
 *   4. On error: ROLLBACK TO the savepoint and rethrow
 */
const fakeInnerTransactionMethod = async (arg) => {
  const tx = transactionClient!;
  const savePointId = `vitest_environment_prisma_postgres_${++savePointCounter}`;
  await tx.$executeRawUnsafe?.(`SAVEPOINT ${savePointId};`);
  const run = () => (Array.isArray(arg) ? Promise.all(arg) : arg(tx!));
  try {
    const result = await run();
    await tx.$executeRawUnsafe?.(`RELEASE SAVEPOINT ${savePointId};`);
    return result;
  } catch (err) {
    await tx.$executeRawUnsafe?.(`ROLLBACK TO SAVEPOINT ${savePointId};`);
    throw err;
  }
};
```
The README's own "Features" list states the explicit design goal that matches this repo's
exact risk: **"Tests run inside sandboxed transactions, but application-level transactions
still work normally."**

Source: https://github.com/codepunkt/vitest-environment-prisma-postgres/blob/main/src/context.ts (fetched raw, quoted above verbatim)
README: https://github.com/codepunkt/vitest-environment-prisma-postgres/blob/main/README.md

**`@chax-at/transactional-prisma-testing`, `src/prisma.testing.helper.ts`** (fetched via
GitHub Blobs API):

Outer wrap (`startNewTransaction`):
```ts
public async startNewTransaction(opts?): Promise<void> {
  ...
  return new Promise(resolve => {
    this.prismaClient.$transaction(async prisma => {
      this.currentPrismaTransactionClient = prisma as Prisma.TransactionClient | undefined;
      await new Promise(innerResolve => {
        this.endCurrentTransactionPromise = innerResolve;
        resolve();
      });
      // We intentionally want to do a rollback of the transaction after a succesful run
      throw internalRollbackErrorSymbol;
    }, opts).catch((error) => { if (error !== internalRollbackErrorSymbol) throw error; });
  });
}
```
Inner interception (array form — **this is the important difference from codepunkt, see
Q_risk below**):
```ts
private async transactionProxyFunction(args: unknown): Promise<unknown> {
  return this.wrapInSavepoint(async () => {
    if (Array.isArray(args)) {
      // "Regular" transaction - list of querys that must be awaited
      const ret = [];
      for (const query of args) {
        ret.push(await query);          // <-- sequential await, NOT Promise.all
      }
      return ret;
    } else if (typeof args === 'function') {
      return args(this.currentPrismaTransactionClient);   // interactive form
    } else {
      throw new Error('[transactional-prisma-testing] Invalid $transaction call...');
    }
  });
}

private async wrapInSavepoint<T>(func: () => Promise<T>): Promise<T> {
  ...
  await transactionClient.$executeRawUnsafe(`SAVEPOINT ${savepointName}`);
  return await this.asyncLocalStorage.run({ transactionSavepoint: savepointName }, func);
  // catch -> ROLLBACK TO SAVEPOINT ${savepointName}
}
```
Source: https://github.com/chax-at/transactional-prisma-testing/blob/main/src/prisma.testing.helper.ts (fetched raw, quoted above verbatim)

**Transfer-condition check (both libraries):** the mechanism requires (a) the app code
under test to be issuing all its Prisma calls through the library's **Proxy client**, not
the real `PrismaClient` instance directly, and (b) the app never establishing its own raw
connection/BEGIN outside Prisma. Both conditions are structurally enforced *if and only if*
the test setup correctly mocks the module the app imports its client from (see Q_risk/
constraints below) — this is an **instructional** dependency (a wiring mistake, e.g.
mocking the wrong module specifier, fails **silently**: the app code would just use the
real ambient `db` singleton, tests would pass functionally but writes would actually
commit). This is the single biggest operational risk and is flagged explicitly in
`constraints` below.

---

## Q2 — Prisma 7 / `@prisma/adapter-pg` driver-adapter support

**codepunkt/vitest-environment-prisma-postgres** — peerDependencies (fetched
`package.json` blob, `2.0.0`):
```json
"peerDependencies": {
  "@prisma/adapter-pg": ">=4 <8",
  "prisma": ">=4 <8",
  "vitest": ">=4.1 <5"
}
```
(Note: my first-pass WebFetch summary of the README claimed peer deps were pinned to
"prisma 7.x" — **that was wrong**; the real `package.json` range is `>=4 <8`, which
includes 7 but is much broader. Flagging this because it's exactly the kind of
secondhand-summary error the honesty bar exists to catch — I only trust the primary
source below.) The library's own `devDependencies`/CI use `prisma@7.2.0` and
`@prisma/adapter-pg@7.2.0`, and `src/context.ts` **constructs its own PrismaClient
internally** using the adapter:
```ts
const originalClient: PrismaClientLike = new PrismaClient({
  adapter: new PrismaPg({ connectionString: process.env.DATABASE_URL }),
  log: options.log,
});
```
So it is built and tested against the driver-adapter pattern specifically — but it also
means the library **duplicates** the app's own client-construction logic (its own
`PrismaPg` call, not padsplit-cockpit's `db.ts`), a real gap explained in constraints.

Known, **currently open** gap (confirmed by reading GitHub issue #22 and PR #32
directly): Prisma 7 added a NEW `prisma-client` generator that emits raw TypeScript
output; the library still loads the client via `createRequire(...)(options.clientPath)`
(CJS `require`), which cannot load `.ts` ESM output —
> "Error: Cannot find module './lib/generated/prisma/client.ts'" ... "This is
> incompatible with Prisma 7's new prisma-client generator, which outputs TypeScript
> files instead of compiled JavaScript."
> — https://github.com/codepunkt/vitest-environment-prisma-postgres/issues/22

A community PR (#32, "fix: use dynamic import() to load Prisma client (fixes #22)") was
opened April 2026 and **closed without being merged** (`"merged": false`) — the maintainer
never landed it, and the *current released source* (v2.0.0, verified above) still uses
`createRequire`. **This gap does NOT apply to padsplit-cockpit**, because
`web/prisma/schema.prisma` uses the **legacy** generator:
```
generator client {
  provider = "prisma-client-js"
}
```
(confirmed by reading the file directly at
`<HOME>/Claude/Projects/padsplit-cockpit/web/prisma/schema.prisma:1-2`), whose
output is loadable via plain `require('@prisma/client')`. Still worth recording because it
signals this project is young (created Nov 2025, 42 stars) and a real reported bug sat
unmerged for ~3 months — a maintenance-attentiveness flag, not a blocker today.

**@chax-at/transactional-prisma-testing** — CHANGELOG (fetched raw, full history):
```
## 1.5.0 - 2026-01-09
### Added
- Added support for Prisma 7
```
Confirmed via the source GitHub issue (#24, "Prisma 7", opened by the maintainer):
> "Prisma 7 has been released - there don't seem to be any breaking changes related to
> this package, but we have to upgrade one testing project and see if everything works
> with Prisma 7." — https://github.com/chax-at/transactional-prisma-testing/issues/24
and confirmed merged in PR #25/#26 (both `"merged": true`) — the fix was a pure
`peerDependencies`/lockfile bump (`"@prisma/client": "^4.7.0 || 5 || 6 || 7"`), **no code
change was needed**, because — unlike codepunkt — this library never constructs its own
`PrismaClient`. It takes an already-constructed client instance as a constructor argument
(`new PrismaTestingHelper(originalPrismaService)`), so **it is architecturally agnostic to
how you built that client** — driver adapter, connection string, whatever padsplit-cockpit's
own `db.ts` already does is untouched and reused as-is. The README even anticipates this
directly:
> "const originalPrismaService = new PrismaService(); // in newer prisma versions, you may
> have to pass an adapter here" — https://github.com/chax-at/transactional-prisma-testing#readme

Prisma 7 itself was released 2025-11-19 per Prisma's own changelog
(https://www.prisma.io/changelog/2025-11-19, "Rust-free Prisma Client becomes the
default"), so chax-at's Prisma-7 support (2026-01-09) trails release by ~7 weeks — a real,
if light-touch, confirmation window, not a same-day rubber-stamp.

**padsplit-cockpit's actual installed versions** (read directly from
`web/package.json`): `prisma@^7.8.0`, `@prisma/client@^7.8.0`, `@prisma/adapter-pg@^7.8.0`,
`vitest@^4.1.9`. Both libraries' peer-dep ranges are satisfied by these versions.

---

## Q3 — Does Prisma/Postgres actually support nesting `$transaction()` calls natively?

**No — this is an open, unimplemented Prisma feature request, not something either
library can lean on.** Confirmed directly:
> **Issue title:** "Support 'nested' transactions in interactive transactions"
> **State:** Open. Labels: `kind/feature`, `topic: interactiveTransactions`,
> `topic: nested transactions`, `topic: savepoint`. The OP explicitly asks for
> SAVEPOINT-based nesting "like Ecto" — i.e. exactly what both candidate libraries
> hand-roll themselves.
> — https://github.com/prisma/prisma/issues/15212

A real user's empirical report of what happens if you naively try to fake it yourself
(from a linked discussion):
> "When i tryed to use other things like `{...tx, $transaction: async (func) => func(tx)}`
> the transaction connection was closed."
> — https://github.com/prisma/prisma/discussions/12373

I additionally checked the **actual installed Prisma 7 type definitions** in this
repo (`<HOME>/Claude/Projects/padsplit-cockpit/node_modules/.prisma/client/index.d.ts:3129`
and `<HOME>/Claude/Projects/padsplit-cockpit/node_modules/@prisma/client/runtime/client.d.ts:467`):
```ts
export type TransactionClient = Omit<Prisma.DefaultPrismaClient, runtime.ITXClientDenyList>
declare const denylist: readonly ["$connect", "$disconnect", "$on", "$use", "$extends"];
```
`$transaction` is **not** in the denylist — so the interactive-transaction client (`tx`)
still *types* `.$transaction` as present. I could **not** find (nor could I locate in the
minified runtime bundle) the exact runtime code path that fires if you call `tx.$transaction(...)`
directly with no library involved — I'm flagging this specific point as **not fully
confirmed by source**, only by the empirical community report above ("connection was
closed"). Practical conclusion either way: relying on Prisma's native behavior for nesting
is not a documented, supported path — this is exactly *why* both libraries exist and both
implement raw-SQL `SAVEPOINT`/`RELEASE SAVEPOINT`/`ROLLBACK TO SAVEPOINT` themselves rather
than calling Prisma's `$transaction()` a second time.

---

## Q_risk — the specific ordering hazard for `forOrg()`'s exact pattern (this is the finding I'd weight most heavily)

`forOrg()`'s `$allOperations` handler does:
```ts
const [, result] = await db.$transaction([
  db.$executeRaw`SELECT set_config('app.org_id', ${orgId}, TRUE)`,
  query(args),
])
```
(`web/src/lib/db-rls.ts:42-45`, read directly). Correctness depends on the `set_config`
call **completing before** the RLS-governed query executes on the *same physical
connection* — that's the entire point of `SET LOCAL`-scoped GUCs.

- **chax-at's array-form handling explicitly preserves this ordering**: it `await`s each
  array element **one at a time, in a `for` loop**, before starting the next —
  `for (const query of args) { ret.push(await query) }`. This guarantees the
  `set_config` call fully resolves before `query(args)` is even invoked.
- **codepunkt's array-form handling uses `Promise.all(arg)`** — it fires `.then()` on
  both array elements without awaiting the first before starting the second. I could
  **not find a test in codepunkt's own suite that exercises this ordering** against a
  real Postgres instance — `src/contest.test.ts`'s only array-form test
  (`'nested $transaction uses SAVEPOINT/RELEASE on success'`) uses a **stubbed** client
  (`test/prisma-client-stub.js`) and plain `Promise.resolve(1), Promise.resolve(2)`
  values, which proves the SAVEPOINT/RELEASE calls happen, but proves **nothing** about
  statement-level ordering against a real connection. My own reasoning (not sourced,
  flagged as reasoning not fact): because both array elements are PrismaPromises bound to
  the *same* single reserved connection (`tx`), and a single Postgres connection can only
  process one statement at a time, dispatch order likely still determines DB-side
  execution order in practice — but this is inference from general Postgres/driver
  behavior, not something the library's own tests or docs confirm for this specific
  pattern.

**Practical recommendation:** given padsplit-cockpit's RLS mechanism is
security-load-bearing and depends on this exact ordering, **prefer chax-at's
sequential-await implementation** over codepunkt's `Promise.all`, and — regardless of
which library is adopted — the build's acceptance criteria should include a real
Postgres integration test that specifically exercises `forOrg()` under the chosen
wrapper and asserts RLS still denies cross-org rows (i.e., re-run something like the
existing `tests/rls-isolation.test.ts` AC1/AC2 assertions *through* the transactional
wrapper before trusting it), not just take either library's own test suite as proof.

---

## Q4 — Is a hand-rolled raw BEGIN/ROLLBACK approach simpler/more robust?

**No — recommend against it.** Two distinct hand-roll options exist, and both are worse
than adopting chax-at:

1. **Naive: call `db.$executeRawUnsafe('BEGIN')` / `('ROLLBACK')` directly on the app's
   pooled/adapter-backed client in `beforeEach`/`afterEach`.** This is **unsafe** with a
   connection-pooled driver adapter (`@prisma/adapter-pg` wraps a `pg.Pool`): each
   `$executeRawUnsafe` call may be routed to **any** available connection in the pool, not
   necessarily the same one on the next call. `BEGIN` on connection A does nothing for a
   subsequent query that lands on connection B — you would not reliably be "in a
   transaction" at all. Prisma's own interactive `$transaction()` API exists specifically
   to reserve one physical connection for the callback's duration; that's why both
   candidate libraries build on top of it rather than raw BEGIN/ROLLBACK. (This reasoning
   follows directly from Prisma's documented driver-adapter/interactive-transaction model;
   I did not find a doc page stating this failure mode in so many words, so flagging as
   inference from documented connection-pooling behavior, not a directly-quoted source.)
2. **More careful: reserve a single raw `pg.Client` yourself, `BEGIN` on it, construct a
   `PrismaPg` adapter bound to exactly that one client/connection for the test, `ROLLBACK`
   after.** This sidesteps the pooling hazard, but you would **still** need the exact
   SAVEPOINT-interception Proxy pattern (Q1/Q3) to handle `forOrg()`'s own
   `.$transaction()` call — i.e. you'd end up re-implementing ~90% of
   `chax-at`'s `wrapInSavepoint`/`transactionProxyFunction`/Proxy machinery yourself, with
   none of its multi-year bug history (see Q5) and no existing test coverage.

Given the actual complexity is in the **nested-transaction interception**, not the
outer BEGIN/ROLLBACK, hand-rolling buys no meaningful simplification here — it trades a
small, already-hardened dependency for an unverified equivalent amount of new code.

---

## Q5 — Which library, concretely, for this repo? (synthesis, not just Q1-Q4 recap)

**Recommendation: `@chax-at/transactional-prisma-testing`.** Reasons, all grounded above
plus two repo-specific facts discovered while reading padsplit-cockpit's own test file:

1. **Ordering correctness** (Q_risk): sequential `for`-loop await vs. `Promise.all` is a
   direct, sourced difference and chax-at's is the safer match for `forOrg()`'s
   `[setConfig, query]` pattern.
2. **No duplicated client construction**: chax-at takes your already-built `PrismaClient`
   (adapter and all); codepunkt builds its own internally via `clientPath` +
   `new PrismaPg({...})`, which is a second place the driver-adapter config could drift
   from `web/src/lib/db.ts`'s own construction (`db.ts:15` passes
   `new PrismaPg(connectionString)` — a positional string — while codepunkt's own internal
   call uses `new PrismaPg({ connectionString: ... })` — an object; I did not verify
   whether both forms are valid for `@prisma/adapter-pg@7.8.0`'s constructor, since this
   only matters for codepunkt's *own* internally-constructed client, which chax-at avoids
   needing entirely).
3. **`$extends()` compatibility has actual multi-year track record**: chax-at's own
   CHANGELOG shows *specific, fixed* bugs directly relevant to `forOrg()`'s
   `db.$extends({...})` usage — issue #10 "Passing an extended PrismaClient breaks
   PrismaTestingHelper type" (fixed 1.2.0, "Relaxed typing requirement... so that extended
   Prisma clients work as well"), issue #14 "`$queryRaw` throws a TypeError when a Prisma
   Client extension that overrides `$transaction` is used" (fixed 1.2.2), issue #17
   "`Prisma.getExtensionContext` return undefined" with extended clients (fixed 1.3.1).
   codepunkt's project (created 2025-11-27, 42 stars) has no equivalent issue history yet
   for `$extends()`-based clients specifically.
   Source: https://github.com/chax-at/transactional-prisma-testing/blob/main/CHANGELOG.md
4. **Repo-specific architecture fact (found by reading padsplit-cockpit's own test file,
   `web/tests/rls-isolation.test.ts:58-73`):** this repo's existing RLS tests already use
   a **second, independently-connected** Prisma client — `ownerDb`, built from
   `DATABASE_URL_OWNER` (a different Postgres role) — for fixture writes, entirely
   separate from the app-path `db` (`DATABASE_URL`/app_user). `chax-at`'s
   `PrismaTestingHelper` is a plain class you can instantiate **twice** (once per
   connection/role) inside one setup file — a natural fit for wrapping *both* connections
   in their own outer transaction+rollback and eliminating this file's manual
   `TEMP_ORG_IDS` / `teardownAllTempOrgs()` (`rls-isolation.test.ts:98-173`) bookkeeping
   entirely. codepunkt's package is a Vitest **environment** built around one global
   `prismaPostgresTestContext` singleton tied to one `DATABASE_URL` — it does not
   naturally extend to a second, differently-rolled connection without real
   customization.
5. **Recency trade-off, stated honestly**: chax-at's last push was 2026-01-09 (the
   Prisma-7 support release) — about 6 months stale as of today (2026-07-10), vs.
   codepunkt pushed 2 days ago. chax-at is more mature (created 2022, 66 commits, 17+
   releases, 52 stars, 0 open issues) rather than more actively developed right now.
   Neither is `archived`; both MIT-licensed.

---

## Q5b — Vitest `pool: 'threads'` / `maxWorkers: 1` / parallel workers

**Confirmed as moot for this repo, exactly as suspected, plus one extra nuance.**
`web/vitest.config.ts:88-89` (read directly): `pool: 'threads'`, `maxWorkers: 1`.

- **codepunkt**: README, "Known limitations" (quoted verbatim):
  > "Support for Vitest pools set to `vmThreads` [...] is not implemented. This
  > environment assumes that tests inside a single worker run one at a time: Do not use
  > `test.concurrent`... Keep `maxConcurrency` at `1`."
  This matches this repo's current config exactly (single worker, one test at a time).
- **chax-at**: README states it "allows parallel test execution against the same
  database," backed by an internal `AsyncLocalStorage` + a `transactionLock`
  (`acquireTransactionLock`, quoted in Q1 source) that serializes concurrent
  `startNewTransaction`/query calls **within one process**. This is a genuine additional
  capability beyond what this repo currently needs (`maxWorkers: 1`) — not a compatibility
  requirement, just headroom if the repo ever loosens that constraint. Neither library's
  docs make a claim about safety *across* separate worker **processes** sharing one
  Postgres connection (they don't need to — each worker/thread would hold its own
  independent helper instance and its own independent outer transaction, which is safe by
  construction, not by a claim I need to verify).

---

## `code_pattern` — what padsplit-cockpit's test setup would concretely look like

This combines two things I verified independently (not copy-pasted from one existing
example, since I could not find a published chax-at + Vitest + `@prisma/adapter-pg`
walkthrough): chax-at's documented public API (`PrismaTestingHelper` constructor,
`getProxyClient()`, `startNewTransaction()`, `rollbackCurrentTransaction()` — all quoted
directly from its README/source above) and Vitest's `vi.hoisted()` mechanism (needed
because `vi.mock()` factories are hoisted above other top-level statements — this is the
same pattern codepunkt's own `src/contest.test.ts` uses for its `PrismaPgMock`, quoted in
Q1's source fetch).

```ts
// web/tests/setup/transactional-db.ts
// New setupFiles entry (append to vitest.config.ts's `setupFiles` array, which
// currently is just ['dotenv/config'] — see web/vitest.config.ts:87).

import { afterEach, beforeEach, vi } from 'vitest'

// vi.mock factories below are hoisted above this file's other statements by
// Vitest, so anything they close over must itself be created inside vi.hoisted().
const { appHelper, ownerHelper } = vi.hoisted(() => {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { PrismaClient } = require('@prisma/client')
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { PrismaPg } = require('@prisma/adapter-pg')
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const { PrismaTestingHelper } = require('@chax-at/transactional-prisma-testing')

  // Mirrors web/src/lib/db.ts's own adapter construction (DATABASE_URL, app_user role).
  const appClient = new PrismaClient({ adapter: new PrismaPg(process.env.DATABASE_URL) })
  // Mirrors web/tests/rls-isolation.test.ts's ownerDb (DATABASE_URL_OWNER, owner role) —
  // wrapping BOTH connections is what lets teardownAllTempOrgs()/TEMP_ORG_IDS go away.
  const ownerClient = new PrismaClient({
    adapter: new PrismaPg(process.env.DATABASE_URL_OWNER ?? process.env.DATABASE_URL),
  })

  return {
    appHelper: new PrismaTestingHelper(appClient),
    ownerHelper: new PrismaTestingHelper(ownerClient),
  }
})

// Replace web/src/lib/db's exported `db` with the transaction-scoped proxy client.
// getProxyClient() returns a STABLE reference (per chax-at's own docs: "you can
// save and cache this reference, all calls will always be executed inside the
// newest transaction") — no getter/indirection needed.
vi.mock('../../src/lib/db', () => ({ db: appHelper.getProxyClient() }))

// Any test file that currently does `getOwnerDb()` / `new PrismaClient({ adapter:
// new PrismaPg(process.env.DATABASE_URL_OWNER) })` inline (as rls-isolation.test.ts
// does today) should instead import this proxy so its writes roll back too.
export const ownerDb = ownerHelper.getProxyClient()

beforeEach(async () => {
  await appHelper.startNewTransaction()
  await ownerHelper.startNewTransaction()
})

afterEach(() => {
  appHelper.rollbackCurrentTransaction()
  ownerHelper.rollbackCurrentTransaction()
})
```

`forOrg()` itself (`web/src/lib/db-rls.ts`) needs **no code change** — it still does
`import { db } from './db'` and calls `db.$transaction([...])`; under this setup, `db` IS
`appHelper.getProxyClient()`, so that `$transaction()` call is transparently intercepted
and turned into a `SAVEPOINT`/`RELEASE SAVEPOINT` pair inside the outer per-test
transaction, exactly as documented in Q1.

**What existing test files change:** `web/tests/rls-isolation.test.ts`'s `getOwnerDb()` /
manual `TEMP_ORG_IDS` + `teardownAllTempOrgs()` machinery (`rls-isolation.test.ts:62-73,
98-173`) becomes unnecessary if that file is migrated to import `ownerDb` from the new
setup file instead of building its own `PrismaClient` — but that migration is itself a
real, separate piece of build work (touching an existing, currently-passing spec-pinned
test file), not something to do silently as a side effect of adding the library.

---

## `constraints`

- **Wiring correctness is instructional, not structural, and fails silently.** The entire
  isolation guarantee depends on `vi.mock('../../src/lib/db', ...)` targeting the *exact*
  module specifier every consumer imports (`db-rls.ts` does `import { db } from './db'`;
  any test or app file importing via a different path/alias — e.g. `@/lib/db` vs a
  relative path — would resolve to the **real, unmocked** singleton, and writes would
  actually commit with no error, no red test, nothing that surfaces as a failure). Confirm
  the mock specifier matches `web/tsconfig.json`'s `@/*` alias resolution exactly (this
  repo's `vitest.config.ts:72` aliases `'@'` to `./src`), and add a guard test if possible
  (e.g., assert `db === appHelper.getProxyClient()` at the top of a canary test) rather
  than trusting the wiring silently.
- **Both `DATABASE_URL` (app_user) and `DATABASE_URL_OWNER` (owner role) connections need
  wrapping**, or only half of each test's writes roll back (see Q5 point 4 and the
  code_pattern above). This is specific to padsplit-cockpit's existing two-role test
  architecture, not a generic library constraint.
- **`forOrg()`'s own doc comment** (`db-rls.ts:16-18`) names an *existing* sanctioned
  pattern for real multi-statement org-scoped transactions ("the D6 pattern... use
  `db.$transaction(async (tx) => {...})`") — that pattern, if exercised by any test, would
  ALSO route through the same SAVEPOINT interception described in Q1 (the **callback**
  form, `arg(this.currentPrismaTransactionClient)` in chax-at's source) — this should be
  covered by at least one test once the library is adopted, since it's a different code
  path (interactive form) than `forOrg()`'s own array-form usage.
  Note: 'contact.create', 'conversation.create' etc. via TypeScript's `as any` casts in
  `rls-isolation.test.ts` (e.g. line 124, 133, 143) suggest the Prisma client's generated
  types may currently lag the schema for some models — unrelated to test isolation, but
  worth the Coder knowing before assuming full type coverage.
- **Peer-dep ranges are satisfied** by padsplit-cockpit's installed
  `prisma@^7.8.0`/`@prisma/client@^7.8.0`/`@prisma/adapter-pg@^7.8.0`/`vitest@^4.1.9` for
  both libraries (chax-at: `@prisma/client: ^4.7.0 || 5 || 6 || 7`; codepunkt:
  `prisma`/`@prisma/adapter-pg`: `>=4 <8`, `vitest: >=4.1 <5`).
- **Fluent API is unsupported by chax-at** ("Fluent API is not supported" — README). I did
  not find any use of Prisma's fluent chained-relation-query API
  (`prisma.user.findUnique(...).posts()`) in `db-rls.ts` or `rls-isolation.test.ts`, but
  this should be grepped across `web/src` before adoption, since it's a silent-breakage
  risk category, not a loud error, per chax-at's own caveat.
- **Sequences/auto-increment IDs are not reset on rollback** (chax-at README) — moot here
  since `padsplit-cockpit`'s schema uses `@id @default(cuid())` (confirmed,
  `schema.prisma:12`), not auto-increment integers.
- **`@default(now())` timestamps freeze to transaction-start time** (chax-at README
  caveat) — worth flagging if any test asserts strict `createdAt` ordering between rows
  created in the same test.

---

## `not_found`

- **No source (library test suite, docs, or issue) directly confirms real-Postgres,
  connection-level statement ordering for codepunkt's array-form `Promise.all(arg)`
  savepoint path.** I read the actual test (`src/contest.test.ts`, "nested $transaction
  uses SAVEPOINT/RELEASE on success") and it uses a **stubbed** client, not a real
  Postgres connection, and generic `Promise.resolve()` values, not two dependent
  raw/model calls. My statement in Q_risk that ordering "likely still holds in practice"
  is my own reasoning from single-connection FIFO semantics, not a verified fact — flagged
  as such there, not stated as confirmed.
- **Could not confirm at the Prisma engine/runtime level what literally happens if
  `tx.$transaction(...)` is called with no library involved** (throw vs. silent
  new-connection vs. hang). I found the TypeScript type still exposes `.$transaction` on
  `TransactionClient` (verified directly in this repo's installed
  `node_modules/@prisma/client/runtime/client.d.ts:467` and
  `node_modules/.prisma/client/index.d.ts:3129`), and one empirical community report
  ("the transaction connection was closed" — Prisma discussion #12373) but no
  authoritative Prisma doc page or changelog entry stating the exact runtime behavior.
  This is moot for the actual recommendation (neither library relies on this path; both
  intercept before Prisma's real `$transaction` ever fires) but I want to name the gap
  rather than imply I traced it to the engine source.
  the exact `PrismaPg` constructor call in `web/src/lib/db.ts:15`
  (`new PrismaPg(connectionString)`, positional string) is a valid, currently-working call
  in production — I did not independently verify `@prisma/adapter-pg@7.8.0`'s exact
  constructor signature/overloads (whether it accepts both a bare string and a config
  object), since this is existing, presumably-already-working app code and outside this
  research's scope; it only becomes relevant if the Coder copies codepunkt's *object-form*
  call (`new PrismaPg({ connectionString: ... })`) verbatim without checking which form
  this app already uses elsewhere.
- **No third real-world example combining chax-at + Vitest + `@prisma/adapter-pg`** was
  found published anywhere (chax-at's own README examples are Jest/NestJS-flavored,
  predating the driver-adapter pattern, with only a one-line aside acknowledging adapters
  might be needed "in newer prisma versions"). The `code_pattern` above is my own
  construction from chax-at's documented API + Vitest's documented `vi.hoisted()`
  mechanism — each piece is sourced, but the combination itself is unverified against a
  real running test until the Coder actually runs it.

---

## Sources (all opened directly, not summarized from search snippets alone)

- https://github.com/codepunkt/vitest-environment-prisma-postgres (tree, tags, README, `src/context.ts`, `src/index.ts`, `src/setup.ts`, `src/contest.test.ts`, `package.json` — all fetched via GitHub Blobs/Trees API and decoded)
- https://github.com/codepunkt/vitest-environment-prisma-postgres/issues/22 and /pull/32 (open issue + closed-unmerged fix PR)
- https://registry.npmjs.org/vitest-environment-prisma-postgres (dist-tags, versions, publish date)
- https://github.com/chax-at/transactional-prisma-testing (tree, README, CHANGELOG, `src/prisma.testing.helper.ts` — fetched via GitHub Blobs API and decoded)
- https://github.com/chax-at/transactional-prisma-testing/issues/24, /pull/25, /pull/26 (Prisma 7 support, confirmed merged)
- https://registry.npmjs.org/@chax-at/transactional-prisma-testing (dist-tags, versions, peerDependencies of latest)
- https://github.com/prisma/prisma/issues/15212 ("Support 'nested' transactions in interactive transactions" — open feature request)
- https://github.com/prisma/prisma/discussions/12373 (empirical report of naive-nesting failure)
- https://www.prisma.io/changelog/2025-11-19 (Prisma 7.0.0 release date/notes)
- Local repo files read directly: `<HOME>/Claude/Projects/padsplit-cockpit/web/src/lib/db-rls.ts`, `web/src/lib/db.ts`, `web/prisma/schema.prisma`, `web/package.json`, `web/vitest.config.ts`, `web/tests/rls-isolation.test.ts`, `node_modules/.prisma/client/index.d.ts`, `node_modules/@prisma/client/runtime/client.d.ts`

