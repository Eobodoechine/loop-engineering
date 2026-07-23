"""Tests for loop-team/harness/evidence_ledger.py (Evidence-Gate Phase 5,
spec: loop-team/runs/2026-07-09_evidence-gate-phase5/specs/spec.md, Item 3
-- ACs 7-8, plus AC13's docstring requirement for this module).

Written BEFORE the implementation exists (evidence_ledger.py is not yet
built) -- importing it below is EXPECTED to fail with ModuleNotFoundError
until the Coder delivers, which fails the collection of this ENTIRE file
(matching hooks/test_closure_touch_scan.py's own already-established
precedent). That is correct per roles/test_writer.md's own header.

Self-contained (mirrors hooks/test_closure_touch_scan.py's stated
convention and this phase's own sibling test files): builds its own
fixture-building helpers rather than importing from
loop-team/harness/test_fixplan_closure_lint.py, styled after that file's own
already-proven conventions for building genuine Proof-block fixtures (real
snapshot files via the actual run_and_record.py CLI).

`build_ledger(content)` is tested UNIT-level, in-process (it is a pure
function of its one string argument, per the spec's own signature). The CLI
(`main(argv)`) is tested by invoking the real script as a subprocess,
matching fixplan_closure_lint.py's own established CLI-testing convention.

Run: python3 -m pytest loop-team/harness/test_evidence_ledger.py -q
"""
import ast
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import fixplan_closure_lint as lint  # noqa: E402 -- existing, real, Phase 1-4 shipped

import evidence_ledger  # noqa: E402 -- does not exist yet; see module docstring

RUN_AND_RECORD = os.path.join(HERE, "run_and_record.py")
LEDGER_SCRIPT = os.path.join(HERE, "evidence_ledger.py")


# ---------------------------------------------------------------------------
# Shared fixture-building helpers (self-contained; see module docstring).
# ---------------------------------------------------------------------------

def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _cutover_date():
    return date.fromisoformat(lint.PROOF_REQUIRED_SINCE)


def _on_or_after_cutover(days=0):
    return (_cutover_date() + timedelta(days=days)).isoformat()


def _closed_heading(id_text, date_str, note="some evidence"):
    return "%s -- some real fix -- CLOSED (%s, %s)" % (id_text, date_str, note)


def _proof_block(command, exit_code, proof_snapshot, verified_at=None, files=None):
    if verified_at is None:
        verified_at = "2026-07-09T00:00:00+00:00"
    lines = [
        "Proof:",
        "- command: %s" % command,
        "- exit_code: %s" % exit_code,
        "- proof_snapshot: %s" % proof_snapshot,
    ]
    if files:
        lines.append("- files: %s" % ", ".join(files))
    lines.append("- verified_at: %s" % verified_at)
    return "\n".join(lines) + "\n"


def _extract_proof_block_fields(remainder_text):
    fields = {}
    for m in re.finditer(r"^-\s*(\w+):\s*(.*)$", remainder_text, re.MULTILINE):
        fields[m.group(1)] = m.group(2).strip()
    return fields


def _make_real_snapshot(gate_dir, command_argv):
    env = dict(os.environ)
    env["LOOP_GATE_DIR"] = str(gate_dir)
    p = subprocess.run(
        [sys.executable, RUN_AND_RECORD, "--"] + list(command_argv),
        capture_output=True, text=True, timeout=30, env=env,
    )
    stdout = p.stdout.lstrip()
    _record, end = json.JSONDecoder().raw_decode(stdout)
    remainder = stdout[end:]
    fields = _extract_proof_block_fields(remainder)
    assert "proof_snapshot" in fields, (
        "run_and_record.py did not print a proof_snapshot line; "
        "stdout=%r stderr=%r" % (p.stdout, p.stderr)
    )
    return fields


def _run_ledger_cli(args, env, timeout=30):
    p = subprocess.run(
        [sys.executable, LEDGER_SCRIPT] + [str(a) for a in args],
        capture_output=True, text=True, timeout=timeout, env=env,
    )
    return p.returncode, p.stdout, p.stderr


# ---------------------------------------------------------------------------
# AC7 [BEHAVIORAL]: build_ledger() on a content with 2 CLOSED headings (one
# complete valid Proof block, one missing a Proof block entirely) returns
# exactly 1 ledger entry, with fields read directly from the parsed Proof
# block (never inferred/invented).
# ---------------------------------------------------------------------------

class TestAC7BuildLedgerReturnsExactlyOneEntryForTheCompleteProofBlock:
    def test_one_complete_and_one_missing_proof_block_yields_exactly_one_entry(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "ledger-ac7-real-evidence"])

        complete_heading = _closed_heading("H-LEDGER-AC7-COMPLETE-1", _on_or_after_cutover(0))
        complete_body = _proof_block(
            fields["command"], fields["exit_code"], fields["proof_snapshot"]
        )
        missing_heading = _closed_heading("H-LEDGER-AC7-MISSING-1", _on_or_after_cutover(0))
        missing_body = "\nSome closure prose, no Proof block at all.\n"

        content = "## %s\n%s\n## %s\n%s" % (
            complete_heading, complete_body, missing_heading, missing_body
        )

        entries = evidence_ledger.build_ledger(content)

        assert len(entries) == 1, entries
        entry = entries[0]
        assert entry["heading"] == complete_heading, entry
        assert entry["command"] == fields["command"], entry
        assert str(entry["exit_code"]) == str(fields["exit_code"]), entry
        assert entry["proof_snapshot"] == fields["proof_snapshot"], entry
        assert entry["verified_at"], entry
        assert entry["files"] == [], (
            "the AC7 fixture's Proof block cites no files (an `echo` command "
            "with no auto-detected files), so the ledger entry's own files "
            "list must be empty, not invented"
        )
        assert not any(e["heading"] == missing_heading for e in entries), entries

    def test_files_field_reflects_the_proof_blocks_own_cited_files(self, tmp_path):
        gate_dir = tmp_path / "gate"
        evidence_file = tmp_path / "ledger_evidence.txt"
        evidence_file.write_text("some evidence content\n", encoding="utf-8")
        fields = _make_real_snapshot(gate_dir, ["cat", str(evidence_file)])

        heading = _closed_heading("H-LEDGER-FILES-1", _on_or_after_cutover(0))
        body = _proof_block(
            fields["command"], fields["exit_code"], fields["proof_snapshot"],
            files=[str(evidence_file)],
        )
        content = "## %s\n%s" % (heading, body)

        entries = evidence_ledger.build_ledger(content)
        assert len(entries) == 1, entries
        assert isinstance(entries[0]["files"], list), entries
        assert any(str(evidence_file) in f for f in entries[0]["files"]), entries

    def test_build_ledger_preserves_heading_order_from_content(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields_1 = _make_real_snapshot(gate_dir, ["echo", "ledger-order-first"])
        fields_2 = _make_real_snapshot(gate_dir, ["echo", "ledger-order-second"])
        heading_1 = _closed_heading("H-LEDGER-ORDER-1", _on_or_after_cutover(0))
        heading_2 = _closed_heading("H-LEDGER-ORDER-2", _on_or_after_cutover(0))
        body_1 = _proof_block(fields_1["command"], fields_1["exit_code"], fields_1["proof_snapshot"])
        body_2 = _proof_block(fields_2["command"], fields_2["exit_code"], fields_2["proof_snapshot"])
        # heading_2 deliberately placed FIRST in content -- returned order
        # must follow content order, not fixture-construction order.
        content = "## %s\n%s\n## %s\n%s" % (heading_2, body_2, heading_1, body_1)

        entries = evidence_ledger.build_ledger(content)
        assert [e["heading"] for e in entries] == [heading_2, heading_1], entries


# ---------------------------------------------------------------------------
# AC8 [BEHAVIORAL]: the ledger CLI's output file is REPRODUCIBLE -- running
# it twice with no change to fix_plan.md produces byte-identical
# evidence_ledger.jsonl content.
# ---------------------------------------------------------------------------

class TestAC8LedgerOutputIsReproducibleAcrossRepeatedRuns:
    def test_build_ledger_is_a_pure_function_of_content_in_process(self, tmp_path):
        """In-process complement to the CLI-level test below: build_ledger()
        itself must be deterministic given identical input content."""
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "ledger-ac8-purity-check"])
        heading = _closed_heading("H-LEDGER-AC8-PURITY-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        content = "## %s\n%s" % (heading, body)

        entries_first = evidence_ledger.build_ledger(content)
        entries_second = evidence_ledger.build_ledger(content)
        assert entries_first == entries_second, (
            "build_ledger() must return identical output for identical input "
            "content -- it must be a pure function of content, not "
            "accumulating/drifting internal state"
        )

    def test_ledger_cli_output_file_byte_identical_across_two_runs(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "ledger-ac8-cli-evidence"])
        heading = _closed_heading("H-LEDGER-AC8-CLI-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        content = "## %s\n%s" % (heading, body)
        fix_plan_path = tmp_path / "fix_plan.md"
        _write(fix_plan_path, content)

        env = dict(os.environ)
        env["LOOP_GATE_DIR"] = str(gate_dir)

        code1, out1, err1 = _run_ledger_cli([str(fix_plan_path)], env)
        assert code1 == 0, "stdout=%r stderr=%r" % (out1, err1)
        ledger_path = gate_dir / "evidence_ledger.jsonl"
        assert ledger_path.is_file(), "expected evidence_ledger.jsonl to be written"
        content_after_run1 = ledger_path.read_bytes()
        assert content_after_run1, "expected a non-empty ledger file"

        code2, out2, err2 = _run_ledger_cli([str(fix_plan_path)], env)
        assert code2 == 0, "stdout=%r stderr=%r" % (out2, err2)
        content_after_run2 = ledger_path.read_bytes()

        assert content_after_run1 == content_after_run2, (
            "evidence_ledger.jsonl must be byte-identical across two runs "
            "with no change to fix_plan.md -- it must be a pure function of "
            "current file state, not accumulating/drifting"
        )

    def test_ledger_cli_output_is_valid_jsonl_matching_build_ledger_shape(self, tmp_path):
        gate_dir = tmp_path / "gate"
        fields = _make_real_snapshot(gate_dir, ["echo", "ledger-ac8-shape-evidence"])
        heading = _closed_heading("H-LEDGER-AC8-SHAPE-1", _on_or_after_cutover(0))
        body = _proof_block(fields["command"], fields["exit_code"], fields["proof_snapshot"])
        content = "## %s\n%s" % (heading, body)
        fix_plan_path = tmp_path / "fix_plan.md"
        _write(fix_plan_path, content)

        env = dict(os.environ)
        env["LOOP_GATE_DIR"] = str(gate_dir)

        code, out, err = _run_ledger_cli([str(fix_plan_path)], env)
        assert code == 0, "stdout=%r stderr=%r" % (out, err)
        ledger_path = gate_dir / "evidence_ledger.jsonl"
        lines = [l for l in ledger_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 1, lines
        record = json.loads(lines[0])
        assert record["heading"] == heading, record


# ---------------------------------------------------------------------------
# AC13 [DOC]: evidence_ledger.py's own module docstring documents its
# purpose and hash-only/no-re-execution / machine-derived guarantee.
# ---------------------------------------------------------------------------

class TestAC13ModuleDocstringDocumentsPurposeAndMachineDerivedGuarantee:
    def test_docstring_documents_machine_derived_not_hand_authored_guarantee(self):
        assert os.path.isfile(LEDGER_SCRIPT), "evidence_ledger.py does not exist yet"
        with open(LEDGER_SCRIPT, encoding="utf-8") as f:
            source = f.read()
        module_doc = ast.get_docstring(ast.parse(source))
        assert module_doc, "expected evidence_ledger.py to have a module docstring"
        lowered = module_doc.lower()
        assert "machine-derived" in lowered or "machine derived" in lowered, (
            "expected the docstring to document the machine-derived (never "
            "hand-authored second source of the same fact) guarantee -- the "
            "explicit 'Do NOT build' constraint this file exists to satisfy"
        )

    def test_docstring_documents_no_reexecution_guarantee(self):
        with open(LEDGER_SCRIPT, encoding="utf-8") as f:
            source = f.read()
        module_doc = ast.get_docstring(ast.parse(source))
        assert module_doc
        lowered = module_doc.lower()
        assert re.search(
            r"never re-execut|no re-execution|not re-execut|does not re-execute|hash", lowered
        ), (
            "expected the docstring to document the hash/parse-only, "
            "no-re-execution-of-cited-commands guarantee"
        )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
