"""Tests for repo_health_gate.py (spec: loop-team/runs/
2026-07-10_repo-health-gate/specs/spec.md, v5, all 5 plan-check rounds
passed/resolved).

Tier-1 test-writer note (per roles/test_writer.md's own header): this file is
written BEFORE `repo_health_gate.py` exists. Every test below is EXPECTED to
fail at COLLECTION time (`ModuleNotFoundError` on the top-level `import
repo_health_gate as gate`, matching test_fixplan_closure_lint.py's own
established `import fixplan_closure_lint as lint` convention) until the Coder
builds the module. That is correct and expected, not a defect in this file.

Convention matched directly from this repo's own test_fixplan_closure_lint.py
and run_and_record.py (per this dispatch's explicit instruction to read and
match those files' conventions rather than invent a different style):
  - pytest, `tmp_path` fixture for all synthetic on-disk fixtures.
  - a thin `_run_script()` subprocess wrapper mirroring `_run()`.
  - `--selftest` tested via a real subprocess with `LOOP_GATE_DIR` overridden
    to a tmp_path (mirrors test_fixplan_closure_lint.py's
    `TestPhase3AC3HeartbeatLogGrowsByExactlyOneLinePerInvocation`), asserting
    the heartbeat log grows by exactly one line per invocation.
  - plain-text/JSON substring and equality assertions on real stdout/stderr,
    not internal mocking.

=== Explicit ambiguity/design-decision flags (per test_writer.md's own
instruction: "do not silently downgrade" a genuinely ambiguous or
under-specified AC) ===

1. AC3 exception types: the spec's "Public interface" section documents that
   `load_ledger()` "Raises a specific, distinctly-typed exception for each
   malformed condition" but never NAMES the 3 exception classes anywhere (no
   class names appear in the spec text at all). A Tier-1 test-writer running
   before any implementation exists has nothing to import a name from without
   inventing implementation the Coder hasn't chosen yet -- which the role
   brief explicitly forbids ("no implementation in the test file"). Resolved
   by testing the STRUCTURAL promise directly and executably instead: (a)
   each malformed condition raises *some* Exception, (b) each exception's
   message names/identifies its own condition (substring checks, matching
   this repo's own established plain-text-message-assertion convention --
   see test_fixplan_closure_lint.py's "missing proof block" / "no matching
   proof snapshot found" checks), and (c) the three exceptions raised for the
   three DIFFERENT malformed conditions are of three MUTUALLY DISTINCT Python
   types (`TestAC3ThreeMalformedConditionsRaiseDistinctExceptionTypes`) --
   this directly operationalizes the word "distinctly-typed" without
   requiring foreknowledge of the Coder's chosen class names. Same reasoning
   applies to `apply_close`'s "Raises a specific exception if `entry_id` is
   not found, or if ... already 'closed'" -- note the spec's OWN wording here
   is singular ("a specific exception", not "a distinctly-typed exception for
   EACH condition" as load_ledger's clause says), so AC5's tests do NOT
   assert cross-case type distinctness for apply_close, only that each raises
   an Exception whose message content differentiates the two cases.
2. AC6 `--selftest` heartbeat log filename: the spec says this mode "reuses
   fixplan_closure_lint.py's heartbeat-log pattern" but never states the
   resulting log's literal filename for THIS tool (fixplan_closure_lint.py's
   own file is named `closure_lint_selftest.log`, not
   `<script_basename>_selftest.log` -- there is no single naming formula to
   mechanically transplant). Resolved by discovering the log file via a glob
   (`*selftest*.log`) under the overridden `LOOP_GATE_DIR`, asserting exactly
   one match exists, then applying the SAME "exactly one new line per
   invocation" check test_fixplan_closure_lint.py already established,
   whatever the Coder names the file.
3. AC10's CLI, as documented in "Public interface", has no ledger-PATH
   override flag at all (`repo_health_gate.py <repo-id>` / `--close <id>
   --reference "<text>"` / `--selftest` -- none take a path argument), yet
   AC10 requires driving `main()` against a `tmp_path`-COPY of the ledger,
   never the real file. The spec's own text supplies the mechanism needed to
   do this WITHOUT inventing an undocumented flag or monkeypatching a private
   symbol: "path resolved relative to the script's own location, matching
   fixplan_closure_lint.py's `_default_path()` convention" -- i.e. resolved
   via `os.path.dirname(os.path.abspath(__file__))`. So `_make_gate_copy()`
   below copies the real `repo_health_gate.py` script FILE (once it exists)
   alongside a copy of the ledger, both named identically to the real
   originals, into one fresh `tmp_path` directory -- invoking the COPIED
   script then resolves ITS OWN default ledger path to the co-located copy,
   through the exact same public, documented default-path mechanism the
   spec describes, with no private-symbol monkeypatching and no invented CLI
   flag.
4. LOOP-M3 (SECURITY-ORACLE labeling): none of this build's ACs describe a
   cross-tenant/adversarial/attacker-facing guarantee (this is an internal
   dev-tooling gate over the loop team's own ledger, not a multi-tenant
   security boundary) -- considered and explicitly not applied, rather than
   silently skipped without review.

AC8/AC9 are prose/doc deliverables (an `orchestrator.md` rule; a new
`fix_plan.md` entry) for the Coder, not `repo_health_gate.py` code -- no unit
test applies to either; see this dispatch's own report for that note.

Run: python3 -m pytest loop-team/harness/test_repo_health_gate.py -q
"""
import copy
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "repo_health_gate.py")
REAL_LEDGER_PATH = os.path.join(HERE, "hardening_ledger.json")

sys.path.insert(0, HERE)
import repo_health_gate as gate  # noqa: E402


# =============================================================================
# Shared fixture builders / helpers.
# =============================================================================

REQUIRED_FIELDS = (
    "id", "repo", "kind", "status", "basis", "description",
    "citation", "opened", "closed", "closing_reference",
)

VERDICT_KEYS = {
    "repo", "verdict", "open_item_count", "open_recurring_classes",
    "cited_entries_driving_verdict", "inferred_entries_driving_verdict",
    "reasoning",
}


def _entry(entry_id, repo, kind, status, basis="cited", **overrides):
    """Build one schema-shaped synthetic ledger entry (all 10 documented
    fields present) for in-memory `compute_verdict`/`apply_close` tests and
    for on-disk `load_ledger` fixture files. `status="closed"` fills
    `closed`/`closing_reference` with plausible defaults unless overridden."""
    entry = {
        "id": entry_id,
        "repo": repo,
        "kind": kind,
        "status": status,
        "basis": basis,
        "description": "synthetic test fixture entry for %s" % entry_id,
        "citation": "synthetic:test-fixture",
        "opened": "2026-01-01",
        "closed": None,
        "closing_reference": None,
    }
    if status == "closed":
        entry["closed"] = "2026-01-02"
        entry["closing_reference"] = "synthetic-prior-close-ref"
    entry.update(overrides)
    return entry


def _write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _assert_verdict_shape(verdict):
    assert set(verdict.keys()) == VERDICT_KEYS, (
        "verdict dict has an unexpected key set: %r (expected exactly %r)"
        % (set(verdict.keys()), VERDICT_KEYS)
    )
    assert verdict["verdict"] in ("FROZEN", "CLEAR")
    assert isinstance(verdict["open_item_count"], int)
    assert isinstance(verdict["open_recurring_classes"], list)
    assert isinstance(verdict["cited_entries_driving_verdict"], list)
    assert isinstance(verdict["inferred_entries_driving_verdict"], list)
    assert isinstance(verdict["reasoning"], str) and verdict["reasoning"].strip()


def _run_script(args, env=None, cwd=None, timeout=30):
    """Invoke the real CLI: python3 repo_health_gate.py <args...>."""
    run_env = dict(os.environ) if env is None else env
    p = subprocess.run(
        [sys.executable, SCRIPT] + list(args),
        capture_output=True, text=True, timeout=timeout, env=run_env, cwd=cwd,
    )
    return p.returncode, p.stdout, p.stderr


# =============================================================================
# AC1 [BEHAVIORAL]: FREEZE logic boundary cells, tested directly against
# compute_verdict() with synthetic in-memory entries.
# =============================================================================

class TestAC1FreezeLogicBoundaryCells:
    """I = open items for repo, C = open recurring classes for repo.
    I<=1 AND C==0 -> CLEAR. I>=2 -> FROZEN. C>=1 -> FROZEN. All four named
    boundary cells -- (0,0)/(1,0)/(2,0)/(0,1) -- plus (1,1)/(2,1) as
    non-contradiction checks. Every fixture also includes noise: one CLOSED
    item + one CLOSED recurring_class for the SAME repo (must not count
    toward I/C) and one OPEN item + one OPEN recurring_class for an
    UNRELATED other repo (must not leak into this repo's own I/C) -- so each
    cell also exercises correct per-repo scoping, not just raw counting."""

    def _noise(self, repo):
        return [
            _entry("NOISE-CLOSED-ITEM-1", repo, "item", "closed"),
            _entry("NOISE-CLOSED-CLASS-1", repo, "recurring_class", "closed"),
            _entry("OTHER-REPO-OPEN-ITEM-1", "some-other-repo", "item", "open"),
            _entry("OTHER-REPO-OPEN-CLASS-1", "some-other-repo", "recurring_class", "open"),
        ]

    def test_cell_0_0_clear(self):
        repo = "cell-0-0"
        entries = self._noise(repo)
        verdict = gate.compute_verdict(entries, repo)
        _assert_verdict_shape(verdict)
        assert verdict["repo"] == repo
        assert verdict["verdict"] == "CLEAR"
        assert verdict["open_item_count"] == 0
        assert verdict["open_recurring_classes"] == []

    def test_cell_1_0_clear(self):
        repo = "cell-1-0"
        entries = self._noise(repo) + [_entry("CELL-1-0-ITEM-1", repo, "item", "open")]
        verdict = gate.compute_verdict(entries, repo)
        _assert_verdict_shape(verdict)
        assert verdict["repo"] == repo
        assert verdict["verdict"] == "CLEAR"
        assert verdict["open_item_count"] == 1
        assert verdict["open_recurring_classes"] == []

    def test_cell_2_0_frozen(self):
        repo = "cell-2-0"
        entries = self._noise(repo) + [
            _entry("CELL-2-0-ITEM-1", repo, "item", "open"),
            _entry("CELL-2-0-ITEM-2", repo, "item", "open"),
        ]
        verdict = gate.compute_verdict(entries, repo)
        _assert_verdict_shape(verdict)
        assert verdict["repo"] == repo
        assert verdict["verdict"] == "FROZEN"
        assert verdict["open_item_count"] == 2
        assert verdict["open_recurring_classes"] == []

    def test_cell_0_1_frozen(self):
        repo = "cell-0-1"
        entries = self._noise(repo) + [
            _entry("CELL-0-1-CLASS-1", repo, "recurring_class", "open"),
        ]
        verdict = gate.compute_verdict(entries, repo)
        _assert_verdict_shape(verdict)
        assert verdict["repo"] == repo
        assert verdict["verdict"] == "FROZEN"
        assert verdict["open_item_count"] == 0
        assert verdict["open_recurring_classes"] == ["CELL-0-1-CLASS-1"]
        assert "CELL-0-1-CLASS-1" in verdict["reasoning"]

    def test_cell_1_1_non_contradiction_frozen(self):
        """I=1<=1 alone would be CLEAR; C=1>=1 must still force FROZEN."""
        repo = "cell-1-1"
        entries = self._noise(repo) + [
            _entry("CELL-1-1-ITEM-1", repo, "item", "open"),
            _entry("CELL-1-1-CLASS-1", repo, "recurring_class", "open"),
        ]
        verdict = gate.compute_verdict(entries, repo)
        _assert_verdict_shape(verdict)
        assert verdict["repo"] == repo
        assert verdict["verdict"] == "FROZEN", (
            "non-contradiction check for cell (1,1): C>=1 must dominate "
            "even though I=1 alone would be CLEAR"
        )
        assert verdict["open_item_count"] == 1
        assert verdict["open_recurring_classes"] == ["CELL-1-1-CLASS-1"]

    def test_cell_2_1_non_contradiction_frozen(self):
        """Both I>=2 and C>=1 independently require FROZEN -- neither
        condition should suppress or contradict the other."""
        repo = "cell-2-1"
        entries = self._noise(repo) + [
            _entry("CELL-2-1-ITEM-1", repo, "item", "open"),
            _entry("CELL-2-1-ITEM-2", repo, "item", "open"),
            _entry("CELL-2-1-CLASS-1", repo, "recurring_class", "open"),
        ]
        verdict = gate.compute_verdict(entries, repo)
        _assert_verdict_shape(verdict)
        assert verdict["repo"] == repo
        assert verdict["verdict"] == "FROZEN"
        assert verdict["open_item_count"] == 2
        assert verdict["open_recurring_classes"] == ["CELL-2-1-CLASS-1"]


# =============================================================================
# AC2 [BEHAVIORAL]: unknown repo -> CLEAR, empty lists, via compute_verdict
# directly -- proving cross-repo isolation (other, KNOWN repos are FROZEN in
# the same entries list, but must not leak into the unknown repo's verdict).
# =============================================================================

class TestAC2UnknownRepoIsClear:
    def test_unknown_repo_returns_clear_with_empty_lists(self):
        entries = [
            _entry("KNOWN-REPO-ITEM-1", "known-repo-a", "item", "open"),
            _entry("KNOWN-REPO-ITEM-2", "known-repo-a", "item", "open"),  # I=2 -> FROZEN for known-repo-a
            _entry("KNOWN-REPO-CLASS-1", "known-repo-b", "recurring_class", "open"),  # FROZEN for known-repo-b
        ]
        verdict = gate.compute_verdict(entries, "totally-unknown-repo-xyz")
        _assert_verdict_shape(verdict)
        assert verdict["repo"] == "totally-unknown-repo-xyz"
        assert verdict["verdict"] == "CLEAR"
        assert verdict["open_item_count"] == 0
        assert verdict["open_recurring_classes"] == []
        assert verdict["cited_entries_driving_verdict"] == []
        assert verdict["inferred_entries_driving_verdict"] == []

    def test_unknown_repo_against_completely_empty_ledger(self):
        verdict = gate.compute_verdict([], "another-unknown-repo")
        _assert_verdict_shape(verdict)
        assert verdict["verdict"] == "CLEAR"
        assert verdict["open_item_count"] == 0
        assert verdict["open_recurring_classes"] == []


# =============================================================================
# AC3 [BEHAVIORAL]: malformed ledger detection, via load_ledger() directly
# against tmp_path-written fixture files. See this file's own module
# docstring, ambiguity flag #1, for why exception TYPES are asserted via
# mutual distinctness rather than named classes.
# =============================================================================

class TestAC3InvalidJsonRaises:
    def test_invalid_json_raises_with_message_naming_the_json_problem(self, tmp_path):
        target = tmp_path / "ledger.json"
        target.write_text("{this is not valid json,,,", encoding="utf-8")

        with pytest.raises(Exception) as excinfo:
            gate.load_ledger(str(target))
        assert re.search(r"json", str(excinfo.value), re.IGNORECASE), (
            "expected the exception message to identify this as a JSON "
            "parsing problem; got: %r" % str(excinfo.value)
        )


class TestAC3MissingRequiredFieldRaises:
    """LOOP-M1 traversal-completeness: the schema's field set is a declared
    FINITE space (the 10 fields in the spec's own 'Public interface' JSON
    shape) -- parametrized over every one of them, not just a single
    representative field, so an implementation that only validates SOME
    fields cannot silently pass this AC."""

    @pytest.mark.parametrize("missing_field", REQUIRED_FIELDS)
    def test_missing_required_field_raises_naming_the_field(self, tmp_path, missing_field):
        entry = _entry("H-MISSING-%s-1" % missing_field.upper(), "some-repo", "item", "open")
        del entry[missing_field]
        target = tmp_path / "ledger.json"
        _write_json(target, [entry])

        with pytest.raises(Exception) as excinfo:
            gate.load_ledger(str(target))
        message = str(excinfo.value)
        assert missing_field in message or "missing" in message.lower(), (
            "expected the exception for a missing '%s' field to name the "
            "field and/or say 'missing'; got: %r" % (missing_field, message)
        )


class TestAC3DuplicateIdRaises:
    def test_duplicate_id_raises_naming_the_id(self, tmp_path):
        entries = [
            _entry("H-DUP-1", "repoA", "item", "open"),
            _entry("H-DUP-1", "repoB", "item", "open"),
        ]
        target = tmp_path / "ledger.json"
        _write_json(target, entries)

        with pytest.raises(Exception) as excinfo:
            gate.load_ledger(str(target))
        message = str(excinfo.value)
        assert "H-DUP-1" in message, (
            "expected the duplicate-id exception message to name the "
            "offending id; got: %r" % message
        )
        assert "duplicate" in message.lower()


class TestAC3ThreeMalformedConditionsRaiseDistinctExceptionTypes:
    """Directly operationalizes the spec's 'a specific, distinctly-typed
    exception for EACH malformed condition' without needing to know the
    Coder's chosen class names in advance (see module docstring, ambiguity
    flag #1)."""

    def test_invalid_json_missing_field_and_duplicate_id_raise_mutually_distinct_types(self, tmp_path):
        json_path = tmp_path / "invalid.json"
        json_path.write_text("not json at all {{{", encoding="utf-8")
        with pytest.raises(Exception) as json_exc:
            gate.load_ledger(str(json_path))

        missing_entry = _entry("H-MISSING-DISTINCT-1", "repoA", "item", "open")
        del missing_entry["citation"]
        missing_path = tmp_path / "missing.json"
        _write_json(missing_path, [missing_entry])
        with pytest.raises(Exception) as missing_exc:
            gate.load_ledger(str(missing_path))

        dup_entries = [
            _entry("H-DUP-DISTINCT-1", "repoA", "item", "open"),
            _entry("H-DUP-DISTINCT-1", "repoB", "item", "open"),
        ]
        dup_path = tmp_path / "dup.json"
        _write_json(dup_path, dup_entries)
        with pytest.raises(Exception) as dup_exc:
            gate.load_ledger(str(dup_path))

        types_seen = {type(json_exc.value), type(missing_exc.value), type(dup_exc.value)}
        assert len(types_seen) == 3, (
            "AC3 requires 'a specific, distinctly-typed exception for EACH "
            "malformed condition' -- got only %d distinct type(s) across 3 "
            "different conditions: %r" % (len(types_seen), types_seen)
        )


# =============================================================================
# AC4/AC5 [BEHAVIORAL]: apply_close() tested directly with in-memory lists
# and a literal fixed closed_date string (never the real wall clock).
# =============================================================================

class TestAC4ApplyCloseUpdatesOnlyMatchingEntry:
    def test_apply_close_updates_matching_entry_and_leaves_others_byte_identical(self):
        entries = [
            _entry("H-A-1", "repoX", "item", "open"),
            _entry("H-B-1", "repoX", "recurring_class", "open"),
            _entry("H-C-1", "repoY", "item", "open"),
        ]
        original_snapshot = copy.deepcopy(entries)
        fixed_closed_date = "2030-06-15"  # literal, deterministic -- never real wall clock

        result = gate.apply_close(entries, "H-B-1", "commit deadbee7", fixed_closed_date)

        # Input list itself must not be mutated in place.
        assert entries == original_snapshot
        assert result is not entries

        updated = next(e for e in result if e["id"] == "H-B-1")
        assert updated["status"] == "closed"
        assert updated["closed"] == fixed_closed_date
        assert updated["closing_reference"] == "commit deadbee7"

        for original_entry in original_snapshot:
            if original_entry["id"] == "H-B-1":
                continue
            matching = next(e for e in result if e["id"] == original_entry["id"])
            assert matching == original_entry, (
                "entry %r changed even though it was not the --close target: "
                "before=%r after=%r" % (original_entry["id"], original_entry, matching)
            )
        assert len(result) == len(original_snapshot)


class TestAC5ApplyCloseErrorPaths:
    def test_apply_close_on_nonexistent_id_raises_and_leaves_input_unmodified(self):
        entries = [_entry("H-EXIST-1", "repoX", "item", "open")]
        snapshot = copy.deepcopy(entries)

        with pytest.raises(Exception) as excinfo:
            gate.apply_close(entries, "H-DOES-NOT-EXIST-1", "ref", "2030-06-15")

        assert entries == snapshot, "the original input list must be unmodified"
        message = str(excinfo.value).lower()
        assert "h-does-not-exist-1" in message or "not found" in message, (
            "expected the not-found exception to identify the missing id "
            "and/or say 'not found'; got: %r" % str(excinfo.value)
        )

    def test_apply_close_on_already_closed_id_raises_and_leaves_input_unmodified(self):
        entries = [
            _entry(
                "H-CLOSED-1", "repoX", "item", "closed",
                closed="2029-01-01", closing_reference="prior-close-ref",
            ),
        ]
        snapshot = copy.deepcopy(entries)

        with pytest.raises(Exception) as excinfo:
            gate.apply_close(entries, "H-CLOSED-1", "new-ref", "2030-06-15")

        assert entries == snapshot, "the original input list must be unmodified"
        message = str(excinfo.value).lower()
        assert "already closed" in message or "already-closed" in message, (
            "expected the already-closed exception to say so explicitly; "
            "got: %r" % str(excinfo.value)
        )


# =============================================================================
# AC6 [BEHAVIORAL]: --selftest exercises all 3 pure functions with
# synthetic/temp fixtures, never opens the real hardening_ledger.json.
# =============================================================================

class TestAC6Selftest:
    def test_selftest_exits_zero_reports_pass_and_never_touches_real_ledger(self, tmp_path):
        assert os.path.isfile(REAL_LEDGER_PATH), (
            "expected the real, seeded hardening_ledger.json at %s (seeded "
            "as part of this same dispatch's AC7 data deliverable)" % REAL_LEDGER_PATH
        )
        real_ledger_before = Path(REAL_LEDGER_PATH).read_bytes()

        gate_dir = tmp_path / "gate"
        env = dict(os.environ)
        env["LOOP_GATE_DIR"] = str(gate_dir)

        code, out, err = _run_script(["--selftest"], env=env)

        real_ledger_after = Path(REAL_LEDGER_PATH).read_bytes()
        assert real_ledger_after == real_ledger_before, (
            "--selftest must never touch the real hardening_ledger.json"
        )
        assert code == 0, "stdout=%r stderr=%r" % (out, err)
        assert "PASS" in out

    def test_selftest_heartbeat_log_grows_by_exactly_one_line_per_invocation(self, tmp_path):
        gate_dir = tmp_path / "gate"
        env = dict(os.environ)
        env["LOOP_GATE_DIR"] = str(gate_dir)

        code1, out1, err1 = _run_script(["--selftest"], env=env)
        assert code1 == 0, "stdout=%r stderr=%r" % (out1, err1)

        log_matches = list(gate_dir.glob("*selftest*.log")) if gate_dir.is_dir() else []
        assert len(log_matches) == 1, (
            "expected exactly one *selftest*.log heartbeat file under %s "
            "after one --selftest invocation, found: %r" % (gate_dir, log_matches)
        )
        log_path = log_matches[0]
        before_lines = log_path.read_text(encoding="utf-8").splitlines()

        code2, out2, err2 = _run_script(["--selftest"], env=env)
        assert code2 == 0, "stdout=%r stderr=%r" % (out2, err2)
        after_lines = log_path.read_text(encoding="utf-8").splitlines()

        assert len(after_lines) - len(before_lines) == 1, (
            "expected the heartbeat log to gain EXACTLY one line per "
            "invocation; before=%r after=%r" % (before_lines, after_lines)
        )
        assert "PASS" in after_lines[-1]


# =============================================================================
# AC7 [BEHAVIORAL]: the real hardening_ledger.json (seeded by this dispatch
# itself, per its own explicit instruction), read-only, verdict-checked
# against compute_verdict() directly.
# =============================================================================

TAXAHEAD_FENCE_ID = "TAXAHEAD-FENCE-ENUM-INCOMPLETE-1"
PADSPLIT_FIXTURE_FLAKY_ID = "PADSPLIT-FIXTURE-FLAKY-SIBLINGS-1"
TIER_B_IDS = [
    "PADSPLIT-SHARED-DB-FRAGILITY-1",
    "PADSPLIT-ALLOWLIST-DRIFT-1",
    "PADSPLIT-UNVALIDATED-INGRESS-1",
]


class TestAC7RealSeededLedgerVerdicts:
    """Every test in this class is READ-ONLY against the real, seeded
    hardening_ledger.json -- never writes to it."""

    def test_real_ledger_file_is_valid_and_untouched_by_load(self):
        before = Path(REAL_LEDGER_PATH).read_bytes()
        entries = gate.load_ledger(REAL_LEDGER_PATH)
        after = Path(REAL_LEDGER_PATH).read_bytes()
        assert after == before, "load_ledger() must never write to the file it reads"
        assert isinstance(entries, list) and len(entries) >= 5
        seen_ids = [e["id"] for e in entries]
        assert len(seen_ids) == len(set(seen_ids)), "real seeded ledger must have unique ids"

    def test_taxahead_is_frozen_via_its_cited_recurring_class(self):
        entries = gate.load_ledger(REAL_LEDGER_PATH)
        verdict = gate.compute_verdict(entries, "taxahead")
        _assert_verdict_shape(verdict)
        assert verdict["verdict"] == "FROZEN"
        assert TAXAHEAD_FENCE_ID in verdict["open_recurring_classes"]
        assert TAXAHEAD_FENCE_ID in verdict["cited_entries_driving_verdict"]
        assert TAXAHEAD_FENCE_ID in verdict["reasoning"]

    def test_padsplit_cockpit_is_frozen_depending_on_inferred_tier_b_entries(self):
        entries = gate.load_ledger(REAL_LEDGER_PATH)
        verdict = gate.compute_verdict(entries, "padsplit-cockpit")
        _assert_verdict_shape(verdict)
        assert verdict["verdict"] == "FROZEN"
        for tier_b_id in TIER_B_IDS:
            assert tier_b_id in verdict["open_recurring_classes"]
            assert tier_b_id in verdict["inferred_entries_driving_verdict"]
        assert PADSPLIT_FIXTURE_FLAKY_ID in verdict["cited_entries_driving_verdict"]
        assert "inferred" in verdict["reasoning"].lower(), (
            "AC7 requires the reasoning to explicitly note dependence on an "
            "inferred-basis entry when the verdict depends on one; got: %r"
            % verdict["reasoning"]
        )

    def test_padsplit_cockpit_clears_once_the_3_tier_b_ids_are_filtered_out_in_memory(self):
        """Proves the dependency asserted above: removing ONLY the 3 Tier-B
        (inferred) entries, in memory, flips the verdict to CLEAR. The
        filtering happens on the in-memory list `load_ledger()` returned --
        never writes to the real file."""
        real_before = Path(REAL_LEDGER_PATH).read_bytes()

        entries = gate.load_ledger(REAL_LEDGER_PATH)
        filtered = [e for e in entries if e["id"] not in TIER_B_IDS]
        verdict = gate.compute_verdict(filtered, "padsplit-cockpit")
        _assert_verdict_shape(verdict)
        assert verdict["verdict"] == "CLEAR", (
            "removing the 3 Tier-B ids should leave only %s (I=1, C=0) for "
            "padsplit-cockpit, which must CLEAR per AC1's own I<=1 AND C==0 "
            "rule" % PADSPLIT_FIXTURE_FLAKY_ID
        )
        assert verdict["open_recurring_classes"] == []
        assert verdict["open_item_count"] == 1

        real_after = Path(REAL_LEDGER_PATH).read_bytes()
        assert real_after == real_before, (
            "this in-memory-filtering test must never write to the real "
            "hardening_ledger.json"
        )


# =============================================================================
# AC10 [BEHAVIORAL]: end-to-end main() test via tmp_path COPIES of the
# seeded ledger. See module docstring, ambiguity flag #3, for why a
# co-located script+ledger copy is used instead of an undocumented CLI flag
# or a monkeypatched private symbol.
# =============================================================================

def _make_gate_copy(tmp_path, ledger_bytes=None):
    """Copy the real repo_health_gate.py SCRIPT plus a ledger file (the real
    seeded ledger's bytes by default, or `ledger_bytes` if given) into a
    FRESH tmp_path directory as co-located siblings, named exactly
    'repo_health_gate.py' / 'hardening_ledger.json'. Returns
    (script_copy_path, ledger_copy_path) as pathlib.Path objects."""
    assert os.path.isfile(SCRIPT), "repo_health_gate.py does not exist yet"
    script_copy = tmp_path / "repo_health_gate.py"
    ledger_copy = tmp_path / "hardening_ledger.json"
    shutil.copy(SCRIPT, script_copy)
    if ledger_bytes is None:
        ledger_bytes = Path(REAL_LEDGER_PATH).read_bytes()
    ledger_copy.write_bytes(ledger_bytes)
    return script_copy, ledger_copy


def _run_copied_script(script_copy, args, timeout=30):
    p = subprocess.run(
        [sys.executable, str(script_copy)] + list(args),
        capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, p.stdout, p.stderr


class TestAC10aCloseWriteBackIsRealAndCorrect:
    def test_close_on_real_entry_writes_back_exactly_what_apply_close_would_produce(self, tmp_path):
        script_copy, ledger_copy = _make_gate_copy(tmp_path)
        original_entries = gate.load_ledger(str(ledger_copy))

        reference_text = "commit deadbee7 (AC10a synthetic close)"
        code, out, err = _run_copied_script(
            script_copy, ["--close", TAXAHEAD_FENCE_ID, "--reference", reference_text],
        )
        assert code == 0, "stdout=%r stderr=%r" % (out, err)

        # gate._today_iso() is the SAME real-wall-clock helper main() itself
        # calls for --close's date value (per the spec's own public
        # interface) -- calling it here, immediately after the subprocess
        # returns, is the same accepted real-wall-clock convention this
        # codebase already uses elsewhere (fixplan_closure_lint.py's own
        # _run_selftest() builds fixtures via its own _today_iso() at test
        # time); a UTC-midnight-boundary flake is a known, accepted risk of
        # that pre-existing pattern, not something newly introduced here.
        closed_date = gate._today_iso()
        expected = gate.apply_close(original_entries, TAXAHEAD_FENCE_ID, reference_text, closed_date)

        with open(ledger_copy, encoding="utf-8") as f:
            actual_on_disk = json.load(f)

        assert actual_on_disk == expected, (
            "the CLI's real --close write-back does not match what "
            "apply_close() itself would produce for the same inputs"
        )


class TestAC10bCloseErrorPathsLeaveCopyByteUnchanged:
    def test_close_on_nonexistent_id_exits_2_and_copy_is_unchanged(self, tmp_path):
        script_copy, ledger_copy = _make_gate_copy(tmp_path)
        before = ledger_copy.read_bytes()

        code, out, err = _run_copied_script(
            script_copy,
            ["--close", "NONEXISTENT-ID-DOES-NOT-EXIST-1", "--reference", "ref"],
        )
        assert code == 2, "stdout=%r stderr=%r" % (out, err)
        assert ledger_copy.read_bytes() == before

    def test_close_on_already_closed_id_exits_2_and_copy_is_unchanged(self, tmp_path):
        entries = gate.load_ledger(REAL_LEDGER_PATH)
        # Manufacture an already-closed entry for this sub-case -- none of
        # the real seeded entries are closed yet (all 5 are open).
        pre_closed = gate.apply_close(entries, TAXAHEAD_FENCE_ID, "prior-ref", "2020-01-01")
        script_copy, ledger_copy = _make_gate_copy(
            tmp_path, ledger_bytes=json.dumps(pre_closed).encode("utf-8"),
        )
        before = ledger_copy.read_bytes()

        code, out, err = _run_copied_script(
            script_copy, ["--close", TAXAHEAD_FENCE_ID, "--reference", "new-ref"],
        )
        assert code == 2, "stdout=%r stderr=%r" % (out, err)
        assert ledger_copy.read_bytes() == before


class TestAC10cPlainRepoIdPathMatchesComputeVerdict:
    def test_plain_repo_id_stdout_is_valid_json_matching_compute_verdict_and_exits_zero(self, tmp_path):
        script_copy, ledger_copy = _make_gate_copy(tmp_path)

        code, out, err = _run_copied_script(script_copy, ["padsplit-cockpit"])
        assert code == 0, "stdout=%r stderr=%r" % (out, err)

        printed = json.loads(out)  # must be valid JSON
        entries = gate.load_ledger(str(ledger_copy))
        expected = gate.compute_verdict(entries, "padsplit-cockpit")
        assert printed == expected


class TestAC10dMalformedLedgerThroughMainExitsTwo:
    """(d): a load_ledger-raising malformed ledger (duplicate id, one of
    AC3's malformed shapes) invoked through main() via BOTH the plain
    <repo-id> path and the --close path -- exit 2, stderr names the file
    path, and (for --close) the copy is byte-unchanged."""

    def _duplicate_id_ledger_bytes(self):
        entries = [
            _entry("H-AC10D-DUP-1", "some-repo", "item", "open"),
            _entry("H-AC10D-DUP-1", "some-other-repo", "item", "open"),
        ]
        return json.dumps(entries).encode("utf-8")

    def test_malformed_ledger_via_plain_repo_id_path_exits_2_and_names_the_file(self, tmp_path):
        script_copy, ledger_copy = _make_gate_copy(
            tmp_path, ledger_bytes=self._duplicate_id_ledger_bytes(),
        )

        code, out, err = _run_copied_script(script_copy, ["some-repo"])
        assert code == 2, "stdout=%r stderr=%r" % (out, err)
        assert str(ledger_copy) in err, (
            "expected stderr to name the malformed file's path (%s); got "
            "stderr=%r" % (ledger_copy, err)
        )

    def test_malformed_ledger_via_close_path_exits_2_names_the_file_and_leaves_copy_unchanged(self, tmp_path):
        script_copy, ledger_copy = _make_gate_copy(
            tmp_path, ledger_bytes=self._duplicate_id_ledger_bytes(),
        )
        before = ledger_copy.read_bytes()

        code, out, err = _run_copied_script(
            script_copy, ["--close", "H-AC10D-DUP-1", "--reference", "ref"],
        )
        assert code == 2, "stdout=%r stderr=%r" % (out, err)
        assert str(ledger_copy) in err, (
            "expected stderr to name the malformed file's path (%s); got "
            "stderr=%r" % (ledger_copy, err)
        )
        assert ledger_copy.read_bytes() == before


# =============================================================================
# AC8/AC9: no test here by design (see module docstring) -- these are
# prose/doc deliverables (an orchestrator.md rule; a new fix_plan.md entry)
# for the Coder, not repo_health_gate.py code under test.
# =============================================================================
