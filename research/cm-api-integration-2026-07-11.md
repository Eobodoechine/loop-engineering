# PMS Cockpit — Channel-Manager API integration (buildable reference). 2026-07-11

Implementation deep-dive for building Cockpit's STR data layer on Hostaway (first) + Hospitable
(second), OwnerRez fast-follow. Companion to [str-data-ingestion-strategy-2026-07-11.md].

## Auth
- **Hostaway** (CONFIRMED): host makes creds in Settings→Hostaway API (Account ID = client_id, API Key
  = client_secret, shown once, expires 24mo). `POST https://api.hostaway.com/v1/accessTokens`
  (`grant_type=client_credentials&client_id&client_secret&scope=general`) → Bearer ~24mo. **Gotcha:
  wait 1s after minting before first use.** Cache one long-lived token per connected host. Base
  `https://api.hostaway.com/v1`.
- **Hospitable** (CONFIRMED): host mints a **Personal Access Token** in my.hospitable.com→Apps→Access
  tokens (owner/full-admin only; **Essentials tier blocked**). Lasts 1yr, no refresh (build expiry
  reminder). Base `https://public.api.hospitable.com/v2`. Financial data needs the **`financials:read`**
  scope or it's silently empty.
- **OwnerRez** (fast-follow): OAuth App (multi-host) or PAT. Base `https://api.ownerrez.com/` v2.

## Core endpoints (Hostaway, CONFIRMED)
- `GET /v1/listings?includeResources=1`, `/v1/listings/{id}` — id,name,internalListingName,address,
  capacity,bedrooms,bathrooms,price,cleaningFee,images,specialStatus(archived).
- `GET /v1/reservations?includeResources=1` — financial fields: totalPrice, baseRate, cleaningFee,
  totalPaid, **remainingBalance**, airbnbPayoutSum, cancellationPayout, guestChannelFee, hostChannelFee,
  otaPaymentProcessingFee, airbnbPassThroughTax, airbnbTransientOccupancyTax, reservationFees[].
  Guest: guestFirstName/LastName/Email/Phone. Status/dates: status, arrivalDate/departureDate,
  reservationDate, confirmationCode, channel/channelId, isArchived, ownerStay.
- `GET /v1/listings/{listingId}/calendar?includeResources=1` — per-day availability/status.
- Messaging: conversation+message objects.
- Pagination: `limit`+`afterId` CURSOR (offset deprecated). Envelope: status/result/count/page/totalPages.

## Webhooks (all 3 support real-time push — no polling for core loop)
- **Hostaway** (CONFIRMED): events Reservation created / updated / New message. `POST /v1/webhooks`
  {url, optional basic auth}. Retries 3x. **Events arrive OUT OF ORDER → dedupe by cmReservationId +
  updatedOn.**
- **Hospitable** [SECONDARY, from SDK]: reservation.created/updated, property.updated/merged,
  message.created, review.created.
- **OwnerRez** (CONFIRMED): generic entity_insert/update/delete + category filter (subscribe broadly or
  you miss `other`).

## Rate limits
- **Hostaway: 15 req/10s per IP (binding constraint), 20/10s per account.** A shared server IP across
  many hosts hits the IP cap fast → per-account token-bucket limiter + queue, maybe egress IP rotation.
- Hospitable [SECONDARY]: calendar 1000/min; message send 2/min per reservation, 50/5min global.

## CM-agnostic adapter (ports-and-adapters)
One `ChannelManagerAdapter` interface: `getListings()`, `getReservations(cursor)`, `getCalendar(listingId,
range)`, `getMessages(convId)`, `subscribeWebhooks(url)`, `parseWebhook(payload)→NormalizedEvent`.
Three impls (Hostaway/Hospitable/OwnerRez) → SAME normalized Prisma models. Every row keeps
`raw Json` + `cmSource` + `cmXId` so adapters slot in with no migration.

Normalized schema: Listing / Room(optional — Hospitable has NO room concept, Room=Listing 1:1) /
Reservation(channel enum: airbnb|vrbo|booking|direct|other) / EarningsSnapshot / CalendarDay / Message.

### Mapping gotchas (where vendors DIVERGE)
1. **Room granularity**: Hostaway/OwnerRez model sub-units; Hospitable is listing-level → make `roomId`
   NULLABLE. (Matches Cockpit's whole-home AND per-room support.)
2. **Revenue**: Hospitable ships a precomputed `revenue`(=payout+adjusted) + clean `payout`; **Hostaway
   has NO reliable single payout — derive from fees, and it's explicitly inaccurate as volume grows.**
3. **Taxes** split differently per vendor → normalize to one `taxes`, keep breakdown in `raw`.
4. **Channel**: Hostaway numeric channelId+text; Hospitable `platform` string; OwnerRez source → normalizer.
5. **ownerStay reservations (Hostaway) carry NO financials** → exclude from revenue rollups.

## CRITICAL gotcha — financial reconciliation (threatens Cockpit's revenue + collections alert)
Hostaway's own docs: payout is "not 100% accurate especially as volume increases"; **Airbnb/Booking roll
multiple reservations into ONE bank payment** → you CANNOT map deposits→bookings from the API. There is
**no actual-payout field**. → Label Cockpit "weekly revenue" as **expected/estimated, not reconciled**.
Key the **overdue/collections alert off `remainingBalance` > 0 vs due-date**, NOT bank reconciliation.
No public sandbox (Hostaway/Hospitable) — test against a real trial/empty host account.

## First-integration build plan (Hostaway first, reproduce Cockpit's existing dashboard)
1. `POST /accessTokens` → cache token (1s wait). 2. `GET /listings?includeResources=1` → Listing/Room.
3. `GET /reservations?includeResources=1` cursor-paginate, filter out ownerStay → Reservation+
EarningsSnapshot (derive revenue, store raw). 4. `GET /listings/{id}/calendar` → CalendarDay → occupancy
(reserved÷available/week). 5. `POST /webhooks` Reservation created+updated → one Next.js upsert route
(dedupe cmReservationId+updatedOn). PLUS a nightly reconciliation poll (out-of-order events + lagging
financials). Dashboard: rooms=Listing/Room; occupancy=CalendarDay; weekly revenue=Σ EarningsSnapshot
(labelled estimated); overdue alert=remainingBalance>0 vs arrivalDate.

## UNVERIFIED (confirm in first spike)
Hospitable JSON keys (platform/check_in/reservation_status) — Stoplight SPA blocked WebFetch. OwnerRez
full field schema at api.ownerreservations.com/help/v2. Whether any sandbox exists (email support).

Docs: api.hostaway.com/documentation · developer.hospitable.com · help.hospitable.com/en/articles/
5651284 · api.ownerrez.com/help/v2 · github.com/keithah/hospitable-python [SECONDARY].
