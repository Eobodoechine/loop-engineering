#!/usr/bin/env python3
"""Loop Team -- Measured optimizer for the Verifier prompt (Phase 1, Sub-phase B).

Reflective, PACE-gated prompt improvement. Scores the incumbent Verifier prompt
on the role-level eval cases, reflects on the ones it gets wrong to propose an
improved prompt, scores the candidate on the SAME cases, and accepts the
candidate ONLY if `acceptor.pace_accept` returns ACCEPT (anytime-valid, not raw
score). On accept it writes a PROPOSAL file -- it never overwrites the live role.
Promotion = human diff-review + a log line in fix_plan.md.

This is the safe, measured form of self-improvement; full Oga-rewrites-the-team
comes later (Phase 5) and is only safe on top of this.

Live run needs an LLM (ANTHROPIC_API_KEY); the glue is tested with FakeLLM.

CLI:
    python3 optimize_verifier.py            # uses roles/verifier.md + anthropic_llm
"""
import os
import sys

OPT_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.normpath(os.path.join(OPT_DIR, "..", "evals"))
ROLES_DIR = os.path.normpath(os.path.join(OPT_DIR, "..", "roles"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPT_DIR)
import acceptor  # noqa: E402
import run_evals  # noqa: E402
import role_runner  # noqa: E402


def verifier_cases(cases=None):
    """The role-level cases whose verdict the Verifier prompt governs."""
    cases = cases if cases is not None else run_evals.load_cases()
    return [c for c in cases
            if c.get("requires") == "judge" and c.get("target") == "verifier"]


def score(llm, role_prompt, cases):
    """Per-case correctness (1/0) of a Verifier prompt on the given cases."""
    judge = role_runner.make_role_judge(llm, role_prompt)
    correct = []
    for c in cases:
        verdict = judge(c)
        bucket = run_evals.classify(c["expected"], verdict)
        correct.append(1 if bucket in ("caught", "ok") else 0)
    return correct


def propose(llm, role_prompt, cases, correct):
    """Ask the LLM to reflect on the missed cases and propose an improved prompt."""
    missed = [c for c, ok in zip(cases, correct) if not ok]
    if not missed:
        return None  # nothing to fix
    failures = "\n".join(
        "- case %s (expected %s): %s" % (c["id"], c["expected"],
                                         c.get("rubric", "")[:280])
        for c in missed)
    reflection = (
        "You are improving the Verifier role prompt below. It currently gives a "
        "WRONG verdict on these cases:\n%s\n\nRewrite the FULL role prompt so it "
        "would handle those cases correctly, WITHOUT weakening anything it already "
        "gets right. Output only the new role prompt.\n\n--- CURRENT PROMPT ---\n%s"
        % (failures, role_prompt))
    return llm(reflection).strip()


def optimize(llm, incumbent_prompt, cases=None, out_dir=None,
             alpha=0.05, lam=0.5, min_discordant=5):
    """One reflective round, PACE-gated. Returns a result dict; writes a proposal
    file iff the candidate is ACCEPTED."""
    cases = verifier_cases(cases)
    if not cases:
        return {"decision": "REJECT", "reason": "no verifier-target cases to score on"}
    inc_correct = score(llm, incumbent_prompt, cases)
    candidate = propose(llm, incumbent_prompt, cases, inc_correct)
    if candidate is None:
        return {"decision": "REJECT", "reason": "incumbent already perfect on suite",
                "incumbent_correct": inc_correct}
    cand_correct = score(llm, candidate, cases)
    pairs = acceptor.pairs_from_correctness(inc_correct, cand_correct)
    result = acceptor.pace_accept(pairs, alpha=alpha, lam=lam,
                                  min_discordant=min_discordant)
    out = {
        "decision": result.decision,
        "reason": result.reason,
        "incumbent_correct": inc_correct,
        "candidate_correct": cand_correct,
        "acceptor": result,
        "candidate_prompt": candidate,
        "proposal_path": None,
    }
    if result.decision == "ACCEPT":
        out_dir = out_dir or os.path.join(OPT_DIR, "proposals")
        os.makedirs(out_dir, exist_ok=True)
        # Number from the MAX existing index + 1, never the COUNT -- a gap (from a
        # promoted/deleted proposal) would otherwise collide and silently
        # overwrite an existing, unreviewed proposal.
        existing = []
        for f in os.listdir(out_dir):
            if f.startswith("verifier.") and f.endswith(".md"):
                mid = f[len("verifier."):-len(".md")]
                if mid.isdigit():
                    existing.append(int(mid))
        nxt = (max(existing) + 1) if existing else 1
        path = os.path.join(out_dir, "verifier.%03d.md" % nxt)
        with open(path, "w", encoding="utf-8") as f:
            f.write(candidate)
        out["proposal_path"] = path
    return out


def main():
    role_path = os.path.join(ROLES_DIR, "verifier.md")
    with open(role_path, encoding="utf-8") as f:
        incumbent = f.read()
    from llm import anthropic_llm  # imported here so --help works without a key
    llm = anthropic_llm()
    out = optimize(llm, incumbent)
    print("decision:", out["decision"], "--", out["reason"])
    print("incumbent correct:", out.get("incumbent_correct"))
    print("candidate correct:", out.get("candidate_correct"))
    if out.get("proposal_path"):
        print("PROPOSAL written:", out["proposal_path"])
        print("Next: diff-review it, then (if good) promote to roles/verifier.md "
              "and log to fix_plan.md. Never silent-promote.")
    sys.exit(0)


if __name__ == "__main__":
    main()
