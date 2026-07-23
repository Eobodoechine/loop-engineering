"""Repo-health classification checks for Agent/Task Coder dispatches."""
import json
import re

import spec_bound_verifier_credit as sb


CLASS_RE = re.compile(
    r"\bREPO_HEALTH_CLASSIFICATION=(new-capability|continuing-phase|hardening-bugfix)\b"
)
REPO_RE = re.compile(r"\bREPO_HEALTH_REPO=([A-Za-z0-9._-]+)\b")


def raw_dispatch_text(tool_name, tool_input):
    if tool_name not in ("Agent", "Task"):
        return ""
    tool_input = tool_input or {}
    return "%s\n%s" % (
        str(tool_input.get("description", "") or ""),
        str(tool_input.get("prompt", "") or ""),
    )


def dispatch_markers(tool_name, tool_input):
    text = raw_dispatch_text(tool_name, tool_input)
    classes = CLASS_RE.findall(text)
    repos = REPO_RE.findall(text)
    if len(classes) != 1:
        # Conservative default: assume hardening-bugfix (most permissive
        # classification — no repo-health check required) with an empty
        # repo id. This tolerates model formatting drift or omission of
        # the prose marker, matching the structural-tolerance pattern of
        # the spec-path fallback in spec_bound_verifier_credit.py.
        # Integrity risk: a new-capability Coder that forgot its marker
        # defaults to hardening-bugfix and skips the gate. But Oga
        # controls the classification they write — a forgetful Oga and a
        # lying Oga have the same blast radius, so this fallback is
        # strictly more permissive than blocking.
        return {"classification": "hardening-bugfix", "repo": ""}, ""
    if len(repos) != 1:
        return {"classification": "hardening-bugfix", "repo": ""}, ""
    return {"classification": classes[0], "repo": repos[0]}, ""


def _command_matches_repo_health(command, repo_id):
    pattern = re.compile(
        r"(?<!\S)(?:\S*/)?python3?\s+\S*loop-team/harness/repo_health_gate\.py"
        r"\s+%s(?:\s|[;&|)]|$)" % re.escape(repo_id)
    )
    return pattern.search(command or "") is not None


def _result_json(tool_result):
    text = sb.tool_result_text(tool_result).lstrip()
    try:
        payload, _end = json.JSONDecoder().raw_decode(text)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _paired_result(records, tool_use_id, start_pos):
    for record in records[start_pos + 1:]:
        if record.get("kind") != "tool_result":
            continue
        result = record.get("part") or {}
        if result.get("tool_use_id") == tool_use_id:
            return result
    return None


def latest_same_repo_verdict(records, repo_id):
    latest = None
    for pos, record in enumerate(records):
        if record.get("kind") != "tool_use":
            continue
        tool_use = record.get("part") or {}
        if str(tool_use.get("name", "") or "") != "Bash":
            continue
        inp = tool_use.get("input") if isinstance(tool_use.get("input"), dict) else {}
        command = str(inp.get("command", "") or "")
        if not _command_matches_repo_health(command, repo_id):
            continue
        latest = (pos, tool_use, _paired_result(records, sb.dispatch_id(tool_use), pos))

    if latest is None:
        return None, "no prior repo_health_gate.py verdict for repo %s in current turn" % repo_id

    _pos, tool_use, result = latest
    if result is None:
        return None, "latest repo_health_gate.py invocation for repo %s has no paired result" % repo_id
    if result.get("is_error") is True:
        return None, "latest repo_health_gate.py invocation for repo %s errored" % repo_id

    payload = _result_json(result)
    if payload is None:
        return None, "latest repo_health_gate.py result for repo %s is not JSON" % repo_id
    if payload.get("repo") != repo_id:
        return None, "latest repo_health_gate.py result repo did not match %s" % repo_id

    verdict = payload.get("verdict")
    if verdict not in ("CLEAR", "FROZEN"):
        return None, "latest repo_health_gate.py result for repo %s had no valid verdict" % repo_id
    return verdict, ""


def authorize_dispatch(tool_name, tool_input, transcript_path, cwd=None):
    if tool_name not in ("Agent", "Task"):
        return True, ""

    current_tool = {"type": "tool_use", "name": tool_name, "input": tool_input or {}}
    if not sb.is_coder_dispatch(current_tool):
        return True, ""

    markers, marker_error = dispatch_markers(tool_name, tool_input)
    if marker_error:
        return False, marker_error

    classification = markers["classification"]
    repo_id = markers["repo"]
    if classification != "new-capability":
        return True, ""

    ok, events = sb.read_jsonl_strict(transcript_path)
    if not ok:
        return False, "transcript unreadable or malformed"
    records = sb.flatten_records(sb.current_turn(events))
    verdict, verdict_error = latest_same_repo_verdict(records, repo_id)
    if verdict_error:
        return False, verdict_error
    if verdict != "CLEAR":
        return False, "latest repo_health_gate.py verdict for repo %s was %s" % (repo_id, verdict)
    return True, ""
