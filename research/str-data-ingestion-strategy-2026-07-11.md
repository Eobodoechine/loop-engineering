# PMS Cockpit — STR data ingestion strategy (no scraping). 2026-07-11

Commissioned because Nnamdi flagged: "how can Cockpit be meaningful for Airbnb/VRBO hosts if we
can't scrape?" Target segment (his answer): **Airbnb/VRBO hosts who ALREADY use a channel manager.**
3 parallel Researcher streams. Consuming artifact: padsplit-cockpit product strategy.

## Bottom line
**Don't scrape. Build on a channel-manager API.** Since the target host already uses a CM, Cockpit
connects to that CM's public API and gets fully-authorized, durable, normalized data (reservations,
calendars, listings, financials, messages) across Airbnb+VRBO+Booking — the OTA integration is
already done by the CM (which IS an official Airbnb/VRBO partner). Zero scraping, zero ToS exposure,
no OTA-partner approval needed.

## Why not the alternatives
- **Direct OTA APIs (Airbnb/VRBO/Booking) — CLOSED to indies in 2026.** Airbnb "not accepting new API
  requests" (partner-gated, security review, min-scale). VRBO/Expedia Rapid = approved partners only.
  Booking.com paused new connectivity-partner onboarding. Sources: airbnb.com/help/article/3418,
  developers.expediagroup.com/rapid, developers.booking.com/connectivity/docs.
- **Scraping / host-session browser extension — fragile + dangerous.** Legally: a host reading their
  OWN data via their own credentials has the best CFAA posture (Van Buren "gates-up") and kills the
  "unauthorized access" theory — BUT still breaches Airbnb's automated-access ToS clause, and puts the
  HOST'S income-producing account at flag/suspension risk. Chronically breaks on DOM changes.
  **Decisive datapoint: PriceLabs — a funded, official Airbnb partner — shipped a host-session Chrome
  extension and then ABANDONED it, pushing hosts to API/PMS/iCal.** Use an extension, if ever, only as
  a disposable onboarding shim, never load-bearing. Sources: hiQ v. LinkedIn, Van Buren v. US,
  help.pricelabs.co (extension deprecated ~2024).
- **iCal — occupancy ONLY.** Airbnb/VRBO/Booking per-listing .ics gives future booked/blocked date
  ranges + (Airbnb) phone-last-4 + reservation URL. NO revenue, guest name (unreliable on VRBO),
  messages. Polled lag 1–4h. Good as a fallback for calendar only. Source: airbnb.com/help/article/99.
- **Email parsing — revenue + guest + occupancy (the no-partner power channel).** Airbnb/VRBO
  booking-confirmation + payout emails carry guest name, dates, confirmation code, payout amount →
  enough to rebuild revenue+occupancy at booking time. Same Gmail-OAuth tech TaxAhead already uses.
  Template-fragile; needs host inbox consent. Source: airbnb.com/help/article/1561, /2390.
- **Host CSV export — revenue (historical).** Airbnb "Gross Earnings" CSV (guest name + confirmation
  code + per-reservation amount + fees + taxes) is the richest no-partner revenue source; VRBO
  Financial Reporting; Booking Extranet. Host downloads + uploads. Source: airbnb.com/help/article/3632.

## Channel-manager API ranking (the recommended foundation)
| CM | API | Indie access | Data | Verdict |
|---|---|---|---|---|
| **Hostaway** | OAuth2 REST `api.hostaway.com/v1` | **Self-serve keys, no approval** (best) | listings, reservations w/ full financials, calendar, messaging, webhooks — all OTAs | **#1 breadth + lowest friction** |
| **Hospitable** | REST v2, **Personal Access Tokens** | **Self-serve, best DX** | properties, reservations, calendars, messaging, webhooks | **#2 fastest to build** |
| **OwnerRez** | REST v2, OAuth + PATs | Yes, very dev-oriented; docs rebuilt 2026-07 "Copy for LLM" | bookings, listings, calendars, guests, deep Airbnb financials | **#3 US owner-operators, deepest financials** |
| Guesty | Open API | Gated to Pro/Enterprise (paywalled) | comprehensive | avoid for indie TAM |
| Lodgify | REST | Pro-tier | booking/calendar-centric | ok if target on Lodgify |
| Uplisting | REST | invite-only | reservations/rates | skip |
| PriceLabs / Beyond | rate APIs | self-serve (PriceLabs) | PRICES only, not reservations | optional rate-enrichment add-on |
| AirDNA / AirROI | market-data APIs | enterprise (AirROI indie-ish) | scraped PUBLIC comps, NOT host's own data | optional market-comps add-on |

Docs: api.hostaway.com/documentation · developer.hospitable.com · api.ownerrez.com/help/v2 ·
open-api-docs.guesty.com · help.pricelabs.co/portal/en/kb/articles/pricelabs-api · airroi.com/api

## Recommendation
1. **Build a CM-agnostic ingestion adapter.** Internal data model stays CM-neutral; each CM is a plugin.
2. **Start with Hostaway (breadth + self-serve keys) or Hospitable (fastest DX / personal tokens).**
   Add OwnerRez as integration #2. Multi-CM from early = the hedge against single-CM dependency.
3. **Fallbacks for hosts NOT on a CM:** iCal (occupancy) + email-parse (revenue/guest, reuse TaxAhead
   Gmail tech) + CSV upload. Extension only as a disposable onboarding shim, never load-bearing.
4. **Market comps** (optional, separate low-trust subsystem): license AirDNA/AirROI or scrape only
   PUBLIC logged-out pages (hiQ-protected) — never behind a host login.
5. **Key strategic tradeoff:** addressable market = "hosts already on CM X"; you inherit the CM's
   uptime/rate-limits/API-openness. Multi-CM support mitigates.

## Open (deeper research dispatched next)
- Hostaway/Hospitable/OwnerRez API implementation reality: data model → Cockpit Prisma mapping, auth
  flow, webhooks, rate limits, the CM-agnostic adapter design.
- **PadSplit ingestion** — PadSplit is its OWN platform, NOT on any channel manager, so the CM-API path
  does NOT apply to the PadSplit half of Cockpit. That's the genuinely harder, unaddressed problem.

## Unverified flags
- Airbnb ToS exact wording paraphrase-confirmed only (Airbnb 403s automated fetch). VRBO iCal field set
  officially undocumented — verify against a real sample feed. Booking CSV columns not field-verified.
