"""[BEHAVIORAL] Validates the CORRECTED $WT-scoped git command sequence spec
section D.5/AC9 documents for syncing `codex/loop-team-branch` -- run
entirely against a DISPOSABLE SCRATCH repo reproducing this repo's topology
(a `main` branch several commits ahead of a strict-ancestor branch, with the
original clone left checked out on `main` throughout), never touching the
real ~/Claude/loop repo.

Spec: loop-team/runs/2026-07-09_reconcile-json-persistence/specs/spec.md,
section D.5 / acceptance criterion 9.

*** SCOPE NOTE -- read before treating a green result here as "AC9 is
implemented" ***: AC9/D.5 describes a ONE-TIME MANUAL git operation Oga/
Nnamdi runs once against the real ~/Claude/loop repo. There is no persistent
code artifact in this spec's Coder deliverable that implements this
procedure -- no `sync_branch.py` module, no CLI flag, nothing importable.
This test therefore validates the CORRECTED PROCEDURE'S LOGIC in an isolated
scratch repo (useful as a regression guard against re-introducing the exact
`-C <original-clone>` no-op bug D.5 reproduced empirically) -- it does NOT
gate on, and will not change status based on, anything the Coder implements
for this spec's other acceptance criteria (the --out flag, the doc edits).
It is expected to PASS today and to keep passing after the Coder's change,
since nothing in the codebase itself changes for AC9's own procedure -- this
is a runbook-correctness check, not an implementation-verification test.
Flagging this distinction explicitly per the dispatching brief's request
rather than silently treating it as equivalent BEHAVIORAL coverage of the
Coder's build.

Run with:
    python3 -m pytest loop-team/harness/test_d5_branch_sync_procedure.py -v
"""
import os
import shutil
import subprocess
import tempfile
import unittest


def _git(cwd, *args, check=True):
    proc = subprocess.run(
        ["git"] + list(args), cwd=cwd, capture_output=True, text=True,
    )
    if check and proc.returncode != 0:
        raise AssertionError(
            "git %s failed (cwd=%s): %s" % (" ".join(args), cwd, proc.stderr)
        )
    return proc


class TestD5CorrectedBranchSyncSequence(unittest.TestCase):
    """Reproduces the exact topology spec section B documents (the ancestor
    branch is a strict, zero-unique-commits ancestor of main) in a scratch
    repo, then runs the AC9-corrected $WT-scoped sequence and asserts a
    genuine fast-forward -- plus separately reproduces the BUGGY variant
    (merging against the original clone instead of $WT) to confirm it is a
    provable silent no-op, matching D.5's own empirical repro."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="d5-scratch-repo-")
        self.origin = os.path.join(self.tmpdir, "origin-clone")
        os.makedirs(self.origin)
        _git(self.origin, "init", "-b", "main")
        _git(self.origin, "config", "user.email", "test@example.com")
        _git(self.origin, "config", "user.name", "Test")
        _git(self.origin, "config", "commit.gpgsign", "false")

        with open(os.path.join(self.origin, "f.txt"), "w") as f:
            f.write("commit1\n")
        _git(self.origin, "add", "f.txt")
        _git(self.origin, "commit", "-m", "commit1")

        # Branch off HERE -- this is the "ancestor" branch's tip. It gains
        # zero commits of its own from this point forward.
        _git(self.origin, "branch", "ancestor-branch")

        # 2 more commits on main only, reproducing "main several commits
        # ahead of a strict-ancestor branch" (spec section B's confirmed
        # git-branch-state topology).
        for n in (2, 3):
            with open(os.path.join(self.origin, "f.txt"), "w") as f:
                f.write("commit%d\n" % n)
            _git(self.origin, "add", "f.txt")
            _git(self.origin, "commit", "-m", "commit%d" % n)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _rev(self, ref):
        return _git(self.origin, "rev-parse", ref).stdout.strip()

    def test_scratch_repo_topology_is_a_strict_fast_forward_ancestor(self):
        # Sanity-check the fixture matches spec section B's topology before
        # trusting the procedure test below against it.
        proc = _git(
            self.origin, "merge-base", "--is-ancestor", "ancestor-branch",
            "main", check=False,
        )
        self.assertEqual(
            proc.returncode, 0,
            "ancestor-branch must be a strict ancestor of main in this "
            "fixture, matching spec section B's confirmed topology",
        )
        log = _git(self.origin, "log", "main..ancestor-branch", "--oneline")
        self.assertEqual(
            log.stdout.strip(), "",
            "ancestor-branch must have zero unique commits of its own",
        )

    def test_buggy_variant_merging_against_original_clone_is_a_silent_noop(self):
        # The exact bug D.5 documents: running `git -C <original-clone>
        # merge main` while the original clone stays checked out on `main`
        # (never on ancestor-branch) is a no-op that still exits 0 --
        # printing "Already up to date." while ancestor-branch's own tip
        # never moves.
        before = self._rev("ancestor-branch")
        proc = _git(self.origin, "merge", "main")
        self.assertIn("Already up to date", proc.stdout)
        self.assertEqual(proc.returncode, 0)
        after = self._rev("ancestor-branch")
        self.assertEqual(
            before, after,
            "the buggy -C <original-clone> merge must NOT move "
            "ancestor-branch's tip -- it silently merges main into itself",
        )

    def test_corrected_wt_scoped_sequence_produces_genuine_fast_forward(self):
        wt = os.path.join(self.tmpdir, "wt-ancestor-branch")
        before = self._rev("ancestor-branch")
        main_tip = self._rev("main")

        # Step 1 (read-only, -C <original-clone> is correct here): confirm
        # no live worktree already has ancestor-branch checked out.
        listing = _git(self.origin, "worktree", "list")
        self.assertNotIn("ancestor-branch", listing.stdout)

        # Step 2 (write -- creates $WT from the original clone's metadata).
        _git(self.origin, "worktree", "add", wt, "ancestor-branch")

        # Step 3 (write -- must target $WT, never the original clone, per
        # AC9's corrected sequence).
        merge_proc = _git(wt, "merge", "main")
        self.assertIn(
            "Fast-forward", merge_proc.stdout,
            "merging main into $WT (checked out on ancestor-branch) must "
            "produce a genuine Fast-forward, per spec D.5's confirmed "
            "ancestor relationship",
        )

        # Step 4 (read-only verification, -C <original-clone> is correct
        # here): the ref actually advanced and now matches main.
        after = self._rev("ancestor-branch")
        self.assertNotEqual(
            before, after,
            "ancestor-branch's ref must actually advance after the "
            "corrected $WT-scoped merge",
        )
        self.assertEqual(after, main_tip)

        # Step 5 (write -- removes $WT, not the original clone).
        _git(self.origin, "worktree", "remove", wt)
        listing_after = _git(self.origin, "worktree", "list")
        self.assertNotIn(wt, listing_after.stdout)
        self.assertFalse(os.path.exists(wt))


if __name__ == "__main__":
    unittest.main()
