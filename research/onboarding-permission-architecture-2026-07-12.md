# Domain Brief: Onboarding Mechanics & Permission Architecture for Email-as-Push-Channel

**Date:** 2026-07-12
**Researcher mode:** D (domain research for a build)
**Build context:** Cockpit — PMS-competitor for STR + PadSplit hosts. Lowest-friction onboarding
is the core adoption lever (incumbent Guesty reportedly needs "an IT person for the first steps").
Candidate data-acquisition channel: read the host's inbox for Airbnb/Vrbo/Booking/PadSplit
notification emails (booking, message, payout) as a real-time push channel that avoids OTA
automation-ToS exposure (see prior finding in `research/str-data-ingestion-strategy-2026-07-11.md`
that Airbnb ToS §11.1 bans "bots, crawlers, scrapers, or other automated means").
**Prior related research this extends:** `research/str-data-ingestion-strategy-2026-07-11.md`
(CM-API-first ingestion strategy; flagged email-parsing as "the no-partner power channel" but
did not research the OAuth/onboarding mechanics — this brief fills that gap) and
`research/vrbo-booking-delegated-access-2026-07-12.md` (native co-host analogues per OTA).

---

## Bottom-line recommendation

**Forward-address (filter-based auto-forwarding to a unique per-host ingestion address), not
Gmail/Outlook OAuth, should be the default onboarding path — with full-inbox OAuth offered only
as an optional "do it for me" upgrade later, once Cockpit has revenue to fund CASA.** The
forward-address model structurally avoids Google's restricted-scope machinery altogether (Cockpit
never requests a Gmail/Graph scope, so there is no CASA tier, no annual reassessment fee, no
100-user/7-day-token trap, no scary "Google hasn't verified this app" screen) at the cost of a
one-time, per-mailbox-provider setup flow (Gmail requires a forwarding-address confirmation
click; Outlook's rule builder is comparably manual). OAuth's *only* structural advantage is that
it can be done in one authorization click with no dependence on the host correctly building a
filter — but that convenience is bought at a real, quantified cost (below) that does not scale
to a pre-revenue startup's first hundreds of hosts. Section "Recommendation detail" below gives
the concrete hybrid design.

---

## Q1 — Gmail `gmail.readonly` restricted-scope OAuth: what Google actually requires

### Q1a. Is `gmail.readonly` a "restricted" scope, and does that trigger CASA?

**Answer: Yes on both counts — this is Google's own scope-classification page, not a
third-party paraphrase.**

**Source:** `https://developers.google.com/workspace/gmail/api/auth/scopes` (opened, fetched
2026-07-12).
**Quote:** *"Restricted: These scopes provide wide access to Google user data and require
restricted scope OAuth App Verification."* — `gmail.readonly` is listed under this
classification. The same page states: *"If you store restricted scope data on servers (or
transmit), then you must go through a security assessment."* Cockpit's whole design (parse
booking emails, store extracted revenue/guest/occupancy data in its own DB) is exactly "store
restricted scope data on servers" — so this is not an edge case Cockpit could argue around.

**Discrepancy flagged:** a secondary source (Unipile blog,
`https://www.unipile.com/google-oauth-100-user-limit/`) tabulates `gmail.readonly` as merely
"sensitive" (4–6 week review, no CASA) and reserves "restricted" for `gmail.send`/full-mailbox
scopes. This directly contradicts Google's own scopes page quoted above. **Trust the primary
source: `gmail.readonly` is restricted, full stop.** This is exactly the kind of secondary-vs-
primary conflict the honesty bar exists to catch — don't let the blog's cost table anchor
planning.

### Q1b. Is CASA mandatory for a production app with this scope?

**Answer: Yes, if Cockpit stores/transmits the data on its own servers (it will) — with one
important operational escape hatch for a pre-revenue pilot (see 1e).**

**Source:** `https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification`
(opened, fetched 2026-07-12).
**Quote:** *"Undergo security assessment — Required if the app 'accesses or has the capability
to access Google user data from or through a server.'"* Same page: *"Mandatory for: Apps
accessing restricted data through third-party servers. Not mandatory for: Personal use,
development/testing phases, service-owned data only, internal-only use, or domain-wide
installation scenarios."*

Confirmed independently at `https://support.google.com/cloud/answer/13464323?hl=en` (fetched),
which lists the same non-verification exceptions: personal use (<100 users), dev/testing/staging
(with the 100-user cap in effect), service-account-only (own data, not user data), internal
Workspace-only apps, and admin-installed/trusted Marketplace apps. **None of these exceptions
fit a real multi-tenant SaaS onboarding real hosts** — Cockpit is exactly the case CASA targets.

### Q1c. CASA tiers, cost, timeline

**Tiers (primary source, App Defense Alliance itself):**
`https://appdefensealliance.dev/casa/tier-2/tier2-overview` (fetched) confirms Tier 2 is
self-scan + lab validation ("developer performs scans using approved tools... assessor
[validates] without... access[ing] the application code or infrastructure") — and flags
**"The CASA self scanning process is deprecated"**, i.e. the mechanics are actively changing;
re-verify current submission steps at build time, don't assume this brief's process detail is
frozen.

Google's own tier-assignment page (`https://support.google.com/cloud/answer/13465431?hl=en`,
fetched) uses newer terminology — **AL1/AL2**, not "Tier 1/2/3" — and states assignment is
*"a risk-based, multi-tiered approach"* based on *"user count, requested scopes, and other
[app-specific] signals,"* and explicitly warns *"the required assurance level is dynamic and may
increase based on changes in your user base or data-handling practices."* **Cockpit should
expect to start at the lower assurance level and get pushed to the harder one as it grows** —
this is a scaling tax, not a one-time cost.

**Cost:** Google's own FAQ (`https://support.google.com/cloud/answer/13463817?hl=en`, fetched)
states plainly: *"Google does not charge the developer any fees for security assessment. The
cost for such a service is agreed on between the developer and the assessor without any
involvement from Google."* Google does not publish a canonical price list, so the figures below
are **secondary-source, flagged accordingly**:
- Deepstrike (`https://deepstrike.io/blog/google-casa-security-assessment-2025`, fetched,
  citing named CASA-authorized lab TAC Security's pricing): **Tier 2 (self-scan + lab
  validation): $540–$1,800 per assessment, 1–3 weeks. Tier 3 (full lab pen-test): ~$4,500 (other
  labs quoted $5,000–$8,000+), 2–4 weeks**, extending further if remediation is needed.
- A second secondary source (Unipile) gave a much wider "$0–$75k" band for restricted scopes —
  this looks like it's smearing in enterprise-scale Tier 3 engagements; **the TAC Security-cited
  numbers are the more credible, named-vendor figure and are what this brief anchors on.**
- **Annual re-assessment is confirmed mandatory by Google itself** (not just the secondary
  sources): *"All applications must be revalidated every year"* (support.google.com/cloud/answer/13465431)
  and *"apps must be reverified for compliance and complete a security assessment at least every
  12 months after your assessor's Letter of Assessment (LOA) approval date"*
  (restricted-scope-verification doc). So the $540–$8,000 figure is a **recurring annual line
  item**, not a one-time cost — real money for a pre-revenue or early-revenue startup, every
  year, indefinitely, for as long as the Gmail-OAuth feature exists.

### Q1d. Other requirements (privacy policy, in-app disclosure, limited use)

All confirmed from the same primary Google page
(`.../restricted-scope-verification`, fetched):
- **Privacy policy:** must be *"visible to users, hosted within the same domain as your
  application's home page"* and must *"disclose the manner in which your application accesses,
  uses, stores, or shares Google user data."*
- **Limited Use:** usage must be *"strict[ly] limit[ed]... to the practices that your published
  privacy policy discloses"* per the Google API Services User Data Policy's Limited Use clause —
  i.e. Cockpit's privacy policy becomes a legally binding scope contract enforceable by Google.
- **In-app disclosure / demo video:** Google requires *"a demonstration video that fully
  demonstrates how a user initiates and grants access to the requested scopes and shows, in
  detail, the usage of the granted sensitive and restricted scopes."*
- **Brand verification** (separate, lighter step): *"Typically takes 2–3 business days if
  branding hasn't changed."*
- **Overall timeline:** the same doc states plainly the full restricted-scope process *"can
  potentially take several weeks to complete"* — consistent with the CASA 1–4-week lab timeline
  above, stacked on top of the brand-verification and application-review steps, i.e. **budget
  4–8+ weeks end to end for a first-time restricted-scope verification**, before any lab
  remediation cycles.

### Q1e. The operational trap that makes "just stay under 100 test users" not actually work

**This is the single most load-bearing finding of this section and it is easy to miss.**
Google's OAuth consent screen has a "Testing" publishing status that exempts an app from
verification entirely, capped at 100 listed test users
(`https://support.google.com/cloud/answer/15549945?hl=en`, fetched: *"Projects configured with a
publishing status of Testing are limited to up to 100 test users listed in the OAuth consent
screen"*). This looks, on first read, like a viable strategy for Cockpit's early pilot cohort —
skip CASA, onboard the first ~100 hosts via Gmail OAuth in Testing mode. **It is not viable as a
standing product mechanism**, because the same page states, quoted verbatim: *"Authorizations by
a test user will expire seven days from the time of consent. If your OAuth client requests an
`offline` access type and receives a refresh token, that token will also expire."* A real-time
inbox-push feature needs a long-lived refresh token; **every pilot host's Gmail access would
silently die after 7 days and require a fresh consent click** — a support/reliability nightmare,
not a growth hack. Testing mode is fine for a demo or an internal dogfood account; it is not a
path to a real pilot cohort.

### Q1f. What the host actually sees (permission scariness)

- **The scope grant text:** for `gmail.readonly`, the consent screen shows *"View your email
  messages and settings"* (confirmed via `developers.google.com/workspace/gmail/api/auth/scopes`
  search-result convergence — this specific consent-screen string was not independently opened
  as a live screenshot in this pass, flagged as **secondary-only for the exact wording**, though
  the scope's existence and classification are primary-confirmed).
- **The unverified-app warning** (relevant until/unless CASA+verification is complete):
  Google's own troubleshooting doc for a related product states the substance —
  *"If the OAuth consent screen displays the warning 'This app isn't verified,' your app is
  requesting scopes that provide access to sensitive user data... until the developer verifies
  this app with Google, you shouldn't use it"* — and the bypass path is *Advanced → "Go to
  {Project Name} (unsafe)"* (`developers.google.com/workspace/keep/api/troubleshoot-authentication-authorization`,
  content surfaced via WebSearch snippet convergence across three independent sources including
  Google's own troubleshoot doc — flagged as **not independently re-opened this pass**, but the
  underlying mechanism — an "unsafe"-labeled bypass button — is consistent with widely
  documented, stable Google OAuth UX and is a reasonable fact to plan against). This is precisely
  the "IT person for the first steps" friction Cockpit is trying to avoid — a host who sees a red
  warning with the word "unsafe" on it before they've done anything is a host who abandons
  onboarding.

---

## Q2 — The auto-forward-address alternative

### Q2a. Does forwarding avoid the restricted-scope/CASA burden entirely?

**Answer: Yes, structurally — this is not a workaround, it is a different mechanism that never
touches Google's OAuth surface at all.** Cockpit never requests any Gmail/Graph scope; the host's
mail provider (Gmail, Outlook, or any other) performs the forwarding itself as a mail-server-side
rule, and Cockpit only ever receives mail actively pushed to an address Cockpit owns (e.g.
`host-abc123@ingest.cockpit.app`). There is no OAuth client, no scope, no CASA tier, no annual
reassessment, no 100-user cap, no 7-day token expiry, no "unverified app" warning. This is the
same trust-minimization pattern already used by e.g. expense-receipt tools' `receipts@` addresses,
which the dispatch itself named as the model.

**Caveat (must be explicit, not glossed over):** avoiding OAuth does not avoid *all* trust
questions — Cockpit still receives real booking/payout data by email and must handle it under
normal data-privacy law (not the Google-specific Limited Use policy, but GDPR/CCPA-equivalent
obligations apply regardless of channel). The dispatch's framing that "Cockpit never accesses the
inbox, only receives forwarded mail" is correct as far as *Google's* review surface goes; it is
not a general trust-and-safety pass.

### Q2b. Gmail forwarding setup steps and the verification friction point

**Source:** `https://support.google.com/mail/answer/10957?hl=en` (opened, fetched 2026-07-12).
Confirmed process:
1. Settings → "See all settings" → "Forwarding and POP/IMAP" tab → "Add a forwarding address."
2. Enter the destination address (Cockpit's per-host ingest address).
3. **The friction point, quoted from the official doc's substance:** *"Gmail sends a verification
   message to the destination address. You must click the verification link in the message... to
   confirm ownership before forwarding activates."* Since the destination is *Cockpit's* address,
   not the host's, **Cockpit — not the host — receives and auto-clicks/auto-confirms this link**
   server-side (this is exactly the receipts@-style pattern: the destination mailbox is
   provider-controlled and can auto-confirm). This means the friction is entirely on the
   forwarding-*setup* side (the host still has to add the address and pick/build the filter), not
   on a "wait for a code to come back to yourself" round-trip the host has to complete manually.
4. To forward only OTA notification emails (not the whole inbox), the host must instead build a
   **Gmail filter** (Settings → Filters and Blocked Addresses → Create a new filter → match sender
   domain e.g. `automated@airbnb.com`/`no-reply@vrbo.com`/`booking.com` → check "Forward it to" →
   select the verified address). This is a materially more manual, multi-field flow than a single
   OAuth consent click — real friction, but it is a **one-time settings-page task**, not a
   recurring compliance program.
5. **Google displays an in-Gmail security banner for one week after forwarding is enabled** as a
   built-in user-safety nudge — a piece of Google-native trust signaling that actually works *for*
   Cockpit's honesty story rather than against it (it visibly confirms to the host what they set
   up, rather than a scary unrelated-app warning).

### Q2c. Can this be templated / one-click?

Not literally one-click inside Gmail's own UI (Google does not expose a public API to
programmatically create a forwarding filter on the host's behalf without... OAuth — which would
reintroduce the exact CASA problem this path is meant to avoid). But it **can be reduced to a
guided, copy-paste wizard**: Cockpit generates the host's unique ingest address, shows an
animated/step-by-step overlay (pre-filled sender-domain list for the filter's "From" field,
pre-formatted destination address to paste), and the host performs 5–6 clicks inside their own
Gmail settings. This is the honest ceiling of "templated" without OAuth — worth stating plainly
rather than overselling it as one-click.

### Q2d. Outlook/Microsoft equivalent friction

Not separately re-verified with a live fetch of Outlook's forwarding-rule UI in this pass
(**flagged not_found for this specific sub-question** — see `not_found` section); Microsoft's
mail-forwarding-rule mechanism (Outlook.com "Rules" / Exchange "Inbox rules") is architecturally
analogous (a server-side rule the user builds, not an OAuth grant) but the exact UI click-path and
whether Microsoft imposes an equivalent external-forwarding-address confirmation step were not
independently confirmed this pass. Treat as a real but unverified assumption for a Coder building
the Outlook onboarding flow — verify Microsoft's own current forwarding-rule docs before shipping.

### Q2e. Comparison table (Q1 vs Q2)

| Dimension | Gmail OAuth (`gmail.readonly`) | Forward-address filter |
|---|---|---|
| Google review required | Yes — restricted-scope verification + CASA, 4–8+ wks, annual | No — Cockpit never registers an OAuth client for this data |
| Recurring cost | $540–$8,000+/yr (secondary-sourced CASA lab pricing, Google itself charges $0) | $0 |
| Host-facing scare surface | "Google hasn't verified this app... (unsafe)" warning until verification completes | None — normal Gmail Settings UI, native 1-week forwarding-enabled banner |
| Setup steps for host | 1 OAuth consent click (but blocked by scary warning pre-verification) | 5–6 manual settings/filter steps (templatable via a guided wizard) |
| Data minimization | Full read access to the scope (even if app only *uses* a subset) | Only the specifically-filtered sender domains ever reach Cockpit — real data minimization |
| Longevity risk | 7-day token death trap if left in Testing mode; must complete full verification to be durable | No token to expire — a mail rule persists until the host removes it |
| Cockpit's server-side burden | Must handle OAuth refresh-token storage, revocation, Limited-Use compliance program | Must run a receiving mail server / inbound-parse endpoint (e.g. SES/Mailgun/Postmark inbound) — different but comparably simple engineering lift |

---

## Q3 — IMAP / app-password viability

**Answer: Technically alive for personal Gmail accounts today, but Google actively discourages
it, it does not apply to Google Workspace business accounts, and it is a strictly worse trust
model than either OAuth or forwarding — not recommended as more than a documented fallback.**

**Source:** `https://support.google.com/accounts/answer/185833` (opened, fetched 2026-07-12).
**Quote:** *"App passwords aren't recommended and are unnecessary in most cases"*; they remain
available only for accounts with 2-Step Verification enabled, described as *"a 16-digit passcode
that gives a less secure app or device permission to access your Google Account."*

**Workspace-vs-personal split, confirmed from the official transition doc**
(`https://knowledge.workspace.google.com/admin/sync/transition-from-less-secure-apps-to-oauth`,
fetched, quoting the effective-March-14-2025 change): *"Access to less secure apps will be turned
off for all Google Accounts... CalDAV, CardDAV, IMAP, SMTP, and POP will no longer work with
legacy passwords (basic authentication)"* — **with an explicit carve-out that app passwords
specifically still work**: *"You will no longer use a password for access, with the exception of
app passwords."* So: raw username+password IMAP is dead everywhere; the 16-digit app-password
mechanism survives as the one remaining non-OAuth credential path, for as long as Google keeps the
exception open (no stated sunset date found).

**Why this is not a good default despite technically working:** it requires the host to (a) turn
on 2-Step Verification if not already on (extra setup step many hosts won't have), (b) navigate
to Google Account → Security → App passwords → generate one, (c) paste a 16-digit secret into
Cockpit. That secret is **functionally a long-lived master credential for the mailbox**, not a
scoped, individually-revocable OAuth grant — a materially worse security posture for Cockpit to
hold than either an OAuth refresh token (revocable, scoped, auditable in the host's Google
Account "Third-party access" page) or a forwarding rule (Cockpit never holds a credential at
all). It should be documented as a fallback for power users who specifically prefer it, not
marketed as the low-friction path.

**Microsoft side:** confirmed via the official Exchange Online basic-auth deprecation doc
(`https://learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/deprecation-of-basic-authentication-exchange-online`,
opened in full, fetched 2026-07-12) — *"Basic authentication is now disabled in all tenants...
Now no one (you or Microsoft support) can re-enable Basic authentication in your tenant"* — and
explicitly: *"The deprecation of basic authentication also prevents the use of app passwords with
apps that don't support two-step verification."* **Microsoft's app-password/basic-auth IMAP path
is fully dead, no exception, for any Microsoft 365/Exchange Online account** (which covers most
Outlook.com-for-business and all Microsoft 365 hosts). IMAP/POP protocols themselves remain
available but *only* via OAuth 2.0 (*"Application developers who have built apps that... process
email using these protocols will be able to keep the same protocol, but need to implement secure,
Modern authentication"*), and notably: *"There's no plan for Outlook clients to support OAuth for
POP and IMAP"* — i.e. this whole path is really only relevant to Cockpit-as-developer building its
own IMAP-over-OAuth client, not a credential-paste shortcut. **Net: IMAP app-password is a
Gmail-only, personal-account-only, discouraged, narrowing escape hatch — not a general
lower-review path.**

---

## Q4 — Microsoft/Outlook equivalent OAuth burden (Mail.Read)

**Answer: Structurally lighter than Google's regime — no CASA-equivalent mandatory paid
security assessment exists for reading mail via Microsoft Graph.**

**Delegated permission behavior — confirmed real difference from Google:**
`https://graphpermissions.merill.net/permission/Mail.Read` (opened, fetched) states plainly:
**"AdminConsentRequired: No"** for the delegated `Mail.Read` permission (vs "Yes" for the
application/tenant-wide variant) — meaning an individual host, as an end user, can consent to
Cockpit reading their own mailbox without needing their organization's IT admin to approve
anything, which matches Cockpit's target user (an independent host, not an enterprise IT
department).

**Publisher Verification — the closest Microsoft analogue to Google's verified-app badge, and it
is free and fast, not a security audit:**
`https://learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview`
(opened in full, fetched 2026-07-12). Direct quotes:
- *"How much does publisher verification cost for the app developer? Does it require a license?
  Microsoft doesn't charge developers for publisher verification. No license is required to
  become a verified publisher."*
- *"Developers who have already met these requirements can be verified in minutes."*
- Requirements are organizational/administrative, not security-technical: a verified **Microsoft
  AI Cloud Partner Program (CPP, formerly MPN)** account, a DNS-verified publisher domain matching
  the CPP account's domain, an app registered under a Microsoft Entra work/school account (not a
  personal MSA), and the initiating user having Application Administrator role + MFA. **No
  penetration test, no annual paid re-assessment, no per-tier lab fee anywhere in this
  requirement list.**
- Why it still matters: *"Beginning November 2020, if risk-based step-up consent is enabled,
  users can't consent to most newly registered multitenant apps that aren't publisher verified...
  a warning appears on the consent screen [that] the app was created by an unverified publisher
  and that the app is risky to download or install."* So there is a scare-warning risk
  structurally analogous to Google's, but the *fix* is free and fast, not a paid annual audit
  program. `Mail.Read` is explicitly named by search-corroborated sources as one of the
  "high-impact" permissions that triggers the blue-badge display logic — consistent with, not
  contradicting, this framing (this specific enumeration was not independently re-opened as a
  primary quote this pass — flagged secondary for the exact permission list, though the
  underlying badge/warning mechanism is primary-confirmed above).
- **Distinct, optional, higher-bar programs exist** (Microsoft 365 Publisher Attestation,
  Microsoft 365 App Certification) that *are* closer in spirit to CASA (self-attestation or
  Microsoft-run compliance review) — but the same primary doc frames them as complementary,
  store-listing-oriented programs (*"should complete"* for AppSource/co-marketing benefits), not
  a gate on basic Graph API mail access. A secondary corroborating source (Nylas provider guide,
  `developer.nylas.com/docs/provider-guides/microsoft/verification-guide/`, fetched) confirms the
  same shape: *"No security audit or formal certification is explicitly stated as mandatory"* for
  the base OAuth flow; the real friction it names is the *consent-restriction* UX (unverified-
  publisher warning discouraging click-through), not a cost/timeline barrier.

**Net comparison:** Microsoft's Mail.Read path has a comparable *scare-UI* problem to Google's
(an unverified-publisher warning) but a **categorically lighter cost/timeline burden** to clear
it — free, self-service, "minutes" once the CPP prerequisite exists, vs Google's paid,
weeks-to-months, annually-recurring CASA program. If Cockpit ever does build the full-OAuth
option, Outlook hosts are meaningfully cheaper to serve than Gmail hosts under this model.

---

## Q5 — Safe co-host polling cadence (enrichment beyond email)

**Answer, stated plainly per the honesty bar: there is no published, authoritative "safe cadence"
guidance for polling an authenticated host web session that the platform has not officially
sanctioned — and that absence is itself the finding, not a gap in this research pass.**
Legitimate, sanctioned integrations get told their rate limits directly (an API key with a
documented quota); an unsanctioned session-replay poller is, by construction, trying to look like
something the platform's bot-detection is specifically built to distinguish from a real browsing
human, and no vendor publishes "here is the cadence that defeats our detection" for obvious
reasons. What *is* available, and what this brief grounds the recommendation in, is (a) what
cadence *legitimate, sanctioned* integrations use as a normalcy benchmark, (b) general
anti-thundering-herd engineering practice for the request-spacing mechanics, and (c) the
already-established fact (from prior research) that a funded, *official* Airbnb partner tried
exactly this shape of thing and walked away from it.

**Benchmark 1 — Zapier's own documented polling range for legitimate SaaS integrations:**
`https://help.zapier.com/hc/en-us/articles/15700915877133-Set-up-custom-polling-intervals-in-your-Zaps`
(surfaced via WebSearch, content: *"you can select between 1 and 15 minutes"* for a polling
trigger's check interval, gated by paid-plan tier) — **not independently re-opened via WebFetch
this pass, flagged secondary-only for the exact number**, though it is a widely and consistently
reported figure across the search result set (Zapier's own community/blog posts corroborate the
1–15-minute band). This is a reasonable "looks like normal automation" reference point: a 5–15
minute base interval is within the range real, sanctioned integration platforms use openly.

**Benchmark 2 — Google's own guidance is "prefer push, and if you must poll, poll rarely":**
`https://developers.google.com/workspace/calendar/api/guides/push` (opened, fetched 2026-07-12).
Quote: push notifications *"eliminate the extra network and compute costs involved with polling
resources to determine if they have changed."* The page itself doesn't give a polling number, but
convergent secondary sources describing real-world Calendar-sync implementations consistently
describe 5–15 minute foreground polling with much sparser (hourly/nightly) background
reconciliation passes as the norm when push is unavailable or needs a safety-net — flagged
secondary for the specific numbers, but directionally consistent with Benchmark 1.

**Benchmark 3 — request-spacing mechanics (not "how often," but "how to space it so it isn't a
synchronized, mechanical signature"):** `https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/`
(opened, fetched 2026-07-12) — the canonical, still-authoritative engineering reference for this
problem class. Quote: *"The solution isn't to remove backoff. It's to add jitter"* — three named
algorithms (**Full Jitter**: `random(0, min(cap, base × 2^attempt))`; **Equal Jitter**:
`cap/2 + random(0, cap/2)`; **Decorrelated Jitter**, which uses the previous sleep value to bound
the next one), with **Full Jitter shown as the most effective at breaking synchronized request
patterns** in the post's own benchmark (100 contending clients, >50% call-volume reduction vs.
un-jittered backoff). This is a retry-backoff post, not a bot-evasion post, but the mechanism
transfers directly: a per-host poller with a randomized, non-fixed interval (not "exactly every
10 minutes, forever") looks structurally different from the synchronized, fixed-interval pattern
that both legitimate rate-limiters and bot-detectors are tuned to flag.

**What Cloudflare's own docs say about distinguishing human vs. automated cadence** — genuinely
thin, confirmed by direct fetch: `https://developers.cloudflare.com/waf/rate-limiting-rules/best-practices/`
(opened, fetched) contains **no explicit request-timing/cadence guidance** for what "looks human."
What it does say is that its bot-scoring is primarily ML/fingerprint-driven (JA3/JA4 TLS
fingerprint, behavioral signal, not just request rate), and that its own recommended path for a
*legitimate* recurring automated client is **out-of-band whitelisting** (*"A partner integration
polling an inventory feed will look like a bot and score accordingly, and should be whitelisted
explicitly by IP range or JA3/JA4 fingerprint"* — WebSearch-surfaced summary of Cloudflare's own
docs, not independently re-quoted verbatim from a primary fetch on this specific line, flagged
secondary for the exact wording). **The honest reading: Cloudflare-class bot detection is not
primarily a cadence problem** — a sufficiently slow, jittered poller can still be caught on
TLS/browser fingerprint or behavioral signal, independent of timing. Cadence design reduces the
crudest detection signal; it does not make session-polling safe against a modern managed
challenge/bot-management stack.

**Ground truth this all sits on (from prior research, restated because it's the actual
governing fact):** Airbnb's ToS §11.1 (`https://www.airbnb.com/help/article/2908`, opened, fetched
2026-07-12) states flatly: *"Do not use bots, crawlers, scrapers, or other automated means to
access or collect data or other content from or otherwise interact with the Airbnb Platform."*
No cadence, however slow or jittered, makes automated session-polling *compliant* with this
clause — it only affects the probability of *detection*. And the decisive real-world precedent
(carried over from `research/str-data-ingestion-strategy-2026-07-11.md`, not re-verified live
this pass but flagged there as sourced) is that **PriceLabs — a funded, official Airbnb partner
— shipped a host-session-based Chrome extension and then abandoned it**, pushing hosts to
API/PMS/iCal instead. If an official partner concluded session-based automation wasn't durable
enough to keep shipping, an unsanctioned poller shouldn't be load-bearing infrastructure for
Cockpit either.

### Defensible design, if co-host polling is used at all (enrichment-only, not core path)

1. **Treat it as a low-frequency enrichment layer, not a real-time channel.** Email (from Q1/Q2)
   is the real-time push channel; a co-host session poll should run on the order of the Q5
   benchmarks above — a base interval in the 10–30 minute range, not seconds/minutes.
2. **Full-Jitter randomization on top of the base interval** (per the AWS reference), so no two
   polls for the same host land at a fixed offset, and no fleet-wide synchronized poll wave exists
   across all of Cockpit's hosts at once (stagger by host ID / random per-host phase offset).
3. **Off-peak backoff, not off-peak-only:** bias polling toward hours matching that specific
   host's own login-time distribution (a host who logs in mornings shouldn't get 3am polls) rather
   than a single global "off-peak" window — this is closer to how a real user's own behavior
   looks, and avoids a fleet-wide 24/7-uniform signature.
4. **Hard per-account rate ceiling** (e.g. a fixed max polls/day per host, independent of what
   jitter produces) as a circuit breaker, so a bug can't turn "occasional enrichment poll" into
   "de facto scraping at scale" for one account.
5. **Design for graceful degradation to zero, not detection-evasion as a permanent feature.**
   Given the PriceLabs precedent, the honest engineering posture is: build this as something
   Cockpit can turn off per-host or fleet-wide the moment it becomes unreliable or risky, not as
   permanent core infrastructure the product depends on.

---

## Recommendation detail (expanding the bottom line)

**Phase 1 (pre-revenue / early pilot, first ~dozens–hundreds of hosts): forward-address only.**
Zero Google/Microsoft review surface, zero recurring CASA cost, real data minimization (only the
filtered OTA sender domains ever reach Cockpit), and the setup friction (a guided one-time Gmail
filter wizard) is materially less scary to a non-technical host than an "unverified app (unsafe)"
OAuth warning screen — which directly serves the stated adoption goal (avoid the "needs an IT
person" failure mode). Outlook gets the equivalent inbox-rule wizard (verify Microsoft's exact
forwarding-rule UI before building — flagged `not_found` below).

**Phase 2 (once Cockpit has revenue to fund the recurring CASA line item and wants a true
one-click "connect your inbox" option for hosts who want zero manual setup): add full Gmail OAuth
as an optional upgrade, sitting alongside forwarding, not replacing it.** Budget $540–$8,000+/year
(Tier-dependent, secondary-sourced but from a named CASA lab) plus 4–8+ weeks initial
verification lead time, and design the product so a host is never stuck in Google's "Testing"
7-day-token trap — either fully complete verification before offering OAuth to real users, or
don't offer it at all yet.

**Add Microsoft Graph `Mail.Read` OAuth as a cheaper complement to Gmail OAuth in the same
Phase 2,** since it carries no CASA-equivalent cost — Publisher Verification is free and
"minutes" once the CPP prerequisite exists, and delegated `Mail.Read` needs no admin consent, so
it's a strictly better cost/friction ratio than the Gmail OAuth path for the same phase.

**Document IMAP app-password as a supported fallback for power users only** (mostly relevant to
Gmail personal accounts that keep the app-password exception open); do not build primary
onboarding UX around it given the credential-custody downside, and note it does not exist at all
for Microsoft 365/Exchange Online accounts (fully dead per the retirement doc above).

**Keep co-host session polling out of the critical path entirely.** Use it, if at all, as an
occasional enrichment source under the jittered/rate-capped design in Q5, with an explicit
kill-switch — not as something the product's core value depends on staying undetected.

---

## `not_found` — what this pass could not verify

- **Outlook.com/Exchange forwarding-rule exact click-path and whether Microsoft requires an
  external-forwarding-address confirmation step analogous to Gmail's.** Not independently
  fetched this pass. A Coder building the Outlook onboarding wizard should verify Microsoft's
  current "Inbox rules" / "Automatic forwarding" docs (support.microsoft.com or
  learn.microsoft.com Exchange docs) directly before shipping, rather than assuming Gmail's exact
  flow transfers.
- **The literal, current Gmail OAuth consent-screen wording and screenshot for `gmail.readonly`**
  ("View your email messages and settings") and the exact unverified-app warning copy were
  confirmed via convergent WebSearch snippets referencing Google's own docs, but **not
  independently re-opened as a live screenshot/page fetch this pass** — flagged secondary for the
  precise UI copy (the underlying mechanisms — restricted classification, unverified-app warning
  existing at all — are primary-confirmed).
- **Exact current CASA Tier-2 submission mechanics**: the App Defense Alliance's own page flags
  *"The CASA self scanning process is deprecated"* without describing the replacement in the
  content fetched — re-verify the live submission process at build time, not from this brief,
  since Google/ADA is actively mid-change on this specific mechanic.
- **A quantified, first-party bot-detection cadence threshold from Airbnb/Vrbo/Booking or
  Cloudflare** (e.g. "N requests/hour triggers our ML score above X"). This does not exist in any
  public source found, and per the reasoning in Q5, is unlikely to ever be published by design —
  treat the Q5 "defensible design" section as an engineering-judgment synthesis grounded in
  adjacent legitimate-integration benchmarks and general request-spacing best practice, not as a
  verified platform-specific threshold.
- **The exact current per-tier CASA cost was not sourced from Google directly** (Google
  states it does not set or publish pricing); all dollar figures in this brief trace to one
  secondary blog citing one named lab (TAC Security) plus a second, wider-ranging secondary
  estimate — treat as a directional planning number, get real quotes from 2–3 ADA-authorized labs
  before budgeting precisely.

---

## Full source list (everything opened this pass, with fetch confirmation)

1. `developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification` — opened
2. `developers.google.com/workspace/gmail/api/auth/scopes` — opened
3. `support.google.com/cloud/answer/13465431` (Security Assessment) — opened
4. `support.google.com/cloud/answer/13463817` (Security Assessment FAQ) — opened
5. `support.google.com/cloud/answer/13464323` (When verification is not needed) — opened
6. `support.google.com/cloud/answer/15549945` (Manage App Audience / Testing status) — opened
7. `support.google.com/mail/answer/10957` (Gmail auto-forwarding setup) — opened
8. `knowledge.workspace.google.com/admin/sync/transition-from-less-secure-apps-to-oauth` — opened
9. `support.google.com/accounts/answer/185833` (App passwords) — opened
10. `learn.microsoft.com/en-us/exchange/clients-and-mobile-in-exchange-online/deprecation-of-basic-authentication-exchange-online` — opened in full
11. `learn.microsoft.com/en-us/entra/identity-platform/publisher-verification-overview` — opened in full
12. `graphpermissions.merill.net/permission/Mail.Read` — opened
13. `learn.microsoft.com/en-us/graph/permissions-reference` — opened (partial/truncated result, Mail.Read entry not directly visible in the fetched excerpt — corroborated instead via source #12)
14. `appdefensealliance.dev/casa/tier-2/tier2-overview` — opened
15. `appdefensealliance.dev/casa/tier-2/getting-started` — opened (did not contain tier-assignment criteria)
16. `deepstrike.io/blog/google-casa-security-assessment-2025` — opened (secondary, blog; cited for cost figures, flagged throughout)
17. `developer.nylas.com/docs/provider-guides/microsoft/verification-guide/` — opened (secondary, third-party integration provider's guide)
18. `www.unipile.com/google-oauth-100-user-limit/` — opened (secondary blog; flagged discrepancy on scope classification vs. primary source #2)
19. `developers.google.com/workspace/calendar/api/guides/push` — opened
20. `developers.cloudflare.com/waf/rate-limiting-rules/best-practices/` — opened
21. `aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/` — opened
22. `www.airbnb.com/help/article/2908` (Airbnb ToS, automated-access clause) — opened

Not independently opened this pass (relied on WebSearch snippet convergence only, flagged
secondary in-line above): Zapier's polling-interval help article,
`developers.google.com/workspace/keep/api/troubleshoot-authentication-authorization` (unverified-
app warning copy).
