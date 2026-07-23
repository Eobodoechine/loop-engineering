#!/usr/bin/env python3
"""Shared findings-persistence scanner for adversarial review dispatches.

The Stop hook owns process control; this module is deliberately pure-ish:
callers pass the current turn's tool_uses/tool_results and receive violation
messages. It does not import loop_stop_guard.py or depend on micro-step target
resolution.
"""
import json
import os
import re
import subprocess


MARKER = "FINDINGS_PERSISTENCE_REQUIRED"
LEDGER_NAME = "KNOWN_ISSUES.md"

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TARGET_RE = re.compile(r"(?m)^\s*TARGET_REPO=([^\s]+)\s*$")
_RUN_ID_LINE_RE = re.compile(r"(?m)^\s*FINDINGS_RUN_ID=([A-Za-z0-9._-]+)\s*$")
_LOOP_FRAMEWORK_TARGET_RE = re.compile(r"(?m)^\s*TARGET_REPO_IS_LOOP_FRAMEWORK=1\s*$")
_FALLBACK_COUNT_RE = re.compile(r"(?im)\bCONFIRMED\s+FINDINGS\s*:\s*(\d+)\b")


def _tool_input(tool_use):
    value = tool_use.get("input")
    return value if isinstance(value, dict) else {}


def dispatch_text(tool_use):
    inp = _tool_input(tool_use)
    name = str(tool_use.get("name", "") or "").lower()
    if name == "workflow":
        return str(inp.get("script", "") or "")
    fields = []
    for key in ("description", "prompt", "script"):
        value = inp.get(key)
        if isinstance(value, str) and value:
            fields.append(value)
    return "\n".join(fields)


def result_text(tool_result):
    content = tool_result.get("content", "")
    if isinstance(content, list):
        return "\n".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def _is_pretooluse_deny(tool_result):
    text = result_text(tool_result).strip().lower()
    return (
        (text.startswith("hook pretooluse:") and "denied this tool" in text[:120])
        or text.startswith("blocked before dispatch")
        or text.startswith("[oga guard]")
    )


def _dispatch_id(tool_use):
    return tool_use.get("id") if tool_use.get("id") is not None else tool_use.get("tool_use_id")


def _result_id(tool_result):
    return (
        tool_result.get("tool_use_id")
        if tool_result.get("tool_use_id") is not None
        else tool_result.get("id")
    )


def _result_for(tool_use, tool_results):
    tid = _dispatch_id(tool_use)
    if not tid:
        return None
    for tr in tool_results:
        if _result_id(tr) == tid:
            return tr
    return None


def _extract_marker_fields(text):
    if MARKER not in (text or ""):
        return None
    target_match = _TARGET_RE.search(text or "")
    run_match = _RUN_ID_LINE_RE.search(text or "")
    return {
        "target": target_match.group(1) if target_match else None,
        "run_id": run_match.group(1) if run_match else None,
        "target_is_loop_framework": bool(_LOOP_FRAMEWORK_TARGET_RE.search(text or "")),
    }


def _parse_json_result(text):
    try:
        value = json.loads(text)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


def _finding_identity(finding):
    title = str(finding.get("title", "") or "").strip()
    component = str(finding.get("component", "") or "").strip()
    return (title.lower(), component.lower())


def _confirmed_structured_findings(text):
    payload = _parse_json_result(text)
    if payload is None:
        return None
    status = str(payload.get("status", "") or "").strip().lower()
    if status in {"blocked", "denied", "errored", "error", "failed"}:
        return []
    findings = payload.get("findings")
    if not isinstance(findings, list):
        return []
    out = []
    seen = set()
    for item in findings:
        if not isinstance(item, dict):
            continue
        verdict = str(item.get("verdict", "") or "").strip().lower()
        if verdict != "confirmed":
            continue
        title = str(item.get("title", "") or "").strip()
        if not title:
            continue
        ident = _finding_identity(item)
        if ident in seen:
            continue
        seen.add(ident)
        out.append(item)
    return out


def _fallback_confirmed_count(text):
    match = _FALLBACK_COUNT_RE.search(text or "")
    if not match:
        return 0
    try:
        return max(0, int(match.group(1)))
    except Exception:
        return 0


def _resolve_repo_root(target):
    if not isinstance(target, str) or not target.startswith("/"):
        return None, "TARGET_REPO must be an existing absolute path"
    real_target = os.path.realpath(os.path.expanduser(target))
    if not os.path.exists(real_target):
        return None, "TARGET_REPO must be an existing absolute path"
    try:
        proc = subprocess.run(
            ["git", "-C", real_target, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return None, "TARGET_REPO must resolve to a git repository"
    if proc.returncode != 0:
        return None, "TARGET_REPO must resolve to a git repository"
    root = proc.stdout.strip()
    if not root:
        return None, "TARGET_REPO must resolve to a git repository"
    return os.path.realpath(root), None


def _has_current_run_id(text, run_id):
    if not run_id:
        return False
    escaped = re.escape(run_id)
    patterns = [
        r"(?m)^\s*FINDINGS_RUN_ID\s*[:=]\s*%s\s*$" % escaped,
        r"(?im)^\s*Findings Run ID\s*[:=]\s*%s\s*$" % escaped,
        r"(?im)^\s*Run ID\s*[:=]\s*%s\s*$" % escaped,
    ]
    return any(re.search(pattern, text or "") for pattern in patterns)


def _split_entries(ledger_text):
    entries = []
    current = []
    for line in (ledger_text or "").splitlines():
        if line.startswith("## "):
            if current:
                entries.append("\n".join(current).strip())
            current = [line]
        elif current:
            current.append(line)
    if current:
        entries.append("\n".join(current).strip())
    return [entry for entry in entries if entry.strip()]


def _words(text):
    stop = {
        "the", "and", "that", "with", "from", "this", "into", "for", "has",
        "have", "issue", "defect", "path", "real", "behavior", "requires",
        "code", "changes", "confirmed", "status", "component", "severity",
        "high", "medium", "low",
    }
    return [
        w for w in re.findall(r"[A-Za-z0-9]+", (text or "").lower())
        if len(w) >= 4 and w not in stop
    ]


def _is_substantive_entry(entry):
    lowered = entry.lower()
    if not entry.strip().startswith("## "):
        return False
    if re.search(r"\b(todo|tbd|placeholder|pending|more details later)\b", lowered):
        return False
    if not re.search(r"(?im)^\s*status\s*:\s*confirmed\b", entry):
        return False
    heading = entry.splitlines()[0] if entry.splitlines() else ""
    if len(_words(heading)) < 2:
        return False
    return len(_words(entry)) >= 8


def _finding_matches_entry(finding, entry):
    if not _is_substantive_entry(entry):
        return False
    lowered = entry.lower()
    title = str(finding.get("title", "") or "").strip()
    component = str(finding.get("component", "") or "").strip()
    title_words = set(_words(title))
    if title and title.lower() in lowered:
        title_ok = True
    else:
        overlap = len(title_words.intersection(_words(entry)))
        title_ok = bool(title_words) and overlap >= min(4, max(2, len(title_words)))
    component_ok = True
    if component:
        component_words = set(_words(component))
        component_ok = component.lower() in lowered or bool(
            component_words.intersection(_words(entry))
        )
    return title_ok and component_ok


def _validate_ledger(repo_root, run_id, structured_findings, fallback_count):
    ledger_path = os.path.join(repo_root, LEDGER_NAME)
    if not os.path.isfile(ledger_path):
        return False, (
            "Confirmed adversarial-review findings must be persisted in %s"
            % ledger_path
        )
    try:
        with open(ledger_path, encoding="utf-8") as fh:
            ledger = fh.read()
    except OSError:
        return False, "Unable to read findings ledger %s" % ledger_path

    if not _has_current_run_id(ledger, run_id):
        return False, (
            "%s must include current-review identity FINDINGS_RUN_ID=%s"
            % (ledger_path, run_id)
        )

    entries = _split_entries(ledger)
    substantive_entries = [entry for entry in entries if _is_substantive_entry(entry)]
    if structured_findings:
        unmatched = []
        for finding in structured_findings:
            if not any(_finding_matches_entry(finding, entry) for entry in entries):
                unmatched.append(str(finding.get("title", "") or "").strip())
        if unmatched:
            return False, (
                "%s must contain substantive issue entries strongly matching "
                "the confirmed finding(s): %s"
                % (ledger_path, ", ".join(unmatched))
            )
        return True, ""

    required = min(fallback_count, 3)
    if required > 0 and len(substantive_entries) < required:
        return False, (
            "%s must contain at least %d substantive issue entries for this "
            "text fallback result"
            % (ledger_path, required)
        )
    return True, ""


def find_findings_persistence_violations(
    tool_uses,
    tool_results,
    blocked_ids=None,
    loop_root=None,
):
    """Return violation messages for marked review results lacking persistence."""
    blocked_ids = set(blocked_ids or set())
    violations = []
    real_loop_root = os.path.realpath(loop_root) if loop_root else None

    for tool_use in tool_uses:
        name = str(tool_use.get("name", "") or "").lower()
        if name not in {"agent", "task", "subagent", "workflow"}:
            continue
        tid = _dispatch_id(tool_use)
        if tid in blocked_ids:
            continue

        text = dispatch_text(tool_use)
        fields = _extract_marker_fields(text)
        if fields is None:
            continue

        tool_result = _result_for(tool_use, tool_results)
        if tool_result is None:
            continue
        if tool_result.get("is_error") is True or _is_pretooluse_deny(tool_result):
            continue

        rtext = result_text(tool_result)
        structured = _confirmed_structured_findings(rtext)
        fallback_count = 0
        if structured is None:
            fallback_count = _fallback_confirmed_count(rtext)
            confirmed_count = fallback_count
            structured = []
        else:
            confirmed_count = len(structured)

        if confirmed_count <= 0:
            continue

        run_id = fields.get("run_id")
        if not run_id or not _RUN_ID_RE.match(run_id):
            violations.append(
                "[LOOP STOP-GUARD] FINDINGS_PERSISTENCE_MISSING: marked review "
                "returned confirmed findings, but dispatch text lacks a valid "
                "FINDINGS_RUN_ID=<id>."
            )
            continue

        repo_root, target_error = _resolve_repo_root(fields.get("target"))
        if repo_root is None:
            violations.append(
                "[LOOP STOP-GUARD] FINDINGS_PERSISTENCE_MISSING: marked review "
                "returned confirmed findings, but %s. Include "
                "TARGET_REPO=<absolute-path>."
                % target_error
            )
            continue

        if (
            real_loop_root
            and os.path.realpath(repo_root) == real_loop_root
            and not fields.get("target_is_loop_framework")
        ):
            violations.append(
                "[LOOP STOP-GUARD] FINDINGS_PERSISTENCE_MISSING: TARGET_REPO "
                "resolved to the loop root (%s). Include "
                "TARGET_REPO_IS_LOOP_FRAMEWORK=1 in this dispatch text only "
                "for intentional loop framework reviews."
                % repo_root
            )
            continue

        ok, reason = _validate_ledger(repo_root, run_id, structured, fallback_count)
        if not ok:
            violations.append(
                "[LOOP STOP-GUARD] FINDINGS_PERSISTENCE_MISSING: %s" % reason
            )

    return violations
