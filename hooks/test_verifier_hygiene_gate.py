#!/usr/bin/env python3
"""AC-B5 regression tests: verifier-dispatch hygiene gate (loop_stop_guard).

Fixture (a) embeds the FULL REAL roles/verifier.md — which itself contains
its own output-format instruction (:13) and harness-green prose (:26) — proving the residue
subtraction works: role-file content never trips the gate; only Oga-ADDED
result-shaped context does. Markers built dynamically (sweep-safe)."""
import json
import os
import subprocess
import sys
import tempfile

import pytest

HOOKS = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HOOKS, "loop_stop_guard.py")
VERIFIER_MD = os.path.expanduser("~/Claude/loop/loop-team/roles/verifier.md")

MK_LASTV = "last " + "verdict"
MK_DLOG = "DECISION " + "LOG"
MK_SPECI = "Spec " + "interpretation:"
MK_ALTR = "Alternatives " + "rejected:"


def _transcript(tool_uses):
    events = [{"role": "user", "content": [{"type": "text", "text": "run the loop"}]}]
    for tu in tool_uses:
        events.append({"role": "assistant",
                       "content": [{"type": "tool_use", "name": "Agent", "input": tu}]})
    f = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    f.write("\n".join(json.dumps(e) for e in events))
    f.close()
    return f.name


def _run(tool_uses):
    tpath = _transcript(tool_uses)
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

    def test_non_verifier_dispatch_never_scanned(self):
        # a clean plan-check Verifier precedes the Coder (satisfies the
        # plan-before-Coder gate); the Coder prompt carries markers — the
        # hygiene gate must not scan non-Verifier dispatches.
        r = _run([{"description": "plan-check Verifier for step 3 spec",
                   "prompt": "Read roles/verifier.md; spec at runs/x/spec.md."},
                  {"description": "Coder for step 3",
                   "prompt": "roles/coder.md ... note: " + MK_LASTV + ": PASS, "
                   "tests " + "passed."}])
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
        for f in ("loop_stop_guard.py", "loop_logger.py"):
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

    def _run_adj(self, tool_uses, cwd=None, session_id="adjtest", env_extra=None):
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
        r = self._run_adj([
            {"description": "plan-check Verifier for widget spec",
             "prompt": "Read roles/verifier.md; spec at runs/x/spec.md."},
            {"description": "Coder for widget spec",
             "prompt": "roles/coder.md. Spec at %s. Implement it." % (rundir / "spec.md")}])
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
