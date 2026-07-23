#!/usr/bin/env python3
"""Deterministic meta-verification (Layer 1) for loop-team builds -- ZERO API.

Most of what an independent verifier does needs no model: re-run the tests, check
the eval suite is green, lint the generated cases (valid JSON / required fields /
no answer-leakage / no PII / trap-good balance), and red-team the keep-logic.
Bundling all of that into a live judgment SUBAGENT meant one `529 Overloaded`
blocked ALL verification signal -- and triggered an hour of open-ended retries.

This script is the always-available Layer 1: it cannot 529. The agentic judgment
verifier (Layer 2) is then ADDITIVE (red-team adaptively, rule on judgment calls),
never the sole source of basic signal. See public/VERIFY_POLICY.md for how the two
layers + the bounded-retry policy fit together. Mirrors the project's own two-layer
verifier philosophy (harness/verify.py Layer 1 + judgment Layer 2), applied to
META-verification.

CLI:  python3 verify_build.py        # structured report; exit 0 iff all checks pass
      python3 verify_build.py --no-pytest   # skip the subprocess sweep (faster)
"""
import glob
import json
import os
import re
import subprocess
import sys

THIS_DIR = os.path.dirname(os.path.abspath(__file__))          # .../loop-team/evals
LOOPTEAM_DIR = os.path.normpath(os.path.join(THIS_DIR, ".."))  # .../loop-team
REPO_ROOT = os.path.normpath(os.path.join(LOOPTEAM_DIR, ".."))  # .../loop (repo root)

# Shared structured logger (stdlib only). Put loop-team/ on sys.path so
# `from harness.log import get_logger` resolves regardless of cwd. Logging is
# best-effort and never touches stdout, so the stdout report + exit code below
# are unaffected.
if LOOPTEAM_DIR not in sys.path:
    sys.path.insert(0, LOOPTEAM_DIR)
try:
    from harness.log import get_logger
except Exception:  # pragma: no cover - defensive; logging stays optional
    get_logger = None
OPTIMIZE_DIR = os.path.join(LOOPTEAM_DIR, "optimize")
PII_GUARD = os.path.join(REPO_ROOT, "scripts", "pii-guard.sh")
# Personal markers live in a LOCAL, gitignored file (not in any tracked script),
# so the published guard + this lint carry no personal strings. Read at runtime.
PII_MARKERS = os.path.join(REPO_ROOT, "scripts", ".pii-markers.local")

sys.path.insert(0, THIS_DIR)
sys.path.insert(0, OPTIMIZE_DIR)

CASE_DIRS = [os.path.join(THIS_DIR, "cases", "candidates"),
             os.path.join(THIS_DIR, "cases", "objective")]
# Per-target required fields for TOP-LEVEL cases/*.json (subdirs excluded; hard/
# holds non-case records). Corpus-scanned 2026-07-01: exactly these targets exist.
TOPLEVEL_SCHEMAS = {
    "harness": ("fixture",),
    "citation_grounding": ("artifacts", "model_output"),
    "recorded_fetch": ("artifact", "report_claim", "snapshot"),
    "verifier": ("artifact", "rubric", "requires"),
    "test_writer": ("artifact", "rubric", "requires"),
    "orchestrator": ("artifact", "rubric", "requires"),
    "slop_metrics": ("code_before", "code_after"),
}
REQUIRED_FIELDS = ("id", "expected", "artifact")
LABELS = ("PASS", "FAIL", "FALSE-PASS")
REJECT_LABELS = ("FAIL", "FALSE-PASS")
# Gold-side fields that state the answer/reasoning -- must NEVER appear inside the
# `artifact` the judge sees (that would leak the verdict).
GOLD_SIDE_FIELDS = ("fact", "why_objective", "failure_mode", "why_hard",
                    "objective_fact", "rubric")
# Fallback used ONLY if the pre-push guard file is unreadable. This file is exempt
# from the guard's own scan (it's key-detection tooling), so listing the key
# prefixes here is safe. Personal markers stay in scripts/pii-guard.sh (the single
# source pii_pattern() reads at runtime); the net here is the LLM key prefixes.
_KEY_PREFIXES = ("sk-ant", "sk-proj")
_DEFAULT_PII = "|".join(_KEY_PREFIXES)


def pii_pattern():
    """Build the PII regex the lint uses, kept in sync with the pre-push guard.

    OR's together, in order: the guard's PATTERN line (just the generic key
    prefixes in the published script), the personal markers from the LOCAL,
    gitignored file (scripts/.pii-markers.local — names/paths kept out of every
    tracked file), and the LLM key prefixes as a built-in net. Falls back to the
    key prefixes alone if both sources are absent."""
    terms = []
    # base pattern from the guard (published: just sk-ant|sk-proj)
    try:
        with open(PII_GUARD, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*PATTERN='([^']+)'", line)
                if m:
                    terms.append(m.group(1))
                    break
    except OSError:
        pass
    # personal markers from the local, gitignored file (raw, to mirror the
    # guard's `grep -E` alternation)
    try:
        with open(PII_MARKERS, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    terms.append(s)
    except OSError:
        pass
    for pfx in _KEY_PREFIXES:
        terms.append(pfx)
    # dedupe, preserve order; fall back to the key prefixes if nothing else
    seen, parts = set(), []
    for t in terms:
        if t and t not in seen:
            seen.add(t)
            parts.append(t)
    return re.compile("|".join(parts) if parts else _DEFAULT_PII, re.IGNORECASE)


def lint_cases(dirs=CASE_DIRS):
    """Validate every case JSON. Returns (ok, report). Checks: parseable JSON,
    required fields, valid `expected` label, NO gold-side field leaking into the
    artifact, NO PII, and trap/good balance (a one-sided dir is a broken suite)."""
    pii = pii_pattern()
    problems = []
    per_dir = {}
    for d in dirs:
        name = os.path.relpath(d, THIS_DIR)
        files = sorted(glob.glob(os.path.join(d, "*.json")))
        traps = goods = 0
        for fp in files:
            base = os.path.basename(fp)
            try:
                with open(fp, encoding="utf-8") as fh:
                    c = json.load(fh)
            except (OSError, json.JSONDecodeError) as e:
                problems.append("%s: invalid JSON (%s)" % (base, e))
                continue
            for k in REQUIRED_FIELDS:
                if not c.get(k):
                    problems.append("%s: missing/empty required field %r" % (base, k))
            exp = c.get("expected")
            if exp not in LABELS:
                problems.append("%s: bad expected label %r (must be %s)"
                                % (base, exp, "/".join(LABELS)))
            artifact = str(c.get("artifact", ""))
            for gf in GOLD_SIDE_FIELDS:
                val = c.get(gf)
                if isinstance(val, str) and val and val in artifact:
                    problems.append("%s: LEAK -- gold-side field %r appears inside the artifact"
                                    % (base, gf))
            blob = json.dumps(c, ensure_ascii=False)
            hit = pii.search(blob)
            if hit:
                problems.append("%s: PII marker %r in case" % (base, hit.group(0)))
            if exp in REJECT_LABELS:
                traps += 1
            elif exp == "PASS":
                goods += 1
        per_dir[name] = {"files": len(files), "traps": traps, "goods": goods}
        # A one-sided suite measures only one direction -- the all-trap lesson.
        if files and (traps == 0 or goods == 0):
            problems.append("%s: one-sided suite (traps=%d goods=%d) -- needs BOTH"
                            % (name, traps, goods))
    return (len(problems) == 0), {"problems": problems, "per_dir": per_dir}


def lint_toplevel_cases(case_dir=None):
    """Per-target schema lint for TOP-LEVEL evals/cases/*.json (spec AC-C2 — the
    top-level corpus was previously unlinted). Subdirectories are never scanned
    here. Returns (ok, report)."""
    case_dir = case_dir or os.path.join(THIS_DIR, "cases")
    pii = pii_pattern()
    problems = []
    files = sorted(glob.glob(os.path.join(case_dir, "*.json")))
    for fp in files:
        base = os.path.basename(fp)
        try:
            with open(fp, encoding="utf-8") as fh:
                c = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            problems.append("%s: invalid JSON (%s)" % (base, e))
            continue
        tgt = c.get("target")
        if tgt not in TOPLEVEL_SCHEMAS:
            problems.append("%s: unknown target %r (known: %s)"
                            % (base, tgt, "/".join(sorted(TOPLEVEL_SCHEMAS))))
            continue
        for k in ("id", "expected"):
            if not c.get(k):
                problems.append("%s: missing/empty required field %r" % (base, k))
        for k in TOPLEVEL_SCHEMAS[tgt]:
            # PRESENCE check, not truthiness: an empty-but-present value can be
            # load-bearing (artifacts={} IS the unsourced-authority trap).
            if k not in c:
                problems.append("%s: missing required field %r for target %r"
                                % (base, k, tgt))
        if c.get("expected") not in LABELS:
            problems.append("%s: bad expected label %r" % (base, c.get("expected")))
        hit = pii.search(json.dumps(c, ensure_ascii=False))
        if hit:
            problems.append("%s: PII marker %r in case" % (base, hit.group(0)))
    return (len(problems) == 0), {"problems": problems, "files": len(files)}


def red_team_keeplogic():
    """Re-run the adversarial-loop keep-logic guards (the probes proven inline):
    a mislabeled-gold candidate can't reach kept_confirmed; a FALSE-PASS verdict
    on a FAIL-gold trap is NOT scored as the verifier being wrong; an unparsed
    (None) judge verdict does not confirm gold."""
    import adversarial_loop as al
    probes = []

    def mapped(m):
        def fn(case):
            for k, v in m.items():
                if k in case["artifact"]:
                    return v
            return None
        return fn

    # 1. mislabeled gold (judge disagrees with proposed) -> never kept
    rep = al.run_round([{"id": "m", "expected": "FAIL", "artifact": "Q",
                         "objective_fact": "1"}], mapped({"Q": "PASS"}), mapped({"Q": "PASS"}))
    probes.append(("mislabeled-not-kept",
                   rep["rows"][0]["bucket"] == "gold_unconfirmed" and rep["kept"] == 0))

    # 2. FALSE-PASS on a FAIL-gold trap == rejection -> verifier not wrong
    rep = al.run_round([{"id": "t", "expected": "FAIL", "artifact": "Q",
                         "objective_fact": "1"}], mapped({"Q": "FAIL"}), mapped({"Q": "FALSE-PASS"}))
    probes.append(("falsepass-collapses-to-reject",
                   rep["rows"][0]["bucket"] == "verifier_correct"
                   and rep["rows"][0]["verifier_wrong"] is False))

    # 3. None judge verdict doesn't confirm gold
    rep = al.run_round([{"id": "n", "expected": "FAIL", "artifact": "Q",
                         "objective_fact": "1"}], mapped({}), mapped({"Q": "PASS"}))
    probes.append(("none-judge-no-confirm",
                   rep["rows"][0]["gold_confirmed"] is False))

    ok = all(p for _, p in probes)
    return ok, {"probes": probes}


def eval_suite_green():
    """run_evals must be GREEN (every frozen gate-hole still caught)."""
    import run_evals
    rep = run_evals.run_suite()
    c = rep["counts"]
    return rep["green"], {"green": rep["green"], "missed": c["missed"],
                          "regression": c["regression"], "error": c["error"],
                          "caught": c["caught"]}


def pytest_sweep():
    """Full pytest sweep over evals/ optimize/ harness/ -- 0 failures required.
    Bounded by timeout= so a hung test can't hang the deterministic layer itself
    (this very call was the operational_invariants() sweep's first finding).
    Excludes tests marked `slow` (e.g. harness/test_verify_node.py's
    VAC1RealPadsplitRepo, which shells out to `npx vitest run` against the real
    external padsplit-cockpit/web repo and can run for a long time with output
    captured rather than streamed -- indistinguishable from a hang from inside
    this sweep). Those tests remain runnable on demand via `-m slow`."""
    try:
        p = subprocess.run(
            [sys.executable, "-m", "pytest", "evals", "optimize", "harness", "-q",
             "-m", "not slow"],
            cwd=LOOPTEAM_DIR, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        return False, {"returncode": -1, "summary": "pytest sweep TIMED OUT (>600s)"}
    tail = (p.stdout or p.stderr).strip().splitlines()[-1:] or [""]
    return p.returncode == 0, {"returncode": p.returncode, "summary": tail[-1]}


# --- Operational invariants (the resilience RULE made an enforced CHECK) ------
# The 529 retry-storm slipped through because the project only ever tested the
# ARTIFACTS the loop produces, never the loop's own runtime conduct. These are
# grep-style source checks (same precedent as hooks/loop_stop_guard.py) that turn
# the resilience rules into something that can say NO: a future unwrapped live
# call or timeout-less subprocess is caught automatically.
# Live-call shapes (any new provider must be added here, or an unwrapped call to it
# silently bypasses the resilience gate -- the flywheel: adding OpenAI surfaced the
# chat.completions.create + OpenAI( invariants).
_RE_LIVE_CALL = re.compile(r"\.messages\.create\s*\(|\.chat\.completions\.create\s*\(")
_RE_CLIENT_CTOR = re.compile(r"anthropic\.Anthropic\s*\(|\bOpenAI\s*\(")
_RE_SUBPROC = re.compile(r"subprocess\.run\s*\(")
_RE_MAX_RETRIES0 = re.compile(r"max_retries\s*=\s*0")
_RE_TIMEOUT = re.compile(r"timeout\s*=")


_RE_STRINGS = re.compile(
    r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')


def _strip_strings_comments(src):
    """Blank string-literal and comment CONTENT (preserving length, so offsets
    stay valid) before scanning -- so a `messages.create(` mentioned inside a
    docstring/example is NOT a violation. Strings first, then # comments."""
    src = _RE_STRINGS.sub(lambda m: " " * len(m.group(0)), src)
    src = re.sub(r"#[^\n]*", lambda m: " " * len(m.group(0)), src)
    return src


def _balanced_call(src, open_paren_idx):
    """Substring from a '(' to its matching ')' -- one call's args even across lines."""
    depth = 0
    for i in range(open_paren_idx, len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                return src[open_paren_idx:i + 1]
    return src[open_paren_idx:]


def _top_level_args(call_text):
    """Mask anything nested DEEPER than this call's own arg list, so a kwarg that
    belongs to a NESTED call (e.g. an inner subprocess.run(..., timeout=5)) is not
    mistaken for the outer call's. `call_text` is a balanced '(' .. ')' slice."""
    out = []
    depth = 0
    for ch in call_text:
        if ch == "(":
            depth += 1
            out.append(" ")
        elif ch == ")":
            depth -= 1
            out.append(" ")
        else:
            out.append(ch if depth == 1 else " ")
    return "".join(out)


def scan_source_invariants(rel, src):
    """Check one source file's text for operational-resilience violations. Pure
    (no I/O) so tests can feed it crafted snippets. Scans CODE only (strings and
    comments blanked) and inspects only each call's TOP-LEVEL args (nested calls
    masked). Returns a list of problems."""
    s = _strip_strings_comments(src)
    problems = []
    # (a) a live messages.create must sit near a call_with_retry (the _call ->
    #     call_with_retry(_call) wrapper pattern). Proximity-based, like the hooks.
    for m in _RE_LIVE_CALL.finditer(s):
        lo, hi = max(0, m.start() - 700), m.end() + 700
        if "call_with_retry" not in s[lo:hi]:
            problems.append("%s: live LLM call (%s) not wrapped in call_with_retry"
                            % (rel, m.group(0).strip()))
    # (b) every LLM client ctor (anthropic.Anthropic / OpenAI) must set
    #     max_retries=0 in THAT call.
    for m in _RE_CLIENT_CTOR.finditer(s):
        args = _top_level_args(_balanced_call(s, m.end() - 1))
        if not _RE_MAX_RETRIES0.search(args):
            problems.append("%s: LLM client ctor (%s) without max_retries=0"
                            % (rel, m.group(0).strip()))
    # (c) every subprocess.run(...) must pass a timeout= at ITS OWN arg level
    #     (a nested call's timeout= must NOT satisfy the outer call).
    for m in _RE_SUBPROC.finditer(s):
        args = _top_level_args(_balanced_call(s, m.end() - 1))
        if not _RE_TIMEOUT.search(args):
            problems.append("%s: subprocess.run( without timeout=" % rel)
    return problems


def operational_invariants(root=LOOPTEAM_DIR):
    """Scan the loop-team Python source for resilience-rule violations. Skips test
    files (they legitimately stub these patterns to prove the check discriminates),
    the _shims, and this scanner file itself (it defines the patterns -> would
    self-match), mirroring how loop_stop_guard / pii-guard exclude themselves."""
    problems = []
    scanned = 0
    me = os.path.abspath(__file__)
    for py in sorted(glob.glob(os.path.join(root, "**", "*.py"), recursive=True)):
        base = os.path.basename(py)
        if base.startswith("test_") or os.sep + "_shims" + os.sep in py \
                or os.path.abspath(py) == me:
            continue
        try:
            with open(py, encoding="utf-8") as fh:
                src = fh.read()
        except OSError as e:
            problems.append("%s: unreadable (%s)" % (py, e))
            continue
        scanned += 1
        problems.extend(scan_source_invariants(os.path.relpath(py, root), src))
    return (len(problems) == 0), {"problems": problems, "scanned": scanned}


# --- Reasoning-capture invariant (a verdict is never consumed without its 'why') --
# The decision/measurement modules must obtain verdicts via run_role_explained /
# make_explained_judge (reasoning retained, self-correction surfaced), NEVER a bare
# run_role/make_role_judge. This is the structural enforcement of the lesson that
# cost hours: a self-corrected verdict read as a bare label sent the loop in circles.
DECISION_MODULES = ("evals/meta_validate.py", "evals/adversarial_loop.py")
_RE_BARE_RUNROLE = re.compile(r"\brun_role\s*\(")        # NOT run_role_explained(
_RE_BARE_JUDGE = re.compile(r"\bmake_role_judge\s*\(")    # NOT make_explained_judge(


def _scan_decision_source(rel, src):
    """Pure check (testable on crafted snippets): one decision module's source must
    capture reasoning and use no bare verdict path. Returns a list of problems."""
    s = _strip_strings_comments(src)  # ignore prose mentions in docstrings/comments
    problems = []
    if "run_role_explained" not in s and "make_explained_judge" not in s:
        problems.append("%s: does not capture reasoning "
                        "(no run_role_explained / make_explained_judge)" % rel)
    if _RE_BARE_RUNROLE.search(s):
        problems.append("%s: bare run_role( in a decision path -- use run_role_explained" % rel)
    if _RE_BARE_JUDGE.search(s):
        problems.append("%s: bare make_role_judge( in a decision path -- use make_explained_judge" % rel)
    return problems


def reasoning_capture_invariant(root=LOOPTEAM_DIR):
    """Decision modules must CAPTURE reasoning, never act on a bare verdict."""
    problems = []
    for rel in DECISION_MODULES:
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                src = f.read()
        except OSError as e:
            problems.append("%s: unreadable (%s)" % (rel, e))
            continue
        problems.extend(_scan_decision_source(rel, src))
    return (len(problems) == 0), {"problems": problems, "modules": list(DECISION_MODULES)}


def run_all(do_pytest=True):
    checks = []
    ok_lint, r_lint = lint_cases()
    checks.append(("case-lint", ok_lint, r_lint))
    ok_tl, r_tl = lint_toplevel_cases()
    checks.append(("case-lint top-level", ok_tl, r_tl))
    ok_rt, r_rt = red_team_keeplogic()
    checks.append(("red-team keep-logic", ok_rt, r_rt))
    ok_oi, r_oi = operational_invariants()
    checks.append(("operational invariants", ok_oi, r_oi))
    ok_rc, r_rc = reasoning_capture_invariant()
    checks.append(("reasoning-capture", ok_rc, r_rc))
    ok_green, r_green = eval_suite_green()
    checks.append(("run_evals GREEN", ok_green, r_green))
    if do_pytest:
        ok_pt, r_pt = pytest_sweep()
        checks.append(("pytest sweep", ok_pt, r_pt))
    overall = all(ok for _, ok, _ in checks)
    return overall, checks


def _log_checks(checks):
    """Emit one structured line per check: PASS -> INFO, FAIL -> WARNING. Writes
    to stderr and, when LOOP_LOG_DIR is set, to <LOOP_LOG_DIR>/log.jsonl too.
    Never touches stdout; never raises (the logger swallows its own errors)."""
    if get_logger is None:
        return
    log_dir = os.environ.get("LOOP_LOG_DIR") or None
    lg = get_logger("verify_build", run_dir=log_dir)
    for name, ok, detail in checks:
        problems = []
        if isinstance(detail, dict):
            problems = detail.get("problems") or []
        if ok:
            lg.info("check", check=name, ok=True)
        else:
            lg.warning("check FAIL", check=name, ok=False, problems=problems[:20])


def print_report(overall, checks):
    # Structured logging runs alongside the stdout report; on an all-pass run it
    # emits only INFO lines (no WARNING/ERROR), per the contract.
    _log_checks(checks)
    print("Loop Team -- Deterministic meta-verification (Layer 1, zero-API)")
    print("=" * 64)
    for name, ok, detail in checks:
        print("  [%s] %s" % ("OK" if ok else "XX", name))
        if name == "case-lint":
            for d, s in detail["per_dir"].items():
                print("        %-22s files=%-3d traps=%-3d goods=%-3d"
                      % (d, s["files"], s["traps"], s["goods"]))
            for p in detail["problems"]:
                print("        !! %s" % p)
        elif name == "red-team keep-logic":
            for pname, pok in detail["probes"]:
                print("        %s %s" % ("ok " if pok else "XX ", pname))
        elif name == "operational invariants":
            print("        scanned %d source file(s): live-calls-wrapped, "
                  "max_retries=0, subprocess timeouts" % detail["scanned"])
            for p in detail["problems"]:
                print("        !! %s" % p)
        elif name == "reasoning-capture":
            print("        decision modules capture reasoning (run_role_explained / "
                  "make_explained_judge): %s" % ", ".join(detail["modules"]))
            for p in detail["problems"]:
                print("        !! %s" % p)
        elif name == "run_evals GREEN":
            print("        caught=%d missed=%d regression=%d error=%d"
                  % (detail["caught"], detail["missed"], detail["regression"], detail["error"]))
        elif name == "pytest sweep":
            print("        %s" % detail["summary"])
    print("-" * 64)
    print("  LAYER-1 VERDICT: %s" % ("PASS" if overall else "FAIL"))


def main():
    do_pytest = "--no-pytest" not in sys.argv
    overall, checks = run_all(do_pytest=do_pytest)
    print_report(overall, checks)
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
