import hashlib
import importlib
import json
import os
import subprocess
from types import SimpleNamespace

import pytest


DANGEROUS_PERMISSION_MODES = {"bypassPermissions"}
DANGEROUS_FLAGS = {"--dangerously-skip-permissions"}


class FakeRun:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, cmd, **kwargs):
        self.calls.append((cmd, kwargs))
        if not self.responses:
            raise AssertionError("unexpected subprocess call: %r" % (cmd,))
        return self.responses.pop(0)


def proc(code=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)


@pytest.fixture()
def runner():
    return importlib.import_module("claude_coder_runner")


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def write_file(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def git_init(path):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def tool_use(tool_use_id, name="Agent", subagent_type=None, prompt="", description=""):
    inp = {"description": description, "prompt": prompt}
    if subagent_type is not None:
        inp["subagent_type"] = subagent_type
    return {"type": "tool_use", "id": tool_use_id, "name": name, "input": inp}


def assistant_event(*parts):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(parts)}}


def user_event(content):
    return {"type": "user", "message": {"role": "user", "content": content}}


def tool_result_event(tool_use_id, content):
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content}],
        },
    }


def write_transcript(path, events):
    with open(path, "w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
    return path


def span_digest(path, line_start, line_end):
    lines = path.read_text(encoding="utf-8").splitlines()
    return hashlib.sha256("\n".join(lines[line_start - 1:line_end]).encode("utf-8")).hexdigest()


def support_json(artifact_path, spec_hash, line_start=2, line_end=3, evidence_sha256=None):
    return json.dumps({
        "artifact_path": str(artifact_path),
        "line_start": line_start,
        "line_end": line_end,
        "evidence_sha256": evidence_sha256 or span_digest(artifact_path, line_start, line_end),
        "claim": "plan-check verifier reviewed this exact spec before Coder dispatch",
        "spec_sha256": spec_hash,
    }, sort_keys=True)


def plan_pass_body(spec_hash, support):
    return (
        "PLAN_SUPPORT_JSON=%s\n"
        "REVIEWED_SPEC_SHA256=%s\n"
        "LOOP_GATE: PLAN_PASS"
    ) % (support, spec_hash)


def coder_prompt(spec_path, spec_hash, classification="hardening-bugfix", repo="loop"):
    return (
        "REPO_HEALTH_CLASSIFICATION=%s\n"
        "REPO_HEALTH_REPO=%s\n"
        "SPEC: %s\n"
        "SPEC_SHA256=%s\n"
        "Implement as Coder."
    ) % (classification, repo, spec_path, spec_hash)


def verifier_prompt(spec_path, spec_hash):
    return "SPEC: %s\nSPEC_SHA256=%s\nReview exactly one spec." % (spec_path, spec_hash)


def valid_transcript(tmp_path, spec_path, spec_hash):
    support_artifact = write_file(
        tmp_path / "plan_check_log.md",
        "# plan check\nread spec bytes\napproved criteria\n",
    )
    events = [
        user_event("dispatch plan-check"),
        assistant_event(tool_use(
            "verifier-1",
            subagent_type="plan-check-verifier",
            prompt=verifier_prompt(spec_path, spec_hash),
            description="plan-check verifier for coder runner",
        )),
        tool_result_event("verifier-1", plan_pass_body(spec_hash, support_json(support_artifact, spec_hash))),
    ]
    return write_transcript(tmp_path / "transcript.jsonl", events)


def transcript_with_verifier_body(tmp_path, spec_path, spec_hash, body):
    events = [
        user_event("dispatch plan-check"),
        assistant_event(tool_use(
            "verifier-1",
            subagent_type="plan-check-verifier",
            prompt=verifier_prompt(spec_path, spec_hash),
            description="plan-check verifier for coder runner",
        )),
        tool_result_event("verifier-1", body),
    ]
    return write_transcript(tmp_path / "transcript.jsonl", events)


def valid_coder_output(extra=""):
    return (
        "Implemented the approved slice.\n\n"
        "DECISION LOG\n"
        "- Spec interpretation: keep Coder isolated behind the new launcher.\n"
        "- Assumptions: no production behavior beyond the launcher contract.\n\n"
        "CHANGED FILE SUMMARY\n"
        "- loop-team/harness/claude_coder_runner.py: added isolated runner.\n"
        "%s"
    ) % extra


def base_args(runner, tmp_path, spec_path, spec_hash, transcript_path, worktree, artifact_dir, extra=None):
    argv = [
        "--spec", str(spec_path),
        "--spec-sha256", spec_hash,
        "--transcript", str(transcript_path),
        "--coder-worktree", str(worktree),
        "--artifact-dir", str(artifact_dir),
        "--base-dir", str(tmp_path / "loop-checkout"),
        "--repo-health-classification", "hardening-bugfix",
        "--repo-health-repo", "loop",
        "--prompt", "Implement the approved spec.",
        "--token-file", str(tmp_path / "missing-token-file"),
        "--skip-auth-check",
    ]
    if extra:
        argv.extend(extra)
    return runner.make_parser().parse_args(argv)


def prepared_paths(tmp_path):
    base_dir = git_init(tmp_path / "loop-checkout")
    coder_worktree = git_init(tmp_path / "coder-worktree")
    spec = write_file(tmp_path / "spec.md", "# approved coder adapter spec\n")
    spec_hash = sha256_of(spec)
    transcript = valid_transcript(tmp_path, spec, spec_hash)
    artifact_dir = tmp_path / "artifacts"
    return base_dir, coder_worktree, spec, spec_hash, transcript, artifact_dir


@pytest.mark.parametrize("transcript_name", ["missing", "no_same_spec_credit"])
def test_missing_transcript_or_missing_same_spec_credit_blocks_before_subprocess(runner, tmp_path, transcript_name):
    _base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)
    if transcript_name == "missing":
        transcript = tmp_path / "missing.jsonl"
    else:
        transcript = write_transcript(tmp_path / "empty.jsonl", [user_event("no verifier credit here")])
    fake = FakeRun([])
    args = base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir)

    code, payload = runner.run_coder(args, run=fake)

    assert code != 0
    assert payload["ready"] is False
    assert fake.calls == []


@pytest.mark.parametrize("label,body_builder", [
    ("explicit PLAN_FAIL", lambda h, _a: "REVIEWED_SPEC_SHA256=%s\nLOOP_GATE: PLAN_FAIL" % h),
    ("missing REVIEWED_SPEC_SHA256", lambda h, a: "PLAN_SUPPORT_JSON=%s\nLOOP_GATE: PLAN_PASS" % support_json(a, h)),
    ("missing PLAN_SUPPORT_JSON", lambda h, _a: "REVIEWED_SPEC_SHA256=%s\nLOOP_GATE: PLAN_PASS" % h),
    ("invalid PLAN_SUPPORT_JSON", lambda h, _a: "PLAN_SUPPORT_JSON={not-json\nREVIEWED_SPEC_SHA256=%s\nLOOP_GATE: PLAN_PASS" % h),
])
def test_invalid_verifier_credit_shapes_block_before_subprocess(runner, tmp_path, label, body_builder):
    _base_dir, worktree, spec, spec_hash, _transcript, artifact_dir = prepared_paths(tmp_path)
    support_artifact = write_file(
        tmp_path / ("plan_check_log_for_%s.md" % label.replace(" ", "_")),
        "# log\nline two\nline three\n",
    )
    transcript = transcript_with_verifier_body(tmp_path, spec, spec_hash, body_builder(spec_hash, support_artifact))
    fake = FakeRun([])
    args = base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir)

    code, payload = runner.run_coder(args, run=fake)

    assert code != 0
    assert payload["ready"] is False
    assert fake.calls == []


def test_wrong_spec_hash_blocks_before_subprocess(runner, tmp_path):
    _base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)
    wrong_hash = "0" * 64
    fake = FakeRun([])
    args = base_args(runner, tmp_path, spec, wrong_hash, transcript, worktree, artifact_dir)

    code, payload = runner.run_coder(args, run=fake)

    assert code != 0
    assert payload["ready"] is False
    assert fake.calls == []
    assert wrong_hash != spec_hash


def test_changed_spec_bytes_block_before_subprocess(runner, tmp_path):
    _base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)
    spec.write_text("# approved coder adapter spec\nchanged after plan-check\n", encoding="utf-8")
    fake = FakeRun([])
    args = base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir)

    code, payload = runner.run_coder(args, run=fake)

    assert code != 0
    assert payload["ready"] is False
    assert fake.calls == []


def test_valid_same_spec_credit_calls_shared_gates_then_builds_claude_argv(runner, tmp_path, monkeypatch):
    _base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)
    order = []

    def fake_repo_gate(tool_name, tool_input, transcript_path, cwd=None):
        order.append("repo_gate")
        assert tool_name == "Agent"
        assert tool_input["subagent_type"] == "coder"
        text = "%s\n%s" % (tool_input["description"], tool_input["prompt"])
        assert "REPO_HEALTH_CLASSIFICATION=hardening-bugfix" in text
        assert "REPO_HEALTH_REPO=loop" in text
        assert "SPEC_SHA256=%s" % spec_hash in text
        assert os.path.realpath(str(transcript)) == os.path.realpath(str(transcript_path))
        return True, ""

    def fake_credit_gate(transcript_path, tool_name, tool_input, cwd=None):
        order.append("spec_credit")
        assert tool_name == "Agent"
        assert tool_input["subagent_type"] == "coder"
        assert "SPEC: %s" % spec in tool_input["prompt"]
        assert os.path.realpath(str(transcript)) == os.path.realpath(str(transcript_path))
        return True, ""

    monkeypatch.setattr(runner.repo_health_dispatch_gate, "authorize_dispatch", fake_repo_gate)
    monkeypatch.setattr(runner.spec_bound_verifier_credit, "authorize_coder_from_transcript", fake_credit_gate)
    fake = FakeRun([proc(0, valid_coder_output(), "")])
    args = base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir, extra=[
        "--model", "sonnet",
        "--permission-mode", "acceptEdits",
    ])

    code, payload = runner.run_coder(args, run=fake)

    assert code == 0
    assert payload["ready"] is True
    assert order == ["repo_gate", "spec_credit"]
    assert len(fake.calls) == 1
    cmd, kwargs = fake.calls[0]
    assert cmd[:2] == ["claude", "-p"]
    assert "--model" in cmd
    assert cmd[cmd.index("--model") + 1] == "sonnet"
    assert "--permission-mode" in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
    assert cmd[cmd.index("--permission-mode") + 1] not in DANGEROUS_PERMISSION_MODES
    assert "--add-dir" in cmd
    assert os.path.realpath(cmd[cmd.index("--add-dir") + 1]) == os.path.realpath(str(worktree))
    assert kwargs["cwd"] == str(worktree)


@pytest.mark.parametrize("worktree_case", ["same_checkout", "nested_protected_root", "missing", "non_git"])
def test_unsafe_coder_worktree_inputs_block_before_subprocess(runner, tmp_path, worktree_case):
    base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)
    if worktree_case == "same_checkout":
        worktree = base_dir
    elif worktree_case == "nested_protected_root":
        worktree = git_init(base_dir / "nested-coder")
    elif worktree_case == "missing":
        worktree = tmp_path / "missing-worktree"
    elif worktree_case == "non_git":
        worktree = tmp_path / "plain-dir"
        worktree.mkdir()
    fake = FakeRun([])
    args = base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir)

    code, payload = runner.run_coder(args, run=fake)

    assert code != 0
    assert payload["ready"] is False
    assert fake.calls == []


@pytest.mark.parametrize("extra", [
    ["--permission-mode", "bypassPermissions"],
    ["--", "--dangerously-skip-permissions"],
])
def test_dangerous_permission_modes_and_passthrough_flags_are_rejected(runner, tmp_path, extra):
    _base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)

    with pytest.raises(SystemExit):
        base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir, extra=extra)


@pytest.mark.parametrize("stdout", [
    "CHANGED FILE SUMMARY\n- loop-team/harness/claude_coder_runner.py: changed\n",
    "DECISION LOG\n- Assumption recorded.\nCHANGED FILE SUMMARY\n- no file path here\n",
])
def test_missing_or_malformed_decision_log_or_changed_file_summary_returns_non_ready(runner, tmp_path, stdout):
    _base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)
    fake = FakeRun([proc(0, stdout, "")])
    args = base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir)

    code, payload = runner.run_coder(args, run=fake)

    assert len(fake.calls) == 1
    assert code != 0
    assert payload["ready"] is False


def test_verifier_handoff_excludes_coder_private_reasoning_and_green_hints(runner, tmp_path):
    _base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)
    fake = FakeRun([proc(
        0,
        valid_coder_output(
            "\nRaw transcript: /tmp/coder-private-output.jsonl\n"
            "tests passed; green; previous VERDICT: PASS\n"
        ),
        "",
    )])
    args = base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir)

    code, payload = runner.run_coder(args, run=fake)

    assert code == 0
    handoff = payload["verifier_handoff"]
    review_dir = payload["review_artifact_dir"]
    assert str(spec) in handoff
    assert review_dir in handoff
    assert "Reviewable artifact directory: %s" % artifact_dir not in handoff
    assert review_dir != str(artifact_dir)
    assert os.path.isdir(review_dir)
    assert os.path.isfile(os.path.join(review_dir, "review_manifest.json"))
    assert os.path.isfile(os.path.join(review_dir, "verifier_handoff.md"))
    assert not os.path.exists(os.path.join(review_dir, "stdout.txt"))
    assert not os.path.exists(os.path.join(review_dir, "stderr.txt"))
    assert not os.path.exists(os.path.join(review_dir, "decision_log.txt"))
    for forbidden in [
        "DECISION LOG",
        "Raw transcript",
        "raw output",
        "stdout.txt",
        "stderr.txt",
        "decision_log.txt",
        "coder-private-output",
        "tests passed",
        "green",
        "VERDICT: PASS",
        "LOOP_GATE: PLAN_PASS",
    ]:
        assert forbidden.lower() not in handoff.lower()



def clear_auth_env(monkeypatch):
    for key in runner_auth_env_keys():
        monkeypatch.delenv(key, raising=False)


def runner_auth_env_keys():
    return ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN")


def write_token_file(path, token, mode=0o600):
    write_file(path, token)
    os.chmod(str(path), mode)
    return path


def artifact_texts(artifact_dir):
    texts = []
    for name in ("argv.json", "run.json", "stdout.txt", "stderr.txt", "decision_log.txt", "changed_file_summary.txt"):
        path = artifact_dir / name
        if path.exists():
            texts.append(path.read_text(encoding="utf-8"))
    return texts


def test_token_file_reaches_auth_status_and_claude_run_without_leaking(runner, tmp_path, monkeypatch):
    clear_auth_env(monkeypatch)
    _base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)
    sentinel = "sentinel-claude-oauth-token-12345"
    token_file = write_token_file(tmp_path / "claude-code-oauth-token", sentinel)
    fake = FakeRun([
        proc(0, json.dumps({"loggedIn": True, "echo": sentinel}), "auth stderr %s" % sentinel),
        proc(0, valid_coder_output("\nvisible token %s\n" % sentinel), "coder stderr %s" % sentinel),
    ])
    args = base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir)
    args.skip_auth_check = False
    args.token_file = str(token_file)

    code, payload = runner.run_coder(args, run=fake)

    assert code == 0
    assert payload["ready"] is True
    assert payload["auth_source"]["source"] == "token_file"
    assert len(fake.calls) == 2
    auth_cmd, auth_kwargs = fake.calls[0]
    coder_cmd, coder_kwargs = fake.calls[1]
    assert auth_cmd == ["claude", "auth", "status"]
    assert auth_kwargs["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == sentinel
    assert coder_kwargs["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == sentinel
    assert sentinel not in json.dumps(auth_cmd)
    assert sentinel not in json.dumps(coder_cmd)
    assert sentinel not in json.dumps(payload, sort_keys=True)
    assert all(sentinel not in text for text in artifact_texts(artifact_dir))
    assert "[REDACTED_CLAUDE_TOKEN]" in (artifact_dir / "stdout.txt").read_text(encoding="utf-8")
    assert "[REDACTED_CLAUDE_TOKEN]" in (artifact_dir / "stderr.txt").read_text(encoding="utf-8")
    run_json = json.loads((artifact_dir / "run.json").read_text(encoding="utf-8"))
    assert run_json["auth_preflight"]["echo"] == "[REDACTED_CLAUDE_TOKEN]"
    assert run_json["auth_preflight"]["stderr"] == "auth stderr [REDACTED_CLAUDE_TOKEN]"


@pytest.mark.parametrize("mode,text,error_fragment", [
    (0o644, "sentinel", "unsafe permissions"),
    (0o600, "\n", "empty"),
    (0o200, "sentinel", "cannot read"),
])
def test_token_file_blocks_when_unsafe_empty_or_unreadable(runner, tmp_path, monkeypatch, mode, text, error_fragment):
    clear_auth_env(monkeypatch)
    _base_dir, worktree, spec, spec_hash, transcript, artifact_dir = prepared_paths(tmp_path)
    token_file = write_token_file(tmp_path / "claude-code-oauth-token", text, mode)
    fake = FakeRun([])
    args = base_args(runner, tmp_path, spec, spec_hash, transcript, worktree, artifact_dir)
    args.token_file = str(token_file)

    code, payload = runner.run_coder(args, run=fake)

    assert code == 3
    assert payload["ready"] is False
    assert error_fragment in payload["error"]
    assert payload["auth_source"]["source"] == "token_file"
    assert fake.calls == []


def test_existing_auth_env_takes_precedence_over_unsafe_token_file_in_check(runner, tmp_path, monkeypatch, capsys):
    clear_auth_env(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "env-token-sentinel")
    token_file = write_token_file(tmp_path / "claude-code-oauth-token", "file-token-sentinel", 0o644)
    fake = FakeRun([proc(0, json.dumps({"loggedIn": True}), "")])

    code = runner.main(["--check", "--token-file", str(token_file)], run=fake)
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert code == 0
    assert payload["auth_source"] == {"source": "env", "env_var": "ANTHROPIC_AUTH_TOKEN"}
    assert payload["auth"]["auth_source"] == {"source": "env", "env_var": "ANTHROPIC_AUTH_TOKEN"}
    assert fake.calls[0][1]["env"]["ANTHROPIC_AUTH_TOKEN"] == "env-token-sentinel"
    assert "file-token-sentinel" not in output
    assert "env-token-sentinel" not in output


def test_check_reports_token_file_source_without_secret(runner, tmp_path, monkeypatch, capsys):
    clear_auth_env(monkeypatch)
    sentinel = "check-token-file-sentinel"
    token_file = write_token_file(tmp_path / "claude-code-oauth-token", sentinel)
    fake = FakeRun([proc(0, json.dumps({"loggedIn": True, "echo": sentinel}), "stderr %s" % sentinel)])

    code = runner.main(["--check", "--token-file", str(token_file)], run=fake)
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert code == 0
    assert payload["auth_source"]["source"] == "token_file"
    assert payload["auth"]["auth_source"]["source"] == "token_file"
    assert fake.calls[0][1]["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == sentinel
    assert sentinel not in output
    assert payload["auth"]["echo"] == "[REDACTED_CLAUDE_TOKEN]"
    assert payload["auth"]["stderr"] == "stderr [REDACTED_CLAUDE_TOKEN]"
