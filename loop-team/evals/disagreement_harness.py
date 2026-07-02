#!/usr/bin/env python3
"""Loop Team -- cross-family DISAGREEMENT-MINING harness (hard-case discovery).

A frozen eval suite only measures the failure modes someone already thought to
write down. This harness MINES for the next ones: it runs TWO judges of disjoint
model families over a pool of cases --

  * the cross-family OpenAI judge (via meta_validate.build_live_judge('openai', M)
    / optimize.llm.openai_llm), and
  * the Anthropic verifier (meta_validate.build_live_judge('anthropic', M)),

both on the SAME role prompt (roles/verifier.md by default) and the SAME artifact
text -- and records every case where the two verdicts DISAGREE. A disagreement is a
high-value signal: at least one strong judge is wrong on it, so it is exactly the
kind of case worth resolving by hand and freezing into the regression suite. The
output is a JSON list of candidate hard cases, each flagged `needs_human_gold:
true` -- the harness deliberately does NOT pick a winner (that's the human's job;
auto-resolving with a third model just reintroduces the circularity this is meant
to break).

Verdicts are read with the project's own reasoning-capturing path
(role_runner.run_role_explained) so a disagreement always carries BOTH judges' raw
reasoning -- you never resolve a disagreement without reading why each side ruled
as it did (the lesson that cost hours). Self-correction is surfaced per judge.

WHY two families: an all-Anthropic panel fails in correlated ways (self-preference
/ EPC collapse); a disjoint OpenAI family gives true Panel-of-LLM-Judges diversity,
so a cross-family disagreement is a genuine signal, not two correlated guesses.

------------------------------------------------------------------------------
LIVE MODE needs keys:
  ANTHROPIC_API_KEY                       (the Anthropic verifier)
  OPENAI_API_KEY  +  --openai-model M     (the cross-family OpenAI judge)
    e.g.  OPENAI_API_KEY=$(cat ~/.config/openai/key) \
          python3 disagreement_harness.py --openai-model gpt-4o-mini \
                  --anthropic-model claude-haiku-4-5-20251001 \
                  --pool cases --out hard_candidates.json

SELFTEST (no keys, no network) -- proves the disagreement-detection logic:
    python3 disagreement_harness.py --selftest

Importing this module performs NO network or key access; the live judges are built
lazily only when a live run is requested. Mirrors meta_validate / optimize.llm.
------------------------------------------------------------------------------
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# The harness reuses the repo's optimize/llm + role_runner + meta_validate. It can
# live either inside the live suite (loop-team/evals) or in this staging dir; in
# the latter case we resolve the repo by walking up to a loop-team/ that has the
# modules. Resolution is best-effort and only matters for a LIVE run -- --selftest
# stubs the judges and needs only role_runner + a role prompt.
def _find_repo_evals():
    """Return (evals_dir, optimize_dir, roles_dir) for the loop-team checkout, or
    (None, None, None) if not found. Tries: this dir is the live evals dir; else an
    env override LOOP_TEAM_DIR; else a few likely relative locations."""
    candidates = []
    # (a) running from inside loop-team/evals
    candidates.append(HERE)
    # (b) explicit override
    env = os.environ.get("LOOP_TEAM_DIR")
    if env:
        candidates.append(os.path.join(env, "evals"))
    # (c) common checkout layouts relative to a staging dir
    for up in ("..", "../..", "../../..", "../../../.."):
        candidates.append(os.path.join(HERE, up, "loop-team", "evals"))
        candidates.append(os.path.join(HERE, up, "loop", "loop-team", "evals"))
    for ev in candidates:
        ev = os.path.normpath(ev)
        opt = os.path.normpath(os.path.join(ev, "..", "optimize"))
        roles = os.path.normpath(os.path.join(ev, "..", "roles"))
        # meta_validate.py lives in evals/, role_runner.py + llm.py in optimize/.
        if os.path.isfile(os.path.join(ev, "meta_validate.py")) \
                and os.path.isfile(os.path.join(opt, "role_runner.py")):
            return ev, opt, roles
    return None, None, None


EVALS_DIR, OPTIMIZE_DIR, ROLES_DIR = _find_repo_evals()
if EVALS_DIR:
    sys.path.insert(0, EVALS_DIR)
if OPTIMIZE_DIR:
    sys.path.insert(0, OPTIMIZE_DIR)


def _import_role_runner():
    """Import role_runner (run_role_explained/parse_verdict). Raises a clear error
    if the repo wasn't found -- needed by BOTH live and selftest paths."""
    if not EVALS_DIR and not OPTIMIZE_DIR:
        raise RuntimeError(
            "could not locate the loop-team checkout (role_runner.py). Set "
            "LOOP_TEAM_DIR=/path/to/loop-team or run from loop-team/evals/.")
    import role_runner  # noqa: E402
    return role_runner


# --- core: judge a pool with two judges, find disagreements -------------------

def judge_pool(cases, judge_a, judge_b, name_a="anthropic", name_b="openai",
               role_prompt=""):
    """Run two judges over `cases` and return a per-case row list.

    `judge_a` / `judge_b` are callables (case_artifact_dict, role_prompt) ->
    explained-result dict {verdict, raw, all_verdicts, self_corrected}. Each row
    records both verdicts and whether they DISAGREE. Pure: no I/O, no globals --
    so the selftest can feed scripted judges and assert the disagreement logic.

    Disagreement = the two parsed verdicts are not equal. An unparsed verdict
    (None) is preserved as its own value, so None vs a real verdict IS a
    disagreement (an unreadable judge is a problem worth surfacing, never silently
    treated as agreement)."""
    rows = []
    for c in cases:
        ra = judge_a(c, role_prompt)
        rb = judge_b(c, role_prompt)
        va, vb = ra.get("verdict"), rb.get("verdict")
        rows.append({
            "id": c.get("id", "<no-id>"),
            "artifact": c.get("artifact", ""),
            name_a: {"verdict": va, "reasoning": ra.get("raw", ""),
                     "self_corrected": ra.get("self_corrected", False)},
            name_b: {"verdict": vb, "reasoning": rb.get("raw", ""),
                     "self_corrected": rb.get("self_corrected", False)},
            "agree": va == vb,
            "disagree": va != vb,
            # An existing frozen label, if the pool case carries one, is kept only
            # as a hint for the human -- it is NOT used to resolve the disagreement
            # (that would just re-assert one side). Often absent for a mined case.
            "existing_expected": c.get("expected"),
        })
    return rows


def mine_disagreements(rows, name_a="anthropic", name_b="openai"):
    """From judged rows, emit the disagreements as candidate hard cases, each
    flagged for human gold-resolution. Returns a list ready to json.dump.

    Each candidate carries BOTH verdicts + BOTH reasonings (so the human resolves
    it from the actual 'why', never a bare label), an empty `expected` to be filled
    by the human, and `needs_human_gold: true`. The harness never picks a winner."""
    out = []
    for r in rows:
        if not r["disagree"]:
            continue
        out.append({
            "id": "mined-%s" % r["id"],
            "origin": "disagreement-mined %s vs %s -- both strong judges ran the "
                      "same artifact and DISAGREED; resolve by hand and freeze."
                      % (name_a, name_b),
            "target": "verifier",
            "requires": "judge",
            "needs_human_gold": True,
            "expected": None,            # <-- human fills this after resolving
            "artifact": r["artifact"],
            "judge_verdicts": {
                name_a: r[name_a]["verdict"],
                name_b: r[name_b]["verdict"],
            },
            "judge_reasoning": {
                name_a: r[name_a]["reasoning"],
                name_b: r[name_b]["reasoning"],
            },
            "self_corrected": {
                name_a: r[name_a]["self_corrected"],
                name_b: r[name_b]["self_corrected"],
            },
            "existing_expected_hint": r["existing_expected"],
            "resolution_note": "At least one of these judges is wrong. A human must "
                               "set `expected` to the correct verdict (PASS / FAIL / "
                               "FALSE-PASS) and remove needs_human_gold before this "
                               "becomes a frozen regression case.",
        })
    return out


def summarize(rows):
    n = len(rows)
    dis = sum(1 for r in rows if r["disagree"])
    return {"pool_size": n, "agreements": n - dis, "disagreements": dis,
            "disagreement_rate": (dis / n) if n else 0.0}


# --- pool loading -------------------------------------------------------------

def load_pool(path):
    """Load cases from a dir of *.json or a single .json file. Only role-level
    artifacts (those with an `artifact` string) are usable by a text judge; others
    are skipped with a note."""
    files = []
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "*.json")))
    elif os.path.isfile(path):
        files = [path]
    cases, skipped = [], []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as fh:
                c = json.load(fh)
        except (OSError, json.JSONDecodeError) as e:
            skipped.append((os.path.basename(fp), "unreadable: %s" % e))
            continue
        if isinstance(c, list):           # a candidates bundle file
            for sub in c:
                (cases if sub.get("artifact") else skipped).append(
                    sub if sub.get("artifact") else (sub.get("id", "?"), "no artifact"))
            continue
        if c.get("artifact"):
            cases.append(c)
        else:
            skipped.append((c.get("id", os.path.basename(fp)), "no artifact text"))
    return cases, skipped


# --- live judge adapters (built lazily; need keys) ----------------------------

def _build_explained_judge(llm):
    """Wrap a raw llm callable into an explained-judge(case, role_prompt) using the
    repo's reasoning-capturing run_role_explained (so both reasonings are retained
    and self-correction is surfaced)."""
    role_runner = _import_role_runner()

    def judge(case, role_prompt):
        synthetic = {"artifact": case.get("artifact", "")}
        return role_runner.run_role_explained(llm, role_prompt, synthetic)
    return judge


def build_live_judges(anthropic_model, openai_model):
    """Build (anthropic_judge, openai_judge) live judges. Keys are read here, not at
    import. Routes through meta_validate.build_live_judge -> optimize.llm, so both
    go through call_with_retry with client max_retries=0 (single retry source)."""
    import meta_validate  # noqa: E402  (resolved via EVALS_DIR on sys.path)
    a_llm = meta_validate.build_live_judge(anthropic_model, provider="anthropic")
    o_llm = meta_validate.build_live_judge(openai_model, provider="openai")
    return _build_explained_judge(a_llm), _build_explained_judge(o_llm)


def load_role_prompt(role="verifier.md"):
    if not ROLES_DIR:
        raise RuntimeError("could not locate roles/ -- set LOOP_TEAM_DIR")
    with open(os.path.join(ROLES_DIR, role), encoding="utf-8") as f:
        return f.read()


def run_live(args):
    cases, skipped = load_pool(args.pool)
    if not cases:
        raise SystemExit("no usable (artifact-bearing) cases in pool %r" % args.pool)
    role_prompt = load_role_prompt(args.role)
    a_judge, o_judge = build_live_judges(args.anthropic_model, args.openai_model)
    rows = judge_pool(cases, a_judge, o_judge,
                      name_a="anthropic", name_b="openai", role_prompt=role_prompt)
    candidates = mine_disagreements(rows, "anthropic", "openai")
    summary = summarize(rows)
    payload = {"summary": summary, "skipped": skipped, "candidates": candidates}
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print("pool=%d  agreements=%d  DISAGREEMENTS=%d (rate %.0f%%)  -> %d candidate "
          "hard case(s) written to %s"
          % (summary["pool_size"], summary["agreements"], summary["disagreements"],
             summary["disagreement_rate"] * 100, len(candidates), args.out))
    for c in candidates:
        print("  [DISAGREE] %-30s anthropic=%s openai=%s  needs_human_gold"
              % (c["id"], c["judge_verdicts"]["anthropic"],
                 c["judge_verdicts"]["openai"]))
    return 0


# --- selftest (FakeLLM, no keys) ---------------------------------------------
# Proves the disagreement-detection logic end to end with scripted judges: cases
# the two families agree on are NOT mined; cases they split on ARE mined, flagged
# needs_human_gold with both reasonings retained; a None (unparsed) verdict counts
# as a disagreement, never a silent agreement.

def _selftest():
    role_runner = _import_role_runner()
    from llm import FakeLLM  # noqa: E402  (optimize/llm.py)

    ok = True

    # A tiny pool: each artifact carries a token that the scripted judges key on.
    pool = [
        {"id": "agree-pass", "artifact": "TICKET-AGREE-PASS body"},
        {"id": "agree-fail", "artifact": "TICKET-AGREE-FAIL body"},
        {"id": "split-1", "artifact": "TICKET-SPLIT-ONE body"},
        {"id": "split-2", "artifact": "TICKET-SPLIT-TWO body"},
        {"id": "anthropic-unparsed", "artifact": "TICKET-NULL body"},
    ]

    # Anthropic-side FakeLLM: scripted by artifact substring -> a verdict line.
    a_llm = FakeLLM({
        "TICKET-AGREE-PASS": "VERDICT: PASS -- looks clean",
        "TICKET-AGREE-FAIL": "VERDICT: FAIL -- defect found",
        "TICKET-SPLIT-ONE":  "VERDICT: PASS -- I accept it",
        "TICKET-SPLIT-TWO":  "VERDICT: FALSE-PASS -- self-graded",
        "TICKET-NULL":       "I have no idea, no verdict here",  # -> parses to None
    })
    # OpenAI-side FakeLLM: AGREES on the two agree-cases, SPLITS on the two splits,
    # and gives a real verdict where the anthropic side was unparsable.
    o_llm = FakeLLM({
        "TICKET-AGREE-PASS": "VERDICT: PASS -- concur",
        "TICKET-AGREE-FAIL": "VERDICT: FAIL -- concur",
        "TICKET-SPLIT-ONE":  "VERDICT: FAIL -- I reject it",
        "TICKET-SPLIT-TWO":  "VERDICT: PASS -- I accept it",
        "TICKET-NULL":       "VERDICT: FAIL -- defect",
    })

    def mk(llm):
        def judge(case, role_prompt):
            return role_runner.run_role_explained(llm, role_prompt, case)
        return judge

    rows = judge_pool(pool, mk(a_llm), mk(o_llm),
                      name_a="anthropic", name_b="openai", role_prompt="ROLE")
    summary = summarize(rows)
    candidates = mine_disagreements(rows, "anthropic", "openai")

    print("== disagreement-harness selftest (FakeLLM, no keys) ==")
    print("  pool=%d agreements=%d disagreements=%d"
          % (summary["pool_size"], summary["agreements"], summary["disagreements"]))
    for r in rows:
        print("    %-20s anthropic=%-10s openai=%-10s  %s"
              % (r["id"], r["anthropic"]["verdict"], r["openai"]["verdict"],
                 "DISAGREE" if r["disagree"] else "agree"))

    by_id = {r["id"]: r for r in rows}
    # 1. agreements are NOT mined
    ok = ok and by_id["agree-pass"]["agree"] and by_id["agree-fail"]["agree"]
    # 2. the two splits ARE disagreements
    ok = ok and by_id["split-1"]["disagree"] and by_id["split-2"]["disagree"]
    # 3. a None (unparsed) verdict vs a real verdict counts as a disagreement
    ok = ok and by_id["anthropic-unparsed"]["disagree"]
    ok = ok and by_id["anthropic-unparsed"]["anthropic"]["verdict"] is None
    # 4. exactly 3 candidates mined (split-1, split-2, anthropic-unparsed)
    ok = ok and summary["disagreements"] == 3 and len(candidates) == 3
    # 5. every mined candidate is flagged for human gold + retains BOTH reasonings
    for c in candidates:
        ok = ok and c["needs_human_gold"] is True and c["expected"] is None
        ok = ok and c["judge_reasoning"]["anthropic"] and c["judge_reasoning"]["openai"]
        ok = ok and set(c["judge_verdicts"]) == {"anthropic", "openai"}
    # 6. and that the mined set is exactly the disagreeing ids
    mined_ids = {c["id"] for c in candidates}
    ok = ok and mined_ids == {"mined-split-1", "mined-split-2",
                              "mined-anthropic-unparsed"}
    # 7. agreement cases never leak into the candidate set
    ok = ok and "mined-agree-pass" not in mined_ids

    # The emitted candidates must be valid JSON (they are the harness's product).
    try:
        json.loads(json.dumps({"candidates": candidates}))
    except (TypeError, ValueError):
        ok = False

    print("  mined candidates: %s" % ", ".join(sorted(mined_ids)))
    print("\nSELFTEST: %s" % ("OK" if ok else "FAIL"))
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true",
                    help="run the FakeLLM selftest (no keys/network)")
    ap.add_argument("--pool", default="cases",
                    help="dir of *.json cases (or a single .json) to mine")
    ap.add_argument("--out", default="hard_candidates.json",
                    help="where to write the mined disagreement candidates")
    ap.add_argument("--role", default="verifier.md",
                    help="role prompt both judges apply (roles/<role>)")
    ap.add_argument("--anthropic-model", default="claude-haiku-4-5-20251001",
                    help="Anthropic model for the verifier judge")
    ap.add_argument("--openai-model", default=None,
                    help="OpenAI model for the cross-family judge (REQUIRED live)")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(0 if _selftest() else 1)
    if not args.openai_model:
        ap.error("live mode needs --openai-model (+ OPENAI_API_KEY and "
                 "ANTHROPIC_API_KEY). For a no-key check, use --selftest.")
    sys.exit(run_live(args))


if __name__ == "__main__":
    main()
