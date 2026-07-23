"""Shared spec-bound Verifier credit checks for PreToolUse and Stop hooks."""
import hashlib
import json
import os
import re
from enum import Enum

from verifier_hygiene_scan import VERIFIER_DETECT


HASH_RE = re.compile(r"\bSPEC_SHA256=([0-9a-f]{64})\b")
SPEC_HASH_LINE_RE = re.compile(r"(?im)^\s*SPEC_SHA256\s*=\s*([0-9a-f]{64})\s*$")
REVIEWED_HASH_RE = re.compile(r"\bREVIEWED_SPEC_SHA256=([0-9a-f]{64})(?:\b|(?=agentId:))")
PLAN_SUPPORT_PREFIX = "PLAN_SUPPORT_JSON="
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
# Strong coder directives — role assignments and implementation directives that
# MUST classify as Coder regardless of subagent_type. These cannot be laundered
# out by claiming a non-Coder subagent_type.
CODER_DETECT_STRONG = re.compile(
    r"role:\s*coder\b"
    r"|\byou are (?:now )?the coder\b"
    r"|\bact as (?:the )?coder\b"
    r"|\bimplement\b.{0,120}\b(?:directly|using (?:the )?(?:edit|write|multiedit|apply_patch) tools?)\b"
    r"|\b(?:edit|write|multiedit|apply_patch) tools?\b.{0,120}\bimplement\b",
    re.I,
)
# Weak coder signals — incidental references that CAN be suppressed when
# subagent_type is a known non-Coder role. These are ambiguous: "coder for <task>"
# or "roles/coder.md" can appear in loop-team framework discussions without the
# dispatch actually being a Coder dispatch.
CODER_DETECT_WEAK = re.compile(
    r"\bcoder for\b"
    r"|roles/coder",
    re.I,
)
# Backwards-compatible alias for code that checks "any coder signal"
CODER_DETECT = re.compile(
    CODER_DETECT_STRONG.pattern + r"|" + CODER_DETECT_WEAK.pattern,
    re.I,
)
SPEC_LINE_RE = re.compile(r"(?im)^\s*(?:SPEC|Review exactly one spec)\s*:\s*(.+?)\s*$")
SPEC_TOKEN_RE = re.compile(r"(?:~|/|\.\.?/)?[^\s\"'`),;]+\.md\b")
TASK_NOTIFICATION_RE = re.compile(r"<task-notification[\s\S]*?</task-notification>", re.I)
NOTIF_TOOL_USE_ID_RE = re.compile(r"<tool-use-id>([^<]+)</tool-use-id>", re.I)
NOTIF_STATUS_RE = re.compile(r"<status>([^<]+)</status>", re.I)
NOTIF_RESULT_RE = re.compile(r"<result>([\s\S]*?)</result>", re.I)
VERIFIER_FALLBACK_RE = re.compile(
    r"plan-?check[- ]verifier"
    r"|verifier[- ]plan-?check"
    r"|verifier\b.{0,40}\bin\s+plan-?check\s+mode",
    re.I,
)
# Code fence tolerance (2026-07-19): subagents naturally wrap structured output
# in markdown code blocks (``` or ```lang ... ```). The closing fence line
# after LOOP_GATE: PLAN_PASS was being rejected as "unexpected content after
# final gate line." Strip bare code fence lines before parsing — they carry
# no semantic content and their presence is a model formatting choice, not a
# hijack vector. A bare fence is exactly ``` optionally followed by a language
# tag, with no other content on the line.
CODE_FENCE_RE = re.compile(r"^```(?:[A-Za-z0-9_+-]*)$")
VERIFIER_ROLE_MODE_RE = re.compile(
    r"(?ims)^\s*#?\s*role\s*:\s*verifier\b"
    r"(?:(?!^\s*#?\s*role\s*:).)*"
    r"^\s*#?\s*mode\s*:\s*plan-?check\b"
)


class PlanResultOutcome(str, Enum):
    """Semantic outcome of one resolved, qualifying Verifier result."""

    VALID_PASS = "VALID_PASS"
    EXPLICIT_PLAN_FAIL = "EXPLICIT_PLAN_FAIL"
    SUPPORT_INVALID_DECLARED_PASS = "SUPPORT_INVALID_DECLARED_PASS"
    OTHER_INVALID_OR_AMBIGUOUS = "OTHER_INVALID_OR_AMBIGUOUS"


def content(event):
    message = event.get("message")
    if isinstance(message, dict) and "content" in message:
        return message["content"]
    return event.get("content")


def _notification_text(event):
    parts = content(event)
    if isinstance(parts, str):
        return parts
    payload = event.get("payload")
    if isinstance(payload, str):
        return payload
    return ""


def _notification_tool_result(event):
    text = _notification_text(event)
    if not text or not TASK_NOTIFICATION_RE.search(text):
        return None
    tid = NOTIF_TOOL_USE_ID_RE.search(text)
    status = NOTIF_STATUS_RE.search(text)
    result = NOTIF_RESULT_RE.search(text)
    if not tid or not status or not result:
        return None
    if status.group(1).strip().lower() != "completed":
        return None
    return {
        "type": "tool_result",
        "tool_use_id": tid.group(1).strip(),
        "content": result.group(1),
    }


def is_tool_result_turn(event):
    parts = content(event)
    if isinstance(parts, list):
        return any(isinstance(p, dict) and p.get("type") == "tool_result" for p in parts)
    # AC-C-1 / C.2(i): loop_stop_guard.py's own re-invocation injects a plain
    # "Stop hook feedback:\n[...]" string back into the transcript -- this is
    # not a genuine turn boundary (no origin-based logic exists in the real
    # code; see C.3), so treat it the same as any other non-boundary event.
    if isinstance(parts, str) and parts.startswith("Stop hook feedback:"):
        return True
    return bool(TASK_NOTIFICATION_RE.search(_notification_text(event)))


def read_jsonl_strict(path):
    if not path:
        return False, []
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except Exception:
        return False, []
    events = []
    for line in lines:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except Exception:
            return False, []
    return True, events


def current_turn(events):
    start = 0
    for i in range(len(events) - 1, -1, -1):
        event = events[i]
        is_user = event.get("role") == "user" or event.get("type") == "user"
        if is_user and not is_tool_result_turn(event):
            start = i
            break
    return events[start:]


def flatten_records(events):
    records = []
    ordinal = 0
    for event in events:
        parts = content(event)
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict):
                    continue
                ptype = part.get("type")
                if ptype in ("tool_use", "tool_result"):
                    # R7: tag as raw/non-synthetic -- a genuine transcript content-part, never
                    # derived from a <task-notification> event.
                    records.append({"ordinal": ordinal, "kind": ptype, "part": part,
                                     "synthetic": False})
                    ordinal += 1
            continue
        notification_result = _notification_tool_result(event)
        if notification_result is not None:
            # R7: tag as synthetic -- constructed from a <task-notification> event, which
            # _notification_tool_result() only ever produces for status=="completed" (line ~48).
            records.append({
                "ordinal": ordinal,
                "kind": "tool_result",
                "part": notification_result,
                "synthetic": True,
            })
            ordinal += 1
    return records


def tool_input(tool_use):
    value = tool_use.get("input")
    return value if isinstance(value, dict) else {}


def dispatch_name(tool_use):
    return str(tool_use.get("name", "") or "").lower()


def is_dispatch_tool(tool_use):
    return dispatch_name(tool_use) in ("task", "agent", "subagent", "workflow")


def is_agent_task_dispatch(tool_use):
    return dispatch_name(tool_use) in ("task", "agent", "subagent")


def dispatch_text(tool_use):
    inp = tool_input(tool_use)
    if dispatch_name(tool_use) == "workflow":
        return str(inp.get("script", "") or "").lower()
    desc = str(inp.get("description", "") or "").lower()
    if desc:
        return desc
    return str(inp.get("prompt", "") or "").lower()


def dispatch_prompt(tool_use):
    inp = tool_input(tool_use)
    if dispatch_name(tool_use) == "workflow":
        return str(inp.get("script", "") or "")
    return str(inp.get("prompt", "") or "")


def is_verifier_dispatch(tool_use):
    if not is_dispatch_tool(tool_use):
        return False
    inp = tool_input(tool_use)
    text = dispatch_text(tool_use)
    content_says_verifier = (
        VERIFIER_DETECT.search(text) is not None
        or VERIFIER_FALLBACK_RE.search(text) is not None
        or VERIFIER_ROLE_MODE_RE.search(dispatch_prompt(tool_use)) is not None
    )
    subagent_says_verifier = (
        str(inp.get("subagent_type", "") or "").strip().lower() == "plan-check-verifier"
    )
    if not (content_says_verifier or subagent_says_verifier):
        return False
    # subagent_type is caller-supplied and structurally unenforced -- it may only
    # ADD to verifier classification, never SUBTRACT Coder-detection scope. This
    # exact suppression shape was independently, adversarially proven exploitable
    # twice in loop_stop_guard.py's own history (Misfire-1/2/3, fix_plan.md
    # 2026-07-08) before this build reintroduced it a third time. A dispatch whose
    # CONTENT independently satisfies is_coder_dispatch's own detection must never
    # be excused into Verifier classification merely because it ALSO claims
    # subagent_type="plan-check-verifier".
    if subagent_says_verifier and not content_says_verifier and is_coder_dispatch(tool_use):
        return False
    return True


# Explicit non-Coder subagent types that suppress WEAK coder signals.
# When subagent_type is set to a known non-Coder role, WEAK coder signals
# (incidental references like "coder for <task>", "roles/coder.md") are suppressed.
# STRONG coder directives (role assignments, implementation directives) are NEVER
# suppressed — they classify as Coder regardless of subagent_type. This preserves
# the hard invariant: "A live, immediate coder directive in the prompt must classify
# as Coder, regardless of what subagent_type the dispatch claims." (Diagnosed 2026-07-19:
# Explore and researcher dispatches were blocked by repo-health + spec-bound credit
# gates because their prompts quoted orchestrator.md which liberally mentions "Coder";
# the classifier had no suppression path for weak signals. The previous fix tried to
# suppress ALL coder signals based on subagent_type, but that violated the hard
# invariant and broke 10 adversarial tests.)
_NON_CODER_SUBAGENT_TYPES = frozenset({
    "explore", "researcher", "verifier", "plan-check-verifier",
    "test-writer", "test_writer", "general-purpose", "claude",
    "claude-code-guide", "plan", "statusline-setup",
})


def is_coder_dispatch(tool_use):
    if not is_dispatch_tool(tool_use):
        return False
    inp = tool_input(tool_use)
    sub = str(inp.get("subagent_type", "") or "").strip().lower()
    # Fast path: explicit coder subagent_type
    if sub == "coder":
        return True
    # Check for STRONG coder directives — these ALWAYS classify as Coder,
    # regardless of subagent_type. This is the hard invariant.
    text = dispatch_text(tool_use)
    prompt = dispatch_prompt(tool_use).lower()
    if (CODER_DETECT_STRONG.search(text) is not None
            or CODER_DETECT_STRONG.search(prompt) is not None):
        return True
    # Only WEAK signals remain. Suppress if subagent_type is a known non-Coder role.
    if sub in _NON_CODER_SUBAGENT_TYPES:
        return False
    # Check for WEAK coder signals — these classify as Coder only when
    # subagent_type is unset, unknown, or ambiguous.
    return (
        CODER_DETECT_WEAK.search(text) is not None
        or CODER_DETECT_WEAK.search(prompt) is not None
    )


def dispatch_id(tool_use):
    tid = tool_use.get("id")
    if tid is None:
        tid = tool_use.get("tool_use_id")
    return tid


def canonical_spec_path(ref, cwd=None):
    if not isinstance(ref, str) or not ref.strip():
        return None
    path = os.path.expanduser(ref.strip())
    if not os.path.isabs(path):
        path = os.path.join(cwd or os.getcwd(), path)
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        return None
    return os.path.realpath(path)


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def extract_spec_info_from_text(text, cwd=None):
    text = text or ""
    hashes = SPEC_HASH_LINE_RE.findall(text)
    if not hashes:
        hashes = HASH_RE.findall(text)
    refs = []
    for match in SPEC_LINE_RE.findall(text):
        for token in SPEC_TOKEN_RE.findall(match):
            token = token.strip().rstrip(".:")
            if token:
                refs.append(token)

    # Fallback: if the strict SPEC: search found 0 or 2+ refs, try broader
    # .md path search across the entire prompt text (not just SPEC: content).
    # Mirrors HASH_RE's existing mid-line fallback pattern for hash extraction.
    if len(refs) != 1:
        fallback_refs = []
        for token in SPEC_TOKEN_RE.findall(text):
            token = token.strip().rstrip(".:")
            if token and token not in fallback_refs:
                fallback_refs.append(token)
        if len(fallback_refs) == 1:
            refs = fallback_refs

    if len(refs) != 1:
        return None, "expected exactly one spec ref"
    if len(hashes) != 1:
        return None, "expected exactly one SPEC_SHA256"
    canonical = canonical_spec_path(refs[0], cwd=cwd)
    if canonical is None:
        return None, "spec ref is not a readable file"
    return {"ref": refs[0], "path": canonical, "hash": hashes[0]}, None


def extract_spec_info(tool_use, cwd=None):
    return extract_spec_info_from_text(dispatch_prompt(tool_use), cwd=cwd)


def current_spec_hash_matches(spec_info):
    try:
        return file_sha256(spec_info["path"]) == spec_info["hash"]
    except Exception:
        return False


def tool_result_text(tool_result):
    value = tool_result.get("content", "")
    if isinstance(value, list):
        value = "\n".join(
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in value
        )
    return str(value)


def is_pretooluse_deny_result(tool_result):
    txt = tool_result_text(tool_result).strip().lower()
    return (
        (txt.startswith("hook pretooluse:") and "denied this tool" in txt[:120])
        or txt.startswith("blocked before dispatch")
        or txt.startswith("[oga guard]")
    )


def _canonical_support_path(artifact_path, cwd=None):
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        return None
    path = os.path.expanduser(artifact_path.strip())
    if not os.path.isabs(path):
        path = os.path.join(cwd or os.getcwd(), path)
    return os.path.realpath(os.path.abspath(path))


def _support_span_digest(path, line_start, line_end):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    if line_start < 1 or line_end < line_start or line_end > len(lines):
        return None, "missing artifact/span"
    selected = lines[line_start - 1:line_end]
    joined = "\n".join(selected)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest(), None


def _validate_plan_support_json(line, reviewed_hash, cwd=None):
    if not line.startswith(PLAN_SUPPORT_PREFIX):
        return False, "malformed support"
    raw = line[len(PLAN_SUPPORT_PREFIX):].strip()
    try:
        obj = json.loads(raw)
    except Exception:
        return False, "malformed support"
    if not isinstance(obj, dict):
        return False, "malformed support"

    artifact_path = obj.get("artifact_path")
    line_start = obj.get("line_start")
    line_end = obj.get("line_end")
    evidence_sha256 = obj.get("evidence_sha256")
    claim = obj.get("claim")
    spec_sha256 = obj.get("spec_sha256")

    if not isinstance(artifact_path, str) or not artifact_path.strip():
        return False, "malformed support"
    if (
        not isinstance(line_start, int) or isinstance(line_start, bool)
        or not isinstance(line_end, int) or isinstance(line_end, bool)
        or line_start < 1 or line_end < line_start
    ):
        return False, "missing artifact/span"
    if not isinstance(evidence_sha256, str) or SHA256_RE.match(evidence_sha256) is None:
        return False, "malformed support"
    if not isinstance(claim, str) or not claim.strip():
        return False, "malformed support"
    if spec_sha256 != reviewed_hash:
        return False, "support spec hash mismatch"

    path = _canonical_support_path(artifact_path, cwd=cwd)
    if path is None or not os.path.isfile(path):
        return False, "missing artifact/span"
    actual, err = _support_span_digest(path, line_start, line_end)
    if err:
        return False, err
    if actual != evidence_sha256:
        return False, "evidence hash mismatch"
    return True, ""


def classify_plan_result_for_hash(tool_result, reviewed_hash, cwd=None):
    """Return ``(PlanResultOutcome, reason)`` for one terminal result.

    A PASS must now bind the final gate line and reviewed spec hash to at
    least one on-disk PLAN_SUPPORT_JSON line-span citation. Support validation
    begins only after unique PASS structure and exact reviewed-hash binding
    succeed, so support-only defects can be distinguished from every other
    fail-closed terminal outcome without parsing diagnostic reason strings.
    """
    if tool_result.get("is_error") is True or is_pretooluse_deny_result(tool_result):
        return (PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS,
                "tool result is an error or PreToolUse deny")
    text = tool_result_text(tool_result)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # Code fence tolerance (2026-07-19): strip bare markdown code fence lines
    # (``` or ```lang) before parsing. Subagents frequently wrap structured
    # gate output in code blocks for readability; the fence lines carry no
    # semantic content and must not trigger "unexpected content after final
    # gate line." This is a pure strip — no content judgment, no tolerance
    # of fences around individual marker lines (which would be a hijack
    # vector). Only bare fence lines are removed; a line like "```json foo"
    # (content after the language tag) is not a fence and is preserved.
    lines = [ln for ln in lines if not CODE_FENCE_RE.match(ln)]

    # D.2.e / D.1.4(d): exactly one standalone "LOOP_GATE:"-prefixed line is
    # required -- zero or 2+ (e.g. a decoy verdict line occurring after the
    # sincere one) is rejected outright, closing the "textually last wins"
    # hijack.
    gate_positions = [
        (idx, ln) for idx, ln in enumerate(lines) if ln.startswith("LOOP_GATE:")
    ]
    if len(gate_positions) != 1:
        return (PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS,
                "expected exactly one LOOP_GATE line")
    gate_idx, gate_line = gate_positions[0]

    # Part 1 (spec 879b9b81): tolerate a SINGLE well-formed trailing
    # <usage>...</usage> block after the final gate line -- the harness
    # appends this to every Agent-tool result; no model controls it. At most
    # one block, must be properly closed (an unterminated/self-closing
    # <usage> is rejected with its own distinct reason, never silently
    # tolerated), and nothing else may trail -- this replaces the old
    # blanket "must be the final non-empty line" rule with a narrow,
    # structurally-scoped tolerance for exactly this one harness artifact.
    trailing = lines[gate_idx + 1:]
    i, n, seen_usage, seen_agent_id = 0, len(trailing), False, False
    while i < n:
        if trailing[i].startswith("<usage"):
            if seen_usage:
                return (PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS,
                        "unexpected content after final gate line")
            seen_usage = True
            while i < n and "</usage>" not in trailing[i]:
                i += 1
            if i >= n:
                return (PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS,
                        "unterminated <usage> block after final gate line")
            i += 1  # consume the line containing </usage>
            continue
        # agentId-harness-metadata tolerance (2026-07-19): the Agent tool
        # harness appends "agentId: <id> (use SendMessage with to: '<id>',
        # summary: '<recap>' to continue this agent.)" as a separate line
        # between the gate line and the <usage> block. This is harness
        # metadata the model does not control — tolerate exactly one such
        # line with a deterministic shape anchor (same as the glued-suffix
        # tolerance at line ~540).
        if not seen_agent_id and re.match(
                r"^agentId:\s*[0-9a-zA-Z-]+\s*\(use SendMessage", trailing[i]):
            seen_agent_id = True
            i += 1
            continue
        return (PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS,
                "unexpected content after final gate line")

    # Part 2 (spec 879b9b81): a second, independently-confirmed-real harness
    # glue form -- the notification/result wrapper's own closing "</result>"
    # tag can land glued directly onto the gate line with no separating
    # newline, distinct from the agentId: glue handled below. Exact-suffix
    # discipline only: a single non-greedy slice off the END, never
    # startswith/replace/split -- the remainder falls through to the
    # unchanged agentId: branch immediately below, which is how the two glue
    # forms compose on one line.
    if gate_line != "LOOP_GATE: PLAN_PASS" and gate_line.endswith("</result>"):
        gate_line = gate_line[:-len("</result>")]

    if gate_line == "LOOP_GATE: PLAN_FAIL":
        return PlanResultOutcome.EXPLICIT_PLAN_FAIL, "explicit LOOP_GATE: PLAN_FAIL"

    # agentId-glue tolerance (mirrors REVIEWED_HASH_RE's own
    # `(?:\b|(?=agentId:))` lookahead at line 11): the harness can glue its
    # own trailing "agentId: <id>..." metadata directly onto this SAME line
    # as the model's sincere "LOOP_GATE: PLAN_PASS" text, with no
    # separating newline -- confirmed live, reproducibly, in both
    # foreground and (very likely) background/notification-delivered
    # results, e.g. the literal observed "LOOP_GATE: PLAN_PASSagentId:
    # a6792fad616e56f8f (use SendMessage with to: ...)". Accept only that
    # one specific glued suffix immediately after the sincere text --
    # anything else (e.g. "LOOP_GATE: PLAN_PASSED", "LOOP_GATE: PLAN_PASS_
    # EXTRA", or arbitrary trailing prose) is still a genuine malformation
    # and must still be rejected, so this stays a narrow tolerance, never a
    # bare startswith("LOOP_GATE: PLAN_PASS") pass that would reopen the
    # exact "textually last wins" hijack the D.2.e comment above guards
    # against.
    #
    # 2026-07-15 follow-up tightening (post-b16cc786): the startswith(...)
    # check above places NO constraint on what follows "agentId:" -- an
    # independent verifier proved live that both
    # "...agentId: fake123 (use SendMessage) actually LOOP_GATE: PLAN_FAIL"
    # and "...agentId: HAHA I CAN WRITE ANYTHING HERE" were wrongly
    # credited as PASS, reopening exactly the "textually last wins" /
    # decoy-verdict hijack the D.2.e comment above defends against --
    # D.2.e's own scan only ever covers lines strictly AFTER the gate
    # line's own index, so a decoy embedded on the gate line's OWN glued
    # suffix was invisible to it. The glued suffix is no longer accepted
    # outright; it must clear two further checks first.
    if gate_line != "LOOP_GATE: PLAN_PASS":
        if not gate_line.startswith("LOOP_GATE: PLAN_PASSagentId:"):
            return (PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS,
                    "final gate line is not LOOP_GATE: PLAN_PASS")
        agent_id_suffix = gate_line[len("LOOP_GATE: PLAN_PASS"):]

        # (1) Structural shape anchor: require the deterministic harness
        # skeleton itself -- an id token immediately followed by "(", e.g.
        # "agentId: a6792fad616e56f8f (use SendMessage with to: ...)" --
        # never the exact prose inside the parens (hardcoding that would
        # be fragile to a harness wording change). This alone rejects
        # "HAHA I CAN WRITE ANYTHING HERE": no "(" immediately follows the
        # first token, so the harness's own shape never matches.
        if not re.match(r"^agentId:\s*[0-9a-zA-Z]+\s*\(", agent_id_suffix):
            return (PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS,
                    "malformed agentId suffix on gate line")

        # (2) Decoy-token scan: the SAME "does a LOOP_GATE-shaped token
        # appear here" family of check used for `trailing_joined` a few
        # lines below, applied to the whole glued suffix instead of only
        # to genuinely-separate trailing lines. Deliberately broader than
        # that check's own PLAN_FAIL-only wording -- D.2.e's stated
        # concern is "a decoy verdict line" in general, not only a
        # PLAN_FAIL-shaped one, so a decoy PLAN_PASS/PLAN_PASSED glued
        # into this same suffix must be rejected too. Keys specifically
        # on the "LOOP_GATE:"-shaped prefix, never a bare "PLAN_PASS"/
        # "PLAN_FAIL" substring search -- the genuine fixture's own
        # trailing prose legitimately echoes the bare word "PLAN_PASS" in
        # its summary text ("summary: 'reviewed spec, PLAN_PASS'"), which
        # a cruder substring check would misfire on.
        if re.search(r'loop_gate["\']?\s*[:=]', agent_id_suffix, re.I):
            return (PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS,
                    "decoy LOOP_GATE token in agentId suffix")

    before_gate = lines[:gate_idx]
    reviewed_hashes = []
    support_lines = []
    for ln in before_gate:
        reviewed_hashes.extend(REVIEWED_HASH_RE.findall(ln))
        if ln.startswith(PLAN_SUPPORT_PREFIX):
            support_lines.append(ln)

    if len(reviewed_hashes) != 1:
        return (PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS,
                "expected exactly one REVIEWED_SPEC_SHA256 before final gate")
    if reviewed_hashes[0] != reviewed_hash:
        return PlanResultOutcome.OTHER_INVALID_OR_AMBIGUOUS, "reviewed spec hash mismatch"
    if not support_lines:
        return (PlanResultOutcome.SUPPORT_INVALID_DECLARED_PASS,
                "no PLAN_SUPPORT_JSON support citation")

    for support_line in support_lines:
        ok, reason = _validate_plan_support_json(support_line, reviewed_hash, cwd=cwd)
        if not ok:
            return PlanResultOutcome.SUPPORT_INVALID_DECLARED_PASS, reason
    return PlanResultOutcome.VALID_PASS, ""


def result_plan_pass_status_for_hash(tool_result, reviewed_hash, cwd=None):
    """Backward-compatible ``(ok, reason)`` PLAN_PASS parser surface."""
    outcome, reason = classify_plan_result_for_hash(
        tool_result, reviewed_hash, cwd=cwd)
    return outcome is PlanResultOutcome.VALID_PASS, reason


def result_is_final_plan_pass_for_hash(tool_result, reviewed_hash, cwd=None):
    ok, _reason = result_plan_pass_status_for_hash(tool_result, reviewed_hash, cwd=cwd)
    return ok


def validate_unique_string_dispatch_ids(records, stop_before_pos=None, include_kinds=("agent", "task", "subagent")):
    seen = set()
    for pos, record in enumerate(records):
        if stop_before_pos is not None and pos >= stop_before_pos:
            break
        if record["kind"] != "tool_use":
            continue
        tool_use = record["part"]
        if dispatch_name(tool_use) not in include_kinds:
            continue
        tid = dispatch_id(tool_use)
        if not isinstance(tid, str) or not tid:
            return False
        if tid in seen:
            return False
        seen.add(tid)
    return True


def prior_verifier_credit(records, coder_pos, coder_info, cwd=None, blocked_ids=None, strict_jsonl=True):
    """C.2(ii)/§C.5: order-independent, unanimous-agreement supersession rule.

    Authorization requires, among all qualifying (matching path+hash, not in
    blocked_ids) Verifier records in the window with a *resolved* paired
    result: at least one resolved, evidence-bound PLAN_PASS and zero explicit
    PLAN_FAIL or other invalid/ambiguous/error/deny results. A declared PASS
    whose unique PASS structure and reviewed hash are valid but whose support
    citation is invalid is resolved yet neutral: it neither grants nor vetoes.
    Every other non-stub result for a qualifying vid is checked individually
    and immediately (not just the positionally-last one), and a genuine fail-
    closed result vetoes wherever encountered. Unresolved/pending records (no
    paired result found yet, or only the structural launch-ack stub) are
    ignored -- they neither grant nor block credit, but are surfaced
    diagnostically (AC-C-4p) once a grant is otherwise earned.

    The launch-stub is exactly, and only, the intersection of two structural
    facts -- never a text-content judgment (R7): (1) was this specific
    dispatch actually launched in background mode
    (tool_input(verifier).get("run_in_background", True))? (2) is this
    specific result record notification-derived ("synthetic": True) or a raw
    content-part ("synthetic": False)? A background dispatch's one raw,
    non-error/deny result is the launch ack -- skippable, not a completion.
    Anything else (a foreground result, a notification-derived/synthetic
    result, or a raw error/deny result) is structurally guaranteed to be a
    real, terminal outcome, regardless of what its text says.
    """
    if not strict_jsonl:
        return False, "transcript JSONL was not strictly readable"
    if not validate_unique_string_dispatch_ids(records, stop_before_pos=coder_pos + 1):
        return False, "current-window dispatch ids are missing, duplicate, or non-string"
    if not current_spec_hash_matches(coder_info):
        return False, "current spec bytes do not match the Coder SPEC_SHA256"

    blocked_ids = blocked_ids or set()
    saw_qualifying_pass = False
    unresolved_sibling_count = 0  # R10: diagnostic-only, see below
    support_invalid_count = 0
    for pos, record in enumerate(records[:coder_pos]):
        if record["kind"] != "tool_use":
            continue
        verifier = record["part"]
        vid = dispatch_id(verifier)
        if vid in blocked_ids or not is_agent_task_dispatch(verifier) or not is_verifier_dispatch(verifier):
            continue
        verifier_info, verifier_error = extract_spec_info(verifier, cwd=cwd)
        if verifier_error or verifier_info is None:
            continue
        if verifier_info["path"] != coder_info["path"] or verifier_info["hash"] != coder_info["hash"]:
            continue
        if not current_spec_hash_matches(verifier_info):
            continue

        # R10: the launch-stub is EXACTLY {background dispatch} AND {raw, non-synthetic result} AND
        # {not an error/deny} -- a structural fact, never a text-content judgment. Default True
        # matches Anthropic's own documented current default (background unless explicitly
        # disabled) -- see the module-level note above for the citation correction. Every fixture
        # in the corpus sets this field explicitly regardless, so this default is provably never
        # load-bearing in the test suite -- only a defensive fallback for real-world edge cases.
        verifier_is_background = tool_input(verifier).get("run_in_background", True)

        # R10: diagnostic-only tracking, closes concurrency-isolation's round-9 finding -- never
        # affects the True/False outcome (AC-C-4f's "genuinely in-flight must never block" is
        # untouched), only annotates the True-path return message so a same-hash sibling that
        # never resolved past its own launch-ack is surfaced, not silently invisible.
        vid_had_non_stub_result = False

        for result_record in records[pos + 1:coder_pos]:
            if result_record["kind"] != "tool_result":
                continue
            result = result_record["part"]
            if result.get("tool_use_id") != vid:
                continue
            # R8: .get(..., True) -- never direct-index "synthetic". A record with no "synthetic"
            # key at all (e.g. Codex-adapter-produced records, which have no launch-stub concept)
            # defaults to "not the stub" -- evaluate normally, never KeyError.
            is_raw = not result_record.get("synthetic", True)
            is_error_or_deny = result.get("is_error") is True or is_pretooluse_deny_result(result)
            if verifier_is_background and is_raw and not is_error_or_deny:
                continue  # the launch ack -- structurally guaranteed, not a completion, keep looking
            vid_had_non_stub_result = True
            outcome, pass_reason = classify_plan_result_for_hash(
                result, coder_info["hash"], cwd=cwd)
            if outcome is PlanResultOutcome.VALID_PASS:
                saw_qualifying_pass = True
            elif outcome is PlanResultOutcome.SUPPORT_INVALID_DECLARED_PASS:
                support_invalid_count += 1
            elif outcome is PlanResultOutcome.EXPLICIT_PLAN_FAIL:
                return False, ("a qualifying Verifier dispatch for this spec hash returned "
                               "an explicit PLAN_FAIL (veto)")
            else:
                # Every resolved non-support ambiguity/error/deny remains an
                # unconditional, order-independent veto.
                return False, ("a qualifying Verifier dispatch for this spec hash returned a "
                               "non-PASS/invalid result: %s" % pass_reason)

        if not vid_had_non_stub_result:
            unresolved_sibling_count += 1  # AC-C-4p: this qualifying vid never got past its ack-stub

    if saw_qualifying_pass:
        notes = []
        if support_invalid_count:
            notes.append(
                "authorized by a valid evidence-bound PLAN_PASS; %d declared PLAN_PASS "
                "attempt(s) had invalid support and were non-crediting/non-vetoing"
                % support_invalid_count)
        if unresolved_sibling_count:
            notes.append(
                "%d same-hash sibling dispatch(es) showed only the launch ack (never "
                "resolved) -- verify their real terminal state directly before trusting "
                "this authorization; see Section H item 5" % unresolved_sibling_count)
        if notes:
            return True, "; ".join(notes)
        return True, ""
    reason = "no prior successful paired Verifier result reviewed this spec hash"
    if support_invalid_count:
        reason += ("; %d support-invalid declared PLAN_PASS attempt(s) granted no credit"
                   % support_invalid_count)
    return False, reason


def check_verifier_pass_flags(session_id, coder_spec_hash, gate_dir=None):
    """Check for a recent .verifier_pass flag file with matching spec hash.

    Returns (True, "authorized by cross-turn verifier_pass flag") on a fresh
    flag whose content matches coder_spec_hash, or (False, reason) on failure.
    Empty-content flags (legacy, from before the hash-storing fix) are never
    considered authorizing -- they are skipped conservatively.
    """
    import glob as _cpf_glob, os as _cpf_os, time as _cpf_time

    if not (session_id and isinstance(session_id, str) and session_id.strip()):
        return False, "no session_id for flag lookup"
    if not (coder_spec_hash and isinstance(coder_spec_hash, str)):
        return False, "no spec hash for flag lookup"

    _cpf_gate_dir = _cpf_os.path.expanduser(
        gate_dir or _cpf_os.environ.get("LOOP_GATE_DIR", "~/.loop-gate"))
    _cpf_pattern = _cpf_os.path.join(
        _cpf_gate_dir, "%s_*.verifier_pass" % _cpf_glob.escape(session_id))
    _cpf_now = _cpf_time.time()
    _cpf_ttl = 24 * 3600

    for _cpf_flag_path in _cpf_glob.glob(_cpf_pattern):
        try:
            _cpf_mtime = _cpf_os.path.getmtime(_cpf_flag_path)
        except OSError:
            continue
        if (_cpf_now - _cpf_mtime) > _cpf_ttl:
            try:
                _cpf_os.remove(_cpf_flag_path)
            except OSError:
                pass
            continue
        try:
            with open(_cpf_flag_path, encoding="utf-8") as _cpf_f:
                _cpf_content = _cpf_f.read().strip()
        except OSError:
            continue
        if not _cpf_content:
            # Empty content = legacy flag, never authorizes
            continue
        if _cpf_content == coder_spec_hash:
            return True, "authorized by cross-turn verifier_pass flag"
    return False, "no matching verifier_pass flag for this spec hash"


def authorize_coder_from_transcript(transcript_path, current_tool_name, current_tool_input, cwd=None, session_id=None):
    ok, events = read_jsonl_strict(transcript_path)
    if not ok:
        return False, "transcript unreadable or malformed"
    current_tool = {"type": "tool_use", "name": current_tool_name, "input": current_tool_input or {}}
    info, info_error = extract_spec_info(current_tool, cwd=cwd)
    if info_error or info is None:
        return False, info_error or "missing spec info"
    try:
        import codex_transcript_adapter as _codex
        if _codex._detect_runtime(transcript_path) == "codex":
            records = _codex.extract_spec_credit_records(transcript_path)
            return prior_verifier_credit(
                records, len(records), info, cwd=cwd, strict_jsonl=True)
    except Exception:
        pass
    records = flatten_records(current_turn(events))
    ok, reason = prior_verifier_credit(records, len(records), info, cwd=cwd, strict_jsonl=True)
    if ok:
        return True, reason
    # Fall back to flag-based cross-turn credit
    if session_id and info and info.get("hash"):
        flag_ok, flag_reason = check_verifier_pass_flags(session_id, info["hash"])
        if flag_ok:
            return True, flag_reason
    return False, reason


def verifier_dispatch_hash_error(tool_name, tool_input, cwd=None):
    tool = {"type": "tool_use", "name": tool_name, "input": tool_input or {}}
    info, info_error = extract_spec_info(tool, cwd=cwd)
    if info_error:
        return info_error
    if not current_spec_hash_matches(info):
        return "SPEC_SHA256 does not match current spec bytes"
    return None
