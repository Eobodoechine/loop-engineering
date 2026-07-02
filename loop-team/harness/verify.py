#!/usr/bin/env python3
"""Loop Team -- Verifier harness.

Deterministically runs a project's tests/build and emits a structured JSON
verdict. This is the objective signal the whole loop optimizes against:
cheap, fast, and hard to fake.

No third-party dependencies. Auto-detects:
  - Python: pytest if importable, else `unittest discover`
  - Node:   vitest or jest when package.json declares one (via npx)

Ecosystem gating is content-aware: a bare `tests/` directory with no real
Python test files (no .py under it, no test_*.py / *_test.py anywhere, no
pytest.ini / pyproject [tool.pytest]) does NOT trigger the Python branch.
When both a real Python test signal and a Node test runner are present,
both run and the results are ANDed; the JSON keeps a single-string
`runner` field for the primary runner and additionally exposes a
`runners` list (additive; existing consumers that read `runner` alone are
unaffected).

Usage:
    python verify.py <project_dir>

Exit code: 0 if passed, 1 if failed, 2 on usage error.
Always prints a JSON object: {passed, runner, summary, output}.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

TIMEOUT = 600  # seconds


def _zero_tests(output, code):
    """Return True when a run collected 0 tests (a false-green).

    Runner-agnostic: matches unittest's "Ran 0 tests" (which exits 0 with
    "OK"), pytest's "no tests ran" banner, or pytest's exit code 5 (the
    "no tests collected" status). Real runs ("Ran 7 tests ... OK",
    "7 passed") return False.
    """
    text = output or ""
    if re.search(r"\bRan 0 tests\b", text):
        return True
    if re.search(r"\bno tests ran\b", text):
        return True
    if code == 5:
        return True
    return False


def run(cmd, cwd, timeout=TIMEOUT, env=None):
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True,
                           text=True, timeout=timeout, env=env)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "TIMEOUT after %ss" % timeout
    except FileNotFoundError as e:
        return 127, "", str(e)


def has_module(mod, cwd):
    code, _, _ = run([sys.executable, "-c", "import %s" % mod], cwd)
    return code == 0


def has_python_tests(project):
    """True only on ACTUAL Python-test evidence (content-aware).

    A directory literally named ``tests/`` is no longer sufficient by
    itself -- an all-TypeScript ``tests/`` dir (e.g. a vitest project) must
    NOT route into the pytest branch. Real evidence is any of:
      - a .py file anywhere under a tests/ directory,
      - a test_*.py or *_test.py file anywhere in the project,
      - a pytest.ini file, or a pyproject.toml with a [tool.pytest...] table.

    (No external callers depend on the old loose "any tests/ dir" behavior
    -- verified by grep; this is the only call site in the repo.)
    """
    tests_dir = os.path.join(project, "tests")
    if os.path.isdir(tests_dir):
        for _, _, files in os.walk(tests_dir):
            if any(f.endswith(".py") for f in files):
                return True
    for root, _, files in os.walk(project):
        if os.sep + "node_modules" in root + os.sep:
            continue
        for f in files:
            if f.startswith("test_") and f.endswith(".py"):
                return True
            if f.endswith("_test.py"):
                return True
    if os.path.isfile(os.path.join(project, "pytest.ini")):
        return True
    pyproject = os.path.join(project, "pyproject.toml")
    if os.path.isfile(pyproject):
        try:
            with open(pyproject, "r") as f:
                if re.search(r"^\[tool\.pytest", f.read(), re.MULTILINE):
                    return True
        except OSError:
            pass
    return False


def _load_package_json(project):
    path = os.path.join(project, "package.json")
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def detect_node_runner(project):
    """Return 'vitest', 'jest', or None from package.json's declared runner.

    Checks dependencies/devDependencies for the package name, and
    scripts.test for a mention of the runner name, per the spec's
    detection order.
    """
    pkg = _load_package_json(project)
    if pkg is None:
        return None
    deps = {}
    deps.update(pkg.get("dependencies") or {})
    deps.update(pkg.get("devDependencies") or {})
    scripts = pkg.get("scripts") or {}
    test_script = scripts.get("test") or ""
    for name in ("vitest", "jest"):
        if name in deps:
            return name
        if name in test_script:
            return name
    return None


def node_runner_argv(name):
    if name == "vitest":
        # NOTE: the spec text says `--reporter=basic`, but vitest's actual
        # built-in reporter names (verified live against the installed
        # vitest 4.1.9 on the VAC1 target) are default/agent/minimal/blob/
        # dot/verbose/json/tap/tap-flat/junit/tree/hanging-process/
        # github-actions -- there is no "basic" reporter. Passing it makes
        # vitest try to resolve "basic" as a custom reporter MODULE, which
        # fails at startup before any test runs (a false, non-representative
        # failure that would masquerade as a real test failure). Using the
        # closest non-interactive built-in, "default", instead.
        return ["npx", "vitest", "run", "--reporter=default"]
    if name == "jest":
        return ["npx", "jest", "--ci"]
    raise ValueError("unknown node runner: %s" % name)


def _run_one(label, argv, project, env, _attempt_log):
    """Run one candidate runner; return a result dict, or None if the
    runner binary itself is missing (code 127) so the caller can move on."""
    _t0 = time.monotonic()
    code, out, err = run(argv, project, env=env)
    _attempt_log.append((label, " ".join(str(a) for a in argv), code,
                          round(time.monotonic() - _t0, 3)))
    if code == 127:  # runner binary missing -- caller tries the next candidate
        return None
    combined = (out + "\n" + err).strip()
    zero = _zero_tests(combined, code)
    return {
        "passed": code == 0 and not zero,
        "zero": zero,
        "summary": "0 tests collected — forced fail" if zero else "exit=%s" % code,
        "output": combined[-8000:],
    }


def detect_and_run(project):
    _attempt_log = []  # list of (label, cmd_str, exit_code, duration_s)
    _start = time.monotonic()

    _env = os.environ.copy()
    _parent = str(pathlib.Path(project).parent.resolve())
    _existing = _env.get("PYTHONPATH", "")
    _env["PYTHONPATH"] = (_parent + os.pathsep + _existing) if _existing else _parent

    def _finish(passed, runner, summary, output, runners=None):
        result = {
            "passed": passed,
            "runner": runner,
            "summary": summary,
            "output": output,
            "duration_s": round(time.monotonic() - _start, 3),
            "attempts": [
                {"label": lbl, "cmd": cmd, "exit_code": ec, "duration_s": dur}
                for lbl, cmd, ec, dur in _attempt_log
            ],
        }
        if runners is not None:
            result["runners"] = runners
        return result

    # -- Python candidates (content-aware gate; see has_python_tests) -----
    python_candidates = []
    if has_python_tests(project):
        if has_module("pytest", project):
            py_runner = "pytest" if shutil.which("pytest") else None
            argv = [py_runner, "-q"] if py_runner else [sys.executable, "-m", "pytest", "-q"]
            python_candidates.append(("pytest", argv))
        else:
            python_candidates.append(("unittest",
                                      [sys.executable, "-m", "unittest", "discover",
                                       "-s", ".", "-p", "test_*.py", "-v"]))

    # -- Node candidate: only a KNOWN runner (vitest/jest) is used; a
    #    package.json with no known runner declared is handled below as
    #    the loud forced-fail case (VAC7), same as "no manifest" (VAC4). --
    has_package_json = os.path.isfile(os.path.join(project, "package.json"))
    node_name = detect_node_runner(project) if has_package_json else None
    node_candidate = (node_name, node_runner_argv(node_name)) if node_name else None

    if not python_candidates and not node_candidate:
        if has_package_json:
            summary = ("package.json present but declares no known test runner "
                       "(looked for vitest/jest) and no Python test signals found — "
                       "forced fail.")
        else:
            summary = "No tests detected (looked for tests/, test_*.py, *_test.py, package.json)."
        return _finish(False, None, summary, "")

    # -- Single-ecosystem paths (existing fallback-chain behavior, now also
    #    covering the pure-Node case) ---------------------------------
    if python_candidates and not node_candidate:
        last_err = None
        for label, argv in python_candidates:
            res = _run_one(label, argv, project, _env, _attempt_log)
            if res is None:
                last_err = "runner not found: %s" % label
                continue
            return _finish(res["passed"], label, res["summary"], res["output"])
        return _finish(False, None, "No usable test runner found.", last_err or "")

    if node_candidate and not python_candidates:
        label, argv = node_candidate
        res = _run_one(label, argv, project, _env, _attempt_log)
        if res is None:
            return _finish(False, None, "runner not found: %s" % label, "")
        return _finish(res["passed"], label, res["summary"], res["output"])

    # -- Dual-ecosystem: both genuinely present -> run BOTH, AND the result.
    #    Contract protection: no exact-match consumer of the `runner` field
    #    value was found in the repo (grepped before writing this), but the
    #    safe branch is followed anyway -- `runner` stays a single primary
    #    name and the pair is exposed additively via `runners`. -----------
    py_label, py_argv = python_candidates[0]
    py_res = _run_one(py_label, py_argv, project, _env, _attempt_log)
    node_label, node_argv = node_candidate
    node_res = _run_one(node_label, node_argv, project, _env, _attempt_log)

    if py_res is None and node_res is None:
        return _finish(False, None, "No usable test runner found.", "")
    if py_res is None:
        return _finish(node_res["passed"], node_label, node_res["summary"], node_res["output"])
    if node_res is None:
        return _finish(py_res["passed"], py_label, py_res["summary"], py_res["output"])

    both_passed = py_res["passed"] and node_res["passed"]
    parts = []
    if py_res["zero"]:
        parts.append("%s: 0 tests collected — forced fail" % py_label)
    else:
        parts.append("%s: %s" % (py_label, py_res["summary"]))
    if node_res["zero"]:
        parts.append("%s: 0 tests collected — forced fail" % node_label)
    else:
        parts.append("%s: %s" % (node_label, node_res["summary"]))
    combined_output = (
        "--- %s ---\n%s\n\n--- %s ---\n%s"
        % (py_label, py_res["output"], node_label, node_res["output"])
    )[-8000:]
    return _finish(
        both_passed,
        py_label,  # primary single-name runner kept for contract safety
        "; ".join(parts),
        combined_output,
        runners=[py_label, node_label],
    )


def _smoke_gate(project):
    """AC-RH4: structural, manifest-declared live-smoke gate.

    If <project>/smoke_manifest.json exists (schema {"artifacts": [relpath,
    ...]}), extract URLs from each listed artifact and sweep them via
    live_smoke. Returns (smoke_dict, error) where smoke_dict is the additive
    {"ran", "passed", "dead"} JSON field and error is a forced-fail message
    (or None). The caller ANDs smoke_dict["passed"] into the overall verdict
    and treats a non-None error as a LOUD forced fail — never an exception,
    preserving the always-prints-JSON contract.

    Blocking semantics are live_smoke.summarize()'s: its `blocking` list is
    dead + nav_failed + errored + proxy_failed + launch_failed — BOT_WALLED
    is deliberately excluded, so a bot-walled URL never fails the gate while
    a DEAD one always does (headless authority is DEAD-only, 2026-06-20).

    Zero-URL artifacts short-circuit BEFORE any sweep call: sweep()'s
    playwright import is function-local, and live_smoke's module import
    pulls in no playwright, so this path never imports playwright
    (offline/CI-safe).
    """
    manifest_path = os.path.join(project, "smoke_manifest.json")
    if not os.path.isfile(manifest_path):
        # Manifest absent -> no behavior change; smoke key is purely additive.
        return {"ran": False, "passed": True, "dead": []}, None

    try:
        with open(manifest_path, "r") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        return ({"ran": False, "passed": False, "dead": []},
                "malformed smoke_manifest.json (%s) — smoke gate forced fail" % e)

    artifacts = data.get("artifacts") if isinstance(data, dict) else None
    if not isinstance(artifacts, list) or \
            not all(isinstance(a, str) for a in artifacts):
        return ({"ran": False, "passed": False, "dead": []},
                'malformed smoke_manifest.json: expected schema '
                '{"artifacts": ["<relpath>", ...]} — smoke gate forced fail')

    missing = [a for a in artifacts
               if not os.path.isfile(os.path.join(project, a))]
    if missing:
        return ({"ran": False, "passed": False, "dead": []},
                "smoke_manifest.json lists artifact file(s) that do not "
                "exist: %s — smoke gate forced fail" % ", ".join(missing))

    try:
        # Lazy import: live_smoke lives beside this file; importing it does
        # NOT import playwright (that import is local to sweep()).
        _here = os.path.dirname(os.path.abspath(__file__))
        if _here not in sys.path:
            sys.path.insert(0, _here)
        import live_smoke

        urls = []
        for a in artifacts:
            for u in live_smoke.extract_urls(os.path.join(project, a)):
                if u not in urls:
                    urls.append(u)

        if not urls:
            # Zero URLs across all artifacts -> trivially passed, and no
            # sweep call means playwright is never imported.
            return {"ran": True, "passed": True, "dead": []}, None

        # _safe_sweep is live_smoke's own crash-safe wrapper around sweep():
        # a missing playwright package or launch crash becomes LAUNCH_FAILED
        # rows (blocking) instead of an uncaught exception.
        results = live_smoke._safe_sweep(urls)
        summary = live_smoke.summarize(results)
        return ({"ran": True, "passed": summary["passed"],
                 "dead": summary["dead"]}, None)
    except Exception as e:  # defensive: JSON contract over any surprise
        return ({"ran": False, "passed": False, "dead": []},
                "smoke gate error while processing smoke_manifest.json: "
                "%s — forced fail" % e)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"passed": False, "runner": None,
                          "summary": "usage: verify.py <project_dir>",
                          "output": ""}))
        sys.exit(2)
    project = os.path.abspath(sys.argv[1])
    if not os.path.isdir(project):
        print(json.dumps({"passed": False, "runner": None,
                          "summary": "not a directory: %s" % project,
                          "output": ""}))
        sys.exit(2)
    result = detect_and_run(project)
    smoke, smoke_error = _smoke_gate(project)
    result["smoke"] = smoke  # additive; existing contract keys untouched
    if smoke_error is not None:
        # LOUD forced fail: explanatory, in-JSON, never an exception.
        result["passed"] = False
        result["summary"] = ("%s | SMOKE GATE FORCED FAIL: %s"
                             % (result.get("summary") or "", smoke_error))
    elif smoke["ran"] and not smoke["passed"]:
        # AND the smoke pass into the overall verdict.
        result["passed"] = False
        result["summary"] = ("%s | live-smoke gate FAILED (dead: %s)"
                             % (result.get("summary") or "",
                                ", ".join(smoke["dead"]) or "none — see smoke buckets"))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
