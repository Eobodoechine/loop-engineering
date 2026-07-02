import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

import citation_grounding
import run_evals


ARTIFACTS = {
    "EVIDENCE_001": {
        "source_type": "github_issue",
        "source_id": "65795",
        "url": "https://github.com/org/repo/issues/65795",
        "excerpt": "The bug affects retry behavior in the scheduler when the session journal is compacted mid-run.",
    },
    "EVIDENCE_002": {
        "source_type": "github_issue",
        "source_id": "65797",
        "url": "https://github.com/org/repo/issues/65797",
        "excerpt": "The regression was reverted in the parser in commit a3f9b12.",
    },
}


def _model(claim):
    return {"claims": [claim]}


def test_absent_evidence_id_is_false_pass():
    status, violations = citation_grounding.validate_claims(_model({
        "claim": "The scheduler fails.",
        "claim_type": "external_artifact",
        "evidence_ids": ["EVIDENCE_003"],
        "quote_spans": [],
    }), ARTIFACTS)
    assert status == "FALSE-PASS"
    assert any(v["code"] == "missing_evidence_id" for v in violations)


def test_raw_issue_number_in_claim_is_false_pass():
    status, violations = citation_grounding.validate_claims(_model({
        "claim": "Issue #65796 confirms the scheduler bug.",
        "claim_type": "external_artifact",
        "evidence_ids": ["EVIDENCE_001"],
        "quote_spans": [{"evidence_id": "EVIDENCE_001", "start": 0, "end": 7}],
    }), ARTIFACTS)
    assert status == "FALSE-PASS"
    assert any(v["code"] == "raw_citation_in_claim" for v in violations)


def test_raw_issue_number_without_hash_in_claim_is_false_pass():
    for raw_ref in [
        "Issue 65796",
        "Issue: 65796",
        "Issue-65796",
        "GH-65796",
        "ticket: 123",
        "PR-123",
        "pull request #123",
        "issue no. 65796",
        "issue number 65796",
        "pull-request 123",
        "GH 65796",
        "GitHub 65796",
        "JIRA-123",
        "CVE-2024-12345",
        "doc section 4",
        "document section 4",
        "section 4.2",
        "Section IV",
        "RFC 9110",
        "PEP 8",
        "ADR 123",
    ]:
        status, violations = citation_grounding.validate_claims(_model({
            "claim": "%s confirms the scheduler bug." % raw_ref,
            "claim_type": "external_artifact",
            "evidence_ids": ["EVIDENCE_001"],
            "quote_spans": [{"evidence_id": "EVIDENCE_001", "start": 0, "end": 7}],
        }), ARTIFACTS)
        assert status == "FALSE-PASS", raw_ref
        assert any(v["code"] == "raw_citation_in_claim" for v in violations), raw_ref


def test_generated_quote_field_is_false_pass():
    status, violations = citation_grounding.validate_claims(_model({
        "claim": "The scheduler fails.",
        "claim_type": "external_artifact",
        "evidence_ids": ["EVIDENCE_001"],
        "quote_spans": [],
        "quote": "resumeFromRunId silently restarts from scratch",
    }), ARTIFACTS)
    assert status == "FALSE-PASS"
    assert any(v["code"] == "generated_quote_field" for v in violations)


def test_out_of_bounds_span_is_false_pass():
    excerpt_len = len(ARTIFACTS["EVIDENCE_001"]["excerpt"])
    status, violations = citation_grounding.validate_claims(_model({
        "claim": "The scheduler fails.",
        "claim_type": "external_artifact",
        "evidence_ids": ["EVIDENCE_001"],
        "quote_spans": [{"evidence_id": "EVIDENCE_001", "start": 0, "end": excerpt_len + 1}],
    }), ARTIFACTS)
    assert status == "FALSE-PASS"
    assert any(v["code"] == "span_out_of_bounds" for v in violations)


def test_span_source_must_be_cited_by_claim():
    status, violations = citation_grounding.validate_claims(_model({
        "claim": "The scheduler fails.",
        "claim_type": "external_artifact",
        "evidence_ids": ["EVIDENCE_001"],
        "quote_spans": [{"evidence_id": "EVIDENCE_002", "start": 0, "end": 14}],
    }), ARTIFACTS)
    assert status == "FALSE-PASS"
    assert any(v["code"] == "span_evidence_not_cited" for v in violations)


def test_external_authority_without_evidence_is_false_pass():
    status, violations = citation_grounding.validate_claims(_model({
        "claim": "Per the company's published compensation framework, this band is standard.",
        "claim_type": "external_authority",
        "evidence_ids": [],
        "quote_spans": [],
    }), ARTIFACTS)
    assert status == "FALSE-PASS"
    assert {v["code"] for v in violations} >= {
        "missing_required_evidence", "unsupported_authority"
    }


def test_analysis_with_authority_language_without_evidence_is_false_pass():
    status, violations = citation_grounding.validate_claims(_model({
        "claim": "According to the industry standard, this is common.",
        "claim_type": "analysis",
        "evidence_ids": [],
        "quote_spans": [],
    }), ARTIFACTS)
    assert status == "FALSE-PASS"
    assert any(v["code"] == "unsupported_authority" for v in violations)


def test_valid_span_based_citation_passes_and_renders_from_artifact():
    claim = {
        "claim": "The scheduler issue was observed.",
        "claim_type": "external_artifact",
        "evidence_ids": ["EVIDENCE_001"],
        "quote_spans": [{"evidence_id": "EVIDENCE_001", "start": 4, "end": 7}],
    }
    status, violations = citation_grounding.validate_claims(_model(claim), ARTIFACTS)
    assert status == "PASS"
    assert violations == []

    report = citation_grounding.render_report([claim], ARTIFACTS)
    assert "The scheduler issue was observed." in report
    assert "'bug'" in report
    assert "source_id=65795" in report
    assert "resumeFromRunId" not in report


def test_unsupported_analysis_without_authority_language_passes():
    claim = {
        "claim": "This is a plausible implementation risk, but no retrieved source supports it.",
        "claim_type": "unsupported",
        "evidence_ids": [],
        "quote_spans": [],
    }
    status, violations = citation_grounding.validate_claims(_model(claim), ARTIFACTS)
    assert status == "PASS"
    assert violations == []
    assert citation_grounding.render_report([claim], ARTIFACTS).startswith("UNSUPPORTED: ")


def test_renderer_refuses_invalid_claims():
    with pytest.raises(ValueError):
        citation_grounding.render_report([{
            "claim": "Issue #65796 confirms this.",
            "claim_type": "external_artifact",
            "evidence_ids": ["EVIDENCE_003"],
            "quote_spans": [],
        }], ARTIFACTS)


def test_run_evals_scores_citation_grounding_trap_as_caught():
    case = {
        "id": "citation-trap",
        "target": "citation_grounding",
        "expected": "FALSE-PASS",
        "artifacts": ARTIFACTS,
        "model_output": _model({
            "claim": "Issue #65796 confirms this.",
            "claim_type": "external_artifact",
            "evidence_ids": ["EVIDENCE_003"],
            "quote_spans": [],
        }),
    }
    row = run_evals._score_case(case, harness=None, judge=None)
    assert row["verdict"] == "FALSE-PASS"
    assert row["bucket"] == "caught"


def test_run_evals_scores_citation_grounding_good_as_ok():
    case = {
        "id": "citation-good",
        "target": "citation_grounding",
        "expected": "PASS",
        "artifacts": ARTIFACTS,
        "model_output": _model({
            "claim": "The scheduler issue was observed.",
            "claim_type": "external_artifact",
            "evidence_ids": ["EVIDENCE_001"],
            "quote_spans": [{"evidence_id": "EVIDENCE_001", "start": 0, "end": 7}],
        }),
    }
    row = run_evals._score_case(case, harness=None, judge=None)
    assert row["verdict"] == "PASS"
    assert row["bucket"] == "ok"
