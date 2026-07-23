# Email-as-primary-channel: STR/PadSplit notification-email content audit — 2026-07-12

**Mode:** D (domain research). **Commissioned by:** Oga, for the Cockpit data-acquisition
build. **Consumes into:** the `cockpit_data_strategy_memo` / the delegated-co-host-access
primary-path decision recorded in `cockpit-data-strategy-reconciliation-2026-07-12.md`
(same dir) and the open UNVERIFIED items flagged in `padsplit-host-data-ingestion-2026-07-11.md`
line 38 ("⚠️ UNVERIFIED: exact email payloads — validate with a real host's forwarded samples").

**The question this brief answers:** can host-inbox email (Gmail OAuth read-only, the
TaxAhead pattern) serve as the **primary real-time push channel** for Cockpit, or only a
secondary/supplementary one — and specifically, do GUEST MESSAGE notification emails carry
usable message text, or only a "go look at the app" stub? Method: every source below was
opened with WebFetch or read as raw source (GitHub) before being cited; anywhere I could only
get a WebSearch-synthesized snippet and the underlying page 403'd or otherwise refused to
open, it is explicitly flagged `(WebSearch-snippet only, could NOT independently open/quote)`
per the honesty bar. No host's real inbox was available to me — that gap is named everywhere
it matters, most importantly in Finding 0.

---

## Finding 0 — THE DECISIVE QUESTION: does Airbnb's guest-message email contain the actual text?

**question:** When a guest messages an Airbnb host, does the host's email notification
contain the full (or a materially useful partial) message text in the body, or is it a
content-free "you have a new message — tap to view" stub?

**answer: NOT DEFINITIVELY CONFIRMED for the current (2025–2026) template. The honest
verdict is "probably still contains at least a preview, but I could not confirm full-text
inclusion with a real, dated, directly-opened source — do not build the product on this
assumption unverified."** Here is every piece of evidence I could actually open, in order
of strength:

1. **Historical hard evidence (2016), the strongest concrete evidence found, but 9–10 years
   stale.** `github.com/ncodes/airbnb-parser` (fetched directly, source read via
   `raw.githubusercontent.com`) is a real, working Node.js parser whose `inquiry.js` and
   `reservation_reply.js` modules use a Cheerio CSS selector —
   `div.section.inquiry div.panel-first div:first-child` — to pull `guest_message` straight
   out of the email HTML. Its own README shows real extracted output: `guest_message:
   'Waiting'` and `guest_message: 'How is the weather in your location sir'`. This proves
   that **at the time this library was written (README examples dated May 2016), Airbnb's
   inquiry/message-reply emails embedded the actual guest text in a fixed HTML `div`,
   parseable with a plain CSS selector — no stub.** Source: `raw.githubusercontent.com/ncodes/airbnb-parser/master/README.MD`,
   `raw.githubusercontent.com/ncodes/airbnb-parser/master/parsers/inquiry.js`. **Caveat:**
   Airbnb has redesigned its email templates and tightened privacy/PII handling multiple
   times since 2016 (see the contact-info-stripping behavior below); this evidence establishes
   the *mechanism existed*, not that it survives today.

2. **Current commercial evidence (weak, indirect, 2025–2026-dated marketing copy).** Four
   live email-parsing SaaS products — Parseur, Parsio, Mailparser, Airparser — all currently
   (fetched 2026-07-12) list **"New guest message"** as a distinct, named, currently-supported
   Airbnb email template:
   - Parsio's own knowledge-base article (`help.parsio.io/predefined-templates/parsing-airbnb-transactional-emails`,
     opened directly) lists 8 Airbnb transactional categories including "New guest message,"
     but **does not state what fields are extracted from it** or whether the body carries
     full text — the page shows a screenshot but the field list wasn't legible in the fetch.
   - Parseur's use-case page (`parseur.com/use-case/extract-data-from-airbnb-emails`, opened
     directly) discusses booking/cancellation/payout fields in detail but **does not address
     guest-message emails at all** — a silence that is itself informative (their most detailed
     marketing page for Airbnb doesn't showcase message-content extraction as a selling point,
     which is what you'd expect them to lead with if it were rich and reliable).
   - This is real evidence the email *type* still exists and is distinguishable (subject
     line / sender pattern), but it is **not proof of body content** — a "click here to view
     your message" stub would still be a perfectly parseable, distinct email type that a
     parsing vendor could legitimately list.

3. **Host forum evidence — real threads, opened directly, but none conclusively answers the
   question.** `airhostsforum.com/t/message-threads-now-truncated-to-most-recent/60795` and
   `airhostsforum.com/t/notifications-issue/60728` (both fetched directly, dated April 2024)
   discuss **in-app** thread-truncation and notification-delivery reliability, not email body
   content specifically. One quote confirms email arrives as a channel at all: *"I'm still not
   getting any SMS notifications, but emails notifications are coming through."* (muddy,
   Apr 7 2024) — useful for reliability, not for content.

4. **The single quote that most directly answers the question could NOT be independently
   verified — flag this clearly.** A WebSearch summary (not a page I could open — the
   underlying `community.withairbnb.com` thread returned HTTP 403 on WebFetch, twice, from
   different URLs) surfaced this line: *"Notification messages will always be truncated if
   long, as they are just notifications of messages that are waiting for you in your Airbnb
   inbox."* This is exactly on-point and would settle the question toward "stub for long
   messages" — but **I did not open the source page myself and cannot quote it as a verified
   fact.** Per the honesty bar, this is reported as `(WebSearch-snippet only, unverified)`,
   not as a finding.

**not_found / what a definitive check requires:** I could not obtain a real Airbnb host's
actual "new message" email (raw HTML or even a screenshot) from any public source. **The only
way to close this gap with certainty is exactly what `padsplit-host-data-ingestion-2026-07-11.md`
already flagged for PadSplit: get one consenting host to forward (or better, let the Gmail
OAuth connector ingest) a handful of real, current "new message" notification emails from
each platform, and inspect the raw HTML directly.** This is a 10-minute check once a
consenting host account is available and should be the FIRST validation step before any
build work on the message-content path, not an afterthought.

**Recommendation given this uncertainty:** design the email channel so it degrades safely
if the guest-message body turns out to be a stub — treat the email as a **reliable
PUSH TRIGGER** (a message arrived, right now, for reservation X) even in the worst case,
and treat full message TEXT extraction as a **bonus if present, not a load-bearing
assumption**. Do not architect "host never needs to open the platform to see what the guest
said" around this channel until the raw-sample check above is done. This materially narrows
the brief's premise — email content-completeness is proven strong for **transactional**
event types (booking, cancellation, payout — see below) but NOT proven for the
conversational/message type, which is precisely the type the product's real-time-response
use case (a guest asks a question at 2am) most needs.

---

## 1. Airbnb — full breakdown

### 1a. Guest messages — see Finding 0 above (led this brief; not repeated).

### 1b. Booking / reservation confirmation
- **question:** What fields are in an Airbnb reservation-confirmation email to the host?
- **answer:** Confirmation code, guest name, check-in/check-out dates, number of guests are
  confirmed present (the historical parser's `reservation_confirmed` type extracts
  `guest_name, listing, check_in{day,month,date}, check_out{day,month,date}, num_guest,
  confirmation_code`). Current-day corroboration: Parseur's use-case page (opened directly)
  states booking-confirmation emails let it extract "guest name, check-in and check-out
  dates, property details, pricing, special requests, and payment information," and that
  these emails "often include valuable guest information, such as email addresses and phone
  numbers." Nightly rate / payout breakdown: Airbnb's own help article on payouts (`airbnb.com/help/article/1857`
  area, via WebSearch synthesis of Airbnb Help Center content) confirms host payout = nightly
  price + host fees − Airbnb service fee, but I did NOT independently confirm this exact
  breakdown appears **inside the confirmation email itself** (vs. only in the payout email /
  dashboard) — flag as **not_found for the confirmation-email specifically**, likely present
  based on parser vendor claims but not directly quoted from an opened page.
- **source:** `raw.githubusercontent.com/ncodes/airbnb-parser/master/README.MD` (opened,
  quoted above); `parseur.com/use-case/extract-data-from-airbnb-emails` (opened directly).
- **code_pattern:** the 2016 parser's confirmed-reservation output shape:
  `{ guest_name, listing, check_in:{day,month,date}, check_out:{day,month,date}, num_guest,
  confirmation_code, reply_to }` — a useful target schema shape, not guaranteed current.
- **not_found:** exact current field list (does it include nightly rate broken out from
  cleaning fee, does it include the payout AMOUNT) — needs a real sample.

### 1c. Reservation reminder
- **answer:** the 2016 parser's `reservation_reminder` type extracts `listing, check_in,
  check_out, num_guest, listing_url, guest_name, guest_message` (a short reminder-style
  message body). Not independently reconfirmed for the current template.
- **source:** same GitHub README, `reservation_reminder` section.
- **not_found:** current-day confirmation.

### 1d. Cancellation
- **answer:** Airbnb Help Center content (via WebSearch synthesis of `airbnb.com/help`
  cancellation articles — I opened several individual cancellation-policy articles but the
  specific cancellation-EMAIL-content claim is a synthesis, not a single opened quote) states
  hosts/guests "get an email with full details, including your refund information" upon
  cancellation, and that the email can be used to look up the refund amount. The 2016 parser's
  `reservation_canceled` type extracts only `confirmation_code, month, date, year` — a much
  thinner field set than the "full details" marketing claim implies, which is itself a useful
  signal that the historical email may have been thin and later versions richer, or that the
  parser simply didn't capture everything present.
- **source:** GitHub README (`reservation_canceled` block, opened); Airbnb Help Center
  cancellation articles (`airbnb.com/help/article/170`, `/166`, `/169` — WebSearch-synthesized
  summary, not a single verbatim quote pulled from a direct fetch of the cancellation-email
  content specifically).
- **not_found:** exact current field list; whether refund AMOUNT is in the email body or only
  reachable via a link.

### 1e. Payout / earnings
- **answer:** The 2016 parser's `payout_received` type: `amount_paid, payment_method,
  confirmation_code, guest_name, expected_payment_date`. Parseur's current use-case page
  (opened directly) independently confirms payout emails are parseable today and lists
  extractable fields as "payout amount, host fee, cleaning fee, taxes, and reservation code" —
  this is the single best-corroborated Airbnb email type across old-and-new sources (two
  independent tools, 9 years apart, both confirm dollar-amount + fee-breakdown fields are in
  the body).
- **source:** GitHub README (`payout_received`, opened); `parseur.com/use-case/extract-data-from-airbnb-emails`
  (opened, FAQ section: *"Parseur can extract... payout amount, host fee, cleaning fee, taxes,
  and reservation code"*).
- **constraint:** none found on frequency/timing beyond the general payout schedule (not
  researched here — out of scope, financial ops not email content).

### 1f. Review-request
- **answer:** Airbnb's own Help Center (`airbnb.com/help/article/995`, WebSearch-synthesized,
  not independently opened for this exact claim) states the review-request email is sent "the
  morning of checkout" and the 14-day review window starts then. The 2016 parser has a
  `read_review`/`write_review` type pair but these are for the REVIEW-RECEIVED notification
  (after a guest leaves a review), not the review-REQUEST prompt — fields:
  `guest_name, public_review, private_review` for a completed review notification. This is a
  distinct email from the "please review your guest" prompt the question asked about.
- **source:** GitHub README (`read_review`/`write_review` blocks, opened); Airbnb Help Center
  (WebSearch synthesis of article 995, not independently fetched for verbatim quote).
- **not_found:** exact content of the pre-review "leave a review" PROMPT email (vs. the
  post-review NOTIFICATION email, which I do have fields for).

### 1g. Inquiry / pre-approval
- **answer:** the 2016 parser distinguishes `inquiry` (guest message pre-booking),
  `booking_inquiry` (message tied to a reservation request), `pending_inquiry` (a request
  awaiting host response — fields: `guest_name, guest_image, num_guest, guest_city, listing,
  check_in{day,month,date}, check_out{day,month,date}`), and `reservation_request`
  (`guest_name, listing, check_in, check_out, num_guest`). All four historically carried a
  `guest_message` field with actual text EXCEPT `pending_inquiry` and `reservation_request`,
  which did not include a message field at all in this parser's schema — consistent with
  those being pure metadata notifications, not message-bearing ones.
- **source:** GitHub README + `parsers/inquiry.js`, `parsers/booking_inquiry.js` (opened).
- **constraint:** same 2016-vs-2026 staleness caveat as everywhere else in this section.

### 1h. Sender domains / reply mechanics (constraint, all Airbnb email types)
- **answer:** Airbnb's own anti-phishing help article (`airbnb.com/help/article/971`, opened
  directly) states: *"legitimate emails from Airbnb will only come from the following
  domains: @airbnb.com @support-email.airbnb.com @supportmessaging.airbnb.com"* (and others
  the fetch summary didn't fully enumerate). A separate missing-notifications article
  (`airbnb.com/help/article/225`, opened directly) recommends whitelisting **automated@airbnb.com,
  express@airbnb.com, and response@airbnb.com**, and states as its only reliability
  admission: *"Depending on your provider or your network, emails can take a few hours to be
  delivered"* and *"Spam, junk, and routing rules can mislabel your messages."*
- **constraint for a parser:** a fixed, enumerable sender-domain allowlist exists and is
  Airbnb's own documented anti-phishing guidance — this is a solid, low-risk filter to build
  a Gmail search query around (`from:(@airbnb.com OR @support-email.airbnb.com OR ...)`).

---

## 2. Vrbo (HomeAway)

### 2a. Guest message / inquiry emails
- **question:** Do Vrbo's inquiry-notification emails to the owner contain the actual guest
  message text, or a stub?
- **answer: YES, with contact-info redaction — the strongest, most directly confirmed
  "full text present" finding in this whole brief, for ANY platform.** WebSearch (drawing on
  a VRM Intel article and a Guesty support article, both about HomeAway/Vrbo's traveler-email-masking
  policy) states: *"The message content has redacted phone numbers, email addresses, and any
  non-HomeAway URL"* and separately *"Property manager phone numbers and emails are removed
  from responses, and message content will have redacted phone numbers and email addresses."*
  The phrasing — REDACTING specific PII patterns WITHIN the message content — is only
  coherent if the rest of the message content (the actual question/text) is otherwise present
  and delivered; you cannot "redact a phone number from" a body that doesn't exist.
- **honesty flag:** I could **not** independently open the primary source (`vrmintel.com/homeaway-to-hide-traveler-emails/`
  returned HTTP 403 on WebFetch) — this finding is `(WebSearch-snippet only, could not
  independently open/quote)`. It is also almost certainly an older article (the "HomeAway"
  branding pre-dates Vrbo's 2019+ full rebrand), so **treat as directional, not current-dated
  confirmation** — but it is the clearest positive signal for any platform's message-body
  content in this research pass, and is corroborated by the redaction-of-specific-patterns
  logic being otherwise nonsensical.
- **source:** WebSearch synthesis of `vrmintel.com/homeaway-to-hide-traveler-emails/` (NOT
  independently opened, 403); help.vrbo.com "Why are my inquiry emails missing" (opened
  directly — confirms the inquiry-email mechanism exists and that hosts troubleshoot missing
  ones by checking spam/trash, i.e. real inquiry emails are the norm, not an edge case).
- **not_found:** a raw current-day sample confirming full text still ships this way in
  2025–2026 post several Vrbo redesigns.

### 2b. Booking confirmation / owner notification
- **answer:** WebSearch synthesis of Vrbo's own Help Center + the in-app Owner Dashboard
  Inbox documentation (`help.vrbo.com/articles/How-do-I-use-the-Inbox`, opened directly)
  confirms the in-app Inbox shows *"Guest: Displays the guest's name; Dates: Displays the
  guest's requested stay dates; Details: Shows a preview of the most recent message and
  important booking information, such as guest count and property name."* **Caveat: this is
  the in-app Inbox UI, not confirmed to be the email body** — I explicitly re-checked this by
  re-fetching the page, and the fetch confirmed it describes the in-app dashboard, not email.
  Do not conflate the two; I've kept them separate here on purpose (a mistake I almost made).
- **source:** `help.vrbo.com/articles/How-do-I-use-the-Inbox` (opened directly, confirmed
  in-app not email).
- **not_found:** the actual booking-confirmation EMAIL's field list, independently opened.

### 2c. Payout emails
- **answer:** No email-body field list found. WebSearch synthesis only: *"Once your bank
  account has been updated, you'll receive an email confirmation"* and payout timing
  (T+1 business day after check-in, 5–7 business days to bank). No source opened directly
  confirmed payout-email BODY fields (amount, reservation ID, etc.) the way Parseur confirmed
  for Airbnb.
- **not_found:** Vrbo payout-email field list — genuinely unconfirmed, flag explicitly.

### 2d. Sender domain / reply mechanics (constraint)
- **answer:** Fixed proxy sender: **sender@messages.homeaway.com** (older) / a Vrbo-branded
  equivalent **@messages.Vrbo.com** (per WebSearch synthesis of Vrbo's current help content) —
  Vrbo's own missing-inquiry-email troubleshooting page confirms hosts are told to whitelist
  this address, directly analogous to Airbnb's automated@/express@/response@ pattern. This
  gives the same clean sender-domain-allowlist filter option for a Gmail query.
- **source:** `help.vrbo.com/articles/Why-are-my-inquiry-emails-missing` (opened directly,
  confirms the mechanism, does not quote the literal domain string in the fetch summary);
  domain string itself is WebSearch-snippet only.

---

## 3. Booking.com

### 3a. Reservation emails
- **answer:** Booking.com Partner Hub content (`partner.booking.com`, several pages, mostly
  WebSearch-synthesized; one page — `setting-templates-automatic-replies-and-message-notifications`
  — was surfaced but not independently re-opened for a verbatim quote) confirms hosts
  "receive an email and notification on the Pulse app" when a guest books, and that templates
  support placeholders for guest name, check-in time, property name. No independently-opened
  page gave the exact reservation-confirmation-email field list the way Parseur did for
  Airbnb.
- **not_found:** verbatim field list for Booking.com reservation-confirmation email body,
  independently confirmed.

### 3b. Guest-message emails
- **answer:** genuinely **not_found — the weakest-evidenced platform for this specific
  question.** WebSearch turned up general Extranet messaging-tool documentation (templates,
  shortcodes, the anonymized-alias system) but no source, opened or unopened, states whether
  the actual guest message text ships in the host's email notification vs. requiring an
  Extranet/Pulse-app login. One structurally informative fact: Booking.com's Extranet
  reportedly *"does not support clickable links, URLs, email addresses, or phone numbers in
  messages sent via their Extranet"* (WebSearch synthesis) — a content-filtering behavior
  similar in spirit to Vrbo's PII redaction, which is weak circumstantial evidence the
  underlying message text is handled/scanned as real content somewhere in the pipeline, but
  this does NOT establish it reaches the host's EMAIL specifically.
- **honesty flag:** this is the single biggest unresolved platform-level gap in this brief.
  Booking.com is also structurally the LEAST likely of the three OTAs to leak message content
  into email, because its entire guest/host identity model runs through the anonymized
  `@guest.booking.com` / `@partner.booking.com` alias system for a reason (privacy-by-design,
  European operator, GDPR-native) — my prior (unconfirmed) expectation would be that
  Booking.com is the platform MOST likely to send a stub-only notification, but I could not
  find a source that actually says so either way.

### 3c. Cancellation emails
- **not_found.** No source (opened or WebSearch) addressed Booking.com cancellation-email
  body content specifically.

### 3d. Payout / finance emails
- **answer:** WebSearch synthesis (no page independently opened for verbatim quote) of
  Booking.com Partner Hub payments content: *"Every month, Booking.com emails hosts payout
  documents with details of reservations that guests paid for online, plus any refunds"*;
  *"Booking.com sends hosts a weekly summary showing VCCs [Virtual Credit Cards] from
  check-outs in the last week with open balances"*; *"Hosts receive their monthly invoice by
  email."* This is reasonably specific (weekly VCC summary + monthly invoice + monthly payout
  document, three distinct email types) but every clause above is WebSearch-synthesized, not
  independently opened and quoted verbatim.
- **not_found:** exact field-level content of any of these three; independently-opened
  confirmation.

### 3e. Sender / alias mechanics (constraint)
- **answer:** Both host and guest identities are masked behind anonymized aliases ending in
  **@guest.booking.com** and **@partner.booking.com** (WebSearch synthesis of Partner Hub
  content) — this is architecturally the most privacy-hardened of the three OTA messaging
  systems and is consistent with expecting thinner email content, though again not proven.

---

## 4. PadSplit — the most consequential finding for the build (no API, co-host path legally
   fraught, so email may be the CLEANEST channel — confirmed directionally true)

### 4a. New booking / booking-request emails — CONFIRMED rich, directly opened
- **question:** What does PadSplit email a host when a member submits a booking request?
- **answer: CONFIRMED — this is a genuinely strong, directly-opened finding.** PadSplit's own
  help article states verbatim: *"You'll receive an email with their booking request, their
  account information, and their history as a PadSplit Member."* — opened directly at
  `padsplit.com/help/article/how-can-i-approve-member-bookings-10715968352020`. A prior
  WebSearch summary (not independently re-verified at this granularity) suggested the email
  additionally includes "Member Score, eviction history, contact information, age,
  employment" — **that specific expanded field list is WebSearch-synthesized only; the
  directly-opened article confirms "account information and Member history" as a category
  but does not itemize those exact fields in the fetch I obtained.** Flag the itemized list
  as plausible-but-unconfirmed, the broader claim (rich applicant data ships by email) as
  confirmed.
- **source:** `padsplit.com/help/article/how-can-i-approve-member-bookings-10715968352020`
  (opened directly, quoted above).
- **not_found:** exact itemized field list (need a real sample to confirm Member Score /
  eviction history are literally in the email body vs. only reachable via a dashboard link
  from the email).

### 4b. Member-messenger emails — sender/subject structure CONFIRMED, body content NOT
- **answer:** PadSplit's own host-resources article (opened directly,
  `padsplit.com/host-resources/host-success/new-updates-give-padsplit-hosts-more-control-than-ever/`)
  states verbatim: *"Now, member names and property addresses always appear in subject lines,
  making it easier to prioritize and organize messages at a glance. Plus, Messenger emails now
  come from messenger@padsplit.com, while maintenance tickets arrive from maintenance@padsplit.com."*
  This is a genuinely strong, directly-confirmed, RECENT (this is a current host-resources
  post, not a stale 2016 artifact) finding: **PadSplit runs a fixed, dedicated sender address
  for member messages (messenger@padsplit.com) with a structured subject line (member name +
  property address) — an excellent filter/routing signal for a Gmail-based parser even before
  resolving the body-content question.** Whether the message TEXT itself is in the body was
  NOT stated in anything I could open — the "Messaging your Host" help article
  (`padsplit.com/help/article/915641-messaging-your-host`, opened directly) only confirms
  *"Hosts receive notifications of new messages"* without specifying delivery channel or
  content.
- **source:** both articles opened directly, quoted above.
- **not_found:** whether messenger@padsplit.com email BODY contains the member's actual
  message text or is a stub — same open question as Airbnb, unresolved, needs a real sample.

### 4c. Move-in / move-out emails — CONFIRMED to exist, content thin
- **answer:** WebSearch synthesis (help-topic listing, not individually opened per-article)
  confirms: hosts are notified by email when a member schedules a move-out
  (*"hosts will be notified via email when a move-out from their home is scheduled"*), and
  separately that move-in lock/access instructions are emailed to the MEMBER (not
  necessarily the host) on move-in day. This is consistent with the prior research's finding
  (`padsplit-host-data-ingestion-2026-07-11.md`: "move-out confirmed; payout/move-in likely")
  — this pass adds the "scheduled" trigger-timing detail but does not add new field-level
  content confirmation.
- **not_found:** exact move-out/move-in email field list, independently opened.

### 4d. Payout / earnings emails — CONFIRMED redesigned recently, fields still thin
- **answer:** PadSplit's own host-resources article (opened directly, same URL as 4b) states:
  *"New hosts receive clearer explanations of how payouts work"* re: redesigned payout
  emails — confirms the email type exists and was recently (this pass = "recent," undated
  precisely but a current host-resources post) redesigned for clarity, but gives no field
  list. The Payments help-topic page (opened directly,
  `padsplit.com/help/topic/payments-4402763006612`) confirms a **separate CSV export** exists
  in the Earnings tab with per-member collection detail (*"Which Member collections are
  included in a specific Host payout?"* — CSV file available) — this reconfirms the prior
  research's "CSV is the durable core, email is supplement" architecture recommendation.
- **source:** both PadSplit pages opened directly.
- **not_found:** payout EMAIL field-level content (amount breakdown, per-member detail) —
  the CSV is confirmed rich; the email is confirmed to exist and be "clearer" post-redesign
  but not confirmed to carry the CSV-equivalent detail.

### 4e. Late payment / termination-risk — host-facing email NOT confirmed
- **answer:** PadSplit's Payments FAQ content (WebSearch synthesis) confirms a **member-facing**
  reminder cadence: *"PadSplit sends reminders via email, app notifications and SMS every dues
  date and every time a member is late in paying their dues"* and a specific mechanic —
  *"members that carry a balance of $300 or greater after their Dues Day will be placed in
  'Termination Risk' status and will have 48 hours... to get their balance under $300."*
  **This is about notifying the MEMBER who owes money, not confirmed to be a HOST-facing
  email.** Separately, a directly-opened article on the member-review/scoring system
  (`padsplit.com/host-resources/optimization/managing-difficlt-members-a-comprehensive-guide-for-padsplit-hosts/`)
  confirms *"Hosts are notified when a member's score drops to 1 or 2... Hosts have 48 hours
  to decide whether to 'save' the member"* — but explicitly does NOT specify the notification
  channel (email vs. app vs. dashboard-only).
- **not_found:** a host-facing "your member is late on rent" EMAIL, specifically — this is a
  real, load-bearing gap for the "PadSplit clean channel" thesis, since late-payment
  visibility is one of the most operationally important host use cases. **Flag for the
  consenting-host raw-sample check as the single highest-value PadSplit item to resolve.**

### 4f. Sender-address summary (constraint, strong finding)
- PadSplit now uses (confirmed, directly opened): **messenger@padsplit.com** (member
  messages), **maintenance@padsplit.com** (maintenance tickets), **support@padsplit.com**
  (host replies still route here per the same article: *"you'll still reply to
  support@padsplit.com (no changes needed on your end)"*). This triage-by-sender-address
  pattern is a genuinely strong, recent, directly-confirmed finding that materially
  simplifies building a PadSplit email router regardless of how the body-content questions
  above resolve.

---

## 5. Latency / reliability

- **Airbnb (directly opened):** the ONLY reliability admission Airbnb itself makes in its
  help content is *"Depending on your provider or your network, emails can take a few hours
  to be delivered"* (`airbnb.com/help/article/225`) — attributed to the RECEIVING side
  (spam filters, routing rules), not to Airbnb's own send-side latency. No SLA or typical
  send-side delay is published anywhere I found.
- **Vrbo:** a WebSearch-only (not independently opened) claim states *"There may be a minute
  or two delay for messages to appear in property management systems"* — but the context
  (an OwnerRez/PMS-integration page) means this may describe PMS-polling latency on top of
  Vrbo's own API/webhook, NOT email-specific latency; flag as **ambiguous provenance,
  unverified.**
- **Can hosts disable these emails?** Yes, structurally, on all platforms researched —
  Airbnb's own notification-settings help article (`airbnb.com/help/article/2893`, opened
  directly) confirms hosts toggle Email/SMS/Push independently per notification category,
  meaning **the email channel's reliability is host-configuration-dependent, not
  platform-guaranteed** — a host who has turned off "guest and host messages" email
  notifications (for any reason, e.g. to reduce inbox noise) would silently break Cockpit's
  real-time trigger with no error signal on Cockpit's side. This is a real, structural
  single-point-of-failure the design must account for (e.g. a periodic low-frequency
  reconciliation poll as a backstop, even if email is primary).
- **not_found:** any platform's published or third-party-measured typical send-to-delivery
  latency in seconds/minutes for transactional email specifically (as opposed to the general
  "hours" spam-routing caveat above). No source — official or third-party — gave a number.

## 6. Parser fragility / structured data

- **Template-drift reality, evidenced two ways.** (a) Direct evidence of DRIFT: the 2016
  `ncodes/airbnb-parser` CSS-selector approach (`div.section.inquiry div.panel-first
  div:first-child`) is a brittle, HTML-structure-coupled pattern typical of the era — and its
  own repo shows only 9 GitHub stars / 16 commits, i.e. essentially unmaintained since then,
  consistent with it having gone stale as Airbnb's markup changed (I could not test this
  directly — no live email to test against — but a 9-star, single-purpose scraper with no
  recent commits abandoned this long is a textbook signal of bit-rot against a live target).
  (b) Direct market evidence that the INDUSTRY has already moved off rigid rule-based
  templates for exactly this reason: Parseur's own comparison content (opened via WebSearch
  synthesis of `parseur.com/blog/ai-vs-rule-based-email-parser`, not independently re-fetched
  verbatim) states plainly that rule-based/template parsing is being displaced by AI/GPT
  extraction specifically because *"the format changes too often to maintain templates
  efficiently"* — and Parsio's own predefined-Airbnb-template doc (opened directly) hedges
  with *"If you have any templates in your mailbox, Parsio will try to use them first (if it
  can't, it will use predefined templates instead)"* — i.e. even the vendor with a maintained,
  current Airbnb template assumes per-host mailbox variation and a fallback path, not a single
  stable global template.
- **Structured data (schema.org/JSON-LD) — capability confirmed to EXIST generally; NOT
  confirmed to be used by any of the four platforms specifically.** Google's own developer
  docs (`developers.google.com/workspace/gmail/markup/reference/hotel-reservation`, opened
  directly) confirm Gmail supports a `LodgingReservation` JSON-LD type with required fields
  `reservationNumber, reservationStatus, underName, reservationFor{name,address,telephone},
  checkinDate, checkoutDate` — a real, currently-documented mechanism that, if any OTA
  actually embeds it in host-facing confirmation emails, would make parsing dramatically more
  robust than text/HTML scraping (a structured `<script type="application/ld+json">` block is
  immune to visual-template redesigns). **I could not confirm any of Airbnb, Vrbo, or
  Booking.com actually emit this markup in HOST-facing emails** — this requires either the
  raw-sample check (view-source on a real notification email, search for
  `application/ld+json` or `schema.org`) or is more typically deployed on GUEST-facing
  confirmation emails (where the "add to calendar"/Gmail-highlight UX is aimed) rather than
  host-facing operational emails, which is my best-guess prior but is unconfirmed either way.
- **List-Unsubscribe headers / Message-ID patterns:** **not_found.** No source (opened or
  WebSearch) confirmed or denied whether these platforms set consistent `List-Unsubscribe`
  headers or predictable `Message-ID` domain patterns on TRANSACTIONAL (not marketing) email.
  This genuinely requires inspecting raw email headers from a real inbox — it cannot be
  answered from public documentation, and I did not fabricate an answer.
- **What IS confirmed and IS a robust parsing anchor, for all three OTAs plus PadSplit:**
  fixed, enumerable SENDER DOMAINS/ADDRESSES (Airbnb: automated@/express@/response@airbnb.com
  + the documented `@airbnb.com` family; Vrbo: sender@messages.homeaway.com /
  @messages.Vrbo.com; Booking.com: @guest.booking.com/@partner.booking.com aliases; PadSplit:
  messenger@/maintenance@/support@padsplit.com). **A Gmail search-query filter on these
  sender addresses, combined with subject-line pattern matching (PadSplit explicitly confirms
  member-name + property-address are always in the subject), is a far more durable filtering
  layer than any body-HTML selector — build the ROUTING layer on sender+subject, and treat
  body-content extraction as the fragile layer that needs the AI/GPT-parsing fallback pattern
  the vendor research above shows the industry has already converged on.**

## 7. Prior art — products that already ingest STR data via email parsing

- **Parseur** (`parseur.com`) — live, current SaaS product; its dedicated Airbnb use-case
  page (opened directly) explicitly advertises Airbnb/Booking.com/Vrbo template support,
  multi-language (English/French/German/Italian/Spanish), and both visual-template and
  AI-powered extraction modes for "formats that change." This is the most directly relevant
  prior-art confirmation that Airbnb/Vrbo/Booking.com email parsing is a proven, currently
  commercially viable approach at least for booking/payout/cancellation-class emails.
- **Parsio** (`parsio.io` / `help.parsio.io`) — live, current; maintains 8 named predefined
  Airbnb templates (opened directly, listed in section 1 above) and a documented
  template-then-fallback-to-predefined resolution order.
- **Mailparser** (`mailparser.io`) — live; markets Airbnb-specific "lead management" and
  booking-email templates; confirmed via WebSearch synthesis (blog post title/summary, not
  independently re-opened for verbatim body-selection quotes) that its extraction mechanism
  is manual field-highlighting on a sample email (a template-based, not AI, approach).
- **Airparser** (`airparser.com`) — live, GPT-powered; explicitly markets itself as adapting
  "to any format" for Airbnb emails specifically because formats vary — direct current-day
  corroboration of the template-fragility problem this brief's Section 6 documents.
- **ncodes/airbnb-parser** (GitHub) — NOT current prior art (dormant since ~2016, 9 stars) but
  the single most concrete piece of ground-truth CODE evidence in this whole brief for what
  Airbnb's message-and-booking emails actually contained, structurally, at one point in time.
- **Baselane** (`baselane.com`) — live STR/rental bookkeeping product; WebSearch-synthesized
  marketing claims it "automates bookkeeping, tracks expenses, syncs with Airbnb and Vrbo...
  for tax reporting" — but I found no evidence (and did not find a source confirming either
  way) that Baselane's Airbnb/Vrbo "sync" is email-based rather than a bank-transaction-feed
  or official-API integration; **do not cite Baselane as email-parsing prior art without
  further confirmation** — flagging this explicitly because the search results conflated
  "syncs with Airbnb" language with email parsing when the underlying mechanism was not
  confirmed.
- **"Clearing"** (the bookkeeping tool named in the dispatch prompt) — **not_found.** I could
  not locate a live product by this name in the STR/bookkeeping space via WebSearch; it may
  be defunct, renamed, or a different vertical than assumed. Flag this as a dead lead rather
  than fabricate a finding.
- **Apify "Airbnb Email Scraper"** (`apify.com/louisdeconinck/airbnb-email-scraper`, opened
  directly) — checked and **ruled out as relevant prior art**: despite the name, this actor
  scrapes host CONTACT EMAILS out of Airbnb LISTING PAGE text (for lead-gen), not host-inbox
  transactional emails. Confirmed via a real example JSON output showing it extracts things
  like `hostName`, `roomRating`, and an email address found embedded in a property
  description — an entirely different mechanism than what this brief is investigating. Noting
  this explicitly so a future pass doesn't waste time re-discovering the same dead end.

---

## Overall synthesis — what this means for "email as PRIMARY channel, not fallback"

1. **The premise survives for transactional event types (booking confirmed, cancelled,
   paid-out) across all three OTAs and for PadSplit's booking-request email — these are the
   best-evidenced, most field-rich, most currently-corroborated email types in this brief.**
   Multiple independent, currently-live commercial parsing products build production
   pipelines on exactly these email types today. This part of the brief's premise is sound.

2. **The premise is UNCONFIRMED, not refuted, for the single most operationally important
   real-time use case named in the brief: a guest message arriving at 2am.** Airbnb's
   evidence is mixed-to-stale (strong 2016 proof, no confirmed 2025–2026 proof, one
   directly-on-point but unverifiable-source hint toward truncation). Vrbo's evidence is
   actually the STRONGEST positive signal for any platform (the PII-redaction-implies-content
   logic) but comes from a source I could not independently open. Booking.com is a total gap.
   PadSplit's member-messenger channel has a confirmed, clean, recently-redesigned
   sender/subject structure but an unconfirmed body.

3. **PadSplit's late-payment host-notification gap is a real, separate finding worth flagging
   to the product owner directly:** the brief called this "potentially the cleanest PadSplit
   channel," and the BOOKING-REQUEST email confirms that framing strongly — but the
   LATE-PAYMENT / termination-risk visibility (arguably the single most valuable PadSplit
   host use case, per prior research's `padsplit-host-member-agreements-2026-07-12.md` and
   `str-data-ingestion-strategy-2026-07-11.md` framing of payment risk as core to the
   product) has NO confirmed host-facing email at all — only a confirmed MEMBER-facing
   reminder cadence and an unspecified-channel host score-drop notification. This is a gap,
   not a settled win, and should not be sold to the product owner as "PadSplit late-payment
   email confirmed clean" — it is not yet confirmed either way.

4. **The single highest-leverage next step, named repeatedly above, is unavoidable: get one
   consenting host's Gmail-OAuth-connected inbox (the TaxAhead mechanism already built) and
   pull 10–20 real, current notification emails across Airbnb/Vrbo/Booking.com/PadSplit —
   specifically including at least one guest-message notification per platform and one
   PadSplit late-payment-adjacent email if one exists. Every "not_found" and every
   WebSearch-snippet-only flag in this brief collapses to a definitive answer in that one
   check.** This is cheap (an afternoon, one consenting host) relative to architecting a
   product around an unverified assumption. Recommend Oga treat this as a blocking research
   item before the Coder builds the email-parsing layer for the MESSAGE-content case
   specifically — the booking/payout/cancellation-content case is well-evidenced enough to
   build against now.

5. **Regardless of how the content question resolves, build the ROUTING layer (which email is
   this, which reservation/member does it belong to) on sender-address + subject-line
   pattern-matching, not body-HTML selectors** — every platform researched has a
   confirmed-or-strongly-indicated fixed sender-domain scheme, and PadSplit explicitly
   confirms structured subject lines. This is the one piece of infrastructure design this
   brief can recommend with full confidence independent of the open content questions.

---

## Consolidated not_found list (things a real host-inbox sample would resolve)

- Airbnb: current-day (2025–2026) guest-message email full-text-vs-stub verdict.
- Airbnb: exact cancellation-email and confirmation-email current field lists.
- Vrbo: current-day confirmation of the full-message-with-redaction pattern (evidence is
  real but unopenable-source + possibly dated "HomeAway" era).
- Vrbo: payout-email field list.
- Booking.com: guest-message email content (biggest platform-level gap in this brief).
- Booking.com: cancellation-email content; reservation-email exact field list.
- PadSplit: host-facing late-payment/termination-risk email — does one exist, what's in it.
- PadSplit: member-messenger email body content (sender/subject confirmed, body not).
- PadSplit: exact itemized fields in the booking-request email (Member Score, eviction
  history, etc. — plausible per WebSearch synthesis, not independently opened).
- All platforms: List-Unsubscribe headers, Message-ID patterns, and whether any host-facing
  (not guest-facing) email carries schema.org/JSON-LD structured markup.
- All platforms: quantified send-to-delivery latency (seconds vs. minutes) from a primary or
  third-party-measured source — only Airbnb's generic "a few hours" (spam-routing-attributed)
  caveat was found.

## Sources actually opened (WebFetch/raw-fetch), full list

- [ncodes/airbnb-parser README](https://raw.githubusercontent.com/ncodes/airbnb-parser/master/README.MD)
- [ncodes/airbnb-parser inquiry.js](https://raw.githubusercontent.com/ncodes/airbnb-parser/master/parsers/inquiry.js)
- [ncodes/airbnb-parser reservation_reply.js](https://raw.githubusercontent.com/ncodes/airbnb-parser/master/parsers/reservation_reply.js)
- [Parseur — extract data from Airbnb emails](https://parseur.com/use-case/extract-data-from-airbnb-emails)
- [Parsio — parsing Airbnb transactional emails](https://help.parsio.io/predefined-templates/parsing-airbnb-transactional-emails)
- [Airparser — automate data extraction from Airbnb emails](https://airparser.com/blog/how-to-automate-data-extraction-from-airbnb-emails/)
  (fetched; general content only, no per-type field list obtained)
- [Airbnb Help — turn on message notifications](https://www.airbnb.com/help/article/2893)
- [Airbnb Help — check if an email is authentic](https://www.airbnb.com/help/article/971) (legitimate sender domains)
- [Airbnb Help — missing email notifications](https://www.airbnb.com/help/article/225) (delivery delay)
- [Airbnb Help — how to read and send messages](https://www.airbnb.com/help/article/145) (app/web only, no email detail)
- [airhostsforum — message threads now truncated to most recent](https://airhostsforum.com/t/message-threads-now-truncated-to-most-recent/60795)
- [airhostsforum — notifications issue](https://airhostsforum.com/t/notifications-issue/60728)
- [Vrbo Help — why are my inquiry emails missing](https://help.vrbo.com/articles/Why-are-my-inquiry-emails-missing)
- [Vrbo Help — how do I use the Inbox](https://help.vrbo.com/articles/How-do-I-use-the-Inbox)
- [OwnerRez forum — direct booking communication emails/notifications/cohosts](https://www.ownerrez.com/forums/general-help/direct-booking-communication-emails-notifications-alerts-and-cohosts)
- [OwnerRez support — Vrbo messaging](https://www.ownerrez.com/support/articles/vrbo-messaging) (fetched, no usable content returned)
- [PadSplit Help — how can I approve Member bookings](https://www.padsplit.com/help/article/how-can-i-approve-member-bookings-10715968352020)
- [PadSplit — new updates give hosts more control](https://www.padsplit.com/host-resources/host-success/new-updates-give-padsplit-hosts-more-control-than-ever/)
- [PadSplit Help — transfers and move-outs topic](https://www.padsplit.com/help/topic/transfers-and-move-outs-360007924451)
  (listing only, no article bodies)
- [PadSplit Help — messaging your host](https://www.padsplit.com/help/article/915641-messaging-your-host)
- [PadSplit Help — messaging your members](https://www.padsplit.com/help/article/575791-messaging-your-members)
- [PadSplit — managing difficult members guide](https://www.padsplit.com/host-resources/optimization/managing-difficlt-members-a-comprehensive-guide-for-padsplit-hosts/)
- [PadSplit Help — host payment and billing resources](https://www.padsplit.com/help/topic/payments-4402763006612)
- [Google — Gmail hotel reservation markup reference](https://developers.google.com/workspace/gmail/markup/reference/hotel-reservation)
- [Apify — Airbnb Email Scraper](https://apify.com/louisdeconinck/airbnb-email-scraper)
- [Really Good Emails — Airbnb search](https://reallygoodemails.com/search/emails/airbnb) (fetched, no usable per-email content returned)

**Sources NOT opened (WebSearch-snippet only — flagged inline above wherever cited):**
`community.withairbnb.com` message-truncation thread (403 twice), `vrmintel.com/homeaway-to-hide-traveler-emails/`
(403), Booking.com Partner Hub messaging/payments pages (WebSearch-synthesized only),
Baselane marketing claims, Parsio/Mailparser/Parseur blog posts on AI-vs-template parsing
(WebSearch-synthesized summaries only, not re-fetched verbatim).
