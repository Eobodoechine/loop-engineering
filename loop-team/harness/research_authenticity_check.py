#!/usr/bin/env python3
"""Loop Team — research-output authenticity check (closes H-DEGENERATE-OUTPUT-1).

Deterministic, mechanical scan of a SAVED Researcher-dispatch markdown file, run
by Oga IMMEDIATELY after any Researcher dispatch returns, BEFORE its findings are
trusted, synthesized, or acted on. This is the structural fix for the real
incident in `fix_plan.md` (`H-DEGENERATE-OUTPUT-1`): 2 of 6 parallel research
dispatches returned literal placeholder content (`claim="test"`,
`source="test"`, `verdict="test"` for every field) that validated CLEANLY
against a required-field JSON schema, because the schema checks TYPE, not
SUBSTANCE. No LLM judgment is used here — the whole point is a check that does
not depend on another model's self-report, since that is exactly the layer
that already failed once.

Handles all 4 of `roles/researcher.md`'s "You produce" field vocabularies:
  Mode A: name, source, maturity, claim, where_it_wires_in, triage, priority,
          risks, experiment
  Mode B: diagnosis, candidate_fixes (list, each item has its own source),
          falsifiable_check, if_not_found
  Mode C: id, target, expected, artifact, failure_mode, why_hard, objective_fact
  Mode D: question, answer, source, code_pattern, constraints, not_found

Plus a 5th genre, Mode E (Evidence-Gate Phase 5, Item 4): a `Proof:` block's
own isolated span (the same `command`/`exit_code`/`proof_snapshot`/
`verified_at`/`files` field shape `fixplan_closure_lint.py` parses out of a
CLOSED fix_plan.md heading). This lets rules 1-3 (placeholder tokens,
identical-value-across-fields, suspiciously-short fields) apply to a Proof
block's own fields for free, reusing this same scanner -- catching, e.g., a
fabricated Proof block whose `command` and `proof_snapshot` are both the
literal string "test". Mode E cites a snapshot file path, not a URL, so
rule 4 (missing source URL) does not apply to it.

Detection rules (deterministic, mode-aware — see spec for full rationale):
  1. Literal placeholder token match — a field's FULL stripped value (not a
     mid-sentence occurrence) is one of a configurable denylist.
  2. Identical-value-across-distinct-fields — an EXPLICIT, per-mode field list
     (not an open-ended "any 2 fields" scan): Mode A compares
     claim/where_it_wires_in/risks; Mode B compares diagnosis/if_not_found
     (candidate_fixes handled separately); Mode C compares
     why_hard/objective_fact/failure_mode; Mode D compares
     question/answer/not_found (dropping not_found when empty/absent); Mode E
     compares command/proof_snapshot.
  3. Suspiciously-short substantive field — under a configurable minimum length
     (default 15 chars).
  4. Missing real source URL where a top-level `source` field exists — Mode A
     and Mode D only (each has a top-level `source`); Mode B has no top-level
     `source` but applies this per `candidate_fixes[].source` item instead;
     Mode C has no `source` field at all and rule 4 is skipped entirely for it;
     Mode E cites a snapshot path rather than a URL and rule 4 is skipped for
     it too.

Output: a JSON verdict on stdout, matching `live_smoke.py`'s convention of a
machine-readable result Oga parses:
    {"passed": bool, "flagged": [{"block_id", "reason", "field",
     "value_excerpt"}, ...], "file": "<path>"}
`passed` is False if ANY block in the file is flagged.

Exit codes (matching `verify.py`'s force-fail convention for a clean
machine-readable signal): 0 if passed, 1 if `passed: false`, 2 on usage error.

Usage:
    python3 research_authenticity_check.py <saved_file_path>
"""
import json
import re
import sys

# --- Rule 1: literal placeholder denylist -----------------------------------
# Case-insensitive; matches only the ENTIRE stripped value of a field (not a
# mid-sentence occurrence — "we ran a test suite" must NOT trigger).
DENYLIST_TOKENS = {
    "test", "todo", "tbd", "n/a", "na", "placeholder", "lorem ipsum", "xxx",
    "foo", "bar", "sample", "example", "unknown",
}

# The subset of DENYLIST_TOKENS that represents a legitimate "not applicable"
# answer, as opposed to a lazy/placeholder token. Only this subset is
# exempted for MODE_OPTIONAL_FIELDS fields -- "test"/"todo"/"lorem ipsum"/etc.
# remain flagged everywhere, including optional fields, since nobody
# legitimately writes those to mean "not applicable."
ABSENCE_TOKENS = {"n/a", "na"}

# Rule 3: default minimum length (characters) for a substantive free-text field.
MIN_SUBSTANTIVE_LENGTH = 15

# Rule 4: what counts as "contains a real URL".
URL_RE = re.compile(r"https?://", re.IGNORECASE)

# Per-mode field vocabularies (from roles/researcher.md's "You produce"
# sections) used to detect which mode a block belongs to.
MODE_FIELDS = {
    "A": {"name", "source", "maturity", "claim", "where_it_wires_in", "triage",
          "priority", "risks", "experiment"},
    "B": {"diagnosis", "candidate_fixes", "falsifiable_check", "if_not_found"},
    "C": {"id", "target", "expected", "artifact", "failure_mode", "why_hard",
          "objective_fact"},
    "D": {"question", "answer", "source", "code_pattern", "constraints",
          "not_found"},
    # Mode E: a fix_plan.md `Proof:` block's own isolated span (Evidence-Gate
    # Phase 5, Item 4) -- not a Researcher-dispatch mode, but the same
    # generic parse_blocks()/detect_mode()/check_block() pipeline applies to
    # it once isolated (matching how fixplan_closure_lint.py already hands
    # a Proof: span to parse_blocks).
    "E": {"command", "exit_code", "proof_snapshot", "verified_at", "files"},
}

# Rule 2's EXPLICIT per-mode field-pair list (not an open-ended scan).
MODE_RULE2_FIELDS = {
    "A": ["claim", "where_it_wires_in", "risks"],
    "B": ["diagnosis", "if_not_found"],
    "C": ["why_hard", "objective_fact", "failure_mode"],
    "D": ["question", "answer", "not_found"],
    "E": ["command", "proof_snapshot"],
}

# Rule 4's per-mode top-level source-field applicability.
# "top" = a single top-level `source` field to check directly.
# "none" = no source field at all (Mode C) -> rule 4 skipped entirely.
# "list" = no top-level source; check each candidate_fixes[].source (Mode B).
# Mode E: a Proof block cites a snapshot path, not a URL -- rule 4 does not
# apply to it either ("none", same skip as Mode C).
MODE_RULE4_KIND = {"A": "top", "B": "list", "C": "none", "D": "top", "E": "none"}

# Fields expected to carry substantive free prose, checked by rule 3 (length).
# candidate_fixes' own `fix` text and each item's `source` are handled
# separately (source goes through rule 4 only, not rule 3 — a URL is
# legitimately short).
MODE_SUBSTANTIVE_FIELDS = {
    "A": ["claim", "where_it_wires_in", "risks"],
    "B": ["diagnosis", "if_not_found"],
    "C": ["why_hard", "objective_fact", "failure_mode"],
    "D": ["question", "answer"],
    "E": ["command", "proof_snapshot"],
}

# Fields the role brief marks as conditionally optional (roles/researcher.md), where a
# genuine "n/a"/"na" is a legitimate value, not a sign of degenerate output. Rule 1 still
# flags every OTHER denylist token (test, todo, placeholder, etc.) in these fields --
# only the specific "not applicable" tokens are exempted here.
MODE_OPTIONAL_FIELDS = {
    "D": ["code_pattern", "constraints"],
}

BLOCK_HEADER_RE = re.compile(r"^##\s+(.*)$")
# A field line: "- field_name: value" (optionally indented, as in
# candidate_fixes sub-items which use extra leading spaces).
FIELD_LINE_RE = re.compile(r"^\s*-\s*([A-Za-z0-9_]+)\s*:\s*(.*)$")
# A candidate_fixes list item's own nested source line: "source: value"
# (no leading "-", indented under a "- fix N: ..." line).
NESTED_SOURCE_RE = re.compile(r"^\s+source\s*:\s*(.*)$")


def _strip(value):
    return (value or "").strip()


def parse_blocks(text):
    """Split the markdown file into candidate/finding blocks (each starting at
    a top-level `## ...` header) and parse each block's `- field: value` lines
    into a dict. Also parses a `candidate_fixes` sub-list (Mode B) into a list
    of {"fix": ..., "source": ...} dicts keyed under "candidate_fixes".

    Schema-agnostic parsing: field NAMES come straight from whatever the file
    contains, so this same parser works across all 4 modes without mode-
    specific parsing branches — mode is only used later, to decide WHICH
    detection rules apply to which fields.
    """
    lines = text.splitlines()
    blocks = []
    current = None
    current_id = None
    in_candidate_fixes = False
    pending_fix_index = None

    def start_block(block_id):
        return {"_id": block_id, "_fields": {}, "candidate_fixes": []}

    for raw_line in lines:
        header_m = BLOCK_HEADER_RE.match(raw_line)
        if header_m:
            if current is not None:
                blocks.append(current)
            current_id = header_m.group(1).strip()
            current = start_block(current_id)
            in_candidate_fixes = False
            continue

        if current is None:
            # Content before the first header: treat as an implicit block so
            # single-block fixtures with no "## ..." header still parse.
            current_id = "block-1"
            current = start_block(current_id)

        # candidate_fixes list header line itself ("- candidate_fixes:")
        m = FIELD_LINE_RE.match(raw_line)
        if m and m.group(1) == "candidate_fixes":
            in_candidate_fixes = True
            continue

        if in_candidate_fixes:
            fix_item_m = re.match(r"^\s*-\s*fix\s*\d*\s*:\s*(.*)$", raw_line, re.IGNORECASE)
            if fix_item_m:
                current["candidate_fixes"].append(
                    {"fix": fix_item_m.group(1).strip(), "source": ""}
                )
                pending_fix_index = len(current["candidate_fixes"]) - 1
                continue
            src_m = NESTED_SOURCE_RE.match(raw_line)
            if src_m and pending_fix_index is not None:
                current["candidate_fixes"][pending_fix_index]["source"] = src_m.group(1).strip()
                continue
            # Any other field line ends the candidate_fixes list.
            if m:
                in_candidate_fixes = False
            elif raw_line.strip() == "":
                continue
            else:
                continue

        if m:
            field, value = m.group(1), m.group(2).strip()
            current["_fields"][field] = value

    if current is not None:
        blocks.append(current)

    return blocks


def detect_mode(fields):
    """Pick the mode whose field vocabulary best matches this block's fields.

    Schema-agnostic-enough design: rather than hard-branch on parsing per
    mode, we parse generically (parse_blocks) then classify AFTER the fact by
    scoring overlap with each mode's known field set. Ties are broken by a
    fixed precedence (A, B, C, D) since real dossiers always include enough
    mode-distinguishing fields (e.g. Mode B's `candidate_fixes`/`diagnosis`,
    Mode C's `why_hard`/`objective_fact`, Mode D's `not_found` alongside
    `question`/`answer`) that a tie in practice does not occur.

    Mode B and Mode E are both special-cased FIRST, ahead of the generic
    overlap-scoring loop (in that order: B, then E) — a fix_plan.md Proof:
    block's own vocabulary (command/exit_code/proof_snapshot/verified_at/
    files) is unrelated to any Researcher-dispatch mode, so it is detected
    explicitly on the co-presence of proof_snapshot + verified_at rather than
    left to the generic scorer.
    """
    present = set(fields.keys())
    if "candidate_fixes" in fields or {"diagnosis", "if_not_found"} & present:
        return "B"
    # Mode E special case (mirrors B's precedent above): a fix_plan.md Proof:
    # block's own isolated span is keyed on the co-presence of
    # proof_snapshot + verified_at -- a combination no other genre's
    # vocabulary contains. An explicit early branch (not the generic
    # overlap-scoring loop below) is used because command/exit_code could in
    # principle partially overlap with a hypothetical future genre.
    if {"proof_snapshot", "verified_at"} <= present:
        return "E"
    best_mode, best_score = None, -1
    for mode, vocab in MODE_FIELDS.items():
        score = len(present & vocab)
        if score > best_score:
            best_mode, best_score = mode, score
    return best_mode or "A"


def _normalize(value):
    """Shared normalization used by both _is_denylisted and the ABSENCE_TOKENS
    check: strip, drop punctuation, lowercase."""
    stripped = _strip(value)
    return re.sub(r"[^\w\s]", "", stripped).strip().lower()


def _is_denylisted(value):
    return _normalize(value) in DENYLIST_TOKENS


def _is_absence_token(value):
    """True if value's normalized form (same normalization as _is_denylisted)
    is one of ABSENCE_TOKENS (a legitimate "not applicable" answer)."""
    return _normalize(value) in ABSENCE_TOKENS


def _excerpt(value, length=60):
    v = _strip(value)
    return v if len(v) <= length else v[:length] + "..."


def check_block(block):
    """Apply rules 1-4 to a single parsed block. Returns a list of flag dicts:
    {"block_id", "reason", "field", "value_excerpt"}.
    """
    fields = block["_fields"]
    block_id = block["_id"]
    mode = detect_mode(fields)
    flags = []

    # --- Rule 1: literal placeholder token (any field with real content) ---
    # Apply to every present, non-empty field whose value we can meaningfully
    # judge -- not just the rule-2/rule-3 lists -- since a placeholder can land
    # in any field (the real incident hit claim/source/verdict alike).
    optional_fields = MODE_OPTIONAL_FIELDS.get(mode, [])
    for field, value in fields.items():
        if field == "priority":
            continue  # numeric/score field, not prose -- skip placeholder scan
        if not _strip(value):
            continue
        if field in optional_fields and _is_absence_token(value):
            continue  # legitimate "not applicable" in a conditionally optional field
        if _is_denylisted(value):
            flags.append({
                "block_id": block_id,
                "reason": f"literal denylist/placeholder token match ('{_strip(value)}')",
                "field": field,
                "value_excerpt": _excerpt(value),
            })
    for i, cf in enumerate(block.get("candidate_fixes", [])):
        fix_val = cf.get("fix", "")
        if fix_val and _is_denylisted(fix_val):
            flags.append({
                "block_id": block_id,
                "reason": f"literal denylist/placeholder token match ('{_strip(fix_val)}')",
                "field": f"candidate_fixes[{i}].fix",
                "value_excerpt": _excerpt(fix_val),
            })

    # --- Rule 2: identical-value-across-distinct-fields (explicit per mode) -
    rule2_fields = MODE_RULE2_FIELDS.get(mode, [])
    seen_values = {}
    for field in rule2_fields:
        value = fields.get(field)
        if value is None:
            continue
        stripped = _strip(value)
        if not stripped:
            continue
        seen_values.setdefault(stripped, []).append(field)
    for value, matching_fields in seen_values.items():
        if len(matching_fields) >= 2:
            flags.append({
                "block_id": block_id,
                "reason": (
                    "identical value across distinct fields: "
                    f"{', '.join(matching_fields)} all share the same value"
                ),
                "field": "+".join(matching_fields),
                "value_excerpt": _excerpt(value),
            })

    # --- Rule 3: suspiciously-short substantive field -----------------------
    for field in MODE_SUBSTANTIVE_FIELDS.get(mode, []):
        value = fields.get(field)
        if value is None:
            continue
        stripped = _strip(value)
        if not stripped:
            continue
        if _is_denylisted(stripped):
            continue  # already caught (and explained) by rule 1
        if len(stripped) < MIN_SUBSTANTIVE_LENGTH:
            flags.append({
                "block_id": block_id,
                "reason": (
                    f"suspiciously short field: {len(stripped)} chars, "
                    f"minimum is {MIN_SUBSTANTIVE_LENGTH}"
                ),
                "field": field,
                "value_excerpt": _excerpt(value),
            })

    # --- Rule 4: missing real source URL (mode-specific) --------------------
    kind = MODE_RULE4_KIND.get(mode, "none")
    if kind == "top":
        source_value = fields.get("source")
        if source_value is not None and _strip(source_value):
            if not URL_RE.search(source_value):
                flags.append({
                    "block_id": block_id,
                    "reason": "source field present but contains no http(s) URL",
                    "field": "source",
                    "value_excerpt": _excerpt(source_value),
                })
    elif kind == "list":
        for i, cf in enumerate(block.get("candidate_fixes", [])):
            source_value = cf.get("source", "")
            if _strip(source_value) and not URL_RE.search(source_value):
                flags.append({
                    "block_id": block_id,
                    "reason": (
                        f"candidate_fixes[{i}].source present but contains "
                        "no http(s) URL"
                    ),
                    "field": f"candidate_fixes[{i}].source",
                    "value_excerpt": _excerpt(source_value),
                })
    # kind == "none" (Mode C): rule 4 is skipped entirely -- no source field
    # exists for this mode, so there is nothing to check.

    return flags


def analyze(text):
    """Parse the file text into blocks and run all rules over each. Returns
    the list of all flags found across the whole file. Pure; unit-testable
    independent of the CLI/file-IO layer.
    """
    blocks = parse_blocks(text)
    flagged = []
    for block in blocks:
        flagged.extend(check_block(block))
    return flagged


def main(argv):
    args = argv[1:]
    if len(args) != 1:
        print(json.dumps({"error": "usage: research_authenticity_check.py <saved_file_path>"}))
        return 2

    path = args[0]
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        print(json.dumps({"error": f"could not read file: {e}", "file": path}))
        return 2

    flagged = analyze(text)
    verdict = {
        "passed": len(flagged) == 0,
        "flagged": flagged,
        "file": path,
    }
    print(json.dumps(verdict, indent=2))
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
