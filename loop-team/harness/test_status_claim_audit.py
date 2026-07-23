"""Tests for the v1 anti-false-status `fix_plan.md` status-claim audit.

These tests define the public behavior expected from
`loop-team/harness/status_claim_audit.py`. They are intentionally red before
the implementation exists. The gate is narrower than the older closure lint:
it audits touched status-claim spans plus their attached evidence spans, and
the manual CLI full sweep reports historical findings without blocking unless
`--strict` is requested.

Run:
    python3 -m pytest loop-team/harness/test_status_claim_audit.py -q
"""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "status_claim_audit.py"
RUN_AND_RECORD_SCRIPT = HERE / "run_and_record.py"


def _load_module():
    assert SCRIPT.exists(), "status_claim_audit.py must exist"
    spec = importlib.util.spec_from_file_location("status_claim_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_cli(args):
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
    )


def _key_for_record(record):
    key_material = {
        "command": record["command"],
        "exit_code": record["exit_code"],
        "output_sha256": record["output_sha256"],
        "files": record["files"],
        "dirty_at_capture": record["dirty_at_capture"],
    }
    return hashlib.sha256(json.dumps(key_material, sort_keys=True).encode("utf-8")).hexdigest()


def _snapshot(tmp_path, command, output, *, captured_at="2026-07-10T12:00:00+00:00",
              exit_code=0, files=None, aliases=None, current_schema=True,
              content_addressed=True):
    record = {
        "command": command.split(),
        "exit_code": exit_code,
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        "captured_at": captured_at,
        "output": output,
        "files": files or {},
        "dirty_at_capture": False,
    }
    if current_schema:
        record.update({
            "proof_schema_version": 1,
            "proof_producer": "loop-team/harness/run_and_record.py",
            "proof_key_algorithm": "run_and_record.v1",
        })
    if aliases:
        record.update(aliases)
    if content_addressed:
        proof_dir = tmp_path / "proof"
        proof_dir.mkdir(exist_ok=True)
        path = proof_dir / ("%s.json" % _key_for_record(record))
    else:
        path = tmp_path / ("proof-%s.json" % hashlib.sha256(command.encode()).hexdigest()[:12])
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def _proof(snapshot_path, command, *, exit_code=0, include_output_sha=True,
           verified_at="2026-07-10T12:00:00+00:00", field_overrides=None,
           current_schema=True):
    fields = {
        "command": command,
        "exit_code": str(exit_code),
        "proof_snapshot": str(snapshot_path),
        "verified_at": verified_at,
    }
    loaded = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    if current_schema:
        fields.update({
            "proof_schema_version": str(loaded.get("proof_schema_version", "")),
            "proof_producer": loaded.get("proof_producer", ""),
            "proof_key_algorithm": loaded.get("proof_key_algorithm", ""),
        })
    if include_output_sha:
        fields["output_sha256"] = loaded["output_sha256"]
        fields["captured_at"] = loaded["captured_at"]
    if field_overrides:
        fields.update(field_overrides)
    return "Proof:\n" + "\n".join("- %s: %s" % (k, v) for k, v in fields.items()) + "\n"


def _entry(heading, body="", proof=""):
    return "## %s\n%s%s\n" % (heading, body, proof)


def _audit(content, touched_ranges=None, **kwargs):
    mod = _load_module()
    return mod.audit_fix_plan_content(
        content,
        touched_ranges=touched_ranges,
        now="2026-07-10T13:00:00+00:00",
        **kwargs,
    )


def _all_findings(result):
    assert isinstance(result, dict), result
    return result.get("findings", [])


def _blocking(result):
    return [f for f in _all_findings(result) if f.get("blocking")]


def _touched_range(content, needle):
    start = content.index(needle)
    return [{"start": start, "end": start + len(needle)}]


def test_true_mechanical_closed_claim_with_relevant_parseable_proof_passes(tmp_path):
    snap = _snapshot(
        tmp_path,
        "python3 -m pytest hooks/test_loop_stop_guard.py -q",
        "1 passed in 0.12s\n",
    )
    content = _entry(
        "H-GOOD -- CLOSED (2026-07-10)",
        "Status: CLOSED. Tests passed for hooks/test_loop_stop_guard.py.\n\n",
        _proof(snap, "python3 -m pytest hooks/test_loop_stop_guard.py -q", include_output_sha=True),
    )
    result = _audit(content, _touched_range(content, "Status: CLOSED"))
    assert _blocking(result) == []


def test_narrative_command_looking_proof_without_parseable_block_blocks():
    content = _entry(
        "H-NARRATIVE (OPEN)",
        "Status: DONE. I ran `python3 -m pytest hooks/test_loop_stop_guard.py -q` "
        "and it passed, but this is only narrative text.\n",
    )
    result = _audit(content, _touched_range(content, "Status: DONE"))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "MISSING_PARSEABLE_EVIDENCE"


@pytest.mark.parametrize("command", ["true", "echo ok", "date", "pwd"])
def test_probe_only_commands_do_not_prove_implemented_claims(tmp_path, command):
    snap = _snapshot(tmp_path, command, "ok\n")
    content = _entry(
        "H-PROBE -- CLOSED (2026-07-10)",
        "Status: IMPLEMENTED for the stop-hook evidence gate.\n\n",
        _proof(snap, command),
    )
    result = _audit(content, _touched_range(content, "Status: IMPLEMENTED"))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "PROBE_ONLY"


def test_closure_lint_true_proof_without_relevant_refs_is_probe_only(tmp_path):
    command = "python3 loop-team/harness/run_and_record.py -- true"
    snap = _snapshot(tmp_path, command, "")
    content = _entry(
        "H-OLD-STYLE -- CLOSED (2026-07-10)",
        "Status: CLOSED after wiring status-claim validation.\n\n",
        _proof(snap, command),
    )
    result = _audit(content, _touched_range(content, "Status: CLOSED"))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "PROBE_ONLY"


@pytest.mark.parametrize("status_word", ["READY", "LIVE_SMOKE_PASS"])
def test_connector_ready_requires_live_smoke_not_build_clean_or_mocked(tmp_path, status_word):
    command = "npm run build"
    snap = _snapshot(tmp_path, command, "build clean; mocked connector tests passed\n")
    content = _entry(
        "H-CONNECTOR (OPEN)",
        "Connector status: %s for Dropbox with mocked tests and build-clean evidence.\n\n"
        % status_word,
        _proof(snap, command),
    )
    result = _audit(content, _touched_range(content, status_word))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "MISSING_LIVE_SMOKE"


def test_ready_to_paste_proof_format_does_not_require_live_smoke(tmp_path):
    command = "python3 -m pytest loop-team/harness/test_run_and_record.py -q"
    snap = _snapshot(tmp_path, command, "16 passed in 2.04s\n")
    content = _entry(
        "H-PROOF-FORMAT -- VERIFIED-MECHANICAL-SLICE (2026-07-11)",
        "The ready-to-paste Proof block now carries output_sha256.\n\n",
        _proof(snap, command),
    )

    result = _audit(content, _touched_range(content, "VERIFIED"))

    assert _blocking(result) == []


def test_phantom_closed_entry_with_no_evidence_blocks():
    content = _entry("H-PHANTOM -- CLOSED (2026-07-10)", "No proof.\n")
    result = _audit(content, _touched_range(content, "CLOSED"))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["claim"] == "CLOSED"


@pytest.mark.parametrize("phrase", ["Suite: GREEN", "tests passed", "all green", "harness is green"])
def test_green_test_claim_variants_require_relevant_proof_blocks(phrase):
    content = _entry("H-GREEN (OPEN)", "%s after the harness update.\n" % phrase)
    result = _audit(content, _touched_range(content, phrase))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["claim"].lower() == phrase.lower()


@pytest.mark.parametrize(
    "sentence",
    [
        "implemented in hooks/x.py",
        "fixed in hooks/x.py",
        "wired into orchestrator.md",
    ],
)
def test_sentence_level_implementation_claims_need_claim_specific_proof(sentence):
    content = _entry("H-SENTENCE (OPEN)", "The gate is %s.\n" % sentence)
    result = _audit(content, _touched_range(content, sentence))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "MISSING_PARSEABLE_EVIDENCE"


@pytest.mark.parametrize("word", ["[IMPLEMENTED]", "[DONE]", "[FIXED]", "[BUILT]", "[RESOLVED]"])
def test_bracketed_status_bullets_need_proof(word):
    content = _entry("H-BRACKET (OPEN)", "- %s stop-hook path added.\n" % word)
    result = _audit(content, _touched_range(content, word))
    assert len(_blocking(result)) == 1


def test_excluded_contexts_do_not_block():
    content = _entry(
        "H-EXCLUDED (OPEN)",
        "```text\nDONE here is example code, not status.\n```\n"
        "> CLOSED in a quoted prior report.\n"
        "Historical note: IMPLEMENTED was once claimed incorrectly.\n"
        "Example: READY would be unsafe here.\n"
        "Counterexample: tests passed as prose only.\n"
        "Do not claim: COMPLETE without evidence.\n",
    )
    result = _audit(content, touched_ranges=None, full_sweep=True)
    assert _blocking(result) == []


def test_instructional_implemented_is_prose_only_and_allowed_when_not_closure_ready_or_pass():
    content = _entry(
        "H-INSTRUCTION (OPEN)",
        "Implementation guidance: if a future Coder says IMPLEMENTED in a "
        "decision log, require evidence before closing.\n",
    )
    result = _audit(content, _touched_range(content, "IMPLEMENTED"))
    findings = _all_findings(result)
    assert findings
    assert findings[0]["classifier"] == "PROSE_ONLY"
    assert findings[0]["blocking"] is False


@pytest.mark.parametrize(
    "claim,command,output,expected",
    [
        (
            "Logging implementation DONE",
            "python3 -m pytest tests/test_logger_import.py -q",
            "1 passed; imported logger\n",
            "MISSING_FORCED_ERROR_READBACK",
        ),
        (
            "Checkpointing CLOSED",
            "test -f .checkpoint/state.json",
            "",
            "MISSING_INTERRUPT_RESUME_PROOF",
        ),
        (
            "Retry/idempotency FIXED",
            "python3 -m pytest tests/test_happy_path.py -q",
            "1 passed\n",
            "MISSING_FAILURE_RETRY_INVARIANT",
        ),
        (
            "Persistence ledger DONE",
            "python3 -m pytest tests/test_persistence_write_only.py -q",
            "record persisted; 1 passed\n",
            "MISSING_DURABLE_READBACK_NEGATIVE_CONTROL",
        ),
        (
            "Browser/UI VERIFIED",
            "curl -i http://localhost:3000/ui",
            "HTTP/1.1 200 OK\n",
            "MISSING_BROWSER_EVIDENCE",
        ),
    ],
)
def test_claim_specific_weak_proofs_block(tmp_path, claim, command, output, expected):
    snap = _snapshot(tmp_path, command, output)
    content = _entry("H-SPECIFIC (OPEN)", "%s.\n\n" % claim, _proof(snap, command))
    result = _audit(content, _touched_range(content, claim.split()[0]))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == expected


@pytest.mark.parametrize(
    "claim,command,output",
    [
        (
            "Logging implementation DONE",
            "python3 -m pytest tests/test_forced_error_log_readback.py -q",
            "forced error persisted; log read back by correlation id; 1 passed\n",
        ),
        (
            "Checkpointing CLOSED",
            "python3 -m pytest tests/test_interrupt_resume_checkpoint.py -q",
            "interrupted before checkpoint; resumed from checkpoint; 1 passed\n",
        ),
        (
            "Retry/idempotency FIXED",
            "python3 -m pytest tests/test_duplicate_failure_retry_invariant.py -q",
            "duplicate request suppressed; failure retried once; invariant held; 1 passed\n",
        ),
        (
            "Persistence ledger DONE",
            "python3 -m pytest tests/test_persistence_readback_negative_control.py -q",
            "write persisted; read back matched; negative control missed; 1 passed\n",
        ),
        (
            "Browser/UI VERIFIED",
            "npx playwright test tests/ui-status.spec.ts --trace on",
            "Playwright trace captured; screenshot saved; DOM assertion passed; 1 passed\n",
        ),
    ],
)
def test_claim_specific_strong_proofs_pass(tmp_path, claim, command, output):
    snap = _snapshot(tmp_path, command, output)
    content = _entry("H-SPECIFIC-PASS -- CLOSED (2026-07-10)", "%s.\n\n" % claim, _proof(snap, command))
    result = _audit(content, _touched_range(content, claim.split()[0]))
    assert _blocking(result) == []


def test_require_word_does_not_trigger_ui_browser_evidence(tmp_path):
    command = "python3 -m pytest loop-team/harness/test_status_claim_audit.py -q"
    snap = _snapshot(tmp_path, command, "1 passed in 0.20s\n")
    content = _entry(
        "H-REQUIRE -- CLOSED (2026-07-10)",
        "Status: VERIFIED; proof requires the current schema fields.\n\n",
        _proof(snap, command),
    )

    result = _audit(content, _touched_range(content, "VERIFIED"))

    assert _blocking(result) == []


def test_proof_block_filename_does_not_create_persistence_ledger_context(tmp_path):
    command = (
        "python3 -m pytest loop-team/harness/test_status_claim_audit.py "
        "loop-team/harness/test_evidence_ledger.py -q"
    )
    snap = _snapshot(tmp_path, command, "64 passed in 1.17s\n")
    content = _entry(
        "H-BOUNDED-SWEEP -- VERIFIED-MECHANICAL-SLICE (2026-07-11)",
        "Status: VERIFIED for bounded status audit.\n\n",
        _proof(snap, command),
    )

    result = _audit(content, _touched_range(content, "VERIFIED"))

    assert _blocking(result) == []


def test_evidence_ledger_test_name_in_verification_prose_does_not_create_persistence_context(tmp_path):
    command = (
        "python3 -m pytest loop-team/harness/test_status_claim_audit.py "
        "loop-team/harness/test_evidence_ledger.py -q"
    )
    snap = _snapshot(tmp_path, command, "64 passed in 1.17s\n")
    content = _entry(
        "H-BOUNDED-SWEEP -- VERIFIED-MECHANICAL-SLICE (2026-07-11)",
        "Status: VERIFIED for bounded status audit.\n"
        "Evidence: evidence-ledger/status pair returned 64 passed.\n\n",
        _proof(snap, command),
    )

    result = _audit(content, _touched_range(content, "VERIFIED"))

    assert _blocking(result) == []


def test_current_run_and_record_schema_with_output_sha256_and_captured_at_is_accepted(tmp_path):
    command = "python3 -m pytest hooks/test_subagent_stop_gate.py -q"
    output = "2 passed in 0.20s\n"
    snap = _snapshot(tmp_path, command, output)
    content = _entry(
        "H-SCHEMA -- CLOSED (2026-07-10)",
        "Status: VERIFIED for hooks/test_subagent_stop_gate.py.\n\n",
        _proof(snap, command, include_output_sha=True),
    )
    result = _audit(content, _touched_range(content, "VERIFIED"))
    assert _blocking(result) == []


def test_current_schema_missing_proof_producer_blocks(tmp_path):
    command = "python3 -m pytest hooks/test_subagent_stop_gate.py -q"
    snap = _snapshot(tmp_path, command, "2 passed in 0.20s\n")
    content = _entry(
        "H-MISSING-PRODUCER -- CLOSED (2026-07-10)",
        "Status: VERIFIED for hooks/test_subagent_stop_gate.py.\n\n",
        _proof(snap, command, field_overrides={"proof_producer": ""}),
    )

    result = _audit(content, _touched_range(content, "VERIFIED"))

    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "MISSING_PROOF_PROVENANCE"


def test_current_schema_wrong_producer_blocks(tmp_path):
    command = "python3 -m pytest hooks/test_subagent_stop_gate.py -q"
    snap = _snapshot(
        tmp_path,
        command,
        "2 passed in 0.20s\n",
        aliases={"proof_producer": "manual-json-writer"},
    )
    content = _entry(
        "H-WRONG-PRODUCER -- CLOSED (2026-07-10)",
        "Status: VERIFIED for hooks/test_subagent_stop_gate.py.\n\n",
        _proof(snap, command),
    )

    result = _audit(content, _touched_range(content, "VERIFIED"))

    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "MISSING_PROOF_PROVENANCE"


def test_current_schema_non_content_addressed_snapshot_path_blocks(tmp_path):
    command = "python3 -m pytest hooks/test_subagent_stop_gate.py -q"
    snap = _snapshot(
        tmp_path,
        command,
        "2 passed in 0.20s\n",
        content_addressed=False,
    )
    content = _entry(
        "H-WRONG-PATH -- CLOSED (2026-07-10)",
        "Status: VERIFIED for hooks/test_subagent_stop_gate.py.\n\n",
        _proof(snap, command),
    )

    result = _audit(content, _touched_range(content, "VERIFIED"))

    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "FABRICATED_EVIDENCE"


def test_stale_proof_snapshot_blocks_fresh_verified_claim(tmp_path):
    command = "python3 -m pytest hooks/test_subagent_stop_gate.py -q"
    snap = _snapshot(
        tmp_path,
        command,
        "2 passed in 0.20s\n",
        captured_at="2020-01-01T00:00:00+00:00",
    )
    content = _entry(
        "H-STALE -- CLOSED (2026-07-10)",
        "Status: VERIFIED for hooks/test_subagent_stop_gate.py.\n\n",
        _proof(snap, command, include_output_sha=True),
    )

    result = _audit(content, _touched_range(content, "VERIFIED"))

    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "STALE_EVIDENCE"


def test_logging_forced_error_persisted_without_readback_blocks(tmp_path):
    command = "python3 -m pytest tests/test_forced_error_log_readback.py -q"
    snap = _snapshot(tmp_path, command, "forced error persisted; 1 passed\n")
    content = _entry(
        "H-LOGGING-READBACK (OPEN)",
        "Logging implementation DONE.\n\n",
        _proof(snap, command),
    )

    result = _audit(content, _touched_range(content, "Logging implementation DONE"))

    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "MISSING_FORCED_ERROR_READBACK"


def test_legacy_schema_aliases_are_accepted(tmp_path):
    command = "python3 -m pytest hooks/test_loop_stop_guard.py -q"
    output = "3 passed in 0.20s\n"
    digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
    snap = _snapshot(
        tmp_path,
        command,
        output,
        aliases={"stdout_sha256": digest, "verified_at": "2026-07-10T12:00:00+00:00"},
    )
    content = _entry(
        "H-SCHEMA-OLD -- CLOSED (2026-07-10)",
        "Status: VERIFIED for hooks/test_loop_stop_guard.py.\n\n",
        _proof(
            snap,
            command,
            field_overrides={
                "snapshot_path": str(snap),
                "proof_snapshot": "",
                "captured_at": "2026-07-10T12:00:00+00:00",
                "stdout_sha256": digest,
            },
        ),
    )
    result = _audit(content, _touched_range(content, "VERIFIED"))
    assert _blocking(result) == []


@pytest.mark.parametrize(
    "blanked_field",
    ["proof_snapshot", "output_sha256", "captured_at", "command", "exit_code", "proof_producer"],
)
def test_blanking_evidence_fields_under_existing_claim_blocks(tmp_path, blanked_field):
    command = "python3 -m pytest hooks/test_loop_stop_guard.py -q"
    snap = _snapshot(tmp_path, command, "1 passed\n")
    overrides = {blanked_field: ""}
    content = _entry(
        "H-BLANK -- CLOSED (2026-07-10)",
        "Status: DONE for stop-hook coverage.\n\n",
        _proof(snap, command, include_output_sha=True, field_overrides=overrides),
    )
    result = _audit(content, _touched_range(content, "- %s:" % blanked_field))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] in (
        "MISSING_PARSEABLE_EVIDENCE",
        "INCOMPLETE_EVIDENCE",
        "MISSING_PROOF_PROVENANCE",
    )


def test_evidence_weakening_to_true_revalidates_existing_claim(tmp_path):
    command = "true"
    snap = _snapshot(tmp_path, command, "")
    content = _entry(
        "H-WEAKEN -- CLOSED (2026-07-10)",
        "Status: DONE for stop-hook coverage.\n\n",
        _proof(snap, command),
    )
    result = _audit(content, _touched_range(content, "- command: true"))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "PROBE_ONLY"


def test_touched_evidence_span_is_part_of_audited_unit_even_status_line_unchanged(tmp_path):
    content = _entry(
        "H-DELETE -- CLOSED (2026-07-10)",
        "Status: DONE for stop-hook coverage.\n\n",
        "",
    )
    result = _audit(content, _touched_range(content, "Status: DONE"))
    findings = _blocking(result)
    assert len(findings) == 1
    assert findings[0]["classifier"] == "MISSING_PARSEABLE_EVIDENCE"


def test_full_sweep_cli_default_reports_historical_findings_but_exits_zero(tmp_path):
    target = tmp_path / "fix_plan.md"
    target.write_text(_entry("H-HISTORICAL -- CLOSED (2026-07-10)", "No proof.\n"), encoding="utf-8")

    proc = _run_cli(["--path", str(target)])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "full_sweep"
    assert payload["findings"][0]["heading"].startswith("H-HISTORICAL")
    assert payload["findings"][0]["classifier"] == "MISSING_PARSEABLE_EVIDENCE"


def test_full_sweep_cli_strict_exits_nonzero_when_blocking_findings_exist(tmp_path):
    target = tmp_path / "fix_plan.md"
    target.write_text(_entry("H-HISTORICAL -- CLOSED (2026-07-10)", "No proof.\n"), encoding="utf-8")

    proc = _run_cli(["--path", str(target), "--strict"])

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["blocking_count"] == 1


def test_recent_headings_strict_reports_only_bounded_recent_findings(tmp_path):
    command = "python3 -m pytest loop-team/harness/test_status_claim_audit.py -q"
    snap = _snapshot(tmp_path, command, "54 passed in 0.31s\n")
    content = (
        _entry("H-OLD-BAD -- CLOSED (2026-01-01)", "No proof.\n")
        + _entry(
            "H-RECENT-GOOD -- CLOSED (2026-07-10)",
            "Status: VERIFIED for status audit.\n\n",
            _proof(snap, command),
        )
        + _entry("H-RECENT-BAD -- CLOSED (2026-07-11)", "No proof.\n")
    )
    target = tmp_path / "fix_plan.md"
    target.write_text(content, encoding="utf-8")

    proc = _run_cli(["--path", str(target), "--recent-headings", "2", "--strict"])

    assert proc.returncode == 1
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "recent_headings"
    assert payload["recent_headings"] == 2
    assert payload["blocking_count"] == 1
    headings = [f["heading"] for f in payload["findings"]]
    assert headings == ["H-RECENT-BAD -- CLOSED (2026-07-11)"]


def test_recent_headings_strict_ignores_older_bad_history_outside_window(tmp_path):
    command = "python3 -m pytest loop-team/harness/test_status_claim_audit.py -q"
    snap = _snapshot(tmp_path, command, "54 passed in 0.31s\n")
    content = (
        _entry("H-OLD-BAD -- CLOSED (2026-01-01)", "No proof.\n")
        + _entry(
            "H-RECENT-GOOD -- CLOSED (2026-07-10)",
            "Status: VERIFIED for status audit.\n\n",
            _proof(snap, command),
        )
    )
    target = tmp_path / "fix_plan.md"
    target.write_text(content, encoding="utf-8")

    proc = _run_cli(["--path", str(target), "--recent-headings", "1", "--strict"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["mode"] == "recent_headings"
    assert payload["recent_headings"] == 1
    assert payload["blocking_count"] == 0
    assert payload["findings"] == []


def test_hook_mode_with_no_touched_spans_does_not_block_on_historical_bad_claim(tmp_path):
    target = tmp_path / "fix_plan.md"
    target.write_text(_entry("H-HISTORICAL -- CLOSED (2026-07-10)", "No proof.\n"), encoding="utf-8")

    proc = _run_cli(["--path", str(target), "--hook-touched-json", "[]"])

    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["blocking_count"] == 0


def test_full_file_write_revalidates_only_changed_evidence_span_not_all_history(tmp_path):
    good_cmd = "python3 -m pytest hooks/test_loop_stop_guard.py -q"
    good_snap = _snapshot(tmp_path, good_cmd, "1 passed\n")
    bad_snap = _snapshot(tmp_path, "true", "")
    content = (
        _entry(
            "H-HISTORICAL -- CLOSED (2026-07-10)",
            "Status: DONE for older work.\n\n",
            _proof(good_snap, good_cmd),
        )
        + _entry(
            "H-CHANGED -- CLOSED (2026-07-10)",
            "Status: DONE for changed work.\n\n",
            _proof(bad_snap, "true"),
        )
    )
    changed_start = content.index("## H-CHANGED")
    result = _audit(content, [{"start": changed_start, "end": len(content), "tool": "Write"}])
    findings = _blocking(result)
    assert [f["heading"] for f in findings] == ["H-CHANGED -- CLOSED (2026-07-10)"]
    assert findings[0]["classifier"] == "PROBE_ONLY"


# ---------------------------------------------------------------------------
# Spec: loop-team/runs/2026-07-16_203920-status-audit-heading-granularity/
# specs/spec.md (REVIEWED_SPEC_SHA256=e1d904e0c8e58c635449bb8398f1e10999533d
# 03721c318886f697f1d5f47885) -- fixes HEADING_RE / _iter_blocks so a nested
# `### H-<id>` sub-entry becomes its own block instead of folding into the
# enclosing `##` parent's body. Tracked as fix_plan.md's
# H-STATUSAUDIT-HEADING-GRANULARITY-PLUS-RELEVANCE-DEADLOCK-1.
#
# These fixtures are modeled directly on REAL fix_plan.md content (main tree,
# as read 2026-07-16), not shapes invented to match whatever regex the Coder
# eventually writes:
#   - parent/child heading pair: `## H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-
#     WORKER-1 (IMPLEMENTED 2026-07-16, priority: HIGH) -- ...` (line 9299)
#     containing `### H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1
#     (IMPLEMENTED 2026-07-16, priority: URGENT ...) -- ...` (line 9363) --
#     the exact real two-heading-levels pair the spec's "Bug mechanism"
#     section cites as both confirmed live occurrences.
#   - the parent's unrelated "log file" mention is modeled on
#     `H-OGAGUARD-EXACTWORKER-AGENTID-NAMESPACE-MISMATCH-1`'s real prose
#     (lines 9482-9484: "...not the many synthetic ... rows the hook's own
#     test suite writes into this SAME shared log file..."; lines 9513-9514:
#     "...deliberately redacts payload VALUES ..., logs only
#     `payload_keys`...").
#   - the generic `### ` sub-header cluster in AC4's fixture quotes real
#     headings verbatim: `### atlanta-rental-scraper (holes are narrow;
#     skill is otherwise solid)` (line 72), `### career-finder (verifier
#     exists but isn't wired into the runtime path)` (line 78), `### How it
#     got past the plan-check Verifier and the test suite` (line 473, a
#     mid-entry narrative sub-header sitting between `### H-GUARD-2` and
#     `### H-GUARD-3`), and `### Worktree note -- \`fix-credit-gate-
#     agentid-concat\` is now fully superseded, not force-deleted` (line
#     8828, a standalone sub-header).
# ---------------------------------------------------------------------------


def _nested_parent_child_content(tmp_path):
    """Build a REAL two-heading-levels fixture: a `##` parent modeled on the
    real `H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1` entry (its own
    already-evidenced claim, plus an unrelated "log file" mention modeled on
    the real `H-OGAGUARD-EXACTWORKER-AGENTID-NAMESPACE-MISMATCH-1` prose)
    containing a nested `### H-<id>` child modeled on the real
    `H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1` entry, with its own
    separate, non-logging claim and its own separate (clean) proof.
    """
    parent_command = (
        "python3 -m pytest hooks/test_loop_stop_guard.py "
        "hooks/test_stopguard_blocked_dispatch.py "
        "hooks/test_verifier_hygiene_gate.py hooks/test_subagent_stop_gate.py "
        "hooks/test_spec_bound_verifier_credit.py hooks/test_pre_tool_use_oga_guard.py "
        "-q --tb=short"
    )
    parent_snap = _snapshot(tmp_path, parent_command, "658 passed, 2 skipped\n")
    child_command = "python3 -m pytest hooks/test_spec_bound_verifier_credit.py -q --tb=short"
    child_snap = _snapshot(tmp_path, child_command, "98 passed\n")

    parent = (
        "## H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1 (IMPLEMENTED "
        "2026-07-16, priority: HIGH) -- old bare plan-check PASS credit and "
        "unrelated in-flight worker identity no longer authorize protected "
        "Coder/worker actions\n\n"
        "Status: IMPLEMENTED for the structural plan-pass evidence guard.\n\n"
        "Checked `~/.loop-gate/oga_guard_debug.jsonl`, filtered to this real "
        "session -- not the many synthetic rows the hook's own test suite "
        "writes into this SAME shared log file, a separate, minor hygiene "
        "gap worth its own note sometime.\n\n"
        + _proof(parent_snap, parent_command)
        + "\n"
    )
    child = (
        "### H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1 (IMPLEMENTED "
        "2026-07-16, priority: URGENT -- currently blocks EVERY Coder "
        "dispatch, not a narrow case) -- `result_plan_pass_status_for_hash`'s "
        "new `gate_idx != len(lines) - 1` \"final line\" check runs before "
        "the glued-agentId tolerance it was deployed alongside\n\n"
        "Root cause, confirmed by direct invocation of the real function "
        "against the real transcript record: the harness glues its own "
        "`agentId:` trailer onto the gate line.\n\n"
        "Status: IMPLEMENTED for the usage-trailer tolerance fix.\n\n"
        + _proof(child_snap, child_command)
    )
    return parent + child


def test_touch_inside_nested_child_body_does_not_arm_or_reclassify_parent_claim(tmp_path):
    """AC1 [BEHAVIORAL]: a `##` parent containing a nested `### H-<id>`
    child -- touching content ONLY inside the child's own body must NOT arm
    or re-classify the parent's own (already-evidenced, unrelated) claim.

    Today, HEADING_RE only recognizes `## `, so the child folds into the
    parent's body span all the way through `_iter_blocks`; a touch anywhere
    inside the child arms the single merged block (`_block_armed`'s
    unconditional "touched text sits anywhere in the block" fallback), and
    the parent's already-clean claim gets re-classified using the merged
    context -- which still carries the parent's own unrelated "log file"
    mention -- wrongly flipping it to MISSING_FORCED_ERROR_READBACK even
    though nothing in the parent's own span was touched.
    """
    content = _nested_parent_child_content(tmp_path)
    touched = _touched_range(
        content,
        "Root cause, confirmed by direct invocation of the real function",
    )

    result = _audit(content, touched)

    assert _blocking(result) == [], (
        "touching only the child's own body must not re-arm or misclassify "
        "the parent's own already-evidenced claim: %r" % _blocking(result)
    )


def test_child_own_claim_classified_using_only_child_body_not_parent_log_mention(tmp_path):
    """AC2 [BEHAVIORAL]: the child's own claim, when armed, must be
    classified using ONLY the child's own body as context -- never the
    parent's. The parent body carries an unrelated "log file" mention
    (modeled on the real H-OGAGUARD-EXACTWORKER-AGENTID-NAMESPACE-MISMATCH-1
    prose); the child's own claim is non-logging.

    Today, a touch inside the child's own claim span still arms the single
    (buggy, merged) block, whose `_claim_context` is built from the WHOLE
    merged body -- including the parent's "log file" mention -- wrongly
    firing MISSING_FORCED_ERROR_READBACK for a claim that was never about
    logging at all.
    """
    content = _nested_parent_child_content(tmp_path)
    touched = _touched_range(content, "IMPLEMENTED for the usage-trailer tolerance fix")

    result = _audit(content, touched)
    findings = _blocking(result)

    assert not any(f["classifier"] == "MISSING_FORCED_ERROR_READBACK" for f in findings), (
        "the child's own non-logging claim must not inherit the parent's "
        "unrelated 'log file' mention into its classification context: %r" % findings
    )
    assert findings == [], (
        "the child's own claim is cleanly evidenced and non-logging; "
        "touching only its own claim span must produce no blocking "
        "finding at all: %r" % findings
    )


def _run_and_record_cli(args, env=None, cwd=None, timeout=30):
    """Invoke the REAL run_and_record.py CLI as a subprocess. Mirrors
    test_run_and_record.py's own `_run()` helper/convention exactly (same
    harness, same repo) per this spec's AC3 instruction to reuse that
    convention rather than fake a snapshot for the integration test below.
    """
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    proc = subprocess.run(
        [sys.executable, str(RUN_AND_RECORD_SCRIPT)] + list(args),
        capture_output=True, text=True, timeout=timeout, env=run_env, cwd=cwd,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _parse_real_run_and_record_stdout(stdout):
    """Mirrors test_run_and_record.py's own `_parse_record_and_snapshot_path`
    convention: the leading JSON record is followed by free-text Proof-block
    content (so a bare `json.loads(stdout)` would fail); use `raw_decode`
    and pull the `proof_snapshot:` path out of the remainder.
    """
    text = stdout.lstrip()
    record, end = json.JSONDecoder().raw_decode(text)
    remainder = text[end:]
    m = re.search(r"^-\s*proof_snapshot:\s*(.+)$", remainder, re.MULTILINE)
    assert m, "could not find a 'proof_snapshot:' line in stdout: %r" % stdout
    return record, m.group(1).strip()


def test_integration_real_run_and_record_snapshot_child_claim_not_misattributed_to_parent(tmp_path):
    """AC3 [BEHAVIORAL]: integration-level regression using a REAL
    run_and_record.py-produced snapshot -- a genuine subprocess invocation,
    real proof_schema_version/proof_producer/proof_key_algorithm/
    output_sha256 fields, confirmed NO fabricated 'output' text key (the
    real schema `run_and_record()` produces is proof_schema_version,
    proof_producer, proof_key_algorithm, command, exit_code, output_sha256,
    files, dirty_at_capture, captured_at -- nothing else) -- fed through the
    FULL `audit_fix_plan_content()` pipeline, not an isolated
    `_classify_relevance()` call.

    The child's own non-logging claim shares its pre-fix merged block with
    the parent's unrelated "log file" mention, which post-fix lives in a
    DIFFERENT, correctly-split block -- the exact compound
    heading-misattribution + logging-relevance false-trigger shape both real
    occurrences hit. Because a real run_and_record.py record has no output
    text at all, `_record_output_text` is always "" -- so whenever this
    false trigger wrongly fires, MISSING_FORCED_ERROR_READBACK is
    unconditional, not merely under-evidenced (spec's "Bug mechanism"
    section). Must not misfire post-fix.
    """
    gate_dir = tmp_path / "gate"
    code, out, err = _run_and_record_cli(
        ["--", sys.executable, "-m", "pytest", "--version"],
        env={"LOOP_GATE_DIR": str(gate_dir)},
        cwd=str(tmp_path),
    )
    assert code == 0, "real run_and_record.py invocation failed: stdout=%r stderr=%r" % (out, err)

    record, snapshot_path = _parse_real_run_and_record_stdout(out)
    assert "output" not in record, (
        "run_and_record.py's real record must never carry a fabricated "
        "'output' text key -- got keys: %r" % sorted(record.keys())
    )

    command_field = " ".join(record["command"])
    content = (
        "## H-STRUCTURAL-PLANPASS-EVIDENCE-EXACT-WORKER-1 (IMPLEMENTED "
        "2026-07-16, priority: HIGH) -- old bare plan-check PASS credit and "
        "unrelated in-flight worker identity no longer authorize protected "
        "Coder/worker actions\n\n"
        "Status: IMPLEMENTED for the structural plan-pass evidence guard.\n\n"
        "Checked `~/.loop-gate/oga_guard_debug.jsonl`, filtered to this real "
        "session -- not the many synthetic rows the hook's own test suite "
        "writes into this SAME shared log file, a separate, minor hygiene "
        "gap worth its own note sometime.\n\n"
        "### H-CREDITGATE-USAGE-TRAILER-STRUCTURAL-BLOCK-1 (IMPLEMENTED "
        "2026-07-16, priority: URGENT -- currently blocks EVERY Coder "
        "dispatch, not a narrow case) -- `result_plan_pass_status_for_hash`'s "
        "new `gate_idx != len(lines) - 1` \"final line\" check runs before "
        "the glued-agentId tolerance it was deployed alongside\n\n"
        "Status: IMPLEMENTED for the usage-trailer tolerance fix.\n\n"
        + _proof(snapshot_path, command_field)
    )

    touched = _touched_range(content, "IMPLEMENTED for the usage-trailer tolerance fix")
    result = _audit(content, touched)
    findings = _blocking(result)

    assert findings == [], (
        "the child's own non-logging claim, evidenced by a REAL "
        "run_and_record.py snapshot, must not be misclassified as "
        "MISSING_FORCED_ERROR_READBACK just because it currently (pre-fix) "
        "shares a merged block with the parent's unrelated log-file "
        "mention: %r" % findings
    )


def test_generic_prose_subheaders_do_not_orphan_parents_own_proof_block(tmp_path):
    """AC4 [BEHAVIORAL] -- forward guard, not a bug-reproduction test (see
    note at the end of this docstring). Generic `### ` prose sub-headers --
    covering the 3 real shapes found in fix_plan.md (a mid-entry narrative
    sub-header, a cluster of skill-name sub-headers under one audit section,
    and a standalone "Worktree note" style sub-header) -- must NOT become
    new block boundaries. A `##` parent whose own `Proof:` block sits
    textually AFTER several of these must still have that Proof: block
    correctly associated with it.

    Modeled on the real `### atlanta-rental-scraper (...)` / `### career-
    finder (...)` cluster (fix_plan.md lines 72/78), the real `### How it
    got past the plan-check Verifier and the test suite` mid-entry narrative
    sub-header (line 473, sitting between `### H-GUARD-2` and `### H-GUARD-
    3`), and the real `### Worktree note -- ...` standalone sub-header
    (line 8828) -- all quoted verbatim as headings below.

    Note on red/green status: unlike AC1-AC3, this scenario is NOT currently
    broken -- HEADING_RE today recognizes only `## `, so NOTHING currently
    splits on any `### ` line (generic or H-ID), and the parent's Proof:
    block is already found correctly as a result. This test pins down the
    spec's own explicit "Design constraint" warning: fixing AC1-AC3 by
    treating every `### ` line as a block boundary would silently introduce
    the OPPOSITE bug (orphaning a parent's own Proof: block behind a generic
    sub-header, producing a fresh MISSING_PARSEABLE_EVIDENCE false
    positive). This test is green against today's unfixed code and MUST STAY
    green after the fix -- it is a non-regression guard against an
    over-broad wrong fix, not a red-now reproduction of the reported bug.
    """
    command = "python3 -m pytest loop-team/harness/test_status_claim_audit.py -q"
    snap = _snapshot(tmp_path, command, "71 passed in 1.02s\n")
    body = (
        "Status: VERIFIED for the skills-audit reconciliation sweep.\n\n"
        "### atlanta-rental-scraper (holes are narrow; skill is otherwise solid)\n"
        "- [x] H-RENT-1 [DONE 2026-06-20 -- closed as C3 in the gate-semantics "
        "build below] -- Verifier only grades the URL it's handed; nothing "
        "checks whether a direct unit link was AVAILABLE but MISSED.\n\n"
        "### career-finder (verifier exists but isn't wired into the runtime path)\n"
        "- [ ] H-CAREER-8 -- SKILL.md Step 5 never invokes the independent "
        "verifier; it only has the writer self-attach a status tag instead of "
        "spawning an independent verifier.\n\n"
        "### How it got past the plan-check Verifier and the test suite\n"
        "The spec Verifier (pre-implementation) found two real bugs -- "
        "if/elif ordering, a broad verify regex. Both fixed. But it did not "
        "ask whether _VERIFIER_DETECT matches the dispatch labels Oga "
        "actually produces in practice.\n\n"
        "### Worktree note -- `fix-credit-gate-agentid-concat` is now fully "
        "superseded, not force-deleted\n"
        "The worktree held an uncommitted candidate fix for the "
        "agentId-concatenation bug; per git-safety practice it was not "
        "force-removed. The worktree is now redundant.\n\n"
    )
    content = _entry(
        "H-SKILLS-AUDIT-RECONCILE-1 -- VERIFIED (2026-06-20)",
        body,
        _proof(snap, command),
    )

    result = _audit(content, _touched_range(content, "Status: VERIFIED"))

    assert _blocking(result) == [], (
        "the parent's own armed claim must still find its Proof: block "
        "despite several generic ### sub-headers sitting between the claim "
        "and the proof: %r" % _blocking(result)
    )
