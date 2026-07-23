#!/usr/bin/env python3
"""repo_health_gate.py -- reallocates the loop team's own time between
new-capability build work and hardening/bugfix work on a PER-REPO basis
(spec: loop-team/runs/2026-07-10_repo-health-gate/specs/spec.md, v5).

Motivation (2026-07-10 research synthesis, `research/two-tier-team-vs-gate-
2026-07-10.md`): rather than splitting the loop team into a permanently
separate build track and debug track, this is a formal, quantitative GATE
(SRE error-budget / Kanban-class-of-service shape) that freezes NEW-
CAPABILITY Coder dispatches on a repo once its open hardening backlog
crosses a threshold, and auto-clears once that backlog is worked down.

**Standing generalization: this mechanism is NOT specific to any one repo.**
Any repo/tool the loop team builds or works on gets tracked in the same
`hardening_ledger.json` once work on it disperses across multiple
sessions/worktrees -- see `orchestrator.md`'s repo-health-gate rule.

Ledger schema (one JSON array of objects, `hardening_ledger.json`, living
alongside this script):
    {
      "id": "<UPPER-KEBAB-ID, unique across the whole file>",
      "repo": "<repo identifier, e.g. 'taxahead', 'padsplit-cockpit', ...>",
      "kind": "item" | "recurring_class",
      "status": "open" | "closed",
      "basis": "cited" | "inferred",
      "description": "<one sentence>",
      "citation": "<exact file:line/heading/commit reference(s)>",
      "opened": "<YYYY-MM-DD>",
      "closed": "<YYYY-MM-DD or null>",
      "closing_reference": "<commit SHA / verifier-run note, or null>"
    }

FREEZE logic (`compute_verdict`): `I` = count of open `kind=="item"` entries
for the repo, `C` = count of open `kind=="recurring_class"` entries for the
repo. `I<=1 AND C==0` -> CLEAR. `I>=2` -> FROZEN. `C>=1` -> FROZEN (an open
recurring class always forces FROZEN, independent of `I`).

Three pure, importable functions (`load_ledger`, `compute_verdict`,
`apply_close`) plus one small, deliberately non-pure date helper
(`_today_iso`) -- reused directly from `fixplan_closure_lint.py:852-859`'s
own `_today_iso()` (same name, same contract: `datetime.now(timezone.utc)`
is called ONLY here, never inside `compute_verdict`/`apply_close`
themselves, so those two stay fully deterministic and test-friendly with a
literal fixed `closed_date` string).

CLI:
    repo_health_gate.py <repo-id>
        Loads the real ledger (path resolved relative to this script's own
        location, matching fixplan_closure_lint.py's `_default_path()`
        convention), computes the verdict for <repo-id>, prints it as JSON
        to stdout, exits 0. On any `load_ledger` exception, prints a clear
        stderr message naming the file path and the condition that fired,
        exits 2.

    repo_health_gate.py --close <id> --reference "<text>"
        Loads the real ledger, computes today's real UTC date via
        `_today_iso()`, calls `apply_close(...)`, and -- only on success --
        writes the updated list back to the real file. On an `apply_close`
        exception (not found / already closed), prints a clear stderr
        message, exits 2, and writes nothing back. On a `load_ledger`
        exception, behaves exactly like the plain `<repo-id>` path above
        (stderr names the file, exit 2, no write).

    repo_health_gate.py --selftest
        Diagnostic mode: exercises `compute_verdict` (including a
        `basis: "inferred"` fixture), `load_ledger`, and `apply_close`
        directly against synthetic/self-created-and-cleaned-up
        `tempfile`-based fixtures -- NEVER the real `hardening_ledger.json`.
        Reuses `fixplan_closure_lint.py`'s heartbeat-log pattern and
        `run_and_record.py`'s `_gate_dir()` for the heartbeat log location:
        every invocation appends one line to
        `<gate_dir>/repo_health_gate_selftest.log`, on every outcome
        (PASS/FAIL/ERROR), so the log's own growth is itself a "did this
        actually fire" signal independent of what it found.

Exit codes:
    0 -- success (plain `<repo-id>` verdict printed, or `--close` applied
         and written back, or `--selftest` passed).
    2 -- usage error, a `load_ledger` failure, an `apply_close` failure, or
         a `--selftest` FAIL/ERROR.
"""
import copy
import json
import os
import sys
import tempfile
from datetime import datetime, timezone

# NOTE: run_and_record.py's `_gate_dir()` (reused for the --selftest
# heartbeat log location, per spec -- do not reinvent it) is imported
# LAZILY, inside `_append_selftest_heartbeat()` below, rather than at
# module level. Reason: AC10's end-to-end CLI tests copy ONLY this script
# file (plus a ledger) into a fresh tmp_path directory to exercise the
# documented default-path convention -- `run_and_record.py` is not
# co-located there, and is not needed for the `<repo-id>` / `--close` paths
# those tests exercise. A module-level import would make every invocation
# of this script (not just --selftest) hard-depend on `run_and_record.py`
# being on sys.path, breaking that scenario. `--selftest` is always
# invoked against the real, co-located harness/ directory (see
# test_repo_health_gate.py's own TestAC6Selftest), so the lazy import
# always succeeds when it's actually needed.


# =============================================================================
# Exception hierarchy.
#
# `load_ledger()` raises a specific, distinctly-TYPED exception for each of
# the three malformed conditions the spec names (invalid JSON, a missing
# required field, a duplicate id) -- each gets its own class, all sharing a
# common `LedgerError` base for callers that want to catch "any malformed-
# ledger condition" without caring which. `apply_close()` raises a specific
# exception for each of its two error conditions (not found / already
# closed) -- the spec's own wording for `apply_close` is singular ("a
# specific exception", not "a distinctly-typed exception for EACH
# condition" as `load_ledger`'s clause reads), so these two are not required
# to be of mutually distinct types from each other, only real, message-
# differentiated exceptions; they are still given their own classes below
# for clarity and so a caller CAN distinguish them if it wants to.
# =============================================================================


class LedgerError(Exception):
    """Base class for every `load_ledger()` malformed-ledger condition."""


class InvalidLedgerJSONError(LedgerError):
    """The ledger file's content is not valid JSON, or its top-level/entry
    shapes are not the JSON array-of-objects the schema requires."""


class LedgerMissingFieldError(LedgerError):
    """An entry in the ledger is missing one of the required schema
    fields."""


class LedgerDuplicateIdError(LedgerError):
    """Two or more entries in the ledger share the same `id`."""


class ApplyCloseError(Exception):
    """Base class for every `apply_close()` error condition."""


class EntryNotFoundError(ApplyCloseError):
    """`apply_close()`'s `entry_id` does not match any entry."""


class EntryAlreadyClosedError(ApplyCloseError):
    """`apply_close()`'s matching entry's `status` is already `'closed'`."""


# The ledger schema's full, finite field set (spec's "Public interface"
# JSON shape) -- every one of these must be present on every entry.
REQUIRED_FIELDS = (
    "id", "repo", "kind", "status", "basis", "description",
    "citation", "opened", "closed", "closing_reference",
)


def load_ledger(path):
    """Read and parse the ledger JSON array at `path`.

    Raises:
        InvalidLedgerJSONError -- the file's content is not valid JSON, or
            parses to something other than a JSON array of JSON objects.
        LedgerMissingFieldError -- an entry is missing one of
            REQUIRED_FIELDS.
        LedgerDuplicateIdError -- two entries share the same `id`.

    A real I/O failure (e.g. the file does not exist) is allowed to
    propagate as the underlying `OSError` unchanged -- that is not one of
    the three "malformed ledger content" conditions above, but `main()`
    still reports it the same way (any `load_ledger` exception -> stderr +
    exit 2).

    Pure with respect to the file: reads only, never writes, never mutates
    anything outside its own return value.
    """
    with open(path, encoding="utf-8") as f:
        raw_text = f.read()

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise InvalidLedgerJSONError(
            "invalid JSON in ledger file %s: %s" % (path, e)
        ) from e

    if not isinstance(data, list):
        raise InvalidLedgerJSONError(
            "invalid JSON in ledger file %s: top-level value must be a "
            "JSON array, got %s" % (path, type(data).__name__)
        )

    seen_ids = set()
    for entry in data:
        if not isinstance(entry, dict):
            raise InvalidLedgerJSONError(
                "invalid JSON in ledger file %s: each entry must be a JSON "
                "object, got %s" % (path, type(entry).__name__)
            )

        for field in REQUIRED_FIELDS:
            if field not in entry:
                raise LedgerMissingFieldError(
                    "ledger file %s: entry %r is missing required field %r"
                    % (path, entry.get("id", "<unknown id>"), field)
                )

        entry_id = entry["id"]
        if entry_id in seen_ids:
            raise LedgerDuplicateIdError(
                "ledger file %s: duplicate id found in ledger: %r"
                % (path, entry_id)
            )
        seen_ids.add(entry_id)

    return data


def compute_verdict(entries, repo_id):
    """Compute the FREEZE/CLEAR verdict for `repo_id` from `entries`
    (already-parsed ledger entries, any mix of repos).

    Pure -- no file I/O, no wall-clock reads. Scoped entirely to entries
    matching `entries[i]['repo'] == repo_id`; entries for other repos
    (open, closed, cited, or inferred) never leak into this repo's own
    counts, lists, or reasoning.

    FREEZE logic: `I` = count of open `kind=="item"` entries for this repo,
    `C` = count of open `kind=="recurring_class"` entries for this repo.
    `I<=1 AND C==0` -> CLEAR. `I>=2` -> FROZEN. `C>=1` -> FROZEN (an open
    recurring class always forces FROZEN, independent of `I` -- verified by
    AC1's (1,1)/(2,1) non-contradiction boundary cells).

    Returns the verdict dict:
        {
          "repo": <repo_id>,
          "verdict": "FROZEN" | "CLEAR",
          "open_item_count": <I>,
          "open_recurring_classes": [<ids of open recurring_class entries>],
          "cited_entries_driving_verdict": [<ids of the OPEN items/classes
              above whose basis=="cited">],
          "inferred_entries_driving_verdict": [<... whose basis=="inferred">],
          "reasoning": "<one sentence citing counts/ids, explicitly noting
              dependence on any inferred-basis entry>",
        }
    """
    repo_entries = [e for e in entries if e.get("repo") == repo_id]

    open_items = [
        e for e in repo_entries
        if e.get("kind") == "item" and e.get("status") == "open"
    ]
    open_classes = [
        e for e in repo_entries
        if e.get("kind") == "recurring_class" and e.get("status") == "open"
    ]

    open_item_count = len(open_items)
    open_class_count = len(open_classes)

    if open_class_count >= 1 or open_item_count >= 2:
        verdict_str = "FROZEN"
    else:
        verdict_str = "CLEAR"

    open_recurring_classes = [e["id"] for e in open_classes]

    # The entries actually "driving" this verdict: every open item/class
    # for this repo (whether or not it alone would force FROZEN) -- split
    # by basis so a caller can see how much of the verdict rests on
    # inferred (vs. directly cited) evidence.
    driving_entries = open_items + open_classes
    driving_ids = [e["id"] for e in driving_entries]
    cited_ids = [e["id"] for e in driving_entries if e.get("basis") == "cited"]
    inferred_ids = [e["id"] for e in driving_entries if e.get("basis") == "inferred"]

    reasoning = "%s: %d open item(s) and %d open recurring class(es) -> %s" % (
        repo_id, open_item_count, open_class_count, verdict_str,
    )
    if driving_ids:
        reasoning += "; driving entries: %s" % ", ".join(driving_ids)
    if inferred_ids:
        reasoning += "; verdict depends on inferred-basis entry(ies): %s" % (
            ", ".join(inferred_ids)
        )

    return {
        "repo": repo_id,
        "verdict": verdict_str,
        "open_item_count": open_item_count,
        "open_recurring_classes": open_recurring_classes,
        "cited_entries_driving_verdict": cited_ids,
        "inferred_entries_driving_verdict": inferred_ids,
        "reasoning": reasoning,
    }


def apply_close(entries, entry_id, reference, closed_date):
    """Return a NEW list (does not mutate `entries` in place) with the
    entry matching `entry_id` closed: `status` set to `'closed'`, `closed`
    set to `closed_date` (caller-supplied ISO `YYYY-MM-DD` -- NOT computed
    here), `closing_reference` set to `reference`. Every other entry is
    left byte-for-byte (deep-copy) identical to the input.

    Raises:
        EntryNotFoundError -- no entry in `entries` has `id == entry_id`.
        EntryAlreadyClosedError -- the matching entry's `status` is already
            `'closed'`.

    In both error cases, `entries` (the caller's original list/dicts) is
    left completely unmodified -- this function deep-copies BEFORE doing
    anything else, so no partial mutation is ever visible even on the
    error path.

    Fully deterministic: `datetime.now()` is never called anywhere in this
    function -- `closed_date` is supplied by the caller (`main()` computes
    it via `_today_iso()` before calling this).
    """
    result = copy.deepcopy(entries)

    match = None
    for entry in result:
        if entry.get("id") == entry_id:
            match = entry
            break

    if match is None:
        raise EntryNotFoundError(
            "entry id %r not found in ledger" % entry_id
        )
    if match.get("status") == "closed":
        raise EntryAlreadyClosedError(
            "entry %r is already closed" % entry_id
        )

    match["status"] = "closed"
    match["closed"] = closed_date
    match["closing_reference"] = reference

    return result


def _today_iso():
    """Return today's real UTC date as an ISO `YYYY-MM-DD` string. The ONLY
    place `datetime.now()` is called for `--close`'s date value. Mirrors
    `fixplan_closure_lint.py`'s own `_today_iso()` (lines 852-859)
    precedent exactly -- same name, same contract, not reimplemented
    differently."""
    return datetime.now(timezone.utc).date().isoformat()


def _default_ledger_path():
    """Resolve `hardening_ledger.json`'s path relative to THIS script's own
    location -- matching `fixplan_closure_lint.py`'s `_default_path()`
    convention of resolving relative to `os.path.dirname(os.path.abspath(
    __file__))`. Unlike that file's `fix_plan.md` (which lives at the repo
    root, two directories up from `loop-team/harness/`), `hardening_ledger.
    json` is co-located directly alongside this script -- this is also what
    lets a `tmp_path`-copied `repo_health_gate.py` transparently resolve to
    a co-located, copied ledger (AC10's end-to-end CLI tests) with no
    invented path-override flag."""
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "hardening_ledger.json")


def _selftest_entry(entry_id, repo, kind, status, basis="cited"):
    """Build one schema-shaped synthetic ledger entry (all REQUIRED_FIELDS
    present) for --selftest's own in-memory/temp-file fixtures."""
    return {
        "id": entry_id,
        "repo": repo,
        "kind": kind,
        "status": status,
        "basis": basis,
        "description": "repo_health_gate --selftest synthetic fixture entry",
        "citation": "selftest:synthetic-fixture",
        "opened": "2026-01-01",
        "closed": None,
        "closing_reference": None,
    }


def _append_selftest_heartbeat(status, detail=""):
    """Append one line to `<gate_dir>/repo_health_gate_selftest.log`,
    recording that --selftest fired and what it found. Called on EVERY
    --selftest outcome (PASS, FAIL, or an unanticipated ERROR) -- never
    skipped -- so the log's own growth is itself the "configured vs fired"
    signal, mirroring `fixplan_closure_lint.py`'s own
    `_append_selftest_heartbeat()` pattern exactly."""
    try:
        from run_and_record import _gate_dir as _rar_gate_dir
    except ImportError:
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
        from run_and_record import _gate_dir as _rar_gate_dir

    gate_dir = _rar_gate_dir()
    os.makedirs(gate_dir, exist_ok=True)
    log_path = os.path.join(gate_dir, "repo_health_gate_selftest.log")
    line = "%s SELFTEST %s%s\n" % (
        datetime.now(timezone.utc).isoformat(),
        status,
        (" detail=%r" % detail) if detail else "",
    )
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def _run_selftest():
    """Diagnostic self-test: exercises `compute_verdict` (with a
    `basis: "inferred"` fixture), `load_ledger`, and `apply_close` directly
    against synthetic, self-created-and-cleaned-up `tempfile` fixtures --
    NEVER the real `hardening_ledger.json`. Also confirms `load_ledger`'s
    own malformed-ledger detection (a duplicate-id fixture) still fires.

    Returns an int exit code: 0 (PASS), 1 (FAIL -- unexpected result from
    one of the exercised functions), or 2 (an unanticipated exception during
    fixture construction/evaluation). Appends one heartbeat line on every
    outcome, including a crash.
    """
    try:
        # --- Part 1: compute_verdict(), including a basis="inferred" case. ---
        synthetic_entries = [
            _selftest_entry("SELFTEST-ITEM-1", "selftest-repo", "item", "open", basis="cited"),
            _selftest_entry("SELFTEST-CLASS-1", "selftest-repo", "recurring_class", "open", basis="inferred"),
            _selftest_entry("SELFTEST-OTHER-REPO-1", "selftest-other-repo", "item", "open", basis="cited"),
        ]
        verdict = compute_verdict(synthetic_entries, "selftest-repo")
        verdict_ok = (
            verdict["repo"] == "selftest-repo"
            and verdict["verdict"] == "FROZEN"
            and verdict["open_item_count"] == 1
            and verdict["open_recurring_classes"] == ["SELFTEST-CLASS-1"]
            and verdict["cited_entries_driving_verdict"] == ["SELFTEST-ITEM-1"]
            and verdict["inferred_entries_driving_verdict"] == ["SELFTEST-CLASS-1"]
            and "inferred" in verdict["reasoning"].lower()
        )

        # --- Part 2: load_ledger() + apply_close(), via self-created,
        # self-cleaned-up tempfile fixtures (never the real ledger). ---
        tmp_dir = tempfile.mkdtemp(prefix="repo_health_gate_selftest_")
        try:
            ledger_path = os.path.join(tmp_dir, "ledger.json")
            with open(ledger_path, "w", encoding="utf-8") as f:
                json.dump(synthetic_entries, f)

            loaded = load_ledger(ledger_path)
            load_ok = loaded == synthetic_entries

            closed_date = "2030-01-01"  # literal, deterministic -- never real wall clock
            closed_entries = apply_close(
                loaded, "SELFTEST-ITEM-1", "selftest-close-ref", closed_date
            )
            closed_entry = next(
                e for e in closed_entries if e["id"] == "SELFTEST-ITEM-1"
            )
            apply_close_ok = (
                closed_entry["status"] == "closed"
                and closed_entry["closed"] == closed_date
                and closed_entry["closing_reference"] == "selftest-close-ref"
                and loaded == synthetic_entries  # loaded/original untouched
            )

            # load_ledger()'s malformed-ledger detection: a duplicate-id
            # fixture must still raise.
            dup_path = os.path.join(tmp_dir, "dup_ledger.json")
            dup_entries = [
                _selftest_entry("SELFTEST-DUP-1", "selftest-repo", "item", "open"),
                _selftest_entry("SELFTEST-DUP-1", "selftest-repo", "item", "open"),
            ]
            with open(dup_path, "w", encoding="utf-8") as f:
                json.dump(dup_entries, f)
            malformed_detected = False
            try:
                load_ledger(dup_path)
            except LedgerDuplicateIdError:
                malformed_detected = True
        finally:
            _rmtree_ignore_errors(tmp_dir)

        selftest_pass = verdict_ok and load_ok and apply_close_ok and malformed_detected

        if selftest_pass:
            print("repo_health_gate: --selftest PASS")
            print("  compute_verdict: inferred-basis fixture verdict as expected")
            print("  load_ledger/apply_close: temp-file round trip as expected")
            print("  load_ledger: duplicate-id fixture correctly flagged as malformed")
            _append_selftest_heartbeat("PASS", "")
            return 0

        fail_reasons = []
        if not verdict_ok:
            fail_reasons.append("compute_verdict")
        if not load_ok:
            fail_reasons.append("load_ledger")
        if not apply_close_ok:
            fail_reasons.append("apply_close")
        if not malformed_detected:
            fail_reasons.append("malformed-ledger-detection")

        print(
            "repo_health_gate: --selftest FAIL -- unexpected result(s) from: %s"
            % ", ".join(fail_reasons)
        )
        _append_selftest_heartbeat("FAIL", ", ".join(fail_reasons))
        return 1
    except Exception as e:
        _append_selftest_heartbeat("ERROR", str(e))
        sys.stderr.write("repo_health_gate: --selftest ERROR -- %s\n" % e)
        return 2


def _rmtree_ignore_errors(path):
    """Best-effort recursive cleanup of a --selftest temp dir. A plain
    stdlib `shutil.rmtree(path, ignore_errors=True)` equivalent, written out
    directly here rather than importing `shutil` for one call site."""
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def _handle_repo_id(repo_id):
    """`main()`'s plain `<repo-id>` path: load the real ledger, compute the
    verdict, print it as JSON, return the process exit code."""
    path = _default_ledger_path()
    try:
        entries = load_ledger(path)
    except Exception as e:
        sys.stderr.write(
            "repo_health_gate: could not load ledger at %s: %s\n" % (path, e)
        )
        return 2

    verdict = compute_verdict(entries, repo_id)
    print(json.dumps(verdict))
    return 0


def _handle_close(args):
    """`main()`'s `--close <id> --reference "<text>"` path: load the real
    ledger, compute today's date, apply the close, and -- only on success
    -- write the result back to the real file. Returns the process exit
    code."""
    if len(args) != 4 or args[2] != "--reference":
        sys.stderr.write(
            'usage: repo_health_gate.py --close <id> --reference "<text>"\n'
        )
        return 2

    entry_id = args[1]
    reference = args[3]
    path = _default_ledger_path()

    try:
        entries = load_ledger(path)
    except Exception as e:
        sys.stderr.write(
            "repo_health_gate: could not load ledger at %s: %s\n" % (path, e)
        )
        return 2

    closed_date = _today_iso()
    try:
        updated = apply_close(entries, entry_id, reference, closed_date)
    except Exception as e:
        sys.stderr.write("repo_health_gate: --close failed: %s\n" % e)
        return 2

    with open(path, "w", encoding="utf-8") as f:
        json.dump(updated, f, indent=2)
        f.write("\n")

    print(json.dumps({
        "closed": entry_id, "closed_date": closed_date, "reference": reference,
    }))
    return 0


def main(argv):
    args = list(argv[1:])

    if args == ["--selftest"]:
        return _run_selftest()
    if args and args[0] == "--selftest":
        sys.stderr.write("usage: repo_health_gate.py --selftest\n")
        return 2

    if args and args[0] == "--close":
        return _handle_close(args)

    if len(args) == 1:
        return _handle_repo_id(args[0])

    sys.stderr.write(
        'usage: repo_health_gate.py <repo-id> | '
        '--close <id> --reference "<text>" | --selftest\n'
    )
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
