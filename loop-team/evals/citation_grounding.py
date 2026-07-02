"""Deterministic citation-grounding gate.

This lane enforces citation authority as a code capability:

- retrieved artifacts own source IDs, URLs, and excerpts
- model output may reference artifact keys and quote spans
- code validates keys/spans/authority markers
- code renders quotes from excerpts

It intentionally does NOT decide whether an exact quote is persuasive support for
the claim. That later support/relevance check belongs in a separate lane.
"""

import re


_AUTHORITY_MARKERS = re.compile(
    r"\b(according to|per(?:\s+the)?|published framework|market data shows|"
    r"industry standard)\b",
    re.IGNORECASE,
)
_RAW_CITATION = re.compile(
    r"(#\d+|"
    r"\b(?:issue|issues|bug|ticket|pr|pull(?:\s|-)?request|pull|gh|github|jira|"
    r"doc(?:ument)?|section|changelog)\s*(?:no\.?|number|num|id|[#:-])?\s*"
    r"[A-Z]{0,12}-?\d{2,}(?:-\d{2,})?\b|"
    r"\b(?:doc(?:ument)?\s+)?section\s+(?:[ivxlcdm]+|\d+(?:\.\d+)*)\b|"
    r"\b(?:RFC|PEP|ADR)\s*-?\s*\d+\b|"
    r"\b(?:GH|JIRA|CVE)-\d{2,}(?:-\d{2,})?\b|"
    r"https?://\S+|\barxiv:\s*\d{4}\.\d{4,5}\b|\b\d{4}\.\d{4,5}\b|"
    r"\bEVIDENCE_\d{3,}\b)",
    re.IGNORECASE,
)
_FORBIDDEN_QUOTE_FIELDS = ("quote", "quotes", "quote_text", "quoted_text")
_EVIDENCE_REQUIRED_TYPES = ("external_artifact", "external_authority")
_KNOWN_CLAIM_TYPES = ("external_artifact", "external_authority", "analysis", "unsupported")


def _violation(code, path, claim="", detail=""):
    return {"code": code, "path": path, "claim": claim, "detail": detail}


def _claim_text(claim):
    return claim.get("claim", "") if isinstance(claim, dict) else ""


def validate_claims(model_output, artifacts):
    """Validate model-authored claim records against retrieved artifacts.

    Returns:
        ("PASS", []) when every citation/authority check is mechanically valid.
        ("FALSE-PASS", [violation, ...]) when the output contains fabricated or
        unsupported citation authority.
    """
    violations = []

    if not isinstance(artifacts, dict):
        return ("FALSE-PASS", [_violation(
            "schema_error", "$.artifacts", detail="artifacts must be a dict"
        )])

    if not isinstance(model_output, dict) or not isinstance(model_output.get("claims"), list):
        return ("FALSE-PASS", [_violation(
            "schema_error", "$", detail="model_output must be a dict with a claims list"
        )])

    for i, claim in enumerate(model_output["claims"]):
        path = "$.claims[%d]" % i
        if not isinstance(claim, dict):
            violations.append(_violation(
                "schema_error", path, detail="claim entry must be a dict"
            ))
            continue

        claim_text = claim.get("claim", "")
        claim_type = claim.get("claim_type", "")
        evidence_ids = claim.get("evidence_ids", [])
        quote_spans = claim.get("quote_spans", [])

        if not isinstance(claim_text, str):
            violations.append(_violation(
                "schema_error", path + ".claim", detail="claim must be a string"
            ))
            claim_text = ""
        if claim_type not in _KNOWN_CLAIM_TYPES:
            violations.append(_violation(
                "schema_error", path + ".claim_type", claim_text,
                "claim_type must be one of %s" % ", ".join(_KNOWN_CLAIM_TYPES),
            ))
        if not isinstance(evidence_ids, list) or not all(isinstance(e, str) for e in evidence_ids):
            violations.append(_violation(
                "schema_error", path + ".evidence_ids", claim_text,
                "evidence_ids must be a list of strings",
            ))
            evidence_ids = []
        if not isinstance(quote_spans, list):
            violations.append(_violation(
                "schema_error", path + ".quote_spans", claim_text,
                "quote_spans must be a list",
            ))
            quote_spans = []

        for field in _FORBIDDEN_QUOTE_FIELDS:
            if field in claim:
                violations.append(_violation(
                    "generated_quote_field", path + "." + field, claim_text,
                    "model output must not contain generated quote text; use quote_spans",
                ))

        if claim_type in _EVIDENCE_REQUIRED_TYPES and not evidence_ids:
            violations.append(_violation(
                "missing_required_evidence", path + ".evidence_ids", claim_text,
                "%s claims require at least one evidence_id" % claim_type,
            ))

        for j, evidence_id in enumerate(evidence_ids):
            if evidence_id not in artifacts:
                violations.append(_violation(
                    "missing_evidence_id", "%s.evidence_ids[%d]" % (path, j), claim_text,
                    "%s is absent from artifacts" % evidence_id,
                ))

        raw_match = _RAW_CITATION.search(claim_text)
        if raw_match:
            violations.append(_violation(
                "raw_citation_in_claim", path + ".claim", claim_text,
                "model-authored claim text contains raw citation token %r" % raw_match.group(0),
            ))

        authority_match = _AUTHORITY_MARKERS.search(claim_text)
        if authority_match and not evidence_ids:
            violations.append(_violation(
                "unsupported_authority", path + ".claim", claim_text,
                "authority marker %r appears without evidence" % authority_match.group(0),
            ))

        cited = set(evidence_ids)
        for k, span in enumerate(quote_spans):
            span_path = "%s.quote_spans[%d]" % (path, k)
            if not isinstance(span, dict):
                violations.append(_violation(
                    "schema_error", span_path, claim_text, "quote span must be a dict"
                ))
                continue

            span_eid = span.get("evidence_id")
            start = span.get("start")
            end = span.get("end")
            if not isinstance(span_eid, str):
                violations.append(_violation(
                    "schema_error", span_path + ".evidence_id", claim_text,
                    "span evidence_id must be a string",
                ))
                continue
            if span_eid not in artifacts:
                violations.append(_violation(
                    "missing_span_evidence_id", span_path + ".evidence_id", claim_text,
                    "%s is absent from artifacts" % span_eid,
                ))
                continue
            if span_eid not in cited:
                violations.append(_violation(
                    "span_evidence_not_cited", span_path + ".evidence_id", claim_text,
                    "%s is used in quote_spans but not listed in evidence_ids" % span_eid,
                ))

            excerpt = artifacts.get(span_eid, {}).get("excerpt", "")
            if not isinstance(excerpt, str):
                violations.append(_violation(
                    "schema_error", "$.artifacts.%s.excerpt" % span_eid, claim_text,
                    "artifact excerpt must be a string",
                ))
                continue
            if not (isinstance(start, int) and isinstance(end, int)):
                violations.append(_violation(
                    "schema_error", span_path, claim_text,
                    "span start and end must be integers",
                ))
                continue
            if not (0 <= start < end <= len(excerpt)):
                violations.append(_violation(
                    "span_out_of_bounds", span_path, claim_text,
                    "span [%s:%s] is out of bounds for excerpt length %d"
                    % (start, end, len(excerpt)),
                ))

    return ("PASS", []) if not violations else ("FALSE-PASS", violations)


def render_report(validated_claims, artifacts):
    """Render a final report from validated claims and artifact metadata.

    The rendered report prints source IDs/URLs and quote text only from the
    artifact dictionary. It never uses model-generated quote text.
    """
    status, violations = validate_claims({"claims": validated_claims}, artifacts)
    if status != "PASS":
        raise ValueError("cannot render invalid citation claims: %r" % violations)

    lines = []
    for claim in validated_claims:
        prefix = "UNSUPPORTED: " if claim.get("claim_type") == "unsupported" else ""
        lines.append(prefix + claim["claim"])
        for span in claim.get("quote_spans", []):
            evidence = artifacts[span["evidence_id"]]
            quote = evidence["excerpt"][span["start"]:span["end"]]
            source_bits = [span["evidence_id"]]
            if evidence.get("source_id"):
                source_bits.append("source_id=%s" % evidence["source_id"])
            if evidence.get("url"):
                source_bits.append("url=%s" % evidence["url"])
            lines.append("  [%s] %r" % (", ".join(source_bits), quote))
    return "\n".join(lines)


def check_case(case):
    """run_evals adapter for target: citation_grounding."""
    status, violations = validate_claims(case.get("model_output"), case.get("artifacts"))
    detail = "; ".join("%s at %s" % (v["code"], v["path"]) for v in violations)
    return {"verdict": status, "summary": detail}
