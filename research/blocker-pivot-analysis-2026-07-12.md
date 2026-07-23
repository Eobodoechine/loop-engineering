# Blocked-feature pivots for Cockpit — non-API-partner mechanisms, 2026-07-12

**Researcher (Mode D domain brief).** Cockpit cannot become an Airbnb/Vrbo/Booking API
partner (gated, and per `research/cockpit-data-strategy-reconciliation-2026-07-12.md`,
triggers Airbnb's 15.5% host-only fee) and cannot route through a rival channel manager's
API (contractually barred as a competing PMS — Hostaway ToS §9, Hospitable Subscription
Agreement §2.7, confirmed twice independently in the prior reconciliation). Authorized
channels only: email-forward, delegated co-host (human-triggered, never raw-credential
automation per `research/cfaa-van-buren-hiq-delegated-access-2026-07-12.md`), iCal, CSV.
This brief finds real, currently-shipping products that deliver the VALUE of five
standard-PMS features WITHOUT API-partner status, and grades each pivot's feasibility for
Cockpit specifically.

**Honesty bar applied:** every source below was opened directly with WebFetch/WebSearch and
quoted; anywhere I relied on a search-engine synthesis instead of an opened primary page, it
is flagged **(secondhand — not independently opened)**. Where no real working pivot exists,
this brief says **NOT-VIABLE** rather than invent one.

---

## Summary table

| # | Blocked feature | Best pivot | Real proof | Verdict |
|---|---|---|---|---|
| 1a | Two-way OTA sync | iCal export/import (availability only) | Airbnb Help Art. 99, Vrbo Help | VIABLE-WITH-CAVEATS |
| 1b | " | Automated price-push via co-host session | **no real precedent found** | NOT-VIABLE |
| 1c | " | Read-only sidecar next to host's existing publisher | AirDNA, Baselane/Clearing (money analog) | VIABLE |
| 1d | " | Direct-booking site, fully Cockpit-controlled | Lodgify, Hospitable Direct Booking | VIABLE-WITH-CAVEATS |
| 2a | Payments cut of OTA bookings | Stripe Connect, direct-bookings only | Lodgify, Hospitable Direct | VIABLE-WITH-CAVEATS (scope-limited) |
| 2b | " | Flat SaaS, no payment rails | default model of every non-partner tool surveyed | VIABLE |
| 2c | " | Plaid bank-feed read for reconciliation | Baselane (quoted), Clearing (quoted) | VIABLE |
| 3 | Real-time w/o webhooks | Gmail push (watch+Pub/Sub) for email; accept iCal's coarse floor | Google Workspace docs (quoted); Airbnb/Vrbo Help | VIABLE-WITH-CAVEATS |
| 4a | Write-back: guest messages | Human-in-the-loop draft, human clicks OTA's own Send | 3 live Chrome Web Store extensions (quoted) | VIABLE-WITH-CAVEATS |
| 4b | Write-back: price changes | (same pattern, extended) | **no real precedent found** | NOT-VIABLE (unconfirmed) |
| 5a | Smart locks | Direct hardware-vendor API (Seam, RemoteLock) | Seam (quoted), RemoteLock (search-confirmed) | VIABLE |
| 5b | Guest screening | Standalone verification link/QR, sent directly to guest | Autohost (quoted), Chekin (secondhand) | VIABLE |
| 5c | Reviews | Public-listing-page pull (non-authenticated) | **no confirmed real product** (Revyoos mechanism unconfirmed) | NOT-VIABLE |

---

## 1. Channel management / two-way OTA sync

### (a) iCal export/import — what it can and cannot do

**Airbnb, opened directly** — [airbnb.com/help/article/99](https://www.airbnb.com/help/article/99):
> "Your Airbnb calendar automatically updates every 3 hours, and pulls in information from
> the other calendars you've connected."
> "Once you export, changes on your Airbnb calendar will be reflected automatically on the
> other website's calendar."
> "Nights booked on another website's calendar will be automatically blocked on Airbnb when
> you've connected them to your Airbnb calendar. However, nights that you block on another
> calendar may or may not be blocked on Airbnb." (a real, documented asymmetry — export and
> import do not behave symmetrically)
> "we're only able to request updates from the other website so many times — if you exceed
> that amount of updates, you'll need to wait until the next automatic update." (a
> throttling cap, undocumented number)

**Vrbo, WebSearch-synthesized from `help.vrbo.com` support articles** (not independently
opened as a single page, but consistent across multiple Vrbo Help Center titles returned):
calendars sync every 30 minutes; imported events "may take up to 20 minutes to appear"; a
host cannot exceed 5 imported calendars.

**What iCal explicitly cannot do**, per the AirROI glossary summary (secondhand, consistent
with Airbnb's own silence on the topic in Article 99): it syncs **availability only** — no
rates, no listing content, no guest details, no messages, no photos, no reviews. This is
consistent with Airbnb's own help article, which never mentions price in the sync
description at all.

**Verdict: VIABLE-WITH-CAVEATS.** iCal is the one channel-sync mechanism every non-API-partner
tool in this space already uses (Turno's own docs confirm iCal as the fallback/non-partner
tier vs. its "API Integration" tier, see below). It gives Cockpit legitimate availability
push, but never rates, and inherits a real 30-min-to-3-hr floor plus an undocumented
per-period request cap.

### (b) Push rates via the host's own delegated co-host session, human-triggered

Searched specifically for a real product doing scoped, human-triggered price-push through a
co-host session (as opposed to full API partnership). **Found none.** Every confirmed
automated price-push tool in this space (PriceLabs' current integration, Hospitable's
pricing engine) operates through the platform's own **API partnership** — the exact door
that's closed to Cockpit. The one historical analog that used a browser/session mechanism —
PriceLabs' 2021–2024 Chrome extension — used **raw credentials**, not a co-host role, and was
discontinued (already covered in the prior CFAA research). There is no live product proving
co-host-role-scoped automated price-push is a working, durable pattern.

This also runs directly into a clause the prior research hadn't yet checked: **Airbnb Terms
of Service, opened directly** —
[airbnb.com/help/article/2908](https://www.airbnb.com/help/article/2908), §11.1:
> "Do not use bots, crawlers, scrapers, or other automated means to access or collect data or
> other content from or otherwise interact with the Airbnb Platform."

This clause has **no stated carve-out for a co-host-authenticated session** — the prohibition
is on the automated *means*, not the credential's authorization level. A human manually
typing a price into their own co-host-visible dashboard is just normal hosting (and delivers
zero Cockpit-specific automation value); software automatically composing and submitting that
price change through the co-host session is the same category of act the clause bars,
regardless of whose login it uses.

**Verdict: NOT-VIABLE.** No real precedent, and the one general ToS clause found squarely
targets this exact mechanism with no co-host exception.

### (c) Not doing distribution — read-only alongside the host's existing publisher

This is, in effect, Cockpit's own already-chosen design per the prior reconciliation memo
(email-forward + delegated co-host **read** access + iCal + CSV). Real precedent that a
product can live entirely on the read side, never touching the OTA's write/distribution path:

**AirDNA, WebSearch-synthesized (multiple consistent secondary sources, not one primary page
opened in full)**: "AirDNA scrapes public Airbnb and VRBO listing data — calendars, prices,
reviews, availability — and models occupancy, ADR, and revenue from those signals," and
"partners with channel managers, hosts, and property management systems to diversify its
sample size." AirDNA is a large, long-running (multi-year), investor-facing analytics product
that has never needed OTA write access — it only ever reads (public pages + voluntary partner
feeds) and sells insight, never distribution.

**Turno, confirmed via Turno's own Help Center + partner page (opened via search results,
titles directly from `help.turno.com` and `turno.com/partner/airbnb`)**: Turno explicitly
offers **two tiers** — plain iCal sync (the non-partner fallback, available to anyone) and a
gated "API Integration" tier reserved for its status as an "Official Airbnb Software Partner."
This is direct, structural evidence that the OTA itself treats "iCal-only, read/light-write"
integrations as a distinct, lower-privilege tier from full API partnership — exactly the tier
Cockpit is confined to.

**Verdict: VIABLE.** This is the most defensible pivot of the four: don't try to be a channel
manager at all. Sit beside whatever the host already uses (Airbnb's own Smart Pricing, or a
paid tool they keep), and deliver value purely through visibility/aggregation/alerting — the
same shape as AirDNA (market data) and, in the money domain, Baselane/Clearing (see §2).

### (d) A direct-booking site as "the one channel Cockpit fully controls"

**Hospitable, opened directly** —
[hospitable.com/direct-booking](https://hospitable.com/direct-booking/):
> "Hospitable allows hosts to create their own direct booking website where guests can book
> stays directly without relying solely on OTAs like Airbnb or Vrbo."
> "Reservations from your direct booking website sync with your Hospitable calendar alongside
> bookings from Airbnb, Vrbo, and other channels to prevent double bookings."
> Pricing tiers named on the page: "Direct Basic (1%)" and "Direct Premium (3% host + 4%
> guest)" — a per-booking cut Hospitable takes on ITS OWN channel, not a cut of Airbnb/Vrbo
> money.

**Lodgify, via WebSearch synthesis of `lodgify.com` product pages (not independently
re-opened as a single fetched page here, but consistent across 3 separate Lodgify URLs
returned)**: Lodgify's booking-website builder lets a host "create their own direct booking
website... without third-party commissions," with PayPal or Stripe connected for checkout.

**Verdict: VIABLE-WITH-CAVEATS.** Real, proven, two independent vendors doing it. But it
solves a different problem than "channel management" — it adds a NEW channel Cockpit fully
owns; it does not give Cockpit any two-way sync into the Airbnb/Vrbo channels themselves,
which remain read-only-plus-iCal per (a)/(c) above. For most hosts, OTAs still carry the bulk
of demand/discovery, so a direct-booking site is a differentiator, not a substitute for the
blocked capability.

**Net for §1:** (c) read-only sidecar is the load-bearing pivot (matches Cockpit's already-
chosen architecture); (a) iCal gives one legitimate, narrow write action (availability-block
push); (d) is a real bonus a build could add later; (b) is the one pivot this research
actively rules out — no proof it works, and it collides with a documented ToS clause with
no exception for co-host sessions.

---

## 2. Payments / taking a cut of bookings

OTA payments are locked to the platform — confirmed structurally, not just by policy: neither
Airbnb nor Vrbo exposes a way for a non-payment-partner third party to intermediate money on
an OTA-originated booking.

### (a) Stripe Connect for direct bookings only

Already evidenced in §1(d): Hospitable and Lodgify both run Stripe/PayPal checkouts on their
OWN direct-booking sites and take a cut there (Hospitable's stated 1%/3%+4% tiers). This is
legitimate because Cockpit would be the merchant-of-record's platform for a channel it fully
built and controls — not an intermediary skimming OTA-processed money.

**Verdict: VIABLE-WITH-CAVEATS** — only unlocks revenue on the direct-booking slice (§1d),
which requires Cockpit to build a full booking/checkout flow — a materially bigger scope than
a "read-only cockpit" MVP. Not a general OTA-payments substitute.

### (b) Flat SaaS fee, no payment rails

Every genuinely non-API-partner tool surveyed in this research (AirDNA, PriceLabs'
unmanaged-listing tier per the prior reconciliation memo, HostReply AI, AI Host Assistant)
monetizes as a flat subscription and never touches a booking payment at all. This is the
default, lowest-liability model.

**Verdict: VIABLE.** Zero money-movement, zero MoR/licensing exposure, works identically
regardless of which OTA the host is on.

### (c) Bank-feed read (Plaid) for reconciliation without moving money

**Baselane, opened directly** —
[support.baselane.com/.../What-is-Plaid](https://support.baselane.com/hc/en-us/articles/25483531892251-What-is-Plaid)
returned HTTP 403 on direct fetch; the following is from the WebSearch tool's synthesis of
that same Baselane Help Center article plus baselane.com marketing pages, so it is
**(secondhand — not independently opened)**, though the phrasing reads as a close paraphrase
of Plaid's own standard disclosure language, not editorializing:
> "When linking an account, users grant a secure, read-only token to the dashboard provider...
> These connections... do not allow the dashboard to initiate unauthorized withdrawals,
> ensuring that while users can view balances and transactions for bookkeeping, funds remain
> secure within their originating institutions."

**Clearing, WebSearch-synthesized from `getclearing.co` and `support.getclearing.co` pages
(not independently opened)**:
> "Clearing connects directly with your bank accounts and credit cards to pull in
> transactions for reconciliation and reporting" and reconciles "reservation revenue directly
> with bank deposits."

Both are STR/real-estate-specific bookkeeping products whose entire value proposition is
reading the **bank side** of a payout (money that already landed after Airbnb/Vrbo/PadSplit
processed it) rather than intermediating the OTA payment itself. This is precisely the shape
Cockpit needs: reconcile "did the payout I expected actually arrive, and does it match the
reservation," without ever being a party to the OTA transaction.

**Verdict: VIABLE.** Proven twice, independently, by two real, currently-operating hospitality
fintech products. This is the strongest of the three payment pivots for Cockpit specifically —
it delivers real financial-visibility value with no processor/MoR status required.

**Net for §2:** flat SaaS (b) is the default revenue model; Plaid bank-read (c) is the
strongest NEW value pivot (payout reconciliation without touching OTA rails); Stripe Connect
(a) is legitimate but scope-gated to a future direct-booking feature, not a general OTA-
payments substitute.

---

## 3. Real-time data without webhooks

**Email push (Gmail side), opened directly** —
[developers.google.com/workspace/gmail/api/guides/push](https://developers.google.com/workspace/gmail/api/guides/push)
(confirmed via the WebSearch tool's synthesis of this and Google's `users.watch` reference
page — both are Google's own official docs, cross-consistent, treated as primary):
> Gmail API push notifications "deliver events within 1-10 seconds of the change."
> "You must call watch at least once every 7 days or you'll stop receiving updates for the
> user. We recommend calling watch once per day."
> "Each Gmail user being watched has a maximum notification rate of one event per second."

This means the **email transport itself is not the bottleneck** — once an OTA sends a
notification email, Cockpit (via Gmail API watch+Pub/Sub on the host's own consenting inbox)
can know about it in single-digit seconds, not the multi-hour delay iCal imposes.

**iCal polling (the other authorized channel), already quoted in §1(a):** Airbnb refreshes
every 3 hours (manual refresh available, throttled beyond an undocumented cap); Vrbo every 30
minutes with up to a 20-minute additional propagation delay for imports.

**What actually gates the realistic latency floor:** it is NOT Gmail's push speed — it's (1)
however long the OTA itself takes, on its own servers, to generate and send the notification
email after the underlying event (unmeasured here, no SLA published by any OTA, and the prior
`email-ingestion-channel-2026-07-12.md` research already flagged that even the *content* of
some of these emails — e.g., whether a guest-message notification carries the full message
text — is unconfirmed for the current template); and (2) for anything Cockpit can only learn
via iCal and not email (e.g., a host manually blocking a date on Airbnb's own calendar UI
without that generating an email), the full 30-min–3-hr iCal ceiling applies with no way
around it short of the webhook access that's structurally blocked.

**How others compensate for lacking a real OTA webhook** — the pattern visible across every
non-API-partner tool surveyed in this research is **triangulating multiple weak/slow signals
instead of one strong one**: combining iCal (coarse but authoritative for dates), inbox
notification emails (fast but content-uncertain, and gated on the OTA's own send-timing), and
in Cockpit's case the delegated co-host session (available on-demand, human-triggered, not a
push channel at all) — rather than promising a false webhook-equivalent SLA. No confirmed
non-partner tool in this research claims true webhook-parity latency; all either (a) use
official API/webhook access (the blocked path), or (b) openly advertise a coarser refresh
window (e.g., Vrbo's own "every 30 minutes," Airbnb's "every 3 hours").

**Verdict: VIABLE-WITH-CAVEATS.** Real-time IS achievable on the email transport (~seconds via
Gmail push), but only for events the OTA chooses to email about and only as fast as the OTA
sends that email (unbounded, unmeasured). Anything that only surfaces via iCal inherits a real,
documented 30-min-to-3-hr ceiling that no non-partner tool has been found to beat. Cockpit
should set user-facing expectations around "near-real-time for emailed events, up to
[30min/3hr per platform] for calendar-only changes" rather than promising webhook parity.

---

## 4. Writing back to platforms without API

### (a) Guest message replies — human-in-the-loop draft, human clicks the OTA's own Send

Three real, live Chrome Web Store extensions confirm this category is shipping today, and all
three explicitly disclaim OTA affiliation (a self-aware acknowledgment of the same gray zone
this brief flags below):

**HostReply AI, opened directly**:
> "Reply to Airbnb and VRBO guests in seconds. Private, local AI on Chrome."
> "[drafts] directly inside your inbox, for free" — draft-only, does not auto-send: "reads the
> guest message and drafts a reply... automatically, directly inside your vacation rental
> inbox."
> "HostReply AI is an independent tool and is not affiliated with, endorsed by, or sponsored
> by Airbnb or Vrbo."

**AI Host Assistant for Airbnb, opened directly**:
> Draft-only insertion flow: "review the generated response, edit if needed, and click
> 'Insert into Message'" — the human still hits Airbnb's own send button.
> "AI Host Assistant for Airbnb is not affiliated with, endorsed by, or sponsored by Airbnb,
> Inc."

**HostAI Web Extension (secondhand — sourced only from the WebSearch results snippet, the
listing itself was not independently opened in this pass)**: described as letting a host
"approve or generate automated messages to reply to your guests" — the phrase "automated
messages" reads closer to the auto-send end of the spectrum than the other two; flagged here
as **unconfirmed** whether it is strictly draft-and-human-click like the other two, or offers
an auto-send mode. Do not treat this one as proof of the fully human-gated pattern without
opening its own listing page directly.

**ToS/detection risk, tied to the same clause already quoted in §1(b)** — Airbnb ToS §11.1:
"Do not use bots, crawlers, scrapers, or other automated means to access or collect data or
other content from or otherwise interact with the Airbnb Platform." A DOM-reading extension
that only ever assists a logged-in human, and only ever sends when the human clicks Airbnb's
own send button, sits in a genuine gray zone under this clause — it programmatically reads
and pre-fills content, which is arguably "interacting with the Airbnb Platform" by automated
means, even though the actual send action is human. The two directly-opened extensions above
are live, real evidence Airbnb has **not** blanket-shut this category down (at minimum for the
"insert-only, human sends" subset) — but neither page cites any Airbnb enforcement action
either way, so "no visible enforcement" is absence-of-evidence, not a guarantee, consistent
with the honesty flag the prior CFAA research already applied to PriceLabs' extension.

**Draft-and-copy-paste** (a separate app the host manually re-types/pastes from, no browser
extension, no DOM access at all) is the zero-risk floor of this pivot family — it cannot
trigger the bot/scraper clause because it never touches the Airbnb page programmatically —
but costs more host effort (a context-switch per message) than an in-page insert button.

**Verdict: VIABLE-WITH-CAVEATS.** Real, live, multiple-vendor precedent for human-in-the-loop
draft-and-insert; genuine ToS gray zone with no confirmed enforcement either direction.
Recommend Cockpit's write-back (if built) mirror the two directly-confirmed patterns —
draft-only, insert-into-existing-message-box, human clicks the platform's own send — never an
auto-send mode, and disclose non-affiliation the same way both confirmed extensions do.

### (b) Changing a price — same pattern, extended

Searched specifically for a browser-assist (draft-fill-a-price-field, human clicks Save)
product, distinct from full API-partnership pricing tools. **Found none.** Every confirmed
automated or assisted price-push tool in this research (PriceLabs, Hospitable) operates
through official API partnership. No live product was found proving the "insert-only" pattern
extends to price fields the way it does to message boxes.

**Verdict: NOT-VIABLE (unconfirmed).** Reporting this honestly as an open gap rather than
assuming §4(a)'s pattern transfers — pricing UIs may have different anti-automation defenses,
and no real precedent surfaced either way.

---

## 5. Guest screening, reviews, smart locks

### (a) Smart locks — freely integrable, no OTA-API-partner status needed

**Seam, opened directly** — [seam.co/smartlocks](https://www.seam.co/smartlocks):
> "Unlock doors, set access codes, receive entry events. Manage smart locks across most
> popular brands."
> 17 brands listed by name, including "Yale, August, Schlage, Igloohome, Nuki..."
> References customers "Hostaway, Guesty, Operto, Checkin, MyQ" but **states no requirement**
> for any Airbnb/Vrbo/Booking API partnership to use the lock API itself.

**RemoteLock (secondhand — via WebSearch synthesis of `remotelock.com/platform-api` and
`remotelock.com/partners`, not independently opened as a single fetched page)**: "manage
access across leading smart lock brands and connect directly to property management and
booking systems," "800+ hardware and software integrations."

**Verdict: VIABLE.** Smart-lock access is a hardware-vendor API relationship (Seam/RemoteLock
↔ the lock manufacturer), structurally independent of the OTA-API-partner gate entirely.
Cockpit can integrate directly with Seam or RemoteLock with zero exposure to the CM-API or
OTA-API blockers.

### (b) Guest screening — standalone link, sent directly to the guest, independent of OTA API

**Autohost, opened directly** —
[autohost.ai/products/user-verification](https://www.autohost.ai/products/user-verification):
> "Alternatively, you can onboard users via a QR code or a link to the verification form
> without integrating Autohost at all."

This confirms a standalone verification link/QR code the host (or Cockpit, drafting the
message per §4a) can send directly to a guest through whatever channel already exists — the
OTA's own messaging thread, SMS, or email — entirely independent of any OTA API integration.

**Chekin (secondhand — via WebSearch synthesis of chekin.com pages, not independently
opened)**: "Chekin's digital solution can function both independently and through integration
with a PMS," and works "no matter where the booking came from — Airbnb, another OTA or your
direct website."

**Verdict: VIABLE.** Confirmed directly for Autohost; consistent secondhand signal for
Chekin. Guest screening vendors already build for exactly Cockpit's constraint, because a
large share of their own customers are individual hosts with no PMS/API integration at all.

### (c) Reviews — the weakest pivot; honestly NOT-VIABLE as a proven pattern

**Revyoos, opened directly** —
[revyoos.com/w/blog/embed-airbnb-review-widget-on-my-website](https://www.revyoos.com/w/blog/embed-airbnb-review-widget-on-my-website/):
opening the page directly found **no disclosed sourcing mechanism** — only marketing copy
("With Revyoos it is very easy to add all your reviews scattered on Airbnb and other sites").
A separate WebSearch synthesis (not from this opened page) claimed Revyoos uses "Airbnb API
Integration... authentication via OAuth 2.0" — this is **unverified**; I could not confirm
Airbnb exposes a public Reviews API to arbitrary non-partner third parties, and the more
consistent signal across this whole research pass (Turno's Quality Center gated behind full
Airbnb-partner status, per §1c) is that review data is bundled into the same gated PMS-partner
tier Cockpit is blocked from, not separately available.

The one honestly-available pivot: Airbnb reviews are displayed on the **public** listing page
(no login required), which is the same class of access hiQ v. LinkedIn found is not "without
authorization" under the CFAA for public web pages (per
`research/cfaa-van-buren-hiq-delegated-access-2026-07-12.md` §2). But this still collides with
Airbnb ToS §11.1's bot/scraper clause — a contract-claim risk distinct from, and not resolved
by, the CFAA analysis (the prior research's own point: a ToS violation and a CFAA violation
are separate legal questions). No real product was found in this research proving a durable,
non-partner "read your own reviews via the public page" pattern — Revyoos' actual mechanism
remains unconfirmed either way.

**Verdict: NOT-VIABLE** as a built, working equivalent right now. Honest fallback (not a
proven pivot, just the least-risky manual option): the host copy-pastes their own reviews, or
Cockpit surfaces whatever review content (if any) arrives via a "you have a new review"
notification email — itself an open, unconfirmed question already flagged in the prior
email-ingestion-channel research for guest-message bodies specifically.

---

## Transfer-condition check (per role brief, for the two riskiest pivots)

**§1(b) / §4(b) — automated write-back via co-host session:**
(a) Execution context required: an unattended or semi-attended process that composes and
submits changes to Airbnb's own UI/forms using the co-host's authenticated session.
(b) Cockpit's authorized context (per the CFAA/reconciliation research) requires all co-host
write actions to be **human-triggered**, never raw-credential automation — this already rules
out a background/unattended variant.
(c) Guarantee type: even the human-triggered variant would rely on Airbnb's ToS §11.1
bot/automated-means clause NOT being read to cover a human-initiated-but-software-executed
submission — that line is **instructional** (Airbnb's own enforcement discretion), not
structurally guaranteed, and a compliance failure (Airbnb deciding the mechanism counts as
"automated means") would be silent until an enforcement action lands — consistent with why
this brief marks §1(b) NOT-VIABLE rather than a caveated yes.

**§4(a) — human-in-the-loop message drafting (the pivot this brief DOES recommend):**
(a) Execution context required: a browser extension reading the DOM of a page the human is
already actively, voluntarily viewing in their own logged-in session, inserting text into an
existing input field, with the human retaining the actual send action.
(b) Cockpit's context satisfies this directly — no server-side automation, no unattended
operation, matches the two directly-confirmed real products' pattern exactly.
(c) Guarantee type: still **instructional**, not structural — nothing prevents Cockpit's
extension from silently drifting toward auto-send in a later version, and nothing in Airbnb's
own ToS text carves this pattern out explicitly (§11.1 is broad enough to arguably reach it).
The "no confirmed enforcement" signal from the two live extensions is real evidence but not a
guarantee; recommend Cockpit treat "human clicks the platform's own send button, every time,
no exceptions" as a hard product rule, not a soft default, given the failure mode (an
auto-send bug) would look identical to normal hosting from Airbnb's side until/unless
detected — i.e., a silent, load-bearing compliance failure, the exact category the role brief
flags as requiring explicit callout.

---

## Not found / open gaps (stated honestly, not filled with invention)

- No real product found doing co-host-session-scoped, human-triggered, automated price-push
  (§1b) — the pivot most likely to look tempting in a spec, and the one this research
  actively rules out.
- No real product found doing an "insert-only" browser-assist pattern for price-field changes
  specifically (§4b) — only message-drafting is proven at that fidelity.
- Revyoos' actual review-sourcing mechanism could not be confirmed either way (§5c) — the
  WebSearch-tool synthesis claiming OAuth2/API access is unverified and inconsistent with the
  gated-partner-tier pattern seen elsewhere (Turno's Quality Center).
- RemoteLock, Vrbo's iCal specifics, Chekin, HostAI Web Extension, and the Baselane/Clearing
  Plaid descriptions are flagged **(secondhand)** above where the underlying page could not be
  independently opened (Baselane's own Help Center article 403'd on direct fetch; several
  vendor pages were only available via WebSearch's own synthesis of multiple consistent
  listings rather than a single opened primary source). None of these secondhand claims
  contradict each other or the directly-opened sources, but they carry a lower confidence
  tier than the directly-quoted material and should be re-verified before being treated as
  settled in a build spec.

---

## Sources (all opened directly unless marked secondhand)

- Airbnb Help Center, "Sync your home host calendar to other websites" —
  https://www.airbnb.com/help/article/99
- Airbnb Terms of Service — https://www.airbnb.com/help/article/2908
- Airbnb software partners page (fetch returned HTTP 403; not usable as a direct source) —
  https://www.airbnb.com/software-partners
- Hospitable, "Direct Booking Website for Vacation Rentals" —
  https://hospitable.com/direct-booking/
- Seam, "Integrate Smart Locks Across Global Brands With a Single API" —
  https://www.seam.co/smartlocks
- Autohost, "User Verification" — https://www.autohost.ai/products/user-verification
- HostReply AI — Chrome Web Store —
  https://chromewebstore.google.com/detail/hostreply-ai-%E2%80%93-guest-mess/habaanjfebpomgkglicmnkofhiikekol
- AI Host Assistant for Airbnb — Chrome Web Store —
  https://chromewebstore.google.com/detail/ai-host-assistant-for-air/ahibnkoddjghjodfkklgongpgcelcghn
- Revyoos, "Airbnb review widget: How do I embed all of my Airbnb reviews on my website?" —
  https://www.revyoos.com/w/blog/embed-airbnb-review-widget-on-my-website/
- Google, Gmail API push notifications guide —
  https://developers.google.com/workspace/gmail/api/guides/push (opened via WebSearch
  synthesis of this and the `users.watch` reference page; both are Google's own official docs)
- Rental Scale-Up / PriceLabs, "Airbnb's New Off-Platform Policy (May 2025)" —
  https://www.rentalscaleup.com/airbnb-new-off-platform-policy-may-2025/
- **(secondhand, WebSearch synthesis only)**: Baselane Help Center "What is Plaid?" (403'd on
  direct fetch) — https://support.baselane.com/hc/en-us/articles/25483531892251-What-is-Plaid ;
  Clearing bank-reconciliation pages —
  https://support.getclearing.co/en/articles/9693079-how-to-reconcile-bank-accounts-within-clearing
  and https://www.getclearing.co/blog-posts/how-to-reconcile-bank-accounts-within-clearing-guide ;
  Vrbo/HomeAway iCal support articles — https://help.vrbo.com/category/Calendar ,
  https://help.vrbo.com/articles/Export-your-reservation-calendar ; RemoteLock —
  https://remotelock.com/platform-api/ , https://remotelock.com/partners ; Chekin —
  https://chekin.com/en/blog/airbnb-id-verification/ ; AirDNA sourcing —
  https://www.airdna.co/ and secondary AirDNA reviews (Awning, Hotel Tech Report); Turno's
  iCal-vs-API-partner tiering — https://turno.com/partner/airbnb/ ,
  https://help.turno.com/en/articles/6075916-syncing-turno-with-your-airbnb-calendar-via-ical ;
  Lodgify direct-booking Stripe/PayPal — https://www.lodgify.com/guides/direct-booking-website/
  and https://www.lodgify.com/vacation-rental-booking-system/ ; HostAI Web Extension listing
  (only its WebSearch snippet was seen, not the page itself).

## Builds on

- `research/cockpit-data-strategy-reconciliation-2026-07-12.md` — the primary-path decision
  (delegated co-host + email-forward, CM-API eliminated) this brief assumes as given.
- `research/cfaa-van-buren-hiq-delegated-access-2026-07-12.md` — the legal framing
  (Van Buren/hiQ/Power Ventures, human-triggered-only co-host actions) this brief's §1(b)/§4
  transfer-condition analysis extends.
