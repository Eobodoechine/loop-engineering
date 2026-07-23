"""[Loop-Team Test-writer] AC4 scoring-path tests for score_fi (spec rev 5,
sections 5.4-5.7). Micro-step S5. Written BEFORE the implementation exists;
these tests FAIL (not skip) on the availability fixture until the Coder
delivers loop-team/evals/fault_injection/score_fi.py.

Public interface under test. The spec PINS the mechanism (in-process, one
verdicts file per column at DISTINCT paths, replay_judge._CACHE reset,
run_evals.load_cases monkeypatched to the fi- subset and RESTORED -- the
precedented pattern of test_replay_judge.py:112-121). Where names are
genuinely unspecified, the SIMPLEST surface is PINNED here:

    score_fi.normalize_verdict(raw_text) -> str or None
        parse_verdict semantics (optimize/role_runner.py): case/underscore/
        space variants normalize to PASS | FAIL | FALSE-PASS; an explicit
        'VERDICT:' line wins and the LAST one wins on self-correction;
        unparseable -> None. (Asserted directly against sample raws whose
        expected outputs were read off the real parse_verdict.)

    score_fi.record_verdict(column_path, case_id, raw_text) -> str or None
        Validation-at-persistence (spec sec 5.6): normalizes raw_text; when
        parseable, upserts {"id": case_id, "verdict": <normalized>} into the
        JSON LIST at column_path (the exact file shape replay_judge replays)
        and returns the label. When raw_text != the persisted label, the row
        also keeps the original under "raw" -- the machine-checkable form of
        'the normalizer LOGS every raw!=normalized pair' so curation can
        review every normalization (replay_judge ignores extra keys). An
        UNPARSEABLE raw is NEVER persisted as a scored label: no row is
        written, None is returned, the id stays MISSING.

    score_fi.score_columns(columns, manifest, cases) -> report (dict)
        columns: dict {column_name: verdicts_file_path}; column_name is
        "<tier>_r<round>" (e.g. "sonnet_r1"); tier = name.rsplit("_r", 1)[0].
        manifest: the injection-log dict {case_id: entry} (family/difficulty;
        controls have family "control"). cases: the fi- case-dict subset
        (production loads them from evals/cases/; tests pass synthetic ones).
        PINNED report keys asserted here:
          report["columns"][name]["trap_accuracy"]      caught/(caught+missed)
          report["columns"][name]["control_ok_rate"]    ok/(ok+regression)
          report["columns"][name]["per_family"]         {family: trap accuracy}
          report["columns"][name]["per_difficulty"]     {difficulty: trap accuracy}
          report["tiers"][tier]["trap_accuracy"]        round-mean
          report["tiers"][tier]["control_ok_rate"]      round-mean
          report["tiers"][tier]["flip_rate"]            fraction of ALL fi- ids
                                                        where r1 and r2 disagree
          report["complete"]  bool -- the sec 5.7 gate: every given column
                              covers EVERY fi- id with ZERO error rows
          report["missing"]   list; each item's str() names the column and id
          report["decision"]  None unless complete; otherwise the decision-rule
                              outcome object (its internal content is verified
                              in S5/S6 against spec sec 6, not pinned here)

Synthetic fixtures only: case dicts mirror the REAL corpus field names
(evals/cases/verifier-hourly-annualize-floor.json: id/origin/type/target/
requires/expected/artifact/rubric -- the fixture-tautology rule); no verbatim
text from real runs or private files; no personal markers.

The raise-on-missing-id contract of replay_judge is asserted UNTOUCHED and is
never monkeypatched away. Python 3.9 compatible; stdlib + pytest only.
"""
import json
import os
import sys

import pytest

FI_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.dirname(FI_DIR)
for _p in (EVALS_DIR, FI_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import replay_judge as rj  # noqa: E402  (exists today)
import run_evals  # noqa: E402  (exists today)

_IMPORT_ERROR = None
try:
    import score_fi  # noqa: F401  (plain-module layout)
except Exception:  # noqa: BLE001
    try:
        from fault_injection import score_fi  # type: ignore  (package layout)
    except Exception as _e2:  # noqa: BLE001
        score_fi = None
        _IMPORT_ERROR = _e2

CANONICAL = ("PASS", "FAIL", "FALSE-PASS")


@pytest.fixture(autouse=True)
def _require_implementation():
    """FAIL (never skip) while the implementation is missing -- pre-Coder red."""
    if score_fi is None:
        pytest.fail(
            "fault_injection score_fi not importable yet (Coder has not delivered): %r"
            % (_IMPORT_ERROR,))


@pytest.fixture(autouse=True)
def _clean_replay_env(monkeypatch):
    """Hygiene: no stale replay env or cache leaks between tests. This resets
    state; it does NOT weaken any replay_judge contract."""
    monkeypatch.delenv("REPLAY_VERDICTS_PATH", raising=False)
    monkeypatch.delenv("REPLAY_MODEL", raising=False)
    monkeypatch.setattr(rj, "_CACHE", {"path": None, "verdicts": None})


# ---------------------------------------------------------------------------
# Synthetic fi- subset: 4 traps + 2 interleaved controls.
# ---------------------------------------------------------------------------

def _mk_case(cid, expected):
    # Field names mirror the REAL corpus shape (fixture-tautology rule).
    return {
        "id": cid,
        "origin": "Synthetic fixture case built for score_fi tests; framing prose first.",
        "type": "BEHAVIORAL",
        "target": "verifier",
        "requires": "judge",
        "expected": expected,
        "artifact": ("Synthetic run-log artifact for %s: gates listed, summary "
                     "claims green; a planted contradiction sits mid-trace." % cid),
        "rubric": ("Framing prose for the judge: catch the planted contradiction "
                   "described only in this gold-side field."),
        "suite": "fault_injection",
    }


def _mk_cases():
    return [
        _mk_case("fi-001", "FALSE-PASS"),
        _mk_case("fi-002", "PASS"),          # control
        _mk_case("fi-003", "FALSE-PASS"),
        _mk_case("fi-004", "FALSE-PASS"),
        _mk_case("fi-005", "PASS"),          # control
        _mk_case("fi-006", "FALSE-PASS"),
    ]


def _mk_manifest():
    def inj(family, difficulty):
        return {"family": family, "difficulty": difficulty,
                "source_run": "2026-06-30_synthetic-run-a", "source_file": "run_log.md",
                "anchor": "synthetic anchor line", "original_snippet": "synthetic original",
                "mutated_snippet": "synthetic mutated", "description": "synthetic entry"}

    def ctl():
        return {"family": "control", "difficulty": "shallow",
                "source_run": "2026-06-30_synthetic-run-b",
                "source_file": "run_log.md", "description": "synthetic control"}

    return {
        "fi-001": inj("verdict_flip", "deep"),
        "fi-002": ctl(),
        "fi-003": inj("count_drift", "shallow"),
        "fi-004": inj("verdict_flip", "deep"),
        "fi-005": ctl(),
        "fi-006": inj("pipe_masked_exit", "deep"),
    }


ALL_IDS = ("fi-001", "fi-002", "fi-003", "fi-004", "fi-005", "fi-006")


def _write_column(tmp_path, name, verdict_by_id):
    """One verdicts file per column at a DISTINCT path (spec sec 5.4) in the
    exact list shape replay_judge replays: [{"id": ..., "verdict": ...}]."""
    p = tmp_path / ("verdicts_%s.json" % name)
    rows = [{"id": cid, "verdict": v} for cid, v in verdict_by_id.items()]
    p.write_text(json.dumps(rows), encoding="utf-8")
    return str(p)


def _four_columns(tmp_path):
    """The main synthetic four-column setup (sonnet r1/r2, haiku r1/r2).

    Expected figures (hand-computed):
      sonnet_r1: traps 4/4 caught (FAIL counts as reject) -> 1.00; controls 2/2 ok -> 1.00
      sonnet_r2: fi-006 missed -> 3/4 = 0.75; controls 1.00
      haiku_r1 : only fi-001 caught -> 1/4 = 0.25; fi-005 rejected -> controls 1/2 = 0.50
      haiku_r2 : identical to haiku_r1
      tier sonnet: trap round-mean 0.875, control 1.00, flip rate 1/6 (only fi-006 flips)
      tier haiku : trap 0.25, control 0.50, flip rate 0.0
    """
    sonnet_r1 = {"fi-001": "FALSE-PASS", "fi-002": "PASS", "fi-003": "FAIL",
                 "fi-004": "FALSE-PASS", "fi-005": "PASS", "fi-006": "FALSE-PASS"}
    sonnet_r2 = dict(sonnet_r1)
    sonnet_r2["fi-006"] = "PASS"
    haiku_r1 = {"fi-001": "FALSE-PASS", "fi-002": "PASS", "fi-003": "PASS",
                "fi-004": "PASS", "fi-005": "FAIL", "fi-006": "PASS"}
    haiku_r2 = dict(haiku_r1)
    return {
        "sonnet_r1": _write_column(tmp_path, "sonnet_r1", sonnet_r1),
        "sonnet_r2": _write_column(tmp_path, "sonnet_r2", sonnet_r2),
        "haiku_r1": _write_column(tmp_path, "haiku_r1", haiku_r1),
        "haiku_r2": _write_column(tmp_path, "haiku_r2", haiku_r2),
    }


# ---------------------------------------------------------------------------
# Bucketing + per-column / per-tier report (AC4 core)
# ---------------------------------------------------------------------------

class TestBucketingAndReport:
    def test_four_column_report_figures(self, tmp_path):
        """[BEHAVIORAL] AC4: synthetic verdicts files bucket fi- traps
        caught/missed and fi- controls ok/regression correctly; per-column,
        per-tier (round-mean + flip rate), per-family and per-difficulty
        figures come out at the hand-computed values; the completeness gate
        passes and the decision object exists."""
        orig_load_cases = run_evals.load_cases
        report = score_fi.score_columns(_four_columns(tmp_path), _mk_manifest(), _mk_cases())

        cols = report["columns"]
        assert cols["sonnet_r1"]["trap_accuracy"] == pytest.approx(1.0)
        assert cols["sonnet_r1"]["control_ok_rate"] == pytest.approx(1.0)
        assert cols["sonnet_r2"]["trap_accuracy"] == pytest.approx(0.75)
        assert cols["sonnet_r2"]["control_ok_rate"] == pytest.approx(1.0)
        assert cols["haiku_r1"]["trap_accuracy"] == pytest.approx(0.25)
        assert cols["haiku_r1"]["control_ok_rate"] == pytest.approx(0.5)
        assert cols["haiku_r2"]["trap_accuracy"] == pytest.approx(0.25)

        tiers = report["tiers"]
        assert tiers["sonnet"]["trap_accuracy"] == pytest.approx(0.875)
        assert tiers["sonnet"]["control_ok_rate"] == pytest.approx(1.0)
        assert tiers["sonnet"]["flip_rate"] == pytest.approx(1.0 / 6.0)
        assert tiers["haiku"]["trap_accuracy"] == pytest.approx(0.25)
        assert tiers["haiku"]["control_ok_rate"] == pytest.approx(0.5)
        assert tiers["haiku"]["flip_rate"] == pytest.approx(0.0)

        # Manifest join (ids are opaque -- family/difficulty come ONLY from gold).
        assert cols["sonnet_r1"]["per_family"]["verdict_flip"] == pytest.approx(1.0)
        assert cols["haiku_r1"]["per_family"]["verdict_flip"] == pytest.approx(0.5)
        assert cols["sonnet_r2"]["per_difficulty"]["deep"] == pytest.approx(2.0 / 3.0)
        assert cols["sonnet_r2"]["per_difficulty"]["shallow"] == pytest.approx(1.0)

        assert report["complete"] is True
        assert report["decision"] is not None

        # The precedented in-process scoping (load_cases monkeypatch) must be
        # RESTORED after scoring -- test_replay_judge.py:112-121 precedent.
        assert run_evals.load_cases is orig_load_cases, (
            "score_columns must restore run_evals.load_cases after in-process scoring")

    def test_identical_columns_at_distinct_paths_agree(self, tmp_path):
        """[BEHAVIORAL] Control for the anti-cache test below: two columns with
        IDENTICAL verdicts at DISTINCT paths produce identical figures and a
        zero flip rate -- so any divergence elsewhere is data, not noise."""
        v = {"fi-001": "FALSE-PASS", "fi-002": "PASS", "fi-003": "FALSE-PASS",
             "fi-004": "PASS", "fi-005": "PASS", "fi-006": "FALSE-PASS"}
        columns = {"sonnet_r1": _write_column(tmp_path, "sonnet_r1", v),
                   "sonnet_r2": _write_column(tmp_path, "sonnet_r2", dict(v))}
        report = score_fi.score_columns(columns, _mk_manifest(), _mk_cases())
        c = report["columns"]
        assert c["sonnet_r1"]["trap_accuracy"] == pytest.approx(c["sonnet_r2"]["trap_accuracy"])
        assert report["tiers"]["sonnet"]["flip_rate"] == pytest.approx(0.0)

    def test_multi_column_different_verdicts_yield_different_figures(self, tmp_path):
        """[BEHAVIORAL] AC4 multi-column test: two columns whose synthetic
        verdicts DIFFER must yield DIFFERENT per-column figures. This is the
        cache-replay corruption trap (spec sec 5.4): replay_judge._CACHE keys
        on path only, so a scorer that fails to reset it / reuse distinct
        paths silently replays column 1 -- identical figures from different
        inputs -- faking flip rate 0 and perfect band agreement."""
        r1 = {"fi-001": "FALSE-PASS", "fi-002": "PASS", "fi-003": "FALSE-PASS",
              "fi-004": "FALSE-PASS", "fi-005": "PASS", "fi-006": "FALSE-PASS"}
        r2 = {"fi-001": "PASS", "fi-002": "PASS", "fi-003": "PASS",
              "fi-004": "PASS", "fi-005": "PASS", "fi-006": "FALSE-PASS"}
        columns = {"sonnet_r1": _write_column(tmp_path, "sonnet_r1", r1),
                   "sonnet_r2": _write_column(tmp_path, "sonnet_r2", r2)}
        report = score_fi.score_columns(columns, _mk_manifest(), _mk_cases())
        a1 = report["columns"]["sonnet_r1"]["trap_accuracy"]
        a2 = report["columns"]["sonnet_r2"]["trap_accuracy"]
        assert a1 == pytest.approx(1.0)
        assert a2 == pytest.approx(0.25)
        assert a1 != a2, (
            "different verdicts files produced identical figures -- the column-1 "
            "cache-replay corruption the spec pins against")
        assert report["tiers"]["sonnet"]["flip_rate"] > 0.0


# ---------------------------------------------------------------------------
# raise-on-missing-id untouched + sec 5.7 completeness gate
# ---------------------------------------------------------------------------

class TestMissingAndCompleteness:
    def test_replay_judge_raise_on_missing_id_untouched(self, tmp_path, monkeypatch):
        """[BEHAVIORAL] AC4: the raise-on-missing-id contract of replay_judge
        is UNTOUCHED after score_fi exists -- an unknown id still raises
        (a gap in the recorded set is an error, never a silent PASS)."""
        p = _write_column(tmp_path, "solo", {"fi-001": "PASS"})
        monkeypatch.setenv("REPLAY_VERDICTS_PATH", p)
        assert rj.judge({"id": "fi-001"}) == "PASS"
        with pytest.raises(RuntimeError):
            rj.judge({"id": "fi-999"})

    def test_missing_id_in_one_column_blocks_decision(self, tmp_path):
        """[BEHAVIORAL] Spec sec 5.7: a column that lacks a verdict for one
        fi- id may not silently shrink the accuracy denominator -- the report
        is incomplete, the missing (column, id) pair is named, and the
        decision rule DOES NOT run."""
        columns = _four_columns(tmp_path)
        short = {"fi-001": "FALSE-PASS", "fi-002": "PASS", "fi-003": "PASS",
                 "fi-004": "PASS", "fi-005": "PASS"}   # fi-006 absent
        columns["haiku_r1"] = _write_column(tmp_path, "haiku_r1_short", short)
        report = score_fi.score_columns(columns, _mk_manifest(), _mk_cases())
        assert report["complete"] is False
        assert report["decision"] is None, (
            "decision rule ran on an incomplete column set (sec 5.7 gate hole)")
        assert any("fi-006" in str(m) and "haiku_r1" in str(m)
                   for m in report["missing"]), (
            "the missing (column, id) pair must be reported: %s" % (report["missing"],))

    def test_blank_verdict_error_row_blocks_decision(self, tmp_path):
        """[BEHAVIORAL] Spec sec 5.7: a blank/None recorded verdict replays as
        MISSING (replay_judge line 92 semantics), which surfaces as an error
        row -- and any error row blocks the decision report too."""
        columns = _four_columns(tmp_path)
        blank = {"fi-001": "FALSE-PASS", "fi-002": "PASS", "fi-003": "FALSE-PASS",
                 "fi-004": "FALSE-PASS", "fi-005": "PASS", "fi-006": None}
        columns["sonnet_r2"] = _write_column(tmp_path, "sonnet_r2_blank", blank)
        report = score_fi.score_columns(columns, _mk_manifest(), _mk_cases())
        assert report["complete"] is False
        assert report["decision"] is None
        assert any("fi-006" in str(m) and "sonnet_r2" in str(m)
                   for m in report["missing"])


# ---------------------------------------------------------------------------
# Validation at persistence (spec sec 5.6) + the AC4 malformed-verdict test
# ---------------------------------------------------------------------------

class TestNormalizationAtPersistence:
    def test_normalize_verdict_variants(self):
        """[BEHAVIORAL] parse_verdict semantics (read off the real
        optimize/role_runner.py implementation): underscore/space/case
        variants normalize; explicit VERDICT: lines win; the LAST verdict wins
        on self-correction; unparseable -> None."""
        assert score_fi.normalize_verdict("VERDICT: FALSE_PASS") == "FALSE-PASS"
        assert score_fi.normalize_verdict("verdict: pass") == "PASS"
        assert score_fi.normalize_verdict("VERDICT: FALSE PASS") == "FALSE-PASS"
        assert score_fi.normalize_verdict(
            "I examined the artifact closely. VERDICT: FAIL. On reflection the "
            "gates do hold after all. VERDICT: FALSE-PASS") == "FALSE-PASS"
        assert score_fi.normalize_verdict("false_pass") == "FALSE-PASS"
        assert score_fi.normalize_verdict(
            "the artifact appears thorough and convincing overall") is None
        assert score_fi.normalize_verdict("") is None

    def test_record_verdict_persists_normalized_label(self, tmp_path):
        """[BEHAVIORAL] Spec sec 5.6: what lands in the column file is the
        LABEL, not the raw string -- and the raw is retained alongside for the
        curation review of every raw!=normalized pair."""
        p = str(tmp_path / "col.json")
        out = score_fi.record_verdict(p, "fi-001", "VERDICT: FALSE_PASS")
        assert out == "FALSE-PASS"
        rows = json.loads(open(p, encoding="utf-8").read())
        row = [r for r in rows if r["id"] == "fi-001"][0]
        assert row["verdict"] == "FALSE-PASS"
        assert row.get("raw") == "VERDICT: FALSE_PASS", (
            "raw!=normalized pairs must be retained for curation review (sec 5.6)")

    def test_record_verdict_unparseable_never_persisted(self, tmp_path):
        """[BEHAVIORAL] Spec sec 5.6: an unparseable verdict is NEVER persisted
        as a scored label -- no row is written, the id stays MISSING so the
        resumable sweep re-judges it and raise-on-missing keeps it loud."""
        p = str(tmp_path / "col.json")
        out = score_fi.record_verdict(
            p, "fi-006", "the artifact appears thorough and convincing overall")
        assert out is None
        if os.path.exists(p):
            rows = json.loads(open(p, encoding="utf-8").read())
            assert not [r for r in rows if r.get("id") == "fi-006"], (
                "an unparseable verdict was persisted (sec 5.6 violation)")

    def test_malformed_verdicts_never_reach_classify(self, tmp_path, monkeypatch):
        """[BEHAVIORAL] The AC4 malformed-verdict test: 'FALSE_PASS', lowercase
        and prose-wrapped variants can never silently bucket as
        missed/regression. Columns are built through record_verdict from raw
        sub-agent text; a spy on run_evals.classify then asserts a raw
        malformed string reaching classify() is IMPOSSIBLE -- every verdict it
        sees is a canonical label. The unparseable id is left MISSING and the
        completeness gate reports it (never a scored bucket)."""
        raws = {
            "fi-001": "VERDICT: FALSE_PASS",
            "fi-002": "verdict: pass",
            "fi-003": ("Detailed review follows. VERDICT: FAIL. Wait -- the count "
                       "reconciles on re-read. VERDICT: FALSE-PASS"),
            "fi-004": "false_pass",
            "fi-005": "VERDICT: PASS",
            "fi-006": "the artifact appears thorough and convincing overall",  # unparseable
        }
        p = str(tmp_path / "verdicts_sonnet_r1.json")
        for cid, raw in raws.items():
            score_fi.record_verdict(p, cid, raw)

        seen = []
        real_classify = run_evals.classify

        def spy(expected, verdict):
            seen.append(verdict)
            return real_classify(expected, verdict)

        monkeypatch.setattr(run_evals, "classify", spy)
        report = score_fi.score_columns({"sonnet_r1": p}, _mk_manifest(), _mk_cases())

        assert seen, "classify was never exercised -- the scoring path did not run"
        bad = [v for v in seen if v not in CANONICAL]
        assert not bad, (
            "raw/malformed verdict strings reached classify(): %s -- they would "
            "silently bucket as missed/regression (run_evals.py:123 class)" % bad)

        # The unparseable id stayed MISSING and the completeness gate says so.
        assert report["complete"] is False
        assert report["decision"] is None
        assert any("fi-006" in str(m) for m in report["missing"])
