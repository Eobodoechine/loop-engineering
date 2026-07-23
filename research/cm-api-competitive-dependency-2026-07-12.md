# Cockpit — is CM-API ingestion a form of "depending on a competitor"? 2026-07-12

Mode D domain brief. Companion to [str-data-ingestion-strategy-2026-07-11.md] and
[cm-api-integration-2026-07-11.md], which recommended building Cockpit's STR data layer on
Hostaway/Hospitable/OwnerRez public APIs. This brief tests that recommendation against the product
owner's explicit constraint: "we would want to not have Hostaway as our layer as we are their
competitor, but if there was a way to circumvent that, I would like that." All sources below were
opened directly (curl/WebFetch) and the quoted text was independently grepped from the fetched page,
not taken on a WebSearch snippet's word, except where marked SECONDARY.

## Bottom line

**No — a host-consented CM-API integration is not categorically different from depending on a
competitor as infrastructure; it is the SAME dependency with a legal-consent wrapper, and two of
the three vendors' own contracts explicitly name and restrict this exact scenario.** Hostaway's
Terms of Service ban "the Customer" from using its API "for competing services." Hospitable's
Subscription Agreement bans "a direct competitor" from accessing its Services (defined to include
the API) "except with Hospitable's prior written consent," and Hospitable's own support docs tell
hosts not to hand their API token to "trusted vendors." OwnerRez requires a "partnership agreement"
with a direct competitor before that competitor's app can even query Listings. Framing the
integration as one of several parallel ingestion adapters (not the sole data layer) is still the
right architecture — it bounds the blast radius to one host segment — but it does not eliminate the
dependency for that segment: those hosts' Cockpit service remains fully gated by a rival PMS's
unilateral, no-notice-required discretion.

---

## Q1 — Do Hostaway/Hospitable/OwnerRez's own terms restrict a competing PMS from reading a mutual
customer's data via their API?

**Answer: Yes, all three — by three different mechanisms, each independently verified by opening
and grepping the actual document text (not summarized by an intermediary model).**

### Hostaway — contractual prohibition on the host, enforced by unilateral revocation
Source: `https://www.hostaway.com/terms/` (fetched via curl, HTML stripped, grepped directly).

> **Section 3.3**: "Except as explicitly permitted in these Terms, the Customer may not use the
> Hostaway Service or the Documentation to offer services to any third party or otherwise transfer
> the Hostaway Service or the Documentation or allow access to the Hostaway Service or the
> Documentation to any third party or allow any third party to benefit from the Hostaway Service or
> the Documentation. There are no implied licenses."

> **Section 9 (API)**: "The Supplier provides the Customer with a non-exclusive, non-transferable,
> and revocable license to access and utilize the Hostaway API for integrating the Hostaway Service
> with the Customer's systems and data. The Customer is required to safeguard their API key,
> ensuring confidentiality, and must not surpass rate limits or use the API for competing services
> or illegal purposes. The Customer agrees to adhere to data protection laws, and to discontinue API
> use and erase any retrieved data if the Supplier terminates access at their sole discretion. The
> API is offered 'as-is' without any warranties."

The bound party is "the Customer" — i.e. the host who signed up for Hostaway, not Cockpit (no
privity between Hostaway and Cockpit in the self-serve-key model the 2026-07-11 research
recommended). But that means: a host who mints their own Hostaway API key and hands it to Cockpit —
exactly the flow the prior research designed — puts **the host** in direct breach of Section 9
("must not... use the API for competing services") and arguably Section 3.3 too. Hostaway's remedy
is explicit: **revoke "at their sole discretion"** and require the host to **"erase any retrieved
data"** — meaning Cockpit could be ordered (via the host, or directly by Hostaway pursuing the host)
to delete its copy of that host's data.

### Hospitable — an explicit "direct competitor" consent gate that names this exact case
Source: `https://hospitable.com/subscription-agreement/` (fetched via curl, HTML stripped, grepped
directly).

> **Section 2.7**: "You may not access the Services if You are a direct competitor of the
> Hospitable, except with Hospitable's prior written consent. You may not access the Services for
> the purposes of monitoring performance, availability, functionality, or for any benchmarking or
> competitive purposes."

"Services" is defined earlier in the same document to include "the applicable Software, Updates,
**API**, Documentation, and all applicable Associated Services" — so 2.7 explicitly covers API
access, not just the web UI. "You"/"Subscriber" is whoever accepts the agreement, which also covers
anyone "authorizing or permitting any Agent to access or use a Service" per the preamble.

> **Section 8.4** (enforcement): "We reserve the right to modify, suspend or terminate the Services
> (or any part thereof), Your Account or Your and/or Agents' or End-Users' rights to access and use
> the Services, and remove, disable and discard any Service Data if We believe that You, Agents or
> End-Users have violated this Agreement."

Separately, Hospitable's own support documentation is even more direct about the exact mechanism the
prior research proposed (host mints a Personal Access Token and hands it to Cockpit):

Source: `https://help.hospitable.com/en/articles/8609392-accessing-the-public-api-with-a-personal-access-token-pat`
(fetched via curl, HTML stripped, grepped directly — this page returned HTTP 200 and was NOT the
JS-blocked Stoplight SPA the prior research hit).

> "🔑 Personal access tokens, like the name suggests, are for personal access only. **Integrating
> partners are expected to implement OAuth in order to gain authorized access to customer account.
> Please do not share your personal access token with anybody, even trusted vendors.**"

This directly contradicts the PAT-sharing flow the 2026-07-11 research assumed as Cockpit's fast,
self-serve Hospitable integration path — Hospitable's own docs tell the host not to do it, and route
any real "integrating partner" (i.e., an app like Cockpit serving many Hospitable hosts) to the OAuth
vendor flow, which requires **requesting vendor client credentials via a form and Hospitable's
approval** (corroborated by `developer.hospitable.com`'s Authentication/Partner Portal pages, which
are JS-rendered Stoplight SPAs I could not open directly — that specific approval-process detail is
SECONDARY, sourced from WebSearch result summaries, not independently opened). Since Hospitable is
Cockpit's direct competitor under Section 2.7, that approval step is a live veto point, not a
formality.

### OwnerRez — a hard technical + business gate on the exact data Cockpit needs
Sources: `https://www.ownerrez.com/support/articles/privacy-security-terms-of-service`,
`.../api-overview`, `.../api-oauth-app` (all fetched via curl, HTML stripped, grepped directly).

> **Universal Terms 5.3**: "You agree not to access (or attempt to access) any of the Services by
> any means other than through the interface OwnerRez provides **unless you have been specifically
> allowed to do so in a separate agreement with OwnerRez.**"

> **api-overview / api-auth**: "Note that the token-based API authentication is intended for
> **private usage**, and is **not designed for partner use or wide deployment**. If you are a
> partner wishing to offer your services to OwnerRez clients in general, you need to use our more
> robust and secure OAuth API authentication."

> **api-oauth-app FAQ**: "Why can't I query Listing endpoints? **Listing endpoints requires a
> partnership agreement between your business and OwnerRez.** To gain access, please contact us at
> partnerhelp@ownerrez.com with the subject line Listing Endpoints Access." Also: "If you are
> building an OAuth app that you plan to market to others, Message webhooks require a partnership
> agreement between your business and OwnerRez."

This is the most concrete gate of the three: OwnerRez's **Listings endpoint — the core property data
any PMS needs — is contractually locked behind a partnership agreement with OwnerRez itself**, not
merely a ToS clause Cockpit could technically route around via a host's PAT. A single-host PAT works
for "private usage" only; anything that looks like a product serving many OwnerRez hosts needs
OwnerRez's sign-off.

### Net read on Q1
All three vendors anticipated and wrote language for exactly this scenario (a competing PMS reading
a mutual customer's data via the API). They differ in mechanism, not in intent:
- **Hostaway**: contract-only restriction on the host, backed by a unilateral, no-cause,
  no-notice-required kill switch + mandated data deletion. No live technical gate today.
- **Hospitable**: contract restriction on "direct competitors" that explicitly covers the API,
  PLUS a documented instruction not to share PATs with vendors, PLUS a real approval gate (OAuth
  vendor registration) for any usage beyond one self-use PAT.
- **OwnerRez**: contract restriction AND a technical/business approval gate on the specific
  endpoints (Listings, Messaging) a PMS actually needs.

---

## Q2 — Real-world precedent: non-PMS tools reading CM data, and how they're positioned

**Answer: Yes, abundant precedent exists — but it is precedent for narrow-vertical tools, not for a
competing full PMS, and that distinction is exactly why those integrations survive.**

- **PriceLabs (dynamic pricing)** — positions itself as "PMS-agnostic but deeply integrated,"
  described as "one of the few non-PMS platforms globally" to hold Booking.com Connectivity Partner
  certification, integrating with 160+ PMS/CMs. Crucially, **Hospitable's own integrations page**
  (`https://hospitable.com/integrations`, fetched via curl, grepped directly) lists "PriceLabs
  Dynamic Pricing" and "Beyond Dynamic Pricing" as partner integrations *side by side* with
  Hospitable's own competing built-in feature: "Hospitable's built-in Dynamic Pricing engine is
  included in every plan and can adjust your nightly rates automatically based on demand
  fluctuations, competition, and seasonality." The page's own tagline: "**Works with the tools you
  already use** — Hospitable makes it easy to connect the tools that power your short-term rental
  business. From dynamic pricing and smart locks to marketing, accounting, and direct bookings."
  Hospitable lists at least 6 dedicated pricing-tool partners (Beyond, DPGO, Homesberg, PriceLabs,
  Rankbreeze, Rategenie, Wheelhouse) that compete head-on with its own native pricing feature — real
  proof that feature-level overlap alone does not trigger the "direct competitor" clause in
  practice, as long as the integrator isn't a competing full PMS.
- **Turno (cleaning/task management)** — connects via the same self-serve API-key pattern Cockpit
  planned: per Hostaway's own support doc "How to connect to Turno?", a host logs into Turno,
  pastes their "Hostaway API Token/Key" and "Hostaway Account ID." Turno is listed in Hostaway's own
  Marketplace (`hostaway.com/marketplace/turno/`). Turno is not a PMS.
- **Accounting tools**: Hostaway's own official QuickBooks Online integration (`get.hostaway.com/quickbooks-integration/`,
  $8/month/listing, changelog.hostaway.com); **VRPlatform** (QuickBooks/Xero/Sage Intacct) — quote
  verified via WebFetch of `vrplatform.app/integrations/hostaway`: "VRPlatform integrates Hostaway
  with QuickBooks Online to automate short-term rental accounting..."; **Clearing** (trust
  accounting) — quote independently verified via WebFetch of
  `getclearing.co/blog-posts/clearing-integration-hostaway-simplify-vacation-rental-finances`: "By
  connecting Clearing's robust financial management platform with **Hostaway's leading property
  management software**, we simplify the way vacation rental businesses handle their finances,"
  and "Key transaction details, booking information, and property data from Hostaway seamlessly
  transfer to Clearing..." Clearing explicitly calls Hostaway "leading property management
  software" and positions itself purely as the financial layer underneath it.

**The pattern across every verified example**: none of these products are a competing full PMS.
Each occupies one narrow vertical (pricing, cleaning ops, bookkeeping) and its public positioning
always explicitly defers "PMS" status to the host's existing Hostaway/Hospitable/OwnerRez account.
That's the structural reason they keep stable, long-lived API access even when (PriceLabs) they
compete on one specific feature — they never ask the host to leave the CM, only to bolt something on
top of it.

---

## Q3 — What happens to Cockpit's data pipe if the host cancels their CM subscription?

**Answer: Access is not owned by the host or by Cockpit — it is a revocable privilege tied to an
active, paid, compliant CM account, and all three vendors' own language says access (and
potentially the underlying data) can be cut at the vendor's discretion, without notice.**

- **Hostaway ToS Section 9** (verified quote above) frames the API grant itself as "a
  non-exclusive, non-transferable, and **revocable** license," and mandates the Customer "discontinue
  API use and erase any retrieved data if the Supplier terminates access **at their sole
  discretion**."
- **Hospitable Subscription Agreement Section 8.4** (verified above): on any believed violation,
  Hospitable can "suspend or terminate the Services... and **remove, disable and discard any
  Service Data**" — not just cut off future API calls, but delete what's stored on their side.
  Separately (established in the prior 2026-07-11 research, CONFIRMED): the public API is gated to
  paid tiers above Essentials, so a host who downgrades (short of full cancellation) can also lose
  API access.
- **OwnerRez Universal Terms Section 4.4** (verified above): "You acknowledge and agree that if
  OwnerRez disables access to your account, you may be prevented from accessing the Services, your
  account details, or any files or other content that is contained in your account." Section 4.3
  (verified, same fetch): "OwnerRez may stop (permanently or temporarily) providing the Services...
  to you or users generally **at OwnerRez's sole discretion without prior notice to you.**"
- **Hostaway cancellation mechanics** (SECONDARY — support.hostaway.com returned HTTP 403 to both
  WebFetch and curl; this is a WebSearch-result summary, not independently opened): reportedly a
  host must manually delete all listings/units before an up-to-30-day deactivation completes, and
  "this data will be permanently lost after deactivation." Flagged as unverified-primary; consistent
  in direction with the other two vendors' verified language but not independently confirmed.

**Direct answer to the question as asked: yes, real dependency risk.** If a host cancels, downgrades,
or lapses on payment — or if the CM decides the connection itself violates their ToS (the Section 9 /
2.7 / partnership-agreement language above) — Cockpit's data pipe for that host goes dark, at the
vendor's sole discretion, with no contractual notice requirement, and Cockpit may have no
contractual right to retain a cached copy of what it already ingested.

---

## Q4 — Does "one of several parallel adapters" framing eliminate the competitive-dependency concern?

**Answer: It is the right architecture, and it materially bounds the blast radius — but it does not
eliminate the dependency for the CM-sourced host segment specifically. A meaningful residual risk
remains, grounded in the facts above, not merely asserted:**

1. **The legal exposure is per-host and contract-level, not architectural.** Whether Cockpit treats
   the CM-API connector as its sole ingestion path or as 1-of-5 adapters, each individual connected
   host is still, in the vendor's own words, doing something the vendor's contract forbids
   ("must not... use the API for competing services" — Hostaway 9; "may not access the Services if
   You are a direct competitor... except with prior written consent" — Hospitable 2.7; "requires a
   partnership agreement" — OwnerRez). Portfolio diversification changes what fraction of Cockpit's
   *total* business is exposed; it does not change whether *that* host's connection is exposed.
   Multi-CM support diversifies **which** vendor might revoke — it does not remove any single
   vendor's ability to revoke.
2. **The verified real-world precedent (Q2) is not actually analogous to Cockpit's situation.**
   PriceLabs, Turno, Clearing, VRPlatform, and QuickBooks all survive specifically *because* they are
   not a competing full PMS — none of the "direct competitor" / "competing services" language was
   written with them in mind, and their public positioning actively signals that ("Hostaway's
   leading property management software," in Clearing's own words). Cockpit, as a full PMS
   competitor, is precisely the entity Hostaway Section 9 and Hospitable Section 2.7 name. Internally
   labeling the CM-API connector as "one adapter among several" is an architecture decision Cockpit
   makes for itself; it is invisible to Hostaway/Hospitable/OwnerRez, who evaluate the connecting
   *application's* nature (a rival PMS), not how Cockpit privately weights that data source in its
   own ingestion portfolio.
3. **Discovery/enforcement risk scales with Cockpit's success, not its architecture.** A CM is more
   likely to notice and act on a channel that is visibly growing (a public "connect your Hostaway
   account" marketing page, support-ticket volume mentioning Cockpit, PAT-usage patterns at scale)
   than one that is small. If the CM-API adapter is the *only* onboarding path for that specific host
   segment (even though it's "one of several" at the whole-product level), losing it removes those
   hosts' entire reason to be Cockpit customers — the parallel-adapters framing protects Cockpit's
   *aggregate* business (other segments keep working) but does not protect the *CM-sourced cohort*
   from a full, no-notice outage if a vendor enforces.

**Recommendation implied by the sources, stated as a recommendation, not a fact:** keep the
multi-adapter architecture (CM-API + iCal + email-parse + CSV + PadSplit-specific, as the prior
research already proposed) precisely because it bounds blast radius — that part of the prior plan is
still correct. But do not present the CM-API path to Nnamdi or the product owner as "circumventing"
the competitor-dependency concern; it does not. It is the same dependency, narrowed to a smaller
share of the business and wrapped in the host's informed consent, which is a real and valuable
mitigation (it's authorized, gets full financials/webhooks, and isn't fragile scraping) — but the
underlying fact pattern (Cockpit's ability to serve those hosts is 100% gated by a rival PMS's
unilateral, revocable-at-will tolerance) is unchanged, and two of the three vendors' own contracts
say so explicitly.

**One flag beyond the research brief's scope:** whether Hostaway/Hospitable/OwnerRez could pursue
Cockpit itself (not just the host) for inducing/facilitating breach of the host's own ToS at
product scale (tortious interference / unfair competition theories) is a real legal question raised
by the "may not... allow access... to any third party or allow any third party to benefit" language
in Hostaway 3.3 and the OAuth-vendor-approval gates in Hospitable/OwnerRez — but it is a legal
determination, not something this research can resolve. This needs actual counsel review before
Cockpit markets a "connect your Hostaway/Hospitable/OwnerRez account" feature at any scale.

---

## Sources (all opened directly; method noted per source)

- `https://www.hostaway.com/terms/` — fetched via curl, HTML→text, grepped. Sections 3.3, 9 quoted.
- `https://hospitable.com/subscription-agreement/` — fetched via curl, HTML→text, grepped. Sections
  2.7, 8.4, and the Services/Agent definitions quoted.
- `https://help.hospitable.com/en/articles/8609392-accessing-the-public-api-with-a-personal-access-token-pat`
  — fetched via curl (HTTP 200), HTML→text, grepped. PAT "personal access only" / "do not share...
  even trusted vendors" quoted.
- `https://hospitable.com/integrations` — fetched via curl, HTML→text, grepped. Dynamic Pricing
  category + built-in-vs-partner language quoted.
- `https://www.ownerrez.com/support/articles/privacy-security-terms-of-service` — fetched via curl,
  HTML→text, grepped. Universal Terms 4.3, 4.4, 5.3, 12.x quoted.
- `https://www.ownerrez.com/support/articles/api-overview`,
  `https://www.ownerrez.com/support/articles/api-oauth-app` — fetched via curl, HTML→text, grepped.
  "Private usage... not designed for partner use," Listing-endpoint partnership-agreement FAQ quoted.
- `https://www.getclearing.co/blog-posts/clearing-integration-hostaway-simplify-vacation-rental-finances`
  — opened via WebFetch, positioning quotes extracted from the fetched article body.
- `https://www.vrplatform.app/integrations/hostaway` — opened via WebFetch, positioning quote
  extracted from the fetched page body.
- `https://support.hostaway.com/hc/en-us/articles/1260802680490-How-to-connect-to-Turno` and
  `https://www.hostaway.com/marketplace/turno/` — surfaced via WebSearch; Turno's "paste your
  Hostaway API Token/Key + Account ID" mechanism corroborated by the prior 2026-07-11 research's
  independently-confirmed self-serve-key auth model, not re-opened this pass.

## Not found / could not verify

- **Hostaway's own cancellation-mechanics page** (`support.hostaway.com/hc/en-us/articles/14006214140699`
  and the cancellations *section* index) returned HTTP 403 to both WebFetch and direct curl
  (Zendesk bot-blocking). The "must delete all listings first, data permanently lost after
  deactivation, up to 30-day process" claim is SECONDARY (WebSearch snippet only) and flagged as
  such above — directionally consistent with OwnerRez/Hospitable's verified termination language,
  but not independently opened.
- **Hospitable's Partner Portal / vendor-OAuth-approval process detail** (`developer.hospitable.com`)
  is a JS-rendered Stoplight SPA; curl and WebFetch both returned only the "Please enable
  Javascript" shell (114 bytes), matching the prior 2026-07-11 research's same finding. The
  "request vendor client credentials via a form, response in a few days" detail is SECONDARY
  (WebSearch summary), not independently opened.
- **No real-world example found of a full competing PMS building its live, ongoing production
  ingestion on a rival PMS's API** (as opposed to a one-time data-export/migration tool). Searched
  directly for this; results returned only migration/import tooling (Rentvine, generic "avoid
  lock-in" content) — not a sustained-dependency case study. This is the load-bearing negative
  result for Q4: the precedent that exists (Q2) is for narrow-vertical non-PMS tools, and there is
  no verified precedent for Cockpit's specific situation (a competing full PMS as the client).
  Absence of a precedent is not proof it's impossible — it may simply be rare/undisclosed — but it
  means Cockpit cannot point to "X did this and it worked" as reassurance.
- **Whether Hostaway/Hospitable/OwnerRez have ever actually enforced these clauses against a
  competing PMS in practice** (vs. simply having the contract language on file) — not researched
  this pass; would need a search of litigation records, industry forum discussion, or direct
  outreach to the vendors' BD teams, none of which were in scope here.
- **Legal enforceability / tortious-interference exposure for Cockpit itself** (as opposed to the
  host) — explicitly flagged above as a legal question this research cannot resolve; needs counsel.
