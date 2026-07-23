#!/usr/bin/env python3
"""Resumable live-judge eval runner.

Run a batch of live model calls (judge N artifacts on M models) WITHOUT losing
work to a flaky API. The contract:

  - persist every verdict keyed by (model, case_id) AFTER each successful call;
  - on (re)start, LOAD what's already done and SKIP it;
  - SWEEP only the not-yet-done (model, case) pairs, repeating up to `max_sweeps`,
    sleeping longer when a whole sweep makes no progress (an outage) and shorter
    when it's progressing;
  - a call that fails its few quick retries stays MISSING (retried next sweep),
    never burned to a `None` row.

So a transient outage costs only wall-clock, never data: a 40-call batch can't come
back all-blank, and re-launching the same command continues from where it left off.

This is the per-BATCH complement to `optimize/llm.call_with_retry` (which bounds a
SINGLE call's retries). Use both: bounded per-call retry inside a resumable per-id
sweep. The live CLI builds judges via `meta_validate.build_live_judge`, so every
underlying call is already `call_with_retry`-wrapped (one retry source).

Library use (testable, no API):
    run_resumable(cases, judges, render, parse, out_path)
        cases  : list of {"id": ..., ...}
        judges : {model_name: callable(prompt)->str}   (raises on transient failure)
        render : callable(case)->prompt
        parse  : callable(raw)->verdict
    Returns {model: {id: row}}; writes {model: [rows]} JSON to out_path.

CLI:
    python3 resumable_runner.py --cases cases.json --role verifier.md \
        --models claude-sonnet-4-6,claude-opus-4-8 --out results.json
"""
import argparse
import json
import os
import sys
import time

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
OPT_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "optimize"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPT_DIR)


def load_done(out_path, models):
    """Load existing results as {model: {id: row}}, keeping only rows with a
    non-None verdict (a blank row is treated as not-yet-done, so it's retried)."""
    res = {m: {} for m in models}
    if os.path.exists(out_path):
        try:
            with open(out_path, encoding="utf-8") as f:
                old = json.load(f)
            for m in models:
                for r in old.get(m, []):
                    if isinstance(r, dict) and r.get("verdict") is not None and "id" in r:
                        res[m][r["id"]] = r
        except Exception:  # noqa: BLE001 -- a corrupt/partial file just means "redo"
            pass
    return res


def save(res, cases, models, out_path):
    """Persist as {model: [rows]} in `cases` order (only the rows we have)."""
    out = {m: [res[m][c["id"]] for c in cases if c["id"] in res[m]] for m in models}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)


def _missing(res, cases, models):
    return [(m, c) for m in models for c in cases if c["id"] not in res[m]]


def run_resumable(cases, judges, render, parse, out_path, *,
                  max_sweeps=14, per_call_retries=2, retry_sleep=8.0,
                  sweep_sleep=40.0, progress_sleep=10.0, sleep=time.sleep,
                  probe=None, log=lambda _s: None):
    """Resumably fill a verdict for every (model, case). Returns {model:{id:row}}.

    `sleep` is injectable so tests run instantly. A judge call that raises is
    attempted up to `per_call_retries` times within a sweep (that's the total
    attempt count, not N+1); if it still fails the pair stays missing and is
    retried on the next sweep (up to `max_sweeps`).

    `probe`: optional zero-arg callable doing one minimal real call. If given, a
    PREFLIGHT runs before any sweep — a PERMANENT block (out of credits / bad key /
    bad model) STOPS immediately with the actionable cause instead of spinning
    through `max_sweeps`. (This is the fix for the ~hour wasted on a credit-out.)"""
    models = list(judges)
    res = load_done(out_path, models)

    if probe is not None and _missing(res, cases, models):
        import preflight as _pf  # imported only when a probe is supplied (truly optional)
        pf = _pf.preflight(probe)
        if _pf.is_permanent(pf["category"]):
            log("PREFLIGHT BLOCKED [%s]: %s" % (pf["category"], pf["action"]))
            return res  # do NOT sweep — a retry can't fix a permanent block

    def try_once(judge, prompt):
        for _ in range(per_call_retries):
            try:
                return judge(prompt)
            except Exception:  # noqa: BLE001 -- transient; retry, then leave missing
                sleep(retry_sleep)
        return None

    for sweep in range(max_sweeps):
        todo = _missing(res, cases, models)
        if not todo:
            log("all done after sweep %d" % sweep)
            break
        log("sweep %d: %d remaining" % (sweep, len(todo)))
        progressed = False
        for m, c in todo:
            raw = try_once(judges[m], render(c))
            if raw is not None:
                row = {"id": c["id"], "verdict": parse(raw), "raw": raw}
                for k in ("expected", "domain"):
                    if k in c:
                        row[k] = c[k]
                res[m][c["id"]] = row
                progressed = True
                save(res, cases, models, out_path)  # persist after EVERY call
        if _missing(res, cases, models):
            sleep(progress_sleep if progressed else sweep_sleep)
    save(res, cases, models, out_path)
    return res


def _live_main(args):
    import meta_validate as mv
    import role_runner
    with open(args.cases, encoding="utf-8") as f:
        cases = json.load(f)
    role_prompt = mv.load_role(args.role)
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    judges = {m: mv.build_live_judge(m, provider=args.provider) for m in models}
    render = lambda c: role_runner.build_prompt(role_prompt, {"artifact": c.get("artifact", "")})  # noqa: E731
    res = run_resumable(
        cases, judges,
        render=render,
        parse=role_runner.parse_verdict,
        out_path=args.out,
        # one cheap real call up front: a credit-out / bad-key stops us in seconds.
        probe=lambda: judges[models[0]](render({"artifact": "ping: 1BR under cap, whole unit."})),
        log=lambda s: print(s, flush=True),
    )
    filled = sum(len(res[m]) for m in models)
    print("FINISHED: %d/%d filled" % (filled, len(cases) * len(models)))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Resumable live-judge eval runner")
    ap.add_argument("--cases", required=True, help="JSON list of cases (each with id + artifact)")
    ap.add_argument("--role", default="verifier.md", help="role file under roles/ to load")
    ap.add_argument("--models", default="claude-sonnet-4-6", help="comma-separated model ids")
    ap.add_argument("--provider", default="anthropic")
    ap.add_argument("--out", required=True, help="results JSON path (resumed if it exists)")
    sys.exit(_live_main(ap.parse_args()))


if __name__ == "__main__":
    main()
