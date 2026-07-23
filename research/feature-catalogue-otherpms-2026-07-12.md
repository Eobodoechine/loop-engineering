# Feature Catalogue: Hospitable, Lodgify, Uplisting, Hostfully, Smoobu — 2026-07-12

**Mode:** D (domain research for a build — Cockpit)
**Purpose:** breadth-and-completeness feature catalogue for five more PMS/channel-manager products, to be
UNIONED with a parallel catalogue of Hostaway/Guesty/OwnerRez so the loop team has the full set of features
the market treats as standard. This is a catalogue, not a recommendation — Cockpit's own feature-set
decisions are downstream of this + the companion pricing/positioning brief.
**Builds on:** `~/Claude/loop/research/competitive-landscape-business-model-2026-07-12.md` (pricing +
partial matrix for Hostaway/Guesty/OwnerRez/Lodgify/Hospitable — read first; this doc does not repeat that
pricing table except where a number changed or needs reconciling, flagged inline).

---

## Honesty-bar access notes — read before trusting any line below

**Vendor pages opened directly and confirmed (first-party, verified):**
- Hospitable: `hospitable.com/pricing` (JS-partial — see caveat below), `help.hospitable.com` pricing
  article (stable HTML, most reliable), `hospitable.com/features`, `hospitable.com/integrations`,
  `hospitable.com/features/direct-booking`.
- Hostfully: `hostfully.com/property-management-platform/`, `hostfully.com/pricing/`,
  `hostfully.com/digital-guidebooks/features/`, `hostfully.com/pmp-features/owner-portal/`.
- Uplisting: `uplisting.io/property-management-software` (404 first try, retried and worked as
  `uplisting.io/features`), `uplisting.io/pricing`, `uplisting.io/integrations`.
- Smoobu: `smoobu.com/en/pricing/`, `smoobu.com/en/channel-manager-vacation-rental/`.
- Lodgify: **the marketing site (`lodgify.com/`, `/features/`, `/pricing/`, `/why-lodgify/`,
  `/streamline-hosting/`, `/vacation-rental-channel-manager/`, `/faqs/`, `/comparisons/...`,
  `get.lodgify.com/channel-manager`) 403'd on every single attempt** — this matches the companion brief's
  finding exactly. What DID open directly: **Lodgify's own blog subdomain** —
  `lodgify.com/blog/lodgify-lowdown-may-2026/` (a first-party product-update post) opened cleanly, which is
  how the AI Co-Host / dynamic-pricing-via-Beyond / calendar-scanning facts below are sourced first-party
  despite the marketing site being blocked.

**Caveat on Hospitable's own `/pricing` page:** as the companion brief already found, `hospitable.com/pricing`
partially JS-renders; my WebFetch of it produced numbers that **contradict** the stable `help.hospitable.com`
support article on two points (Host-tier smart-device/direct-booking inclusion, and per-extra-property
dollar amounts). I treat the **help-center article as authoritative** (same call the companion brief made)
and flag the JS-page's conflicting numbers rather than silently picking one — see the Hospitable section.

**403'd / could not open directly, used secondhand with a second-source check:** Lodgify's entire marketing
site (see above — the blog subdomain was the one first-party escape hatch found this pass), G2's
Lodgify features page (`g2.com/products/lodgify/features`, 403), Smoobu's guest-app page (404 — no such
URL; guest-app content instead sourced from Capterra/support-center mentions).

**Third-party corroboration sources used throughout (labeled `[secondhand]` inline):** Capterra feature
checklists (generic category checklist, not vendor-specific — flagged where the checklist reads as a
boilerplate PMS-category list rather than Lodgify-specific claims), G2, `thehoststack.com`,
`channel-managers.com`, `rakidzich.com`-style aggregators, and Uplisting/Hospitable/Hostfully support-center
articles (first-party even when reached via search).

---

## 1. Hospitable

### Pricing / tier structure (verified via `help.hospitable.com`, the stable source)
Four tiers: **Essentials (Free, $0/mo, unlimited properties)** → **Host ($29/mo, 1 property, +$10/extra,
max 2)** → **Professional ($59/mo, 2 properties, +$15/extra, unlimited max)** → **Mogul ($99/mo, 3
properties, +$30/extra, unlimited max)**. 12% annual-billing discount. `[help.hospitable.com/en/articles/
4596748, verified, opened directly]`

### Channel management & distribution
- Channel Manager syncing **Airbnb, Vrbo, Booking.com, Agoda** with double-booking protection across
  channels `[hospitable.com/features, verified]`
- Google Vacation Rentals listing push (Direct Booking feature, not a full OTA channel) `[hospitable.com/
  features/direct-booking, verified]`

### Unified inbox / messaging
- Unified Inbox consolidating Airbnb/Vrbo/Booking.com/Agoda/direct messages `[hospitable.com/features,
  verified]`
- "Copilot AI Assistant" — AI-powered reply/review/guest-question suggestions `[hospitable.com/features,
  verified]`
- Smart Replies to common questions; multi-language translation built in `[hospitable.com/features,
  verified]`
- Message AI Assistant with **10 AI-suggested replies/week on Essentials**, scaling by tier
  `[help.hospitable.com, verified]`

### Calendar & reservation management
- Double-booking protection with calendar + pricing sync across platforms `[hospitable.com/apps content
  via WebSearch synthesis of hospitable.com/introducing-hospitables-ios-and-android-mobile-apps]`
- Manual reservation entry that still triggers automation workflows `[hospitable.com/features, verified]`

### Pricing (dynamic pricing)
- **Native Dynamic Pricing add-on**: Essentials gets it free for first 3 bookings/30 days, then **$15/property/mo**
  (help-center figure) — a separate WebFetch of the JS pricing page said "$5/property," a direct
  contradiction I cannot resolve; **treating $15/property/mo (help.hospitable.com) as authoritative**.
  Host/Professional/Mogul: dynamic pricing included in the base subscription. `[help.hospitable.com,
  verified — primary]`
- Third-party dynamic-pricing integrations: **PriceLabs, Wheelhouse, Beyond, DPGO, Homesberg, Rankbreeze,
  Rategenie** all listed as named integration partners `[hospitable.com/integrations, verified]`

### Guest experience
- Guest Portal — secure link with trip details, check-in info, upsells `[hospitable.com/features, verified]`
- Guest Verification — **Direct Premium tier**: front/back ID upload + machine authenticity check + selfie
  photo-match + passive liveness detection `[help.hospitable.com/en/articles/8383706, verified via
  WebSearch synthesis quoting the article directly]`
- Upsells: early check-in, late checkout, and custom add-ons, at a **7% processing fee** (Professional+)
  `[help.hospitable.com, verified]`
- Automated Reviews — "AI that sounds like the host" posts reviews automatically `[WebSearch synthesis of
  hospitable.com content, not independently opened for this specific claim — flagged secondhand]`

### Operations
- Team & Task Management — auto-assigns cleaning/maintenance on booking events, custom user permissions
  `[hospitable.com/features, verified]`
- Smart Lock/device integrations with **expiring access codes** for guests and cleaners; **2 devices
  included per active property on Professional, 4 on Mogul, $5/extra device** `[hospitable.com/features +
  help.hospitable.com, both verified]`
- "Pay your team" — in-platform payouts to cleaners/collaborators `[help.hospitable.com, verified]`

### Direct booking
- Direct Booking Website — Basic (1% fee) or Premium (4% host + 3% guest processing) tiers, gated to
  Professional/Mogul `[help.hospitable.com, verified]`
- "Abandoned booking recovery," promo codes with custom rules, flexible cancellation policies
  `[hospitable.com/features/direct-booking, verified — direct quote: "Abandoned booking recovery to
  recover lost revenue"]`
- Chargeback protection + **$5M damage protection** on Direct Premium `[hospitable.com/features/
  direct-booking, verified]`
- Google Vacation Rentals listing for commission-free discovery traffic `[hospitable.com/features/
  direct-booking, verified]`

### Payments & financials
- Security-deposit auto-collect/hold/release, 2% processing fee `[help.hospitable.com, verified]`
- Owner statements + Owner Portal with payouts, **gated to Mogul only** `[help.hospitable.com, verified]`
- QuickBooks accounting integration, gated to Mogul `[help.hospitable.com, verified]`
- 1.5% fee (capped at $5) for extra owner-payout runs `[companion brief, cross-referenced, consistent]`

### Analytics & reporting
- Metrics Dashboard — limited on Essentials/Host, "full"/customizable on Professional/Mogul
  `[help.hospitable.com, verified]`
- Owner/commission-based automated reports (Mogul) `[hospitable.com/features, verified]`

### Integrations
- Extensive integration marketplace with **named categories**: Accounting, AI Agents, Amenities, Channels,
  Direct Booking, Dynamic Pricing, Guest Communication, Guest Portal, Guest Registration, Guest
  Verification, Guidebook, Home Automation, Marketing, Monitoring, Operations, Professional Services,
  Security Deposits `[hospitable.com/integrations, verified — this is the fullest partner taxonomy found
  across all five products]`
- Named partners include: **BookingTrust, Clearing, Intuit QuickBooks** (accounting); **PriceLabs, Beyond,
  Wheelhouse, DPGO** (pricing); **Autohost, Chekin, Safely, Strly** (guest verification); **Breezeway,
  Cleanster, ResortCleaning, PetScreening** (operations); **Minut, Alertify** (monitoring); **StayFi,
  Mailchimp** (marketing) `[hospitable.com/integrations, verified, opened directly]`

### Owner/co-host management
- Owner Portal with payouts and statements, commission tracking — **Mogul only** `[help.hospitable.com,
  verified]`
- Unlimited secondary users on every tier including free Essentials `[help.hospitable.com, verified]`

### AI / newer features (2025-2026)
- **Hospitable is the first official MCP (Model Context Protocol) server from a short-term rental
  platform** — confirmed via Hospitable's own community changelog: *"Hospitable is the first official MCP
  server from a short-term rental platform"* `[community.hospitable.com/hospitable-changelog-3/
  hospitable-is-the-first-official-mcp-server-from-a-short-term-rental-platform-1426, verified via
  WebSearch quoting the title directly]`. Launched alongside the free Essentials plan, April 3, 2026, per
  the changelog title: *"Introducing the Essentials plan and Hospitable MCP! April 3, 2026"*
  `[community.hospitable.com, verified]`. Gives a connected AI agent (ChatGPT, Claude, Cursor) read access
  to "reservations, conversations, calendars, tasks, properties, payouts, reviews... across all your
  connected channels," and — per a later changelog entry — **smart-device control**: *"Your AI can now
  access smart devices through Hospitable MCP"* `[community.hospitable.com, verified via WebSearch quoting
  the title]`. This is the single most distinctive 2026 feature found across all five products in this
  batch — no other vendor in this catalogue has a comparable AI-agent-facing API surface.
- AI Guest Summaries — pulls guest preferences from past reviews `[hospitable.com/features, verified]`

### Mobile app
- Free iOS/Android app on every tier including Essentials; **feature parity with desktop is a stated
  goal** — *"whenever a new feature is added to the desktop version, they strive to make it available on
  the mobile apps at the same time"* `[WebSearch synthesis of hospitable.com/introducing-hospitables-ios-
  and-android-mobile-apps, not independently opened this pass — flagged secondhand but the source is a
  first-party Hospitable URL]`
- Smart-device dashboard, automated lock-code creation, real-time push notifications for new messages
  `[same source]`

---

## 2. Lodgify

### Pricing / tier structure — CONFLICTING secondhand figures, flagged (Lodgify's own pricing page 403'd
on every attempt, consistent with the companion brief)
Two independent secondhand syntheses disagree on exact dollar amounts and even tier count:
- **4-tier version** (thehoststack.com review, opened directly): Basic $14/mo (1 property, 1.9% fee) →
  Starter $16/mo annual (max 2 properties, 1.9% fee) → Professional $40/mo annual (unlimited, no fee) →
  Ultimate $59/mo annual (unlimited, no fee).
- **3-tier version** (WebSearch synthesis of multiple review sites): Starter $26/mo → Professional $42/mo
  → Ultimate $62/mo (annual-billed), with a monthly-billed variant running higher.
Both agree on the **qualitative tier-gating** (see below) even though dollar figures diverge — I'm treating
the qualitative gating as more reliable than either specific number.

### Tier-gating (qualitative, corroborated across 2 independent secondhand sources)
- **Starter/Basic:** channel sync, direct booking website, payment processing, "AI-assisted inbox," basic
  automated messaging, email-only support, **1.9% booking fee applies**.
- **Professional:** adds full guest-messaging automation, **Google Vacation Rentals listing**, damage
  protection pre-authorization, phone support, **booking fee drops to 0%**.
- **Ultimate:** adds task automation, guest invoicing, **owner reporting + analytics**, **team permission
  management**, priority chat support. `[thehoststack.com/lodgify-review-2026/, opened directly, + a second
  independent WebSearch-synthesized comparison agreeing on the same feature-gating pattern]`

### Channel management & distribution
- Two-way API sync with **Airbnb, Booking.com, Vrbo, Expedia**; **Airbnb and Booking.com sync in real
  time, Vrbo updates hourly**; iCal for additional channels `[WebSearch synthesis of lodgify.com content,
  secondhand — vendor page 403'd]`
- Google Vacation Rentals integration, Professional tier and above `[same, secondhand]`

### Unified inbox / messaging
- Unified Inbox pulling messages from all connected channels + direct-booking site, with **AI-assisted
  reply suggestions** `[WebSearch synthesis, secondhand]`
- **"Improve with AI" / "Suggest with AI" buttons** inside the reservation interface for guest replies —
  found via a first-party blog reference, though the specific page describing it wasn't independently
  opened `[secondhand, WebSearch synthesis of lodgify.com/blog content]`

### Calendar & reservation management
- **Calendar-scanning feature (2026 launch)**: *"identifies bookable gaps and orphan nights hidden by
  minimum-stay rules, surfacing them with a single tap to fix"* `[lodgify.com/blog/lodgify-lowdown-
  may-2026/, verified, opened directly — this is a first-party quote]`
- Standard multi-property calendar sync to prevent double bookings `[secondhand, consistent across sources]`

### Pricing (dynamic pricing)
- **New (2026) native dynamic-pricing engine "powered by Beyond"**: *"combines Lodgify's AI... with
  Beyond's real-time market data and dynamic pricing algorithm. Prices update automatically each day"*
  `[shorttermrentalz.com/news/lodgify-introduces-dynamic-pricing-and-ai-updates/, verified, opened
  directly, quoting Lodgify's own announcement]`. Older native dynamic pricing charged **0.8% per booking**
  per one secondhand source `[secondhand]`.
- PriceLabs integration also available and, per a third-party review, "typically works out cheaper than
  Lodgify's built-in dynamic pricing" for higher-priced/high-occupancy properties `[WebSearch synthesis
  citing PriceLabs' own integration page, secondhand]`

### Guest experience
- Guest messaging automation (Professional+); damage-protection pre-authorization (Professional+)
  `[thehoststack.com, verified]`
- Truvi integration for **guest screening and damage protection** — named explicitly: *"Truvi for guest
  screening and damage protection fills the gap that opens up when you move beyond OTA bookings"`
  `[secondhand, WebSearch synthesis]`; also **Safely.com and Properly Damage Waiver** for embedded
  insurance `[secondhand]`
- Airbnb-style auto-replies for common guest questions (part of Airbnb's own 2026 updates, not Lodgify's —
  noted to avoid misattribution) `[lodgify.com/blog/lodgify-lowdown-may-2026/, verified]`

### Operations
- **Ultimate tier**: task automation + advanced cleaning/task management `[thehoststack.com, verified;
  companion brief corroborates independently: "Ultimate tier claims 'advanced...cleaning management'"]`
- **Redesigned Users page (2026)**: cleaner team-member add/manage flow, **assign rentals during the
  invitation process** `[WebSearch synthesis of a Lodgify product-update source, secondhand but describes
  a first-party feature]`
- Lodgify Smart Locks: connects **Lynx, Nuki, Chekin**; auto-generates unique per-reservation access codes;
  **$7/connected device/month** `[secondhand, WebSearch synthesis]`

### Direct booking
- No-code Website Builder — drag-and-drop templates, custom domain, live in "under 5 minutes" per
  marketing copy `[secondhand, consistent across multiple review sources]`
- Built-in Booking Engine accepting reservations + payments directly on the site `[secondhand]`
- Rated by an independent third-party aggregator as **"best in class"** for direct-booking conversion
  design, per the companion brief's cross-reference `[companion brief, `rakidzich.com`, secondhand]`
- **ChatGPT pilot (2026)**: *"a direct connection between independent hosts' direct booking sites and
  ChatGPT," allowing guests to describe desired stays and receive commission-free property matches*
  `[shorttermrentalz.com, verified, opened directly]`

### Payments & financials
- QuickBooks Online, Xero, FreshBooks integrations for automated owner statements `[secondhand, WebSearch
  synthesis]`
- **Ultimate tier**: guest invoicing `[thehoststack.com, verified]`
- **Q4 2026 roadmap item**: "accounting AI for tax preparation" and "embedded insurance products"
  `[WebSearch synthesis of a Lodgify roadmap source, secondhand]`

### Analytics & reporting
- **Ultimate tier only**: "advanced analytics features to visualize occupation rates, cancellation
  reasons, and other performance metrics," owner reporting `[WebSearch synthesis + thehoststack.com, two
  independent sources agreeing on Ultimate-tier gating]`
- Companion brief independently found Lodgify's financial reporting described by a third-party aggregator
  as **"limited," "an afterthought,"** with an explicit recommendation against using Lodgify for co-hosting
  3+ properties — **flag this as a real tension**: Lodgify's own marketing claims Ultimate-tier "advanced
  analytics," but an independent comparison site rates the category weak overall. Both can be true if the
  weakness is in owner-statement/trust-accounting depth specifically rather than dashboard analytics.

### Integrations
- 100+ third-party integrations per marketing claims `[secondhand]`; named partners: **PriceLabs
  (pricing), Truvi/Safely/Properly (screening & damage), Lynx/Nuki/Chekin (smart locks), QuickBooks/
  Xero/FreshBooks (accounting)** `[secondhand, consistent across 2+ independent sources per partner]`

### Owner/co-host management
- Team-permission management (Ultimate tier) `[thehoststack.com, verified]`
- Owner reporting (Ultimate tier) `[thehoststack.com, verified]`

### AI / newer features (2025-2026)
- **AI Co-Host (beta, 2026)**: *"an always-on operator that proactively scans bookings, messages, and
  upcoming stays, surfacing only whatever needs a host's decision... available across Lodgify, WhatsApp,
  and iMessage, with the first version arriving this summer [2026]"* `[lodgify.com/blog/lodgify-lowdown-
  may-2026/, verified, opened directly — first-party]`
- ChatGPT direct-booking pilot (above) `[verified, first-party]`
- "AI search optimization" — visibility in AI-powered search results, mentioned but not detailed
  `[lodgify.com/blog/lodgify-lowdown-may-2026/, verified, opened directly, though the mechanism is not
  explained on the page]`
- Full brand refresh (new logo/colors "Pioneering Yellow") — cosmetic, noted only for completeness
  `[verified, same source]`

### Mobile app
- Dedicated iOS/Android app, relaunched per *"Lodgify Releases its Brand New Mobile App for Hosts"*
  `[secondhand headline via WebSearch, matches a first-party lodgify.com/blog URL not independently opened
  this pass]`

---

## 3. Uplisting

### Pricing / tier structure (verified via direct fetch of `uplisting.io/pricing` — GBP-denominated,
current as of this pass)
- **Independent Host:** £72/month flat, 1–5 properties.
- **Portfolio Manager** (marked "Most Popular"): £16/property/month, 6–40 properties.
- **Premier:** custom pricing, 41+ properties.
- Add-ons: **Client Statements + Portal £8/property/mo; Security Deposits £4/property/mo; Guest ID
  Verification £1.65/verification.** `[uplisting.io/pricing, verified, opened directly]`

**Flag:** a separate WebSearch synthesis independently reported a **USD** "$100/month + $20/month per
property" Pro-tier structure with an "Enterprise" custom tier — this **disagrees** with the GBP page I
opened directly (different tier names too: Pro/Enterprise vs Independent Host/Portfolio Manager/Premier).
The direct fetch is the more trustworthy, current source; the USD figures may be an older pricing scheme,
a regional variant, or a stale aggregator page — **treating the direct fetch as authoritative** and flagging
the conflict rather than silently picking one, per the honesty bar.

### Channel management & distribution
- Channel Manager for **Airbnb, Vrbo, Booking.com** confirmed directly; a fuller channel count wasn't
  found on Uplisting's own pages — one third-party comparison implies Uplisting's channel list is narrower
  than category leaders, noting Uplisting "focuses on these core channels" vs. competitors with 60+
  `[WebSearch synthesis comparing Uplisting to Hostaway/Rentals United, secondhand]`
- iCal connections available for additional platforms beyond the direct API partnerships `[secondhand]`
- "0% commission on bookings" stated as a core positioning claim across all tiers `[uplisting.io/features,
  verified, opened directly]`

### Unified inbox / messaging
- Unified Inbox across OTA + direct channels `[uplisting.io/features, verified]`
- **Enquiry Auto-Responder**: configurable 0–60 minute delay, *"can auto-respond to guest enquiries in
  seconds... some members prefer to delay up to 60 minutes to allow them to respond manually"*
  `[support.uplisting.io/docs/enquiry-auto-responder, verified via WebSearch quoting the doc directly]`;
  if a host responds manually first, the auto-responder **does not** double-send `[same source, verified]`
- Dynamic message tags (e.g. `{guest_first_name}`) for templated personalization `[support.uplisting.io,
  verified via WebSearch quote]`
- **SMS messaging** from the Unified Inbox directly to guest phones `[uplisting.io content via WebSearch
  synthesis, secondhand]`
- AI Messaging / "Airbnb Auto Responder" listed as a distinct feature line on Uplisting's own features page
  `[uplisting.io/features, verified, opened directly]`

### Calendar & reservation management
- Multi-Calendar — single view across all connected channels `[uplisting.io/features, verified]`
- Real-time sync explicitly marketed to prevent double bookings `[channel-managers.com review, verified,
  opened directly]`

### Pricing (dynamic pricing)
- **No native dynamic-pricing engine advertised** — Uplisting relies entirely on third-party integrations:
  **PriceLabs (rated 4.9/5 for the Uplisting integration per a review aggregator), Beyond, Wheelhouse**
  `[WebSearch synthesis of uplisting.io/integrations content, secondhand]`. This is a genuine gap relative
  to Hospitable/Lodgify/Smoobu, all three of which now have a native/first-party pricing engine.

### Guest experience
- **eSign Rental Agreements**: *"displayed to guests on the guest confirmation page, alongside the security
  deposit and guest identity verification modules... guests can sign... and receive a downloadable PDF"*
  `[support.uplisting.io/docs/esign-rental-agreements, verified via WebSearch quote]`
- **Guest Identity Verification** — paid add-on `[uplisting.io/features, verified]`
- **Automated Reviews** — collection automation to "boost a listing's credibility"; auto-responds to
  Airbnb enquiries to help Airbnb search ranking `[secondhand, WebSearch synthesis]`
- Single "booking welcome page" bundling: reservation review, deposit collection, ID upload +
  auto-verification, real-email capture, and rental-agreement e-sign `[secondhand, WebSearch synthesis]`

### Operations
- Cleaning Scheduler `[uplisting.io/features, verified]`
- **Security Deposits** — automated multi-attempt charging: *"first attempts to charge a security deposit
  24 hours before the guest's arrival time, then attempts to charge 8 more times over a few hours, with
  the last attempt 6 hours after the first attempt"* `[WebSearch synthesis quoting Uplisting's own support
  docs, secondhand but a first-party doc]`
- Message filters (a support-doc feature found but not detailed further) `[support.uplisting.io, found via
  search title only, not opened]`

### Direct booking
- Direct Booking Website, included from the Independent Host tier up `[uplisting.io/pricing, verified]`

### Payments & financials
- Guest Payment Links, Guest Payment Plans, Stripe/PayPal-based payments `[uplisting.io/features, verified]`
- **Client (Owner) Statements + Portal** — paid add-on, £8/property/mo `[uplisting.io/pricing, verified]`
- Security Deposits — paid add-on, £4/property/mo, or a flat "$6/property/mo" figure cited by a different
  secondhand source — **flag the £4 vs $6 discrepancy as unresolved (currency + possible stale-source
  mismatch)**, treating the direct-fetched £4/property/mo as authoritative.

### Analytics & reporting
- **This is Uplisting's most explicitly self-acknowledged weak spot.** A WebSearch synthesis of Capterra
  content states: *"the Uplisting team recognizes that their reporting features have room for
  improvement, and their product team is continuously working on enhancements"* `[WebSearch synthesis of
  Capterra reviews, secondhand, but directly attributed to Uplisting's own team's public acknowledgment]`.
  No native analytics/BI dashboard was found on Uplisting's own pages; the workaround suggested by users is
  **exporting bookings to Airtable/Google Sheets via Zapier** to build custom reports `[secondhand,
  WebSearch synthesis]`.

### Integrations
- Uplisting's own `/integrations` page is the most thoroughly categorized integration page I opened for
  any of the five, with named categories and partners:
  - **Guest Communication & AI:** HostBNB.ai, Duve, Touch Stay, SuiteOp
  - **Smart Locks:** August, Alfred, Kwikset, Schlage, Yale, Nuki, TTLock, RemoteLock, GateGoing, Jervis
    Systems
  - **Cleaning:** Lula.Cleaning, Cleanster, Turno, ResortCleaning, Properly
  - **Dynamic Pricing:** PriceLabs, Beyond, Wheelhouse, Rented.com, IntelliHost
  - **Payments/Financial:** Stripe, ClearSplit, bookingtrust, VRPlatform, Clearing
  - **Guest Screening/Insurance:** Truvi, Safely, Strly
  - **Noise/Occupancy:** Minut, Alertify
  - **WiFi/Guest Services:** StayFi, DACK
  - **Marketing:** Google Ads, Facebook Pixel, Google Analytics
  - Plus Dtravel (blockchain direct booking), Zapier, Lindy, KeyNest, TrustedStays
  `[uplisting.io/integrations, verified, opened directly — the fullest single-page taxonomy found for
  Uplisting]`

### Owner/co-host management
- Client Owner Portal + Statements — paid add-on `[uplisting.io/features, verified]`

### AI / newer features (2025-2026)
- AI Messaging / automated response generation listed as a feature line, but no dedicated "what's new in
  2026" AI announcement was found for Uplisting the way there was for Hospitable/Lodgify/Hostfully —
  **flag this as a genuine gap in what I could find**, not necessarily a gap in the product; Uplisting may
  simply not publish an AI-specific changelog.

### Mobile app
- Dedicated iOS and Android apps confirmed via an independent review: *"Mobile Apps: Dedicated iOS and
  Android applications"* `[channel-managers.com/channel-manager/best-channel-manager-comparison/
  uplisting-review/, verified, opened directly]`

---

## 4. Hostfully

**Two distinct product lines, priced separately — do not conflate them:**
1. **Property Management Platform (full PMS)**
2. **Digital Guidebooks** (can be bought standalone, without the PMS)

### Pricing / tier structure — PMS (verified via direct fetch of `hostfully.com/pricing/`, current)
- **Growth:** from $15/property/month + platform fee, best for 1–50 listings. Includes full PMS, 24/7
  support, mobile app, **1% payment gateway fee, 0.85% direct-booking fee**.
- **Pro:** from $25/property/month + platform fee, best for 1–199 listings. Everything in Growth, **no
  payment gateway fee, no direct-booking commission**, dedicated Customer Success Manager.
- **Enterprise:** custom, 200+ listings. Everything in Pro + tailored onboarding, priority support.
- All tiers: 120+ integrations, onboarding assistance, 300+ help articles. `[hostfully.com/pricing/,
  verified, opened directly]`

**Flag:** a separate WebSearch synthesis surfaced an apparently older/different PMS pricing scheme —
**Starter $49/mo, Pro $129/mo, Premium $219/mo, Gold $499/mo** — which conflicts with the per-property +
platform-fee model on the page I opened directly. Given the direct fetch is the live current page, I'm
treating the **per-property + platform-fee structure as current** and the flat-tier numbers as likely
**stale/outdated** (possibly a pre-2026 pricing scheme still indexed by aggregators) — flagging rather than
discarding, since I can't rule out both being real (e.g., different regions or grandfathered plans).

### Pricing / tier structure — Digital Guidebooks (standalone product, secondhand)
**Power Host $9.99/mo → Prime $24.99/mo → Prime Plus $49.99/mo → Professional $75/mo**, plus a genuinely
free tier ("first guidebook always free, forever") `[WebSearch synthesis, secondhand, not independently
opened for the dollar figures — but the "first guidebook free" claim is corroborated by the directly-opened
digital-guidebooks features page]`.

### Channel management & distribution
- Channel Manager syncing **60+ channels** including **Airbnb, Vrbo, Booking.com, Expedia, Homes & Villas
  by Marriott Bonvoy** `[WebSearch synthesis of hostfully.com/property-management-software/features/
  channel-manager/, secondhand but a direct quote of Hostfully's own copy: "syncs your listings across
  direct booking sites, Airbnb, Vrbo, Booking.com, and 60+ more channels"]`
- Open API for connecting **niche/regional OTAs** beyond the pre-built 60+ `[same source, secondhand]`
- **Booking Pipeline** — tracks the guest journey from lead to booking completion, explicitly framed as
  double-booking prevention `[hostfully.com/property-management-platform/, verified, opened directly]`

### Unified inbox / messaging
- **Unified Inbox + InboxAI**: *"consolidates messages from Airbnb, Vrbo, Booking.com, and direct
  bookings into one place, and InboxAI drafts contextual replies by pulling from your property data and
  guidebook content"* `[shorttermrentalz.com/news/hostfully-inboxai-tool-guest-communication/, verified via
  WebSearch quoting the announcement directly]`
- InboxAI: *"understands your tone and preferences," approve/edit/send workflow, and **multi-lingual
  automatic replies in the guest's preferred language*** `[WebSearch synthesis of hostfully.com/pmp-
  features/inboxai/, secondhand but quoting first-party copy]`

### Calendar & reservation management
- Central Calendar — single view across all platforms, explicit double-booking prevention
  `[hostfully.com/property-management-platform/, verified]`
- Pre-Arrival Forms to collect guest info ahead of stay `[hostfully.com/property-management-platform/,
  verified]`

### Pricing (dynamic pricing)
- **No fully native dynamic-pricing engine found** — Hostfully leans on integrations: **PriceLabs (rated
  4.7 on Hostfully's own integration listing) and Wheelhouse (rated 4.5)** `[WebSearch synthesis quoting
  Hostfully's stated analysis of "2,200+ accounts and 31,000+ active integrations, mapping adoption of
  dynamic pricing tools," secondhand]`
- Custom API automation can push dynamic-pricing updates via the Open API `[same source, secondhand]`

### Guest experience
- **Digital Guidebooks**: Guidebook Wizard for quick content creation, branded templates, bulk-edit across
  multiple guidebooks, Google-sourced local recommendations import, **auto pins + self-check-in PIN codes
  for smart locks**, **16+ language auto-translation** `[hostfully.com/digital-guidebooks/features/,
  verified, opened directly]`
- **AI Itinerary Planner** — *"a first-of-its-kind feature in the digital guidebook industry"* generating
  personalized activity/restaurant recommendations from guest prompts (timing, seasonality, duration,
  group size/ages, interests) `[WebSearch synthesis of help.hostfully.com/en/articles/7946692, verified via
  direct quote of Hostfully's own announcement]`
- **Viator affiliate integration**: *"When you connect your Viator account with Hostfully, the AI Planner
  will pull activity links from Viator, earning you an 8% commission on all activities guests book"*
  `[hostfully.com/digital-guidebooks/features/, verified, opened directly — a genuinely distinctive
  monetization feature not found on any other of the five products]`
- Upsell add-ons: early check-in, late checkout, baby gear, bikes, mid-stay cleanings, airport pickups, "in-
  home chef services" `[hostfully.com/digital-guidebooks/features/, verified]`
- Guest screening + automatic damage protection described qualitatively (*"friction-free guest screening,
  automatic damage protection, and fast, direct payouts"*) but no dollar figure or mechanism found
  `[WebSearch synthesis of hostfully.com/property-management-software/features/channel-manager/, secondhand]`
- Digital rental agreements with e-signature capture `[hostfully.com/property-management-platform/,
  verified]`

### Operations
- **Four built-in user roles**: Property Manager, Booking Agent, Property Sales Manager, Associate — plus
  separate "Service Provider" account types for cleaners/greeters/maintenance `[WebSearch synthesis
  quoting hostfully.com/pmp-features/user-permissions/ directly, secondhand but first-party-quoted]`
- Task Management: title/description/duration/assignee/checklist/photos/notes per task; **event-triggered
  tasks** (e.g. auto-create a cleaning task on checkout, schedule maintenance ahead of arrival)
  `[WebSearch synthesis of hostfully.com/property-management-software/features/task-management/,
  secondhand but first-party-quoted]`
- **Hostfully Devices** — smart-device management add-on, **$6/device/month**, supporting 200+ device
  types: locks, keypads, thermostats, garage doors, lockboxes, safes, cabinets, lights, switches, plugs,
  hubs, hot tubs, pool heaters `[WebSearch synthesis of hostfully.com/hostfully-devices/, secondhand but
  first-party-quoted]`

### Direct booking
- Direct Booking Site included on all PMS plans (not gated), explicitly framed to "reduce OTA fees" and
  "promote add-ons" `[hostfully.com/property-management-platform/, verified]`
- Growth tier charges **0.85% direct-booking fee**; Pro/Enterprise **waive it** `[hostfully.com/pricing/,
  verified]`

### Payments & financials
- Payment processing via **PayPal, Stripe, Vacation Rent Payment** `[hostfully.com/property-management-
  platform/, verified]`
- Growth tier: **1% payment-gateway fee**; Pro/Enterprise: **waived** `[hostfully.com/pricing/, verified]`
- **Owner Portal**: view bookings, financial statements ("net rates" = total rent minus agency commission),
  owner date-blocking, real-time notifications, multi-property dashboard, in-portal messaging, Airbnb
  account connection, **multi-language (French/English/Spanish/Portuguese, Polish/German/Dutch "coming
  soon")**, owner-adjustment tracking, deduction documentation for fees/repairs/expenses charged to owners
  `[hostfully.com/pmp-features/owner-portal/, verified, opened directly — the single most detailed owner-
  portal feature list found across all five products]`

### Analytics & reporting
- Reporting & Analytics: customizable automated reports, **report scheduler** for recurring reports,
  exportable as **PDF for operations teams** or **CSV RevPar snapshots for pricing managers**
  `[WebSearch synthesis of hostfully.com/property-management-software/features/enhanced-reporting/,
  secondhand but first-party-quoted]`

### Integrations
- **120+ integrations** stated across all PMS tiers `[hostfully.com/pricing/, verified]`; a separate page
  claims **150+** — minor discrepancy, both first-party pages, not reconciled
- **Open API + webhooks**: configurable webhook triggers on new booking, modification, cancellation, for
  pushing data to third-party apps `[WebSearch synthesis of hostfully.com/glossary/external-webhook-
  integration/, secondhand but first-party-quoted]`

### Owner/co-host management
- Owner Portal (detailed above) — included, not a top-tier-only gate the way Hospitable gates it to Mogul
  `[hostfully.com/pmp-features/owner-portal/, verified]`

### AI / newer features (2025-2026)
- **InboxAI** (guest-messaging AI, multi-lingual) — launched 2026 per shorttermrentalz.com's announcement
  coverage `[verified, see Unified Inbox section above]`
- **AI Itinerary Planner** with Viator revenue-share — a first-of-category claim `[verified, see Guest
  Experience section]`

### Mobile app
- iOS/Android app with a **"Service Hub"**: cleaners/maintenance/service-providers view tasks by job-view
  or calendar-view, receive push notifications `[WebSearch synthesis of hostfully.com/mobile-app/,
  secondhand but first-party-quoted]`

---

## 5. Smoobu

### Pricing / tier structure (verified via direct fetch of `smoobu.com/en/pricing/`)
- **Professional Flex:** €29/mo (~$33.15), **0.9% booking fee**, all Professional Prepaid features.
- **Professional Prepaid:** €31.50/mo with 10% annual discount (~$36.01), **0% booking fee** — includes
  Website Builder, invoicing, customer-service chat, iOS/Android app, Channel Manager, email+phone support,
  Price Sync, Guest Guide, Communications, Guest Management (CRM), Booking System (Stripe/PayPal), Custom
  Templates, Online check-in, Connected Accounts, **Full API Access**, Reservation System (PMS), Booking
  Website, Statistics.
- **Teams Pro+:** €49.50/mo with 10% annual discount (~$56.58), **0% booking fee** — everything above plus
  e-invoicing, **2 months free Dynamic Pricing**, prioritized support, **two write-access accounts**.
`[smoobu.com/en/pricing/, verified, opened directly]`

**Flag:** a separate secondhand source describes a "Team" tier at **$179.10/mo with unlimited read-only
accounts** and a lower-priced "Professional" at $26.10/mo — these don't map cleanly onto the three tiers
found on the directly-fetched pricing page (Professional Flex / Professional Prepaid / Teams Pro+); likely
either an older tier name set or a different currency/region snapshot. Treating the directly-fetched page
as current and authoritative.

### Channel management & distribution
- Channel Manager instantly syncing calendars across **Airbnb, Booking.com, Expedia, Agoda, TripAdvisor,
  Vrbo/HomeAway**, and more — one third-party estimate puts the total near **100+ OTA connections**, another
  near **~80 booking partners**; neither figure independently confirmed on Smoobu's own page, which names
  channels but doesn't publish a total count `[smoobu.com/en/channel-manager-vacation-rental/, verified for
  the named channels; the "100+"/"~80" totals are secondhand and unreconciled]`
- **"Real-time booking synchronization"** stated explicitly as eliminating double-booking risk
  `[smoobu.com/en/channel-manager-vacation-rental/, verified, direct quote: "instantly synchronizes booking
  calendars across major global portals...automating updates and eliminating the risk of double bookings"]`

### Unified inbox / messaging
- "Communications" module — included on Professional Prepaid+ `[smoobu.com/en/pricing/, verified]`
- **AI-powered real-time message translation (2026)**: *"Hosts can now instantly translate incoming guest
  messages into their own language, and easily translate their own replies into the guest's language before
  sending"* `[WebSearch synthesis of smoobu.com/en/blog/smoobu-monthly-product-updates-april-2026-edition/,
  secondhand but quoting Smoobu's own product-update post directly]`
- Automated post-checkout review-request messages: *"lets you automate a post-checkout message that thanks
  the guest and kindly requests a review... set up message templates once — including a review request —
  and they fire automatically forever"* `[WebSearch synthesis quoting Smoobu's own guide content,
  secondhand but first-party-quoted]`
- Unified review management centralizing Airbnb/Booking.com/Expedia review responses, with the ability to
  **respond to Airbnb guest reviews without logging into Airbnb** `[secondhand, WebSearch synthesis]`
- Revyoos integration adds cross-platform review aggregation (Airbnb, Booking, Vrbo, Google) `[secondhand]`
- **Messages page overhaul (2026)**: mark individual/bulk messages read/unread or delete in bulk,
  color-coded host/guest bubbles, booking-detail dropdown per conversation `[WebSearch synthesis of Smoobu's
  April 2026 product-update post, secondhand but first-party-quoted]`

### Calendar & reservation management
- Unified calendar view across all connected properties/channels `[smoobu.com/en/channel-manager-vacation-
  rental/, verified]`
- **Reservation System (PMS)** listed as its own line item distinct from the channel manager, included from
  Professional Prepaid `[smoobu.com/en/pricing/, verified]`
- Performance updates (2026): faster calendar-page load times, described as a dedicated engineering focus
  `[WebSearch synthesis of April-2026 update post, secondhand but first-party-quoted]`

### Pricing (dynamic pricing)
- **Dynamic Pricing sold as a separate paid add-on**, not bundled into any tier by default: **€12.99/mo per
  property** `[companion-brief-adjacent WebSearch synthesis, corroborated independently this pass]`; **2
  months free** when included in a Teams Pro+ signup promo `[smoobu.com/en/pricing/, verified]`

### Guest experience
- **Guest Guide** — in-app guest guide/digital guidebook module, included Professional Prepaid+
  `[smoobu.com/en/pricing/, verified]`
- **Online check-in**: guest ID/registration + verification workflow; can require ID upload + deposit
  before releasing automated check-in codes `[support.smoobu.com articles via WebSearch synthesis,
  secondhand but first-party-quoted]`
- Chekin integration adds a dedicated guest-data-collection/check-in flow `[smoobu.com/en/integrations/
  chekin/, verified via WebSearch synthesis of the page title/content, secondhand]`
- Multi-language and **multi-currency support** explicitly marketed for international hosts `[WebSearch
  synthesis of smoobu.com app-store copy, secondhand but first-party-quoted]`

### Operations
- Statistics/reporting module included from Professional Prepaid `[smoobu.com/en/pricing/, verified]`
- **"Two write-access accounts"** on Teams Pro+ vs. presumably single-user on lower tiers (page doesn't
  explicitly state single-user-only on Flex/Prepaid, but the Teams-tier callout implies it's the
  differentiator) `[smoobu.com/en/pricing/, verified for the Teams Pro+ line, inferred for the gating logic]`
- **Face ID login (iOS, 2026)** `[WebSearch synthesis of April-2026 product update, secondhand but
  first-party-quoted]`

### Direct booking
- **Website Builder** — no-code, included Professional Prepaid+ `[smoobu.com/en/pricing/, verified]`
- **Booking Engine** — customizable, marketed to "decrease reliance on third-party platforms and their high
  commission fees," works with the built-in Website Builder `[smoobu.com/en/channel-manager-vacation-
  rental/ + WebSearch synthesis of smoobu.com/en/booking-system-engine-vacation-rental/, verified/secondhand
  mix]`

### Payments & financials
- Booking System including **Stripe & PayPal** `[smoobu.com/en/pricing/, verified]`
- New (2026) **invoicing solution / e-invoicing** feature, called out explicitly as "New" on the pricing
  page `[smoobu.com/en/pricing/, verified]`
- Booking-fee structure itself is a financial lever: **Professional Flex charges 0.9% per booking in
  exchange for a lower flat monthly rate; Professional Prepaid/Teams Pro+ charge 0% but cost more upfront**
  — this flex/prepaid trade-off is a genuinely distinctive pricing mechanic not seen (in this exact form) on
  any of the other four products `[smoobu.com/en/pricing/, verified]`

### Analytics & reporting
- "Statistics" module — included from Professional Prepaid; described elsewhere as covering "reservations,
  revenue, and channel performance" with "one-click report generation," though the pricing page itself just
  lists "Statistics" as a line item without elaborating `[smoobu.com/en/pricing/, verified for inclusion;
  the elaboration is secondhand WebSearch synthesis]`

### Integrations
- **Full API Access** included from Professional Prepaid `[smoobu.com/en/pricing/, verified]`
- Named integration partners found: **Chekin** (check-in/guest data), **Revyoos** (reviews) — Smoobu's own
  integration-category pages (e.g., `smoobu.com/en/integration-category/online-check-in/`) suggest a
  broader marketplace exists, but I did not open a full integrations-directory page the way I did for
  Hospitable/Uplisting, so **Smoobu's integration breadth is under-documented in this pass relative to the
  other four** — flagging as a real gap in this catalogue, not a claim that Smoobu lacks integrations.

### Owner/co-host management
- No dedicated "Owner Portal" feature was found advertised on Smoobu's own pricing/channel-manager pages —
  **this appears to be a genuine feature gap relative to Hospitable, Hostfully, and Uplisting**, all three
  of which explicitly sell an owner-portal/owner-statements feature. Not confirmed absent (I did not
  exhaustively search Smoobu's full site), but notably absent from every page I opened.

### AI / newer features (2025-2026)
- AI-powered real-time message translation (above) — the main named AI feature found for Smoobu
  `[verified via direct quote, see Unified Inbox section]`
- No dedicated AI-copilot, AI-agent-API, or AI-itinerary feature was found for Smoobu — relative to
  Hospitable's MCP server and Hostfully's InboxAI/AI Itinerary Planner, **Smoobu's AI surface area looks
  the thinnest of the five products in this batch** based on what I could open/find.

### Mobile app
- iOS & Android app, called out as "New" on the pricing page (i.e., a genuinely recent addition, not a
  long-standing feature) `[smoobu.com/en/pricing/, verified]`
- **Face ID authentication (iOS, 2026)** `[secondhand, first-party-quoted, see Operations section]`

---

## 6. Cross-product synthesis — what's table-stakes across ALL or MOST of these five

**Present on all five (Hospitable, Lodgify, Uplisting, Hostfully, Smoobu) — the strongest table-stakes
signal:**
1. **Channel manager syncing at minimum Airbnb + Booking.com + Vrbo**, with real-time or near-real-time
   two-way availability/rate sync and double-booking prevention as the explicit marketing claim.
2. **Unified inbox** consolidating messages across all connected channels plus direct bookings.
3. **Automated/templated guest messaging** (check-in instructions, confirmations, review requests at
   minimum), with per-vendor variation only in automation *depth* (branching logic, AI-drafted replies)
   not in the base capability's presence.
4. **Direct-booking website + booking engine**, either included in the base tier (Hostfully, Smoobu
   Professional+, Hospitable Host+) or as a clearly-priced first-party add-on (Uplisting, all Lodgify
   tiers) — none of the five treats this as a third-party-only feature.
5. **Some form of guest-facing digital guidebook/portal** (Hospitable's Guest Portal, Hostfully's flagship
   Digital Guidebooks product, Smoobu's Guest Guide, Uplisting via Touch Stay integration, Lodgify via
   third-party guidebook partners).
6. **Task/cleaning-operations feature**, either native (Hostfully Task Management, Uplisting Cleaning
   Scheduler, Hospitable Team & Task Management, Lodgify Ultimate-tier cleaning management) or via a
   named first-party integration partner (all five integrate Turno and/or Breezeway-class tools).
7. **Security-deposit / damage-protection handling**, though maturity varies sharply: native +
   dollar-figured on Hospitable (2% fee, $5M coverage claim) and Uplisting (automated multi-attempt
   charging), integration-based on Lodgify (Truvi/Safely) and Smoobu (via Chekin-adjacent tools), and
   qualitatively-described-only on Hostfully ("automatic damage protection," no mechanism found).
8. **Team/multi-user access with role-based permissions**, present on all five but gated differently:
   free/unlimited on Hospitable (even the $0 tier), tier-gated on Lodgify (Ultimate only) and Smoobu
   (Teams Pro+ only), paid-per-property add-on on Uplisting, and role-count-limited (4 named roles +
   service-provider accounts) on Hostfully.
9. **Third-party dynamic-pricing integration with PriceLabs and/or Wheelhouse/Beyond**, universal across
   all five — but **native, first-party dynamic pricing is NOT universal**: Hospitable, Lodgify (2026,
   powered by Beyond), and Smoobu (paid add-on) have shipped a native engine; **Uplisting and Hostfully
   have not** and rely entirely on integrations. This directly echoes the companion brief's finding for
   Hostaway/Guesty/OwnerRez ("none of these include dynamic pricing native" at base tier) — dynamic
   pricing-as-a-stacked-cost is the dominant pattern across the whole eight-product union, not just this
   batch of five.
10. **Mobile app (iOS + Android)** — present on all five, though Smoobu's is explicitly flagged "New" on
    its own pricing page (i.e., the most recently-shipped of the five), and Hospitable's is the only one
    with an explicitly-stated feature-parity-with-desktop commitment.

**Present on most (3-4 of 5), notably absent or unconfirmed on the rest:**
- **Native owner portal with financial statements**: present and well-developed on Hospitable (Mogul-only),
  Hostfully (all tiers, the most detailed of the five), and Uplisting (paid add-on) — **not found
  advertised anywhere on Smoobu's own pages** (flagged as a real gap above), and gated to Lodgify's
  top Ultimate tier only.
- **AI-drafted guest-reply assistant**: present on Hospitable (Copilot), Lodgify ("Improve/Suggest with
  AI"), Hostfully (InboxAI), Uplisting (AI Messaging line item) — Smoobu's only confirmed AI feature is
  translation, not reply-drafting, making it the outlier.
- **Native guest-ID/identity verification with photo/liveness matching**: detailed and dollar-figured on
  Hospitable (Direct Premium) and Uplisting (paid add-on, £1.65/verification); integration-based on
  Lodgify (Truvi) and Smoobu (Chekin); not separately detailed for Hostfully beyond a qualitative
  "friction-free guest screening" claim.

**A genuinely differentiating (not table-stakes) feature found in this batch:**
- **Hospitable's MCP server** (first official STR-platform MCP server, giving external AI agents
  read/write-adjacent access to reservations, calendars, payouts, smart devices) has no analog on any of
  the other four products in this batch, nor (per the companion brief) on Hostaway/Guesty/OwnerRez.
- **Hostfully's Viator-affiliate AI Itinerary Planner** (8% commission revenue-share on guest-booked
  activities, generated via an AI itinerary tool) is likewise unique to Hostfully among all eight products
  now catalogued across both research passes.
- **Smoobu's Flex-vs-Prepaid booking-fee trade-off** (pay a % of bookings for a lower flat rate, or pay
  more flat and drop the % to zero) is a pricing *mechanic*, not a feature, but it's a structurally
  distinct choice-of-model not seen on any other of the eight products.

---

## Not found / could not verify — full list (per the honesty bar)

- **Lodgify's official marketing-site pricing figures** — every direct URL attempt 403'd (root, /pricing/,
  /features/, /why-lodgify/, /streamline-hosting/, /vacation-rental-channel-manager/, /faqs/,
  /comparisons/..., get.lodgify.com/channel-manager). Only the blog subdomain opened directly. All pricing
  and most feature-category claims for Lodgify in this doc are therefore secondhand (WebSearch synthesis of
  third-party reviews), cross-checked against 2+ independent sources where possible and flagged inline
  where sources disagreed.
- **Reconciling Hospitable's two conflicting pricing sources** (JS-rendered `hospitable.com/pricing` vs.
  `help.hospitable.com`) — I picked the help-center article as authoritative per the same call the
  companion brief made, but I could not find a third source to definitively settle the Host-tier
  smart-device/direct-booking-availability contradiction between the two pages.
- **Uplisting's exact channel count** — no total-channel-count figure found on Uplisting's own pages
  (unlike Hostfully's explicit "60+" and Smoobu's implied ~80-100+); only the three named core OTAs
  (Airbnb, Vrbo, Booking.com) were confirmed.
- **Smoobu's full integration marketplace** — I did not locate or open a single integrations-directory page
  analogous to Hospitable's or Uplisting's; only two named partners (Chekin, Revyoos) were confirmed,
  which likely understates Smoobu's real integration count.
- **Hostfully's "120+" vs "150+" integrations discrepancy** — both figures are first-party (from two
  different Hostfully pages) and I could not find a page reconciling them.
- **Uplisting's USD vs GBP pricing discrepancy** — could not determine whether the WebSearch-synthesized
  "$100/mo + $20/property, Pro/Enterprise" figures represent a stale/older pricing page, a US-specific
  variant, or an aggregator error; the directly-fetched `uplisting.io/pricing` page (GBP, Independent
  Host/Portfolio Manager/Premier) is treated as current and authoritative.
- **Hostfully's PMS pricing history** — could not confirm whether the secondhand "Starter $49/Pro $129/
  Premium $219/Gold $499" figures are a genuinely outdated pricing scheme or a still-live alternate plan
  set; flagged as likely-stale given the directly-fetched current page uses a different (per-property +
  platform-fee) structure entirely.
- **Exact mechanism for Hostfully's "automatic damage protection"** claim — found the qualitative marketing
  line but no fee structure, coverage cap, or provider name (unlike Hospitable's dollar-figured $5M
  claim or Lodgify's named Truvi/Safely partners).
