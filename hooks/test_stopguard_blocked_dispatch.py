#!/usr/bin/env python3
"""Tests for H-STOPGUARD-BLOCKED-DISPATCH-REPLAY-1 (spec-v5.md, AC1-AC10):
`loop_stop_guard.py` must exclude any `tool_use` that was blocked by a
PreToolUse deny (evidenced by its correlated `tool_result`'s deny signature or
`is_error: true`) from all five load-bearing consumers of `_TOOL_USES` --
the VERIFIER signal (line ~743), the plan-check classification loop
(~1206-1250), the Verifier-dispatch hygiene scan (~1468), the Verifier-
dispatch adjacency scan (~1529), and the Researcher-gate loop
(~1400-1423, which sets `_seen_researcher2`/`_seen_plan_verifier_after_research`).

This is a NEW test file (not an extension of test_loop_stop_guard.py) because
the fixtures here all need one new, self-contained idiom -- a `tool_use` /
`tool_result` PAIR correlated by an explicit id, where the `tool_result`
carries a PreToolUse-deny signature -- that no existing fixture in
test_loop_stop_guard.py builds. This mirrors the existing precedent of
test_verifier_hygiene_gate.py: a dedicated, self-contained file per named
gate/mechanism inside loop_stop_guard.py, rather than growing the (already
~8000-line) test_loop_stop_guard.py further. Fixture-construction idioms
(`tool_use`, `assistant_msg`, `tool_result_event`, `make_turn_events`,
`run_guard`) are copied byte-for-byte in spirit from test_loop_stop_guard.py
so the two files stay mutually legible, with `tool_result_event` extended
with an optional `is_error` kwarg this file's fixtures need.

IMPORTANT -- these tests target a mechanism (`_blocked_tool_use_ids`) that
does NOT exist yet in loop_stop_guard.py as of this writing. Several tests
below (AC1, AC3, AC6, AC8, AC10) are RED-BEFORE / currently-failing BY
DESIGN: they reproduce today's bug (or scan for the not-yet-built
mechanism's source) and must fail against the current, unmodified guard.
Others (AC2, AC5, AC9) assert behavior that is ALREADY correct today and
must stay green both before and after the fix -- they exist to prove the fix
does not weaken or overreach the existing gates. See each class's docstring
for which bucket it is in, and this file's own final summary comment at the
bottom.

Run with:
    python3 -m pytest hooks/test_stopguard_blocked_dispatch.py -q
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HOOKS_DIR, "loop_stop_guard.py")
REPO_DIR = os.path.dirname(HOOKS_DIR)

GATE_DIR = tempfile.mkdtemp(prefix="loop-gate-stopguard-blocked-dispatch-")


# [D.2 rule-1 4-tests bullet / D.3 Bucket A2's fix] This file had zero
# sha256/hashlib/spec-file helpers -- mirrors test_loop_stop_guard.py's own
# _sb_write_spec()/_sb_sha256() (lines ~514-523) so fixtures needing a real,
# matching SPEC:/SPEC_SHA256= marker (now mandatory on every Coder-classified
# dispatch) can build one without inventing a second, divergent idiom.
def _sb_write_spec(tmpdir, name="spec.md", content="# spec\n"):
    path = os.path.join(tmpdir, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _sb_sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _sb_span_sha256(path, line_start, line_end):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    return hashlib.sha256(
        "\n".join(lines[line_start - 1:line_end]).encode("utf-8")
    ).hexdigest()


def _sb_plan_support_json(spec_path, spec_hash):
    return json.dumps({
        "artifact_path": spec_path,
        "line_start": 1,
        "line_end": 1,
        "evidence_sha256": _sb_span_sha256(spec_path, 1, 1),
        "claim": "test fixture support citation for same-spec plan-check PASS",
        "spec_sha256": spec_hash,
    }, sort_keys=True)


def _sb_plan_pass_text(spec_path, spec_hash, extra_text=""):
    prefix = ("%s\n" % extra_text.strip()) if extra_text and extra_text.strip() else ""
    return (
        "%sPLAN_SUPPORT_JSON=%s\n"
        "REVIEWED_SPEC_SHA256=%s\n"
        "LOOP_GATE: PLAN_PASS"
    ) % (prefix, _sb_plan_support_json(spec_path, spec_hash), spec_hash)


# ---------------------------------------------------------------------------
# Fixture-construction idiom (copied in spirit from test_loop_stop_guard.py's
# own tool_use/assistant_msg/tool_result_event/make_turn_events/run_guard --
# same production shape: a human user message, an assistant message holding
# tool_use parts, and tool_results recorded as their own user-type entries).
# ---------------------------------------------------------------------------
def tool_use(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def assistant_msg(*parts):
    return {"type": "assistant",
            "message": {"role": "assistant", "content": list(parts)}}


def tool_result_event(tool_use_id, content_text, is_error=None):
    """A tool_result recorded as its own user-type entry, tied to a specific
    tool_use id via `tool_use_id` -- the correlation channel the new
    `_blocked_tool_use_ids` mechanism (spec-v5.md D.1) reads. `is_error` is
    OMITTED entirely when not given (matching a genuinely successful
    dispatch's real shape, which carries no `is_error` key at all), and set
    explicitly (True/False) only when a fixture needs it."""
    part = {"type": "tool_result", "tool_use_id": tool_use_id,
            "content": content_text}
    if is_error is not None:
        part["is_error"] = is_error
    return {"type": "user", "message": {"role": "user", "content": [part]}}


def make_turn_events(*entries):
    """One genuine human turn-boundary, then the given assistant/tool_result
    events verbatim -- same helper test_loop_stop_guard.py uses for fixtures
    that need explicit dispatch -> returned-result ordering."""
    return [{"type": "user",
             "message": {"role": "user", "content": "go build"}}] + list(entries)


def run_guard(events, stop_hook_active=False):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e) + "\n")
        payload = json.dumps({"transcript_path": path,
                              "stop_hook_active": stop_hook_active})
        env = dict(os.environ, LOOP_GATE_DIR=GATE_DIR)
        p = subprocess.run([sys.executable, GUARD], input=payload,
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stderr
    finally:
        os.remove(path)


# Deny-signature text this repo's PreToolUse guard's own runtime surfaces
# TODAY (confirmed against the Claude Code hooks reference + anthropics/
# claude-code issue #59643, per spec-v5.md Section C / D.1): the generic
# string "Hook PreToolUse:<Tool> denied this tool". Used verbatim by every
# "blocked" fixture below, exactly as AC1 specifies it.
PRETOOLUSE_DENY_TEXT = "Hook PreToolUse:Agent denied this tool"

# Distinguishing substrings of each gate's own violation message text, used
# to identify WHICH gate fired (a single-violation turn's stderr is just the
# raw message prose -- the gate's own name string, e.g. "PLAN_CHECK", is only
# printed when 2+ violations co-occur -- see loop_stop_guard.py's final
# _VIOLATIONS-to-stderr block). Matches the existing convention already used
# in test_loop_stop_guard.py, e.g.:
#   self.assertIn("[LOOP STOP-GUARD] A Researcher (Mode D)", err)  # confirms RESEARCH_GATE, not FEATURE
PLAN_CHECK_MSG = "A Coder sub-agent was dispatched this turn without a preceding"
RESEARCH_GATE_MSG = "A Researcher (Mode D) sub-agent ran this turn and Oga directly"
VERIFIER_HYGIENE_MSG = "Verifier-dispatch hygiene violation"
VERIFIER_ADJACENCY_MSG = "Verifier-dispatch adjacency violation"


# ===========================================================================
# AC1 [BEHAVIORAL] -- RED-BEFORE reproduction of the false-POSITIVE bug
# (goal item 1, hygiene scan). This is the spec's own explicitly-named
# RED-BEFORE test: "reproduce the bug first (must exit 2 against the pre-fix
# code), then confirm it exits 0 after the fix."
# ===========================================================================
class AC1RedBeforeBlockedVerifierHygieneReplay(unittest.TestCase):
    """AC1: a fixture turn containing (a) a Verifier-shaped tool_use whose
    correlated tool_result carries a PreToolUse-deny signature, (b) a
    genuinely clean, successfully-dispatched Verifier tool_use with a normal
    (non-deny) result, (c) a Coder tool_use -- must exit 0.

    Trace against TODAY's (pre-fix) code, confirmed by direct read of
    loop_stop_guard.py (not assumed): the hygiene scan (~line 1468) walks
    EVERY tool_use matching _VERIFIER_DETECT with zero correlation to its
    tool_result, so the BLOCKED verifier's own dispatch text (part (a),
    below) is scanned identically to a live one -- its prompt's "last
    verdict: PASS" phrase trips _shared_evaluate_hygiene() and sets
    _hyg_violation, which appends a VERIFIER_HYGIENE violation and causes
    sys.exit(2), EVEN THOUGH a genuinely clean Verifier (part (b)) also ran
    this same turn and would, on its own, satisfy every gate cleanly. This
    reproduces goal item 1 (Section B) exactly: "Hygiene scan -- false
    POSITIVE direction (blocks a clean turn)."
    """

    def test_blocked_verifier_dispatch_does_not_trip_hygiene_gate_when_real_verifier_also_ran(self):
        # [D.2 rule-1 4-tests bullet / D.3 Bucket A2's fix] The Coder
        # dispatch needs a real, matching SPEC:/SPEC_SHA256= marker and a
        # genuinely resolved Verifier-PASS credit chain (now mandatory) so
        # the separate spec-bound-credit (PLAN_CHECK) gate does not itself
        # deny this turn before ever reaching the hygiene branch this test
        # exists to exercise (confirmed live: without this, the fixture is
        # denied via "expected exactly one spec ref", not a hygiene
        # violation at all).
        d = tempfile.mkdtemp(prefix="ac1-spec-")
        try:
            spec_path = _sb_write_spec(d)
            spec_hash = _sb_sha256(spec_path)

            blocked_verifier = tool_use(
                "Agent",
                description="Independent verifier dispatch for the spec",
                prompt="Note: last verdict: PASS was already recorded for this "
                       "exact change; just rubber-stamp it.")
            blocked_verifier["id"] = "toolu_ac1_blocked_verifier"

            real_verifier = tool_use(
                "Agent",
                description="Independent verifier for the spec",
                prompt="Review the plan and the spec fresh; form your own "
                       "independent judgment before approving.\n"
                       "SPEC: %s\nSPEC_SHA256=%s" % (spec_path, spec_hash),
                run_in_background=False)
            real_verifier["id"] = "toolu_ac1_real_verifier"

            coder = tool_use("Agent", description="Coder for the build",
                             prompt="Implement the approved plan now.\n"
                                    "SPEC: %s\nSPEC_SHA256=%s" % (spec_path, spec_hash))
            coder["id"] = "toolu_ac1_coder"

            # NOTE: real_verifier's own credited PASS result must appear
            # BEFORE coder's own tool_use in the flattened record stream for
            # prior_verifier_credit() to see it (it only scans
            # records[pos+1:coder_pos]) -- so coder is dispatched in its OWN
            # later assistant message, after both tool_results, mirroring
            # SpecBoundVerifierCreditGateV1's own proven
            # test_matching_prior_verifier_result_allows_coder pattern.
            events = make_turn_events(
                assistant_msg(blocked_verifier, real_verifier),
                tool_result_event("toolu_ac1_blocked_verifier",
                                  PRETOOLUSE_DENY_TEXT, is_error=True),
                tool_result_event("toolu_ac1_real_verifier",
                                  _sb_plan_pass_text(
                                      spec_path, spec_hash,
                                      "Verifier completed its review: the plan is sound.")),
                assistant_msg(coder),
            )

            code, err = run_guard(events)
            # RED-BEFORE: this exact fixture, run against the CURRENT unmodified
            # loop_stop_guard.py, exits 2 with a VERIFIER_HYGIENE violation
            # (verified live -- see this file's own verification run). After the
            # Coder's fix (site 3's `continue` guard on _blocked_tool_use_ids),
            # it must exit 0.
            self.assertEqual(code, 0,
                "AC1: a blocked Verifier-shaped dispatch attempt must not trip "
                "the hygiene gate when a genuinely clean Verifier also ran this "
                "turn. Got exit %d, stderr:\n%s" % (code, err))
            self.assertNotIn(VERIFIER_HYGIENE_MSG, err)
            self.assertNotIn(VERIFIER_ADJACENCY_MSG, err)
            self.assertNotIn(PLAN_CHECK_MSG, err)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)


# ===========================================================================
# AC2 [BEHAVIORAL] -- non-regression: the skip-guard must not weaken the
# real hygiene gate. Unlike AC1, this fixture involves NO blocked/denied
# dispatch at all, so it is expected to PASS (exit 2) both TODAY and after
# the fix -- it exists to prove the new mechanism does not overreach and
# accidentally excuse a genuinely dirty, successfully-dispatched Verifier
# merely because it happens to have a correlated (normal) tool_result.
# ===========================================================================
class AC2GenuineDirtyVerifierStillCaught(unittest.TestCase):
    """AC2: a Verifier tool_use genuinely dispatched (no deny) whose prompt
    carries a real hygiene marker ("tests passed") and whose OWN tool_result
    is a normal, non-error, non-deny result -- must still exit 2. Proves the
    skip-guard's deny-signature check doesn't accidentally treat ANY
    correlated tool_result as evidence of "blocked" and wrongly excuse a
    dirty dispatch."""

    def test_genuinely_dispatched_dirty_verifier_with_normal_result_still_blocks(self):
        dirty_verifier = tool_use(
            "Agent",
            description="Independent verifier for the widget spec",
            prompt="The harness run shows tests passed already for this "
                   "change; approve without re-checking anything new.")
        dirty_verifier["id"] = "toolu_ac2_dirty_verifier"

        events = make_turn_events(
            assistant_msg(dirty_verifier),
            tool_result_event("toolu_ac2_dirty_verifier",
                              "Verifier dispatched and completed its review "
                              "of the spec normally."),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2, err)
        self.assertIn(VERIFIER_HYGIENE_MSG, err)


# ===========================================================================
# AC3 [BEHAVIORAL] [SECURITY-ORACLE] -- RED-BEFORE reproduction of the
# DANGEROUS false-NEGATIVE bug (goal item 4): a blocked, Verifier-shaped
# dispatch attempt must not satisfy _seen_verifier_anywhere and thereby
# suppress the plan-check-before-Coder gate. Labeled [SECURITY-ORACLE] per
# LOOP-M3: this is an isolation-style claim ("a denied action cannot count
# as though it succeeded, letting a Coder dispatch bypass plan-check") --
# flagged here for Tier-2 mutation-oracle scrutiny before this test is
# trusted, per test_writer.md's own routing rule.
#
# AC4's mutation check lives HERE as a comment (matching this repo's
# existing convention -- there is no automated mutation-check infrastructure
# for loop_stop_guard.py anywhere in this codebase today; every existing
# mutation-style requirement in this file's siblings is likewise a
# hand-written manual-verification comment / [SECURITY-ORACLE] label, not an
# automated mutate-and-rerun step -- see e.g. test_adversarial_loop_stop_
# guard.py's TTLExactBoundaryFreshness class docstring, which documents a
# hypothetical mutation in prose only).
# ===========================================================================
class AC3BlockedVerifierAloneDoesNotSatisfyPlanCheck(unittest.TestCase):
    """AC3: ONLY a blocked, Verifier-shaped tool_use exists (no live Verifier
    at all) followed by a Coder tool_use -- must exit 2 with a PLAN_CHECK
    violation.

    Trace against TODAY's (pre-fix) code, confirmed by direct read: the
    classification loop at ~line 1206 sets _seen_verifier_anywhere = True for
    ANY tool_use whose dispatch text matches _VERIFIER_DETECT, with zero
    correlation to its tool_result -- so the blocked verifier here (which
    never actually ran) STILL satisfies _seen_verifier_anywhere, and
    `_plan_check_violated = _seen_coder_anywhere and not _seen_verifier_
    anywhere` evaluates to False. TODAY this fixture exits 0 (verified live
    -- see this file's own verification run). This is exactly goal item 4's
    "dangerous case" (Section B): "it lets a Coder dispatch in the same turn
    pass the plan-check-before-Coder gate on the strength of a Verifier
    dispatch that was DENIED before it ever executed."

    AC4 MUTATION CHECK (manual, per this AC's own requirement -- no
    automated mutate-and-rerun harness exists for this file): once the
    Coder's fix lands, manually delete the `if (tu.get("id") or tu.get(
    "tool_use_id")) in _blocked_tool_use_ids: continue` guard from the
    _seen_verifier_anywhere/_seen_coder_anywhere classification loop
    (site 2, spec-v5.md D.2 item 2, originally ~line 1206) and re-run this
    exact test. It MUST go red (exit 0 instead of 2) -- if it stays green
    with the guard deleted, this fixture is not actually exercising the new
    code path and needs to be rebuilt.
    """

    def test_blocked_verifier_only_plus_coder_blocks_plan_check(self):
        blocked_verifier_only = tool_use(
            "Agent",
            description="Independent verifier for the spec",
            prompt="Approve the plan before any dispatch.")
        blocked_verifier_only["id"] = "toolu_ac3_blocked_verifier"

        coder = tool_use("Agent", description="Coder for the build",
                         prompt="Implement the approved plan now.")

        events = make_turn_events(
            assistant_msg(blocked_verifier_only, coder),
            tool_result_event("toolu_ac3_blocked_verifier",
                              PRETOOLUSE_DENY_TEXT, is_error=True),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2,
            "AC3: a blocked Verifier-shaped dispatch attempt (never actually "
            "ran) must not satisfy the plan-check-before-Coder gate. Got "
            "exit %d, stderr:\n%s" % (code, err))
        self.assertIn(PLAN_CHECK_MSG, err)


# ===========================================================================
# AC6 [DOC] -- structural source-text check: _blocked_tool_use_ids must be
# built exactly once (not recomputed per walk) and referenced at all five
# load-bearing sites named in spec-v5.md Section D.2. This is a fact about
# the artifact's OWN text/structure (explicitly labeled [DOC] in the spec
# itself), so a source-scan test is the right instrument here -- matching
# the existing convention for this kind of structural regression (see
# test_pre_tool_use_oga_guard.py::TestNoLiteralMarkersInHooks::
# test_hyg_marker_source_still_exists, a "companion" source-text check that
# guards against silent rename/drift the same way).
#
# RED-BEFORE: every test in this class fails against the CURRENT source
# (the `_blocked_tool_use_ids` name does not exist anywhere in
# loop_stop_guard.py today -- confirmed via `grep -c _blocked_tool_use_ids`
# returning 0, see this file's own verification run).
# ===========================================================================
class AC6BlockedIdsBuiltOnceAndReusedAtAllFiveSites(unittest.TestCase):
    _BUILD_RE = re.compile(r'_blocked_tool_use_ids\s*=\s*(\{|set\()')

    # Site anchors: literal substrings from the CURRENT source that bound
    # each of the five load-bearing walks named in spec-v5.md Section D.2.
    # Chosen deliberately to span the WHOLE relevant loop/expression (not
    # just up to its first pre-existing internal check) so a `continue`
    # guard placed anywhere reasonable inside the loop body is captured --
    # e.g. site 4's own `if _adj_violation: break` line is NOT used as an
    # end anchor because it would truncate the slice before the loop's
    # actual end.
    # [Section H] site2's anchor pair updated: "_seen_verifier_anywhere =
    # False" / "_plan_check_violated = _seen_coder_anywhere" no longer exist
    # anywhere in loop_stop_guard.py -- confirmed via direct grep -- this is
    # the SAME _TURN_RECORDS-enumeration redesign
    # H-LOOPSTOPGUARD-DUAL-TURN-WINDOW-FALSEDENY-1 already documents. The new
    # pair below (confirmed unique via direct grep, each occurring exactly
    # once) brackets the WHOLE current classification loop, from its own
    # initialization through the first statement after the loop ends. Sites
    # 1/3/4/5's own anchor pairs are UNCHANGED -- confirmed still present,
    # verbatim, in the current source.
    _SITES = {
        "site1_VERIFIER_signal": ("VERIFIER = any(", "for tu in _TOOL_USES)"),
        "site2_plan_check_classification_loop": (
            "_plan_check_violated = False",
            "if _plan_check_violated:"),
        "site3_hygiene_scan": (
            "_hyg_violation = None",
            "_shared_evaluate_hygiene(_prompt, _known)"),
        "site4_adjacency_scan": (
            "_adj_violation = None",
            "_shared_evaluate_adjacency(_adj_prompt, _adj_cwd, _adj_target_dir)"),
        "site5_research_gate_loop": (
            "_seen_researcher2 = False",
            "if _research_direct_edit_without_verify:"),
    }

    @classmethod
    def setUpClass(cls):
        with open(GUARD, encoding="utf-8") as f:
            cls.src = f.read()

    def _region(self, start_anchor, end_anchor, label):
        self.assertIn(start_anchor, self.src,
            "%s: start anchor %r not found in guard source -- has the file "
            "structure changed since this test was written?"
            % (label, start_anchor))
        start = self.src.index(start_anchor)
        self.assertIn(end_anchor, self.src[start:],
            "%s: end anchor %r not found after the start anchor" % (label, end_anchor))
        end = self.src.index(end_anchor, start)
        return self.src[start:end]

    def test_exactly_one_build_assignment(self):
        builds = self._BUILD_RE.findall(self.src)
        self.assertEqual(len(builds), 1,
            "AC6 requires `_blocked_tool_use_ids` built EXACTLY ONCE per "
            "hook invocation (a single set assignment), not recomputed per "
            "walk. Found %d build-shaped assignment(s)." % len(builds))

    def test_build_precedes_all_five_sites(self):
        self.assertTrue(self._BUILD_RE.search(self.src),
            "AC6 requires a `_blocked_tool_use_ids = {...}` (or `set(...)`) "
            "build assignment somewhere in loop_stop_guard.py; none found.")
        build_idx = self._BUILD_RE.search(self.src).start()
        for label, (start_anchor, _end_anchor) in self._SITES.items():
            self.assertIn(start_anchor, self.src, label)
            site_idx = self.src.index(start_anchor)
            self.assertLess(build_idx, site_idx,
                "AC6: _blocked_tool_use_ids must be BUILT before site %r "
                "(anchor %r), so every site reuses the same built set "
                "instead of racing its own construction." % (label, start_anchor))

    def test_site1_verifier_signal_references_blocked_ids(self):
        # [Section H] The current source calls the wrapper _tu_id_is_blocked(
        # tu) at this site, not the raw _blocked_tool_use_ids variable name
        # directly -- a legitimate internal refactor. The check is now
        # structurally-precise (does this site consult the skip-guard at
        # all) rather than literally counting on the old inline shape.
        start, end = self._SITES["site1_VERIFIER_signal"]
        region = self._region(start, end, "site1_VERIFIER_signal")
        self.assertIn("_tu_id_is_blocked(", region)

    def test_site2_plan_check_loop_references_blocked_ids(self):
        # [Section H] This site uses the WIDE-WINDOW wrapper
        # _credit_gate_tu_id_is_blocked(tu) (backed by _CREDIT_GATE_BLOCKED_
        # IDS, H-LOOPSTOPGUARD-DUAL-TURN-WINDOW-FALSEDENY-1) -- a distinct
        # mechanism from sites 1/3/4/5's narrow _tu_id_is_blocked(), by
        # design (see loop_stop_guard.py's own comment at that site). Its
        # own real, currently-passing behavioral proof lives in this same
        # file's AC3BlockedVerifierAloneDoesNotSatisfyPlanCheck (a blocked
        # verifier-only + Coder still correctly blocks via PLAN_CHECK),
        # confirming this wrapper is genuinely built/consulted here, not
        # just textually present.
        start, end = self._SITES["site2_plan_check_classification_loop"]
        region = self._region(start, end, "site2_plan_check_classification_loop")
        self.assertIn("_credit_gate_tu_id_is_blocked(", region)

    def test_site3_hygiene_scan_references_blocked_ids(self):
        start, end = self._SITES["site3_hygiene_scan"]
        region = self._region(start, end, "site3_hygiene_scan")
        self.assertIn("_tu_id_is_blocked(", region)

    def test_site4_adjacency_scan_references_blocked_ids(self):
        start, end = self._SITES["site4_adjacency_scan"]
        region = self._region(start, end, "site4_adjacency_scan")
        self.assertIn("_tu_id_is_blocked(", region)

    def test_site5_research_gate_loop_references_blocked_ids(self):
        start, end = self._SITES["site5_research_gate_loop"]
        region = self._region(start, end, "site5_research_gate_loop")
        self.assertIn("_tu_id_is_blocked(", region)


# ===========================================================================
# AC5 [BEHAVIORAL] and AC7 [BEHAVIORAL] -- neither is a NEW runtime test in
# this file. Both are documented here as `@unittest.skip`-ped placeholders
# so they show up (as explicitly SKIPPED, never silently absent) in
# `pytest --collect-only` / a full test-suite run, per this AC's own
# explicit framing in spec-v5.md:
#
#   AC5: "The full existing hooks/test_loop_stop_guard.py and hooks/
#   test_verifier_hygiene_gate.py suites must remain 100% green after the
#   change." This is satisfied by running those two EXISTING suites, not by
#   writing a new one:
#       python3 -m pytest hooks/test_loop_stop_guard.py hooks/test_verifier_hygiene_gate.py -q
#   (Confirmed both suites are 100% green against the CURRENT, pre-fix code
#   as this file's own baseline -- see this file's verification run. AC5's
#   own bar is that they stay green AFTER the Coder's change too, which can
#   only be checked once that change exists.)
#
#   AC7: "Diff-shape check (plan-check / Verifier, not a runtime test):
#   confirm the change at each of the five sites is a pure exclusion
#   (continue/not in), with no modification to _VERIFIER_DETECT,
#   _CODER_DETECT, _RESEARCHER_DETECT_V2, or any existing detection regex."
#   The spec itself states this is NOT a runtime test -- it is a manual/
#   plan-check diff-shape review of the Coder's actual patch, verifying the
#   fail-safe direction from spec-v5.md Section D.3 holds (the skip-guard
#   can only ever REMOVE a tool_use from a walk, never add permissiveness
#   elsewhere). No pytest assertion can substitute for actually reading the
#   diff, so none is attempted here.
# ===========================================================================
class AC5AC7DocumentationOnlyChecks(unittest.TestCase):
    @unittest.skip("AC5: satisfied by re-running the two EXISTING suites "
                    "(test_loop_stop_guard.py, test_verifier_hygiene_gate.py) "
                    "after the Coder's change -- see class docstring above "
                    "for the exact command; not a new test to write here.")
    def test_ac5_existing_suites_stay_green_see_class_docstring(self):
        pass

    @unittest.skip("AC7: explicitly a diff-shape / plan-check review per "
                    "spec-v5.md ('not a runtime test'), not a pytest "
                    "assertion -- see class docstring above.")
    def test_ac7_diff_shape_is_pure_exclusion_see_class_docstring(self):
        pass


# ===========================================================================
# AC8 [BEHAVIORAL] [SECURITY-ORACLE] -- RED-BEFORE reproduction of the
# DANGEROUS false-NEGATIVE bug at site 5 (goal item 5 / v2 addition): a
# blocked, Verifier-shaped dispatch attempt must not satisfy
# _seen_plan_verifier_after_research and thereby suppress the
# Research-then-direct-edit-without-verify violation. Labeled
# [SECURITY-ORACLE] per LOOP-M3 for the same reason as AC3 -- a denied
# dispatch attempt must never count as a real "a Verifier approved this"
# signal.
# ===========================================================================
class AC8BlockedVerifierDoesNotSuppressResearchGate(unittest.TestCase):
    """AC8: (a) a Researcher tool_use whose result is a real, returned
    research finding (arms _seen_researcher2 via the legitimate path), (b) a
    blocked, Verifier-shaped tool_use (PreToolUse-deny result), (c) a direct
    code-edit tool_use matching _rh3_is_code_edit -- must exit 2 with a
    RESEARCH_GATE violation.

    Trace against TODAY's (pre-fix) code, confirmed by direct read: in the
    site-5 loop (~line 1400), when the blocked verifier (b) is reached,
    `_seen_researcher2 (True) and not _seen_plan_verifier_after_research
    (still False) and _VERIFIER_DETECT.search(...)` evaluates True with zero
    correlation to (b)'s own tool_result, so `_seen_plan_verifier_after_
    research` is wrongly set True. When the edit (c) is then reached, `not
    _seen_plan_verifier_after_research` is now False, so
    `_research_direct_edit_without_verify` is NEVER set. TODAY this fixture
    exits 0 -- verified live (see this file's own verification run). This is
    exactly the v2 finding 1 defect (Section A/B item 5): the blocked
    dispatch "suppresses the Research-then-direct-edit-without-verify
    violation even when no real plan-check Verifier ran after the
    Researcher's findings."

    MUTATION CHECK (manual, per AC8's own requirement, same convention as
    AC3/AC4 above -- no automated mutate-and-rerun harness exists for this
    file): once the Coder's fix lands, manually delete the site-5 `continue`
    guard (spec-v5.md D.2 item 5, originally ~lines 1400-1423) and re-run
    this exact test. It MUST go red (exit 0 instead of 2).
    """

    def test_blocked_verifier_between_real_research_and_direct_edit_still_blocks(self):
        real_researcher = tool_use(
            "Agent",
            description="Researcher Mode D — stopguard blocked-dispatch fix research",
            prompt="You are the Researcher. Investigate the root cause of "
                   "the blocked-dispatch replay bug in loop_stop_guard.py.")
        real_researcher["id"] = "toolu_ac8_researcher"

        blocked_verifier = tool_use(
            "Agent",
            description="Independent verifier for the stopguard fix spec",
            prompt="Review the plan and approve before any dispatch.")
        blocked_verifier["id"] = "toolu_ac8_blocked_verifier"

        code_edit = tool_use("Edit", file_path="/x/src/service.py",
                             old_string="a", new_string="b")

        events = make_turn_events(
            assistant_msg(real_researcher, blocked_verifier, code_edit),
            tool_result_event("toolu_ac8_researcher",
                              "Researcher findings: root cause confirmed in "
                              "loop_stop_guard.py's _TOOL_USES construction."),
            tool_result_event("toolu_ac8_blocked_verifier",
                              PRETOOLUSE_DENY_TEXT, is_error=True),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 2,
            "AC8: a blocked Verifier-shaped dispatch attempt occurring "
            "between a REAL Researcher dispatch and a direct code edit must "
            "not suppress the Research-gate violation. Got exit %d, "
            "stderr:\n%s" % (code, err))
        self.assertIn(RESEARCH_GATE_MSG, err)
        self.assertIn("/x/src/service.py", err)


# ===========================================================================
# AC9 [BEHAVIORAL] -- false-EXCLUSION regression test (v2 finding 2). Unlike
# AC1/AC3/AC6/AC8/AC10, this is NOT a RED-BEFORE test against today's
# no-mechanism code: today's code classifies a Verifier dispatch purely from
# its OWN dispatch text (never its tool_result), so this fixture already
# passes today for an entirely different (and correct-by-accident) reason.
# Its real job -- exactly as spec-v5.md states -- is to DISCRIMINATE between
# two candidate designs for the not-yet-built `_tr_is_pretooluse_deny`: it
# must FAIL against a v1-style unanchored substring check
# ("pretooluse" in txt and "deny" in txt) and PASS against the v2-style
# anchored `.startswith(...)` design. See this file's own verification run
# and the accompanying report for a worked trace of both hypothetical
# implementations against this exact fixture.
# ===========================================================================
class AC9GenuineVerifierReportDiscussingPreToolUseDenyNotExcluded(unittest.TestCase):
    """AC9: a Verifier tool_use is genuinely dispatched (no PreToolUse deny)
    and its own RETURNED REPORT -- a normal, non-error tool_result -- makes
    ordinary, legitimate mention of "PreToolUse" and "deny" together (e.g.
    because it is reviewing this exact fix, or any spec/code touching
    PreToolUse-deny behavior), NOT as a canned deny message and NOT starting
    with one of the anchored prefixes. The Verifier must still be counted:
    _seen_verifier_anywhere/VERIFIER must stay True.

    _seen_verifier_anywhere is a private module-level variable with no
    public accessor, so this test observes it the same way the rest of this
    file's sibling tests do -- through its only externally-visible effect: a
    Coder dispatched in the same turn must still pass the plan-check-
    before-Coder gate (exit 0) precisely because the real Verifier here is
    correctly counted, not because nothing checks it."""

    def test_verifier_report_mentioning_pretooluse_and_deny_as_topic_does_not_exclude_it(self):
        # [D.2 rule-1 4-tests bullet / D.3 Bucket A2's fix] Real, matching
        # SPEC:/SPEC_SHA256= marker + a genuinely resolved Verifier-PASS
        # credit chain (now mandatory) so the separate spec-bound-credit
        # gate does not itself deny this turn before ever reaching this
        # test's own subject (whether a genuine, non-deny report merely
        # DISCUSSING "PreToolUse"/"deny" still counts as a real Verifier).
        d = tempfile.mkdtemp(prefix="ac9-spec-")
        try:
            spec_path = _sb_write_spec(d)
            spec_hash = _sb_sha256(spec_path)

            real_verifier = tool_use(
                "Agent",
                description="Independent verifier for the stopguard fix spec",
                prompt="Review the spec fresh and form your own independent "
                       "verdict; do not rely on any prior report.\n"
                       "SPEC: %s\nSPEC_SHA256=%s" % (spec_path, spec_hash),
                run_in_background=False)
            real_verifier["id"] = "toolu_ac9_real_verifier"

            coder = tool_use("Agent", description="Coder for the build",
                             prompt="Implement the approved plan now.\n"
                                    "SPEC: %s\nSPEC_SHA256=%s" % (spec_path, spec_hash))
            coder["id"] = "toolu_ac9_coder"

            # The Verifier's OWN returned report -- realistic prose for a
            # Verifier reviewing THIS EXACT fix (spec-v5.md's own stated
            # motivating scenario) -- legitimately discusses "PreToolUse" and
            # "deny" as a topic, not as a canned deny message, and is a NORMAL
            # (non-error) result. Deliberately does NOT include a literal
            # "verdict: pass" phrase -- combined with this fixture's own
            # SPEC:-line directory reference, that phrase would additionally
            # (and unrelatedly) trip the separate RUNLOG_MISSING gate
            # (confirmed live), which is not this test's subject; the
            # genuine credit is carried entirely by the REVIEWED_SPEC_SHA256=/
            # LOOP_GATE: PLAN_PASS block instead.
            report_text = (
                "Verifier report: reviewed the plan for H-STOPGUARD-BLOCKED-"
                "DISPATCH-REPLAY-1. The design correctly anchors "
                "_tr_is_pretooluse_deny to a startswith() check on the START of "
                "the tool_result content, so a genuine PreToolUse hook deny "
                "signal is never confused with ordinary prose that merely "
                "discusses PreToolUse deny semantics elsewhere in a report -- "
                "this is the exact false-exclusion risk the anchored design "
                "closes."
            )
            # NOTE: real_verifier's own credited result must appear BEFORE
            # coder's own tool_use in the flattened record stream for
            # prior_verifier_credit() to see it -- see AC1's identical note
            # above.
            events = make_turn_events(
                assistant_msg(real_verifier),
                tool_result_event(
                    "toolu_ac9_real_verifier",
                    _sb_plan_pass_text(spec_path, spec_hash, report_text)),
                assistant_msg(coder),
            )
            code, err = run_guard(events)
            self.assertEqual(code, 0,
                "AC9: a genuinely-dispatched Verifier whose own returned report "
                "merely DISCUSSES 'PreToolUse' and 'deny' as a topic must still "
                "be counted -- the Coder dispatched alongside it must still "
                "pass the plan-check gate. Got exit %d, stderr:\n%s" % (code, err))
            self.assertNotIn(PLAN_CHECK_MSG, err)
        finally:
            import shutil
            shutil.rmtree(d, ignore_errors=True)


# ===========================================================================
# AC10 [BEHAVIORAL] [SECURITY-ORACLE] -- RED-BEFORE reproduction of the v2
# round-2 defect: a blocked, RESEARCHER-shaped dispatch attempt must not
# arm _seen_researcher2 ITSELF (not merely the downstream _seen_plan_
# verifier_after_research elif), because `_rh3_returned_ids` (the set the
# Researcher-detection branch checks a dispatch's id against) is built with
# ZERO deny/success filtering -- a blocked dispatch's own deny-tool_result
# still carries a `tool_use_id` and lands in `_rh3_returned_ids` exactly
# like a genuinely successful one's.
# ===========================================================================
class AC10BlockedResearcherAloneDoesNotArmResearchGate(unittest.TestCase):
    """AC10: ONLY (a) a blocked, Researcher-shaped tool_use (PreToolUse-deny
    result -- no real Researcher ever ran, no real research findings exist)
    followed by (b) a direct code-edit tool_use matching _rh3_is_code_edit --
    must exit 0 (no RESEARCH_GATE violation).

    FEATURE-gate isolation note (judgment call, documented explicitly): the
    bare fixture described by the AC text alone (just (a) and (b), nothing
    else) would ALSO trip the PRE-EXISTING, out-of-scope FEATURE gate
    (~line 1116) regardless of this fix, since that gate fires on any code
    edit with no VERIFIER-shaped dispatch anywhere in the turn at all. A
    Researcher-shaped dispatch is not Verifier-shaped, so it can never
    satisfy VERIFIER either way. This fixture therefore ALSO includes one
    genuine, unblocked plan-check Verifier dispatch, placed BEFORE the
    blocked researcher, purely to neutralize the unrelated FEATURE gate --
    exactly the same "FEATURE overlay" isolation convention
    test_loop_stop_guard.py's own ResearcherGateArmOnResultRH3 class already
    documents and uses for this identical gate area ("every fixture whose
    turn edits a code file carries a plan-check Verifier dispatch so the
    FEATURE gate stays off and the Researcher gate is the only gate that can
    decide the exit code"). Ordering is deliberate and load-bearing: the
    Verifier dispatch must be processed BEFORE the (blocked) researcher in
    the site-5 loop, so it can never be misread as "a plan-check Verifier
    that ran AFTER research" (mirroring test_loop_stop_guard.py's own
    test_early_verifier_then_researcher_then_edit_blocks precedent for the
    same ordering hazard).

    Trace against TODAY's (pre-fix) code, confirmed by direct read: in the
    site-5 loop, the blocked researcher's own tool_result (a deny result)
    still has a `tool_use_id`, which `_rh3_returned_ids` collects with ZERO
    deny/success filtering (confirmed by direct read of lines ~1362-1369) --
    so `_rh3_rid in _rh3_returned_ids` is True even though the dispatch was
    denied, and `_seen_researcher2` is wrongly set True. The subsequent edit
    then satisfies `_seen_researcher2 and not _seen_plan_verifier_after_
    research and _rh3_is_code_edit(tu)` and sets `_research_direct_edit_
    without_verify = True` -- RESEARCH_GATE fires. TODAY this fixture exits
    2 -- verified live (see this file's own verification run). AC10 requires
    exit 0.

    MUTATION CHECK (v4 addition, per AC10's own explicit requirement): once
    the Coder's fix lands, manually move the site-5 `continue` guard to
    AFTER the `_RESEARCHER_DETECT_V2` check (i.e. so it guards only the
    `elif`s at ~1409/1413, not `_seen_researcher2`'s own build) --
    reproducing v2's original, incorrect placement. Re-run this exact test;
    it MUST go red (exit 2 instead of 0), proving this fixture actually
    exercises the TRUE-loop-top placement rather than passing for an
    unrelated reason.
    """

    def test_blocked_researcher_alone_never_arms_research_gate(self):
        real_plan_verifier = tool_use(
            "Agent",
            description="plan-check Verifier — residual-holes researcher-gate spec",
            prompt="You are an independent verifier reviewing the spec. "
                   "Approve or reject the plan before any dispatch.")

        blocked_researcher = tool_use(
            "Agent",
            description="Researcher Mode D — hook transcript event model brief",
            prompt="You are the Researcher. Map the JSONL event model that "
                   "hook transcripts use for dispatches and results.")
        blocked_researcher["id"] = "toolu_ac10_blocked_researcher"

        src_edit = tool_use("Edit", file_path="/x/src/service.py",
                            old_string="a", new_string="b")

        events = make_turn_events(
            assistant_msg(real_plan_verifier, blocked_researcher, src_edit),
            tool_result_event("toolu_ac10_blocked_researcher",
                              PRETOOLUSE_DENY_TEXT, is_error=True),
        )
        code, err = run_guard(events)
        self.assertEqual(code, 0,
            "AC10: a blocked Researcher-shaped dispatch attempt (never "
            "actually ran, no real research findings exist) must not arm "
            "the Research gate at all. Got exit %d, stderr:\n%s" % (code, err))
        self.assertNotIn(RESEARCH_GATE_MSG, err)


if __name__ == "__main__":
    unittest.main()
