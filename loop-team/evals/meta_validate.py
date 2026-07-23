#!/usr/bin/env python3
"""Loop Team -- META-VERIFIER validation (make verification genuinely independent).

Part 1 of the adversarial hard-case plan. The problem it solves: our "independent
verifier" sub-agents are independent in CONTEXT (fresh, no shared reasoning) but
run on the SAME model family as the thing they grade -- and a model judging a
model's judgment is exactly the self-preference / EPC-collapse risk. We built the
MVVP math (judge_validate.py) and never applied it to the meta-verification. This
module applies it.

THE TRICK that dissolves the circularity -- OBJECTIVE-FACT GOLD as the calibration
anchor. The objective cases (evals/cases/objective/*.json) have verdicts that are
incontestable ARITHMETIC: $47k base < $55k floor -> FAIL; $30/hr*2080 >= $55k ->
PASS; a deposit copied into the rent field -> FAIL; "Present" with a concrete end
date -> FAIL. On these, cheating is impossible -- there is a right answer a
calculator agrees with. A judge that agrees with arithmetic truth (kappa >= 0.60,
position-flip <= 0.10, test-retest > 0.95) has EARNED trust on cases where it
cannot fake it. Only such a validated judge is then allowed to rule on the
judgment-call cases (Part 2), where its error would be invisible.

THREE DISTINCT ROLES, never one model judging itself:
  - case author       : the human (these frozen objective cases) -- NOT a model.
  - verifier-under-test: roles/verifier.md -- the thing whose quality we measure.
  - gold judge         : roles/gold_judge.md -- this independent fact-checker,
                          run on a DIFFERENT model, validated here before trust.

PANEL + position-swap: we run >= 2 models and, for each, audit order-invariance by
re-judging every artifact with its two key facts presented in swapped order. With
only an Anthropic key the panel is Haiku + Sonnet -- same family, so this is
PARTIAL independence (a true PoLL needs a cross-family key); we state that limit
honestly rather than claim more than we have. An EPC monitor reports verdict
concentration and inter-judge agreement so panel collapse is visible as the suite
grows into judgment cases.

CLI:
    python3 meta_validate.py --selftest     # FakeLLM, no key -- exercises the glue
    python3 meta_validate.py --live         # Haiku+Sonnet panel vs the objective gold
"""
import json
import os
import sys

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
OBJECTIVE_DIR = os.path.join(EVALS_DIR, "cases", "objective")
ROLES_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "roles"))
OPTIMIZE_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "optimize"))

sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPTIMIZE_DIR)

import judge_validate as jv          # noqa: E402  -- the MVVP math (kappa/flip/retest)
import role_runner                   # noqa: E402  -- build_prompt/parse_verdict/run_role


def load_objective_cases():
    """Load the objective-fact gold cases (the incontestable calibration anchor)."""
    cases = []
    if not os.path.isdir(OBJECTIVE_DIR):
        return cases
    for fn in sorted(os.listdir(OBJECTIVE_DIR)):
        if fn.endswith(".json"):
            with open(os.path.join(OBJECTIVE_DIR, fn), encoding="utf-8") as f:
                cases.append(json.load(f))
    return cases


def load_role(name):
    with open(os.path.join(ROLES_DIR, name), encoding="utf-8") as f:
        return f.read()


def run_judge_pass(llm, role_prompt, cases, key="artifact"):
    """Run a judge over each case once; return a list of EXPLAINED results
    (parallel to cases) -- {verdict, raw, all_verdicts, self_corrected}, NOT a bare
    verdict. Reasoning is retained so a disagreement's 'why' is always legible and
    self-correction is never silently parsed (the bug that manufactured a fake
    blind spot). `key` selects the framing ("artifact" forward / "artifact_swapped"
    swap). The judge sees ONLY the chosen artifact text (build_prompt never leaks
    the gold-side fields)."""
    out = []
    for c in cases:
        synthetic = {"artifact": c.get(key, c.get("artifact", ""))}
        out.append(role_runner.run_role_explained(llm, role_prompt, synthetic))
    return out


def _collapse(v):
    """Collapse a 3-label verdict to the accept/reject binary.

    The objective-fact anchor is incontestable about ONE thing: should a
    calculator-checkable artifact be ACCEPTED or REJECTED? ($47k < $55k -> reject;
    rent over cap -> reject; deposit-in-rent-field -> reject; above-floor -> accept).
    Whether a rejection is labeled FAIL vs FALSE-PASS is itself a judgment, NOT an
    arithmetic fact -- and the project's own run_evals.classify already treats both
    as equivalent rejections. So the objective anchor is scored on this binary;
    the reject-label nuance is validated separately on the judgment cases (Part 2).
    An unparsed verdict (None) stays None so it counts as disagreement, not a
    silent accept."""
    if v == "PASS":
        return "ACCEPT"
    if v in ("FAIL", "FALSE-PASS"):
        return "REJECT"
    return v  # None / unparsed -- preserved as its own (disagreeing) label


def _collapse_list(vs):
    return [_collapse(v) for v in vs]


def validate_judge_on_objective(llm, role_prompt, cases):
    """MVVP-validate one judge against the objective-fact gold.

    Runs three passes -- forward, retest (forward again), swapped (facts reordered).
    Certification is scored on the ACCEPT/REJECT binary (the incontestable claim);
    the raw 3-label verdicts and a 3-label MVVP report are kept for transparency
    so the reject-label nuance is visible, not hidden.

    Returns (report, raw): `report` is the accept/reject MVVP report used for
    certification; `raw` holds per-pass verdicts + `report_3label`."""
    gold = [c["expected"] for c in cases]
    fwd_ex = run_judge_pass(llm, role_prompt, cases, "artifact")
    rt_ex = run_judge_pass(llm, role_prompt, cases, "artifact")
    sw_ex = run_judge_pass(llm, role_prompt, cases, "artifact_swapped")
    # Extract verdicts for the math; KEEP the explained results (raw reasoning +
    # self-correction) so a disagreement's 'why' is legible and instability surfaced.
    forward = [r["verdict"] for r in fwd_ex]
    retest = [r["verdict"] for r in rt_ex]
    swapped = [r["verdict"] for r in sw_ex]
    self_corrected = sum(1 for r in fwd_ex if r["self_corrected"])
    # 3-label diagnostics (reject-label nuance) -- reported, not gated.
    report_3 = jv.validate_judge(gold, forward, retest=retest, swap=(forward, swapped))
    # Objective anchor: accept-vs-reject is the incontestable thing -> gate on it.
    cg, cf, cr, cs = map(_collapse_list, (gold, forward, retest, swapped))
    report = jv.validate_judge(cg, cf, retest=cr, swap=(cf, cs))
    raw = {"gold": gold, "forward": forward, "retest": retest, "swapped": swapped,
           "report_3label": report_3, "explained": fwd_ex, "self_corrected": self_corrected}
    return report, raw


def _hhi(labels):
    """Herfindahl-Hirschman index over a label distribution: sum p_i^2.

    1.0 = total concentration on one label; ~1/k = maximally spread over k labels."""
    labels = [x for x in labels if x is not None]
    n = len(labels)
    if n == 0:
        return 0.0
    counts = {}
    for x in labels:
        counts[x] = counts.get(x, 0) + 1
    return sum((c / n) ** 2 for c in counts.values())


def _mean_interjudge_agreement(per_judge_forward):
    """Average over cases of the fraction of judge PAIRS that gave the same verdict.

    High on objective-fact cases is CORRECT (truth is incontestable), not collapse;
    it becomes a real herding signal only once judgment cases enter the suite. The
    load-bearing EPC tripwire on objective cases is position-flip, reported per
    judge. This is monitoring context, not a gate."""
    names = list(per_judge_forward)
    if len(names) < 2:
        return None
    n_cases = len(per_judge_forward[names[0]])
    if n_cases == 0:
        return None
    total = 0.0
    for i in range(n_cases):
        verdicts = [per_judge_forward[name][i] for name in names]
        pairs = agree = 0
        for a in range(len(verdicts)):
            for b in range(a + 1, len(verdicts)):
                pairs += 1
                if verdicts[a] == verdicts[b]:
                    agree += 1
        total += (agree / pairs) if pairs else 0.0
    return total / n_cases


def validate_panel(judges, cases):
    """MVVP-validate a panel of named judges. `judges` maps name -> (llm, role_prompt).

    Returns a panel report: per-judge MVVP reports, an EPC monitor block, the
    majority verdict per case, and `certified` = at least one panel member earned
    trust (kappa/retest/flip all pass)."""
    per_judge = {}
    per_judge_forward = {}
    for name, (llm, prompt) in judges.items():
        report, raw = validate_judge_on_objective(llm, prompt, cases)
        per_judge[name] = {"report": report, "raw": raw}
        per_judge_forward[name] = raw["forward"]

    # Majority verdict per case across the panel (ties -> None, reported as split).
    majority = []
    n_cases = len(cases)
    for i in range(n_cases):
        votes = {}
        for name in judges:
            v = per_judge_forward[name][i]
            if v is not None:
                votes[v] = votes.get(v, 0) + 1
        if not votes:
            majority.append(None)
            continue
        top = max(votes.values())
        winners = [k for k, c in votes.items() if c == top]
        majority.append(winners[0] if len(winners) == 1 else None)

    pooled = [v for name in judges for v in per_judge_forward[name]]
    flips = [per_judge[name]["report"]["flip_rate"] for name in judges
             if per_judge[name]["report"]["flip_rate"] is not None]
    # Kish n_eff: effective INDEPENDENT votes from the panel's error correlation
    # ("Nine Judges, Two Effective Votes"). n_eff ~ N = genuinely diverse; ~1 = the
    # judges fail together (correlated errors -> add an execution-grounded verifier,
    # not more chat models). Lazy import: judge_independence imports this module.
    from judge_independence import kish_neff
    gold = [c["expected"] for c in cases]
    correctness = [[1 if _collapse(v) == _collapse(g) else 0
                    for v, g in zip(per_judge_forward[name], gold)] for name in judges]
    neff = kish_neff(correctness)
    epc = {
        "verdict_hhi": _hhi(pooled),
        "mean_interjudge_agreement": _mean_interjudge_agreement(per_judge_forward),
        "max_position_flip": max(flips) if flips else None,
        "flip_threshold": jv.FLIP_MAX,
        "panel_order_biased": (max(flips) > jv.FLIP_MAX) if flips else False,
        "kish_n_eff": neff["n_eff"],
        "mean_error_corr": neff["mean_error_corr"],
        "n_judges": neff["n_judges"],
    }

    certified_judges = [name for name in judges
                        if per_judge[name]["report"]["certified"]]
    return {
        "n_cases": n_cases,
        "judges": per_judge,
        "majority": majority,
        "epc": epc,
        "certified_judges": certified_judges,
        "certified": len(certified_judges) >= 1,
    }


def print_panel_report(panel, cases):
    print("Loop Team -- Meta-Verifier MVVP validation (objective-fact gold)")
    print("=" * 64)
    print("roles: case-author=human  verifier-under-test=verifier.md  "
          "gold-judge=gold_judge.md")
    print("cases: %d objective-fact (verdict settled by arithmetic/dates)\n"
          % panel["n_cases"])
    for name, entry in panel["judges"].items():
        r = entry["report"]
        raw = entry["raw"]
        print("-- judge: %s  (certification scored on ACCEPT/REJECT anchor) --" % name)
        jv.print_report(r)
        r3 = raw["report_3label"]
        print("  [3-label diagnostic] kappa=%.3f retest=%.3f flip=%.3f  "
              "(reject-label nuance, NOT gated here)"
              % (r3["kappa"],
                 r3["retest_kappa"] if r3["retest_kappa"] is not None else float("nan"),
                 r3["flip_rate"] if r3["flip_rate"] is not None else float("nan")))
        # Self-correction must be SURFACED, never silently parsed (the bug that
        # manufactured a fake blind spot). Count it, and print the model's REASONING
        # for any case it got wrong -- so the 'why' is never invisible.
        print("  self-corrected (>1 verdict in one answer): %d/%d  %s"
              % (raw.get("self_corrected", 0), len(cases),
                 "<-- READ these, the model changed its mind"
                 if raw.get("self_corrected", 0) else ""))
        explained = raw.get("explained") or [{}] * len(cases)
        # Full per-case verdict dump -- nothing hidden: gold, forward, retest, swap,
        # and whether the accept/reject decision agreed/flipped.
        print("    %-26s %-6s | fwd / retest / swap" % ("case", "gold"))
        for c, g, f, rt, sw, ex in zip(cases, raw["gold"], raw["forward"],
                                       raw["retest"], raw["swapped"], explained):
            anchor_ok = _collapse(f) == _collapse(g)
            flipped = _collapse(f) != _collapse(sw)
            tag = "" if anchor_ok else "  <-- anchor MISS"
            if flipped:
                tag += "  <-- order FLIP"
            if ex.get("self_corrected"):
                tag += "  <-- self-corrected"
            print("    %-26s %-6s | %-10s %-10s %-10s%s"
                  % (c["id"], g, f, rt, sw, tag))
            # On a MISS, print WHY -- the reasoning, not just the label. This is the
            # enforcement: a disagreement can never again be acted on un-read.
            if not anchor_ok and ex.get("raw"):
                why = " ".join(ex["raw"].split())
                print("        why: %s" % (why[:200]))
        print()
    e = panel["epc"]
    print("-- EPC monitor (panel collapse / order-bias) --")
    print("  verdict HHI (pooled)      : %.3f" % e["verdict_hhi"])
    agree = e["mean_interjudge_agreement"]
    print("  mean inter-judge agreement: %s"
          % ("%.3f (high is CORRECT on objective gold)" % agree
             if agree is not None else "n/a (single judge)"))
    mpf = e["max_position_flip"]
    print("  max position-flip         : %s  (gate <= %.2f)  %s"
          % ("%.3f" % mpf if mpf is not None else "n/a", e["flip_threshold"],
             "BIASED" if e["panel_order_biased"] else "ok"))
    ec = e.get("mean_error_corr")
    print("  Kish n_eff (indep votes)  : %.2f of %d judges  (error-corr %s; ~N=diverse, ~1=fail together)"
          % (e.get("kish_n_eff", float(e.get("n_judges", 1))), e.get("n_judges", 1),
             "%.3f" % ec if ec is not None else "n/a"))
    print("-" * 64)
    print("  certified judges : %s"
          % (", ".join(panel["certified_judges"]) or "NONE"))
    print("  PANEL CERTIFIED  : %s" % panel["certified"])
    if not panel["certified"]:
        print("  -> no judge earned trust on incontestable cases; do NOT let any "
              "of these judges rule on judgment-call cases (Part 2).")


# ---------------------------------------------------------------------------
# Live panel (needs ANTHROPIC_API_KEY). Built here (temperature=0 for retest
# determinism) rather than via optimize/llm.py to keep changes localized and
# avoid pulling temperature plumbing into the optimizer's contract.
# ---------------------------------------------------------------------------
def build_live_judge(model, provider="anthropic", temperature=0.0, max_tokens=512):
    """Build a live judge llm callable. provider='anthropic' (default) or 'openai'
    (the cross-family judge). Both route through call_with_retry with client
    max_retries=0 (single retry source). OpenAI omits temperature/max_tokens for
    cross-model compatibility (see optimize/llm.openai_llm)."""
    if provider == "openai":
        from llm import openai_llm
        return openai_llm(model)
    if provider != "anthropic":
        raise ValueError("unknown provider %r" % provider)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set -- the live MVVP run needs a key. The glue "
            "is tested with FakeLLM (--selftest); export the rotated key to run live.")
    try:
        import anthropic
    except ImportError as e:  # noqa: BLE001
        raise RuntimeError("`pip install anthropic` to run the live panel") from e
    from llm import call_with_retry  # bounded retries on transient infra errors
    # max_retries=0: call_with_retry is the single source of retry behavior.
    client = anthropic.Anthropic(api_key=key, max_retries=0)

    def llm(prompt):
        def _call():
            kw = dict(model=model, max_tokens=max_tokens,
                      messages=[{"role": "user", "content": prompt}])
            try:
                msg = client.messages.create(temperature=temperature, **kw)
            except anthropic.BadRequestError as e:
                # some models (e.g. opus-4-8) deprecate `temperature` -- drop it
                # rather than crash/exclude the judge (a silent-exclusion bug).
                if "temperature" in str(e).lower():
                    msg = client.messages.create(**kw)
                else:
                    raise
            return "".join(getattr(b, "text", "") for b in msg.content)
        return call_with_retry(_call)
    return llm


# Cross-family panel: the two Anthropic models + a CHEAP OpenAI model for true
# PoLL diversity. The OpenAI panelist is added only when OPENAI_PANEL_MODEL is set
# (and a key is present) -- otherwise the run is Anthropic-only, same as before.
LIVE_PANEL = {
    "haiku": ("anthropic", "claude-haiku-4-5-20251001"),
    "sonnet": ("anthropic", "claude-sonnet-4-6"),
}


def _live_panel():
    """Resolve the panel, appending the cross-family OpenAI judge if configured."""
    panel = dict(LIVE_PANEL)
    gpt = os.environ.get("OPENAI_PANEL_MODEL")
    if gpt and os.environ.get("OPENAI_API_KEY"):
        panel["gpt"] = ("openai", gpt)
    return panel


def run_live():
    cases = load_objective_cases()
    if not cases:
        raise SystemExit("no objective-fact cases found in %s" % OBJECTIVE_DIR)
    gold_prompt = load_role("gold_judge.md")
    spec = _live_panel()
    if "gpt" not in spec:
        print("(note: no cross-family judge -- set OPENAI_PANEL_MODEL + OPENAI_API_KEY "
              "for true PoLL; running Anthropic-only)\n")
    judges = {name: (build_live_judge(model, provider=provider), gold_prompt)
              for name, (provider, model) in spec.items()}
    panel = validate_panel(judges, cases)
    print_panel_report(panel, cases)
    return 0 if panel["certified"] else 1


# ---------------------------------------------------------------------------
# Self-test (FakeLLM): the glue, with no network. A judge that agrees with the
# arithmetic gold certifies; a position-biased one fails the flip check; a
# chance-level one fails kappa.
# ---------------------------------------------------------------------------
def _selftest():
    cases = load_objective_cases()
    if not cases:
        print("SELFTEST: FAIL -- no objective cases loaded")
        return False
    from llm import FakeLLM
    gold_prompt = load_role("gold_judge.md")
    ok = True

    # A perfect judge: matches the artifact text it is shown (forward OR swapped)
    # back to its case and answers that case's gold verdict -- so it is both
    # correct vs truth AND order-invariant (the swapped framing maps to the same
    # case, same verdict). Full-string match is unique per case.
    def perfect(prompt):
        for c in cases:
            if c["artifact"] in prompt or c.get("artifact_swapped", "\0") in prompt:
                return "VERDICT: %s -- by fact" % c["expected"]
        return "VERDICT: PASS -- default"

    print("== perfect judge (agrees with arithmetic truth) ==")
    pg = validate_panel({"oracle": (FakeLLM(perfect), gold_prompt)}, cases)
    print_panel_report(pg, cases)
    ok = ok and pg["certified"] and pg["judges"]["oracle"]["report"]["complete"]

    # Position-biased judge: PASS in the forward framing, FAIL in the swapped one
    # -- so its verdict flips with order on every case -> high flip-rate.
    def biased(prompt):
        for c in cases:
            if c["artifact"] in prompt:
                return "VERDICT: PASS -- leads forward"
            if c.get("artifact_swapped", "\0") in prompt:
                return "VERDICT: FAIL -- leads swapped"
        return "VERDICT: PASS"
    print("\n== position-biased judge (order-sensitive) ==")
    pb = validate_panel({"biased": (FakeLLM(biased), gold_prompt)}, cases)
    print("  biased flip-rate: %.3f (want > %.2f)"
          % (pb["judges"]["biased"]["report"]["flip_rate"], jv.FLIP_MAX))
    ok = ok and (not pb["certified"]) and (pb["epc"]["panel_order_biased"])

    # Chance-level judge: constant PASS -> high exact-match, ~0 kappa.
    print("\n== chance-level judge (constant verdict) ==")
    pc = validate_panel({"chance": (FakeLLM(lambda p: "VERDICT: PASS"), gold_prompt)}, cases)
    print("  chance kappa: %.3f (want < %.2f)"
          % (pc["judges"]["chance"]["report"]["kappa"], jv.KAPPA_MIN))
    ok = ok and (not pc["certified"])

    print("\nSELFTEST: %s" % ("OK" if ok else "FAIL"))
    return ok


def main():
    if "--selftest" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    if "--live" in sys.argv:
        sys.exit(run_live())
    print(__doc__)


if __name__ == "__main__":
    main()
