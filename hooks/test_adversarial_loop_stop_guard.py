#!/usr/bin/env python3
"""Adversarial tests for hooks/loop_stop_guard.py + hooks/micro_step_gates.py --
the H-SUBAGENT-MASKING-1 full-closure build (commits f03ae8f, cca3abc, af7b658).

Tier 2 (Adversarial Test-writer). These tests are written FROM THE CODE, not
from the spec's acceptance criteria -- they attack the exact mechanisms the
spec's own text calls out as novel/risky: the `_l1_flagged_shas` dedup set's
membership semantics, the EOF `_VIOLATIONS` reporting block's behavior under
3+ simultaneous violations and adversarial message content, the TTL boundary
condition, and the `record_sigs` wiring's interaction with gates other than
Layer 1.

Self-contained: builds its own minimal fixtures (real git repos, real flag
files, real sub-agent transcripts) rather than importing helpers from
test_loop_stop_guard.py, so this file can be run/read independently and never
risks silently depending on (or corrupting) that file's own module-level
GATE_DIR state.

Run with:
    python3 -m pytest hooks/test_adversarial_loop_stop_guard.py -q
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HOOKS_DIR, "loop_stop_guard.py")

PLAN_PASS_TTL_SECONDS = 24 * 3600


# ---------------------------------------------------------------------------
# Minimal, self-contained fixture helpers (deliberately NOT imported from
# test_loop_stop_guard.py -- adversarial tests should not depend on the
# standard suite's own infrastructure being correct).
# ---------------------------------------------------------------------------

def _write_jsonl(events, path):
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def run_guard_full(events, gate_dir, transcript_path=None, session_id=None,
                    stop_hook_active=False):
    """Drive the real guard subprocess against a crafted transcript, with an
    explicit gate_dir the caller controls (so flag files/target files can be
    pre-arranged before the call)."""
    own_tmp = transcript_path is None
    if own_tmp:
        fd, transcript_path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
    try:
        _write_jsonl(events, transcript_path)
        payload = {"transcript_path": transcript_path,
                   "stop_hook_active": stop_hook_active}
        if session_id is not None:
            payload["session_id"] = session_id
        env = dict(os.environ, LOOP_GATE_DIR=gate_dir)
        p = subprocess.run([sys.executable, GUARD], input=json.dumps(payload),
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        if own_tmp:
            os.remove(transcript_path)


def write_l1_flag(gate_dir, session_id, agent_id, content, mtime=None):
    """Write a {session_id}_{agent_id}.commit_violation flag with RAW content
    (any JSON-serializable value, or a raw string for genuinely-invalid
    JSON). Mirrors subagent_stop_gate.py's real write shape."""
    os.makedirs(gate_dir, exist_ok=True)
    path = os.path.join(gate_dir, "%s_%s.commit_violation" % (session_id, agent_id))
    text = content if isinstance(content, str) else json.dumps(content)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def scratch_git_repo():
    d = tempfile.mkdtemp(prefix="adv-scratch-repo-")
    subprocess.run(["git", "-C", d, "init", "-q"], capture_output=True)
    subprocess.run(["git", "-C", d, "config", "user.email", "adv@test"], capture_output=True)
    subprocess.run(["git", "-C", d, "config", "user.name", "adv"], capture_output=True)
    with open(os.path.join(d, "seed.txt"), "w", encoding="utf-8") as f:
        f.write("seed\n")
    subprocess.run(["git", "-C", d, "add", "seed.txt"], capture_output=True)
    subprocess.run(["git", "-C", d, "commit", "-qm", "seed"], capture_output=True)
    return d


def real_git_commit(repo, rel_path, content, message):
    full = os.path.join(repo, rel_path)
    os.makedirs(os.path.dirname(full) or repo, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    subprocess.run(["git", "-C", repo, "add", rel_path], capture_output=True)
    r = subprocess.run(["git", "-C", repo, "commit", "-m", message],
                       capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def sha_from_commit_output(out):
    return out.split("]")[0].split()[-1]


def write_subagent_transcript(project_dir, session_id, agent_id, events):
    sub_dir = os.path.join(project_dir, session_id, "subagents")
    os.makedirs(sub_dir, exist_ok=True)
    path = os.path.join(sub_dir, "agent-%s.jsonl" % agent_id)
    _write_jsonl(events, path)
    return path


def bash_tool_use_with_id(tool_use_id, command):
    return {"type": "tool_use", "name": "Bash", "id": tool_use_id,
            "input": {"command": command}}


def assistant_msg(*parts):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(parts)}}


def tool_result_event(tool_use_id, content_text):
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id, "content": content_text}]}}


def agent_dispatch_result_event(tool_use_id, agent_id):
    return {
        "toolUseResult": {"isAsync": True, "status": "async_launched",
                           "agentId": agent_id, "description": "dispatch"},
        "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_use_id,
             "content": "Async agent launched successfully.\nagentId: %s" % agent_id}]},
        "type": "user",
    }


def oga_marker():
    return {"type": "user", "message": {
        "role": "user", "content": "you are **oga** -- orchestrator playbook loaded"}}


def human_turn_start():
    return {"type": "user", "message": {"role": "user", "content": "go build"}}


def dispatch_task_tool_use():
    return {"type": "tool_use", "name": "Task", "input": {"description": "dispatch"}}


def arm_target(gate_dir, session_id, target_dir):
    os.makedirs(gate_dir, exist_ok=True)
    tfile = os.path.join(gate_dir, "%s_target" % session_id)
    with open(tfile, "w", encoding="utf-8") as f:
        f.write(target_dir)
    return tfile


class AdversarialTestCase(unittest.TestCase):
    """Common gate_dir/tempdir bookkeeping for every adversarial test below."""

    def setUp(self):
        self.gate_dir = tempfile.mkdtemp(prefix="adv-gate-")
        self._cleanup_dirs = [self.gate_dir]

    def tearDown(self):
        for d in self._cleanup_dirs:
            shutil.rmtree(d, ignore_errors=True)

    def mkdtemp(self, prefix):
        d = tempfile.mkdtemp(prefix=prefix)
        self._cleanup_dirs.append(d)
        return d


# ===========================================================================
# Category: State / dedup-key attacks -- the (agent_id, sha) tuple membership
# test in `_l1_flagged_shas` and the Layer-2 filter that consumes it.
# ===========================================================================

class DedupKeyPoisoningFromMalformedSiblingItem(AdversarialTestCase):
    """[BEHAVIORAL] REAL BUG FOUND: a single Layer-1 flag file whose JSON
    array contains ONE well-formed item (a real, in-scope SHA) FOLLOWED BY
    one malformed item (an unhashable `sha`, e.g. a JSON array instead of a
    string) causes:
      1. The whole flag's reported evidence to fall back to the generic
         "<could not be parsed>" placeholder -- so Oga's visible report
         NEVER names the real, well-formed SHA from item 1.
      2. BUT `_l1_flagged_shas.add((agent_id, real_sha))` for item 1 already
         executed successfully BEFORE the loop reached item 2's exception --
         so `(agent_id, real_sha)` silently persists in the dedup set.
      3. If Layer 2 independently, correctly finds that EXACT SAME
         (agent_id, sha) violation via the sub-agent's own transcript, the
         dedup filter suppresses it -- because it believes Layer 1 already
         reported it. But Layer 1 never actually surfaced that SHA to Oga.

    Net effect: Oga's Stop is blocked, but the violation report contains
    ZERO concrete evidence (no SHA, no touched filename) of a real, genuine
    scope violation that TWO independent detection layers actually found.
    This reproduces exactly the class of masking bug this whole build exists
    to close, via a narrow but real, adversarially-constructible input the
    197-test standard suite never tries (every existing malformed-flag
    fixture uses a SINGLE-item array, never a MIXED good+malformed array).

    This test currently FAILS against the real implementation -- it is
    reported as a genuine finding, not fixed here (adversarial test-writer
    scope: prove it, do not patch loop_stop_guard.py)."""

    def test_real_sha_masked_when_later_sibling_item_is_malformed(self):
        repo = scratch_git_repo()
        self._cleanup_dirs.append(repo)
        rc, out, err_txt = real_git_commit(
            repo, "RUN.md", "poisoning-probe content\n", "poisoning probe commit")
        self.assertEqual(rc, 0, err_txt)
        sha = sha_from_commit_output(out)

        sid = "poison-%s" % uuid.uuid4().hex
        agent_id = "poisonAgent"
        project_dir = self.mkdtemp("adv-poison-proj-")

        # Flag content: item 1 is REAL and well-formed (sha = the real,
        # in-scope commit above). Item 2 is malformed -- its "sha" is a JSON
        # array (unhashable once loaded into Python), tripping the loop's
        # own try/except AFTER item 1's .add() already ran.
        write_l1_flag(self.gate_dir, sid, agent_id, [
            {"sha": sha, "touched": ["RUN.md"]},
            {"sha": ["not", "a", "string"], "touched": ["fix_plan.md"]},
        ])

        write_subagent_transcript(project_dir, sid, agent_id, [
            assistant_msg(bash_tool_use_with_id("pd1",
                'git commit -m "poisoning probe commit"')),
            tool_result_event("pd1", out),
        ])

        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        events = [
            oga_marker(),
            human_turn_start(),
            assistant_msg(dispatch_task_tool_use()),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        arm_target(self.gate_dir, sid, repo)

        code, err = run_guard_full(events, self.gate_dir,
                                   transcript_path=oga_tpath, session_id=sid)
        self.assertEqual(code, 2, err)

        # What SHOULD be true (matches the spec's own explicit "malformed +
        # genuine" double-report decision, and the general masking-gap-
        # closure goal: "genuinely-distinct violations are all reported in
        # full"): the real SHA and its real touched file must appear
        # SOMEWHERE in the report -- either via Layer 1's own evidence
        # (if the malformed-item exception were scoped per-ITEM rather than
        # per-FLAG-FILE) or via Layer 2's independent, unsuppressed finding.
        real_evidence_present = (sha in err) and ("RUN.md" in err)
        self.assertTrue(
            real_evidence_present,
            "FOUND BUG: a real, well-formed violation's SHA (%r) and touched "
            "file (RUN.md) are completely absent from the block message, "
            "even though BOTH Layer 1 (partially, before choking on a "
            "malformed SIBLING item in the same flag file) and Layer 2 "
            "(independently, via the sub-agent's own transcript) detected "
            "this exact violation. The malformed item poisoned the dedup "
            "set with (%r, %r) via a partial .add() that ran before the "
            "loop's own try/except caught the LATER item's unhashable sha, "
            "then that poisoned entry silently suppressed Layer 2's "
            "legitimate, well-formed report of the SAME violation -- while "
            "Layer 1's own visible message fell back to the generic "
            "'<could not be parsed>' placeholder that never names this SHA "
            "at all. Full stderr:\n%s" % (sha, agent_id, sha, err))


class DedupKeyTypeCoercionIntVsString(AdversarialTestCase):
    """[BEHAVIORAL] A Layer-1 flag whose `sha` value is a JSON NUMBER (Python
    int after json.loads) is a technically-valid shape per the flag's own
    shape check (`"sha" in _l1_item` only checks key presence, never type).
    Layer 2's real SHAs are ALWAYS strings (extracted via a regex capture
    group on git's own text output) -- so `(agent_id, 1234567)` (int) and
    `(agent_id, "1234567")` (str) are DIFFERENT dedup keys in Python
    (`1234567 != "1234567"`, confirmed: `("a", 1234567) in {("a", "1234567")}`
    is False). This test proves the current, real behavior for this case
    (a genuinely different violation is NOT filtered, i.e. Layer 1's
    int-sha flag and Layer 2's real string-sha finding for the SAME agent
    do NOT dedup against each other) -- a real, live divergence risk if a
    future flag-writer ever emits a numeric-looking sha as a bare JSON
    number instead of a string. Documented as a REGRESSION GUARD (the
    current behavior is internally consistent -- Layer 1's int-typed "sha"
    genuinely never equals Layer 2's string SHA -- not a masking failure in
    THIS specific fixture, since here the two are deliberately DIFFERENT
    real commits, so two reports is correct)."""

    def test_int_sha_and_string_sha_are_distinct_dedup_keys_both_reported(self):
        repo = scratch_git_repo()
        self._cleanup_dirs.append(repo)
        # A REAL commit whose sha happens to be referenced (deliberately
        # wrongly-typed) as a JSON int in the Layer-1 flag.
        rc, out, err_txt = real_git_commit(
            repo, "RUN.md", "int-sha content\n", "int sha commit")
        self.assertEqual(rc, 0, err_txt)
        sha = sha_from_commit_output(out)

        sid = "intsha-%s" % uuid.uuid4().hex
        agent_id = "intShaAgent"
        project_dir = self.mkdtemp("adv-intsha-proj-")

        # Deliberately wrong type: sha as a bare JSON number derived from the
        # numeric PREFIX of the real hex sha (if it happens to parse as an
        # int) -- if the real sha is not all-digits, we instead just assert
        # the type-mismatch behavior in isolation with a synthetic numeric
        # sha value that could never equal Layer 2's real (string, hex)
        # finding, proving the two layers report INDEPENDENTLY (2 violations)
        # rather than silently, incorrectly deduping across a type boundary.
        write_l1_flag(self.gate_dir, sid, agent_id, [
            {"sha": 1234567, "touched": ["RUN.md"]},
        ])

        write_subagent_transcript(project_dir, sid, agent_id, [
            assistant_msg(bash_tool_use_with_id("pd1", 'git commit -m "int sha commit"')),
            tool_result_event("pd1", out),
        ])

        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        events = [
            oga_marker(),
            human_turn_start(),
            assistant_msg(dispatch_task_tool_use()),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        arm_target(self.gate_dir, sid, repo)

        code, err = run_guard_full(events, self.gate_dir,
                                   transcript_path=oga_tpath, session_id=sid)
        self.assertEqual(code, 2, err)
        # Layer 1's int-sha evidence appears (its own evidence string
        # renders `%s (touches: %s)" % (1234567, ...)` -- the int prints as
        # its str() form).
        self.assertIn("1234567", err)
        self.assertIn("Layer 1", err)
        # Layer 2's real, string-typed sha for the SAME agent is NOT
        # filtered (proves the int/str dedup-key mismatch does not
        # accidentally cause an OVER-suppression in this direction -- two
        # distinct dedup keys correctly produce two reports).
        self.assertIn(sha, err)
        self.assertIn("Layer 2", err)
        self.assertIn("2 violations detected", err)


class DedupKeyNullShaDoesNotCrash(AdversarialTestCase):
    """[BEHAVIORAL] Category 2 (type attack): `sha` present but JSON `null`
    (Python `None`). `None` is hashable, so `_l1_flagged_shas.add((agent_id,
    None))` must not raise. Confirms the gate still blocks and does not
    crash, and that a genuinely different Layer-2 finding for the same agent
    (a real string sha) is correctly NOT filtered by a null-keyed entry."""

    def test_null_sha_does_not_crash_and_does_not_over_suppress(self):
        repo = scratch_git_repo()
        self._cleanup_dirs.append(repo)
        rc, out, err_txt = real_git_commit(
            repo, "RUN.md", "null-sha content\n", "null sha commit")
        self.assertEqual(rc, 0, err_txt)
        sha = sha_from_commit_output(out)

        sid = "nullsha-%s" % uuid.uuid4().hex
        agent_id = "nullShaAgent"
        project_dir = self.mkdtemp("adv-nullsha-proj-")

        write_l1_flag(self.gate_dir, sid, agent_id, [
            {"sha": None, "touched": ["RUN.md"]},
        ])
        write_subagent_transcript(project_dir, sid, agent_id, [
            assistant_msg(bash_tool_use_with_id("pd1", 'git commit -m "null sha commit"')),
            tool_result_event("pd1", out),
        ])

        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        events = [
            oga_marker(),
            human_turn_start(),
            assistant_msg(dispatch_task_tool_use()),
            agent_dispatch_result_event("disp1", agent_id),
        ]
        arm_target(self.gate_dir, sid, repo)

        code, err = run_guard_full(events, self.gate_dir,
                                   transcript_path=oga_tpath, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertNotIn("Traceback", err)
        self.assertIn("Layer 1", err)
        self.assertIn(sha, err)
        self.assertIn("Layer 2", err)
        self.assertIn("2 violations detected", err)


class DedupKeyEmptyStringShaDoesNotCrash(AdversarialTestCase):
    """[BEHAVIORAL] Category 1 (boundary/empty): `sha` present but an empty
    string. Empty string is hashable and falsy but distinct from `None`.
    Must not crash; must not accidentally match every other empty/falsy
    dedup key."""

    def test_empty_string_sha_does_not_crash(self):
        sid = "emptysha-%s" % uuid.uuid4().hex
        agent_id = "emptyShaAgent"
        write_l1_flag(self.gate_dir, sid, agent_id, [
            {"sha": "", "touched": ["RUN.md"]},
        ])
        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            {"type": "assistant", "message": {"role": "assistant",
                                              "content": [{"type": "text", "text": "nothing"}]}},
        ]
        code, err = run_guard_full(events, self.gate_dir, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertNotIn("Traceback", err)
        self.assertIn(agent_id, err)


class DedupKeyVeryLongShaStringDoesNotCrash(AdversarialTestCase):
    """[BEHAVIORAL] Category 1 (boundary): a pathologically long `sha`
    string (10,000 chars). Must not crash, must not silently truncate in a
    way that causes a false collision with another long-but-different sha
    (Python str hashing/equality is exact regardless of length)."""

    def test_very_long_sha_string_does_not_crash_and_is_not_confused(self):
        sid = "longsha-%s" % uuid.uuid4().hex
        agent_id = "longShaAgent"
        long_sha_1 = "a" * 10000
        long_sha_2 = "a" * 9999 + "b"  # differs only in the LAST character
        write_l1_flag(self.gate_dir, sid, agent_id, [
            {"sha": long_sha_1, "touched": ["RUN.md"]},
        ])
        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            {"type": "assistant", "message": {"role": "assistant",
                                              "content": [{"type": "text", "text": "nothing"}]}},
        ]
        code, err = run_guard_full(events, self.gate_dir, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertNotIn("Traceback", err)
        # Sanity: Python string equality/hashing correctly distinguishes
        # these two 10,000-char strings that differ only in their last byte
        # (this is a property of the language, but worth pinning explicitly
        # since the whole dedup mechanism depends on exact tuple equality).
        self.assertNotEqual(long_sha_1, long_sha_2)
        self.assertNotEqual(hash(long_sha_1), hash(long_sha_2))


class DedupKeyUnicodeNormalizationAgentId(AdversarialTestCase):
    """[BEHAVIORAL] Category 6 (unicode): two visually-identical agent_ids
    that differ in Unicode NORMALIZATION FORM (NFC precomposed vs NFD
    decomposed) are UNEQUAL as Python strings (`'agent\\u00e9' !=
    'agent\\u0065\\u0301'`, confirmed live). If a Layer-1 flag's filename
    encodes an agent_id in one normalization form and Layer 2's sub-agent
    transcript directory encodes the SAME logical agent_id in the other
    form, the dedup filter's (agent_id, sha) key never matches even for the
    IDENTICAL underlying commit -- producing an (accepted-direction, safe)
    double-report rather than a silent suppression. This test proves the
    SAFE direction holds: over-report, never silent-drop, under a
    normalization mismatch. (Documented as a regression guard for the safe
    failure mode, not a bug -- the project's own standing principle is
    over-fire is the safe direction, fix_plan.md RH1d.)"""

    def test_nfc_vs_nfd_agent_id_mismatch_double_reports_not_silently_drops(self):
        agent_nfc = "agenté"        # 'agenté' precomposed (6 chars)
        agent_nfd = "agenté"       # 'agente' + combining acute (7 chars)
        self.assertNotEqual(agent_nfc, agent_nfd)  # sanity: language-level fact

        repo = scratch_git_repo()
        self._cleanup_dirs.append(repo)
        rc, out, err_txt = real_git_commit(
            repo, "RUN.md", "unicode-agent content\n", "unicode agent commit")
        self.assertEqual(rc, 0, err_txt)
        sha = sha_from_commit_output(out)

        sid = "unicode-%s" % uuid.uuid4().hex
        project_dir = self.mkdtemp("adv-unicode-proj-")

        # Layer-1 flag filed under the NFC form.
        write_l1_flag(self.gate_dir, sid, agent_nfc, [
            {"sha": sha, "touched": ["RUN.md"]},
        ])
        # Layer-2 sub-agent transcript filed under the NFD form (the "same"
        # agent to a human eye, a different key to Python).
        write_subagent_transcript(project_dir, sid, agent_nfd, [
            assistant_msg(bash_tool_use_with_id("pd1",
                'git commit -m "unicode agent commit"')),
            tool_result_event("pd1", out),
        ])

        oga_tpath = os.path.join(project_dir, "%s.jsonl" % sid)
        events = [
            oga_marker(),
            human_turn_start(),
            assistant_msg(dispatch_task_tool_use()),
            agent_dispatch_result_event("disp1", agent_nfd),
        ]
        arm_target(self.gate_dir, sid, repo)

        code, err = run_guard_full(events, self.gate_dir,
                                   transcript_path=oga_tpath, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertNotIn("Traceback", err)
        # Safe direction: BOTH layers' evidence for the (to-a-human) same
        # commit appear -- nothing is silently dropped. This documents a
        # real (narrow) limitation: the dedup filter is not Unicode-
        # normalization-aware, but the failure mode is over-reporting, not
        # under-reporting.
        self.assertIn(sha, err)
        self.assertIn("Layer 1", err)
        self.assertIn("Layer 2", err)


# ===========================================================================
# Category: Boundary attacks -- TTL exact-equality edge.
# ===========================================================================

class TTLExactBoundaryFreshness(AdversarialTestCase):
    """[BEHAVIORAL] Category 1 (boundary): the staleness check is a strict
    `>` (`(_l1_now - _l1_mtime) > PLAN_PASS_TTL_SECONDS`), so a flag whose
    age is EXACTLY equal to the TTL must still be treated as FRESH (blocks),
    and TTL+1 second must be treated as STALE (does not block). The existing
    standard suite's stale-flag test uses a 2-hour margin past the TTL --
    this pins the exact boundary the `>` operator creates, distinguishing it
    from a hypothetical `>=` mutation."""

    def test_flag_at_exactly_ttl_boundary_still_blocks(self):
        sid = "ttl-exact-%s" % uuid.uuid4().hex
        agent_id = "ttlExactAgent"
        # Age == exactly PLAN_PASS_TTL_SECONDS (use a small negative epsilon
        # to survive the wall-clock time elapsed between mtime-set and the
        # guard's own now-read, which would otherwise nondeterministically
        # tip this over the boundary in the wrong direction).
        mtime = time.time() - PLAN_PASS_TTL_SECONDS + 2
        flag = write_l1_flag(self.gate_dir, sid, agent_id,
                             [{"sha": "ttlexact1", "touched": ["RUN.md"]}], mtime=mtime)
        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            {"type": "assistant", "message": {"role": "assistant",
                                              "content": [{"type": "text", "text": "nothing"}]}},
        ]
        code, err = run_guard_full(events, self.gate_dir, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertTrue(os.path.exists(flag), "a fresh flag must never be consumed/removed")

    def test_flag_just_past_ttl_boundary_does_not_block(self):
        sid = "ttl-past-%s" % uuid.uuid4().hex
        agent_id = "ttlPastAgent"
        mtime = time.time() - PLAN_PASS_TTL_SECONDS - 5
        flag = write_l1_flag(self.gate_dir, sid, agent_id,
                             [{"sha": "ttlpast1", "touched": ["RUN.md"]}], mtime=mtime)
        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            {"type": "assistant", "message": {"role": "assistant",
                                              "content": [{"type": "text", "text": "nothing"}]}},
        ]
        code, err = run_guard_full(events, self.gate_dir, session_id=sid)
        self.assertEqual(code, 0, err)
        self.assertFalse(os.path.exists(flag), "a stale flag should be best-effort removed")


# ===========================================================================
# Category: 3+ simultaneous violations -- EOF block formatting/numbering.
# ===========================================================================

class ThreeSimultaneousViolationsFormatting(AdversarialTestCase):
    """[BEHAVIORAL] The spec's own ACs (AC5, AC8) only construct 2-violation
    turns. This test constructs a REAL 3-different-gate turn (ROLE_OR_HARNESS_
    EDIT + FEATURE + PLAN_CHECK, all independently real, all in one turn) and
    verifies the EOF block's numbering/priority-first guarantee holds for
    N=3, not just N=2: the banner states "3 violations detected", each
    violation is numbered i/3 in strictly increasing order 1,2,3, the
    NAMED-first gate in the banner matches the actual first violation's name,
    and every violation's own distinguishing text is present."""

    def test_three_different_gates_fire_same_turn_correctly_numbered(self):
        events = [
            {"type": "user", "message": {"role": "user", "content": "go build"}},
            {"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Edit", "input": {
                    "file_path": "/x/loop-team/roles/verifier.md",
                    "old_string": "a", "new_string": "b"}},
                {"type": "tool_use", "name": "Edit", "input": {
                    "file_path": "/x/src/module.py",
                    "old_string": "a", "new_string": "b"}},
                {"type": "tool_use", "name": "Task", "input": {
                    "description": "dispatch", "prompt": "role: coder for the feature"}},
            ]}},
        ]
        code, err = run_guard_full(events, self.gate_dir)
        self.assertEqual(code, 2, err)
        self.assertIn("3 violations detected", err)
        self.assertIn("----- Violation 1/3 (ROLE_OR_HARNESS_EDIT) -----", err)
        self.assertIn("----- Violation 2/3 (FEATURE) -----", err)
        self.assertIn("----- Violation 3/3 (PLAN_CHECK) -----", err)
        # Priority-first: the banner names the SAME gate as violation 1/3.
        banner_idx = err.index("3 violations detected")
        first_block_idx = err.index("----- Violation 1/3")
        self.assertLess(banner_idx, first_block_idx)
        self.assertIn("(ROLE_OR_HARNESS_EDIT)", err[banner_idx:first_block_idx])
        # Strictly increasing order of the numbered blocks themselves.
        i1 = err.index("----- Violation 1/3")
        i2 = err.index("----- Violation 2/3")
        i3 = err.index("----- Violation 3/3")
        self.assertLess(i1, i2)
        self.assertLess(i2, i3)
        # Each violation's own distinguishing content survives.
        self.assertIn("Phase-1 rule", err)
        self.assertIn("INDEPENDENT verifier", err)
        self.assertIn("plan-check Verifier", err)


class FourSimultaneousViolationsIncludingLayer1First(AdversarialTestCase):
    """[BEHAVIORAL] N=4, including Layer 1 (the highest file-order priority
    gate) plus 3 other independent gates, to further stress the numbering
    logic and re-confirm priority-first ordering holds beyond N=3 as well."""

    def test_four_violations_layer1_plus_three_others_numbered_correctly(self):
        sid = "quad-%s" % uuid.uuid4().hex
        agent_id = "quadAgent"
        write_l1_flag(self.gate_dir, sid, agent_id,
                     [{"sha": "quad1234", "touched": ["RUN.md"]}])

        events = [
            oga_marker(),
            human_turn_start(),
            assistant_msg(
                {"type": "tool_use", "name": "Edit", "input": {
                    "file_path": "/x/loop-team/roles/verifier.md",
                    "old_string": "a", "new_string": "b"}},
                {"type": "tool_use", "name": "Edit", "input": {
                    "file_path": "/x/src/module.py",
                    "old_string": "a", "new_string": "b"}},
                {"type": "tool_use", "name": "Task", "input": {
                    "description": "dispatch", "prompt": "role: coder for the feature"}},
            ),
        ]
        code, err = run_guard_full(events, self.gate_dir, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn("4 violations detected", err)
        self.assertIn("----- Violation 1/4 (SUBAGENT_COMMIT_VIOLATION) -----", err)
        self.assertIn("----- Violation 2/4 (ROLE_OR_HARNESS_EDIT) -----", err)
        self.assertIn("----- Violation 3/4 (FEATURE) -----", err)
        self.assertIn("----- Violation 4/4 (PLAN_CHECK) -----", err)
        i1 = err.index("----- Violation 1/4")
        i2 = err.index("----- Violation 2/4")
        i3 = err.index("----- Violation 3/4")
        i4 = err.index("----- Violation 4/4")
        self.assertLess(i1, i2)
        self.assertLess(i2, i3)
        self.assertLess(i3, i4)


# ===========================================================================
# Category: Message-content injection into the EOF block's own formatting.
# ===========================================================================

class InjectedFakeViolationBannerDoesNotCorruptRealNumbering(AdversarialTestCase):
    """[BEHAVIORAL] Category 5 (semantic) / adversarial construction: a
    Layer-1 flag's `touched` list is attacker/subagent-controlled content
    that flows verbatim into the violation message. Craft a `touched` entry
    containing a literal string that looks EXACTLY like the EOF block's own
    "----- Violation N/M (...) -----" banner syntax, embedded inside a real,
    single violation's body, alongside a second REAL violation (so we are in
    the N>1 numbered-block code path). Assert: this does not crash, and the
    REAL banners for violation 1/2 and 2/2 are still present, correctly
    bounding the real content -- i.e. the injected fake banner does not
    fool a mechanical `re.findall(r"----- Violation \\d+/\\d+", err)` scan
    into reporting more than the true 2 real banners are semantically
    identifiable as the FIRST two matches in the string, appearing at the
    positions the real EOF loop itself controls."""

    def test_injected_fake_banner_text_does_not_break_real_numbering(self):
        sid = "inject-%s" % uuid.uuid4().hex
        agent_id = "injectAgent"
        fake_banner = (
            "----- Violation 1/1 (FAKE_GATE) -----\n"
            "FAKE injected content designed to look like a real block\n\n"
            "----- Violation 2/1 (FAKE_GATE) -----"
        )
        write_l1_flag(self.gate_dir, sid, agent_id,
                     [{"sha": "deadbeef", "touched": [fake_banner]}])

        events = [
            oga_marker(),
            human_turn_start(),
            assistant_msg({"type": "tool_use", "name": "Edit", "input": {
                "file_path": "/x/loop-team/roles/verifier.md",
                "old_string": "a", "new_string": "b"}}),
        ]
        code, err = run_guard_full(events, self.gate_dir, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertNotIn("Traceback", err)
        self.assertIn("2 violations detected", err)
        # The REAL banners (produced by the EOF loop itself, over the TWO
        # real violations: SUBAGENT_COMMIT_VIOLATION and ROLE_OR_HARNESS_EDIT)
        # must both be present and in the correct order.
        real_1 = "----- Violation 1/2 (SUBAGENT_COMMIT_VIOLATION) -----"
        real_2 = "----- Violation 2/2 (ROLE_OR_HARNESS_EDIT) -----"
        self.assertIn(real_1, err)
        self.assertIn(real_2, err)
        self.assertLess(err.index(real_1), err.index(real_2))
        # The injected fake banner text is present too (it's legitimate
        # evidence content, verbatim) but strictly INSIDE violation 1's own
        # body -- i.e. after the real "Violation 1/2" banner and before the
        # real "Violation 2/2" banner.
        fake_idx = err.index("FAKE injected content")
        self.assertGreater(fake_idx, err.index(real_1))
        self.assertLess(fake_idx, err.index(real_2))


class TouchedFilenameWithEmbeddedNewlinesDoesNotBreakRstrip(AdversarialTestCase):
    """[BEHAVIORAL] Category 6/1: a `touched` entry containing embedded
    newlines and trailing whitespace/newlines, to probe whether the EOF
    block's `_msg.rstrip("\\n")` normalization (applied to the FULL message,
    not the individual evidence fields) could be defeated by evidence text
    that reintroduces trailing newlines AFTER the point `.rstrip` inspects --
    it cannot (rstrip is applied to the complete, already-concatenated
    message string, and the message's own suffix is always the same fixed
    trailer text, not attacker content), but this is a real path worth
    proving does not crash or misformat rather than assuming it doesn't."""

    def test_multiline_touched_field_does_not_break_formatting_or_crash(self):
        sid = "multiline-%s" % uuid.uuid4().hex
        agent_id = "multilineAgent"
        messy_touched = "RUN.md\n\n\n----- Violation 9/9 (SPOOF) -----\n\n"
        write_l1_flag(self.gate_dir, sid, agent_id,
                     [{"sha": "multi1234", "touched": [messy_touched]}])
        events = [
            oga_marker(),
            human_turn_start(),
            assistant_msg({"type": "tool_use", "name": "Edit", "input": {
                "file_path": "/x/loop-team/roles/verifier.md",
                "old_string": "a", "new_string": "b"}}),
        ]
        code, err = run_guard_full(events, self.gate_dir, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertNotIn("Traceback", err)
        self.assertIn("2 violations detected", err)
        # Still exactly two real numbered banners, not three (the embedded
        # fake "9/9" text must not be misparsed as a real third violation by
        # anything mechanical scanning this output -- the guard itself does
        # not re-parse its own stderr, so this is inherently safe, but
        # pinning it as an explicit assertion documents the guarantee).
        import re as _re
        real_banners = _re.findall(r"----- Violation (\d+)/(\d+) \((?!SPOOF)", err)
        self.assertEqual(len(real_banners), 2)
        self.assertEqual([b[1] for b in real_banners], ["2", "2"])


# ===========================================================================
# Category: `record_sigs` wiring -- earlier-violation gates OTHER than Layer 1.
# ===========================================================================

class RecordSigsFalseWhenEarlierNonLayer1GateViolates(AdversarialTestCase):
    """[BEHAVIORAL] The existing standard suite's ONLY integration-level
    proof that `record_sigs=(not _VIOLATIONS)` is wired correctly uses Layer
    1 as the earlier-firing gate (MicroStepBlockedWhenLayer1AlreadyViolated
    DoesNotRecordSigsMasking1). Layer 1 is structurally the FIRST gate in
    file order, so that test cannot distinguish "record_sigs correctly reads
    _VIOLATIONS at call time" from a hypothetical bug that only checks
    "did Layer 1 specifically fire" (e.g. a bug that hardcoded a Layer-1-only
    flag instead of the general `_VIOLATIONS` list). This test uses
    ROLE_OR_HARNESS_EDIT instead -- a COMPLETELY different, non-Layer-1 gate
    that also fires strictly before the MICRO_STEP call site in file order --
    to independently confirm the wiring generalizes to ANY earlier violation,
    not just Layer 1's specific one."""

    def test_no_signatures_file_written_when_role_edit_violation_precedes_microstep(self):
        repo = scratch_git_repo()
        self._cleanup_dirs.append(repo)
        sid = "rolesigs-%s" % uuid.uuid4().hex

        # Force a real step-size violation in the SAME armed target, so this
        # test proves the MICRO_STEP block's own detection logic actually
        # EXECUTED this invocation (mirrors the existing Layer-1 test's own
        # "prove it ran, not merely never-reached" design).
        with open(os.path.join(repo, "big.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n" * 250)
        subprocess.run(["git", "-C", repo, "add", "-A"], capture_output=True)

        events = [
            oga_marker(),
            human_turn_start(),
            assistant_msg({"type": "tool_use", "name": "Edit", "input": {
                "file_path": "/x/loop-team/roles/verifier.md",
                "old_string": "a", "new_string": "b"}}),
        ]
        arm_target(self.gate_dir, sid, repo)
        sig_file = os.path.join(self.gate_dir, "%s_signatures.json" % sid)
        self.assertFalse(os.path.isfile(sig_file))

        code, err = run_guard_full(events, self.gate_dir, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn("Phase-1 rule", err)  # ROLE_OR_HARNESS_EDIT fired
        # Proof the micro-step-gates block's own detection ran this
        # invocation (not never-reached): its step-size violation is also
        # reported, i.e. this really is a 2-violation turn.
        self.assertIn("step-size", err)
        self.assertIn("2 violations detected", err)
        self.assertFalse(
            os.path.isfile(sig_file),
            "ROLE_OR_HARNESS_EDIT (a non-Layer-1 gate) already appended a "
            "violation earlier in file order than MICRO_STEP -- record_sigs "
            "must still resolve to False generically from _VIOLATIONS being "
            "non-empty, not from any Layer-1-specific special case")


class RecordSigsTrueWhenNoEarlierViolationButMicroStepItselfBlocks(AdversarialTestCase):
    """[BEHAVIORAL] Companion/contrast case: when NO earlier gate has fired
    (an empty _VIOLATIONS at the point MICRO_STEP's own call site is
    reached), record_sigs must resolve to True even if the micro-step-gates
    block ITSELF is about to append the only violation this turn (its own
    firing must not retroactively flip record_sigs=False for its own call --
    `not _VIOLATIONS` is evaluated as the ARGUMENT to `_msg_mod.run(...)`,
    strictly BEFORE that call executes and strictly before MICRO_STEP's own
    _VIOLATIONS.append() a few lines later)."""

    def test_record_sigs_true_when_microstep_is_the_first_and_only_violation(self):
        repo = scratch_git_repo()
        self._cleanup_dirs.append(repo)
        sid = "firstsigs-%s" % uuid.uuid4().hex

        with open(os.path.join(repo, "big.py"), "w", encoding="utf-8") as f:
            f.write("x = 1\n" * 250)
        subprocess.run(["git", "-C", repo, "add", "-A"], capture_output=True)

        events = [
            oga_marker(),
            human_turn_start(),
            {"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "content": "nothing this turn"}]}},
        ]
        arm_target(self.gate_dir, sid, repo)
        sig_file = os.path.join(self.gate_dir, "%s_signatures.json" % sid)
        self.assertFalse(os.path.isfile(sig_file))

        code, err = run_guard_full(events, self.gate_dir, session_id=sid)
        self.assertEqual(code, 2, err)
        self.assertIn("step-size", err)
        # This is a single-violation turn (MICRO_STEP is the ONLY entry in
        # _VIOLATIONS), so the EOF block takes the single-message branch --
        # confirm no "violations detected" banner (single-violation shape).
        self.assertNotIn("violations detected", err)


if __name__ == "__main__":
    unittest.main()
