# Feature Catalogue: Hostaway, Guesty, OwnerRez — Exhaustive Pass

**Date:** 2026-07-12
**Mode:** D (domain research for a build) — Researcher dispatch
**Builds on:** `~/Claude/loop/research/competitive-landscape-business-model-2026-07-12.md` (pricing +
partial ~10-feature matrix, already done — NOT repeated here except where a gating/pricing fact is new).
**Purpose:** breadth-first inventory of everything Hostaway, Guesty, and OwnerRez advertise, so Cockpit's
planning knows the full "table stakes" surface, not just the top-10 features already matrixed.

## Honesty-bar access notes (read first)

- **No 403s this pass.** Every vendor `/features/...` URL I attempted to open directly via WebFetch
  succeeded (unlike the prior brief's pricing-page pass, which hit several 403s). Direct-WebFetch pages,
  listed below, are marked **[opened directly]** and every claim from them is a quote from that fetch.
- **WebSearch-synthesized vendor content.** For many sub-feature pages I did not call WebFetch on every
  single URL (there are dozens per vendor); instead I used WebSearch queries scoped to the vendor's own
  domain and to specific named features, and WebSearch returned a synthesis built from opening the
  vendor's own page(s) in the search index. These are marked **[WebSearch synthesis of vendor's own
  page(s), not independently opened by me]** — first-party content (the vendor's own site), but I did not
  personally render the page, so treat these as slightly lower-confidence than the "opened directly" set.
  I did not need G2/Capterra as a fallback because no vendor page 403'd; I did not independently open
  G2/Capterra pages this pass.
- **Third-party corroboration used sparingly**, only where noted (e.g., a rakidzich.com tier comparison
  for Guesty Lite vs. Pro vs. Enterprise, since Guesty's own pricing page is quote-gated above Lite).
- **Pages opened directly, this pass:**
  - Hostaway: `hostaway.com/features/`, `/features/channel-manager/`, `/features/operations/`,
    `/features/property-management-system/`, `/features/services/`, `/features/ai-cohost/`,
    `/features/marketing/`, `/marketplace/`
  - Guesty: `guesty.com/features/`, `/features/reporting-tools/`, `/features/automation-tools/`,
    `/features/guest-app/`, `/features/guesty-ultimate/`
  - OwnerRez: `ownerrez.com/features`, `/property-management`, `/integrations`
- **Not found / could not verify** (see also the closing section): Hostaway's exact total OTA-channel
  count (search only surfaced "major OTAs plus dozens of secondary OTAs," no number); OwnerRez's exact
  annual-discount percentage on Property Management add-on pricing beyond the base rate; whether
  Hostaway's AI CoHost is tier-gated (the page itself doesn't disclose gating — flagged inline).

---

## 1. Channel management & distribution

### Hostaway
- OTAs named: **Airbnb, Vrbo, Booking.com, Expedia, Google (Vacation Rentals), Marriott Homes & Villas**,
  plus "dozens of secondary/regional OTAs" via the marketplace `[opened directly, features/channel-manager/
  + marketplace/]`. Exact total channel count not published anywhere I could find — **not found**.
- Two-way, near-real-time sync: *"Instantly reflect new bookings, cancellations, price changes, and
  availability across connected channels"*; *"Direct APIs with major booking platforms"*; claims
  **"Near-zero latency"** `[opened directly, /features/channel-manager/]`.
- Rate/availability/content push: **"Customizable Listings"** lets users **"Control pricing and content
  per OTA"** `[opened directly]`.
- Partner status: claims **"premiere/preferred partner status"** with major platforms `[opened directly]`.
- Positioned explicitly against double-booking: *"Make double bookings a thing of the past"*
  `[opened directly]`.
- Gating: channel manager itself is core/all-tier; the **portfolio-size tiering (2-14 / 15-49 / 50-199+)**
  gates depth of *other* features (reporting, task workflows, permissions, onboarding), not channel access
  itself `[opened directly, /features/]`.

### Guesty
- **60+ booking platforms** on Lite/base; Pro/Enterprise extend to **"over 100 listing channels"** and
  sync richer content (descriptions, images, amenities) `[WebSearch synthesis of guesty.com/features/
  channel-manager/ + rakidzich.com Lite-vs-Pro comparison — the "60+" vs "100+" split is a **tier-gated**
  fact, flag it]`.
- Named OTAs/marketplaces: **Airbnb, Vrbo, Booking.com, Expedia, Agoda, TripAdvisor, HomeAway, Homes &
  Villas by Marriott**, "luxury platforms" `[WebSearch synthesis of vendor page]`.
- Real-time sync: *"When a guest books on any channel, all others update instantly"* `[WebSearch
  synthesis]`.
- Per-channel markup/discount control: *"apply markups, discounts, and custom promotions per platform"*
  `[WebSearch synthesis]`.
- Listing creation/onboarding: *"listings go live on new platforms automatically with no manual
  re-entry"* `[WebSearch synthesis]`.
- **Gating confirmed directly from the features page** `[opened directly, /features/]`: base "Channel
  Manager" is listed under "Distribution and Operations" as a core feature; **Premium Distribution** (free
  access to premium channels) is explicitly bundled only inside the **Guesty Ultimate** add-on package
  `[opened directly, /features/guesty-ultimate/]`.

### OwnerRez
- Direct API integrations named: **Airbnb, Vrbo, Booking.com, Google Vacation Rentals** `[WebSearch
  synthesis of ownerrez.com support docs]`; the **integrations page itself, opened directly**, lists a
  **"Channel Integrations"** category with **28 named partners** `[opened directly, /integrations]`.
- "Update Once, Publish Everywhere" — rates, availability, house rules, photos, description pushed from
  one place `[opened directly, /features]`.
- OwnerRez is a **Vrbo API "Preferred Partner"** and *piloted, then opened to all, a program letting
  individual homeowners use the Vrbo API connection directly* `[WebSearch synthesis of vendor content]` —
  notable because Vrbo/Airbnb API access is normally reserved for larger PMS accounts; this is a real
  differentiator OwnerRez advertises for small/single-property hosts.
- Booking.com integration was explicitly **expanded** as of a March-2026 product update (paired with the
  new Quality Center launch) `[WebSearch synthesis of ownerrez.com/blog product-update post]`.
- No tiering on channel management itself — it's included in the base $88/mo/property plan (per the prior
  brief's pricing table); premium *feature modules* are what's gated, not channel connections.

**Cross-vendor note:** none of the three publish an authoritative, single, current total-channel count
that I could independently verify — Guesty's "60+" (Lite) / "100+" (Pro) split is the most concrete,
directly tier-differentiated number found.

---

## 2. Unified inbox / messaging

### Hostaway
- Channels unified: **email, SMS, WhatsApp, and OTA messages (Airbnb, Vrbo, Booking.com)** in *"one inbox
  for every conversation"* `[opened directly, /features/property-management-system/]`.
- Automation claims **"handling up to 90% of routine replies"** `[opened directly, /features/]`.
- Reusable templates for check-in, house rules, FAQs `[opened directly]`.
- **AI Replies** — automated response *generation* (distinct line item from "Automated Messaging" workflow
  triggers) `[opened directly, /features/]`.
- **AI CoHost** (see §12) can also draft/adjust messaging as part of its broader agent capability.
- Gating: base unified inbox + templates + AI replies appear in the **2-14 listing** tier tile; nothing on
  the page suggests messaging itself is gated higher, only reporting/permissions are `[opened directly]`.

### Guesty
- Channels unified: **Airbnb, Vrbo, Booking.com, email, SMS, and WhatsApp** — WhatsApp is a named,
  specifically-launched capability (*"Guesty's Unified Inbox now officially supports WhatsApp messages"*),
  enabled automatically once a guest phone number is on the reservation `[WebSearch synthesis of
  guesty.com/features/unified-inbox/ + guesty.com/blog/whatsapp-integration/]`.
- Color-coded status indicators, filterable by urgency/reservation status/check-in date `[WebSearch
  synthesis]`.
- **ReplyAI Autopilot** — a 2025/2026-launched AI agent that *"automates guest communication, identifies
  issues in real time, and generates ready-to-assign tasks"*, with adjustable tone/length `[WebSearch
  synthesis, shorttermrentalz.com + guesty.com blog coverage]`.
- Automated trigger-based SMS/WhatsApp sends (e.g. "24 hours before check-in") `[WebSearch synthesis]`.
- Mobile app fully supports the inbox including WhatsApp `[WebSearch synthesis]`.
- Gating: multi-user access to the inbox (i.e., multiple team members responding) is **Pro/Enterprise
  only** — Lite is single-operator `[WebSearch synthesis of rakidzich.com Lite-vs-Pro comparison,
  third-party but corroborates the vendor's own Lite-tier FAQ language about "certain features continue
  to be available exclusively for Pro users, including multiple users..."]`.

### OwnerRez
- Channels unified: **email, SMS, Airbnb, Vrbo** (Booking.com messaging also listed as a distinct
  capability) via the "Unified Inbox," "activity timeline," and "system alerts" `[opened directly,
  /features + WebSearch synthesis of ownerrez.com/support/articles/messaging-overview]`.
- Templates + Triggers: *"a large array of built-in system message templates for routine situations, like
  payment receipts, payment requests, quotes, date changes"* `[WebSearch synthesis of vendor docs]`.
- Channel-native message delivery: templates can be sent *"on the platform"* (i.e., through the Airbnb/
  Vrbo native messaging thread, not just email) `[WebSearch synthesis]`.
- **Rezzy AI** (launched free to all in Feb, billed starting March per a product-update post) — an AI
  messaging assistant that *"automatically handles common questions and requests instantly"* (WiFi,
  check-in/out, parking, amenities), performs **sentiment analysis**, and **auto-generates trackable
  tasks** from guest messages by reading *"real booking data, property info, policies, and guest history"*
  `[WebSearch synthesis of ownerrez.com/blog + support articles]`. Rezzy is listed among OwnerRez's
  **premium features** (billed like the other add-ons) `[opened directly, /features — "Premium Features"
  list includes Rezzy AI]`.
- **Known gap, reviewer-sourced (secondhand):** *"reviewers appreciate the centralized communication...
  though some wish for a unified mailbox and improved VRBO messaging"* `[WebSearch synthesis, cites a
  third-party review roundup — flagged as a review-site claim, not a vendor admission]`.
- SMS specifically is a metered premium add-on: **500 free outbound segments/mo, then $0.015/segment**
  `[opened directly for the "premium feature" framing on /features + WebSearch synthesis of the exact
  segment/price figures from ownerrez.com/support/articles/sms-segments-calculator]`.

---

## 3. Calendar & reservation management

### Hostaway
- **Multi-calendar** unifying all channels into one view; *"Combined multi-calendar across all
  channels"*, *"Unified calendar view for the full picture"* `[opened directly, /features/
  property-management-system/]`.
- Centralized reservation management tied to booking channels across a stated **2 to 200+ listing**
  portfolio range `[opened directly]`.
- Double-booking prevention is the calendar's core marketed value prop (see §1).
- No explicit drag-drop or owner-block/gap-night language surfaced on the pages I opened — **not
  independently confirmed**; third-party comparison sites imply it (standard PMS calendar UI) but I did
  not find a Hostaway first-party quote naming "drag and drop" or "owner block" specifically. Flagging as
  **not found on a page I opened**, though functionally near-certain to exist.

### Guesty
- **Multi-Calendar** feature line: *"Manage reservations from multiple channels within a single
  calendar"* `[opened directly, /features/]`.
- Mobile app calendar parity: *"View and manage reservations directly from the Multi-Calendar,"* create
  new reservations, and **"Create manual blocks"** (i.e., owner/maintenance blocks) directly from the
  mobile app `[WebSearch synthesis of guesty.com/features/property-management-mobile-app/ +
  help.guesty.com mobile-app-overview article]` — this is the clearest first-party confirmation of
  owner-block functionality across the three vendors.
- Owner reservations are visually distinguished on the calendar (*"marked in dark blue with an icon"*)
  and **cannot be edited by other users**, which is the closest first-party evidence of gap-night /
  owner-stay handling `[WebSearch synthesis of Guesty Help Center owners-portal articles]`.

### OwnerRez
- No dedicated calendar-only feature page found; calendar functionality is folded into the Channel
  Management / Property Management module description (*"centralizes booking calendars across listing
  sites, keeping availability up-to-date"*) `[WebSearch synthesis]`.
- The mobile PWA explicitly supports *"approving or adjusting reservations, or assigning cleaning or
  maintenance tasks"* on the go, but **bulk rate updates** require desktop `[WebSearch synthesis of
  ownerrez.com support/forum content on mobile]` — i.e., calendar/reservation editing works on mobile,
  bulk pricing operations do not.
- Owner-stay / block handling: implied by the Property Management module's owner-portal access, but I did
  not find an OwnerRez-specific "owner block" or "gap night" quote — **not found**, flagged.

---

## 4. Pricing (dynamic pricing, rules, fees, taxes)

### Hostaway
- **No native dynamic-pricing engine** confirmed — the vendor page frames "Dynamic Pricing" as a feature
  category but the substance is the marketplace integration layer (PriceLabs, Wheelhouse, Beyond, DPGO
  listed under "Revenue Management" in the marketplace) `[opened directly, /marketplace/]`, combined with
  a claimed outcome stat: **"earning 25.1% more revenue per listing on average"** `[opened directly,
  /features/]` — this stat's methodology is not disclosed on the page; treat as a vendor-marketing claim,
  not an independently verified figure.
- Taxes/fees: not detailed on any page I opened or found via search — **not found**.

### Guesty
- **Guesty PriceOptimizer™** — native/embedded (not just an integration) AI dynamic-pricing tool, sold as
  a paid **add-on** both standalone and inside the Guesty Ultimate bundle: *"Dynamic AI pricing that
  works"* / *"uses real-time data from your local market and competition to adjust rates 24/7"* `[opened
  directly for the add-on/bundle framing, /features/guesty-ultimate/; WebSearch synthesis for the
  mechanism description]`.
- **AI Agent for Revenue Management** (2025/2026 launch) — described as unifying *"pricing, policies,
  availability, and content performance into a single, actionable revenue management layer"* — the first
  of a stated multi-agent AI roadmap `[WebSearch synthesis of prnewswire.com press release +
  shorttermrentalz.com coverage]`.
- Fees/taxes: GST-compliant invoicing mentioned in the currency-handling context `[WebSearch synthesis]`;
  no dedicated tax-rule-engine page found — **not found** beyond that one mention.

### OwnerRez
- **No native dynamic-pricing engine** — integrates with **PriceLabs and Beyond** `[WebSearch synthesis of
  vendor integrations content, corroborated by the /integrations page's own "Dynamic Pricing" category
  listing 8 partners, opened directly]`.
- Taxes: a distinct **"Taxes"** line item appears under the Accounting category on the features page
  `[opened directly, /features]`, and a **March-2026 product update added "Statement Taxes for Handling
  GST/HST"** `[WebSearch synthesis of ownerrez.com/blog product-update post]` — i.e., tax handling is a
  real, recently-improved feature, not just a line-item label.
- Length-of-stay / rules: not explicitly detailed on the pages opened — **not found** as a named feature,
  though "compare rates by channel" is listed under Channel Management `[opened directly]`.

---

## 5. Guest experience (guidebooks, guest app/portal, upsells, check-in, ID/screening, reviews)

### Hostaway
- **Guest Portal**: self-serve view of outstanding balance, payment, and **upsell purchases** (early
  check-in, late check-out, other add-ons) `[WebSearch synthesis of Hostaway support + glossary pages]`.
- **Digital Guidebook / Welcome Book**: Hostaway's own glossary distinguishes a "digital guidebook"
  (property + destination info) from the broader "guest portal" (self-service hub including booking
  management, access codes, communication, upsells, *and* guidebook content) and states *"Hostaway's guest
  portal combines both functions into a single guest-facing interface"* `[WebSearch synthesis of
  hostaway.com/glossary pages]` — native guidebook capability exists, but is also commonly delivered via
  marketplace partners (Touch Stay, YourWelcome, Tourmie) for hosts who want a more polished result
  `[opened directly, /marketplace/, "Guest Experience" category]`.
- **Online Check-in Form**: collects guest name, sex, email, phone, DOB, nationality, **ID number, ID
  photo, and selfie** for adults 18+ `[WebSearch synthesis of support.hostaway.com]`.
- **ID/guest screening — important nuance, confirmed via direct search of Hostaway's own content**:
  *"Hostaway does not check the ID of the guest to make sure that it is not a fake"* — i.e., Hostaway
  **collects** ID data natively but does **not perform verification/authentication** natively; actual
  fraud/ID screening requires a marketplace partner (Autohost, Truvi, ChargeAutomation, SuiteOp/
  SuiteVerify) `[WebSearch synthesis, directly quoting Hostaway's own blog content on this exact
  question]`. This is a genuine, named gap worth flagging for Cockpit's competitive framing.
- **Automated Reviews**: review solicitation/collection listed as a standing feature `[opened directly,
  /features/]`.
- **Smart lock integration**: 100+ locks via marketplace, two-way API sync confirmed for RemoteLock,
  auto-generated unique codes tied to reservation dates, codes expire at checkout, full access audit trail
  `[opened directly, /marketplace/ + WebSearch synthesis of support docs]`.

### Guesty
- **Guest App**: customizable check-in forms *("collect credit card details, selfies, and IDs")*,
  e-signature rental agreements with dynamic variables, **branded guidebooks and upsell opportunities**
  (local services, recommendations, late check-out), **auto-translation in Spanish, German, French,
  Portuguese, and more** `[opened directly, /features/guest-app/]`.
- **GuestVerify™** — dedicated guest-screening/ID-verification product, marked as a paid **add-on**:
  *"Screen guests and collect and verify IDs upon booking"* `[opened directly, /features/]` — this is a
  more explicit native verification claim than Hostaway's (which admits it doesn't verify), though it's
  gated as an add-on rather than included.
- **Damage protection** — separate paid add-on line item, distinct from GuestVerify `[opened directly,
  /features/]`.
- **Automated review collection** *"that reaches guests at peak satisfaction"* `[WebSearch synthesis of
  automation-tools page]`.
- **Smart lock**: sold as the **Guesty LocksManager™ add-on**, *"remotely manage all your smart locks from
  a single dashboard"* `[opened directly, /features/ + /features/guesty-ultimate/]`.
- **Guesty Liability Coverage** (add-on, US-only): up to **$1M per-reservation** coverage, pay-per-
  occupied-night billing, automatic enrollment once opted in `[WebSearch synthesis of guesty.com/features/
  liability-coverage/]` — this is a materially different, insurance-like feature not found (as a native
  offering) on either Hostaway's or OwnerRez's pages.

### OwnerRez
- No dedicated native "guest app" — guest-facing experience is delivered through the website/booking flow
  and channel messaging rather than a standalone branded app (**absence noted, not found** as a named
  product on the pages I checked).
- **Guest screening / damage protection**: via **Truvi integration** — *"automatically screening every
  booking against Truvi's watchlist of known problem guests, with email and phone verification to flag
  disposable or fake contact details"* `[WebSearch synthesis of vendor + Truvi content]` — i.e., like
  Hostaway, OwnerRez's screening is a third-party integration, not a built product (unlike Guesty's
  GuestVerify, which Guesty sells as its own add-on).
- **Quality Center** (new, launched ~March 2026): a consolidated dashboard with tabs for **Overview,
  Reviews, Sentiment (if Rezzy AI enabled), and Analyzer** — centralizes guest/host review management and
  **"Smart Reviews"** (formerly "Automatic 5-Star Host Reviews," i.e. automated review-request/posting
  logic) `[WebSearch synthesis of ownerrez.com support articles + blog product-update post]`.
- **Smart-lock/check-in integrations**: **RemoteLock, i-checkin (300+ locks across 42 brands + intercom
  systems), Hubitat, Schlage ($4/lock/mo), Jervis Systems ($5/device/mo), igloohome, Brivo, eRentalLock,
  Kaba/Oracode, Lynx, PointCentral** `[WebSearch synthesis of ownerrez.com support docs, with the pricing
  figures directly quoted from those pages]` — notably the **most granular per-device pricing disclosure**
  of the three vendors for this category.

---

## 6. Operations (cleaning/task mgmt, team roles, checklists, mobile ops, damage/deposit)

### Hostaway
- **Task Management**: *"Automatically create tasks based on the reservations. Our automated tasks change
  if the reservation changes"* `[opened directly, /features/operations/]`.
- **Checklists**: tasks can require sub-task checklists via pre-defined **checklist templates**; cleaners
  can upload 1-2 photos before/after `[WebSearch synthesis of support.hostaway.com Tasks articles]`.
- **Mobile app**: iOS + Android, described on-page as *"The highest-rated mobile app in the industry"*
  `[opened directly, /features/services/]`; task assignment, auto-calculated clean duration based on
  property size + buffer time before next check-in, automatic reassignment to backup cleaner if the
  primary is unavailable `[WebSearch synthesis of support docs + Hostaway blog]`.
- **Team roles/permissions**: named example roles — *administrator, property manager, reservations agent,
  cleaning coordinator, owner (read-only), accountant* — with per-section **View/Modify/Create/Delete**
  granularity (Listing, Reservation, Owner Stays, Calendar, Booking Engine, Financial Reporting, etc.) and
  **User Groups** for bulk role assignment `[WebSearch synthesis of support.hostaway.com User Management
  articles]`.
- **Contract signature automation**: *"Automate your rental contracts with a few clicks"* `[opened
  directly, /features/operations/]`.
- **Damage deposits**: handled via **Automated Payments**, *"Charge the right amount on time, every time,
  by default, including damage deposits"* `[opened directly, /features/operations/]` — this is a direct,
  native (not third-party) damage-deposit claim, more explicit than what I found for Guesty or OwnerRez in
  this category.
- Gating: task workflows + user management/permissions are explicitly called out as part of the
  **50-199+ listing tier**, not the entry tier `[opened directly, /features/]`.

### Guesty
- **Task Management** (base feature, not add-on) — *"Organize cleaning, maintenance, and other tasks
  without missing a beat"* `[opened directly, /features/]`; task templates with **title, description,
  duration, priority, and a checklist of required sub-items** (e.g. "clean kitchen," "change bedding")
  `[WebSearch synthesis of guesty.com/features/tasks-management/ + Help Center articles]`.
- **Automated turnover workflows**: task auto-creation tied to reservation lifecycle triggers (e.g. "at
  check-out," "2 hours before check-in") `[WebSearch synthesis]`.
- **Per-property-type templates**: *"your 5-bedroom lakehouse gets a different checklist than your
  1-bedroom condo"* `[WebSearch synthesis]`.
- **Mobile App**: listed as a base/core feature line (not marked add-on) `[opened directly, /features/]`;
  supports Multi-Calendar view/edit, guest-detail updates, new-reservation creation, payment management,
  **manual blocks**, invoice sharing, and full WhatsApp/SMS inbox `[WebSearch synthesis of Guesty mobile
  app docs]`.
- **Team roles/permissions**: per-user role assignment with a live **"permissions summary"** preview, plus
  **per-listing access control** (a user can be scoped to specific listings only) `[WebSearch synthesis of
  Guesty Help Center user-management articles]`. **Multi-user access itself is Pro/Enterprise-gated** —
  Lite is single-operator (see §2).
- **Damage protection**: sold as its own paid add-on line (distinct from GuestVerify), *"Guesty Damage
  Protection™"* `[opened directly, /features/]` (name confirmed on the pricing page per the prior brief
  too).
- **Enterprise Management Hub** (add-on/Enterprise-tier feature): built for companies managing
  **"franchises and multiple sub-accounts from a single dashboard"** — i.e., multi-brand/multi-entity
  portfolio management `[WebSearch synthesis of guesty.com/features/enterprise-management-hub/]`.
- **Guesty Card**: a company-spend/expense-control product — virtual + physical cards, per-card spending
  limits/categories, real-time expense tracking, and **credit-line approval based on Guesty payment
  history** `[WebSearch synthesis of guesty.com/features/guesty-card/]` — this is a genuinely distinct
  operational-finance feature not found on either other vendor's page.

### OwnerRez
- **Property Management module** (premium add-on): user-portal access for **owners, cleaners, maintenance
  staff, and vacation rental managers**, each with a **separate login** for secure, scoped access
  `[opened directly, /property-management]`.
- **Expense tracking**: *"Record expenses for items you paid for that the owner will reimburse. You can
  attach files"* `[opened directly, /property-management]`.
- Mobile (PWA, not native app — see §11) supports task assignment (*"assigning cleaning or maintenance
  tasks"*) on the go `[WebSearch synthesis]`.
- **Housekeeping integrations** (not a native task engine): the /integrations page lists an **11-partner
  "Housekeeping Services"** category `[opened directly, /integrations]` — i.e., OwnerRez's cleaning/task
  workflow leans more on third-party tools (e.g. Turno, Breezeway-style partners) than a fully native
  checklist/task system, in contrast to Hostaway and Guesty which both built native checklist/task
  features directly into their dashboards.
- Damage deposits: handled under **"Security Deposits"** on the Accounting feature list `[opened directly,
  /features]`; damage *screening* is via the Truvi integration (see §5), not a native OwnerRez product.

---

## 7. Direct booking (website builder, booking engine, branding, marketing/SEO)

### Hostaway
- **Booking Website** (Standard + Pro plans): *"Launch a stunning, conversion-optimized website with
  expert vacation rental templates, no code needed"* `[opened directly, /features/marketing/]`.
- **AI-powered SEO + built-in blog** *"to rank on Google and drive organic traffic"* `[opened directly]`.
- **Marketing suite**: email campaigns, pop-ups, lead capture, promo codes `[opened directly]`.
- **Built-in booking engine**: *"real-time Hostaway sync, instant booking, and secure payments"* `[opened
  directly]`.
- Mobile-friendly, SEO-optimized, **Google Vacation Rentals-integrated** builder `[WebSearch synthesis of
  vendor content]`.
- Pricing model for this feature specifically: *"website builder free of charge and only pay a nominal
  processing fee for each direct reservation"* `[WebSearch synthesis]` — i.e., the builder itself isn't a
  flat add-on fee, it's transaction-fee-monetized, similar in structure to Hospitable's model noted in the
  prior brief.
- Owner Portal embedded in the same builder flow so owners can *"manage and optimize their direct
  bookings"* `[WebSearch synthesis]`.

### Guesty
- **Guesty Websites**: *"Craft stunning booking sites that convert visitors into guests"*, with **AI-
  powered tools that generate keyword-rich titles, meta descriptions, and image alt text optimized for
  hospitality search terms"* `[opened directly, /features/ + WebSearch synthesis of guesty-websites page
  for the AI-SEO detail]` — this is a more explicitly AI-driven SEO claim than either other vendor makes.
- Bundled free inside **Guesty Ultimate**: *"Easy website builder helps your brand shine with customizable
  templates designed for hospitality"* `[opened directly, /features/guesty-ultimate/]`.
- Tier note: per the Lite-vs-Pro comparison, *"The Lite booking site is functional, the Pro site is closer
  to production-grade"* `[WebSearch synthesis of rakidzich.com comparison, third-party but consistent with
  Guesty's own Ultimate-bundle upsell framing]`.

### OwnerRez
- **Two distinct builder paths**, both confirmed via support docs:
  1. **Hosted Website Builder** — *"built for speed and reliability rather than elaborate design,"*
     templates are comparatively limited on visual customization `[WebSearch synthesis of ownerrez.com
     support content]`.
  2. **WordPress Plugin** — native, **in-house-built by OwnerRez engineers**, requires WordPress ≥5.4 and
     PHP ≥7.4 (tested to 8.0), combined with **Widgets** to build a fully custom site `[WebSearch
     synthesis of ownerrez.com/support/articles/wordpress-plugin-overview]`.
- Both Hosted Websites and the WordPress Plugin are listed among OwnerRez's **premium (paid add-on)
  features**, not included in the base plan `[opened directly, /features]`.
- No AI-SEO claim found for OwnerRez's website tooling — **not found** (in contrast to both Hostaway's and
  Guesty's explicit AI-SEO marketing language).

---

## 8. Payments & financials (processing, owner statements, trust accounting, QuickBooks, expenses)

### Hostaway
- **Payment processing**: *"Reliable payment capture,"* explicitly **PCI compliant** `[opened directly,
  /features/operations/]`.
- **Guest invoicing**: automated, accurate invoices `[opened directly]`.
- **Owner statements**: *"Automated owner statements and payouts"*; financial reporting filterable by
  property/owner/channel; claims to **"save up to 90% of the time spent on end-of-month reporting"**
  `[opened directly, /features/property-management-system/]`.
- **QuickBooks Online integration — important nuance**: it pushes **reservation-level data (invoices)**
  into QuickBooks, but *"the integration only supports pushing data from reservations and does not
  support generating owner statements directly"* — full owner-statement generation via QuickBooks requires
  a third-party layer like **VRPlatform** on top of the native integration `[WebSearch synthesis, directly
  quoting Hostaway's own support/FAQ content on this exact limitation]`. This is a concrete, named gap.
- No native trust-accounting claim found — **not found** as a labeled feature (contrast with Guesty, which
  explicitly names trust accounting).
- Payment gating: Payments listed as a base feature line on `/features/`, not called out as tier-gated.

### Guesty
- **Trust Accounting** — explicitly named, paid **add-on**: *"Automated compliance tools for complex
  hospitality accounting,"* stated to be **compliant with North Carolina and Queensland trust-accounting
  regulations** specifically `[opened directly for the add-on framing, /features/; WebSearch synthesis for
  the jurisdiction-compliance detail]` — the most explicit, jurisdiction-specific trust-accounting claim
  found among the three.
- **Guesty Accounting** (bundled in Guesty Ultimate): *"eliminate manual bank reconciliation with AI that
  reviews transactions and matches them automatically"* and auto-creates owner statements *"that reflect
  business needs"* `[opened directly, /features/guesty-ultimate/ + WebSearch synthesis]`.
- **QuickBooks integration**: via the **Guesty Connect add-on** (a separate subscribed add-on required
  before QuickBooks can be connected) `[WebSearch synthesis of Guesty Help Center articles]` — i.e.
  QuickBooks sync is gated behind its own paid connector, not bundled free.
- **Payment Solutions / GuestyPay™**: paid add-on, *"Frictionless payments designed for short-term rental
  success"* `[opened directly, /features/]`; **AI fraud detection** and **3D-secure authentication** via
  **Guesty Pay Protect** `[WebSearch synthesis]`.
- **Guesty Capital™**: named as a distinct add-on line item on the features page — a financing/capital-
  access product `[opened directly, /features/]`; not detailed further in sources I could open — flagged
  as **name-confirmed only**, mechanism **not found**.
- **Guesty Card**: expense/spend-management (see §6).
- Multi-currency: guest-facing billing supports multiple currencies, but **Guesty's own internal billing
  to the property manager is USD-only** (*"Guesty Billing only supports United States Dollars (USD)"*),
  with a bank conversion fee possibly applying `[WebSearch synthesis of Guesty Help Center currency
  articles]` — a specific, useful nuance for anyone assuming "multi-currency" is unconditional.

### OwnerRez
- **Explicitly stated: no revenue %, no booking fees, no commission** — "use your own payment processor"
  for both channel-connected and manual payments `[opened directly, /features]` (reconfirms the prior
  brief's pricing finding, now sourced from the features page itself, not just pricing).
- **Trust/escrow accounting model**, native to the Property Management module: *"follows the trust/escrow
  accounting model where it is assumed that you are collecting payments from guests as 'rents in trust' in
  a separate escrow bank account"* `[opened directly, /property-management]` — this is a directly-quoted,
  first-party trust-accounting claim (distinct from Guesty's jurisdiction-specific compliance claim, but
  functionally the same category of feature).
- **Commission calculation + monthly owner statements** generated natively from the PM module `[opened
  directly, /property-management]`.
- **QuickBooks integration**: listed as a discrete premium add-on (separate from the PM module itself)
  `[opened directly, /features — "Premium Features" list]`.
- **CRM**: *"Get the guest 'REAL' email address"* + *"Collect & Store Reviews"* listed as base-plan CRM
  features `[opened directly, /features]` — the "real email address" framing is notable: it implies
  OwnerRez surfaces the guest's actual contact info even on OTA-sourced bookings where the OTA would
  normally mask it, which is a specific, differentiated CRM/marketing capability.
- **Wide variety of reports**, exportable to **Excel and/or CSV** `[opened directly, /features]`.
- Reports/accounting integration count: **Accounting category on /integrations lists 8 named partners**
  `[opened directly, /integrations]`.

---

## 9. Analytics & reporting

### Hostaway
- KPIs named: **occupancy rate, ADR, RevPAR, booking pace, owner payouts, channel performance**
  `[WebSearch synthesis of hostaway.com/features/analytics-and-reporting/]`.
- **Occupancy Report**: nights available, nights booked, owner-stay nights, occupancy % (calculated as
  Nights Booked×100/Total Nights Available), total check-ins `[WebSearch synthesis of support.hostaway.com
  Occupancy Report article]`.
- Owner Statements summarize income, expenses, net profit per property `[WebSearch synthesis]`.
- **AI Revenue Management** listed as its own feature line (pricing optimization + revenue forecasting),
  separate from "Advanced Reporting" `[opened directly, /features/]`.
- Gating: **Advanced Reporting + owner statements/portals are explicitly a 15-49+ listing tier feature**,
  not present in the entry 2-14 tier tile `[opened directly, /features/]` — a concrete example of
  analytics itself being tier-gated, not just an add-on.

### Guesty
- KPIs/metrics: revenue by channel, occupancy trends, operational performance, task completion times,
  staff workloads, guest-communication response rates, **Airbnb listing quality scores** `[opened
  directly, /features/reporting-tools/]`.
- **Benchmarking**: *"Compare your listings to similar listings in your market across ADR, occupancy,
  booked days, and cancellation trends"* `[opened directly]` — this is the most explicit
  competitive-benchmarking claim found among the three vendors (neither Hostaway nor OwnerRez's pages made
  an equivalent market-comparison claim).
- **Custom/owner reports**: report library, share-by-link, **recurring delivery schedules**, granular
  drill-down (e.g. "last month's cleaning costs or specific guest details") `[opened directly]`.
- **Guesty Copilot** (AI): answers business questions "in everyday language" from a centralized dashboard
  `[opened directly]`.
- **Advanced Analytics** is explicitly bundled as part of **Guesty Ultimate** and is one of the
  Pro/Enterprise-exclusive features per the Lite comparison `[opened directly, /features/guesty-ultimate/;
  WebSearch synthesis for the Lite-exclusion detail]`.

### OwnerRez
- No dedicated "analytics/reporting" feature page found distinct from the general Reports line; the
  **Quality Center's "Analyzer" tab** (new, 2026) is the closest thing to a KPI/insight dashboard
  identified `[WebSearch synthesis of ownerrez.com support content]` — specifics of what "Analyzer"
  measures were **not found** in the sources I could open; flag as name-confirmed only.
- **"Wide variety of reports," exportable to Excel/CSV** `[opened directly, /features]` — but no named KPI
  list (ADR, RevPAR, occupancy %, etc.) surfaced the way it did for Hostaway and Guesty. **Not found**:
  whether OwnerRez computes RevPAR/ADR natively or leaves that to the exported-data user.
- **Owner Dashboard revenue/payout filters** were added as part of the March-2026 product update alongside
  Quality Center `[WebSearch synthesis of ownerrez.com/blog product-update post]`.

**Cross-vendor note:** analytics/reporting is the category with the clearest **depth gradient** across the
three — Guesty's benchmarking + custom-report-library claims are the most feature-rich and explicit;
Hostaway names concrete KPIs but gates the advanced version to mid/large portfolios; OwnerRez's analytics
story is the thinnest of the three in what I could verify (reports exist and export cleanly, but no
named-KPI dashboard surfaced).

---

## 10. Integrations (marketplace size, smart locks/IoT, key partners, API/webhooks)

### Hostaway
- **Marketplace size**: *"the largest integrated marketplace for vacation rental tools and software,"*
  **more than 100 apps** `[opened directly, /marketplace/]`.
- Categories confirmed directly: Distribution/Booking Channels, Revenue Management (PriceLabs, Wheelhouse,
  Beyond, DPGO), Payment Processing (Stripe, Braintree, ChargeAutomation, Authorize.net), Smart Access &
  Locks (RemoteLock, Nuki, August, Yale, Schlage, ASSA ABLOY, Kwikset), Cleaning & Maintenance (Turno,
  Breezeway, Keepers, EZcare, TIDY), Guest Communication (Chekin, Autohost, Truvi, RueBaRue), Accounting &
  Financial (QuickBooks, Clearing, VRPlatform, Clyr), Guest Experience (YourWelcome, Guest Portal, Tourmie,
  Touch Stay) `[opened directly, /marketplace/]`.
- **Open API**: *"Integrate any software or build your own with Hostaway"* `[opened directly,
  /features/services/]` — page frames this for "growing property managers," implying it's a
  more-advanced-tier expectation rather than a beginner feature, though not explicitly gated.

### Guesty
- **Marketplace size**: **"200+ (and growing)"** third-party solutions `[WebSearch synthesis of Guesty
  Marketplace overview content]` — double Hostaway's stated 100+, though both are self-reported vendor
  claims, not independently counted by me.
- Categories: booking channels, yield management, payment processors, home automation, guest-experience
  tools, housekeeping/maintenance, keyless entry, noise monitors, insurance, accounting, data/analytics,
  luggage storage, legal services `[WebSearch synthesis]`.
- **API**: explicitly **tier-gated** — *"Lite has none, Pro has limited, Enterprise has full"* `[WebSearch
  synthesis of rakidzich.com Lite-vs-Pro-vs-Enterprise comparison]` — this is the most explicit API-gating
  statement found among the three (Hostaway and OwnerRez both present API access as flat/included).
- Smart locks: sold as the **Guesty LocksManager™** paid add-on (see §5/§6), not a flat marketplace
  integration the way Hostaway frames it.

### OwnerRez
- **Integrations page, opened directly**, confirms: **172 total named integration partners across 14
  categories** — Dynamic Pricing (8), Door Locks (13), Guest Communication (28), AI (9), Housekeeping
  Services (11), Insurance (5), Automation (4), Accounting (8), Business Intelligence (9), Devices (8),
  Websites (16), Other Integrations (9), Channel Integrations (28), Payment Processors (13) `[opened
  directly, /integrations]`. Page states: **"Join over 100+ companies who have integrated with
  OwnerRez."** — the page's own summary line ("100+") undercounts the actual per-category tally (172) I
  counted from its own listed partners; both numbers are first-party but I flag the discrepancy rather
  than picking one.
- **API + Webhooks**: OAuth-authenticated apps only; webhook events include `entity_insert`,
  `entity_update`, `entity_delete` (for bookings/blocks), plus newer **Quote and Inquiry webhooks** (added
  per a Dec-2024 email-blast note, i.e. a relatively recent addition) `[WebSearch synthesis of
  ownerrez.com/support/articles/api-webhooks + api-overview + the Dec-2024 email-blast archive page]`.
- Smart-lock integration count (13 named partners) is the **most granular door-lock integration list**
  found among the three, with per-device pricing disclosed for two of them (Schlage $4/lock/mo, Jervis
  Systems $5/device/mo) `[opened directly, /integrations, for the category count; WebSearch synthesis for
  the individual per-lock pricing figures]`.
- OwnerRez also has a dedicated **"AI" integrations category (9 partners)** distinct from its own native
  Rezzy AI — i.e., third-party AI tools can also plug in on top of OwnerRez `[opened directly,
  /integrations]`.

---

## 11. Owner/co-host management (portals, multi-owner, sub-accounts, white-label)

### Hostaway
- **Owner Portal**: described as a base capability across the property-management feature set, sharing
  *"curated information with role-based permissions"* while the Guest Portal is guest-facing `[WebSearch
  synthesis of Hostaway feature/glossary pages]`.
- Owner-facing statements/payouts and portal access are explicitly gated to the **15-49 listing tier and
  above** (see §9) `[opened directly, /features/]` — i.e. entry-tier (2-14 listings) Hostaway customers do
  **not** get the owner portal by the page's own tier breakdown.
- No explicit "white-label" or "sub-account" language found for Hostaway — **not found**.

### Guesty
- **Owners Portal**: supports **full ownership, co-ownership, and fractional ownership** models, each
  owner gets **individual portal access**; property managers control exactly which data/features each
  owner sees, **customizable per owner** `[WebSearch synthesis of Guesty Help Center Owners Portal
  articles]`.
- Multi-owner reservation visibility: other-owner reservations shown but **locked from editing** (dark-
  blue + icon marker) `[WebSearch synthesis]`.
- Owners Portal available as **both a web portal and a dedicated mobile app** `[WebSearch synthesis]`.
- **Enterprise Management Hub** is the clearest **sub-account / multi-entity** feature among the three —
  explicitly built for *"franchises and multiple sub-accounts from a single dashboard"* `[WebSearch
  synthesis of guesty.com/features/enterprise-management-hub/]` (see §6).
- No explicit "white-label" claim found for Guesty on the pages/searches I ran — **not found** (Guesty
  Websites supports "your brand," but that's not the same as reselling the platform under a different
  brand).

### OwnerRez
- **Property Management module**: separate logins/scoped access for **owners, cleaners, maintenance
  staff, vacation rental managers** `[opened directly, /property-management]`.
- Monthly **owner + PM statements**, commission calc, expense reimbursement tracking — all native to the
  PM module `[opened directly]`.
- No dedicated "multi-owner per property" (co-ownership/fractional) language found the way Guesty
  explicitly states it — **not found**; OwnerRez's PM module reads as one-owner-per-property-per-manager
  rather than Guesty's explicit fractional/co-ownership framing.
- No white-label or sub-account/franchise feature found — **not found**.

---

## 12. AI / newer features (2025-2026 launches)

### Hostaway
- **AI CoHost** (marked "NEW" on the features page): conversational assistant with a stated **Ask →
  Analyze → Act** workflow; reads reservations, listings, financials, reviews, calendar, and guest
  messages; can **execute** actions (rewrite listing copy, adjust distribution variables, autonomously
  assign maintenance tickets) subject to user approval `[opened directly, /features/ai-cohost/ + WebSearch
  synthesis of support.hostaway.com AI CoHost article for the access-control detail]`.
- Access control: **account owner/admin get it by default; other users need "AI CoHost with full financial
  access" granted explicitly** under Settings → Users `[WebSearch synthesis of support article]`. **Tier
  gating (does it cost extra / require a specific plan) was not disclosed on the page itself** — flagged
  as genuinely unknown, not just unfound.
- **AI Revenue Management** (pricing + forecasting) is listed as a separate AI feature line from CoHost
  `[opened directly, /features/]`.
- **AI Replies** for guest messaging (§2).

### Guesty
- The most AI-feature-dense of the three by page count: **ReplyAI Autopilot** (messaging), **AI Task
  Creation**, **AI Agent for Revenue Management** (the described "first" of a multi-agent roadmap),
  **Guesty Copilot** (natural-language analytics Q&A), **AI-powered SEO content generation** (Websites),
  **AI-powered dynamic pricing** (PriceOptimizer), **AI fraud detection / 3D-secure** (Pay Protect), and
  **automated bank-reconciliation AI** (Accounting) `[opened directly for several of these on /features/
  and /features/guesty-ultimate/; WebSearch synthesis for the press-release-sourced Revenue Management
  Agent and ReplyAI Autopilot details]`.
- Explicit **multi-agent product strategy** stated in a company press release: *"accelerates
  multi-agent AI product strategy"* `[WebSearch synthesis of prnewswire.com]` — i.e. Guesty is
  positioning AI as a portfolio of specialized agents (pricing, messaging, fraud, analytics) rather than
  one general assistant, a different architecture from Hostaway's single "CoHost" framing.

### OwnerRez
- **Rezzy AI** — the one clear native AI feature: guest messaging automation, sentiment analysis, and
  auto-task-generation from guest messages, trained on the account's own booking/property/policy data
  `[WebSearch synthesis, multiple ownerrez.com blog/support sources]`. Was **free for a promotional month
  (Feb per the blog post), then rolled into standard premium-feature billing** starting the following
  month `[WebSearch synthesis of ownerrez.com/blog/introducing-rezzy]`.
- **Quality Center's "Sentiment" tab is explicitly gated to accounts with Rezzy-AI enabled** `[WebSearch
  synthesis of ownerrez.com support content]` — i.e. one AI feature unlocks a second, non-AI-labeled
  feature's functionality, a cross-feature dependency not seen documented this explicitly for the other
  two vendors.
- OwnerRez is the only one of the three with a dedicated **third-party "AI" integrations category (9
  partners)** on its own integrations page, i.e. it explicitly invites AI point-solutions to plug in
  alongside its native Rezzy AI `[opened directly, /integrations]`.
- **Overall AI surface area is narrower than Guesty's and roughly on par with, or slightly behind,
  Hostaway's** — one flagship assistant (Rezzy) versus Guesty's stated multi-agent suite.

---

## 13. Mobile app, notifications, and other cross-cutting items

### Hostaway
- **Native iOS + Android app**, marketed as *"the highest-rated mobile app in the industry"* `[opened
  directly, /features/services/]`.
- Notification channels: *"desktop app, mobile app notifications or email"* `[opened directly]`.
- **Capterra 4.8 / G2 4.8 / Trustpilot 4.7** review-score badges displayed on the features page itself
  `[opened directly, /features/]` — self-reported, not independently verified by me this pass, but a
  first-party claim worth noting as marketing signal.

### Guesty
- **Native mobile app**, listed as a base (non-add-on) feature line, with a fairly complete feature parity
  to desktop for day-to-day ops (calendar, guest details, new reservations, payments, manual blocks,
  invoice sharing, WhatsApp/SMS inbox) `[opened directly for the base-feature-line placement, /features/;
  WebSearch synthesis for the detailed capability list]`.
- **Owners Portal also has its own dedicated mobile app**, separate from the operator mobile app
  `[WebSearch synthesis]` — i.e. Guesty ships two distinct mobile surfaces (staff-facing + owner-facing).

### OwnerRez
- **No native mobile app** — confirmed directly and unambiguously: *"OwnerRez doesn't have a native iOS or
  Android app, but it runs as a progressive web app (PWA) in your mobile browser"* — add-to-home-screen
  only, full desktop functionality not available on mobile (bulk rate updates, in-depth financial
  reporting require desktop) `[WebSearch synthesis, but directly quoting OwnerRez's own forum/support
  answer to this exact question, corroborated independently by a third-party review site (stayfi.com)
  describing the same PWA-only architecture]`. **This is the single clearest, most concrete
  feature-completeness gap found for OwnerRez across the whole catalogue** — both Hostaway and Guesty
  explicitly market native mobile apps as a feature; OwnerRez explicitly does not have one.

---

## Gating summary (what's paid-tier / add-on vs included, per vendor — consolidated)

| Vendor | Confirmed add-on / paid-tier features | Confirmed base/included (no extra gating found) |
|---|---|---|
| **Hostaway** | Owner portal + owner statements + advanced reporting (15-49+ tier); task workflows/user permissions (50-199+ tier); AI CoHost tier-gating **unknown** | Channel manager, unified inbox, AI replies, dynamic-pricing *access* (mechanism via marketplace), booking website builder (fee-per-booking model instead of subscription add-on), damage-deposit auto-charging |
| **Guesty** | PriceOptimizer, Trust Accounting, Guesty Pay, Guesty Capital, LocksManager, Advanced Websites, Advanced Analytics, GuestVerify, Damage Protection, Liability Coverage, Guesty Connect (QuickBooks), Guesty Card, Enterprise Management Hub — **all explicitly named add-ons**, several bundled at a discount in **Guesty Ultimate**; multi-user access + full API gated Pro/Enterprise vs Lite | Channel manager (60+ channels on Lite, 100+ on Pro), unified inbox incl. WhatsApp, mobile app, base task management, base CRM |
| **OwnerRez** | Property Management module, QuickBooks integration, Hosted Websites, WordPress Plugin, SMS messaging (metered past 500 segments), Rezzy AI — **all explicitly labeled "Premium Features"** on the features page itself | Channel management (Airbnb/Vrbo/Booking.com/Google), unified inbox/messaging templates, CRM (incl. "real" guest email), reporting/export, base accounting fields (Taxes, Security Deposits) — **no per-listing markup, no % of revenue, no setup fee** on any of these |

---

## Not found / could not verify — full list (per the honesty bar)

- Hostaway's exact total number of connected OTA channels (only "major OTAs + dozens of secondary" found).
- Whether Hostaway's AI CoHost carries its own price or tier gate (the feature page doesn't disclose it).
- Hostaway native drag-and-drop calendar interaction and explicit "owner block"/"gap night" terminology —
  functionally near-certain to exist but no first-party quote found naming them.
- OwnerRez's Quality Center "Analyzer" tab — name confirmed, but what it actually measures was not found.
- OwnerRez native KPI computation (ADR/RevPAR/occupancy %) as a labeled dashboard feature — only "wide
  variety of reports, exportable" was found; unclear if these specific metrics are pre-computed natively.
- Guesty Capital's actual mechanism (loan terms, eligibility) — name and category confirmed only.
- The precise reconciliation of OwnerRez's two different integration-partner counts on its own site ("100+
  companies" summary line vs. 172 counted across its own listed categories) — both first-party, not
  reconciled.
- G2/Capterra corroboration was not independently pulled this pass because no vendor `/features` page
  403'd (contrast with the prior brief's pricing-page pass, which did hit 403s and used G2/Capterra-style
  third-party sources more heavily).

---

## Notable cross-vendor differentiators worth carrying into Cockpit's competitive framing

1. **OwnerRez has no native mobile app** (PWA only) — a concrete, sourced gap against two incumbents that
   both market native apps heavily. If Cockpit ships a real mobile experience, this is a stated OwnerRez
   weakness to position against, not an assumption.
2. **Hostaway explicitly does not verify guest ID authenticity natively** (collects the data, doesn't
   verify it) — Guesty's GuestVerify add-on and OwnerRez's Truvi integration both go further, in different
   ways (Guesty sells its own verification product; OwnerRez integrates a specialized third party).
3. **Guesty is the most AI-feature-dense and the most explicitly multi-agent** in its own PR language,
   distinctly different in architecture from Hostaway's single "CoHost" and OwnerRez's single "Rezzy."
4. **Guesty is also the most aggressively add-on-monetized** — nearly every advanced capability (pricing,
   accounting, locks, websites, card, capital, liability coverage) is a separately named, separately priced
   product, with "Guesty Ultimate" existing specifically to bundle-discount them. OwnerRez's add-on list is
   shorter and its gating language ("Premium Features") is more transparent/consolidated. Hostaway's gating
   is mostly listing-count-tier-based rather than per-feature-add-on-based.
5. **OwnerRez discloses integration partner counts and even individual smart-lock device pricing
   ($4-5/device/mo) directly on its own site** — a transparency pattern consistent with its pricing-page
   behavior documented in the prior brief, and a real contrast to Hostaway's and Guesty's quote-gated /
   vaguer disclosure style for equivalent line items.
