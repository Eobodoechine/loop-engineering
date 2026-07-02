#!/usr/bin/env python3
"""fi- scoring glue for the D1 fault-injection ratchet (spec rev 5, S5).

Pinned mechanism (spec 5.4-5.7): IN-PROCESS scoring; one verdicts file per
column at DISTINCT paths; REPLAY_VERDICTS_PATH set per column with an explicit
replay_judge._CACHE reset (the path-keyed cache would silently replay column 1
across columns, faking flip rate 0 and perfect band agreement); fi- scoping via
the precedented run_evals.load_cases monkeypatch, always RESTORED. The
raise-on-missing-id contract is untouched: a gap becomes an error row, which
the 5.7 completeness gate names and uses to withhold the decision.
record_verdict (5.6) persists LABELS only, via parse_verdict semantics
(optimize/role_runner.py); every raw!=normalized pair retains the raw for
curation review; an unparseable verdict is never persisted (id stays MISSING,
the resumable sweep re-judges it). The spec-6 decision table runs only on a
complete, zero-error column set. Python 3.9, stdlib only, deterministic.
"""
import json
import os
import re
import sys

FI_DIR = os.path.dirname(os.path.abspath(__file__))
EVALS_DIR = os.path.dirname(FI_DIR)
for _p in (EVALS_DIR, FI_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import replay_judge  # noqa: E402
import run_evals  # noqa: E402

VERDICTS = ("FALSE-PASS", "FAIL", "PASS")  # order matters: FALSE-PASS contains PASS
_SCORED = ("caught", "missed", "ok", "regression")
_VERDICT_LINE = re.compile(
    r"verdict\s*[:=]\s*(false[\s_-]*pass|false-pass|fail|pass)", re.IGNORECASE)
# Spec-6 edges -- recorded as tunable, not laws.
THRESHOLDS = {"freeze_lo": 60.0, "freeze_hi": 80.0, "gray_hi": 90.0,
              "weak_lo": 75.0, "weak_hi": 85.0, "control_min_ok": 0.80, "min_n": 5}


def normalize_verdict(raw_text):
    """parse_verdict semantics: PASS | FAIL | FALSE-PASS, or None if unparseable.
    Explicit VERDICT: lines win, LAST wins on self-correction; variants fold;
    the bare-token fallback is first-position-wins (hence the raw log)."""
    if not raw_text:
        return None
    matches = _VERDICT_LINE.findall(raw_text)
    if matches:
        tok = matches[-1].upper().replace(" ", "-").replace("_", "-")
        return "FALSE-PASS" if tok.startswith("FALSE") else tok
    up = re.sub(r"FALSE[ _]PASS", "FALSE-PASS", raw_text.upper())
    best, best_pos = None, len(up) + 1
    for v in VERDICTS:
        pos = up.find(v)
        if pos != -1 and pos < best_pos:
            best, best_pos = v, pos
    return best


def record_verdict(column_path, case_id, raw_text):
    """Validation-at-persistence (5.6): upsert {id, verdict:<label>} into the
    JSON list replay_judge replays; keep "raw" whenever it differs from the
    label; unparseable -> nothing written, None returned, id stays MISSING."""
    label = normalize_verdict(raw_text)
    if label is None:
        return None
    rows = []
    if os.path.exists(column_path):
        with open(column_path, encoding="utf-8") as f:
            rows = json.load(f)
    row = {"id": case_id, "verdict": label}
    if raw_text != label:
        row["raw"] = raw_text
    rows = [r for r in rows if r.get("id") != case_id] + [row]
    tmp = column_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=1)
    os.replace(tmp, column_path)
    return label


def _validated_replay_judge(case):
    """File-level verdict validation (5.6 defense-in-depth): a verdicts FILE
    can carry rows that never went through record_verdict (hand-recovered
    after a crashed sweep). Only a verdict that normalizes to an exact valid
    label may reach classify(); anything else raises here, so the row becomes
    an ERROR row and the 5.7 completeness gate blocks the decision -- never a
    silently scored missed/regression bucket."""
    raw = replay_judge.judge(case)
    if not isinstance(raw, str):
        raise RuntimeError(
            "score_fi: non-string verdict %r recorded for case id %r -- "
            "error row, never a scored bucket" % (raw, case.get("id")))
    label = normalize_verdict(raw)
    if label not in VERDICTS:
        raise RuntimeError(
            "score_fi: recorded verdict %r for case id %r does not normalize "
            "to a valid label -- error row, never a scored bucket"
            % (raw, case.get("id")))
    return label


def _reject_duplicate_file_ids(path, name):
    """Duplicate rows for one id inside a verdicts FILE used to resolve
    silently last-wins (replay_judge's dict build); raise instead -- Oga
    overruled last-wins per the raise-on-anomaly philosophy, D1 run log
    2026-07-02. Only the readable list shape is checked here; missing/
    malformed/dict-shaped files stay on replay_judge's own loud paths."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return
    if not isinstance(data, list):
        return
    seen, dupes = set(), set()
    for r in data:
        if isinstance(r, dict) and isinstance(r.get("id"), str):
            if r["id"] in seen:
                dupes.add(r["id"])
            seen.add(r["id"])
    if dupes:
        raise ValueError(
            "score_fi: duplicate verdict rows for id(s) %s in column %r (%s); "
            "silent last-wins is disallowed -- re-record the column"
            % (sorted(dupes), name, path))


def _ratio(hit, miss):
    return hit / float(hit + miss) if (hit + miss) else None


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _column_stats(rows_by_id, ids, manifest):
    """Bucket one column; per-family/per-difficulty joined via the withheld
    manifest (traps only). Returns (stats, [(cid, detail)] error/absent)."""
    counts = {"caught": 0, "missed": 0, "ok": 0, "regression": 0}
    fam, dif, missing = {}, {}, []
    for cid in ids:
        r = rows_by_id.get(cid)
        b = r["bucket"] if r else "error"
        if b not in _SCORED:  # never silently shrink a denominator (5.7)
            missing.append((cid, (r or {}).get("detail", "no row")))
            continue
        counts[b] += 1
        if b in ("caught", "missed"):
            ent = manifest.get(cid, {})
            for tbl, key in ((fam, ent.get("family", "unknown")),
                             (dif, ent.get("difficulty", "unknown"))):
                c, n = tbl.get(key, (0, 0))
                tbl[key] = (c + (b == "caught"), n + 1)
    return ({"trap_accuracy": _ratio(counts["caught"], counts["missed"]),
             "control_ok_rate": _ratio(counts["ok"], counts["regression"]),
             "per_family": {k: c / float(n) for k, (c, n) in fam.items()},
             "per_difficulty": {k: c / float(n) for k, (c, n) in dif.items()},
             "counts": counts}, missing)


def _tier_stats(col_names, col_reports, col_verdicts, ids):
    """Round-mean per tier (<tier>_r<round>) + flip rate over ALL fi- ids."""
    by_tier, tiers = {}, {}
    for name in col_names:
        by_tier.setdefault(name.rsplit("_r", 1)[0], []).append(name)
    for tier, names in sorted(by_tier.items()):
        flip = None
        if len(names) >= 2 and ids:
            flip = sum(1 for cid in ids if len(set(
                col_verdicts[n].get(cid) for n in names)) > 1) / float(len(ids))
        tiers[tier] = {
            "trap_accuracy": _mean([col_reports[n]["trap_accuracy"] for n in names]),
            "control_ok_rate": _mean([col_reports[n]["control_ok_rate"] for n in names]),
            "flip_rate": flip, "rounds": sorted(names)}
    return tiers


def _band_strong(p):
    """A_s bands partition [0,100]; A_s=80 is inside the freeze band (spec 6)."""
    return ("below_60" if p < THRESHOLDS["freeze_lo"] else
            "freeze_60_80" if p <= THRESHOLDS["freeze_hi"] else
            "gray_80_90" if p <= THRESHOLDS["gray_hi"] else "above_90")


def _band_weak(p):
    return ("le_75" if p <= THRESHOLDS["weak_lo"] else
            "mid_75_85" if p < THRESHOLDS["weak_hi"] else "ge_85")


def _round_issues(tier, tiers):
    """Spec 5.3: TWO independent judging rounds per tier; with one round the
    band-agreement set is a singleton and agreement is vacuous, so a
    fewer-than-two-round tier can never license a decision-bearing outcome."""
    n = len(tiers[tier]["rounds"])
    if n < 2:
        return ["%s: only %d judging round(s); spec 5.3 requires two rounds "
                "in band agreement for any decision-bearing outcome" % (tier, n)]
    return []


def _control_issues(tier, tiers, col_reports, n_controls):
    """Spec-6 control precondition + minimum-n on the control subset."""
    t, issues = THRESHOLDS, []
    rate = tiers[tier]["control_ok_rate"]
    if rate is None:
        issues.append("%s: no scored controls" % tier)
    elif rate < t["control_min_ok"]:
        issues.append("%s: control ok-rate %.2f < %.2f -- over-rejection; audit "
                      "control rejections first" % (tier, rate, t["control_min_ok"]))
    if n_controls < t["min_n"]:
        issues.append("%s: control n=%d < %d (minimum-n)" % (tier, n_controls, t["min_n"]))
    if len(set((r or 0) >= t["control_min_ok"] for r in
               (col_reports[n]["control_ok_rate"] for n in tiers[tier]["rounds"]))) > 1:
        issues.append("%s: control rounds straddle the 80%% edge" % tier)
    return issues


def _decide(tiers, col_reports, n_traps, n_controls):
    """Spec-6 table, exhaustive over (A_s, A_h). Decision-bearing rows (FREEZE /
    ESCALATE_INJECTOR / KILL_LANE) also need the control precondition on each
    tier they read plus minimum-n; any failure or band-straddle routes to
    GRAY_ZONE, never to the nearer row."""
    names = sorted(tiers)
    strong = "sonnet" if "sonnet" in tiers else (names[0] if len(names) == 1 else max(
        names, key=lambda t: tiers[t]["trap_accuracy"] or 0.0))
    weak = "haiku" if ("haiku" in tiers and strong != "haiku") else next(
        (t for t in names if t != strong), None)

    def pct(t):
        a = tiers[t]["trap_accuracy"] if t else None
        return None if a is None else a * 100.0

    def rpct(t):
        return [col_reports[n]["trap_accuracy"] * 100.0 for n in tiers[t]["rounds"]
                if col_reports[n]["trap_accuracy"] is not None]

    d = {"strong_tier": strong, "weak_tier": weak, "A_s": pct(strong), "A_h": pct(weak),
         "C_s": tiers[strong]["control_ok_rate"],
         "C_h": tiers[weak]["control_ok_rate"] if weak else None,
         "thresholds": dict(THRESHOLDS), "outcome": None, "reasons": [],
         "notes": ["per-family/per-difficulty figures are DESCRIPTIVE ONLY "
                   "(minimum-n: subset actions need >=5 traps; pool below that)"]}

    def out(outcome, *reasons):
        d["outcome"] = outcome
        d["reasons"].extend(reasons)
        return d

    if d["A_s"] is None:
        return out("GRAY_ZONE", "no scored traps for the strong tier")
    s_r = rpct(strong)
    d["band_agreement_strong"] = len(set(_band_strong(v) for v in s_r)) == 1
    if not d["band_agreement_strong"]:
        return out("GRAY_ZONE", "A_s rounds straddle a band edge (60/80/90): %s" % s_r)
    band = _band_strong(d["A_s"])
    if band == "below_60":
        return out("AUDIT_SUITE", "A_s %.1f%% < 60%%: audit EVERY miss for injection "
                   "artifacts + control regressions; repair/drop; re-measure" % d["A_s"])
    if band == "gray_80_90":
        return out("GRAY_ZONE", "A_s %.1f%% in (80,90]: gray-zone default; freeze only "
                   "decision-grade [60,80] subsets; human decision logged" % d["A_s"])
    small_n = (["trap n=%d < %d: one flip swings >20pp -- not decision-grade"
                % (n_traps, THRESHOLDS["min_n"])] if n_traps < THRESHOLDS["min_n"] else [])
    if band == "freeze_60_80":
        issues = (_round_issues(strong, tiers)
                  + _control_issues(strong, tiers, col_reports, n_controls) + small_n)
        return out("GRAY_ZONE", *issues) if issues else out(
            "FREEZE", "A_s %.1f%% in [60,80], control precondition met: freeze as the "
            "hard suite; record stratified split; D4 unblocked" % d["A_s"])
    if weak is None or d["A_h"] is None:  # above_90 rows are the only A_h readers
        return out("GRAY_ZONE", "A_s > 90% with no weak-tier measurement: crude-injector "
                   "vs verifier competence not separable")
    h_r = rpct(weak)
    d["band_agreement_weak"] = len(set(_band_weak(v) for v in h_r)) == 1
    if not d["band_agreement_weak"]:
        return out("GRAY_ZONE", "A_h rounds straddle a band edge (75/85): %s" % h_r)
    issues = (_round_issues(strong, tiers) + _round_issues(weak, tiers)
              + _control_issues(strong, tiers, col_reports, n_controls)
              + _control_issues(weak, tiers, col_reports, n_controls) + small_n)
    if issues:
        return out("GRAY_ZONE", *issues)
    wband = _band_weak(d["A_h"])
    if wband == "ge_85":
        return out("ESCALATE_INJECTOR", "A_s > 90% and A_h >= 85%: both tiers near-"
                   "ceiling -- injector too crude; one round of harder deep injections "
                   "before any kill-lane verdict")
    if wband == "le_75":
        return out("KILL_LANE", "A_s > 90% and A_h <= 75%: tier separation -- recommend "
                   "killing the trace-text lane for Lane C; HUMAN decision, log to fix_plan")
    return out("GRAY_ZONE", "A_s > 90%, 75% < A_h < 85% (ambiguous middle): neither row "
               "licensed; human decision to fix_plan with both hypotheses stated")


def score_columns(columns, manifest, cases):
    """Score verdict columns over the fi- subset (spec 5.4-5.7).
    columns: {"<tier>_r<round>": verdicts_file_path} at DISTINCT paths;
    manifest: injection-log dict (controls: family "control"); cases: the fi-
    case dicts. Returns the pinned report (columns/tiers/complete/missing/
    decision); decision is None unless every column covers every id error-free."""
    fi_cases = list(cases)
    ids = [c["id"] for c in fi_cases]
    # LOUD pre-scoring validation -- anomalies raise, they never skew a figure:
    # (a) duplicate case ids would collapse rows_by_id and silently drop a row
    # from the denominator (5.7); (b) two columns sharing one verdicts path is
    # the exact corruption 5.4 pins against (fake flip rate 0.0); (c) duplicate
    # ids inside one verdicts file (silent last-wins overruled).
    dup_ids = sorted(set(cid for i, cid in enumerate(ids) if cid in ids[:i]))
    if dup_ids:
        raise ValueError(
            "score_fi: duplicate case id(s) %s in the fi- subset; a duplicate "
            "collapses rows_by_id and silently drops a row from the accuracy "
            "denominator (spec 5.7)" % dup_ids)
    path_owner = {}
    for name in sorted(columns):
        real = os.path.realpath(columns[name])
        if real in path_owner:
            raise ValueError(
                "score_fi: columns %r and %r share one verdicts path (%r); "
                "spec 5.4 requires one verdicts file per column at DISTINCT "
                "paths" % (path_owner[real], name, columns[name]))
        path_owner[real] = name
        _reject_duplicate_file_ids(columns[name], name)
    n_traps = sum(1 for c in fi_cases if c.get("expected") in ("FAIL", "FALSE-PASS"))
    n_controls = sum(1 for c in fi_cases if c.get("expected") == "PASS")
    col_rows, col_verdicts = {}, {}
    orig_load = run_evals.load_cases
    orig_env = os.environ.get("REPLAY_VERDICTS_PATH")
    try:
        run_evals.load_cases = lambda: fi_cases  # precedented in-process scoping
        for name in sorted(columns):
            os.environ["REPLAY_VERDICTS_PATH"] = columns[name]
            replay_judge._CACHE = {"path": None, "verdicts": None}  # explicit reset (5.4)
            suite = run_evals.run_suite(judge=_validated_replay_judge)
            col_rows[name] = dict((r["id"], r) for r in suite["rows"])
            col_verdicts[name] = dict((r["id"], r.get("verdict")) for r in suite["rows"])
    finally:
        run_evals.load_cases = orig_load  # ALWAYS restored
        replay_judge._CACHE = {"path": None, "verdicts": None}
        if orig_env is None:
            os.environ.pop("REPLAY_VERDICTS_PATH", None)
        else:
            os.environ["REPLAY_VERDICTS_PATH"] = orig_env
    col_reports, missing = {}, []
    for name in sorted(columns):
        stats, miss = _column_stats(col_rows[name], ids, manifest)
        col_reports[name] = stats
        missing.extend("%s: %s -- %s" % (name, cid, detail) for cid, detail in miss)
    tiers = _tier_stats(sorted(columns), col_reports, col_verdicts, ids)
    complete = not missing
    return {"columns": col_reports, "tiers": tiers, "complete": complete,
            "missing": missing, "n_cases": len(ids), "n_traps": n_traps,
            "n_controls": n_controls,
            "decision": _decide(tiers, col_reports, n_traps, n_controls) if complete else None}
