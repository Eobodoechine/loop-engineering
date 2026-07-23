#!/usr/bin/env python3
"""AC-B5 regression tests: verifier-dispatch hygiene gate (loop_stop_guard).

Fixture (a) embeds the FULL REAL roles/verifier.md — which itself contains
its own output-format instruction (:13) and harness-green prose (:26) — proving the residue
subtraction works: role-file content never trips the gate; only Oga-ADDED
result-shaped context does. Markers built dynamically (sweep-safe)."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import pytest

HOOKS = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HOOKS, "loop_stop_guard.py")
VERIFIER_MD = os.path.expanduser("~/Claude/loop/loop-team/roles/verifier.md")


def _spec_and_hash(tmpdir, name="spec.md", content="# spec\n"):
    """[D.2 rule-1 4-tests bullet / D.3 Bucket A2's fix] Real spec-file+
    sha256 helper this file lacked entirely -- mirrors test_loop_stop_
    guard.py's own _sb_write_spec()/_sb_sha256()."""
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    return path, digest


def _span_sha256(path, line_start, line_end):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    return hashlib.sha256(
        "\n".join(lines[line_start - 1:line_end]).encode("utf-8")
    ).hexdigest()


def _plan_support_json(spec_path, spec_hash):
    return json.dumps({
        "artifact_path": spec_path,
        "line_start": 1,
        "line_end": 1,
        "evidence_sha256": _span_sha256(spec_path, 1, 1),
        "claim": "test fixture support citation for same-spec plan-check PASS",
        "spec_sha256": spec_hash,
    }, sort_keys=True)


def _supported_plan_pass(spec_path, spec_hash, extra_text=""):
    prefix = ("%s\n" % extra_text.strip()) if extra_text and extra_text.strip() else ""
    return (
        "%sPLAN_SUPPORT_JSON=%s\n"
        "REVIEWED_SPEC_SHA256=%s\n"
        "LOOP_GATE: PLAN_PASS"
    ) % (prefix, _plan_support_json(spec_path, spec_hash), spec_hash)

MK_LASTV = "last " + "verdict"
MK_DLOG = "DECISION " + "LOG"
MK_SPECI = "Spec " + "interpretation:"
MK_ALTR = "Alternatives " + "rejected:"


def _transcript(tool_uses, results=None):
    """[D.2 rule-1 4-tests bullet / D.3 Bucket A2's fix] Extended (backward-
    compatibly) to assign tool_use ids and support correlated tool_results:
    `results`, if given, is a list of (tool_use_id, content_text) pairs.
    Each result is emitted immediately after its OWN correlated dispatch
    (matched by tool_use_id) and BEFORE any later dispatch -- required so
    prior_verifier_credit()'s own windowed scan (records[pos+1:coder_pos])
    can actually see a Verifier's result as preceding a later Coder
    dispatch; the two dispatches previously used here, plus their
    intervening result, are structurally significant, not incidental
    ordering. Each dict in `tool_uses` may now optionally carry its own
    "id" key (used as the tool_use_id on the emitted event); omitted
    entirely when absent, so every pre-existing fixture (none of which set
    "id" or pass `results`) is byte-for-byte unaffected."""
    results_by_id = {}
    for tool_use_id, content_text in (results or []):
        results_by_id.setdefault(tool_use_id, []).append(content_text)
    events = [{"role": "user", "content": [{"type": "text", "text": "run the loop"}]}]
    for tu in tool_uses:
        tu_input = {k: v for k, v in tu.items() if k != "id"}
        block = {"type": "tool_use", "name": "Agent", "input": tu_input}
        tu_id = tu.get("id")
        if tu_id is not None:
            block["id"] = tu_id
        events.append({"role": "assistant", "content": [block]})
        for content_text in results_by_id.pop(tu_id, []):
            events.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tu_id, "content": content_text}]})
    # Any unmatched results (no corresponding tool_use id above) are appended
    # at the end -- should not normally happen, but fail open rather than
    # silently dropping them.
    for tool_use_id, content_texts in results_by_id.items():
        for content_text in content_texts:
            events.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tool_use_id, "content": content_text}]})
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    f.write("\n".join(json.dumps(e) for e in events))
    f.close()
    return f.name


def _run(tool_uses, results=None):
    tpath = _transcript(tool_uses, results=results)
    try:
        data = json.dumps({"transcript_path": tpath, "session_id": "hygtest"})
        return subprocess.run([sys.executable, GUARD], input=data, text=True,
                              capture_output=True, timeout=60)
    finally:
        os.unlink(tpath)


@pytest.fixture(scope="module")
def role_text():
    if not os.path.isfile(VERIFIER_MD):
        pytest.skip("verifier.md not at documented path")
    return open(VERIFIER_MD, encoding="utf-8").read()


class TestHygieneGate:
    def test_a_full_role_embed_clean_context_allows(self, role_text):
        """(a) verbatim role embed + clean Oga context -> ALLOW. Only satisfiable
        via residue subtraction: the role text contains marker phrases."""
        r = _run([{"description": "plan-check Verifier for widget spec",
                   "prompt": role_text + "\nSpec at runs/x/spec.md. Artifact: src/w.py."}])
        assert r.returncode == 0, r.stderr

    def test_b_green_leak_in_added_context_blocks(self, role_text):
        r = _run([{"description": "plan-check Verifier for widget spec",
                   "prompt": role_text + "\nContext: " + MK_LASTV + ": PASS from the harness."}])
        assert r.returncode == 2
        assert "hygiene" in r.stderr.lower()

    def test_c_pasted_decision_log_blocks(self, role_text):
        r = _run([{"description": "independent verifier for the build",
                   "prompt": role_text + "\n" + MK_DLOG + ":\n" + MK_SPECI + " "
                   "I assumed X.\n" + MK_ALTR + " Y."}])
        assert r.returncode == 2
        assert "hygiene" in r.stderr.lower()

    def test_d_spec_by_path_dispatch_allows(self):
        # fixture rebased 2026-07-01 per hlt4_fix_spec.md — spec-beside-status-docs
        # is now a correct BLOCK, see AC2. The old fixture path
        # (runs/2026-07-01_micro-step-loop/spec.md) sits beside run_log.md and
        # plan_check_log.md and is now CORRECTLY flagged by the H-LT4 adjacency
        # gate, so it no longer exercises "clean spec-by-path dispatch -> allow".
        # Re-pointed at an existing specs/-convention path that is verified real
        # and free of status docs in its own directory.
        r = _run([{"description": "plan-check Verifier for spec revision",
                   "prompt": "Read your role brief at roles/verifier.md. The full spec "
                   "is at runs/2026-07-01_hlt4-depriming-gate/specs/hlt4_fix_spec.md — "
                   "read it first. Review the plan and emit the gate line."}])
        assert r.returncode == 0, r.stderr

    def test_non_verifier_dispatch_never_scanned(self, tmp_path):
        # a clean plan-check Verifier precedes the Coder (satisfies the
        # plan-before-Coder gate); the Coder prompt carries markers — the
        # hygiene gate must not scan non-Verifier dispatches.
        #
        # [D.2/D.3 Bucket A2-fix] Both dispatches now need a real, matching
        # SPEC:/SPEC_SHA256= marker (and the Verifier a genuine, resolved
        # PLAN_PASS credit) so the now-mandatory spec-bound-credit gate
        # does not itself deny the Coder before ever reaching this test's
        # own subject (the hygiene gate's non-Verifier exclusion).
        spec_path, spec_hash = _spec_and_hash(str(tmp_path))
        r = _run([
            {"description": "plan-check Verifier for step 3 spec",
             "prompt": "Read roles/verifier.md; spec at runs/x/spec.md.\n"
                       "SPEC: %s\nSPEC_SHA256=%s" % (spec_path, spec_hash),
             "run_in_background": False, "id": "vh-nvd-verifier"},
            {"description": "Coder for step 3",
             "prompt": "roles/coder.md ... note: " + MK_LASTV + ": PASS, "
             "tests " + "passed.\nSPEC: %s\nSPEC_SHA256=%s" % (spec_path, spec_hash),
             "id": "vh-nvd-coder"},
        ], results=[("vh-nvd-verifier",
                     _supported_plan_pass(
                         spec_path, spec_hash, "Reviewed the plan."))])
        assert r.returncode == 0, r.stderr


    def test_e_dispatch_embedding_guard_source_allows(self):
        """Regression for the post-build verifier's demonstrated false positive:
        a dispatch embedding loop_stop_guard.py's OWN source (realistic when the
        repo builds on its own hooks) must not trip the gate — requires every
        marker in the guard source to be built non-contiguously."""
        guard_src = open(GUARD, encoding="utf-8").read()
        r = _run([{"description": "plan-check Verifier for hook change",
                   "prompt": "Spec at runs/x/spec.md. Artifact under review:\n"
                   + guard_src}])
        assert r.returncode == 0, r.stderr[-400:]


class TestCloneAnywherePortability:
    """AC3c: the hygiene gate must be ACTIVE from a clone at any path — the role
    base derives from the hook's own location. Both tests neutralize the
    personal-install fallback by pointing HOME at an empty temp dir, so they
    DISCRIMINATE on this machine (with the fallback live, byte-identical real
    role files would mask an unimplemented derivation)."""

    def _clone(self, tmp_path):
        import shutil
        clone = tmp_path / "clone"
        (clone / "hooks").mkdir(parents=True)
        (clone / "loop-team" / "roles").mkdir(parents=True)
        # [Section F] loop_stop_guard.py:67 does a bare `import
        # spec_bound_verifier_credit as _spec_credit` -- not previously
        # copied into the clone, so the cloned script crashed with
        # ModuleNotFoundError before producing any output. Its own single
        # dependency, verifier_hygiene_scan.py, is already present here.
        for f in ("loop_stop_guard.py", "loop_logger.py", "verifier_hygiene_scan.py",
                  "spec_bound_verifier_credit.py"):
            src = os.path.join(HOOKS, f)
            if os.path.exists(src):
                shutil.copy(src, clone / "hooks" / f)
        real = os.path.expanduser("~/Claude/loop/loop-team")
        shutil.copy(os.path.join(real, "orchestrator.md"),
                    clone / "loop-team" / "orchestrator.md")
        import glob as g
        for rf in g.glob(os.path.join(real, "roles", "*.md")):
            shutil.copy(rf, clone / "loop-team" / "roles" / os.path.basename(rf))
        return clone

    def _run_from(self, clone, tool_uses, home):
        events = [{"role": "user", "content": [{"type": "text", "text": "run"}]}]
        for tu in tool_uses:
            events.append({"role": "assistant",
                           "content": [{"type": "tool_use", "name": "Agent",
                                        "input": tu}]})
        tpath = clone / "transcript.jsonl"
        tpath.write_text("\n".join(json.dumps(e) for e in events))
        data = json.dumps({"transcript_path": str(tpath), "session_id": "clonetest"})
        env = {**os.environ, "HOME": str(home)}
        return subprocess.run([sys.executable, str(clone / "hooks" / "loop_stop_guard.py")],
                              input=data, text=True, capture_output=True,
                              timeout=60, env=env)

    def test_violation_blocks_from_temp_clone_with_neutralized_fallback(self, tmp_path):
        clone = self._clone(tmp_path)
        empty_home = tmp_path / "home"; empty_home.mkdir()
        r = self._run_from(clone, [{
            "description": "plan-check Verifier for widget",
            "prompt": "spec at runs/x/spec.md. Note: " + MK_LASTV + ": PASS."}],
            empty_home)
        assert r.returncode == 2, (r.returncode, r.stderr[-300:])
        assert "hygiene" in r.stderr.lower()

    def test_sentinel_in_clone_roles_is_subtracted_proving_derived_base(self, tmp_path):
        """Plant a marker-bearing sentinel line in the CLONE's verifier.md; if the
        gate reads the DERIVED base it subtracts the sentinel (allow); if it read
        the real install's files (fallback/hardcode) the sentinel stays in residue
        and blocks — so an allow here proves derivation."""
        clone = self._clone(tmp_path)
        empty_home = tmp_path / "home"; empty_home.mkdir()
        vmd = clone / "loop-team" / "roles" / "verifier.md"
        sentinel = "sentinel context: " + MK_LASTV + ": PASS was recorded here"
        vmd.write_text(vmd.read_text() + "\n" + sentinel + "\n")
        r = self._run_from(clone, [{
            "description": "plan-check Verifier for widget",
            "prompt": "Role brief follows:\n" + vmd.read_text()
                      + "\nSpec at runs/x/spec.md."}], empty_home)
        assert r.returncode == 0, (r.returncode, r.stderr[-300:])


class TestAdjacencyGateH_LT4:
    """H-LT4 (runs/2026-07-01_hlt4-depriming-gate/specs/hlt4_fix_spec.md): the
    deterministic Verifier-dispatch ADJACENCY gate. One test per named AC.
    Uses real tempdirs (not the residue/marker fixtures above) since this gate
    inspects the FILESYSTEM beside referenced paths, not prompt text content."""

    def _run_adj(self, tool_uses, cwd=None, session_id="adjtest", env_extra=None, results=None):
        tpath = _transcript(tool_uses, results=results)
        try:
            data = json.dumps({"transcript_path": tpath, "session_id": session_id})
            env = dict(os.environ)
            if env_extra:
                env.update(env_extra)
            return subprocess.run([sys.executable, GUARD], input=data, text=True,
                                  capture_output=True, timeout=60, cwd=cwd, env=env)
        finally:
            os.unlink(tpath)

    def test_ac1_dirty_absolute_spec_beside_handoff_blocks(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "spec.md").write_text("spec content")
        (rundir / "HANDOFF.md").write_text("handoff content")
        r = self._run_adj([{
            "description": "plan-check Verifier for widget spec",
            "prompt": "Spec at %s. Review and emit the gate line." % (rundir / "spec.md")}])
        assert r.returncode == 2, r.stderr
        assert str(rundir / "spec.md") in r.stderr
        assert "HANDOFF.md" in r.stderr

    def test_ac2_spec_moved_to_specs_subdir_allows(self, tmp_path):
        rundir = tmp_path / "rundir"
        specs = rundir / "specs"
        specs.mkdir(parents=True)
        (specs / "spec.md").write_text("spec content")
        (rundir / "HANDOFF.md").write_text("handoff content")
        r = self._run_adj([{
            "description": "plan-check Verifier for widget spec",
            "prompt": "Spec at %s. Review and emit the gate line." % (specs / "spec.md")}])
        assert r.returncode == 0, r.stderr

    def test_ac3_coder_dispatch_referencing_dirty_dir_allows(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "spec.md").write_text("spec content")
        (rundir / "HANDOFF.md").write_text("handoff content")
        # A clean plan-check Verifier must precede the Coder dispatch to satisfy
        # the separate plan-before-Coder gate (not under test here); what's
        # under test is that the ADJACENCY gate never scans the Coder dispatch
        # even though it references the dirty (HANDOFF-adjacent) spec path.
        #
        # [D.2/D.3 Bucket A2-fix] The credit chain backing the plan-before-
        # Coder gate must reference a SEPARATE, clean spec file (its own
        # directory, no adjacent status doc) -- referencing the DIRTY
        # rundir/spec.md for the marker instead would make the VERIFIER's
        # OWN dispatch (which the adjacency gate DOES scan) trip the very
        # violation this test proves the Coder dispatch is correctly
        # excluded from. The Coder's ORIGINAL dirty-path reference is kept
        # unchanged as this test's own point; the clean marker is purely
        # additive.
        clean_dir = tmp_path / "clean"
        clean_dir.mkdir()
        clean_spec, clean_hash = _spec_and_hash(str(clean_dir))
        r = self._run_adj([
            {"description": "plan-check Verifier for widget spec",
             "prompt": "Read roles/verifier.md; spec at %s.\n"
                       "SPEC: %s\nSPEC_SHA256=%s" % (clean_spec, clean_spec, clean_hash),
             "run_in_background": False, "id": "ac3-verifier"},
            {"description": "Coder for widget spec",
             "prompt": "roles/coder.md. Spec at %s. Implement it.\n"
                       "SPEC: %s\nSPEC_SHA256=%s"
                       % (rundir / "spec.md", clean_spec, clean_hash),
             "id": "ac3-coder"},
        ], results=[("ac3-verifier",
                     _supported_plan_pass(clean_spec, clean_hash, "Reviewed."))])
        assert r.returncode == 0, r.stderr

    def test_ac4_nonexistent_path_token_does_not_flag(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "spec.md").write_text("spec content")
        # HANDOFF-free real path alongside a plausible-but-absent ghost path.
        r = self._run_adj([{
            "description": "plan-check Verifier for widget spec",
            "prompt": ("Spec at %s. See also /Use" + "rs/nobody/ghost/spec.md"
                       " for background.") % (rundir / "spec.md")}])
        assert r.returncode == 0, r.stderr

    def test_ac4b_bare_relative_path_beside_handoff_blocks(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "spec.md").write_text("spec content")
        (rundir / "HANDOFF.md").write_text("handoff content")
        # bare relative token ("rundir/spec.md", no leading / or ~), resolved
        # against the hook process cwd -- so run the subprocess FROM tmp_path.
        r = self._run_adj([{
            "description": "plan-check Verifier for widget spec",
            "prompt": "Spec at rundir/spec.md. Review and emit the gate line."}],
            cwd=str(tmp_path))
        assert r.returncode == 2, r.stderr
        assert "HANDOFF.md" in r.stderr

    def test_ac4c_eval_baseline_readme_no_false_positive(self):
        # real repo path: parent dir contains verifier_verdicts.json (deliberately
        # excluded via *verdict* NOT being in the denylist) but no
        # HANDOFF/plan_check_log/decision_log/run_log/summary -- must allow.
        real_path = os.path.expanduser(
            "~/Claude/loop/loop-team/evals/baselines/README.md")
        assert os.path.isfile(real_path), "fixture path must exist: %s" % real_path
        r = self._run_adj([{
            "description": "plan-check Verifier for baseline doc",
            "prompt": "Spec at %s. Review and emit the gate line." % real_path}])
        assert r.returncode == 0, r.stderr

    def test_ac4d_symlink_evasion_via_real_parent_blocks(self, tmp_path):
        real_rundir = tmp_path / "real_rundir"
        real_rundir.mkdir()
        (real_rundir / "spec.md").write_text("spec content")
        (real_rundir / "HANDOFF.md").write_text("handoff content")
        symlink_dir = tmp_path / "symlinked_rundir"
        symlink_dir.symlink_to(real_rundir, target_is_directory=True)
        r = self._run_adj([{
            "description": "plan-check Verifier for widget spec",
            "prompt": "Spec at %s. Review and emit the gate line."
                      % (symlink_dir / "spec.md")}])
        assert r.returncode == 2, r.stderr
        assert "HANDOFF.md" in r.stderr

    def test_ac4e_run_summary_doc_adjacency_blocks(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "spec.md").write_text("spec content")
        (rundir / "run_summary.md").write_text("summary content")
        r = self._run_adj([{
            "description": "plan-check Verifier for widget spec",
            "prompt": "Spec at %s. Review and emit the gate line." % (rundir / "spec.md")}])
        assert r.returncode == 2, r.stderr
        assert "run_summary.md" in r.stderr

    def test_ac4e_summary_doc_adjacency_blocks(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "spec.md").write_text("spec content")
        (rundir / "summary.md").write_text("summary content")
        r = self._run_adj([{
            "description": "plan-check Verifier for widget spec",
            "prompt": "Spec at %s. Review and emit the gate line." % (rundir / "spec.md")}])
        assert r.returncode == 2, r.stderr
        assert "summary.md" in r.stderr


class TestAdjacencyGateSelfMatchMisfire2:
    """AC-2/AC-2b/AC-2c (research/loop-stop-guard-misfire-dossier-2026-07-08.md
    section 2, "Misfire-2 root cause"; fix_plan.md H-GUARD-6 sub-case (d) —
    see that entry's own "STILL OPEN" text, quoted in full in this build's
    report). H-LT4's own intent comment (loop_stop_guard.py lines 980-986)
    already frames the adjacency gate as being about a path that sits
    *BESIDE* a status doc — but evaluate_adjacency() does not encode that
    distinction: it never excludes the referenced target file itself from
    the directory-listing scan of its own parent, so "target IS the status
    doc" and "target sits beside an unrelated status doc" are structurally
    indistinguishable today. Every existing TestAdjacencyGateH_LT4 fixture
    above constructs the referenced token as a DISTINCT file (spec.md/
    README.md) from the status-doc file that triggers the denylist match —
    none construct the case where the referenced token IS itself the
    denylist-matching filename. This class closes that gap.

    Uses its own `_run_adj` copy (same body as TestAdjacencyGateH_LT4's),
    matching this file's existing per-class helper-duplication convention
    (see TestHygieneGate._run vs TestCloneAnywherePortability._run_from —
    distinct classes each keep their own small helper rather than sharing
    one across unrelated fixture shapes)."""

    def _run_adj(self, tool_uses, cwd=None, session_id="selfmatchtest", env_extra=None):
        tpath = _transcript(tool_uses)
        try:
            data = json.dumps({"transcript_path": tpath, "session_id": session_id})
            env = dict(os.environ)
            if env_extra:
                env.update(env_extra)
            return subprocess.run([sys.executable, GUARD], input=data, text=True,
                                  capture_output=True, timeout=60, cwd=cwd, env=env)
        finally:
            os.unlink(tpath)

    # [BEHAVIORAL] AC-2: the dispatch's OWN literal, sole read target IS the
    # status-doc-named file (plan_check_log.md) — there is no separate spec
    # being contaminated by a neighboring doc when the target IS the doc.
    # Must ALLOW (exit 0).
    def test_ac2_self_referenced_status_doc_file_does_not_flag(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "plan_check_log.md").write_text("prior plan-check verdict here\n")
        r = self._run_adj([{
            "description": "plan-check Verifier for a fact-check pass",
            "prompt": "Read %s and quote the relevant line range verbatim."
                      % (rundir / "plan_check_log.md")}])
        assert r.returncode == 0, (
            "the dispatch's sole referenced path IS plan_check_log.md itself "
            "(not a distinct spec/target sitting beside it) -- there is no "
            "separate artifact being contaminated by a neighboring status "
            "doc, so this must not be flagged as an adjacency violation. "
            "stderr=%s" % r.stderr
        )

    # [BEHAVIORAL] AC-2, real-incident variant (case (a) in the denylist —
    # handoff*/plan_check_log*/decision_log* etc. — same mechanism, different
    # denylisted filename, confirming the fix is not a plan_check_log.md-
    # specific special case).
    def test_ac2_self_referenced_handoff_file_does_not_flag(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "HANDOFF.md").write_text("decision log content\n")
        r = self._run_adj([{
            "description": "plan-check Verifier for a fact-check pass",
            "prompt": "Read %s and summarize the handoff." % (rundir / "HANDOFF.md")}])
        assert r.returncode == 0, r.stderr

    # [BEHAVIORAL] AC-2b (no regression — true positive preserved): cand is a
    # DIFFERENT file (spec.md) sitting in the same directory as a real,
    # DISTINCT plan_check_log.md — must still BLOCK exactly as today.
    # Reproduces TestAdjacencyGateH_LT4.test_ac1_dirty_absolute_spec_beside_
    # handoff_blocks's shape with plan_check_log.md (rather than HANDOFF.md)
    # as the neighbor, so both denylist entries are exercised in both
    # directions (self-match allow vs. neighbor-match block) in this class.
    def test_ac2b_distinct_target_beside_plan_check_log_still_blocks(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "spec.md").write_text("spec content")
        (rundir / "plan_check_log.md").write_text("prior plan-check verdict here\n")
        r = self._run_adj([{
            "description": "plan-check Verifier for widget spec",
            "prompt": "Spec at %s. Review and emit the gate line." % (rundir / "spec.md")}])
        assert r.returncode == 2, r.stderr
        assert str(rundir / "spec.md") in r.stderr
        assert "plan_check_log.md" in r.stderr

    # [BEHAVIORAL] AC-2c: cand is a DIRECTORY (not a file) that CONTAINS a
    # status doc — self-exclusion must apply ONLY when the candidate target
    # itself literally IS the status-doc FILE, never when it's a directory
    # that merely contains one; the existing flag-it behavior for a
    # directory target must be preserved.
    def test_ac2c_directory_candidate_containing_status_doc_still_blocks(self, tmp_path):
        rundir = tmp_path / "rundir"
        rundir.mkdir()
        (rundir / "plan_check_log.md").write_text("prior plan-check verdict here\n")
        r = self._run_adj([{
            "description": "plan-check Verifier for the run directory",
            "prompt": "Explore %s for context before reviewing." % rundir}])
        assert r.returncode == 2, r.stderr
        assert "plan_check_log.md" in r.stderr
