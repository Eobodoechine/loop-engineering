#!/usr/bin/env python3
"""Run the loop-team Coder role through Claude Code in a separate worktree."""
from __future__ import print_function

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_REPO_DIR = os.path.realpath(os.path.abspath(os.path.join(THIS_DIR, "..", "..")))
HOOKS_DIR = os.path.join(BASE_REPO_DIR, "hooks")
if HOOKS_DIR not in sys.path:
    sys.path.insert(0, HOOKS_DIR)

import repo_health_dispatch_gate  # noqa: E402
import spec_bound_verifier_credit  # noqa: E402


SAFE_PERMISSION_MODES = ("acceptEdits", "manual", "dontAsk", "plan")
DEFAULT_PERMISSION_MODE = "acceptEdits"
DEFAULT_MODEL = "sonnet"
DEFAULT_TOKEN_FILE = "~/.claude/claude-code-oauth-token"
AUTH_ENV_KEYS = ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
FILE_SUMMARY_RE = re.compile(r"^\s*-\s+[\w./-]+(?:/[\w./-]+)?\.[A-Za-z0-9][\w.-]*\s*:", re.M)


def _expand(path):
    return os.path.abspath(os.path.expanduser(str(path)))


def _real(path):
    return os.path.realpath(_expand(path))


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, sort_keys=True, indent=2)
        f.write("\n")


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text or "")



def _redact_text(text, secret_values):
    if text is None:
        return text
    redacted = str(text)
    for secret in secret_values:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED_CLAUDE_TOKEN]")
    return redacted


def _redact_obj(value, secret_values):
    if isinstance(value, dict):
        return {k: _redact_obj(v, secret_values) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_obj(v, secret_values) for v in value]
    if isinstance(value, str):
        return _redact_text(value, secret_values)
    return value


def _secret_values_from_env(env):
    return [env.get(name) for name in AUTH_ENV_KEYS if env.get(name)]


def build_claude_auth_env(token_file=DEFAULT_TOKEN_FILE, base_env=None):
    env = dict(os.environ if base_env is None else base_env)
    for key in AUTH_ENV_KEYS:
        if env.get(key):
            return env, {"source": "env", "env_var": key}, ""

    token_path = _expand(token_file)
    source = {"source": "none", "token_file": token_path}
    try:
        st = os.stat(token_path)
    except FileNotFoundError:
        return env, source, ""
    except OSError as exc:
        return None, source, "cannot inspect Claude token file %s: %s" % (token_path, exc)

    source = {"source": "token_file", "token_file": token_path}
    if not stat.S_ISREG(st.st_mode):
        return None, source, "Claude token file must be a regular file: %s" % token_path
    if st.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        return None, source, (
            "Claude token file has unsafe permissions: %s. Run: chmod 600 %s"
            % (token_path, token_path)
        )
    try:
        with open(token_path, "r", encoding="utf-8") as f:
            token = f.read().strip()
    except OSError as exc:
        return None, source, "cannot read Claude token file %s: %s" % (token_path, exc)
    if not token:
        return None, source, "Claude token file is empty: %s" % token_path

    env["CLAUDE_CODE_OAUTH_TOKEN"] = token
    return env, source, ""


def ensure_artifact_dir(path):
    artifact_dir = _expand(path)
    os.makedirs(artifact_dir, exist_ok=True)
    return artifact_dir


def review_artifact_dir_for(artifact_dir):
    parent = os.path.dirname(_real(artifact_dir))
    name = os.path.basename(_real(artifact_dir)).strip() or "claude-coder"
    review_dir = os.path.join(parent, "review-safe-%s" % name)
    os.makedirs(review_dir, exist_ok=True)
    return review_dir


def block_payload(reason, artifact_dir=None, extra=None):
    payload = {
        "ready": False,
        "ok": False,
        "error": reason,
    }
    if artifact_dir:
        payload["artifact_dir"] = artifact_dir
    if extra:
        payload.update(extra)
    return payload


def validate_spec(spec_path, expected_hash):
    if not SHA256_RE.match(expected_hash or ""):
        return None, "invalid SPEC_SHA256"
    spec = _real(spec_path)
    if not os.path.isfile(spec):
        return None, "spec is not a readable file"
    try:
        actual = file_sha256(spec)
    except OSError:
        return None, "spec is not a readable file"
    if actual != expected_hash:
        return None, "SPEC_SHA256 does not match current spec bytes"
    return spec, ""


def _is_nested_under(child, parent):
    try:
        return os.path.commonpath([child, parent]) == parent and child != parent
    except ValueError:
        return False


def validate_worktree(coder_worktree, protected_checkout):
    worktree = _real(coder_worktree)
    protected = _real(protected_checkout)
    if not os.path.isdir(worktree):
        return None, "coder worktree is not a readable directory"
    if not os.access(worktree, os.R_OK | os.X_OK):
        return None, "coder worktree is not readable"
    if worktree == protected:
        return None, "coder worktree must be distinct from protected checkout"
    if _is_nested_under(worktree, protected):
        return None, "coder worktree must not be nested under protected checkout"
    git_marker = os.path.join(worktree, ".git")
    if not os.path.exists(git_marker):
        return None, "coder worktree is not a git repo"
    return worktree, ""


def read_prompt(prompt, prompt_file):
    if prompt_file:
        with open(prompt_file, encoding="utf-8") as f:
            return f.read()
    return prompt or ""


def build_coder_dispatch(args, spec_path):
    prompt = "\n".join([
        "REPO_HEALTH_CLASSIFICATION=%s" % args.repo_health_classification,
        "REPO_HEALTH_REPO=%s" % args.repo_health_repo,
        "SPEC: %s" % spec_path,
        "SPEC_SHA256=%s" % args.spec_sha256,
        "",
        "You are the loop-team Coder. Implement only the approved spec.",
        "Return a DECISION LOG and CHANGED FILE SUMMARY.",
        "",
        read_prompt(args.prompt, args.prompt_file).strip(),
    ])
    return {
        "subagent_type": "coder",
        "description": "Claude-backed Coder dispatch",
        "prompt": prompt,
    }


def _foreground_credit_transcript(transcript_path, artifact_dir):
    ok, events = spec_bound_verifier_credit.read_jsonl_strict(transcript_path)
    if not ok:
        return None
    changed = False
    normalized = []
    for event in events:
        cloned = json.loads(json.dumps(event))
        message = cloned.get("message") if isinstance(cloned.get("message"), dict) else None
        parts = message.get("content") if isinstance(message, dict) else cloned.get("content")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, dict) or part.get("type") != "tool_use":
                    continue
                current = {"type": "tool_use", "name": part.get("name"), "input": part.get("input") or {}}
                inp = current["input"]
                if (
                    isinstance(inp, dict)
                    and "run_in_background" not in inp
                    and spec_bound_verifier_credit.is_verifier_dispatch(current)
                ):
                    inp["run_in_background"] = False
                    part["input"] = inp
                    changed = True
        normalized.append(cloned)
    if not changed:
        return None
    path = os.path.join(artifact_dir, "foreground_credit_transcript.jsonl")
    with open(path, "w", encoding="utf-8") as f:
        for event in normalized:
            f.write(json.dumps(event, sort_keys=True) + "\n")
    return path


def authorize_spec_credit_with_foreground_fallback(args, dispatch, artifact_dir):
    ok, reason = spec_bound_verifier_credit.authorize_coder_from_transcript(
        args.transcript, "Agent", dispatch, cwd=args.base_dir)
    decisions = [{
        "gate": "spec_bound_verifier_credit",
        "ok": bool(ok),
        "reason": reason,
        "transcript": _real(args.transcript) if args.transcript else args.transcript,
    }]
    if ok:
        return True, reason, decisions
    if reason != "no prior successful paired Verifier result reviewed this spec hash":
        return False, reason, decisions
    normalized = _foreground_credit_transcript(args.transcript, artifact_dir)
    if not normalized:
        return False, reason, decisions
    retry_ok, retry_reason = spec_bound_verifier_credit.authorize_coder_from_transcript(
        normalized, "Agent", dispatch, cwd=args.base_dir)
    decisions.append({
        "gate": "spec_bound_verifier_credit_foreground_normalized",
        "ok": bool(retry_ok),
        "reason": retry_reason,
        "transcript": normalized,
    })
    return retry_ok, retry_reason, decisions


def build_coder_prompt(args, spec_path, coder_worktree):
    role_path = os.path.join(_real(args.base_dir), "loop-team", "roles", "coder.md")
    return "\n".join([
        "You are acting as the loop-team Coder for Codex/Oga.",
        "",
        "Before editing, read the canonical Coder role file:",
        role_path,
        "",
        "Approved spec:",
        spec_path,
        "SPEC_SHA256=%s" % args.spec_sha256,
        "",
        "Coder worktree:",
        coder_worktree,
        "",
        "Hard constraints:",
        "- Edit only inside the Coder worktree.",
        "- Do not weaken tests.",
        "- Keep implementation minimal and scoped to the approved spec.",
        "- Your final response must contain a DECISION LOG section.",
        "- Your final response must contain a CHANGED FILE SUMMARY section with file paths.",
        "",
        "Delegation from Codex/Oga:",
        read_prompt(args.prompt, args.prompt_file).strip(),
        "",
    ])


def build_claude_command(args, coder_worktree, prompt_text):
    return [
        args.claude_bin,
        "-p",
        "--output-format", "text",
        "--model", args.model,
        "--permission-mode", args.permission_mode,
        "--add-dir", coder_worktree,
        prompt_text,
    ]


def claude_auth_status(claude_bin="claude", run=subprocess.run, env=None, auth_source=None):
    redact_values = _secret_values_from_env(env or os.environ)
    proc = run(
        [claude_bin, "auth", "status"],
        capture_output=True,
        text=True,
        env=env,
    )
    stdout = _redact_text(proc.stdout or "", redact_values)
    stderr = _redact_text(proc.stderr or "", redact_values)
    try:
        payload = json.loads(stdout or "{}")
    except ValueError:
        payload = {"raw_stdout": stdout}
    payload = _redact_obj(payload, redact_values)
    payload["exit_code"] = proc.returncode
    payload["stderr"] = stderr
    if auth_source is not None:
        payload["auth_source"] = auth_source
    return payload


def section_between(text, start_heading, end_heading=None):
    lines = (text or "").splitlines()
    start = None
    end = len(lines)
    for idx, line in enumerate(lines):
        if line.strip().upper() == start_heading:
            start = idx + 1
            break
    if start is None:
        return None
    if end_heading:
        for idx in range(start, len(lines)):
            if lines[idx].strip().upper() == end_heading:
                end = idx
                break
    return "\n".join(lines[start:end]).strip()


def parse_coder_output(stdout):
    decision_log = section_between(stdout, "DECISION LOG", "CHANGED FILE SUMMARY")
    changed_summary = section_between(stdout, "CHANGED FILE SUMMARY")
    if not decision_log:
        return None, None, "missing DECISION LOG"
    if not changed_summary:
        return None, None, "missing CHANGED FILE SUMMARY"
    if FILE_SUMMARY_RE.search(changed_summary) is None:
        return None, None, "CHANGED FILE SUMMARY has no file-path entries"
    return decision_log, changed_summary, ""


def verifier_handoff(spec_path, spec_hash, review_artifact_dir):
    return "\n".join([
        "Verifier handoff for Claude-backed Coder run",
        "",
        "Spec: %s" % spec_path,
        "Spec SHA256: %s" % spec_hash,
        "Review-safe artifact directory: %s" % review_artifact_dir,
        "",
        "Instructions:",
        "- Independently inspect the implementation against the spec.",
        "- Use only the review-safe artifacts referenced here.",
        "- Do not rely on Coder-private runner files or harness status summaries.",
        "- Form your own verdict from the artifact and commands you run.",
        "",
    ])


def persist_review_artifacts(review_artifact_dir, data):
    safe = {
        "spec": data.get("spec"),
        "spec_sha256": data.get("spec_sha256"),
        "coder_worktree": data.get("coder_worktree"),
        "status": data.get("status"),
    }
    write_json(os.path.join(review_artifact_dir, "review_manifest.json"), safe)
    if data.get("verifier_handoff") is not None:
        write_text(os.path.join(review_artifact_dir, "verifier_handoff.md"), data["verifier_handoff"])


def persist_run_artifacts(artifact_dir, data):
    write_json(os.path.join(artifact_dir, "argv.json"), data.get("argv", []))
    write_text(os.path.join(artifact_dir, "stdout.txt"), data.get("stdout", ""))
    write_text(os.path.join(artifact_dir, "stderr.txt"), data.get("stderr", ""))
    if data.get("decision_log") is not None:
        write_text(os.path.join(artifact_dir, "decision_log.txt"), data["decision_log"])
    if data.get("changed_file_summary") is not None:
        write_text(os.path.join(artifact_dir, "changed_file_summary.txt"), data["changed_file_summary"])
    if data.get("verifier_handoff") is not None:
        write_text(os.path.join(artifact_dir, "verifier_handoff.md"), data["verifier_handoff"])
    metadata = dict(data)
    for key in ("stdout", "stderr", "decision_log", "changed_file_summary", "verifier_handoff"):
        metadata.pop(key, None)
    write_json(os.path.join(artifact_dir, "run.json"), metadata)


def run_coder(args, run=subprocess.run):
    artifact_dir = ensure_artifact_dir(args.artifact_dir)
    review_artifact_dir = review_artifact_dir_for(artifact_dir)
    gate_decisions = []
    claude_env, auth_source, auth_error = build_claude_auth_env(args.token_file)
    if auth_error:
        payload = block_payload(auth_error, artifact_dir, {"auth_source": auth_source})
        persist_run_artifacts(artifact_dir, {
            "status": "blocked_external_setup",
            "reason": auth_error,
            "auth_source": auth_source,
            "gate_decisions": gate_decisions,
        })
        return 3, payload
    redact_values = _secret_values_from_env(claude_env)

    spec_path, spec_error = validate_spec(args.spec, args.spec_sha256)
    if spec_error:
        payload = block_payload(spec_error, artifact_dir)
        persist_run_artifacts(artifact_dir, {"status": "blocked", "reason": spec_error, "gate_decisions": gate_decisions})
        return 2, payload

    coder_worktree, worktree_error = validate_worktree(args.coder_worktree, args.base_dir)
    if worktree_error:
        payload = block_payload(worktree_error, artifact_dir)
        persist_run_artifacts(artifact_dir, {"status": "blocked", "reason": worktree_error, "gate_decisions": gate_decisions})
        return 2, payload

    dispatch = build_coder_dispatch(args, spec_path)
    repo_ok, repo_reason = repo_health_dispatch_gate.authorize_dispatch(
        "Agent", dispatch, args.transcript, cwd=args.base_dir)
    gate_decisions.append({"gate": "repo_health_dispatch_gate", "ok": bool(repo_ok), "reason": repo_reason})
    if not repo_ok:
        payload = block_payload(repo_reason or "repo health dispatch gate denied", artifact_dir,
                                {"gate_decisions": gate_decisions})
        persist_run_artifacts(artifact_dir, {"status": "blocked", "reason": payload["error"], "gate_decisions": gate_decisions})
        return 2, payload

    credit_ok, credit_reason, credit_decisions = authorize_spec_credit_with_foreground_fallback(
        args, dispatch, artifact_dir)
    gate_decisions.extend(credit_decisions)
    if not credit_ok:
        payload = block_payload(credit_reason or "same-spec verifier credit denied", artifact_dir,
                                {"gate_decisions": gate_decisions})
        persist_run_artifacts(artifact_dir, {"status": "blocked", "reason": payload["error"], "gate_decisions": gate_decisions})
        return 2, payload

    auth = {"skipped": True}
    if not args.skip_auth_check:
        auth = claude_auth_status(args.claude_bin, run=run, env=claude_env, auth_source=auth_source)
        if not auth.get("loggedIn"):
            payload = block_payload("claude_not_logged_in", artifact_dir, {
                "status": "blocked_external_setup",
                "auth_preflight": auth,
                "auth_source": auth_source,
                "gate_decisions": gate_decisions,
            })
            persist_run_artifacts(artifact_dir, {
                "status": "blocked_external_setup",
                "reason": "claude_not_logged_in",
                "auth_preflight": auth,
                "auth_source": auth_source,
                "gate_decisions": gate_decisions,
            })
            return 3, payload
    else:
        auth["auth_source"] = auth_source

    prompt_text = build_coder_prompt(args, spec_path, coder_worktree)
    argv = build_claude_command(args, coder_worktree, prompt_text)
    proc = run(
        argv,
        capture_output=True,
        text=True,
        cwd=coder_worktree,
        timeout=args.timeout,
        env=claude_env,
    )
    stdout = _redact_text(proc.stdout or "", redact_values)
    stderr = _redact_text(proc.stderr or "", redact_values)
    decision_log, changed_summary, contract_error = parse_coder_output(stdout)
    handoff = verifier_handoff(spec_path, args.spec_sha256, review_artifact_dir)

    ready = proc.returncode == 0 and not contract_error
    status = "ready" if ready else "non_ready"
    persist_run_artifacts(artifact_dir, {
        "status": status,
        "ready": ready,
        "argv": argv,
        "cwd": coder_worktree,
        "coder_worktree": coder_worktree,
        "protected_checkout": _real(args.base_dir),
        "review_artifact_dir": review_artifact_dir,
        "spec": spec_path,
        "spec_sha256": args.spec_sha256,
        "auth_preflight": auth,
        "auth_source": auth_source,
        "gate_decisions": gate_decisions,
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "decision_log": decision_log,
        "changed_file_summary": changed_summary,
        "contract_error": contract_error,
        "verifier_handoff": handoff,
    })
    persist_review_artifacts(review_artifact_dir, {
        "status": status,
        "spec": spec_path,
        "spec_sha256": args.spec_sha256,
        "coder_worktree": coder_worktree,
        "verifier_handoff": handoff,
    })
    payload = {
        "ready": ready,
        "ok": ready,
        "status": status,
        "exit_code": proc.returncode,
        "artifact_dir": artifact_dir,
        "review_artifact_dir": review_artifact_dir,
        "gate_decisions": gate_decisions,
        "auth_preflight": auth,
        "auth_source": auth_source,
        "contract_error": contract_error,
        "verifier_handoff": handoff,
    }
    return (0 if ready else 2), payload


def make_parser():
    parser = argparse.ArgumentParser(
        description="Run loop-team Coder via local Claude Code in a separate worktree."
    )
    parser.add_argument("--check", action="store_true",
                        help="Check Claude CLI auth and exit without dispatching Coder.")
    parser.add_argument("--spec", help="Approved spec path.")
    parser.add_argument("--spec-sha256", help="Expected SHA-256 of the approved spec bytes.")
    parser.add_argument("--transcript", help="Transcript containing same-spec Verifier credit.")
    parser.add_argument("--coder-worktree", help="Distinct git worktree Claude may edit.")
    parser.add_argument("--artifact-dir", help="Directory for runner artifacts.")
    parser.add_argument("--base-dir", default=BASE_REPO_DIR,
                        help="Protected loop checkout. Coder worktree must be distinct.")
    parser.add_argument("--repo-health-classification", required=False,
                        choices=("new-capability", "continuing-phase", "hardening-bugfix"))
    parser.add_argument("--repo-health-repo", required=False)
    parser.add_argument("--prompt", default="", help="Coder delegation prompt text.")
    parser.add_argument("--prompt-file", help="Read Coder delegation prompt from this file.")
    parser.add_argument("--claude-bin", default="claude")
    parser.add_argument("--token-file", default=DEFAULT_TOKEN_FILE,
                        help="Private Claude Code OAuth token file fallback.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--permission-mode", default=DEFAULT_PERMISSION_MODE,
                        choices=SAFE_PERMISSION_MODES)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--skip-auth-check", action="store_true",
                        help="Skip Claude auth preflight. Intended for tests only.")
    return parser


def _require_run_args(parser, args):
    required = (
        "spec", "spec_sha256", "transcript", "coder_worktree", "artifact_dir",
        "repo_health_classification", "repo_health_repo",
    )
    missing = [name for name in required if not getattr(args, name)]
    if missing:
        parser.error("missing required arguments: %s" % ", ".join("--" + n.replace("_", "-") for n in missing))


def main(argv=None, run=subprocess.run):
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.check:
        claude_env, auth_source, auth_error = build_claude_auth_env(args.token_file)
        if auth_error:
            print(json.dumps({"ok": False, "auth_source": auth_source, "error": auth_error}, sort_keys=True))
            return 2
        status = claude_auth_status(args.claude_bin, run=run, env=claude_env, auth_source=auth_source)
        ok = bool(status.get("loggedIn"))
        print(json.dumps({"ok": ok, "auth": status, "auth_source": auth_source}, sort_keys=True))
        return 0 if ok else 1
    _require_run_args(parser, args)
    code, payload = run_coder(args, run=run)
    print(json.dumps(payload, sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())
