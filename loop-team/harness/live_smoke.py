#!/usr/bin/env python3
"""Loop Team — live-smoke verifier (H-LOOPTEAM-2).

Exercises an external-touching artifact's URLs against the real web, so a build
can't be declared done while a documented URL silently 404s. Extracts http(s)
URLs from a file (or takes them on argv), navigates each headlessly, and gives
each a verdict grouped by the LAYER that produced it — so a failure is actionable
(a dead URL, a proxy block, and a launch crash need different fixes):

  HTTP-response layer (the browser got a response):
    LIVE        2xx/3xx and not a 404/not-found page
    DEAD        404 or a "not found" page                  -> REAL failure
    BOT_WALLED  401/403 / captcha / press&hold -> INCONCLUSIVE: a naive headless
                probe gets bot-detected (false 403s that load fine in a real
                browser). Recheck via the production browser before judging.
    REDIRECTED  final URL differs materially from the requested one

  Transport layer (no usable response — the URL was NOT confirmed live):
    NAV_FAILED  could not reach/load the host (DNS, connection refused/reset,
                empty response, timeout)                    -> REAL failure
    ERROR       any other navigation exception              -> REAL failure

  Environment / tooling layer (could NOT test — NOT a verdict on the URL):
    PROXY_FAILED  the proxy refused the tunnel (env proxy config, not the URL)
    LAUNCH_FAILED chromium could not launch (missing system libs / binary)

`passed` is True only when EVERY url is confirmed reachable; any failure verdict
(response, transport, OR environment) blocks the pass, but each is surfaced in
its own bucket so the consumer knows whether to fix the URL, the proxy, or the
host. This headless sweep is the FAST FIRST PASS, authoritative for DEAD but NOT
for BOT_WALLED (see roles/live_smoke.md).

Exit: 0 only if passed (every url reachable); 1 otherwise; 2 on usage error.
Prints a JSON summary to STDOUT (its machine-readable contract — always pure,
json.loads-able JSON, even when the browser can't launch). Honors HTTPS_PROXY /
HTTP_PROXY when launching chromium, so it works in proxied / CI environments.
Requires the `playwright` package + chromium browser.

Structured logs (stderr, and a per-run <run-dir>/log.jsonl when --run-dir /
--log-dir or LOOP_LOG_DIR is given) are emitted alongside the stdout JSON: one
line per URL verdict (LIVE -> INFO; any failure -> WARNING/ERROR) plus a run
summary line. Logging NEVER touches stdout, so the JSON contract is preserved.

Usage:
    python3 live_smoke.py --file path/to/SKILL.md
    python3 live_smoke.py https://a.com https://b.com
    python3 live_smoke.py --run-dir runs/smoke https://a.com
"""
import json
import os
import re
import sys

# Make `from harness.log import ...` resolvable whether run from loop-team/ or
# directly as a script from harness/ (mirror how test_live_smoke.py shims HERE).
_HERE = os.path.dirname(os.path.abspath(__file__))           # .../loop-team/harness
_LOOPTEAM_DIR = os.path.dirname(_HERE)                        # .../loop-team
for _p in (_LOOPTEAM_DIR, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from harness.log import get_logger
except Exception:  # pragma: no cover - extremely defensive; logging is best-effort
    get_logger = None

URL_RE = re.compile(r'https?://[^\s"\'`)>\]]+')

# Verdicts that are not a clean confirmed-live URL: logged at WARNING/ERROR with
# the url + its verdict. Only LIVE is logged at INFO. (Per the spec, the
# inconclusive/redirected verdicts are surfaced at WARNING too so the operator
# sees them in the log even though summarize() does not treat them as blocking.)
_FAILURE_VERDICTS = {
    "LAUNCH_FAILED", "PROXY_FAILED", "NAV_FAILED", "ERROR", "DEAD",
    "BOT_WALLED", "REDIRECTED",
}


def resolve_proxy(env=None):
    """Return a Playwright proxy dict from standard proxy env vars, or None.

    Honors HTTPS_PROXY / HTTP_PROXY (and lowercase variants), HTTPS preferred,
    so live_smoke works in proxied / CI environments where chromium has no
    direct egress. Pure + unit-tested; no network. (NO_PROXY is intentionally
    not parsed — the sweep targets a few explicit URLs, not arbitrary hosts.)
    """
    env = os.environ if env is None else env
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        val = env.get(key)
        if val:
            return {"server": val}
    return None


def classify(status, title, requested, final):
    """Map a navigation result to a verdict. Pure; unit-tested."""
    low = (title or "").lower()
    if status == 404 or "404" in (title or "") or "not found" in low:
        return "DEAD"
    if status in (401, 403) or "access denied" in low or "press & hold" in low \
            or "captcha" in low or "are you a robot" in low or "access to this page has been denied" in low:
        return "BOT_WALLED"

    def norm(u):
        return (u or "").split("?")[0].rstrip("/").lower()

    if final and norm(final) != norm(requested):
        return "REDIRECTED"
    if status and 200 <= status < 400:
        return "LIVE"
    return "ERROR"


def classify_nav_error(message):
    """Classify a navigation EXCEPTION by layer. Pure; unit-tested.

    Chromium surfaces net::ERR_* codes in the exception text. We separate the
    ENVIRONMENT/proxy layer from the TRANSPORT layer so a failure is actionable:

      PROXY_FAILED  the proxy refused/failed the tunnel (fix the proxy/env, the
                    URL itself is not implicated)
      NAV_FAILED    transport could not reach/load the host — DNS, connection
                    refused/reset/timed-out, empty response (the URL was not
                    confirmed live)
      ERROR         any other navigation exception (catch-all)
    """
    m = (message or "").upper()
    if any(s in m for s in (
            "ERR_TUNNEL_CONNECTION_FAILED", "ERR_PROXY_CONNECTION_FAILED",
            "ERR_NO_SUPPORTED_PROXIES", "ERR_PROXY_AUTH_REQUESTED")):
        return "PROXY_FAILED"
    if any(s in m for s in (
            "ERR_EMPTY_RESPONSE", "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_RESET",
            "ERR_CONNECTION_TIMED_OUT", "ERR_CONNECTION_CLOSED", "ERR_NAME_NOT_RESOLVED",
            "ERR_ADDRESS_UNREACHABLE", "ERR_NETWORK_CHANGED", "ERR_SOCKET_NOT_CONNECTED",
            "ERR_ABORTED", "ERR_TIMED_OUT", "TIMEOUT")):
        return "NAV_FAILED"
    return "ERROR"


def extract_urls(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    seen, out = set(), []
    for m in URL_RE.findall(txt):
        u = m.rstrip(".,);")
        # Skip documented TEMPLATE urls with placeholders (e.g. walkscore
        # /score/[street-address-with-hyphens]) — they aren't real links and
        # would be false DEADs. Markers: [ ] { } < >.
        if any(ch in u for ch in "[]{}<>"):
            continue
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def sweep(urls):
    from playwright.sync_api import sync_playwright
    ua = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120 Safari/537.36")
    results = []
    with sync_playwright() as p:
        # LAUNCH layer: if chromium can't start (missing system libs / binary),
        # NO url can be tested. Report LAUNCH_FAILED per url — a tool/env problem,
        # explicitly NOT a verdict on the URL — so the consumer fixes the host,
        # not the link. (This is the failure that the bare ERROR bucket used to
        # silently swallow and mis-attribute to the URL.)
        try:
            b = p.chromium.launch(headless=True, proxy=resolve_proxy())
        except Exception as e:
            msg = str(e).splitlines()[0][:200]
            return [{"url": u, "status": None, "title": None, "final": None,
                     "verdict": "LAUNCH_FAILED", "error": msg} for u in urls]
        ctx = b.new_context(user_agent=ua)
        for u in urls:
            page = ctx.new_page()
            error = None
            try:
                r = page.goto(u, timeout=15000, wait_until="domcontentloaded")
                status = r.status if r else None
                title = (page.title() or "")[:80]
                final = page.url
                verdict = classify(status, title, u, final)          # HTTP-response layer
            except Exception as e:
                error = str(e).splitlines()[0][:120]
                status, title, final = None, None, None
                verdict = classify_nav_error(error)                  # proxy / transport layer
            finally:
                page.close()
            row = {"url": u, "status": status, "title": title,
                   "final": final, "verdict": verdict}
            if error:
                row["error"] = error
            results.append(row)
        b.close()
    return results


def summarize(results):
    """Build the smoke summary from per-URL results. Pure + unit-tested.

    `passed` is True only when EVERY url is confirmed reachable. Any failure —
    a dead URL, a transport failure, OR an environment failure (proxy/launch) —
    blocks the pass: reporting `passed: True` when a URL could not be confirmed
    live is the false-pass class this tool exists to prevent. (The original bug
    keyed `passed` on DEAD only, so an errored url reported True.)

    Each failure is surfaced in its OWN bucket, by layer, so the verdict is
    actionable — fix the URL (dead), the host/transport (nav_failed/errored), or
    the environment (proxy_failed/launch_failed). BOT_WALLED is inconclusive
    (recheck in a real browser), not auto-failed. REDIRECTED counts as reachable.
    """
    counts = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

    def urls_with(verdict):
        return [r["url"] for r in results if r["verdict"] == verdict]

    dead = urls_with("DEAD")                  # response layer: URL is 404/gone
    nav_failed = urls_with("NAV_FAILED")      # transport layer: couldn't reach host
    errored = urls_with("ERROR")              # transport layer: other nav exception
    proxy_failed = urls_with("PROXY_FAILED")  # env layer: proxy refused the tunnel
    launch_failed = urls_with("LAUNCH_FAILED")  # env layer: chromium couldn't start
    bot_walled = urls_with("BOT_WALLED")      # inconclusive: recheck in real browser

    blocking = dead + nav_failed + errored + proxy_failed + launch_failed
    return {
        "passed": len(blocking) == 0,
        "counts": counts,
        # response layer (the URL itself is broken):
        "dead": dead,
        # transport layer (could not reach/load the host):
        "nav_failed": nav_failed,
        "errored": errored,
        # environment / tooling layer (could NOT test — not a verdict on the URL):
        "proxy_failed": proxy_failed,
        "launch_failed": launch_failed,
        # inconclusive (recheck via the production browser):
        "bot_walled_recheck_via_real_browser": bot_walled,
        "results": results,
    }


def _safe_sweep(urls):
    """Run sweep(urls), turning a launch-layer failure into LAUNCH_FAILED rows.

    sweep() launches chromium via playwright. When the `playwright` package is
    absent its import raises ModuleNotFoundError; when the chromium binary/libs
    are missing the launch raises (already handled inside sweep, which returns
    LAUNCH_FAILED rows). We catch the import-time failure HERE so main() always
    has rows to summarize and can still print parseable JSON to stdout — a
    tooling/environment problem must NOT be a crash or a verdict on the URL.
    """
    try:
        return sweep(urls)
    except Exception as e:  # ModuleNotFoundError (no playwright) and any launch crash
        msg = (str(e).splitlines() or [""])[0][:200]
        return [{"url": u, "status": None, "title": None, "final": None,
                 "verdict": "LAUNCH_FAILED", "error": msg} for u in urls]


def _resolve_log_dir(args, env=None):
    """Pick the persist dir for structured logs: --run-dir/--log-dir flag wins,
    else LOOP_LOG_DIR env, else None (stderr-only). Returns (log_dir, remaining_args)."""
    env = os.environ if env is None else env
    log_dir = None
    rest = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--run-dir", "--log-dir"):
            if i + 1 < len(args):
                log_dir = args[i + 1]
                i += 2
                continue
            i += 1
            continue
        if a.startswith("--run-dir=") or a.startswith("--log-dir="):
            log_dir = a.split("=", 1)[1]
            i += 1
            continue
        rest.append(a)
        i += 1
    if log_dir is None:
        log_dir = env.get("LOOP_LOG_DIR") or None
    return log_dir, rest


def main(argv):
    args = argv[1:]
    log_dir, args = _resolve_log_dir(args)
    lg = get_logger("live_smoke", run_dir=log_dir) if get_logger else None

    if not args:
        print(json.dumps({"error": "usage: live_smoke.py [--run-dir DIR] --file <path> | <url> [url...]"}))
        return 2
    if args[0] == "--file":
        if len(args) < 2:
            print(json.dumps({"error": "missing file path after --file"}))
            return 2
        urls = extract_urls(args[1])
    else:
        urls = args
    if not urls:
        print(json.dumps({"error": "no urls found", "results": []}))
        return 2

    results = _safe_sweep(urls)
    summary = summarize(results)

    # One structured line per URL verdict; failures at WARNING, LIVE at INFO.
    if lg is not None:
        for r in results:
            verdict = r.get("verdict")
            fields = {"url": r.get("url"), "verdict": verdict}
            if r.get("error"):
                fields["error"] = r["error"]
            if verdict in _FAILURE_VERDICTS:
                lg.warning("url verdict", **fields)
            else:
                lg.info("url verdict", **fields)
        # Run-level summary line: WARNING when the smoke did not pass, else INFO.
        run_fields = {"passed": summary["passed"], "counts": summary.get("counts", {})}
        if summary["passed"]:
            lg.info("live_smoke run", **run_fields)
        else:
            lg.warning("live_smoke run", **run_fields)

    print(json.dumps(summary, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
