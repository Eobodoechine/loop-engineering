#!/usr/bin/env python3
"""product_dashboard.py — LoopTeam: the per-product "where am I / is it really
fixed" board. Renders one glanceable, self-contained HTML page from the
``status.json`` files written by ``reality_gate.py``.

Stdlib only. No network, no external deps. The output HTML inlines all CSS
(no external stylesheet/script/resource references except intentional GitHub
commit links), so it is safe to open or serve anywhere — matching the
conventions of the sibling ``dashboard.py``.

Usage:
    python3 product_dashboard.py [--status <path> ...] [--glob <pattern> ...] [--out product_dashboard.html]

Flags:
  --status <path>   An explicit status.json path (repeatable).
  --glob <pattern>  A glob used to DISCOVER status.json files (repeatable),
                    e.g. ``~/Claude/Projects/*/status.json``.
  --out <path>      Output HTML file (default ``product_dashboard.html``).
  --serve [PORT]    Nice-to-have; not implemented (prints a notice).

Discovery: with neither --status nor --glob, two default globs are used to
discover status.json files: ``~/Claude/Projects/*/status.json`` and
``~/Claude/Projects/*/.loop/status.json``. Discovered paths are de-duplicated;
missing files are skipped; a present-but-invalid-JSON file becomes an ERROR
card (it never crashes the whole render).

Badge rule (the core "is it really done?" distinction), one badge per item:
  * VERIFIED (green) iff the item's ``verified`` is true — a ground-truth check
    passed.
  * CLAIMED (amber) iff not verified AND ``status == "fixed"`` — an agent said
    it was fixed but no ground-truth check has confirmed it.
  * else a phase badge showing the item's phase (must / doing / built / broken;
    broken is red), or a grey ``other`` badge for an absent/unknown phase.

The header rollup chips are a partition of the items: each item counts in
EXACTLY one bucket (verified > claimed > broken > doing > must > built > other,
first match wins), so the shown non-zero chip counts sum to the item count.
"""
import argparse
import glob as _glob
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

# Default discovery globs, used only when neither --status nor --glob is given.
DEFAULT_GLOBS = [
    os.path.expanduser("~/Claude/Projects/*/status.json"),
    os.path.expanduser("~/Claude/Projects/*/.loop/status.json"),
]

# The four known phases (anything else is bucketed as "other").
KNOWN_PHASES = ("must", "doing", "built", "broken")

# Sort order for the item list: broken first ... other last.
PHASE_SORT = {"broken": 0, "doing": 1, "must": 2, "built": 3, "other": 4}

# Display order for the rollup chip row (only non-zero buckets are shown).
ROLLUP_ORDER = ("verified", "claimed", "broken", "doing", "must", "built", "other")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(s):
    """HTML-escape a value (None -> "")."""
    return html.escape(s if s is not None else "")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, ValueError):
        return None


def discover_paths(status_paths, globs):
    """Resolve the ordered, de-duplicated list of status.json paths to render.

    Explicit --status paths come first, then glob expansions. Missing files are
    skipped. Duplicates (by absolute path) are removed while preserving order.
    """
    ordered = []
    seen = set()

    def _add(p):
        ap = os.path.abspath(os.path.expanduser(p))
        if ap in seen:
            return
        if not os.path.isfile(ap):
            return
        seen.add(ap)
        ordered.append(ap)

    for s in status_paths or []:
        _add(s)
    patterns = list(globs or [])
    if not (status_paths or globs):
        patterns = list(DEFAULT_GLOBS)
    for pat in patterns:
        for hit in sorted(_glob.glob(os.path.expanduser(pat))):
            _add(hit)
    return ordered


def _origin_url(repo_dir):
    """Best-effort read of the ``origin`` remote url from ``repo_dir/.git/config``.

    Pure file read (no ``git``, no network). Returns the url string or None if
    the config is missing/unreadable/unparseable — never raises.
    """
    cfg = os.path.join(repo_dir, ".git", "config")
    text = _read(cfg)
    if text is None:
        return None
    in_origin = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_origin = stripped.replace(" ", "").lower() == '[remote"origin"]'
            continue
        if in_origin:
            m = re.match(r"url\s*=\s*(.+)", stripped)
            if m:
                return m.group(1).strip()
    return None


def _github_repo_base(origin):
    """Normalize an origin url to ``https://github.com/O/R`` — but ONLY when the
    host is literally ``github.com``. Any other host or an unparseable url
    returns None (so the commit renders as a plain-text sha, never a wrong link).
    """
    if not origin:
        return None
    o = origin.strip()
    host = path = None
    m = re.match(r"git@([^:/]+):(.+)$", o)  # scp-like: git@host:owner/repo.git
    if m:
        host, path = m.group(1), m.group(2)
    else:
        m = re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*://(?:[^@/]+@)?([^/:]+)(?::\d+)?/(.+)$", o)
        if m:
            host, path = m.group(1), m.group(2)
    if host is None or host.lower() != "github.com":
        return None
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not path:
        return None
    return "https://github.com/" + path


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def _norm_item(raw):
    """Normalize one raw item dict, applying the spec's defaults."""
    if not isinstance(raw, dict):
        raw = {}
    title = raw.get("title")
    if not title:
        title = "(untitled)"
    status = raw.get("status")
    if not status:
        status = "claimed"
    verified = bool(raw.get("verified"))
    prio = raw.get("priority")
    if isinstance(prio, bool) or not isinstance(prio, int):
        prio = 9999
    phase = raw.get("phase")
    return {
        "title": title,
        "status": status,
        "verified": verified,
        "priority": prio,
        "phase": phase,
        "problems": raw.get("problems") if isinstance(raw.get("problems"), list) else [],
        "evidence": raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {},
    }


def _phase_bucket(item):
    """The item's phase group for sorting/rollup fallback ('other' if unknown)."""
    p = item["phase"]
    return p if p in KNOWN_PHASES else "other"


def _rollup_bucket(item):
    """The single partition bucket for an item (badge-primary, first match wins)."""
    if item["verified"]:
        return "verified"
    if item["status"] == "fixed":
        return "claimed"
    return _phase_bucket(item)


def _badge(item):
    """Return (text, class_token) for the item's single status badge."""
    if item["verified"]:
        return "VERIFIED", "verified"
    if item["status"] == "fixed":
        return "CLAIMED", "claimed"
    p = item["phase"]
    if p in KNOWN_PHASES:
        return p, p
    # Unknown/absent phase -> grey "other" badge showing the literal phase.
    return (p if p else "other"), "other"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _render_commit(commit, gh_base):
    """Render evidence.commit: a GitHub link when resolvable, else plain sha."""
    if not commit:
        return ""
    sha = str(commit)
    if gh_base:
        href = gh_base + "/commit/" + sha
        return '<a href="{}"><code>{}</code></a>'.format(_esc(href), _esc(sha))
    return "<code>{}</code>".format(_esc(sha))


def _render_evidence(item, gh_base):
    """Render the collapsible <details> for an item's evidence + problems."""
    ev = item["evidence"]
    problems = item["problems"]
    commit = ev.get("commit")
    test = ev.get("test")
    log = ev.get("log")
    if not (commit or test or log or problems):
        return ""
    rows = []
    if commit:
        rows.append("<div class='ev-row'>commit: {}</div>".format(_render_commit(commit, gh_base)))
    if test:
        rows.append("<div class='ev-row'>test: <code>{}</code></div>".format(_esc(str(test))))
    if log:
        rows.append("<div class='ev-row'>log: <code>{}</code></div>".format(_esc(str(log))))
    for prob in problems:
        if not isinstance(prob, dict):
            continue
        desc = _esc(str(prob.get("desc", "")))
        pev = _esc(str(prob.get("evidence", "")))
        rows.append("<div class='ev-row problem'>{}{}</div>".format(
            desc, (" — <code>{}</code>".format(pev) if pev else "")))
    return ("<details class='evidence'><summary>evidence</summary>"
            + "".join(rows) + "</details>")


def _render_item(item, gh_base):
    text, cls = _badge(item)
    details = _render_evidence(item, gh_base)
    return (
        "<div class='item'>"
        "<span class='badge {cls}'>{text}</span>"
        "<span class='item-title'>{title}</span>"
        "<span class='item-prio'>p{prio}</span>"
        "{details}"
        "</div>"
    ).format(cls=cls, text=_esc(text), title=_esc(item["title"]),
             prio=_esc(str(item["priority"])), details=details)


def _render_rollup(items):
    counts = {}
    for it in items:
        b = _rollup_bucket(it)
        counts[b] = counts.get(b, 0) + 1
    chips = []
    for bucket in ROLLUP_ORDER:
        n = counts.get(bucket, 0)
        if n:
            chips.append("<span class='rollup-chip'>{}: {}</span>".format(bucket, n))
    return "<div class='rollup'>" + "".join(chips) + "</div>"


def _render_product_card(product, gh_base, source_path=None):
    name = _esc(product["product"])
    goal = _esc(product["done_sentence"])
    updated = product["updated"]
    updated_html = ("<div class='updated'>updated: {}</div>".format(_esc(str(updated)))
                    if updated else "")
    # AC10.1: per-item DEMO marking is source-path based and applies in the
    # legacy default-glob invocation too (test 19), not only --control-plane
    # mode -- a status.json whose path contains "/demo/" carries the visible
    # .cp-demo bar.
    demo_html = ('<span class="cp-bar cp-demo">DEMO</span>'
                 if source_path and "/demo/" in source_path else "")
    items = product["items"]
    rollup = _render_rollup(items)
    if items:
        ordered = sorted(items, key=lambda it: (PHASE_SORT[_phase_bucket(it)], it["priority"]))
        body = "".join(_render_item(it, gh_base) for it in ordered)
    else:
        body = "<div class='no-items'>no items</div>"
    return (
        "<div class='product-card'>"
        "<div class='card-head'>"
        "<h2 class='product-name'>{name}</h2>"
        "<div class='goal'>{goal}</div>"
        "{demo}"
        "{updated}"
        "{rollup}"
        "</div>"
        "<div class='items'>{body}</div>"
        "</div>"
    ).format(name=name, goal=goal, demo=demo_html, updated=updated_html,
             rollup=rollup, body=body)


def _render_error_card(path):
    return (
        "<div class='error-card'>"
        "<div class='err-title'>Invalid status.json</div>"
        "<div class='err-path'><code>{}</code></div>"
        "<div class='err-note'>File is not valid JSON and was skipped.</div>"
        "</div>"
    ).format(_esc(path))


STYLE = """
  * { box-sizing: border-box; }
  body { margin: 0; background: #0f1115; color: #e6e8ec;
    font: 14px/1.5 -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; }
  .wrap { max-width: 1180px; margin: 0 auto; padding: 24px 20px 64px; }
  header h1 { margin: 0 0 4px; font-size: 22px; }
  header .sub { color: #9aa3b2; font-size: 12.5px; }
  code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 14px; margin-top: 18px; }
  .product-card, .error-card { background: #171a21; border: 1px solid #2a2f3a;
    border-radius: 12px; padding: 14px 16px; }
  .error-card { border-color: #7f1d1d; background: #1c1416; }
  .err-title { color: #f87171; font-weight: 700; }
  .err-path { color: #9aa3b2; font-size: 12px; margin: 4px 0; word-break: break-all; }
  .err-note { color: #9aa3b2; font-size: 12px; }
  .product-name { margin: 0 0 2px; font-size: 16px; }
  .goal { color: #9aa3b2; font-size: 12.5px; }
  .updated { color: #6b7280; font-size: 11.5px; margin-top: 2px; }
  .rollup { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 4px; }
  .rollup-chip { font-size: 11px; color: #cbd5e1; background: #1e222b;
    border: 1px solid #2a2f3a; padding: 2px 8px; border-radius: 999px; }
  .items { margin-top: 8px; }
  .item { display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    padding: 6px 0; border-top: 1px solid #22262f; }
  .item-title { flex: 1; }
  .item-prio { color: #6b7280; font-size: 11.5px; }
  .no-items { color: #6b7280; font-size: 12.5px; padding: 8px 0; }
  .badge { font-size: 10.5px; font-weight: 700; letter-spacing: .4px; padding: 2px 8px;
    border-radius: 999px; background: #1e222b; color: #9aa3b2; border: 1px solid #2a2f3a; }
  .badge.verified { color: #34d399; border-color: #14532d; }
  .badge.claimed { color: #fbbf24; border-color: #4a3b15; }
  .badge.broken { color: #f87171; border-color: #7f1d1d; }
  .badge.other { color: #9aa3b2; }
  details.evidence { flex-basis: 100%; margin: 4px 0 2px; }
  details.evidence summary { cursor: pointer; color: #818cf8; font-size: 12px; }
  .ev-row { color: #cbd5e1; font-size: 12px; margin: 3px 0 0 12px; }
  .ev-row.problem { color: #f0a3a3; }
  .empty { background: #171a21; border: 1px dashed #2a2f3a; border-radius: 12px;
    padding: 40px; text-align: center; color: #9aa3b2; line-height: 1.8; margin-top: 18px; }
  footer { margin-top: 30px; color: #9aa3b2; font-size: 11.5px; }

  /* --- Control-plane v1 redesign: AC2/AC3/AC9 additions (micro-step 1)
     PLUS AC4/AC5/AC6/AC7 additions (micro-step 2) PLUS the AC8 declared-
     color-contrast support and AC10 refresh-meta wiring (this, final,
     micro-step -- render_html's own body carries the AC10 <meta> markup,
     not STYLE). Every rule is a pure ADDITION -- nothing existing above
     this point is removed or altered (AC11). */
  .cp-card { background: #171a21; border: 1px solid #2a2f3a; border-radius: 12px;
    padding: 14px 16px; }
  .cp-banner { background: #1b2233; border: 1px solid #3b4252; border-radius: 12px;
    padding: 12px 16px; margin: 18px 0 4px; }
  /* AC3: three-tier visual weight, CSS-only -- .cp-weight-loud (mismatch/
     unverified-claim) is louder than the plain .cp-card baseline, which is
     in turn louder than .cp-weight-quiet (verified). Never affects DOM
     order -- see render_control_plane's own docstring. */
  .cp-weight-loud { border-color: #7f1d1d; box-shadow: 0 0 0 1px #f87171 inset; }
  .cp-weight-quiet { opacity: .78; filter: saturate(.65); }
  .cp-all-clear { color: #34d399; font-size: 13px; margin: 4px 0 14px; }

  /* AC4: one card, one concept -- product+claim is the dominant element;
     the wip/evidence axis pair, the AC-RENDER bars, and the commit row each
     get their own distinct block-level container with visible separation
     (never a run-on inline sentence). */
  .cp-head { margin-bottom: 6px; }
  .cp-product { font-size: 17px; font-weight: 700; margin-right: 10px; }
  .cp-claim { font-size: 13px; color: #9aa3b2; }
  .cp-bars { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
  .cp-bar { display: inline-block; font-size: 10.5px; font-weight: 700;
    letter-spacing: .3px; padding: 2px 8px; border-radius: 999px;
    background: #1e222b; border: 1px solid #2a2f3a; color: #cbd5e1; }
  .cp-axes { display: flex; flex-wrap: wrap; gap: 14px; margin: 8px 0;
    padding-top: 8px; border-top: 1px solid #22262f; font-size: 12.5px;
    color: #cbd5e1; }
  .cp-commit-row { margin-top: 8px; font-size: 12px; color: #9aa3b2; }

  /* AC5: redundant status encoding -- verified/mismatch bars each get a
     color-driven treatment in ADDITION to their own in-text glyph+label
     (glyph/label are markup TEXT, not CSS content, so they always survive
     copy/paste and screen readers regardless of these color rules). NOTE:
     deliberately never spelling out either class's own full dotted-class
     selector name inside THIS comment block -- a naive CSS comment/selector
     scan (as this repo's own test harness uses) glues any preceding comment
     text onto the NEXT rule's captured "selector," so a comment mentioning
     a sibling class's dotted name would falsely count as that sibling's
     own declared-color rule. Every rule immediately below is still its own
     real, single-purpose selector; only the ENGLISH prose above is
     deliberately generic. */
  .cp-bar.cp-verified { color: #34d399; border-color: #14532d; }
  .cp-bar.cp-mismatch { color: #f87171; border-color: #7f1d1d; }

  /* AC8 support: these three AC-RENDER bar classes each get their OWN
     declared (muted/informational) color -- distinct from one another, but
     all clustered close together relative to the verified/mismatch
     declared-color distance above, so claimed-vs-verified stays the single
     LOUDEST declared contrast on the page (AC8's priority constraint over
     AC3-AC5, not a separate independent item). Same naming caveat as the
     AC5 comment above: no sibling class's own dotted name is spelled out
     here, for the same comment-gluing reason. */
  .cp-bar.cp-demo { color: #93c5fd; border-color: #1e3a5f; }
  .cp-bar.cp-focus { color: #c4b5fd; border-color: #4c3a7a; }
  .cp-bar.cp-legacy-label { color: #9aa3b2; border-color: #3f4655; }

  /* AC6/AC7: an always-visible one-line verification summary rendered
     ahead of the collapsed evidence trail; the trail itself uses a native
     details/summary disclosure element (zero JS). */
  .cp-evidence-section { margin-top: 6px; }
  .cp-summary-line { font-size: 12.5px; color: #cbd5e1; margin-bottom: 4px; }
  details.cp-evidence-trail { font-size: 12px; }
  details.cp-evidence-trail summary { cursor: pointer; color: #818cf8; }
  .cp-trail-row { color: #9aa3b2; margin: 3px 0 0 12px; }
"""


def render_html(cards_html, empty, refresh_seconds=None):
    """Render the shared page shell around ``cards_html`` (the legacy
    ``build()`` grid, or the control-plane grid/banner markup).

    ``refresh_seconds`` (AC10, optional, additive): when ``None`` (the
    legacy ``build()`` call site's default -- it never passes this kwarg),
    output is byte-identical to the pre-redesign shell -- no meta tag is
    emitted. When given a real value, the emitted ``<head>`` includes a
    literal ``<meta http-equiv="refresh" content="{refresh_seconds}">`` so a
    kept-open browser tab (``render_control_plane``'s use case) refreshes
    itself periodically. Zero JS either way."""
    body = cards_html
    if empty:
        body = ("<div class='empty'>No products found.<br>"
                "Point this at some status.json files with --status or --glob, "
                "then regenerate.</div>")
    else:
        body = "<div class='grid'>" + cards_html + "</div>"
    refresh_meta = ""
    if refresh_seconds is not None:
        refresh_meta = ('<meta http-equiv="refresh" content="{}">\n'
                        .format(refresh_seconds))
    return (
        "<!doctype html>\n"
        "<html lang=\"en\"><head><meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        + refresh_meta +
        "<title>Product Dashboard</title>\n"
        "<style>" + STYLE + "</style></head>\n"
        "<body><div class=\"wrap\">\n"
        "<header><h1>Product Dashboard</h1>"
        "<div class=\"sub\">Where am I &middot; is it really fixed? "
        "(green = ground-truth check passed; amber = agent said fixed, unconfirmed)</div></header>\n"
        + body +
        "\n<footer>Self-contained &middot; stdlib-only generator</footer>\n"
        "</div></body></html>\n"
    )


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _build_product(data, path):
    """Turn parsed JSON into a normalized product dict (defaults applied)."""
    if not isinstance(data, dict):
        data = {}
    product = data.get("product") or "(unnamed product)"
    done = data.get("done_sentence") or ""
    updated = data.get("updated")
    raw_items = data.get("items")
    items = [_norm_item(it) for it in raw_items] if isinstance(raw_items, list) else []
    return {"product": product, "done_sentence": done, "updated": updated, "items": items}


def build(status_paths=None, globs=None, out="product_dashboard.html"):
    """Render the dashboard HTML to ``out``. Returns (out, rollups)."""
    paths = discover_paths(status_paths, globs)
    cards = []
    rollups = []
    for path in paths:
        text = _read(path)
        if text is None:
            cards.append(_render_error_card(path))
            rollups.append((path, "unreadable"))
            continue
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            cards.append(_render_error_card(path))
            rollups.append((path, "invalid JSON"))
            continue
        product = _build_product(data, path)
        repo_dir = os.path.dirname(path)
        gh_base = _github_repo_base(_origin_url(repo_dir))
        cards.append(_render_product_card(product, gh_base, source_path=path))
        # One-line rollup summary for stdout.
        counts = {}
        for it in product["items"]:
            b = _rollup_bucket(it)
            counts[b] = counts.get(b, 0) + 1
        summary = ", ".join("%s: %d" % (b, counts[b]) for b in ROLLUP_ORDER if counts.get(b))
        rollups.append((product["product"], summary or "no items"))

    empty = len(cards) == 0
    html_text = render_html("".join(cards), empty)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    return out, rollups


# ===========================================================================
# Control-plane dashboard slice (real-evidence gated) -- validation/schema
# layer. Spec: runs/2026-07-11_control-plane-dashboard/specs/spec.md (V9).
# Proof-record / item validation primitives (AC1-AC4, AC2 13-field schema,
# AC3/AC4/AC6.1 closed enums). Rendering, ladder derivation, discovery, and
# the CLI surface are built in later micro-steps.
# ===========================================================================

# AC3: proof_class closed enum -- exactly these 7 values, no others.
PROOF_CLASS_ENUM = frozenset({
    "unit_or_mock", "build_or_typecheck", "preflight", "live_smoke",
    "dashboard_render", "readback_cleanup", "repo_health",
})
# AC4: a proof record's claimed evidence_label closed enum -- exactly 5.
CLAIMED_EVIDENCE_LABEL_ENUM = frozenset({
    "mock-tested", "build-clean", "preflight-pass", "live-smoke-pass", "ready",
})
# AC6.1: wip_column closed enum -- exactly these 5 values, no others.
WIP_COLUMN_ENUM = frozenset({
    "Ready", "Doing", "Evidence Needed", "Blocked External", "Done Verified",
})
# AC6.3: derived-evidence_label ladder rank (used by later micro-steps).
EVIDENCE_LABEL_RANK = {
    "Unverified": 0, "mock-tested": 1, "build-clean": 2,
    "preflight-pass": 3, "live-smoke-pass": 4, "ready": 5,
}
# AC4 per-label required proof_class (self-referential). "ready" is absent --
# never a valid single-record claim (needs 2-3 classes), so always rejected.
LABEL_REQUIRED_PROOF_CLASS = {
    "mock-tested": "unit_or_mock", "build-clean": "build_or_typecheck",
    "preflight-pass": "preflight", "live-smoke-pass": "live_smoke",
}
# AC4: for these three proof_classes the per-label self-consistency check does
# NOT apply -- they carry any non-"ready" enum label as a nominal tag.
_NOMINAL_TAG_PROOF_CLASSES = frozenset({
    "dashboard_render", "readback_cleanup", "repo_health",
})
# AC2: the 12 required raw fields (the 13th, stale_or_valid, is derived).
_REQUIRED_PROOF_FIELDS = (
    "product", "claim", "evidence_label", "proof_class", "command", "cwd",
    "git_sha", "exit_code", "output_hash", "artifact_hashes", "timestamp",
    "source_artifact_path",
)
# Coder-defined, run-log-stated staleness threshold. Spec test 1 pins only
# qualitative extremes (decades-old vs "now"), never this exact number. 14
# days: a snapshot older than a fortnight is stale (soft, never a hard reject).
STALENESS_THRESHOLD_SECONDS = 14 * 24 * 60 * 60


class InvalidProofRecordError(Exception):
    """Raised by ``validate_proof_record`` for a HARD-reject condition (AC2
    missing field / AC3 or AC4 out-of-enum / AC4 label-vs-proof_class
    mismatch / a "ready" claim). Staleness is never a hard reject."""


class InvalidItemError(Exception):
    """Raised by ``validate_item`` for an out-of-enum ``wip_column`` (AC6.1),
    parallel to AC3's closure rule."""


def _parse_timestamp(value):
    """Parse an ISO-8601 timestamp string into a timezone-aware ``datetime``
    (assuming UTC if the string carries no offset). Returns None if the value
    is not a parseable ISO timestamp -- the caller treats that as stale."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):  # fromisoformat (3.9) rejects a trailing "Z"
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def validate_proof_record(record, current_head=None, recompute_artifact_hash=None,
                          now=None):
    """Validate a raw AC2 proof record; return a NEW dict = copy of ``record``
    plus the derived ``stale_or_valid`` field ("stale"/"valid").

    HARD rejects (raise ``InvalidProofRecordError``): missing required AC2
    field; out-of-enum ``proof_class`` (AC3); out-of-enum claimed
    ``evidence_label`` (AC4); a claimed label in the 4 non-"ready" values
    whose own ``proof_class`` mismatches that label's required class (AC4 --
    unless proof_class is dashboard_render/readback_cleanup/repo_health, which
    carry any non-"ready" label as a nominal tag); and any "ready" claim.

    SOFT staleness (never a raise, only in ``stale_or_valid``): git-HEAD axis
    (skipped if ``current_head`` is None); artifact-hash axis via
    ``recompute_artifact_hash`` (a None recompute => file missing => stale;
    skipped if the callable is None); and a timestamp older than
    ``STALENESS_THRESHOLD_SECONDS`` vs ``now`` (default real UTC now), or
    unparseable.
    """
    if not isinstance(record, dict):
        raise InvalidProofRecordError("proof record must be a dict")

    # AC2: every required field must be present (not silently defaulted).
    for field in _REQUIRED_PROOF_FIELDS:
        if field not in record:
            raise InvalidProofRecordError(
                "proof record missing required AC2 field: %r" % field)

    proof_class = record["proof_class"]
    evidence_label = record["evidence_label"]

    # AC3 / AC4: proof_class and claimed evidence_label must be in-enum.
    if proof_class not in PROOF_CLASS_ENUM:
        raise InvalidProofRecordError(
            "unrecognized proof_class: %r (AC3 closed enum)" % (proof_class,))
    if evidence_label not in CLAIMED_EVIDENCE_LABEL_ENUM:
        raise InvalidProofRecordError(
            "unrecognized claimed evidence_label: %r (AC4 closed enum)"
            % (evidence_label,))
    # AC4: a "ready" claim is always rejected (no single record satisfies it).
    if evidence_label == "ready":
        raise InvalidProofRecordError(
            "a single proof record can never claim 'ready' (AC4)")
    # AC4: per-label self-consistency (skipped for the nominal-tag classes).
    required_class = LABEL_REQUIRED_PROOF_CLASS.get(evidence_label)
    if required_class is not None and proof_class not in _NOMINAL_TAG_PROOF_CLASSES:
        if proof_class != required_class:
            raise InvalidProofRecordError(
                "claimed evidence_label %r requires proof_class %r, got %r "
                "(AC4)" % (evidence_label, required_class, proof_class))

    # Soft staleness across the three freshness axes.
    stale = False
    if current_head is not None and record.get("git_sha") != current_head:
        stale = True
    if recompute_artifact_hash is not None:
        artifact_hashes = record.get("artifact_hashes") or {}
        for path, stored_hash in artifact_hashes.items():
            recomputed = recompute_artifact_hash(path)
            if recomputed is None or recomputed != stored_hash:
                stale = True
                break

    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    parsed_ts = _parse_timestamp(record.get("timestamp"))
    if parsed_ts is None:
        stale = True
    else:
        age_seconds = (now - parsed_ts).total_seconds()
        if age_seconds > STALENESS_THRESHOLD_SECONDS:
            stale = True

    result = dict(record)
    result["stale_or_valid"] = "stale" if stale else "valid"
    return result


def validate_item(item):
    """Validate a NEW-shaped item's ``wip_column`` against the AC6.1 closed
    enum; return a copy. Raises ``InvalidItemError`` for an out-of-enum value
    (a legacy item, lacking ``wip_column``, is mapped down elsewhere)."""
    if not isinstance(item, dict):
        raise InvalidItemError("item must be a dict")
    wip_column = item.get("wip_column")
    if wip_column not in WIP_COLUMN_ENUM:
        raise InvalidItemError(
            "unrecognized wip_column: %r (AC6.1 closed enum)" % (wip_column,))
    return dict(item)


def build_proof_record_from_snapshot(snapshot_record, snapshot_path, *, product,
                                     claim, evidence_label, proof_class, cwd,
                                     git_sha, source_artifact_path):
    """Build a raw (NOT-yet-validated) AC2-shaped proof record from a
    ``run_and_record()`` snapshot (AC1's reuse boundary). Execution fields are
    copied byte-identically from the snapshot: ``command`` <- ``command``,
    ``exit_code`` <- ``exit_code``, ``output_hash`` <- ``output_sha256``,
    ``artifact_hashes`` <- ``files``, ``timestamp`` <- ``captured_at`` (test
    25). The other six fields come from this function's own arguments (AC2
    origin table). ``stale_or_valid`` is absent -- computed later by
    ``validate_proof_record``.
    """
    return {
        "product": product,
        "claim": claim,
        "evidence_label": evidence_label,
        "proof_class": proof_class,
        "command": snapshot_record["command"],
        "cwd": cwd,
        "git_sha": git_sha,
        "exit_code": snapshot_record["exit_code"],
        "output_hash": snapshot_record["output_sha256"],
        "artifact_hashes": snapshot_record["files"],
        "timestamp": snapshot_record["captured_at"],
        "source_artifact_path": source_artifact_path,
    }


def _joined_valid_records(item, proof_records):
    """The subset of ``proof_records`` that count toward ``item``'s derivation:
    each must be a dict, be ``stale_or_valid == "valid"`` (never stale), and
    JOIN to the item by an exact ``(product, claim)`` match (AC6.4 join key --
    a mismatched-join-key proof is ignored, test_negative_b)."""
    product = item.get("product")
    claim = item.get("claim")
    out = []
    for rec in proof_records or []:
        if not isinstance(rec, dict):
            continue
        if rec.get("stale_or_valid") != "valid":
            continue
        if rec.get("product") != product or rec.get("claim") != claim:
            continue
        out.append(rec)
    return out


def _is_genuine_live_smoke(record):
    """Whether a valid ``live_smoke`` proof genuinely earns the live-smoke-pass
    tier (AC4). Beyond being valid it must be: non-demo (its
    ``source_artifact_path`` has no ``/demo/``), non-mock (no case-insensitive
    ``mock`` substring in ``source_artifact_path`` or in any ``command`` token),
    carry a non-empty ``artifact_hashes`` dict (a readback-confirmed artifact
    hash), have recorded ``exit_code == 0`` (the command itself passed;
    test_negative_a), and a non-empty ``output_hash`` (empty/absent is vacuous,
    not genuine machine-checkable evidence; test_negative_c)."""
    if record.get("proof_class") != "live_smoke":
        return False
    if record.get("exit_code") != 0:
        return False
    if not record.get("output_hash"):
        return False
    source = record.get("source_artifact_path") or ""
    if "/demo/" in source:
        return False
    if "mock" in source.lower():
        return False
    for token in record.get("command") or []:
        if isinstance(token, str) and "mock" in token.lower():
            return False
    if not record.get("artifact_hashes"):
        return False
    return True


def derive_evidence_label(item, proof_records, live_repo_health="CLEAR"):
    """Pure top-down AC4-ladder derivation of an item's DERIVED evidence_label
    (AC4b.2) over its whole ``(product, claim)`` proof group.

    Each record in ``proof_records`` is assumed already run through
    ``validate_proof_record`` (so it carries ``stale_or_valid``). Only VALID,
    join-key-matching records count (see ``_joined_valid_records``). A record's
    OWN claimed ``evidence_label`` plays no role -- an authored claim never
    escalates the derived label; only ``proof_class`` occurrence plus the extra
    live-smoke/ready gates matter.

    Ladder (highest satisfied tier wins):
      mock-tested     <- a valid ``unit_or_mock`` proof
      build-clean     <- a valid ``build_or_typecheck`` proof
      preflight-pass  <- a valid ``preflight`` proof
      live-smoke-pass <- a valid ``live_smoke`` proof passing the genuineness
                         gates (``_is_genuine_live_smoke``)
      ready           <- live-smoke-pass achieved AND a valid ``dashboard_render``
                         proof exists AND (``item['requires_cleanup']`` is falsy
                         OR a valid ``readback_cleanup`` proof exists) AND
                         ``live_repo_health == "CLEAR"`` (AC6.4/AC9).

    Returns one of "Unverified"/"mock-tested"/"build-clean"/"preflight-pass"/
    "live-smoke-pass"/"ready"; "Unverified" when nothing valid counts.
    """
    valid = _joined_valid_records(item, proof_records)
    classes = set(rec.get("proof_class") for rec in valid)

    # Top two tiers hinge on a genuine live_smoke proof.
    if any(_is_genuine_live_smoke(rec) for rec in valid):
        has_dashboard = "dashboard_render" in classes
        cleanup_ok = (not item.get("requires_cleanup")) or ("readback_cleanup" in classes)
        if has_dashboard and cleanup_ok and live_repo_health == "CLEAR":
            return "ready"
        return "live-smoke-pass"

    if "preflight" in classes:
        return "preflight-pass"
    if "build_or_typecheck" in classes:
        return "build-clean"
    if "unit_or_mock" in classes:
        return "mock-tested"
    return "Unverified"


def _select_backing_record(item, proof_records, derived_label):
    """AC7: pick the single proof record that BACKS a given DERIVED label, so
    the renderer can show its elapsed age ("2h ago"/"14d ago"). A pure
    ADDITION built entirely from ``derive_evidence_label``'s own already-
    standalone building blocks (``_joined_valid_records``,
    ``_is_genuine_live_smoke``, ``LABEL_REQUIRED_PROOF_CLASS``,
    ``_parse_timestamp``) -- zero edits to ``derive_evidence_label`` itself
    (AC11 scope lock). Exact shape given by the spec's own AC7 code block."""
    valid = _joined_valid_records(item, proof_records)
    if derived_label in ("ready", "live-smoke-pass"):
        # Same gate derive_evidence_label itself uses for these two tiers
        # (see derive_evidence_label's own _is_genuine_live_smoke check) --
        # kept as a literal check here because LABEL_REQUIRED_PROOF_CLASS
        # deliberately omits "ready".
        candidates = [r for r in valid if _is_genuine_live_smoke(r)]
    else:
        required_class = LABEL_REQUIRED_PROOF_CLASS.get(derived_label)
        if required_class is None:
            return None  # "Unverified" (or any future non-tier label)
        candidates = [r for r in valid if r.get("proof_class") == required_class]
    if not candidates:
        return None
    # Every "valid" record has a parseable timestamp (validate_proof_record
    # marks unparseable timestamps stale) -- max() returns the FIRST maximal
    # item on ties, i.e. "most recent, ties broken by list order".
    return max(candidates, key=lambda r: _parse_timestamp(r["timestamp"]))


def wip_mismatch(wip_column, derived_label, live_repo_health="CLEAR"):
    """AC6.3 contradiction table: does an item's authored ``wip_column``
    overstate reality relative to its DERIVED ``evidence_label``?

    Uses ``EVIDENCE_LABEL_RANK`` for the ladder comparison. Returns a real
    ``bool``. Only these columns can ever contradict; any other ``wip_column``
    (including a not-yet-recognized value) returns False (no contradiction):

      "Done Verified"    -> True iff rank(derived_label) < rank("ready") OR
                            live_repo_health == "FROZEN". The OR is independent
                            (defense-in-depth per AC9): a FROZEN repo fires the
                            mismatch even for a hypothetical derived "ready".
      "Blocked External" -> True iff rank(derived_label) >= rank("live-smoke-pass").
      "Evidence Needed"  -> True iff rank(derived_label) >= rank("live-smoke-pass").
      "Ready" / "Doing"  -> always False (never fire).
    """
    rank = EVIDENCE_LABEL_RANK.get(derived_label, 0)
    if wip_column == "Done Verified":
        return rank < EVIDENCE_LABEL_RANK["ready"] or live_repo_health == "FROZEN"
    if wip_column in ("Blocked External", "Evidence Needed"):
        return rank >= EVIDENCE_LABEL_RANK["live-smoke-pass"]
    return False


# ---------------------------------------------------------------------------
# Control-plane rendering (AC-RENDER / AC6.2 / AC7 / AC10.1 / AC10.2).
# ---------------------------------------------------------------------------

def _is_legacy_item(item):
    """A control-plane item is LEGACY-SHAPED iff it lacks a ``wip_column``
    key entirely (i.e. it came from an old-shape status.json carrying
    ``title``/``status``/``verified``/``phase``/``evidence`` instead of the
    AC6 ``wip_column``/``requires_cleanup`` schema)."""
    return isinstance(item, dict) and "wip_column" not in item


def _map_legacy_wip_column(item):
    """Map a legacy-shaped item DOWN to one of the 5 real AC6.1 wip_column
    values (Coder's mapping policy). A legacy item never carried machine-
    checkable proof through this slice's validation, so it is NEVER mapped
    to ``Done Verified`` -- a legacy "verified"/"fixed" claim is exactly the
    unproven-doneness case AC10 exists to distrust. Policy:

      * a legacy ``phase == "broken"``            -> ``Blocked External``
      * a legacy ``phase == "doing"``             -> ``Doing``
      * a legacy ``phase == "must"``              -> ``Ready``
      * a legacy ``verified`` truthy OR
        ``status == "fixed"`` (a doneness claim,
        but unproven here)                        -> ``Evidence Needed``
      * anything else                             -> ``Evidence Needed``

    ``Evidence Needed`` is the deliberate default: a legacy item's authored
    claim is treated as "asserts progress, but this slice has no validated
    proof for it", which is the honest control-plane framing.
    """
    phase = item.get("phase")
    if phase == "broken":
        return "Blocked External"
    if phase == "doing":
        return "Doing"
    if phase == "must":
        return "Ready"
    return "Evidence Needed"


def _git_object_exists(repo_dir, sha):
    """True iff ``sha`` resolves to a real commit object in the git repo at
    ``repo_dir`` (``git -C <repo> cat-file -e <sha>^{commit}``). A fabricated
    / non-existent sha, a missing repo, or any git error -> False. Never
    raises (a broken/absent git environment simply means "not verifiable ->
    plain text")."""
    if not repo_dir or not sha:
        return False
    try:
        proc = subprocess.run(
            ["git", "-C", repo_dir, "cat-file", "-e", str(sha) + "^{commit}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _render_cp_commit(commit, repo_dir):
    """AC10.2 commit-badge, retiring the legacy ``_render_commit`` for
    control-plane mode: render ``commit`` as a LINKED ``/commit/<sha>`` badge
    ONLY when it is a real git object in ``repo_dir`` AND that repo has a
    resolvable github ``origin``. A fabricated/non-existent sha (or a repo
    with no github origin) renders as PLAIN, explicitly-unverified text --
    the sha is visible but carries no ``/commit/`` link."""
    if not commit:
        return ""
    sha = str(commit)
    if _git_object_exists(repo_dir, sha):
        gh_base = _github_repo_base(_origin_url(repo_dir))
        if gh_base:
            href = gh_base + "/commit/" + sha
            return ('<a class="cp-commit-link" href="{}"><code>{}</code></a>'
                    .format(_esc(href), _esc(sha)))
    return ('<code class="cp-commit-plain">{} (unverified)</code>'
            .format(_esc(sha)))


def _default_repo_health_lookup(product):
    """The real live per-product repo-health verdict (AC9): a single fresh
    ``repo_health_gate.compute_verdict`` over the live ``hardening_ledger.
    json``. This is only used when the caller passes no explicit
    ``repo_health_lookup`` (the real CLI path); every test injects a fake.

    Failure taxonomy (fail-SAFE, never falsely-verified):

    - ledger file MISSING (``FileNotFoundError``) => ``CLEAR``. No hardening
      is tracked, so a product with no ledger entry is genuinely CLEAR (0
      open items/classes).
    - ledger present + valid + product absent => ``CLEAR`` (``compute_verdict``
      already yields CLEAR for a zero-open-item repo; that path is untouched).
    - ledger PRESENT but undeterminable -- ``load_ledger`` fails to
      load/parse/validate (``repo_health_gate.LedgerError`` and its
      subclasses), is unreadable (a non-``FileNotFound`` ``OSError``), or
      contains undecodable bytes so the read raises a ``ValueError`` --
      including its ``UnicodeDecodeError`` subclass, raised by ``f.read()``
      on invalid UTF-8 BEFORE any JSON parse => ``FROZEN``. An undeterminable
      health MUST gate rendering, never silently degrade to CLEAR and risk a
      genuinely-unhealthy product rendering ``.cp-verified`` (AC9 / AC-RENDER).

    A truly-unexpected error (e.g. a bug inside ``compute_verdict``, or an
    ``ImportError`` for the always-present sibling module) is deliberately
    NOT swallowed -- it surfaces rather than being masked as a false CLEAR.
    The fail-safe is scoped to the ``load_ledger`` step ONLY;
    ``compute_verdict`` runs OUTSIDE the try/except, so a genuine bug inside
    it propagates rather than being masked as FROZEN."""
    import repo_health_gate as _rhg
    try:
        entries = _rhg.load_ledger(_rhg._default_ledger_path())
    except FileNotFoundError:
        return "CLEAR"
    except (_rhg.LedgerError, OSError, ValueError):
        return "FROZEN"
    return _rhg.compute_verdict(entries, product)["verdict"]


def _validate_item_records(item, current_head_lookup, recompute_artifact_hash):
    """Validate each RAW proof record on ``item`` (via
    ``validate_proof_record``), threading the per-record ``current_head`` (from
    ``current_head_lookup``) and ``recompute_artifact_hash`` when provided, and
    DISCARDING every hard-invalid record (``InvalidProofRecordError``). Returns
    the list of validated (``stale_or_valid``-carrying) records; a stale-but-
    not-hard-invalid record is kept (the ladder derivation drops it later)."""
    validated = []
    for raw in item.get("proof_records") or []:
        current_head = None
        if current_head_lookup is not None:
            current_head = current_head_lookup(raw)
        try:
            rec = validate_proof_record(
                raw, current_head=current_head,
                recompute_artifact_hash=recompute_artifact_hash)
        except InvalidProofRecordError:
            continue
        validated.append(rec)
    return validated


# AC5: the three redundant-encoding glyphs -- rendered in the markup TEXT
# itself (never CSS ::before alone), one per overall per-item state:
# verified (check), mismatch (warning), plain/unverified-or-claimed
# (neutral). Each is a genuinely distinct unicode character so a
# color-blind reader (or a screen reader/copy-paste) still gets a unique
# signal per state (WCAG 1.4.1, unconditional per AC5 -- brief open
# question #3 concluded "cheap to just do it right regardless").
_CP_GLYPH_VERIFIED = "✓"  # check mark (verified)
_CP_GLYPH_MISMATCH = "⚠"  # warning sign (mismatch)
_CP_GLYPH_NEUTRAL = "○"  # white circle (plain/unverified)

# AC10: auto-refresh interval (seconds) for the control-plane page, informed
# directly by Nnamdi's kept-open-browser-tab workflow answer (spec SS A) --
# not a research finding. Only render_control_plane passes this to
# render_html's refresh_seconds kwarg; the legacy build() path never does.
CP_REFRESH_SECONDS = 120


def _cp_state_glyph(verified, mismatch):
    """AC5: the single glyph representing an item's overall state -- check
    for verified, warning for mismatch, else the neutral glyph for the
    ordinary plain/unverified-or-claimed case. Verified and mismatch are
    mutually exclusive (``verified`` already requires ``not mismatch``, see
    ``_cp_item_state``), so this is an unambiguous 3-way choice."""
    if verified:
        return _CP_GLYPH_VERIFIED
    if mismatch:
        return _CP_GLYPH_MISMATCH
    return _CP_GLYPH_NEUTRAL


def _cp_render_age_text(record):
    """AC7: render a backing proof record's timestamp as a short elapsed-time
    string ("2h ago"/"14d ago"/"3m ago"), or the literal ``"age unknown"``
    fallback when there is no backing record at all (``record is None``,
    i.e. ``_select_backing_record`` returned ``None``) or -- defensively,
    should not occur for a genuinely "valid" record per
    ``validate_proof_record``'s own invariant -- its timestamp fails to
    parse. Days take priority over hours over minutes (whichever is the
    largest non-zero unit); an elapsed time of under a minute renders as
    "0m ago" (always contains "ago", never a bare "just now")."""
    if record is None:
        return "age unknown"
    parsed = _parse_timestamp(record.get("timestamp"))
    if parsed is None:
        return "age unknown"
    now = datetime.now(timezone.utc)
    seconds = (now - parsed).total_seconds()
    if seconds < 0:
        seconds = 0
    days = int(seconds // 86400)
    if days >= 1:
        return "{}d ago".format(days)
    hours = int(seconds // 3600)
    if hours >= 1:
        return "{}h ago".format(hours)
    minutes = int(seconds // 60)
    return "{}m ago".format(minutes)


def _render_cp_evidence_trail(validated_records):
    """AC6: the FULL evidence-trail detail -- every one of the item's own
    validated proof records (both ``"valid"`` and ``"stale"``; hard-invalid
    records were already discarded by ``_validate_item_records`` upstream),
    each showing its ``proof_class``, its own AUTHORED/claimed
    ``evidence_label``, its ``stale_or_valid`` verdict, and its own elapsed
    age -- wrapped in a native, collapsed-by-default ``<details
    class="cp-evidence-trail">``. Purely a new render-layer addition: it
    only reads already-validated fields and computes no new judgment of its
    own (no edits to ``validate_proof_record``/``derive_evidence_label``)."""
    if not validated_records:
        rows_html = "<div class='cp-trail-row cp-trail-empty'>No proof records on file.</div>"
    else:
        rows_html = "".join(
            "<div class='cp-trail-row cp-trail-{sv}'>{pc} &mdash; claimed {lbl} &mdash; "
            "{sv} &mdash; {age}</div>".format(
                sv=_esc(rec.get("stale_or_valid") or "unknown"),
                pc=_esc(rec.get("proof_class") or ""),
                lbl=_esc(rec.get("evidence_label") or ""),
                age=_esc(_cp_render_age_text(rec)),
            )
            for rec in validated_records
        )
    return ("<details class='cp-evidence-trail'><summary>evidence trail"
            "</summary>{}</details>").format(rows_html)


def _cp_item_state(item, focus, repo_health_lookup, current_head_lookup,
                   recompute_artifact_hash):
    """Compute one control-plane item's full render state: its per-card HTML
    fragment PLUS the page-level flags ``render_control_plane`` needs for
    layout (AC2's focus-banner grouping, AC9(b)'s calm all-clear summary) --
    derived ONCE per item so those two page-level decisions never re-run
    ``validate_proof_record``/``derive_evidence_label``/``wip_mismatch`` a
    second time. The per-card markup's four regions (product+claim / the
    wip+evidence axis pair / the AC-RENDER bars / the commit row) each
    render in their OWN distinct block-level container (AC4); the two axis
    spans and the ``.cp-verified``/``.cp-mismatch`` bars each carry a
    redundant glyph alongside their text label (AC5); a collapsed-by-default
    evidence trail plus an always-visible one-line summary render per item
    (AC6/AC7). The outer ``.cp-card`` also carries an AC3 visual-weight
    class, and the FOCUS bar also carries the literal ``cp-focus-banner``
    token (see ``_render_cp_focus_banner``'s docstring for why).

    Returns a dict: ``html`` (the card's HTML string), ``product``,
    ``focused`` (bool, ``product == focus``), ``mismatch`` (bool),
    ``verified`` (bool, the same condition that gates the ``.cp-verified``
    bar)."""
    product = item.get("product")
    source_path = item.get("source_path") or ""
    legacy = _is_legacy_item(item)

    # Axis 1: the authored (or legacy-mapped) wip_column.
    if legacy:
        wip_column = _map_legacy_wip_column(item)
    else:
        wip_column = item.get("wip_column")

    # Axis 2: the DERIVED evidence_label over the item's VALID proof records.
    valid_records = _validate_item_records(
        item, current_head_lookup, recompute_artifact_hash)
    if repo_health_lookup is not None:
        live_health = repo_health_lookup(product)
    else:
        live_health = _default_repo_health_lookup(product)
    derived = derive_evidence_label(item, valid_records, live_repo_health=live_health)

    mismatch = wip_mismatch(wip_column, derived, live_health)
    focused = focus is not None and product == focus
    verified = (wip_column == "Done Verified" and derived == "ready" and not mismatch)

    # AC5: the single glyph for this item's overall state, redundant with
    # (never a substitute for) the color-driven CSS class -- shared by the
    # two axis spans below and, where applicable, the .cp-verified/
    # .cp-mismatch bars.
    state_glyph = _cp_state_glyph(verified, mismatch)

    # AC-RENDER bars: each a dedicated, plain, visible <span> (never inside a
    # collapsed <details>, never display:none) in the card header region.
    bars = []
    if "/demo/" in source_path:
        bars.append('<span class="cp-bar cp-demo">DEMO</span>')
    if mismatch:
        # AC5: a warning glyph alongside the existing plain-language label --
        # status must never be distinguishable by color alone.
        bars.append('<span class="cp-bar cp-mismatch">{glyph} '
                    'MISMATCH: authored column contradicts machine-checkable '
                    'evidence</span>'.format(glyph=_CP_GLYPH_MISMATCH))
    if focused:
        # AC2: this bar ALSO carries the literal "cp-focus-banner" marker
        # token (in ADDITION to the pre-existing "cp-focus" token) -- see
        # _render_cp_focus_banner's docstring for why the wrapping element
        # itself is deliberately NOT named "cp-focus-banner".
        bars.append('<span class="cp-bar cp-focus cp-focus-banner">FOCUS</span>')
    if legacy:
        bars.append('<span class="cp-bar cp-legacy-label">'
                    'legacy status mapped down &mdash; unproven</span>')
    if verified:
        # AC5: a check glyph alongside the existing plain-language label.
        bars.append('<span class="cp-bar cp-verified">{glyph} VERIFIED</span>'
                    .format(glyph=_CP_GLYPH_VERIFIED))

    # Base display elements -- the two axes, never conflated. AC5: each
    # carries the shared state glyph (redundant encoding) alongside its own
    # plain-language text; AC4: both live inside ONE shared block-level
    # container, distinct from product+claim/bars/commit-row.
    wip_html = '<span class="cp-wip">{g} {t}</span>'.format(
        g=state_glyph, t=_esc(wip_column))
    evidence_html = '<span class="cp-evidence">{g} {t}</span>'.format(
        g=state_glyph, t=_esc(derived))

    # AC10.2: a legacy item carrying evidence.commit renders a validated
    # commit badge (linked only for a real git object; plain text otherwise).
    commit_html = ""
    if legacy:
        evidence = item.get("evidence")
        if isinstance(evidence, dict) and evidence.get("commit"):
            repo_dir = os.path.dirname(source_path) if source_path else ""
            commit_html = ("<div class='cp-commit-row'>commit: {}</div>"
                           .format(_render_cp_commit(evidence.get("commit"),
                                                     repo_dir)))

    # AC3: three-tier visual weight, CSS-only. A mismatch/unverified-claim
    # item gets the "loud" tier; a verified item gets the "quiet" tier;
    # anything else (in-progress -- neither confirmed problematic nor fully
    # verified) is the implicit middle/neutral tier via the plain .cp-card
    # baseline (no extra class needed). This is purely an added CSS class on
    # the existing outer wrapper -- it never changes DOM emission order (see
    # render_control_plane's own docstring for the order guarantee).
    weight_cls = ""
    if mismatch:
        weight_cls = " cp-weight-loud"
    elif verified:
        weight_cls = " cp-weight-quiet"

    # AC6/AC7: an always-visible one-line verification summary (rendered
    # AHEAD of the collapsed evidence trail, never hidden behind it) showing
    # the item's overall state glyph/word plus the elapsed age of its own
    # AC7 backing record -- "age unknown" when no record backs the derived
    # label (an untiered "Unverified" label, or zero qualifying candidates).
    backing_record = _select_backing_record(item, valid_records, derived)
    age_text = _cp_render_age_text(backing_record)
    summary_word = "verified" if verified else ("mismatch" if mismatch else derived)
    summary_line_html = (
        "<div class='cp-summary-line'>{glyph} {word} &middot; {age}</div>"
    ).format(glyph=state_glyph, word=_esc(summary_word), age=_esc(age_text))
    evidence_trail_html = _render_cp_evidence_trail(valid_records)

    card_html = (
        "<div class='cp-card{weight}'>"
        "<div class='cp-head'>"
        "<span class='cp-product'>{product}</span>"
        "<span class='cp-claim'>{claim}</span>"
        "</div>"
        "<div class='cp-bars'>{bars}</div>"
        "<div class='cp-axes'>{wip}{evidence}</div>"
        "<div class='cp-evidence-section'>{summary}{trail}</div>"
        "{commit}"
        "</div>"
    ).format(
        weight=weight_cls,
        product=_esc(product if product is not None else ""),
        claim=_esc(item.get("claim") if item.get("claim") is not None else ""),
        bars="".join(bars), wip=wip_html, evidence=evidence_html,
        summary=summary_line_html, trail=evidence_trail_html,
        commit=commit_html,
    )

    return {
        "html": card_html,
        "product": product,
        "focused": focused,
        "mismatch": mismatch,
        "verified": verified,
    }


def _render_cp_card(item, focus, repo_health_lookup, current_head_lookup,
                    recompute_artifact_hash):
    """Render one control-plane item card: the AC-RENDER bars plus the two
    always-present base display elements (``.cp-wip`` = authored/legacy-mapped
    wip_column; ``.cp-evidence`` = DERIVED evidence_label). Each value renders
    in its OWN dedicated element so the two axes are never conflated (test 8/
    16): the authored column string is emitted ONLY inside ``.cp-wip`` and the
    derived label ONLY inside ``.cp-evidence``.

    A thin wrapper over ``_cp_item_state`` (same signature as before this
    redesign) -- kept as the stable, documented single-item entry point;
    ``render_control_plane`` calls ``_cp_item_state`` directly so its own
    page-level aggregation (AC2 banner grouping, AC9(b) all-clear) never
    re-derives the same per-item state twice."""
    return _cp_item_state(item, focus, repo_health_lookup, current_head_lookup,
                          recompute_artifact_hash)["html"]


def _render_cp_focus_banner(cards_html):
    """AC2: wrap one or more focused items' UNCHANGED card markup inside a
    single, visually distinct banner section -- a RELOCATION of the existing
    per-item ``.cp-focus`` marking (which item gets marked is untouched by
    this function), never a duplicate render.

    Deliberately named ``cp-banner``, NOT ``cp-focus-banner``: this repo's
    own test helpers (``_count_class``/``_has_class`` in
    test_control_plane_dashboard.py) match a class token via a
    ``\\bTOKEN\\b`` regex, which is fooled by a compound class name sharing a
    hyphenated prefix -- naming this wrapper literally ``cp-focus-banner``
    would make its own class attribute ALSO count as an extra, spurious
    ``.cp-focus`` occurrence (confirmed by direct experiment: a bare
    ``class='cp-focus-banner'`` attribute alone matches the ``cp-focus``
    token pattern), silently breaking the "identical total .cp-focus count"
    regression contract this same AC requires. The per-item FOCUS bar
    itself (see ``_cp_item_state``) carries the literal ``cp-focus-banner``
    token instead -- a real marker on a real element genuinely inside the
    real banner section, without the counting collision."""
    return "<div class='cp-banner'>" + cards_html + "</div>"


def _render_cp_all_clear(verified_count, mismatch_count):
    """AC9(b): a calm, explicit affirmative one-line summary. The caller
    renders this ONLY when >=1 item exists, no focus is active/matched, and
    zero items carry ``.cp-mismatch`` -- computed purely from already-derived
    per-item values (no new schema)."""
    return ("<div class='cp-all-clear'>Nothing needs attention &mdash; "
            "{v} verified, {m} mismatches</div>").format(
        v=verified_count, m=mismatch_count)


def _insert_before_grid(html_text, prefix_html):
    """Insert AC2's focus banner / AC9(b)'s all-clear summary into the
    already-rendered page HTML immediately BEFORE the ``<div class='grid'>``
    wrapper -- a true DOM sibling preceding the grid container, matching
    AC2's literal "positioned in the DOM before the .grid" wording, while
    leaving ``render_html``'s own wrapping logic completely untouched this
    micro-step (its only sanctioned edit is AC10's later, separate
    ``refresh_seconds`` kwarg). Returns ``html_text`` unchanged if no grid
    marker is found (the zero-items ``.empty`` state -- nothing to prefix
    ahead of; callers never have a non-empty ``prefix_html`` in that case
    anyway, since AC9(b)/AC2 both require >=1 item)."""
    marker = "<div class='grid'>"
    idx = html_text.find(marker)
    if idx == -1:
        return html_text
    return html_text[:idx] + prefix_html + html_text[idx:]


def render_control_plane(items, out, focus=None, repo_health_lookup=None,
                         current_head_lookup=None, recompute_artifact_hash=None):
    """Render the control-plane dashboard HTML from ``items`` (as
    ``discover_control_plane_items`` would return, or hand-built fixtures with
    the same keys), write it to ``out``, and return the HTML text.

    Per item it validates each RAW proof record, discards hard-invalid ones,
    derives the item's evidence_label over the survivors, cross-checks the
    authored ``wip_column`` against that derived label (``wip_mismatch``), and
    emits the AC-RENDER bars plus the two base display elements. It does NOT
    route through the legacy ``_render_commit``/``_render_evidence`` path
    (AC10.2) and MUST NOT import/call ``evidence_ledger.build_ledger`` (AC1).

    ``repo_health_lookup``: optional ``product -> "CLEAR"/"FROZEN"`` callable;
    the live per-product AC9 source of truth. Default (None) does a real live
    lookup; every test injects a fake so the real ledger is never read.
    ``current_head_lookup`` / ``recompute_artifact_hash``: optional callables
    threaded into each record's ``validate_proof_record`` (the git-HEAD and
    artifact-hash freshness axes). When None (the pure-fixture default), those
    axes are SKIPPED per record.

    Page layout (AC2/AC3/AC9, this micro-step):
      * Every item's own per-card state is computed exactly once (via
        ``_cp_item_state``), in plain input-list order -- no sorting or
        grouping is EVER applied to ``items``, so non-focused items keep the
        exact emission order they always have (AC3's styling-only weight
        change never reorders anything).
      * AC2: items whose ``product == focus`` are RELOCATED (not
        duplicated) into one ``.cp-banner`` section rendered before the
        ordinary grid; when no focus is set or it matches no item, no
        banner renders at all (grid-only, unchanged from pre-redesign).
      * AC9(a): the pre-existing zero-items ``.empty`` state is untouched
        (``empty = len(items) == 0``).
      * AC9(b): when >=1 item renders, no focus is active/matched, and zero
        items anywhere carry ``.cp-mismatch``, a calm ``.cp-all-clear``
        summary renders at the very top of the page.
    """
    items = list(items or [])
    states = [
        _cp_item_state(item, focus, repo_health_lookup, current_head_lookup,
                       recompute_artifact_hash)
        for item in items
    ]

    focus_cards = [s["html"] for s in states if s["focused"]]
    grid_cards = [s["html"] for s in states if not s["focused"]]

    any_focus_active = any(s["focused"] for s in states)
    mismatch_count = sum(1 for s in states if s["mismatch"])
    verified_count = sum(1 for s in states if s["verified"])

    prefix_sections = []
    # AC9(b): calm affirmative summary -- >=1 item, no ACTIVE (matching)
    # focus, and zero items anywhere carry .cp-mismatch.
    if states and not any_focus_active and mismatch_count == 0:
        prefix_sections.append(_render_cp_all_clear(verified_count, mismatch_count))
    # AC2: focused items relocate into ONE banner section before the grid --
    # a relocation of the existing per-item .cp-focus marking, never a
    # duplication (each focused item's own card HTML is UNCHANGED; only
    # WHERE it lives on the page moves).
    if focus_cards:
        prefix_sections.append(_render_cp_focus_banner("".join(focus_cards)))

    empty = len(items) == 0
    html_text = render_html("".join(grid_cards), empty=empty,
                            refresh_seconds=CP_REFRESH_SECONDS)
    if prefix_sections:
        html_text = _insert_before_grid(html_text, "".join(prefix_sections))

    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html_text)
    return html_text


def discover_control_plane_items(root, status_paths=None, globs=None):
    """AC8 real-mode discovery: return the flat list of control-plane item
    dicts to render.

    Default (no ``status_paths``/``globs``): recursively find every
    ``<root>/runs/**/status.json`` (via ``glob.glob(..., recursive=True)`` --
    NOT a shallow one-level glob), EXCLUDING any path containing ``/demo/``.
    Override: when ``status_paths`` or ``globs`` is non-empty, it supplies the
    file set directly (via the pre-existing ``discover_paths``) and BYPASSES
    both the recursive default AND the ``/demo/`` exclusion (AC5/test 27 -- the
    only way a ``/demo/`` item is rendered in control-plane mode).

    Each status.json is parsed; for each of its ``items`` an item dict is
    emitted carrying the top-level ``product`` (AC6.4/AC9 <repo-id>), the
    item's own fields (``claim``/``wip_column``/``requires_cleanup`` for a
    new-shaped item, or the legacy ``title``/``status``/``verified``/``phase``/
    ``evidence`` fields for a legacy-shaped one), ``source_path`` (the
    status.json path, used for per-item ``/demo/`` marking), and
    ``proof_records`` = the RAW dicts from that item's on-disk ``proofs`` array
    (not yet validated). A malformed/unreadable status.json is skipped.

    This path deliberately does NOT import or call
    ``evidence_ledger.build_ledger`` (AC1's reuse boundary -- proof snapshots
    are resolved by direct path, not via the ledger; test 25 asserts zero
    calls)."""
    if status_paths or globs:
        paths = discover_paths(status_paths, globs)
    else:
        pattern = os.path.join(root, "runs", "**", "status.json")
        paths = []
        seen = set()
        for hit in sorted(_glob.glob(pattern, recursive=True)):
            if "/demo/" in hit:
                continue
            ap = os.path.abspath(hit)
            if ap in seen or not os.path.isfile(ap):
                continue
            seen.add(ap)
            paths.append(ap)

    items = []
    for path in paths:
        text = _read(path)
        if text is None:
            continue
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        product = data.get("product")
        raw_items = data.get("items")
        if not isinstance(raw_items, list):
            continue
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            item["product"] = product
            item["source_path"] = path
            proofs = raw.get("proofs")
            item["proof_records"] = proofs if isinstance(proofs, list) else []
            items.append(item)
    return items


def _cli_repo_health_lookup():
    """Build the real, live per-product repo-health lookup for the CLI path
    (AC9): a single fresh ``repo_health_gate`` verdict per product, computed
    ONCE and cached so every item of the same product shares one authoritative
    verdict. A product with no ledger entries is genuinely CLEAR."""
    cache = {}

    def lookup(product):
        if product not in cache:
            cache[product] = _default_repo_health_lookup(product)
        return cache[product]

    return lookup


def _cli_current_head_lookup(record):
    """Real git-HEAD freshness source (AC8): ``git -C <record['cwd']> rev-parse
    HEAD`` (stripped), or None on any failure (no repo / git error / no cwd)."""
    cwd = record.get("cwd") if isinstance(record, dict) else None
    if not cwd:
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "HEAD"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    head = proc.stdout.decode("utf-8", "replace").strip()
    return head or None


def _cli_recompute_artifact_hash(path):
    """Real artifact-hash freshness source (AC8): the sha256 hex of the file at
    ``path`` as it exists on disk right now, or None if it is missing/
    unreadable (which ``validate_proof_record`` treats as stale)."""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError:
        return None
    return hashlib.sha256(data).hexdigest()


def _run_control_plane(args):
    """AC5 control-plane CLI mode: discover items under ``--root`` (or the
    ``--status``/``--glob`` override), render them with the three REAL live
    callables wired, and print a one-line summary."""
    root = os.path.abspath(os.path.expanduser(args.root))

    # --focus atomically records the focus pointer next to the root; when the
    # flag is absent we READ BACK <root>/.control-plane-focus so a prior focus
    # keeps highlighting (AC7 "read from that pointer if --focus is not passed").
    pointer = os.path.join(root, ".control-plane-focus")
    focus = args.focus
    if focus is not None:
        tmp = pointer + ".tmp"
        try:
            os.makedirs(root, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(focus)
            os.replace(tmp, pointer)
        except OSError:
            pass
    else:
        # No --focus: degrade to no-focus on any read failure, empty/whitespace
        # pointer, or absent file. A pointer naming an absent product is passed
        # through unchanged -- render_control_plane emits no .cp-focus when the
        # name matches no present item, so zero-focus stays valid (AC7).
        try:
            with open(pointer, "r", encoding="utf-8") as fh:
                stored = fh.read().strip()
            if stored:
                focus = stored
        except OSError:
            pass

    items = discover_control_plane_items(root, status_paths=args.status,
                                         globs=args.globs)
    render_control_plane(
        items, args.out, focus=focus,
        repo_health_lookup=_cli_repo_health_lookup(),
        current_head_lookup=_cli_current_head_lookup,
        recompute_artifact_hash=_cli_recompute_artifact_hash,
    )
    print("Wrote {} ({} control-plane item(s)).".format(args.out, len(items)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render the per-product status dashboard.")
    ap.add_argument("--status", action="append", dest="status", default=[],
                    help="explicit status.json path (repeatable)")
    ap.add_argument("--glob", action="append", dest="globs", default=[],
                    help="glob pattern to discover status.json files (repeatable)")
    ap.add_argument("--out", default="product_dashboard.html", help="output HTML path")
    ap.add_argument("--serve", nargs="?", const="8000", default=None,
                    help="(nice-to-have; not implemented)")
    ap.add_argument("--control-plane", action="store_true", dest="control_plane",
                    help="render the real-evidence control-plane dashboard (AC5)")
    ap.add_argument("--root", dest="root", default=None,
                    help="control-plane discovery root; also holds .control-plane-focus "
                         "(REQUIRED with --control-plane or --focus)")
    ap.add_argument("--focus", dest="focus", default=None,
                    help="highlight one product and write <root>/.control-plane-focus")
    args = ap.parse_args(argv)

    # AC5 (round-8 gap): --root is REQUIRED whenever --control-plane or --focus
    # is used; either without --root is a usage error -> exit code 2 with a
    # stderr message containing "required" (ap.error), and NO output file is
    # written (this check precedes any render/build).
    if (args.control_plane or args.focus is not None) and not args.root:
        ap.error("--root is required when --control-plane or --focus is used")

    if args.serve is not None:
        print("--serve is not implemented; generating the static HTML instead.")

    if args.control_plane or args.focus is not None:
        return _run_control_plane(args)

    out, rollups = build(status_paths=args.status, globs=args.globs, out=args.out)
    print("Wrote {} ({} product(s)).".format(out, len(rollups)))
    for name, summary in rollups:
        print("  - {}: {}".format(name, summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
