"""Tests for reality_gate.py -- the unfakeable "verified" writer.

Spec: loop-team/runs/2026-07-11_reality-gate/spec.md (Revision 1). Covers
AC1-AC14 plus plan-check R2 caveats N2 and N4. Every behavioral criterion is
exercised by EXECUTING the real CLI against throwaway git repos built in-test
(real commits, `--allow-empty` empty commits, and commits that ADD vs REMOVE a
line containing a target substring) -- not by grepping the artifact.

Written BEFORE the implementation exists (harness/reality_gate.py is not yet
built) -- these tests are EXPECTED to fail now: the subprocess invocation of a
missing script exits non-zero with an interpreter "can't open file" error and
prints no JSON, so `data` is None and the first assertion trips. That is
correct per the Test-writer role brief (Tier 1, spec-only, runs before the
Coder).

Assumed result JSON contract (the public interface the Coder implements to; a
Test-writer's prerogative to pin -- the spec fixes the reason tokens and the
per-check names, this pins where they land):
  `check` / `verify` print a single JSON object to stdout with:
    - "passed": bool  (logical AND over the checks that ran)
    - "commit": str    (the resolved concrete sha of --commit)
    - "checks": { "commit-is-real": bool,
                  "substring-present": bool,   # only when --expect-substring
                  "test-passes": bool }        # only when --test-cmd
    - a failure reason token appears somewhere in stdout for the spec-named
      failures: "no-binding-check", "test-timeout", "bad-status-json".
  Exit codes: 0 pass, 1 check-failed, 2 usage / not-found / bad-status-json.

Isolation:
  - Every git repo is a throwaway `git init` inside a pytest tmp_path. Never
    the real ~/Claude/loop repo.
  - Every fixture git commit pins `-c user.email=/-c user.name=/-c
    commit.gpgsign=false` so tests never depend on or contaminate host config.
    (reality_gate.py itself only runs READ-ONLY git -- show/rev-parse -- so the
    tool needs no committer identity.)
  - status.json fixtures are written with the spec's PINNED serializer
    (indent=2, ensure_ascii=False, sort_keys=False, one trailing newline) so
    byte-for-byte comparisons are meaningful.

Run: python3 -m pytest loop-team/harness/test_reality_gate.py -q
"""
import copy
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "reality_gate.py")

NOW = "2026-07-11T00:00:00Z"  # pinned --now so `updated` is deterministic

GIT_CFG = [
    "-c", "user.email=test@example.com",
    "-c", "user.name=Test Writer",
    "-c", "commit.gpgsign=false",
]


# ---------------------------------------------------------------------------
# Serialization helper -- the spec's PINNED serializer (§Serialization)
# ---------------------------------------------------------------------------

def _dumps(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n"


def _write_status(path, obj):
    with open(str(path), "w", encoding="utf-8") as f:
        f.write(_dumps(obj))


def _read_bytes(path):
    with open(str(path), "rb") as f:
        return f.read()


def _read_text(path):
    with open(str(path), "r", encoding="utf-8") as f:
        return f.read()


def _load(path):
    with open(str(path), "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# status.json fixture builders
# ---------------------------------------------------------------------------

def _item(id_, title, extra=None):
    """A schema item with keys in the spec's declared order."""
    d = {
        "id": id_,
        "title": title,
        "phase": "must",
        "status": "claimed",
        "verified": False,
        "priority": 1,
        "problems": [{"desc": "", "evidence": ""}],
        "evidence": {"commit": None, "test": None, "log": None},
    }
    if extra:
        d.update(extra)  # appended last -> insertion order preserved
    return d


def _status(items):
    return {
        "product": "TaxAhead",
        "done_sentence": "the live working core flow",
        "updated": None,
        "items": items,
    }


# ---------------------------------------------------------------------------
# git repo helpers -- REAL git subprocess, throwaway repos
# ---------------------------------------------------------------------------

def _git(repo, *args, check=True):
    return subprocess.run(
        ["git"] + GIT_CFG + list(args),
        cwd=str(repo), check=check, capture_output=True, text=True,
    )


def _init_repo(repo):
    os.makedirs(str(repo), exist_ok=True)
    subprocess.run(["git", "init"], cwd=str(repo), check=True,
                   capture_output=True, text=True)
    _git(repo, "commit", "--allow-empty", "-m", "init")
    return repo


def _head(repo):
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _write_file(repo, name, text):
    with open(os.path.join(str(repo), name), "w", encoding="utf-8") as f:
        f.write(text)


def _commit_adding_line(repo, name, line, msg="add line"):
    """Create/append a file so `line` appears on an ADDED (+) patch line, and
    is present in the committed blob. Returns the resolved full sha."""
    path = os.path.join(str(repo), name)
    prior = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            prior = f.read()
    with open(path, "w", encoding="utf-8") as f:
        f.write(prior + line + "\n")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", msg)
    return _head(repo)


def _commit_removing_line(repo, name, marker):
    """Seed a file containing `marker`, then commit a change that REMOVES the
    marker line. In the removal commit the marker appears only on a `-` line
    and is absent from both the added lines and the committed blob. Returns the
    resolved full sha of the removal commit."""
    _write_file(repo, name, "keep-a\n" + marker + "\nkeep-b\n")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", "seed with marker")
    _write_file(repo, name, "keep-a\nkeep-b\n")  # marker line removed
    _git(repo, "add", name)
    _git(repo, "commit", "-m", "remove marker line")
    return _head(repo)


# ---------------------------------------------------------------------------
# CLI runner
# ---------------------------------------------------------------------------

def _run(args, timeout=60):
    """Invoke: python3 reality_gate.py <args...>.
    Returns (exit_code, parsed_json_or_None, raw_stdout, raw_stderr)."""
    p = subprocess.run(
        [sys.executable, SCRIPT] + [str(a) for a in args],
        capture_output=True, text=True, timeout=timeout,
    )
    try:
        data = json.loads(p.stdout)
    except (json.JSONDecodeError, ValueError):
        data = None
    return p.returncode, data, p.stdout, p.stderr


def _checks(data):
    return (data or {}).get("checks", {}) if isinstance(data, dict) else {}


# ===========================================================================
# AC1 / AC11 -- Core invariant: no verified:true without a supplied binding
#               check that passed. The 4-member binding arg-class.
# ===========================================================================

class TestAC1AC11BindingArgClass:
    """[BEHAVIORAL] [SECURITY-ORACLE] The full 4-member binding arg-class of
    `verify`: (a) neither substring nor test -> exit 2 no-binding-check, no
    write; (b) substring-only can verify; (c) test-only can verify; (d) both
    must pass. This is the core security invariant (AC1) + LOOP-M5 class-close
    (AC11). Flagged for Tier-2 mutation-oracle check."""

    def test_a_neither_binding_check_exit2_no_binding_and_no_write(self, tmp_path):
        # [SECURITY-ORACLE] member (a): commit-is-real alone must NEVER verify.
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "some real change")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))
        before = _read_bytes(sp)

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
        ])

        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert "no-binding-check" in out, out
        assert _read_bytes(sp) == before, "status.json must be untouched"
        assert _load(sp)["items"][0]["verified"] is False

    def test_b_substring_only_can_verify(self, tmp_path):
        # member (b): substring is an item-binding check; can produce verified.
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "line with UNIQUE_MARKER_B in it")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "UNIQUE_MARKER_B", "--now", NOW,
        ])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        item = _load(sp)["items"][0]
        assert item["verified"] is True
        assert item["status"] == "fixed"
        assert item["evidence"]["test"] is None  # no test supplied

    def test_c_test_only_can_verify(self, tmp_path):
        # member (c): test-cmd is an item-binding check; can produce verified.
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "any real change")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--test-cmd", "true", "--now", NOW,
        ])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        item = _load(sp)["items"][0]
        assert item["verified"] is True
        assert item["evidence"]["test"] == "true"

    def test_d_both_supplied_both_must_pass(self, tmp_path):
        # member (d): both supplied and both pass -> verified.
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "line with BOTH_MARKER present")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "BOTH_MARKER", "--test-cmd", "true",
            "--now", NOW,
        ])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert _load(sp)["items"][0]["verified"] is True

    def test_d_both_supplied_one_failing_does_not_verify(self, tmp_path):
        # [SECURITY-ORACLE] member (d), failing case: substring present but
        # test fails -> overall fail, no verified:true.
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "line with BOTH_MARKER present")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "BOTH_MARKER", "--test-cmd", "false",
            "--now", NOW,
        ])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert _load(sp)["items"][0]["verified"] is False

    def test_substring_absent_does_not_verify(self, tmp_path):
        # [SECURITY-ORACLE] failing-check case: substring genuinely not in the
        # diff -> no verified:true (the real honest-hallucination threat).
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "a real change without the token")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "NOT_IN_THE_DIFF", "--now", NOW,
        ])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert _checks(data).get("substring-present") is False
        assert _load(sp)["items"][0]["verified"] is False


# ===========================================================================
# AC2 -- Phantom (empty) commit rejected by commit-is-real.
# ===========================================================================

class TestAC2PhantomCommitRejected:
    """[BEHAVIORAL] `git commit --allow-empty` -> commit-is-real fails;
    check/verify exit non-zero, no verified:true."""

    def test_check_rejects_empty_commit(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "commit", "--allow-empty", "-m", "phantom, no file changes")

        code, data, out, err = _run([
            "check", "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "anything",
        ])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert data is not None, f"stdout={out!r} stderr={err!r}"
        assert data.get("passed") is False
        assert _checks(data).get("commit-is-real") is False

    def test_verify_rejects_empty_commit_no_verified(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _git(repo, "commit", "--allow-empty", "-m", "phantom")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "anything", "--now", NOW,
        ])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert _load(sp)["items"][0]["verified"] is False


# ===========================================================================
# AC3 -- Happy path writes verified with resolved sha.
# ===========================================================================

class TestAC3HappyPathWritesVerified:
    """[BEHAVIORAL] Real commit + expected substring on an ADDED line + passing
    test-cmd -> item verified:true, status:"fixed", evidence.commit == resolved
    full sha, exit 0."""

    def test_happy_path_full(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        sha = _commit_adding_line(repo, "f.txt", "added HAPPY_TOKEN here")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "HAPPY_TOKEN", "--test-cmd", "true",
            "--now", NOW,
        ])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert data.get("passed") is True
        item = _load(sp)["items"][0]
        assert item["verified"] is True
        assert item["status"] == "fixed"
        assert item["evidence"]["commit"] == sha
        assert len(sha) == 40 and sha != "HEAD"
        assert item["evidence"]["test"] == "true"
        assert _load(sp)["updated"] == NOW


# ===========================================================================
# AC4 -- Exit-code honesty (real returncode, not masked by a pipe).
# ===========================================================================

class TestAC4ExitCodeHonesty:
    """[BEHAVIORAL] `--test-cmd 'false'` fails (the real returncode is read
    directly, even though `false | tail` would mask it)."""

    def test_false_test_cmd_fails(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "a real change")

        code, data, out, err = _run([
            "check", "--repo", repo, "--commit", "HEAD", "--test-cmd", "false",
        ])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert data.get("passed") is False
        assert _checks(data).get("test-passes") is False

    def test_true_test_cmd_passes(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "a real change")

        code, data, out, err = _run([
            "check", "--repo", repo, "--commit", "HEAD", "--test-cmd", "true",
        ])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert data.get("passed") is True
        assert _checks(data).get("test-passes") is True


# ===========================================================================
# AC5 -- Value-preserving, atomic write.
# ===========================================================================

class TestAC5ValuePreservingAtomicWrite:
    """[BEHAVIORAL] After a verify write: every other item and every unknown
    key is preserved (json.load equality); with the pinned serializer the whole
    file is byte-identical except the target item's changed fields + top-level
    updated; no truncated/temp files left behind (temp+replace)."""

    def _two_item_status_with_unknowns(self):
        return {
            "product": "TaxAhead",
            "done_sentence": "core flow",
            "updated": None,
            "x_custom_top": {"nested": [1, 2, 3], "note": "preserve me"},
            "items": [
                _item("must-1", "story one", extra={"x_item_extra": "keep-me"}),
                _item("must-2", "story two", extra={"x_item_extra2": "keep-me-too"}),
            ],
        }

    def test_json_load_equality_preserves_others(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "added PRESERVE_TOKEN here")
        statusdir = tmp_path / "statusdir"
        statusdir.mkdir()
        sp = statusdir / "status.json"
        obj = self._two_item_status_with_unknowns()
        _write_status(sp, obj)

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "PRESERVE_TOKEN", "--now", NOW,
        ])
        assert code == 0, f"stdout={out!r} stderr={err!r}"

        loaded = _load(sp)
        # Untouched second item preserved value/key/order.
        assert loaded["items"][1] == obj["items"][1]
        # Unknown top-level key preserved.
        assert loaded["x_custom_top"] == obj["x_custom_top"]
        # Target item's unknown key preserved; only known fields changed.
        assert loaded["items"][0]["x_item_extra"] == "keep-me"
        assert loaded["items"][0]["verified"] is True
        assert loaded["items"][0]["status"] == "fixed"

    def test_full_file_byte_identical_except_target_and_updated(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        sha = _commit_adding_line(repo, "f.txt", "added PRESERVE_TOKEN here")
        statusdir = tmp_path / "statusdir"
        statusdir.mkdir()
        sp = statusdir / "status.json"
        obj = self._two_item_status_with_unknowns()
        _write_status(sp, obj)

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "PRESERVE_TOKEN", "--test-cmd", "true",
            "--now", NOW,
        ])
        assert code == 0, f"stdout={out!r} stderr={err!r}"

        expected = copy.deepcopy(obj)
        expected["updated"] = NOW
        it = expected["items"][0]
        it["status"] = "fixed"
        it["verified"] = True
        it["evidence"] = {"commit": sha, "test": "true", "log": None}

        assert _read_text(sp) == _dumps(expected)

    def test_no_temp_files_left_behind(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "added PRESERVE_TOKEN here")
        statusdir = tmp_path / "statusdir"
        statusdir.mkdir()
        sp = statusdir / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "PRESERVE_TOKEN", "--now", NOW,
        ])
        assert code == 0, f"stdout={out!r} stderr={err!r}"
        # Atomic temp+replace leaves only the final file behind, and the file
        # always parses (never a truncated mid-write).
        assert os.listdir(str(statusdir)) == ["status.json"]
        assert _load(sp)["items"][0]["verified"] is True


# ===========================================================================
# AC6 -- Item lookup: by id, then exact title; missing/ambiguous -> exit 2.
# ===========================================================================

class TestAC6ItemLookup:
    """[BEHAVIORAL] Match by id; else exact title; missing or ambiguous ->
    exit 2, no write."""

    def test_lookup_by_id(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "added LOOKUP_TOKEN here")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([
            _item("must-1", "first story"),
            _item("must-2", "second story"),
        ]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-2",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "LOOKUP_TOKEN", "--now", NOW,
        ])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        loaded = _load(sp)
        assert loaded["items"][1]["verified"] is True
        assert loaded["items"][0]["verified"] is False  # only the matched one

    def test_lookup_by_exact_title_when_no_id_match(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "added LOOKUP_TOKEN here")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "the exact title here")]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "the exact title here",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "LOOKUP_TOKEN", "--now", NOW,
        ])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert _load(sp)["items"][0]["verified"] is True

    def test_missing_item_exit2_no_write(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "added LOOKUP_TOKEN here")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "first story")]))
        before = _read_bytes(sp)

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "no-such-item",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "LOOKUP_TOKEN", "--now", NOW,
        ])

        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert data is not None, f"expected error JSON on stdout: {out!r} {err!r}"
        assert _read_bytes(sp) == before, "no write on missing item"

    def test_ambiguous_title_exit2_no_write(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "added LOOKUP_TOKEN here")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([
            _item("must-1", "dup story"),
            _item("must-2", "dup story"),
        ]))
        before = _read_bytes(sp)

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "dup story",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "LOOKUP_TOKEN", "--now", NOW,
        ])

        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert data is not None, f"expected error JSON on stdout: {out!r} {err!r}"
        assert _read_bytes(sp) == before, "no write on ambiguous title"


# ===========================================================================
# AC7 -- check writes nothing (no --status-json, no file mutation).
# ===========================================================================

class TestAC7CheckWritesNothing:
    """[BEHAVIORAL] `check` takes no --status-json; no status.json bytes/mtime
    change from any check run."""

    def test_check_does_not_touch_status_json(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "added CHECK_TOKEN here")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))
        before_bytes = _read_bytes(sp)
        before_mtime = os.path.getmtime(str(sp))

        # A variety of check invocations, none of which may write status.json.
        # Assert each actually RAN (emitted JSON) so a missing/crashing script
        # cannot pass this test by never touching the file.
        c1, d1, o1, e1 = _run(["check", "--repo", repo, "--commit", "HEAD",
                               "--expect-substring", "CHECK_TOKEN"])
        c2, d2, o2, e2 = _run(["check", "--repo", repo, "--commit", "HEAD",
                               "--test-cmd", "true"])
        c3, d3, o3, e3 = _run(["check", "--repo", repo, "--commit", "HEAD",
                               "--test-cmd", "false"])
        assert d1 is not None and d2 is not None and d3 is not None, (
            f"check must emit JSON: {o1!r} {o2!r} {o3!r}")

        assert _read_bytes(sp) == before_bytes
        assert os.path.getmtime(str(sp)) == before_mtime

    def test_check_no_binding_requirement_commit_only_passes(self, tmp_path):
        # check imposes NO binding-check requirement: commit-is-real alone on a
        # real commit passes (exit 0). (Contrast verify, which requires binding.)
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "a real change")

        code, data, out, err = _run(["check", "--repo", repo, "--commit", "HEAD"])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert data.get("passed") is True
        assert _checks(data).get("commit-is-real") is True


# ===========================================================================
# AC8 -- Timeout is a failure, not a hang.
# ===========================================================================

class TestAC8TimeoutIsFailure:
    """[BEHAVIORAL] `--test-cmd 'sleep 5' --test-timeout 1` -> reason
    "test-timeout", exit 1."""

    def test_test_timeout_fails(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "a real change")

        code, data, out, err = _run([
            "check", "--repo", repo, "--commit", "HEAD",
            "--test-cmd", "sleep 5", "--test-timeout", "1",
        ], timeout=30)

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert "test-timeout" in out, out
        assert _checks(data).get("test-passes") is False


# ===========================================================================
# AC9 -- Interface documented (DOC).
# ===========================================================================

class TestAC9InterfaceDocumented:
    """[DOC] Module docstring documents all 3 subcommands, flags, exit codes."""

    def test_module_docstring_documents_subcommands_and_exit_codes(self):
        # Fails now because reality_gate.py does not exist yet.
        text = _read_text(SCRIPT)
        head = text[:4000].lower()
        for token in ("check", "verify", "init-status", "exit"):
            assert token in head, f"docstring must document {token!r}"


# ===========================================================================
# AC10 -- init-status never clobbers.
# ===========================================================================

class TestAC10InitStatusNeverClobbers:
    """[BEHAVIORAL] init-status on an existing path -> exit 2, file unchanged;
    on a fresh path -> creates a valid skeleton with empty items."""

    def test_existing_path_exit2_unchanged(self, tmp_path):
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "existing")]))
        before = _read_bytes(sp)

        code, data, out, err = _run([
            "init-status", "--path", sp,
            "--product", "TaxAhead", "--done", "the working flow",
        ])

        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert data is not None, f"expected error JSON on stdout: {out!r} {err!r}"
        assert _read_bytes(sp) == before, "existing file must be untouched"

    def test_fresh_path_creates_valid_skeleton(self, tmp_path):
        sp = tmp_path / "fresh_status.json"
        assert not sp.exists()

        code, data, out, err = _run([
            "init-status", "--path", sp,
            "--product", "MyProduct", "--done", "the live working core flow",
        ])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert sp.exists()
        skeleton = _load(sp)  # must parse
        assert skeleton["product"] == "MyProduct"
        assert skeleton["done_sentence"] == "the live working core flow"
        assert skeleton["items"] == []
        # One trailing newline (pinned serializer).
        assert _read_text(sp).endswith("\n")


# ===========================================================================
# AC12 -- substring matches ADDED lines only; --expect-file matches the blob.
# ===========================================================================

class TestAC12SubstringAddedLinesOnly:
    """[BEHAVIORAL] A commit that REMOVES a line containing the substring
    (substring absent from added lines and from the committed blob) ->
    substring-present FAILS. And --expect-file matches the committed blob even
    when the patch context differs."""

    def test_removed_line_substring_not_matched(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_removing_line(repo, "f.txt", "REMOVED_MARKER on this line")

        code, data, out, err = _run([
            "check", "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "REMOVED_MARKER",
        ])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert _checks(data).get("substring-present") is False

    def test_expect_file_matches_blob_when_only_in_context(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        # Seed a file whose blob contains BLOB_MARKER.
        _write_file(repo, "f.txt", "BLOB_MARKER on line one\nfiller\n")
        _git(repo, "add", "f.txt")
        _git(repo, "commit", "-m", "seed with blob marker")
        # New commit ADDS an unrelated line far away; BLOB_MARKER appears only
        # as unchanged CONTEXT in this commit's patch, but IS in the blob.
        _write_file(repo, "f.txt",
                    "BLOB_MARKER on line one\nfiller\nnewly added tail line\n")
        _git(repo, "add", "f.txt")
        _git(repo, "commit", "-m", "append tail")

        # Patch mode: BLOB_MARKER is only in context -> FAIL.
        code_patch, data_patch, out_p, err_p = _run([
            "check", "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "BLOB_MARKER",
        ])
        assert code_patch == 1, f"stdout={out_p!r} stderr={err_p!r}"
        assert _checks(data_patch).get("substring-present") is False

        # Expect-file mode: checks the committed blob -> PASS.
        code_blob, data_blob, out_b, err_b = _run([
            "check", "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "BLOB_MARKER", "--expect-file", "f.txt",
        ])
        assert code_blob == 0, f"stdout={out_b!r} stderr={err_b!r}"
        assert _checks(data_blob).get("substring-present") is True


# ===========================================================================
# AC13 -- malformed status.json fails closed.
# ===========================================================================

class TestAC13MalformedStatusFailsClosed:
    """[BEHAVIORAL] verify against a corrupt JSON file -> exit 2
    "bad-status-json", file unchanged, no traceback/partial write."""

    def test_corrupt_status_json_exit2_unchanged(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "added GOOD_TOKEN here")
        sp = tmp_path / "status.json"
        with open(str(sp), "w", encoding="utf-8") as f:
            f.write("{ this is : not valid json,,, ]")
        before = _read_bytes(sp)

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "GOOD_TOKEN", "--now", NOW,
        ])

        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert "bad-status-json" in out, out
        assert _read_bytes(sp) == before, "corrupt file must be left unchanged"
        # No unhandled traceback surfaced to stderr.
        assert "Traceback" not in err, err


# ===========================================================================
# AC14 -- fail-path downgrade of a previously-verified item.
# ===========================================================================

class TestAC14FailPathDowngrade:
    """[BEHAVIORAL] [SECURITY-ORACLE] Given an item already verified:true, a
    verify whose check fails sets it back to verified:false, exit 1, no
    verified:true anywhere. (N3 intended fail-safe-toward-less-verified.)"""

    def test_failing_reverify_downgrades_to_false(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "a real change")
        sp = tmp_path / "status.json"
        # Item starts already verified:true (as if a prior pass wrote it).
        item = _item("must-1", "story one")
        item["verified"] = True
        item["status"] = "fixed"
        _write_status(sp, _status([item]))

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD",
            "--test-cmd", "false", "--now", NOW,
        ])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        loaded = _load(sp)
        assert loaded["items"][0]["verified"] is False
        # No verified:true anywhere in the written file.
        assert all(it["verified"] is False for it in loaded["items"])


# ===========================================================================
# N2 -- substring semantics: leading '+' stripped; no cross-line matching.
# ===========================================================================

class TestN2SubstringSemantics:
    """[BEHAVIORAL] [SECURITY-ORACLE] The leading '+' of an added patch line is
    stripped before matching (so `--expect-substring "+foo"` does NOT match an
    added line whose content is `foo`), and a substring must not span the
    boundary between two added lines."""

    def test_leading_plus_is_stripped_not_matched(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        # Added line content is exactly `foo`; its patch representation is `+foo`.
        _commit_adding_line(repo, "f.txt", "foo")

        code, data, out, err = _run([
            "check", "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "+foo",
        ])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert _checks(data).get("substring-present") is False, (
            "must not match merely because the patch line reads '+foo'"
        )

    def test_substring_must_not_span_two_added_lines(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        # Two consecutive added lines: 'foo' then 'bar'.
        path = os.path.join(str(repo), "f.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("foo\nbar\n")
        _git(repo, "add", "f.txt")
        _git(repo, "commit", "-m", "add foo and bar lines")

        # 'foobar' spans the boundary of two separate added lines -> no match.
        code, data, out, err = _run([
            "check", "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "foobar",
        ])

        assert code == 1, f"stdout={out!r} stderr={err!r}"
        assert _checks(data).get("substring-present") is False

    def test_single_added_line_substring_matches(self, tmp_path):
        # Positive control: the substring within ONE added line does match.
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "foobar together on one line")

        code, data, out, err = _run([
            "check", "--repo", repo, "--commit", "HEAD",
            "--expect-substring", "foobar",
        ])

        assert code == 0, f"stdout={out!r} stderr={err!r}"
        assert _checks(data).get("substring-present") is True


# ===========================================================================
# N4 -- --expect-file without --expect-substring is a usage error (exit 2).
# ===========================================================================

class TestN4ExpectFileRequiresSubstring:
    """[BEHAVIORAL] Both check and verify error (exit 2) on --expect-file with
    no --expect-substring -- it would be a no-op."""

    def test_check_expect_file_without_substring_exit2(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "a real change")

        code, data, out, err = _run([
            "check", "--repo", repo, "--commit", "HEAD", "--expect-file", "f.txt",
        ])

        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert data is not None, f"expected error JSON on stdout: {out!r} {err!r}"

    def test_verify_expect_file_without_substring_exit2_no_write(self, tmp_path):
        repo = _init_repo(tmp_path / "repo")
        _commit_adding_line(repo, "f.txt", "a real change")
        sp = tmp_path / "status.json"
        _write_status(sp, _status([_item("must-1", "story one")]))
        before = _read_bytes(sp)

        code, data, out, err = _run([
            "verify", "--status-json", sp, "--item", "must-1",
            "--repo", repo, "--commit", "HEAD", "--expect-file", "f.txt",
            "--now", NOW,
        ])

        assert code == 2, f"stdout={out!r} stderr={err!r}"
        assert data is not None, f"expected error JSON on stdout: {out!r} {err!r}"
        assert _read_bytes(sp) == before, "no write on usage error"
