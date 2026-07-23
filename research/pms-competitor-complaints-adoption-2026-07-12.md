# Domain Brief: Incumbent PMS/Channel-Manager Customer Complaints, by Theme and Product

**Date:** 2026-07-12
**Mode:** D (domain research for a build) — Cockpit (STR + PadSplit PMS competitor)
**Question:** Find concrete, sourced customer complaints about Hostaway, Guesty, OwnerRez,
Lodgify, Hospitable on pricing, reliability, data accuracy, support, and onboarding friction —
and assess whether the evidence supports the thesis that email-invite/co-host-style onboarding
(no API keys, no dev setup) would be materially easier than what these incumbents require today.

## Access notes (read this before the quotes — it bounds what's verified vs not)

Per the honesty bar (open every source before citing it), here is exactly what I could and
could not open directly:

- **Capterra** — worked reliably for all 5 products. Every quote below marked `[Capterra, verified]`
  was extracted from a page I opened myself via WebFetch on the live review-listing URL.
- **Software Advice** — worked for Hostaway. Marked `[Software Advice, verified]`.
- **BNBCalc** (editorial "team of Superhosts" reviews) — worked. Marked `[BNBCalc, verified]`;
  note this site's own prose claims are editorial, not user quotes, and I've kept the two apart.
- **G2** (`g2.com/products/.../reviews`) — returned **HTTP 403 Forbidden** on every attempt
  (Hostaway, Guesty, both with and without `?qs=pros-and-cons`). I could not open it. Any
  G2-attributed text below came only from WebSearch's own synthesized answer (which itself
  claims to summarize G2 review content) — it is marked `[G2, via WebSearch synthesis — NOT
  independently opened/verified by me]` and should be treated as directionally suggestive,
  not a confirmed primary quote.
- **TrustRadius** — same problem: `trustradius.com/products/.../reviews` returned 403 on every
  attempt. Marked the same way, unverified.
- **Trustpilot** (`trustpilot.com/review/lodgify.com`, `hospitable.com`, and the `ca.` subdomain)
  — 403 Forbidden on every attempt. Unverified.
- **Airbnb Community Center** (`community.withairbnb.com`) — the one directly relevant thread I
  found ("Guesty vs. Hospitable — which do you prefer?") returned 403 Forbidden. Unverified.
- **Reddit** (r/AirBnBHosts, r/vacationrentals, r/PropertyManagement, r/Hosting) — **completely
  inaccessible in this environment.** WebFetch on `www.reddit.com` and `old.reddit.com` both
  returned a hard tool error ("Claude Code is unable to fetch from www.reddit.com" /
  "...old.reddit.com"). WebSearch with `allowed_domains: ["reddit.com"]` returned an API error:
  *"The following domains are not accessible to our user agent: ['reddit.com']."* Unrestricted
  WebSearch queries (8 different phrasings, including product-name combinations, "switched
  from X," "worst channel manager experience," "onboarding took forever") returned **zero**
  reddit.com URLs in the result set across the entire session. This is a hard environment
  limitation, not a lack of effort — I am flagging it per the honesty bar rather than
  fabricating or inferring Reddit content. **Gap: no Reddit-sourced quotes in this brief.**
  If Reddit evidence specifically is required, it needs either a different fetch tool/proxy or
  a human to pull screenshots/text manually.

Bottom line on sourcing: the quotes below that are NOT marked "unverified" are real quotes I
opened and read myself, with reviewer role and date as shown on the page. Treat the marked
G2/TrustRadius/Trustpilot/Airbnb-Community lines as leads only.

---

## Part 1 — Complaints organized by theme

### Theme: Pricing / billing surprises

**Hostaway**
- "A bit pricey compared to others. So far, I am not seeing value for monthly cost." — Linda Y.,
  Owner, Hospitality, <6 months (May 14, 2026) `[Capterra, verified]`
- "Wildly expensive" — Ben R., Director of Operations, Real Estate, 6–12 months (Sept 18, 2025)
  `[Capterra, verified]`
- "International charges for subscriptions should also be communicated up front" — James H.,
  Owner, Hospitality, 1–2 years (Feb 24, 2026) `[Capterra, verified]`
- "constant price increases" — reviewer role/date not shown `[Software Advice, verified]`
- Aggregate claim (not a quote): "Hostaway takes a percentage of the booking fee for direct
  bookings (despite calling it a free booking engine)... Hostaway also has lots of hidden fees
  which users weren't aware of prior to using it." `[WebSearch synthesis of G2 — unverified,
  page returned 403]`

**Guesty**
- "They kept charging me anyway. It has been 4 to 5 months of back and forth." — Kevin L., CEO,
  2–10 employees (April 6, 2026) `[Capterra, verified]`
- "Pricing is not very competitive compared to other channels." — Lina L., General Manager,
  2+ years (March 23, 2026) `[Capterra, verified]`
- "Pricing is also on the high side, especially for smaller operators." — PANAGIOTIS T., CEO,
  1–2 years (Nov 21, 2025) `[Capterra, verified]`
- "Its costly and accounting is very complicated and analytics are very limited, everything is
  an additional expense which is very frustrating." — Jennifer P. (as quoted on Capterra, relayed
  via BNBCalc's review) `[BNBCalc, verified — BNBCalc itself opened and quoted this Capterra
  review; I did not independently re-locate this specific reviewer on Capterra's own page, so
  treat as one level removed from primary]`
- Aggregate claim (not a quote): "Guesty Pro typically requires a $500+ onboarding fee... Guesty
  charges additional 'hidden' fees on top, like a cancellation fee, and a history of rounding up
  %'s to the nearest dollar, and suddenly increasing their commission percentage." `[WebSearch
  synthesis of G2/other aggregators — unverified]`

**OwnerRez**
- No billing-surprise complaints surfaced in the Capterra pages I opened (259 reviews, 4.9/5).
  Cost was mentioned only positively: "ALso, it is less expensive!" — Natalie W., Owner,
  Hospitality, <6 months (July 30, 2025) `[Capterra, verified]`, and "uses straightforward,
  usage-based pricing that's very cost-effective for single or small-portfolio STR owners" —
  Verified Reviewer, Co-Owner, Real Estate, 2+ years (Sept 2025) `[Capterra, verified]`.
  OwnerRez is the one product in this set where pricing is a stated *strength*, not a complaint,
  in the sources I could open.

**Lodgify**
- "wish pricing wasn't quite as expensive" — Michelle K, Owner, Hospitality, 1–2 years
  (Feb 2026) `[Capterra, verified]`
- "It's expensive, especially when you want to use all the extended features" — Gertrud M.,
  Property Manager, Hospitality, <6 months (May 2026) `[Capterra, verified]`
- "The fact that there isn't a lower charge when you are using some [features only]" —
  Katerina M., Hospitality, 6–12 months (Feb 2026) `[Capterra, verified]`
- "took my nightly cost in pesos and just changed it to USD without [notice]" — Thomas H., CEO,
  Hospitality, <6 months (Oct 2025) `[Capterra, verified — currency conversion billing bug]`

**Hospitable**
- No pricing complaints surfaced in the Capterra pages I opened for Hospitable.com (143
  reviews). This is a genuine gap, not a "clean bill" — I only had Capterra as a verified
  source for this product; Trustpilot (where a pricing thread more plausibly lives) returned
  403.

### Theme: Reliability / sync bugs / downtime

**Hostaway**
- "Financial information doesn't flow through correctly for platforms like VRBO and Hopper" —
  Kara K., Senior Associate, Accounting, 6–12 months (July 7, 2025) `[Capterra, verified]`
- "I have had huge issues with syncing pricing across platforms." — Kim G., Owner, Real Estate,
  <6 months (Nov 1, 2025) `[Capterra, verified]`
- "Issues with exporting, for example not all prices got synchronised correctly" — Anouk K.,
  Reservation Manager, Leisure/Travel/Tourism, <6 months (May 7, 2026) `[Capterra, verified]`
- "Their app and website go down in the middle of the day for up to an hour" — Ben R., Director
  of Operations, Real Estate, 6–12 months (Sept 18, 2025) `[Capterra, verified]`
- "the VRBO integration had bugs and issues and did not work for about 3 weeks to connect,
  during that time we had a double booking" — reviewer role/date not shown `[Software Advice,
  verified]` — this is a direct data-accuracy/reliability failure (a double booking) tied
  explicitly to channel-connection bugs.

**Guesty**
- "It took months to identify the issue, and still to this day, guesty still hasn't identified
  how it happened." — Clay L., CTO, 2–10 employees `[Capterra, verified]`
- "Synchronization problems and loss of configurations following certain updates." — Marco L.,
  Owner, 6–12 months (March 30, 2026) `[Capterra, verified]`
- "We still are not connected to VRBO after 3 weeks." — Victoria M., Property Manager, <6 months
  (Nov 26, 2025) `[Capterra, verified]`

**Lodgify**
- "only allowing even hour check ins and check outs" [a calendar/booking-rule bug] — Michelle K,
  Owner, Hospitality, 1–2 years (Feb 2026) `[Capterra, verified]`
- "two properties were cross mapped to the wrong Vrbo listings" — Mohammed B., Owner,
  Hospitality, <6 months (July 2026) `[Capterra, verified — this is a data-accuracy failure:
  bookings could land against the wrong property]`
- "Some glitches with Airbnb adding additional guests after initial booking" — April M., Owner,
  Real Estate, 1–2 years (Oct 2025) `[Capterra, verified]`
- Aggregate claim (not a quote): "reservations are not syncing correctly with Booking.com, which
  is causing major operational and financial problems for some operators." `[WebSearch synthesis
  — unverified against a primary page I could open, though directionally consistent with the
  verified Mohammed B. cross-mapping quote above]`

**Hospitable**
- "Things break constantly" — ahmed M., Owner, Hospitality, Self-employed (Nov 7, 2025)
  `[Capterra, verified]`
- "Some of their features simply don't work, so you're not getting what you're paying for...
  Some are very core features like automated messages or auto-syncing with Airbnb." — Verified
  Reviewer, Owner, Hospitality (May 27, 2025) `[Capterra, verified]` — notable because
  auto-sync failing is exactly the data-accuracy risk (missed/duplicate bookings) that a PMS
  exists to prevent.

**OwnerRez**
- No reliability/sync-bug complaints surfaced in the OwnerRez Capterra pages I opened; the
  closest is a feature-delay complaint: "When something is 'on the way,' it can take longer
  than expected" — Andrew W., CEO, Hospitality (Jan 17, 2026) `[Capterra, verified]`, which is
  a roadmap/feature-lag complaint, not a live-bug complaint.

### Theme: Support responsiveness

**Hostaway**
- "No one picks up the phone or calls back when you try to use that option." — Kim G., Owner,
  Real Estate, <6 months (Nov 1, 2025) `[Capterra, verified]`
- "Support ticket has been escalated for almost 3 days, with limited responses" — Kim G. (same
  reviewer, Nov 1, 2025) `[Capterra, verified]`
- "I had my issues ignored for days on end...would not return emails or phone calls" — Ben R.,
  Director of Operations, Real Estate, 6–12 months (Sept 18, 2025) `[Capterra, verified]`
- "support take along time to get back to you" `[Software Advice, verified, role/date not shown]`
- "It was frustrating to email with two separate support staff, both of which said our booking
  windows were opening up due to something we were doing and offered no answers" `[Software
  Advice, verified, role/date not shown]`

**Guesty**
- "Every time I reach out it feels like we are starting over. No real progress." — Kevin L.,
  CEO, 2–10 employees (April 6, 2026) `[Capterra, verified]`
- "The amount of time it took to resolve a group billing issue — over three weeks." — Kaylyn V.,
  AGM, 6–12 months (Dec 2, 2025) `[Capterra, verified]`

**Lodgify**
- "Replies took days. When we escalated, we were told the mapping is a self[-service issue]" —
  Mohammed B., Owner, Hospitality, <6 months (July 2026) `[Capterra, verified]`
- "Support has been completely unhelpful...pure rudeness from 'Support'" — Tom Y., Real Estate,
  <6 months (June 2025) `[Capterra, verified]`

**Hospitable**
- "The ticket was closed during a holiday without resolution." — Kristy K., Co-owner, Marketing
  and Advertising, 2–10 employees (Jan 2, 2026) `[Capterra, verified]`
- "Absolutely nightmare of a customer service... None of the agents know anything." — ahmed M.,
  Owner, Hospitality, Self-employed (Nov 7, 2025) `[Capterra, verified]`
- "Their support team is very bad." — Verified Reviewer, Owner, Hospitality (May 27, 2025)
  `[Capterra, verified]`

**OwnerRez**
- "Really not much [support] — at all — if anything it was you needed to scheduled a call" —
  Carl P., Owner, Hospitality (Jan 20, 2025) `[Capterra, verified]`
- "I need more one on one help and I'm happy to pay for 30 min or hour sessions" — Nicole D.,
  Owner, Real Estate (April 28, 2025) `[Capterra, verified]`
- "Unable to chat on the phone. I feel phone chat enables the area of concern to be fully
  understood" — Sandy W., Owner Operator, Hospitality (May 21, 2025) `[Capterra, verified]`
- Counter-note: OwnerRez support is also praised heavily in the same review set ("She was so
  patient with us and provided great support through helpful support articles and screen
  sharing" — Harold R., Owner, Real Estate, Nov 14, 2025 `[Capterra, verified]`) — support here
  reads as "good when you get a human, but access to a human (phone/live chat) is limited,"
  which is a different complaint shape than Hostaway/Guesty's "we tried to reach them and got
  nothing."

### Theme: Onboarding / setup friction (the core question)

This is the theme most directly relevant to the "email-invite, no API keys, no dev setup" thesis,
so I'm keeping the full quotes with context rather than trimming.

**Hostaway**
- "I had a difficult time getting my on board started" and found "the onboarding a week or so
  out which is to long" — Keelan P., Owner, Real Estate (May 23, 2026) `[Capterra, verified]`
- "The initial setup was more time-consuming than expected, there's a lot to configure" —
  Sonya M., Property Manager, Hospitality (Oct 29, 2025) `[Capterra, verified]`
- "I didn't realize how much work there is to be done and how long it takes" — Robin C., Owner,
  Hospitality (July 3, 2025), whose fuller review (per direct re-fetch) describes the
  integration process taking "MANY hours" of personal prep work and frustration at having to
  "follow up directly with Hostaway's affiliated partners rather than having comprehensive
  onboarding support" `[Capterra, verified]`
- "setup process can feel a bit overwhelming at first" due to the number of features to learn —
  Julie C., Property Manager, Hospitality (Oct 16, 2025) `[Capterra, verified]`
- Editorial claim (not a user quote): "creating and fully setting up an account can take
  anywhere from 2 to 8 hours in total." `[BNBCalc, verified — this is BNBCalc's own summary
  claim, distinguished here from a direct user quote per the honesty bar]`

**Guesty**
- **"Needs an IT person in your team, at least for the first steps."** — Jeff M., CTO, Real
  Estate (Nov 26, 2025) `[Capterra, verified]` — this is the single most directly on-point
  quote in this brief for the adoption thesis: a reviewer who is themselves a CTO says Guesty's
  setup needs IT-level involvement, at least initially.
- "we still are not connected to VRBO after 3 weeks" — Victoria M., Property Manager, <6 months
  (Nov 26, 2025) `[Capterra, verified]` — channel connection can stall for weeks post-signup.
- Positive counter-examples exist too (see Part 2 nuance below): "found the onboarding and set
  up process to be pretty straight forward" — Simon P., Founder, Real Estate (May 29, 2026)
  `[Capterra, verified]`; "implementation specialist...took me from being completely new to the
  platform to being proficient in a very short period" — John R., President, Real Estate
  (March 6, 2026) `[Capterra, verified]`.

**Lodgify**
- "onboarding was great, connectivity to OTA's takes some waiting" — Adam W., Owner, Hospitality
  (Dec 16, 2025) `[Capterra, verified]` — explicitly separates "the vendor's onboarding" (fine)
  from "OTA-side connection" (slow) — an important structural distinction, see synthesis below.
- "The Vrbo integration sat inactive for weeks after onboarding" — Mohammed B., Owner,
  Hospitality (July 9, 2026) `[Capterra, verified]`
- "onboarding took longer than the 14-day cool-off period" — Alessandro G., Owner, Accounting,
  <6 months (Sept 2025) `[Capterra, verified]`
- Currency-conversion setup bug during Airbnb import + failed Stripe account setup — Thomas H.,
  CEO, Hospitality (Oct 27, 2025) `[Capterra, verified]`

**OwnerRez**
- "A little difficult to know where to go if you aren't very tech savvy" — Jessica T., Owner,
  Real Estate, Self-employed (Jan 13, 2025) `[Capterra, verified]`
- "The amount of information to learn ~ the capabilities are so incredible but its overwhelming"
  — Natalie W., Owner, Hospitality, Self-employed (July 30, 2025) `[Capterra, verified]`
- "The learning curve is high but the more times you go into the program you learn faster" —
  Harold R., Owner, Real Estate, Self-employed (Nov 14, 2025) `[Capterra, verified]`
- "When we went to integrate with channels it was not easy and places like VRBO kept trying to
  connect it to the prior owner's account" — Kristy O., Owner, Real Estate (June 16, 2026)
  `[Capterra, verified]` — a channel/identity-resolution failure on the OTA side, not really
  fixable by any PMS vendor's own onboarding UI.

**Hospitable**
- "It's not the easiest to stop and think through what and when the messaging goes out... It
  takes a lot of energy [to] process to map your business." — Kami M., CEO, Hospitality
  (Sept 19, 2020) `[Capterra, verified]`
- "It's not magic. You have to sit down and learn and try and test certain features. So it does
  take some time to learn what are the best settings that suit your needs." — Yaroslav L.,
  Investor, Real Estate (April 3, 2020) `[Capterra, verified]`
- Note: these are the only two onboarding-specific comments in the Hospitable Capterra set I
  could open, and both are dated 2020 — old relative to the other products' 2025-2026 review
  clusters. This is a real coverage gap for Hospitable specifically.

---

## Part 2 — Does the evidence support the "email-invite/co-host onboarding beats incumbents" thesis?

**Short answer: partially supports it, with an important structural caveat the Coder needs to
know before over-claiming this in positioning.**

**What supports the thesis:**
1. Setup is consistently measured in **hours to weeks**, not minutes, even at vendors that are
   rated well overall (Hostaway 4.8/5 Capterra, OwnerRez 4.9/5 Capterra). "2 to 8 hours"
   (BNBCalc's own estimate for Hostaway), "a week or so" (Keelan P.), "MANY hours" of personal
   prep (Robin C.), "took longer than the 14-day cool-off period" (Alessandro G., Lodgify) — none
   of this reads as "connect and go."
2. **A CTO reviewer explicitly names the technical bar**: "Needs an IT person in your team, at
   least for the first steps" (Jeff M., Guesty). This is direct evidence that at least one
   incumbent's setup exceeds what a non-technical host/co-host can self-serve.
3. Every one of the four products with substantial review volume (Hostaway, Guesty, Lodgify,
   OwnerRez) needed a **scheduled, human-staffed onboarding call/specialist** as the mechanism
   that made setup tractable at all — repeatedly cited as the *reason reviews are positive*
   ("The dedicated onboarding support was key to my choice" — Adam W., Lodgify; "onboarding
   process was fantastic; I received a one-on-one, in-depth walkthrough" — Anna J., Guesty).
   That is itself evidence of friction: the incumbents have had to build a white-glove human
   layer to compensate for setup complexity, rather than making the product self-serve.
4. Multiple hosts across products report the OTA-connection step (Airbnb/VRBO/Booking.com) as a
   multi-week bottleneck even after the vendor's own onboarding was fine (Adam W.'s
   "connectivity to OTA's takes some waiting"; Victoria M.'s "3 weeks" VRBO wait; Mohammed B.'s
   "sat inactive for weeks"; Kristy O.'s prior-owner VRBO account collision).

**The caveat — read this before positioning Cockpit's onboarding claim:**
Point 4 above cuts both ways. A meaningful fraction of the "onboarding took weeks" complaints are
about **OTA-side channel connection/approval** (VRBO account mapping, Booking.com sync, Airbnb
API connection), not about the PMS vendor's own signup flow or UI. That delay is largely outside
any PMS vendor's control — it's Vrbo/Booking.com's own account-linking and approval process. An
email-invite/co-host-style onboarding model would very plausibly fix the *vendor-side* friction
(no scheduled call, no IT person needed, no multi-hour manual configuration) — the evidence above
supports that cleanly. But it would **not**, by itself, fix the OTA-side channel-connection delay,
which several of the worst "weeks of waiting" complaints are actually about. If Cockpit's pitch is
"instant, friction-free setup," the Coder/PM should scope that claim to "vendor onboarding" and
not imply OTA channel connection will also be instant — that part of the friction is structural
to the OTAs, not to competitor PMS design choices.

**Secondary nuance:** the friction isn't uniformly "too hard," it's "too slow + occasionally needs
a human." Several reviewers rate the *guided* onboarding experience positively once they get a
specialist on a call (Guesty's Simon P.: "pretty straight forward"; John R.: "proficient in a
very short period"). This means the real bar an email-invite/co-host model needs to clear isn't
"replace an impossible process" — it's "replace a multi-day-to-multi-week process that currently
requires booking a call with a human" with something that takes minutes and requires no call.
That's a real, evidenced gap, but it's a claim about **speed and self-serve-ness**, not about the
existing process being unusable — the incumbents' own reviewers rate them 4.5–4.9/5 overall, so
"onboarding friction" is a real, quotable pain point but not the dominant complaint driving churn
in these review sets (pricing and support responsiveness show up at least as often, arguably more).

---

## Part 3 — Complaints organized by product (summary index; full quotes above)

- **Hostaway** (G2 4.7, Capterra 4.8, Trustpilot 4.7 per aggregate ratings — ratings themselves
  are secondary/unverified since I couldn't open G2/Trustpilot directly): pricing surprises
  (intl. charges, "wildly expensive"), phone support that doesn't pick up, VRBO sync bugs
  including a **double booking**, setup taking 2-8 hrs to a week+.
- **Guesty** (G2 4.5 per unverified aggregate): the clearest onboarding-technical-bar complaint
  in the whole set ("needs an IT person"), billing disputes that drag on months, VRBO connection
  stalling 3+ weeks, config loss after platform updates.
- **OwnerRez** (Capterra 4.9/5, 259 reviews — verified rating): pricing is a *strength* in this
  data, not a complaint; the honest trade-off is steep learning curve + limited phone/live-chat
  access (must schedule a call), and VRBO identity-collision on channel connect.
- **Lodgify**: pricing complaints on the "expensive when you use extended features" pattern, a
  wrong-listing cross-mapping bug (real data-accuracy risk), replies "took days" from support,
  weeks-long inactive Vrbo integration post-onboarding.
- **Hospitable**: thinnest verified dataset (Capterra only, Trustpilot blocked) — but what's
  there is sharp: "Things break constantly," core auto-sync/automated-messaging features
  reported not working, "Absolutely nightmare of a customer service." Onboarding-specific
  complaints found were both from 2020, a coverage gap worth another pass if this product
  matters more to the positioning.

---

## Not found / could not verify (explicit, per the honesty bar)

- No Reddit quotes (r/AirBnBHosts, r/vacationrentals, r/PropertyManagement, r/Hosting) —
  environment cannot reach reddit.com via either WebFetch or WebSearch domain-scoping. See
  Access notes above for the exact errors.
- No directly-opened G2, TrustRadius, or Trustpilot quotes — all returned HTTP 403 on every
  URL variant tried (with/without query params, regional subdomains for Trustpilot). Only
  WebSearch's own synthesized summaries of these pages were available, and those are flagged
  inline as unverified rather than presented as primary quotes.
- No Facebook host group content — not attempted, as public indexing of Facebook groups is
  generally unavailable to search/fetch tools and none surfaced in the searches run.
- Hospitable-specific pricing complaints — none surfaced in the one source (Capterra) I could
  open for this product.
- A precise, sourced answer to "how many minutes/hours does an email-invite co-host connection
  take vs. these incumbents" — no source directly measures Cockpit's own (not-yet-built) flow,
  so this brief only establishes the incumbent baseline (hours-to-weeks), not a head-to-head
  number.
