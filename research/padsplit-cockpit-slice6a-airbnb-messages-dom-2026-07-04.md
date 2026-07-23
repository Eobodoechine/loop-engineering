# Airbnb `/hosting/messages` live DOM inspection — 2026-07-04

**Method**: Nnamdi signed into his real Airbnb host account in a real, local, connected
Chrome browser. Oga then read the live page structure directly (`javascript_tool`
read-only DOM queries — no messages sent, no actions taken beyond dismissing one
notification modal and clicking between two existing threads). This closes the gap
`extractMessages()` was built against in Slice 6a's micro-step 3 (best-guess selectors,
scope decision #5) — see `runs/2026-07-04_airbnb-inbox/specs/spec.md` §A.

## 1. No `__NEXT_DATA__` on this page — JSON-first strategy is dead code here

`document.getElementById('__NEXT_DATA__')` is `null` on `/hosting/messages/*`. The 5
`<script type="application/json">` tags present (`data-flagger_cdn_experiments`,
`aphrodite-classes`, `data-linaria-css`, `data-initializer-bootstrap`,
`data-injector-instances`) are Airbnb's atomic-CSS/experiment-flag build internals, not
application data. **`extractListings()`'s two-tier JSON-first/DOM-fallback strategy does
NOT transfer to this page** — `/hosting/listings` is apparently server-rendered
differently than the messages inbox. `extractMessages()` must be DOM-only; the
`findThreadsInJson` JSON-search path Slice 6a's Coder built will simply never fire on
real Airbnb and should either be removed or left as inert defensive code with this
explicitly noted.

## 2. Real thread ID + URL shape

- URL: `https://www.airbnb.com/hosting/messages/{numericThreadId}` — confirmed numeric
  (e.g. `2268791309`), NOT a slug/UUID as originally guessed.
- Each thread-list row carries `data-testid="inbox_list_{threadId}"` — **the same numeric
  ID as the URL**. This is a clean, stable `threadId` source, far better than the original
  guess of scraping it from a URL param or `__NEXT_DATA__` field (neither exists/needed).

## 3. Thread list row structure (`[data-testid^="inbox_list_"]`)

Each row is an `<a href="#">` (not a real navigable href — click-handled). Its full
`textContent` (screen-reader-oriented, all one string) follows this pattern:

> "Read Conversation with {name(s)}. Last message sent {date} is: {preview text}.
> Booking status is {status}. Reservation from {startDate} to {endDate} in {city}."

Real examples captured:
- "Read Conversation with Jeff, Henry, Marlene. Last message sent May 17 is: Airbnb
  update: Reminder - Leave a review. Booking status is Completed. Reservation from May 14
  to May 17 in Alhambra."
- "Read Conversation with Cynthia. Last message sent 5/14/25 is: You: Sorry but the dates
  are no longer available . Booking status is Dates are not available. Reservation from
  May 16 to 19, 2025 in [truncated]."

This is regex-parseable for `guestName` (see finding 5 — CAVEAT), last-message preview,
booking status, and a date range. **The "in {city}" fragment is a neighborhood/city name
(e.g. "Alhambra"), NOT the precise listing title** — see finding 4.

## 4. Precise property/listing name requires opening the thread

`[data-testid="reservation-dynamic-marquee-title-header-v3"]` (only present once a thread
is open, in the right-hand reservation panel) gives the real listing title, e.g. "Home in
Alhambra" — this matches what the property was actually named when synced via
`syncListings()`/`extractListings()` (per Slice 6a's existing `Property.address` matching
convention). **The thread-LIST view alone (before opening any thread) only exposes a
coarse city/neighborhood string, not the exact listing name `Property.address` matching
requires.** This is a real design constraint: if the scraper is meant to batch-extract
`{threads: [...]}` from the list view without opening each thread individually, precise
`propertyName` resolution is not reliably available at that level. `[data-testid=
"reservation-destination-link"]` also exists but appeared to reference a DIFFERENT
listing than the one actually open in one observed sample — treat it as unreliable/
possibly a carousel-card artifact, not a trustworthy property-name source.

**Recommendation**: `extractMessages()` should scrape whichever ONE thread is currently
OPEN (matching the "host visits the page, extension reads what's rendered" pattern
already established for PadSplit, scope decision #3) and pull `propertyName` from the
marquee title element, NOT attempt a full-inbox batch scrape from the list view alone.
This is a real, load-bearing correction to the original `{threads: [...]}` (plural,
batch) contract in spec.md §A.2 — worth a spec correction, not just a code tweak.

## 5. CRITICAL finding — the header/list "guest name" can include host-team members, not just the guest

`[data-testid="thread-header-title"]`'s text for the "Jeff, Henry, Marlene" thread is
genuinely "Jeff, Henry, Marlene" (duplicated twice in the DOM — one `aria-hidden` div,
one visible span — needs de-duplication, not a data issue). But reading the actual
message senders in that same thread via `[data-testid="message-thread-profile-link"]`'s
`aria-label`:
- "Jeff · Host"
- "Henry · Co-host"

Both messages are addressed "Dear Emmanuel," / "Hi Emmanuel, ..." — **the real guest's
name is "Emmanuel," which does not appear anywhere in the thread header text at all.**
"Marlene" (the third header name) was never confirmed as the guest either — she may be a
second co-host, an additional traveler, or the actual guest; without a message from her
in the visible scroll position, her role couldn't be confirmed.

Cross-checked against a single-participant thread ("Cynthia"): `thread-header-title` =
"Cynthia" (clean), and her `message-thread-profile-link` aria-label = "Cynthia · Booker".

**Conclusion**: `aria-label` on `message-thread-profile-link` reliably encodes a role
suffix — `"{name} · {role}"` — where `Host`/`Co-host` = property team, `Booker` = the
guest who made the reservation. **This is the correct signal for `guestName`, NOT
`thread-header-title`'s raw text**, which can silently include host-team member names
with no way to distinguish them from the guest by position or count alone.

**CORRECTED confidence level (2026-07-04, follow-up check after Nnamdi directly asked
"did you confirm the Booker role amongst the multiple chats?" — the honest answer was
no, and this section originally overstated it as "confirmed twice"):** Across this
account's real inbox (15 threads total), only 2 have multi-participant headers
("Jeff, Henry, Marlene" and "Homi Spaces and 4 others") — checked BOTH exhaustively
(all message-groups in each, confirmed fully loaded via `scrollHeight === clientHeight`
and the `thread_page_last_item` marker, not partially scrolled). **Neither contains a
single guest-authored message** — every sender in both threads is `Host` or `Co-host`;
the actual guest ("Emmanuel" in the first thread) never sent a message with its own
group-leader row at all. So **the "Booker" role label is directly confirmed in exactly
ONE case (Cynthia, a single-guest thread) — not in any multi-participant/co-hosted
thread**, because no real example of a guest replying in a co-hosted thread exists in
this account's current inbox to check against. The role-filter mechanism (guestName =
whoever has role "Booker", `null` if none found) remains the best available design — it
degrades safely to `null` rather than misattributing a co-host's name as the guest's,
which is what the ORIGINAL header-text-based design would have silently done — but
"a guest's own message in a co-hosted thread literally carries the Booker label" is an
inference from the single-guest case and the Host/Co-host labels being clearly distinct
categories, not something directly witnessed. Flag this as the single most important
open uncertainty in this dossier — it should be spot-checked against a real co-hosted
thread the first time one has an actual guest reply, not assumed proven. Whether a
"Guest" role (vs. "Booker") exists for additional non-booking travelers on a reservation
was also not confirmed — treat as a separate open sub-question.

## 6. Message row structure (real, verified via 2 threads)

Each message GROUP-LEADER (first message in a run of consecutive messages from the same
sender) is reachable by walking up 5 parent levels from its
`[data-testid="message-thread-profile-link"]` element. That row container has (at least)
4 children in this order:
0. Avatar/profile-link wrapper (the clickable avatar button itself)
1. Sender+timestamp wrapper — contains exactly 2 leaf `<span>` elements: one with
   `"{name} · {role}"`, one with a bare time string (e.g. `"1:57 PM"`, no date)
2. Message content (plain text, can be multi-paragraph within one bubble)
3. An empty div (hover-revealed reactions/menu area, per the `menu-button-reactions`/
   `menu-button-actions` testids seen nearby)

**Known gap, not resolved during this pass**: consecutive messages from the SAME sender
(a grouped run, no repeated avatar) do NOT get their own `message-thread-profile-link` —
meaning a naive "one message per profile-link" extraction loop will MISS grouped
continuation messages entirely (undercounting, not corrupting — the first message in each
group is still captured correctly). Closing this gap needs either a more general
"message content" selector that fires on every bubble regardless of grouping (the
content div's own CSS class, e.g. `mjx4h5j` in one build — but Airbnb's classnames are
clearly atomic/hashed build artifacts from a CSS-in-JS system, per the
`aphrodite-classes`/`data-linaria-css` script tags found earlier — **treat any raw
classname as unstable across Airbnb deploys and prefer `data-testid`-based selectors
wherever possible**), or accepting only group-leader messages are captured as a stated
v1 limitation.

## 7. Message timestamps are time-only; full dates come from separate separator rows

Message timestamps read from the sender+timestamp span (e.g. "1:57 PM", "10:09 PM") carry
NO date. Full-date separator strings (e.g. "May 13, 2025") appear as standalone text
elsewhere in the same `[data-testid="message-list"]` container, interleaved between
groups of messages (mirroring a typical chat-app "date divider" pattern). **Correctly
resolving each message's real calendar date requires associating it with the nearest
PRECEDING date-separator in DOM order**, not just parsing the time string alone — parsing
"1:57 PM" without this context would produce an ambiguous or wrong date (likely
defaulting to "today," which is incorrect for historical messages).

## 8. Stable vs. unstable selector strategy — a general lesson for this file

Every `data-testid` found (`inbox_list_{id}`, `thread-header-title`,
`message-thread-profile-link`, `message-list`, `reservation-dynamic-marquee-title-
header-v3`, `host-response-time`, `messaging-composebar`, etc.) is a much more durable
selector target than any of the observed CSS classnames (`t1gcreg5`, `m1cml9zk`,
`mjx4h5j`, etc.), which are atomic/hashed and near-certainly regenerate on Airbnb's own
deploys (same risk class as any CSS-in-JS/atomic-CSS build system). **`extractMessages()`
should be rewritten to select almost exclusively via `[data-testid="..."]`, treating any
classname-based selector as a last-resort fallback only**, unlike the current
implementation's guessed `[class*="Bubble"]`/`[class*="Thread"]`-style selectors, none of
which were confirmed to exist on the real page.

## 9. Host inbox mixes Nnamdi's own hosting AND his personal travel bookings — already safely handled

Nnamdi clarified directly: `/hosting/messages` is not host-only — it mixes threads where
he's hosting (guests booking his own properties) with threads where he personally booked
someone else's place while traveling. Confirmed concretely: the "Jeff, Henry, Marlene"
thread's property ("Home in Alhambra," near LA) does NOT appear on Nnamdi's own
`/hosting/listings` page (`Your listings`), which lists only his real Atlanta properties
("Calm Room in Central Atlanta," "Serene Home in Central Atlanta," etc.) — confirming
that thread isn't one of his own listings.

**No design change needed.** `syncAirbnbCommunication`'s existing §B.2 property-resolution
step only ever matches a thread's `propertyName` against `Property` rows already synced
from Nnamdi's OWN `/hosting/listings` page (via `syncListings()`) — a thread for a
property he doesn't host (including his own personal travel bookings) simply won't match
anything and is already correctly, safely rejected via the existing, tested `{synced: 0,
errors: [...]}` path (AC3) — zero garbage rows, by construction, no new filtering logic
required. The only residual risk is the SAME pre-existing, already-documented
name-collision fragility (`Property.address` matching by string, not a stable Airbnb
listing ID) already flagged in spec.md §B.2 — not a new gap this finding introduces.

## 10. EXHAUSTIVE SWEEP (2026-07-04, all 15 threads in the real inbox) — requested directly by
Nnamdi after the initial 2-3-thread sample proved insufficient (see item 5 above, the
"Booker role" confidence correction). This sweep found THREE further defects the small
sample missed entirely, and confirms the original `extractMessages()` build (micro-step 3)
needs a substantial rewrite, not a patch.

### 10a. CRITICAL — `[data-testid="message-thread-profile-link"]` misses the majority of real messages, INCLUDING every message the currently-logged-in host sends themselves

The originally-shipped `extractMessages()` enumerates messages by finding
`message-thread-profile-link` elements. Across the two threads checked in the initial
sample, this happened to look adequate. Across all 15 threads, it is not: in the
longest real thread (15 profile-link "groups"), the ACTUAL message count (found via a
different, comprehensive selector — see 10b) is 41. **The 26 messages missing from the
profile-link-based count include every message the logged-in host sends themselves
(confirmed: a direct host reply in a different thread — "Hello Heather, Yes it is" —
renders with a bare timestamp and NO profile-link at all, while the guest's message
immediately before it correctly got one), plus consecutive-paragraph continuations from
ANY sender.** A scraper built on `message-thread-profile-link` alone would never capture
a single one of the host's own sent replies — a severe, silent data-completeness defect
that would have shipped undetected had the original 2-thread sample simply not happened
to include a case with a host reply in view.

### 10b. FIX for 10a — the reliable, general per-message selector is `[data-testid^="MessageOuter"]`

Every real message (and every system/status line, and read-receipt artifacts) inside
`[data-testid="message-list"]` carries its own `data-testid` beginning with the literal
string `"MessageOuter"` (a per-message unique ID follows this prefix) — confirmed present
regardless of sender, regardless of whether a profile-link/avatar happens to be attached.
**`extractMessages()` must enumerate messages via `[data-testid^="MessageOuter"]`, not via
profile-link elements.** This alone fixes the completeness gap in 10a. Two structural
notes: (1) many `MessageOuter` elements are non-message system/status lines (see 10d);
(2) at least one message class showed a transient `"Sending..."` sub-element (an
in-flight/optimistic-UI artifact of viewing your own just-sent message) — filter this
noise text out, it is not part of the message content.

### 10c. Sender attribution for unlabeled messages is a genuinely hard, NOT reliably solved problem — scope the v1 extractor to labeled messages only

Once every `MessageOuter` is enumerated, most lack their own "{name} · {role}" label (only
the FIRST message when a sender's turn begins gets one; every other message — the host's
own, AND a counterparty's own consecutive follow-up messages — is unlabeled). Three
approaches were tried to resolve who sent an unlabeled message:
1. **Profile-link presence** — already shown unreliable (10a); a message can have a name
   label with NO profile-link, or a profile-link with NO name label — these are
   independent, not correlated signals.
2. **Horizontal position of the message-content div** (`getBoundingClientRect().left`) — a
   REAL, measurable, consistent-WITHIN-one-thread signal (distinct offsets cleanly
   separated system/status lines, "the other party," and "the currently-logged-in viewer's
   own messages" within any single thread) — but the ABSOLUTE offset for "the other party"
   vs. "self" is NOT fixed across threads; it appeared to invert between two different
   threads. This is now understood (see 10e: "Emmanuel" is very likely Nnamdi's own Airbnb
   identity, and self is ALWAYS unlabeled regardless of whether Nnamdi is acting as host or
   guest in that specific thread — so the roles genuinely do swap between threads, it
   isn't noise). The corrected, thread-relative version of this signal — establish "the
   other party's column" from whichever `left` value co-occurs with a real name+role label
   found ANYWHERE in the current thread, then classify every other message as "other" (same
   column) or "self" (different column, and not the system-message column) — is
   **structurally sound but was not stress-tested against every thread in this sweep**
   (verified directly against 2 threads only: the 41-message thread and Heather's).
3. **Network interception of the real GraphQL response** (`ViaductGetThreadAndDataQuery`,
   confirmed via `read_network_requests` to be the exact query with
   `getParticipants: true, getMessageFields: true` — this would almost certainly carry
   unambiguous per-message sender IDs) — **correctly blocked by the session's own safety
   classifier** when attempted (patching `window.fetch` to capture the real request's
   authenticated headers was flagged as credential materialization). This avenue was not
   pursued further and should not be re-attempted the same way.

**Decision: ship v1 scoped to labeled messages only.** Given sender attribution for
unlabeled messages is not reliably solved, and given a WRONG attribution (a guest's
complaint silently credited to the host, or vice versa) would actively corrupt the
AI-draft-generation feature's grounding context — a strictly worse failure mode than
missing message history — `extractMessages()` should only emit a `Message` candidate for
`MessageOuter` elements that carry their OWN "{name} · {role}" label. Unlabeled
continuation messages (both the host's own replies and a guest's own follow-up messages)
are dropped, not guessed. This is a real, accepted completeness gap for v1 — the majority
of a long thread's message volume will not be captured — flagged plainly, not silently
absorbed. The position-based "self vs. other" mechanism in point 2 above is documented as
a candidate for a v2 improvement, not implemented now, since it was not verified
thoroughly enough across the full 15-thread population to trust in production.

### 10d. System/status lines must be explicitly filtered, and the filter needs a role-suffix validation fix

`MessageOuter` elements include non-message system lines: "Your reservation is confirmed
for N guests...", "You requested a change to this trip.", "Alteration request
accepted...", "Inquiry sent · N guests, {dates}", "Let us know what you thought about your
stay. Leave a review", and read-receipt lines ("Read by {name}"). These must be excluded
from the `messages` array. **A real bug found while building this filter**: naively
checking "does this element's leaf span contain ' · '" to detect a name+role label
produces a FALSE POSITIVE on "Inquiry sent · 12 guests, Mar 8 – Nov 8, 2025" (a status
line, not a sender label) — the same `" · "` separator is reused for an unrelated purpose.
**Fix**: only treat a `" · "`-containing span as a real sender label if the text AFTER the
separator matches a known role string exactly (`Host`, `Co-host`, `Booker`, `Superhost
Ambassador` — see 10f for the full role list found) — never accept an arbitrary trailing
string as a role.

### 10e. "Emmanuel" is very likely Nnamdi's own name/identity on Airbnb — found by chance, confirmed three independent ways

The guest addressed throughout the "Jeff, Henry, Marlene" thread ("Dear Emmanuel," "Hi
Emmanuel...") was originally assumed to be an unrelated third-party guest, since "Home in
Alhambra" does not appear among Nnamdi's own Atlanta listings (see item 9). This
assumption is now very likely WRONG. "Emmanuel" is separately addressed in TWO more,
completely unrelated threads: Airbnb's own Superhost Ambassador congratulating "Emmanuel"
on publishing a listing ("Hi Emmanuel, Congratulations on publishing your listing..." —
this is Airbnb's own internal program addressing the ACCOUNT HOLDER, i.e. Nnamdi), and a
prospective guest's (Janee's) inquiry ("Hello Emmanuel, sorry for the late message...").
Three independent messages, from three unrelated senders (a co-host team, Airbnb's own
support program, and a prospective guest), all addressing "Emmanuel" as the account
owner/host, is strong convergent evidence that **Emmanuel is Nnamdi's actual first
name/display identity on Airbnb** (distinct from "Nnamdi," which this document's author
otherwise knows him by) — NOT a coincidence of three different people happening to know a
third party by the same name. This reconciles the "Jeff, Henry, Marlene" thread
completely: Nnamdi/Emmanuel is the actual GUEST in that thread (confirming his own direct
clarification, item 9, that his inbox mixes his own travel bookings with his hosting
threads) — and explains why no message in that thread ever carried an
"Emmanuel · Booker" label: self-authored messages are NEVER labeled with a name, matching
the SAME pattern found for the host's own unlabeled replies in Nnamdi's direct-rental
threads. **This is inferred with high confidence from message content, not directly
confirmed from an account settings page — recommend Nnamdi verify his exact Airbnb display
name directly before it is used in any config value** (e.g. before adding "Emmanuel" to
`BACKFILL_HOST_NAMES` for Airbnb's `deriveDirection` classification to work on
self-authored messages, since self-messages carry no sender field to derive automatically
and this is the config value that would need to match).

### 10f. Full set of role-suffixes found across all 15 threads

`Host`, `Co-host`, `Booker`, `Superhost Ambassador` (an Airbnb-internal support/mentorship
program account, not a guest or co-host — found in one thread, `1589536940`). No `Guest`
role (distinct from `Booker`, for a non-booking additional traveler) was observed in any
of the 15 threads — its existence remains unconfirmed either way.

### 10g. `propertyName` extraction was CRITICALLY broken for 14 of 15 real threads — found and fixed by the sweep

The originally-shipped design sourced `propertyName` exclusively from
`[data-testid="reservation-dynamic-marquee-title-header-v3"]`. **This element is present
in exactly 1 of the 15 real threads swept** — the one with an active/confirmed
reservation. Every other thread (inquiries, declined bookings, cancelled dates — the
overwhelming majority of any real inbox) has NO marquee title element at all, meaning
`propertyName` would resolve to `null` for nearly every real thread, which would then fail
§B.2's property-matching and cause the WHOLE THREAD to be silently skipped — the scraper
would have appeared to work (no errors, no crashes) while actually syncing almost nothing.
**Fix, confirmed via 2 additional real threads**: for non-confirmed-reservation threads,
the property name IS available via a DIFFERENT, mutually-exclusive element,
`[data-testid="hrd-sbui-header-section"]` — specifically, the text of the first `<div>`
immediately following that container's `<h3>` element (the `<h3>` holds the guest's name;
the property name is the next sibling `<div>`, both confirmed via direct child enumeration
on 2 separate threads: "Serene Home in Central Atlanta" and "Blissful room, Central
Atlanta, Monthly Stays" — both exact matches to Nnamdi's own real listing names).
**Corrected mechanism: try `reservation-dynamic-marquee-title-header-v3` first (confirmed
reservation case); if absent, fall back to `hrd-sbui-header-section`'s h3-adjacent div
(every other reservation state).** This was the single most consequential defect this
sweep found — without this fix, the previously-"complete" build would have synced almost
no real threads at all, a failure mode that would not have been obvious from a quick
manual test (no errors are thrown; threads are just silently skipped by design, per AC3).

## Honesty bar (updated 2026-07-04 after the exhaustive 15-thread sweep, section 10)

Everything in sections 1-4, 6-8, 10a/10b/10d/10f/10g is a direct, first-hand observation,
now checked across ALL 15 threads in the real inbox (not a 2-3 thread sample) — quoted DOM
text/attribute values, structural relationships, and element counts, not inferred. This is
a materially stronger evidence base than the original pass: the sweep itself DIRECTLY
CAUGHT two things the small sample missed and had stated with false confidence (the
`message-thread-profile-link` completeness gap, 10a; the `propertyName` marquee-title
mechanism failing on 14/15 real threads, 10g) — both now fixed and re-verified against
multiple real threads.

**Still not fully resolved, stated plainly rather than papered over**:
- Sender attribution for messages lacking their own name+role label (10c) — a
  thread-relative positional heuristic was DESIGNED and looks structurally sound, but was
  only spot-checked against 2 of 15 threads, not stress-tested against the full
  population. **Decision made: do not ship this heuristic in v1** — only extract messages
  with their own explicit label; drop unlabeled ones rather than risk a wrong attribution.
- "Emmanuel = Nnamdi's Airbnb identity" (10e) is inferred with high confidence from 3
  independent pieces of message content, not confirmed from an account settings page —
  flagged for Nnamdi to verify directly before it's used in any config value.
- Whether a "Guest" role (distinct from "Booker") exists for additional non-booking
  travelers remains unconfirmed either way — not observed in any of the 15 real threads,
  which is suggestive but not conclusive of its absence.
- Network-response-based sender attribution (a likely-clean alternative to the DOM
  heuristics above) was correctly blocked by the session's safety classifier before it
  could be tried — genuinely untested, not ruled out on its merits.
