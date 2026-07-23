"""Tests for `reconcile_gap_records.py`'s not-yet-implemented `--out <path>`
CLI flag (Tier 1 -- written BEFORE the Coder's implementation exists).

Spec: loop-team/runs/2026-07-09_reconcile-json-persistence/specs/spec.md

Covers acceptance criteria 1, 2, 3, and the task's item 4 (needs_human
3-shape reality lock-in). Reuses the real gap-28 (AC28 vs AC42) and
iteration-14 fixtures from `test_reconcile_gap_records.py` per that spec's
own precedent for real-incident data over invented fixtures, and matches
this suite's existing unittest.TestCase conventions.

Run with:
    python3 -m pytest loop-team/harness/test_reconcile_out_flag.py -v

EXPECTED STATUS BEFORE THE CODER'S CHANGE (documented here, not just in the
dispatch report, so a reader of this file alone knows what to expect):
  - `TestBackwardCompatibilityNoOutFlag` and `TestNeedsHumanThreeShapeReality`
    and `test_contradictions_pair_round_trips_as_two_element_array_via_spec_mechanism`
    target CURRENT, already-implemented code (`reconcile()` and the existing
    no---out CLI path) and are expected to PASS today -- these are the
    regression-protection baseline.
  - Every other test here invokes the not-yet-implemented `--out` flag (via
    real subprocess execution of the actual script) and is expected to FAIL
    until the Coder delivers it.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(HARNESS_DIR, "reconcile_gap_records.py")
sys.path.insert(0, HARNESS_DIR)

import reconcile_gap_records as rgr  # noqa: E402
import test_reconcile_gap_records as base  # noqa: E402 -- reuse real fixtures


def _run_cli(records, out_path=None, raw_stdin=None, timeout=30,
             barrier_state=None, allow_partial=False):
    """Invoke reconcile_gap_records.py as a REAL subprocess -- the actual
    public CLI interface -- mirroring the module's own __main__ contract
    (stdin JSON in, summary + exit code out, optionally --out <path>)."""
    args = [sys.executable, SCRIPT_PATH]
    if out_path is not None:
        args.extend(["--out", out_path])
    if barrier_state is not None:
        args.extend(["--barrier-state", barrier_state])
    if allow_partial:
        args.append("--allow-partial-barrier")
    stdin_text = raw_stdin if raw_stdin is not None else json.dumps(records)
    return subprocess.run(
        args, input=stdin_text, capture_output=True, text=True, timeout=timeout,
    )


def _write_barrier_state(tmpdir, payload):
    path = os.path.join(tmpdir, "lens_barrier_state.json")
    with open(path, "w") as f:
        json.dump(payload, f)
    return path


# ---------------------------------------------------------------------------
# Item 2 -- backward-compatibility regression baseline (pinned against the
# CURRENT, pre---out implementation; must keep passing after the Coder's
# change since D.1 requires --out to be purely additive).
# ---------------------------------------------------------------------------

class TestBackwardCompatibilityNoOutFlag(unittest.TestCase):
    """[BEHAVIORAL] Running the CLI WITHOUT --out must produce byte-identical
    stdout + exit code to the CURRENT implementation -- pinned by directly
    running the live, pre---out script (see this file's docstring for the
    exact captured values). PASSES today; must keep passing after the
    Coder's change (--out is purely additive, D.1)."""

    def test_iteration14_three_independent_records_stdout_and_exit_code(self):
        records = base._iteration14_three_independent_records()
        proc = _run_cli(records)
        self.assertEqual(
            proc.stdout,
            '{"merged_item_count": 3, "contradiction_count": 0, '
            '"needs_human_count": 0}\n',
        )
        self.assertEqual(proc.returncode, 0)

    def test_gap28_pair_stdout_and_exit_code(self):
        records = [base._gap28_ac28_record(), base._gap28_ac42_record()]
        proc = _run_cli(records)
        self.assertEqual(
            proc.stdout,
            '{"merged_item_count": 2, "contradiction_count": 0, '
            '"needs_human_count": 1}\n',
        )
        self.assertEqual(proc.returncode, 0)

    def test_empty_input_stdout_and_exit_code(self):
        proc = _run_cli([])
        self.assertEqual(
            proc.stdout,
            '{"merged_item_count": 0, "contradiction_count": 0, '
            '"needs_human_count": 0}\n',
        )
        self.assertEqual(proc.returncode, 0)

    def test_invalid_json_input_error_path_and_exit_code(self):
        proc = _run_cli(None, raw_stdin="not json")
        self.assertEqual(proc.stdout, '{"error": "invalid JSON input"}\n')
        self.assertEqual(proc.returncode, 2)


# ---------------------------------------------------------------------------
# AC1 -- --out flag: full ReconciliationResult round-trip via the real CLI
# ---------------------------------------------------------------------------

class TestOutFlagFullRoundTrip(unittest.TestCase):
    """[BEHAVIORAL] AC1: `--out <path>` persists the full ReconciliationResult
    (all 5 fields) as JSON, with every nested GapRecord's 8 fields intact.
    Uses the real gap-28 (AC28 vs AC42) fixture via the actual subprocess
    CLI."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.out_path = os.path.join(
            self.tmpdir.name, "gap_records_reconciled.json"
        )
        self.ac28 = base._gap28_ac28_record()
        self.ac42 = base._gap28_ac42_record()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_out_file_is_created(self):
        _run_cli([self.ac28, self.ac42], out_path=self.out_path)
        self.assertTrue(
            os.path.exists(self.out_path),
            "--out <path> must create the file at that path",
        )

    def test_out_file_is_valid_json_with_all_five_result_fields(self):
        _run_cli([self.ac28, self.ac42], out_path=self.out_path)
        with open(self.out_path) as f:
            data = json.load(f)  # raises if not valid JSON
        self.assertEqual(
            set(data.keys()),
            {
                "merged_items", "contradictions", "needs_human",
                "contradiction_log", "final_check",
            },
            "the persisted JSON must have exactly the 5 ReconciliationResult "
            "top-level fields, no more, no fewer",
        )

    def test_final_check_field_serializes_as_json_null(self):
        _run_cli([self.ac28, self.ac42], out_path=self.out_path)
        with open(self.out_path) as f:
            data = json.load(f)
        self.assertIsNone(
            data["final_check"],
            "final_check is currently always None in reconcile() and must "
            "be persisted as JSON null, not dropped (spec B/D.1)",
        )

    def test_nested_gap_record_has_all_8_fields_intact(self):
        _run_cli([self.ac28, self.ac42], out_path=self.out_path)
        with open(self.out_path) as f:
            data = json.load(f)
        found = None
        for item in data["merged_items"]:
            for rec in item.get("records", []):
                if rec.get("broken_assumption") == self.ac28["broken_assumption"]:
                    found = rec
        self.assertIsNotNone(
            found,
            "the AC28 GapRecord must be findable somewhere in "
            "merged_items[].records after round-tripping through --out JSON",
        )
        expected_fields = {
            "lens", "round", "gap_type", "broken_assumption",
            "why_it_fails", "proposed_fix", "touches", "mechanism_refs",
        }
        self.assertEqual(set(found.keys()), expected_fields)
        for field in expected_fields:
            self.assertEqual(
                found[field], self.ac28[field],
                "field %r must round-trip intact through --out JSON" % field,
            )

    def test_stdout_and_exit_code_unchanged_when_out_is_also_given(self):
        proc = _run_cli([self.ac28, self.ac42], out_path=self.out_path)
        self.assertEqual(
            proc.stdout,
            '{"merged_item_count": 2, "contradiction_count": 0, '
            '"needs_human_count": 1}\n',
            "the existing 3-key stdout summary must be identical whether or "
            "not --out is also passed (spec D.1: --out is purely additive)",
        )
        self.assertEqual(proc.returncode, 0)

    def test_out_flag_omitted_creates_no_file_at_all(self):
        # Confirms the file-write code path is not entered when --out is
        # omitted (D.1: "zero behavior change" when omitted).
        _run_cli([self.ac28, self.ac42])  # no out_path
        self.assertFalse(os.path.exists(self.out_path))


class TestBarrierStatePreflight(unittest.TestCase):
    """[BEHAVIORAL] Optional --barrier-state fails closed before reconcile.

    This is the mechanical bridge between the N-lens expected/completed-set
    barrier and the reconciliation CLI. Existing callers are unchanged when
    the flag is omitted.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.out_path = os.path.join(
            self.tmpdir.name, "gap_records_reconciled.json"
        )
        self.records = base._iteration14_three_independent_records()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_complete_barrier_preserves_existing_reconcile_behavior(self):
        barrier = _write_barrier_state(self.tmpdir.name, {
            "expected": ["regression-audit", "concurrency-isolation",
                         "state-completeness"],
            "completed": ["state-completeness", "regression-audit",
                          "concurrency-isolation"],
        })

        proc = _run_cli(self.records, out_path=self.out_path,
                        barrier_state=barrier)

        self.assertEqual(
            proc.stdout,
            '{"merged_item_count": 3, "contradiction_count": 0, '
            '"needs_human_count": 0}\n',
        )
        self.assertEqual(proc.returncode, 0)
        self.assertTrue(os.path.exists(self.out_path))

    def test_missing_lens_blocks_before_out_file_is_written(self):
        barrier = _write_barrier_state(self.tmpdir.name, {
            "expected": ["regression-audit", "concurrency-isolation",
                         "state-completeness"],
            "completed": ["regression-audit", "concurrency-isolation"],
        })

        proc = _run_cli(self.records, out_path=self.out_path,
                        barrier_state=barrier)
        payload = json.loads(proc.stdout)

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload["verdict"], "WAITING_FOR_RESULTS")
        self.assertEqual(payload["missing"], ["state-completeness"])
        self.assertFalse(
            os.path.exists(self.out_path),
            "reconcile --out must not write a merged file when a lens result "
            "is missing",
        )

    def test_retryable_lens_blocks_before_reconcile(self):
        barrier = _write_barrier_state(self.tmpdir.name, {
            "expected": ["regression-audit", "concurrency-isolation"],
            "completed": ["regression-audit"],
            "failed": ["concurrency-isolation"],
            "retry_counts": {"concurrency-isolation": 0},
        })

        proc = _run_cli(self.records, out_path=self.out_path,
                        barrier_state=barrier)
        payload = json.loads(proc.stdout)

        self.assertEqual(proc.returncode, 1)
        self.assertEqual(payload["verdict"], "WAITING_FOR_RETRY")
        self.assertEqual(payload["retryable"], ["concurrency-isolation"])
        self.assertFalse(os.path.exists(self.out_path))

    def test_partial_completion_is_nonzero_by_default(self):
        barrier = _write_barrier_state(self.tmpdir.name, {
            "expected": ["regression-audit", "concurrency-isolation"],
            "completed": ["regression-audit"],
            "abandoned": ["concurrency-isolation"],
        })

        proc = _run_cli(self.records, out_path=self.out_path,
                        barrier_state=barrier)
        payload = json.loads(proc.stdout)

        self.assertEqual(proc.returncode, 3)
        self.assertEqual(payload["verdict"], "PARTIAL_COMPLETION")
        self.assertFalse(os.path.exists(self.out_path))

    def test_partial_completion_can_be_explicitly_allowed(self):
        barrier = _write_barrier_state(self.tmpdir.name, {
            "expected": ["regression-audit", "concurrency-isolation"],
            "completed": ["regression-audit"],
            "abandoned": ["concurrency-isolation"],
        })

        proc = _run_cli(self.records, out_path=self.out_path,
                        barrier_state=barrier, allow_partial=True)

        self.assertEqual(proc.returncode, 0)
        self.assertIn('"merged_item_count": 3', proc.stdout)
        self.assertTrue(os.path.exists(self.out_path))


# ---------------------------------------------------------------------------
# AC3 -- --out given an unwritable path must fail LOUDLY
# ---------------------------------------------------------------------------

class TestOutFlagUnwritablePathFailsLoudly(unittest.TestCase):
    """[BEHAVIORAL] AC3: --out pointed at an unwritable path (missing parent
    directory, or no permissions) must fail loudly (non-zero exit, visible
    error) -- never silently succeed or silently drop the write, per D.1's
    explicit fail-loud convention (no missing-parent-dir auto-creation)."""

    def setUp(self):
        self.records = [base._gap28_ac28_record(), base._gap28_ac42_record()]

    def test_missing_parent_directory_exits_nonzero(self):
        bogus_path = "/this/parent/directory/does/not/exist/out.json"
        proc = _run_cli(self.records, out_path=bogus_path)
        self.assertNotEqual(
            proc.returncode, 0,
            "a missing --out parent directory must exit non-zero, not "
            "silently succeed with exit 0",
        )

    def test_missing_parent_directory_produces_visible_error_not_silence(self):
        bogus_path = "/this/parent/directory/does/not/exist/out.json"
        proc = _run_cli(self.records, out_path=bogus_path)
        self.assertTrue(
            proc.stderr.strip(),
            "a missing --out parent directory must produce a visible error "
            "on stderr (a raised, uncaught exception per D.1), not fail "
            "silently with empty stderr",
        )

    def test_missing_parent_directory_does_not_create_a_stray_file(self):
        bogus_path = "/this/parent/directory/does/not/exist/out.json"
        _run_cli(self.records, out_path=bogus_path)
        self.assertFalse(
            os.path.exists(bogus_path),
            "a failed --out write must not leave a partial/stray file behind",
        )

    def test_existing_but_unwritable_directory_exits_nonzero(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("running as root -- permission bits are not enforced")
        with tempfile.TemporaryDirectory() as d:
            os.chmod(d, stat.S_IREAD | stat.S_IEXEC)
            try:
                path = os.path.join(d, "out.json")
                proc = _run_cli(self.records, out_path=path)
                self.assertNotEqual(
                    proc.returncode, 0,
                    "--out pointed into a directory with no write "
                    "permission must fail loudly (non-zero exit), not "
                    "silently succeed",
                )
            finally:
                os.chmod(d, stat.S_IRWXU)  # restore so tempdir cleanup works


# ---------------------------------------------------------------------------
# Item 4 -- needs_human 3-shape reality (only the tie-breaker-dispatched
# shape carries a "lenses" key). Targets reconcile() directly (unchanged
# code) -- regression-protection, expected to PASS today.
# ---------------------------------------------------------------------------

class TestNeedsHumanThreeShapeReality(unittest.TestCase):
    """[BEHAVIORAL] Locks in the documented needs_human 3-shape reality
    (spec section B): only shape 2 (the tie-breaker-dispatched / tracer-
    CONTRADICTORY shape) carries a top-level "lenses" key; shape 1 (no
    tracer at all) and shape 3 (INCONCLUSIVE/unrecognized trace verdict) do
    not. Targets reconcile() directly (already-existing, unchanged code) --
    PASSES today and must keep passing after the Coder's change, guarding
    this documented behavior from silently breaking."""

    def setUp(self):
        self.ac28 = base._gap28_ac28_record()
        self.ac42 = base._gap28_ac42_record()

    def test_shape1_no_tracer_at_all_has_pair_but_no_lenses_key(self):
        result = rgr.reconcile([self.ac28, self.ac42])
        self.assertEqual(len(result.needs_human), 1)
        entry = result.needs_human[0]
        self.assertIn("pair", entry)
        self.assertNotIn(
            "lenses", entry,
            "shape 1 (no mechanism_tracer injected at all) must NOT carry "
            "a top-level 'lenses' key",
        )

    def test_shape2_tracer_contradictory_no_tie_breaker_has_lenses_key(self):
        tracer = base.RecordingMechanismTracer(verdict="CONTRADICTORY")
        result = rgr.reconcile(
            [self.ac28, self.ac42], round=16, mechanism_tracer=tracer,
        )
        self.assertEqual(len(result.needs_human), 1)
        entry = result.needs_human[0]
        self.assertIn(
            "lenses", entry,
            "shape 2 (tracer CONTRADICTORY, appended unconditionally when "
            "no tie_breaker was injected) is the ONLY needs_human shape "
            "documented to carry a top-level 'lenses' key",
        )

    def test_shape2_tracer_contradictory_tie_breaker_inconclusive_has_lenses_key(self):
        tracer = base.RecordingMechanismTracer(verdict="CONTRADICTORY")
        tie_breaker = base.RecordingTieBreaker(verdict="INCONCLUSIVE")
        result = rgr.reconcile(
            [self.ac28, self.ac42], round=16, mechanism_tracer=tracer,
            tie_breaker=tie_breaker,
        )
        self.assertEqual(len(result.needs_human), 1)
        entry = result.needs_human[0]
        self.assertIn("lenses", entry)

    def test_shape3_inconclusive_trace_verdict_has_no_lenses_key(self):
        tracer = base.RecordingMechanismTracer(verdict="INCONCLUSIVE")
        result = rgr.reconcile(
            [self.ac28, self.ac42], round=16, mechanism_tracer=tracer,
        )
        self.assertEqual(len(result.needs_human), 1)
        entry = result.needs_human[0]
        self.assertIn("pair", entry)
        self.assertIn("trace_verdict", entry)
        self.assertNotIn(
            "lenses", entry,
            "shape 3 (INCONCLUSIVE/unrecognized trace verdict) must NOT "
            "carry a top-level 'lenses' key",
        )

    def test_exactly_one_of_the_three_shapes_carries_lenses_key(self):
        shape2_tracer = base.RecordingMechanismTracer(verdict="CONTRADICTORY")
        shape3_tracer = base.RecordingMechanismTracer(verdict="INCONCLUSIVE")

        r1 = rgr.reconcile([self.ac28, self.ac42])
        r2 = rgr.reconcile([self.ac28, self.ac42], mechanism_tracer=shape2_tracer)
        r3 = rgr.reconcile([self.ac28, self.ac42], mechanism_tracer=shape3_tracer)
        entries = [r1.needs_human[0], r2.needs_human[0], r3.needs_human[0]]
        with_lenses = [e for e in entries if "lenses" in e]
        self.assertEqual(
            len(with_lenses), 1,
            "exactly 1 of the 3 documented needs_human shapes may carry a "
            "top-level 'lenses' key -- the other 2 must fall back to "
            "walking their nested GapRecord(s)' own .lens field",
        )


# ---------------------------------------------------------------------------
# AC2 -- CONTRADICTORY pair's "pair" field serializes as a 2-element array
# ---------------------------------------------------------------------------

class TestContradictionsPairTupleSerialization(unittest.TestCase):
    """[BEHAVIORAL] AC2: a CONTRADICTORY pair's "pair" field (a 2-tuple of
    full GapRecord objects) must serialize/deserialize as a plain 2-element
    JSON array via the spec-mandated mechanism (json.dumps(result._asdict(),
    indent=2), no custom JSONEncoder -- spec section B/D.1)."""

    def setUp(self):
        self.ac28 = base._gap28_ac28_record()
        self.ac42 = base._gap28_ac42_record()

    def test_contradictions_pair_round_trips_as_two_element_array_via_spec_mechanism(self):
        # NOTE: this test targets reconcile() (already-existing, unchanged)
        # plus the EXACT literal serialization call spec D.1 mandates for
        # the --out write step (json.dumps(result._asdict(), indent=2), no
        # custom encoder). It therefore PASSES already today -- it is a
        # foundational/regression-protection test confirming the empirical
        # claim the whole --out design rests on (spec section B: "Verified
        # empirically... a direct Python repro serialized cleanly with no
        # TypeError"), NOT a test of the Coder's new argparse/CLI wiring
        # (see the sibling CLI-level test below for that half, via
        # needs_human's structurally identical "pair" 2-tuple).
        tracer = base.RecordingMechanismTracer(verdict="CONTRADICTORY")
        tie_breaker = base.RecordingTieBreaker()
        result = rgr.reconcile(
            [self.ac28, self.ac42], round=16, mechanism_tracer=tracer,
            tie_breaker=tie_breaker,
        )
        self.assertEqual(len(result.contradictions), 1)
        serialized = json.dumps(result._asdict(), indent=2)
        deserialized = json.loads(serialized)
        pair = deserialized["contradictions"][0]["pair"]
        self.assertIsInstance(pair, list)
        self.assertEqual(len(pair), 2)
        for original, round_tripped in zip((self.ac28, self.ac42), pair):
            for field in (
                "lens", "round", "gap_type", "broken_assumption",
                "why_it_fails", "proposed_fix", "touches", "mechanism_refs",
            ):
                self.assertEqual(round_tripped[field], original[field])

    def test_cli_out_flag_serializes_a_real_2tuple_pair_field_as_json_array(self):
        # AC2's literal ask is about `contradictions[i]["pair"]` -- but D.1's
        # Non-goals explicitly puts round/mechanism_tracer/tie_breaker
        # injection OUT OF SCOPE for the CLI itself (`reconcile(records)` is
        # called with no tracer, exactly as today), so `contradictions` can
        # NEVER be non-empty via the actual, real __main__ entry point,
        # today or after this spec's implementation (confirmed by direct
        # code read: the "mechanism_tracer is None" branch is unconditional
        # for the CLI's call site and never reaches the CONTRADICTORY
        # verdict branch). The closest REAL, CLI-reachable analogue is
        # needs_human's shape-1 entry, which carries the structurally
        # identical 2-tuple "pair" field (two full GapRecord objects) -- this
        # test exercises that through the genuine subprocess CLI with --out,
        # using the real gap-28 fixture, confirming the tuple->array
        # serialization holds for the ACTUAL shipped --out code path (not
        # just in isolation, per the sibling test above).
        with tempfile.TemporaryDirectory() as d:
            out_path = os.path.join(d, "out.json")
            _run_cli([self.ac28, self.ac42], out_path=out_path)
            with open(out_path) as f:
                data = json.load(f)
            pair = data["needs_human"][0]["pair"]
            self.assertIsInstance(pair, list)
            self.assertEqual(len(pair), 2)
            for original, round_tripped in zip((self.ac28, self.ac42), pair):
                self.assertEqual(
                    round_tripped["broken_assumption"],
                    original["broken_assumption"],
                )


if __name__ == "__main__":
    unittest.main()
