#!/usr/bin/env python3
"""Loop Team -- Eval/Regression Suite runner (the verifier-for-the-verifier).

Replays each frozen case in evals/cases/*.json through the relevant role or
harness and compares the verdict to the case's `expected`. Prints a scorecard
that measures the gate as a REJECTOR: a "trap" case (expected FAIL/FALSE-PASS)
is a wrong artifact that the gate MUST reject; catching it is a true positive,
letting it through is a false-pass -- the project's deepest failure mode.

Zero third-party dependencies, matching harness/verify.py. Deterministic
`target: harness` cases run live against verify.py today. Role-level cases
(`requires: "judge"`) need an LLM-judge adapter (Phase-1 Sub-phase A4 / B) and
are listed as PENDING until one is supplied via --judge.

Usage:
    python run_evals.py                 # run the suite, print scorecard
    python run_evals.py --json          # machine-readable scorecard (for the gate/acceptor)
    python run_evals.py --harness PATH  # override verify.py (suite-validity "test the tests")
    python run_evals.py --judge MODULE  # supply a judge adapter for role-level cases

Exit code: 0 if the suite is GREEN (no missed / no regression / no error over
runnable cases), 1 otherwise, 2 on usage error.
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
CASES_DIR = os.path.join(EVALS_DIR, "cases")
FIXTURES_DIR = os.path.join(EVALS_DIR, "fixtures")
DEFAULT_HARNESS = os.path.normpath(os.path.join(EVALS_DIR, "..", "harness", "verify.py"))

# A verdict "rejects" the artifact when these expected labels are satisfied by NOT passing.
_REJECT_LABELS = ("FAIL", "FALSE-PASS")
# The only valid case labels; anything else in a case file is a defect, not a pass.
_KNOWN_LABELS = ("PASS", "FAIL", "FALSE-PASS")


def load_cases():
    cases = []
    for fn in sorted(os.listdir(CASES_DIR)):
        if fn.endswith(".json"):
            with open(os.path.join(CASES_DIR, fn), encoding="utf-8") as f:
                cases.append(json.load(f))
    return cases


NO_PYTEST_SHIM = os.path.join(EVALS_DIR, "_shims", "no_pytest")


def run_harness_case(case, harness):
    """Run a deterministic harness case through verify.py. Returns verdict dict."""
    fixture = os.path.join(FIXTURES_DIR, case["fixture"])
    if not os.path.isdir(fixture):
        return {"verdict": None, "error": "fixture not found: %s" % fixture}
    env = dict(os.environ)
    if case.get("hide_pytest"):
        # Force verify.py down the unittest path so the 0-test guard (not pytest's
        # exit-5) is the thing under test -- the actual H-LOOPTEAM-1 false-green.
        env["PYTHONPATH"] = NO_PYTEST_SHIM + os.pathsep + env.get("PYTHONPATH", "")
    try:
        p = subprocess.run([sys.executable, harness, fixture],
                           capture_output=True, text=True, timeout=600, env=env)
        result = json.loads(p.stdout)
    except Exception as e:  # noqa: BLE001 -- any harness failure is a case error
        return {"verdict": None, "error": "harness run failed: %s" % e}
    # passed=True -> "PASS"; passed=False -> "FAIL" (the gate rejected the artifact)
    return {"verdict": "PASS" if result.get("passed") else "FAIL",
            "summary": result.get("summary", "")}


def run_recorded_fetch_case(case):
    """Lane C-min: deterministic execution against a RECORDED snapshot. Compares the
    report's stated claims to the frozen `snapshot` in code (no LLM, no network).
    Returns a verdict dict like run_harness_case."""
    if not case.get("snapshot"):
        return {"verdict": None, "error": "recorded_fetch case missing 'snapshot'"}
    import recorded_fetch_check
    verdict, reasons = recorded_fetch_check.check_report(case)
    return {"verdict": verdict, "summary": "; ".join(reasons)}


def run_citation_grounding_case(case):
    """Deterministic citation-authority check. Validates a model's structured claim
    records against retrieved artifact metadata/excerpts, with no LLM and no network."""
    if "artifacts" not in case:
        return {"verdict": None, "error": "citation_grounding case missing 'artifacts'"}
    if "model_output" not in case:
        return {"verdict": None, "error": "citation_grounding case missing 'model_output'"}
    import citation_grounding
    return citation_grounding.check_case(case)


def load_judge(spec):
    """Load an optional judge adapter exposing judge(case) -> 'PASS'|'FAIL'|'FALSE-PASS'."""
    if not spec:
        return None
    sp = importlib.util.spec_from_file_location("loop_eval_judge", spec)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    if not hasattr(mod, "judge"):
        raise SystemExit("judge adapter %s must expose judge(case) -> verdict" % spec)
    return mod.judge


def classify(expected, verdict):
    """Map (expected, verdict) onto a scorecard bucket.

    Trap cases (expected rejects): catching == reject correctly; miss == false-pass.
    Good cases (expected PASS): pass == ok; fail == regression (false alarm).

    Raises ValueError on an unknown `expected` label. A typo'd label (e.g.
    'false-pass', 'Fail') must NOT silently fall through to the good-case branch
    and turn a missed trap into a green pass -- the caller buckets that as `error`.
    """
    if expected not in _KNOWN_LABELS:
        raise ValueError("unknown expected label %r (must be one of %s)"
                         % (expected, ", ".join(_KNOWN_LABELS)))
    is_trap = expected in _REJECT_LABELS
    rejected = verdict in _REJECT_LABELS or verdict == "FAIL"
    if is_trap:
        return "caught" if rejected else "missed"
    # expected == PASS
    return "ok" if verdict == "PASS" else "regression"


def run_slop_metrics_case(case):
    """Deterministic erosion lane (spec AC-C1): recompute the slop-gate metrics
    on the embedded before/after code; a delta above the case threshold is a
    FALSE-PASS. radon unavailable -> {'pending': True} (bucketed like a missing
    judge, never an error -- SUITE GREEN stays machine-independent)."""
    import sys as _s
    _s.path.insert(0, os.path.normpath(os.path.join(EVALS_DIR, "..", "..", "hooks")))
    try:
        from slop_gate import erosion_metrics
        before = erosion_metrics(case["code_before"])
        after = erosion_metrics(case["code_after"])
    except ImportError as e:
        return {"verdict": None, "pending": True,
                "error": "slop metrics unavailable (%s)" % e}
    delta = after["erosion_mass_pct"] - before["erosion_mass_pct"]
    thr = float(case.get("max_erosion_delta_pp", 5.0))
    verdict = "FALSE-PASS" if delta > thr else "PASS"
    return {"verdict": verdict,
            "summary": "erosion %.1f%%->%.1f%% (delta %.1fpp, thr %.1f)"
                       % (before["erosion_mass_pct"], after["erosion_mass_pct"],
                          delta, thr)}


def _score_case(case, harness, judge):
    """Score one case into a row dict. May raise (missing keys / unknown label);
    run_suite isolates that into an `error` row so one bad file can't crash the
    suite or, worse, pass silently."""
    if case.get("requires") == "judge":
        if judge is None:
            return {"id": case["id"], "target": case["target"],
                    "expected": case["expected"], "bucket": "pending",
                    "verdict": None, "detail": "no judge adapter"}
        verdict, detail = judge(case), ""
        if verdict is None:
            # A judge that returns None is a BROKEN judge, not a PASS verdict --
            # bucket as error so it can never read as a missed trap (or a green).
            return {"id": case["id"], "target": case["target"],
                    "expected": case["expected"], "bucket": "error",
                    "verdict": None, "detail": "judge returned None"}
    elif case["target"] == "harness":
        res = run_harness_case(case, harness)
        if res["verdict"] is None:
            return {"id": case["id"], "target": "harness",
                    "expected": case["expected"], "bucket": "error",
                    "verdict": None, "detail": res["error"]}
        verdict, detail = res["verdict"], res.get("summary", "")
    elif case["target"] == "recorded_fetch":
        res = run_recorded_fetch_case(case)
        if res["verdict"] is None:
            return {"id": case["id"], "target": "recorded_fetch",
                    "expected": case["expected"], "bucket": "error",
                    "verdict": None, "detail": res["error"]}
        verdict, detail = res["verdict"], res.get("summary", "")
    elif case["target"] == "slop_metrics":
        res = run_slop_metrics_case(case)
        if res.get("pending"):
            return {"id": case["id"], "target": "slop_metrics",
                    "expected": case["expected"], "bucket": "pending",
                    "verdict": None, "detail": res["error"]}
        verdict, detail = res["verdict"], res.get("summary", "")
    elif case["target"] == "citation_grounding":
        res = run_citation_grounding_case(case)
        if res["verdict"] is None:
            return {"id": case["id"], "target": "citation_grounding",
                    "expected": case["expected"], "bucket": "error",
                    "verdict": None, "detail": res["error"]}
        verdict, detail = res["verdict"], res.get("summary", "")
    else:
        return {"id": case["id"], "target": case["target"],
                "expected": case["expected"], "bucket": "error",
                "verdict": None, "detail": "no runner for target"}
    bucket = classify(case["expected"], verdict)   # raises on unknown label
    return {"id": case["id"], "target": case["target"],
            "expected": case["expected"], "bucket": bucket,
            "verdict": verdict, "detail": detail}


def run_suite(harness=DEFAULT_HARNESS, judge_spec=None, judge=None, arith_guard=False):
    # judge may be supplied directly as a callable (e.g. the optimizer passing a
    # role-runner closure) or as a module path via judge_spec.
    if judge is None:
        judge = load_judge(judge_spec)
    # Opt-in two-layer judge: a deterministic arithmetic layer in front of the LLM
    # (a provably-wrong stated number -> FALSE-PASS without asking the model). OFF by
    # default so a measurement of the LLM prompt ALONE stays uncontaminated.
    if arith_guard and judge is not None:
        import arithmetic_check
        judge = arithmetic_check.guard_judge(judge)
    rows = []
    for case in load_cases():
        try:
            rows.append(_score_case(case, harness, judge))
        except Exception as e:  # noqa: BLE001 -- one malformed case must not crash the suite
            rows.append({"id": case.get("id", "<unknown>"),
                         "target": case.get("target"), "expected": case.get("expected"),
                         "bucket": "error", "verdict": None,
                         "detail": "case error: %s" % e})

    counts = {"caught": 0, "missed": 0, "ok": 0, "regression": 0,
              "pending": 0, "error": 0}
    for r in rows:
        counts[r["bucket"]] += 1
    traps = counts["caught"] + counts["missed"]
    false_pass_rate = counts["missed"] / traps if traps else 0.0
    runnable = counts["caught"] + counts["missed"] + counts["ok"] + counts["regression"]
    # GREEN requires at least one actually-runnable case: an empty or all-pending
    # suite proves nothing and must not read as green.
    green = (runnable > 0 and counts["missed"] == 0
             and counts["regression"] == 0 and counts["error"] == 0)
    return {
        "green": green,
        "counts": counts,
        "traps": traps,
        "caught_hole_rate": (counts["caught"] / traps) if traps else 1.0,
        "false_pass_rate": false_pass_rate,
        "rows": rows,
    }


def print_scorecard(report):
    c = report["counts"]
    print("Loop Team -- Eval/Regression Suite")
    print("=" * 52)
    for r in report["rows"]:
        mark = {"caught": "OK  caught", "ok": "OK  pass",
                "missed": "XX  MISSED(false-pass)", "regression": "XX  REGRESSION",
                "pending": "--  pending", "error": "!!  error"}[r["bucket"]]
        v = r["verdict"] or "-"
        print("  [%s] %-28s exp=%-10s got=%-10s %s"
              % (mark.split()[0], r["id"], r["expected"], v,
                 "" if r["bucket"] in ("caught", "ok") else mark))
    print("-" * 52)
    print("  traps: %d  caught: %d  MISSED(false-pass): %d"
          % (report["traps"], c["caught"], c["missed"]))
    print("  good-case regressions: %d   errors: %d   pending(judge): %d"
          % (c["regression"], c["error"], c["pending"]))
    print("  caught-hole rate: %.0f%%   false-pass rate: %.0f%%"
          % (report["caught_hole_rate"] * 100, report["false_pass_rate"] * 100))
    print("  SUITE: %s" % ("GREEN" if report["green"] else "RED"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--harness", default=DEFAULT_HARNESS,
                    help="path to verify.py (override for suite-validity checks)")
    ap.add_argument("--judge", default=None,
                    help="path to a judge adapter module exposing judge(case)")
    ap.add_argument("--json", action="store_true", help="emit JSON scorecard")
    ap.add_argument("--arith-guard", action="store_true",
                    help="wrap the judge with the deterministic arithmetic layer (two-layer verifier)")
    args = ap.parse_args()

    if args.arith_guard and not args.judge:
        print("note: --arith-guard has no effect without --judge (no judge to wrap)", file=sys.stderr)
    report = run_suite(harness=args.harness, judge_spec=args.judge, arith_guard=args.arith_guard)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_scorecard(report)
    sys.exit(0 if report["green"] else 1)


if __name__ == "__main__":
    main()
