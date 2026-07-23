# Gate verification pass — Airbnb guest-message content + PadSplit host late-payment email — 2026-07-12

**Mode:** D (domain research), verification dispatch. **Commissioned by:** Oga, to close two
specific OPEN gates left by the prior pass at
`~/Claude/loop/research/email-ingestion-channel-2026-07-12.md` (read first, per instructions —
this brief does not repeat that pass's sources/dead-ends except where a new angle changed the
picture). No real host inbox was available to me either; every finding below is public-source
only, and every source cited was actually opened (via WebFetch, direct `curl`, or the
GitHub REST API via `gh`) before being quoted — anything I could not open is explicitly flagged
`(WebSearch-snippet only, unverified)`.

**New technique this pass, worth flagging for future Researcher runs:** GitHub's own web code-search
UI requires a login and returns nothing to WebFetch. `gh search code "<query>" --limit N` (the
already-authenticated `gh` CLI) works around this and was the single highest-yield tool used in
this pass — it surfaced two *directly relevant, real, current (Nov 2025 and Feb–Mar 2026)*
open-source Airbnb-email-processing tools that plain WebSearch never turned up.

---

## GATE 1 — Airbnb guest-message notification emails: full text / usable preview, or content-free stub?

### Angles tried from the dispatch, and what happened on each

1. **milled.com** — `milled.com/airbnb` and `milled.com/search?q=airbnb` both returned **HTTP 403**
   on WebFetch. Structural point worth recording so a future pass doesn't retry this: Milled and
   "really good emails"-style galleries harvest **marketing/newsletter** email by subscribing to
   brand mailing lists — they cannot capture a **personalized, per-recipient transactional**
   notification like "Guest X messaged you" because no such email is ever broadcast to a public
   subscriber list. This is a structural dead end for this specific question, not just a blocked
   fetch — flag it as such so it isn't retried.
2. **GitHub code search for recent (2023–2026) Airbnb email parsers/fixtures** — the productive
   angle this pass (see below). `github.com/search?...&type=code` itself needs a GitHub login and
   fails on WebFetch; `gh search code` (authenticated CLI) does not, and surfaced real hits.
3. **Commercial parser vendor documentation** — not re-attempted beyond the prior pass's coverage
   (Parseur/Parsio/Mailparser/Airparser were already opened directly last pass and found to not
   itemize message-email fields); no new vendor page was found this pass.
4. **Airbnb's own current help-center pages** — `airbnb.com/help/article/2899` (Managing guest
   messages) and `/2893` (message notification toggle) were in the prior pass's list already;
   re-searched this pass, no new Airbnb-authored page surfaced that states message-notification
   content explicitly either way.
5. **Recent host-forum/Reddit threads** — targeted 2024–2026-specific WebSearch queries (see
   below) surfaced *more*, and *more specific*, `community.withairbnb.com` thread titles than the
   prior pass found, but the thread pages themselves are still **HTTP 403 on both WebFetch and raw
   `curl`** (re-confirmed this pass, twice, on a different specific thread URL than the prior
   pass tried) — this is a Cloudflare/bot-wall, not a one-off failure. `airhostsforum.com` threads
   remained open and readable but none added new content-specific information this pass.

### New, directly-opened, dated evidence found this pass

**1. `bdyson556/AirbnbEmailParser` (GitHub, pushed 2024-02-18) — real, dated, current-era email
fixtures that embed the guest's actual free-text message in full.**
Opened directly via `gh api repos/bdyson556/AirbnbEmailParser/contents/tests/sample_A.py` (and
B/C/D). These are `body_plain` fixtures the repo owner used to test a parser — the file names and
`date` fields (`"Tue, 21 Nov 2023 21:13:08 +0000 (UTC)"`, `"Fri, 16 Feb 2024 13:30:36 +0000 (UTC)"`,
etc.) and the specific tracking-URL/`euid=` query-string format are the signature of an actually
*received* email, not an invented mock. Sample A's body, quoted verbatim from the fetched file:

> "Hi Lindsey, Thanks for the opportunity to stay at your place. My two kids (ages 8 & 10) and I
> are coming to Minneapolis (from Omaha) in June to watch the Olympic trials at the Target
> Center. I believe there is a bus stop close to your place. If you have any recommendations,
> please let us know. Also, my son is allergic to animals so if you have animals in your place,
> we may have to find somewhere else to stay. Thanks so much & will be in touch. Thanks, Sheila"

Sample D similarly embeds a 4-sentence guest note in full. **This is a "Reservation confirmed"
email (the guest's initial at-booking note), not the ongoing mid-stay "new message" thread
notification the gate asks about — that distinction matters and I am not collapsing it.** But it
is directly-opened, dated, real-vintage (late 2023/early 2024) proof that Airbnb's *current-era*
transactional email templates do carry real, unredacted, multi-sentence guest-authored free text
in the body when one exists — the opposite of "Airbnb strips all guest text out of host emails
now." That was a live open question after the prior pass (which only had 2016 evidence for this).
Source: `raw` fetch of
`repos/bdyson556/AirbnbEmailParser/contents/tests/sample_A.py` and `sample_D.py` via `gh api`
(GitHub REST content API, base64-decoded).

**2. `ddiparshan/AirbnbAgent` (GitHub, created 2025-11-19, pushed 2025-11-20) — a real, currently
built and (per its own README) actively-run bot whose entire mechanism depends on the guest-message
email carrying extractable content, not a stub.**
Opened directly (`gh api .../contents/airbnb_bot.py`, `gh api .../contents/README.md`). The
README states plainly: *"Since Airbnb does not have a public API for messages, this tool acts as a
'wrapper' by listening to email notifications. It processes the incoming message with a local AI
(Ollama running Llama 3.1) and instantly sends a drafted reply to a Discord Channel for review."*
The `.env` example in the README defaults `WIFI_SSID=sherpastay` — i.e. this reads as a real
individual's actual short-term-rental property, not a demo. The code:
- Filters `criteria = AND(seen=False, from_="airbnb.com")` over IMAP IDLE (real-time).
- `extract_guest_name()` parses two live subject-line patterns: `"Message from {name}"` and
  `"Respond to {name}'s"` — this is real, current (Nov 2025) confirmation of Airbnb's actual
  message-notification subject-line formats, which neither this brief nor the prior pass had
  before.
- `parse_email_body()` walks the HTML's `<p>/<span>/<div>` elements and **explicitly filters out
  known boilerplate strings** — `"forwarded message"`, `"from:"/"subject:"/"to:"/"date:"` headers,
  `"respond to"`, `"accept/decline"`, `"identity verified"`, `"get the app"` — keeping up to the
  first 3 non-boilerplate text blocks; if none survive the filter, it **falls back to
  `soup.get_text(strip=True)[200:700] + "..."`** — a 500-character slice starting 200 characters
  in.
This design only makes sense against an email that *has* real guest-authored text mixed in among
template chrome — a true one-line "you have a new message, tap to view" stub would not need
boilerplate-filtering logic, and would not have 700+ characters of body text to slice into for the
fallback path. The bot's whole value proposition (feed the guest's real question to a local LLM,
get back a usable draft reply) is inoperable against a content-free stub. This is **inferential
evidence from real, current, directly-opened code design**, not a raw email I viewed myself — that
distinction is preserved in the verdict below.

**3. `mustafat52/channel-manager` (GitHub, created 2026-02-28, pushed 2026-03-28 — the most
recent source in this entire brief) — confirms the literal detection phrases found in real,
production Airbnb message-notification emails, though this repo deliberately does not extract
their content.**
Opened directly (`gh api .../contents/app/parsers/router.py`, `.../contents/app/parsers/airbnb.py`).
The `airbnb.py` module's own docstrings distinguish two formats it was built and tested against:
*"Format A (forwarded/plain text — original test samples)"* vs. *"Format B (direct from Airbnb —
real production emails)"* — i.e. the developer explicitly worked from real captured Airbnb email
text, not only synthetic samples, and the parsing logic (regex fallbacks for both a
`"Confirmation code\n<CODE>"` layout and a `"CONFIRMATION CODE\n<CODE>"` layout, name-extraction
that has to strip an inline tracking URL glued to the guest's name on the same line) reads as
genuinely reverse-engineered from messy real HTML-to-text output, matching the same tracking-URL
artifacts seen independently in the bdyson556 fixtures above (cross-corroboration between two
unrelated repos). Crucially, `router.py`'s `NON_BOOKING_PHRASES["airbnb"]` list —
`["sent you a message", "you have a new message", "left you a review", "review reminder", "your
payout", "upcoming trip reminder", "checkout reminder"]` — is used to **detect and silently skip**
message-type emails (the repo only implements confirmation/cancellation parsers). This confirms
`"sent you a message"` and `"you have a new message"` are real, current, literal substrings this
developer found in real Airbnb message-notification emails (used as a reliable detection
signature) — but because the router deliberately never parses these emails' bodies, **this source
does NOT itself confirm or deny full-text-vs-stub** — it only confirms the email type's detection
signature, and is included here for completeness/honesty, not as content evidence.

**4. Airbnb Community forum — richer, more specific WebSearch synthesis this pass, but still
UNVERIFIABLE by direct fetch (403, twice, on a different URL than the prior pass tried).**
Targeted 2024-2026 WebSearch queries surfaced three independent thread *titles* that converge on
the same theme: *"long Airbnb message gets cut off after only a few words"*
(`community.withairbnb.com/t5/Help/long-Airbnb-message-gets-cut-off-after-only-a-few-words/m-p/682581`),
*"AirBnB guest commications getting truncated"*, and *"Truncated messages to guests"*. I attempted
to open the first directly via both WebFetch and raw `curl` with a browser user-agent — **both
returned HTTP 403**; this is a bot-wall on the whole `community.withairbnb.com` domain, not a
one-off block (now confirmed on two different thread URLs across two research passes). The
WebSearch tool's own synthesis of these pages states: *"Notification messages will always be
truncated if long, as they are just notifications of messages that are waiting for you in your
Airbnb inbox"* (this is the same line the prior pass flagged as unverified) and, new this pass:
*"When you get a message from a guest, Airbnb sends you an email notification of it. It may
contain the entire message the guest sent, or it may be a truncated version if the message is
long... What is being cut off is the short summary that is sent by SMS... [for email] it will end
with '...' and then you have to go to the app."* **I am flagging this explicitly and clearly as
`(WebSearch-snippet only, could NOT independently open/quote)`, exactly as the honesty bar
requires** — I did not verify this by reading the source page myself. I report it because it is
*directionally consistent* with, and adds a length-conditioned mechanism to, everything else found
this pass (a length-capped preview, not a universal stub) — but it is not being counted as
confirmed evidence on its own.

### GATE 1 — Synthesis

Every piece of *directly-opened* evidence found this pass — a real dated fixture with a guest's
full message embedded in a same-era transactional email, and a real currently-built/run bot whose
entire mechanism requires extractable guest text in the notification email — points the same
direction: **away from** a universal content-free "click here to view" stub, and **toward** a
usable text preview that is present for short-to-medium messages and (per the not-independently-verified
but multiply-converging forum-thread pattern) length-capped/truncated with an ellipsis for long
ones. No source found this pass or last pass states or implies the opposite (a message-notification
email with literally zero guest text). Nothing found rules the truncation-when-long shape out
either — it is the most specific, best-supported characterization available from public evidence.

**VERDICT: RESOLVED-YES — bounded.** Airbnb's guest-message notification emails carry a **usable
text preview** (real guest-authored text, not a content-free stub), most strongly evidenced for
short-to-medium messages; evidence (real but not independently re-verified) suggests **long
messages are truncated with an ellipsis**, requiring an app/web visit for the remainder. This is a
genuine narrowing from the prior pass's "not definitively confirmed" — but it rests on **inferential
evidence from real, current, directly-opened code** (two independently-built tools that would not
work, or would not need the design they have, against a true stub) plus one adjacent real fixture
(a different Airbnb email type that does embed full guest text), **not on a raw current
"new message" notification email I viewed myself.** That gap is real and should not be
overstated as closed.

**Cheapest remaining check, if 100% certainty is required before building the product around it:**
get one consenting host's Gmail-connected inbox (unchanged from the prior pass's recommendation)
and pull 2–3 real "new message"/"respond to" notification emails — specifically **one from a
guest who is known to have sent a long (3+ sentence) message** — and view-source it. That single
sample settles the length-cap question definitively; the "is there real text at all" question is
now well-evidenced enough from this pass to build against with a documented assumption, treating
long-message truncation as the thing to design a graceful degradation for (e.g., "preview + a
reliable push-trigger + fallback to opening the thread link for the full text") rather than as an
open unknown.

---

## GATE 2 — Does PadSplit send a host-facing late-payment / termination-risk EMAIL?

### What I found (both quotes independently curl-fetched from the live page myself, not
WebFetch-summarized, specifically to avoid a repeat of the prior pass's summarization risk)

**1. `padsplit.com/help/article/how-can-i-prevent-a-member-from-being-terminated-for-collections-11304886456852`
(Last updated April 8, 2024) — PRE-termination host email, confirmed.**
Raw page text, fetched via `curl` and stripped of HTML, quoted verbatim:

> "How do I know which Members are at risk of termination? **Hosts will receive an email 24 hours
> before a Member's termination.** Hosts can find the financial status of a Member in the
> Member's profile - Finances tab at any time. Members with a balance at $300 or greater on their
> dues day are placed in financial probation. They then have 48 hours to bring their balance under
> $300 or their Membership with PadSplit will be terminated... Hosts will be able to prevent a
> Member's termination during these 48 hours."

This is a host-addressed article (title, all body pronouns, and the described actions —
"Hosts can... issue a concession," "Hosts can... extend their termination date" — are all
host-facing), and it states plainly and specifically that an automated email is sent to the host,
timed 24 hours before the termination deadline, i.e. during the collections/late-payment
"financial probation" window. This directly answers the gate's (a) question: **email, not
dashboard-only, not nothing.**

**2. `padsplit.com/help/article/800520-How-do-I-reinstate-a-Member-who-was-terminated-for-collections`
(Last updated August 28, 2023) — POST-termination host email, confirmed, and independently
corroborates the collections-email mechanism with a different, older article.**
Raw page text, fetched via `curl`, quoted verbatim:

> "How do I know which Members have been terminated? ... There are several ways to know when a
> Member has been terminated: **Email: Hosts will receive an email when a Member is terminated.**
> Maintenance Dashboard: Whenever a Member is terminated, a room turn maintenance ticket will be
> generated in your maintenance board with the 'Collections' description... Dashboard - Members
> List: Hosts can also find the financial status of all Members by viewing the Members tab on your
> dashboard."

Note this article itself lists **three** channels (email, maintenance-dashboard ticket,
members-list dashboard) and names email FIRST and separately — a second, independent, differently-dated
(2023 vs. 2024) PadSplit help article confirming the existence of a host-facing collections
email, this time for the termination EVENT itself rather than the 24-hour warning.

**3. Corroborating context (also curl-fetched directly) — confirms the $300/48-hour "financial
probation" mechanic these two emails are tied to, and separately confirms the *member*-facing
reminder cadence the prior pass found is a genuinely distinct thing from the host emails above.**
`padsplit.com/help/article/782765-How-do-Member-Financials-work` (Last updated July 7, 2026),
quoted verbatim, under the heading *"What does PadSplit do to help Members that are facing
financial hardship?"* (note: this section is about communications TO the member):

> "The PadSplit Collections team works hard to contact and remind Members of their balances,
> upcoming deadlines and the consequences of non-payment. **We send reminders via email, app
> notifications and SMS every dues date and every time a Member is late in paying their dues.**"

This confirms the prior pass was correct to keep the member-facing reminder cadence and the
host-facing termination-risk email as two separate findings — they are. The member gets frequent
(every-dues-date, every-late-payment) reminders; the host gets the two specific, less frequent,
consequence-tied emails quoted above (24h-before-termination, and at-termination).

### GATE 2 — What is still NOT confirmed (a real, narrower residual gap, not blocking)

Neither host-facing-email article states the literal **subject line**, **sender address**, or
**itemized body fields** (member name? balance amount? a deep link to the profile? the property
address?) of either email. I searched specifically for this (`"financial probation" email
notification member balance`, `reinstate collections email host`) and found no PadSplit page or
forum post that itemizes the email's actual content — only its existence, trigger condition, and
timing. This is a real but secondary gap: it affects how precisely a parser could extract
structured fields from this specific email, not whether the host learns about the risk via email
at all.

### GATE 2 — Synthesis

The prior pass's finding was: *"confirmed a MEMBER-facing reminder cadence but could NOT confirm a
host-facing email for member delinquency."* This pass closes that gap directly from PadSplit's own
help-center documentation (two separate, independently-dated articles, both fetched and quoted
verbatim from the raw page myself), not from a WebSearch synthesis: PadSplit **does** email hosts,
automatically, tied specifically to a member's late-payment/collections process — once ~24 hours
before a termination deadline (giving the host a window to intervene with a concession or
extension), and again when the termination actually happens. This is a stronger, more specific,
and more load-bearing finding than "some late-payment host email exists" — it is tied to the exact
mechanic (the $300-balance / 48-hour financial-probation window) already documented in the prior
research, which materially increases confidence it's accurate (internally consistent across three
separate PadSplit articles fetched independently) rather than a marketing generality.

**VERDICT: RESOLVED-YES.** PadSplit sends the host an automated EMAIL (not merely an in-app/dashboard
alert) tied to member late-payment/termination risk — specifically: (a) an email ~24 hours before
a collections-driven termination (during the 48-hour "financial probation" window that starts once
a member's balance hits $300+ on their Dues Day), source: `padsplit.com/help/article/how-can-i-prevent-a-member-from-being-terminated-for-collections-11304886456852`
(updated 2024-04-08); and (b) a separate email when the termination actually occurs, source:
`padsplit.com/help/article/800520-How-do-I-reinstate-a-Member-who-was-terminated-for-collections`
(updated 2023-08-28). Both quotes above were fetched directly from the live page by me (`curl`),
not summarized by WebFetch, specifically to meet the honesty bar at full strength for this
Gate.

**Residual (non-blocking) not_found, and its cheapest check:** the exact subject line / sender
address / itemized field list of either email. Given the existence question is now settled from
two independent primary-source articles, the cheapest way to close this residual gap is **not**
Gmail-OAuth access to a real host inbox (overkill for a subject-line/sender-address question) — it
is simpler: ask any current PadSplit host directly (a 2-minute question), or search
`padsplit.com/help` for a template/screenshot article (none was found in this pass's searches, but
was not exhaustively searched beyond the queries listed above). If a raw-inbox check is ever done
for Gate 1, capturing one of these two PadSplit emails opportunistically would resolve this
residual for free.

---

## Sources actually opened this pass (WebFetch, direct `curl`, or `gh api`/`gh search`)

**Gate 1:**
- [bdyson556/AirbnbEmailParser — tests/sample_A.py](https://github.com/bdyson556/AirbnbEmailParser/blob/master/tests/sample_A.py) (fetched via `gh api`, base64-decoded, quoted)
- [bdyson556/AirbnbEmailParser — tests/sample_B.py, sample_C.py, sample_D.py](https://github.com/bdyson556/AirbnbEmailParser) (same method)
- [bdyson556/AirbnbEmailParser — tests/test_main.py](https://github.com/bdyson556/AirbnbEmailParser/blob/master/tests/test_main.py) (fetched, confirms fixtures are used as parser-correctness ground truth)
- [ddiparshan/AirbnbAgent — airbnb_bot.py](https://github.com/ddiparshan/AirbnbAgent/blob/main/airbnb_bot.py) (fetched full source, quoted)
- [ddiparshan/AirbnbAgent — README.md](https://github.com/ddiparshan/AirbnbAgent/blob/main/README.md) (fetched full text, quoted)
- [ddiparshan/AirbnbAgent — repo metadata](https://github.com/ddiparshan/AirbnbAgent) (`gh api repos/.../{created_at,pushed_at}` = 2025-11-19 / 2025-11-20)
- [mustafat52/channel-manager — app/parsers/router.py](https://github.com/mustafat52/channel-manager/blob/main/app/parsers/router.py) (fetched, quoted)
- [mustafat52/channel-manager — app/parsers/airbnb.py](https://github.com/mustafat52/channel-manager/blob/main/app/parsers/airbnb.py) (fetched, quoted)
- [mustafat52/channel-manager — repo metadata](https://github.com/mustafat52/channel-manager) (`gh api` = created 2026-02-28, pushed 2026-03-28)
- [Alon-gilad-5/Airbnb-Agentic-System — app/services/mail_mock_emails.py](https://github.com/Alon-gilad-5/Airbnb-Agentic-System/blob/main/app/services/mail_mock_emails.py) (fetched; explicitly self-labeled MOCK, used only as weak/directional evidence of a developer's assumption, not counted as content proof — flagged inline)
- [zd-1-6/airbnb_email_parser — airbnb_eml_to_sql.py](https://github.com/zd-1-6/airbnb_email_parser/blob/main/airbnb_eml_to_sql.py) (fetched, real Gmail-OAuth-based confirmation-only parser, dated Sept 2025; no message-type handling found)

**Gate 2 (all fetched via direct `curl` + HTML-strip, not WebFetch, to eliminate summarization risk):**
- [PadSplit — How can I prevent a Member from being terminated for collections?](https://www.padsplit.com/help/article/how-can-i-prevent-a-member-from-being-terminated-for-collections-11304886456852) (updated 2024-04-08)
- [PadSplit — How do I reinstate a Member who was terminated for collections?](https://www.padsplit.com/help/article/800520-How-do-I-reinstate-a-Member-who-was-terminated-for-collections) (updated 2023-08-28)
- [PadSplit — How do Member Financials work?](https://www.padsplit.com/help/article/782765-How-do-Member-Financials-work) (updated 2026-07-07)
- [PadSplit — How to interpret a Member's financial status](https://www.padsplit.com/help/article/319723-how-to-interpret-a-member-s-financial-status) (updated 2026-07-07)
- [PadSplit — What happens if I have an outstanding balance?](https://www.padsplit.com/help/article/what-happens-if-i-have-an-outstanding-balance-360039546952) (updated 2026-05-21; confirmed this is the MEMBER-facing article, kept separate from the host-facing findings)
- [PadSplit — Preparing for an eviction](https://www.padsplit.com/help/article/preparing-for-an-eviction-360060395031) (updated 2026-06-26; no email-notification content, included for completeness)
- [PadSplit — When can a Member be terminated?](https://www.padsplit.com/help/article/when-can-a-member-be-terminated-360057135891) (fetched, no channel-specific content)
- [PadSplit — Rating a Member](https://www.padsplit.com/help/article/874468-rating-a-member) (fetched, confirms a *behavioral*-score termination email exists but is a separate mechanism from the *financial*/collections one)

## Sources NOT opened this pass (blocked or dead-end — flagged so a future pass doesn't retry them the same way)

- `milled.com/airbnb`, `milled.com/search?q=airbnb` — HTTP 403 both times; also structurally
  unlikely to ever help (see Gate 1 angle 1 note on personalized-vs-broadcast email).
- `grep.app/search?q=...` — HTTP 429 (rate-limited); not retried this pass. Worth trying again in
  a future pass with delay/backoff — it indexes public GitHub code and could be a useful
  supplement to `gh search code`.
- `community.withairbnb.com/t5/Help/long-Airbnb-message-gets-cut-off-after-only-a-few-words/m-p/682581`
  — HTTP 403 on both WebFetch and direct `curl` with a real browser user-agent. Confirmed (this is
  the second research pass and the second distinct URL on this domain to hit the same wall) that
  `community.withairbnb.com` is not fetchable by this toolset at all — stop trying to open it
  directly in future passes; treat anything from it as permanently WebSearch-snippet-only unless a
  different fetch mechanism becomes available.
- `github.com/search?q=...&type=code` (the web UI) — requires GitHub login, unusable via WebFetch.
  **Use `gh search code "<query>" --limit N` instead** (already-authenticated CLI) — this is the
  one methodological finding from this pass worth carrying into the next Researcher dispatch that
  needs GitHub code search.

## Consolidated verdicts

- **GATE 1 (Airbnb guest-message content):** **RESOLVED-YES — bounded.** Usable text preview
  confirmed via new, real, dated, directly-opened code evidence (not a raw email I viewed myself);
  best-supported shape is "present in full for short/medium messages, truncated with an ellipsis
  for long ones." Residual: one raw current sample (ideally a long-message case) would remove the
  last inferential step.
- **GATE 2 (PadSplit host late-payment email):** **RESOLVED-YES.** Two independently-dated,
  directly-quoted PadSplit help-center articles confirm host-facing automated emails exist, tied
  to the collections/termination-risk process (pre-termination warning + at-termination
  notification). Residual: exact subject/sender/field-list content, a minor and cheaply-closeable
  gap (ask any current host, or capture opportunistically during any future raw-inbox check for
  Gate 1).
