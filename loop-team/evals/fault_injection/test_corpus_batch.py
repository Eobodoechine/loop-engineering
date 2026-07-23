"""[Loop-Team Test-writer] AC5 batch-composition invariants + AC3 suite-safety
tests over the COMMITTED corpus (spec rev 5, sections 4 and 7). Micro-step S4.

These tests run against the real committed artifacts:
    loop-team/evals/cases/fi-*.json                (the curated batch)
    loop-team/evals/fault_injection/injection_log.json  (the gold manifest)

SKIP-vs-FAIL discipline (assert-nonempty-then-check, never vacuous):
  * BEFORE S4 lands there are zero fi- case files AND no manifest -> every
    test here SKIPS with an explicit reason (explicit absence).
  * A HALF-LANDED state (manifest without cases, or cases without manifest)
    is a FAILURE, not a skip -- the bijection is broken.
  * Once the batch exists, every check runs for real over a set asserted
    non-empty first. Nothing here can pass vacuously on an empty set.

PINNED operationalizations (where spec sec 4 leaves the machine check open):
  * "controls interleaved not blocked": in numeric id order the control
    positions must not form one contiguous block, and the first control must
    appear in the first two-thirds of the batch.
  * "controls' PASS provenance": each control's source_run resolves to an
    existing runs/<source_run>/ dir whose run_log.md mentions verification
    (r"(?i)verif") and a PASS token -- the deeper judgment (that the PASS was
    truly independent) is a curation duty and is flagged as partial coverage
    in the Test-writer report.
  * ">=40% deep": over INJECTED (non-control) manifest entries, difficulty
    contains "deep" (case-insensitive) for at least 40%.

AC3 note: "full pytest sweeps green" cannot be re-run from inside pytest
(recursive collection); that leg stays with verify_build.pytest_sweep and the
close-out gates -- flagged as a coverage boundary. What IS asserted here
behaviorally: the live top-level lint passes and the default (judge-less)
run_suite() is GREEN with every fi- case bucketed pending.

Python 3.9 compatible; stdlib + pytest only.
"""
import glob
import json
import os
import re
import sys

import pytest

FI_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.dirname(FI_DIR)
LOOPTEAM_DIR = os.path.dirname(EVALS_DIR)
REPO_ROOT = os.path.dirname(LOOPTEAM_DIR)
CASES_DIR = os.path.join(EVALS_DIR, "cases")
MANIFEST_PATH = os.path.join(FI_DIR, "injection_log.json")
RUNS_DIR = os.path.join(REPO_ROOT, "runs")

for _p in (EVALS_DIR, FI_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# The 7 registered defect families (spec sec 1 table) + the control tag.
KNOWN_FAMILIES = ("verdict_flip", "count_drift", "dropped_caveat",
                  "unimplemented_clause", "pipe_masked_exit",
                  "wrong_target_certification", "diff_defect")
ID_RE = re.compile(r"fi-\d{3}\Z")

INJECTED_ENTRY_KEYS = ("source_run", "source_file", "family", "difficulty",
                       "anchor", "original_snippet", "mutated_snippet", "description")


def _load_batch():
    """Load (fi_files, cases_by_id, manifest) or SKIP on explicit absence."""
    fi_files = sorted(glob.glob(os.path.join(CASES_DIR, "fi-*.json")))
    manifest_exists = os.path.exists(MANIFEST_PATH)
    if not fi_files and not manifest_exists:
        pytest.skip("S4 batch not committed yet: no evals/cases/fi-*.json and no "
                    "fault_injection/injection_log.json (explicit absence -- these "
                    "tests run for real once the batch lands; they never pass "
                    "vacuously on an empty set)")
    # Half-landed states are failures, not skips.
    assert fi_files, "injection_log.json exists but there are no fi- case files (broken bijection)"
    assert manifest_exists, "fi- case files exist but injection_log.json is missing (gold lost)"
    cases = {}
    for fp in fi_files:
        with open(fp, encoding="utf-8") as f:
            c = json.load(f)
        cases[os.path.basename(fp)[:-len(".json")]] = c
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    assert cases, "empty batch after load"
    assert manifest, "empty manifest after load"
    return fi_files, cases, manifest


def _controls(manifest):
    return {cid: e for cid, e in manifest.items() if e.get("family") == "control"}


def _injected(manifest):
    return {cid: e for cid, e in manifest.items() if e.get("family") != "control"}


# ---------------------------------------------------------------------------
# AC5 -- batch composition invariants
# ---------------------------------------------------------------------------

class TestBatchComposition:
    def test_batch_count_20_to_30(self):
        """[DOC] Spec sec 4: 20-30 cases total."""
        fi_files, cases, _ = _load_batch()
        assert 20 <= len(fi_files) <= 30, "batch size %d outside 20-30" % len(fi_files)

    def test_opaque_id_shape_and_filenames(self):
        """[DOC] Spec sec 2: opaque zero-padded ids fi-\\d{3}; filename == id;
        the id carries zero per-case signal (the regex admits no family,
        difficulty, or control token)."""
        _, cases, _ = _load_batch()
        for stem, c in cases.items():
            assert ID_RE.match(stem), "filename stem %r is not fi-NNN" % stem
            assert c.get("id") == stem, "id %r != filename stem %r" % (c.get("id"), stem)

    def test_case_field_shape(self):
        """[DOC] Every fi- case conforms to the live case format (spec sec 2):
        target verifier, requires judge, type BEHAVIORAL, suite fault_injection,
        non-empty artifact/rubric/origin, valid expected label."""
        _, cases, _ = _load_batch()
        for cid, c in cases.items():
            assert c.get("target") == "verifier", cid
            assert c.get("requires") == "judge", cid
            assert c.get("type") == "BEHAVIORAL", cid
            assert c.get("suite") == "fault_injection", cid
            assert c.get("artifact"), "%s: empty artifact" % cid
            assert c.get("rubric"), "%s: empty rubric" % cid
            assert c.get("origin"), "%s: empty origin" % cid
            assert c.get("expected") in ("PASS", "FALSE-PASS"), (
                "%s: expected %r (batch uses PASS controls / FALSE-PASS traps)"
                % (cid, c.get("expected")))

    def test_manifest_case_bijection(self):
        """[DOC] Spec sec 4: every case id has a manifest entry and every
        manifest entry resolves to an existing case file -- a bijection."""
        _, cases, manifest = _load_batch()
        assert set(manifest.keys()) == set(cases.keys()), (
            "manifest/case sets differ: only-in-manifest=%s only-in-cases=%s"
            % (sorted(set(manifest) - set(cases)), sorted(set(cases) - set(manifest))))

    def test_manifest_entry_schema(self):
        """[DOC] Spec sec 3 manifest schema: injected entries carry source_run,
        source_file, family, difficulty, anchor, original_snippet,
        mutated_snippet, description; controls carry family=control plus
        provenance (source_run)."""
        _, _, manifest = _load_batch()
        for cid, e in _injected(manifest).items():
            for k in INJECTED_ENTRY_KEYS:
                assert e.get(k) not in (None, ""), "%s: manifest missing %r" % (cid, k)
            assert e["family"] in KNOWN_FAMILIES, "%s: unknown family %r" % (cid, e["family"])
        for cid, e in _controls(manifest).items():
            assert e.get("source_run"), "%s: control lacks provenance (source_run)" % cid

    def test_family_spread_at_least_five(self):
        """[DOC] Spec sec 4: >=5 distinct injected families exercised (all 7
        implemented; minimum 5 in the batch)."""
        _, _, manifest = _load_batch()
        fams = {e["family"] for e in _injected(manifest).values()}
        assert len(fams) >= 5, "only %d families exercised: %s" % (len(fams), sorted(fams))

    def test_source_run_spread_at_least_four(self):
        """[DOC] Spec sec 4: >=4 distinct source runs across the batch."""
        _, _, manifest = _load_batch()
        runs = {e.get("source_run") for e in manifest.values() if e.get("source_run")}
        assert len(runs) >= 4, "only %d distinct source runs: %s" % (len(runs), sorted(runs))

    def test_control_fraction_quarter_to_third(self):
        """[DOC] Spec sec 4: clean controls between 1/4 and 1/3 of the batch
        (inclusive; asserted with integer arithmetic: 3c <= n <= 4c)."""
        _, cases, manifest = _load_batch()
        n = len(cases)
        c = len(_controls(manifest))
        assert c > 0, "batch has no controls -- one-sided suite"
        assert 3 * c <= n <= 4 * c, (
            "control fraction %d/%d outside [1/4, 1/3]" % (c, n))

    def test_expected_labels_match_manifest(self):
        """[DOC] Spec sec 2: injected cases are expected FALSE-PASS; clean
        controls are expected PASS -- the gold label IS the injection log."""
        _, cases, manifest = _load_batch()
        for cid, c in cases.items():
            if manifest[cid].get("family") == "control":
                assert c["expected"] == "PASS", "%s: control not expected PASS" % cid
            else:
                assert c["expected"] == "FALSE-PASS", "%s: trap not expected FALSE-PASS" % cid

    def test_controls_pass_provenance(self):
        """[DOC] Spec sec 4: controls come only from runs whose run_log records
        an independent Verifier PASS. Machine check (PINNED operationalization):
        the source_run dir exists under runs/, has a run_log.md, and that log
        mentions verification and a PASS token. Deeper independence judgment
        stays a curation duty (flagged as partial coverage).

        Oga 2026-07-02: clone-portability — private corpus absent on clean checkouts must skip, not fail."""
        _, _, manifest = _load_batch()
        if not os.path.isdir(RUNS_DIR) or not os.listdir(RUNS_DIR):
            pytest.skip("runs/ is private and absent on clean checkouts; control "
                        "provenance is checkable only on the curation machine")
        for cid, e in _controls(manifest).items():
            src = e["source_run"]
            if src.startswith("runs/"):
                src = src[len("runs/"):]
            run_dir = os.path.join(RUNS_DIR, src)
            assert os.path.isdir(run_dir), "%s: source_run %r not found under runs/" % (cid, src)
            log_path = os.path.join(run_dir, "run_log.md")
            assert os.path.isfile(log_path), "%s: %r has no run_log.md" % (cid, src)
            with open(log_path, encoding="utf-8") as f:
                log = f.read()
            assert re.search(r"(?i)verif", log), (
                "%s: run_log of %r never mentions verification" % (cid, src))
            assert re.search(r"PASS", log), (
                "%s: run_log of %r records no PASS token" % (cid, src))

    def test_deep_fraction_at_least_40pct(self):
        """[DOC] Spec sec 4 difficulty mix: >=40% of injected cases are deep."""
        _, _, manifest = _load_batch()
        injected = _injected(manifest)
        assert injected, "no injected entries"
        deep = sum(1 for e in injected.values()
                   if "deep" in str(e.get("difficulty", "")).casefold())
        frac = deep / float(len(injected))
        assert frac >= 0.4 - 1e-9, "deep fraction %.2f < 0.40 (%d/%d)" % (
            frac, deep, len(injected))

    def test_controls_interleaved_not_blocked(self):
        """[DOC] Spec sec 2: control ids must be interleaved with trap ids --
        a contiguous block of controls (e.g. all at the end) is itself a
        signal the blind export would leak."""
        _, cases, manifest = _load_batch()
        order = sorted(cases.keys())   # zero-padded ids: lexical == numeric
        flags = [manifest[cid].get("family") == "control" for cid in order]
        idx = [i for i, f in enumerate(flags) if f]
        assert idx, "no controls found"
        if len(idx) >= 2:
            assert idx[-1] - idx[0] + 1 > len(idx), (
                "controls form one contiguous id block at positions %s" % idx)
        assert idx[0] < (2 * len(order)) // 3, (
            "all controls bunched in the final third (first control at %d/%d)"
            % (idx[0], len(order)))

    def test_no_home_paths_survive_in_committed_artifacts(self):
        """[DOC] Spec sec 2 sanitizer outcome on the committed corpus: no
        absolute home-path (slash-Users or slash-home) survives in any fi- case
        or in the manifest."""
        _, cases, manifest = _load_batch()
        blob = json.dumps({"cases": cases, "manifest": manifest}, ensure_ascii=False)
        assert re.search("/Use" + "rs/[A-Za-z0-9_.-]+/", blob) is None, (
            "absolute home-path (slash-Users shape) survived sanitization")
        assert re.search("/ho" + "me/[A-Za-z0-9_.-]+/", blob) is None, (
            "absolute home-path (slash-home shape) survived sanitization")


# ---------------------------------------------------------------------------
# Blind-export safety over the real batch (spec sec 2 curation rule)
# ---------------------------------------------------------------------------

class TestBlindExportOverBatch:
    def test_export_blind_accepts_every_committed_case(self):
        """[BEHAVIORAL] The REAL replay_judge.export_blind runs over the whole
        committed batch without raising (no gold field leaks into any
        artifact; origin/rubric obey the blind-file curation rule) and yields
        exactly {id, artifact} pairs."""
        import replay_judge
        _, cases, _ = _load_batch()
        out = replay_judge.export_blind(list(cases.values()))
        assert len(out) == len(cases)
        for row in out:
            assert set(row.keys()) == {"id", "artifact"}, (
                "blind export leaked extra fields: %s" % sorted(row.keys()))


# ---------------------------------------------------------------------------
# AC3 -- suite safety with the batch present
# ---------------------------------------------------------------------------

class TestSuiteSafety:
    def test_verify_build_toplevel_lint_clean(self):
        """[BEHAVIORAL] AC3: with the batch committed, the live
        verify_build.lint_toplevel_cases passes over the real cases dir."""
        _load_batch()
        import verify_build
        ok, rep = verify_build.lint_toplevel_cases()
        assert ok, "top-level case lint problems: %s" % rep["problems"]

    def test_default_run_suite_green_all_fi_pending(self):
        """[BEHAVIORAL] AC3: the default (judge-less) run_evals.run_suite() is
        GREEN with the fi- cases present, and EVERY fi- case buckets pending
        (requires: judge with no adapter supplied). Runs the real suite
        in-process -- this includes the deterministic harness/recorded-fetch
        lanes, so it takes real time; that is the point (execute, don't grep)."""
        fi_files, _, _ = _load_batch()
        import run_evals
        report = run_evals.run_suite()
        assert report["green"], "default suite went RED with the batch present: %s" % (
            report["counts"],)
        fi_rows = [r for r in report["rows"] if str(r.get("id", "")).startswith("fi-")]
        assert len(fi_rows) == len(fi_files), (
            "run_suite saw %d fi- rows but %d fi- case files exist"
            % (len(fi_rows), len(fi_files)))
        bad = [(r["id"], r["bucket"]) for r in fi_rows if r["bucket"] != "pending"]
        assert not bad, "fi- cases must bucket pending in the judge-less run: %s" % bad
