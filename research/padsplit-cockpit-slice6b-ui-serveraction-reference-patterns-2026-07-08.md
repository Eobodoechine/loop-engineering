# Slice 6b UI-layer domain research — Server Action / `useActionState` reference patterns (padsplit-cockpit)

**Mode:** D (domain research for a build). **Date:** 2026-07-08. **Researcher:** leaf worker, no sub-dispatch.
**Consumes:** `~/Claude/loop/runs/2026-07-04_airbnb-calendar/specs/spec.md` (revision 33) §C.1 (lines
2580–3509), the UI layer about to be literally transcribed: `web/src/app/dashboard/calendar-sync/actions.ts`,
`page.tsx`, `components/CalendarLinkForm.tsx`.
**Does NOT re-research:** the iCal format, guest-correlation, or `Reservation` Prisma model — settled in
`~/Claude/loop/research/padsplit-cockpit-slice6b-airbnb-calendar-research-2026-07-04.md` and
`~/Claude/loop/research/padsplit-cockpit-slice6-airbnb-research-2026-07-04.md` (confirmed by skim; both
are backend/schema-focused, RentTools.io + `open-hotel-pms` are their prior art — neither touches the
UI/Server-Action layer this dispatch is scoped to).
**Ground rules honored:** no sub-agent dispatch; every URL/file cited below was actually opened (curl/
WebFetch/direct file Read) and quoted, not inferred from a WebSearch snippet.

---

## Headline finding (the single most load-bearing one)

**spec.md revision 33's §C.1 code blocks match the real, current Next.js 16 / React 19 API surface — no
correction needed.** `useActionState` imported from `'react'` (not `'react-dom'`, not the pre-19
`useFormState`), `<form action={formAction}>` bound to the value `useActionState` returns (not the raw
server action), `revalidatePath` imported from `'next/cache'` with a single string argument — all three
confirmed against (a) the actual official Next.js 16.2.10 docs, fetched directly today, and (b) this exact
repo's own already-shipped, already-compiling `RegenerateButton.tsx`, which uses the identical pattern.
The two sources agree with each other and with spec.md. See Q2 below for the full grounding.

---

## Question 1 — What is this repo's own existing convention for a Server Action that mutates data, calls `revalidatePath`, and is invoked from a client form? (Highest-value reference, checked first.)

**Answer: the repo has exactly two existing `'use server'` files — `web/src/app/inbox/actions.ts` and
`web/src/app/dashboard/actions.ts` — and one existing `useActionState`-wrapped Client Component,
`web/src/app/inbox/components/RegenerateButton.tsx`. None of the three existing actions currently calls
`revalidatePath` (grepped, zero hits, confirmed below) — spec.md's own claim of this is accurate, not
fabricated. The `useActionState` wiring pattern spec.md's `CalendarLinkForm.tsx` code block uses is a
byte-for-byte structural match of `RegenerateButton.tsx`'s real, shipped code.**

### 1a. `package.json` — exact installed versions (confirmed by direct read, not assumed)
`<HOME>/Claude/Projects/padsplit-cockpit/web/package.json`:
```
"next": "16.2.9",
"react": "19.2.4",
"react-dom": "19.2.4",
"eslint": "^9",
"eslint-config-next": "16.2.9"
```
Note: `node_modules/` is not currently installed in this working copy (`node_modules/next` does not
exist) — every version-specific claim below is grounded against `package.json`'s pinned version and the
*live, official* docs for that version, not a locally-inspected `node_modules/next/dist/docs/` (which
`web/AGENTS.md` points to but which isn't present on disk right now). **Flag for whoever runs `next
build`: run `npm install` (or equivalent) first if it hasn't been run since this dispatch.**

### 1b. `web/src/app/inbox/components/RegenerateButton.tsx` — the real, shipped `useActionState` pattern
Full file read directly. The load-bearing lines:
```tsx
"use client"

import { useActionState } from "react"
import type { GenerateDraftResult } from "../actions"
import { generateDraft } from "../actions"

const INITIAL_STATE: { status: undefined } = { status: undefined }

export function RegenerateButton({ ... }) {
  const [state, formAction, pending] = useActionState<
    { status: undefined } | GenerateDraftResult,
    FormData
  >(async (_prevState, formData) => generateDraft(formData), INITIAL_STATE)

  return (
    <div className="flex flex-col gap-2">
      <form action={formAction} onSubmit={handleSubmit}>
        <input type="hidden" name="conversationId" value={conversationId} />
        <button type="submit" disabled={pending}>...</button>
      </form>
      {state.status === "escalated" ... ? <p>...</p> : null}
    </div>
  )
}
```
This is the **exact same shape** spec.md's `CalendarLinkForm.tsx` code block uses for both
`syncFormAction`/`syncState`/`syncPending` and `saveFormAction`/`saveState`/`savePending` — a wrapper arrow
function `async (_prevState, formData) => someAction(formData)` around a plain `(formData: FormData) =>
Promise<Result>` server action (not an action whose own signature was rewritten to accept `prevState`,
which is the *alternative* pattern the official docs also show — see Q2). This confirms spec.md picked
the pattern this codebase has ALREADY proven compiles and ships, not a theoretical one.

**One real, functionally-inert deviation worth flagging before transcription**: the real file's directive
and import strings use **double quotes** (`"use client"`, `from "react"`, `from "../actions"`), while
spec.md's quoted code blocks throughout §C.1 use **single quotes** (`'use client'`, `from 'react'`). This
repo has no Prettier config and no ESLint `quotes` rule (confirmed — see Q4/tooling note), so this is
cosmetically inconsistent with the rest of the file but **will not fail `tsc --noEmit` or `next build`** —
JS/TS string literals don't care about quote style. Not a blocker; noted for completeness since the
dispatch brief asked for literal transcription fidelity.

### 1c. `web/src/app/dashboard/actions.ts` and `web/src/app/inbox/actions.ts` — the ownership-check + import convention
Both real files, full content read directly. Confirmed import block (both files use this exact shape,
`dashboard/actions.ts` shown):
```ts
"use server"
import type { Prisma } from '@prisma/client'
import { getSession } from '@/lib/session'
import { db } from '@/lib/db'
import { forOrg } from '@/lib/db-rls'
import { logger } from '@/lib/logger'
```
`dismissAlert`'s real, cited ownership-check convention (quoted verbatim, lines 48-55):
```ts
const room = await forOrg(orgId).room.findUnique({
  where: { id: roomId },
  include: { property: { select: { orgId: true } } },
})
if (!room || room.property.orgId !== orgId) {
  logger.error({ orgId, roomId }, 'dismissAlert: ownership check failed — room not found or cross-org')
  throw new Error('Not found')
}
```
This exactly matches spec.md's own citation of this convention for `saveCalendarLink`'s
`forOrg(orgId).property.findUnique({where:{id:propertyId}})` + `if (!property || property.orgId !== orgId)`
check.

**One real, deliberate divergence worth flagging explicitly (not a bug, but could look like one to a
transcribing Coder):** all three EXISTING server actions (`generateDraft`, `discardDraft`, `approveDraft`,
`dismissAlert`, `completeTask`) `throw new Error('Unauthorized')` / `throw new Error('Not found')` on
auth/ownership failure — an **uncaught throw**, which (per spec.md's own §C.1 "Invocation mechanism" note,
independently confirmed against the real `RegenerateButton.tsx`/`generateDraft` pairing) would crash to the
nearest error boundary rather than deliver a graceful message via `useActionState`. spec.md's NEW
`saveCalendarLink`/`syncNowAction` deliberately do NOT follow this majority pattern — both wrap their
*entire* body, including the `getSession()` call, in one `try/catch` and return `{status:'error', message}`
instead of throwing. This is spec.md's own explicit, reasoned design choice (revision 22/25/26's "Save-
action failure" and "Scope" notes), not an oversight to "fix" back to the throw-style during transcription
— confirming it here so it survives the transcription pass as written.

### 1d. Confirmed absent from the whole repo (grounds spec.md's own "zero hits" claims)
```
grep -rn "revalidatePath\|router.refresh\|next/cache" web/src/   → zero hits
grep -n "next/link\|<Link" web/src/app/dashboard/page.tsx        → zero hits
```
`useRouter` exists in exactly ONE place in the whole repo, `web/src/components/SignOutButton.tsx`:
```tsx
"use client"
import { useRouter } from "next/router"  // NO — corrected below, see exact quote
```
**Exact quote (corrected from my own paraphrase above — read directly):**
```tsx
import { useRouter } from "next/navigation"
...
const router = useRouter()
...
onSuccess: () => router.push("/auth/signin"),
```
This confirms `next/navigation` (not `next/router`, the Pages-Router-era path) is this repo's own real,
only precedent for `useRouter` — matching spec.md's `import { useRouter } from 'next/navigation'` for
`CalendarLinkForm.tsx`'s selector `router.push`.

### 1e. `dashboard/page.tsx` — the async-`searchParams` and property-group-header conventions spec.md cites
Confirmed by direct read, exact line matches:
- Lines 220-230: `export default async function DashboardPage({ searchParams }: { searchParams:
  Promise<{ filter?: string }> })`, `const session = await getSession()`, `if (!session?.user?.orgId)
  redirect('/auth/signin')`, `const sp = await searchParams` — matches spec.md's cited pattern for
  `calendar-sync/page.tsx` exactly, including the `redirect()` import path (`next/navigation`).
- Lines 446-449: `<div className="mb-3"><h2>...</h2><p>...</p></div>` — confirmed the literal
  property-group header block spec.md's "Connect Calendar" link insertion targets.
- Line 214: `<a href={href} aria-current={...} className={className}>` (the `FilterTab` component) — the
  ONLY link-rendering convention in this file; `next/link`'s `<Link>` is never imported (1d), confirming
  spec.md's instruction to use a plain `<a href=...>` for "Connect Calendar" is the file's real convention,
  not an invented shortcut.

---

## Question 2 — Do spec.md's §C.1 `useActionState`/form code blocks match the real, current Next.js 16 / React 19 API? (The load-bearing question.)

**Answer: YES, confirmed against the live, official docs (not a WebSearch summary — both pages fetched
directly, versions/dates below), and independently cross-checked against this repo's own shipped code
(Q1). No correction needed.**

### 2a. `useActionState` import and shape — confirmed against react.dev
Source: `https://react.dev/reference/react/useActionState`, fetched directly. Confirmed import:
```js
import { useActionState } from 'react';
```
Confirmed return shape and action signature from the docs' own full example:
```js
const [count, dispatchAction, isPending] = useActionState(updateCartAction, 0);
...
async function updateCartAction(prevCount, formData) {
  const type = formData.get('type');
  // ...
  return newCount;
}
```
`useActionState(action, initialState)` returns `[state, dispatchAction, isPending]`; the wrapped action
receives `(prevState, formData)`. This is precisely the shape spec.md's `CalendarLinkForm.tsx` uses (its
own wrapper `async (_prevState, formData) => syncNowAction(formData)` matches the `(prevState, formData)
=> newState` contract, delegating to the real, simpler `(formData) => Promise<Result>` action underneath —
exactly `RegenerateButton.tsx`'s own real pattern too, Q1).

### 2b. Next.js's own forms guide — confirmed current version, quoted directly
Source: `https://nextjs.org/docs/app/guides/forms`, fetched directly — page metadata confirms
`version: 16.2.10`, `lastUpdated: 2026-06-23` (i.e., this IS the current doc for the installed
`next@16.2.9` release line, not a stale cached page). Quoted directly:

> To display validation errors or messages, turn the component that defines the `<form>` into a Client
> Component and use React `useActionState`... When using `useActionState`, the Server function signature
> will change to receive a new `prevState` or `initialState` parameter as its first argument.
```tsx
'use client'
import { useActionState } from 'react'
import { createUser } from '@/app/actions'
const initialState = { message: '' }
export function Signup() {
  const [state, formAction, pending] = useActionState(createUser, initialState)
  return (
    <form action={formAction}>
      ...
      <p aria-live="polite">{state?.message}</p>
      <button disabled={pending}>Sign up</button>
    </form>
  )
}
```
This confirms `<form action={formAction}>` (the value RETURNED by `useActionState`, not the raw imported
action function) is the documented, current pattern — matching spec.md's explicit correction
("`<form action={syncFormAction}>`/`<form action={saveFormAction}>` (NOT `<form
action={syncNowAction}>`/`<form action={saveCalendarLink}>` directly)").

**One doc-level nuance worth noting, NOT a spec.md deviation**: the docs show a SECOND, alternative
pattern where the doc's own example rewrites the action's signature to accept `prevState` as its own first
param (`export async function createUser(initialState, formData) {...}`) directly, rather than wrapping a
plain-`FormData`-only action in an inline arrow function. spec.md (mirroring `RegenerateButton.tsx`'s real
precedent, Q1) chose the wrapper-arrow-function variant instead, which keeps `syncNowAction`/
`saveCalendarLink` themselves simple `(formData: FormData) => Promise<Result>` functions — both are valid,
documented approaches; spec.md's choice is the one this exact repo already has shipped, working proof for.

### 2c. `revalidatePath` — confirmed single-argument, current, unaffected by any Next 16 breaking change
Source: `https://nextjs.org/docs/app/getting-started/mutating-data`, fetched directly (`version: 16.2.10`,
`lastUpdated: 2026-06-23`). Quoted directly:
```ts
import { auth } from '@/lib/auth'
import { revalidatePath } from 'next/cache'

export async function createPost(formData: FormData) {
  'use server'
  ...
  revalidatePath('/posts')
}
```
Matches spec.md's `import { revalidatePath } from 'next/cache'` + `revalidatePath('/dashboard/calendar-sync')`
exactly (single string argument, no second param).

**Load-bearing version-drift check, done directly (not assumed):** fetched the official Next.js 16
upgrade guide (`https://nextjs.org/docs/app/guides/upgrading/version-16`, `lastUpdated: 2026-05-13`) and
confirmed the ONLY caching-API breaking change in Next 16 is to **`revalidateTag`** (now requires a second
`cacheLife`-profile argument) — **`revalidatePath` is not mentioned as changed at all**, and the "Mutating
Data" doc's own current example (above) still shows the pre-16 single-argument call working as-is. spec.md
uses `revalidatePath`, never `revalidateTag`, so this Next-16-specific breaking change does not apply —
confirmed, not just assumed-safe.

Also confirmed from the same upgrade guide (directly relevant, matches spec.md's own already-correct
design): `searchParams` in `page.js` is explicitly listed under "Async Request APIs (Breaking change)" —
"Starting with Next.js 16, synchronous access is fully removed. These APIs can only be accessed
asynchronously." — validating spec.md's `Promise<{propertyId?: string}>` async-prop pattern is not just
matching a codebase habit but a hard Next-16 requirement, not optional style.

### 2d. `useFormStatus` — confirmed NOT what spec.md uses, and confirmed why that's the right call here
Source: same `nextjs.org/docs/app/guides/forms` fetch. Quoted:
> Alternatively, you can use the `useFormStatus` hook to show a loading indicator... **imported from
> `react-dom`**... When using this hook, you'll need to create a separate component to render the loading
> indicator.
spec.md's `CalendarLinkForm.tsx` needs the ACTION'S RETURN VALUE (the three-way `SyncNowResult` branch,
the `SaveCalendarLinkResult` error message) delivered into rendered state, not just a pending boolean —
`useFormStatus` only exposes `pending` (plus request metadata), never the action's resolved value. The
docs' own guidance ("use `useActionState` when you need the action result and form-level state, or
`useFormStatus`... for simple pending indicators") confirms `useActionState` is the correct choice for
this dispatch's requirements, not an oversight that `useFormStatus` was available and unused.

---

## Question 3 — Real, currently-maintained open-source repos with a comparable "paste external URL, Save, manual Sync-now" settings UI (beyond RentTools.io/open-hotel-pms's already-covered backend/schema)

**Answer: found ONE genuinely comparable, real, opened-and-quoted example — RentTools.io's OWN frontend
(`add-property/page.tsx`) — but it is a WEAKER match for direct pattern-copying than expected: it's built
as a plain client-fetch form (`onSubmit` → `fetch('/api/calendar/links', ...)`), NOT a Next.js App Router
Server Action with `useActionState`. A broader search for a Next.js App-Router-Server-Action-based
"connect calendar via URL" settings page (Cal.com's ICS-feed app, generic calendar-sync OSS) did not
surface a second, better-matching, independently-opened example. This repo's OWN `RegenerateButton.tsx`
(Q1) remains the single best, most load-bearing reference for the ACTUAL mechanism (`useActionState` +
`'use server'` file) — the domain-comparable UI shape (URL-paste + Save) is confirmed well-trodden, but
the SPECIFIC Next-16-Server-Action wiring pattern has no better external analog than this repo's own
existing code.**

### 3a. RentTools.io's own `add-property/page.tsx` — real, fetched in full, same STR-calendar-sync domain
`https://raw.githubusercontent.com/Gribadan/RentTools.io/master/src/app/dashboard/add-property/page.tsx`
(10,875 bytes, fetched in full). Confirmed real fields matching padsplit-cockpit's own target UI shape
almost verbatim (`icalExportUrl`, per-platform rows) — quoted directly:
```tsx
const submit = async (e: React.FormEvent) => {
  e.preventDefault();
  ...
  const propRes = await fetch(`/api/properties`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: name.trim() }),
  });
  ...
  for (const row of rows) {
    if (!row.url.trim()) continue;
    const r = await fetch(`/api/calendar/links`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        propertyId: property.id,
        platform: row.platform,
        icalExportUrl: row.url.trim(),
      }),
    });
    ...
  }
  router.push(`/dashboard?property=${property.id}`);
};
...
<form onSubmit={submit} className="space-y-8">
```
**Assessment**: this confirms the general UI shape ("paste an iCal export URL per platform, Save") is a
real, live, working pattern in an actively-maintained STR tool (pushed `2026-07-03` per the earlier Slice
6 dossier's confirmation) in the exact same problem domain. **But it is architecturally the OLDER
Pages-Router-style client-fetch-to-API-route pattern** (`'use client'` component's `onSubmit` handler
calling `fetch()` against a REST endpoint), not App Router Server Actions — RentTools.io's own
`src/app/dashboard/page.tsx` (17,170 bytes, also fetched in full) was grepped for
`icalExportUrl|CalendarLink|'use server'|action=|revalidatePath|useActionState` and returned **zero
hits**, confirming this repo does not itself use the Server-Actions pattern anywhere for this feature —
it cannot be cited as an App-Router-Server-Action precedent, only as confirmation that the general "paste
URL, Save" UX shape is sound and well-precedented in this domain.

### 3b. Cal.com's "ICS Feed" app — real, exists, but source not independently opened this pass
`app.cal.com/apps/ics-feed` is confirmed to exist as a real, shipped Cal.com integration (via WebSearch
results referencing live GitHub issues against it, e.g. `calcom/cal.com#13856`, `#2054`, `#1846`), and
Cal.com itself is a large, well-known, actively-maintained open-source project. **I did NOT independently
open and quote its actual source file this pass** (GitHub's unauthenticated code-search API returned
`401 Requires authentication` when I tried to locate the exact handler file, and I did not pursue an
alternate path to the source given time budget and that Q1/Q3a already ground the pattern adequately) —
per the honesty bar, this is flagged as an UNVERIFIED lead, not cited as a confirmed source. If a future
pass wants a second, larger-scale reference implementation, `github.com/calcom/cal.com`'s
`packages/app-store/ics-feedcalendar` (a plausible but unconfirmed path, inferred from the app-store
directory-naming convention Cal.com uses elsewhere, not confirmed by opening it) would be the next thing
to open directly.

---

## Question 4 — Tooling note: ESLint config for "referenced identifier never bound / missing import" at lint-time

**Answer: this repo's own real ESLint config (confirmed by direct read) already uses the standard,
current, TypeScript-aware Next.js config — `eslint-config-next/core-web-vitals` + `eslint-config-next/
typescript` — and the TypeScript-ESLint project's OWN official guidance is that `no-undef` should NOT be
enabled for TypeScript projects, because `tsc` itself already catches this class of bug more precisely.
This means the plan to run `tsc --noEmit`/`next build` (rather than reaching for an ESLint rule) is the
correct, officially-recommended mechanism for this exact failure class — not a gap to fill with a lint
rule.**

`web/eslint.config.mjs`, full file, confirmed by direct read:
```js
import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);
export default eslintConfig;
```
Source: `https://typescript-eslint.io/troubleshooting/faqs/eslint/`, fetched directly. Quoted:
> "The checks it [`no-undef`] provides are already provided by TypeScript without the need for
> configuration - TypeScript just does this significantly better."
Also confirmed via the Next.js 16 upgrade guide (already fetched, §2c above): **`next lint` was removed
in Next.js 16** ("The `next lint` command has been removed. Use Biome or ESLint directly. `next build` no
longer runs linting.") — this repo's own `package.json` `"lint": "eslint"` script already reflects this
migration (bare `eslint` CLI, not `next lint`), confirming the repo is already on the current, post-16
convention. **Practical consequence for a future loop-improvement**: `next build`/`tsc --noEmit` and
`npm run lint` are two genuinely independent commands in this stack now (Next 16 build never silently
lints) — a "missing import" bug is a `tsc`/`next build` failure, never an ESLint one; adding `no-undef` to
this repo's ESLint config would be actively AGAINST the ecosystem's own documented guidance, not a gap.

---

## Honesty-bar summary

| Claim | Status |
|---|---|
| `next@16.2.9`/`react@19.2.4` are the exact installed versions | CONFIRMED — direct read, `package.json` |
| `node_modules/` (incl. `next/dist/docs/`) is not currently installed | CONFIRMED — `ls` returned "No such file or directory" |
| Repo's only 2 existing `'use server'` files are `inbox/actions.ts` and `dashboard/actions.ts` | CONFIRMED — `grep -rl "'use server'"` (zero hits) then `grep -n "use server"` (2 hits, double-quoted) across `web/src/app` |
| `RegenerateButton.tsx`'s exact `useActionState` wrapper-arrow-function pattern | CONFIRMED — full file read directly |
| `revalidatePath`/`router.refresh`/`next/cache` absent from the whole repo | CONFIRMED — direct grep, zero hits |
| `useRouter` exists in exactly one file (`SignOutButton.tsx`), from `next/navigation` | CONFIRMED — direct grep + full file read |
| `dashboard/page.tsx`'s async-`searchParams`, ownership-check, and header-`<div>`/`FilterTab` conventions | CONFIRMED — direct read of the cited line ranges |
| `useActionState` import from `'react'`, return shape `[state, dispatchAction, isPending]` | CONFIRMED — `react.dev/reference/react/useActionState`, fetched directly |
| `<form action={formAction}>` (the hook's return value, not the raw action) is the current documented pattern | CONFIRMED — `nextjs.org/docs/app/guides/forms`, fetched directly, version 16.2.10, quoted |
| `revalidatePath('/path')` single-argument form is still current/unaffected by any Next 16 breaking change | CONFIRMED — `nextjs.org/docs/app/getting-started/mutating-data` + `nextjs.org/docs/app/guides/upgrading/version-16`, both fetched directly |
| `searchParams` async-only is a hard Next 16 requirement, not just a codebase habit | CONFIRMED — Next 16 upgrade guide, quoted |
| `useFormStatus` (from `react-dom`) is the alternative hook, correctly NOT chosen here since it lacks the action's return value | CONFIRMED — `nextjs.org/docs/app/guides/forms`, quoted |
| RentTools.io's `add-property/page.tsx` real content, client-fetch (not Server Action) pattern | CONFIRMED — full file fetched directly, grepped |
| RentTools.io's `dashboard/page.tsx` has NO calendar-link Server-Action code | CONFIRMED — full file fetched, grepped, zero hits |
| Cal.com's ICS-feed app exists as a real, shipped feature | CONFIRMED it exists (via real GitHub issue URLs referencing it) — its SOURCE FILE was NOT independently opened this pass, flagged UNVERIFIED |
| This repo's `eslint.config.mjs` uses `eslint-config-next/core-web-vitals` + `/typescript` | CONFIRMED — direct read |
| `no-undef` is officially not recommended for TS projects (tsc supersedes it) | CONFIRMED — `typescript-eslint.io/troubleshooting/faqs/eslint/`, fetched directly, quoted |
| `next lint` removed in Next 16, `next build` no longer lints | CONFIRMED — Next 16 upgrade guide, quoted |

---

## Not found / explicitly unresolved

1. **Cal.com's actual `ics-feed` app source file** — confirmed to exist as a shipped feature (via real
   GitHub issue references), but not independently opened/quoted this pass (GitHub code-search API
   required auth I don't have; did not pursue an alternate path given the strength of the in-repo
   `RegenerateButton.tsx` precedent already found). If a second external reference for the Server-Action
   mechanism specifically is ever wanted, this is the next thing to try opening directly — a plausible but
   UNCONFIRMED path is `github.com/calcom/cal.com/tree/main/packages/app-store/ics-feedcalendar`.
2. **Whether `node_modules` has been installed since this dispatch** — not re-checked; whoever runs
   `next build`/`tsc --noEmit` should confirm `npm install` has run first, since it had not as of this
   research pass.
3. No other real, comparable open-source Next-App-Router "external URL + Save + manual sync trigger"
   settings page was found and independently opened beyond RentTools.io's (older-pattern) example — this
   is stated plainly rather than padded with an unopened lead.

---

## Sources (every URL/file actually opened this pass)

- `<HOME>/Claude/Projects/padsplit-cockpit/web/package.json` — full file read
- `<HOME>/Claude/Projects/padsplit-cockpit/web/AGENTS.md` / `CLAUDE.md` — read (Next.js-version-drift warning)
- `<HOME>/Claude/Projects/padsplit-cockpit/web/src/app/inbox/actions.ts` — full file read
- `<HOME>/Claude/Projects/padsplit-cockpit/web/src/app/dashboard/actions.ts` — full file read
- `<HOME>/Claude/Projects/padsplit-cockpit/web/src/app/inbox/components/RegenerateButton.tsx` — full file read
- `<HOME>/Claude/Projects/padsplit-cockpit/web/src/components/SignOutButton.tsx` — full file read
- `<HOME>/Claude/Projects/padsplit-cockpit/web/src/app/dashboard/page.tsx` — read in targeted ranges (1-30, 200-250, 440-455)
- `<HOME>/Claude/Projects/padsplit-cockpit/web/eslint.config.mjs` — full file read
- Direct `grep -rn` sweeps of `web/src/` for `revalidatePath`/`router.refresh`/`next/cache`/`useRouter`/`next/navigation`/`use server` — run directly, results quoted above
- `https://react.dev/reference/react/useActionState` — fetched directly, quoted
- `https://nextjs.org/docs/app/guides/forms` — fetched directly (version 16.2.10, lastUpdated 2026-06-23), quoted extensively
- `https://nextjs.org/docs/app/getting-started/mutating-data` — fetched directly (version 16.2.10, lastUpdated 2026-06-23), quoted
- `https://nextjs.org/docs/app/guides/upgrading/version-16` — fetched directly (version 16.2.10, lastUpdated 2026-05-13), quoted (Async Request APIs, `revalidateTag` change, `next lint` removal)
- `https://typescript-eslint.io/troubleshooting/faqs/eslint/` — fetched directly, quoted
- `https://raw.githubusercontent.com/Gribadan/RentTools.io/master/src/app/dashboard/page.tsx` — fetched in full (473 lines), grepped
- `https://raw.githubusercontent.com/Gribadan/RentTools.io/master/src/app/dashboard/add-property/page.tsx` — fetched in full, quoted
- `https://api.github.com/repos/Gribadan/RentTools.io/contents/src/app/dashboard` and `.../add-property` — GitHub Contents API, directory listings confirmed
- WebSearch queries (lead generation only, each lead re-opened above before citing, EXCEPT the Cal.com
  source file which remains unopened and is flagged as such): Next.js 16 Server Actions/`useActionState`
  documentation search, `react.dev useActionState` import search, open-source Next.js "connect calendar"
  iCal-URL-settings-page search, Cal.com ICS-feed search, `eslint-config-next no-undef` search, Next.js 16
  upgrade/breaking-changes search.
- `~/Claude/loop/research/padsplit-cockpit-slice6b-airbnb-calendar-research-2026-07-04.md` and
  `~/Claude/loop/research/padsplit-cockpit-slice6-airbnb-research-2026-07-04.md` — skimmed in full to
  confirm no duplication (both are backend/schema-scoped, confirmed).
- `~/Claude/loop/runs/2026-07-04_airbnb-calendar/specs/spec.md` — read lines 2580–3509 (§C.1) in full.
- `~/Claude/loop/loop-team/roles/researcher.md` — read in full (role brief, Mode D section).
