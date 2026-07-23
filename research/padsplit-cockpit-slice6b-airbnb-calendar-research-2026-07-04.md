# Slice 6b domain research — Airbnb calendar/iCal sync + `Reservation` model (padsplit-cockpit)

**Mode:** D (domain research for a build). **Date:** 2026-07-04. **Researcher:** leaf worker, no sub-dispatch.
**Consumes:** `~/Claude/loop/runs/2026-07-04_airbnb-inbox/specs/spec.md` Context, scope decision #1 (the
three deferred risks that split Slice 6 into 6a/6b).
**Feeds:** the not-yet-written Slice 6b spec (calendar/iCal sync + `Reservation` model), same
adversarial plan-check process as Slices 4/6a.
**Ground rules honored:** no sub-agent dispatch (all WebSearch/WebFetch/file-reads done directly by
this worker); no live-DOM/live-account claims made (I have no browser access this dispatch — every
claim about the real Airbnb UI is sourced to "per Airbnb's own published Help Center HTML," never to
direct observation); real, opened URLs only, no fabricated citations.

---

## 0. Repo grounding done first (read before any external research)

Direct reads, not guessed:
- `<HOME>/Claude/Projects/padsplit-cockpit/web/prisma/schema.prisma` (full, 482 lines,
  re-read fresh for this dispatch — confirms the schema state described in the Slice 6a research is
  still current; no `Reservation`/`CalendarEvent`/`CalendarLink` model exists anywhere in it today).
- `~/Claude/loop/research/padsplit-cockpit-slice6-airbnb-research-2026-07-04.md` (Slice 6 pre-split
  research — RentTools.io / open-hotel-pms findings, the original modeling-tension analysis).
- `~/Claude/loop/research/padsplit-cockpit-slice6a-airbnb-messages-dom-2026-07-04.md` (Slice 6a's
  live-DOM dossier — specifically §10g's `reservation-dynamic-marquee-title-header-v3` /
  `hrd-sbui-header-section` findings, which this dossier's Question 2 builds on).
- `~/Claude/loop/runs/2026-07-04_airbnb-inbox/specs/spec.md` (the Slice 6a spec, now built/shipped
  as commit `219f9ad` — read in full for Context/scope-decision #1's exact framing of what Slice 6b
  must resolve).

---

## Question 1 — Where does a host find the Airbnb iCal export URL, and what does Airbnb's own documentation say the URL format is?

**Answer: confirmed directly from Airbnb's own live Help Center page HTML (not a WebFetch summary —
I downloaded the raw page and extracted the literal embedded content, including a machine-readable
`HowTo` JSON-LD block and the literal `<ol><li>` step text). Both a desktop and a mobile-browser
navigation path are given, word-for-word identical except "Click" vs. "Tap."**

### 1a. Exact navigation path (Airbnb's own words, both variants)

Source: `https://www.airbnb.com/help/article/99` ("Sync your home host calendar to other websites"),
fetched directly via `curl` with a browser User-Agent (not WebFetch's summarizer) on 2026-07-04, and
the two navigation sequences below extracted from the page's own embedded HTML (`<h3>Sync your
calendars on desktop</h3>` and `<h3>Sync your calendars on mobile browser</h3>` sections):

**Desktop** (exact quoted list items, in order):
1. `Click <a href="/hosting/calendar">Calendar</a> and select the listing calendar you want to change`
2. `Click **Availability**`
3. `Under **Connect calendars**, click **Connect to another website**`
4. `To export your calendar, copy the Airbnb calendar link, then paste it into your other iCal-based calendar`
5. `Next, to import a calendar, get a link ending in .ics from the other website and paste the URL into the calendar address field`
6. `Give the calendar a name and click **Add calendar**`

**Mobile browser** (same sequence, "Tap" instead of "Click," otherwise identical):
1. `Tap <a href="/hosting/calendar">Calendar</a> and select the listing calendar you want to change`
2. `Tap **Availability**`
3. `Under **Connect calendars**, tap **Connect to another website**`
4. `To export your calendar, copy the Airbnb calendar link, then paste it into your other iCal-based calendar`
5. `To import a calendar, get a link ending in .ics from the other website and paste the URL into the calendar address field`
6. `Name the calendar and then click Add calendar`

**A separate, machine-readable `HowTo` JSON-LD block on the SAME page (Google-rich-result markup,
not prose) independently corroborates the same skeleton**, for the "Refresh your imported calendar"
sub-flow (confirming "Availability" and "Connect calendars → Connect to another website" are stable,
reused UI landmarks across multiple flows on this page, not a one-off phrasing):
```json
{"name":"Refresh your imported calendar","step":[
  {"text":"Click Calendar and select the listing calendar you want to change","@type":"HowToStep"},
  {"text":"Click Availability","@type":"HowToStep"},
  {"text":"Under Connect calendars, click Connect to another website","@type":"HowToStep"},
  {"text":"Choose your imported calendar and click Refresh Calendar","@type":"HowToStep"}
],"@context":"https://schema.org","@type":"HowTo"}
```

**Practical takeaway for Oga's live verification pass**: the precise path per Airbnb's own copy is
**Calendar (`/hosting/calendar`) → select the listing → "Availability" tab/section → a "Connect
calendars" section → "Connect to another website" button** — NOT literally a page/button labeled
"Export Calendar" as several secondary sources phrase it (see 1b) — Airbnb's own copy uses "Connect
to another website" as the actual clickable control; "export" is the ACTION that control performs,
described in prose, not a separate menu item of its own on the live page per this source. The
internal link target `/hosting/calendar` is itself a concrete, checkable URL fragment Oga can visit
directly in Nnamdi's real host account.

### 1b. Secondary-source corroboration — largely consistent, with real terminology variance across vendors

Multiple independent, unaffiliated channel-manager/blog sources converge on the same functional
sequence, though none uses Airbnb's exact literal button copy verbatim — flagging this variance
explicitly rather than picking one phrasing and hiding the disagreement:
- Operto Teams (`help-teams.operto.com/article/610-airbnb-export-ical`): "Pricing and availability" →
  "Calendar sync" → "Export Calendar."
- hosttools.com (`hosttools.com/blog/airbnb-rentals/export-airbnb-calendar/`): "Go to 'Host' and
  click 'Calendar'... Under 'Sync calendars', click 'Export calendar'."
- A general search-engine synthesis (not independently opened/quotable as a single page) converged on
  "Host > Listing > Calendar, then click Availability settings, then Sync calendars."

**Assessment**: all three variants name the same functional landing spot (a "Calendar" page, then an
"Availability"-adjacent section, then a sync/connect/export control) but use different literal labels
("Sync calendars" vs. "Connect calendars," "Export calendar" vs. "Connect to another website"). This
is very plausibly explained by Airbnb having **renamed or restyled this control over time** (these
vendor articles are undated or older than the freshly-fetched Airbnb page) — the current, live
`airbnb.com/help/article/99` HTML (fetched today, 2026-07-04) is the most authoritative and most
recent single source I have, so its literal wording ("Connect calendars" / "Connect to another
website") should be treated as the current ground truth, with the other phrasings flagged as
plausible OLDER or VENDOR-PARAPHRASED labels for the same underlying control — Oga should expect the
literal live UI to say "Connect calendars" / "Connect to another website," and treat "Sync calendars"/
"Export calendar" as the older or colloquial name if the live UI doesn't match verbatim.

**Live verification addendum (Oga, 2026-07-04) — the navigation path above is now
directly confirmed, not just documented.** Navigated Nnamdi's real Airbnb host account:
`/hosting/calendar` → select a listing → "Availability" (real link, `href` confirmed) →
a "Connect calendars" section exists on the real Availability-settings page exactly as
cited, containing per-listing "Linked calendar" status rows and a "Connect another
calendar" link. Clicking that link reveals exactly two distinct real options: **"Connect
to another website"** (external iCal — matches this section's Help Center citation
verbatim) and **"Connect multiple Airbnb listings"** (Airbnb's own internal cross-listing
calendar linking — a DIFFERENT feature, already in active use on this real account:
"Serene Home in Central Atlanta," an Entire-home listing, has its calendar linked to 4
separate Private-room sub-listings within the same physical property — a live, concrete
example of the whole-home + per-room hybrid structure this project's schema must
support). **Not further verified, deliberately**: clicking into "Connect to another
website" itself was correctly blocked by the session's own safety classifier as an
unauthorized live configuration-change action on a real, production hosting account
(this could initiate or expose an actual external calendar connection) — the exact
`.ics?s={token}` URL format in §1c below therefore remains at the SAME confidence level
already stated there (corroborated from secondary sources, not directly observed). This
satisfies the `H-LIVE-VERIFY-COVERAGE-1` gate's intent for the NAVIGATION PATH claim
specifically (now exhaustively confirmed against the real UI) while being explicit that
the URL FORMAT claim's confidence is unchanged, not silently upgraded by association.

### 1c. Exact URL format

**Confirmed only as a secondary-source claim, consistent across multiple independent vendor sources,
NOT independently re-derived from a live feed by this research pass** (I have no Airbnb host account
access in this dispatch — same limitation as the original Slice 6 research):

> `https://www.airbnb.com/calendar/ical/{listingId}.ics?s={secretToken}` — e.g.
> `https://www.airbnb.com/calendar/ical/12345678.ics?s=abcdef123456`

This exact shape was repeated consistently across independent WebSearch result summaries citing
bnb-pilot.com and other host-education blogs, and matches the general pattern this project's own
prior Slice 6 research already found (Operto Teams, Beds24 wiki, OwnerRez support docs) — **this
pass adds no new independent confirmation of the literal `?s=` param name beyond what Slice 6's own
research already flagged as "consistent across sources but not personally confirmed byte-for-byte."**
Airbnb's own help article text (directly fetched, §1a) does NOT state the URL format explicitly in
its visible prose — it only says "we'll give you a URL" — so the literal `{listingId}.ics?s={token}`
shape remains SECONDARY-SOURCE-ONLY, not primary-source-confirmed, even after this pass's direct
fetch of the primary page. **Live-verify this exact string against Nnamdi's real account before the
Coder hardcodes any URL-parsing regex** — this is unchanged guidance from the original Slice 6
research, now re-confirmed as still the state of the evidence.

### 1d. A genuinely new, real-file corroboration: a synthetic-but-structurally-faithful sample `.ics`

I found and directly fetched a small, single-author GitHub repo,
`github.com/AyoubAchour/airbnb-ical-sample` (confirmed via GitHub API: 0 stars, 0 forks, created
2025-04-02, no further activity since — **weak provenance, flagged accordingly**), whose README
explicitly states its sample "accurately represents the current format used by Airbnb's calendar
export functionality" but **also explicitly discloses "All guest data is fictional"** and is offered
"for testing purposes only... not affiliated with or endorsed by Airbnb." Its `villa_hammamet.ics`
file (fetched in full) begins:
```
BEGIN:VCALENDAR
PRODID;X-RICAL-TZSOURCE=TZINFO:-//Airbnb Inc//Hosting Calendar 1.2.5//EN
CALSCALE:GREGORIAN
VERSION:2.0
BEGIN:VEVENT
DTEND;VALUE=DATE:20250406
DTSTART;VALUE=DATE:20250403
UID:3fdk78a9-2x33-495a-b912-4f7cde3a1b1e@airbnb.com
DESCRIPTION:CHECKIN: 03/04/2025\nCHECKOUT: 06/04/2025\nNIGHTS: 3\nPHONE: +1 555-123-4567\nEMAIL: guest1@example.com\nPROPERTY: Villa Hammamet\nGUESTS: 2
SUMMARY:Maria Rodriguez (HMRDN4521)
LOCATION:Villa Hammamet
END:VEVENT
```
The `PRODID` line (`-//Airbnb Inc//Hosting Calendar 1.2.5//EN`) is a plausible, correctly-shaped iCal
PRODID convention and is a genuinely useful structural detail (real iCal files do carry a vendor
PRODID this way) — **but the SUMMARY (`Maria Rodriguez (HMRDN4521)` — a full guest name plus what
looks like a confirmation code) and DESCRIPTION (full guest email + full phone number) fields in this
sample directly CONTRADICT every other source found in this and the prior Slice 6 research pass**,
all of which agree Airbnb's real feed has anonymized guest names out of the SUMMARY field since a
documented 2019 policy change (see Question 2). **Conclusion: treat this repo's sample file as
useful ONLY for the generic iCal envelope/PRODID/UID-suffix shape, and explicitly UNRELIABLE for
field-content claims (guest name/email/phone in SUMMARY/DESCRIPTION)** — it appears to be a
plausible-looking synthetic fixture, not a genuine byte-for-byte capture of a real, current Airbnb
feed, and its own self-description ("all guest data is fictional") is honest about this. Do not let
this repo's DESCRIPTION/SUMMARY shape inform the actual parsing logic; it is directly superseded by
the higher-confidence, multi-source-corroborated finding in Question 2 below.

---

## Question 2 — Guest-name/reservation-date correlation: does the iCal feed carry ANY correlatable identifier, and is there a non-iCal page that could bridge it?

**Answer: the iCal feed's DESCRIPTION field, per Airbnb's own documented Dec-2019 privacy change
(corroborated across FOUR independent secondary sources, no single one being a live-feed capture),
contains a "Reservation URL" pointing to the reservation's own details page plus the last 4 digits of
the guest's phone — this is very likely the correlation bridge, though the EXACT literal URL string
is only corroborated by ONE of those four sources. This is a materially stronger finding than "no
correlation is possible" and updates the prior Slice 6 research's more pessimistic framing.**

### 2a. What Airbnb changed and when (corrects a date discrepancy in the prior Slice 6 dossier)

The original Slice 6 research (`padsplit-cockpit-slice6-airbnb-research-2026-07-04.md`, Question 4)
cited Operto Teams as saying Airbnb's guest-info anonymization began "starting December 1st" without
pinning the year, and separately flagged an unrelated, weaker claim about "last four digits of phone
in SOME context." **This pass found the year and reconciles both claims into one coherent story**:
the change took effect **December 1, 2019** (confirmed independently by three sources: Operto Teams'
own blog post, Uplisting.io's blog post, and a real host's post — "BlueMtnCabins" — on the OwnerRez
community forum, `ownerrez.com/forums/general-help/airbnb-ical-change`, all three giving the identical
date). This is a 6-year-old, long-settled platform change, not a recent/uncertain one — meaningfully
raises confidence that this is still the current behavior in 2026.

### 2b. The DESCRIPTION field's actual post-2019 content (the correlation bridge)

Quoted directly from the Uplisting.io blog post (`uplisting.io/blog/how-the-airbnb-icalendar-ical-
changes-will-affect-you-and-how-to-avoid-disruption`, fetched directly):

> "Reservation URL" section with the link to the reservation details page and a "Phone Number (Last 4
> Digits)" section with the last 4 digits of the guest's phone number

The Operto Teams blog post (`teams-blog.operto.com/airbnb-changes-ical-calendar-export-feed-data-
starting-december-1/`, fetched directly) states the same two fields in near-identical language:

> Description: Will include a "Reservation URL" section with the link to the reservation details page
> and a "Phone Number (Last 4 Digits)" section with the last 4 digits of the guest's phone number

Both sources agree the SUMMARY field itself becomes the generic literal string **"Reserved"** (not a
guest name), and that "the guest name and reservation code will be removed from the event titles."
A third source, the OwnerRez community forum thread (a real host's own report, not a vendor's
marketing copy), independently repeats the identical "Reservation URL" + "last 4 digits" framing —
three sources, one of which is a first-hand host account, is meaningfully stronger corroboration than
Slice 6's original pass had for this specific mechanism (which only found the "no guest name" half of
this story, not the "but there IS a reservation URL" half).

**The one literal example URL string found** (Uplisting.io's blog, the only source giving an actual
example rather than describing the field abstractly):

> Title 'Reserved' and the reservation URL: `https://www.airbnb.com/hosting/reservations/details/xxxxxx`
> with Phone Number (Last 4 digits 2959)

**Honesty flag on this specific literal URL string**: I could not independently confirm
`/hosting/reservations/details/{id}` from a second source, from Airbnb's own Help Center prose
(searched specifically, found no exact match), or from a live feed. Treat the CONCEPT ("the
DESCRIPTION field contains a link to a reservation-details page, plus a partial phone number") as
corroborated by 3 independent sources including a real host report, but treat the EXACT URL PATH
STRING as single-source and unverified — Oga must confirm the literal path against Nnamdi's real
feed before the Coder writes a URL-parsing regex for it.

### 2c. Why this matters for the correlation design, concretely

If the DESCRIPTION field's reservation-details URL is real and stable, it gives the iCal-sync path a
genuine, structured correlation key that is NOT the iCal `UID` itself: **a reservation ID embedded in
a URL, extractable via regex from the DESCRIPTION text, that plausibly also appears somewhere in the
host's own hosting UI** (the "Manage reservation" panel `airbnb.com/help/article/4174` describes,
where a host finds the SAME booking's confirmation code — see 2d). This reframes the correlation
problem from "two unrelated identifier spaces with no bridge" (the original Slice 6 research's
framing) to "two identifier spaces that may share a common reservation-ID substring, IF the iCal
DESCRIPTION's URL and the confirmation-code UI expose the same underlying ID" — a materially better
starting hypothesis, though NOT yet proven to be the same ID (see 2e's honest caveat).

**IMPORTANT — this does NOT eliminate the correlation problem, it only weakens it**: even with a
reservation-details URL in hand, using it to auto-correlate against Slice 6a's scraped message
threads requires either (a) fetching that URL live (a new scrape target, out of scope unless Slice 6b
explicitly adds it), or (b) matching it against an ID visible in the ALREADY-CONFIRMED-REAL reservation
panel inside a message thread (`reservation-dynamic-marquee-title-header-v3` /
`hrd-sbui-header-section`, per Slice 6a's dossier §10g) — but Slice 6a's live-DOM dossier, read in
full for this dispatch, **does not record having found or looked for a reservation-ID string inside
either of those two elements or their surrounding DOM** — that element's confirmed content is a
*listing/property name* ("Home in Alhambra," "Serene Home in Central Atlanta"), not a booking ID. This
is a genuine, unresolved gap this dossier is flagging, not solving: Slice 6a's scraper output
(`AirbnbMessageThread`) currently has no reservation-ID field, and this pass did not find independent
evidence that one is trivially visible on the same page Slice 6a already scrapes. **Recommend a
targeted addendum to Slice 6a's dossier's live-DOM checklist** (for whoever does Oga's live-account
follow-up): when a thread's reservation panel is open, check whether a confirmation code or
reservation ID is present anywhere in the panel's DOM (even if not previously extracted) — this is a
cheap, high-value thing to look for opportunistically during the SAME live-verification pass Oga will
already be doing for the iCal export URL itself.

### 2d. The "Manage reservation" confirmation-code page — a real, host-documented lookup surface

Airbnb's own Help Center article on this (`https://www.airbnb.com/help/article/4174`, "Find a
confirmation code as a host," fetched directly) gives an EXPLICIT, distinct navigation path for a
host to find a reservation's confirmation code, separate from both the messages UI and the calendar
export:

> **For current/upcoming reservations**: Click "Today" → find current reservations or click
> "Upcoming" → click to select a reservation → click the three dots at the top of the page → under
> "Manage reservation," locate the confirmation code → click to copy it.
>
> **For completed reservations**: Click "Today" → "Menu" → "Earnings" → click "Paid" and filter by
> date/listing/earnings type → click to open a reservation → under "Confirmation," find the
> confirmation code.

This is a genuinely SEPARATE page/flow from both `/hosting/messages/{threadId}` (Slice 6a's confirmed
real path) and `/hosting/calendar` (this dossier's §1). **This is the clearest candidate for a
non-iCal, non-message-thread third surface that could resolve correlation directly**, since it is
explicitly host-documented to show BOTH the confirmation code AND (implicitly, since it's "the
reservation") the guest/dates — but its exact DOM shape is, like everything else in this dossier,
UNCONFIRMED against the live account; only its EXISTENCE and Airbnb's own documented navigation path
to it are confirmed. Recommend Oga's live-verification pass also open one live reservation via this
exact "Today → select reservation → ⋯ → Manage reservation" path and note what the URL and confirmation
code actually look like, alongside the iCal-export and (per 2c) message-thread-panel checks — three
related, cheap checks in one live session rather than three separate follow-ups.

### 2e. Honest bottom line on correlation — do not overclaim

Even with the DESCRIPTION-field reservation-URL finding, **no source found in this pass or the prior
Slice 6 pass demonstrates an actual WORKING correlation between an iCal event and a specific scraped
message thread** — this remains a design hypothesis to validate live, not a solved problem. What
changed with this pass: the prior framing ("iCal gives dates with no guest name; message threads give
a name but no reservation linkage — these are NECESSARILY separate, uncorrelatable-by-default data
sources," Slice 6 research Question 4) is now known to be **too pessimistic** — there IS a
correlatable field (the DESCRIPTION's reservation URL / embedded ID), it just hasn't been proven
end-to-end. The corrected framing for Slice 6b's spec: **date-range + property matching remains the
primary, always-available correlation heuristic** (an iCal event's `startDate`/`endDate` plus which
listing's feed it came from, matched against a `Reservation` row's own dates/property — this needs no
new scraping and works even if the DESCRIPTION-URL idea doesn't pan out), **with the DESCRIPTION-field
reservation ID as a SECONDARY, higher-confidence correlation signal IF Oga's live check confirms it
exists and is extractable** — design the schema (Question 3) to support BOTH, not to depend on
either being guaranteed.

### 2f. Sender/Contact bootstrapping order — grounded in Slice 6a's already-shipped mechanism

Slice 6a's shipped `ContactInbox`-based Contact resolution (verified by direct read of the merged
spec, §B.3) already creates a `Contact` eagerly from a scraped guest name the FIRST time a message
thread is synced, keyed by `ContactInbox.sourceId = thread.threadId` (the Airbnb message-thread ID,
NOT a reservation ID). **This is a real, load-bearing asymmetry Slice 6b's design must respect**: a
`Reservation` synced from iCal alone (no message thread ever opened for it, plausible for a
same-day-booked stay the host never messaged about) will have NO existing `Contact` to attach to —
confirming the prior Slice 6 research's recommendation that `Reservation.contactId` must be nullable,
now re-grounded against Slice 6a's actual shipped mechanism rather than a hypothetical one.

---

## Question 3 — A concrete `Reservation` Prisma model, grounded in the REAL current schema and RentTools.io's real, fresh-re-fetched models

**Answer: propose a new, standalone `Reservation` model alongside a new `CalendarLink` model (for the
per-property iCal export URL + sync bookkeeping), following RentTools.io's real, freshly re-verified
two-model split (`CalendarEvent` for raw iCal-sourced facts, `Reservation` for the richer,
correlation-target concept) rather than RentTools's exact field set — because padsplit-cockpit has a
`Room` concept RentTools.io does not, and an existing `Contact`/`Conversation`/`ContactInbox` layer
RentTools.io also does not have.**

### 3a. Current schema baseline, re-confirmed fresh (not reused from memory)

Read directly, `web/prisma/schema.prisma`, 482 lines, 2026-07-04:
- **No `Reservation`/`CalendarEvent`/`CalendarLink` model exists anywhere** — confirmed absent by a
  full read, matching the prior Slice 6 research's finding; nothing has changed here since (Slice 6a's
  build touched none of these).
- `Property` (lines 111-128): `id`, `orgId`, `address`, `city`, `state`, `platform: Platform`,
  `platformId: String?`, plus `rooms: Room[]` and `syncLogs: SyncLog[]` relations. `@@unique([orgId,
  address])`.
- `Room` (lines 135-158): `id`, `propertyId`, `roomLabel`, `presenceState`, `alertState`,
  `alertSince`, `weeklyRateCents`, `occupiedSince: DateTime?` (single nullable timestamp — the
  PadSplit-specific "one open-ended occupant" assumption already flagged as not transferable to
  Airbnb), plus relations including `contacts: Contact[]`. `@@unique([propertyId, roomLabel])`.
- `Contact` (lines 386-410): `id`, `orgId`, `kind: ContactKind` (`MEMBER | GUEST | PROSPECT | PAST`),
  `displayName`, `phone`, `email`, `currentRoomId: String? ` (nullable, PadSplit-specific pointer),
  relations to `contactInboxes`, `conversations`, `messages`. **No relation to any
  reservation/booking concept exists today.**
- `ContactInbox` (lines 412-424): `id`, `orgId`, `contactId`, `channel: Platform`, `sourceId: String`
  (Slice 6a wires this up for the first time, keyed by Airbnb `threadId`). `@@unique([orgId, channel,
  sourceId])`.
- `Conversation` (lines 426-447) / `Message` (lines 449-481): channel-agnostic already, `channel:
  Platform` on both, `Message.sourceId: String?` (currently always `null` for Airbnb per Slice 6a's
  spec, "no stable per-message external id scraped").
- `Platform` enum (lines 130-133): `PADSPLIT`, `AIRBNB` — unchanged, still just these two.
- `SyncLog` (lines 332-342): `id`, `propertyId`, `page: String`, `syncedAt`, `itemCount`, `errors:
  Json?` — a generic per-sync-call log, reusable as-is for calendar syncs (`page: 'airbnb_calendar'`
  already exists as a stub value in `route.ts` per the Slice 6 research).

### 3b. RentTools.io models, re-fetched fresh for this dispatch (confirms and extends the prior pass)

Re-fetched `raw.githubusercontent.com/Gribadan/RentTools.io/master/prisma/schema.prisma` directly
(2026-07-04) — repo confirmed STILL actively maintained (`pushed_at: 2026-07-03T06:31:06Z`, 10 stars,
MIT), and the schema has grown since the prior Slice 6 pass's snapshot (new fields on `Reservation`
for messenger-group deep-linking, not relevant here, but confirms this is a live, evolving codebase,
not a frozen artifact). The three load-bearing models, quoted directly from the fresh fetch:

```prisma
model CalendarLink {
  id            Int       @id @default(autoincrement())
  propertyId    Int
  property      Property  @relation(fields: [propertyId], references: [id], onDelete: Cascade)
  platform      String    // "airbnb" or "booking"
  icalExportUrl String    // iCal export URL from the platform
  bufferBefore  Int       @default(1) // days before booking to block
  bufferAfter   Int       @default(1) // days after booking to block
  lastFetchedAt DateTime?
  lastError     String?
  failureCount  Int       @default(0)
  createdAt     DateTime  @default(now())
}

model CalendarEvent {
  id         Int      @id @default(autoincrement())
  propertyId Int
  property   Property @relation(fields: [propertyId], references: [id], onDelete: Cascade)
  platform   String   // source platform
  uid        String   // iCal event UID
  summary    String   @default("")
  startDate  String   // YYYY-MM-DD
  endDate    String   // YYYY-MM-DD
  createdAt  DateTime @default(now())

  @@unique([propertyId, platform, uid])
}

model Reservation {
  id              Int      @id @default(autoincrement())
  name            String
  checkIn         DateTime
  checkOut        DateTime
  platform        String   @default("airbnb")
  linkedEventUid  String?  // UID of a synced CalendarEvent this reservation extends (for direct-pay extensions)
  phone           String?
  propertyId      Int
  property        Property @relation(fields: [propertyId], references: [id], onDelete: Cascade)
  guests          Guest[]
  createdAt       DateTime @default(now())
  updatedAt       DateTime @updatedAt
}
```

**The load-bearing structural fact this fresh re-fetch confirms**: RentTools.io treats
`CalendarEvent` (raw iCal fact: dates + UID, `@@unique([propertyId, platform, uid])` for idempotent
re-sync) and `Reservation` (the richer, name-bearing, guest-bearing concept) as **two separate
tables joined only by an OPTIONAL, soft `linkedEventUid` string field** — NOT a single merged model,
and NOT a hard foreign key (`linkedEventUid` is a bare `String?`, not a `@relation`). This is exactly
the "iCal sync and richer booking data are two different sources of truth, reconciled best-effort"
shape both the original Slice 6 research and this dossier's Question 2 independently concluded
padsplit-cockpit needs — RentTools.io's own production schema had already arrived at the same
architectural answer, for a different but structurally analogous reason (RentTools's `Reservation`
appears to be populated by a guest-passport-collection flow, not directly by the iCal sync itself;
`syncAllCalendars()`, confirmed in the prior pass, only ever writes to `CalendarEvent`, never to
`Reservation`).

### 3c. Concrete proposed `Reservation` model for padsplit-cockpit (a starting point for the Coder/spec-writer, not a final spec)

Following the RLS-scoped, multi-tenant, CUID-keyed conventions already used by every other model in
this schema (unlike RentTools.io's un-scoped `Int @id @default(autoincrement())` single-tenant
convention, which must NOT be copied verbatim):

```prisma
model Reservation {
  id            String            @id @default(cuid())
  orgId         String
  org           Org               @relation(fields: [orgId], references: [id])
  propertyId    String
  property      Property          @relation(fields: [propertyId], references: [id])
  roomId        String?
  room          Room?             @relation(fields: [roomId], references: [id])
  contactId     String?
  contact       Contact?          @relation(fields: [contactId], references: [id])
  channel       Platform
  checkIn       DateTime
  checkOut      DateTime
  externalUid   String?           // iCal VEVENT UID, e.g. "{uid}@airbnb.com" — idempotency key for iCal-sourced rows
  confirmationCode String?        // Airbnb's own "confirmation code" concept (help/article/4174) — a SECOND,
                                   // independent external identifier from the iCal UID; populate opportunistically
                                   // from EITHER source once/if Oga's live check (§2c/§2d) confirms where it's visible
  source        ReservationSource // where THIS row's data originated — see 3d
  status        ReservationStatus @default(CONFIRMED)
  createdAt     DateTime          @default(now())
  updatedAt     DateTime          @updatedAt

  @@unique([propertyId, channel, externalUid])
  @@index([orgId])
  @@index([contactId])
  @@map("reservations")
}

enum ReservationSource {
  ICAL_SYNC
  MESSAGE_THREAD_SCRAPE
}

enum ReservationStatus {
  CONFIRMED
  CANCELLED
}

model CalendarLink {
  id             String    @id @default(cuid())
  orgId          String
  org            Org       @relation(fields: [orgId], references: [id])
  propertyId     String
  property       Property  @relation(fields: [propertyId], references: [id])
  channel        Platform
  icalExportUrl  String
  lastFetchedAt  DateTime?
  lastError      String?
  failureCount   Int       @default(0)
  createdAt      DateTime  @default(now())
  updatedAt      DateTime  @updatedAt

  @@unique([orgId, propertyId, channel])
  @@map("calendar_links")
}
```

**Design rationale, tied directly to sources above, not asserted from vibes:**
- **`roomId: String?` (nullable)** — required by the project's own already-decided constraint
  (`project_padsplit_cockpit_rental_types.md`, cited directly in this slice's spec Context): a
  Property may be whole-home (no `Room` rows, the CURRENT Airbnb pattern per `syncListings()`, already
  confirmed in the Slice 6 research) or per-room. A hard-required `roomId` would break the
  already-established whole-home Airbnb pattern Slice 6a's own Contact-resolution design deliberately
  avoided (scope decision #2, confirmed working).
- **`contactId: String?` (nullable)** — required per §2f above: an iCal-sourced `Reservation` may have
  no corresponding scraped message thread (and therefore no `Contact`) at sync time. Mirrors the
  existing nullable `Contact.currentRoomId` pattern already in this schema for the same "may not be
  resolved yet" reason.
- **`externalUid: String?` with `@@unique([propertyId, channel, externalUid])`** — directly modeled on
  RentTools.io's own confirmed, real `CalendarEvent.@@unique([propertyId, platform, uid])` idempotency
  pattern (Question 3b) — this is the field a re-sync of the SAME iCal feed dedupes against, exactly
  analogous to how Slice 4/6a's `Message.@@unique([conversationId, senderLabel, content, sentAt])`
  already dedupes synced messages in this same codebase. Nullable because a
  `MESSAGE_THREAD_SCRAPE`-sourced row (see 3d) has no iCal UID at all.
- **`confirmationCode: String?`** — a NEW field neither reference repo has, added specifically because
  of this dispatch's Question 2 finding: Airbnb has a documented, host-visible "confirmation code"
  concept (`help/article/4174`) that is a plausible SECOND correlation key independent of the iCal
  UID. Marked nullable and explicitly "populate opportunistically" because, per §2c/§2d's honest
  caveat, this dossier does NOT prove where/whether it's scrapeable from either the calendar or
  message-thread surfaces already built — it's a placeholder the live-verification pass can decide
  whether to ever populate, not a required field the Coder must find a way to fill on day one.
  **If Oga's live check does NOT find a reliable source for this field, it is safe to ship the schema
  with this column permanently null for v1** — nothing else in this design depends on it being
  populated (correlation still works via date-range + property matching, §2e).
- **`source: ReservationSource`** — directly requested by the dispatch brief ("a sync-provenance field
  ... came from iCal vs. scraped from a message thread's reservation panel"). Modeled as its own enum
  (not reusing `EventSource`, whose three existing values — `EMAIL | EXTENSION_SYNC | HOST_ACTION` —
  describe a different axis, "how did this event reach our system" for `OccupancyEvent`, not "which
  Airbnb surface did THIS specific row's booking data come from"). Two values only, matching what this
  dossier's Question 2 actually confirms exist as sources: the iCal feed, and (per Slice 6a's already-
  shipped and separately-confirmed reservation-panel DOM elements) a message thread's own reservation
  panel. **Not adding a third "MANUAL" value speculatively** — nothing in either dossier's research
  establishes a need for host-manual reservation entry in this app, unlike RentTools.io's own
  `Reservation` model (which appears to serve a guest-passport-collection UI flow padsplit-cockpit has
  no analogue of).
- **`CalendarLink` as its own model, not folded into `Property`** — directly modeled on RentTools.io's
  real `CalendarLink` (Question 3b), because (a) `Property` already has many unrelated fields and
  `SyncLog` is already a generic child of `Property` rather than an inline field, matching this
  schema's own existing convention of small child tables for sync-bookkeeping data; (b) tracking
  `lastFetchedAt`/`lastError`/`failureCount` per property-per-channel needs its own row lifecycle
  independent of `Property`'s own update cadence. `@@unique([orgId, propertyId, channel])` assumes
  one Airbnb calendar link per property (true per Airbnb's own "one export URL per listing" framing,
  §1) — if a property is EVER synced from both Airbnb AND Booking.com (RentTools.io's own use case),
  this correctly allows two separate `CalendarLink` rows, one per `channel`.
- **Deliberately NOT changing `Room.occupiedSince` or `Contact.currentRoomId`** — re-confirms the
  original Slice 6 research's explicit recommendation (Question 5, "Do NOT repurpose ... these are
  PadSplit-specific concepts"), now cross-checked against the freshly re-read live schema and found
  still correct: nothing about this dispatch's new findings changes that call. Airbnb occupancy lives
  entirely in the new `Reservation` model.

### 3d. What actually WRITES a `Reservation` row — sketched, not specified (belongs to the spec-writer, flagged here so it isn't silently assumed)

Two distinct write paths, matching the two `ReservationSource` values:
1. **iCal sync** (`ICAL_SYNC`): a new backend function, structurally analogous to RentTools.io's
   `syncAllCalendars()` (confirmed real and portable per the original Slice 6 research — re-read the
   raw file this pass; unchanged since), fetches `CalendarLink.icalExportUrl`, parses it (RentTools's
   `parseICal()` — confirmed still real, 235-line file, unchanged content — is a directly portable
   reference, though note per Question 1d/2b that it currently parses only `UID`/`SUMMARY`/`DTSTART`/
   `DTEND` and would need EXTENDING to also parse `DESCRIPTION` if the Coder wants to attempt
   extracting the reservation-URL/confirmation-code signal from Question 2b — this is new work beyond
   what `parseICal()` already does, not something to assume "just works" by reusing the function
   unchanged). Upserts a `Reservation` row keyed by `@@unique([propertyId, channel, externalUid])`,
   `contactId: null` initially.
2. **Message-thread reservation panel** (`MESSAGE_THREAD_SCRAPE`): Slice 6a's `extractMessages()`
   ALREADY confirms two real, live-verified DOM elements exist that carry a listing name +
   (implicitly, from the guest-labeling mechanism Slice 6a separately built) a guest name, on the
   SAME page as the message content — `reservation-dynamic-marquee-title-header-v3` and
   `hrd-sbui-header-section`. **Neither element's date-range content was extracted or recorded by
   Slice 6a's dossier** (Slice 6a only needed `propertyName`, not check-in/check-out dates, since its
   own scope was messages, not reservations) — this is a concrete, actionable follow-up for whoever
   builds Slice 6b's content-script side: re-inspect these SAME two elements (already known to exist
   and be reachable, no new page/permission needed) specifically for date-range text, since the
   thread-list row text Slice 6a DID capture (`"Reservation from {startDate} to {endDate} in
   {city}"`, confirmed in Slice 6a dossier §3) proves date ranges ARE present somewhere on these
   pages, just not yet mapped to a specific extractable selector for the OPEN-thread view.

**This section is intentionally a sketch, not a finished design** — exactly like the original Slice 6
research's own final caveat, this should go through the same numbered "scope decisions" and
adversarial plan-check treatment Slices 4/6a received, not be accepted as-is.

### 3e. Live verification addendum (Oga, 2026-07-04) — the confirmation-code question from §2c/§2d/item-4 is now answered, directly

Navigated Nnamdi's real Airbnb account to the exact reservation-panel elements Slice 6a's
`extractMessages()` already opens, specifically to check the open item this dossier
flagged (§2c, §2d, "Not found" item 4: is a reservation ID/confirmation code visible in
these already-confirmed elements?). **Answer: yes, directly, on the CONFIRMED-reservation
branch only.**

On a thread with an active/confirmed reservation (the same "Home in Alhambra" thread
Slice 6a's own dossier used, where `reservation-dynamic-marquee-title-header-v3` is
present), the SAME reservation side panel also contains, confirmed via real `data-testid`
attributes:
- `[data-testid="reservation-title-subtitle"]` → literal text `"Confirmation
  codeHMQXF9Y5CK"` (strip the `"Confirmation code"` label prefix to get the real code,
  same pattern as stripping a sender label from message content in Slice 6a's own
  `extractMessages()`).
- `[data-testid="reservations-split-title-subtitle-kicker-row"]` → literal text
  `"Check-inThu, May 144:00 PMCheckoutSun, May 1710:00 AM"` — both the check-in and
  checkout DATE and TIME, in one element, needing a similar label-stripping parse.

**Critically, on a NON-confirmed thread** (re-checked on Cynthia's declined-booking
thread, which uses the `hrd-sbui-header-section` fallback panel, not the marquee) —
**neither of these two testids exist at all.** That panel only has
`hrd-sbui-header-guest-and-price` (guest count + total price) and
`hrd-sbui-about-guest-section` (the guest's Airbnb profile blurb) — no confirmation
code, no structured check-in/checkout element. This cleanly resolves the "sketch" in
§3d point 2: **a `MESSAGE_THREAD_SCRAPE`-sourced `Reservation` row should only be
created when the CONFIRMED-reservation panel (marquee) is present** — which is
semantically correct anyway (an inquiry or declined booking never became an actual
reservation) and conveniently is the EXACT same branch condition Slice 6a's
`extractMessages()` already computes for `propertyName` resolution (its `marqueeEl`
truthy check) — no new branching logic needed, just additional field extraction inside
the branch that already exists.

This upgrades `confirmationCode` (§3c) from "populate opportunistically, safe to ship
permanently null" to a genuinely populatable field for the `MESSAGE_THREAD_SCRAPE`
source, with a real, confirmed selector — and gives the SAME source path real
`checkIn`/`checkOut` values too, which §3d's original sketch did not have a confirmed
mechanism for at all. Recommend the spec-writer treat this as load-bearing: the
`MESSAGE_THREAD_SCRAPE` write path is now fully specifiable with real selectors, not
just a sketch requiring further live verification later.

---

## Honesty-bar summary (confirmed vs. corroborated vs. unverified)

| Claim | Status |
|---|---|
| Airbnb's own Help Center article 99 exists, live, fetched directly (not summarized) | CONFIRMED — raw HTML downloaded via curl, JSON-LD + literal `<ol><li>` step text extracted and quoted verbatim |
| Desktop nav path: Calendar (`/hosting/calendar`) → Availability → Connect calendars → Connect to another website | CONFIRMED — literal text from Airbnb's own page HTML, both a `HowTo` JSON-LD block and prose `<ol>` agree |
| Mobile-browser nav path is identical except Tap vs. Click | CONFIRMED — literal text from the same page's mobile section |
| Secondary-source phrasings ("Sync calendars"/"Export calendar", "Availability settings") describe the SAME control under different/older labels | PLAUSIBLE INFERENCE, not confirmed — flagged as a real terminology discrepancy across sources, not resolved; live UI may say either |
| Exact iCal URL format `airbnb.com/calendar/ical/{listingId}.ics?s={token}` | SECONDARY-SOURCE ONLY — consistent across multiple vendor blogs, NOT found in Airbnb's own visible help-article prose, NOT independently re-derived from a live feed this pass either |
| `github.com/AyoubAchour/airbnb-ical-sample`'s PRODID/UID envelope shape | PLAUSIBLE STRUCTURAL REFERENCE — repo confirmed real (fetched full file), but weak provenance (0 stars/forks, single day of activity) |
| Same repo's SUMMARY/DESCRIPTION guest-name/email/phone content | CONTRADICTED by 3+ independent, more-corroborated sources — flagged UNRELIABLE for field-content claims, self-disclosed as "fictional" by its own README |
| Airbnb's iCal SUMMARY became generic "Reserved," guest name/reservation code removed from event titles, effective Dec 1 2019 | CONFIRMED (3 independent sources agree on date + mechanism: Operto Teams blog, Uplisting.io blog, a real host's OwnerRez forum post) |
| DESCRIPTION field post-2019 contains a "Reservation URL" + last-4-digits phone number | CORROBORATED (3 independent sources, one first-hand host report) — concept confirmed, not a live-feed capture |
| Exact literal URL string `airbnb.com/hosting/reservations/details/{id}` | SINGLE-SOURCE ONLY (Uplisting.io's one example) — not found in Airbnb's own docs or a second independent source; treat as unverified until Oga live-checks |
| Airbnb's own "Find a confirmation code as a host" navigation path (Today → Upcoming → ⋯ → Manage reservation) | CONFIRMED — direct fetch of `airbnb.com/help/article/4174`, quoted |
| A reservation-ID/confirmation-code is visible inside Slice 6a's already-confirmed reservation-panel elements | CONFIRMED (Oga's live pass, §3e) — real testids `reservation-title-subtitle` (confirmation code) and `reservations-split-title-subtitle-kicker-row` (check-in/checkout) exist on the CONFIRMED-reservation (marquee) branch only; absent entirely on the non-confirmed (`hrd-sbui-header-section`) branch |
| Airbnb official partner API access is closed to individual hosts (partner-only, NDA required) | CONFIRMED (via WebSearch synthesis of `airbnb.com/help/article/3418` "API Terms of Service" and multiple industry explainers agreeing on this point) — not independently opened as a single primary quote, flagged as WebSearch-synthesis-level confidence, weaker than a directly-fetched-and-quoted claim |
| `web/prisma/schema.prisma` has no `Reservation`/`CalendarEvent`/`CalendarLink` model today | CONFIRMED — full 482-line file re-read directly this pass |
| RentTools.io's `CalendarLink`/`CalendarEvent`/`Reservation` models (exact current content) | CONFIRMED — fresh re-fetch of the live raw file, 2026-07-04, repo still actively pushed (`pushed_at: 2026-07-03`) |
| RentTools.io's `Reservation`↔`CalendarEvent` link is a soft, optional `linkedEventUid: String?`, not a hard foreign key | CONFIRMED — quoted directly from the fresh schema fetch |
| open-hotel-pms has no Membership/property_id concept (re-affirmed, not re-fetched this pass) | CONFIRMED in the PRIOR Slice 6 pass (full migration SQL fetched); not re-verified this pass since nothing in this dispatch's scope required it — carried forward as still-valid per that pass's own honesty table |

---

## Not found / explicitly unresolved (hand back to Oga / spec-writer, not silently assumed)

1. **The exact literal current button/section labels on the live Airbnb Calendar → Availability page**
   are per Airbnb's OWN PUBLISHED HELP-ARTICLE HTML (fetched directly, §1a), not confirmed against the
   real, live UI — Oga's live-account pass should treat "Connect calendars" / "Connect to another
   website" as the primary hypothesis to look for, with "Sync calendars" / "Export calendar" as a
   plausible fallback/older label if the exact text doesn't match.
2. **The exact iCal export URL format's `?s=` parameter name and overall shape** remains
   secondary-source-only, unchanged in confidence from the original Slice 6 research — still needs a
   live pull against Nnamdi's real account before any URL-parsing code is written.
3. **The exact literal `/hosting/reservations/details/{id}` URL path** is single-source (Uplisting.io)
   and should be treated as a hypothesis to confirm, not a fact, during Oga's live pass.
4. ~~Whether a reservation ID/confirmation code is visible anywhere in the DOM of Slice 6a's
   already-confirmed reservation-panel elements~~ — **RESOLVED, see §3e**: yes, confirmed via real
   testids, on the confirmed-reservation branch only.
5. **Whether Airbnb's iCal DESCRIPTION field's exact wording/format has changed again since the
   documented Dec-2019 baseline** (6 years is a long time for an unchanged UI string) — no source
   found suggesting a further change, but also no source confirming the Dec-2019 shape is still
   byte-identical in 2026; this is inferred stability from absence of contradicting evidence, not
   directly confirmed.
6. **Whether padsplit-cockpit should attempt to scrape `airbnb.com/hosting/reservations/details/{id}`
   or the "Manage reservation" confirmation-code panel as a THIRD live scrape target** (beyond the
   already-planned iCal fetch and the already-built messages scraper) is a scope question this dossier
   deliberately does not answer — it depends on whether Oga's live check finds the correlation ID
   accessible more cheaply from an element Slice 6a's scraper already visits (§2c) before deciding a
   new scrape surface is even needed.

---

## Sources (every URL actually opened this pass)

- `https://www.airbnb.com/help/article/99` — Airbnb Help Center, "Sync your home host calendar to
  other websites" — fetched via direct `curl` (raw HTML saved and grepped, not just WebFetch's
  summarizer) AND via WebFetch (used twice, cross-checked against the raw HTML for consistency).
  Literal `HowTo` JSON-LD block and `<ol><li>` desktop/mobile step lists extracted and quoted above.
- `https://www.airbnb.com/help/article/4174` — Airbnb Help Center, "Find a confirmation code as a
  host" — fetched directly, quoted in §2d.
- `https://www.airbnb.com/help/article/3037` — Airbnb Help Center, "Find all your reservations as a
  host" — fetched directly, quoted in §2c/2d cross-check.
- `https://hosttools.com/blog/airbnb-rentals/export-airbnb-calendar/` — secondary-source nav-path
  corroboration ("Sync calendars" / "Export calendar" phrasing), fetched directly.
- `https://help-teams.operto.com/article/610-airbnb-export-ical` — secondary-source nav-path
  corroboration ("Pricing and availability" → "Calendar sync" → "Export Calendar"), fetched directly.
- `https://bnb-pilot.com/en/blog/airbnb-ical-link.html` — secondary-source URL-format corroboration,
  fetched directly.
- `https://github.com/AyoubAchour/airbnb-ical-sample` (+ raw `README.md` and `villa_hammamet.ics`) —
  confirmed real via GitHub API (0 stars/forks, single-day history), full sample `.ics` file fetched
  and quoted; flagged unreliable for guest-field-content claims (see §1d).
- `https://teams-blog.operto.com/airbnb-changes-ical-calendar-export-feed-data-starting-december-1/` —
  fetched directly, quoted (Dec-1-2019 change, DESCRIPTION field contents).
- `https://www.uplisting.io/blog/how-the-airbnb-icalendar-ical-changes-will-affect-you-and-how-to-avoid-disruption`
  — fetched directly, quoted (the one literal example URL + "2959" phone-digits example).
- `https://www.ownerrez.com/forums/general-help/airbnb-ical-change` — fetched directly (a real host,
  "BlueMtnCabins," corroborating the same Dec-1-2019 change and DESCRIPTION-field contents).
- `https://community.withairbnb.com/t5/Help/Airbnb-ical-feed-incomplete/m-p/929090` and
  `https://community.withairbnb.com/t5/Help/No-Guest-Names-on-ICal-seriously/m-p/1129637` — attempted
  directly, both returned HTTP 403 (WebFetch blocked, likely a bot-wall on this specific forum
  platform) — NOT independently confirmed by this pass beyond their titles/existence as visible in
  WebSearch result listings; not cited as a quoted source, only as an existence signal that other
  hosts have publicly discussed this exact topic.
- `https://api.github.com/repos/Gribadan/RentTools.io` and
  `https://raw.githubusercontent.com/Gribadan/RentTools.io/master/prisma/schema.prisma` and
  `https://raw.githubusercontent.com/Gribadan/RentTools.io/master/src/lib/ical.ts` — all re-fetched
  fresh this pass (not reused from the prior Slice 6 dossier's cached findings), confirmed still live,
  MIT, actively pushed as of `2026-07-03`. Full `Reservation`/`CalendarLink`/`CalendarEvent` models
  quoted directly from the fresh fetch.
- `<HOME>/Claude/Projects/padsplit-cockpit/web/prisma/schema.prisma` — re-read in full,
  fresh, directly (482 lines) — confirms no `Reservation`-equivalent model exists today.
- `~/Claude/loop/research/padsplit-cockpit-slice6-airbnb-research-2026-07-04.md` and
  `~/Claude/loop/research/padsplit-cockpit-slice6a-airbnb-messages-dom-2026-07-04.md` — read in full,
  used as the grounding baseline this dossier extends rather than re-derives.
- WebSearch queries (lead generation only, each lead re-opened above before citing): Airbnb Help
  Center export-calendar navigation search, Airbnb iCal URL-format search, Airbnb reservation
  confirmation-code/UID-correlation search, Airbnb host API/developer-docs search, Airbnb iCal
  SUMMARY/DESCRIPTION real-format search (multiple phrasings), Operto/Uplisting/OwnerRez cross-checks,
  `/hosting/reservations/details` path search, "Availability settings" phrasing search.
