"""[Loop-Team Adversarial Test-writer, Tier 2] Attacks on the D1 fault-injection
package (spec rev 5): injector.py, make_cases.py, score_fi.py.

Written FROM THE CODE, after the standard suite (70/70) went green; deduplicated
against test_injector_f1_f4.py / test_injector_f5_f7.py / test_sanitizer_emitter.py
/ test_corpus_batch.py / test_score_fi.py (read LAST, per role Phase 5).

File layout -- two sections:

  1. FAILING ATTACKS  -- each test FAILS against the current implementation.
     These are the findings (the deliverable). Docstrings name the attack and
     the spec clause the behavior violates.
  2. SURVIVED ATTACKS -- the implementation held; kept as regression pins
     (they add coverage the standard suite does not have, notably the entire
     spec-6 decision table, which had ZERO standard-test coverage).

No existing file is modified. No real marker file is ever read -- all marker
fixtures are synthetic temp files (AC2 discipline). Python 3.9; stdlib + pytest.
"""
import importlib.util
import json
import os
import sys

import pytest

FI_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.dirname(FI_DIR)
LOOP_TEAM_DIR = os.path.dirname(EVALS_DIR)
for _p in (EVALS_DIR, FI_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import injector  # noqa: E402
import make_cases  # noqa: E402
import replay_judge as rj  # noqa: E402
import run_evals  # noqa: E402
import score_fi  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_replay_env(monkeypatch):
    """Hygiene (mirrors test_score_fi.py): no stale replay env/cache between
    tests. Resets state only; weakens no replay_judge contract."""
    monkeypatch.delenv("REPLAY_VERDICTS_PATH", raising=False)
    monkeypatch.delenv("REPLAY_MODEL", raising=False)
    monkeypatch.setattr(rj, "_CACHE", {"path": None, "verdicts": None})


# ---------------------------------------------------------------------------
# Shared synthetic fixtures (no real markers, no real run text)
# ---------------------------------------------------------------------------

def _write_markers(tmp_path, lines, name="markers.local"):
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def _mk_case(cid, expected):
    """Minimal fi-shaped case for score_columns (field names mirror the corpus)."""
    return {
        "id": cid, "expected": expected, "target": "verifier",
        "requires": "judge", "type": "BEHAVIORAL", "suite": "fault_injection",
        "artifact": "Synthetic artifact for %s; summary claims green." % cid,
    }


def _batch(n_traps, n_controls):
    traps = [_mk_case("fi-0%02d" % i, "FALSE-PASS") for i in range(1, n_traps + 1)]
    controls = [_mk_case("fi-1%02d" % i, "PASS") for i in range(1, n_controls + 1)]
    return traps + controls


def _write_column(tmp_path, name, batch, trap_hits, control_hits=None):
    """Verdicts file: first `trap_hits` traps caught (FALSE-PASS), rest missed
    (PASS); first `control_hits` controls ok (PASS), rest rejected (FAIL)."""
    rows, t, c = [], 0, 0
    for case in batch:
        if case["expected"] == "PASS":
            hits = len([x for x in batch if x["expected"] == "PASS"]) \
                if control_hits is None else control_hits
            rows.append({"id": case["id"], "verdict": "PASS" if c < hits else "FAIL"})
            c += 1
        else:
            rows.append({"id": case["id"],
                         "verdict": "FALSE-PASS" if t < trap_hits else "PASS"})
            t += 1
    p = str(tmp_path / (name + ".json"))
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rows, f)
    return p


# ===========================================================================
# SECTION 1: FAILING ATTACKS -- findings. Every test below FAILS against the
# current implementation. Do not "fix" the tests; fix the code.
# ===========================================================================


class TestFailingSanitizerAttacks:
    def test_bom_in_marker_file_disarms_first_marker(self, tmp_path):
        """[BEHAVIORAL] ATTACK: UTF-8 BOM smuggle. A marker file saved with a
        BOM (utf-8-sig -- a one-keystroke editor/tool default) makes the FIRST
        marker load as '\\ufeffMARKER': it can never match the real marker in
        text, so the marker sanitizes to nothing and the fail-closed gate
        stays silent. Spec sec 2: 'fails closed if any marker ... survives'.
        Here the marker survives into the emitted output with NO raise."""
        p = tmp_path / "bom.markers"
        p.write_bytes(b"\xef\xbb\xbfZQXSYNTHNAME\nOTHERSYNTH\n")
        out = make_cases.sanitize_text("send mail to ZQXSYNTHNAME now", str(p))
        assert "ZQXSYNTHNAME" not in out, (
            "BOM-prefixed first marker survived sanitization silently "
            "(fail-closed bypass): %r" % out)

    def test_home_path_survives_dot_segment_and_double_slash(self, tmp_path):
        """[BEHAVIORAL] ATTACK: home-path smuggle via non-canonical separators.
        _HOME_PATH_RE consumes exactly one [^/\\s]+ component after the
        slash-Users prefix, so the dot-segment spelling (slash-Users then
        '/./joeblow/f.txt') redacts the DOT as the username and lets the
        real username through, and the doubled-slash spelling survives
        verbatim. Both resolve to the same home path a run log can emit
        (doubled slashes are common in tool output). Spec sec 2: absolute
        home paths are replaced with <REPO>-style placeholders."""
        markers = _write_markers(tmp_path, ["UNRELATEDSYNTH"])
        out1 = make_cases.sanitize_text("/Use" + "rs/./joeblow/f.txt", markers)
        assert "joeblow" not in out1, (
            "username leaked through the dot-segment home-path spelling: %r"
            % out1)
        out2 = make_cases.sanitize_text("/Use" + "rs//joeblow/f.txt", markers)
        assert "joeblow" not in out2, (
            "home path with doubled slash survived verbatim: %r" % out2)

    def test_build_case_accepts_id_with_trailing_newline(self, tmp_path):
        """[BEHAVIORAL] ATTACK: opaque-id regex anchoring. _CASE_ID_RE uses
        '$', which matches BEFORE a trailing newline, so build_case accepts
        'fi-007\\n'. Filename = id (spec sec 2), so this id cannot round-trip
        to a case file; downstream ids are keys in verdicts files and the
        manifest. Should raise ValueError (use fullmatch/\\Z)."""
        markers = _write_markers(tmp_path, ["SYNTHMARKERX"])
        with pytest.raises(ValueError):
            make_cases.build_case(
                "fi-007\n", "Artifact body text for the id-shape attack.",
                "PASS", "Framing origin prose for this synthetic case.",
                "Framing rubric prose for this synthetic case.", markers)

    def test_build_case_accepts_non_ascii_digit_id(self, tmp_path):
        """[BEHAVIORAL] ATTACK: Unicode digits. \\d in _CASE_ID_RE matches ANY
        Unicode decimal digit, so 'fi-١٢٣' (Arabic-Indic 123)
        passes the opaque-shape check. Spec sec 2 pins zero-padded ids
        fi-001..fi-030 (ASCII); a non-ASCII id is a covert per-case signal
        channel and breaks filename=id conventions. Should raise ValueError."""
        markers = _write_markers(tmp_path, ["SYNTHMARKERX"])
        with pytest.raises(ValueError):
            make_cases.build_case(
                "fi-١٢٣", "Artifact body text for the digit attack.",
                "PASS", "Framing origin prose for this synthetic case.",
                "Framing rubric prose for this synthetic case.", markers)

    def test_manifest_entry_marker_inside_container_field_leaks(self, tmp_path):
        """[BEHAVIORAL] ATTACK: nested-container smuggle. sanitize_manifest_entry
        passes non-string values through UNCHANGED, so a marker inside a list
        (or nested dict) field -- e.g. a curated params/notes field added to a
        manifest entry -- is returned live, with no sanitization and no
        fail-closed raise. The sanitizer's contract (spec sec 2) is that
        nothing it returns still carries a marker; sanitizing-or-raising are
        both acceptable, silent pass-through is not."""
        markers = _write_markers(tmp_path, ["SYNTHLEAKNAME"])
        entry = {"description": "clean text",
                 "notes": ["curation note mentioning SYNTHLEAKNAME here"],
                 "params": {"anchor": "quote by SYNTHLEAKNAME"}}
        out = make_cases.sanitize_manifest_entry(entry, markers)
        assert "SYNTHLEAKNAME" not in json.dumps(out, ensure_ascii=False), (
            "marker inside a non-string manifest field passed through the "
            "sanitizer silently: %r" % (out,))


class TestFailingInjectorAttacks:
    def test_f2_count_drift_drifts_a_date_not_the_count(self):
        """[BEHAVIORAL] ATTACK: wrong-site selection (gold fidelity). F2 takes
        the FIRST N/M on the anchored line; when a date/version precedes the
        trap count, the DATE is drifted ('07/01' -> '8/2') and the count
        reconciles untouched -- the family definition (spec sec 1: 'stated
        count contradicts the enumerable list') is not instantiated, so the
        case ships with expected=FALSE-PASS gold that is simply WRONG, and it
        passes the no-op guard because bytes changed."""
        src = ("run log\n"
               "on 07/01: 15/15 traps green per the list below\n"
               "- t1\n- t2\n")
        mutated, rec = injector.inject(src, "count_drift",
                                       {"anchor": "traps green per the list"})
        assert "07/01" in rec["mutated_snippet"], (
            "the date was drifted instead of the trap count: %r"
            % rec["mutated_snippet"])
        assert "15/15" not in rec["mutated_snippet"], (
            "the stated trap count survived unchanged -- no count/list "
            "contradiction was injected: %r" % rec["mutated_snippet"])

    def test_f6_drifts_version_token_not_cited_target(self):
        """[BEHAVIORAL] ATTACK: wrong-site selection (gold fidelity). F6's
        target-token regex matches ANY dotted token, so a version like 'v2.0'
        earlier on the line is 'corrected' to 'v2.1' while the actually-cited
        target (parcel_9021.json) survives -- the certification still points
        at the RIGHT target and the FALSE-PASS gold is wrong."""
        src = "log\nverified against policy v2.0 record parcel_9021.json ok\n"
        mutated, rec = injector.inject(
            src, "wrong_target_certification", {"anchor": "verified against"})
        assert "v2.0" in rec["mutated_snippet"], (
            "the version token was drifted instead of the cited target: %r"
            % rec["mutated_snippet"])
        assert "parcel_9021.json" not in rec["mutated_snippet"], (
            "the cited target survived unchanged -- evidence still certifies "
            "the right thing: %r" % rec["mutated_snippet"])

    def test_f7_corrupts_return_annotation_arrow_not_the_comparison(self):
        """[BEHAVIORAL] ATTACK: wrong-site selection (gold fidelity). F7
        inverts the FIRST <=|>=|==|!=|<|> on the anchored diff line; on a line
        with a Python '->' return annotation the '>' of the arrow is the first
        match, producing '-<' -- a syntax error, not the spec's 'localized
        logic defect' (inverted comparison / off-by-one / dropped guard), and
        the real comparison 'x > 0' the quoted evidence contradicts survives."""
        src = ("checkpoint diff:\n"
               "+ def check(x) -> bool: return x > 0\n"
               "quoted evidence: assert check(3) is True\n")
        mutated, rec = injector.inject(src, "diff_defect", {"anchor": "def check"})
        assert "->" in rec["mutated_snippet"], (
            "the '->' annotation arrow was corrupted into a syntax error: %r"
            % rec["mutated_snippet"])
        assert "x < 0" in rec["mutated_snippet"], (
            "the logic comparison was not the inverted site: %r"
            % rec["mutated_snippet"])

    def test_f1_on_cr_separated_text_flips_the_success_claim_too(self):
        """[BEHAVIORAL] ATTACK: line-boundary assumption. _line_bounds only
        understands '\\n'; on classic-Mac '\\r'-separated text (or any anchored
        'line' that also carries the claim) the whole text is one line, and
        F1's unbounded re.sub flips the SUCCESS CLAIM along with the evidence.
        Spec sec 1 (F1 row): the claimed green is RETAINED and only the
        embedded evidence shows red -- flipping both yields a self-consistent
        red artifact whose FALSE-PASS gold is wrong."""
        src = "claim: PASS all good\rEvidence: 3 passed, 0 failed\rexit code: 0\r"
        mutated, rec = injector.inject(src, "verdict_flip", {"anchor": "3 passed"})
        assert "claim: PASS" in mutated, (
            "the success claim was flipped too -- FALSE-PASS structure "
            "destroyed: %r" % mutated)


class TestFailingScoringAttacks:
    def test_adversarial_verdicts_file_reaches_classify_silently(self, tmp_path):
        """[BEHAVIORAL] ATTACK: file-level malformed verdicts. AC4: 'a raw
        malformed string reaching classify() is asserted impossible'. The
        standard AC4 test only builds files through record_verdict; a verdicts
        FILE containing raw 'FALSE_PASS' (underscore) or a LIST verdict --
        e.g. hand-recovered rows after a crashed sweep -- replays through
        replay_judge untouched (any truthy verdict is kept) and classify()
        silently buckets both traps as MISSED, with the completeness gate
        fully satisfied. The scored figure is corrupted with zero signal."""
        batch = [_mk_case("fi-001", "FALSE-PASS"), _mk_case("fi-002", "FALSE-PASS"),
                 _mk_case("fi-003", "PASS")]
        p = str(tmp_path / "adversarial.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump([{"id": "fi-001", "verdict": "FALSE_PASS"},
                       {"id": "fi-002", "verdict": ["FALSE-PASS"]},
                       {"id": "fi-003", "verdict": "PASS"}], f)
        report = score_fi.score_columns({"sonnet_r1": p}, {}, batch)
        counts = report["columns"]["sonnet_r1"]["counts"]
        assert counts["missed"] == 0, (
            "malformed file verdicts silently bucketed as missed traps "
            "(counts=%s, complete=%s) -- AC4's impossible path is live"
            % (counts, report["complete"]))

    def test_duplicate_case_ids_drop_a_row_but_gate_passes(self, tmp_path):
        """[BEHAVIORAL] ATTACK: completeness-gate hole. Two cases sharing an id
        (a curation slip AC5 only checks on the COMMITTED corpus) collapse in
        rows_by_id: the trap's row is overwritten by the control's, the same
        surviving row is counted twice, and the gate still reports complete.
        Spec sec 5.7: a row 'may not silently vanish from the accuracy
        denominator'. Either raise on duplicate ids or report incompleteness."""
        batch = [_mk_case("fi-007", "FALSE-PASS"), _mk_case("fi-007", "PASS")]
        p = str(tmp_path / "dup.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump([{"id": "fi-007", "verdict": "FAIL"}], f)
        try:
            report = score_fi.score_columns({"s_r1": p}, {}, batch)
        except ValueError:
            return  # loud rejection of duplicate ids is acceptable
        counts = report["columns"]["s_r1"]["counts"]
        assert (not report["complete"]) or (
            counts["caught"] == 1 and counts["regression"] == 1), (
            "duplicate case id silently dropped a row while the completeness "
            "gate passed: counts=%s complete=%s" % (counts, report["complete"]))

    def test_same_path_for_two_columns_fakes_flip_rate_zero(self, tmp_path):
        """[BEHAVIORAL] ATTACK: distinct-paths mechanism unenforced. Spec 5.4
        pins 'one verdicts file per column at DISTINCT paths' precisely so
        identical figures from different inputs are impossible to miss (AC4);
        passing the SAME path for both rounds silently manufactures flip rate
        0.0 and perfect band agreement -- exactly the corruption shape the
        spec pins against. score_columns must reject duplicate paths loudly."""
        batch = _batch(5, 5)
        p = _write_column(tmp_path, "one", batch, trap_hits=5)
        with pytest.raises(ValueError):
            score_fi.score_columns({"sonnet_r1": p, "sonnet_r2": p}, {}, batch)

    def test_single_round_tier_reaches_decision_bearing_outcome(self, tmp_path):
        """[BEHAVIORAL] ATTACK: vacuous band agreement. Spec 5.3/6: TWO
        independent rounds per tier; the decision rule applies only where BOTH
        rounds land in the same band (single-run placement has +-5-7pp noise).
        With ONE round the band-agreement set has one element, agreement is
        vacuously true, and a decision-bearing FREEZE is issued from
        single-round data. A one-round tier must route to gray zone/refusal."""
        batch = _batch(10, 5)
        p = _write_column(tmp_path, "solo", batch, trap_hits=7)  # 70% -> freeze band
        report = score_fi.score_columns({"sonnet_r1": p}, {}, batch)
        assert report["decision"]["outcome"] not in (
            "FREEZE", "KILL_LANE", "ESCALATE_INJECTOR"), (
            "decision-bearing outcome %r issued from a SINGLE judging round "
            "(spec 5.3 requires two rounds in band agreement)"
            % report["decision"]["outcome"])


# ===========================================================================
# SECTION 2: SURVIVED ATTACKS -- the implementation held. Kept as regression
# pins; none of these paths are covered by the standard suite.
# ===========================================================================


class TestSurvivedSanitizer:
    def test_marker_file_is_a_directory_fails_closed(self, tmp_path):
        """[BEHAVIORAL] Attack: marker path exists but is a DIRECTORY.
        IsADirectoryError is an OSError, so load_markers raises ValueError and
        build_case emits nothing. Survived."""
        with pytest.raises(ValueError):
            make_cases.load_markers(str(tmp_path))
        with pytest.raises(ValueError):
            make_cases.build_case("fi-001", "Artifact body.", "PASS",
                                  "Framing origin prose here.",
                                  "Framing rubric prose here.", str(tmp_path))

    @pytest.mark.skipif(os.geteuid() == 0, reason="permission bits ignored as root")
    def test_marker_file_unreadable_permissions_fails_closed(self, tmp_path):
        """[BEHAVIORAL] Attack: marker file exists but is chmod 000
        (unreadable-but-existing). PermissionError is an OSError -> ValueError
        before anything is emitted. Survived."""
        p = tmp_path / "locked.markers"
        p.write_text("SYNTHM\n", encoding="utf-8")
        os.chmod(str(p), 0)
        try:
            with pytest.raises(ValueError):
                make_cases.load_markers(str(p))
            with pytest.raises(ValueError):
                make_cases.build_case("fi-001", "Artifact body.", "PASS",
                                      "Framing origin prose here.",
                                      "Framing rubric prose here.", str(p))
        finally:
            os.chmod(str(p), 0o600)

    def test_marker_synthesized_by_repo_placeholder_still_raises(self, tmp_path):
        """[BEHAVIORAL] Attack: marker formed BY the home-path replacement
        (marker text containing '<REPO>'; the replacement stitches it
        together). The post-substitution gate re-checks markers and raises --
        fail-closed holds even for sanitizer-synthesized markers. Survived."""
        markers = _write_markers(tmp_path, ["AB<REPO> y"])
        with pytest.raises(ValueError):
            make_cases.sanitize_text("AB/Use" + "rs/x y z", markers)

    def test_marker_overlapping_home_path_fully_redacted(self, tmp_path):
        """[BEHAVIORAL] Attack: marker IS the home-dir username, overlapping
        the path replacement's span. Marker pass runs first, then the path
        pass still matches the redacted component; nothing survives. Survived."""
        markers = _write_markers(tmp_path, ["joeblow"])
        out = make_cases.sanitize_text("/Use" + "rs/joeblow/x.txt", markers)
        assert "joeblow" not in out
        assert "<REPO>" in out

    def test_marker_substring_of_redacted_placeholder_spurious_raise(self, tmp_path):
        """[DOC] Quirk pin, fail-closed direction: if any marker is a
        case-insensitive substring of '<REDACTED>' (e.g. 'red', 'ted', 'act'),
        redacting ANY OTHER marker plants that substring, and the gate raises
        on text that never contained the second marker. Wrong raise, but it
        blocks emission rather than leaking -- acceptable per spec sec 2;
        pinned so a future 'fix' does not flip it to fail-open."""
        markers = _write_markers(tmp_path, ["synthalice", "red"])
        with pytest.raises(ValueError):
            make_cases.sanitize_text("synthalice went home", markers)


class TestSurvivedInjector:
    def test_f1_crlf_line_endings_flip_stays_localized(self):
        """[BEHAVIORAL] Attack: CRLF endings. The '\\r' rides inside the
        'line', regex \\b boundaries still hold, the flip lands and the
        replacement reconstruction stays byte-exact. Survived."""
        src = "claim ok\r\nresult: 3 passed, 0 failed\r\ndone\r\n"
        mutated, rec = injector.inject(src, "verdict_flip", {"anchor": "3 passed"})
        assert "2 passed, 1 failed" in rec["mutated_snippet"]
        assert rec["mutated_snippet"].endswith("\r")
        assert src.replace(rec["original_snippet"], rec["mutated_snippet"], 1) == mutated

    def test_f1_zero_passed_boundary(self):
        """[BEHAVIORAL] Mutation-operator pin (passed > 0 boundary): '0 passed,
        0 failed' must flip to '0 passed, 1 failed', never '-1 passed'.
        Survived; kills the >= mutant on _flip_passed_counts."""
        src = "log\nresult: 0 passed, 0 failed\nend\n"
        _, rec = injector.inject(src, "verdict_flip", {"anchor": "0 passed"})
        assert "0 passed, 1 failed" in rec["mutated_snippet"]
        assert "-1" not in rec["mutated_snippet"]

    def test_f2_zero_over_zero_boundary(self):
        """[BEHAVIORAL] Boundary: '0/0' drifts to '1/1' (both incremented, no
        crash, no negative). Survived."""
        src = "log\nStated: 0/0 checks reconciled\nend\n"
        _, rec = injector.inject(src, "count_drift", {"anchor": "checks reconciled"})
        assert "1/1" in rec["mutated_snippet"]

    def test_f4_anchor_on_last_line_without_trailing_newline(self):
        """[BEHAVIORAL] Attack: file-boundary anchor. F4 on the final,
        newline-less line deletes exactly that line; on a single-line source
        the mutated artifact is the empty string (still a real change, record
        accurate). Survived."""
        src = "clause list\n- c1 evidence\n- c2 evidence"
        mutated, rec = injector.inject(src, "unimplemented_clause",
                                       {"anchor": "c2 evidence"})
        assert mutated == "clause list\n- c1 evidence\n"
        single = "only line with evidence token"
        mutated2, rec2 = injector.inject(single, "unimplemented_clause",
                                         {"anchor": "evidence token"})
        assert mutated2 == ""
        assert rec2["original_snippet"] == single

    def test_f5_leading_zero_and_ten_never_false_flip(self):
        """[BEHAVIORAL] Attack: \\b guard on the exit-code digit. 'exit code:
        01' and 'exit code: 10' carry no zero-exit evidence; both must raise
        (no-op guard), never mangle digits. Survived."""
        for line in ("exit code: 01", "exit code: 10"):
            src = "pipeline green\n%s observed\n" % line
            with pytest.raises(ValueError):
                injector.inject(src, "pipe_masked_exit", {"anchor": "observed"})

    def test_f6_digit_carry_and_no_digit_fallback(self):
        """[BEHAVIORAL] Boundary: digit-run bump with carry (9 -> 10) must not
        embed the original token; a digitless target gets '-alt' before the
        extension. Survived."""
        src = "log\nchecked file9.txt as claimed\nend\n"
        _, rec = injector.inject(src, "wrong_target_certification",
                                 {"anchor": "as claimed"})
        assert "file10.txt" in rec["mutated_snippet"]
        assert "file9.txt" not in rec["mutated_snippet"]
        src2 = "log\nchecked notes.txt as claimed\nend\n"
        _, rec2 = injector.inject(src2, "wrong_target_certification",
                                  {"anchor": "as claimed"})
        assert "notes-alt.txt" in rec2["mutated_snippet"]

    def test_inject_input_type_guards(self):
        """[BEHAVIORAL] Type attacks on the dispatcher: bytes source, empty
        source, non-dict params, non-string/True anchor -- all ValueError,
        never a silent no-op or a TypeError deep in a family fn. Survived."""
        with pytest.raises(ValueError):
            injector.inject(b"bytes source", "verdict_flip", {"anchor": "x"})
        with pytest.raises(ValueError):
            injector.inject("", "verdict_flip", {"anchor": "x"})
        with pytest.raises(ValueError):
            injector.inject("text PASS here", "verdict_flip", ["anchor"])
        with pytest.raises(ValueError):
            injector.inject("text PASS here", "verdict_flip", {"anchor": True})
        with pytest.raises(ValueError):
            injector.inject("text PASS here", "verdict_flip", {"anchor": ""})

    def test_anchor_at_very_start_of_source(self):
        """[BEHAVIORAL] Attack: anchor on the FIRST line (rfind returns -1;
        the +1 must land on index 0, not slice from the end). Survived."""
        src = "Stated: 3/3 traps caught\n- a\n- b\n- c\n"
        mutated, rec = injector.inject(src, "count_drift", {"anchor": "Stated:"})
        assert rec["original_snippet"] == "Stated: 3/3 traps caught"
        assert mutated.startswith("Stated: 4/4 traps caught\n")


class TestSurvivedScoring:
    def test_id_case_variant_blocks_decision(self, tmp_path):
        """[BEHAVIORAL] Attack: verdicts recorded under 'FI-001' while the case
        id is 'fi-001'. replay_judge raises on the unknown id, the row becomes
        an error, the gate reports it and the decision is withheld -- ids stay
        case-sensitive and loud. Survived."""
        p = str(tmp_path / "case.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump([{"id": "FI-001", "verdict": "PASS"}], f)
        report = score_fi.score_columns({"s_r1": p}, {}, [_mk_case("fi-001", "PASS")])
        assert report["complete"] is False
        assert report["decision"] is None

    def test_multi_model_dict_verdicts_file_blocks_decision(self, tmp_path):
        """[BEHAVIORAL] Attack: the banned multi-model single-file shape
        ({model: rows} with 2 keys, spec 5.4). replay_judge refuses without
        REPLAY_MODEL; every row errors; gate withholds the decision. Survived."""
        p = str(tmp_path / "multi.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"sonnet": [{"id": "fi-001", "verdict": "PASS"}],
                       "haiku": [{"id": "fi-001", "verdict": "PASS"}]}, f)
        report = score_fi.score_columns({"s_r1": p}, {}, [_mk_case("fi-001", "PASS")])
        assert report["complete"] is False
        assert report["decision"] is None

    def test_duplicate_ids_inside_verdicts_file_raises_loudly(self, tmp_path):
        """[BEHAVIORAL] Pin (AMENDED): duplicate rows for one id in a verdicts
        FILE raise ValueError before any scoring. This test originally pinned
        the silent last-wins resolution as a DOC quirk; Oga overruled last-wins
        per the raise-on-anomaly philosophy, D1 run log 2026-07-02 -- the only
        authorized test change of the adversarial-fix round, strictly in the
        stricter direction."""
        p = str(tmp_path / "dupfile.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump([{"id": "fi-001", "verdict": "PASS"},
                       {"id": "fi-001", "verdict": "FALSE-PASS"}], f)
        with pytest.raises(ValueError):
            score_fi.score_columns({"s_r1": p}, {},
                                   [_mk_case("fi-001", "FALSE-PASS")])

    def test_record_verdict_non_string_raw_raises_loudly(self, tmp_path):
        """[DOC] Pin: a non-string truthy raw (int) raises TypeError inside
        normalization -- loud, nothing persisted. Never a silent label."""
        p = str(tmp_path / "col.json")
        with pytest.raises(TypeError):
            score_fi.record_verdict(p, "fi-001", 123)
        assert not os.path.exists(p)

    def test_normalize_verdict_parity_with_role_runner_parse_verdict(self):
        """[BEHAVIORAL] Differential attack: spec 5.6 pins normalize_verdict to
        parse_verdict SEMANTICS (optimize/role_runner.py). Run both on nasty
        raws (newline inside the FALSE token, self-correction, bare-token
        first-position traps, unparseable) and require identical outputs --
        any divergence is a measurement-semantics drift. Survived."""
        rr_path = os.path.join(LOOP_TEAM_DIR, "optimize", "role_runner.py")
        spec = importlib.util.spec_from_file_location("rr_for_parity", rr_path)
        rr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rr)
        raws = [
            "VERDICT: FALSE\nPASS",                      # \s in the token gap
            "verdict: pass\nwait, recompute\nVERDICT: FAIL",
            "VERDICT: FALSE_PASS", "verdict=false pass", "false_pass",
            "No failures; PASS",                          # first-position caveat
            "VERDICT: NOT PASS",                          # documented sharp edge
            "the artifact appears thorough", "", None,
        ]
        for raw in raws:
            assert score_fi.normalize_verdict(raw) == rr.parse_verdict(raw), (
                "normalize_verdict diverges from parse_verdict on %r" % (raw,))


class TestSurvivedDecisionTable:
    """Spec-6 decision-table boundary attacks. The standard suite has ZERO
    coverage of _decide's internals; every test here is new coverage and kills
    the </<= mutants on the band edges."""

    def _score(self, tmp_path, n_traps, n_controls, s_hits, h_hits=None,
               ctl_hits=None):
        batch = _batch(n_traps, n_controls)
        columns = {}
        for i, hits in enumerate(s_hits, 1):
            columns["sonnet_r%d" % i] = _write_column(
                tmp_path, "s%d" % i, batch, hits, ctl_hits)
        for i, hits in enumerate(h_hits or [], 1):
            columns["haiku_r%d" % i] = _write_column(
                tmp_path, "h%d" % i, batch, hits, ctl_hits)
        report = score_fi.score_columns(columns, {}, batch)
        assert report["complete"] is True
        return report["decision"]

    def test_a_s_exactly_80_is_inside_freeze_band(self, tmp_path):
        """[BEHAVIORAL] Boundary: A_s = 80.0 exactly (both rounds 16/20) is
        INSIDE [60,80] (spec rev 3 disambiguation) -> FREEZE, not gray."""
        d = self._score(tmp_path, 20, 5, s_hits=[16, 16])
        assert d["outcome"] == "FREEZE", d

    def test_a_s_rounds_straddling_80_edge_route_gray(self, tmp_path):
        """[BEHAVIORAL] Band agreement: rounds at 80% and 85% straddle the
        80 edge -> GRAY_ZONE, never the nearer row."""
        d = self._score(tmp_path, 20, 5, s_hits=[16, 17])
        assert d["outcome"] == "GRAY_ZONE", d

    def test_a_h_exactly_85_escalates_injector(self, tmp_path):
        """[BEHAVIORAL] Boundary: A_s > 90 and A_h = 85.0 exactly (17/20 both
        rounds) -> both near-ceiling -> ESCALATE_INJECTOR (spec: A_h >= 85)."""
        d = self._score(tmp_path, 20, 5, s_hits=[20, 20], h_hits=[17, 17])
        assert d["outcome"] == "ESCALATE_INJECTOR", d

    def test_a_h_exactly_75_is_kill_lane(self, tmp_path):
        """[BEHAVIORAL] Boundary: A_s > 90 and A_h = 75.0 exactly (15/20 both
        rounds) -> tier separation -> KILL_LANE (spec: A_h <= 75)."""
        d = self._score(tmp_path, 20, 5, s_hits=[20, 20], h_hits=[15, 15])
        assert d["outcome"] == "KILL_LANE", d

    def test_a_h_ambiguous_middle_80_defaults_gray(self, tmp_path):
        """[BEHAVIORAL] The probable operating point: A_s > 90, A_h = 80.0
        (16/20) sits in (75,85) -> GRAY_ZONE by default, neither row licensed."""
        d = self._score(tmp_path, 20, 5, s_hits=[20, 20], h_hits=[16, 16])
        assert d["outcome"] == "GRAY_ZONE", d

    def test_control_ok_exactly_80pct_meets_precondition(self, tmp_path):
        """[BEHAVIORAL] Boundary: control ok-rate exactly 0.80 (4/5) MEETS the
        >= 80% precondition -> FREEZE proceeds. Kills the <= mutant."""
        d = self._score(tmp_path, 20, 5, s_hits=[14, 14], ctl_hits=4)  # 70% traps
        assert d["outcome"] == "FREEZE", d

    def test_control_below_80pct_routes_gray_not_freeze(self, tmp_path):
        """[BEHAVIORAL] Control precondition: 3/5 controls ok (60%) on a tier
        the FREEZE row reads -> over-rejection -> GRAY_ZONE, never FREEZE."""
        d = self._score(tmp_path, 20, 5, s_hits=[14, 14], ctl_hits=3)
        assert d["outcome"] == "GRAY_ZONE", d

    def test_control_n_below_minimum_routes_gray(self, tmp_path):
        """[BEHAVIORAL] Minimum-n on the control subset: 4 controls (< 5), all
        ok, freeze-band traps -> GRAY_ZONE (spec sec 6 minimum-n rule)."""
        d = self._score(tmp_path, 20, 4, s_hits=[14, 14])
        assert d["outcome"] == "GRAY_ZONE", d

    def test_zero_controls_routes_gray(self, tmp_path):
        """[BEHAVIORAL] None-rate attack: a batch with ZERO controls has no
        control_ok_rate at all; a decision without a false-alarm term is not
        a decision -> GRAY_ZONE."""
        d = self._score(tmp_path, 20, 0, s_hits=[14, 14])
        assert d["outcome"] == "GRAY_ZONE", d

    def test_above_90_without_weak_tier_routes_gray(self, tmp_path):
        """[BEHAVIORAL] A_s > 90 with no haiku measurement: crude-injector vs
        competence not separable -> GRAY_ZONE (never KILL/ESCALATE)."""
        d = self._score(tmp_path, 20, 5, s_hits=[20, 20])
        assert d["outcome"] == "GRAY_ZONE", d

    def test_a_s_below_60_is_audit_suite(self, tmp_path):
        """[BEHAVIORAL] A_s < 60 (11/20 = 55% both rounds) -> AUDIT_SUITE
        (unfair-or-too-hard row), regardless of controls."""
        d = self._score(tmp_path, 20, 5, s_hits=[11, 11])
        assert d["outcome"] == "AUDIT_SUITE", d

    def test_a_h_rounds_straddling_75_edge_route_gray(self, tmp_path):
        """[BEHAVIORAL] Weak-tier band agreement: haiku rounds 15/20 (75 ->
        le_75) and 16/20 (80 -> middle) straddle the 75 edge -> GRAY_ZONE,
        not KILL_LANE."""
        d = self._score(tmp_path, 20, 5, s_hits=[20, 20], h_hits=[15, 16])
        assert d["outcome"] == "GRAY_ZONE", d
