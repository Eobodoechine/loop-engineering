# Slice 6 domain research — Airbnb sync + message-thread scraper (padsplit-cockpit)

**Mode:** D (domain research for a build). **Date:** 2026-07-04. **Researcher:** leaf worker, no sub-dispatch.
**Consumes:** `~/Claude/loop/runs/2026-06-30_crm-spec/MVP_PLAN.md` §9 item 6 (line 165-167).
**Feeds:** the not-yet-written Slice 6 spec (Airbnb sync + message-thread scraper), same 15-round
adversarial plan-check process as Slice 4 (`~/Claude/loop/runs/2026-07-03_ai-draft-approve/specs/spec.md`).

---

## 0. Repo grounding done first (read before any external research)

Direct reads, not guessed:
- `<HOME>/Claude/Projects/padsplit-cockpit/web/prisma/schema.prisma` (full, 482 lines)
- `<HOME>/Claude/Projects/padsplit-cockpit/extension/content/padsplit.js` (full)
- `<HOME>/Claude/Projects/padsplit-cockpit/extension/content/airbnb.js` (full)
- `<HOME>/Claude/Projects/padsplit-cockpit/extension/manifest.json` (full)
- `<HOME>/Claude/Projects/padsplit-cockpit/extension/background.js` (full)
- `<HOME>/Claude/Projects/padsplit-cockpit/web/src/app/api/sync/airbnb/route.ts` (full)
- `~/Claude/loop/runs/2026-07-03_ai-draft-approve/specs/spec.md` (Slice 4 spec, PadSplit message-sync architecture)
- `~/Claude/loop/runs/2026-06-30_crm-spec/MVP_PLAN.md` (full)

### CORRECTED SCOPE FINDING — MVP_PLAN.md's premise about Airbnb is stale; more already exists than the plan or the dispatch brief assumes

The dispatch brief and MVP_PLAN §3/§8.4 both say the Airbnb scraper "does not exist" / only reads
an unread count. **This is only half true today.** Verified by direct read:

- `extension/content/airbnb.js` **already exists** and is a real, working (if basic) content script:
  it scrapes `/hosting/listings` (via Airbnb's `__NEXT_DATA__` JSON blob, with a DOM-text fallback),
  `/hosting/calendar` (blocked/unavailable date cells), and `/hosting` (`extractToday()` — unread
  message COUNT and upcoming-reservation COUNT only, confirming the plan's one true claim).
- `extension/manifest.json` already registers content-script matches for
  `https://www.airbnb.com/hosting*`, `/hosting/listings*`, `/hosting/calendar*`, and already lists
  `https://www.airbnb.com/*` as a host permission.
- `extension/background.js` already routes `AIRBNB_DATA` messages to a real endpoint,
  `/api/sync/airbnb`, distinct from the PadSplit endpoint.
- `web/src/app/api/sync/airbnb/route.ts` **already exists** and already handles `airbnb_listings`
  (upserts a `Property` row with `platform: 'AIRBNB'`), while `airbnb_today` and `airbnb_calendar`
  are stubbed to `{ ok: true }` (accepted, not yet persisted anywhere).
- **What genuinely does NOT exist** (confirming the one part of the plan that IS still accurate):
  no message-THREAD content extractor for Airbnb (nothing reads individual message bubbles/content
  the way `extractCommunication()` does for PadSplit), no `CalendarEvent`/`Reservation`-equivalent
  Prisma model or sync-route branch for calendar data (the `airbnb_calendar` stub discards
  `blockedDates` on the floor), and no Airbnb `Conversation`/`Message` rows are ever created.

**Consequence for the spec-writer:** Slice 6 is a genuine EXTENSION of an already-half-built Airbnb
sync pipeline, not a green-field build. Scope should be framed as "close the calendar-persistence and
message-thread gaps in the existing Airbnb sync path," parallel to how Slice 4 found PadSplit's
`communication` page was scraped but never wired to a backend branch. The spec-writer must re-verify
this repo state fresh at spec time (this is a live codebase; state may have moved) rather than trusting
MVP_PLAN.md's now-stale framing.

---

## Question 1 — RentTools.io: real product? Public source? Is `ical.ts`/`calendar-sync.ts` real?

**Answer: YES — RentTools.io is real, MIT-licensed, and BOTH named files exist verbatim, with content
verified by direct fetch (not a WebFetch summary I trusted blind — the GitHub REST API confirms the
repo and I pulled raw file bytes).**

- **Site:** https://renttools.io/ — "Free, open-source property manager for short-term rental hosts."
  States: "MIT-licensed on GitHub. Read the code, file an issue, or self-host on any $4 droplet."
- **Repo:** https://github.com/Gribadan/RentTools.io — confirmed live via direct `curl` (HTTP 200) and
  the GitHub REST API (`api.github.com/repos/Gribadan/RentTools.io`, not a WebSearch snippet):
  - `full_name: Gribadan/RentTools.io`, `private: false`, `fork: false`
  - `description`: "Free, open-source property manager for short-term rental hosts. Sync Airbnb +
    Booking.com calendars, automate cleaning schedules, extract guest passport data. Live at renttools.io."
  - `license.spdx_id: MIT`
  - `default_branch: master` (NOT `main` — the first tree-fetch attempt 404'd on `main`, a real gotcha
    worth flagging to whoever next clones this)
  - `stargazers_count: 10`, `pushed_at: 2026-07-03T06:31:06Z` (pushed to **yesterday**, actively maintained)
  - `size: 13325` KB — a substantial, real codebase, not a stub
- **`src/lib/ical.ts` — confirmed real, fetched in full (235 lines)**, raw URL
  `https://raw.githubusercontent.com/Gribadan/RentTools.io/master/src/lib/ical.ts`. It is a
  dependency-free iCal (.ics) parser/generator:
  ```ts
  export interface ICalEvent {
    uid: string;
    summary: string;
    startDate: string; // YYYY-MM-DD
    endDate: string;   // YYYY-MM-DD
  }
  export function parseICal(icalText: string): ICalEvent[] { ... }
  export function addDays(dateStr: string, days: number): string { ... }
  export function generateICal(events: ICalEvent[], calendarName = "RentTools Sync"): string { ... }
  ```
  Parses `BEGIN:VEVENT`/`END:VEVENT` blocks, unfolds continuation lines per the iCal line-folding spec,
  extracts `UID`/`SUMMARY`/`DTSTART`/`DTEND`, and normalizes both `VALUE=DATE` and `DATE-TIME` forms to
  `YYYY-MM-DD`. This is a genuinely minimal, readable reference implementation — a good pattern to copy
  (or port near-verbatim) rather than reinvent, and small enough that the Coder can read the whole file.
- **`src/lib/calendar-sync.ts` — confirmed real, fetched in full (381 lines)**, raw URL
  `https://raw.githubusercontent.com/Gribadan/RentTools.io/master/src/lib/calendar-sync.ts`. Key
  exported function, `syncAllCalendars(opts?: { propertyIds?: number[] })`:
  - Fetches each property's `CalendarLink.icalExportUrl` with a 15s abort-controller timeout and a
    real `User-Agent` header, validates the response contains the literal string `"VCALENDAR"` before
    parsing (a cheap but real defense against a broken/HTML error page silently "succeeding").
  - Groups links by `propertyId` so it can log/report per-property; supports being called for ALL
    properties (the cron path) or a scoped subset (the manual "Sync now" button path) via
    `propertyIds` — directly analogous to padsplit-cockpit's existing host-driven ("visits the page,
    extension scrapes") vs. potential-future-cron distinction.
  - Tracks `failureCount`/`lastError`/`lastFetchedAt` on `CalendarLink` and logs to a `SyncLog` table —
    same idiom padsplit-cockpit's own `SyncLog` model (`schema.prisma:332-342`) already uses.
- **`prisma/schema.prisma` — confirmed real, fetched in full (568 lines)**, raw URL
  `https://raw.githubusercontent.com/Gribadan/RentTools.io/master/prisma/schema.prisma`. Relevant models
  (see Question 5 for the full modeling-tension analysis):
  ```prisma
  model Property {
    id  Int @id @default(autoincrement())
    ...
    reservations   Reservation[]
    calendarLinks  CalendarLink[]
    calendarEvents CalendarEvent[]
  }
  model CalendarLink {
    id Int @id @default(autoincrement())
    propertyId Int
    property   Property @relation(fields: [propertyId], references: [id], onDelete: Cascade)
    platform      String   // "airbnb" or "booking"
    icalExportUrl String
    bufferBefore  Int @default(1)
    bufferAfter   Int @default(1)
    lastFetchedAt DateTime?
    lastError     String?
    failureCount  Int @default(0)
  }
  model CalendarEvent {
    id Int @id @default(autoincrement())
    propertyId Int
    property Property @relation(fields: [propertyId], references: [id], onDelete: Cascade)
    platform  String
    uid       String   // iCal event UID
    summary   String @default("")
    startDate String   // YYYY-MM-DD
    endDate   String   // YYYY-MM-DD
    @@unique([propertyId, platform, uid])
  }
  model Reservation {
    id Int @id @default(autoincrement())
    name String
    checkIn  DateTime
    checkOut DateTime
    platform String @default("airbnb")
    linkedEventUid String?
    propertyId Int
    property Property @relation(fields: [propertyId], references: [id], onDelete: Cascade)
    guests Guest[]
  }
  ```

**Maturity signal:** single-author (`Gribadan`), 10 stars, MIT, actively pushed as of yesterday, real
CI (`.github/workflows/ci.yml`, `deploy.yml`, dependabot configured). Not enterprise-scale, but a live,
working, self-hosted product with paying-adjacent usage (it markets a hosted `renttools.io` product) —
this is meaningfully more credible than a pure research/toy repo, though still a small solo project and
should be treated as "reference implementation to port from," not "dependency to install."

**No alternative proposed** — the exact-named files exist and are directly usable/portable; I did not
find a reason to look further. (I did not exhaustively survey every other open-source iCal-sync engine
since RentTools.io's own code cleanly satisfies the ask; if a future pass wants a second opinion,
`ical-generator`/`node-ical` on npm are the standard off-the-shelf libraries or dependencies most other
STR tools reach for instead of a hand-rolled parser — noted for completeness, not verified line-by-line
here since RentTools.io's own hand-rolled version already meets the bar and needs no new dependency.)

---

## Question 2 — open-hotel-pms: real repo? Per-room + Membership + property_id?

**Answer: A real repo BY THIS EXACT NAME exists — `peeraseepat-cell/open-hotel-pms` — but it is a
genuine per-room NIGHTLY hotel PMS with NO "Membership" concept and NO `property_id` field anywhere
(single-hotel, not multi-property). The plan's "replace nightly w/ open-ended Membership; +property_id"
framing describes work the SPEC must invent, not something already built in this repo to copy.**

### Two same-ish-sounding false leads ruled out first (important — don't let a future pass rediscover these)
1. **`github.com/open-hotel` org** (`open-hotel-client`, 113 stars, TypeScript) — confirmed via GitHub
   API to be **"A Habbo Client developed in HTML5 Canvas by Open Hotel"** — a Habbo-Hotel-style
   social-network/game emulator (`orion-emulator` = "JavaScript Habbo Emulator"), completely unrelated
   to property management. The word "hotel" here means the 2000s virtual-world game, not lodging. Ruled
   out by reading the org's repo list and descriptions directly, not by name alone.
2. **OpenHotel PMS (openhotel.com)** — a real, but **proprietary/commercial** hotel PMS/channel-manager
   product (confirmed via SoftwareAdvice/HotelTechReport listings and the vendor's own site). No public
   GitHub repo. Do not conflate this vendor name with the open-source repo below — they are unrelated
   entities that happen to share "OpenHotel" branding.

### The real match: `peeraseepat-cell/open-hotel-pms`
- Confirmed via GitHub REST search (`api.github.com/search/repositories?q=open-hotel-pms+in:name`,
  `total_count: 3`, top hit is the exact-name match) and then confirmed by opening the repo directly.
- **README** (fetched raw, `raw.githubusercontent.com/peeraseepat-cell/open-hotel-pms/main/README.md`):
  > "Open Hotel PMS is a full property-management system designed around how a small hotel **actually
  > runs a shift**... It has been in daily production use at an independent hotel since March 2026, and
  > is developed iteratively by an AI-agent engineering workflow."
  > "This is a **sanitized public release**. Hotel-specific branding, logos, photos, and real contact
  > data have been removed, and the seed room map / pricing in `supabase/seed.sql` is generic example
  > data."
  Stack: **Next.js (App Router) + TypeScript + Supabase (Postgres/Auth/RPC) + Tailwind** — NOT Prisma
  (a real mismatch with padsplit-cockpit's own stack — see caveat below).
- **Maturity signal — mixed, worth flagging honestly:** `stargazers_count: 0`, `forks: 0`,
  single-author, MIT license, **`created_at: 2026-06-02T06:08:59Z`, `pushed_at: 2026-06-02T07:45:58Z`**
  — i.e. the entire visible git history on GitHub spans under two hours on a single day roughly a month
  ago, with zero external engagement (0 stars/forks). This reads like a single bulk-upload snapshot of
  a private/local project's history rather than an actively-developed-in-public repo — the README's
  "in daily production use since March 2026" and "developed iteratively" claims describe development
  that happened BEFORE or OUTSIDE this public mirror, not development visible in this repo's own commit
  timeline. Treat the "production-grade, actively developed" self-description as **unverified beyond
  the code's own internal complexity** (which is real and substantial — 186+ SQL migration files) —
  there is no independent evidence (stars, forks, issues, external contributors, a commit cadence) that
  this is maintained or supported going forward. This is meaningfully weaker provenance than RentTools.io's.
- **Schema — real per-room, NIGHTLY reservation model**, confirmed by fetching the actual base migration
  `supabase/migrations/20260219_000001_init_core.sql` in full (raw URL:
  `raw.githubusercontent.com/peeraseepat-cell/open-hotel-pms/main/supabase/migrations/20260219_000001_init_core.sql`):
  ```sql
  create table if not exists public.rooms (
    id uuid primary key default gen_random_uuid(),
    room_number text not null unique,
    room_type_id bigint not null references public.room_types (id),
    is_sellable boolean not null default true,
    is_visible_on_board boolean not null default true,
    closure_reason text,
    ...
  );

  create table if not exists public.reservations (
    id uuid primary key default gen_random_uuid(),
    booking_code text not null unique,
    guest_name text not null,
    phone text,
    source public.booking_source not null default 'walkin',
    status public.reservation_status not null default 'active',
    checkin_date date not null,
    checkout_date date not null,
    ...
    constraint reservation_date_range check (checkout_date > checkin_date)
  );

  create table if not exists public.reservation_nights (
    id uuid primary key default gen_random_uuid(),
    reservation_id uuid not null references public.reservations (id) on delete cascade,
    room_id uuid not null references public.rooms (id),
    stay_date date not null,
    nightly_price numeric(10, 2) not null default 0,
    is_ota boolean not null default false,
    cancelled_at timestamptz,
    ...
  );

  create unique index if not exists uq_reservation_nights_active_room_day
    on public.reservation_nights (room_id, stay_date)
    where cancelled_at is null;
  ```
  This confirms `rooms` (per-room, not per-listing) and a genuine **nightly** granularity —
  `reservation_nights` is literally one row per room per calendar date, with a partial unique index
  preventing double-booking a room on a given night. This is exactly the "nightly" model the plan's
  phrasing ("replace nightly w/ open-ended Membership") refers to wanting to replace.
- **`Membership` — confirmed ABSENT.** `grep -i membership` across the full 186+ file migration tree
  (captured via the GitHub Git Trees API) returns zero hits. There is no membership, subscription, or
  open-ended-occupancy concept anywhere in this repo — every stay is a dated `reservation` +
  `reservation_nights` row with a `checkin_date`/`checkout_date`.
- **`property_id` — confirmed ABSENT.** This repo is single-hotel (its own README: "independent
  hotels," singular use case, `rooms.room_number` is globally unique with no property scoping column
  anywhere in the base schema or in the 186 later migrations I filename-scanned for `room`/`property`).
  There is no multi-tenant/multi-property dimension in this codebase at all.

**What this means for the spec-writer, stated plainly:** MVP_PLAN.md's phrase "Per-room model ←
open-hotel-pms (replace nightly w/ open-ended Membership; +property_id)" should be read as **"borrow
the per-room + nightly-reservation MODELING PATTERN from open-hotel-pms as a reference for how to shape
a room-scoped booking record, then design a NEW `Membership`-like open-ended-occupancy concept and a NEW
`property_id` scoping column yourself"** — not "copy a Membership+property_id feature that already
exists in this repo." Neither exists there. This is exactly the kind of unverified/aspirational planning
language the dispatch brief warned about — the original research that produced this MVP_PLAN line
appears to have named a real repo for the per-room PART but extrapolated the Membership/property_id part
without it actually being present, and never left a paper trail distinguishing "found in the repo" from
"proposed as new work." Flag this explicitly in the spec so the next reader doesn't assume it's a port.

**Practical portability caveat:** open-hotel-pms is Supabase-native raw SQL + RPC, not Prisma. Porting
its SCHEMA IDEAS (room table shape, per-night uniqueness constraint pattern) into padsplit-cockpit's
existing Prisma schema is straightforward (translate the SQL DDL intent into Prisma model syntax); porting
actual CODE (its RPC functions, Supabase-specific auth/RLS patterns) is not directly reusable since
padsplit-cockpit already has its own Postgres-RLS-via-Prisma pattern (`forOrg()`/`db-rls.ts`, per the
Slice 4 spec) that is architecturally different from Supabase's built-in RLS+RPC model. Treat
open-hotel-pms as **read for the schema shape, not copy-pasted for the code.**

---

## Question 3 — Airbnb host messaging: real DOM shape, prior art, ToS/detection risk

### 3a. DOM structure — no confirmed, currently-accurate public source found; treat as unverified until live-checked

I could not find a reliable, dated, structurally-detailed public description of the current (2026)
`airbnb.com/hosting/messages` (or `messages.airbnb.com`) DOM shape — Airbnb is a heavily-obfuscated
React SPA that "changes their website structure often" (confirmed by a scraping-vendor source, ScrapingBee,
though that source covers public listing pages, not the private host inbox specifically) and no source I
found gives a class-name/selector-level breakdown of the messages UI the way this project's own
`padsplit.js`/`airbnb.js` already do for PadSplit/Airbnb listings pages. **This is a genuine "not found,"
not a soft-pedaled guess** — stating it plainly per the honesty-bar rule rather than fabricating a
plausible-sounding selector list the way the existing `airbnb.js` fallback regexes were clearly derived
from someone actually looking at the live page (the plan-check process should require the same: whoever
builds this must open a real logged-in Airbnb host account and inspect the DOM directly, exactly as the
Slice 4 spec flagged as an "open item requiring live verification" for PadSplit's own communication page
timestamp format).

What I DID confirm, functionally (from Airbnb's own Help Center / Resource Center, not scrapers):
- The Messages tab groups conversations into categories: **Homes, Experiences, Services, Traveling,
  Support, Direct Messages** — https://www.airbnb.com/help/article/3558 ("Manage all your Airbnb messages").
- **Each reservation starts its own conversation thread** — https://www.airbnb.com/resources/hosting-homes/a/getting-the-most-out-of-the-messages-tab-678
  states additional invited guests are added to that SAME reservation's thread, and hosts/co-hosts/guests
  message within "a single thread." This is structurally the same "one Conversation per booking/tenancy"
  shape padsplit-cockpit's `Conversation` model already assumes (`@@unique([contactId, channel])`), which
  is a good sign for reuse — see Question 5.
- Filters exist for unread/trip-stage/listing/starred (https://www.airbnb.com/help/article/3558), meaning
  a content script could plausibly navigate to an "unread" filtered view to reduce scrape volume, the same
  way the existing `extractToday()` already reads an "N unread messages" summary string.
- Read receipts and "threaded replies" (nested sub-threads) exist per the Resource Center article — a
  potential DOM-complexity gotcha (a message thread may not be a flat list of bubbles the way PadSplit's
  `extractCommunication()` assumes) that whoever builds the scraper needs to account for; flagged as an
  open question, not resolved here.

### 3b. Published open-source Airbnb inbox/message scraper — none found

I searched specifically for an open-source project scraping the private host-messages inbox (as opposed
to public listing/review data, which many commercial and open-source scrapers exist for —
`dtrungtin/actor-airbnb-scraper` on GitHub, Apify's `tri_angle/airbnb-scraper`, etc. — all public-page
scrapers, not messaging). **None of the search results surfaced a maintained open-source Airbnb
host-inbox scraper.** This matches the MVP_PLAN's own claim ("Airbnb message threads are NOT captured
yet... a new thread scraper first") — confirmed as still true industry-wide, not just true of this repo.
The nearest commercial analogues (Hospitable, Enso Connect, HostAI — all cited in MVP_PLAN §1/§2 from
prior research) are closed-source SaaS products; none publish their scraping/integration mechanism, so
they cannot be "learned from" beyond their marketing claims already folded into MVP_PLAN.

### 3c. ToS and automated-access risk — real, confirmed, directly applicable

Airbnb's own live Terms of Service (fetched directly, https://www.airbnb.com/help/article/2908, Section
11.1, "Do not scrape, hack, reverse engineer, compromise or impair the Airbnb Platform"), quoted verbatim:

> "Do not use bots, crawlers, scrapers, or other automated means to access or collect data or other
> content from or otherwise interact with the Airbnb Platform."

This is an unqualified prohibition in the text — it does not carve out an exception for a host reading
their OWN account data via a personal browser extension content script (as opposed to a third-party
scraping someone else's public listings). **This is the exact same ToS exposure the existing PadSplit
scraper already carries** — nothing about Slice 6 introduces a NEW category of risk relative to what
`extension/content/padsplit.js` already does today; it is the same mechanism (a content script reading
DOM the logged-in host's own browser already rendered, then POSTing structured data to this app's own
backend) applied to a second platform. Per the "Transfer-condition check" required by my role brief:
- **(a) Execution context the mechanism requires:** a logged-in human host manually navigating to the
  page in their own browser with the extension installed — NOT headless automation, NOT a background
  cron hitting Airbnb's servers unattended. This distinction matters because it is the same one this
  project's own architecture already relies on for PadSplit (host-driven sync cadence, not fixed/scheduled)
  and it is consistent with how Airbnb's own detection systems are described (see below) as targeting
  automated/bot-like ACCESS PATTERNS, not merely "any script touched the DOM."
- **(b) Does padsplit-cockpit's Airbnb extension satisfy that context?** Yes, by construction —
  `extension/manifest.json`'s `content_scripts` only match specific `/hosting*` paths and run at
  `document_idle` when the host is already on the page; there is no polling/auto-navigation. This is
  the same low-risk shape as the existing PadSplit scraper.
  Airbnb's account-security messaging (https://news.airbnb.com/prevent-account-takeovers/) describes
  Airbnb "automated processes that analyze account activities" to catch risk signals, but this describes
  fraud/takeover detection, not specifically anti-scraping bot detection of a host's own logged-in
  session — I could not find Airbnb-specific public documentation of THIS distinction (attended
  extension-driven scraping of one's own data vs. detected "bot" access) being treated differently in
  practice; **this is a real unknown, not a confirmed safe harbor.** State this honestly to Nnamdi rather
  than implying the ToS risk is somehow smaller for Airbnb than it already is/was accepted to be for
  PadSplit — it is the SAME shape of risk, just a second platform's ToS now exposed to it.
- **(c) Structural or instructional guarantee?** Purely instructional — nothing in the extension's code
  or Airbnb's platform enforces "only run this while a human is actively looking at the page"; a
  modified/compromised build of this extension COULD be pointed at headless automation, and Airbnb has
  no way to distinguish that from the intended use except behavioral/rate signals it doesn't publish.
  This is the same residual risk profile as the already-accepted PadSplit scraper — not a new gap Slice 6
  introduces, but worth restating in the spec's risk section rather than silently assuming "we already do
  this for PadSplit so it's fine" without saying so.
- **Net recommendation for the spec-writer:** name this ToS exposure explicitly in Slice 6's spec (the
  same way MVP_PLAN §8 item 5 already flags "AI auto-send ToS on PadSplit/Airbnb — keep draft-approve
  until cleared" as an open risk) rather than treating a second platform's scraper as risk-neutral because
  the first one already shipped. Recommend keeping the same "host-triggered by visiting the page, never a
  background cron" pattern Slice 4 already established for PadSplit, for both risk-reduction and
  consistency.

---

## Question 4 — Airbnb iCal export: real feature, URL shape, what fields (guest info anonymized?)

**Confirmed real, standard, documented Airbnb host feature.**

- **Official doc:** https://www.airbnb.com/help/article/99 ("Sync your calendar to other websites").
  Confirms the export mechanism exists: hosts are given "a URL that you'll paste into the other
  website's calendar," and states the destination calendar reflects "nights that are blocked" or
  "booked" automatically as the Airbnb calendar changes. The WebFetch summary of this page was thin on
  exact URL syntax (Airbnb's help pages are themselves partly obfuscated/JS-rendered), so the URL shape
  below is corroborated from a secondary but consistent source rather than pulled from the primary page's
  visible text alone — flagged accordingly.
- **URL shape** (from a channel-manager integration knowledge base, Operto Teams —
  https://help-teams.operto.com/article/367-how-do-ical-feeds-import-bookings-blocks-and-guest-information —
  cross-checked against the general pattern independently described by multiple channel-manager docs in
  the same search batch, e.g. Beds24's wiki and OwnerRez's support article, all describing the same
  `.ics` URL convention consistently): a listing-specific URL of the form
  `https://www.airbnb.com/calendar/ical/{listingId}.ics?s={token}` — a numeric listing id plus an
  opaque signing token as a query parameter. **This specific URL string was reported by a secondary
  source, not independently re-derived by fetching a live feed myself in this research pass** (I have no
  Airbnb host account to pull a real feed from) — treat the exact query-param name (`s=`) as
  plausible-and-consistent-across-sources but not something I personally confirmed byte-for-byte against
  a live Airbnb response. The build should re-verify this against Nnamdi's own real Airbnb host account
  before hardcoding any URL-parsing assumption (same "live-verify before build" discipline MVP_PLAN §8
  already requires for the PadSplit SLA windows).
- **Guest info: NOT exposed in the iCal feed — this is Airbnb's OWN deliberate anonymization, not
  merely "not part of the iCal spec."** Multiple independent sources agree on this, converging on the
  same claim:
  - Operto Teams (https://teams-blog.operto.com/airbnb-changes-ical-calendar-export-feed-data-starting-december-1/):
    Airbnb changed its iCal export specifically to reduce guest-info exposure — the search summary states
    "Guest names, contact details, and reservation specifics are never surfaced in Airbnb's iCal export
    feeds... exported iCal events will no longer display reservation details," and separately notes
    Airbnb "only sends blocked dates and the last four digits of the guest's phone number" in some
    contexts (this second claim is less clearly sourced and may refer to a different Airbnb surface, not
    the iCal feed itself — flagged as the WEAKER of the two claims from that same source, don't treat it
    as confirmed for the iCal feed specifically).
  - The general iCal (RFC 5545) format ITSELF has no inherent restriction on `SUMMARY`/`DESCRIPTION`
    field content — other platforms' iCal exports (e.g., some smaller booking tools) DO put guest names
    in the `SUMMARY` field. **Airbnb's anonymization is a deliberate Airbnb PRODUCT decision on top of a
    format that would otherwise allow it, not an iCal-spec-level restriction** — this distinction matters
    for the spec-writer: don't write code that assumes "no guest name" is a property of the .ics format
    in general (RentTools.io's own `ICalEvent` interface, confirmed above, has a `summary: string` field
    that COULD carry a name from a non-Airbnb source), only that it's true of AIRBNB'S feed specifically.
  - **Practical consequence for Slice 6's data model:** an Airbnb iCal-synced reservation gives you
    stay dates (check-in/check-out) and, at most, an opaque or generic `SUMMARY` (commonly literally
    "Reserved" for Airbnb's feed, per common channel-manager documentation of the format, though I did
    not independently pull a live Airbnb feed to confirm the exact literal string) — **no guest name, no
    contact info, no reservation ID usable for message-thread correlation.** This means the iCal sync
    path and the message-thread-scraper path are NECESSARILY separate, uncorrelatable-by-default data
    sources for the same underlying booking unless a THIRD signal (matching by date range, or scraping
    the reservation's guest name separately from the messages/reservations UI, which Airbnb's normal
    hosting UI does show) is used to stitch them together. This is a real, concrete integration gap the
    spec must resolve explicitly (see Question 5) — it is not an incidental detail.
- **365-day forward window limit:** multiple sources (Beds24 wiki, general channel-manager docs)
  independently state the exported feed only includes reservations up to 365 days in the future — a
  minor but real constraint worth a code comment if the sync logic ever needs to reason about "is this
  feed exhaustive."

---

## Question 5 — Prisma schema implications: what changes/extends, and the PadSplit-vs-Airbnb modeling tension

### Current schema baseline (verified, `web/prisma/schema.prisma`)
- `Platform` enum today: **`PADSPLIT`, `AIRBNB`** (schema.prisma:130-133) — already has both values, so
  no enum change needed there; the dispatch brief's assumption that it's "currently just PADSPLIT" is
  itself slightly stale (already extended, likely during the CRM/Contact-model slice).
- `Property` (schema.prisma:111-128): already has a `platform: Platform` field and a `platformId`
  string — already shaped to hold an Airbnb listing as a `Property` row (and indeed
  `syncListings()` in the existing `/api/sync/airbnb/route.ts` already upserts exactly this way).
- `Room` (schema.prisma:135-158): `@@unique([propertyId, roomLabel])`, has `presenceState`,
  `occupiedSince` (single nullable timestamp — implies ONE current occupant/stay at a time per room).
- `Contact`/`Conversation`/`Message` (schema.prisma:386-481): already channel-agnostic in shape —
  `Conversation.channel: Platform`, `@@unique([contactId, channel])`; `Message.channel: Platform`. This
  is a meaningful existing strength: the Slice 4 architecture ALREADY generalizes across platforms at
  the Contact/Conversation/Message layer — Airbnb messages could flow into the exact same tables with
  `channel: 'AIRBNB'` with ZERO schema changes to those three models. This is the single biggest reason
  Slice 6 is tractable without a rewrite.
- **No `Reservation`/`CalendarEvent`/`CalendarLink`-equivalent model exists at all today.** This is the
  genuinely new surface area, confirmed absent by reading the full schema.

### The real modeling tension, stated explicitly (this is the load-bearing finding for the spec-writer)

**PadSplit's `Room.occupiedSince: DateTime?` (a single nullable timestamp) encodes an assumption that
does not hold for Airbnb: "a room has at most one ongoing (open-ended) occupancy at a time."** For
PadSplit this is true by construction — a member moves in and stays indefinitely (weeks/months) until
they move out; `Contact.currentRoomId` (a 1:1-ish pointer, enforced by `@@unique([orgId, currentRoomId])`
on `Contact`) is the "who's in this room right now" answer. Airbnb breaks this in two distinct ways:

1. **Multiple discrete FUTURE reservations can exist for the same room simultaneously** (a booking next
   week, another the week after) — this is normal and expected for STR, not an edge case. A single
   nullable `occupiedSince` field cannot represent "this room has 3 upcoming, non-overlapping bookings."
   You need a genuine one-to-many `Room → Reservation[]` (or `Property → Reservation[]`, see point 2)
   relationship with date ranges, which does not exist today.
2. **Reservations are date-ranged and TERMINATE on a known checkout date**, whereas PadSplit's
   `Contact`/`Member` relationship is open-ended until an explicit move-out EVENT fires
   (`OccupancyEventType.MEMBER_MOVED_OUT`). An Airbnb "Contact" (a guest) is fundamentally a
   **per-reservation** entity, not a **per-room, long-lived** entity the way a PadSplit member is —
   the same physical person could book the same room twice, six months apart, and (per MVP_PLAN §3's own
   stated scope decision) these might reasonably be treated as two separate Contact-adjacent records
   (or need a `kind: GUEST` + `stage`-based lifecycle distinct from `kind: MEMBER`'s, which the schema's
   `ContactKind` enum already anticipates: `MEMBER | GUEST | PROSPECT | PAST`, schema.prisma:358-363 —
   `GUEST` already exists as a value with no live writer yet, mirroring the exact "scaffolded but unused"
   pattern Slice 4 found for `Message.isDraft` before that slice wired it up).
3. **RentTools.io's own schema (Question 1) resolves this tension by NOT being per-room at all** — its
   `Property` model has no `Room`-equivalent child entity; a `Reservation` belongs directly to a
   `Property`. This works for RentTools's target user (a single-unit STR host) but is a WORSE fit than
   open-hotel-pms's per-room model for padsplit-cockpit's stated architecture (which already has
   `Room` as a first-class entity because PadSplit rents individual rooms within a property). **This is
   exactly why MVP_PLAN's own plan pulls the per-room pattern from a DIFFERENT source (open-hotel-pms)
   than the iCal-sync pattern (RentTools.io)** — the two reference repos solve two different sub-problems
   and neither one alone is a complete fit; the spec-writer needs to consciously combine ideas from both,
   not adopt either repo's full schema wholesale.
4. **The iCal-feed/message-thread correlation gap (from Question 4) compounds this**: even once a
   `Reservation` model exists, an iCal-synced reservation (dates only, no guest name) and a
   message-thread-scraped `Conversation` (has a guest name, from the Messages UI) are NOT automatically
   the same row without an explicit correlation strategy — likely date-range + property/room matching,
   done best-effort, with an explicit "confidence"/manual-link fallback. This is a genuinely open design
   question the spec must resolve, not a solved problem inherited from either reference repo (neither
   RentTools.io nor open-hotel-pms has this cross-source-correlation problem, because each gets its
   guest+dates from a SINGLE source of truth — RentTools.io only has the iCal feed with no separate
   messaging scrape at all; open-hotel-pms is a single in-house system with one database, not two
   external platforms to reconcile).

### Concrete, minimal-diff schema recommendation (a starting point for the Coder, not a final spec)
- Add a `Reservation` model (new, not touching existing `Room`/`Contact` shape): `id`, `orgId`,
  `roomId` (nullable — Airbnb `Property`-level bookings with no PadSplit-style room subdivision should
  still be representable; not every Airbnb property in this app will have `Room` rows), `propertyId`,
  `contactId?` (nullable — a reservation synced from iCal alone, before message-thread correlation,
  has no contact yet), `channel: Platform`, `checkIn: DateTime`, `checkOut: DateTime`,
  `externalUid: String?` (the iCal `UID`, for idempotent re-sync, mirroring RentTools's
  `@@unique([propertyId, platform, uid])` pattern on its `CalendarEvent`), `status` (an enum:
  something like `CONFIRMED | CANCELLED` at minimum), `source: EventSource`-like distinction between
  "came from iCal" vs "came from message-thread scrape."
- Do NOT repurpose `Room.occupiedSince`/`Contact.currentRoomId` for Airbnb — these are PadSplit-specific
  concepts (long-lived, singular). Leave them untouched; Airbnb occupancy lives entirely in the new
  `Reservation` model, keeping the two tenancy models cleanly separated rather than forcing one
  ill-fitting shape onto both (the plan's phrase "replace nightly w/ open-ended Membership" is, on this
  reading, backwards for padsplit-cockpit's actual needs — PadSplit is the open-ended side already
  modeled by `Contact`/`Room.occupiedSince`; Airbnb is the NEW nightly/dated side that needs its own
  model, not a replacement of the existing one).
- `Conversation`/`Message` need no schema change (channel-agnostic already) but DO need a policy decision
  on `contactId` when an Airbnb message thread arrives before any reservation/contact correlation is
  resolved — possibly a placeholder/thin `Contact` row created eagerly from the scraped guest name
  (mirroring how PadSplit's `syncMembers` already eagerly creates `Member`/`Contact` rows), reconciled
  to a `Reservation` later.

**This section is a research-informed hypothesis for the spec-writer to interrogate, not a finished
design** — in particular the nullable `roomId` on `Reservation` and the contact-correlation strategy are
exactly the kind of decision that should get its own explicit "Scope decisions for this slice" treatment
(the way Slice 4's spec numbered nine explicit scope decisions) and should go through the same
adversarial plan-check rounds, not be accepted as-is from this research pass.

---

## Honesty-bar summary (what's confirmed vs. what's flagged as unverified)

| Claim | Status |
|---|---|
| RentTools.io is real, MIT, public GitHub repo | CONFIRMED — direct API + raw file fetch |
| `src/lib/ical.ts` exists with this exact content | CONFIRMED — full file fetched, 235 lines |
| `src/lib/calendar-sync.ts` exists with this exact content | CONFIRMED — full file fetched, 381 lines |
| RentTools.io Prisma schema (`Property`/`CalendarLink`/`CalendarEvent`/`Reservation`) | CONFIRMED — full schema fetched, 568 lines |
| `open-hotel-pms` exact-name repo exists | CONFIRMED — `peeraseepat-cell/open-hotel-pms` |
| `open-hotel-pms` per-room + nightly reservation model | CONFIRMED — base migration SQL fetched and quoted |
| `open-hotel-pms` has NO Membership concept | CONFIRMED — zero grep hits across full migration tree |
| `open-hotel-pms` has NO `property_id` (single-hotel) | CONFIRMED — absent from base schema + not found in later migration filenames |
| `open-hotel-pms` "production, actively developed" self-claim | FLAGGED UNVERIFIED — repo's own git history is a ~2hr single-day snapshot, 0 stars/forks, no external signal of ongoing maintenance |
| `github.com/open-hotel` org is a Habbo game, not a PMS | CONFIRMED — org repo descriptions read directly |
| Airbnb `airbnb.com/hosting/messages` exact current DOM/selector shape | NOT FOUND — no dated, structurally-detailed public source located; must be live-verified against a real host account before the Coder builds selectors, same as Slice 4's own precedent for PadSplit's communication-page timestamp format |
| Published open-source Airbnb host-inbox message scraper | NOT FOUND — none located; nearest analogues are closed-source commercial SaaS (Hospitable/Enso/HostAI) |
| Airbnb ToS prohibits bots/scrapers/automated means | CONFIRMED — direct quote, Section 11.1, fetched from airbnb.com/help/article/2908 |
| Airbnb host-inbox-via-extension risk being materially different/safer than PadSplit's already-accepted risk | UNCONFIRMED — no Airbnb-specific public statement found distinguishing attended-extension use from bot detection; treat as same risk class, not a new or lesser one |
| Airbnb iCal export feature is real, documented | CONFIRMED — airbnb.com/help/article/99 |
| Exact Airbnb iCal URL shape (`/calendar/ical/{id}.ics?s={token}`) | PARTIALLY CONFIRMED — consistent across multiple secondary (channel-manager) sources, NOT independently re-derived from a live feed in this pass; re-verify against Nnamdi's real account before hardcoding |
| Airbnb iCal feed excludes guest name/contact info by design | CONFIRMED (cross-source agreement) — Operto Teams' documentation of Airbnb's Dec-2025-era change, consistent with the guest-privacy framing in AirROI's 2026 guest-screening article (though that article itself doesn't mention iCal specifically) |
| padsplit-cockpit already has a partial Airbnb sync pipeline (`airbnb.js`, `manifest.json`, `/api/sync/airbnb/route.ts`) | CONFIRMED — full files read directly; this contradicts the dispatch brief's implicit "nothing exists yet" framing and MUST be accounted for in the spec |
| `Platform` enum already includes `AIRBNB` (not "currently just PADSPLIT") | CONFIRMED — schema.prisma:130-133 |

---

## Sources (every URL actually opened this pass)

- https://renttools.io/ — RentTools.io marketing site, MIT/GitHub claim
- https://github.com/Gribadan/RentTools.io — repo (confirmed via `curl` + GitHub REST API)
- https://raw.githubusercontent.com/Gribadan/RentTools.io/master/src/lib/ical.ts — full file fetched
- https://raw.githubusercontent.com/Gribadan/RentTools.io/master/src/lib/calendar-sync.ts — full file fetched
- https://raw.githubusercontent.com/Gribadan/RentTools.io/master/prisma/schema.prisma — full file fetched
- https://github.com/peeraseepat-cell/open-hotel-pms — repo (confirmed via GitHub REST search API)
- https://raw.githubusercontent.com/peeraseepat-cell/open-hotel-pms/main/README.md — full README fetched
- https://raw.githubusercontent.com/peeraseepat-cell/open-hotel-pms/main/supabase/migrations/20260219_000001_init_core.sql — full base-schema migration fetched
- https://github.com/open-hotel (org page + repo list via API) — ruled out as unrelated (Habbo game)
- https://github.com/Qloapps/QloApps — surfaced as an alternative open-source hotel PMS, NOT deep-dived
  (open-hotel-pms was a closer name/shape match and was prioritized)
- https://www.airbnb.com/help/article/2908 — Airbnb Terms of Service (Section 11.1 bot/scraper clause, quoted verbatim)
- https://www.airbnb.com/help/article/99 — Airbnb calendar iCal export help article
- https://www.airbnb.com/help/article/3558 — "Manage all your Airbnb messages" (inbox categories/filters)
- https://www.airbnb.com/resources/hosting-homes/a/getting-the-most-out-of-the-messages-tab-678 — Messages tab / per-reservation threading
- https://news.airbnb.com/prevent-account-takeovers/ — Airbnb automated account-risk detection (fraud-focused, not scraping-specific)
- https://rankbreeze.com/airreview/ — real Airbnb host Chrome extension precedent (public-page only; no ToS-risk disclaimers found)
- https://teams-blog.operto.com/airbnb-changes-ical-calendar-export-feed-data-starting-december-1/ — Airbnb iCal guest-info anonymization change
- https://help-teams.operto.com/article/367-how-do-ical-feeds-import-bookings-blocks-and-guest-information — iCal URL shape corroboration
- https://www.airroi.com/blog/airbnb-guest-screening-privacy-era-2026 — guest-privacy context (did NOT confirm iCal specifics; noted as such)
- WebSearch queries (lead generation only, each lead re-opened above before citing): RentTools.io product search, "open-hotel-pms" github (multiple phrasings), open-source hotel PMS Prisma/TypeScript search, Airbnb host inbox DOM structure search, Airbnb iCal export search, Airbnb automation/ban risk search, Airbnb official API/partner program search, messages.airbnb.com structure search, Airbnb ToS scraping clause search.

## Not found / explicitly unresolved (hand back to Oga / spec-writer, not silently assumed)

1. **No independently-verified, current (2026) DOM/selector map for Airbnb's host messages UI.** Whoever
   builds the scraper must open a real logged-in Airbnb host account and inspect the DOM live — exactly
   the same live-verification step Slice 4 already required for PadSplit's `<time>` element format.
2. **No independently re-derived Airbnb iCal feed URL/content** — the URL shape and "no guest name" claim
   are corroborated across multiple secondary sources but not pulled from a live feed by this research
   pass (no Airbnb host account available to me). Re-verify against Nnamdi's real account before the
   Coder hardcodes any URL-parsing regex.
3. **Whether Airbnb's automated-risk detection treats attended-extension scraping of one's own account
   differently from bot-like access patterns** — no Airbnb-specific public statement found either way.
   State the ToS risk to Nnamdi as real and equivalent to the already-accepted PadSplit risk, not smaller.
4. **The precise guest-to-reservation correlation strategy** (iCal feed has dates but no name; message
   thread has a name but the thread's own reservation linkage/structure is itself unverified per point 1)
   is a genuine open design gap, not something either reference repo solves — flagged for the spec-writer
   to design explicitly as its own scope decision, the same weight Slice 4 gave its nine numbered scope
   decisions.
