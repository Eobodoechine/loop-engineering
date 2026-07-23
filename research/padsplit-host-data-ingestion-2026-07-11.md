# PMS Cockpit — PadSplit host data ingestion (no scraping). 2026-07-11

Companion to [str-data-ingestion-strategy-2026-07-11.md]. The STR side is solved via channel-manager
APIs; this is the PadSplit half, which is harder because PadSplit is its OWN closed marketplace + PMS
with no external API and an anti-automation ToS.

## Bottom line
PadSplit has **no host API and no developer program**, and its ToS explicitly bans scraping/automated
access. BUT the host can **export a rich CSV** that already contains the operational data Cockpit
needs — so the core PadSplit dashboard is buildable from a **host-uploaded export**, ToS-clean, no
scraping. Live between-export status is an optional enhancement, not the backbone.

## The load-bearing channel: host CSV export (first-party, ToS-clean)
From the Host Earnings Dashboard: "Export CSV (12 months)" → a ZIP of CSVs:
- `summary.csv`: Gross Collected (Col G, matches 1099-K), PadSplit fees deducted.
- **member-transaction detail: per-member bills, per-member payments, property address, payout month**
  — enough to reconstruct per-room/per-member rent-collection status.
- Occupancy CSV: per-room prices, days-on-market, price/occupancy history, occupancy-by-month.
- Maintenance tickets export; 1099 forms.
Source: padsplit.com/help/article/new-earnings-dashboard-47579746918420,
padsplit.com/help/article/padsplit-host-tax-reporting-45834808435988.
→ **Cockpit's core view (rooms, occupancy, rent-collection, payouts) can run entirely off this upload.**

## Host dashboard exposes (for reference)
Properties/rooms (per-occupant pricing, door codes, activate/deactivate), members (occupancy status,
profiles, co-host perms), "True Occupancy" (flags rooms needing attention), Financials (income/
expenses/net by month+property, dues-collection tracking at tenant/property/portfolio level),
Messenger (host↔member), Maintenance/Tasks. Source: padsplit.com/help/topic/how-to-navigate-the-host-dashboard-4404909037332.

## Payout mechanics (design for reconciliation)
PadSplit collects member rent weekly internally, pays host ONE consolidated monthly payout in arrears,
net of **8% fee**, by ~10th (≤20th) of following month. → A bank/Plaid feed shows one lump deposit,
CANNOT reconcile per-member; use bank feed only for coarse payout-arrived verification.

## Ingestion stack (priority order)
1. **Foundation — host-uploaded CSV/report exports.** ToS-clean, first-party, already per-member. Build first.
2. **Supplement — parsed PadSplit notification emails** (move-out confirmed; payout/move-in likely).
   Reuse the TaxAhead Gmail-OAuth tech. ⚠️ UNVERIFIED: exact email payloads — validate with a real
   host's forwarded samples before writing the parser schema.
3. **Optional enhancement — consenting host-session extension** for LIVE per-member paid/late status +
   messages + real-time occupancy the exports miss. ToS-gray (PadSplit bans automated access; risk lands
   on the host's account — lower detection risk than Airbnb since PadSplit is smaller, but high
   consequence). Opt-in, host-owned-session only, NEVER the sole source of a critical field.

## Strategic notes
- **White space:** no existing third-party tool ingests PadSplit host data programmatically — genuine
  opportunity (only done-for-you management services exist, e.g. Out Fast).
- **Contrast with STR:** STR gets a channel-manager abstraction layer; PadSplit has none, so the stack
  is host-consented (upload + email + optional extension), CSV-upload being the durable core.
- PadSplit only CONSUMES others' APIs (RemoteLock smart-locks, Dialpad CRM) — it exposes none.

## UNVERIFIED / probe-next (resolve with one consenting host's real export + emails)
(a) exact payout/payment/move-in email contents; (b) whether current-cycle per-member "paid vs late"
is in any export or only on-screen live; (c) full column list of the non-summary earnings CSVs.

Sources: padsplit.com/terms-of-use; earnings-dashboard + tax-reporting + host-dashboard + occupancy +
payout-FAQ + fee-model help articles (URLs in the padsplit help center).
