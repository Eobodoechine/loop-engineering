#!/usr/bin/env python3
"""Executable acceptance suite for product_dashboard.py (Tier-1, spec-only).

Written BEFORE the implementation exists; every test is expected to FAIL until
the Coder delivers loop-team/harness/product_dashboard.py. Do NOT put any
implementation here.

Each test builds status.json fixtures in ``tmp_path``, invokes the tool as a
subprocess (``python3 product_dashboard.py --status ... --out ...``), reads the
rendered ``--out`` HTML, and asserts on the HTML string. Each test is mapped to
its acceptance criterion in a comment and tagged [DOC]/[BEHAVIORAL].

---------------------------------------------------------------------------
Rendering contract (test-defined; the Coder implements to satisfy it).
The spec fixes the *semantics* (badge meanings, colors, partition) but leaves
exact markup open, so this suite pins a minimal, natural contract the renderer
must honor. These are the load-bearing hooks the assertions key on:

  * Product card ..... an element whose class attribute contains token
                       ``product-card`` (one per rendered product).
  * Error card ....... an element whose class attribute contains token
                       ``error-card`` (invalid-JSON file only, per AC6).
  * Empty state ...... an element with class token ``empty`` (matches
                       dashboard.py's convention) when there are no products.
  * Status badges .... render the LITERAL uppercase text ``VERIFIED`` /
                       ``CLAIMED``; phase badges render the phase word
                       (must/doing/built/broken) or the literal unknown phase.
                       Color semantics carried via class tokens: a VERIFIED
                       badge's class contains ``verified``; a CLAIMED badge's
                       class contains ``claimed``; a broken phase badge's class
                       contains ``broken``.
  * Rollup chips ..... each non-zero bucket renders as lowercase text of the
                       form ``<bucket>: <count>`` (e.g. ``verified: 2``), where
                       <bucket> is one of verified/claimed/broken/doing/must/
                       built/other. (Lowercase-with-colon is what distinguishes
                       a chip from an uppercase badge or a plain phase word.)
  * Evidence ......... shown inside a ``<details>`` element; a GitHub-resolvable
                       commit renders as ``<a href="https://github.com/O/R/commit/<sha>">``.
---------------------------------------------------------------------------
"""
import json
import os
import re
import subprocess
import sys

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL = os.path.join(HARNESS_DIR, "product_dashboard.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_status(dirpath, data, name="status.json"):
    """Write a JSON status file, return its absolute path."""
    os.makedirs(dirpath, exist_ok=True)
    p = os.path.join(str(dirpath), name)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return p


def _write_raw(dirpath, text, name="status.json"):
    """Write raw bytes/text (e.g. corrupt JSON), return its absolute path."""
    os.makedirs(dirpath, exist_ok=True)
    p = os.path.join(str(dirpath), name)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)
    return p


def _make_repo(base, name, origin_url):
    """Create a fake repo dir <base>/<name> with a .git/config carrying an
    origin remote. Returns the repo dir path (where status.json should live so
    that dir == the containing repo root)."""
    repo = os.path.join(str(base), name)
    gitdir = os.path.join(repo, ".git")
    os.makedirs(gitdir, exist_ok=True)
    cfg = (
        "[core]\n"
        "\trepositoryformatversion = 0\n"
        '[remote "origin"]\n'
        "\turl = %s\n"
        "\tfetch = +refs/heads/*:refs/remotes/origin/*\n" % origin_url
    )
    with open(os.path.join(gitdir, "config"), "w", encoding="utf-8") as fh:
        fh.write(cfg)
    return repo


def _run(tmp_path, status_paths=(), globs=(), out_name="product_dashboard.html", extra=()):
    """Invoke the tool as a subprocess. Return (proc, html_text)."""
    out = os.path.join(str(tmp_path), out_name)
    cmd = [sys.executable, TOOL]
    for s in status_paths:
        cmd += ["--status", str(s)]
    for g in globs:
        cmd += ["--glob", str(g)]
    cmd += ["--out", out]
    cmd += list(extra)
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc.stdout = proc.stdout.decode("utf-8", "replace")
    proc.stderr = proc.stderr.decode("utf-8", "replace")
    html = ""
    if os.path.exists(out):
        with open(out, "r", encoding="utf-8") as fh:
            html = fh.read()
    return proc, html


def _count_class(html, token):
    """Count elements whose class *attribute* contains the whole-word token.
    Keys on class="..."/class='...' so a CSS selector like `.product-card{` in
    the inlined <style> block is NOT miscounted."""
    return len(re.findall(r'class=["\'][^"\']*\b' + re.escape(token) + r'\b', html))


def _has_class(html, token):
    return _count_class(html, token) > 0


_CHIP_RE = re.compile(r"\b(verified|claimed|broken|doing|must|built|other)\s*:\s*(\d+)\b")


def _chip_counts(html):
    """Parse lowercase `bucket: N` rollup chips into {bucket: count}."""
    out = {}
    for m in _CHIP_RE.finditer(html):
        out[m.group(1)] = int(m.group(2))
    return out


def _no_crash(proc):
    assert proc.returncode == 0, "exit %s, stderr:\n%s" % (proc.returncode, proc.stderr)
    assert "Traceback" not in proc.stderr, "unexpected traceback:\n%s" % proc.stderr


# ---------------------------------------------------------------------------
# AC1 [BEHAVIORAL] Reads N, renders N.
# ---------------------------------------------------------------------------

def test_ac1_reads_two_renders_two_cards(tmp_path):
    s1 = _write_status(os.path.join(str(tmp_path), "p1"),
                       {"product": "Alpha Product", "done_sentence": "Alpha is shipped.",
                        "items": []})
    s2 = _write_status(os.path.join(str(tmp_path), "p2"),
                       {"product": "Beta Product", "done_sentence": "Beta is fully done.",
                        "items": []})
    proc, html = _run(tmp_path, status_paths=[s1, s2])
    _no_crash(proc)
    assert "Alpha Product" in html
    assert "Beta Product" in html
    assert "Alpha is shipped." in html
    assert "Beta is fully done." in html
    assert _count_class(html, "product-card") == 2, \
        "expected exactly 2 product cards, got %d" % _count_class(html, "product-card")


# ---------------------------------------------------------------------------
# AC2 [BEHAVIORAL] VERIFIED badge iff verified:true; same item flipped -> CLAIMED.
# ---------------------------------------------------------------------------

def test_ac2_verified_true_renders_green_verified_badge(tmp_path):
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "Prod", "done_sentence": "d", "items": [
                          {"id": "i1", "title": "The fix", "phase": "built",
                           "status": "fixed", "verified": True, "priority": 1}]})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    assert "VERIFIED" in html
    assert _has_class(html, "verified"), "VERIFIED badge must carry a `verified` class token"
    assert "CLAIMED" not in html


def test_ac2_same_item_verified_false_fixed_renders_amber_claimed(tmp_path):
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "Prod", "done_sentence": "d", "items": [
                          {"id": "i1", "title": "The fix", "phase": "built",
                           "status": "fixed", "verified": False, "priority": 1}]})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    assert "CLAIMED" in html
    assert _has_class(html, "claimed"), "CLAIMED badge must carry a `claimed` class token"
    assert "VERIFIED" not in html


# ---------------------------------------------------------------------------
# AC3 [BEHAVIORAL] CLAIMED vs phase badge.
# ---------------------------------------------------------------------------

def test_ac3_fixed_unverified_is_claimed(tmp_path):
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "Prod", "done_sentence": "d", "items": [
                          {"id": "i1", "title": "Fixed thing", "phase": "built",
                           "status": "fixed", "verified": False, "priority": 1}]})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    assert "CLAIMED" in html
    assert "VERIFIED" not in html


def test_ac3_claimed_status_doing_phase_is_phase_badge_not_claimed(tmp_path):
    # status=="claimed" is NOT status=="fixed", so no CLAIMED badge; phase wins.
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "Prod", "done_sentence": "d", "items": [
                          {"id": "i1", "title": "In progress", "phase": "doing",
                           "status": "claimed", "verified": False, "priority": 1}]})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    assert "doing" in html, "expected a 'doing' phase badge"
    assert "CLAIMED" not in html
    assert "VERIFIED" not in html


# ---------------------------------------------------------------------------
# AC4 [BEHAVIORAL] Rollup counts = full 7-bucket partition; chips SUM to item count.
# ---------------------------------------------------------------------------

def test_ac4_rollup_covers_all_seven_buckets_and_sums(tmp_path):
    items = [
        # -> verified bucket (verified wins over phase/status)
        {"id": "v", "title": "V item", "phase": "built", "status": "fixed",
         "verified": True, "priority": 1},
        # -> claimed bucket (fixed & !verified)
        {"id": "c", "title": "C item", "phase": "doing", "status": "fixed",
         "verified": False, "priority": 2},
        # -> broken bucket
        {"id": "b", "title": "B item", "phase": "broken", "status": "claimed",
         "verified": False, "priority": 3},
        # -> doing bucket
        {"id": "d", "title": "D item", "phase": "doing", "status": "claimed",
         "verified": False, "priority": 4},
        # -> must bucket
        {"id": "m", "title": "M item", "phase": "must", "status": "claimed",
         "verified": False, "priority": 5},
        # -> built bucket
        {"id": "bu", "title": "Bu item", "phase": "built", "status": "claimed",
         "verified": False, "priority": 6},
        # -> other bucket (unknown phase)
        {"id": "o", "title": "O item", "phase": "legacy", "status": "claimed",
         "verified": False, "priority": 7},
    ]
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "Prod", "done_sentence": "d", "items": items})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    chips = _chip_counts(html)
    for bucket in ("verified", "claimed", "broken", "doing", "must", "built", "other"):
        assert chips.get(bucket) == 1, \
            "bucket %r should show count 1, chips=%r" % (bucket, chips)
    assert sum(chips.values()) == len(items), \
        "partition invariant broken: chips sum %d != item count %d (chips=%r)" % (
            sum(chips.values()), len(items), chips)


# ---------------------------------------------------------------------------
# AC5 [BEHAVIORAL] Evidence rendered; GitHub origin -> commit link; test/log in details.
# ---------------------------------------------------------------------------

def test_ac5_evidence_commit_github_link_and_details(tmp_path):
    repo = _make_repo(tmp_path, "widget", "git@github.com:acme/widget.git")
    s = _write_status(repo,
                      {"product": "Widget", "done_sentence": "d", "items": [
                          {"id": "i1", "title": "Wired up", "phase": "built",
                           "status": "fixed", "verified": True, "priority": 1,
                           "evidence": {"commit": "abc1234",
                                        "test": "pytest -q tests/",
                                        "log": "/logs/widget_run.log"}}]})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    assert "abc1234" in html, "short sha must be shown"
    assert 'href="https://github.com/acme/widget/commit/abc1234"' in html, \
        "resolvable GitHub origin must render a commit <a href>"
    assert "<details" in html, "evidence must live in a collapsible <details>"
    assert "pytest -q tests/" in html, "evidence.test must be shown"
    assert "/logs/widget_run.log" in html, "evidence.log path must be shown"


# ---------------------------------------------------------------------------
# AC6 [BEHAVIORAL] Malformed file -> error card naming file; others render; exit 0.
# ---------------------------------------------------------------------------

def test_ac6_corrupt_json_yields_error_card_others_render_exit0(tmp_path):
    bad = _write_raw(os.path.join(str(tmp_path), "bad"),
                     "{ this is not valid json ,,,", name="corrupt_status.json")
    good = _write_status(os.path.join(str(tmp_path), "good"),
                         {"product": "Healthy Product", "done_sentence": "ok",
                          "items": []})
    proc, html = _run(tmp_path, status_paths=[bad, good])
    _no_crash(proc)  # exit code 0, no traceback
    assert _has_class(html, "error-card"), "malformed file must produce an error card"
    assert "corrupt_status.json" in html, "error card must name the offending file"
    assert "Healthy Product" in html, "valid product must still render alongside the error"


# ---------------------------------------------------------------------------
# AC7 [BEHAVIORAL] Empty / no files -> friendly empty state, no crash.
# ---------------------------------------------------------------------------

def test_ac7_no_files_friendly_empty_state(tmp_path):
    # A glob that matches nothing under the isolated tmp dir.
    empty_glob = os.path.join(str(tmp_path), "does_not_exist", "*.json")
    proc, html = _run(tmp_path, globs=[empty_glob])
    _no_crash(proc)
    assert _has_class(html, "empty"), "expected a friendly empty-state element"
    assert _count_class(html, "product-card") == 0, "no products should render"
    assert len(html) > 0, "must still write a valid HTML document"


# ---------------------------------------------------------------------------
# AC8 [BEHAVIORAL][SECURITY-ORACLE] Self-contained + HTML-escaped.
# (XSS-escaping guard -> flagged for Tier-2 mutation-oracle check.)
# ---------------------------------------------------------------------------

def test_ac8_script_escaped_and_no_external_resources(tmp_path):
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "<script>alert(1)</script>Evil",
                       "done_sentence": "<img src=x onerror=alert(2)>",
                       "items": [
                           {"id": "i1", "title": "<script>steal()</script>",
                            "phase": "doing", "status": "claimed",
                            "verified": False, "priority": 1}]})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    # Injected markup must be escaped, never emitted as live tags.
    assert "<script>alert(1)</script>" not in html
    assert "<script>steal()</script>" not in html
    assert "&lt;script&gt;" in html, "escaped form of the injected <script> must appear"
    # Self-contained: no external stylesheet/script/resource references.
    # This fixture has no GitHub evidence, so there must be NO external URLs.
    assert "http://" not in html and "https://" not in html, \
        "no external http(s) resource references expected in this fixture"
    assert re.search(r"<script[^>]*\ssrc=", html) is None, "no external <script src=>"
    assert re.search(r'<link[^>]*href=["\']https?:', html) is None, "no external stylesheet link"
    assert "@import" not in html, "no external @import"


# ---------------------------------------------------------------------------
# AC9 [DOC] Interface documented in the module docstring.
# ---------------------------------------------------------------------------

def test_ac9_module_docstring_documents_interface(tmp_path):
    with open(TOOL, "r", encoding="utf-8") as fh:
        src = fh.read()
    m = re.search(r'"""(.*?)"""', src, re.DOTALL)
    assert m, "product_dashboard.py must have a module docstring"
    doc = m.group(1)
    for flag in ("--status", "--glob", "--out"):
        assert flag in doc, "docstring must document the %s flag" % flag
    assert re.search(r"glob|discover", doc, re.IGNORECASE), \
        "docstring must describe status.json discovery"
    assert "VERIFIED" in doc and "CLAIMED" in doc, \
        "docstring must state the VERIFIED-vs-CLAIMED badge rule"


# ---------------------------------------------------------------------------
# AC10 [BEHAVIORAL] Sort order: broken > doing > must > built > other; ties by priority asc.
# ---------------------------------------------------------------------------

def test_ac10_sort_order_by_phase_then_priority(tmp_path):
    # All status="claimed", verified=false so the badge equals the phase and no
    # reclassification into verified/claimed occurs. Unique titles let us read
    # the rendered order by string position.
    items = [
        {"id": "1", "title": "BU1", "phase": "built", "status": "claimed",
         "verified": False, "priority": 1},
        {"id": "2", "title": "MU5", "phase": "must", "status": "claimed",
         "verified": False, "priority": 5},
        {"id": "3", "title": "DO3", "phase": "doing", "status": "claimed",
         "verified": False, "priority": 3},
        {"id": "4", "title": "BR9", "phase": "broken", "status": "claimed",
         "verified": False, "priority": 9},
        {"id": "5", "title": "BR2", "phase": "broken", "status": "claimed",
         "verified": False, "priority": 2},
        {"id": "6", "title": "OT7", "phase": "legacy", "status": "claimed",
         "verified": False, "priority": 7},
    ]
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "Prod", "done_sentence": "d", "items": items})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    order = ["BR2", "BR9", "DO3", "MU5", "BU1", "OT7"]
    positions = [html.index(t) for t in order]
    assert positions == sorted(positions), \
        "items out of order; expected %r, got index order %r" % (
            order, [t for _, t in sorted(zip(positions, order))])
    # broken phase badge carries the red `broken` class token.
    assert _has_class(html, "broken"), "broken items must carry a `broken` class token"


# ---------------------------------------------------------------------------
# AC11 [BEHAVIORAL] Missing structural keys render safely (defaults), not errors.
# ---------------------------------------------------------------------------

def test_ac11_missing_items_key_renders_empty_card_not_error(tmp_path):
    # Valid JSON, no `items` key -> empty card, NOT an error card.
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "No Items Product", "done_sentence": "d"})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    assert "No Items Product" in html
    assert _count_class(html, "error-card") == 0, "missing items must NOT be an error card"
    assert re.search(r"no items", html, re.IGNORECASE), "empty card should say 'no items'"


def test_ac11_item_missing_title_and_priority_uses_defaults_no_crash(tmp_path):
    # One item missing title+priority (defaults: '(untitled)', priority 9999),
    # plus a normal item so the comparator actually compares.
    items = [
        {"id": "x", "phase": "doing", "status": "claimed", "verified": False},  # no title/priority
        {"id": "y", "title": "Has Title", "phase": "must", "status": "claimed",
         "verified": False, "priority": 3},
    ]
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "Defaults Product", "done_sentence": "d", "items": items})
    # A valid sibling product must also still render, exit 0.
    s2 = _write_status(os.path.join(str(tmp_path), "prod2"),
                       {"product": "Sibling", "done_sentence": "d", "items": []})
    proc, html = _run(tmp_path, status_paths=[s, s2])
    _no_crash(proc)
    assert "(untitled)" in html, "missing title must default to (untitled)"
    assert "Has Title" in html
    assert "Sibling" in html, "other valid products must still render"


# ---------------------------------------------------------------------------
# AC12 [BEHAVIORAL] verified/phase overlap counts ONCE (in verified, not broken).
# ---------------------------------------------------------------------------

def test_ac12_verified_broken_overlap_counts_once_partition_holds(tmp_path):
    items = [
        # verified:true wins over phase:broken -> counts as verified only.
        {"id": "ov", "title": "Overlap item", "phase": "broken", "status": "fixed",
         "verified": True, "priority": 1},
        # plain built item -> counts in built.
        {"id": "b", "title": "Plain built", "phase": "built", "status": "claimed",
         "verified": False, "priority": 2},
    ]
    s = _write_status(os.path.join(str(tmp_path), "prod"),
                      {"product": "Prod", "done_sentence": "d", "items": items})
    proc, html = _run(tmp_path, status_paths=[s])
    _no_crash(proc)
    assert "VERIFIED" in html, "overlap item must show a VERIFIED badge"
    chips = _chip_counts(html)
    assert chips.get("verified") == 1, "overlap item must increment the verified chip once"
    assert "broken" not in chips, "overlap item must NOT count in the broken bucket"
    assert chips.get("built") == 1, "plain built item must show in the built chip"
    assert sum(chips.values()) == len(items), \
        "partition invariant broken: chips %r sum != %d" % (chips, len(items))


# ---------------------------------------------------------------------------
# AC13 [BEHAVIORAL][SECURITY-ORACLE] Non-GitHub origin -> plain-text sha, never a
# github href; missing .git/config never crashes. (Wrong-host-link guard ->
# flagged for Tier-2 mutation-oracle check.)
# ---------------------------------------------------------------------------

def _item_with_commit(sha):
    return {"id": "i1", "title": "Item", "phase": "built", "status": "fixed",
            "verified": True, "priority": 1,
            "evidence": {"commit": sha, "test": "pytest", "log": "/l.log"}}


def test_ac13_gitlab_origin_renders_plain_sha_no_github_link(tmp_path):
    repo = _make_repo(tmp_path, "glproj", "https://gitlab.com/acme/widget.git")
    s = _write_status(repo, {"product": "GL", "done_sentence": "d",
                             "items": [_item_with_commit("def5678")]})
    proc, html = _run(tmp_path, status_paths=[s], out_name="gl.html")
    _no_crash(proc)
    assert "def5678" in html, "sha must still render as plain text"
    assert "https://github.com" not in html, "must not fabricate a github.com link"
    assert "/commit/def5678\"" not in html.replace("gitlab.com", ""), \
        "gitlab origin must not produce a github commit href"


def test_ac13_self_hosted_origin_renders_plain_sha_no_github_link(tmp_path):
    repo = _make_repo(tmp_path, "shproj", "git@git.example.com:acme/widget.git")
    s = _write_status(repo, {"product": "SH", "done_sentence": "d",
                             "items": [_item_with_commit("aa11bb22")]})
    proc, html = _run(tmp_path, status_paths=[s], out_name="sh.html")
    _no_crash(proc)
    assert "aa11bb22" in html
    assert "https://github.com" not in html, "self-hosted origin must not link to github.com"


def test_ac13_missing_git_config_never_crashes(tmp_path):
    # Repo dir with NO .git/config at all.
    d = os.path.join(str(tmp_path), "nogit")
    s = _write_status(d, {"product": "NoGit", "done_sentence": "d",
                          "items": [_item_with_commit("cc33dd44")]})
    proc, html = _run(tmp_path, status_paths=[s], out_name="nogit.html")
    _no_crash(proc)
    assert "cc33dd44" in html, "sha must render as plain text even with no git config"
    assert "https://github.com" not in html
