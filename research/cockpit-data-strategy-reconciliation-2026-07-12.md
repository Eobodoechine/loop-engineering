# Cockpit data-acquisition strategy — reconciliation pass, 2026-07-12

Commissioned because 2026-07-11's `str-data-ingestion-strategy-2026-07-11.md` (build on
channel-manager APIs) and same-day (2026-07-12) deep-research (build on delegated co-host
access) reached CONFLICTING primary recommendations. 7 loop-team Researcher (Mode D) dispatches
+ 1 deep-research workflow run (101 agents) commissioned to reconcile. Consuming artifact:
padsplit-cockpit product strategy / the `cockpit_data_strategy_memo` artifact.

**Workflow note:** the reconciliation deep-research run's own top-level synthesis field came
back degenerate ("Test minimal call to isolate schema error" + a placeholder "test claim").
Per orchestrator.md's degenerate-output Failure Arbiter class, that field was discarded; this
synthesis was reconstructed from the run's own verify-phase log (25 claims, each independently
3-vote adversarially checked, full claim text + vote recovered from the per-agent search/fetch
transcripts) — the underlying research was real and sound, only the final packaging step broke.

## Decision (superseding both prior single-path recommendations)

**Neither prior recommendation stands as originally stated. The reconciled answer is: delegated
co-host access is the sound primary path (2026-07-12's recommendation) — but the channel-manager
API path (2026-07-11's recommendation) is not merely strategically undesirable, it is
CONTRACTUALLY BLOCKED for a competing PMS, confirmed independently by two separate research
passes.** No "dual-adapter, pick-per-host" reconciliation is viable, because one of the two
paths is closed by the vendors' own terms, not by Cockpit's own preference.

## 1. The CM-API path is closed, not just undesirable — confirmed twice, independently

Both the standalone R2 Researcher dispatch and the reconciliation workflow's own 3-vote
adversarial panel (separately sourced, separately verified) landed on the same finding:

- **Hostaway ToS §9**: bars using the API "for competing services" — confirmed 2-1 in the
  reconciliation workflow, independently confirmed in R2 (`cm-api-competitive-dependency-2026-07-12.md`).
- **Hospitable Subscription Agreement §2.7**: bars a "direct competitor" of Hospitable from
  accessing "the Services" (a defined term that includes the Software, Updates, API, and
  Documentation) without Hospitable's prior written consent — confirmed 2-1 in the reconciliation
  workflow, independently confirmed in R2.
- **Hospitable's Personal Access Token (PAT) API is explicitly NOT intended for third-party/vendor
  integrations** — confirmed 3-0 in the reconciliation workflow: "Personal access tokens... are
  for personal access only," integrating partners are expected to use OAuth, not PAT handoff.
  This directly contradicts the PAT-handoff mechanism 2026-07-11's research assumed would work.
- **OwnerRez's Listings endpoint** (the core PMS data) requires a partnership agreement with
  OwnerRez — the same approval bottleneck as the direct-OTA-API route, per R2.

No real-world precedent was found of a rival full PMS building production ingestion on a
competitor's API (R2); the closest analog found, PriceLabs, is a narrow-vertical pricing tool,
not a competing PMS, and even PriceLabs' own dual-path model (see §3 below) doesn't establish
that a *competing* product could do the same.

**Conclusion: the CM-API path is eliminated as a scalable primary OR secondary ingestion
mechanism for Cockpit specifically**, because Cockpit is the exact class of entity (a competing
PMS) these vendors' own contracts name and exclude. This is a structural/contractual bar, not a
product-preference call — it would hold even if Cockpit wanted to use it.

## 2. Delegated co-host access — reconfirmed as platform-granted, but the "agency" framing is
   weaker than the original memo asserted

Reconciliation workflow, independently re-verified:
- "Airbnb defines a co-host as a role explicitly authorized through the platform's own Co-Host
  Tools to act on the host's behalf" — **confirmed 3-0**. Platform-granted permission structure,
  not a shared-login/scraping arrangement. This holds up.
- "A 'Full Access' co-host is granted, as a named platform feature..." — **confirmed 3-0**.
- BUT: "Airbnb's terms formally frame the Full Access co-host relationship as agency: the host
  must acknowledge/warrant the co-host is authorized to act on its behalf and legally bind the
  host — directly supporting [the] characterization of co-host access as 'agency-authorized'" —
  **REFUTED 1-2**. The independent adversarial panel did NOT confirm the strong agency-in-law
  framing by the required margin. **Downgrade this claim in the memo from settled legal doctrine
  to "textually agency-shaped, not independently confirmed as dispositive agency law" — it needs
  actual counsel confirmation, not just a platform's own Co-Host Terms wording, before being
  treated as settled.**

## 3. PriceLabs — independently reconfirmed as a DIFFERENT, riskier mechanism than proposed;
   NOT strong evidence against co-host + human-triggered access

Reconciliation workflow independently reconfirms R1's finding, from separately-sourced fetches:
- "The PriceLabs Chrome extension for Airbnb required hosts to enter their actual Airbnb login
  credentials (email and password) directly into the extension... a raw credential-sharing/
  session-based mechanism, not an OAuth token exchange or platform-granted permission" —
  **confirmed 3-0**.
- "The PriceLabs Airbnb-connector extension was removed from the Chrome Web Store on 2024-05-24"
  — **confirmed 3-0**, consistent with R1's finding of an orderly, planned deprecation over a
  ~4-month migration window, not an emergency pull.
- "The only user-reported failure mode visible in the extension's reviews is login/authentication
  incompatibility... not any mention of Airbnb account flags, bans, or detected-automation
  warnings" — this specific claim scored 0-3 (refuted) in the reconciliation workflow, meaning
  the panel did NOT consider this negative-evidence framing fully proven either way — treat "no
  ToS enforcement found" as R1's best-available honest read, not an airtight absence-of-evidence
  proof.
- A more modest version of the PriceLabs-precedent claim — "PriceLabs itself already operated a
  dual-path, per-host-selected model (direct-API for unmanaged hosts, PMS-mediated for CM-using
  hosts)" — **confirmed 2-1**. A stronger version ("PriceLabs operationally *requires* CM-using
  hosts to route through their PMS") was refuted 0-3. Net: PriceLabs *supports* multiple paths
  chosen per-host; it does not *mandate* PMS-routing. This is weak, real precedent for
  segment-aware ingestion design generally, but — per §1 above — it doesn't transfer to Cockpit's
  CM-API option specifically, since Cockpit (unlike PriceLabs) is a direct PMS competitor.

**Conclusion (unchanged from R1, now independently reconfirmed): PriceLabs' abandonment is
evidence against harvest-once-then-run-unattended-server-automation on raw credentials — not
evidence against a co-host-role-scoped, human-triggered agent.** These are different mechanisms.

## 4. Fee mechanics — reconfirmed, no new relief

- "Effective October 27, 2025, all hosts using property management software... automatically
  transition to Airbnb's host-only fee structure" — confirmed 2-1.
- "Airbnb transitioned all PMS/software-connected hosts to a 15.5% host-only service fee...
  starting October 27, 2025 (16% in Brazil)" — confirmed 2-1.
- Consistent with R6's separate live-status finding: the software/API connection (not the
  co-host role) is the fee trigger, and R6 additionally found no evidence co-host accounts are
  exempt from the broader Sept/Oct 2026 all-hosts migration. Fee-avoidance remains real TODAY,
  time-limited to ~2-3 months from this writing, not a durable structural advantage.

## Net effect on the memo's recommendation

1. **Primary path unchanged: delegated co-host access (Airbnb; Booking.com's Extranet
   Primary/Admin/User system per R3).** Independently reconfirmed as platform-granted, not
   scraping. Soften the "agency law" framing to reflect the REFUTED strong-agency claim above.
2. **Eliminate, don't deprioritize, the channel-manager-API path** for Cockpit specifically —
   it's contractually closed to a competing PMS, confirmed twice independently. This also closes
   the "circumvent Hostaway as our layer" question the product owner asked about: there is no
   circumvention available under current vendor contracts short of direct written permission
   from Hostaway/Hospitable/OwnerRez, which is a business-development ask, not an engineering one.
3. **PriceLabs' abandonment is not disqualifying evidence** against the co-host + human-triggered
   design — it tested a different, riskier mechanism (raw credential harvest → unattended server
   automation) — but it is real evidence AGAINST any future "just have the agent log in with the
   host's saved password" shortcut, which the CFAA research (R5) independently shows carries real
   legal exposure once a platform sends a cease-and-desist (Amazon v. Perplexity, 2026, on appeal).
4. **Fee-avoidance stays real but time-boxed** — do not sell it as durable.

## Sources
All 7 Researcher briefs (saved 2026-07-12, same `research/` dir, filenames prefixed by topic)
+ reconciliation workflow verify-phase log (25 claims, 3-vote adversarial, 16 confirmed / 9
refuted / 0 unverified) reconstructed from `w92vuo5i0`'s per-agent search/fetch transcripts
after its top-level synthesis field returned degenerate placeholder content. Full per-agent
transcript: `<HOME>/.claude/projects/-Users-eobodoechine/dc0b6d7d-5a72-4a64-be15-c88ce0c0acb1/subagents/workflows/wf_a949b64d-86a/journal.jsonl`.

## Independent fidelity check (2026-07-12, same day)

An independent Verifier sub-agent re-derived the vote/claim mapping from the raw
per-voter `.jsonl` transcripts (not just this doc) for 7 claims — all matched. It
found the memo (not this doc) had dropped this doc's own hedge on the PriceLabs
"no ToS enforcement found" claim (reverted to R1's pre-adversarial-review phrasing,
losing the 0-3 vote and a dissenting voter's real counter-evidence that Airbnb
flagged a comparable automation tool), conflated a directly-opened Help Center page
with a 403'd Resource Center page for the Sept/Oct 2026 fee dates, presented the
Amazon v. Perplexity ruling without noting the order itself is PACER-gated and
relied on secondary law-firm alerts, and compressed a privity nuance in the
Hostaway-clause framing (binds the host who signed, not Cockpit directly). All four
were fixed in the memo. Overall verdict: PASS-WITH-CAVEATS — the reconstruction
itself was accurate; the caveats were in the memo-writing pass, now closed.

**Bounded re-verification (same day, second independent Verifier):** confirmed all 4
fixes landed correctly — none overcorrected, none left vague, no new inaccuracy
introduced, prose and HTML structurally clean. Overall verdict: PASS. Loop closed.

## Follow-up research (2026-07-12, same day): email-as-primary-channel viability

Commissioned separately to test the product owner's proposed alternative — host-inbox email
(Gmail OAuth, the TaxAhead pattern) as the PRIMARY real-time push channel instead of/alongside
delegated co-host access, since co-host access has no webhook mechanism. Full domain brief:
`research/email-ingestion-channel-2026-07-12.md`. Headline finding: the decisive question —
does Airbnb's guest-message notification email carry the actual message text or just a stub —
could NOT be definitively confirmed for the current (2025–2026) template (real 2016 code
evidence it once did; no independently-opened current source either way). Transactional email
types (booking confirmed, cancelled, paid-out; PadSplit's booking-request email) are
well-evidenced as field-rich across all platforms. PadSplit's member-messenger channel has a
confirmed, current sender/subject structure (`messenger@padsplit.com`, member-name-in-subject)
but unconfirmed body content, and its host-facing late-payment notification (arguably the most
operationally important PadSplit signal) is NOT confirmed to exist by email at all — only a
member-facing reminder cadence and an unspecified-channel host score-drop alert. Recommends a
consenting host's real Gmail-connected inbox sample (10–20 real notification emails across all
four platforms) as the single highest-leverage next step before building the message-content
extraction layer; the booking/payout/cancellation-content path is evidenced enough to build
against now. This does not change the primary-path decision above (delegated co-host access
stands) — it answers whether email can be added as a PARALLEL real-time trigger, and the
honest answer is: yes for transactional events, unconfirmed for guest messages specifically.

## Open follow-up logged
`fix_plan.md` — deep-research workflow's Synthesize phase can return a degenerate/placeholder
top-level result (`summary`/`findings` populated with literal "test" content) while the
underlying Scope/Search/Fetch/Verify phases complete correctly and produce real, adversarially-
verified claims recoverable from the verify-phase `logs` array and per-agent transcripts. Not
yet root-caused (schema-retry fallback? truncated context on the synthesis call?). Until fixed,
treat any deep-research result whose `summary`/`findings` looks templated/test-like as
degenerate-output per the Failure Arbiter, and reconstruct from `logs` + per-agent
`resultPreview` fields rather than discarding the run.
