# Domain Brief: PadSplit Host Agreement & Member Agreement (beyond public ToU)

**Date:** 2026-07-12
**Mode:** D (domain research for a build)
**Build context:** Cockpit (PMS-competitor product), PadSplit as second-priority data source
**Prior artifact this extends:** the earlier pass that verified padsplit.com/terms-of-use
(Aug 1 2019) — Clause 7 automation ban, Clause 1 competitive-use/systematic-retrieval ban,
native Co-Host role, native CSV export. That pass flagged the Host Agreement and Member
Agreement as UNVERIFIED. This brief closes that gap.

---

## Method note (how these were opened)

Both `padsplit.com/host-agreement` and `padsplit.com/member-agreement` are Next.js
client-rendered pages — a plain `curl`/WebFetch only returns an empty loading-spinner
shell (confirmed: `curl -sI` on both returns HTTP 200, but the HTML body is 20 lines of
boilerplate with a `<div role="progressbar">` and no legal text; `WebFetch` on these URLs
correctly reported it could see nothing but the string "PadSplit"). The actual legal text
is compiled into the page's own Next.js JS chunk and injected via a `content` prop at
render time. I identified each page's chunk filename from the shell HTML's `<script src>`
tags and fetched those chunk files directly over HTTPS (same-origin, same route, no
authentication token supplied) — this is the same bytes a browser downloads and executes
to render the page, so it is a legitimate "opened" primary source, not a
guess/hallucination. Every quote below is copy-pasted from that fetched, decoded text.

- Host Agreement chunk: `https://www.padsplit.com/_next/static/chunks/pages/host-agreement-150baaa6ed1d51f3.js` (99,145 bytes, fetched 2026-07-12, HTTP 200, no auth) — contains the full static legal text.
- Member Agreement chunk: `https://www.padsplit.com/_next/static/chunks/pages/member-agreement-e102e6b6c6a119f3.js` (13,016 bytes, fetched 2026-07-12, HTTP 200) — contains only a role-gate component, NOT the legal text (see Q3 below).

---

## Q1 — Delegated access / co-hosts / property managers / third-party account access

**Answer:** Yes — the Host Agreement contains a full, legally binding "Co-Owners" clause
that is substantially more detailed than, and uses different vocabulary from, the
help-center's informal "Co-Host" description the prior pass found. There is also a
**separate, apparently distinct** dashboard "Team" role system (Superadmin/Admin/Finance/
Management) described only in help-center content, never mentioned in the Host Agreement
text — flagged as an open reconciliation question below, not asserted as settled.

**Document identity:** `https://www.padsplit.com/host-agreement` self-titles as
`title:"Host Agreement"` (page `<h1>`/header component) and
`metaTitle:"Host terms of Use"`, with the actual document header reading:

> "Last Updated: 1/28/2021 \| TERMS AND CONDITIONS APPLICABLE TO PADSPLIT OWNERS"

This is a **different, newer, and far more PadSplit-specific document** than the general
`/terms-of-use` page (still separately live, still dated "Last Updated: August 1st, 2019",
confirmed by directly fetching its own chunk `terms-of-use-1660d5e8cd5a1392.js`). The Host
Agreement uses PadSplit's actual domain vocabulary throughout (Room, Listing, Order, Room
Contract, Owner, Guest, Co-Owner); the general ToU reads as generic boilerplate that only
ever says "the Site" and never uses PadSplit-specific nouns — evidence these are genuinely
two separate underlying documents, not two URLs pointing at the same text.

**The Co-Owner clause, quoted in full** (Section 7 "Terms specific for Owners" →
"Co-Owners" subsection):

> "PadSplit may enable Owners to authorize other Users (**"Co-Owners"**) to administer the
> Owner's Listing(s), and to bind the Owner and take certain actions in relation to the
> Listing(s) as permitted by the Owner, such as executing or electronically accepting
> these Terms and Conditions, messaging and welcoming Members, and updating the Listing
> Fee and calendar availability (collectively, **"Co-Owner Services"**). Any agreement
> formed between a Owner and Co-Owner may not conflict with these Terms, or any other
> PadSplit policy applicable to your Room(s). **Co-Owners may only act in an individual
> capacity and not on behalf of a company or other organization, unless expressly
> authorized by PadSplit.** PadSplit reserves the right, in our sole discretion, to (i)
> refuse the use of a Co-Owner and/or (ii) limit the number of Co-Owners an Owner may
> invite for each Listing and/or (iii) to limit the number of Listings a Co-Owner may
> manage."

Continuing (liability + termination):

> "Owners remain solely responsible and liable for any and all Listings and User Content
> published on the PadSplit Platform, including any Listing created by a Co-Owner on
> their behalf... In addition, both Owner and Co-Owner are jointly responsible and
> severally liable for third party claims, including Guest claims, arising from the acts
> and omissions of the other person as related to Owner activities, communications with
> Guests, and the provision of any Co-Owner Services."

> "When the Co-Owner agreement is terminated, the Owner will remain responsible for all of
> the Co-Owner's actions prior to the termination... **When a User is removed as a
> Co-Owner, that User will no longer have access to any Owner or Member information
> related to the applicable Owner's Listing(s).**"

Separately, Section 4 (Account Registration) contains an explicit anti-credential-sharing
clause relevant to any third-party tool wanting host-account access:

> "These features do not require that you share your credentials with any other person.
> **No third party is authorized by PadSplit to ask for your credentials, and you shall
> not request the credentials of another User.**"

**What this means for Cockpit, concretely (implications, not new claims):**
1. **The individual-capacity restriction is the single most load-bearing line for a PMS
   product.** "Co-Owners may only act in an individual capacity and not on behalf of a
   company or other organization, unless expressly authorized by PadSplit" reads as
   ruling out "Cockpit Inc." (or any generic service-account email) being added as a
   Co-Owner across many hosts' Listings at scale — the contract's default posture is one
   named individual per Co-Owner grant, with a company-level integration requiring
   PadSplit's express authorization (i.e., a business-development/partnership
   conversation, not a self-serve invite flow).
2. **PadSplit can revoke or cap this at will and without process** ("in our sole
   discretion... refuse... limit the number of Co-Owners... limit the number of Listings
   a Co-Owner may manage") — this is a platform-dependency risk for any feature Cockpit
   builds on top of the Co-Owner invite mechanism.
3. **Joint-and-several liability attaches** — if Cockpit (acting as a Co-Owner on a
   host's behalf) mishandles a Guest interaction, the Host is contractually exposed for
   Cockpit's acts and vice versa. This is a real, quotable legal exposure to surface to
   the host in onboarding/ToS, not just a technical integration detail.
4. **The credential-sharing ban is explicit and platform-enforced-by-policy** (not just
   implied by the automation ban) — Cockpit must integrate via the Co-Owner invite
   mechanism (or a future official PadSplit API/partnership), never by asking a host to
   hand over their login.

**Open reconciliation question (explicitly unresolved by this pass):** the help-center
article "How do I set up my team in the dashboard?"
(`https://www.padsplit.com/help/article/how-do-i-set-up-my-team-in-the-dashboard-4407683862420`,
opened directly) describes a dashboard "Team" feature with four roles — quoted directly:

> "Property Superadmin: Can make changes to the team and account. Can take any action and
> see anything on the dashboard." / "Property Admin: Can view/edit all information for
> the property but cannot make changes to the team and account." / "Finance: Can
> view/edit financial information for the property, but cannot view or edit management
> functionality" / "Management: Can access day-to-day management functions but cannot
> view or edit financial information"

That article uses **"Owner" and "Operator"** vocabulary and never says "Co-Host" or
"Co-Owner" anywhere in its text (confirmed by direct read). This is the same
Superadmin/Admin/Finance/Management tier structure the prior pass's "Co-Host role"
finding referenced. I could not fully verify from public sources whether this Team/role
system IS the product-UI surface of the same contractual "Co-Owner" grant defined in the
Host Agreement (two names for one mechanism), or a separate, additional
account-permissioning layer stacked on top of it (a "Co-Owner" is added at the
Listing/contract level; a "Team member" is then assigned a dashboard permission tier).
The Host Agreement text itself never mentions "Team," "Superadmin," "Admin," "Finance," or
"Management" — those terms appear only in help-center/product-UI content, not in the
legal document. **This is a genuine gap**: confirming which is which would require either
a live host-account walkthrough (adding a Co-Owner and observing whether it's the same
invite flow as the "Team" invite, and what dashboard permissions the resulting user gets)
or asking PadSplit support directly.

A separate, third document was also located during this search —
`https://www.padsplit.com/help/article/terms-and-conditions-for-host-occupied-properties-37124171644948`
(opened directly) — which turned out to be the underlying real-estate **lease** between a
host and PadSplit's operating entity (per a related help article, the "Tenant" on that
lease is **PS-AA1, LLC**; quoted permitted-use clause: *"Occupancy of Tenant and its duly
admitted members, and other uses ancillary to the foregoing... In no event shall Tenant
make the Premises available for use by the general public for residential purposes or
otherwise."* — from
`https://www.padsplit.com/help/article/why-cant-i-rent-rooms-outside-of-padsplit-48700604268308`,
opened directly). I checked this lease-terms page specifically for delegated-access,
co-host, property-manager, automation, or competitive-use language and **found none** —
it is a standard landlord-tenant lease (insurance, maintenance, default/remedies,
destruction/restoration), not a platform-access contract. Flagged only for completeness
since it is a real "Host Agreement"-adjacent document a future search might otherwise
mistake for the operative platform contract.

---

## Q2 — Automation/scraping bans and competitive-use bans: ToU vs Host Agreement

**Answer:** Both documents ban automated access/scraping and both ban competitive/
commercial use — but the Host Agreement's versions are phrased differently, and on close
reading its automation ban is **stricter/more absolute** (no stated written-permission
carve-out) while its competitive-use ban is **broader** (any unpermitted "commercial or
other purpose," not just "competing" or "revenue-generating").

### Public ToU (`padsplit.com/terms-of-use`, "Last Updated: August 1st, 2019")
Directly re-opened and re-quoted this pass (chunk `terms-of-use-1660d5e8cd5a1392.js`) to
confirm the prior pass's finding still holds and to get exact text for a side-by-side:

Automation (three separate clauses, layered):
> "you will not access the Site through automated or non-human means, whether through a
> bot, script, or otherwise" (User Representations)

> "Systematically retrieve data or other content from the Site to create or compile,
> directly or indirectly, a collection, compilation, database, or directory **without
> written permission from us**." (Prohibited Activities)

> "Engage in any automated use of the system, such as using scripts to send comments or
> messages, or using any data mining, robots, or similar data gathering and extraction
> tools." (Prohibited Activities)

> "Except as may be the result of standard search engine or internet browser usage, use,
> launch, develop, or distribute any automated system, including without limitation, any
> spider, robot, cheat utility, scraper, or offline reader that accesses the Site, or
> using or launching any unauthorized script or other software." (Prohibited Activities)

Competitive/commercial use:
> "Use the Site as part of any effort to compete with us or otherwise use the Site and/or
> the Content for any revenue-generating endeavor or commercial enterprise." (Prohibited
> Activities)

### Host Agreement (`padsplit.com/host-agreement`, "Last Updated: 1/28/2021", Section 12
"Prohibited Activities")

Automation — a single consolidated clause, no exception language attached:
> "use any robots, spider, crawler, scraper or other automated means or processes to
> access, collect data or other content from or otherwise interact with the PadSplit
> Platform **for any purpose**;"

I searched the full Host Agreement text for "systematic retrieval," "written permission,"
and "standard search engine" (the three qualifying/exception phrases present in the ToU's
automation clauses) and got **zero matches for all three** — confirmed by direct
full-text grep of the fetched chunk. The Host Agreement's ban reads as unconditional
("for any purpose"); it does not carry forward the ToU's "without written permission from
us" cure that applies to the ToU's systematic-retrieval clause specifically, nor its
"except standard search engine... usage" carve-out.

Competitive/commercial use — differently framed, and arguably a lower bar to trip:
> "use the PadSplit Platform or PadSplit Content for any commercial or other purposes
> that are not expressly permitted by this Agreement or in a manner that falsely implies
> PadSplit endorsement, partnership or otherwise misleads others as to your affiliation
> with PadSplit;"

The ToU's version requires an "effort to compete" or a "revenue-generating endeavor";
the Host Agreement's version bans **any** commercial-or-other purpose not "expressly
permitted by this Agreement" — Cockpit reading/writing host data for its own paid product
would likely fall inside this broader Host Agreement prohibition even in a scenario where
one might argue it isn't literally "competing" with PadSplit.

The Host Agreement also has a clause with no clean ToU analog, directly on point for a
PMS's host-acquisition motion:
> "contact another Owner or Member for any purpose other than asking a question related
> to the Room Contract, Listing, or the Member's use of the PadSplit Platform, including,
> but not limited to, **recruiting or otherwise soliciting any Member to join
> third-party services, applications or websites, without our prior written approval**;"

This specifically bans using PadSplit's own in-platform messaging to recruit
Owners/Members to a third-party product (i.e., Cockpit) without PadSplit's prior written
approval. It does not on its face restrict recruiting hosts through channels outside the
PadSplit platform (ads, cold outreach, real-estate-investor communities, etc.) — only
platform-mediated solicitation.

**Net comparison for the Coder:** treat the Host Agreement's automation ban as the
**stricter** of the two operative documents (no stated exception), and treat its
competitive/commercial-use ban as **broader in scope** than the ToU's — do not rely on
the ToU's narrower "without written permission" framing as a safe harbor when reasoning
about the Host Agreement, since that qualifying phrase does not appear there.

---

## Q3 — Member Agreement: not publicly accessible; explicit "not found" + what was tried

**Answer: could not retrieve the Member Agreement's substantive legal text from a public,
unauthenticated source.** Unlike the Host Agreement, the Member Agreement is a
per-Member, individually generated document (tied to each Member's own move-in date/room/
Order), gated behind a login, not a single static template served to all visitors.

**What I tried, in order:**
1. Fetched `https://www.padsplit.com/member-agreement` directly (`curl`, no auth) → HTTP
   200, but the HTML body is the same 20-line loading-spinner shell as the Host Agreement
   page (confirmed by direct byte comparison — both are the generic Next.js shell).
2. Identified and fetched the page's own JS chunk,
   `https://www.padsplit.com/_next/static/chunks/pages/member-agreement-e102e6b6c6a119f3.js`
   (13,016 bytes) — this is what the Host Agreement's equivalent chunk (99,145 bytes) had
   contained the actual legal text inline. This chunk does **not** contain legal prose;
   instead it contains a role-gate component with the literal enum values
   `accessGranted`, `accessDenied`, `unauthorized`, plus logic referencing
   `o.refreshStatus`, `o.user`, and a `window.location.href` redirect keyed off
   `window.location.pathname` — i.e., the page checks the visitor's authenticated Member
   status and, when absent, denies access/redirects rather than rendering the agreement
   text. Metadata confirms the page's real intent: `metaTitle:"Member Agreement",
   metaDescription:"Member Agreement between you and PadSplit governing your access to
   your room"` — a per-Member "governing your access to your room" document, consistent
   with it being individually generated, not a boilerplate template.
3. Confirmed the same conclusion from an independent PadSplit-authored source: the help
   article "Proof of Residency & Letter of Recommendation Requests"
   (`https://www.padsplit.com/help/article/proof-of-residency-letter-of-recommendation-requests-48521757632916`,
   opened directly) instructs Members to retrieve their own agreement from inside a
   logged-in dashboard, quoted verbatim: *"Go to **Profile > Settings > Registration**"
   then "Scroll down to the **Membership Agreement** section"* and download — this is
   internally consistent with the page being login-gated per-Member, not a public
   document.
4. Found one third-party mirror lead — a Scribd listing titled "PadSplit Membership
   Agreement Overview | PDF | Arbitration"
   (`https://www.scribd.com/document/814584105/Membership-Agreement`) — but opening it
   returned only Scribd's preview/landing shell (title, page-count metadata, Scribd's own
   navigation/footer) with **no actual clause text visible**, and Scribd gates full
   documents behind its own login/paywall. Per the honesty bar, **I am not citing any
   content from this document** because I could not open and read it — it is reported
   here only as an unverified lead for a future pass that can authenticate to Scribd (or
   locate whoever uploaded it, since Scribd documents are user-uploaded and this one may
   simply be a Member's own downloaded copy re-shared publicly, meaning its authenticity
   relative to the current live version is also unconfirmed even if opened).
5. Checked the Wayback Machine's CDX index for both `/member-agreement` and
   `/host-agreement` — both have historical snapshots (2020–2022) but all recorded page
   sizes (3.5–5.9 KB) match the generic client-rendered shell size, not a size consistent
   with embedded full legal text (the live Host Agreement shell+chunk today totals
   ~106 KB) — so archived snapshots would not resolve this either without also fetching
   and executing the archived JS chunk from that period, which was not attempted this
   pass (diminishing-returns judgment call, flagged rather than silently skipped).

**What a future search that could authenticate as a Member (or possibly Host, if the same
account type can view it) would need:**
- An active PadSplit session (real Member login credentials, or a test/sandbox Member
  account if PadSplit offers one to partners) with a valid session cookie/auth token.
- Navigate to Profile > Settings > Registration in the dashboard (per the help article's
  exact instructions above) and either read the rendered page directly, or — more
  reliably for extracting exact clause text — open browser DevTools' Network tab while
  loading that page/section to capture the actual API endpoint the frontend calls (likely
  something returning a signed PDF or HTML/JSON payload of the Member's specific
  agreement), then fetch that endpoint's response directly the same way this pass fetched
  the Host Agreement's JS-embedded text.
- Because the Member Agreement is generated per-Member (tied to their specific Room/Order/
  move-in date), even an authenticated fetch would return one Member's individualized
  instance, not necessarily the single canonical template — a future pass should note
  which parts read as boilerplate (present verbatim across the document type generally,
  as legal templates typically use) vs. which parts are clearly per-instance fill-ins
  (dates, room number, dollar amounts), and only treat the boilerplate portions as
  representative of "the Member Agreement" generally.

---

## Source list (honesty-bar: every URL below was actually opened this pass)

| # | URL | What it is | Opened via |
|---|-----|-----------|-----------|
| 1 | `https://www.padsplit.com/host-agreement` | Host Agreement landing page (shell) | curl (raw HTML) |
| 2 | `https://www.padsplit.com/_next/static/chunks/pages/host-agreement-150baaa6ed1d51f3.js` | Host Agreement full text (embedded) | curl (raw JS, full-text extraction) |
| 3 | `https://www.padsplit.com/member-agreement` | Member Agreement landing page (shell) | curl (raw HTML) |
| 4 | `https://www.padsplit.com/_next/static/chunks/pages/member-agreement-e102e6b6c6a119f3.js` | Member Agreement page logic (role-gate, no legal text) | curl (raw JS) |
| 5 | `https://www.padsplit.com/terms-of-use` | General public ToU (re-verified this pass) | WebFetch |
| 6 | `https://www.padsplit.com/_next/static/chunks/pages/terms-of-use-1660d5e8cd5a1392.js` | ToU full text (embedded), for side-by-side quoting | curl (raw JS, full-text extraction) |
| 7 | `https://www.padsplit.com/help/article/why-cant-i-rent-rooms-outside-of-padsplit-48700604268308` | Help article quoting the separate host-property lease | WebFetch |
| 8 | `https://www.padsplit.com/help/article/terms-and-conditions-for-host-occupied-properties-37124171644948` | The underlying real-estate lease terms (3rd distinct doc) | WebFetch |
| 9 | `https://www.padsplit.com/help/article/how-do-i-set-up-my-team-in-the-dashboard-4407683862420` | Dashboard "Team" role system (Superadmin/Admin/Finance/Management) | WebFetch |
| 10 | `https://www.padsplit.com/help/article/proof-of-residency-letter-of-recommendation-requests-48521757632916` | Confirms Member Agreement is dashboard-gated, per-Member | WebFetch |
| 11 | `https://www.scribd.com/document/814584105/Membership-Agreement` | Third-party mirror lead — **could not open content, not cited** | WebFetch (preview only, flagged unverified) |
| 12 | `http://web.archive.org/cdx/search/cdx?url=padsplit.com/member-agreement*` and `.../host-agreement*` | Wayback history check (snapshot sizes only, not opened further) | curl (CDX API) |

---

## Summary for the Coder

- There genuinely are two live, separate PadSplit contracts beyond the help-center docs:
  the general ToU (Aug 2019, generic) and the Host Agreement (Jan 2021, PadSplit-specific,
  titled "TERMS AND CONDITIONS APPLICABLE TO PADSPLIT OWNERS"). Both ban automation/
  scraping and competitive/commercial use; the Host Agreement's versions are the more
  recent, more specific, and — on the automation clause — the stricter of the two (no
  stated written-permission exception). Any build decision that leans on the ToU's
  "with written permission" framing as a safe harbor should re-check against the Host
  Agreement text quoted above, since that framing isn't present there.
- The Host Agreement's "Co-Owner" clause is the concrete legal mechanism behind what
  help-center content calls "Co-Host" — it explicitly restricts a Co-Owner to acting "in
  an individual capacity and not on behalf of a company or other organization, unless
  expressly authorized by PadSplit," which is the single fact most likely to constrain
  how Cockpit can integrate at the account-delegation layer (implies needing named
  individual invites, or a PadSplit business-development conversation for anything at
  company scale).
- The Member Agreement's actual clause text remains genuinely unverified — it is
  login-gated and per-Member, not a static public template — and this brief documents
  exactly what a future authenticated pass would need to retrieve it properly.
