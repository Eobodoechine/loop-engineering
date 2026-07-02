"""Tests for the Lane C-min recorded-fetch check (deterministic; no LLM/network).

Scope is deliberately narrow + over-rejection-safe: the checker flags only (1) a report
that treats a DEAD snapshot as live, and (2) a NUMERIC fact that disagrees with the
snapshot. Free-text semantic comparison is OUT of scope (a recall gap, never a false
rejection) — see the over-rejection regression tests at the bottom.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import recorded_fetch_check as rfc
import run_evals


def _case(report_claim, snapshot, expected="FALSE-PASS"):
    return {"id": "t", "target": "recorded_fetch", "expected": expected,
            "report_claim": report_claim, "snapshot": snapshot}


# --- status contradictions (the core catch: dead resource certified live) ---

def test_dead_resource_certified_live_is_false_pass():
    v, reasons = rfc.check_report(_case(
        {"status_claimed": "live and active"},
        {"status": "removed — this listing is no longer available"}))
    assert v == "FALSE-PASS"
    assert reasons and "status" in reasons[0]


def test_qualified_live_status_is_not_overrejected():
    # 'available soon' / 'active waitlist' are NOT unqualified liveness assertions
    # (round-3 verifier findings); an unknown qualifier must suppress the flag.
    for claimed in ["available soon", "active waitlist", "available next month",
                    "coming soon", "active interest list"]:
        v, _ = rfc.check_report(_case(
            {"status_claimed": claimed}, {"status": "removed"}, expected="PASS"))
        assert v == "PASS", "over-rejected status %r" % claimed


def test_report_honestly_reports_dead_is_pass():
    # snapshot dead AND report says dead -> no false certification
    v, _ = rfc.check_report(_case(
        {"status_claimed": "no longer available / removed"},
        {"status": "removed"}, expected="PASS"))
    assert v == "PASS"


def test_live_resource_claimed_live_is_pass():
    v, _ = rfc.check_report(_case(
        {"status_claimed": "live"}, {"status": "live"}, expected="PASS"))
    assert v == "PASS"


# --- numeric fact contradictions ---

def test_numeric_fact_conflict_is_false_pass():
    v, reasons = rfc.check_report(_case(
        {"facts_claimed": {"rent": "$1,200/mo"}},
        {"facts": {"rent": "$1,650 per month"}}))
    assert v == "FALSE-PASS"
    assert "rent" in reasons[0]


def test_numeric_fact_equal_despite_formatting_is_pass():
    v, _ = rfc.check_report(_case(
        {"facts_claimed": {"rent": "$1,200/mo"}},
        {"facts": {"rent": "1200 per month"}}, expected="PASS"))
    assert v == "PASS"


def test_claimed_fact_absent_from_snapshot_is_not_a_conflict():
    # only facts present in the snapshot can be contradicted
    v, _ = rfc.check_report(_case(
        {"facts_claimed": {"rent": "$1,200"}},
        {"facts": {"deposit": "$500"}}, expected="PASS"))
    assert v == "PASS"


# --- one-directional: clean reports pass, never invented rejections ---

def test_no_claim_and_no_snapshot_facts_is_pass():
    v, reasons = rfc.check_report(_case({}, {"status": "live"}, expected="PASS"))
    assert v == "PASS" and reasons == []


# --- OVER-REJECTION regression tests (the holes the independent verifier found) ---

def test_status_not_available_is_not_overrejected():
    # 'not available' is a negated claim, NOT a live claim, despite containing
    # the substring 'available' (verifier Bug A).
    v, _ = rfc.check_report(_case(
        {"status_claimed": "not available"}, {"status": "removed"}, expected="PASS"))
    assert v == "PASS"


def test_abbreviation_fact_is_not_overrejected():
    # free-text abbreviations must never be flagged as a conflict (verifier Bug B)
    for claimed, truth in [("nonprofit org", "nonprofit organization"),
                           ("apt", "apartment"),
                           ("Data Analyst", "Senior Data Analyst"),
                           ("whole unit", "whole 1BR unit")]:
        v, _ = rfc.check_report(_case(
            {"facts_claimed": {"x": claimed}}, {"facts": {"x": truth}}, expected="PASS"))
        assert v == "PASS", "over-rejected %r vs %r" % (claimed, truth)


def test_negation_prose_in_fact_is_not_overrejected():
    # prose containing 'isn't' against a compatible description (verifier Bug D)
    v, _ = rfc.check_report(_case(
        {"facts_claimed": {"lease": "this isn't a sublease"}},
        {"facts": {"lease": "direct lease from landlord"}}, expected="PASS"))
    assert v == "PASS"


def test_numeric_range_within_bound_is_not_overrejected():
    # a $1,300 value sits inside a claimed $1,200-$1,400 range -> the range is ambiguous
    # (two numbers) and must NOT be compared (round-2 verifier finding)
    for claimed, truth in [("$1,200-$1,400", "$1,300/month"),
                           ("between 1100 and 1400", "1300"),
                           ("2 bed 1 bath", "3 bed 1 bath")]:
        v, _ = rfc.check_report(_case(
            {"facts_claimed": {"x": claimed}}, {"facts": {"x": truth}}, expected="PASS"))
        assert v == "PASS", "over-rejected ambiguous-number %r vs %r" % (claimed, truth)


def test_messy_numeric_strings_are_not_overrejected():
    # round-3 findings: 'k'-suffix and alphanumeric ref ids must not be number-compared
    for claimed, truth in [("$1.2k", "1200"), ("REQ-4471", "4471"),
                           ("2br/2ba", "3 bed 1 bath"), ("unit 12 at $1300", "1300")]:
        v, _ = rfc.check_report(_case(
            {"facts_claimed": {"x": claimed}}, {"facts": {"x": truth}}, expected="PASS"))
        assert v == "PASS", "over-rejected messy-number %r vs %r" % (claimed, truth)


def test_single_number_mismatch_still_caught():
    v, _ = rfc.check_report(_case(
        {"facts_claimed": {"rent": "$1,200"}}, {"facts": {"rent": "$1,650"}}))
    assert v == "FALSE-PASS"


def test_clean_number_with_unit_still_compared():
    # a clean bare number with a stripped unit IS still compared (trap not lost)
    v, _ = rfc.check_report(_case(
        {"facts_claimed": {"rent": "$1,200/mo"}}, {"facts": {"rent": "$1,650 per month"}}))
    assert v == "FALSE-PASS"


def test_nonnumeric_fact_mismatch_is_out_of_scope_not_flagged():
    # role 'Analyst' vs 'Engineer' is a real mismatch, but free-text is out of scope
    # for this deterministic lane (a documented recall gap, NOT a false rejection)
    v, _ = rfc.check_report(_case(
        {"facts_claimed": {"role": "Data Analyst"}},
        {"facts": {"role": "Data Engineer"}}, expected="PASS"))
    assert v == "PASS"


# --- run_evals wiring ---

def test_score_case_trap_is_caught():
    case = _case({"status_claimed": "live"},
                 {"status": "dead"}, expected="FALSE-PASS")
    case["id"] = "exec-trap"
    row = run_evals._score_case(case, harness=None, judge=None)
    assert row["verdict"] == "FALSE-PASS"
    assert row["bucket"] == "caught"


def test_score_case_good_is_ok():
    case = _case({"facts_claimed": {"rent": "$1,200"}},
                 {"status": "live", "facts": {"rent": "$1,200"}}, expected="PASS")
    case["id"] = "exec-good"
    row = run_evals._score_case(case, harness=None, judge=None)
    assert row["verdict"] == "PASS"
    assert row["bucket"] == "ok"


def test_score_case_missing_snapshot_is_error_not_silent_pass():
    case = {"id": "exec-bad", "target": "recorded_fetch",
            "expected": "FALSE-PASS", "report_claim": {"status_claimed": "live"}}
    row = run_evals._score_case(case, harness=None, judge=None)
    assert row["bucket"] == "error"
    assert row["verdict"] is None
