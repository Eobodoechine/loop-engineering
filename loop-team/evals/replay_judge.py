#!/usr/bin/env python3
"""Replay a recorded set of sub-agent verdicts as a `run_evals` judge adapter.

The free (subscription) judging path, per `JUDGE_ADAPTER_SUBAGENT.md`: the
orchestrator judges the blind cases out-of-band with a sub-agent ($0), writes the
verdicts to a file, and this module replays them so `run_evals` can score -- which
means the free path satisfies the EXISTING `--judge MODULE` contract with no new
scoring code.

  REPLAY_VERDICTS_PATH=/tmp/verdicts.json \
      python3 run_evals.py --judge replay_judge.py --arith-guard

The verdicts-file path comes from the `REPLAY_VERDICTS_PATH` env var, NOT a CLI flag:
`run_evals --judge MODULE` imports the module and calls `mod.judge(case)`, forwarding
nothing, so a flag can't reach us (caught in spec review).

Verdicts file: a list `[{id, verdict, reason?}]`, or a dict `{model: [...]}` (then
set `REPLAY_MODEL` to pick the column). A missing/empty file, an unknown case id,
or a blank verdict RAISES -- a gap in the recorded set is an error, never a silent
PASS. `export_blind` is the companion prep helper (strip gold before judging).
"""
import json
import os
import re

# Gold-side fields that must never reach the judging sub-agent (superset of
# verify_build's GOLD_SIDE_FIELDS so this stays at least as strict as the lint).
_GOLD_SIDE = ("expected", "rubric", "objective_fact", "fact", "why_objective",
              "failure_mode", "why_hard", "source", "origin")

_CACHE = {"path": None, "verdicts": None}


def _norm(s):
    return re.sub(r"\s+", " ", s).casefold()


def export_blind(cases):
    """Strip every gold-side field -> [{id, artifact}] for the judging sub-agent.

    The strip is the real protection (the sub-agent never receives `expected` /
    `rubric` / `objective_fact` / ...). On top of that, a BEST-EFFORT leak guard:
    if a long (>=20 char) gold-reasoning string is embedded in the artifact
    (case/whitespace-normalized substring), refuse -- a case author mistake would
    let the sub-agent see the answer and inflate the measurement. Precision-first,
    not a proof: it intentionally ignores short fields (e.g. `expected: "PASS"`
    would match everywhere) and exotic paraphrases."""
    out = []
    for c in cases:
        art = str(c.get("artifact", ""))
        art_n = _norm(art)
        for f in _GOLD_SIDE:
            val = c.get(f)
            if isinstance(val, str) and len(val) >= 20 and _norm(val)[:40] in art_n:
                raise ValueError("export_blind: gold field %r leaks into artifact of case %r"
                                 % (f, c.get("id")))
        out.append({"id": c["id"], "artifact": art})
    return out


def _select_rows(data):
    """A verdicts file is a list of rows, or {model: [rows]}; REPLAY_MODEL picks a
    column when it's a multi-model dict."""
    if isinstance(data, dict):
        model = os.environ.get("REPLAY_MODEL")
        if model:
            if model not in data:
                raise RuntimeError("replay_judge: REPLAY_MODEL %r not in %s" % (model, sorted(data)))
            return data[model]
        keys = list(data)
        if len(keys) == 1:
            return data[keys[0]]
        raise RuntimeError("replay_judge: multi-model verdicts; set REPLAY_MODEL to one of %s" % keys)
    return data


def _verdicts():
    """Lazily load + cache {id: verdict} from REPLAY_VERDICTS_PATH. Re-reads when the
    env path CHANGES. (It does not re-read the SAME path if overwritten in-process --
    fine for the real usage: run_evals runs as a fresh subprocess, so the cache starts
    empty each run; the test suite resets _CACHE in setUp.)"""
    path = os.environ.get("REPLAY_VERDICTS_PATH")
    if not path:
        raise RuntimeError("replay_judge: set REPLAY_VERDICTS_PATH to the verdicts JSON file")
    if _CACHE["path"] != path or _CACHE["verdicts"] is None:
        if not os.path.exists(path):
            raise RuntimeError("replay_judge: verdicts file not found: %s" % path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        m = {}
        for r in _select_rows(data):
            if r.get("verdict"):                 # blank/None == not recorded -> stays missing
                m[r["id"]] = r["verdict"]
        if not m:
            raise RuntimeError("replay_judge: no usable verdicts in %s" % path)
        _CACHE["path"], _CACHE["verdicts"] = path, m
    return _CACHE["verdicts"]


def judge(case):
    """run_evals `--judge` entrypoint: return the recorded verdict for case['id'].
    Raises on an unknown id -- a gap in the recorded set is an error, not a PASS."""
    v = _verdicts()
    cid = case.get("id")
    if cid not in v:
        raise RuntimeError("replay_judge: no recorded verdict for case id %r "
                           "(judge the blind cases first, or a gap in the recorded set)" % cid)
    return v[cid]
