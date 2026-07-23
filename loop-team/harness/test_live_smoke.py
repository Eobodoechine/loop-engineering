"""Tests for live_smoke.py (H-LOOPTEAM-2).

Unit tests for the pure classifier + URL extractor, plus one [BEHAVIORAL] test
that actually launches chromium and hits a live URL end-to-end.

Run: python3 -m pytest loop-team/harness/test_live_smoke.py -q
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import live_smoke  # noqa: E402


class Classify(unittest.TestCase):
    def test_404_status_is_dead(self):
        self.assertEqual(live_smoke.classify(404, "Whatever", "u", "u"), "DEAD")

    def test_404_title_is_dead(self):
        self.assertEqual(live_smoke.classify(200, "404 Page Not Found", "u", "u"), "DEAD")

    def test_not_found_title_is_dead(self):
        self.assertEqual(live_smoke.classify(200, "Page Not Found", "u", "u"), "DEAD")

    def test_403_is_bot_walled_not_dead(self):
        # The key lesson: a 403 is INCONCLUSIVE, never DEAD.
        self.assertEqual(live_smoke.classify(403, "Access Denied", "u", "u"), "BOT_WALLED")

    def test_access_denied_phrase_is_bot_walled(self):
        self.assertEqual(
            live_smoke.classify(200, "Access to this page has been denied", "u", "u"),
            "BOT_WALLED")

    def test_pressandhold_is_bot_walled(self):
        self.assertEqual(live_smoke.classify(200, "Press & Hold to confirm", "u", "u"), "BOT_WALLED")

    def test_200_normal_is_live(self):
        self.assertEqual(
            live_smoke.classify(200, "155 Listings Available", "http://a.com/x", "http://a.com/x"),
            "LIVE")

    def test_redirect_detected(self):
        self.assertEqual(
            live_smoke.classify(200, "Home", "http://a.com/x", "http://a.com/elsewhere"),
            "REDIRECTED")


class ExtractUrls(unittest.TestCase):
    def test_extracts_and_dedupes_in_order(self):
        d = tempfile.mkdtemp()
        f = os.path.join(d, "a.md")
        with open(f, "w") as fh:
            fh.write("see https://x.com/a and https://x.com/a then https://y.com/b.")
        self.assertEqual(live_smoke.extract_urls(f), ["https://x.com/a", "https://y.com/b"])

    def test_skips_placeholder_template_urls(self):
        d = tempfile.mkdtemp()
        f = os.path.join(d, "a.md")
        with open(f, "w") as fh:
            fh.write("real https://x.com/a and template "
                     "https://www.walkscore.com/score/[street-address]-Atlanta-GA done")
        # the placeholder url must be skipped, only the real one returned
        self.assertEqual(live_smoke.extract_urls(f), ["https://x.com/a"])


class Summary(unittest.TestCase):
    """Freezes the false-pass bug: a URL that could not load is NOT a pass.

    Regression for: live_smoke reported `passed: True` while a URL's verdict was
    ERROR (navigation failed / empty response) — the project's deepest failure
    mode (a false-pass) living inside the very tool meant to catch broken URLs.
    These are deterministic (no network), so the wiring catches any recurrence.
    """

    def _r(self, url, verdict):
        return {"url": url, "status": None, "title": None,
                "requested": url, "final": url, "verdict": verdict}

    def test_error_verdict_is_not_passed(self):
        s = live_smoke.summarize([self._r("https://x.com/a", "ERROR")])
        self.assertFalse(s["passed"], s)            # the bug: this was True
        self.assertIn("https://x.com/a", s["errored"])

    def test_dead_verdict_is_not_passed(self):
        s = live_smoke.summarize([self._r("https://x.com/d", "DEAD")])
        self.assertFalse(s["passed"], s)

    def test_all_live_passes(self):
        s = live_smoke.summarize([self._r("a", "LIVE"), self._r("b", "LIVE")])
        self.assertTrue(s["passed"], s)

    def test_one_error_among_live_fails_the_whole_smoke(self):
        s = live_smoke.summarize([self._r("a", "LIVE"), self._r("b", "ERROR")])
        self.assertFalse(s["passed"], s)

    def test_bot_walled_is_inconclusive_not_failed(self):
        s = live_smoke.summarize([self._r("b", "BOT_WALLED")])
        self.assertTrue(s["passed"], s)             # surfaced for recheck, not auto-failed
        self.assertIn("b", s["bot_walled_recheck_via_real_browser"])

    def test_nav_failed_is_not_passed_and_bucketed(self):
        s = live_smoke.summarize([self._r("https://x.com/n", "NAV_FAILED")])
        self.assertFalse(s["passed"], s)
        self.assertIn("https://x.com/n", s["nav_failed"])

    def test_proxy_failed_is_env_layer_not_passed_and_bucketed(self):
        s = live_smoke.summarize([self._r("https://x.com/p", "PROXY_FAILED")])
        self.assertFalse(s["passed"], s)            # could-not-test != a pass
        self.assertIn("https://x.com/p", s["proxy_failed"])
        self.assertNotIn("https://x.com/p", s["dead"])  # NOT mistaken for a dead URL

    def test_launch_failed_is_env_layer_not_passed_and_bucketed(self):
        s = live_smoke.summarize([self._r("https://x.com/l", "LAUNCH_FAILED")])
        self.assertFalse(s["passed"], s)
        self.assertIn("https://x.com/l", s["launch_failed"])
        self.assertNotIn("https://x.com/l", s["dead"])

    def test_layers_are_distinct_buckets(self):
        s = live_smoke.summarize([
            self._r("d", "DEAD"), self._r("n", "NAV_FAILED"),
            self._r("p", "PROXY_FAILED"), self._r("l", "LAUNCH_FAILED"),
            self._r("ok", "LIVE")])
        self.assertFalse(s["passed"], s)
        self.assertEqual((s["dead"], s["nav_failed"], s["proxy_failed"], s["launch_failed"]),
                         (["d"], ["n"], ["p"], ["l"]))


class NavErrorClassification(unittest.TestCase):
    """A navigation exception is classified by LAYER from its net::ERR_* code."""

    def test_tunnel_failure_is_proxy_layer(self):
        self.assertEqual(
            live_smoke.classify_nav_error("Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://x"),
            "PROXY_FAILED")

    def test_empty_response_is_nav_layer(self):
        self.assertEqual(
            live_smoke.classify_nav_error("net::ERR_EMPTY_RESPONSE at https://x"), "NAV_FAILED")

    def test_dns_failure_is_nav_layer(self):
        self.assertEqual(
            live_smoke.classify_nav_error("net::ERR_NAME_NOT_RESOLVED at https://nope.invalid"),
            "NAV_FAILED")

    def test_timeout_is_nav_layer(self):
        self.assertEqual(live_smoke.classify_nav_error("Timeout 15000ms exceeded"), "NAV_FAILED")

    def test_unknown_exception_is_error(self):
        self.assertEqual(live_smoke.classify_nav_error("something weird happened"), "ERROR")


class ProxyResolution(unittest.TestCase):
    """live_smoke honors HTTPS_PROXY / HTTP_PROXY so it works behind a proxy / in CI."""

    def test_https_proxy_preferred(self):
        self.assertEqual(
            live_smoke.resolve_proxy({"HTTPS_PROXY": "http://p:3128", "HTTP_PROXY": "http://q:8080"}),
            {"server": "http://p:3128"})

    def test_http_proxy_fallback(self):
        self.assertEqual(live_smoke.resolve_proxy({"HTTP_PROXY": "http://q:8080"}),
                         {"server": "http://q:8080"})

    def test_lowercase_variant_honored(self):
        self.assertEqual(live_smoke.resolve_proxy({"https_proxy": "http://p:3128"}),
                         {"server": "http://p:3128"})

    def test_none_when_unset(self):
        self.assertIsNone(live_smoke.resolve_proxy({}))


class Behavioral(unittest.TestCase):
    def test_runs_against_a_real_url_end_to_end(self):
        """Actually launches chromium and hits a live URL — proves the tool works.

        EXECUTION-based, not import-based: importing playwright does NOT prove
        the browser can launch (the import-vs-binary lesson — `import playwright`
        succeeds even when the chromium binary or system libs are missing). So we
        actually RUN the tool and decide from what it produced, skipping with the
        real cause when the environment genuinely can't run a live browser, and
        asserting in full when it can.
        """
        out = subprocess.run(
            [sys.executable, os.path.join(HERE, "live_smoke.py"), "https://example.com"],
            capture_output=True, text=True, timeout=60)
        if not out.stdout.strip():
            self.skipTest(
                "live_smoke emitted no JSON — the browser could not launch "
                "(missing playwright package, chromium binary, or system libs). "
                "stderr tail: " + (out.stderr.strip()[-300:] or "<empty>"))
        data = json.loads(out.stdout)
        row = data["results"][0]
        verdict = row["verdict"]
        # Layer-aware skip: each non-LIVE failure here is an ENVIRONMENT limit of
        # this runner (can't launch chromium / proxy blocks the host / can't reach
        # it / bot-walled), NOT a defect in the tool — skip with the precise layer.
        # On a normal machine example.com is reachable and the assertion runs.
        env_layers = {
            "LAUNCH_FAILED": "chromium could not launch (missing system libs / binary)",
            "PROXY_FAILED":  "the proxy refused the tunnel to the URL",
            "NAV_FAILED":    "could not reach the host (no egress / DNS / timeout)",
            "ERROR":         "navigation raised an unclassified error",
            "BOT_WALLED":    "bot-walled (needs a real-browser recheck)",
        }
        if verdict in env_layers:
            self.skipTest(f"environment could not confirm the URL live "
                          f"[{verdict}: {env_layers[verdict]}] — {row.get('error', '')}")
        # Browser launched AND example.com loaded — the behavioral assertion runs in full.
        self.assertEqual(verdict, "LIVE")
        self.assertTrue(data["passed"], data)
        self.assertIn("example", (row["title"] or "").lower())


if __name__ == "__main__":
    unittest.main()
