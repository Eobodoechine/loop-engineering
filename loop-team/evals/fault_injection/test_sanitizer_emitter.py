"""[Loop-Team Test-writer] AC2 sanitizer + case-emitter tests (spec rev 5,
sections 2-3). Micro-step S3. Written BEFORE the implementation exists; these
tests FAIL (not skip) on the availability fixture until the Coder delivers
loop-team/evals/fault_injection/make_cases.py.

Public interface under test. The spec pins the BEHAVIOR (fail-closed
sanitizer, manifest-field coverage, lint-conformant emission); where it leaves
names unspecified, the SIMPLEST surface is PINNED here and the Coder must
follow it:

    make_cases.load_markers(markers_path) -> list of marker strings
        Raises ValueError if the file is MISSING, EMPTY, or contains no usable
        marker line (comment-only == empty: zero markers means the environment
        is wrong, not that there are no markers -- spec sec 2 fail-closed rule;
        do NOT inherit verify_build.pii_pattern's fail-open fallback).

    make_cases.sanitize_text(text, markers_path) -> str
        Replaces ABSOLUTE HOME PATHS (slash-Users or slash-home + <name> shapes)
        with a "<REPO"-prefixed placeholder (PINNED: the placeholder starts
        with "<REPO"); strips every marker loaded from markers_path; raises
        ValueError (via load_markers) on a missing/empty marker file BEFORE
        producing any output.

    make_cases.assert_no_markers(text, markers_path) -> None
        The explicit fail-closed gate: raises ValueError if ANY marker
        survives in `text`; returns None on clean text. The emission pipeline
        must call this on every emitted artifact and manifest string field.

    make_cases.sanitize_manifest_entry(entry, markers_path) -> dict
        Returns a new dict with every string field sanitized via
        sanitize_text -- at minimum the spec-named manifest fields
        original_snippet, mutated_snippet, source_file, description
        (spec sec 2: the sanitizer runs on every manifest string field).
        Non-string fields pass through unchanged.

    make_cases.build_case(case_id, artifact_text, expected, origin, rubric,
                          markers_path) -> dict
        Returns a lint-conformant top-level case dict with PINNED fixed
        fields: target="verifier", requires="judge", type="BEHAVIORAL",
        suite="fault_injection"; id/expected/origin/rubric as given;
        artifact/origin/rubric sanitized. Raises ValueError on an `expected`
        not in ("PASS", "FAIL", "FALSE-PASS") -- a typo'd label must never
        reach classify() -- and raises (emitting nothing) when the marker
        file is missing/empty.

Marker hygiene: every marker-like fixture string is BUILT AT RUNTIME by
concatenation (never a contiguous literal) and is fully synthetic -- no real
names, emails, or home paths. The REAL scripts/.pii-markers.local is never
touched, pointed at, or modified by these tests: the missing/empty raise
paths use a nonexistent tmp path and an empty tmp file, per AC2.

Fixture-tautology rule honored: emitted-case shape is checked against the
REAL corpus oracles -- verify_build.lint_toplevel_cases (the live lint) and
replay_judge.export_blind (the live blind-export guard) -- not against a
fixture crafted to match an imagined implementation.

Python 3.9 compatible; stdlib + pytest only.
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

_IMPORT_ERROR = None
try:
    import make_cases  # noqa: F401  (plain-module layout)
except Exception:  # noqa: BLE001
    try:
        from fault_injection import make_cases  # type: ignore  (package layout)
    except Exception as _e2:  # noqa: BLE001
        make_cases = None
        _IMPORT_ERROR = _e2


@pytest.fixture(autouse=True)
def _require_implementation():
    """FAIL (never skip) while the implementation is missing -- pre-Coder red."""
    if make_cases is None:
        pytest.fail(
            "fault_injection make_cases not importable yet (Coder has not delivered): %r"
            % (_IMPORT_ERROR,))


# ---------------------------------------------------------------------------
# Runtime-built synthetic markers (never contiguous literals; fully invented).
# ---------------------------------------------------------------------------

def _name_marker():
    return "".join(["Zeph", "yrine", " ", "Quill", "feather"])


def _email_marker():
    return "zq" + chr(64) + "nowhere-example" + ".test"


def _home_path():
    # synthetic absolute home path (no real user); built by concatenation
    return "/" + "Users" + "/" + "synthuser42" + "/proj/run_log.md"


@pytest.fixture()
def markers_path(tmp_path):
    """A synthetic marker file (comment line + two markers), like the real
    .pii-markers.local shape -- but entirely invented and in tmp."""
    p = tmp_path / "markers.local"
    p.write_text("# synthetic markers (test-only)\n%s\n%s\n"
                 % (_name_marker(), _email_marker()), encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Fail-closed marker-file loading (the missing/empty raise path -- AC2)
# ---------------------------------------------------------------------------

class TestLoadMarkersFailClosed:
    def test_missing_file_raises(self, tmp_path):
        """[BEHAVIORAL] AC2: a NONEXISTENT marker-file path raises -- never a
        fail-open fallback (verify_build.pii_pattern's tolerance is explicitly
        the wrong precedent for an emitter, spec sec 2)."""
        with pytest.raises(ValueError):
            make_cases.load_markers(str(tmp_path / "does-not-exist.local"))

    def test_empty_file_raises(self, tmp_path):
        """[BEHAVIORAL] AC2: an EMPTY marker file at emission time raises."""
        p = tmp_path / "empty.local"
        p.write_text("", encoding="utf-8")
        with pytest.raises(ValueError):
            make_cases.load_markers(str(p))

    def test_comment_only_file_raises(self, tmp_path):
        """[BEHAVIORAL] PINNED extension of the same rule: a comment-only file
        yields ZERO usable markers, which is 'empty' for fail-closed purposes
        (the rationale is 'absence means the environment is wrong')."""
        p = tmp_path / "comments.local"
        p.write_text("# only a comment, no markers\n", encoding="utf-8")
        with pytest.raises(ValueError):
            make_cases.load_markers(str(p))

    def test_loads_synthetic_markers(self, markers_path):
        """[BEHAVIORAL] Sanity: a well-formed marker file loads both markers
        and skips the comment line."""
        markers = make_cases.load_markers(markers_path)
        assert _name_marker() in markers
        assert _email_marker() in markers
        assert not any(str(m).startswith("#") for m in markers)


# ---------------------------------------------------------------------------
# sanitize_text (AC2 core)
# ---------------------------------------------------------------------------

class TestSanitizeText:
    def test_strips_marker_email_and_home_path(self, markers_path):
        """[BEHAVIORAL] AC2: a synthetic source seeded with runtime-built
        markers and an absolute home path sanitizes to text containing NONE of
        them, with a <REPO-style placeholder standing in for the path."""
        text = ("Run log excerpt (synthetic): analyst %s reviewed %s and "
                "signed off; contact %s for the trace."
                % (_name_marker(), _home_path(), _email_marker()))
        out = make_cases.sanitize_text(text, markers_path)
        assert _name_marker() not in out
        assert _email_marker() not in out
        assert "synthuser42" not in out, "absolute home path survived sanitization"
        assert "<REPO" in out, "home path must be replaced with a <REPO>-style placeholder"

    def test_raises_on_missing_marker_file_before_emitting(self, tmp_path):
        """[BEHAVIORAL] AC2: sanitize_text with a nonexistent marker path
        raises -- the sanitizer must refuse to operate rather than pass text
        through unchecked."""
        with pytest.raises(ValueError):
            make_cases.sanitize_text("any text", str(tmp_path / "gone.local"))

    def test_raises_on_empty_marker_file_before_emitting(self, tmp_path):
        """[BEHAVIORAL] AC2: sanitize_text with an EMPTY marker file raises."""
        p = tmp_path / "empty.local"
        p.write_text("", encoding="utf-8")
        with pytest.raises(ValueError):
            make_cases.sanitize_text("any text", str(p))

    def test_clean_text_passes_through_semantically(self, markers_path):
        """[BEHAVIORAL] Marker-free, path-free text is not damaged: the
        substantive content survives sanitization."""
        text = "## Gates at close\ntest sweep: 41 passed, 0 failed\nSUITE GREEN\n"
        out = make_cases.sanitize_text(text, markers_path)
        assert "41 passed, 0 failed" in out
        assert "SUITE GREEN" in out


# ---------------------------------------------------------------------------
# assert_no_markers (the explicit fail-closed gate -- 'a surviving marker raises')
# ---------------------------------------------------------------------------

class TestAssertNoMarkers:
    def test_surviving_marker_raises(self, markers_path):
        """[BEHAVIORAL] AC2 fail-closed: text still containing a marker raises
        ValueError -- the emitter must emit NOTHING containing a marker."""
        with pytest.raises(ValueError):
            make_cases.assert_no_markers(
                "final artifact text mentioning %s directly" % _name_marker(),
                markers_path)

    def test_surviving_email_marker_raises(self, markers_path):
        """[BEHAVIORAL] Same gate for the email-shaped marker."""
        with pytest.raises(ValueError):
            make_cases.assert_no_markers(
                "contact: %s" % _email_marker(), markers_path)

    def test_clean_text_does_not_raise(self, markers_path):
        """[BEHAVIORAL] Clean text passes the gate."""
        make_cases.assert_no_markers("clean synthetic artifact text", markers_path)


# ---------------------------------------------------------------------------
# sanitize_manifest_entry (AC2: the same treatment for manifest string fields)
# ---------------------------------------------------------------------------

class TestSanitizeManifestEntry:
    def test_all_named_string_fields_sanitized(self, markers_path):
        """[BEHAVIORAL] AC2: original_snippet, mutated_snippet, source_file and
        description are all sanitized -- markers and home paths seeded into
        EACH of the four fields come out clean."""
        entry = {
            "source_run": "2026-06-30_synthetic-run",
            "source_file": _home_path(),
            "family": "verdict_flip",
            "difficulty": "deep",
            "anchor": "test sweep: 41 passed",
            "original_snippet": "reviewed by %s before close" % _name_marker(),
            "mutated_snippet": "log kept at %s per %s" % (_home_path(), _email_marker()),
            "description": "synthetic injection; contact %s" % _email_marker(),
        }
        out = make_cases.sanitize_manifest_entry(entry, markers_path)
        for field in ("original_snippet", "mutated_snippet", "source_file", "description"):
            assert _name_marker() not in out[field]
            assert _email_marker() not in out[field]
            assert "synthuser42" not in out[field], (
                "home path survived in manifest field %r" % field)

    def test_non_string_fields_and_semantics_preserved(self, markers_path):
        """[BEHAVIORAL] Sanitization must not corrupt the entry: family,
        difficulty and other clean fields survive unchanged."""
        entry = {"source_run": "2026-06-30_synthetic-run", "source_file": "run_log.md",
                 "family": "count_drift", "difficulty": "shallow",
                 "anchor": "Stated: 4/4", "original_snippet": "Stated: 4/4",
                 "mutated_snippet": "Stated: 5/5", "description": "clean synthetic entry"}
        out = make_cases.sanitize_manifest_entry(entry, markers_path)
        assert out["family"] == "count_drift"
        assert out["difficulty"] == "shallow"
        assert out["mutated_snippet"] == "Stated: 5/5"

    def test_raises_on_missing_marker_file(self, tmp_path):
        """[BEHAVIORAL] The manifest path is as fail-closed as the artifact
        path: missing marker file raises before any entry is produced."""
        with pytest.raises(ValueError):
            make_cases.sanitize_manifest_entry(
                {"description": "x"}, str(tmp_path / "gone.local"))


# ---------------------------------------------------------------------------
# build_case: emitted-case lint-shape conformance (spec sec 2), checked
# against the REAL corpus oracles (fixture-tautology rule).
# ---------------------------------------------------------------------------

def _artifact():
    return (
        "# Run log -- synthetic build theta (fixture, invented content)\n"
        "## Gates at close\n"
        "test sweep: 39 passed, 0 failed (exit code: 0)\n"
        "Stated: 5/5 traps caught.\n"
        "  - trap: masked-exit\n"
        "  - trap: stale-cache\n"
        "  - trap: dropped-caveat\n"
        "  - trap: wrong-target\n"
        "## Summary\n"
        "ALL GATES GREEN -- build certified.\n"
    )


# Framing prose FIRST in origin/rubric (spec sec 2 blind-file curation rule:
# neither field may open with a >=20-char verbatim quote of the artifact).
_ORIGIN = ("Injected fixture case for the emitter test: a synthetic count drift "
           "was planted over the trap list.")
_RUBRIC = ("Framing prose for the judge oracle: the verifier should notice that "
           "the stated trap total does not reconcile with the enumerated list.")


class TestBuildCase:
    def test_case_dict_shape(self, markers_path):
        """[BEHAVIORAL] The emitted case carries the PINNED fixed fields and
        the given id/expected/origin/rubric -- the live-lint field set of
        spec sec 2 (id, expected, artifact, rubric, requires, target, type,
        suite, origin)."""
        case = make_cases.build_case("fi-101", _artifact(), "FALSE-PASS",
                                     _ORIGIN, _RUBRIC, markers_path)
        assert case["id"] == "fi-101"
        assert case["expected"] == "FALSE-PASS"
        assert case["target"] == "verifier"
        assert case["requires"] == "judge"
        assert case["type"] == "BEHAVIORAL"
        assert case["suite"] == "fault_injection"
        assert case["origin"] and case["rubric"] and case["artifact"]

    def test_real_lint_toplevel_conformance(self, markers_path, tmp_path):
        """[BEHAVIORAL] A built case, written to disk, passes the REAL
        verify_build.lint_toplevel_cases -- the live corpus linter is the
        shape oracle, not a hand-rolled schema (fixture-tautology rule)."""
        import verify_build
        case = make_cases.build_case("fi-101", _artifact(), "FALSE-PASS",
                                     _ORIGIN, _RUBRIC, markers_path)
        d = tmp_path / "cases"
        d.mkdir()
        with open(os.path.join(str(d), "fi-101.json"), "w", encoding="utf-8") as f:
            json.dump(case, f)
        ok, rep = verify_build.lint_toplevel_cases(case_dir=str(d))
        assert ok, "emitted case fails the live top-level lint: %s" % rep["problems"]

    def test_real_export_blind_accepts_built_case(self, markers_path):
        """[BEHAVIORAL] The built case passes the REAL replay_judge.export_blind
        guard (blind-file curation rule: origin/rubric must not open with a
        >=20-char verbatim artifact quote) and exports as exactly
        {id, artifact} -- gold-side fields stripped."""
        import replay_judge
        case = make_cases.build_case("fi-102", _artifact(), "FALSE-PASS",
                                     _ORIGIN, _RUBRIC, markers_path)
        out = replay_judge.export_blind([case])
        assert out == [{"id": "fi-102", "artifact": case["artifact"]}]

    def test_seeded_marker_and_path_never_reach_emitted_case(self, markers_path):
        """[BEHAVIORAL] AC2 end-to-end: an artifact seeded with a runtime-built
        marker and an absolute home path emits a case containing neither,
        anywhere in the serialized JSON."""
        dirty = _artifact() + ("\nreviewed by %s; trace at %s; contact %s\n"
                               % (_name_marker(), _home_path(), _email_marker()))
        case = make_cases.build_case("fi-103", dirty, "FALSE-PASS",
                                     _ORIGIN, _RUBRIC, markers_path)
        blob = json.dumps(case, ensure_ascii=False)
        assert _name_marker() not in blob
        assert _email_marker() not in blob
        assert "synthuser42" not in blob

    def test_bad_expected_label_raises(self, markers_path):
        """[BEHAVIORAL] A typo'd expected label ('false-pass') raises at build
        time -- classify() raising later in the suite is too late for an
        emitter that commits files (PINNED: ValueError)."""
        with pytest.raises(ValueError):
            make_cases.build_case("fi-104", _artifact(), "false-pass",
                                  _ORIGIN, _RUBRIC, markers_path)

    def test_missing_marker_file_emits_nothing(self, tmp_path):
        """[BEHAVIORAL] AC2: build_case with a missing marker file raises
        BEFORE anything is emitted (nonexistent tmp path -- the real
        scripts/.pii-markers.local is never involved)."""
        with pytest.raises(ValueError):
            make_cases.build_case("fi-105", _artifact(), "FALSE-PASS",
                                  _ORIGIN, _RUBRIC,
                                  str(tmp_path / "does-not-exist.local"))
