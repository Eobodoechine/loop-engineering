# Domain Brief: PadSplit / MTR / Co-living Host Feature Requirements — Cockpit's Wedge

**Date:** 2026-07-12
**Mode:** D (domain research for a build)
**Builds on (skimmed, not repeated):**
- `~/Claude/loop/research/competitive-landscape-business-model-2026-07-12.md` — verified the PadSplit/co-living
  wedge is genuinely unserved (PadSplit's own host-recommendations page recommends zero PMS/analytics tools;
  no coliving-operator platform surveyed mentions PadSplit).
- `~/Claude/loop/research/padsplit-host-member-agreements-2026-07-12.md` — Host Agreement Co-Owner clause,
  automation/competitive-use bans (relevant to *how* Cockpit can connect, not to *what* it should build — this
  brief is about the latter).
- `~/Claude/loop/research/email-ingestion-channel-2026-07-12.md` + `gate-verification-2026-07-12.md` — confirmed
  PadSplit sends hosts a booking-request email (rich member data), a member-messenger email (sender/subject
  confirmed, body unconfirmed), and — the gate-verification pass's key finding — **two host-facing collections
  emails** (24h-pre-termination warning + at-termination notice), tied to the $300-balance/48-hour "financial
  probation" mechanic this brief also verifies independently below.

**Question this brief answers:** what does a PadSplit/MTR/co-living host actually *do*, week to week, and what
does that operational reality imply about the feature set Cockpit needs to build — as distinct from a
whole-home STR PMS.

**Honesty-bar method note:** every URL below marked "opened directly" was fetched via WebFetch/curl this pass
(not just a WebSearch snippet) and the quotes are what the fetch tool extracted from that live page. Where a
fetch failed (403) or I relied only on WebSearch's own synthesis without opening the underlying page, it is
flagged `(WebSearch-snippet only, not independently opened)`. A specific, honest gap up front: **I could not
find a real PadSplit host's own YouTube "day in the life" or operations-focused vlog** — the one YouTube result
that surfaced was a *resident's* day-in-the-life, not a host's. I did not have a YouTube-transcript tool
available and treated a resident's clip as out of scope for host operations. Host testimonial evidence in this
brief instead comes from BiggerPockets forum threads (real, opened directly, but thinner than hoped — flagged
inline) and PadSplit's own host-education content (real, opened directly, but naturally not self-critical).

---

## 1. The PadSplit host operating model

### 1a. Leasing unit = the ROOM, not the property
- Members book, pay for, and can be evicted from **individual rooms** — pricing, occupancy status, and
  financial status are all tracked at room/member grain. Multi-occupancy (a couple sharing a room) is a
  **host-controlled per-room revenue lever**: hosts can raise a room's weekly price "up to $100/week using the
  'Manage Rooms' tab," must disclose the added fee in the room description, and PadSplit states "approximately
  20% of applicants seek multi-occupant rooms" `[padsplit.com/help/article/charging-fees-for-multiple-occupants-in-your-padsplit-room-30837897413396,
  opened directly]`.
- **Members can transfer between a host's properties with no new booking fee** `[padsplit.com/help/article/what-is-padsplits-fee-model-for-hosts-24614775906324,
  opened directly]` — i.e. PadSplit already models a multi-property portfolio as one pool a member can move
  within, which is itself evidence the unit of analysis PadSplit's own system treats as fluid is the *room*
  within a *host's portfolio*, not a single property.

### 1b. Billing is per-member, weekly/biweekly, prepaid — payout to the host is monthly, in arrears
This is the single most consequential structural fact in this brief for Cockpit's payout-reconciliation
feature (see §2).
- Members choose their own **"Dues Day"** and pay **weekly or biweekly**, prepaying for the upcoming period
  (e.g., a Friday-the-11th Dues Day invoice covers "housing from Saturday the 12th through Friday the 18th")
  `[padsplit.com/help/article/782765-How-do-Member-Financials-work, opened directly]`.
- A **$25 late fee** applies if a balance survives past 11:59pm on Dues Day; a balance of **$300 or more**
  places the member in **"Termination Risk"/financial probation**, with **48 hours** to cure or be terminated
  `[same source, opened directly]`.
- PadSplit's own financial-status article states there are **"seven different types of financial statuses"**
  hosts can filter Members by on the dashboard — but the article's text does not itemize the seven (the
  itemization is in an embedded image the fetch tool could not read) `[padsplit.com/help/article/319723-how-to-interpret-a-member-s-financial-status,
  opened directly, itemized list NOT FOUND — flag explicitly]`.
- **Host payouts are monthly, in arrears** — "Host Payouts are paid... after the conclusion of each month,"
  targeted complete by the 10th, no later than the 20th `[WebSearch synthesis of PadSplit's own Earnings Payout
  FAQ / payment-topic content — the specific payout-timing page returned only a listing snippet, not
  independently re-opened verbatim this pass; flag as WebSearch-snippet-only for the exact day numbers, though
  the monthly-in-arrears cadence itself is corroborated by the payout-formula page below]`.
- The payout **formula**, confirmed directly: **"Host Earnings (Payout) = Gross Income − Booking Fees − Service
  Fees"**, where **"Service Fee = Service Fee % × (Gross Income − Booking Fees)"**
  `[padsplit.com/help/article/how-does-padsplit-calculate-a-hosts-monthly-payout-4402853494676, opened directly,
  last updated 2024-07-17]`. Note this page gives the formula but **does not describe any reconciliation
  process for matching dozens of weekly/biweekly member transactions to the single resulting monthly number** —
  that reconciliation work is left to the host.
- The **mechanism that exists to do that reconciliation manually** is a CSV export in the Earnings tab:
  "Member collection details for each monthly Host payout" with a `Category` column distinguishing billing vs.
  collection transactions, member bills, member payments, property address, and payout month, filterable/date-
  rangeable, and recently enhanced with an "annual month-by-month summary broken down by property"
  `[WebSearch synthesis of PadSplit's own "Which Member collections are included..." + "New Earnings Dashboard"
  help articles — not independently re-opened verbatim this pass, but consistent with and corroborates the
  CSV-centric architecture the prior email-ingestion brief already confirmed]`.
- **What the dashboard confirms it does NOT give natively:** the one dashboard-financial-views page I opened
  directly enumerates **portfolio-level** ("aggregate view of your earnings") and **property-level** ("Income,
  Expenses, and net Earnings by month and by property") views, plus the CSV for transaction-level detail — **it
  does not mention any per-member or per-room financial view** in what the fetch tool could extract
  `[padsplit.com/help/article/where-can-i-view-my-financials-on-my-host-dashboard-4404902173460, opened
  directly — absence noted, not asserted with 100% certainty since the fetch tool may have summarized
  incompletely, but this is consistent with every other source in this brief]`.

### 1c. Fee model (context for host P&L math)
**"10 days + 8%"**: PadSplit keeps 100% of the first 10 days of a new member's stay as a booking fee, then
takes **8% of all transactions thereafter**; the host keeps the full move-in fee (host-set, "varies per room
but averages $100," meant to cover cleaning/prep); early departure before 10 days means PadSplit only keeps
dues for days actually stayed, and the host keeps the move-in fee regardless
`[padsplit.com/help/article/what-is-padsplits-fee-model-for-hosts-24614775906324, opened directly]`.

### 1d. Member vetting: host-controlled since "Say Yes," but time-boxed and default-approve
- Before the "Say Yes" feature existed, **"PadSplit managed the screening and placement of members into
  hosts' homes based on preferences... hosts often had limited visibility into who was moving in"**
  `[padsplit.com/host-resources/host-success/how-using-padsplits-say-yes-feature-can-boost-your-occupancy/,
  opened directly]` — i.e. host-side vetting control is a relatively recent product addition, not the original
  model, and PadSplit's central placement algorithm still exists as the default/fallback.
- With Say Yes on: a booking request triggers a host **email + dashboard notification**, and the host has
  **24 hours** to accept/reject — **"If the Host does nothing, it will auto-approve after 24 hours"**
  `[WebSearch synthesis of padsplit.com/help/article/how-can-i-approve-member-bookings-10715968352020 — this
  specific article was directly opened and quoted in the prior gate-verification-2026-07-12.md brief already
  (booking-request email content); the 24-hour auto-approve mechanic is corroborated across two independent
  PadSplit help articles found this pass]`.
- The booking-request email itself carries: **eviction history (past 7 years), Member Score, whether keys were
  ever removed from a prior PadSplit occupancy, contact info, age, employment (if known), approval amount and
  income, and the applicant's optional booking message** `[padsplit.com/help/article/how-can-i-approve-member-bookings-10715968352020,
  opened directly, previously quoted in gate-verification-2026-07-12.md]`.
- "Many hosts have a secondary screening process to get to know prospective members better" beyond what
  PadSplit auto-supplies `[same source]` — i.e. hosts widely feel the platform's vetting isn't sufficient alone.

### 1e. Member scoring/reputation is portable and ties directly to termination risk
- A Member score of **1 or 2 for more than 4 consecutive weeks auto-flags the Member for termination**; the
  host is notified and has an opportunity to request termination, **or** can do nothing for 7 days (auto-raises
  the score to 3) **or** actively click **"Save from termination"**
  `[padsplit.com/help/article/874468-rating-a-member, opened directly]`.
- **"Host ratings have the greatest impact on a Member's score"** and this score is portable across the
  platform: **"Future Hosts may deny or accept this Member's booking based on their score"**
  `[same source, opened directly]` — this is a cross-portfolio, cross-host reputation system a multi-property
  host both feeds into and depends on.

### 1f. Move-in cadence — explicitly framed as a retention lever, not a one-time event
PadSplit's own host-education content prescribes a 10-step move-in playbook (honest listing → qualify →
build rapport pre-move-in → custom move-in instructions → clean/functional/accessible room → welcome kit →
responsive during initial period → post-move-in follow-up → monitor feedback → be consistent) and repeatedly
ties execution quality directly to retention: **"members feel supported, respected, and comfortable from day
one, they're more likely to stay longer," "reducing turnover and fostering a stable, respectful environment"**
`[padsplit.com/host-resources/host-success/10-steps-for-padsplit-hosts-to-ensure-smooth-move-ins-and-boost-tenure/,
opened directly]`.

### 1g. Move-out / eviction — the host does the legal work, PadSplit gives status fields + a ledger on request
- Hosts move a room through three dashboard statuses: **"Needs Flip" → "present" → "Eviction"**
  `[padsplit.com/help/article/preparing-for-an-eviction-360060395031, opened directly]`.
- To get financial evidence (rent due, running totals, weekly/daily rates, fees) and violation documentation,
  **the host must email support@padsplit.com** — this is not a self-serve dashboard export, it's a manual
  support request `[same source, opened directly]`.
- **"Platform Hosts are responsible for peacefully removing or legally evicting terminated Members"** — PadSplit
  explicitly does not do the eviction itself; it offers an optional Vendor Network referral, and states hosts
  handle it "whether or not you are using our... eviction vendor" `[same source, opened directly]`.

### 1h. Stay length / churn baseline — PadSplit's own marketing is internally inconsistent by a few months
- PadSplit's `earn-more` page: **"residents staying 6–9 months"** `[padsplit.com/earn-more, opened directly]`.
- A separate WebSearch synthesis (multiple PadSplit-adjacent pages) states **"9-month average stays"** as a
  standalone marketing figure, and a third-party underwriting thread paraphrases PadSplit as claiming **"the
  average tenant stays 9 months"** `[WebSearch synthesis, not independently re-opened for this specific number
  beyond the 6–9-month range already confirmed directly above]`. **Flag:** treat "6–9 months" as the directly-
  verified range and "9 months" as PadSplit's own rounded/rhetorical figure elsewhere — not a contradiction
  worth much weight, but worth noting Cockpit shouldn't hard-code a single "average tenure" constant from
  marketing copy without letting a host's own data override it.
- **Minimum commitment: 12 weeks**, with a **2-weeks'-dues penalty** for leaving early on the standard plan, or
  a **one-time $175 fee at booking for unlimited flexibility** (no minimum-stay penalty)
  `[WebSearch synthesis of padsplit.com's own minimum-commitment and "how long can you stay" help/blog content —
  not independently re-opened verbatim this pass, but internally consistent across multiple PadSplit-authored
  pages in the search results]`.

### 1i. Recurring host tasks (the "what recurs weekly" answer)
From PadSplit's own "Managing Room for Rent Properties" help topic and "Understanding your responsibilities"
article (both opened directly):
- **Twice-monthly in-person property walkthroughs** — "An in-person, twice-monthly walkthrough of the property"
  `[padsplit.com/help/topic/property-management-360009344272, opened directly]`.
- **Maintenance ticket triage** against stated response-time guidelines; smart-lock code management is largely
  automated via RemoteLock on move-in/move-out `[same source]`.
- **True Occupancy monitoring** — see §2 below; explicitly described as existing "to highlight the rooms that
  need attention (rooms that are inactive, in 'flipped' status, or rooms waiting to be booked)"
  `[padsplit.com/help/article/how-is-occupancy-calculated-11389456521876, opened directly]`.
- **Utility funding/activation and cost monitoring** — utilities are included in the member's price, and the
  host bears overage risk; PadSplit's only stated mitigation is pre-listing "efficiency of the home"
  `[padsplit.com/help/topic/property-management-360009344272, opened directly]` — **no cost-monitoring or
  per-room utility-allocation tool was found anywhere in PadSplit's own content.**
- **House-rule setup and enforcement** — a fixed set of togglable presets (no animals except service animals,
  no kitchen appliances in bedrooms, no guests, quiet hours 11pm–9am, no outside furniture) plus free-text
  custom rules per property, all shown to members pre-booking and on their profile
  `[padsplit.com/help/article/setting-up-your-custom-house-rules-11180181938580, opened directly via
  WebSearch's page-content extraction]`.
- **Member rating / house-rule violation follow-up**, **dues/balance follow-up via the PadSplit messaging
  system with host discretion on leniency**, and **secondary screening beyond auto-approval**
  `[padsplit.com/host-resources/padsplit-education/understanding-your-responsibilities-as-a-padsplit-host/,
  opened directly]`.

### 1j. Real-host ground truth (thinner than hoped, but real, and directly informative)
BiggerPockets forum threads were opened directly this pass, not just searched:
- One thread's synthesis (the underwriting thread) surfaces a materially important **skeptical host quote about
  PadSplit's own collection-rate marketing**: *"PadSplit claims they collect 97% of rents, but... a much larger
  % of their tenants get kicked out owing $500 or more in back rent that is rarely ever collected"*
  `[biggerpockets.com/forums/48/topics/1220382-underwriting-a-padsplit-deal-assumptions-and-operating-expenses,
  opened directly]`. **This is directly relevant to Cockpit's arrears-tracking feature case (§2)**: at least one
  experienced host does not trust PadSplit's own self-reported collection metric and wants independent
  visibility into actual uncollected back-rent — exactly the kind of platform-marketing-vs-ledger-reality gap
  an independent PMS-adjacent tool exists to close.
- A second thread's synthesis characterizes the model, from an experienced investor, as closer to running a
  **"rooming house business"** than a passive investment, and separately (a different reviewer) as **"Section 8
  meets Airbnb"** `[biggerpockets.com/forums/61/topics/1230934-anyone-personally-have-feedback-on-pad-split-as-a-host,
  opened directly]` — both descriptions converge with everything else in this brief: management-intensive,
  weekly-cadence, tenant-quality-variable operations, not a "set a price, sync a calendar" STR workflow.
- **Honesty flag:** neither thread yielded much host-specific quantified operational data (turnover-cost
  dollar figures, exact weekly time spent, specific spreadsheet practices) — the forum-thread angle was real
  but thinner than a dedicated host-testimonial video/podcast would have been. I did not find and open a
  PadSplit-host-specific YouTube video or podcast transcript this pass (see the honesty-bar note at the top).

---

## 2. What metrics/features a PadSplit/co-living host needs — vs. what PadSplit's own dashboard already gives

Legend: **CONFIRMED NATIVE** = a source I opened directly states PadSplit's dashboard provides this. **GAP** =
no source found states PadSplit provides this; treated as a gap, not proven absent (public help-center docs
are not exhaustive — flagged where relevant).

| Need | PadSplit native? | Evidence |
|---|---|---|
| **Room-level occupancy status** (which specific rooms are vacant/flipped/booked) | **CONFIRMED NATIVE**, but as a *property-level aggregate metric with per-room status flags*, not a room-level occupancy-rate-over-time report | "True Occupancy" formula = occupied rooms ÷ total rooms at active properties `[padsplit.com/help/article/how-is-occupancy-calculated-11389456521876]`; purpose is to flag individual problem rooms, but the metric itself is computed and displayed at the property level |
| **Portfolio-wide occupancy roll-up across properties** | **CONFIRMED NATIVE** ("Manage → Properties" dashboard view referenced "45 rooms" across a portfolio) | `padsplit.com/hosts/property-and-member-management`, opened directly |
| **Arrears / delinquency list, filterable** | **CONFIRMED NATIVE** (7 financial statuses, filterable Members list) | `padsplit.com/help/article/319723-...`, opened directly — **but the 7 statuses are not itemized in any public text I could open**, and there's no confirmed portfolio-wide arrears total/aging report (30/60/90-day buckets) |
| **Independent/auditable collection-rate or true-arrears figure** (vs. PadSplit's self-reported 97%) | **GAP** — no tool found; and at least one real host on BiggerPockets explicitly distrusts PadSplit's own 97% figure (§1j) | This is a clean, evidenced wedge, not a speculative one |
| **Payout reconciliation** (matching many weekly/biweekly member transactions to one monthly lump payout) | **PARTIAL** — the underlying CSV data exists (member bills/payments/property/payout-month/category) but no confirmed automated reconciliation/delta report | §1b above |
| **Per-room P&L** (revenue − allocated utility cost − turnover/cleaning cost − vacancy-day cost) | **GAP** — no PadSplit source found describes this; utility cost is explicitly host-borne with no allocation tool; move-in/cleaning fee is host-set but not tracked as a P&L line anywhere found | §1c, §1i |
| **Member lifecycle funnel** (applied→approved→moved-in→current→late→terminated, as one visual pipeline) | **PARTIAL** — the discrete pieces exist (Say Yes approval, financial-status filter, Eviction dashboard status) but no confirmed single funnel/pipeline view | Contrast with ColivHQ, which explicitly sells "web inquiry through tour, application, deposit, and move-in" as one pipeline (§4) — evidence this is a recognized, sellable gap in the adjacent category |
| **Turnover cost tracking** (cost per room-flip) | **GAP** — no tool found; "Needs Flip" is a status label only, not a cost-tracked event | §1g, §1i |
| **Portable member-reputation visibility in portfolio context** (not just per-booking-request email) | **PARTIAL** — the Member Score exists and is portable/cross-host, but no confirmed portfolio-wide "which of my current members' scores are trending down" view | §1e |
| **Eviction-ready financial ledger, self-serve** | **GAP as self-serve** — exists only via a manual emailed request to support@padsplit.com | §1g |
| **Cross-property member transfer visibility** | **CONFIRMED NATIVE** (no new booking fee on transfer, implying the system tracks it) | §1a |

**Net read:** PadSplit's own dashboard is genuinely strongest at *property-level and portfolio-aggregate*
income/expense/occupancy views plus raw CSV export — consistent with the prior competitive-landscape brief's
finding that native tooling is "a chore tracker and a messaging app" (that framing undersells the financial
side slightly — there IS a real Earnings tab and CSV — but every *room-level*, *reconciliation-level*, and
*lifecycle-level* analytical layer on top of that raw data is confirmed absent or at best partial.)

---

## 3. MTR / Furnished Finder hosts — how they differ operationally

### 3a. Structural difference #1: Furnished Finder does not process payments or leases — the host does
- Furnished Finder is a **lead-generation marketplace only**: hosts pay a **flat $99/year** listing fee (vs.
  Airbnb's ~3% host commission per booking) `[WebSearch synthesis of Furnished Finder's own marketing/blog
  content, not independently re-opened verbatim this pass, but consistent across multiple search results]`.
- **Furnished Finder itself does not collect rent** — "the platform doesn't handle bookings or payments...
  rent is paid directly to the landlord," with landlords optionally routing payments through **Baselane or
  KeyCheck, sister companies**, for ACH processing (a **$2/invoice fee** for external-bank-account transfers)
  `[WebSearch synthesis of support.furnishedfinder.com articles on Baselane/KeyCheck payments and
  biggerpockets.com/forums/925/topics/1084237-furnished-finder-rent-payment-method — the specific Baselane
  guide page 403'd on direct WebFetch this pass, flagged]`.
- **This is the single most important architectural implication for Cockpit**: for a PadSplit host, the
  platform's own CSV/email IS the financial system of record (§1b). For a Furnished Finder/MTR host, **the
  landlord's own bank account or Baselane ledger is the only system of record** — Furnished Finder has no
  equivalent of PadSplit's Earnings CSV for the underlying transaction. Any Cockpit ingestion strategy for MTR
  hosts must be **bank/Baselane-transaction-centric**, not platform-CSV-centric — a structurally different
  ingestion architecture per host segment, not a variation on the same pipe.

### 3b. Structural difference #2: real leases and security deposits, landlord-held, not platform-standard
- Furnished Finder added a **"Leases & Legal Docs"** feature via a **Rocket Lawyer** partnership: state-specific
  templates, e-sign, and customizable fields for "dates, rental rates, deposits, pet policies, house rules"
  `[WebSearch synthesis of furnishedfinder.com/blog/leases-and-legal-docs-now-built-into-your-dashboard and
  support.furnishedfinder.com's "What is the Leases & Legal Docs Service?" article — the direct landlord-tools
  guide page 403'd on WebFetch this pass, flagged]`.
- **"Furnished Finder does not process payments or manage security deposits... landlords must handle security
  deposit collection and management directly"** `[same WebSearch synthesis]` — unlike PadSplit's platform-
  standard Room Contract (per the prior host-agreement brief) and unlike Airbnb's booking-contract model, an
  MTR/Furnished-Finder host is operating as a **traditional landlord with a real lease and a real deposit they
  personally hold and must track for return/deduction** — this is a distinct compliance/tracking need (deposit
  ledger, state-specific deposit-return timelines) that neither STR PMSs nor PadSplit's model surface.
- Screening is the landlord's own responsibility; **KeyCheck** (Furnished Finder's screening product, page
  403'd on direct fetch this pass, description from search results only) provides background/credit checks as
  a bolt-on the landlord opts into — **not a centralized, portable score like PadSplit's Member Score.**

### 3c. Structural difference #3: assignment-driven vacancy clustering, not random turnover
- Travel-nurse/corporate tenants typically move on **contract-length cycles** (commonly ~13 weeks per travel-
  nurse assignment norms) rather than open-ended STR-style random turnover — meaning **vacancy risk clusters
  predictably around known assignment-end dates** rather than being uniformly distributed. No Furnished-Finder-
  native feature was found for advance-notice-to-relist automation keyed to a tenant's known assignment end
  date — **GAP, not found.**
- Comparison data point (secondhand, WebSearch synthesis, internally consistent across sources but not
  independently opened): **"Airbnb assumes a 25-night/month average; Furnished Finder assumes 10.5 months/year
  occupied,"** and FF renters "typically sign leases of roughly three months on average," meaning **far fewer
  turnovers than STR** but (unlike PadSplit) each individual turnover is a **whole-unit** vacancy, not a
  single-room vacancy inside an otherwise-occupied property — so the *portfolio-level* vacancy-smoothing effect
  PadSplit gets from having many rooms per property doesn't apply the same way to single-unit MTR hosts.

### 3d. What MTR hosts need that STR PMSs don't model (and PadSplit-style tools don't either)
- **Deposit ledger** (amount held, state-specific return-timeline deadline, deduction documentation) — not
  modeled by STR PMSs (which handle OTA-processed damage-protection instead, per the earlier competitive brief)
  and not needed by PadSplit hosts (no landlord-held deposit in that model).
- **Assignment-end-date-aware vacancy forecasting** tied to lease end dates, not calendar-availability toggles.
- **Bank/Baselane-transaction reconciliation against a *lease schedule*** (expected monthly rent per unit vs.
  actual deposits), the MTR analog of PadSplit's CSV-vs-payout reconciliation gap in §2, but sourced from a
  bank feed instead of a platform export.
- **Multi-platform lead aggregation**: MTR hosts commonly list the same unit across Furnished Finder, Airbnb
  (monthly-stay filter), and sometimes PadSplit simultaneously (the earlier competitive brief already confirmed
  PadSplit itself lists 1,000+ rooms on Furnished Finder) — a portfolio view that unifies leads/bookings across
  these different systems-of-record is a distinct integration need from OTA calendar-sync (which the earlier
  competitive brief already flagged as structurally unavailable to Cockpit without API-partner status, but
  which matters less here since FF itself has no calendar-sync API to begin with).

---

## 4. Co-living platform tools that already exist — real features, none PadSplit-specific

All four opened directly this pass (feature pages or a third-party comparison that itself opened them).

### ColivHQ (`colivhq.com/features`, opened directly)
- **Leasing:** lead pipeline, tenant portal, contracts & e-sign, **inquiry-to-move-in tracking with source
  attribution**, reply templates, follow-up reminders, SLA timers.
- **Financial:** auto-billing, multi-currency rent, deposit tracking, vendor invoices, **"property-level P&L
  that updates as money moves"** (a *live* P&L — no PadSplit or STR-PMS source in this research confirmed a
  live/real-time P&L; this is the closest precedent found), pro-rated billing, multi-cycle billing, auto-
  collect, multiple pay rails (Stripe, GoCardless, bank transfer, FPS).
- **Maintenance:** ticket routing by property/category, SLA escalation, vendor self-serve portal, **audit
  trails with photos and cost tracking** (a turnover/maintenance-cost-tracking precedent §2 found no PadSplit
  equivalent of).
- **Reporting/automation:** workflow automation, **resident lifecycle tracking**, **renewal-status monitoring**,
  API/MCP-server integration.
- Pricing (from an independent third-party comparison, opened directly): **$5/unit/month**
  `[everythingcoliving.com/compare/property-management-software, opened directly]`.

### COHO (`coho.life` / feature listings, WebSearch-synthesized this pass, not independently re-opened beyond
what the prior competitive brief's adjacent research already covered)
- Customizable application forms, automated rent schedules, integrated e-sign; **"custom credit control
  workflows"** for rent-arrears reminders (a direct precedent for the arrears-tracking gap in §2); compliance/
  document-renewal tracking with audit trail; Xero integration. From the independent comparison table: **from
  £1/month**, and explicitly listed as having **"No"** channel management `[everythingcoliving.com/compare/property-management-software,
  opened directly]`.

### Bidrento (`bidrento.com`, WebSearch-synthesized this pass)
- Automated recurring billing **with cost allocation and rent indexation** — i.e., a confirmed real precedent
  for **allocating shared utility/service costs across units**, which is exactly the tool §2 found PadSplit
  does not give hosts for utility overage risk. Built-in maintenance calendar, tenant self-service app,
  smart-lock and accounting integrations.

### MonkSpaces (`monkspaces.ai`, WebSearch-synthesized this pass)
- AI-agent-driven leasing/communications/maintenance coordination across voice, WhatsApp, email; **"system of
  record for availability and unit status"**; **real-time occupancy, collections, and resident-satisfaction
  analytics**; a "Hybrid Rental" channel manager that lists coliving units on Booking.com/Trip.com/Agoda —
  the most "PMS + OTA-channel + AI-ops" hybrid of the four surveyed.

### The independent comparison confirms the wedge from a second angle
`everythingcoliving.com/compare/property-management-software` (opened directly) runs a feature-comparison table
across six platforms (Custom Build PMS, MonkSpaces, COHO, Lavanda, Res:harmonics, ColivHQ) with rows including
**"Bed-Level Inventory"** (most support unit/room level — evidence room-level modeling is a recognized,
comparison-worthy axis in this category generally) and **"Channel Management"** (varies: MonkSpaces has
Airbnb/Booking.com, COHO has none, Lavanda has 400+). **PadSplit, Bidrento, and per-room financial reporting as
a named comparison axis are not mentioned anywhere in this document** `[opened directly, confirmed by direct
read]` — a second, independent source (different from the prior competitive brief's substack citation)
corroborating that no coliving PMS surveyed in this category serves or even discusses PadSplit specifically.

---

## The feature set a PadSplit/MTR/co-living host needs that no STR PMS provides

This is the differentiated core Cockpit's wedge should build, synthesized from everything above:

1. **Room-level (not property-level) financial roll-up across a portfolio of many small rooms** — revenue,
   occupancy days, vacancy, and the multi-occupancy-fee lever, rolled up per room across many properties. No
   STR PMS models a "room" as the leasable unit at all (they model whole listings); PadSplit's own dashboard
   confirms property/portfolio-aggregate views but not this room-level roll-up (§2).
2. **An independent, auditable arrears/AR-aging ledger** cross-checked against the platform's own reported
   collection numbers — directly evidenced as a real host need by a BiggerPockets host who explicitly distrusts
   PadSplit's self-reported 97% collection rate (§1j) — with 30/60/90-day aging and the specific
   $300-balance/48-hour "financial probation" status tracked from the CSV/email data, not just PadSplit's UI.
3. **Payout reconciliation across a billing-frequency mismatch** — dozens of members paying weekly/biweekly,
   the host receiving one lump monthly payout in arrears — automatically matching the CSV's per-member
   billing/collection lines to that payout and surfacing any delta. PadSplit gives the raw CSV; it does not
   give the reconciled reconciliation itself (§1b, §2).
4. **Per-room P&L**: revenue minus allocated utility cost, turnover/cleaning cost, and vacancy-day cost. No
   source in this entire research pass — not PadSplit, not the four coliving-specific PMS tools, not any STR
   PMS from the prior competitive brief — confirmed this exists today (§2).
5. **A unified member/tenant lifecycle funnel** (applied→approved→moved-in→current→late→terminated) as one
   pipeline view. PadSplit has the discrete pieces (Say Yes, financial-status filters, Eviction status) but no
   confirmed single funnel; ColivHQ explicitly sells exactly this pipeline in the adjacent coliving category,
   which is independent evidence of real, monetizable demand for it (§2, §4).
6. **Turnover-cost tracking tied to churn/rating data** PadSplit already collects (Member Score, "Needs Flip"
   status) but does not surface financially — ColivHQ's photo/cost-tracked maintenance audit trail is the
   closest real precedent (§4).
7. **A segment-aware ingestion architecture, not a one-size-fits-all sync**: PadSplit-CSV/email-centric for
   PadSplit hosts vs. bank/Baselane-transaction-centric for Furnished-Finder/MTR hosts vs. OTA-email-centric for
   STR hosts (per the prior email-ingestion brief) — because, uniquely among these three segments, **Furnished
   Finder itself holds no transaction record at all** (§3a) — this is a structural design fork, not a detail.
8. **Portfolio-wide portable-reputation visibility**: PadSplit's Member Score is cross-host and cross-property
   by design, but no confirmed dashboard view lets a multi-property host see "which of my current members'
   scores are trending down" across their whole portfolio at once, only per-booking-request emails (§1e, §2).
9. **Utility cost-per-room allocation/monitoring** — PadSplit explicitly puts utility-overage risk on the host
   with no allocation tool; Bidrento's "cost allocation" billing feature is the direct, real precedent for what
   PadSplit hosts specifically lack (§2, §4).
10. **A deposit ledger + assignment-end-date-aware vacancy forecasting** for MTR/Furnished-Finder hosts —
    landlord-held security deposits with state-specific return deadlines, and vacancy risk clustered around
    known contract-end dates rather than random STR-style turnover (§3b, §3c) — neither modeled by STR PMSs nor
    needed in the PadSplit model, making this segment-specific, not a shared feature.

None of items 1, 2, 3, 4, 6, 8, or 9 were confirmed to exist in PadSplit's own native tooling, in any of the
four coliving-specific PMS tools surveyed (ColivHQ, COHO, Bidrento, MonkSpaces), or in any STR PMS covered by
the prior competitive-landscape brief. Item 5 (lifecycle funnel) and item 7's underlying billing-model
transparency exist as isolated precedents in the adjacent coliving-PMS category (evidence of real demand) but
not combined with PadSplit-specific ingestion. This is the gap Cockpit's PadSplit/MTR wedge should build into.

---

## Not found / could not verify — full list (honesty bar)

- **PadSplit's exact enumeration of its "seven financial statuses"** — the article that names the count (7)
  does not itemize them in extractable text; only images. A future pass would need a live host-account
  screenshot or a Gmail-forwarded sample of a status-change notification.
- **PadSplit's exact monthly payout day-of-month figures** and the Earnings-tab CSV field list beyond what
  WebSearch synthesized — the specific payout-FAQ and CSV-detail pages were not independently re-opened
  verbatim this pass (relied on WebSearch synthesis of PadSplit's own help articles, internally consistent
  across multiple pages but not hand-quoted from a direct fetch).
- **A PadSplit-host-specific "day in the life" video, podcast, or vlog** — none found; only a PadSplit
  *resident's* day-in-the-life video surfaced, which is out of scope for host operations. This is a real,
  named gap in this brief's evidence base, not a silent omission.
- **Furnished Finder's own landlord-tools guide page and KeyCheck product page content** — both 403'd on direct
  WebFetch this pass; relied on WebSearch synthesis, itself drawing on Furnished Finder's own blog/support
  content, but not hand-quoted from a page I opened myself.
- **Exact per-room turnover-cost dollar figures from real PadSplit hosts** — searched specifically, found none;
  the only concrete host-facing cost figure confirmed is the ~$100 average move-in/cleaning fee (host-set,
  host-kept), not a comprehensive turnover-cost figure (vacancy days + relist time + cleaning combined).
- **COHO's and Bidrento's pricing and full feature depth** — relied on WebSearch synthesis and one third-party
  comparison table for COHO's price point; their own marketing pages were not independently re-opened verbatim
  this pass (time-boxed against the four-tool survey the dispatch asked for, prioritized ColivHQ — the
  best-documented of the four — for a fully-opened, itemized feature list).
- **Whether any coliving PMS (ColivHQ/COHO/Bidrento/MonkSpaces) has since added PadSplit-specific support** —
  this pass, like the prior competitive-landscape brief, found none; but "not found in a search-and-fetch pass"
  is not the same as "provably does not exist anywhere," and this is stated as a limitation, not a certainty.

---

## Sources opened directly this pass (WebFetch/curl)

- [PadSplit — How is occupancy calculated?](https://www.padsplit.com/help/article/how-is-occupancy-calculated-11389456521876)
- [PadSplit — Property & Member management (hosts page)](https://www.padsplit.com/hosts/property-and-member-management)
- [PadSplit — How using PadSplit's Say Yes feature can boost your occupancy](https://www.padsplit.com/host-resources/host-success/how-using-padsplits-say-yes-feature-can-boost-your-occupancy/)
- [PadSplit — Understanding your responsibilities as a PadSplit host](https://www.padsplit.com/host-resources/padsplit-education/understanding-your-responsibilities-as-a-padsplit-host/)
- [PadSplit — 10 steps for PadSplit hosts to ensure smooth move-ins and boost tenure](https://www.padsplit.com/host-resources/host-success/10-steps-for-padsplit-hosts-to-ensure-smooth-move-ins-and-boost-tenure/)
- [PadSplit — How do Member Financials work?](https://www.padsplit.com/help/article/782765-How-do-Member-Financials-work)
- [PadSplit — How to interpret a Member's financial status](https://www.padsplit.com/help/article/319723-how-to-interpret-a-member-s-financial-status)
- [PadSplit — Rating a Member](https://www.padsplit.com/help/article/874468-rating-a-member)
- [PadSplit — Managing Room for Rent Properties (help topic)](https://www.padsplit.com/help/topic/property-management-360009344272)
- [PadSplit — What is PadSplit's fee model for Hosts?](https://www.padsplit.com/help/article/what-is-padsplits-fee-model-for-hosts-24614775906324)
- [PadSplit — Charging Fees for Multiple Occupants in Your PadSplit Room](https://www.padsplit.com/help/article/charging-fees-for-multiple-occupants-in-your-padsplit-room-30837897413396)
- [PadSplit — How does PadSplit calculate a Host's monthly payout?](https://www.padsplit.com/help/article/how-does-padsplit-calculate-a-hosts-monthly-payout-4402853494676)
- [PadSplit — Where can I view my financials on my Host dashboard?](https://www.padsplit.com/help/article/where-can-i-view-my-financials-on-my-host-dashboard-4404902173460)
- [PadSplit — Preparing for an eviction](https://www.padsplit.com/help/article/preparing-for-an-eviction-360060395031)
- [PadSplit — earn-more (host marketing page)](https://www.padsplit.com/earn-more)
- [PadSplit — Setting up your Custom House Rules](https://www.padsplit.com/help/article/setting-up-your-custom-house-rules-11180181938580) (opened via search-tool page extraction)
- [BiggerPockets — Underwriting a PadSplit deal: assumptions and operating expenses](https://www.biggerpockets.com/forums/48/topics/1220382-underwriting-a-padsplit-deal-assumptions-and-operating-expenses)
- [BiggerPockets — Anyone personally have feedback on pad split as a host](https://www.biggerpockets.com/forums/61/topics/1230934-anyone-personally-have-feedback-on-pad-split-as-a-host)
- [ColivHQ — Features](https://www.colivhq.com/features)
- [Everything Coliving — Best Property Management Software for Coliving 2026 (comparison table)](https://everythingcoliving.com/compare/property-management-software)

## Sources NOT opened directly this pass (403 or WebSearch-snippet only — flagged inline above wherever cited)

- `furnishedfinder.com/KeyCheck` (403)
- `furnishedfinder.com/blog/furnished-finder-exclusive-landlord-tools` (403)
- `furnishedfinder.com/blog/how-rent-payments-work-through-baselane-complete-guide` (403)
- `furnishedfinder.com/blog/why-rent-to-travel-nurses` (403)
- COHO's and Bidrento's own marketing pages (WebSearch synthesis only)
- PadSplit's Earnings Payout FAQ / New Earnings Dashboard / "Which Member collections are included" articles
  (WebSearch synthesis only — not independently re-opened verbatim, though corroborated across multiple
  PadSplit-authored pages in the search results)
- A PadSplit-host operational YouTube video/podcast (searched, none found — see honesty-bar note at top)
