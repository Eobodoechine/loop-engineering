#!/usr/bin/env python3
"""dashboard.py — LoopTeam: parse every run directory and render a single
self-contained ``dashboard.html`` ("are my agents running as I want?" view).

Stdlib only. No external deps, no network. The output HTML inlines all CSS/JS.

What it reads, per run directory found under the configured roots:
  - The run's narrative log: run_log.md / run_summary.md / summary.md /
    SUMMARY.md / brief.md (first that exists, in that priority order).
  - plan_check_log.md (if present) for plan-check rounds.
  - trace.jsonl (if present, via trace.read_trace) for live per-step events,
    cumulative tokens and cost.

What it extracts, per run:
  name, date, final status (pass/fail/done/unknown), iteration count,
  plan-check rounds (PLAN_FAIL -> PLAN_PASS), adversarial bugs caught,
  verifier verdict, lessons, and token/cost totals when a trace exists.

Usage:
    python3 dashboard.py [--out dashboard.html] [--root DIR ...]

With no --root, it defaults to the two LoopTeam run roots. Missing roots are
skipped silently (so this is safe to run anywhere).
"""
import argparse
import html
import json
import os
import re

try:
    from trace import read_trace  # local module
except Exception:  # pragma: no cover - trace.py should sit beside this file
    def read_trace(_run_dir):
        return []


# Default run roots (both LoopTeam run locations). Override with --root.
DEFAULT_ROOTS = [
    os.path.expanduser("~/Claude/loop/runs"),
    os.path.expanduser("~/Claude/loop/loop-team/runs"),
]

# Log file names in priority order — first match is the run's primary log.
LOG_CANDIDATES = ["run_log.md", "run_summary.md", "summary.md", "SUMMARY.md", "brief.md"]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _find_log(run_dir):
    """Return (filename, text) for the highest-priority log present, else ("", "")."""
    for name in LOG_CANDIDATES:
        p = os.path.join(run_dir, name)
        if os.path.exists(p):
            return name, _read(p)
    return "", ""


def _extract_date(name, text):
    """A run's date: leading YYYY-MM-DD in the dir name, else a 'Date:' line."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", name)
    if m:
        return m.group(1)
    m = re.search(r"^\s*Date:\s*(\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
    return m.group(1) if m else ""


def _extract_status(text):
    """Final status: pass / fail / done / unknown.

    Priority: an explicit VERDICT: PASS/FAIL wins; then an 'Outcome:' line;
    then bare PASS/DONE/FAIL signals. Conservative — defaults to 'unknown'.
    """
    t = text or ""
    mverdict = re.search(r"VERDICT:\s*(PASS|FAIL)", t)
    if mverdict:
        return mverdict.group(1).lower()
    mout = re.search(r"Outcome:\s*\**\s*(PASS|FAIL|DONE)", t, re.IGNORECASE)
    if mout:
        return mout.group(1).lower()
    if re.search(r"\bOutcome:\s*DONE\b", t, re.IGNORECASE) or re.search(r"\bDONE\b\s*[✓✔]", t):
        return "done"
    if re.search(r"\bverdict\b.*\bPASS\b", t, re.IGNORECASE) or re.search(r":\s*PASS\b", t):
        return "pass"
    if re.search(r"\bFAIL\b", t):
        return "fail"
    if re.search(r"\bDONE\b", t):
        return "done"
    return "unknown"


def _extract_verdict(text):
    """Independent-verifier verdict line, if stated."""
    m = re.search(r"VERDICT:\s*(PASS|FAIL)", text or "")
    if m:
        return "VERDICT: " + m.group(1)
    m = re.search(r"Verifier[^\n]*?\b(PASS|FAIL)\b", text or "", re.IGNORECASE)
    if m:
        return "Verifier: " + m.group(1).upper()
    return ""


def _extract_iterations(text):
    """Best-effort iteration count from 'Iteration N' / 'Iter N' / '### Step N'.

    Returns the max integer seen, or 0 if none.
    """
    # Require 'Iteration N' / 'Iter N' as a token with the number on the SAME
    # line (no newline-spanning \s+), so 'a 1 iteration\n27 tests' doesn't
    # falsely read 27 as an iteration count.
    nums = [int(n) for n in re.findall(r"\b(?:Iteration|Iter)[ \t]+(\d+)\b", text or "", re.IGNORECASE)]
    if nums:
        return max(nums)
    # Fall back to counting distinct 'Step N' headers as a loose proxy.
    steps = [int(n) for n in re.findall(r"\bStep[ \t]+(\d+)\b", text or "", re.IGNORECASE)]
    return max(steps) if steps else 0


def _extract_plan_rounds(run_dir, log_text):
    """Plan-check rounds = number of PLAN_FAIL/PLAN_PASS markers, preferring the
    dedicated plan_check_log.md, falling back to the main log text."""
    plan_text = _read(os.path.join(run_dir, "plan_check_log.md")) or ""
    src = plan_text if plan_text.strip() else (log_text or "")
    fails = len(re.findall(r"PLAN_FAIL", src))
    passes = len(re.findall(r"PLAN_PASS", src))
    rounds = fails + passes
    return {"rounds": rounds, "fails": fails, "passes": passes}


def _extract_adversarial(text):
    """Adversarial bugs caught: count concrete bug signals near adversarial work.

    We look for explicit "N real bug(s) found", and for named race-condition
    classes (TOCTOU / race) that the logs use to describe caught bugs.
    """
    t = text or ""
    bugs = 0
    notes = []
    for m in re.finditer(r"(\d+)\s+real\s+bug", t, re.IGNORECASE):
        bugs += int(m.group(1))
    # Named bug classes the adversarial pass is documented to catch.
    for kw in ("TOCTOU", "race condition", "concurrent dismissal"):
        if re.search(re.escape(kw), t, re.IGNORECASE):
            notes.append(kw)
    has_adversarial = bool(re.search(r"adversarial", t, re.IGNORECASE))
    # If adversarial work happened and named a concrete bug class but gave no
    # explicit count, credit at least 1 caught bug.
    if bugs == 0 and has_adversarial and notes:
        bugs = 1
    return {"bugs": bugs, "adversarial": has_adversarial, "classes": sorted(set(notes))}


def _extract_lessons(text):
    """Pull 'lesson' / 'gate hole' / 'findings logged' style takeaways.

    Returns a short list of one-line lessons (deduped, trimmed).
    """
    t = text or ""
    lessons = []
    # Headed sections we treat as lessons.
    for m in re.finditer(
        r"^#{1,4}\s*(?:Gate hole|Lessons?|Findings|Remaining Caveat|Caveats?)\b[^\n]*\n(.*?)(?=\n#{1,4}\s|\Z)",
        t, re.MULTILINE | re.DOTALL | re.IGNORECASE,
    ):
        block = m.group(1).strip()
        for line in block.splitlines():
            line = line.strip().lstrip("-*0123456789. ").strip()
            if len(line) > 8:
                lessons.append(line)
    # Bold inline "Gate hole captured" markers.
    for m in re.finditer(r"\*\*([^*]*?(?:gate hole|lesson)[^*]*?)\*\*", t, re.IGNORECASE):
        lessons.append(m.group(1).strip())
    # Dedup, keep order, cap length.
    seen, out = set(), []
    for l in lessons:
        key = l.lower()[:80]
        if key not in seen:
            seen.add(key)
            out.append(l if len(l) <= 240 else l[:237] + "...")
    return out[:6]


def _summarize_trace(events):
    """Reduce trace events to dashboard-facing totals + a step list."""
    if not events:
        return None
    last = events[-1]
    cum_tokens = last.get("cum_tokens")
    # cum_cost may be null (poisoned by an unpriced model). Take the last
    # non-null running total if the very last is null but earlier ones weren't.
    cum_cost = last.get("cum_cost_usd")
    if cum_cost is None:
        for e in reversed(events):
            if e.get("cum_cost_usd") is not None:
                cum_cost = e["cum_cost_usd"]
                break
    return {
        "n_events": len(events),
        "cum_tokens": cum_tokens,
        "cum_cost_usd": cum_cost,
        "cost_known": last.get("cum_cost_usd") is not None,
        "events": events,
    }


def parse_run(run_dir):
    """Parse a single run directory into a dashboard record dict."""
    name = os.path.basename(run_dir.rstrip("/"))
    log_name, log_text = _find_log(run_dir)
    date = _extract_date(name, log_text)
    status = _extract_status(log_text)
    plan = _extract_plan_rounds(run_dir, log_text)
    adv = _extract_adversarial(log_text)
    trace = _summarize_trace(read_trace(run_dir))

    return {
        "name": name,
        "dir": run_dir,
        "date": date,
        "log_name": log_name,
        "log_text": log_text,
        "status": status,
        "iterations": _extract_iterations(log_text),
        "plan": plan,
        "adversarial": adv,
        "verdict": _extract_verdict(log_text),
        "lessons": _extract_lessons(log_text),
        "trace": trace,
    }


def discover_runs(roots):
    """Find run directories under each root (immediate subdirectories that look
    like runs — i.e. contain at least one known log file or a trace)."""
    runs = []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            d = os.path.join(root, name)
            if not os.path.isdir(d):
                continue
            has_log = any(os.path.exists(os.path.join(d, c)) for c in LOG_CANDIDATES)
            has_trace = os.path.exists(os.path.join(d, "trace.jsonl"))
            if has_log or has_trace:
                runs.append(parse_run(d))
    # Newest first by date then name.
    runs.sort(key=lambda r: (r["date"], r["name"]), reverse=True)
    return runs


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _esc(s):
    return html.escape(s if s is not None else "")


def _fmt_cost(c):
    if c is None:
        return "—"
    return "${:,.2f}".format(c) if c >= 0.005 else "<$0.01"


def _fmt_tokens(t):
    if t is None:
        return "—"
    if t >= 1000:
        return "{:,}".format(t)
    return str(t)


STATUS_LABELS = {"pass": "PASS", "done": "DONE", "fail": "FAIL", "unknown": "UNKNOWN"}


def _summary_stats(runs):
    total = len(runs)
    passes = sum(1 for r in runs if r["status"] in ("pass", "done"))
    fails = sum(1 for r in runs if r["status"] == "fail")
    bugs = sum(r["adversarial"]["bugs"] for r in runs)
    plan_rounds = sum(r["plan"]["rounds"] for r in runs)
    with_trace = sum(1 for r in runs if r["trace"])
    pass_rate = (passes / total * 100) if total else 0.0
    return {
        "total": total, "passes": passes, "fails": fails, "bugs": bugs,
        "plan_rounds": plan_rounds, "with_trace": with_trace,
        "pass_rate": pass_rate,
    }


def _render_trace_table(trace):
    rows = []
    for e in trace["events"]:
        et = _esc(e.get("event_type"))
        role = _esc(e.get("role") or "")
        model = _esc(e.get("model") or "")
        it = e.get("iteration")
        it = str(it) if it is not None else ""
        ti = e.get("tokens_in")
        to = e.get("tokens_out")
        toks = ""
        if ti is not None or to is not None:
            toks = "{}/{}".format(ti if ti is not None else "?", to if to is not None else "?")
        cum = _fmt_tokens(e.get("cum_tokens"))
        cost = _fmt_cost(e.get("cum_cost_usd"))
        verdict = _esc(e.get("verdict") or e.get("outcome") or "")
        note = _esc(e.get("note") or "")
        vclass = ""
        v = (e.get("verdict") or "").upper()
        if "PASS" in v:
            vclass = "v-pass"
        elif "FAIL" in v:
            vclass = "v-fail"
        rows.append(
            "<tr><td>{ts}</td><td><span class='ev'>{et}</span></td><td>{role}</td>"
            "<td class='mono'>{model}</td><td>{it}</td><td class='mono'>{toks}</td>"
            "<td class='mono'>{cum}</td><td class='mono'>{cost}</td>"
            "<td class='{vclass}'>{verdict}</td><td class='note'>{note}</td></tr>".format(
                ts=_esc(e.get("ts") or ""), et=et, role=role, model=model, it=it,
                toks=toks, cum=cum, cost=cost, vclass=vclass, verdict=verdict, note=note,
            )
        )
    return (
        "<div class='trace'><table class='trace-tbl'><thead><tr>"
        "<th>ts</th><th>event</th><th>role</th><th>model</th><th>iter</th>"
        "<th>tok in/out</th><th>cum tok</th><th>cum $</th><th>verdict</th><th>note</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _render_card(run, idx):
    s = run["status"]
    badge = STATUS_LABELS.get(s, "UNKNOWN")
    chips = []
    chips.append("<span class='chip'>iters: {}</span>".format(run["iterations"]))
    if run["plan"]["rounds"]:
        chips.append("<span class='chip'>plan-check: {} ({}✗/{}✓)</span>".format(
            run["plan"]["rounds"], run["plan"]["fails"], run["plan"]["passes"]))
    if run["adversarial"]["adversarial"]:
        b = run["adversarial"]["bugs"]
        chips.append("<span class='chip chip-bug'>adversarial bugs: {}</span>".format(b))
    if run["verdict"]:
        chips.append("<span class='chip'>{}</span>".format(_esc(run["verdict"])))
    if run["trace"]:
        tr = run["trace"]
        chips.append("<span class='chip chip-trace'>trace: {} steps · {} tok · {}</span>".format(
            tr["n_events"], _fmt_tokens(tr["cum_tokens"]), _fmt_cost(tr["cum_cost_usd"])))

    lessons_html = ""
    if run["lessons"]:
        items = "".join("<li>{}</li>".format(_esc(l)) for l in run["lessons"])
        lessons_html = "<div class='lessons'><h4>Lessons</h4><ul>{}</ul></div>".format(items)

    trace_html = ""
    if run["trace"]:
        trace_html = "<h4>Live trace</h4>" + _render_trace_table(run["trace"])

    log_html = "<pre class='log'>{}</pre>".format(_esc(run["log_text"]) or "<em>(no log text)</em>")

    return (
        "<details class='card status-{s}'>"
        "<summary>"
        "<span class='dot'></span>"
        "<span class='run-name'>{name}</span>"
        "<span class='run-date'>{date}</span>"
        "<span class='status-badge'>{badge}</span>"
        "<span class='chips'>{chips}</span>"
        "</summary>"
        "<div class='card-body'>"
        "<div class='meta'>dir: <span class='mono'>{dir}</span> · log: <span class='mono'>{logname}</span></div>"
        "{lessons}{trace}"
        "<h4>Run log ({logname})</h4>{log}"
        "</div></details>"
    ).format(
        s=s, name=_esc(run["name"]), date=_esc(run["date"] or "—"), badge=badge,
        chips="".join(chips), dir=_esc(run["dir"]), logname=_esc(run["log_name"] or "—"),
        lessons=lessons_html, trace=trace_html, log=log_html,
    )


def render_html(runs, roots):
    stats = _summary_stats(runs)
    cards = "".join(_render_card(r, i) for i, r in enumerate(runs))
    if not runs:
        cards = ("<div class='empty'>No runs found under:<br>" +
                 "<br>".join(_esc(r) for r in roots) +
                 "<br><br>Run a build with the loop-team, then regenerate.</div>")

    roots_line = " · ".join(_esc(r) for r in roots)
    import datetime as _dt
    generated = _dt.datetime.now().replace(microsecond=0).isoformat()

    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Loop Team — Run Dashboard</title>
<style>
  :root {{
    --bg:#0f1115; --panel:#171a21; --panel2:#1e222b; --ink:#e6e8ec; --muted:#9aa3b2;
    --line:#2a2f3a; --pass:#34d399; --fail:#f87171; --done:#60a5fa; --unknown:#9aa3b2;
    --bug:#fbbf24; --accent:#818cf8;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:24px 20px 64px; }}
  header h1 {{ margin:0 0 4px; font-size:22px; letter-spacing:.2px; }}
  header .sub {{ color:var(--muted); font-size:12.5px; }}
  .mono {{ font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  .stats {{ display:flex; flex-wrap:wrap; gap:12px; margin:20px 0 8px; }}
  .stat {{ background:var(--panel); border:1px solid var(--line); border-radius:12px;
    padding:14px 18px; min-width:128px; flex:1; }}
  .stat .n {{ font-size:26px; font-weight:700; }}
  .stat .l {{ color:var(--muted); font-size:11.5px; text-transform:uppercase; letter-spacing:.6px; }}
  .stat.pass .n {{ color:var(--pass); }} .stat.bug .n {{ color:var(--bug); }}
  .controls {{ display:flex; gap:8px; align-items:center; margin:14px 0 6px; flex-wrap:wrap; }}
  .controls input {{ background:var(--panel2); border:1px solid var(--line); color:var(--ink);
    padding:7px 11px; border-radius:8px; font-size:13px; min-width:220px; }}
  .filter-btn {{ background:var(--panel2); border:1px solid var(--line); color:var(--muted);
    padding:6px 12px; border-radius:999px; cursor:pointer; font-size:12.5px; }}
  .filter-btn.active {{ color:var(--ink); border-color:var(--accent); }}
  .card {{ background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--unknown);
    border-radius:12px; margin:10px 0; overflow:hidden; }}
  .card.status-pass {{ border-left-color:var(--pass); }}
  .card.status-done {{ border-left-color:var(--done); }}
  .card.status-fail {{ border-left-color:var(--fail); }}
  summary {{ list-style:none; cursor:pointer; padding:13px 16px; display:flex; align-items:center;
    gap:10px; flex-wrap:wrap; }}
  summary::-webkit-details-marker {{ display:none; }}
  .dot {{ width:9px; height:9px; border-radius:50%; background:var(--unknown); flex:none; }}
  .status-pass .dot {{ background:var(--pass); }} .status-done .dot {{ background:var(--done); }}
  .status-fail .dot {{ background:var(--fail); }}
  .run-name {{ font-weight:600; }}
  .run-date {{ color:var(--muted); font-size:12px; }}
  .status-badge {{ font-size:11px; font-weight:700; letter-spacing:.5px; padding:2px 8px;
    border-radius:999px; background:var(--panel2); color:var(--muted); }}
  .status-pass .status-badge {{ color:var(--pass); }} .status-done .status-badge {{ color:var(--done); }}
  .status-fail .status-badge {{ color:var(--fail); }}
  .chips {{ display:flex; gap:6px; flex-wrap:wrap; margin-left:auto; }}
  .chip {{ font-size:11px; color:var(--muted); background:var(--panel2); border:1px solid var(--line);
    padding:2px 8px; border-radius:999px; }}
  .chip-bug {{ color:var(--bug); border-color:#4a3b15; }}
  .chip-trace {{ color:var(--accent); border-color:#332f5e; }}
  .card-body {{ padding:4px 16px 16px; border-top:1px solid var(--line); }}
  .meta {{ color:var(--muted); font-size:11.5px; margin:10px 0; }}
  h4 {{ margin:16px 0 8px; font-size:12.5px; text-transform:uppercase; letter-spacing:.6px; color:var(--muted); }}
  .lessons ul {{ margin:4px 0; padding-left:18px; }} .lessons li {{ margin:3px 0; }}
  pre.log {{ background:var(--bg); border:1px solid var(--line); border-radius:8px; padding:12px;
    max-height:360px; overflow:auto; white-space:pre-wrap; font-size:12px;
    font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace; }}
  .trace {{ overflow:auto; border:1px solid var(--line); border-radius:8px; }}
  table.trace-tbl {{ border-collapse:collapse; width:100%; font-size:11.5px; }}
  .trace-tbl th, .trace-tbl td {{ padding:5px 8px; border-bottom:1px solid var(--line); text-align:left;
    white-space:nowrap; vertical-align:top; }}
  .trace-tbl th {{ color:var(--muted); position:sticky; top:0; background:var(--panel2); }}
  .trace-tbl td.note {{ white-space:normal; color:var(--muted); }}
  .ev {{ background:var(--panel2); padding:1px 6px; border-radius:6px; }}
  .v-pass {{ color:var(--pass); font-weight:600; }} .v-fail {{ color:var(--fail); font-weight:600; }}
  .empty {{ background:var(--panel); border:1px dashed var(--line); border-radius:12px;
    padding:40px; text-align:center; color:var(--muted); line-height:1.8; }}
  footer {{ margin-top:30px; color:var(--muted); font-size:11.5px; }}
</style></head>
<body><div class="wrap">
  <header>
    <h1>Loop Team — Run Dashboard</h1>
    <div class="sub">Are my agents running as I want? · generated {generated}<br>roots: <span class="mono">{roots}</span></div>
  </header>

  <div class="stats">
    <div class="stat"><div class="n">{total}</div><div class="l">Total runs</div></div>
    <div class="stat pass"><div class="n">{pass_rate:.0f}%</div><div class="l">Pass rate</div></div>
    <div class="stat"><div class="n">{passes}</div><div class="l">Pass / Done</div></div>
    <div class="stat"><div class="n">{fails}</div><div class="l">Fail</div></div>
    <div class="stat bug"><div class="n">{bugs}</div><div class="l">Adversarial bugs caught</div></div>
    <div class="stat"><div class="n">{plan_rounds}</div><div class="l">Plan-check rounds</div></div>
    <div class="stat"><div class="n">{with_trace}</div><div class="l">Runs with live trace</div></div>
  </div>

  <div class="controls">
    <input id="q" type="text" placeholder="filter runs by name / text…" oninput="applyFilters()">
    <button class="filter-btn active" data-f="all" onclick="setFilter(this)">All</button>
    <button class="filter-btn" data-f="pass" onclick="setFilter(this)">Pass/Done</button>
    <button class="filter-btn" data-f="fail" onclick="setFilter(this)">Fail</button>
    <button class="filter-btn" data-f="trace" onclick="setFilter(this)">Has trace</button>
    <button class="filter-btn" data-f="bugs" onclick="setFilter(this)">Bugs caught</button>
  </div>

  <div id="runs">{cards}</div>

  <footer>Self-contained · stdlib-only generator · regenerate with
    <span class="mono">python3 dashboard.py</span></footer>
</div>
<script>
  var FILTER = "all";
  function setFilter(btn) {{
    FILTER = btn.getAttribute("data-f");
    document.querySelectorAll(".filter-btn").forEach(function(b){{ b.classList.remove("active"); }});
    btn.classList.add("active");
    applyFilters();
  }}
  function applyFilters() {{
    var q = (document.getElementById("q").value || "").toLowerCase();
    document.querySelectorAll(".card").forEach(function(card) {{
      var text = card.textContent.toLowerCase();
      var cls = card.className;
      var passF = true;
      if (FILTER === "pass") passF = /status-(pass|done)/.test(cls);
      else if (FILTER === "fail") passF = /status-fail/.test(cls);
      else if (FILTER === "trace") passF = card.querySelector(".chip-trace") != null;
      else if (FILTER === "bugs") passF = card.querySelector(".chip-bug") != null;
      var passQ = !q || text.indexOf(q) !== -1;
      card.style.display = (passF && passQ) ? "" : "none";
    }});
  }}
</script>
</body></html>
""".format(
        generated=_esc(generated), roots=roots_line,
        total=stats["total"], pass_rate=stats["pass_rate"], passes=stats["passes"],
        fails=stats["fails"], bugs=stats["bugs"], plan_rounds=stats["plan_rounds"],
        with_trace=stats["with_trace"], cards=cards,
    )


def build(roots=None, out="dashboard.html"):
    roots = roots or DEFAULT_ROOTS
    runs = discover_runs(roots)
    html_text = render_html(runs, roots)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    return out, runs


def main():
    ap = argparse.ArgumentParser(description="Render the Loop Team run dashboard.")
    ap.add_argument("--out", default="dashboard.html", help="output HTML path")
    ap.add_argument("--root", action="append", dest="roots",
                    help="run root dir (repeatable); defaults to the two LoopTeam roots")
    args = ap.parse_args()
    out, runs = build(roots=args.roots, out=args.out)
    print("Wrote {} ({} run(s)).".format(out, len(runs)))
    for r in runs:
        tr = " trace={}ev".format(r["trace"]["n_events"]) if r["trace"] else ""
        print("  - {:<40} {:<7} iters={} plan={} bugs={}{}".format(
            r["name"], r["status"], r["iterations"], r["plan"]["rounds"],
            r["adversarial"]["bugs"], tr))


if __name__ == "__main__":
    main()
