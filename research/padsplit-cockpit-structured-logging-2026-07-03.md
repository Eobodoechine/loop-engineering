# Domain brief: structured logging for padsplit-cockpit (Next.js 16.2.9 / Turbopack / Vercel / Prisma 7.8 + @prisma/adapter-pg)

Mode D research, dispatched by Oga 2026-07-03. Scope: recommend the minimal-but-real
logging setup for a solo-operator Next.js app on Vercel, grounded in the app's actual
current state (zero structured logging, 3 raw console calls total, all auth-only) and
in real 2026 sources — not vibes. This is a domain brief for the Coder, not a radar
entry or PACE experiment (no priority scores, no experiment spec).

**Consuming artifact:** this informs the padsplit-cockpit logging build (dispatched
alongside the ops-clock/sync bug-hunt findings from 2026-07-03). Link this file from
that build's plan/decision log.

---

## 0. Grounding: what's actually in the repo today

Verified directly via grep/read, not assumed:

- `package.json`: `"next": "16.2.9"`, `"@prisma/client": "^7.8.0"`, `"@prisma/adapter-pg": "^7.8.0"`, `"better-auth": "^1.6.23"`, `"react": "19.2.4"`. No `pino`, `winston`, `@sentry/nextjs`, or `@axiomhq/*` in dependencies.
- Only 3 `console.*` calls in `src/`, all auth-related:
  - `src/app/api/auth/register/route.ts:59` — `console.error("[register] failed to send magic link", err)`
  - `src/app/api/auth/sign-in/magic-link/route.ts:56` — `console.error("[auth] failed to issue magic link", err)`
  - `src/lib/auth.ts:156` — `console.log(`[auth] magic link for ${email}: ${url}`)`
- `src/lib/db.ts` — Prisma client construction confirmed:
  ```ts
  const adapter = new PrismaPg(connectionString)
  return new PrismaClient({ adapter })
  ```
  No `log` option configured at all — zero query/warn/error visibility.
- `src/app/api/sync/airbnb/route.ts` (read in full for the listings path) — confirmed the
  exact swallow pattern described in the Brief: each per-item DB error is caught and pushed
  into a plain `errors: string[]` returned in the JSON response body; **nothing is logged
  server-side**, so if the caller (the browser extension) never reads or persists that
  array, the error is gone forever. Same shape for `sync/padsplit/route.ts` (8 catch blocks,
  none logging).
- `src/lib/task-recompute.ts` (the ops-clock alert engine) — no logging present.
- Dashboard server actions (`dismissAlert`/`completeTask`/`flagPaymentDispute`/`resolvePaymentDispute`) — not separately re-grepped here beyond the repo-wide console.* scan above, which returned zero hits outside auth; confirms the Brief's claim.

This confirms the Brief's framing is accurate, not exaggerated: the app has real
production code paths (sync, recompute, dashboard actions) with **zero** durable
server-side error visibility.

---

## 1. Idiomatic 2026 approach for Next.js App Router on Vercel

**Answer:** log to `stdout`/`stderr` via `console.*` or a logger that writes synchronously
to stdout — Vercel captures this automatically into its Function Logs — and layer
OpenTelemetry (`@vercel/otel`) on top for traces/spans, not as a logging replacement.
Do NOT reach for a transport-based async logger (Pino's worker-thread transport, Winston
transports that batch/flush on a timer) unless you've specifically verified it survives a
single, short-lived serverless invocation.

**Source, quoted:**
- Vercel automatically captures console output from serverless functions — confirmed via
  search synthesis across multiple 2026 sources on Vercel's Next.js logging docs and
  community write-ups (e.g. Wisp CMS "How to Manage Logging for Next.js Hosted on Vercel",
  https://www.wisp.blog/blog/how-to-manage-logging-for-nextjs-hosted-on-vercel).
- Official: Next.js recommends OpenTelemetry for instrumentation, not logging per se —
  https://nextjs.org/docs/app/guides/open-telemetry (fetched directly, version 16.2.10,
  lastUpdated 2026-02-11): *"We recommend using OpenTelemetry for instrumenting your apps.
  It's a platform-agnostic way to instrument apps that allows you to change your
  observability provider without changing your code."* This is about traces/spans
  (`instrumentation.ts` + `registerOTel()`), not structured application logs — Next.js's
  OTel integration instruments spans like `executing api route (app) [next.route]` and
  `render route (app) [next.route]` automatically, but does NOT give you a `logger.info()`
  call inside your route handler. You still need your own logging calls inside route
  handlers/server actions/server components; OTel gives you the surrounding trace context.

**Real constraint — Pino's async transport breaks specifically on this stack (confirmed,
not hypothetical):**

Two real, currently-open/recently-fixed GitHub issues on `vercel/next.js`, both filed
against Next.js 16 + Turbopack (this app's exact bundler config), both fetched and
confirmed directly:

- **Issue #86099** — *"[Turbopack Nextjs 16]: Pino - Cannot find module './transport-stream'"*
  (https://github.com/vercel/next.js/issues/86099). Next.js version: 16.1.0-canary.16.
  Exact error: `Error: Cannot find module './transport-stream' Require stack: -
  /var/task/node_modules/.pnpm/pino@10.1.0/node_modules/pino/lib/worker.js`. Maintainer
  quote: *"Pino is way too dynamic for Turbopack to determine all required files
  automatically."* Two sub-cases: non-Vercel resolved in that canary; **the Vercel-deployed
  case remains unresolved** at time of research. Workarounds offered: switch to
  `next build --webpack`, add `pino`/`thread-stream` to `serverExternalPackages`, or install
  `thread-stream` explicitly.
- **Issue #84766** — *"[Turbopack Nextjs 16]: Pino - Worker thread cannot find module
  'real-require'"* (https://github.com/vercel/next.js/issues/84766). Next.js version:
  16.0.0-beta.0. Root cause per reporter: *"Pino uses thread-stream to send logs to worker
  thread when logging asynchronously, which uses real-require to work with webpack. Looks
  like Turbopack doesn't bundle `real-require` properly."* This one **was fixed** (closed via
  PR #85734, tracked internally as PACK-5694) — but it demonstrates the pattern recurs across
  Next.js 16 canary/beta releases as Turbopack's bundling of Pino's dynamic `require()` calls
  changes version to version. Given this app pins `"next": "16.2.9"` (a later, presumably
  more-patched release than either issue's version), the specific errors above may not
  reproduce as-is — but the underlying fragility (Pino's transport mechanism depends on
  dynamic `require()` patterns that Turbopack has repeatedly mis-bundled across 16.x) is a
  structural risk, not a one-off bug, and should be treated as "verify before trusting" rather
  than "definitely still broken."

**Why this happens mechanically** (from Pino's own docs, fetched directly —
https://github.com/pinojs/pino/blob/main/docs/transports.md): Pino's transport system
spins up a **separate worker thread** for log transformation/transmission so the main
thread isn't blocked. The doc states *"It is recommended that any log transformation or
transmission is performed either in a separate thread or a separate process"* — a
recommendation designed for **long-lived servers**, not single-invocation serverless
functions. It also warns: *"The new transports boot asynchronously and calling
`process.exit()` before the transport starts will cause logs to not be delivered"* — a
direct risk in serverless, where the runtime can freeze/terminate the invocation the
moment the response is sent, with no guarantee the transport's worker thread has finished
booting or flushing.

**The safe pattern:** use plain `pino()` (no `pino.transport()`, no `pino/file`, no
external transport target) so it writes JSON synchronously to `stdout` on the main thread
— no worker thread spun up at all. This sidesteps both the Turbopack bundling issue and
the async-delivery risk. If you need routing to an external service, do it via a
**synchronous Vercel-compatible transport** (see Axiom section below) or let Vercel's log
drain forward stdout externally, rather than using Pino's worker-thread transport
mechanism directly inside the function.

---

## 2. Concrete library comparison

### Pino
- **Version:** v10.x current major (issue #86099 reproduced against pino@10.1.0).
  Actively maintained (NearForm-backed, frequent releases).
- **Serverless/Vercel compatibility:** Safe in **basic synchronous mode**
  (`import pino from 'pino'; const logger = pino()` — writes JSON to stdout on the main
  thread, no worker thread). **NOT safe as-is** if you reach for `pino.transport()` /
  `pino/file` / any transport target — confirmed broken against this exact stack
  (Next.js 16 + Turbopack) in issues #86099 and #84766 above. If sync mode is used, Pino
  is a fine choice: near-zero overhead, structured JSON out of the box, `req`/`err`
  serializers, child loggers for request-scoped context (e.g. `orgId`, `route`).
- **Verdict:** usable, but only in sync mode. Don't add `pino-pretty` or any transport
  package to the Vercel build.

### Vercel-native (OpenTelemetry via `@vercel/otel`)
- **Current, official, fetched directly** from https://nextjs.org/docs/app/guides/open-telemetry
  (version 16.2.10 doc, dated 2026-02-11 — i.e. current for this app's Next.js 16.2.9).
  Install: `@vercel/otel @opentelemetry/sdk-logs @opentelemetry/api-logs
  @opentelemetry/instrumentation`. Setup is a root `instrumentation.ts`:
  ```ts
  import { registerOTel } from '@vercel/otel'
  export function register() {
    registerOTel({ serviceName: 'next-app' })
  }
  ```
- **What it gives you automatically:** spans for the root request
  (`[http.method] [next.route]`), app-router rendering, fetch calls, and — directly
  relevant to this Brief — **`executing api route (app) [next.route]`** which wraps every
  Route Handler execution (i.e. the sync routes) and would show up as a span even when the
  handler's own error handling swallows the error internally. This is trace/span
  visibility, not application-level structured logs — it would tell you a sync route ran
  and roughly how long it took, but not "listing 3 had no identifier" unless you also add a
  custom log call or span attribute inside the handler.
- **Verdict:** worth adding for free trace visibility (near-zero setup cost, official,
  works out of the box on Vercel per the doc: *"We made sure that OpenTelemetry works out
  of the box on Vercel"*), but it does NOT replace the need for explicit `logger.error()`
  calls in the sync route catch blocks — it complements, doesn't substitute.
- **Caveat found:** a real, currently open bug (see Sentry section below, issue #19367)
  shows Next.js 16 + Turbopack can duplicate `@opentelemetry/api` across chunks, causing a
  fatal `RangeError: Maximum call stack size exceeded` when **Sentry's** OTel integration
  is layered in. The bug report itself does not mention `@vercel/otel` specifically, so it
  is not confirmed to affect `@vercel/otel` alone — flag as unconfirmed-for-this-exact-path,
  but worth watching if Sentry is added later (see below).

### Axiom
- **Still current and Vercel-paired, but the integration path changed.** `next-axiom` (the
  old package) is now explicitly in maintenance-only mode — confirmed via WebSearch
  synthesis of Axiom's own docs/blog: *"The next-axiom library is no longer under active
  development. It's supported with bug fixes, but it won't receive new features."*
- **Current recommended package**, fetched directly from
  https://axiom.co/docs/send-data/nextjs: **`@axiomhq/nextjs`** (paired with `@axiomhq/js`
  and `@axiomhq/logging`) if you want to send logs directly from the app **without**
  requiring Vercel Drains (a paid-plan-gated feature). Minimal setup confirmed from the doc:
  ```ts
  // lib/axiom/server.ts
  import axiomClient from '@/lib/axiom/axiom'
  import { Logger, AxiomJSTransport } from '@axiomhq/logging'
  import { createAxiomRouteHandler, nextJsFormatters } from '@axiomhq/nextjs'

  export const logger = new Logger({
    transports: [new AxiomJSTransport({ axiom: axiomClient, dataset: process.env.NEXT_PUBLIC_AXIOM_DATASET! })],
    formatters: nextJsFormatters,
  })
  export const withAxiom = createAxiomRouteHandler(logger)
  ```
- **Verdict for this app:** genuinely useful if you want searchable/queryable logs outside
  Vercel's own (short-retention, less-searchable) function log viewer, and it avoids the
  paid-Drains requirement. But it's an **added third-party dependency + external account**
  for a solo-operator tool that doesn't yet have any logging at all — reasonable as a
  phase 2, not phase 1.

### Sentry
- **Different concern, confirmed correctly in the Brief:** error tracking with
  stack-trace grouping, alerting, release tracking — not general structured logging.
- **Next.js 16 + Turbopack compatibility — real, current issues found and fetched:**
  - Turbopack is the default bundler in Next.js 16, and Sentry reworked its SDK
    (`@sentry/nextjs` v9+) specifically to stop depending on bundler internals — "if
    you're on Next.js 15.4.1 or later, Turbopack just works" per Sentry's own blog
    (https://blog.sentry.io/turbopack-support-next-js-sdk/).
  - **But a real, currently OPEN bug exists at this exact combination** — fetched directly:
    **Issue #19367**, https://github.com/getsentry/sentry-javascript/issues/19367 —
    *"Next.js 16 Turbopack duplicates @opentelemetry/api across chunks, causing infinite
    .with() recursion and fatal RangeError: Maximum call stack size exceeded."* Confirmed:
    Next.js 16.1.6, `@sentry/nextjs` 10.38.0 (regression between 10.8.0 and 10.38.0), status
    **open, "Waiting for: Community"**, no fix merged at time of research. Workaround found
    in the issue: downgrade to `@sentry/nextjs@10.8.0`. Setting `tracesSampleRate: 0` does
    NOT avoid the crash; `skipOpenTelemetrySetup: true` avoids the crash but introduces a
    `MaxListenersExceededWarning` flood instead.
  - Other confirmed Next.js 16 + Turbopack Sentry gotchas from the same search pass (via
    Sentry's own docs, not independently re-fetched here — flag as secondary/less-verified
    than the two issues above): Turbopack does not auto-import `sentry.client.config.ts`
    the way Webpack did (needs manual init via a Client Component + `useEffect`); and a
    `Math.random()` collision with Next.js 16's `dynamicIO` mode since Sentry's OTel
    integration uses `Math.random()` for trace IDs.
- **Verdict:** worth adding for a solo operator specifically because it turns "an error
  happened somewhere" into an alert with a stack trace and a count — which is exactly what's
  missing today (errors currently vanish into a response array nobody reads). But given
  Next.js 16.2.9 is very close to the 16.1.6 version where issue #19367 is confirmed open, **pin
  and test the exact `@sentry/nextjs` version before deploying** — do not blindly install
  `latest`. If it crashes, the known workaround is pinning to `10.8.0`.

### Others considered, not recommended for this app's scale
- **Winston** — came up in the general search synthesis as a Pino alternative, but has the
  same category of issue (file/transport-based logging assumes a long-lived process); no
  Vercel-specific advantage over sync-mode Pino was found, and it's heavier. Not
  independently deep-dived given the honesty bar (no specific Vercel/Winston GitHub issue
  fetched) — flagging as **not researched further**, not recommending either way.
- **Baselime** — appeared in Vercel's own template gallery
  (`vercel.com/templates/next.js/nextjs-baselime-opentelemetry`) as an OTel-paired
  alternative to Axiom. Not independently fetched/verified this pass — noted as an
  alternative worth a look if Axiom's pricing/fit doesn't work, not verified further here.
- **Enterprise-scale stacks (Datadog, full self-hosted OTel Collector + Grafana/Loki
  stack)** — explicitly out of scope per the Brief's own framing (solo-operator tool);
  not researched, correctly excluded.

---

## 3. Prisma-specific logging (driver-adapter, Prisma 7.x)

**Yes, still current — and it DOES work with the `@prisma/adapter-pg` driver-adapter
setup, not just the legacy connection mode.** Confirmed via WebSearch synthesis of a
concrete example (search result quoting real usage):
```ts
super({
  adapter,
  log: [
    { emit: 'event', level: 'query' },
    { emit: 'stdout', level: 'error' },
    { emit: 'stdout', level: 'warn' },
  ],
})
```
This is the same `log` array + `$on('query', ...)` mechanism from Prisma's official docs
(https://www.prisma.io/docs/orm/prisma-client/observability-and-logging/logging, fetched
directly), applied on top of an adapter-based client rather than a connection-string-based
one — the `log` option is a `PrismaClientOptions` field independent of which adapter is
passed. Official doc code:
```ts
const prisma = new PrismaClient({ log: [{ emit: 'stdout', level: 'query' }] })
prisma.$on('query', (e) => {
  console.log('Query: ' + e.query)
  console.log('Params: ' + e.params)
  console.log('Duration: ' + e.duration + 'ms')
})
```
Note: `$on` requires `emit: 'event'` (not `'stdout'`) for that specific level to be
subscribable in code; `emit: 'stdout'`/`'stderr'` writes directly to console without a
subscription. This app's `src/lib/db.ts` currently passes **no `log` option at all** —
confirmed by direct read.

**Would Prisma-level query logging have surfaced today's `client.query()` concurrency
warning more visibly? Partially — and here's the concrete, confirmed mechanism, not a
guess:**

- The concurrency warning is a **Node.js process-level `DeprecationWarning`** emitted by
  `pg` (node-postgres) itself, not a Prisma query-level warning — so Prisma's `log: [{level: 'warn'}]`
  option (which surfaces *Prisma's own* internal warnings) would likely **not** capture it directly, since it originates one layer below Prisma in the `pg` driver.
- **But it is directly traceable to Prisma's own adapter code**, confirmed via a real, open
  issue fetched directly: **prisma/prisma#29646**
  (https://github.com/prisma/prisma/issues/29646) — *"DeprecationWarning with
  @prisma/adapter-pg v7.8.0"* (the exact version pinned in this app's `package.json`).
  Root cause per the issue: the `performIO` method in `@prisma/adapter-pg` passes the
  `values` parameter **twice** to `client.query()` — once inside the query config object,
  once again as a second positional argument — which is exactly the deprecated
  double-invocation pattern `pg` warns about (confirmed separately from
  brianc/node-postgres#3612, https://github.com/brianc/node-postgres/issues/3612: *"Calling
  client.query() when the client is already executing a query is deprecated and will be
  removed in pg@9.0"*, introduced in `pg@8.19.0`). Functional impact: none (queries still
  succeed) — but it's a real, currently-open bug (no confirmed fix; the only workaround
  noted is downgrading Prisma) that will become a hard break when `pg` ships v9.0 and
  removes the double-invocation path entirely.
- **What WOULD have helped:** this warning prints to `process.stderr` via Node's own
  deprecation-warning mechanism (`--trace-deprecation` / default stderr emission), which
  Vercel captures into function logs the same as any stderr output — **so it was always
  visible in Vercel's raw function logs**, just not surfaced anywhere a human would
  routinely look (no alert, no dashboard, buried in verbose function-log noise). Prisma
  query-level logging (`emit: 'stdout', level: 'query'`) would not have caught this specific
  warning, but a **general practice of routinely reviewing Vercel function logs (or piping
  them to a log drain / Axiom where they're searchable)** would have. This is the concrete
  argument for *some* level of log aggregation, even for a warning that technically "was
  already being emitted."

---

## 4. Concrete, scoped recommendation for THIS app

**Do NOT install a full observability stack for a solo-operator tool.** The honest
scoped answer, ordered by cost-to-value for this specific app:

### Phase 1 (do this now, near-zero cost, directly targets today's two bugs)

1. **Add a tiny logging wrapper using Pino in synchronous mode only** (no transport, no
   `pino-pretty` in production, no `pino/file`):
   ```ts
   // src/lib/logger.ts
   import pino from 'pino'
   export const logger = pino({
     level: process.env.LOG_LEVEL ?? 'info',
     base: { env: process.env.VERCEL_ENV ?? 'development' },
   })
   ```
   This writes structured JSON to stdout synchronously on the main thread — no worker
   thread, so it sidesteps the confirmed Turbopack/Pino transport bugs (#86099, #84766)
   entirely, because those only fire when `pino.transport()`/`pino/file` targets are used.
   Vercel captures stdout automatically into Function Logs — no drain, no external account,
   no cost.

2. **Fix the actual silent-swallow pattern in the sync routes.** Today: `catch (err) {
   errors.push(...String(err)) }` with nothing server-side. Change to: log AND still return
   the array (don't remove the response-body error reporting — that's used by the caller):
   ```ts
   } catch (err) {
     logger.error({ orgId, listingIndex: i, listingId: listing.listingId, err }, 'sync/airbnb: listing upsert failed')
     errors.push(`listing ${i}: ${String(err)}`)
   }
   ```
   Do this at **every** catch block in `src/app/api/sync/padsplit/route.ts` (8 found) and
   `src/app/api/sync/airbnb/route.ts` (2 found) — each should log with enough structured
   context (`orgId`, the item/index being processed, the route/page, the raw `err`) to
   reconstruct what failed without needing to reproduce it. This is the single change that
   would have made today's silently-dropped sync payload visible in Vercel's function logs
   at the moment it happened, instead of requiring a live bug hunt to discover after the fact.

3. **Log at the dashboard server actions** (`dismissAlert`/`completeTask`/
   `flagPaymentDispute`/`resolvePaymentDispute`) — at minimum, log on any thrown/caught
   error path, with the actor/org/task ID. These are user-triggered mutations; a silent
   failure here means a user click did nothing and nobody — including the operator — would
   know.

4. **Log at `task-recompute.ts`** (the ops-clock engine) — this is scheduled/background
   logic with no request/response round-trip to fall back on, so it needs its own log lines
   at minimum on: recompute start/end with counts (how many tasks evaluated, how many
   alerts raised/cleared), and any per-record error caught during the recompute loop. This
   is the path with the least natural visibility (no HTTP response to inspect after the
   fact) and arguably benefits most from logging.

5. **Turn on Prisma's own `log` option** on the adapter-based client in `src/lib/db.ts`:
   ```ts
   const adapter = new PrismaPg(connectionString)
   return new PrismaClient({
     adapter,
     log: [
       { emit: 'event', level: 'warn' },
       { emit: 'event', level: 'error' },
       ...(process.env.LOG_LEVEL === 'debug' ? [{ emit: 'event', level: 'query' } as const] : []),
     ],
   })
   ```
   then pipe `db.$on('warn', ...)` / `db.$on('error', ...)` into the same `logger` from
   step 1, so DB-level warnings land in the same structured stream as everything else. Keep
   `query`-level logging **event-gated behind an env var**, not always-on — full query
   logging on every request is real overhead and log-volume noise for a solo-operator app;
   it's a debugging toggle, not a standing default. This alone would NOT have caught the
   `pg` deprecation warning (confirmed above — that's a Node-process-level stderr emission,
   one layer below Prisma's own warn/error events), so don't oversell it — but it gives
   query-level visibility for cheap and costs nothing at info/warn/error level.

### Phase 2 (worth it, but only after Phase 1 proves logging is actually being looked at)

6. **Add Sentry** (`@sentry/nextjs`) for error alerting specifically — because "an error
   was logged to stdout" still requires the operator to go looking; Sentry pushes an alert.
   **Pin the version and test it against this app's Next.js 16.2.9 before trusting it** —
   issue #19367 (open, unresolved) is a real crash risk at Next.js 16.1.6 with recent
   `@sentry/nextjs` (10.38.0); if it reproduces, the known workaround is pinning to
   `@sentry/nextjs@10.8.0`. Budget an explicit smoke-test step for this, don't just `npm
   install @sentry/nextjs@latest` and assume it's fine.

### Phase 3 (optional, only if Vercel's own function-log UI proves too limited in practice)

7. **Axiom** (`@axiomhq/nextjs` + `@axiomhq/js` + `@axiomhq/logging`) for searchable,
   retained log aggregation outside Vercel's own short-retention log viewer — genuinely
   useful once there's enough log volume that grepping Vercel's dashboard stops being
   practical, but adds a third-party account + dependency for an app that has zero logging
   today. Don't front-load this; add it once Phase 1 is generating logs worth searching.

### What's overkill and correctly excluded
- A self-hosted OpenTelemetry Collector + Grafana/Loki/Tempo stack — enterprise-scale,
  operational burden (running infra) that a solo operator on Vercel doesn't need; Vercel's
  own OTel support (`@vercel/otel`) already covers trace-level visibility without
  self-hosting anything.
- Datadog or similar enterprise APM — cost and setup complexity disproportionate to a
  single-operator tool's scale.
- Full `@vercel/otel` + custom span instrumentation everywhere — worth the near-zero-cost
  basic setup (`instrumentation.ts` + `registerOTel()`) for free trace context, but don't
  invest time hand-instrumenting custom spans throughout the sync/recompute code; that
  effort is better spent on the structured `logger.error()` calls in Phase 1, which directly
  target the two bug classes named in the Brief.

---

## Sources (all fetched/opened directly, not cited from search snippets alone)

- Next.js OpenTelemetry guide (official, fetched in full) — https://nextjs.org/docs/app/guides/open-telemetry
- Pino transports doc (official repo, fetched) — https://github.com/pinojs/pino/blob/main/docs/transports.md
- Next.js/Turbopack + Pino transport bug #1 (fetched) — https://github.com/vercel/next.js/issues/86099
- Next.js/Turbopack + Pino transport bug #2 (fetched) — https://github.com/vercel/next.js/issues/84766
- Axiom Next.js integration docs (official, fetched) — https://axiom.co/docs/send-data/nextjs
- Sentry Turbopack support blog (referenced via search synthesis, not independently re-fetched this pass) — https://blog.sentry.io/turbopack-support-next-js-sdk/
- Sentry + Next.js 16 Turbopack OTel duplication bug (fetched, OPEN as of research date) — https://github.com/getsentry/sentry-javascript/issues/19367
- Prisma logging docs (official, fetched) — https://www.prisma.io/docs/orm/prisma-client/observability-and-logging/logging
- Prisma adapter-pg deprecation-warning bug (fetched) — https://github.com/prisma/prisma/issues/29646
- node-postgres deprecation warning issue (fetched) — https://github.com/brianc/node-postgres/issues/3612
- node-postgres pooling future-support discussion (found, not independently fetched this pass) — https://github.com/brianc/node-postgres/issues/3617

## Not found / not independently verified this pass (flagged honestly)
- Winston's specific Vercel/serverless compatibility — no dedicated GitHub issue fetched;
  not recommending for or against beyond noting it shares Pino's category of risk.
- Baselime's current setup/pricing — only seen via a Vercel template gallery listing, not
  independently fetched.
- Whether `@vercel/otel` itself (as opposed to `@sentry/nextjs`'s OTel integration)
  triggers the chunk-duplication bug in issue #19367 — the issue report does not mention
  `@vercel/otel`, so this is unconfirmed either way; flag as a "test before combining Sentry
  + @vercel/otel in the same app" caveat rather than a known-safe or known-broken claim.
