"""Lane C-min — deterministic recorded-fetch check (execution against RECORDED
ground truth).

The EXECUTION analog of `arithmetic_check`: instead of asking an LLM judge whether a
report's claim about an external resource is true, the harness compares the report's
STATED claims against a FROZEN snapshot of that resource and flags any contradiction
in code. No LLM, no network.

Why this exists: the verifier's "reality check / open the URL" mandate was, until now,
only INSTRUCTED in prose and judged from prose — the eval never actually checked a
fetched resource, so a report could *say* a dead listing was live and a text-only judge
had nothing to compare against. This lane closes that: the `snapshot` IS the recorded
ground truth (deliberately an artifact — it proves the report-claim-vs-fetched-evidence
MECHANISM under deterministic, frozen gold; it is the first rung, NOT live-URL reality,
which has no stable gold).

SACRED PROPERTY — one-directional, never over-reject. It must only flag a PROVABLE
contradiction (-> FALSE-PASS); a correct report must always return PASS. So both checks
compare ONLY when the values are UNAMBIGUOUS, and default to "consistent" otherwise:
  - status: flag iff the snapshot is dead AND the claimed status is an UNQUALIFIED
    liveness assertion (composed entirely of live-words + connectors). Any unrecognized
    qualifier ('soon', 'waitlist', 'not', 'removed') => not a clean live claim => no flag.
  - facts: flag iff BOTH the claim and the snapshot reduce to a CLEAN BARE NUMBER and
    they differ. A range / compound / unit-suffixed-non-numeric ('$1,200-$1,400',
    '$1.2k', 'REQ-4471', '2br/2ba') => not comparable => no flag.
Missed contradictions are an accepted recall gap; a false rejection of a good report is
not. Semantic free-text comparison is the LLM judge's job, not this lane's.
"""

import re

# Snapshot-status markers that mean the resource is gone / not actually available.
_DEAD = ("dead", "removed", "expired", "unavailable", "closed", "404",
         "not found", "gone", "filled", "off-market", "off market",
         "no longer available", "deleted", "taken down")
# Words that, ALONE or combined, assert the resource is present / usable right now.
_LIVE = {"live", "active", "available", "open", "listed", "up", "online",
         "accepting", "current", "submitted", "received"}
# Filler that may appear alongside live-words without qualifying them away.
_CONNECTOR = {"and", "or", "now", "currently", "still", "the", "is", "are", "it",
              "this", "unit", "listing", "status", "fully", "yes", "page", "posting"}
# Trailing rent/pay unit suffixes stripped before testing if a fact is a bare number.
_UNIT_RE = re.compile(r"\b(per month|per mo|a month|monthly|month|mo|"
                      r"/month|/mo|per year|annually|yr|year|per hour|hr|hour)\b")


def _norm(s):
    s = str(s).strip().lower().replace("$", "").replace(",", "")
    return re.sub(r"\s+", " ", s)


def _clean_num(s):
    """Return the value IFF the whole string reduces to ONE clean bare number (after
    stripping currency/commas and a trailing rent/pay unit), else None.

    A range, compound, or anything with letters or extra structure ('$1,200-$1,400',
    '$1.2k', 'REQ-4471', '2br/2ba', '1200 per month was 1400') reduces to non-numeric
    and returns None — it is NOT compared, so a correct report with such a value is
    never false-rejected.
    """
    t = _UNIT_RE.sub(" ", _norm(s)).replace("/mo", " ").replace("/month", " ")
    t = re.sub(r"\s+", "", t)
    return float(t) if re.fullmatch(r"-?\d+(?:\.\d+)?", t) else None


def _values_conflict(claimed, truth):
    """True iff a claimed CLEAN-NUMBER value disagrees with the recorded clean-number
    value. Non-numeric / ambiguous values are treated as consistent (see _clean_num)."""
    a, b = _clean_num(claimed), _clean_num(truth)
    return a is not None and b is not None and a != b


def check_report(case):
    """Compare a report's claims against the recorded snapshot.

    Returns (verdict, reasons): 'FALSE-PASS' (with the contradicting reasons) iff the
    report contradicts the snapshot — it certifies a dead resource as live, or asserts
    a clean-number fact that disagrees with the snapshot's recorded number — else 'PASS'.
    """
    claim = case.get("report_claim") or {}
    snap = case.get("snapshot") or {}
    reasons = []

    snap_dead = any(d in _norm(snap.get("status", "")) for d in _DEAD)
    toks = _norm(claim.get("status_claimed", "")).split()
    # A clean live claim = at least one live word AND every token recognized (live or
    # connector). Any unknown token ('soon', 'waitlist', 'not', 'removed') => not clean
    # => not flagged. Conservative by design (a missed trap beats an over-rejection).
    claims_live = (any(t in _LIVE for t in toks)
                   and all(t in _LIVE or t in _CONNECTOR for t in toks))
    if snap_dead and claims_live:
        reasons.append("status: report claims %r but the snapshot shows %r"
                       % (claim.get("status_claimed"), snap.get("status")))

    snap_facts = snap.get("facts") or {}
    for k, claimed_v in (claim.get("facts_claimed") or {}).items():
        if k in snap_facts and _values_conflict(claimed_v, snap_facts[k]):
            reasons.append("fact %r: report claims %r, snapshot has %r"
                           % (k, claimed_v, snap_facts[k]))

    return ("FALSE-PASS", reasons) if reasons else ("PASS", [])
