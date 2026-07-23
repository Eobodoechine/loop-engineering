# Domain brief (Mode D synthesis): revalidatePath + useActionState UI refresh — padsplit-cockpit

Date: 2026-07-09
Repo: <HOME>/Claude/Projects/padsplit-cockpit (npm workspaces: `web`, `extension`)
Synthesized from 3 parallel research angles (2 substantive, 1 empty/garbage) + independent
verification performed directly against this repo's installed `node_modules` and source tree.

## question

In this padsplit-cockpit repo (Next.js 16.2.9, App Router, npm workspaces), does calling
`revalidatePath('/inbox')` inside a Server Action invoked via a `useActionState`-wrapped
client binding refresh the mounted `/inbox` page's UI without an additional explicit
`router.refresh()` call?

## answer

**Yes — no structural coupling between `useActionState` and the revalidation signal.**
Calling `revalidatePath('/inbox')` inside a Server Action refreshes the mounted `/inbox`
page's UI in the same round-trip, regardless of whether the action is invoked via a plain
`<form action={fn}>` or via a `useActionState`-wrapped `formAction` bound to
`<form action={formAction}>`. No explicit `router.refresh()` is required.

All three lines of evidence converge on this, and — critically — **this exact pattern is
already shipped and live in this repo** (see "Real-world precedent" below), which is
stronger evidence than any doc or source trace alone:

1. **Official docs (both the public site and, more authoritatively, the doc bundled with
   the exact installed `next@16.2.9` package)** describe the action-response protocol as
   carrying two independent things in one HTTP round-trip: the action's *return value*
   (consumed by `useActionState`/`useFormState`) and a freshly-rendered RSC payload for the
   revalidated route (committed by Next.js's client router runtime as a seeded navigation).
   `useActionState` only touches the first; it has no visibility into or control over the
   second.
2. **Direct source-tracing in this repo's own installed `next@16.2.9` and `react-dom@19.2.4`**
   confirms the two are architecturally separate call paths: `useActionState`
   (`runActionStateAction` in `react-dom-client.development.js`) just calls the bound action
   function and wraps its return value into state — it never touches HTTP or cache code. The
   actual transport (`callServer` → `dispatchAppRouterAction` → `serverActionReducer` →
   `invalidateBfCache`/`invalidateEntirePrefetchCache` + apply the RSC payload as a seeded
   navigation) is registered ONCE globally at hydration and is invoked identically no matter
   which hook dispatched the call.
3. **A live, already-shipped precedent inside padsplit-cockpit itself**:
   `web/src/app/dashboard/calendar-sync/components/CalendarLinkForm.tsx` wraps
   `saveCalendarLink`/`syncNowAction` in `useActionState`, binds each to
   `<form action={saveFormAction}>` / `<form action={syncFormAction}>`, and the corresponding
   actions in `web/src/app/dashboard/calendar-sync/actions.ts` call
   `revalidatePath('/dashboard/calendar-sync')` — with **no `router.refresh()` call anywhere
   in that component**. `useRouter()` IS imported there, but only for `router.push(...)` on a
   `<select>` change, never for `.refresh()`. This is the exact code shape the `/inbox` question
   is asking about, already built and running in this codebase.

**No genuine disagreement between the two substantive angles** — both concluded
invocation-agnostic behavior; they differ only in method (docs+issues vs. source-tracing),
and the source-tracing is the stronger, version-locked grounding. One correction to angle 2's
own caveat: it claimed `web/AGENTS.md`'s pointer to `next/dist/docs/` was "stale/nonexistent
in this version" — **this is false**, verified directly (see Source below): the directory and
the exact `revalidatePath`/`mutating-data` docs exist and are bundled with the installed
`16.2.9` package, making them the single most version-authoritative source available (more
authoritative than the public nextjs.org site, which could theoretically drift from the
exact installed version). The third angle supplied ("test"/"test"/"test") is empty and
contributes no evidentiary value — disregarded.

## source

Strongest, most authoritative — quoted directly, opened by me:
- `<HOME>/Claude/Projects/padsplit-cockpit/node_modules/next/dist/docs/01-app/03-api-reference/04-functions/revalidatePath.md`
  (bundled with the exact installed `next@16.2.9`, confirmed via
  `node_modules/next/package.json` → `"version": "16.2.9"`):
  > "**Server Functions**: Updates the UI immediately (if viewing the affected path)."
- `<HOME>/Claude/Projects/padsplit-cockpit/node_modules/next/dist/docs/01-app/01-getting-started/07-mutating-data.md`
  — "Revalidate data" section shows `revalidatePath('/posts')` inside a `'use server'`
  function; the same page's "Showing a pending state" section shows the identical action
  wired through `useActionState` — no distinction drawn between the two invocation shapes
  anywhere in this doc.
- Live repo precedent (already shipped, not hypothetical):
  `web/src/app/dashboard/calendar-sync/actions.ts:158-167` (`saveCalendarLink`) and
  `:192-200` (`syncNowAction`) — both call `revalidatePath('/dashboard/calendar-sync')`
  inside a try/catch treating it as a non-fatal side effect; consumed by
  `web/src/app/dashboard/calendar-sync/components/CalendarLinkForm.tsx:12,14,27,29-37`
  (`useActionState` + `<form action={saveFormAction}>` / `<form action={syncFormAction}>`,
  `useRouter()` used only for `.push()`, never `.refresh()`).
- Source-tracing, verified directly against the files actually installed in this repo
  (not summarized from elsewhere):
  - `node_modules/next/dist/server/app-render/action-handler.js:99-124` (`addRevalidationHeader`,
    sets `NEXT_ACTION_REVALIDATED_HEADER` from `workStore.pathWasRevalidated`) and
    `:874,901` (`skipPageRendering` gated on `workStore.pathWasRevalidated !== ActionDidNotRevalidate`
    — i.e., calling `revalidatePath` inside the action flips this so the server DOES render
    and include the fresh RSC payload in the same response).
  - `node_modules/next/dist/client/components/router-reducer/reducers/server-action-reducer.js:191-208`
    — `fetchServerAction(...).then(({revalidationKind, actionFlightData: flightData, ...}) => {
    if (revalidationKind !== ActionDidNotRevalidate) { invalidateBfCache(); ... }` then applies
    `flightData` via `convertServerPatchToFullTree` as a seeded navigation — this runs
    unconditionally, independent of which hook triggered the call.
  - `node_modules/next/dist/client/app-call-server.js` (`callServer`) + `app-index.js:172,188,194`
    — confirms ONE shared `callServer` is registered globally at hydration; every server
    action invocation (form, button, or `useActionState`'s dispatch) funnels through it.
  - `node_modules/react-dom/cjs/react-dom-client.development.js:8370-8413` (`runActionStateAction`)
    — confirmed by reading the function directly: it does `action(prevState, payload)` and
    wraps the promise into `state`/`isPending` via `handleActionReturnValue`; it contains no
    transport or cache-invalidation code, confirming it cannot intercept or suppress the
    server-side revalidation signal.
- Secondary docs, opened and quoted by angle 1 (public site, same content as the bundled
  version for the sections that matter): https://nextjs.org/docs/app/guides/server-actions,
  https://nextjs.org/docs/app/api-reference/functions/revalidatePath,
  https://nextjs.org/docs/app/getting-started/mutating-data, https://react.dev/reference/react/useActionState.
- Known secondary-bug caveats (real, but NOT about this coupling — separate React-state
  bookkeeping glitches on specific version/route combos), opened and quoted by angle 1:
  https://github.com/vercel/next.js/discussions/82289 (v15 `isPending` stuck, unreproducible
  on canary), https://github.com/vercel/next.js/issues/58772 (Intercepting-Routes-specific
  `useFormState` stall), https://github.com/vercel/next.js/issues/66426 (`loading.tsx` +
  Suspense first-submission race).

## code_pattern

Safest pattern: copy the already-shipped, working shape from
`calendar-sync/actions.ts` + `CalendarLinkForm.tsx`, applied to `web/src/app/inbox/actions.ts`
(currently `generateDraft`/`discardDraft`/`approveDraft` do NOT call `revalidatePath` at all —
confirmed by reading the file; this is presumably the gap this research is meant to close).

Server Action (`web/src/app/inbox/actions.ts`), mirroring the non-fatal try/catch convention
already established in `calendar-sync/actions.ts:158-167`:
```ts
'use server'
import { revalidatePath } from 'next/cache'
// ...existing imports...

export async function approveDraft(formData: FormData): Promise<ApproveDraftResult> {
  // ...existing logic unchanged...
  // after the successful updateMany that marks the draft SENT:
  try {
    revalidatePath('/inbox')
  } catch (err) {
    logger.error({ orgId, messageId, err }, 'approveDraft: revalidatePath failed (non-fatal)')
  }
  return { ok: true }
}
```

Client binding — NO CHANGE NEEDED. `ApproveDraftForm.tsx`, `DiscardButton.tsx`, and
`RegenerateButton.tsx` already use the exact pattern that works (verified against the
`calendar-sync` precedent and the bundled docs' "Showing a pending state" example):
```tsx
const [state, formAction, pending] = useActionState<...>(
  async (_prevState, formData) => approveDraft(formData),
  INITIAL_STATE
)
// ...
<form action={formAction}>...</form>
```
Because the action is bound via a `<form>` element's `action` prop (not a bare `onClick`
outside a form), React auto-wraps the dispatch in `startTransition` per the bundled doc
(`mutating-data.md` line 21-24: "This happens automatically when the function is: Passed to
a `<form>` using the `action` prop... Passed to a `<button>` using the `formAction` prop.") —
no manual `startTransition(action)` wrapper is needed here (that wrapper is only shown in the
docs for the `<button onClick={...}>`-outside-a-form case).

Do **not** add `router.refresh()`/`useRouter` to these components — the repo's own shipped
precedent (`CalendarLinkForm.tsx`) explicitly does not need it, and adding it would be
redundant, not merely harmless (see constraints).

## constraints

- **Version-locked to this exact repo**: `next@16.2.9`, `react`/`react-dom@19.2.4`, npm
  workspaces (`web`, `extension`), confirmed via `web/package.json` and
  `node_modules/next/package.json`. Do not assume behavior generalizes to Next 15.x without
  re-checking — angle 1 found real, version-specific bugs on 15.x (`isPending` stuck,
  Intercepting Routes stall) that were not reproducible on later canaries; this repo is on
  16.2.9, past that window, and has its own live precedent, so those are not blocking.
- `web/src/app/inbox/page.tsx` is a **dynamic** Server Component (reads `searchParams`
  asynchronously and calls `getSession()`), with no `export const dynamic`/`revalidate`
  override — confirmed there is no static-generation caching complication for this route.
  `revalidatePath('/inbox')` is called as a **literal path with no dynamic route segment in
  the file path** (only a client-visible `?contact=` query string, which is not a route
  segment) — per the bundled doc, `type` should be omitted for a literal path, which matches
  the exact call the question asks about (`revalidatePath('/inbox')`, no second argument).
- `revalidatePath` inside a Server Action is documented (bundled doc, "Good to know") as:
  "Updates the UI immediately (if viewing the affected path). Currently, it also causes all
  previously visited pages to refresh when navigated to again. This behavior is temporary."
  — a minor, undocumented-duration side effect, not a blocker.
- Treat `revalidatePath` as a **non-fatal side effect after the real mutation succeeds** —
  this repo's own established convention (`calendar-sync/actions.ts`) wraps it in try/catch
  with a logged, swallowed error, specifically because it can throw "Invariant: static
  generation store missing" outside a real Next.js request context (e.g. in a test harness).
  Follow the same convention for the `/inbox` actions rather than letting a revalidation
  failure turn a real DB-write success into a reported failure.
- `revalidateTag` (not used anywhere in this repo currently) has a materially different
  timing profile — per angle 1's docs citation it "does NOT include a re-render in the same
  action response" for certain cache-life profiles. This constraint does not apply to
  `revalidatePath`, which is what the question and this repo's precedent both use.
- No live-browser (Playwright) regression test in this repo currently asserts the
  `calendar-sync` page's own UI updates without a refresh — `web/tests/airbnb-calendar-sync.test.ts`
  tests `syncAirbnbCalendar`'s server-side logic only, not the client DOM refresh behavior.
  The "no `router.refresh()` needed" conclusion here is grounded in source-code tracing +
  docs, not an existing live-DOM assertion in this repo. Per this project's own standing
  practice (live-browser testing catches bugs test suites miss), recommend a quick manual/
  Playwright live check of `/inbox` after wiring `revalidatePath` in — approve/discard/
  regenerate a draft and confirm the list/thread panes update without a manual page reload —
  before treating this as fully closed, rather than trusting the source trace alone.

## not_found

- No official Next.js release note/changelog (15.x→16.x) explicitly documents a behavioral
  CHANGE to how the action-response protocol interacts with `useActionState` — the
  docs' "single response carries data and UI" framing may be a clarification of
  always-existing behavior rather than a version-introduced change; not resolved by this
  pass (angle 1's gap, not independently closed here).
- No Vercel/React RFC or PR description was located that names the Flight-stream separation
  of "return value vs RSC payload" as an explicit design decision — only the docs prose and
  source code itself were locatable/verifiable.
- No live-DOM (Playwright/browser) test exists in this repo today confirming the
  `calendar-sync` UI actually refreshes without `router.refresh()` in a running browser — the
  conclusion rests on source-code tracing + the absence of a `.refresh()` call in shipped,
  presumably-working code, not an executed live assertion. If Oga wants zero remaining
  doubt before wiring `/inbox`, a short live-browser check of the calendar-sync page (already
  shipped) would close this gap cheaply, before or instead of testing the new `/inbox` wiring
  in isolation.

## In-repo precedent scan (redo, resolves prior degenerate attempt)

Ran against `<HOME>/Claude/Projects/padsplit-cockpit-worktrees/inbox-revalidate`
(an isolated git worktree checked out at the same commit as the main `padsplit-cockpit` repo).
Two bounded steps only, no sub-delegation.

### Step 1 — repo-wide grep: useActionState invocation + revalidatePath/revalidateTag

`grep -rln "useActionState" web/src --include="*.tsx"` returns exactly 4 files:
- `web/src/app/inbox/components/DiscardButton.tsx` (calls `discardDraft`)
- `web/src/app/inbox/components/RegenerateButton.tsx` (calls `generateDraft`)
- `web/src/app/inbox/components/ApproveDraftForm.tsx` (calls `approveDraft`)
- `web/src/app/dashboard/calendar-sync/components/CalendarLinkForm.tsx` (calls `saveCalendarLink` and `syncNowAction`)

Checked the action files each imports from:
- `web/src/app/inbox/actions.ts` (507 lines, defines `generateDraft`, `discardDraft`,
  `approveDraft`) — `grep -in "revalidate"` returns **zero matches**. None of these three
  inbox actions call `revalidatePath`/`revalidateTag` at all. The three inbox
  `useActionState` usages satisfy (a) invocation-via-`useActionState` but fail (b)
  revalidation-on-success.
- `web/src/app/dashboard/calendar-sync/actions.ts` (206 lines) — `saveCalendarLink`
  (line 163) and `syncNowAction` (line 197) both call
  `revalidatePath('/dashboard/calendar-sync')` inside a try/catch, on the success path.

**Only `calendar-sync/actions.ts` satisfies both (a) and (b) anywhere in the repo** — no
other precedent exists. Also confirmed via `grep -rn "router.refresh"` across both
`web/src/app/dashboard/calendar-sync/` and `web/src/app/inbox/`: zero matches in either —
no `router.refresh()` call exists in either chain.

### Step 2 — plan_check_log.md round 22 + ac7_ui_evidence.md

`ac7_ui_evidence.md` **does not exist** anywhere under
`~/Claude/loop/runs/2026-07-04_airbnb-calendar/` — confirmed by `find` (only 4 files exist
in that run dir: `specs/spec.md`, `CONTINUATION_PROMPT_known_issues_fix.md`,
`plan_check_log.md`, `trace.jsonl`) and by a recursive grep for the literal string
`ac7_ui_evidence`, which returns no hits at all, even as a reference. There is no
UI-evidence artifact to read.

Round 22 of `plan_check_log.md` (lines 1748–1829) ran 5 parallel plan-check lenses: 2
PASS, 3 FAIL. The **state-transition-table** lens (lines 1785–1797) is the one that speaks
directly to this question. Verbatim quote:

> "Additionally raised a genuine KNOWLEDGE gap: no verified claim backs the assumption that
> a `useActionState` submission refreshes the page-load-sourced health display, and no
> `revalidatePath`/`router.refresh` precedent exists anywhere in the real codebase."

This is an explicit, on-the-record **denial** of precedent as of round 22 — the plan-check
process itself found no such refresh mechanism proven to exist anywhere in the repo at that
point in the build.

The round-22 fix applied for revision 23 (`plan_check_log.md` lines 1809–1827) was:
> "Both actions now call `revalidatePath('/dashboard/calendar-sync')` explicitly on success,
> closing the unverified implicit-refresh KNOWLEDGE gap rather than asserting an unproven
> runtime claim."

This is a **spec-authoring decision** (write the explicit call into the plan) — it resolves
the ambiguity about what code to write, but it is not itself a live-browser verification
that the resulting UI actually refreshes.

**Was the round-22 gap ever later resolved?** Grepped the rest of `plan_check_log.md` and
the other files in the run directory for `revalidatePath`, `router.refresh`, `live-verif`,
`browser`, `dev server`, `AC7`:
- Later rounds (26, 27, 28, 30) found and fixed a separate, real bug: a missing
  `revalidatePath` **import** (line 2104: `revalidatePath` import added, confirmed against
  `node_modules/next/cache.d.ts`) — a code-correctness fix, not a UI-refresh-behavior
  verification.
- The plan-check loop's final entry (round 31, `plan_check_log.md` lines 2523–2549) is a
  **process pivot decision by Nnamdi**:
  > "STOP the prose plan-check loop... carried forward as an explicit implementation note
  > for the Coder, to be caught/verified via real `next build`/`tsc`/live browser testing
  > instead of another round of lens dispatches... with REQUIRED real-build verification
  > (`next build`, `tsc --noEmit`) plus the mandatory live-browser check
  > (`H-BROWSER-UI-CHECK-MISSING-1`) before considering this slice done."

  This is where `plan_check_log.md` **ends** — it hands the live-browser obligation to a
  downstream Coder/build phase but records no outcome of that check itself. No `run_log.md`
  exists anywhere in the run directory.
- `CONTINUATION_PROMPT_known_issues_fix.md` line 4 — written after that handoff, as
  background context for a later bug-fix pass — states: "a manual live-browser click-through
  confirmed the feature works end-to-end" alongside "99/99 automated tests passing" and
  clean `tsc`/`next build`. This is the only trace in the run directory of a live-browser
  pass having occurred. It is a terse, unsourced summary sentence in a prompt written for a
  different downstream agent (a known-issues bug-fix pass) — it does not cite what
  specifically was clicked through, does not isolate or confirm the
  `revalidatePath`-without-`router.refresh` UI-refresh mechanism as the thing checked, and
  no evidence file (the promised `ac7_ui_evidence.md` was never created) substantiates that
  specific claim with concrete steps/screenshots/DOM state.

### Exact citations
- `web/src/app/dashboard/calendar-sync/components/CalendarLinkForm.tsx` lines 29–37
  (`useActionState` calls) — no `router.refresh()` anywhere in file.
- `web/src/app/dashboard/calendar-sync/actions.ts` lines 7, 158–166 (`saveCalendarLink`'s
  `revalidatePath` call), 192–200 (`syncNowAction`'s `revalidatePath` call).
- `web/src/app/inbox/actions.ts` — confirmed zero `revalidate*` calls (grep exit 1, no
  matches).
- `~/Claude/loop/runs/2026-07-04_airbnb-calendar/plan_check_log.md` lines 1785–1797 (round
  22 state-transition-table KNOWLEDGE-gap finding), lines 1809–1827 (revision-23 fix), lines
  2523–2549 (round 31 STOP decision, handoff to live-browser check).
- `~/Claude/loop/runs/2026-07-04_airbnb-calendar/CONTINUATION_PROMPT_known_issues_fix.md`
  line 4 (unsourced "manual live-browser click-through confirmed" claim).

### Bottom line

Real in-repo precedent for the **code pattern** exists — `calendar-sync/actions.ts` +
`CalendarLinkForm.tsx` is a genuine, shipped example of a Server Action invoked via
`useActionState` that calls `revalidatePath` on success with no `router.refresh()` anywhere
in the chain, and it is the only such example anywhere in `web/src` (the three `inbox/`
`useActionState` usages call actions that never revalidate at all). But no rigorous,
live-verified precedent exists for the **refresh behavior** specifically: the build's own
plan-check process explicitly flagged this exact mechanism as an unverified KNOWLEDGE gap at
round 22, closed it only by adding the code (not by proving it works), deferred the mandatory
live-browser check to a downstream build phase at round 31, and the only subsequent claim of
a live-browser pass is one unsourced sentence in a later continuation prompt — with the
evidence file that was supposed to document it (`ac7_ui_evidence.md`) never created.
