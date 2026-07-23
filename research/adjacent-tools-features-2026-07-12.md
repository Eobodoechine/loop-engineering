# Domain brief: Adjacent/specialized tool feature catalogue (Analytics, Pricing, Ops, Bookkeeping, Guest Experience)

**Mode:** D — domain research for a build (Cockpit: read-only, email-first host-portfolio analytics/ops layer)
**Date:** 2026-07-12
**Goal:** catalogue the feature sets of specialized/adjacent STR/MTR tools (NOT full PMSs) so we know what
Cockpit can win on — features full PMSs treat as weak add-ons but that specialists nail.
**Builds on (read, not repeated in full):**
- `~/Claude/loop/research/pricelabs-extension-abandonment-2026-07-12.md` — deep dive on PriceLabs'
  abandoned Chrome extension → official OAuth integration migration; reused here rather than re-researched.
- `~/Claude/loop/research/competitive-landscape-business-model-2026-07-12.md` — pricing/positioning for
  full-PMS incumbents (Hostaway, Guesty, OwnerRez, Lodgify, Hospitable) plus partial AirDNA/KeyData/Clearing
  coverage; this brief extends the adjacent-tool categories, especially cleaning/ops and guest-experience,
  which that brief did not cover.

## Honesty-bar access notes (read before trusting any figure below)

- **Vendor pages that rendered real content via WebFetch (opened directly):** KeyData
  (`keydatadashboard.com` home + `/blog/airdna-alternatives`), Rankbreeze (`rankbreeze.com`), Wheelhouse
  (`usewheelhouse.com` + `/integrations/airbnb`), Beyond Pricing (`beyondpricing.com`), Breezeway
  (`breezeway.io` + `/breezeway-pricing`), Baselane (`baselane.com`), Clearing (`getclearing.co`),
  Bnbtally/TallyBreeze (`tallybreeze.com`, redirected from `bnbtally.com`), Duve (`duve.com`), Enso Connect
  (`ensoconnect.com`), Touch Stay (`touchstay.com`), PriceLabs (`hello.pricelabs.co`, plus the deep-dive
  brief above).
- **Vendor pages that 403'd or JS-blocked on EVERY attempt (multiple URL variants tried):** AirDNA
  (`airdna.co` home, `/vacation-rental-data/app`, `/faqs`, `/pricing`, `apidocs.airdna.co` — all 403 or
  content-blocked; `web.archive.org` is unreachable from this environment's WebFetch, so I could not use
  Wayback as a workaround this time, unlike the PriceLabs brief). G2's AirDNA features/pricing pages also
  403'd. **AirDNA's entire entry below is built from independent secondary sources** (WebSearch synthesis
  of Mashvisor, Awning, 10xbnb, learn.airdna reviews, KeyData's own comparison page) — I could not
  independently open a single AirDNA-owned page this pass. This is the weakest-verified entry in the brief;
  flagged throughout.
- **Turno's own pricing page (`turno.com/pricing/`) 403'd**; figures below come from WebSearch synthesis of
  Turno's own Help Center article snippets (`help.turno.com`) surfaced in search results, which is
  closer to first-party than a pure aggregator but was not independently opened as a full page this pass.
- **Hostfully guidebooks page returned a PNG/image render, not text** — figures below are WebSearch
  synthesis, not an opened page.
- **PadSplit/MTR-specific tool question:** re-confirmed with one fresh, differently-worded search this
  pass (see §6) — found nothing new. Full verified absence-of-tool evidence (PadSplit's own
  host-recommendations page, ColivHQ, coliving-substack commentary) already lives in
  `competitive-landscape-business-model-2026-07-12.md` §3 and is not re-opened here; cited by reference.

---

## 1. Analytics / market data

### AirDNA — `airdna.co` (all direct fetches 403'd; secondary-sourced entry, flagged)

**Core products (per independent secondary sources, internally consistent across 4+ sources):**
- **Rentalizer** — property-level revenue estimator: enter an address + beds/baths/guest-count, get
  projected annual revenue, ADR, and occupancy based on a comp set within a radius.
- **MarketMinder** — the analytics dashboard: city/submarket-level ADR, occupancy, RevPAR, supply growth,
  seasonality, top-performing properties, regulation notes, and a proprietary "market grade." Investors can
  link their own listings to build a custom comp set and see occupancy/booked-rate/lead-time against it.
- **Smart Rates** — AirDNA's own dynamic-pricing engine (nightly rate recommendations from market data,
  demand signals, competitor pricing, seasonal patterns) — explicitly requires "a compatible property
  management system (PMS) or channel manager that supports the AirDNA integration" to actually push rates;
  AirDNA itself does not push to Airbnb directly. One source states this plainly: *"Smart Rates cannot push
  pricing directly to Airbnb without a property management system."* `[secondhand — learn.10xbnb.com via
  WebSearch synthesis]`
- **Enterprise** — negotiated/custom pricing for PMs, investment funds, hospitality consultancies; API
  access, lead-gen tools, market forecasts. `[secondhand]`
- An **API** exists (`apidocs.airdna.co`) but I could not open it to describe its scope — title-only fetch.

**Positioning vs. PMS:** *"Smarter Pricing Decisions on Behalf of PMSs for the Hosts and Property Managers
They Support"* `[quote surfaced via WebSearch synthesis, not independently opened — treat as directional]`
— i.e., AirDNA explicitly frames itself as PMS-adjacent infrastructure, not a PMS competitor, consistent
with every other tool in this brief.

**Data ingestion:** market-level data is aggregated/modeled from public listing data (not user-connected
PMS feeds for the market-comp side); Rentalizer/MarketMinder let a host **link their own listing** to
compare against that market model. This is architecturally different from KeyData (below), which sources
property-level performance from **direct PMS integrations** rather than public-listing modeling — see
KeyData's own comparison page, which draws this distinction explicitly.

**Pricing:** tier names (Free/Research/Host/Advanced/Global/Enterprise) were confirmed in the companion
`competitive-landscape-business-model-2026-07-12.md` brief via AirDNA's help-center article; exact dollar
figures were not independently verified there either (flagged `[secondhand]` in that brief too) and I could
not add verification this pass — the official pricing page 403'd again today.

**Not verified this pass:** any AirDNA-owned page's exact wording on "we don't replace your PMS" (searched
directly, no exact-phrase match found); exact API scope/use-cases; current exact dollar pricing.

### KeyData — `keydatadashboard.com` (opened directly)

**Core features (own site, opened directly):**
- *"verified occupancy and revenue data"* for benchmarking — its central differentiator is **verified**
  (PMS-sourced) vs. **modeled/scraped** data.
- *"Track pacing and booking windows to spot demand shifts"* — pacing + booking-window analytics.
- **DemandIQ®** — proprietary predictive layer: *"reveals traveler intent before reservations are made"* —
  a forecasting feature beyond historical reporting.
- **40+ tracked metrics** including *"occupancy, ADR, RevPAR, pacing, and booking windows,"* refreshed
  **daily**.
- Deep filtering: *"filter results by property size, market, booking channel, or length of stay."*
- Market benchmarking: compare *"your portfolio against the market."*

**Data ingestion:** *"sources its data directly from 65+ property management systems rather than scraping
public listings"* `[keydatadashboard.com/blog/airdna-alternatives, verified, opened directly]` — direct
PMS integrations (the home page separately states 80+ integrations listed by name — 365Villas, Avantio,
Hostaway, Guesty, LiveRez, OwnerRez, Lodgify, etc. — the 65 vs. 80 discrepancy across two of KeyData's own
pages is noted, not resolved; treat as "60-80+" range). This directly avoids *"inflated ADRs, miscounted
nights, or revenue overstatements"* — KeyData's own stated critique of scraped-data competitors (implicitly
AirDNA).

**Positioning vs. PMS:** does not state "we don't replace your PMS" verbatim on the pages fetched, but
functions unambiguously as an analytics layer sitting **on top of** a host's existing PMS connection — the
entire value proposition (verified PMS-sourced data + benchmarking) presupposes the host keeps their PMS.
The prior `competitive-landscape` brief independently confirmed the explicit "does not replace your PMS"
framing plus DMO/enterprise-API customers.

**Pricing:** not published (quote/demo-gated) — confirmed in the prior brief, unchanged this pass.

### Rankbreeze — `rankbreeze.com` (opened directly), pricing via `rankbreeze.com/price/` (WebSearch synthesis)

**Core features (own site, opened directly):** this tool is narrower than AirDNA/KeyData — it is an
**Airbnb search-visibility / SEO + rules-based pricing** tool, not a portfolio financial-analytics tool:
- **Search Ranking Tracker** — *"Get insights into your true search visibility with our different rank
  trackers"* — shows where a listing ranks for a given guest-count/date-range search.
- **Rules-based pricing engine** — *"stacked rules for seasonality, day-of-week demand, and orphan days"*
  (per WebSearch synthesis of the site) plus a dynamic pricing calendar showing competitor rates.
- **Optimization Journal** — A/B-test titles/photos, track whether a change moved rank up or down.
- **Market Scanner** — neighborhood-level opportunity discovery.
- **AirReview** (Lite/Pro tiers) — review analytics.
- **Optimized Listing Service** — a paid, human-delivered copywriting/SEO relaunch add-on ($397/property
  one-time) — notably a **services**, not pure-software, revenue line few other tools in this brief have.

**Data ingestion — important, distinct mechanism:** *"RankBreeze does not access or modify Airbnb accounts
directly. Instead, the platform analyzes publicly available listing data and simulates search results to
estimate ranking positions... All search data is provided from an incognito browser, which means less
personalization is applied."* `[WebSearch synthesis; language reads as first-party but was not confirmed by
opening the specific help-center article]` — i.e., Rankbreeze's ranking data comes from **simulated public
searches**, not the host's own account/API access at all. This is a materially different (and lower legal
risk) data-acquisition pattern than a co-host or credential-based approach — worth noting for Cockpit's own
data-strategy debate (see the cross-referenced `cockpit-data-strategy...` and `cfaa-van-buren...` research).

**Pricing:** Starter ~$29/mo (≤3 listings) → Standard (≤10) → Scaling (≤30), all including both
search-optimization and pricing tools bundled (not sold separately); quarterly billing gets a 15% discount.
`[WebSearch synthesis of rankbreeze.com/price/, not independently opened as a rendered page]`

**Positioning vs. PMS:** not a PMS at all — a **listing-optimization + pricing** specialist; the fetched
homepage explicitly frames itself as complementary, targeting owners/PMs/investors who already operate on
a PMS or directly on Airbnb.

---

## 2. Dynamic pricing

### PriceLabs — `hello.pricelabs.co` (opened directly) + full mechanism history in the companion brief

**Core features (own site, opened directly):**
- **Hyper Local Pulse (HLP)** — *"our smart pricing algorithm that uses hyper local market data."*
- **Market dashboards** — trend analysis + competitive comparison.
- **Portfolio analytics** — occupancy, ADR, RevPAR tracked at portfolio level.
- **Revenue Estimator Pro** — property earning-potential analysis (also sold as a standalone metered
  add-on, $10–125/mo, per the companion brief).
- **Listing Optimizer** — Airbnb listing-content improvement (overlaps with Rankbreeze's category).
- **Minimum-stay intelligence** — automated booking-duration recommendations.
- Orphan-day pricing, occupancy-based algorithms exist per the companion brief's earlier research but were
  not re-confirmed word-for-word on the homepage fetched this pass — treat those two as carried over from
  the prior verified brief, not re-verified today.

**Price-push mechanism (the critical question) — full answer already researched in depth in
`pricelabs-extension-abandonment-2026-07-12.md`, reused here rather than re-derived:**
- **Today (current, live):** *"Syncs directly with Airbnb, Booking.com, VRBO and 160+ PMSs"*
  `[hello.pricelabs.co, verified, opened directly this pass]` — i.e., PriceLabs now has BOTH a direct,
  Airbnb-sanctioned OAuth connection ("Click 'Connect with Airbnb'... redirected to Airbnb's website to
  authorize PriceLabs to pull your properties," per the companion brief's Source 3) AND ~160 PMS
  integrations as an alternative path.
- **History (the abandoned-extension precedent, already fully researched — not re-done here):** PriceLabs
  ran a Chrome extension (2022–2024) that harvested the host's Airbnb password/session **once**, then ran
  indefinite **unattended, server-side, scheduled** price pushes against Airbnb's internal API
  (`api.airbnb.com`) from PriceLabs' own servers — a session Airbnb's own new-device-login email named
  "Ruby." It was retired 2024-05-24 in favor of the current official OAuth integration. The companion
  brief's bottom line: this was a **business/product decision correlated with technical fragility** (social
  login incompatibility, "doesn't work" support burden), not documented Airbnb enforcement — full sourcing
  and quotes in that file, not repeated here.
- **Co-host support in the current integration:** *"Co-Host Permissions: If you're a co-host, make sure
  your permissions are set to Full Access"* `[companion brief, Source 3, verified]` — confirms Airbnb's
  current partner-integration model treats co-host-granted access as a legitimate, supported basis for a
  third-party pricing tool today.

**Pricing (from companion brief, verified, opened directly):** $14.49–19.99/listing/mo base, sliding to
$5.00/listing/mo at 251+ listings; **also offers a 1%-of-integrated-platform-revenue plan** as an
alternative to the flat fee; metered analytics add-ons (Market Dashboard $9.99–39.99/mo, Revenue Estimator
Pro $10–125/mo).

### Wheelhouse — `usewheelhouse.com` (opened directly)

**Core features (own site, opened directly):**
- **Dynamic pricing** — *"Mix rule-based or data-driven strategies"* with 15+ customizable settings; claims
  a *"20.6% avg. revenue uplift for standard user adopting Wheelhouse."*
- **Performance Analytics** — segmentation + A/B comparisons.
- **Dynamic Sets** — portfolio grouping/context for applying strategies across similar units.
- **Navigator** — a geospatial market-insights tool.
- Custom report layouts.
- **API** — *"Fully-featured APIs"* for pricing recommendations and market data, positioned for
  integrating Wheelhouse's price recs into a third party's own website/booking platform/PMS.

**Price-push mechanism:** the `/integrations/airbnb` page describes a 3-step flow — *"Connect your
account" → "Build your strategies" → "Configure your calendar... we'll sync your prices to the connected
accounts"* `[usewheelhouse.com/integrations/airbnb, opened directly]` — reads as a direct, OAuth-style
account connection to Airbnb (parallel to PriceLabs' current model), but **the page does not explicitly
state whether this is a native Airbnb API partnership or routes through a PMS intermediary**, and I could
not confirm Wheelhouse's presence on Airbnb's own Preferred-Software-Partner list (the 2025 list page
403'd on direct fetch; WebSearch found no explicit Wheelhouse mention in partner announcements). Separately
confirmed via a Hospitable support doc (cited in the companion brief's WebSearch pass): when routed through
a PMS, *"Hospitable receives pricing from Wheelhouse and forwards it to all of your listings and booking
platforms"* — i.e., Wheelhouse supports **both** a direct-connect path and a PMS-intermediary path,
mirroring PriceLabs' dual-path model. **Flagged not fully verified: which path is primary/default, and
Wheelhouse's official Airbnb-partner status.**

**Pricing (2026, per WebSearch synthesis, not independently opened on Wheelhouse's own pricing page):**
Free (Insights only, no dynamic pricing) → Pro Flex (1% of revenue, $2.99/listing minimum) → Pro Flat
($19.99/listing/mo, $16.99 at 10-49 listings) → Enterprise (custom, 50+ listings). `[secondhand]`

### Beyond (Beyond Pricing) — `beyondpricing.com` (opened directly)

**Core features (own site, opened directly):**
- **Dynamic pricing** — *"Automated Pricing to Maximize Every Booking,"* AI-driven.
- **Neyoba** — an AI assistant for *"AI-Powered Answers & Faster Pricing Decisions."*
- **Owner Insights** — owner-facing performance reporting (directly overlaps with the bookkeeping category
  below — pricing tools are creeping into owner-reporting territory).
- **Listing Lens** — AI analysis of photos/reviews/descriptions (overlaps with Rankbreeze's category).
- **Signal** — a branded direct-booking site (overlaps with guest-experience/booking-engine category).
- **Tally** — payment processing for STRs (a second overlap, into bookkeeping/payments).
- **Market Intelligence** — 5 years of historical pricing/occupancy by market, per WebSearch synthesis of a
  separate query.
- **Health Score** — a proprietary per-listing metric scoring *revenue health* (not just occupancy),
  explicitly designed to surface **both** under-pricing in busy seasons and over-pricing in shoulder months
  — a genuinely distinct analytic framing vs. raw occupancy/ADR. `[per WebSearch synthesis]`
- **Orphan-day pricing** — automatically drops price on a single day stranded between two reservations to
  fill it. `[per WebSearch synthesis]`

**Price-push mechanism:** own site states *"Two-Way PMS Integrations"* and *"Dynamic Price Syncing"* but —
same gap as Wheelhouse — **does not explicitly state on the fetched page** whether Airbnb/Vrbo/Booking.com
connections are native-API or PMS-routed. A separate WebSearch pass found: *"Beyond connects with Airbnb and
sends rates, check-in/check-out requirements, and minimum stay requirements including gap fills"* and
confirms *"Beyond announces official Airbnb integration"* (same era as PriceLabs' Jan-2024 announcement, per
the companion brief's Source 9 — flagged there as secondary/directional, not independently re-verified this
pass). Beyond also publishes a **partner API** (`partners.beyondpricing.com`) for third-party integrators —
*"Accounts (connect channel accounts including PMS and Airbnb)... Authentication using OAuth2 client
credentials"* `[WebSearch synthesis of partners.beyondpricing.com, not independently opened]` — this
confirms an OAuth2-based connection model exists, consistent with the industry's post-2024 shift away from
credential-harvesting extensions.

**Pricing:** Growth (entry) → Pro (adds Search-Powered Pricing + market insights) tiers named on-site; no
dollar figures disclosed on the pages fetched; a "$50 credit" trial offer mentioned.

**Cross-vendor synthesis for §2 (relevant to whether Cockpit could ever offer pricing):** all three pricing
tools have **migrated away from ad hoc credential/extension-based Airbnb access toward an OAuth-style
"Connect your account" flow**, run either as a direct Airbnb-sanctioned partner connection or through a PMS
intermediary — the same two-path model, no exceptions found. **None of the three publicly documents a
currently-operating credential-harvesting browser extension** — PriceLabs' was retired in 2024, and no
active equivalent surfaced for Wheelhouse or Beyond in this research. This strongly implies that for Cockpit
to ever push prices (not just show them), it would need either (a) Airbnb API-partner status via the same
OAuth application process these three used, or (b) to ride on a PMS's existing channel connection — **not**
a bespoke scraping/extension approach, which the market has visibly moved away from as unsustainable.

---

## 3. Operations / cleaning

### Turno (formerly TurnoverBnB) — `turno.com` (home page opened directly; `/pricing/` 403'd, pricing via search)

**Core features (own site, opened directly):**
- **Cleaner Marketplace** — *"25,000+ STR cleaners across the United States, Canada, Europe, and beyond"*
  — hosts solicit and select **bids** from independent cleaners by location/budget.
- **Auto-Scheduling** — syncs the host's rental calendar and *"imports bookings and automatically generates
  cleaning projects associated with guest check-in and checkout dates"* — i.e., calendar-driven task
  automation, the core operational primitive of this category.
- **Photo Checklists** — thousands of pre-built checklists, customizable or built from scratch; cleaners
  submit **photo proof** per task.
- **Inventory Management** — tracks consumables (toiletries, towels, cleaning supplies) and alerts when
  running low.
- **In-App Chat** — direct host↔cleaner messaging.
- **Payments** — automatic cleaner payment on project completion.
- Claims *"save over forty hours each year"* per host.

**Data ingestion:** calendar sync (iCal-style import, "after syncing their rental calendar" — not stated as
a full PMS API integration on the pages opened, reads as calendar-feed-driven).

**Pricing (per WebSearch synthesis of Turno's own Help Center, not independently opened as a full page this
pass):** **Free** for a single property using **non-marketplace** (host's own) cleaners, regardless of
cleaner count. Paid subscription is **per-property**: $10/mo (monthly) or $8/mo (annual, billed
$96/yr/property). **Marketplace cleaner searches are always free** (no subscription needed at all if using
Marketplace exclusively), but Turno charges a **5% transaction fee** on each marketplace clean, charged to
both host and cleaner.

**Positioning vs. PMS:** not a PMS — pure task/cleaner-ops automation; explicitly designed to sit on top of
whatever calendar/PMS a host already uses (confirmed via Hostaway's own support docs in the companion
brief: Hostaway automates cleaning-task creation on checkout *via integration with Turno or Breezeway*,
i.e., PMSs treat this as an integration point, not a built-in feature).

### Breezeway — `breezeway.io` (home + `/breezeway-pricing` opened directly)

**Core features (own site, opened directly) — notably broader than Turno's cleaner-marketplace focus:**
- **Task Automation & Scheduling** — *"Automate everyday tasks"* across turnovers.
- **Work Coordination** — team assignment + real-time progress monitoring (built for **staffed/in-house**
  ops teams, not primarily a marketplace of independent cleaners like Turno).
- **Mobile Checklists** — custom, photo-proof checklists, available in **10 languages**.
- **Maintenance Workflows** — preventative-maintenance scheduling + **inspections** (a distinct workflow
  type beyond cleaning — this is Breezeway's clearest differentiator vs. Turno).
- **Inventory Tracking** — supply optimization/monitoring.
- **Guest Messaging** — AI-powered automated messaging + a *"digital welcome book"* (overlaps into the
  guest-experience category below).
- **Quality Assurance** — photo documentation + accountability.
- **Insights & Reporting** — an operations dashboard.

**Data ingestion:** *"integrates with major property management systems including Airbnb, Guesty,
Cloudbeds, Mews, Hostaway, and others"* `[breezeway.io, verified, opened directly]` — PMS-integration-driven,
consistent with the rest of this category; explicitly frames itself as *"a layer atop existing PMS
infrastructure rather than replacing it"* and runs its own **"PMS vs Breezeway"** comparison page in its own
site navigation — the most explicit "we are not a PMS" self-positioning artifact found in this entire brief.

**Pricing (own pricing page, opened directly):**
- **Freemium** — free ops-platform access for the host's first property.
- **Host Essentials** — starts at **$19/mo per unit** (minimum), includes messaging/guide/operations tools.
- **Essential Ops / Ops + Guest Experience Suite / Operations Pro / Operations + Guest Experience** — all
  **quote-gated**, no published dollar figures.
- *"Our pricing is based per property, billed monthly — with volume discounts for those with 5+
  properties."*

**Positioning vs. PMS:** the strongest, most explicit "operations layer, not a PMS" framing of any tool
researched in this brief — see the dedicated comparison page referenced above.

---

## 4. Bookkeeping / finance

### Clearing (getclearing.co) — opened directly (also covered in the companion pricing brief; extended here)

**Core features (own site, opened directly):**
- **Automated bookkeeping & reconciliation** — *"Close your books faster than ever with Clearing's
  automated categorization and allocation by property matched with booking details."*
- **Trust accounting** — separate balances **per homeowner**, commission tracking — the specific mechanic
  full PMSs (per the companion brief's feature matrix) mostly lack natively.
- **Expense management** — custom categories, automated homeowner allocation.
- **Owner statements** — generated *"in just a few clicks."*
- **Payment processing** — pay bills and homeowners via ACH from within the platform.
- **Accountant portal** — invite an accountant to review transactions / prep tax reports.
- **Owner portal** — real-time portfolio-performance visibility for homeowners themselves.

**Data ingestion:** bank feeds (named: Bank of America, Chase, Amex), payment platforms (Stripe, Airbnb),
PMS integrations (named: Hostfully, Guesty, Hostify), and QuickBooks Online sync.

**Positioning vs. PMS:** explicit — *"No, you can use Clearing even if you don't have a Property Management
Software"* `[getclearing.co, verified, opened directly]` — i.e., Clearing is designed to work **with or
without** a PMS, a distinct and stronger claim than most tools in this brief (most assume a PMS exists to
integrate with).

**Pricing (from companion brief, verified, opened directly):** Starter $25/mo (≤5 listings), Standard
from $150/mo (≤10 listings), $199 one-time setup fee (includes a dedicated specialist), Trust Accounting
add-on $2.50/unit/mo, 20% annual-contract discount.

### Bnbtally → now rebranded **TallyBreeze** — `tallybreeze.com` (opened directly; `bnbtally.com` 301-redirects here)

**Note:** the brand itself has changed since the tool was last researched under "Bnbtally" — worth flagging
explicitly, since anyone searching only "Bnbtally" will land on a redirect.

**Core features (own site, opened directly):**
- **Automated reservation accruals + reconciliation** across listings — *"Automate reservation accruals,
  reconciliation, and tax allocations—all with pristine accuracy and control."*
- **Tax allocation** by property.
- **Payout reconciliation** automation.
- **Commission and trust-account management.**
- **Per-listing revenue/tax/fee tracking.**
- **Rollback/undo** for imported entries — a granular-control feature not seen elsewhere in this brief.
- **Class-tracking categories** for financial separation by listing (a QuickBooks/Xero-native concept
  mapped onto STR bookkeeping).
- **Customizable allocation rules** — percentage splits, fixed amounts, per-night calculations.

**Data ingestion:** direct **Airbnb** listing connections + PMS integrations named: **Guesty, HostAway,
Lodgify, Hospitable, Hostfully**; syncs into **QuickBooks and Xero** as the accounting-software targets.

**Pricing (own site, opened directly):** **$32/mo** starting price, includes the first 2 listings;
additional listings raise the rate; historical bulk imports priced separately (months × listings × monthly
rate); 7-day free trial with current + previous month importable free.

**Positioning vs. PMS:** *"positions itself as an accounting layer, not a PMS replacement... connects
existing rental platforms to accounting software, enabling hosts and property managers to maintain clean
books while using any PMS — avoiding 'platform lock-in.'"* `[tallybreeze.com, verified, opened directly]`

### Baselane — `baselane.com` (opened directly) — the general-landlord (non-STR-specific) comparison point

**Core features (own site, opened directly):**
- **Banking** — unlimited property-specific sub-accounts, no maintenance fees/minimums, FDIC coverage up to
  $5M via a bank partnership (Thread Bank).
- **Bookkeeping** — AI-powered transaction tagging to entity/property/tax category.
- **Rent collection** — automated invoices/reminders for rent, deposits, late fees.
- **Tax prep** — instant generation of tax packages (ledgers, receipts, statements).
- **Payment automation** — bill pay, disbursements, overdraft prevention.

**Explicitly NOT STR-specific** — targets landlords across long-term, mid-term, and short-term rentals
alike (*"multi-property investors... short-term, mid-term, and long-term rental investors"*), unlike every
other tool in this section. Claims *"50,000+ real estate investors"* managing *"97,000 properties"* and
*"$3.1B annually."*

**Monetization (from the companion brief, not re-verified this pass):** free core product, monetized via
interchange/card-processing fees (2.99% card-payment fee) + affiliate revenue — the only tool in this
entire brief that monetizes via **money-movement fees** rather than a subscription. Relevant precedent only
if Cockpit ever adds a payments/banking layer, which is out of scope for a read-only product as currently
defined.

---

## 5. Guest experience

### Duve — `duve.com` (opened directly)

**Core features (own site, opened directly):**
- **Online check-in** — registration, ID verification, payment collection pre-arrival.
- **Guest App** — white-label, no-download mobile experience covering pre/during/post-stay info.
- **Upsells** — *"AI-driven profile-based offers,"* claims *"$180 average uplift per room per month"* — the
  single most concrete revenue-per-guest figure found across all guest-experience tools in this brief.
- **Guest Communication Hub** — unified inbox across WhatsApp, SMS, email, and OTA messaging, with AI
  automation.
- **Digital Keys** — smart-lock integration for mobile room access.
- **Room Directory** — digital amenities/menus/house-rules.
- **Digital Menus & Mobile Ordering** — in-room-service/restaurant ordering.
- **Analytics & Segmentation** — conversion-rate and guest-segment tracking dashboard.
- **Generative AI Agents** — multi-language automated guest responses.

**Data ingestion:** *"100+ integrations"* including major PMS platforms (named: Mews, Protel, Oracle,
Infor — notably **hotel-industry PMSs**, reflecting Duve's broader hospitality/hotel-adjacent customer base
beyond pure STR), payment processors (Stripe, Adyen), smart-lock systems (ASSA ABLOY, Salto).

**Positioning vs. PMS:** complementary — *"handling guest experience and revenue optimization while PMS
systems manage core reservations and operations."*

**Pricing:** not disclosed on the fetched page; a separate WebSearch pass found **$120/mo (Basic) → $150/mo
(Pro) → $200/mo (Premium) → custom Enterprise** `[secondhand, not independently opened — flagged as
directional only, and notably not stated as per-unit, which is unusual for this category]`.

### Enso Connect — `ensoconnect.com` (opened directly)

**Core features (own site, opened directly):**
- **Unified guest messaging** — *"Bring Airbnb, Booking.com, WhatsApp, SMS, email and phone into one
  inbox."*
- **EnsoAI** — two operating modes: **Copilot** (human-reviewed AI drafts) vs. **Autopilot** (fully
  autonomous AI responses) — the most explicit human-in-the-loop-vs-autonomous distinction found in this
  brief; potentially a directly reusable design pattern for Cockpit's own AI features.
- **Digital check-in** — contactless verification/onboarding.
- **Upselling** — automated offers for early check-in, late checkout, stay extensions, add-ons.
- **Boarding Pass** — a consolidated guest app (check-in, WiFi, local tips, upsells) — Enso's name for the
  same "single guest link" concept as Duve's Guest App / Touch Stay's guidebook.
- **Digital guidebooks.**
- **Guest verification/screening** — sold as an add-on, extra cost.
- **Smart-lock integration.**
- **Custom no-code workflows** triggered by guest events.
- **Analytics & CRM** — performance tracking, **sentiment analysis**, direct-booking campaign tools.

**Data ingestion:** integrates with existing PMSs (Guesty named explicitly); exact API/ingestion mechanism
not detailed on the fetched page.

**Pricing (per WebSearch synthesis, not independently opened as a rendered page):** **$9–16/listing/mo**
depending on listing count/features enabled (includes Boarding Pass, personalized upsells, Enso
Experiences, unlimited automations, CRM, EnsoAI sentiment reporting); guest verification/screening and some
EnsoAI features cost extra; **implementation fee starting at $300** for Enso-team-led setup — notable since
this is a real, disclosed onboarding-fee precedent in a category where most competitors hide pricing
entirely.

**Positioning vs. PMS:** complementary layer — *"handling guest experience and revenue optimization while
integrating with existing property management systems."* Also promotes an **"ROI Guarantee"** — subscription
cost recoverable via upsells, claimed average time-to-ROI of one month — a concrete, falsifiable value claim
worth noting as a marketing pattern (not verified independently; a vendor's own claim).

### Touch Stay — `touchstay.com` (opened directly)

**Core features (own site, opened directly):**
- **AI chatbot** — automated instant guest support.
- **Email & text messaging** — scheduled, automated, two-way.
- **Upsell widget** — *"earn more with extras like products or services."*
- **5-star review popup** — feedback/review-generation tool.
- **Data dashboard** — analytics/insights.
- **AI guidebook generator** + **AI content assistant** — rapid guide creation/customization.
- **Multimedia support** — images, virtual tours, video.
- **Brandable design** — custom logo/colors (white-label).
- **Multi-language support.**
- **Third-party embeds.**

**Data ingestion:** PMS connectors named: Airbnb, Lodgify, OwnerRez, Guesty, HostAway, Escapia; an
**"Airbnb connector"** specifically for *"import your properties with a click."*

**Positioning vs. PMS:** complementary guest-experience layer, explicitly "atop existing property
management infrastructure."

**Pricing:** genuinely conflicting figures across secondary sources — one aggregator states **~$15/mo/
property** (or ~$118/yr), another states plans **"start from $8.25/mo,"** and Touch Stay's own pricing page
is described elsewhere as requiring a custom quote/calculator rather than a flat public number. **Flagging
this spread explicitly rather than picking one** — the discrepancy is likely tier/volume-dependent, same
pattern as Hospitable's conflicting figures in the companion brief; I could not resolve it with a direct
fetch (the pricing page is a JS calculator, not static content).

### Hostfully Digital Guidebooks — standalone product (WebSearch synthesis only; direct fetch returned an
unreadable image render, not text — flagged, not independently verified this pass)

**Core features (per WebSearch synthesis):** guest communications, multi-property management, QR-code/link
sharing, maps/video embeds, reporting/analytics on guest engagement; **Guidebook Marketplace** — upsell
cards for early check-in, late checkout, mid-stay cleaning, etc., processed via Stripe with a **1% Stripe
fee** on marketplace transactions (this is the only fee on an otherwise flat-subscription product).

**Pricing (per WebSearch synthesis):** Power Host $9.99/mo → Prime $24.99/mo → Prime Plus $49.99/mo →
Professional from $75/mo; **a single guidebook is free.** Notably this is sold as a genuinely **standalone**
product independent of Hostfully's own full PMS — i.e., even a PMS vendor sees enough standalone value in
the guidebook/upsell category to spin it out as its own SKU, which is a meaningful signal for how
specialists in this category monetize.

---

## 6. PadSplit / MTR / co-living-specific tool — reconfirmed, still none found

Ran one fresh, differently-worded search this pass (*"PadSplit portfolio analytics dashboard tool 2026
co-living MTR host software"*) specifically to check for a new entrant since the last research pass. Found:
- PadSplit's own **New Earnings Dashboard** (2026 update) — an in-house feature improving *"Collections,
  Expenses and Adjustments"* breakdowns, filterable by month/property/payout account/true-owner — this is
  PadSplit's own native tool getting incrementally better, not a third-party product.
- No new dedicated third-party PadSplit/co-living portfolio-analytics tool surfaced in this search pass.

**This reconfirms, rather than contradicts,** the much deeper verified-absence finding already on file in
`competitive-landscape-business-model-2026-07-12.md` §3 (PadSplit's own host-recommendations page
recommends zero PMS/analytics tools; no coliving-operator platform — ColivHQ, Bidrento, Lavanda, MonkSpaces,
StarRez — mentions PadSplit; a coliving-community substack independently calls PadSplit's native tooling
*"a chore tracker and a messaging app"*). **Not re-opened here** — that brief's sourcing stands; this pass
adds only a fresh negative-search data point plus the 2026 Earnings Dashboard detail as a new fact.

---

## Synthesis: the 5-8 features a specialized analytics/ops COCKPIT most needs to be credible and differentiated

Grounded in the patterns above — what specialists in EVERY category do that full PMSs (per the companion
brief's feature matrix) treat as a weak, tiered, or absent add-on:

1. **Verified, PMS/email-sourced metrics over modeled/scraped ones — KeyData's core wedge, directly
   portable.** KeyData's explicit critique of scraped-data competitors (*"avoid inflated ADRs, miscounted
   nights, or revenue overstatements"*) is exactly the trust argument Cockpit's email-first ingestion model
   can make even more strongly than KeyData's own PMS-API sourcing, since Cockpit reads the platform's own
   confirmation emails/co-host view rather than either scraping or depending on a PMS's API fidelity.

2. **Pacing + booking-window + forecasting analytics as a named, dashboarded feature (KeyData's DemandIQ,
   AirDNA's MarketMinder) — not just trailing occupancy/ADR.** Every full-PMS competitor's owner-reporting
   is backward-looking (per the companion brief's feature-matrix); every analytics specialist's
   differentiator is forward-looking (pacing, booking window, demand forecasting). This is a table-stakes
   requirement for Cockpit to be taken seriously as an "analytics" product at all, not an optional nicety.

3. **Trust accounting + owner statements + per-owner allocation (Clearing/TallyBreeze's core, Lodgify's
   documented weak spot, Hospitable's top-tier-gated feature).** This is the single most consistently
   under-served feature across BOTH the full-PMS feature matrix (companion brief) and confirmed here as a
   dedicated specialist category (two tools, Clearing and TallyBreeze, exist to sell almost nothing else) —
   strong signal this is real, monetizable pain, and directly buildable from ingested reservation/payout
   data without needing OTA write access.

4. **A named, opinionated "health"/anomaly metric, not just raw numbers (Beyond's Health Score pattern).**
   Every pricing tool differentiates on a proprietary derived score rather than presenting raw ADR/occupancy
   — Cockpit should ship at least one branded, opinionated derived metric (e.g., a portfolio "at-risk" or
   "under-priced" flag) rather than only a dashboard of raw numbers, both for differentiation and because
   host time-pressure rewards synthesis over raw data.

5. **Reconciliation-grade transaction detail with rollback/audit trail (TallyBreeze's rollback/undo,
   class-tracking).** A read-only visibility product's single biggest credibility risk is a host catching
   ONE wrong number and distrusting everything after — TallyBreeze's granular undo/rollback for imported
   entries is a direct, cheap-to-borrow pattern: show provenance (which email/record a number came from) and
   let a host flag/correct without Cockpit silently "fixing" it.

6. **A genuinely PadSplit/MTR-native metric set, not an STR-first product with a room-count bolt-on.**
   Reconfirmed again this pass: zero competitors — not even PadSplit itself, per its own recommended-tools
   page — build portfolio analytics for rent-by-room/co-living. This remains Cockpit's most defensible,
   least-contested wedge of anything surveyed in this entire brief (STR analytics is crowded four ways —
   AirDNA, KeyData, Rankbreeze, and every PMS's own reporting; PadSplit/co-living analytics has zero
   dedicated competitors found across two research passes).

7. **Explicit, plain-language "we are not a PMS" self-positioning, modeled on Breezeway's dedicated
   comparison page.** Breezeway's own site navigation includes a standing "PMS vs Breezeway" page — the
   single clearest self-positioning artifact found in this brief. Cockpit should adopt the same posture
   explicitly (a dedicated "Cockpit vs. your PMS" page/section) rather than relying on read-only-ness
   speaking for itself — every specialist surveyed here does this proactively, not passively.

8. **A disclosed, low/zero setup fee as an explicit differentiator line, not an assumption.** Clearing
   charges $199 setup despite being a narrower product than a full PMS; Enso Connect discloses a $300
   implementation fee; Hostaway/Guesty's onboarding fees are $300–1,500 (companion brief). A $0-setup,
   email-invite-to-value-in-minutes claim is verifiably differentiated against the *specialist* competitive
   set too, not just against full PMSs — worth stating as a concrete, comparable claim, not vague ease-of-use
   marketing.

**What did NOT make the shortlist, deliberately:** dynamic pricing / price-push itself (§2's synthesis shows
every current player uses an OAuth-partner-or-PMS-intermediary model Cockpit doesn't have and would take
material effort — Airbnb API-partner application or piggybacking a PMS's channel connection — to replicate;
this is a "maybe later" bet, not a credibility-day-one feature) and cleaner-marketplace/task-automation
(Turno/Breezeway's core, but this requires either a cleaner supply-side network Cockpit doesn't have or deep
PMS write-integration for task creation — orthogonal to a read-only analytics/visibility positioning).

---

## Not found / could not verify — full list (per the honesty bar)

- **AirDNA:** could not open a single AirDNA-owned page this pass (`airdna.co` home, `/faqs`, `/pricing`,
  `/vacation-rental-data/app`, `apidocs.airdna.co` all 403'd or content-blocked; G2's AirDNA pages also
  403'd; Wayback Machine unreachable from this environment this pass). The entire AirDNA entry rests on
  independent secondary sources (Mashvisor, Awning, 10xbnb, KeyData's own comparison page) — internally
  consistent across 4+ sources but not vendor-verified directly. Exact current dollar pricing not found.
- **Turno's own pricing page** (`turno.com/pricing/`) 403'd; figures are from WebSearch synthesis of Turno's
  Help Center content, not an independently opened rendered page.
- **Hostfully Digital Guidebooks** — direct fetch returned an unreadable image render; all figures/features
  are WebSearch synthesis only, not independently opened.
- **Wheelhouse's and Beyond Pricing's exact Airbnb-partner status** (official-partner vs. PMS-intermediary
  as the *primary* path) — neither vendor's own page states this explicitly; Airbnb's own 2025 Preferred
  Software Partners page 403'd on direct fetch, so I could not check the partner list directly this pass
  (the 2024 list was checked in the companion PriceLabs brief and did not include PriceLabs either — pricing
  tools may categorically sit outside that specific PMS/channel-manager-scoped program; not confirmed).
- **Touch Stay's actual current pricing** — conflicting secondhand figures ($8.25/mo vs. ~$15/mo), pricing
  page is a JS calculator I could not render as text; genuinely unresolved, flagged rather than guessed.
- **Duve's exact pricing structure** (per-unit vs. flat) — the one secondhand figure found ($120–200/mo
  tiers) does not specify per-property scaling, unusual for this category; not independently confirmed.
- **Rankbreeze's precise data-refresh cadence and whether "simulated incognito search" is the sole ranking
  data source or one of several** — the WebSearch-synthesized quote reads as authoritative but was not
  independently confirmed by opening Rankbreeze's own methodology page directly.

## Constraints/gotchas for future researchers on this domain

- `airdna.co`, `apidocs.airdna.co`, and `g2.com` product-feature/pricing pages are hard-blocked to this
  environment's WebFetch (403) with no working Wayback fallback available this session — plan to either try
  a different fetch path (curl-with-UA workaround used successfully for `help.pricelabs.co` in the companion
  brief) or budget for secondary-source-only coverage on AirDNA specifically.
- Several vendor pricing pages are **JS-rendered calculators** (Touch Stay, Wheelhouse), not static text —
  WebFetch returns an empty/generic shell even at 200 status; this is a distinct failure mode from a 403 and
  needs the same "flag as unverified" treatment, not silent omission.
- Brand-rename redirects are live in this space right now — Bnbtally → TallyBreeze (301 redirect confirmed
  live 2026-07-12) — a stale brand name in a future search may miss the current product entirely.
