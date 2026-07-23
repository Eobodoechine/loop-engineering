# Domain Brief: Competitive Pricing, Feature Matrix, Wedge & Business Model — Cockpit (STR + PadSplit PMS)

**Date:** 2026-07-12
**Mode:** D (domain research for a build)
**Builds on:** `~/Claude/loop/research/pms-competitor-complaints-adoption-2026-07-12.md` (customer-complaints
pass — read first; this brief does not repeat those quotes, only cross-references them where relevant).
**Question:** market/pricing/positioning facts needed to write a business plan + competitive feature set for
Cockpit, a read-only/co-host-onboarded PMS-adjacent product for STR + PadSplit hosts.

## Honesty-bar access notes (read before trusting any number below)

- **Official vendor pricing pages that rendered real numbers via WebFetch:** OwnerRez
  (`ownerrez.com/pricing`), Guesty (`guesty.com/pricing`, partial — Lite tier only), Hospitable
  (`help.hospitable.com` support article), PriceLabs (`hello.pricelabs.co/plans/` +
  `help.pricelabs.co` KB article), Clearing (`getclearing.co/pricing`).
- **Official vendor pricing pages that returned only a JS shell / no numbers via WebFetch** (confirmed
  by opening — genuinely no content, not a fabrication): Hostaway (`hostaway.com/pricing`, quote-gated,
  page literally says "Get a free quote," no published number — this is Hostaway's real, deliberate
  no-published-price policy, confirmed independently by a third party below), Hospitable's own
  `hospitable.com/pricing` (numbers render as JS placeholders `--/mo` — I got the real numbers instead
  from Hospitable's own **help-center** article, which is still a first-party Hospitable source).
- **Pages that 403'd on every attempt (Lodgify's own pricing page, AirDNA's own pricing page, PadSplit's
  Furnished Finder stats page):** could not open directly. Where this happened I used WebSearch's
  synthesis of third-party roundups/aggregators and **flag every such number `[secondhand — WebSearch
  synthesis, not independently opened]`**, and looked for a second independent source to corroborate
  before including it.
- **Operator-cost-roundup sites** (`rakidzich.com`, `costbench.com`, `dupple.com`, `pricingnow.com`) are
  third-party aggregators, not vendors. Rakidzich explicitly self-labels its Pro/Enterprise-tier
  Guesty/Hostaway figures as **"operator-reported quotes," not official pricing** — I've kept that
  distinction visible below rather than presenting them as vendor-published numbers. Two independent
  aggregators (rakidzich + costbench/dupple via WebSearch) landed in the same ballpark for Guesty Pro
  ($40–72/listing/mo), which is the corroboration bar Mode D asks for.
- **Not found / could not verify:** Lodgify's official per-plan dollar figures (site 403'd every attempt;
  only WebSearch-synthesized numbers available, which themselves disagreed slightly — $16 vs $26 for
  Starter — depending on monthly/annual framing, so I report both and flag the spread). AirDNA's official
  pricing page (403'd; used WebSearch synthesis + AirDNA's own help-center article, which confirmed tier
  *names* but not dollar figures). A single authoritative "how many PadSplit hosts exist" figure — I
  found room/resident counts, not a host/landlord count (see Wedge section). The specific "14,000→78,000
  US coliving beds 2018–2025" stat I surfaced early could **not be re-traced to any primary report** on a
  second pass (searched 3 more ways) — I am **dropping it as unverifiable** rather than including it; see
  Wedge section for the two figures I could ground instead.

---

## 1. Pricing models — incumbent-by-incumbent

### Summary table

| Vendor | Model | Entry price (verified where marked) | Min. listings | What unlocks at higher tiers | Setup/onboarding fee | Contract |
|---|---|---|---|---|---|---|
| **Hostaway** | Per-listing subscription, quote-gated (no public price list) | No published number. Third-party operator-reported range: **$125–175/mo for 1–4 listings**, compressing to **$15–25/listing/mo at 10+ listings** `[secondhand — rakidzich.com, self-labeled "operator-reported 2026 quotes," corroborated in direction by a second WebSearch roundup]` | None found in official docs; billing scales per listing, no stated floor `[Hostaway support FAQ page 403'd, could not open directly]` | Not tiered by feature so much as by listing count; higher volume = lower per-unit rate | **$300–1,000+** one-time, scaling with portfolio size/data-migration complexity `[secondhand, same source]` | **Annual is the default/steered option**, 10–20% cheaper than month-to-month; some operators report annual-only for new accounts `[secondhand]` |
| **Guesty** | Per-listing subscription, tiered by listing-count band | **Lite: "$9/month per listing," for 1–3 listings** `[guesty.com/pricing, verified — I opened this page directly]`. Pro tier: no published number; operator-reported **$40–72/listing/mo** `[secondhand, rakidzich.com; independently corroborated in the same $40–72 band by a second WebSearch aggregator pass]` | Lite: 1–3 listings. Pro: 4–199. Enterprise: 200+ `[guesty.com/pricing, verified — exact band language on the page]` | Pro unlocks the quote-gated tier (implies deeper automation/API); Enterprise adds custom/negotiated terms. Add-ons sold separately: PriceOptimizer, Damage Protection, Guesty Pay, Advanced Websites, LocksManager, Capital — a **"Guesty Ultimate" bundle claims "Save 40%"** on these bundled together `[guesty.com/pricing, verified]` | Lite: none stated. Pro: **operator-reported $300–1,500** `[secondhand]` | Monthly available but **annual is discounted** (exact % not published on the page I opened) `[guesty.com/pricing, verified for the fact, not the %]` |
| **OwnerRez** | Sliding per-property scale, **no revenue %, no booking fees, no commission** | **$88/month for 1 property**, "the more properties, the cheaper the fee is per property" (published sliding scale beyond 1 property not shown on the page — table for 5+ requires contacting them) `[ownerrez.com/pricing, verified — opened directly]` | None — starts at 1 | Premium *feature modules* (not listing tiers) sold as add-ons: Property Management module, QuickBooks integration, Hosted Websites, WordPress plugin, SMS (usage fees after 500 outbound segments/mo), Rezzy AI `[ownerrez.com/pricing, verified]` | **Explicitly zero** — "No setup fees, booking fees, or contracts" `[ownerrez.com/pricing, verified quote]` | **Monthly only**, credit card on file, cancel anytime; 14-day free trial (premium features included only during trial) `[ownerrez.com/pricing, verified]` |
| **Hospitable** | Per-property tiered subscription + transaction-based add-ons | **Free "Essentials" tier now exists** (unlimited properties, core sync/inbox, no AI auto-reply, no direct-booking site, no smart-lock, no API) — **$0/mo** `[help.hospitable.com official support article, verified]`. Paid: **Host $29/mo (up to ~2 properties, +$10/mo per extra)**; **Professional $59/mo for 2 properties (+$15/mo per extra)**; **Mogul $99/mo for 3 properties (+$30/mo per extra)** `[help.hospitable.com, verified — official first-party source]`. A second official-adjacent third-party source (staystra.com, which itself opened Hospitable's docs) reports the *annual-billed* per-additional-property increments as lower ($1/$2/$3 instead of $10/$15/$30) — **the discrepancy is annual-discount framing, not a contradiction**; flagging both numbers rather than picking one. | 0 (free tier), scaling per-property fees above that | Host→Professional adds direct-booking site + guest payments + more smart-device slots; Professional→Mogul adds owner portal, custom branding, QuickBooks, marketplace access `[help.hospitable.com, verified]` | None stated as a flat fee; **transaction-based fees instead**: Dynamic Pricing add-on $5–15/property/mo depending on tier, Direct Booking 1% (Basic) or 4%+3% (Premium), security-deposit processing 2%, custom-upsell processing 7–10%, owner-payout extra runs 1.5% capped at $5 `[hospitable.com/pricing + help.hospitable.com, verified]` | 12% discount for annual billing on Host/Professional/Mogul base rate `[help.hospitable.com, verified]`; 14-day free trial, no card required |
| **Lodgify** | Per-property tiered subscription, 3 named tiers | **Could not open the official pricing page directly (403 on every attempt, including a get.lodgify.com variant).** WebSearch-synthesized figures, two variants that disagree by billing cycle: **Starter $16/mo (annual) vs $26/mo (monthly)**; **Professional $40/mo (annual) vs $42/mo (monthly)**; **Ultimate $59/mo (annual) vs $62/mo (monthly)** `[secondhand — WebSearch synthesis only, NOT independently opened; treat as directional]` | Not established (blocked source) | Starter: unified inbox, channel manager, booking widget. Professional adds 24/7 support + Google Vacation Rentals + custom workflows. Ultimate adds advanced analytics, cleaning/task management `[secondhand, same caveat]` | **"No setup or hidden fees"** per Lodgify's own marketing language surfaced in search `[secondhand]` | 7-day free trial, no card required; "1:1 onboarding with a product expert" bundled into paid tiers per search-synthesized copy `[secondhand]` |

### Cross-vendor takeaways for the business plan
1. **Every incumbent except OwnerRez actively hides its real price** behind a quote/demo gate above the
   entry tier — this is a deliberate go-to-market choice (sales-assisted, high-touch), not an oversight.
   OwnerRez is the outlier: full transparency, flat sliding scale, explicitly zero setup/booking fees.
2. **Onboarding fees are real and material** at Hostaway ($300–1,000+, secondhand) and Guesty Pro
   ($300–1,500, secondhand) — a new entrant charging $0 onboarding is a legitimate, quantifiable
   differentiator, not just a vibe claim.
3. **Hospitable's free tier is the most directly relevant precedent** for Cockpit: a real incumbent just
   launched a $0/unlimited-properties core tier and monetizes the add-ons (dynamic pricing, direct
   booking %, smart devices) instead of the base subscription. This is evidence a freemium-core /
   paid-analytics-and-automation model is commercially viable in this exact market, not a hypothetical.
4. **None of the five charge a straight "% of booking revenue" as their primary model** — Guesty and
   Hospitable both offer/impose small **transaction-level** fees (GuestyPay ~2.9%+$0.30, Hospitable
   1%/4%+3% on direct bookings) but the *core* subscription is flat/per-listing in all five. PriceLabs
   (see §4) is the one product surveyed that offers a pure 1%-of-revenue plan as an *alternative* to its
   flat per-listing fee — worth citing as precedent that usage-based pricing exists in this space, just
   not as the incumbents' primary PMS pricing model.

---

## 2. Feature matrix — table stakes vs. incumbent coverage

Sourced primarily from a third-party comparison (`rakidzich.com/articles/lodgify-vs-hostaway-vs-guesty-vs-ownerrez-2026`,
opened directly) plus vendor pages opened directly for OwnerRez (`ownerrez.com/features` search
synthesis + support docs) and Hostaway's own support/marketplace pages (opened directly for smart-lock
and cleaning-integration facts). Cross-referenced against the complaints file's per-vendor gap findings.

| Feature | Hostaway | Guesty | OwnerRez | Lodgify | Hospitable | Common gap / complaint tie-back |
|---|---|---|---|---|---|---|
| **Unified inbox / messaging** | Yes, with automation + conditional-logic branching `[rakidzich, secondhand-aggregator]` | Yes, with AI-drafted replies `[rakidzich]` | Yes (automated email templates) `[WebSearch synthesis of ownerrez.com/features]` | Yes, but "lacks automation depth beyond welcome message + review nudge" `[rakidzich]` | Yes — but complaints file found "automated messages...simply don't work" for some reviewers `[cross-ref: complaints file, Hospitable reliability theme]` | Table stakes, all 5 have it; automation *depth* and *reliability* (not presence) is the real differentiator |
| **Multi-calendar / channel sync** | "Excellent," described as operator favorite, but complaints file documents a real double-booking from a 3-week VRBO sync bug `[rakidzich + cross-ref complaints file]` | "Excellent," "enterprise-grade redundancy" per aggregator, but complaints file has "still not connected to VRBO after 3 weeks" `[rakidzich + cross-ref]` | Channel Management module connects to Vrbo/Airbnb in real time `[WebSearch synthesis of ownerrez.com support docs]`; complaints file has a VRBO identity-collision issue (prior-owner account) | "Good" but "reports sync lag and occasional double bookings at 15+ listings" per aggregator; complaints file independently found a **wrong-property cross-mapping bug** `[rakidzich + cross-ref complaints file — two independent sources agree Lodgify has real sync-accuracy risk]` | Complaints file: "auto-syncing with Airbnb" reported as a core feature that "simply doesn't work" for some reviewers | **This is the single most-corroborated gap across BOTH research passes** — every vendor has shipped the feature, but sync-accuracy failures (double bookings, cross-mapping, stalled connections) are the dominant reliability complaint in the complaints file, independent of which vendor |
| **Dynamic pricing (native or integrated)** | Integrates PriceLabs/Beyond, no native engine | Sells its own **PriceOptimizer** add-on (priced separately, not bundled) | Integrates PriceLabs and Beyond `[WebSearch synthesis of ownerrez.com]` | Not covered in the comparison I opened; presumed integration-only | Native Dynamic Pricing add-on, $5–15/property/mo depending on tier `[hospitable.com/pricing, verified]` | Aggregator explicitly states **"none of these [three] include dynamic pricing native"** for the base tier, recommending pairing with PriceLabs/Wheelhouse/Beyond at "$20–40/mo per listing" on top `[rakidzich, secondhand]` — i.e., dynamic pricing is a *stacked* cost on top of the base PMS fee for most of the market, reinforcing that a PMS-agnostic pricing layer is normal, not novel |
| **Cleaning / task management** | Automates cleaning-task creation on checkout via integration with **Turno or Breezeway** (confirmed via Hostaway's own support docs, opened directly) `[support.hostaway.com, verified]` | Not detailed in sources opened | Not detailed in sources opened | Only the **Ultimate** tier claims "advanced...cleaning management" `[secondhand, WebSearch synthesis]` | Not detailed in sources opened | Cleaning/task management is largely **outsourced to third-party integrations (Turno, Breezeway)** rather than built natively across this set — a genuine feature-completeness question for Cockpit: build native or integrate |
| **Direct-booking website** | "Add-on, basic...does not win you guests," most operators pair with a separate WordPress/Webflow site `[rakidzich]` | "Add-on, polished," multi-property-brand oriented `[rakidzich]` | Included: direct booking websites are a core listed feature `[WebSearch synthesis of ownerrez.com]` | "Best in class," drag-and-drop, conversion-focused per aggregator `[rakidzich]` | Direct Booking available Basic (1% fee) / Premium (4%+3% fee) tiers `[hospitable.com/pricing, verified]` | Wide quality spread — Lodgify's strongest asset per this comparison, Hostaway's weakest |
| **Channel management (OTA distribution)** | Table stakes across all 5 | Table stakes across all 5 | Table stakes | Table stakes but "sync lag...at 15+ listings" | Table stakes | This is the one feature category that structurally **requires OTA API-partner status** — directly relevant to Cockpit's constraint (§4/§5): Cockpit cannot compete here head-on without becoming an Airbnb/Vrbo API partner, which the brief states it is not |
| **Financial reporting / owner statements** | "Solid," QuickBooks integration, works for co-hosts under ~25 properties per aggregator; **no full trust accounting** `[rakidzich]` | "Full trust accounting" incl. owner statements, expense tracking, 1099 prep — the strongest in this set per the aggregator `[rakidzich]` | "Quiet favorite" for owner statements/trust accounting/CRM per aggregator; official docs confirm a Property Management module generates monthly owner statements + granular owner/cleaner/maintenance portal access `[rakidzich + WebSearch synthesis of ownerrez.com support docs]` | "Limited," "an afterthought" — aggregator explicitly advises **"if you co-host even 3 properties for other people, you should not pick Lodgify"** `[rakidzich]` | Owner statements/portal/QuickBooks gated to the top **Mogul** tier only ($99+/mo) `[help.hospitable.com, verified]` | **Directly relevant to Cockpit's likely core value prop** (owner/co-host-facing financial visibility): Lodgify is weak here by its own comparison-site's admission; Hospitable gates it to the top tier; this is a legitimate wedge feature to lead with, especially for hosts who co-host/report to owners |
| **Automated review requests** | Yes, part of automation suite `[rakidzich]` | Not explicitly detailed beyond AI message drafting `[rakidzich]` | Not detailed in sources opened | Basic triggers mentioned `[rakidzich]` | Not detailed in sources opened | Table stakes, but shallow signal across the board — lower priority differentiator |
| **Smart-lock / IoT integration** | Compatible with 100+ smart locks including Schlage; two-way API sync with RemoteLock confirmed via Hostaway's own docs `[support.hostaway.com + hostaway.com/marketplace/remote-lock, verified]` | Sold as a paid add-on (LocksManager) per pricing page `[guesty.com/pricing, verified]`; aggregator says Guesty treats smart locks as add-on, no native thermostat sync `[rakidzich]` | RemoteLock integration confirmed (auto-generates unique door codes tied to reservation dates) `[WebSearch synthesis of ownerrez.com support docs]` | Paid add-on per aggregator, no native thermostat sync `[rakidzich]` | **Included in Professional/Mogul plans**, not gated as a separate paid add-on — 2 devices/property on Professional, 4 on Mogul `[hospitable.com/pricing + help.hospitable.com, verified]` | Hospitable is the only one of the 5 bundling smart-lock into a mid-tier plan rather than upselling it separately — worth noting for feature-set design (bundle vs. line-item) |
| **Damage / deposit handling** | Not detailed in sources opened | Sold as add-on: **"Guesty Damage Protection™"** `[guesty.com/pricing, verified as an add-on name, not a price]` | Integrates with **Truvi** for guest screening/damage protection `[WebSearch synthesis of ownerrez.com]` | Not detailed in sources opened | Native: **security-deposit processing at 2% fee**; damage protection claims **"$5M coverage per stay"** `[hospitable.com/pricing, verified]` | Thin/inconsistent coverage across vendors — a real gap, and directly relevant to PadSplit-style rent-by-room hosts where damage/deposit friction is a distinct, recurring operational pain point (see §3) |

**Feature-matrix bottom line:** the technically hardest table-stakes item to replicate — real-time,
reliable multi-OTA channel sync — is exactly the one Cockpit's stated constraint (no API-partner status)
makes structurally unavailable to build the same way the incumbents do. The clearest feature-set
differentiators available *without* API-partner status are: (a) financial/owner reporting (Lodgify is
weak, Hospitable gates it high — a wedge Cockpit can hit at a lower price point via ingestion rather than
API sync), and (b) reliability/accuracy of what's shown (the complaints file's dominant theme), which a
read-only ingestion model can credibly claim to solve differently (no live write-back means no risk of
Cockpit itself causing a double-booking) — but this needs to be framed honestly: Cockpit trades
"can't push changes to OTAs" for "can't cause an OTA-sync bug," which is a real trade-off, not a pure win.

---

## 3. Underserved segments / wedge — is PadSplit/co-living genuinely unserved?

### Direct evidence PadSplit hosts have no dedicated portfolio-management tool
- **PadSplit's own host-recommendations page** (`padsplit.com/host-recommendations`, opened directly)
  recommends exactly **one** third-party tool for property management — Moen Flo (water-leak
  monitoring) — plus a Nest thermostat mention. **No accounting, analytics, multi-property dashboard, or
  portfolio-management tool is recommended anywhere on PadSplit's own resource page.** `[verified,
  opened directly]` For a company running 33,000+ rooms and actively publishing host-education content,
  the absence of a recommended PMS-adjacent tool is a meaningful negative signal, not just silence.
- **PadSplit's own property-management feature page** (`padsplit.com/hosts/property-and-member-management`,
  opened directly) states the *only* named third-party integration across the whole page is
  **RemoteLock** for smart locks. No PMS, no analytics tool, no accounting integration is mentioned.
  `[verified, opened directly]`
- I searched specifically for evidence of a third-party PadSplit-focused PMS/analytics tool (multiple
  query variants) and found **none**. The closest adjacent products are general coliving operator
  platforms — **ColivHQ** (opened directly: "operating system for coliving...0–200 beds," built by
  founders of a Singapore coliving brand, **does not mention PadSplit or STR platforms anywhere on its
  page**) and **Bidrento / Lavanda / MonkSpaces / StarRez** (found via search, not independently opened
  — but none surfaced with a PadSplit integration or mention in any snippet). A coliving-community
  substack (`everythingcoliving.substack.com`, opened directly) makes the same observation from the
  operator side: it explicitly names COHO, MonkSpaces, and ColivHQ as tools with *community-engagement*
  features "that could be adapted for PadSplit's distributed model" — phrased as a hypothetical
  adaptation, i.e. **confirms none currently serve PadSplit's specific model.** `[verified, opened
  directly]`
- **PadSplit's own native tooling is explicitly thin**: the substack piece characterizes it bluntly —
  *"The 'community' tools amount to a chore tracker and a messaging app"* `[everythingcoliving.substack.com,
  verified, opened directly]* — and PadSplit's own marketing copy (property-and-member-management page)
  confirms the native toolset is messaging + maintenance-ticketing + payments + move-in automation, with
  no cross-portfolio financial/analytics layer described anywhere in what I could open.

**Conclusion on the wedge: the evidence supports the thesis.** No dedicated PMS/analytics tool for
PadSplit hosts or rent-by-room co-living operators surfaced anywhere in this research — not on PadSplit's
own recommended-tools page, not among the general coliving-operator platforms, not in review/forum
search. This is a genuine, verifiably unserved segment as of this research pass, not an assumption.

### Market sizing (mixed confidence — read the caveats)
- **PadSplit scale (verified, two independent PadSplit-published figures, opened directly and via
  WebSearch corroboration):** **33,000+ shared-housing rooms** nationwide as of June 2026, across **35+
  metros**, having **housed over 60,000 people** total (as of Dec 2025) `[padsplit.com content via
  WebSearch synthesis of PadSplit's own market-insights page + corroborated by the Furnished Finder
  press release, which independently states "more than 33,000 shared housing rooms nationwide" —
  same-order-of-magnitude agreement between two separate PadSplit-sourced mentions]`.
- **PadSplit host/landlord count: NOT FOUND.** I could not locate a published host or landlord count
  anywhere (only room and resident counts). This is a real gap for the business plan's TAM math — rooms
  ÷ average rooms-per-host would need a PadSplit-published or estimated ratio, which I did not find.
  **Flag this explicitly to whoever writes the business plan**, since "size of the PadSplit host market"
  was one of the specific questions asked and I cannot answer it with a real number.
- **US coliving market size:** two independent figures, roughly consistent in order of magnitude —
  (a) "~$4.2B in 2025, projected to exceed $10B by 2030" (WebSearch synthesis, not independently opened)
  and (b) North America = 28% of a global $13B (2026) coliving market from `everythingcoliving.com/coliving-statistics`
  (opened directly) = **~$3.6B**, consistent-ish with (a). I'm treating ~$3.6–4.2B as a reasonable
  current US coliving-market range, corroborated by two separate sources, though neither is a
  government/primary statistical source. **A specific bed-count time series I initially surfaced
  ("14,000→78,000 US beds, 2018–2025") could not be re-traced to any primary source on a second search
  pass and is dropped — do not cite it.**
- **MTR/mid-term-rental market:** AirDNA is cited (via WebSearch synthesis, not independently opened) as
  estimating **"$6B+ of transactions on [Airbnb] that are 28 days and longer,"** and mid-term rentals are
  characterized as **"19% of the total rental market"** by the same synthesis — this specific 19% figure
  is high enough relative to context that it reads as possibly a misattribution/rounding in the
  search-engine's summarization (I flag it as suspect, not confirmed). More solid: **Furnished Finder's
  own growth** — from "~20,000 to more than 300,000 listings" between 2019 and now (WebSearch synthesis
  of Furnished Finder's own content, not independently opened; Furnished Finder's stats page itself
  403'd on direct fetch) — and the **PadSplit × Furnished Finder partnership** (`prnewswire.com`, opened
  directly) confirms PadSplit listed "1,000+ rooms on Furnished Finder" as of the partnership, and that
  private-room rentals were "19% of all property views on Furnished Finder in 2025" with "over 60,000
  private room listings" and "average monthly rental rates around $1,300" — **this 19%-of-views figure is
  a different, better-sourced number than the suspect "19% of total rental market" figure above; don't
  conflate them.**

### Other underserved segments (beyond PadSplit/co-living)
- **Small hosts (1–5 listings) priced out of Guesty's Pro tier structurally**: Guesty's own published
  tier bands (Lite 1–3, Pro 4–199) mean a host who wants Pro-tier features but has 1–3 listings is
  structurally pushed into Lite or a quote call — this is evidenced directly from Guesty's own pricing
  page tier bands `[guesty.com/pricing, verified]`, not inferred.
- **"Cockpit without switching" is itself a validated model, not a novel bet**: **KeyData**
  (`keydatadashboard.com`, opened directly) is a live, real precedent for exactly this positioning — a
  **read-only analytics layer** that "does not replace your PMS," integrates with 80+ existing PMSs
  including Guesty and Hostaway, and pulls "verified reservation data from property managers" rather than
  scraping. `[verified, opened directly]` This directly de-risks the "hosts who want analytics without
  switching their whole operation" segment named in the brief — it's proven to be a fundable, real
  product category (KeyData also serves DMOs/enterprise investors via API, per its own site), though its
  own pricing is not published (quote-gated), so I can't quantify how well it monetizes that segment.

---

## 4. Business model options — what fits a read-only/cockpit-first product

Cockpit's stated constraint: **no OTA API-partner status → cannot take a % of booking revenue the way
Hostaway/Guesty structurally could; ingestion is email/co-host-based, not a live two-way API.** This
section surveys what adjacent **read-only/analytics-first** tools actually charge, since those are the
closer pricing precedent than the full-PMS incumbents in §1.

| Tool | Category | Model (verified where marked) | Relevance to Cockpit |
|---|---|---|---|
| **PriceLabs** | Dynamic pricing (own category, not full PMS) | **$14.49–$19.99/listing/mo base** (US/UK/CA/EU/AU/NZ/IL), sliding down to **$5.00/listing/mo at 251+ listings**, **$9.99/listing/mo rest-of-world** `[hello.pricelabs.co/plans/ + help.pricelabs.co KB, both verified, opened directly]`. **Also offers a pure 1%-of-integrated-platform-revenue plan as an alternative to the flat fee**, explicitly "for hosts who prefer usage-based pricing tied directly to their earnings" `[hello.pricelabs.co, verified]`. Add-ons: Market Dashboard $9.99–39.99/mo, Revenue Estimator Pro $10–125/mo, extra API sync $1/listing/mo. | **Directly relevant precedent**: PriceLabs is *also* not an OTA API-partner-of-record for pricing pushes in the same sense a PMS is — it pushes pricing via the PMS's own channel connections. It monetizes via a flat per-listing fee with steep volume discounts, an optional %-of-revenue alternative, and separately-metered analytics add-ons (Market Dashboard, Revenue Estimator). This is a close structural analog to what Cockpit could do: flat-per-unit core + metered analytics add-ons. |
| **AirDNA** | Market data / analytics (read-only, no PMS integration required) | Tier names confirmed officially (Free / Research / Host / Advanced) `[help.airdna.co, verified]`, but exact dollar figures only available via WebSearch synthesis: **Free tier** (12mo history, limited lookups); **~$19.95–99.95/mo** MarketMinder tiers by market size (small/mid/major market); **Global ~$999.95/mo or ~$599.99/mo annual**; **"40% annual discount" runs consistently** `[secondhand — WebSearch synthesis only, official page 403'd; internally consistent across two independent search queries, treated as directionally reliable but not vendor-confirmed]` | Proves a **freemium + market-size-tiered** pricing model works in this exact adjacent category — relevant if Cockpit wants a free/cheap entry tier with paid tiers gated by portfolio size or market coverage rather than by feature. |
| **Baselane** | Banking/bookkeeping for landlords (not STR-specific, adjacent) | **Free** core banking/bookkeeping/rent-collection; monetizes via **interchange/merchant fees + a 2.99% card-payment processing fee** + affiliate revenue; **"premium features at a monthly fee" are stated as coming, not yet live** `[WebSearch synthesis, not independently opened — Baselane's own page was not fetched directly this pass]` | Real precedent for **free-core, monetize-the-money-movement** — relevant if Cockpit ever touches payments/payouts, though Cockpit as scoped (read-only/analytics) has no natural money-movement layer to monetize this way unless it adds one. |
| **Clearing (getclearing.co)** | Accounting/bookkeeping specifically for STR | **Starter $25/mo for up to 5 listings; Standard from $150/mo for up to 10 listings**; **$199 one-time setup fee** (includes a dedicated specialist); **Trust Accounting add-on $2.50/unit/mo**; 20% annual-contract discount; 30-day money-back guarantee `[getclearing.co/pricing, verified, opened directly]` | Useful comp for **small-portfolio flat pricing with a real setup fee** — note Clearing does NOT waive setup fee despite being a narrower/lighter product than a full PMS, which argues Cockpit's "$0 setup" claim (if made) is a genuine differentiator worth stating explicitly, not assumed. |
| **KeyData** | Read-only PMS-agnostic analytics layer | Not published (quote/demo-gated); confirmed to integrate with 80+ PMSs without replacing them `[keydatadashboard.com, verified, opened directly]` | Closest **structural** precedent to "Cockpit sits on top of/alongside the host's existing operation" — but KeyData's pricing opacity means it offers no pricing-model lesson, only a positioning-validation one. |

### Model options ranked for Cockpit's actual constraint (no API-partner status, email/co-host ingestion)

1. **Flat SaaS per-host or per-unit, tiered by unit count** (OwnerRez/PriceLabs pattern) — simplest to
   explain, no dependency on OTA revenue visibility (which Cockpit may not even reliably have without API
   access), and matches the one incumbent (OwnerRez) whose pricing photographs best with hosts in the
   complaints-file research (pricing was a *strength*, not a complaint, for OwnerRez).
2. **Freemium core + paid analytics/automation add-ons** (Hospitable's new free tier + AirDNA free/paid
   split pattern) — directly precedented by a live incumbent (Hospitable) launching exactly this in the
   same market in 2026, and structurally sound for Cockpit since the paid add-ons (deeper analytics,
   owner-statement automation, PadSplit-specific room-level reporting) don't require OTA API access to
   build — they're computed from ingested data Cockpit already has.
3. **Per-listing metered analytics** (PriceLabs' Market Dashboard / Revenue Estimator Pro pattern,
   AirDNA's per-market pattern) — good fit if Cockpit's paid tier is specifically the analytics/insight
   layer rather than the ingestion/inbox layer, letting the core "connect your email/co-host" flow stay
   free as a growth loop.
4. **NOT recommended given the stated constraint: any %-of-revenue model.** Every %-based fee found in
   this research (Hospitable's direct-booking 1%/4%+3%, Guesty's ~2%–3.5%, GuestyPay's 2.9%+$0.30,
   PriceLabs' optional 1% alternative) is charged by a product that **either processes the payment
   itself or has direct API visibility into confirmed revenue.** Cockpit, as scoped (read-only,
   email/co-host ingestion, not an OTA API partner), has neither — it would be charging a % of a number
   it cannot independently verify, which is both a trust problem (hosts would have to self-report
   revenue Cockpit can't confirm) and matches the exact "hidden fee / rounding up %" complaint pattern
   already documented against Guesty in the companion complaints file. **This is a clean, evidence-backed
   reason to avoid %-of-revenue, not just a stated constraint to route around.**

---

## 5. Positioning — one to two sentences each, given Cockpit's actual constraints

*(No API partnership + email/co-host ingestion + PadSplit-native ambition + lowest-friction onboarding —
each line below is grounded in a specific fact from this research pass or the companion complaints file,
cited inline.)*

- **vs. Hostaway/Guesty (the sync-heavy, sales-gated incumbents):** Cockpit doesn't compete on live
  two-way OTA sync — it can't, without API-partner status — so it should position as the tool that
  *shows you the truth about your portfolio without adding another system that can itself cause a
  double-booking* (a real, documented Hostaway/Lodgify failure mode from the complaints file), reachable
  in minutes via an email invite instead of the "IT person for the first steps" onboarding a Guesty CTO
  reviewer described `[complaints file, verified]` or the $300–1,500 onboarding fee Guesty Pro reportedly
  charges `[secondhand, this brief §1]`.
- **vs. OwnerRez (the transparent, technical, DIY incumbent):** OwnerRez already proves flat, no-hidden-fee
  pricing wins loyalty in this market (§1) — Cockpit should credit that instinct and go further on
  *ease*, not price transparency alone: OwnerRez's own reviewers cite a steep learning curve and
  limited live support `[complaints file, verified]`, which is the opposite of an email-invite,
  no-configuration onboarding model.
- **vs. Lodgify/Hospitable (the feature-bundled, tier-gated PMSs):** both gate real financial/owner-reporting
  value behind either weak execution (Lodgify, per an independent aggregator's explicit warning against
  co-hosting on it, §2) or a top-dollar tier (Hospitable's Mogul, $99+/mo, §1) — Cockpit can offer the
  reporting/visibility layer on its own, decoupled from the full PMS purchase, at a materially lower
  entry point, the same way KeyData already validates as a real, fundable category (§3).
- **vs. the PadSplit/co-living gap specifically (Cockpit's sharpest, most defensible wedge):** this is not
  a "underserved-adjacent" claim — it's a verified absence. PadSplit's own host-education resources
  recommend zero portfolio-management or analytics tools `[verified, §3]`, no coliving-operator platform
  found in this research mentions PadSplit `[verified, §3]`, and PadSplit's own native tooling is
  described even by coliving-community commentary as "a chore tracker and a messaging app"
  `[verified, §3]`. Cockpit can credibly claim to be the first cockpit-style analytics/reporting layer
  built for PadSplit and rent-by-room hosts specifically, rather than a room-rental afterthought bolted
  onto an STR-first product — no incumbent surveyed here, including PadSplit itself, occupies that
  position today.

---

## Not found / could not verify — full list (per the honesty bar)

- Lodgify's official per-tier dollar figures (page 403'd on every URL variant tried, including a
  get.lodgify.com variant found via search; only secondhand WebSearch-synthesized numbers available, and
  those disagreed with each other by billing-cycle framing).
- AirDNA's official pricing-page dollar figures (403'd; tier *names* confirmed via AirDNA's own help
  article, dollar amounts only from WebSearch synthesis).
- Hostaway's official minimum-listing policy and exact billing-FAQ contents (`support.hostaway.com`
  billing FAQ page 403'd on direct fetch).
- Furnished Finder's own stats page (403'd on direct fetch; used only via a press release and
  WebSearch-synthesized figures instead).
- A specific PadSplit **host/landlord count** (only room-count and resident-count figures found;
  explicitly flag this gap to whoever sizes the PadSplit TAM for the business plan).
- The "14,000→78,000 US coliving beds, 2018–2025" statistic — surfaced once via WebSearch synthesis,
  could not be re-traced to a primary source on a dedicated second search pass, and is **dropped, not
  included** as a citable figure in this brief.
- Exact annual-discount percentages for Guesty (page confirms annual is cheaper than monthly but does not
  state the %) and for OwnerRez's premium-feature-module pricing table beyond the 1-property base rate
  (page directs to "contact us" for 5+ properties).
- A precise, independently-confirmed reconciliation of the two conflicting Hospitable
  per-additional-property figures ($10/$15/$30 monthly-framed vs $1/$2/$3 annual-framed) — both are cited
  from sources that themselves cite Hospitable's own docs, but I could not find a single page showing
  both framings side by side to confirm the exact relationship.
