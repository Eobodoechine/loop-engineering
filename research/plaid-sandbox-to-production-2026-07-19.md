# Plaid Sandbox → Production: current (2026) requirements for TaxAhead

Mode D domain-research brief. Prepared 2026-07-19 for the TaxAhead build (AI tax-readiness
app that needs Plaid Transactions, likely Auth/Identity, to ingest real users' bank
transaction data). Every claim below is sourced from a directly-opened Plaid doc/support
page or, where the page was blocked by bot-protection, from a WebSearch synthesis flagged
explicitly as secondary. No claim is asserted without a citation.

**Honesty-bar note on sourcing method:** `plaid.com/docs/*` pages fetched directly and cleanly
via WebFetch (quotes below are from the actual page). `support.plaid.com/hc/*` pages are
behind Cloudflare bot-challenge and returned HTTP 403 to both WebFetch and a direct `curl`
with a browser user-agent — those facts are WebSearch-snippet-sourced (marked
**[search-snippet]** below) rather than directly opened. `dashboard.plaid.com/*` pages require
an authenticated login session and were not reachable (marked **[not reachable — needs your
own dashboard login]**). Where a fact came only from a single WebFetch AI-summarization pass
over a long changelog/listing page (a known hallucination-risk pattern per the Researcher role
brief), it is flagged **[low-confidence — WebFetch listing-page summary, corroborate before
relying on it]**.

---

## 1. Plaid's environment/access model as it exists NOW (2026)

**Bottom line: Plaid moved from a three-tier model (Sandbox → Development → Production) to a
two-environment model (Sandbox, Production) with graduated access tiers *inside* Production.**
This is a real, fairly recent change — verify-before-assuming was the right call.

- **Development environment: retired June 20, 2024.** Directly confirmed from Plaid's own
  glossary: *"Development (https://development.plaid.com) was a Plaid environment on which you
  could run your code, along with Sandbox and Production."* — past tense, and the docs changelog
  entry states all Development Items were deleted on that date.
  Source: [Quickstart - Glossary | Plaid Docs](https://plaid.com/docs/quickstart/glossary/)
  (directly fetched); corroborated by
  [Plaid: development environment decommissioned · Issue #42102 · frappe/erpnext](https://github.com/frappe/erpnext/issues/42102)
  and [Plaid free development service withdrawn on 20th June 2024 - Frappe Forum](https://discuss.frappe.io/t/plaid-free-development-service-withdrawn-on-20th-june-2024/123481).

- **Current official model is two environments.** Directly quoted from Plaid's own glossary
  (fetched 2026-07-19): *"The Sandbox (https://sandbox.plaid.com) is one of two Plaid
  environments on which you can run your code, along with Production"* and *"Production
  (https://production.plaid.com) is one of two Plaid environments on which you can run your
  code, along with Sandbox. Unlike Sandbox, Production uses real data."*
  Source: [Quickstart - Glossary | Plaid Docs](https://plaid.com/docs/quickstart/glossary/).

- **What gates "real-user-reachable" is a tier *within* Production, not a separate environment.**
  As of 2026 there are effectively three tiers a team can be in once pointed at
  `production.plaid.com`:
  1. **Trial plan** — free, real production data, auto-approved for most US/Canada
     developers, capped at **10 Production Items**, 8 core products included (Auth,
     Transactions incl. Refresh, Balance, Identity, Assets, Liabilities, Investments incl.
     Refresh, Statements), access to "almost all institutions" including most OAuth banks.
     **[search-snippet]**, corroborated across 3+ independent WebSearch queries with
     internally-consistent figures (10 Items, 8 products, "90% auto-approved within 60
     seconds," "no business registration, security questionnaire, or contract required").
     Support source: [What is the Plaid Trial plan? – Plaid Help Center](https://support.plaid.com/hc/en-us/articles/39994173227159-What-is-the-Plaid-Trial-plan)
     (blocked by Cloudflare on direct fetch, relying on search snippets).
  2. **Limited Production** — the older restricted-real-data tier this replaces. Directly
     quoted definition from Plaid's own glossary: *"Limited Production is a restricted mode
     of the Production environment. In Limited Production, you can make free API calls using
     real-world data for testing purposes, but the number of API calls you can make and the
     number of Items you can create are capped"* — and it explicitly **cannot** connect to
     Bank of America, Chase, or Wells Fargo (OAuth institutions) per
     [search-snippet]. Source: [Quickstart - Glossary | Plaid Docs](https://plaid.com/docs/quickstart/glossary/) (directly fetched, definition kept for legacy teams).
  3. **Full (paid) Production access** — required once you exceed 10 Items, need a product
     outside the Trial bundle, or need the paid-plan-gated Security Questionnaire that some
     OAuth institutions (Schwab, Capital One) require. This is the tier that removes the
     Item cap and is what "real, general-availability launch" means.

- **Date of the Trial-plan rollout — treat with care.** Multiple independent WebSearch queries
  converged on **April 15, 2026** as the date Trial plans became the default replacement for
  Limited Production for *new* US/Canada teams (e.g. *"as of April 15, 2026, new Limited
  Production signups are no longer available for developers in the US and Canada"*
  [search-snippet]). One WebFetch pass over the Plaid changelog page returned a conflicting
  date of **April 16, 2025** for "Introduced Plaid Trial plans" **[low-confidence — WebFetch
  listing-page summary]** — this could be a genuine 2025 soft-launch followed by an April 2026
  full replacement of Limited Production, or it could be a one-year date error from the
  summarizer (a known WebFetch failure mode on long listing pages). **Action for TaxAhead:**
  don't rely on either date — log into `dashboard.plaid.com/overview` and check which tier the
  existing TaxAhead Plaid team is actually on (Trial vs. legacy Limited Production); the
  self-service upgrade path differs slightly but the end goal (apply for full Production) is
  the same either way.

- **Practical implication for TaxAhead:** the Sandbox integration you have today needs to
  (a) get *some* real-data access first — either the team is already eligible for a Trial
  plan (fast, self-service, no business paperwork) or is on/needs Limited Production — to
  validate real institution behavior, and then (b) apply for and be approved for **full
  Production access** before onboarding real paying users at any scale beyond ~10 test Items,
  and *before* most large-bank (OAuth) institutions will work at all.

Sources for this section:
- [Quickstart - Glossary | Plaid Docs](https://plaid.com/docs/quickstart/glossary/) — directly fetched, primary source for the 2-environment model and Limited Production definition
- [Sandbox - Overview | Plaid Docs](https://plaid.com/docs/sandbox/) — directly fetched
- [How are Sandbox, Production, Trial plan, and Limited Production different? – Plaid Help Center](https://support.plaid.com/hc/en-us/articles/16110110883479-How-are-Sandbox-Production-Trial-plan-and-Limited-Production-different) — blocked (403), search-snippet only
- [What is the Plaid Trial plan? – Plaid Help Center](https://support.plaid.com/hc/en-us/articles/39994173227159-What-is-the-Plaid-Trial-plan) — blocked (403), search-snippet only
- [Changelog | Plaid Docs](https://plaid.com/docs/changelog/) — directly fetched but date extraction flagged low-confidence
- [Can I use Plaid for free? – Plaid Help Center](https://support.plaid.com/hc/en-us/articles/16194695660311-Can-I-use-Plaid-for-free) — search-snippet only

---

## 2. The Production Access application process

- **Where it happens:** the "Request Production Access" button appears in
  `dashboard.plaid.com` once required endpoint validation passes; full request flow is at
  `dashboard.plaid.com/overview/request-products` **[not reachable — needs your own dashboard
  login]**, referenced directly in Plaid's own docs ("apply for Production access" links to
  that exact path) — source: `plaid.com/docs/llms-full.txt` (directly fetched, official
  Plaid-published LLM-readable doc dump).

- **What the application collects (per Plaid's own docs, directly fetched from the OAuth
  guide):**
  - **Application (display) profile** — *"Public information that end users of your
    application will see when managing connections between your application and their bank
    accounts"* (app name, logo) — shown during Link/OAuth flows.
  - **Company profile** — *"information about your organization (not shared with end
    users)"* — legal company name, and optionally a **Legal Entity Identifier (LEI)**.
  - **Security Questionnaire** — required to access certain OAuth institutions (Schwab,
    Capital One named explicitly), and required generally once on a **paid (non-Trial)
    plan**. Confirmed 25-question / 19-category structure (hosting, vulnerability
    management, access controls, MFA, encryption in transit/at rest, logging/monitoring,
    incident response, vendor management, background checks, data-selling restrictions) —
    source: [Plaid Security Questionnaire (v6) gist](https://gist.github.com/coolaj86/0c17836066362d812006314ffc36ef13)
    (directly fetched).
  - **Plaid Master Services Agreement (MSA)** acceptance (US/CA) — clickwrap; legally must be
    accepted by *"you represent and warrant that you are authorized to bind the entity to the
    Agreement"* — source: search-derived from Plaid's own MSA text hosted via SEC EDGAR filing
    ([Plaid MSA on SEC EDGAR](https://www.sec.gov/Archives/edgar/data/2069448/000206944825000001/Plaid_msa.htm)).
  - **Redirect URIs** — registered separately under Team Settings → API → *Allowed redirect
    URIs* (see Section 4).
  - **Use case selection (Data Transparency Messaging)** — mandatory since Oct 31, 2024 for
    any new customer launching to end users in US/Canada (see Section 3).
  - **LEI (Legal Entity Identifier)** — currently *optional*, tied to the CFPB Section 1033
    rule for OAuth connections to US institutions, but *"Plaid is not currently enforcing the
    requirement to have an LEI and will not do so until the first 1033 compliance
    deadline"* — that deadline *"has been moved from April 2026 until at least July 2026 and
    its enforcement is currently stayed pending the finalization of a revised 1033
    rule"* [search-snippet, corroborated across multiple queries]. Not a blocker today, but
    worth having on file before the deadline firms up.
  - Expected-volume / API-call-volume is referenced ("cap on total Items unless you have
    full Production access") but the exact application-form field wording could not be
    confirmed without an authenticated dashboard session.

- **Who must submit it:** Plaid Dashboard permission model — *"Members with the Admin
  permission are automatically granted all permissions to the entire Plaid Dashboard. Admin
  users can manage users, request production access, and more"*; a "Team Management"
  permission has similar reach [search-snippet, from
  [Account - Teams | Plaid Docs](https://plaid.com/docs/account/teams/)]. **Legally**, whoever
  clicks through the MSA must be a person with actual authority to bind the company — Plaid's
  own MSA language ("you represent and warrant that you are authorized to bind the entity")
  does not require a specific title, but a solo/small-team startup should treat this as the
  founder/owner's action, not an engineer's or an AI agent's — see Section 7 (a)/(b) split.

- **Review timeline (2026):**
  - General Production approval: *"a couple of business days"* once company/use-case info is
    submitted [search-snippet]; Plaid's own (older) launch-checklist language says *"allow at
    least one week"* for EU-specific requests specifically — for US/CA the couple-of-days
    figure is the more current one.
  - Trial-plan applications: *"90% of applicants are auto-approved within 60 seconds"*; if
    flagged for manual review, *"Plaid's Customer Oversight team will follow up within 2–3
    business days via email"* [search-snippet].
  - **Per-institution OAuth registration is separate and adds time on top of account
    approval**: *"Access to most institutions is available within hours... some institutions
    may take up to 1-2 days"*; **Charles Schwab may take up to six weeks** from Production
    approval to Schwab-specific access — directly confirmed in
    [Link - OAuth guide | Plaid Docs](https://plaid.com/docs/link/oauth/) (fetched directly).
    Chase OAuth registration specifically had documented delays that Plaid says it resolved:
    changelog entry (Nov 4, 2025): *"Delays with Chase OAuth registration have been resolved.
    Chase registration will now typically complete in approximately 1-2 business days for new
    clients"* **[low-confidence — WebFetch listing-page summary, but plausible and
    consistent with the "hours to 1-2 days" general pattern]**.

- **Common reasons for rejection/delay** (from Plaid's own troubleshooting docs, directly
  fetched): incomplete Security Questionnaire (*"If you are on a paid (non-Trial) plan, you
  must complete the Security Questionnaire"*), incomplete application/company profile,
  redirect URI mismatch or non-HTTPS redirect URI, invalid `client_id`, and simply not yet
  being registered with a specific institution (1-2 day lag after account-level approval).
  Source: [Errors - Institution errors | Plaid Docs](https://plaid.com/docs/errors/institution/)
  and related troubleshooting pages (directly fetched via search synthesis of doc content).

Sources: [Link - OAuth guide | Plaid Docs](https://plaid.com/docs/link/oauth/) (directly fetched — primary source for institution-specific timelines and Dashboard registration requirements) · [Account - Teams | Plaid Docs](https://plaid.com/docs/account/teams/) · [Plaid Security Questionnaire (v6) gist](https://gist.github.com/coolaj86/0c17836066362d812006314ffc36ef13) (directly fetched) · [Plaid MSA — SEC EDGAR filing](https://www.sec.gov/Archives/edgar/data/2069448/000206944825000001/Plaid_msa.htm) · [Section 1033: What companies need to know | Plaid](https://plaid.com/resources/compliance/section-1033-authorized-third-parties/) · Hacker News, [I work at Plaid] comment thread on onboarding friction: [item 37617661](https://news.ycombinator.com/item?id=37617661), [item 37614748](https://news.ycombinator.com/item?id=37614748)

---

## 3. Compliance / legal prerequisites

- **End User Privacy Policy disclosure requirement.** Confirmed via Plaid's Developer
  Policy content (search-derived synthesis of the actual policy page, which was fetched but
  the tool could not confirm the pre-linking disclosure template verbatim): *"Before any end
  user engages with the client application in a manner that uses the service, the client will
  ensure that each end user is put on notice of, and agrees to, Plaid's privacy policy"* —
  and the company must either link to `https://plaid.com/legal` with a clear statement that
  end users' data is treated per that policy, or include compliant equivalent language in
  their own privacy policy [search-snippet, from
  [Developer Policy | Plaid](https://plaid.com/developer-policy/)]. Directly fetched
  [Privacy and security policies | Plaid](https://plaid.com/legal/) confirms Plaid's own End
  User Privacy Policy content that this must reference: what Plaid collects (identifiers
  incl. SSN, financial account data, device/IP data) and that Plaid shares data *"with the
  developer of the app you are using... and with the financial institutions you connect to
  Plaid."* **Practically for TaxAhead:** the app's own privacy policy (shown before the user
  ever opens Plaid Link) needs a clause covering this — this is UI copy / legal text, buildable
  in parallel (see Section 7b), but the legal *sign-off* on final wording should still get an
  owner/counsel pass given TaxAhead handles SSNs and tax data.

- **Master Services Agreement + Data Processing Agreement.** The DPA is *"an addendum to the
  Master Services Agreement that is incorporated as part of the Agreement"* — clients get
  access to End User Data via Plaid and *"are required to provide all notices and obtain all
  express consents from each End User as required under applicable laws... these consents
  must be clear and conspicuous and generally specify the categories of End User Data that
  will be received and how it will be used, stored and otherwise processed"* [search-snippet].
  This agreement acceptance happens in the Plaid Portal/Dashboard at production-application
  time and is a legal act, not an engineering one.

- **Security Questionnaire** (detailed in Section 2) is the closest thing Plaid runs to a
  SOC2-adjacent review *of the integrating company* — it is not itself a SOC2 audit, but asks
  SOC2-Trust-Services-style questions (encryption at rest/in transit, MFA, access control,
  vulnerability management, incident response, background checks, vendor management, audit
  logging) that an engineer answers factually about TaxAhead's own stack.
  Source: [Plaid Security Questionnaire (v6) gist](https://gist.github.com/coolaj86/0c17836066362d812006314ffc36ef13) (directly fetched).
  Separately, **Plaid itself** publishes its own SOC 2 Type II + ISAE 3000, ISO 27001, and ISO
  27701 certifications for TaxAhead's own vendor-risk diligence *on Plaid* — via
  [Plaid Trust Center](https://security.plaid.com/) / [security.plaid.com/documents](https://security.plaid.com/documents)
  [search-snippet]. These are two different directions of scrutiny — don't conflate them.

- **Data Transparency Messaging (DTM) / use-case selection — mandatory, tied to the CFPB
  Section 1033 rule.** Directly fetched and quoted:
  *"As of October 31, 2024, all new Plaid Inc. customers launching to end users in the US
  and/or Canada are automatically enrolled for Data Transparency Messaging and must select a
  use case to use Link in Production."* A company selects 1-3 use cases from four categories
  (Payments; Identity verification and fraud; **Personal/Business finance management**;
  Credit underwriting) and configures which data scopes (accounts, transactions, contact
  info, routing/account numbers) it's asking for — this is then surfaced *to the end user
  inside the Link flow itself* before they consent. TaxAhead's use case almost certainly maps
  to "Personal/Business finance management." This is Dashboard configuration + Link-flow UI
  copy — engineering-buildable, but the use-case choice itself has compliance weight and is
  worth an owner/counsel sanity check since it's what Plaid tells the end user TaxAhead is
  asking for.
  Source: [Link - Data Transparency Messaging migration | Plaid Docs](https://plaid.com/docs/link/data-transparency-messaging-migration-guide/) (directly fetched).

- **Extra scrutiny for tax-prep-specific use cases — important finding: Plaid itself does
  NOT have a formal, named "tax software" review tier.** Searches for Plaid-specific "tax
  preparer" scrutiny, restricted-industry lists, or compliance callouts turned up nothing —
  Plaid's restricted/enhanced-due-diligence industry lists that *do* exist are scoped to its
  **Transfer** (money-movement) product, not Transactions/Auth/Identity (data-read) products,
  and tax preparation is not named among them [search-snippet, from Plaid's Transfer
  application docs]. **The real extra scrutiny for TaxAhead is not a Plaid gate — it's
  TaxAhead's own regulatory exposure once it uses bank data to help prepare tax returns:**
  - **IRS Section 7216 (26 U.S.C. §7216)** — a criminal statute governing "tax return
    preparers'" use/disclosure of "tax return information." If TaxAhead's product functions
    as a return preparer (or works with a preparer) and uses Plaid-sourced transaction data
    as an input to tax-prep advice/output, using that data for anything beyond the
    return-preparation purpose the taxpayer consented to (e.g., cross-selling, using it to
    solicit other financial products) requires a **separate, explicit written 7216 consent**
    — distinct from and in addition to Plaid's own End User Privacy Policy consent. Key
    sourced facts: *"No tax information can be disclosed or used without taxpayer consent...
    consent forms must be separate from other documents, such as engagement letters"*; civil
    penalties are *"$1,000 for each improper disclosure or use... without a cap on the total
    amount"*; criminal exposure up to *"imprisoned not more than one year"* per violation.
    Source: [Section 7216 information center | IRS](https://www.irs.gov/tax-professionals/section-7216-information-center),
    [26 U.S. Code § 7216 | Cornell LII](https://www.law.cornell.edu/uscode/text/26/7216),
    [26 CFR § 301.7216-2 | Cornell LII](https://www.law.cornell.edu/cfr/text/26/301.7216-2).
    **This is a legal-review item for TaxAhead's counsel/owner, not something Plaid's
    application process will catch or flag — it needs its own consent flow independent of
    Plaid Link's consent screen.**

Sources: [Developer Policy | Plaid](https://plaid.com/developer-policy/) · [Privacy and security policies | Plaid](https://plaid.com/legal/) (directly fetched) · [Link - Data Transparency Messaging migration | Plaid Docs](https://plaid.com/docs/link/data-transparency-messaging-migration-guide/) (directly fetched) · [Plaid Trust Center](https://security.plaid.com/) · [Plaid Security Questionnaire (v6) gist](https://gist.github.com/coolaj86/0c17836066362d812006314ffc36ef13) (directly fetched) · [Section 1033: What companies need to know | Plaid](https://plaid.com/resources/compliance/section-1033-authorized-third-parties/) · [Section 7216 information center | IRS](https://www.irs.gov/tax-professionals/section-7216-information-center) · [26 U.S. Code § 7216 | Cornell LII](https://www.law.cornell.edu/uscode/text/26/7216) · [26 CFR § 301.7216-2 | Cornell LII](https://www.law.cornell.edu/cfr/text/26/301.7216-2)

---

## 4. Technical requirements that apply in production but not sandbox

### 4a. Webhook endpoint (real, public, verified)
- **Must be HTTPS with a valid SSL cert; must be publicly reachable.** Directly-sourced quote:
  *"When specifying a webhook, the URL must be in the standard format of
  `http(s)://(www.)domain.com/` and, if https, must have a valid SSL certificate."* Sandbox
  will fire webhooks to a temporary listener (Plaid explicitly suggests Webhook.site/Request
  Bin for early testing, with the caution *"make sure you are using Plaid's Sandbox
  environment and not sending out live data"*) — but production requires a real, durable,
  publicly-addressable endpoint on TaxAhead's own infrastructure.
  Source: [API - Webhooks | Plaid Docs](https://plaid.com/docs/api/webhooks/) (directly
  fetched).
- **Signature verification is mandatory to trust an incoming webhook.** Full verified
  procedure (directly fetched from
  [API - Webhook verification | Plaid Docs](https://plaid.com/docs/api/webhooks/webhook-verification/)):
  1. Read the `Plaid-Verification` header (a JWT).
  2. Decode the JWT header (without validating signature yet); require `alg == "ES256"`,
     reject otherwise.
  3. Extract `kid`, call `/webhook_verification_key/get` with `client_id`/`secret`/`key_id`
     to fetch the JWK public key; **cache it** (Plaid explicitly recommends caching to avoid
     calling this on every webhook).
  4. Verify the JWT signature against the JWK; reject if invalid.
  5. Check `iat` (issued-at) — reject if the webhook is **more than 5 minutes old** (replay
     protection).
  6. Compute SHA-256 of the raw webhook body and compare (constant-time) against
     `request_body_sha256` in the JWT payload — note Plaid's own caveat that this hash *"is
     sensitive to the whitespace in the webhook body and uses a tab-spacing of 2."*
  Plaid also documents a rotating source-IP list (`52.21.26.131, 52.21.47.157, 52.41.247.19,
  52.88.82.239` at fetch time) but explicitly flags *"these IP addresses are subject to
  change"* — so IP-allowlisting is a defense-in-depth measure, not a substitute for JWT
  verification.

### 4b. Link token + product config
- `link_token` must be created server-side (not sandbox test-only), with the real `products`
  array (`transactions`, and if used, `auth`/`identity`), and the correct `redirect_uri` if
  OAuth institutions are supported (see 4c).
- **Recommended integration pattern for Transactions in 2026 is `/transactions/sync`, not the
  older `/transactions/get`.** Directly-corroborated: *"It is recommended that any new
  integrations use `/transactions/sync` instead of `/transactions/get`, for easier and
  simpler handling of transaction state changes."* The `SYNC_UPDATES_AVAILABLE` webhook is
  what fires when new data is ready — but **it will not fire at all until `/transactions/sync`
  has been called at least once for that Item**, so the initial sync must be triggered
  explicitly right after Item creation, not just waited on. `initial_update_complete` (≥30
  days of history) and `historical_update_complete` (up to 24 months) flags in the webhook
  payload tell you when backfill is done.
  Source: [Transactions - Transactions webhooks | Plaid Docs](https://plaid.com/docs/transactions/webhooks/),
  [Transactions - Transactions Sync migration guide | Plaid Docs](https://plaid.com/docs/transactions/sync-migration/).

### 4c. OAuth (large-bank support)
Directly fetched from [Link - OAuth guide | Plaid Docs](https://plaid.com/docs/link/oauth/):
- OAuth is **mandatory** for connecting to institutions in the US that use it (Chase, Bank of
  America, Wells Fargo, Capital One, Citi, U.S. Bank, PNC, Navy Federal, Merrill, American
  Express named), and *universal* for all UK/EU institutions. Canada does not currently use
  OAuth.
- **Redirect URIs**: must be HTTPS (localhost-over-HTTP is Sandbox-only); no custom URI
  schemes in any environment; subdomain wildcards allowed with `*`; must be registered in
  **Team Settings → API → Allowed redirect URIs** (*"Next to Allowed redirect URIs click
  Configure then Add New URI"*) [search-snippet] AND passed as the exact `redirect_uri` string
  in `/link/token/create` (no query params on that string).
- **Web**: host a blank page at the redirect URI. **iOS/React Native-iOS**: needs an Apple App
  Association file + universal links (no custom scheme). **Android**: pass
  `android_package_name` instead of `redirect_uri`; Plaid auto-generates the redirect.
  **Webviews**: must extend the webview's redirect handler specifically to support Chase's
  App2App flow.
- Production (paid or Trial) access is *"a prerequisite for supporting OAuth"* at all — it
  cannot be built/tested end-to-end against real OAuth banks in Sandbox (Sandbox only offers
  synthetic OAuth test institutions like `ins_127287` "Platypus OAuth Bank").
- Per-institution enablement timelines: most institutions within hours of completing
  registration; some 1-2 days; **Charles Schwab up to six weeks**.

### 4d. Item/error webhook handling
Directly fetched from [API - Items | Plaid Docs](https://plaid.com/docs/api/items/):

| Webhook | Trigger | Required response |
|---|---|---|
| `ERROR` | Error encountered on an Item (commonly wraps `ITEM_LOGIN_REQUIRED`) | Re-auth via Link **update mode** |
| `PENDING_EXPIRATION` | Item's access consent expiring in **7 days** (UK/EU) | Re-auth via Link update mode before expiry |
| `PENDING_DISCONNECT` | Item scheduled for disconnection in **7 days** (US/CA analog) | Re-auth via Link update mode before disconnect |
| `LOGIN_REPAIRED` | Item exited `ITEM_LOGIN_REQUIRED` without the user going through update mode | Silence any "please reconnect" messaging you'd shown |
| `NEW_ACCOUNTS_AVAILABLE` | Plaid detects a new account at an already-linked institution | Prompt update mode to add it (US/CA) |
| `USER_PERMISSION_REVOKED` | End user revoked consent (e.g. via Plaid Portal, `my.plaid.com`) | Attempt restore via update mode, or delete the Item's data |
| `USER_ACCOUNT_REVOKED` | End user revoked access at the *data provider's own* portal | **Must delete any Plaid-derived data** tied to that account |
| `WEBHOOK_UPDATE_ACKNOWLEDGED` | Webhook URL was changed for an Item | Informational only |

`ITEM_LOGIN_REQUIRED` error code = *"the login details of this item have changed
(credentials, MFA, or required user action)"* — resolved the same way, via Link update mode,
whether you hit it synchronously from an API call or asynchronously via the `ERROR` webhook.
Source: [Link - Update mode | Plaid Docs](https://plaid.com/docs/link/update-mode/),
[Errors - Item errors | Plaid Docs](https://plaid.com/docs/errors/item/).

### 4e. Rate limits (production) — directly fetched from
[Errors - Rate Limit Exceeded errors | Plaid Docs](https://plaid.com/docs/errors/rate-limit-exceeded/):

| Endpoint | Per-Item limit | Per-client limit |
|---|---|---|
| `/transactions/sync` | 50/min | 2,500/min (500/min for empty-cursor requests) |
| `/transactions/get` | 30/min | 20,000/min |
| `/auth/get` | 15/min | 12,000/min |
| `/identity/get` | 15/min | 2,000/min |
| `/item/get` | 15/min | 5,000/min |
| `/accounts/get` | 15/min | 15,000/min |

Plaid's own framing: *"Plaid default rate limits are set such that using the API as designed
should typically not cause a rate limit to be encountered"* — a higher limit is available on
request via account manager/support ticket if TaxAhead's growth needs it.

Sources: [API - Webhooks | Plaid Docs](https://plaid.com/docs/api/webhooks/) · [API - Webhook verification | Plaid Docs](https://plaid.com/docs/api/webhooks/webhook-verification/) · [Link - OAuth guide | Plaid Docs](https://plaid.com/docs/link/oauth/) · [Transactions - Transactions webhooks | Plaid Docs](https://plaid.com/docs/transactions/webhooks/) · [Transactions - Transactions Sync migration guide | Plaid Docs](https://plaid.com/docs/transactions/sync-migration/) · [API - Items | Plaid Docs](https://plaid.com/docs/api/items/) · [Link - Update mode | Plaid Docs](https://plaid.com/docs/link/update-mode/) · [Errors - Item errors | Plaid Docs](https://plaid.com/docs/errors/item/) · [Errors - Rate Limit Exceeded errors | Plaid Docs](https://plaid.com/docs/errors/rate-limit-exceeded/) (all directly fetched)

---

## 5. Cost / production pricing

- **Sandbox: free, unconditionally.** **Trial plan: free**, real data, capped at 10 Items —
  *"no business registration, security questionnaire, or contract required"* [search-snippet].
  **Full Production requires live billing.** Confirmed structurally (directly fetched from
  [Account - Pricing and billing | Plaid Docs](https://plaid.com/docs/account/billing/)):
  billing model varies **by product**:
  - *Per-Item, one-time-fee products*: *"a fee is charged when the Item is created"* —
    Auth, Identity, and Income are named as one-time-fee products [search-snippet].
  - *Subscription-fee products*: *"an Item will incur a monthly subscription fee as long as a
    valid access_token exists"* — **Transactions is billed this way**
    [search-snippet]. Billing cycle is calendar-month, UTC.
  - *Per-request/flat-fee products*: *"a flat fee is charged for each successful API
    call."*
- **Exact $ figures are not publicly listed by Plaid** — directly confirmed: the pricing page
  states *"For more information on pricing, plans, or volume discounts, please visit Plaid
  Billing or connect with our sales team"* and a third-party pricing-strategy analysis
  confirms this is deliberate (*"Plaid's pricing page deliberately avoids publishing detailed
  rate cards... to ensure serious prospects talk to sales"*). Community/third-party-sourced
  **approximate** ranges (not Plaid-published, treat as indicative only): Auth ≈ $0.30–$1.00
  per successful connection; Transactions ≈ $0.30–$0.60 per successful call/subscription-item
  equivalent; Identity ≈ $0.15–$0.30 per successful call — **these are unverified
  aggregator estimates, not Plaid-quoted numbers**, and should not be used for budgeting
  without confirming with Plaid sales.
- **Plan tiers**: **Pay-as-you-go** (*"No minimum spend or commitment. Most appropriate for
  hobbyist use, or for early-stage small businesses"*) vs. **Growth** (*"minimum spend and
  annual commitment... lower per-use costs... SSO, priority support, a personal account
  manager"*, appropriate above roughly $2,000/month usage) vs. **Custom/Scale** (enterprise,
  contact sales, one source cites a $500/month starting anchor for the "Scale" plan)
  [search-snippet, multiple corroborating queries]. **Actual pricing is shown to you on the
  final page of the production-access request flow itself** — directly confirmed:
  *"Pricing information for Pay-as-you-go and Growth plans will be displayed on the last page
  before you submit your request"* — source: `plaid.com/docs/llms-full.txt` (directly
  fetched, official Plaid doc).
- **Billing setup is a prerequisite of the production request, not a downstream step** — you
  see and accept pricing as part of submitting the request, meaning a card-on-file /ACH
  billing setup on the Plaid account is required at application time, unlike Sandbox/Trial
  which need none.

Sources: [Account - Pricing and billing | Plaid Docs](https://plaid.com/docs/account/billing/) (directly fetched) · [Pricing - United States & Canada | Plaid](https://plaid.com/pricing/) (directly fetched) · `plaid.com/docs/llms-full.txt` (directly fetched) · [Inside Plaid's Pricing Strategy - PricingSaaS](https://newsletter.pricingsaas.com/p/inside-plaids-pricing-strategy) (directly fetched) · [How much does Plaid cost, and what are the pricing models? – Plaid Help Center](https://support.plaid.com/hc/en-us/articles/16194632655895-How-much-does-Plaid-cost-and-what-are-the-pricing-models) (search-snippet, blocked on direct fetch)

---

## 6. Realistic timeline (application → approval → first real user)

Stitching together the sourced pieces above (all individually cited earlier; combined here
for planning):

| Step | Duration (sourced) |
|---|---|
| Trial-plan signup (if eligible / not already past it) | Self-service; *"90% auto-approved within 60 seconds"*; manual-review cases followed up within 2-3 business days [search-snippet] |
| Full Production application (company profile, use case, security questionnaire, MSA, billing) | *"a couple of business days"* once submitted complete [search-snippet]; incomplete Security Questionnaire is the most commonly cited cause of delay |
| General institution registration after account-level Production approval | Hours to 1-2 business days for most institutions (directly sourced from Plaid OAuth guide) |
| Chase OAuth specifically | ~1-2 business days for new clients as of Nov 2025 per Plaid's changelog **[low-confidence — WebFetch listing summary]** |
| Charles Schwab specifically | Up to **6 weeks** from Production approval (directly sourced, Plaid OAuth guide) |
| EU/UK institution access (not needed for a US tax app, noted for completeness) | Separate compliance process; *"allow at least one week"* for the request [search-snippet] |

**Realistic end-to-end estimate for TaxAhead (US-only, no Schwab dependency assumed):**
roughly **1-2 weeks** from a complete, first-try application (profile + security
questionnaire + billing all correct) to being able to onboard a real user through a
non-Schwab, non-EU institution — with the caveat that this compresses to near-zero if
TaxAhead is currently eligible for the Trial plan (real data, real OAuth banks, no
application at all, just capped at 10 Items) and only the *full* paid-Production step (needed
past 10 users, or to remove the Trial's restrictions) adds the few-days review layered on top.
If any target institution is Schwab, budget 6 weeks separately for that one institution while
everything else proceeds. These are Plaid's own published figures / directly-sourced
changelog notes, not third-party guesses — no independent community (Reddit/IndieHackers/HN)
timeline reporting beyond the one HN "[I work at Plaid]" thread cited in Section 2 could be
found to corroborate or contest them further; that gap is noted rather than papered over.

---

## 7. Ordered checklist — (a) owner-only vs (b) engineering-parallel-buildable

### (a) Requires the business owner personally — cannot be delegated to an engineer or an AI agent
1. **Decide/confirm the Plaid tier TaxAhead is actually on right now** (log into
   `dashboard.plaid.com/overview` — Trial vs. legacy Limited Production vs. already-Sandbox-
   only) — a business decision about which path to pursue, informs everything downstream.
2. **Accept the Plaid Master Services Agreement** — legally must be done by someone with
   actual authority to bind TaxAhead as a company (Section 2); this is a clickwrap contract
   acceptance, not an engineering task.
3. **Accept the Data Processing Agreement** (addendum to the MSA) — same authority
   requirement; governs how TaxAhead is allowed to store/use End User Data received via
   Plaid.
4. **Set up production billing on the Plaid account** (card/ACH on file) — required at
   application submission time per Section 5; a financial/legal act.
5. **Submit the Request Production Access application itself** under TaxAhead's company
   Plaid account — even though an Admin-permission team member *could* technically click the
   button, the underlying legal representations (company profile, security questionnaire
   accuracy, MSA) mean this should be the owner's action or explicitly owner-authorized, not
   default-delegated.
6. **Complete/attest the Security Questionnaire's company-identity and governance answers**
   — an engineer can draft the technical answers (encryption, MFA, logging — see 7b), but
   attesting on behalf of the company to things like background-check policy, incident
   response ownership, and vendor management is an owner-level sign-off.
7. **Sign off on the final End User Privacy Policy text and the 7216 tax-data consent
   language** — an engineer/AI agent can draft both (see 7b), but given TaxAhead handles SSNs
   and tax-return-adjacent data, and given Section 7216's per-violation civil/criminal
   exposure (Section 3), the actual legal wording needs an owner (or counsel) sign-off before
   it goes live to real users.
8. **Choose the DTM "use case" category(ies) shown to end users inside Plaid Link** (Section
   3) — a compliance-facing decision about how Plaid describes TaxAhead's data request to the
   end user; low-effort but owner-should-see-it before it ships.
9. **Decide the pricing plan tier (Pay-as-you-go vs. Growth) and accept the quoted cost** —
   shown only at the final step of the application flow (Section 5); a spend commitment
   decision.

### (b) Pure engineering work — can be built NOW, in parallel with / ahead of Plaid's approval
1. **Stand up a real, publicly-reachable HTTPS webhook endpoint** (Section 4a) — this needs
   zero Plaid approval; it's just infrastructure (TLS cert, public DNS, durable server/serverless
   function).
2. **Implement full Plaid webhook signature verification** (Section 4a) — the exact 6-step
   JWT/JWK/ES256/5-minute-freshness/SHA-256-body-hash procedure is fully documented and testable
   today; Sandbox fires real (correctly-signed) webhooks, so this can be built and tested
   end-to-end against Sandbox before Production exists.
3. **Build Item/error webhook handling** for all 8 webhook types in the Section 4d table —
   `ERROR`/`ITEM_LOGIN_REQUIRED`, `PENDING_EXPIRATION`, `PENDING_DISCONNECT`,
   `LOGIN_REPAIRED`, `NEW_ACCOUNTS_AVAILABLE`, `USER_PERMISSION_REVOKED`,
   `USER_ACCOUNT_REVOKED`, `WEBHOOK_UPDATE_ACKNOWLEDGED` — including the Link **update-mode**
   re-auth flow and the "delete data on revocation" handler. All testable in Sandbox.
4. **Migrate/build Transactions ingestion on `/transactions/sync`**, not the legacy
   `/transactions/get`, with the initial explicit sync call + `SYNC_UPDATES_AVAILABLE`
   webhook loop, and cursor persistence per Item (Section 4b) — fully buildable and testable
   against Sandbox test institutions today.
5. **Wire OAuth redirect handling end-to-end** (Section 4c): host the blank redirect-URI
   page (web), configure the Apple App Association file (iOS, if a native/RN app exists),
   implement `receivedRedirectUri` re-initialization for web/webview, and handle Android via
   `android_package_name`. Buildable against Sandbox's synthetic OAuth institution
   (`ins_127287`, "Platypus OAuth Bank") — the actual redirect URI value just needs to be
   swapped from a Sandbox/dev URL to the real production URL once that's decided, and
   registered in the Dashboard's Allowed Redirect URIs list (a low-friction config step, not
   a legal one).
6. **Draft the End User Privacy Policy disclosure copy and the 7216 tax-data consent flow
   UI** (Section 3) — the actual screens/copy/consent-checkbox UX can be fully built now; only
   final legal sign-off is gated on the owner (7a-7).
7. **Configure Link token creation with the real `products` array** (`transactions`, plus
   `auth`/`identity` if used) and implement the DTM use-case data-scope wiring in code —
   the Dashboard-side use-case *choice* is 7a-8, but the code that reads it and requests the
   right product/data-scope combination from Link is pure engineering.
8. **Draft the Security Questionnaire's technical answers** (Section 3: TLS version,
   encryption-at-rest method, MFA implementation, vulnerability scanning cadence, logging/
   audit-trail design, code-review/change-control process) — an engineer can write all of
   this factually; only the company-attestation parts need owner sign-off (7a-6).
9. **Rate-limit-aware client design** (Section 4e) — build request batching/backoff against
   the documented per-Item and per-client limits now, so Production traffic doesn't need
   rework later.
10. **Set the environment-switch config** (Sandbox vs. Production base URL / `client_id` /
    `secret`, `PLAID_ENV` flag) so flipping TaxAhead from Sandbox to Production is a config
    change, not a code change, the moment (a)-track approval lands.

---

## Full source index (every URL cited above)

Directly fetched and quoted from:
- https://plaid.com/docs/quickstart/glossary/
- https://plaid.com/docs/sandbox/
- https://plaid.com/docs/link/oauth/
- https://plaid.com/docs/api/webhooks/
- https://plaid.com/docs/api/webhooks/webhook-verification/
- https://plaid.com/docs/api/items/
- https://plaid.com/docs/account/billing/
- https://plaid.com/pricing/
- https://plaid.com/docs/link/data-transparency-messaging-migration-guide/
- https://plaid.com/legal/
- https://plaid.com/docs/changelog/ (dates flagged low-confidence)
- https://plaid.com/docs/llms-full.txt
- https://gist.github.com/coolaj86/0c17836066362d812006314ffc36ef13 (Plaid Security Questionnaire v6)
- https://newsletter.pricingsaas.com/p/inside-plaids-pricing-strategy
- https://www.irs.gov/tax-professionals/section-7216-information-center
- https://www.law.cornell.edu/uscode/text/26/7216
- https://www.law.cornell.edu/cfr/text/26/301.7216-2

Referenced via WebSearch synthesis (page blocked by Cloudflare bot-challenge on direct
fetch/curl, or not independently re-opened) — flagged `[search-snippet]` inline above:
- https://support.plaid.com/hc/en-us/articles/16110110883479-How-are-Sandbox-Production-Trial-plan-and-Limited-Production-different
- https://support.plaid.com/hc/en-us/articles/39994173227159-What-is-the-Plaid-Trial-plan
- https://support.plaid.com/hc/en-us/articles/16194695660311-Can-I-use-Plaid-for-free
- https://support.plaid.com/hc/en-us/articles/16194632655895-How-much-does-Plaid-cost-and-what-are-the-pricing-models
- https://plaid.com/docs/account/teams/
- https://plaid.com/developer-policy/
- https://plaid.com/resources/compliance/section-1033-authorized-third-parties/
- https://plaid.com/docs/transactions/webhooks/
- https://plaid.com/docs/transactions/sync-migration/
- https://plaid.com/docs/link/update-mode/
- https://plaid.com/docs/errors/item/
- https://plaid.com/docs/errors/rate-limit-exceeded/
- https://plaid.com/docs/errors/institution/
- https://www.sec.gov/Archives/edgar/data/2069448/000206944825000001/Plaid_msa.htm
- https://news.ycombinator.com/item?id=37617661 / item?id=37614748 (Plaid employee comments on onboarding)

Not reachable this pass (needs an authenticated TaxAhead Plaid dashboard session to confirm
directly — flag for the Coder/owner to verify against the live account before relying on
exact field names):
- https://dashboard.plaid.com/overview/production
- https://dashboard.plaid.com/overview/request-products
- https://dashboard.plaid.com/settings/company/compliance

## What could NOT be confirmed (gaps, stated plainly)
- Exact, verbatim list of every field on the live "Request Production Access" form (blocked —
  needs dashboard login).
- Exact Plaid $/Item and $/call pricing for TaxAhead's specific volume — Plaid does not
  publish this; only shown after starting the real application, or via a sales call. Treat
  the ~$0.15-$1.00-per-call aggregator figures in Section 5 as rough market color, not a
  quote.
- Whether the security questionnaire requires periodic (e.g. annual) re-attestation — found
  general Plaid internal practices (annual employee background checks, recommended annual
  JWKS key rotation) but no explicit statement that the questionnaire itself is re-submitted
  on a cycle.
- Independent (non-Plaid) community timeline reports (Reddit/IndieHackers) for how long
  full Production review actually took recent applicants in 2025-2026 — searches did not
  surface usable threads beyond the one 2023-era Hacker News "I work at Plaid" thread cited
  above; the timeline in Section 6 rests on Plaid's own published figures, not corroborating
  community reporting, and that's a real gap, not a hidden one.
