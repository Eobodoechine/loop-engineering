#!/usr/bin/env python3
"""Audit high-risk fix_plan.md status claims against mechanical evidence.

This is the v1 anti-false-status gate. It is intentionally narrower than a
general truth auditor: hook mode audits only touched claim/evidence units,
while manual full-sweep mode reports historical findings without blocking
unless --strict is requested.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone


HEADING_RE = re.compile(r"^## (.*)$", re.MULTILINE)
# A nested gate-hole sub-entry: an `### H-<id>...` line one level deeper than
# a normal `## ` section heading. Only lines that start with `H-` immediately
# after the `### ` prefix count -- this is the file's own real convention for
# a genuine status-claim-bearing entry (`## ` OR `### ` level), which
# discriminates it from a generic `### ` prose sub-header (a mid-entry
# narrative aside, a skill-name cluster heading, a "Worktree note", etc.)
# that is not an independent claim and must stay folded into its enclosing
# block. Verified directly against the live fix_plan.md (`grep -n "^### "`):
# matches all 13 real H-ID `###` lines there and none of the 10 prose ones.
SUBENTRY_RE = re.compile(r"^### (H-\S.*)$", re.MULTILINE)
PROOF_MARKER = "Proof:"
PROOF_FIELD_RE = re.compile(r"^\s*-\s*([A-Za-z0-9_]+)\s*:\s*(.*)$")
STALE_EVIDENCE_MAX_AGE_DAYS = 30

STATUS_TOKEN_RE = re.compile(
    r"\b("
    r"DONE|CLOSED|IMPLEMENTED|VERIFIED|PASS|READY(?!-)|LIVE_SMOKE_PASS|"
    r"STRUCTURAL|FIXED|BUILT|WIRED|SHIPPED|RESOLVED|COMPLETE|COMPLETED|"
    r"RE-CLOSED|REVERIFIED|RE-VERIFIED|GREEN|SUITE_GREEN"
    r")\b",
    re.IGNORECASE,
)
GREEN_PHRASE_RE = re.compile(
    r"\b(Suite:\s*GREEN|tests\s+passed|all\s+green|harness\s+is\s+green)\b",
    re.IGNORECASE,
)
SENTENCE_CLAIM_RE = re.compile(
    r"\b(implemented|fixed|wired|built|shipped|resolved)\s+"
    r"(?:in|into|for|to)\s+[`A-Za-z0-9_./:-]+",
    re.IGNORECASE,
)

PROBE_COMMAND_RE = re.compile(
    r"^\s*(?:true|pwd|date|echo(?:\s+.*)?|python3\s+\S*run_and_record\.py\s+--\s+true)\s*$",
    re.IGNORECASE,
)

BLOCKING_CLASSIFIERS = {
    "MISSING_PARSEABLE_EVIDENCE",
    "INCOMPLETE_EVIDENCE",
    "FABRICATED_EVIDENCE",
    "MISSING_PROOF_PROVENANCE",
    "PROBE_ONLY",
    "MISSING_LIVE_SMOKE",
    "MISSING_FORCED_ERROR_READBACK",
    "MISSING_INTERRUPT_RESUME_PROOF",
    "MISSING_FAILURE_RETRY_INVARIANT",
    "MISSING_DURABLE_READBACK_NEGATIVE_CONTROL",
    "MISSING_BROWSER_EVIDENCE",
    "STALE_EVIDENCE",
}


def _parse_ts(ts):
    if not ts:
        return None
    try:
        parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iter_blocks(content):
    """Yield one dict per real status-claim-bearing entry.

    Block boundaries come from BOTH `HEADING_RE` (`## ` section headings) AND
    `SUBENTRY_RE` (nested `### H-<id>` gate-hole sub-entries), merged and
    sorted by position -- so a `###`-nested H-ID entry becomes its own
    yielded block (with its own heading/body span) instead of folding into
    its enclosing `##` parent's body all the way through to the next `##`.
    Generic `### ` prose sub-headers do not match `SUBENTRY_RE` and so do not
    introduce a boundary; they stay inside whatever block already contains
    them, exactly as before this function recognized any `### ` line.
    """
    matches = sorted(
        list(HEADING_RE.finditer(content)) + list(SUBENTRY_RE.finditer(content)),
        key=lambda m: m.start(),
    )
    for i, m in enumerate(matches):
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        yield {
            "heading": m.group(1),
            "heading_start": m.start(),
            "heading_end": m.end(),
            "body_start": body_start,
            "body_end": body_end,
            "body": content[body_start:body_end],
        }


def _proof_span(block):
    body = block["body"]
    offset = 0
    lines = body.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if line.strip() != PROOF_MARKER:
            offset += len(line)
            continue
        start = block["body_start"] + offset
        end = start + len(line)
        fields = {}
        j = i + 1
        while j < len(lines):
            m = PROOF_FIELD_RE.match(lines[j])
            if not m:
                break
            fields[m.group(1)] = m.group(2).strip()
            end += len(lines[j])
            j += 1
        return {"start": start, "end": end, "fields": fields}
    return None


def _line_spans(content):
    spans = []
    pos = 0
    for line in content.splitlines(keepends=True):
        spans.append((pos, pos + len(line), line))
        pos += len(line)
    if not content.endswith("\n"):
        return spans
    return spans


def _excluded_line(line, in_code):
    stripped = line.strip()
    if stripped.startswith("```"):
        return True, not in_code
    if in_code:
        return True, in_code
    low = stripped.lower()
    if stripped.startswith(">"):
        return True, in_code
    prefixes = (
        "historical note:",
        "example:",
        "counterexample:",
        "do not claim:",
    )
    if low.startswith(prefixes):
        return True, in_code
    return False, in_code


def _claim_spans(content, block):
    spans = []
    in_code = False
    for start, end, line in _line_spans(content[block["heading_start"]:block["body_end"]]):
        abs_start = block["heading_start"] + start
        excluded, in_code = _excluded_line(line, in_code)
        if excluded:
            continue
        for pattern in (GREEN_PHRASE_RE, SENTENCE_CLAIM_RE, STATUS_TOKEN_RE):
            for m in pattern.finditer(line):
                spans.append({
                    "start": abs_start + m.start(),
                    "end": abs_start + m.end(),
                    "claim": m.group(0),
                    "line": line.strip(),
                    "line_start": abs_start,
                    "line_end": abs_start + len(line),
                })
    return spans


def _ranges_overlap(a_start, a_end, b_start, b_end):
    return a_start < b_end and a_end > b_start


def _block_armed(block, claims, proof, touched_ranges, full_sweep):
    if full_sweep or touched_ranges is None:
        return bool(claims)
    if not touched_ranges:
        return False
    for tr in touched_ranges:
        try:
            ts, te = int(tr.get("start", 0)), int(tr.get("end", 0))
        except Exception:
            continue
        if te < ts:
            ts, te = te, ts
        if te == ts:
            te += 1
        if not _ranges_overlap(ts, te, block["heading_start"], block["body_end"]):
            continue
        for c in claims:
            if _ranges_overlap(ts, te, c["start"], c["end"]):
                return True
            # A touch anywhere on the same line as a claim revalidates that
            # claim; tests intentionally touch "Logging" while the risky
            # token is later in the same sentence.
            if _ranges_overlap(ts, te, c.get("line_start", c["start"]), c.get("line_end", c["end"])):
                return True
        if proof and _ranges_overlap(ts, te, proof["start"], proof["end"]):
            return True
        if tr.get("block") or tr.get("tool") == "Write":
            return True
        # Fallback: if the touched text sits anywhere in the block, audit the
        # block. Hook callers use this for proof deletion, where the old Proof
        # span no longer exists in post-edit content.
        return True
    return False


def _claim_context(block, claims):
    body = block["body"]
    proof = _proof_span(block)
    if proof:
        proof_start = max(0, proof["start"] - block["body_start"])
        proof_end = max(proof_start, proof["end"] - block["body_start"])
        body = body[:proof_start] + body[proof_end:]
    parts = [block["heading"], body]
    for c in claims:
        parts.append(c.get("line", ""))
        parts.append(c.get("claim", ""))
    return " ".join(parts).lower()


def _normalize_command(value):
    if isinstance(value, list):
        return " ".join(str(x) for x in value)
    return str(value or "")


def _load_snapshot(fields):
    path = fields.get("proof_snapshot") or fields.get("snapshot_path") or ""
    if not path:
        return None, "INCOMPLETE_EVIDENCE"
    if not os.path.isfile(path):
        return None, "FABRICATED_EVIDENCE"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, ValueError):
        return None, "FABRICATED_EVIDENCE"


def _validate_proof_fields(fields):
    required = ["command", "exit_code"]
    for name in required:
        if not fields.get(name):
            return "INCOMPLETE_EVIDENCE"
    current_schema = bool(fields.get("proof_snapshot"))
    if not (fields.get("proof_snapshot") or fields.get("snapshot_path")):
        return "INCOMPLETE_EVIDENCE"
    if not (fields.get("verified_at") or fields.get("captured_at")):
        return "INCOMPLETE_EVIDENCE"
    if current_schema:
        for name in ("proof_schema_version", "proof_producer", "proof_key_algorithm", "output_sha256"):
            if not fields.get(name):
                return "MISSING_PROOF_PROVENANCE"
    for optional in ("output_sha256", "stdout_sha256", "captured_at"):
        if optional in fields and not fields.get(optional):
            return "INCOMPLETE_EVIDENCE"
    return None


def _expected_snapshot_basename(record):
    try:
        key_material = {
            "command": record["command"],
            "exit_code": record["exit_code"],
            "output_sha256": record["output_sha256"],
            "files": record["files"],
            "dirty_at_capture": record["dirty_at_capture"],
        }
    except KeyError:
        return None
    serialized = json.dumps(key_material, sort_keys=True)
    return "%s.json" % hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _validate_current_provenance(fields, record):
    """Validate the current run_and_record proof schema.

    Legacy `snapshot_path` / `stdout_sha256` proofs intentionally bypass this
    stricter path; current-schema `proof_snapshot` records must prove they came
    from the harness convention, not just a hand-named arbitrary JSON blob.
    """
    if not fields.get("proof_snapshot"):
        return None
    if str(fields.get("proof_schema_version")) != str(record.get("proof_schema_version")):
        return "MISSING_PROOF_PROVENANCE"
    if fields.get("proof_producer") != record.get("proof_producer"):
        return "MISSING_PROOF_PROVENANCE"
    if fields.get("proof_key_algorithm") != record.get("proof_key_algorithm"):
        return "MISSING_PROOF_PROVENANCE"
    if record.get("proof_producer") != "loop-team/harness/run_and_record.py":
        return "MISSING_PROOF_PROVENANCE"
    if str(record.get("proof_schema_version")) != "1":
        return "MISSING_PROOF_PROVENANCE"
    if record.get("proof_key_algorithm") != "run_and_record.v1":
        return "MISSING_PROOF_PROVENANCE"

    path = fields.get("proof_snapshot") or ""
    expected = _expected_snapshot_basename(record)
    if not expected:
        return "MISSING_PROOF_PROVENANCE"
    if os.path.basename(path) != expected:
        return "FABRICATED_EVIDENCE"
    if os.path.basename(os.path.dirname(path)) != "proof":
        return "FABRICATED_EVIDENCE"
    return None


def _snapshot_matches(fields, record):
    claimed_command = fields.get("command", "")
    recorded_command = _normalize_command(record.get("command"))
    if claimed_command != recorded_command:
        return False
    if str(fields.get("exit_code", "")) != str(record.get("exit_code")):
        return False
    claimed_hash = fields.get("output_sha256") or fields.get("stdout_sha256")
    if claimed_hash:
        rec_hash = record.get("output_sha256") or record.get("stdout_sha256")
        if claimed_hash != rec_hash:
            return False
    return True


def _mechanical_text(command, record):
    output = record.get("output", "")
    if not isinstance(output, str):
        output = json.dumps(output, sort_keys=True)
    return ("%s\n%s" % (command, output)).lower()


def _record_output_text(record):
    output = record.get("output", "")
    if not isinstance(output, str):
        output = json.dumps(output, sort_keys=True)
    return output.lower()


def _mentions_browser_context(context):
    return bool(
        re.search(r"\bui\b", context)
        or "browser" in context
        or "playwright" in context
    )


def _mentions_readiness_claim(context):
    return bool("live_smoke_pass" in context or re.search(r"\bready\b(?!-)", context))


def _evidence_timestamps(fields, record):
    stamps = []
    for source in (fields, record):
        for key in ("captured_at", "verified_at", "timestamp"):
            if source.get(key):
                parsed = _parse_ts(source.get(key))
                if parsed is None:
                    return None
                stamps.append(parsed)
    return stamps


def _classify_freshness(fields, record, now):
    parsed_now = _parse_ts(now) if now else None
    if parsed_now is None:
        parsed_now = datetime.now(timezone.utc)
    stamps = _evidence_timestamps(fields, record)
    if stamps is None or not stamps:
        return "INCOMPLETE_EVIDENCE"
    max_age = STALE_EVIDENCE_MAX_AGE_DAYS * 24 * 60 * 60
    if any((parsed_now - stamp).total_seconds() > max_age for stamp in stamps):
        return "STALE_EVIDENCE"
    return None


def _classify_relevance(context, command, record):
    text = _mechanical_text(command, record)
    output_text = _record_output_text(record)
    cmd_low = command.lower()
    if PROBE_COMMAND_RE.match(command):
        return "PROBE_ONLY"
    if _mentions_readiness_claim(context):
        if "live_smoke" not in text and "live-smoke" not in text:
            return "MISSING_LIVE_SMOKE"
    if "logging" in context or "log " in context or "logger" in context:
        negative_path = "forced" in output_text or "error" in output_text or "negative path" in output_text
        durable_readback = (
            "read back" in output_text
            or "readback" in output_text
            or "retrieved" in output_text
            or "retrieval" in output_text
            or re.search(r"\bread\s+from\s+(?:durable|log|ledger|destination|store|file|database|db|disk|sink)\b", output_text)
        )
        if not (negative_path and durable_readback):
            return "MISSING_FORCED_ERROR_READBACK"
    if "checkpoint" in context:
        if not (("checkpoint" in text) and ("resume" in text or "restart" in text or "interrupt" in text)):
            return "MISSING_INTERRUPT_RESUME_PROOF"
    if "retry" in context or "idempot" in context:
        if not (("fail" in text or "duplicate" in text) and ("retry" in text or "invariant" in text or "idempot" in text or "suppress" in text)):
            return "MISSING_FAILURE_RETRY_INVARIANT"
    if "persistence" in context or "persist" in context or re.search(r"\bdurable\s+ledger\b", context):
        if not (("write" in text or "persist" in text) and ("read back" in text or "readback" in text) and ("negative control" in text or "negative" in text)):
            return "MISSING_DURABLE_READBACK_NEGATIVE_CONTROL"
    if _mentions_browser_context(context):
        if not ("playwright" in text or "browser" in text or "screenshot" in text or "chromium" in text):
            return "MISSING_BROWSER_EVIDENCE"
    if "curl" in cmd_low and re.search(r"\b200\b", text) and _mentions_browser_context(context):
        return "MISSING_BROWSER_EVIDENCE"
    if not (
        "pytest" in cmd_low
        or "vitest" in cmd_low
        or "npm run test" in cmd_low
        or "live_smoke" in cmd_low
        or "live-smoke" in cmd_low
        or "playwright" in cmd_low
        or "test_" in cmd_low
        or "forced" in text
        or "checkpoint" in text
        or "duplicate" in text
        or "read back" in text
    ):
        return "PROBE_ONLY"
    return None


def _classify_block(content, block, claims, proof, now=None):
    if not proof:
        # Instructional prose can mention a risky word without asserting done.
        ctx = _claim_context(block, claims)
        if "future" in ctx or "guidance" in ctx or "require evidence" in ctx:
            return "PROSE_ONLY"
        return "MISSING_PARSEABLE_EVIDENCE"
    fields = proof["fields"]
    incomplete = _validate_proof_fields(fields)
    if incomplete:
        return incomplete
    record, err = _load_snapshot(fields)
    if err:
        return err
    provenance = _validate_current_provenance(fields, record)
    if provenance:
        return provenance
    if not _snapshot_matches(fields, record):
        return "FABRICATED_EVIDENCE"
    if str(record.get("exit_code")) != "0":
        return "INCOMPLETE_EVIDENCE"
    stale = _classify_freshness(fields, record, now)
    if stale:
        return stale
    command = fields.get("command", "")
    return _classify_relevance(_claim_context(block, claims), command, record)


def audit_fix_plan_content(content, touched_ranges=None, now=None, full_sweep=False):
    """Return a JSON-serializable audit result for fix_plan.md content."""
    findings = []
    for block in _iter_blocks(content):
        claims = _claim_spans(content, block)
        if not claims:
            continue
        proof = _proof_span(block)
        if not _block_armed(block, claims, proof, touched_ranges, full_sweep):
            continue
        classifier = _classify_block(content, block, claims, proof, now=now)
        if not classifier:
            continue
        for claim in claims[:1]:
            # Prefer phrase claims over generic tokens when present.
            selected = claim
            for c in claims:
                if " " in c["claim"] or ":" in c["claim"]:
                    selected = c
                    break
            blocking = classifier in BLOCKING_CLASSIFIERS
            findings.append({
                "heading": block["heading"],
                "claim": selected["claim"],
                "classifier": classifier,
                "blocking": blocking,
                "start": selected["start"],
                "end": selected["end"],
            })
            break
    return {
        "findings": findings,
        "blocking_count": sum(1 for f in findings if f.get("blocking")),
    }


def _successful_ids(tool_results):
    by_id = {}
    for tr in tool_results or []:
        tid = tr.get("tool_use_id") or tr.get("id")
        if not tid:
            continue
        txt = str(tr.get("content", "")).lower()
        denied = (
            txt.strip().startswith("hook pretooluse:")
            or "denied this tool call" in txt[:160]
            or tr.get("is_error") is True
        )
        by_id[tid] = not denied
    return by_id


def touched_ranges_for_tool_uses(tool_uses, tool_results, target_path, content=None):
    """Best-effort touched ranges for successful Write/Edit/MultiEdit calls."""
    if content is None:
        try:
            with open(target_path, encoding="utf-8") as f:
                content = f.read()
        except OSError:
            return []
    target_real = os.path.realpath(os.path.expanduser(target_path))
    success = _successful_ids(tool_results)
    ranges = []
    blocks = list(_iter_blocks(content))

    def target_matches(inp):
        fp = inp.get("file_path") or inp.get("path") or ""
        return isinstance(fp, str) and os.path.realpath(os.path.expanduser(fp)) == target_real

    def add_occurrences(text, force_block=False):
        if not text:
            return
        found = False
        for m in re.finditer(re.escape(text), content):
            ranges.append({"start": m.start(), "end": m.end(), "block": force_block})
            found = True
        if force_block and not found:
            for b in blocks:
                ranges.append({"start": b["heading_start"], "end": b["body_end"], "block": True})

    for tu in tool_uses or []:
        name = (tu.get("name") or "").lower()
        if name not in ("write", "edit", "multiedit"):
            continue
        inp = tu.get("input") or {}
        if not isinstance(inp, dict) or not target_matches(inp):
            continue
        tid = tu.get("id") or tu.get("tool_use_id")
        if tid in success and not success[tid]:
            continue
        if tid not in success:
            # Missing result: count only when the authored replacement is
            # observably present and not a no-op. This preserves direct hook
            # fixtures while ignoring denied/errored/missing-result no-ops.
            if name == "write":
                if content != inp.get("content", "") or content.count("\n## ") == 0:
                    continue
            elif name == "edit" and inp.get("old_string") == inp.get("new_string"):
                continue
            elif name == "multiedit":
                edits = inp.get("edits") or []
                if all(isinstance(e, dict) and e.get("old_string") == e.get("new_string") for e in edits):
                    continue
        if name == "write":
            text = inp.get("content", "")
            for block in blocks:
                if text and content[block["heading_start"]:block["body_end"]] in text:
                    # Conservative but not whole-history: audit blocks that
                    # have an attached Proof block, or the sole block in a
                    # one-entry write.
                    if _proof_span(block) or len(blocks) == 1:
                        ranges.append({
                            "start": block["heading_start"],
                            "end": block["body_end"],
                            "tool": "Write",
                            "block": True,
                        })
            continue
        if name == "edit":
            force = "Proof:" in str(inp.get("old_string", ""))
            add_occurrences(inp.get("new_string", ""), force_block=force)
        else:
            for edit in inp.get("edits") or []:
                if not isinstance(edit, dict):
                    continue
                force = "Proof:" in str(edit.get("old_string", ""))
                add_occurrences(edit.get("new_string", ""), force_block=force)
    return ranges


def audit_path(path, touched_ranges=None, full_sweep=False):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    return audit_fix_plan_content(content, touched_ranges=touched_ranges, full_sweep=full_sweep)


def _recent_heading_ranges(content, count):
    """Return block ranges for the last `count` fix_plan.md entries.

    "Entries" here means whatever `_iter_blocks` yields: markdown H2 (`## `)
    sections AND nested H3 (`### H-<id>`) gate-hole sub-entries, in document
    order. A nested sub-entry carries its own real status claim, so it counts
    toward `count` and is reachable by a bounded recent-N sweep just like a
    top-level H2 section -- it is not permanently invisible behind its
    enclosing parent.

    This is a bounded historical-sweep helper: callers can ask for the most
    recent N fix_plan entries and combine it with --strict, instead of running
    a whole-file strict sweep over years of known historical debt.
    """
    try:
        count = int(count)
    except (TypeError, ValueError):
        return []
    if count <= 0:
        return []
    blocks = list(_iter_blocks(content))
    selected = blocks[-count:]
    return [
        {
            "start": block["heading_start"],
            "end": block["body_end"],
            "block": True,
        }
        for block in selected
    ]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--strict", action="store_true")
    scoped = parser.add_mutually_exclusive_group()
    scoped.add_argument("--hook-touched-json")
    scoped.add_argument("--recent-headings", type=int)
    args = parser.parse_args(argv)
    if args.hook_touched_json is not None:
        try:
            touched = json.loads(args.hook_touched_json)
        except ValueError:
            touched = []
        mode = "hook"
        result = audit_path(args.path, touched_ranges=touched, full_sweep=False)
    elif args.recent_headings is not None:
        try:
            with open(args.path, encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            sys.stderr.write("could not read %s: %s\n" % (args.path, e))
            return 2
        mode = "recent_headings"
        touched = _recent_heading_ranges(content, args.recent_headings)
        result = audit_fix_plan_content(content, touched_ranges=touched, full_sweep=False)
        result["recent_headings"] = args.recent_headings
    else:
        mode = "full_sweep"
        result = audit_path(args.path, touched_ranges=None, full_sweep=True)
    result["mode"] = mode
    print(json.dumps(result, sort_keys=True))
    if args.strict and result.get("blocking_count", 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
