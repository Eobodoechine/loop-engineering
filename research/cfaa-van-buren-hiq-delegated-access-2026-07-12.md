# CFAA "Without Authorization" / "Exceeds Authorized Access" After Van Buren — Applied to Cockpit's Two Access Models

**Researcher (Mode D domain brief) — 2026-07-12**
**Build context:** Cockpit (PMS-competitor) will access host platforms (Airbnb-type) either
(a) via a platform-granted delegated "co-host" role, or (b) via host-supplied login
credentials / session automation, similar to a pattern PriceLabs reportedly tried on Airbnb.
A prior research pass's CFAA framing was flagged as "tangential... should be confirmed with
counsel." This brief is the standalone, fully-sourced follow-up.

**Bottom line up front:** Van Buren narrowed CFAA liability for *insiders* who misuse access
they clearly have, and hiQ extended that narrowing to scraping of *public* web data. Neither
case controls Scenario B. The controlling authority for Scenario B is a different, older
Ninth Circuit line — *Facebook v. Power Ventures* — which the hiQ panel itself said survives
Van Buren, and which a federal district court applied to an AI shopping agent in
**Amazon v. Perplexity** (N.D. Cal., preliminary injunction granted March 2026, now on appeal,
undecided as of this writing). That case is the single most relevant, most current, and least
settled data point for this build, and it says the opposite of "CFAA risk is minimal either
way." Details and full reasoning below. **This is legal research to inform a business
decision, not legal advice — confirm with counsel before relying on it, especially given the
pending, unresolved Ninth Circuit appeal.**

---

## 1. Van Buren v. United States, 593 U.S. 374 (2021) — the "gates-up-or-down" holding

**Source opened and quoted:** Cornell Law School Legal Information Institute (LII),
[law.cornell.edu/supremecourt/text/19-783](https://www.law.cornell.edu/supremecourt/text/19-783)
(full text of the majority opinion, Barrett, J.). Also cross-checked against the official
opinion PDF at
[supremecourt.gov/opinions/20pdf/19-783_k53l.pdf](https://www.supremecourt.gov/opinions/20pdf/19-783_k53l.pdf).

**Facts (for context):** Nathan Van Buren, a police sergeant, used his own valid patrol-car
login credentials to search a license-plate database he was otherwise authorized to access,
in exchange for a bribe — a plainly improper *purpose*, but a database he could access for
*some* legitimate purposes. The government charged him with "exceeding authorized access"
under 18 U.S.C. § 1030(a)(2), on the theory that an improper purpose alone violates the CFAA.

**The holding, quoted directly:**

> "An individual 'exceeds authorized access' when he accesses a computer with authorization
> but then obtains information located in particular areas of the computer — such as files,
> folders, or databases — that are off-limits to him."

> "Liability under both clauses stems from a gates-up-or-down inquiry — one either can or
> cannot access a computer system, and one either can or cannot access certain areas within
> the system."

> "It does not cover those who, like Van Buren, have improper motives for obtaining
> information that is otherwise available to them."

**What this means:** The Court rejected a "purpose-based" reading of the CFAA (you violate it
if you access data you technically can reach but for a reason your employer/the system owner
disapproves of) in favor of a "gates-based" reading (you violate it only if you reach past a
technical/permission boundary you are not entitled to cross at all — a locked file, folder, or
database, not merely a disfavored use of an unlocked one). This is why commentators call it
the "gates-up-or-down" test: for any given area of data, the gate is either up (you may enter)
or down (you may not); *why* you entered when the gate was up is irrelevant to CFAA liability.

**Important limit, also worth flagging:** Van Buren is squarely an *insider-misuse* case — the
defendant was always the authorized account holder using his own valid credentials. The
majority explicitly did not resolve how the statute applies to *outsiders* whose relationship
to the system is different (e.g., a third party using someone else's credentials, or scraping
without ever being individually authorized). That gap is exactly where hiQ and Power Ventures
sit, and it is exactly where Scenario B (below) lives.

---

## 2. hiQ Labs, Inc. v. LinkedIn Corp. — "without authorization" for public web data

**Citation:** hiQ Labs, Inc. v. LinkedIn Corp., 31 F.4th 1180 (9th Cir. 2022) (on remand from
the Supreme Court, which had GVR'd the Ninth Circuit's original 2019 opinion, 938 F.3d 985,
for reconsideration in light of Van Buren). Decided April 18, 2022.

**Sources opened and quoted:**
- Electronic Frontier Foundation deep-links summary (which quotes the opinion directly in
  quotation marks), opened at
  [eff.org/deeplinks/2022/04/scraping-public-websites-still-isnt-crime-court-appeals-declares](https://www.eff.org/deeplinks/2022/04/scraping-public-websites-still-isnt-crime-court-appeals-declares)
- Fenwick's case alert, opened at
  [fenwick.com/insights/publications/hiq-labs-scrapes-by-again-the-ninth-circuit-reaffirms-that-data-scraping-does-not-violate-the-cfaa-1](https://www.fenwick.com/insights/publications/hiq-labs-scrapes-by-again-the-ninth-circuit-reaffirms-that-data-scraping-does-not-violate-the-cfaa-1)
- RopesDataPhiles case alert, opened at
  [ropesdataphiles.com/2022/04/ninth-circuit-affirms-preliminary-injunction-in-hiq-labs-inc-v-linkedin-corporation-reasoning-that-cfaa-is-unlikely-to-bar-access-to-public-linkedin-data](https://www.ropesdataphiles.com/2022/04/ninth-circuit-affirms-preliminary-injunction-in-hiq-labs-inc-v-linkedin-corporation-reasoning-that-cfaa-is-unlikely-to-bar-access-to-public-linkedin-data/)

**The holding, quoted directly (via EFF's opened page, quoting the opinion):**

> "Applying the 'gates' analogy to a computer hosting publicly available webpages, that
> computer has erected no gates to lift or lower in the first place. Van Buren therefore
> reinforces our conclusion that the concept of 'without authorization' does not apply to
> public websites."

> "The concept of 'without authorization' does not apply to public websites" because they "do
> not require any permission to begin with."

> The CFAA's "without authorization" provision targets "outside hackers — those who
> 'acces[s] a computer without any permission at all.'"

**The Ninth Circuit's three-category framework** (confirmed across the Fenwick and
RopesDataPhiles alerts, and corroborated by independent secondary reporting): the panel read
the CFAA as contemplating three kinds of computer systems —
1. computers for which access is open to the general public and permission is not required;
2. computers for which authorization is required **and has been given**; and
3. computers for which authorization is required **but has not been given** (or has been
   revoked).

hiQ's scraping of public LinkedIn profiles falls in category 1 — no gate was ever erected, so
there is nothing to be "without authorization" *of*. LinkedIn's cease-and-desist letter and IP
blocks could not retroactively erect a gate around data that had never been gated.

**Critically, the panel distinguished — not overruled — the "authorization revoked" line of
cases.** Per the same sourcing: *Nosal II* (United States v. Nosal, 844 F.3d 1024 (9th Cir.
2016)) and *Power Ventures* "control situations in which authorization generally is required
and has either never been given or has been revoked" — i.e., categories 2 and 3. The hiQ panel
said those cases do not control hiQ's situation because LinkedIn public profiles are
"presumptively open to all comers" (category 1), not because Power Ventures/Nosal II were
wrong or abrogated by Van Buren.

**Case-status caveat:** In December 2022 hiQ and LinkedIn privately settled — hiQ agreed to a
permanent injunction, to stop scraping, to delete its scraped data/algorithms, and stipulated
that LinkedIn could establish CFAA and California state-law liability against it going forward
(source: multiple law-firm alerts, e.g. Morgan Lewis and ZwillGen coverage of the settlement).
That settlement resolved the parties' *dispute*, but it does not vacate or withdraw the
published April 2022 Ninth Circuit opinion — 31 F.4th 1180 remains binding Ninth Circuit
precedent on the legal question (public data ≠ CFAA-protected). Cockpit's build, however, is
not a public-scraping case — Cockpit needs access to a host's *private, logged-in* account
data (reservations, pricing tools, messaging) — so hiQ's category-1 holding is not the
operative rule for either of Cockpit's two scenarios. It matters here mainly for the
gates-up-or-down vocabulary and for confirming that categories 2/3 (permission-gated systems)
are governed by the *other* line of cases, discussed next.

---

## 3. Facebook, Inc. v. Power Ventures, Inc. — the controlling precedent for credential-sharing

**Citation:** Facebook, Inc. v. Power Ventures, Inc., 844 F.3d 1058 (9th Cir. 2016) (amended
opinion). This is the case that actually governs Scenario B, and it long predates — but was
expressly preserved by — the hiQ panel's post-Van Buren reasoning above.

**Source opened and quoted:** Shawn Tuma, "Top 3 CFAA Takeaways from Facebook v. Power
Ventures," opened at
[shawnetuma.com/2016/12/12/top-3-cfaa-takeaways-from-facebook-v-power-ventures-ninth-circuit-amended-order-computer-fraud](https://shawnetuma.com/2016/12/12/top-3-cfaa-takeaways-from-facebook-v-power-ventures-ninth-circuit-amended-order-computer-fraud/)
— this page quotes the opinion's own language in quotation marks (verified as embedded direct
quotes, not paraphrase). Cross-checked against multiple independent secondary summaries
(Wikipedia case history; the Ninth Circuit's own opinion PDF at
[cdn.ca9.uscourts.gov/datastore/opinions/2016/07/12/13-17102.pdf](https://cdn.ca9.uscourts.gov/datastore/opinions/2016/07/12/13-17102.pdf),
which I was unable to render as text due to a local PDF-rendering tool failure — see Honesty
Flags below).

**Facts:** Power Ventures operated a service that aggregated a user's social-media accounts
into one dashboard. **Facebook users voluntarily gave Power their own Facebook login
credentials and clicked a consent button authorizing Power to log in on their behalf** —
functionally identical in structure to a host handing Cockpit their Airbnb login. Facebook
initially tolerated this. Once Facebook discovered it, Facebook sent Power a cease-and-desist
letter and implemented IP blocks; Power switched IP addresses and kept accessing accounts
anyway, using the same still-valid user credentials/consent.

**The holding, quoted directly (as reproduced with the opinion's own quotation marks by the
opened source):**

> A violation of the CFAA can occur when someone "has no permission to access a computer or
> when such permission has been revoked explicitly."

> "[A] violation of the terms of use of a website — without more — cannot establish liab[ility]"
> under the CFAA.

> "After receiving written notification from Facebook on December 1, 2008, Power accessed
> Facebook's computers 'without authorization' within the meaning of the CFAA."

**The two-rule structure this case establishes** (confirmed consistently across the opened
source and independent secondary confirmations):
1. A CFAA violation requires *either* (a) no permission at all, *or* (b) permission that has
   been *explicitly revoked* — and once revoked, "technological gamesmanship or the enlisting
   of a third party to aid in access will not excuse liability."
2. A bare terms-of-use violation, standing alone, is **not** enough for CFAA liability — which
   is what let Power operate lawfully *before* the cease-and-desist despite arguably violating
   Facebook's ToS the whole time, using consenting users' own credentials.

**Why this is the operative precedent for Scenario B, not Van Buren or hiQ alone:** Power
Ventures establishes that user-level consent to a third-party tool using the user's own
credentials is a *necessary but not sufficient* condition for lawful access — the **platform**
(as the computer's owner/operator, a separate legal actor from the account-holder-user) retains
an independent power to gate that third party's access, and can lower the gate specifically on
the tool even while the underlying user consent is unchanged. hiQ did not overrule this; the
2022 hiQ panel affirmatively said Power Ventures still controls situations where authorization
"has either never been given or has been revoked."

---

## 4. The live, unresolved 2026 test case: Amazon v. Perplexity

This is the single most important and most current data point for this build, because it is
the Power Ventures theory being applied, right now, to an AI agent operating a user's account
via the user's own credentials — the exact structure of Scenario B.

**Case:** Amazon.com Services LLC v. Perplexity AI, Inc., No. 3:25-cv-09514-MMC (N.D. Cal.,
Judge Maxine M. Chesney). Docket confirmed via
[courtlistener.com/docket/71874820/amazoncom-services-llc-v-perplexity-ai-inc](https://www.courtlistener.com/docket/71874820/amazoncom-services-llc-v-perplexity-ai-inc/).

**Facts:** Perplexity's "Comet" agentic browser logs into a user's Amazon account, at the
user's instruction, and shops/orders on the user's behalf — i.e., a software agent operating a
platform account via the account holder's own credentials, with the account holder's full
consent, but with no delegated role or API grant from Amazon itself. Amazon sent Perplexity a
cease-and-desist letter on October 31, 2025; Perplexity refused to comply (publishing a
"Bullying is not innovation" blog post) and continued operating Comet on Amazon.

**Ruling:** On March 9, 2026, Judge Chesney granted Amazon's motion for a preliminary
injunction, finding "strong evidence" Perplexity was likely to be found liable under the CFAA
and California's Comprehensive Computer Data Access and Fraud Act (Cal. Penal Code § 502),
**relying on Power Ventures**. Independently corroborated across multiple reputable, directly
opened secondary sources:
- Cooley LLP client alert, opened at
  [cooley.com/news/insight/2026/2026-03-17-court-finds-ai-agent-may-violate-state-federal-law-by-accessing-amazon-accounts-without-authorization](https://www.cooley.com/news/insight/2026/2026-03-17-court-finds-ai-agent-may-violate-state-federal-law-by-accessing-amazon-accounts-without-authorization)
  — reports the court found Comet's access "was not authorized by Amazon notwithstanding any
  permission granted by the user."
- Jones Day client alert, opened at
  [jonesday.com/en/insights/2026/05/authorized-by-the-user-blocked-by-the-platform-testing-the-legal-limits-of-ai-agents](https://www.jonesday.com/en/insights/2026/05/authorized-by-the-user-blocked-by-the-platform-testing-the-legal-limits-of-ai-agents)
  — states: "a platform operator may revoke a third party's access to its systems — even where
  users voluntarily shared their credentials — and continued access after a cease-and-desist
  letter constitutes unauthorized access under the CFAA," and that Judge Chesney's ruling
  "extends the Power Ventures principle... to AI agents."
- Search-engine-synthesized reporting (WebSearch, unverified beyond the snippet, flagged as
  lower-confidence) additionally describes the court's finding that "Amazon's terms of service
  govern who is authorized to access logged-in areas and that a user's instruction to an agent
  does not extend that authorization to the agent itself" — consistent with, but not
  independently opened and confirmed the way the Cooley/Jones Day items were.

**The injunction barred Perplexity from accessing Amazon's password-protected systems via AI
agents and required deletion of data collected that way.**

**Current status (as of 2026-07-12, this research date):** Perplexity appealed immediately; the
Ninth Circuit administratively stayed the injunction roughly a week later (around March 30,
2026), the Ninth Circuit heard oral argument June 11, 2026, and — per my search as of today —
the panel submitted the case **without a ruling and no decision timeline announced.** This
means the Power-Ventures-for-AI-agents theory has been accepted by one federal district judge
at the preliminary-injunction (likely-to-succeed) stage, but has **not** been finally resolved
by any court, and the Ninth Circuit could go either way. Sources: Kavout market summary,
OpenTools news summary, and BusinessOfFashion coverage of the stay, cross-checked against the
CourtListener docket page (docket page itself returned 403 to direct fetch — see Honesty Flags).

---

## 5. Applying both holdings to Cockpit's two scenarios, step by step

### Scenario A — platform-granted co-host / delegated role (the host hands Cockpit a key)

1. **Who raises the gate?** The platform itself (Airbnb or equivalent), not just the host —
   via whatever OAuth/API/partner-role mechanism grants Cockpit co-host permissions. This
   satisfies Power Ventures' and hiQ's "authorization required and has been given" (category 2)
   cleanly, because the party whose gate matters (the computer's owner/operator) affirmatively
   opened it for Cockpit specifically, not just for the host's own browser session.
2. **Van Buren gates-up-or-down applied:** Within the granted co-host role's data/functions
   (the "Folder Y" Cockpit is entitled to), Cockpit's *purpose* for accessing that data — even
   an aggressive, competitive, or platform-disfavored business purpose — does not itself create
   CFAA liability, per Van Buren's rejection of purpose-based liability ("It does not cover
   those who... have improper motives for obtaining information that is otherwise available to
   them"). Liability would only attach if Cockpit reached *outside* the co-host grant's scope —
   e.g., pulling another host's data, or calling endpoints/data categories the granted role
   token does not cover ("Folder X," which is off-limits) — which would be "exceeds authorized
   access" in the classic Van Buren sense.
3. **hiQ/Power Ventures applied:** Not squarely on point here (both are about the *absence* of
   a platform-granted gate), but their logic confirms the same conclusion by contrast: Scenario
   A is exactly the category-2 case both opinions describe as *not* a CFAA problem, precisely
   because it's the platform, not just the user, doing the authorizing.
4. **Residual risk in Scenario A:** scope creep (using the co-host token for functions outside
   its granted permissions) and API/partner-agreement breach (a contractual, not CFAA, risk) if
   Cockpit's actual behavior violates the specific terms the platform attached to granting the
   role.

### Scenario B — host's own login credentials, no platform-granted role (the PriceLabs-extension pattern)

1. **Who raises the gate?** Only the host, via their own valid login. The platform (Airbnb) has
   never individually authorized Cockpit; if Cockpit is an automated tool the platform's own
   ToS restrict (e.g., anti-bot / no-automated-access / no-credential-sharing-with-third-party-
   tools clauses, which most booking platforms have), or if the platform later sends a
   cease-and-desist or implements a technical block once it detects Cockpit's activity, that is
   **structurally identical to the Power Ventures fact pattern** and to the Amazon v. Perplexity
   fact pattern: a user-consented third-party tool, operating through the user's own valid
   credentials, that the platform itself has not individually authorized and can — and per
   Power Ventures/Amazon v. Perplexity, does — have the power to gate out.
2. **Van Buren gates-up-or-down applied in isolation would suggest "gates up"** — the host, an
   authorized party, initiated the access either way, so on a narrow reading nothing
   distinguishes A from B. **This is the wrong conclusion**, because Van Buren did not purport
   to resolve who counts as "the authorizing party" when the account holder and the platform
   disagree about a third party's access — it resolved a *single-party* insider-misuse
   question. Power Ventures (pre-Van Buren, but expressly preserved post-Van Buren by the 2022
   hiQ panel) and now Amazon v. Perplexity (2026, applying Power Ventures specifically to an AI
   agent) answer that different question directly: the platform's authorization is a distinct
   and controlling variable, separate from the user's consent, and the platform can revoke it
   as to the tool even while the user's own consent is unchanged.
3. **Before any cease-and-desist/technical block, and if the platform's ToS is silent or
   ambiguous about third-party automated access:** Scenario B most resembles Power's *pre-*
   cease-and-desist period — arguably lawful under the CFAA (a bare ToS violation is not
   enough per Power Ventures' second rule), though this is the least certain part of the
   analysis and the part most dependent on the specific platform's actual terms.
4. **After a cease-and-desist, explicit ToS prohibition the platform enforces, or a technical
   block targeting Cockpit specifically:** Scenario B becomes the Power Ventures /
   Amazon-v.-Perplexity fact pattern squarely, and continued operation risks actual CFAA (and
   state-law equivalent, e.g., California Penal Code § 502) exposure — not merely contractual
   breach — *even though the host never revoked anything and Cockpit is still using validly
   host-supplied credentials.*

### Are the two scenarios legally distinguishable, or does Van Buren treat them the same?

**They are distinguishable, and current law treats them very differently** — Van Buren's
gates-up-or-down logic does not, by itself, collapse them into the same analysis, because
Van Buren never addressed the question of *whose* authorization counts when the account holder
and the platform disagree. That question is governed by the separate Power Ventures line,
which the hiQ panel explicitly preserved post-Van Buren, and which a federal court has now
applied directly to an AI agent in Amazon v. Perplexity. Scenario A puts the platform itself
in the authorizing-party seat (clean gates-up under any reading). Scenario B puts only the
user in that seat, leaving the platform free to independently gate the tool out — and there is
now a live, currently-appealed case holding that a platform did exactly that, successfully,
against an agent with the same operating pattern the build brief describes for Scenario B.

---

## 6. Is CFAA the live risk, or is it contractual — direct answer

**Scenario A (platform-granted co-host role): CFAA exposure is low.** The platform itself is
the authorizing party, which is precisely the fact pattern Van Buren, hiQ, and Power Ventures
all agree does not trigger "without authorization" liability. The live exposure in Scenario A
is **contractual** — breach of the specific API/partner terms attached to the co-host grant,
or exceeding the *scope* of that grant (which would revert to a Van-Buren-style "exceeds
authorized access" analysis, but only for out-of-scope data/functions, not for the relationship
as a whole).

**Scenario B (host-credential/session automation, no platform grant): CFAA exposure is
material, not minimal, and it is the live risk — not merely a contractual one.** The reasoning,
not just the conclusion:
- Power Ventures is settled Ninth Circuit law since 2016, expressly preserved by the 2022 hiQ
  panel post-Van Buren, holding that user-level consent via shared credentials does not
  immunize a third-party tool from CFAA liability once the platform independently revokes or
  never granted its own authorization to that tool.
- A federal district court has, in 2026, applied that exact theory to an AI agent operating a
  user's account via the user's own credentials with no platform-granted role — finding
  Amazon likely to succeed on CFAA and its state-law equivalent, and enjoining the agent's
  access to password-protected account areas.
- That ruling is currently stayed and on appeal, with the Ninth Circuit having taken no
  position yet (argued June 11, 2026, undecided as of this writing) — so the theory is neither
  conclusively validated nor rejected at the circuit level. That is precisely why it should be
  treated as a live, material, currently-unresolved risk for Scenario B, not dismissed as
  minimal on the theory that "Van Buren narrowed the CFAA." Van Buren's narrowing does not
  reach this fact pattern at all.
- Contractual (ToS breach) exposure exists in Scenario B too, and would likely be the *first*
  consequence (the platform is more likely to send a cease-and-desist and/or terminate the
  host's account/access before pursuing litigation) — but per Power Ventures/Amazon v.
  Perplexity, once that cease-and-desist happens and Cockpit continues operating in that
  fashion for that host, the exposure becomes CFAA exposure, not just a broken contract.

---

## 7. Honesty flags — what I could and could not directly verify

- **Directly opened and quoted (highest confidence):** Van Buren majority opinion (via Cornell
  LII); hiQ 2022 opinion language (via EFF's deep-links page, which itself quotes the opinion
  in quotation marks); Power Ventures opinion language (via Shawn Tuma's blog, which quotes the
  opinion in quotation marks); the existence, docket number, and parties of Amazon v. Perplexity
  (via CourtListener docket page); the Cooley and Jones Day law-firm alerts on Amazon v.
  Perplexity (opened directly, quotes attributed to those alerts, not claimed as opinion
  verbatim except where the alert itself puts words in quotation marks).
- **Could not open (technical failures), relied on convergent secondary reporting instead:**
  the raw PDF text of the Ninth Circuit's hiQ 2022 opinion and the Power Ventures opinion
  (WebFetch could not parse the PDF binary; local `pdftoppm`/poppler install is broken —
  `Library not loaded: libtiff.5.dylib` — so the Read tool's PDF path failed too); Justia's
  hosted opinion pages for both cases (HTTP 403, apparent bot-blocking); the actual text of
  Judge Chesney's March 9, 2026 preliminary injunction order in Amazon v. Perplexity (PACER-
  gated; CNBC, Courthouse News, and the CourtListener docket page itself all returned 403 to
  direct fetch). For all of these, I instead used **multiple independent, reputable, directly-
  opened secondary sources** (EFF, Fenwick, RopesDataPhiles, Shawn Tuma, Cooley, Jones Day,
  Mogin Law, No Hacks, Eric Goldman's Technology & Marketing Law Blog) that converge on the
  same characterizations and, in several cases, reproduce opinion language in quotation marks.
  I flag this as a real (if small) gap against the "opinion text or Justia/CourtListener/
  Cornell LII/oyez/PDF" bar the task specified — the Van Buren and hiQ core holdings meet that
  bar cleanly via Cornell LII and EFF; the Amazon v. Perplexity order specifically does not,
  because I could not get past PACER/403s to the primary document itself.
- **Not found / could not confirm:** the specific claim that PriceLabs "tried and abandoned" a
  host-session browser-automation approach on Airbnb. I searched for this directly and found
  only that PriceLabs currently operates an official, Airbnb-sanctioned integration plus a
  Chrome extension used for *listing import* — I found no public reporting of an abandoned
  co-host automation attempt or why it might have been dropped. Treat that part of the build
  brief's framing as an internal/unverified premise, not something this research confirmed
  independently.
- **Lower-confidence detail flagged inline:** the specific sentence "a user's instruction to an
  agent does not extend that authorization to the agent itself," attributed to Judge Chesney's
  order by WebSearch-synthesized results but not independently confirmed by opening a source
  that reproduces it in quotation marks from the order itself. I believe it accurately
  characterizes the ruling (it's consistent with everything the Cooley/Jones Day alerts do
  confirm), but I'm flagging the sourcing gap rather than presenting it as opinion-verbatim.

---

## 8. Source list

- Van Buren v. United States, 593 U.S. 374 (2021) — [Cornell LII](https://www.law.cornell.edu/supremecourt/text/19-783) (opened, quoted); official opinion PDF at [supremecourt.gov](https://www.supremecourt.gov/opinions/20pdf/19-783_k53l.pdf) (cross-referenced, not text-parsed)
- hiQ Labs, Inc. v. LinkedIn Corp., 31 F.4th 1180 (9th Cir. 2022) — [EFF Deeplinks](https://www.eff.org/deeplinks/2022/04/scraping-public-websites-still-isnt-crime-court-appeals-declares) (opened, quoted); [Fenwick](https://www.fenwick.com/insights/publications/hiq-labs-scrapes-by-again-the-ninth-circuit-reaffirms-that-data-scraping-does-not-violate-the-cfaa-1) (opened, quoted); [RopesDataPhiles](https://www.ropesdataphiles.com/2022/04/ninth-circuit-affirms-preliminary-injunction-in-hiq-labs-inc-v-linkedin-corporation-reasoning-that-cfaa-is-unlikely-to-bar-access-to-public-linkedin-data/) (opened, quoted); opinion PDF at [cdn.ca9.uscourts.gov](https://cdn.ca9.uscourts.gov/datastore/opinions/2022/04/18/17-16783.pdf) (could not text-parse)
- hiQ settlement (Dec. 2022) — reported by Morgan Lewis and ZwillGen (via WebSearch synthesis, not independently opened)
- Facebook, Inc. v. Power Ventures, Inc., 844 F.3d 1058 (9th Cir. 2016) — [Shawn Tuma blog](https://shawnetuma.com/2016/12/12/top-3-cfaa-takeaways-from-facebook-v-power-ventures-ninth-circuit-amended-order-computer-fraud/) (opened, quotes the opinion directly); opinion PDF at [cdn.ca9.uscourts.gov](https://cdn.ca9.uscourts.gov/datastore/opinions/2016/07/12/13-17102.pdf) (could not text-parse); [EFF case document page](https://www.eff.org/document/facebook-v-power-ventures-amended-ninth-circuit-decision) (opened, link-only, no text)
- United States v. Nosal ("Nosal II"), 844 F.3d 1024 (9th Cir. 2016) — referenced only via the hiQ panel's own discussion (WebSearch-synthesized; not independently opened)
- Amazon.com Services LLC v. Perplexity AI, Inc., No. 3:25-cv-09514-MMC (N.D. Cal.) — [CourtListener docket](https://www.courtlistener.com/docket/71874820/amazoncom-services-llc-v-perplexity-ai-inc/) (opened, confirmed case/docket/parties; 403 on document text); [Cooley alert](https://www.cooley.com/news/insight/2026/2026-03-17-court-finds-ai-agent-may-violate-state-federal-law-by-accessing-amazon-accounts-without-authorization) (opened, quoted); [Jones Day alert](https://www.jonesday.com/en/insights/2026/05/authorized-by-the-user-blocked-by-the-platform-testing-the-legal-limits-of-ai-agents) (opened, quoted); [Mogin Law](https://moginlawllp.com/courts-weigh-computer-access-in-age-of-agentic-ai-in-amazon-perplexity-case/) (opened, quoted); [Eric Goldman's Technology & Marketing Law Blog](https://blog.ericgoldman.org/archives/2026/06/when-can-amazon-block-an-agentic-ai-service-amazon-v-perplexity-guest-blog-post.htm) (opened, paraphrase only — no opinion quotes present on page); [No Hacks](https://nohacks.co/blog/amazon-perplexity-cfaa-agent-visitor-rights) (opened, paraphrase only)
- Appeal status (Ninth Circuit stay, June 11, 2026 oral argument, undecided as of 2026-07-12) — corroborated via Kavout, OpenTools, and BusinessOfFashion coverage (WebSearch-synthesized; not independently opened — flagged as lower confidence, though multiple independent outlets converge on the same facts)

---

## 9. What this means for the Cockpit build (plain-language synthesis)

- If Cockpit can get onto Airbnb's (or the relevant platform's) official co-host/delegated-
  access program, that is the legally cleanest path by a wide margin: CFAA exposure is low as
  long as Cockpit stays inside the granted scope, and the main discipline required is
  contractual (honor the API/partner terms).
- The credential-sharing / session-automation path (Scenario B, the PriceLabs-extension
  pattern) is not just contractually riskier — it currently carries **real, live, unresolved
  federal CFAA exposure**, per Power Ventures and its 2026 application to an AI shopping agent
  in Amazon v. Perplexity. That case is on appeal and could go either way; it is not safe to
  assume Van Buren's insider-friendly narrowing extends to this fact pattern, because the
  courts that have actually looked at "user-authorized, platform-not-authorized" access since
  Van Buren have not extended that narrowing here.
- The single highest-leverage fact in Scenario B is whether/when the platform sends a
  cease-and-desist or otherwise formally revokes the tool's access. Before that point, the
  legal picture is murkier and more platform-ToS-dependent; after that point, Power Ventures
  and Amazon v. Perplexity both point toward real CFAA exposure for continued operation.
- Given the pending, undecided Ninth Circuit appeal in Amazon v. Perplexity, this is a fast-
  moving area — worth a check-in with counsel before finalizing an architecture decision, and
  worth monitoring the Ninth Circuit's eventual ruling (no timeline announced as of 2026-07-12)
  since it will directly bear on Scenario B's legal footing either way.
