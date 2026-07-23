#!/usr/bin/env python3
"""Executable acceptance suite for the control-plane dashboard slice added to
``product_dashboard.py`` (Tier-1, spec-only; spec:
runs/2026-07-11_control-plane-dashboard/specs/spec.md (repo-root-relative --
NOT ``loop-team/runs/...``, which does not exist on disk; ``runs/`` is
gitignored, see ``test_spec_reference_path_correct_and_present`` below), V9,
SPEC_SHA256=1d59c50d306870106b78ed3028525700febadff6a66f2aa7bb0ee371ca758b0e).

Written BEFORE the implementation exists. Every test is expected to FAIL
until the Coder extends ``loop-team/harness/product_dashboard.py`` with the
public interface documented below. Do NOT put any implementation here.

Target: Python 3.9 (no ``X | Y`` union syntax anywhere in this file).

===========================================================================
PUBLIC INTERFACE CONTRACT -- the Coder must add ALL of the following to
``product_dashboard.py`` (module referenced below as ``pd``). Names/shapes
are this Test-writer's own design choice (the spec fixes semantics, not
exact API surface) -- follow them exactly so this suite is the oracle.
===========================================================================

Module-level constants (informative; tests do not hard-require every one of
these to exist as an attribute, only the behavior they describe):
    PROOF_CLASS_ENUM            = frozenset({"unit_or_mock", "build_or_typecheck",
                                   "preflight", "live_smoke", "dashboard_render",
                                   "readback_cleanup", "repo_health"})   # AC3, 7 values
    CLAIMED_EVIDENCE_LABEL_ENUM = frozenset({"mock-tested", "build-clean",
                                   "preflight-pass", "live-smoke-pass", "ready"})  # AC4
    WIP_COLUMN_ENUM             = frozenset({"Ready", "Doing", "Evidence Needed",
                                   "Blocked External", "Done Verified"})  # AC6.1
    EVIDENCE_LABEL_RANK = {"Unverified": 0, "mock-tested": 1, "build-clean": 2,
                            "preflight-pass": 3, "live-smoke-pass": 4, "ready": 5}  # AC6.3 ladder

Exceptions (module-level, importable from ``product_dashboard``):
    class InvalidProofRecordError(Exception): ...
        Raised by ``validate_proof_record()`` for a HARD-reject condition
        only: a missing required AC2 field, an out-of-enum ``proof_class``
        (AC3), an out-of-enum claimed ``evidence_label`` (AC4), a claimed
        ``evidence_label`` in {"mock-tested","build-clean","preflight-pass",
        "live-smoke-pass"} whose OWN ``proof_class`` does not match that
        label's required proof_class (AC4's per-label mapping, self-
        referential: ``mock-tested``<->``unit_or_mock``, ``build-clean``<->
        ``build_or_typecheck``, ``preflight-pass``<->``preflight``,
        ``live-smoke-pass``<->``live_smoke``), or a claimed
        ``evidence_label == "ready"`` (ALWAYS rejected -- no single record
        carries the 2-3 distinct proof_classes "ready" needs, AC4 last
        para). NOTE: this self-consistency check does NOT apply when
        ``proof_class`` is ``dashboard_render``/``readback_cleanup``/
        ``repo_health`` -- AC4's bulleted per-label mapping names no
        required class for those three, so such a record may carry any of
        the four non-"ready" enum labels as a nominal tag (fixtures below
        use "build-clean" for these three proof_classes by convention).
        Staleness/freshness (git_sha mismatch, timestamp age, artifact-hash
        mismatch) is NEVER a hard-reject -- it is soft, reflected only in
        the returned record's ``stale_or_valid`` field (see below).
    class InvalidItemError(Exception): ...
        Raised by ``validate_item()`` for an out-of-enum ``wip_column``
        (AC6.1), parallel to AC3's closure rule.

Functions:

  validate_proof_record(record, current_head=None, recompute_artifact_hash=None, now=None)
      -> dict  (a NEW dict: a copy of ``record`` PLUS a computed
         ``stale_or_valid`` key set to the string ``"stale"`` or ``"valid"``
         -- the 13th AC2 field, "derived by validation, never author-
         asserted"). ``record`` is expected to already carry the other 12
         AC2 fields (product, claim, evidence_label, proof_class, command,
         cwd, git_sha, exit_code, output_hash, artifact_hashes, timestamp,
         source_artifact_path).
      Raises InvalidProofRecordError for any HARD-reject condition above.
      ``current_head``: str or None. If given and
          ``record["git_sha"] != current_head``, freshness fails (stale).
          If None, the git-HEAD freshness axis is SKIPPED (treated as
          passing) -- this is the injection point fixture-only tests use to
          avoid needing a real git repo.
      ``recompute_artifact_hash``: optional callable ``path -> sha256hex``.
          If given, every ``(path, stored_hash)`` in
          ``record["artifact_hashes"]`` is re-checked: any path whose
          recomputed hash != stored hash makes the record stale. If None,
          this axis is SKIPPED (treated as passing) -- same rationale.
      ``now``: optional ``datetime`` (default: real UTC now) -- injected
          "current time" so a staleness test never depends on wall-clock
          flakiness. This suite pins only qualitative extremes (a
          decades-old timestamp vs. "now"), never the Coder's exact
          numeric staleness-threshold constant (that threshold and its
          value are the Coder's own choice, stated in the run log per the
          spec's "Coder-defined, run-log-stated threshold" wording).

  validate_item(item)
      -> dict (copy of ``item``, unchanged content -- validation only)
      Raises InvalidItemError if ``item["wip_column"]`` is not one of the 5
      AC6.1 enum values (only called when the item is NOT legacy-shaped;
      see the legacy-mapping note below).

  build_proof_record_from_snapshot(snapshot_record, snapshot_path, product,
                                    claim, evidence_label, proof_class, cwd,
                                    git_sha, source_artifact_path)
      -> dict (a raw, NOT-yet-``validate_proof_record``-ed AC2-shaped proof
         record dict; ``stale_or_valid`` absent)
      AC1's reuse-boundary primitive: ``snapshot_record`` is the ``record``
      dict returned by ``run_and_record.run_and_record(command)`` (or
      loaded back from the ``snapshot_path`` it wrote). This function MUST
      populate the returned dict's ``command``/``exit_code``/``output_hash``/
      ``artifact_hashes``/``timestamp`` fields FROM
      ``snapshot_record["command"]``/``["exit_code"]``/``["output_sha256"]``/
      ``["files"]``/``["captured_at"]`` respectively (byte-identical, no
      re-derivation) -- test 25 asserts this equality directly. The other
      six fields (product/claim/evidence_label/proof_class/cwd/git_sha/
      source_artifact_path) come from this function's own arguments
      (author-supplied / control-plane-captured per the AC2 origin table).

  derive_evidence_label(item, proof_records, live_repo_health="CLEAR")
      -> one of "Unverified", "mock-tested", "build-clean", "preflight-pass",
         "live-smoke-pass", "ready"
      Pure top-down AC4-ladder derivation (AC4b.2) over ``proof_records``
      (the item's whole ``(product, claim)`` group, EACH ALREADY RUN through
      ``validate_proof_record`` -- i.e. each dict already carries
      ``stale_or_valid``). Records with ``stale_or_valid != "valid"`` never
      count toward any tier. ``item["requires_cleanup"]`` (bool, AC6.4)
      gates whether a ``readback_cleanup`` proof is required for "ready".
      ``live_repo_health``: the CALLER-SUPPLIED result ("CLEAR" or
      "FROZEN") of the live ``repo_health_gate.py <repo-id>`` check for
      ``item["product"]`` (AC9) -- THIS IS THE INJECTION POINT. The real
      CLI/render path resolves this once per product via a genuine live
      call (subprocess to ``repo_health_gate.py``, or
      ``compute_verdict(load_ledger(_default_ledger_path()), item["product"])
      ["verdict"]``); tests call this function directly with a literal
      string and never touch the real ``hardening_ledger.json``.
      Ladder (highest satisfied tier wins):
        mock-tested     <- a valid record with proof_class=="unit_or_mock"
        build-clean     <- a valid record with proof_class=="build_or_typecheck"
        preflight-pass  <- a valid record with proof_class=="preflight"
        live-smoke-pass <- a valid record with proof_class=="live_smoke" that is
                            ADDITIONALLY: non-demo (its "source_artifact_path"
                            does not contain "/demo/"), non-mock (neither any
                            token of its "command" list nor its
                            "source_artifact_path" contains the case-
                            insensitive substring "mock"), and carries a
                            non-empty "artifact_hashes" dict (a "readback-
                            confirmed artifact hash", AC4).
        ready           <- live-smoke-pass tier achieved AND a valid record
                            with proof_class=="dashboard_render" exists AND
                            (item["requires_cleanup"] is falsy OR a valid
                            record with proof_class=="readback_cleanup"
                            exists) AND live_repo_health == "CLEAR".
      A proof record's own claimed ``evidence_label`` field plays NO role in
      this derivation (AC4b.2: "an authored claim NEVER escalates the
      rendered label") -- only ``proof_class`` occurrence + the checks above
      matter. (A record claiming "ready" can never even reach this
      function's input list, since ``validate_proof_record`` always rejects
      it -- test 4b/17.)

  wip_mismatch(wip_column, derived_label, live_repo_health="CLEAR")
      -> bool
      Pure function implementing the AC6.3 contradiction table exactly,
      using EVIDENCE_LABEL_RANK for the ladder comparison:
        "Done Verified"     -> True iff rank(derived_label) < rank("ready")
                                OR live_repo_health == "FROZEN"  (the OR is
                                independent/defense-in-depth per AC9 -- test
                                14b pins this even for a hypothetical
                                derived_label=="ready").
        "Blocked External"  -> True iff rank(derived_label) >= rank("live-smoke-pass")
        "Evidence Needed"   -> True iff rank(derived_label) >= rank("live-smoke-pass")
        "Ready" / "Doing"   -> always False (never fire, AC6.3)

  discover_control_plane_items(root, status_paths=None, globs=None)
      -> list[dict]  (Python 3.9: no ``list[dict]`` runtime annotation used
         in the actual implementation, this is prose only)
      AC8 real-mode discovery: recursively finds ``<root>/runs/**/
      status.json`` (``glob.glob(pattern, recursive=True)`` or an
      ``os.walk``-based scan -- NOT a bare non-recursive glob), EXCLUDING
      any path containing "/demo/". When ``status_paths`` or ``globs`` is
      non-empty, it supplies the item set directly and BYPASSES the
      recursive default (including the "/demo/" exclusion) -- AC5's
      override rule, which is what makes test 27 reachable.
      MUST NOT import or call ``evidence_ledger.build_ledger`` anywhere on
      this path (AC1's reuse-boundary; test 25's second half asserts this
      via monkeypatch).
      Each returned item dict carries at minimum: "product", "claim",
      "wip_column", "requires_cleanup", "source_path" (the status.json path
      it was read from -- used for "/demo/" per-item marking, AC10.1), and
      "proof_records" (list of RAW, not-yet-validated AC2-shaped dicts, read
      from that item's own "proofs" array in the on-disk status.json --
      see ON-DISK SHAPE below). A legacy-shaped item (see below) is
      returned too, still carrying "source_path" and (possibly empty)
      "proof_records", plus whatever legacy fields it had (e.g. "status",
      "verified", "evidence") so the renderer can map it down.

  render_control_plane(items, out, focus=None, repo_health_lookup=None,
                        current_head_lookup=None, recompute_artifact_hash=None)
      -> str  (the HTML text; also written to ``out``)
      Pure-Python entry point requiring NO subprocess -- the hook this
      suite's fixture-based render tests use. ``items`` is a list of item
      dicts shaped as ``discover_control_plane_items`` would return (or a
      hand-built fixture with the same keys; "proof_records" holds RAW,
      unvalidated AC2-shaped dicts -- ``render_control_plane`` internally
      calls ``validate_proof_record``/``derive_evidence_label``/
      ``wip_mismatch`` per item and discards records that fail hard
      validation).
      ``repo_health_lookup``: optional callable ``product -> "CLEAR"/
          "FROZEN"``; default is a real live lookup. EVERY test in this
          suite passes an explicit fake lookup (never the default) so the
          real ``hardening_ledger.json`` is never read by this suite.
      ``current_head_lookup`` / ``recompute_artifact_hash``: optional
          callables threaded straight into each item's per-record
          ``validate_proof_record`` call. When left None (the default this
          suite always uses for pure-fixture render tests), those two
          freshness axes are SKIPPED for every record (see
          ``validate_proof_record`` above) -- deliberately, so a render
          test needs no real git repo or real files on disk. The genuine
          CLI/disk path (``main()``) wires these to real
          ``git rev-parse HEAD`` / real re-hash checks.
      ``focus``: the one product name to highlight with ``.cp-focus``, or
          None/absent-product-name for no highlight (AC7 -- never an error
          either way).
      Emits the AC-RENDER bar classes exactly as named there:
        .cp-demo           -- item's "source_path" contains "/demo/" (AC10.1)
        .cp-mismatch        -- wip_mismatch(...) is True (AC6.3/AC9)
        .cp-focus           -- item["product"] == focus (AC7)
        .cp-legacy-label     -- item is legacy-shaped (mapped down, AC10.1/test11)
        .cp-verified         -- wip_column=="Done Verified" AND derived_label
                                =="ready" AND NOT wip_mismatch(...) (AC-RENDER)
      PLUS two base display classes (this Test-writer's own naming choice,
      NOT part of AC-RENDER's closed 5-class "must be seen" enumeration --
      these are the ordinary always-present value renders that AC-RENDER's
      enumeration presupposes exist, distinct elements per test 8/16):
        .cp-wip              -- element whose text is the item's authored
                                wip_column value (or its legacy-mapped
                                equivalent)
        .cp-evidence          -- element whose text is the item's DERIVED
                                evidence_label (AC6.2; "Unverified" string
                                for the derived-absence case)

  Legacy-item detection (used by both discover_control_plane_items and
  render_control_plane, and by the pre-existing legacy render path):
      An item dict that lacks a "wip_column" key entirely (i.e. came from
      an old-shape status.json with the pre-existing ``items[].{title,
      status,verified,phase,evidence}`` shape, see test_product_dashboard.py)
      is LEGACY-SHAPED. It is mapped down to one of the 5 real wip_column
      values (mapping policy is the Coder's own choice) and ALWAYS carries
      the ``.cp-legacy-label`` AC-RENDER bar wherever it renders. This is
      separate from AC10.1's per-item DEMO marking (source-path-based,
      applies identically to legacy- and new-shaped items, and applies in
      BOTH the legacy default-glob invocation and ``--control-plane`` mode).

CLI surface added to ``main()`` (AC5):
    --control-plane            mode switch
    --root <dir>                REQUIRED whenever --control-plane or --focus
                                is used; the AC8 discovery root, and the dir
                                the ``.control-plane-focus`` pointer lives in
    --focus <product>           atomically writes ``<root>/.control-plane-focus``
                                (tmp-file + os.replace)
    --status / --glob           (pre-existing flags) explicit override; when
                                either is passed in --control-plane mode, it
                                supplies the item set directly and bypasses
                                AC8 discovery (test 27)
    Violation (AC5, round-8 gap): invoking --control-plane without --root,
    or --focus without --root, exits code 2 and writes a usage message to
    stderr THAT CONTAINS THE SUBSTRING "required" (this Test-writer's own
    minimal, checkable wording requirement -- distinguishes the Coder's
    real required-flag validation from argparse's generic "unrecognized
    arguments" error, which a not-yet-implemented ``--control-plane`` flag
    would otherwise also produce with exit code 2, making test 28
    accidentally pass pre-implementation without this extra check). No
    output file is written on this path.

ON-DISK control-plane status.json SHAPE (this Test-writer's own minimal
format choice for control-plane items -- the pre-existing legacy shape
remains valid too and is auto-detected, see Legacy-item detection above):
    {
      "product": "<top-level product name, AC6.4>",
      "items": [
        {
          "claim": "<...>",
          "wip_column": "Doing",
          "requires_cleanup": false,
          "proofs": [ <AC2-shaped dict, minus "stale_or_valid",
                       exactly what build_proof_record_from_snapshot()
                       produces / validate_proof_record() consumes>, ... ]
        }
      ]
    }

===========================================================================
KNOWN COVERAGE LIMIT (flagged per role instructions, not silently
downgraded): AC-RENDER requires each bar be "not inside a collapsed
<details>" and "not display:none/visibility:hidden/zero-size". This suite
verifies the executable proxy -- class-token presence, occurrence COUNTS,
and cross-element TEXT NON-CONTAINMENT (regex-based, matching this
harness's existing test_product_dashboard.py convention) -- but does not
parse computed CSS or DOM nesting. A follow-up DOM-aware or headless-
browser check is the natural next step if stricter visibility verification
is ever required; this is a genuine gap, not a claim of full coverage.
===========================================================================
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HARNESS_DIR, "product_dashboard.py")

if HARNESS_DIR not in sys.path:
    sys.path.insert(0, HARNESS_DIR)

import product_dashboard as pd  # noqa: E402  (the module under extension)

import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# Generic HTML helpers (matches test_product_dashboard.py's convention).
# ---------------------------------------------------------------------------

def _count_class(html, token):
    return len(re.findall(r'class=["\'][^"\']*\b' + re.escape(token) + r'\b', html))


def _has_class(html, token):
    return _count_class(html, token) > 0


def _elements_with_class(html, token):
    """Return the inner text of every element whose class attribute carries
    ``token``, matching the element's own closing tag. Best-effort (assumes
    simple, non-deeply-nested span/div-style markup, matching this repo's
    existing rendering conventions)."""
    pattern = re.compile(
        r"<([a-zA-Z][a-zA-Z0-9]*)\b[^>]*\bclass=[\"'][^\"']*\b"
        + re.escape(token) + r"\b[^\"']*[\"'][^>]*>(.*?)</\1\s*>",
        re.DOTALL,
    )
    return [m.group(2) for m in pattern.finditer(html)]


def _find_class_elements_with_positions(html, token):
    """Like ``_elements_with_class`` but also returns each match's start
    OFFSET in ``html`` and its full opening-tag attribute string -- the
    extra data ``_assert_bar_visible_and_not_collapsed`` needs to check for
    an inline hidden style and for a collapsed <details> ancestor."""
    pattern = re.compile(
        r"<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*\bclass=[\"'][^\"']*\b"
        + re.escape(token) + r"\b[^\"']*[\"'][^>]*)>(.*?)</\1\s*>",
        re.DOTALL,
    )
    return [(m.start(), m.group(2), m.group(3)) for m in pattern.finditer(html)]


def _assert_bar_visible_and_not_collapsed(html, token):
    """Light STRUCTURAL proxy (proportionate, no CSS/DOM engine -- matching
    this harness's existing regex-based rendering-assertion convention) for
    AC-RENDER's (a)/(b) bar: for every element whose class attribute
    carries ``token``, assert it is (a) not nested inside a collapsed
    <details> ancestor, and (b) not carrying an inline
    display:none/visibility:hidden style. Fails loudly if ``token`` is
    absent entirely (a bar that never renders is not "visible")."""
    occurrences = _find_class_elements_with_positions(html, token)
    assert occurrences, "expected at least one element carrying class %r" % token
    for start, attrs, _inner in occurrences:
        style_match = re.search(r'style=["\']([^"\']*)["\']', attrs)
        if style_match:
            style_val = style_match.group(1).replace(" ", "").lower()
            assert "display:none" not in style_val, \
                "%r bar must not be display:none" % token
            assert "visibility:hidden" not in style_val, \
                "%r bar must not be visibility:hidden" % token
        preceding = html[:start]
        open_details = preceding.count("<details")
        close_details = preceding.count("</details")
        assert open_details <= close_details, \
            "%r bar must not be nested inside a collapsed <details> element" % token


def _run_cli(args, cwd=None):
    # Isolation/robustness: 60s timeout so a hung subprocess never hangs the
    # suite (dispatch item 5). No explicit ``env=`` is passed -- Python's
    # subprocess.run() with env=None inherits the CURRENT process
    # environment automatically, which is exactly how the autouse
    # ``_isolated_loop_gate_dir`` fixture below routes every CLI
    # subprocess's LOOP_GATE_DIR to a per-test temp dir (it calls
    # ``monkeypatch.setenv``, which mutates this process's real
    # ``os.environ`` for the duration of the test).
    cmd = [sys.executable, TOOL] + list(args)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                           timeout=60)
    proc.stdout = proc.stdout.decode("utf-8", "replace")
    proc.stderr = proc.stderr.decode("utf-8", "replace")
    return proc


def _git_init(repo_dir):
    os.makedirs(repo_dir, exist_ok=True)
    subprocess.run(["git", "init", "-q", repo_dir], check=True, timeout=30,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return repo_dir


def _write_json(dirpath, data, name="status.json"):
    os.makedirs(dirpath, exist_ok=True)
    p = os.path.join(str(dirpath), name)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return p


# ---------------------------------------------------------------------------
# Proof-record / item fixture builders (AC2 13-field schema / AC6 item schema).
# ---------------------------------------------------------------------------

DEFAULT_HEAD = "a" * 40


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def make_proof_record(**overrides):
    """A complete, self-consistent, FRESH raw AC2 proof record (12 author/
    captured fields; ``stale_or_valid`` intentionally absent -- computed by
    ``validate_proof_record``). Defaults to a genuine, non-demo, non-mock
    ``live_smoke`` claim. Override any field via kwargs."""
    record = {
        "product": "alpha",
        "claim": "does the thing",
        "evidence_label": "live-smoke-pass",
        "proof_class": "live_smoke",
        "command": ["python3", "tools/live_smoke_runner.py"],
        "cwd": "/tmp/alpha",
        "git_sha": DEFAULT_HEAD,
        "exit_code": 0,
        "output_hash": "0" * 64,
        "artifact_hashes": {"artifact.txt": "1" * 64},
        "timestamp": _now_iso(),
        "source_artifact_path": "<HOME>/Claude/loop/runs/2026-07-11_x/status.json",
    }
    record.update(overrides)
    return record


def make_item(**overrides):
    item = {
        "product": "alpha",
        "claim": "does the thing",
        "wip_column": "Doing",
        "requires_cleanup": False,
        "source_path": "<HOME>/Claude/loop/runs/2026-07-11_x/status.json",
    }
    item.update(overrides)
    return item


def _validate(record, **kw):
    """validate_proof_record() with sane self-matching freshness defaults
    (current_head == the record's own git_sha; recompute_artifact_hash ==
    "return the stored value", i.e. a match) -- so a caller only needs to
    override these when the test is SPECIFICALLY about staleness."""
    kw.setdefault("current_head", record.get("git_sha", DEFAULT_HEAD))
    kw.setdefault("recompute_artifact_hash",
                  lambda path: record.get("artifact_hashes", {}).get(path))
    return pd.validate_proof_record(record, **kw)


def _ready_proof_group(product="alpha", claim="does the thing"):
    """A minimal (product, claim) record group that satisfies "ready" when
    requires_cleanup is False and live_repo_health=="CLEAR": a genuine
    live_smoke record + a dashboard_render record."""
    return [
        _validate(make_proof_record(product=product, claim=claim,
                                     proof_class="live_smoke",
                                     evidence_label="live-smoke-pass")),
        _validate(make_proof_record(product=product, claim=claim,
                                     proof_class="dashboard_render",
                                     evidence_label="build-clean")),
    ]


def _cleanup_record(product="alpha", claim="does the thing"):
    return _validate(make_proof_record(product=product, claim=claim,
                                        proof_class="readback_cleanup",
                                        evidence_label="build-clean"))


def _render_cp(items, out_path, focus=None, repo_health_lookup=None):
    """render_control_plane() wrapper that ALWAYS injects a fake
    repo_health_lookup (default CLEAR-everywhere) so this suite never
    touches the real hardening_ledger.json."""
    if repo_health_lookup is None:
        def repo_health_lookup(_product):
            return "CLEAR"
    return pd.render_control_plane(items, str(out_path), focus=focus,
                                    repo_health_lookup=repo_health_lookup)


@pytest.fixture(autouse=True)
def _isolated_loop_gate_dir(monkeypatch, tmp_path):
    """Isolation/robustness (dispatch item 5): route every
    ``run_and_record.py`` proof-snapshot write -- both IN-PROCESS (e.g. test
    25's direct ``run_and_record.run_and_record()`` call) and SUBPROCESS
    (every ``_run_cli`` / ad-hoc ``subprocess.run`` invocation added by this
    suite, none of which pass an explicit ``env=`` and therefore inherit
    the current process environment) -- to a per-test temp dir, never the
    real ``~/.loop-gate``. ``monkeypatch.setenv`` mutates this process's
    real ``os.environ`` for the duration of the test and reverts it
    afterwards, which is exactly the "subprocess env= AND os.environ for
    in-process paths" isolation the dispatch asked for, without needing to
    thread an explicit ``env=`` through every individual call site."""
    gate_dir = os.path.join(str(tmp_path), "isolated-loop-gate")
    monkeypatch.setenv("LOOP_GATE_DIR", gate_dir)
    yield gate_dir


# ===========================================================================
# Test 1 -- AC2/staleness: stale timestamp fails validation.
# ===========================================================================

def test_01_stale_timestamp_fails_validation(tmp_path):  # [BEHAVIORAL]
    stale_record = make_proof_record(timestamp="2000-01-01T00:00:00+00:00")
    validated = pd.validate_proof_record(stale_record, current_head=stale_record["git_sha"])
    assert validated["stale_or_valid"] == "stale"

    fresh_record = make_proof_record(timestamp=_now_iso())
    validated_fresh = pd.validate_proof_record(fresh_record, current_head=fresh_record["git_sha"])
    assert validated_fresh["stale_or_valid"] == "valid"


# ===========================================================================
# Test 2 -- AC2: git_sha != current HEAD fails validation for HEAD-freshness
# labels (live-smoke-pass / ready-derivation).
# ===========================================================================

def test_02_git_sha_mismatch_fails_head_freshness():  # [BEHAVIORAL] [SECURITY-ORACLE]
    stale_head = make_proof_record(git_sha="b" * 40, proof_class="live_smoke",
                                    evidence_label="live-smoke-pass")
    validated = pd.validate_proof_record(stale_head, current_head="a" * 40,
                                          recompute_artifact_hash=lambda p: "1" * 64)
    assert validated["stale_or_valid"] == "stale"

    item = make_item(requires_cleanup=False)
    label = pd.derive_evidence_label(item, [validated], live_repo_health="CLEAR")
    assert label not in ("live-smoke-pass", "ready"), \
        "a stale (wrong-HEAD) live_smoke record must not grant live-smoke-pass/ready"

    fresh_head = make_proof_record(git_sha="a" * 40, proof_class="live_smoke",
                                    evidence_label="live-smoke-pass")
    validated_ok = pd.validate_proof_record(fresh_head, current_head="a" * 40,
                                             recompute_artifact_hash=lambda p: "1" * 64)
    assert validated_ok["stale_or_valid"] == "valid"
    label_ok = pd.derive_evidence_label(item, [validated_ok], live_repo_health="CLEAR")
    assert label_ok == "live-smoke-pass"


# ===========================================================================
# Test 3 -- AC2: artifact_hashes != fresh recomputation fails validation.
# ===========================================================================

def test_03_artifact_hash_mismatch_fails_validation():  # [BEHAVIORAL] [SECURITY-ORACLE]
    record = make_proof_record(artifact_hashes={"f.txt": "deadbeef" * 8})

    def recompute_mismatch(_path):
        return "cafebabe" * 8

    validated = pd.validate_proof_record(record, current_head=record["git_sha"],
                                          recompute_artifact_hash=recompute_mismatch)
    assert validated["stale_or_valid"] == "stale"

    def recompute_match(_path):
        return "deadbeef" * 8

    validated_ok = pd.validate_proof_record(record, current_head=record["git_sha"],
                                             recompute_artifact_hash=recompute_match)
    assert validated_ok["stale_or_valid"] == "valid"


# ===========================================================================
# Test 4 -- AC4: missing required proof_class for claimed evidence_label
# fails validation; a record claiming "ready" is always rejected.
# ===========================================================================

def test_04_missing_required_proof_class_and_ready_claim_rejected():  # [BEHAVIORAL] [SECURITY-ORACLE]
    mismatched = make_proof_record(evidence_label="build-clean", proof_class="unit_or_mock")
    with pytest.raises(pd.InvalidProofRecordError):
        pd.validate_proof_record(mismatched)

    ready_claim = make_proof_record(evidence_label="ready", proof_class="live_smoke")
    with pytest.raises(pd.InvalidProofRecordError):
        pd.validate_proof_record(ready_claim)

    # Even a proof_class that WOULD otherwise be plausible for "ready"
    # (dashboard_render) is still rejected when it claims "ready" itself.
    ready_claim2 = make_proof_record(evidence_label="ready", proof_class="dashboard_render")
    with pytest.raises(pd.InvalidProofRecordError):
        pd.validate_proof_record(ready_claim2)


# ===========================================================================
# Test 5 -- AC4: a /demo/-sourced proof cannot make a REAL product reach
# "ready".
# ===========================================================================

def test_05_demo_sourced_proof_cannot_reach_ready_for_real_product():  # [BEHAVIORAL] [SECURITY-ORACLE]
    item = make_item(requires_cleanup=False)
    demo_live_smoke = _validate(make_proof_record(
        proof_class="live_smoke", evidence_label="live-smoke-pass",
        source_artifact_path="<HOME>/Claude/loop/runs/demo/status.json"))
    render_proof = _validate(make_proof_record(
        proof_class="dashboard_render", evidence_label="build-clean"))

    label = pd.derive_evidence_label(item, [demo_live_smoke, render_proof],
                                      live_repo_health="CLEAR")
    assert label != "ready", "a /demo/-sourced live_smoke proof must not grant ready"

    real_live_smoke = _validate(make_proof_record(
        proof_class="live_smoke", evidence_label="live-smoke-pass",
        source_artifact_path="<HOME>/Claude/loop/runs/2026-07-11_x/status.json"))
    label2 = pd.derive_evidence_label(item, [real_live_smoke, render_proof],
                                       live_repo_health="CLEAR")
    assert label2 == "ready", "sanity: the identical group minus the /demo/ path DOES reach ready"


# ===========================================================================
# Test 6 -- AC4: a mocked live_smoke command/context cannot satisfy
# live-smoke-pass.
# ===========================================================================

def test_06_mocked_live_smoke_cannot_satisfy_live_smoke_pass():  # [BEHAVIORAL] [SECURITY-ORACLE]
    item = make_item(requires_cleanup=False)
    mocked = _validate(make_proof_record(
        proof_class="live_smoke", evidence_label="live-smoke-pass",
        command=["python3", "tools/live_smoke_MOCKED_runner.py"]))
    label = pd.derive_evidence_label(item, [mocked], live_repo_health="CLEAR")
    assert label not in ("live-smoke-pass", "ready"), \
        "a command naming itself mocked must not grant live-smoke-pass/ready"

    real = _validate(make_proof_record(
        proof_class="live_smoke", evidence_label="live-smoke-pass",
        command=["python3", "tools/live_smoke_runner.py"]))
    label2 = pd.derive_evidence_label(item, [real], live_repo_health="CLEAR")
    assert label2 == "live-smoke-pass"


# ===========================================================================
# Test 7 -- prose-only claim with zero backing proof cannot render
# green/ready (the "VERDICT PASS" narrative regression).
# ===========================================================================

def test_07_prose_only_claim_no_backing_proof_cannot_render_verified(tmp_path):  # [BEHAVIORAL] [SECURITY-ORACLE]
    item = make_item(wip_column="Done Verified", requires_cleanup=False)
    item["notes"] = "VERDICT PASS -- fully verified and shipped, ready for release."
    item["proof_records"] = []  # zero machine-checkable evidence

    label = pd.derive_evidence_label(item, [], live_repo_health="CLEAR")
    assert label == "Unverified"

    out = os.path.join(str(tmp_path), "prose_only.html")
    html = _render_cp([item], out)
    assert not _has_class(html, "cp-verified"), \
        "a prose-only claim must never trigger the .cp-verified positive bar"
    assert _has_class(html, "cp-mismatch"), \
        "Done Verified + Unverified derivation is an overstated-doneness mismatch (AC6.3)"


# ===========================================================================
# Test 8 -- two-fixture mechanical non-conflation: wip_column vs derived
# evidence_label render in distinct DOM elements/classes, and neither
# fixture fires .cp-mismatch (Ready/Doing never mismatch).
# ===========================================================================

def test_08_wip_and_evidence_label_never_conflated(tmp_path):  # [BEHAVIORAL]
    item_a = make_item(product="prod-a", claim="claim-a", wip_column="Ready",
                        requires_cleanup=False)
    item_a["proof_records"] = [make_proof_record(product="prod-a", claim="claim-a",
                                                   proof_class="unit_or_mock",
                                                   evidence_label="mock-tested")]

    item_b = make_item(product="prod-b", claim="claim-b", wip_column="Doing",
                        requires_cleanup=False)
    item_b["proof_records"] = [
        make_proof_record(product="prod-b", claim="claim-b", proof_class="live_smoke",
                           evidence_label="live-smoke-pass"),
        make_proof_record(product="prod-b", claim="claim-b", proof_class="dashboard_render",
                           evidence_label="build-clean"),
    ]

    out = os.path.join(str(tmp_path), "nonconflate.html")
    html = _render_cp([item_a, item_b], out)

    assert _has_class(html, "cp-wip")
    assert _has_class(html, "cp-evidence")

    wip_texts = " ".join(_elements_with_class(html, "cp-wip"))
    evidence_texts = " ".join(_elements_with_class(html, "cp-evidence"))

    assert "Ready" in wip_texts and "Doing" in wip_texts
    assert "mock-tested" in evidence_texts and "ready" in evidence_texts

    assert "mock-tested" not in wip_texts, "claimed/derived label string leaked into .cp-wip"
    assert "Ready" not in evidence_texts, "authored wip_column string leaked into .cp-evidence"
    assert "Doing" not in evidence_texts, "authored wip_column string leaked into .cp-evidence"

    assert _count_class(html, "cp-mismatch") == 0, \
        "Ready/Doing must never fire .cp-mismatch regardless of evidence level (AC6.3)"


# ===========================================================================
# Test 9 -- multiple simultaneous Doing products render without error;
# focus pointer highlights only the named product; unset/absent-product
# pointer yields no highlight and no error.
# ===========================================================================

def test_09_multiple_doing_products_and_focus_targeting(tmp_path):  # [BEHAVIORAL]
    item_x = make_item(product="product-x", claim="c", wip_column="Doing",
                        requires_cleanup=False)
    item_x["proof_records"] = []
    item_y = make_item(product="product-y", claim="c", wip_column="Doing",
                        requires_cleanup=False)
    item_y["proof_records"] = []

    out1 = os.path.join(str(tmp_path), "both.html")
    html_both = _render_cp([item_x, item_y], out1, focus=None)
    assert html_both and "<!doctype" in html_both.lower()
    assert _count_class(html_both, "cp-mismatch") == 0

    out2 = os.path.join(str(tmp_path), "x_only_focused.html")
    html_x_focused = _render_cp([item_x], out2, focus="product-x")
    assert _count_class(html_x_focused, "cp-focus") == 1

    out3 = os.path.join(str(tmp_path), "y_not_focused.html")
    html_y_with_x_focus = _render_cp([item_y], out3, focus="product-x")
    assert _count_class(html_y_with_x_focus, "cp-focus") == 0, \
        "a focus pointer naming product-x must not highlight product-y's own card"

    out4 = os.path.join(str(tmp_path), "unset.html")
    html_unset = _render_cp([item_x, item_y], out4, focus=None)
    assert _count_class(html_unset, "cp-focus") == 0

    out5 = os.path.join(str(tmp_path), "absent.html")
    html_absent = _render_cp([item_x, item_y], out5, focus="ghost-product-not-present")
    assert _count_class(html_absent, "cp-focus") == 0


# ===========================================================================
# Test 10 -- AC9: FROZEN repo-health blocks derived "ready" regardless of
# other proofs.
# ===========================================================================

def test_10_frozen_repo_health_blocks_ready_regardless_of_proofs():  # [BEHAVIORAL] [SECURITY-ORACLE]
    item = make_item(requires_cleanup=False)
    proofs = _ready_proof_group()

    label_clear = pd.derive_evidence_label(item, proofs, live_repo_health="CLEAR")
    assert label_clear == "ready"

    label_frozen = pd.derive_evidence_label(item, proofs, live_repo_health="FROZEN")
    assert label_frozen != "ready", \
        "FROZEN repo-health must cap the derivation below ready regardless of proof strength"


# ===========================================================================
# Test 11 -- legacy labels: a PROOF RECORD claiming fixed/verified/claimed
# is rejected (AC4 closed enum); a legacy ITEM-level status is mapped down
# WITH a .cp-legacy-label caveat.
# ===========================================================================

def test_11_legacy_proof_label_rejected_and_legacy_item_mapped_with_caveat(tmp_path):  # [BEHAVIORAL]
    for legacy_label in ("fixed", "verified", "claimed"):
        bad = make_proof_record(evidence_label=legacy_label, proof_class="unit_or_mock")
        with pytest.raises(pd.InvalidProofRecordError):
            pd.validate_proof_record(bad)

    legacy_item = {
        "product": "legacyprod",
        "claim": "old claim",
        "status": "fixed",
        "verified": False,
        "source_path": "<HOME>/Claude/loop/runs/2026-07-11_legacy/status.json",
        "proof_records": [],
        # deliberately NO "wip_column" key -> legacy-shaped
    }
    out = os.path.join(str(tmp_path), "legacy.html")
    html = _render_cp([legacy_item], out)
    assert _has_class(html, "cp-legacy-label"), \
        "a legacy item-level status must carry the .cp-legacy-label AC-RENDER caveat"
    assert any(v in html for v in pd.WIP_COLUMN_ENUM), \
        "the legacy status must be mapped down to one of the 5 real wip_column values"


# ===========================================================================
# Test 12 -- AC6.4: requires_cleanup (ITEM field) gates "ready" on a valid
# readback_cleanup proof; requires_cleanup=false reaches ready without one.
# ===========================================================================

def test_12_requires_cleanup_gates_ready():  # [BEHAVIORAL]
    item_true = make_item(requires_cleanup=True)
    proofs_without_cleanup = _ready_proof_group()
    assert pd.derive_evidence_label(item_true, proofs_without_cleanup,
                                     live_repo_health="CLEAR") != "ready"

    proofs_with_cleanup = proofs_without_cleanup + [_cleanup_record()]
    assert pd.derive_evidence_label(item_true, proofs_with_cleanup,
                                     live_repo_health="CLEAR") == "ready"

    item_false = make_item(requires_cleanup=False)
    assert pd.derive_evidence_label(item_false, proofs_without_cleanup,
                                     live_repo_health="CLEAR") == "ready"


# ===========================================================================
# Test 13 -- AC10.2: in --control-plane mode, a NON-/demo/ item with a
# fabricated evidence.commit (not a real git object) does NOT render as a
# verified/linked badge -- plain, explicitly-unverified text only.
#
# FIXED (dispatch item 4): the original version of this test called
# _git_init() but never configured a github ``origin`` remote, so
# ``_github_repo_base(_origin_url(...))`` returns None regardless of the
# fabricated sha's own validity -- the "not a linked badge" assertion
# passed TRIVIALLY (there was never a github base url to link with in the
# first place). This version wires a REAL github origin (so a link WOULD
# be emitted for a valid, real sha) and adds a positive-control item with a
# REAL commit sha in the same repo, proving the negative assertion below is
# an actual exercise of sha validation, not a no-op.
# ===========================================================================

def test_13_fabricated_commit_not_rendered_as_verified_link_control_plane(tmp_path):  # [BEHAVIORAL] [SECURITY-ORACLE]
    repo_dir = os.path.join(str(tmp_path), "realprod")
    _git_init(repo_dir)
    subprocess.run(["git", "-C", repo_dir, "remote", "add", "origin",
                     "https://github.com/acme/realprod.git"],
                    check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    readme = os.path.join(repo_dir, "README.md")
    with open(readme, "w", encoding="utf-8") as fh:
        fh.write("real\n")
    subprocess.run(["git", "-C", repo_dir, "add", "README.md"], check=True, timeout=30,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", repo_dir, "-c", "user.email=test@example.com",
                     "-c", "user.name=Test", "commit", "-q", "-m", "init"],
                    check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    real_sha = subprocess.run(["git", "-C", repo_dir, "rev-parse", "HEAD"], check=True,
                               timeout=30, stdout=subprocess.PIPE).stdout.decode().strip()

    fabricated_sha = "f" * 40  # a syntactically valid, but genuinely
                                # NON-EXISTENT git object id in THIS repo
                                # (which now has a real origin AND at least
                                # one real commit, so this is a real check).

    status = _write_json(repo_dir, {
        "product": "RealProd",
        "done_sentence": "d",
        "items": [
            {"id": "i1", "title": "Old-style claim", "phase": "built",
             "status": "fixed", "verified": True, "priority": 1,
             "evidence": {"commit": fabricated_sha}},
            {"id": "i2", "title": "Real-commit claim", "phase": "built",
             "status": "fixed", "verified": True, "priority": 2,
             "evidence": {"commit": real_sha}},
        ],
    })
    root = os.path.join(str(tmp_path), "root")
    os.makedirs(root, exist_ok=True)
    out = os.path.join(str(tmp_path), "cp13.html")

    proc = _run_cli(["--control-plane", "--root", root, "--status", status, "--out", out])
    assert proc.returncode == 0, "stderr:\n%s" % proc.stderr
    assert "Traceback" not in proc.stderr

    with open(out, "r", encoding="utf-8") as fh:
        html = fh.read()

    assert fabricated_sha in html, "the fabricated sha must still be shown as plain text"
    assert ("/commit/" + fabricated_sha) not in html, \
        "a fabricated (non-real-git-object) sha must never render as a linked/verified " \
        "commit badge, EVEN THOUGH this repo has a real github origin configured"

    # Positive control: the origin IS wired up, and a REAL commit sha in
    # this same repo DOES render as a linked badge -- this is what proves
    # the negative assertion above is a genuine validation check rather
    # than a no-op (no origin / no real commit to ever link).
    assert ("/commit/" + real_sha) in html, \
        "a real commit sha in a repo with a real github origin must render as a linked " \
        "badge in control-plane mode (positive control proving the origin is wired)"


# ===========================================================================
# Test 14 -- AC6.3 generalized mismatch table, pinned to the exact
# threshold rank (live-smoke-pass, one below ready) so an off-by-one
# comparator is caught.
# ===========================================================================

def test_14_ac63_mismatch_generalized_pinned_to_threshold():  # [BEHAVIORAL] [SECURITY-ORACLE]
    # (a) Done Verified + live-smoke-pass (rank 4, immediately below ready)
    assert pd.wip_mismatch("Done Verified", "live-smoke-pass", "CLEAR") is True
    # (b) same, but repo FROZEN -- independent OR clause fires even for a
    #     hypothetical derived_label=="ready" (defense in depth, AC9).
    assert pd.wip_mismatch("Done Verified", "ready", "FROZEN") is True
    # (c) Blocked External + live-smoke-pass (exactly the threshold)
    assert pd.wip_mismatch("Blocked External", "live-smoke-pass", "CLEAR") is True
    # (d) Evidence Needed + live-smoke-pass
    assert pd.wip_mismatch("Evidence Needed", "live-smoke-pass", "CLEAR") is True
    # Negative controls: Ready/Doing never fire, at any evidence level.
    assert pd.wip_mismatch("Ready", "ready", "CLEAR") is False
    assert pd.wip_mismatch("Doing", "ready", "FROZEN") is False
    assert pd.wip_mismatch("Ready", "Unverified", "FROZEN") is False


# ===========================================================================
# Test 15 -- AC8: a status.json nested 2+ directory levels under
# <root>/runs/ IS discovered by real-mode recursive discovery.
# ===========================================================================

def test_15_recursive_discovery_finds_deeply_nested_status_json(tmp_path):  # [BEHAVIORAL]
    root = os.path.join(str(tmp_path), "root")
    deep_dir = os.path.join(root, "runs", "2026-07-11_somerun", "someproduct")
    _write_json(deep_dir, {
        "product": "someproduct",
        "items": [{"claim": "c1", "wip_column": "Doing", "requires_cleanup": False,
                   "proofs": []}],
    })
    items = pd.discover_control_plane_items(root)
    assert any(it.get("product") == "someproduct" for it in items), \
        "a status.json 2+ levels under <root>/runs/ must be discovered (not a shallow-only glob)"


# ===========================================================================
# Test 16 -- an authored Evidence Needed wip_column and a separately
# derived Unverified evidence_label render as textually distinct labels in
# distinct elements.
# ===========================================================================

def test_16_evidence_needed_wip_and_unverified_derived_render_distinct(tmp_path):  # [BEHAVIORAL]
    item_a = make_item(product="prod-a", wip_column="Evidence Needed", requires_cleanup=False)
    item_a["proof_records"] = [make_proof_record(product="prod-a", proof_class="unit_or_mock",
                                                   evidence_label="mock-tested")]
    item_b = make_item(product="prod-b", wip_column="Doing", requires_cleanup=False)
    item_b["proof_records"] = []  # no proofs -> derived "Unverified"

    out = os.path.join(str(tmp_path), "distinct.html")
    html = _render_cp([item_a, item_b], out)

    assert "Evidence Needed" in html
    assert "Unverified" in html

    wip_texts = " ".join(_elements_with_class(html, "cp-wip"))
    evidence_texts = " ".join(_elements_with_class(html, "cp-evidence"))
    assert "Evidence Needed" in wip_texts
    assert "Evidence Needed" not in evidence_texts
    assert "Unverified" in evidence_texts
    assert "Unverified" not in wip_texts


# ===========================================================================
# Test 17 -- a rejected claim (unsupported label) does not suppress the
# item's independently-derivable lower label.
# ===========================================================================

def test_17_rejected_claim_does_not_suppress_lower_derivable_label():  # [BEHAVIORAL]
    item = make_item(requires_cleanup=False)

    good_record = _validate(make_proof_record(proof_class="unit_or_mock",
                                                evidence_label="mock-tested"))
    bad_raw_record = make_proof_record(proof_class="unit_or_mock",
                                        evidence_label="preflight-pass")  # mismatched -> reject
    with pytest.raises(pd.InvalidProofRecordError):
        pd.validate_proof_record(bad_raw_record)

    # A real pipeline drops the invalid record and keeps only the valid
    # one; the item's independently-derivable "mock-tested" tier must
    # survive that drop.
    label = pd.derive_evidence_label(item, [good_record], live_repo_health="CLEAR")
    assert label == "mock-tested"


# ===========================================================================
# Test 18 -- happy path: Done Verified + derived ready + repo-health CLEAR
# renders .cp-verified and fires NO .cp-mismatch.
# ===========================================================================

def test_18_happy_path_renders_cp_verified_no_mismatch(tmp_path):  # [BEHAVIORAL]
    item = make_item(wip_column="Done Verified", requires_cleanup=False)
    proofs = _ready_proof_group()

    label = pd.derive_evidence_label(item, proofs, live_repo_health="CLEAR")
    assert label == "ready"
    assert pd.wip_mismatch("Done Verified", label, "CLEAR") is False

    item["proof_records"] = [
        make_proof_record(proof_class="live_smoke", evidence_label="live-smoke-pass"),
        make_proof_record(proof_class="dashboard_render", evidence_label="build-clean"),
    ]
    out = os.path.join(str(tmp_path), "happy.html")
    html = _render_cp([item], out, repo_health_lookup=lambda p: "CLEAR")
    assert _has_class(html, "cp-verified")
    assert _count_class(html, "cp-mismatch") == 0


# ===========================================================================
# Test 19 -- demo-mode is per-item by source path, evaluated in BOTH modes:
# the PRE-EXISTING legacy (non--control-plane) invocation must ALSO carry
# .cp-demo for a /demo/-path item, and must NOT regress a real product.
# ===========================================================================

def test_19_demo_marking_per_item_legacy_invocation_no_regression(tmp_path):  # [BEHAVIORAL]
    demo_dir = os.path.join(str(tmp_path), "demo", "widget")
    demo_status = _write_json(demo_dir, {"product": "DemoWidget", "done_sentence": "d",
                                          "items": []})
    real_dir = os.path.join(str(tmp_path), "realprod")
    real_status = _write_json(real_dir, {"product": "RealWidget", "done_sentence": "d",
                                          "items": []})

    out_demo_only = os.path.join(str(tmp_path), "demo_only.html")
    proc_demo = _run_cli(["--status", demo_status, "--out", out_demo_only])
    assert proc_demo.returncode == 0, proc_demo.stderr
    with open(out_demo_only, "r", encoding="utf-8") as fh:
        html_demo_only = fh.read()
    assert _has_class(html_demo_only, "cp-demo"), \
        "the pre-existing legacy invocation must ALSO mark a /demo/-path item (AC10.1)"

    out_real_only = os.path.join(str(tmp_path), "real_only.html")
    proc_real = _run_cli(["--status", real_status, "--out", out_real_only])
    assert proc_real.returncode == 0, proc_real.stderr
    with open(out_real_only, "r", encoding="utf-8") as fh:
        html_real_only = fh.read()
    assert not _has_class(html_real_only, "cp-demo"), \
        "a real, non-/demo/ product must NOT regress to showing a demo badge"

    out_both = os.path.join(str(tmp_path), "both.html")
    proc_both = _run_cli(["--status", demo_status, "--status", real_status, "--out", out_both])
    assert proc_both.returncode == 0, proc_both.stderr
    with open(out_both, "r", encoding="utf-8") as fh:
        html_both = fh.read()
    assert _count_class(html_both, "cp-demo") == 1, \
        "exactly the demo item (not the real one) should carry .cp-demo when rendered together"


# ===========================================================================
# Test 20 -- AC6.3 boundary negative controls, just below the threshold:
# Blocked External / Evidence Needed at preflight-pass (rank 3) do NOT
# fire .cp-mismatch.
# ===========================================================================

def test_20_below_threshold_boundary_no_mismatch():  # [BEHAVIORAL]
    assert pd.wip_mismatch("Blocked External", "preflight-pass", "CLEAR") is False
    assert pd.wip_mismatch("Evidence Needed", "preflight-pass", "CLEAR") is False


# ===========================================================================
# Test 21 -- AC9: two claims of ONE product carry divergent stored
# repo_health snapshots (one CLEAR, one FROZEN), both SHA/timestamp-fresh.
# The single LIVE repo_health_gate.py verdict (here injected as "FROZEN")
# governs uniformly for BOTH claims, regardless of each claim's own stored
# snapshot.
# ===========================================================================

def test_21_live_repo_health_governs_over_divergent_stored_snapshots():  # [BEHAVIORAL] [SECURITY-ORACLE]
    item_a = make_item(product="sharedproduct", claim="claimA",
                        wip_column="Done Verified", requires_cleanup=False)
    item_b = make_item(product="sharedproduct", claim="claimB",
                        wip_column="Done Verified", requires_cleanup=False)

    # Each claim stores its OWN (divergent) repo_health capture-evidence
    # snapshot -- capture evidence only, never gating (AC9).
    stored_clear = _validate(make_proof_record(product="sharedproduct", claim="claimA",
                                                 proof_class="repo_health",
                                                 evidence_label="build-clean"))
    stored_frozen = _validate(make_proof_record(product="sharedproduct", claim="claimB",
                                                  proof_class="repo_health",
                                                  evidence_label="build-clean"))

    live_smoke_a = _validate(make_proof_record(product="sharedproduct", claim="claimA",
                                                 proof_class="live_smoke",
                                                 evidence_label="live-smoke-pass"))
    dash_a = _validate(make_proof_record(product="sharedproduct", claim="claimA",
                                          proof_class="dashboard_render",
                                          evidence_label="build-clean"))
    live_smoke_b = _validate(make_proof_record(product="sharedproduct", claim="claimB",
                                                 proof_class="live_smoke",
                                                 evidence_label="live-smoke-pass"))
    dash_b = _validate(make_proof_record(product="sharedproduct", claim="claimB",
                                          proof_class="dashboard_render",
                                          evidence_label="build-clean"))

    # THE INJECTION POINT: the single live repo_health_gate.py verdict for
    # "sharedproduct" at render/derivation time, resolved ONCE and passed
    # to both claims -- never read from either stored snapshot above.
    live_verdict = "FROZEN"

    label_a = pd.derive_evidence_label(item_a, [stored_clear, live_smoke_a, dash_a],
                                        live_repo_health=live_verdict)
    label_b = pd.derive_evidence_label(item_b, [stored_frozen, live_smoke_b, dash_b],
                                        live_repo_health=live_verdict)

    assert label_a != "ready", "live FROZEN must gate claimA despite its own stored CLEAR snapshot"
    assert label_b != "ready", "live FROZEN must gate claimB (whose own stored snapshot was FROZEN too)"
    assert pd.wip_mismatch("Done Verified", label_a, live_verdict) is True
    assert pd.wip_mismatch("Done Verified", label_b, live_verdict) is True


# ===========================================================================
# Test 22 -- AC3: an unrecognized proof_class is rejected, not coerced.
# ===========================================================================

def test_22_unrecognized_proof_class_rejected():  # [BEHAVIORAL] [SECURITY-ORACLE]
    bad = make_proof_record(proof_class="blocker_scan")  # removed from the enum in V8
    with pytest.raises(pd.InvalidProofRecordError):
        pd.validate_proof_record(bad)

    bad2 = make_proof_record(proof_class="totally_made_up_class")
    with pytest.raises(pd.InvalidProofRecordError):
        pd.validate_proof_record(bad2)


# ===========================================================================
# Test 23 -- AC6.1: an unrecognized wip_column is rejected, not coerced.
# ===========================================================================

def test_23_unrecognized_wip_column_rejected():  # [BEHAVIORAL] [SECURITY-ORACLE]
    bad_item = make_item(wip_column="In Review")
    with pytest.raises(pd.InvalidItemError):
        pd.validate_item(bad_item)


# ===========================================================================
# Test 24 -- AC2: a proof record missing any one of the 13 required fields
# (tested: product, claim, cwd, source_artifact_path) is rejected, not
# accepted with a blank/default.
# ===========================================================================

def test_24_missing_required_ac2_field_rejected():  # [BEHAVIORAL] [SECURITY-ORACLE]
    for field in ("product", "claim", "cwd", "source_artifact_path"):
        record = make_proof_record()
        del record[field]
        with pytest.raises(pd.InvalidProofRecordError):
            pd.validate_proof_record(record)


# ===========================================================================
# Test 25 -- AC1 reuse-boundary oracle: proof-record execution fields equal
# a captured run_and_record() snapshot's own fields; evidence_ledger.
# build_ledger is NEVER invoked on the real-mode status.json read path.
# ===========================================================================

def test_25_execution_fields_match_snapshot_and_no_evidence_ledger_reuse(tmp_path, monkeypatch):  # [BEHAVIORAL]
    import run_and_record

    exit_code, snapshot_record, snapshot_path = run_and_record.run_and_record(
        ["python3", "-c", "print('control-plane-test-25')"]
    )
    assert exit_code == 0
    assert snapshot_record is not None

    proof = pd.build_proof_record_from_snapshot(
        snapshot_record, snapshot_path,
        product="p25", claim="c25", evidence_label="live-smoke-pass",
        proof_class="live_smoke", cwd=os.getcwd(), git_sha="a" * 40,
        source_artifact_path="<HOME>/Claude/loop/runs/2026-07-11_x/status.json",
    )
    assert proof["command"] == snapshot_record["command"]
    assert proof["exit_code"] == snapshot_record["exit_code"]
    assert proof["output_hash"] == snapshot_record["output_sha256"]
    assert proof["artifact_hashes"] == snapshot_record["files"]
    assert proof["timestamp"] == snapshot_record["captured_at"]

    import evidence_ledger
    calls = []

    def _spy_build_ledger(*a, **k):
        calls.append((a, k))
        return []

    monkeypatch.setattr(evidence_ledger, "build_ledger", _spy_build_ledger)

    root = os.path.join(str(tmp_path), "root25")
    deep_dir = os.path.join(root, "runs", "run25", "prod25")
    _write_json(deep_dir, {
        "product": "prod25",
        "items": [{"claim": "c25", "wip_column": "Doing", "requires_cleanup": False,
                   "proofs": []}],
    })
    pd.discover_control_plane_items(root)

    assert calls == [], \
        "evidence_ledger.build_ledger must NEVER be invoked on the control-plane status.json read path"


# ===========================================================================
# Test 26 -- AC5 CLI smoke: --control-plane --root <tmp> --out <tmp.html>
# exits 0 and writes real, non-empty HTML.
# ===========================================================================

def test_26_cli_control_plane_smoke_writes_real_html(tmp_path):  # [BEHAVIORAL]
    root = os.path.join(str(tmp_path), "root26")
    os.makedirs(root, exist_ok=True)
    out = os.path.join(str(tmp_path), "cp26.html")

    proc = _run_cli(["--control-plane", "--root", root, "--out", out])
    assert proc.returncode == 0, "stderr:\n%s" % proc.stderr
    assert "Traceback" not in proc.stderr
    assert os.path.exists(out)

    with open(out, "r", encoding="utf-8") as fh:
        html = fh.read()
    assert "<!doctype html>" in html.lower()
    assert len(html) > 0


# ===========================================================================
# Test 27 -- AC10.1 control-plane demo half: in --control-plane mode, an
# item supplied via an explicit --status/--glob override whose source path
# contains /demo/ renders the .cp-demo bar (proving demo-marking is
# evaluated per-item in control-plane mode too, not only via legacy).
# ===========================================================================

def test_27_control_plane_status_override_demo_item_shows_cp_demo(tmp_path):  # [BEHAVIORAL]
    demo_dir = os.path.join(str(tmp_path), "root27", "demo", "widget")
    status = _write_json(demo_dir, {
        "product": "DemoWidget27",
        "items": [{"claim": "c1", "wip_column": "Doing", "requires_cleanup": False,
                   "proofs": []}],
    })
    root = os.path.join(str(tmp_path), "root27")
    out = os.path.join(str(tmp_path), "cp27.html")

    proc = _run_cli(["--control-plane", "--root", root, "--status", status, "--out", out])
    assert proc.returncode == 0, "stderr:\n%s" % proc.stderr

    with open(out, "r", encoding="utf-8") as fh:
        html = fh.read()
    assert _has_class(html, "cp-demo"), \
        "an explicit --status override into /demo/ must still render .cp-demo in control-plane mode"


# ===========================================================================
# Test 28 -- AC5 required-flag violation: --control-plane without --root
# (and, separately, --focus without --root) exits 2 with a usage message
# on stderr; no dashboard file is produced.
# ===========================================================================

def test_28_missing_root_exits_2_usage_error_no_file_written(tmp_path):  # [BEHAVIORAL]
    out1 = os.path.join(str(tmp_path), "should_not_exist_1.html")
    proc1 = _run_cli(["--control-plane", "--out", out1])
    assert proc1.returncode == 2
    assert proc1.stderr.strip() != ""
    assert "required" in proc1.stderr.lower(), \
        "the usage message must explain --root is required (distinguishes this from a generic argparse error)"
    assert not os.path.exists(out1), "no dashboard file may be produced on the required-flag violation path"

    out2 = os.path.join(str(tmp_path), "should_not_exist_2.html")
    proc2 = _run_cli(["--focus", "someproduct", "--out", out2])
    assert proc2.returncode == 2
    assert proc2.stderr.strip() != ""
    assert "required" in proc2.stderr.lower()
    assert not os.path.exists(out2)


# ===========================================================================
# ===========================================================================
#   ***  PRIMARY CODER-ACCEPTANCE TEST  ***
#
#   Everything above (tests 1-28) is a REGRESSION suite over fixtures /
#   direct function calls -- excellent for pinning exact semantics, but a
#   Coder could satisfy every one of them with an implementation that only
#   ever sees hand-built in-memory dicts and never correctly wires together
#   real disk discovery + a real run_and_record.py snapshot's own fields +
#   a real git repo's real HEAD + a real live repo-health lookup + the real
#   CLI flags, end to end.
#
#   THIS is the test that proves the real pipeline. Nothing here is a
#   fixture or a stub: a real ``git init``+commit, a real artifact file on
#   disk, a real ``run_and_record.py`` subprocess invocation (producing a
#   real proof-snapshot JSON file on disk), the real captured HEAD sha, a
#   real ``status.json`` written to ``<root>/runs/<run>/<product>/
#   status.json``, and a real ``product_dashboard.py --control-plane``
#   subprocess CLI invocation. It must PASS for a genuinely-wired
#   implementation and FAIL for a synthetic/stubbed one -- including
#   DOWNGRADING when the real artifact is mutated out from under a
#   previously-verified item.
# ===========================================================================
# ===========================================================================

def test_PRIMARY_real_pipeline_end_to_end_verified_then_downgrades_on_mutation(tmp_path):  # [BEHAVIORAL]
    # --- Real git repo + real committed artifact -----------------------
    repo_dir = os.path.join(str(tmp_path), "e2e_repo")
    _git_init(repo_dir)

    artifact_path = os.path.join(repo_dir, "artifact.txt")
    with open(artifact_path, "w", encoding="utf-8") as fh:
        fh.write("original content\n")

    subprocess.run(["git", "-C", repo_dir, "add", "artifact.txt"], check=True, timeout=30,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["git", "-C", repo_dir, "-c", "user.email=test@example.com",
                     "-c", "user.name=Test", "commit", "-q", "-m", "add artifact"],
                    check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    head_sha = subprocess.run(["git", "-C", repo_dir, "rev-parse", "HEAD"], check=True,
                               timeout=30, stdout=subprocess.PIPE).stdout.decode().strip()
    assert len(head_sha) == 40, "sanity: a real git commit sha"

    # --- Real run_and_record.py SUBPROCESS invocation against a command
    # that actually reads the real artifact file, so the artifact's own
    # content lands in the snapshot's "files" dict via real hashing. No
    # explicit env= is passed -- the autouse _isolated_loop_gate_dir
    # fixture already routed LOOP_GATE_DIR to a per-test temp dir via
    # os.environ, which this subprocess (env=None) inherits.
    rar_cmd = [sys.executable, os.path.join(HARNESS_DIR, "run_and_record.py"), "--",
               sys.executable, "-c", "import sys; open(sys.argv[1]).read()", artifact_path]
    rar_proc = subprocess.run(rar_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               cwd=repo_dir, timeout=60)
    rar_stdout = rar_proc.stdout.decode("utf-8", "replace")
    assert rar_proc.returncode == 0, "stderr:\n%s" % rar_proc.stderr.decode("utf-8", "replace")

    first_line = rar_stdout.splitlines()[0]
    snapshot_record = json.loads(first_line)
    assert snapshot_record["exit_code"] == 0
    assert artifact_path in snapshot_record["files"], \
        "the real command's own artifact-path argv token must be real-hashed by run_and_record.py"

    m = re.search(r"proof_snapshot:\s*(\S+)", rar_stdout)
    assert m, "run_and_record.py must print the real proof_snapshot path"
    snapshot_path = m.group(1)
    assert os.path.isfile(snapshot_path), \
        "the proof snapshot JSON must really exist on disk at the printed path"
    with open(snapshot_path, "r", encoding="utf-8") as fh:
        on_disk_snapshot = json.load(fh)
    assert on_disk_snapshot["output_sha256"] == snapshot_record["output_sha256"], \
        "the on-disk snapshot file must match the printed record (real, not fabricated)"

    # --- A real status.json, its proof records built FROM this real
    # snapshot's own fields (AC2 origin table), joined by (product, claim),
    # nested 2+ levels under <root>/runs/ (AC8).
    run_dir_name = "2026-07-11_e2e-run"
    status_dir = os.path.join(str(tmp_path), "root", "runs", run_dir_name, "e2e-product")
    status_path = os.path.join(status_dir, "status.json")

    live_smoke_proof = {
        "product": "e2e-product", "claim": "artifact reflects real state",
        "evidence_label": "live-smoke-pass", "proof_class": "live_smoke",
        "command": snapshot_record["command"], "cwd": repo_dir, "git_sha": head_sha,
        "exit_code": snapshot_record["exit_code"], "output_hash": snapshot_record["output_sha256"],
        "artifact_hashes": snapshot_record["files"], "timestamp": snapshot_record["captured_at"],
        "source_artifact_path": status_path,
    }
    dashboard_render_proof = {
        "product": "e2e-product", "claim": "artifact reflects real state",
        "evidence_label": "build-clean", "proof_class": "dashboard_render",
        "command": snapshot_record["command"], "cwd": repo_dir, "git_sha": head_sha,
        "exit_code": snapshot_record["exit_code"], "output_hash": snapshot_record["output_sha256"],
        "artifact_hashes": {}, "timestamp": snapshot_record["captured_at"],
        "source_artifact_path": status_path,
    }

    status_data = {
        "product": "e2e-product",
        "items": [{
            "claim": "artifact reflects real state",
            "wip_column": "Done Verified",
            "requires_cleanup": False,
            "proofs": [live_smoke_proof, dashboard_render_proof],
        }],
    }
    os.makedirs(status_dir, exist_ok=True)
    with open(status_path, "w", encoding="utf-8") as fh:
        json.dump(status_data, fh)

    root = os.path.join(str(tmp_path), "root")
    out = os.path.join(str(tmp_path), "e2e.html")

    # --- Real CLI invocation: python3 product_dashboard.py --control-plane
    # --root <root> --out <out.html>, discovering the real status.json we
    # just wrote (AC8 recursive discovery), with the REAL (default) live
    # repo-health lookup -- "e2e-product" has no hardening_ledger.json
    # entries at all, so the real live repo_health_gate.py verdict for it
    # is genuinely CLEAR (0 open items/classes), no fake lookup needed.
    proc = subprocess.run(
        [sys.executable, TOOL, "--control-plane", "--root", root, "--out", out],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=repo_dir, timeout=60,
    )
    assert proc.returncode == 0, "stderr:\n%s" % proc.stderr.decode("utf-8", "replace")
    assert os.path.isfile(out)
    with open(out, "r", encoding="utf-8") as fh:
        html = fh.read()

    assert _has_class(html, "cp-verified"), \
        "a genuinely-ready item backed by real git/hash/CLI evidence must render .cp-verified"
    assert _count_class(html, "cp-mismatch") == 0, \
        "a genuinely consistent item must not fire .cp-mismatch"
    assert _has_class(html, "cp-wip") and _has_class(html, "cp-evidence")
    wip_texts = " ".join(_elements_with_class(html, "cp-wip"))
    evidence_texts = " ".join(_elements_with_class(html, "cp-evidence"))
    assert "Done Verified" in wip_texts, "the authored wip_column must render correctly"
    assert "ready" in evidence_texts, "the derived evidence_label must render correctly"

    # --- Mutation: change the REAL artifact's real on-disk content, so the
    # stored artifact_hashes no longer matches a fresh recomputation of the
    # real file. Nothing else changes -- same status.json, same recorded
    # git_sha. Re-render via the same real CLI and assert the SAME item
    # DOWNGRADES: it must no longer render .cp-verified, and the downgrade
    # must be visible (either .cp-mismatch fires, or a stale/invalid state
    # is rendered).
    with open(artifact_path, "w", encoding="utf-8") as fh:
        fh.write("MUTATED content -- no longer matches the recorded artifact hash\n")

    out2 = os.path.join(str(tmp_path), "e2e_mutated.html")
    proc2 = subprocess.run(
        [sys.executable, TOOL, "--control-plane", "--root", root, "--out", out2],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=repo_dir, timeout=60,
    )
    assert proc2.returncode == 0, "stderr:\n%s" % proc2.stderr.decode("utf-8", "replace")
    with open(out2, "r", encoding="utf-8") as fh:
        html2 = fh.read()

    assert not _has_class(html2, "cp-verified"), \
        "mutating the REAL artifact so its hash no longer matches must DOWNGRADE the item -- " \
        "it must no longer render .cp-verified"
    assert (_has_class(html2, "cp-mismatch") or "stale" in html2.lower()), \
        "the downgrade must be VISIBLE: either the .cp-mismatch warning fires, or a stale/" \
        "invalid-evidence state is rendered -- a silent downgrade (still looks fine, just no " \
        "green badge) is not acceptable"


# ===========================================================================
# Spec-oracle provenance (dispatch item 2) -- the module docstring's spec
# path is repo-root ``runs/2026-07-11_control-plane-dashboard/specs/
# spec.md``, NOT ``loop-team/runs/...`` (which does not exist on disk).
# ``runs/`` is gitignored, so this is a SKIP-not-FAIL provenance check, not
# a hard dependency of the acceptance suite.
# ===========================================================================

def test_spec_reference_path_correct_and_present():  # [DOC]
    repo_root = os.path.abspath(os.path.join(HARNESS_DIR, "..", ".."))
    spec_path = os.path.join(repo_root, "runs", "2026-07-11_control-plane-dashboard",
                              "specs", "spec.md")
    if not os.path.isfile(spec_path):
        pytest.skip("spec.md not present at the corrected repo-root runs/ path in this "
                    "checkout (runs/ is gitignored) -- provenance check skipped, not failed")
    with open(spec_path, "r", encoding="utf-8") as fh:
        content = fh.read()
    assert "Control-plane dashboard slice" in content, \
        "the file at the corrected path must actually be this slice's spec"


# ===========================================================================
# Negative proof cases (dispatch item 3) -- each its own test, each
# asserting the record/item is rejected OR the derived label downgrades
# (never silently granted a tier it did not earn).
# ===========================================================================

def test_negative_a_nonzero_exit_code_rejected_or_downgrades():  # [BEHAVIORAL] [SECURITY-ORACLE]
    """(3a) A live_smoke proof whose underlying command exited nonzero is
    not genuine passing evidence -- the command itself failed. It must not
    grant live-smoke-pass/ready, whether the Coder implements this as a
    hard validation reject (InvalidProofRecordError) or as a
    derivation-level exclusion (stale_or_valid=="valid" but the ladder
    still refuses to count it)."""
    item = make_item(requires_cleanup=False)
    failing = make_proof_record(proof_class="live_smoke", evidence_label="live-smoke-pass",
                                 exit_code=1)
    try:
        validated = _validate(failing)
    except pd.InvalidProofRecordError:
        return  # a hard reject is an acceptable Coder choice for this case
    label = pd.derive_evidence_label(item, [validated], live_repo_health="CLEAR")
    assert label not in ("live-smoke-pass", "ready"), \
        "a live_smoke proof whose recorded command exited nonzero must not grant " \
        "live-smoke-pass/ready"


def test_negative_b_mismatched_join_key_proof_not_counted():  # [BEHAVIORAL] [SECURITY-ORACLE]
    """(3b) AC6.4: a proof record joins to its item by the pair (product,
    claim). A proof record whose OWN (product, claim) does not match the
    item it is (erroneously) being considered for must never count toward
    that item's derivation -- this is the join-key gate itself, tested
    directly against derive_evidence_label so it cannot be satisfied by
    accident."""
    item = make_item(product="alpha", claim="claim-A", requires_cleanup=False)
    mismatched_claim = _validate(make_proof_record(
        product="alpha", claim="claim-B",  # different claim than the item's own
        proof_class="live_smoke", evidence_label="live-smoke-pass"))
    label = pd.derive_evidence_label(item, [mismatched_claim], live_repo_health="CLEAR")
    assert label not in ("live-smoke-pass", "ready"), \
        "a proof record whose (product, claim) does not match the item's own join key " \
        "must not count toward that item's derived evidence_label"

    mismatched_product = _validate(make_proof_record(
        product="beta", claim="claim-A",  # different product than the item's own
        proof_class="live_smoke", evidence_label="live-smoke-pass"))
    label2 = pd.derive_evidence_label(item, [mismatched_product], live_repo_health="CLEAR")
    assert label2 not in ("live-smoke-pass", "ready"), \
        "a proof record whose product does not match the item's own join key must not count"


def test_negative_c_missing_or_empty_output_hash_rejected():  # [BEHAVIORAL] [SECURITY-ORACLE]
    """(3c) AC2: output_hash is a REQUIRED field (from the snapshot's
    output_sha256) -- missing it is a hard AC2 reject (parallel to test
    24). An empty string is present-but-vacuous: an acceptable Coder
    implementation either hard-rejects it too, or at minimum must never
    let it count as genuine machine-checkable evidence toward
    live-smoke-pass/ready."""
    missing = make_proof_record(proof_class="live_smoke", evidence_label="live-smoke-pass")
    del missing["output_hash"]
    with pytest.raises(pd.InvalidProofRecordError):
        pd.validate_proof_record(missing)

    empty = make_proof_record(proof_class="live_smoke", evidence_label="live-smoke-pass",
                               output_hash="")
    item = make_item(requires_cleanup=False)
    try:
        validated = _validate(empty)
    except pd.InvalidProofRecordError:
        return  # a hard reject of an empty output_hash is an acceptable choice
    label = pd.derive_evidence_label(item, [validated], live_repo_health="CLEAR")
    assert label not in ("live-smoke-pass", "ready"), \
        "an empty output_hash must not be treated as genuine machine-checkable evidence"


def test_negative_d_artifact_hash_references_missing_file_invalid():  # [BEHAVIORAL] [SECURITY-ORACLE]
    """(3d) A proof's artifact_hashes references a path that (per a real
    recompute callable) can no longer be recomputed -- the artifact file is
    missing/unreadable. Recompute impossible must never be treated as
    recompute-matches; the record must come out stale, not valid."""
    record = make_proof_record(artifact_hashes={"/nonexistent/does_not_exist.txt": "a" * 64})

    def recompute_missing(_path):
        return None  # simulates: file does not exist / cannot be re-read

    validated = pd.validate_proof_record(record, current_head=record["git_sha"],
                                          recompute_artifact_hash=recompute_missing)
    assert validated["stale_or_valid"] == "stale", \
        "a recompute callable that cannot recompute a referenced artifact's hash (file " \
        "missing) must mark the record stale, not valid"


def test_negative_e_live_smoke_empty_artifact_hashes_cannot_satisfy_live_smoke_pass():  # [BEHAVIORAL] [SECURITY-ORACLE]
    """(3e) AC4: live-smoke-pass requires "a readback-confirmed artifact
    hash" -- a live_smoke proof with EMPTY artifact_hashes has nothing
    readback-confirmed at all and must not satisfy live-smoke-pass/ready,
    regardless of how clean everything else about the record looks."""
    item = make_item(requires_cleanup=False)
    no_artifact = _validate(make_proof_record(proof_class="live_smoke",
                                               evidence_label="live-smoke-pass",
                                               artifact_hashes={}))
    label = pd.derive_evidence_label(item, [no_artifact], live_repo_health="CLEAR")
    assert label not in ("live-smoke-pass", "ready"), \
        "a live_smoke proof with EMPTY artifact_hashes has no readback-confirmed artifact " \
        "hash and must not satisfy live-smoke-pass (AC4)"


# ===========================================================================
# Visibility structural check (dispatch item 6) -- AC-RENDER's key claim
# bars must render in a non-collapsed, non-display:none element in the
# header/card region. Light structural check (class-token + nesting/style
# proxy), not a full CSS/DOM engine -- proportionate, matching this
# harness's existing regex-based rendering-assertion convention (see the
# module docstring's own "KNOWN COVERAGE LIMIT" note).
# ===========================================================================

def test_29_claim_bars_render_visible_not_collapsed_or_hidden(tmp_path):  # [BEHAVIORAL]
    verified_item = make_item(product="verified-prod", wip_column="Done Verified",
                               requires_cleanup=False)
    verified_item["proof_records"] = [
        make_proof_record(product="verified-prod", proof_class="live_smoke",
                           evidence_label="live-smoke-pass"),
        make_proof_record(product="verified-prod", proof_class="dashboard_render",
                           evidence_label="build-clean"),
    ]

    mismatch_item = make_item(product="mismatch-prod", wip_column="Done Verified",
                               requires_cleanup=False)
    mismatch_item["proof_records"] = []  # derived "Unverified" -> Done Verified mismatch

    demo_item = make_item(product="demo-prod", wip_column="Doing", requires_cleanup=False,
                           source_path="<HOME>/Claude/loop/runs/demo/status.json")
    demo_item["proof_records"] = []

    out = os.path.join(str(tmp_path), "visibility.html")
    html = _render_cp([verified_item, mismatch_item, demo_item], out)

    _assert_bar_visible_and_not_collapsed(html, "cp-verified")
    _assert_bar_visible_and_not_collapsed(html, "cp-mismatch")
    _assert_bar_visible_and_not_collapsed(html, "cp-demo")


# ===========================================================================
# Test 30 -- AC7 (Section-E test item 9, second half): the focus pointer is a
# single central pointer READ BACK when --focus is not passed. Every existing
# focus test (test 9) drives ``render_control_plane(focus=...)`` DIRECTLY and
# so only ever exercises the WRITE side of the argument -- none drives the
# real CLI's write-then-read-back pointer cycle. AC7 requires the pointer be
# "read/written via --focus <product> ... OR read from that pointer if
# --focus is not passed." This test drives the REAL CLI (subprocess against
# product_dashboard.py) end to end:
#   (1) --focus prodX writes <root>/.control-plane-focus == "prodX" and puts
#       .cp-focus on prodX's card;
#   (2) a subsequent invocation with NO --focus must READ BACK that pointer
#       and keep highlighting prodX (this is the assertion the current
#       implementation fails -- it wires focus=args.focus=None and never
#       reads the pointer file back);
#   (3) a pointer naming an ABSENT product yields zero focus, no highlight,
#       and no error (AC7 "zero focus is valid").
# ===========================================================================

def _write_cp_status(dirpath, product, name="status.json"):
    return _write_json(dirpath, {
        "product": product,
        "items": [{"claim": "c", "wip_column": "Doing", "requires_cleanup": False,
                   "proofs": []}],
    }, name=name)


def test_30_cli_focus_pointer_written_then_read_back_ac7(tmp_path):  # [BEHAVIORAL]
    root = os.path.join(str(tmp_path), "root30")
    os.makedirs(root, exist_ok=True)
    # A genuine, non-/demo/ product supplied via the --status override (the
    # same override path test 27 exercises); its top-level "product" name is
    # what the pointer will point at and what .cp-focus keys off.
    status = _write_cp_status(os.path.join(str(tmp_path), "focus-src"), "focusprod")
    pointer = os.path.join(root, ".control-plane-focus")

    # --- Step 1: --focus writes the single pointer file AND highlights. -----
    out1 = os.path.join(str(tmp_path), "cp30_focus.html")
    proc1 = _run_cli(["--control-plane", "--root", root, "--status", status,
                      "--focus", "focusprod", "--out", out1])
    assert proc1.returncode == 0, "stderr:\n%s" % proc1.stderr
    assert "Traceback" not in proc1.stderr
    assert os.path.isfile(pointer), \
        "--focus must write the single <root>/.control-plane-focus pointer file (AC7)"
    with open(pointer, "r", encoding="utf-8") as fh:
        assert fh.read().strip() == "focusprod", \
            "the pointer file must name exactly the one focused product (AC7)"
    with open(out1, "r", encoding="utf-8") as fh:
        html1 = fh.read()
    assert _count_class(html1, "cp-focus") == 1, \
        "the focused product's card must carry exactly one .cp-focus bar (AC7)"

    # --- Step 2 (THE AC7 READ-BACK ASSERTION): re-invoke with NO --focus.
    # The CLI must READ BACK <root>/.control-plane-focus and keep highlighting
    # the pointed-to product. This is what the current implementation fails --
    # it never reads the pointer when --focus is absent, so .cp-focus is 0.
    out2 = os.path.join(str(tmp_path), "cp30_readback.html")
    proc2 = _run_cli(["--control-plane", "--root", root, "--status", status, "--out", out2])
    assert proc2.returncode == 0, "stderr:\n%s" % proc2.stderr
    assert "Traceback" not in proc2.stderr
    with open(out2, "r", encoding="utf-8") as fh:
        html2 = fh.read()
    assert _count_class(html2, "cp-focus") == 1, \
        "with no --focus, the CLI must READ BACK the <root>/.control-plane-focus pointer " \
        "and keep highlighting the pointed-to product (AC7 'read from that pointer if " \
        "--focus is not passed')"

    # --- Step 3 (negative): a pointer naming an ABSENT product must yield NO
    # focus highlight and no error (AC7 'zero focus is valid'). Written via the
    # real --focus CLI path (which accepts any product name -- focus is
    # decoupled from discovery/verification, AC7), then read back.
    ghost_write = os.path.join(str(tmp_path), "cp30_ghost_write.html")
    proc3a = _run_cli(["--control-plane", "--root", root, "--status", status,
                       "--focus", "ghost-absent-product", "--out", ghost_write])
    assert proc3a.returncode == 0, "stderr:\n%s" % proc3a.stderr
    assert "Traceback" not in proc3a.stderr
    with open(pointer, "r", encoding="utf-8") as fh:
        assert fh.read().strip() == "ghost-absent-product", \
            "--focus must overwrite the pointer with the new (even absent) product name"

    out3 = os.path.join(str(tmp_path), "cp30_absent_readback.html")
    proc3 = _run_cli(["--control-plane", "--root", root, "--status", status, "--out", out3])
    assert proc3.returncode == 0, "stderr:\n%s" % proc3.stderr
    assert "Traceback" not in proc3.stderr
    with open(out3, "r", encoding="utf-8") as fh:
        html3 = fh.read()
    assert _count_class(html3, "cp-focus") == 0, \
        "a pointer naming an absent product must yield NO .cp-focus highlight and no error " \
        "(AC7 'zero focus is valid')"


# ===========================================================================
# Test 31 -- AC9 / AC-RENDER fail-SAFE default repo-health lookup: an
# UNDETERMINABLE repo-health (a ledger file that is PRESENT but cannot be
# loaded/parsed) must gate as "FROZEN", never silently degrade to "CLEAR".
#
# This pins the DEFAULT ``pd._default_repo_health_lookup(product)`` helper --
# the real live lookup the CLI/render path uses when no explicit
# ``repo_health_lookup`` is injected (product_dashboard.py line ~846). It
# resolves the live per-product verdict via
# ``repo_health_gate.compute_verdict(load_ledger(_default_ledger_path()), ...)``.
#
# Three sub-cases across the ledger-state space, exercised by monkeypatching
# ``repo_health_gate._default_ledger_path`` (the module-level path helper the
# lazy ``import repo_health_gate as _rhg`` inside the lookup resolves against)
# to point at a temp file THIS test controls -- so the real on-disk
# ``hardening_ledger.json`` is never read:
#   (2) ledger path MISSING (file does not exist)          => "CLEAR"
#       (PRIMARY reliance: a product with no hardening tracked is genuinely
#        CLEAR -- 0 open items/classes -- this must NOT regress to FROZEN).
#   (3) ledger PRESENT + valid + product not in it (empty) => "CLEAR"
#       (compute_verdict already yields CLEAR for a zero-entry repo).
#   (1) ledger PRESENT but CORRUPT / unparseable           => "FROZEN"
#       (THE assertion the current fail-OPEN ``except Exception: return
#        "CLEAR"`` gets WRONG: an undeterminable health silently renders
#        CLEAR, which could let a genuinely-unhealthy product reach
#        .cp-verified. Undeterminable => gate, never grant. AC9/AC-RENDER:
#        no item renders verified without machine-checkable proof; a health
#        signal that cannot be computed is NOT such proof.)
#   (4) ledger PRESENT but INVALID UTF-8 BYTES              => "FROZEN"
#       (a residual robustness gap (1) does NOT cover: ``load_ledger`` does
#        ``open(path, encoding="utf-8").read()`` BEFORE any json.loads, so
#        undecodable bytes raise ``UnicodeDecodeError`` -- a ``ValueError``
#        subclass, NOT an ``OSError`` and NOT a ``LedgerError`` -- which the
#        lookup's current ``except (LedgerError, OSError)`` does not catch,
#        so it PROPAGATES and crashes the dashboard instead of gating this
#        product FROZEN. Same undeterminable => fail-SAFE direction as (1).)
#
# Sub-cases (2) and (3) are asserted FIRST (they already pass -- regression
# guards preserving PRIMARY / the existing CLEAR path); sub-cases (1) and (4)
# are asserted LAST so the failure surfaced against the current implementation
# is exactly "undeterminable ledger => expected FROZEN, got CLEAR (or crash)".
# ===========================================================================

def test_31_undeterminable_repo_health_fails_safe_to_frozen(tmp_path, monkeypatch):  # [BEHAVIORAL] [SECURITY-ORACLE]
    import repo_health_gate as rhg

    def _point_ledger_at(path):
        # The lookup does ``import repo_health_gate as _rhg`` then calls
        # ``_rhg._default_ledger_path()`` -- the module object is the same
        # singleton this test imported, so patching it here redirects the
        # real helper without touching the on-disk hardening_ledger.json.
        monkeypatch.setattr(rhg, "_default_ledger_path", lambda: str(path))

    # --- Sub-case (2): MISSING ledger file => CLEAR (PRIMARY reliance). ------
    missing_path = os.path.join(str(tmp_path), "does_not_exist_ledger.json")
    assert not os.path.exists(missing_path)
    _point_ledger_at(missing_path)
    assert pd._default_repo_health_lookup("someproduct") == "CLEAR", \
        "a MISSING ledger (no hardening tracked) must resolve CLEAR -- PRIMARY " \
        "relies on a product with no ledger entry being genuinely CLEAR"

    # --- Sub-case (3): PRESENT + valid + product absent (empty) => CLEAR. ----
    empty_path = os.path.join(str(tmp_path), "empty_valid_ledger.json")
    with open(empty_path, "w", encoding="utf-8") as fh:
        json.dump([], fh)  # a valid, empty ledger array -- loads cleanly
    _point_ledger_at(empty_path)
    assert pd._default_repo_health_lookup("someproduct") == "CLEAR", \
        "a valid ledger with no entry for the queried product must resolve " \
        "CLEAR (compute_verdict yields CLEAR for a zero-open-item repo)"

    # --- Sub-case (1): PRESENT but CORRUPT/unparseable => FROZEN (fail-safe).
    # THIS is the assertion the current ``except Exception: return "CLEAR"``
    # fails: it swallows the parse error and silently returns CLEAR.
    corrupt_path = os.path.join(str(tmp_path), "corrupt_ledger.json")
    with open(corrupt_path, "w", encoding="utf-8") as fh:
        fh.write("{ this is not valid json ]]] :::")  # present, but unparseable
    _point_ledger_at(corrupt_path)
    assert pd._default_repo_health_lookup("someproduct") == "FROZEN", \
        "an UNDETERMINABLE repo-health (a present-but-corrupt ledger that " \
        "fails to load/parse) must fail SAFE to FROZEN and gate rendering -- " \
        "it must NOT silently degrade to CLEAR and risk a genuinely-unhealthy " \
        "product rendering .cp-verified (AC9 / AC-RENDER)"

    # --- Sub-case (4): PRESENT but INVALID UTF-8 BYTES => FROZEN (fail-safe).
    # A residual robustness gap the JSON-corrupt case (1) does NOT cover:
    # ``load_ledger`` opens the file with ``encoding="utf-8"`` and calls
    # ``f.read()`` BEFORE any ``json.loads`` -- so a file of undecodable bytes
    # raises ``UnicodeDecodeError`` (a ``ValueError`` subclass, NOT an
    # ``OSError`` and NOT a ``LedgerError``) at read time. The lookup's current
    # ``except (LedgerError, OSError)`` clause does not catch it, so it
    # PROPAGATES and crashes the whole dashboard instead of gating this one
    # product FROZEN. A present-but-unreadable-bytes ledger is just as
    # undeterminable as a corrupt-JSON one and must fail SAFE the same way.
    bad_bytes_path = os.path.join(str(tmp_path), "invalid_utf8_ledger.json")
    with open(bad_bytes_path, "wb") as fh:
        fh.write(b"\xff\xfe\x00\x01 not valid utf-8 \xff")  # present, undecodable
    _point_ledger_at(bad_bytes_path)
    assert pd._default_repo_health_lookup("someproduct") == "FROZEN", \
        "a present-but-UNREADABLE-BYTES ledger (invalid UTF-8, raising " \
        "UnicodeDecodeError at read time -- a ValueError, not an OSError or " \
        "LedgerError) is an undeterminable repo-health and must fail SAFE to " \
        "FROZEN. It must NOT propagate/crash the dashboard, and must NOT " \
        "silently degrade to CLEAR (AC9 / AC-RENDER)"


# ===========================================================================
# ===========================================================================
#   NEW COVERAGE -- Round-4 UI/UX REDESIGN spec (AC2 through AC12, spec:
#   runs/2026-07-12_control-plane-dashboard-redesign/spec.md). Written BEFORE
#   any redesign implementation exists (Tier-1 test-writer convention, same
#   as the rest of this file): every test below is expected to FAIL until
#   the Coder implements the redesign. Tests 1-31 and _PRIMARY/negative-case/
#   spec-reference tests above are the pre-existing AC1 regression backstop
#   and are UNTOUCHED by this addition.
#
#   NEW class-name contract this Test-writer is introducing for the
#   redesign's new elements (the spec fixes behavior/semantics, not exact
#   class names -- these are this suite's own naming choice, exactly as the
#   ORIGINAL interface contract at the top of this file already did for
#   .cp-wip/.cp-evidence; the Coder must use these exact tokens so this
#   suite remains the oracle):
#     .cp-focus-banner    -- AC2's wrapping banner section: one or more
#                            focus-matching items relocate here, positioned
#                            before the grid; never ALSO duplicated inside
#                            the grid.
#     .cp-evidence-trail  -- AC6's collapsed <details> evidence trail (this
#                            EXACT class name + <details>/<summary> tag pair
#                            is given directly by the spec's own AC6 text,
#                            not invented here).
#     .cp-summary-line    -- AC6/AC7's always-visible one-line verification
#                            summary, rendered OUTSIDE and ahead of the
#                            <details> trail; carries AC7's elapsed-time text
#                            (e.g. "2h ago") or the literal "age unknown"
#                            fallback.
#     .cp-all-clear       -- AC9(b)'s new calm affirmative one-line summary,
#                            rendered when >=1 item renders, no focus is
#                            active, and zero items carry .cp-mismatch.
#
#   AC11's scope lock is verified MECHANICALLY below (not only by manual
#   diff review) via a sha256 hash of each locked function's own
#   inspect.getsource() text, captured directly from the UNMODIFIED
#   pre-redesign product_dashboard.py before this build began.
# ===========================================================================
# ===========================================================================


# ---------------------------------------------------------------------------
# Helpers for the NEW AC2-AC12 tests only (existing _has_class/_count_class/
# _elements_with_class/_assert_bar_visible_and_not_collapsed above are reused
# unchanged wherever they suffice; these are ADDITIONAL, narrowly-scoped
# helpers for checks those regexes genuinely cannot express -- real ancestor/
# nesting queries (AC4) and CSS rule-body color extraction (AC8)).
# ---------------------------------------------------------------------------

from html.parser import HTMLParser  # noqa: E402  (stdlib only, new AC4 helper)


class _DomNode(object):
    __slots__ = ("tag", "classes", "parent")

    def __init__(self, tag, classes, parent):
        self.tag = tag
        self.classes = classes
        self.parent = parent


class _MinimalDomTreeBuilder(HTMLParser):
    """A small, stdlib-only, best-effort HTML tree builder used ONLY by the
    new AC4 structural-nesting assertion below -- the existing
    _has_class/_count_class/_elements_with_class helpers are deliberately
    non-nesting-aware regexes (documented in this module's own "KNOWN
    COVERAGE LIMIT" note above) and cannot answer an "ancestor element"
    question. This parser is intentionally minimal: it tracks an open-tag
    stack and records each element's tag/classes/parent-index -- enough for
    a real "what directly contains this" query, nothing more. Malformed/
    unbalanced markup degrades gracefully (best-effort pop-to-match on an
    unmatched end tag), never raises."""

    VOID_TAGS = frozenset({"br", "hr", "img", "meta", "input", "link"})

    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.nodes = []
        self._stack = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        classes = frozenset((attr_map.get("class") or "").split())
        parent = self._stack[-1] if self._stack else None
        self.nodes.append(_DomNode(tag, classes, parent))
        if tag not in self.VOID_TAGS:
            self._stack.append(len(self.nodes) - 1)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)  # self-closing -- record, never push

    def handle_endtag(self, tag):
        for i in range(len(self._stack) - 1, -1, -1):
            if self.nodes[self._stack[i]].tag == tag:
                del self._stack[i:]
                return


def _dom_nodes(html_text):
    builder = _MinimalDomTreeBuilder()
    builder.feed(html_text)
    return builder.nodes


def _first_parent_index_for_class(nodes, token):
    """The NODE INDEX of the immediate parent of the FIRST node (in document
    order) carrying class ``token`` -- None if not found, or if that node
    has no parent."""
    for node in nodes:
        if token in node.classes:
            return node.parent
    return None


def _iso_hours_ago(hours):
    """A deterministic ISO-8601 UTC timestamp ``hours`` in the past -- built
    from only ``datetime``/``timezone`` (already imported at the top of this
    file) so no new import is needed for the AC7 elapsed-time fixtures."""
    ts = datetime.now(timezone.utc).timestamp() - hours * 3600
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


_GLYPH_TOKEN_RE = re.compile(r"&#?[a-zA-Z0-9]+;|[^\x00-\x7F]+")
_PLAIN_TEXT_ENTITIES = frozenset({
    "&mdash;", "&ndash;", "&amp;", "&nbsp;", "&lt;", "&gt;", "&quot;", "&#39;",
})


def _glyph_tokens(text):
    """Extract the 'glyph' tokens from an element's captured inner text: any
    run of non-ASCII characters (a literal unicode symbol/emoji), or any
    HTML character-reference entity OTHER than the small set of plain-
    punctuation entities this harness's OWN pre-existing markup already uses
    (e.g. ``&mdash;`` in cp-legacy-label's existing "legacy status mapped
    down &mdash; unproven" text) -- so a plain em-dash is never mistaken for
    the "distinct glyph" AC5 requires, but a genuine ``&check;``/``&#10003;``/
    a literal '✓'/'⚠' character IS recognized as one. Returns a list (order
    preserved, duplicates preserved) so callers can both check presence
    (``bool(...)``) and compare distinct-glyph SETS across elements."""
    tokens = []
    for m in _GLYPH_TOKEN_RE.finditer(text):
        token = m.group(0)
        if token.startswith("&") and token in _PLAIN_TEXT_ENTITIES:
            continue
        tokens.append(token)
    return tokens


def _has_extra_glyph(text):
    return bool(_glyph_tokens(text))


_HEX_COLOR_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")


def _hex_to_rgb(hexstr):
    if len(hexstr) == 3:
        hexstr = "".join(ch * 2 for ch in hexstr)
    return tuple(int(hexstr[i:i + 2], 16) for i in (0, 2, 4))


def _css_rule_bodies_for_selector_token(css_text, token):
    """Return the list of ``{...}`` rule BODIES (raw text) from a CSS blob
    whose SELECTOR (the text before the ``{``) contains ``token`` as a
    substring -- a light, regex-based CSS rule scan (this harness's existing
    convention is regex-based markup assertions, not a full parser; a real
    CSS parser is unnecessary for the deterministic color-value check AC8
    needs). Handles comma-separated / compound (e.g. ``.cp-bar.cp-verified``)
    selectors."""
    bodies = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css_text):
        selector, body = m.group(1), m.group(2)
        if token in selector:
            bodies.append(body)
    return bodies


def _first_declared_color_rgb(css_text, token, prop="color"):
    """The first ``prop:`` hex color value (as an (r,g,b) tuple) declared in
    ANY rule whose selector mentions ``token``; falls back to ANY hex color
    in such a rule body if no ``prop:``-prefixed one is found (some Coder
    layouts might declare the state color via border-color/background
    instead of a plain ``color:``); returns None if ``token`` never appears
    in the CSS at all, or no hex color can be found for it."""
    bodies = _css_rule_bodies_for_selector_token(css_text, token)
    if not bodies:
        return None
    prop_re = re.compile(re.escape(prop) + r"\s*:\s*(#[0-9a-fA-F]{3,6})")
    for body in bodies:
        m = prop_re.search(body)
        if m:
            return _hex_to_rgb(m.group(1).lstrip("#"))
    for body in bodies:
        m = _HEX_COLOR_RE.search(body)
        if m:
            return _hex_to_rgb(m.group(1))
    return None


def _rgb_distance(rgb_a, rgb_b):
    return sum((a - b) ** 2 for a, b in zip(rgb_a, rgb_b)) ** 0.5


_STYLE_BLOCK_RE = re.compile(r"<style>.*?</style>", re.DOTALL)


def _strip_style_block(html_text):
    """Normalize a rendered page by blanking out the <style>...</style>
    block's CONTENTS -- this build's own spec explicitly SANCTIONS additive
    growth of the shared STYLE constant (new cp-* selectors: "STYLE ...
    global CSS block, shared; add cp-* selectors, do not remove/alter
    existing non-cp- selectors"), so a literal byte-for-byte comparison of
    the WHOLE page would spuriously fail on that permitted growth alone.
    AC10's actual guarantee is narrower -- the legacy build() call site gets
    NO new markup/behavior (no refresh meta, no structural change) -- this
    normalized comparison isolates exactly that."""
    return _STYLE_BLOCK_RE.sub("<style>STYLE-OMITTED</style>", html_text)


# Captured directly from running the UNMODIFIED pre-redesign
# product_dashboard.py's build() against this exact fixture, BEFORE this
# build began (2026-07-12, this Test-writer dispatch) -- the concrete
# "pre-redesign baseline render" AC10 asks a Test-writer to diff against.
_AC10_LEGACY_BASELINE_NORMALIZED_HTML = (
    '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '<title>Product Dashboard</title>\n<style>STYLE-OMITTED</style></head>\n'
    '<body><div class="wrap">\n<header><h1>Product Dashboard</h1>'
    '<div class="sub">Where am I &middot; is it really fixed? '
    '(green = ground-truth check passed; amber = agent said fixed, unconfirmed)</div>'
    '</header>\n'
    "<div class='grid'><div class='product-card'><div class='card-head'>"
    "<h2 class='product-name'>LegacyRegProd</h2><div class='goal'>goal.</div>"
    "<div class='updated'>updated: 2026-01-01</div><div class='rollup'>"
    "<span class='rollup-chip'>verified: 1</span></div></div>"
    "<div class='items'><div class='item'><span class='badge verified'>VERIFIED</span>"
    "<span class='item-title'>t1</span><span class='item-prio'>p1</span></div></div>"
    "</div></div>\n<footer>Self-contained &middot; stdlib-only generator</footer>\n"
    "</div></body></html>\n"
)


# AC11 scope lock, verified MECHANICALLY: sha256 of each locked function's
# OWN inspect.getsource() text, captured from this same product_dashboard.py
# BEFORE this redesign build began (2026-07-12). Only the functions AC11's
# own sentence names BY NAME are locked here -- render_control_plane /
# _render_cp_card / render_html / STYLE, and any new small private helper,
# are the deliberate, explicitly-permitted edit targets and are NOT included.
_AC11_LOCKED_FUNCTION_HASHES = {
    "discover_control_plane_items":
        "4f43d98c2145423e084109a130a184ab2d31609c561fb0870d0f551bf2d89484",
    "validate_proof_record":
        "cd78c4aded54d3b8917888e835786a2501fe5a5c277610b32213229128b5450b",
    "derive_evidence_label":
        "ea5d5eafe9c5f1503bad60abb703f3043e4a79554a957faa421967498bcf7f97",
    "wip_mismatch":
        "d7dec9791f3a670e896c09bb204ed3b4a43930bccffd98f64f2514b97500a45c",
    "_cli_repo_health_lookup":
        "9cea1780e29e576a171b984cec510fe3f6dfcc79708bc6a8f7992f9efe615dad",
    "_cli_current_head_lookup":
        "cf6a6b5c0311c29e9b96ab9053450dbda75fb2946a392a73f916f4517e9d17c9",
    "_cli_recompute_artifact_hash":
        "c1d442e83d6b2dded5496352279ad0640750f2298a37d53507deeca0976a6e8d",
    "_render_item":
        "0776c87dda996e99d3fcc7ad3b171c0ef597e2dec27a662c0e89593b2abb91b2",
    "_render_product_card":
        "5a3a5fb7e6fb28c9bb471fd0370f5ab4fb8ec3163c2c134d72b3a2bd7d92ee7d",
    "build":
        "7dd58bcfc29db3bb1724fa607fae25f7929dc30cc7a57c0ced1a08a1bbca41d7",
}


# ===========================================================================
# AC2 -- Single focus banner: relocation, not duplication.
# ===========================================================================

def test_ac2_focus_items_relocate_into_single_banner_without_duplication(tmp_path):  # [BEHAVIORAL]
    """AC2: one or more items sharing product==focus render inside ONE
    .cp-focus-banner wrapping section, positioned before the grid content --
    a RELOCATION of the existing per-item .cp-focus marking, never a
    duplication. Baseline (captured by reading the CURRENT, pre-redesign
    render_control_plane/_render_cp_card: no sorting/grouping of any kind is
    ever applied to ``items`` -- each item independently earns its own
    .cp-focus bar via ``if focus is not None and product == focus``): TWO
    items sharing the focused product must contribute exactly TWO .cp-focus
    occurrences pre- AND post-redesign -- the redesign only moves WHERE that
    (unchanged-count) markup lives, never adds/removes an occurrence."""
    item1 = make_item(product="focusprod", claim="claim-one", wip_column="Doing",
                       requires_cleanup=False)
    item1["proof_records"] = []
    item2 = make_item(product="focusprod", claim="claim-two", wip_column="Doing",
                       requires_cleanup=False)
    item2["proof_records"] = []
    other = make_item(product="other-prod", claim="c-other", wip_column="Doing",
                       requires_cleanup=False)
    other["proof_records"] = []

    out = os.path.join(str(tmp_path), "banner.html")
    html = _render_cp([item1, item2, other], out, focus="focusprod")

    assert _has_class(html, "cp-focus-banner"), \
        "one or more focused items must render inside a .cp-focus-banner wrapping section"
    assert _count_class(html, "cp-focus") == 2, \
        "exactly one .cp-focus bar per matching item (2 items share the focused product) -- " \
        "identical total count to the pre-redesign per-item marking logic; relocation, not " \
        "duplication or suppression"

    # Each focused item's own claim text must appear EXACTLY ONCE in the
    # whole page -- proving its card was MOVED into the banner, not also
    # left behind (duplicated) in the grid.
    assert html.count("claim-one") == 1
    assert html.count("claim-two") == 1

    # The banner must be positioned BEFORE the ordinary (non-focused) grid
    # content -- checked against a marker that can ONLY ever appear in the
    # ordinary grid (the unfocused item's own claim text).
    banner_pos = html.find("cp-focus-banner")
    other_item_pos = html.find("c-other")
    assert banner_pos != -1 and other_item_pos != -1
    assert banner_pos < other_item_pos, \
        "the .cp-focus-banner section must be positioned in the DOM before the ordinary " \
        "(non-focused) grid items"


def test_ac2_no_banner_when_focus_unset_or_matches_no_item(tmp_path):  # [BEHAVIORAL]
    """AC2: when no focus is set, or focus matches no item, no banner
    section renders -- grid-only, matching current no-focus behavior
    exactly (zero .cp-focus, zero .cp-focus-banner)."""
    item = make_item(product="plain-a", wip_column="Doing", requires_cleanup=False)
    item["proof_records"] = []

    out_none = os.path.join(str(tmp_path), "no_focus.html")
    html_none = _render_cp([item], out_none, focus=None)
    assert not _has_class(html_none, "cp-focus-banner")
    assert _count_class(html_none, "cp-focus") == 0

    out_ghost = os.path.join(str(tmp_path), "ghost_focus.html")
    html_ghost = _render_cp([item], out_ghost, focus="ghost-product-not-present")
    assert not _has_class(html_ghost, "cp-focus-banner")
    assert _count_class(html_ghost, "cp-focus") == 0


# ===========================================================================
# AC3 -- Three-tier visual weight is CSS-only: DOM emission order of
# non-focused grid items must never reorder.
# ===========================================================================

def test_ac3_grid_item_order_preserved_no_reorder_regression(tmp_path):  # [BEHAVIORAL]
    """AC3: the DOM emission order of non-focused items in the grid must
    remain byte-identical to current (pre-redesign) output -- a
    styling-only visual-weight change, never a reorder. Baseline captured by
    READING the current render_control_plane (product_dashboard.py: no
    sorting/grouping is applied anywhere over ``items`` -- cards are built
    via a plain list comprehension over ``items`` in the EXACT order given),
    so the correct pre-redesign order for ANY fixture is simply the input
    list order itself -- this is the concrete "pre-redesign baseline
    render" the spec asks to diff against, expressed here as a literal
    expected-order assertion rather than a separately-stored snapshot
    file."""
    item_mismatch = make_item(product="zzz-mismatch-prod", wip_column="Done Verified",
                               requires_cleanup=False)
    item_mismatch["proof_records"] = []  # Unverified -> Done Verified mismatch

    item_verified = make_item(product="aaa-verified-prod", wip_column="Done Verified",
                               requires_cleanup=False)
    item_verified["proof_records"] = [
        make_proof_record(product="aaa-verified-prod", proof_class="live_smoke",
                           evidence_label="live-smoke-pass"),
        make_proof_record(product="aaa-verified-prod", proof_class="dashboard_render",
                           evidence_label="build-clean"),
    ]

    item_plain = make_item(product="mmm-plain-prod", wip_column="Doing",
                            requires_cleanup=False)
    item_plain["proof_records"] = []

    # Deliberately NOT alphabetical / NOT sorted by state -- product names
    # are chosen so an accidental alphabetic-sort or state-grouping defect
    # would be visible too.
    fixture_order = [item_mismatch, item_verified, item_plain]
    expected_products = ["zzz-mismatch-prod", "aaa-verified-prod", "mmm-plain-prod"]

    out = os.path.join(str(tmp_path), "order.html")
    html = _render_cp(fixture_order, out, focus=None)

    rendered_products = _elements_with_class(html, "cp-product")
    assert rendered_products == expected_products, \
        "AC3's visual-weight styling must be CSS-only -- item DOM emission order must stay " \
        "exactly input order, matching the current no-sort/no-group pre-redesign baseline"


# ===========================================================================
# AC4 -- One card, one concept: distinct block-level structural containers.
# ===========================================================================

def test_ac4_product_axes_and_bars_render_in_distinct_block_containers(tmp_path):  # [BEHAVIORAL]
    """AC4: product+claim, the wip/evidence axis pair, and the AC-RENDER
    bars must render with "clear structural separation (distinct
    block-level containers, not one run-on inline sentence)" -- i.e. they
    are no longer all flattened as direct siblings of the SAME single
    wrapping element the way the pre-redesign ``.cp-head`` div holds
    EVERYTHING today (product_dashboard.py's current _render_cp_card:
    .cp-product, .cp-claim, every bar span, and .cp-axes are all direct
    children of one ``<div class='cp-head'>``). This test builds a real DOM
    (stdlib html.parser, see _dom_nodes above -- the existing regex helpers
    cannot answer an ancestor question) and asserts the immediate parent of
    .cp-product differs from the immediate parent of .cp-wip, which in turn
    differs from the immediate parent of .cp-mismatch -- distinct
    containers per concept group, not one flat parent for all of them --
    and that none of those containers is a bare inline <span>."""
    item = make_item(product="structprod", wip_column="Done Verified",
                      requires_cleanup=False)
    item["proof_records"] = []  # Unverified -> Done Verified mismatch (guarantees a bar)

    out = os.path.join(str(tmp_path), "struct.html")
    html = _render_cp([item], out)
    assert _has_class(html, "cp-mismatch"), "sanity: fixture must trigger a bar to test"

    nodes = _dom_nodes(html)
    product_parent = _first_parent_index_for_class(nodes, "cp-product")
    wip_parent = _first_parent_index_for_class(nodes, "cp-wip")
    bar_parent = _first_parent_index_for_class(nodes, "cp-mismatch")

    assert product_parent is not None and wip_parent is not None and bar_parent is not None, \
        "cp-product/cp-wip/cp-mismatch must each render inside SOME parent element"
    assert product_parent != wip_parent, \
        "product+claim and the wip/evidence axis pair must render in DISTINCT block " \
        "containers, not as siblings of the exact same wrapping element (AC4)"
    assert wip_parent != bar_parent, \
        "the wip/evidence axis pair and the AC-RENDER bars must render in DISTINCT block " \
        "containers (AC4)"
    assert product_parent != bar_parent, \
        "product+claim and the AC-RENDER bars must render in DISTINCT block containers (AC4)"

    for parent_idx, label in ((product_parent, "product+claim"), (wip_parent, "axis pair"),
                               (bar_parent, "bars")):
        parent_tag = nodes[parent_idx].tag
        assert parent_tag != "span", \
            ("the %s group's wrapping container must be block-level, not a bare inline "
             "<span> (AC4 'not one run-on inline sentence')" % label)


def test_ac4_commit_row_renders_in_distinct_block_container(tmp_path):  # [BEHAVIORAL]
    """AC4 (commit-row half): a legacy item's .cp-commit-row must render in
    its own distinct block container too, separate from product+claim --
    completing AC4's 4-region separation (product+claim / axis pair / bars /
    commit row) alongside the product+claim vs. axis-pair vs. bars check
    above."""
    legacy_item = {
        "product": "commitprod",
        "claim": "old claim",
        "status": "fixed",
        "verified": True,
        "phase": "built",
        "source_path": "<HOME>/Claude/loop/runs/2026-07-11_legacy2/status.json",
        "proof_records": [],
        "evidence": {"commit": "deadbeef" * 5},
        # deliberately NO "wip_column" -> legacy-shaped, carries evidence.commit
        # -> renders .cp-commit-row.
    }
    out = os.path.join(str(tmp_path), "commitrow.html")
    html = _render_cp([legacy_item], out)
    assert _has_class(html, "cp-commit-row"), "sanity: fixture must render a commit row"

    nodes = _dom_nodes(html)
    product_parent = _first_parent_index_for_class(nodes, "cp-product")
    commit_parent = _first_parent_index_for_class(nodes, "cp-commit-row")
    assert product_parent is not None and commit_parent is not None
    assert product_parent != commit_parent, \
        "the commit row must render in its own distinct block container, separate from " \
        "product+claim (AC4)"


# ===========================================================================
# AC5 -- Redundant status encoding: a text label PLUS a distinct glyph,
# never color alone.
# ===========================================================================

def test_ac5_verified_and_mismatch_bars_carry_a_distinct_glyph_not_color_alone(tmp_path):  # [BEHAVIORAL]
    """AC5: cp-verified -> a check glyph, cp-mismatch -> a warning glyph,
    rendered in the markup TEXT itself (not CSS ::before alone) -- so status
    is never distinguishable by color alone. Verified via
    _elements_with_class's captured INNER TEXT, which can only ever contain
    markup-emitted text, never CSS-pseudo-element-injected content -- a CSS
    ::before glyph would be invisible to this extraction, which is exactly
    the failure mode AC5 requires this test to catch."""
    verified_item = make_item(product="glow-verified", wip_column="Done Verified",
                               requires_cleanup=False)
    verified_item["proof_records"] = [
        make_proof_record(product="glow-verified", proof_class="live_smoke",
                           evidence_label="live-smoke-pass"),
        make_proof_record(product="glow-verified", proof_class="dashboard_render",
                           evidence_label="build-clean"),
    ]
    mismatch_item = make_item(product="glow-mismatch", wip_column="Done Verified",
                               requires_cleanup=False)
    mismatch_item["proof_records"] = []  # Unverified -> Done Verified mismatch

    out = os.path.join(str(tmp_path), "glyphs.html")
    html = _render_cp([verified_item, mismatch_item], out)

    verified_texts = _elements_with_class(html, "cp-verified")
    mismatch_texts = _elements_with_class(html, "cp-mismatch")
    assert verified_texts, "sanity: fixture must render a .cp-verified bar"
    assert mismatch_texts, "sanity: fixture must render a .cp-mismatch bar"

    assert _has_extra_glyph(verified_texts[0]), \
        "the .cp-verified bar's own markup TEXT must carry a glyph/character beyond its " \
        "plain-language label -- status may not be color-alone (AC5)"
    assert _has_extra_glyph(mismatch_texts[0]), \
        "the .cp-mismatch bar's own markup TEXT must carry a glyph/character beyond its " \
        "plain-language label -- status may not be color-alone (AC5)"
    assert set(_glyph_tokens(verified_texts[0])).isdisjoint(
        set(_glyph_tokens(mismatch_texts[0]))), \
        "the check glyph (cp-verified) and the warning glyph (cp-mismatch) must be visually " \
        "DISTINCT from each other, not the same glyph reused for opposite meanings"


def test_ac5_plain_unverified_state_also_carries_a_neutral_glyph_distinct_from_the_others(tmp_path):  # [BEHAVIORAL]
    """AC5: "plain unverified/claimed -> a neutral glyph" -- an item that
    fires NEITHER cp-verified NOR cp-mismatch (a genuinely plain state, e.g.
    Doing + Unverified, which per AC6.3 never mismatches) must still carry a
    distinct glyph on its .cp-evidence axis span, and that glyph must differ
    from BOTH the check glyph (cp-verified) and the warning glyph
    (cp-mismatch) used elsewhere on the page -- three visually distinct
    signals, never overlapping, never color-alone."""
    plain_item = make_item(product="glow-plain", wip_column="Doing", requires_cleanup=False)
    plain_item["proof_records"] = []  # Doing never mismatches; Unverified derived

    verified_item = make_item(product="glow-verified2", wip_column="Done Verified",
                               requires_cleanup=False)
    verified_item["proof_records"] = [
        make_proof_record(product="glow-verified2", proof_class="live_smoke",
                           evidence_label="live-smoke-pass"),
        make_proof_record(product="glow-verified2", proof_class="dashboard_render",
                           evidence_label="build-clean"),
    ]
    mismatch_item = make_item(product="glow-mismatch2", wip_column="Done Verified",
                               requires_cleanup=False)
    mismatch_item["proof_records"] = []

    out = os.path.join(str(tmp_path), "glyphs_plain.html")
    html = _render_cp([plain_item, verified_item, mismatch_item], out)
    assert _count_class(html, "cp-mismatch") == 1  # only mismatch_item fires it
    assert _count_class(html, "cp-verified") == 1  # only verified_item fires it

    # Order preserved (AC3) -> plain_item is the FIRST evidence element.
    plain_text = _elements_with_class(html, "cp-evidence")[0]
    assert "Unverified" in plain_text
    assert _has_extra_glyph(plain_text), \
        "the plain/unverified .cp-evidence text must carry its own neutral glyph too (AC5)"

    verified_glyphs = set(_glyph_tokens(_elements_with_class(html, "cp-verified")[0]))
    mismatch_glyphs = set(_glyph_tokens(_elements_with_class(html, "cp-mismatch")[0]))
    plain_glyphs = set(_glyph_tokens(plain_text))
    assert plain_glyphs, "expected at least one distinct glyph token in the plain state's text"
    assert plain_glyphs.isdisjoint(verified_glyphs), \
        "the neutral glyph must be visually DISTINCT from the check glyph (not reused)"
    assert plain_glyphs.isdisjoint(mismatch_glyphs), \
        "the neutral glyph must be visually DISTINCT from the warning glyph (not reused)"


# ===========================================================================
# AC6 -- Progressive disclosure with an always-visible one-line summary.
# ===========================================================================

def test_ac6_evidence_trail_collapsed_with_always_visible_leading_summary(tmp_path):  # [BEHAVIORAL]
    """AC6: the full evidence-trail detail renders inside a native
    ``<details class="cp-evidence-trail"><summary>...</summary>...
    </details>``, collapsed by default (no ``open`` attribute); a one-line
    verification summary renders OUTSIDE and AHEAD of that ``<details>``,
    always visible (never hidden behind the toggle). Zero JS anywhere in the
    page."""
    item = make_item(wip_column="Doing", requires_cleanup=False)
    item["proof_records"] = [make_proof_record(proof_class="unit_or_mock",
                                                evidence_label="mock-tested")]

    out = os.path.join(str(tmp_path), "trail.html")
    html = _render_cp([item], out)

    assert _has_class(html, "cp-evidence-trail")
    m = re.search(
        r'<details\b([^>]*\bclass=["\'][^"\']*\bcp-evidence-trail\b[^"\']*["\'][^>]*)>', html)
    assert m, "cp-evidence-trail must be rendered as a native <details> element"
    attrs = m.group(1)
    assert not re.search(r'(^|\s)open(\s|=|/|>|$)', attrs), \
        "the evidence trail <details> must be COLLAPSED by default (no 'open' attribute)"
    assert "<summary" in html, "the <details> must carry a native <summary>"

    assert _has_class(html, "cp-summary-line"), \
        "an always-visible one-line verification summary must render"
    summary_pos = html.find("cp-summary-line")
    details_pos = m.start()
    assert summary_pos != -1 and summary_pos < details_pos, \
        "the one-line summary must render OUTSIDE and AHEAD of the <details> trail -- never " \
        "hidden behind the collapse toggle"

    assert "<script" not in html.lower(), "AC6/stack constraint: zero JS anywhere in the page"


# ===========================================================================
# AC7 -- Render elapsed time via the new, isolated _select_backing_record
# helper.
# ===========================================================================

def test_ac7_select_backing_record_tie_break_prefers_most_recent_then_list_order():  # [BEHAVIORAL]
    """AC7: _select_backing_record's max()-based tie-break -- among 2+ valid
    records sharing the winning tier's proof_class, the MOST RECENT
    timestamp wins; a genuine EXACT tie is broken by list order (the FIRST
    maximal item, per Python's max() semantics, which the spec's own code
    block explicitly relies on)."""
    item = make_item(requires_cleanup=False)

    older = _validate(make_proof_record(timestamp=_iso_hours_ago(48)))
    older["_marker"] = "older"
    newer = _validate(make_proof_record(timestamp=_iso_hours_ago(1)))
    newer["_marker"] = "newer"

    picked = pd._select_backing_record(item, [older, newer], "live-smoke-pass")
    assert picked is not None and picked.get("_marker") == "newer", \
        "the MOST RECENT valid record sharing the tier's proof_class must be selected"

    same_ts = _iso_hours_ago(5)
    first = _validate(make_proof_record(timestamp=same_ts))
    first["_marker"] = "first"
    second = _validate(make_proof_record(timestamp=same_ts))
    second["_marker"] = "second"
    picked_tie = pd._select_backing_record(item, [first, second], "live-smoke-pass")
    assert picked_tie is not None and picked_tie.get("_marker") == "first", \
        "an EXACT timestamp tie must be broken by list order -- the FIRST maximal item wins"


def test_ac7_select_backing_record_genuineness_gate_applies_before_tie_break():  # [BEHAVIORAL] [SECURITY-ORACLE]
    """AC7: a NON-genuine live_smoke record (fails _is_genuine_live_smoke)
    must NEVER be selected even when its own timestamp is MORE RECENT than a
    genuine record's -- the genuineness gate is applied to build the
    CANDIDATE list first; the max()-by-timestamp tie-break only ever runs
    over records that already passed it."""
    item = make_item(requires_cleanup=False)

    genuine_but_older = _validate(make_proof_record(timestamp=_iso_hours_ago(48)))
    genuine_but_older["_marker"] = "genuine"

    fake_but_newer = _validate(make_proof_record(
        timestamp=_iso_hours_ago(1),
        command=["python3", "tools/live_smoke_MOCKED_runner.py"]))  # fails genuineness
    fake_but_newer["_marker"] = "fake"

    picked = pd._select_backing_record(item, [genuine_but_older, fake_but_newer],
                                        "live-smoke-pass")
    assert picked is not None and picked.get("_marker") == "genuine", \
        "a non-genuine (mocked) live_smoke record must never win the tie-break, even with a " \
        "strictly later timestamp than the genuine candidate"


def test_ac7_select_backing_record_returns_none_for_unverified_and_when_no_candidates_qualify():  # [BEHAVIORAL]
    """AC7: _select_backing_record returns None exactly when the derived
    label is "Unverified"/untiered, OR when zero candidate records qualify
    for the label's required proof_class -- never a raw record-count
    check."""
    item = make_item(requires_cleanup=False)

    assert pd._select_backing_record(item, [], "Unverified") is None, \
        "an untiered ('Unverified') derived label must return None (no backing record)"

    only_mock = _validate(make_proof_record(proof_class="unit_or_mock",
                                             evidence_label="mock-tested"))
    # "build-clean" requires a valid build_or_typecheck record -- none is
    # present, even though records DO exist (proves this is a qualifying-
    # candidate check, not a bare "any records at all" check).
    assert pd._select_backing_record(item, [only_mock], "build-clean") is None, \
        "zero qualifying candidates for the derived label's required proof_class must " \
        "return None even when OTHER (non-qualifying) records exist"


def test_ac7_select_backing_record_lower_tier_uses_required_proof_class_mapping():  # [BEHAVIORAL]
    """AC7: for a sub-live-smoke tier (e.g. "mock-tested"), the ELSE branch
    of _select_backing_record must select via LABEL_REQUIRED_PROOF_CLASS's
    mapping ("mock-tested" -> "unit_or_mock"), picking the most recent
    matching record among 2+ candidates -- the same tie-break rule as the
    live-smoke branch, exercised on a DIFFERENT tier so a Coder bug isolated
    to only the live-smoke branch is still caught."""
    item = make_item(requires_cleanup=False)

    older_mock = _validate(make_proof_record(proof_class="unit_or_mock",
                                              evidence_label="mock-tested",
                                              timestamp=_iso_hours_ago(72)))
    older_mock["_marker"] = "older"
    newer_mock = _validate(make_proof_record(proof_class="unit_or_mock",
                                              evidence_label="mock-tested",
                                              timestamp=_iso_hours_ago(2)))
    newer_mock["_marker"] = "newer"
    # A distractor of a DIFFERENT proof_class must never be considered.
    distractor = _validate(make_proof_record(proof_class="preflight",
                                              evidence_label="preflight-pass",
                                              timestamp=_iso_hours_ago(1)))

    picked = pd._select_backing_record(item, [older_mock, newer_mock, distractor],
                                        "mock-tested")
    assert picked is not None and picked.get("_marker") == "newer", \
        "the most recent record matching the required proof_class for a lower tier must win"


def test_ac7_age_unknown_isolated_via_doing_and_evidence_needed_wip_columns(tmp_path):  # [BEHAVIORAL]
    """AC7 Test isolation requirement: a dedicated test using a wip_column
    that does NOT unconditionally trigger wip_mismatch at a sub-"ready"
    derived label ("Doing" and "Evidence Needed" -- Doing NEVER mismatches
    per AC6.3; Evidence Needed only mismatches at rank >= live-smoke-pass,
    which neither fixture item below reaches), so the "age unknown" fallback
    text is the SOLE, unconfounded, independently observable signal --
    exactly the isolation gap the retracted "Done Verified" PRIMARY-test
    citation could not provide (its cp-mismatch fires unconditionally there
    regardless of AC7's own rendering)."""
    no_backing_item = make_item(product="age-unknown-prod", wip_column="Doing",
                                 requires_cleanup=False)
    no_backing_item["proof_records"] = []  # Unverified -> _select_backing_record -> None

    has_backing_item = make_item(product="age-known-prod", wip_column="Evidence Needed",
                                  requires_cleanup=False)
    has_backing_item["proof_records"] = [
        make_proof_record(product="age-known-prod", proof_class="unit_or_mock",
                           evidence_label="mock-tested", timestamp=_iso_hours_ago(2)),
    ]  # derived "mock-tested" (rank 1) is well below live-smoke-pass (rank 4), so
       # "Evidence Needed" does NOT mismatch here (AC6.3) -- true isolation.

    out = os.path.join(str(tmp_path), "age_isolation.html")
    html = _render_cp([no_backing_item, has_backing_item], out)

    # Isolation sanity: NEITHER item fires cp-mismatch, so any "age unknown"
    # vs. elapsed-time difference below cannot be a side effect of mismatch
    # rendering logic.
    assert _count_class(html, "cp-mismatch") == 0, \
        "sanity: this fixture must not confound the age-rendering check with a mismatch bar"

    summaries = _elements_with_class(html, "cp-summary-line")
    assert len(summaries) == 2

    # Order preserved (AC3) -> summaries[0] is no_backing_item's own summary.
    assert "age unknown" in summaries[0], \
        "an item with NO qualifying backing record (_select_backing_record -> None) must " \
        "render the literal 'age unknown' fallback text"
    assert "age unknown" not in summaries[1], \
        "an item WITH a qualifying backing record must render its actual elapsed time, not " \
        "the 'age unknown' fallback"
    assert "ago" in summaries[1], \
        "an item with a qualifying backing record must render its elapsed time (e.g. '2h ago')"


# ===========================================================================
# AC8 -- Claimed vs. Verified is the loudest contrast on the page.
# ===========================================================================

def test_ac8_verified_vs_mismatch_is_the_largest_declared_color_contrast():  # [BEHAVIORAL, joint DOC/visual]
    """AC8: the CSS-value-level portion of "claimed vs. verified is the
    loudest contrast on the page" that IS mechanically testable without a
    browser: the declared color distance between .cp-verified and
    .cp-mismatch's own CSS rules must exceed the declared color distance
    between EVERY OTHER sampled pair of AC-RENDER bar states (.cp-demo /
    .cp-focus / .cp-legacy-label -- the three OTHER AC-RENDER bar classes
    AC-RENDER's own closed enumeration guarantees will exist).

    This is NOT an exhaustive check over "every other pair of rendered
    states on the page" -- see the trailing comment below (and this
    dispatch's own final report) for the explicit, un-downgraded coverage
    gap: full "largest visual contrast" verification needs a human/Verifier
    visual read or a headless-browser computed-style/perceptual-contrast
    audit. This is the deterministic slice AC8 itself asks a Test-writer to
    write when full visual-contrast verification is not unit-testable."""
    style = pd.STYLE
    verified_rgb = _first_declared_color_rgb(style, "cp-verified")
    mismatch_rgb = _first_declared_color_rgb(style, "cp-mismatch")
    assert verified_rgb is not None, \
        "no declared hex color found for any CSS rule mentioning cp-verified -- AC8 requires " \
        "a color-driven visual distinction to compare"
    assert mismatch_rgb is not None, \
        "no declared hex color found for any CSS rule mentioning cp-mismatch -- AC8 requires " \
        "a color-driven visual distinction to compare"
    target_distance = _rgb_distance(verified_rgb, mismatch_rgb)

    other_pairs = [("cp-demo", "cp-focus"), ("cp-legacy-label", "cp-demo"),
                   ("cp-focus", "cp-legacy-label")]
    checked_any = False
    for token_a, token_b in other_pairs:
        rgb_a = _first_declared_color_rgb(style, token_a)
        rgb_b = _first_declared_color_rgb(style, token_b)
        if rgb_a is None or rgb_b is None:
            continue  # that other class has no declared color of its own -- nothing to compare
        other_distance = _rgb_distance(rgb_a, rgb_b)
        checked_any = True
        assert target_distance > other_distance, (
            "the declared color distance between .cp-verified and .cp-mismatch (%.1f) must "
            "exceed the color distance between .%s and .%s (%.1f) -- AC8's 'largest contrast "
            "on the page' priority constraint" % (target_distance, token_a, token_b, other_distance)
        )
    assert checked_any, \
        "none of the sampled other-state pairs had a comparable declared color at all -- " \
        "cp-demo/cp-focus/cp-legacy-label must each carry SOME declared color to make this " \
        "AC8 comparison meaningful"

    # --- KNOWN COVERAGE GAP (flagged explicitly, not silently downgraded) ---
    # This check is necessarily PARTIAL: it only compares DECLARED CSS hex
    # colors for a sampled set of OTHER bar-class pairs, using the first
    # matching color rule found per class. It cannot verify:
    #   * actual COMPUTED contrast as rendered by a real browser (cascade/
    #     specificity resolution, inherited colors, opacity/alpha, the base
    #     page background luminance, or a color set via a named CSS color
    #     keyword / rgb()/hsl() function this regex does not parse);
    #   * contrast against every OTHER possible pair of "rendered states" on
    #     the page (e.g. the focus-banner's own background vs. the plain
    #     grid's background, or the .cp-wip/.cp-evidence axis-pair's own
    #     default text color vs. either state) -- only the 3 OTHER
    #     AC-RENDER bar-class pairs are sampled here, not an exhaustive set;
    #   * perceptual/WCAG contrast ratio (relative luminance), only naive
    #     Euclidean RGB distance.
    # A human/Verifier visual read (or a headless-browser computed-style /
    # perceptual-contrast audit) is the correct next step for full AC8
    # coverage -- this is a genuine, explicitly-flagged gap, not a claim of
    # complete testability, per the Test-writer's standing hard constraint
    # on [BEHAVIORAL] criteria that resist full mechanical verification.


# ===========================================================================
# AC9 -- Calm empty and all-clear states.
# ===========================================================================

def test_ac9a_zero_items_empty_state_preserved_no_grid(tmp_path):  # [BEHAVIORAL]
    """AC9(a): the existing zero-items .empty state is preserved with its
    current trigger condition (len(cards) == 0) -- no .grid, no
    cp-all-clear (there is nothing to affirm with zero items)."""
    out = os.path.join(str(tmp_path), "empty_cp.html")
    html = _render_cp([], out)
    assert _has_class(html, "empty")
    assert not _has_class(html, "cp-all-clear"), \
        "zero items must not ALSO render the new calm all-clear summary"
    assert "class='grid'" not in html and 'class="grid"' not in html, \
        "the empty state must not ALSO render a (necessarily empty) grid wrapper"


def test_ac9b_calm_all_clear_summary_when_no_mismatches_and_no_active_focus(tmp_path):  # [BEHAVIORAL]
    """AC9(b): when >=1 item renders, no focus is set (or focus matches no
    item), and ZERO items carry cp-mismatch, an explicit calm affirmative
    one-line summary renders at the TOP of the page -- computed purely from
    already-derived per-item values, no new schema."""
    verified_item = make_item(product="allclear-verified", wip_column="Done Verified",
                               requires_cleanup=False)
    verified_item["proof_records"] = [
        make_proof_record(product="allclear-verified", proof_class="live_smoke",
                           evidence_label="live-smoke-pass"),
        make_proof_record(product="allclear-verified", proof_class="dashboard_render",
                           evidence_label="build-clean"),
    ]
    doing_item = make_item(product="allclear-doing", wip_column="Doing",
                            requires_cleanup=False)
    doing_item["proof_records"] = []

    out = os.path.join(str(tmp_path), "allclear.html")
    html = _render_cp([verified_item, doing_item], out, focus=None)
    assert _count_class(html, "cp-mismatch") == 0, "sanity: fixture must have zero mismatches"

    assert _has_class(html, "cp-all-clear"), \
        "zero mismatches + no active focus + >=1 item must render the calm all-clear summary"
    all_clear_text = _elements_with_class(html, "cp-all-clear")[0]
    assert re.search(r"\d+", all_clear_text), \
        "the all-clear summary must state a real (already-derived) verified count"

    all_clear_pos = html.find("cp-all-clear")
    first_product_pos = html.find("cp-product")
    assert all_clear_pos != -1 and first_product_pos != -1 and all_clear_pos < first_product_pos, \
        "the calm all-clear summary must render at the TOP of the page, before any item card"

    # Unmatched focus behaves the same as no focus at all (AC9(b) 'or focus
    # matches no item').
    out2 = os.path.join(str(tmp_path), "allclear_ghost_focus.html")
    html2 = _render_cp([verified_item, doing_item], out2, focus="ghost-not-present")
    assert _has_class(html2, "cp-all-clear")


def test_ac9b_all_clear_absent_when_any_mismatch_present(tmp_path):  # [BEHAVIORAL]
    """AC9(b) negative: a single mismatching item anywhere in the render
    must suppress the calm all-clear summary."""
    verified_item = make_item(product="mixed-verified", wip_column="Done Verified",
                               requires_cleanup=False)
    verified_item["proof_records"] = [
        make_proof_record(product="mixed-verified", proof_class="live_smoke",
                           evidence_label="live-smoke-pass"),
        make_proof_record(product="mixed-verified", proof_class="dashboard_render",
                           evidence_label="build-clean"),
    ]
    mismatch_item = make_item(product="mixed-mismatch", wip_column="Done Verified",
                               requires_cleanup=False)
    mismatch_item["proof_records"] = []

    out = os.path.join(str(tmp_path), "mixed.html")
    html = _render_cp([verified_item, mismatch_item], out, focus=None)
    assert _count_class(html, "cp-mismatch") == 1, "sanity"
    assert not _has_class(html, "cp-all-clear"), \
        "any cp-mismatch anywhere in the render must suppress the calm all-clear summary"


def test_ac9b_all_clear_absent_when_focus_is_active(tmp_path):  # [BEHAVIORAL]
    """AC9(b) negative: an ACTIVE (matching) focus suppresses the calm
    all-clear summary even with zero mismatches -- AC9(b)'s condition is
    explicitly "no focus is set (OR focus matches no item)", so a genuinely
    matching focus is a separate, mutually-exclusive page state from the
    all-clear summary."""
    focused_item = make_item(product="focus-active-prod", wip_column="Doing",
                              requires_cleanup=False)
    focused_item["proof_records"] = []

    out = os.path.join(str(tmp_path), "focus_active_allclear.html")
    html = _render_cp([focused_item], out, focus="focus-active-prod")
    assert _count_class(html, "cp-mismatch") == 0, "sanity"
    assert not _has_class(html, "cp-all-clear"), \
        "an ACTIVE matching focus must suppress the calm all-clear summary (AC9(b))"


# ===========================================================================
# AC10 -- Auto-refresh for a kept-open tab; legacy build() path unaffected.
# ===========================================================================

def test_ac10_legacy_build_output_unchanged_outside_sanctioned_style_growth(tmp_path):  # [BEHAVIORAL]
    """AC10: the legacy build() call site passes ONLY its existing two
    positional args to render_html (never touching the new refresh_seconds
    kwarg), so its output must remain unchanged from the pre-redesign
    baseline -- captured directly by running the UNMODIFIED
    product_dashboard.py against this exact fixture BEFORE this build began
    (see ``_AC10_LEGACY_BASELINE_NORMALIZED_HTML`` above). The comparison
    excludes the STYLE block's own text (see ``_strip_style_block``'s
    docstring) because this SAME spec separately, and explicitly, sanctions
    additive cp-* growth to that shared constant -- excluding it is the
    correct, non-self-contradictory reading of "byte-identical," not a
    weakening of the check."""
    status = _write_json(str(tmp_path), {
        "product": "LegacyRegProd", "done_sentence": "goal.", "updated": "2026-01-01",
        "items": [{"title": "t1", "status": "fixed", "verified": True, "phase": "built",
                   "priority": 1, "evidence": {}}],
    })
    out = os.path.join(str(tmp_path), "legacy_ac10.html")
    pd.build(status_paths=[status], out=out)
    with open(out, "r", encoding="utf-8") as fh:
        html = fh.read()

    assert 'http-equiv="refresh"' not in html, \
        "the legacy build() call site must NEVER emit the new auto-refresh <meta> tag"

    normalized = _strip_style_block(html)
    assert normalized == _AC10_LEGACY_BASELINE_NORMALIZED_HTML, \
        "outside the separately-sanctioned STYLE-block growth, the legacy build() output " \
        "must be unchanged from the pre-redesign baseline"


def test_ac10_render_html_refresh_seconds_kwarg_is_additive_and_off_by_default():  # [BEHAVIORAL]
    """AC10: render_html gains ONE new optional refresh_seconds=None kwarg.
    Default None emits no refresh meta tag at all; a real value emits the
    EXACT literal meta tag with that value -- tested with a value (60)
    DIFFERENT from CP_REFRESH_SECONDS (120) so this exercises genuine
    parameterization, not a hardcoded 120 baked into render_html itself."""
    html_default = pd.render_html("<div>x</div>", False)
    assert 'http-equiv="refresh"' not in html_default

    html_explicit_none = pd.render_html("<div>x</div>", False, refresh_seconds=None)
    assert 'http-equiv="refresh"' not in html_explicit_none

    html_60 = pd.render_html("<div>x</div>", False, refresh_seconds=60)
    assert '<meta http-equiv="refresh" content="60">' in html_60, \
        "a real refresh_seconds value must emit the literal auto-refresh <meta> tag with " \
        "that exact value"


def test_ac10_render_control_plane_emits_refresh_meta_via_module_constant(tmp_path):  # [BEHAVIORAL]
    """AC10: render_control_plane must call render_html with the
    module-level CP_REFRESH_SECONDS == 120 constant, so its own output DOES
    contain the auto-refresh meta tag (unlike the legacy build() path
    above)."""
    assert pd.CP_REFRESH_SECONDS == 120, \
        "AC10 names this exact module-level constant directly"

    item = make_item(wip_column="Doing", requires_cleanup=False)
    item["proof_records"] = []
    out = os.path.join(str(tmp_path), "refresh_cp.html")
    html = _render_cp([item], out)
    assert '<meta http-equiv="refresh" content="120">' in html, \
        "render_control_plane's own output must include the auto-refresh meta tag for a " \
        "kept-open browser tab (AC10)"


# ===========================================================================
# AC11 -- Scope lock, verified mechanically.
# ===========================================================================

def test_ac11_scope_locked_functions_source_unchanged_by_redesign():  # [DOC]
    """AC11 scope lock, verified MECHANICALLY (not just by manual diff
    review): each of these functions' own source text (inspect.getsource)
    must hash-match the EXACT pre-redesign baseline captured directly from
    this same product_dashboard.py before this build began -- ANY textual
    edit (including whitespace/comment/docstring changes) to one of these
    AC11-named functions is exactly the scope-lock violation AC11 forbids.
    Only the functions AC11's own sentence names BY NAME are locked here
    (render_control_plane/_render_cp_card/render_html/STYLE and any new
    small private helper are explicitly the intended edit targets and are
    deliberately NOT included)."""
    import inspect
    import hashlib
    for name, expected_hash in _AC11_LOCKED_FUNCTION_HASHES.items():
        fn = getattr(pd, name)
        actual_hash = hashlib.sha256(inspect.getsource(fn).encode("utf-8")).hexdigest()
        assert actual_hash == expected_hash, (
            "AC11 scope-lock violation: %r's own source text changed during this redesign "
            "(expected sha256 %s, got %s) -- AC11 permits edits ONLY to "
            "render_control_plane/_render_cp_card/render_html/STYLE and clearly-named new "
            "small private helpers" % (name, expected_hash, actual_hash)
        )
