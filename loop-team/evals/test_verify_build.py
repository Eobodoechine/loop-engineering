"""Tests for the deterministic Layer-1 meta-verifier (verify_build.py), no API.

IMPORTANT: these tests NEVER call verify_build.pytest_sweep() -- that shells out
to `pytest evals optimize harness`, which would re-collect THIS file and recurse.
We test the pure functions (lint_cases, red_team_keeplogic, eval_suite_green,
pii_pattern) directly.

Run:  python3 -m pytest loop-team/evals/test_verify_build.py -q
"""
import json
import os
import sys
import tempfile
import unittest

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
OPT_DIR = os.path.normpath(os.path.join(EVALS_DIR, "..", "optimize"))
sys.path.insert(0, EVALS_DIR)
sys.path.insert(0, OPT_DIR)

import verify_build as vb  # noqa: E402


def _write(d, name, obj):
    with open(os.path.join(d, name), "w", encoding="utf-8") as f:
        json.dump(obj, f)


GOOD_TRAP = {"id": "t1", "expected": "FAIL", "artifact": "a role marked PASS but $1 < $2",
             "objective_fact": "1 < 2"}
GOOD_PASS = {"id": "g1", "expected": "PASS", "artifact": "a role marked PASS, $9 >= $2",
             "objective_fact": "9 >= 2"}


class LintRealCases(unittest.TestCase):
    def test_real_case_dirs_pass(self):
        ok, report = vb.lint_cases()
        self.assertTrue(ok, report["problems"])
        # Both shipped dirs should be balanced (traps AND goods present).
        for d, s in report["per_dir"].items():
            if s["files"]:
                self.assertGreater(s["traps"], 0, d)
                self.assertGreater(s["goods"], 0, d)


class LintCatchesDefects(unittest.TestCase):
    def test_balanced_tmp_dir_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "t1.json", GOOD_TRAP)
            _write(d, "g1.json", GOOD_PASS)
            ok, rep = vb.lint_cases([d])
            self.assertTrue(ok, rep["problems"])

    def test_leak_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            leaky = dict(GOOD_TRAP, artifact="the answer hinges on 1 < 2 here")
            # objective_fact "1 < 2" is a substring of the artifact -> leak
            _write(d, "t1.json", leaky)
            _write(d, "g1.json", GOOD_PASS)
            ok, rep = vb.lint_cases([d])
            self.assertFalse(ok)
            self.assertTrue(any("LEAK" in p for p in rep["problems"]), rep["problems"])

    def test_bad_json_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "broken.json"), "w") as f:
                f.write("{not valid json")
            _write(d, "g1.json", GOOD_PASS)
            ok, rep = vb.lint_cases([d])
            self.assertFalse(ok)
            self.assertTrue(any("invalid JSON" in p for p in rep["problems"]))

    def test_bad_label_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "x.json", dict(GOOD_TRAP, expected="false-pass"))  # wrong case
            _write(d, "g1.json", GOOD_PASS)
            ok, rep = vb.lint_cases([d])
            self.assertFalse(ok)
            self.assertTrue(any("bad expected label" in p for p in rep["problems"]))

    def test_missing_required_field_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            bad = {"expected": "FAIL", "artifact": "x", "objective_fact": "z"}  # no id
            _write(d, "x.json", bad)
            _write(d, "g1.json", GOOD_PASS)
            ok, rep = vb.lint_cases([d])
            self.assertFalse(ok)
            self.assertTrue(any("missing/empty required field" in p for p in rep["problems"]))

    def test_one_sided_suite_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            _write(d, "t1.json", GOOD_TRAP)
            _write(d, "t2.json", dict(GOOD_TRAP, id="t2"))  # all traps, no goods
            ok, rep = vb.lint_cases([d])
            self.assertFalse(ok)
            self.assertTrue(any("one-sided" in p for p in rep["problems"]))

    def test_pii_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            # use a fake key prefix (sk-ant) as the marker -- it's caught by the
            # lint but is NOT one of the personal markers the pre-push guard greps,
            # so this test file can't itself trip the guard.
            _write(d, "t1.json", dict(GOOD_TRAP,
                                      artifact="oops pasted sk-ant-deadbeefcafe into the role marked PASS"))
            _write(d, "g1.json", GOOD_PASS)
            ok, rep = vb.lint_cases([d])
            self.assertFalse(ok)
            self.assertTrue(any("PII" in p for p in rep["problems"]), rep["problems"])


class PiiPattern(unittest.TestCase):
    def test_pattern_matches_key_and_name(self):
        """Oga 2026-07-02: clone-portability + removed reconstructable personal-name fragments from a published file."""
        pat = vb.pii_pattern()
        self.assertTrue(pat.search("sk-ant-xxxx"))  # key prefix always covered
        self.assertFalse(pat.search("a perfectly clean synthetic artifact"))
        # Load a personal marker at runtime the same way verify_build does (from
        # the LOCAL, gitignored markers file) -- zero personal literals in this
        # file. Upper-cased so we still prove the loaded pattern matches AND is
        # case-insensitive.
        marker = None
        if os.path.isfile(vb.PII_MARKERS):
            with open(vb.PII_MARKERS, encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith("#") and s not in vb._KEY_PREFIXES:
                        marker = s
                        break
        if marker is None:
            self.skipTest("no local personal markers; pattern falls back to key "
                          "prefixes — personal-marker matching checkable only "
                          "where .pii-markers.local exists")
        self.assertTrue(pat.search(marker.upper()))


class OperationalInvariants(unittest.TestCase):
    """The resilience RULE made an enforced CHECK. The real tree must PASS; a
    source with each violation must FAIL -- proving the check discriminates."""

    def test_real_tree_passes(self):
        ok, rep = vb.operational_invariants()
        self.assertTrue(ok, rep["problems"])
        self.assertGreater(rep["scanned"], 0)

    def test_unwrapped_live_call_fails(self):
        bad = ("client = anthropic.Anthropic(api_key=k, max_retries=0)\n"
               "def llm(p):\n"
               "    msg = client.messages.create(model=m, messages=[])\n"
               "    return msg\n")  # no call_with_retry anywhere near
        probs = vb.scan_source_invariants("bad.py", bad)
        self.assertTrue(any("not wrapped in call_with_retry" in p for p in probs), probs)

    def test_wrapped_live_call_passes(self):
        good = ("client = anthropic.Anthropic(api_key=k, max_retries=0)\n"
                "def llm(p):\n"
                "    def _call():\n"
                "        return client.messages.create(model=m, messages=[])\n"
                "    return call_with_retry(_call)\n")
        self.assertEqual(vb.scan_source_invariants("good.py", good), [])

    def test_client_without_max_retries_fails(self):
        bad = "c = anthropic.Anthropic(api_key=k)\n"
        probs = vb.scan_source_invariants("bad.py", bad)
        self.assertTrue(any("without max_retries=0" in p for p in probs), probs)

    def test_subprocess_without_timeout_fails(self):
        bad = "p = subprocess.run([exe, '-m', 'pytest'], capture_output=True)\n"
        probs = vb.scan_source_invariants("bad.py", bad)
        self.assertTrue(any("without timeout=" in p for p in probs), probs)

    def test_subprocess_with_timeout_passes(self):
        good = "p = subprocess.run([exe], capture_output=True, timeout=600)\n"
        self.assertEqual(vb.scan_source_invariants("good.py", good), [])

    def test_nested_subprocess_outer_missing_timeout_fails(self):
        # FALSE-NEGATIVE the independent verifier found: the OUTER subprocess.run
        # has no timeout=, but a NESTED subprocess.run(..., timeout=5) is in its
        # args. The inner timeout must NOT satisfy the outer call.
        bad = ("p = subprocess.run([cmd], capture_output=True, "
               "input=subprocess.run([x], timeout=5).stdout)\n")
        probs = vb.scan_source_invariants("bad.py", bad)
        self.assertTrue(any("without timeout=" in p for p in probs), probs)

    def test_messages_create_inside_string_not_flagged(self):
        # FALSE-POSITIVE the verifier found: a messages.create( inside a docstring
        # / string literal is documentation, not a live call -> must NOT be flagged.
        ok_src = 'DOC = """client.messages.create(model=m, messages=[])"""\n'
        self.assertEqual(vb.scan_source_invariants("doc.py", ok_src), [])
        # and a subprocess.run / Anthropic( mentioned only in a string is ignored too
        ok2 = "HELP = 'use subprocess.run(cmd) and anthropic.Anthropic(key)'\n"
        self.assertEqual(vb.scan_source_invariants("doc.py", ok2), [])

    def test_openai_unwrapped_call_fails(self):
        bad = ("client = OpenAI(api_key=k, max_retries=0)\n"
               "def llm(p):\n"
               "    r = client.chat.completions.create(model=m, messages=[])\n"
               "    return r\n")  # no call_with_retry
        probs = vb.scan_source_invariants("bad.py", bad)
        self.assertTrue(any("not wrapped in call_with_retry" in p for p in probs), probs)

    def test_openai_client_without_max_retries_fails(self):
        bad = "c = OpenAI(api_key=k)\n"
        probs = vb.scan_source_invariants("bad.py", bad)
        self.assertTrue(any("without max_retries=0" in p for p in probs), probs)

    def test_openai_wrapped_and_configured_passes(self):
        good = ("client = OpenAI(api_key=k, max_retries=0)\n"
                "def llm(p):\n"
                "    def _call():\n"
                "        return client.chat.completions.create(model=m, messages=[])\n"
                "    return call_with_retry(_call)\n")
        self.assertEqual(vb.scan_source_invariants("good.py", good), [])

    def test_multiline_call_args_are_inspected(self):
        # the balanced-paren reader must see args that span lines
        good = ("p = subprocess.run(\n"
                "    [exe, '-m', 'pytest'],\n"
                "    cwd=d, capture_output=True, timeout=600)\n")
        self.assertEqual(vb.scan_source_invariants("good.py", good), [])
        bad = ("c = anthropic.Anthropic(\n"
               "    api_key=k,\n"
               "    base_url=u)\n")  # spans lines, no max_retries=0
        self.assertTrue(any("without max_retries=0" in p
                            for p in vb.scan_source_invariants("bad.py", bad)))


class ReasoningCaptureInvariant(unittest.TestCase):
    """Decision modules must capture reasoning (run_role_explained /
    make_explained_judge), never a bare verdict path."""

    def test_real_decision_modules_pass(self):
        ok, rep = vb.reasoning_capture_invariant()
        self.assertTrue(ok, rep["problems"])
        self.assertEqual(set(rep["modules"]),
                         {"evals/meta_validate.py", "evals/adversarial_loop.py"})

    def test_missing_reasoning_capture_fails(self):
        bad = "verdict = make_role_judge(llm, prompt)(case)\n"
        probs = vb._scan_decision_source("evals/x.py", bad)
        self.assertTrue(any("does not capture reasoning" in p for p in probs), probs)
        self.assertTrue(any("bare make_role_judge" in p for p in probs), probs)

    def test_bare_run_role_fails(self):
        bad = "v = run_role(llm, prompt, case)\nx = run_role_explained(llm, p, c)\n"
        # has run_role_explained (capture present) BUT also a bare run_role( -> flagged
        probs = vb._scan_decision_source("evals/x.py", bad)
        self.assertTrue(any("bare run_role(" in p for p in probs), probs)

    def test_explained_path_passes(self):
        good = ("res = run_role_explained(llm, prompt, case)\n"
                "j = make_explained_judge(llm, prompt)\n")
        self.assertEqual(vb._scan_decision_source("evals/x.py", good), [])

    def test_prose_mention_not_flagged(self):
        # run_role/make_role_judge mentioned only in a docstring/comment is fine
        ok_src = ('"""use run_role_explained, not run_role()."""\n'
                  "j = make_explained_judge(llm, p)\n")
        self.assertEqual(vb._scan_decision_source("evals/x.py", ok_src), [])


class RedTeamAndGreen(unittest.TestCase):
    def test_red_team_probes_hold(self):
        ok, rep = vb.red_team_keeplogic()
        self.assertTrue(ok, rep["probes"])
        self.assertEqual(len(rep["probes"]), 3)
        self.assertTrue(all(p for _, p in rep["probes"]))

    def test_eval_suite_is_green(self):
        ok, rep = vb.eval_suite_green()
        self.assertTrue(ok, rep)
        self.assertEqual(rep["missed"], 0)
        self.assertEqual(rep["regression"], 0)


if __name__ == "__main__":
    unittest.main()


class TopLevelLint(unittest.TestCase):
    """AC-C2: per-target schema lint over top-level cases/ (previously unlinted)."""

    def test_live_corpus_passes(self):
        ok, rep = vb.lint_toplevel_cases()
        self.assertTrue(ok, rep["problems"])

    def test_unknown_target_and_missing_field_flagged(self):
        import json as _j, tempfile, os as _o
        d = tempfile.mkdtemp()
        _j.dump({"id": "bad1", "expected": "FAIL", "target": "mystery"},
                open(_o.path.join(d, "bad1.json"), "w"))
        _j.dump({"id": "bad2", "expected": "FAIL", "target": "slop_metrics",
                 "code_before": "x=1"},  # code_after missing
                open(_o.path.join(d, "bad2.json"), "w"))
        ok, rep = vb.lint_toplevel_cases(case_dir=d)
        self.assertFalse(ok)
        probs = " ".join(rep["problems"])
        self.assertIn("unknown target", probs)
        self.assertIn("code_after", probs)

    def test_empty_but_present_field_is_valid(self):
        import json as _j, tempfile, os as _o
        d = tempfile.mkdtemp()
        _j.dump({"id": "g", "expected": "FALSE-PASS", "target": "citation_grounding",
                 "artifacts": {}, "model_output": {"claims": []}},
                open(_o.path.join(d, "g.json"), "w"))
        ok, rep = vb.lint_toplevel_cases(case_dir=d)
        self.assertTrue(ok, rep["problems"])
