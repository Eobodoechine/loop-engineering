# Domain Brief: Airbnb Host-Only-Fee Migration — Live Status Check (as of 2026-07-12)

**Mode:** D (domain research for a build) — Cockpit (PMS-competitor) data-acquisition strategy
**Researcher run date:** 2026-07-12
**Requested by:** Oga, re-verifying a prior research pass's time-sensitive claim before it informs a build decision.

---

## Question 1 — Current official Airbnb wording on fee-model eligibility + migration timeline

### What I could actually open directly

**Source A — Airbnb Help Center, "Airbnb service fees," `https://www.airbnb.com/help/article/1857`**
Opened directly via WebFetch (succeeded, unlike most other airbnb.com URLs tried — see honesty notes below). Verbatim quotes pulled from the live page:

- Split fee: *"Most hosts pay a 3% service fee, but some pay more. Hosts pay a 4% fee for listings in Brazil and Mexico."* / *"This fee structure is split between the host and the guest."*
- Single/host-only fee: *"Most hosts pay 15.5%, remaining hosts typically pay 14%-16%, and hosts pay a 16% fee for listings in Brazil and Mexico."*
- Current eligibility language: *"This fee structure is mandatory for certain hosts, including traditional hospitality listings (e.g., hotels, serviced apartments, etc.), hosts who use property management software, and hosts in countries subject to this fee structure."*
- Confirms the migration explicitly reaches non-PMS hosts: *"To help hosts who don't use property management software adjust their pricing when they transition from the split-fee structure to the single-fee structure, we built a new price adjustment tool in the app."*
- No specific migration date appears on this particular page, and no visible "Last updated" stamp — only a `© 2026 Airbnb, Inc.` footer.

**Honesty flag on this source:** article/help pages are JS-rendered SPAs; my tool renders them via a fetch+summarize pass, not a full browser, so I cannot 100% rule out truncation. But the quotes above are specific and internally consistent across two separate fetch attempts with different prompts, which is the strongest confirmation I can get without a real browser.

**Source B — Airbnb Resource Center, "Simplifying service fees on Airbnb," `https://www.airbnb.com/resources/hosting-homes/a/simplifying-service-fees-on-airbnb-771`**
This is the page that actually carries the Sept 15 / Oct 13, 2026 dates. **I could NOT open this page directly** — WebFetch returned `403 Forbidden` on three separate attempts (this URL and the sibling articles `-746` and `-761` all 403'd; help-center article 1857 was the only airbnb.com page that let me in). I instead confirmed the page's content two ways: (1) a `site:airbnb.com "September 15" 2026 fee` search, which returned this exact URL from Google's index with the snippet *"The deadline to adjust prices is September 15 if you live outside the European Economic Area... The fee being implemented is based on Airbnb's global average service fees of 15.5%. If hosts don't take action before their deadline, their prices and payouts per night will be lower"*; (2) a repeat search that pulled a second, consistent snippet from the same URL: *"The deadline to adjust your prices is September 15 if you live outside the European Economic Area and October 13 if you live within it."* Both snippets are attributed by the search tool to the airbnb.com/resources URL itself, not to a third-party blog.

**Downgrade this to secondary-verified, not primary-opened.** I never rendered the page myself; I'm relying on a search index's snippet extraction of an airbnb.com page. It is genuinely airbnb-domain-sourced (confirmed twice, independently, via `site:` search), but it is one level removed from my own eyes on the page, unlike Source A.

**Mechanism, per the same snippet:** *"Airbnb built a tool that helps you adjust prices across all your listings at once to account for the single service fee... The single service fee will only apply to reservations made after you switch to a single fee."* — i.e., the deadline isn't a hard cutover where bookings stop; it's a repricing deadline, after which the host's un-adjusted price simply pays out less (fee comes out of the same nightly rate) rather than the listing being blocked.

### Answer to Q1
Airbnb's live Help Center (article 1857) currently lists three mandatory triggers for the host-only fee — traditional hospitality listings, PMS-connected hosts, and "hosts in countries subject to this fee structure" — and explicitly says it built a price-adjustment tool for hosts who **don't** use PMS, confirming the migration is not limited to API-connected hosts. The specific Sept 15, 2026 (non-EU) / Oct 13, 2026 (EU) deadline lives on a separate Resource Center page which I could only confirm via search-index snippets, not a direct render — treat the exact date as airbnb-domain-sourced-but-not-personally-verified.

---

## Question 2 — Recent (last 30–60 days) rollout-status reporting: on schedule, delayed, or cancelled?

### Timeline reconstructed across sources (each dated where verified)

| Date | Event | Source (opened) |
|---|---|---|
| 2020–2021 | Most software-connected hosts outside the Americas moved to ~15% host-only | RentalScaleUp, `rentalscaleup.com/airbnb-host-fees/`, **updated Jul 8, 2026** |
| Aug 25, 2025 | New Airbnb accounts using a PMS auto-placed on host-only fee | WebSearch synthesis, repeated across multiple secondary sources (not independently opened on a primary page) |
| Oct 27, 2025 | Mandatory host-only fee for PMS/API-connected hosts | Confirmed on RentalScaleUp (opened) + Futurestay (opened, published Apr 27, 2026) + Hostaway (opened, published Dec 5, 2025) |
| ~Dec 1, 2025 | Narrower event: non-PMS hosts who had **already voluntarily opted into single-fee pricing** standardized to 15.5% (NOT a forced migration of all manual hosts) | RentalScaleUp `airbnb-host-only-fee/`, opened, published/updated Oct 10, 2025: *"Dec 1, 2025 → Most non-PMS hosts already on single-fee also standardize to 15.5%"* |
| ~Dec 2025 (uncertain — see flag below) | A LinkedIn post attributed to Stacey St. John states: *"Airbnb has officially pushed out the mandatory single-fee rollout for hosts NOT connected via a PMS into 2026,"* describing a Dec-1-2025-scheduled full non-PMS mandatory rollout as delayed into a phased 2026 schedule | LinkedIn post, opened via WebFetch. **Date flag:** the fetch tool reported "Post Date: 7 months ago (approximately July 2024)" — that arithmetic is internally inconsistent (7 months before 2026-07-12 is ~Dec 2025, not mid-2024), so I do not trust the tool's absolute-date conversion here. Treat this as a real post from roughly late 2025, content unverified beyond the tool's summary; I could not re-derive the exact date myself. |
| Apr 13, 2026 | Remaining PMS-connected hosts worldwide moved to 15.5% | RentalScaleUp (opened, Jul 8 2026 update); corroborated by Futurestay (opened) |
| May 25, 2026 | Peru and South Korea — **first non-PMS/manual-host countries** moved | RentalScaleUp, opened, Jul 8 2026 update: *"May 25, 2026: hosts in Peru and South Korea — the first no-software countries"* |
| Jun 22, 2026 | Germany and the UK — next non-PMS/manual-host wave | Same source, same quote block |
| **Jul 2026 (ongoing, i.e. right now)** | Airbnb actively emailing hosts — **including US self-managed/non-PMS hosts** — that the single fee takes effect Sept 15, with a repricing deadline | Multiple WebSearch-synthesized snippets, consistent across at least 4 independent queries and corroborated by Tabivista (opened directly, page states "Last updated: July 9, 2026") |
| Sep 15, 2026 (non-EU) / Oct 13, 2026 (EU) | Stated final/mop-up deadline for the "all hosts including non-PMS" wave | Airbnb Resource Center `-771` (secondary-verified per Q1 above); repeated by ~10 independent secondary blogs |

### Rollout-status verdict
**On schedule, not delayed, not cancelled — with one caveat.** No source found (direct or secondary) reports a delay, postponement, or cancellation of the currently-stated Sept 15 / Oct 13, 2026 dates. The only delay I found in the record is the *earlier* one (a Dec-1-2025-slated full non-PMS rollout that got rescheduled into 2026's phased country-by-country wave), which itself now appears to be executing on schedule: hosts are receiving repricing-deadline emails **right now, in July 2026**, roughly two months ahead of Sept 15 — which matches the pattern RentalScaleUp's tracker explicitly names: *"an email and a Resource Center post roughly two months ahead, then a hard deadline."*

**Caveat / evidence tension I want to flag rather than paper over:** RentalScaleUp's own timeline table — the single most rigorously wave-dated source I found, and the most recently updated (Jul 8, 2026, four days before this research run) — **stops at the June 22, 2026 Germany/UK wave** and does not itself list Sept 15 or Oct 13, 2026. Its author instead writes *"it is probable that all hosts will need to make the move, worldwide"* and *"Next: more countries, on the same pattern"* — i.e., as of Jul 8, 2026, this particular tracker had not yet logged a confirmed date for the US/remaining-country wave, even though the Sept 15/Oct 13 dates are already circulating elsewhere (and even though hosts are apparently already receiving the deadline emails, per other sources dated Jul 9, 2026). This is a one-source gap, not a contradiction — it's plausible RentalScaleUp simply hadn't updated that specific table row yet — but I'm flagging it because it's the difference between "confirmed by the most careful tracker" and "confirmed everywhere except the most careful tracker."

**Trade press:** I was not able to open **Skift** or **PhocusWire** — PhocusWire returned `403 Forbidden` on the one relevant-looking URL I found (`phocuswire.com/airbnb-changes-service-fee-otas-hotels`), and I found no Skift article specifically on this topic via search (the query returned only the same secondary-blog cluster, no skift.com hit). **Hospitable** (a co-hosting/STR-software vendor, directly relevant to Cockpit's space) has a support article confirming the "all hosts" framing and referencing the Oct 27, 2025 PMS deadline, but its own service-fee comparison page (`help.hospitable.com/en/articles/4703232-...`) 403'd on WebFetch both times I tried; content came through only via a WebSearch snippet pass, which I'm treating as secondary. **I could not independently verify a genuine host-focused trade-press piece (Skift/PhocusWire) reporting live rollout status** — this is a real gap in coverage, not a confirmed absence of press coverage.

---

## Question 3 — Does the migration treat co-host (delegated, non-API) accounts the same as fully manual hosts?

This is the load-bearing question for Cockpit's strategy, and it has a **split answer**: one part is solidly confirmed, one part is a genuine unresolved gap.

### Confirmed: co-host logins structurally cannot authorize a PMS/API connection at all (today)
Via Guesty's own help-center content (relayed through WebSearch snippets — **I attempted to open `help.guesty.com/hc/en-gb/articles/30966052858781-Integrating-Airbnb-co-host-listings` directly twice and got `403 Forbidden` both times**, so this is secondary-sourced, not primary-opened):
- *"An Airbnb restriction blocks co-hosted listings from being managed by a PMS, even if you have full co-host permissions."*
- *"Airbnb does not support using a co-host account to authorize PMS for listings management, and the host account must be connected instead."*
- Workaround PMS vendors use: *"invite the host to connect their Airbnb account to Guesty, and the host's listings must remain connected to Guesty"* — i.e., the primary host, not the co-host, has to be the one who authorizes the API connection.

This confirms that, **mechanically**, a co-host-only login (Cockpit's dashboard-access model) is not even capable of triggering Airbnb's PMS/API-connection flag — the connection literally isn't offered at that permission level. That's a real, structural (not just policy) fact, at least as things stand today.

### Unresolved: does that protection survive the Sept 2026 "all hosts" wave?
**I found no source — official or secondary, primary-opened or search-relayed — that explicitly states co-host-managed accounts are exempt from, or subject to, the Sept 15/Oct 13 2026 all-hosts migration.** I searched specifically for this (`"co-host" Airbnb "host-only fee" trigger`, `co-host NOT API manual exempt split fee`, reddit and community-forum searches) and got nothing that named co-hosts in the context of the 2026 fee migration.

What the evidence *does* show, and why I read it as pointing against an exemption:
- Help Center article 1857's current eligibility list is **country-based and host-based**, not connection-based: *"hosts in countries subject to this fee structure"* is an open-ended criterion tied to the host account and its country, with no mention of how the account is operated day-to-day.
- The Resource Center page (Q1, Source B) explicitly extends the tool and deadline to hosts who **don't** use PMS — the "all hosts including non-PMS" framing that every secondary source repeats is about connection status being *irrelevant* to this final wave, which is the opposite of a carve-out for a specific access mode.
- No vendor page (Hospitable, Guesty, Hostaway, PriceLabs) — all of which have a direct commercial incentive to publicize any co-host loophole to their own customers — mentions one. If a co-host exemption existed and mattered, it's the kind of thing a PMS vendor blog would be shouting about right now, given how much of their July 2026 content is specifically about this deadline.

**My honest read:** the Sept 2026 wave is being described everywhere as a host/country-level cutover, not a connection-level one, so a delegated co-host account almost certainly moves with its host's account regardless of how the co-host accesses it — but this is inference from an absence of a stated exemption, not a quoted confirmation. Flag this to Oga as **not_found with a leaning**, not as a settled fact.

---

## `not_found` — explicitly unanswered

- **Exact wording of the Sept 15/Oct 13, 2026 deadline as rendered on airbnb.com** — I could not get past `403 Forbidden` on the Resource Center pages themselves; my confirmation is search-snippet-level, not a direct render. If this date needs to be load-bearing for a build decision, it should be re-confirmed by a human opening `https://www.airbnb.com/resources/hosting-homes/a/simplifying-service-fees-on-airbnb-771` in a real logged-in browser (the bot-block may be tied to lacking a session/cookie).
- **Skift or PhocusWire's own reporting on this specific rollout** — not found despite multiple targeted searches; PhocusWire's one relevant-looking URL 403'd.
- **Any explicit Airbnb statement on co-host-managed accounts and the 2026 all-hosts fee migration** — searched multiple angles, found nothing naming co-hosts in this context either way.
- **Whether "hosts in countries subject to this fee structure" (the exact current Help Center eligibility language) has a published country list** — not found; the phrase reads as intentionally vague/rolling as the country-by-country wave proceeds.

---

## Bottom line for Cockpit's strategy

1. The host-only-fee migration for non-API-connected hosts is **real, actively rolling out right now (July 2026), and — as far as every source I could reach shows — on schedule** for Sept 15, 2026 (non-EU) / Oct 13, 2026 (EU). No credible evidence of delay or cancellation surfaced.
2. The **current, structural** protection for co-host/delegated-dashboard access (Airbnb won't let a co-host login authorize a PMS/API connection) is real and confirmed by PMS-vendor documentation — but this protection is about the **PMS/API-status trigger specifically**, which is a *different* trigger than the country/host-level "all hosts" trigger landing in ~2 months.
3. **The single biggest open risk for the build:** I could not find any evidence that co-host-operated accounts are exempt from the Sept/Oct 2026 all-hosts wave, and the framing of every source I found (country- and host-account-based, not connection-based) suggests they are **not** exempt. If Cockpit's fee-avoidance strategy depends on the co-host route surviving past Sept 15/Oct 13, 2026, that assumption is not supported by anything I found and should be treated as unconfirmed-and-likely-false rather than a safe planning assumption.

---

### Full source list (opened vs. secondary-relayed)

**Opened directly (WebFetch succeeded):**
- `https://www.airbnb.com/help/article/1857` — Airbnb Help Center, "Airbnb service fees" (no visible update date; opened twice)
- `https://www.rentalscaleup.com/airbnb-host-fees/` — updated Jul 8, 2026
- `https://www.rentalscaleup.com/airbnb-host-only-fee/` — published/updated Oct 10, 2025
- `https://www.futurestay.com/read/airbnb-15-5-percent-host-fee-explained-2026` — published Apr 27, 2026
- `https://www.tabivista.com/blog/airbnb-host-fees-2026/` — published Mar 1, 2026, last updated Jul 9, 2026
- `https://www.hostaway.com/blog/airbnb-host-only-fee-what-to-know-about-the-15-percent-host-fee/` — published/updated Dec 5, 2025
- `https://staceystjohn.com/airbnb-host-fees/` — published Aug 28, 2025
- `https://staceystjohn.com/airbnb-property-management-vs-co-hosting-whats-the-difference/` — no date shown (no fee-structure content found)
- `https://www.linkedin.com/posts/staceystjohn_airbnb-quietly-updated-their-service-fee-activity-7405290367396573184-T3kZ` — date uncertain, tool's absolute-date conversion is internally inconsistent (flagged above)
- `https://www.airbnb.com/help/article/3389` — "How co-host payouts work" (no fee-structure/PMS content found)

**403 Forbidden / could not open (secondary-relayed via WebSearch only):**
- `https://www.airbnb.com/resources/hosting-homes/a/simplifying-service-fees-on-airbnb-771` (the actual Sept 15/Oct 13 source page — confirmed via `site:airbnb.com` search snippets instead)
- `https://www.airbnb.com/resources/hosting-homes/a/simplifying-airbnb-service-fees-746`
- `https://help.hospitable.com/en/articles/4703232-airbnb-service-fees-split-fee-vs-host-only-fee`
- `https://help.hospitable.com/en/articles/8889941-airbnb-using-other-software-with-airbnb-limited-connection` (partially opened — got a co-host/PMS-account quote but no fee-structure content)
- `https://help.guesty.com/hc/en-gb/articles/30966052858781-Integrating-Airbnb-co-host-listings` (the co-host/PMS-block source — relayed via WebSearch snippet only)
- `https://www.phocuswire.com/airbnb-changes-service-fee-otas-hotels`
- `https://community.withairbnb.com/*` (multiple community forum URLs tried, all 403'd)
- `https://www.maxreservations.com/airbnbs-new-15-5-host-only-fee-...`
